"""Durable single-owner session lease and required-action planning for Codex.

This is a supervised session helper, not a daemon. It cannot act while Codex is
closed. Broker-native protection and an explicit human handoff cover interruption.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from risk_engine import canonical_hash, dec, positive, timestamp


class SessionClosed(ValueError):
    pass


class SupervisedSession:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS sessions (
            account_alias TEXT PRIMARY KEY, owner TEXT NOT NULL, policy_hash TEXT NOT NULL,
            state TEXT NOT NULL, started_at TEXT NOT NULL, heartbeat_at TEXT NOT NULL,
            expires_at TEXT NOT NULL, heartbeat_seconds INTEGER NOT NULL, authorization_ref TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS session_events (
            sequence INTEGER PRIMARY KEY, account_alias TEXT, at TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
        """)

    def close(self):
        self.db.close()

    def _event(self, alias, now, kind, detail):
        self.db.execute("INSERT INTO session_events(account_alias,at,kind,detail) VALUES (?,?,?,?)",
                        (alias, now.isoformat(), kind, json.dumps(detail, allow_nan=False)))

    def start(self, account_alias, owner, policy_hash, expires_at, authorization_ref,
              heartbeat_seconds=60, now=None):
        now = now or datetime.now(timezone.utc)
        end = timestamp(expires_at)
        if not all(isinstance(v, str) and v.strip() for v in (account_alias, owner, policy_hash, authorization_ref)):
            raise SessionClosed("Session requires explicit owner, policy and actual human session authorization")
        if (not now < end <= now + timedelta(hours=16) or type(heartbeat_seconds) is not int
                or not 5 <= heartbeat_seconds <= 300):
            raise SessionClosed("Invalid session duration/heartbeat")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.execute("SELECT * FROM sessions WHERE account_alias=?", (account_alias,)).fetchone()
            if existing and existing["state"] == "RUNNING":
                raise SessionClosed("Existing session must be explicitly stopped/reconciled before takeover")
            self.db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?)",
                            (account_alias, owner, policy_hash, "RUNNING", now.isoformat(), now.isoformat(),
                             end.isoformat(), heartbeat_seconds, authorization_ref))
            self._event(account_alias, now, "START", {"owner": owner, "policy_hash": policy_hash})
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return self.status(account_alias, owner, policy_hash, now)

    def status(self, account_alias, owner, policy_hash, now=None):
        now = now or datetime.now(timezone.utc)
        row = self.db.execute("SELECT * FROM sessions WHERE account_alias=?", (account_alias,)).fetchone()
        reasons = []
        if row is None:
            return {"ready": False, "reasons": ["NO_SUPERVISED_SESSION"]}
        if row["owner"] != owner:
            reasons.append("SESSION_OWNED_BY_ANOTHER_RUN")
        if row["policy_hash"] != policy_hash:
            reasons.append("SESSION_POLICY_CHANGED")
        if row["state"] != "RUNNING":
            reasons.append("SESSION_STOPPED")
        if not timestamp(row["started_at"]) <= now < timestamp(row["expires_at"]):
            reasons.append("SESSION_EXPIRED_OR_CLOCK_REVERSED")
        if not 0 <= (now - timestamp(row["heartbeat_at"])).total_seconds() <= row["heartbeat_seconds"]:
            reasons.append("HEARTBEAT_LOST")
        return {"ready": not reasons, "reasons": reasons, "account_alias": account_alias,
                "owner": row["owner"], "heartbeat_at": row["heartbeat_at"], "expires_at": row["expires_at"],
                "policy_hash": row["policy_hash"], "checked_at": now.isoformat()}

    def heartbeat(self, account_alias, owner, policy_hash, now=None):
        now = now or datetime.now(timezone.utc)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            result = self.status(account_alias, owner, policy_hash, now)
            if not result["ready"]:
                raise SessionClosed("; ".join(result["reasons"]) + "; cannot revive a stale lease silently")
            self.db.execute("UPDATE sessions SET heartbeat_at=? WHERE account_alias=?", (now.isoformat(), account_alias))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return self.status(account_alias, owner, policy_hash, now)

    def stop(self, account_alias, owner, handoff, now=None):
        now = now or datetime.now(timezone.utc)
        if not handoff.get("evidence_ref") or handoff.get("disposition") not in {"flat", "protected_human_handoff", "emergency_handoff"}:
            raise SessionClosed("Explicit flat/protection/emergency handoff evidence required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT owner FROM sessions WHERE account_alias=?", (account_alias,)).fetchone()
            if not row or row["owner"] != owner:
                raise SessionClosed("Cannot stop another run's lease")
            self.db.execute("UPDATE sessions SET state='STOPPED' WHERE account_alias=?", (account_alias,))
            self._event(account_alias, now, "STOP", handoff)
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise


def actions_needed(snapshot, positions, protection, now=None):
    """Return required actions, never broker commands or permission to cancel stops.

    Protection records identify symbol/sleeve, covered_quantity, as_of and state.
    Time exits remain due even if a protective stop is working at the broker.
    """
    now = now or datetime.now(timezone.utc)
    actions = []
    if snapshot.get("reconciled") is not True:
        actions.append({"action": "RECONCILE_ACCOUNT_BEFORE_NEW_RISK"})
    closing = timestamp(snapshot["session"]["close"])
    for position in positions:
        if position["sleeve"] == "core" or dec(position["quantity"]) == 0:
            continue
        quantity = positive(position["quantity"])
        cover = [p for p in protection if p["symbol"] == position["symbol"] and p["sleeve"] == position["sleeve"]]
        # Duplicate records cannot multiply the coverage of one broker protection group.
        if len({p["protection_ref"] for p in cover}) != len(cover):
            raise SessionClosed("Duplicate protective coverage records")
        covered = sum((dec(p["covered_quantity"]) for p in cover if p["state"] == "working"
                       and p.get("native_broker") is True and p.get('side') == 'sell'
                       and dec(p['stop_price']) == dec(position['stop_price'])
                       and timestamp(p['expires_at']) >= timestamp(position['exit_by'])
                       and 0 <= (now - timestamp(p["as_of"])).total_seconds() <= 30), dec(0))
        if covered < quantity:
            actions.append({"symbol": position["symbol"], "sleeve": position["sleeve"],
                            "action": "PROTECTION_GAP_HALT_ENTRIES_AND_ESCALATE", "uncovered_quantity": str(quantity - covered)})
        if covered > quantity:
            actions.append({"symbol": position["symbol"], "sleeve": position["sleeve"],
                            "action": "EXCESS_EXIT_COVERAGE_RECONCILE_POTENTIAL_OVERSELL", "excess_quantity": str(covered - quantity)})
        deadline = timestamp(position["exit_by"])
        if position["sleeve"] == "intraday" and deadline >= closing:
            actions.append({"symbol": position["symbol"], "action": "INVALID_INTRADAY_EXIT_DEADLINE"})
        if now >= deadline:
            actions.append({"symbol": position["symbol"], "sleeve": position["sleeve"],
                            "action": "TIME_EXIT_DUE_RECONCILE_PROTECTIVE_ORDERS_THEN_REDUCE", "quantity": str(quantity)})
    return {"new_entries_permitted_by_supervisor": not actions, "required_actions": actions,
            "checked_at": now.isoformat(), "snapshot_hash": canonical_hash(snapshot),
            "caveat": "Active-session planner; no process runs or sends notifications after Codex stops"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8-sig"))
    session = SupervisedSession(args.database)
    try:
        operation = request["operation"]
        if operation not in {"start", "heartbeat", "status", "stop"}:
            raise ValueError("Unknown session operation")
        result = getattr(session, operation)(**request["inputs"])
        print(json.dumps(result or {"state": "STOPPED"}, indent=2))
    finally:
        session.close()


if __name__ == "__main__":
    main()
