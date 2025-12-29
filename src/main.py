import cv2
import time
import signal
import sys
import logging
import argparse
import queue
from camera.frame_buffer import FrameBuffer
from camera.rtsp_reader import RTSPReader
from processing.motion_analyzer import MotionAnalyzer
from processing.event_engine import EventEngine

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Main")

def main():
    parser = argparse.ArgumentParser(description="RTSP Event Detection MVP - Ingestion Phase")
    parser.add_argument("--source", type=str, required=True, help="RTSP URL or Video File Path")
    parser.add_argument("--buffer-size", type=int, default=1, help="Size of frame buffer")
    parser.add_argument("--no-display", action="store_true", help="Disable GUI window (headless mode)")
    
    args = parser.parse_args()

    # Setup Buffer and Reader
    buffer = FrameBuffer(max_size=args.buffer_size)
    reader = RTSPReader(rtsp_url=args.source, frame_buffer=buffer)

    # Setup Processing
    motion_analyzer = MotionAnalyzer()
    event_engine = EventEngine()

    # NOTE: We rely on default Python SIGINT handler which raises KeyboardInterrupt
    # This ensures it is caught by our try/except block.

    try:
        reader.start()
        
        logger.info(f"Starting main loop. Press 'q' to quit. Source: {args.source}")
        
        frame_count = 0
        last_log = time.time()

        while True:
            # Check if reader is still alive (if it crashed or stopped)
            if not reader.running and buffer.empty():
                logger.info("Reader stopped and buffer empty. Exiting main loop.")
                break

            try:
                # Use a short timeout so we can check for exit conditions/signals frequently
                frame = buffer.get(timeout=0.1)
            except queue.Empty:
                # Timeout, just loop back to check reader status and allow waitKey
                if not args.no_display:
                    # Provide opportunity to process GUI events even if no frame
                    if cv2.waitKey(10) & 0xFF == ord('q'):
                         logger.info("Quit requested via GUI (during idle)")
                         break
                continue
            
            frame_count += 1
            timestamp = time.time()

            # --- Processing ---
            is_moving, score = motion_analyzer.detect_motion(frame)
            events = event_engine.process(is_moving, timestamp)

            for event in events:
                logger.info(f">> EVENT GENERATED: {event}")
            
            # ------------------
            
            # Throttling for local files (Simulate Real-Time)
            # Simple heuristic: if not starting with rtsp/http, assume local file
            is_stream = args.source.lower().startswith(('rtsp://', 'rtsps://', 'udp://', 'http://', 'https://'))
            if not is_stream:
                time.sleep(1/30.0)

            # Log FPS every 5 seconds
            if time.time() - last_log > 5.0:
                logger.info(f"Processed {frame_count} frames. Buffer size: {buffer.qsize()}")
                last_log = time.time()

            if not args.no_display:
                # Visualize motion (simple red/green border or text)
                color = (0, 255, 0) if not is_moving else (0, 0, 255)
                cv2.putText(frame, f"Motion: {score:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
                
                status_text = f"State: {event_engine.state}"
                cv2.putText(frame, status_text, (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 0), 2)

                cv2.imshow("RTSP Event Detection MVP", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    logger.info("Quit requested via GUI")
                    break

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt caught in main loop")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
    finally:
        logger.info("Cleaning up...")
        reader.stop()
        if not args.no_display:
            # Ensure windows are closed
            for i in range(5):
                cv2.waitKey(1)
                cv2.destroyAllWindows()
                cv2.waitKey(1)
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    main()
