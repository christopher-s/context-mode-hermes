import pytest
import json
from unittest.mock import patch, MagicMock
import context_mode_hermes

def test_malformed_json_from_binary():
    """Binary returns invalid JSON → fail-open (None)."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = 'not valid json {{{'
    with patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/cm"), \
         patch("subprocess.run", return_value=mock_result):
        result = context_mode_hermes._route_via_hook("terminal", {"command": "ls"}, "test")
        assert result is None

def test_missing_hook_specific_output():
    """Binary returns JSON without hookSpecificOutput → passthrough."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"some_other_field": "value"}'
    with patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/cm"), \
         patch("subprocess.run", return_value=mock_result):
        result = context_mode_hermes._route_via_hook("terminal", {"command": "ls"}, "test")
        assert result is None

def test_missing_permission_decision():
    """hookSpecificOutput exists but no permissionDecision → passthrough."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"hookSpecificOutput": {"hookEventName": "PreToolUse"}}'
    with patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/cm"), \
         patch("subprocess.run", return_value=mock_result):
        result = context_mode_hermes._route_via_hook("terminal", {"command": "ls"}, "test")
        assert result is None

def test_deny_without_reason():
    """permissionDecision=deny but no reason → block with empty message."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = '{"hookSpecificOutput": {"permissionDecision": "deny"}}'
    with patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/cm"), \
         patch("subprocess.run", return_value=mock_result):
        result = context_mode_hermes._route_via_hook("terminal", {"command": "ls"}, "test")
        assert result == {"action": "block", "message": ""}

def test_hook_safe_swallows_exceptions():
    """If a hook raises, _hook_safe wrapper swallows it (returns None)."""
    with patch("context_mode_hermes._check_context_mode", side_effect=RuntimeError("boom")):
        # _pre_tool_call is wrapped by _hook_safe, so it should NOT raise
        result = context_mode_hermes._pre_tool_call(
            tool_name="terminal", args={}, session_id="test", task_id="t1"
        )
        assert result is None

def test_session_lifecycle_clears_markers(mock_binary_available):
    """on_session_end cleans up session marker files."""
    with patch("context_mode_hermes._cleanup_session_markers") as mock_cleanup:
        context_mode_hermes._on_session_end(session_id="test-sess")
        mock_cleanup.assert_called_once_with("test-sess")

def test_session_reset_clears_markers(mock_binary_available):
    """on_session_reset cleans up session marker files."""
    with patch("context_mode_hermes._cleanup_session_markers") as mock_cleanup:
        context_mode_hermes._on_session_reset(session_id="test-sess")
        mock_cleanup.assert_called_once_with("test-sess")

def test_session_end_no_session_id():
    """on_session_end with empty session_id → no-op."""
    with patch("context_mode_hermes._cleanup_session_markers") as mock_cleanup:
        context_mode_hermes._on_session_end(session_id="")
        mock_cleanup.assert_not_called()
