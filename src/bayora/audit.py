"""Tamper-evident audit records backed by a keyed hash chain."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .db import Database


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLog:
    def __init__(self, database: Database, key_path: Path):
        self.database = database
        self.key_path = key_path
        self.key = self._load_key()
        self._initialize()

    def _load_key(self) -> bytes:
        if self.key_path.exists():
            key = self.key_path.read_bytes()
        else:
            key = secrets.token_bytes(32)
            self.key_path.write_bytes(key)
        self.key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        if len(key) < 32:
            raise ValueError("audit key is too short")
        return key

    def _initialize(self) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    session_id TEXT,
                    payload_json TEXT NOT NULL,
                    prev_digest TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def _digest(self, record: dict[str, Any]) -> str:
        material = "|".join(
            str(record[key])
            for key in (
                "id",
                "event_type",
                "actor_id",
                "tenant_id",
                "session_id",
                "payload_json",
                "prev_digest",
                "created_at",
            )
        )
        return hmac.new(self.key, material.encode("utf-8"), hashlib.sha256).hexdigest()

    def append(
        self,
        event_type: str,
        actor_id: str,
        tenant_id: str,
        session_id: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        created_at = utc_now()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute("SELECT digest FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
            previous_digest = previous[0] if previous else ""
            cursor = connection.execute(
                """
                INSERT INTO audit_events
                (event_type, actor_id, tenant_id, session_id, payload_json, prev_digest, digest, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (event_type, actor_id, tenant_id, session_id, payload_json, previous_digest, "pending", created_at),
            )
            record = {
                "id": cursor.lastrowid,
                "event_type": event_type,
                "actor_id": actor_id,
                "tenant_id": tenant_id,
                "session_id": session_id,
                "payload_json": payload_json,
                "prev_digest": previous_digest,
                "created_at": created_at,
            }
            digest = self._digest(record)
            connection.execute("UPDATE audit_events SET digest = ? WHERE id = ?", (digest, cursor.lastrowid))
            record["digest"] = digest
        return record

    def records(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM audit_events ORDER BY id").fetchall()]

    def events_for_session(self, session_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id, event_type, created_at, digest FROM audit_events WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def verify_records(self, records: Iterable[dict[str, Any]]) -> tuple[bool, str]:
        previous = ""
        for record in records:
            if record.get("prev_digest") != previous:
                return False, f"previous digest mismatch at record {record.get('id')}"
            expected = self._digest(record)
            if not hmac.compare_digest(str(record.get("digest", "")), expected):
                return False, f"digest mismatch at record {record.get('id')}"
            previous = expected
        return True, "audit chain verified"

    def verify(self) -> tuple[bool, str]:
        return self.verify_records(self.records())
