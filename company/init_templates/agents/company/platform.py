"""Small OS adapters: actual identity, private authority files, locks and aliases."""
from contextlib import contextmanager
from functools import lru_cache
import csv
import base64
import os
from pathlib import Path
import re
import shlex
import subprocess
import time

WINDOWS = os.name == 'nt'
_HOOK_UTF8="[Console]::InputEncoding=[Text.UTF8Encoding]::new($false); [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); $OutputEncoding=[Console]::OutputEncoding; "


def user_id():
    if not WINDOWS:
        return os.getuid()
    return _windows_user_id()


@lru_cache(maxsize=1)
def _windows_user_id():
    rows = csv.reader(subprocess.check_output(
        ['whoami', '/user', '/fo', 'csv', '/nh'], text=True, encoding='utf-8', errors='replace').splitlines())
    sid = next((value for row in rows for value in row if re.fullmatch(r'S-1-[0-9-]+', value)), None)
    if not sid:
        raise PermissionError('Windows did not expose the current user SID')
    return sid


def is_link(path):
    path = Path(path)
    if path.is_symlink():
        return True
    if WINDOWS:
        try:
            return bool(path.lstat().st_file_attributes & 0x400)
        except FileNotFoundError:
            return False
    return False


@lru_cache(maxsize=1)
def _windows_api():
    import ctypes as c
    from ctypes import wintypes as w
    adv = c.WinDLL('advapi32', use_last_error=True)
    kernel = c.WinDLL('kernel32', use_last_error=True)
    ptr = c.c_void_p
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [w.LPCWSTR, w.DWORD, c.POINTER(ptr), c.POINTER(w.DWORD)]
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = w.BOOL
    adv.GetSecurityDescriptorDacl.argtypes = [ptr, c.POINTER(w.BOOL), c.POINTER(ptr), c.POINTER(w.BOOL)]
    adv.GetSecurityDescriptorDacl.restype = w.BOOL
    adv.GetSecurityDescriptorOwner.argtypes = [ptr, c.POINTER(ptr), c.POINTER(w.BOOL)]
    adv.GetSecurityDescriptorOwner.restype = w.BOOL
    adv.SetNamedSecurityInfoW.argtypes = [w.LPWSTR, w.DWORD, w.DWORD, ptr, ptr, ptr, ptr]
    adv.SetNamedSecurityInfoW.restype = w.DWORD
    adv.GetNamedSecurityInfoW.argtypes = [w.LPWSTR, w.DWORD, w.DWORD, c.POINTER(ptr), c.POINTER(ptr), c.POINTER(ptr), c.POINTER(ptr), c.POINTER(ptr)]
    adv.GetNamedSecurityInfoW.restype = w.DWORD
    adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [ptr, w.DWORD, w.DWORD, c.POINTER(w.LPWSTR), c.POINTER(w.DWORD)]
    adv.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = w.BOOL
    adv.ConvertSidToStringSidW.argtypes = [ptr, c.POINTER(w.LPWSTR)]
    adv.ConvertSidToStringSidW.restype = w.BOOL
    adv.GetAclInformation.argtypes = [ptr,ptr,w.DWORD,w.DWORD]
    adv.GetAclInformation.restype = w.BOOL
    adv.GetAce.argtypes = [ptr,w.DWORD,c.POINTER(ptr)]
    adv.GetAce.restype = w.BOOL
    kernel.LocalFree.argtypes = [ptr]
    kernel.LocalFree.restype = ptr
    return c, w, adv, kernel


def protect_private(path):
    """Restrict new authority files to this user (and Windows SYSTEM)."""
    path = Path(path)
    if is_link(path):
        raise PermissionError('Private files cannot be links or reparse points')
    if not WINDOWS:
        path.chmod(0o700 if path.is_dir() else 0o600)
        return
    c, w, adv, kernel = _windows_api()
    descriptor = c.c_void_p()
    flags = 'OICI' if path.is_dir() else ''
    sddl = f'O:{user_id()}D:P(A;{flags};FA;;;{user_id()})(A;{flags};FA;;;SY)'
    if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, c.byref(descriptor), None):
        raise c.WinError(c.get_last_error())
    try:
        dacl = c.c_void_p(); owner = c.c_void_p(); present = w.BOOL(); defaulted = w.BOOL()
        if not adv.GetSecurityDescriptorDacl(descriptor, c.byref(present), c.byref(dacl), c.byref(defaulted)) or not present.value or not dacl.value:
            raise PermissionError('Cannot establish a private Windows DACL')
        if not adv.GetSecurityDescriptorOwner(descriptor, c.byref(owner), c.byref(defaulted)):
            raise c.WinError(c.get_last_error())
        error = adv.SetNamedSecurityInfoW(str(path), 1, 1 | 4 | 0x80000000, owner, None, dacl, None)
        if error:
            raise c.WinError(error)
    finally:
        kernel.LocalFree(descriptor)


def is_private(path, *, allow_administrators=False):
    path = Path(path)
    if is_link(path):
        return False
    if not WINDOWS:
        metadata = path.stat()
        return metadata.st_uid == user_id() and not metadata.st_mode & 0o077
    c, w, adv, kernel = _windows_api()
    descriptor = c.c_void_p(); owner = c.c_void_p(); dacl = c.c_void_p()
    error = adv.GetNamedSecurityInfoW(str(path), 1, 1 | 4, c.byref(owner), None, c.byref(dacl), None, c.byref(descriptor))
    if error:
        raise c.WinError(error)
    sid = w.LPWSTR()
    try:
        if not dacl.value or not adv.ConvertSidToStringSidW(owner, c.byref(sid)):
            return False
        if sid.value != user_id():
            return False
        # Inspect binary ACE SIDs. SDDL may abbreviate a local administrator
        # as LA; string aliases are not stable identity comparisons.
        class AclSize(c.Structure):
            _fields_=[('count',w.DWORD),('used',w.DWORD),('free',w.DWORD)]
        info=AclSize()
        if not adv.GetAclInformation(dacl,c.byref(info),c.sizeof(info),2):return False
        allowed={str(user_id()),'S-1-5-18'}
        if allow_administrators:allowed.add('S-1-5-32-544')
        owner_access=False
        for index in range(info.count):
            ace=c.c_void_p();principal=w.LPWSTR()
            if not adv.GetAce(dacl,index,c.byref(ace)):return False
            if c.cast(ace,c.POINTER(c.c_ubyte))[0]!=0:return False
            if not adv.ConvertSidToStringSidW(c.c_void_p(ace.value+8),c.byref(principal)):return False
            try:
                if principal.value not in allowed:return False
                mask=c.cast(ace.value+4,c.POINTER(w.DWORD)).contents.value
                if principal.value==user_id() and mask & 0x1f01ff == 0x1f01ff:owner_access=True
            finally:kernel.LocalFree(c.cast(principal,c.c_void_p))
        return owner_access
    finally:
        if sid: kernel.LocalFree(c.cast(sid, c.c_void_p))
        kernel.LocalFree(descriptor)


def owned_path(path):
    """POSIX filesystem ownership; Windows requires an explicit private ACL."""
    return is_private(path,allow_administrators=True) if WINDOWS else Path(path).stat().st_uid == user_id()


def open_lock(path):
    path = Path(path)
    if is_link(path):
        raise PermissionError('Lock files cannot be links')
    return os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)


def acquire_lock(fd, *, blocking=True):
    if not WINDOWS:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        return
    import msvcrt
    if os.fstat(fd).st_size == 0:
        os.write(fd, b'\0')
    while True:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return
        except OSError as error:
            if error.errno not in {13, 11, 36}:
                raise
            if not blocking:
                raise BlockingIOError('Another process owns this file lock') from error
            time.sleep(.02)


def release_lock(fd):
    if not WINDOWS:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)
    else:
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


@contextmanager
def locked_file(path, *, blocking=True):
    fd = open_lock(path)
    try:
        acquire_lock(fd, blocking=blocking)
        try:
            yield
        finally:
            release_lock(fd)
    finally:
        os.close(fd)


def create_alias(path, target):
    path, target = Path(path), Path(target).resolve()
    if not WINDOWS:
        path.symlink_to(os.path.relpath(target, path.parent), target_is_directory=target.is_dir())
    elif target.is_dir():
        # Directory junctions need no Developer Mode or symlink privilege.
        result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(path), str(target)],
                                capture_output=True, text=True, timeout=15)
        if result.returncode:
            raise OSError('Cannot create the runtime junction on this local volume: ' + result.stderr)
    else:
        os.link(target, path)


def detached_process():
    return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS} if WINDOWS else {'start_new_session': True}


def hook_command(python, script):
    args = [str(python), '-B', str(script)]
    if not WINDOWS:
        return shlex.join(args)
    # An explicit PowerShell process works from cmd, PowerShell and Git Bash.
    # Encode only our exact argv, so Unicode, spaces and shell metacharacters
    # never become a second command. Python receives UTF-8 pipe encoding.
    args = [str(python), '-X', 'utf8', '-B', str(script)]
    body = _HOOK_UTF8 + '& ' + ' '.join("'" + a.replace("'", "''") + "'" for a in args) + '; exit $LASTEXITCODE'
    return 'powershell.exe -NoProfile -NonInteractive -EncodedCommand ' + base64.b64encode(body.encode('utf-16le')).decode('ascii')


def hook_arguments(command):
    prefix = 'powershell.exe -NoProfile -NonInteractive -EncodedCommand '
    if not command.startswith(prefix):
        return shlex.split(command)
    body = base64.b64decode(command[len(prefix):], validate=True).decode('utf-16le')
    args = [a.replace("''", "'") for a in re.findall(r"'((?:[^']|'')*)'", body)]
    expected = _HOOK_UTF8 + '& ' + ' '.join("'" + a.replace("'", "''") + "'" for a in args) + '; exit $LASTEXITCODE'
    if body != expected or len(args) != 5 or args[1:4] != ['-X', 'utf8', '-B']:
        raise ValueError('Not an owned SpielOS hook invocation')
    return args
