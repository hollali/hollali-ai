try:
    import hollali_fast as _rust
except Exception:  # pragma: no cover - optional accelerator
    _rust = None

RUST_AVAILABLE = _rust is not None


def __getattr__(name):
    if _rust is not None and hasattr(_rust, name):
        return getattr(_rust, name)
    raise AttributeError(name)
