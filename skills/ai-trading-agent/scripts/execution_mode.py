"""Describe the mode from the current task's execution policy without orders.

Prompts supply rule context; they never select or override the policy mode.
The local result describes host instructions, not verified host readiness.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import sys

from execution_handoff import redact_private
from execution_policy import parse_json, read_policy, validate_json, validate_task_policy

BEHAVIORS = {
    'paper': 'SIMULATION_ONLY',
    'approval': 'REQUIRES_ORDER_APPROVAL',
    'autonomous': 'STANDING_AUTHORITY_WITHIN_SCOPE',
}
CONTEXT_FIELDS = ('objective', 'accounts', 'instruments', 'actions', 'duration',
                  'limits', 'important_events', 'holding_period',
                  'review_schedule', 'notifications')


def describe_mode(policy, mandate=None, *, task_id):
    """Describe policy-selected behavior and preserve prompt context as data.

Field presence establishes neither completeness nor authenticity. This helper
does not enforce the workflow, approve an order or assess host capabilities.
"""
    mode = validate_task_policy(policy, task_id)
    if mandate is None:
        mandate = {}
    if type(mandate) is not dict:
        raise ValueError('Mandate must be a JSON object.')
    try:
        validate_json(mandate)
    except RecursionError:
        raise ValueError('Mandate nesting is too deep.') from None
    missing = [key for key in CONTEXT_FIELDS
               if key not in mandate or mandate[key] is None
               or mandate[key] == '' or mandate[key] == [] or mandate[key] == {}]
    return {
        'kind': 'EXECUTION_MODE_PLAN', 'mode': mode, 'mode_source': 'POLICY',
        'task_id': task_id, 'policy_scope': 'TASK',
        'result_scope': 'OFFLINE_DESCRIPTION_NOT_HOST_EXECUTION_RESULT',
        'per_order_behavior': BEHAVIORS[mode],
        'policy': deepcopy(policy), 'mandate': deepcopy(mandate),
        'rule_source': 'USER_PROMPTS_AND_EXISTING_INSTRUCTIONS',
        'configuration_file_required': True,
        'host_workflow': {
            'in_scope_action': BEHAVIORS[mode],
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


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', required=True, help='Explicit user-selected policy JSON file')
    parser.add_argument('--task-id', required=True, help='Current host task identifier')
    args = parser.parse_args()
    try:
        policy = read_policy(args.policy, args.task_id)
        raw = sys.stdin.read()
        mandate = parse_json(raw) if raw.strip() else {}
        if type(mandate) is not dict:
            raise ValueError('Expected an object.')
        result = describe_mode(policy, mandate, task_id=args.task_id)
    except (ValueError, TypeError, OSError, RecursionError):
        parser.error('Expected the current task policy and a finite JSON mandate object.')
    print(json.dumps(redact_private(result), indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(cli())
