"""OS dispatch fencing and local process identity for the component store."""
from contextlib import contextmanager
from functools import lru_cache
import errno
import hashlib
import os
from pathlib import Path
import socket
import sys
import time


class StoreLockError(Exception):
    """A store admission failure must not be recorded as unavailable provider data."""


class StoreLockLimit(StoreLockError, ValueError):
    pass


class StoreLockBusy(StoreLockError, RuntimeError):
    pass


class StoreLockExists(StoreLockError, FileExistsError):
    pass


@contextmanager
def dispatch_fence(marker, deadline):
    # Never replace or truncate the store marker. The Windows byte range is
    # beyond its JSON, so metadata readers and archive copies remain available.
    with marker.open('rb') as stream:
        if os.name == 'nt':
            import msvcrt
            stream.seek(1 << 30)
            def acquire():
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        while True:
            try:
                acquire()
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                if time.monotonic() >= deadline:
                    raise StoreLockBusy('STORE_DISPATCH_BUSY') from exc
                time.sleep(.01)
        yield
        # Closing the handle relinquishes the OS lock, also after abnormal exit.


def _linux_value(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def process_scope():
    result = {'platform': sys.platform}
    machine = None
    if sys.platform.startswith('linux'):
        machine = _linux_value('/etc/machine-id')
        result['boot'] = _linux_value('/proc/sys/kernel/random/boot_id')
        try:
            result['pid_namespace'] = os.readlink('/proc/self/ns/pid')
        except OSError:
            result['pid_namespace'] = None
    elif os.name == 'nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography',
                                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                machine = winreg.QueryValueEx(k, 'MachineGuid')[0]
        except OSError:
            pass
    elif sys.platform == 'darwin':
        import subprocess
        # Boot-session UUID distinguishes hosts without recording hardware data.
        try:
            session = subprocess.check_output(['/usr/sbin/sysctl', '-n', 'kern.bootsessionuuid'],
                                              stderr=subprocess.DEVNULL, timeout=2)
            import uuid
            result['boot'] = str(uuid.UUID(session.decode('ascii').strip()))
        except (OSError, ValueError, subprocess.SubprocessError):
            result['boot'] = None
    if machine:
        result['machine'] = hashlib.sha256(machine.encode('utf-8')).hexdigest()
    return result


def _windows_process(pid):
    # Query/inspect only. os.kill(pid, 0) can terminate a process on Windows.
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)  # limited query and synchronize
    if not handle:
        return ('dead' if ctypes.get_last_error() == 87 else 'unknown'), None
    try:
        wait = kernel.WaitForSingleObject(handle, 0)
        if wait == 0:
            return 'dead', None
        if wait != 258:  # WAIT_TIMEOUT means still running
            return 'unknown', None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return 'live', None
        creation = times[0]
        return 'live', str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
    finally:
        kernel.CloseHandle(handle)


def process_info(pid):
    if os.name == 'nt':
        return _windows_process(pid)
    if sys.platform.startswith('linux'):
        try:
            # comm (field 2) can contain spaces and parentheses; start is field 22.
            stat_fields = Path('/proc', str(pid), 'stat').read_bytes().rsplit(b') ', 1)[1].split()
            if stat_fields[0] in (b'Z', b'X'):
                return 'dead', None
            return 'live', str(int(stat_fields[19]))
        except (IndexError, OSError, ValueError):
            pass
    try:
        os.kill(pid, 0)
        return 'live', None
    except ProcessLookupError:
        return 'dead', None
    except (OSError, OverflowError):
        return 'unknown', None


def dead_reason(record, host, scope, pid):
    if record['hostname'] != host or record['process_scope'].get('platform') != scope['platform']:
        return None
    previous = record['process_scope']
    if previous.get('machine') != scope.get('machine'):
        return None
    if os.name == 'nt' and not scope.get('machine'):
        return None
    if sys.platform.startswith('linux'):
        if previous.get('boot') != scope.get('boot'):
            if previous.get('boot') and scope.get('boot') and scope.get('machine'):
                return 'PREVIOUS_BOOT'
            return None
        if not scope.get('pid_namespace') or previous.get('pid_namespace') != scope['pid_namespace']:
            return None
        if not scope.get('boot'):
            return None
    elif sys.platform == 'darwin':
        if not scope.get('boot') or previous.get('boot') != scope['boot']:
            return None
    elif os.name != 'nt':
        return None
    owner_pid = record['pid']
    if owner_pid == pid:
        # Handles PID reuse on restart while avoiding a syscall per current-owner capture.
        status, creation = 'live', _self_start(pid)
    else:
        status, creation = process_info(owner_pid)
    if status == 'dead':
        return 'OWNER_EXITED'
    initial = record['process_start']
    if status == 'live' and initial and creation and initial != creation:
        return 'PID_REUSED'
    return None


@lru_cache(maxsize=1)
def _self_start(pid):
    return process_info(pid)[1]


def local_process():
    pid = os.getpid()
    return pid, socket.gethostname(), _cached_scope(pid), _self_start(pid)


@lru_cache(maxsize=1)
def _cached_scope(pid):
    # A forked worker gets its own identity even if the module was imported before fork.
    return process_scope()
