# Your local JARVIS (Windows + Google Gemini free tier)

Voice assistant: wake word → speech-to-text (local, faster-whisper) → Gemini
(cloud, free tier) → tool calls (open apps, run commands, weather, web search,
system stats) → natural-sounding text-to-speech. Only the Gemini/weather/web-search
requests leave your machine; everything else runs locally.

## 1. Get a free Gemini API key

1. Go to https://aistudio.google.com/apikey and sign in with a Google account.
2. Click "Create API key" — no billing setup required for the free tier.
3. Set it as an environment variable so it's never hardcoded in the source:

   **PowerShell** (recommended — then close and reopen your terminal):
   ```powershell
   setx GEMINI_API_KEY "your-key-here"
   ```

   **cmd.exe**:
   ```cmd
   setx GEMINI_API_KEY "your-key-here"
   ```

The free tier has rate limits (requests/minute and/or per day depending on the
model) but no cost. If you outgrow it, the same code works with a billed key.

## 2. Python environment

Install [Python 3.11+ for Windows](https://www.python.org/downloads/windows/) first
(check "Add python.exe to PATH" during install), then:

```powershell
cd jarvis
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

If `piper-tts` fails to install (its wheels are Linux-first), run this instead:

```powershell
pip install piper-phonemize
pip install piper-tts --no-deps
```

You'll also want [ffmpeg for Windows](https://www.gyan.dev/ffmpeg/builds/) on your
PATH — faster-whisper needs it for some audio formats.

## 3. Download the wake word model

openWakeWord ships pretrained models, including one that literally matches your
assistant's name:

```powershell
python -c "import openwakeword; openwakeword.utils.download_models(['hey_jarvis_v0.1'])"
```

`wake_word.py` now locates this file automatically inside your installed
`openwakeword` package (works whether that's under Linux or Windows site-packages),
so there's nothing to configure by hand.

## 4. Download a Piper voice

Pick a voice from the [Piper voice list](https://github.com/rhasspy/piper/blob/master/VOICES.md).
`en_GB-alan-medium` or `en_US-ryan-high` both sound close to a "JARVIS" tone.

Download the two files below into a `voices\` folder (right-click → Save As in your
browser works fine, or use PowerShell):

```powershell
mkdir voices
cd voices
curl -o en_GB-alan-medium.onnx https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx
curl -o en_GB-alan-medium.onnx.json https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json
cd ..
```

If you pick a different voice, update `PIPER_VOICE_PATH` / `PIPER_VOICE_CONFIG` in
`config.py` to match.

## 5. Run it

```powershell
python main.py
```

Say **"Hey Jarvis"**, wait for the acknowledgement ("Yes?" / "Go ahead."), then speak
your request. Try things like:

- "What's the weather in Chennai?"
- "Open Firefox."
- "What are my system stats?"
- "Search the web for the latest Ubuntu LTS release."
- "List the files in my Downloads folder."

Say "stop", "shut down", or "go to sleep" to quiet it without killing the process
(Ctrl+C exits for good).

## How it works

- **Wake word** (`wake_word.py`): openWakeWord streams mic audio and scores it against
  the "Hey Jarvis" model continuously — this is the only always-on listener, and it's
  a tiny, cheap model, not the LLM.
- **STT** (`stt.py`): once woken, records until you stop talking (simple energy-based
  silence detection) and transcribes locally with faster-whisper.
- **LLM** (`llm.py`): sends your text + short rolling history to Google's Gemini API
  (free tier — `gemini-2.5-flash` by default, see `config.py`). We use a prompted JSON
  convention for tool calls (Gemini does support native function calling, but this
  keeps `tools.py`/`TOOL_REGISTRY` unchanged) — if the model decides it needs a tool,
  it emits a single JSON object naming the tool and args, which gets executed, fed
  back in, and the model is asked to phrase a final spoken sentence from the result.
- **Tools** (`tools.py`): `open_app`, `run_command`, `read_file`, `list_dir`,
  `get_weather`, `web_search`, `system_stats`.
- **TTS** (`tts.py`): Piper synthesizes and plays the reply through your speakers.

## Tuning tips

- **Wake word too sensitive/not sensitive enough**: adjust `WAKE_WORD_THRESHOLD` in
  `config.py` (0.0–1.0).
- **Cuts you off / doesn't cut off**: adjust `SILENCE_RMS_THRESHOLD` and
  `SILENCE_HANG_SECONDS`.
- **Slow responses**: for faster STT, drop `WHISPER_MODEL_SIZE` to `"tiny.en"` or
  `"base.en"` in `config.py`. If you have an NVIDIA GPU, set `WHISPER_DEVICE = "cuda"`.
- **"Gemini returned no usable text" / errors**: usually a hit free-tier rate limit
  (requests-per-minute or per-day) — wait a bit, or switch `GEMINI_MODEL` in
  `config.py` to `"gemini-2.5-flash-lite"`, which has higher free-tier limits.
- **Different personality**: edit `SYSTEM_PROMPT` in `llm.py`.

## Safety note on `run_command`

This tool lets the assistant execute arbitrary shell commands you ask for by voice.
`config.py`'s `DANGEROUS_COMMAND_PATTERNS` blocks an obvious blacklist (`rm -rf /`,
`mkfs`, `shutdown`, blind `wget`/`curl`, etc.) but a blacklist is not a sandbox — don't
expose this to anyone but yourself, and don't run it on a machine with sensitive data
you wouldn't want touched by a misheard voice command. If you want it safer, remove
`run_command` from `TOOL_REGISTRY` in `tools.py` or replace it with a curated set of
specific actions (e.g. only "open app X" instead of arbitrary shell).

## Extending it

Add a new capability in three steps:
1. Write a function in `tools.py` that takes an `args: dict` and returns a short string.
2. Register it in `TOOL_REGISTRY` and describe it in `TOOL_DESCRIPTIONS`.
3. That's it — the LLM will start calling it whenever a request seems to match.
