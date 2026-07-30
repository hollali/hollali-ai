from __future__ import annotations

import os
from unittest.mock import patch

import config


class TestConfig:
    def test_getenv_returns_default_when_not_set(self):
        with patch.dict(os.environ, {}, clear=True):
            val = config._getenv("MISSING_VAR", "fallback")
            assert val == "fallback"

    def test_getenv_returns_empty_string_default(self):
        with patch.dict(os.environ, {}, clear=True):
            val = config._getenv("MISSING_VAR")
            assert val == ""

    def test_getenv_returns_env_value(self):
        with patch.dict(os.environ, {"MY_VAR": "my_value"}, clear=True):
            val = config._getenv("MY_VAR", "fallback")
            assert val == "my_value"

    def test_platform_flags_exist(self):
        assert isinstance(config.IS_WINDOWS, bool)
        assert isinstance(config.IS_MACOS, bool)
        assert isinstance(config.IS_LINUX, bool)

    def test_module_constants_are_strings(self):
        assert isinstance(config.GMAIL_USER, str)
        assert isinstance(config.LLM_MODEL, str)
        assert isinstance(config.STT_ENGINE, str)
        assert isinstance(config.TTS_ENGINE, str)
