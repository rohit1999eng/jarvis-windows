"""
Central configuration for your local JARVIS assistant.
Tweak these values to change behavior without touching the rest of the code.
"""

# ---- Local Ollama / LLM ----
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
# OLLAMA_MODEL = "dolphin-llama3:8b"
OLLAMA_MODEL = "qwen3:8b"

LLM_TEMPERATURE = 0.6
MAX_HISTORY_TURNS = 8

# ---- Wake word ----
WAKE_WORD_MODEL = "hey_jarvis_v0.1"
WAKE_WORD_THRESHOLD = 0.5
MIC_SAMPLE_RATE = 16000
MIC_CHUNK = 1280

# ---- Speech-to-text (faster-whisper) ----
WHISPER_MODEL_SIZE = "small.en"
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"

# Silence detection while recording your command
SILENCE_RMS_THRESHOLD = 500
SILENCE_HANG_SECONDS = 0.7
MAX_RECORD_SECONDS = 8

# ---- Text-to-speech (Piper) ----
PIPER_VOICE_PATH = "voices/en_GB-alan-medium.onnx"
PIPER_VOICE_CONFIG = "voices/en_GB-alan-medium.onnx.json"

# ---- Assistant identity ----
ASSISTANT_NAME = "Jarvis"
WAKE_ACK_PHRASES = ["Yes?", "I'm listening.", "Go ahead.", "At your service."]

# ---- Safety ----
DANGEROUS_COMMAND_PATTERNS = [
    # Linux/macOS
    "rm -rf /", "rm -rf ~", "rm -rf --no-preserve-root",
    "mkfs", "dd if=", ":(){:|:&};",
    "> /dev/sda", "chmod -r 777 /", "chown -r",
    "shutdown", "reboot", "poweroff", "mv /* ",
    "wget http", "curl http",

    # Windows
    "format ", "del /f", "del /s", "rd /s", "rmdir /s",
    "diskpart", "shutdown /s", "shutdown /r",
    "vssadmin delete", "cipher /w",
    "reg delete", "net user administrator",
    "taskkill /f /im",

    # Shell chaining/injection guards
    "&&", "||", ";", "|", "`", "$(",
]