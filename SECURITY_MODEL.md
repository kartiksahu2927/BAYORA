# Bayora Security Model

## Authorization

Every API route except `/healthz` and static assets requires an authenticated,
server-managed session cookie. The session resolves to an actor with a role and
tenant; client-selected role labels are not trusted. Review routes are limited to
Security Administrator and Auditor roles. Evaluation reads are tenant-scoped for
Red Team actors; Blue Team reads are tenant-scoped plus explicit per-assessment
grants to the authenticated Blue account. Blue defensive analysis history is
private to authorized Blue, Administrator, and Auditor actors. Missing or
invalid sessions return `401`, while authenticated actors without a required
permission return `403` (or a resource-scoped `404` where existence must not be
disclosed).

## Information-flow policy

The policy engine uses a default-deny decision function. A flow includes:

- source role;
- destination class;
- resource class;
- source tenant;
- source session;
- optional target tenant and session.

Only a Red Team evaluation flow to the LLM adapter with matching tenant and
session is allowed by default. An explicitly authorized Blue defensive-analysis
flow may reach the LLM adapter through a fresh Blue analysis session with
matching analysis tenant and session. The service checks the assessment grant
before composing source evidence. Private role data, host resources, and other
sessions remain blocked.

## Data minimization

Evaluation records retain prompt length and a SHA-256 prompt digest for
provenance. New assessments also retain the original prompt in a separate
protected evidence table so an authorized Blue reviewer can examine the actual
test input; list responses and audit records contain no raw prompt. Older
assessments without that evidence report it as unavailable. Source responses
and Blue analysis outputs remain protected application data. Production
deployments should use encrypted storage and a retention policy for prompt,
response, analysis, and remediation evidence.

## Failure behavior

Malformed input, missing identity, failed policy checks, worker errors, and audit verification failures fail closed at their respective boundaries. API errors do not return stack traces or request bodies.
