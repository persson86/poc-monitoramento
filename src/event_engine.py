import json
import uuid
import time
import os
import logging
import datetime
from typing import Dict, Optional, List, Any, Union

# Configure local logger for the event engine
logger = logging.getLogger("EventEngine")
# Ensure logging is configured if run standalone, but usually Main configures it
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

EVENTS_DIR = "events"

# --- Taxonomy Constants ---
CATEGORY_MOTION = "motion"
CATEGORY_POSTURE = "posture"
CATEGORY_SPATIAL = "spatial"
CATEGORY_INTERACTION = "interaction"
CATEGORY_COMPOSITE = "composite"

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

def _ensure_directory(path: str):
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create directory {path}: {e}")

def emit_event(
    event_type: str,
    event_category: str,
    signals: Dict[str, Any],
    source: Optional[Dict[str, Any]] = None,
    temporal_context: Optional[Dict[str, Any]] = None,
    derived_hypotheses: Optional[List[str]] = None,
    event_chain: Optional[List[str]] = None,
    severity_hint: str = SEVERITY_MEDIUM,
    confidence_hint: float = 0.0,
    context: Optional[Dict[str, Any]] = None # Deprecated
) -> Dict[str, Any]:
    """
    Emits an event following the v1.2 contract.
    
    Args:
        event_type: Specific event name.
        event_category: High level category.
        signals: Observable facts.
        source: Information about the sensor/module.
        temporal_context: Timing info.
        derived_hypotheses: Semantic interpretations.
        event_chain: List of UUIDs of atomic events that led to this event (for composite events).
        severity_hint: visual severity indication.
        confidence_hint: generic confidence score of the detection.
    """
    current_time = time.time()
    event_id = str(uuid.uuid4())
    
    # Default source structure if not provided
    final_source = {
        "engine": "vision",
        "module": "unknown",
        "input_type": "unknown"
    }
    if source:
        final_source.update(source)

    # Construct Event v1.2
    event = {
        "id": event_id,
        "event_type": event_type,
        "event_category": event_category,
        "timestamp": current_time,
        "source": final_source,
        "signals": signals,
        "temporal_context": temporal_context or {},
        "derived_hypotheses": derived_hypotheses or [],
        "event_chain": event_chain or [],
        "severity_hint": severity_hint,
        "confidence_hint": confidence_hint,
        "version": "1.2"
    }
    
    # Persist to Disk
    try:
        date_str = datetime.datetime.fromtimestamp(current_time).strftime('%Y-%m-%d')
        date_dir = os.path.join(EVENTS_DIR, date_str)
        _ensure_directory(date_dir)

        # Filename: <timestamp>_<EVENT_TYPE>.json
        filename = f"{current_time:.3f}_{event_type}.json"
        filepath = os.path.join(date_dir, filename)

        with open(filepath, 'w') as f:
            json.dump(event, f, indent=2)
            
        logger.info(f"Event emitted: {event_type} (ID: {event_id}) -> {filepath}")

    except Exception as e:
        logger.error(f"Failed to persist event {event_id}: {e}")

    return event
