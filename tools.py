"""
Tools JARVIS can call. Each function takes a dict of args (from the LLM's
JSON tool call) and returns a short string result that gets fed back to the
LLM so it can compose a natural-language answer.

Keep tool outputs SHORT — they go back into the LLM's context window.
"""
import platform
import subprocess
import shlex
import os
import psutil
import requests

from config import DANGEROUS_COMMAND_PATTERNS

IS_WINDOWS = platform.system() == "Windows"


def _truncate(text: str, limit: int = 1200) -> str:
    return text if len(text) <= limit else text[:limit] + "... [truncated]"


def open_app(args: dict) -> str:
    """Launch a desktop application by name, e.g. 'firefox', 'code', 'notepad'."""
    app = args.get("app", "").strip()
    if not app:
        return "No app name given."

    if IS_WINDOWS:
        try:
            # 'start' resolves things registered with Windows (installed apps,
            # file associations, etc.) the same way the Start menu/Run box does.
            subprocess.Popen(
                f'start "" {app}',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"Opened {app}."
        except Exception:
            return f"Couldn't find an application called '{app}'."

    try:
        # Try a straightforward launch first (works for most binaries on PATH)
        subprocess.Popen(shlex.split(app), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Opened {app}."
    except FileNotFoundError:
        # Fall back to desktop-file launch via gio
        try:
            subprocess.Popen(["gio", "launch", f"/usr/share/applications/{app}.desktop"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opened {app}."
        except Exception:
            return f"Couldn't find an application called '{app}'."


SAFE_COMMANDS_WINDOWS = (
    "whoami", "date", "time", "dir", "cd", "echo", "ver", "systeminfo",
    "tasklist", "ipconfig", "hostname",
)
SAFE_COMMANDS_POSIX = (
    "pwd", "whoami", "date", "uptime", "ls", "free", "df", "nvidia-smi",
)


def run_command(args: dict) -> str:
    """Run a command only after explicit confirmation."""
    cmd = args.get("command", "").strip()

    if not cmd:
        return "No command given."

    lowered = cmd.lower()

    for pattern in DANGEROUS_COMMAND_PATTERNS:
        if pattern in lowered:
            return (
                "I refused to run that command because it matches a "
                f"blocked pattern: {pattern}"
            )

    safe_commands = SAFE_COMMANDS_WINDOWS if IS_WINDOWS else SAFE_COMMANDS_POSIX

    # Only match on the actual first token (not a substring/prefix match), so
    # e.g. "lsblk" or "ls something; rm -rf ~" can't sneak past as "ls".
    # posix=False on Windows since shlex assumes POSIX quoting rules by default.
    try:
        tokens = shlex.split(cmd, posix=not IS_WINDOWS)
    except ValueError:
        return "Couldn't parse that command (unbalanced quotes?)."

    first_word = tokens[0].lower() if tokens else ""

    if first_word not in safe_commands:
        return (
            "This command requires confirmation before execution: "
            f"{cmd}. Please confirm explicitly in the GUI."
        )

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=15,
        )

        out = result.stdout.strip() or result.stderr.strip() or "(no output)"
        return _truncate(out)

    except subprocess.TimeoutExpired:
        return "Command timed out after 15 seconds."

    except Exception as e:
        return f"Command failed: {e}"


def read_file(args: dict) -> str:
    """Read a text file's contents."""
    path = os.path.expanduser(args.get("path", "").strip())
    if not path:
        return "No path given."
    try:
        with open(path, "r", errors="replace") as f:
            return _truncate(f.read())
    except Exception as e:
        return f"Couldn't read file: {e}"


def list_dir(args: dict) -> str:
    """List files in a directory."""
    path = os.path.expanduser(args.get("path", ".").strip() or ".")
    try:
        entries = os.listdir(path)
        return _truncate(", ".join(sorted(entries)) or "(empty directory)")
    except Exception as e:
        return f"Couldn't list directory: {e}"


def get_weather(args: dict) -> str:
    """Get current weather for a location using wttr.in (no API key needed)."""
    location = args.get("location", "").strip() or ""
    try:
        resp = requests.get(f"https://wttr.in/{location}?format=3", timeout=8)
        return resp.text.strip()
    except Exception as e:
        return f"Couldn't fetch weather: {e}"


def web_search(args: dict) -> str:
    """Search the web and return brief top results."""
    query = args.get("query", "").strip()
    if not query:
        return "No search query given."
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        if not results:
            return "No results found."
        lines = [f"{r['title']}: {r['body'][:180]}" for r in results]
        return _truncate(" | ".join(lines))
    except Exception as e:
        return f"Search failed: {e}"


def system_stats(args: dict) -> str:
    """Report CPU, memory, disk, battery, and NVIDIA GPU status."""
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    battery = psutil.sensors_battery()

    parts = [
        f"CPU {cpu}% usage",
        f"RAM {mem.percent}% used "
        f"({mem.used // (1024**2)}MB/{mem.total // (1024**2)}MB)",
        f"Disk {disk.percent}% used",
    ]

    if battery:
        charging = " (charging)" if battery.power_plugged else ""
        parts.append(f"Battery {battery.percent}%{charging}")

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0 and result.stdout.strip():
            gpu_name, temperature, utilization, memory_used, memory_total = (
                result.stdout.strip().split(",", 4)
            )

            parts.append(
                f"GPU {gpu_name.strip()}, "
                f"{utilization.strip()}% usage, "
                f"{temperature.strip()}°C, "
                f"{memory_used.strip()}MB/"
                f"{memory_total.strip()}MB VRAM used"
            )
        else:
            parts.append("NVIDIA GPU information unavailable")

    except FileNotFoundError:
        parts.append("nvidia-smi was not found")
    except Exception:
        parts.append("GPU information unavailable")

    return ", ".join(parts)

# Registry the LLM layer uses to dispatch tool calls by name
TOOL_REGISTRY = {
    "open_app": open_app,
    "run_command": run_command,
    "read_file": read_file,
    "list_dir": list_dir,
    "get_weather": get_weather,
    "web_search": web_search,
    "system_stats": system_stats,
}

# Human-readable descriptions injected into the LLM's system prompt
TOOL_DESCRIPTIONS = """
- open_app(app): launch a desktop application, e.g. {"app": "firefox"}
- run_command(command): run a shell command, e.g. {"command": "ls ~/Downloads"}
- read_file(path): read a text file, e.g. {"path": "~/notes.txt"}
- list_dir(path): list a directory's contents, e.g. {"path": "~/Documents"}
- get_weather(location): current weather, e.g. {"location": "Chennai"}
- web_search(query): search the web, e.g. {"query": "latest news on AI"}
- system_stats(): CPU/RAM/disk/battery status, e.g. {}
""".strip()
