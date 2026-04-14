"""WakeWordDetector stub — to be implemented with openwakeword."""

from __future__ import annotations

from core.config_loader import WakeWordConfig


class WakeWordDetector:
    """Detects the wake word from the microphone stream.

    Stub: raises NotImplementedError until openwakeword integration
    is implemented.
    """

    def __init__(self, config: WakeWordConfig) -> None:
        self._config = config

    async def detect(self) -> bool:
        """Block until the wake word is detected.

        Returns:
            True when the wake word fires.

        Raises:
            NotImplementedError: until openwakeword is integrated.
        """
        raise NotImplementedError("WakeWordDetector not yet implemented")
