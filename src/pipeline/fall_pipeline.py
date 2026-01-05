import time
import uuid
import logging
from typing import Dict, Any, Optional, List
from shared.logging_contracts import emit_log
from analysis.analysis_snapshot import AnalysisSnapshotEngine
from decision.decision_engine import DecisionEngine
from decision.llm_arbiter import LLMDecisionArbiter
from decision.communication_policy import evaluate_communication_policy

logger = logging.getLogger("FallPipeline")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

class FallDetectionPipeline:
    """
    Encapsulates the logic for detecting falls, managing events, and generating decisions/alerts.
    Designed to be driven by either a camera feed (real-time) or a simulation (deterministic).
    """

    def __init__(self):
        # Components
        self.snapshot_engine = AnalysisSnapshotEngine()
        self.decision_engine = DecisionEngine()
        self.llm_arbiter = LLMDecisionArbiter(enabled=True)

        # State Configuration
        self.motion_threshold = 0.18
        self.cooldown_seconds = 2.0
        self.snapshot_interval = 10.0
        self.t_confirm_fall = 25.0

        # Runtime State
        self.recent_events = []
        self.last_snapshot_time = 0
        self.last_event_time = 0
        self.frame_count = 0
        
        # ON_FLOOR Tracking
        self.floor_enter_time = None
        self.on_floor_duration_seconds = 0.0
        self.duration_fall_emitted = False
        
        # Snapshot Deduplication
        self.last_snapshot_state = None
        self.last_snapshot_trigger = None
        self.critical_event_occurred = False
        self.critical_event_reason = None
        self.state_change_occurred = False
        self.last_observed_state = None
        
        # Atomic Events State (for Camera)
        self.prev_center_y = None
        self.prev_time = None
        self.last_event_time = 0

    def process_landmarks(self, timestamp: float, landmarks: Any, frame_shape: tuple):
        """
        Process landmarks from a camera frame.
        """
        h, w = frame_shape[:2]
        LEFT_HIP = 23
        RIGHT_HIP = 24
        
        left_hip = landmarks[LEFT_HIP]
        right_hip = landmarks[RIGHT_HIP]
        center_y = (left_hip.y + right_hip.y) / 2.0
        
        # Determine current state based on vertical position
        current_state = "ON_FLOOR" if center_y > 0.7 else "STANDING"
        
        # Atomic Logic (Motion)
        self._process_atomic_motion(timestamp, center_y)
        
        # Delegate to state processing
        self.process_state(timestamp, current_state)

    def _process_atomic_motion(self, now: float, center_y: float):
        if self.prev_center_y is not None and self.prev_time is not None:
            dy = center_y - self.prev_center_y
            dt = now - self.prev_time
            
            velocity_y = dy / dt if dt > 0 else 0
            
            threshold_passed = (
                dy > self.motion_threshold
                and dt < 0.6
                and (now - self.last_event_time) > self.cooldown_seconds
            )
            
            # Simplified Atomic Event Emission for Pipeline
            if threshold_passed:
                atomic_event_id = str(uuid.uuid4())
                confidence = min(abs(dy) / (self.motion_threshold * 2), 1.0)
                
                # Emit atomic event log
                emit_log(
                    log_type="ATOMIC_EVENT",
                    payload={
                        "event_id": atomic_event_id,
                        "event_type": "RAPID_VERTICAL_MOVEMENT",
                        "raw_value": float(dy),
                        "decision": "TRIGGERED"
                    },
                    trace_id=atomic_event_id,
                    component="atomic_event_detector"
                )
                
                event_data = {
                    "id": atomic_event_id,
                    "event_type": "RAPID_VERTICAL_MOVEMENT",
                    "event_category": "motion",
                    "timestamp": now,
                    "confidence_hint": confidence
                }
                self.recent_events.append(event_data)
                
                # Check for POTENTIAL_FALL composite
                if dy > (self.motion_threshold * 1.5):
                    self._trigger_potential_fall(now, atomic_event_id, dt)
                    
                self.last_event_time = now
                
        self.prev_center_y = center_y
        self.prev_time = now

    def _trigger_potential_fall(self, now: float, trigger_id: str, time_window: float):
        composite_id = str(uuid.uuid4())
        composite_event = {
            "id": composite_id,
            "event_type": "POTENTIAL_FALL",
            "event_category": "composite",
            "timestamp": now,
            "event_chain": [trigger_id],
            "confidence_hint": 0.85
        }
        self.recent_events.append(composite_event)
        
        emit_log(
            log_type="COMPOSITE_EVENT",
            payload={
                "composite_event_id": composite_id,
                "composite_type": "POTENTIAL_FALL",
                "state": "OPEN",
                "reasoning_summary": "Rapid vertical movement"
            },
            trace_id=composite_id,
            component="composite_event_detector"
        )
        
        self.critical_event_occurred = True
        self.critical_event_reason = "CRITICAL_EVENT"

    def process_state(self, timestamp: float, current_state: str):
        """
        Process a single time step based on explicit state (e.g., from Simulation).
        Does NOT process landmarks/motion, only state-based logic (Duration).
        """
        self._update_floor_duration(timestamp, current_state)
        self._check_duration_fall(timestamp, current_state)
        self._check_state_transition(current_state)
        self._manage_snapshots(timestamp, current_state)

    def _update_floor_duration(self, now: float, current_state: str):
        if current_state == "ON_FLOOR":
            if self.floor_enter_time is None:
                self.floor_enter_time = now
            self.on_floor_duration_seconds = now - self.floor_enter_time
        else:
            self.floor_enter_time = None
            self.on_floor_duration_seconds = 0.0
            self.duration_fall_emitted = False

    def _check_duration_fall(self, now: float, current_state: str):
        if (current_state == "ON_FLOOR" and 
            self.on_floor_duration_seconds >= self.t_confirm_fall and 
            not self.duration_fall_emitted):
            
            self.duration_fall_emitted = True
            composite_id = str(uuid.uuid4())
            
            logger.info(f"⏳ CONFIRMED_FALL_BY_DURATION triggered ({self.on_floor_duration_seconds:.1f}s)")
            
            # Create event object
            composite_event = {
                "id": composite_id,
                "event_type": "CONFIRMED_FALL_BY_DURATION",
                "event_category": "composite",
                "timestamp": now,
                "event_chain": [], 
                "confidence_hint": 0.95,
                "on_floor_duration": self.on_floor_duration_seconds
            }
            self.recent_events.append(composite_event)
            
            # Emit log
            emit_log(
                log_type="COMPOSITE_EVENT",
                payload={
                    "composite_event_id": composite_id,
                    "composite_type": "CONFIRMED_FALL_BY_DURATION",
                    "triggering_events": [],
                    "time_window_seconds": float(self.on_floor_duration_seconds),
                    "confidence": 0.95,
                    "state": "CONFIRMED",
                    "reasoning_summary": f"Person on floor for {self.on_floor_duration_seconds:.1f}s (Threshold: {self.t_confirm_fall}s)"
                },
                trace_id=composite_id,
                component="composite_event_detector"
            )
            
            self.critical_event_occurred = True
            self.critical_event_reason = "CONFIRMED_FALL_BY_DURATION"

    def _check_state_transition(self, current_state: str):
        if self.last_observed_state is not None and self.last_observed_state != current_state:
            if "ON_FLOOR" in [self.last_observed_state, current_state]:
                self.state_change_occurred = True
                logger.info(f"🔄 State transition: {self.last_observed_state} → {current_state}")
        self.last_observed_state = current_state

    def _manage_snapshots(self, now: float, current_state: str):
        trigger_reason = None
        should_generate_snapshot = False
        
        # Initial snapshot time sync
        if self.last_snapshot_time == 0:
            self.last_snapshot_time = now

        if self.critical_event_occurred:
            should_generate_snapshot = True
            trigger_reason = self.critical_event_reason if self.critical_event_reason else "CRITICAL_EVENT"
        elif self.state_change_occurred:
            should_generate_snapshot = True
            trigger_reason = "STATE_CHANGE"
        elif now - self.last_snapshot_time >= self.snapshot_interval:
            should_generate_snapshot = True
            trigger_reason = "TIMER"
        
        if should_generate_snapshot:
            # Deduplication
            skip_snapshot = False
            if (current_state == self.last_snapshot_state and 
                trigger_reason == self.last_snapshot_trigger and
                trigger_reason != "TIMER"):
                skip_snapshot = True
                # logger.info(f"⏭️ Skipping redundant snapshot (state={current_state}, trigger={trigger_reason})")
            
            # Force snapshot if we have critical events even if simple state matches
            if self.critical_event_occurred:
                skip_snapshot = False

            if not skip_snapshot:
                # IMPORTANT: If critical event occurred, ensure we iterate even if recent_events is empty?
                # Actually recent_events should have the composite event if critical.
                if self.recent_events or self.critical_event_occurred:
                     self._execute_decision_pipeline(now, trigger_reason)
                
                # Update tracking
                self.last_snapshot_state = current_state
                self.last_snapshot_trigger = trigger_reason
            
            # Reset flags
            self.critical_event_occurred = False
            self.critical_event_reason = None
            self.state_change_occurred = False
            self.last_snapshot_time = now

    def _execute_decision_pipeline(self, now: float, trigger_reason: str):
        snapshot = self.snapshot_engine.analyze_window(
            self.recent_events, 
            window_seconds=self.snapshot_interval,
            trigger_reason=trigger_reason,
            on_floor_duration_seconds=self.on_floor_duration_seconds
        )
        
        decision_result = self.decision_engine.decide(snapshot)
        
        preliminary_decision = {
            "decision": decision_result["decision"],
            "decision_confidence": decision_result["decision_confidence"],
            "reasoning": decision_result["reasoning"]
        }
        
        # Explicitly force LLM execution for Family Info events
        should_force_llm = (decision_result["decision"] == "NOTIFY_FAMILY_INFO")
        
        llm_result = self.llm_arbiter.arbitrate(
            snapshot, 
            preliminary_decision, 
            force_observe=should_force_llm
        )
        
        policy_result = evaluate_communication_policy(
            decision_result,
            llm_result,
            snapshot["snapshot_id"],
            on_floor_duration_seconds=self.on_floor_duration_seconds
        )
        
        # Clear/Aging logic for events could go here, for now strictly clear
        self.recent_events = []
