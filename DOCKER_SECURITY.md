# Docker Security

Docker is a deployment boundary for Bayora, not a claim of complete host isolation.

## Default control plane

The `bayora` container runs the HTTP control plane, dashboard, SQLite state, audit chain, and isolated provider worker. It uses:

- a non-root UID;
- `cap_drop: ALL`;
- `no-new-privileges`;
- a read-only root filesystem;
- a `noexec`, `nosuid`, `nodev` temporary filesystem;
- explicit CPU, memory, and PID limits;
- no host mounts;
- no Docker socket; and
- a container init process for child reaping.

The writable state is split into database, audit-key, and application workspace volumes. Audit records remain in the SQLite database; the signing key is stored in a separate audit volume.

## Network topology

The control plane is attached to separate internal networks for Red Team access, Blue Team access, the optional local provider, and audit storage. Red and Blue workloads are never attached to the same network. The control plane is the trusted gateway between those zones.

Remote provider egress is a separate network attached only to Bayora. Red and Blue workload containers cannot use that network directly.

## Workload profile

The `security-tests` profile starts small Red and Blue workload containers. They are non-root, read-only, capability-free, PID-limited, memory-limited, and attached to separate networks. They do not receive host mounts or `/var/run/docker.sock`.

Run the actual network and hardening checks with:

```bash
bash scripts/container-security-test.sh
```

## Boundary limitations

- Linux namespaces isolate process, filesystem, network, and mount views but depend on the host kernel.
- Dropped capabilities reduce privilege but do not make a container equivalent to a VM.
- `no-new-privileges` prevents privilege escalation through executable transitions but does not remove kernel vulnerabilities.
- Read-only filesystems constrain writes but do not prevent all memory or CPU abuse.
- Resource limits constrain normal exhaustion paths but are not a complete denial-of-service solution.
- Docker daemon, kernel, image provenance, and host configuration remain trusted deployment dependencies.
