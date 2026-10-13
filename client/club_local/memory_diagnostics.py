"""Read-only own-process and system counters; no game-memory scanning."""
import ctypes
import os
from ctypes import wintypes


class Counters(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in
        ('peakWorking', 'working', 'peakPaged', 'paged', 'peakNonpaged', 'nonpaged', 'pagefile', 'peakPagefile', 'private')]


class Status(ctypes.Structure):
    _fields_ = [('length', wintypes.DWORD), ('load', wintypes.DWORD)] + [(name, ctypes.c_ulonglong) for name in
        ('totalPhys', 'availPhys', 'totalPage', 'availPage', 'totalVirtual', 'availVirtual', 'availExtended')]


def snapshot():
    if os.name != 'nt':
        return None
    try:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(Status)]
        counters, status = Counters(), Status()
        counters.cb, status.length = ctypes.sizeof(counters), ctypes.sizeof(status)
        if not kernel.K32GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return None
        if not kernel.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        mib = 1024 * 1024
        return (f'PAMIĘĆ: launcher RAM={counters.working/mib:.1f} MiB; prywatna={counters.private/mib:.1f} MiB; '
                f'system wolny RAM={status.availPhys/mib:.0f} MiB; dostępny commit dla procesu={status.availPage/mib:.0f} MiB')
    except (OSError, AttributeError):
        return None
