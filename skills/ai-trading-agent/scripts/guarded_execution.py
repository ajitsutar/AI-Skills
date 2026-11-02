"""Compatibility handoff for retired skill-owned execution enforcement.

Normal execution belongs to native host/broker tools. No passed transport is
called, and no runtime, policy, grant, quote or incident is used as a skill gate.
"""
from pathlib import Path
from execution_handoff import handoff, cli

ROOT = Path(__file__).resolve().parents[1]

def runtime_path(directory, **kwargs):
    """Compatibility path conversion only; no runtime setup or validation."""
    return Path(directory)

def submit(directory=None, bundle=None, transport=None, **kwargs):
    return handoff(bundle, source='guarded_execution.submit_retired')

def consume_host_ticket(directory=None, intent_id=None, tool_name=None, arguments=None):
    """Legacy hook has no authorization function; remove it from host connectors."""
    return handoff({'tool_name': tool_name, 'arguments': arguments}, source='retired_ticket_hook')

class CommandTransport:
    """Compatibility shim; contains no subprocess, network or broker transport."""
    def __init__(self, directory=None, intent_id=None, **kwargs):
        pass
    def verify(self):
        return handoff(source='retired_transport_verification')
    def __call__(self, request):
        return handoff(request, source='retired_skill_transport')

def recover_readonly(directory=None, capabilities=None, plans=None, transport=None, account_alias=None, **kwargs):
    return handoff({'operation': 'broker_status_review', 'account_alias': account_alias},
                   source='retired_skill_recovery')

if __name__ == '__main__':
    raise SystemExit(cli('guarded_execution_retired'))
