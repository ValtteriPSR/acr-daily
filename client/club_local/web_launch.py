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
        k32.CloseHandle.argtypes=[ctypes.c_void_p]
        k32.CloseHandle(handle)
        return None
    return handle


class WebLaunchWindow:
    def __init__(self, root, ticket=None):
        self.root=root
        self.ticket=ticket
        self.running=True
        self.queue=queue.Queue()
        self.monitor=None
        self.finished=False
        self.restart_link=None
        self.preparation_ready=False
        root.title('ACR Rally Club V'+VERSION+' — start ze strony')
        root.geometry('760x330')
        root.minsize(620,300)
        root.configure(bg='#13212c')
        tk.Label(root,text='ACR RALLY CLUB',font=('Segoe UI',19,'bold'),
                 fg='white',bg='#13212c').pack(anchor='w',padx=18,pady=(14,5))
        self.status=tk.StringVar(value='Łączenie z serwerem i weryfikacja biletu RUN...')
        tk.Label(root,textvariable=self.status,fg='#55e0ad',bg='#13212c',
                 wraplength=650,justify='left').pack(anchor='w',padx=18,pady=(0,12))
        self.setup_notice=tk.StringVar(value='')
        tk.Label(root,textvariable=self.setup_notice,fg='#ffd166',bg='#13212c',wraplength=650,justify='left').pack(anchor='w',padx=18,pady=(0,8))
        self.console_visible=False
        self.console_toggle=tk.Button(root,text='Rozwiń konsolę ▾',command=self.toggle_console)
        self.console_toggle.pack(anchor='w',padx=18,pady=(0,8))
        self.console_frame=tk.Frame(root,bg='#13212c')
        self.text=scrolledtext.ScrolledText(self.console_frame,background='#0c1822',foreground='#d7ecfa',
                                            height=15,font=('Consolas',10))
        self.text.pack(expand=True,fill='both',padx=18,pady=(0,16))
        self.text.tag_configure('warning',foreground='#ffd166')
        self.text.configure(state='disabled')
        self.nav_notice=tk.StringVar(value='Przejdź samodzielnie: Racing → Rally → Rally Weekend → WYBIERZ SAMOCHÓD I NIE ZMIENIAJ ŻADNYCH USTAWIEŃ → START RALLY → opony → START STAGE.')
        tk.Label(root,textvariable=self.nav_notice,fg='#55e0ad',bg='#13212c',
                 wraplength=650,justify='left').pack(anchor='w',padx=18,pady=(0,8))
        controls=tk.Frame(root,bg='#13212c');controls.pack(fill='x',padx=18,pady=(0,10))
        for label,action in [('Przywróć potwierdzoną kopię','restore')]:
            tk.Button(controls,text=label,command=lambda a=action:self.save_action(a)).pack(fill='x',pady=2)
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.log('Wersja launchera: '+VERSION+' · nawigacja w menu ACR: RĘCZNA')
        root.after(100,self.drain)
        if ticket is None:
            self.finished=True
            self.set_status('Narzędzia zapisu · gra musi być zamknięta podczas operacji')
            self.set_navigation('Po przywróceniu zapisu zrestartuj launcher i grę.')
        self.worker=threading.Thread(target=self.prepare if ticket else self.observe_private_stages,daemon=True)
        self.worker.start()

    def toggle_console(self):
        self.console_visible=not self.console_visible
        if self.console_visible:
            self.console_frame.pack(after=self.console_toggle,expand=True,fill='both')
            self.console_toggle.configure(text='Zwiń konsolę ▴')
            self.root.geometry('760x590')
        else:
            self.console_frame.pack_forget()
            self.console_toggle.configure(text='Rozwiń konsolę ▾')
            self.root.geometry('760x480' if self.setup_notice.get() else '760x330')

    def save_action(self,action):
        from . import save_safety
        if not self.finished and self.preparation_ready and self.monitor and self.monitor.status=='registered' and not saveslot.game_running():
            try:
                self.monitor.api.call('/api/launcher/abort',{})
                self.monitor.dead=True;self.finished=True
                self.log('Nadzór przed startem anulowany bez zużycia podejścia. Narzędzia zapisu są dostępne.')
            except Exception as exc:
                messagebox.showwarning('Zapis ACR','Nie udało się zwolnić wstępnego RUN: '+str(exc));return
        if not self.finished or (self.monitor and self.monitor.status=='active'):
            messagebox.showwarning('Zapis ACR','Najpierw zakończ nadzór. Nie zmieniaj zapisu podczas przygotowania lub aktywnego rajdu.');return
        try:
            if action=='restore':
                if not messagebox.askyesno('Przywrócenie zapisu','Przywrócić zachowaną kopię MASTER? Obecny zapis zostanie zachowany osobno. Kopia może cofnąć późniejsze zmiany i postęp. Rajd nie zostanie uruchomiony.'):
                    return
                source=save_safety.state().get('serverCopy')
                save_safety.restore_previous()
                self.log('Przywrócono potwierdzoną kopię. Zrestartuj launcher i grę, następnie kliknij RUN.')
                messagebox.showinfo('Przywrócono zapis','Zrestartuj launcher i grę, następnie kliknij RUN.')
                if source:
                    session=json.loads((data_dir()/'player-session.json').read_text(encoding='utf-8'))
                    if session.get('eventId')==source['eventId'] and session.get('playerId')==source['playerId']:
                        api=Api(session['server']);api.token=session['token']
                        api.call('/api/save-problem',{'digest':source['digest'],'reason':'Game could not load the save'})
                        self.log('Kopia rajdu została również oznaczona na serwerze; nie będzie przywracana ponownie.')
        except Exception as exc:messagebox.showwarning('Zapis ACR',str(exc))

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
                    lines=int(self.text.index('end-1c').split('.')[0])
                    if lines>1200:self.text.delete('1.0',f'{lines-1200}.0')
                    self.text.see('end')
                    self.text.configure(state='disabled')
                elif kind=='setup':
                    self.setup_notice.set(data)
                    if not self.console_visible:self.root.geometry('760x480' if data else '760x330')
                elif kind=='dialog':
                    messagebox.showinfo('ACR Rally Club — pierwsza kopia',data)
                elif kind=='navigation':
                    self.nav_notice.set(data)
                elif kind=='restart':
                    self.handle_run(data)
                    if not self.running:return
                else:
                    self.status.set(data)
        except queue.Empty:
            pass
        if self.running:
            self.root.after(120,self.drain)

    def handle_run(self,link):
        from .launcher_control import restart_problem
        problem=restart_problem(self.monitor,saveslot.game_running(),preparing=not self.preparation_ready and not self.finished)
        self.root.lift()
        if problem:
            messagebox.showwarning('ACR Rally Club — RUN',problem)
            return
        if not messagebox.askyesno('ACR Rally Club — restart EXE',
                'Launcher EXE jest już otwarty. Czy zamknąć tę sesję i uruchomić launcher ponownie dla klikniętego RUN? Gra zostanie otwarta dopiero po sprawdzeniu rajdu i przywróceniu właściwego zapisu.'):
            return
        # Recheck after the dialog: never replace an attempt that became active.
        problem=restart_problem(self.monitor,saveslot.game_running())
        if problem:
            messagebox.showwarning('ACR Rally Club — RUN',problem)
            return
        self.restart_link=link
        self.running=False
        self.root.destroy()

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
            from . import save_safety
            try:
                if save_safety.prepare_run():self.log(save_safety.MASTER_NOTICE)
            except save_safety.WeekendRequired:
                api.call('/api/launcher/abort',{})
                api=None;self.finished=True
                self.queue.put(('setup',save_safety.FIRST_WEEKEND_MESSAGE))
                self.log(save_safety.FIRST_WEEKEND_MESSAGE)
                self.set_status('Najpierw utwórz Rally Weekend w grze · podejście Club zachowane')
                self.set_navigation('Pozostaw launcher otwarty. Czekaj na żółte potwierdzenie utworzenia kopii; potem zamknij grę i kliknij RUN RALLY.')
                self.observe_private_stages(setup=True)
                return
            if Path(saveslot.SAVE).exists():save_safety.preflight()
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
                if state['status']=='ready' and not event.get('allowBreaks',True):
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
            monitor=AttemptMonitor(api,event,nickname,self.log,baseline=baseline,catalog=catalog['cars'])
            monitor.resume()
            if monitor.dead:
                raise RuntimeError('Próba zablokowana przez serwer')
            if state['status']=='registered' and state.get('recoveryRequired'):
                api.call('/api/recovery-ack',{'settings':integrity.read_and_check(event)})
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
            self.preparation_ready=True
            self.watch(monitor)
            self.observe_private_stages()
        except Exception as exc:
            self.finished=True
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
            self.observe_private_stages()

    def watch(self, monitor):
        from .save_safety import StageStartObserver
        observer=StageStartObserver(self.log)
        try:
            while self.running and not monitor.dead:
                try:
                    observer.poll()
                    monitor.poll()
                    self.set_status('OSTRZEŻENIE · podejście zachowane. Zamknij grę i launcher, potem kliknij RUN.' if monitor.recovery_required else f'{monitor.status.upper()} · OS {min(monitor.stage_index+1,len(monitor.event["stages"]))}/{len(monitor.event["stages"])}')
                except Exception as exc:
                    self.log('Błąd nadzoru: '+str(exc))
                    if monitor.status=='active':
                        monitor._server_dnf('Błąd aplikacji podczas aktywnego OS-u')
                    break
                time.sleep(.10)
        finally:
            observer.close()
            try: monitor.close()
            except Exception as exc: self.log('Błąd zamykania monitoringu: '+str(exc))
            self.finished=True
            self.set_status('Nadzór zakończony · '+monitor.status.upper())
            self.log('Koniec nadzoru: '+monitor.status)

    def observe_private_stages(self,launch_game=False,setup=False):
        from .save_safety import StageStartObserver
        def emit(message):
            self.log(message)
            if setup and message.startswith('Kopia MASTER została'):
                from .save_safety import SETUP_COMPLETE
                self.queue.put(('setup',SETUP_COMPLETE))
                self.set_status('Kopia gotowa · zamknij grę i kliknij RUN RALLY')
        observer=StageStartObserver(emit)
        try:
            observer.poll()  # Re-arm restoration before starting the new game process.
            if launch_game and os.name=='nt':os.startfile('steam://rungameid/3917090')
            while self.running:
                try:observer.poll()
                except (OSError,ValueError) as exc:
                    self.log('OSTRZEŻENIE: obserwacja kopii Master wstrzymana: '+str(exc))
                    return
                time.sleep(.10)
        finally:observer.close()

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


def main(link=None):
    ticket=parse_launch_link(link) if link else None
    guard=single_instance_lock()
    from .launcher_control import ControlServer,forward_run
    if os.name=='nt' and guard is None:
        if link:forward_run(data_dir(),link,parse_launch_link)
        else:messagebox.showwarning('ACR Rally Club','Launcher jest już otwarty. Użyj jego narzędzi zapisu.')
        return
    # Keep mutex handle alive as long as Tk's event loop runs.
    _=guard
    root=tk.Tk()
    window=WebLaunchWindow(root,ticket)
    control=None
    if os.name=='nt':
        try:control=ControlServer(data_dir(),lambda value:window.queue.put(('restart',value)),parse_launch_link)
        except OSError:window.log('OSTRZEŻENIE: automatyczny restart EXE niedostępny. Zamknij grę i launcher ręcznie przed następnym RUN.')
    try:root.mainloop()
    finally:
        window.running=False
        if window.restart_link:window.worker.join(timeout=10)
        if control:control.close()
        if guard:
            import ctypes
            k32=ctypes.windll.kernel32
            k32.ReleaseMutex.argtypes=[ctypes.c_void_p]
            k32.CloseHandle.argtypes=[ctypes.c_void_p]
            k32.ReleaseMutex(guard);k32.CloseHandle(guard)
    if window.restart_link:
        if window.worker.is_alive():raise RuntimeError('Nadzór nie zakończył się jeszcze. Ponownie kliknij RUN po zamknięciu starego launchera.')
        import subprocess
        command=[sys.executable,window.restart_link] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).resolve().parents[1]/'run_web_launcher.py'),window.restart_link]
        subprocess.Popen(command)
