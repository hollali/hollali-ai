from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

import database
from ui.dialogs import SettingsDialog
from ui.navigation import SideNav
from ui.overlay import OverlayWidget
from ui.theming import DARK_THEME, LIGHT_THEME, _theme_palette, invalidate_palette_cache
from ui.threads import EngineThread, TextCommandThread
from ui.widgets import ChatBubble, ChatView, MicButton, ThinkingIndicator, ToastWidget, WaveformWidget


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, engine: EngineThread, overlay: OverlayWidget | None = None):
        super().__init__()
        self.engine = engine
        self._overlay = overlay
        self.setWindowTitle("Hollali")
        self.setMinimumSize(640, 540)
        self.resize(720, 620)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        top_bar = QtWidgets.QWidget()
        top_bar.setObjectName("topBar")
        top_layout = QtWidgets.QHBoxLayout(top_bar)
        top_layout.setContentsMargins(8, 2, 8, 2)
        top_layout.setSpacing(4)

        self._toggle_btn = QtWidgets.QPushButton("\u2630")
        self._toggle_btn.setObjectName("sideToggleBtn")
        self._toggle_btn.setFixedSize(30, 30)
        self._toggle_btn.setToolTip("Toggle sidebar (Ctrl+B)")
        self._toggle_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_side_nav)
        top_layout.addWidget(self._toggle_btn)

        title_label = QtWidgets.QLabel("Hollali")
        title_label.setStyleSheet("font-size: 14px; font-weight: 600; padding: 0 8px;")
        top_layout.addWidget(title_label)

        top_layout.addStretch()

        self._settings_btn = QtWidgets.QPushButton("\u2699")
        self._settings_btn.setObjectName("topSettingsBtn")
        self._settings_btn.setFixedSize(30, 30)
        self._settings_btn.setToolTip("Settings (Ctrl+,)")
        self._settings_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._settings_btn.clicked.connect(self._open_settings)
        top_layout.addWidget(self._settings_btn)

        main_layout.addWidget(top_bar)

        content_row = QtWidgets.QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)

        self.side_nav = SideNav()
        content_row.addWidget(self.side_nav)

        chat_container = QtWidgets.QWidget()
        chat_layout = QtWidgets.QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)

        self.chat_view = ChatView()
        chat_layout.addWidget(self.chat_view, 1)

        self.thinking_indicator = ThinkingIndicator()
        chat_layout.addWidget(self.thinking_indicator)

        input_container = QtWidgets.QWidget()
        input_container.setObjectName("inputContainer")
        input_layout = QtWidgets.QHBoxLayout(input_container)
        input_layout.setContentsMargins(12, 4, 12, 4)
        input_layout.setSpacing(6)

        self.mic_btn = MicButton()
        self.mic_btn.clicked.connect(self._toggle_mic)
        input_layout.addWidget(self.mic_btn)

        self.input_field = QtWidgets.QPlainTextEdit()
        self.input_field.setPlaceholderText("Message Hollali...")
        self.input_field.setFixedHeight(36)
        self.input_field.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.input_field.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.input_field.textChanged.connect(self._on_input_changed)
        self.input_field.installEventFilter(self)
        input_layout.addWidget(self.input_field, 1)

        self.cancel_btn = QtWidgets.QPushButton("\u2715")
        self.cancel_btn.setFixedSize(32, 32)
        self.cancel_btn.setToolTip("Cancel")
        self.cancel_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.hide()
        self.cancel_btn.clicked.connect(self._cancel_text)
        input_layout.addWidget(self.cancel_btn)

        self.send_btn = QtWidgets.QPushButton("\u2191")
        self.send_btn.setFixedSize(32, 32)
        self.send_btn.setToolTip("Send")
        self.send_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self._send_text)
        self.send_btn.hide()
        input_layout.addWidget(self.send_btn)

        chat_layout.addWidget(input_container)

        waveform_row = QtWidgets.QHBoxLayout()
        waveform_row.setContentsMargins(16, 0, 16, 4)
        self.partial_label = QtWidgets.QLabel("")
        self.partial_label.setStyleSheet("font-size: 12px; font-style: italic; background: transparent;")
        self.partial_label.setWordWrap(True)
        self.waveform = WaveformWidget()
        waveform_row.addWidget(self.partial_label, 1)
        waveform_row.addWidget(self.waveform)
        chat_layout.addLayout(waveform_row)

        content_row.addWidget(chat_container, 1)

        main_layout.addLayout(content_row, 1)

        self.toast = ToastWidget(self)

        engine.response_ready.connect(self._add_response)
        engine.partial_text.connect(self._on_partial)
        engine.audio_level.connect(self.waveform.set_level)
        engine.thinking_started.connect(self.thinking_indicator.start)
        engine.thinking_ended.connect(self.thinking_indicator.stop)
        engine.error_occurred.connect(self._on_engine_error)
        engine.status_changed.connect(self._on_status_changed)
        self.chat_view.welcome.chip_clicked.connect(self._on_welcome_chip)

        self.side_nav.new_chat_clicked.connect(self._on_new_chat)
        self.side_nav.session_selected.connect(self._load_session)
        self.side_nav.theme_toggled.connect(self._toggle_theme)
        self.side_nav.settings_clicked.connect(self._open_settings)

        self._setup_shortcuts()

        self._streaming_bubble = None

    def _setup_shortcuts(self):
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Q"), self, self._quit_app)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+M"), self, self._toggle_listening_shortcut)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+,"), self, self._open_settings)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Return"), self, self._send_text)
        QtGui.QShortcut(QtGui.QKeySequence("Escape"), self, lambda: self.showMinimized() if self.isVisible() else None)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+B"), self, self._toggle_side_nav)

    def eventFilter(self, obj, event):
        if obj == self.input_field and event.type() == QtCore.QEvent.Type.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if key == QtCore.Qt.Key.Key_Return and not (mods & QtCore.Qt.ShiftModifier):
                self._send_text()
                return True
            if key == QtCore.Qt.Key.Key_Return and (mods & QtCore.Qt.ShiftModifier):
                return False
        return super().eventFilter(obj, event)

    def _on_input_changed(self):
        text = self.input_field.toPlainText()
        self.send_btn.setVisible(bool(text.strip()))
        self._adjust_input_height()

    def _adjust_input_height(self):
        doc = self.input_field.document()
        doc_height = doc.size().height()
        margins = self.input_field.contentsMargins()
        v_margin = margins.top() + margins.bottom() + 4
        line_height = self.input_field.fontMetrics().lineSpacing()
        min_h = line_height + v_margin
        max_h = line_height * 8 + v_margin
        ideal_h = doc_height + v_margin
        new_h = max(min_h, min(max_h, ideal_h))
        self.input_field.setFixedHeight(int(new_h))

    def _quit_app(self):
        QtWidgets.QApplication.instance().quit()

    def _on_welcome_chip(self, cmd: str):
        if cmd == "_WEATHER_":
            self._quick_weather()
        else:
            self._quick_send(cmd)

    def _toggle_listening_shortcut(self):
        self.mic_btn.animateClick()

    def _toggle_side_nav(self):
        visible = self.side_nav.isVisible()
        self.side_nav.setVisible(not visible)
        self.toast.show_message("Sidebar " + ("shown" if not visible else "hidden"), 1500)

    def _on_new_chat(self):
        self.chat_view.clear()
        self.input_field.clear()
        self.input_field.setFocus()
        self.toast.show_message("New conversation started", 1500)

    def apply_theme(self, theme: str):
        invalidate_palette_cache()
        stylesheet = DARK_THEME if theme == "dark" else LIGHT_THEME
        QtWidgets.QApplication.instance().setStyleSheet(stylesheet)
        self.waveform.update()
        palette = _theme_palette()
        if self._overlay:
            self._overlay.apply_theme()
        self.chat_view.welcome.apply_theme_colors(palette)
        self.thinking_indicator.update_theme(palette)
        self.side_nav.update_theme_btn_text(theme)
        for i in range(self.chat_view._layout.count()):
            item = self.chat_view._layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), ChatBubble):
                item.widget().update_theme(palette)
        self.mic_btn.update()
        self.send_btn.setStyleSheet(
            f"QPushButton {{ background: {palette['accent']}; color: white; border: none; border-radius: 8px; font-size: 16px; padding: 4px 8px; }}"
            f"QPushButton:hover {{ background: {palette['accent_hover']}; }}"
            f"QPushButton:disabled {{ background: {palette['surface_hover']}; color: {palette['text_sec']}; }}"
        )
        self.cancel_btn.setStyleSheet(
            f"QPushButton {{ background: {palette['error']}; color: white; border: none; border-radius: 16px; font-size: 14px; padding: 4px; }}"
            f"QPushButton:hover {{ background: #dc2626; }}"
        )
        self.partial_label.setStyleSheet(
            f"font-size: 12px; font-style: italic; color: {palette['text_sec']}; background: transparent;"
        )
        input_container = self.findChild(QtWidgets.QWidget, "inputContainer")
        if input_container:
            input_container.setStyleSheet(
                f"#inputContainer {{ background: {palette['bg']}; border-top: 1px solid {palette['border']}; }}"
            )

    def _toggle_theme(self):
        current = database.get_preference("theme", "dark")
        new_theme = "light" if current == "dark" else "dark"
        database.set_preference("theme", new_theme)
        self.apply_theme(new_theme)
        self.toast.show_message(f"Theme: {new_theme}", 2000)

    def _load_session(self, session_id: str):
        messages = database.load_conversation(session_id, limit=50)
        self.chat_view.clear()
        for msg in messages:
            is_user = msg["role"] == "user"
            sender = "You" if is_user else "Hollali"
            self.chat_view.add_message(sender, msg["content"], is_user=is_user)

    def _send_text(self, text: str = ""):
        text = text or self.input_field.toPlainText().strip()
        if not text:
            return
        self.input_field.clear()
        self.chat_view.add_message("You", text, is_user=True)
        self.thinking_indicator.start()
        self.input_field.setEnabled(False)
        self.cancel_btn.show()
        self.send_btn.hide()
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
        self.send_btn.setVisible(bool(self.input_field.toPlainText().strip()))
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
        self.send_btn.setVisible(bool(self.input_field.toPlainText().strip()))
        streamed = self._streaming_bubble is not None
        self._streaming_bubble = None
        if response and not streamed:
            self.chat_view.add_message("Hollali", response, is_user=False)
        self.input_field.setFocus()

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
        self.mic_btn.blockSignals(True)
        self.mic_btn.setChecked(active)
        self.mic_btn.blockSignals(False)
        self.mic_btn.set_active(active)

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
            self.toast.show_message("Hollali minimized to tray. Click tray icon to show.", 4000, "info")
