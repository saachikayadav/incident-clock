"""Runtime configuration, read once from environment variables.

Secrets (API_KEY, DATABASE_URL) are never committed; they are injected by the
host as environment variables (Phase 2, Q7.3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    api_key: str
    database_url: str
    version: str


def load_settings() -> Settings:
    api_key = os.environ.get("API_KEY", "")
    database_url = os.environ.get("DATABASE_URL", "")
    if not api_key:
        raise RuntimeError("API_KEY environment variable is required")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")
    # Render exposes the deployed commit as RENDER_GIT_COMMIT; SERVICE_VERSION overrides.
    version = os.environ.get("SERVICE_VERSION") or os.environ.get("RENDER_GIT_COMMIT") or "dev"
    return Settings(api_key=api_key, database_url=database_url, version=version[:12])


# Field length limits. The submitted contract says maximum lengths are "agreed by
# both teams" without fixing numbers; these are this team's proposal pending pod
# agreement (docs/spec-issues.md, ISSUE-02).
MAX_LEN = {
    "title": 200,
    "description": 5000,
    "reporterName": 200,
    "summary": 5000,
    "source": 500,
}
