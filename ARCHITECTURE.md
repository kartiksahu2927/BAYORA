# Bayora Architecture

Bayora is organized around four trust zones:

1. **Control plane** — authenticates an actor, validates request shape, and exposes the API and dashboard.
2. **Policy and provenance plane** — makes information-flow decisions, persists tenant-scoped state, and signs audit events.
3. **Evaluation plane** — creates an opaque session and invokes a constrained model adapter in a separate process.
4. **Protected resources** — host resources, other tenants, other sessions, and role-private data. These are deny-by-default.

## Request path

1. The HTTP handler enforces a bounded body size and server-managed session authentication.
2. The service resolves the actor and tenant before reading evaluation state.
3. The policy engine evaluates source, destination, resource, tenant, and session identifiers.
4. An allowed model request is sent to `worker.py` through a pipe. The worker has a private working directory, a sanitized environment, and operating-system resource limits. It either invokes the configured OpenAI-compatible endpoint or fails closed when no provider is available.
5. The response is persisted before `evaluation_completed` is recorded. State transitions and control decisions are recorded as HMAC-linked audit events. Raw prompts are not placed in the audit payload.

## Trust boundaries

The browser is untrusted. The API is trusted to enforce authorization. SQLite is an integrity-sensitive state store. The model worker is treated as a separate workload even though it is launched by the API process. The worker receives only the prompt data needed for the current session and no platform token.

## Scaling path

The process adapter can be replaced by a container or remote model adapter. The replacement must accept a session-scoped request, return a bounded response, and preserve policy and audit calls in the control plane. Tenant state should move to a managed database and audit records to append-only storage before multi-node operation.
