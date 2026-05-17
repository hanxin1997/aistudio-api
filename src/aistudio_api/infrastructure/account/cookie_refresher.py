"""Cookie loading for browser injection via raw cookie string + curl_cffi refresh."""

from __future__ import annotations

import logging
from typing import Any

from aistudio_api.infrastructure.account.cookie_parser import _DOMAIN_OVERRIDES

log = logging.getLogger("aistudio.cookie_refresher")

# Auth cookies that need httpOnly=False so JS can read them (for SAPISIDHASH)
AUTH_COOKIE_NAMES = {
    "SID", "SSID", "HSID", "APISID", "SAPISID",
    "__Secure-1PAPISID", "__Secure-3PAPISID",
    "__Secure-1PSID", "__Secure-3PSID",
}

def _parse_cookie_string(raw: str) -> dict[str, str]:
    """Parse a semicolon-separated cookie string into a dict."""
    cookies = {}
    for part in raw.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def _refresh_session_cookies(cookies: dict[str, str]) -> dict[str, str]:
    """Use curl_cffi to GET aistudio.google.com and refresh session cookies."""
    try:
        from curl_cffi import requests
    except ImportError:
        log.warning("curl_cffi not installed, returning cookies as-is")
        return dict(cookies)

    session = requests.Session()
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".google.com")

    try:
        resp = session.get("https://myaccount.google.com", impersonate="chrome", timeout=15)
        log.debug("GET aistudio.google.com: %d", resp.status_code)
    except Exception as e:
        log.warning("Failed to refresh session cookies: %s", e)
        return dict(cookies)

    all_cookies = dict(session.cookies)
    log.info("Refreshed cookies: %d total", len(all_cookies))
    return all_cookies


def load_cookies_from_string(cookie_string: str) -> list[dict[str, Any]]:
    """Load cookies from a raw cookie string.

    Parses directly, refreshes session cookies via curl_cffi,
    returns Playwright-format cookies for browser injection.
    Real expires come from browser export after visiting the page.
    """
    import time

    parsed = _parse_cookie_string(cookie_string)
    refreshed = _refresh_session_cookies(parsed)
    default_expires = int(time.time()) + 86400 * 180  # 180 天后过期

    seen: set[tuple[str, str]] = set()
    cookies: list[dict[str, Any]] = []

    def _add(name: str, value: str, domain: str) -> None:
        key = (name, domain)
        if key in seen:
            return
        seen.add(key)
        cookies.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": "/",
            "secure": True,
            "httpOnly": name not in AUTH_COOKIE_NAMES,
            "sameSite": "None",
            "expires": default_expires,
        })

    for name, value in refreshed.items():
        if name in _DOMAIN_OVERRIDES:
            for domain in _DOMAIN_OVERRIDES[name]:
                _add(name, value, domain)
        else:
            _add(name, value, ".google.com")

    log.info("[cookie_string] parsed %d cookies", len(cookies))
    return cookies

