from __future__ import annotations

import atexit
import concurrent.futures
import json
import logging
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import math

import config
from log import logger

# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

_tts_engine = None


def _init_pyttsx3() -> None:
    global _tts_engine
    import pyttsx3
    _tts_engine = pyttsx3.init()
    voices = _tts_engine.getProperty("voices")
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


_PIPER_BIN = Path(config.PIPER_BIN_PATH)
_PIPER_VOICE = Path(config.PIPER_VOICE_PATH)

_piper_available: bool | None = None
_piper_lock = threading.Lock()


def _check_piper() -> bool:
    global _piper_available
    if _piper_available is None:
        _piper_available = _PIPER_BIN.exists() and _PIPER_VOICE.exists()
    return _piper_available


def _talk_piper(text: str) -> None:
    if not _check_piper():
        logger.warning("Piper not available, falling back to espeak")
        _talk_espeak(text)
        return
    with _piper_lock:
        try:
            piper = subprocess.Popen(
                [str(_PIPER_BIN), "--model", str(_PIPER_VOICE), "--output_raw"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            raw_out, piper_err = piper.communicate(input=text.encode(), timeout=30)
            if piper.returncode != 0:
                logger.warning(f"Piper failed (rc={piper.returncode}): {piper_err.decode().strip()}")
                _talk_espeak(text)
                return

            wav_path = Path.home() / ".hollali" / "piper_output.wav"
            wav_path.parent.mkdir(parents=True, exist_ok=True)

            import struct
            data_len = len(raw_out)
            with open(wav_path, "wb") as wf:
                wf.write(b"RIFF")
                wf.write(struct.pack("<I", 36 + data_len))
                wf.write(b"WAVE")
                wf.write(b"fmt ")
                wf.write(struct.pack("<I", 16))
                wf.write(struct.pack("<H", 1))
                wf.write(struct.pack("<H", 1))
                wf.write(struct.pack("<I", 22050))
                wf.write(struct.pack("<I", 44100))
                wf.write(struct.pack("<H", 2))
                wf.write(struct.pack("<H", 16))
                wf.write(b"data")
                wf.write(struct.pack("<I", data_len))
                wf.write(raw_out)

            for player in ("pw-play", "paplay"):
                try:
                    subprocess.run(
                        [player, str(wav_path)],
                        capture_output=True, timeout=60, check=True,
                    )
                    break
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
            else:
                raise RuntimeError("No audio player found (pw-play, paplay)")
            wav_path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Piper playback error: {e}", exc_info=True)
            _talk_espeak(text)


def _talk_espeak(text: str) -> None:
    result = subprocess.run(
        ["espeak-ng", text, "-v", "en-us", "-s", "120", "-p", "50", "-a", "200"],
        capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode().strip()
        logger.warning(f"espeak-ng failed (rc={result.returncode}): {stderr}")


_talk_pool: concurrent.futures.ThreadPoolExecutor | None = None
_speaking = False
_speaking_lock = threading.Lock()


def is_speaking() -> bool:
    with _speaking_lock:
        return _speaking


def talk(text: str) -> None:
    global _speaking
    with _speaking_lock:
        _speaking = True
    try:
        logger.info(text)
        if config.TTS_ENGINE == "piper":
            _talk_piper(text)
        elif config.TTS_ENGINE == "espeak":
            _talk_espeak(text)
        elif _tts_engine is None:
            _init_pyttsx3()
            _tts_engine.say(text)
            _tts_engine.runAndWait()
        else:
            _tts_engine.say(text)
            _tts_engine.runAndWait()
    finally:
        with _speaking_lock:
            _speaking = False


def talk_async(text: str) -> None:
    """Run talk() in a background thread so it doesn't block the caller."""
    global _talk_pool
    if _talk_pool is None:
        _talk_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        atexit.register(_talk_pool.shutdown, wait=False)
    _talk_pool.submit(talk, text)


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

_vosk_model = None
_vosk_init_lock = threading.Lock()


def _init_vosk() -> None:
    global _vosk_model
    if _vosk_model is not None:
        return
    with _vosk_init_lock:
        if _vosk_model is not None:
            return
        import vosk
        vosk.SetLogLevel(-1)
        model_path = config.VOSK_MODEL_PATH
        if model_path and Path(model_path).exists():
            _vosk_model = vosk.Model(str(model_path))
        else:
            model_path = Path.home() / ".hollali" / "vosk-model-small"
            if not model_path.exists():
                logger.info("Downloading Vosk small model (~40MB)...")
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


def _rms(data: bytes) -> float:
    if not data:
        return 0.0
    samples = len(data) // 2
    total = 0
    for i in range(samples):
        val = int.from_bytes(data[i * 2 : i * 2 + 2], "little", signed=True)
        total += val * val
    return math.sqrt(total / samples)


def rec_audio(timeout: float | None = None, phrase_limit: float | None = None,
              partial_cb: Callable[[str], None] | None = None, level_cb: Callable[[float], None] | None = None) -> str:
    if config.STT_ENGINE == "vosk":
        return _rec_vosk(timeout, partial_cb=partial_cb, level_cb=level_cb)
    return _rec_google(timeout, phrase_limit)


def _rec_vosk(timeout: float | None = None, partial_cb: Callable[[str], None] | None = None, level_cb: Callable[[float], None] | None = None) -> str:
    global _vosk_model
    if _vosk_model is None:
        _init_vosk()

    import sounddevice as sd
    import vosk

    q: queue.Queue = queue.Queue()
    _partial_sent: list[str] = []

    def callback(indata: Any, frames: int, atime: Any, status: Any) -> None:
        if status:
            logger.warning(f"Audio status: {status}")
        raw = bytes(indata)
        level = _rms(raw)
        if level_cb:
            level_cb(min(1.0, level / 8000.0))
        if level < 200:
            return
        q.put(raw)

    logger.debug("Listening (Vosk)...")
    with sd.RawInputStream(
        samplerate=16000, blocksize=8000, dtype="int16",
        channels=1, callback=callback,
    ):
        rec = vosk.KaldiRecognizer(_vosk_model, 16000)
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
                    logger.info(f"You said: {text}")
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
        logger.warning("speech_recognition not installed, falling back to Vosk")
        config.STT_ENGINE = "vosk"
        return _rec_vosk(timeout)

    recog = sr.Recognizer()
    recog.energy_threshold = 4000
    recog.dynamic_energy_threshold = True

    import contextlib
    import os as _os

    _devnull = open(_os.devnull, "w")
    try:
        with contextlib.redirect_stderr(_devnull):
            mic = sr.Microphone()

        with mic as source:
            if timeout is None or timeout > 0:
                adj_timeout = timeout if timeout else 1
                with contextlib.redirect_stderr(_devnull):
                    recog.adjust_for_ambient_noise(source, duration=min(0.5, adj_timeout))
            try:
                audio = recog.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
            except sr.WaitTimeoutError:
                return ""
    except (OSError, AttributeError) as e:
        if config.STT_ENGINE != "vosk":
            logger.warning(f"Microphone not available ({e}), falling back to Vosk")
            config.STT_ENGINE = "vosk"
        return _rec_vosk(timeout)
    finally:
        _devnull.close()

    try:
        data = recog.recognize_google(audio)
        logger.info(f"You said: {data}")
        return data
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as ex:
        logger.error(f"Google STT request error: {ex}")
        return ""


def call(text: str) -> bool:
    return bool(re.search(r"\bhollali\b", text.lower()))
