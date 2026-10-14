"""Opt-in integration test for a configured real OpenAI-compatible endpoint."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from bayora.config import Settings
from bayora.service import BayoraService


REAL_PROVIDER_CONFIGURED = (
    os.environ.get("LLM_PROVIDER") == "openai_compatible"
    and bool(os.environ.get("LLM_BASE_URL"))
    and bool(os.environ.get("LLM_MODEL"))
)


@unittest.skipUnless(
    REAL_PROVIDER_CONFIGURED,
    "set LLM_PROVIDER=openai_compatible, LLM_BASE_URL, and LLM_MODEL to run the real-provider test",
)
class RealProviderIntegrationTests(unittest.TestCase):
    def test_real_model_canary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = BayoraService(Settings.from_env(Path(directory)))
            evaluation = service.create_evaluation(
                service.actor_for_token("bayora-red-token"),
                {
                    "prompt": "Respond with exactly:\n\nBAYORA_REAL_LLM_CANARY_638291\n\nDo not add anything else.",
                },
            )
            self.assertEqual(evaluation["state"], "completed")
            self.assertTrue(evaluation["response"])
            self.assertNotEqual(evaluation["model"]["evidence_type"], "test_fixture")
            self.assertEqual(
                [event["event_type"] for event in evaluation["audit_events"]],
                ["evaluation_created", "policy_checked", "llm_invocation", "llm_response_received", "evaluation_completed"],
            )


if __name__ == "__main__":
    unittest.main()
