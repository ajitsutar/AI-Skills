"""Shared validation for offline quant calculations; no broker or network access."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from price_audit import timestamp


def require(condition, message):
    if not condition:
        raise ValueError(message)


def scalar(value, name='number', minimum=None, maximum=None):
    require(type(value) in (int, float), 'NUMERIC_REQUIRED:' + name)
    value = float(value)
    require(np.isfinite(value), 'FINITE_REQUIRED:' + name)
    require(minimum is None or value >= minimum, 'BELOW_MINIMUM:' + name)
    require(maximum is None or value <= maximum, 'ABOVE_MAXIMUM:' + name)
    return value


def integer(value, name, minimum=0, maximum=None):
    require(type(value) is int, 'INTEGER_REQUIRED:' + name)
    scalar(value, name, minimum, maximum)
    return value


def vector(values, name, length=None, minimum=None):
    require(isinstance(values, list) and len(values) > 0, 'NONEMPTY_ARRAY:' + name)
    out = np.array([scalar(v, name, minimum) for v in values], dtype=float)
    require(length is None or len(out) == length, 'LENGTH_MISMATCH:' + name)
    return out


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def series(rows, field='return', minimum=3):
    require(isinstance(rows, list) and len(rows) >= minimum, 'INSUFFICIENT_OBSERVATIONS')
    dates = [timestamp(r['timestamp']) for r in rows]
    require(dates == sorted(set(dates)), 'UNIQUE_INCREASING_TIMESTAMPS_REQUIRED')
    values = vector([r[field] for r in rows], field)
    return dates, values


def covariance(value, n):
    require(isinstance(value, list) and len(value) == n, 'COVARIANCE_DIMENSIONS')
    matrix = np.array([vector(row, 'covariance', n) for row in value])
    require(np.allclose(matrix, matrix.T, atol=1e-12, rtol=0), 'COVARIANCE_NOT_SYMMETRIC')
    require(np.linalg.eigvalsh(matrix).min() >= -1e-12, 'COVARIANCE_NOT_PSD')
    return matrix


def cli(operations):
    parser = argparse.ArgumentParser(description='Offline quant calculation from retained JSON')
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    document = json.loads(args.input.read_text(encoding='utf-8-sig'))
    operation = document['operation']
    require(operation in operations, 'UNKNOWN_OPERATION')
    result = operations[operation](**document['inputs'])
    result.update(input_sha256=digest(document), execution_authorized=False,
                  implementation_sha256=hashlib.sha256(Path(__import__('__main__').__file__).read_bytes().replace(b'\r\n', b'\n')).hexdigest())
    print(json.dumps(result, indent=2, allow_nan=False))

