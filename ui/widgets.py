from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ui.theming import _DARK, _theme_palette


class WaveformWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(180, 32)
        self._level = 0.0
        self._bars = 20
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
        palette = _theme_palette()
        is_dark = palette is _DARK
        w = self.width() / self._bars
        gap = 2
        bar_w = w - gap
        accent = QtGui.QColor(palette["accent"])
        idle = QtGui.QColor("#4a4a4a" if is_dark else "#d0d0d0")

        for i in range(self._bars):
            frac = i / self._bars
            h = max(2, self.height() * self._level * (1.0 - frac * 0.5))
            if self._level > 0.01:
                alpha = int(255 * (1.0 - frac * 0.4))
                color = QtGui.QColor(accent)
                color.setAlpha(alpha)
                p.setBrush(color)
            else:
                p.setBrush(idle)
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.drawRoundedRect(
                int(i * w + gap / 2),
                int(self.height() - h),
                int(bar_w),
                int(h),
                2, 2,
            )
        p.end()


class ChatBubble(QtWidgets.QFrame):
    def __init__(self, sender: str, text: str, is_user: bool, palette: dict, parent=None):
        super().__init__(parent)
        self._is_user = is_user
        self._palette = palette

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(2)

        self._sender_label = QtWidgets.QLabel(sender)
        self._sender_label.setStyleSheet(
            f"font-size: 11px; color: {palette['text_sec']}; background: transparent; font-weight: 600;"
        )
        layout.addWidget(self._sender_label)

        self.text_label = QtWidgets.QLabel(text)
        self.text_label.setWordWrap(True)
        self.text_label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.text_label.setStyleSheet(
            f"font-size: 14px; color: {palette['text']}; background: transparent;"
        )
        layout.addWidget(self.text_label)

        self._copy_btn = QtWidgets.QPushButton("Copy")
        self._copy_btn.setFixedSize(42, 20)
        self._copy_btn.setToolTip("Copy text")
        self._copy_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._copy_btn.clicked.connect(
            lambda: QtWidgets.QApplication.clipboard().setText(self.text_label.text())
        )
        self._copy_btn.hide()
        self._style_copy_btn()
        layout.addWidget(self._copy_btn, 0, QtCore.Qt.AlignmentFlag.AlignLeft)

        self._apply_bubble_style()

    def _style_copy_btn(self):
        p = self._palette
        self._copy_btn.setStyleSheet(
            f"QPushButton {{ background: {p['surface_hover']}; color: {p['text_sec']}; border: 1px solid {p['border']}; border-radius: 11px; font-size: 11px; padding: 0 6px; }}"
            f"QPushButton:hover {{ background: {p['border']}; color: {p['text']}; }}"
        )

    def _apply_bubble_style(self):
        p = self._palette
        if self._is_user:
            self.setStyleSheet(
                f"background: {p['surface']}; border-radius: 12px;"
            )
        else:
            self.setStyleSheet(
                f"background: transparent; border-left: 2px solid {p['accent']};"
            )

    def enterEvent(self, event):
        self._copy_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._copy_btn.hide()
        super().leaveEvent(event)

    def set_bubble_width(self, container_width: int):
        if container_width <= 0:
            return
        self.setMaximumWidth(container_width)

    def update_theme(self, palette: dict):
        self._palette = palette
        self._apply_bubble_style()
        self._style_copy_btn()
        self.text_label.setStyleSheet(
            f"font-size: 14px; color: {palette['text']}; background: transparent;"
        )
        self._sender_label.setStyleSheet(
            f"font-size: 11px; color: {palette['text_sec']}; background: transparent; font-weight: 600;"
        )

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
        copy_action.triggered.connect(
            lambda: QtWidgets.QApplication.clipboard().setText(self.text_label.text())
        )
        menu.exec(event.globalPos())


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
        self._layout.setContentsMargins(24, 20, 24, 20)
        self._layout.setSpacing(12)

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

        self.subtitle = QtWidgets.QLabel("Ask me anything or try these suggestions:")
        self.subtitle.setWordWrap(True)
        self.subtitle.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle)

        chip_row = QtWidgets.QHBoxLayout()
        chip_row.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        chip_row.setSpacing(8)

        chips = [
            ("Weather", "_WEATHER_"),
            ("News", "latest news"),
            ("Joke", "tell me a joke"),
            ("Time", "what time is it"),
            ("Date", "what is the date"),
        ]
        for label, cmd in chips:
            chip = QtWidgets.QPushButton(label)
            chip.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            chip.setFixedHeight(32)
            chip_row.addWidget(chip)
            chip.clicked.connect(lambda checked=False, c=cmd: self.chip_clicked.emit(c))

        layout.addLayout(chip_row)
        self.setStyleSheet("background: transparent;")
        self.apply_theme_colors(_theme_palette())

    def apply_theme_colors(self, palette: dict):
        self.title.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {palette['accent']}; background: transparent;"
        )
        self.subtitle.setStyleSheet(
            f"font-size: 14px; color: {palette['text_sec']}; background: transparent;"
        )
        bg = palette["surface"]
        text = palette["text"]
        border = palette["border"]
        for ch in self.findChildren(QtWidgets.QPushButton):
            ch.setStyleSheet(
                f"QPushButton {{ background: {bg}; color: {text}; border: 1px solid {border}; border-radius: 16px; padding: 6px 18px; font-size: 13px; }}"
                f"QPushButton:hover {{ background: {palette['surface_hover']}; border-color: {palette['accent']}; }}"
            )


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
        self.label.setStyleSheet(
            f"color: {palette['text_sec']}; font-size: 13px; font-style: italic; background: transparent;"
        )
        for dot in self._dots:
            dot.setStyleSheet(
                f"color: {palette['text_sec']}; font-size: 8px; background: transparent;"
            )

    def start(self):
        self._dot_index = 0
        self.show()
        self._timer.start(350)

    def stop(self):
        self._timer.stop()
        self.hide()
        for dot in self._dots:
            dot.setStyleSheet(
                f"color: {self._palette['text_sec']}; font-size: 8px; background: transparent;"
            )

    def _animate(self):
        for i, dot in enumerate(self._dots):
            if i == self._dot_index:
                dot.setStyleSheet(
                    f"color: {self._palette['accent']}; font-size: 11px; background: transparent;"
                )
            else:
                dot.setStyleSheet(
                    f"color: {self._palette['text_sec']}; font-size: 8px; background: transparent;"
                )
        self._dot_index = (self._dot_index + 1) % 3


class ToastWidget(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(320, 44)
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
        colors = {"info": self._palette_text_sec(), "error": "#ef4444", "success": "#22c55e"}
        self.label.setStyleSheet(f"color: {colors.get(msg_type, 'white')}; font-size: 13px; background: transparent;")
        self.label.setText(text)
        c = _theme_palette()
        self.setStyleSheet(
            f"ToastWidget {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; }}"
        )
        self._fade_in.stop()
        self._fade_out.stop()
        self._opacity.setOpacity(0.0)
        self._position()
        self.show()
        self.raise_()
        self._fade_in.start()
        self._hide_timer.start(duration)

    def _palette_text_sec(self):
        return _theme_palette()["text_sec"]

    def show_error(self, text: str):
        self.show_message(text, 4000, "error")

    def _position(self):
        parent = self.parent()
        if parent:
            self.move(parent.width() - self.width() - 16, 60)

    def _start_fade_out(self):
        self._fade_out.start()


class MicIconWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._listening = False
        self.setFixedSize(24, 24)

    def set_listening(self, active: bool):
        self._listening = active
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        bg = QtGui.QColor("#22c55e") if self._listening else QtGui.QColor("#6b7280")
        p.setBrush(bg)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.drawEllipse(self.rect().adjusted(2, 2, -2, -2))
        p.end()


class MicButton(QtWidgets.QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(36, 36)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Toggle voice listening (Ctrl+M)")
        self._active = False
        self._hovered = False

    def set_active(self, active: bool):
        self._active = active
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def _colors(self) -> tuple:
        from ui.theming import _theme_palette
        c = _theme_palette()
        if self._active:
            return QtGui.QColor("#22c55e"), QtGui.QColor("white")
        if self._hovered:
            return QtGui.QColor(c["border"]), QtGui.QColor(c["text"])
        return QtGui.QColor(c["surface_hover"]), QtGui.QColor(c["text_sec"])

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)

        bg, fg = self._colors()
        rect = self.rect().adjusted(3, 3, -3, -3)

        p.setBrush(bg)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)

        cx = rect.center().x()
        body_top = rect.top() + 3
        body_bot = rect.bottom() - 8
        body_mid = (body_top + body_bot) / 2
        body_w = rect.width() * 0.35
        body_h = body_bot - body_top

        p.setBrush(fg)
        p.setPen(QtCore.Qt.PenStyle.NoPen)

        body = QtCore.QRectF(cx - body_w / 2, body_top, body_w, body_h)
        p.drawRoundedRect(body, 3, 3)

        arc_rect = QtCore.QRectF(cx - body_w / 2, body_top - 2, body_w, body_h * 0.4)
        p.drawEllipse(arc_rect)

        stand_x = cx
        stand_top = body_bot
        stand_bot = rect.bottom() - 2
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        pen = QtGui.QPen(fg, 2)
        p.setPen(pen)
        p.drawLine(int(stand_x), int(stand_top), int(stand_x), int(stand_bot))

        base_w = rect.width() * 0.5
        p.drawLine(int(cx - base_w / 2), int(stand_bot), int(cx + base_w / 2), int(stand_bot))

        p.end()



