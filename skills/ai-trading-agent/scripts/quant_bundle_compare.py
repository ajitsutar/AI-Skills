"""Compare stored and current workbench results by job ID without executing either producer."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path

from quant_bundle_evidence import inspect_bundle


EXACT_FIELDS = {'status', 'decision', 'decisions', 'reason', 'reasons', 'flag', 'flags',
                'id', 'operation', 'reject', 'execution_authorized'}


def bound_bundle(path, expected):
    evidence = inspect_bundle(path, receipt_sha256=expected)
    raw = path.read_bytes()
    if evidence['status'] != 'DIGESTS_MATCH' or hashlib.sha256(raw).hexdigest() != evidence['bundle_file_sha256']:
        raise ValueError(f'Archive digest check failed or bytes changed while reading {path}')
    bundle = json.loads(raw.decode('utf-8-sig'))
    return bundle, evidence


def index_jobs(bundle):
    rows = {}
    for row in bundle['result']['results']:
        job_id = row['id']
        if not isinstance(job_id, str) or not job_id or job_id in rows:
            raise ValueError('A distinct nonempty string ID is required for every result job')
        rows[job_id] = row
    return rows


def child(path, key):
    return path + '/' + str(key).replace('~', '~0').replace('/', '~1')


def within_tolerance(left, right, absolute, relative):
    try:
        return math.isclose(left, right, abs_tol=absolute, rel_tol=relative)
    except OverflowError:
        # JSON integers can be larger than float. Apply the same max-based rule.
        left, right = Fraction(left), Fraction(right)
        return abs(left-right) <= max(Fraction(absolute), Fraction(relative)*max(abs(left), abs(right)))


def number_delta(left, right):
    delta = abs(Fraction(left) - Fraction(right))
    if delta.denominator == 1:
        return delta.numerator
    try:
        return float(delta)
    except OverflowError:
        return str(delta)


def compare_jobs(stored, current, absolute, relative, exact_fields):
    numeric = []
    exact = []
    structural = []
    def walk(path, left, right, discrete=False):
        if type(left) in (int, float) and type(right) in (int, float):
            delta = number_delta(left, right)
            close = within_tolerance(left, right, absolute, relative)
            numeric.append(dict(path=path, stored=left, current=right, absolute_delta=delta,
                                within_tolerance=close))
            if discrete:
                exact.append(dict(path=path, kind='discrete', stored=left, current=right, equal=left == right))
        elif type(left) is not type(right):
            kind = 'discrete' if discrete or type(left) is bool or type(right) is bool else 'type'
            exact.append(dict(path=path, kind=kind, stored=left, current=right, equal=False))
        elif isinstance(left, dict):
            for key in sorted(left.keys() | right.keys()):
                p = child(path, key)
                if key not in left:
                    structural.append(dict(path=p, change='added', current=right[key]))
                elif key not in right:
                    structural.append(dict(path=p, change='removed', stored=left[key]))
                else:
                    walk(p, left[key], right[key], discrete or key in exact_fields)
        elif isinstance(left, list):
            for i in range(max(len(left), len(right))):
                p = child(path, i)
                if i >= len(left):
                    structural.append(dict(path=p, change='added', current=right[i]))
                elif i >= len(right):
                    structural.append(dict(path=p, change='removed', stored=left[i]))
                else:
                    walk(p, left[i], right[i], discrete)
        elif discrete or type(left) is bool or left != right:
            kind = 'discrete' if discrete or type(left) is bool else 'categorical'
            exact.append(dict(path=path, kind=kind, stored=left, current=right, equal=left == right))

    walk('', stored, current)
    # Take the maximum from every shared numeric leaf, before filtering by tolerance.
    largest = max(numeric, key=lambda row: abs(Fraction(row['stored'])-Fraction(row['current'])), default=None)
    return dict(numeric_leaves=len(numeric), maximum_raw_delta=largest,
                nonzero_numeric_differences=[r for r in numeric if r['absolute_delta'] != 0],
                outside_tolerance=sum(not r['within_tolerance'] for r in numeric),
                exact_checks=exact, exact_mismatches=sum(not r['equal'] for r in exact),
                discrete_mismatches=sum(r['kind'] == 'discrete' and not r['equal'] for r in exact),
                structure_changes=structural)


def compare(stored_path, current_path, absolute=1e-8, relative=1e-7,
            stored_sha256=None, current_sha256=None, exact_fields=()):
    if not all(math.isfinite(t) and t >= 0 for t in (absolute, relative)):
        raise ValueError('Tolerances must be finite and nonnegative')
    stored, old_evidence = bound_bundle(stored_path, stored_sha256)
    current, new_evidence = bound_bundle(current_path, current_sha256)
    old_jobs, new_jobs = index_jobs(stored), index_jobs(current)
    fields = EXACT_FIELDS | set(exact_fields)
    rows = {}
    for job_id in old_jobs:
        if job_id in new_jobs:
            rows[job_id] = compare_jobs(old_jobs[job_id], new_jobs[job_id], absolute, relative, fields)
    maxima = [dict(job_id=k, **v['maximum_raw_delta']) for k,v in rows.items() if v['maximum_raw_delta'] is not None]
    largest = max(maxima, key=lambda r: abs(Fraction(r['stored'])-Fraction(r['current'])), default=None)
    metadata = {}
    for name,bundle in [('stored',stored), ('current',current)]:
        metadata[name] = {k:v for k,v in bundle['result'].items() if k != 'results'}
        metadata[name]['recorded_environment'] = bundle.get('environment')
    return {
        'scope': 'Stored outputs compared against the supplied current bundle. Neither producer was executed by this comparison.',
        'stored_artifact': old_evidence, 'current_artifact': new_evidence,
        'same_input': old_evidence['checks']['input']['actual'] == new_evidence['checks']['input']['actual'],
        'same_contract': old_evidence['checks']['contract']['actual'] == new_evidence['checks']['contract']['actual'],
        'absolute_tolerance': absolute, 'relative_tolerance': relative, 'exact_fields': sorted(fields),
        'metadata': metadata, 'stored_job_ids': list(old_jobs), 'current_job_ids': list(new_jobs),
        'removed_jobs': [v for k,v in old_jobs.items() if k not in new_jobs],
        'added_jobs': [v for k,v in new_jobs.items() if k not in old_jobs], 'common_jobs': rows,
        'common_numeric_leaves': sum(r['numeric_leaves'] for r in rows.values()),
        'nonzero_numeric_leaves': sum(len(r['nonzero_numeric_differences']) for r in rows.values()),
        'maximum_raw_delta': largest, 'outside_tolerance': sum(r['outside_tolerance'] for r in rows.values()),
        'exact_mismatches': sum(r['exact_mismatches'] for r in rows.values()),
        'discrete_mismatches': sum(r['discrete_mismatches'] for r in rows.values()),
        'changed_common_job_structures': [k for k,r in rows.items() if r['structure_changes']],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stored', type=Path)
    parser.add_argument('current', type=Path)
    parser.add_argument('--absolute', type=float, default=1e-8)
    parser.add_argument('--relative', type=float, default=1e-7)
    parser.add_argument('--stored-sha256')
    parser.add_argument('--current-sha256')
    parser.add_argument('--exact-field', action='append', default=[], help='Additional discrete field name')
    args = parser.parse_args()
    print(json.dumps(compare(args.stored, args.current, args.absolute, args.relative,
                             args.stored_sha256, args.current_sha256, args.exact_field),
                     indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
