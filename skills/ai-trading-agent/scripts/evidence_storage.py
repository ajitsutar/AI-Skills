"""Lossless logical artifacts over deterministic gzip objects, without extra dependencies.

The index binds original logical names to raw SHA256/size and stored SHA256/size.
It is not source authentication. All readers verify bytes before returning them.
"""
from __future__ import annotations
from collections.abc import MutableMapping
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import stat

INDEX = 'storage-index.json'
MAX_OBJECT_BYTES = 1024 ** 3
MAX_STORED_BYTES = MAX_OBJECT_BYTES + 1024 * 1024
MAX_INDEX_BYTES = 16 * 1024 * 1024
MAX_RESIDENT_COMPRESSED_BYTES = 256 * 1024 * 1024

def no_redirects(path):
    """Inspect lexical ancestors before resolve; bounded by pathlib's parents."""
    path = Path(path).absolute()
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('ARTIFACT_REDIRECT_REJECTED')
    return path

def safe_path(root, name):
    path = no_redirects(no_redirects(root) / name_check(name))
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('ARTIFACT_PATH_ESCAPE')
    return path

def bounded_read(path, limit, expected_size=None):
    no_redirects(path)
    size = path.stat().st_size
    if size > limit or (expected_size is not None and size != expected_size):
        raise ValueError('STORED_ARTIFACT_SIZE_LIMIT_OR_MISMATCH')
    with path.open('rb') as handle:
        raw = handle.read(size + 1)
    if len(raw) != size or len(raw) > limit:
        raise ValueError('STORED_ARTIFACT_SIZE_LIMIT_OR_CHANGED')
    return raw

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def name_check(name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name or any(
            p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('INVALID_LOGICAL_ARTIFACT_NAME')
    return name

def compress(raw):
    target = io.BytesIO()
    with gzip.GzipFile(fileobj=target, mode='wb', mtime=0, compresslevel=1) as out:
        view = memoryview(raw)
        for offset in range(0, len(view), 1024 * 1024):
            out.write(view[offset:offset + 1024 * 1024])
    return target.getvalue()

def unpack(raw, expected_size):
    if type(expected_size) is not int or not 0 <= expected_size <= MAX_OBJECT_BYTES:
        raise ValueError('ARTIFACT_SIZE_LIMIT')
    result = bytearray()
    with gzip.GzipFile(fileobj=io.BytesIO(raw), mode='rb') as handle:
        while True:
            chunk = handle.read(min(1024 * 1024, expected_size + 1 - len(result)))
            if not chunk:
                break
            result.extend(chunk)
            if len(result) > expected_size:
                raise ValueError('ARTIFACT_SIZE_MISMATCH')
    if len(result) != expected_size:
        raise ValueError('ARTIFACT_SIZE_MISMATCH')
    return bytes(result)

class CompressedArtifacts(MutableMapping):
    """Keep completed artifact buffers compressed; identical raw bytes stored once."""
    def __init__(self, initial=(), writer=None):
        self.names, self.objects, self.writer = {}, {}, writer
        self.update(initial)
    def __getitem__(self, key):
        digest, size = self.names[key]
        return unpack(self.objects[digest], size)
    def __setitem__(self, key, raw):
        name_check(key)
        if len(raw) > MAX_OBJECT_BYTES:
            raise ValueError('ARTIFACT_SIZE_LIMIT')
        digest = sha(raw)
        if digest not in self.objects:
            packed = compress(raw)
            if sum(map(len, self.objects.values())) + len(packed) > MAX_RESIDENT_COMPRESSED_BYTES:
                raise ValueError('COMPRESSED_ARTIFACT_MEMORY_LIMIT')
            self.objects[digest] = packed
        self.names[key] = (digest, len(raw))
        if self.writer:
            self.writer(key, raw)
    def __delitem__(self, key):
        del self.names[key]
    def __iter__(self):
        return iter(self.names)
    def __len__(self):
        return len(self.names)

class ArtifactStore:
    """New private-root store. No unrelated paths, overwrites or deletion."""
    def __init__(self, root, create=False):
        self.root = no_redirects(root).resolve()
        if create:
            self.root.mkdir(exist_ok=False)
            (self.root / 'objects').mkdir()
            self.index = {'schema_version':1, 'storage':'sha256-gzip-v1', 'artifacts':{}}
            self._save()
        else:
            self.index = json.loads(bounded_read(safe_path(self.root, INDEX), MAX_INDEX_BYTES))
            if self.index.get('schema_version') != 1 or self.index.get('storage') != 'sha256-gzip-v1':
                raise ValueError('ARTIFACT_STORAGE_SCHEMA')
            for name in self.index['artifacts']:
                name_check(name)
    def _save(self):
        temporary = safe_path(self.root, INDEX + '.tmp')
        encoded = (json.dumps(self.index, sort_keys=True, separators=(',', ':'))+'\n').encode('utf-8')
        if len(encoded) > MAX_INDEX_BYTES:
            raise ValueError('ARTIFACT_INDEX_SIZE_LIMIT')
        temporary.write_bytes(encoded)
        temporary.replace(safe_path(self.root, INDEX))
    def write(self, name, raw):
        name_check(name)
        if name in self.index['artifacts']:
            raise ValueError('ARTIFACT_ALREADY_WRITTEN')
        if len(raw) > MAX_OBJECT_BYTES:
            raise ValueError('ARTIFACT_SIZE_LIMIT')
        digest = sha(raw)
        packed = compress(raw)
        object_name = 'objects/' + digest + '.gz'
        path = safe_path(self.root, object_name)
        if path.exists():
            if sha(bounded_read(path, MAX_STORED_BYTES, len(packed))) != sha(packed):
                raise ValueError('EXISTING_OBJECT_MISMATCH')
        else:
            with path.open('xb') as out:
                out.write(packed)
        self.index['artifacts'][name] = {'object':object_name, 'sha256':digest,
            'bytes':len(raw), 'stored_sha256':sha(packed), 'stored_bytes':len(packed)}
        self._save()
    def read(self, name):
        row = self.index['artifacts'][name_check(name)]
        digest = row['sha256']
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest) or row['object'] != 'objects/' + digest + '.gz':
            raise ValueError('INVALID_OBJECT_IDENTITY')
        path = safe_path(self.root, row['object'])
        if type(row['stored_bytes']) is not int or not 0 <= row['stored_bytes'] <= MAX_STORED_BYTES:
            raise ValueError('STORED_ARTIFACT_SIZE_LIMIT_OR_MISMATCH')
        packed = bounded_read(path, MAX_STORED_BYTES, row['stored_bytes'])
        if len(packed) != row['stored_bytes'] or sha(packed) != row['stored_sha256']:
            raise ValueError('COMPRESSED_ARTIFACT_HASH_MISMATCH')
        raw = unpack(packed, row['bytes'])
        if sha(raw) != digest:
            raise ValueError('ARTIFACT_HASH_MISMATCH')
        return raw
    def exists(self, name):
        return name_check(name) in self.index['artifacts']

class Reader:
    """One verified logical reader for legacy or compressed artifacts."""
    def __init__(self, root, store=None, prefix=''):
        self.root = no_redirects(root).resolve()
        self.store = store or (ArtifactStore(self.root) if (self.root / INDEX).is_file() else None)
        self.prefix = prefix
    def read(self, name):
        name_check(name)
        if self.store:
            return self.store.read(self.prefix + name)
        path = safe_path(self.root, name)
        return bounded_read(path, MAX_OBJECT_BYTES)
    def exists(self, name):
        name_check(name)
        return self.store.exists(self.prefix + name) if self.store else safe_path(self.root, name).is_file()

def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('list','extract'))
    parser.add_argument('directory')
    parser.add_argument('artifact', nargs='?')
    parser.add_argument('--private-output')
    args=parser.parse_args()
    try:
        store=ArtifactStore(args.directory)
        if args.command=='list':
            if args.artifact or args.private_output:
                raise ValueError('LIST_OPTIONS')
            print(json.dumps(store.index,sort_keys=True,indent=2))
        else:
            if not args.artifact or not args.private_output:
                raise ValueError('ARTIFACT_AND_OUTPUT_REQUIRED')
            output=no_redirects(args.private_output)
            if output.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
                raise ValueError('PRIVATE_OUTPUT_OUTSIDE_SKILL_REQUIRED')
            raw=store.read(args.artifact)
            with output.open('xb') as handle:
                handle.write(raw)
            print('EXACT_ARTIFACT_EXTRACTED')
    except (ValueError, KeyError, TypeError, OSError, EOFError):
        parser.exit(2,'Invalid artifact store or output; no source values printed.\n')

if __name__=='__main__':
    main()
