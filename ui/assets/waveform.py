"""Waveform utilities for Jarvis audio visualization.

The main waveform animation lives inside OrbWidget (ui/overlay.py) as part
of the mouth drawing. This module provides:

- WaveformData: a lightweight rolling buffer for real-time audio levels
- WaveformWidget: a standalone bar-chart widget (usable outside the orb
  if a larger visualization is ever needed)

Both are optional extras — the orb works without them.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Sequence

from loguru import logger

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QPainter, QPainterPath
    from PyQt6.QtWidgets import QSizePolicy, QWidget

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


# ---------------------------------------------------------------------------
# WaveformData — rolling buffer, no Qt dependency
# ---------------------------------------------------------------------------


class WaveformData:
    """Thread-safe rolling buffer for normalized audio level values (0.0–1.0).

    Used to decouple audio capture from UI updates. The audio thread calls
    push(), the UI thread reads snapshot().

    Args:
        size: Number of levels to keep (one per "band" or time step).
    """

    def __init__(self, size: int = 32) -> None:
        self._size = size
        self._buf: deque[float] = deque([0.0] * size, maxlen=size)

    def push(self, level: float) -> None:
        """Append a new level value, discarding the oldest."""
        self._buf.append(max(0.0, min(1.0, level)))

    def push_bands(self, levels: Sequence[float]) -> None:
        """Append multiple band values at once (e.g. FFT bands)."""
        for v in levels:
            self._buf.append(max(0.0, min(1.0, v)))

    def snapshot(self) -> list[float]:
        """Return a copy of the current buffer for rendering."""
        return list(self._buf)

    @property
    def peak(self) -> float:
        """Current maximum level in the buffer."""
        return max(self._buf) if self._buf else 0.0

    @property
    def rms(self) -> float:
        """Root-mean-square of current buffer."""
        if not self._buf:
            return 0.0
        return math.sqrt(sum(v * v for v in self._buf) / len(self._buf))


# ---------------------------------------------------------------------------
# WaveformWidget — optional standalone Qt bar visualizer
# ---------------------------------------------------------------------------


class WaveformWidget(QWidget):
    """Animated equalizer-style waveform widget.

    Renders normalized audio levels as vertical bars in the JARVIS color
    scheme. Used as a standalone widget — the orb draws its own mouth
    animation internally.

    Args:
        bars:      Number of equalizer bars to display.
        parent:    Qt parent widget.
    """

    _BAR_COLOR = QColor("#00c8ff")    # cyan (matches C_PRIMARY)
    _BAR_COLOR_PEAK = QColor("#00ff99")  # green flash at peaks
    _BG_COLOR = QColor(0, 0, 0, 0)   # transparent

    def __init__(self, bars: int = 16, parent: "QWidget | None" = None) -> None:
        if not _HAS_QT:
            raise ImportError(
                "PyQt6 is required for WaveformWidget.\n"
                "Install it with: pip install PyQt6"
            )
        super().__init__(parent)
        self._bars = bars
        self._levels: list[float] = [0.0] * bars
        self._peak_levels: list[float] = [0.0] * bars
        self._peak_decay = 0.02  # decay per paint call

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(30)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_levels(self, levels: list[float]) -> None:
        """Update the waveform with new audio level data.

        Args:
            levels: List of normalized float values (0.0–1.0) per band.
                    If fewer values than bars, remaining bars fade to 0.
                    If more, they are averaged into the bar count.
        """
        n = len(levels)
        if n == 0:
            self._levels = [0.0] * self._bars
        elif n == self._bars:
            self._levels = [max(0.0, min(1.0, v)) for v in levels]
        elif n < self._bars:
            # Pad with zeros
            self._levels = [max(0.0, min(1.0, v)) for v in levels] + [0.0] * (self._bars - n)
        else:
            # Downsample: average groups
            chunk = n / self._bars
            result = []
            for i in range(self._bars):
                start = int(i * chunk)
                end = int((i + 1) * chunk)
                group = levels[start:end]
                avg = sum(group) / len(group) if group else 0.0
                result.append(max(0.0, min(1.0, avg)))
            self._levels = result

        # Track peaks
        for i, v in enumerate(self._levels):
            if v > self._peak_levels[i]:
                self._peak_levels[i] = v

        self.update()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        if not _HAS_QT:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        if w == 0 or h == 0 or self._bars == 0:
            p.end()
            return

        gap = max(1.0, w * 0.04)
        bar_w = (w - gap * (self._bars - 1)) / self._bars

        for i, level in enumerate(self._levels):
            bar_h = max(2.0, level * h)
            x = i * (bar_w + gap)
            y = h - bar_h

            # Bar color: green at peak, cyan otherwise
            if self._peak_levels[i] > 0.85:
                color = self._BAR_COLOR_PEAK
            else:
                color = self._BAR_COLOR

            # Glow effect (wider, lower opacity)
            glow = QColor(color.red(), color.green(), color.blue(), 60)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(
                x - 1, y - 1, bar_w + 2, bar_h + 2, 2.0, 2.0
            )

            # Main bar
            p.setBrush(color)
            p.drawRoundedRect(x, y, bar_w, bar_h, 1.5, 1.5)

            # Peak decay
            self._peak_levels[i] = max(0.0, self._peak_levels[i] - self._peak_decay)

        p.end()
