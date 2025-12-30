import unittest
import os
import sys
import logging
from unittest.mock import patch
from decision.llm_arbiter import LLMDecisionArbiter

class TestLLMObserveMode(unittest.TestCase):
    
    def setUp(self):
        self.snapshot = {
            "human_readable_summary": "Subject fell and is not moving. Critical.",
            "observed_state": {"posture": "on_floor"},
            "hypotheses": []
        }
        self.preliminary = {
            "decision": "REQUEST_CONFIRMATION",
            "reasoning": "Unsure."
        }

    # IMPORTANT: We purposefully do NOT mock stdout here. 
    # The goal is to verify that the system PRINTS to the real terminal.
    
    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "mock-key",
        "LLM_ENABLED": "true",
        "LLM_MODE": "observe",
        "LLM_MODEL": "gpt-mock"
    })
    def test_observe_mode_is_noisy(self):
        """
        Verifies that Observe Mode runs without crashes and allows printing.
        User must manually verify "--- LLM OBSERVATION ---" appears in the output.
        """
        print("\n[TEST START] test_observe_mode_is_noisy")
        
        # Verify startup logs are correct
        with self.assertLogs("LLMDecisionArbiter", level='INFO') as cm:
            arbiter = LLMDecisionArbiter(enabled=True)
            result = arbiter.arbitrate(self.snapshot, self.preliminary)
            
            # Check Logs
            log_messages = "\n".join(cm.output)
            self.assertIn("LLM enabled: true", log_messages)
            self.assertIn("LLM mode: observe", log_messages)
            self.assertIn("API key present: true", log_messages)
            
        print("[TEST INFO] Arbiter result logic verification...")
        self.assertEqual(result["final_decision"], "REQUEST_CONFIRMATION",
                         "Observe mode MUST fallback to original decision.")
            
        print("[TEST END] test_observe_mode_is_noisy (Check above for observation block)\n")

if __name__ == "__main__":
    unittest.main()
