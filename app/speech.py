"""Speech-to-text — server-side socket.

Voice input has TWO paths, by design:

  PATH A (primary, free, multilingual): the user's own browser. Chrome's
  Web Speech API recognizes speech on the device in en-IN, hi-IN, ml-IN
  and more — no server work at all. The frontend uses this when available.

  PATH B (fallback, this file): browsers without speech support record
  audio and POST it to /transcribe. We convert it with ffmpeg and feed an
  offline Vosk model IF one is installed under models/. No model → an
  honest 503, never a fake transcript. (Same socket pattern as llm.py:
  drop a model folder in, the feature switches on, no code changes.)
"""

import subprocess
import tempfile
from pathlib import Path

MODEL_DIR = next(Path("models").glob("vosk-model*"), None) if Path("models").exists() else None


def available() -> bool:
    return MODEL_DIR is not None


def transcribe(audio_bytes: bytes) -> str:
    """Audio (any format the browser records) → text, via Vosk."""
    if not available():
        raise RuntimeError(
            "Server-side speech model not installed. "
            "Place a Vosk model under models/ (e.g. vosk-model-small-en-in)."
        )

    import json as _json

    import vosk

    with tempfile.NamedTemporaryFile(suffix=".webm") as src, \
         tempfile.NamedTemporaryFile(suffix=".wav") as wav:
        src.write(audio_bytes)
        src.flush()
        # ffmpeg: whatever came in → 16kHz mono WAV (what Vosk expects).
        subprocess.run(
            ["ffmpeg", "-y", "-i", src.name, "-ar", "16000", "-ac", "1", wav.name],
            capture_output=True, timeout=60, check=True,
        )
        model = vosk.Model(str(MODEL_DIR))
        recognizer = vosk.KaldiRecognizer(model, 16000)
        pcm = subprocess.run(
            ["ffmpeg", "-y", "-i", wav.name, "-f", "s16le", "-"],
            capture_output=True, timeout=60, check=True,
        ).stdout
        recognizer.AcceptWaveform(pcm)
        return _json.loads(recognizer.FinalResult()).get("text", "")
