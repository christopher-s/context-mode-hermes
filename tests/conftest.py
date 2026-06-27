import pytest
import context_mode_hermes
from unittest.mock import MagicMock, patch
import tempfile
import os
import shutil

@pytest.fixture(autouse=True)
def reset_module_state():
    """Resets module-global caches before each test."""
    context_mode_hermes._ctx_available = None
    context_mode_hermes._mcp_ready = None
    yield
    context_mode_hermes._ctx_available = None
    context_mode_hermes._mcp_ready = None

@pytest.fixture
def fake_ctx():
    """A fake context object that records hook registrations."""
    ctx = MagicMock()
    return ctx

@pytest.fixture
def mock_binary_available():
    """Simulates context-mode binary being available."""
    with patch("context_mode_hermes._check_context_mode", return_value=True):
        yield

@pytest.fixture
def mock_binary_unavailable():
    """Simulates context-mode binary NOT being available."""
    with patch("context_mode_hermes._check_context_mode", return_value=False):
        yield

@pytest.fixture
def mock_mcp_ready():
    """Simulates MCP being ready."""
    with patch("context_mode_hermes._check_mcp_ready", return_value=True):
        yield

@pytest.fixture
def mock_mcp_not_ready():
    """Simulates MCP NOT being ready."""
    with patch("context_mode_hermes._check_mcp_ready", return_value=False):
        yield

@pytest.fixture
def tmp_guidance_dir(tmp_path):
    """Patches _guidance_marker_dir to use a tmp_path."""
    marker_dir = tmp_path / "markers"
    marker_dir.mkdir()
    with patch("context_mode_hermes._guidance_marker_dir", return_value=str(marker_dir)):
        yield marker_dir
