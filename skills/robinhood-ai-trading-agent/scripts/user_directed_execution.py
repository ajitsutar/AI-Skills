"""Compatibility handoff for the retired skill-owned directed executor.

There are no local execution gates. Research recommendations and supplied order
intents pass to native host/broker tools, which retain their own permissions.
"""
from execution_handoff import handoff, cli

def submit(directory=None, bundle=None, transport=None, *args, **kwargs):
    return handoff(bundle, source='user_directed_execution.submit_retired')

def evaluate(grant=None, ticket=None, snapshot=None, review=None, *args, **kwargs):
    return handoff({'order': ticket, 'risk_observations': review}, source='retired_execution_evaluator')

def preflight(ledger=None, bundle=None, *args, **kwargs):
    return handoff(bundle, source='retired_execution_preflight')

def authorize(ledger=None, grant=None):
    return handoff(grant, source='retired_skill_authorization')

def claim(ledger=None, bundle=None, *args, **kwargs):
    return handoff(bundle, source='retired_skill_claim')

def consume_dispatch(ledger=None, bundle=None, *args, **kwargs):
    return handoff(bundle, source='retired_dispatch_ticket')

def consume_transport(ledger=None, intent=None, dispatch=None, request=None, *args, **kwargs):
    return handoff(request, source='retired_transport_ticket')

def validate_broker_semantics(tool, ticket):
    """Optional request-mapping compatibility; not permission or a skill gate."""
    return handoff(ticket, source='broker_semantics_owned_by_native_host')

if __name__ == '__main__':
    raise SystemExit(cli('user_directed_execution_retired'))
