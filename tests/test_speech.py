from __future__ import annotations

import speech


class TestSpeech:
    def test_call_wake_word_detected(self):
        assert speech.call("Hollali, do something") is True
        assert speech.call("hey hollali") is True
        assert speech.call("hollali") is True

    def test_call_wake_word_not_detected(self):
        assert speech.call("hello there") is False
        assert speech.call("what is the weather") is False
        assert speech.call("") is False

    def test_is_speaking_default(self):
        assert speech.is_speaking() is False

    def test_rms_with_silence(self):
        data = bytes([0, 0]) * 100
        rms = speech._rms(data)
        assert rms == 0.0

    def test_rms_with_known_input(self):
        data = bytes([100, 0]) * 100
        rms = speech._rms(data)
        assert rms > 0.0

    def test_rms_with_empty_data(self):
        assert speech._rms(b"") == 0.0
