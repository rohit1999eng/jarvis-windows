"""
The animated central visualization: the "core" that reflects JARVIS's
current state, plus a lightweight audio waveform strip underneath it.

Both widgets paint with native QPainter only -- no browser engine, no
external graphics libraries -- so they stay cheap to run continuously.
"""

from __future__ import annotations

import math
from collections import deque

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ui.theme import ACCENT, ERROR, TEXT_MUTED, state_color

# Canonical states the core understands. Anything else passed to
# ``set_state`` is mapped to the closest one of these (see _normalize).
IDLE = "IDLE"
LISTENING = "LISTENING"
RECORDING = "RECORDING"
TRANSCRIBING = "TRANSCRIBING"
THINKING = "THINKING"
TOOL_EXECUTION = "TOOL EXECUTION"
SPEAKING = "SPEAKING"
ERROR_STATE = "ERROR"

_STATE_ALIASES = {
    "SYSTEMS ONLINE": IDLE,
    "STARTING": LISTENING,
    "RECORDING COMMAND": RECORDING,
}


def _normalize(state: str) -> str:
    state = (state or "").upper()
    return _STATE_ALIASES.get(state, state if state else IDLE)


class AudioWaveform(QWidget):
    """
    A compact bar-style waveform. The worker thread feeds it amplitude
    samples via :meth:`push_level` (0.0-1.0); when nothing is being pushed
    it decays to a flat, subtle line so it's visually obvious when the
    microphone is idle vs. active.
    """

    BAR_COUNT = 42

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(46)
        self.setAccessibleName("Microphone activity level")
        self.setToolTip("Live microphone amplitude while recording")
        self._levels = deque([0.02] * self.BAR_COUNT, maxlen=self.BAR_COUNT)
        self._active = False

        # The decay timer only needs to run while bars are actually moving
        # back toward baseline. Running it unconditionally forever (as the
        # first version did) repaints ~22x/sec even while nothing is
        # happening -- wasted work on a machine that's also busy running
        # Whisper/Ollama/Piper. It is started on demand and stops itself
        # once the waveform has visibly settled.
        self._decay_timer = QTimer(self)
        self._decay_timer.timeout.connect(self._decay)

    def set_active(self, active: bool):
        self._active = active
        if active:
            self._decay_timer.stop()
        else:
            # let the existing bars fall back to baseline rather than
            # snapping instantly -- reads as "microphone went quiet".
            if not self._decay_timer.isActive():
                self._decay_timer.start(45)
        self.update()

    def push_level(self, level: float):
        level = max(0.0, min(1.0, float(level)))
        self._levels.append(level)
        self.update()

    def _decay(self):
        if self._active:
            self._decay_timer.stop()
            return
        last = self._levels[-1] if self._levels else 0.02
        settled = last <= 0.021
        if settled:
            self._decay_timer.stop()
            return
        self._levels.append(max(0.02, last * 0.85))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()

        color = QColor(ACCENT if self._active else TEXT_MUTED)
        bar_width = rect.width() / (self.BAR_COUNT * 1.6)
        gap = bar_width * 0.6
        x = gap
        mid_y = rect.height() / 2

        painter.setPen(Qt.NoPen)
        for level in self._levels:
            h = max(2.0, level * (rect.height() * 0.9))
            alpha = 90 if not self._active else 200
            painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), alpha)))
            painter.drawRoundedRect(
                QRectF(x, mid_y - h / 2, bar_width, h), 1.5, 1.5
            )
            x += bar_width + gap


class JarvisCore(QWidget):
    """Animated central JARVIS core that reflects the current system state."""

    # Idle just breathes slowly, so it doesn't need 30fps to look smooth;
    # active states get the full frame rate because their speed is what
    # communicates "working". Keeping idle at a lower cadence noticeably
    # cuts CPU use for what is, most of the time, a background assistant.
    _IDLE_INTERVAL_MS = 90
    _ACTIVE_INTERVAL_MS = 33

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = IDLE
        self.phase = 0.0
        self.setMinimumSize(240, 240)
        self.setAccessibleName("JARVIS status core")

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(self._IDLE_INTERVAL_MS)
        self._current_interval = self._IDLE_INTERVAL_MS

    # ------------------------------------------------------------------

    def set_state(self, state: str):
        self.state = _normalize(state)
        self.setToolTip(f"Status: {self.state}")

        target_interval = self._IDLE_INTERVAL_MS if self.state == IDLE else self._ACTIVE_INTERVAL_MS
        if target_interval != self._current_interval:
            self.timer.setInterval(target_interval)
            self._current_interval = target_interval

        self.update()

    def _animate(self):
        # Skip work entirely while the widget isn't actually on screen
        # (minimized window, hidden tab, etc.) -- there's nothing to save
        # by advancing the animation phase if nobody can see it, and it
        # avoids queuing up repaint events the compositor will throw away.
        if not self.isVisible():
            return

        speed = {
            THINKING: 0.16,
            TOOL_EXECUTION: 0.20,
            RECORDING: 0.11,
            SPEAKING: 0.13,
            ERROR_STATE: 0.05,
        }.get(self.state, 0.06)
        self.phase += speed
        self.update()

    # ------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        cx, cy = rect.center().x(), rect.center().y()
        base_radius = min(rect.width(), rect.height()) * 0.22

        accent = QColor(state_color(self.state))

        # Idle breathes slowly; active states pulse harder / faster.
        pulse = 1.0 + 0.05 * math.sin(self.phase)
        if self.state not in (IDLE,):
            pulse += 0.035 * math.sin(self.phase * 2.2)
        radius = base_radius * pulse

        # --- outer static rings -------------------------------------------------
        for i, factor in enumerate((1.55, 1.85, 2.15)):
            alpha = max(25, 90 - i * 22)
            pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), alpha))
            pen.setWidth(2 if i == 0 else 1)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            r = base_radius * factor
            painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # --- orbiting particles (speed communicates "thinking/working") --------
        n_particles = 10 if self.state in (THINKING, TOOL_EXECUTION) else 8
        for i in range(n_particles):
            direction = 1 if i % 2 == 0 else -1
            angle = self.phase * direction * 0.9 + i * (2 * math.pi / n_particles)
            orbit = base_radius * 1.85
            x = cx + math.cos(angle) * orbit
            y = cy + math.sin(angle) * orbit
            size = 4.5 if i % 2 == 0 else 3
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(accent))
            painter.drawEllipse(QRectF(x - size, y - size, size * 2, size * 2))

        # --- glow shell -----------------------------------------------------
        for r, alpha in (
            (radius + base_radius * 0.28, 28),
            (radius + base_radius * 0.15, 55),
            (radius, 130),
        ):
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(accent.red(), accent.green(), accent.blue(), alpha)))
            painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        # --- inner core body --------------------------------------------------
        painter.setBrush(QBrush(accent))
        painter.drawEllipse(
            QRectF(cx - radius * 0.72, cy - radius * 0.72, radius * 1.44, radius * 1.44)
        )

        painter.setBrush(QBrush(QColor("#07131c")))
        painter.drawEllipse(
            QRectF(cx - radius * 0.46, cy - radius * 0.46, radius * 0.92, radius * 0.92)
        )

        # error state gets a hard warning cross instead of a soft dot
        if self.state == ERROR_STATE:
            pen = QPen(QColor(ERROR), 3)
            painter.setPen(pen)
            d = radius * 0.18
            painter.drawLine(int(cx - d), int(cy - d), int(cx + d), int(cy + d))
            painter.drawLine(int(cx - d), int(cy + d), int(cx + d), int(cy - d))
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(accent))
            painter.drawEllipse(QRectF(cx - 7, cy - 7, 14, 14))

        # --- state label ---------------------------------------------------
        painter.setPen(accent)
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        label = self.state
        metrics = painter.fontMetrics()
        painter.drawText(
            int(cx - metrics.horizontalAdvance(label) / 2),
            int(cy + base_radius * 2.55),
            label,
        )
