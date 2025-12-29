import queue
import threading
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

class FrameBuffer:
    """
    A thread-safe buffer for video frames.
    Implements a 'drop oldest' strategy when full to ensure low latency.
    """
    def __init__(self, max_size: int = 1):
        self._queue = queue.Queue(maxsize=max_size)
        self._lock = threading.Lock()

    def put(self, frame: Any) -> None:
        """
        Put a frame into the buffer. If full, drop the oldest frame.
        """
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            # Buffer is full. Remove oldest item and add new one.
            with self._lock:
                try:
                    # Double check if full inside lock and remove one
                    if self._queue.full():
                        _ = self._queue.get_nowait()
                except queue.Empty:
                    pass # Someone else emptied it, proceed to put
                
                # Try putting again
                try:
                    self._queue.put_nowait(frame)
                except queue.Full:
                    # Should be rare if max_size >= 1
                    logger.warning("FrameBuffer full even after dropping")

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Any:
        """
        Get the next frame.
        """
        return self._queue.get(block=block, timeout=timeout)

    def empty(self) -> bool:
        return self._queue.empty()
    
    def qsize(self) -> int:
        return self._queue.qsize()
