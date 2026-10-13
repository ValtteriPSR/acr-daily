"""Bounded, read-only views of mappings created by ACR. Never create mappings.

Opening all three blocks is transactional: release partial views on failure.
The pinned upstream opener otherwise loses partially opened views/handles.
"""
import ctypes
import time


class Block:
    def __init__(self, name, size, kernel=None):
        if size not in (200, 268, 296, 1224):
            raise ValueError('Unsupported telemetry block size')
        if kernel is None:
            from acr_daily.telemetry import _Block
            kernel = _Block.k32()
        self.kernel = kernel
        self.size = size
        self.handle = None
        self.addr = None
        self.handle = kernel.OpenFileMappingW(4, False, 'Local\\' + name)
        if not self.handle:
            raise OSError('no mapping ' + name)
        try:
            self.addr = kernel.MapViewOfFile(self.handle, 4, 0, 0, size)
            if not self.addr:
                raise OSError('cannot map ' + name)
        except Exception:
            self.close()
            raise

    def read(self):
        if not self.addr:
            raise OSError('Telemetry view is closed')
        return ctypes.string_at(self.addr, self.size)

    def close(self):
        if self.addr:
            self.kernel.UnmapViewOfFile(self.addr)
            self.addr = None
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


class Source:
    STALE_S = 5.0

    def __init__(self, block_factory=Block):
        self.block_factory = block_factory
        self.blocks = None
        self.last_packet = None
        self.last_change = 0.0
        self.next_open = 0.0
        self.unloaded = False

    def _open(self, now):
        opened = []
        try:
            for name, size in (('acpmf_graphics', 268), ('acpmf_physics', 296), ('acpmf_static', 200)):
                opened.append(self.block_factory(name, size))
        except OSError:
            for block in opened:
                block.close()
            self.next_open = now + 1.0
            return False
        self.blocks = tuple(opened)
        self.last_packet, self.last_change = None, now
        return True

    def close(self):
        if self.blocks:
            for block in self.blocks:
                block.close()
        self.blocks = None

    def read(self):
        from acr_daily.telemetry import frame_from_bytes
        now = time.monotonic()
        self.unloaded = False
        if self.blocks is None and (now < self.next_open or not self._open(now)):
            return None
        g, p, s = (block.read() for block in self.blocks)
        frame = frame_from_bytes(now, g, p, s)
        if frame.packet != self.last_packet:
            self.last_packet, self.last_change = frame.packet, now
        elif now - self.last_change > self.STALE_S:
            self.close()
            self.next_open = now + 1.0
            return None
        if frame.packet == 0 and not frame.track:
            self.unloaded = True
            return None
        return frame


def self_test():
    """Windows smoke check against our own disposable mapping, never ACR."""
    import os
    import uuid
    from ctypes import wintypes
    if os.name != 'nt':
        return
    from acr_daily.telemetry import _Block
    kernel = _Block.k32()
    kernel.CreateFileMappingW.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR]
    kernel.CreateFileMappingW.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    name = 'ACRClubSelfTest-' + uuid.uuid4().hex
    owner = kernel.CreateFileMappingW(wintypes.HANDLE(-1), None, 4, 0, 4096, 'Local\\' + name)
    assert owner
    def handles():
        count = wintypes.DWORD()
        assert kernel.GetProcessHandleCount(kernel.GetCurrentProcess(), ctypes.byref(count))
        return count.value
    try:
        before = handles()
        for _ in range(1000):
            block = Block(name, 200)
            assert block.read() == bytes(200)
            block.close(); block.close()
        def partial(block_name, size):
            if block_name != 'acpmf_graphics':
                raise OSError('Simulated missing physics mapping')
            return Block(name, 200)
        source = Source(partial)
        for i in range(1000):
            assert not source._open(float(i))
        source.close()
        assert handles() <= before + 2, 'Telemetry handle leak'
    finally:
        kernel.CloseHandle(owner)
