# Bayora

## Secure Adversarial AI Testing Infrastructure

Bayora is a security-focused platform for evaluating AI systems through controlled adversarial testing while maintaining isolation between testing workloads, defensive systems, and the model under evaluation.

The repository contains a runnable proof of concept with:

- tenant-aware evaluation sessions;
- explicit flow policy decisions;
- a separate, resource-limited model-provider worker process;
- private per-session workspaces with restrictive permissions;
- a hash-chained, HMAC-authenticated audit log;
- a browser dashboard for evaluations, findings, and validation results; and
- reproducible security validation checks.

## Quick start

Bayora requires Python 3.11 or newer and has no runtime dependency outside the standard library.

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
bayora validate --data-dir .bayora
bayora serve --data-dir .bayora --host 127.0.0.1 --port 8080
```

Configure at least one bootstrap password before starting the service. For a local
administrator session, for example:

```bash
export BAYORA_BOOTSTRAP_ADMIN_PASSWORD='choose-a-local-password'
```

You may also configure `BAYORA_BOOTSTRAP_RED_PASSWORD`,
`BAYORA_BOOTSTRAP_BLUE_PASSWORD`, and `BAYORA_BOOTSTRAP_AUDITOR_PASSWORD`.

For an existing local database, initialize passwords interactively without
putting them in shell history or source files:

```bash
PYTHONPATH=src python3 -m bayora.cli init-users --data-dir .bayora
```

The command asks for each missing account password and confirmation. Existing
passwords are skipped, and a running Bayora server sees successful changes
immediately. Use `--username red-analyst` (or another seeded username) to
initialize one account.

Open <http://127.0.0.1:8080>. The existing dashboard asks for the configured
credentials using the browser's native prompt, then displays the backend-provided
role. Selecting another role in the existing selector asks for that account's
backend credentials; it cannot switch identity or privileges without a successful
login for the selected account.

The default configuration is `LLM_PROVIDER=fixture`. It requires no LLM installation and labels every result **Test Fixture — Not Real Model Evidence**. Fixture output is deterministic pipeline evidence, never model evidence. Bayora supports three provider modes:

```bash
export LLM_PROVIDER=openai_compatible
export LLM_BASE_URL=https://your-model-gateway.example/v1
export LLM_MODEL=your-model-name
export LLM_API_KEY=your-provider-key
export LLM_TIMEOUT_SECONDS=10
bayora serve --data-dir .bayora --host 127.0.0.1 --port 8080
```

For optional Ollama/local inference:

```bash
export LLM_PROVIDER=ollama
export LLM_BASE_URL=http://127.0.0.1:11434
export LLM_MODEL=your-local-model
bayora serve --data-dir .bayora --host 127.0.0.1 --port 8080
```

Ollama is not installed, imported, or required by Bayora. Setting `LLM_PROVIDER=unconfigured` intentionally exercises the not-configured path and returns `llm_not_configured` rather than crashing the platform.

## TinyFish security intelligence

Security intelligence is an optional backend capability and does not change
the approved dashboard. Configure the documented TinyFish Agent API with
runtime environment variables; leaving `TINYFISH_API_KEY` blank keeps Bayora
running and reports the integration as `not_configured`.

```bash
export TINYFISH_API_KEY='your-tinyfish-api-key'
export TINYFISH_BASE_URL='https://agent.tinyfish.ai/v1'
export TINYFISH_TIMEOUT_SECONDS=30
export TINYFISH_POLL_INTERVAL_SECONDS=2
export TINYFISH_MAX_DURATION_SECONDS=120
bayora serve --data-dir .bayora --host 127.0.0.1 --port 8080
```

The initial approved categories are `nvd`, `owasp`, `atlas`, and
`huggingface`. They resolve to exact public HTTPS targets in the server
configuration. Override them only with a JSON object of approved category to
URL-array mappings in `BAYORA_INTELLIGENCE_ALLOWED_SOURCES`; arbitrary caller
URLs are never accepted. Red Team users can submit research through the
security-intelligence API. Blue Team users remain unable to create Red Team
evaluations, but can review an assessment explicitly shared with their account
and initiate a separate advisory/unverified defensive analysis from the
recorded evidence. Blue users can record remediation recommendations or
user-reported implementations; the system does not apply code changes, retest,
or verify those claims. Security Administrators and Auditors can review
evidence across tenants. See [API.md](API.md) for request and response
details.

## Architecture

```text
Browser
   |
   v
Bayora HTTP API ---- Policy engine ---- Audit chain
   |                       |
   v                       v
SQLite state          Isolated worker process
   |                       |
   v                       v
Tenant/session data   Model-under-evaluation adapter
```

The API is the only component that receives client requests. The evaluation engine depends on one `LLMProvider` interface (`health`, `generate`, and `metadata`). The provider adapter runs in a resource-limited worker and selects `FixtureProvider`, `OpenAICompatibleProvider`, or `OllamaProvider` behind that interface. Provider-specific HTTP and response parsing stay inside the adapter. Normalized responses contain text, provider, model, invocation ID, latency, usage, and evidence type; provider-specific JSON is never exposed to the evaluation service.

```text
Red Team -> Bayora policy gateway -> Evaluation service -> LLMProvider adapter -> Provider -> Model
Blue Team -> explicit assessment grant -> defensive analysis service -> LLMProvider adapter -> Provider -> Model
```

For a remote provider, the model and its execution boundary are outside Bayora. For Ollama, the endpoint is local but its process boundary is not created by Bayora; a deployment must separately isolate that runtime. Fixture output is test evidence only. A configured real provider that is unavailable is recorded as a failed evaluation; Bayora never silently changes it to fixture mode.

## Security model

Bayora treats adversarial input and stored model output as untrusted data. A
session receives an opaque identifier, a private workspace, and a tenant
context. The default policy permits `red -> llm` only when the target belongs
to the same session and tenant. An explicitly shared assessment may be supplied
to a fresh Blue defensive-analysis session; the Blue service still denies host
resources, unrelated sessions, and private data outside that grant.

The local credentials demonstrate product roles:

| Role | Purpose |
| --- | --- |
| Red Team | Creates adversarial evaluation sessions. |
| Blue Team | Represents defensive ownership boundaries. |
| Security Administrator | Runs platform validation and reviews configuration. |
| Auditor | Verifies audit integrity and evaluation provenance. |
| LLM Service | Runs behind the isolated model worker boundary. |

See [THREAT_MODEL.md](THREAT_MODEL.md), [SECURITY_MODEL.md](SECURITY_MODEL.md), and [SECURITY_GUARANTEES.md](SECURITY_GUARANTEES.md) for assumptions and measurable controls.

## Security validation

The validation command executes real application-policy and audit-chain checks:

```bash
python3 -m bayora.cli validate --data-dir /tmp/bayora-validation
```

The result covers:

```text
RED -> LLM                 ALLOW
RED -> BLUE PRIVATE DATA   BLOCK
BLUE -> RED PRIVATE DATA   BLOCK
RED -> HOST                BLOCK
CROSS-SESSION DATA        BLOCK
AUDIT TAMPERING           DETECTED
```

The policy controls do not claim a host-kernel sandbox boundary. Fixture mode also exercises the provider adapter without requiring a model runtime. The audit tampering result is produced by altering an in-memory copy of a signed record and verifying that the chain rejects it. The persistent audit log is not modified by the check.

## Real provider validation

After starting with the remote provider configuration, check `GET /api/v1/provider/status` or the dashboard. `CONNECTED` is returned only after an actual provider health request, authentication check, and model-catalog check when the endpoint advertises a catalog. The health response never contains the endpoint or credential.

Run the real canary through the Red Team evaluation API:

```bash
curl -c bayora.cookies -X POST http://127.0.0.1:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"red-analyst","password":"configured-password"}'

curl -b bayora.cookies -X POST http://127.0.0.1:8080/api/v1/evaluations \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Respond with exactly:\n\nBAYORA_REAL_LLM_CANARY_638291\n\nDo not add anything else."}'
```

`completed` is valid only when the configured provider returned non-empty response text. A refusal is still a real response. If the provider cannot be reached, the result is `failed` with a safe error such as `llm_unavailable`, `llm_timeout`, `llm_authentication_failed`, or `llm_model_unavailable`. No provider response means no `evaluation_completed` event.

The normal test suite uses mocked HTTP endpoints. The opt-in real-provider test runs only when `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL`, and `LLM_MODEL` are explicitly present:

```bash
PYTHONPATH=src python3 -m unittest tests.test_real_provider_integration -v
```

## API overview

Authentication is password-backed and session-cookie based. Configure bootstrap
passwords through environment variables rather than placing credentials in source,
HTML, JavaScript, request URLs, or documentation.

Create an evaluation:

```bash
curl -b bayora.cookies -X POST http://127.0.0.1:8080/api/v1/evaluations \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Evaluate refusal behavior for a benign policy probe."}'
```

Inspect the evaluation, list security findings, or verify the audit chain with:

```bash
curl -b bayora.cookies http://127.0.0.1:8080/api/v1/evaluations
curl -b bayora.cookies http://127.0.0.1:8080/api/v1/findings
curl -b bayora.cookies http://127.0.0.1:8080/api/v1/audit/verify
```

The complete route and payload reference is in [API.md](API.md).

## Deployment

Docker is the only host prerequisite for the default deployment. No Python, Node.js, database server, or Ollama installation is needed.

```bash
cp .env.example .env
docker compose up --build
```

Open <http://localhost:8080>. The default Compose environment uses the deterministic fixture and displays `Test Fixture — Not Real Model Evidence`.

Verify the complete containerized path with:

```bash
BAYORA_SMOKE_ADMIN_PASSWORD='configured-admin-password' \
BAYORA_SMOKE_RED_PASSWORD='configured-red-password' \
BAYORA_SMOKE_AUDITOR_PASSWORD='configured-auditor-password' \
bash scripts/smoke-test.sh
```

The smoke test logs in through the same cookie-based authentication used by the
dashboard. The smoke-test variables must match the bootstrap passwords supplied
when the container was initialized; they are never written to the repository.

The container drops Linux capabilities, uses a non-root user, stores state in separate named volumes, and applies memory, CPU, PID, and filesystem restrictions. See [DEPLOYMENT.md](DEPLOYMENT.md), [DOCKER_SECURITY.md](DOCKER_SECURITY.md), and [CONTAINER_SECURITY.md](CONTAINER_SECURITY.md).

Run the actual Red/Blue network separation checks with:

```bash
bash scripts/container-security-test.sh
```

## Testing

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

The test suite covers tenant boundaries, policy decisions, worker isolation properties, resource validation, audit tamper detection, and API authorization.

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — component boundaries and trust zones
- [THREAT_MODEL.md](THREAT_MODEL.md) — assets, actors, threats, and assumptions
- [SECURITY_MODEL.md](SECURITY_MODEL.md) — enforcement rules and roles
- [NETWORK_SECURITY.md](NETWORK_SECURITY.md) — network exposure and egress posture
- [CONTAINER_SECURITY.md](CONTAINER_SECURITY.md) — container hardening
- [DOCKER_SECURITY.md](DOCKER_SECURITY.md) — Docker trust zones and workload checks
- [LLM_SECURITY.md](LLM_SECURITY.md) — model session controls
- [AUDIT_ARCHITECTURE.md](AUDIT_ARCHITECTURE.md) — integrity chain and provenance
- [DATA_FLOW.md](DATA_FLOW.md) — request and data movement
- [TESTING.md](TESTING.md) — reproducible verification
- [DEPLOYMENT.md](DEPLOYMENT.md) — local and container operation
- [API.md](API.md) — HTTP API
- [RESIDUAL_RISK.md](RESIDUAL_RISK.md) — known limitations
- [SECURITY_GUARANTEES.md](SECURITY_GUARANTEES.md) — guarantees and evidence
