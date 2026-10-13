"""Read-only extension of the pinned upstream telemetry reader.

ACC-layout acpmf_graphics penaltyTime is at byte 1220, after coordinates,
car IDs and playerCarID. See nobonobo/ac-telemetry/graphics.go (MIT).
Unsupported/invalid/mismatched frames are unknown, never proof of zero penalties.
No process injection, save writes or guessed result-screen OCR is involved.
"""
import math
import re
import struct
import time
from .read_only_memory import Block, Source


def penalty_from_bytes(data, frame):
    if len(data) < 1224:
        return None
    packet = struct.unpack_from('<i', data, 0)[0]
    text=data[12:42].decode('utf-16-le', 'replace').split('\0')[0].strip()
    if not re.fullmatch(r'\d+(?::\d+){1,2}\.\d{3}',text): return None
    parts=text.split(':')
    clock=round((sum(int(v)*60**(len(parts)-1-i) for i,v in enumerate(parts[:-1]))+float(parts[-1]))*1000)
    value = struct.unpack_from('<f', data, 1220)[0]
    if packet != frame.packet or clock != frame.clock_ms or not math.isfinite(value) or not 0 <= value <= 3600:
        return None
    return round(value * 1000)


class SharedMemory:
    def __init__(self):
        from acr_daily import telemetry
        self.telemetry=telemetry
        self.source = Source()
        self.penalty_block = None
        self.next_penalty_open = 0.0

    @property
    def unloaded(self):
        return self.source.unloaded

    def read(self):
        frame = self.source.read()
        if frame is None:
            if self.penalty_block is not None:
                self.penalty_block.close()
                self.penalty_block = None
            return None
        frame.penalty_ms = None
        try:
            if self.penalty_block is None:
                if time.monotonic() < self.next_penalty_open:
                    return frame
                self.penalty_block = Block('acpmf_graphics', 1224)
            frame.penalty_ms = penalty_from_bytes(self.penalty_block.read(), frame)
        except (OSError, ValueError, struct.error):
            self.next_penalty_open = time.monotonic() + 5.0
            # A short or unsupported mapping must not break normal timing.
            if self.penalty_block is not None:
                self.penalty_block.close()
                self.penalty_block = None
        return frame

    def close(self):
        self.source.close()
        if self.penalty_block is not None:
            self.penalty_block.close()
            self.penalty_block = None
