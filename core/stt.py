"""STTEngine — faster-whisper speech-to-text integration.

Transcribes raw PCM audio (int16, mono, 16 kHz) to Spanish text using
faster-whisper. The heavy model load and CPU-bound transcription run in
worker threads via asyncio.to_thread so the event loop stays free.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import numpy as np
from loguru import logger

from core.config_loader import WhisperConfig

if TYPE_CHECKING:
    # Import only for type-checking; real import is lazy inside __init__
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]

_SAMPLE_RATE: int = 16_000
_LANGUAGE: str = "es"


class STTEngine:
    """Speech-to-text engine backed by faster-whisper.

    The WhisperModel is loaded once on first construction (lazy import so
    import-time overhead is zero even when faster-whisper is not installed).

    Args:
        config: WhisperConfig with model size and device.
    """

    def __init__(self, config: WhisperConfig) -> None:
        self._config = config
        self._model: Any = None  # faster_whisper.WhisperModel, set in _load_model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def transcribe(self, audio: bytes) -> str:
        """Transcribe raw PCM audio bytes to Spanish text.

        Args:
            audio: Raw PCM bytes — int16, mono, 16 kHz (from AudioCapture).

        Returns:
            Transcribed text string (may be empty if audio contains only noise).
        """
        if self._model is None:
            self._model = await asyncio.to_thread(self._load_model)

        return await asyncio.to_thread(self._transcribe_blocking, audio)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_model(self) -> "WhisperModel":
        """Load the WhisperModel — runs in a worker thread (slow first time)."""
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "faster-whisper is not installed. "
                "Run: pip install faster-whisper"
            ) from exc

        model_size = self._config.model
        device = self._config.device

        # CTranslate2 compute type: int8 is fastest on CPU, float16 on GPU
        if device == "cpu":
            compute_type = "int8"
        else:
            # rocm / cuda
            compute_type = "float16"

        logger.info(
            "Loading Whisper model '{}' on device='{}' compute_type='{}'",
            model_size,
            device,
            compute_type,
        )
        t0 = time.monotonic()
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        elapsed = time.monotonic() - t0
        logger.info("Whisper model loaded in {:.2f}s", elapsed)
        return model

    def _transcribe_blocking(self, audio: bytes) -> str:
        """CPU-bound transcription — runs in a worker thread."""
        # Convert raw int16 PCM → float32 in [-1, 1]
        pcm = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0

        if pcm.size == 0:
            logger.warning("STTEngine: received empty audio buffer")
            return ""

        duration = pcm.size / _SAMPLE_RATE
        logger.debug("STTEngine: transcribing {:.2f}s of audio", duration)

        t0 = time.monotonic()
        segments, info = self._model.transcribe(
            pcm,
            language=_LANGUAGE,
            vad_filter=True,          # Silero VAD — strips leading/trailing silence
            beam_size=5,
        )

        # segments is a generator — consume it all
        text_parts: list[str] = [seg.text.strip() for seg in segments]
        text = " ".join(part for part in text_parts if part)

        elapsed = time.monotonic() - t0
        logger.info(
            "STTEngine: transcribed in {:.2f}s | lang={} prob={:.2f} | '{}'",
            elapsed,
            info.language,
            info.language_probability,
            text or "<empty>",
        )
        return text
