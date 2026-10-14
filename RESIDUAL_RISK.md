# Residual Risk

Bayora's proof of concept demonstrates control flow and evidence generation. The following risks remain:

- Bootstrap passwords are intended for local deployment setup. Production deployments still need an external identity provider, MFA, password lifecycle, rate limiting, and TLS termination; set `BAYORA_SESSION_COOKIE_SECURE=1` behind HTTPS.
- The worker process boundary is not a complete hostile-code sandbox. A production untrusted adapter needs a separate container or VM boundary and kernel hardening.
- SQLite and the local audit key are single-node assets. A privileged host operator can alter or delete both.
- The deterministic provider is a pipeline fixture and does not measure the safety of a real model. Real model behavior depends on the configured OpenAI-compatible endpoint.
- The HTTP server is intentionally minimal and should sit behind a hardened TLS reverse proxy for shared use.
- Response retention, key rotation, backup encryption, and alert routing require deployment-specific policy.
- Resource limits are operating-system dependent; container-level quotas must remain enabled.

These limitations are explicit so that a security review can separate demonstrated guarantees from deployment assumptions.
