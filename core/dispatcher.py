"""ToolDispatcher — resolves tool calls against TOOL_REGISTRY and executes them."""

from typing import Any, Callable

from loguru import logger

from core.protocols import ToolCall, ToolResult


class ToolDispatcher:
    """Resolves tool names to async callables and executes them safely.

    All errors are caught and returned as standard error contract dicts —
    the dispatcher never raises exceptions to its caller.
    """

    def __init__(self, registry: dict[str, Callable[..., Any]]) -> None:
        self._registry = registry

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call and return a ToolResult.

        Handles:
        - Unknown tool names → error contract, WARNING log
        - NotImplementedError (stubs) → error contract, WARNING log
        - Any other exception → error contract, ERROR log

        Args:
            tool_call: The tool call to execute, including name and arguments.

        Returns:
            ToolResult with a standardized { success, result, error } dict.
        """
        fn = self._registry.get(tool_call.name)

        if fn is None:
            logger.warning("Unknown tool requested: {!r}", tool_call.name)
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                result={
                    "success": False,
                    "result": None,
                    "error": f"Unknown tool: {tool_call.name}",
                },
            )

        try:
            # Tool functions are async — await them directly.
            # If a tool is CPU-bound or uses sync I/O, it should use
            # asyncio.to_thread internally.
            raw_result = await fn(**tool_call.arguments)
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                result=raw_result,
            )

        except NotImplementedError as exc:
            logger.warning("Tool {!r} not yet implemented: {}", tool_call.name, exc)
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                result={
                    "success": False,
                    "result": None,
                    "error": f"Tool not yet implemented: {tool_call.name}",
                },
            )

        except Exception as exc:
            logger.error(
                "Tool {!r} raised an unexpected error: {}",
                tool_call.name,
                exc,
                exc_info=True,
            )
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                result={
                    "success": False,
                    "result": None,
                    "error": str(exc),
                },
            )
