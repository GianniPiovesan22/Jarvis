"""
Unit tests for ToolDispatcher.

All tests use fake async callables — never the real TOOL_REGISTRY.
No I/O, no HTTP calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.dispatcher import ToolDispatcher
from core.protocols import ToolCall, ToolResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_call(name: str, arguments: dict | None = None, call_id: str = "call-1") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments or {})


# ---------------------------------------------------------------------------
# Unknown tool
# ---------------------------------------------------------------------------


async def test_unknown_tool_returns_error_result(tool_registry: dict) -> None:
    """Requesting a tool that isn't in the registry returns success=False."""
    dispatcher = ToolDispatcher(tool_registry)
    result = await dispatcher.execute(make_call("nonexistent_tool"))

    assert isinstance(result, ToolResult)
    assert result.name == "nonexistent_tool"
    assert result.tool_call_id == "call-1"
    assert result.result["success"] is False
    assert "Unknown tool" in result.result["error"]


# ---------------------------------------------------------------------------
# Successful tool call
# ---------------------------------------------------------------------------


async def test_known_tool_is_called_with_correct_arguments(tool_registry: dict) -> None:
    """Known tool is invoked with the exact arguments from the ToolCall."""
    dispatcher = ToolDispatcher(tool_registry)
    call = make_call("fake_success", arguments={"volume": 80}, call_id="call-abc")

    result = await dispatcher.execute(call)

    # The mock should have been called with the tool's arguments
    tool_registry["fake_success"].assert_awaited_once_with(volume=80)

    assert isinstance(result, ToolResult)
    assert result.tool_call_id == "call-abc"
    assert result.name == "fake_success"
    assert result.result["success"] is True
    assert result.result["result"] == "ok"
    assert result.result["error"] is None


async def test_known_tool_no_args(tool_registry: dict) -> None:
    """Tool with no arguments is called correctly."""
    dispatcher = ToolDispatcher(tool_registry)
    result = await dispatcher.execute(make_call("fake_success"))

    tool_registry["fake_success"].assert_awaited_once_with()
    assert result.result["success"] is True


# ---------------------------------------------------------------------------
# NotImplementedError → stub tools
# ---------------------------------------------------------------------------


async def test_not_implemented_error_returns_error_result(tool_registry: dict) -> None:
    """NotImplementedError from a stub tool returns success=False with descriptive error."""
    dispatcher = ToolDispatcher(tool_registry)
    result = await dispatcher.execute(make_call("fake_not_implemented", call_id="call-ni"))

    assert isinstance(result, ToolResult)
    assert result.tool_call_id == "call-ni"
    assert result.name == "fake_not_implemented"
    assert result.result["success"] is False
    assert result.result["result"] is None
    assert "fake_not_implemented" in result.result["error"]


# ---------------------------------------------------------------------------
# Generic Exception → unexpected errors
# ---------------------------------------------------------------------------


async def test_generic_exception_returns_error_result(tool_registry: dict) -> None:
    """Any unexpected exception is caught and returned as success=False."""
    dispatcher = ToolDispatcher(tool_registry)
    result = await dispatcher.execute(make_call("fake_error", call_id="call-err"))

    assert isinstance(result, ToolResult)
    assert result.tool_call_id == "call-err"
    assert result.name == "fake_error"
    assert result.result["success"] is False
    assert result.result["result"] is None
    # The error message is the str() of the exception
    assert "tool exploded" in result.result["error"]


# ---------------------------------------------------------------------------
# Multiple calls — dispatcher is stateless
# ---------------------------------------------------------------------------


async def test_dispatcher_handles_multiple_sequential_calls(tool_registry: dict) -> None:
    """Dispatcher can execute multiple calls in sequence without state leaking."""
    dispatcher = ToolDispatcher(tool_registry)

    r1 = await dispatcher.execute(make_call("fake_success", call_id="c1"))
    r2 = await dispatcher.execute(make_call("fake_success", call_id="c2"))
    r3 = await dispatcher.execute(make_call("fake_error", call_id="c3"))

    assert r1.tool_call_id == "c1"
    assert r1.result["success"] is True

    assert r2.tool_call_id == "c2"
    assert r2.result["success"] is True

    assert r3.tool_call_id == "c3"
    assert r3.result["success"] is False


# ---------------------------------------------------------------------------
# Custom registry (inline, not fixture)
# ---------------------------------------------------------------------------


async def test_dispatcher_uses_injected_registry() -> None:
    """ToolDispatcher uses only the registry passed at construction time."""
    custom_fn = AsyncMock(return_value={"success": True, "result": 42, "error": None})
    dispatcher = ToolDispatcher({"my_tool": custom_fn})

    result = await dispatcher.execute(make_call("my_tool", {"x": 1}))

    custom_fn.assert_awaited_once_with(x=1)
    assert result.result["result"] == 42
