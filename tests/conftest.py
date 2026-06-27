import pytest
import context_mode_hermes
from unittest.mock import MagicMock, patch
import tempfile
import os
import shutil

# Make the real context-mode binary discoverable for integration tests.
# Hermes installs it to ~/.hermes/node/bin/ which isn't on the default PATH.
_HERMES_NODE_BIN = os.path.expanduser("~/.hermes/node/bin")
if os.path.isdir(_HERMES_NODE_BIN) and shutil.which("context-mode") is None:
    os.environ["PATH"] = _HERMES_NODE_BIN + os.pathsep + os.environ.get("PATH", "")

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
def tmp_markers(tmp_path):
    """Patches marker paths to use a tmp_path instead of the system temp dir."""
    marker_dir = tmp_path / "markers"
    marker_dir.mkdir()
    with patch("context_mode_hermes._marker_path", side_effect=lambda prefix, sid, suffix="": os.path.join(str(marker_dir), f"{prefix}-{sid}-{suffix}.txt" if suffix else f"{prefix}-{sid}.txt")):
        yield marker_dir
