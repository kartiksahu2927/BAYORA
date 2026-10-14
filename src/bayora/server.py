"""Small dependency-free HTTP API and dashboard server."""

from __future__ import annotations

import json
import mimetypes
import time
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .intelligence import IntelligenceError
from .service import AuthenticationError, AuthorizationError, BayoraService, ForbiddenError, ValidationError


STATIC_DIR = Path(__file__).with_name("static")


class BayoraHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], service: BayoraService):
        self.service = service
        super().__init__(address, BayoraRequestHandler)


class BayoraRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        # Keep access logs free of request bodies and authorization headers.
        super().log_message("%s", format % args)

    @property
    def service(self) -> BayoraService:
        return self.server.service  # type: ignore[attr-defined]

    def _send(self, status: int, payload: dict[str, Any], headers: dict[str, str] | None = None) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'")
        for key, value in {**self._cors_headers(), **(headers or {})}.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def _error(self, status: int, message: str) -> None:
        self._send(status, {"error": message})

    def _send_empty(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _cors_headers(self) -> dict[str, str]:
        """Allow harmless local-browser preflight without exposing remote origins."""
        origin = self.headers.get("Origin")
        if not origin:
            return {}
        parsed_origin = urlparse(origin)
        host = parsed_origin.hostname
        try:
            port = parsed_origin.port or (443 if parsed_origin.scheme == "https" else 80)
        except ValueError:
            return {}
        same_request_host = parsed_origin.netloc == self.headers.get("Host", "")
        if parsed_origin.scheme == "http" and host in {"127.0.0.1", "localhost"} and (same_request_host or port == self.service.settings.port):
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Vary": "Origin",
            }
        return {}

    def _request_origin_allowed(self) -> bool:
        """Reject cross-site state changes while allowing non-browser local clients."""
        fetch_site = self.headers.get("Sec-Fetch-Site", "").lower()
        if fetch_site == "cross-site":
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed_origin = urlparse(origin)
        try:
            port = parsed_origin.port or (443 if parsed_origin.scheme == "https" else 80)
        except ValueError:
            return False
        host = parsed_origin.hostname
        same_request_host = parsed_origin.netloc == self.headers.get("Host", "")
        return parsed_origin.scheme == "http" and host in {"127.0.0.1", "localhost"} and (same_request_host or port == self.service.settings.port)

    def _actor(self):
        return self.service.actor_for_session(self._session_token())

    def _session_token(self) -> str | None:
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return None
        cookies = SimpleCookie()
        try:
            cookies.load(cookie_header)
        except (TypeError, ValueError):
            return None
        morsel = cookies.get(self.service.settings.session_cookie_name)
        return morsel.value if morsel else None

    def _session_cookie(self, token: str, max_age: int | None = None) -> str:
        parts = [
            f"{self.service.settings.session_cookie_name}={token}",
            "Path=/",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if max_age is not None:
            parts.append(f"Max-Age={max_age}")
        if self.service.settings.session_cookie_secure:
            parts.append("Secure")
        return "; ".join(parts)

    def _expired_session_cookie(self) -> str:
        return self._session_cookie("", 0)

    def _body(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise ValidationError("content type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValidationError("invalid content length") from exc
        if length <= 0 or length > self.service.settings.max_request_bytes:
            raise ValidationError("request body exceeds the configured size limit")
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError("request body must be JSON") from exc
        if not isinstance(body, dict):
            raise ValidationError("request body must be an object")
        return body

    def do_OPTIONS(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            headers = {
                "Allow": "GET, POST, OPTIONS",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                **self._cors_headers(),
            }
            self._send_empty(HTTPStatus.NO_CONTENT, headers)
            return
        self._send_empty(HTTPStatus.NO_CONTENT, {"Allow": "GET, OPTIONS"})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._send(HTTPStatus.OK, {"status": "ok", "service": "bayora"})
            return
        if not parsed.path.startswith("/api/"):
            self._static(parsed.path)
            return
        try:
            actor = self._actor()
            if parsed.path == "/api/v1/me":
                self._send(HTTPStatus.OK, {"actor_id": actor.actor_id, "tenant_id": actor.tenant_id, "role": actor.role})
            elif parsed.path == "/api/v1/policy":
                from .policy import POLICY_MATRIX

                self._send(HTTPStatus.OK, {"policy": POLICY_MATRIX})
            elif parsed.path == "/api/v1/provider/status":
                self._send(HTTPStatus.OK, self.service.provider_status(actor))
            elif parsed.path == "/api/v1/evaluations":
                self._send(HTTPStatus.OK, {"evaluations": self.service.list_evaluations(actor)})
            elif parsed.path == "/api/v1/blue-team/recipients":
                self._send(HTTPStatus.OK, {"recipients": self.service.list_blue_recipients(actor)})
            elif parsed.path.startswith("/api/v1/evaluations/"):
                parts = parsed.path.split("/")
                evaluation_id = parts[4] if len(parts) > 4 else ""
                if len(parts) == 6 and parts[5] == "blue-analyses":
                    self._send(HTTPStatus.OK, {"analyses": self.service.list_blue_analyses(actor, evaluation_id)})
                elif len(parts) == 6 and parts[5] == "remediations":
                    self._send(HTTPStatus.OK, {"remediations": self.service.list_remediations(actor, evaluation_id)})
                elif len(parts) == 5:
                    self._send(HTTPStatus.OK, self.service.get_evaluation(actor, evaluation_id))
                else:
                    self._error(HTTPStatus.NOT_FOUND, "route not found")
            elif parsed.path == "/api/v1/findings":
                self._send(HTTPStatus.OK, {"findings": self.service.list_findings(actor)})
            elif parsed.path == "/api/v1/audit/verify":
                self._send(HTTPStatus.OK, self.service.verify_audit(actor))
            elif parsed.path == "/api/v1/security-intelligence/status":
                self._send(HTTPStatus.OK, self.service.intelligence_status(actor))
            elif parsed.path == "/api/v1/security-intelligence/tasks":
                self._send(HTTPStatus.OK, {"tasks": self.service.list_intelligence_tasks(actor)})
            elif parsed.path.startswith("/api/v1/security-intelligence/tasks/"):
                parts = parsed.path.split("/")
                task_id = parts[5] if len(parts) > 5 else ""
                if len(parts) == 7 and parts[6] == "results":
                    self._send(HTTPStatus.OK, {"results": self.service.get_intelligence_evidence(actor, task_id)})
                elif len(parts) == 6:
                    self._send(HTTPStatus.OK, self.service.get_intelligence_task(actor, task_id))
                else:
                    self._error(HTTPStatus.NOT_FOUND, "route not found")
            else:
                self._error(HTTPStatus.NOT_FOUND, "route not found")
        except AuthenticationError as exc:
            self._send(HTTPStatus.UNAUTHORIZED, {"error": str(exc)}, {"WWW-Authenticate": "Cookie"})
        except IntelligenceError as exc:
            self._send(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
        except ForbiddenError as exc:
            self._error(HTTPStatus.FORBIDDEN, str(exc))
        except AuthorizationError as exc:
            self._error(HTTPStatus.FORBIDDEN, str(exc))
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, "resource not found")
        except Exception:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "request could not be completed")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if not self._request_origin_allowed():
                self._error(HTTPStatus.FORBIDDEN, "request origin is not allowed")
                return
            if parsed.path in {"/api/v1/auth/login", "/api/v1/login"}:
                body = self._body()
                credentials = self.service.login(
                    body.get("username", body.get("user_id", body.get("actor_id", ""))),
                    body.get("password", ""),
                    self._session_token(),
                )
                max_age = max(1, int(credentials.expires_at - time.time()))
                self._send(
                    HTTPStatus.OK,
                    {
                        "actor_id": credentials.actor.actor_id,
                        "tenant_id": credentials.actor.tenant_id,
                        "role": credentials.actor.role,
                        "expires_at": credentials.expires_at,
                    },
                    {"Set-Cookie": self._session_cookie(credentials.token, max_age)},
                )
                return

            if parsed.path in {"/api/v1/auth/logout", "/api/v1/logout"}:
                self.service.logout(self._session_token())
                self._send(
                    HTTPStatus.OK,
                    {"logged_out": True},
                    {"Set-Cookie": self._expired_session_cookie()},
                )
                return

            actor = self._actor()
            if parsed.path == "/api/v1/evaluations":
                self._send(HTTPStatus.CREATED, self.service.create_evaluation(actor, self._body()))
            elif parsed.path.startswith("/api/v1/evaluations/"):
                parts = parsed.path.split("/")
                evaluation_id = parts[4] if len(parts) > 4 else ""
                if len(parts) == 6 and parts[5] == "blue-team-access":
                    self._send(HTTPStatus.CREATED, self.service.grant_blue_access(actor, evaluation_id, self._body()))
                elif len(parts) == 6 and parts[5] == "blue-analyses":
                    self._send(HTTPStatus.CREATED, self.service.create_blue_analysis(actor, evaluation_id, self._body()))
                elif len(parts) == 6 and parts[5] == "remediations":
                    self._send(HTTPStatus.CREATED, self.service.create_remediation(actor, evaluation_id, self._body()))
                else:
                    self._error(HTTPStatus.NOT_FOUND, "route not found")
            elif parsed.path in {"/api/v1/security-intelligence/research", "/api/security-intelligence/research"}:
                self._send(HTTPStatus.ACCEPTED, self.service.create_intelligence_task(actor, self._body()))
            elif parsed.path == "/api/v1/security/validation":
                self._send(HTTPStatus.OK, self.service.run_security_validation(actor))
            else:
                self._error(HTTPStatus.NOT_FOUND, "route not found")
        except AuthenticationError as exc:
            self._send(HTTPStatus.UNAUTHORIZED, {"error": str(exc)}, {"WWW-Authenticate": "Cookie"})
        except ForbiddenError as exc:
            self._error(HTTPStatus.FORBIDDEN, str(exc))
        except AuthorizationError as exc:
            self._error(HTTPStatus.FORBIDDEN, str(exc))
        except ValidationError as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except IntelligenceError as exc:
            status = HTTPStatus.SERVICE_UNAVAILABLE if exc.code == "tinyfish_not_configured" else HTTPStatus.BAD_GATEWAY
            self._send(status, {"error": str(exc)})
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, "resource not found")
        except Exception:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "request could not be completed")

    def _static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"", "/"} else unquote(request_path.lstrip("/"))
        candidate = (STATIC_DIR / relative).resolve()
        if STATIC_DIR.resolve() not in candidate.parents and candidate != STATIC_DIR.resolve():
            self._error(HTTPStatus.NOT_FOUND, "resource not found")
            return
        if not candidate.is_file():
            self._error(HTTPStatus.NOT_FOUND, "resource not found")
            return
        content = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'")
        self.end_headers()
        self.wfile.write(content)


def serve(service: BayoraService, host: str, port: int) -> None:
    server = BayoraHTTPServer((host, port), service)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
