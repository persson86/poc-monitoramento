import uuid
import time
import json
import os
import logging
import datetime
from typing import List, Dict, Any, Optional
from shared.logging_contracts import emit_log

logger = logging.getLogger("AnalysisSnapshotEngine")
# Configure if not already configured
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

SNAPSHOTS_DIR = "analysis_snapshots"

class AnalysisSnapshotEngine:
    """
    Engine responsible for analyzing recent events and producing a semantic
    Analysis Snapshot of the world state.
    """

    def __init__(self):
        pass

    def _ensure_directory(self, path: str):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create directory {path}: {e}")

    def analyze_window(self, events: List[Dict[str, Any]], window_seconds: float = 30.0, trigger_reason: str = "TIMER", on_floor_duration_seconds: float = 0.0) -> Dict[str, Any]:
        """
        Analyzes a list of events (presumably from a recent window) and generates a snapshot.
        
        Args:
            events: List of event dictionaries.
            window_seconds: The duration of the window these events cover (for metadata).
        """
        current_time = time.time()
        start_time = current_time - window_seconds
        
        # Filter strictly by time if needed, but assuming caller passes relevant events
        # We will sort them by timestamp
        sorted_events = sorted(events, key=lambda x: x.get("timestamp", 0))
        
        if sorted_events:
            start_time = sorted_events[0].get("timestamp", start_time)
            end_time = sorted_events[-1].get("timestamp", current_time)
        else:
             end_time = current_time

        # --- Analysis Logic (Deterministic Heuristics) ---
        
        # 1. Grouping & Counting
        event_types = {}
        composite_events = []
        involved_entities = set() # Placeholder for entity tracking
        
        for evt in sorted_events:
            etype = evt.get("event_type", "unknown")
            event_types[etype] = event_types.get(etype, 0) + 1
            
            if evt.get("event_category") == "composite":
                composite_events.append(evt)
            
            # Extract entities if available (future proofing)
            # if "person_id" in evt.get("signals", {})... 
            # For now, we assume single subject context implied
            involved_entities.add("person_0") 

        # 2. Pattern Detection & Reasoning
        world_state = "normal"
        risk_level = "low"
        detected_patterns = []
        reasoning_trace = []
        
        # Pattern: Fall Detection
        potential_falls = [e for e in composite_events if e.get("event_type") == "POTENTIAL_FALL"]
        
        # Pre-check for rapid movements (moved here to be available for early reasoning)
        rapid_movements = event_types.get("RAPID_VERTICAL_MOVEMENT", 0)
        if rapid_movements > 0:
            detected_patterns.append("rapid_vertical_movement")
            reasoning_trace.append(f"Observed {rapid_movements} rapid movement events")
            
        # 3. Check for CONFIRMED_FALL_BY_DURATION (High Priority Override)
        confirmed_duration_falls = [e for e in events if e.get("event_type") == "CONFIRMED_FALL_BY_DURATION"]
        if confirmed_duration_falls:
            world_state = "fall_confirmed"
            risk_level = "critical"
            # Use the confidence from the event or default to 0.95
            evt_conf = confirmed_duration_falls[0].get("confidence_hint", 0.95)
            # Duration bonus logic from standard flow might try to cap/modify, but we set a strong baseline here.
            # We can let the later 'duration bonus' logic run, but we ensure we start high.
            # Actually, let's explicitly handle it here to ensure sovereignity.
            
            detected_patterns.append("prolonged_floor_immobility")
            reasoning_trace.append("CRITICAL: Confirmed fall by duration threshold")
            
            # We might still want to add hypotheses, so we let it flow, but we set the critical state.
            
        # 4. Standard Fall Hypotheses (if not already confirmed by duration)
        if world_state != "fall_confirmed":
             if potential_falls:
                world_state = "possible_fall_detected"
                risk_level = "high"
                
                # Check confidence of latest fall event
                latest_fall = potential_falls[-1]
                base_conf = latest_fall.get("confidence_hint", 0.0)
                
                # Apply duration bonus (up to +0.15 max)
                duration_bonus = min(on_floor_duration_seconds * 0.02, 0.15)
                final_conf = min(base_conf + duration_bonus, 1.0)
                
                if final_conf > 0.8:
                    risk_level = "critical"
                    world_state = "possible_fall_confirmed"
                    
                    # Emit COMPOSITE_EVENT log (CONFIRMED state)
                    triggering_events = latest_fall.get("event_chain", [])
                    time_window = window_seconds
                    
                    reasoning = f"High confidence validation - world state: {world_state}"
                    if duration_bonus > 0:
                        reasoning += f" (+{duration_bonus:.2f} duration boost)"
                    
                    emit_log(
                        log_type="COMPOSITE_EVENT",
                        payload={
                            "composite_event_id": latest_fall.get("id"),
                            "composite_type": "POTENTIAL_FALL",
                            "triggering_events": triggering_events,
                            "time_window_seconds": float(time_window),
                            "confidence": float(final_conf),
                            "state": "CONFIRMED",
                            "reasoning_summary": reasoning
                        },
                        trace_id=latest_fall.get("id"),
                        component="analysis_snapshot_engine"
                    )
                
                reasoning_trace.append(f"Detected {len(potential_falls)} POTENTIAL_FALL events.")
                reasoning_trace.append(f"Latest fall confidence: {final_conf:.2f} (base: {base_conf}, bonus: {duration_bonus:.2f})")
        else:
             # If already confirmed by duration, we still log checking potential falls for context
             if potential_falls:
                 reasoning_trace.append(f"Also detected {len(potential_falls)} motion-based potential falls.")

        # Pattern: Rapid Movement
        # This check is now conditional on risk_level, and the initial rapid_movements check is above.
        # This ensures that if a fall is already critical, rapid movement doesn't downgrade it.
        if rapid_movements > 0 and risk_level == "low":
            risk_level = "medium"
            reasoning_trace.append(f"Observed {rapid_movements} rapid vertical movements.")

        # Pattern: Immobility (if we had those events)
        # immobility_events = event_types.get("IMMOBILE_UPDATE", 0)
        # if immobility_events > 0: ...

        if not sorted_events:
            reasoning_trace.append("No events observed in window.")

        # 3. Construct Summary of Supporting Events
        supporting_events_summary = []
        for evt in sorted_events:
            # Brief summary
            supporting_events_summary.append({
                "id": evt.get("id"),
                "type": evt.get("event_type"),
                "timestamp": evt.get("timestamp")
            })

        # 4. Global Confidence
        # Simple heuristic: if critical, we are quite confident something is wrong
        snapshot_confidence = 0.5
        if risk_level == "critical": snapshot_confidence = 0.9
        elif risk_level == "high": snapshot_confidence = 0.8
        elif risk_level == "medium": snapshot_confidence = 0.7
        elif sorted_events: snapshot_confidence = 0.6 # We saw something

        # 5. Build Snapshot
        snapshot_id = str(uuid.uuid4())
        
        snapshot = {
            "snapshot_id": snapshot_id,
            "timestamp": current_time,
            "window_start": start_time,
            "window_end": end_time,
            "world_state": world_state,
            "confidence": snapshot_confidence,
            "risk_level": risk_level,
            "involved_entities": list(involved_entities),
            "supporting_events": supporting_events_summary,
            "detected_patterns": detected_patterns,
            "reasoning_trace": "; ".join(reasoning_trace),
            "on_floor_duration_seconds": on_floor_duration_seconds,
            "version": "1.0"
        }
        
        # Emit CLOSED state logs for all composite events processed
        for comp_evt in composite_events:
            emit_log(
                log_type="COMPOSITE_EVENT",
                payload={
                    "composite_event_id": comp_evt.get("id"),
                    "composite_type": comp_evt.get("event_type"),
                    "triggering_events": comp_evt.get("event_chain", []),
                    "time_window_seconds": float(window_seconds),
                    "confidence": float(comp_evt.get("confidence_hint", 0.0)),
                    "state": "CLOSED",
                    "reasoning_summary": "Event processed in analysis window"
                },
                trace_id=comp_evt.get("id"),
                component="analysis_snapshot_engine"
            )
        
        # Build hypotheses from world state and patterns
        hypotheses = []
        if world_state != "normal":
            # Map internal states to DecisionEngine expected types
            h_type = "unknown"
            if "fall" in world_state:
                h_type = "fall"
            elif world_state == "possible_fall_detected":
                h_type = "possible_fall"
            
            hypotheses.append({
                "type": h_type,
                "description": world_state,
                "confidence": snapshot_confidence
            })
        
        # Add hypothesis for significant floor time
        if on_floor_duration_seconds > 5.0 and world_state != "normal":
             hypotheses.append({
                 "type": "duration_concern",
                 "duration": on_floor_duration_seconds,
                 "description": f"prolonged_floor_time({on_floor_duration_seconds:.1f}s)"
             })
             
        # Add patterns as structured hypotheses
        for p in detected_patterns:
            hypotheses.append({
                "type": "pattern",
                "subtype": p,
                "description": p
            })
        
        # Extract composite event IDs
        composite_event_ids = [evt.get("id") for evt in composite_events]
        
        # KEY FIX: update snapshot with the built hypotheses
        snapshot["hypotheses"] = hypotheses
        
        # Emit ANALYSIS_SNAPSHOT log
        emit_log(
            log_type="ANALYSIS_SNAPSHOT",
            payload={
                "snapshot_id": snapshot_id,
                "window_start": float(start_time),
                "window_end": float(end_time),
                "observed_state": world_state,
                "atomic_event_counts": event_types,
                "composite_events": composite_event_ids,
                "patterns_detected": detected_patterns,
                "hypotheses": hypotheses,
                "human_readable_summary": "; ".join(reasoning_trace) if reasoning_trace else "No significant events observed",
                "trigger_reason": trigger_reason,
                "on_floor_duration_seconds": on_floor_duration_seconds
            },
            trace_id=snapshot_id,
            component="analysis_snapshot_engine"
        )
        
        return snapshot

    def persist_snapshot(self, snapshot: Dict[str, Any]) -> Optional[str]:
        """
        Saves the snapshot to analysis_snapshots/YYYY-MM-DD/
        """
        try:
            ts = snapshot["timestamp"]
            date_str = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
            dir_path = os.path.join(SNAPSHOTS_DIR, date_str)
            self._ensure_directory(dir_path)
            
            filename = f"{ts:.3f}_snapshot.json"
            filepath = os.path.join(dir_path, filename)
            
            with open(filepath, 'w') as f:
                json.dump(snapshot, f, indent=2)
                
            logger.info(f"Snapshot persisted: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to persist snapshot: {e}")
            return None
