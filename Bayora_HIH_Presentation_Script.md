# BAYORA - Presentation Script

## Slide 1 - Team

“Our project is Bayora, a proposed secure adversarial AI testing platform. The
team-name and member placeholders are intentionally left editable because those
details were not included in the supplied project material.”

## Slide 2 - Problem Statement & Theme

“AI systems can fail in ways that are difficult to reproduce and explain. A
crafted prompt or instruction embedded in external content can change model
behavior, expose information, or trigger an unsafe action. OWASP identifies
prompt injection as a leading LLM application risk. The problem is not simply
finding a bad answer once; it is creating a controlled, authorized, repeatable
process for testing, evidence collection, and review. Bayora is intended to
support secure and responsible AI work. The official HIH theme was not present
in the available materials, so that alignment still needs confirmation.”

## Slide 3 - Solution

“Bayora proposes one traceable workflow for authorized AI security assessment.
Red Team users can define adversarial probes, while Blue Team and review roles
can examine the resulting findings in their authorized scope. The planned
system connects assessment history, evidence, provenance, and auditability.
Its value is the chain from test design to evidence-backed review, rather than
an isolated chatbot or a one-off prompt experiment.”

## Slide 4 - Architecture

“The planned architecture separates the control plane from evaluation work.
An authorized request first passes scope and policy checks. A constrained
evaluation boundary then interacts with the selected model or provider. Results
are normalized into findings and evidence, while tenant context and audit
provenance are preserved. The technology choices shown here are the proposed
direction: a browser interface, Python API, SQLite for an initial deployment,
isolated workers, and provider adapters. TinyFish is an optional planned
research integration for approved public sources.”

## Slide 5 - Market Research / Analysis

“The primary users are AI builders, security researchers, and enterprise AI or
security teams. The market figure shown is category context, not Bayora’s TAM:
Grand View Research estimates the AI governance market at 308.3 million US
dollars in 2025 and forecasts 36 percent CAGR through 2033. We would test a
community-to-enterprise model: accessible core capabilities, paid team and
enterprise features, and optional assessment services. We are not claiming
customers, revenue, or adoption today.”

## Slide 6 - Future Scope

“The MVP should stay focused: repeatable authorized tests and an evidence trail.
The next phase can add more providers, threat-framework mappings, and reporting
formats. Enterprise readiness would add identity integrations, collaboration,
and stronger operational controls. Long term, Bayora could support reusable
benchmark libraries and multi-organization scale.”

## Slide 7 - Safeguards & Credibility

“Security is part of the design, not an afterthought. Bayora is intended to
enforce authorization and approved-source policy before research begins. Tenant
isolation and role-based access should restrict who can view evidence. Retrieved
web content remains untrusted data: it cannot change policy, permissions, or
audit history. Evidence is labeled unverified until an authorized reviewer
checks the source. The reference points are OWASP, NIST AI RMF, and MITRE ATLAS.”

## Slide 8 - Closing

“Bayora’s goal is to make AI security evaluation more disciplined, explainable,
and reviewable. It is a project idea at the planning stage, with a clear MVP,
a controlled architecture, and a path toward enterprise-grade evidence and
governance. Thank you.”

## Suggested timing

- Slides 1-2: 60 seconds
- Slides 3-4: 120 seconds
- Slides 5-6: 90 seconds
- Slide 7: 45 seconds
- Slide 8: 15 seconds
