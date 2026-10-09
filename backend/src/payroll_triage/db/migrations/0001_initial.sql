-- Migration 0001: Phase 1 data model (architecture overview, section 7).
-- Applied by `uv run ptc migrate` inside one transaction. LangGraph checkpoint tables are
-- created by the checkpointer's own setup() in the same database (ADR-013).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE agreement_versions (
    code            text NOT NULL,
    version         text NOT NULL,
    name            text NOT NULL,
    effective_from  date NOT NULL,
    effective_to    date NOT NULL,
    PRIMARY KEY (code, version)
);

-- Corpus chunks for hybrid retrieval: one row per anchored agreement section and one per deal
-- memo. `effective_from`/`effective_to` and `permission_scope` exist from day one (ADR-011) but
-- are not filtered on in Phase 1.
CREATE TABLE corpus_chunks (
    id               bigserial PRIMARY KEY,
    source_type      text NOT NULL CHECK (source_type IN ('agreement', 'deal_memo')),
    citation_key     text NOT NULL UNIQUE,
    agreement_code   text,
    version          text NOT NULL,
    section          text NOT NULL,
    heading          text NOT NULL,
    body             text NOT NULL,
    effective_from   date NOT NULL,
    effective_to     date,
    permission_scope text,
    embedding        vector(384) NOT NULL,
    tsv              tsvector GENERATED ALWAYS AS (
                         to_tsvector('english', heading || ' ' || body)
                     ) STORED
);
CREATE INDEX corpus_chunks_tsv_idx ON corpus_chunks USING gin (tsv);
CREATE INDEX corpus_chunks_version_idx ON corpus_chunks (version);

CREATE TABLE productions (
    id       text PRIMARY KEY,
    title    text NOT NULL,
    season   integer NOT NULL,
    employer text NOT NULL
);

CREATE TABLE employees (
    id   text PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE deal_memos (
    id                        text PRIMARY KEY,
    employee_id               text NOT NULL REFERENCES employees (id),
    production_id             text NOT NULL REFERENCES productions (id),
    occupation_code           text NOT NULL,
    occupation_title          text NOT NULL,
    guild                     text NOT NULL,
    hourly_rate_usd           numeric(10, 2) NOT NULL,
    scale_relationship        text NOT NULL,
    department                text NOT NULL,
    hire_state                text NOT NULL,
    work_state                text NOT NULL,
    start_date                date NOT NULL,
    eligibility_status        text NOT NULL,
    eligibility_completed_on  date,
    raw                       jsonb NOT NULL
);

CREATE TABLE timecards (
    id              text PRIMARY KEY,
    scenario_id     text NOT NULL DEFAULT '',
    employee_id     text NOT NULL REFERENCES employees (id),
    deal_memo_id    text NOT NULL REFERENCES deal_memos (id),
    occupation_code text NOT NULL,
    department      text NOT NULL,
    week_ending     date NOT NULL,
    producer_week   date NOT NULL,
    status          text NOT NULL,
    UNIQUE (employee_id, week_ending)
);

CREATE TABLE timecard_days (
    timecard_id   text NOT NULL REFERENCES timecards (id) ON DELETE CASCADE,
    date          date NOT NULL,
    weekday       text NOT NULL,
    day_type      text NOT NULL,
    work_location text NOT NULL,
    call          numeric(5, 1),
    meal_out      numeric(5, 1),
    meal_in       numeric(5, 1),
    wrap          numeric(5, 1),
    PRIMARY KEY (timecard_id, date)
);

-- One case per timecard with findings; thread_id is the LangGraph thread (equals the case id).
CREATE TABLE cases (
    id              text PRIMARY KEY,
    timecard_id     text NOT NULL UNIQUE REFERENCES timecards (id),
    deal_memo_id    text NOT NULL REFERENCES deal_memos (id),
    week_ending     date NOT NULL,
    findings        jsonb NOT NULL,
    policy_action   text NOT NULL CHECK (policy_action IN ('approve', 'return', 'escalate')),
    amount_usd      numeric(10, 2) NOT NULL,
    priority_score  integer NOT NULL,
    status          text NOT NULL CHECK (status IN (
                        'detected', 'awaiting_decision', 'needs_human_review',
                        'approved', 'returned', 'escalated')),
    review_reason   text,
    thread_id       text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX cases_queue_idx ON cases (priority_score DESC, week_ending ASC);

-- LLM outputs are stored as suggestions, never as decisions.
CREATE TABLE suggestions (
    id                 bigserial PRIMARY KEY,
    case_id            text NOT NULL REFERENCES cases (id),
    kind               text NOT NULL CHECK (kind IN ('explain', 'propose', 'draft')),
    content            jsonb NOT NULL,
    provider           text NOT NULL,
    model              text NOT NULL,
    adapter_version    text NOT NULL,
    validation_status  text NOT NULL DEFAULT 'not_validated'
                       CHECK (validation_status IN ('not_validated', 'valid', 'invalid')),
    validation_detail  jsonb,
    created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX suggestions_case_idx ON suggestions (case_id, created_at);

CREATE TABLE decisions (
    id         bigserial PRIMARY KEY,
    case_id    text NOT NULL REFERENCES cases (id),
    actor      text NOT NULL,
    action     text NOT NULL CHECK (action IN ('approve', 'return', 'escalate')),
    message    text,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Effects of executed decisions (code only, after the human checkpoint).
CREATE TABLE premium_lines (
    id          bigserial PRIMARY KEY,
    timecard_id text NOT NULL REFERENCES timecards (id),
    case_id     text NOT NULL REFERENCES cases (id),
    rule_id     text NOT NULL,
    day_date    date,
    description text NOT NULL,
    amount_usd  numeric(10, 2) NOT NULL,
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE return_messages (
    id             bigserial PRIMARY KEY,
    case_id        text NOT NULL REFERENCES cases (id),
    recipient_role text NOT NULL,
    body           text NOT NULL,
    sent_by        text NOT NULL,
    sent_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE escalations (
    id         bigserial PRIMARY KEY,
    case_id    text NOT NULL REFERENCES cases (id),
    note       text NOT NULL,
    raised_by  text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Append-only audit log: a trigger rejects UPDATE and DELETE at the database level.
CREATE TABLE audit_log (
    id          bigserial PRIMARY KEY,
    case_id     text NOT NULL,
    entry_kind  text NOT NULL CHECK (entry_kind IN (
                    'suggestion', 'validation', 'review', 'decision', 'execution')),
    actor       text NOT NULL,
    payload     jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_case_idx ON audit_log (case_id, id);

CREATE FUNCTION audit_log_is_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only (% not allowed)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_update_or_delete
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_is_append_only();

-- TRUNCATE does not fire row triggers; a statement trigger closes that path too. The demo reset
-- (`ptc seed --reset`) disables this trigger explicitly inside its own transaction.
CREATE TRIGGER audit_log_no_truncate
    BEFORE TRUNCATE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION audit_log_is_append_only();
