from datetime import datetime, timezone
import os

# Module-level state for log file persistence
_log_file_handle = None
_log_directory = "logs"

def _initialize_log_file():
    """
    Initializes the log file for this execution.
    Creates logs/ directory if needed and opens a timestamped log file.
    """
    global _log_file_handle
    
    if _log_file_handle is not None:
        return  # Already initialized
    
    # Create logs directory if it doesn't exist
    os.makedirs(_log_directory, exist_ok=True)
    
    # Generate filename with ISO timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"manual_test_{timestamp}.log"
    filepath = os.path.join(_log_directory, filename)
    
    # Open file in append mode
    _log_file_handle = open(filepath, 'a', encoding='utf-8')
    print(f"📝 Log file created: {filepath}\n")

def emit_log(log_type: str, payload: dict, trace_id: str, component: str = "main"):
    """
    Emits a structured log to stdout and to a log file.
    
    Args:
        log_type: The generic type of the log (e.g., ATOMIC_EVENT, DECISION)
        payload: Dictionary of specific data to log.
        trace_id: Unique identifier for the event trace.
        component: The system component emitting the log.
    """
    # Initialize log file on first use
    _initialize_log_file()
    
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Build log lines
    lines = [
        f"[{log_type.upper()}]",
        f"timestamp={now}",
        f"component={component}",
        f"trace_id={trace_id}"
    ]
    
    for key, value in payload.items():
        val_str = str(value)
        lines.append(f"{key}={val_str}")
    
    lines.append("")  # Empty line for readability
    
    # Output to terminal
    for line in lines:
        print(line)
    
    # Output to file
    if _log_file_handle:
        for line in lines:
            _log_file_handle.write(line + '\n')
        _log_file_handle.flush()  # Ensure real-time writing
