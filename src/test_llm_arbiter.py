import unittest
import json
import os
from unittest.mock import patch, MagicMock
from decision.llm_arbiter import LLMDecisionArbiter

class TestLLMDecisionArbiter(unittest.TestCase):
    
    def setUp(self):
        # Base snapshot structure
        self.base_snapshot = {
            "snapshot_id": "test_snap_1",
            "time_window": {"duration_seconds": 30},
            "observed_state": {"posture": "unknown", "movement_trend": "unknown"},
            "hypotheses": [],
            "human_readable_summary": "Test summary"
        }
        
        self.preliminary_decision = {
            "decision": "REQUEST_CONFIRMATION",
            "decision_confidence": 0.5,
            "reasoning": "Uncertain logic."
        }

    @patch.dict(os.environ, {"OPENAI_API_KEY": "mock-key", "LLM_MODE": "enforce", "LLM_ENABLED": "false"})
    def test_disabled_arbiter_returns_fallback(self):
        """Test that disabled arbiter returns input decision"""
        arbiter = LLMDecisionArbiter(enabled=False)
        result = arbiter.arbitrate(self.base_snapshot, self.preliminary_decision)
        
        self.assertEqual(result["final_decision"], "REQUEST_CONFIRMATION")
        self.assertIn("Fallback/Skipped", result["reasoning"])
        self.assertEqual(result["arbiter_status"], "skipped")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "mock-key", "LLM_MODE": "enforce", "LLM_ENABLED": "true"})
    def test_non_confirmation_decision_skipped(self):
        """Test that decisions other than REQUEST_CONFIRMATION are ignored"""
        arbiter = LLMDecisionArbiter(enabled=True)
        decision = {
            "decision": "IGNORE",
            "decision_confidence": 0.9,
            "reasoning": "Nothing happened."
        }
        result = arbiter.arbitrate(self.base_snapshot, decision)
        
        self.assertEqual(result["final_decision"], "IGNORE")
        self.assertEqual(result["arbiter_status"], "skipped")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "mock-key", "LLM_MODE": "enforce", "LLM_ENABLED": "true"})
    def test_escalation_to_notify(self):
        """Test mock logic escalating critical context"""
        arbiter = LLMDecisionArbiter(enabled=True)
        snapshot = self.base_snapshot.copy()
        snapshot["human_readable_summary"] = "Subject had a major fall and is unconscious. critical"
        
        result = arbiter.arbitrate(snapshot, self.preliminary_decision)
        
        self.assertEqual(result["final_decision"], "NOTIFY_CAREGIVER")
        self.assertEqual(result["arbiter_status"], "enforced")
        # Reasoning comes from the mock response logic in _call_llm_provider

    @patch.dict(os.environ, {"OPENAI_API_KEY": "mock-key", "LLM_MODE": "enforce", "LLM_ENABLED": "true"})
    def test_downgrade_to_monitor(self):
        """Test mock logic downgrading stable context"""
        arbiter = LLMDecisionArbiter(enabled=True)
        snapshot = self.base_snapshot.copy()
        # The internal mock now looks for 'critical' -> notify, otherwise 'monitor'
        # To test downgrade, we ensure it's NOT critical.
        snapshot["human_readable_summary"] = "Subject stumbled but is recovering and sitting up."
        
        result = arbiter.arbitrate(snapshot, self.preliminary_decision)
        
        self.assertEqual(result["final_decision"], "MONITOR")
        self.assertEqual(result["arbiter_status"], "enforced")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "mock-key", "LLM_MODE": "enforce", "LLM_ENABLED": "true"})
    def test_fallback_on_llm_error(self):
        """Test fallback when LLM returns garbage"""
        # Subclass to force failure
        class BrokenArbiter(LLMDecisionArbiter):
            def _call_llm_provider(self, prompt):
                return "Not JSON"
        
        broken_arbiter = BrokenArbiter(enabled=True)
        result = broken_arbiter.arbitrate(self.base_snapshot, self.preliminary_decision)
        
        self.assertEqual(result["final_decision"], "REQUEST_CONFIRMATION")
        self.assertIn("Fallback", result["reasoning"])

if __name__ == "__main__":
    unittest.main()
