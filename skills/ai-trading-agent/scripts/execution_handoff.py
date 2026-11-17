"""Advisory research handoff to the user's native host/broker execution tools.

No skill execution gates, approval tickets, policy activation, runtime database,
transport callback or broker operation. Platform/broker permissions remain theirs.
The API preserves supplied values; CLI output redacts private routing/auth fields.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal, InvalidOperation
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


def recurring_dollar_intent(recurring_request, *, currency=None, companion_context=None):
    """Describe recurring buy amounts without inventing a native broker contract.

    This opt-in constructor is independent of sizing, funding and execution.
    Amounts are original decimal strings or integers, not binary floats. The
    original request and companion context remain intact in the private API.
    Currency is explicit; the word dollar alone does not establish USD.
    """
    if not isinstance(recurring_request, dict) or not isinstance(recurring_request.get('amounts'), dict):
        raise ValueError('recurring_request must contain an amounts object')
    if currency is not None and (not isinstance(currency, str) or not currency.strip()):
        raise ValueError('currency must be an explicit nonempty string or null')
    intents = []
    for symbol, amount in recurring_request['amounts'].items():
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError('amounts keys must be nonempty symbols')
        if isinstance(amount, bool) or not isinstance(amount, (str, int)):
            raise ValueError('amounts must preserve decimal strings or integers; binary floats are not accepted')
        try:
            number = Decimal(amount)
        except InvalidOperation as exc:
            raise ValueError('amounts must be finite nonnegative decimals') from exc
        if not number.is_finite() or number < 0:
            raise ValueError('amounts must be finite nonnegative decimals')
        intents.append({'symbol': symbol, 'side': 'buy', 'requested_dollar_amount': amount,
                        'currency': currency})
    record = {'kind': 'RECURRING_DOLLAR_ECONOMIC_INTENT',
              'schema_basis': {'status': 'UNMAPPED', 'broker_contract_bound': False,
                               'host_capability_verified': False,
                               'reason': 'No native broker contract is bound by this constructor. Economic fields are not broker argument names.'},
              'economic_intents': intents, 'currency_status': 'NOT_SUPPLIED_TO_CONSTRUCTOR' if currency is None else 'SUPPLIED',
              'original_recurring_request': deepcopy(recurring_request),
              'companion_context': deepcopy(companion_context),
              'execution_owner': 'native_host_and_broker', 'skill_execution_gates': [],
              'advisory_only': True, 'skill_submitted_order': False, 'schedule_created': False,
              'local_runtime_required': False, 'external_permissions_changed': False}
    record['summary'] = recurring_dollar_summary(record)
    return record


def recurring_dollar_summary(record):
    """Render the constructor's economic record, without asserting native support."""
    lines = ['UNMAPPED recurring dollar intent; no broker tool or argument schema is bound.',
             'Amounts below are requested economic amounts, not share quantities or executable broker arguments.']
    for intent in record['economic_intents']:
        unit = intent['currency'] if intent['currency'] is not None else 'currency not supplied to this constructor; original request context not verified'
        lines.append(f"- Buy amount {intent['requested_dollar_amount']} ({unit}) for {intent['symbol']}.")
    lines.append('The original request and companion context are retained separately; no submission or schedule was created. '
                 'The host must inspect its actual broker contract before mapping; this artifact neither grants nor refuses execution.')
    return '\n'.join(lines)


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
