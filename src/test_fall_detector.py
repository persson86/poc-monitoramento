import cv2
import time
import argparse
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

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
if args.source == "webcam":
    cap = cv2.VideoCapture(0)
    print("🎥 Usando webcam")
else:
    cap = cv2.VideoCapture(args.source)
    print(f"🎥 Usando vídeo: {args.source}")

if not cap.isOpened():
    raise RuntimeError("❌ Não foi possível abrir a fonte de vídeo")

# =========================
# Variáveis de estado
# =========================
prev_center_y = None
prev_time = None
motion_threshold = 0.18
cooldown_seconds = 2.0
last_fall_time = 0

LEFT_HIP = 23
RIGHT_HIP = 24

print("▶️ Teste iniciado. Pressione 'q' para sair.")

# =========================
# Loop principal
# =========================
while True:
    ret, frame = cap.read()
    if not ret:
        print("⏹️ Fim da fonte de vídeo")
        break

    h, w, _ = frame.shape
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    result = pose_detector.detect(mp_image)

    if result.pose_landmarks:
        landmarks = result.pose_landmarks[0]

        left_hip = landmarks[LEFT_HIP]
        right_hip = landmarks[RIGHT_HIP]
        center_y = (left_hip.y + right_hip.y) / 2.0

        # Desenhar landmarks
        for lm in landmarks:
            cx, cy = int(lm.x * w), int(lm.y * h)
            cv2.circle(frame, (cx, cy), 3, (0, 255, 0), -1)

        now = time.time()

        if prev_center_y is not None and prev_time is not None:
            dy = center_y - prev_center_y
            dt = now - prev_time

            if (
                dy > motion_threshold
                and dt < 0.6
                and (now - last_fall_time) > cooldown_seconds
            ):
                print("🚨 EVENTO:", {
                    "type": "FALL_DETECTED",
                    "timestamp": now,
                    "message": "Fall detected (pose + motion)"
                })
                last_fall_time = now

        prev_center_y = center_y
        prev_time = now

        cv2.putText(
            frame,
            "POSE ACTIVE",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2
        )

    cv2.imshow("Fall Detection Test", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        print("🛑 Encerrado pelo usuário")
        break

cap.release()
cv2.destroyAllWindows()
print("✅ Finalizado")