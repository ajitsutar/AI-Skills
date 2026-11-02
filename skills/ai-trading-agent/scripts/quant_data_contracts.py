"""Small stdlib evidence primitives; hashes bind supplied bytes, not their truth."""
import copy
import hashlib
import json
import math
import re
from datetime import date, datetime
from point_in_time_data import timestamp


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def text(value, name):
    require(isinstance(value, str) and value.strip() == value and bool(value), name)
    return value


def day(value):
    require(isinstance(value, str) and len(value) == 10, 'ISO_SESSION_DATE_REQUIRED')
    require(date.fromisoformat(value).isoformat() == value, 'ISO_SESSION_DATE_REQUIRED')
    return value


def instant(value):
    return datetime.fromisoformat(timestamp(value).replace('Z', '+00:00'))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def pointer(body, path):
    require(isinstance(path, str) and (path == '' or path.startswith('/')), 'JSON_POINTER_REQUIRED')
    value = body
    for raw in path.split('/')[1:]:
        require(re.search(r'~(?![01])', raw) is None, 'INVALID_JSON_POINTER_ESCAPE')
        key = raw.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            require(key.isdigit() and (key == '0' or not key.startswith('0')), 'ARRAY_POINTER_INDEX')
            index = int(key)
            require(index < len(value), 'POINTER_MISSING')
            value = value[index]
        else:
            require(isinstance(value, dict) and key in value, 'POINTER_MISSING')
            value = value[key]
    return copy.deepcopy(value)


def sources(rows):
    require(isinstance(rows, list) and len(rows) <= 10000, 'BOUNDED_SOURCES_REQUIRED')
    result = {}
    for row in rows:
        sid = text(row['id'], 'SOURCE_ID_REQUIRED')
        require(sid not in result, 'DUPLICATE_SOURCE_ID')
        require(row.get('source_role') in {'native_json', 'reviewed_extraction'}, 'EXPLICIT_SOURCE_ROLE')
        text(row['uri'], 'SOURCE_URI_REQUIRED')
        timestamp(row['retrieved_at'])
        require(row['body_sha256'] == digest(row['body']), 'SOURCE_BODY_HASH_MISMATCH')
        result[sid] = row
    return result


def bound_record(row, source_map, fields):
    """Resolve required fields from retained structured-source pointers, never literals."""
    sid = row['source_id']
    require(sid in source_map, 'UNKNOWN_SOURCE')
    bindings = row['bindings']
    require(isinstance(bindings, dict) and set(bindings) == set(fields), 'EXACT_SOURCE_FIELD_BINDINGS')
    return {k: pointer(source_map[sid]['body'], bindings[k]) for k in fields}


def cli(function):
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('input')
    p.add_argument('--output')
    args = p.parse_args()
    from pathlib import Path
    raw = Path(args.input).read_bytes()
    require(len(raw) <= 64 * 1024 * 1024, 'INPUT_TOO_LARGE')
    document = json.loads(raw)
    result = function(document)
    rendered = json.dumps(result, indent=2, allow_nan=False)
    if args.output:
        target = Path(args.output)
        require(not target.exists(), 'OUTPUT_ALREADY_EXISTS')
        target.write_text(rendered, encoding='utf-8')
    else:
        print(rendered)
