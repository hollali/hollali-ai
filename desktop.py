from __future__ import annotations

import os
import sys
import threading
from queue import Empty, Queue

from PySide6 import QtCore, QtGui, QtWidgets

import config
import database
from commands import process_command
from speech import call, rec_audio, talk

END_CONVERSATION = ("stop listening", "that's all", "never mind", "go to sleep", "shut up")
AUTOSTART_PATH = os.path.expanduser("~/.config/autostart/hollali-autostart.desktop")

DARK_THEME = """
QMainWindow, QDialog, QWidget { background: #1f2937; color: #e5e7eb; }
QTextEdit { background: #111827; color: #e5e7eb; border: none; font-size: 14px; padding: 8px; }
QLineEdit { background: #374151; color: white; border: 1px solid #4b5563; border-radius: 6px; padding: 8px 12px; font-size: 14px; }
QToolBar { background: #1f2937; border: none; padding: 4px; spacing: 4px; }
QToolBar QToolButton { color: #e5e7eb; padding: 6px 12px; border-radius: 6px; font-size: 13px; }
QToolBar QToolButton:hover { background: #374151; }
QToolBar QToolButton:checked { background: #3b82f6; }
QListWidget { background: #111827; color: #e5e7eb; border: 1px solid #374151; border-radius: 6px; font-size: 13px; }
QListWidget::item { padding: 6px 10px; }
QListWidget::item:hover { background: #374151; }
QListWidget::item:selected { background: #3b82f6; }
QPushButton { background: #3b82f6; color: white; border: none; border-radius: 6px; padding: 8px 20px; font-size: 14px; }
QPushButton:hover { background: #2563eb; }
QPushButton:pressed { background: #1d4ed8; }
QComboBox, QSpinBox { background: #374151; color: white; border: 1px solid #4b5563; border-radius: 4px; padding: 4px 8px; }
QCheckBox { color: #e5e7eb; }
QSplitter::handle { background: #374151; width: 2px; }
"""

LIGHT_THEME = """
QMainWindow, QDialog, QWidget { background: #ffffff; color: #1f2937; }
QTextEdit { background: #f9fafb; color: #1f2937; border: none; font-size: 14px; padding: 8px; }
QLineEdit { background: #f9fafb; color: #1f2937; border: 1px solid #d1d5db; border-radius: 6px; padding: 8px 12px; font-size: 14px; }
QToolBar { background: #ffffff; border: none; padding: 4px; spacing: 4px; }
QToolBar QToolButton { color: #1f2937; padding: 6px 12px; border-radius: 6px; font-size: 13px; }
QToolBar QToolButton:hover { background: #f3f4f6; }
QToolBar QToolButton:checked { background: #3b82f6; color: white; }
QListWidget { background: #f9fafb; color: #1f2937; border: 1px solid #e5e7eb; border-radius: 6px; font-size: 13px; }
QListWidget::item { padding: 6px 10px; }
QListWidget::item:hover { background: #f3f4f6; }
QListWidget::item:selected { background: #3b82f6; color: white; }
QPushButton { background: #3b82f6; color: white; border: none; border-radius: 6px; padding: 8px 20px; font-size: 14px; }
QPushButton:hover { background: #2563eb; }
QPushButton:pressed { background: #1d4ed8; }
QComboBox, QSpinBox { background: white; color: #1f2937; border: 1px solid #d1d5db; border-radius: 4px; padding: 4px 8px; }
QCheckBox { color: #1f2937; }
QSplitter::handle { background: #e5e7eb; width: 2px; }
"""


class EngineThread(QtCore.QThread):
    partial_text = QtCore.Signal(str)
    response_ready = QtCore.Signal(str)
    wake_word_detected = QtCore.Signal()
    status_changed = QtCore.Signal(str)
    error_occurred = QtCore.Signal(str)
    audio_level = QtCore.Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = False
        self._in_conversation = False

    def run(self):
        self._enabled = True
        self._in_conversation = False
        while self._enabled:
            try:
                if self._in_conversation:
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

            if self._in_conversation:
                if any(w in text.lower() for w in END_CONVERSATION):
                    self.status_changed.emit("idle")
                    self._in_conversation = False
                    talk("Going back to idle. Say 'Hollali' when you need me.")
                    continue

                if any(w in text.lower() for w in ("exit", "quit")):
                    talk("Goodbye!")
                    self._enabled = False
                    break

                response = process_command(text)
                if response:
                    talk(response)
                    self.response_ready.emit(response)
                continue

            if call(text):
                self.wake_word_detected.emit()
                self._in_conversation = True
                self.status_changed.emit("conversation")
                talk("Hollali here. I'm listening.")
                continue

    def stop(self):
        self._enabled = False


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
        self._level = max(self._level, level)

    def _decay(self):
        if self._level > 0.01:
            self._level *= 0.85
            self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        w = self.width() / self._bars
        gap = 2
        bar_w = w - gap
        for i in range(self._bars):
            frac = i / self._bars
            h = max(2, self.height() * self._level * (1.0 - frac * 0.5))
            if self._level > 0.01:
                r, g, b = int(59 + frac * 196), int(130 + (1 - frac) * 100), int(246)
                p.setBrush(QtGui.QColor(r, g, b))
            else:
                p.setBrush(QtGui.QColor("#374151"))
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.drawRoundedRect(int(i * w + gap / 2), int(self.height() - h), int(bar_w), int(h), 2, 2)
        p.end()


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
        with database._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT session_id, MAX(created_at) as last "
                "FROM conversations GROUP BY session_id ORDER BY last DESC LIMIT 30"
            ).fetchall()
        for r in rows:
            item = QtWidgets.QListWidgetItem(f"{r['session_id']} — {r['last']}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, r['session_id'])
            self.list_widget.addItem(item)

    def _on_item_clicked(self, item):
        sid = item.data(QtCore.Qt.ItemDataRole.UserRole)
        self.session_selected.emit(sid)


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
        color = QtGui.QColor("#22c55e") if self._listening else QtGui.QColor("#6b7280")
        p.setBrush(color)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 10, 10)
        p.setPen(QtGui.QPen(QtGui.QColor("white"), 2))
        cx, cy = 24, 24
        p.setFont(QtGui.QFont("sans-serif", 18))
        p.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "🎤")


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
        self.setFixedSize(420, 90)
        self._dragging = False
        self._drag_pos = QtCore.QPoint()

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.mic = MicIconWidget()
        layout.addWidget(self.mic)

        right = QtWidgets.QVBoxLayout()
        right.setSpacing(2)

        self.label = QtWidgets.QLabel("Say 'Hollali' to start")
        self.label.setStyleSheet("color: white; font-size: 13px;")
        self.label.setWordWrap(True)
        right.addWidget(self.label)

        self.partial_label = QtWidgets.QLabel("")
        self.partial_label.setStyleSheet("color: #9ca3af; font-size: 11px; font-style: italic;")
        self.partial_label.setWordWrap(True)
        self.partial_label.setMaximumHeight(20)
        right.addWidget(self.partial_label)

        layout.addLayout(right, 1)

        right_btns = QtWidgets.QVBoxLayout()
        self.close_btn = QtWidgets.QPushButton("✕")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet("background: transparent; color: #9ca3af; border: none; font-size: 16px;")
        self.close_btn.clicked.connect(self.hide)
        right_btns.addWidget(self.close_btn)
        right_btns.addStretch()
        layout.addLayout(right_btns)

        self.setStyleSheet("background-color: #1f2937; border-radius: 12px;")

        self._show_timer = QtCore.QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.timeout.connect(self._hide_partial)

        engine.status_changed.connect(self._on_status)
        engine.response_ready.connect(self._on_response)
        engine.partial_text.connect(self._on_partial)

    def _on_status(self, status: str):
        self.mic.set_listening(status == "conversation")
        self.label.setText("Listening..." if status == "conversation" else "Say 'Hollali' to start")

    def _on_response(self, text: str):
        self.label.setText(text[:60] + ("..." if len(text) > 60 else ""))

    def _on_partial(self, text: str):
        self.partial_label.setText(f"… {text}")
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
        self.tts_combo.addItems(["pyttsx3", "espeak"])
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
                f"Exec={os.path.abspath('hollali-desktop')}\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n"
            )
            with open(AUTOSTART_PATH, "w") as f:
                f.write(content)
        else:
            if os.path.isfile(AUTOSTART_PATH):
                os.unlink(AUTOSTART_PATH)


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
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QtWidgets.QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self.listening_btn = QtGui.QAction("🎤 Start", self)
        self.listening_btn.setCheckable(True)
        self.listening_btn.triggered.connect(self._toggle_listening)
        toolbar.addAction(self.listening_btn)

        toolbar.addSeparator()

        if self._overlay:
            overlay_action = QtGui.QAction("Overlay", self)
            overlay_action.triggered.connect(self._overlay.show_overlay)
            toolbar.addAction(overlay_action)

        toolbar.addSeparator()

        history_action = QtGui.QAction("History", self)
        history_action.setCheckable(True)
        history_action.triggered.connect(self._toggle_history)
        toolbar.addAction(history_action)

        toolbar.addSeparator()

        theme_action = QtGui.QAction("Toggle Theme", self)
        theme_action.triggered.connect(self._toggle_theme)
        toolbar.addAction(theme_action)

        toolbar.addSeparator()

        for label, cmd in [
            ("☀ Weather", None),
            ("📰 News", "latest news"),
            ("😂 Joke", "tell me a joke"),
            ("🕐 Time", "what time is it"),
            ("📅 Date", "what is the date"),
            ("🔊 Vol+", None),
            ("🔉 Vol-", None),
            ("📷 Screenshot", "take a screenshot"),
            ("🔒 Lock", "lock the screen"),
        ]:
            act = QtGui.QAction(label, self)
            if cmd:
                act.triggered.connect(lambda checked, c=cmd: self._quick_send(c))
            elif "Vol+" in label:
                act.triggered.connect(self._quick_volume_up)
            elif "Vol-" in label:
                act.triggered.connect(self._quick_volume_down)
            elif "Weather" in label:
                act.triggered.connect(self._quick_weather)
            toolbar.addAction(act)

        toolbar.addSeparator()

        settings_action = QtGui.QAction("Settings", self)
        settings_action.triggered.connect(self._open_settings)
        toolbar.addAction(settings_action)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)

        chat_container = QtWidgets.QWidget()
        chat_layout = QtWidgets.QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)

        self.chat = QtWidgets.QTextEdit()
        self.chat.setReadOnly(True)
        chat_layout.addWidget(self.chat, 1)

        waveform_row = QtWidgets.QHBoxLayout()
        waveform_row.setContentsMargins(8, 0, 8, 0)
        self.partial_label = QtWidgets.QLabel("")
        self.partial_label.setStyleSheet("color: #9ca3af; font-size: 12px; font-style: italic;")
        self.waveform = WaveformWidget()
        waveform_row.addWidget(self.partial_label, 1)
        waveform_row.addWidget(self.waveform)
        chat_layout.addLayout(waveform_row)

        input_layout = QtWidgets.QHBoxLayout()
        input_layout.setContentsMargins(8, 4, 8, 8)

        self.input_field = QtWidgets.QLineEdit()
        self.input_field.setPlaceholderText("Type a command (Ctrl+Enter)")
        self.input_field.returnPressed.connect(self._send_text)
        input_layout.addWidget(self.input_field)

        send_btn = QtWidgets.QPushButton("Send")
        send_btn.clicked.connect(self._send_text)
        input_layout.addWidget(send_btn)

        chat_layout.addLayout(input_layout)

        splitter.addWidget(chat_container)

        self.history_panel = HistoryPanel()
        self.history_panel.session_selected.connect(self._load_session)
        self.history_panel.hide()
        splitter.addWidget(self.history_panel)
        splitter.setSizes([500, 0])

        layout.addWidget(splitter)

        engine.response_ready.connect(self._add_response)
        engine.partial_text.connect(self._on_partial)
        engine.audio_level.connect(self.waveform.set_level)

        self._setup_shortcuts()

    def _setup_shortcuts(self):
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Q"), self, self._quit_app)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+M"), self, self._toggle_listening_shortcut)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+,"), self, self._open_settings)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Return"), self, self._send_text)
        QtGui.QShortcut(QtGui.QKeySequence("Escape"), self, lambda: self.showMinimized() if self.isVisible() else None)

    def _quit_app(self):
        QtWidgets.QApplication.instance().quit()

    def _toggle_listening_shortcut(self):
        self.listening_btn.trigger()

    def apply_theme(self, theme: str):
        stylesheet = DARK_THEME if theme == "dark" else LIGHT_THEME
        QtWidgets.QApplication.instance().setStyleSheet(stylesheet)
        self.waveform.update()

    def _toggle_theme(self):
        current = database.get_preference("theme", "dark")
        new_theme = "light" if current == "dark" else "dark"
        database.set_preference("theme", new_theme)
        self.apply_theme(new_theme)

    def _toggle_history(self):
        visible = not self.history_panel.isVisible()
        self.history_panel.setVisible(visible)
        sender = self.sender()
        if sender:
            sender.setChecked(visible)

    def _load_session(self, session_id: str):
        messages = database.load_conversation(session_id, limit=50)
        self.chat.clear()
        for msg in messages:
            color = "#60a5fa" if msg["role"] == "user" else "#34d399"
            sender = "You" if msg["role"] == "user" else "Hollali"
            self.chat.append(f'<span style="color:{color}; font-weight:bold;">{sender}:</span> {msg["content"]}')

    def _send_text(self, text: str = ""):
        text = text or self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()
        self._add_message("You", text, "#60a5fa")
        response = process_command(text)
        if response:
            self._add_message("Hollali", response, "#34d399")

    def _quick_send(self, cmd: str):
        self._send_text(cmd)

    def _quick_weather(self):
        self.input_field.setText("weather in ")
        self.input_field.setFocus()
        self.input_field.selectAll()

    def _quick_volume_up(self):
        self._send_text("set volume to 75")

    def _quick_volume_down(self):
        self._send_text("set volume to 25")

    def _add_message(self, sender: str, text: str, color: str = "#e5e7eb"):
        self.chat.append(f'<span style="color:{color}; font-weight:bold;">{sender}:</span> {text}')

    def _add_response(self, text: str):
        self._add_message("Hollali", text, "#34d399")

    def _on_partial(self, text: str):
        self.partial_label.setText(f"… {text}")

    def _toggle_listening(self, active: bool):
        self.engine._in_conversation = active
        if active:
            self.listening_btn.setText("⏹ Stop")
            self.engine.status_changed.emit("conversation")
        else:
            self.listening_btn.setText("🎤 Start")
            self.engine.status_changed.emit("idle")

    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.apply_theme(database.get_preference("theme", "dark"))

    def closeEvent(self, event):
        event.ignore()
        self.hide()


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
        active = not self.engine._in_conversation
        self.engine._in_conversation = active
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
    painter.drawEllipse(QtCore.QPoint(cx, cy), 6, 6)
    painter.drawLine(cx, cy + 6, cx, cy + 14)
    painter.drawLine(cx - 5, cy + 14, cx + 5, cy + 14)
    painter.end()
    return pixmap


class HollaliDesktop:
    def __init__(self):
        self.app = QtWidgets.QApplication(sys.argv)
        self.app.setApplicationName("Hollali")
        self.app.setQuitOnLastWindowClosed(False)

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
    desktop = HollaliDesktop()
    try:
        sys.exit(desktop.run())
    finally:
        desktop.cleanup()


if __name__ == "__main__":
    main()
