"""Authenticated local RUN handoff. JSON bytes only; never deserialize pickle."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
from multiprocessing.connection import Listener,Client
from multiprocessing import AuthenticationError


def restart_problem(monitor,game_running,preparing=False):
    if preparing:return 'Launcher przygotowuje zapis. Poczekaj na zakończenie przygotowania.'
    if monitor is not None and monitor.status=='active':
        return 'OS jest aktywny. RUN nie może restartować launchera ani dać drugiej próby. Restart lub wyjście z OS-u oznacza DNF.'
    if game_running:return 'Najpierw zamknij grę ACR, następnie ponownie kliknij RUN. Launcher nie podmieni zapisu przy otwartej grze.'
    if monitor is not None and monitor.status=='ready':
        if not monitor.event.get('allowBreaks',True):return 'Ten rajd wymaga jazdy na raz. Restart gry lub launchera między OS-ami oznacza DNF.'
        if monitor.recovery_required:
            if not monitor.recovery_notified:return 'Poczekaj na potwierdzenie ostrzeżenia na serwerze.'
        elif not (monitor.checkpoint_sent or monitor.snapshot_digest):return 'Brak potwierdzonej kopii po ostatnim OS-ie. Poczekaj na KOPIA CLUB lub PRZERWA przed kolejnym RUN.'
    return None


def pipe_address(directory):
    user=hashlib.sha256(str(Path(directory).resolve()).casefold().encode()).hexdigest()[:24]
    return r'\\.\pipe\ACRRallyClub-'+user


def serve_connection(connection,on_run,validate):
    try:
        payload=json.loads(connection.recv_bytes(4096).decode('utf-8'))
        if not isinstance(payload,dict) or set(payload)!={'link'}:raise ValueError('Invalid RUN request')
        validate(payload['link'])
        on_run(payload['link'])
        connection.send_bytes(b'{"forwarded":true}')
    finally:connection.close()


class ControlServer:
    def __init__(self,directory,on_run,validate):
        self.key_path=Path(directory)/'launcher-control.key'
        self.authkey=secrets.token_bytes(32)
        self.listener=Listener(pipe_address(directory),family='AF_PIPE',authkey=self.authkey)
        self.key_path.write_bytes(self.authkey)
        self.stopped=False
        self.on_run,self.validate=on_run,validate
        threading.Thread(target=self.run,daemon=True).start()

    def run(self):
        while not self.stopped:
            try:serve_connection(self.listener.accept(),self.on_run,self.validate)
            except (OSError,EOFError,ValueError,TypeError):continue
            except Exception:continue  # An invalid local message cannot stop the real launcher.

    def close(self):
        self.stopped=True
        self.listener.close()
        try:
            if self.key_path.read_bytes()==self.authkey:self.key_path.unlink()
        except OSError:pass


def forward_run(directory,link,validate):
    validate(link)
    try:
        key=(Path(directory)/'launcher-control.key').read_bytes()
        if len(key)!=32:raise ValueError('Invalid local control key')
        connection=Client(pipe_address(directory),family='AF_PIPE',authkey=key)
        try:
            connection.send_bytes(json.dumps({'link':link}).encode())
            if not connection.poll(4):raise RuntimeError('Existing launcher did not respond')
            answer=json.loads(connection.recv_bytes(4096).decode())
            if answer!={'forwarded':True}:raise ValueError('Invalid local RUN acknowledgement')
        finally:connection.close()
    except (OSError,EOFError,ValueError,RuntimeError,AuthenticationError) as exc:
        raise RuntimeError('Launcher EXE już działa. Zamknij grę i dotychczasowy launcher, potem ponownie kliknij RUN. Automatyczny restart wymaga aktualnego EXE 0.2.8.') from exc


def self_test(validate):
    """Exercise real authenticated Windows pipe inside the frozen build."""
    if os.name!='nt':return
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as directory:
        received=[]
        control=ControlServer(directory,received.append,validate)
        link='acrclub://start?ticket='+'a'*43
        try:
            forward_run(directory,link,validate)
            assert received==[link]
        finally:control.close()
