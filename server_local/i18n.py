"""Request-scoped translation of static UI literals, never user-authored data."""
from contextvars import ContextVar
from functools import wraps
from html import escape
from http.cookies import SimpleCookie
import json
from pathlib import Path
import re
from urllib.parse import urlencode, urlsplit

LANGUAGE_COOKIE = 'acrclub_language'
SUPPORTED_LANGUAGES = ('pl', 'en')
_language = ContextVar('acrclub_language', default='pl')
_return_path = ContextVar('acrclub_language_return_path', default='/')
_polish = json.loads((Path(__file__).parent / 'translations' / 'pl.json').read_text(encoding='utf-8'))


def language():
    return _language.get()


def tr(text):
    """Translate only known static source strings before user values are inserted."""
    return _polish.get(text, text) if language() == 'pl' else text


def request_localized(method):
    @wraps(method)
    def wrapped(handler, *args, **kwargs):
        cookies = SimpleCookie()
        try:
            cookies.load(handler.headers.get('Cookie', ''))
            chosen = cookies[LANGUAGE_COOKIE].value if LANGUAGE_COOKIE in cookies else 'pl'
        except Exception:
            chosen = 'pl'
        token = _language.set(chosen if chosen in SUPPORTED_LANGUAGES else 'pl')
        path_token = _return_path.set(safe_return_path(handler.path))
        try:
            return method(handler, *args, **kwargs)
        finally:
            _return_path.reset(path_token)
            _language.reset(token)
    return wrapped


def safe_return_path(value):
    if not isinstance(value, str) or not value.startswith('/'):
        return '/'
    if value.startswith('//') or '\\' in value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        return '/'
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or parts.path == '/language':
        return '/'
    return value


def language_cookie(chosen, secure=False):
    return (f'{LANGUAGE_COOKIE}={chosen}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000'
            + ('; Secure' if secure else ''))


def localize_document(page):
    """Set document metadata and add a switch without modifying page text or scripts."""
    page = re.sub(r'(<html\b[^>]*\blang=)[\"\'][^\"\']*[\"\']',
                  lambda match: match.group(1) + '"' + language() + '"', page, count=1)
    links = []
    for code, label in (('pl', 'Polski'), ('en', 'English')):
        href = '/language?' + urlencode({'lang': code, 'next': _return_path.get()})
        current = ' aria-current="true"' if code == language() else ''
        links.append('<a href="' + escape(href, quote=True) + '" lang="' + code
                     + '" hreflang="' + code + '" aria-label="' + label + '"'
                     + current + '>' + code.upper() + '</a>')
    switch = '<span class="language-switch" aria-label="Language / Język">' + ''.join(links) + '</span>'
    style = ('<style>.language-switch{display:inline-flex;gap:3px;align-items:center;'
             'white-space:nowrap;margin-left:8px}.language-switch a{padding:7px 9px;'
             'border:1px solid #535d6e;border-radius:0;color:#eef3fa;font:700 12px system-ui;'
             'text-decoration:none}.language-switch a[aria-current=true]{background:#ff7038;color:#101522;'
             'border-color:#ff7038}.language-switch-fallback{padding:12px 24px;text-align:right}</style>')
    if '</head>' in page:
        page = page.replace('</head>', style + '</head>', 1)
    else:
        page = page.replace('<main>', style + '<main>', 1)
    if '</nav>' in page:
        page = page.replace('</nav>', switch + '</nav>', 1)
    else:
        page = page.replace('<main>', '<div class="language-switch-fallback">' + switch + '</div><main>', 1)
    return page
