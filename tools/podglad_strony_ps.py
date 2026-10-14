"""Podgląd projectsimracing.pl razem z lokalnym serwerem ACR — BEZ zmieniania plików strony.

Serwuje folder strony ligi (do-wyslania) na http://localhost:8000 i w locie
podmienia dwa pliki ustawień, tak jak wyglądałyby po integracji:

  * assets/js/zrodla.js  -> sources.acr wskazuje na lokalny serwer ACR,
  * assets/js/config.js  -> dopisane: pozycja „Klub AC Rally” w menu, link w hubie,
                            nazwa sezonu ACR i przycisk na stronie wyników.

Uruchomienie (najpierw serwer ACR na porcie 8790):

    python tools/podglad_strony_ps.py --site ../../do-wyslania

Potem otwórz http://localhost:8000/wyniki.html?champ=acr
"""
import argparse
import functools
import http.server
import re
from pathlib import Path

CONFIG_PATCH = r"""
/* ---- PODGLĄD INTEGRACJI ACR (dopisane przez tools/podglad_strony_ps.py) ---- */
(function (C, ACR) {
  C.nav.splice(2, 0, { label: { pl: 'Klub AC Rally', en: 'AC Rally Club' }, href: ACR + '/' });
  C.championships.forEach(function (c) {
    if (c.id === 'acr') { c.season = { pl: 'Sezon 1', en: 'Season 1' }; c.sheetUrl = ACR + '/seasons'; }
  });
  C.hub.forEach(function (col) {
    col.links.forEach(function (l, i) {
      if (l.label === 'Assetto Corsa Rally') {
        col.links[i] = { label: { pl: 'Assetto Corsa Rally — rajdy i zapisy', en: 'Assetto Corsa Rally — rallies' }, href: ACR + '/', tag: 'ACR' };
      }
    });
  });
  C.seriesLabel.acr = { pl: 'Assetto Corsa Rally · Sezon 1', en: 'Assetto Corsa Rally · Season 1' };
})(window.PS_CONFIG, '__ACR__');
"""


class Handler(http.server.SimpleHTTPRequestHandler):
    acr = 'http://127.0.0.1:8790'

    def send_head(self):
        path = self.path.split('?', 1)[0]
        if path in ('/assets/js/zrodla.js', '/assets/js/config.js'):
            file = Path(self.translate_path(path))
            text = file.read_text(encoding='utf-8')
            if path.endswith('zrodla.js'):
                text = re.sub(r"acr:\s*'[^']*'", "acr: '" + self.acr + "/api/ps/wyniki'", text, count=1)
            else:
                text += CONFIG_PATCH.replace('__ACR__', self.acr)
            raw = text.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            import io
            return io.BytesIO(raw)
        return super().send_head()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default=str(Path(__file__).resolve().parents[2] / 'do-wyslania'),
                    help='folder strony ligi (domyślnie ../../do-wyslania względem repozytorium)')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--acr', default='http://127.0.0.1:8790', help='adres lokalnego serwera ACR')
    args = ap.parse_args()
    site = Path(args.site).resolve()
    if not (site / 'wyniki.html').is_file():
        raise SystemExit('Nie znaleziono wyniki.html w ' + str(site) + ' — podaj --site')
    Handler.acr = args.acr.rstrip('/')
    server = http.server.ThreadingHTTPServer(('127.0.0.1', args.port), functools.partial(Handler, directory=str(site)))
    print('Strona ligi (podgląd): http://localhost:%d/wyniki.html?champ=acr' % args.port)
    print('Serwer ACR:            ' + Handler.acr + '/')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
