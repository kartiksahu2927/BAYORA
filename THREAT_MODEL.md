# Bayora Threat Model

## Assets

- evaluation prompts and model responses;
- role-private defensive and adversarial data;
- tenant and session identifiers;
- policy decisions and security findings;
- audit provenance and the audit signing key;
- host and container resources.

## Relevant actors

| Actor | Capability | Security concern |
| --- | --- | --- |
| Red Team | Supplies adversarial prompts | Prompt abuse, data probing, resource exhaustion |
| Blue Team | Owns defensive material | Accidental disclosure across role boundaries |
| Security Administrator | Changes platform settings | Excessive authority and unsafe configuration |
| Auditor | Reads provenance and integrity state | Unauthorized access to evaluation data |
| Model adapter | Processes evaluation input | Session confusion and output abuse |
| Host operator | Runs the service | Key theft, process escape, storage tampering |

## Threats addressed

- cross-tenant reads are rejected before storage access;
- cross-session data requests are rejected by the policy engine;
- host access is not granted to evaluation flows;
- evaluation input is bounded and runs in a separate child process;
- credentials are absent from the worker environment;
- audit record alteration is detected through a keyed chain;
- tenant-scoped API reads prevent one tenant from viewing another tenant's sessions.

## Assumptions

The host kernel, Python runtime, container runtime, and audit key storage are trusted. Local password-backed sessions are a minimal deployment credential layer, not a complete identity provider; production deployments still require an external identity provider and MFA. The deterministic model adapter is a fixture for control verification and does not represent the safety behavior of a production model.
