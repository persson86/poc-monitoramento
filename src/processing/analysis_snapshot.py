import uuid
import time
import json
import os
import logging
import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger("AnalysisSnapshotBuilder")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

EVENTS_DIR = "events"

class AnalysisSnapshotBuilder:
    """
    Builder for creating rich, human-readable Analysis Snapshots from a sequence of events.
    """

    def __init__(self):
        pass

    def _ensure_directory(self, path: str):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create directory {path}: {e}")

    def build_snapshot(self, events: List[Dict[str, Any]], window_seconds: float = None) -> Dict[str, Any]:
        """
        Builds a full Analysis Snapshot (v2) from a list of events.
        """
        current_time = time.time()
        
        # Sort events
        sorted_events = sorted(events, key=lambda x: x.get("timestamp", 0))
        
        start_time = current_time
        end_time = current_time
        
        if sorted_events:
            start_time = sorted_events[0].get("timestamp", 0)
            end_time = sorted_events[-1].get("timestamp", 0)
        
        if window_seconds and not sorted_events:
             start_time = end_time - window_seconds
        
        duration = end_time - start_time
        if duration < 0: duration = 0

        # --- Metrics Calculation ---
        atomic_events = []
        composite_events = []
        vertical_displacements = []
        
        for evt in sorted_events:
            if evt.get("event_category") == "composite":
                composite_events.append(evt)
            else:
                atomic_events.append(evt)
            
            # Extract dy
            signals = evt.get("signals", {})
            if "motion" in signals:
                dy = signals["motion"].get("vertical_displacement", 0)
                if dy > 0:
                    vertical_displacements.append(dy)

        max_dy = max(vertical_displacements) if vertical_displacements else 0.0
        avg_dy = sum(vertical_displacements) / len(vertical_displacements) if vertical_displacements else 0.0

        # --- Inference Logic ---
        occupant_state = "UNKNOWN"
        state_confidence = 0.5
        hypotheses = []

        # Heuristics
        has_fall_event = any(e.get("event_type") == "POTENTIAL_FALL" for e in composite_events)
        has_rapid_movement = any(e.get("event_type") == "RAPID_VERTICAL_MOVEMENT" for e in atomic_events)
        
        if has_fall_event:
            occupant_state = "ON_FLOOR"
            state_confidence = 0.85
            hypotheses.append({
                "type": "POSSIBLE_FALL",
                "confidence": 0.85,
                "reasoning": "Multiple rapid vertical movements detected followed by potential fall event."
            })
        elif has_rapid_movement:
            occupant_state = "MOVING" # or UNSTABLE
            state_confidence = 0.7
            hypotheses.append({
                "type": "NEEDS_ATTENTION",
                "confidence": 0.6,
                "reasoning": "Rapid vertical movements detected without confirmed fall."
            })
        elif sorted_events:
            occupant_state = "STANDING" # Default assumption if active events exist but no fall
            state_confidence = 0.5
        else:
            occupant_state = "UNKNOWN"
            state_confidence = 0.0

        # --- Human Readable Summary ---
        start_str = datetime.datetime.fromtimestamp(start_time).strftime('%H:%M:%S')
        end_str = datetime.datetime.fromtimestamp(end_time).strftime('%H:%M:%S')
        
        summary_parts = []
        summary_parts.append(f"Between {start_str} and {end_str}, {len(sorted_events)} events were detected.")
        if has_rapid_movement:
            summary_parts.append("Rapid vertical movements were observed.")
        if has_fall_event:
            summary_parts.append("This pattern is consistent with a possible fall.")
            summary_parts.append("The occupant state is inferred as ON_FLOOR.")
        elif sorted_events:
            summary_parts.append("No critical patterns were identified.")
        
        human_readable_summary = " ".join(summary_parts)

        # --- Construct JSON ---
        snapshot = {
            "snapshot_id": str(uuid.uuid4()),
            "created_at": current_time,
            "time_window": {
                "start": start_time,
                "end": end_time,
                "duration_seconds": duration
            },
            "events_summary": {
                "atomic_events": [self._summarize_event(e) for e in atomic_events],
                "composite_events": [self._summarize_event(e) for e in composite_events]
            },
            "inferred_state": {
                "occupant_state": occupant_state,
                "confidence": state_confidence
            },
            "hypotheses": hypotheses,
            "metrics": {
                "max_dy": float(f"{max_dy:.3f}"),
                "avg_dy": float(f"{avg_dy:.3f}"),
                "event_count": len(sorted_events)
            },
            "human_readable_summary": human_readable_summary,
            "version": "2.0 (Snapshots)"
        }
        
        return snapshot

    def _summarize_event(self, evt: Dict) -> Dict:
        """Brief summary for embedding."""
        return {
            "id": evt.get("id"),
            "type": evt.get("event_type"),
            "timestamp": evt.get("timestamp"),
            "confidence": evt.get("confidence_hint")
        }

    def save_snapshot(self, snapshot: Dict[str, Any]) -> str:
        """
        Saves to events/YYYY-MM-DD/analysis_snapshots/<timestamp>_ANALYSIS_SNAPSHOT.json
        """
        try:
            ts = snapshot["created_at"]
            date_str = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
            
            # Construct path: events/YYYY-MM-DD/analysis_snapshots/
            base_dir = os.path.join(EVENTS_DIR, date_str, "analysis_snapshots")
            self._ensure_directory(base_dir)
            
            filename = f"{ts:.3f}_ANALYSIS_SNAPSHOT.json"
            filepath = os.path.join(base_dir, filename)
            
            with open(filepath, 'w') as f:
                json.dump(snapshot, f, indent=2)
                
            logger.info(f"Snapshot saved: {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")
            return ""
