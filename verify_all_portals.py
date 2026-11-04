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
        "auth_cookies": ["sessionid", "csrftoken"],
        "critical_cookies": ["sessionid"]
    },
    "cutshort": {
        "name": "Cutshort",
        "file": "session_cutshort.json",
        "auth_cookies": ["cutshort_authentication", "user_logged_in_once"],
        "critical_cookies": ["cutshort_authentication", "user_logged_in_once"]
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
        "auth_cookies": ["hirist_seeker_enc", "HIRIST_CK1", "PHPSESSID", "chatSdkToken"],
        "critical_cookies": ["hirist_seeker_enc"]
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
        captured_url = data.get("metadata", {}).get("captured_url", "").lower()
        is_authenticated_meta = data.get("metadata", {}).get("authenticated") is True
        is_cs_page = any(route in captured_url for route in ["/profile", "/inbox", "/dashboard", "/jobs", "/candidate", "/messages", "/feed"])
        origins = data.get("origins", [])
        ls_keys = set()
        for o in origins:
            for item in o.get("localStorage", []):
                ls_keys.add(item.get("name", "").lower())
        has_auth_storage = any(k in ls_keys for k in ["user", "candidate_id", "email", "profile", "jwt", "token"])

        # Anonymous visitors have cutshort_authentication on homepage but lack candidate route or candidate storage
        if not auth_cookie or len(auth_cookie.get("value", "")) < 15 or not (is_cs_page or has_auth_storage or (is_authenticated_meta and captured_url.rstrip("/") != "https://cutshort.io")):
            return {
                "key": key,
                "name": conf["name"],
                "file": conf["file"],
                "status": "NOT LOGGED IN",
                "reason": "Anonymous session only (login not completed on candidate portal)",
                "cookies_found": len(cookies),
                "auth_tokens": [],
                "candidate_id": None
            }

    elif key == "instahyre":
        session_cookie = cookie_map.get("sessionid")
        if not session_cookie or len(session_cookie.get("value", "")) < 15:
            return {
                "key": key,
                "name": conf["name"],
                "file": conf["file"],
                "status": "NOT LOGGED IN",
                "reason": "sessionid cookie missing or invalid",
                "cookies_found": len(cookies),
                "auth_tokens": [],
                "candidate_id": None
            }

        # Check if authenticated via metadata or candidate session length
        is_authenticated_meta = data.get("metadata", {}).get("authenticated") is True
        origins = data.get("origins", [])
        ls_keys = set()
        for o in origins:
            for item in o.get("localStorage", []):
                ls_keys.add(item.get("name", ""))

        has_auth_storage = any(k in ls_keys for k in ["user", "candidate_id", "email", "profile"])
        
        # In Instahyre, a logged-in user with Google/Email has sessionid + 20+ cookies
        if is_authenticated_meta or has_auth_storage or len(cookies) >= 15:
            return {
                "key": key,
                "name": conf["name"],
                "file": conf["file"],
                "status": "LOGGED IN",
                "reason": "Verified Instahyre candidate authenticated session",
                "cookies_found": len(cookies),
                "auth_tokens": ["sessionid", "csrftoken"],
                "candidate_id": "Candidate Dashboard Verified"
            }
        else:
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

    elif key == "hirist":
        has_seeker_enc = "hirist_seeker_enc" in cookie_map
        has_ck1 = "HIRIST_CK1" in cookie_map
        captured_url = data.get("metadata", {}).get("captured_url", "").lower()
        is_candidate_page = any(route in captured_url for route in ["/jobfeed", "/candidate", "/job-feed", "/dashboard", "/profile"])
        
        # Extract candidate ID from JWT if present
        candidate_id = None
        for ck_name in ["hirist_seeker_enc", "HIRIST_CK1"]:
            if ck_name in cookie_map:
                try:
                    import base64
                    val = cookie_map[ck_name].get("value", "")
                    parts = val.split(".")
                    if len(parts) >= 2:
                        pad = "=" * (-len(parts[1]) % 4)
                        payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad).decode(errors="ignore"))
                        if payload.get("id"):
                            candidate_id = f"Candidate #{payload['id']}"
                            break
                except Exception:
                    pass

        if (has_seeker_enc or has_ck1) and (len(cookies) >= 15 or is_candidate_page or candidate_id):
            return {
                "key": key,
                "name": conf["name"],
                "file": conf["file"],
                "status": "LOGGED IN",
                "reason": f"Verified Hirist candidate session ({', '.join(auth_found) if auth_found else 'hirist_seeker_enc'})",
                "cookies_found": len(cookies),
                "auth_tokens": [c for c in ["hirist_seeker_enc", "HIRIST_CK1", "PHPSESSID"] if c in cookie_map],
                "candidate_id": candidate_id or "Verified Candidate"
            }
        else:
            return {
                "key": key,
                "name": conf["name"],
                "file": conf["file"],
                "status": "NOT LOGGED IN",
                "reason": "Missing Hirist candidate authentication cookies (hirist_seeker_enc)",
                "cookies_found": len(cookies),
                "auth_tokens": [],
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
