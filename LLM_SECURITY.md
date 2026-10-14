# LLM Session Security

## Provider boundary

Bayora exposes one provider-agnostic contract to the evaluation engine:

```text
LLMProvider
  health() -> ProviderHealth
  generate(LLMRequest) -> LLMResponse
  metadata() -> safe provider metadata
```

The available implementations are:

* `FixtureProvider`: deterministic test output. Every result is labeled **Test Fixture — Not Real Model Evidence** and has evidence type `test_fixture`.
* `OpenAICompatibleProvider`: an administrator-configured chat/completions HTTP adapter. It supports any compatible endpoint without hardcoded vendor, URL, credential, or model values.
* `OllamaProvider`: optional local HTTP support. Ollama is not a Bayora dependency and is never required for startup.
* `UnconfiguredProvider`: an explicit failure-path provider that reports `llm_not_configured`.

Red Team and Blue Team users cannot call a provider endpoint directly. The only request path is:

```text
Red Team -> Bayora authorization/policy -> evaluation service
          -> isolated provider worker -> configured model endpoint
```

Credentials are loaded from environment variables, passed only to the worker process through its private request pipe, and excluded from API responses, frontend data, logs, and audit payloads. Provider errors are reduced to safe classifications before persistence.

## Session and conversation isolation

Each evaluation receives a new opaque `session_id`, a new invocation ID, and a private owner-only workspace. The worker is launched for each provider operation and receives only the current prompt, session ID, and invocation ID. The OpenAI-compatible request contains only one user message for that evaluation; Bayora does not reuse conversation history between evaluations. The optional Ollama request also starts without a prior message history.

This guarantees **application-layer session isolation**: Bayora policy checks, tenant queries, request construction, audit events, and persisted results are bound to one evaluation session. A cross-session flow is denied by policy and cannot cause Bayora to send another session's data to the provider.

This does not claim hardware-level, kernel-level, or model-weight isolation. The remote provider controls its own server-side state. A compatible gateway may retain logs, cache prompts, batch requests, or maintain provider-side memory according to its configuration. Bayora does not claim KV-cache isolation, because the selected provider runtimes do not expose a guarantee that KV caches are private per Bayora session.

## Runtime state limitations

The current implementation makes one stateless chat/completions request per evaluation and sends no conversation identifier or history. Bayora does not batch requests and does not retain provider conversation state. The remote endpoint or Ollama runtime may still retain request logs, use internal batching, share process memory, or share KV caches. Those behaviors are outside Bayora's control and must be addressed in the provider deployment if stronger inference-runtime isolation is required.

## Health and lifecycle evidence

Provider health is a live worker operation. The OpenAI-compatible check requests the provider's model catalog, validates authentication responses, and verifies the configured model when the catalog is available. A catalog-less compatible endpoint may report that the endpoint is reachable while model availability is verified on generation. Health is never marked connected from configuration values alone.

Successful real evaluations audit:

```text
evaluation_created -> policy_checked -> llm_invocation
                   -> llm_response_received -> evaluation_completed
```

Failures audit `llm_request_failed` followed by `evaluation_failed`. A provider failure cannot produce `evaluation_completed`. Audit payloads contain provider/model identifiers, timestamps supplied by the audit record, invocation IDs, policy decisions, response hashes, and lengths; raw prompts are represented by hashes and credentials are never stored.

Remote mode places the model, model weights, and provider infrastructure outside Bayora's trust boundary. Local Ollama mode places the endpoint on the local network but does not automatically create a container or kernel boundary around that process. Fixture mode provides reproducible pipeline behavior only.
