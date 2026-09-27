"""
A polished conversation timeline that replaces the single QTextEdit log.

Each entry is its own small widget so USER / JARVIS / SYSTEM / TOOL messages
can be styled distinctly and timestamped, while staying inside a normal
QScrollArea (cheap, native, no HTML-in-a-textbox hacks needed for anything
except the text formatting within a single bubble).
"""

from __future__ import annotations

import html
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.theme import (
    BG_PANEL_ALT,
    BORDER,
    ROLE_JARVIS,
    ROLE_SYSTEM,
    ROLE_TOOL,
    ROLE_USER,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

_ROLE_STYLE = {
    "USER": (ROLE_USER, "YOU"),
    "JARVIS": (ROLE_JARVIS, "JARVIS"),
    "SYSTEM": (ROLE_SYSTEM, "SYSTEM"),
    "TOOL": (ROLE_TOOL, "TOOL"),
}


class MessageBubble(QFrame):
    def __init__(self, role: str, text: str, parent=None):
        super().__init__(parent)
        color, label = _ROLE_STYLE.get(role.upper(), (TEXT_PRIMARY, role.upper()))

        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {BG_PANEL_ALT};
                border: 1px solid {BORDER};
                border-left: 3px solid {color};
                border-radius: 8px;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 9)
        layout.setSpacing(3)

        header = QLabel(
            f'<span style="color:{color};font-weight:700;font-size:11px;">{label}</span>'
            f'<span style="color:{TEXT_MUTED};font-size:10px;"> &nbsp;&middot;&nbsp; '
            f'{datetime.now().strftime("%H:%M:%S")}</span>'
        )
        layout.addWidget(header)

        body = QLabel()
        body.setText(html.escape(text).replace("\n", "<br>"))
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:13px; border:none; background:transparent;")
        layout.addWidget(body)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)


class ConversationView(QScrollArea):
    """Scrollable, auto-following timeline of MessageBubble widgets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(4, 4, 10, 4)
        self._layout.setSpacing(8)
        self._layout.addStretch(1)

        self.setWidget(container)
        self._container = container

        # connected once; keeps the view pinned to the newest message
        self.verticalScrollBar().rangeChanged.connect(
            lambda _mn, mx: self.verticalScrollBar().setValue(mx)
        )

    def add_message(self, role: str, text: str):
        bubble = MessageBubble(role, text)
        # insert before the trailing stretch so new items stack top-to-bottom
        self._layout.insertWidget(self._layout.count() - 1, bubble)

    def clear(self):
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
