#!/usr/bin/env python3
from __future__ import annotations
"""
Unified Browser Factory for Google Chrome Automation
Launches official Google Chrome (/Applications/Google Chrome.app) using Playwright channel="chrome".
Ensures anti-bot stealth flags, proper user agents, and safe isolation so personal Chrome windows
never conflict or trigger 'SingletonLock' reopening errors.
"""

import os
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

CHROME_APP_PATH = Path("/Applications/Google Chrome.app")
PROJECT_DIR = Path(__file__).resolve().parent.parent

# Persistent Google Chrome Profile directories for automation
CHROME_PROFILE_PRIMARY = PROJECT_DIR / "session_chrome_primary"
CHROME_PROFILE_SECONDARY = PROJECT_DIR / "session_chrome_secondary"

DEFAULT_CHROME_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--password-store=basic",
]

DEFAULT_STEALTH_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"


def is_google_chrome_installed() -> bool:
    """Checks if official Google Chrome is installed on the host system."""
    return CHROME_APP_PATH.exists()


def get_browser_channel() -> Optional[str]:
    """Returns 'chrome' if official Google Chrome is available, otherwise None (Chromium fallback)."""
    return "chrome" if is_google_chrome_installed() else None


def launch_chrome_browser(
    p,
    headless: bool = True,
    browser_mode: str = "visible",
    slow_mo: Optional[int] = None,
    extra_args: Optional[List[str]] = None,
):
    """
    Launches Google Chrome (channel='chrome') with stealth flags.
    Falls back gracefully to Chromium if Chrome is not present.
    """
    args = list(DEFAULT_CHROME_ARGS)
    if extra_args:
        args.extend(extra_args)

    if browser_mode == "headless" or headless:
        is_headless = True
    elif browser_mode == "minimized":
        is_headless = False
        args.append("--start-minimized")
    else:
        is_headless = False

    channel = get_browser_channel()
    launch_kwargs: Dict[str, Any] = {
        "headless": is_headless,
        "args": args,
    }
    if slow_mo:
        launch_kwargs["slow_mo"] = slow_mo

    if channel:
        launch_kwargs["channel"] = channel
        try:
            return p.chromium.launch(**launch_kwargs)
        except Exception:
            # If Google Chrome fails, fallback to Chromium cleanly
            del launch_kwargs["channel"]
            return p.chromium.launch(**launch_kwargs)

    return p.chromium.launch(**launch_kwargs)


def create_stealth_context(browser, storage_state: Optional[str | Path] = None, **kwargs):
    """
    Creates a Playwright browser context with authentic desktop Chrome headers,
    Macintosh User-Agent, and realistic viewport to pass Akamai/Cloudflare bot detection.
    """
    ctx_kwargs = {
        "user_agent": DEFAULT_STEALTH_USER_AGENT,
        "viewport": {"width": 1280, "height": 800},
        "device_scale_factor": 2,
        "has_touch": False,
        "is_mobile": False,
        "locale": "en-US",
        "timezone_id": "Asia/Kolkata",
    }
    if storage_state and Path(storage_state).exists():
        ctx_kwargs["storage_state"] = str(storage_state)
    ctx_kwargs.update(kwargs)
    return browser.new_context(**ctx_kwargs)


def launch_chrome_persistent_context(
    p,
    user_data_dir: Path | str,
    headless: bool = True,
    browser_mode: str = "visible",
    slow_mo: Optional[int] = None,
    extra_args: Optional[List[str]] = None,
):
    """
    Launches a persistent Google Chrome context inside a dedicated automation profile folder.
    This avoids any SingletonLock conflict with everyday personal Chrome windows.
    """
    data_dir = Path(user_data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    args = list(DEFAULT_CHROME_ARGS)
    if extra_args:
        args.extend(extra_args)

    if browser_mode == "headless" or headless:
        is_headless = True
    elif browser_mode == "minimized":
        is_headless = False
        args.append("--start-minimized")
    else:
        is_headless = False

    channel = get_browser_channel()
    launch_kwargs: Dict[str, Any] = {
        "user_data_dir": str(data_dir),
        "headless": is_headless,
        "args": args,
        "user_agent": DEFAULT_STEALTH_USER_AGENT,
        "viewport": {"width": 1280, "height": 800},
    }
    if channel:
        launch_kwargs["channel"] = channel
    if slow_mo:
        launch_kwargs["slow_mo"] = slow_mo

    return p.chromium.launch_persistent_context(**launch_kwargs)
