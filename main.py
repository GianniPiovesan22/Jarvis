"""
JARVIS — Entry point.

Wires all components together and runs the main interaction loop.
Currently runs in text-input mode (wake word + audio pipeline are stubs).
Use --force-local / --force-claude / --force-gemini to override routing.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from typing import Any

from loguru import logger

from core.config_loader import load_config
from core.dispatcher import ToolDispatcher
from core.llm_claude import ClaudeClient
from core.llm_gemini import GeminiClient
from core.llm_ollama import OllamaClient
from core.llm_router import LLMRouter, RouteTarget
from core.protocols import LLMResponse, LLMProvider, ToolResult
from memory.db import MemoryDB
from tools import TOOL_REGISTRY, TOOL_SCHEMAS


# ---------------------------------------------------------------------------
# Interaction handler
# ---------------------------------------------------------------------------


async def handle_interaction(
    text: str,
    router: LLMRouter,
    llm_map: dict[str, LLMProvider],
    dispatcher: ToolDispatcher,
    tts: Any,
    memory: MemoryDB,
    session_id: str,
    force_target: RouteTarget | None = None,
) -> LLMResponse:
    """Handle a single user interaction end-to-end.

    Routes the text to the appropriate LLM, executes any tool calls,
    speaks the response (if TTS is available), and persists the turn
    to SQLite.

    Args:
        text:         User's raw input text.
        router:       LLMRouter for automatic target selection.
        llm_map:      Map of RouteTarget → LLMProvider instance.
        dispatcher:   ToolDispatcher for executing tool calls.
        tts:          TTSEngine instance (may raise NotImplementedError).
        memory:       MemoryDB instance for persistence.
        session_id:   Current session identifier.
        force_target: If set, bypasses router and uses this target directly.

    Returns:
        The final LLMResponse (after tool calls resolved, if any).
    """
    target: RouteTarget = router.route(text, force=force_target)
    logger.info("Routing to: {}", target)

    llm = llm_map[target]
    history = memory.get_history(session_id)

    # ClaudeClient.chat() accepts an extra model_target kwarg
    if target in ("claude_haiku", "claude_sonnet"):
        response = await llm.chat(  # type: ignore[call-arg]
            text, history, TOOL_SCHEMAS, model_target=target
        )
    else:
        response = await llm.chat(text, history, TOOL_SCHEMAS)

    # Handle tool calls
    if response.tool_calls:
        tool_results: list[ToolResult] = []
        for tc in response.tool_calls:
            result = await dispatcher.execute(tc)
            memory.log_action(
                session_id,
                tc.name,
                tc.arguments,
                result.result,
                result.result.get("success", False),
            )
            tool_results.append(result)
        response = await llm.complete_with_result(tool_results)

    # TTS — stub raises NotImplementedError, which we silently swallow
    try:
        await tts.speak(response.text)
    except NotImplementedError:
        pass

    # Persist the turn to memory
    memory.save_turn("user", text, session_id)
    memory.save_turn(
        "assistant", response.text, session_id, model_used=response.model_used
    )

    return response


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    """Initialize all components and run the main text interaction loop."""
    parser = argparse.ArgumentParser(
        description="JARVIS — Asistente de IA Local",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python main.py                    # modo automático\n"
            "  python main.py --force-local       # todo a Ollama\n"
            "  python main.py --force-claude      # todo a claude-sonnet\n"
            "  python main.py --force-gemini      # todo a gemini-flash\n"
            "  python main.py --no-ui             # sin interfaz gráfica\n"
        ),
    )
    parser.add_argument(
        "--force-local",
        action="store_true",
        help="Forzar todas las consultas al LLM local (Ollama)",
    )
    parser.add_argument(
        "--force-claude",
        action="store_true",
        help="Forzar todas las consultas a Claude Sonnet",
    )
    parser.add_argument(
        "--force-gemini",
        action="store_true",
        help="Forzar todas las consultas a Gemini Flash",
    )
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Ejecutar en modo headless (sin overlay PyQt6)",
    )
    parser.add_argument(
        "--test-tts",
        type=str,
        metavar="TEXT",
        help="Probar síntesis de voz con el texto dado y salir",
    )
    parser.add_argument(
        "--test-stt",
        action="store_true",
        help="Probar transcripción de audio (STT) y salir",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Ruta al archivo de configuración (default: config.yaml)",
    )
    args = parser.parse_args()

    # Resolve force target
    force_target: RouteTarget | None = None
    if args.force_local:
        force_target = "local"
    elif args.force_claude:
        force_target = "claude_sonnet"
    elif args.force_gemini:
        force_target = "gemini_flash"

    config = load_config(args.config)
    logger.info("Jarvis starting — profile: {}", config.profile_name)

    # Initialize all components
    memory = MemoryDB(config.memory.db_path)
    router = LLMRouter(config.llm)
    ollama = OllamaClient(config.llm)
    claude = ClaudeClient(config.llm)
    gemini = GeminiClient(config.llm)
    dispatcher = ToolDispatcher(TOOL_REGISTRY)

    from core.tts import TTSEngine

    tts = TTSEngine(config.tts)

    llm_map: dict[str, LLMProvider] = {
        "local": ollama,
        "claude_haiku": claude,
        "claude_sonnet": claude,
        "gemini_flash": gemini,
    }

    session_id = str(uuid.uuid4())
    logger.info("Session: {}", session_id)

    if force_target:
        logger.info("Force mode: all requests → {}", force_target)

    # ------------------------------------------------------------------
    # Special modes: --test-tts / --test-stt
    # ------------------------------------------------------------------

    if args.test_tts:
        logger.info("TTS test mode — text={!r}", args.test_tts)
        try:
            await tts.speak(args.test_tts)
            print(f"TTS: {args.test_tts!r}")
        except NotImplementedError:
            print("TTS no implementado todavía.")
        return

    if args.test_stt:
        logger.info("STT test mode")
        from core.audio_capture import AudioCapture
        from core.stt import STTEngine

        stt = STTEngine(config.whisper)
        audio_capture = AudioCapture()
        try:
            print("Grabando audio… hablá ahora.")
            audio = await audio_capture.capture_until_silence()
            text = await stt.transcribe(audio)
            print(f"Transcripción: {text!r}")
        except NotImplementedError:
            print("STT / captura de audio no implementado todavía.")
        return

    # ------------------------------------------------------------------
    # Main text input loop
    # ------------------------------------------------------------------

    print("JARVIS v1.0 — Escribí tu comando (o 'salir' para terminar)")
    print(
        f"Modo: {'forzado → ' + force_target if force_target else 'router automático'}"
    )
    print()

    while True:
        try:
            text: str = await asyncio.to_thread(input, ">>> ")
        except (EOFError, KeyboardInterrupt):
            break

        text = text.strip()
        if not text or text.lower() in ("salir", "exit", "quit"):
            break

        response = await handle_interaction(
            text,
            router,
            llm_map,
            dispatcher,
            tts,
            memory,
            session_id,
            force_target,
        )
        print(f"\nJARVIS: {response.text}\n")

    logger.info("Jarvis shutting down")


if __name__ == "__main__":
    asyncio.run(main())
