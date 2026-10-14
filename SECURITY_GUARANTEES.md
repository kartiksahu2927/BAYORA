# Security Guarantees and Evidence

| Guarantee | Mechanism | Evidence |
| --- | --- | --- |
| Evaluation input reaches only its authorized model flow | Default-deny policy with tenant and session matching | Policy tests and validation control |
| Private role data is not exposed by the control plane | Destination-specific deny rules | Validation controls and findings table |
| Host access is not part of an authorized evaluation flow | Explicit application-policy host deny rule and restricted worker cwd | Policy test and worker profile; not a host-kernel sandbox claim |
| Sessions have separate filesystem paths | Opaque IDs and owner-only directories | Workspace test |
| Worker resources are bounded | CPU, memory, file, descriptor, timeout limits | Isolation implementation and container quotas |
| Audit alteration is observable | HMAC chain with previous-digest links | Audit mutation test and validation control |
| Tenant reads are scoped | Actor tenant check before serialization | Service/API tests |
| Evaluation provenance is reproducible | Prompt digest, state events, fixed validation cases | Audit records and validation output |

The guarantees depend on the assumptions in [THREAT_MODEL.md](THREAT_MODEL.md) and the limitations in [RESIDUAL_RISK.md](RESIDUAL_RISK.md).
