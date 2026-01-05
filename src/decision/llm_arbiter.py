import logging
import json
import os
from typing import Dict, Any, Optional
from pathlib import Path
from decision.openai_provider import RealOpenAIProvider
from decision.mock_provider import MockLLMProvider
from shared.logging_contracts import emit_log

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

    def arbitrate(self, snapshot: Dict[str, Any], preliminary_decision: Dict[str, Any], force_observe: bool = False) -> Dict[str, Any]:
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

        # Add check for prolonged floor time to force observe mode
        on_floor_duration = snapshot.get("on_floor_duration_seconds", 0.0)
        patterns = snapshot.get("detected_patterns", [])
        should_force_observe = False
        
        # Force observe if:
        # 1. Explicitly requested by caller (force_observe=True)
        # 2. Duration > 5s (generic validation)
        # 3. Decision is NOTIFY_FAMILY_INFO (internal safety check)
        # 4. Pattern 'prolonged_floor_immobility' is present
        if (force_observe or
            on_floor_duration > 5.0 or 
            original_decision == "NOTIFY_FAMILY_INFO" or 
            "prolonged_floor_immobility" in patterns):
            
            logger.info(f"Forced observe mode triggered. Forced={force_observe}, Duration: {on_floor_duration}s, Decision: {original_decision}")
            should_force_observe = True
            # Proceed with LLM call, but then force the 'observe' path
            self.mode = "observe" # Temporarily override mode for this arbitration

        # Only arbitrate ambiguous cases UNLESS we are forcing observe for duration/critical events
        if original_decision != "REQUEST_CONFIRMATION" and not should_force_observe:
            # Emit LLM_SKIPPED log to make explicit why LLM was not called
            skip_reason = f"Decision '{original_decision}' does not require confirmation and no force triggers (duration={on_floor_duration:.1f}s)"
            emit_log(
                log_type="LLM_SKIPPED",
                payload={
                    "reason": skip_reason,
                    "original_decision": original_decision,
                    "on_floor_duration_seconds": on_floor_duration
                },
                trace_id=snapshot.get("snapshot_id", "unknown"),
                component="llm_arbiter"
            )
            return fallback_result

        # Generation logic
        generated_text = None
        used_model = "unknown"
        
        try:
            prompt = self._construct_prompt(snapshot)
            
            # Emit LLM_INPUT log before API call
            snapshot_id = snapshot.get("snapshot_id", "unknown")
            risk_level = snapshot.get("risk_level", "unknown")
            world_state = snapshot.get("world_state", "unknown")
            patterns = snapshot.get("detected_patterns", [])
            event_count = len(snapshot.get("supporting_events", []))
            
            payload_summary = f"risk={risk_level}, state={world_state}, patterns={len(patterns)}, events={event_count}"
            
            emit_log(
                log_type="LLM_INPUT",
                payload={
                    "model": self.model_name,
                    "mode": self.mode,
                    "snapshot_id": snapshot_id,
                    "payload_summary": payload_summary,
                    "system_question": "Analyze snapshot and provide safety recommendation"
                },
                trace_id=snapshot_id,
                component="llm_arbiter"
            )
            
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
                
                # Emit LLM_OUTPUT log for error case
                emit_log(
                    log_type="LLM_OUTPUT",
                    payload={
                        "recommended_action": None,
                        "risk_level": None,
                        "confidence": None,
                        "flags": ["provider_error", "no_response"],
                        "notes": "Provider failed to generate content"
                    },
                    trace_id=snapshot_id,
                    component="llm_arbiter"
                )
                return fallback_result

        except Exception as e:
            logger.error(f"LLM Arbitration Failed: {e}")
            
            # Emit LLM_OUTPUT log for exception case
            emit_log(
                log_type="LLM_OUTPUT",
                payload={
                    "recommended_action": None,
                    "risk_level": None,
                    "confidence": None,
                    "flags": ["exception", "api_failure"],
                    "notes": f"Exception during LLM call: {str(e)}"
                },
                trace_id=snapshot.get("snapshot_id", "unknown"),
                component="llm_arbiter"
            )
            return fallback_result

        # Parse and Return
        parsed_decision = self._parse_llm_response(generated_text)
        
        if not parsed_decision:
            logger.warning("Failed to parse LLM response.")
            
            # Emit LLM_OUTPUT log for parse failure
            emit_log(
                log_type="LLM_OUTPUT",
                payload={
                    "recommended_action": None,
                    "risk_level": None,
                    "confidence": None,
                    "flags": ["parse_error"],
                    "notes": "Failed to parse LLM response as valid JSON"
                },
                trace_id=snapshot_id,
                component="llm_arbiter"
            )
            return fallback_result
        
        # Emit LLM_OUTPUT log for successful response
        emit_log(
            log_type="LLM_OUTPUT",
            payload={
                "recommended_action": parsed_decision.get("recommendation"),
                "risk_level": parsed_decision.get("risk_level"),
                "confidence": parsed_decision.get("confidence"),
                "flags": parsed_decision.get("uncertainty_flags", []),
                "notes": parsed_decision.get("notes", "")
            },
            trace_id=snapshot_id,
            component="llm_arbiter"
        )

        # Unconditional Message Preview Generation
        # Requirement: Always generate preview if LLM was called, derived exclusively from LLM output.
        self._emit_message_preview(snapshot_id, parsed_decision)
        fallback_result["message_preview_generated"] = True

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
            "arbiter_status": "enforced",
            "message_preview_generated": True
        }

    def _emit_message_preview(self, snapshot_id: str, parsed_decision: Dict[str, Any]):
        rec = parsed_decision.get("recommendation", "IGNORE")
        risk = parsed_decision.get("risk_level", "unknown")
        conf = parsed_decision.get("confidence", 0.0)
        notes = parsed_decision.get("notes", "No notes provided")
        
        # Simple Portuguese formatting
        title_map = {
            "NOTIFY_CAREGIVER": "🚨 ALERTA DE QUEDA",
            "REQUEST_CONFIRMATION": "⚠️ CONFIRMAÇÃO NECESSÁRIA",
            "MONITOR": "ℹ️ MONITORAMENTO",
            "NOTIFY_FAMILY_INFO": "ℹ️ AVISO FAMILIAR - Queda Detectada (Tempo)",
            "IGNORE": "👻 SISTEMA SILENCIOSO (IGNORE)" 
        }
        title = title_map.get(rec, "MENSAGEM DO SISTEMA")
        
        # Custom body formatting based on message type
        if rec == "NOTIFY_FAMILY_INFO":
            body = (
                "Olá. O sistema detectou que a pessoa monitorada permaneceu no chão por um tempo prolongado.\n"
                "A situação parece estável e não foi identificada como emergência crítica, "
                "mas recomendamos verificar o ambiente quando possível.\n\n"
                f"Observação da IA: {notes}"
            )
        else:
            body = f"Análise AI: Risco {risk.upper()} ({conf:.2f}).\nObs: {notes}"
        
        emit_log(
            log_type="MESSAGE_PREVIEW",
            payload={
                "source": "LLM",
                "channel": "TELEGRAM",
                "recipient": "Caregiver",
                "title": title,
                "body": body,
                "requires_ack": (rec == "REQUEST_CONFIRMATION")
            },
            trace_id=snapshot_id,
            component="llm_arbiter"
        )

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
  "recommendation": "NOTIFY_CAREGIVER | REQUEST_CONFIRMATION | MONITOR | IGNORE | NOTIFY_FAMILY_INFO",
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
            
            valid = ["NOTIFY_CAREGIVER", "MONITOR", "REQUEST_CONFIRMATION", "IGNORE", "NOTIFY_FAMILY_INFO"]
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
