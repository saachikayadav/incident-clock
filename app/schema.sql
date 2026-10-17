-- IncidentClock persistent schema (Phase 3).
-- Append-only: rows are never updated or deleted by the application (REQ-07).
-- Row-level triggers reject UPDATE/DELETE; POST /reset uses TRUNCATE, which does
-- not fire row triggers (REQ-14 test reset is the only sanctioned removal).
-- Incident status is NOT stored: it is derived from the current decision and
-- filing (Phase 2, Q3.3). Decision/filing tables arrive in Phases 4-5.

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
