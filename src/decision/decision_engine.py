import uuid
import time
import json
import logging
import datetime
from typing import Dict, Any, List
from shared.logging_contracts import emit_log

logger = logging.getLogger("DecisionEngine")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


class DecisionEngine:
    """
    Deterministic Decision Engine that consumes Analysis Snapshots
    and recommends actions without executing them.
    """

    def __init__(self):
        pass
    
    def _iso_format(self, timestamp: float) -> str:
        return datetime.datetime.fromtimestamp(timestamp).isoformat()

    def decide(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluates a snapshot and returns a decision.
        """
        current_time_ts = time.time()
        snapshot_id = snapshot.get("snapshot_id", "unknown")
        
        # Extract features from snapshot
        hypotheses = snapshot.get("hypotheses", [])
        observed_state = snapshot.get("observed_state", {})
        temporal_pattern = snapshot.get("temporal_pattern", {})
        event_summary = snapshot.get("event_summary", {})
        
        posture = observed_state.get("posture", "unknown")
        movement_trend = observed_state.get("movement_trend", "unknown")
        pattern_type = temporal_pattern.get("pattern_type", "unknown")
        total_events = event_summary.get("total_events", 0)
        
        # Find strongest hypothesis
        fall_hypothesis = next((h for h in hypotheses if h.get("type", "").lower() in ["possible_fall", "fall"]), None)
        instability_hypothesis = next((h for h in hypotheses if h.get("type", "").lower() in ["instability", "needs_attention"]), None)
        
        # --- Decision Logic (Baseline Rules) ---
        
        # Default decision
        decision = "IGNORE"
        risk_level = "low"
        recommended_next_step = "none"
        reasoning_parts = []
        rules_triggered = []
        
        # Baseline logic v0.2
        # Calculate time in low posture if applicable
        time_in_low_posture = 0.0
        recovery_detected = False
        
        # We need the timestamp of the fall event to compare with window end
        # Since we don't have the full event list details here (unless we request them),
        # we can estimate using the window duration if the hypothesis is strong.
        # Ideally, the snapshot should contain this info or we infer it.
        # Workaround: Use the fact that if a fall is detected, it ends close to "end_time" or we check the duration.
        # BETTER: Check raw_event_ids or pass event_summary details. 
        # But wait, we cannot blindly re-read events. 
        # Let's trust the 'observed_state' and 'movement_trend'.
        
        # Assuming v0.2 relies on provided 'snapshot' fields.
        # If the builder puts sufficient info, great. If not, we infer.
        # "recovery_detected" -> movement_trend == "stable" or "recovering"
        
        if movement_trend in ["stable", "recovering"] and posture != "low_height" and posture != "on_floor":
             recovery_detected = True
        
        # Estimate Time in Low Posture
        # If observed state is low_height/on_floor, we assume it persists from the fall event.
        # We don't have the exact fall timestamp in the simplified dict.
        # Let's parse generated_at vs window start? No.
        # Let's assume for v0.2 we rely on 'temporal_pattern' or 'hypotheses' providing more context,
        # OR we just say "if fall detected and status is STILL on floor, time is significant".
        # To strictly implement "time_in_low_posture >= 10", we need that data.
        # Let's look for "duration_seconds" in time_window. If the fall happened, it happened within this window.
        # If the window is 30s and we are still on floor, it *could* be > 10s.
        # Let's add a placeholder logic: if window > 10s and fall detected, assume critical duration for safety.
        # This aligns with "Conservative Decision".
        
        window_duration = snapshot.get("time_window", {}).get("duration_seconds", 0)
        
        # Rule 1: Fall + Low Posture + Long Duration (Critical)
        if fall_hypothesis and posture in ["low_height", "on_floor"]:
             rules_triggered.append("Fall + Low Posture")
             # If we are strictly conservative:
             if window_duration >= 10 and not recovery_detected:
                 decision = "NOTIFY_CAREGIVER"
                 risk_level = "critical"
                 recommended_next_step = "notify"
                 reasoning_parts.append("Confirmed fall with persistent low posture (>10s estimate).")
                 rules_triggered.append("Long Duration (>10s)")
             else:
                 # Short duration or uncertainty
                 decision = "REQUEST_CONFIRMATION"
                 risk_level = "medium"
                 recommended_next_step = "ask_confirmation"
                 reasoning_parts.append("Fall detected but duration in low posture is short or recent.")
        
        # Rule 2: Fall with Recovery
        elif fall_hypothesis and recovery_detected:
             rules_triggered.append("Fall with Recovery")
             decision = "MONITOR"
             risk_level = "medium"
             recommended_next_step = "wait"
             reasoning_parts.append("Fall detected but subject shows signs of recovery/stability.")
             
        # Rule 3: Instability (No Fall)
        elif pattern_type in ["instability", "repeated_instability"]:
            rules_triggered.append("Instability Pattern")
            decision = "MONITOR"
            risk_level = "medium"
            recommended_next_step = "wait"
            reasoning_parts.append("Instability detected without confirmed fall.")
            
        # Rule 4: Normal/Ignore
        else:
             rules_triggered.append("Normal/Baseline")
             if total_events > 0:
                  reasoning_parts.append(f"Observed {total_events} events, no critical pattern.")
                  decision = "IGNORE"
             else:
                  reasoning_parts.append("No significant events.")
                  decision = "IGNORE"

        # Add logic to check ON_FLOOR duration and escalate decision.
        is_fall_detected = fall_hypothesis is not None and fall_hypothesis.get("type", "").lower() == "fall"
        is_potential_fall = fall_hypothesis is not None and fall_hypothesis.get("type", "").lower() == "possible_fall"

        if is_fall_detected or is_potential_fall:
            # Check for prolonged floor time detected by Analysis Engine
        # User Requirement: Treat as informational family notification (non-emergency)
            if "prolonged_floor_immobility" in snapshot.get("detected_patterns", []) or float(snapshot.get("on_floor_duration_seconds", 0.0)) > 25.0:
                 decision = "NOTIFY_FAMILY_INFO"
                 risk_level = "high" # Downgraded from critical per requirement
                 rules_triggered.append("confirmed_fall_by_duration")
                 reasoning_parts.append(f"Person on floor > 25s - Triggering family information update")
                 recommended_next_step = "notify_family"
            
            elif float(snapshot.get("on_floor_duration_seconds", 0.0)) > 15.0:
                # Fallback for generic long duration without specific event
                 decision = "NOTIFY_CAREGIVER"
                 risk_level = "critical"
                 rules_triggered.append(f"prolonged_immobility_detected")
                 reasoning_parts.append(f"Person on floor > 15s - Immediate notification recommended")
                 recommended_next_step = "notify"
                 
            elif is_fall_detected:
                 rules_triggered.append("potential_fall_monitoring")
                 decision = "MONITOR"
                 risk_level = "medium"
                 reasoning_parts.append("Potential fall detected, monitoring for recovery or escalation.")
                 recommended_next_step = "wait"

        # Final Safeguard
        if not decision:
            decision = "MONITOR"
            risk_level = "low"
            reasoning_parts.append("Fallback decision.")

        result = {
            "decision": decision,
            "decision_confidence": 1.0,
            "reasoning": " ".join(reasoning_parts),
            "risk_level": risk_level,
            "recommended_next_step": recommended_next_step,
            "snapshot_id": snapshot_id,
            "decision_version": "0.2",
            "generated_at": self._iso_format(current_time_ts)
        }
        
        # Emit DECISION_ENGINE log
        emit_log(
            log_type="DECISION_ENGINE",
            payload={
                "snapshot_id": snapshot_id,
                "final_decision": decision,
                "rules_triggered": rules_triggered,
                "risk_assessment": risk_level,
                "notes": " ".join(reasoning_parts)
            },
            trace_id=snapshot_id,
            component="decision_engine"
        )
        
        return result
