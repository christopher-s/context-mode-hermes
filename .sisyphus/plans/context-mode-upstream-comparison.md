# Context Mode Upstream Comparison + Hermes Adapter Parity

## TL;DR
> **Summary**: Safely clone upstream `mksglu/context-mode` into an ignored `.reference/context-mode-upstream/` folder, compare upstream hook/adapter policy against the Hermes Python adapter, then implement focused Hermes plugin parity improvements with automated tests and CI.
> **Deliverables**:
> - `.gitignore` updated to ignore `.reference/`
> - Upstream reference checkout at `.reference/context-mode-upstream/` with recorded commit SHA, never committed or modified
> - Adapter/policy parity matrix documenting upstream → Hermes decisions
> - Hermes plugin enhancements in `context_mode_hermes/__init__.py` only where justified by the matrix
> - Minimal `pytest` coverage and GitHub Actions CI
> - README updates documenting reference-only workflow and new behavior
> **Effort**: Medium
> **Parallel**: YES - 4 waves
> **Critical Path**: Gitignore + safe clone → upstream/local parity matrix → plugin/test implementation → final review

## Context
### Original Request
User requested: pull down `https://github.com/mksglu/context-mode` into a sub-folder in this project, add it to gitignore, use it only as a reference, never change/commit/push from it, then examine local Hermes context-mode code against the upgraded upstream context-mode and determine + implement enhancements/adjustments to Hermes plugin code.

### Interview Summary
- Reference folder: `.reference/context-mode-upstream/`.
- Scope: compare + implement concrete Hermes plugin enhancements, not report-only.
- Test strategy: add minimal `pytest` + CI.
- Strict upstream guardrail: no edits, commits, pushes, package installs, builds, or generated files inside `.reference/context-mode-upstream/`.

### Metis Review (gaps addressed)
- Separate two comparison dimensions:
  - **Adapter mechanics**: Hermes-specific binary discovery, MCP readiness checks, hook registration, marker files, module-global state.
  - **Policy parity**: command classification, routing guidance, hook behavior, session lifecycle semantics compared against upstream TypeScript hooks/adapters.
- Tests must not require a real `context-mode` binary; mock `shutil.which`, `subprocess.run`, environment, temp markers, and module-global caches.
- Confirm `.gitignore` exists and currently lacks `.reference/`; add the ignore before or immediately after clone and verify `git status --ignored` behavior.
- Python support decision: keep existing `requires-python >=3.9` and test 3.9-3.13 unless a separate user decision changes support policy.

## Work Objectives
### Core Objective
Bring the Hermes plugin up to documented, tested adapter/policy parity with current upstream context-mode without vendoring, modifying, or depending on the upstream checkout as runtime code.

### Deliverables
- Ignored reference checkout and safety checks.
- `docs` content embedded in README or a generated parity report tracked in repo (choose README + `.sisyphus/evidence` for evidence; do not create new long-lived docs unless implementation needs it).
- Updated Hermes hook adapter logic when the parity matrix identifies clear upstream-aligned improvements.
- Minimal test suite and CI.

### Definition of Done (verifiable conditions with commands)
- `git status --short` does not show `.reference/context-mode-upstream/` or any nested upstream files.
- `git -C .reference/context-mode-upstream status --short` is empty after analysis.
- `git -C .reference/context-mode-upstream rev-parse HEAD` recorded in implementation evidence and README/parity note.
- `python -m pytest` passes.
- `python -m build` or packaging verification passes if build tooling is added; otherwise `python -m py_compile context_mode_hermes/__init__.py` passes.
- GitHub Actions workflow validates supported Python versions 3.9-3.13.
- README documents reference-only upstream workflow and current routing/test behavior.

### Must Have
- `.reference/` ignored in `.gitignore`.
- No upstream code copied wholesale into Hermes; only compare policy and reimplement small adapter behaviors as needed.
- Tests isolate external binary/MCP behavior via mocks.
- Parity matrix explicitly names upstream files inspected and local file/line targets.

### Must NOT Have
- No commits, pushes, edits, installs, builds, lockfiles, or generated artifacts inside `.reference/context-mode-upstream/`.
- No submodule addition.
- No runtime dependency on the reference checkout path.
- No attempt to port upstream TypeScript MCP server into Python.
- No human-only QA criteria.

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: tests-after + minimal `pytest`; add GitHub Actions CI.
- QA policy: Every task has agent-executed scenarios.
- Evidence: `.sisyphus/evidence/task-{N}-{slug}.{ext}`.

## Execution Strategy
### Parallel Execution Waves
> Target: 5-8 tasks per wave. <3 per wave (except final) = under-splitting.
> Extract shared dependencies as Wave-1 tasks for max parallelism.

Wave 1: Task 1 safe reference setup; Task 2 local adapter audit; Task 3 upstream static policy audit; Task 4 test/CI scaffold design.
Wave 2: Task 5 parity matrix and implementation decisions; Task 6 pytest fixture implementation; Task 7 docs/reference workflow update.
Wave 3: Task 8 Hermes adapter enhancements; Task 9 test coverage for enhancements; Task 10 CI/package verification.
Wave 4: Task 11 repository hygiene and final evidence.

### Dependency Matrix (full, all tasks)
- Task 1 blocks Tasks 3 and 5.
- Task 2 blocks Tasks 5, 6, 8, 9.
- Task 3 blocks Task 5.
- Task 4 blocks Tasks 6 and 10.
- Task 5 blocks Tasks 8 and 9.
- Task 6 blocks Task 9.
- Task 7 can run after Task 1; final content should be reconciled after Task 5.
- Task 8 blocks Task 9 and Task 11.
- Task 9 blocks Task 10 and Task 11.
- Task 10 blocks Task 11.
- Task 11 blocks final verification wave.

### Agent Dispatch Summary (wave → task count → categories)
- Wave 1 → 4 tasks → quick, deep, deep, quick
- Wave 2 → 3 tasks → deep, quick, writing
- Wave 3 → 3 tasks → unspecified-high, quick, quick
- Wave 4 → 1 task → unspecified-high

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [x] 1. Safe Reference Checkout + Ignore Guardrails

  **What to do**: Add `.reference/` to `.gitignore`. Create `.reference/` if needed. Clone `https://github.com/mksglu/context-mode` into `.reference/context-mode-upstream/` using a shallow clone unless full history is specifically needed. Record upstream HEAD SHA via `git -C .reference/context-mode-upstream rev-parse HEAD` into `.sisyphus/evidence/task-1-reference-sha.txt`. Verify main repo does not track or stage the nested repository.
  **Must NOT do**: Do not run `npm install`, `bun install`, `npm run`, `bun run`, `git add .reference`, `git submodule add`, or any commit/push command inside the upstream checkout.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: small repository hygiene task with strict commands.
  - Skills: [`git-master`] - Needed for safe gitignore/nested repo hygiene checks.
  - Omitted: [`frontend-ui-ux`] - No UI work.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 3, 5, 7 | Blocked By: none

  **References**:
  - Pattern: `.gitignore:1-24` - existing ignore file; append `.reference/` under a clear `# Reference-only upstream checkouts` comment.
  - External: `https://github.com/mksglu/context-mode` - upstream reference source.

  **Acceptance Criteria**:
  - [ ] `.gitignore` contains `.reference/`.
  - [ ] `.reference/context-mode-upstream/.git/` exists locally.
  - [ ] `git status --short --ignored` shows `.reference/` only as ignored, never staged/tracked.
  - [ ] `git -C .reference/context-mode-upstream status --short` returns empty.
  - [ ] `.sisyphus/evidence/task-1-reference-sha.txt` contains upstream SHA and clone command used.

  **QA Scenarios**:
  ```
  Scenario: Main repo ignores upstream checkout
    Tool: Bash
    Steps: Run `git status --short --ignored` from repo root.
    Expected: `.reference/` appears only with ignored marker and no `.reference/context-mode-upstream` files are staged/tracked.
    Evidence: .sisyphus/evidence/task-1-git-status.txt

  Scenario: Upstream checkout remains clean
    Tool: Bash
    Steps: Run `git -C .reference/context-mode-upstream status --short`.
    Expected: No output.
    Evidence: .sisyphus/evidence/task-1-upstream-clean.txt
  ```

  **Commit**: YES | Message: `chore(reference): ignore upstream context-mode checkout` | Files: [`.gitignore`, `.sisyphus/evidence/task-1-reference-sha.txt`]

- [x] 2. Local Hermes Adapter Audit

  **What to do**: Inspect `context_mode_hermes/__init__.py`, `pyproject.toml`, and `README.md`. Produce `.sisyphus/evidence/task-2-local-audit.md` with sections for adapter mechanics and policy logic. Include exact local symbols and line ranges for: `SAFE_COMMAND_PATTERNS`, `INLINE_HTTP_PATTERNS`, `BUILD_TOOL_PATTERNS`, `_resolve_context_mode_binary`, `_check_context_mode`, `_check_mcp_ready`, `_is_structurally_bounded`, `_guidance_once`, `_pre_tool_call`, `_pre_tool_call_terminal`, `_post_tool_call`, `_pre_llm_call`, `_trigger_session_start`, and `register`.
  **Must NOT do**: Do not change plugin logic in this task.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: careful code reading and classification.
  - Skills: [] - No special skill needed.
  - Omitted: [`git-master`] - No git mutation.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 5, 6, 8, 9 | Blocked By: none

  **References**:
  - Pattern: `context_mode_hermes/__init__.py:47` - `SAFE_COMMAND_PATTERNS`.
  - Pattern: `context_mode_hermes/__init__.py:86` - `INLINE_HTTP_PATTERNS`.
  - Pattern: `context_mode_hermes/__init__.py:94` - `BUILD_TOOL_PATTERNS`.
  - Pattern: `context_mode_hermes/__init__.py:381` - `_pre_tool_call`.
  - Pattern: `context_mode_hermes/__init__.py:550` - `_post_tool_call`.
  - Pattern: `context_mode_hermes/__init__.py:633` - `_pre_llm_call`.
  - Pattern: `pyproject.toml:11` - Python support `>=3.9`.
  - Pattern: `pyproject.toml:28-29` - Hermes plugin entry point.

  **Acceptance Criteria**:
  - [ ] Audit file exists and distinguishes adapter mechanics from policy logic.
  - [ ] Audit includes every listed symbol with line range and current responsibility.
  - [ ] Audit identifies module-global caches/state that tests must reset.

  **QA Scenarios**:
  ```
  Scenario: Audit covers required symbols
    Tool: Bash
    Steps: Run a script or grep checks for all required symbol names in `.sisyphus/evidence/task-2-local-audit.md`.
    Expected: Every required symbol appears at least once with file/line reference.
    Evidence: .sisyphus/evidence/task-2-audit-coverage.txt

  Scenario: No source mutation during audit
    Tool: Bash
    Steps: Run `git diff -- context_mode_hermes/__init__.py pyproject.toml README.md` immediately after audit.
    Expected: No diff for these files from Task 2.
    Evidence: .sisyphus/evidence/task-2-no-mutation.txt
  ```

  **Commit**: NO | Message: `n/a` | Files: [`.sisyphus/evidence/task-2-local-audit.md`]

- [x] 3. Upstream Static Policy + Adapter Audit

  **What to do**: Read upstream files inside `.reference/context-mode-upstream/` statically. Produce `.sisyphus/evidence/task-3-upstream-audit.md` covering canonical policy behavior from upstream `hooks/`, `plugins/`, `src/adapters/`, `src/core/`, `src/session/`, and CLI/tool docs. Record file paths, line ranges, and behavior descriptions. If exact paths differ, discover them by file search but keep the scope to hook/adapter/policy/session-start behavior.
  **Must NOT do**: Do not install dependencies, run upstream builds/tests, edit upstream files, or copy large upstream code into Hermes.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: multi-module upstream architecture comparison.
  - Skills: [] - Read-only repository analysis.
  - Omitted: [`git-master`] - No upstream git operations beyond read-only status/SHA.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 5 | Blocked By: 1

  **References**:
  - External: `.reference/context-mode-upstream/hooks/` - upstream hook behavior.
  - External: `.reference/context-mode-upstream/plugins/` - plugin integration patterns.
  - External: `.reference/context-mode-upstream/src/adapters/` - adapter parity reference.
  - External: `.reference/context-mode-upstream/src/core/` - MCP tool/routing concepts.
  - External: `.reference/context-mode-upstream/src/session/` - session event semantics.

  **Acceptance Criteria**:
  - [ ] Upstream audit records the exact SHA from Task 1.
  - [ ] Audit includes at least one upstream reference for tool-call blocking, tool-result/session event capture, session-start/resume behavior, pre-compact/resume guidance if present, and CLI/tool hierarchy guidance.
  - [ ] `git -C .reference/context-mode-upstream status --short` remains empty.

  **QA Scenarios**:
  ```
  Scenario: Upstream audit is traceable to commit
    Tool: Bash
    Steps: Compare SHA in `.sisyphus/evidence/task-3-upstream-audit.md` to `git -C .reference/context-mode-upstream rev-parse HEAD`.
    Expected: Values match exactly.
    Evidence: .sisyphus/evidence/task-3-sha-check.txt

  Scenario: Upstream remains reference-only
    Tool: Bash
    Steps: Run `git -C .reference/context-mode-upstream status --short`.
    Expected: No output.
    Evidence: .sisyphus/evidence/task-3-upstream-clean.txt
  ```

  **Commit**: NO | Message: `n/a` | Files: [`.sisyphus/evidence/task-3-upstream-audit.md`]

- [x] 4. Test + CI Scaffold Design

  **What to do**: Design the minimal test infrastructure before implementation. Update `pyproject.toml` to add pytest test configuration and any dev optional dependencies needed. Create `tests/` with fixtures capable of importing `context_mode_hermes`, resetting module-global state, monkeypatching environment/tempfile paths, mocking `shutil.which`, and mocking `subprocess.run`. Create `.github/workflows/ci.yml` with Python 3.9, 3.10, 3.11, 3.12, and 3.13 matrix.
  **Must NOT do**: Do not require a real `context-mode` binary or Hermes runtime for unit tests.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: small Python test scaffold.
  - Skills: [] - Standard pytest/CI work.
  - Omitted: [`git-master`] - No complex git history work.

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 6, 10 | Blocked By: none

  **References**:
  - Pattern: `pyproject.toml:11` - keep Python `>=3.9` unless user later changes support policy.
  - Pattern: `pyproject.toml:28-29` - test entry-point import and `register` availability.
  - Pattern: `context_mode_hermes/__init__.py:101-133` - binary/MCP checks to mock.
  - Pattern: `context_mode_hermes/__init__.py:201-253` - marker/guidance state to isolate.

  **Acceptance Criteria**:
  - [ ] `python -m pytest` runs and passes with at least one smoke test.
  - [ ] CI workflow exists at `.github/workflows/ci.yml` and runs `python -m pytest` across 3.9-3.13.
  - [ ] Tests mock external binary/MCP interactions.

  **QA Scenarios**:
  ```
  Scenario: Local tests do not need context-mode binary
    Tool: Bash
    Steps: Run tests with PATH temporarily set to a minimal value that excludes context-mode while mocks are active.
    Expected: `python -m pytest` passes.
    Evidence: .sisyphus/evidence/task-4-pytest-no-binary.txt

  Scenario: CI config has full Python matrix
    Tool: Bash
    Steps: Parse `.github/workflows/ci.yml` and verify versions `3.9`, `3.10`, `3.11`, `3.12`, `3.13` are present.
    Expected: All versions present.
    Evidence: .sisyphus/evidence/task-4-ci-matrix.txt
  ```

  **Commit**: YES | Message: `test: add hermes plugin pytest and ci scaffold` | Files: [`pyproject.toml`, `tests/**`, `.github/workflows/ci.yml`]

- [x] 5. Adapter/Policy Parity Matrix + Implementation Decisions

  **What to do**: Create `.sisyphus/evidence/task-5-parity-matrix.md` comparing upstream canonical behavior to Hermes current behavior. Required columns: `Concern`, `Upstream reference`, `Hermes reference`, `Parity status`, `Decision`, `Implementation task`. Concerns must include: terminal curl/wget blocking, inline HTTP detection, build/high-output routing, bounded/safe command allowlist, file-read/search guidance, external MCP/web guidance, tool result/session event handling, session start/resume behavior, pre-compact/resume snapshot equivalent, CLI availability/doctor/stats guidance, crash-safe hook behavior, and throttled guidance.
  **Must NOT do**: Do not leave any row without a final decision; each row must be `implement`, `document only`, or `no change` with rationale.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: central decision-complete comparison artifact.
  - Skills: [] - Requires synthesis from evidence.
  - Omitted: [`frontend-ui-ux`] - No UI.

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 8, 9 | Blocked By: 1, 2, 3

  **References**:
  - Evidence: `.sisyphus/evidence/task-2-local-audit.md` - local behavior.
  - Evidence: `.sisyphus/evidence/task-3-upstream-audit.md` - upstream behavior.
  - Oracle guardrail: Hermes is an adapter delegating to upstream binary/MCP server, not a Python MCP rewrite.
  - Metis guardrail: separate adapter mechanics from policy parity.

  **Acceptance Criteria**:
  - [ ] Matrix includes every required concern.
  - [ ] Every row has an explicit decision and rationale.
  - [ ] Rows requiring code changes are mapped to Task 8 and Task 9 test cases.

  **QA Scenarios**:
  ```
  Scenario: Matrix has no undecided rows
    Tool: Bash
    Steps: Search `.sisyphus/evidence/task-5-parity-matrix.md` for placeholder language or blank Decision cells.
    Expected: No matches.
    Evidence: .sisyphus/evidence/task-5-no-tbd.txt

  Scenario: Required concerns all covered
    Tool: Bash
    Steps: Run scripted check for each required concern phrase in the parity matrix.
    Expected: All required concern phrases present.
    Evidence: .sisyphus/evidence/task-5-concern-coverage.txt
  ```

  **Commit**: NO | Message: `n/a` | Files: [`.sisyphus/evidence/task-5-parity-matrix.md`]

- [x] 6. Pytest Fixtures for Hook Isolation

  **What to do**: Implement reusable tests/fixtures for Hermes hook testing. Include a fake plugin context object that records calls to hook registration APIs used by `register(ctx)`. Include helpers to reset module globals/caches, isolate `tempfile.gettempdir()` marker usage where needed, and mock subprocess results for `_check_mcp_ready` and `_trigger_session_start`.
  **Must NOT do**: Do not call real Hermes, real MCP server, real `context-mode`, or upstream checkout.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: bounded test support implementation.
  - Skills: [] - Standard pytest monkeypatch work.
  - Omitted: [`agent-browser`] - No browser.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 9 | Blocked By: 2, 4

  **References**:
  - Pattern: `context_mode_hermes/__init__.py:101-133` - binary and MCP readiness mocks.
  - Pattern: `context_mode_hermes/__init__.py:201-253` - guidance/marker file helpers.
  - Pattern: `context_mode_hermes/__init__.py:736` - `register(ctx)` behavior.

  **Acceptance Criteria**:
  - [ ] Test fixture verifies `register(ctx)` registers expected hook names.
  - [ ] Fixture can simulate context-mode available/unavailable without a binary.
  - [ ] Repeated test runs are order-independent.

  **QA Scenarios**:
  ```
  Scenario: Register smoke test
    Tool: Bash
    Steps: Run `python -m pytest tests -k register -vv`.
    Expected: Fake context records expected hooks and test passes.
    Evidence: .sisyphus/evidence/task-6-register-test.txt

  Scenario: Test isolation repeatability
    Tool: Bash
    Steps: Run `python -m pytest tests -vv` twice in a row.
    Expected: Both runs pass without state leakage.
    Evidence: .sisyphus/evidence/task-6-repeatability.txt
  ```

  **Commit**: YES | Message: `test: isolate hermes hook adapter behavior` | Files: [`tests/**`]

- [x] 7. README Reference Workflow + Behavior Documentation

  **What to do**: Update `README.md` to document the reference-only upstream checkout policy, the adapter-not-reimplementation architecture, supported Python/test workflow, and current routing behavior after Task 5 decisions. Include explicit warning that `.reference/context-mode-upstream/` is ignored and never used at runtime.
  **Must NOT do**: Do not claim Hermes includes upstream MCP server functionality; do not document the reference checkout as an installation requirement.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: documentation update.
  - Skills: [] - No special skill.
  - Omitted: [`git-master`] - No git complexity.

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 11 | Blocked By: 1; reconcile after 5

  **References**:
  - Pattern: `README.md` - existing install/config/routing documentation.
  - Evidence: `.sisyphus/evidence/task-5-parity-matrix.md` - behavior decisions.
  - Pattern: `.gitignore` - `.reference/` ignore policy.

  **Acceptance Criteria**:
  - [ ] README states upstream checkout is reference-only, ignored, and not runtime input.
  - [ ] README states Hermes plugin delegates to context-mode binary/MCP server and does not reimplement upstream server.
  - [ ] README includes `python -m pytest` test command after tests exist.

  **QA Scenarios**:
  ```
  Scenario: README contains reference-only warning
    Tool: Bash
    Steps: Search README for `.reference/context-mode-upstream`, `reference-only`, and `not used at runtime`.
    Expected: All phrases/concepts present.
    Evidence: .sisyphus/evidence/task-7-readme-reference-warning.txt

  Scenario: README test command works
    Tool: Bash
    Steps: Run the test command documented in README exactly as written.
    Expected: Command passes.
    Evidence: .sisyphus/evidence/task-7-readme-test-command.txt
  ```

  **Commit**: YES | Message: `docs: document upstream reference workflow` | Files: [`README.md`]

- [x] 8. Implement Hermes Adapter Parity Enhancements

  **What to do**: Modify `context_mode_hermes/__init__.py` only according to Task 5 rows marked `implement`. Expected change classes may include updated command pattern policy, improved guidance text/tool hierarchy, better bounded-command detection, refined post-tool/session event behavior, improved session start/resume handling, or safer binary/MCP readiness handling. Keep changes small, stdlib-only, crash-safe via existing `_hook_safe`, and compatible with Python 3.9.
  **Must NOT do**: Do not port upstream MCP server, add runtime dependencies, import from `.reference`, or add broad behavior not justified by Task 5.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: central adapter behavior changes require careful implementation.
  - Skills: [] - Python hook implementation.
  - Omitted: [`frontend-ui-ux`] - No UI.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: 9, 11 | Blocked By: 5

  **References**:
  - Evidence: `.sisyphus/evidence/task-5-parity-matrix.md` - authoritative list of allowed code changes.
  - Pattern: `context_mode_hermes/__init__.py:47-99` - command pattern constants.
  - Pattern: `context_mode_hermes/__init__.py:101-133` - binary/MCP availability.
  - Pattern: `context_mode_hermes/__init__.py:381-549` - pre-tool routing.
  - Pattern: `context_mode_hermes/__init__.py:550-632` - post-tool handling.
  - Pattern: `context_mode_hermes/__init__.py:633-735` - pre-LLM/session start handling.

  **Acceptance Criteria**:
  - [ ] Every code change maps to a Task 5 `implement` row.
  - [ ] No imports beyond Python stdlib unless separately justified in Task 5 and reflected in `pyproject.toml`.
  - [ ] `python -m py_compile context_mode_hermes/__init__.py` passes.
  - [ ] Existing crash-safe wrapper behavior remains intact.

  **QA Scenarios**:
  ```
  Scenario: Code changes are traceable
    Tool: Bash
    Steps: Review `git diff -- context_mode_hermes/__init__.py` and cross-check changed functions against Task 5 implement rows.
    Expected: Every changed function is named in Task 5.
    Evidence: .sisyphus/evidence/task-8-traceability.txt

  Scenario: Syntax compatibility
    Tool: Bash
    Steps: Run `python -m py_compile context_mode_hermes/__init__.py`.
    Expected: Command exits 0.
    Evidence: .sisyphus/evidence/task-8-py-compile.txt
  ```

  **Commit**: YES | Message: `feat(adapter): align hermes routing with upstream context-mode` | Files: [`context_mode_hermes/__init__.py`]

- [x] 9. Behavior Tests for Parity Enhancements

  **What to do**: Add tests covering every Task 8 behavior change plus baseline routing behavior. Required test groups: safe bounded commands pass, curl/wget blocks with ctx guidance, inline HTTP blocks, build/high-output command blocks or advises per Task 5, guidance throttles once per session, context-mode unavailable fails open/does not crash, MCP readiness mocked success/failure, `pre_llm_call` injects current routing rules, `post_tool_call` marker/session behavior if changed.
  **Must NOT do**: Do not assert brittle full-message strings unless the exact text is part of acceptance criteria; prefer key phrases and action fields.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: direct pytest coverage once fixtures exist.
  - Skills: [] - Standard tests.
  - Omitted: [`agent-browser`] - No browser.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: 10, 11 | Blocked By: 5, 6, 8

  **References**:
  - Evidence: `.sisyphus/evidence/task-5-parity-matrix.md` - expected behavior.
  - Tests: `tests/**` from Tasks 4 and 6 - fixture patterns.
  - API/Type: `context_mode_hermes/__init__.py` hook functions - private functions may be tested where no public API exists.

  **Acceptance Criteria**:
  - [ ] Each Task 8 code change has at least one test.
  - [ ] Required test groups are present.
  - [ ] `python -m pytest -vv` passes.

  **QA Scenarios**:
  ```
  Scenario: Full unit test suite passes
    Tool: Bash
    Steps: Run `python -m pytest -vv`.
    Expected: All tests pass.
    Evidence: .sisyphus/evidence/task-9-pytest-full.txt

  Scenario: Behavior coverage mapped to parity matrix
    Tool: Bash
    Steps: Produce a mapping of Task 5 implement rows to test names and save it.
    Expected: Every implement row has at least one test name.
    Evidence: .sisyphus/evidence/task-9-coverage-map.md
  ```

  **Commit**: YES | Message: `test(adapter): cover upstream parity routing behavior` | Files: [`tests/**`]

- [x] 10. CI + Packaging Verification

  **What to do**: Ensure `.github/workflows/ci.yml` installs the package/test dependencies and runs pytest on Python 3.9-3.13. Add build verification only if build tooling is available or added intentionally. Validate workflow YAML syntax sufficiently using local parsing or a safe dry-run-compatible checker if available.
  **Must NOT do**: Do not require upstream checkout in CI; do not clone upstream in CI; do not publish packages.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: bounded CI validation.
  - Skills: [] - YAML + Python packaging.
  - Omitted: [`git-master`] - No history operations.

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: 11 | Blocked By: 4, 9

  **References**:
  - Pattern: `.github/workflows/ci.yml` - new CI workflow.
  - Pattern: `pyproject.toml` - dependency/test config.
  - Test: `tests/**` - CI target.

  **Acceptance Criteria**:
  - [ ] CI workflow has no step that references `.reference/`.
  - [ ] CI workflow has Python matrix 3.9-3.13.
  - [ ] Local command equivalent to CI test step passes.

  **QA Scenarios**:
  ```
  Scenario: CI does not depend on reference checkout
    Tool: Bash
    Steps: Search `.github/workflows/ci.yml` for `.reference`, `context-mode-upstream`, `git clone https://github.com/mksglu/context-mode`.
    Expected: No matches.
    Evidence: .sisyphus/evidence/task-10-ci-no-reference.txt

  Scenario: Local CI-equivalent test command passes
    Tool: Bash
    Steps: Run the same install/test commands used by CI locally where safe.
    Expected: Commands pass.
    Evidence: .sisyphus/evidence/task-10-local-ci-equivalent.txt
  ```

  **Commit**: YES | Message: `ci: verify hermes plugin tests` | Files: [`.github/workflows/ci.yml`, `pyproject.toml`]

- [x] 11. Repository Hygiene + Final Evidence Bundle

  **What to do**: Produce final evidence proving scope fidelity. Save `git diff --stat`, `git status --short --ignored`, upstream clean status, pytest output, py_compile output, and a concise implementation summary to `.sisyphus/evidence/task-11-final-summary.md`. Confirm no `.reference/` files are staged or tracked. Confirm no upstream checkout files changed.
  **Must NOT do**: Do not commit/push upstream, do not delete `.reference/context-mode-upstream/` unless user explicitly asks, and do not mark final verification complete before user approval.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: final integrity review across git, tests, docs, and upstream guardrails.
  - Skills: [`git-master`] - Needed for safe status/diff review.
  - Omitted: [`frontend-ui-ux`] - No UI.

  **Parallelization**: Can Parallel: NO | Wave 4 | Blocks: Final Verification Wave | Blocked By: 7, 8, 9, 10

  **References**:
  - Evidence: `.sisyphus/evidence/task-1-reference-sha.txt` - upstream SHA.
  - Evidence: `.sisyphus/evidence/task-5-parity-matrix.md` - decisions.
  - Pattern: `.gitignore` - reference ignore rule.

  **Acceptance Criteria**:
  - [ ] Final summary exists and includes all required command outputs or paths to captured outputs.
  - [ ] Main repo status shows only intended tracked changes.
  - [ ] Upstream repo status is clean.
  - [ ] Tests pass.

  **QA Scenarios**:
  ```
  Scenario: No upstream files staged/tracked
    Tool: Bash
    Steps: Run `git status --short --ignored` and verify `.reference/` only appears as ignored.
    Expected: No tracked/staged `.reference` paths.
    Evidence: .sisyphus/evidence/task-11-main-status.txt

  Scenario: Final test and compile pass
    Tool: Bash
    Steps: Run `python -m py_compile context_mode_hermes/__init__.py && python -m pytest -vv`.
    Expected: Both commands pass.
    Evidence: .sisyphus/evidence/task-11-final-tests.txt
  ```

  **Commit**: YES | Message: `chore: finalize upstream parity evidence` | Files: [`.sisyphus/evidence/**`]

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.
- [x] F1. Plan Compliance Audit — oracle
- [x] F2. Code Quality Review — unspecified-high
- [x] F3. Real Manual QA — unspecified-high
- [x] F4. Scope Fidelity Check — deep

## Commit Strategy
- Use small commits aligned to task boundaries when Sisyphus executes.
- Never stage `.reference/`.
- Before each commit: inspect `git status --short`, `git diff --stat`, and `git diff --cached --stat`.
- Do not push unless the user separately requests it.

## Success Criteria
- Upstream exists locally as ignored reference material only.
- Hermes plugin has explicit, tested parity decisions against upstream adapter/policy behavior.
- Tests and CI exist and do not require upstream checkout or real context-mode binary.
- README accurately documents the adapter architecture, test workflow, and reference-only guardrails.
- Final verification agents approve and user explicitly approves completion.
