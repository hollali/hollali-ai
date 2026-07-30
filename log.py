from __future__ import annotations

import logging
import sys
from pathlib import Path

LOG_PATH = Path.home() / ".hollali" / "hollali.log"


def setup_logger(name: str = "hollali") -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    fh = logging.FileHandler(str(LOG_PATH))
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(ch)

    return logger


logger = setup_logger()
