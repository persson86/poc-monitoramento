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

    @patch.dict(os.environ, {"OPENAI_API_KEY": "", "LLM_MODE": "enforce", "LLM_ENABLED": "true"})
    def test_missing_key_raises_error(self):
        """Test that missing API key raises ValueError (Fail-Fast)"""
        with self.assertRaises(ValueError):
            LLMDecisionArbiter(enabled=True)

    @patch.dict(os.environ, {"OPENAI_API_KEY": "mock-key", "LLM_MODE": "enforce", "LLM_ENABLED": "false"})
    def test_disabled_arbiter_uses_mock(self):
        """Test that disabled arbiter uses Mock Provider"""
        arbiter = LLMDecisionArbiter(enabled=False)
        result = arbiter.arbitrate(self.base_snapshot, self.preliminary_decision)
        
        self.assertEqual(result["final_decision"], "REQUEST_CONFIRMATION")
        self.assertEqual(result["arbiter_status"], "enforced")
        self.assertIn("Mock ambiguous", result["reasoning"])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "mock-key", "LLM_MODE": "enforce", "LLM_ENABLED": "true"})
    def test_broken_provider_returns_fallback(self):
        """Test fallback when Real Provider fails (NO Mock fallback allowed)"""
        arbiter = LLMDecisionArbiter(enabled=True)
        
        # Inject Broken Provider
        class BrokenProvider:
            def generate(self, system_prompt, user_prompt=""):
                raise Exception("Network Error")
        
        arbiter.provider = BrokenProvider()
        
        result = arbiter.arbitrate(self.base_snapshot, self.preliminary_decision)
        
        # Should return original decision (skipped), NOT mock output
        self.assertEqual(result["final_decision"], "REQUEST_CONFIRMATION")
        self.assertIn("Fallback", result["reasoning"])
        self.assertEqual(result["arbiter_status"], "skipped")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "mock-key", "LLM_MODE": "enforce", "LLM_ENABLED": "false"})
    def test_mock_triggers(self):
        """Test that mocking still works when explicitly disabled (LLM_ENABLED=false)"""
        arbiter = LLMDecisionArbiter(enabled=False)
        snapshot = self.base_snapshot.copy()
        snapshot["human_readable_summary"] = "Subject had a major fall."
        
        result = arbiter.arbitrate(snapshot, self.preliminary_decision)
        
        self.assertEqual(result["final_decision"], "NOTIFY_CAREGIVER")
        self.assertEqual(result["risk_level"], "critical")

if __name__ == "__main__":
    unittest.main()
