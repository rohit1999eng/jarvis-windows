"""Pipeline latency breakdown -- useful for tuning the local stack."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QGridLayout, QLabel

from ui.theme import ACCENT, TEXT_MUTED


class PerformancePanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel_flat")

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(6)

        title = QLabel("PERFORMANCE")
        title.setObjectName("section_title")
        layout.addWidget(title, 0, 0, 1, 2)

        self._rows: dict[str, QLabel] = {}
        for i, key in enumerate(("RECORD", "STT", "LLM", "TOOL", "TTS", "TOTAL"), start=1):
            name = QLabel(key)
            name.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px; font-weight:600;")
            value = QLabel("--")
            weight = 800 if key == "TOTAL" else 600
            value.setStyleSheet(f"color:{ACCENT}; font-size:12px; font-weight:{weight};")
            layout.addWidget(name, i, 0)
            layout.addWidget(value, i, 1)
            self._rows[key] = value

    def update_times(
        self,
        record: float = 0.0,
        stt: float = 0.0,
        llm: float = 0.0,
        tool: float = 0.0,
        tts: float = 0.0,
        total: float | None = None,
    ):
        if total is None:
            total = record + stt + llm + tool + tts

        values = {
            "RECORD": record,
            "STT": stt,
            "LLM": llm,
            "TOOL": tool,
            "TTS": tts,
            "TOTAL": total,
        }
        for key, seconds in values.items():
            self._rows[key].setText(f"{seconds:.2f}s")
