from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

import config

# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

_tts_engine = None


def _init_pyttsx3():
    global _tts_engine
    import pyttsx3
    _tts_engine = pyttsx3.init()
    voices = _tts_engine.getProperty("voices")
    # prefer en-us (32), then en-gb-rp (30), then first available
    preferred = ["gmw/en-us", "gmw/en-gb-x-rp"]
    for p in preferred:
        for v in voices:
            if v.id == p:
                _tts_engine.setProperty("voice", v.id)
                break
        else:
            continue
        break
    else:
        if voices:
            _tts_engine.setProperty("voice", voices[0].id)
    _tts_engine.setProperty("rate", 130)
    _tts_engine.setProperty("volume", 1.0)


def talk(text: str) -> None:
    print(text)
    if config.TTS_ENGINE == "espeak":
        subprocess.run(
            ["espeak-ng", text, "-v", "en-us", "-s", "120", "-p", "50", "-a", "200"],
            capture_output=True,
        )
    elif config.TTS_ENGINE == "pyttsx3":
        if _tts_engine is None:
            _init_pyttsx3()
        _tts_engine.say(text)
        _tts_engine.runAndWait()
    else:
        if _tts_engine is None:
            _init_pyttsx3()
        _tts_engine.say(text)
        _tts_engine.runAndWait()


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

_vosk_model = None
_vosk_init_lock = threading.Lock()


def _init_vosk():
    global _vosk_model
    if _vosk_model is not None:
        return
    with _vosk_init_lock:
        if _vosk_model is not None:
            return
        import vosk
        vosk.SetLogLevel(-1)  # suppress verbose C++ logs
        model_path = config.VOSK_MODEL_PATH
        if model_path and Path(model_path).exists():
            _vosk_model = vosk.Model(str(model_path))
        else:
            # auto-download small model
            model_path = Path.home() / ".hollali" / "vosk-model-small"
            if not model_path.exists():
                print("Downloading Vosk small model (~40MB)...")
                import urllib.request
                import zipfile
                model_path.parent.mkdir(parents=True, exist_ok=True)
                url = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
                zip_path = model_path.parent / "model.zip"
                urllib.request.urlretrieve(url, zip_path)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(model_path.parent)
                zip_path.unlink()
                extracted = model_path.parent / "vosk-model-small-en-us-0.15"
                if extracted.exists():
                    extracted.rename(model_path)
            _vosk_model = vosk.Model(str(model_path))


def rec_audio(timeout: float | None = None, phrase_limit: float | None = None,
              partial_cb=None, level_cb=None) -> str:
    if config.STT_ENGINE == "vosk":
        return _rec_vosk(timeout, partial_cb=partial_cb, level_cb=level_cb)

    return _rec_google(timeout, phrase_limit)


def _rec_vosk(timeout: float | None = None, partial_cb=None, level_cb=None) -> str:
    global _vosk_model
    if _vosk_model is None:
        _init_vosk()

    import json
    import math
    import queue
    import sounddevice as sd
    import vosk

    q: queue.Queue = queue.Queue()
    _partial_sent: list[str] = []

    def callback(indata, frames, atime, status):
        if status:
            print(f"Audio status: {status}", file=sys.stderr)
        import numpy as np
        arr = np.frombuffer(indata, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(arr ** 2))
        if level_cb:
            level = min(1.0, rms / 8000.0)
            level_cb(level)
        if rms < 200:
            return
        q.put(bytes(indata))

    print("Listening (Vosk)...")
    with sd.RawInputStream(
        samplerate=16000, blocksize=8000, dtype="int16",
        channels=1, callback=callback,
    ):
        rec = vosk.KaldiRecognizer(_vosk_model, 16000)
        import time
        start = time.time()
        last_activity = time.time()
        while True:
            try:
                data = q.get(timeout=0.1)
            except queue.Empty:
                if partial_cb:
                    partial = json.loads(rec.PartialResult())
                    ptext = partial.get("partial", "").strip()
                    if ptext and (not _partial_sent or ptext != _partial_sent[-1]):
                        _partial_sent.append(ptext)
                        partial_cb(ptext)
                if timeout and (time.time() - last_activity) > timeout:
                    return ""
                continue
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = result.get("text", "").strip()
                if text:
                    print(f"You said: {text}")
                    return text
                last_activity = time.time()
            partial = json.loads(rec.PartialResult())
            if partial.get("partial", "").strip():
                last_activity = time.time()
                if partial_cb:
                    ptext = partial["partial"].strip()
                    if not _partial_sent or ptext != _partial_sent[-1]:
                        _partial_sent.append(ptext)
                        partial_cb(ptext)
            if timeout and (time.time() - last_activity) > timeout:
                return ""


def _rec_google(timeout: float | None = None, phrase_limit: float | None = None) -> str:
    try:
        import speech_recognition as sr
    except ImportError:
        print("speech_recognition not installed, falling back to Vosk")
        config.STT_ENGINE = "vosk"
        return _rec_vosk(timeout)

    recog = sr.Recognizer()
    recog.energy_threshold = 4000
    recog.dynamic_energy_threshold = True

    import os as _os
    try:
        with open(_os.devnull, "w") as _null:
            _old_stderr = sys.stderr
            sys.stderr = _null
            try:
                mic = sr.Microphone()
            finally:
                sys.stderr = _old_stderr

        with mic as source:
            if timeout is None:
                with open(_os.devnull, "w") as _null:
                    _old_stderr = sys.stderr
                    sys.stderr = _null
                    try:
                        recog.adjust_for_ambient_noise(source, duration=0.5)
                    finally:
                        sys.stderr = _old_stderr
            try:
                audio = recog.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            except sr.WaitTimeoutError:
                return ""
    except (OSError, AttributeError) as e:
        if config.STT_ENGINE != "vosk":
            print(f"Microphone not available ({e}), falling back to Vosk")
            config.STT_ENGINE = "vosk"
        return _rec_vosk(timeout)

    try:
        data = recog.recognize_google(audio)
        print(f"You said: {data}")
        return data
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as ex:
        print(f"Request Error from Google Speech Recognition: {ex}")
        return ""


def call(text: str) -> bool:
    return "hollali" in text.lower()
