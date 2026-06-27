"""
Context Mode Plugin for Hermes Agent

Thin adapter that delegates tool-call routing to the Context Mode binary.
Intercepts terminal and webfetch tool calls, forwards them to the context-mode
binary's pretooluse hook, and maps the binary's decision to Hermes format.

Hooks:
  pre_tool_call   — Forwards tool calls to binary for routing decisions.
  post_tool_call  — Observational: reads markers, forwards events to SessionDB.
  pre_llm_call    — Injects routing rules on first turn; handles /compact snapshot.
  on_session_end  — Cleans up session marker files.
  on_session_reset — Cleans up session marker files.

The plugin auto-registers via the hermes_agent.plugins entry point.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Optional

__version__ = "1.3.0"

logger = logging.getLogger(__name__)

_ctx_available: Optional[bool] = None
_mcp_ready: Optional[bool] = None

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
    binary = _resolve_context_mode_binary()
    # _resolve_context_mode_binary returns "context-mode" as bare fallback
    # which will fail in subprocess — check if it's a real path
    if binary == "context-mode" and shutil.which("context-mode") is None:
        _mcp_ready = False
        return False
    try:
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


# ─── Session marker cleanup ────────────────────────────────────────────────────

def _cleanup_session_markers(session_id: str) -> None:
    """Remove session marker files from temp dir."""
    if not session_id:
        return
    for prefix in ("injected", "rejected", "latency"):
        marker = _marker_path(prefix, session_id)
        try:
            os.unlink(marker)
        except (FileNotFoundError, OSError):
            pass
    # Latency markers include tool_name suffix — glob cleanup
    import glob
    safe_session = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
    for stale in glob.glob(os.path.join(tempfile.gettempdir(), f"context-mode-latency-{safe_session}-*.txt")):
        try:
            os.unlink(stale)
        except OSError:
            pass


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
    """pre_tool_call hook: delegate routing to context-mode binary.

    Returns {"action": "block", "message": str} to veto and redirect,
    or None to passthrough.
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
        str(int(time.time() * 1000)),
    )

    # Delegate ALL routing decisions to the context-mode binary
    result = _route_via_hook(tool_name, args, session_id)

    # Write rejected marker for post_tool_call logging if blocked
    if result and result.get("action") == "block":
        _write_marker(
            _marker_path("rejected", session_id),
            f"{tool_name}:{str(args)[:200]}",
        )

    return result


def _route_via_hook(tool_name: str, args: dict, session_id: str) -> Optional[dict]:
    """Delegate pre-tool routing to the context-mode binary's pretooluse hook.

    The binary contains the canonical routing logic (safe command allowlist,
    curl/wget detection, inline HTTP, build tools, WebFetch interception).
    We call it via subprocess and map its response to Hermes format.

    Input to binary (stdin JSON):
        {"tool_name": "Bash", "tool_input": {"command": "..."}, ...}

    Output from binary (stdout JSON):
        {"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": "..."}}
        or empty/null for passthrough.
    """
    try:
        tool_map = {"terminal": "Bash", "webfetch": "WebFetch", "WebFetch": "WebFetch"}
        cc_tool_name = tool_map.get(tool_name, tool_name)

        payload = json.dumps({
            "tool_name": cc_tool_name,
            "tool_input": args if isinstance(args, dict) else {},
            "session_id": session_id,
            "cwd": os.getcwd(),
        })

        env = dict(os.environ)
        env["CLAUDE_SESSION_ID"] = session_id
        env["CLAUDE_PROJECT_DIR"] = os.getcwd()

        result = subprocess.run(
            [_resolve_context_mode_binary(), "hook", "claude-code", "pretooluse"],
            input=payload,
            text=True,
            env=env,
            timeout=5,
            capture_output=True,
        )

        if result.returncode != 0:
            logger.debug("[context-mode] pretooluse hook exited %d", result.returncode)
            return None

        stdout = result.stdout.strip()
        if not stdout:
            return None

        data = json.loads(stdout)

        hook_output = data.get("hookSpecificOutput", {})
        decision = hook_output.get("permissionDecision", "")
        reason = hook_output.get("permissionDecisionReason", "")

        if decision == "deny":
            return {"action": "block", "message": reason}
        elif decision == "ask":
            return {"action": "ask", "message": reason}
        return None

    except subprocess.TimeoutExpired:
        logger.debug("[context-mode] pretooluse hook timed out — passthrough")
        return None
    except Exception as exc:
        logger.debug("[context-mode] pretooluse hook failed: %s", exc)
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
            elapsed = int((time.time() * 1000)) - start_time
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
        _trigger_precompact(session_id)
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
    if session_id:
        _cleanup_session_markers(session_id)


@_hook_safe("on_session_reset")
def _on_session_reset(*, session_id: str = "", **_kwargs) -> None:
    if session_id:
        _cleanup_session_markers(session_id)


def _trigger_session_start(session_id: str, is_resume: bool) -> str:
    """Trigger upstream SessionStart to generate auto-injection logic."""
    try:
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


def _trigger_precompact(session_id: str) -> None:
    """Forward precompact event so upstream can build a resume snapshot before compaction."""
    try:
        env = dict(os.environ)
        env["CLAUDE_SESSION_ID"] = session_id
        env["CLAUDE_PROJECT_DIR"] = os.getcwd()

        subprocess.run(
            [_resolve_context_mode_binary(), "hook", "claude-code", "precompact"],
            text=True,
            env=env,
            timeout=2,
            capture_output=True,
        )
    except Exception as exc:
        logger.debug("[context-mode] failed to forward precompact: %s", exc)


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
