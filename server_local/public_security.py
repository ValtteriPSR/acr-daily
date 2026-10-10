"""Internet deployment boundary: origin checks, proxy auth and request throttling.
Never trust X-Forwarded-For/Proto without a secret-signed trusted gateway. The
application is NOT published directly: only Caddy binds public 80/443.
"""
from __future__ import annotations
import hmac
import ipaddress
import os
import secrets
import threading
import time
from urllib.parse import urlsplit

PUBLIC_URL = os.environ.get('ACR_PUBLIC_BASE_URL', '').rstrip('/')
GATEWAY_SECRET = os.environ.get('ACR_GATEWAY_SECRET', '')
DOWNLOAD_URL = os.environ.get('ACR_LAUNCHER_DOWNLOAD_URL', '')
MIN_LAUNCHER_VERSION = os.environ.get('ACR_MIN_LAUNCHER_VERSION','0.2.0')


def check_config():
    if not PUBLIC_URL:
        return
    p = urlsplit(PUBLIC_URL)
    if p.scheme != 'https' or not p.hostname or p.path or p.query or p.fragment or p.username or p.password:
        raise RuntimeError('ACR_PUBLIC_BASE_URL must be an HTTPS origin (no path)')
    if len(GATEWAY_SECRET) < 32:
        raise RuntimeError('ACR_GATEWAY_SECRET must be at least 32 characters in public mode')
    if DOWNLOAD_URL:
        u=urlsplit(DOWNLOAD_URL)
        if u.scheme != 'https' or not u.hostname or u.username or u.password:
            raise RuntimeError('ACR_LAUNCHER_DOWNLOAD_URL must be a valid HTTPS URL')


def gateway_ok(headers):
    if not PUBLIC_URL:
        return True
    expected=GATEWAY_SECRET.encode('utf8')
    supplied=str(headers.get('X-ACR-Gateway','')).encode('utf8')
    return hmac.compare_digest(supplied, expected)


def check_host(headers):
    if not PUBLIC_URL:
        return True
    return str(headers.get('Host','')).lower().rstrip('.') == urlsplit(PUBLIC_URL).netloc.lower()


def browser_origin(origin, headers):
    if not PUBLIC_URL:
        return None  # use established local-mode checks
    if not origin:
        return True  # CSRF double-submit remains mandatory
    if origin == 'null':
        # Privacy-oriented browsers can send the opaque literal null (as observed
        # with the local club). Accept it only AFTER the caller verifies the CSRF
        # double-submit cookie/form token; reject Fetch Metadata cross-site.
        return headers.get('Sec-Fetch-Site') in (None, '', 'same-origin', 'same-site', 'none')
    return origin == PUBLIC_URL


def remote_addr(headers, socket_addr):
    if not PUBLIC_URL:
        return socket_addr
    # Only called after gateway_ok, which is guaranteed by the handler.
    first=str(headers.get('X-Forwarded-For','')).split(',')[0].strip()
    try:
        return str(ipaddress.ip_address(first))
    except ValueError:
        return socket_addr


class RateLimiter:
    def __init__(self):
        self.lock=threading.Lock()
        self.recent={}

    def allow(self, peer, route, limit, period=60):
        now=time.monotonic()
        key=(peer,route)
        with self.lock:
            # bounded memory, clear expired entries opportunistically
            if len(self.recent)>3000:
                self.recent={k:v for k,v in self.recent.items() if v and v[-1]>now-period}
            times=[t for t in self.recent.get(key,[]) if t>now-period]
            if len(times)>=limit:
                self.recent[key]=times
                return False
            times.append(now)
            self.recent[key]=times
            return True


def version_allowed(raw):
    from re import fullmatch
    if not isinstance(raw,str) or not fullmatch(r'[0-9]{1,3}(?:\.[0-9]{1,3}){2}',raw):
        return False
    if not fullmatch(r'[0-9]{1,3}(?:\.[0-9]{1,3}){2}',MIN_LAUNCHER_VERSION):
        return False
    candidate = tuple(map(int, raw.split('.')))
    minimum = tuple(map(int, MIN_LAUNCHER_VERSION.split('.')))
    # The project restarted its numbering at 0.2. Keep the working cloud EXE
    # usable during migration, while still rejecting the incomplete 6.3.0 EXE.
    if minimum[0] == 0 and candidate[0] == 6:
        return candidate >= (6, 3, 1)
    return candidate >= minimum
