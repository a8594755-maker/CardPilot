"""Resumable, copy-only research backup; verify every copied byte with SHA-256."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import time
import traceback

SOURCE = Path(r'\\?\C:\Users\a8594\CardPilot\research')
ROOT = Path(r'\\?\D:\Computer_Backup_2026-09-16')
DEST = ROOT / 'Projects/CardPilot/research'
META = ROOT / 'Verification/research'
CHUNK = 8 * 1024 * 1024
EXCLUDED_DIRS = set()


def main():
    label = ctypes.create_unicode_buffer(261)
    if not ctypes.windll.kernel32.GetVolumeInformationW('D:\\', label, 261, None, None, None, None, 0):
        raise RuntimeError('D volume unavailable')
    if label.value != 'Computer_Backup':
        raise RuntimeError('Unexpected D volume label')
    marker = json.loads((ROOT / 'Verification/format_complete.json').read_text(encoding='utf-8-sig'))
    if marker['serial'] != 'NA9Y543N':
        raise RuntimeError('Unexpected backup disk marker')
    META.mkdir(parents=True, exist_ok=True)
    lock = open(META / 'runner.lock', 'a+b')
    import msvcrt
    lock.seek(0)
    lock.write(b'0')
    lock.flush()
    lock.seek(0)
    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    db = sqlite3.connect(META / 'manifest.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, size INTEGER, mtime_ns INTEGER, sha256 TEXT)')
    progress = dict(pid=os.getpid(), source=str(SOURCE), destination=str(DEST),
                    state='inventory', started_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                    total_files=0, total_bytes=0, verified_files=0, verified_bytes=0,
                    errors=0, current_file='')
    last_update = 0.0
    error_log = open(META / 'errors.jsonl', 'a', encoding='utf-8')

    def update(force=False):
        nonlocal last_update
        if force or time.monotonic() - last_update > 5:
            progress['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
            temporary = META / 'progress.tmp'
            temporary.write_text(json.dumps(progress, indent=2), encoding='utf-8')
            os.replace(temporary, META / 'progress.json')
            last_update = time.monotonic()

    def error(path, exc):
        progress['errors'] += 1
        error_log.write(json.dumps(dict(path=str(path), error=str(exc)), ensure_ascii=False) + '\n')
        error_log.flush()

    def hash_file(path):
        digest = hashlib.sha256()
        with open(path, 'rb') as f:
            while block := f.read(CHUNK):
                digest.update(block)
                update()
        return digest.hexdigest()

    inventory = []
    update(True)
    for directory, dirs, names in os.walk(SOURCE, followlinks=False, onerror=lambda exc: error(exc.filename, exc)):
        for name in list(dirs):
            if name in EXCLUDED_DIRS:
                dirs.remove(name)
                continue
            child = Path(directory) / name
            if child.is_symlink() or child.is_junction():
                dirs.remove(name)
                error(child, 'Directory link excluded; requires separate review')
        for name in names:
            path = Path(directory) / name
            try:
                s = path.lstat()
                if not stat.S_ISREG(s.st_mode) or path.is_symlink():
                    raise RuntimeError('Non-regular file requires separate review')
                inventory.append((path, s.st_size))
                progress['total_files'] += 1
                progress['total_bytes'] += s.st_size
            except OSError as exc:
                error(path, exc)
        update()
    (META / 'scope.json').write_text(json.dumps(dict(source=str(SOURCE), destination=str(DEST),
        total_files=progress['total_files'], total_bytes=progress['total_bytes'],
        scope='Only research, including all checkpoints and raw evidence; no source deletions.'), indent=2), encoding='utf-8')
    already = db.execute('SELECT coalesce(sum(size),0) FROM files').fetchone()[0]
    if shutil.disk_usage(ROOT).free < progress['total_bytes'] - already + 5 * 1024**3:
        raise RuntimeError('Insufficient destination free space')
    # Preserve current run first, then smaller records, then large historical files.
    inventory.sort(key=lambda item: ('v6-fromzero-10m-20260908' not in str(item[0]), item[1]))
    progress['state'] = 'copying_and_verifying'
    update(True)
    for src, _ in inventory:
        relative = src.relative_to(SOURCE)
        key = relative.as_posix()
        dest = DEST / relative
        progress['current_file'] = key
        try:
            before = src.stat()
            row = db.execute('SELECT size,mtime_ns,sha256 FROM files WHERE path=?', (key,)).fetchone()
            digest = None
            if row and row[:2] == (before.st_size, before.st_mtime_ns) and dest.is_file() and dest.stat().st_size == before.st_size:
                if hash_file(dest) == row[2]:
                    digest = row[2]
            if digest is None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                partial = dest.with_name(dest.name + '.backup-partial')
                h = hashlib.sha256()
                with open(src, 'rb') as reader, open(partial, 'wb') as writer:
                    while block := reader.read(CHUNK):
                        writer.write(block)
                        h.update(block)
                        update()
                    writer.flush()
                    os.fsync(writer.fileno())
                after = src.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise RuntimeError('Source changed during copy; retry required')
                digest = h.hexdigest()
                if hash_file(partial) != digest:
                    raise RuntimeError('Destination SHA-256 mismatch')
                os.replace(partial, dest)
                shutil.copystat(src, dest)
                db.execute('INSERT OR REPLACE INTO files VALUES (?,?,?,?)',
                           (key, before.st_size, before.st_mtime_ns, digest))
                db.commit()
            progress['verified_files'] += 1
            progress['verified_bytes'] += before.st_size
        except Exception as exc:
            error(src, exc)
        update()
    progress['state'] = 'completed' if not progress['errors'] else 'completed_with_errors'
    progress['current_file'] = ''
    update(True)
    with open(META / 'sha256.jsonl', 'w', encoding='utf-8') as f:
        for path, size, mtime, digest in db.execute('SELECT * FROM files ORDER BY path'):
            f.write(json.dumps(dict(path=path, size=size, mtime_ns=mtime, sha256=digest), ensure_ascii=False) + '\n')
    db.close()
    error_log.close()
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
