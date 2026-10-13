"""Read-only compatibility access to historical local execution records.

This module neither grants nor blocks execution and never mutates old runtime
databases. Native host/broker tools own current orders and authorization. The
legacy method names return informational handoffs so old callers cannot revive
skill-owned enforcement or silently reset historical records.
"""
import sqlite3
from pathlib import Path
from execution_handoff import handoff

TERMINAL = {'FILLED', 'CANCELLED', 'REJECTED', 'NOT_SUBMITTED'}
STATES = TERMINAL | {'CLAIMED', 'UNKNOWN', 'OPEN', 'PARTIALLY_FILLED', 'CANCEL_PENDING'}

class GateClosed(ValueError):
    """Import compatibility only; no skill execution path raises this class."""

class ExecutionLedger:
    def __init__(self, path):
        self.path = Path(path)

    def close(self):
        pass

    def _read(self, table, columns, condition):
        if not self.path.is_file():
            return []
        # All SQL identifiers here are fixed module constants, not user input.
        db = sqlite3.connect(self.path.resolve().as_uri() + '?mode=ro', uri=True)
        db.row_factory = sqlite3.Row
        try:
            tables = {r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if table not in tables:
                return []
            existing = {r['name'] for r in db.execute('PRAGMA table_info(' + table + ')')}
            selected = [c for c in columns if c in existing]
            return [dict(r) for r in db.execute('SELECT ' + ','.join(selected) + ' FROM ' + table + ' WHERE ' + condition)]
        finally:
            db.close()

    def unresolved(self):
        return self._read('orders', ['id','state','filled','average_price','fees'],
                          "state NOT IN ('FILLED','CANCELLED','REJECTED','NOT_SUBMITTED')")

    def unresolved_incidents(self):
        return self._read('incidents', ['id','state','created_at','resolved_at'], "state!='RESOLVED'")

    def unresolved_cancellations(self):
        return self._read('cancellations', ['id','state'], "state!='TERMINAL'")

    def _retired(self, operation, *args, **kwargs):
        return handoff({'legacy_operation': operation}, source='execution_ledger_retired')

    def authorize(self, *args, **kwargs): return self._retired('authorize', *args, **kwargs)
    def revoke(self, *args, **kwargs): return self._retired('revoke', *args, **kwargs)
    def claim(self, *args, **kwargs): return self._retired('claim', *args, **kwargs)
    def consume_dispatch(self, *args, **kwargs): return self._retired('consume_dispatch', *args, **kwargs)
    def consume_transport(self, *args, **kwargs): return self._retired('consume_transport', *args, **kwargs)
    def claim_cancel(self, *args, **kwargs): return self._retired('claim_cancel', *args, **kwargs)
    def reconcile(self, *args, **kwargs): return self._retired('reconcile', *args, **kwargs)
    def reconcile_cancel(self, *args, **kwargs): return self._retired('reconcile_cancel', *args, **kwargs)
    def quarantine(self, *args, **kwargs): return self._retired('quarantine', *args, **kwargs)
    def resolve_incident(self, *args, **kwargs): return self._retired('resolve_incident', *args, **kwargs)
    def mark_unknown(self, *args, **kwargs): return self._retired('mark_unknown', *args, **kwargs)
    def mark_not_submitted(self, *args, **kwargs): return self._retired('mark_not_submitted', *args, **kwargs)
