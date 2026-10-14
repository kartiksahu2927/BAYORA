# Audit Architecture

Audit events are stored in SQLite with an append sequence, event type, actor, tenant, optional session, canonical payload JSON, previous digest, digest, and UTC timestamp.

The digest is an HMAC-SHA256 over the complete record and the previous digest. The signing key is generated once in `audit.key`, stored with owner-only permissions, and never exposed through the API. Verification walks records in sequence and checks both the previous link and the keyed digest.

The security validation path mutates an in-memory copy of a record. A changed payload produces a digest mismatch, yielding the `AUDIT TAMPERING / DETECTED` control result while preserving the persistent chain.

SQLite is suitable for a single-node proof of concept. A production deployment should stream events to append-only, access-controlled storage and rotate keys with an external key-management service. Key rotation needs an explicit versioned verification scheme before being enabled.
