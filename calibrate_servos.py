"""
Snorlax Focus Buddy — Servo Calibration
Run on the Pi. Walks you through finding the 4 pulse widths
(servo 1 locked/unlocked, servo 2 locked/unlocked) for your mount.

Prints a paste-ready block at the end. Ctrl-C is safe — servos detach.

USAGE: python3 calibrate_servos.py
"""

import sys
import time
import pigpio

SERVO_1_PIN = 17
SERVO_2_PIN = 27

SWEEP_START_US = 1000
SWEEP_END_US   = 2000
SWEEP_STEP_US  = 100
SWEEP_DWELL_S  = 1.0

SAFE_MIN_US = 500
SAFE_MAX_US = 2500
NEUTRAL_US  = 1500

pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("pigpio daemon not running. sudo systemctl start pigpiod")


def detach(pin):
    pi.set_servo_pulsewidth(pin, 0)


def hold(pin, us):
    pi.set_servo_pulsewidth(pin, us)


def prompt_int(label):
    while True:
        raw = input(label).strip()
        try:
            v = int(raw)
        except ValueError:
            print(f"  ! not a number, try again")
            continue
        if v < SAFE_MIN_US or v > SAFE_MAX_US:
            print(f"  ! {v} outside safe range {SAFE_MIN_US}–{SAFE_MAX_US}, try again")
            continue
        return v


def confirm_position(pin, label):
    """Prompt for a value, move servo there, ask y/n, loop until y. Return final value."""
    while True:
        v = prompt_int(f"Enter pulse width for {label} position ({SAFE_MIN_US}–{SAFE_MAX_US}): ")
        hold(pin, v)
        ans = input(f"  Moved to {v}μs. Is this the {label} position? [y/n]: ").strip().lower()
        if ans == "y":
            return v


def calibrate_servo(servo_num, this_pin, other_pin):
    print()
    print(f"═══════════ SERVO {servo_num} (GPIO {this_pin}) ═══════════")

    # Idle the other servo so it doesn't buzz/twitch
    detach(other_pin)

    # Pre-sweep safety pause at neutral
    print(f"Servo {servo_num} about to move to neutral ({NEUTRAL_US}μs).")
    print("Ctrl-C now if arm will collide with anything.")
    hold(this_pin, NEUTRAL_US)
    time.sleep(SWEEP_DWELL_S)

    # Sweep
    print(f"Sweeping {SWEEP_START_US}→{SWEEP_END_US}μs in {SWEEP_STEP_US}μs steps...")
    for us in range(SWEEP_START_US, SWEEP_END_US + 1, SWEEP_STEP_US):
        hold(this_pin, us)
        print(f"  {us}μs")
        time.sleep(SWEEP_DWELL_S)

    # Locked + visual confirm
    locked = confirm_position(this_pin, "LOCKED")
    # Unlocked + visual confirm
    unlocked = confirm_position(this_pin, "UNLOCKED")

    return locked, unlocked


def print_paste_block(s1_locked, s1_unlocked, s2_locked, s2_unlocked):
    bar = "─" * 47
    print()
    print(f"{bar}")
    print("           PASTE INTO pi_server.py")
    print(f"{bar}")
    print("# Replace SERVO_LOCKED_US and SERVO_UNLOCKED_US with:")
    print(f"SERVO_1_LOCKED_US   = {s1_locked}")
    print(f"SERVO_1_UNLOCKED_US = {s1_unlocked}")
    print(f"SERVO_2_LOCKED_US   = {s2_locked}")
    print(f"SERVO_2_UNLOCKED_US = {s2_unlocked}")
    print()
    print("# Replace set_servos() with:")
    print("def set_servos(state):")
    print("    \"\"\"state: 'locked' or 'unlocked'\"\"\"")
    print("    if state == 'locked':")
    print("        pi.set_servo_pulsewidth(SERVO_1_PIN, SERVO_1_LOCKED_US)")
    print("        pi.set_servo_pulsewidth(SERVO_2_PIN, SERVO_2_LOCKED_US)")
    print("    else:")
    print("        pi.set_servo_pulsewidth(SERVO_1_PIN, SERVO_1_UNLOCKED_US)")
    print("        pi.set_servo_pulsewidth(SERVO_2_PIN, SERVO_2_UNLOCKED_US)")
    print("    time.sleep(0.5)")
    print("    pi.set_servo_pulsewidth(SERVO_1_PIN, 0)")
    print("    pi.set_servo_pulsewidth(SERVO_2_PIN, 0)")
    print()
    print("# Also update callers:")
    print("#   set_servos(SERVO_UNLOCKED_US)  →  set_servos('unlocked')")
    print("#   set_servos(SERVO_LOCKED_US)    →  set_servos('locked')")
    print(f"{bar}")


def main():
    try:
        s1_locked, s1_unlocked = calibrate_servo(1, SERVO_1_PIN, SERVO_2_PIN)
        s2_locked, s2_unlocked = calibrate_servo(2, SERVO_2_PIN, SERVO_1_PIN)
        print_paste_block(s1_locked, s1_unlocked, s2_locked, s2_unlocked)
    finally:
        detach(SERVO_1_PIN)
        detach(SERVO_2_PIN)
        pi.stop()
        print()
        print("Servos detached. Run pi_server.py to re-engage.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # finally in main() already ran; just exit clean
        sys.exit(0)
