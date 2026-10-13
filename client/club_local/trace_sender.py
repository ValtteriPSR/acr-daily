"""One-Hz samples, live bounded batches on an independent network worker."""
from collections import deque
import math,threading,time

class TraceSender:
    def __init__(self,api,event_id,emit):
        self.api,self.event_id,self.emit=api,event_id,emit
        self.buffer=deque();self.lock=threading.Lock();self.stop=threading.Event()
        self.last_clock={};self.last_sample={};self.sequences={};self.dropped={};self.started=False
        self.thread=None;self.pending=None;self.last_warning=-100.0
        self.disabled=set()

    def observe(self,index,frame,now):
        if index in self.disabled:return
        if frame is None or type(frame.clock_ms) is not int or frame.clock_ms<0:return
        if now-self.last_sample.get(index,-2)<1 or frame.clock_ms<=self.last_clock.get(index,-1):return
        values=[getattr(frame,k,None) for k in ('x','z','speed')]
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):return
        point=[frame.clock_ms,round(values[0],2),round(values[1],2),round(values[2],2)]
        for key,lo,hi in [('gas',0,1),('brake',0,1),('steer',-2,2),('gear',-1,12),('rpm',0,20000)]:
            value=getattr(frame,key,None)
            point.append(round(value,3) if type(value) in (int,float) and math.isfinite(value) and lo<=value<=hi else None)
        value=getattr(frame,'airborne',None);point.append(value if type(value) is bool else None)
        with self.lock:
            self.last_clock[index]=frame.clock_ms;self.last_sample[index]=now
            if len(self.buffer)>=90:
                lost,_=self.buffer.popleft();self.dropped[lost]=self.dropped.get(lost,0)+1
            self.buffer.append((index,point))
            if not self.started:
                self.emit('TELEMETRIA: zapis ścieżki, prędkości i sterowania na żywo (około 1 próbka/s). Dane do przeglądu są dostępne na podstronie rajdu przez 30 dni po jego zakończeniu.')
                self.started=True;self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def take_batch(self):
        with self.lock:
            if not self.buffer:return None
            idx=self.buffer[0][0];points=[]
            while self.buffer and self.buffer[0][0]==idx and len(points)<12:points.append(self.buffer.popleft()[1])
            return {'eventId':self.event_id,'stageIndex':idx,'seq':self.sequences.get(idx,0),'points':points,'dropped':self.dropped.get(idx,0)}

    def run(self):
        while not self.stop.wait(3):
            self.send_once()
        # Try the final partial live batch. A stopped sender never blocks timing checks.
        self.send_once()

    def send_once(self):
        if self.pending is None:self.pending=self.take_batch()
        if self.pending is None:return
        try:
            self.api.call('/api/live-telemetry',self.pending)
            idx=self.pending['stageIndex'];self.sequences[idx]=self.pending['seq']+1;self.pending=None
        except Exception as exc:
            if str(exc).startswith(tuple('HTTP '+str(code)+':' for code in (400,401,403,404,409,410,413,507))):
                # An expired/invalid stage must not block telemetry for a later SS.
                index=self.pending['stageIndex'];self.disabled.add(index);self.pending=None
                with self.lock:
                    self.buffer=deque((i,p) for i,p in self.buffer if i!=index)
            now=time.monotonic()
            if now-self.last_warning>=30:
                self.last_warning=now;self.emit('OSTRZEŻENIE: telemetria chwilowo nie dotarła na serwer; bufor jest ograniczony. Wyniki i kontrola OS-u działają niezależnie. '+str(exc))

    def close(self):
        self.stop.set()
