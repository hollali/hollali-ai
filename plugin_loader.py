from __future__ import annotations

import importlib.util
import inspect
import sys
from collections.abc import Callable
from pathlib import Path

from log import logger

PLUGIN_DIR = Path(__file__).parent / "plugins"
_loaded_plugins: list[object] = []
_discovered = False
_PLUGIN_TIMEOUT = 5


def _run_with_timeout(fn: Callable[[str], str | None], text: str, timeout: int) -> str | None:
    result: list[str | None] = [None]
    exc: list[BaseException | None] = [None]

    def worker() -> None:
        try:
            result[0] = str(fn(text) or "")
        except BaseException as e:
            exc[0] = e

    import threading

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        logger.warning(f"Plugin handler timed out after {timeout}s")
        return None
    if exc[0]:
        raise exc[0]
    return result[0]


def discover() -> list[dict]:
    if not PLUGIN_DIR.exists():
        return []

    plugins = []
    for f in sorted(PLUGIN_DIR.iterdir()):
        if f.suffix != ".py" or f.name == "__init__.py" or f.name.startswith("_"):
            continue

        mod_name = f"plugins.{f.stem}"
        if mod_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(mod_name, f)
            if not spec or not spec.loader:
                continue
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            try:
                spec.loader.exec_module(mod)
            except Exception as e:
                logger.error(f"Plugin load error ({f.name}): {e}", exc_info=True)
                continue
        else:
            mod = sys.modules[mod_name]

        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if name.startswith("_"):
                continue
            try:
                plugin = obj()
            except Exception as e:
                logger.error(f"Plugin instantiation error ({name}): {e}", exc_info=True)
                continue
            if hasattr(plugin, "name") and hasattr(plugin, "handle"):
                plugins.append(
                    {
                        "name": plugin.name,
                        "keywords": getattr(plugin, "keywords", [plugin.name.lower()]),
                        "instance": plugin,
                    }
                )
                _loaded_plugins.append(plugin)
                logger.info(f"Loaded plugin: {plugin.name}")

    return plugins


def match(text: str) -> str | None:
    global _discovered
    if not _discovered:
        discover()
        _discovered = True
    for p in _loaded_plugins:
        for kw in getattr(p, "keywords", []):
            if kw in text.lower():
                try:
                    return _run_with_timeout(p.handle, text, _PLUGIN_TIMEOUT)
                except Exception as e:
                    logger.error(f"Plugin error ({p.name}): {e}", exc_info=True)
                    return None
    return None
