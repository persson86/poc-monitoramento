import os
import json
import logging
from processing.analysis_snapshot import AnalysisSnapshotBuilder

EVENTS_DIR = "events"

def load_events(limit: int = 50) -> list:
    all_events = []
    if not os.path.exists(EVENTS_DIR):
        print("No events directory found.")
        return []
    
    # Scan all dates
    for d in sorted(os.listdir(EVENTS_DIR)):
        path = os.path.join(EVENTS_DIR, d)
        if os.path.isdir(path):
            files = [f for f in os.listdir(path) if f.endswith(".json") and "ANALYSIS_SNAPSHOT" not in f]
            for f in files:
                try:
                    with open(os.path.join(path, f)) as fo:
                        all_events.append(json.load(fo))
                except Exception as e:
                    print(f"Skipping {f}: {e}")
    
    # Sort descending by timestamp
    all_events.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return all_events[:limit]

def main():
    print("--- Testing AnalysisSnapshotBuilder v1.2 ---")
    
    # 1. Load recent events to simulate "what just happened"
    events = load_events(30)
    print(f"Loaded {len(events)} events (limit 30).")
    
    if not events:
        print("No events found. Please run detector to generate events first.")
        return

    # 2. Instantiate Builder
    builder = AnalysisSnapshotBuilder()
    
    # 3. Build Snapshot
    # In a real scenario, we would filter these events by the exact time window.
    # Here we just pass the events we loaded and claim they belong to the window
    # to test the summarization logic.
    print("Building snapshot for assumed window of 30s...")
    snapshot = builder.build_snapshot(events, window_seconds=30.0)
    
    # 4. Validate Human Readable Summary
    print("\n[Human Readable Summary]")
    print(f"> {snapshot.get('human_readable_summary')}")
    
    # 5. Print JSON Preview
    print("\n[JSON Structure Preview]")
    print(json.dumps(snapshot, indent=2))
    
    # 6. Save
    print("\n[Persistence]")
    path = builder.save_snapshot(snapshot)
    if path:
        print(f"Snapshot saved to: {path}")
    else:
        print("Failed to save snapshot.")

if __name__ == "__main__":
    main()
