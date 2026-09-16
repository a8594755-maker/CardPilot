"""Observe current users of two preserved checkpoint files; never close them."""
import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
RUN = HERE.parent / 'moving256_stage1'
FILES = [RUN / 'latest.pt', RUN / '.latest.pt.c836605996e94811862c30e5da30ad98.pending']


class UniqueProcess(C.Structure):
    _fields_ = [('pid', W.DWORD), ('start', W.FILETIME)]


class ProcessInfo(C.Structure):
    _fields_ = [('process', UniqueProcess), ('app_name', W.WCHAR * 256),
                ('service_name', W.WCHAR * 64), ('app_type', C.c_int),
                ('app_status', W.ULONG), ('session_id', W.DWORD), ('restartable', W.BOOL)]


def inspect(paths):
    api = C.WinDLL('Rstrtmgr.dll')
    api.RmStartSession.argtypes = [C.POINTER(W.DWORD), W.DWORD, W.LPWSTR]
    api.RmStartSession.restype = W.DWORD
    api.RmRegisterResources.argtypes = [W.DWORD, W.UINT, C.POINTER(W.LPCWSTR), W.UINT,
                                       C.POINTER(UniqueProcess), W.UINT, C.POINTER(W.LPCWSTR)]
    api.RmRegisterResources.restype = W.DWORD
    api.RmGetList.argtypes = [W.DWORD, C.POINTER(W.UINT), C.POINTER(W.UINT),
                             C.POINTER(ProcessInfo), C.POINTER(W.DWORD)]
    api.RmGetList.restype = W.DWORD
    api.RmEndSession.argtypes = [W.DWORD]
    api.RmEndSession.restype = W.DWORD
    handle, key = W.DWORD(), C.create_unicode_buffer(33)
    code = api.RmStartSession(C.byref(handle), 0, key)
    if code:
        return {'api_error': int(code), 'api': 'RmStartSession', 'processes': None}
    try:
        names = (W.LPCWSTR * len(paths))(*(str(p.resolve()) for p in paths))
        code = api.RmRegisterResources(handle, len(paths), names, 0, None, 0, None)
        if code:
            return {'api_error': int(code), 'api': 'RmRegisterResources', 'processes': None}
        needed, count, reasons = W.UINT(), W.UINT(), W.DWORD()
        code = api.RmGetList(handle, C.byref(needed), C.byref(count), None, C.byref(reasons))
        for _ in range(3):
            if code != 234:
                break
            count = W.UINT(needed.value)
            buffer = (ProcessInfo * count.value)()
            code = api.RmGetList(handle, C.byref(needed), C.byref(count), buffer, C.byref(reasons))
        if code:
            return {'api_error': int(code), 'api': 'RmGetList', 'processes': None}
        rows = []
        for item in buffer[:count.value] if count.value else []:
            stamp = (item.process.start.dwHighDateTime << 32) | item.process.start.dwLowDateTime
            rows.append({'pid': int(item.process.pid), 'create_time': stamp / 10000000 - 11644473600,
                         'app_name': item.app_name, 'service_name': item.service_name,
                         'application_type': int(item.app_type)})
        return {'api_error': 0, 'processes': rows, 'reboot_reason_bitmask': int(reasons.value)}
    finally:
        api.RmEndSession(handle)


def main():
    out = HERE / 'current_file_users.json'
    if out.exists() or not all(p.is_file() for p in FILES):
        raise ValueError('Preserved target files required; prior diagnostics must not be overwritten')
    begin = time.perf_counter()
    value = {'created_at': datetime.now(timezone.utc).isoformat(), 'command': [sys.executable, *sys.argv],
             'paths': [str(p) for p in FILES], 'current_observation': inspect(FILES),
             'failure_time_holder_not_established': True, 'no_shutdown_or_restart_calls': True,
             'permissions_and_file_contents_unchanged': True,
             'wall_seconds': time.perf_counter() - begin,
             'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'references': ['https://learn.microsoft.com/en-us/windows/win32/api/restartmanager/nf-restartmanager-rmgetlist',
                            'https://learn.microsoft.com/en-us/windows/win32/api/restartmanager/ns-restartmanager-rm_process_info'],
             'training_hands': 0, 'evaluation_hands': 0}
    with out.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')
    print(json.dumps(value, indent=2))


if __name__ == '__main__':
    main()
