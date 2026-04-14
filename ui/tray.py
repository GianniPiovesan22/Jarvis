"""SystemTray — PyQt6 QSystemTrayIcon for Jarvis.

Provides a minimal tray icon with context menu:
- Mostrar/Ocultar Jarvis
- Activar/Desactivar escucha
- Salir

The icon is a small colored circle generated with QPainter — no external
image files required.
"""

from __future__ import annotations

from loguru import logger

try:
    from PyQt6.QtCore import QSize, Qt, pyqtSlot
    from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
    from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
except ImportError as exc:
    raise ImportError(
        "PyQt6 is required for the Jarvis system tray.\n"
        "Install it with: pip install PyQt6\n"
        f"Original error: {exc}"
    ) from exc

from ui.overlay import JarvisOverlay

# State → icon color mapping
_ICON_COLORS: dict[str, QColor] = {
    "idle":       QColor("#1a4060"),   # dim blue — not active
    "listening":  QColor("#00ff99"),   # green
    "processing": QColor("#00c8ff"),   # cyan
    "speaking":   QColor("#ffaa44"),   # orange
    "error":      QColor("#ff3366"),   # red
}

_ICON_SIZE = 22  # pixels


def _make_icon(state: str) -> QIcon:
    """Generate a small colored circle icon for the given state."""
    color = _ICON_COLORS.get(state, _ICON_COLORS["idle"])
    px = QPixmap(QSize(_ICON_SIZE, _ICON_SIZE))
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    if state != "idle":
        # Outer glow ring
        glow = QColor(color)
        glow.setAlpha(60)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(1, 1, _ICON_SIZE - 2, _ICON_SIZE - 2)

    # Main circle
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawEllipse(4, 4, _ICON_SIZE - 8, _ICON_SIZE - 8)

    # Inner highlight
    highlight = QColor(255, 255, 255, 60)
    p.setBrush(highlight)
    p.drawEllipse(5, 5, (_ICON_SIZE - 8) // 2, (_ICON_SIZE - 8) // 2)

    p.end()
    return QIcon(px)


class SystemTray(QSystemTrayIcon):
    """System tray icon for Jarvis with state-aware icon and context menu."""

    def __init__(self, overlay: JarvisOverlay) -> None:
        super().__init__()
        self._overlay = overlay
        self._listening_active = True
        self._current_state = "idle"

        self.setIcon(_make_icon("idle"))
        self.setToolTip("Jarvis — Inactivo")

        self._build_menu()

        self.activated.connect(self._on_activated)
        logger.info("SystemTray initialized")

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        menu = QMenu()
        menu.setObjectName("jarvis-tray-menu")

        # Show/hide toggle
        self._toggle_action = menu.addAction("Mostrar Jarvis")
        self._toggle_action.triggered.connect(self._toggle_overlay)

        # Listening on/off toggle
        self._listen_action = menu.addAction("Desactivar escucha")
        self._listen_action.triggered.connect(self._toggle_listening)

        menu.addSeparator()

        # Quit
        quit_action = menu.addAction("Salir")
        quit_action.triggered.connect(self._quit)

        self.setContextMenu(menu)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_state(self, state: str) -> None:
        """Update tray icon and tooltip based on Jarvis state."""
        self._current_state = state
        self.setIcon(_make_icon(state))

        labels = {
            "idle":       "Jarvis — Inactivo",
            "listening":  "Jarvis — Escuchando···",
            "processing": "Jarvis — Procesando···",
            "speaking":   "Jarvis — Hablando",
            "error":      "Jarvis — Error",
        }
        self.setToolTip(labels.get(state, "Jarvis"))
        logger.debug("Tray state → {}", state)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @pyqtSlot()
    def _toggle_overlay(self) -> None:
        if self._overlay.isVisible():
            self._overlay.hide_overlay()
            self._toggle_action.setText("Mostrar Jarvis")
        else:
            self._overlay.show_overlay()
            self._toggle_action.setText("Ocultar Jarvis")

    @pyqtSlot()
    def _toggle_listening(self) -> None:
        self._listening_active = not self._listening_active
        if self._listening_active:
            self._listen_action.setText("Desactivar escucha")
            logger.info("Wake word listening activated via tray")
        else:
            self._listen_action.setText("Activar escucha")
            logger.info("Wake word listening deactivated via tray")

    @pyqtSlot()
    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Single click — toggle overlay
            self._toggle_overlay()

    @pyqtSlot()
    def _quit(self) -> None:
        logger.info("Quit requested from system tray")
        app = QApplication.instance()
        if app:
            app.quit()

    @property
    def listening_active(self) -> bool:
        """Whether wake word listening is currently enabled."""
        return self._listening_active
