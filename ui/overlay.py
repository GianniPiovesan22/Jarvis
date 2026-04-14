"""JarvisOverlay — PyQt6 futuristic robot orb overlay.

Ports the HTML/Canvas prototype (jarvis_robot_v1.html) to QPainter.
Frameless, always-on-top, transparent window. Positioned bottom-right.

States: idle, listening, processing, speaking, error
"""

from __future__ import annotations

import math
import random
import time
from typing import Callable

from loguru import logger

try:
    from PyQt6.QtCore import (
        QEasingCurve,
        QPoint,
        QPointF,
        QPropertyAnimation,
        QRect,
        QRectF,
        QSize,
        Qt,
        QTimer,
        pyqtSignal,
        pyqtSlot,
    )
    from PyQt6.QtGui import (
        QBrush,
        QColor,
        QConicalGradient,
        QFont,
        QFontMetrics,
        QLinearGradient,
        QPainter,
        QPainterPath,
        QPen,
        QPixmap,
        QRadialGradient,
    )
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsOpacityEffect,
        QLabel,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:
    raise ImportError(
        "PyQt6 is required for the Jarvis UI overlay.\n"
        "Install it with: pip install PyQt6\n"
        f"Original error: {exc}"
    ) from exc

from core.config_loader import UIConfig

# ---------------------------------------------------------------------------
# Constants — ported from HTML prototype
# ---------------------------------------------------------------------------

STATES = frozenset({"idle", "listening", "processing", "speaking", "error"})

# Colors matching the HTML prototype exactly
C_BG = QColor("#060c14")
C_FACE_BASE = QColor("#0a1826")
C_PRIMARY = QColor("#00c8ff")       # cyan
C_GREEN = QColor("#00ff99")         # green (speaking)
C_METAL1 = QColor("#1a3040")
C_METAL2 = QColor("#0e2030")
C_NOSE = QColor("#0c1e2e")
C_DIM = QColor(0, 200, 255, 46)    # rgba(0,200,255,0.18)

# State pip colors
PIP_COLORS: dict[str, QColor] = {
    "idle":       QColor("#2a4050"),
    "listening":  QColor("#00ff99"),
    "processing": QColor("#00c8ff"),
    "speaking":   QColor("#ffaa44"),
    "error":      QColor("#ff3366"),
}

# Animation timing (ms)
FRAME_INTERVAL = 16        # ~60 fps
BLINK_CLOSE_MS = 80.0
BLINK_OPEN_MS = 80.0
BLINK_MIN_WAIT = 2000
BLINK_MAX_WAIT = 6000

# Ring parameters: (inset_px, color_rgba, speed_deg_per_ms, reverse, dashed)
RINGS = [
    (14, QColor(0, 200, 255, 51),  360 / 6000,   False, False),  # ring-1: 6s
    (22, QColor(0, 255, 153, 31),  360 / 10000,  True,  True),   # ring-2: 10s dashed
    (30, QColor(0, 200, 255, 18),  360 / 18000,  False, False),  # ring-3: 18s
]


# ---------------------------------------------------------------------------
# OrbWidget — the robot face (ported from HTML canvas draw functions)
# ---------------------------------------------------------------------------

class OrbWidget(QWidget):
    """Custom-painted robot orb face. 176x176 logical canvas, scaled to orb_size."""

    def __init__(self, orb_size: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._orb_size = orb_size

        # Logical canvas size from HTML prototype
        self._W = 176
        self._H = 176
        self._cx = self._W / 2
        self._cy = self._H / 2
        self._R = 82.0

        # Animation state
        self._t: float = 0.0           # elapsed ms (cumulative)
        self._state: str = "idle"
        self._audio_level: float = 0.0
        self._target_audio: float = 0.0

        # Blink state (0=open, 1=closing, 2=opening)
        self._blink_state: int = 0
        self._blink_progress: float = 0.0
        self._blink_t: float = 0.0
        self._next_blink: float = float(random.randint(2000, 5000))

        # Ring angles (degrees)
        self._ring_angles: list[float] = [0.0, 0.0, 0.0]

        # Error pulse
        self._error_phase: float = 0.0

        self.setFixedSize(orb_size + 60, orb_size + 60)  # extra space for rings
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        self._state = state

    def tick(self, dt: float) -> None:
        """Advance animation by dt milliseconds."""
        self._t += dt

        # Audio level smoothing (lerp toward target)
        if self._state == "idle":
            self._target_audio = 0.0
        elif self._state == "listening":
            self._target_audio = 0.5 + math.sin(self._t * 0.003) * 0.4
        elif self._state == "processing":
            self._target_audio = 0.2
        elif self._state == "speaking":
            self._target_audio = 0.4 + math.sin(self._t * 0.005) * 0.5
        elif self._state == "error":
            self._target_audio = 0.3
            self._error_phase += dt * 0.005
        else:
            self._target_audio = 0.0

        self._audio_level += (self._target_audio - self._audio_level) * 0.08

        # Blink logic — same as HTML prototype
        if self._state != "processing":
            self._blink_t += dt
            if self._blink_state == 0 and self._blink_t > self._next_blink:
                self._blink_state = 1
                self._blink_progress = 0.0
                self._blink_t = 0.0
            if self._blink_state == 1:
                self._blink_progress += dt / BLINK_CLOSE_MS
                if self._blink_progress >= 1.0:
                    self._blink_state = 2
                    self._blink_progress = 0.0
            if self._blink_state == 2:
                self._blink_progress += dt / BLINK_OPEN_MS
                if self._blink_progress >= 1.0:
                    self._blink_state = 0
                    self._blink_progress = 0.0
                    self._next_blink = random.uniform(BLINK_MIN_WAIT, BLINK_MAX_WAIT)

        # Rotate rings
        for i, (_, _, speed, reverse, _) in enumerate(RINGS):
            delta = speed * dt
            if reverse:
                self._ring_angles[i] -= delta
            else:
                self._ring_angles[i] += delta

        self.update()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Scale from logical 176x176 canvas to actual widget center
        widget_cx = self.width() / 2
        widget_cy = self.height() / 2
        scale = self._orb_size / self._W

        # Draw rings first (behind the orb) — in widget coordinates
        self._draw_rings(p, widget_cx, widget_cy, scale)

        # Outer glow (pulsing radial gradient around the orb circle)
        self._draw_outer_glow(p, widget_cx, widget_cy, scale)

        # Draw the face canvas onto a pixmap, then stamp it
        # We work in a translated+scaled painter context
        p.save()
        p.translate(widget_cx - self._cx * scale, widget_cy - self._cy * scale)
        p.scale(scale, scale)
        self._draw_face(p)
        p.restore()

        p.end()

    # ------------------------------------------------------------------
    # Ring drawing (CSS rings ported to QPainter)
    # ------------------------------------------------------------------

    def _draw_rings(self, p: QPainter, cx: float, cy: float, scale: float) -> None:
        orb_r = self._R * scale

        for i, (inset_px, color, _speed, _rev, dashed) in enumerate(RINGS):
            ring_r = orb_r + inset_px * scale
            dot_r = ring_r  # dot sits at left edge of the ring

            angle_rad = math.radians(self._ring_angles[i])

            p.save()
            pen = QPen(color)
            pen.setWidthF(1.0)
            if dashed:
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(
                QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
            )

            # Dot on ring (ring-1 = cyan, ring-2 = green)
            if i < 2:
                dot_color = C_PRIMARY if i == 0 else C_GREEN
                dot_size = 5.0 * scale if i == 0 else 4.0 * scale

                # Dot orbits at ring_r distance from center
                dot_x = cx + ring_r * math.cos(angle_rad)
                dot_y = cy + ring_r * math.sin(angle_rad)

                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(dot_color)
                half = dot_size / 2
                p.drawEllipse(QRectF(dot_x - half, dot_y - half, dot_size, dot_size))

                # Glow effect — paint larger translucent circle behind dot
                glow = QColor(dot_color)
                glow.setAlpha(60)
                p.setBrush(glow)
                p.drawEllipse(QRectF(dot_x - half * 2, dot_y - half * 2, dot_size * 2, dot_size * 2))

            p.restore()

    def _draw_outer_glow(self, p: QPainter, cx: float, cy: float, scale: float) -> None:
        glow_phase = 0.5 + 0.5 * math.sin(self._t * 0.002)  # 0..1, 2.5s period
        glow_opacity = 0.6 + 0.4 * glow_phase
        glow_scale = 1.0 + 0.08 * glow_phase
        orb_r = self._R * scale * glow_scale

        grad = QRadialGradient(cx, cy, orb_r + 6 * scale)
        c1 = QColor(0, 200, 255, int(31 * glow_opacity))  # rgba(0,200,255,0.12)
        c2 = QColor(0, 0, 0, 0)
        grad.setColorAt(0.0, c1)
        grad.setColorAt(0.7, c2)
        grad.setColorAt(1.0, c2)

        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        r = orb_r + 6 * scale
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        p.restore()

    # ------------------------------------------------------------------
    # Face drawing (logical 176x176 coordinates — ported from JS)
    # ------------------------------------------------------------------

    def _draw_face(self, p: QPainter) -> None:
        cx, cy, R = self._cx, self._cy, self._R

        # --- Clip to circle ---
        clip_path = QPainterPath()
        clip_path.addEllipse(QPointF(cx, cy), R, R)
        p.setClipPath(clip_path)

        # --- Background radial gradient ---
        bg = QRadialGradient(cx, cy - 10, 10)
        bg.setFocalPoint(QPointF(cx, cy - 10))
        bg.setRadius(R)
        bg.setColorAt(0.0, QColor("#0e1e2e"))
        bg.setColorAt(1.0, QColor("#040810"))
        p.fillRect(QRectF(0, 0, self._W, self._H), QBrush(bg))

        # --- Hex grid ---
        self._draw_hex_grid(p)

        # --- Face panels ---
        self._draw_face_panels(p)

        # --- Eyes ---
        self._draw_eyes(p)

        # --- Mouth ---
        self._draw_mouth(p)

        # --- Forehead ---
        self._draw_forehead(p)

        # --- Overlay depth gradient ---
        ov = QRadialGradient(cx, cy, R)
        ov.setColorAt(0.4, QColor(0, 0, 0, 0))
        ov.setColorAt(1.0, QColor(0, 0, 0, 128))
        p.setClipping(False)
        p.fillRect(QRectF(0, 0, self._W, self._H), QBrush(ov))
        p.setClipPath(clip_path)

        # --- Rim light ---
        p.setClipping(False)
        rim_alpha = int((0.25 + self._audio_level * 0.4) * 255)
        if self._state == "error":
            # Error state: red rim pulsing
            pulse = 0.5 + 0.5 * math.sin(self._error_phase)
            rim_alpha = int((0.4 + 0.6 * pulse) * 255)
            rim_pen = QPen(QColor(255, 51, 102, rim_alpha))
        else:
            rim_pen = QPen(QColor(0, 200, 255, rim_alpha))
        rim_pen.setWidthF(1.5)
        p.setPen(rim_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R, R)

    def _draw_hex_grid(self, p: QPainter) -> None:
        """Subtle hex grid — opacity 0.06, cyan. Ported from drawHexGrid()."""
        p.save()
        p.setOpacity(0.06)
        pen = QPen(C_PRIMARY)
        pen.setWidthF(0.5)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        s = 14.0
        for row in range(-1, 14):
            for col in range(-1, 14):
                x = col * s * 1.73 + (row % 2) * s * 0.866
                y = row * s * 1.5
                path = QPainterPath()
                for vi in range(6):
                    a = math.radians(60 * vi - 30)
                    rx = x + s * 0.9 * math.cos(a)
                    ry = y + s * 0.9 * math.sin(a)
                    if vi == 0:
                        path.moveTo(rx, ry)
                    else:
                        path.lineTo(rx, ry)
                path.closeSubpath()
                p.drawPath(path)

        p.setOpacity(1.0)
        p.restore()

    def _draw_face_panels(self, p: QPainter) -> None:
        """Geometric face panels — ported from drawFacePanels()."""
        p.save()
        p.setOpacity(0.5)

        border_pen = QPen(QColor(0, 200, 255, 38))  # rgba(0,200,255,0.15)
        border_pen.setWidthF(0.8)

        def poly(points: list[tuple[float, float]], fill: QColor) -> None:
            path = QPainterPath()
            path.moveTo(*points[0])
            for pt in points[1:]:
                path.lineTo(*pt)
            path.closeSubpath()
            p.fillPath(path, fill)
            p.setPen(border_pen)
            p.drawPath(path)

        # Left cheek
        poly([(25, 75), (60, 65), (65, 115), (28, 120)], C_METAL1)
        # Right cheek
        poly([(151, 75), (116, 65), (111, 115), (148, 120)], C_METAL1)
        # Chin plate
        poly([(55, 120), (121, 120), (115, 148), (61, 148)], C_METAL2)
        # Nose bridge
        poly(
            [(self._cx - 8, 72), (self._cx + 8, 72),
             (self._cx + 5, 105), (self._cx - 5, 105)],
            C_NOSE,
        )

        p.setOpacity(1.0)
        p.restore()

    def _draw_forehead(self, p: QPainter) -> None:
        """Forehead panel + accent line + pip dots — ported from drawForehead()."""
        p.save()
        cx = self._cx

        # Forehead panel
        panel = QPainterPath()
        panel.moveTo(42, 45)
        panel.lineTo(134, 45)
        panel.lineTo(128, 70)
        panel.lineTo(48, 70)
        panel.closeSubpath()

        p.setOpacity(0.6)
        p.fillPath(panel, C_METAL2)
        panel_pen = QPen(QColor(0, 200, 255, 51))  # rgba(0,200,255,0.2)
        panel_pen.setWidthF(0.8)
        p.setPen(panel_pen)
        p.drawPath(panel)

        # Central accent line
        p.setOpacity(0.8)
        accent_pen = QPen(C_PRIMARY)
        accent_pen.setWidthF(1.5)
        p.setPen(accent_pen)
        # Shadow/glow via semi-transparent wider stroke
        glow_pen = QPen(QColor(0, 200, 255, 80))
        glow_pen.setWidthF(4.0)
        p.setPen(glow_pen)
        p.drawLine(QPointF(cx - 20, 52), QPointF(cx + 20, 52))
        p.setPen(accent_pen)
        p.drawLine(QPointF(cx - 20, 52), QPointF(cx + 20, 52))

        # Small pip dots
        p.setOpacity(0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C_PRIMARY)
        for ox in (-28, -10, 10, 28):
            p.drawEllipse(QPointF(cx + ox, 60), 1.5, 1.5)

        p.setOpacity(1.0)
        p.restore()

    def _ease_in_out(self, t: float) -> float:
        """Cubic ease-in-out."""
        if t < 0.5:
            return 2 * t * t
        return 1 - ((-2 * t + 2) ** 2) / 2

    def _draw_eyes(self, p: QPainter) -> None:
        """Eyes with blink, glow, pupil — ported from drawEyes()."""
        cx = self._cx
        eye_y = 90.0
        left_x = cx - 28
        right_x = cx + 28
        eye_w = 22.0
        eye_h = 10.0

        # Blink scale
        scale_y = 1.0
        if self._blink_state == 1:
            scale_y = 1.0 - self._ease_in_out(self._blink_progress)
        elif self._blink_state == 2:
            scale_y = self._ease_in_out(self._blink_progress)
        scale_y = max(scale_y, 0.01)  # never fully zero to avoid degenerate ellipses

        is_idle = self._state == "idle"
        alpha = 0.4 if is_idle else 1.0
        col = C_GREEN if self._state == "speaking" else C_PRIMARY
        col_glow_alpha = int(128 * alpha)
        shadow_blur = 4 if is_idle else int(12 + self._audio_level * 8)

        for ex in (left_x, right_x):
            p.save()

            # Eye socket (dark ellipse behind eye)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#020810"))
            p.drawEllipse(QPointF(ex, eye_y), eye_w + 3, (eye_h + 4) * scale_y)

            # Eye glow fill
            glow_fill = QColor(col)
            glow_fill.setAlpha(int(38 * alpha))  # 0.15 opacity
            p.setBrush(glow_fill)
            p.setOpacity(alpha * (0.7 + self._audio_level * 0.3))
            p.drawEllipse(QPointF(ex, eye_y), eye_w, eye_h * scale_y)

            # Main eye stroke with glow
            p.setOpacity(alpha)
            eye_pen = QPen(col)
            eye_pen.setWidthF(1.5)
            p.setPen(eye_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            # Draw glow (wider, lower opacity)
            glow_pen = QPen(QColor(col.red(), col.green(), col.blue(),
                                   min(255, shadow_blur * 8)))
            glow_pen.setWidthF(shadow_blur * 0.6)
            p.setPen(glow_pen)
            p.drawEllipse(QPointF(ex, eye_y), eye_w, eye_h * scale_y)
            # Sharp stroke on top
            p.setPen(eye_pen)
            p.drawEllipse(QPointF(ex, eye_y), eye_w, eye_h * scale_y)

            # Inner highlight arc (top half)
            highlight_pen = QPen(col)
            highlight_pen.setWidthF(1.0)
            p.setPen(highlight_pen)
            p.setOpacity(alpha * 0.4)
            arc_rect = QRectF(
                ex - eye_w * 0.5,
                eye_y - 1 - eye_h * 0.35 * scale_y,
                eye_w,
                eye_h * 0.35 * scale_y * 2,
            )
            # Draw arc from 0 to 180 degrees (upper half of ellipse)
            p.drawArc(arc_rect, 0 * 16, 180 * 16)

            # Pupil dot
            p.setOpacity(alpha * (0.8 + self._audio_level * 0.2))
            p.setPen(Qt.PenStyle.NoPen)
            pupil_color = QColor(col)
            p.setBrush(pupil_color)
            p.drawEllipse(QPointF(ex, eye_y), 3.0, 3.0 * scale_y)

            p.setOpacity(1.0)
            p.restore()

    def _draw_mouth(self, p: QPainter) -> None:
        """Mouth animation — ported from drawMouth()."""
        my = 128.0
        cx = self._cx
        is_idle = self._state == "idle"

        p.save()

        if is_idle:
            # Flat dim line
            pen = QPen(C_PRIMARY)
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.setOpacity(0.2)
            p.drawLine(QPointF(cx - 20, my), QPointF(cx + 20, my))
            p.setOpacity(1.0)
            p.restore()
            return

        p.setOpacity(0.9)

        if self._state == "speaking":
            # Equalizer bars — 9 bars animated
            bars = 9
            bw = 3.0
            gap = 3.0
            total_w = bars * (bw + gap) - gap
            start_x = cx - total_w / 2

            p.setPen(Qt.PenStyle.NoPen)
            for i in range(bars):
                bx = start_x + i * (bw + gap)
                phase = self._t * 0.003 + i * 0.6
                bh = (math.sin(phase) * 0.5 + 0.5) * 12 * (0.4 + self._audio_level * 0.6) + 3
                bar_rect = QRectF(bx, my - bh / 2, bw, bh)

                # Glow
                glow_brush = QColor(C_GREEN.red(), C_GREEN.green(), C_GREEN.blue(), 60)
                p.setBrush(glow_brush)
                p.drawRoundedRect(
                    QRectF(bx - 1, my - bh / 2 - 1, bw + 2, bh + 2), 1.5, 1.5
                )
                # Bar
                p.setBrush(C_GREEN)
                p.drawRoundedRect(bar_rect, 1.0, 1.0)

        elif self._state == "listening":
            # Animated sine wave
            path = QPainterPath()
            pts = 30
            for i in range(pts + 1):
                x = cx - 26 + (52.0 / pts) * i
                phase = self._t * 0.004 + i * 0.4
                y = my + math.sin(phase) * (3 + self._audio_level * 8)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)

            # Glow
            glow_pen = QPen(QColor(0, 200, 255, 80))
            glow_pen.setWidthF(3.0)
            p.setPen(glow_pen)
            p.drawPath(path)
            # Sharp stroke
            wave_pen = QPen(C_PRIMARY)
            wave_pen.setWidthF(1.5)
            p.setPen(wave_pen)
            p.drawPath(path)

        elif self._state in ("processing", "error"):
            # Scanning line
            base_pen = QPen(C_DIM)
            base_pen.setWidthF(1.0)
            p.setPen(base_pen)
            p.drawLine(QPointF(cx - 26, my), QPointF(cx + 26, my))

            # Scan position
            scan_x = cx - 26 + (self._t * 0.05) % 52
            scan_col = QColor("#ff3366") if self._state == "error" else C_PRIMARY

            glow_pen = QPen(QColor(scan_col.red(), scan_col.green(), scan_col.blue(), 80))
            glow_pen.setWidthF(4.0)
            p.setPen(glow_pen)
            p.drawLine(QPointF(scan_x - 4, my), QPointF(scan_x + 4, my))

            scan_pen = QPen(scan_col)
            scan_pen.setWidthF(2.0)
            p.setPen(scan_pen)
            p.drawLine(QPointF(scan_x - 4, my), QPointF(scan_x + 4, my))

        p.setOpacity(1.0)
        p.restore()


# ---------------------------------------------------------------------------
# StatusPip — small colored dot showing current state
# ---------------------------------------------------------------------------

class StatusPip(QWidget):
    """Small circle widget showing state color with glow."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = "idle"
        self.setFixedSize(9, 9)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_state(self, state: str) -> None:
        self._state = state
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = PIP_COLORS.get(self._state, PIP_COLORS["idle"])

        if self._state == "idle":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(QRectF(0.5, 0.5, 8, 8))
        else:
            # Glow
            glow = QRadialGradient(4.5, 4.5, 7)
            glow_c = QColor(color)
            glow_c.setAlpha(80)
            glow.setColorAt(0.0, glow_c)
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(glow))
            p.drawEllipse(QRectF(-2, -2, 13, 13))
            # Dot
            p.setBrush(color)
            p.drawEllipse(QRectF(0.5, 0.5, 8, 8))

        p.end()


# ---------------------------------------------------------------------------
# InfoBubble — text popup above the orb
# ---------------------------------------------------------------------------

class InfoBubble(QWidget):
    """Semi-transparent info bubble with typewriter animation.

    Shows transcript (dim) and response (bright) text.
    Hidden when IDLE.
    """

    _TYPEWRITER_INTERVAL = 35  # ms per character

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(240)

        self._transcript = ""
        self._response_full = ""
        self._response_visible = ""
        self._typewriter_pos = 0
        self._typewriter_active = False

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        self._transcript_label = QLabel("")
        self._transcript_label.setWordWrap(True)
        self._transcript_label.setStyleSheet(
            "color: #4a8a9a; font-size: 10px; letter-spacing: 0.3px;"
            "background: transparent; font-family: monospace;"
        )

        self._response_label = QLabel("")
        self._response_label.setWordWrap(True)
        self._response_label.setStyleSheet(
            "color: #c8e8f0; font-size: 12px; line-height: 1.5;"
            "background: transparent; font-family: monospace;"
        )

        layout.addWidget(self._transcript_label)
        layout.addWidget(self._response_label)

        # Typewriter timer
        self._tw_timer = QTimer(self)
        self._tw_timer.setInterval(self._TYPEWRITER_INTERVAL)
        self._tw_timer.timeout.connect(self._typewriter_tick)

        self.setVisible(False)

    def set_transcript(self, text: str) -> None:
        self._transcript = text
        self._transcript_label.setText(text)
        pass  # fixed size — no adjust

    def set_response(self, text: str, typewriter: bool = True) -> None:
        self._response_full = text
        if typewriter:
            self._typewriter_pos = 0
            self._response_visible = ""
            self._typewriter_active = True
            self._tw_timer.start()
        else:
            self._response_visible = text
            self._response_label.setText(text)
            self._tw_timer.stop()
        pass  # fixed size — no adjust

    @pyqtSlot()
    def _typewriter_tick(self) -> None:
        if self._typewriter_pos < len(self._response_full):
            self._typewriter_pos += 1
            self._response_visible = self._response_full[: self._typewriter_pos]
            self._response_label.setText(self._response_visible + "▌")
        else:
            self._response_label.setText(self._response_full)
            self._tw_timer.stop()
            self._typewriter_active = False
        pass  # fixed size — no adjust

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height() - 6)

        # Background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(5, 10, 18, 217))  # rgba(5,10,18,0.85)
        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)
        p.drawPath(path)

        # Border
        border_pen = QPen(QColor(0, 200, 255, 38))  # rgba(0,200,255,0.15)
        border_pen.setWidthF(1.0)
        p.setPen(border_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # Top gradient line
        top_grad = QLinearGradient(0, 0, self.width(), 0)
        top_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        top_grad.setColorAt(0.3, QColor(0, 200, 255, 153))
        top_grad.setColorAt(0.7, QColor(0, 255, 153, 153))
        top_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        top_pen = QPen(QBrush(top_grad), 1.5)
        p.setPen(top_pen)
        p.drawLine(QPointF(8, 1), QPointF(self.width() - 8, 1))

        # Arrow pointing down (bottom-right)
        arrow_x = self.width() - 22.0
        arrow_y = self.height() - 6.0
        arrow = QPainterPath()
        arrow.moveTo(arrow_x, arrow_y)
        arrow.lineTo(arrow_x + 10, arrow_y)
        arrow.lineTo(arrow_x + 5, arrow_y + 6)
        arrow.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(5, 10, 18, 217))
        p.drawPath(arrow)

        p.end()


# ---------------------------------------------------------------------------
# JarvisOverlay — main overlay window
# ---------------------------------------------------------------------------

class JarvisOverlay(QWidget):
    """Transparent overlay window with the JARVIS orb, positioned bottom-right.

    States: idle, listening, processing, speaking, error

    Thread-safe state changes via Qt signals.
    """

    # Signals for thread-safe updates from non-GUI threads
    state_changed = pyqtSignal(str)
    transcription_ready = pyqtSignal(str)
    response_ready = pyqtSignal(str)

    def __init__(self, config: UIConfig) -> None:
        # Ensure QApplication exists
        if QApplication.instance() is None:
            raise RuntimeError(
                "QApplication must be created before JarvisOverlay.\n"
                "Create it in main.py before instantiating JarvisOverlay."
            )

        super().__init__()
        self._config = config
        self._state = "idle"
        self._last_frame_time: float = time.monotonic() * 1000  # ms

        self._setup_window()
        self._build_ui()
        self._connect_signals()
        self._start_animation()

        # Load Hyprland window rules once at startup (before first show)
        _apply_hyprland_rules()

        logger.info("JarvisOverlay initialized — orb_size={}, state=idle", config.orb_size)

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowTitle("jarvis-overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # Don't show in taskbar
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowOpacity(self._config.opacity)

        # Position bottom-right with 28px margin (matching HTML)
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            orb_total = self._config.orb_size + 60  # rings extra space
            bubble_h = 80  # estimated bubble height
            total_h = bubble_h + 10 + orb_total  # gap between bubble and orb

            x = geom.right() - orb_total - 28
            y = geom.bottom() - total_h - 28

            self.move(x, y)

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _build_ui(self) -> None:
        orb_size = self._config.orb_size
        orb_total = orb_size + 60  # extra space for rings
        widget_w = max(orb_total, 240)  # wide enough for bubble
        bubble_h = 80
        widget_h = bubble_h + 10 + orb_total

        # Fixed size — no layout expansion
        self.setFixedSize(widget_w, widget_h)

        # Info bubble (above the orb) — positioned manually, no layout
        self._bubble = InfoBubble(self)
        self._bubble.move(widget_w - 240, 0)
        self._bubble.setVisible(False)

        # Orb container (orb + status pip)
        orb_container = QWidget(self)
        orb_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        orb_container.setFixedSize(orb_total, orb_total)
        orb_container.move(widget_w - orb_total, bubble_h + 10)

        # The orb itself
        self._orb = OrbWidget(orb_size, orb_container)
        self._orb.move(0, 0)

        # Status pip — bottom-right of the orb circle area
        self._pip = StatusPip(orb_container)
        pip_offset = orb_total // 2 + int(orb_size * 0.45)
        self._pip.move(pip_offset - 4, pip_offset - 4)

    def _connect_signals(self) -> None:
        self.state_changed.connect(self._on_state_changed)
        self.transcription_ready.connect(self._on_transcription)
        self.response_ready.connect(self._on_response)

    def _start_animation(self) -> None:
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(FRAME_INTERVAL)
        self._anim_timer.timeout.connect(self._animation_tick)
        self._anim_timer.start()

    # ------------------------------------------------------------------
    # Animation loop
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _animation_tick(self) -> None:
        now = time.monotonic() * 1000
        dt = now - self._last_frame_time
        self._last_frame_time = now
        dt = min(dt, 100.0)  # clamp to avoid huge jumps after suspend

        self._orb.tick(dt)

    # ------------------------------------------------------------------
    # Public API (thread-safe — emit signals from any thread)
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        """Change orb state. Thread-safe."""
        if state not in STATES:
            logger.warning("Unknown state '{}', ignoring", state)
            return
        self.state_changed.emit(state)

    def show_transcription(self, text: str) -> None:
        """Show user's transcribed text in the info bubble. Thread-safe."""
        self.transcription_ready.emit(text)

    def show_response(self, text: str) -> None:
        """Show Jarvis response in the info bubble with typewriter. Thread-safe."""
        self.response_ready.emit(text)

    def show_overlay(self) -> None:
        """Animate the overlay appearing (slide up from bottom)."""
        if not self.isVisible():
            self.show()

            # Slide-up animation via geometry
            screen = QApplication.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
                end_y = self.y()
                start_y = geom.bottom() + 20

                # Temporarily move below screen
                self.move(self.x(), start_y)
                self.show()

                self._slide_anim = QPropertyAnimation(self, b"pos")
                self._slide_anim.setDuration(500)
                self._slide_anim.setStartValue(QPoint(self.x(), start_y))
                self._slide_anim.setEndValue(QPoint(self.x(), end_y))
                self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                self._slide_anim.start()

    def hide_overlay(self) -> None:
        """Animate the overlay disappearing (slide down)."""
        if self.isVisible():
            screen = QApplication.primaryScreen()
            if screen:
                geom = screen.availableGeometry()
                end_y = geom.bottom() + 20

                self._slide_out_anim = QPropertyAnimation(self, b"pos")
                self._slide_out_anim.setDuration(400)
                self._slide_out_anim.setStartValue(QPoint(self.x(), self.y()))
                self._slide_out_anim.setEndValue(QPoint(self.x(), end_y))
                self._slide_out_anim.setEasingCurve(QEasingCurve.Type.InCubic)
                self._slide_out_anim.finished.connect(self.hide)
                self._slide_out_anim.start()

    # ------------------------------------------------------------------
    # Slot implementations (always called on GUI thread)
    # ------------------------------------------------------------------

    @pyqtSlot(str)
    def _on_state_changed(self, state: str) -> None:
        self._state = state
        self._orb.set_state(state)
        self._pip.set_state(state)
        logger.debug("Overlay state → {}", state)

        # Auto-show/hide bubble based on state
        if state == "idle":
            self._bubble.setVisible(False)
        else:
            self._bubble.setVisible(True)

    @pyqtSlot(str)
    def _on_transcription(self, text: str) -> None:
        self._bubble.set_transcript(text)
        self._bubble.setVisible(True)
        pass  # fixed size — no adjust

    @pyqtSlot(str)
    def _on_response(self, text: str) -> None:
        self._bubble.set_response(text, typewriter=True)
        self._bubble.setVisible(True)
        pass  # fixed size — no adjust


# ---------------------------------------------------------------------------
# Hyprland integration
# ---------------------------------------------------------------------------


def _apply_hyprland_rules() -> None:
    """Load static Hyprland window rules from scripts/hyprland-rules.conf.

    Uses ``hyprctl keyword source`` so rules are applied by the compositor
    before the window is even rendered, guaranteeing correct position/float/pin.
    Called ONCE at overlay init — not on every show().
    """
    import subprocess
    from pathlib import Path

    rules_path = Path(__file__).parent.parent / "scripts" / "hyprland-rules.conf"
    if not rules_path.exists():
        logger.warning("hyprland-rules.conf not found at {}", rules_path)
        return

    try:
        subprocess.run(
            ["hyprctl", "keyword", "source", str(rules_path.resolve())],
            capture_output=True,
            timeout=2,
        )
        logger.info("Hyprland rules loaded from {}", rules_path)
    except FileNotFoundError:
        pass  # Not on Hyprland
    except subprocess.TimeoutExpired:
        logger.warning("hyprctl timed out loading rules")
