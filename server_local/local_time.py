"""Czas polski (Europe/Warsaw) bez zależności od bazy stref czasowych systemu.

Polska stosuje unijną regułę zmiany czasu: czas letni (UTC+2) od ostatniej
niedzieli marca 01:00 UTC do ostatniej niedzieli października 01:00 UTC,
poza tym czas zimowy (UTC+1). W bazie i API czasy pozostają w UTC — tu tylko
wyświetlamy je tak, jak widzi je kierowca w Polsce.
"""
from datetime import datetime, timedelta, timezone


def _last_sunday(year, month):
    day = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
    return day - timedelta(days=(day.weekday() + 1) % 7)


def warsaw_offset(moment):
    """Przesunięcie Polski względem UTC (1 lub 2 godziny) w danej chwili UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc)
    start = _last_sunday(moment.year, 3).replace(hour=1)
    end = _last_sunday(moment.year, 10).replace(hour=1)
    return 2 if start <= moment < end else 1


def to_warsaw(value):
    """ISO 8601 (ze strefą) albo datetime -> datetime w czasie polskim."""
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if moment.tzinfo is None:
        raise ValueError('Timestamp requires timezone')
    return moment.astimezone(timezone(timedelta(hours=warsaw_offset(moment))))


def label(value, fmt='%d.%m.%Y · %H:%M'):
    """Np. '25.10.2026 · 21:00' — bez dopisku strefy, bo to zwykły czas polski."""
    try:
        return to_warsaw(value).strftime(fmt)
    except (ValueError, TypeError):
        return str(value)[:24]


# Ten sam algorytm dla przeglądarki (panel administratora): zamiana pola
# datetime-local wpisanego w czasie polskim na UTC i odwrotnie.
JS = r"""
const plOffset=ms=>{const d=new Date(ms),y=d.getUTCFullYear();
  const last=m=>{const x=new Date(Date.UTC(y,m+1,0,1));x.setUTCDate(x.getUTCDate()-x.getUTCDay());return x.getTime()};
  return ms>=last(2)&&ms<last(9)?2:1};
const plToUtc=value=>{const naive=Date.parse(value+':00Z');if(!value||!Number.isFinite(naive))throw Error('Wpisz poprawną datę (czas polski)');
  let utc=naive-plOffset(naive)*3600000;utc=naive-plOffset(utc)*3600000;return new Date(utc).toISOString()};
const plFromUtc=iso=>{const ms=Date.parse(iso);if(!Number.isFinite(ms))return '';return new Date(ms+plOffset(ms)*3600000).toISOString().slice(0,16)};
const plLabel=(iso,dateOnly)=>{const v=plFromUtc(iso);if(!v)return '';const [d,t]=v.split('T');const [Y,M,D]=d.split('-');return D+'.'+M+'.'+Y+(dateOnly?'':' '+t)};
"""


def polish_admin_time(page):
    """Panele administratora: pola dat i listy w czasie polskim zamiast stałego UTC+2.

    Działa na już przetłumaczonym HTML (PL i EN), więc nie zmienia kluczy tłumaczeń.
    """
    import re
    from i18n import language
    zone = '(czas polski)' if language() == 'pl' else '(Polish time)'
    page = page.replace('(UTC+2)', zone)
    page = page.replace("timeZone:'Etc/GMT-2'", "timeZone:'Europe/Warsaw'").replace("+' UTC+2'", '')
    page = re.sub(r"const isoLocal = utc => \{.*?\};", 'const isoLocal = plFromUtc;', page, count=1)
    page = re.sub(r"const toUtc = value => \{.*?return date\.toISOString\(\)\};", 'const toUtc = plToUtc;', page, count=1)
    page = re.sub(r"const localISO=iso=>\{.*?\};", 'const localISO=plFromUtc;', page, count=1)
    page = re.sub(r"const utc=txt=>\{.*?return d\.toISOString\(\)\};", 'const utc=plToUtc;', page, count=1)
    return page.replace('<script>', '<script>' + JS, 1)
