# Task 2 — Local Hermes Adapter Audit

**Scope:** Read-only audit of the local Hermes adapter plugin. No source file
(`context_mode_hermes/__init__.py`, `pyproject.toml`, `README.md`) was modified
by this task. Line ranges are exact (derived via Python `ast` parse, which is
robust to brackets inside regex string literals).

**Audited file:** `context_mode_hermes/__init__.py` — 781 content lines.
**Package:** `context-mode-hermes` v1.2.2, `requires-python >= 3.9`, no runtime
deps (pure stdlib: `functools`, `logging`, `os`, `re`, `shutil`, `tempfile`,
`typing`; `subprocess`/`json`/`time` imported lazily inside functions).
**Entry point:** `hermes_agent.plugins` → `context-mode = "context_mode_hermes:register"`.

---

## Module Overview & Layout

The plugin is a **hook-based adapter** that delegates to the upstream
`context-mode` binary/MCP server at runtime. It does NOT reimplement the MCP
server; it intercepts Hermes tool calls and *enforces routing* into upstream
sandbox tools (`ctx_execute`, `ctx_batch_execute`, `ctx_search`,
`ctx_fetch_and_index`, `ctx_purge`, `ctx_upgrade`).

Top-level symbol map (full index, for cross-reference):

| Symbol | Kind | Lines |
|---|---|---|
| `__version__` | assign | 31 |
| `logger` | assign | 33 |
| `_ctx_available` | annassign (module-global cache) | 35 |
| `_mcp_ready` | annassign (module-global cache) | 36 |
| `SHELL_CONTROL_OPERATORS` | assign (compiled regex) | 42 |
| `SAFE_COMMAND_PATTERNS` | assign (list of 35 regexes) | 47–83 |
| `INLINE_HTTP_PATTERNS` | assign (list of 4 regexes) | 86–91 |
| `BUILD_TOOL_PATTERNS` | assign (list of 2 regexes) | 94–97 |
| `_resolve_context_mode_binary` | def | 101–109 |
| `_check_context_mode` | def | 112–130 |
| `_check_mcp_ready` | def | 133–165 |
| `_strip_heredocs` | def | 170–172 |
| `_strip_quoted_content` | def | 175–182 |
| `_is_structurally_bounded` | def | 187–196 |
| `_guidance_marker_dir` | def | 201–202 |
| `_guidance_once` | def | 205–220 |
| `_reset_guidance` | def | 223–228 |
| `_marker_path` | def | 233–241 |
| `_write_marker` | def | 244–250 |
| `_read_and_unlink_marker` | def | 253–261 |
| `_hook_safe` | def (decorator factory) | 266–287 |
| `ROUTING_BLOCK` | assign (triple-quoted string) | 292–352 |
| `BASH_GUIDANCE` | assign (string) | 354–358 |
| `READ_GUIDANCE` | assign (string) | 360–365 |
| `GREP_GUIDANCE` | assign (string) | 367–371 |
| `EXTERNAL_MCP_GUIDANCE` | assign (string) | 373–377 |
| `_pre_tool_call` | def (`@_hook_safe`) | 382–413 |
| `_pre_tool_call_terminal` | def | 416–545 |
| `_post_tool_call` | def (`@_hook_safe`) | 551–628 |
| `_pre_llm_call` | def (`@_hook_safe`) | 634–681 |
| `_on_session_end` | def (`@_hook_safe`) | 687–691 |
| `_on_session_reset` | def (`@_hook_safe`) | 695–699 |
| `_trigger_session_start` | def | 702–731 |
| `register` | def | 736–755 |
| `_ModuleProxy` | class | 758–777 |
| `register` (re-wrap) | assign `register = _ModuleProxy(register)` | 781 |

> Note on the `register` re-bind at L781: after the function is defined
> (L736–755) it is wrapped once at import time as
> `register = _ModuleProxy(register)`. This makes the entry-point-loadable
> object both callable *and* expose a `.register` attribute (see
> `_ModuleProxy` below).

---

# SECTION 1 — Adapter Mechanics

Adapter mechanics = the plumbing that discovers the upstream binary, probes the
MCP server, dispatches Hermes hooks, passes data between hooks, survives
crashes, and registers itself. **None of this decides *what* to block** — that
is policy (Section 2).

### `_resolve_context_mode_binary()` — L101–109
Returns the path to the `context-mode` binary. Resolution order: (1)
`shutil.which("context-mode")` (on PATH); (2) known install location
`~/.hermes/node/bin/context-mode` (via `os.path.exists`); (3) bare fallback
string `"context-mode"` (will fail loudly downstream if truly absent). Pure
function, no caching.

### `_check_context_mode()` — L112–130  → mutates module global `_ctx_available`
Boolean availability check for the binary, **memoised** in the module-global
`_ctx_available`. Short-circuits if already resolved (`if _ctx_available is not
None: return _ctx_available`). Repeats the same PATH-then-known-location probes
as `_resolve_context_mode_binary` (logic duplicated, not delegated) and caches
the result. This is a **test-isolation hazard** — see "Module-Global Mutable
State" below.

### `_check_mcp_ready()` — L133–165  → mutates module global `_mcp_ready`
Boolean check that the upstream MCP server actually responds, **memoised** in
the module-global `_mcp_ready`. On cache miss it locates the binary (own copy of
the `shutil.which` logic; falls back to `_resolve_context_mode_binary()` and
bails if that returns the bare `"context-mode"` fallback). It then lazily
`import subprocess` and runs the binary with a 5 s timeout, feeding it a two-line
JSON-RPC handshake (`initialize` + `tools/list`). Ready is defined as
`'"tools"' in result.stdout and result.returncode == 0`. Any exception → logs
at debug and caches `False`. **Test-isolation hazard.**

### `_hook_safe(hook_name)` — L266–287
Decorator factory. Wraps a hook so **any exception is logged and swallowed**
(`return None`). Philosophy in its docstring: "a failed hook is better than a
broken session." Uses `functools.wraps` to preserve identity. This is the
crash-resilience boundary for every registered hook — all six hooks below are
decorated with `@_hook_safe(...)`.

### Marker-file helpers (cross-hook communication) — L233–261
Because a `pre_tool_call` hook in Hermes can only *block* (not inject context),
and because `post_tool_call` needs to know what was attempted, the adapter uses
temp-file markers as a side channel:

- **`_marker_path(prefix, session_id, suffix="")`** — L233–241. Builds a path
  under `tempfile.gettempdir()` of form
  `context-mode-{prefix}-{safe_session}[-{safe_suffix}].txt`. `session_id` and
  `suffix` are both **sanitised** (`re.sub(r"[^a-zA-Z0-9_-]", "_", ...)`) to
  prevent path traversal.
- **`_write_marker(path, content)`** — L244–250. Best-effort UTF-8 write;
  failures are logged at debug and swallowed (never raises).
- **`_read_and_unlink_marker(path)`** — L253–261. Atomic-ish read-then-delete;
  returns `None` if the file is absent or unreadable (any exception → `None`).

Used prefixes in practice: `"latency"` (written in `_pre_tool_call`, read in
`_post_tool_call`), `"rejected"` (written when a call is blocked, read/logged in
`_post_tool_call`), `"injected"` (written when routing block is injected in
`_pre_llm_call`, checked to avoid duplicate injection on resume).

### Guidance throttle (per-session, file-backed) — L201–228
A second, separate marker mechanism that throttles *advisory* guidance to once
per (session, type):

- **`_guidance_marker_dir(session_id)`** — L201–202. Returns
  `$TMPDIR/cm-hermes-guidance-{session_id}` (note: `session_id` is **NOT**
  sanitised here, unlike `_marker_path` — see "Open observations").
- **`_guidance_once(type_name, session_id)`** — L205–220. Returns `True` the
  first time a given `type_name` is asked for in a session, else `False`.
  Enforces uniqueness via `os.open(..., O_CREAT | O_EXCL | O_WRONLY)` (atomic
  cross-process creation). Empty `session_id` → always returns `True`.
- **`_reset_guidance(session_id)`** — L223–228. `shutil.rmtree` of the
  session's guidance dir, `ignore_errors=True`. Called on session end/reset.

### `register(ctx)` — L736–755 (then re-wrapped at L781)
Entry point called by Hermes. Refuses to register if `_check_context_mode()` is
`False` (logs a warning and returns — plugin self-disables). Probes
`_check_mcp_ready()`; logs ready vs not-ready but **registers hooks regardless**
(redirects may fail but hooks still load). Registers four hooks:
`pre_tool_call`, `post_tool_call`, `pre_llm_call`, `on_session_end`,
`on_session_reset`. *(Note: `on_session_end` and `on_session_reset` are
registered but there is no upstream session-start lifecycle registration —
session-start is instead simulated inside `_pre_llm_call` on first turn.)*

### `_ModuleProxy` — L758–777 + re-bind L781
Workaround for Hermes' entry-point loading. When the entry point references a
function directly, `importlib`'s `ep.load()` returns the function itself, which
has no `register` attribute; Hermes then does `getattr(module, "register")` and
fails. `_ModuleProxy` wraps the function so it is **both callable** (`__call__`
delegates to the underlying fn) **and exposes `.register`** (`__getattr__
returns the underlying fn for the name "register"`). Bound once at import:
`register = _ModuleProxy(register)` (L781).

---

# SECTION 2 — Policy Logic

Policy logic = the decisions about *which* commands are safe vs blocked vs
advised, the text shown to the model, and the per-hook/per-session semantics.

## 2.1 Command classification (regex)

Classification is layered: **structurally-bounded allowlist** (passes through),
then explicit **blocklist** families (curl/wget, inline HTTP, build tools),
then an **advisory** bucket. All regexes are pre-compiled at import. Quotes and
heredocs are stripped before matching to avoid false positives.

### `SHELL_CONTROL_OPERATORS` — L42 (gate for the allowlist)
```
re.compile(r"[|`\n\r]|\$\(|>>|>|<(?!<)|&(?!&)|&&|\|\||;")
```
Matches any shell control operator that could compose a safe command with an
**unbounded sink** (pipe, backtick, newline, `$(`, redirection `>`/`>>`,
`<` excluding heredoc `<<`, single `&` excluding `&&`, `&&`, `||`, `;`).
**Any match disqualifies a command from the allowlist** (`_is_structurally_bounded`
returns `False`).

### `SAFE_COMMAND_PATTERNS` — L47–83 (the allowlist, 35 entries)
Commands whose output is "structurally bounded" (short / silent on success).
Each pattern is **anchored** and must **not** contain shell control operators.
Categories:

- **Identity/env:** `^pwd$`, `^whoami$`, `^hostname(?:\s+-[a-zA-Z]+)?$`,
  `^uname(?:\s+-[a-zA-Z]+)?$`, `^id(?:\s+\S+)?$`,
  `^date(?:\s+[^\r\n]+)?$`.
- **Echo/print:** `^echo\s`, `^printf\s`.
- **Lookup:** `^which\s+\S+(?:\s+\S+)*$`, `^type\s+\S+(?:\s+\S+)*$`,
  `^command\s+-v\s+\S+(?:\s+\S+)*$`.
- **Path ops:** `^readlink(?:\s+[^\r\n]+)?$`,
  `^basename(?:\s+[^\r\n]+)?$`, `^dirname(?:\s+[^\r\n]+)?$`,
  `^realpath(?:\s+[^\r\n]+)?$`.
- **FS mutations (bounded):** `^cd(?:\s+[^\r\n]+)?$`,
  `^mkdir(?:\s+[^\r\n]+)?$`, `^touch\s+[^\r\n]+$`.
- **FS mutations with verbose EXCLUDED:** `mv`/`cp`/`rm`/`ln`, each with
  negative lookaheads forbidding verbose flags — e.g.
  `^mv(?!\s+-[a-zA-Z]*v[a-zA-Z]*)(?!\s+--verbose\b)\s+[^\r\n]+$` (so `mv -v`,
  `rm --verbose` are NOT bounded and get nudged).
- **Listing (recursive excluded):**
  `^ls(?!\s+-[a-zA-Z]*R)(?!\s+--recursive)(?:\s+[^\r\n]+)?$`.
- **Read-only git:** `git status`, `git rev-parse`, `git remote (-v|show X)`,
  `git branch`, `git config --get`, `git diff --stat`, `git diff --name-only`,
  `git stash list`, `git tag (-l ...)`, `git log -N` (1–2 digit cap).
- **Version probes:** `(?:^|\s)--version(?:\s|$)`, `^\S+\s+-V(?:\s|$)`.

### `INLINE_HTTP_PATTERNS` — L86–91 (4 entries, always blocked)
```
\bfetch\s*\(\s*['"](https?://|http)
\brequests\.(get|post|put|delete|patch)\s*\(
\bhttp\.(get|post|request)\s*\(
\burllib\.request\.urlopen\s*\(
```
Matched against heredoc-stripped text (quoted content in `-e` flags is
intentionally left in). Match → hard block.

### `BUILD_TOOL_PATTERNS` — L94–97 (2 entries, always blocked)
```
(?:^|\s|&&|\||\;)(\.\/gradlew|gradlew|gradle|\.\/mvnw|mvnw|mvn|\.\/sbt|sbt)(\s|$)
\bcargo\s+(build|test|run|check)\b
```
Matched against quote-stripped text. Match → hard block with the original
command echoed back into a `ctx_execute(... tail -30)` suggestion.

## 2.2 Quote/heredoc stripping (false-positive defence) — L170–182

- **`_strip_heredocs(cmd)`** — L170–172. Removes heredoc bodies via
  `re.sub(r"<<-?\s*[\"']?(\w+)[\"']?[\s\S]*?\n\s*\1", "", cmd)` so regexes only
  see command tokens.
- **`_strip_quoted_content(cmd)`** — L175–182. Strips heredocs, then collapses
  single-quoted (`'[^']*'` → `''`) and double-quoted (`"[^"]*"` → `""`) content.
  Prevents false positives like `gh issue edit --body "text mentioning curl"`.

## 2.3 Structural-boundedness gate — `_is_structurally_bounded()` L187–196
Conservative triage: empty → `False`; if `SHELL_CONTROL_OPERATORS` matches →
`False`; otherwise `True` iff any `SAFE_COMMAND_PATTERNS` regex matches.
**Unknown commands return `False`** (i.e. they fall through to the
blocklist/advisory path — boundedness is opt-in, not assumed).

## 2.4 Hook behaviour

### `_pre_tool_call(...)` — L382–413 (`@_hook_safe("pre_tool_call")`)
Dispatcher. Gate order:
1. If `_check_context_mode()` is False → `return None` (plugin inert).
2. If `_check_mcp_ready()` is False → passthrough (do NOT block — agent would
   be redirected to broken tools). Logs debug.
3. Write a `"latency"` marker (epoch ms) for `post_tool_call` timing.
4. If `tool_name == "terminal"` → delegate to `_pre_tool_call_terminal`.
5. Otherwise → `return None` (only the terminal tool is policed at this hook).

### `_pre_tool_call_terminal(args, session_id)` — L416–545 (core policy)
Sequence (on the stripped command):
1. **Bounded allowlist pass-through** (L424–426): if
   `_is_structurally_bounded(stripped)` → `return None`.
2. **curl/wget** (L428–498, regex `(?:^|\s|&&|\||\;)(curl|wget)\s` case-insensitive,
   on quote-stripped text): splits on `&&`/`||`/`;` into segments and inspects
   each. A segment is **dangerous** (→ block) if the curl/wget invocation lacks
   file-output flags (`-o`/`--output` for curl, `-O`/`--output-document` for
   wget, or `>`/`>>` redirection), OR targets stdout aliases (`-o -`,
   `-o /dev/stdout`, `-O -`), OR carries verbose/trace flags
   (`-v`/`--verbose`/`--trace`/`-D -`), OR is **not silent** (curl needs `-s`/
   `--silent`; wget needs `-q`/`--quiet`). If any segment is dangerous → write a
   `"rejected"` marker and `return {"action": "block", "message": ...}` pointing
   to `ctx_execute`/`ctx_fetch_and_index`. **All segments safe → allow through**
   (silent file download).
3. **Inline HTTP** (L500–518): any `INLINE_HTTP_PATTERNS` match on
   heredoc-stripped text → block with `ctx_execute` redirect + `"rejected"`
   marker.
4. **Build tools** (L520–537): any `BUILD_TOOL_PATTERNS` match on quote-stripped
   text → block, message echoes the command into a suggested
   `ctx_execute(language: "shell", code: "{cmd} 2>&1 | tail -30")`.
5. **Advisory** (L539–544): for everything else, calls `_guidance_once("bash",
   session_id)` and *sets the bash-guidance marker* (logs debug). Because Hermes
   cannot inject context from `pre_tool_call`, no guidance is returned here — it
   only touches the throttle. `return None` (the command runs).

### `_post_tool_call(...)` — L551–628 (`@_hook_safe("post_tool_call")`)
Observational only (returns `None`). Skipped entirely when `session_id` is empty.
Performs four things:
1. **Large-output warning** (L570–578): if `len(result) > 50_000` → debug log.
2. **Rejected-approach log** (L580–583): reads+unlinks the `"rejected"` marker;
   if present → `logger.info("[context-mode] rejected-approach: ...")`.
3. **Latency log** (L585–599): reads+unlinks the `"latency"` marker; if elapsed
   > 5000 ms → `logger.info("[context-mode] tool_latency: ...")`.
4. **Forward to upstream SessionDB** (L601–628): pipes `{tool_name, tool_input,
   tool_response}` as JSON to `context-mode hook claude-code posttooluse`, with
   `CLAUDE_SESSION_ID`/`CLAUDE_PROJECT_DIR` env vars set, 2 s timeout. This is
   how the plugin inherits upstream SQLite SessionDB tracking "without
   reinventing it in Python." Failures are debug-logged.

### `_pre_llm_call(...)` — L634–681 (`@_hook_safe("pre_llm_call")`)
1. Bails if `_check_context_mode()` is False.
2. On **first turn or resume** (`is_first_turn` or `is_resume`): checks an
   `"injected"` marker to avoid duplicate injection on resumes where turn
   resets to 1; if not already injected, calls
   `_trigger_session_start(session_id, is_resume)` to fetch upstream routing
   context, **falls back to the baked-in `ROUTING_BLOCK`** if upstream fails or
   returns empty, writes the `"injected"` marker, and
   `return {"context": block}`.
3. On `/clear` or `/compact` (case-insensitive, also bare `clear`/`compact`):
   `return {"context": ...}` telling the model the KB is preserved and to inform
   the user about `ctx purge`.
4. Otherwise → `return None`.

### `_trigger_session_start(session_id, is_resume)` — L702–731
Shells out to `context-mode hook claude-code sessionstart` with
`{"source": "startup"|"resume"}` (2 s timeout, CLAUDE_* env). Parses JSON;
returns `hookSpecificOutput.additionalContext` on success, else `""`. This is
how upstream's auto-injection (auto-memory, routing instructions) is pulled in
on first turn — the Hermes equivalent of Claude Code's `SessionStart` hook.

### `_on_session_end(...)` / `_on_session_reset(...)` — L687–699
Both `@_hook_safe`-wrapped, both call `_reset_guidance(session_id)` (rmtree the
guidance marker dir) when `session_id` is non-empty. Pure cleanup; no upstream
forwarding.

## 2.5 Routing / guidance text (injected into the model)

### `ROUTING_BLOCK` — L292–352
The full `<context_window_protection>` XML block injected on first turn (when
upstream is unavailable). Contains: `priority_instructions` (Think-in-Code),
`tool_selection_hierarchy` (0 MEMORY `ctx_search`, 1 GATHER `ctx_batch_execute`,
2 FOLLOW-UP `ctx_search`, 3 PROCESSING `ctx_execute`/`ctx_execute_file`, 4 WEB
`ctx_fetch_and_index`), `when_not_to_use` rules, `file_writing_policy`,
`output_constraints.artifact_policy`, `session_continuity`, and `ctx_commands`
(slash-command dispatch table: `ctx-stats`, `ctx-doctor`, `ctx-upgrade`,
`ctx-purge`). **This is a verbatim copy of context-mode's own
`<context_window_protection>` system prompt.**

### Guidance constants — L354–377
Four short `<context_guidance><tip>...</tip></context_guidance>` blocks
(**defined but currently NOT wired into any hook** — see "Open observations"):
- `BASH_GUIDANCE` (L354–358): nudge to `ctx_batch_execute`/`ctx_execute` for
  processing; Bash is right for short observation/state mutation.
- `READ_GUIDANCE` (L360–365): use `ctx_execute_file` for analysis; `read_file`
  for editing.
- `GREP_GUIDANCE` (L367–371): pipe large match lists through `ctx_execute`.
- `EXTERNAL_MCP_GUIDANCE` (L373–377): pipe large MCP payloads through
  `ctx_execute`; use `ctx_fetch_and_index` for docs.

## 2.6 Session lifecycle semantics
- **Start:** simulated in `_pre_llm_call` (first turn / resume) rather than a
  true `on_session_start` hook — there is no such hook registered.
- **Reset / End:** both clear guidance markers via `_reset_guidance`.
- **Per-session dedup:** the `"injected"` marker prevents duplicate
  `ROUTING_BLOCK` injection; `_guidance_once` would throttle advisory guidance
  per (session, type).

---

## Module-Global Mutable State (TEST-ISOLATION HAZARDS)

Tests MUST reset these between cases for isolation:

| State | Where declared | Mutated by | Reset value |
|---|---|---|---|
| `_ctx_available: Optional[bool]` | L35 (annassign) | `_check_context_mode` via `global` at **L114** | `None` |
| `_mcp_ready: Optional[bool]` | L36 (annassign) | `_check_mcp_ready` via `global` at **L135** | `None` |

These two are the **only** runtime-mutated module globals (confirmed by AST
`Global`-declaration scan: only L114 and L135 declare `global`). All other
top-level assignments are **constants** (compiled regexes, immutable strings)
or the one-time import-time re-bind of `register` at L781.

**Filesystem state tests must also manage** (not in-memory, but equally
shared/isolation-sensitive):
- Guidance markers: `$TMPDIR/cm-hermes-guidance-{session_id}/` (written by
  `_guidance_once` via `O_CREAT|O_EXCL`; cleared by `_reset_guidance`).
- Cross-hook markers: `$TMPDIR/context-mode-{prefix}-{session}[-{suffix}].txt`
  with prefixes `latency`, `rejected`, `injected` (written/read-unlinked by the
  marker helpers).
- Tests should use unique `session_id` values and/or a per-test temp dir, and
  must **mock** `shutil.which`, `subprocess.run`, and the binary path so no real
  `context-mode` binary or Hermes runtime is required.

---

## What passes through vs blocked vs advised (cheat-sheet)

| Bucket | Examples | Outcome |
|---|---|---|
| **Pass-through (bounded)** | `pwd`, `git status`, `mkdir x`, `rm a b`, `ls`, `--version` | `return None` — runs untouched |
| **curl/wget, silent file output** | `curl -s -o /tmp/x https://...` | allow through |
| **curl/wget stdout/verbose/non-silent** | `curl https://...`, `wget -v ...` | **BLOCK** → `ctx_execute`/`ctx_fetch_and_index` |
| **Inline HTTP** | `requests.get(`, `fetch("http`, `urllib.request.urlopen(` | **BLOCK** → `ctx_execute` |
| **Build tools** | `gradle`, `mvn`, `./mvnw`, `cargo build`, `sbt` | **BLOCK** → `ctx_execute(shell, "...|tail -30")` |
| **Everything else (terminal)** | `git log`, `npm test`, `cat big.log` | **ADVISORY** (sets bash marker) → runs; guidance only injected on next first-turn via `ROUTING_BLOCK` |
| **Non-terminal tools** | any `tool_name != "terminal"` | passthrough at `pre_tool_call` |

---

## Open observations (not in scope to fix — read-only audit)

1. **Guidance constants are dead code as wired.** `BASH_GUIDANCE`,
   `READ_GUIDANCE`, `GREP_GUIDANCE`, `EXTERNAL_MCP_GUIDANCE` (L354–377) are
   defined but never referenced by any hook. The advisory path in
   `_pre_tool_call_terminal` (L539–544) only *sets* the `bash` guidance marker
   and returns `None` — it cannot inject context from `pre_tool_call` in Hermes,
   so these constants are currently inert. (Likely a parity gap vs upstream
   hooks that can inject from PreToolUse.)
2. **`_guidance_marker_dir` does not sanitise `session_id`** (L201–202), unlike
   `_marker_path` which does (L235, L239). If a hostile/malformed `session_id`
   contained path separators it could escape the intended dir. Low risk
   (Hermes controls session ids) but an inconsistency.
3. **Probe logic duplication.** `_check_context_mode` (L112–130) re-implements
   the PATH/known-location probe already in `_resolve_context_mode_binary`
   (L101–109) instead of delegating.
4. **`_pre_llm_call` clears/`compact` interception** (L672–679) matches the bare
   words `clear`/`compact` — could false-trigger on a user message that is just
   "clear" or "compact" used in ordinary English.

---

## Verification (read-only)

```
git diff -- context_mode_hermes/__init__.py README.md   →  EMPTY (clean)
git diff -- pyproject.toml                                →  PRE-EXISTING change only
```

The `pyproject.toml` diff (addition of `[project.optional-dependencies] dev =
["pytest>=7.0"]` and `[tool.pytest.ini_options]` at the top of the file, +7
lines) **pre-existed this task** — it is the pytest test-harness scaffolding
added by an earlier setup step and was NOT introduced or modified by this audit.
`context_mode_hermes/__init__.py` and `README.md` are completely untouched. No
source file was edited, written, or deleted by Task 2.
