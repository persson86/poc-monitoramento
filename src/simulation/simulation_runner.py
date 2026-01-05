import json
import time
import logging
import argparse
import sys
from shared.logging_contracts import emit_log
from pipeline.fall_pipeline import FallDetectionPipeline

logger = logging.getLogger("SimulationRunner")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

class SimulationRunner:
    def __init__(self, scenario_path: str):
        self.scenario_path = scenario_path
        self.pipeline = FallDetectionPipeline()
        self.scenario_data = self._load_scenario()
        
    def _load_scenario(self):
        try:
            with open(self.scenario_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load scenario: {e}")
            sys.exit(1)

    def run(self, speed_factor: float = 0.1):
        """
        speed_factor: 1s simulation = speed_factor seconds real time.
        """
        logger.info(f"Starting simulation: {self.scenario_data['scenario_id']}")
        
        # Emit Start Log
        emit_log("SIMULATION_START", {
            "scenario_id": self.scenario_data['scenario_id'],
            "description": self.scenario_data['description']
        }, "sim-start", "simulation_runner")
        
        timeline = sorted(self.scenario_data['timeline'], key=lambda x: x['t'])
        start_time_sim = 0.0
        max_time = timeline[-1]['t'] + 5.0 # Run a bit past the last event
        
        # Real-world base time for logs
        real_start_time = time.time()
        
        time_step = 0.1 # Simulation resolution
        current_sim_time = 0.0
        current_state = self.scenario_data['initial_state']['observed_state']
        
        timeline_idx = 0
        
        while current_sim_time <= max_time:
            # Check for timeline events
            while timeline_idx < len(timeline) and timeline[timeline_idx]['t'] <= current_sim_time:
                event = timeline[timeline_idx]
                if event['type'] == 'STATE':
                    current_state = event['observed_state']
                    
                    emit_log("SIMULATION_EVENT", {
                        "t": event['t'],
                        "injected_state": current_state
                    }, f"sim-evt-{timeline_idx}", "simulation_runner")
                    
                    logger.info(f"⏱️ T={current_sim_time:.1f}s | Injected State: {current_state}")
                
                timeline_idx += 1
            
            # Inject into pipeline
            # Use real_start_time + current_sim_time to generate "pseudo-real" timestamps that monotonically increase
            pseudo_now = real_start_time + current_sim_time
            self.pipeline.process_state(pseudo_now, current_state)
            
            # Advance time
            current_sim_time += time_step
            
            # Sleep to match speed factor (optional, for visibility)
            if speed_factor > 0:
                time.sleep(time_step * speed_factor)
                
        emit_log("SIMULATION_END", {
            "scenario_id": self.scenario_data['scenario_id'],
            "duration_sim": current_sim_time
        }, "sim-end", "simulation_runner")
        logger.info("Simulation Complete")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", type=str)
    args = parser.parse_args()
    runner = SimulationRunner(args.scenario)
    runner.run(speed_factor=0.01) # Fast forward by default
