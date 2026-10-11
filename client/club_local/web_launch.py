"""Small participant window spawned by acrclub://start?ticket=... from a website.

Uses exactly the existing V3.1 Rally Weekend writer and AttemptMonitor.
No participant token is embedded in a web URL.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext
from urllib.parse import urlsplit, parse_qs

from acr_daily import rallyclub, saveslot, settings as acr_daily_settings
from .monitor import Api, ApiError, AttemptMonitor, baseline_counts
from . import integrity
from .checkpoint_restore import restore as restore_club_checkpoint
from .version import VERSION


def data_dir():
    directory = Path(os.environ.get('LOCALAPPDATA') or str(Path.home())) / 'ACR Rally Club'
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def configured_server():
    from .site_config import DEFAULT_SERVER
    config_path = data_dir() / 'launcher-config.json'
    if not config_path.exists():
        return DEFAULT_SERVER
    config = json.loads(config_path.read_text(encoding='utf-8'))
    server = str(config.get('server','')).rstrip('/')
    parsed = urlsplit(server)
    if parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
        raise ValueError('Nieprawidłowy adres serwera w launcher-config.json')
    if parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1','localhost'):
        if not config.get('allow_insecure_lan',False):
            raise ValueError('Zdalny serwer wymaga HTTPS; lokalny HTTP jest dozwolony')
    if parsed.scheme not in ('http','https') or not parsed.hostname:
        raise ValueError('Nieprawidłowy adres serwera')
    return server


def parse_launch_link(link):
    parsed = urlsplit(link)
    if parsed.scheme.lower() != 'acrclub' or parsed.netloc.lower() != 'start' or parsed.path not in ('','/'):
        raise ValueError('Niepoprawny adres acrclub://')
    qs = parse_qs(parsed.query, keep_blank_values=True)
    if set(qs) != {'ticket'} or len(qs['ticket']) != 1:
        raise ValueError('Link RUN musi zawierać wyłącznie jednorazowy ticket')
    ticket=qs['ticket'][0]
    if not re.fullmatch(r'[A-Za-z0-9_-]{40,128}',ticket):
        raise ValueError('Błędny format biletu')
    return ticket


def single_instance_lock():
    """Only one live launcher per Windows user to prevent accidental double starts."""
    if os.name != 'nt':
        return None
    import ctypes
    k32=ctypes.windll.kernel32
    k32.CreateMutexW.restype=ctypes.c_void_p
    handle=k32.CreateMutexW(None, True, 'Local\\ACRRallyClubWebLauncher')
    if not handle:
        raise RuntimeError('Nie udało się utworzyć blokady launchera')
    if k32.GetLastError() == 183:
        k32.CloseHandle(handle)
        raise RuntimeError('Launcher już działa. Przejdź do jego okna.')
    return handle


class WebLaunchWindow:
    def __init__(self, root, ticket):
        self.root=root
        self.ticket=ticket
        self.running=True
        self.queue=queue.Queue()
        self.monitor=None
        self.finished=False
        root.title('ACR Rally Club V'+VERSION+' — start ze strony')
        root.geometry('720x450')
        root.minsize(540,320)
        root.configure(bg='#13212c')
        tk.Label(root,text='ACR RALLY CLUB',font=('Segoe UI',19,'bold'),
                 fg='white',bg='#13212c').pack(anchor='w',padx=18,pady=(14,5))
        self.status=tk.StringVar(value='Łączenie z serwerem i weryfikacja biletu RUN...')
        tk.Label(root,textvariable=self.status,fg='#55e0ad',bg='#13212c',
                 wraplength=650,justify='left').pack(anchor='w',padx=18,pady=(0,12))
        self.text=scrolledtext.ScrolledText(root,background='#0c1822',foreground='#d7ecfa',
                                            height=15,font=('Consolas',10))
        self.text.pack(expand=True,fill='both',padx=18,pady=(0,16))
        self.text.tag_configure('warning',foreground='#ffd166')
        self.text.configure(state='disabled')
        self.nav_notice=tk.StringVar(value='Przejdź samodzielnie: Racing → Rally → Rally Weekend → WYBIERZ SAMOCHÓD I NIE ZMIENIAJ ŻADNYCH USTAWIEŃ → START RALLY → opony → START STAGE.')
        tk.Label(root,textvariable=self.nav_notice,fg='#55e0ad',bg='#13212c',
                 wraplength=650,justify='left').pack(anchor='w',padx=18,pady=(0,8))
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.log('Wersja launchera: '+VERSION+' · nawigacja w menu ACR: RĘCZNA')
        root.after(100,self.drain)
        threading.Thread(target=self.prepare,daemon=True).start()

    def log(self,msg):
        self.queue.put(('log',str(msg)))
        try:
            with (data_dir()/'player-events.log').open('a',encoding='utf-8') as f:
                f.write(time.strftime('%Y-%m-%d %H:%M:%S')+' [WEB] '+str(msg)+'\n')
        except OSError:
            pass

    def set_status(self,value):
        self.queue.put(('status',value))

    def set_navigation(self,value):
        self.queue.put(('navigation',value))

    def drain(self):
        try:
            while True:
                kind,data=self.queue.get_nowait()
                if kind=='log':
                    self.text.configure(state='normal')
                    self.text.insert('end',time.strftime('%H:%M:%S')+'  '+data+'\n',('warning',) if data.startswith(('OSTRZEŻENIE:','NIEZGODNOŚĆ')) else ())
                    self.text.see('end')
                    self.text.configure(state='disabled')
                elif kind=='navigation':
                    self.nav_notice.set(data)
                else:
                    self.status.set(data)
        except queue.Empty:
            pass
        if self.running:
            self.root.after(120,self.drain)

    def prepare(self):
        api=None
        preparation_complete=False
        try:
            # Force a runtime verification of a module that an earlier EXE omitted.
            # This runs before redeeming the one-time RUN ticket.
            if not callable(getattr(acr_daily_settings, 'load', None)):
                raise RuntimeError('Launcher EXE jest niekompletny (acr_daily.settings). Zainstaluj wersję 0.2 lub nowszą.')
            server=configured_server()
            if saveslot.game_running():
                raise RuntimeError('Zamknij Assetto Corsa Rally przed kliknięciem RUN; zapis .sav nie może być zmieniany przy uruchomionej grze.')
            api=Api(server)
            launch=api.call('/api/launcher/redeem', {'ticket':self.ticket})
            self.ticket=None
            event=launch['event']
            nickname=launch['nickname']
            token=launch['token']
            player_id=launch['playerId']
            api.token=token
            self.log(f'RUN potwierdzony: {nickname} · {event["name"]} · {len(event["stages"])} OS')
            catalog=api.call('/api/catalog')
            state=api.call('/api/me')
            if state['status'] not in ('registered','ready'):
                raise RuntimeError('Rajd nie może być wznowiony: '+state['status'])

            # Session path is shared with the classic GUI, without importing it.
            SESSION = data_dir() / 'player-session.json'
            try:
                old=json.loads(SESSION.read_text(encoding='utf-8'))
            except (OSError,ValueError):
                old={}
            restored=None
            if state['status']=='ready' or state.get('recoveryRequired'):
                if not event.get('allowBreaks',True):
                    api.call('/api/integrity-violation',{'reason':'Próba wznowienia rajdu wymagającego jazdy na raz'})
                    raise RuntimeError('Rajd wymaga jazdy na raz; ponowne uruchomienie oznacza DNF')
                restored=restore_club_checkpoint(api,event,player_id,state,self.log)
                if restored is not None:
                    old=restored
            same=(old.get('eventId')==event['id'] and old.get('playerId')==player_id)
            if state['status']=='ready' and (not same or old.get('baseline') is None):
                raise RuntimeError('Brak zapisanej bazy wyników poprzedniego OS-u na tym komputerze. '
                    'Wstrzymuję start zamiast dopuścić niezweryfikowany wynik.')
            baseline=old.get('baseline') if same else None
            if baseline is None:
                baseline=baseline_counts(Path(saveslot.SAVE).read_bytes())
            session={'server':server,'eventId':event['id'],'playerId':player_id,
                     'nickname':nickname,'token':token,'baseline':baseline}
            SESSION.write_text(json.dumps(session,ensure_ascii=False,indent=2),encoding='utf-8')
            try:
                from acr_daily import rallyweekend
                for entry in rallyweekend.results(Path(saveslot.SAVE).read_bytes())[-10:]:
                    self.log('KATALOG: stageId='+entry['stage']+' | carId='+','.join(r['car'] for r in entry['runs']))
            except (OSError,ValueError,IndexError,TypeError): pass
            if state['status']=='registered' and restored is None:
                self.log('Tworzę kopię bezpieczeństwa i przygotowuję Rally Weekend w Twoim zapisie...')
                rallyclub.write_club_weekend(event,event['allowedCars'][0],{c['id']:c for c in catalog['cars']},replace_in_progress=True)
                self.log('Kalendarz rajdu został zapisany; gra jest nadal zamknięta.')
            else:
                self.log('Wznawiam przed kolejnym OS-em z '+('kopii serwera.' if restored is not None else 'oryginalnego lokalnego zapisu Club.'))
            integrity.read_and_check(event)
            self.log('Kontrola zasad i kalendarza Rally Weekend: OK')
            monitor=AttemptMonitor(api,event,nickname,self.log,baseline=baseline)
            monitor.resume()
            if monitor.dead:
                raise RuntimeError('Próba zablokowana przez serwer')
            if state['status']=='registered' and event.get('allowBreaks',True):
                monitor._capture_recovery_copy(time.monotonic())
                if state.get('recoveryRequired') and restored is None:
                    if not monitor.snapshot_digest:
                        raise RuntimeError('Nie potwierdzono poprawnej kopii OS1 na serwerze. Podejście zachowane; ponów RUN.')
                    api.call('/api/recovery-ack',{'digest':monitor.snapshot_digest,'settings':integrity.read_and_check(event)})
            self.monitor=monitor
            preparation_complete=True
            self.set_status(f'Nadzór aktywny · oczekuję na START OS {monitor.stage_index+1}')
            navigation=('Otwórz Racing → Rally → Rally Weekend i kontynuuj zapisany rajd przed OS '+str(monitor.stage_index+1)+'. Nie twórz nowego Rally Weekend i nie zmieniaj samochodu ani ustawień.' if state['status']=='ready' else 'Przejdź samodzielnie: Racing → Rally → Rally Weekend → WYBIERZ SAMOCHÓD I NIE ZMIENIAJ ŻADNYCH USTAWIEŃ → START RALLY → opony → START STAGE.')
            self.set_navigation(navigation)
            if os.name=='nt':
                os.startfile('steam://rungameid/3917090')
                self.log('ACR uruchomione przez Steam. Nie zamykaj launchera podczas jazdy.')
                self.log(navigation)
            else:
                self.log('Symulacja poza Windows: nie uruchamiam Steam')
            self.watch(monitor)
        except Exception as exc:
            if not preparation_complete and api is not None and getattr(api,'token',None):
                try:
                    api.call('/api/launcher/abort',{})
                    self.log('Wstępny RUN anulowany na serwerze (nie zużyto podejścia).')
                except Exception as cleanup:
                    self.log('Nie udało się odblokować biletu RUN: '+str(cleanup))
            self.log('BŁĄD: '+str(exc))
            if not preparation_complete and ('sav' in str(exc).lower() or isinstance(exc,(FileNotFoundError,integrity.IntegrityError))):
                self.log('Jeśli brakuje poprawnego pliku Rally Weekend: ustaw w grze dowolny Rally Weekend, uruchom OS (nie musisz kończyć), wyjdź z gry i kliknij ponownie RUN na stronie. Nie zmieniaj ustawień rajdu po RUN.')
            self.set_status('Błąd uruchamiania · sprawdź szczegóły w dzienniku')

    def watch(self, monitor):
        try:
            while self.running and not monitor.dead:
                try:
                    monitor.poll()
                    self.set_status('OSTRZEŻENIE · podejście zachowane. Zamknij grę i launcher, potem kliknij RUN.' if monitor.recovery_required else f'{monitor.status.upper()} · OS {min(monitor.stage_index+1,len(monitor.event["stages"]))}/{len(monitor.event["stages"])}')
                except Exception as exc:
                    self.log('Błąd nadzoru: '+str(exc))
                    if monitor.status=='active':
                        monitor._server_dnf('Błąd aplikacji podczas aktywnego OS-u')
                    break
                time.sleep(.10)
        finally:
            try: monitor.close()
            except Exception as exc: self.log('Błąd zamykania monitoringu: '+str(exc))
            self.finished=True
            self.set_status('Nadzór zakończony · '+monitor.status.upper())
            self.log('Koniec nadzoru: '+monitor.status)

    def close(self):
        if self.monitor and self.monitor.recovery_required:
            if not self.monitor.recovery_notified:
                messagebox.showwarning('ACR Rally Club','Poczekaj na potwierdzenie ostrzeżenia na serwerze; sprawdź połączenie internetowe.')
                return
            self.running=False
            self.root.destroy()
            return
        if self.monitor and self.monitor.status=='active':
            if not messagebox.askyesno('ACR Rally Club',
                  'OS jest aktywny. Zamknięcie launchera oznacza DNF całego rajdu. Zamknąć?'):
                return
            self.monitor.close()
        if self.monitor and self.monitor.status=='ready' and self.monitor.event.get('launcherProtocol')=='0.2.4':
            if not self.monitor.event.get('allowBreaks',True):
                if not messagebox.askyesno('ACR Rally Club','Ten rajd wymaga jazdy na raz. Zamknięcie launchera oznacza DNF. Zamknąć?'): return
                self.monitor.close()
            elif not self.monitor.checkpoint_sent and (self.monitor.event.get('launcherProtocol')=='0.2.4' or self.monitor.event['stages'][self.monitor.stage_index].get('serviceBefore',False)):
                messagebox.showwarning('ACR Rally Club','Najpierw wyjdź z gry na dozwolonym serwisie i poczekaj na komunikat PRZERWA: kopia zapisu przesłana na serwer. Nie zamykaj launchera przed potwierdzeniem kopii.')
                return
        self.running=False
        self.root.destroy()


def main(link):
    ticket=parse_launch_link(link)
    guard=single_instance_lock()
    # Keep mutex handle alive as long as Tk's event loop runs.
    _=guard
    root=tk.Tk()
    WebLaunchWindow(root,ticket)
    root.mainloop()
