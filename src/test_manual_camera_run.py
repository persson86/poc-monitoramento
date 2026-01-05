#!/usr/bin/env python3
"""
Manual Camera Test - Complete Fall Detection Pipeline
Execute: python3 src/test_manual_camera_run.py

Runs the complete pipeline with webcam input, displaying all structured logs.
"""

import cv2
import time
import uuid
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Import all pipeline modules
from analysis.analysis_snapshot import AnalysisSnapshotEngine
from decision.decision_engine import DecisionEngine
from decision.llm_arbiter import LLMDecisionArbiter
from decision.communication_policy import evaluate_communication_policy
from shared.logging_contracts import emit_log

print("="*60)
print("🎥 MANUAL CAMERA TEST - Fall Detection Pipeline")
print("="*60)
print("Press 'q' to quit")
print("All structured logs will appear below...")
print("="*60)
print()

# Initialize MediaPipe Pose
MODEL_PATH = "models/pose_landmarker_lite.task"
base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
options = vision.PoseLandmarkerOptions(
    base_options=base_options,
    output_segmentation_masks=False
)
pose_detector = vision.PoseLandmarker.create_from_options(options)

# Initialize pipeline components
snapshot_engine = AnalysisSnapshotEngine()
decision_engine = DecisionEngine()
llm_arbiter = LLMDecisionArbiter(enabled=True)

# Open webcam
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise RuntimeError("❌ Failed to open webcam")

print("✅ Webcam opened successfully")
print()

# State tracking
prev_center_y = None
prev_time = None
motion_threshold = 0.18
cooldown_seconds = 2.0
last_event_time = 0
frame_count = 0

# Event collection for snapshots
recent_events = []
snapshot_interval = 10.0  # Generate snapshot every 10 seconds
last_snapshot_time = time.time()
critical_event_occurred = False  # Flag for immediate snapshot triggering
critical_event_reason = None

# State tracking for transition detection
last_observed_state = None
state_change_occurred = False

# Snapshot deduplication tracking
last_snapshot_state = None
last_snapshot_trigger = None

# ON_FLOOR duration tracking
floor_enter_time = None
on_floor_duration_seconds = 0.0

LEFT_HIP = 23
RIGHT_HIP = 24

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("⏹️ End of video stream")
            break
        
        now = time.time()
        frame_count += 1
        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        result = pose_detector.detect(mp_image)

        if result.pose_landmarks:
            landmarks = result.pose_landmarks[0]

            left_hip = landmarks[LEFT_HIP]
            right_hip = landmarks[RIGHT_HIP]
            center_y = (left_hip.y + right_hip.y) / 2.0
            
            # Determine current state based on vertical position
            current_state = "ON_FLOOR" if center_y > 0.7 else "STANDING"
            
            # Track ON_FLOOR duration
            if current_state == "ON_FLOOR":
                if floor_enter_time is None:
                    floor_enter_time = now
                on_floor_duration_seconds = now - floor_enter_time
            else:
                floor_enter_time = None
                on_floor_duration_seconds = 0.0
            
            # Detect state transitions (to/from ON_FLOOR)
            if last_observed_state is not None and last_observed_state != current_state:
                # Check if transition involves ON_FLOOR
                if "ON_FLOOR" in [last_observed_state, current_state]:
                    state_change_occurred = True
                    print(f"🔄 State transition: {last_observed_state} → {current_state}")
            
            # Reset duration fall flag if standing
            if current_state != "ON_FLOOR":
                duration_fall_emitted = False
            
            # CONFIRMED_FALL_BY_DURATION Logic
            T_CONFIRM_FALL = 25.0
            if (current_state == "ON_FLOOR" and 
                on_floor_duration_seconds >= T_CONFIRM_FALL and 
                not duration_fall_emitted):
                
                duration_fall_emitted = True
                composite_id = str(uuid.uuid4())
                
                print(f"⏳ CONFIRMED_FALL_BY_DURATION triggered ({on_floor_duration_seconds:.1f}s)")
                
                # Create event object
                composite_event = {
                    "id": composite_id,
                    "event_type": "CONFIRMED_FALL_BY_DURATION",
                    "event_category": "composite",
                    "timestamp": now,
                    "event_chain": [], # No atomic dependencies
                    "confidence_hint": 0.95, # High confidence due to duration
                    "on_floor_duration": on_floor_duration_seconds
                }
                recent_events.append(composite_event)
                
                # Emit log
                emit_log(
                    log_type="COMPOSITE_EVENT",
                    payload={
                        "composite_event_id": composite_id,
                        "composite_type": "CONFIRMED_FALL_BY_DURATION",
                        "triggering_events": [],
                        "time_window_seconds": float(on_floor_duration_seconds),
                        "confidence": 0.95,
                        "state": "CONFIRMED",
                        "reasoning_summary": f"Person on floor for {on_floor_duration_seconds:.1f}s (Threshold: {T_CONFIRM_FALL}s)"
                    },
                    trace_id=composite_id,
                    component="composite_event_detector"
                )
                
                # Trigger critical snapshot
                critical_event_occurred = True
                critical_event_reason = "CONFIRMED_FALL_BY_DURATION"

            # Visual feedback
            for lm in landmarks:
                cx, cy = int(lm.x * w), int(lm.y * h)
                cv2.circle(frame, (cx, cy), 3, (0, 255, 0), -1)



            # Atomic event detection
            if prev_center_y is not None and prev_time is not None:
                dy = center_y - prev_center_y
                dt = now - prev_time

                velocity_y = dy / dt if dt > 0 else 0
                atomic_event_id = str(uuid.uuid4())
                confidence = min(abs(dy) / (motion_threshold * 2), 1.0)

                threshold_passed = (
                    dy > motion_threshold
                    and dt < 0.6
                    and (now - last_event_time) > cooldown_seconds
                )

                decision = "TRIGGERED" if threshold_passed else "DISCARDED"

                # Emit atomic event log
                emit_log(
                    log_type="ATOMIC_EVENT",
                    payload={
                        "event_id": atomic_event_id,
                        "event_type": "RAPID_VERTICAL_MOVEMENT",
                        "source_signal": "vertical_motion",
                        "raw_value": float(dy),
                        "normalized_value": float(velocity_y),
                        "threshold": motion_threshold,
                        "confidence": float(confidence),
                        "decision": decision
                    },
                    trace_id=atomic_event_id,
                    component="atomic_event_detector"
                )

                if threshold_passed:
                    # Create event structure for snapshot
                    event_data = {
                        "id": atomic_event_id,
                        "event_type": "RAPID_VERTICAL_MOVEMENT",
                        "event_category": "motion",
                        "timestamp": now,
                        "confidence_hint": confidence
                    }
                    recent_events.append(event_data)

                    # Composite event for strong falls
                    if dy > (motion_threshold * 1.5):
                        composite_id = str(uuid.uuid4())
                        composite_event = {
                            "id": composite_id,
                            "event_type": "POTENTIAL_FALL",
                            "event_category": "composite",
                            "timestamp": now,
                            "event_chain": [atomic_event_id],
                            "confidence_hint": 0.85
                        }
                        recent_events.append(composite_event)

                        # Emit OPEN state
                        emit_log(
                            log_type="COMPOSITE_EVENT",
                            payload={
                                "composite_event_id": composite_id,
                                "composite_type": "POTENTIAL_FALL",
                                "triggering_events": [atomic_event_id],
                                "time_window_seconds": float(dt),
                                "confidence": 0.85,
                                "state": "OPEN",
                                "reasoning_summary": "Composite event triggered by rapid vertical movement"
                            },
                            trace_id=composite_id,
                            component="composite_event_detector"
                        )
                        
                        # Set flag for immediate snapshot
                        critical_event_occurred = True
                        critical_event_reason = "CRITICAL_EVENT"

                    last_event_time = now

            prev_center_y = center_y
            prev_time = now

            cv2.putText(
                frame,
                f"State: {current_state} ({on_floor_duration_seconds:.1f}s)",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0) if current_state == "STANDING" else (0, 0, 255),
                2
            )
            
            cv2.putText(
                frame,
                "Pipeline Active - Logs in Terminal",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2
            )
        


        # Generate snapshot on critical event, state change, OR periodically
        trigger_reason = None
        should_generate_snapshot = False
        
        if critical_event_occurred:
            should_generate_snapshot = True
            trigger_reason = critical_event_reason if critical_event_reason else "CRITICAL_EVENT"
        elif state_change_occurred:
            should_generate_snapshot = True
            trigger_reason = "STATE_CHANGE"
        elif now - last_snapshot_time >= snapshot_interval:
            should_generate_snapshot = True
            trigger_reason = "TIMER"
        
        if should_generate_snapshot:
            # Deduplication check: skip if snapshot would be redundant
            skip_snapshot = False
            if result.pose_landmarks:
                current_snapshot_state = current_state
                if (current_snapshot_state == last_snapshot_state and 
                    trigger_reason == last_snapshot_trigger and
                    trigger_reason != "TIMER"):  # Always allow timer-based snapshots
                    skip_snapshot = True
                    print(f"⏭️ Skipping redundant snapshot (state={current_snapshot_state}, trigger={trigger_reason})")
            
            if not skip_snapshot and recent_events:
                # Generate analysis snapshot
                snapshot = snapshot_engine.analyze_window(
                    recent_events, 
                    window_seconds=snapshot_interval,
                    trigger_reason=trigger_reason,
                    on_floor_duration_seconds=on_floor_duration_seconds
                )
                
                # Run decision engine
                decision_result = decision_engine.decide(snapshot)
                
                # Run LLM arbiter (observe mode)
                preliminary_decision = {
                    "decision": decision_result["decision"],
                    "decision_confidence": decision_result["decision_confidence"],
                    "reasoning": decision_result["reasoning"]
                }
                
                # Explicitly force LLM execution for Family Info events
                should_force_llm = (decision_result["decision"] == "NOTIFY_FAMILY_INFO")
                
                llm_result = llm_arbiter.arbitrate(
                    snapshot, 
                    preliminary_decision, 
                    force_observe=should_force_llm
                )
                
                # Runtime Check: Verify MESSAGE_PREVIEW for NOTIFY_FAMILY_INFO
                if decision_result["decision"] == "NOTIFY_FAMILY_INFO":
                    if not llm_result.get("message_preview_generated"):
                        print("\n❌ TEST FAILED: MESSAGE_PREVIEW not generated for NOTIFY_FAMILY_INFO")
                    else:
                        print("✅ VERIFIED: MESSAGE_PREVIEW generated for Family Info")
                
                # Evaluate communication policy (just for logging context)
                policy_result = evaluate_communication_policy(
                    decision_result,
                    llm_result,
                    snapshot["snapshot_id"],
                    on_floor_duration_seconds=on_floor_duration_seconds
                )
                
                # Clear old events
                recent_events = []
                
                # Update snapshot tracking for deduplication
                if result.pose_landmarks:
                    last_snapshot_state = current_state
                    last_snapshot_trigger = trigger_reason
            
            # Reset flags and update state tracking
            critical_event_occurred = False
            critical_event_reason = None
            state_change_occurred = False
            if result.pose_landmarks:
                last_observed_state = current_state
            last_snapshot_time = now

        cv2.imshow("Manual Camera Test - Fall Detection", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\n🛑 User requested quit")
            break

except KeyboardInterrupt:
    print("\n\n🛑 Interrupted by user (Ctrl+C)")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    cap.release()
    cv2.destroyAllWindows()
    print("\n✅ Camera released. Test complete.")
