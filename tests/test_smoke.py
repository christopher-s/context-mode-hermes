import importlib.metadata
import inspect
import types

import context_mode_hermes


def test_plugin_smoke():
    assert callable(context_mode_hermes.register)
    assert list(inspect.signature(context_mode_hermes.register).parameters) == ["ctx"]
    assert hasattr(context_mode_hermes, "_pre_tool_call")
    assert hasattr(context_mode_hermes, "_post_tool_call")
    assert hasattr(context_mode_hermes, "_pre_llm_call")


def test_entry_point_loads_module_for_loader_compatibility():
    entry_point = next(
        ep
        for ep in importlib.metadata.entry_points().select(group="hermes_agent.plugins")
        if ep.name == "context-mode"
    )
    loaded = entry_point.load()

    assert isinstance(loaded, types.ModuleType)
    assert loaded.register is context_mode_hermes.register
    assert not callable(loaded)
