"""
OllamaClient — LLM provider backed by a local Ollama instance.

Communicates over HTTP using httpx.AsyncClient. Tool calls are parsed
manually from the raw text response using regex + JSON parsing, since
Ollama's tool-use support varies by model.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

import httpx
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


class OllamaClient:
    """Async LLM client for local Ollama models.

    Implements the LLMProvider protocol. Stateless: history and tools
    are passed per-call. Internal state tracks the current turn's
    message list to support complete_with_result().
    """

    def __init__(self, config: LLMConfig) -> None:
        self._ollama_url: str = config.ollama_url
        self._model: str = config.ollama_model
        self._max_tokens: int = config.max_tokens
        self._http: httpx.AsyncClient = httpx.AsyncClient(timeout=60.0)
        # Holds the active conversation for the current turn (reset each chat())
        self._current_messages: list[dict[str, Any]] = []
        logger.info(
            "OllamaClient ready — model={!r} url={!r}", self._model, self._ollama_url
        )

    # ------------------------------------------------------------------
    # Public API (LLMProvider protocol)
    # ------------------------------------------------------------------

    async def chat(
        self,
        text: str,
        history: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Send a user message and get a response from Ollama.

        Builds the full message list (system + history + user message),
        POSTs to the Ollama /api/chat endpoint, and attempts to parse
        tool calls from the response content.

        Args:
            text:    The user's transcribed command.
            history: Previous turns as returned by MemoryDB.get_history().
            tools:   TOOL_SCHEMAS list (JSON Schema format).

        Returns:
            LLMResponse with text and optional tool_calls.
        """
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": text})
        self._current_messages = messages

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": self._max_tokens},
        }

        try:
            resp = await self._http.post(
                f"{self._ollama_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama HTTP error: {} {}", exc.response.status_code, exc)
            return LLMResponse(
                text=f"Error al contactar Ollama (HTTP {exc.response.status_code}). Revisá que el servicio esté corriendo.",
                tool_calls=None,
                model_used=self._model,
            )
        except httpx.RequestError as exc:
            logger.error("Ollama request error: {}", exc)
            return LLMResponse(
                text="No pude conectarme a Ollama. ¿Está corriendo el servicio local?",
                tool_calls=None,
                model_used=self._model,
            )

        content: str = data.get("message", {}).get("content", "")
        logger.debug("Ollama raw response ({} chars): {!r}", len(content), content[:200])

        tool_calls = self._parse_tool_calls(content)

        # Append assistant response to internal message list
        self._current_messages.append({"role": "assistant", "content": content})

        return LLMResponse(
            text=content,
            tool_calls=tool_calls,
            model_used=self._model,
        )

    async def complete_with_result(
        self,
        tool_results: list[ToolResult],
    ) -> LLMResponse:
        """Submit tool execution results and get the final response.

        Appends tool results as an assistant context message and re-calls
        the Ollama API with the full updated conversation.

        Args:
            tool_results: Results from ToolDispatcher.execute().

        Returns:
            LLMResponse with the final natural-language answer.
        """
        # Summarize tool results and append as a user context message
        results_text = "\n".join(
            f"[{tr.name}]: {json.dumps(tr.result, ensure_ascii=False)}"
            for tr in tool_results
        )
        context_msg = f"Resultados de las herramientas ejecutadas:\n{results_text}\n\nRespondé basándote en estos resultados."
        self._current_messages.append({"role": "user", "content": context_msg})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": self._current_messages,
            "stream": False,
            "options": {"num_predict": self._max_tokens},
        }

        try:
            resp = await self._http.post(
                f"{self._ollama_url}/api/chat",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama complete_with_result HTTP error: {}", exc)
            return LLMResponse(
                text=f"Error al procesar el resultado de las herramientas (HTTP {exc.response.status_code}).",
                tool_calls=None,
                model_used=self._model,
            )
        except httpx.RequestError as exc:
            logger.error("Ollama complete_with_result request error: {}", exc)
            return LLMResponse(
                text="No pude obtener la respuesta final de Ollama.",
                tool_calls=None,
                model_used=self._model,
            )

        content: str = data.get("message", {}).get("content", "")
        return LLMResponse(
            text=content,
            tool_calls=None,
            model_used=self._model,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_tool_calls(self, content: str) -> list[ToolCall] | None:
        """Attempt to extract tool calls from raw LLM text output.

        Looks for:
        1. JSON code blocks: ```json { "name": ..., "arguments": ... } ```
        2. Raw JSON objects with "name" and "arguments" keys.

        Never raises — returns None if parsing fails or nothing is found.

        Args:
            content: Raw text from the LLM response.

        Returns:
            List of ToolCall objects, or None if none were found.
        """
        candidates: list[str] = []

        # Strategy 1: extract ```json ... ``` blocks
        code_block_pattern = re.compile(
            r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE
        )
        for match in code_block_pattern.finditer(content):
            candidates.append(match.group(1))

        # Strategy 2: extract any top-level JSON object from the text
        if not candidates:
            bare_json_pattern = re.compile(r"\{[^{}]*\}", re.DOTALL)
            for match in bare_json_pattern.finditer(content):
                candidates.append(match.group(0))

        tool_calls: list[ToolCall] = []

        for candidate in candidates:
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError:
                continue

            # Must have "name" and "arguments" keys
            if not isinstance(data, dict):
                continue
            name = data.get("name")
            arguments = data.get("arguments")
            if not isinstance(name, str) or not isinstance(arguments, dict):
                continue

            tool_calls.append(
                ToolCall(
                    id=str(uuid.uuid4()),
                    name=name,
                    arguments=arguments,
                )
            )
            logger.debug("Parsed tool call from Ollama response: name={!r}", name)

        if not tool_calls:
            return None

        return tool_calls
