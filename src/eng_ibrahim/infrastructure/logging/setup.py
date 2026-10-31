"""Daily rotating log, 30 days retention (SPEC 24.2). Never log credentials."""
from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging(log_dir: Path, level: int = logging.INFO, retention_days: int = 30) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_eng_ibrahim", False):
            root.removeHandler(h)
            h.close()
    handler = TimedRotatingFileHandler(
        log_file, when="midnight", backupCount=retention_days, encoding="utf-8"
    )
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler._eng_ibrahim = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)
    return log_file
