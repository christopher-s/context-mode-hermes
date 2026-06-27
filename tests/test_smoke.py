import pytest
import context_mode_hermes
from unittest.mock import patch, MagicMock

def test_plugin_smoke():
    # Verify entry point exists
    assert callable(context_mode_hermes.register)
    
    # Verify hooks exist
    assert hasattr(context_mode_hermes, "_pre_tool_call")
    assert hasattr(context_mode_hermes, "_post_tool_call")
    assert hasattr(context_mode_hermes, "_pre_llm_call")

def test_plugin_initialization_no_binary():
    # Ensure we don't trigger real binary checks
    mock_ctx = MagicMock()
    with patch("context_mode_hermes._check_context_mode", return_value=True), \
         patch("context_mode_hermes._check_mcp_ready", return_value=True):
        # This should not raise an error
        context_mode_hermes.register(mock_ctx)
    
    # Verify hooks were registered
    assert mock_ctx.register_hook.called
