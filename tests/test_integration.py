import pytest
import shutil
from unittest.mock import patch
import context_mode_hermes

pytestmark = pytest.mark.skipif(
    shutil.which("context-mode") is None,
    reason="context-mode binary not installed"
)

def test_real_binary_curl_blocked():
    context_mode_hermes._ctx_available = None
    context_mode_hermes._mcp_ready = None
    
    result = context_mode_hermes._pre_tool_call(
        tool_name="terminal",
        args={"command": "curl https://httpbin.org/get"},
        session_id="integration-test",
        task_id="t1"
    )
    if result is not None:
        assert result["action"] == "block"
        assert "ctx_execute" in result["message"] or "ctx_fetch" in result["message"]

def test_real_binary_safe_command_passes():
    context_mode_hermes._ctx_available = None
    context_mode_hermes._mcp_ready = None
    
    result = context_mode_hermes._pre_tool_call(
        tool_name="terminal",
        args={"command": "git status"},
        session_id="integration-test",
        task_id="t1"
    )
    assert result is None
