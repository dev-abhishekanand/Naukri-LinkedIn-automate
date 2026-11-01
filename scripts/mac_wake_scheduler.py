#!/usr/bin/env python3
"""
macOS Wake & Power-On Watchdog Scheduler
Ensures that if the Mac was powered off, shut down, or sleeping with lid closed during
the scheduled 8:55 AM - 9:00 AM daily window, the daily headline refresh and apply pipeline
execute immediately at the very second the Mac turns on or the lid gets opened.
"""

import os
import sys
import time
import json
import socket
import ctypes
import subprocess
from datetime import datetime, date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
STATE_FILE = PROJECT_DIR / ".daily_run_state.json"
LOG_DIR = PROJECT_DIR / "scheduler_logs"
WATCHDOG_LOG = LOG_DIR / "watchdog.log"

MORNING_BURST_SCRIPT = PROJECT_DIR / "scripts" / "run_morning_burst.sh"
EVENING_BURST_SCRIPT = PROJECT_DIR / "scripts" / "run_evening_burst.sh"
WEEKLY_AUDIT_SCRIPT = PROJECT_DIR / "scripts" / "run_weekly_audit_scheduled.sh"

SCHEDULED_TASKS = [
    {
        "id": "morning_burst",
        "name": "🌅 Morning Power Burst (Apply & Post)",
        "target_hour": 8,
        "target_minute": 55,
        "script": [str(MORNING_BURST_SCRIPT)],
        "sync_sheets": True,
    },
    {
        "id": "evening_burst",
        "name": "🌆 Evening Power Burst (Inbox & Follow-ups)",
        "target_hour": 17,
        "target_minute": 30,
        "script": [str(EVENING_BURST_SCRIPT)],
    },
    {
        "id": "weekly_audit",
        "name": "Weekly Profile Performance Audit & Auto-Revamp (Sunday 07:00 PM)",
        "target_hour": 19,
        "target_minute": 0,
        "weekly_day": 6,  # 6 = Sunday
        "script": [str(WEEKLY_AUDIT_SCRIPT)],
    },
]

LOG_DIR.mkdir(parents=True, exist_ok=True)


def is_night_silence_window(dt: datetime = None) -> bool:
    """
    Checks if current time falls within the Complete Night Silence Window (08:00 PM - 08:30 AM).
    During this period, all background automation is silenced to save 100% battery.
    """
    now = dt or datetime.now()
    curr_minute = now.hour * 60 + now.minute
    # 20:00 (8:00 PM) is 1200 minutes. 08:30 AM is 510 minutes.
    return curr_minute >= 1200 or curr_minute < 510


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] [Watchdog] {msg}"
    print(formatted, flush=True)
    try:
        with open(WATCHDOG_LOG, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass


def get_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"WARN: Could not read state file: {e}")
    state = {
        "last_wake_at": "",
        "last_check_at": "",
    }
    for task in SCHEDULED_TASKS:
        state[f"{task['id']}_date"] = ""
    return state


def save_state(state: dict):
    tmp_file = STATE_FILE.with_suffix(".tmp")
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        tmp_file.replace(STATE_FILE)
    except Exception as e:
        log(f"ERROR: Could not save state: {e}")


def is_network_ready(timeout: float = 3.0) -> bool:
    """Checks if the system has active internet access."""
    for host, port in [("8.8.8.8", 53), ("1.1.1.1", 53), ("www.naukri.com", 443)]:
        try:
            s = socket.create_connection((host, port), timeout=timeout)
            s.close()
            return True
        except OSError:
            continue
    return False


def wait_for_network(max_wait_seconds: int = 30) -> bool:
    """Waits for network to establish after Mac lid open or boot."""
    log("Waiting for network/Wi-Fi to establish...")
    start = time.time()
    while time.time() - start < max_wait_seconds:
        if is_network_ready(timeout=2.0):
            elapsed = time.time() - start
            log(f"Network is online (connected in {elapsed:.1f}s).")
            return True
        time.sleep(1.5)
    log(f"WARN: Network not reachable after {max_wait_seconds}s.")
    return False


def check_and_run(trigger_source: str = "periodic") -> dict:
    """
    Evaluates whether any hourly scheduled pipeline tasks are due or missed today,
    executing them sequentially with safe spacing.
    """
    state = get_state()
    today_str = date.today().isoformat()
    now = datetime.now()
    curr_minute_of_day = now.hour * 60 + now.minute

    # 1. Night Silence Window Check (08:00 PM – 08:30 AM)
    if is_night_silence_window(now):
        if trigger_source not in ("heartbeat", "periodic"):
            log("🌙 [NIGHT SILENCE ACTIVE] Automation is completely powered down (8:00 PM – 8:30 AM). Zero tasks run.")
        return {"due_count": 0, "status": "night_silence_active"}

    due_tasks = []
    for task in SCHEDULED_TASKS:
        task_id = task["id"]
        weekly_day = task.get("weekly_day")
        if weekly_day is not None and now.weekday() != weekly_day:
            continue
        target_min = task["target_hour"] * 60 + task["target_minute"]
        key = f"{task_id}_date"
        if curr_minute_of_day >= target_min and state.get(key) != today_str:
            due_tasks.append(task)

    state["last_check_at"] = now.isoformat()

    if not due_tasks:
        # Avoid disk writes on heartbeat when nothing is due
        if trigger_source != "heartbeat":
            save_state(state)
        return {"due_count": 0, "status": "up_to_date"}

    # Power & Battery Guardrail
    try:
        from common.power_manager import get_power_status
        power = get_power_status()
        if power.get("is_low_battery"):
            log(f"🛑 [BATTERY SAVER] Pausing heavy automated task execution. Battery is at {power.get('battery_percent')}% on Battery Power. Plug in charger to run.")
            return {"due_count": len(due_tasks), "status": "paused_low_battery"}
    except Exception:
        pass

    log(f"Trigger [{trigger_source}]: {len(due_tasks)} scheduled task(s) due: {[t['name'] for t in due_tasks]}")

    if not wait_for_network(max_wait_seconds=35):
        log("Cannot run scheduled jobs right now: No internet connection. Will retry on next check.")
        return {"due_count": len(due_tasks), "status": "no_internet"}

    executed_count = 0
    for idx, task in enumerate(due_tasks):
        task_id = task["id"]
        log(f"Executing [{idx + 1}/{len(due_tasks)}]: {task['name']}...")
        try:
            cmd = ["/bin/zsh"] + task["script"]
            res = subprocess.run(cmd, capture_output=False)
            if res.returncode == 0:
                log(f"✓ {task['name']} finished successfully.")
                state[f"{task_id}_date"] = today_str
                executed_count += 1
            else:
                log(f"WARN: {task['name']} exited with code {res.returncode}.")
                # If non-zero, mark completed for non-critical informational tasks to prevent tight error loops
                if task_id in ("headline", "post", "interview", "inbox"):
                    state[f"{task_id}_date"] = today_str
        except Exception as e:
            log(f"ERROR running {task['name']}: {e}")

        save_state(state)

        if task.get("sync_sheets"):
            try:
                from google_sheets_logger import record_daily_metrics
                record_daily_metrics(today_str, notes=f"Watchdog Run ({trigger_source})")
                log("✓ Synced Daily Apply Metrics tab in Google Sheets.")
            except Exception as e:
                log(f"Note: Could not sync Daily Apply Metrics: {e}")

        if idx < len(due_tasks) - 1:
            log("Pausing 30s before next scheduled pipeline task...")
            time.sleep(30)

    log(f"Sequential pipeline check completed for date: {today_str} ({executed_count}/{len(due_tasks)} executed).")
    return {"due_count": len(due_tasks), "executed_count": executed_count, "status": "completed"}


def run_daemon():
    """Continuous background listener for sleep/wake and power-on events."""
    log("=======================================================")
    log("Starting Mac Wake & Power-On Watchdog Daemon...")
    log(f"Project directory: {PROJECT_DIR}")
    log(f"State file:        {STATE_FILE}")
    log("=======================================================")

    # Initialize libSystem Darwin notification listener
    lib = None
    tokens = []
    try:
        lib = ctypes.CDLL("/usr/lib/libSystem.dylib")
        for key in [
            "com.apple.system.powermanagement.systemdidwake",
            "com.apple.powermanagement.hasdisplaypoweredon",
        ]:
            token = ctypes.c_int()
            status = lib.notify_register_check(key.encode("utf-8"), ctypes.byref(token))
            if status == 0:
                tokens.append((token, key))
                log(f"Registered Darwin notification listener for: {key}")
    except Exception as e:
        log(f"Note: Darwin notification registration unavailable: {e}")

    # Immediate check upon daemon startup (catches Mac power-on / boot / login)
    log("Checking missed schedule on daemon startup...")
    check_and_run(trigger_source="mac_boot_or_login")

    last_monotonic = time.monotonic()
    last_wall = time.time()

    # Battery-Aware Adaptive Loop (Sleep 60s on battery, 30s on AC)
    while True:
        try:
            # Complete Night Silence Window (08:00 PM – 08:30 AM): Deep Sleep with 0 checks
            if is_night_silence_window():
                time.sleep(120)
                last_monotonic = time.monotonic()
                last_wall = time.time()
                continue

            # Check power source dynamically
            loop_sleep = 30
            try:
                from common.power_manager import get_power_status
                p = get_power_status()
                if p.get("is_on_battery"):
                    loop_sleep = 60
            except Exception:
                loop_sleep = 30

            time.sleep(loop_sleep)
            curr_monotonic = time.monotonic()
            curr_wall = time.time()
            wall_diff = curr_wall - last_wall
            mono_diff = curr_monotonic - last_monotonic

            wake_detected = False
            wake_reason = ""

            # 1. Check Darwin notifications (System did wake / Display on / Lid open)
            if lib and tokens:
                for token, key in tokens:
                    check_val = ctypes.c_int()
                    lib.notify_check(token, ctypes.byref(check_val))
                    if check_val.value != 0:
                        wake_detected = True
                        wake_reason = f"Darwin notification ({key})"
                        break

            # 2. Check time jump (sleep detection: wall time progressed much faster than monotonic or expected sleep)
            if not wake_detected and wall_diff >= (loop_sleep * 2.5):
                wake_detected = True
                wake_reason = f"Wall time jump detected ({wall_diff:.1f}s sleep elapsed)"

            if wake_detected:
                log(f"⚡ [MAC WAKE DETECTED] Lid opened or Mac woke up! Reason: {wake_reason}")
                state = get_state()
                state["last_wake_at"] = datetime.now().isoformat()
                save_state(state)
                check_and_run(trigger_source="mac_lid_open_or_wake")
            else:
                # Periodic heartbeat check (catches normal 8:55 AM / 9:00 AM while awake)
                check_and_run(trigger_source="heartbeat")

            last_monotonic = curr_monotonic
            last_wall = curr_wall

        except Exception as e:
            log(f"Unexpected error in watchdog loop: {e}")
            time.sleep(30)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Mac Wake & Power-On Watchdog Scheduler")
    parser.add_argument("--daemon", action="store_true", help="Run as background watchdog daemon")
    parser.add_argument("--check", action="store_true", help="Check and execute missed jobs now")
    parser.add_argument("--status", action="store_true", help="Print current status and state")
    parser.add_argument("--reset-today", action="store_true", help="Reset today state to test run")
    args = parser.parse_args()

    if args.status:
        state = get_state()
        print("\n--- Daily Run State ---")
        today_str = date.today().isoformat()
        now = datetime.now()
        curr_min = now.hour * 60 + now.minute
        print(f"Current Time: {now.strftime('%Y-%m-%d %H:%M:%S')} (Minute: {curr_min})")
        print("-" * 75)
        for task in SCHEDULED_TASKS:
            weekly_day = task.get("weekly_day")
            is_today_run = (weekly_day is None or now.weekday() == weekly_day)
            t_min = task["target_hour"] * 60 + task["target_minute"]
            ran = state.get(f"{task['id']}_date") == today_str
            is_past = (curr_min >= t_min) if is_today_run else False
            time_str = f"{task['target_hour']:02d}:{task['target_minute']:02d}"
            due_label = ("YES" if is_past else "NO") if is_today_run else "SUN ONLY"
            print(f"[{time_str}] {task['name']:<52} Ran: {'YES' if ran else 'NO':<4} | Due/Past: {due_label}")
        print("-" * 75)
        sys.exit(0)

    if args.reset_today:
        state = get_state()
        state["headline_date"] = ""
        state["apply_date"] = ""
        save_state(state)
        print("✓ Reset today's run state.")
        sys.exit(0)

    if args.check:
        res = check_and_run(trigger_source="manual_cli_check")
        print("Result:", res)
        sys.exit(0)

    if args.daemon:
        run_daemon()
    else:
        parser.print_help()
