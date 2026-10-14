# Deployment

## Local process

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
bayora serve --data-dir /var/lib/bayora --host 127.0.0.1 --port 8080
```

The data directory contains the SQLite database, the owner-only audit key, and session workspaces. Back it up using storage encryption and preserve the audit key with the database if historical verification is required.

## Provider modes

Bayora starts in fixture mode without a model runtime:

```bash
LLM_PROVIDER=fixture bayora serve --data-dir /var/lib/bayora --host 127.0.0.1 --port 8080
```

Remote mode uses `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY`. `LLM_BASE_URL` may be the API root (for example `/v1`) or the full `/chat/completions` endpoint. Bayora sends one isolated user message with the configured model, and does not send Bayora session metadata, tenant data, credentials, or role-private data to the provider.

```bash
LLM_PROVIDER=openai_compatible \
LLM_BASE_URL=https://model-gateway.example/v1 \
LLM_API_KEY=replace-with-a-secret \
LLM_MODEL=your-model \
LLM_TIMEOUT_SECONDS=10 \
bayora serve --data-dir /var/lib/bayora --host 127.0.0.1 --port 8080
```

`LLM_TIMEOUT_SECONDS` bounds each provider operation. `BAYORA_WORKER_TIMEOUT_SECONDS` optionally changes the outer worker deadline; the default is 15 seconds and is kept at least one second longer than the provider timeout. Connection errors, authentication errors, invalid models, malformed responses, and timeouts keep the control plane running and create failed evaluation records.

Local Ollama mode uses `LLM_PROVIDER=ollama`, `LLM_BASE_URL`, and `LLM_MODEL`. Ollama is optional and is not part of the Bayora installation or container image. If a provider is unavailable, the control plane remains available and an evaluation is recorded as failed. Bayora does not automatically switch an explicitly configured real provider to the fixture.

Use `LLM_PROVIDER=unconfigured` to exercise the explicit no-provider path. It reports `NOT CONFIGURED` in health status and `llm_not_configured` for evaluations. Leaving `LLM_PROVIDER` unset continues to select the default fixture.

`GET /api/v1/provider/status` performs a live health request in the isolated worker. For an OpenAI-compatible provider it requests `/models`, validates authentication, and checks the configured model when the catalog is advertised. A model catalog that is not exposed is reported as reachable with availability verified during generation. Health output is safe for the UI and never includes `LLM_BASE_URL` or `LLM_API_KEY`.

## Container

```bash
cp .env.example .env
docker compose up --build -d
docker compose logs -f bayora
```

The default Compose profile starts one Bayora service with embedded SQLite and audit storage. It binds the service to loopback, gives database, audit, and application state separate named volumes, and applies the controls described in [DOCKER_SECURITY.md](DOCKER_SECURITY.md). Set bootstrap passwords in `.env` for local access; replace this local password layer with an external identity provider and enable secure cookies before exposing the service to a network.

The service is healthy when `/healthz` responds. Since SQLite is owned by the Bayora process, there is no separate database container or database startup race in the default profile.

## Container profiles

The Red/Blue workload checks are opt-in:

```bash
docker compose --profile security-tests up --build
bash scripts/container-security-test.sh
```

The optional Ollama container is also opt-in:

```bash
LLM_PROVIDER=ollama \
LLM_BASE_URL=http://ollama:11434 \
LLM_MODEL=your-local-model \
docker compose --profile local-llm up --build
```

The local provider image does not download model weights automatically. Model requirements depend on the selected model; as a planning baseline, reserve at least 8 GB RAM for small quantized models, additional disk for weights, and GPU memory only when the selected image and host runtime support it. The default fixture uses no model memory, VRAM, or disk.

## Operations

- Monitor `/healthz` and process resource usage.
- Run `bayora validate` after changing policy or runtime configuration.
- Verify the audit chain before exporting evaluation evidence.
- Treat fixture results as **Test Fixture — Not Real Model Evidence**; only a real provider response creates real-model evidence.
- Confirm the result's provider, model, latency, response hash, and session-scoped audit references before accepting an evaluation.
- Restrict access to `audit.key` and the state directory.
- Retain only the evaluation data required for the defined review period.
- Run `BAYORA_SMOKE_ADMIN_PASSWORD=... BAYORA_SMOKE_RED_PASSWORD=... BAYORA_SMOKE_AUDITOR_PASSWORD=... bash scripts/smoke-test.sh` after a clean build. The values must match the configured local account passwords.

## Troubleshooting provider failures

| Symptom | Meaning | Action |
| --- | --- | --- |
| `NOT CONFIGURED` / `llm_not_configured` | No provider was selected for the request | Set `LLM_PROVIDER` and the required provider variables, or use the default fixture intentionally. |
| `UNAVAILABLE` / `llm_unavailable` | Endpoint could not be reached | Check the URL, routing, firewall, and provider process. |
| `Authentication failure` / `llm_authentication_failed` | The provider rejected credentials | Replace the environment-provided secret; do not put it in a request or audit record. |
| `llm_model_unavailable` | Endpoint or configured model was not found | Confirm the model catalog and exact `LLM_MODEL` value. |
| `llm_timeout` | The provider exceeded its request deadline | Check provider load and increase `LLM_TIMEOUT_SECONDS` within an acceptable operational bound. |
| `llm_invalid_response` | The endpoint did not return the required chat/completions shape | Confirm the endpoint implements the OpenAI-compatible response contract. |
