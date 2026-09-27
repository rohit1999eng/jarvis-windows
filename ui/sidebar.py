"""
Left navigation rail. Selecting an item switches the page shown in the
right-hand QStackedWidget (see gui.py); "Settings" is the exception -- it
opens the settings dialog directly rather than a page, since it's an
action, not a place to browse.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QPushButton, QVBoxLayout

NAV_ITEMS = ["System", "Tools", "Memory", "Conversations"]

_TOOLTIPS = {
    "System": "CPU, RAM, GPU, disk, battery and pipeline latency",
    "Tools": "Functions Qwen3 can call via Ollama tool calling",
    "Memory": "What JARVIS currently remembers for this session",
    "Conversations": "Session history (single live session for now)",
}


class Sidebar(QFrame):
    page_changed = Signal(str)
    settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self.setFixedWidth(150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 14)
        layout.setSpacing(4)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        for name in NAV_ITEMS:
            button = QPushButton(f"  {name}")
            button.setObjectName("nav_button")
            button.setCheckable(True)
            button.setToolTip(_TOOLTIPS.get(name, ""))
            button.setAccessibleName(f"Show {name} panel")
            button.clicked.connect(lambda _checked, n=name: self.page_changed.emit(n))
            self._group.addButton(button)
            layout.addWidget(button)

        layout.addStretch(1)

        settings_button = QPushButton("  Settings")
        settings_button.setObjectName("nav_button")
        settings_button.setToolTip("Open JARVIS settings (Ctrl+,)")
        settings_button.setAccessibleName("Open settings dialog")
        settings_button.clicked.connect(self.settings_requested.emit)
        layout.addWidget(settings_button)

        # default selection
        first = self._group.buttons()[0]
        first.setChecked(True)
