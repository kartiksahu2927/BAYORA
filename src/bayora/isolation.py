"""Process and filesystem boundary for the model-under-evaluation adapter."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .providers import LLMProvider, LLMRequest, LLMResponse, ProviderConfig, ProviderError, ProviderHealth, provider_from_config


class WorkerError(RuntimeError):
    """Raised when the constrained worker cannot complete safely."""

    def __init__(self, message: str, code: str = "worker_error"):
        super().__init__(message)
        self.code = code


def create_workspace(root: Path, session_id: str) -> Path:
    if not session_id.isalnum() or len(session_id) > 80:
        raise ValueError("invalid session identifier")
    workspace = root / session_id
    workspace.mkdir(mode=0o700)
    workspace.chmod(stat.S_IRWXU)
    return workspace


def _apply_limits() -> None:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
        resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
        os.setsid()
    except (ImportError, AttributeError, OSError, ValueError):
        # Windows and restricted runtimes use the parent timeout and container limits.
        return


def _run_provider_worker(
    workspace: Path,
    config: ProviderConfig,
    operation: str,
    request: LLMRequest | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"operation": operation, "provider_config": config.as_worker_dict()}
    if request is not None:
        payload["request"] = {
            "prompt": request.prompt,
            "session_id": request.session_id,
            "invocation_id": request.invocation_id,
        }
    encoded_request = json.dumps(payload, separators=(",", ":"))
    worker_path = Path(__file__).with_name("worker.py")
    environment = {"PYTHONIOENCODING": "utf-8"}
    try:
        completed = subprocess.run(
            [sys.executable, "-I", str(worker_path)],
            input=encoded_request,
            text=True,
            capture_output=True,
            cwd=workspace,
            env=environment,
            timeout=timeout_seconds,
            check=False,
            close_fds=True,
            preexec_fn=_apply_limits if os.name == "posix" else None,
        )
    except subprocess.TimeoutExpired as exc:
        raise WorkerError("model provider exceeded its time budget", "llm_timeout") from exc
    except (OSError, ValueError) as exc:
        raise WorkerError("model worker could not be started", "worker_launch_failed") from exc
    if completed.returncode != 0:
        try:
            failure = json.loads(completed.stdout)
        except json.JSONDecodeError:
            failure = {}
        if isinstance(failure, dict) and failure.get("status") == "error":
            raise WorkerError(str(failure.get("error", "model provider failed")), str(failure.get("code", "llm_failure")))
        raise WorkerError("model worker exited without a valid result", "worker_failure")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise WorkerError("model worker returned malformed output", "worker_malformed_output") from exc
    if not isinstance(result, dict) or result.get("status") != "ok":
        raise WorkerError("model worker returned an invalid result", "worker_invalid_result")
    if operation == "generate" and (not isinstance(result.get("response"), str) or not result["response"].strip()):
        raise WorkerError("model provider returned no response text", "llm_empty_response")
    return result


class IsolatedLLMProvider(LLMProvider):
    """Provider adapter that keeps provider execution behind a child process."""

    def __init__(self, config: ProviderConfig, workspace_root: Path, workspace: Path | None = None, timeout_seconds: float = 4.0):
        self.config = config
        self.workspace_root = workspace_root
        self.workspace = workspace
        self.timeout_seconds = timeout_seconds

    def metadata(self) -> dict[str, Any]:
        try:
            return provider_from_config(self.config).metadata()
        except ProviderError:
            return {
                "provider": self.config.provider,
                "display_name": "Unavailable Provider",
                "model": self.config.model or "—",
                "external": False,
            }

    def supports_offline_validation(self) -> bool:
        try:
            return provider_from_config(self.config).supports_offline_validation()
        except ProviderError:
            return False

    def health(self) -> ProviderHealth:
        workspace, holder = ephemeral_workspace(self.workspace_root, "provider-health-")
        try:
            result = _run_provider_worker(workspace, self.config, "health", None, self.timeout_seconds)
            health = result.get("health")
            if not isinstance(health, dict):
                return ProviderHealth("unavailable", "provider returned invalid health data")
            return ProviderHealth(str(health.get("status", "unavailable")), str(health.get("message", "provider unavailable")))
        except WorkerError as exc:
            return ProviderHealth("unavailable", str(exc))
        finally:
            holder.cleanup()

    def generate(self, request: LLMRequest) -> LLMResponse:
        if self.workspace is None:
            raise ProviderError("evaluation workspace is not configured", "worker_configuration_error")
        try:
            result = _run_provider_worker(self.workspace, self.config, "generate", request, self.timeout_seconds)
        except WorkerError as exc:
            raise ProviderError(str(exc), exc.code) from exc
        try:
            return LLMResponse(
                text=str(result["response"]),
                provider=str(result["provider"]),
                model=str(result["model"]),
                invocation_id=str(result["invocation_id"]),
                latency_ms=float(result["latency_ms"]) if result.get("latency_ms") is not None else None,
                usage=result.get("usage") if isinstance(result.get("usage"), dict) else {},
                evidence_type=str(result.get("evidence_type", "real_model")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("provider returned incomplete response metadata", "llm_invalid_response") from exc


def remove_workspace(workspace: Path) -> None:
    if workspace.exists():
        shutil.rmtree(workspace)


def ephemeral_workspace(root: Path, prefix: str = "validation-") -> tuple[Path, tempfile.TemporaryDirectory[str]]:
    holder = tempfile.TemporaryDirectory(prefix=prefix, dir=root)
    path = Path(holder.name)
    path.chmod(0o700)
    return path, holder
