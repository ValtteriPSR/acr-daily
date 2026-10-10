"""ACR Rally Club local participant GUI (Tk / Python 3.13).
Uses the ACR Daily telemetry/save parser, not any cheat-prone memory scanning.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser

from acr_daily import rallyclub, saveslot
from .monitor import Api, ApiError, AttemptMonitor, baseline_counts
from . import integrity


def app_dir():
    base = os.environ.get('LOCALAPPDATA') or str(Path.home())
    path = Path(base) / 'ACR Rally Club'
    path.mkdir(parents=True, exist_ok=True)
    return path

SESSION = app_dir() / 'player-session.json'
LOG = app_dir() / 'player-events.log'


class PlayerApp:
    def __init__(self, root):
        self.root = root
        root.title('ACR Rally Club — klient rajdowy / local test')
        root.geometry('880x660')
        self.events = []
        self.monitor = None
        self.api = None
        self.stopping = False
        self.busy = False
        self.jobs = queue.Queue()
        self.server = tk.StringVar(value='http://127.0.0.1:8790')
        self.nickname = tk.StringVar()
        self.event_label = tk.StringVar()
        self.state = tk.StringVar(value='Połącz się z lokalnym serwerem')
        self.session = self.load_session()
        if self.session:
            self.server.set(self.session.get('server', self.server.get()))
            self.nickname.set(self.session.get('nickname', ''))

        shell = ttk.Frame(root, padding=22)
        shell.pack(fill='both', expand=True)
        shell.columnconfigure(1, weight=1)
        ttk.Label(shell, text='ACR RALLY CLUB', font=('Segoe UI', 24, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w')
        ttk.Label(shell, text='Klient gracza · oficjalne wyniki i kary z Assetto Corsa Rally', foreground='#687687').grid(row=1, column=0, columnspan=2, sticky='w', pady=(0,18))
        ttk.Label(shell, text='Adres serwera').grid(row=2,column=0,sticky='w',pady=6)
        ttk.Entry(shell, textvariable=self.server).grid(row=2,column=1,sticky='ew')
        ttk.Label(shell, text='Twój nick (bez konta Steam)').grid(row=3,column=0,sticky='w',pady=6)
        ttk.Entry(shell, textvariable=self.nickname).grid(row=3,column=1,sticky='ew')
        ttk.Label(shell, text='Rajd').grid(row=4,column=0,sticky='w',pady=6)
        self.chooser = ttk.Combobox(shell, textvariable=self.event_label, state='readonly')
        self.chooser.grid(row=4,column=1,sticky='ew')
        topbuttons = ttk.Frame(shell)
        topbuttons.grid(row=5,column=0,columnspan=2,sticky='w',pady=(12,4))
        ttk.Button(topbuttons, text='Pobierz listę rajdów', command=self.refresh).pack(side='left',padx=(0,8))
        self.playbutton = ttk.Button(topbuttons, text='Pobierz rajd i uruchom ACR', command=self.play)
        self.playbutton.pack(side='left',padx=(0,8))
        ttk.Button(topbuttons, text='Strona z wynikami', command=self.open_page).pack(side='left')
        ttk.Separator(shell, orient='horizontal').grid(row=6,column=0,columnspan=2,sticky='ew',pady=(12,12))
        ttk.Label(shell, text='Stan rajdu:', font=('Segoe UI',10,'bold')).grid(row=7,column=0,sticky='w')
        ttk.Label(shell, textvariable=self.state, wraplength=620).grid(row=7,column=1,sticky='w')
        self.text = tk.Text(shell, height=20, background='#14202b', foreground='#d4e9fb',
                            insertbackground='white',font=('Consolas',10),wrap='word')
        self.text.grid(row=8,column=0,columnspan=2,sticky='nsew',pady=(14,10))
        shell.rowconfigure(8, weight=1)
        ttk.Label(shell, text='Zasady: jedna próba na OS. Restart / wyjście / niezgodne ustawienia Rally Weekend = DNF całego rajdu. Pauza dozwolona.',
                  wraplength=815,foreground='#687687').grid(row=9,column=0,columnspan=2,sticky='w')
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(100, self.drain)
        self.root.after(250, self.refresh)

    def load_session(self):
        try:
            return json.loads(SESSION.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return None

    def save_session(self):
        # Persist a random bearer token; the nickname alone is not sufficient to
        # hijack someone else's result entry.
        SESSION.write_text(json.dumps(self.session,ensure_ascii=False,indent=2), encoding='utf-8')

    def emit(self, msg):
        self.jobs.put(('log', str(msg)))
        try:
            with LOG.open('a', encoding='utf-8') as stream:
                stream.write(time.strftime('%Y-%m-%d %H:%M:%S') + ' ' + str(msg) + '\n')
        except OSError:
            pass

    def drain(self):
        try:
            while True:
                typ, val = self.jobs.get_nowait()
                if typ == 'log':
                    self.text.insert('end', time.strftime('%H:%M:%S') + '  ' + val + '\n')
                    self.text.see('end')
                elif typ == 'state':
                    self.state.set(val)
                elif typ == 'error':
                    messagebox.showerror('ACR Rally Club', val)
                elif typ == 'events':
                    self.events = val
                    labels = [f"{ev['name']} · {len(ev['stages'])} OS · {ev['carClass']}" for ev in val]
                    self.chooser['values'] = labels
                    selected = self.session.get('eventId') if self.session else None
                    index = next((i for i,e in enumerate(val) if e['id'] == selected), 0)
                    if labels:
                        self.chooser.current(index)
                        self.event_label.set(labels[index])
                    self.emit('Odebrano rajdy: ' + str(len(val)))
                elif typ == 'idle':
                    self.busy = False
                    self.playbutton.config(state='normal')
        except queue.Empty:
            pass
        if not self.stopping:
            self.root.after(120, self.drain)

    def background(self, fn, *args):
        if self.busy:
            return
        self.busy = True
        self.playbutton.config(state='disabled')
        def work():
            try:
                fn(*args)
            except Exception as exc:
                self.emit('BŁĄD: ' + str(exc))
                self.jobs.put(('error',str(exc)))
            finally:
                self.jobs.put(('idle',None))
        threading.Thread(target=work,daemon=True).start()

    def refresh(self):
        self.background(self._refresh, self.server.get().strip())

    def _refresh(self, address):
        api = Api(address)
        info = api.call('/api/events')
        self.jobs.put(('events',info['events']))

    def open_page(self):
        if self.events and self.chooser.current() >= 0:
            url = self.server.get().rstrip('/') + '/rally/' + self.events[self.chooser.current()]['id']
        else:
            url = self.server.get().rstrip('/') + '/'
        webbrowser.open(url)

    def play(self):
        if not self.events or self.chooser.current() < 0:
            return messagebox.showerror('ACR Rally Club','Pobierz i wybierz rajd')
        event = self.events[self.chooser.current()]
        nick = self.nickname.get().strip()
        if not 2 <= len(nick) <= 24:
            return messagebox.showerror('ACR Rally Club','Wpisz nick (2–24 znaki)')
        if self.monitor and not self.monitor.dead:
            return messagebox.showinfo('ACR Rally Club','Nadzór jest już aktywny')
        self.background(self._prepare_and_start, event, nick, self.server.get().strip())

    def _prepare_and_start(self, event, nick, server):
        server = server.rstrip('/')
        token = None
        if self.session and self.session.get('server')==server and \
                self.session.get('eventId')==event['id'] and \
                self.session.get('nickname','').casefold()==nick.casefold():
            token = self.session.get('token')
        api = Api(server, token)
        if not token:
            info = api.call('/api/join', {'eventId':event['id'], 'nickname':nick})
            token = info['token']
            self.session = dict(server=server, eventId=event['id'],nickname=nick,token=token)
            self.save_session()
            api.token = token
            self.emit('Zarejestrowano nick na serwerze; token zapisany lokalnie')
        state = api.call('/api/me')
        self.jobs.put(('state',f'{state["status"]} · OS {state["stage_index"]+1} z {len(event["stages"])}'))
        if state['status'] in ('dnf','completed'):
            raise RuntimeError('Rajd już zakończony: '+state['status']+' (blokada jednej próby)')
        if state['status']=='active':
            # Do not start another game while an active attempt is unresolved.
            monitor = AttemptMonitor(api,event,nick,self.emit)
            monitor.resume()
            raise RuntimeError('Przerwano poprzedni aktywny OS — DNF. Nie ma powtórek.')
        if saveslot.game_running():
            raise RuntimeError('Najpierw zamknij ACR. Podmiana własnego zapisu jest dozwolona tylko przy zamkniętej grze.')
        # Read before editing the save, so that old records are excluded.
        baseline = self.session.get('baseline') if self.session else None
        if baseline is None:
            baseline = baseline_counts(Path(saveslot.SAVE).read_bytes())
            self.session['baseline'] = baseline
            self.save_session()
        if state['status']=='registered':
            # Does not download another player's .sav; config is applied to the
            # current profile via ACR Daily's verified in-game save writer.
            self.emit('Pobrano konfigurację rajdu z serwera. Tworzę kopię zapasową .sav...')
            car_placeholder = event['allowedCars'][0] # only needed to validate class membership
            rallyclub.write_club_weekend(event, car_placeholder)
            self.emit(f'Zapisano lokalny Rally Weekend: {len(event["stages"])} OS')
        else:
            self.emit('Wznawiam bez zmiany pliku .sav (gotowy do kolejnego OS-u lub końcowych wyników)')
        # Read-back verification BEFORE launching Steam; the server will re-check
        # the same structured settings at every stage start, heartbeat and finish.
        integrity.read_and_check(event)
        self.emit('Kontrola ustawień: OK (uszkodzenia, kary, zasady, kalendarz)')
        monitor = AttemptMonitor(api,event,nick,self.emit,baseline=baseline)
        monitor.resume()
        if monitor.dead:
            return
        self.monitor = monitor
        self.api = api
        self.jobs.put(('state','Nadzór aktywny — czekam na pierwszy START OS-u'))
        if os.name == 'nt' and state['status'] != 'awaiting_results':
            try:
                os.startfile('steam://rungameid/3917090')
                self.emit('Uruchamiam Assetto Corsa Rally przez Steam (App ID 3917090)')
            except OSError as exc:
                self.emit('Steam nie uruchomił gry automatycznie. Uruchom ACR ręcznie: ' + str(exc))
        else:
            self.emit('Tryb testowy poza Windows — uruchamianie Steam wyłączone')
        threading.Thread(target=self._watch, args=(monitor,),daemon=True).start()

    def _watch(self, monitor):
        try:
            while not self.stopping and not monitor.dead:
                try:
                    monitor.poll()
                    self.jobs.put(('state',
                        f'{monitor.status.upper()} · OS {min(monitor.stage_index+1,len(monitor.event["stages"]))}/{len(monitor.event["stages"])}'+
                        (f' · RAW {monitor.highwater/1000:.3f}s' if monitor.status=='active' else '')))
                except Exception as exc:
                    self.emit('Problem telemetrii: '+str(exc))
                    if monitor.status=='active':
                        monitor._server_dnf('Błąd klienta podczas aktywnego OS')
                    break
                time.sleep(.10)
        finally:
            try:
                monitor.close()
            except Exception as exc:
                self.emit('Błąd kończenia nadzoru: '+str(exc))
            self.jobs.put(('state','Rajd zakończony lub nadzór przerwany'))

    def close(self):
        if self.monitor and self.monitor.status=='active':
            if not messagebox.askyesno('ACR Rally Club','Jesteś w trakcie OS! Zamknięcie klienta oznacza DNF całego rajdu. Zamknąć?'):
                return
            self.emit('Użytkownik zamknął klienta podczas OS')
            self.monitor.close()
        self.stopping = True
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use('clam')
    except tk.TclError:
        pass
    PlayerApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
