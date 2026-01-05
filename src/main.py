import cv2
import time
import sys
import logging
import argparse
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from shared.logging_contracts import emit_log
from simulation.simulation_runner import SimulationRunner
from pipeline.fall_pipeline import FallDetectionPipeline
from camera.rtsp_reader import RTSPReader
from camera.frame_buffer import FrameBuffer

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Main")

def main():
    parser = argparse.ArgumentParser(description="Fall Detection System - Unified Runner")
    parser.add_argument("--simulation", type=str, help="Path to scenario JSON for deterministic simulation")
    parser.add_argument("--source", type=str, default="0", help="Camera source (default: webcam 0)")
    parser.add_argument("--buffer-size", type=int, default=1, help="Size of frame buffer")
    parser.add_argument("--no-display", action="store_true", help="Disable GUI window")
    
    args = parser.parse_args()

    if args.simulation:
        logger.info(f"🚀 Launching in SIMULATION mode with scenario: {args.simulation}")
        runner = SimulationRunner(args.simulation)
        runner.run(speed_factor=0.0) 
    else:
        logger.info(f"🎥 Launching in CAMERA/RTSP mode (Source: {args.source})")
        logger.info("Initializing Advanced Fall Detection Pipeline...")

        # Initialize MediaPipe Pose
        MODEL_PATH = "models/pose_landmarker_lite.task"
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            output_segmentation_masks=False
        )
        pose_detector = vision.PoseLandmarker.create_from_options(options)

        # Initialize Pipeline
        pipeline = FallDetectionPipeline()
        
        # Initialize Reader
        buffer = FrameBuffer(max_size=args.buffer_size)
        reader = RTSPReader(rtsp_url=args.source, frame_buffer=buffer)
        
        # State Visualization Helpers
        LEFT_HIP = 23
        RIGHT_HIP = 24
        
        try:
            reader.start()
            logger.info("Pipeline started.")
            
            while True:
                if not reader.running and buffer.empty():
                    break
                try:
                    frame = buffer.get(timeout=0.1)
                except:
                    if not args.no_display:
                         if cv2.waitKey(10) & 0xFF == ord('q'): break
                    continue
                
                h, w, _ = frame.shape
                timestamp = time.time()
                
                # MediaPipe Detection
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = pose_detector.detect(mp_image)
                
                if result.pose_landmarks:
                    landmarks = result.pose_landmarks[0]
                    # Drive the pipeline
                    pipeline.process_landmarks(timestamp, landmarks, frame.shape)
                    
                    # Visualization
                    if not args.no_display:
                        # Draw landmarks
                        for lm in landmarks:
                            cx, cy = int(lm.x * w), int(lm.y * h)
                            cv2.circle(frame, (cx, cy), 3, (0, 255, 0), -1)
                            
                        # Draw State Info
                        # Pipeline doesn't expose state easily purely via valid public API yet,
                        # but we can infer or add getters. 
                        # For MVP visualization:
                        left_hip = landmarks[LEFT_HIP]
                        right_hip = landmarks[RIGHT_HIP]
                        center_y = (left_hip.y + right_hip.y) / 2.0
                        state = "ON_FLOOR" if center_y > 0.7 else "STANDING"
                        color = (0, 0, 255) if state == "ON_FLOOR" else (0, 255, 0)
                        cv2.putText(frame, f"State: {state}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                        
                        if pipeline.on_floor_duration_seconds > 0:
                             cv2.putText(frame, f"Time on Floor: {pipeline.on_floor_duration_seconds:.1f}s", (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

                if not args.no_display:
                    cv2.imshow("Advanced Fall Detection", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            reader.stop()
            cv2.destroyAllWindows()
            logger.info("Shutdown complete.")

if __name__ == "__main__":
    main()
