import cv2
import time
import argparse
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import event_engine

# =========================
# Argumentos
# =========================
parser = argparse.ArgumentParser()
parser.add_argument(
    "--source",
    type=str,
    default="webcam",
    help="Fonte de vídeo: 'webcam' ou caminho para vídeo"
)
args = parser.parse_args()

# =========================
# MediaPipe Pose
# =========================
MODEL_PATH = "models/pose_landmarker_lite.task"
base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
options = vision.PoseLandmarkerOptions(
    base_options=base_options,
    output_segmentation_masks=False
)
pose_detector = vision.PoseLandmarker.create_from_options(options)

# =========================
# Fonte de vídeo
# =========================
source_name = "webcam"
input_type = "webcam"
if args.source == "webcam":
    cap = cv2.VideoCapture(0)
    print("🎥 Usando webcam")
else:
    cap = cv2.VideoCapture(args.source)
    source_name = args.source
    input_type = "file"
    print(f"🎥 Usando vídeo: {args.source}")

if not cap.isOpened():
    raise RuntimeError("❌ Não foi possível abrir a fonte de vídeo")

# =========================
# Variáveis de estado
# =========================
prev_center_y = None
prev_time = None
motion_threshold = 0.18 # Sensitivity for vertical movement
cooldown_seconds = 2.0
last_event_time = 0
frame_count = 0

LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12

print("▶️ Teste iniciado. Pressione 'q' para sair.")
print("ℹ️ Eventos v1.1 serão salvos na pasta 'events/'")

# =========================
# Loop principal
# =========================
while True:
    ret, frame = cap.read()
    if not ret:
        print("⏹️ Fim da fonte de vídeo")
        break
    
    frame_count += 1
    h, w, _ = frame.shape
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    result = pose_detector.detect(mp_image)

    if result.pose_landmarks:
        landmarks = result.pose_landmarks[0]

        left_hip = landmarks[LEFT_HIP]
        right_hip = landmarks[RIGHT_HIP]
        center_y = (left_hip.y + right_hip.y) / 2.0

        # Visualization
        for lm in landmarks:
            cx, cy = int(lm.x * w), int(lm.y * h)
            cv2.circle(frame, (cx, cy), 3, (0, 255, 0), -1)

        now = time.time()

        if prev_center_y is not None and prev_time is not None:
            dy = center_y - prev_center_y # Positive dy means moving DOWN (y increases downwards)
            dt = now - prev_time

            # Detection Logic
            if (
                dy > motion_threshold  # Significant downward movement
                and dt < 0.6          # Fast movement
                and (now - last_event_time) > cooldown_seconds
            ):
                # 1. Emit Observable Fact: RAPID_VERTICAL_MOVEMENT
                # This is a pure physical observation.
                velocity_y = dy / dt if dt > 0 else 0
                
                signals = {
                    "motion": {
                        "vertical_displacement": float(dy),
                        "velocity_y": float(velocity_y),
                        "direction": "down"
                    },
                    "posture": {
                        "hip_center_y": float(center_y),
                        "keypoints_count": len(landmarks)
                    }
                }
                
                temporal_ctx = {
                    "frame_id": frame_count,
                    "time_since_last_event": now - last_event_time
                }

                atomic_event = event_engine.emit_event(
                    event_type="RAPID_VERTICAL_MOVEMENT",
                    event_category=event_engine.CATEGORY_MOTION,
                    signals=signals,
                    source={
                        "module": "test_fall_detector",
                        "camera_id": source_name,
                        "input_type": input_type
                    },
                    temporal_context=temporal_ctx,
                    derived_hypotheses=["rapid_descent", "potential_instability"],
                    severity_hint=event_engine.SEVERITY_MEDIUM
                )
                
                print(f"🚨 EVENTO: RAPID_VERTICAL_MOVEMENT (dy={dy:.2f})")

                # Store ID for traceability
                # In a real system, we might maintain a rolling window of recent events
                recent_atomic_ids = [atomic_event["id"]]

                # 2. Derive Composite Event: POTENTIAL_FALL
                # If the movement is very strong, we suggest a fall.
                if dy > (motion_threshold * 1.5):
                     event_engine.emit_event(
                        event_type="POTENTIAL_FALL",
                        event_category=event_engine.CATEGORY_COMPOSITE,
                        signals=signals, # Share same signals
                        source={
                            "module": "test_fall_detector",
                            "camera_id": source_name,
                            "input_type": input_type
                        },
                        temporal_context=temporal_ctx,
                        derived_hypotheses=["fall_detected", "occupant_on_floor"],
                        event_chain=recent_atomic_ids, # Traceability: which atomic events triggered this?
                        severity_hint=event_engine.SEVERITY_HIGH,
                        confidence_hint=0.85 # Example heuristic
                    )
                     print("⚠️ EVENTO COMPOSTO: POTENTIAL_FALL (Linked to Atomic Events)")

                last_event_time = now

        prev_center_y = center_y
        prev_time = now

        cv2.putText(
            frame,
            "Event Engine v1.1 Active",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2
        )

    cv2.imshow("Event Platform Test", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        print("🛑 Encerrado pelo usuário")
        break

cap.release()
cv2.destroyAllWindows()
print("✅ Finalizado")