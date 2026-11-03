"""IncidentClock web frontend (Flask) for the Phase 3 API.

Covers what the service implements today: health, create incident, view incident with
its evidence, and add evidence. Decisions, deadlines, filings and the timeline are left
out until the API delivers them (Phases 4-5).

The browser only talks to this app; this app calls the API with X-API-Key. The key
never reaches the browser, and the API needs no CORS support.

The API has no list operation, so "recent incidents" are the ones this browser created
or opened, kept in the signed session cookie.
"""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.wrappers import Response

EVIDENCE_CATEGORIES = {
    "TECHNICAL": "Technical",
    "BUSINESS_IMPACT": "Business impact",
    "LEGAL": "Legal",
    "OTHER": "Other",
}
MAX_RECENT = 20
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_OFFSET = re.compile(r"^[+-]\d{2}:\d{2}$")
_LOCAL_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")
# UTC offsets in current use, with the standard timezone names that use each one (standard
# and daylight time both appear, since the offset for a zone changes with DST). The user
# picks one explicitly for every timestamp.
UTC_OFFSETS = {
    "-12:00": "",
    "-11:00": "SST",
    "-10:00": "HST",
    "-09:30": "MART",
    "-09:00": "AKST, HDT",
    "-08:00": "PST, AKDT",
    "-07:00": "MST, PDT",
    "-06:00": "CST, MDT",
    "-05:00": "EST, CDT",
    "-04:00": "EDT, AST",
    "-03:30": "NST",
    "-03:00": "ADT, BRT, ART",
    "-02:00": "",
    "-01:00": "CVT",
    "+00:00": "GMT, WET",
    "+01:00": "CET, BST, WAT",
    "+02:00": "EET, CEST, SAST",
    "+03:00": "MSK, EEST",
    "+03:30": "IRST",
    "+04:00": "GST",
    "+04:30": "AFT",
    "+05:00": "PKT",
    "+05:30": "IST",
    "+05:45": "NPT",
    "+06:00": "BDT",
    "+06:30": "MMT",
    "+07:00": "ICT, WIB",
    "+08:00": "SGT, AWST, China",
    "+08:45": "ACWST",
    "+09:00": "JST, KST",
    "+09:30": "ACST",
    "+10:00": "AEST",
    "+10:30": "ACDT",
    "+11:00": "AEDT",
    "+12:00": "NZST",
    "+12:45": "CHAST",
    "+13:00": "NZDT",
    "+14:00": "LINT",
}
# Times are displayed in UTC with Eastern Time alongside: REQ-09 counts filing deadlines
# by the Eastern Time date, so ET is the zone that matters for every incident.
DISPLAY_TZ = ZoneInfo("America/New_York")


class ApiUnavailable(Exception):
    """The API could not be reached, or answered in a way the UI cannot use."""


@dataclass(frozen=True)
class ApiResult:
    status: int
    body: dict[str, Any]


def create_app(
    api_url: str | None = None,
    api_key: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> Flask:
    api_url = api_url or os.environ.get("INCIDENT_API_URL", "http://127.0.0.1:8000")
    api_key = api_key if api_key is not None else os.environ.get("API_KEY", "")
    if not api_key:
        raise RuntimeError("API_KEY environment variable is required")
    # REQ-13: the key travels with every call, so the API must be reached over HTTPS
    # (plain HTTP is allowed only to a service on this machine, for local development).
    parsed = httpx.URL(api_url)
    if parsed.scheme != "https" and parsed.host not in LOCAL_HOSTS:
        raise RuntimeError(f"INCIDENT_API_URL must use https unless it is local (got {api_url})")

    app = Flask(__name__)
    # A random fallback only means sessions (recent incidents) reset on restart.
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
    client = httpx.Client(base_url=api_url, headers={"X-API-Key": api_key}, timeout=10.0, transport=transport)

    def call(method: str, path: str, payload: dict[str, Any] | None = None) -> ApiResult:
        try:
            resp = client.request(method, path, json=payload)
        except httpx.HTTPError as exc:
            raise ApiUnavailable(f"could not reach the API at {api_url} ({type(exc).__name__})") from exc
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code == 401:
            raise ApiUnavailable("the API rejected this frontend's API_KEY")
        if resp.status_code >= 500:
            request_id = resp.headers.get("X-Request-ID", "unknown")
            raise ApiUnavailable(f"the API returned {resp.status_code} (request id {request_id})")
        return ApiResult(resp.status_code, body if isinstance(body, dict) else {})

    def api_health() -> str:
        try:
            resp = client.get("/health")
        except httpx.HTTPError:
            return "down"
        return "ok" if resp.status_code == 200 else "degraded"

    def remember(incident_id: str, title: str) -> None:
        recent = [r for r in session.get("recent", []) if r["id"] != incident_id]
        session["recent"] = [{"id": incident_id, "title": title}, *recent][:MAX_RECENT]

    def render_home(form: dict[str, str], errors: dict[str, str], status: int = 200) -> tuple[str, int]:
        html = render_template(
            "home.html", form=form, errors=errors, health=api_health(), recent=session.get("recent", [])
        )
        return html, status

    def render_incident(
        incident_id: str, form: dict[str, str], errors: dict[str, str], status: int = 200
    ) -> tuple[str, int]:
        result = call("GET", f"/incidents/{incident_id}")
        if result.status == 404:
            return render_template("not_found.html", incident_id=incident_id), 404
        incident = result.body
        remember(incident["incidentId"], incident["title"])
        html = render_template(
            "incident.html", incident=incident, form=form, errors=errors, categories=EVIDENCE_CATEGORIES
        )
        return html, status

    @app.errorhandler(ApiUnavailable)
    def _api_unavailable(exc: ApiUnavailable) -> tuple[str, int]:
        return render_template("error.html", message=str(exc)), 502

    @app.context_processor
    def _globals() -> dict[str, Any]:
        return {"category_label": lambda c: EVIDENCE_CATEGORIES.get(c, c), "utc_offsets": UTC_OFFSETS}

    app.add_template_filter(format_utc, "utc")

    @app.get("/")
    def home() -> tuple[str, int]:
        return render_home({}, {})

    @app.post("/incidents")
    def create_incident() -> Response | tuple[str, int]:
        form = submitted_form()
        payload = {
            "title": form.get("title", ""),
            "description": form.get("description", ""),
            "reporterName": form.get("reporterName", ""),
        }
        problem = add_timestamp(payload, form, "discoveredAt")
        if problem:
            return render_home(form, problem, 400)
        result = call("POST", "/incidents", payload)
        if result.status == 201:
            incident_id = result.body["incidentId"]
            remember(incident_id, payload["title"])
            flash(f"Created {incident_id} with status {result.body.get('status', 'OPEN')}.")
            return redirect(url_for("incident", incident_id=incident_id))
        #400 error recieved for timestamp being off
        return render_home(form, field_errors(result), 400)

    @app.get("/open")
    def open_incident() -> Response:
        incident_id = request.args.get("id", "").strip().upper()
        if not incident_id:
            return redirect(url_for("home"))
        return redirect(url_for("incident", incident_id=incident_id))

    @app.get("/incidents/<incident_id>")
    def incident(incident_id: str) -> tuple[str, int]:
        return render_incident(incident_id, {}, {})

    @app.post("/incidents/<incident_id>/evidence")
    def add_evidence(incident_id: str) -> Response | tuple[str, int]:
        form = submitted_form()
        payload: dict[str, Any] = {
            "category": form.get("category") or None,
            "summary": form.get("summary", ""),
            "source": form.get("source", ""),
        }
        problem = add_timestamp(payload, form, "collectedAt")
        if problem:
            return render_incident(incident_id, form, problem, 400)
        result = call("POST", f"/incidents/{incident_id}/evidence", payload)
        if result.status == 201:
            flash(f"Added {result.body['evidenceId']}.")
            return redirect(url_for("incident", incident_id=incident_id) + "#evidence")
        if result.status == 404:
            return render_template("not_found.html", incident_id=incident_id), 404
        return render_incident(incident_id, form, field_errors(result), 400)

    return app


def submitted_form() -> dict[str, str]:
    """The posted form with textarea line breaks (CRLF) normalized to LF.

    Browsers send each line break as two characters, while the on-page counter (and the
    reader) sees one; normalizing keeps the API's length check in step with the counter.
    """
    return {k: v.replace("\r\n", "\n") for k, v in request.form.items()}


def add_timestamp(payload: dict[str, Any], form: dict[str, str], field: str) -> dict[str, str]:
    """Put `field` into `payload` as RFC 3339 with the offset the user chose.

    The API refuses timestamps without an offset, so the frontend never invents one
    (no silent UTC fallback): a missing offset is reported on the form instead.
    An empty value is left out so the API reports the field as required.
    Returns {field: message} when the form input cannot be sent, else {}.
    """
    local = form.get(field, "").strip()
    if not local:
        return {}
    offset = form.get(f"{field}_offset", "")
    if not _OFFSET.match(offset):
        return {field: f"{field} needs a UTC offset"}
    if _LOCAL_DATETIME.match(local) and len(local) == 16:
        local += ":00"
    # A malformed date/time is sent as typed so the API names the field and rejects it.
    payload[field] = local + offset
    return {}


def format_utc(value: str) -> str:
    """Show an API timestamp (always UTC) with Eastern Time in parentheses, the same for every viewer.

    "2026-10-01 14:00:00 UTC (10:00:00 EDT)"; the Eastern date is added when it differs:
    "2026-10-02 02:00:00 UTC (2026-10-01 22:00:00 EDT)".
    """
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return str(value)
    utc, eastern = dt.astimezone(UTC), dt.astimezone(DISPLAY_TZ)
    eastern_fmt = "%H:%M:%S %Z" if eastern.date() == utc.date() else "%Y-%m-%d %H:%M:%S %Z"
    return f"{utc:%Y-%m-%d %H:%M:%S} UTC ({eastern.strftime(eastern_fmt)})"


def field_errors(result: ApiResult) -> dict[str, str]:
    """Map an API 400 to {field: message}. INVALID_<FIELD> messages start with the field name."""
    code = str(result.body.get("error", ""))
    message = str(result.body.get("message", "")) or code or f"request failed ({result.status})"
    if code.startswith("INVALID_") and code != "INVALID_BODY":
        return {message.split(" ", 1)[0]: message}
    return {"_form": message}


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("FRONTEND_PORT", "5001")), debug=True)
