"""WakeWordDetector — openwakeword + sounddevice integration.

Listens continuously on the microphone using sounddevice (PipeWire-compatible),
feeds 80ms chunks to openwakeword, and fires a callback when confidence
exceeds the configured threshold.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path
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


class WakeWordDetector:
    """Detects a wake word from the microphone using openwakeword.

    Runs a blocking audio loop in a background thread so the async
    event loop stays free. When confidence > threshold, calls callback().
    """

    def __init__(self, config: WakeWordConfig) -> None:
        self._config = config
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._model: Any = None
        self._paused = threading.Event()  # when set, detection is paused

    async def start_listening(self, callback: Callable[[], None]) -> None:
        """Start continuous wake word detection in a background thread."""
        self._model = await asyncio.to_thread(self._load_model)

        self._stop_event.clear()
        self._paused.clear()
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

    def pause(self) -> None:
        """Pause detection (while Jarvis is processing/speaking)."""
        self._paused.set()

    def resume(self) -> None:
        """Resume detection after pause."""
        self._paused.clear()

    def _load_model(self) -> Any:
        """Load the openwakeword model."""
        try:
            import openwakeword  # type: ignore[import-untyped]
            from openwakeword.model import Model  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "openwakeword is not installed. Run: pip install openwakeword"
            ) from exc

        # Try custom model path first
        custom_path = Path(self._config.model_path)
        if custom_path.exists():
            logger.info("Loading custom wake word model: {}", custom_path)
            return Model(wakeword_model_paths=[str(custom_path)])

        # Find bundled hey_jarvis model in openwakeword package
        pkg_dir = Path(openwakeword.__file__).parent
        bundled = pkg_dir / "resources" / "models" / "hey_jarvis_v0.1.onnx"
        if bundled.exists():
            logger.info("Loading bundled hey_jarvis model: {}", bundled)
            return Model(wakeword_model_paths=[str(bundled)])

        # Try any bundled model as fallback
        models_dir = pkg_dir / "resources" / "models"
        if models_dir.exists():
            for onnx in sorted(models_dir.glob("*.onnx")):
                if onnx.name in ("embedding_model.onnx", "melspectrogram.onnx", "silero_vad.onnx"):
                    continue  # skip infrastructure models
                logger.warning("hey_jarvis not found, falling back to: {}", onnx.name)
                return Model(wakeword_model_paths=[str(onnx)])

        raise RuntimeError(
            f"No wake word model available. "
            f"Custom path '{self._config.model_path}' not found and no bundled models found."
        )

    def _detection_loop(self, callback: Callable[[], None]) -> None:
        """Blocking loop: read mic chunks, feed to openwakeword, fire callback."""
        logger.debug("Wake word detection loop starting")

        audio_buffer: list[np.ndarray] = []

        def _audio_callback(
            indata: np.ndarray,
            frames: int,
            time_info: Any,
            status: sd.CallbackFlags,
        ) -> None:
            if status:
                logger.warning("sounddevice status: {}", status)
            audio_buffer.append(indata[:, 0].copy())

        try:
            with sd.InputStream(
                samplerate=_SAMPLE_RATE,
                channels=_CHANNELS,
                dtype=_DTYPE,
                blocksize=_CHUNK_SIZE,
                callback=_audio_callback,
            ):
                logger.info("Microphone open — listening for wake word ('Hey Jarvis')")
                while not self._stop_event.is_set():
                    # If paused (Jarvis is processing), drain buffer and wait
                    if self._paused.is_set():
                        audio_buffer.clear()
                        self._stop_event.wait(timeout=0.05)
                        continue

                    if not audio_buffer:
                        self._stop_event.wait(timeout=0.01)
                        continue

                    chunk = audio_buffer.pop(0)
                    predictions = self._model.predict(chunk)

                    for model_name, score_val in predictions.items():
                        score = float(score_val)
                        if score > 0.05:
                            logger.debug(
                                "Wake word '{}' confidence: {:.3f}",
                                model_name, score,
                            )
                        if score >= self._config.threshold:
                            logger.info(
                                ">>> WAKE WORD DETECTED! confidence={:.3f} <<<",
                                score,
                            )
                            callback()
                            # Pause briefly to avoid double-firing
                            self._stop_event.wait(timeout=2.0)
                            # Reset the model's prediction buffer
                            self._model.reset()
                            break

        except Exception:
            logger.exception("Wake word detection loop crashed")
