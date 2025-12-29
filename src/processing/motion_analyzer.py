import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

class MotionAnalyzer:
    """
    Analyzes video frames to detect motion using background subtraction / frame differencing.
    """
    def __init__(self, sensitivity: int = 500, blur_size: int = 21, threshold: int = 25):
        """
        :param sensitivity: Minimum area of changed pixels to consider as motion.
        :param blur_size: Size of GaussianBlur kernel (must be odd).
        :param threshold: Pixel intensity difference threshold.
        """
        self.sensitivity = sensitivity
        self.blur_size = blur_size
        self.threshold_val = threshold
        self.prev_frame = None

    def detect_motion(self, frame: np.ndarray) -> tuple[bool, float]:
        """
        Detects motion in the current frame compared to the previous one.
        Returns:
            (is_moving, motion_score)
            motion_score is the area of changed pixels.
        """
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (self.blur_size, self.blur_size), 0)

        if self.prev_frame is None:
            self.prev_frame = gray
            return False, 0.0

        # Compute difference
        delta = cv2.absdiff(self.prev_frame, gray)
        thresh = cv2.threshold(delta, self.threshold_val, 255, cv2.THRESH_BINARY)[1]
        
        # Dilate to fill holes
        thresh = cv2.dilate(thresh, None, iterations=2)

        # Find countours (optional, but good for area calculation)
        # Alternatively, just countNonZero for total motion score
        # Using countNonZero is faster and sufficient for "global motion" score
        motion_area = cv2.countNonZero(thresh)

        # Update reference frame
        # We update every frame to adapt to slow lighting changes (inter-frame diff)
        self.prev_frame = gray

        is_moving = motion_area > self.sensitivity
        
        return is_moving, float(motion_area)
