"""AudioCapture — sounddevice-based mic recording with silence detection.

Records audio from the default input device until:
  - RMS amplitude stays below *silence_threshold* for *silence_duration* seconds, OR
  - *max_duration* seconds have elapsed (safety ceiling).

Returns raw PCM bytes (int16, mono, 16 kHz) — the format faster-whisper accepts
after converting to float32.
"""

from __future__ import annotations

import asyncio
import time

import numpy as np
import sounddevice as sd
from loguru import logger

_SAMPLE_RATE: int = 16_000
_CHANNELS: int = 1
_DTYPE: str = "int16"
# Block size: ~30 ms chunks for responsive silence detection
_BLOCKSIZE: int = 480


class AudioCapture:
    """Records mic audio until silence is detected.

    Args:
        sample_rate:       Audio sample rate in Hz (default 16 kHz for Whisper).
        silence_threshold: RMS amplitude below which audio is considered silence.
                           Range 0–1 (int16 normalised). 0.01 ≈ quiet room.
        silence_duration:  Seconds of continuous silence before stopping.
        max_duration:      Hard ceiling on recording length (seconds).
    """

    def __init__(
        self,
        sample_rate: int = _SAMPLE_RATE,
        silence_threshold: float = 0.01,
        silence_duration: float = 1.5,
        max_duration: float = 15.0,
    ) -> None:
        self._sample_rate = sample_rate
        self._silence_threshold = silence_threshold
        self._silence_duration = silence_duration
        self._max_duration = max_duration

    async def capture_until_silence(self) -> bytes:
        """Record from the microphone until silence is detected.

        Runs the blocking sounddevice capture in a thread via
        asyncio.to_thread so the event loop stays free.

        Returns:
            Raw PCM bytes — int16, mono, 16 kHz.
        """
        return await asyncio.to_thread(self._record_blocking)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _record_blocking(self) -> bytes:
        """Blocking recording loop — runs in a worker thread."""
        logger.debug(
            "AudioCapture: starting (silence_threshold={}, silence_duration={}s, max={}s)",
            self._silence_threshold,
            self._silence_duration,
            self._max_duration,
        )

        chunks: list[np.ndarray] = []
        silence_start: float | None = None
        recording_start = time.monotonic()

        with sd.InputStream(
            samplerate=self._sample_rate,
            channels=_CHANNELS,
            dtype=_DTYPE,
            blocksize=_BLOCKSIZE,
        ) as stream:
            logger.info("AudioCapture: recording…")

            while True:
                elapsed = time.monotonic() - recording_start

                if elapsed >= self._max_duration:
                    logger.warning(
                        "AudioCapture: hit max duration ({:.1f}s), stopping", elapsed
                    )
                    break

                data, overflowed = stream.read(_BLOCKSIZE)
                if overflowed:
                    logger.warning("AudioCapture: input overflow")

                chunk = data[:, 0]  # flatten (frames, 1) → (frames,)
                chunks.append(chunk.copy())

                rms = _rms(chunk)

                if rms < self._silence_threshold:
                    if silence_start is None:
                        silence_start = time.monotonic()
                    elif time.monotonic() - silence_start >= self._silence_duration:
                        logger.debug(
                            "AudioCapture: silence detected after {:.2f}s of quiet",
                            time.monotonic() - silence_start,
                        )
                        break
                else:
                    silence_start = None

        duration = time.monotonic() - recording_start
        audio = np.concatenate(chunks, axis=0)
        raw_bytes = audio.tobytes()

        logger.info(
            "AudioCapture: captured {:.2f}s of audio ({} bytes)",
            duration,
            len(raw_bytes),
        )
        return raw_bytes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rms(chunk: np.ndarray) -> float:
    """Root mean square of an int16 chunk, normalised to [0, 1]."""
    if chunk.size == 0:
        return 0.0
    # Normalise int16 → float32 in [-1, 1] before computing RMS
    normalised = chunk.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(normalised ** 2)))
