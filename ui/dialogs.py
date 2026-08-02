from __future__ import annotations

import os

from PySide6 import QtCore, QtWidgets

import config
import database
from ui.theming import _theme_palette
from ui.threads import AUTOSTART_PATH, _resolve_desktop_script


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hollali Settings")
        self.setFixedSize(420, 380)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        form = QtWidgets.QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

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
        form.addRow("", self.autostart_cb)

        layout.addLayout(form)
        layout.addStretch()

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(8)
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setFlat(True)
        cancel_btn.clicked.connect(self.reject)
        save_btn = QtWidgets.QPushButton("Save")
        save_btn.clicked.connect(self._save)
        buttons.addStretch()
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

        self._apply_dialog_theme()

    def _apply_dialog_theme(self):
        palette = _theme_palette()
        self.setStyleSheet(f"QDialog {{ background: {palette['bg']}; }}")

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
