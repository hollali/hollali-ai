from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

import plugin_loader


class TestPluginLoader:
    def test_run_with_timeout_normal(self):
        def handler(text: str) -> str | None:
            return "handled"

        result = plugin_loader._run_with_timeout(handler, "test", 5)
        assert result == "handled"

    def test_run_with_timeout_fast_handler(self):
        def handler(text: str) -> str | None:
            return "ok"

        result = plugin_loader._run_with_timeout(handler, "input", 5)
        assert result == "ok"

    def test_run_with_timeout_slow_handler(self):
        import time

        def handler(text: str) -> str | None:
            time.sleep(10)
            return "too late"

        result = plugin_loader._run_with_timeout(handler, "test", 1)
        assert result is None

    def test_run_with_timeout_exception(self):
        def handler(text: str) -> str | None:
            raise ValueError("oops")

        with pytest.raises(ValueError):
            plugin_loader._run_with_timeout(handler, "test", 5)

    def test_discover_no_plugin_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = plugin_loader.PLUGIN_DIR
            try:
                plugin_loader.PLUGIN_DIR = Path(tmp) / "nonexistent"
                result = plugin_loader.discover()
                assert result == []
            finally:
                plugin_loader.PLUGIN_DIR = original
