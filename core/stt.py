"""STTEngine stub — to be implemented with faster-whisper."""

from __future__ import annotations

from core.config_loader import WhisperConfig


class STTEngine:
    """Speech-to-text engine using faster-whisper.

    Stub: raises NotImplementedError until faster-whisper integration
    is implemented.
    """

    def __init__(self, config: WhisperConfig) -> None:
        self._config = config

    async def transcribe(self, audio: bytes) -> str:
        """Transcribe raw PCM audio bytes to text.

        Args:
            audio: Raw PCM audio bytes from AudioCapture.

        Returns:
            Transcribed text string.

        Raises:
            NotImplementedError: until faster-whisper is integrated.
        """
        raise NotImplementedError("STTEngine not yet implemented")
