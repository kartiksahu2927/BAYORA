"""Small shared data types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Actor:
    actor_id: str
    tenant_id: str
    role: str


@dataclass(frozen=True)
class Flow:
    source: str
    destination: str
    resource: str
    tenant_id: str
    session_id: str
    target_tenant_id: str | None = None
    target_session_id: str | None = None


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    control: str

    def as_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "control": self.control,
        }
