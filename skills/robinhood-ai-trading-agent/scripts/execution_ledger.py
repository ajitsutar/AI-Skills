"""Local order-intent journal and permission gate; deliberately contains no broker client.

The trusted execution stage calls claim BEFORE one official MCP submission, then
records cumulative broker status. A timeout is UNKNOWN, never a retry permission.
This is operational state, not an authentication/security boundary against a process
that can edit this database. Human authorization must be verified by the host.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone

from risk_engine import canonical_hash, dec, evaluate, fresh, positive, timestamp


TERMINAL = {"FILLED", "CANCELLED", "REJECTED"}
STATES = TERMINAL | {"CLAIMED", "UNKNOWN", "OPEN", "PARTIALLY_FILLED", "CANCEL_PENDING"}


class GateClosed(ValueError):
    pass


class ExecutionLedger:
    def __init__(self, path):
        self.path = Path(path)
        self.db = sqlite3.connect(path, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS authorizations (
                id TEXT PRIMARY KEY, body TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, signal_id TEXT UNIQUE NOT NULL, digest TEXT UNIQUE NOT NULL, body TEXT NOT NULL,
                state TEXT NOT NULL, filled TEXT NOT NULL DEFAULT '0', average_price TEXT,
                claimed_at TEXT NOT NULL, session_day TEXT NOT NULL, notional TEXT NOT NULL,
                auth_id TEXT NOT NULL, mode TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY, order_id TEXT, event TEXT NOT NULL,
                detail TEXT NOT NULL, at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cancellations (
                id TEXT PRIMARY KEY, request_hash TEXT UNIQUE NOT NULL, target_ref TEXT NOT NULL,
                state TEXT NOT NULL, auth_id TEXT NOT NULL, body TEXT NOT NULL, claimed_at TEXT NOT NULL);
        """)

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def authorize(self, record):
        """Host records an actual human grant, not an LLM-generated approval.

        record: id, kind (order/mandate), policy_hash, account_alias, starts_at,
        expires_at, human_authorization_ref; order grants also order_hash/review_hash.
        A reference is a local user-message label, never a token or account ID.
        """
        if record["kind"] not in {"order", "mandate"}:
            raise GateClosed("Unknown authorization type")
        if not record["human_authorization_ref"] or not record["account_alias"]:
            raise GateClosed("Explicit human grant and account alias required")
        if timestamp(record["starts_at"]) >= timestamp(record["expires_at"]):
            raise GateClosed("Invalid grant interval")
        if record["kind"] == "order" and (not record["order_hash"] or not record["review_hash"]):
            raise GateClosed("Exact order and review hashes required")
        with self.transaction():
            self.db.execute("INSERT INTO authorizations(id,body) VALUES (?,?)",
                            (record["id"], json.dumps(record, sort_keys=True, allow_nan=False)))

    def revoke(self, authorization_id):
        with self.transaction():
            if not self.db.execute("UPDATE authorizations SET revoked=1 WHERE id=?",
                                   (authorization_id,)).rowcount:
                raise GateClosed("Unknown authorization")

    def claim(self, policy, snapshot, order, review, authorization_id=None, now=None):
        """Atomically consume permission and reserve this intent before any submission.

        One nonterminal local order at a time. This intentionally serializes the
        execution stage; unresolved attempts halt further submissions after restart.
        """
        now = now or datetime.now(timezone.utc)
        with self.transaction():
            verdict = evaluate(policy, snapshot, order, now)
            if not verdict["allowed"]:
                raise GateClosed("; ".join(verdict["reasons"]))
            digest = canonical_hash(order)
            if self.db.execute("SELECT 1 FROM orders WHERE id=? OR digest=? OR signal_id=?", (order["id"], digest, order["signal_id"])).fetchone():
                raise GateClosed("DUPLICATE_ORDER_INTENT")
            if self.db.execute("SELECT 1 FROM orders WHERE state NOT IN ('FILLED','CANCELLED','REJECTED')").fetchone():
                raise GateClosed("UNRESOLVED_PRIOR_ORDER_REQUIRES_RECONCILIATION")
            if self.db.execute("SELECT 1 FROM cancellations WHERE state!='TERMINAL'").fetchone():
                raise GateClosed("UNRESOLVED_CANCELLATION_REQUIRES_RECONCILIATION")
            previous_cancel = self.db.execute('SELECT id FROM cancellations ORDER BY rowid DESC LIMIT 1').fetchone()
            if previous_cancel and snapshot.get('reconciled_through_cancellation') != previous_cancel['id']:
                raise GateClosed('REFRESH_BROKER_SNAPSHOT_AFTER_CANCELLATION')
            previous = self.db.execute("SELECT id FROM orders ORDER BY rowid DESC LIMIT 1").fetchone()
            if previous and snapshot.get("reconciled_through_intent") != previous["id"]:
                raise GateClosed("REFRESH_BROKER_SNAPSHOT_AFTER_PREVIOUS_INTENT")
            mode = policy["mode"]
            auth_id = "paper"
            if mode != "paper":
                if policy["deployment_context"] != "personal":
                    raise GateClosed("LEARNING_CONTEXT_LIVE_EXECUTION_DISABLED")
                if order["side"] == "buy" and order["setup"] not in policy["live_validated_setups"]:
                    raise GateClosed("STRATEGY_NOT_PROMOTED_TO_LIVE")
                row = self.db.execute("SELECT body,revoked FROM authorizations WHERE id=?", (authorization_id,)).fetchone()
                if not row or row["revoked"]:
                    raise GateClosed("NO_ACTIVE_HUMAN_AUTHORIZATION")
                auth = json.loads(row["body"])
                if not timestamp(auth["starts_at"]) <= now < timestamp(auth["expires_at"]):
                    raise GateClosed("AUTHORIZATION_EXPIRED_OR_NOT_STARTED")
                if auth["policy_hash"] != canonical_hash(policy):
                    raise GateClosed("POLICY_CHANGED_REAUTHORIZE")
                if auth["account_alias"] != snapshot["account_alias"] or order["account_alias"] != auth["account_alias"]:
                    raise GateClosed("ACCOUNT_SCOPE_MISMATCH")
                if auth["kind"] == "order":
                    if auth["order_hash"] != digest or auth["review_hash"] != canonical_hash(review):
                        raise GateClosed("APPROVED_ORDER_OR_REVIEW_CHANGED")
                    if (self.db.execute("SELECT 1 FROM orders WHERE auth_id=?", (authorization_id,)).fetchone()
                            or self.db.execute("SELECT 1 FROM cancellations WHERE auth_id=?", (authorization_id,)).fetchone()):
                        raise GateClosed("ONE_TIME_APPROVAL_ALREADY_CONSUMED")
                elif mode != "bounded_autonomous":
                    raise GateClosed("PER_ORDER_APPROVAL_REQUIRED")
                elif order["sleeve"] not in policy["autonomous_sleeves"]:
                    raise GateClosed("SLEEVE_OUTSIDE_AUTONOMOUS_MANDATE")
                if review["order_hash"] != digest or review["official_mcp"] is not True:
                    raise GateClosed("EXACT_OFFICIAL_BROKER_REVIEW_REQUIRED")
                if review["snapshot_hash"] != canonical_hash(snapshot):
                    raise GateClosed("BROKER_SNAPSHOT_CHANGED_REVIEW_AGAIN")
                if review["accepted"] is not True or review["supported_order"] is not True:
                    raise GateClosed("BROKER_REVIEW_FAILED")
                if not fresh(review["checked_at"], now, policy["limits"]["max_quote_age_seconds"]):
                    raise GateClosed("STALE_BROKER_REVIEW")
                if review["trade_approvals_enabled"] is not False:
                    raise GateClosed("BROKER_REQUIRES_MANUAL_APPROVAL")
                if auth["kind"] == "mandate" and review["warnings"]:
                    raise GateClosed("NEW_BROKER_WARNINGS_REQUIRE_REVIEW")
                if order["side"] == "buy" and order["sleeve"] != "core":
                    if review["exit_plan_verified"] is not True:
                        raise GateClosed("NO_VERIFIED_PROTECTION_AND_TIME_EXIT")
                if policy["schema_version"] != 3:
                    raise GateClosed("PERSONAL_POLICY_V3_REQUIRED")
                from personal_readiness import entry_readiness
                try:
                    readiness = entry_readiness(policy, snapshot, order, review["readiness_inputs"],
                                                self.path.parent, verdict, now)
                except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
                    raise GateClosed("PERSONAL_READINESS_INVALID_OR_MISSING: " + str(exc)) from exc
                if not readiness["ready"]:
                    raise GateClosed("; ".join(readiness["reasons"]))
                auth_id = authorization_id
            day = timestamp(snapshot["session"]["open"]).date().isoformat()
            # Approval and bounded modes share the same account's live counters.
            # Paper activity stays separate and never resets a live session budget.
            mode_filter = "mode='paper'" if mode == "paper" else "mode!='paper'"
            today = self.db.execute("SELECT notional,body FROM orders WHERE session_day=? AND " + mode_filter,
                                    (day,)).fetchall()
            external_count, external_turnover = dec(0), dec(0)
            if mode != 'paper':
                if snapshot.get('session_activity_reconciled') is not True:
                    raise GateClosed('BROKER_SESSION_ACTIVITY_NOT_RECONCILED')
                external_count = dec(snapshot['external_session_order_count'])
                external_turnover = dec(snapshot['external_session_turnover'])
                if external_count < 0 or external_count != external_count.to_integral_value() or external_turnover < 0:
                    raise GateClosed('INVALID_EXTERNAL_SESSION_ACTIVITY')
                setup_counts = [dec(v) for v in snapshot['external_setup_entry_counts'].values()]
                if any(v < 0 or v != v.to_integral_value() for v in setup_counts) or sum(setup_counts,dec(0)) > external_count:
                    raise GateClosed('INVALID_EXTERNAL_SETUP_ACTIVITY')
            if order["side"] == "buy":
                if len(today) + external_count >= dec(policy["limits"]["max_orders_per_day"]):
                    raise GateClosed("DAILY_ORDER_LIMIT")
                if mode != 'paper' and order['sleeve'] != 'core':
                    cap=policy['strategy_registry'][order['setup']]['max_entries_per_symbol_session']
                    if type(cap) is not int or cap < 1:
                        raise GateClosed('INVALID_STRATEGY_SESSION_ENTRY_CAP')
                    previous_entries=[json.loads(row['body']) for row in today]
                    count=sum(1 for prior in previous_entries if prior['symbol']==order['symbol']
                              and prior['setup']==order['setup'] and prior['side']=='buy')
                    count += int(snapshot['external_setup_entry_counts'].get(order['setup']+':'+order['symbol'],0))
                    if count >= cap:
                        raise GateClosed('STRATEGY_SESSION_ENTRY_LIMIT')
                used = sum((dec(r["notional"]) for r in today), external_turnover)
                if used + dec(verdict["metrics"]["notional"]) > dec(policy["limits"]["max_daily_turnover"]):
                    raise GateClosed("DAILY_TURNOVER_LIMIT")
            self.db.execute("INSERT INTO orders(id,signal_id,digest,body,state,claimed_at,session_day,notional,auth_id,mode) VALUES (?,?,?,?,'CLAIMED',?,?,?,?,?)",
                            (order["id"], order["signal_id"], digest, json.dumps(order, sort_keys=True, allow_nan=False), now.isoformat(),
                             day, verdict["metrics"]["notional"], auth_id, mode))
            self.db.execute("INSERT INTO events(order_id,event,detail,at) VALUES (?,?,?,?)",
                            (order["id"], "CLAIMED", json.dumps({"policy_hash": canonical_hash(policy), "review_hash": canonical_hash(review)}), now.isoformat()))
            return {"id": order["id"], "state": "CLAIMED", "order_hash": digest,
                    "may_submit_once": mode != "paper", "mode": mode,
                    "broker_request_hash": readiness["evidence"]["request_hash"] if mode != "paper" else None}

    def reconcile(self, order_id, state, cumulative_filled, average_price=None, now=None):
        """Persist an unresolved latch if a previously terminal report contradicts.

        The failed update must not roll back the latch and leave new claims enabled.
        Reconcile from authoritative broker evidence before clearing UNKNOWN.
        """
        try:
            return self._reconcile(order_id, state, cumulative_filled, average_price, now)
        except (ValueError, TypeError, KeyError) as exc:
            with self.transaction():
                row = self.db.execute("SELECT state FROM orders WHERE id=?", (order_id,)).fetchone()
                if row and row["state"] in TERMINAL:
                    self.db.execute("UPDATE orders SET state='UNKNOWN' WHERE id=?", (order_id,))
                    self.db.execute("INSERT INTO events(order_id,event,detail,at) VALUES (?,?,?,?)",
                                    (order_id, "TERMINAL_CONFLICT", json.dumps({"previous_state": row["state"],
                                     "error": str(exc)}), (now or datetime.now(timezone.utc)).isoformat()))
            raise

    def _reconcile(self, order_id, state, cumulative_filled, average_price=None, now=None):
        """Use cumulative broker quantities, never add repeated snapshots as fills.

        CANCELLED/REJECTED may retain partial fills. A contradictory terminal update
        raises and requires operator investigation; it never silently releases risk.
        """
        now = now or datetime.now(timezone.utc)
        if state not in STATES - {"CLAIMED"}:
            raise GateClosed("Invalid broker state")
        filled = dec(cumulative_filled)
        with self.transaction():
            row = self.db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if not row:
                raise GateClosed("Unknown local intent")
            quantity = positive(json.loads(row["body"])["quantity"])
            if filled < dec(row["filled"]) or filled > quantity or filled < 0:
                raise GateClosed("NONMONOTONIC_OR_EXCESS_FILL")
            if state == "FILLED" and filled != quantity:
                raise GateClosed("FILLED_REQUIRES_FULL_QUANTITY")
            if state == "PARTIALLY_FILLED" and not 0 < filled < quantity:
                raise GateClosed("INVALID_PARTIAL_FILL")
            if state == "OPEN" and filled != 0:
                raise GateClosed("OPEN_WITH_FILL_REQUIRES_PARTIAL_STATE")
            if filled and (average_price is None or positive(average_price) <= 0):
                raise GateClosed("CUMULATIVE_AVERAGE_FILL_PRICE_REQUIRED")
            avg = str(positive(average_price)) if filled else None
            intent = json.loads(row['body'])
            if filled and ((intent['side'] == 'buy' and dec(avg) > dec(intent['limit_price']))
                           or (intent['side'] == 'sell' and dec(avg) < dec(intent['limit_price']))):
                raise GateClosed('FILL_CONTRADICTS_LIMIT_PRICE_EXCLUDING_FEES')
            if row["state"] in TERMINAL:
                same_average = (row["average_price"] is None and avg is None) or (
                    row["average_price"] is not None and avg is not None and dec(row["average_price"]) == dec(avg))
                if row["state"] == state and dec(row["filled"]) == filled and same_average:
                    return dict(row)
                raise GateClosed("CONTRADICTORY_TERMINAL_STATE_INVESTIGATE")
            self.db.execute("UPDATE orders SET state=?,filled=?,average_price=? WHERE id=?", (state, str(filled), avg, order_id))
            self.db.execute("INSERT INTO events(order_id,event,detail,at) VALUES (?,?,?,?)",
                            (order_id, state, json.dumps({"cumulative_filled": str(filled), "average_price": avg}), now.isoformat()))
            return dict(self.db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone())

    def unresolved(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM orders WHERE state NOT IN ('FILLED','CANCELLED','REJECTED')")]

    def claim_cancel(self, policy, snapshot, action, review, authorization_id, now=None):
        """Journal one schema-bound cancellation; ACK alone never releases risk.

        This is separate from the entry's state (a filled entry can have working
        protection). Bounded grants must explicitly cover each cancellation role.
        Cancelled protection requires a reviewed reduction/handoff plan; cancel
        and replacement are not atomic and must never overlap sell quantities.
        """
        from risk_engine import validate_policy
        from broker_bridge import build_request
        from supervised_session import SupervisedSession
        now = now or datetime.now(timezone.utc)
        validate_policy(policy)
        if (policy['schema_version'] != 3 or policy['mode'] == 'paper'
                or policy['deployment_context'] != 'personal' or policy['configuration_status'] != 'approved'):
            raise GateClosed('APPROVED_PERSONAL_LIVE_POLICY_REQUIRED')
        with self.transaction():
            if snapshot['reconciled'] is not True or not fresh(snapshot['as_of'],now,policy['limits']['max_snapshot_age_seconds']):
                raise GateClosed('FRESH_RECONCILED_ACCOUNT_REQUIRED')
            target = [o for o in snapshot['open_orders'] if o['local_ref'] == action['target_ref']]
            if len(target) != 1 or target[0]['status'] not in {'open','partially_filled','cancel_pending'}:
                raise GateClosed('EXACT_KNOWN_OPEN_ORDER_REQUIRED')
            target = target[0]
            if action['account_alias'] != snapshot['account_alias'] or action['symbol'] != target['symbol'] or action['sleeve'] != target['sleeve']:
                raise GateClosed('CANCELLATION_SCOPE_MISMATCH')
            role = target['role']
            if role not in {'entry','protection'} or action['role'] != role:
                raise GateClosed('CANCELLATION_ROLE_MISMATCH')
            if target['side'] != ('buy' if role == 'entry' else 'sell'):
                raise GateClosed('CANCELLATION_SIDE_ROLE_CONFLICT')
            if role == 'protection':
                plan = review['reduction_plan']
                if (plan['symbol'] != action['symbol'] or plan['sleeve'] != action['sleeve']
                        or plan.get('purpose') != 'reduce_owned_position' or not plan.get('human_handoff_ref')
                        or plan.get('gap_risk_acknowledged') is not True):
                    raise GateClosed('PROTECTION_CANCELLATION_NEEDS_REDUCTION_AND_HANDOFF_PLAN')
            row = self.db.execute('SELECT body,revoked FROM authorizations WHERE id=?',(authorization_id,)).fetchone()
            if not row or row['revoked']:
                raise GateClosed('NO_ACTIVE_HUMAN_AUTHORIZATION')
            auth = json.loads(row['body'])
            if (auth['policy_hash'] != canonical_hash(policy) or auth['account_alias'] != action['account_alias']
                    or not timestamp(auth['starts_at']) <= now < timestamp(auth['expires_at'])):
                raise GateClosed('CANCELLATION_AUTHORIZATION_SCOPE_OR_EXPIRY')
            if auth['kind'] == 'order':
                if auth['order_hash'] != canonical_hash(action) or auth['review_hash'] != canonical_hash(review):
                    raise GateClosed('APPROVED_CANCELLATION_CHANGED')
                if (self.db.execute('SELECT 1 FROM orders WHERE auth_id=?',(authorization_id,)).fetchone()
                        or self.db.execute('SELECT 1 FROM cancellations WHERE auth_id=?',(authorization_id,)).fetchone()):
                    raise GateClosed('ONE_TIME_APPROVAL_ALREADY_CONSUMED')
            elif (policy['mode'] != 'bounded_autonomous' or action['sleeve'] not in policy['autonomous_sleeves']
                    or ('cancel_entries' if role == 'entry' else 'cancel_protection_for_reduction') not in auth.get('permissions', [])):
                raise GateClosed('CANCELLATION_OUTSIDE_MANDATE')
            if (review['snapshot_hash'] != canonical_hash(snapshot) or review.get('official_mcp') is not True
                    or review.get('accepted') is not True or review.get('trade_approvals_enabled') is not False
                    or not fresh(review['checked_at'],now,policy['limits']['max_quote_age_seconds'])):
                raise GateClosed('FRESH_OFFICIAL_CANCELLATION_REVIEW_REQUIRED')
            if review.get('warnings'):
                raise GateClosed('CANCELLATION_WARNINGS_REQUIRE_RESOLUTION')
            session_path = self.path.parent/'supervised-session.db'
            if not session_path.is_file():
                raise GateClosed('NO_SUPERVISED_SESSION')
            session = SupervisedSession(session_path)
            try:
                status = session.status(action['account_alias'],review['session_owner'],canonical_hash(policy),now)
            finally:
                session.close()
            if not status['ready']:
                raise GateClosed('; '.join(status['reasons']))
            request = build_request(review['capabilities'],'cancel',review['broker_inputs'],now,action['account_alias'])
            if request['request_hash'] != review['reviewed_request_hash']:
                raise GateClosed('CANCELLATION_REQUEST_CHANGED')
            if review['broker_inputs']['target_ref'] != action['target_ref']:
                raise GateClosed('PRIVATE_BROKER_ID_MUST_RESOLVE_TO_EXACT_LOCAL_TARGET')
            if review.get('target_identity_verified') is not True:
                raise GateClosed('BROKER_CANCEL_TARGET_IDENTITY_NOT_VERIFIED')
            if self.db.execute("SELECT 1 FROM cancellations WHERE state!='TERMINAL'").fetchone():
                raise GateClosed('UNRESOLVED_PRIOR_CANCELLATION')
            self.db.execute('INSERT INTO cancellations VALUES (?,?,?,?,?,?,?)',
                (action['id'],request['request_hash'],action['target_ref'],'CLAIMED',authorization_id,
                 json.dumps(action,sort_keys=True,allow_nan=False),now.isoformat()))
            return dict(id=action['id'],state='CLAIMED',may_submit_once=True,broker_request_hash=request['request_hash'])

    def reconcile_cancel(self, action_id, target_state, evidence_ref, now=None):
        """Only authoritative terminal target evidence finishes a cancellation."""
        now = now or datetime.now(timezone.utc)
        if target_state not in {'UNKNOWN','OPEN','PARTIALLY_FILLED','CANCEL_PENDING','CANCELLED','FILLED','REJECTED'} or not evidence_ref:
            raise GateClosed('EXPLICIT_CANCEL_TARGET_STATE_AND_EVIDENCE_REQUIRED')
        state = 'TERMINAL' if target_state in TERMINAL else 'UNKNOWN'
        with self.transaction():
            row = self.db.execute('SELECT * FROM cancellations WHERE id=?',(action_id,)).fetchone()
            if not row:
                raise GateClosed('UNKNOWN_CANCELLATION')
            self.db.execute('UPDATE cancellations SET state=? WHERE id=?',(state,action_id))
            self.db.execute('INSERT INTO events(order_id,event,detail,at) VALUES (?,?,?,?)',
                (action_id,'CANCEL_RECONCILIATION',json.dumps(dict(target_state=target_state,evidence_ref=evidence_ref)),now.isoformat()))
        return dict(id=action_id,state=state,target_state=target_state,
                    next='Refresh fills, positions and protection; a replacement requires a new order claim')

    def unresolved_cancellations(self):
        return [dict(r) for r in self.db.execute("SELECT id,target_ref,state FROM cancellations WHERE state!='TERMINAL'")]
