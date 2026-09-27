"""
Shows what JARVIS currently "remembers" for this session.

The exact internal shape of llm.Conversation is not part of the spec this
GUI was built against, so this panel never assumes a specific attribute
exists -- it probes a handful of common names (``messages``, ``history``,
``_messages``) defensively and falls back to "not exposed" rather than
crashing. If you want this panel fully populated, the cheapest fix is to
add a ``def as_list(self): return self.<your attr>`` method to
Conversation and this panel will prefer that automatically.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.theme import ACCENT, TEXT_MUTED, TEXT_PRIMARY

_CANDIDATE_ATTRS = ("as_list", "messages", "history", "_messages", "turns")


def _extract_messages(conversation) -> list | None:
    for attr in _CANDIDATE_ATTRS:
        value = getattr(conversation, attr, None)
        if value is None:
            continue
        if callable(value):
            try:
                value = value()
            except Exception:
                continue
        if isinstance(value, (list, tuple)):
            return list(value)
    return None


class MemoryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("SESSION MEMORY")
        title.setObjectName("section_title")
        layout.addWidget(title)

        self._turns_label = QLabel("--")
        self._chars_label = QLabel("--")
        self._note_label = QLabel("")
        self._note_label.setWordWrap(True)
        self._note_label.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")

        for caption, value_label in (
            ("Turns this session", self._turns_label),
            ("Approx. characters in context", self._chars_label),
        ):
            row = QLabel(caption)
            row.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px; font-weight:600;")
            value_label.setStyleSheet(f"color:{ACCENT}; font-size:16px; font-weight:800;")
            layout.addWidget(row)
            layout.addWidget(value_label)

        layout.addWidget(self._note_label)
        layout.addStretch(1)

    def refresh(self, conversation):
        messages = _extract_messages(conversation)
        if messages is None:
            self._turns_label.setText("N/A")
            self._chars_label.setText("N/A")
            self._note_label.setText(
                "Conversation's internal structure isn't exposed in a way this "
                "panel recognizes. Add an as_list() method to Conversation to "
                "populate this fully."
            )
            return

        self._turns_label.setText(str(len(messages)))
        total_chars = 0
        for item in messages:
            if isinstance(item, dict):
                total_chars += len(str(item.get("content", "")))
            else:
                total_chars += len(str(item))
        self._chars_label.setText(f"~{total_chars:,}")
        self._note_label.setText("")
