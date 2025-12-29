import time
import math
from collections import deque

class FallDetector:
    def __init__(
        self,
        window_seconds=1.0,
        min_drop_ratio=0.25,
        max_angle_deg=45
    ):
        self.window_seconds = window_seconds
        self.min_drop_ratio = min_drop_ratio
        self.max_angle_deg = max_angle_deg

        self.history = deque()
        self.last_fall_time = 0

    def _avg_height(self, landmarks):
        ys = [lm.y for lm in landmarks]
        return sum(ys) / len(ys)

    def _torso_angle(self, landmarks):
        # Shoulder midpoint → hip midpoint
        ls = landmarks[11]  # left shoulder
        rs = landmarks[12]  # right shoulder
        lh = landmarks[23]  # left hip
        rh = landmarks[24]  # right hip

        shoulder_y = (ls.y + rs.y) / 2
        hip_y = (lh.y + rh.y) / 2

        shoulder_x = (ls.x + rs.x) / 2
        hip_x = (lh.x + rh.x) / 2

        dx = hip_x - shoulder_x
        dy = hip_y - shoulder_y

        angle_rad = math.atan2(dy, dx)
        angle_deg = abs(math.degrees(angle_rad))

        return angle_deg

    def update(self, landmarks):
        now = time.time()

        avg_height = self._avg_height(landmarks)
        angle = self._torso_angle(landmarks)

        self.history.append((now, avg_height, angle))

        # Remove frames antigos
        while self.history and now - self.history[0][0] > self.window_seconds:
            self.history.popleft()

        if len(self.history) < 2:
            return None

        oldest = self.history[0]
        newest = self.history[-1]

        height_drop = newest[1] - oldest[1]

        fall_detected = (
            height_drop > self.min_drop_ratio and
            newest[2] > self.max_angle_deg and
            now - self.last_fall_time > 2.0
        )

        if fall_detected:
            self.last_fall_time = now
            return {
                "type": "FALL_DETECTED",
                "timestamp": now,
                "message": "Fall detected (pose + motion)"
            }

        return None