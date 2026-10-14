from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from unittest.mock import patch

from bayora.audit import AuditLog
from bayora.config import Settings
from bayora.db import Database
from bayora.intelligence import IntelligenceError, SourcePolicyError, TinyFishClient, TinyFishRun, validate_public_source_url
from bayora.isolation import IsolatedLLMProvider, create_workspace, remove_workspace
from bayora.models import Flow
from bayora.policy import decide
from bayora.providers import LLMRequest, ProviderConfig, ProviderError, provider_from_config
from bayora.server import BayoraHTTPServer
from bayora.service import AuthenticationError, BayoraService


class ProviderHandler(BaseHTTPRequestHandler):
    prompts: list[str] = []
    payloads: list[dict] = []
    mode = "success"

    def do_POST(self) -> None:
        if ProviderHandler.mode == "auth":
            self.send_response(401)
            self.end_headers()
            return
        if ProviderHandler.mode == "model":
            self.send_response(404)
            self.end_headers()
            return
        if ProviderHandler.mode == "timeout":
            import time

            time.sleep(0.2)
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        ProviderHandler.payloads.append(payload)
        ProviderHandler.prompts.append(payload["messages"][0]["content"])
        body = json.dumps(
            {
                "model": "bayora-test-model",
                "choices": [{"message": {"content": "BAYORA_LLM_RESPONSE_CANARY_847291"}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
            }
        ).encode()
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


class TinyFishRedirectTarget(BaseHTTPRequestHandler):
    hits = 0
    authorization_headers: list[str] = []

    def do_GET(self) -> None:
        TinyFishRedirectTarget.hits += 1
        TinyFishRedirectTarget.authorization_headers.append(self.headers.get("X-API-Key", ""))
        self.send_response(200)
        self.end_headers()

    def do_POST(self) -> None:
        self.do_GET()

    def log_message(self, format: str, *args: object) -> None:
        return


class TinyFishRedirectSource(BaseHTTPRequestHandler):
    target = ""

    def do_POST(self) -> None:
        self.send_response(302)
        self.send_header("Location", self.target)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


class SecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_policy_allows_only_same_session_model_flow(self) -> None:
        allowed = decide(Flow("red", "llm", "evaluation", "tenant-a", "session-a", "tenant-a", "session-a"))
        self.assertTrue(allowed.allowed)
        self.assertFalse(decide(Flow("red", "host", "host", "tenant-a", "session-a", "tenant-a", "session-a")).allowed)
        self.assertFalse(decide(Flow("red", "llm", "evaluation", "tenant-a", "session-a", "tenant-a", "session-b")).allowed)
        self.assertFalse(decide(Flow("red", "blue_private", "private", "tenant-a", "session-a", "tenant-a", "session-a")).allowed)

    def test_audit_chain_detects_record_mutation(self) -> None:
        database = Database(self.root / "bayora.sqlite3")
        audit = AuditLog(database, self.root / "audit.key")
        audit.append("test.started", "actor", "tenant", None, {"value": 1})
        records = audit.records()
        self.assertEqual(audit.verify(), (True, "audit chain verified"))
        records[0]["payload_json"] = json.dumps({"value": 2})
        valid, message = audit.verify_records(records)
        self.assertFalse(valid)
        self.assertIn("digest mismatch", message)

    def test_workspace_permissions_and_worker(self) -> None:
        workspace = create_workspace(self.root, "sessionabc123")
        try:
            self.assertEqual(os.stat(workspace).st_mode & 0o777, 0o700)
            result = IsolatedLLMProvider(
                ProviderConfig(provider="fixture"),
                self.root,
                workspace,
            ).generate(
                LLMRequest("bounded input", workspace.name, "invocationabc123")
            )
            self.assertEqual(result.provider, "fixture")
            self.assertEqual(result.model, "bayora-deterministic-fixture")
            self.assertIn("Not Real Model Evidence", result.text)
        finally:
            remove_workspace(workspace)
        self.assertFalse(workspace.exists())

    def test_worker_rejects_malformed_input_without_traceback(self) -> None:
        worker = Path(__file__).parents[1] / "src" / "bayora" / "worker.py"
        for payload in ("[]", '{"operation":"generate","provider_config":{"provider":"fixture"},"request":{"prompt":null,"session_id":"s","invocation_id":"i"}}'):
            completed = subprocess.run(
                [sys.executable, str(worker)],
                input=payload,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 3)
            self.assertEqual(json.loads(completed.stdout)["status"], "error")
            self.assertEqual(completed.stderr, "")

    def test_evaluation_worker_failure_is_persisted_and_workspace_is_removed(self) -> None:
        service = BayoraService(Settings(data_dir=self.root))
        with patch("bayora.isolation.subprocess.run", side_effect=OSError("simulated worker launch failure")):
            evaluation = service.create_evaluation(
                service.actor_for_token("bayora-red-token"),
                {"prompt": "worker launch failure"},
            )
        self.assertEqual(evaluation["state"], "failed")
        self.assertEqual(evaluation["error"]["code"], "worker_launch_failed")
        self.assertEqual(list(service.settings.workspace_dir.iterdir()), [])
        self.assertEqual(
            [event["event_type"] for event in evaluation["audit_events"]][-2:],
            ["llm_request_failed", "evaluation_failed"],
        )

    def test_real_provider_contract_persists_response_and_audit_sequence(self) -> None:
        ProviderHandler.prompts = []
        ProviderHandler.payloads = []
        ProviderHandler.mode = "success"
        provider = ThreadingHTTPServer(("127.0.0.1", 0), ProviderHandler)
        thread = threading.Thread(target=provider.serve_forever, daemon=True)
        thread.start()
        try:
            settings = Settings(
                data_dir=self.root,
                llm_provider="openai_compatible",
                llm_model="bayora-test-model",
                llm_base_url=f"http://127.0.0.1:{provider.server_port}/v1/chat/completions",
            )
            service = BayoraService(settings)
            red = service.actor_for_token("bayora-red-token")
            prompt = "Return the controlled model marker."
            evaluation = service.create_evaluation(red, {"prompt": prompt})
            self.assertEqual(evaluation["state"], "completed")
            self.assertEqual(evaluation["response"], "BAYORA_LLM_RESPONSE_CANARY_847291")
            self.assertEqual(evaluation["model"]["provider"], "openai_compatible")
            self.assertEqual(evaluation["model"]["evidence_type"], "real_model")
            self.assertGreaterEqual(evaluation["latency_ms"], 0)
            self.assertEqual(evaluation["usage"]["total_tokens"], 5)
            self.assertEqual(set(ProviderHandler.payloads[0]), {"model", "messages", "temperature", "stream"})
            self.assertEqual(set(ProviderHandler.payloads[0]["messages"][0]), {"role", "content"})
            self.assertNotIn("session_id", ProviderHandler.payloads[0])
            self.assertEqual(ProviderHandler.prompts, [prompt])
            self.assertIsNone(evaluation["input"].get("prompt"))
            self.assertEqual(service.database.evaluation(evaluation["id"])["response"], evaluation["response"])
            self.assertNotIn("workspace", evaluation)
            self.assertEqual(list(service.settings.workspace_dir.iterdir()), [])
            self.assertEqual(
                [event["event_type"] for event in evaluation["audit_events"]],
                ["evaluation_created", "policy_checked", "llm_invocation", "llm_response_received", "evaluation_completed"],
            )
        finally:
            provider.shutdown()
            provider.server_close()
            thread.join(timeout=2)

    def test_unconfigured_provider_fails_without_completed_state(self) -> None:
        service = BayoraService(Settings(data_dir=self.root, llm_provider="unconfigured"))
        red = service.actor_for_token("bayora-red-token")
        evaluation = service.create_evaluation(red, {"prompt": "test model refusal"})
        self.assertEqual(evaluation["state"], "failed")
        self.assertEqual(evaluation["error"]["code"], "llm_not_configured")
        self.assertIsNone(evaluation["response"])
        self.assertNotIn("evaluation_completed", [event["event_type"] for event in evaluation["audit_events"]])
        self.assertEqual(
            [event["event_type"] for event in evaluation["audit_events"]],
            ["evaluation_created", "policy_checked", "llm_invocation", "llm_request_failed", "evaluation_failed"],
        )

    def test_provider_failures_are_recorded_without_fixture_fallback(self) -> None:
        for mode, expected_code in (("auth", "llm_authentication_failed"), ("model", "llm_model_unavailable"), ("timeout", "llm_timeout")):
            ProviderHandler.mode = mode
            provider = ThreadingHTTPServer(("127.0.0.1", 0), ProviderHandler)
            thread = threading.Thread(target=provider.serve_forever, daemon=True)
            thread.start()
            try:
                service = BayoraService(
                    Settings(
                        data_dir=self.root / mode,
                        llm_provider="openai_compatible",
                        llm_model="bayora-test-model",
                        llm_base_url=f"http://127.0.0.1:{provider.server_port}/v1",
                        llm_timeout_seconds=0.05,
                    )
                )
                evaluation = service.create_evaluation(
                    service.actor_for_token("bayora-red-token"),
                    {"prompt": f"provider failure {mode}"},
                )
                self.assertEqual(evaluation["state"], "failed")
                self.assertEqual(evaluation["error"]["code"], expected_code)
                self.assertIsNone(evaluation["response"])
                self.assertNotEqual(evaluation["model"]["provider"], "fixture")
                self.assertNotIn("evaluation_completed", [event["event_type"] for event in evaluation["audit_events"]])
            finally:
                provider.shutdown()
                provider.server_close()
                thread.join(timeout=2)

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            unused_port = probe.getsockname()[1]
        service = BayoraService(
            Settings(
                data_dir=self.root / "unavailable",
                llm_provider="openai_compatible",
                llm_model="bayora-test-model",
                llm_base_url=f"http://127.0.0.1:{unused_port}/v1",
                llm_timeout_seconds=0.05,
            )
        )
        evaluation = service.create_evaluation(service.actor_for_token("bayora-red-token"), {"prompt": "provider unavailable"})
        self.assertEqual(evaluation["state"], "failed")
        self.assertEqual(evaluation["error"]["code"], "llm_unavailable")

    def test_session_context_isolation_and_credentials_are_not_disclosed(self) -> None:
        ProviderHandler.prompts = []
        ProviderHandler.payloads = []
        ProviderHandler.mode = "success"
        provider = ThreadingHTTPServer(("127.0.0.1", 0), ProviderHandler)
        thread = threading.Thread(target=provider.serve_forever, daemon=True)
        thread.start()
        try:
            secret = "test-secret-that-must-not-escape"
            service = BayoraService(
                Settings(
                    data_dir=self.root,
                    llm_provider="openai_compatible",
                    llm_model="bayora-test-model",
                    llm_base_url=f"http://127.0.0.1:{provider.server_port}/v1",
                    llm_api_key=secret,
                )
            )
            red = service.actor_for_token("bayora-red-token")
            first = service.create_evaluation(red, {"prompt": "first isolated prompt"})
            second = service.create_evaluation(red, {"prompt": "second isolated prompt"})
            self.assertNotEqual(first["session_id"], second["session_id"])
            self.assertEqual(ProviderHandler.prompts, ["first isolated prompt", "second isolated prompt"])
            status = service.provider_status(red)
            self.assertNotIn(secret, json.dumps(status))
            self.assertNotIn(secret, json.dumps(first))
            self.assertNotIn(secret, json.dumps(second))
            self.assertNotIn(secret, json.dumps(service.audit.records()))
        finally:
            provider.shutdown()
            provider.server_close()
            thread.join(timeout=2)

    def test_provider_selection_is_explicit(self) -> None:
        self.assertEqual(provider_from_config(ProviderConfig(provider="fixture")).metadata()["provider"], "fixture")
        self.assertEqual(
            provider_from_config(ProviderConfig(provider="openai_compatible", base_url="http://model", model="m"))
            .metadata()["provider"],
            "openai_compatible",
        )

    def test_invalid_provider_fails_without_corrupting_audit_state(self) -> None:
        service = BayoraService(Settings(data_dir=self.root, llm_provider="invalid-provider"))
        evaluation = service.create_evaluation(
            service.actor_for_token("bayora-red-token"),
            {"prompt": "invalid provider test"},
        )
        self.assertEqual(evaluation["state"], "failed")
        self.assertEqual(evaluation["error"]["code"], "llm_provider_invalid")
        self.assertTrue(service.audit.verify()[0])

    def test_invalid_numeric_configuration_is_rejected(self) -> None:
        with patch.dict(os.environ, {"BAYORA_PORT": "not-a-port"}, clear=False):
            with self.assertRaisesRegex(ValueError, "BAYORA_PORT"):
                Settings.from_env(self.root)
        with patch.dict(os.environ, {"BAYORA_WORKER_TIMEOUT_SECONDS": "nan"}, clear=False):
            with self.assertRaisesRegex(ValueError, "BAYORA_WORKER_TIMEOUT_SECONDS"):
                Settings.from_env(self.root)
        with self.assertRaisesRegex(ValueError, "finite positive"):
            Settings(data_dir=self.root, llm_timeout_seconds=float("inf"))

    def test_validation_fails_when_fixture_worker_fails(self) -> None:
        service = BayoraService(Settings(data_dir=self.root))
        with patch.object(IsolatedLLMProvider, "generate", side_effect=ProviderError("simulated worker failure", "worker_failure")):
            validation = service.run_security_validation(service.actor_for_token("bayora-admin-token"))
        self.assertFalse(validation["passed"])
        self.assertFalse(validation["runtime"]["worker_passed"])
        self.assertIn("Fixture worker failed", validation["runtime"]["note"])

    def test_intelligence_source_validation_rejects_private_destinations(self) -> None:
        with self.assertRaises(SourcePolicyError):
            validate_public_source_url(
                "https://approved.example/research",
                ("https://approved.example/research",),
                resolver=lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
            )
        with self.assertRaises(SourcePolicyError):
            validate_public_source_url(
                "http://approved.example/research",
                ("http://approved.example/research",),
                resolver=lambda *args, **kwargs: [],
            )

    def test_tinyfish_redirect_does_not_forward_api_key(self) -> None:
        TinyFishRedirectTarget.hits = 0
        TinyFishRedirectTarget.authorization_headers = []
        target = ThreadingHTTPServer(("127.0.0.1", 0), TinyFishRedirectTarget)
        target_thread = threading.Thread(target=target.serve_forever, daemon=True)
        target_thread.start()
        TinyFishRedirectSource.target = f"http://localhost:{target.server_port}/redirected"
        source = ThreadingHTTPServer(("127.0.0.1", 0), TinyFishRedirectSource)
        source_thread = threading.Thread(target=source.serve_forever, daemon=True)
        source_thread.start()
        try:
            client = object.__new__(TinyFishClient)
            client.base_url = f"http://127.0.0.1:{source.server_port}/v1/"
            client.api_key = "synthetic-tinyfish-key"
            client.timeout_seconds = 1
            with self.assertRaisesRegex(IntelligenceError, "rejected"):
                client._request("POST", "/automation/run-async", {})
            self.assertEqual(TinyFishRedirectTarget.hits, 0)
            self.assertEqual(TinyFishRedirectTarget.authorization_headers, [])
        finally:
            source.shutdown()
            source.server_close()
            source_thread.join(timeout=2)
            target.shutdown()
            target.server_close()
            target_thread.join(timeout=2)

    def test_intelligence_task_is_async_deduplicated_persisted_and_tenant_scoped(self) -> None:
        service = BayoraService(
            Settings(
                data_dir=self.root,
                tinyfish_api_key="test-only-key",
                tinyfish_poll_interval_seconds=0.001,
                tinyfish_max_duration_seconds=1,
                intelligence_allowed_sources={"test": ("https://approved.example/research",)},
                bootstrap_passwords={"red-analyst": "red-local-password", "blue-engineer": "blue-local-password", "security-admin": "admin-local-password"},
            )
        )

        class FakeTinyFish:
            def __init__(self, *args, **kwargs):
                return None

            def run(self, url, goal, schema):
                self.url = url
                self.goal = goal
                self.schema = schema
                return TinyFishRun(
                    "tinyfish-run-1",
                    "COMPLETED",
                    {"findings": [{"id": "CVE-test", "title": "Public guidance", "summary": "Unverified security guidance", "source_url": url}]},
                )

        with patch("bayora.service.validate_public_source_url"), patch("bayora.service.TinyFishClient", FakeTinyFish):
            red = service.actor_for_token("bayora-red-token")
            request = {"topic": "prompt injection", "objective": "Collect public guidance", "source_categories": ["test"], "max_results": 3, "correlation_id": "research-1"}
            first = service.create_intelligence_task(red, request)
            second = service.create_intelligence_task(red, request)
            deadline = time.time() + 2
            while time.time() < deadline:
                first = service.get_intelligence_task(red, first["id"])
                if first["state"] in {"COMPLETED", "FAILED"}:
                    break
                time.sleep(0.01)
            self.assertEqual(first["state"], "COMPLETED")
            self.assertEqual(first["result_count"], 1)
            self.assertEqual(second["id"], first["id"])
            evidence = service.get_intelligence_evidence(red, first["id"])
            self.assertEqual(evidence[0]["source_url"], "https://approved.example/research")
            self.assertTrue(evidence[0]["provenance"]["content_unverified"])
            reopened = BayoraService(
                Settings(
                    data_dir=self.root,
                    tinyfish_api_key="test-only-key",
                    tinyfish_poll_interval_seconds=0.001,
                    tinyfish_max_duration_seconds=1,
                    intelligence_allowed_sources={"test": ("https://approved.example/research",)},
                )
            )
            self.assertEqual(reopened.get_intelligence_task(red, first["id"])["state"], "COMPLETED")
            self.assertEqual(reopened.database.intelligence_evidence(first["id"])[0]["summary"], "Unverified security guidance")
            blue = service.actor_for_token("bayora-blue-token")
            with self.assertRaises(KeyError):
                service.get_intelligence_task(blue, first["id"])
            auditor = service.actor_for_token("bayora-auditor-token")
            self.assertEqual(service.get_intelligence_task(auditor, first["id"])["id"], first["id"])
            event_types = [event["event_type"] for event in service.audit.records()]
            self.assertIn("security_intelligence_task_requested", event_types)
            self.assertIn("security_intelligence_task_completed", event_types)

    def test_intelligence_missing_credentials_is_safe_and_provider_failure_is_not_success(self) -> None:
        service = BayoraService(Settings(data_dir=self.root, intelligence_allowed_sources={"test": ("https://approved.example/research",)}))
        with self.assertRaisesRegex(IntelligenceError, "not configured"):
            service.create_intelligence_task(
                service.actor_for_token("bayora-red-token"),
                {"topic": "topic", "objective": "objective", "source_categories": ["test"]},
            )

        service = BayoraService(
            Settings(data_dir=self.root / "failure", tinyfish_api_key="test-only-key", intelligence_allowed_sources={"test": ("https://approved.example/research",)})
        )
        class FailedTinyFish:
            def __init__(self, *args, **kwargs):
                return None

            def run(self, *args, **kwargs):
                return TinyFishRun("tinyfish-run-failed", "FAILED", error={"code": "SITE_BLOCKED"})

        with patch("bayora.service.validate_public_source_url"), patch("bayora.service.TinyFishClient", FailedTinyFish):
            task = service.create_intelligence_task(
                service.actor_for_token("bayora-red-token"),
                {"topic": "topic", "objective": "objective", "source_categories": ["test"]},
            )
            deadline = time.time() + 2
            while time.time() < deadline:
                task = service.get_intelligence_task(service.actor_for_token("bayora-red-token"), task["id"])
                if task["state"] in {"COMPLETED", "FAILED"}:
                    break
                time.sleep(0.01)
            self.assertEqual(task["state"], "FAILED")
            self.assertEqual(task["error_code"], "tinyfish_task_failed")

    def test_service_tenant_scope_and_validation(self) -> None:
        service = BayoraService(Settings.from_env(self.root))
        red = service.actor_for_token("bayora-red-token")
        blue = service.actor_for_token("bayora-blue-token")
        evaluation = service.create_evaluation(red, {"prompt": "test model refusal"})
        self.assertEqual(evaluation["state"], "completed")
        self.assertIn("Not Real Model Evidence", evaluation["response"])
        self.assertEqual(service.get_evaluation(red, evaluation["id"])["id"], evaluation["id"])
        with self.assertRaises(KeyError):
            service.get_evaluation(blue, evaluation["id"])
        validation = service.run_security_validation(service.actor_for_token("bayora-admin-token"))
        self.assertTrue(validation["passed"])
        self.assertEqual(len(validation["controls"]), 6)
        self.assertEqual(validation["runtime"]["scope"], "application_policy_and_fixture_worker")

    def test_http_requires_authentication(self) -> None:
        service = BayoraService(
            Settings(
                data_dir=self.root,
                bootstrap_passwords={
                    "red-analyst": "red-local-password",
                    "blue-engineer": "blue-local-password",
                    "security-admin": "admin-local-password",
                    "audit-reviewer": "auditor-local-password",
                },
            )
        )
        server = BayoraHTTPServer(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            url = f"{base_url}/api/v1/evaluations"
            preflight = Request(
                f"{base_url}/api/v1/security/validation",
                headers={
                    "Origin": base_url,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
                method="OPTIONS",
            )
            with urlopen(preflight) as response:
                self.assertEqual(response.status, 204)
                self.assertEqual(response.headers["Access-Control-Allow-Origin"], base_url)
                self.assertIn("POST", response.headers["Access-Control-Allow-Methods"])

            with self.assertRaises(HTTPError) as error:
                urlopen(url)
            self.assertEqual(error.exception.code, 401)
            error.exception.close()

            legacy_request = Request(url, headers={"Authorization": "Bearer bayora-red-token"})
            with self.assertRaises(HTTPError) as error:
                urlopen(legacy_request)
            self.assertEqual(error.exception.code, 401)
            error.exception.close()

            opener = build_opener(HTTPCookieProcessor(CookieJar()))
            invalid_login = Request(
                f"{base_url}/api/v1/auth/login",
                data=json.dumps({"username": "red-analyst", "password": "wrong"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as error:
                opener.open(invalid_login)
            self.assertEqual(error.exception.code, 401)
            error.exception.close()

            wrong_content_type = Request(
                f"{base_url}/api/v1/auth/login",
                data=json.dumps({"username": "red-analyst", "password": "red-local-password"}).encode(),
                headers={"Content-Type": "text/plain"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as error:
                opener.open(wrong_content_type)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()

            cross_site_login = Request(
                f"{base_url}/api/v1/auth/login",
                data=json.dumps({"username": "red-analyst", "password": "red-local-password"}).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://untrusted.example",
                    "Sec-Fetch-Site": "cross-site",
                },
                method="POST",
            )
            with self.assertRaises(HTTPError) as error:
                opener.open(cross_site_login)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()

            malformed_origin = Request(
                f"{base_url}/healthz",
                headers={"Origin": "http://localhost:not-a-port"},
            )
            with opener.open(malformed_origin) as response:
                self.assertEqual(response.status, 200)

            login = Request(
                f"{base_url}/api/v1/auth/login",
                data=json.dumps({"username": "red-analyst", "password": "red-local-password"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with opener.open(login) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("bayora_session=", response.headers["Set-Cookie"])

            me_request = Request(f"{base_url}/api/v1/me")
            with opener.open(me_request) as response:
                self.assertEqual(json.load(response)["role"], "red")

            logout = Request(f"{base_url}/api/v1/auth/logout", data=b"{}", method="POST")
            with opener.open(logout) as response:
                self.assertEqual(response.status, 200)
                self.assertIn("Max-Age=0", response.headers["Set-Cookie"])

            with self.assertRaises(HTTPError) as error:
                opener.open(me_request)
            self.assertEqual(error.exception.code, 401)
            error.exception.close()

            blue_opener = build_opener(HTTPCookieProcessor(CookieJar()))
            blue_login = Request(
                f"{base_url}/api/v1/auth/login",
                data=json.dumps({"username": "blue-engineer", "password": "blue-local-password"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with blue_opener.open(blue_login) as response:
                self.assertEqual(response.status, 200)
            forbidden_request = Request(
                url,
                data=json.dumps({"prompt": "must be denied for blue"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as error:
                blue_opener.open(forbidden_request)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
            status_request = Request(
                f"http://127.0.0.1:{server.server_port}/api/v1/provider/status",
            )
            with blue_opener.open(status_request) as response:
                status = json.load(response)
                self.assertEqual(status["provider"]["provider"], "fixture")
                self.assertEqual(status["health"]["status"], "connected")
                self.assertNotIn("api_key", status)
                self.assertNotIn("base_url", status)

            review_opener = build_opener(HTTPCookieProcessor(CookieJar()))
            admin_login = Request(
                f"{base_url}/api/v1/auth/login",
                data=json.dumps({"username": "security-admin", "password": "admin-local-password"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with review_opener.open(admin_login) as response:
                self.assertEqual(json.load(response)["role"], "admin")
            def validation_request() -> Request:
                return Request(
                    f"{base_url}/api/v1/security/validation",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )

            with review_opener.open(validation_request()) as response:
                self.assertTrue(json.load(response)["passed"])

            auditor_login = Request(
                f"{base_url}/api/v1/auth/login",
                data=json.dumps({"username": "audit-reviewer", "password": "auditor-local-password"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with review_opener.open(auditor_login) as response:
                self.assertEqual(json.load(response)["role"], "auditor")
            with review_opener.open(validation_request()) as response:
                self.assertTrue(json.load(response)["passed"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_http_security_intelligence_routes_use_existing_cookie_rbac(self) -> None:
        service = BayoraService(
            Settings(
                data_dir=self.root,
                tinyfish_api_key="test-only-key",
                tinyfish_poll_interval_seconds=0.001,
                tinyfish_max_duration_seconds=1,
                intelligence_allowed_sources={"test": ("https://approved.example/research",)},
                bootstrap_passwords={"red-analyst": "red-local-password", "blue-engineer": "blue-local-password", "security-admin": "admin-local-password"},
            )
        )
        class FakeTinyFish:
            def __init__(self, *args, **kwargs):
                return None

            def run(self, url, goal, schema):
                return TinyFishRun("http-run-1", "COMPLETED", {"findings": [{"summary": "Unverified result", "source_url": url}]})

        server = BayoraHTTPServer(("127.0.0.1", 0), service)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            opener = build_opener(HTTPCookieProcessor(CookieJar()))
            login = Request(
                base_url + "/api/v1/auth/login",
                data=json.dumps({"username": "red-analyst", "password": "red-local-password"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with patch("bayora.service.validate_public_source_url"), patch("bayora.service.TinyFishClient", FakeTinyFish):
                with opener.open(login) as response:
                    self.assertEqual(response.status, 200)
                request = Request(
                    base_url + "/api/v1/security-intelligence/research",
                    data=json.dumps({"topic": "topic", "objective": "objective", "source_categories": ["test"]}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with opener.open(request) as response:
                    self.assertEqual(response.status, 202)
                    task = json.load(response)
                deadline = time.time() + 2
                while time.time() < deadline:
                    with opener.open(Request(base_url + f"/api/v1/security-intelligence/tasks/{task['id']}")) as response:
                        task = json.load(response)
                    if task["state"] in {"COMPLETED", "FAILED"}:
                        break
                    time.sleep(0.01)
                self.assertEqual(task["state"], "COMPLETED")
                with opener.open(Request(base_url + f"/api/v1/security-intelligence/tasks/{task['id']}/results")) as response:
                    self.assertEqual(len(json.load(response)["results"]), 1)
                blue_opener = build_opener(HTTPCookieProcessor(CookieJar()))
                blue_login = Request(
                    base_url + "/api/v1/auth/login",
                    data=json.dumps({"username": "blue-engineer", "password": "blue-local-password"}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with blue_opener.open(blue_login):
                    pass
                with self.assertRaises(HTTPError) as error:
                    blue_opener.open(Request(base_url + f"/api/v1/security-intelligence/tasks/{task['id']}"))
                self.assertEqual(error.exception.code, 404)
                error.exception.close()
                admin_opener = build_opener(HTTPCookieProcessor(CookieJar()))
                admin_login = Request(
                    base_url + "/api/v1/auth/login",
                    data=json.dumps({"username": "security-admin", "password": "admin-local-password"}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with admin_opener.open(admin_login):
                    pass
                admin_request = Request(
                    base_url + "/api/v1/security-intelligence/research",
                    data=json.dumps({"topic": "admin-topic", "objective": "admin-objective", "source_categories": ["test"]}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as error:
                    admin_opener.open(admin_request)
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_static_dashboard_does_not_expose_legacy_role_credentials(self) -> None:
        static_dir = Path(__file__).parents[1] / "src" / "bayora" / "static"
        for name in ("index.html", "app.js"):
            content = (static_dir / name).read_text()
            self.assertNotIn("bayora-red-token", content)
            self.assertNotIn("bayora-blue-token", content)
            self.assertNotIn("bayora-admin-token", content)
            self.assertNotIn("bayora-auditor-token", content)

    def test_authenticated_account_switch_requires_new_backend_credentials(self) -> None:
        service = BayoraService(
            Settings(
                data_dir=self.root,
                bootstrap_passwords={
                    "red-analyst": "red-local-password",
                    "blue-engineer": "blue-local-password",
                },
            )
        )
        red_session = service.login("red-analyst", "red-local-password")
        blue_session = service.login("blue-engineer", "blue-local-password", red_session.token)
        self.assertEqual(service.actor_for_session(blue_session.token).role, "blue")
        with self.assertRaises(AuthenticationError):
            service.actor_for_session(red_session.token)


if __name__ == "__main__":
    unittest.main()
