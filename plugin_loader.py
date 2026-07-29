from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent / "plugins"

_loaded_plugins: list[object] = []


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
                print(f"Plugin load error ({f.name}): {e}")
                continue
        else:
            mod = sys.modules[mod_name]

        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if name.startswith("_"):
                continue
            plugin = obj()
            if hasattr(plugin, "name") and hasattr(plugin, "handle"):
                plugins.append({
                    "name": plugin.name,
                    "keywords": getattr(plugin, "keywords", [plugin.name.lower()]),
                    "instance": plugin,
                })
                _loaded_plugins.append(plugin)
                print(f"  Loaded plugin: {plugin.name}")

    return plugins


def match(text: str) -> str | None:
    for p in _loaded_plugins:
        for kw in getattr(p, "keywords", []):
            if kw in text.lower():
                try:
                    return str(p.handle(text) or "")
                except Exception as e:
                    print(f"Plugin error ({p.name}): {e}")
                    return None
    return None
