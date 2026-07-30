from __future__ import annotations

import os
import platform
import sys
import threading
from pathlib import Path
from queue import Empty, Queue

from PySide6 import QtCore, QtGui, QtWidgets

import config
import database
from commands import process_command, process_command_stream
from log import logger
from speech import call, rec_audio, talk, talk_async

END_CONVERSATION = ("stop listening", "that's all", "never mind", "go to sleep", "shut up")
AUTOSTART_PATH = os.path.expanduser("~/.config/autostart/hollali-autostart.desktop")

def _resolve_desktop_script() -> str:
    root = Path(__file__).resolve().parent
    script = root / "hollali-desktop"
    if script.exists() and os.access(str(script), os.X_OK):
        return str(script)
    # fallback: module entry point
    return "hollali-desktop"

# ── Color Tokens ───────────────────────────────────────────────────────

_DARK = {
    "bg": "#1e1e2e",
    "surface": "#2a2a3e",
    "surface2": "#363650",
    "text": "#e5e7eb",
    "text_sec": "#9ca3af",
    "accent": "#3b82f6",
    "accent_hover": "#2563eb",
    "accent_pressed": "#1d4ed8",
    "user_bubble": "#3b82f6",
    "asst_bubble": "#2a2a3e",
    "border": "#4b5563",
    "error": "#ef4444",
    "success": "#22c55e",
}

_LIGHT = {
    "bg": "#f8f9fa",
    "surface": "#ffffff",
    "surface2": "#f1f3f5",
    "text": "#1f2937",
    "text_sec": "#6b7280",
    "accent": "#3b82f6",
    "accent_hover": "#2563eb",
    "accent_pressed": "#1d4ed8",
    "user_bubble": "#3b82f6",
    "asst_bubble": "#ffffff",
    "border": "#d1d5db",
    "error": "#ef4444",
    "success": "#22c55e",
}

def _theme_palette() -> dict:
    return _DARK if database.get_preference("theme", "dark") == "dark" else _LIGHT

def _make_stylesheet(c: dict) -> str:
    return f"""
QMainWindow, QDialog, QWidget {{ background: {c['bg']}; color: {c['text']}; }}
QTextEdit {{ background: {c['surface2']}; color: {c['text']}; border: none; font-size: 14px; padding: 8px; border-radius: 8px; }}
QLineEdit {{ background: {c['surface2']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 10px 14px; font-size: 14px; }}
QLineEdit:focus {{ border: 2px solid {c['accent']}; padding: 9px 13px; }}
QToolBar {{ background: {c['surface']}; border: none; border-bottom: 1px solid {c['border']}; padding: 4px 8px; spacing: 4px; }}
QToolBar QToolButton {{ color: {c['text']}; padding: 6px 12px; border-radius: 6px; font-size: 13px; }}
QToolBar QToolButton:hover {{ background: {c['surface2']}; }}
QToolBar QToolButton:checked {{ background: {c['accent']}; color: white; }}
QToolBar::separator {{ background: {c['border']}; width: 1px; margin: 4px 6px; }}
QListWidget {{ background: {c['surface2']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 8px; font-size: 13px; }}
QListWidget::item {{ padding: 8px 12px; border-radius: 4px; }}
QListWidget::item:hover {{ background: {c['surface']}; }}
QListWidget::item:selected {{ background: {c['accent']}; color: white; }}
QPushButton {{ background: {c['accent']}; color: white; border: none; border-radius: 8px; padding: 8px 20px; font-size: 14px; font-weight: 600; }}
QPushButton:hover {{ background: {c['accent_hover']}; }}
QPushButton:pressed {{ background: {c['accent_pressed']}; }}
QPushButton:disabled {{ background: {c['surface2']}; color: {c['text_sec']}; }}
QComboBox, QSpinBox {{ background: {c['surface2']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 6px 10px; }}
QCheckBox {{ color: {c['text']}; spacing: 8px; }}
    QSplitter::handle {{ background: {c['border']}; width: 2px; }}
    #sideNav {{ background: {c['surface']}; border-right: 1px solid {c['border']}; }}
    #navBtn {{ background: transparent; border: none; border-radius: 6px; padding: 6px 14px; text-align: left; font-size: 13px; color: {c['text']}; }}
    #navBtn:hover {{ background: {c['surface2']}; }}
    #navBtn:checked {{ background: {c['accent']}; color: white; }}
    #navLabel {{ font-size: 10px; font-weight: bold; color: {c['text_sec']}; padding: 4px 14px 0px; }}
    #toggleStrip {{ background: {c['surface']}; border-right: 1px solid {c['border']}; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 4px; min-height: 30px; margin: 2px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 4px; min-width: 30px; margin: 2px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
"""

DARK_THEME = _make_stylesheet(_DARK)
LIGHT_THEME = _make_stylesheet(_LIGHT)


# ── Text Command Thread ────────────────────────────────────────────────

class TextCommandThread(QtCore.QThread):
    finished = QtCore.Signal(str)
    partial = QtCore.Signal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.text = text

    def run(self):
        for event_type, *args in process_command_stream(self.text):
            if self.isInterruptionRequested():
                return
            if event_type == "chunk":
                self.partial.emit(args[0])
            elif event_type == "done":
                self.finished.emit(args[0] if args else "")
                return


# ── Engine Thread ──────────────────────────────────────────────────────

class EngineThread(QtCore.QThread):
    partial_text = QtCore.Signal(str)
    response_ready = QtCore.Signal(str)
    wake_word_detected = QtCore.Signal()
    status_changed = QtCore.Signal(str)
    error_occurred = QtCore.Signal(str)
    audio_level = QtCore.Signal(float)
    thinking_started = QtCore.Signal()
    thinking_ended = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = False
        self._in_conversation = False
        self._lock = threading.Lock()

    def run(self):
        self._enabled = True
        with self._lock:
            self._in_conversation = False
        while self._enabled:
            try:
                with self._lock:
                    in_conv = self._in_conversation
                if in_conv:
                    text = rec_audio(
                        timeout=config.CONVERSATION_TIMEOUT,
                        partial_cb=lambda t: self.partial_text.emit(t),
                        level_cb=lambda l: self.audio_level.emit(l),
                    )
                else:
                    text = rec_audio(
                        level_cb=lambda l: self.audio_level.emit(l),
                    )
            except Exception as e:
                self.error_occurred.emit(str(e))
                continue

            if not text:
                continue

            with self._lock:
                in_conv = self._in_conversation
            if in_conv:
                if any(w in text.lower() for w in END_CONVERSATION):
                    self.status_changed.emit("idle")
                    with self._lock:
                        self._in_conversation = False
                    talk_async("Going back to idle. Say 'Hollali' when you need me.")
                    continue

                if any(w in text.lower() for w in ("exit", "quit")):
                    talk_async("Goodbye!")
                    self._enabled = False
                    break

                self.thinking_started.emit()
                response = process_command(text)
                self.thinking_ended.emit()
                if response:
                    talk_async(response)
                    self.response_ready.emit(response)
                continue

            if call(text):
                self.wake_word_detected.emit()
                with self._lock:
                    self._in_conversation = True
                self.status_changed.emit("conversation")
                talk("Hollali here. I'm listening.")
                continue

    def set_conversation(self, active: bool) -> None:
        with self._lock:
            self._in_conversation = active

    def is_conversation(self) -> bool:
        with self._lock:
            return self._in_conversation

    def stop(self):
        self._enabled = False


# ── Waveform Widget ────────────────────────────────────────────────────

class WaveformWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 48)
        self._level = 0.0
        self._bars = 24
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._decay)
        self._timer.start(50)

    def set_level(self, level: float):
        self._level = max(self._level, min(level, 1.0))

    def _decay(self):
        if self._level > 0.005:
            self._level *= 0.85
            self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        w = self.width() / self._bars
        gap = 2
        bar_w = w - gap
        is_dark = _theme_palette() is _DARK
        idle_color = QtGui.QColor("#363650" if is_dark else "#e5e7eb")

        for i in range(self._bars):
            frac = i / self._bars
            h = max(2, self.height() * self._level * (1.0 - frac * 0.5))

            if self._level > 0.01:
                r = int(59 + frac * 100)
                g = int(130 + (1 - frac) * 80)
                b = int(246)
                p.setBrush(QtGui.QColor(r, g, b))
            else:
                p.setBrush(idle_color)

            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.drawRoundedRect(
                int(i * w + gap / 2),
                int(self.height() - h),
                int(bar_w),
                int(h),
                2, 2,
            )
        p.end()


# ── Chat Bubble ────────────────────────────────────────────────────────

class ChatBubble(QtWidgets.QFrame):
    def __init__(self, sender: str, text: str, is_user: bool, palette: dict, parent=None):
        super().__init__(parent)
        self._is_user = is_user
        self._palette = palette

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(4)

        self.text_label = QtWidgets.QLabel(text)
        self.text_label.setWordWrap(True)
        self.text_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        text_color = palette["text"]
        self.text_label.setStyleSheet(
            f"font-size: 14px; color: {text_color}; background: transparent;"
        )
        layout.addWidget(self.text_label)

        self._btn_row = QtWidgets.QHBoxLayout()
        self._btn_row.setContentsMargins(0, 2, 0, 0)
        self._btn_row.setSpacing(4)

        self._copy_btn = QtWidgets.QPushButton("Copy")
        self._copy_btn.setFixedHeight(22)
        self._copy_btn.setToolTip("Copy text")
        self._copy_btn.clicked.connect(lambda: QtWidgets.QApplication.clipboard().setText(self.text_label.text()))
        self._btn_row.addWidget(self._copy_btn)

        if not is_user:
            self._speak_btn = QtWidgets.QPushButton("Speak")
            self._speak_btn.setFixedHeight(22)
            self._speak_btn.setToolTip("Speak this response aloud")
            self._speak_btn.clicked.connect(lambda: talk_async(self.text_label.text()))
            self._btn_row.addWidget(self._speak_btn)

        self._style_tool_buttons(self._copy_btn)
        if not is_user:
            self._style_tool_buttons(self._speak_btn)

        self._btn_row.addStretch()
        layout.addLayout(self._btn_row)

        if is_user:
            self.setObjectName("chatBubble")
            self.setStyleSheet(f"""
                #chatBubble {{
                    background: {palette["surface2"]};
                    border-radius: 16px;
                }}
            """)
        else:
            self.setStyleSheet("background: transparent; border: none;")

    def set_bubble_width(self, container_width: int):
        if self._is_user:
            mw = max(280, int(container_width * 0.60))
        else:
            mw = max(280, int(container_width * 0.95))
        self.setMaximumWidth(mw)

    def _style_tool_buttons(self, btn, palette=None):
        p = palette or self._palette
        btn.setStyleSheet(
            f"QPushButton {{ background: {p['surface2']}; color: {p['text_sec']}; border: none; border-radius: 11px; font-size: 11px; padding: 0 4px; }}"
            f"QPushButton:hover {{ background: {p['border']}; color: {p['text']}; }}"
        )

    def update_theme(self, palette: dict):
        self._palette = palette
        if self._is_user:
            self.setStyleSheet(f"""
                #chatBubble {{
                    background: {palette["surface2"]};
                    border-radius: 16px;
                }}
            """)
        else:
            self.setStyleSheet("background: transparent; border: none;")
        text_color = palette["text"]
        self.text_label.setStyleSheet(
            f"font-size: 14px; color: {text_color}; background: transparent;"
        )
        for btn in self.findChildren(QtWidgets.QPushButton):
            self._style_tool_buttons(btn, palette)

    def append_text(self, text_piece: str):
        current = self.text_label.text()
        self.text_label.setText(current + text_piece)
        p = self.parent()
        while p:
            if isinstance(p, ChatView):
                p._scroll_to_bottom()
                break
            p = p.parent()

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu(self)
        copy_action = menu.addAction("Copy")
        copy_action.triggered.connect(lambda: QtWidgets.QApplication.clipboard().setText(self.text_label.text()))
        menu.exec(event.globalPos())


# ── Chat View ──────────────────────────────────────────────────────────

class ChatView(QtWidgets.QScrollArea):
    welcome_triggered = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        self.container = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(self.container)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(10)

        self.welcome = WelcomeWidget(self)
        self._layout.addWidget(self.welcome, 0, QtCore.Qt.AlignmentFlag.AlignCenter)

        self._layout.addStretch()

        self.setWidget(self.container)
        self.setStyleSheet("background: transparent;")

    def _update_bubble_widths(self):
        cw = self.container.width() or self.width()
        if cw <= 0:
            return
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), ChatBubble):
                item.widget().set_bubble_width(cw)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_bubble_widths()

    def add_message(self, sender: str, text: str, is_user: bool):
        self.welcome.hide()
        palette = _theme_palette()
        bubble = ChatBubble(sender, text, is_user, palette, self.container)
        align = QtCore.Qt.AlignmentFlag.AlignRight if is_user else QtCore.Qt.AlignmentFlag.AlignLeft
        self._layout.insertWidget(self._layout.count() - 1, bubble, 0, align)
        cw = self.container.width() or self.width()
        if cw > 0:
            bubble.set_bubble_width(cw)
        self._scroll_to_bottom()

    def _start_streaming_bubble(self):
        palette = _theme_palette()
        bubble = ChatBubble("Hollali", "", False, palette, self.container)
        align = QtCore.Qt.AlignmentFlag.AlignLeft
        self._layout.insertWidget(self._layout.count() - 1, bubble, 0, align)
        cw = self.container.width() or self.width()
        if cw > 0:
            bubble.set_bubble_width(cw)
        self._scroll_to_bottom()
        return bubble

    def _remove_streaming_bubble(self, bubble):
        if bubble is None:
            return
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            if item and item.widget() is bubble:
                self._layout.takeAt(i)
                bubble.deleteLater()
                break

    def clear(self):
        # remove everything except welcome (idx 0) and stretch (last)
        while self._layout.count() > 2:
            item = self._layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        if hasattr(self, 'welcome'):
            self.welcome.show()
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        QtCore.QTimer.singleShot(30, self._do_scroll)

    def _do_scroll(self):
        sb = self.verticalScrollBar()
        anim = QtCore.QPropertyAnimation(sb, b"value")
        anim.setDuration(150)
        anim.setStartValue(sb.value())
        anim.setEndValue(sb.maximum())
        anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        anim.start()
        self._scroll_anim = anim


# ── Welcome Widget ─────────────────────────────────────────────────────

class WelcomeWidget(QtWidgets.QWidget):
    chip_clicked = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        self.title = QtWidgets.QLabel("Hello, I'm Hollali")
        self.title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)

        self.subtitle = QtWidgets.QLabel("Your voice assistant. Click a quick action or type a command below.")
        self.subtitle.setWordWrap(True)
        self.subtitle.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle)

        chip_row = QtWidgets.QHBoxLayout()
        chip_row.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        chip_row.setSpacing(8)
        for c_label, c_cmd in [
            ("\u2600 Weather", "_WEATHER_"),
            ("\U0001F4F0 News", "latest news"),
            ("\U0001F602 Joke", "tell me a joke"),
            ("\U0001F512 Lock", "lock the screen"),
        ]:
            chip = QtWidgets.QPushButton(c_label)
            chip.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            chip.setFixedHeight(32)
            chip_row.addWidget(chip)
            chip.clicked.connect(lambda checked=False, c=c_cmd: self.chip_clicked.emit(c))

        layout.addLayout(chip_row)
        self.setStyleSheet("background: transparent;")
        self.apply_theme_colors(_theme_palette())

    def apply_theme_colors(self, palette: dict):
        self.title.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {palette['accent']}; background: transparent;")
        self.subtitle.setStyleSheet(f"font-size: 14px; color: {palette['text_sec']}; background: transparent;")
        bg = palette["surface2"]
        text = palette["text"]
        border = palette["border"]
        for ch in self.findChildren(QtWidgets.QPushButton):
            ch.setStyleSheet(f"QPushButton {{ background: {bg}; color: {text}; border: 1px solid {border}; border-radius: 16px; padding: 6px 16px; font-size: 13px; }} QPushButton:hover {{ background: {palette['surface']}; border-color: {palette['accent']}; }}")


# ── Thinking Indicator ─────────────────────────────────────────────────

class ThinkingIndicator(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dot_index = 0
        self._palette = _theme_palette()
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(20, 4, 20, 4)
        layout.setSpacing(4)

        self.label = QtWidgets.QLabel("Hollali is thinking")
        layout.addWidget(self.label)

        self._dots = []
        for _ in range(3):
            dot = QtWidgets.QLabel("\u25CF")
            self._dots.append(dot)
            layout.addWidget(dot)

        layout.addStretch()
        self.update_theme(self._palette)
        self.hide()

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._animate)

    def update_theme(self, palette: dict):
        self._palette = palette
        self.label.setStyleSheet(f"color: {palette['text_sec']}; font-size: 13px; font-style: italic; background: transparent;")
        for dot in self._dots:
            dot.setStyleSheet(f"color: {palette['text_sec']}; font-size: 8px; background: transparent;")

    def start(self):
        self._dot_index = 0
        self.show()
        self._timer.start(350)

    def stop(self):
        self._timer.stop()
        self.hide()
        for dot in self._dots:
            dot.setStyleSheet(f"color: {self._palette['text_sec']}; font-size: 8px; background: transparent;")

    def _animate(self):
        for i, dot in enumerate(self._dots):
            if i == self._dot_index:
                dot.setStyleSheet(f"color: {self._palette['accent']}; font-size: 11px; background: transparent;")
            else:
                dot.setStyleSheet(f"color: {self._palette['text_sec']}; font-size: 8px; background: transparent;")
        self._dot_index = (self._dot_index + 1) % 3


# ── Toast Notification ─────────────────────────────────────────────────

class ToastWidget(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(300, 44)
        self.hide()

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)

        self.label = QtWidgets.QLabel()
        self.label.setWordWrap(True)
        self.label.setStyleSheet("font-size: 13px; background: transparent;")
        layout.addWidget(self.label)

        self._opacity = QtWidgets.QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)

        self._fade_in = QtCore.QPropertyAnimation(self._opacity, b"opacity")
        self._fade_in.setDuration(200)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)

        self._fade_out = QtCore.QPropertyAnimation(self._opacity, b"opacity")
        self._fade_out.setDuration(300)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.finished.connect(self.hide)

        self._hide_timer = QtCore.QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._start_fade_out)

    def show_message(self, text: str, duration: int = 3000, msg_type: str = "info"):
        colors = {"info": "white", "error": "#ef4444", "success": "#22c55e"}
        icons = {"info": "", "error": "\u26A0 ", "success": "\u2713 "}
        color = colors.get(msg_type, "white")
        self.label.setText(f"{icons.get(msg_type, '')}{text}")
        self.label.setStyleSheet(f"color: {color}; font-size: 13px; background: transparent;")
        c = _theme_palette()
        self.setStyleSheet(f"""
            ToastWidget {{
                background: {c['surface2']};
                border: 1px solid {c['border']};
                border-radius: 10px;
            }}
        """)
        self._fade_in.stop()
        self._fade_out.stop()
        self._opacity.setOpacity(0.0)
        self._position()
        self.show()
        self.raise_()
        self._fade_in.start()
        self._hide_timer.start(duration)

    def show_error(self, text: str):
        self.show_message(text, 4000, "error")

    def _position(self):
        parent = self.parent()
        if parent:
            self.move(parent.width() - self.width() - 16, 60)

    def _start_fade_out(self):
        self._fade_out.start()


# ── History Panel ──────────────────────────────────────────────────────

class HistoryPanel(QtWidgets.QWidget):
    session_selected = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        label = QtWidgets.QLabel("Conversations")
        label.setStyleSheet("font-weight: bold; font-size: 13px; padding: 4px;")
        layout.addWidget(label)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget, 1)

        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn)

        self.refresh()

    def refresh(self):
        self.list_widget.clear()
        for s in database.list_sessions(30):
            item = QtWidgets.QListWidgetItem(f"{s['session_id']} \u2014 {s['last']}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, s["session_id"])
            self.list_widget.addItem(item)

    def _on_item_clicked(self, item):
        sid = item.data(QtCore.Qt.ItemDataRole.UserRole)
        self.session_selected.emit(sid)


# ── Mic Icon ───────────────────────────────────────────────────────────

class MicIconWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._listening = False
        self.setFixedSize(48, 48)

    def set_listening(self, active: bool):
        self._listening = active
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        bg = QtGui.QColor("#22c55e") if self._listening else QtGui.QColor("#4b5563")
        p.setBrush(bg)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 12, 12)

        p.setFont(QtGui.QFont("sans-serif", 18))
        p.setPen(QtGui.QPen(QtGui.QColor("white"), 1))
        p.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "\U0001F3A4")
        p.end()


# ── Overlay Widget ─────────────────────────────────────────────────────

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
        self.setFixedSize(450, 100)
        self._dragging = False
        self._drag_pos = QtCore.QPoint()

        shadow = QtWidgets.QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QtGui.QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        self.mic = MicIconWidget()
        layout.addWidget(self.mic)

        center = QtWidgets.QVBoxLayout()
        center.setSpacing(4)

        self.label = QtWidgets.QLabel("Say 'Hollali' to start")
        self.label.setStyleSheet("color: white; font-size: 14px; font-weight: 600; background: transparent;")
        self.label.setWordWrap(True)
        center.addWidget(self.label)

        self.partial_label = QtWidgets.QLabel("")
        self.partial_label.setStyleSheet("color: #9ca3af; font-size: 11px; font-style: italic; background: transparent;")
        self.partial_label.setWordWrap(True)
        self.partial_label.setMaximumHeight(20)
        center.addWidget(self.partial_label)

        layout.addLayout(center, 1)

        self.close_btn = QtWidgets.QPushButton("\u2715")
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #9ca3af;
                border: none;
                font-size: 16px;
                border-radius: 13px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.1);
                color: white;
            }
        """)
        self.close_btn.clicked.connect(self.hide)
        layout.addWidget(self.close_btn)

        self.setStyleSheet(f"""
            OverlayWidget {{
                background: {_DARK['bg']};
                border: 1px solid {_DARK['border']};
                border-radius: 16px;
            }}
        """)

        self._show_timer = QtCore.QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.timeout.connect(self._hide_partial)

        engine.status_changed.connect(self._on_status)
        engine.response_ready.connect(self._on_response)
        engine.partial_text.connect(self._on_partial)
        engine.thinking_started.connect(self._on_thinking_started)
        engine.thinking_ended.connect(self._on_thinking_ended)

    def _on_status(self, status: str):
        self.mic.set_listening(status == "conversation")
        self.label.setText(
            "Listening..." if status == "conversation" else "Say 'Hollali' to start"
        )

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
        screen = QtWidgets.QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.right() - self.width() - 20, geo.top() + 20)
        self.show()


# ── Settings Dialog ────────────────────────────────────────────────────

class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hollali Settings")
        self.setFixedSize(360, 320)

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setSpacing(10)

        self.stt_combo = QtWidgets.QComboBox()
        self.stt_combo.addItems(["google", "vosk"])
        self.stt_combo.setCurrentText(config.STT_ENGINE)
        form.addRow("STT Engine:", self.stt_combo)

        self.tts_combo = QtWidgets.QComboBox()
        self.tts_combo.addItems(["piper", "espeak", "pyttsx3"])
        self.tts_combo.setCurrentText(config.TTS_ENGINE)
        form.addRow("TTS Engine:", self.tts_combo)

        self.timeout_spin = QtWidgets.QSpinBox()
        self.timeout_spin.setRange(3, 60)
        self.timeout_spin.setValue(config.CONVERSATION_TIMEOUT)
        self.timeout_spin.setSuffix(" sec")
        form.addRow("Timeout:", self.timeout_spin)

        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        self.theme_combo.setCurrentText(database.get_preference("theme", "dark"))
        form.addRow("Theme:", self.theme_combo)

        self.autostart_cb = QtWidgets.QCheckBox("Launch at login")
        self.autostart_cb.setChecked(os.path.isfile(AUTOSTART_PATH))
        form.addRow(self.autostart_cb)

        layout.addLayout(form)
        layout.addStretch()

        buttons = QtWidgets.QHBoxLayout()
        save_btn = QtWidgets.QPushButton("Save")
        save_btn.clicked.connect(self._save)
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

    def _save(self):
        config.STT_ENGINE = self.stt_combo.currentText()
        config.TTS_ENGINE = self.tts_combo.currentText()
        config.CONVERSATION_TIMEOUT = self.timeout_spin.value()
        database.set_preference("stt_engine", config.STT_ENGINE)
        database.set_preference("tts_engine", config.TTS_ENGINE)
        database.set_preference("conversation_timeout", str(config.CONVERSATION_TIMEOUT))
        database.set_preference("theme", self.theme_combo.currentText())
        self._set_autostart(self.autostart_cb.isChecked())
        self.accept()

    def _set_autostart(self, enabled: bool):
        autostart_dir = os.path.dirname(AUTOSTART_PATH)
        os.makedirs(autostart_dir, exist_ok=True)
        if enabled:
            content = (
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Hollali\n"
                f"Exec={_resolve_desktop_script()}\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n"
            )
            with open(AUTOSTART_PATH, "w") as f:
                f.write(content)
        else:
            if os.path.isfile(AUTOSTART_PATH):
                os.unlink(AUTOSTART_PATH)


# ── Side Navigation ────────────────────────────────────────────────────

class SideNav(QtWidgets.QWidget):
    def __init__(self, main_window: MainWindow, engine: EngineThread,
                 overlay: OverlayWidget | None = None):
        super().__init__()
        self.setObjectName("sideNav")
        self.setFixedWidth(210)
        M = main_window

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(1)

        def _btn(text: str, checkable: bool = False):
            b = QtWidgets.QPushButton(text)
            b.setObjectName("navBtn")
            b.setCheckable(checkable)
            b.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(34)
            layout.addWidget(b)
            return b

        def _label(text: str):
            lbl = QtWidgets.QLabel(text)
            lbl.setObjectName("navLabel")
            lbl.setFixedHeight(22)
            layout.addWidget(lbl)

        # ── Mic ──
        self.listening_btn = _btn("\U0001F3A4  Listen", checkable=True)
        self.listening_btn.setToolTip("Toggle voice listening (Ctrl+M)")
        self.listening_btn.clicked.connect(M._toggle_listening)
        layout.addSpacing(4)

        # ── View ──
        _label("VIEW")
        if overlay:
            ov = _btn("Overlay")
            ov.setToolTip("Show compact overlay widget")
            ov.clicked.connect(overlay.show_overlay)
        self.history_btn = _btn("History", checkable=True)
        self.history_btn.setToolTip("Show conversation history panel")
        self.history_btn.clicked.connect(M._toggle_history)

        layout.addSpacing(4)

        # ── Quick Actions ──
        _label("QUICK ACTIONS")
        tips = {
            "\u2600 Weather": "Check weather (prompts for city)",
            "\U0001F4F0 News": "Get latest news headlines",
            "\U0001F602 Joke": "Tell me a joke",
            "\U0001F550 Time": "What time is it?",
            "\U0001F4C5 Date": "What is the date?",
        }
        for label, cmd in [
            ("\u2600 Weather", None),
            ("\U0001F4F0 News", "latest news"),
            ("\U0001F602 Joke", "tell me a joke"),
            ("\U0001F550 Time", "what time is it"),
            ("\U0001F4C5 Date", "what is the date"),
        ]:
            b = _btn(label)
            b.setToolTip(tips.get(label, ""))
            if cmd:
                b.clicked.connect(lambda checked, c=cmd: M._quick_send(c))
            else:
                b.clicked.connect(M._quick_weather)

        layout.addSpacing(4)

        # ── System ──
        _label("SYSTEM")
        sys_tips = {
            "\U0001F50A Vol+": "Increase volume to 75%",
            "\U0001F509 Vol-": "Decrease volume to 25%",
            "\U0001F4F7 Screenshot": "Take a screenshot",
            "\U0001F512 Lock": "Lock the screen",
        }
        for label, cb in [
            ("\U0001F50A Vol+", M._quick_volume_up),
            ("\U0001F509 Vol-", M._quick_volume_down),
            ("\U0001F4F7 Screenshot", lambda: M._quick_send("take a screenshot")),
            ("\U0001F512 Lock", lambda: M._quick_send("lock the screen")),
        ]:
            b = _btn(label)
            b.setToolTip(sys_tips.get(label, ""))
            b.clicked.connect(cb)

        layout.addStretch()

        # ── Bottom ──
        _label("SETTINGS")
        t = _btn("Theme")
        t.setToolTip("Switch between dark and light theme")
        t.clicked.connect(M._toggle_theme)
        s = _btn("\u2699  Settings")
        s.setToolTip("Open settings (Ctrl+,)")
        s.clicked.connect(M._open_settings)


# ── Main Window ────────────────────────────────────────────────────────

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, engine: EngineThread, overlay: OverlayWidget | None = None):
        super().__init__()
        self.engine = engine
        self._overlay = overlay
        self.setWindowTitle("Hollali Assistant")
        self.setMinimumSize(640, 540)
        self.resize(720, 620)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        row = QtWidgets.QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # ── Toggle strip (always visible) ──
        self._toggle_strip = QtWidgets.QWidget()
        self._toggle_strip.setObjectName("toggleStrip")
        self._toggle_strip.setFixedWidth(32)
        strip_layout = QtWidgets.QVBoxLayout(self._toggle_strip)
        strip_layout.setContentsMargins(0, 4, 0, 0)
        strip_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignHCenter)

        self._toggle_btn = QtWidgets.QPushButton("\u2630")
        self._toggle_btn.setObjectName("navBtn")
        self._toggle_btn.setFixedSize(32, 32)
        self._toggle_btn.setStyleSheet("font-size: 18px;")
        self._toggle_btn.setToolTip("Toggle side panel (Ctrl+B)")
        self._toggle_btn.clicked.connect(self._toggle_side_nav)
        strip_layout.addWidget(self._toggle_btn)
        strip_layout.addStretch()
        row.addWidget(self._toggle_strip)

        # ── Side nav ──
        self.side_nav = SideNav(self, engine, overlay)
        row.addWidget(self.side_nav)

        # ── Splitter ──
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        chat_container = QtWidgets.QWidget()
        chat_layout = QtWidgets.QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)

        self.chat_view = ChatView()
        chat_layout.addWidget(self.chat_view, 1)

        self.thinking_indicator = ThinkingIndicator()
        chat_layout.addWidget(self.thinking_indicator)

        waveform_row = QtWidgets.QHBoxLayout()
        waveform_row.setContentsMargins(12, 0, 12, 0)
        self.partial_label = QtWidgets.QLabel("")
        self.partial_label.setStyleSheet("color: #9ca3af; font-size: 12px; font-style: italic; background: transparent;")
        self.partial_label.setWordWrap(True)
        self.waveform = WaveformWidget()
        waveform_row.addWidget(self.partial_label, 1)
        waveform_row.addWidget(self.waveform)
        chat_layout.addLayout(waveform_row)

        input_layout = QtWidgets.QHBoxLayout()
        input_layout.setContentsMargins(12, 4, 12, 12)

        self.mic_btn = QtWidgets.QPushButton("Mic")
        self.mic_btn.setFixedSize(44, 28)
        self.mic_btn.setToolTip("Toggle voice listening (Ctrl+M)")
        self.mic_btn.setCheckable(True)
        self.mic_btn.clicked.connect(self._toggle_mic)
        input_layout.addWidget(self.mic_btn)

        self.input_field = QtWidgets.QLineEdit()
        self.input_field.setPlaceholderText("Type a command (Enter to send)")
        self.input_field.returnPressed.connect(self._send_text)
        input_layout.addWidget(self.input_field, 1)

        send_btn = QtWidgets.QPushButton("Send")
        send_btn.clicked.connect(self._send_text)
        input_layout.addWidget(send_btn)

        self.cancel_btn = QtWidgets.QPushButton("\u2715")
        self.cancel_btn.setFixedSize(32, 32)
        self.cancel_btn.setStyleSheet("QPushButton { background: #ef4444; color: white; border: none; border-radius: 16px; font-size: 16px; } QPushButton:hover { background: #dc2626; }")
        self.cancel_btn.hide()
        self.cancel_btn.clicked.connect(self._cancel_text)
        input_layout.addWidget(self.cancel_btn)

        chat_layout.addLayout(input_layout)

        splitter.addWidget(chat_container)

        self.history_panel = HistoryPanel()
        self.history_panel.session_selected.connect(self._load_session)
        self.history_panel.hide()
        splitter.addWidget(self.history_panel)
        splitter.setSizes([500, 0])

        row.addWidget(splitter, 1)

        # ── Toast ──
        self.toast = ToastWidget(self)

        # ── Connections ──
        engine.response_ready.connect(self._add_response)
        engine.partial_text.connect(self._on_partial)
        engine.audio_level.connect(self.waveform.set_level)
        engine.thinking_started.connect(self.thinking_indicator.start)
        engine.thinking_ended.connect(self.thinking_indicator.stop)
        engine.error_occurred.connect(self._on_engine_error)
        engine.status_changed.connect(self._on_status_changed)
        self.chat_view.welcome.chip_clicked.connect(self._on_welcome_chip)

        self._setup_shortcuts()

    def _setup_shortcuts(self):
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Q"), self, self._quit_app)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+M"), self, self._toggle_listening_shortcut)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+,"), self, self._open_settings)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Return"), self, self._send_text)
        QtGui.QShortcut(QtGui.QKeySequence("Escape"), self, lambda: self.showMinimized() if self.isVisible() else None)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+B"), self, self._toggle_side_nav)

    def _quit_app(self):
        QtWidgets.QApplication.instance().quit()

    def _on_welcome_chip(self, cmd: str):
        if cmd == "_WEATHER_":
            self._quick_weather()
        else:
            self._quick_send(cmd)

    def _toggle_listening_shortcut(self):
        self.side_nav.listening_btn.animateClick()

    def _toggle_side_nav(self):
        visible = self.side_nav.isVisible()
        self.side_nav.setVisible(not visible)
        self.toast.show_message("Side nav " + ("shown" if not visible else "hidden"), 1500)

    def apply_theme(self, theme: str):
        stylesheet = DARK_THEME if theme == "dark" else LIGHT_THEME
        QtWidgets.QApplication.instance().setStyleSheet(stylesheet)
        self.waveform.update()
        palette = _theme_palette()
        self.chat_view.welcome.apply_theme_colors(palette)
        self.thinking_indicator.update_theme(palette)
        for i in range(self.chat_view._layout.count()):
            item = self.chat_view._layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), ChatBubble):
                item.widget().update_theme(palette)
        self.mic_btn.setStyleSheet(
            f"QPushButton {{ background: {palette['surface2']}; color: {palette['text_sec']}; border: none; border-radius: 14px; font-size: 11px; font-weight: bold; padding: 0 8px; }}"
            f"QPushButton:hover {{ background: {palette['border']}; color: {palette['text']}; }}"
            f"QPushButton:checked {{ background: #22c55e; color: white; }}"
        )

    def _toggle_theme(self):
        current = database.get_preference("theme", "dark")
        new_theme = "light" if current == "dark" else "dark"
        database.set_preference("theme", new_theme)
        self.apply_theme(new_theme)
        self.toast.show_message(f"Theme: {new_theme}", 2000)

    def _toggle_history(self):
        visible = not self.history_panel.isVisible()
        self.history_panel.setVisible(visible)
        self.side_nav.history_btn.setChecked(visible)
        if visible:
            splitter = self.findChild(QtWidgets.QSplitter)
            if splitter:
                total = splitter.width()
                splitter.setSizes([int(total * 0.65), int(total * 0.35)])
        self.toast.show_message("History " + ("shown" if visible else "hidden"))

    def _load_session(self, session_id: str):
        messages = database.load_conversation(session_id, limit=50)
        self.chat_view.clear()
        for msg in messages:
            is_user = msg["role"] == "user"
            sender = "You" if is_user else "Hollali"
            self.chat_view.add_message(sender, msg["content"], is_user=is_user)

    def _send_text(self, text: str = ""):
        text = text or self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self.chat_view.add_message("You", text, is_user=True)
        self.thinking_indicator.start()
        self.input_field.setEnabled(False)
        self.cancel_btn.show()
        self._streaming_bubble = None

        if hasattr(self, '_text_thread') and self._text_thread.isRunning():
            self._text_thread.requestInterruption()
            self._text_thread.quit()
            self._text_thread.wait(500)

        self._text_thread = TextCommandThread(text, self)
        self._text_thread.partial.connect(self._on_stream_partial)
        self._text_thread.finished.connect(self._on_text_response)
        self._text_thread.finished.connect(self._text_thread.deleteLater)
        self._text_thread.finished.connect(lambda: self.thinking_indicator.stop())
        self._text_thread.start()

    def _cancel_text(self):
        if hasattr(self, '_text_thread') and self._text_thread.isRunning():
            self._text_thread.requestInterruption()
            self._text_thread.quit()
            self._text_thread.wait(500)
        self.thinking_indicator.stop()
        self.cancel_btn.hide()
        self.input_field.setEnabled(True)
        self.chat_view._remove_streaming_bubble(self._streaming_bubble)
        self._streaming_bubble = None
        self.toast.show_message("Command cancelled", 1500, "info")

    def _on_stream_partial(self, chunk: str):
        if self._streaming_bubble is None:
            self._streaming_bubble = self.chat_view._start_streaming_bubble()
        self._streaming_bubble.append_text(chunk)

    def _on_text_response(self, response: str):
        self.cancel_btn.hide()
        self.input_field.setEnabled(True)
        streamed = self._streaming_bubble is not None
        self._streaming_bubble = None
        if response and not streamed:
            self.chat_view.add_message("Hollali", response, is_user=False)

    def _quick_send(self, cmd: str):
        self._send_text(cmd)

    def _quick_weather(self):
        city, ok = QtWidgets.QInputDialog.getText(self, "Weather", "Enter city name:")
        if ok and city.strip():
            self._send_text(f"weather in {city.strip()}")

    def _quick_volume_up(self):
        self._send_text("set volume to 75")

    def _quick_volume_down(self):
        self._send_text("set volume to 25")

    def _add_response(self, text: str):
        self.chat_view.add_message("Hollali", text, is_user=False)

    def _on_partial(self, text: str):
        self.partial_label.setText(f"\u2026 {text}")

    def _toggle_listening(self, active: bool):
        self.engine.set_conversation(active)
        self.engine.status_changed.emit("conversation" if active else "idle")

    def _toggle_mic(self):
        active = not self.engine.is_conversation()
        self._toggle_listening(active)

    def _on_status_changed(self, status: str):
        active = status == "conversation"
        btn = self.side_nav.listening_btn
        btn.blockSignals(True)
        btn.setChecked(active)
        btn.blockSignals(False)
        btn.setText("\u23F9  Stop" if active else "\U0001F3A4  Listen")
        self.mic_btn.blockSignals(True)
        self.mic_btn.setChecked(active)
        self.mic_btn.blockSignals(False)

    def _on_engine_error(self, error: str):
        self.toast.show_error(error)

    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.apply_theme(database.get_preference("theme", "dark"))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.toast._position()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        if not hasattr(self, '_minimize_toast_shown'):
            self._minimize_toast_shown = True
            self.toast.show_message("Hollali minimized to tray. Click tray icon or press Ctrl+B to show.", 4000, "info")


# ── System Tray ────────────────────────────────────────────────────────

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


# ── Tray Icon ──────────────────────────────────────────────────────────

def _make_icon_pixmap(size: int, active: bool = False) -> QtGui.QPixmap:
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    bg = QtGui.QColor("#22c55e") if active else QtGui.QColor("#4b5563")
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


# ── App Bootstrap ──────────────────────────────────────────────────────

def _warn_wayland() -> None:
    if platform.system() == "Linux" and os.environ.get("WAYLAND_DISPLAY"):
        logger.info(
            "Wayland detected — system tray icon may not appear without "
            "libappindicator or a compatible shell extension"
        )


class HollaliDesktop:
    def __init__(self):
        self.app = QtWidgets.QApplication(sys.argv)
        self.app.setApplicationName("Hollali")
        self.app.setQuitOnLastWindowClosed(False)

        _warn_wayland()

        self.engine = EngineThread()
        self.overlay = OverlayWidget(self.engine)
        self.window = MainWindow(self.engine, self.overlay)
        self.tray = SystemTray(self.app, self.window, self.overlay, self.engine)

        theme = database.get_preference("theme", "dark")
        self.window.apply_theme(theme)

    def run(self):
        self.engine.start()
        self.tray.show()
        self.window.show()
        return self.app.exec()

    def cleanup(self):
        self.engine.stop()
        self.engine.wait(2000)


def main():
    database.init_db()
    config.load_persisted_settings()
    desktop = HollaliDesktop()
    try:
        sys.exit(desktop.run())
    finally:
        desktop.cleanup()


if __name__ == "__main__":
    main()
