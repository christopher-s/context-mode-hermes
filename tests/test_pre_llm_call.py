import pytest
import os
from unittest.mock import patch, MagicMock
import context_mode_hermes

def test_binary_unavailable_returns_none(mock_binary_unavailable):
    """Binary missing → pre_llm_call returns None."""
    with patch("context_mode_hermes._check_context_mode", return_value=False):
        result = context_mode_hermes._pre_llm_call(
            session_id="test", user_message="hello",
            is_first_turn=True, model="test", platform="test"
        )
        assert result is None

def test_first_turn_injects_routing_block(mock_binary_available, mock_mcp_ready):
    with patch("context_mode_hermes._check_context_mode", return_value=True), \
         patch("context_mode_hermes._trigger_session_start", return_value=""), \
         patch("context_mode_hermes._write_marker"):
        result = context_mode_hermes._pre_llm_call(
            session_id="test-session", user_message="hello",
            is_first_turn=True, model="test", platform="test"
        )
        assert result is not None
        assert "context" in result
        assert "ctx_execute" in result["context"]

def test_first_turn_with_existing_marker_skips_injection(mock_binary_available, mock_mcp_ready):
    """If injected marker already exists → skip (no duplicate)."""
    with patch("context_mode_hermes._check_context_mode", return_value=True), \
         patch("os.path.exists", return_value=True), \
         patch("context_mode_hermes._trigger_session_start") as mock_trigger:
        result = context_mode_hermes._pre_llm_call(
            session_id="test-session", user_message="hello",
            is_first_turn=True, model="test", platform="test"
        )
        assert result is None
        mock_trigger.assert_not_called()

def test_first_turn_uses_upstream_context_when_available(mock_binary_available, mock_mcp_ready):
    """When upstream returns context, use it instead of ROUTING_BLOCK."""
    upstream_block = "<custom_routing>upstream rules</custom_routing>"
    with patch("context_mode_hermes._check_context_mode", return_value=True), \
         patch("context_mode_hermes._trigger_session_start", return_value=upstream_block), \
         patch("context_mode_hermes._write_marker"):
        result = context_mode_hermes._pre_llm_call(
            session_id="test-session", user_message="hello",
            is_first_turn=True, model="test", platform="test"
        )
        assert result["context"] == upstream_block

def test_compact_returns_preservation_message(mock_binary_available, mock_mcp_ready):
    """/compact message → returns knowledge base preservation context."""
    with patch("context_mode_hermes._check_context_mode", return_value=True), \
         patch("context_mode_hermes._trigger_precompact"):
        result = context_mode_hermes._pre_llm_call(
            session_id="test", user_message="/compact",
            is_first_turn=False, model="test", platform="test"
        )
        assert result is not None
        assert "context" in result
        assert "preserved" in result["context"].lower()

def test_normal_message_returns_none(mock_binary_available, mock_mcp_ready):
    """Normal message (not first turn, not compact) → returns None."""
    with patch("context_mode_hermes._check_context_mode", return_value=True):
        result = context_mode_hermes._pre_llm_call(
            session_id="test", user_message="write some code",
            is_first_turn=False, model="test", platform="test"
        )
        assert result is None
