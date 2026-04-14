"""WaveformWidget stub — to be implemented with PyQt6 QPainter."""

from __future__ import annotations


class WaveformWidget:
    """Animated waveform widget for the Jarvis overlay.

    Visualizes audio input levels during listening state.

    Stub: raises NotImplementedError until PyQt6 integration
    is implemented.
    """

    def update_levels(self, levels: list[float]) -> None:
        """Update the waveform with new audio level data.

        Args:
            levels: List of normalized float values (0.0–1.0) per frequency band.

        Raises:
            NotImplementedError: until PyQt6 is integrated.
        """
        raise NotImplementedError("WaveformWidget not yet implemented")
