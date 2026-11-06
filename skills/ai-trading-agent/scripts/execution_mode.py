"""Describe a requested decision mode without activation, transport or scheduling.

The API preserves a private mandate. CLI display uses structured-field redaction;
neither is a secret scanner, authorization validator or broker capability probe.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
import sys

from execution_handoff import redact_private


MODES = {
    'autonomous': 'PROMPT_DEFINED_RULES_AND_DELEGATED_DISCRETION',
}
CONTEXT_FIELDS = ('objective', 'accounts', 'instruments', 'actions', 'duration',
                  'limits', 'important_events', 'holding_period',
                  'review_schedule', 'notifications')


def _check_json(value):
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ValueError('Mandate object keys must be strings.')
        for child in value.values():
            _check_json(child)
    elif type(value) is list:
        for child in value:
            _check_json(child)
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError('Mandate numbers must be finite.')
    elif value is not None and type(value) not in (str, int, bool):
        raise ValueError('Mandate must contain JSON values only.')


def describe_mode(mode, mandate=None):
    """Return an informational mode plan, not a permission or risk decision.

Unspecified context refers only to this object. Existing conversation instructions
still apply. Field presence establishes neither completeness nor authenticity.
No mandate is activated, no clock consulted, and no trading limits are inferred.
"""
    if type(mode) is not str or mode not in MODES:
        raise ValueError('Choose autonomous explicitly.')
    if mandate is None:
        mandate = {}
    if type(mandate) is not dict:
        raise ValueError('Mandate must be a JSON object.')
    _check_json(mandate)
    missing = [key for key in CONTEXT_FIELDS
               if key not in mandate or mandate[key] is None
               or mandate[key] == '' or mandate[key] == [] or mandate[key] == {}]
    return {
        'kind': 'EXECUTION_MODE_PLAN', 'mode': mode,
        'result_scope': 'OFFLINE_DESCRIPTION_NOT_HOST_EXECUTION_RESULT',
        'selection_scope': MODES[mode], 'mandate': deepcopy(mandate),
        'rule_source': 'USER_PROMPTS_AND_EXISTING_INSTRUCTIONS',
        'configuration_file_required': False,
        'host_workflow': {
            'in_scope_action': 'USE_NATIVE_BROKER_TOOLS_WHEN_AUTHORIZED_AND_HOST_PERMITTED',
            'per_order_reconfirmation': 'NO_ADDITIONAL_SKILL_APPROVAL_FOR_EXISTING_AUTHORITY',
            'external_requirements': 'HOST_PLATFORM_AND_BROKER_REQUIREMENTS_STILL_APPLY',
            'unknown_prior_outcome': 'HOST_RECONCILIATION_BEFORE_ANY_RETRY',
        },
        'unspecified_context': missing,
        'context_assessment': 'FIELD_PRESENCE_ONLY_NOT_AUTHORITY_OR_COMPLETENESS',
        'activation_performed': False, 'skill_submitted_order': False,
        'external_permissions_changed': False, 'advisory_only': True,
        'host_readiness': 'NOT_ASSESSED', 'scheduling_status': 'NOT_CONFIGURED',
        'skill_execution_gates': [],
    }


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field.')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('Nonfinite JSON value.')


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=tuple(MODES))
    args = parser.parse_args()
    try:
        raw = sys.stdin.read()
        mandate = json.loads(raw, object_pairs_hook=_unique_object,
                             parse_constant=_invalid_constant) if raw.strip() else {}
        # JSON null is not an object; None is an API-only convenience default.
        if type(mandate) is not dict:
            raise ValueError('Expected an object.')
        result = describe_mode(args.mode, mandate)
    except (ValueError, TypeError, RecursionError):
        parser.error('Expected a finite JSON mandate object with unique string keys.')
    print(json.dumps(redact_private(result), indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(cli())
