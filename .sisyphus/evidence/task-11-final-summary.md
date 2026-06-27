# Task 11 — Repository Hygiene + Final Evidence Bundle

**Scope:** Final verification proving scope fidelity for the
context-mode-upstream comparison deliverable. No source files were modified by
this task; it only runs read-only verification commands and writes this summary.

**Date:** 2026-06-26
**Upstream reference:** `.reference/context-mode-upstream/` @ SHA
`0b4c96deba3d3d33269542c24a7f4843f0681efc` (v1.0.168).
**Hermes plugin:** `context_mode_hermes/__init__.py` (v1.2.2).

---

## 1. Upstream SHA (confirmed)

```
0b4c96deba3d3d33269542c24a7f4843f0681efc
```

Command: `git -C .reference/context-mode-upstream rev-parse HEAD`

Matches the recorded reference SHA in `.sisyphus/evidence/task-1-reference-sha.txt` ✅.

## 2. Upstream status — clean

Evidence file: `.sisyphus/evidence/task-11-upstream-status.txt` (**0 bytes**).

Command: `git -C .reference/context-mode-upstream status --short` → empty output.

**Confirmation:** The upstream checkout is **completely clean** — no modified,
staged, or untracked files. The reference checkout was treated as read-only
throughout the engagement. ✅

## 3. Main repo — git diff --stat (tracked changes)

Command: `git diff --stat` (no staged changes; `git diff --staged --name-only` is empty).

```
 .gitignore                      |  3 ++
 README.md                       | 38 +++++++++++++++++++++++-
 context_mode_hermes/__init__.py | 65 +++++++++++++++++++++++++----------------
 pyproject.toml                  |  7 +++++
 4 files changed, 87 insertions(+), 26 deletions(-)
```

Matches the expected change footprint from the task brief (`.gitignore` +3,
`pyproject.toml` +7, `README.md` +38, `__init__.py` 40 insertions / 25
deletions net of +65/-26 including the dead-constant removal). ✅

## 4. Main repo — git status (full, with ignored)

Evidence file: `.sisyphus/evidence/task-11-main-status.txt` (250 bytes).

Command: `git status --short --ignored`

```
 M .gitignore
 M README.md
 M context_mode_hermes/__init__.py
 M pyproject.toml
?? .github/
?? .sisyphus/
?? tests/
!! .pytest_cache/
!! .reference/
!! .venv/
!! context_mode_hermes.egg-info/
!! context_mode_hermes/__pycache__/
!! tests/__pycache__/
```

**Staged count:** `0` (nothing staged). ✅

**`.reference/` placement check:** `.reference/` appears **only** under the
ignored (`!!`) section. It does **not** appear as modified (`M`), staged, or
untracked (`??`). ✅

## 5. Tracked `.reference/` paths — none

Command: `git ls-files | grep -E '(^|/)\.reference/'` → **NONE_TRACKED**.

Full tracked file set (6 entries):
```
.gitignore
LICENSE
README.md
context_mode_hermes/__init__.py
pyproject.toml
setup.py
```

`.gitignore` line 27 contains the `.reference/` ignore rule, so the directory
was never tracked. ✅

## 6. Test results — 16/16 passed

Evidence file: `.sisyphus/evidence/task-11-pytest.txt` (verbose).

Command: `/usr/bin/pytest -vv`

```
============================= test session starts ==============================
platform linux -- Python 3.14.4, pytest-9.0.2, pluggy-1.6.0
collected 16 items

tests/test_precompact.py::test_compact_triggers_precompact PASSED          [  6%]
tests/test_precompact.py::test_clear_triggers_precompact PASSED            [ 12%]
tests/test_precompact.py::test_non_compact_does_not_trigger_precompact PASSED [ 18%]
tests/test_precompact.py::test_precompact_fails_open PASSED                [ 25%]
tests/test_register.py::test_register_with_all_ready PASSED                [ 31%]
tests/test_register.py::test_register_without_binary PASSED                [ 37%]
tests/test_routing.py::test_curl_blocked PASSED                            [ 43%]
tests/test_routing.py::test_safe_command_passes PASSED                     [ 50%]
tests/test_routing.py::test_binary_unavailable_fails_open PASSED           [ 56%]
tests/test_routing.py::test_mcp_unavailable_passes_through PASSED          [ 62%]
tests/test_smoke.py::test_plugin_smoke PASSED                              [ 68%]
tests/test_smoke.py::test_plugin_initialization_no_binary PASSED           [ 75%]
tests/test_webfetch.py::test_webfetch_denied_and_redirected PASSED         [ 81%]
tests/test_webfetch.py::test_webfetch_case_insensitive PASSED              [ 87%]
tests/test_webfetch.py::test_webfetch_writes_rejected_marker PASSED        [ 93%]
tests/test_webfetch.py::test_non_webfetch_tool_passes_through PASSED       [100%]

============================== 16 passed in 0.03s ==============================
```

**16/16 passed** across 5 test modules (precompact 4, register 2, routing 4,
smoke 2, webfetch 4). ✅

## 7. Compile status — OK

Command: `python3 -m py_compile context_mode_hermes/__init__.py` →
`PY_COMPILE_EXIT=0`.

**Compile status: OK** (no syntax errors). ✅

---

## 8. Scope fidelity — only intended files changed

### 8.1 Modified tracked files (4)

| File | Change | Intent |
|------|--------|--------|
| `.gitignore` | +3 lines | Add `.reference/` + build/cache ignores |
| `pyproject.toml` | +7 lines | Add pytest + CI config (`testpaths`, typeguard) |
| `README.md` | +38 lines | Document reference workflow + adapter limitations |
| `context_mode_hermes/__init__.py` | 40 ins / 25 del | 3 parity implementations (Task 8) |

### 8.2 New untracked files (intended)

| Path | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | GitHub Actions CI (Task 9/10) |
| `tests/__init__.py` | package marker |
| `tests/conftest.py` | shared fixtures + cache reset |
| `tests/test_smoke.py` | 2 smoke tests |
| `tests/test_register.py` | 2 register tests |
| `tests/test_routing.py` | 4 routing tests |
| `tests/test_webfetch.py` | 4 webfetch tests |
| `tests/test_precompact.py` | 4 precompact tests |
| `.sisyphus/evidence/*.txt`, `*.md` | task evidence bundle |

### 8.3 Scope confirmation

No file outside the intended set was modified. No `.reference/` path is staged,
tracked, committed, or registered as a submodule. ✅

---

## 9. Parity changes implemented (Task 5 → Task 8)

The 3 `implement` decisions from `.sisyphus/evidence/task-5-parity-matrix.md`,
all realised in `context_mode_hermes/__init__.py` and covered by tests:

1. **WebFetch deny + redirect (matrix #13).** `_pre_tool_call` now intercepts
   `webfetch`/`WebFetch` (case-insensitive) and returns a deny block that
   redirects to `ctx_fetch_and_index`, writing a `rejected` session marker.
   *Verified by `tests/test_webfetch.py` (4 tests).*

2. **Pre-compact event forwarding (matrix #9).** `_pre_llm_call` now shells out
   to `context-mode hook claude-code precompact` on the `/compact` and `/clear`
   branches, closing the event-capture → snapshot → resume-injection pipeline
   gap. Fails open (subprocess errors never break the compact path).
   *Verified by `tests/test_precompact.py` (4 tests).*

3. **Dead guidance constant removal (matrix #15).** Removed the inert
   `BASH_GUIDANCE` / `READ_GUIDANCE` / `GREP_GUIDANCE` /
   `EXTERNAL_MCP_GUIDANCE` constants — advisory content never reached a code
   path; equivalent guidance is delivered via the `ROUTING_BLOCK`
   session-start injection.

The 3 `document only` rows (advisory read/grep guidance, periodic MCP nudge,
throttled guidance) are explained in `README.md`; the 12 `no change` rows were
already at parity.

---

## 10. Reference guardrails — confirmed

| Guardrail | Status |
|-----------|--------|
| Upstream checkout untouched (clean working tree) | ✅ 0 bytes status |
| Upstream never committed (no commits added to upstream repo) | ✅ clean |
| Upstream never pushed | ✅ N/A — no commits |
| `.reference/` not staged or tracked in main repo | ✅ `NONE_TRACKED` |
| `.reference/` not a git submodule | ✅ no `.gitmodules`; not in `git ls-files` |
| `.reference/` ignored via `.gitignore` line 27 | ✅ `!! .reference/` |
| Upstream SHA recorded and matches | ✅ `0b4c96deba3d3d33269542c24a7f4843f0681efc` |

---

## 11. Evidence file index

| File | Contents |
|------|----------|
| `.sisyphus/evidence/task-11-main-status.txt` | `git status --short --ignored` (main repo) |
| `.sisyphus/evidence/task-11-upstream-status.txt` | `git -C .reference/... status --short` (empty = clean) |
| `.sisyphus/evidence/task-11-pytest.txt` | full verbose pytest output (16 passed) |
| `.sisyphus/evidence/task-1-reference-sha.txt` | recorded upstream SHA |
| `.sisyphus/evidence/task-5-parity-matrix.md` | parity decisions |
| `.sisyphus/evidence/task-2-local-audit.md` | Hermes local audit |
| `.sisyphus/evidence/task-3-upstream-audit.md` | upstream behaviour audit |
| `.sisyphus/evidence/task-10-ci-no-reference.txt` | CI reference-isolation check |

---

## 12. Summary verdict

| Check | Result |
|-------|--------|
| Upstream SHA matches recorded value | ✅ |
| Upstream repo clean | ✅ |
| Main repo shows only intended tracked changes | ✅ |
| Nothing staged | ✅ |
| No `.reference/` paths tracked/staged | ✅ |
| `.reference/` appears only as ignored | ✅ |
| Not a submodule | ✅ |
| Tests pass | ✅ 16/16 |
| py_compile succeeds | ✅ exit 0 |
| 3 parity changes implemented + tested | ✅ |

All scope-fidelity conditions are met. Ready for the orchestrator's final
verification wave.
