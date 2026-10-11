"""Database-backed public branding and validated data catalogs; portable across hosts."""
import base64
from contextvars import ContextVar
from functools import wraps
from html import escape
import json
import re
import struct
from urllib.parse import urlsplit
from i18n import tr

_current = ContextVar('club_branding', default={})
DEFAULTS = {'title':'ACR RALLY CLUB','subtitle':'Rally championship','tagline':'','discordInvite':'','logo':''}
MAX_LOGO = 256 * 1024


def install(store):
    store.db.execute('CREATE TABLE IF NOT EXISTS club_settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)')


def read(store, name, default):
    with store.lock:
        cache=getattr(store,'_club_settings_cache',None)
        if cache is None: cache=store._club_settings_cache={}
        if name in cache: return cache[name]
        row = store.db.execute('SELECT value FROM club_settings WHERE name=?', (name,)).fetchone()
        result=json.loads(row[0]) if row else default
        cache[name]=result
        return result


def write(store, name, value):
    with store.lock:
        store.db.execute('INSERT INTO club_settings(name,value) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',
                         (name,json.dumps(value,ensure_ascii=False)))
        getattr(store,'_club_settings_cache',{}).pop(name,None)


def public(store):
    return {**DEFAULTS, **read(store, 'branding', {})}


def context(store):
    def decorate(method):
        @wraps(method)
        def wrapped(*args, **kwargs):
            if args and args[0].path.startswith('/api/'):
                return method(*args,**kwargs)
            b=public(store)
            custom=read(store,'catalog',None)
            if custom: b['catalog']=custom
            token = _current.set(b)
            try: return method(*args, **kwargs)
            finally: _current.reset(token)
        return wrapped
    return decorate


def branding():
    return {**DEFAULTS, **_current.get()}


def brand_html(admin=False):
    b=branding()
    logo = ('<img class="brand-logo" src="/club-logo" alt="" width="43" height="43">' if b['logo']
            else '<span class="brand-symbol">AC</span>')
    return '<a href="/" class="brand">'+logo+'<span>'+escape(b['title'])+'<span class="brand-sub">'+escape(b['subtitle'])+'</span></span></a>'


def invite_html():
    link=branding()['discordInvite']
    return '<a class="discord-invite" href="'+escape(link,quote=True)+'" target="_blank" rel="noopener noreferrer">Discord ↗</a>' if link else ''


def configure(store, data):
    from server import Fault
    b=public(store)
    for key,limit in [('title',80),('subtitle',100),('tagline',180)]:
        value=data.get(key,b[key])
        if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 for c in value):
            raise Fault(400, 'Invalid branding text')
        if key!='tagline' and not value.strip(): raise Fault(400, 'Title and subtitle cannot be empty')
        b[key]=value.strip()
    invite=data.get('discordInvite',b['discordInvite'])
    if not isinstance(invite,str) or len(invite)>200: raise Fault(400,'Invalid Discord invite')
    parts=urlsplit(invite)
    if invite and (parts.scheme!='https' or parts.netloc not in ('discord.gg','discord.com','www.discord.com') or parts.query or parts.fragment
                   or not re.fullmatch(r'/(?:invite/)?[A-Za-z0-9-]{2,100}',parts.path)
                   or (parts.netloc!='discord.gg' and not parts.path.startswith('/invite/'))):
        raise Fault(400,'Use an https://discord.gg/… or https://discord.com/invite/… invite')
    b['discordInvite']=invite
    if data.get('removeLogo') is True: b['logo']=''
    logo=data.get('logo','')
    if logo:
        # Bounded PNG only, served separately with nosniff and a restrictive CSP.
        if not isinstance(logo,str) or not logo.startswith('data:image/png;base64,'): raise Fault(400,'Choose a PNG logo (up to 256 KB)')
        try: raw=base64.b64decode(logo.split(',',1)[1],validate=True)
        except Exception: raise Fault(400,'Invalid PNG logo')
        if len(raw)>MAX_LOGO or len(raw)<33 or raw[:8]!=b'\x89PNG\r\n\x1a\n' or raw[12:16]!=b'IHDR': raise Fault(400,'Invalid PNG logo')
        width,height=struct.unpack('>II',raw[16:24])
        if not 1<=width<=2048 or not 1<=height<=2048: raise Fault(400,'Logo dimensions must be at most 2048 × 2048')
        b['logo']=logo
    write(store,'branding',b)
    return b


def catalog(store, root):
    from admin_panel import load_catalog
    base=load_catalog(root)
    custom=read(store,'catalog',None)
    if custom: base.update(custom)
    return base


def save_catalog(store,data):
    from server import Fault
    cleaned={}
    for kind,fields,limit in [('cars',('id','telemetry','name','cls','group'),500),('stages',('id','name'),2000)]:
        rows=data.get(kind)
        if not isinstance(rows,list) or not 1<=len(rows)<=limit: raise Fault(400,'Invalid catalog size')
        ids=set();out=[]
        for row in rows:
            if not isinstance(row,dict): raise Fault(400,'Invalid catalog row')
            item={}
            for field in fields:
                v=row.get(field)
                if not isinstance(v,str) or not 1<=len(v.strip())<=150 or any(ord(c)<32 for c in v): raise Fault(400,'Invalid catalog field: '+field)
                item[field]=v.strip()
            if not re.fullmatch(r'[A-Za-z0-9_]{1,100}',item['id']) or item['id'] in ids: raise Fault(400,'Invalid or duplicate ID')
            if kind=='stages' and not item['id'].startswith(('GreeceS','AlsaceS','WelesS','WalesS','MonteCarloS')): raise Fault(400,'Unsupported location prefix; the game save writer must support the location first')
            ids.add(item['id']);out.append(item)
        cleaned[kind]=out
    # Never silently remove IDs still used by an existing rally.
    cars={r['id']:r for r in cleaned['cars']};stages={r['id'] for r in cleaned['stages']}
    for ev in store.listing():
        if any(c not in cars or cars[c]['cls']!=ev['carClass'] for c in ev['allowedCars']) or any(s['stageId'] not in stages for s in ev['stages']):
            raise Fault(409,'Keep IDs and car classes used by existing rallies')
    write(store,'catalog',cleaned)
    return {'ok':True,**cleaned}
