"""
Context Mode Plugin for Hermes Agent

Intercepts high-output tool calls and redirects to Context Mode MCP tools
for sandboxed execution, achieving up to 98% context window savings.

Hooks:
  pre_tool_call   — Blocks curl/wget (with nuance), inline HTTP, build tools;
                    guides on high-output Bash; nudges large reads.
  post_tool_call  — Observational: reads redirect/latency markers, logs events.
  pre_llm_call    — Injects routing rules on first turn (tool hierarchy,
                    forbidden actions, session continuity).

Installation:
    uv pip install -e ~/tools/context-mode-hermes --python ~/.hermes/hermes-agent/venv/bin/python

The plugin auto-registers via the hermes_agent.plugins entry point.
No manual configuration needed — just install, enable in config.yaml, and restart Hermes.
"""

from __future__ import annotations

import functools
import logging
import os
import re
import shutil
import tempfile
from typing import Optional

__version__ = "1.2.2"

logger = logging.getLogger(__name__)

_ctx_available: Optional[bool] = None
_mcp_ready: Optional[bool] = None

# ─── Command patterns ──────────────────────────────────────────────────────────

# Shell control operators that can compose a safe command with an unbounded sink.
# Any match disqualifies the command from the allowlist.
SHELL_CONTROL_OPERATORS = re.compile(r"[|`\n\r]|\$\(|>>|>|<(?!<)|&(?!&)|&&|\|\||;")

# Commands whose output is structurally bounded (short / silent on success).
# These skip the routing nudge — the warning would be noise.
# Each pattern MUST be anchored and must NOT contain shell control operators.
SAFE_COMMAND_PATTERNS = [
    re.compile(r"^pwd$"),
    re.compile(r"^whoami$"),
    re.compile(r"^hostname(?:\s+-[a-zA-Z]+)?$"),
    re.compile(r"^uname(?:\s+-[a-zA-Z]+)?$"),
    re.compile(r"^id(?:\s+\S+)?$"),
    re.compile(r"^date(?:\s+[^\r\n]+)?$"),
    re.compile(r"^echo\s"),
    re.compile(r"^printf\s"),
    re.compile(r"^which\s+\S+(?:\s+\S+)*$"),
    re.compile(r"^type\s+\S+(?:\s+\S+)*$"),
    re.compile(r"^command\s+-v\s+\S+(?:\s+\S+)*$"),
    re.compile(r"^readlink(?:\s+[^\r\n]+)?$"),
    re.compile(r"^basename(?:\s+[^\r\n]+)?$"),
    re.compile(r"^dirname(?:\s+[^\r\n]+)?$"),
    re.compile(r"^realpath(?:\s+[^\r\n]+)?$"),
    re.compile(r"^cd(?:\s+[^\r\n]+)?$"),
    re.compile(r"^mkdir(?:\s+[^\r\n]+)?$"),
    re.compile(r"^touch\s+[^\r\n]+$"),
    re.compile(r"^mv(?!\s+-[a-zA-Z]*v[a-zA-Z]*)(?!\s+--verbose\b)\s+[^\r\n]+$"),
    re.compile(r"^cp(?!\s+-[a-zA-Z]*v[a-zA-Z]*)(?!\s+--verbose\b)\s+[^\r\n]+$"),
    re.compile(r"^rm(?!\s+-[a-zA-Z]*v[a-zA-Z]*)(?!\s+--verbose\b)\s+[^\r\n]+$"),
    re.compile(r"^ln(?!\s+-[a-zA-Z]*v[a-zA-Z]*)(?!\s+--verbose\b)\s+[^\r\n]+$"),
    re.compile(r"^ls(?!\s+-[a-zA-Z]*R)(?!\s+--recursive)(?:\s+[^\r\n]+)?$"),
    re.compile(r"^git\s+status(?:\s+[^\r\n]+)?$"),
    re.compile(r"^git\s+rev-parse(?:\s+[^\r\n]+)?$"),
    re.compile(r"^git\s+remote(?:\s+-v|\s+show\s+\S+)?$"),
    re.compile(r"^git\s+branch(?:\s+[^\r\n]+)?$"),
    re.compile(r"^git\s+config\s+--get(?:\s+[^\r\n]+)?$"),
    re.compile(r"^git\s+diff\s+--stat(?:\s+[^\r\n]+)?$"),
    re.compile(r"^git\s+diff\s+--name-only(?:\s+[^\r\n]+)?$"),
    re.compile(r"^git\s+stash\s+list$"),
    re.compile(r"^git\s+tag(?:\s+-l(?:\s+[^\r\n]+)?)?$"),
    re.compile(r"^git\s+log\s+-\d{1,2}(?:\s+[^\r\n]+)?$"),
    re.compile(r"(?:^|\s)--version(?:\s|$)"),
    re.compile(r"^\S+\s+-V(?:\s|$)"),
]

# Inline HTTP patterns inside shell commands (heredocs stripped first)
INLINE_HTTP_PATTERNS = [
    re.compile(r"\bfetch\s*\(\s*['\"](https?://|http)"),
    re.compile(r"\brequests\.(get|post|put|delete|patch)\s*\("),
    re.compile(r"\bhttp\.(get|post|request)\s*\("),
    re.compile(r"\burllib\.request\.urlopen\s*\("),
]

# Build tools that produce extremely verbose output
BUILD_TOOL_PATTERNS = [
    re.compile(r"(?:^|\s|&&|\||\;)(\.\/gradlew|gradlew|gradle|\.\/mvnw|mvnw|mvn|\.\/sbt|sbt)(\s|$)"),
    re.compile(r"\bcargo\s+(build|test|run|check)\b"),
]

# ─── Availability checks ───────────────────────────────────────────────────────

def _resolve_context_mode_binary() -> str:
    """Return the path to the context-mode binary, checking PATH then known location."""
    binary = shutil.which("context-mode")
    if binary:
        return binary
    known = os.path.expanduser("~/.hermes/node/bin/context-mode")
    if os.path.exists(known):
        return known
    return "context-mode"  # fallback — will fail loudly if truly missing


def _check_context_mode() -> bool:
    """Check if context-mode binary is available in PATH or known location. Result is cached."""
    global _ctx_available
    if _ctx_available is not None:
        return _ctx_available
    
    # Check PATH first
    if shutil.which("context-mode") is not None:
        _ctx_available = True
        return True
    
    # Fallback to known install location
    known_path = os.path.expanduser("~/.hermes/node/bin/context-mode")
    if os.path.exists(known_path):
        _ctx_available = True
        return True
    
    _ctx_available = False
    return False


def _check_mcp_ready() -> bool:
    """Check if the context-mode MCP server responds to a tools/list handshake."""
    global _mcp_ready
    if _mcp_ready is not None:
        return _mcp_ready
    binary = shutil.which("context-mode")
    if not binary:
        binary = _resolve_context_mode_binary()
        if binary == "context-mode":
            _mcp_ready = False
            return False
    try:
        import subprocess

        handshake = (
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
            '{"protocolVersion":"2024-11-05","capabilities":{},'
            '"clientInfo":{"name":"hermes-probe","version":"1.0"}}}'
            "\n"
            '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'
        )
        result = subprocess.run(
            [binary],
            input=handshake,
            capture_output=True,
            text=True,
            timeout=5,
        )
        _mcp_ready = '"tools"' in result.stdout and result.returncode == 0
    except Exception as exc:
        logger.debug("[context-mode] MCP readiness probe failed: %s", exc)
        _mcp_ready = False
    return _mcp_ready


# ─── Quote stripping (prevents false positives) ────────────────────────────────

def _strip_heredocs(cmd: str) -> str:
    """Strip heredoc content so regex only matches command tokens."""
    return re.sub(r"<<-?\s*[\"']?(\w+)[\"']?[\s\S]*?\n\s*\1", "", cmd)


def _strip_quoted_content(cmd: str) -> str:
    """Strip ALL quoted content: heredocs, single-quoted strings, double-quoted strings.
    Prevents false positives like: gh issue edit --body "text with curl in it"
    """
    no_heredoc = _strip_heredocs(cmd)
    no_single = re.sub(r"'[^']*'", "''", no_heredoc)
    no_double = re.sub(r'"[^"]*"', '""', no_single)
    return no_double


# ─── Structural boundedness check ──────────────────────────────────────────────

def _is_structurally_bounded(command: str) -> bool:
    """Return True when the command's output is bounded enough that the routing
    nudge would be noise. Conservative — unknown commands return False.
    """
    if not command:
        return False
    trimmed = command.strip()
    if SHELL_CONTROL_OPERATORS.search(trimmed):
        return False
    return any(rx.search(trimmed) for rx in SAFE_COMMAND_PATTERNS)


# ─── Guidance throttle (per-session, file-backed) ──────────────────────────────

def _guidance_marker_dir(session_id: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"cm-hermes-guidance-{session_id}")


def _guidance_once(type_name: str, session_id: str) -> bool:
    """Return True if this is the first time this guidance type has been shown
    for this session. Uses atomic file creation (O_CREAT | O_EXCL) for
    cross-process safety.
    """
    if not session_id:
        return True
    dir_path = _guidance_marker_dir(session_id)
    os.makedirs(dir_path, exist_ok=True)
    marker = os.path.join(dir_path, type_name)
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _reset_guidance(session_id: str) -> None:
    """Clear guidance markers for a session. Called on session reset/end."""
    if session_id:
        import shutil as _shutil

        _shutil.rmtree(_guidance_marker_dir(session_id), ignore_errors=True)


# ─── Marker-file helpers (cross-hook communication) ────────────────────────────

def _marker_path(prefix: str, session_id: str, suffix: str = "") -> str:
    # Sanitize session_id to prevent path traversal if it contains separators
    safe_session = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    base = f"context-mode-{prefix}-{safe_session}"
    if suffix:
        # Also sanitize suffix (tool_name may contain path separators in theory)
        safe_suffix = re.sub(r"[^a-zA-Z0-9_-]", "_", suffix)
        base += f"-{safe_suffix}"
    return os.path.join(tempfile.gettempdir(), f"{base}.txt")


def _write_marker(path: str, content: str) -> None:
    """Best-effort marker write — never block on failure."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as exc:
        logger.debug("[context-mode] marker write failed: %s", exc)


def _read_and_unlink_marker(path: str) -> Optional[str]:
    """Read marker content and delete it. Returns None if absent or unreadable."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = f.read().strip()
        os.unlink(path)
        return data
    except Exception:
        return None


# ─── Crash-resilient hook wrapper ──────────────────────────────────────────────

def _hook_safe(hook_name: str):
    """Decorator that wraps a hook so any exception is logged and swallowed.
    Hooks must never crash the agent — a failed hook is better than a broken session.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                logger.warning(
                    "[context-mode] %s hook failed (swallowed): %s",
                    hook_name,
                    exc,
                    exc_info=logger.isEnabledFor(logging.DEBUG),
                )
                return None

        return wrapper

    return decorator


# ─── Routing block (injected on session start) ─────────────────────────────────

ROUTING_BLOCK = """<context_window_protection>
  <priority_instructions>
    Every byte a tool returns enters your conversation memory and costs reasoning capacity for the rest of the session. The context-mode tools let you do the work in a sandbox and surface only the derived answer — the raw bytes stay out. Think-in-Code: program the analysis, do not compute it by reading raw data into your conversation.
  </priority_instructions>

  <tool_selection_hierarchy>
    0. MEMORY: ctx_search(sort: "timeline")
       - On resume or compaction, query prior decisions, errors, plans, user prompts before asking the user — auto-captured session memory is searchable.
    1. GATHER: ctx_batch_execute(commands, queries)
       - Primary research tool. Runs commands in parallel, auto-indexes each output, and (when queries are passed) returns matching sections in the same round trip — no follow-up search call.
       - Each command: {label: "section header", command: "shell command"}; the label becomes the FTS5 chunk title — descriptive labels improve search.
       - Use concurrency: 4-8 for I/O-bound work (network calls, API queries).
       - Keep concurrency: 1 for CPU-bound (npm test, build, lint) or shared-state commands.
    2. FOLLOW-UP: ctx_search(queries: ["q1", "q2", ...])
       - Multiple related questions about anything already indexed (your captures + session memory). Batch every question in one array; the ranking pipeline runs per-query and the round-trip cost is paid once.
    3. PROCESSING: ctx_execute(language, code) | ctx_execute_file(path, language, code)
       - Derive answers FROM data: filter, count, aggregate, parse, transform. Only what you console.log() enters your conversation; the raw bytes stay in the sandbox.
    4. WEB: ctx_fetch_and_index(url, source) then ctx_search(queries)
       - Raw HTML never enters context. 24h TTL cache.
  </tool_selection_hierarchy>

  <when_not_to_use>
    - You intend to PROCESS the output (filter, count, parse, aggregate) → use ctx_batch_execute or ctx_execute. Bash stays correct when you intend to OBSERVE a short fixed output (git status on a clean tree, whoami, pwd) or when you are mutating state (git, mkdir, rm, mv, navigation).
    - You want to analyze, summarize, or extract from a file → use ctx_execute_file. Read stays correct when you intend to Edit the file (Edit needs the exact bytes in your conversation to match against).
    - WebFetch → use ctx_fetch_and_index; full network access, results indexed for ctx_search, raw page bytes never enter your conversation.
    - ctx_execute and ctx_execute_file for file writes → these run code in a subprocess and discard the sandbox FS; they are for analysis, processing, and computation only.
  </when_not_to_use>

  <file_writing_policy>
    File writes use the native Write or Edit tool — ctx_execute, ctx_execute_file, and Bash subprocesses do not persist edits to the host filesystem.
    Applies to all file types: code, configs, plans, specs, YAML, JSON, markdown.
  </file_writing_policy>

  <output_constraints>
    <artifact_policy>
      Write artifacts (code, configs, PRDs) to files. Return only: file path + 1-line description.
    </artifact_policy>
  </output_constraints>

  <session_continuity>
    Skills, roles, and decisions set during this session remain active until the user revokes them.
    Do not drop behavioral directives as context grows.
    After /clear or /compact: knowledge base and session stats are preserved.
  </session_continuity>

  <ctx_commands>
    "ctx stats" | "ctx-stats" | "/ctx-stats" | context savings question
    → Call ctx_stats MCP tool, display full output verbatim.

    "ctx doctor" | "ctx-doctor" | "/ctx-doctor" | diagnose context-mode
    → Call ctx_doctor MCP tool, run returned shell command, display as checklist.

    "ctx upgrade" | "ctx-upgrade" | "/ctx-upgrade" | update context-mode
    → Call ctx_upgrade MCP tool, run returned shell command, display as checklist.

    "ctx purge" | "ctx-purge" | "/ctx-purge" | wipe/reset knowledge base
    → Call ctx_purge MCP tool with confirm: true. Warn: irreversible.

    After /clear or /compact: knowledge base preserved. Tell user: "context-mode knowledge base preserved. Use `ctx purge` to start fresh."
  </ctx_commands>
</context_window_protection>"""

BASH_GUIDANCE = """<context_guidance>
  <tip>
    When you intend to PROCESS the output (filter, count, parse, aggregate), use ctx_batch_execute(commands, queries) for multiple commands or ctx_execute(language: "shell", code: "...") for one — the raw output stays in the sandbox and only what you print enters your conversation. Bash stays the right surface when you intend to OBSERVE a short fixed output or when you are mutating state (git, mkdir, rm, mv, navigation).
  </tip>
</context_guidance>"""

READ_GUIDANCE = """<context_guidance>
  <tip>
    Reading to Edit the file? read_file is correct — Edit needs the exact bytes in your conversation to match against.
    Reading to analyze, summarize, or extract from the file? Use ctx_execute_file(path, language, code) — the bytes stay in the sandbox and only what your code prints enters your conversation.
  </tip>
</context_guidance>"""

GREP_GUIDANCE = """<context_guidance>
  <tip>
    Grep results may be larger than you expect. When you intend to count, filter, or aggregate matches (not just spot-check one), run the search through ctx_execute(language: "shell", code: "...") — the raw match list stays in the sandbox and only your derived answer enters your conversation.
  </tip>
</context_guidance>"""

EXTERNAL_MCP_GUIDANCE = """<context_guidance>
  <tip>
    External MCP tools commonly return large payloads (channel history, file content, search results) that enter your conversation in full. When you intend to filter, count, or aggregate that data, pipe it through ctx_execute(language, code) — the raw payload stays in the sandbox and only the derived answer enters your conversation. For docs-style fetches you will want to query later, prefer ctx_fetch_and_index(url, source) then ctx_search(queries).
  </tip>
</context_guidance>"""

# ─── PreToolUse hook ───────────────────────────────────────────────────────────

@_hook_safe("pre_tool_call")
def _pre_tool_call(
    *,
    tool_name: str,
    args: dict,
    task_id: str,
    session_id: str = "",
    **_kwargs,
) -> Optional[dict]:
    """pre_tool_call hook: intercept terminal calls that would flood context.

    Returns {"action": "block", "message": str} to veto the call and redirect
    the model to use context-mode MCP tools instead.
    """
    if not _check_context_mode():
        return None

    # MCP redirect guard: if the MCP server is not responding, do not block —
    # the agent would get stuck with redirects to broken tools.
    if not _check_mcp_ready():
        logger.debug("[context-mode] MCP not ready — passthrough for %s", tool_name)
        return None

    # Write latency marker for cross-hook timing (PostToolUse reads it)
    _write_marker(
        _marker_path("latency", session_id, tool_name),
        str(int(__import__("time").time() * 1000)),
    )

    if tool_name == "terminal":
        return _pre_tool_call_terminal(args, session_id)

    return None


def _pre_tool_call_terminal(args: dict, session_id: str) -> Optional[dict]:
    command = args.get("command")
    if not isinstance(command, str) or not command:
        return None

    stripped = command.strip()
    stripped_no_quotes = _strip_quoted_content(stripped)

    # Pass through structurally bounded commands (RTK territory)
    if _is_structurally_bounded(stripped):
        return None

    # curl/wget — allow silent file-output downloads, block stdout floods (#166).
    if re.search(r"(?:^|\s|&&|\||\;)(curl|wget)\s", stripped_no_quotes, re.I):
        segments = re.split(r"\s*(?:&&|\|\||;)\s*", stripped_no_quotes)
        has_dangerous = False
        for seg in segments:
            s = seg.strip()
            if not re.search(r"(?:^|\s)(curl|wget)\s", s, re.I):
                continue
            is_curl = re.search(r"\bcurl\b", s, re.I)
            is_wget = re.search(r"\bwget\b", s, re.I)

            # Check for file output flags
            if is_curl:
                has_file_out = (
                    re.search(r"\s(-o|--output)\s", s)
                    or re.search(r"\s*>\s*", s)
                    or re.search(r"\s*>>\s*", s)
                )
            else:
                has_file_out = (
                    re.search(r"\s(-O|--output-document)\s", s)
                    or re.search(r"\s*>\s*", s)
                    or re.search(r"\s*>>\s*", s)
                )

            if not has_file_out:
                has_dangerous = True
                break

            # Stdout aliases: -o -, -o /dev/stdout, -O -
            if is_curl and re.search(r"\s(-o|--output)\s+(-|\/dev\/stdout)(\s|$)", s):
                has_dangerous = True
                break
            if is_wget and re.search(r"\s(-O|--output-document)\s+(-|\/dev\/stdout)(\s|$)", s):
                has_dangerous = True
                break

            # Verbose/trace flags flood stderr → context
            if re.search(r"\s(-v|--verbose|--trace|-D\s+-)\b", s):
                has_dangerous = True
                break

            # Must be silent to prevent progress bar stderr flood
            is_silent = (
                re.search(r"\s-[a-zA-Z]*s|--silent", s)
                if is_curl
                else re.search(r"\s-[a-zA-Z]*q|--quiet", s)
            )
            if not is_silent:
                has_dangerous = True
                break

        if has_dangerous:
            logger.debug("[context-mode] blocked curl/wget stdout flood: %s", stripped[:120])
            _write_marker(
                _marker_path("rejected", session_id),
                f"terminal:curl/wget stdout flood:{stripped[:200]}",
            )
            return {
                "action": "block",
                "message": (
                    "context-mode: curl/wget blocked. Think in Code — use "
                    "ctx_execute(language, code) to write code that fetches, "
                    "processes, and prints only the answer. Or use "
                    "ctx_fetch_and_index(url, source) to fetch and index. "
                    "Write pure JS with try/catch, no npm deps. "
                    "Do NOT retry with curl/wget."
                ),
            }
        # All segments safe → allow through (silent file download)
        return None

    # Inline HTTP detection (strip heredocs only — quoted content in -e flags is fine)
    no_heredoc = _strip_heredocs(stripped)
    for pattern in INLINE_HTTP_PATTERNS:
        if pattern.search(no_heredoc):
            logger.debug("[context-mode] blocked inline HTTP: %s", stripped[:120])
            _write_marker(
                _marker_path("rejected", session_id),
                f"terminal:inline HTTP:{stripped[:200]}",
            )
            return {
                "action": "block",
                "message": (
                    "context-mode: Inline HTTP blocked. Think in Code — use "
                    "ctx_execute(language, code) to write code that fetches, "
                    "processes, and console.log() only the result. "
                    "Write robust pure JS with try/catch, no npm deps. "
                    "Do NOT retry with the terminal tool."
                ),
            }

    # Build tools (gradle, maven, sbt, cargo) → redirect to sandbox
    for pattern in BUILD_TOOL_PATTERNS:
        if pattern.search(stripped_no_quotes):
            safe_cmd = stripped.replace("\\", "\\\\").replace('"', '\\"')
            logger.debug("[context-mode] blocked build tool: %s", stripped[:120])
            _write_marker(
                _marker_path("rejected", session_id),
                f"terminal:build tool:{stripped[:200]}",
            )
            return {
                "action": "block",
                "message": (
                    f'context-mode: Build tool redirected. Think in Code — use '
                    f'ctx_execute(language: "shell", code: "{safe_cmd} 2>&1 | tail -30") '
                    f"to run and print only errors/summary. "
                    f"Do NOT retry with the terminal tool."
                ),
            }

    # Advisory for other potentially high-output commands (once per session)
    if _guidance_once("bash", session_id):
        # We cannot inject context from pre_tool_call in Hermes (only block).
        # Guidance is injected via pre_llm_call on first turn.
        logger.debug("[context-mode] bash guidance marker set for session %s", session_id)

    return None


# ─── PostToolCall hook (observational) ─────────────────────────────────────────

@_hook_safe("post_tool_call")
def _post_tool_call(
    *,
    tool_name: str,
    args: dict,
    result: str,
    task_id: str,
    session_id: str = "",
    duration_ms: int = 0,
    **_kwargs,
) -> None:
    """post_tool_call hook: observational logging for byte accounting,
    redirect tracking, and forwarding events to upstream context-mode
    for SessionDB tracking.
    """
    if not session_id:
        return

    result_len = len(result) if isinstance(result, str) else 0

    # ── Large output warning ──
    if result_len > 50_000:
        logger.debug(
            "[context-mode] large tool output: %s returned %d bytes in %d ms (session=%s)",
            tool_name,
            result_len,
            duration_ms,
            session_id[:8],
        )

    # ── Rejected-approach marker (from PreToolUse) ──
    rejected_data = _read_and_unlink_marker(_marker_path("rejected", session_id))
    if rejected_data:
        logger.info("[context-mode] rejected-approach: %s", rejected_data)

    # ── Latency marker (from PreToolUse) ──
    latency_data = _read_and_unlink_marker(_marker_path("latency", session_id, tool_name))
    if latency_data:
        try:
            start_time = int(latency_data)
            elapsed = int((__import__("time").time() * 1000)) - start_time
            if elapsed > 5000:
                logger.info(
                    "[context-mode] tool_latency: %s took %d ms (session=%s)",
                    tool_name,
                    elapsed,
                    session_id[:8],
                )
        except ValueError:
            pass

    # ── Forward to upstream SessionDB ──
    # By piping the tool result to context-mode's native posttooluse hook
    # masquerading as 'claude-code', we inherit the full SQLite SessionDB 
    # tracking without reinventing it in Python.
    try:
        import subprocess
        import json
        
        payload = json.dumps({
            "tool_name": tool_name,
            "tool_input": args,
            "tool_response": result
        })
        
        env = dict(os.environ)
        env["CLAUDE_SESSION_ID"] = session_id
        env["CLAUDE_PROJECT_DIR"] = os.getcwd()
        
        subprocess.run(
            [_resolve_context_mode_binary(), "hook", "claude-code", "posttooluse"],
            input=payload,
            text=True,
            env=env,
            timeout=2,
            capture_output=True
        )
    except Exception as exc:
        logger.debug("[context-mode] failed to forward event to SessionDB: %s", exc)


# ─── PreLLMCall hook ───────────────────────────────────────────────────────────

@_hook_safe("pre_llm_call")
def _pre_llm_call(
    *,
    session_id: str,
    user_message: str,
    is_first_turn: bool,
    model: str,
    platform: str,
    **_kwargs,
) -> Optional[dict]:
    """pre_llm_call hook: inject routing rules on first turn of each session.

    Appends the context-mode routing block to the user message. This mirrors
    the SessionStart hook on Claude Code / Gemini CLI / Codex CLI.
    """
    if not _check_context_mode():
        return None

    is_resume = _kwargs.get("is_resume", False)
    
    # First turn of a fresh session OR resuming an existing session:
    if is_first_turn or is_resume:
        # Avoid duplicate injection on resumes where turn=1 again
        marker = _marker_path("injected", session_id)
        if os.path.exists(marker):
            return None
            
        logger.debug("[context-mode] triggering SessionStart logic for session %s (resume=%s)", session_id, is_resume)
        
        # Read upstream SessionDB routing instructions and auto-memory
        upstream_context = _trigger_session_start(session_id, is_resume)
        
        # If upstream failed or returned empty, fallback to the baked-in block
        block = upstream_context if upstream_context else ROUTING_BLOCK
        
        _write_marker(marker, "1")
        return {"context": block}

    # Intervene on commands attempting to format the model's knowledge base
    msg = user_message.lower().strip()
    if msg in ("/clear", "/compact", "clear", "compact"):
        return {
            "context": (
                "After /clear or /compact: knowledge base preserved. Tell the user: "
                '"context-mode knowledge base preserved. Use `ctx purge` to start fresh."'
            )
        }

    return None


# ─── Session lifecycle hooks ───────────────────────────────────────────────────

@_hook_safe("on_session_end")
def _on_session_end(*, session_id: str = "", **_kwargs) -> None:
    """Clean up per-session guidance markers on session end."""
    if session_id:
        _reset_guidance(session_id)
        logger.debug("[context-mode] cleared guidance markers for session %s", session_id)


@_hook_safe("on_session_reset")
def _on_session_reset(*, session_id: str = "", **_kwargs) -> None:
    """Clean up per-session guidance markers on session reset."""
    if session_id:
        _reset_guidance(session_id)
        logger.debug("[context-mode] cleared guidance markers on reset for session %s", session_id)


def _trigger_session_start(session_id: str, is_resume: bool) -> str:
    """Trigger upstream SessionStart to generate auto-injection logic."""
    try:
        import subprocess
        import json
        
        env = dict(os.environ)
        env["CLAUDE_SESSION_ID"] = session_id
        env["CLAUDE_PROJECT_DIR"] = os.getcwd()
        
        # 'startup' for fresh sessions, 'resume' for continued sessions
        source = "resume" if is_resume else "startup"
        payload = json.dumps({"source": source})
        
        result = subprocess.run(
            [_resolve_context_mode_binary(), "hook", "claude-code", "sessionstart"],
            input=payload,
            text=True,
            env=env,
            timeout=2,
            capture_output=True
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if "hookSpecificOutput" in data and "additionalContext" in data["hookSpecificOutput"]:
                return data["hookSpecificOutput"]["additionalContext"]
    except Exception as exc:
        logger.debug("[context-mode] failed to trigger SessionStart: %s", exc)
    
    return ""


# ─── Entry point ───────────────────────────────────────────────────────────────

def register(ctx) -> None:
    """Entry point called by Hermes plugin system."""
    if not _check_context_mode():
        logger.warning("[context-mode] context-mode binary not found in PATH — plugin disabled")
        return

    mcp_ok = _check_mcp_ready()
    if not mcp_ok:
        logger.warning("[context-mode] MCP server not responding — redirects may fail")
    else:
        logger.info("[context-mode] MCP server responding — redirects active")

    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("post_tool_call", _post_tool_call)
    ctx.register_hook("pre_llm_call", _pre_llm_call)
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_hook("on_session_reset", _on_session_reset)
    logger.info(
        "[context-mode] Hermes plugin registered (pre_tool_call + post_tool_call + pre_llm_call + session_lifecycle)"
    )


class _ModuleProxy:
    """Wrapper that exposes register() as an attribute.

    Hermes calls getattr(module, "register") after ep.load().
    When the entry point references a function directly, ep.load()
    returns the function itself, which has no "register" attribute.
    This wrapper delegates attribute access to the underlying function
    so both module.register and module.register(ctx) work.
    """

    def __init__(self, fn):
        self._fn = fn

    def __call__(self, *args, **kwargs):
        return self._fn(*args, **kwargs)

    def __getattr__(self, name):
        if name == "register":
            return self._fn
        raise AttributeError(name)


# Wrap the register function so it survives getattr(module, "register")
register = _ModuleProxy(register)
