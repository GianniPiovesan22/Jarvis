"""TTSEngine — piper-tts CLI integration for PipeWire systems.

Pipes text through piper-tts and plays the raw audio with pw-play
(PipeWire native) falling back to aplay when pw-play is not available.

speak()           — full text, waits for playback to finish
speak_streaming() — splits on sentence boundaries, lower first-word latency
"""

from __future__ import annotations

import asyncio
import re
import shutil
import time
from typing import Final

from loguru import logger

from core.config_loader import TTSConfig

# piper output: 22050 Hz, mono, signed 16-bit little-endian
_PIPER_RATE: Final[int] = 22_050
_PIPER_CHANNELS: Final[int] = 1
_PIPER_FORMAT_APLAY: Final[str] = "S16_LE"

# Regex that splits on sentence-ending punctuation followed by whitespace
_SENTENCE_RE: re.Pattern[str] = re.compile(r"(?<=[.!?;])\s+")


class TTSEngine:
    """Text-to-speech engine using piper-tts subprocess.

    Args:
        config: TTSConfig with voice name and speed multiplier.
    """

    def __init__(self, config: TTSConfig) -> None:
        self._config = config
        # length_scale: lower = faster. speed 1.1 → ~0.91
        self._length_scale: float = round(1.0 / config.speed, 4)
        self._player_cmd: list[str] = _resolve_player()
        logger.debug(
            "TTSEngine: voice='{}' speed={} length_scale={} player={}",
            config.voice,
            config.speed,
            self._length_scale,
            self._player_cmd[0],
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def speak(self, text: str) -> None:
        """Synthesize *text* and play it to completion.

        Args:
            text: Plain text to speak (no SSML).
        """
        if not text.strip():
            return
        t0 = time.monotonic()
        await self._run_pipeline(text)
        logger.info("TTSEngine: spoke {:.2f}s | '{}'", time.monotonic() - t0, _truncate(text))

    async def speak_streaming(self, text: str) -> None:
        """Synthesize *text* sentence by sentence for lower start latency.

        Each sentence is synthesised and played before the next starts.
        The first word of the response is heard sooner than with speak().

        Args:
            text: Plain text to speak.
        """
        if not text.strip():
            return

        sentences = _split_sentences(text)
        logger.debug("TTSEngine: streaming {} sentence(s)", len(sentences))

        t0 = time.monotonic()
        for sentence in sentences:
            if sentence.strip():
                await self._run_pipeline(sentence)

        logger.info(
            "TTSEngine: streamed {} sentence(s) in {:.2f}s",
            len(sentences),
            time.monotonic() - t0,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_pipeline(self, text: str) -> None:
        """Run: echo text | piper --output_raw | pw-play (or aplay)."""
        piper_cmd = _build_piper_cmd(self._config.voice, self._length_scale)
        player_cmd = self._player_cmd

        logger.debug("TTSEngine: synthesising '{}'", _truncate(text))

        try:
            # piper reads from stdin, writes raw PCM to stdout
            piper_proc = await asyncio.create_subprocess_exec(
                *piper_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # player reads raw PCM from stdin
            player_proc = await asyncio.create_subprocess_exec(
                *player_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )

            # Send text to piper, collect PCM, forward to player
            piper_stdout, piper_stderr = await piper_proc.communicate(
                input=text.encode("utf-8")
            )

            if piper_proc.returncode != 0:
                logger.error(
                    "piper exited with code {}: {}",
                    piper_proc.returncode,
                    piper_stderr.decode(errors="replace").strip(),
                )
                player_proc.stdin.close()  # type: ignore[union-attr]
                await player_proc.wait()
                return

            # Feed PCM to the player
            player_stdout, player_stderr = await player_proc.communicate(
                input=piper_stdout
            )

            if player_proc.returncode != 0:
                logger.error(
                    "{} exited with code {}: {}",
                    player_cmd[0],
                    player_proc.returncode,
                    player_stderr.decode(errors="replace").strip(),
                )

        except FileNotFoundError as exc:
            raise RuntimeError(
                f"TTS pipeline binary not found: {exc}. "
                "Install piper-tts and ensure pw-play or aplay is available."
            ) from exc


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _resolve_player() -> list[str]:
    """Return the play command to use, preferring pw-play over aplay."""
    if shutil.which("pw-play"):
        return [
            "pw-play",
            f"--rate={_PIPER_RATE}",
            f"--channels={_PIPER_CHANNELS}",
            "--format=s16",
            "-",
        ]
    if shutil.which("aplay"):
        logger.warning("pw-play not found — falling back to aplay")
        return [
            "aplay",
            f"--rate={_PIPER_RATE}",
            f"--channels={_PIPER_CHANNELS}",
            f"--format={_PIPER_FORMAT_APLAY}",
            "-",
        ]
    raise RuntimeError(
        "No audio player found. Install pw-play (pipewire-pulse) or aplay (alsa-utils)."
    )


def _build_piper_cmd(voice: str, length_scale: float) -> list[str]:
    """Build the piper CLI invocation."""
    if not shutil.which("piper"):
        raise RuntimeError(
            "piper-tts is not installed or not on PATH. "
            "See: https://github.com/rhasspy/piper"
        )
    return [
        "piper",
        "--model", voice,
        "--output_raw",
        "--length_scale", str(length_scale),
    ]


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on punctuation boundaries."""
    parts = _SENTENCE_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def _truncate(text: str, n: int = 60) -> str:
    """Truncate text for log lines."""
    return text[:n] + "…" if len(text) > n else text
