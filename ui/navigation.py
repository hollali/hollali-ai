from __future__ import annotations

from PySide6 import QtCore, QtWidgets

import database


class SideNav(QtWidgets.QWidget):
    new_chat_clicked = QtCore.Signal()
    session_selected = QtCore.Signal(str)
    theme_toggled = QtCore.Signal()
    settings_clicked = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sideNav")
        self.setFixedWidth(260)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)

        new_chat_btn = QtWidgets.QPushButton("+ New Chat")
        new_chat_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        new_chat_btn.setMinimumHeight(38)
        new_chat_btn.clicked.connect(self.new_chat_clicked.emit)
        layout.addWidget(new_chat_btn)

        layout.addSpacing(12)

        history_label = QtWidgets.QLabel("History")
        history_label.setObjectName("historyLabel")
        layout.addWidget(history_label)

        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget, 1)

        layout.addSpacing(8)

        self.theme_btn = QtWidgets.QPushButton("Theme")
        self.theme_btn.setObjectName("themeBtn")
        self.theme_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self.theme_toggled.emit)
        layout.addWidget(self.theme_btn)

        self.settings_btn = QtWidgets.QPushButton("\u2699  Settings")
        self.settings_btn.setObjectName("settingsBtn")
        self.settings_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.settings_btn.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self.settings_btn)

        self.refresh_history()

    def refresh_history(self):
        self.list_widget.clear()
        for s in database.list_sessions(30):
            sid = s["session_id"]
            label = f"{sid[:12]} \u2014 {s['last']}"
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, sid)
            self.list_widget.addItem(item)

    def _on_item_clicked(self, item):
        sid = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if sid:
            self.session_selected.emit(sid)

    def update_theme_btn_text(self, theme: str):
        icon = "\u2601" if theme == "dark" else "\u2600"
        self.theme_btn.setText(f"{icon}  Theme")
