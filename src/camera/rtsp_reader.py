import cv2
import time
import threading
import logging
from typing import Optional
from .frame_buffer import FrameBuffer

logger = logging.getLogger(__name__)

class RTSPReader:
    """
    Reads frames from an RTSP stream in a separate thread.
    Handles connection loss and automatic reconnection.
    """
    def __init__(self, rtsp_url: str, frame_buffer: FrameBuffer, reconnect_delay: int = 5):
        self.rtsp_url = rtsp_url
        self.frame_buffer = frame_buffer
        self.reconnect_delay = reconnect_delay
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        # Simple heuristic to differentiate stream from file
        self.is_stream = self.rtsp_url.lower().startswith(('rtsp://', 'rtsps://', 'udp://', 'http://', 'https://'))

    def start(self):
        """Start the reader thread."""
        if self.running:
            return
        
        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run, args=(), daemon=True)
        self.thread.start()
        logger.info(f"RTSPReader started for {self.rtsp_url} (Stream mode: {self.is_stream})")

    def stop(self):
        """Stop the reader thread."""
        self.running = False
        self._stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        logger.info("RTSPReader stopped")

    def _run(self):
        cap = None
        while self.running and not self._stop_event.is_set():
            try:
                if cap is None or not cap.isOpened():
                    source = self.rtsp_url
                    # Support webcam index passed as string
                    if isinstance(source, str) and source.isdigit():
                         source = int(source)
                         
                    logger.info(f"Opening source: {source}")
                    cap = cv2.VideoCapture(source)
                    
                    if not cap.isOpened():
                        msg = "Failed to open source."
                        if self.is_stream:
                            logger.error(f"{msg} Retrying in {self.reconnect_delay}s...")
                            time.sleep(self.reconnect_delay)
                            continue
                        else:
                            logger.error(f"{msg} File not found or invalid. Stopping.")
                            self.running = False
                            break
                    
                    logger.info("Source connected.")

                ret, frame = cap.read()
                
                if not ret:
                    if self.is_stream:
                        logger.warning("Stream read failed. Reconnecting...")
                        cap.release()
                        cap = None
                        time.sleep(self.reconnect_delay)
                        continue
                    else:
                        logger.info("End of file reached.")
                        self.running = False
                        break

                # Valid frame, put into buffer
                self.frame_buffer.put(frame)

            except Exception as e:
                logger.exception(f"Error in RTSPReader loop: {e}")
                if cap:
                    cap.release()
                cap = None
                if self.is_stream:
                    time.sleep(self.reconnect_delay)
                else:
                    self.running = False # Stop on exception for files too? Or retry? Usually stop.
                    break

        if cap:
            cap.release()
