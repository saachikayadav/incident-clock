-- IncidentClock persistent schema (Phase 4).
-- Append-only: rows are never updated or deleted by the application (REQ-07).
-- Row-level triggers reject UPDATE/DELETE; POST /reset uses TRUNCATE, which does
-- not fire row triggers (REQ-14 test reset is the only sanctioned removal).
-- Incident status is NOT stored: it is derived from the current decision and
-- filing (Phase 2, Q3.3). Decisions and filings were added in Phase 4.

CREATE TABLE IF NOT EXISTS incidents (
    seq            BIGSERIAL PRIMARY KEY,
    incident_id    TEXT GENERATED ALWAYS AS (
                       'INC-' || CASE WHEN seq < 1000 THEN lpad(seq::text, 3, '0') ELSE seq::text END
                   ) STORED UNIQUE,
    title          TEXT        NOT NULL,
    description    TEXT        NOT NULL,
    discovered_at  TIMESTAMPTZ NOT NULL,
    reporter_name  TEXT        NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS evidence (
    seq            BIGSERIAL PRIMARY KEY,
    evidence_id    TEXT GENERATED ALWAYS AS (
                       'EVD-' || CASE WHEN seq < 1000 THEN lpad(seq::text, 3, '0') ELSE seq::text END
                   ) STORED UNIQUE,
    incident_seq   BIGINT      NOT NULL REFERENCES incidents (seq),
    category       TEXT        NOT NULL CHECK (category IN ('TECHNICAL', 'BUSINESS_IMPACT', 'LEGAL', 'OTHER')),
    summary        TEXT        NOT NULL,
    source         TEXT        NOT NULL,
    collected_at   TIMESTAMPTZ NOT NULL,
    recorded_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS evidence_incident_idx ON evidence (incident_seq, seq);
-- Lets decision_evidence prove, in the database, that cited evidence belongs to the
-- decision's own incident (REQ-04/REQ-05).
CREATE UNIQUE INDEX IF NOT EXISTS evidence_seq_incident_uq ON evidence (seq, incident_seq);

-- Human materiality decisions (REQ-04). The deadline is computed once by app/deadline.py
-- when the decision is recorded and stored with it, so a later holiday-list change cannot
-- silently move a recorded deadline. corrects_seq is reserved for Phase 5 corrections (REQ-06).
CREATE TABLE IF NOT EXISTS decisions (
    seq            BIGSERIAL PRIMARY KEY,
    decision_id    TEXT GENERATED ALWAYS AS (
                       'DEC-' || CASE WHEN seq < 1000 THEN lpad(seq::text, 3, '0') ELSE seq::text END
                   ) STORED UNIQUE,
    incident_seq   BIGINT      NOT NULL REFERENCES incidents (seq),
    decision       TEXT        NOT NULL CHECK (decision IN ('MATERIAL', 'NOT_MATERIAL')),
    determined_at  TIMESTAMPTZ NOT NULL,
    decided_by     TEXT        NOT NULL,
    rationale      TEXT        NOT NULL,
    deadline       DATE,
    corrects_seq   BIGINT      REFERENCES decisions (seq),
    recorded_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CHECK ((decision = 'MATERIAL') = (deadline IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS decisions_incident_idx ON decisions (incident_seq, seq);

CREATE TABLE IF NOT EXISTS decision_evidence (
    decision_seq   BIGINT NOT NULL REFERENCES decisions (seq),
    position       INT    NOT NULL,
    evidence_seq   BIGINT NOT NULL,
    incident_seq   BIGINT NOT NULL,
    PRIMARY KEY (decision_seq, position),
    UNIQUE (decision_seq, evidence_seq),
    FOREIGN KEY (evidence_seq, incident_seq) REFERENCES evidence (seq, incident_seq)
);

-- 8-K filing records (REQ-11). At most one per incident.
CREATE TABLE IF NOT EXISTS filings (
    seq               BIGSERIAL PRIMARY KEY,
    filing_id         TEXT GENERATED ALWAYS AS (
                          'FIL-' || CASE WHEN seq < 1000 THEN lpad(seq::text, 3, '0') ELSE seq::text END
                      ) STORED UNIQUE,
    incident_seq      BIGINT      NOT NULL UNIQUE REFERENCES incidents (seq),
    decision_seq      BIGINT      NOT NULL REFERENCES decisions (seq),
    filed_at          TIMESTAMPTZ NOT NULL,
    accession_number  TEXT        NOT NULL,
    timeliness        TEXT        NOT NULL CHECK (timeliness IN ('ON_TIME', 'LATE')),
    business_days_late INT        NOT NULL CHECK (business_days_late >= 0),
    recorded_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Audit/history log feeding the REQ-12 timeline (endpoint delivered in Phase 5).
CREATE TABLE IF NOT EXISTS events (
    seq            BIGSERIAL PRIMARY KEY,
    incident_seq   BIGINT      NOT NULL REFERENCES incidents (seq),
    event_type     TEXT        NOT NULL CHECK (event_type IN (
                       'INCIDENT_CREATED', 'EVIDENCE_ADDED', 'DECISION_RECORDED',
                       'DECISION_CORRECTED', 'FILING_RECORDED')),
    reference_id   TEXT        NOT NULL,
    recorded_at    TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS events_incident_idx ON events (incident_seq, seq);

CREATE OR REPLACE FUNCTION reject_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'table % is append-only', TG_TABLE_NAME USING ERRCODE = 'insufficient_privilege';
END
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER incidents_append_only BEFORE UPDATE OR DELETE ON incidents
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE OR REPLACE TRIGGER evidence_append_only BEFORE UPDATE OR DELETE ON evidence
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE OR REPLACE TRIGGER events_append_only BEFORE UPDATE OR DELETE ON events
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE OR REPLACE TRIGGER decisions_append_only BEFORE UPDATE OR DELETE ON decisions
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE OR REPLACE TRIGGER decision_evidence_append_only BEFORE UPDATE OR DELETE ON decision_evidence
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE OR REPLACE TRIGGER filings_append_only BEFORE UPDATE OR DELETE ON filings
    FOR EACH ROW EXECUTE FUNCTION reject_mutation();

-- Course cross-team testing interface: sessions prepared by POST /test/setup.
-- Not cleared by POST /reset, so a session ID can never be reused (409).
-- The latest row is the active session; superseded sessions keep a frozen
-- coverage snapshot for GET /test/report.
CREATE TABLE IF NOT EXISTS test_sessions (
    seq             BIGSERIAL PRIMARY KEY,
    session_id      TEXT        NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    frozen_coverage JSONB
);
