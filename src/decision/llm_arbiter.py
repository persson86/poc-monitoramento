import logging
import json
import os
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from pathlib import Path

# --- MANDATORY ENV FIX ---
# Explicitly load .env from the current working directory to avoid
# auto-discovery issues in CI or interactive shells.
try:
    from dotenv import load_dotenv
    env_path = Path(".env")
    load_dotenv(dotenv_path=env_path)
except ImportError:
    logging.getLogger("LLMDecisionArbiter").warning("python-dotenv not installed. Skipping explicit .env load.")

logger = logging.getLogger("LLMDecisionArbiter")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

class LLMDecisionArbiter:
    """
    Arbiter that uses an LLM to review 'REQUEST_CONFIRMATION' decisions.
    
    Principles:
    1. Deterministic prompt.
    2. Zero access to raw video.
    3. Fails safe (returns original decision).
    4. Cost controlled (minimal context).
    5. Supports 'Observe Mode' for safe testing.
    6. explicit configuration loading.
    """

    def __init__(self, enabled: bool = True):
        # 1. Read Configuration Strictly via os.getenv
        env_enabled_str = os.getenv("LLM_ENABLED", "false").lower()
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.mode = os.getenv("LLM_MODE", "observe").lower() # observe | enforce
        
        # 2. Determine Activation Status
        # Requirements: Env var must be "true", and API key must be present.
        is_env_enabled = (env_enabled_str == "true")
        
        if is_env_enabled and not self.api_key:
            logger.warning("OPENAI_API_KEY not set. LLM disabled.")
            self.enabled = False
        elif is_env_enabled:
            self.enabled = True
        else:
            logger.info("LLM disabled via environment variable.")
            self.enabled = False

        self.version = "0.3" # Hardening Update

        # 3. Explicit Initialization Logging (Mandatory)
        # format: LLM enabled: true / false ...
        key_status = "true" if self.api_key else "false"
        
        log_msg = (
            f"LLM Arbiter Initialized | "
            f"LLM enabled: {str(self.enabled).lower()} | "
            f"LLM mode: {self.mode} | "
            f"LLM model: {self.model_name} | "
            f"API key present: {key_status}"
        )
        logger.info(log_msg)

    def arbitrate(self, snapshot: Dict[str, Any], preliminary_decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reviews a preliminary decision and returns a final decision.
        """
        original_decision = preliminary_decision.get("decision", "IGNORE")
        
        # Fallback result structure
        fallback_result = {
            "final_decision": original_decision,
            "confidence": preliminary_decision.get("decision_confidence", 1.0),
            "reasoning": preliminary_decision.get("reasoning", "") + " [Arbiter: Fallback/Skipped]",
            "arbiter_version": self.version,
            "arbiter_status": "skipped"
        }

        # 1. Check enablement
        if not self.enabled:
            return fallback_result

        # Only arbitrate ambiguous cases
        if original_decision != "REQUEST_CONFIRMATION":
            return fallback_result

        try:
            # 2. Construct Prompt
            prompt = self._construct_prompt(snapshot, preliminary_decision)
            
            # 3. Call LLM
            llm_response_text = self._call_llm_provider(prompt)
            
            # 4. Parse Response
            parsed_decision = self._parse_llm_response(llm_response_text)
            
            if not parsed_decision:
                logger.warning("Failed to parse LLM response. Using fallback.")
                return fallback_result

            # 5. Handle Observe Mode (NOISY) vs Enforce Mode
            if self.mode == "observe":
                # Mandatory: Always print in observe mode
                self._print_observation(parsed_decision)
                
                # Return original decision (Safety)
                fallback_result["arbiter_debug"] = parsed_decision
                fallback_result["arbiter_status"] = "observed"
                return fallback_result

            # Enforce Mode
            return {
                "final_decision": parsed_decision.get("llm_recommendation", original_decision),
                "confidence": parsed_decision.get("confidence", 0.5),
                "reasoning": parsed_decision.get("reasoning", "No reasoning provided."),
                "notes": parsed_decision.get("notes", ""),
                "arbiter_version": self.version,
                "arbiter_status": "enforced"
            }

        except Exception as e:
            logger.error(f"LLM Arbiter encountered an error: {e}")
            return fallback_result

    def _construct_prompt(self, snapshot: Dict[str, Any], preliminary_decision: Dict[str, Any]) -> str:
        summary = snapshot.get("human_readable_summary", "No summary available.")
        observed_state = json.dumps(snapshot.get("observed_state", {}), indent=2)
        hypotheses = json.dumps(snapshot.get("hypotheses", []), indent=2)
        
        current_decision = preliminary_decision.get("decision", "UNKNOWN")
        current_reasoning = preliminary_decision.get("reasoning", "No reasoning.")

        return f"""
SYSTEM: You are an expert human observer analyzing summarized monitoring events.
You must be cautious.
False positives are costly.
Human safety matters, but panic is harmful.

INPUT DATA:
--- Summary ---
{summary}

--- Observed State ---
{observed_state}

--- Hypotheses ---
{hypotheses}

--- Preliminary Decision ---
Decision: {current_decision}
Reasoning: {current_reasoning}

TASK:
Determine the final decision. Options:
- NOTIFY_CAREGIVER: High confidence of a fall or dangerous situation.
- MONITOR: Situation seems stable, recovering, or is a known false alarm.
- REQUEST_CONFIRMATION: Still ambiguous, needs human eyes.
- IGNORE: Explicitly safe.

OUTPUT FORMAT (JSON ONLY):
{{
  "llm_recommendation": "NOTIFY_CAREGIVER" | "MONITOR" | "REQUEST_CONFIRMATION" | "IGNORE",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<concise explanation>",
  "notes": "<optional notes>"
}}
"""

    def _call_llm_provider(self, prompt: str) -> str:
        """
        Calls OpenAI API using standard urllib.
        """
        # --- MOCK LOGIC FOR LOCAL TESTING ---
        if self.api_key == "mock-key":
             return self._mock_response(prompt)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }
        
        try:
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(data).encode('utf-8'),
                headers=headers,
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                response_body = response.read().decode('utf-8')
                return json.loads(response_body)["choices"][0]["message"]["content"]
                
        except urllib.error.URLError as e:
            logger.error(f"OpenAI API Request Failed: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error in LLM call: {e}")
            raise e

    def _mock_response(self, prompt: str) -> str:
        """Internal mock."""
        prompt_lower = prompt.lower()
        if "critical" in prompt_lower:
            return json.dumps({"llm_recommendation": "NOTIFY_CAREGIVER", "confidence": 0.9, "reasoning": "Mock critical."})
        return json.dumps({"llm_recommendation": "MONITOR", "confidence": 0.8, "reasoning": "Mock monitor."})

    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        try:
            clean_text = response_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_text)
            
            if "decision" in data and "llm_recommendation" not in data:
                data["llm_recommendation"] = data["decision"]

            valid = ["NOTIFY_CAREGIVER", "MONITOR", "REQUEST_CONFIRMATION", "IGNORE"]
            if data.get("llm_recommendation") not in valid:
                logger.error(f"Invalid recommendation: {data.get('llm_recommendation')}")
                return None
            return data
        except json.JSONDecodeError:
            return None

    def _print_observation(self, data: Dict[str, Any]):
        print("\n" + "="*30)
        print("--- LLM OBSERVATION ---")
        print(f"Model: {self.model_name}")
        print(f"Recommendation: {data.get('llm_recommendation')}")
        print(f"Confidence: {data.get('confidence')}")
        print(f"Reasoning: {data.get('reasoning')}")
        print(f"Notes: {data.get('notes', '')}")
        print("="*30 + "\n")
