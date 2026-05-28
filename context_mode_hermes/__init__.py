"""
Context Mode Plugin for Hermes Agent

Intercepts high-output tool calls and redirects to Context Mode MCP tools
for sandboxed execution, achieving up to 98% context window savings.

Hooks:
  pre_tool_call   — Blocks curl/wget (with nuance), inline HTTP, build tools;
                    guides on high-output Bash; nudges large reads.
  post_tool_call  — Observational: logs redirect events for byte accounting.
  pre_llm_call    — Injects routing rules on first turn (tool hierarchy,
                    forbidden actions, session continuity).

Installation:
    uv pip install -e ~/tools/context-mode-hermes --python ~/.hermes/hermes-agent/venv/bin/python

The plugin auto-registers via the hermes_agent.plugins entry point.
No manual configuration needed — just install, enable in config.yaml, and restart Hermes.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from typing import Optional

__version__ = "1.1.0"

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

def _check_context_mode() -> bool:
    """Check if context-mode binary is available in PATH. Result is cached."""
    global _ctx_available
    if _ctx_available is not None:
        return _ctx_available
    _ctx_available = shutil.which("context-mode") is not None
    return _ctx_available


def _check_mcp_ready() -> bool:
    """Check if the context-mode MCP server responds to a tools/list handshake."""
    global _mcp_ready
    if _mcp_ready is not None:
        return _mcp_ready
    binary = shutil.which("context-mode")
    if not binary:
        _mcp_ready = False
        return False
    try:
        import subprocess
        handshake = (
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
            '{"protocolVersion":"2024-11-05","capabilities":{},'
            '"clientInfo":{"name":"hermes-probe","version":"1.0"}}}'
            '\n'
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


# ─── Routing block (injected on session start) ────────────────────────────────

ROUTING_BLOCK = """<context_window_protection>
  <priority_instructions>
    Raw tool output floods your context window. You MUST use context-mode MCP tools to keep raw data in the sandbox.
  </priority_instructions>

  <tool_selection_hierarchy>
    0. MEMORY: ctx_search(sort: "timeline")
       - After resume, check prior context before asking user.
    1. GATHER: ctx_batch_execute(commands, queries)
       - Primary tool for research. Runs all commands, auto-indexes, and searches.
       - ONE call replaces many individual steps.
       - Each command: {label: "descriptive section header", command: "shell command"}
       - label becomes the FTS5 chunk title — use descriptive labels for better search.
       - Use concurrency: 4-8 for I/O-bound work (network calls, API queries).
       - Keep concurrency: 1 for CPU-bound (npm test, build, lint) or shared-state commands.
    2. FOLLOW-UP: ctx_search(queries: ["q1", "q2", ...])
       - Use for all follow-up questions. ONE call, many queries.
    3. PROCESSING: ctx_execute(language, code) | ctx_execute_file(path, language, code)
       - Use for API calls, log analysis, and data processing.
    4. WEB: ctx_fetch_and_index(url, source) then ctx_search(queries)
       - Raw HTML never enters context. 24h TTL cache.
  </tool_selection_hierarchy>

  <forbidden_actions>
    - DO NOT use the terminal tool for curl, wget, or any HTTP fetching — use ctx_execute or ctx_fetch_and_index.
    - DO NOT use the terminal tool for commands producing >20 lines of output — use ctx_batch_execute or ctx_execute.
    - DO NOT use the terminal tool for build commands (gradle, mvn, cargo build) — use ctx_execute.
    - The terminal tool is ONLY for: git, mkdir, rm, mv, ls, npm install, pip install, and short-output commands.
    - NEVER use ctx_execute or ctx_execute_file for file creation/modification. Use write_file or patch.
  </forbidden_actions>

  <file_writing_policy>
    ALWAYS use write_file or patch to create or modify files.
    NEVER use ctx_execute or the terminal tool to write file content.
  </file_writing_policy>

  <output_constraints>
    <word_limit>Keep your final response under 500 words.</word_limit>
    <artifact_policy>
      Write artifacts (code, configs, PRDs) to FILES using write_file or patch.
      NEVER return them as inline text. Return only: file path + 1-line description.
    </artifact_policy>
  </output_constraints>

  <session_continuity>
    Skills, roles, and decisions persist for the entire session. Do not abandon them as the conversation grows.
    After /clear or /compact: knowledge base and session stats are preserved.
  </session_continuity>

  <ctx_commands>
    When the user says "ctx stats" — call the ctx_stats MCP tool and display the output.
    When the user says "ctx doctor" — call the ctx_doctor MCP tool and display results as a checklist.
    When the user says "ctx upgrade" — call the ctx_upgrade MCP tool and display results as a checklist.
    When the user says "ctx purge" — call the ctx_purge MCP tool with confirm: true. Warn the user this is irreversible.
  </ctx_commands>
</context_window_protection>"""

BASH_GUIDANCE = """<context_guidance>
  <tip>
    This terminal command may produce large output. To stay efficient:
    - Use ctx_batch_execute(commands, queries) for multiple commands
    - Use ctx_execute(language: "shell", code: "...") to run in sandbox
    - Only your final printed summary will enter the context.
    - The terminal tool is best for: git, mkdir, rm, mv, navigation, and short-output commands only.
  </tip>
</context_guidance>"""

READ_GUIDANCE = """<context_guidance>
  <tip>
    Reading to Edit? read_file is correct — Edit needs content in context.
    Reading to analyze/explore/summarize? Use ctx_execute_file(path, language, code) — only printed summary enters context.
  </tip>
</context_guidance>"""

# ─── PreToolUse hook ───────────────────────────────────────────────────────────

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

    if tool_name == "terminal":
        return _pre_tool_call_terminal(args, session_id)

    # Nudge on large read_file calls (no block — just guidance injection via pre_llm_call)
    # We do not block read_file because the model genuinely needs it for editing.

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
                has_file_out = re.search(r"\s(-o|--output)\s", s) or re.search(r"\s*>\s*", s) or re.search(r"\s*>>\s*", s)
            else:
                has_file_out = re.search(r"\s(-O|--output-document)\s", s) or re.search(r"\s*>\s*", s) or re.search(r"\s*>>\s*", s)

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
                re.search(r"\s-[a-zA-Z]*s|--silent", s) if is_curl
                else re.search(r"\s-[a-zA-Z]*q|--quiet", s)
            )
            if not is_silent:
                has_dangerous = True
                break

        if has_dangerous:
            logger.debug("[context-mode] blocked curl/wget stdout flood: %s", stripped[:120])
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
            safe_cmd = stripped.replace('\\', '\\\\').replace('"', '\\"')
            logger.debug("[context-mode] blocked build tool: %s", stripped[:120])
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
    """post_tool_call hook: observational logging for byte accounting and
    redirect tracking. Does not modify results.
    """
    # Future: write redirect events to a local SQLite for session continuity
    # (mirrors Claude Code's SessionDB integration).
    if not session_id:
        return
    # Log large tool outputs for debugging context usage
    result_len = len(result) if isinstance(result, str) else 0
    if result_len > 50_000:
        logger.debug(
            "[context-mode] large tool output: %s returned %d bytes in %d ms (session=%s)",
            tool_name, result_len, duration_ms, session_id[:8],
        )


# ─── PreLLMCall hook ───────────────────────────────────────────────────────────

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

    if not is_first_turn:
        return None

    logger.debug("[context-mode] injecting routing block for session %s", session_id)
    return {"context": ROUTING_BLOCK}


# ─── Session lifecycle hooks ───────────────────────────────────────────────────

def _on_session_end(*, session_id: str = "", **_kwargs) -> None:
    """Clean up per-session guidance markers on session end."""
    if session_id:
        _reset_guidance(session_id)
        logger.debug("[context-mode] cleared guidance markers for session %s", session_id)


def _on_session_reset(*, session_id: str = "", **_kwargs) -> None:
    """Clean up per-session guidance markers on session reset."""
    if session_id:
        _reset_guidance(session_id)
        logger.debug("[context-mode] cleared guidance markers on reset for session %s", session_id)


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
