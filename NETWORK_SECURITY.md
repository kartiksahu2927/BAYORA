# Network Security

The local server binds to `127.0.0.1` by default. Container operation exposes port 8080 only on the loopback interface in the supplied compose file. A reverse proxy should terminate TLS, apply identity-aware access control, and restrict the API to approved operators before a shared deployment.

The Compose topology uses separate internal `red-control`, `blue-control`, `llm`, and `audit` networks. Red and Blue workload containers are attached to different control networks and cannot resolve each other. Bayora is the trusted gateway attached to both. The optional local provider is attached only to `llm`. Remote provider egress is available only to Bayora through `provider-egress`.

The worker receives a sanitized environment. Fixture and unconfigured modes make no model network request. `openai_compatible` connects to the administrator-supplied remote endpoint. `ollama` connects to the configured local HTTP endpoint. Production deployments must enforce a dedicated egress policy and endpoint allowlist; the provider URL itself is configuration, not an isolation guarantee. The container profile drops capabilities, sets `no-new-privileges`, and uses a non-root UID.

The API does not enable cross-origin requests. Browser access is same-origin and protected with a restrictive content security policy. Responses include anti-sniffing, frame, and referrer controls.
