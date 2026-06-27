# Decisions — Context Mode Upstream Comparison

## User Decisions (confirmed)
- Reference folder: `.reference/context-mode-upstream/`
- Deliverable scope: compare + implement (not report-only)
- Test strategy: add pytest + CI (GitHub Actions, Python 3.9-3.13)

## Architecture Decisions
- Hermes plugin is an adapter, NOT a Python rewrite of upstream MCP server.
- Implementation changes go ONLY in `context_mode_hermes/__init__.py`, justified by the parity matrix (Task 5).
- No new runtime dependencies. Pure stdlib only.
- Keep Python `>=3.9` support.

## Safety Decisions
- Upstream checkout is reference-only: no edits, commits, pushes, installs, builds, submodule, or runtime dependency.
- `.reference/` added to `.gitignore` before/after clone; verify `git status --ignored`.
- Shallow clone by default unless full history explicitly needed.
- Record upstream SHA for traceability.

## Test Decisions
- Mock external binary/MCP; tests must pass without `context-mode` binary installed.
- Reset module-global caches between tests for isolation.

## Task 5 — Parity Matrix Final Decisions

**Matrix:** `.sisyphus/evidence/task-5-parity-matrix.md` (18 required concerns, all decided).

### Decision tally: 3 implement, 3 document only, 12 no change

### implement (Task 8 code changes required):
1. **#9 Pre-compact/resume snapshot:** Add `context-mode hook claude-code precompact` subprocess call in `_pre_llm_call` `/compact` branch. Closes the event-capture → snapshot → resume-injection pipeline gap.
2. **#13 WebFetch handling:** Add `webfetch`/`WebFetch` tool-name interception in `_pre_tool_call` dispatch; deny + redirect to `ctx_fetch_and_index`; write `rejected` marker.
3. **#15 Dead guidance constants:** Remove `BASH_GUIDANCE`/`READ_GUIDANCE`/`GREP_GUIDANCE`/`EXTERNAL_MCP_GUIDANCE` (L354-377) — inert dead code; guidance content already in `ROUTING_BLOCK`.

### document only (README/docs, no code change):
- **#5 File-read/search guidance:** Advisory guidance delivered via `ROUTING_BLOCK` session-start injection. Cannot inject from `pre_tool_call` (platform limitation). Converting to hard blocks would break parity.
- **#6 External MCP/web guidance:** Periodic nudge not implementable (platform limitation). General guidance in `ROUTING_BLOCK`.
- **#12 Throttled guidance:** `_guidance_once` structurally present but inert (advisory path returns `None`). Guidance via session-start routing block.

### no change (12 rows — parity confirmed):
- **#1 curl/wget, #2 inline HTTP, #3 build tools:** Already implemented with correct action-semantics mapping (block = modify+guidance). Hermes has superset patterns (adds `urllib`, `cargo`).
- **#4 bounded allowlist:** 35 patterns vs upstream 34; identical `SHELL_CONTROL_OPERATORS`.
- **#7 post_tool_call:** Forwards to upstream `posttooluse` hook — inherits event extraction.
- **#8 session start/resume:** Simulated in `_pre_llm_call`; delegates to upstream `sessionstart`.
- **#10 CLI guidance:** `ROUTING_BLOCK` contains `<ctx_commands>` verbatim.
- **#11 crash-safe hooks:** `_hook_safe` = same contract as `run-hook.mjs` (different mechanism).
- **#14 MCP fail-open:** Explicitly passes through when `!_mcp_ready` — #1 invariant satisfied.
- **#16 ROUTING_BLOCK:** Confirmed verbatim copy.
- **#17 shell control operators:** Byte-identical regex.
- **#18 heredoc/quote stripping:** Same two-stage stripping, same selective application.

### Key platform constraint (informs all decisions):
Hermes `pre_tool_call` can only return `allow`/`deny`/`ask` — no `modify` and no `{action:"context"}`. Upstream `modify`-redirects (curl/wget/inline-HTTP/build) map to Hermes `deny`+guidance. Upstream advisory `{action:"context"}` nudges (bash/read/grep/external-mcp) have no Hermes `pre_tool_call` equivalent — guidance is delivered via `ROUTING_BLOCK` at session start instead.
