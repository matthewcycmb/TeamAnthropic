"""
Snorlax Focus Buddy — Pi server
Runs on the Raspberry Pi 4. Controls 2 servos, runs CV, exposes Flask API.

DEPENDENCIES (install on Pi):
  sudo apt update
  sudo apt install -y python3-pip python3-opencv python3-flask python3-picamera2 pigpio
  sudo pip3 install pigpio --break-system-packages
  sudo systemctl enable pigpiod && sudo systemctl start pigpiod

WIRING:
  Servo 1 signal -> GPIO 17 (pin 11)
  Servo 2 signal -> GPIO 27 (pin 13)
  Servo VCC      -> external 5V (NOT Pi 5V — SG90 spikes will brown out the Pi)
  Servo GND      -> common ground with Pi GND

RUN:
  python3 pi_server.py
  Server listens on 0.0.0.0:5000
  Find Pi IP from laptop:  ping raspberrypi.local   OR   hostname -I on the Pi
"""

import cv2
import time
import threading
from flask import Flask, jsonify, Response, request
import pigpio
from picamera2 import Picamera2

# ─────────────────────────── CONFIG ───────────────────────────
SERVO_1_PIN = 17
SERVO_2_PIN = 27

# Pulse widths in microseconds (1000=0°, 1500=90°, 2000=180°)
# Calibrated 2026-05-27 via calibrate_servos.py
SERVO_1_LOCKED_US   = 1300
SERVO_1_UNLOCKED_US = 2300
SERVO_2_LOCKED_US   = 1300   # not yet wired; placeholder
SERVO_2_UNLOCKED_US = 2300   # not yet wired; placeholder

# Frame diff detection
SLOT_ROI = (200, 150, 240, 200)   # (x, y, w, h) — region of camera frame to watch
                                   # tune so it covers exactly the phone slot
EMPTY_REF_FRAME = None             # captured at startup
PHONE_PIXEL_THRESHOLD = 0.08       # fraction of ROI pixels changed = phone present
HAND_PIXEL_THRESHOLD = 0.25        # bigger change = a hand is in there

# ─────────────────────────── STATE ───────────────────────────
state = {
    "phone_detected": False,
    "hand_detected": False,
    "locked": False,
    "last_escape_attempt": 0,
}
state_lock = threading.Lock()

# ─────────────────────────── HARDWARE ───────────────────────────
pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("pigpio daemon not running. sudo systemctl start pigpiod")

def set_servos(state):
    """state: 'locked' or 'unlocked'"""
    if state == 'locked':
        pi.set_servo_pulsewidth(SERVO_1_PIN, SERVO_1_LOCKED_US)
        pi.set_servo_pulsewidth(SERVO_2_PIN, SERVO_2_LOCKED_US)
    else:
        pi.set_servo_pulsewidth(SERVO_1_PIN, SERVO_1_UNLOCKED_US)
        pi.set_servo_pulsewidth(SERVO_2_PIN, SERVO_2_UNLOCKED_US)
    time.sleep(0.5)
    pi.set_servo_pulsewidth(SERVO_1_PIN, 0)
    pi.set_servo_pulsewidth(SERVO_2_PIN, 0)

# Start unlocked
set_servos('unlocked')

# ─────────────────────────── CAMERA ───────────────────────────
picam = Picamera2()
picam.configure(picam.create_video_configuration(main={"size": (640, 480), "format": "RGB888"}))
picam.start()
time.sleep(2)  # let auto-exposure settle

latest_frame = None
frame_lock = threading.Lock()

def grab_loop():
    """Continuously grab frames, run detection, update state."""
    global latest_frame, EMPTY_REF_FRAME

    # Capture empty reference frame at startup
    time.sleep(1)
    ref = picam.capture_array()
    ref_gray = cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY)
    EMPTY_REF_FRAME = cv2.GaussianBlur(ref_gray, (21, 21), 0)
    print("[INFO] Empty reference frame captured. Slot should be EMPTY at startup.")

    while True:
        frame = picam.capture_array()
        bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # Detection: frame diff on the slot ROI
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)
        diff = cv2.absdiff(EMPTY_REF_FRAME, gray)
        x, y, w, h = SLOT_ROI
        roi_diff = diff[y:y+h, x:x+w]
        thresh = cv2.threshold(roi_diff, 25, 255, cv2.THRESH_BINARY)[1]
        changed_ratio = (thresh > 0).sum() / thresh.size

        with state_lock:
            state["phone_detected"] = bool(changed_ratio > PHONE_PIXEL_THRESHOLD)
            # Escape detection disabled — venue lighting too unstable.
            # UI triggers escapes locally via the S key instead.
            state["hand_detected"] = False

        # Draw ROI + status onto frame for debug stream
        cv2.rectangle(bgr, (x, y), (x+w, y+h), (0, 255, 0), 2)
        label = f"phone={state['phone_detected']} hand={state['hand_detected']} locked={state['locked']}"
        cv2.putText(bgr, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(bgr, f"diff={changed_ratio:.2f}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        with frame_lock:
            latest_frame = bgr

        time.sleep(0.05)  # ~20 fps

threading.Thread(target=grab_loop, daemon=True).start()

# ─────────────────────────── FLASK API ───────────────────────────
app = Flask(__name__)

# CORS for laptop browser
@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp

@app.route("/status")
def status():
    with state_lock:
        return jsonify(dict(state))

@app.route("/lock", methods=["POST"])
def lock():
    set_servos('locked')
    with state_lock:
        state["locked"] = True
    return jsonify({"ok": True, "locked": True})

@app.route("/unlock", methods=["POST"])
def unlock():
    set_servos('unlocked')
    with state_lock:
        state["locked"] = False
        state["hand_detected"] = False
    return jsonify({"ok": True, "locked": False})

@app.route("/recalibrate", methods=["POST"])
def recalibrate():
    """Re-capture empty reference frame. Slot must be empty when calling."""
    global EMPTY_REF_FRAME
    ref = picam.capture_array()
    gray = cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY)
    EMPTY_REF_FRAME = cv2.GaussianBlur(gray, (21, 21), 0)
    return jsonify({"ok": True})

def gen_mjpeg():
    while True:
        with frame_lock:
            f = latest_frame
        if f is None:
            time.sleep(0.05)
            continue
        ok, jpg = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            continue
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")
        time.sleep(0.05)

@app.route("/stream")
def stream():
    return Response(gen_mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    print("[INFO] Snorlax Pi server starting on :5000")
    app.run(host="0.0.0.0", port=5000, threaded=True)
