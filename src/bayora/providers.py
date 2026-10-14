"""Provider-agnostic LLM contract and provider implementations.

The evaluation service only consumes ``LLMProvider``. Provider-specific
protocols, endpoints, credentials, and response parsing stay in this module.
"""

from __future__ import annotations

import hashlib
import json
import math
import socket
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest
from urllib.request import HTTPRedirectHandler, build_opener


MAX_RESPONSE_CHARS = 32_000


class _NoRedirectHandler(HTTPRedirectHandler):
    """Never forward provider credentials to a redirected origin."""

    def redirect_request(self, request: URLRequest, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


_URL_OPENER = build_opener(_NoRedirectHandler())


def _open_url(request: URLRequest, timeout: float):
    return _URL_OPENER.open(request, timeout=timeout)


@dataclass(frozen=True)
class LLMRequest:
    prompt: str
    session_id: str
    invocation_id: str


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    invocation_id: str
    latency_ms: float | None = None
    usage: dict[str, int | float] = field(default_factory=dict)
    evidence_type: str = "real_model"

    @property
    def response_sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "response": self.text,
            "provider": self.provider,
            "model": self.model,
            "invocation_id": self.invocation_id,
            "response_sha256": self.response_sha256,
            "response_length": len(self.text),
            "latency_ms": self.latency_ms,
            "usage": dict(self.usage),
            "evidence_type": self.evidence_type,
        }
        return result


@dataclass(frozen=True)
class ProviderHealth:
    status: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"status": self.status, "message": self.message}


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "fixture"
    base_url: str | None = None
    model: str = ""
    api_key: str | None = field(default=None, repr=False)
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool) or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("provider timeout must be a finite positive number")

    def as_worker_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "api_key": self.api_key,
            "timeout_seconds": self.timeout_seconds,
        }


class ProviderError(RuntimeError):
    """A provider failure that must become a failed evaluation, never success."""

    def __init__(self, message: str, code: str = "provider_failure"):
        super().__init__(message)
        self.code = code


class LLMProvider(ABC):
    """The only interface used by the evaluation engine."""

    @abstractmethod
    def health(self) -> ProviderHealth:
        raise NotImplementedError

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    def metadata(self) -> dict[str, Any]:
        raise NotImplementedError

    def supports_offline_validation(self) -> bool:
        """Whether validation may invoke this provider without external model access."""
        return False


class FixtureProvider(LLMProvider):
    """Deterministic, dependency-free pipeline fixture; not model evidence."""

    def health(self) -> ProviderHealth:
        return ProviderHealth("connected", "Test Fixture — Not Real Model Evidence")

    def metadata(self) -> dict[str, Any]:
        return {
            "provider": "fixture",
            "display_name": "Test Fixture — Not Real Model Evidence",
            "model": "bayora-deterministic-fixture",
            "external": False,
            "evidence_type": "test_fixture",
            "warning": "Test Fixture — Not Real Model Evidence",
        }

    def supports_offline_validation(self) -> bool:
        return True

    def generate(self, request: LLMRequest) -> LLMResponse:
        digest = hashlib.sha256(request.prompt.encode("utf-8")).hexdigest()
        text = (
            "Test Fixture — Not Real Model Evidence\n"
            "Deterministic pipeline output generated without an LLM runtime.\n"
            f"Session input SHA-256: {digest}"
        )
        return LLMResponse(
            text,
            "fixture",
            "bayora-deterministic-fixture",
            request.invocation_id,
            latency_ms=0.0,
            evidence_type="test_fixture",
        )


class OpenAICompatibleProvider(LLMProvider):
    """Provider for any OpenAI-compatible chat-completions HTTP endpoint."""

    def __init__(self, config: ProviderConfig):
        self.config = config

    def metadata(self) -> dict[str, Any]:
        return {
            "provider": "openai_compatible",
            "display_name": "OpenAI-Compatible",
            "model": self.config.model or "not configured",
            "external": True,
            "evidence_type": "real_model",
        }

    def _endpoint(self) -> str:
        if not self.config.base_url:
            raise ProviderError("LLM_BASE_URL is not configured", "llm_not_configured")
        base = self.config.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/models"):
            return f"{base.removesuffix('/models')}/chat/completions"
        return f"{base}/chat/completions"

    def _api_root(self) -> str:
        if not self.config.base_url:
            raise ProviderError("LLM_BASE_URL is not configured", "llm_not_configured")
        base = self.config.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base.removesuffix("/chat/completions")
        if base.endswith("/models"):
            return base.removesuffix("/models")
        return base

    def _models_url(self) -> str:
        return f"{self._api_root()}/models"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def health(self) -> ProviderHealth:
        if not self.config.model:
            return ProviderHealth("not_configured", "LLM_MODEL is not configured")
        try:
            with _open_url(URLRequest(self._models_url(), headers=self._headers()), timeout=self.config.timeout_seconds) as response:
                if not 200 <= response.status < 300:
                    return ProviderHealth("unavailable", f"Remote provider returned HTTP {response.status}")
                raw = response.read(256 * 1024)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                return ProviderHealth("unavailable", "Remote provider returned invalid model metadata")
            models = body.get("data") if isinstance(body, dict) else None
            if isinstance(models, list) and models:
                available = {
                    item.get("id")
                    for item in models
                    if isinstance(item, dict) and isinstance(item.get("id"), str)
                }
                if available and self.config.model not in available:
                    return ProviderHealth("unavailable", "Configured model is not available")
                return ProviderHealth("connected", "Remote provider reachable and model available")
            # Some compatible gateways authenticate and answer /models without
            # advertising their catalog. The endpoint is still genuinely
            # reachable, but model availability can only be verified on use.
            return ProviderHealth("connected", "Remote provider reachable; model catalog unavailable")
        except ValueError as exc:
            return ProviderHealth("not_configured", "LLM_BASE_URL is invalid")
        except HTTPError as exc:
            code = exc.code
            exc.close()
            if code in {401, 403}:
                return ProviderHealth("unavailable", "Authentication failure")
            if code in {404, 400}:
                return ProviderHealth("unavailable", "Provider model endpoint or model is unavailable")
            return ProviderHealth("unavailable", f"Remote provider returned HTTP {code}")
        except (socket.timeout, TimeoutError):
            return ProviderHealth("unavailable", "Provider health check timed out")
        except URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                return ProviderHealth("unavailable", "Provider health check timed out")
            return ProviderHealth("unavailable", "Remote provider unavailable")
        except OSError:
            return ProviderHealth("unavailable", "Remote provider unavailable")

    def generate(self, request: LLMRequest) -> LLMResponse:
        if not self.config.model:
            raise ProviderError("LLM_MODEL is not configured", "llm_not_configured")
        payload = json.dumps(
            {
                "model": self.config.model,
                "messages": [{"role": "user", "content": request.prompt}],
                "temperature": 0,
                "stream": False,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        started = time.perf_counter()
        try:
            with _open_url(
                URLRequest(self._endpoint(), data=payload, headers=self._headers(), method="POST"),
                timeout=self.config.timeout_seconds,
            ) as response:
                raw = response.read(256 * 1024)
        except ValueError as exc:
            raise ProviderError("LLM_BASE_URL is invalid", "llm_not_configured") from exc
        except HTTPError as exc:
            status = exc.code
            if status in {401, 403}:
                code = "llm_authentication_failed"
                message = "Authentication failure"
            elif status in {404, 400}:
                code = "llm_model_unavailable"
                message = "Configured model or provider endpoint is unavailable"
            elif status in {408, 504}:
                code = "llm_timeout"
                message = "Provider request timed out"
            else:
                code = "llm_http_failure"
                message = f"Remote provider returned HTTP {status}"
            exc.close()
            raise ProviderError(message, code) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise ProviderError("Provider request timed out", "llm_timeout") from exc
        except URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise ProviderError("Provider request timed out", "llm_timeout") from exc
            raise ProviderError("Remote provider unavailable", "llm_unavailable") from exc
        except OSError as exc:
            raise ProviderError("Remote provider unavailable", "llm_unavailable") from exc
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        try:
            body = json.loads(raw)
            text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError("Remote provider returned an invalid response", "llm_invalid_response") from exc
        if not isinstance(text, str) or not text.strip():
            raise ProviderError("Remote provider returned empty response text", "llm_empty_response")
        usage: dict[str, int | float] = {}
        raw_usage = body.get("usage") if isinstance(body, dict) else None
        if isinstance(raw_usage, dict):
            for key, value in raw_usage.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if not math.isfinite(value):
                        raise ProviderError("Remote provider returned non-finite usage metadata", "llm_invalid_response")
                    usage[str(key)] = value
        response_model = body.get("model") if isinstance(body, dict) else None
        model = response_model if isinstance(response_model, str) and response_model else self.config.model
        return LLMResponse(
            text[:MAX_RESPONSE_CHARS],
            "openai_compatible",
            model,
            request.invocation_id,
            latency_ms=latency_ms,
            usage=usage,
            evidence_type="real_model",
        )


class OllamaProvider(LLMProvider):
    """Optional local Ollama HTTP provider; never imported or required at install time."""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @property
    def base_url(self) -> str:
        return (self.config.base_url or "http://127.0.0.1:11434").rstrip("/")

    def metadata(self) -> dict[str, Any]:
        return {
            "provider": "ollama",
            "display_name": "Ollama / Local Endpoint",
            "model": self.config.model or "not configured",
            "external": False,
            "evidence_type": "real_model",
        }

    def health(self) -> ProviderHealth:
        if not self.config.model:
            return ProviderHealth("not_configured", "LLM_MODEL is not configured")
        try:
            with _open_url(URLRequest(f"{self.base_url}/api/tags"), timeout=self.config.timeout_seconds) as response:
                if not 200 <= response.status < 300:
                    return ProviderHealth("unavailable", f"Local provider returned HTTP {response.status}")
                raw = response.read(256 * 1024)
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    return ProviderHealth("unavailable", "Local provider returned invalid model metadata")
                models = body.get("models") if isinstance(body, dict) else None
                available = {
                    item.get("name")
                    for item in models or []
                    if isinstance(item, dict) and isinstance(item.get("name"), str)
                }
                if available and self.config.model not in available:
                    return ProviderHealth("unavailable", "Configured model is not available")
                if available:
                    return ProviderHealth("connected", "Local provider reachable and model available")
                return ProviderHealth("connected", "Local provider reachable; model catalog unavailable")
        except HTTPError as exc:
            exc.close()
            return ProviderHealth("unavailable", "Local provider unavailable")
        except (socket.timeout, TimeoutError):
            return ProviderHealth("unavailable", "Provider health check timed out")
        except URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                return ProviderHealth("unavailable", "Provider health check timed out")
            return ProviderHealth("unavailable", "Local provider unavailable")
        except (OSError, ValueError):
            return ProviderHealth("unavailable", "Local provider unavailable")

    def generate(self, request: LLMRequest) -> LLMResponse:
        if not self.config.model:
            raise ProviderError("LLM_MODEL is not configured", "llm_not_configured")
        payload = json.dumps(
            {
                "model": self.config.model,
                "messages": [{"role": "user", "content": request.prompt}],
                "stream": False,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        started = time.perf_counter()
        try:
            with _open_url(
                URLRequest(f"{self.base_url}/api/chat", data=payload, headers={"Content-Type": "application/json"}, method="POST"),
                timeout=self.config.timeout_seconds,
            ) as response:
                raw = response.read(256 * 1024)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            code = "llm_model_unavailable" if status in {400, 404} else "llm_http_failure"
            raise ProviderError(f"Local provider returned HTTP {status}", code) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise ProviderError("Provider request timed out", "llm_timeout") from exc
        except URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise ProviderError("Provider request timed out", "llm_timeout") from exc
            raise ProviderError("Local provider unavailable", "llm_unavailable") from exc
        except OSError as exc:
            raise ProviderError("Local provider unavailable", "llm_unavailable") from exc
        try:
            body = json.loads(raw)
            text = body["message"]["content"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderError("Local provider returned an invalid response", "llm_invalid_response") from exc
        if not isinstance(text, str) or not text.strip():
            raise ProviderError("Local provider returned empty response text", "llm_empty_response")
        return LLMResponse(
            text[:MAX_RESPONSE_CHARS],
            "ollama",
            self.config.model,
            request.invocation_id,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            evidence_type="real_model",
        )


class UnconfiguredProvider(LLMProvider):
    def health(self) -> ProviderHealth:
        return ProviderHealth("not_configured", "LLM provider not configured")

    def metadata(self) -> dict[str, Any]:
        return {
            "provider": "unconfigured",
            "display_name": "Not Configured",
            "model": "—",
            "external": False,
            "evidence_type": "none",
        }

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise ProviderError("LLM provider not configured", "llm_not_configured")


def provider_from_config(config: ProviderConfig) -> LLMProvider:
    providers: dict[str, type[LLMProvider]] = {
        "fixture": FixtureProvider,
        "openai_compatible": OpenAICompatibleProvider,
        "ollama": OllamaProvider,
        "unconfigured": UnconfiguredProvider,
    }
    provider_type = providers.get(config.provider)
    if provider_type is None:
        raise ProviderError(f"unsupported LLM provider: {config.provider}", "llm_provider_invalid")
    if provider_type in {FixtureProvider, UnconfiguredProvider}:
        return provider_type()
    return provider_type(config)  # type: ignore[call-arg]
