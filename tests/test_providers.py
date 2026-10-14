from __future__ import annotations

import json
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bayora.providers import (
    FixtureProvider,
    LLMRequest,
    OllamaProvider,
    OpenAICompatibleProvider,
    ProviderConfig,
    ProviderError,
)


class ProviderHTTPHandler(BaseHTTPRequestHandler):
    provider_kind = "openai"
    mode = "success"

    def do_GET(self) -> None:
        if self.mode == "timeout":
            time.sleep(0.2)
        if self.mode == "auth":
            self.send_response(401)
            self.end_headers()
            return
        if self.provider_kind == "openai":
            body = b'{"data":[{"id":"test-model"}]}' if self.mode != "model_unavailable" else b'{"data":[{"id":"other-model"}]}'
        else:
            body = b'{"models":[]}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def do_POST(self) -> None:
        if self.mode == "timeout":
            time.sleep(0.2)
        if self.mode == "auth":
            self.send_response(401)
            self.end_headers()
            return
        if self.mode == "failure":
            self.send_response(500)
            self.end_headers()
            return
        if self.mode in {"model", "model_unavailable"}:
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if self.mode == "malformed":
            body = b'{"choices":[]}'
        elif self.provider_kind == "openai":
            usage = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": float("inf")} if self.mode == "nonfinite" else {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}
            body = json.dumps(
                {
                    "model": "test-model",
                    "choices": [{"message": {"content": "remote provider output"}}],
                    "usage": usage,
                }
            ).encode()
        else:
            body = json.dumps({"message": {"content": "local provider output"}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def log_message(self, format: str, *args: object) -> None:
        return


class RedirectProbeHandler(BaseHTTPRequestHandler):
    target = ""

    def _redirect(self) -> None:
        self.send_response(302)
        self.send_header("Location", self.target)
        self.end_headers()

    def do_GET(self) -> None:
        self._redirect()

    def do_POST(self) -> None:
        self._redirect()

    def log_message(self, format: str, *args: object) -> None:
        return


class RedirectTargetHandler(BaseHTTPRequestHandler):
    authorization_headers: list[str] = []

    def _respond(self, body: bytes) -> None:
        self.authorization_headers.append(self.headers.get("Authorization", ""))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._respond(b'{"data":[{"id":"test-model"}]}')

    def do_POST(self) -> None:
        self._respond(b'{"model":"test-model","choices":[{"message":{"content":"redirected"}}]}')

    def log_message(self, format: str, *args: object) -> None:
        return


def start_provider(kind: str, mode: str) -> tuple[ThreadingHTTPServer, threading.Thread]:
    ProviderHTTPHandler.provider_kind = kind
    ProviderHTTPHandler.mode = mode
    server = ThreadingHTTPServer(("127.0.0.1", 0), ProviderHTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def start_provider_target() -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectTargetHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


class ProviderTests(unittest.TestCase):
    request = LLMRequest("provider test", "sessionabc", "invocationabc")

    def test_fixture_is_available_without_runtime(self) -> None:
        provider = FixtureProvider()
        self.assertEqual(provider.health().status, "connected")
        response = provider.generate(self.request)
        self.assertIn("Not Real Model Evidence", response.text)
        self.assertEqual(provider.metadata()["provider"], "fixture")

    def test_openai_compatible_health_and_success(self) -> None:
        server, thread = start_provider("openai", "success")
        try:
            provider = OpenAICompatibleProvider(
                ProviderConfig(provider="openai_compatible", base_url=f"http://127.0.0.1:{server.server_port}/v1", model="test-model")
            )
            self.assertEqual(provider.health().status, "connected")
            response = provider.generate(self.request)
            self.assertEqual(response.text, "remote provider output")
            self.assertEqual(response.model, "test-model")
            self.assertEqual(response.usage["total_tokens"], 5)
            self.assertEqual(response.evidence_type, "real_model")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_openai_compatible_auth_failure_endpoint_failure_and_timeout(self) -> None:
        for mode, expected_code in (
            ("auth", "llm_authentication_failed"),
            ("failure", "llm_http_failure"),
            ("timeout", "llm_timeout"),
            ("model", "llm_model_unavailable"),
            ("malformed", "llm_invalid_response"),
        ):
            server, thread = start_provider("openai", mode)
            try:
                provider = OpenAICompatibleProvider(
                    ProviderConfig(
                        provider="openai_compatible",
                        base_url=f"http://127.0.0.1:{server.server_port}/v1",
                        model="test-model",
                        timeout_seconds=0.05,
                    )
                )
                with self.assertRaises(ProviderError) as error:
                    provider.generate(self.request)
                self.assertEqual(error.exception.code, expected_code)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_provider_rejects_redirects_without_forwarding_api_key(self) -> None:
        RedirectTargetHandler.authorization_headers = []
        target, target_thread = start_provider_target()
        RedirectProbeHandler.target = f"http://localhost:{target.server_port}/redirected"
        redirect = ThreadingHTTPServer(("127.0.0.1", 0), RedirectProbeHandler)
        redirect_thread = threading.Thread(target=redirect.serve_forever, daemon=True)
        redirect_thread.start()
        try:
            provider = OpenAICompatibleProvider(
                ProviderConfig(
                    provider="openai_compatible",
                    base_url=f"http://127.0.0.1:{redirect.server_port}/v1",
                    model="test-model",
                    api_key="synthetic-review-secret",
                )
            )
            self.assertEqual(provider.health().status, "unavailable")
            with self.assertRaises(ProviderError):
                provider.generate(self.request)
            self.assertEqual(RedirectTargetHandler.authorization_headers, [])
        finally:
            redirect.shutdown()
            redirect.server_close()
            redirect_thread.join(timeout=2)
            target.shutdown()
            target.server_close()
            target_thread.join(timeout=2)

    def test_openai_compatible_rejects_nonfinite_usage(self) -> None:
        server, thread = start_provider("openai", "nonfinite")
        try:
            provider = OpenAICompatibleProvider(
                ProviderConfig(
                    provider="openai_compatible",
                    base_url=f"http://127.0.0.1:{server.server_port}/v1",
                    model="test-model",
                )
            )
            with self.assertRaises(ProviderError) as error:
                provider.generate(self.request)
            self.assertEqual(error.exception.code, "llm_invalid_response")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_openai_compatible_health_rejects_unavailable_model(self) -> None:
        server, thread = start_provider("openai", "model_unavailable")
        try:
            provider = OpenAICompatibleProvider(
                ProviderConfig(
                    provider="openai_compatible",
                    base_url=f"http://127.0.0.1:{server.server_port}/v1",
                    model="test-model",
                )
            )
            health = provider.health()
            self.assertEqual(health.status, "unavailable")
            self.assertIn("model", health.message.lower())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_openai_compatible_health_reports_authentication_failure(self) -> None:
        server, thread = start_provider("openai", "auth")
        try:
            provider = OpenAICompatibleProvider(
                ProviderConfig(
                    provider="openai_compatible",
                    base_url=f"http://127.0.0.1:{server.server_port}/v1",
                    model="test-model",
                    api_key="invalid-but-never-returned",
                )
            )
            health = provider.health()
            self.assertEqual(health.status, "unavailable")
            self.assertEqual(health.message, "Authentication failure")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_ollama_health_and_success_without_importing_ollama(self) -> None:
        server, thread = start_provider("ollama", "success")
        try:
            provider = OllamaProvider(
                ProviderConfig(provider="ollama", base_url=f"http://127.0.0.1:{server.server_port}", model="local-model")
            )
            self.assertEqual(provider.health().status, "connected")
            self.assertEqual(provider.generate(self.request).text, "local provider output")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_ollama_unavailable_is_reported_without_startup_failure(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            unused_port = probe.getsockname()[1]
        provider = OllamaProvider(ProviderConfig(provider="ollama", base_url=f"http://127.0.0.1:{unused_port}", model="local-model", timeout_seconds=0.05))
        self.assertEqual(provider.health().status, "unavailable")
        with self.assertRaises(ProviderError) as error:
            provider.generate(self.request)
        self.assertEqual(error.exception.code, "llm_unavailable")


if __name__ == "__main__":
    unittest.main()
