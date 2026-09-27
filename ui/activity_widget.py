"""
A slim, single-line "what is JARVIS doing right now" indicator.

This is deliberately separate from the permanent conversation timeline
(see chat_widget.ConversationView): the timeline is a durable record,
this widget is a transient live status -- it shows the current step and
clears itself once a turn finishes, so raw tool-call JSON never leaks to
the user.

It is driven by an optional ``on_event(event_type, name, detail)`` hook.
If the project's ``llm.ask`` function does not (yet) support an
``on_event`` callback, this widget simply never receives events and stays
on its idle message -- nothing else in the GUI depends on it.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel

from ui.theme import ROLE_TOOL, TEXT_MUTED, TEXT_SECONDARY

_ICONS = {
    "thinking": "🧠",
    "tool_request": "🔧",
    "tool_executing": "⚙️",
    "tool_result": "✓",
    "speaking": "🔊",
    "idle": "•",
}


class ToolActivityBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel_flat")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(8)

        self._icon = QLabel(_ICONS["idle"])
        self._icon.setStyleSheet("font-size:14px;")

        self._text = QLabel("Ready.")
        self._text.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")

        layout.addWidget(self._icon)
        layout.addWidget(self._text, 1)

        self._clear_timer = QTimer(self)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.timeout.connect(self.reset)

    def reset(self):
        self._icon.setText(_ICONS["idle"])
        self._text.setText("Ready.")
        self._text.setStyleSheet(f"color:{TEXT_MUTED}; font-size:12px;")

    def on_event(self, event_type: str, name: str = "", detail: str = ""):
        event_type = (event_type or "").lower()
        icon = _ICONS.get(event_type, "•")
        self._icon.setText(icon)

        if event_type == "thinking":
            message = "Thinking..."
        elif event_type == "tool_request":
            message = f"Tool requested: {name}"
        elif event_type == "tool_executing":
            message = f"Executing {name}..."
        elif event_type == "tool_result":
            message = f"{name} completed" + (f" — {detail}" if detail else "")
        elif event_type == "speaking":
            message = "Speaking response..."
        else:
            message = detail or name or "Working..."

        color = ROLE_TOOL if event_type.startswith("tool") else TEXT_SECONDARY
        self._text.setStyleSheet(f"color:{color}; font-size:12px; font-weight:600;")
        self._text.setText(message)

        # tool-result messages fade back to idle after a moment so the bar
        # doesn't get stuck reading "completed" forever
        if event_type == "tool_result":
            self._clear_timer.start(4000)
