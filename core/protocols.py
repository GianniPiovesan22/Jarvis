"""
Core protocols and shared data types for Jarvis.

All LLM providers implement LLMProvider. All tool results use the
{"success": bool, "result": Any, "error": str | None} contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ToolCall:
    """A single tool invocation requested by an LLM."""

    id: str          # unique call id (native from Claude; generated for Ollama/Gemini)
    name: str        # must exist in TOOL_REGISTRY
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """The result of executing a ToolCall."""

    tool_call_id: str
    name: str
    result: dict[str, Any]  # always {"success": bool, "result": Any, "error": str | None}


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""

    text: str
    tool_calls: list[ToolCall] | None
    model_used: str  # exact model string, e.g. "llama3.2:3b", "claude-haiku-4-5-20251001"


@runtime_checkable
class LLMProvider(Protocol):
    """
    Protocol that all LLM provider clients must satisfy.

    Providers: OllamaClient, ClaudeClient, GeminiClient.
    All methods are async. History and tools are passed in per-call
    (stateless client — state lives in MemoryDB and main.py).
    """

    async def chat(
        self,
        text: str,
        history: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """
        Send a user message and get an LLM response.

        Args:
            text:    The user's transcribed command.
            history: Previous turns as [{"role": "user"|"assistant", "content": str}, ...].
            tools:   JSON Schema tool definitions for tool use.

        Returns:
            LLMResponse with text and optional tool_calls.
        """
        ...

    async def complete_with_result(
        self,
        tool_results: list[ToolResult],
    ) -> LLMResponse:
        """
        Submit tool execution results and get the final LLM response.

        Called after dispatcher.execute() resolves tool_calls from chat().

        Args:
            tool_results: Results from ToolDispatcher.execute() for each tool_call.

        Returns:
            LLMResponse with the final natural-language answer.
        """
        ...
