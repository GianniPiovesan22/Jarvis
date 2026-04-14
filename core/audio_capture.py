"""AudioCapture stub — to be implemented with PyAudio or sounddevice."""

from __future__ import annotations


class AudioCapture:
    """Captures audio from the microphone until silence is detected.

    Stub: raises NotImplementedError until audio pipeline is implemented.
    """

    async def capture_until_silence(self) -> bytes:
        """Record audio from the default input device until silence.

        Returns:
            Raw PCM audio bytes.

        Raises:
            NotImplementedError: until audio capture is implemented.
        """
        raise NotImplementedError("AudioCapture not yet implemented")
