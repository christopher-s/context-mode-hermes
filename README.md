# Context Mode Plugin for Hermes Agent

Transparently intercepts high-output tool calls in [Hermes Agent](https://github.com/NousResearch/hermes-agent) and redirects them to [Context Mode](https://github.com/mksglu/context-mode) sandboxed execution, achieving **up to 98% context window savings**.

## How it works

Context Mode runs as an MCP server alongside Hermes. This plugin enforces its use through two hooks:

1. **`pre_tool_call`** — Delegates every tool call to the Context Mode binary's `pretooluse` hook via subprocess. The binary contains all routing logic (safe-command allowlist, curl/wget detection, inline HTTP, build tools, WebFetch interception). When the binary returns a deny decision, the plugin blocks the call and tells the model to use `ctx_execute` instead.
2. **`pre_llm_call`** — On the first turn of each session, injects routing rules (tool hierarchy, forbidden actions, output constraints) so the model knows sandbox tools exist and when to use them.

```
Agent runs: terminal(command="curl https://api.example.com/data")
  → Plugin forwards tool call to context-mode hook
  → Binary returns deny + redirect guidance
  → Plugin returns {"action": "block", "message": "Use ctx_execute instead"}
  → Agent sees the redirect, calls ctx_execute
  → Only stdout enters context (98% savings)

Agent runs: terminal(command="git status")
  → Plugin forwards to context-mode hook
  → Binary returns allow (safe command)
  → Plugin passes through — command runs normally
```

The plugin enforces routing so the model uses Context Mode's MCP tools (`ctx_execute`, `ctx_batch_execute`, `ctx_search`, `ctx_fetch_and_index`, etc.) instead of raw Bash for high-output commands. All sandbox execution, pattern matching, and routing decisions live in the Context Mode binary — this plugin is a thin adapter that forwards decisions.

## Installation

```bash
# 1. Install Context Mode globally
npm install -g context-mode

# 2. Install the plugin in Hermes' venv
~/.hermes/hermes-agent/venv/bin/pip install context-mode-hermes

# 3. Ensure context-mode MCP server is configured in ~/.hermes/config.yaml:
# mcp_servers:
#   context-mode:
#     command: context-mode

# 4. Restart Hermes — plugin auto-registers
```

## Configuration

The plugin is enabled by default when Context Mode is found. To disable:

```yaml
# ~/.hermes/config.yaml
plugins:
  disabled:
    - context-mode
```

## What gets intercepted

The Context Mode binary decides what to intercept. The plugin forwards every `terminal` and `webfetch` tool call and returns the binary's decision. Typical interceptions include:

| Pattern | Action | Redirect |
|---------|--------|----------|
| `curl` / `wget` (stdout output) | **Block** | `ctx_execute(language, code)` or `ctx_fetch_and_index(url, source)` |
| Inline HTTP (`requests.get`, `fetch(`, `http.get`) | **Block** | `ctx_execute(language, code)` |
| Build tools (`gradle`, `mvn`, `cargo build`) | **Block** | `ctx_execute(language: "shell", code: "...")` |
| `webfetch` / `WebFetch` | **Block** | `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` |

Short-output commands (git status, mkdir, ls, rm, mv) pass through untouched — they belong to RTK's compression layer instead.

The full routing rules live in the Context Mode binary and update automatically when you upgrade `context-mode` via npm.

## Complementary to RTK

RTK and Context Mode operate at different layers:

- **RTK** rewrites short commands for token compression (`git log --stat` → `rtk git log --stat`). The command still runs through the normal terminal tool.
- **Context Mode** intercepts high-output commands and routes them through a sandbox. The raw output stays out of context.

Both plugins coexist on the `pre_tool_call` hook. RTK handles compression; Context Mode handles avoidance. The first block wins.

## Troubleshooting

| Symptom | Cause | Resolution |
|---------|-------|------------|
| Plugin doesn't intercept anything | Context Mode binary missing from PATH | Run `which context-mode` — if empty, reinstall with `npm install -g context-mode` |
| Blocks bypassed, no redirects | MCP server unresponsive | Check `~/.hermes/config.yaml` has the `context-mode` MCP server entry; restart Hermes |
| Session-start routing rules absent | SessionStart hook failed | Check Hermes logs for `[context-mode]` entries; the session continues without routing rules |
| Plugin registered but silent | Binary found, MCP ready, but only safe commands ran | Expected behavior — only high-output commands trigger blocks |
| Agent retries `webfetch` after block | Model ignored the redirect guidance | The block message says "Do NOT retry with webfetch" — this is a model compliance issue |

**Graceful degradation:** When Context Mode is absent, the plugin disables itself silently. When the MCP server is unresponsive, blocks are bypassed (passthrough) and guidance is suppressed. When any hook crashes, Hermes catches the error and the agent continues.

## Development

```bash
pip install -e .[dev]   # installs pytest
python -m pytest
```

Tests mock the external `context-mode` binary and MCP server, so they run without a real Context Mode installation.

## License

MIT
