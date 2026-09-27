"""
Listens continuously on the mic for the "Hey Jarvis" wake word using
openWakeWord (fully local, runs fine on CPU, works on Windows or Linux).
"""
import os

import numpy as np
import openwakeword
import sounddevice as sd
from openwakeword.model import Model

from config import WAKE_WORD_MODEL, WAKE_WORD_THRESHOLD, MIC_SAMPLE_RATE, MIC_CHUNK

_oww_model = None


def _resolve_model_path() -> str:
    """Find the pretrained .onnx model file inside the installed openwakeword
    package itself, instead of a hardcoded machine-specific path. Works the
    same whether the package lives under Linux's site-packages or Windows'
    Lib\\site-packages."""
    base_dir = os.path.dirname(openwakeword.__file__)
    candidate = os.path.join(base_dir, "resources", "models", f"{WAKE_WORD_MODEL}.onnx")
    if not os.path.exists(candidate):
        raise FileNotFoundError(
            f"Couldn't find wake word model at {candidate}. Run:\n"
            "  python -c \"import openwakeword; "
            "openwakeword.utils.download_models(['" + WAKE_WORD_MODEL + "'])\""
        )
    return candidate


def _get_model():
    global _oww_model
    if _oww_model is None:
        print("[wake_word] loading openWakeWord model...")
        _oww_model = Model(wakeword_model_paths=[_resolve_model_path()])
    return _oww_model


def wait_for_wake_word():
    """Blocks until the wake word is detected."""
    model = _get_model()
    print(f"[wake_word] listening for wake word ('{WAKE_WORD_MODEL}')...")

    with sd.InputStream(samplerate=MIC_SAMPLE_RATE, channels=1, dtype="int16", blocksize=MIC_CHUNK) as stream:
        while True:
            block, _ = stream.read(MIC_CHUNK)
            audio = block.flatten()
            predictions = model.predict(audio)
            for name, score in predictions.items():
                if score >= WAKE_WORD_THRESHOLD:
                    print(f"[wake_word] detected '{name}' ({score:.2f})")
                    model.reset()
                    return
