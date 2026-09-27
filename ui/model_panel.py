"""
Static + best-effort-live model information.

MODEL / BACKEND / MODE are known from config.py directly. CONTEXT and
QUANTIZATION are not something the existing backend exposes, so this panel
optionally asks Ollama's own local HTTP API (POST /api/show) for them.

That request runs on a single, persistent background QThread that polls on
its own timer -- rather than spinning up and tearing down a new QThread on
every check -- so a transient failure (e.g. Ollama still warming up when
the GUI starts) recovers automatically instead of showing OFFLINE forever,
without the overhead of repeatedly creating OS threads. `connection_changed`
lets other widgets (e.g. the header badge) mirror the real status instead
of a static hardcoded label.
"""

from __future__ import annotations

import json
import urllib.request

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel

from ui.theme import ACCENT, ERROR, SUCCESS, TEXT_MUTED

OLLAMA_SHOW_URL = "http://localhost:11434/api/show"
POLL_INTERVAL_MS = 15000


class _OllamaInfoFetcher(QObject):
    """Lives on its own thread for the app's lifetime; polls on a loop."""

    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, model_name: str):
        super().__init__()
        self.model_name = model_name

    @Slot()
    def start_polling(self):
        # Created here so the QTimer's thread affinity is the worker
        # thread, not whatever thread constructed this object.
        self._timer = QTimer()
        self._timer.timeout.connect(self._poll)
        self._timer.start(POLL_INTERVAL_MS)
        self._poll()  # first check immediately, don't wait 15s

    @Slot()
    def stop_polling(self):
        # Must run on this object's own thread. It's wired to the worker
        # QThread's `finished` signal, which fires from inside that same
        # thread just before it stops -- so stopping the timer here (rather
        # than letting it get garbage-collected later from the GUI thread)
        # avoids a "killTimer from another thread" warning at shutdown.
        if hasattr(self, "_timer"):
            self._timer.stop()

    def _poll(self):
        try:
            payload = json.dumps({"name": self.model_name}).encode("utf-8")
            request = urllib.request.Request(
                OLLAMA_SHOW_URL, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=3) as response:
                data = json.loads(response.read().decode("utf-8"))
            self.finished.emit(data)
        except Exception as exc:  # noqa: BLE001 - purely informational
            self.failed.emit(str(exc))


class ModelPanel(QFrame):
    connection_changed = Signal(bool)

    def __init__(self, model_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("panel_flat")
        self.model_name = model_name

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(6)

        title = QLabel("MODEL")
        title.setObjectName("section_title")
        layout.addWidget(title, 0, 0, 1, 2)

        self._rows: dict[str, QLabel] = {}
        fields = [
            ("MODEL", model_name),
            ("BACKEND", "Ollama"),
            ("MODE", "Local"),
            ("CONTEXT", "--"),
            ("QUANTIZATION", "--"),
        ]
        for i, (key, initial) in enumerate(fields, start=1):
            name = QLabel(key)
            name.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px; font-weight:600;")
            value = QLabel(initial)
            value.setStyleSheet(f"color:{ACCENT}; font-size:12px; font-weight:700;")
            layout.addWidget(name, i, 0)
            layout.addWidget(value, i, 1)
            self._rows[key] = value

        conn_name = QLabel("CONNECTION")
        conn_name.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px; font-weight:600;")
        self.connection_value = QLabel("● CHECKING")
        self.connection_value.setStyleSheet(f"color:{TEXT_MUTED}; font-size:12px; font-weight:700;")
        layout.addWidget(conn_name, len(fields) + 1, 0)
        layout.addWidget(self.connection_value, len(fields) + 1, 1)

        self._thread = QThread(self)
        self._fetcher = _OllamaInfoFetcher(model_name)
        self._fetcher.moveToThread(self._thread)
        self._thread.started.connect(self._fetcher.start_polling)
        self._thread.finished.connect(self._fetcher.stop_polling)
        self._fetcher.finished.connect(self._on_info)
        self._fetcher.failed.connect(self._on_failed)
        self._thread.start()

    # ------------------------------------------------------------------

    def shutdown(self):
        """Stop the background polling thread cleanly on app exit."""
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1500)

    def _set_connection(self, online: bool):
        if online:
            self.connection_value.setText("● ONLINE")
            self.connection_value.setStyleSheet(f"color:{SUCCESS}; font-size:12px; font-weight:700;")
        else:
            self.connection_value.setText("● OFFLINE")
            self.connection_value.setStyleSheet(f"color:{ERROR}; font-size:12px; font-weight:700;")
        self.connection_changed.emit(online)

    def _on_info(self, data: dict):
        self._set_connection(True)
        details = data.get("details", {}) or {}
        quant = details.get("quantization_level")
        if quant:
            self._rows["QUANTIZATION"].setText(quant)

        # context length usually lives in model_info under a key like
        # "<family>.context_length" -- search for it rather than guessing
        # the exact family name.
        model_info = data.get("model_info", {}) or {}
        for key, value in model_info.items():
            if key.endswith("context_length"):
                context_k = int(value) // 1000
                self._rows["CONTEXT"].setText(f"{context_k}K" if context_k else str(value))
                break

    def _on_failed(self, _reason: str):
        self._set_connection(False)
