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
    Builder for creating rich, human-readable Analysis Snapshots (v1.2) from a sequence of events.
    """

    def __init__(self):
        pass

    def _ensure_directory(self, path: str):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create directory {path}: {e}")

    def _iso_format(self, timestamp: float) -> str:
        return datetime.datetime.fromtimestamp(timestamp).isoformat()

    def build_snapshot(self, events: List[Dict[str, Any]], window_seconds: float = 30.0) -> Dict[str, Any]:
        """
        Builds a full Analysis Snapshot (v1.2) from a list of events.
        """
        current_time_ts = time.time()
        
        # Sort events
        sorted_events = sorted(events, key=lambda x: x.get("timestamp", 0))
        
        # Determine strict window based on input or events
        end_time_ts = current_time_ts
        start_time_ts = end_time_ts - window_seconds
        
        # Only consider events within the window? 
        # The prompt says "Ler todos os eventos JSON dentro da janela".
        # Assuming the caller might filter, but we should double check or just process what's given.
        # Ideally we process what is passed.
        
        # Metrics Calculation
        total_events = len(sorted_events)
        event_types_count = {}
        atomic_events = []
        composite_events = []
        raw_event_ids = []
        
        for evt in sorted_events:
            etype = evt.get("event_type", "unknown")
            event_types_count[etype] = event_types_count.get(etype, 0) + 1
            raw_event_ids.append(evt.get("id"))
            
            if evt.get("event_category") == "composite":
                composite_events.append(evt)
            else:
                atomic_events.append(evt)

        # Inference Logic (Heuristics)
        # 1. Posture & Movement Trend
        posture = "unknown"
        movement_trend = "unknown"
        confidence = 0.0
        
        has_fall_event = any(e.get("event_type") == "POTENTIAL_FALL" for e in composite_events)
        has_rapid_movement = any(e.get("event_type") == "RAPID_VERTICAL_MOVEMENT" for e in atomic_events)
        
        if has_fall_event:
            posture = "low_height"
            movement_trend = "unstable"
            confidence = 0.85
        elif has_rapid_movement:
            posture = "moving"
            movement_trend = "unstable" # suggestive
            confidence = 0.6
        elif total_events > 0:
            posture = "standing" # Default assumption if active events exist but no fall
            movement_trend = "stable"
            confidence = 0.4
        else:
            posture = "unknown"
            movement_trend = "unknown"
            confidence = 1.0 # Confident that we know nothing? Or 0? Let's say 1.0 that nothing happened.

        # 2. Temporal Pattern
        pattern_type = "ambiguous"
        pattern_desc = "No significant pattern observed."
        
        if total_events == 0:
            pattern_type = "quiet"
            pattern_desc = "No events detected in the time window."
        elif has_fall_event:
            pattern_type = "instability"
            pattern_desc = "Sequence of movements culminating in a potential fall detection."
        elif event_types_count.get("RAPID_VERTICAL_MOVEMENT", 0) > 2:
            pattern_type = "repeated_instability"
            pattern_desc = "Multiple rapid vertical movements detected without confirmed fall."
        elif total_events == 1:
             pattern_type = "isolated_event"
             pattern_desc = "Single isolated event detected."

        # 3. Hypotheses
        hypotheses = []
        if has_fall_event:
            hypotheses.append({
                "type": "possible_fall",
                "supporting_events": [e.get("id") for e in composite_events if e.get("event_type") == "POTENTIAL_FALL"],
                "confidence": 0.85
            })
        elif has_rapid_movement:
             hypotheses.append({
                "type": "instability",
                "supporting_events": [e.get("id") for e in atomic_events if e.get("event_type") == "RAPID_VERTICAL_MOVEMENT"],
                "confidence": 0.6
            })
        else:
             hypotheses.append({
                "type": "normal_activity",
                "supporting_events": [],
                "confidence": 0.5
            })

        # 4. Human Readable Summary
        summary_parts = []
        if total_events == 0:
            summary_parts.append("No activity detected in the last window.")
        else:
            summary_parts.append(f"Observed {total_events} events.")
            if has_fall_event:
                summary_parts.append("Detected a potential fall scenario.")
                summary_parts.append("The subject appears to be at low height/on floor.")
            elif has_rapid_movement:
                summary_parts.append("Detected multiple rapid movements, suggesting instability.")
                summary_parts.append("Subject is likely moving but upright.")
            else:
                 summary_parts.append("Minor activity detected, currently stable.")
        
        human_readable_summary = " ".join(summary_parts)

        # Construct JSON v1.2
        snapshot = {
            "snapshot_id": str(uuid.uuid4()),
            "snapshot_version": "1.2",
            "time_window": {
                "start": self._iso_format(start_time_ts),
                "end": self._iso_format(end_time_ts),
                "duration_seconds": window_seconds
            },
            "event_summary": {
                "total_events": total_events,
                "event_types_count": event_types_count
            },
            "temporal_pattern": {
                "pattern_type": pattern_type,
                "description": pattern_desc
            },
            "observed_state": {
                "posture": posture,
                "movement_trend": movement_trend,
                "confidence": float(f"{confidence:.2f}")
            },
            "hypotheses": hypotheses,
            "human_readable_summary": human_readable_summary,
            "raw_event_ids": raw_event_ids,
            "generated_at": self._iso_format(current_time_ts)
        }
        
        return snapshot

    def save_snapshot(self, snapshot: Dict[str, Any]) -> str:
        """
        Saves to events/YYYY-MM-DD/analysis_snapshots/<timestamp>_ANALYSIS_SNAPSHOT.json
        """
        try:
            # Parse generated_at back to timestamp for filename, or just use current time
            # Using timestamp from generated_at is safer
            gen_at = snapshot["generated_at"]
            dt = datetime.datetime.fromisoformat(gen_at)
            ts = dt.timestamp()
            date_str = dt.strftime('%Y-%m-%d')
            
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
