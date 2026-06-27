import pytest
import context_mode_hermes

def test_register_with_all_ready(fake_ctx, mock_binary_available, mock_mcp_ready):
    """Verify hooks are registered when binary and MCP are ready."""
    context_mode_hermes.register(fake_ctx)
    assert fake_ctx.register_hook.called

def test_register_without_binary(fake_ctx, mock_binary_unavailable):
    """Verify register returns early if binary is unavailable."""
    context_mode_hermes.register(fake_ctx)
    assert not fake_ctx.register_hook.called
