import pytest
from unittest.mock import patch, MagicMock
import context_mode_hermes

def test_webfetch_routes_through_hook(mock_binary_available, mock_mcp_ready):
    with patch("context_mode_hermes._route_via_hook", return_value={"action": "block", "message": "Use ctx_fetch_and_index"}):
        response = context_mode_hermes._pre_tool_call(
            tool_name="webfetch", args={"url": "https://example.com"},
            session_id="test", task_id="task-1"
        )
        assert response is not None
        assert response["action"] == "block"

def test_terminal_routes_through_hook(mock_binary_available, mock_mcp_ready):
    with patch("context_mode_hermes._route_via_hook", return_value=None) as mock_route:
        response = context_mode_hermes._pre_tool_call(
            tool_name="terminal", args={"command": "ls"},
            session_id="test", task_id="task-1"
        )
        assert response is None
        mock_route.assert_called_once_with("terminal", {"command": "ls"}, "test")
