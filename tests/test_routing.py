import pytest
from unittest.mock import patch, MagicMock
import context_mode_hermes

def test_guard_binary_unavailable(mock_binary_unavailable, mock_mcp_ready):
    with patch("context_mode_hermes._route_via_hook") as mock_route:
        response = context_mode_hermes._pre_tool_call(
            tool_name="terminal", args={"command": "curl https://example.com"},
            session_id="test", task_id="task-1"
        )
        assert response is None
        mock_route.assert_not_called()

def test_guard_mcp_not_ready(mock_binary_available, mock_mcp_not_ready):
    with patch("context_mode_hermes._route_via_hook") as mock_route:
        response = context_mode_hermes._pre_tool_call(
            tool_name="terminal", args={"command": "curl https://example.com"},
            session_id="test", task_id="task-1"
        )
        assert response is None
        mock_route.assert_not_called()

def test_route_returns_block(mock_binary_available, mock_mcp_ready):
    with patch("context_mode_hermes._route_via_hook", return_value={"action": "block", "message": "Use ctx_execute"}), \
         patch("context_mode_hermes._marker_path", return_value="/tmp/test_rejected.txt"), \
         patch("context_mode_hermes._write_marker") as mock_write:
        response = context_mode_hermes._pre_tool_call(
            tool_name="terminal", args={"command": "curl https://example.com"},
            session_id="test", task_id="task-1"
        )
        assert response == {"action": "block", "message": "Use ctx_execute"}
        mock_write.assert_called()

def test_route_returns_passthrough(mock_binary_available, mock_mcp_ready):
    with patch("context_mode_hermes._route_via_hook", return_value=None):
        response = context_mode_hermes._pre_tool_call(
            tool_name="terminal", args={"command": "git status"},
            session_id="test", task_id="task-1"
        )
        assert response is None
