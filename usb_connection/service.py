import glob
import logging
import os
import threading
import time
from typing import Dict, List, Optional

import cv2

from .camera import UsbCamera

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cameras: Dict[int, UsbCamera] = {}
_scanner_thread: Optional[threading.Thread] = None
_scanner_stop = threading.Event()

SCAN_INTERVAL_S = 10

# Set of device indices known to belong to the Pi's internal ISP/codec pipeline.
# Populated once via sysfs so we never waste time probing them again.
_pi_isp_indices: set = set()
_pi_isp_scanned = False


def _is_pi_isp_device(dev_name: str) -> bool:
    """Return True if a /dev/videoN is a Pi internal ISP node (not a real camera)."""
    sys_path = f'/sys/class/video4linux/{dev_name}'
    if not os.path.isdir(sys_path):
        return False
    try:
        real_path = os.path.realpath(os.path.join(sys_path, 'device'))
        return 'usb' not in real_path
    except Exception:
        return False


def _build_isp_blocklist():
    """One-time scan of sysfs to find Pi ISP devices we should skip."""
    global _pi_isp_scanned
    if _pi_isp_scanned:
        return
    _pi_isp_scanned = True
    sysfs = '/sys/class/video4linux'
    if not os.path.isdir(sysfs):
        logger.info('sysfs not available (Docker?) — skipping ISP blocklist')
        return
    for entry in os.listdir(sysfs):
        if not entry.startswith('video'):
            continue
        try:
            idx = int(entry.replace('video', ''))
        except ValueError:
            continue
        if _is_pi_isp_device(entry):
            _pi_isp_indices.add(idx)
    if _pi_isp_indices:
        logger.info('Pi ISP devices blocklisted: %s', sorted(_pi_isp_indices))


def _probe_device(index: int) -> bool:
    """Return True if the device index is a real, working video-capture device."""
    try:
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap = cv2.VideoCapture(index)
            if not cap.isOpened():
                return False
        ok, frame = cap.read()
        cap.release()
        return ok and frame is not None
    except Exception:
        return False


def _enumerate_video_devices() -> List[int]:
    """Scan /dev/video* and return indices of working capture devices.

    On bare-metal Pi: uses sysfs blocklist to skip ISP nodes.
    In Docker: probes all /dev/video* devices directly.
    Skips probing devices that are already tracked and connected to avoid
    "device busy" conflicts with the running UsbCamera instance.
    """
    _build_isp_blocklist()
    indices = []
    with _lock:
        already_tracked = {idx for idx, cam in _cameras.items() if cam.is_connected()}
    for path in sorted(glob.glob('/dev/video*')):
        try:
            idx = int(path.replace('/dev/video', ''))
        except ValueError:
            continue
        if idx in _pi_isp_indices:
            continue
        if idx in already_tracked:
            indices.append(idx)
            continue
        if _probe_device(idx):
            indices.append(idx)
            logger.info('Found working camera at /dev/video%d', idx)
    return indices


def _scan_loop() -> None:
    while not _scanner_stop.is_set():
        try:
            detected = _enumerate_video_devices()
            with _lock:
                current_indices = set(_cameras.keys())
                detected_set = set(detected)

                for idx in detected_set - current_indices:
                    logger.info('USB camera detected at /dev/video%d', idx)
                    cam = UsbCamera(idx)
                    cam.start()
                    _cameras[idx] = cam

                for idx in current_indices - detected_set:
                    logger.info('USB camera removed at /dev/video%d', idx)
                    cam = _cameras.pop(idx)
                    cam.stop()
        except Exception as exc:
            logger.warning('USB camera scan error: %s', exc)

        _scanner_stop.wait(SCAN_INTERVAL_S)


def start_usb_scanner() -> None:
    global _scanner_thread
    if _scanner_thread and _scanner_thread.is_alive():
        return
    _scanner_stop.clear()
    _scanner_thread = threading.Thread(target=_scan_loop, daemon=True)
    _scanner_thread.start()


def stop_usb_scanner() -> None:
    _scanner_stop.set()
    with _lock:
        for cam in _cameras.values():
            cam.stop()
        _cameras.clear()


def get_usb_cameras() -> Dict[int, UsbCamera]:
    with _lock:
        return dict(_cameras)


def trigger_scan() -> List[int]:
    """Run an immediate scan and return detected indices."""
    detected = _enumerate_video_devices()
    with _lock:
        current_indices = set(_cameras.keys())
        detected_set = set(detected)

        for idx in detected_set - current_indices:
            cam = UsbCamera(idx)
            cam.start()
            _cameras[idx] = cam

        for idx in current_indices - detected_set:
            cam = _cameras.pop(idx)
            cam.stop()

    return detected
