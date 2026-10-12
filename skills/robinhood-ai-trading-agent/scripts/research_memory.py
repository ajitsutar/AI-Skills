"""Local research inventory and refresh planner; no network, trades or auto-refresh.

Sealing verifies bytes, not factual accuracy or investment eligibility. Keep the
inventory and its files outside the skill installation and public repository.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

KINDS = {'filing', 'review', 'prices', 'estimates', 'events', 'universe',
         'snapshot', 'result', 'code', 'mandate'}


def instant(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def local_file(root, relative):
    # Reject cross-platform path ambiguities as well as symlink escapes.
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        raise ValueError('Portable relative file path required')
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Path escapes archive')
    base = Path(root).resolve()
    target = (base / path).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise ValueError('Missing file or path escapes archive: ' + relative)
    return target


def file_hash(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
    return sha.hexdigest()


def seal(root, catalog):
    for key in ('run_id', 'as_of', 'hold', 'universe'):
        if not isinstance(catalog.get(key), str) or not catalog[key].strip():
            raise ValueError('Required catalog field: ' + key)
    when = instant(catalog['as_of'])
    entries = catalog.get('artifacts')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Artifacts required')
    records, seen = [], set()
    for item in entries:
        relative = item['path']
        if relative.casefold() in seen or item['kind'] not in KINDS:
            raise ValueError('Duplicate artifact or unknown kind')
        seen.add(relative.casefold())
        if instant(item['as_of']) > when:
            raise ValueError('Artifact is later than archive as_of')
        path = local_file(root, relative)
        records.append({**item, 'sha256': file_hash(path), 'bytes': path.stat().st_size})
    document = {k: catalog[k] for k in ('run_id', 'as_of', 'hold', 'universe')}
    document.update(schema_version=1, artifacts=records, execution_authorized=False)
    return {**document, 'manifest_sha256': digest(document)}


def verify(root, manifest):
    document = {k: v for k, v in manifest.items() if k != 'manifest_sha256'}
    if manifest.get('schema_version') != 1 or digest(document) != manifest.get('manifest_sha256'):
        raise ValueError('Manifest integrity mismatch')
    rebuilt = seal(root, manifest)
    if rebuilt != manifest:
        raise ValueError('Archived bytes changed')
    return {'status': 'ARCHIVE_BYTES_MATCH', 'files': len(manifest['artifacts']),
            'manifest_sha256': manifest['manifest_sha256'], 'execution_authorized': False}


def refresh_plan(root, manifest, as_of, hold, universe):
    verify(root, manifest)
    if instant(as_of) < instant(manifest['as_of']):
        raise ValueError('Historical point-in-time reconstruction is not a refresh')
    if not hold.strip() or not universe.strip():
        raise ValueError('Current hold and universe required')
    actions = {
        'filing': ('RECHECK_SOURCE_THEN_REUSE', 'Check issuer/SEC index for newer filings, amendments and restatements. Reuse verified unchanged facts with original source and period.'),
        'review': ('REVALIDATE', 'Reuse notes as prior research; check new disclosures, news, earnings normalization, events and the current mandate before any eligibility judgment.'),
        'prices': ('REFRESH', 'Fetch through the new cutoff for the entire universe; audit actions and revised adjusted history before merging.'),
        'estimates': ('REFRESH', 'Refresh estimates, revisions and fiscal-period mapping; old snapshots remain historical observations.'),
        'events': ('REFRESH', 'Recheck issuer and macro calendars across the new entry-to-exit interval.'),
        'universe': ('REFRESH', 'Reacquire membership and issuer mappings, including new listings, delistings and class changes.'),
        'snapshot': ('REBUILD', 'New snapshot needs a new contract and acquisition receipts; failed components remain gaps. Do not relabel cached data as newly fetched.'),
        'result': ('RECOMPUTE', 'Rerank the whole eligible universe with current inputs and peer groups, then review in queue order. Old results are replay-only.'),
        'code': ('PIN_OR_MIGRATE', 'Replay old results with saved code. A newer scorer/profile needs an explicit new version and full reranking.'),
        'mandate': ('RECONFIRM_FROM_REQUEST', 'Apply the current request, horizon and capital; do not silently inherit old personal preferences.')}
    return {'schema_version': 1, 'status': 'REFRESH_PLAN_ONLY',
            'parent_manifest_sha256': manifest['manifest_sha256'], 'as_of': as_of,
            'hold': hold, 'universe': universe,
            'context_changed': hold != manifest['hold'] or universe != manifest['universe'],
            'artifacts': [{**item, 'action': actions[item['kind']][0],
                           'reason': actions[item['kind']][1]} for item in manifest['artifacts']],
            'automatic_download_performed': False, 'execution_authorized': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('seal', 'verify', 'plan'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--as-of')
    parser.add_argument('--hold')
    parser.add_argument('--universe')
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding='utf-8-sig'))
    if args.operation == 'seal':
        result = seal(args.root, data)
    elif args.operation == 'verify':
        result = verify(args.root, data)
    else:
        if not all((args.as_of, args.hold, args.universe)):
            parser.error('plan requires --as-of, --hold and --universe')
        result = refresh_plan(args.root, data, args.as_of, args.hold, args.universe)
    encoded = json.dumps(result, indent=2, allow_nan=False)
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(encoded + '\n')
        print(json.dumps({'saved': str(args.output), 'status': result.get('status', 'SEALED')}))
    else:
        print(encoded)


if __name__ == '__main__':
    main()
