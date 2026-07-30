from __future__ import annotations

import os
import platform
import sys

from PySide6 import QtWidgets

import config
import database
from log import logger

from ui.main_window import MainWindow
from ui.overlay import OverlayWidget
from ui.threads import EngineThread
from ui.tray import SystemTray


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
