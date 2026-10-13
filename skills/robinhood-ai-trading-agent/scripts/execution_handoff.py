"""Advisory research handoff to the user's native host/broker execution tools.

No skill execution gates, approval tickets, policy activation, runtime database,
transport callback or broker operation. Platform/broker permissions remain theirs.
The API preserves supplied values; CLI output redacts private routing/auth fields.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import sys


PRIVATE_FIELDS = {'account', 'accounts', 'account_id', 'account_alias', 'account_number',
                  'account_identifier', 'account_uuid', 'account_ref', 'account_url',
                  'account_uri', 'broker_account_id', 'account_routing', 'broker_order_id',
                  'private_routing', 'authorization', 'authorization_header',
                  'authentication', 'credentials', 'headers', 'cookies', 'set_cookie',
                  'token', 'access_token', 'refresh_token', 'session_token', 'bearer_token',
                  'password', 'secret', 'client_secret', 'api_key', 'x_api_key'}


def _field_name(key):
    """Match common snake/camel/kebab/space spellings without changing payload keys."""
    return ''.join(char for char in key.casefold() if char.isalnum()) if isinstance(key, str) else ''


_PRIVATE_FIELD_NAMES = frozenset(_field_name(key) for key in PRIVATE_FIELDS)


def handoff(payload=None, *, source='execution_handoff'):
    """Return an informational handoff, never execution permission or a refusal.

    Any research state, order basis or missing optional fact is passed through.
    The native host chooses and validates its own available broker operation.
    Risk observations remain observations, not machine-interpreted order gates.
    """
    return {'kind': 'NATIVE_HOST_BROKER_HANDOFF', 'source': source,
            'execution_owner': 'native_host_and_broker', 'skill_execution_gates': [],
            'local_runtime_required': False, 'skill_submitted_order': False,
            'external_permissions_changed': False, 'advisory_only': True,
            'payload': deepcopy({} if payload is None else payload)}


def redact_private(value):
    """Return a display copy with recognized private structured fields removed.

    This is not a free-text secret scanner. The handoff API never calls this
    function: actual host payloads, including routing, remain exact.
    """
    if isinstance(value, dict):
        return {key: '<PRIVATE_HOST_VALUE>' if _field_name(key) in _PRIVATE_FIELD_NAMES else redact_private(child)
                for key, child in value.items()}
    if isinstance(value, list):
        return [redact_private(child) for child in value]
    if isinstance(value, tuple):
        return tuple(redact_private(child) for child in value)
    return value


def cli(source='execution_handoff'):
    parser = argparse.ArgumentParser(description=__doc__)
    # Old callers can keep their operation/runtime arguments during migration.
    # They are descriptive only: no path is opened and no operation is executed.
    parser.add_argument('legacy_arguments', nargs='*')
    args = parser.parse_args()
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    result = handoff(payload, source=source)
    if args.legacy_arguments:
        result['legacy_arguments_not_executed'] = args.legacy_arguments
    print(json.dumps(redact_private(result), indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(cli())
