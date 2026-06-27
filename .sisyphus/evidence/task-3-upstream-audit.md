# Task 3 — Upstream Static Policy + Adapter Audit

**Scope:** Read-only static audit of the upstream `context-mode` repository at
`.reference/context-mode-upstream/`. No file inside the upstream tree was
modified, executed, installed, or built by this task. All line ranges are exact
(derived from direct file reads in this turn).

**Upstream HEAD SHA:** `0b4c96deba3d3d33269542c24a7f4843f0681efc`
**Upstream package:** `context-mode` v1.0.168 (TypeScript/Node.js, ESM, Elastic-2.0 license)
**Verified clean:** `git -C .reference/context-mode-upstream status --short` → empty
(preserved upstream SHA confirmed via `git rev-parse HEAD`).

---

## 0. Repository Layout (what exists)

The upstream is a multi-adapter MCP plugin. The policy logic lives almost
entirely in **`hooks/`** (runtime hook scripts) and **`src/`** (MCP server + CLI +
session store). There is NO `src/core/`, `src/cli/`, `src/ctx-index/`, or
`src/tools/` subdirectory — those responsibilities are flattened:

- `src/cli.ts` (single 2040-line file) — the CLI binary.
- `src/server.ts` (4969 lines) — the MCP server exposing the 11 `ctx_*` tools.
- `src/session/` — session DB, event extraction, resume snapshot, analytics.
- `src/security.ts` (889 lines) — user deny/allow pattern enforcement.
- `src/store.ts` + `src/store-directory.ts` — FTS5 content store.
- `src/executor.ts` — the sandboxed code executor behind `ctx_execute`.
- `hooks/core/routing.mjs` (1017 lines) — **the canonical policy engine**.
- `hooks/routing-block.mjs` — the system-prompt injection text (single source of truth).
- `hooks/{pretooluse,posttooluse,precompact,sessionstart,stop,userpromptsubmit}.mjs` — Claude Code hook entry points.
- `hooks/run-hook.mjs` — crash-resilient wrapper shared by all hook entries.
- `bin/statusline.mjs` — Claude Code status line.
- `configs/<adapter>/` — per-adapter rules/AGENTS.md/hooks.json/mcp.json.

This audit focuses on the **canonical Claude Code hook path** (the
`hooks/*.mjs` + `hooks/core/*` files), which is the parity reference for the
Hermes adapter. Per-adapter hook variants under `hooks/<adapter>/` re-export or
thinly wrap the same `hooks/core/routing.mjs` engine.

---

## 1. Hook Registration Surface — `hooks/hooks.json` (143 lines)

The canonical Claude Code hook manifest. Six events are wired, all dispatching
to `.mjs` entry scripts:

| Event | Matcher(s) | Entry script |
|---|---|---|
| `PreToolUse` | `Bash`, `WebFetch`, `Read`, `Grep`, `Agent`, `mcp__plugin_context-mode_...__ctx_execute`, `...ctx_execute_file`, `...ctx_batch_execute`, and broad `mcp__` (external MCP) | `pretooluse.mjs` |
| `PostToolUse` | `Bash\|Read\|Write\|Edit\|NotebookEdit\|Glob\|Grep\|TodoWrite\|TaskCreate\|TaskUpdate\|EnterPlanMode\|ExitPlanMode\|Skill\|Agent\|AskUserQuestion\|EnterWorktree\|mcp__` | `posttooluse.mjs` |
| `PreCompact` | `""` (all) | `precompact.mjs` |
| `UserPromptSubmit` | `""` (all) | `userpromptsubmit.mjs` |
| `SessionStart` | `""` (all) | `sessionstart.mjs` |
| `Stop` | `""` (all) | `stop.mjs` |

The broad `mcp__` PreToolUse matcher (L100-106) is what routes **external MCP**
tool calls (slack/notion/jira/etc.) into the periodic-nudge branch (see §6.9).

---

## 2. Crash-Safety Wrapper — `hooks/run-hook.mjs` (≈90 lines)

Every hook entry (`pretooluse/posttooluse/precompact/sessionstart/stop/
userpromptsubmit`) is wrapped as `await runHook(async () => { ... })` — see
e.g. `pretooluse.mjs:23`, `posttooluse.mjs:15`, `precompact.mjs:14`.

Canonical behavior (`hooks/run-hook.mjs`):
- **L57-59:** installs `process.on("uncaughtException", …)` that logs the error
  and calls `process.exit(0)` — a hook must NEVER surface a non-zero exit, or
  Claude Code treats every tool call as a "non-blocking hook error".
- **L41-50 (`logError`):** appends `[<ISO ts>] pid=<pid> <stack>` to
  `<configDir>/context-mode/hook-errors.log`, where `configDir` honors
  `$CLAUDE_CONFIG_DIR` (with `~` expansion) and falls back to `~/.claude`.
- **L31-39 (`resolveClaudeConfigDir`):** mirrors the config-dir contract used by
  `session-helpers.mjs`.
- All module loads happen **dynamically inside the wrapper** so a missing or
  poisoned dependency cannot hard-fail the hook at parse time (the documented
  rationale in `pretooluse.mjs:11-19`).

**Hermes parity analogue:** `context_mode_hermes/__init__.py::_hook_safe`
(L266-287) — same intent (crash → log → return None), but Hermes logs to Python
`logging` + stderr, not a `hook-errors.log` file.

---

## 3. Tool-Call Blocking — `hooks/core/routing.mjs::routePreToolUse` (L670-1017)

This is the single canonical routing decision function. Signature
(`routing.mjs:670`):

```
routePreToolUse(toolName, toolInput, projectDir, platform, sessionId, options={})
```

It normalizes the tool name via `TOOL_ALIASES` (L700) and dispatches per
canonical tool. `pretooluse.mjs` reads stdin, calls this, and formats the
returned `{action, reason|updatedInput|additionalContext, redirectMeta}` via
`hooks/core/formatters.mjs`. `mcpRedirect()` (L28-32) short-circuits any
redirect to `null` when MCP tools are unavailable or `isMCPReady()` is false
— **so all blocking gracefully degrades to pass-through if the context-mode MCP
server is not live.** This is the single most important parity invariant.

### 3.1 Fail-closed gate (opt-in) — L673-688
`CONTEXT_MODE_REQUIRE_SECURITY=1` + `securityInitFailed` → `{action:"deny"}` for
**every** tool (universal, not just Bash). Default is fail-OPEN (stderr warning,
routing continues).

### 3.2 Bash / Terminal — Stage 1 (security), then Stage 2 (routing) — L704-841

**Stage 1 — user policy enforcement (L707-723):** when `src/security.ts` has
loaded and `readBashPolicies(projectDir, platformSettingsPath)` returns patterns,
`evaluateCommand(command, policies)` decides `deny`/`ask`/`allow`. Only an
explicit matched pattern acts; `ask` with no pattern falls through.

**Stage 2 — context-mode routing (canonical blocklist/redirect):**

1. **curl/wget blocking (L727-786).** `stripQuotedContent` first (L729) to avoid
   false positives like `gh issue edit --body "text with curl in it"` (Issue #63).
   Detection regex (L733): `/(^|\s|&&|\||\;)(curl|wget)\s/i`. The command is
   **split on chain operators** (`&&`, `||`, `;`) and each curl/wget segment is
   evaluated independently (L735-765). A segment is "dangerous" unless ALL hold:
   - has file-output flag (`-o`/`--output`/`-O`/`--output-document` or `>`/`>>`),
   - not the stdout aliases (`-o -`, `-o /dev/stdout`, `-O -`),
   - no verbose/trace flag (`-v`/`--verbose`/`--trace`/`-D -`),
   - is silent (`-s`/`--silent` for curl, `-q`/`--quiet` for wget).
   On any dangerous segment → `mcpRedirect({action:"modify",
   updatedInput:{command: echo "...redirected. Call ctx_execute..."},
   redirectMeta:{tool:"Bash", type:"bash-redirected", bytesAvoided:8192,
   commandSummary}})`. **Action is `modify` (not `deny`)** — it replaces the
   command with an `echo` guidance string. All-safe → `null` (allow).

2. **Inline HTTP detection (L788-805).** Uses `stripHeredocs` only (NOT full quote
   stripping) so code passed via `-e`/`-c` stays visible while heredoc bodies are
   removed. Matches (L794-797):
   - `/fetch\s*\(\s*['"](https?:\/\/|http)/i`
   - `/requests\.(get|post|put)\s*\(/i`
   - `/http\.(get|request)\s*\(/i`
   On match → `mcpRedirect({action:"modify", updatedInput:{command: echo
   "...Inline HTTP redirected. Call ctx_execute..."}})`. No `redirectMeta`
   (no byte accounting on this branch).

3. **Build tools (L807-818).** Detection regex (L810):
   `/(^|\s|&&|\||\;)(\.\/gradlew|gradlew|gradle|\.\/mvnw|mvnw|mvn|\.\/sbt|sbt)(\s|$)/i`
   — word-boundary guard prevents matching `gradle-wrapper-config`/`mvnDocker`.
   On match → `mcpRedirect({action:"modify", updatedInput:{command: echo
   "...Build tool redirected. Call ctx_execute(language:'shell',
   code:'<cmd> 2>&1 | tail -30')..."}})`. The original command is shell-escaped
   and embedded in the suggested `ctx_execute` call (L811).

4. **Structurally-bounded allowlist skip (L820-826).** `isStructurallyBounded`
   returns true → `null` (no nudge). See §4.

5. **Size threshold (opt-in, L828-837).** `CONTEXT_MODE_BASH_NUDGE_MIN_COMMAND_BYTES`
   (default 0 = off). When >0 and `Buffer.byteLength(command) < min` → `null`
   (small commands pass untouched; reserving the nudge for flood-prone ones).

6. **Catch-all bash nudge — once per session (L839-840).** Everything else →
   `guidanceOnce("bash", bashGuidance, sessionId)` (see §5 throttle). This is the
   only place an *advisory* (not a hard redirect) is injected for Bash.

### 3.3 Read — large-file redirect + once-per-session nudge (L843-867)
If the file is a real file and `st.size > 50_000` bytes →
`guidanceOnce("read", readGuidance, sessionId)` decorated with
`redirectMeta:{tool:"Read", type:"read-redirected", bytesAvoided: st.size,
commandSummary: filePath}` (so PostToolUse can emit a `read-redirected` event
with the actual byte count). Otherwise (small/missing file) → plain
`guidanceOnce("read", readGuidance, sessionId)`.

### 3.4 Grep — once-per-session nudge (L869-872)
`guidanceOnce("grep", grepGuidance, sessionId)`.

### 3.5 WebFetch — hard deny + redirect (L874-890)
`{action:"deny", reason:"...WebFetch redirected. Call ctx_fetch_and_index(url,
source) then ctx_search... or ctx_execute...", redirectMeta:{tool:"WebFetch",
type:"webfetch-redirected", bytesAvoided:16384, commandSummary:url}}`. This is a
**`deny`** (unlike curl/wget/build which `modify`).

### 3.6 Agent (subagents) — routing injection (L892-916)
Prepends a routing block to the subagent's prompt. Claude Code defers `ctx_*`
schemas, so for `platform === "claude-code"` a `ToolSearch(query:"select:…")`
bootstrap is prepended (`toolSearchBootstrap: true`). The subagent block omits
the ctx-commands section (subagents can't call stats/doctor/upgrade/purge, #233).
If `subagentType === "Bash"` it is rewritten to `general-purpose`.

### 3.7 ctx_execute — security + cwd pin (L918-943)
Matches bare `execute`, generic MCP, and legacy names
(`matchesContextModeTool(toolName,"ctx_execute","execute")`). When
`toolInput.language === "shell"`: runs `evaluateCommand(code, policies)` and
denies/asks on a deny match. Also pins `cwd: projectDir` for claude-code when
unset.

### 3.8 ctx_execute_file — file-path + code deny (L945-973)
Checks the `path` against Read deny globs (`readToolDenyPatterns("Read",…)` +
`evaluateFilePath`), and the `code` (when `language === "shell"`) against Bash
deny patterns.

### 3.9 ctx_batch_execute — per-command security (L975-997)
Iterates `toolInput.commands[]`, running `evaluateCommand(entry.command, …)` on
each; denies on the first match (naming the offending label/command). Also pins
cwd for claude-code.

### 3.10 External MCP tools — periodic nudge, NOT deny (L999-1013)
Fires for any tool matched by the broad `mcp__` PreToolUse matcher that is not a
context-mode tool (`isExternalMcpTool`, L592). Returns
`guidancePeriodic("external-mcp", externalMcpGuidance, sessionId,
getExternalMcpNudgeEvery())` — i.e. re-fires every N calls (default 10). It
**does not deny or modify** the call.

### 3.11 Unknown tool → `null` (L1015-1016). Pass-through.

---

## 4. Safe/Bounded Command Allowlist — `hooks/core/routing.mjs` (L228-384)

### 4.1 Quote/heredoc stripping (L228-241)
- `stripHeredocs` (L228-230): removes `<<-? "WORD"…\nWORD` heredoc bodies.
- `stripQuotedContent` (L237-241): `stripHeredocs` + collapses single- and
  double-quoted strings to `''`/`""` so regex only sees command tokens.

### 4.2 `SAFE_COMMAND_PATTERNS` — 34 entries (L260-346)
The documented allowlist of structurally-bounded commands (#463). Categories
include: system probes (`pwd`, `whoami`, `hostname`, `uname`, `id`, `date`,
`echo`, `printf`, `which`, `type`, `command -v`, `readlink`, `basename`,
`dirname`, `realpath`), and conservative git-read / version-probe patterns.
**34 regex entries** between L260 and L346 (counted in this turn).

### 4.3 `SHELL_CONTROL_OPERATORS` (L339)
```
const SHELL_CONTROL_OPERATORS = /[|`\n\r]|\$\(|>>|>|<(?!<)|&(?!&)|&&|\|\|;/;
```
Any pipe, backtick, newline, CR, command-substitution `$(`, redirect `>`/`>>`,
stdin `<`, single `&`, `&&`, `||`, or `;` **disqualifies** a command from the
bounded set — fail-safe (unknown/compound commands stay unbounded).

### 4.4 `isStructurallyBounded(command)` (L347-384)
Returns true ONLY when (1) no shell-control-operator is present AND (2) the
command matches a `SAFE_COMMAND_PATTERNS` entry. Used at `routePreToolUse` L824
to **skip the routing nudge** for bounded commands (the nudge is pure noise on
`pwd`/`git status`/`--version` probes — ~85 wasted tokens).

**Hermes parity note:** Hermes has the structural mirror
(`SAFE_COMMAND_PATTERNS` L47-83, `SHELL_CONTROL_OPERATORS` L42,
`_strip_heredocs` L170, `_strip_quoted_content` L175, `_is_structurally_bounded`
L187-196) but its `_pre_tool_call_terminal` advisory path is inert (cannot inject
context in a `pre_tool_call` hook) — Task 2 finding #1.

---

## 5. Guidance Throttling — `hooks/core/routing.mjs` (L36-228)

### 5.1 `guidanceOnce(type, content, sessionId)` (L121-144) — once-per-session
- **Fast path:** in-memory `_guidanceShown` Set (L51) for same-process callers.
- **Cross-process:** marker directory
  `$TMPDIR/context-mode-guidance-{s-<sessionId>|-<ppid>}/` (L116-119) via
  `guidanceDirFor`. Marker created with `O_CREAT | O_EXCL | O_WRONLY` (L134) —
  atomic create-or-fail; first writer wins, others get EEXIST → return `null`.
- Session-id resolution order (L42-50): caller-supplied `sessionId` →
  `process.ppid` fallback (unreliable on Windows/Git Bash, #298).
- On first fire: adds to Set, returns
  `{action:"context", additionalContext: content}`.

### 5.2 `guidancePeriodic(type, content, sessionId, period)` (L161+) — every N calls
Re-fires on calls 1, period+1, 2·period+1, … Counter is process-aware
(in-memory `_guidanceCounters` Map L57) **and file-backed**
(`<guidanceDir>/<type>.count`). On any IO/parse failure it **falls back to
firing** — losing a counter beats silently dropping the advisory.

### 5.3 Tunables
- `getExternalMcpNudgeEvery()` (L69-77): `CONTEXT_MODE_EXTERNAL_MCP_NUDGE_EVERY`,
  default 10, clamped to [1,100]; invalid → default.
- `getBashNudgeMinCommandBytes()` (L100+): `CONTEXT_MODE_BASH_NUDGE_MIN_COMMAND_BYTES`,
  default 0 (off).
- `resetGuidanceThrottle(sessionId)` (L214, exported) — clears markers (used at
  session boundaries).

---

## 6. Routing-Block / System-Prompt Injection — `hooks/routing-block.mjs` (≈8 KB)

**Single source of truth** for the injected guidance text, imported by both
`pretooluse.mjs` (via `createRoutingBlock` through `routing.mjs`) and
`sessionstart.mjs` (L25, L49). Factory:

```
createRoutingBlock(t, options={})   // t = platform tool-namer; options.includeCommands, options.toolSearchBootstrap
```

The produced `<context_window_protection>` XML block contains:
- `<priority_instructions>` — "Every byte a tool returns enters your
  conversation memory… Think-in-Code" (L19-22).
- `<deferred_tool_bootstrap>` (only when `toolSearchBootstrap`) — instructs a
  one-time `ToolSearch(query:"select:ctx_batch_execute,ctx_search,…")` before the
  first ctx_* call (L23-29).
- `<tool_selection_hierarchy>` — the canonical **tool hierarchy** (L30+):
  - **0. MEMORY:** `ctx_search(sort:"timeline")` — prior decisions/errors/plans.
  - **1. GATHER:** `ctx_batch_execute(commands, queries)` — primary research tool.
  - **2. FOLLOW-UP:** `ctx_search(queries:[...])`.
  - **3. PROCESSING:** `ctx_execute(language,code) | ctx_execute_file(path,…)`.
- `<when_not_to_use>`, `<ctx_commands>` (the `ctx stats`/`ctx doctor`/… slash
  commands), `<file_writing_policy>` (Write/Edit only — sandbox tools discard FS),
  `<output_constraints>`.

Static backward-compat exports (`ROUTING_BLOCK`, `READ_GUIDANCE`, `GREP_GUIDANCE`,
`BASH_GUIDANCE`, `EXTERNAL_MCP_GUIDANCE`) default to claude-code naming
(routing.mjs L694-697 uses the platform factory when a platform is passed, else
the static constants).

**Hermes parity:** Hermes copied this block **verbatim** into
`ROUTING_BLOCK` (`context_mode_hermes/__init__.py` L292-352), used as the fallback
when `_trigger_session_start` fails/empty. Confirmed identical text.

---

## 7. Session Lifecycle — `hooks/sessionstart.mjs`, `hooks/precompact.mjs`, `hooks/posttooluse.mjs`

### 7.1 SessionStart — `hooks/sessionstart.mjs` (≈330 lines)
Documented lifecycle modes (header L9-16):
- **startup** → fresh session; inject previous-session knowledge; cleanup old data.
- **compact** → auto-compact; inject resume snapshot + stats.
- **resume** → `--continue`/`--resume`/`/resume`; CC sends the ACTIVE session_id
  (often a *fresh* id for `/resume`, so live events miss → fall back to snapshot, #413).
- **clear** → user cleared context; no resume.

Behavior: detects platform (`detectPlatformFromEnv`), builds the routing block
(`createRoutingBlock`, L49), loads SessionDB, emits a `session_start` **canonical
event** at each lifecycle boundary (L55+), builds the session directive via
`hooks/session-directive.mjs::buildSessionDirective`, and applies
`auto-injection.mjs::buildAutoInjection` (P1 role → P2 decisions → P3 skills →
P4 intent, hard-capped at ~500 tokens / ~2000 chars).

### 7.2 PreCompact — `hooks/precompact.mjs` (≈110 lines)
Triggered before Claude Code compacts. Reads all captured session events from
SessionDB, calls `src/session/snapshot.ts::buildResumeSnapshot(events,
{compactCount})` to produce a **priority-sorted resume snapshot (<2KB XML)**,
stores it via `db.upsertResume(sessionId, snapshot, events.length)`, and
`db.incrementCompactCount(sessionId)`. Also writes a `compaction`-category event
(L56-72) so the dashboard's compact widget gets per-compaction rows. Debug log at
`<configDir>/context-mode/precompact-debug.log`.

### 7.3 PostToolUse — `hooks/posttooluse.mjs` (≈200 lines)
**Tool-result / session-event capture.** Reads stdin, ensures the session row
exists (`db.ensureSession`), then `extractEvents({tool_name, tool_input,
tool_response, tool_output})` (from `src/session/extract.ts`) produces events
across **13+ categories** (file, decision, error, skill, role, intent, prompt,
rejected-approach, …). These are attributed to the project
(`resolveProjectAttributions`) and inserted. Target latency: **<20ms**, no
network, no LLM — pure SQLite writes (header L1-11).

**Rejected-approach capture (L62+):** reads a PreToolUse marker
`$TMPDIR/context-mode-rejected-<sessionId>.txt` (written when routePreToolUse
denies), unlinks it, and records the rejected approach as a session event
(Category 18).

### 7.4 Session directive — `hooks/session-directive.mjs` (≈400 lines)
`groupEvents`, `writeSessionEventsFile`, `buildSessionDirective`,
`getSessionEvents`. Notable: **leg-boundary** logic (`computeLegBoundary`
L16-22) — the session_id persists across `--continue` legs, so rows written in a
prior leg are partitioned by the last `session_start` event timestamp.
**Data-reference sizing (#840):** `DATA_REF_INLINE_MAX=8` recent captures inline,
`DATA_REF_ENTRY_MAX=150` chars/entry; older/larger blobs are referenced by a
one-line pointer and stay queryable via `ctx_search(source:"session-events")`.

---

## 8. CLI Tool Surface — `src/cli.ts` (2040 lines) + `package.json`

The CLI binary is `context-mode` (`package.json` `"bin": {"context-mode":
"./cli.bundle.mjs"}`). Dispatch is a hand-rolled `args[0]` switch
(`src/cli.ts:191-252`, `printHelp` L193-224):

| Command | Behavior |
|---|---|
| `context-mode` (no args) | Start MCP server over stdio |
| `context-mode index <path>` | Index a file/dir into the FTS5 knowledge base (opts: `--source`, `--project`, `--max-depth`, `--max-files`, `--ext`, `--include`, `--exclude`, `--no-gitignore`, `--follow-symlinks`) |
| `context-mode search <query...>` | Search the project's FTS5 KB (opts: `--project`, `--source`, `--limit`, `--type code\|prose`) |
| `context-mode doctor` | Diagnose runtime issues, hooks, FTS5, version |
| `context-mode upgrade` | Fix hooks, permissions, and settings |
| `context-mode hook <platform> <event>` | Dispatch a configured hook script |
| `context-mode statusline` | Print Claude Code status line (`bin/statusline.mjs`) |
| `context-mode insight` | Launch the Insight dashboard (L252) |

**IMPORTANT parity distinction:** `stats`, `purge`, `execute`, `execute_file`,
`batch_execute`, `fetch_and_index`, `insight` are **NOT** CLI subcommands — they
are **MCP server tools only**, exposed via stdio by `src/server.ts`. The Hermes
`ctx stats`/`ctx doctor`/`ctx purge`/`ctx upgrade` slash commands (documented in
`ROUTING_BLOCK`'s `<ctx_commands>`) invoke these MCP tools through the agent's
MCP client, not the CLI binary.

**Environment override:** `CONTEXT_MODE_DIR=/absolute/path` overrides the
sessions/content storage root (empty ignored, non-empty must be absolute).

---

## 9. Canonical MCP Tool Set — `src/server.ts` (4969 lines)

Eleven tools registered (string-literal scan of server.ts in this turn):

`ctx_batch_execute`, `ctx_doctor`, `ctx_execute`, `ctx_execute_file`,
`ctx_fetch_and_index`, `ctx_index`, `ctx_insight`, `ctx_purge`, `ctx_search`,
`ctx_stats`, `ctx_upgrade`.

This is the canonical tool surface the Hermes adapter routes into. Tool
descriptions follow the ADR `docs/adr/0002-tool-description-style.md`.

---

## 10. Adapters — `src/adapters/` (parity reference)

`src/adapters/` holds per-agent installers/detectors (claude-code, codex,
gemini-cli, cursor, copilot-cli, jetbrains-copilot, kimi, kiro, opencode,
openclaw, omp, antigravity, antigravity-cli, vscode-copilot). Each adapter writes
the appropriate `configs/<adapter>/{hooks.json,mcp.json,AGENTS.md|CLAUDE.md|...}`
and `hooks/<adapter>/*.mjs` variants that wrap the shared `hooks/core/routing.mjs`
engine. `src/adapters/detect.ts` (29 KB) performs agent auto-detection. These are
**install-time mechanics** — the runtime policy is identical across adapters
because they all call `routePreToolUse` with their platform's tool-namer.

**Hermes is a hook ADAPTER on this model:** it does not reimplement the MCP
server; it intercepts Hermes tool calls and enforces routing into the upstream
`ctx_*` tools. The parity target is therefore §3 (blocking/redirect logic) and §6
(routing-block text), not the adapter installers.

---

## 11. Summary — Canonical Policy vs. the 10 Audit Questions

| # | Question | Canonical answer (file:lines) |
|---|---|---|
| 1 | Bash tool-call blocking | routing.mjs L704-841: Stage1 security deny/ask; Stage2 curl/wget `modify`-redirect (L733-786, 8192-byte accounting), inline-HTTP `modify` (L794-805), build-tools `modify` (L810-818), bounded-skip (L824), size-threshold (L834), once-per-session bash nudge (L840). |
| 2 | Inline HTTP patterns | routing.mjs L788-805: `fetch("http`, `requests.get/post/put(`, `http.get/request(` (heredoc-stripped only). Redirect → ctx_execute. |
| 3 | Build tools | routing.mjs L807-818: `gradle/gradlew`, `mvn/mvnw`, `sbt` (word-boundary). Redirect → ctx_execute `2>&1 \| tail -30`. |
| 4 | Safe/bounded allowlist | routing.mjs L260-384: 34 `SAFE_COMMAND_PATTERNS` + `SHELL_CONTROL_OPERATORS` (L339) + `isStructurallyBounded` (L347). |
| 5 | Routing-rule / guidance injection | routing-block.mjs `createRoutingBlock` (the `<context_window_protection>` system prompt); injected via guidanceOnce (pre-LLM context) in routePreToolUse and via sessionstart.mjs L49. |
| 6 | Session start/resume | sessionstart.mjs: startup/compact/resume/clear modes; emits `session_start` event; injects routing block + resume snapshot + auto-injection. |
| 7 | Pre-compact / resume snapshot | precompact.mjs: `buildResumeSnapshot` (<2KB XML) → `db.upsertResume` + `incrementCompactCount` + compaction event. snapshot.ts (18 KB). |
| 8 | CLI tools exposed | cli.ts L191-252: `context-mode` (MCP stdio), `index`, `search`, `doctor`, `upgrade`, `hook <platform> <event>`, `statusline`, `insight`. stats/purge/etc. are MCP tools, not CLI. |
| 9 | Crash-safety in hooks | run-hook.mjs: `uncaughtException`→`exit(0)`, hook-errors.log, dynamic imports inside wrapper; never non-zero exit. All 6 entry hooks wrapped. |
| 10 | Throttling of guidance | guidanceOnce (once/session, O_EXCL markers, L121-144); guidancePeriodic (every N, file-backed counter, L161+); external-MCP cadence default 10 via `CONTEXT_MODE_EXTERNAL_MCP_NUDGE_EVERY` [1,100] (L64-77). |

---

## 12. Key Parity Invariants for the Hermes Adapter (carry into Task 5)

1. **Graceful degradation:** all redirects go through `mcpRedirect()` which
   returns `null` when MCP tools are unavailable / `isMCPReady()` is false.
   Hermes must likewise pass-through (not block) when the upstream binary/MCP is
   absent.
2. **Action semantics:** curl/wget/inline-HTTP/build use `modify` (replace
   command with an `echo` guidance); WebFetch uses `deny`; bounded/unknown uses
   `null`. Hermes `_pre_tool_call` can only return allow/deny/ask — it cannot
   `modify`, so the upstream `modify`-redirects map to Hermes deny+guidance.
3. **Once-per-session throttle** on bash/read/grep/external-mcp nudges via marker
   files — Hermes has `_guidance_once` (L205-220) parity but its pre_tool_call
   path is inert (Task 2 finding #1).
4. **Verbatim routing block** already copied (Hermes L292-352 == routing-block.mjs).
5. **Fail-closed is opt-in** (`CONTEXT_MODE_REQUIRE_SECURITY=1`); default is
   fail-open with a stderr warning.

---

**Verification performed this task:**
- `git -C .reference/context-mode-upstream status --short` → empty (no modifications).
- `git -C .reference/context-mode-upstream rev-parse HEAD` →
  `0b4c96deba3d3d33269542c24a7f4843f0681efc` (matches required SHA).
- No `npm install` / `bun install` / build / test run inside upstream.
- All analysis was read-only (Read + in-sandbox static text processing).
