import pytest
import shutil
import json
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
    assert result is not None
    assert result["action"] == "block"
    assert "ctx_execute" in result["message"] or "ctx_fetch" in result["message"]


def test_real_binary_wget_blocked():
    context_mode_hermes._ctx_available = None
    context_mode_hermes._mcp_ready = None

    result = context_mode_hermes._pre_tool_call(
        tool_name="terminal",
        args={"command": "wget https://httpbin.org/get"},
        session_id="integration-test",
        task_id="t1"
    )
    assert result is not None
    assert result["action"] == "block"


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


def test_real_binary_ls_passes():
    context_mode_hermes._ctx_available = None
    context_mode_hermes._mcp_ready = None

    result = context_mode_hermes._pre_tool_call(
        tool_name="terminal",
        args={"command": "ls -la"},
        session_id="integration-test",
        task_id="t1"
    )
    assert result is None


def test_real_binary_inline_http_requests_blocked():
    context_mode_hermes._ctx_available = None
    context_mode_hermes._mcp_ready = None

    result = context_mode_hermes._pre_tool_call(
        tool_name="terminal",
        args={"command": "python -c 'import requests; requests.get(\"https://example.com\")'"},
        session_id="integration-test",
        task_id="t1"
    )
    assert result is not None
    assert result["action"] == "block"


def test_real_binary_build_tool_blocked():
    context_mode_hermes._ctx_available = None
    context_mode_hermes._mcp_ready = None

    result = context_mode_hermes._pre_tool_call(
        tool_name="terminal",
        args={"command": "gradle build"},
        session_id="integration-test",
        task_id="t1"
    )
    assert result is not None
    assert result["action"] == "block"


def test_real_binary_curl_silent_file_output_passes():
    context_mode_hermes._ctx_available = None
    context_mode_hermes._mcp_ready = None

    result = context_mode_hermes._pre_tool_call(
        tool_name="terminal",
        args={"command": "curl -s -o /tmp/test.json https://httpbin.org/get"},
        session_id="integration-test",
        task_id="t1"
    )
    assert result is None


def test_real_binary_deny_message_contains_redirect():
    context_mode_hermes._ctx_available = None
    context_mode_hermes._mcp_ready = None

    result = context_mode_hermes._pre_tool_call(
        tool_name="terminal",
        args={"command": "curl https://httpbin.org/get"},
        session_id="integration-test",
        task_id="t1"
    )
    assert result is not None
    msg = result["message"].lower()
    assert "ctx_execute" in msg or "ctx_fetch_and_index" in msg


def test_route_via_hook_real_binary_format():
    context_mode_hermes._ctx_available = None
    context_mode_hermes._mcp_ready = None

    result = context_mode_hermes._route_via_hook(
        "terminal",
        {"command": "curl https://httpbin.org/get"},
        "integration-test"
    )
    assert result is not None
    assert result["action"] == "block"
    assert isinstance(result["message"], str)
    assert len(result["message"]) > 10


def test_route_via_hook_real_binary_passthrough_format():
    context_mode_hermes._ctx_available = None
    context_mode_hermes._mcp_ready = None

    result = context_mode_hermes._route_via_hook(
        "terminal",
        {"command": "pwd"},
        "integration-test"
    )
    assert result is None
