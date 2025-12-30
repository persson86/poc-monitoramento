import uuid
import time
import json
import os
import logging
import datetime
from typing import List, Dict, Any, Optional

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

    def analyze_window(self, events: List[Dict[str, Any]], window_seconds: float = 30.0) -> Dict[str, Any]:
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
        if potential_falls:
            world_state = "person_unstable"
            risk_level = "high"
            detected_patterns.append("fall_sequence_detected")
            
            # Check confidence of latest fall event
            latest_fall = potential_falls[-1]
            conf = latest_fall.get("confidence_hint", 0.0)
            if conf > 0.8:
                risk_level = "critical"
                world_state = "possible_fall_confirmed"
            
            reasoning_trace.append(f"Detected {len(potential_falls)} POTENTIAL_FALL events.")
            reasoning_trace.append(f"Latest fall confidence: {conf}")

        # Pattern: Rapid Movement
        rapid_movements = event_types.get("RAPID_VERTICAL_MOVEMENT", 0)
        if rapid_movements > 0 and risk_level == "low":
            risk_level = "medium"
            detected_patterns.append("sudden_motion")
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
            "version": "1.0"
        }
        
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
