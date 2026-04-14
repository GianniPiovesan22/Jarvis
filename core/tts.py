"""TTSEngine — Edge TTS integration for fast, high-quality speech synthesis.

Uses Microsoft Edge's neural TTS voices via the edge-tts library.
Audio is generated as MP3 and played with mpv (preferred) or ffplay.

speak()           — full text, waits for playback to finish
speak_streaming() — splits on sentence boundaries, lower first-word latency
"""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Final

from loguru import logger

from core.config_loader import TTSConfig

# Default voice: Argentine Spanish male
_DEFAULT_VOICE: Final[str] = "es-AR-TomasNeural"

# Regex that splits on sentence-ending punctuation followed by whitespace
_SENTENCE_RE: re.Pattern[str] = re.compile(r"(?<=[.!?;])\s+")


class TTSEngine:
    """Text-to-speech engine using Edge TTS (Microsoft neural voices).

    Args:
        config: TTSConfig with voice name and speed multiplier.
    """

    def __init__(self, config: TTSConfig) -> None:
        self._voice = config.voice if config.voice != "es_ES-davefx-high" else _DEFAULT_VOICE
        self._rate = _speed_to_rate(config.speed)
        self._player = _resolve_player()
        logger.debug(
            "TTSEngine: voice='{}' rate='{}' player='{}'",
            self._voice,
            self._rate,
            self._player,
        )

    async def speak(self, text: str) -> None:
        """Synthesize *text* and play it to completion."""
        if not text.strip():
            return
        t0 = time.monotonic()
        await self._synthesize_and_play(text)
        logger.info("TTS: spoke {:.2f}s | '{}'", time.monotonic() - t0, _truncate(text))

    async def speak_streaming(self, text: str) -> None:
        """Synthesize *text* sentence by sentence for lower start latency."""
        if not text.strip():
            return

        sentences = _split_sentences(text)
        logger.debug("TTS: streaming {} sentence(s)", len(sentences))

        t0 = time.monotonic()
        for sentence in sentences:
            if sentence.strip():
                await self._synthesize_and_play(sentence)

        logger.info(
            "TTS: streamed {} sentence(s) in {:.2f}s",
            len(sentences),
            time.monotonic() - t0,
        )

    async def _synthesize_and_play(self, text: str) -> None:
        """Generate audio with edge-tts and play it."""
        try:
            import edge_tts
        except ImportError:
            raise RuntimeError(
                "edge-tts not installed. Run: pip install edge-tts"
            )

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=self._voice,
                rate=self._rate,
            )
            await communicate.save(tmp_path)

            # Play the audio file
            await self._play_file(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def _play_file(self, path: str) -> None:
        """Play an audio file using the system player."""
        if self._player == "mpv":
            cmd = ["mpv", "--no-video", "--really-quiet", path]
        elif self._player == "ffplay":
            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]
        elif self._player == "pw-play":
            # pw-play can handle mp3 via pipewire
            cmd = ["pw-play", path]
        else:
            cmd = ["aplay", path]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()

        if proc.returncode != 0:
            logger.warning("Audio player '{}' exited with code {}", self._player, proc.returncode)


def _resolve_player() -> str:
    """Find the best available audio player."""
    for player in ("mpv", "ffplay", "pw-play", "aplay"):
        if shutil.which(player):
            return player
    raise RuntimeError(
        "No audio player found. Install mpv, ffplay, or pw-play."
    )


def _speed_to_rate(speed: float) -> str:
    """Convert speed multiplier (1.0=normal, 1.1=faster) to Edge TTS rate string."""
    # Edge TTS uses "+10%", "-20%", etc.
    pct = round((speed - 1.0) * 100)
    if pct >= 0:
        return f"+{pct}%"
    return f"{pct}%"


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on punctuation boundaries."""
    parts = _SENTENCE_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def _truncate(text: str, n: int = 60) -> str:
    """Truncate text for log lines."""
    return text[:n] + "…" if len(text) > n else text
