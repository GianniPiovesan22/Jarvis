"""TTSEngine stub — to be implemented with piper-tts."""

from __future__ import annotations

from core.config_loader import TTSConfig


class TTSEngine:
    """Text-to-speech engine using piper-tts.

    Stub: raises NotImplementedError until piper-tts integration
    is implemented.
    """

    def __init__(self, config: TTSConfig) -> None:
        self._config = config

    async def speak(self, text: str) -> None:
        """Synthesize and play text through the default audio output.

        Args:
            text: The text to speak aloud.

        Raises:
            NotImplementedError: until piper-tts is integrated.
        """
        raise NotImplementedError("TTSEngine not yet implemented")
