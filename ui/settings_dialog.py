"""
Settings dialog.

Per the project's own rule ("do not modify config.py automatically unless
necessary"), this dialog is read-first: it loads whichever of the expected
attributes actually exist on the config module and displays them for
editing in-memory. Wiring `_save` up to actually persist back to
config.py (or a separate settings.json) is left as an explicit, visible
TODO rather than silently rewriting the user's config file.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ui.theme import TEXT_MUTED

# name -> (attribute on config module, kind)
# kind is one of: "text", "float", "choice"
_CANDIDATE_FIELDS = [
    ("Wake word", "WAKE_WORD", "text"),
    ("Wake threshold", "WAKE_THRESHOLD", "float"),
    ("Whisper model", "WHISPER_MODEL", "text"),
    ("Whisper device", "WHISPER_DEVICE", "text"),
    ("Whisper compute type", "WHISPER_COMPUTE_TYPE", "text"),
    ("Ollama model", "OLLAMA_MODEL", "text"),
    ("Temperature", "OLLAMA_TEMPERATURE", "float"),
    ("TTS voice", "TTS_VOICE", "text"),
    ("Microphone", "MICROPHONE_DEVICE", "text"),
    ("Speech timeout (s)", "SPEECH_TIMEOUT", "float"),
]


class SettingsDialog(QDialog):
    def __init__(self, config_module, parent=None):
        super().__init__(parent)
        self.setWindowTitle("JARVIS Settings")
        self.setMinimumWidth(380)
        self.config_module = config_module
        self._fields: dict[str, object] = {}

        outer = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        found_any = False
        for label, attr, kind in _CANDIDATE_FIELDS:
            if not hasattr(config_module, attr):
                continue
            found_any = True
            current = getattr(config_module, attr)

            if kind == "float":
                widget = QDoubleSpinBox()
                widget.setRange(0.0, 1000.0)
                widget.setDecimals(2)
                try:
                    widget.setValue(float(current))
                except (TypeError, ValueError):
                    pass
            else:
                widget = QLineEdit(str(current))

            self._fields[attr] = widget
            form.addRow(label, widget)

        outer.addLayout(form)

        if not found_any:
            note = QLabel(
                "No recognized settings attributes were found on config.py.\n"
                "Add the expected names (see settings_dialog.py) to expose them here."
            )
            note.setWordWrap(True)
            note.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px;")
            outer.addWidget(note)

        hint = QLabel(
            "Changes here apply for this session only. Persisting to config.py "
            "is intentionally not wired up yet -- see _save() in settings_dialog.py."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{TEXT_MUTED}; font-size:10px;")
        outer.addWidget(hint)

        save_button = QPushButton("Apply for this session")
        save_button.setObjectName("primary_button")
        save_button.clicked.connect(self._save)
        outer.addWidget(save_button)

    def _save(self):
        for attr, widget in self._fields.items():
            if isinstance(widget, QDoubleSpinBox):
                value = widget.value()
            elif isinstance(widget, QComboBox):
                value = widget.currentText()
            else:
                value = widget.text()
            # Session-only: mutate the already-imported module object so the
            # rest of the running app sees the new value immediately, without
            # touching the config.py file on disk.
            setattr(self.config_module, attr, value)
        self.accept()
