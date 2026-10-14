# Container Security

The supplied container configuration provides a baseline execution profile:

- non-root UID 10001;
- dropped Linux capabilities;
- `no-new-privileges`;
- read-only root filesystem;
- a dedicated writable state volume;
- a `noexec`, `nosuid`, `nodev` temporary filesystem;
- process and memory limits; and
- no package installed beyond the Python runtime and Bayora.

The worker also applies CPU, address-space, file-size, and open-file limits on POSIX hosts. These limits are defense in depth, not a complete sandbox. A production deployment should run untrusted adapters in a separately managed sandbox with a hardened kernel profile, seccomp, mandatory access controls, and independent lifecycle management.

The concrete Compose topology and executable checks are documented in [DOCKER_SECURITY.md](DOCKER_SECURITY.md). The default profile does not start Red, Blue, or Ollama containers; those profiles are opt-in so a clean Docker host can run fixture mode without a model runtime.
