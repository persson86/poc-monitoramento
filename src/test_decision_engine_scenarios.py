import json
import logging
from decision.decision_engine import DecisionEngine

def create_mock_snapshot(case_name, events, posture, movement, duration, fall_conf=0.0):
    """Helper to create mock snapshots for scenarios."""
    hypotheses = []
    if fall_conf > 0:
        hypotheses.append({"type": "possible_fall", "confidence": fall_conf})
    
    return {
        "snapshot_id": f"mock_{case_name}",
        "time_window": {"duration_seconds": duration},
        "event_summary": {"total_events": events},
        "observed_state": {"posture": posture, "movement_trend": movement},
        "temporal_pattern": {"pattern_type": "instability" if events > 0 else "quiet"},
        "hypotheses": hypotheses,
        "human_readable_summary": f"Mock summary for {case_name}"
    }

def main():
    print("--- Testing DecisionEngine v0.2 Scenarios ---")
    engine = DecisionEngine()
    
    scenarios = [
        # Case 1: Fall, Low Posture, Long Time (>10s) -> Expect NOTIFY
        ("Critical Fall", create_mock_snapshot("critical", 10, "on_floor", "unstable", 30, 0.9)),
        
        # Case 2: Fall, Low Posture, Short Time (<10s) -> Expect REQUEST_CONFIRMATION
        ("Recent Fall", create_mock_snapshot("recent", 5, "on_floor", "unstable", 5, 0.9)),

        # Case 3: Fall, but Recovered (Standing) -> Expect MONITOR
        ("Recovered Fall", create_mock_snapshot("recovered", 10, "standing", "stable", 30, 0.9)),
        
        # Case 4: Instability only -> Expect MONITOR
        ("Instability", create_mock_snapshot("instability", 5, "standing", "unstable", 30, 0.0)),
        
        # Case 5: Quiet -> Expect IGNORE
        ("Quiet", create_mock_snapshot("quiet", 0, "unknown", "unknown", 30, 0.0)),
    ]
    
    for name, snap in scenarios:
        print(f"\n[Scenario: {name}]")
        decision = engine.decide(snap)
        print(f"DECISION: {decision['decision']}")
        print(f"REASON:   {decision['reasoning']}")
        print(f"VERSION:  {decision['decision_version']}")

if __name__ == "__main__":
    main()
