import unittest
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# --- MANDATORY ENV LOAD ---
# Force load .env from current directory, overriding any existing env vars.
# This ensures we are testing against the REAL credentials in .env.
env_path = Path(".env")
load_dotenv(dotenv_path=env_path, override=True)

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
        
    def test_observe_mode_is_noisy(self):
        """
        Verifies that Observe Mode runs without crashes and allows printing.
        User must manually verify "--- LLM OBSERVATION ---" appears in the output.
        """
        print("\n" + "="*50)
        print("[TEST START] test_observe_mode_is_noisy")
        print(f"LLM_ENABLED: {os.getenv('LLM_ENABLED')}")
        print(f"LLM_MODEL:   {os.getenv('LLM_MODEL')}")
        print(f"API_KEY:     {'***' if os.getenv('OPENAI_API_KEY') else 'MISSING'}")
        print("="*50 + "\n")
        
        # We expect this to SUCCEED if configured correctly, 
        # or FAIL/LOG ERROR if configured incorrectly (Fail-Fast).
        # We do NOT use assertLogs because we want to see the stdout.
        
        try:
            arbiter = LLMDecisionArbiter(enabled=True)
            result = arbiter.arbitrate(self.snapshot, self.preliminary)
            
            print("\n[TEST INFO] Arbiter result received.")
            self.assertEqual(result["final_decision"], "REQUEST_CONFIRMATION",
                            "Observe mode MUST fallback to original decision.")
            
            # Additional check for status
            if os.getenv("LLM_ENABLED", "false").lower() == "true":
                 print(f"[TEST CHECK] Expected 'Active Provider: RealOpenAI' in logs.")
            else:
                 print(f"[TEST CHECK] Expected 'Active Provider: MockLLM' in logs.")

        except ValueError as e:
            print(f"\n[TEST FAILURE EXPECTED?] Initialization failed: {e}")
            # If the user INTENDED to fail fast (missing key), this might be a 'pass' 
            # but for this generic test script, we let it crash to be noisy.
            raise e
            
        print("\n[TEST END] test_observe_mode_is_noisy (Check above for observation block)\n")

if __name__ == "__main__":
    unittest.main()
