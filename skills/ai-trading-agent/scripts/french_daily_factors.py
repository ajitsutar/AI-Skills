"""Join a pinned, manually downloaded daily French FF3/FF5 CSV to asset returns."""
import argparse
import csv
import hashlib
import io
import json
import math
from datetime import date, datetime
from pathlib import Path

from factor_research import fama_french


def clock(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("An offset is required for capture and study clocks")
    return result


def evaluate(raw, study):
    digest = hashlib.sha256(raw).hexdigest()
    if digest != study["sha256"]:
        raise ValueError("French factor CSV differs from its pinned SHA-256")
    as_of = clock(study["as_of"])
    captured = clock(study["retrieved_at"])
    if captured > as_of or not study["source_url"].strip():
        raise ValueError("A source and factor vintage available by the study cutoff are required")
    model = study["model"]
    if model not in ("FF3", "FF5"):
        raise ValueError("Choose daily FF3 or FF5")
    fields = ["Mkt-RF", "SMB", "HML"] + (["RMW", "CMA"] if model == "FF5" else []) + ["RF"]
    inputs = study["asset_returns"]
    sessions = [date.fromisoformat(row["session"]) for row in inputs]
    if not sessions or sessions != sorted(set(sessions)) or sessions[-1] > as_of.date():
        raise ValueError("Expected unique, ordered historical asset sessions")
    required_end = date.fromisoformat(study["through_session"])
    if sessions[-1] != required_end:
        raise ValueError("Asset history does not reach the requested last session")
    wanted = set(sessions)
    found = {}
    header = False
    latest = None
    for cells in csv.reader(io.StringIO(raw.decode("utf-8-sig"))):
        cols = [item.strip() for item in cells]
        if not header:
            header = cols == ["", *fields]
            continue
        if not cols or not cols[0]:
            if latest is not None:
                break
            continue
        if not (len(cols[0]) == 8 and cols[0].isdigit()):
            raise ValueError("Expected daily YYYYMMDD French factor observations")
        day = datetime.strptime(cols[0], "%Y%m%d").date()
        if day > captured.date():
            raise ValueError("French factor session postdates the declared file capture")
        if latest is not None and day <= latest:
            raise ValueError("French factor sessions must be unique and increasing")
        latest = day
        if day not in wanted:
            continue
        if len(cols) != len(fields) + 1:
            raise ValueError("Wrong factor columns for " + day.isoformat())
        values = [float(token) for token in cols[1:]]
        if any(not math.isfinite(x) or x in (-99.99, -999.0) for x in values):
            raise ValueError("Missing French factor on " + day.isoformat())
        found[day] = {name.lower().replace("-", "_"): x / 100 for name, x in zip(fields, values)}
    if not header or latest is None or latest < required_end or found.keys() != wanted:
        raise ValueError("Missing, stale or mismatched daily factors for the requested sessions")
    rows = [{**found[d], "asset_return": r["asset_return"], "timestamp": d.isoformat()+"T00:00:00Z"}
            for d, r in zip(sessions, inputs)]
    return {"source_url": study["source_url"], "sha256": digest, "retrieved_at": study["retrieved_at"],
            "as_of": study["as_of"], "through_session": required_end.isoformat(),
            "last_file_session": latest.isoformat(), "provider_units": "percent_return",
            "regression": fama_french(rows, model, "daily")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("study", type=Path)
    args = parser.parse_args()
    result = evaluate(args.csv_file.read_bytes(), json.loads(args.study.read_text(encoding="utf-8-sig")))
    print(json.dumps(result, indent=2, allow_nan=False))
