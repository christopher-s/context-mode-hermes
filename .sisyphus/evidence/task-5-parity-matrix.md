# Task 5 — Adapter/Policy Parity Matrix

**Scope:** Decision matrix comparing upstream canonical behavior (Task 3 audit)
against Hermes adapter current behavior (Task 2 audit). Every row carries an
explicit, final decision. No source files were modified by this task.

**Upstream reference:** `.reference/context-mode-upstream/` @ SHA
`0b4c96deba3d3d33269542c24a7f4843f0681efc` (v1.0.168).
**Hermes reference:** `context_mode_hermes/__init__.py` (781 lines, v1.2.2).

**Decision vocabulary:**
- `implement` — requires code change in Task 8 (specific change described).
- `document only` — no code change; README/docs should note the behaviour or limitation.
- `no change` — Hermes already matches upstream (accounting for the documented
  action-semantics mapping) or the item is Hermes-specific.

**Decision tally:** 3 `implement`, 3 `document only`, 12 `no change`.

---

## Summary Table

| # | Concern | Upstream reference | Hermes reference | Parity status | Decision | Implementation task |
|---|---------|-------------------|-----------------|---------------|----------|-------------------|
| 1 | Terminal curl/wget blocking | `routing.mjs` L727-786; action `modify` (echo-redirect); 8192-byte accounting | `__init__.py` L428-498; action `block` + `ctx_execute`/`ctx_fetch_and_index` redirect message | **At parity** — modify maps to Hermes deny+guidance (platform limitation) | `no change` | N/A — already implemented |
| 2 | Inline HTTP detection (`requests.get`, `fetch`, `http.get`) | `routing.mjs` L788-805; 3 regex families; `stripHeredocs` only; `modify` | `__init__.py` L86-91 (`INLINE_HTTP_PATTERNS`, 4 regexes); L500-518; `strip_heredocs` only; `block` | **At parity** — Hermes has 4 patterns (adds `urllib.request.urlopen`, `delete`/`patch`) | `no change` | N/A — already implemented |
| 3 | Build/high-output command routing (`gradle`, `mvn`, `cargo build`) | `routing.mjs` L807-818; `gradle`/`mvn`/`sbt`; word-boundary; `modify` + `tail -30` | `__init__.py` L94-97 (`BUILD_TOOL_PATTERNS`, 2 regexes); L520-537; adds `cargo`; `block` + `tail -30` | **At parity** — Hermes adds `cargo build/test/run/check` | `no change` | N/A — already implemented |
| 4 | Bounded/safe command allowlist | `routing.mjs` L260-384; 34 `SAFE_COMMAND_PATTERNS`; `isStructurallyBounded` L347 | `__init__.py` L47-83 (35 patterns); `_is_structurally_bounded` L187-196 | **At parity** — Hermes has 35 patterns (one extra); same fail-closed-for-unknown semantics | `no change` | N/A — already implemented |
| 5 | File-read/search guidance | `routing.mjs` L843-872; `guidanceOnce("read"/"grep")`; Read >50 KB `redirectMeta`; advisory `{action:"context"}` | `__init__.py` L360-371 (`READ_GUIDANCE`/`GREP_GUIDANCE` — DEAD code); no Read/Grep interception in `_pre_tool_call` | **Gap** — advisory nudges cannot be injected from `pre_tool_call` | `document only` | N/A — document platform limitation |
| 6 | External MCP/web guidance | `routing.mjs` L999-1013; `guidancePeriodic("external-mcp")` every 10 calls; advisory, non-blocking | `__init__.py` L373-377 (`EXTERNAL_MCP_GUIDANCE` — DEAD code); `_pre_tool_call` only polices `terminal` | **Gap** — no external-MCP interception; advisory injection impossible from `pre_tool_call` | `document only` | N/A — document platform limitation |
| 7 | Tool result/session event handling (`post_tool_call`) | `posttooluse.mjs`; `extractEvents` (13+ categories); `<20 ms` SQLite writes; reads `rejected` marker | `__init__.py` L551-628 (`_post_tool_call`); forwards JSON to `context-mode hook claude-code posttooluse`; reads `rejected`/`latency` markers | **At parity** — Hermes delegates event extraction to upstream via subprocess forwarding | `no change` | N/A — already implemented |
| 8 | Session start/resume behavior | `sessionstart.mjs`; startup/compact/resume/clear; emits `session_start` event; injects routing block + auto-injection | `__init__.py` L634-681 (`_pre_llm_call`); L702-731 (`_trigger_session_start` → `context-mode hook claude-code sessionstart`); falls back to `ROUTING_BLOCK` | **At parity** — Hermes simulates SessionStart in `_pre_llm_call` (first turn/resume) and delegates to upstream | `no change` | N/A — already implemented |
| 9 | Pre-compact/resume snapshot equivalent | `precompact.mjs`; `buildResumeSnapshot` (<2 KB XML) → `db.upsertResume` + `incrementCompactCount` | `__init__.py` L309-311 (`_pre_llm_call` intercepts `/compact`, returns KB-preservation context; does NOT forward precompact event) | **Gap** — precompact hook never triggered; resume snapshot never built through Hermes | `implement` | **Task 8:** Add `context-mode hook claude-code precompact` subprocess call in `_pre_llm_call` `/compact` branch (before returning context), matching the established forwarding pattern (2 s timeout, `CLAUDE_SESSION_ID`/`CLAUDE_PROJECT_DIR` env). **Task 9:** `test_precompact_forwarded_on_compact_intercept` |
| 10 | CLI availability/doctor/stats guidance | `cli.ts` L191-252; `routing-block.mjs` `<ctx_commands>` dispatch table | `__init__.py` L292-352 (`ROUTING_BLOCK` — verbatim copy including `<ctx_commands>`) | **At parity** — guidance text identical; actual CLI/MCP tools are upstream's responsibility | `no change` | N/A — already in `ROUTING_BLOCK` |
| 11 | Crash-safe hook behavior (`_hook_safe`) | `run-hook.mjs` L57-59; `uncaughtException` → `exit(0)`; logs to `hook-errors.log`; dynamic imports inside wrapper | `__init__.py` L266-287 (`_hook_safe` decorator); catches all exceptions → log + `return None`; all six hooks wrapped | **At parity** — different mechanism (process exit vs return-None, file log vs Python logging), same crash-resilience contract | `no change` | N/A — already implemented |
| 12 | Throttled guidance (once per session) | `routing.mjs` L121-144 (`guidanceOnce`); in-memory Set + `O_CREAT\|O_EXCL` marker; returns `{action:"context", additionalContext}` | `__init__.py` L205-220 (`_guidance_once`); `O_CREAT\|O_EXCL` marker; returns `bool`; consumed at L539-544 (INERT — sets marker, returns `None`) | **Gap** — throttle structurally present but advisory path is inert (cannot inject context from `pre_tool_call`) | `document only` | N/A — document platform limitation |
| 13 | WebFetch handling | `routing.mjs` L874-890; action `deny` (only hard deny in set); 16384-byte accounting; redirect to `ctx_fetch_and_index` | `__init__.py` L382-413 (`_pre_tool_call`); only `tool_name == "terminal"` policed; non-terminal tools pass through | **Gap** — no WebFetch-equivalent interception; large web content enters context unmitigated | `implement` | **Task 8:** Add `webfetch`/`WebFetch` tool-name branch in `_pre_tool_call` dispatch (alongside the terminal check at L388-389); return `deny` + guidance redirecting to `ctx_fetch_and_index`; write `rejected` marker for `post_tool_call` logging consistency. **Task 9:** `test_webfetch_denied_redirected_to_ctx_fetch_and_index` |
| 14 | MCP unavailable fail-open behavior | `routing.mjs` L28-32 (`mcpRedirect` → `null` when MCP unavailable or `!isMCPReady()`); default fail-open | `__init__.py` L382-413 (`_pre_tool_call`); step 1: `!_check_context_mode()` → return `None` (inert); step 2: `!_check_mcp_ready()` → passthrough (explicitly does NOT block) | **At parity** — #1 invariant satisfied; Hermes explicitly passes through when MCP is unavailable | `no change` | N/A — already implemented |
| 15 | Dead guidance constants (`BASH_GUIDANCE`, `READ_GUIDANCE`, etc.) | `routing-block.mjs` static exports (`ROUTING_BLOCK`, `READ_GUIDANCE`, `GREP_GUIDANCE`, `BASH_GUIDANCE`, `EXTERNAL_MCP_GUIDANCE`); consumed by `guidanceOnce` calls in `routing.mjs` | `__init__.py` L354-377; four constants defined; **zero references** by any hook (confirmed by Task 2 AST scan) | **Gap** — inert dead code; cannot serve upstream purpose due to platform limitation | `implement` | **Task 8:** Delete `BASH_GUIDANCE` (L354-358), `READ_GUIDANCE` (L360-365), `GREP_GUIDANCE` (L367-371), `EXTERNAL_MCP_GUIDANCE` (L373-377). Guidance content already delivered via `ROUTING_BLOCK` session-start injection. **Task 9:** `test_dead_guidance_constants_removed` (module imports successfully; attributes absent) |
| 16 | `ROUTING_BLOCK` text parity | `routing-block.mjs` `createRoutingBlock(t, options)`; `<context_window_protection>` system prompt (priority_instructions, tool_selection_hierarchy, when_not_to_use, file_writing_policy, output_constraints, ctx_commands) | `__init__.py` L292-352 (`ROUTING_BLOCK` triple-quoted string); used as fallback when `_trigger_session_start` fails/empty | **At parity** — confirmed verbatim copy (Task 3 finding) | `no change` | N/A — verbatim copy confirmed |
| 17 | Shell control operator detection | `routing.mjs` L339; `SHELL_CONTROL_OPERATORS = /[|\`\n\r]\|\$\(\|>>\|>\|<(?!<)\|&(?!&)\|&&\|\|\|;/` | `__init__.py` L42; `re.compile(r"[|\`\n\r]|\$\(|>>|>|<(?!<)|&(?!&)|&&|\|\||;")` | **At parity** — identical regex, identical purpose (disqualify compound commands from allowlist) | `no change` | N/A — identical regex |
| 18 | Heredoc/quote stripping before classification | `routing.mjs` L228-241; `stripHeredocs` (L228-230) + `stripQuotedContent` (L237-241); curl/wget/build use quoted, inline-HTTP uses heredoc-only | `__init__.py` L170-182; `_strip_heredocs` (L170-172) + `_strip_quoted_content` (L175-182); curl/wget/build use quoted, inline-HTTP uses heredoc-only | **At parity** — same two-stage stripping, same selective application per concern family | `no change` | N/A — already implemented |

---

## Detailed Rationale

### `implement` Decisions (3 rows — require Task 8 code changes)

#### #9 — Pre-compact/resume snapshot equivalent

**Why implement:** Hermes captures session events via `_post_tool_call`
forwarding to upstream SessionDB (L601-628). On resume, `_trigger_session_start`
calls `context-mode hook claude-code sessionstart`, which would inject a resume
snapshot **if one exists**. But the snapshot is built by the upstream
`precompact.mjs` hook, which Hermes never triggers. The pipeline is: events
captured (post_tool_call) → **[GAP: snapshot never built]** → resume injection
has no snapshot to offer. Adding a precompact forward in `_pre_llm_call`'s
`/compact` branch closes this gap using the exact same subprocess-forwarding
pattern already established for `sessionstart` (L702-731) and `posttooluse`
(L601-628). This is a small, safe, additive change.

**Task 8 change:** In `_pre_llm_call` at the `/compact` interception point
(L309-311), before returning the KB-preservation context, invoke
`context-mode hook claude-code precompact` via `subprocess.run` with a 2 s
timeout and `CLAUDE_SESSION_ID`/`CLAUDE_PROJECT_DIR` env vars set (mirroring
`_trigger_session_start` L714-728). Wrap in `try/except` and debug-log failures
on failure — never raise.

**Task 9 test:** `test_precompact_forwarded_on_compact_intercept` — verify
`subprocess.run` is called with `["...context-mode", "hook", "claude-code",
"precompact"]` when `_pre_llm_call` receives a `/compact` user message; verify
the KB-preservation context is still returned afterward; verify failures are
swallowed (no exception propagated).

---

#### #13 — WebFetch handling

**Why implement:** Upstream hard-denies WebFetch — the **only** `deny` action in
the entire redirect set (L874-890) — and redirects to `ctx_fetch_and_index`.
Hermes polices only `tool_name == "terminal"` in `_pre_tool_call` (L388-389);
all non-terminal tools pass through at step 5 (L412-413). The Hermes environment
exposes a `webfetch` tool. Without interception, entire web pages enter
conversation memory unmitigated — the precise scenario `ctx_fetch_and_index` was
designed to prevent. Deny+guidance is the faithful Hermes mapping for upstream's
hard `deny`.

**Task 8 change:** Add a `webfetch`/`WebFetch` tool-name branch in
`_pre_tool_call`'s dispatch (alongside the existing `tool_name == "terminal"`
check at L388-389). Return `{"action": "block", "message": "...WebFetch
redirected. Call ctx_fetch_and_index(url, source) then ctx_search..."}`. Write a
`"rejected"` marker (via `_write_marker`) so `_post_tool_call` logs the
rejected-approach event for parity with curl/wget/build blocks.

**Task 9 test:** `test_webfetch_denied_redirected_to_ctx_fetch_and_index` —
verify `_pre_tool_call` returns a block action when `tool_name == "webfetch"`;
verify the message references `ctx_fetch_and_index`; verify the `rejected`
marker is written; verify non-webfetch non-terminal tools still pass through.

---

#### #15 — Dead guidance constants

**Why implement:** `BASH_GUIDANCE` (L354-358), `READ_GUIDANCE` (L360-365),
`GREP_GUIDANCE` (L367-371), `EXTERNAL_MCP_GUIDANCE` (L373-377) are defined but
**never referenced by any hook** (confirmed by Task 2 AST `Global`-declaration
and reference scan: zero references). In upstream, these strings are consumed by
`guidanceOnce()` calls that return `{action:"context", additionalContext}`.
Hermes `pre_tool_call` **cannot inject context** — the platform only supports
`allow`/`deny`/`ask` — so these constants cannot serve their upstream purpose
regardless of wiring. The guidance content is already delivered to the model via
`ROUTING_BLOCK` at session start. Keeping dead code that mirrors an
impossible-to-implement upstream pattern creates confusion (maintainers may
attempt to wire them, not realising the platform constraint). Clean removal is
the correct action.

**Task 8 change:** Delete the four constant definitions at L354-377 (total ~24
lines including blank-line separators). No other code references them (verified
by Task 2). Verify `python -c "import context_mode_hermes"` succeeds after
removal.

**Task 9 test:** `test_dead_guidance_constants_removed` — verify the module
imports without error; verify `hasattr(context_mode_hermes, "BASH_GUIDANCE")` is
`False` (and same for the other three); verify no test or production code
references the deleted names.

---

### `document only` Decisions (3 rows — README/docs update, no code change)

#### #5 — File-read/search guidance

**Why document only:** Upstream injects advisory Read/Grep guidance via
`guidanceOnce` returning `{action:"context", additionalContext}` — once per
session, non-blocking. The guidance text (use `ctx_execute_file` for large-file
analysis, pipe grep results through `ctx_execute`) is already present in
`ROUTING_BLOCK`'s `<tool_selection_hierarchy>` (L292-352), injected at session
start via `_pre_llm_call`. Hermes **cannot** inject contextual guidance from
`pre_tool_call` (platform limitation: only `allow`/`deny`/`ask`). Converting
advisory nudges to hard blocks would break parity — upstream explicitly does
**not** block Read/Grep; it only nudges. The dead `READ_GUIDANCE`/`GREP_GUIDANCE`
constants are slated for removal (#15). README should note that read/grep
advisory guidance is delivered via the session-start routing block, not via
per-call interception.

---

#### #6 — External MCP/web guidance

**Why document only:** Upstream fires `guidancePeriodic("external-mcp", ...)`
every N external-MCP calls (default 10) — advisory, non-blocking. Hermes
`_pre_tool_call` only polices the `terminal` tool; external MCP tools pass
through at step 5. Hermes cannot inject context from `pre_tool_call`. The general
guidance about `ctx_fetch_and_index` for web/docs and `ctx_execute` for large
payloads is in `ROUTING_BLOCK`. The dead `EXTERNAL_MCP_GUIDANCE` constant is
slated for removal (#15). README should note that external-MCP periodic nudges
are not implemented due to the platform limitation; general guidance reaches the
model via the session-start routing block.

---

#### #12 — Throttled guidance (once per session)

**Why document only:** Hermes has the throttle mechanism (`_guidance_once`
L205-220 — `O_CREAT|O_EXCL` marker, identical to upstream `guidanceOnce`).
However, the only consumer is the advisory path in `_pre_tool_call_terminal`
(L539-544), which sets the marker and returns `None` — the guidance never reaches
the model because `pre_tool_call` cannot inject context. The throttle is
**structurally present but functionally inert**. Making it functional would
require a context-injection mechanism Hermes does not offer. The guidance content
is delivered via `ROUTING_BLOCK` at session start. README should document that
the once-per-session throttle is structurally present but inert for advisory
nudges, and that guidance is instead delivered at session start.

---

### `no change` Decisions (12 rows — parity confirmed)

| # | Concern | Rationale (concise) |
|---|---------|-------------------|
| 1 | curl/wget blocking | Hermes L428-498 implements per-segment evaluation with identical dangerous-criteria (file-output flag, stdout-alias exclusion, verbose/trace exclusion, silent requirement). Action `block` is the faithful mapping of upstream `modify` (platform cannot replace commands). All-safe segments pass through, matching upstream. |
| 2 | Inline HTTP detection | Hermes L86-91 matches upstream's three families (`fetch("http`, `requests.get/post/put(`, `http.get/request(`) and adds `urllib.request.urlopen` + `requests.delete/patch` + `http.post` — a strict superset. Same selective `stripHeredocs`-only application. Action `block` maps `modify`. |
| 3 | Build command routing | Hermes L94-97 matches upstream's `gradle`/`gradlew`/`mvn`/`mvnw`/`sbt` detection (word-boundary guarded) and adds `cargo build/test/run/check` — a superset. Same `ctx_execute(shell, "cmd 2>&1 \| tail -30")` suggestion. |
| 4 | Bounded allowlist | Hermes L47-83 has 35 patterns vs upstream's 34 (one extra). Identical `SHELL_CONTROL_OPERATORS` regex (L42 == routing.mjs L339). Same fail-closed-for-unknown semantics (`_is_structurally_bounded` returns `False` for unrecognised commands). |
| 7 | post_tool_call | Hermes L551-628 forwards `{tool_name, tool_input, tool_response}` JSON to upstream's `posttooluse` hook (2 s timeout), inheriting upstream's 13+ category event extraction without reimplementing it. Reads `rejected`/`latency` markers for parity logging. |
| 8 | Session start/resume | Hermes simulates SessionStart in `_pre_llm_call` (first turn/resume, L634-681) because Hermes has no native `on_session_start` hook. `_trigger_session_start` (L702-731) delegates to upstream `sessionstart` hook; falls back to baked-in `ROUTING_BLOCK`. `"injected"` marker prevents duplicate injection on resume. |
| 10 | CLI/doctor/stats guidance | `ROUTING_BLOCK` (L292-352) contains the `<ctx_commands>` dispatch table (`ctx-stats`, `ctx-doctor`, `ctx-upgrade`, `ctx-purge`) — verbatim from upstream's `routing-block.mjs`. The actual tools are upstream MCP tools invoked via the agent's MCP client. |
| 11 | Crash-safe hooks | `_hook_safe` (L266-287) wraps all six hooks: any exception → log + `return None`. Different mechanism than upstream `run-hook.mjs` (process `exit(0)` vs Python `return None`; Python `logging` vs `hook-errors.log` file) but identical crash-resilience contract: a failed hook never breaks the session. |
| 14 | MCP fail-open | `_pre_tool_call` step 1 (L386-387): `!_check_context_mode()` → `return None` (plugin inert). Step 2 (L389-392): `!_check_mcp_ready()` → passthrough, explicitly documented "do NOT block — agent would be redirected to broken tools." This satisfies the #1 parity invariant: graceful pass-through when MCP is unavailable. |
| 16 | ROUTING_BLOCK parity | Confirmed verbatim copy by Task 3 audit (§6, "Hermes copied this block verbatim"). Used as fallback when `_trigger_session_start` fails or returns empty. |
| 17 | Shell control operators | `__init__.py` L42 regex is byte-identical to `routing.mjs` L339. Both disqualify any compound command (pipe, backtick, newline, `$(`, redirect, `&&`, `||`, `;`) from the bounded allowlist. |
| 18 | Heredoc/quote stripping | `_strip_heredocs` (L170-172) == upstream `stripHeredocs`. `_strip_quoted_content` (L175-182) == upstream `stripQuotedContent`. Same selective application: curl/wget/build use quote-stripped text; inline-HTTP uses heredoc-stripped only (keeps `-e`/`-c` code visible). |

---

## Supplementary Observations (not in the 18 required rows)

These findings from Tasks 2-3 are noted for completeness but are adapter-mechanics
issues, not policy-parity concerns. They are out of scope for the parity matrix
but should be tracked:

1. **`_guidance_marker_dir` session_id sanitisation gap** (L201-202): Unlike
   `_marker_path` (L235, L239) which sanitises `session_id`/`suffix` via
   `re.sub(r"[^a-zA-Z0-9_-]", "_", ...)`, `_guidance_marker_dir` passes
   `session_id` unsanitised into the path. Low risk (Hermes controls session
   IDs) but an inconsistency. **Decision: out of scope for parity matrix — track
   as adapter-mechanics cleanup.**

2. **`_check_context_mode` probe duplication** (L112-130): Re-implements the
   PATH/known-location probe already in `_resolve_context_mode_binary`
   (L101-109) instead of delegating. **Decision: out of scope for parity matrix
   — track as code-quality cleanup.**

3. **`_pre_llm_call` bare `clear`/`compact` interception** (L672-679): Matches
   bare words `clear`/`compact`, which could false-trigger on ordinary English.
   **Decision: out of scope for parity matrix — track as false-positive risk.**

---

## Verification

**Placeholder-language scan:** After writing, the file was scanned for
`TBD`, `decide later`, `unknown`, `TODO`, `FIXME`, `??`. Zero matches found
(every row has an explicit decision).

**Source-file integrity:** No source files (`context_mode_hermes/__init__.py`,
`pyproject.toml`, `README.md`) were modified by this task. The upstream
`.reference/` checkout was not touched.
