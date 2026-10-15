"""Logging setup shared by the API and the CLI entry points."""

from __future__ import annotations

import logging
import sys


def configure_logging(debug: bool = False) -> None:
    """Install a single concise handler on the root logger."""
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", "%H:%M:%S")
    )
    root.addHandler(handler)
    root.setLevel(level)
    # Uvicorn's access log is noisy during tests; keep our own logs readable.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
