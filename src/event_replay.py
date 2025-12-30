import os
import json
import argparse
import datetime
from typing import List, Dict

EVENTS_DIR = "events"

def load_events(target_date: str = None) -> List[Dict]:
    """
    Load all events from the events directory, optionally filtered by date.
    Args:
        target_date: Date string YYYY-MM-DD
    """
    all_events = []
    
    # If date is not provided, look at all folders
    if target_date:
        dirs_to_scan = [os.path.join(EVENTS_DIR, target_date)]
    else:
        if not os.path.exists(EVENTS_DIR):
            return []
        dirs_to_scan = [os.path.join(EVENTS_DIR, d) for d in os.listdir(EVENTS_DIR) 
                        if os.path.isdir(os.path.join(EVENTS_DIR, d))]

    for day_dir in dirs_to_scan:
        if not os.path.exists(day_dir):
            continue
            
        for filename in os.listdir(day_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(day_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        event = json.load(f)
                        all_events.append(event)
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")
    
    return all_events

def format_timestamp(ts: float) -> str:
    dt = datetime.datetime.fromtimestamp(ts)
    return dt.strftime("%H:%M:%S.%f")[:-3]

def main():
    parser = argparse.ArgumentParser(description="Event Replay Mode for Offline Analysis")
    parser.add_argument("--date", type=str, help="Filter by date (YYYY-MM-DD), default all")
    parser.add_argument("--event-type", type=str, help="Filter by exact event type")
    parser.add_argument("--generate-snapshot", action="store_true", help="Generate Analysis Snapshot from replayed events")
    
    args = parser.parse_args()
    
    events = load_events(args.date)
    
    # Sort by timestamp
    events.sort(key=lambda x: x.get("timestamp", 0))
    
    if not events:
        print("No events found.")
        return

    print(f"--- REPLAY START ({len(events)} events) ---")
    
    for evt in events:
        if args.event_type and evt.get("event_type") != args.event_type:
            continue
            
        ts_str = format_timestamp(evt.get("timestamp", 0))
        etype = evt.get("event_type", "UNKNOWN")
        ecat = evt.get("event_category", "unknown")
        severity = evt.get("severity_hint", "unknown")
        
        # Summary string construction based on category
        extra_info = ""
        
        if ecat == "motion":
            signals = evt.get("signals", {}).get("motion", {})
            dy = signals.get("vertical_displacement", 0)
            extra_info = f"| dy={dy:.2f}"
            
        elif ecat == "composite":
            conf = evt.get("confidence_hint", 0)
            chain = evt.get("event_chain", [])
            extra_info = f"| confidence={conf:.2f} | chain_len={len(chain)}"
            
        print(f"[{ts_str}] {etype:<25} ({ecat}) | severity={severity:<6} {extra_info}")

    print("--- REPLAY END ---")

    # Generate Snapshot if requested
    if args.generate_snapshot:
        from analysis.analysis_snapshot import AnalysisSnapshotEngine
        print("Generating Analysis Snapshot...")
        engine = AnalysisSnapshotEngine()
        # Analyze the whole sequence as one window
        duration = events[-1].get("timestamp", 0) - events[0].get("timestamp", 0) if events else 0
        snapshot = engine.analyze_window(events, window_seconds=duration)
        
        # Save
        saved_path = engine.persist_snapshot(snapshot)
        if saved_path:
            print(f"Snapshot saved to: {saved_path}")
            # Optional: Print Preview
            print("Snapshot Preview (Reasoning):")
            print(snapshot.get("reasoning_trace", ""))

if __name__ == "__main__":
    main()
