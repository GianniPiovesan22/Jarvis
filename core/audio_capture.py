"""AudioCapture — sounddevice-based mic recording with adaptive silence detection.

Records audio from the default input device until:
  - RMS amplitude drops back to ~ambient level for *silence_duration* seconds, OR
  - *max_duration* seconds have elapsed (safety ceiling).

Calibrates ambient noise level automatically in the first 0.3s of recording
so it works in noisy environments (music, fans, etc.).

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
_BLOCKSIZE: int = 480  # ~30ms chunks


class AudioCapture:
    """Records mic audio until silence is detected.

    Uses adaptive silence detection: measures ambient noise for the first
    0.3 seconds, then considers "silence" as anything within 1.5x of that
    ambient level. This makes it work with background music/noise.
    """

    def __init__(
        self,
        sample_rate: int = _SAMPLE_RATE,
        silence_duration: float = 1.5,
        max_duration: float = 10.0,
        calibration_time: float = 0.3,
    ) -> None:
        self._sample_rate = sample_rate
        self._silence_duration = silence_duration
        self._max_duration = max_duration
        self._calibration_time = calibration_time

    async def capture_until_silence(self) -> bytes:
        """Record from the microphone until silence is detected."""
        return await asyncio.to_thread(self._record_blocking)

    def _record_blocking(self) -> bytes:
        """Blocking recording loop with adaptive silence detection."""
        chunks: list[np.ndarray] = []
        calibration_rms: list[float] = []
        ambient_threshold: float | None = None
        silence_start: float | None = None
        speech_detected = False
        recording_start = time.monotonic()

        logger.debug(
            "AudioCapture: starting (silence_duration={}s, max={}s, calibration={}s)",
            self._silence_duration,
            self._max_duration,
            self._calibration_time,
        )

        with sd.InputStream(
            samplerate=self._sample_rate,
            channels=_CHANNELS,
            dtype=_DTYPE,
            blocksize=_BLOCKSIZE,
        ) as stream:
            logger.info("AudioCapture: recording — speak now!")

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

                chunk = data[:, 0]
                chunks.append(chunk.copy())
                rms = _rms(chunk)

                # Phase 1: calibrate ambient noise (first 0.3s)
                if elapsed < self._calibration_time:
                    calibration_rms.append(rms)
                    continue

                # Set threshold once after calibration
                if ambient_threshold is None:
                    if calibration_rms:
                        avg_ambient = sum(calibration_rms) / len(calibration_rms)
                        # Threshold = 2x ambient (need to speak louder than background)
                        ambient_threshold = max(avg_ambient * 2.0, 0.005)
                    else:
                        ambient_threshold = 0.01
                    logger.info(
                        "AudioCapture: ambient RMS={:.4f}, silence threshold={:.4f}",
                        avg_ambient if calibration_rms else 0,
                        ambient_threshold,
                    )

                # Phase 2: detect speech then silence
                if rms >= ambient_threshold:
                    speech_detected = True
                    silence_start = None
                else:
                    if speech_detected:
                        # Speech was happening, now it's quiet
                        if silence_start is None:
                            silence_start = time.monotonic()
                        elif time.monotonic() - silence_start >= self._silence_duration:
                            logger.debug(
                                "AudioCapture: silence after speech ({:.1f}s quiet)",
                                time.monotonic() - silence_start,
                            )
                            break

        duration = time.monotonic() - recording_start
        audio = np.concatenate(chunks, axis=0)
        raw_bytes = audio.tobytes()

        logger.info(
            "AudioCapture: captured {:.2f}s ({} bytes, speech_detected={})",
            duration, len(raw_bytes), speech_detected,
        )
        return raw_bytes


def _rms(chunk: np.ndarray) -> float:
    """Root mean square of an int16 chunk, normalised to [0, 1]."""
    if chunk.size == 0:
        return 0.0
    normalised = chunk.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(normalised ** 2)))
