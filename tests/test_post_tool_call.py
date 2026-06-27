import pytest
from unittest.mock import patch, MagicMock
import context_mode_hermes

def test_no_session_id_returns_early():
    """Empty session_id → return immediately, no processing."""
    with patch("context_mode_hermes._read_and_unlink_marker") as mock_read:
        context_mode_hermes._post_tool_call(
            tool_name="terminal", args={}, result="output",
            task_id="t1", session_id="", duration_ms=100
        )
        mock_read.assert_not_called()

def test_reads_rejected_marker(mock_binary_available):
    """When a rejected marker exists, it's read and logged."""
    with patch("context_mode_hermes._check_context_mode", return_value=True), \
         patch("context_mode_hermes._read_and_unlink_marker", side_effect=["webfetch:blocked", None, None]), \
         patch("subprocess.run") as mock_subprocess:
        # Note: _read_and_unlink_marker is called twice: once for rejected, once for latency
        # The side_effect provides values in call order
        context_mode_hermes._post_tool_call(
            tool_name="terminal", args={"command": "ls"}, result="file1\nfile2",
            task_id="t1", session_id="test-sess", duration_ms=50
        )
        # Verify subprocess was called for event forwarding
        mock_subprocess.assert_called()

def test_forwards_event_to_upstream(mock_binary_available):
    """PostToolUse forwards the tool result to context-mode binary."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("context_mode_hermes._check_context_mode", return_value=True), \
         patch("context_mode_hermes._read_and_unlink_marker", return_value=None), \
         patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/context-mode"), \
         patch("subprocess.run", return_value=mock_result) as mock_run:
        context_mode_hermes._post_tool_call(
            tool_name="terminal", args={"command": "ls"}, result="file1",
            task_id="t1", session_id="test-sess", duration_ms=50
        )
        # Verify the command includes "posttooluse"
        cmd = mock_run.call_args.args[0]
        assert "posttooluse" in cmd

def test_posttool_fails_open(mock_binary_available):
    """Subprocess failure in post_tool_call does NOT raise."""
    with patch("context_mode_hermes._check_context_mode", return_value=True), \
         patch("context_mode_hermes._read_and_unlink_marker", return_value=None), \
         patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/context-mode"), \
         patch("subprocess.run", side_effect=Exception("binary crashed")):
        # Should NOT raise
        context_mode_hermes._post_tool_call(
            tool_name="terminal", args={}, result="data",
            task_id="t1", session_id="test-sess", duration_ms=50
        )
