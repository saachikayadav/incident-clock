# IncidentClock — system models (as delivered, Phase 3)

These models describe the code in this repository at the Phase 3 increment. A box appears
only if the matching component exists in code; planned Phase 4–5 elements are drawn dashed
and labelled "planned". GitHub renders the Mermaid blocks directly.

Source of truth for each model:

| Model | Type | Derived from |
|---|---|---|
| M1 Incident status | State machine | `derive_status()` in `app/main.py`; Phase 2 Model 1 |
| M2 Information model | ER / schema | `app/schema.sql` (tables, keys, checks, triggers) |
| M3 Deadline calculation | Activity | Phase 2 Model 3 — **not yet implemented** (Phase 4) |
| M4 Request check order | Activity | `_observe` middleware + handlers in `app/main.py` |
| A1 Architecture & data flow | Component | `app/` modules; `render.yaml`; Phase 2 Q7.1 |

---

## A1 — Architecture and data flow (component)

```mermaid
flowchart LR
  subgraph Clients
    T["Pod test runner<br/>(pytest, BASE_URL + API_KEY)"]
    U["Reviewer / grader<br/>(HTTP client)"]
  end

  subgraph Render["Render web service (Docker, region ohio)"]
    MW["Middleware _observe<br/>request id · X-API-Key check (401)<br/>timing · JSON log line"]
    H["Route handlers (app/main.py)<br/>404 existence → 400 validation"]
    V["validation.py<br/>RFC 3339 + offset, field rules,<br/>INVALID_&lt;FIELD&gt; errors"]
    S["Store (app/db.py)<br/>psycopg pool, INSERT-only,<br/>one transaction per write"]
    D["deadline module<br/>(planned, Phase 4)"]
  end

  DB[("Render Postgres 16<br/>incidents · evidence · events<br/>append-only triggers")]
  LOG[["Render log stream<br/>(stdout JSON)"]]
  GH["GitHub repo + Actions CI<br/>autoDeployTrigger: checksPass"]

  T -- "HTTPS JSON (common interface)" --> MW
  U -- "HTTPS JSON" --> MW
  MW --> H
  H --> V
  H --> S
  S -- "SQL" --> DB
  MW -- "1 line / request" --> LOG
  GH -- "deploy commit SHA<br/>(RENDER_GIT_COMMIT → X-Service-Version)" --> Render
  H -.-> D

  classDef planned stroke-dasharray: 5 5,color:#888;
  class D planned;
```

**Responsibilities retained outside the system:** materiality judgment (disclosure committee),
filing on EDGAR, and API-key distribution to the pod (shared out of band).

---

## M1 — Incident status (state machine)

Status is never stored; it is derived from the current decision and filing (Phase 2 Q3.3).
In Phase 3 no decision or filing can exist, so every incident is `OPEN`.

```mermaid
stateDiagram-v2
  [*] --> OPEN : POST /incidents (201)
  OPEN --> OPEN : POST evidence (201)
  OPEN --> MATERIAL_PENDING_FILING : decision MATERIAL (planned P4)
  OPEN --> NOT_MATERIAL : decision NOT_MATERIAL (planned P4)
  NOT_MATERIAL --> MATERIAL_PENDING_FILING : correction to MATERIAL (planned P5)
  MATERIAL_PENDING_FILING --> NOT_MATERIAL : correction to NOT_MATERIAL (planned P5)
  MATERIAL_PENDING_FILING --> FILED : POST filing (planned P5)
  FILED --> FILED : decision / correction → 409 (planned P4–5)

  note right of OPEN
    Delivered in Phase 3: only OPEN is reachable.
    Edit/delete on an incident → 405 in any state.
  end note
```

---

## M2 — Information model (ER, as implemented in `app/schema.sql`)

```mermaid
erDiagram
  INCIDENTS ||--o{ EVIDENCE : "has (FK incident_seq)"
  INCIDENTS ||--o{ EVENTS : "history (FK incident_seq)"

  INCIDENTS {
    bigint seq PK "BIGSERIAL"
    text incident_id UK "generated: INC-001, INC-002 ..."
    text title "required, <=200 (proposed)"
    text description "required, <=5000 (proposed)"
    timestamptz discovered_at "required, offset mandatory, not future"
    text reporter_name "required"
    timestamptz created_at "DB clock"
  }
  EVIDENCE {
    bigint seq PK
    text evidence_id UK "generated: EVD-001 ..."
    bigint incident_seq FK
    text category "CHECK in TECHNICAL, BUSINESS_IMPACT, LEGAL, OTHER"
    text summary
    text source
    timestamptz collected_at
    timestamptz recorded_at "DB clock"
  }
  EVENTS {
    bigint seq PK "recording order"
    bigint incident_seq FK
    text event_type "INCIDENT_CREATED, EVIDENCE_ADDED (P3); others planned"
    text reference_id "INC-/EVD- id"
    timestamptz recorded_at "same instant as the resource"
  }
```

Invariants enforced by the database, not only the application:
- `BEFORE UPDATE OR DELETE` triggers on all three tables raise an error (REQ-07).
- `POST /reset` uses `TRUNCATE ... RESTART IDENTITY`, which bypasses row triggers and restarts
  ID numbering (REQ-14). It is the only removal path.
- Evidence cannot reference a missing incident (FK).

Planned (not in code yet): `decisions` (with `supersedes` link for corrections, REQ-06) and `filings`.

---

## M3 — Deadline calculation (activity) — planned, Phase 4

Not implemented in Phase 3. The rule agreed in Phase 2 is unchanged: take the Eastern Time
calendar date of `determinedAt` as day 0; count forward, skipping Saturdays, Sundays and dates
on the pod's shared holiday list; the 4th counted day is the deadline (Form 8-K Gen. Instr. B.1).

---

## M4 — Request check order (activity, as implemented)

```mermaid
flowchart TD
  A[Request arrives] --> P{Path is /health<br/>or /openapi.yaml?}
  P -- yes --> R[Route]
  P -- no --> K{X-API-Key present<br/>and equal?}
  K -- no --> E401[401 UNAUTHORIZED]
  K -- yes --> R
  R --> M{Path + method<br/>routed?}
  M -- "path unknown" --> E404a[404 NOT_FOUND]
  M -- "method not allowed<br/>(PUT/PATCH/DELETE)" --> E405[405 METHOD_NOT_ALLOWED]
  M -- yes --> X{incidentId in path?}
  X -- "no: POST /incidents" --> B
  X -- "no: /health, /reset" --> OK
  X -- yes --> F{Incident exists?}
  F -- no --> E404b[404 NOT_FOUND]
  F -- yes --> I{Phase 4/5 operation?}
  I -- yes --> E501[501 NOT_IMPLEMENTED]
  I -- no --> B{Body is a JSON object<br/>and every field valid?}
  B -- no --> E400["400 INVALID_&lt;FIELD&gt; / INVALID_BODY"]
  B -- yes --> W[(INSERT in one transaction)]
  W --> OK[201 / 200 + JSON]
  E401 & E405 & E404a & E404b & E501 & E400 & OK --> L[One JSON log line:<br/>status, latency_ms, error_code, version]
```

409 (state conflicts) will sit between the 400 check and the write once decisions exist (Phase 4).
