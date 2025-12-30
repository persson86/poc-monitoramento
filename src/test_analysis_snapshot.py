import os
import json
import argparse
from analysis.analysis_snapshot import AnalysisSnapshotEngine

EVENTS_DIR = "events"

def load_recent_events(limit: int = 20) -> list:
    """Load the most recent events from the events directory."""
    all_events = []
    if not os.path.exists(EVENTS_DIR):
        print("No events directory found.")
        return []

    # Walk through all date directories
    for date_dir in sorted(os.listdir(EVENTS_DIR)):
        path = os.path.join(EVENTS_DIR, date_dir)
        if not os.path.isdir(path):
            continue
            
        for fname in os.listdir(path):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(path, fname), 'r') as f:
                        all_events.append(json.load(f))
                except Exception as e:
                    print(f"Error loading {fname}: {e}")
    
    # Sort by timestamp descending
    all_events.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return all_events[:limit]

def main():
    print("--- Analysis Snapshot Test ---")
    
    # 1. Load Events
    events = load_recent_events(50) # Load last 50 events
    print(f"Loaded {len(events)} recent events.")
    
    if not events:
        print("No events to analyze. Run detector first.")
        return

    # 2. Instantiate Engine
    engine = AnalysisSnapshotEngine()
    
    # 3. Analyze
    print("Running analysis (window=last events)...")
    snapshot = engine.analyze_window(events)
    
    # 4. Print Result
    print("\n=== SNAPSHOT GENERATED ===")
    print(json.dumps(snapshot, indent=2))
    
    # 5. Persist
    path = engine.persist_snapshot(snapshot)
    if path:
        print(f"\nSnapshot saved to: {path}")

if __name__ == "__main__":
    main()
