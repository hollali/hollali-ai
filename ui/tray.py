from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from ui.overlay import OverlayWidget
from ui.threads import EngineThread

if TYPE_CHECKING:
    from ui.main_window import MainWindow


def _make_icon_pixmap(size: int, active: bool = False) -> QtGui.QPixmap:
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    bg = QtGui.QColor("#10a37f") if active else QtGui.QColor("#6b7280")
    painter.setBrush(bg)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, size - 4, size - 4, 8, 8)
    painter.setPen(QtGui.QPen(QtGui.QColor("white"), 2))
    cx, cy = size // 2, size // 2
    painter.drawEllipse(QtCore.QPoint(cx, cy - 2), 4, 4)
    painter.drawLine(cx, cy + 2, cx, cy + 10)
    painter.drawLine(cx - 5, cy + 10, cx + 5, cy + 10)
    painter.end()
    return pixmap


class SystemTray(QtWidgets.QSystemTrayIcon):
    def __init__(self, app: QtWidgets.QApplication, window: MainWindow,
                 overlay: OverlayWidget, engine: EngineThread):
        pixmap = _make_icon_pixmap(48)
        super().__init__(QtGui.QIcon(pixmap), app)
        self.window = window
        self.overlay = overlay
        self.engine = engine
        self.setToolTip("Hollali Assistant")

        menu = QtWidgets.QMenu()
        show_action = menu.addAction("Show Window")
        show_action.triggered.connect(window.show)

        self.listen_action = menu.addAction("Start Listening")
        self.listen_action.triggered.connect(self._toggle_listening)

        self.overlay_action = menu.addAction("Show Overlay")
        self.overlay_action.triggered.connect(overlay.show_overlay)

        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activate)
        engine.status_changed.connect(self._on_status)

    def _quit(self):
        self.engine.stop()
        QtWidgets.QApplication.instance().quit()

    def _toggle_listening(self):
        active = not self.engine.is_conversation()
        self.engine.set_conversation(active)
        self.listen_action.setText("Stop Listening" if active else "Start Listening")
        self._update_icon(active)

    def _on_status(self, status: str):
        active = status == "conversation"
        self.listen_action.setText("Stop Listening" if active else "Start Listening")
        self._update_icon(active)
        if active:
            self.showMessage("Hollali", "Listening...",
                             QtWidgets.QSystemTrayIcon.MessageIcon.Information, 2000)

    def _update_icon(self, active: bool):
        pixmap = _make_icon_pixmap(48, active)
        self.setIcon(QtGui.QIcon(pixmap))

    def _on_activate(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            if self.window.isVisible():
                self.window.hide()
            else:
                self.window.show()
                self.window.raise_()
                self.window.activateWindow()
