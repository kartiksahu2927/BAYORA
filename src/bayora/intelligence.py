"""TinyFish-backed security intelligence and evidence collection.

The adapter deliberately keeps the vendor contract at this boundary. Bayora
authorizes the source, tenant, session, and evidence before anything is
persisted; TinyFish only performs the approved browser task.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urljoin
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_TOPIC_CHARS = 500
MAX_OBJECTIVE_CHARS = 2_000
MAX_CORRELATION_CHARS = 120
MAX_EVIDENCE_TEXT_CHARS = 8_000
MAX_SOURCE_URL_CHARS = 2_048
MAX_PROVIDER_RESPONSE_BYTES = 512 * 1024


class IntelligenceError(RuntimeError):
    """A safe, client-independent research integration failure."""

    def __init__(self, message: str, code: str = "intelligence_failed"):
        super().__init__(message)
        self.code = code


class SourcePolicyError(IntelligenceError):
    def __init__(self, message: str = "research source is not approved"):
        super().__init__(message, "source_policy_violation")


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


_OPENER = build_opener(_NoRedirectHandler())


@dataclass(frozen=True)
class IntelligenceRequest:
    topic: str
    objective: str
    source_categories: tuple[str, ...]
    max_results: int
    evaluation_session_id: str | None = None
    correlation_id: str | None = None


@dataclass(frozen=True)
class TinyFishRun:
    run_id: str
    status: str
    result: Any = None
    error: Any = None
    started_at: str | None = None
    finished_at: str | None = None
    num_of_steps: int | None = None


def _is_public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def validate_public_source_url(
    url: str,
    allowed_urls: tuple[str, ...],
    *,
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
) -> str:
    """Validate an HTTPS URL against exact configured targets and public DNS."""
    if not isinstance(url, str) or len(url) > MAX_SOURCE_URL_CHARS:
        raise SourcePolicyError()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SourcePolicyError()
    normalized = url.rstrip("/")
    configured = {candidate.rstrip("/") for candidate in allowed_urls}
    if normalized not in configured:
        raise SourcePolicyError()
    try:
        addresses = resolver(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        raise SourcePolicyError() from exc
    if not addresses:
        raise SourcePolicyError()
    for address in addresses:
        host = address[4][0]
        try:
            if not _is_public_ip(host):
                raise SourcePolicyError()
        except ValueError as exc:
            raise SourcePolicyError() from exc
    return url


def validate_result_source_url(url: str, allowed_hosts: frozenset[str]) -> str:
    """Keep extracted provenance on an approved HTTPS public hostname."""
    if not isinstance(url, str) or len(url) > MAX_SOURCE_URL_CHARS:
        raise SourcePolicyError()
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.fragment:
        raise SourcePolicyError()
    if host not in allowed_hosts and not any(host.endswith("." + item) for item in allowed_hosts):
        raise SourcePolicyError()
    return url


class TinyFishClient:
    """Small documented Agent API client using async run plus polling."""

    def __init__(self, base_url: str, api_key: str | None, timeout_seconds: float, poll_interval_seconds: float, max_duration_seconds: float):
        if not base_url.startswith("https://"):
            raise ValueError("TinyFish base URL must use HTTPS")
        if not api_key:
            raise IntelligenceError("security intelligence integration is not configured", "tinyfish_not_configured")
        self.base_url = base_url.rstrip("/") + "/"
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.max_duration_seconds = max_duration_seconds

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
        request = Request(
            urljoin(self.base_url, path.lstrip("/")),
            data=body,
            headers={"X-API-Key": self.api_key, "Accept": "application/json", "Content-Type": "application/json"},
            method=method,
        )
        try:
            with _OPENER.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
                if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
                    raise IntelligenceError("TinyFish response exceeded the configured size limit", "tinyfish_response_too_large")
        except HTTPError as exc:
            status = exc.code
            exc.close()
            if status == 401:
                raise IntelligenceError("TinyFish authentication failed", "tinyfish_authentication_failed") from exc
            if status == 429:
                raise IntelligenceError("TinyFish rate limit reached", "tinyfish_rate_limited") from exc
            if status in {408, 504}:
                raise IntelligenceError("TinyFish request timed out", "tinyfish_timeout") from exc
            if status >= 500:
                raise IntelligenceError("TinyFish service is unavailable", "tinyfish_unavailable") from exc
            raise IntelligenceError("TinyFish rejected the request", "tinyfish_request_rejected") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise IntelligenceError("TinyFish request timed out", "tinyfish_timeout") from exc
        except (URLError, OSError) as exc:
            raise IntelligenceError("TinyFish service is unavailable", "tinyfish_unavailable") from exc
        try:
            body_data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IntelligenceError("TinyFish returned an invalid response", "tinyfish_invalid_response") from exc
        if not isinstance(body_data, dict):
            raise IntelligenceError("TinyFish returned an invalid response", "tinyfish_invalid_response")
        return body_data

    def run(self, url: str, goal: str, output_schema: dict[str, Any]) -> TinyFishRun:
        response = self._request(
            "POST",
            "/automation/run-async",
            {"url": url, "goal": goal, "output_schema": output_schema},
        )
        run_id = response.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise IntelligenceError("TinyFish did not return a task identifier", "tinyfish_invalid_response")
        deadline = time.monotonic() + self.max_duration_seconds
        while True:
            current = self._request("GET", f"/runs/{run_id}")
            status = current.get("status")
            if status in {"COMPLETED", "FAILED", "CANCELLED"}:
                return TinyFishRun(
                    run_id,
                    status,
                    current.get("result"),
                    current.get("error"),
                    current.get("started_at"),
                    current.get("finished_at"),
                    current.get("num_of_steps") if isinstance(current.get("num_of_steps"), int) else None,
                )
            if status not in {"PENDING", "RUNNING"}:
                raise IntelligenceError("TinyFish returned an unknown task status", "tinyfish_invalid_response")
            if time.monotonic() >= deadline:
                raise IntelligenceError("TinyFish task exceeded its time limit", "tinyfish_timeout")
            time.sleep(min(self.poll_interval_seconds, max(0.0, deadline - time.monotonic())))


def output_schema(max_results: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "maxItems": max_results,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "source_url": {"type": "string"},
                        "title": {"type": "string"},
                        "publication_date": {"type": "string"},
                        "category": {"type": "string"},
                        "summary": {"type": "string"},
                        "technical_details": {"type": "string"},
                        "mitigation": {"type": "string"},
                    },
                    "required": ["summary"],
                },
            }
        },
        "required": ["findings"],
    }


def normalize_findings(
    run: TinyFishRun,
    source_url: str,
    topic: str,
    max_results: int,
    allowed_hosts: frozenset[str],
) -> list[dict[str, Any]]:
    if run.status != "COMPLETED":
        code = "tinyfish_cancelled" if run.status == "CANCELLED" else "tinyfish_task_failed"
        raise IntelligenceError("TinyFish task did not complete", code)
    result = run.result
    if isinstance(result, dict) and isinstance(result.get("result"), dict):
        result = result["result"]
    if not isinstance(result, dict):
        raise IntelligenceError("TinyFish returned no usable research result", "tinyfish_empty_result")
    if result.get("status") == "failure":
        raise IntelligenceError("TinyFish could not complete the research objective", "tinyfish_task_failed")
    raw_findings = result.get("findings")
    if not isinstance(raw_findings, list):
        raise IntelligenceError("TinyFish returned no usable research findings", "tinyfish_empty_result")
    collected_at = datetime.now(timezone.utc).isoformat()
    normalized: list[dict[str, Any]] = []
    for item in raw_findings[:max_results]:
        if not isinstance(item, dict) or not isinstance(item.get("summary"), str) or not item["summary"].strip():
            continue
        candidate_url = item.get("source_url") if isinstance(item.get("source_url"), str) else source_url
        source = validate_result_source_url(candidate_url, allowed_hosts)
        summary = item["summary"].strip()[:MAX_EVIDENCE_TEXT_CHARS]
        title = item.get("title") if isinstance(item.get("title"), str) else None
        technical = item.get("technical_details") if isinstance(item.get("technical_details"), str) else None
        mitigation = item.get("mitigation") if isinstance(item.get("mitigation"), str) else None
        publication_date = item.get("publication_date") if isinstance(item.get("publication_date"), str) else None
        category = item.get("category") if isinstance(item.get("category"), str) else None
        provider_id = item.get("id") if isinstance(item.get("id"), str) else ""
        evidence_id = hashlib.sha256(f"{source}|{topic}|{provider_id}|{summary}".encode("utf-8")).hexdigest()
        normalized.append(
            {
                "evidence_id": evidence_id,
                "provider_finding_id": provider_id or None,
                "source_url": source,
                "title": title[:MAX_EVIDENCE_TEXT_CHARS] if title else None,
                "publication_date": publication_date,
                "collected_at": collected_at,
                "topic": topic,
                "category": category,
                "summary": summary,
                "technical_details": technical[:MAX_EVIDENCE_TEXT_CHARS] if technical else None,
                "mitigation": mitigation[:MAX_EVIDENCE_TEXT_CHARS] if mitigation else None,
                "provenance": {
                    "provider": "tinyfish",
                    "provider_run_id": run.run_id,
                    "provider_status": run.status,
                    "content_unverified": True,
                },
            }
        )
    if not normalized:
        raise IntelligenceError("TinyFish returned no usable research findings", "tinyfish_empty_result")
    return normalized
