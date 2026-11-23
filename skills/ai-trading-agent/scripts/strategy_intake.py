"""Resolve the original response declaration for a local prospective strategy."""
import hashlib
from pathlib import Path
import re

import handoff_report as binding_json
from response_contract import declared_fields
from supplied_research import read as bounded_read, require, safe


def read(path):
    path = Path(path).absolute()
    require(path == safe(path), 'CANONICAL_STRATEGY_INPUT_REQUIRED')
    return bounded_read(path)


def packaged_request(source_root):
    """Recognize only an adjacent manifest that binds both conventional input documents."""
    source = Path(source_root).absolute()
    require(source == safe(source), 'CANONICAL_STRATEGY_SOURCE_REQUIRED')
    for package in (source, source.parent):
        manifest = package / 'HASHES.json'
        prompt = source / 'PROMPT.txt'
        protocol = package / 'PROTOCOL.txt'
        if not all(path.is_file() for path in (manifest, prompt, protocol)):
            continue
        inventory = binding_json.strict_json(read(manifest))
        names = (prompt.relative_to(package).as_posix(), protocol.relative_to(package).as_posix())
        if not isinstance(inventory, dict) or not all(name in inventory for name in names):
            continue
        originals = (read(prompt), read(protocol))
        require(all(hashlib.sha256(raw).hexdigest() == inventory[name]
                    for name, raw in zip(names, originals)), 'ORIGINAL_PROMPT_OR_PROTOCOL_HASH_CHANGED')
        return originals
    return None


def mentions_fields(raw):
    return re.search(rb'\b`?response\.json`?\s+(?:containing|must contain|must include|with required fields)\b',
                     raw, re.IGNORECASE) is not None


def original_contract(prompt, source_root, explicit=None):
    package = packaged_request(source_root)
    candidates = []
    if package is not None:
        require(prompt == package[0], 'ORIGINAL_PACKAGE_REQUEST_CHANGED')
        if mentions_fields(package[1]):
            candidates.append(package[1])
    if mentions_fields(prompt):
        candidates.append(prompt)
    if explicit is not None:
        candidates.append(read(explicit))
    if not candidates:
        return None
    required = declared_fields(candidates[0])
    for declaration in candidates[1:]:
        require(set(declared_fields(declaration)) == set(required), 'CONFLICTING_ORIGINAL_RESPONSE_DECLARATIONS')
    return candidates[0]
