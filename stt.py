"""
Records audio from the mic after wake word detection, and transcribes it
locally with faster-whisper (no cloud calls).
"""
import time
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from config import (
    MIC_SAMPLE_RATE, WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
    SILENCE_RMS_THRESHOLD, SILENCE_HANG_SECONDS, MAX_RECORD_SECONDS,
)

_model = None


def _get_model():
    global _model
    if _model is None:
        print(f"[stt] loading whisper model '{WHISPER_MODEL_SIZE}'...")
        _model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    return _model

def record_command() -> np.ndarray:
    """Records from the mic until the user stops talking (silence-based)."""
    block_duration = 0.1
    block_size = int(MIC_SAMPLE_RATE * block_duration)

    chunks = []
    silence_run = 0.0
    speech_started = False
    start = time.time()

    with sd.InputStream(
        samplerate=MIC_SAMPLE_RATE,
        channels=1,
        dtype="int16",
    ) as stream:

        print("[stt] listening for your command...")

        while True:
            block, _ = stream.read(block_size)
            block = block.copy()
            chunks.append(block)

            rms = np.sqrt(np.mean(block.astype(np.float32) ** 2))

            if rms >= SILENCE_RMS_THRESHOLD:
                speech_started = True
                silence_run = 0.0
            elif speech_started:
                silence_run += block_duration

            elapsed = time.time() - start

            # Only allow silence to end recording AFTER speech was detected.
            if speech_started and silence_run >= SILENCE_HANG_SECONDS:
                break

            # Safety cap.
            if elapsed >= MAX_RECORD_SECONDS:
                break

    audio = (
        np.concatenate(chunks, axis=0)
        .flatten()
        .astype(np.float32)
        / 32768.0
    )

    return audio
# def record_command() -> np.ndarray:
#     """Records from the mic until the user stops talking (silence-based), returns float32 samples."""
#     block_duration = 0.1
#     block_size = int(MIC_SAMPLE_RATE * block_duration)
#     chunks = []
#     silence_run = 0.0
#     start = time.time()

#     with sd.InputStream(samplerate=MIC_SAMPLE_RATE, channels=1, dtype="int16") as stream:
#         print("[stt] listening for your command...")
#         while True:
#             block, _ = stream.read(block_size)
#             chunks.append(block.copy())
#             rms = np.sqrt(np.mean(block.astype(np.float32) ** 2))

#             if rms < SILENCE_RMS_THRESHOLD:
#                 silence_run += block_duration
#             else:
#                 silence_run = 0.0

#             elapsed = time.time() - start
#             # Require at least a little speech before allowing silence to end it,
#             # and always stop after MAX_RECORD_SECONDS as a safety cap.
#             if (elapsed > 0.6 and silence_run >= SILENCE_HANG_SECONDS) or elapsed >= MAX_RECORD_SECONDS:
#                 break

#     audio = np.concatenate(chunks, axis=0).flatten().astype(np.float32) / 32768.0
#     return audio


def transcribe(audio: np.ndarray) -> str:
    model = _get_model()
    segments, _ = model.transcribe(audio, language="en", beam_size=1)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    return text
