"""
Context Mode Plugin for Hermes Agent

Intercepts high-output tool calls and redirects to Context Mode MCP tools
for sandboxed execution, achieving up to 98% context window savings.

Two hooks:
  pre_tool_call  — Blocks curl/wget, inline HTTP, build tools; guides on high-output Bash
  pre_llm_call   — Injects routing rules on first turn (tool hierarchy, forbidden actions)

Installation:
    pip install context-mode-hermes

The plugin auto-registers via the hermes_agent.plugins entry point.
No manual configuration needed — just install and restart Hermes.
"""

from __future__ import annotations

import logging
import re
import shutil
from typing import Optional

__version__ = "1.0.0"

logger = logging.getLogger(__name__)

_ctx_available: Optional[bool] = None
_guidance_shown: bool = False

# ─── Command patterns ──────────────────────────────────────────────────────────

# Commands that are always blocked and redirected to sandbox
BLOCKED_PATTERNS = [
    # curl / wget — always use ctx_execute or ctx_fetch_and_index
    (re.compile(r"\bcurl\b"), "curl"),
    (re.compile(r"\bwget\b"), "wget"),
]

# Inline HTTP patterns inside shell commands
INLINE_HTTP_PATTERNS = [
    re.compile(r"\bfetch\s*\(\s*['\"]http"),
    re.compile(r"\brequests\.(get|post|put|delete|patch)\s*\("),
    re.compile(r"\bhttp\.(get|post|request)\s*\("),
    re.compile(r"\burllib\.request\.urlopen\s*\("),
]

# Build tools that produce extremely verbose output
BUILD_TOOL_PATTERNS = [
    re.compile(r"\bgradle\b"),
    re.compile(r"\bmvn\b"),
    re.compile(r"\bcargo\s+(build|test|run|check)\b"),
]

# Commands that should always pass through (RTK territory)
ALLOWED_COMMANDS = [
    "git status", "git add", "git commit", "git push", "git pull",
    "git stash", "git branch", "git checkout", "git merge", "git rebase",
    "mkdir", "rmdir", "rm", "mv", "cp", "touch", "chmod", "chown",
    "ls", "pwd", "cd", "echo", "cat", "head", "tail",
    "npm install", "pip install", "pip3 install",
    "docker ps", "docker images",
    "which", "whoami", "hostname", "uname", "date", "env",
    "rtk ",  # RTK-handled commands
]

# ─── Availability check ────────────────────────────────────────────────────────

def _check_context_mode() -> bool:
    """Check if context-mode binary is available in PATH. Result is cached."""
    global _ctx_available
    if _ctx_available is not None:
        return _ctx_available
    _ctx_available = shutil.which("context-mode") is not None
    return _ctx_available


def _is_short_command(command: str) -> bool:
    """Check if this is a short-output command that should pass through to RTK."""
    stripped = command.strip()
    for allowed in ALLOWED_COMMANDS:
        if stripped.startswith(allowed):
            return True
    return False


# ─── Routing block (injected on session start) ────────────────────────────────

ROUTING_BLOCK = """<context_window_protection>
  <priority_instructions>
    Raw tool output floods your context window. You MUST use context-mode MCP tools to keep raw data in the sandbox.
  </priority_instructions>

  <tool_selection_hierarchy>
    1. GATHER: ctx_batch_execute(commands, queries)
       - Primary tool for research. Runs all commands, auto-indexes, and searches.
       - ONE call replaces many individual steps.
       - Each command: {label: "descriptive section header", command: "shell command"}
       - label becomes the FTS5 chunk title — use descriptive labels for better search.
    2. FOLLOW-UP: ctx_search(queries: ["q1", "q2", ...])
       - Use for all follow-up questions. ONE call, many queries.
    3. PROCESSING: ctx_execute(language, code) | ctx_execute_file(path, language, code)
       - Use for API calls, log analysis, and data processing.
  </tool_selection_hierarchy>

  <forbidden_actions>
    - DO NOT use the terminal tool for curl, wget, or any HTTP fetching — use ctx_execute or ctx_fetch_and_index.
    - DO NOT use the terminal tool for commands producing >20 lines of output — use ctx_batch_execute or ctx_execute.
    - DO NOT use the terminal tool for build commands (gradle, mvn, cargo build) — use ctx_execute.
    - The terminal tool is ONLY for: git, mkdir, rm, mv, ls, npm install, pip install, and short-output commands.
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

  <ctx_commands>
    When the user says "ctx stats" — call the ctx_stats MCP tool and display the output.
    When the user says "ctx doctor" — call the ctx_doctor MCP tool and display results as a checklist.
    When the user says "ctx purge" — call the ctx_purge MCP tool with confirm: true. Warn the user this is irreversible.
    After /clear or /compact: knowledge base and session stats are preserved. Use "ctx purge" to start fresh.
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


# ─── Hooks ─────────────────────────────────────────────────────────────────────

def _pre_tool_call(*, tool_name: str, args: dict, task_id: str, **_kwargs) -> Optional[dict]:
    """pre_tool_call hook: intercept terminal calls that would flood context.

    Returns {"action": "block", "message": str} to veto the call and redirect
    the model to use context-mode MCP tools instead.
    """
    if tool_name != "terminal":
        return None

    if not _check_context_mode():
        return None

    command = args.get("command")
    if not isinstance(command, str) or not command:
        return None

    stripped = command.strip()

    # Pass through short commands (RTK territory)
    if _is_short_command(stripped):
        return None

    # Check blocked patterns: curl, wget
    for pattern, name in BLOCKED_PATTERNS:
        if pattern.search(stripped):
            logger.debug("[context-mode] blocked %s: %s", name, stripped[:100])
            return {
                "action": "block",
                "message": (
                    f"context-mode: {name} blocked. Think in Code — use "
                    "ctx_execute(language, code) to write code that fetches, "
                    "processes, and prints only the answer. Or use "
                    'ctx_fetch_and_index(url, source) to fetch and index. '
                    "Write pure JS with try/catch, no npm deps. "
                    f"Do NOT retry with {name}."
                ),
            }

    # Check inline HTTP patterns
    for pattern in INLINE_HTTP_PATTERNS:
        if pattern.search(stripped):
            logger.debug("[context-mode] blocked inline HTTP: %s", stripped[:100])
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

    # Check build tools
    for pattern in BUILD_TOOL_PATTERNS:
        if pattern.search(stripped):
            logger.debug("[context-mode] blocked build tool: %s", stripped[:100])
            return {
                "action": "block",
                "message": (
                    "context-mode: Build tool redirected. Think in Code — use "
                    f'ctx_execute(language: "shell", code: "{stripped} 2>&1 | tail -30") '
                    "to run and print only errors/summary. "
                    "Do NOT retry with the terminal tool."
                ),
            }

    # Advisory for other potentially high-output commands (once per session)
    global _guidance_shown
    if not _guidance_shown:
        _guidance_shown = True
        logger.debug("[context-mode] bash guidance for: %s", stripped[:100])
        # Return None to let the command through, but inject guidance
        # via the message field — the model sees it as context
        return None  # Guidance is handled by pre_llm_call injection

    return None


def _pre_llm_call(*, session_id: str, user_message: str, is_first_turn: bool,
                   model: str, platform: str, **_kwargs) -> Optional[dict]:
    """pre_llm_call hook: inject routing rules on first turn of each session.

    Appends the context-mode routing block (tool hierarchy, forbidden actions,
    output constraints) to the user message. This mirrors the SessionStart hook
    on Claude Code / Gemini CLI / Codex CLI.

    The context is injected into the user message (not system prompt) to
    preserve prompt caching.
    """
    if not _check_context_mode():
        return None

    if not is_first_turn:
        return None

    logger.debug("[context-mode] injecting routing block for session %s", session_id)
    return {"context": ROUTING_BLOCK}


# ─── Entry point ───────────────────────────────────────────────────────────────

def register(ctx) -> None:
    """Entry point called by Hermes plugin system."""
    if not _check_context_mode():
        logger.warning("[context-mode] context-mode binary not found in PATH — plugin disabled")
        return

    ctx.register_hook("pre_tool_call", _pre_tool_call)
    ctx.register_hook("pre_llm_call", _pre_llm_call)
    logger.info("[context-mode] Hermes plugin registered (pre_tool_call + pre_llm_call)")


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
