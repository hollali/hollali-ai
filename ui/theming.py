from __future__ import annotations

import time

import database

_palette_cache: dict | None = None
_palette_cache_ts: float = 0
_PALETTE_TTL = 60.0


def invalidate_palette_cache() -> None:
    global _palette_cache, _palette_cache_ts
    _palette_cache = None
    _palette_cache_ts = 0


_DARK = {
    "bg": "#212121",
    "surface": "#2f2f2f",
    "surface_hover": "#3a3a3a",
    "sidebar": "#1a1a1a",
    "text": "#ececec",
    "text_sec": "#a0a0a0",
    "accent": "#10a37f",
    "accent_hover": "#0d8c6e",
    "border": "#3a3a3a",
    "error": "#ef4444",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "input_bg": "#2f2f2f",
}

_LIGHT = {
    "bg": "#f5f5f5",
    "surface": "#ffffff",
    "surface_hover": "#f0f0f0",
    "sidebar": "#f0f0f0",
    "text": "#1f1f1f",
    "text_sec": "#8a8a8a",
    "accent": "#10a37f",
    "accent_hover": "#0d8c6e",
    "border": "#e0e0e0",
    "error": "#ef4444",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "input_bg": "#ffffff",
}


def _theme_palette() -> dict:
    global _palette_cache, _palette_cache_ts
    now = time.time()
    if _palette_cache is not None and (now - _palette_cache_ts) < _PALETTE_TTL:
        return _palette_cache
    is_dark = database.get_preference("theme", "dark") == "dark"
    _palette_cache = _DARK if is_dark else _LIGHT
    _palette_cache_ts = now
    return _palette_cache


def _make_stylesheet(c: dict) -> str:
    return f"""
QMainWindow, QDialog, QWidget {{ background: {c["bg"]}; color: {c["text"]}; }}
QPlainTextEdit, QTextEdit, QLineEdit {{ background: {c["input_bg"]}; color: {c["text"]}; border: 1px solid {c["border"]}; border-radius: 10px; padding: 8px 12px; font-size: 14px; selection-background-color: {c["accent"]}; }}
QPlainTextEdit:focus, QTextEdit:focus, QLineEdit:focus {{ border: 2px solid {c["accent"]}; }}
#topBar {{ background: {c["sidebar"]}; border-bottom: 1px solid {c["border"]}; min-height: 36px; }}
QListWidget {{ background: transparent; color: {c["text"]}; border: none; font-size: 13px; outline: none; }}
QListWidget::item {{ padding: 8px 12px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {c["surface_hover"]}; }}
QListWidget::item:selected {{ background: {c["accent"]}; color: white; }}
QPushButton {{ background: {c["accent"]}; color: white; border: none; border-radius: 8px; padding: 8px 20px; font-size: 14px; font-weight: 600; }}
QPushButton:hover {{ background: {c["accent_hover"]}; }}
QPushButton:disabled {{ background: {c["surface_hover"]}; color: {c["text_sec"]}; }}
#themeBtn, #settingsBtn {{ background: transparent; color: {c["text_sec"]}; text-align: left; padding: 8px 12px; border-radius: 6px; font-weight: normal; }}
#themeBtn:hover, #settingsBtn:hover {{ color: {c["text"]}; background: {c["surface_hover"]}; }}
#historyLabel {{ font-size: 11px; font-weight: bold; color: {c["text_sec"]}; padding: 4px 8px; }}
#sideToggleBtn, #topSettingsBtn {{ background: transparent; color: {c["text_sec"]}; border: none; border-radius: 6px; font-size: 16px; padding: 4px; }}
#sideToggleBtn:hover, #topSettingsBtn:hover {{ background: {c["surface_hover"]}; color: {c["text"]}; }}
QComboBox, QSpinBox {{ background: {c["input_bg"]}; color: {c["text"]}; border: 1px solid {c["border"]}; border-radius: 6px; padding: 6px 10px; }}
QCheckBox {{ color: {c["text"]}; spacing: 8px; }}
QSplitter::handle {{ background: {c["border"]}; width: 2px; }}
#sideNav {{ background: {c["sidebar"]}; border-right: 1px solid {c["border"]}; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {c["border"]}; border-radius: 4px; min-height: 30px; margin: 2px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; }}
QScrollBar::handle:horizontal {{ background: {c["border"]}; border-radius: 4px; min-width: 30px; margin: 2px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QMenu {{ background: {c["surface"]}; color: {c["text"]}; border: 1px solid {c["border"]}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 24px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c["surface_hover"]}; }}
"""


DARK_THEME = _make_stylesheet(_DARK)
LIGHT_THEME = _make_stylesheet(_LIGHT)
