# Bayora API

The API is served under `/api/v1`. All protected API requests require an authenticated
server-managed session cookie. The browser receives this `HttpOnly` cookie after login;
role labels and client-side state are never accepted as authorization.

## Authentication

`POST /api/v1/auth/login` accepts a configured username and password:

```json
{"username":"security-admin","password":"configured-password"}
```

On success it returns the authenticated actor and sets the `bayora_session` cookie.
The session is opaque, expires according to `BAYORA_SESSION_TTL_SECONDS`, and is
revoked by `POST /api/v1/auth/logout`. Password hashes are initialized only for users
without an existing hash from the corresponding `BAYORA_BOOTSTRAP_*_PASSWORD`
environment variable; existing passwords are never overwritten at startup.

## Identity

`GET /api/v1/me` returns the authenticated actor, tenant, and role.

## Evaluations

`POST /api/v1/evaluations` is available to Red Team roles.

```json
{"prompt":"Evaluate refusal behavior for a benign policy probe."}
```

The response includes an evaluation identifier, tenant, session identifier, state, policy decision, normalized model metadata, response text on success, error metadata on failure, latency/usage metadata, and session-scoped audit event references. Prompt content is not included in list responses; new assessments retain it in a separate protected evidence record for authorized assessment detail. `completed` is returned only after the configured provider has returned non-empty response text and that response has been persisted.

The normalized model shape is:

```json
{
  "provider": "openai_compatible",
  "name": "configured-or-provider-model",
  "invocation_id": "opaque-id",
  "evidence_type": "real_model"
}
```

Successful real results also contain `latency_ms`, provider-reported numeric `usage` when available, `response_sha256`, and `response`. Fixture results use `provider: "fixture"`, `name: "bayora-deterministic-fixture"`, `evidence_type: "test_fixture"`, and the warning **Test Fixture — Not Real Model Evidence**. They must not be interpreted as model evidence.

When no provider is configured, the request returns a normal evaluation record with state `failed` and error code `llm_not_configured`; it does not claim a successful model run. If a real provider is selected but unavailable, Bayora returns `failed` with a provider-specific safe error and never falls back to the fixture.

`GET /api/v1/evaluations` lists the caller's tenant sessions. Blue Team actors also see assessments explicitly shared with their exact account. Security Administrator and Auditor roles can review all stored sessions.

`GET /api/v1/evaluations/{id}` returns one session subject to the same access rule. Detail includes recorded source evidence when available: the original prompt, target response, policy result, findings, and model provenance. Older records without retained source evidence report `prompt_available: false`; Bayora never reconstructs a prompt from its digest.

## Findings

`GET /api/v1/findings` returns policy findings visible to the caller's role, tenant, or explicit Blue assessment grant.

## Blue Team assessment review

Blue Team users do not create Red Team evaluations. A Red assessment owner or
Security Administrator can explicitly share a terminal assessment with one
Blue account:

`GET /api/v1/blue-team/recipients` returns eligible Blue account identifiers to
Red and Administrator roles. `POST /api/v1/evaluations/{id}/blue-team-access`
accepts `{"blue_actor_id":"blue-engineer"}`. Sharing grants access to that
assessment only; it does not copy data to another tenant or start analysis.

An authorized Blue user can initiate defensive analysis without re-entering
stored evidence through `POST /api/v1/evaluations/{id}/blue-analyses`:

```json
{"instructions":"Focus on evidence-supported input validation risks."}
```

The backend retrieves the original prompt (when available), target response,
policy result, findings, and model metadata. These are supplied to the
configured provider as untrusted review data. The output is persisted as
`advisory_unverified` with `remediation_status: recommended`; `implemented`,
`retested`, and `verified` are always false. Provider failures are persisted as
failed analysis records rather than reported as successful analysis.

`GET /api/v1/evaluations/{id}/blue-analyses` returns history to authorized Blue,
Administrator, and Auditor actors. Red actors cannot read Blue defensive
analysis history.

`GET /api/v1/evaluations/{id}/remediations` returns separate remediation notes
to those review roles. Blue users can record `recommended` notes or an
`implemented` user report with supporting evidence through the matching POST
route. These records explicitly remain `retested: false` and `verified: false`;
Bayora does not apply code changes or claim a fix from a recommendation or
user-reported implementation.

## Controls

`GET /api/v1/policy` returns the active information-flow matrix.

`GET /api/v1/provider/status` performs a live provider health check and returns the configured provider display name, model display name, safe status (`CONNECTED`, `UNAVAILABLE`, or `NOT_CONFIGURED`), and human-readable safe reason. OpenAI-compatible health checks use the model catalog where available to verify authentication and model availability. It never returns provider URLs, API keys, or host environment values.

`POST /api/v1/security/validation` runs the six reproducible control checks. Security Administrator and Auditor roles may invoke it. The fixture worker is invoked by validation only when fixture mode is selected; a real provider is never invoked as an implicit validation substitute.

`GET /api/v1/audit/verify` verifies the complete HMAC chain and returns its record count. Security Administrator and Auditor roles may invoke it.

## Security intelligence

Bayora can optionally use the TinyFish Agent API to collect authorized
security intelligence from an administrator-configured allowlist of public
HTTPS sources. TinyFish is an execution service only; Bayora performs the
authorization, source checks, tenant checks, result validation, persistence,
and audit logging. Retrieved page content is untrusted and is labeled as such
in evidence provenance.

`GET /api/v1/security-intelligence/status` returns whether the integration is
`configured` or `not_configured`, the approved source categories, and the
maximum result count. It never returns the TinyFish endpoint or API key.

`POST /api/v1/security-intelligence/research` is available to Red Team roles
and returns `202 Accepted` with a persisted task record. The task executes
asynchronously and has one of `PENDING`, `RUNNING`, `COMPLETED`, or `FAILED`.

```json
{
  "topic": "prompt injection defenses",
  "objective": "Collect recent public guidance and mitigations.",
  "source_categories": ["owasp", "atlas"],
  "max_results": 5,
  "evaluation_session_id": "optional-authorized-session-id",
  "correlation_id": "optional-idempotency-correlation"
}
```

The source categories are resolved server-side to exact approved HTTPS URLs;
the caller cannot submit an arbitrary URL. Repeating the same request in the
same tenant returns the existing task instead of starting a duplicate task.

`GET /api/v1/security-intelligence/tasks` lists tasks visible to the caller.
`GET /api/v1/security-intelligence/tasks/{task_id}` returns one authorized
task and status. `GET /api/v1/security-intelligence/tasks/{task_id}/results`
returns normalized evidence for an authorized task. Red and Blue Team users
are tenant-scoped; Security Administrators and Auditors may review all task
records and evidence but cannot initiate research through these endpoints.

TinyFish uses `POST /v1/automation/run-async` followed by
`GET /v1/runs/{run_id}` with the `X-API-Key` header. A TinyFish `COMPLETED`
run is not by itself treated as successful: Bayora requires usable normalized
findings. TinyFish credentials and raw provider responses are never returned
to clients or written to audit payloads.

Bayora validates configured source URLs as HTTPS, exact allowlisted targets,
and publicly routable at submission time, and disables HTTP redirects in its
own API client. Because browser navigation runs in TinyFish's remote service,
Bayora cannot independently observe or revalidate every remote DNS lookup or
redirect; the research goal also instructs the remote agent to stay on the
approved source. This residual remote-egress limitation must be addressed with
TinyFish-side network controls before production use.

## Health and errors

`GET /healthz` does not require authentication and returns a minimal service status; it does not claim that the LLM provider is healthy. Use `/api/v1/provider/status` for a live provider check. Error bodies have the form `{"error":"message"}`. Missing or invalid sessions return `401`; authenticated actors without the required role return `403`. Request bodies are bounded to 256 KiB by default, and prompts are bounded to 12,000 characters.

## Audit lifecycle

For a successful evaluation, session-scoped audit references appear in this order:

```text
evaluation_created
policy_checked
llm_invocation
llm_response_received
evaluation_completed
```

For a provider failure, the final two events are `llm_request_failed` and `evaluation_failed`; `evaluation_completed` is never written. Audit events include timestamps, provider/model identifiers, invocation IDs, policy decisions, response hashes, and lengths where applicable. Credentials and raw prompt content are excluded. Assessment sharing, Blue evidence review, defensive analysis, and remediation events record assessment identifiers and digests rather than raw prompts, instructions, responses, or notes.
