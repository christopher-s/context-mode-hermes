import pytest
from unittest.mock import patch, MagicMock
import subprocess
import context_mode_hermes
import json

def test_deny_maps_to_block():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": "Use ctx_execute"}}'
    with patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/context-mode"), \
         patch("subprocess.run", return_value=mock_result):
        result = context_mode_hermes._route_via_hook("terminal", {"command": "curl http://example.com"}, "test")
        assert result == {"action": "block", "message": "Use ctx_execute"}

def test_allow_maps_to_passthrough():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"hookSpecificOutput": {"permissionDecision": "allow"}}'
    with patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/context-mode"), \
         patch("subprocess.run", return_value=mock_result):
        result = context_mode_hermes._route_via_hook("terminal", {"command": "git status"}, "test")
        assert result is None

def test_empty_stdout_passthrough():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ''
    with patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/context-mode"), \
         patch("subprocess.run", return_value=mock_result):
        result = context_mode_hermes._route_via_hook("terminal", {"command": "ls"}, "test")
        assert result is None

def test_timeout_fails_open():
    with patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/context-mode"), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="pretooluse", timeout=5)):
        result = context_mode_hermes._route_via_hook("terminal", {"command": "curl http://example.com"}, "test")
        assert result is None

def test_nonzero_exit_fails_open():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ''
    with patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/context-mode"), \
         patch("subprocess.run", return_value=mock_result):
        result = context_mode_hermes._route_via_hook("terminal", {"command": "curl http://example.com"}, "test")
        assert result is None

def test_ask_maps_to_ask():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"hookSpecificOutput": {"permissionDecision": "ask", "permissionDecisionReason": "Confirm?"}}'
    with patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/context-mode"), \
         patch("subprocess.run", return_value=mock_result):
        result = context_mode_hermes._route_via_hook("terminal", {"command": "rm -rf /"}, "test")
        assert result == {"action": "ask", "message": "Confirm?"}

def test_tool_name_mapping():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ''
    with patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/context-mode"), \
         patch("subprocess.run", return_value=mock_result) as mock_run:
        context_mode_hermes._route_via_hook("terminal", {"command": "ls"}, "test")
        payload = json.loads(mock_run.call_args.kwargs["input"])
        assert payload["tool_name"] == "Bash"

        context_mode_hermes._route_via_hook("webfetch", {"url": "http://example.com"}, "test")
        payload2 = json.loads(mock_run.call_args.kwargs["input"])
        assert payload2["tool_name"] == "WebFetch"
