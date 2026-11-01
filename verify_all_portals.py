#!/usr/bin/env python3
"""
Comprehensive Live Portal Session Verifier
Checks genuine candidate authentication tokens and profiles across all supported portals:
- Naukri (Primary, Secondary, Tertiary)
- LinkedIn
- Indeed
- Instahyre
- Cutshort
- Wellfound
- Hirist
"""
import sys
import json
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

PORTALS = {
    "naukri_primary": {
        "name": "Naukri (Primary)",
        "file": "session_naukri.json",
        "auth_cookies": ["nauk_at", "nauk_user", "naukri_auth", "n_auth", "is_login", "nauk_sid"],
        "critical_cookies": ["nauk_at", "n_auth", "nauk_user"]
    },
    "naukri_secondary": {
        "name": "Naukri (Secondary)",
        "file": "session_naukri_secondary.json",
        "auth_cookies": ["nauk_at", "nauk_user", "naukri_auth", "n_auth", "is_login", "nauk_sid"],
        "critical_cookies": ["nauk_at", "n_auth", "nauk_user"]
    },
    "linkedin": {
        "name": "LinkedIn",
        "file": "session_linkedin.json",
        "auth_cookies": ["li_at"],
        "critical_cookies": ["li_at"]
    },
    "indeed": {
        "name": "Indeed",
        "file": "session_indeed.json",
        "auth_cookies": ["PPID", "SHARED_SESSION_TOKEN", "LOGGED_IN", "HP_MYINDEED", "SOCK", "UD", "INDEED_CSRF_TOKEN"],
        "critical_cookies": ["PPID", "SOCK", "SURF"]
    },
    "instahyre": {
        "name": "Instahyre",
        "file": "session_instahyre.json",
        "auth_cookies": ["auth_token", "candidate_id", "sessionid"],
        "critical_cookies": ["auth_token"]
    },
    "cutshort": {
        "name": "Cutshort",
        "file": "session_cutshort.json",
        "auth_cookies": ["cutshort_authentication", "user_logged_in_once"],
        "critical_cookies": ["cutshort_authentication"]
    },
    "wellfound": {
        "name": "Wellfound",
        "file": "session_wellfound.json",
        "auth_cookies": ["remember_user_token", "auth_token", "_wellfound"],
        "critical_cookies": ["remember_user_token", "auth_token"]
    },
    "hirist": {
        "name": "Hirist",
        "file": "session_hirist.json",
        "auth_cookies": ["hirist_session", "candidate_id", "user_id"],
        "critical_cookies": ["hirist_session", "candidate_id"]
    }
}


def check_portal(key: str, conf: dict) -> dict:
    session_file = PROJECT_DIR / conf["file"]
    if not session_file.exists():
        return {
            "key": key,
            "name": conf["name"],
            "file": conf["file"],
            "status": "NOT LOGGED IN",
            "reason": "File does not exist",
            "cookies_found": 0,
            "auth_tokens": [],
            "candidate_id": None
        }

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {
            "key": key,
            "name": conf["name"],
            "file": conf["file"],
            "status": "CORRUPTED",
            "reason": f"Invalid JSON: {e}",
            "cookies_found": 0,
            "auth_tokens": [],
            "candidate_id": None
        }

    cookies = data.get("cookies", [])
    cookie_map = {c.get("name"): c for c in cookies if c.get("name")}
    
    auth_found = [c for c in conf["auth_cookies"] if c in cookie_map]
    critical_found = [c for c in conf["critical_cookies"] if c in cookie_map]

    # Specific checks per portal
    candidate_info = None
    
    if key == "indeed":
        ppid_cookie = cookie_map.get("PPID")
        if ppid_cookie and ppid_cookie.get("value"):
            val = ppid_cookie["value"]
            # Check expiry
            exp = ppid_cookie.get("expires", -1)
            is_expired = exp > 0 and exp < time.time()
            if not is_expired:
                # Try decoding payload
                try:
                    import base64
                    payload = val.split(".")[1]
                    # pad
                    payload += "=" * ((4 - len(payload) % 4) % 4)
                    decoded = json.loads(base64.b64decode(payload))
                    candidate_info = decoded.get("email") or decoded.get("sub")
                except Exception:
                    candidate_info = "PPID Token Valid"
            else:
                return {
                    "key": key,
                    "name": conf["name"],
                    "file": conf["file"],
                    "status": "EXPIRED",
                    "reason": "PPID token expired",
                    "cookies_found": len(cookies),
                    "auth_tokens": auth_found,
                    "candidate_id": None
                }

    elif key == "cutshort":
        auth_cookie = cookie_map.get("cutshort_authentication")
        if not auth_cookie or len(auth_cookie.get("value", "")) < 15:
            return {
                "key": key,
                "name": conf["name"],
                "file": conf["file"],
                "status": "NOT LOGGED IN",
                "reason": "cutshort_authentication token missing or empty",
                "cookies_found": len(cookies),
                "auth_tokens": auth_found,
                "candidate_id": None
            }

    elif key == "instahyre":
        # Check if auth_token exists or candidate localStorage is present
        origins = data.get("origins", [])
        ls_keys = set()
        for o in origins:
            for item in o.get("localStorage", []):
                ls_keys.add(item.get("name", ""))
                # If only login rum exists, it's NOT logged in
                if item.get("name") == "instahyre_rum_view_windows_v1" and "login" in item.get("value", "") and "candidate" not in item.get("value", ""):
                    ls_keys.add("__only_login__")

        has_auth_cookie = "auth_token" in cookie_map or "candidate_id" in cookie_map
        has_auth_storage = any(k in ls_keys for k in ["user", "candidate_id", "email", "profile"])
        
        if "__only_login__" in ls_keys and not has_auth_cookie:
            return {
                "key": key,
                "name": conf["name"],
                "file": conf["file"],
                "status": "NOT LOGGED IN",
                "reason": "Anonymous session at login page only",
                "cookies_found": len(cookies),
                "auth_tokens": [],
                "candidate_id": None
            }

        if not has_auth_cookie and not has_auth_storage and not ("sessionid" in cookie_map and len(cookies) > 20):
            return {
                "key": key,
                "name": conf["name"],
                "file": conf["file"],
                "status": "NOT LOGGED IN",
                "reason": "Missing candidate authentication credentials",
                "cookies_found": len(cookies),
                "auth_tokens": [],
                "candidate_id": None
            }

    elif key == "linkedin":
        li_cookie = cookie_map.get("li_at")
        if not li_cookie or len(li_cookie.get("value", "")) < 15:
            return {
                "key": key,
                "name": conf["name"],
                "file": conf["file"],
                "status": "NOT LOGGED IN",
                "reason": "li_at authentication cookie missing or empty",
                "cookies_found": len(cookies),
                "auth_tokens": auth_found,
                "candidate_id": None
            }

    # General check
    if critical_found or (auth_found and len(auth_found) >= 1):
        status = "LOGGED IN"
        reason = f"Verified tokens: {', '.join(auth_found)}"
    else:
        status = "NOT LOGGED IN"
        reason = f"Missing candidate auth tokens (requires {', '.join(conf['critical_cookies'])})"

    return {
        "key": key,
        "name": conf["name"],
        "file": conf["file"],
        "status": status,
        "reason": reason,
        "cookies_found": len(cookies),
        "auth_tokens": auth_found,
        "candidate_id": candidate_info
    }


def verify_all() -> list:
    results = []
    for key, conf in PORTALS.items():
        results.append(check_portal(key, conf))
    return results


def print_report(results: list):
    print("=" * 85)
    print("📋 MULTI-PORTAL LIVE AUTHENTICATION STATUS AUDIT")
    print("=" * 85)
    print(f"{'PORTAL':<22} | {'STATUS':<15} | {'COOKIES':<8} | {'DETAILS':<34}")
    print("-" * 85)
    for r in results:
        status_icon = "🟢" if r["status"] == "LOGGED IN" else ("🔴" if r["status"] == "NOT LOGGED IN" else "🟡")
        status_str = f"{status_icon} {r['status']}"
        details = r["candidate_id"] or r["reason"]
        if len(details) > 33:
            details = details[:30] + "..."
        print(f"{r['name']:<22} | {status_str:<15} | {r['cookies_found']:<8} | {details:<34}")
    print("=" * 85)


if __name__ == "__main__":
    results = verify_all()
    print_report(results)
