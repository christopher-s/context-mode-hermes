import pytest
from unittest.mock import patch, MagicMock
import context_mode_hermes

def test_no_session_id_returns_early():
    with patch("context_mode_hermes._read_and_unlink_marker") as mock_read:
        context_mode_hermes._post_tool_call(
            tool_name="terminal", args={}, result="output",
            task_id="t1", session_id="", duration_ms=100
        )
        mock_read.assert_not_called()

def test_reads_and_consumes_rejected_marker(mock_binary_available):
    with patch("context_mode_hermes._check_context_mode", return_value=True), \
         patch("context_mode_hermes._read_and_unlink_marker", side_effect=["webfetch:blocked", None]) as mock_read, \
         patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/cm"), \
         patch("subprocess.run"):
        context_mode_hermes._post_tool_call(
            tool_name="terminal", args={"command": "ls"}, result="file1\nfile2",
            task_id="t1", session_id="test-sess", duration_ms=50
        )
        # First call reads the rejected marker (second is latency)
        first_call_args = mock_read.call_args_list[0]
        assert "rejected" in first_call_args.args[0]

def test_forwards_event_to_upstream(mock_binary_available):
    """PostToolUse forwards the tool result to context-mode binary with correct payload."""
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
        cmd = mock_run.call_args.args[0]
        assert "posttooluse" in cmd
        import json
        payload = json.loads(mock_run.call_args.kwargs["input"])
        assert payload["tool_name"] == "terminal"
        assert payload["tool_input"] == {"command": "ls"}
        assert payload["tool_response"] == "file1"

def test_posttool_fails_open(mock_binary_available):
    with patch("context_mode_hermes._check_context_mode", return_value=True), \
         patch("context_mode_hermes._read_and_unlink_marker", return_value=None), \
         patch("context_mode_hermes._resolve_context_mode_binary", return_value="/fake/context-mode"), \
         patch("subprocess.run", side_effect=Exception("binary crashed")):
        context_mode_hermes._post_tool_call(
            tool_name="terminal", args={}, result="data",
            task_id="t1", session_id="test-sess", duration_ms=50
        )
