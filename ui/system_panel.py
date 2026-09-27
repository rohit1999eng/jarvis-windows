"""
Live system monitor: CPU / RAM / Disk / GPU / VRAM / Battery.

CPU/RAM/disk/battery come from psutil, which is a fast, non-blocking
syscall snapshot -- cheap enough to sample directly on a GUI-thread
QTimer. GPU stats are different: they require shelling out to
`nvidia-smi`, and a subprocess call has no upper bound on how long it can
block if the driver stalls or the process is slow to spawn. That call
runs on a dedicated QThread (`_GpuSampler`) so a slow or hung GPU query
can never freeze the window, matching how JarvisWorker keeps the LLM
pipeline off the GUI thread.
"""

from __future__ import annotations

import shutil
import subprocess

import psutil
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout

from ui.theme import TEXT_MUTED, TEXT_PRIMARY


class MetricBar(QFrame):
    """One labeled progress bar, e.g.  CPU  [######----]  17%"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("metric_card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        top = QLabel(title.upper())
        top.setObjectName("metric_title")

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)

        self._value = QLabel("--")
        self._value.setObjectName("metric_value")

        layout.addWidget(top)
        layout.addWidget(self._bar)
        layout.addWidget(self._value)

    def set_percent(self, percent: float, text: str | None = None):
        percent = max(0, min(100, int(percent)))
        self._bar.setValue(percent)
        self._value.setText(text if text is not None else f"{percent}%")

    def set_unavailable(self):
        self._bar.setValue(0)
        self._value.setText("Unavailable")
        self._value.setStyleSheet(f"color:{TEXT_MUTED}; font-size:13px; font-weight:700;")


class _GpuSampler(QObject):
    """Runs blocking `nvidia-smi` calls on its own thread, on a loop."""

    result = Signal(object)  # dict on success, None when unavailable

    @Slot()
    def start_polling(self):
        # The QTimer is created here (not in __init__) so it lives on
        # whichever thread start_polling actually runs on -- i.e. the
        # worker thread once moveToThread has taken effect, not whatever
        # thread constructed this object.
        self._timer = QTimer()
        self._timer.timeout.connect(self._poll)
        self._timer.start(2000)
        self._poll()

    @Slot()
    def stop_polling(self):
        # See ModelPanel/_OllamaInfoFetcher.stop_polling for why this needs
        # to run on this object's own thread via the thread's `finished`
        # signal rather than relying on eventual GC.
        if hasattr(self, "_timer"):
            self._timer.stop()

    def _poll(self):
        if shutil.which("nvidia-smi") is None:
            self.result.emit(None)
            return
        try:
            proc = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                raise RuntimeError("nvidia-smi returned no data")

            util, used, total, temp = [
                x.strip() for x in proc.stdout.strip().splitlines()[0].split(",")
            ]
            self.result.emit(
                {
                    "util": float(util),
                    "used_gb": float(used) / 1024,
                    "total_gb": float(total) / 1024,
                    "temp": temp,
                }
            )
        except Exception:
            self.result.emit(None)


class SystemPanel(QFrame):
    """Vertical stack of MetricBar widgets, refreshed on a timer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel_flat")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("SYSTEM MONITOR")
        title.setObjectName("section_title")
        layout.addWidget(title)

        self.cpu = MetricBar("CPU")
        self.ram = MetricBar("RAM")
        self.disk = MetricBar("DISK")
        self.gpu = MetricBar("GPU")
        self.vram = MetricBar("VRAM")
        self.battery = MetricBar("BATTERY")

        for card in (self.cpu, self.ram, self.disk, self.gpu, self.vram, self.battery):
            layout.addWidget(card)

        layout.addStretch(1)

        # Cheap psutil metrics stay on a plain GUI-thread timer.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_cheap_metrics)
        self._timer.start(1500)
        self._refresh_cheap_metrics()

        # GPU polling runs on its own thread indefinitely; see _GpuSampler.
        self._gpu_thread = QThread(self)
        self._gpu_sampler = _GpuSampler()
        self._gpu_sampler.moveToThread(self._gpu_thread)
        self._gpu_thread.started.connect(self._gpu_sampler.start_polling)
        self._gpu_thread.finished.connect(self._gpu_sampler.stop_polling)
        self._gpu_sampler.result.connect(self._on_gpu_result)
        self._gpu_thread.start()

    # ------------------------------------------------------------------

    def shutdown(self):
        """Stop the background GPU-polling thread cleanly on app exit."""
        if self._gpu_thread.isRunning():
            self._gpu_thread.quit()
            self._gpu_thread.wait(1500)

    def _refresh_cheap_metrics(self):
        self._read_cpu_ram_disk()
        self._read_battery()

    def _on_gpu_result(self, data):
        if data is None:
            self.gpu.set_unavailable()
            self.vram.set_unavailable()
            return
        self.gpu.set_percent(data["util"], f"{data['util']:.0f}%  •  {data['temp']}°C")
        total_gb = data["total_gb"]
        self.vram.set_percent(
            (data["used_gb"] / total_gb * 100) if total_gb else 0,
            f"{data['used_gb']:.1f} / {total_gb:.1f} GB",
        )

    def _read_cpu_ram_disk(self):
        cpu = psutil.cpu_percent(interval=None)
        self.cpu.set_percent(cpu)

        mem = psutil.virtual_memory()
        self.ram.set_percent(
            mem.percent,
            f"{mem.used / (1024 ** 3):.1f} / {mem.total / (1024 ** 3):.0f} GB",
        )

        try:
            disk = psutil.disk_usage("/")
        except Exception:
            disk = None
        if disk is not None:
            self.disk.set_percent(
                disk.percent,
                f"{disk.used / (1024 ** 3):.0f} / {disk.total / (1024 ** 3):.0f} GB",
            )
        else:
            self.disk.set_unavailable()

    def _read_battery(self):
        try:
            battery = psutil.sensors_battery()
        except Exception:
            battery = None

        if battery is None:
            self.battery.set_unavailable()
            return

        status = "Charging" if battery.power_plugged else "On battery"
        self.battery.set_percent(battery.percent, f"{battery.percent:.0f}% • {status}")
