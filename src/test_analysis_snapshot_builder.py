import os
import json
import logging
from processing.analysis_snapshot import AnalysisSnapshotBuilder

EVENTS_DIR = "events"

def load_events(limit: int = 50) -> list:
    all_events = []
    if not os.path.exists(EVENTS_DIR):
        return []
    
    # Simple loader - scan all dates
    for d in sorted(os.listdir(EVENTS_DIR)):
        path = os.path.join(EVENTS_DIR, d)
        if os.path.isdir(path):
            files = [f for f in os.listdir(path) if f.endswith(".json") and "ANALYSIS_SNAPSHOT" not in f]
            for f in files:
                try:
                    with open(os.path.join(path, f)) as fo:
                        all_events.append(json.load(fo))
                except: pass
    
    # Sort descending
    all_events.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return all_events[:limit]

def main():
    print("--- Testing AnalysisSnapshotBuilder ---")
    
    events = load_events(30)
    print(f"Loaded {len(events)} events.")
    
    if not events:
        print("No events found. Generate events first using test_fall_detector.py")
        return

    builder = AnalysisSnapshotBuilder()
    
    print("Building snapshot...")
    snapshot = builder.build_snapshot(events)
    
    print("\n--- JSON OUTPUT ---")
    print(json.dumps(snapshot, indent=2))
    
    print("\n--- SAVING ---")
    path = builder.save_snapshot(snapshot)
    print(f"Saved to: {path}")

if __name__ == "__main__":
    main()
