"""P01-owned SQLite DDL (single source of truth).

All tables enable foreign keys. Times are UTC RFC3339 with Z. Sequences /
head_version are SQLite integers stored as decimal strings on the contract
surface. PK/FK use named constraints; JSON columns store canonical UTF-8.
"""
from __future__ import annotations

# project.sqlite -----------------------------------------------------------
PROJECT_DDL = """
CREATE TABLE IF NOT EXISTS schema_migration (
    migration_id    TEXT PRIMARY KEY,
    checksum        TEXT NOT NULL,
    applied_at      TEXT NOT NULL,
    schema_version  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entity (
    project_id      TEXT NOT NULL,
    type            TEXT NOT NULL,
    object_id       TEXT NOT NULL,
    created_seq     INTEGER NOT NULL,
    PRIMARY KEY (project_id, type, object_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS revision (
    project_id      TEXT NOT NULL,
    type            TEXT NOT NULL,
    object_id       TEXT NOT NULL,
    revision_id     TEXT NOT NULL,
    ordinal         INTEGER NOT NULL,
    parent_ref      TEXT,
    payload_schema  TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    digest          TEXT NOT NULL,
    commit_seq      INTEGER NOT NULL,
    command_id      TEXT NOT NULL,
    principal_id    TEXT NOT NULL,
    PRIMARY KEY (project_id, type, object_id, revision_id),
    UNIQUE (project_id, type, object_id, ordinal),
    CONSTRAINT fk_revision_entity FOREIGN KEY (project_id, type, object_id)
        REFERENCES entity (project_id, type, object_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS entity_head (
    project_id      TEXT NOT NULL,
    type            TEXT NOT NULL,
    object_id       TEXT NOT NULL,
    pointer_name    TEXT NOT NULL,
    revision_id     TEXT NOT NULL,
    head_version    INTEGER NOT NULL,
    updated_seq     INTEGER NOT NULL,
    PRIMARY KEY (project_id, type, object_id, pointer_name),
    CONSTRAINT fk_head_revision FOREIGN KEY (project_id, type, object_id, revision_id)
        REFERENCES revision (project_id, type, object_id, revision_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS head_history (
    project_id      TEXT NOT NULL,
    type            TEXT NOT NULL,
    object_id       TEXT NOT NULL,
    pointer_name    TEXT NOT NULL,
    commit_seq      INTEGER NOT NULL,
    revision_id     TEXT NOT NULL,
    head_version    INTEGER NOT NULL,
    PRIMARY KEY (project_id, type, object_id, pointer_name, commit_seq)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS commit_log (
    commit_seq      INTEGER PRIMARY KEY,
    command_id      TEXT UNIQUE NOT NULL,
    principal_id    TEXT NOT NULL,
    committed_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS command_receipt (
    principal_id    TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    command_kind    TEXT NOT NULL,
    input_hash      TEXT NOT NULL,
    command_id      TEXT UNIQUE NOT NULL,
    status          TEXT NOT NULL,
    receipt_json    TEXT NOT NULL,
    commit_seq      INTEGER,
    PRIMARY KEY (principal_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS audit_event (
    commit_seq      INTEGER NOT NULL,
    event_index     INTEGER NOT NULL,
    event_type      TEXT NOT NULL,
    event_schema    TEXT NOT NULL,
    object_refs     TEXT,
    command_id      TEXT NOT NULL,
    causal_refs     TEXT,
    source_key      TEXT,
    payload         TEXT,
    PRIMARY KEY (commit_seq, event_index)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS outbox (
    outbox_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    consumer        TEXT NOT NULL,
    effect_id       TEXT NOT NULL,
    effect_kind     TEXT NOT NULL,
    payload_ref     TEXT,
    state           TEXT NOT NULL,
    lease_token     TEXT,
    lease_until     TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_retry      TEXT,
    error           TEXT,
    UNIQUE (consumer, effect_id, effect_kind)
);

CREATE TABLE IF NOT EXISTS source_event (
    host_id             TEXT NOT NULL,
    origin_session_id   TEXT NOT NULL,
    log_generation      TEXT NOT NULL,
    source_seq          TEXT NOT NULL,
    payload_hash        TEXT NOT NULL,
    schema_version      TEXT NOT NULL,
    body                TEXT,
    commit_seq          INTEGER NOT NULL,
    completeness        TEXT NOT NULL,
    PRIMARY KEY (host_id, origin_session_id, log_generation, source_seq)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS source_cursor (
    source_stream_key   TEXT PRIMARY KEY,
    contiguous_seq      TEXT NOT NULL,
    seen_high_water     TEXT NOT NULL,
    gaps_json           TEXT NOT NULL,
    status              TEXT NOT NULL,
    updated_seq         INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS project_meta (
    project_id      TEXT PRIMARY KEY,
    store_id        TEXT NOT NULL,
    schema_version  TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_revision_commit_seq ON revision (commit_seq);
CREATE INDEX IF NOT EXISTS idx_audit_command_id ON audit_event (command_id);
CREATE INDEX IF NOT EXISTS idx_outbox_state ON outbox (state, next_retry);
"""

# migration 0002: flow/domain index & archive tables (ChangeRequest from P02/P05,
# approved by P00/P13; DDL owned by P01). These are typed index tables alongside
# the revision ledger; payload truth stays in `revision`.
FLOW_DOMAIN_DDL = """
CREATE TABLE IF NOT EXISTS task_index (
    task_id         TEXT NOT NULL,
    current_ref     TEXT NOT NULL,
    phase           TEXT NOT NULL,
    terminal_outcome TEXT,
    head_version    INTEGER NOT NULL,
    project_id      TEXT NOT NULL,
    PRIMARY KEY (project_id, task_id)
);

CREATE TABLE IF NOT EXISTS blocker (
    blocker_id      TEXT NOT NULL,
    task_id         TEXT NOT NULL,
    code            TEXT NOT NULL,
    evidence_ref    TEXT,
    resolution_ref  TEXT,
    project_id      TEXT NOT NULL,
    PRIMARY KEY (project_id, blocker_id)
);

CREATE TABLE IF NOT EXISTS execution_packet (
    packet_id       TEXT NOT NULL,
    revision_ref    TEXT NOT NULL,
    task_ref        TEXT NOT NULL,
    baseline_digest TEXT NOT NULL,
    status          TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    PRIMARY KEY (project_id, packet_id)
);

CREATE TABLE IF NOT EXISTS requirement_acceptance (
    requirement_ref     TEXT NOT NULL,
    item_id             TEXT NOT NULL,
    acceptance_item_ref TEXT NOT NULL,
    recipe_ref          TEXT NOT NULL,
    required            INTEGER NOT NULL,
    project_id          TEXT NOT NULL,
    PRIMARY KEY (project_id, requirement_ref, item_id)
);

CREATE TABLE IF NOT EXISTS design_option (
    project_id      TEXT NOT NULL,
    design_ref      TEXT NOT NULL,
    option_id       TEXT NOT NULL,
    decision_ref    TEXT,
    PRIMARY KEY (project_id, design_ref, option_id)
);

CREATE TABLE IF NOT EXISTS attempt_index (
    attempt_id          TEXT NOT NULL,
    task_id             TEXT NOT NULL,
    packet_ref          TEXT NOT NULL,
    status              TEXT NOT NULL,
    execution_root_ref  TEXT,
    execution_handle_id TEXT,
    mode                TEXT NOT NULL,
    project_id          TEXT NOT NULL,
    PRIMARY KEY (project_id, attempt_id)
);

CREATE TABLE IF NOT EXISTS verification_index (
    report_ref          TEXT NOT NULL,
    attempt_id          TEXT NOT NULL,
    candidate_digest    TEXT NOT NULL,
    result              TEXT NOT NULL,
    project_id          TEXT NOT NULL,
    PRIMARY KEY (project_id, report_ref)
);

CREATE TABLE IF NOT EXISTS delivery_snapshot (
    snapshot_id     TEXT NOT NULL,
    body_schema     TEXT NOT NULL,
    body_json       TEXT NOT NULL,
    body_digest     TEXT NOT NULL,
    commit_seq      INTEGER NOT NULL,
    project_id      TEXT NOT NULL,
    PRIMARY KEY (project_id, snapshot_id)
);

CREATE TABLE IF NOT EXISTS approval_index (
    approval_id     TEXT NOT NULL,
    snapshot_id     TEXT NOT NULL,
    digest          TEXT NOT NULL,
    status          TEXT NOT NULL,
    expires_at      TEXT,
    head_version    INTEGER NOT NULL,
    project_id      TEXT NOT NULL,
    PRIMARY KEY (project_id, approval_id)
);

CREATE TABLE IF NOT EXISTS delivery_operation (
    operation_id    TEXT NOT NULL,
    approval_id     TEXT NOT NULL,
    snapshot_id     TEXT NOT NULL,
    digest          TEXT NOT NULL,
    state           TEXT NOT NULL,
    epoch           INTEGER NOT NULL,
    lease           TEXT,
    provider        TEXT,
    target_ref      TEXT,
    receipt_ref     TEXT,
    project_id      TEXT NOT NULL,
    PRIMARY KEY (project_id, operation_id)
);

CREATE TABLE IF NOT EXISTS artifact (
    artifact_id     TEXT NOT NULL,
    digest          TEXT NOT NULL,
    size            INTEGER NOT NULL,
    mime            TEXT NOT NULL,
    source_ref      TEXT,
    retention       TEXT,
    state           TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    PRIMARY KEY (project_id, artifact_id)
);

CREATE TABLE IF NOT EXISTS location (
    artifact_id     TEXT NOT NULL,
    sink            TEXT NOT NULL,
    locator         TEXT NOT NULL,
    state           TEXT NOT NULL,
    verified_at     TEXT,
    project_id      TEXT NOT NULL,
    PRIMARY KEY (project_id, artifact_id, sink)
);

CREATE TABLE IF NOT EXISTS archive_manifest (
    manifest_id     TEXT NOT NULL,
    body_schema     TEXT NOT NULL,
    body_json       TEXT NOT NULL,
    digest          TEXT NOT NULL,
    commit_seq      INTEGER NOT NULL,
    project_id      TEXT NOT NULL,
    PRIMARY KEY (project_id, manifest_id)
);

CREATE TABLE IF NOT EXISTS sink_receipt (
    manifest_id     TEXT NOT NULL,
    sink            TEXT NOT NULL,
    state           TEXT NOT NULL,
    digest          TEXT NOT NULL,
    lease           TEXT,
    error           TEXT,
    project_id      TEXT NOT NULL,
    PRIMARY KEY (project_id, manifest_id, sink)
);
"""

# migration 0003: legacy import + knowledge domain tables (ChangeRequest CR-002,
# proposals from P07/P08; DDL owned by P01).
LEGACY_KNOWLEDGE_DDL = """
CREATE TABLE IF NOT EXISTS imported_fact (
    source_store_id TEXT NOT NULL,
    legacy_type     TEXT NOT NULL,
    legacy_id       TEXT NOT NULL,
    source_digest   TEXT NOT NULL,
    batch_id        TEXT NOT NULL,
    new_ref         TEXT NOT NULL,
    original_json   TEXT NOT NULL,
    classification  TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    PRIMARY KEY (project_id, source_store_id, legacy_type, legacy_id)
);

CREATE TABLE IF NOT EXISTS legacy_source_snapshot (
    snapshot_id     TEXT PRIMARY KEY,
    source_store_id TEXT NOT NULL,
    manifest_digest TEXT NOT NULL,
    body_json       TEXT NOT NULL,
    commit_seq      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS legacy_import_batch (
    batch_id            TEXT NOT NULL,
    source_snapshot_ref TEXT NOT NULL,
    import_plan_ref     TEXT,
    state               TEXT NOT NULL,
    commit_seq          INTEGER NOT NULL,
    project_id          TEXT NOT NULL,
    PRIMARY KEY (project_id, batch_id)
);

CREATE TABLE IF NOT EXISTS use_event (
    source_use_key  TEXT NOT NULL,
    knowledge_ref   TEXT NOT NULL,
    use_kind        TEXT NOT NULL,
    context_ref     TEXT,
    commit_seq      INTEGER NOT NULL,
    project_id      TEXT NOT NULL,
    PRIMARY KEY (project_id, source_use_key)
);

CREATE TABLE IF NOT EXISTS outcome (
    source_outcome_key  TEXT NOT NULL,
    use_ref             TEXT,
    verified_result_ref TEXT,
    commit_seq          INTEGER NOT NULL,
    project_id          TEXT NOT NULL,
    PRIMARY KEY (project_id, source_outcome_key)
);

CREATE TABLE IF NOT EXISTS promotion_task (
    promotion_task_id   TEXT NOT NULL,
    knowledge_ref       TEXT NOT NULL,
    reviewed_scope      TEXT,
    human_decision_ref  TEXT NOT NULL,
    state               TEXT NOT NULL,
    project_id          TEXT NOT NULL,
    PRIMARY KEY (project_id, promotion_task_id)
);
"""

# shared.sqlite (identity domain) ------------------------------------------
IDENTITY_DDL = """
CREATE TABLE IF NOT EXISTS identity_project (
    project_id      TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    state           TEXT NOT NULL,
    store_id        TEXT NOT NULL,
    canonical_root  TEXT NOT NULL,
    schema_stamp    TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS identity_binding (
    host_id         TEXT NOT NULL,
    binding_kind    TEXT NOT NULL,
    canonical_key   TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    binding_version TEXT NOT NULL,
    metadata        TEXT,
    PRIMARY KEY (host_id, binding_kind, canonical_key),
    CONSTRAINT fk_binding_project FOREIGN KEY (project_id)
        REFERENCES identity_project (project_id)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS provision_receipt (
    provision_request_id TEXT PRIMARY KEY,
    principal_id    TEXT NOT NULL,
    project_id      TEXT NOT NULL,
    state           TEXT NOT NULL,
    store_id        TEXT,
    manifest_ref    TEXT,
    commit_seq      INTEGER NOT NULL,
    receipt_json    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS identity_meta (
    store_id        TEXT PRIMARY KEY,
    commit_seq      INTEGER NOT NULL
);
"""

# migration 0002 (identity): shared knowledge domain (P08 CR-2). Cross-store
# replication is performed by the promote service and verified by digest; the
# table holds the shared, digest-verified knowledge revision.
SHARED_KNOWLEDGE_DDL = """
CREATE TABLE IF NOT EXISTS shared_knowledge (
    store_id        TEXT NOT NULL,
    object_id       TEXT NOT NULL,
    revision_id     TEXT NOT NULL,
    digest          TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    promoted_at     TEXT NOT NULL,
    PRIMARY KEY (store_id, object_id, revision_id)
);
"""
