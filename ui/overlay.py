"""JarvisOverlay stub — to be implemented with PyQt6.

The overlay is a frameless, always-on-top window that shows the
futuristic orb in the bottom-right corner of the screen.
"""

from __future__ import annotations

from core.config_loader import UIConfig


class JarvisOverlay:
    """Frameless PyQt6 overlay window with animated orb.

    Stub: all methods raise NotImplementedError until PyQt6 integration
    is implemented.
    """

    def __init__(self, config: UIConfig) -> None:
        self._config = config

    def show(self) -> None:
        """Make the overlay visible on screen.

        Raises:
            NotImplementedError: until PyQt6 is integrated.
        """
        raise NotImplementedError("JarvisOverlay not yet implemented")

    def hide(self) -> None:
        """Hide the overlay without destroying it.

        Raises:
            NotImplementedError: until PyQt6 is integrated.
        """
        raise NotImplementedError("JarvisOverlay not yet implemented")

    def set_state(self, state: str) -> None:
        """Change the orb animation state.

        Args:
            state: One of "idle", "listening", "thinking", "speaking".

        Raises:
            NotImplementedError: until PyQt6 is integrated.
        """
        raise NotImplementedError("JarvisOverlay not yet implemented")

    def show_transcription(self, text: str) -> None:
        """Display the transcribed user speech in the overlay.

        Args:
            text: The STT-transcribed user command.

        Raises:
            NotImplementedError: until PyQt6 is integrated.
        """
        raise NotImplementedError("JarvisOverlay not yet implemented")

    def show_response(self, text: str) -> None:
        """Display the LLM response text in the overlay.

        Args:
            text: The assistant's response text.

        Raises:
            NotImplementedError: until PyQt6 is integrated.
        """
        raise NotImplementedError("JarvisOverlay not yet implemented")
