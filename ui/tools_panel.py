"""
Read-only view of the tools available to Qwen3 via Ollama's native tool
calling. This never imports/patches tools.py's behavior -- it only lists
public, top-level functions and their docstrings via `inspect`, so it
can't drift from (or interfere with) the real safety model in tools.py.
"""

from __future__ import annotations

import inspect

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ui.theme import ACCENT, BORDER, TEXT_MUTED, TEXT_PRIMARY


class ToolsPanel(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(10)

        title = QLabel("AVAILABLE TOOLS")
        title.setObjectName("section_title")
        layout.addWidget(title)

        for name, doc in self._discover_tools():
            layout.addWidget(self._tool_row(name, doc))

        layout.addStretch(1)
        self.setWidget(container)

    def _discover_tools(self) -> list[tuple[str, str]]:
        try:
            import tools  # the project's own tool-calling module
        except Exception as exc:  # noqa: BLE001
            return [("tools.py not importable", str(exc))]

        found = []
        for name, member in inspect.getmembers(tools, inspect.isfunction):
            if name.startswith("_"):
                continue
            if member.__module__ != tools.__name__:
                continue  # skip re-exported imports
            doc = (inspect.getdoc(member) or "No description available.").splitlines()[0]
            found.append((name, doc))

        if not found:
            return [("No public functions found", "Check tools.py's function definitions.")]
        return sorted(found)

    def _tool_row(self, name: str, doc: str) -> QWidget:
        row = QWidget()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)
        row.setStyleSheet(
            f"background-color: rgba(255,255,255,6); border: 1px solid {BORDER}; border-radius: 8px;"
        )

        title = QLabel(f"🔧 {name}")
        title.setStyleSheet(f"color:{ACCENT}; font-weight:700; font-size:12px; border:none; background:transparent;")
        layout.addWidget(title)

        desc = QLabel(doc)
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px; border:none; background:transparent;")
        layout.addWidget(desc)

        return row
