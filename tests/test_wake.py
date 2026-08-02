from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import wake
from wake import build_wake_pattern, matches


class FakeModel:
    def __init__(self, scores):
        self.scores = dict(scores)

    def predict(self, audio):
        return dict(self.scores)


def detector_with_model(model, threshold=0.5) -> wake.WakeWordDetector:
    with patch("config.WAKE_ENGINE", "stt"):
        det = wake.WakeWordDetector(word="hollali")
    det._active = True  # noqa: SLF001
    det._model = model  # noqa: SLF001
    det._threshold = threshold  # noqa: SLF001
    return det


class TestFrameScores:
    def test_empty_until_80ms_window_accumulates(self):
        det = detector_with_model(FakeModel({"hollali": 0.1}))
        assert det.frame_scores(b"\x00\x00" * 100) == {}
        assert det.frame_scores(b"\x00\x00" * 3000) == {"hollali": 0.1}

    def test_normalizes_dict_predictions(self):
        det = detector_with_model(FakeModel({"hollali": {"score": 0.9}}))
        assert det.frame_scores(b"\x00\x00" * 2560) == {"hollali": 0.9}

    def test_empty_when_inactive(self):
        with patch("config.WAKE_ENGINE", "stt"):
            det = wake.WakeWordDetector(word="hollali")
        assert det.frame_scores(b"\x00\x00" * 2560) == {}

    def test_empty_on_inference_error(self):
        class BrokenModel:
            def predict(self, audio):
                raise RuntimeError("boom")

        det = detector_with_model(BrokenModel())
        assert det.frame_scores(b"\x00\x00" * 2560) == {}

    def test_feed_triggers_above_threshold(self):
        det = detector_with_model(FakeModel({"hollali": 0.9}), threshold=0.5)
        assert det.feed(b"\x00\x00" * 2560) is True

    def test_feed_ignores_below_threshold(self):
        det = detector_with_model(FakeModel({"hollali": 0.2}), threshold=0.5)
        assert det.feed(b"\x00\x00" * 2560) is False


class TestIsWakewordModel:
    def _patch_session(self, shapes):
        class FakeInput:
            def __init__(self, shape):
                self.shape = shape

        class FakeSession:
            def __init__(self, *_args, **_kwargs):
                self._inputs = [FakeInput(s) for s in shapes]

            def get_inputs(self):
                return self._inputs

        return patch("onnxruntime.InferenceSession", FakeSession)

    def test_accepts_3d_feature_input(self):
        with self._patch_session([[1, 16, 96]]):
            assert wake.WakeWordDetector._is_wakeword_model(Path("wake.onnx"))  # noqa: SLF001

    def test_rejects_4d_auxiliary_input(self):
        with self._patch_session([["unk", 76, 32, 1]]):
            assert not wake.WakeWordDetector._is_wakeword_model(Path("embedding.onnx"))  # noqa: SLF001


class TestBuildWakePattern:
    def test_matches_exact(self):
        assert matches("hollali", "hollali")

    def test_matches_case_insensitive(self):
        assert matches("HEY HOLLALI", "hollali")

    def test_matches_with_prefixes(self):
        for prefix in ("hey", "ok", "okay"):
            assert matches(f"{prefix} hollali", "hollali"), prefix

    def test_matches_embedded_in_sentence(self):
        assert matches("hello hollali what time is it", "hollali")

    def test_rejects_partial_words(self):
        assert not matches("hollalina is my friend", "hollali")
        assert not matches("hollalic", "hollali")

    def test_rejects_other_words(self):
        assert not matches("holiday", "hollali")
        assert not matches("hello", "hollali")

    def test_rejects_short_prefix_no_word(self):
        assert not matches("hey there", "hollali")

    def test_custom_word(self):
        assert matches("jarvis", "jarvis")
        assert matches("hey jarvis", "jarvis")
        assert not matches("jarvisso", "jarvis")


class TestDetectorFallback:
    @patch("config.WAKE_ENGINE", "stt")
    def test_detector_inactive_for_stt_engine(self):
        det = wake.WakeWordDetector(word="hollali")
        assert det.active is False
        assert det.feed(b"\x00\x00" * 2000) is False

    @patch("config.WAKE_ENGINE", "openwakeword")
    def test_detector_falls_back_when_library_missing(self):
        with patch("config.OPENWAKEWORD_MODEL_DIR", "/nonexistent"):
            det = wake.WakeWordDetector(word="hollali")
        assert det.active is False

    @patch("config.WAKE_ENGINE", "openwakeword")
    def test_listen_for_wake_returns_empty_when_inactive(self):
        with patch("config.OPENWAKEWORD_MODEL_DIR", "/nonexistent"):
            result = wake.listen_for_wake()
        assert result == ""


class TestPatternCompilation:
    def test_pattern_ignores_word_boundary_false_positives(self):
        pat = build_wake_pattern("hollali")
        assert pat.search("hollali") is not None
        assert pat.search("hollali!") is not None
        assert pat.search("hollalina") is None
        assert pat.search("holla") is None
