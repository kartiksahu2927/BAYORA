"""Explicit information-flow decisions used by every protected operation."""

from __future__ import annotations

from .models import Decision, Flow


POLICY_MATRIX = {
    "red_to_llm": "allow when tenant and session match",
    "blue_to_llm_defensive_analysis": "allow authorized defensive analysis when tenant and session match",
    "red_to_blue_private": "block",
    "blue_to_red_private": "block",
    "red_to_host": "block",
    "cross_session_data": "block",
    "cross_tenant_data": "block",
    "red_to_external_intelligence": "allow when tenant and session match",
}


def decide(flow: Flow) -> Decision:
    """Return a deny-by-default decision for a requested information flow."""

    if flow.target_tenant_id and flow.target_tenant_id != flow.tenant_id:
        return Decision(False, "cross-tenant access is prohibited", "cross_tenant_data")

    if flow.target_session_id and flow.target_session_id != flow.session_id:
        return Decision(False, "session-private data cannot cross an evaluation boundary", "cross_session_data")

    if flow.destination == "llm" and flow.source == "red" and flow.resource == "evaluation":
        return Decision(True, "adversarial input may reach the model adapter", "red_to_llm")

    if (
        flow.destination == "llm" and flow.source == "blue" and flow.resource == "defensive_analysis"
        and flow.target_tenant_id == flow.tenant_id and flow.target_session_id == flow.session_id
    ):
        # Assessment authorization is enforced by the service before composing
        # evidence in a fresh Blue session. This does not grant red_private access.
        return Decision(True, "authorized defensive evidence may reach the model adapter", "blue_to_llm_defensive_analysis")

    if flow.destination == "external_intelligence" and flow.source == "red" and flow.resource == "intelligence_collection":
        return Decision(True, "red team may collect approved public security intelligence in its authorized scope", "red_to_external_intelligence")

    if flow.destination == "blue_private":
        return Decision(False, "defensive private data is isolated from adversarial input", "red_to_blue_private")

    if flow.destination == "red_private":
        return Decision(False, "adversarial private data is isolated from defensive input", "blue_to_red_private")

    if flow.destination == "host":
        return Decision(False, "workloads cannot access host resources", "red_to_host")

    return Decision(False, "no policy grants this information flow", "default_deny")
