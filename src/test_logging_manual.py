from shared.logging_contracts import emit_log

def test_manual_logging():
    print("Test 1: Atomic Event")
    emit_log(
        log_type="atomic_event",
        payload={
            "event_type": "RAPID_VERTICAL_MOVEMENT",
            "confidence": 0.91,
            "details": "Subject drop detected"
        },
        trace_id="abc12345",
        component="atomic_event_detector"
    )

    print("Test 2: Complex Payload")
    emit_log(
        log_type="decision",
        payload={
            "decision": "NOTIFY_CAREGIVER",
            "metrics": {"velocity": 2.5, "height": 0.0},
            "flags": ["motionless"]
        },
        trace_id="xyz98765",
        component="decision_engine"
    )

if __name__ == "__main__":
    test_manual_logging()
