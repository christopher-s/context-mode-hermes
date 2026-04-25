# Context Mode Plugin for Hermes Agent

Transparently intercepts high-output tool calls in [Hermes Agent](https://github.com/NousResearch/hermes-agent) and redirects them to [Context Mode](https://github.com/mksglu/context-mode) sandboxed execution, achieving **up to 98% context window savings**.

## How it works

Context Mode runs as an MCP server alongside Hermes. This plugin enforces its use through two hooks:

1. **`pre_tool_call`** — Intercepts `terminal` tool calls that would flood context (curl, wget, inline HTTP, build tools, high-output commands). Blocks the call and tells the model to use `ctx_execute` instead.
2. **`pre_llm_call`** — On the first turn of each session, injects routing rules (tool hierarchy, forbidden actions, output constraints) so the model knows sandbox tools exist and when to use them.

```
Agent runs: terminal(command="curl https://api.example.com/data")
  → Plugin intercepts pre_tool_call hook
  → Returns {"action": "block", "message": "Use ctx_execute instead"}
  → Agent sees the redirect, calls ctx_execute
  → Only stdout enters context (98% savings)

Agent runs: terminal(command="git log --stat")
  → Plugin intercepts, returns guidance (once per session)
  → Agent learns to prefer ctx_execute for high-output commands
```

The plugin does NOT execute the sandbox itself — it enforces routing so the model uses Context Mode's MCP tools (`ctx_execute`, `ctx_batch_execute`, `ctx_search`, `ctx_fetch_and_index`, etc.) instead of raw Bash.

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

| Pattern | Action | Redirect |
|---------|--------|----------|
| `curl` / `wget` | **Block** | `ctx_execute(language, code)` or `ctx_fetch_and_index(url, source)` |
| Inline HTTP (`requests.get`, `fetch(`, `http.get`) | **Block** | `ctx_execute(language, code)` |
| Build tools (`gradle`, `mvn`, `cargo build`) | **Block** | `ctx_execute(language: "shell", code: "...")` |
| High-output Bash (guidance, once per session) | **Advisory** | Nudge toward `ctx_batch_execute` or `ctx_execute` |

Short-output commands (git status, mkdir, ls, rm, mv) pass through untouched — they belong to RTK's compression layer instead.

## Complementary to RTK

RTK and Context Mode operate at different layers:

- **RTK** rewrites short commands for token compression (`git log --stat` → `rtk git log --stat`). The command still runs through the normal terminal tool.
- **Context Mode** intercepts high-output commands and routes them through a sandbox. The raw output never enters context.

Both plugins coexist on the `pre_tool_call` hook. RTK handles compression; Context Mode handles avoidance. The first block wins.

## Graceful degradation

- Context Mode binary not found → plugin disabled silently
- MCP server not ready → blocks bypassed (passthrough), guidance suppressed
- SessionStart injection fails → logged, session continues
- Plugin crashes → Hermes catches the error, agent continues

## Architecture

This follows the same pattern as [rtk-hermes](https://github.com/rtk-ai/rtk): a thin Python plugin using Hermes's `pre_tool_call` and `pre_llm_call` hooks. The actual sandbox execution, FTS5 indexing, and session continuity are handled by Context Mode's MCP server — this plugin just enforces routing.

## License

MIT
