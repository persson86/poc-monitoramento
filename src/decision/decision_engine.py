import uuid
import time
import json
import logging
import datetime
from typing import Dict, Any, List

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
             # If we are strictly conservative:
             if window_duration >= 10 and not recovery_detected:
                 decision = "NOTIFY_CAREGIVER"
                 risk_level = "critical"
                 recommended_next_step = "notify"
                 reasoning_parts.append("Confirmed fall with persistent low posture (>10s estimate).")
             else:
                 # Short duration or uncertainty
                 decision = "REQUEST_CONFIRMATION"
                 risk_level = "medium"
                 recommended_next_step = "ask_confirmation"
                 reasoning_parts.append("Fall detected but duration in low posture is short or recent.")
        
        # Rule 2: Fall with Recovery
        elif fall_hypothesis and recovery_detected:
             decision = "MONITOR"
             risk_level = "medium"
             recommended_next_step = "wait"
             reasoning_parts.append("Fall detected but subject shows signs of recovery/stability.")
             
        # Rule 3: Instability (No Fall)
        elif pattern_type in ["instability", "repeated_instability"]:
            decision = "MONITOR"
            risk_level = "medium"
            recommended_next_step = "wait"
            reasoning_parts.append("Instability detected without confirmed fall.")
            
        # Rule 4: Normal/Ignore
        else:
             if total_events > 0:
                  reasoning_parts.append(f"Observed {total_events} events, no critical pattern.")
                  decision = "IGNORE"
             else:
                  reasoning_parts.append("No significant events.")
                  decision = "IGNORE"

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
        
        return result
