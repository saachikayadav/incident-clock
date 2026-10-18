"""IncidentClock service package.

The baseline coverage collector starts before any other app module is imported so
that import-time lines are measured once (see coverage_session.py).
"""

from . import coverage_session as _coverage_session

_coverage_session.start_baseline()
