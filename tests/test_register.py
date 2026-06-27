import pytest
import context_mode_hermes

EXPECTED_HOOKS = [
    "pre_tool_call",
    "post_tool_call",
    "pre_llm_call",
    "on_session_end",
    "on_session_reset",
]

def test_register_with_all_ready(fake_ctx, mock_binary_available, mock_mcp_ready):
    """Verify all 5 expected hooks are registered when binary and MCP are ready."""
    context_mode_hermes.register(fake_ctx)

    registered_hooks = [call.args[0] for call in fake_ctx.register_hook.call_args_list]
    for hook_name in EXPECTED_HOOKS:
        assert hook_name in registered_hooks, f"hook '{hook_name}' was not registered"
    assert fake_ctx.register_hook.call_count == len(EXPECTED_HOOKS)

def test_register_without_binary(fake_ctx, mock_binary_unavailable):
    """Verify register returns early if binary is unavailable — no hooks registered."""
    context_mode_hermes.register(fake_ctx)
    assert not fake_ctx.register_hook.called
