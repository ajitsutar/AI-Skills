"""Initialize, read or update one task's selected execution-policy mode.

Policy persistence only: no broker transport, credentials, scheduling or orders.
Other supplied policy fields are retained without interpretation or modification.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import uuid

from execution_handoff import redact_private

SUPPORTED_MODES = ('paper', 'approval', 'autonomous')
MAX_POLICY_BYTES = 4 * 1024 * 1024


def validate_json(value, _ancestors=None):
    """Accept finite JSON data with string keys; reject cyclic Python objects."""
    ancestors = set() if _ancestors is None else _ancestors
    if type(value) in (dict, list):
        identity = id(value)
        if identity in ancestors:
            raise ValueError('Cyclic data is not JSON.')
        ancestors.add(identity)
        try:
            if type(value) is dict:
                if any(type(key) is not str for key in value):
                    raise ValueError('JSON object keys must be strings.')
                children = value.values()
            else:
                children = value
            for child in children:
                validate_json(child, ancestors)
        finally:
            ancestors.remove(identity)
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError('JSON numbers must be finite.')
    elif value is not None and type(value) not in (str, int, bool):
        raise ValueError('Expected JSON values.')


def validate_policy_mode(policy):
    """Validate mode only; unrelated research fields are not execution gates."""
    if type(policy) is not dict:
        raise ValueError('Execution policy must be a JSON object.')
    try:
        validate_json(policy)
    except RecursionError:
        raise ValueError('Policy nesting is too deep.') from None
    mode = policy.get('mode')
    if type(mode) is not str or mode not in SUPPORTED_MODES:
        raise ValueError('Execution policy requires a supported mode.')
    return mode


def _validate_task_id(task_id):
    if (type(task_id) is not str or not task_id or task_id != task_id.strip()
            or any(ord(char) < 32 for char in task_id)):
        raise ValueError('A stable nonempty task identifier is required.')
    return task_id


def validate_task_policy(policy, task_id):
    """Bind execution behavior to the actual task; never infer a global policy."""
    _validate_task_id(task_id)
    mode = validate_policy_mode(policy)
    if type(policy.get('task_id')) is not str or policy['task_id'] != task_id:
        raise ValueError('Selected policy does not belong to the current task.')
    return mode


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field.')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('Nonfinite JSON value.')


def parse_json(text):
    try:
        value = json.loads(text, object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant)
        validate_json(value)
        return value
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ValueError('Expected finite JSON with unique string keys.') from None


def _path(path):
    try:
        selected = Path(path).absolute()
        for item in (selected, *selected.parents):
            if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
                raise ValueError('Linked policy paths are not supported.')
        if not selected.parent.is_dir():
            raise ValueError('Policy parent directory must exist.')
        return selected
    except (OSError, TypeError):
        raise ValueError('Policy path is unavailable.') from None


def _read_bytes(path):
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_POLICY_BYTES + 1)
        if len(raw) > MAX_POLICY_BYTES:
            raise ValueError('Policy file exceeds the supported size.')
        return raw
    except OSError:
        raise ValueError('Policy file is unavailable.') from None


def _decode_policy(raw):
    try:
        policy = parse_json(raw.decode('utf-8-sig'))
    except UnicodeError:
        raise ValueError('Policy must be UTF-8 JSON.') from None
    validate_policy_mode(policy)
    return policy


def read_policy(path, task_id):
    """Read the selected task-bound file without a fallback or mode default."""
    _validate_task_id(task_id)
    policy = _decode_policy(_read_bytes(_path(path)))
    validate_task_policy(policy, task_id)
    return policy


def _flags():
    return {'skill_submitted_order': False, 'external_permissions_changed': False,
            'scheduling_status': 'NOT_CONFIGURED'}


def _write_private(path, raw):
    # Restrictive creation mode where the filesystem supports POSIX modes.
    # Windows applies its normal inherited ACLs; this does not change ACLs.
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def _persist_policy(path, mode, task_id, create, initializing):
    """Persist a task policy while backing up exact previous bytes on change.

The adjacent exclusive lock coordinates this helper's writers. Immediately before
replacement the original bytes are checked again; unrelated editors do not honor
that lock, so it is not a cross-process compare-and-swap guarantee.
"""
    validate_policy_mode({'mode': mode})
    _validate_task_id(task_id)
    if type(create) is not bool:
        raise ValueError('Create must be Boolean.')
    selected = _path(path)
    lock = selected.with_name('.' + selected.name + '.update.lock')
    _path(lock)
    lock_fd = None
    stage = None
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        selected = _path(selected)
        exists = selected.exists()
        if exists and not selected.is_file():
            raise ValueError('Policy path must be a regular file.')
        if not exists and not create:
            raise ValueError('Creating a policy requires an explicit create request.')
        previous = _read_bytes(selected) if exists else None
        policy = (_decode_policy(previous) if exists else
                  {'schema_version': 1, 'task_id': task_id, 'mode': mode})
        validate_task_policy(policy, task_id)
        previous_mode = policy['mode'] if exists else None
        selected_mode = policy['mode'] if initializing and exists else mode
        receipt = {'kind': 'EXECUTION_POLICY_INITIALIZATION' if initializing else 'EXECUTION_POLICY_UPDATE',
                   'mode': selected_mode, 'task_id': task_id, 'policy_scope': 'TASK',
                   'previous_mode': previous_mode, 'policy_source': 'FILE',
                   'policy_path': str(selected), 'created': not exists,
                   'backup_path': None, **_flags()}
        if exists and (initializing or previous_mode == selected_mode):
            return {**receipt, 'policy_updated': False,
                    'policy_sha256': hashlib.sha256(previous).hexdigest()}
        updated = deepcopy(policy)
        updated['mode'] = selected_mode
        raw = (json.dumps(updated, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
        if len(raw) > MAX_POLICY_BYTES:
            raise ValueError('Policy file exceeds the supported size.')
        stamp = uuid.uuid4().hex
        stage = selected.with_name('.' + selected.name + '.staged-' + stamp)
        _path(stage)
        _write_private(stage, raw)
        if exists:
            backup = selected.with_name(selected.name + '.backup-' + stamp)
            _path(backup)
            _write_private(backup, previous)
            receipt['backup_path'] = str(backup)
            _path(selected)
            if _read_bytes(selected) != previous:
                raise ValueError('Policy changed concurrently; update not applied.')
            os.replace(stage, selected)
            stage = None
        else:
            # A link creates atomically without replacing an unrelated file that
            # appeared after the missing-file check. It exposes completed bytes.
            _path(selected)
            os.link(stage, selected)
        final = _read_bytes(selected)
        if final != raw:
            raise ValueError('Policy changed during verification; inspect current file.')
        return {**receipt, 'policy_updated': True,
                'policy_sha256': hashlib.sha256(raw).hexdigest()}
    except OSError:
        raise ValueError('Policy update unavailable or another update is in progress.') from None
    finally:
        if stage is not None:
            try:
                stage.unlink()
            except FileNotFoundError:
                pass
        if lock_fd is not None:
            os.close(lock_fd)
            lock.unlink()


def initialize_task_policy(path, task_id):
    """Create a new task policy in paper mode; preserve an existing matching one.

This is normal new-task initialization, not a mode reset or implicit migration.
Existing malformed or mismatched task policies remain errors and are unchanged.
"""
    return _persist_policy(path, 'paper', task_id, create=True, initializing=True)


def set_policy_mode(path, mode, task_id, create=False):
    """Apply an explicit mode change only to the identified task's policy."""
    return _persist_policy(path, mode, task_id, create=create, initializing=False)


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    initialize = commands.add_parser('init')
    initialize.add_argument('path')
    initialize.add_argument('--task-id', required=True)
    show = commands.add_parser('show')
    show.add_argument('path')
    show.add_argument('--task-id', required=True)
    update = commands.add_parser('set')
    update.add_argument('path')
    update.add_argument('--task-id', required=True)
    update.add_argument('--mode', choices=SUPPORTED_MODES, required=True)
    update.add_argument('--create', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'show':
            policy = read_policy(args.path, args.task_id)
            result = {'kind': 'EXECUTION_POLICY', 'mode': policy['mode'],
                      'task_id': args.task_id, 'policy_scope': 'TASK',
                      'policy_source': 'FILE', 'policy_path': str(_path(args.path)),
                      'policy': policy, **_flags()}
        elif args.command == 'init':
            result = initialize_task_policy(args.path, args.task_id)
        else:
            result = set_policy_mode(args.path, args.mode, args.task_id, create=args.create)
    except (ValueError, OSError, TypeError, RecursionError):
        parser.error('Policy operation could not complete; check the task, selected file, mode and concurrent updates.')
    print(json.dumps(redact_private(result), indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(cli())
