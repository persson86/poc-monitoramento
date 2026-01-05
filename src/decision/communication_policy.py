from typing import Dict, Any, Optional
from shared.logging_contracts import emit_log

def evaluate_communication_policy(
    decision_result: Dict[str, Any],
    llm_result: Optional[Dict[str, Any]] = None,
    snapshot_id: str = "unknown",
    on_floor_duration_seconds: float = 0.0
) -> Dict[str, Any]:
    """
    Evaluates whether to communicate with humans based on Decision Engine and LLM outputs.
    
    This is a policy function that determines notification creation without actually
    sending messages.
    
    Args:
        decision_result: Output from Decision Engine
        llm_result: Optional output from LLM Arbiter
        snapshot_id: Snapshot identifier for correlation
        on_floor_duration_seconds: Duration person has been on floor
        
    Returns:
        Policy decision with action recommendation
    """
    
    # Extract decision engine outcome
    decision_outcome = decision_result.get("decision", "IGNORE")
    risk_level = decision_result.get("risk_level", "low")
    
    # Extract LLM recommendation if available
    llm_recommendation = None
    if llm_result:
        llm_recommendation = llm_result.get("final_decision") or llm_result.get("recommendation")
    
    # Collect context flags
    context_flags = []
    
    # Add flags from decision result
    if decision_result.get("decision_confidence", 1.0) < 0.8:
        context_flags.append("low_confidence")
    
    # Add flags from LLM if available
    if llm_result:
        arbiter_status = llm_result.get("arbiter_status")
        if arbiter_status == "observed":
            context_flags.append("llm_observe_mode")
        elif arbiter_status == "skipped":
            context_flags.append("llm_skipped")
        
        # Add uncertainty flags from LLM
        if "arbiter_debug" in llm_result:
            llm_flags = llm_result["arbiter_debug"].get("uncertainty_flags", [])
            context_flags.extend(llm_flags)
            
    # Add context based on floor duration
    if on_floor_duration_seconds > 0:
        context_flags.append(f"on_floor_duration_seconds={on_floor_duration_seconds:.1f}")
    
    # Policy Decision Logic (Gatekeeping)
    # We enforce that the SYSTEM decides IF to send, while LLM decides WHAT to say.
    
    should_send = False
    policy_reason = "No criteria met for external communication"
    
    # 1. Critical decision from Engine always overrides
    if decision_outcome == "NOTIFY_CAREGIVER":
        should_send = True
        policy_reason = f"System enforced notification (Risk: {risk_level})"
        
    # 2. Informational Decision (Family Info)
    elif decision_outcome == "NOTIFY_FAMILY_INFO":
        should_send = True
        policy_reason = "Approved: Family information update (Confirmed Duration Fall)"
        
    # 3. LLM Recommendation (if enabled and high confidence)
    elif llm_recommendation == "NOTIFY_CAREGIVER":
        # Additional policy check: do not auto-send solely on LLM unless confirmed high risk
        if risk_level in ["high", "critical"]:
            should_send = True
            policy_reason = "LLM recommendation validated by high risk level"
        else:
            policy_reason = "LLM recommended notification but suppressed (Risk too low for auto-send)"
            
    # 3. Message Status
    result = "SEND_MESSAGE" if should_send else "SUPPRESS_MESSAGE"
    
    # Emit COMMUNICATION_POLICY log
    emit_log(
        log_type="COMMUNICATION_POLICY",
        payload={
            "gatekeeper_decision": result,
            "policy_reason": policy_reason,
            "decision_engine_outcome": decision_outcome,
            "llm_recommendation": llm_recommendation if llm_recommendation else "N/A",
            "risk_level": risk_level,
            "context_flags": context_flags,
            "on_floor_duration_seconds": on_floor_duration_seconds,
            "simulated_action": {
                "channel": "TELEGRAM",
                "recipient": "FAMILY" if decision_outcome == "NOTIFY_FAMILY_INFO" else "CAREGIVER",
                "sent": should_send
            }
        },
        trace_id=snapshot_id,
        component="communication_policy"
    )
    
    return {
        "action": result,
        "reason": policy_reason,
        "snapshot_id": snapshot_id
    }
