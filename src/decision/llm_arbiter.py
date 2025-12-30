import logging
import json
import os
from typing import Dict, Any, Optional
from pathlib import Path
from decision.openai_provider import RealOpenAIProvider
from decision.mock_provider import MockLLMProvider

# Module-level load (standard), tests can override via patch.dict or load_dotenv(override=True)
try:
    from dotenv import load_dotenv
    env_path = Path(".env")
    load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

logger = logging.getLogger("LLMDecisionArbiter")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

class LLMDecisionArbiter:
    """
    Arbiter that uses an LLM to review 'REQUEST_CONFIRMATION' decisions.
    
    STRICT MODE:
    - Enabled=True -> MUST use Real OpenAI. If fails/missing key -> FAIL/ERROR.
    - Enabled=False -> Always Mock.
    """

    def __init__(self, enabled: bool = True):
        # 1. Read Configuration
        env_enabled_str = os.getenv("LLM_ENABLED", "false").lower()
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model_name = os.getenv("LLM_MODEL", "gpt-5-mini")
        self.mode = os.getenv("LLM_MODE", "observe").lower()
        
        # 2. Determine Activation
        self.using_real = (env_enabled_str == "true")
        
        self.provider = None
        self.provider_name = "None"

        # 3. Provider Initialization (Fail-Fast Logic)
        if self.using_real:
            # Strict Requirement: API Key MUST be present
            if not self.api_key:
                err_msg = "LLM_ENABLED=true but OPENAI_API_KEY is missing in environment."
                logger.error(err_msg)
                raise ValueError(err_msg)
            
            try:
                self.provider = RealOpenAIProvider(api_key=self.api_key, model=self.model_name)
                self.provider_name = "RealOpenAI"
            except Exception as e:
                # Should rarely happen during init unless SDK is missing
                logger.error(f"Failed to initialize RealOpenAIProvider: {e}")
                raise e
        else:
            # Disabled -> Mock
            self.provider = MockLLMProvider(model="gpt-mock")
            self.provider_name = "MockLLM"

        self.version = "0.7" # Fail-Fast Update

        # 4. Explicit Logging
        log_msg = (
            f"LLM Arbiter Initialized | "
            f"Mode: {self.mode} | "
            f"Active Provider: {self.provider_name} | "
            f"Target Model: {self.model_name}"
        )
        logger.info(log_msg)

    def arbitrate(self, snapshot: Dict[str, Any], preliminary_decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reviews a preliminary decision.
        """
        original_decision = preliminary_decision.get("decision", "IGNORE")
        
        # Setup fallback structure
        fallback_result = {
            "final_decision": original_decision,
            "confidence": preliminary_decision.get("decision_confidence", 1.0),
            "reasoning": preliminary_decision.get("reasoning", "") + " [Arbiter: Fallback/Skipped]",
            "arbiter_version": self.version,
            "arbiter_status": "skipped"
        }

        # Only arbitrate ambiguous cases
        if original_decision != "REQUEST_CONFIRMATION":
            return fallback_result

        # Generation logic
        generated_text = None
        used_model = "unknown"
        
        try:
            prompt = self._construct_prompt(snapshot)
            
            # Call Provider
            if self.provider:
                # If using Real Provider, this calls the API. If it fails, we catch Exception below.
                # We do NOT catch specific errors here to swap provider.
                # If real provider fails, we return error fallback, NOT mock content.
                generated_text = self.provider.generate(system_prompt=prompt)
                
                if self.using_real:
                    used_model = self.model_name
                else:
                    used_model = "gpt-mock"

            if not generated_text:
                # If real provider returned None (e.g. SDK error logged inside provider), we stop.
                logger.error("Provider returned no content.")
                return fallback_result

        except Exception as e:
            logger.error(f"LLM Arbitration Failed: {e}")
            return fallback_result

        # Parse and Return
        parsed_decision = self._parse_llm_response(generated_text)
        
        if not parsed_decision:
            logger.warning("Failed to parse LLM response.")
            return fallback_result

        # Observe vs Enforce
        if self.mode == "observe":
            self._print_observation(parsed_decision, used_model)
            fallback_result["arbiter_debug"] = parsed_decision
            fallback_result["arbiter_status"] = "observed"
            return fallback_result

        # Enforce Mode
        return {
            "final_decision": parsed_decision.get("recommendation", original_decision),
            "confidence": parsed_decision.get("confidence", 0.5),
            "reasoning": parsed_decision.get("reasoning", "No reasoning provided."),
            "notes": parsed_decision.get("notes", ""),
            "risk_level": parsed_decision.get("risk_level", "unknown"),
            "uncertainty_flags": parsed_decision.get("uncertainty_flags", []),
            "arbiter_version": self.version,
            "arbiter_status": "enforced"
        }

    def _construct_prompt(self, snapshot: Dict[str, Any]) -> str:
        snapshot_json = json.dumps(snapshot, indent=2)
        return f"""
You are an analytical safety observer embedded in a video-monitoring system.

Your role is to critically analyze a structured Analysis Snapshot generated from
motion, posture, and temporal event data.

IMPORTANT CONSTRAINTS:
- You do NOT see video.
- You do NOT control any system.
- You do NOT trigger actions.
- You ONLY provide a reasoned assessment based on the provided snapshot.
- You may be wrong and must signal uncertainty when appropriate.
- Avoid alarmism. Prefer conservative interpretations when data is ambiguous.

Your task:
1. Interpret what most likely happened in the real world.
2. Assess the associated risk level.
3. Suggest an appropriate action recommendation.

You must base your reasoning ONLY on the snapshot content.
Do NOT assume camera accuracy, subject identity, or injury unless strongly supported.
If information is insufficient, prefer lower-risk recommendations.

You MUST return ONLY valid JSON, with no text before or after, using EXACTLY
the following schema:

{{
  "recommendation": "NOTIFY_CAREGIVER | REQUEST_CONFIRMATION | MONITOR | IGNORE",
  "risk_level": "low | medium | high | critical",
  "confidence": 0.0,
  "reasoning": "short, clear explanation grounded in the snapshot",
  "uncertainty_flags": [],
  "notes": ""
}}

Here is the Analysis Snapshot to analyze:

{snapshot_json}
"""

    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        try:
            clean_text = response_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_text)
            
            valid = ["NOTIFY_CAREGIVER", "MONITOR", "REQUEST_CONFIRMATION", "IGNORE"]
            if data.get("recommendation") not in valid:
                logger.error(f"Invalid recommendation: {data.get('recommendation')}")
                return None
            return data
        except json.JSONDecodeError:
            return None

    def _print_observation(self, data: Dict[str, Any], model_used: str):
        print("\n" + "="*30)
        print("--- LLM OBSERVATION ---")
        print(f"Model: {model_used}")
        print(f"Recommendation: {data.get('recommendation')}")
        print(f"Risk Level: {data.get('risk_level')}")
        print(f"Confidence: {data.get('confidence')}")
        print(f"Reasoning: {data.get('reasoning')}")
        print(f"Flags: {data.get('uncertainty_flags')}")
        print(f"Notes: {data.get('notes', '')}")
        print("="*30 + "\n")
