# Data Flow

## Evaluation

```text
Actor -> API: authenticated session cookie + bounded JSON
API -> Auth: actor, role, tenant
API -> Policy: source, destination, resource, tenant, session
Policy -> Worker: allowed prompt only
Worker -> API: bounded model result
API -> SQLite: digest metadata, protected source evidence, and result state
API -> Audit chain: state transition and control decision
```

## Denied access

Requests for Blue Team private data, Red Team private data, host resources,
another tenant without an explicit assessment grant, or another session stop at
the policy function. A Blue review of a Red assessment is only possible after
the Red owner or an Administrator creates an explicit per-assessment access
grant; the service authorizes that grant before retrieving source evidence. No
protected-resource query is performed for a denied decision.

## Storage classes

| Data | Location | Boundary |
| --- | --- | --- |
| Prompt digest and length | SQLite evaluation record | Tenant-scoped |
| Original prompt | SQLite protected evidence record | Authorized assessment detail only |
| Model result metadata | SQLite evaluation record | Tenant-scoped |
| Blue analysis/remediation | SQLite Blue workflow records | Exact assessment grant and review roles |
| Audit event metadata | SQLite audit table | Review roles |
| Audit key | Owner-only file | Host operator |
| Temporary worker files | Session workspace | Owner-only process |
