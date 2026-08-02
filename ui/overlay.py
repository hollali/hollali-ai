from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ui.theming import _theme_palette
from ui.threads import EngineThread
from ui.widgets import MicIconWidget


class OverlayWidget(QtWidgets.QWidget):
    def __init__(self, engine: EngineThread):
        super().__init__()
        self.engine = engine
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(400, 80)
        self._dragging = False
        self._drag_pos = QtCore.QPoint()

        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QtGui.QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        self.mic = MicIconWidget()
        layout.addWidget(self.mic)

        center = QtWidgets.QVBoxLayout()
        center.setSpacing(2)

        self.label = QtWidgets.QLabel("Say 'Hollali' to start")
        self.label.setStyleSheet("font-size: 14px; font-weight: 600; background: transparent;")
        self.label.setWordWrap(True)
        center.addWidget(self.label)

        self.partial_label = QtWidgets.QLabel("")
        self.partial_label.setStyleSheet("font-size: 11px; font-style: italic; background: transparent;")
        self.partial_label.setWordWrap(True)
        self.partial_label.setMaximumHeight(18)
        center.addWidget(self.partial_label)

        layout.addLayout(center, 1)

        self.close_btn = QtWidgets.QPushButton("\u2715")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.hide)
        layout.addWidget(self.close_btn)

        self.apply_theme()

        self._show_timer = QtCore.QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.timeout.connect(self._hide_partial)

        engine.status_changed.connect(self._on_status)
        engine.response_ready.connect(self._on_response)
        engine.partial_text.connect(self._on_partial)
        engine.thinking_started.connect(self._on_thinking_started)
        engine.thinking_ended.connect(self._on_thinking_ended)

    def apply_theme(self):
        palette = _theme_palette()
        self.setStyleSheet(
            f"OverlayWidget {{ background: {palette['surface']}; border: 1px solid {palette['border']}; border-radius: 14px; }}"
        )
        text_color = palette["text"]
        sec_color = palette["text_sec"]
        self.label.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {text_color}; background: transparent;")
        self.partial_label.setStyleSheet(
            f"font-size: 11px; font-style: italic; color: {sec_color}; background: transparent;"
        )
        self.close_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {sec_color}; border: none; font-size: 14px; border-radius: 12px; }}"
            f"QPushButton:hover {{ background: {palette['surface_hover']}; color: {text_color}; }}"
        )

    def _on_status(self, status: str):
        self.mic.set_listening(status == "conversation")
        self.label.setText("Listening..." if status == "conversation" else "Say 'Hollali' to start")

    def _on_thinking_started(self):
        self.label.setText("Thinking...")

    def _on_thinking_ended(self):
        self.label.setText("Listening...")

    def _on_response(self, text: str):
        self.label.setText(text[:60] + ("..." if len(text) > 60 else ""))

    def _on_partial(self, text: str):
        self.partial_label.setText(f"\u2026 {text}")
        self._show_timer.start(3000)

    def _hide_partial(self):
        self.partial_label.setText("")

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.hide()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def show_overlay(self):
        self.apply_theme()
        screen = QtWidgets.QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.right() - self.width() - 20, geo.top() + 20)
        self.show()
