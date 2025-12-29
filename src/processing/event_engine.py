import time
import logging
from typing import List, Dict, Any, Set

logger = logging.getLogger(__name__)

# Event Types
EVENT_MOTION_STARTED = "MOTION_STARTED"
EVENT_MOTION_STOPPED = "MOTION_STOPPED"
EVENT_IMMOBILE = "IMMOBILE_UPDATE"

class EventEngine:
    """
    State machine to generate high-level events from raw motion signals.
    """
    STATE_STILL = "STILL"
    STATE_MOVING = "MOVING"

    def __init__(self, cooldown: float = 2.0, immobile_milestones: List[float] = None):
        """
        :param cooldown: Seconds of no motion required to transition from MOVING to STILL.
        :param immobile_milestones: List of seconds to trigger immobile events (e.g. [5, 10, 30]).
        """
        self.cooldown = cooldown
        self.immobile_milestones = sorted(immobile_milestones) if immobile_milestones else [5.0, 10.0, 30.0, 60.0]
        
        self.state = self.STATE_STILL
        self.last_motion_time = 0.0
        self.state_start_time = time.time()
        # Track which milestones have been emitted for the current STILL session
        self.emitted_milestones: Set[float] = set()

    def process(self, is_moving: bool, timestamp: float) -> List[Dict[str, Any]]:
        """
        Process the current motion state and return generated events.
        """
        events = []

        if is_moving:
            self.last_motion_time = timestamp
            
            if self.state == self.STATE_STILL:
                # Transition to MOVING
                self.state = self.STATE_MOVING
                self.state_start_time = timestamp
                self.emitted_milestones.clear() # Reset milestones
                events.append({
                    "type": EVENT_MOTION_STARTED,
                    "timestamp": timestamp,
                    "message": "Motion started detected"
                })
        
        else:
            # Not moving right now
            if self.state == self.STATE_MOVING:
                # Check cooldown
                if (timestamp - self.last_motion_time) > self.cooldown:
                    # Transition to STILL
                    self.state = self.STATE_STILL
                    self.state_start_time = timestamp
                    self.emitted_milestones.clear() # Reset milestones (just in case)
                    events.append({
                        "type": EVENT_MOTION_STOPPED,
                        "timestamp": timestamp,
                        "duration": timestamp - self.state_start_time,
                        "message": "Motion stopped (cooldown elapsed)"
                    })
            
            elif self.state == self.STATE_STILL:
                # Calculate how long we have been still
                current_duration = timestamp - self.state_start_time
                
                # Check milestones
                for milestone in self.immobile_milestones:
                    if current_duration >= milestone and milestone not in self.emitted_milestones:
                        self.emitted_milestones.add(milestone)
                        events.append({
                            "type": EVENT_IMMOBILE,
                            "timestamp": timestamp,
                            "duration": current_duration,
                            "milestone_seconds": milestone,
                            "message": f"Immobile for {milestone} seconds"
                        })

        return events
