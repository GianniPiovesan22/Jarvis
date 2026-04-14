"""WakeWordDetector — openwakeword + sounddevice integration.

Listens continuously on the microphone using sounddevice (PipeWire-compatible),
feeds 80ms chunks to openwakeword, and fires a callback when confidence
exceeds the configured threshold.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import Any

import numpy as np
import sounddevice as sd
from loguru import logger

from core.config_loader import WakeWordConfig

# openwakeword chunk spec: 1280 samples at 16 kHz = 80 ms
_SAMPLE_RATE: int = 16_000
_CHUNK_SIZE: int = 1_280
_CHANNELS: int = 1
_DTYPE: str = "int16"

# Built-in model names to try when no custom model file is found
_BUILTIN_MODELS: list[str] = ["hey_jarvis", "alexa"]


class WakeWordDetector:
    """Detects a wake word from the microphone using openwakeword.

    Runs a blocking audio loop in a background thread so the async
    event loop stays free. When confidence > threshold, calls callback().

    Usage::

        detector = WakeWordDetector(config)
        await detector.start_listening(on_wake_word)
        # ... later ...
        detector.stop()
    """

    def __init__(self, config: WakeWordConfig) -> None:
        self._config = config
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._model: Any = None  # openwakeword.Model, loaded lazily

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_listening(self, callback: Callable[[], None]) -> None:
        """Start continuous wake word detection in a background thread.

        The callback is invoked (from the background thread) each time the
        wake word fires. Use asyncio.get_event_loop().call_soon_threadsafe()
        if you need to schedule coroutines from within it.

        Args:
            callback: Zero-argument callable fired on each detection.
        """
        self._model = await asyncio.to_thread(self._load_model)

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._detection_loop,
            args=(callback,),
            daemon=True,
            name="wake-word-detector",
        )
        self._thread.start()
        logger.info("WakeWordDetector started (threshold={})", self._config.threshold)

    def stop(self) -> None:
        """Signal the background thread to stop and wait for it to exit."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        logger.info("WakeWordDetector stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self) -> Any:
        """Load the openwakeword model (runs in a thread — may be slow)."""
        try:
            import openwakeword  # type: ignore[import-untyped]
            from openwakeword.model import Model  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "openwakeword is not installed. "
                "Run: pip install openwakeword"
            ) from exc

        model_path = self._config.model_path

        # Try the configured custom ONNX model file first
        import os

        if os.path.exists(model_path):
            logger.info("Loading custom wake word model: {}", model_path)
            return Model(wakeword_models=[model_path], inference_framework="onnx")

        # Fall back to openwakeword built-in models
        for name in _BUILTIN_MODELS:
            try:
                logger.warning(
                    "Custom model not found at '{}', trying built-in '{}'",
                    model_path,
                    name,
                )
                # openwakeword downloads / caches built-in models by name
                openwakeword.utils.download_models([name])
                return Model(wakeword_models=[name], inference_framework="onnx")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Built-in model '{}' failed: {}", name, exc)

        raise RuntimeError(
            f"No wake word model available. "
            f"Custom path '{model_path}' not found and built-in fallbacks failed. "
            f"Run: python scripts/setup_wake_word.py"
        )

    def _detection_loop(self, callback: Callable[[], None]) -> None:
        """Blocking loop: read mic chunks, feed to openwakeword, fire callback."""
        logger.debug("Wake word detection loop starting")

        # Buffer for accumulating samples between openwakeword calls
        audio_buffer: list[np.ndarray] = []

        def _audio_callback(
            indata: np.ndarray,
            frames: int,
            time_info: Any,
            status: sd.CallbackFlags,
        ) -> None:
            if status:
                logger.warning("sounddevice status: {}", status)
            # indata shape: (frames, channels) — flatten to 1D int16
            audio_buffer.append(indata[:, 0].copy())

        try:
            with sd.InputStream(
                samplerate=_SAMPLE_RATE,
                channels=_CHANNELS,
                dtype=_DTYPE,
                blocksize=_CHUNK_SIZE,
                callback=_audio_callback,
            ):
                logger.info("Microphone open — listening for wake word")
                while not self._stop_event.is_set():
                    if not audio_buffer:
                        self._stop_event.wait(timeout=0.01)
                        continue

                    chunk = audio_buffer.pop(0)
                    # openwakeword expects a 1D int16 numpy array
                    predictions: dict[str, np.ndarray] = self._model.predict(chunk)

                    for model_name, scores in predictions.items():
                        score: float = float(scores[-1]) if hasattr(scores, "__len__") else float(scores)
                        if score > 0.05:
                            logger.debug(
                                "Wake word '{}' confidence: {:.3f} (threshold={})",
                                model_name,
                                score,
                                self._config.threshold,
                            )
                        if score >= self._config.threshold:
                            logger.info(
                                "Wake word DETECTED! model='{}' confidence={:.3f}",
                                model_name,
                                score,
                            )
                            callback()
                            # Brief pause to avoid double-firing on the same utterance
                            self._stop_event.wait(timeout=1.0)
                            break

        except Exception as exc:
            logger.exception("Wake word detection loop crashed: {}", exc)
