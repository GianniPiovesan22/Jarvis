"""
JARVIS — Entry point.

Wires all components together and runs the main interaction loop.

Supports TWO modes:
  - Voice mode (default): wake word → audio → STT → LLM → TTS + UI overlay
  - Text mode (--no-ui / --text-mode): text input loop, no audio, no UI

Use --force-local / --force-claude / --force-gemini to override LLM routing.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from core.config_loader import load_config

# ---------------------------------------------------------------------------
# PID file — written on startup so scripts/trigger.sh can find us
# ---------------------------------------------------------------------------

_PID_FILE = Path("/tmp/jarvis.pid")


def _write_pid() -> None:
    _PID_FILE.write_text(str(os.getpid()))
    logger.debug("PID {} written to {}", os.getpid(), _PID_FILE)


def _remove_pid() -> None:
    try:
        _PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


from core.dispatcher import ToolDispatcher
from core.llm_claude import ClaudeClient
from core.llm_gemini import GeminiClient
from core.llm_ollama import OllamaClient
from core.llm_router import LLMRouter, RouteTarget
from core.protocols import LLMResponse, LLMProvider, ToolResult
from memory.db import MemoryDB
from tools import TOOL_REGISTRY, TOOL_SCHEMAS


# ---------------------------------------------------------------------------
# Interaction handler (shared by both modes)
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

    # TTS — gracefully skip if not available
    try:
        await tts.speak(response.text)
    except (NotImplementedError, RuntimeError) as e:
        logger.debug("TTS skipped: {}", e)

    # Persist the turn to memory
    memory.save_turn("user", text, session_id)
    memory.save_turn(
        "assistant", response.text, session_id, model_used=response.model_used
    )

    return response


# ---------------------------------------------------------------------------
# JarvisEngine — async pipeline in background thread, emits Qt signals
# ---------------------------------------------------------------------------


def _try_import_pyqt6() -> bool:
    """Return True if PyQt6 is available."""
    try:
        import PyQt6.QtCore  # noqa: F401
        return True
    except ImportError:
        return False


def _try_import_audio_deps() -> bool:
    """Return True if all audio deps (sounddevice, numpy) are available."""
    try:
        import sounddevice  # noqa: F401
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


class JarvisEngine:
    """Runs the async voice pipeline in a background thread.

    Communicates with the Qt UI via signal callbacks registered at init time.
    Using plain callables (not QObject/pyqtSignal) keeps this class importable
    even when PyQt6 is not installed.

    Callbacks are invoked from the background asyncio thread — the caller is
    responsible for thread-safe dispatch (Qt signals handle this automatically
    when connected to overlay slots).
    """

    def __init__(
        self,
        config: Any,
        router: LLMRouter,
        llm_map: dict[str, LLMProvider],
        dispatcher: ToolDispatcher,
        tts: Any,
        stt: Any,
        audio_capture: Any,
        wake_word: Any,
        memory: MemoryDB,
        session_id: str,
        force_target: RouteTarget | None,
        *,
        on_state_changed: Any = None,       # callable(str)
        on_transcription: Any = None,       # callable(str)
        on_response: Any = None,            # callable(str)
        on_show: Any = None,                # callable() — show overlay
        on_hide: Any = None,                # callable() — hide overlay
    ) -> None:
        self._config = config
        self._router = router
        self._llm_map = llm_map
        self._dispatcher = dispatcher
        self._tts = tts
        self._stt = stt
        self._audio_capture = audio_capture
        self._wake_word = wake_word
        self._memory = memory
        self._session_id = session_id
        self._force_target = force_target

        # UI callbacks (may be None in headless mode)
        self._on_state_changed = on_state_changed
        self._on_transcription = on_transcription
        self._on_response = on_response
        self._on_show = on_show
        self._on_hide = on_hide

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = threading.Event()

        # Gate: only process one wake word at a time
        self._processing = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the async pipeline loop in a background daemon thread."""
        self._thread = threading.Thread(
            target=self._run_loop,
            name="jarvis-engine",
            daemon=True,
        )
        self._thread.start()
        logger.info("JarvisEngine started in background thread")

    def stop(self) -> None:
        """Signal the engine to stop and wait for the thread to exit."""
        self._stop_event.set()
        if self._wake_word is not None:
            self._wake_word.stop()
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("JarvisEngine stopped")

    # ------------------------------------------------------------------
    # Internal — background thread entry point
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Entry point for the background thread — owns its asyncio event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._main_loop())
        except Exception:
            logger.exception("JarvisEngine: unhandled exception in main loop")
        finally:
            loop.close()
            logger.debug("JarvisEngine: event loop closed")

    async def _main_loop(self) -> None:
        """Main engine loop — wake word is optional, SIGUSR1 (Super+J) is primary."""
        self._emit_state("idle")

        # Try wake word — if it fails, continue without it (SIGUSR1 still works)
        if self._wake_word is not None:
            try:
                def _wake_callback() -> None:
                    if self._processing.is_set():
                        return
                    if self._loop is not None:
                        self._loop.call_soon_threadsafe(
                            lambda: asyncio.ensure_future(self._handle_wake_word())
                        )

                await self._wake_word.start_listening(_wake_callback)
                logger.info("JarvisEngine: wake word active + SIGUSR1 hotkey ready")
            except Exception:
                logger.warning("JarvisEngine: wake word failed to start — using SIGUSR1 (Super+J) only")
                self._wake_word = None
        else:
            logger.info("JarvisEngine: no wake word — using SIGUSR1 (Super+J) only")

        # Keep the loop alive until stop is requested
        while not self._stop_event.is_set():
            await asyncio.sleep(0.1)

        if self._wake_word is not None:
            self._wake_word.stop()

    async def _handle_wake_word(self) -> None:
        """Full pipeline: capture → STT → LLM → TTS → reset to idle."""
        if self._processing.is_set():
            return
        self._processing.set()
        self._wake_word.pause()  # stop listening while we process

        try:
            # ---- 0. Show overlay ----
            if self._on_show:
                self._on_show()

            # ---- 1. Listening: capture audio ----
            logger.info("Wake word detected — starting audio capture")
            self._emit_state("listening")

            try:
                audio: bytes = await self._audio_capture.capture_until_silence()
                logger.info("JarvisEngine: audio captured — {} bytes", len(audio))
            except Exception:
                logger.exception("JarvisEngine: audio capture failed")
                self._emit_state("error")
                await asyncio.sleep(2.0)
                self._emit_state("idle")
                return

            # ---- 2. Processing: STT ----
            self._emit_state("processing")

            try:
                text: str = await self._stt.transcribe(audio)
                logger.info("JarvisEngine: STT result → {!r}", text)
            except Exception:
                logger.exception("JarvisEngine: STT transcription failed")
                self._emit_state("error")
                await asyncio.sleep(2.0)
                self._emit_state("idle")
                return

            if not text.strip():
                logger.warning("JarvisEngine: STT returned empty text — nothing to process")
                self._emit_state("idle")
                return

            logger.info("JarvisEngine: transcribed → {!r}", text)
            if self._on_transcription:
                self._on_transcription(text)

            # ---- 3. LLM + tools ----
            try:
                response = await handle_interaction(
                    text,
                    self._router,
                    self._llm_map,
                    self._dispatcher,
                    # Pass a no-op TTS here — we handle TTS ourselves below
                    # so we control timing and UI state transitions
                    _NoOpTTS(),
                    self._memory,
                    self._session_id,
                    self._force_target,
                )
            except Exception as exc:
                logger.exception(
                    "JarvisEngine: LLM interaction failed — {}: {}",
                    type(exc).__name__, exc,
                )
                self._emit_state("error")
                await asyncio.sleep(2.0)
                self._emit_state("idle")
                return

            # ---- 4. Speaking: TTS ----
            self._emit_state("speaking")
            if self._on_response:
                self._on_response(response.text)

            try:
                await self._tts.speak(response.text)
            except (NotImplementedError, Exception):
                logger.warning("JarvisEngine: TTS speak failed or not implemented")

            # ---- 5. Cooldown before going back to sleep ----
            await asyncio.sleep(3.0)

        finally:
            self._emit_state("idle")
            if self._on_hide:
                self._on_hide()
            self._processing.clear()
            # Extra cooldown before resuming wake word to avoid self-trigger.
            # Wrapped in shield so a CancelledError doesn't skip the resume().
            try:
                await asyncio.shield(asyncio.sleep(1.0))
            except asyncio.CancelledError:
                pass
            self._wake_word.resume()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emit_state(self, state: str) -> None:
        logger.debug("JarvisEngine: state → {}", state)
        if self._on_state_changed:
            self._on_state_changed(state)


class _NoOpTTS:
    """Drop-in TTS that does nothing — used to skip TTS inside handle_interaction."""

    async def speak(self, text: str) -> None:  # noqa: ARG002
        pass


# ---------------------------------------------------------------------------
# Voice mode bootstrap
# ---------------------------------------------------------------------------


def _init_audio_components(config: Any) -> tuple[Any, Any, Any, Any]:
    """Try to initialize wake word, audio capture, STT, and TTS.

    Returns (wake_word, audio_capture, stt, tts) — or raises on failure.
    Any ImportError from missing deps propagates to the caller.
    """
    from core.audio_capture import AudioCapture
    from core.stt import STTEngine
    from core.tts import TTSEngine
    from core.wake_word import WakeWordDetector

    wake_word = WakeWordDetector(config.wake_word)
    audio_capture = AudioCapture()
    stt = STTEngine(config.whisper)
    tts = TTSEngine(config.tts)
    return wake_word, audio_capture, stt, tts


def _run_voice_mode(
    config: Any,
    router: LLMRouter,
    llm_map: dict[str, LLMProvider],
    dispatcher: ToolDispatcher,
    memory: MemoryDB,
    session_id: str,
    force_target: RouteTarget | None,
) -> None:
    """Bootstrap and run full voice + UI mode. Blocks until quit."""
    from PyQt6.QtWidgets import QApplication

    from ui.overlay import JarvisOverlay
    from ui.tray import SystemTray

    # Must create QApplication before any other Qt objects
    app = QApplication(sys.argv)
    app.setApplicationName("jarvis-overlay")
    app.setDesktopFileName("jarvis-overlay")
    app.setQuitOnLastWindowClosed(False)  # keep alive when overlay is hidden

    overlay = JarvisOverlay(config.ui)
    # Start HIDDEN — only show when wake word detected

    tray = SystemTray(overlay)
    tray.show()

    # Wire engine signals → overlay (thread-safe: overlay.set_state emits
    # internal Qt signals via pyqtSignal, which crosses threads safely)
    wake_word, audio_capture, stt, tts = _init_audio_components(config)

    engine = JarvisEngine(
        config=config,
        router=router,
        llm_map=llm_map,
        dispatcher=dispatcher,
        tts=tts,
        stt=stt,
        audio_capture=audio_capture,
        wake_word=wake_word,
        memory=memory,
        session_id=session_id,
        force_target=force_target,
        on_state_changed=lambda s: (overlay.set_state(s), tray.update_state(s)),
        on_transcription=overlay.show_transcription,
        on_response=overlay.show_response,
        on_show=overlay.show_overlay,
        on_hide=overlay.hide_overlay,
    )

    # Handle Ctrl+C cleanly: stop engine then quit Qt
    def _handle_sigint(*_: Any) -> None:
        logger.info("SIGINT received — shutting down")
        _remove_pid()
        engine.stop()
        app.quit()

    # SIGUSR1: keyboard shortcut trigger (Super+J via scripts/trigger.sh)
    def _handle_sigusr1(*_: Any) -> None:
        logger.info("SIGUSR1 received — keyboard trigger activated")
        if engine._loop is not None and engine._loop.is_running():
            engine._loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(engine._handle_wake_word())
            )

    signal.signal(signal.SIGINT, _handle_sigint)
    signal.signal(signal.SIGUSR1, _handle_sigusr1)

    # Write PID so scripts/trigger.sh can find us
    _write_pid()

    engine.start()

    logger.info(
        "Jarvis voice mode running — waiting for wake word | hotkey: kill -SIGUSR1 $(cat /tmp/jarvis.pid)"
    )
    exit_code = app.exec()
    engine.stop()
    _remove_pid()
    sys.exit(exit_code)


# ---------------------------------------------------------------------------
# Text mode
# ---------------------------------------------------------------------------


async def _text_loop(
    router: LLMRouter,
    llm_map: dict[str, LLMProvider],
    dispatcher: ToolDispatcher,
    tts: Any,
    memory: MemoryDB,
    session_id: str,
    force_target: RouteTarget | None,
) -> None:
    """Classic text-input interaction loop (no audio, no UI)."""
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    """Parse args, init shared components, then branch to voice or text mode."""
    parser = argparse.ArgumentParser(
        description="JARVIS — Asistente de IA Local",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            "  python main.py                    # modo voz completo\n"
            "  python main.py --no-ui            # modo texto headless\n"
            "  python main.py --text-mode        # alias de --no-ui\n"
            "  python main.py --force-local      # todo a Ollama\n"
            "  python main.py --force-claude     # todo a claude-sonnet\n"
            "  python main.py --force-gemini     # todo a gemini-flash\n"
            "  python main.py --test-tts 'Hola'  # probar TTS y salir\n"
            "  python main.py --test-stt         # probar STT y salir\n"
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
        help="Ejecutar en modo texto headless (sin overlay PyQt6)",
    )
    parser.add_argument(
        "--text-mode",
        action="store_true",
        help="Alias de --no-ui — forzar modo texto",
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
    parser.add_argument(
        "--trigger",
        action="store_true",
        help="Enviar SIGUSR1 al proceso Jarvis corriendo y salir (hotkey trigger)",
    )
    parser.add_argument(
        "--listen-once",
        action="store_true",
        help="Capturar audio una vez, procesar y salir (sin wake word)",
    )
    args = parser.parse_args()

    # --trigger: send SIGUSR1 to the running Jarvis and exit immediately
    if args.trigger:
        if not _PID_FILE.exists():
            print("Jarvis is not running (no PID file at /tmp/jarvis.pid)", file=sys.stderr)
            sys.exit(1)
        pid = int(_PID_FILE.read_text().strip())
        try:
            os.kill(pid, signal.SIGUSR1)
            logger.info("SIGUSR1 sent to Jarvis PID {}", pid)
        except ProcessLookupError:
            print(f"Jarvis process {pid} not found — stale PID file", file=sys.stderr)
            _remove_pid()
            sys.exit(1)
        return

    # Resolve LLM force target
    force_target: RouteTarget | None = None
    if args.force_local:
        force_target = "local"
    elif args.force_claude:
        force_target = "claude_sonnet"
    elif args.force_gemini:
        force_target = "gemini_flash"

    config = load_config(args.config)
    logger.info("Jarvis starting — profile: {}", config.profile_name)

    # ------------------------------------------------------------------
    # Shared components (both modes)
    # ------------------------------------------------------------------
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

        stt_engine = STTEngine(config.whisper)
        audio_capture = AudioCapture()
        try:
            print("Grabando audio… hablá ahora.")
            audio = await audio_capture.capture_until_silence()
            text = await stt_engine.transcribe(audio)
            print(f"Transcripción: {text!r}")
        except NotImplementedError:
            print("STT / captura de audio no implementado todavía.")
        return

    if args.listen_once:
        logger.info("listen-once mode — skipping wake word, capturing audio directly")
        from core.audio_capture import AudioCapture
        from core.stt import STTEngine

        stt_engine = STTEngine(config.whisper)
        audio_capture = AudioCapture()
        try:
            logger.info("Capturing audio…")
            audio = await audio_capture.capture_until_silence()
            logger.info("Audio captured: {} bytes", len(audio))
            text = await stt_engine.transcribe(audio)
            logger.info("Transcription: {!r}", text)
            if not text.strip():
                logger.warning("Empty transcription — nothing to process")
                return
            response = await handle_interaction(
                text, router, llm_map, dispatcher, tts, memory, session_id, force_target
            )
            print(f"\nJARVIS: {response.text}\n")
        except NotImplementedError as e:
            logger.error("listen-once: component not implemented: {}", e)
        return

    # ------------------------------------------------------------------
    # Mode selection: voice vs text
    # ------------------------------------------------------------------

    text_mode_requested = args.no_ui or args.text_mode

    if not text_mode_requested:
        # Try to bring up full voice + UI mode, degrading gracefully
        pyqt6_ok = _try_import_pyqt6()
        audio_ok = _try_import_audio_deps()

        if not pyqt6_ok:
            logger.warning(
                "PyQt6 not installed — falling back to text mode. "
                "Install with: pip install PyQt6"
            )
            text_mode_requested = True
        elif not audio_ok:
            logger.warning(
                "Audio deps (sounddevice/numpy) not installed — falling back to text mode. "
                "Install with: pip install sounddevice numpy"
            )
            text_mode_requested = True

    if not text_mode_requested:
        # Voice mode: this call blocks (runs Qt event loop) and never returns
        # normally — it exits the process when the user quits.
        # We exit the asyncio.run() context by calling sys.exit() inside.
        _run_voice_mode(
            config=config,
            router=router,
            llm_map=llm_map,
            dispatcher=dispatcher,
            memory=memory,
            session_id=session_id,
            force_target=force_target,
        )
        # _run_voice_mode calls sys.exit() — code below is unreachable in voice mode
        return  # pragma: no cover

    # Text mode
    logger.info("Running in text mode (no UI, no wake word)")
    await _text_loop(
        router=router,
        llm_map=llm_map,
        dispatcher=dispatcher,
        tts=tts,
        memory=memory,
        session_id=session_id,
        force_target=force_target,
    )


if __name__ == "__main__":
    asyncio.run(main())
