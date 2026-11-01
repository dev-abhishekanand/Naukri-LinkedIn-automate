#!/usr/bin/env python3
"""
Hardware & Battery Power Manager (macOS Optimized)
Monitors battery health, charging status, and power source via macOS `pmset`.
Enforces power-aware throttling to prevent battery drainage during heavy automation.
"""
import re
import subprocess
from typing import Dict, Any

_CACHED_POWER_STATUS: Dict[str, Any] = {}
_LAST_POWER_CHECK: float = 0.0


def get_power_status(cache_ttl_seconds: float = 10.0) -> Dict[str, Any]:
    """
    Returns macOS battery and power status:
    - power_source: 'Battery Power' or 'AC Power'
    - battery_percent: int (0-100)
    - is_charging: bool
    - is_on_battery: bool
    - is_low_battery: bool (<35% on battery)
    - should_throttle: bool (True if on battery and <=40%)
    """
    import time
    global _CACHED_POWER_STATUS, _LAST_POWER_CHECK
    now = time.time()
    if _CACHED_POWER_STATUS and (now - _LAST_POWER_CHECK < cache_ttl_seconds):
        return _CACHED_POWER_STATUS

    status = {
        "power_source": "AC Power",
        "battery_percent": 100,
        "is_charging": False,
        "is_on_battery": False,
        "is_low_battery": False,
        "should_throttle": False,
        "time_remaining": "N/A"
    }

    try:
        out = subprocess.check_output(["pmset", "-g", "batt"], text=True, timeout=2.0)
        # Check power source
        if "Battery Power" in out:
            status["power_source"] = "Battery Power"
            status["is_on_battery"] = True
        else:
            status["power_source"] = "AC Power"
            status["is_on_battery"] = False

        # Extract percentage
        pct_match = re.search(r"(\d+)%", out)
        if pct_match:
            status["battery_percent"] = int(pct_match.group(1))

        # Check charging state
        status["is_charging"] = "charging" in out.lower() and "discharging" not in out.lower()

        # Extract remaining time if available
        time_match = re.search(r"(\d+:\d+)\s+remaining", out)
        if time_match:
            status["time_remaining"] = time_match.group(1)

        # Smart Throttling Thresholds:
        # Throttle heavy runs if discharging on battery with <= 45% remaining
        if status["is_on_battery"] and status["battery_percent"] <= 45:
            status["should_throttle"] = True
        if status["is_on_battery"] and status["battery_percent"] <= 25:
            status["is_low_battery"] = True

    except Exception as e:
        # Fallback if pmset fails (e.g. non-mac or permission)
        status["error"] = str(e)

    _CACHED_POWER_STATUS = status
    _LAST_POWER_CHECK = now
    return status


def check_throttle_override(task_name: str = "batch_apply") -> tuple[bool, str]:
    """
    Returns (should_proceed, reason_message) based on current battery status.
    Light tasks (inbox, diagnostics) are always permitted. Heavy tasks (batch browser apply)
    are throttled if on low battery.
    """
    p = get_power_status()
    if not p["is_on_battery"]:
        return True, "Running on AC Power (Full Performance)"

    if p["is_low_battery"]:
        return False, f"🛑 PAUSED: Mac is at {p['battery_percent']}% on Battery Power. Plug in charger to continue heavy automation."

    if p["should_throttle"]:
        return True, f"⚠️ ECO-MODE: Battery at {p['battery_percent']}%. Throttling concurrency and browser intensity to preserve battery."

    return True, f"Battery at {p['battery_percent']}% (Adequate charge)."


if __name__ == "__main__":
    import json
    print(json.dumps(get_power_status(), indent=2))
