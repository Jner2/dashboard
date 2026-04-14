import threading
import time
from typing import Optional

import cv2


class UsbCamera:
    """Captures frames from a USB camera (V4L2 device index) in a background thread."""

    def __init__(
        self,
        device_index: int,
        reconnect_delay_s: int = 5,
        jpeg_quality: int = 72,
        jpeg_fps: float = 6.0,
        jpeg_max_width: int = 960,
    ):
        self.device_index = device_index
        self.reconnect_delay_s = reconnect_delay_s
        self.jpeg_quality = max(40, min(95, int(jpeg_quality)))
        self.jpeg_fps = max(1.0, float(jpeg_fps))
        self.jpeg_max_width = max(320, int(jpeg_max_width))
        self._lock = threading.Lock()
        self._jpeg: Optional[bytes] = None
        self._connected: bool = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_jpeg_ts: float = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def is_connected(self) -> bool:
        with self._lock:
            return self._connected

    def get_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._jpeg

    def _encode_display_jpeg(self, frame):
        now = time.monotonic()
        if self._jpeg is not None and (now - self._last_jpeg_ts) < (1.0 / self.jpeg_fps):
            return self._jpeg

        out = frame
        h, w = frame.shape[:2]
        if w > self.jpeg_max_width:
            scale = self.jpeg_max_width / float(w)
            new_h = max(1, int(round(h * scale)))
            out = cv2.resize(frame, (self.jpeg_max_width, new_h), interpolation=cv2.INTER_AREA)

        ok, jpg = cv2.imencode('.jpg', out, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
        if not ok:
            return self._jpeg

        self._last_jpeg_ts = now
        return jpg.tobytes()

    def _run(self) -> None:
        cap = None
        while not self._stop.is_set():
            try:
                cap = cv2.VideoCapture(self.device_index, cv2.CAP_V4L2)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(self.device_index)
                if not cap.isOpened():
                    with self._lock:
                        self._connected = False
                        self._jpeg = None
                    time.sleep(self.reconnect_delay_s)
                    continue

                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass

                with self._lock:
                    self._connected = True

                while not self._stop.is_set():
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        break
                    with self._lock:
                        self._jpeg = self._encode_display_jpeg(frame)
                        self._connected = True
                    time.sleep(0.04)
            except Exception:
                with self._lock:
                    self._connected = False
                    self._jpeg = None
                time.sleep(self.reconnect_delay_s)
            finally:
                if cap is not None:
                    try:
                        cap.release()
                    except Exception:
                        pass
                    cap = None
                with self._lock:
                    self._connected = False
                    self._jpeg = None
                if not self._stop.is_set():
                    time.sleep(self.reconnect_delay_s)
