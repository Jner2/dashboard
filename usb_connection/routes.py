import time

from flask import Blueprint, Response, jsonify, request

from .service import get_usb_cameras, trigger_scan
from usb_detection_engine import get_all_usb_latest

usb_bp = Blueprint('usb', __name__)


@usb_bp.route('/usb/status')
def usb_status():
    cameras = get_usb_cameras()
    detection_results = get_all_usb_latest()
    camera_list = []
    for idx, cam in sorted(cameras.items()):
        det = detection_results.get(idx, {})
        camera_list.append({
            'device_index': idx,
            'device_path': f'/dev/video{idx}',
            'connected': cam.is_connected(),
            'display_text': det.get('display_text', 'No detected'),
            'state': det.get('state', 'WAITING'),
            'display_state': det.get('display_state', 'WAITING'),
            'river_level_m': det.get('river_level_m'),
            'confidence_pct': det.get('confidence_pct', 0.0),
            'updated_at': det.get('updated_at'),
        })
    return jsonify({'cameras': camera_list, 'count': len(camera_list)})


def _mjpeg_generator(index: int):
    boundary = b'--frame'
    while True:
        cameras = get_usb_cameras()
        cam = cameras.get(index)
        if cam is None:
            time.sleep(1)
            continue
        jpg = cam.get_jpeg()
        if jpg is None:
            time.sleep(0.2)
            continue
        yield boundary + b'\r\n'
        yield b'Content-Type: image/jpeg\r\n'
        yield f'Content-Length: {len(jpg)}\r\n\r\n'.encode('utf-8')
        yield jpg + b'\r\n'
        time.sleep(0.12)


@usb_bp.route('/usb/<int:index>/feed')
def usb_feed(index: int):
    return Response(
        _mjpeg_generator(index),
        mimetype='multipart/x-mixed-replace; boundary=frame',
    )


@usb_bp.route('/usb/scan', methods=['POST'])
def scan():
    detected = trigger_scan()
    return jsonify({'success': True, 'detected': detected, 'count': len(detected)})
