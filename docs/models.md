# IncidentClock — system models (as delivered, Phase 4)

These models describe the code in this repository at the Phase 4 increment. A box appears
only if the matching component exists in code; planned Phase 5 elements are drawn dashed
and labelled "planned". GitHub renders the Mermaid blocks directly.

Source of truth for each model:

| Model | Type | Derived from |
|---|---|---|
| M1 Incident status | State machine | `status_of()` + `record_decision()`/`record_filing()` state checks in `app/db.py`; Phase 2 Model 1, REQ-08 |
| M2 Information model | ER / schema | `app/schema.sql` (tables, keys, checks, triggers) |
| M3 Deadline calculation | Activity | `app/deadline.py` (`filing_deadline`, `deadline_status`, `days_late`) |
| M4 Request check order | Activity | `_observe` middleware + handlers in `app/main.py`; 409 inside the Store transaction |
| A1 Architecture & data flow | Component | `app/`, `tester/`, `frontend/` modules; `render.yaml`; Phase 2 Q7.1 |
| T1 Cross-team test session | Sequence | `tester/main.py`, `/test/*` routes in `app/main.py`; course testing interface |

---

## A1 — Architecture and data flow (component)

```mermaid
flowchart LR
  G["Grader / podmate<br/>(HTTP client)"]
  PT["Podmate tester"]
  U["Browser user"]

  subgraph FE["Render web service: incident-clock-frontend (Python, gunicorn)"]
    FA["frontend/app.py (Flask)<br/>incident + evidence forms · explicit UTC offset<br/>UTC + Eastern display · API key held server-side"]
  end

  subgraph TS["Render web service: incident-clock-tester (Docker)"]
    TA["tester/main.py<br/>/test/setup · /test/run · /test/report<br/>sessions + reports in memory"]
    TP["pytest subprocess<br/>plan = tests/ (non-provisional)<br/>+ tester/plugin.py outcomes"]
    TR["tester/reporting.py<br/>results + code/component/system coverage"]
  end

  subgraph SYS["Render web service: incident-clock (Docker)"]
    MW["Middleware _observe<br/>request id · X-API-Key check (401)<br/>timing · JSON log line"]
    H["Route handlers (app/main.py)<br/>404 existence → 400 validation<br/>decisions · deadline-status · filing"]
    TI["/test/setup · /test/report<br/>(app/main.py)"]
    CV["coverage_session.py<br/>coverage.py, sys.monitoring core"]
    V["validation.py<br/>RFC 3339 + offset, field rules"]
    S["Store (app/db.py)<br/>psycopg pool, INSERT-only<br/>row lock → 409 state check → INSERT"]
    D["deadline.py<br/>ET date · federal holiday list<br/>deadline · status · days late"]
    C["corrections · timeline<br/>(planned, Phase 5: 501)"]
  end

  DB[("Render Postgres 16<br/>incidents · evidence · decisions · decision_evidence<br/>filings · events (append-only) · test_sessions")]
  LOG[["Render log streams<br/>(stdout JSON)"]]
  GH["GitHub + Actions CI<br/>autoDeployTrigger: checksPass"]

  G -- "target_url" --> TA
  TA --> TP
  TP --> TR
  TA -- "POST /test/setup, GET /test/report<br/>(X-API-Key, registered targets only)" --> MW
  TP -- "pod contract v1.0 requests" --> MW
  PT -- "same interface" --> MW
  G -- "direct testing" --> MW
  U -- "HTML forms" --> FA
  FA -- "pod contract v1.0 requests<br/>(X-API-Key)" --> MW
  MW --> H
  MW --> TI
  TI --> CV
  TI --> S
  H --> V
  H --> S
  S -- "SQL" --> DB
  MW -- "1 line / request" --> LOG
  TA -- "run events" --> LOG
  GH -- "commit SHA → X-Service-Version / tester_version" --> SYS
  GH --> TS
  GH --> FE
  H --> D
  H -.-> C

  classDef planned stroke-dasharray: 5 5,color:#888;
  class C planned;
```

**Responsibilities retained outside the system:** materiality judgment (disclosure committee),
filing on EDGAR, and API-key distribution to the pod (shared out of band; the tester holds keys
only for targets registered in its `TARGETS` setting).

---

## T1 — Cross-team test session (sequence, as implemented)

```mermaid
sequenceDiagram
  autonumber
  actor G as Grader
  participant T as Tester (ours)
  participant P as pytest subprocess
  participant S as Target system
  G->>T: POST /test/setup {target_url}
  alt target not in TARGETS
    T-->>G: 400 {message, source: tester}
  else registered
    T->>S: POST /test/setup {session_id, setup: {}} + X-API-Key
    S->>S: clear project data, register session, restart coverage
    S-->>T: 201 {session_id}
    T-->>G: 201 {session_id}
  end
  G->>T: POST /test/run {session_id}
  T->>P: run tests/ (-m "not provisional"), BASE_URL = target
  loop each planned test, in order
    P->>S: POST /reset, then contract requests
    S-->>P: responses
    P->>P: pass / fail / error(source) / skip → results.jsonl
  end
  T->>S: GET /test/report?session_id
  S-->>T: coverage.code
  T->>T: component + system coverage, store report
  T-->>G: 200 report  (500 + stored partial report on abort)
  G->>T: GET /test/report?session_id (after a lost response)
  T-->>G: stored report (409 until the suite ends)
```

---

## M1 — Incident status (state machine, as implemented)

Status is never stored; `status_of()` derives it from the current decision and whether a
filing exists (Phase 2 Q3.3). The 409 rules are REQ-08, checked after validation inside the
same transaction as the insert, so a rejected request changes nothing.

```mermaid
stateDiagram-v2
  [*] --> OPEN : POST /incidents (201)
  OPEN --> MATERIAL_PENDING_FILING : POST decisions MATERIAL (201, deadline set)
  OPEN --> NOT_MATERIAL : POST decisions NOT_MATERIAL (201, deadline null)
  NOT_MATERIAL --> MATERIAL_PENDING_FILING : POST decisions MATERIAL (201) [ISSUE-20]
  NOT_MATERIAL --> NOT_MATERIAL : POST decisions NOT_MATERIAL (201)
  MATERIAL_PENDING_FILING --> FILED : POST filing (201, ON_TIME / LATE)
  MATERIAL_PENDING_FILING --> MATERIAL_PENDING_FILING : POST decisions → 409
  FILED --> FILED : POST decisions → 409 · POST filing → 409
  OPEN --> OPEN : POST filing → 409
  NOT_MATERIAL --> NOT_MATERIAL : POST filing → 409

  note right of MATERIAL_PENDING_FILING
    Corrections (REQ-06) are planned for Phase 5 and
    return 501 now; they will be the only way to
    change a MATERIAL decision before filing.
  end note
  note left of OPEN
    POST evidence → 201 in every state.
    PUT/PATCH/DELETE → 405 in every state.
  end note
```

---

## M2 — Information model (ER, as implemented in `app/schema.sql`)

```mermaid
erDiagram
  INCIDENTS ||--o{ EVIDENCE : "has"
  INCIDENTS ||--o{ DECISIONS : "decided by"
  INCIDENTS ||--o| FILINGS : "filed as (UNIQUE incident_seq)"
  INCIDENTS ||--o{ EVENTS : "history"
  DECISIONS ||--|{ DECISION_EVIDENCE : "cites (>=1)"
  EVIDENCE ||--o{ DECISION_EVIDENCE : "cited by (FK seq, incident_seq)"
  DECISIONS ||--o| FILINGS : "deadline basis"
  DECISIONS |o--o| DECISIONS : "corrects_seq (Phase 5)"

  INCIDENTS {
    bigint seq PK
    text incident_id UK "INC-001 ..."
    text title "<=200 (proposed)"
    text description "<=5000 (proposed)"
    timestamptz discovered_at "offset mandatory, not future"
    text reporter_name
    timestamptz created_at "DB clock"
  }
  EVIDENCE {
    bigint seq PK
    text evidence_id UK "EVD-001 ..."
    bigint incident_seq FK "UNIQUE (seq, incident_seq)"
    text category "TECHNICAL, BUSINESS_IMPACT, LEGAL, OTHER"
    text summary
    text source
    timestamptz collected_at
    timestamptz recorded_at
  }
  DECISIONS {
    bigint seq PK
    text decision_id UK "DEC-001 ..."
    bigint incident_seq FK
    text decision "MATERIAL, NOT_MATERIAL"
    timestamptz determined_at ">= discovered_at, not future"
    text decided_by
    text rationale
    date deadline "CHECK: set iff MATERIAL"
    bigint corrects_seq FK "null until Phase 5"
    timestamptz recorded_at
  }
  DECISION_EVIDENCE {
    bigint decision_seq PK,FK
    int position PK "request order"
    bigint evidence_seq FK
    bigint incident_seq FK "must equal the evidence's incident"
  }
  FILINGS {
    bigint seq PK
    text filing_id UK "FIL-001 ..."
    bigint incident_seq FK,UK
    bigint decision_seq FK
    timestamptz filed_at
    text accession_number
    text timeliness "ON_TIME, LATE"
    int business_days_late ">= 0"
    timestamptz recorded_at
  }
  EVENTS {
    bigint seq PK "recording order"
    bigint incident_seq FK
    text event_type "INCIDENT_CREATED, EVIDENCE_ADDED, DECISION_RECORDED, FILING_RECORDED (DECISION_CORRECTED in P5)"
    text reference_id "INC-/EVD-/DEC-/FIL- id"
    timestamptz recorded_at
  }
  TEST_SESSIONS {
    bigint seq PK "latest row = active session"
    text session_id UK
    timestamptz created_at
    jsonb frozen_coverage
  }
```

Invariants enforced by the database, not only the application:
- `BEFORE UPDATE OR DELETE` triggers on all six project tables raise an error (REQ-07).
- `decision_evidence` references `evidence (seq, incident_seq)`, so a decision cannot cite
  another incident's evidence even if the application check were removed (REQ-05).
- `decisions.deadline` is non-null exactly when the decision is MATERIAL; the date is computed
  once by `app/deadline.py` and stored, so a later holiday-list change cannot move it.
- One filing per incident (`UNIQUE incident_seq`).
- `POST /reset` uses `TRUNCATE ... RESTART IDENTITY`, which bypasses row triggers (REQ-14).

`test_sessions` is not cleared by `POST /reset` or `/test/setup`, so a session ID can never be reused.

---

## M3 — Deadline calculation and status (activity, as implemented in `app/deadline.py`)

```mermaid
flowchart TD
  A["determinedAt (RFC 3339 with offset)"] --> B["day0 = calendar date in America/New_York<br/>(DST via zoneinfo)"]
  B --> R{day0 within<br/>2023-01-01 .. 2027-12-20?}
  R -- no --> X["400 INVALID_DETERMINED_AT (ISSUE-17)"]
  R -- yes --> C["n = 0, d = day0"]
  C --> D["d = d + 1 day"]
  D --> E{"Mon–Fri and not in<br/>federal holiday list?"}
  E -- no --> D
  E -- yes --> F["n = n + 1"]
  F --> G{n = 4?}
  G -- no --> D
  G -- yes --> H["deadline = d (stored on the decision)"]

  S["GET deadline-status ?as_of (default now)"] --> T{status is<br/>MATERIAL_PENDING_FILING?}
  T -- no --> NA["NOT_APPLICABLE, deadline null, businessDays 0"]
  T -- yes --> U["a = ET date of as_of"]
  U --> V{a <= deadline?}
  V -- yes --> P["PENDING, businessDays = business days in (a, deadline]"]
  V -- no --> O["OVERDUE, businessDays = max(1, business days in (deadline, a]) (ISSUE-19)"]

  FL["POST filing"] --> FD["f = ET date of filedAt"]
  FD --> FV{f <= deadline?}
  FV -- yes --> ON["ON_TIME, businessDaysLate 0"]
  FV -- no --> LA["LATE, businessDaysLate = max(1, business days in (deadline, f])"]
```

Day 0 is the determination date even when it is a weekend or holiday (AC-10: Saturday Oct 4,
2025 → Thursday Oct 9). Holiday list: `fixtures/holidays.json`.

---

## M4 — Request check order (activity, as implemented)

```mermaid
flowchart TD
  A[Request arrives] --> P{Path is /health, /docs<br/>or an OpenAPI file?}
  P -- yes --> R[Route]
  P -- no --> K{X-API-Key present<br/>and equal?}
  K -- no --> E401[401 UNAUTHORIZED]
  K -- yes --> R
  R --> M{Path + method<br/>routed?}
  M -- "path unknown" --> E404a[404 NOT_FOUND]
  M -- "method not allowed<br/>(PUT/PATCH/DELETE)" --> E405[405 METHOD_NOT_ALLOWED]
  M -- yes --> X{incidentId in path?}
  X -- "no: POST /incidents" --> B
  X -- "no: /health, /reset, /test/*" --> OK
  X -- yes --> F{Incident exists?}
  F -- no --> E404b[404 NOT_FOUND]
  F -- yes --> I{corrections or timeline?<br/>Phase 5}
  I -- yes --> E501[501 NOT_IMPLEMENTED]
  I -- no --> B{Body / as_of valid?<br/>incl. determinedAt >= discoveredAt}
  B -- no --> E400["400 INVALID_&lt;FIELD&gt; / INVALID_BODY"]
  B -- yes --> T["BEGIN; SELECT incident FOR UPDATE"]
  T --> EV{decisions: every evidenceId<br/>belongs to this incident?}
  EV -- no --> E400b["400 INVALID_EVIDENCE_IDS, ROLLBACK"]
  EV -- yes --> S{State allows it?<br/>REQ-08}
  S -- no --> E409[409 STATE_CONFLICT, ROLLBACK]
  S -- yes --> W[(INSERT record + event; COMMIT)]
  W --> OK[201 / 200 + JSON]
  E401 & E405 & E404a & E404b & E501 & E400 & E409 & E400b & OK --> L[One JSON log line:<br/>status, latency_ms, error_code, version]
```

Every 400 precedes every 409 (ISSUE-03): field validation runs before the transaction, and the
evidence-ownership check runs inside it, after the incident row is locked but before the state
check. The lock serializes concurrent decisions and filings on one incident, so the state that was
checked is the state the insert commits against.
