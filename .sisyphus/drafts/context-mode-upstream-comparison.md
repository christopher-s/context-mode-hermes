# Draft: Context Mode Upstream Comparison

## Requirements (confirmed)
- User wants upstream repo pulled down from `https://github.com/mksglu/context-mode` into a sub-folder in this project.
- User wants that sub-folder added to `.gitignore`.
- User wants the upstream checkout treated strictly as reference-only: no changes to it, no commits from it, no pushes from it, and no use as anything except reference material.
- User wants Hermes `context-mode` plugin code examined and compared to upstream because upstream is many versions ahead.
- User wants recommendations/enhancements/adjustments for the Hermes plugin code.

## Technical Decisions
- Planning artifact only: Prometheus will not clone, edit `.gitignore`, or modify plugin code directly.
- The execution plan must include safeguards for nested Git repository handling and reference-only analysis.
- Upstream clone will be placed at `.reference/context-mode-upstream/` and never committed.
- The plan should require static inspection only for upstream unless a task explicitly needs command output; avoid installs/build scripts inside upstream.
- Deliverable scope is compare + implement: plan must include safe reference clone, comparison, and concrete Hermes plugin enhancement tasks.

## Research Findings
- Local Hermes plugin structure from explore agent:
  - `context_mode_hermes/__init__.py`: primary hook entry point; contains `pre_tool_call`, `post_tool_call`, `pre_llm_call`, regex command classification, and routing logic.
  - `pyproject.toml`: build/dependency/entry-point configuration.
  - `README.md`: plugin purpose, install/config docs, and routing rules.
- Upstream context-mode research from librarian:
  - Modular MCP server with core server, adapters, memory/indexing, hooks/plugins, and CLI tools.
  - Comparison should focus on `package.json`, `src/core/`, `src/adapters/`, `src/session/`, `hooks/`, `plugins/`, and CLI tooling.
  - Recent direction includes rename from `claude-context-mode` to `context-mode`, multi-platform adapter support, output compression improvements, and robust CLI/session tools.
- Test infrastructure research from explore agent:
  - No `pytest.ini`, `tox.ini`, or test-related config in `pyproject.toml`.
  - No representative tests found (`test_`, `pytest`, `unittest`).
  - No `.github/workflows` or other CI config found.
  - No fixture/mock infrastructure; plugin appears directly hook-based with subprocess/environment interaction.

## Open Questions
- Should the work plan include setting up minimal `pytest` infrastructure and CI for plugin changes, or keep verification to static/manual agent QA only?

## Scope Boundaries
- INCLUDE: clone/reference handling, `.gitignore` update, upstream/local comparison, Hermes plugin enhancement recommendations, plugin change tasks if requested.
- EXCLUDE: modifying upstream checkout, committing upstream checkout, pushing upstream, executing package install/build/test inside upstream unless explicitly justified and sandboxed.
