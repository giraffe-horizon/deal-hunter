"""Centralized logging configuration.

Two flavors:

* `setup_app_logging()` — the main CLI / services setup: stream + rotating file
  handler under the repo root. Safe to call multiple times (no-op on repeats).
* `setup_bot_logging()` — feedback-bot flavor: stream only, simpler format.

Call from entrypoints (cli.main, bot.main). Library code should just do
``logger = logging.getLogger(__name__)`` and inherit from the root.
"""

from __future__ import annotations

import logging
from pathlib import Path

from deal_hunter.core.settings import get_settings

_DEFAULT_FORMAT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_app_logging(
    *,
    level: int = logging.INFO,
    log_file: Path | None = None,
) -> None:
    """Configure the root logger with stream + file handler. Idempotent."""
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(level)

    fmt = logging.Formatter(_DEFAULT_FORMAT, datefmt=_DATEFMT)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    target = log_file or (get_settings().base_dir / "deal_hunter.log")
    fh = logging.FileHandler(target, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)


def setup_bot_logging(*, level: int = logging.INFO) -> None:
    """Stream-only logging for the feedback bot. Idempotent."""
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        level=level,
    )
