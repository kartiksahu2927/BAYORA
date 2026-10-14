# BAYORA - Potential Judge Questions and Suggested Answers

## 1. What is Bayora in one sentence?

Bayora is a proposed platform for authorized adversarial AI testing that links
controlled assessments to evidence, findings, provenance, and review.

## 2. Is Bayora already built?

This presentation intentionally presents Bayora as an idea and planning-stage
project. The deck does not claim implementation, deployment, customer use,
benchmarks, or completed integrations.

## 3. How is this different from simply testing a model in a chat window?

Bayora is intended to add the missing control layer: explicit authorization,
repeatable assessment workflows, role-aware review, session and tenant scope,
evidence provenance, and an audit trail. The proposed value is traceability and
governed workflow, not just sending prompts to a model.

## 4. Who is allowed to use it?

The proposed role model separates Red Team assessment creation, Blue Team
defensive review, Security Administrator oversight, and Auditor provenance
review. Backend authorization—not hidden UI controls—would enforce those
boundaries.

## 5. How would Bayora reduce prompt-injection risk?

It would treat prompts and retrieved web content as untrusted data, keep them
separate from privileged instructions, enforce approved scopes and sources, and
record provenance. It would not claim to eliminate prompt injection or every
AI vulnerability.

## 6. Why include TinyFish?

TinyFish is a possible research and evidence-collection service for approved
public security sources. Bayora would remain responsible for authorization,
allowlists, validation, evidence storage, and auditability. TinyFish output
would not be treated as inherently trustworthy.

## 7. How do you prevent SSRF or unrestricted browsing?

The proposed design uses server-side source categories and an exact HTTPS
allowlist instead of caller-supplied arbitrary URLs. It would reject local,
private, link-local, reserved, and metadata destinations, bound task duration
and response size, and re-check provenance. Remote browser egress remains a
deployment limitation that must also be controlled by the research provider.

## 8. What is the smallest viable product?

An authorized assessment workflow for one or more model providers, with clear
scope checks, repeatable test cases, evidence capture, role-aware review, and a
tamper-evident audit trail. Provider breadth and advanced integrations can
follow later.

## 9. What is the market opportunity?

AI governance is a relevant proxy category because organizations need oversight
as AI adoption and regulation grow. Grand View Research reports a 2025 AI
governance market estimate of USD 308.3M and a forecast CAGR of 36.0% for
2026-2033. That is third-party category context, not a claim about Bayora's
addressable market or future revenue.

## 10. What are the main risks?

The major risks are incomplete threat coverage, false confidence in automated
findings, provider-side data handling, remote browser egress, and unclear
ownership of security evidence. The proposed mitigations are bounded scope,
human review, explicit provenance, conservative defaults, and clear residual
risk documentation.

## 11. Why is there no mobile app in the roadmap?

Bayora's intended primary users are security and engineering teams working with
complex assessment evidence. A browser-based workflow is the more appropriate
MVP; mobile access can be reconsidered only if it improves review without
weakening security controls.

## 12. What information still needs confirmation?

The team name, member identities, assigned roles, official HIH theme, and
official judging criteria were not found in the supplied project materials.
Those placeholders should be finalized before submitting the deck.
