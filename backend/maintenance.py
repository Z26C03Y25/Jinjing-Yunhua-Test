"""Offline evidence backup and safe restore. Run only after stopping writers."""
import argparse
import hashlib
import json
import pathlib
import sqlite3
import tarfile
import tempfile
from contextlib import closing


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def check_database(path):
    with closing(sqlite3.connect('file:' + path.as_posix() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity check failed')
        return {table: db.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                for table in ('tasks', 'events', 'rule_revisions', 'analyst_notes', 'audit')}


def backup(state, output):
    check_database(state / 'events.sqlite')
    files = sorted(p for p in state.rglob('*') if p.is_file())
    if any(p.is_symlink() for p in state.rglob('*')):
        raise ValueError('Symbolic links are not supported')
    manifest = {p.relative_to(state).as_posix(): digest(p) for p in files}
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create prevents accidental overwrite of an existing backup.
    with output.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for path in files:
            archive.add(path, arcname=path.relative_to(state).as_posix(), recursive=False)
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / 'backup-manifest.json'
            path.write_text(json.dumps(manifest), encoding='utf-8')
            archive.add(path, arcname='backup-manifest.json')
    return {'files': len(manifest), 'archive_sha256': digest(output)}


def restore(state, source):
    state.mkdir(parents=True, exist_ok=True)
    if any(state.iterdir()):
        raise ValueError('Restore requires an empty directory; existing evidence is never overwritten')
    with tarfile.open(source, 'r:gz') as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive paths')
        for member in members:
            name = pathlib.PurePosixPath(member.name)
            if not member.isfile() or name.is_absolute() or '..' in name.parts or '\\' in member.name:
                raise ValueError('Unsafe archive entry')
        stream = archive.extractfile('backup-manifest.json')
        manifest = json.load(stream)
        if set(names) != set(manifest) | {'backup-manifest.json'}:
            raise ValueError('Manifest file list mismatch')
        # Never use extractall: write only validated regular files below the target.
        for member in members:
            if member.name == 'backup-manifest.json':
                continue
            target = state / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as reader, target.open('xb') as writer:
                for block in iter(lambda: reader.read(1024 * 1024), b''):
                    writer.write(block)
            if digest(target) != manifest[member.name]:
                raise ValueError('Backup checksum mismatch: ' + member.name)
    return {'verified_files': len(manifest), 'database_counts': check_database(state / 'events.sqlite')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['backup', 'restore'])
    parser.add_argument('--state', type=pathlib.Path, default=pathlib.Path('/state'))
    parser.add_argument('--archive', required=True, type=pathlib.Path)
    args = parser.parse_args()
    result = backup(args.state, args.archive) if args.action == 'backup' else restore(args.state, args.archive)
    print(json.dumps(result))
