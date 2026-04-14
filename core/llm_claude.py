"""
ClaudeClient — LLM provider backed by the Anthropic Claude API.

Uses the official anthropic.AsyncAnthropic SDK. Supports both haiku
(fast, cheap) and sonnet (complex reasoning) models via a single client
instance — the model is selected per-call via model_target.
"""

from __future__ import annotations

from typing import Any

import anthropic
from loguru import logger

from core.config_loader import LLMConfig
from core.protocols import LLMResponse, ToolCall, ToolResult

# ---------------------------------------------------------------------------
# System prompt (SPEC section 7)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "Sos Jarvis, un asistente de IA personal corriendo en la PC de Gianni. "
    "Sos conciso, directo y eficiente — como el Jarvis de Iron Man. "
    "Respondés en español rioplatense. "
    "Nunca decís frases innecesarias. Vas al punto. "
    "Cuando ejecutás una acción, confirmás brevemente qué hiciste. "
    "Si algo no podés hacer, lo decís directo sin rodeos. "
    "Tenés acceso completo al sistema. "
    "Usás las herramientas disponibles sin dudar. "
    "Recordás el contexto de conversaciones anteriores."
)


class ClaudeClient:
    """Async LLM client for Anthropic Claude models.

    Implements the LLMProvider protocol. A single client instance handles
    both haiku and sonnet — the model is resolved per-call. Stateless:
    history and tools are passed per-call. Internal state tracks the
    current conversation for complete_with_result().
    """

    def __init__(self, config: LLMConfig) -> None:
        self._haiku_model: str = config.claude_haiku
        self._sonnet_model: str = config.claude_sonnet
        self._max_tokens: int = config.max_tokens
        self._history_turns: int = config.history_turns
        self._client: anthropic.AsyncAnthropic = anthropic.AsyncAnthropic()
        # Holds the active message list for the current turn
        self._current_messages: list[dict[str, Any]] = []
        self._current_model: str = self._sonnet_model
        logger.info(
            "ClaudeClient ready — haiku={!r} sonnet={!r}",
            self._haiku_model,
            self._sonnet_model,
        )

    # ------------------------------------------------------------------
    # Public API (LLMProvider protocol)
    # ------------------------------------------------------------------

    async def chat(
        self,
        text: str,
        history: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        model_target: str = "claude_sonnet",
    ) -> LLMResponse:
        """Send a user message and get a response from Claude.

        Args:
            text:         The user's transcribed command.
            history:      Previous turns from MemoryDB.get_history().
            tools:        TOOL_SCHEMAS list (JSON Schema format).
            model_target: "claude_haiku" or "claude_sonnet" (default: sonnet).

        Returns:
            LLMResponse with text and optional tool_calls.
        """
        model = (
            self._haiku_model
            if model_target == "claude_haiku"
            else self._sonnet_model
        )
        self._current_model = model

        messages: list[dict[str, Any]] = []
        for turn in history[-self._history_turns :]:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": text})
        self._current_messages = messages

        formatted_tools = self._format_tools(tools)

        try:
            response = await self._client.messages.create(
                model=model,
                max_tokens=self._max_tokens,
                system=SYSTEM_PROMPT,
                tools=formatted_tools,
                messages=messages,
            )
        except anthropic.APIStatusError as exc:
            logger.error("Claude API status error: {} — {}", exc.status_code, exc.message)
            return LLMResponse(
                text=f"Error en la API de Claude ({exc.status_code}). Revisá la clave de API o el estado del servicio.",
                tool_calls=None,
                model_used=model,
            )
        except anthropic.APIConnectionError as exc:
            logger.error("Claude connection error: {}", exc)
            return LLMResponse(
                text="No pude conectarme a la API de Claude. Verificá tu conexión a internet.",
                tool_calls=None,
                model_used=model,
            )
        except anthropic.APIError as exc:
            logger.error("Claude API error: {}", exc)
            return LLMResponse(
                text="Ocurrió un error inesperado con la API de Claude.",
                tool_calls=None,
                model_used=model,
            )

        # Parse response content blocks
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )
                logger.debug("Claude tool_use block: name={!r} id={!r}", block.name, block.id)

        response_text = "\n".join(text_parts)

        # Store assistant turn for complete_with_result()
        self._current_messages.append(
            {"role": "assistant", "content": response.content}  # type: ignore[arg-type]
        )

        return LLMResponse(
            text=response_text,
            tool_calls=tool_calls if tool_calls else None,
            model_used=model,
        )

    async def complete_with_result(
        self,
        tool_results: list[ToolResult],
    ) -> LLMResponse:
        """Submit tool execution results and get the final Claude response.

        Builds tool_result content blocks and re-calls the Claude API
        with the updated conversation.

        Args:
            tool_results: Results from ToolDispatcher.execute().

        Returns:
            LLMResponse with the final natural-language answer.
        """
        # Build the tool_result message
        tool_result_content: list[dict[str, Any]] = []
        for tr in tool_results:
            tool_result_content.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tr.tool_call_id,
                    "content": str(tr.result),
                }
            )

        self._current_messages.append(
            {"role": "user", "content": tool_result_content}
        )

        try:
            response = await self._client.messages.create(
                model=self._current_model,
                max_tokens=self._max_tokens,
                system=SYSTEM_PROMPT,
                messages=self._current_messages,
            )
        except anthropic.APIStatusError as exc:
            logger.error("Claude complete_with_result status error: {}", exc)
            return LLMResponse(
                text=f"Error al procesar el resultado de las herramientas (HTTP {exc.status_code}).",
                tool_calls=None,
                model_used=self._current_model,
            )
        except anthropic.APIError as exc:
            logger.error("Claude complete_with_result API error: {}", exc)
            return LLMResponse(
                text="No pude obtener la respuesta final de Claude.",
                tool_calls=None,
                model_used=self._current_model,
            )

        text_parts: list[str] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)

        return LLMResponse(
            text="\n".join(text_parts),
            tool_calls=None,
            model_used=self._current_model,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _format_tools(
        self, tool_schemas: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Convert TOOL_SCHEMAS format to Claude's expected tool format.

        Claude expects: name, description, input_schema (JSON Schema object).
        TOOL_SCHEMAS already uses this layout — this method normalizes any
        potential differences and filters out incomplete entries.

        Args:
            tool_schemas: List of tool dicts from TOOL_SCHEMAS.

        Returns:
            List of dicts formatted for the Claude messages.create() tools param.
        """
        formatted: list[dict[str, Any]] = []
        for schema in tool_schemas:
            name = schema.get("name")
            description = schema.get("description", "")
            input_schema = schema.get("input_schema", {"type": "object", "properties": {}})
            if not name:
                continue
            formatted.append(
                {
                    "name": name,
                    "description": description,
                    "input_schema": input_schema,
                }
            )
        return formatted
