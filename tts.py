"""
Speaks text out loud using Piper.
"""
import os
import tempfile
import wave

import sounddevice as sd
import numpy as np
from piper.voice import PiperVoice

from config import PIPER_VOICE_PATH, PIPER_VOICE_CONFIG

_voice = None


def _get_voice():
    global _voice
    if _voice is None:
        print("[tts] loading Piper voice...")
        _voice = PiperVoice.load(
            PIPER_VOICE_PATH,
            config_path=PIPER_VOICE_CONFIG,
        )
    return _voice


def speak(text: str):
    if not text:
        return

    voice = _get_voice()
    print(f"[tts] {text}")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
        wav_path = temp_file.name

    try:
        with wave.open(wav_path, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file)

        with wave.open(wav_path, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            sample_width = wav_file.getsampwidth()
            channels = wav_file.getnchannels()
            audio_bytes = wav_file.readframes(wav_file.getnframes())

        if sample_width != 2:
            raise RuntimeError(
                f"Unsupported WAV sample width: {sample_width} bytes"
            )

        audio = np.frombuffer(audio_bytes, dtype=np.int16)

        if channels > 1:
            audio = audio.reshape(-1, channels)

        sd.play(audio, samplerate=sample_rate)
        sd.wait()

    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)
