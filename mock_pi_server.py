"""
Mock Pi server — runs on your Mac at http://localhost:5000.
Mimics pi_server.py's API so you can test index.html end-to-end without hardware.

USAGE:
  python3 mock_pi_server.py
  Then in your index.html → Pi settings → enter http://localhost:5000 → Save.
  Click "Start focus session" with 1 min selected.

BEHAVIOR (simulated):
  - Click Start → mock waits ~3s, then flips phone_detected=true.
    Triggers your JS to call /lock and enter focus page.
  - During focus session, hand_detected pulses true briefly every ~5s.
    Triggers shame audio + escape counter.
  - Timer hits 0 → JS calls /unlock → mock resets → complete page should show.
  - /stream serves a single static SVG (just so the <img> doesn't error).

NO DEPENDENCIES — stdlib only.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

PORT = 5000

state = {
    "phone_detected": False,
    "hand_detected": False,
    "locked": False,
    "last_escape_attempt": 0,
}
state_lock = threading.Lock()

# Timing trackers
poll_start_time = None   # when /status was first polled in idle state
lock_time = 0            # when /lock was called
manual_escape_until = 0  # epoch seconds; while now < this, hand_detected=true

PHONE_APPEAR_DELAY_S = 3.0      # how long after Start before "phone in slot"
ESCAPE_CYCLE_S       = 0        # 0 = disable auto-escape (manual trigger only via /trigger-escape)
ESCAPE_PULSE_S       = 0.8      # how long a manually-triggered escape lasts
ESCAPE_QUIET_S       = 3.0      # grace period after locking before any escape

STREAM_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">
  <rect width="400" height="300" fill="#1a1a1c"/>
  <text x="20" y="40" fill="#7cc36b" font-family="monospace" font-size="22" font-weight="bold">MOCK STREAM</text>
  <text x="20" y="65" fill="#888" font-family="monospace" font-size="12">No camera - running on localhost:5000</text>
  <rect x="100" y="100" width="200" height="150" fill="none" stroke="#7cc36b" stroke-width="3"/>
  <text x="135" y="180" fill="#7cc36b" font-family="monospace" font-size="14">SLOT ROI (fake)</text>
</svg>'''.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {fmt % args}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/status":
            self._handle_status()
        elif path == "/stream":
            self._handle_stream()
        else:
            self.send_error(404)

    def do_POST(self):
        global poll_start_time, lock_time, manual_escape_until
        path = urlparse(self.path).path
        if path == "/lock":
            with state_lock:
                state["locked"] = True
                state["hand_detected"] = False
            lock_time = time.time()
            self._json({"ok": True, "locked": True})
        elif path == "/unlock":
            with state_lock:
                state["locked"] = False
                state["phone_detected"] = False
                state["hand_detected"] = False
            poll_start_time = None
            lock_time = 0
            manual_escape_until = 0
            self._json({"ok": True, "locked": False})
        elif path == "/recalibrate":
            self._json({"ok": True})
        elif path == "/trigger-escape":
            # Fire hand_detected=true for ESCAPE_PULSE_S seconds, for demo purposes
            manual_escape_until = time.time() + ESCAPE_PULSE_S
            self._json({"ok": True, "triggered": True})
        else:
            self.send_error(404)

    def _handle_status(self):
        global poll_start_time
        now = time.time()
        with state_lock:
            # First idle poll = user just clicked Start
            if not state["locked"] and not state["phone_detected"] and poll_start_time is None:
                poll_start_time = now

            # Simulate phone being slid in after delay
            if (poll_start_time
                    and not state["locked"]
                    and (now - poll_start_time) > PHONE_APPEAR_DELAY_S):
                state["phone_detected"] = True

            # Escape attempts: only when manually triggered via /trigger-escape (E key in UI).
            # Auto-cycle disabled (ESCAPE_CYCLE_S=0). Quiet period after lock still applies.
            if state["locked"] and lock_time and (now - lock_time) > ESCAPE_QUIET_S:
                hand_now = now < manual_escape_until
                state["hand_detected"] = hand_now
                if hand_now:
                    state["last_escape_attempt"] = now
            else:
                state["hand_detected"] = False

            self._json(dict(state))

    def _handle_stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.send_header("Content-Length", str(len(STREAM_SVG)))
        self.end_headers()
        try:
            self.wfile.write(STREAM_SVG)
        except (BrokenPipeError, ConnectionResetError):
            pass


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    print(f"[INFO] Mock Pi server on http://localhost:{PORT}")
    print(f"[INFO] In index.html: Pi settings → http://localhost:{PORT} → Save")
    print(f"[INFO] Phone 'placed' after {PHONE_APPEAR_DELAY_S}s of polling.")
    print(f"[INFO] Escape pulses every {ESCAPE_CYCLE_S}s while locked.")
    print("[INFO] Ctrl-C to stop.\n")
    srv = ThreadedHTTPServer(("", PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] Stopped.")


if __name__ == "__main__":
    main()
