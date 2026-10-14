# Testing and Reproducibility

Install the package in editable mode and run the focused suite:

```bash
python3 -m pip install -e .
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Run the end-to-end control check with a fresh state directory:

```bash
python3 scripts/security_validation.py /tmp/bayora-validation
```

The test suite verifies:

- allowed and denied policy paths;
- tenant-scoped evaluation reads;
- owner-only session workspaces;
- explicit provider selection and fixture labeling;
- mocked OpenAI-compatible health, model discovery, request translation, normalized response metadata, authentication, timeout, invalid-model, and unavailable-endpoint paths;
- configured provider contract, worker process output, and bounds;
- audit mutation detection;
- evaluation lifecycle and audit ordering for success and provider failures;
- application session isolation and credential non-disclosure;
- all six validation controls; and
- API authentication behavior;
- explicit Red-to-specific-Blue assessment sharing;
- Blue defensive analysis persistence, authorization, evidence boundaries, and
  advisory-only result states; and
- user-reported remediation notes that remain untested and unverified.

The provider contract tests use local mocked OpenAI-compatible HTTP servers. They verify request routing, response persistence, API serialization, health behavior, failure classification, and audit ordering; they are not evidence that a real external model was available. A real-provider run requires the environment variables described in [README.md](README.md). The opt-in integration test is skipped unless `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL`, and `LLM_MODEL` are explicitly configured.

Run the real-provider test only when a real endpoint is intentionally configured:

```bash
PYTHONPATH=src python3 -m unittest tests.test_real_provider_integration -v
```

Its canary prompt is:

```text
Respond with exactly:

BAYORA_REAL_LLM_CANARY_638291

Do not add anything else.
```

The test passes only after an actual non-empty response from the configured provider. A refusal is still a real response; an unavailable or unauthenticated provider is a failed evaluation, not fixture evidence.

For a deployment review, repeat the validation after container startup, inspect the audit verification endpoint, and confirm that the published port is not reachable beyond the intended network boundary.

## Container checks

From a clean Docker host:

```bash
docker compose down -v
docker compose build --no-cache
docker compose up -d
bash scripts/smoke-test.sh
bash scripts/container-security-test.sh
```

The smoke script exercises the fixture through the running container, including the dashboard asset, provider status, evaluation persistence, audit verification, and security validation. The container security script starts the opt-in Red and Blue workloads and tests their separate Docker networks, gateway reachability, provider-network denial, non-root hardening, read-only roots, capability drops, PID/memory limits, no-new-privileges, and Docker socket absence.
