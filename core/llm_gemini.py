"""
GeminiClient — LLM provider backed by Google Gemini (google-genai SDK).

The google-genai SDK is synchronous, so all API calls are wrapped in
asyncio.to_thread() to avoid blocking the event loop. Activated only
via --force-gemini; not in the default routing path.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from google import genai
from google.genai import types
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


class GeminiClient:
    """Async LLM client for Google Gemini models.

    Implements the LLMProvider protocol. Wraps the synchronous google-genai
    SDK in asyncio.to_thread(). Stateless: history and tools are passed
    per-call. Internal state tracks the current conversation for
    complete_with_result().
    """

    def __init__(self, config: LLMConfig) -> None:
        self._model: str = config.gemini_model
        api_key_env: str = config.gemini_api_key_env
        api_key = os.environ.get(api_key_env, "")
        if not api_key:
            logger.warning(
                "GeminiClient: env var {!r} is not set — Gemini calls will fail",
                api_key_env,
            )
        self._client: genai.Client = genai.Client(api_key=api_key)
        # Active contents for the current turn (reset each chat())
        self._current_contents: list[types.Content] = []
        logger.info("GeminiClient ready — model={!r}", self._model)

    # ------------------------------------------------------------------
    # Public API (LLMProvider protocol)
    # ------------------------------------------------------------------

    async def chat(
        self,
        text: str,
        history: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        """Send a user message and get a response from Gemini.

        Wraps the synchronous generate_content call in asyncio.to_thread.

        Args:
            text:    The user's transcribed command.
            history: Previous turns from MemoryDB.get_history().
            tools:   TOOL_SCHEMAS list (JSON Schema format).

        Returns:
            LLMResponse with text and optional tool_calls.
        """
        contents: list[types.Content] = []

        for turn in history:
            role = turn.get("role", "user")
            content_text = turn.get("content", "")
            if role == "user":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part(text=content_text)],
                    )
                )
            elif role == "assistant":
                contents.append(
                    types.Content(
                        role="model",
                        parts=[types.Part(text=content_text)],
                    )
                )

        contents.append(
            types.Content(
                role="user",
                parts=[types.Part(text=text)],
            )
        )
        self._current_contents = list(contents)

        function_declarations = self._convert_tools(tools)
        gemini_tools = [types.Tool(function_declarations=function_declarations)]

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=gemini_tools,
            max_output_tokens=None,
        )

        try:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self._model,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            logger.error("Gemini chat error: {}", exc)
            return LLMResponse(
                text="Ocurrió un error al contactar la API de Gemini. Verificá tu clave de API y conexión.",
                tool_calls=None,
                model_used=self._model,
            )

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for candidate in response.candidates or []:
            for part in candidate.content.parts if candidate.content else []:
                if part.text:
                    text_parts.append(part.text)
                elif part.function_call:
                    fc = part.function_call
                    args: dict[str, Any] = {}
                    if fc.args:
                        args = dict(fc.args)
                    tool_calls.append(
                        ToolCall(
                            id=fc.name or "",
                            name=fc.name or "",
                            arguments=args,
                        )
                    )
                    logger.debug("Gemini function_call: name={!r}", fc.name)

        # Append the model's response to current contents for complete_with_result()
        if response.candidates:
            model_content = response.candidates[0].content
            if model_content:
                self._current_contents.append(model_content)

        return LLMResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls if tool_calls else None,
            model_used=self._model,
        )

    async def complete_with_result(
        self,
        tool_results: list[ToolResult],
    ) -> LLMResponse:
        """Submit tool execution results and get the final Gemini response.

        Builds function_response parts and re-calls generate_content
        with the full conversation history.

        Args:
            tool_results: Results from ToolDispatcher.execute().

        Returns:
            LLMResponse with the final natural-language answer.
        """
        function_response_parts: list[types.Part] = []
        for tr in tool_results:
            function_response_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=tr.name,
                        response=tr.result,
                    )
                )
            )

        self._current_contents.append(
            types.Content(
                role="user",
                parts=function_response_parts,
            )
        )

        try:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self._model,
                contents=self._current_contents,
            )
        except Exception as exc:
            logger.error("Gemini complete_with_result error: {}", exc)
            return LLMResponse(
                text="No pude obtener la respuesta final de Gemini.",
                tool_calls=None,
                model_used=self._model,
            )

        text_parts: list[str] = []
        for candidate in response.candidates or []:
            for part in candidate.content.parts if candidate.content else []:
                if part.text:
                    text_parts.append(part.text)

        return LLMResponse(
            text="\n".join(text_parts),
            tool_calls=None,
            model_used=self._model,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _convert_tools(
        self, tool_schemas: list[dict[str, Any]]
    ) -> list[types.FunctionDeclaration]:
        """Convert TOOL_SCHEMAS format to Gemini FunctionDeclaration objects.

        Args:
            tool_schemas: List of tool dicts from TOOL_SCHEMAS.

        Returns:
            List of types.FunctionDeclaration ready for GenerateContentConfig.
        """
        declarations: list[types.FunctionDeclaration] = []

        for schema in tool_schemas:
            name = schema.get("name")
            description = schema.get("description", "")
            input_schema = schema.get("input_schema", {})

            if not name:
                continue

            properties_raw: dict[str, Any] = input_schema.get("properties", {})
            required: list[str] = input_schema.get("required", [])

            parameters_schema = types.Schema(
                type=types.Type.OBJECT,
                properties={
                    prop_name: self._convert_property(prop_def)
                    for prop_name, prop_def in properties_raw.items()
                },
                required=required,
            )

            declarations.append(
                types.FunctionDeclaration(
                    name=name,
                    description=description,
                    parameters=parameters_schema,
                )
            )

        return declarations

    def _convert_property(self, prop_def: dict[str, Any]) -> types.Schema:
        """Convert a single JSON Schema property dict to a Gemini Schema object.

        Args:
            prop_def: Single property definition from input_schema.properties.

        Returns:
            types.Schema instance.
        """
        type_map: dict[str, types.Type] = {
            "string": types.Type.STRING,
            "integer": types.Type.INTEGER,
            "number": types.Type.NUMBER,
            "boolean": types.Type.BOOLEAN,
            "array": types.Type.ARRAY,
            "object": types.Type.OBJECT,
        }

        raw_type = prop_def.get("type", "string")
        gemini_type = type_map.get(raw_type, types.Type.STRING)
        description = prop_def.get("description", "")
        enum_values: list[str] | None = prop_def.get("enum")

        return types.Schema(
            type=gemini_type,
            description=description,
            enum=enum_values,
        )
