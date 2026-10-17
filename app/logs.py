"""Structured JSON logging to stdout (Phase 2, Q7.3).

One line per request plus explicit events (startup, auth failures, validation
failures, unexpected errors). Request bodies and the X-API-Key header are never
logged.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_logger = logging.getLogger("incidentclock")


def setup() -> None:
    if _logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


def log(level: str, event: str, **fields: Any) -> None:
    record = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "level": level,
        "event": event,
        **fields,
    }
    _logger.log(getattr(logging, level.upper(), logging.INFO), json.dumps(record, default=str))
