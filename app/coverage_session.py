"""Per-session code coverage for the course cross-team testing interface.

System GET /test/report must return line coverage "for the project requests made in
this session since setup". Design:

* Coverage uses the ``sysmon`` core (Python 3.12+ ``sys.monitoring``), which traces
  every thread - including the anyio worker threads that run database calls and
  already exist before a session starts. The classic C tracer misses those threads
  (verified empirically; see docs/genai-log.md C9).
* Module-level lines (imports, ``def`` statements) run once at import, before any
  session. They are measured by a *baseline* collector started in ``app/__init__``
  and stopped once the app has started; every session report counts them as
  executed, so the numbers are not deflated by code that cannot run per request.
* A session collector is (re)started by ``POST /test/setup`` and measures only
  ``app/`` source lines executed after that point, plus the baseline.

Scope: line coverage only (sysmon on Python 3.12 does not support branch coverage).
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("COVERAGE_CORE", "sysmon")

try:  # coverage is a runtime dependency, but the service must still run without it
    import coverage
except ImportError:  # pragma: no cover
    coverage = None  # type: ignore[assignment]

APP_DIR = Path(__file__).resolve().parent
_EXCLUDE = {"__init__.py", "coverage_session.py"}
_lock = threading.Lock()


def _source_files() -> list[str]:
    return sorted(str(p) for p in APP_DIR.glob("*.py") if p.name not in _EXCLUDE)


def _new_collector() -> Any:
    return coverage.Coverage(
        data_file=None,
        include=[str(APP_DIR / "*.py")],
        omit=[str(APP_DIR / name) for name in _EXCLUDE],
        config_file=False,
    )


@dataclass
class _State:
    baseline: dict[str, set[int]]
    baseline_cov: Any = None
    session_cov: Any = None
    unavailable_reason: str | None = None


_state = _State(baseline={})


def start_baseline() -> None:
    """Called first thing in app/__init__.py, before other app modules import."""
    if coverage is None:
        _state.unavailable_reason = "coverage package not installed"
        return
    try:
        _state.baseline_cov = _new_collector()
        _state.baseline_cov.start()
    except Exception as exc:  # never let instrumentation stop the service
        _state.baseline_cov = None
        _state.unavailable_reason = f"instrumentation failed to start: {type(exc).__name__}"


def finish_baseline() -> None:
    """Called at app startup, after every app module has been imported."""
    cov = _state.baseline_cov
    if cov is None:
        return
    with _lock:
        cov.stop()
        data = cov.get_data()
        _state.baseline = {f: set(data.lines(f) or []) for f in data.measured_files()}
        _state.baseline_cov = None


def start_session() -> None:
    """(Re)start session measurement. Called by POST /test/setup."""
    if coverage is None or _state.unavailable_reason:
        return
    with _lock:
        if _state.session_cov is not None:
            _state.session_cov.stop()
        _state.session_cov = _new_collector()
        _state.session_cov.start()


def snapshot() -> dict[str, Any]:
    """Line coverage of app/ since the current session's setup (plus import-time lines)."""
    basis_scope = (
        "Executable source lines in the deployed app/ package (__init__ and coverage glue excluded) "
        "executed since this session's /test/setup; module-level lines run at import are counted "
        "as executed. Measured in-process with coverage.py (sys.monitoring core), line coverage only."
    )
    if coverage is None or _state.unavailable_reason:
        reason = _state.unavailable_reason or "instrumentation unavailable"
        return {"covered": None, "total": None, "basis": f"Source lines; {reason}"}
    with _lock:
        cov = _state.session_cov
        if cov is None:
            return {"covered": None, "total": None, "basis": "Source lines; no session measurement running"}
        cov.stop()
        try:
            data = cov.get_data()
            executed = {f: set(data.lines(f) or []) for f in data.measured_files()}
            covered = total = 0
            for path in _source_files():
                _, statements, _, _, _ = cov.analysis2(path)
                stmts = set(statements)
                hit = (executed.get(path, set()) | _state.baseline.get(path, set())) & stmts
                covered += len(hit)
                total += len(stmts)
        finally:
            cov.start()  # resume: later project requests keep updating the measurement
    return {"covered": covered, "total": total, "basis": basis_scope}


def freeze() -> dict[str, Any]:
    """Final snapshot for a session that is being superseded by a new /test/setup."""
    return snapshot()
