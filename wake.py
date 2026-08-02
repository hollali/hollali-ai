from __future__ import annotations

import re
import threading
from collections.abc import Callable
from pathlib import Path

import config
from log import logger

_PREFIXES = ("hey", "ok", "okay")
# Do not treat trailing sounds like "hollali-something" as a wake.
_PREFIX_GROUP = r"(?:(" + "|".join(_PREFIXES) + r")\s+)?"


def build_wake_pattern(word: str) -> re.Pattern[str]:
    """Compile a case-insensitive pattern for the configured wake word.

    Accepts ``word``, ``hey word``, ``ok word`` and ``okay word``, each
    matched on word boundaries so ``hollalina`` or ``holla`` do not trigger.
    """
    escaped = re.escape(word.lower())
    return re.compile(rf"\b{_PREFIX_GROUP}{escaped}\b")


def matches(text: str, word: str | None = None) -> bool:
    """True if ``text`` (from STT) contains the wake word."""
    word = (word or config.WAKE_WORD).lower()
    return bool(build_wake_pattern(word).search(text.lower()))


class WakeWordDetector:
    """Streaming wake-word detection via openwakeword (optional).

    ``config.WAKE_ENGINE`` selects the engine:
      - ``"stt"`` (default): no streaming detector; wake detection happens on
        STT results via :func:`matches`. ``active`` returns False.
      - ``"openwakeword"``: loads a custom ONNX model for the wake word from
        ``config.OPENWAKEWORD_MODEL_DIR`` and detects on raw audio frames.

    The streaming engine is only active when at least one custom ``.onnx``
    model exists in the model directory (openwakeword's built-in keywords do
    not match an arbitrary wake word). Otherwise it logs clear instructions
    and falls back to the STT-based path.
    """

    def __init__(self, word: str | None = None, model_dir: str | None = None, threshold: float = 0.5) -> None:
        self.word = (word or config.WAKE_WORD).lower()
        self._model_dir = Path(model_dir or config.OPENWAKEWORD_MODEL_DIR)
        self._threshold = threshold
        self._lock = threading.Lock()
        self._active = False
        self._model = None
        self._buffer: bytearray = bytearray()
        self._chunk_size = 1280 * 2  # 1280 int16 frames == 80ms at 16 kHz (openwakeword window)

        if config.WAKE_ENGINE != "openwakeword":
            return
        self._init_openwakeword()

    @property
    def active(self) -> bool:
        return self._active

    @staticmethod
    def _silence_cuda_warning() -> None:
        import warnings

        warnings.filterwarnings("ignore", message="Specified provider.*")
        warnings.filterwarnings("ignore", message=".*CUDAExecutionProvider.*")

    @staticmethod
    def _is_wakeword_model(path: Path) -> bool:
        """True if the ONNX model takes the openwakeword feature input.

        Wake-word models expect 3D input ``[batch, n_mels, frames]``. Auxiliary
        files (e.g. openwakeword's ``embedding_model.onnx``, which expects 4D
        input) would otherwise crash inference for the whole detector.
        """
        try:
            import onnxruntime as ort

            session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
            return any(len(inp.shape) == 3 for inp in session.get_inputs())
        except Exception:
            return True  # cannot inspect; let loading surface any real error

    def _init_openwakeword(self) -> None:
        try:
            self._silence_cuda_warning()
            from openwakeword.model import Model

            if not self._model_dir.exists() or not list(self._model_dir.glob("*.onnx")):
                logger.warning(
                    f"WAKE_ENGINE=openwakeword set but no *.onnx model found in "
                    f"{self._model_dir}. Drop a trained model for your wake word "
                    f"there, or set WAKE_ENGINE=stt. Falling back to STT detection."
                )
                return

            custom_paths = [str(p) for p in sorted(self._model_dir.glob("*.onnx")) if self._is_wakeword_model(p)]
            if not custom_paths:
                logger.warning(
                    f"No wake-word model (3D feature input) found in {self._model_dir}; using STT detection"
                )
                return

            self._model = self._load_model(Model, custom_paths)
            if self._model is None:
                logger.warning("Failed to load any openwakeword model; using STT detection")
                return

            self._active = True
            logger.info(f"Wake-word engine 'openwakeword' ready (word={self.word!r}, models={len(custom_paths)})")
        except ImportError:
            logger.warning(
                "openwakeword is not installed. Run `pip install openwakeword` or "
                "set WAKE_ENGINE=stt. Using STT-based wake detection."
            )
        except Exception as e:
            logger.warning(f"openwakeword initialization failed ({e}); using STT detection")

    @staticmethod
    def _load_model(model_cls, paths: list[str]):
        """Load custom models across openwakeword versions."""
        kwargs = {"wakeword_model_paths": paths}  # openwakeword >= 0.4
        try:
            return model_cls(**kwargs)
        except TypeError:
            try:
                return model_cls(custom_model_paths=paths)  # openwakeword >= 0.6
            except TypeError:
                return None

    def feed(self, frames: bytes) -> bool:
        """Feed raw int16 PCM (16 kHz, mono) audio; return True once woken."""
        if not self._active:
            return False
        scores = self.frame_scores(frames)
        top = max(scores.values(), default=0.0)
        if top >= self._threshold:
            logger.info(f"Wake word detected (score={top:.2f})")
            return True
        return False

    def frame_scores(self, frames: bytes) -> dict[str, float]:
        """Feed one audio chunk and return the model scores for the newest frame.

        Returns an empty dict until a full 80 ms window (1280 samples) has
        accumulated.
        """
        if not self._active or self._model is None:
            return {}
        self._buffer += frames
        if len(self._buffer) < self._chunk_size:
            return {}
        payload = bytes(self._buffer[: self._chunk_size])
        del self._buffer[: self._chunk_size]

        try:
            import numpy as np

            audio = np.frombuffer(payload, dtype=np.int16)
            prediction = self._model.predict(audio)
            return {
                name: score.get("score") if isinstance(score, dict) else score for name, score in prediction.items()
            }
        except Exception as e:
            logger.error(f"openwakeword inference error: {e}")
            return {}


_detector: WakeWordDetector | None = None
_detector_lock = threading.Lock()


def get_detector() -> WakeWordDetector:
    global _detector
    if _detector is None:
        with _detector_lock:
            if _detector is None:
                _detector = WakeWordDetector()
    return _detector


def wake_listener_active() -> bool:
    """True when the streaming wake-word engine should be used in idle mode."""
    return get_detector().active


def listen_for_wake(level_cb: Callable[[float], None] | None = None) -> str:
    """Block until the wake word is heard (openwakeword engine).

    Returns the configured wake word so callers can treat it as if STT heard
    it. Falls back to an empty string if the engine is unavailable.
    """
    detector = get_detector()
    if not detector.active:
        return ""

    try:
        import sounddevice as sd

        with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype="int16", channels=1) as stream:
            while True:
                try:
                    data, _ = stream.read(8000)
                except Exception:
                    logger.error("Wake-word audio stream error", exc_info=True)
                    return ""
                if level_cb:
                    level_cb(min(1.0, _rms(bytes(data)) / 8000.0))
                if detector.feed(bytes(data)):
                    return detector.word
    except Exception as e:
        logger.error(f"Wake-word listening failed ({e}); using STT-based wake detection")
        detector._active = False  # noqa: SLF001  degrade to STT path
        return ""


def _rms(data: bytes) -> float:
    if not data:
        return 0.0
    samples = len(data) // 2
    total = 0
    for i in range(samples):
        val = int.from_bytes(data[i * 2 : i * 2 + 2], "little", signed=True)
        total += val * val
    return (total / samples) ** 0.5


def test_model_cli() -> None:
    """Listen on the microphone and print live wake-word scores.

    Useful to verify a trained model works and to tune the threshold before
    enabling WAKE_ENGINE=openwakeword. Ctrl+C to stop.
    """
    import time

    detector = WakeWordDetector()
    if not detector.active:
        print("No streaming wake-word engine active. Set WAKE_ENGINE=openwakeword and")
        print(f"place a trained *.onnx model in {detector._model_dir} first.")  # noqa: SLF001
        return

    print(f"Listening for {detector.word!r} with openwakeword (threshold={detector._threshold}).")  # noqa: SLF001
    print("Speak the wake word or press Ctrl+C to stop.\n")
    try:
        import sounddevice as sd

        with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype="int16", channels=1) as stream:
            while True:
                data, _ = stream.read(8000)
                scores = detector.frame_scores(bytes(data))
                if not scores:
                    continue
                top = max(scores.values())
                if top >= detector._threshold:  # noqa: SLF001
                    print(f"  *** WAKE WORD DETECTED (score={top:.2f}) ***", flush=True)
                    time.sleep(1)
                elif top > 0.1:
                    print(f"  score={top:.2f}", flush=True)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    test_model_cli()
