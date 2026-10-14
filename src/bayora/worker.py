"""Generic isolated entry point for the provider abstraction."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from providers import LLMRequest, ProviderConfig, ProviderError, provider_from_config


def failure(code: str, message: str) -> int:
    sys.stdout.write(json.dumps({"status": "error", "code": code, "error": message}, separators=(",", ":")))
    return 3


def main() -> int:
    try:
        envelope = json.load(sys.stdin)
        if not isinstance(envelope, dict):
            return failure("invalid_request", "invalid provider worker request")
        operation = envelope.get("operation")
        config_data = envelope.get("provider_config")
        if operation not in {"health", "generate"} or not isinstance(config_data, dict):
            return failure("invalid_request", "invalid provider worker request")
        provider_name = config_data.get("provider", "fixture")
        model_name = config_data.get("model", "")
        if not isinstance(provider_name, str) or not isinstance(model_name, str):
            return failure("invalid_request", "provider configuration is invalid")
        config = ProviderConfig(
            provider=provider_name,
            base_url=config_data.get("base_url") if isinstance(config_data.get("base_url"), str) else None,
            model=model_name,
            api_key=config_data.get("api_key") if isinstance(config_data.get("api_key"), str) else None,
            timeout_seconds=float(config_data.get("timeout_seconds", 10.0)),
        )
        provider = provider_from_config(config)
        if operation == "health":
            health = provider.health()
            return_code = 0 if health.status in {"connected", "not_configured", "unavailable"} else 3
            sys.stdout.write(json.dumps({"status": "ok", "health": health.as_dict()}, separators=(",", ":")))
            return return_code

        request_data = envelope.get("request")
        if not isinstance(request_data, dict):
            return failure("invalid_request", "missing provider request")
        prompt = request_data.get("prompt")
        session_id = request_data.get("session_id")
        invocation_id = request_data.get("invocation_id")
        if not all(isinstance(value, str) and value for value in (prompt, session_id, invocation_id)):
            return failure("invalid_request", "provider request is incomplete")
        request = LLMRequest(
            prompt=prompt,
            session_id=session_id,
            invocation_id=invocation_id,
        )
        response = provider.generate(request)
        result = {"status": "ok", **response.as_dict()}
        sys.stdout.write(json.dumps(result, separators=(",", ":")))
        return 0
    except ProviderError as exc:
        return failure(exc.code, str(exc))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return failure("invalid_request", str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
