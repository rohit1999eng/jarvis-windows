import random
import sys
import time
import traceback

import psutil

from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt, QTimer, QRectF
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import WAKE_ACK_PHRASES, OLLAMA_MODEL
from stt import record_command, transcribe
from tts import speak
from llm import Conversation, ask


# ---------------------------------------------------------------------------
# Animated JARVIS core
# ---------------------------------------------------------------------------

class JarvisCore(QWidget):
    """Animated central JARVIS core that reflects the current system state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = "SYSTEMS ONLINE"
        self.phase = 0.0
        self.setMinimumSize(260, 260)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(40)

    def set_state(self, state: str):
        self.state = state.upper()
        self.update()

    def _animate(self):
        self.phase += 0.09
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        cx = rect.center().x()
        cy = rect.center().y()

        # Background
        painter.fillRect(rect, QColor("#0b0f15"))

        # State-dependent pulse
        active = self.state not in {"SYSTEMS ONLINE", "ERROR"}
        pulse = 1.0 + (0.06 * (0.5 + 0.5 * __import__("math").sin(self.phase)))
        if active:
            pulse += 0.04 * __import__("math").sin(self.phase * 2.0)

        radius = 66 * pulse

        # Outer rings
        for i, base in enumerate((92, 112, 132)):
            alpha = max(35, 110 - i * 25)
            pen = QPen(QColor(50, 205, 255, alpha))
            pen.setWidth(2 if i == 0 else 1)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(
                QRectF(cx - base, cy - base, base * 2, base * 2)
            )

        # Rotating orbit marks
        import math
        for i in range(8):
            angle = self.phase * (0.8 if i % 2 == 0 else -0.55) + i * math.pi / 4
            orbit = 112
            x = cx + math.cos(angle) * orbit
            y = cy + math.sin(angle) * orbit
            size = 5 if i % 2 == 0 else 3
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("#65d9ff")))
            painter.drawEllipse(QRectF(x - size, y - size, size * 2, size * 2))

        # Core glow rings
        for r, alpha in ((radius + 18, 30), (radius + 10, 55), (radius, 120)):
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor(45, 200, 255, alpha)))
            painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        painter.setBrush(QBrush(QColor("#65d9ff")))
        painter.drawEllipse(QRectF(cx - radius * 0.72, cy - radius * 0.72,
                                   radius * 1.44, radius * 1.44))

        # Inner core
        painter.setBrush(QBrush(QColor("#07131c")))
        painter.drawEllipse(QRectF(cx - radius * 0.45, cy - radius * 0.45,
                                   radius * 0.90, radius * 0.90))

        # Center dot
        painter.setBrush(QBrush(QColor("#65d9ff")))
        painter.drawEllipse(QRectF(cx - 8, cy - 8, 16, 16))

        # State label
        painter.setPen(QColor("#65d9ff"))
        painter.setFont(QFont("DejaVu Sans", 10, QFont.Bold))
        label = self.state
        metrics = painter.fontMetrics()
        painter.drawText(
            cx - metrics.horizontalAdvance(label) / 2,
            cy + 160,
            label,
        )


# ---------------------------------------------------------------------------
# Metric card
# ---------------------------------------------------------------------------

class MetricCard(QFrame):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("metric_card")

        self.title = QLabel(title.upper())
        self.title.setObjectName("metric_title")

        self.value = QLabel("--")
        self.value.setObjectName("metric_value")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        layout.addWidget(self.title)
        layout.addWidget(self.value)

    def set_value(self, value: str):
        self.value.setText(value)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class JarvisWorker(QObject):
    finished = Signal()
    status_changed = Signal(str)
    user_message = Signal(str)
    jarvis_message = Signal(str)
    error = Signal(str)
    performance = Signal(float, float, float, float, float)

    @Slot()
    def listen_once(self):
        try:
            self.status_changed.emit("LISTENING")

            speak(random.choice(WAKE_ACK_PHRASES))

            self.status_changed.emit("RECORDING COMMAND")

            record_start = time.perf_counter()
            audio = record_command()
            record_time = time.perf_counter() - record_start

            self.status_changed.emit("TRANSCRIBING")

            stt_start = time.perf_counter()
            user_text = transcribe(audio)
            stt_time = time.perf_counter() - stt_start

            if not user_text.strip():
                self.jarvis_message.emit("I didn't catch that.")
                speak("I didn't catch that.")
                return

            self.user_message.emit(user_text)

            self.status_changed.emit("THINKING")

            llm_start = time.perf_counter()
            reply = ask(self.conversation, user_text)
            llm_time = time.perf_counter() - llm_start

            self.jarvis_message.emit(reply)

            self.status_changed.emit("SPEAKING")

            tts_start = time.perf_counter()
            speak(reply)
            tts_time = time.perf_counter() - tts_start

            total_time = record_time + stt_time + llm_time + tts_time

            self.performance.emit(
                record_time,
                stt_time,
                llm_time,
                tts_time,
                total_time,
            )

            self.status_changed.emit("SYSTEMS ONLINE")

        except Exception:
            details = traceback.format_exc()
            self.error.emit(details)
            self.status_changed.emit("ERROR")

        finally:
            self.finished.emit()

    def set_conversation(self, conversation):
        self.conversation = conversation


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class JarvisWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("JARVIS")
        self.resize(1250, 780)
        self.setMinimumSize(1050, 680)

        self.conversation = Conversation()
        self.thread = None
        self.worker = None

        self._build_ui()
        self._start_metrics_timer()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        # Header
        header = QHBoxLayout()

        title_box = QVBoxLayout()
        title = QLabel("J A R V I S")
        title.setObjectName("main_title")

        subtitle = QLabel("LOCAL INTELLIGENCE SYSTEM")
        subtitle.setObjectName("subtitle")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        header.addLayout(title_box)
        header.addStretch()

        self.connection = QLabel("● OLLAMA ONLINE")
        self.connection.setObjectName("online_badge")

        self.model_badge = QLabel(f"QWEN3 • {OLLAMA_MODEL}")
        self.model_badge.setObjectName("model_badge")

        header.addWidget(self.connection)
        header.addWidget(self.model_badge)

        root.addLayout(header)

        # Main split
        main = QHBoxLayout()
        main.setSpacing(14)

        # Left: core
        left = QFrame()
        left.setObjectName("panel")

        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)

        self.core = JarvisCore()
        left_layout.addWidget(self.core, 1)

        self.state_label = QLabel("● SYSTEMS ONLINE")
        self.state_label.setObjectName("state_label")
        self.state_label.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.state_label)

        main.addWidget(left, 1)

        # Right: conversation
        right = QFrame()
        right.setObjectName("panel")

        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)

        conversation_title = QLabel("CONVERSATION")
        conversation_title.setObjectName("section_title")
        right_layout.addWidget(conversation_title)

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText(
            "Your conversation with JARVIS will appear here..."
        )
        right_layout.addWidget(self.chat, 1)

        self.activity = QLabel("Ready for command.")
        self.activity.setObjectName("activity")
        right_layout.addWidget(self.activity)

        main.addWidget(right, 2)

        root.addLayout(main, 1)

        # Metrics
        metrics = QGridLayout()
        metrics.setSpacing(8)

        self.cpu_card = MetricCard("CPU")
        self.ram_card = MetricCard("RAM")
        self.gpu_card = MetricCard("GPU")
        self.vram_card = MetricCard("VRAM")
        self.llm_card = MetricCard("OLLAMA")
        self.tts_card = MetricCard("TTS")
        self.total_card = MetricCard("TOTAL")

        cards = [
            self.cpu_card,
            self.ram_card,
            self.gpu_card,
            self.vram_card,
            self.llm_card,
            self.tts_card,
            self.total_card,
        ]

        for i, card in enumerate(cards):
            metrics.addWidget(card, 0, i)

        root.addLayout(metrics)

        # Controls
        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.listen_button = QPushButton("🎙  START LISTENING")
        self.listen_button.setObjectName("primary_button")
        self.listen_button.setMinimumHeight(52)
        self.listen_button.clicked.connect(self.start_listening)

        self.clear_button = QPushButton("CLEAR CHAT")
        self.clear_button.setMinimumHeight(52)
        self.clear_button.clicked.connect(self.clear_chat)

        self.stop_button = QPushButton("STOP")
        self.stop_button.setMinimumHeight(52)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_worker)

        controls.addWidget(self.listen_button, 2)
        controls.addWidget(self.stop_button, 1)
        controls.addWidget(self.clear_button, 1)

        root.addLayout(controls)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0b0f15;
                color: #dcefff;
                font-family: "DejaVu Sans";
            }

            QFrame#panel {
                background-color: #111720;
                border: 1px solid #20384a;
                border-radius: 14px;
            }

            QLabel#main_title {
                color: #65d9ff;
                font-size: 31px;
                font-weight: 800;
                letter-spacing: 5px;
            }

            QLabel#subtitle {
                color: #5d7f91;
                font-size: 10px;
                letter-spacing: 3px;
            }

            QLabel#online_badge {
                color: #55ff99;
                background-color: #10251c;
                border: 1px solid #245d40;
                border-radius: 10px;
                padding: 8px 12px;
                font-weight: bold;
            }

            QLabel#model_badge {
                color: #65d9ff;
                background-color: #10212b;
                border: 1px solid #28546b;
                border-radius: 10px;
                padding: 8px 12px;
                font-weight: bold;
            }

            QLabel#state_label {
                color: #65d9ff;
                font-size: 15px;
                font-weight: bold;
                padding: 8px;
            }

            QLabel#section_title {
                color: #65d9ff;
                font-size: 13px;
                font-weight: bold;
                letter-spacing: 2px;
                padding-bottom: 4px;
            }

            QTextEdit {
                background-color: #0b1017;
                color: #dcefff;
                border: 1px solid #1f3b4c;
                border-radius: 10px;
                padding: 12px;
                font-size: 14px;
                selection-background-color: #16455c;
            }

            QLabel#activity {
                color: #6f94a8;
                padding: 5px;
            }

            QFrame#metric_card {
                background-color: #101821;
                border: 1px solid #203b4b;
                border-radius: 10px;
                min-width: 125px;
            }

            QLabel#metric_title {
                color: #58788a;
                font-size: 9px;
                font-weight: bold;
            }

            QLabel#metric_value {
                color: #65d9ff;
                font-size: 14px;
                font-weight: bold;
            }

            QPushButton {
                background-color: #111d27;
                color: #65d9ff;
                border: 1px solid #2b566d;
                border-radius: 10px;
                font-size: 13px;
                font-weight: bold;
                padding: 8px;
            }

            QPushButton:hover {
                background-color: #163447;
                border-color: #65d9ff;
            }

            QPushButton:pressed {
                background-color: #0d2735;
            }

            QPushButton:disabled {
                color: #4d626e;
                border-color: #293943;
                background-color: #10151a;
            }

            QPushButton#primary_button {
                background-color: #123f54;
                border: 1px solid #65d9ff;
                font-size: 15px;
            }

            QPushButton#primary_button:hover {
                background-color: #18536d;
            }

            QProgressBar {
                border: 1px solid #203b4b;
                border-radius: 5px;
                background-color: #0b1017;
            }

            QProgressBar::chunk {
                background-color: #65d9ff;
                border-radius: 4px;
            }
        """)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def _start_metrics_timer(self):
        self.metrics_timer = QTimer(self)
        self.metrics_timer.timeout.connect(self.update_metrics)
        self.metrics_timer.start(1500)
        self.update_metrics()

    def update_metrics(self):
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()

            self.cpu_card.set_value(f"{cpu:.1f}%")
            self.ram_card.set_value(
                f"{mem.used / (1024**3):.1f} / "
                f"{mem.total / (1024**3):.0f} GB"
            )

            # NVIDIA stats
            try:
                import subprocess

                result = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,utilization.gpu,temperature.gpu,"
                        "memory.used,memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )

                if result.returncode == 0 and result.stdout.strip():
                    values = [
                        x.strip()
                        for x in result.stdout.strip().split(",", 4)
                    ]

                    if len(values) == 5:
                        name, util, temp, used, total = values

                        short_name = name.replace("NVIDIA GeForce ", "")
                        self.gpu_card.set_value(
                            f"{short_name} • {util}%"
                        )
                        self.vram_card.set_value(
                            f"{float(used)/1024:.1f} / "
                            f"{float(total)/1024:.1f} GB"
                        )
                    else:
                        self.gpu_card.set_value("Unavailable")
                        self.vram_card.set_value("--")
                else:
                    self.gpu_card.set_value("Unavailable")
                    self.vram_card.set_value("--")

            except Exception:
                self.gpu_card.set_value("Unavailable")
                self.vram_card.set_value("--")

        except Exception:
            pass

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------

    def show_user_message(self, message):
        self.chat.append(
            f'<div style="margin:10px 0;">'
            f'<span style="color:#6f94a8;font-weight:bold;">YOU</span><br>'
            f'<span style="color:#e6f7ff;">{message}</span>'
            f'</div>'
        )
        self.activity.setText("JARVIS is processing your request...")

    def show_jarvis_message(self, message):
        self.chat.append(
            f'<div style="margin:10px 0;">'
            f'<span style="color:#65d9ff;font-weight:bold;">JARVIS</span><br>'
            f'<span style="color:#dcefff;">{message}</span>'
            f'</div>'
        )
        self.activity.setText("Response ready.")

    def clear_chat(self):
        self.chat.clear()
        self.conversation = Conversation()
        self.activity.setText("Conversation cleared.")

    # ------------------------------------------------------------------
    # Listening
    # ------------------------------------------------------------------

    def start_listening(self):
        if self.thread is not None:
            return

        self.listen_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.update_state("STARTING")

        self.thread = QThread()
        self.worker = JarvisWorker()

        self.worker.set_conversation(self.conversation)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.listen_once)

        self.worker.status_changed.connect(self.update_state)
        self.worker.user_message.connect(self.show_user_message)
        self.worker.jarvis_message.connect(self.show_jarvis_message)
        self.worker.error.connect(self.show_error)
        self.worker.performance.connect(self.update_performance)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.listening_finished)

        self.thread.start()

    def stop_worker(self):
        # The existing audio/LLM functions are synchronous, so this button
        # cannot safely interrupt an active recording or inference call.
        # It prevents starting another job and communicates the limitation.
        self.activity.setText(
            "Current operation cannot be interrupted safely; waiting for completion."
        )

    def listening_finished(self):
        self.listen_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        if self.state_label.text().endswith("ERROR"):
            return

        self.update_state("SYSTEMS ONLINE")

        self.thread = None
        self.worker = None

    # ------------------------------------------------------------------
    # State / performance
    # ------------------------------------------------------------------

    def update_state(self, message):
        self.state_label.setText(f"● {message}")
        self.core.set_state(message)

        if message == "ERROR":
            self.state_label.setStyleSheet(
                "color:#ff647c;font-size:15px;font-weight:bold;"
            )
        else:
            self.state_label.setStyleSheet(
                "color:#65d9ff;font-size:15px;font-weight:bold;"
            )

        self.activity.setText(message)

    def update_performance(
        self,
        record_time,
        stt_time,
        llm_time,
        tts_time,
        total_time,
    ):
        self.llm_card.set_value(f"{llm_time:.2f}s")
        self.tts_card.set_value(f"{tts_time:.2f}s")
        self.total_card.set_value(f"{total_time:.2f}s")

    def show_error(self, details):
        self.chat.append(
            f'<div style="margin:10px 0;">'
            f'<span style="color:#ff647c;font-weight:bold;">ERROR</span><br>'
            f'<pre style="color:#ff9aaa;">{details}</pre>'
            f'</div>'
        )
        self.activity.setText("An error occurred. Check the terminal output.")

    def closeEvent(self, event):
        if self.thread is not None and self.thread.isRunning():
            self.activity.setText("Waiting for current JARVIS operation...")
            event.ignore()
            return

        event.accept()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = JarvisWindow()
    window.show()

    sys.exit(app.exec())
