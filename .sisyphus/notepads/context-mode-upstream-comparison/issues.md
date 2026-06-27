# Issues — Context Mode Upstream Comparison

(No issues yet — populated during execution)
Task 1 completed: .reference/ added to .gitignore, upstream cloned shallowly, SHA recorded.

## Task 8 — Implementation Notes
- `python` not on PATH; use `python3` for py_compile (the venv under rtk has it).
- LSP server `basedpyright` not installed — py_compile + pytest + AST-level import check used as equivalent verification.
- `_trigger_precompact` is NOT wrapped by `@_hook_safe` (it's a plain helper called from within `_pre_llm_call`, which IS wrapped). It has its own internal try/except for fail-open behavior — this mirrors `_trigger_session_start` exactly.
- The `/compact` branch in `_pre_llm_call` also matches `/clear`, `clear`, and `compact` (bare words). The precompact forward fires for all four variants. This is acceptable — building a snapshot on `/clear` is harmless (upstream decides whether to act on it).
Tests passed: 16/16
