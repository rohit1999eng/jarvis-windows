"""
JARVIS desktop GUI -- entry point.

This file wires together the widgets in ui/ around the existing,
unmodified backend:

    Python -> openWakeWord -> faster-whisper STT -> Ollama -> Qwen3:8B
    -> Ollama native tool calling -> tools.py -> tool result
    -> Qwen3 final response -> Piper TTS

The public interface this GUI depends on is unchanged:

    from llm import Conversation, ask
    from stt import record_command, transcribe
    from tts import speak
    from config import WAKE_ACK_PHRASES, OLLAMA_MODEL

Two OPTIONAL, backward-compatible hooks are attempted and gracefully
skipped if unsupported (see _ask_with_optional_hooks / _record_with_optional_level):

    ask(conversation, text, on_event=callback)          # tool-call lifecycle events
    record_command(level_callback=callback)              # live mic amplitude

Neither hook is required for the GUI to work. Without them you still get
the full timeline, system monitor, performance panel, etc. -- you just
won't see live tool-activity chips or a reactive waveform; the waveform
falls back to a simple "recording" pulse and the activity bar just shows
generic THINKING / SPEAKING states driven by the existing status signal.
"""

from __future__ import annotations

import logging
import random
import sys
import time
import traceback

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

# Full tracebacks go here instead of into the chat timeline -- a debugging
# tool a developer can tail, not something the end user has to scroll past.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("jarvis")

import config
from config import WAKE_ACK_PHRASES, OLLAMA_MODEL
from stt import record_command, transcribe
from tts import speak
from llm import Conversation, ask

from ui import theme
from ui.core_widget import AudioWaveform, JarvisCore
from ui.chat_widget import ConversationView
from ui.activity_widget import ToolActivityBar
from ui.system_panel import SystemPanel
from ui.performance_panel import PerformancePanel
from ui.model_panel import ModelPanel
from ui.sidebar import Sidebar
from ui.tools_panel import ToolsPanel
from ui.memory_panel import MemoryPanel
from ui.settings_dialog import SettingsDialog


# ---------------------------------------------------------------------------
# Worker: runs one full listen -> think -> speak turn off the GUI thread
# ---------------------------------------------------------------------------

class JarvisWorker(QObject):
    finished = Signal()
    status_changed = Signal(str)
    user_message = Signal(str)
    jarvis_message = Signal(str)
    tool_event = Signal(str, str, str)   # event_type, name, detail
    audio_level = Signal(float)          # 0.0 - 1.0
    error = Signal(str)
    performance = Signal(float, float, float, float, float, float)  # record, stt, llm, tool, tts, total

    def set_conversation(self, conversation: Conversation):
        self.conversation = conversation

    # ------------------------------------------------------------------
    # Optional-hook helpers. These exist so we never need to touch
    # stt.py / llm.py: if the hook keyword isn't in their signature, the
    # call raises TypeError *before* doing any work, and we transparently
    # retry without it.
    # ------------------------------------------------------------------

    def _record_with_optional_level(self):
        def level_cb(level: float):
            self.audio_level.emit(float(level))

        try:
            return record_command(level_callback=level_cb)
        except TypeError:
            return record_command()

    def _ask_with_optional_events(self, user_text: str):
        tool_seconds = {"total": 0.0}
        tool_start = {}

        def on_event(event_type: str, name: str = "", detail: str = ""):
            if event_type == "tool_executing":
                tool_start[name] = time.perf_counter()
            elif event_type == "tool_result" and name in tool_start:
                tool_seconds["total"] += time.perf_counter() - tool_start.pop(name)
            self.tool_event.emit(event_type, name, detail)

        self.tool_event.emit("thinking", "", "")
        try:
            reply = ask(self.conversation, user_text, on_event=on_event)
        except TypeError:
            reply = ask(self.conversation, user_text)
        return reply, tool_seconds["total"]

    # ------------------------------------------------------------------

    @Slot()
    def listen_once(self):
        try:
            self.status_changed.emit("LISTENING")
            speak(random.choice(WAKE_ACK_PHRASES))

            self.status_changed.emit("RECORDING COMMAND")
            record_start = time.perf_counter()
            audio = self._record_with_optional_level()
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
            reply, tool_time = self._ask_with_optional_events(user_text)
            llm_time = (time.perf_counter() - llm_start) - tool_time

            self.jarvis_message.emit(reply)

            self.status_changed.emit("SPEAKING")
            tts_start = time.perf_counter()
            speak(reply)
            tts_time = time.perf_counter() - tts_start

            total_time = record_time + stt_time + llm_time + tool_time + tts_time
            self.performance.emit(record_time, stt_time, llm_time, tool_time, tts_time, total_time)

            self.status_changed.emit("SYSTEMS ONLINE")

        except Exception:
            self.error.emit(traceback.format_exc())
            self.status_changed.emit("ERROR")

        finally:
            self.finished.emit()


# ---------------------------------------------------------------------------
# Header bar
# ---------------------------------------------------------------------------

class HeaderBar(QFrame):
    def __init__(self, model_name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("panel_flat")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("J A R V I S")
        title.setObjectName("main_title")
        subtitle = QLabel("LOCAL AI COMMAND CENTER")
        subtitle.setObjectName("subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        layout.addLayout(title_box)
        layout.addStretch(1)

        # Starts as "checking" rather than a hardcoded ONLINE -- the real
        # status arrives asynchronously from ModelPanel's connection check.
        self.connection_badge = QLabel("● CHECKING")
        self.connection_badge.setObjectName("model_badge")
        self.connection_badge.setToolTip("Waiting for the first Ollama connectivity check...")
        layout.addWidget(self.connection_badge)

        model_badge = QLabel(f"QWEN3 • {model_name}")
        model_badge.setObjectName("model_badge")
        layout.addWidget(model_badge)

    def set_online(self, online: bool):
        """Mirror the real Ollama connectivity reported by ModelPanel.

        Previously this label was set once at construction and never
        updated, so it could silently claim ONLINE while Ollama was
        actually unreachable -- the single most visible status indicator
        in the app was lying. It's now driven by ModelPanel.connection_changed.
        """
        text = "● ONLINE" if online else "● OFFLINE"
        object_name = "online_badge" if online else "offline_badge"
        self.connection_badge.setText(text)
        self.connection_badge.setToolTip(
            "Ollama is reachable at localhost:11434"
            if online
            else "Ollama did not respond at localhost:11434 -- is it running?"
        )
        if self.connection_badge.objectName() != object_name:
            self.connection_badge.setObjectName(object_name)
            # QSS selectors keyed on objectName only get re-evaluated after
            # an explicit unpolish/polish cycle -- this is the standard Qt
            # idiom for that, not a workaround.
            self.connection_badge.style().unpolish(self.connection_badge)
            self.connection_badge.style().polish(self.connection_badge)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class JarvisWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS — Local AI Command Center")
        self.resize(1400, 860)
        self.setMinimumSize(1150, 720)

        self.conversation = Conversation()
        self.thread: QThread | None = None
        self.worker: JarvisWorker | None = None
        self._close_requested = False

        # Tracks "a turn is in flight" explicitly rather than inferring it
        # from QThread.isRunning(). QThread.start() returns before the OS
        # has actually scheduled the thread, so isRunning() can briefly
        # read False immediately after start_listening() -- a real race
        # that showed up under test: closing the window in that window
        # would skip the "wait for it to finish" path entirely.
        self._turn_in_progress = False

        self._build_ui()

        # Belt-and-suspenders: closeEvent already calls shutdown() on the
        # panels that own background QThreads, but that only fires for a
        # normal window-close. Anything else (app.quit(), Ctrl+C reaching
        # the Qt event loop, a forced quit) skips closeEvent entirely and
        # would otherwise tear the process down while those threads are
        # still alive -- Qt aborts the process when that happens. Hooking
        # aboutToQuit covers every quit path, not just this one window's.
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._shutdown_background_threads)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        self.header = HeaderBar(OLLAMA_MODEL)
        root.addWidget(self.header)

        # ---- middle row: sidebar | core | right pages -------------------
        # A QSplitter (not a plain QHBoxLayout with setFixedWidth panels)
        # so the person using this can actually drag panel boundaries to
        # fit their screen -- fixed-pixel panels didn't adapt to anything
        # narrower or wider than the size this was designed at.
        middle = QSplitter(Qt.Horizontal)
        middle.setChildrenCollapsible(False)
        middle.setHandleWidth(6)

        self.sidebar = Sidebar()
        self.sidebar.page_changed.connect(self._show_page)
        self.sidebar.settings_requested.connect(self._open_settings)
        middle.addWidget(self.sidebar)

        core_panel = QFrame()
        core_panel.setObjectName("panel")
        core_panel.setMinimumWidth(360)
        core_layout = QVBoxLayout(core_panel)
        core_layout.setContentsMargins(14, 14, 14, 14)
        core_layout.setSpacing(8)

        self.core = JarvisCore()
        core_layout.addWidget(self.core, 1)

        self.waveform = AudioWaveform()
        core_layout.addWidget(self.waveform)

        self.state_label = QLabel("● SYSTEMS ONLINE")
        self.state_label.setObjectName("state_label")
        self.state_label.setAlignment(Qt.AlignCenter)
        self.state_label.setAccessibleName("Current JARVIS state")
        core_layout.addWidget(self.state_label)

        middle.addWidget(core_panel)

        right_panel = QFrame()
        right_panel.setObjectName("panel")
        right_panel.setMinimumWidth(260)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(14, 14, 14, 14)

        self.pages = QStackedWidget()
        self._build_pages()
        right_layout.addWidget(self.pages)

        middle.addWidget(right_panel)

        # Initial proportions (sidebar : core : right panel); the person
        # can still drag these -- this just sets a sensible starting point.
        middle.setStretchFactor(0, 0)
        middle.setStretchFactor(1, 3)
        middle.setStretchFactor(2, 0)
        middle.setSizes([150, 700, 300])

        root.addWidget(middle, 3)

        # ---- conversation timeline + live activity ----------------------
        convo_panel = QFrame()
        convo_panel.setObjectName("panel")
        convo_layout = QVBoxLayout(convo_panel)
        convo_layout.setContentsMargins(14, 12, 14, 10)
        convo_layout.setSpacing(6)

        convo_title = QLabel("CONVERSATION / ACTIVITY")
        convo_title.setObjectName("section_title")
        convo_layout.addWidget(convo_title)

        self.conversation_view = ConversationView()
        convo_layout.addWidget(self.conversation_view, 1)

        self.activity_bar = ToolActivityBar()
        convo_layout.addWidget(self.activity_bar)

        root.addWidget(convo_panel, 4)

        # ---- controls -----------------------------------------------------
        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.listen_button = QPushButton("🎙  START LISTENING")
        self.listen_button.setObjectName("primary_button")
        self.listen_button.setMinimumHeight(50)
        self.listen_button.setToolTip("Start a listen -> think -> speak turn (Ctrl+L)")
        self.listen_button.clicked.connect(self.start_listening)

        self.stop_button = QPushButton("STOP")
        self.stop_button.setMinimumHeight(50)
        self.stop_button.setEnabled(False)
        self.stop_button.setToolTip(
            "The active recording/inference/speech call can't be interrupted mid-flight; "
            "this only blocks queuing another turn."
        )
        self.stop_button.clicked.connect(self.stop_worker)

        self.clear_button = QPushButton("CLEAR")
        self.clear_button.setMinimumHeight(50)
        self.clear_button.setToolTip("Clear the conversation timeline and start a fresh session (Ctrl+K)")
        self.clear_button.clicked.connect(self.clear_chat)

        settings_button = QPushButton("SETTINGS")
        settings_button.setMinimumHeight(50)
        settings_button.setToolTip("Open JARVIS settings (Ctrl+,)")
        settings_button.clicked.connect(self._open_settings)

        controls.addWidget(self.listen_button, 2)
        controls.addWidget(self.stop_button, 1)
        controls.addWidget(self.clear_button, 1)
        controls.addWidget(settings_button, 1)

        root.addLayout(controls)

        self.setStyleSheet(theme.stylesheet())
        self._install_shortcuts()

    def _install_shortcuts(self):
        # Keyboard-only path to the two most common actions, for anyone who
        # can't or doesn't want to reach for the mouse. Bound to the window
        # rather than a single button so they work regardless of focus.
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._trigger_listen_shortcut)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.clear_chat)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self._open_settings)

    def _trigger_listen_shortcut(self):
        if self.listen_button.isEnabled():
            self.start_listening()

    def _build_pages(self):
        # name -> page widget is the single source of truth for routing;
        # previously this was a hand-maintained {name: index} dict in
        # _show_page that had to stay in sync with the order pages were
        # added *and* with Sidebar.NAV_ITEMS purely by convention -- one
        # reorder in either place would silently point at the wrong page.
        self._page_widgets: dict[str, QWidget] = {}

        # "System" page: monitor + performance + model, stacked vertically,
        # inside a QScrollArea so it can't get clipped at the window's
        # minimum height instead of just growing off-screen.
        system_content = QWidget()
        system_layout = QVBoxLayout(system_content)
        system_layout.setContentsMargins(0, 0, 6, 0)
        system_layout.setSpacing(14)

        self.system_panel = SystemPanel()
        self.performance_panel = PerformancePanel()
        self.model_panel = ModelPanel(OLLAMA_MODEL)
        self.model_panel.connection_changed.connect(self.header.set_online)

        system_layout.addWidget(self.system_panel)
        system_layout.addWidget(self.performance_panel)
        system_layout.addWidget(self.model_panel)
        system_layout.addStretch(1)

        system_page = QScrollArea()
        system_page.setWidgetResizable(True)
        system_page.setFrameShape(QFrame.NoFrame)
        system_page.setWidget(system_content)
        self._add_page("System", system_page)

        self.tools_panel = ToolsPanel()
        self._add_page("Tools", self.tools_panel)

        self.memory_panel = MemoryPanel()
        self._add_page("Memory", self.memory_panel)

        conversations_page = QWidget()
        conversations_layout = QVBoxLayout(conversations_page)
        title = QLabel("CONVERSATIONS")
        title.setObjectName("section_title")
        note = QLabel(
            "This build keeps a single live session (see the timeline below). "
            "Persisted, multi-session history isn't part of the current backend, "
            "so there's nothing to browse here yet -- wire up a store in "
            "Conversation to populate this list."
        )
        note.setWordWrap(True)
        conversations_layout.addWidget(title)
        conversations_layout.addWidget(note)
        conversations_layout.addStretch(1)
        self._add_page("Conversations", conversations_page)

    def _add_page(self, name: str, widget: QWidget):
        self.pages.addWidget(widget)
        self._page_widgets[name] = widget

    def _show_page(self, name: str):
        widget = self._page_widgets.get(name)
        if widget is None:
            return
        self.pages.setCurrentWidget(widget)
        if name == "Memory":
            self.memory_panel.refresh(self.conversation)

    def _open_settings(self):
        dialog = SettingsDialog(config, self)
        dialog.exec()

    # ------------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------------

    def show_user_message(self, message: str):
        self.conversation_view.add_message("USER", message)

    def show_jarvis_message(self, message: str):
        self.conversation_view.add_message("JARVIS", message)

    def on_tool_event(self, event_type: str, name: str, detail: str):
        self.activity_bar.on_event(event_type, name, detail)
        if event_type == "tool_request":
            self.conversation_view.add_message("TOOL", f"{name}()")
        elif event_type == "tool_result" and detail:
            self.conversation_view.add_message("TOOL", f"{name} → {detail}")

    def clear_chat(self):
        self.conversation_view.clear()
        self.conversation = Conversation()
        self.conversation_view.add_message("SYSTEM", "Conversation cleared.")

    # ------------------------------------------------------------------
    # Listening lifecycle
    # ------------------------------------------------------------------

    def start_listening(self):
        if self.thread is not None:
            return

        self._turn_in_progress = True
        self.listen_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.update_state("STARTING")

        # Parented to the window as a Qt-ownership safety net (in addition
        # to the manual None-ing out in listening_finished) so an unusual
        # teardown order can't leave the thread object dangling unowned.
        self.thread = QThread(self)
        self.worker = JarvisWorker()
        self.worker.set_conversation(self.conversation)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.listen_once)
        self.worker.status_changed.connect(self.update_state)
        self.worker.user_message.connect(self.show_user_message)
        self.worker.jarvis_message.connect(self.show_jarvis_message)
        self.worker.tool_event.connect(self.on_tool_event)
        self.worker.audio_level.connect(self._on_audio_level)
        self.worker.error.connect(self.show_error)
        self.worker.performance.connect(self.performance_panel.update_times)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.listening_finished)

        self.thread.start()

    def stop_worker(self):
        # record_command / ask / speak are synchronous calls from the
        # existing backend, so there's no safe interruption point without
        # changing that architecture (explicitly out of scope). This just
        # prevents queuing another turn and is honest about the limitation.
        self.activity_bar.on_event(
            "idle", "", "Current operation can't be interrupted safely; waiting for completion."
        )

    def listening_finished(self):
        self.listen_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.waveform.set_active(False)

        if not self.state_label.text().endswith("ERROR"):
            self.update_state("SYSTEMS ONLINE")

        self.thread = None
        self.worker = None
        self._turn_in_progress = False

        if self._close_requested:
            # The window was asked to close mid-turn; now that the turn is
            # done, actually follow through instead of leaving the person
            # to notice and click close again.
            self.close()

    # ------------------------------------------------------------------
    # State / telemetry plumbing
    # ------------------------------------------------------------------

    def update_state(self, message: str):
        self.state_label.setText(f"● {message}")
        self.core.set_state(message)
        color = theme.state_color(message)
        self.state_label.setStyleSheet(f"color:{color}; font-size:14px; font-weight:700;")

        recording = message in ("RECORDING COMMAND", "RECORDING", "SPEAKING")
        self.waveform.set_active(recording)

    def _on_audio_level(self, level: float):
        self.waveform.push_level(level)

    def show_error(self, details: str):
        # The previous version dumped the full traceback straight into the
        # conversation timeline -- a wall of text in the one place meant to
        # stay readable. The full trace still goes somewhere a developer
        # would actually look (the log / terminal); the timeline gets a
        # one-line summary a user can act on.
        logger.error("JARVIS worker error:\n%s", details)
        last_line = details.strip().splitlines()[-1] if details.strip() else "Unknown error"
        self.conversation_view.add_message(
            "SYSTEM", f"Something went wrong: {last_line}\n(Full traceback logged to the terminal.)"
        )

    def closeEvent(self, event):
        if self._turn_in_progress:
            # Don't just ignore-and-forget: remember that a close was
            # requested so the window actually closes itself once the
            # in-flight turn finishes, instead of silently requiring the
            # person to notice nothing happened and click close again.
            self._close_requested = True
            self.activity_bar.on_event("idle", "", "Finishing current operation before closing...")
            event.ignore()
            return

        self._shutdown_background_threads()
        event.accept()

    def _shutdown_background_threads(self):
        # Safe to call more than once: both shutdown() methods no-op if
        # their thread isn't running (e.g. closeEvent already handled it
        # before aboutToQuit also fires during normal shutdown).
        self.system_panel.shutdown()
        self.model_panel.shutdown()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = JarvisWindow()
    window.show()
    sys.exit(app.exec())
