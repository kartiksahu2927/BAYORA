"""Runtime configuration for Bayora."""

from __future__ import annotations

import os
import math
import json
from dataclasses import dataclass, field
from pathlib import Path

from .providers import ProviderConfig


DEFAULT_INTELLIGENCE_SOURCES = {
    "nvd": ("https://nvd.nist.gov/vuln/search",),
    "owasp": ("https://owasp.org/www-project-top-ten/",),
    "atlas": ("https://atlas.mitre.org/",),
    "huggingface": ("https://huggingface.co/docs",),
}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str = "127.0.0.1"
    port: int = 8080
    max_prompt_chars: int = 12_000
    max_request_bytes: int = 256 * 1024
    # The worker deadline is intentionally a little longer than the provider
    # request timeout so a provider timeout can be classified and persisted by
    # Bayora instead of being cut off as an unexplained worker failure.
    worker_timeout_seconds: float = 15.0
    llm_provider: str = "fixture"
    llm_model: str = ""
    llm_base_url: str | None = None
    llm_api_key: str | None = field(default=None, repr=False)
    llm_timeout_seconds: float = 10.0
    # Passwords are used only to initialize users that do not have a password
    # hash yet. They are never persisted in Settings or the database.
    bootstrap_passwords: dict[str, str] = field(default_factory=dict, repr=False)
    session_ttl_seconds: float = 8 * 60 * 60
    session_cookie_name: str = "bayora_session"
    session_cookie_secure: bool = False
    tinyfish_api_key: str | None = field(default=None, repr=False)
    tinyfish_base_url: str = "https://agent.tinyfish.ai/v1"
    tinyfish_timeout_seconds: float = 30.0
    tinyfish_poll_interval_seconds: float = 2.0
    tinyfish_max_duration_seconds: float = 120.0
    intelligence_max_results: int = 20
    intelligence_allowed_sources: dict[str, tuple[str, ...]] = field(default_factory=lambda: DEFAULT_INTELLIGENCE_SOURCES.copy())

    def __post_init__(self) -> None:
        if not isinstance(self.port, int) or isinstance(self.port, bool) or not 0 <= self.port <= 65535:
            raise ValueError("port must be an integer between 0 and 65535")
        for name in (
            "worker_timeout_seconds",
            "llm_timeout_seconds",
            "session_ttl_seconds",
            "tinyfish_timeout_seconds",
            "tinyfish_poll_interval_seconds",
            "tinyfish_max_duration_seconds",
        ):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a finite positive number")
        for name in ("max_prompt_chars", "max_request_bytes", "intelligence_max_results"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if not isinstance(self.tinyfish_base_url, str) or not self.tinyfish_base_url.startswith("https://"):
            raise ValueError("tinyfish_base_url must use HTTPS")

    @property
    def database_path(self) -> Path:
        return self.data_dir / "database" / "bayora.sqlite3"

    @property
    def audit_key_path(self) -> Path:
        return self.data_dir / "audit" / "audit.key"

    @property
    def workspace_dir(self) -> Path:
        return self.data_dir / "application" / "workspaces"

    @property
    def provider_config(self) -> ProviderConfig:
        return ProviderConfig(
            provider=self.llm_provider,
            base_url=self.llm_base_url,
            model=self.llm_model,
            api_key=self.llm_api_key,
            timeout_seconds=self.llm_timeout_seconds,
        )

    @property
    def auth_session_ttl_seconds(self) -> float:
        """Compatibility alias for callers that use the auth-prefixed name."""
        return self.session_ttl_seconds

    @property
    def auth_cookie_name(self) -> str:
        return self.session_cookie_name

    @property
    def auth_cookie_secure(self) -> bool:
        return self.session_cookie_secure

    @classmethod
    def from_env(cls, data_dir: str | Path | None = None) -> "Settings":
        root = Path(data_dir or os.environ.get("BAYORA_DATA_DIR", ".bayora"))

        def env(primary: str, legacy: str | None = None, default: str | None = None) -> str | None:
            return os.environ.get(primary, os.environ.get(legacy, default) if legacy else default)

        def integer(name: str, value: str | None) -> int:
            try:
                return int(value or "")
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be an integer") from exc

        def finite_float(name: str, value: str | None) -> float:
            try:
                parsed = float(value or "")
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a finite positive number") from exc
            if not math.isfinite(parsed) or parsed <= 0:
                raise ValueError(f"{name} must be a finite positive number")
            return parsed

        bootstrap_passwords: dict[str, str] = {}
        for user_id, variables in {
            "red-analyst": ("BAYORA_BOOTSTRAP_RED_PASSWORD", "BAYORA_RED_PASSWORD"),
            "blue-engineer": ("BAYORA_BOOTSTRAP_BLUE_PASSWORD", "BAYORA_BLUE_PASSWORD"),
            "security-admin": ("BAYORA_BOOTSTRAP_ADMIN_PASSWORD", "BAYORA_ADMIN_PASSWORD"),
            "audit-reviewer": ("BAYORA_BOOTSTRAP_AUDITOR_PASSWORD", "BAYORA_AUDITOR_PASSWORD"),
        }.items():
            for variable in variables:
                if password := os.environ.get(variable):
                    bootstrap_passwords[user_id] = password
                    break

        return cls(
            data_dir=root,
            host=os.environ.get("BAYORA_HOST", "127.0.0.1"),
            port=integer("BAYORA_PORT", os.environ.get("BAYORA_PORT", "8080")),
            llm_provider=env("LLM_PROVIDER", "BAYORA_LLM_PROVIDER", "fixture") or "fixture",
            llm_model=env("LLM_MODEL", "BAYORA_LLM_MODEL", "") or "",
            llm_base_url=env("LLM_BASE_URL", "BAYORA_LLM_ENDPOINT"),
            llm_api_key=env("LLM_API_KEY", "BAYORA_LLM_API_KEY"),
            llm_timeout_seconds=finite_float("LLM_TIMEOUT_SECONDS", env("LLM_TIMEOUT_SECONDS", "BAYORA_LLM_TIMEOUT_SECONDS", "10")),
            worker_timeout_seconds=finite_float("BAYORA_WORKER_TIMEOUT_SECONDS", os.environ.get("BAYORA_WORKER_TIMEOUT_SECONDS", "15")),
            bootstrap_passwords=bootstrap_passwords,
            session_ttl_seconds=finite_float(
                "BAYORA_SESSION_TTL_SECONDS",
                env("BAYORA_SESSION_TTL_SECONDS", "BAYORA_AUTH_SESSION_TTL_SECONDS", str(8 * 60 * 60))
                or str(8 * 60 * 60)
            ),
            session_cookie_name=os.environ.get("BAYORA_SESSION_COOKIE_NAME", "bayora_session"),
            session_cookie_secure=os.environ.get("BAYORA_SESSION_COOKIE_SECURE", "0").lower()
            in {"1", "true", "yes", "on"},
            tinyfish_api_key=env("TINYFISH_API_KEY"),
            tinyfish_base_url=env("TINYFISH_BASE_URL", default="https://agent.tinyfish.ai/v1") or "https://agent.tinyfish.ai/v1",
            tinyfish_timeout_seconds=finite_float("TINYFISH_TIMEOUT_SECONDS", os.environ.get("TINYFISH_TIMEOUT_SECONDS", "30")),
            tinyfish_poll_interval_seconds=finite_float("TINYFISH_POLL_INTERVAL_SECONDS", os.environ.get("TINYFISH_POLL_INTERVAL_SECONDS", "2")),
            tinyfish_max_duration_seconds=finite_float("TINYFISH_MAX_DURATION_SECONDS", os.environ.get("TINYFISH_MAX_DURATION_SECONDS", "120")),
            intelligence_max_results=integer("BAYORA_INTELLIGENCE_MAX_RESULTS", os.environ.get("BAYORA_INTELLIGENCE_MAX_RESULTS", "20")),
            intelligence_allowed_sources=cls._allowed_sources_from_env(),
        )

    @classmethod
    def _allowed_sources_from_env(cls) -> dict[str, tuple[str, ...]]:
        raw = os.environ.get("BAYORA_INTELLIGENCE_ALLOWED_SOURCES", "")
        if not raw:
            return {key: tuple(values) for key, values in DEFAULT_INTELLIGENCE_SOURCES.items()}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("BAYORA_INTELLIGENCE_ALLOWED_SOURCES must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("BAYORA_INTELLIGENCE_ALLOWED_SOURCES must be a JSON object")
        result: dict[str, tuple[str, ...]] = {}
        for category, urls in parsed.items():
            if not isinstance(category, str) or not category or not isinstance(urls, list) or not urls or not all(isinstance(url, str) for url in urls):
                raise ValueError("BAYORA_INTELLIGENCE_ALLOWED_SOURCES must map categories to URL arrays")
            result[category] = tuple(urls)
        return result

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.audit_key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.workspace_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.data_dir.chmod(0o700)
        self.database_path.parent.chmod(0o700)
        self.audit_key_path.parent.chmod(0o700)
        self.workspace_dir.chmod(0o700)
