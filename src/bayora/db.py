"""SQLite persistence with tenant-scoped query helpers."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator
from typing import Any


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('red', 'blue', 'admin', 'auditor')),
                    password_hash TEXT
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    revoked_at REAL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS evaluations (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    session_id TEXT NOT NULL UNIQUE,
                    workspace TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    result_json TEXT,
                    finished_at TEXT,
                    model_provider TEXT,
                    model_name TEXT,
                     model_invocation_id TEXT,
                     response_text TEXT,
                     response_sha256 TEXT,
                     latency_ms REAL,
                     usage_json TEXT,
                     evidence_type TEXT,
                     error_code TEXT,
                    error_message TEXT,
                    policy_json TEXT,
                    finding_json TEXT
                );
                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evaluation_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    control TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (evaluation_id) REFERENCES evaluations(id)
                );
                CREATE TABLE IF NOT EXISTS evaluation_blue_access (
                    evaluation_id TEXT NOT NULL,
                    blue_actor_id TEXT NOT NULL,
                    granted_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (evaluation_id, blue_actor_id),
                    FOREIGN KEY (evaluation_id) REFERENCES evaluations(id),
                    FOREIGN KEY (blue_actor_id) REFERENCES users(id),
                    FOREIGN KEY (granted_by) REFERENCES users(id)
                );
                CREATE INDEX IF NOT EXISTS idx_evaluation_blue_access_actor
                    ON evaluation_blue_access (blue_actor_id, evaluation_id);
                CREATE TABLE IF NOT EXISTS evaluation_evidence (
                    evaluation_id TEXT PRIMARY KEY,
                    original_prompt TEXT NOT NULL,
                    prompt_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (evaluation_id) REFERENCES evaluations(id)
                );
                CREATE TABLE IF NOT EXISTS blue_analyses (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    source_evaluation_id TEXT NOT NULL,
                    session_id TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL CHECK (state IN ('created', 'running', 'completed', 'failed')),
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    finished_at TEXT,
                    model_provider TEXT,
                    model_name TEXT,
                    model_invocation_id TEXT,
                    model_evidence_type TEXT,
                    source_model_json TEXT NOT NULL,
                    source_state TEXT NOT NULL,
                    source_fixture INTEGER NOT NULL CHECK (source_fixture IN (0, 1)),
                    source_evidence_hashes_json TEXT NOT NULL,
                    instructions_sha256 TEXT NOT NULL,
                    prompt_sha256 TEXT NOT NULL,
                    policy_json TEXT,
                    response_text TEXT,
                    response_sha256 TEXT,
                    latency_ms REAL,
                    usage_json TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    evidence_type TEXT NOT NULL DEFAULT 'advisory_unverified' CHECK (evidence_type = 'advisory_unverified'),
                    remediation_status TEXT NOT NULL DEFAULT 'recommended' CHECK (remediation_status = 'recommended'),
                    implemented INTEGER NOT NULL DEFAULT 0 CHECK (implemented = 0),
                    retested INTEGER NOT NULL DEFAULT 0 CHECK (retested = 0),
                    verified INTEGER NOT NULL DEFAULT 0 CHECK (verified = 0),
                    FOREIGN KEY (source_evaluation_id) REFERENCES evaluations(id),
                    FOREIGN KEY (actor_id) REFERENCES users(id)
                );
                CREATE INDEX IF NOT EXISTS idx_blue_analyses_source_created
                    ON blue_analyses (source_evaluation_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS blue_analysis_instructions (
                    analysis_id TEXT PRIMARY KEY,
                    instructions TEXT NOT NULL,
                    FOREIGN KEY (analysis_id) REFERENCES blue_analyses(id)
                );
                CREATE TABLE IF NOT EXISTS evaluation_remediations (
                    id TEXT PRIMARY KEY,
                    source_evaluation_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    session_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('recommended', 'implemented')),
                    notes TEXT NOT NULL,
                    evidence TEXT,
                    notes_sha256 TEXT NOT NULL,
                    evidence_sha256 TEXT,
                    evidence_type TEXT NOT NULL DEFAULT 'user_reported' CHECK (evidence_type = 'user_reported'),
                    implemented_reported INTEGER NOT NULL CHECK (
                        (status = 'implemented' AND implemented_reported = 1) OR
                        (status = 'recommended' AND implemented_reported = 0)
                    ),
                    retested INTEGER NOT NULL DEFAULT 0 CHECK (retested = 0),
                    verified INTEGER NOT NULL DEFAULT 0 CHECK (verified = 0),
                    FOREIGN KEY (source_evaluation_id) REFERENCES evaluations(id),
                    FOREIGN KEY (actor_id) REFERENCES users(id)
                );
                CREATE INDEX IF NOT EXISTS idx_evaluation_remediations_source_created
                    ON evaluation_remediations (source_evaluation_id, created_at DESC);
                CREATE TABLE IF NOT EXISTS intelligence_tasks (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    evaluation_session_id TEXT,
                    state TEXT NOT NULL CHECK (state IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')),
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    topic TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    source_categories_json TEXT NOT NULL,
                    source_urls_json TEXT NOT NULL,
                    max_results INTEGER NOT NULL,
                    correlation_id TEXT,
                    request_key TEXT NOT NULL UNIQUE,
                    provider TEXT NOT NULL,
                    provider_run_ids_json TEXT NOT NULL,
                    result_count INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT,
                    error_message TEXT,
                    policy_json TEXT,
                    FOREIGN KEY (evaluation_session_id) REFERENCES evaluations(session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_intelligence_tasks_tenant_created
                    ON intelligence_tasks (tenant_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_intelligence_tasks_state
                    ON intelligence_tasks (state);
                CREATE TABLE IF NOT EXISTS intelligence_evidence (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    evaluation_session_id TEXT,
                    provider_finding_id TEXT,
                    source_url TEXT NOT NULL,
                    title TEXT,
                    publication_date TEXT,
                    collected_at TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    category TEXT,
                    summary TEXT NOT NULL,
                    technical_details TEXT,
                    mitigation TEXT,
                    provenance_json TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES intelligence_tasks(id)
                );
                CREATE INDEX IF NOT EXISTS idx_intelligence_evidence_task
                    ON intelligence_evidence (task_id);
                CREATE INDEX IF NOT EXISTS idx_intelligence_evidence_tenant
                    ON intelligence_evidence (tenant_id, collected_at DESC);
                """
            )
            existing_user_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            if "password_hash" not in existing_user_columns:
                # Existing installations have users but no credential column.
                # A nullable column lets the service add configured bootstrap
                # hashes without inventing or replacing a password.
                connection.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            existing_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(evaluations)").fetchall()
            }
            migrations = {
                "finished_at": "TEXT",
                "model_provider": "TEXT",
                "model_name": "TEXT",
                "model_invocation_id": "TEXT",
                 "response_text": "TEXT",
                 "response_sha256": "TEXT",
                 "latency_ms": "REAL",
                 "usage_json": "TEXT",
                 "evidence_type": "TEXT",
                 "error_code": "TEXT",
                "error_message": "TEXT",
                "policy_json": "TEXT",
                "finding_json": "TEXT",
            }
            for column, definition in migrations.items():
                if column not in existing_columns:
                    connection.execute(f"ALTER TABLE evaluations ADD COLUMN {column} {definition}")
            connection.executemany(
                "INSERT OR IGNORE INTO users (id, tenant_id, role, password_hash) VALUES (?, ?, ?, ?)",
                [
                    ("red-analyst", "tenant-red-lab", "red", None),
                    ("blue-engineer", "tenant-blue-lab", "blue", None),
                    ("security-admin", "tenant-platform", "admin", None),
                    ("audit-reviewer", "tenant-platform", "auditor", None),
                ],
            )

    def user(self, actor_id: str) -> dict[str, str] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT id, tenant_id, role FROM users WHERE id = ?", (actor_id,)).fetchone()
            return dict(row) if row else None

    def blue_recipients(self) -> list[dict[str, str]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT id AS actor_id FROM users WHERE role = 'blue' ORDER BY id"
            ).fetchall()]

    def grant_blue_access(self, evaluation_id: str, blue_actor_id: str, granted_by: str, created_at: str) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO evaluation_blue_access
                (evaluation_id, blue_actor_id, granted_by, created_at) VALUES (?, ?, ?, ?)
                """,
                (evaluation_id, blue_actor_id, granted_by, created_at),
            )
            row = connection.execute(
                "SELECT * FROM evaluation_blue_access WHERE evaluation_id = ? AND blue_actor_id = ?",
                (evaluation_id, blue_actor_id),
            ).fetchone()
            assert row is not None
            return dict(row)

    def has_blue_access(self, evaluation_id: str, blue_actor_id: str) -> bool:
        with self.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM evaluation_blue_access WHERE evaluation_id = ? AND blue_actor_id = ?",
                (evaluation_id, blue_actor_id),
            ).fetchone() is not None

    def user_credentials(self, actor_id: str) -> dict[str, str | None] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, tenant_id, role, password_hash FROM users WHERE id = ?",
                (actor_id,),
            ).fetchone()
            return dict(row) if row else None

    def set_password_hash_if_missing(self, actor_id: str, password_hash: str) -> bool:
        """Set a bootstrap hash without overwriting an existing credential."""
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE users
                SET password_hash = ?
                WHERE id = ? AND (password_hash IS NULL OR password_hash = '')
                """,
                (password_hash, actor_id),
            )
            return cursor.rowcount == 1

    def create_auth_session(self, token_hash: str, actor_id: str, created_at: float, expires_at: float) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (token_hash, actor_id, created_at, expires_at),
            )

    def auth_session_user(self, token_hash: str, now: float) -> dict[str, str] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT users.id, users.tenant_id, users.role
                FROM auth_sessions
                JOIN users ON users.id = auth_sessions.user_id
                WHERE auth_sessions.token_hash = ?
                  AND auth_sessions.revoked_at IS NULL
                  AND auth_sessions.expires_at > ?
                """,
                (token_hash, now),
            ).fetchone()
            return dict(row) if row else None

    def revoke_auth_session(self, token_hash: str, revoked_at: float) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE auth_sessions
                SET revoked_at = ?
                WHERE token_hash = ? AND revoked_at IS NULL
                """,
                (revoked_at, token_hash),
            )
            return cursor.rowcount == 1

    def insert_evaluation(self, record: dict[str, Any], *, original_prompt: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO evaluations
                (id, tenant_id, actor_id, state, created_at, completed_at, session_id, workspace, input_json, result_json,
                 finished_at, model_provider, model_name, model_invocation_id, response_text, response_sha256,
                 latency_ms, usage_json, evidence_type, error_code, error_message, policy_json, finding_json)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"],
                    record["tenant_id"],
                    record["actor_id"],
                    record["state"],
                    record["created_at"],
                    record.get("completed_at"),
                    record["session_id"],
                    record["workspace"],
                    json.dumps(record["input"], sort_keys=True),
                    json.dumps(record["result"], sort_keys=True) if record.get("result") is not None else None,
                    record.get("finished_at"),
                    record.get("model_provider"),
                    record.get("model_name"),
                    record.get("model_invocation_id"),
                    record.get("response"),
                    record.get("response_sha256"),
                    record.get("latency_ms"),
                    json.dumps(record["usage"], sort_keys=True) if record.get("usage") is not None else None,
                    record.get("evidence_type"),
                    record.get("error_code"),
                    record.get("error_message"),
                    json.dumps(record["policy"], sort_keys=True) if record.get("policy") is not None else None,
                    json.dumps(record["finding"], sort_keys=True) if record.get("finding") is not None else None,
                ),
            )
            if original_prompt is not None:
                connection.execute(
                    """
                    INSERT INTO evaluation_evidence (evaluation_id, original_prompt, prompt_sha256, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (record["id"], original_prompt, record["input"]["prompt_sha256"], record["created_at"]),
                )

    def evaluation_prompt(self, evaluation_id: str) -> str | None:
        """Protected source evidence: callers must authorize the assessment first."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT original_prompt FROM evaluation_evidence WHERE evaluation_id = ?", (evaluation_id,)
            ).fetchone()
            return row["original_prompt"] if row else None

    def update_evaluation(
        self,
        evaluation_id: str,
        state: str,
        result: dict[str, Any],
        finished_at: str | None,
        *,
        model_provider: str | None = None,
        model_name: str | None = None,
        model_invocation_id: str | None = None,
        response: str | None = None,
        response_sha256: str | None = None,
        latency_ms: float | None = None,
        usage: dict[str, int | float] | None = None,
        evidence_type: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        policy: dict[str, Any] | None = None,
        finding: dict[str, Any] | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE evaluations
                SET state = ?, result_json = ?,
                    completed_at = CASE WHEN ? = 'completed' THEN ? ELSE NULL END,
                    finished_at = ?,
                    model_provider = COALESCE(?, model_provider),
                    model_name = COALESCE(?, model_name),
                    model_invocation_id = COALESCE(?, model_invocation_id),
                     response_text = COALESCE(?, response_text),
                     response_sha256 = COALESCE(?, response_sha256),
                     latency_ms = COALESCE(?, latency_ms),
                     usage_json = COALESCE(?, usage_json),
                     evidence_type = COALESCE(?, evidence_type),
                     error_code = COALESCE(?, error_code),
                    error_message = COALESCE(?, error_message),
                    policy_json = COALESCE(?, policy_json),
                    finding_json = COALESCE(?, finding_json)
                WHERE id = ?
                """,
                (
                    state,
                    json.dumps(result, sort_keys=True),
                    state,
                    finished_at,
                    finished_at,
                    model_provider,
                    model_name,
                    model_invocation_id,
                    response,
                    response_sha256,
                    latency_ms,
                    json.dumps(usage, sort_keys=True) if usage is not None else None,
                    evidence_type,
                    error_code,
                    error_message,
                    json.dumps(policy, sort_keys=True) if policy is not None else None,
                    json.dumps(finding, sort_keys=True) if finding is not None else None,
                    evaluation_id,
                ),
            )

    def _evaluation(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        # The workspace is an internal filesystem location, not API data.
        item.pop("workspace", None)
        item["input"] = json.loads(item.pop("input_json"))
        # Legacy input metadata must not turn a list response into a prompt export.
        item["input"].pop("prompt", None)
        item["input"].pop("original_prompt", None)
        item["result"] = json.loads(item.pop("result_json")) if item.get("result_json") else None
        item.pop("result_json", None)
        item["response"] = item.pop("response_text", None)
        item["latency_ms"] = item.pop("latency_ms", None)
        item["usage"] = json.loads(item.pop("usage_json")) if item.get("usage_json") else {}
        evidence_type = item.pop("evidence_type", None)
        item["model"] = {
            "provider": item.pop("model_provider", None),
            "name": item.pop("model_name", None),
            "invocation_id": item.pop("model_invocation_id", None),
            "evidence_type": evidence_type,
        }
        error_code = item.pop("error_code", None)
        error_message = item.pop("error_message", None)
        item["error"] = {"code": error_code, "message": error_message} if error_code or error_message else None
        item["policy"] = json.loads(item.pop("policy_json")) if item.get("policy_json") else None
        item["finding"] = json.loads(item.pop("finding_json")) if item.get("finding_json") else None
        return item

    def evaluations(self, tenant_id: str | None = None, *, blue_actor_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM evaluations"
        args: tuple[str, ...] = ()
        if tenant_id and blue_actor_id:
            # Keep the normal tenant listing bounded, but never hide an
            # explicitly granted assessment behind that listing limit.
            query = """
                SELECT * FROM (
                    SELECT * FROM evaluations
                    WHERE tenant_id = ?
                    ORDER BY created_at DESC
                    LIMIT 100
                )
                UNION
                SELECT * FROM evaluations
                WHERE EXISTS (
                    SELECT 1
                    FROM evaluation_blue_access AS access
                    WHERE access.evaluation_id = evaluations.id
                      AND access.blue_actor_id = ?
                )
                ORDER BY created_at DESC
            """
            args = (tenant_id, blue_actor_id)
        elif tenant_id:
            query += " WHERE (tenant_id = ?"
            args = (tenant_id,)
            query += ")"
            query += " ORDER BY created_at DESC LIMIT 100"
        else:
            query += " ORDER BY created_at DESC LIMIT 100"
        with self.connect() as connection:
            return [self._evaluation(row) for row in connection.execute(query, args).fetchall()]

    def evaluation(self, evaluation_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM evaluations WHERE id = ?", (evaluation_id,)).fetchone()
            return self._evaluation(row) if row else None

    def evaluation_by_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM evaluations WHERE session_id = ?", (session_id,)).fetchone()
            return self._evaluation(row) if row else None

    def insert_finding(self, record: dict[str, str]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO findings (evaluation_id, tenant_id, control, severity, summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                tuple(record[key] for key in ("evaluation_id", "tenant_id", "control", "severity", "summary", "created_at")),
            )

    def evaluation_findings(self, evaluation_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM findings WHERE evaluation_id = ? ORDER BY id", (evaluation_id,)
            ).fetchall()]

    def insert_blue_analysis(self, record: dict[str, Any], instructions: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO blue_analyses
                (id, tenant_id, actor_id, source_evaluation_id, session_id, state, created_at,
                 model_provider, model_name, model_invocation_id, model_evidence_type,
                 source_model_json, source_state, source_fixture, source_evidence_hashes_json,
                 instructions_sha256, prompt_sha256)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"], record["tenant_id"], record["actor_id"], record["source_evaluation_id"],
                    record["session_id"], record["state"], record["created_at"], record["model"]["provider"],
                    record["model"]["name"], record["model"]["invocation_id"], record["model"]["evidence_type"],
                    json.dumps(record["source_model"], sort_keys=True), record["source_state"],
                    int(record["source_fixture"]), json.dumps(record["source_evidence_hashes"], sort_keys=True),
                    record["instructions_sha256"], record["prompt_sha256"],
                ),
            )
            connection.execute(
                "INSERT INTO blue_analysis_instructions (analysis_id, instructions) VALUES (?, ?)",
                (record["id"], instructions),
            )

    def update_blue_analysis(self, analysis_id: str, **fields: Any) -> None:
        allowed = {
            "state", "started_at", "completed_at", "finished_at", "model_provider", "model_name",
            "model_invocation_id", "model_evidence_type", "policy", "response", "response_sha256",
            "latency_ms", "usage", "error_code", "error_message",
        }
        if set(fields) - allowed:
            raise ValueError("unsupported defensive analysis fields")
        assignments: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            column = {"response": "response_text", "policy": "policy_json", "usage": "usage_json"}.get(key, key)
            assignments.append(f"{column} = ?")
            values.append(json.dumps(value, sort_keys=True) if key in {"policy", "usage"} else value)
        if not assignments:
            return
        with self.connect() as connection:
            connection.execute(f"UPDATE blue_analyses SET {', '.join(assignments)} WHERE id = ?", [*values, analysis_id])

    def _blue_analysis(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["model"] = {
            "provider": item.pop("model_provider"),
            "name": item.pop("model_name"),
            "invocation_id": item.pop("model_invocation_id"),
            "evidence_type": item.pop("model_evidence_type"),
        }
        item["source_model"] = json.loads(item.pop("source_model_json"))
        item["source_evidence_type"] = item["source_model"].get("evidence_type")
        item["source_fixture_label"] = "Test Fixture — Not Real Model Evidence" if item["source_fixture"] else None
        item["fixture_label"] = (
            "Test Fixture — Not Real Model Evidence"
            if item["model"]["provider"] == "fixture" or item["model"]["evidence_type"] == "test_fixture" else None
        )
        item["source_evidence_hashes"] = json.loads(item.pop("source_evidence_hashes_json"))
        item["policy"] = json.loads(item["policy_json"]) if item["policy_json"] else None
        item.pop("policy_json")
        item["usage"] = json.loads(item["usage_json"]) if item["usage_json"] else {}
        item.pop("usage_json")
        item["response"] = item.pop("response_text")
        error_code, error_message = item.pop("error_code"), item.pop("error_message")
        item["error"] = {"code": error_code, "message": error_message} if error_code or error_message else None
        for key in ("source_fixture", "implemented", "retested", "verified"):
            item[key] = bool(item[key])
        # This is a server-owned invariant, not a claim that can be supplied
        # by the model or by the Blue Team request.
        item["advisory_unverified"] = True
        return item

    def blue_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM blue_analyses WHERE id = ?", (analysis_id,)).fetchone()
            return self._blue_analysis(row) if row else None

    def blue_analyses(self, evaluation_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [self._blue_analysis(row) for row in connection.execute(
                "SELECT * FROM blue_analyses WHERE source_evaluation_id = ? ORDER BY created_at DESC, id",
                (evaluation_id,),
            ).fetchall()]

    def insert_remediation(self, record: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO evaluation_remediations
                (id, source_evaluation_id, tenant_id, actor_id, session_id, created_at, status,
                 notes, evidence, notes_sha256, evidence_sha256, implemented_reported)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"], record["source_evaluation_id"], record["tenant_id"], record["actor_id"],
                    record["session_id"], record["created_at"], record["status"], record["notes"],
                    record["evidence"], record["notes_sha256"], record["evidence_sha256"],
                    int(record["implemented_reported"]),
                ),
            )

    def remediations(self, evaluation_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            result = []
            for row in connection.execute(
                "SELECT * FROM evaluation_remediations WHERE source_evaluation_id = ? ORDER BY created_at DESC, id",
                (evaluation_id,),
            ).fetchall():
                item = dict(row)
                for key in ("implemented_reported", "retested", "verified"):
                    item[key] = bool(item[key])
                result.append(item)
            return result

    def insert_intelligence_task(self, record: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO intelligence_tasks
                (id, tenant_id, actor_id, evaluation_session_id, state, created_at,
                 started_at, completed_at, topic, objective, source_categories_json,
                 source_urls_json, max_results, correlation_id, request_key, provider,
                 provider_run_ids_json, result_count, error_code, error_message, policy_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["id"], record["tenant_id"], record["actor_id"], record.get("evaluation_session_id"),
                    record["state"], record["created_at"], record.get("started_at"), record.get("completed_at"),
                    record["topic"], record["objective"], json.dumps(record["source_categories"], sort_keys=True),
                    json.dumps(record["source_urls"], sort_keys=True), record["max_results"], record.get("correlation_id"),
                    record["request_key"], record["provider"], json.dumps(record.get("provider_run_ids", []), sort_keys=True),
                    record.get("result_count", 0), record.get("error_code"), record.get("error_message"),
                    json.dumps(record["policy"], sort_keys=True) if record.get("policy") is not None else None,
                ),
            )

    def update_intelligence_task(self, task_id: str, **fields: Any) -> None:
        allowed = {
            "state", "started_at", "completed_at", "provider_run_ids", "result_count",
            "error_code", "error_message", "policy",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError("unsupported intelligence task fields")
        assignments: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            column = f"{key}_json" if key in {"provider_run_ids", "policy"} else key
            assignments.append(f"{column} = ?")
            values.append(json.dumps(value, sort_keys=True) if key in {"provider_run_ids", "policy"} else value)
        if not assignments:
            return
        values.append(task_id)
        with self.connect() as connection:
            connection.execute(f"UPDATE intelligence_tasks SET {', '.join(assignments)} WHERE id = ?", values)

    def _intelligence_task(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["source_categories"] = json.loads(item.pop("source_categories_json"))
        item["source_urls"] = json.loads(item.pop("source_urls_json"))
        item["provider_run_ids"] = json.loads(item.pop("provider_run_ids_json"))
        item["policy"] = json.loads(item.pop("policy_json")) if item.get("policy_json") else None
        item.pop("policy_json", None)
        return item

    def intelligence_task(self, task_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM intelligence_tasks WHERE id = ?", (task_id,)).fetchone()
            return self._intelligence_task(row) if row else None

    def intelligence_task_by_key(self, tenant_id: str, request_key: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM intelligence_tasks WHERE tenant_id = ? AND request_key = ?",
                (tenant_id, request_key),
            ).fetchone()
            return self._intelligence_task(row) if row else None

    def intelligence_tasks(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM intelligence_tasks"
        args: tuple[str, ...] = ()
        if tenant_id:
            query += " WHERE tenant_id = ?"
            args = (tenant_id,)
        query += " ORDER BY created_at DESC LIMIT 100"
        with self.connect() as connection:
            return [self._intelligence_task(row) for row in connection.execute(query, args).fetchall()]

    def insert_intelligence_evidence(self, record: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO intelligence_evidence
                (id, task_id, tenant_id, evaluation_session_id, provider_finding_id,
                 source_url, title, publication_date, collected_at, topic, category,
                 summary, technical_details, mitigation, provenance_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["evidence_id"], record["task_id"], record["tenant_id"], record.get("evaluation_session_id"),
                    record.get("provider_finding_id"), record["source_url"], record.get("title"),
                    record.get("publication_date"), record["collected_at"], record["topic"], record.get("category"),
                    record["summary"], record.get("technical_details"), record.get("mitigation"),
                    json.dumps(record["provenance"], sort_keys=True),
                ),
            )

    def intelligence_evidence(self, task_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM intelligence_evidence WHERE task_id = ? ORDER BY collected_at, id",
                (task_id,),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["provenance"] = json.loads(item.pop("provenance_json"))
                result.append(item)
            return result

    def findings(self, tenant_id: str | None = None, *, blue_actor_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM findings"
        args: tuple[str, ...] = ()
        if tenant_id and blue_actor_id:
            # Findings follow the same visibility rule as evaluations. The
            # tenant list remains bounded while exact Blue grants are always
            # returned, even when the granted assessment is older.
            query = """
                SELECT * FROM (
                    SELECT * FROM findings
                    WHERE tenant_id = ?
                    ORDER BY created_at DESC
                    LIMIT 100
                )
                UNION
                SELECT * FROM findings
                WHERE EXISTS (
                    SELECT 1
                    FROM evaluation_blue_access AS access
                    WHERE access.evaluation_id = findings.evaluation_id
                      AND access.blue_actor_id = ?
                )
                ORDER BY created_at DESC
            """
            args = (tenant_id, blue_actor_id)
        elif tenant_id:
            query += " WHERE (tenant_id = ?"
            args = (tenant_id,)
            query += ")"
            query += " ORDER BY created_at DESC LIMIT 100"
        else:
            query += " ORDER BY created_at DESC LIMIT 100"
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(query, args).fetchall()]
