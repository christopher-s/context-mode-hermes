import pytest
from unittest.mock import MagicMock, patch
import context_mode_hermes
import subprocess

def test_compact_triggers_precompact(mock_binary_available, mock_mcp_ready):
    with patch("context_mode_hermes._check_context_mode", return_value=True), \
         patch("context_mode_hermes._check_mcp_ready", return_value=True), \
         patch("subprocess.run") as mock_run:
        
        context_mode_hermes._pre_llm_call(
            session_id="test",
            user_message="/compact",
            is_first_turn=False,
            model="test-model",
            platform="test-platform"
        )
        
        assert mock_run.called
        assert "precompact" in " ".join(mock_run.call_args[0][0])

def test_clear_triggers_precompact(mock_binary_available, mock_mcp_ready):
    with patch("context_mode_hermes._check_context_mode", return_value=True), \
         patch("context_mode_hermes._check_mcp_ready", return_value=True), \
         patch("subprocess.run") as mock_run:
        
        context_mode_hermes._pre_llm_call(
            session_id="test",
            user_message="/clear",
            is_first_turn=False,
            model="test-model",
            platform="test-platform"
        )
        
        assert mock_run.called
        assert "precompact" in " ".join(mock_run.call_args[0][0])

def test_non_compact_does_not_trigger_precompact(mock_binary_available, mock_mcp_ready):
    with patch("context_mode_hermes._check_context_mode", return_value=True), \
         patch("context_mode_hermes._check_mcp_ready", return_value=True), \
         patch("subprocess.run") as mock_run:
        
        context_mode_hermes._pre_llm_call(
            session_id="test",
            user_message="hello",
            is_first_turn=False,
            model="test-model",
            platform="test-platform"
        )
        
        assert not mock_run.called

def test_precompact_fails_open(mock_binary_available, mock_mcp_ready):
    with patch("context_mode_hermes._check_context_mode", return_value=True), \
         patch("context_mode_hermes._check_mcp_ready", return_value=True), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="precompact", timeout=2)):
        
        context_mode_hermes._pre_llm_call(
            session_id="test",
            user_message="/compact",
            is_first_turn=False,
            model="test-model",
            platform="test-platform"
        )
