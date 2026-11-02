"""Apply auditable financial-cell corrections from any reviewed accessible source.

Offline only: this validates provenance structure and replays declared mappings;
it cannot establish that a web source is authentic or that an extraction is right.
The original snapshot is never mutated. No arbitrary code or URL is executed.
"""
import argparse
import copy
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from price_audit import timestamp
from public_research import digest, number, require, table

FIELDS = {
    'income': {'OperatingIncome', 'NetIncome', 'NetIncomeCommonStockholders'},
    'balance': {'TotalDebt', 'TotalAssets', 'CashAndCashEquivalents', 'CommonStockEquity'},
    'cashflow': {'OperatingCashFlow', 'CapitalExpenditure'},
}


def apply_overlay(snapshot, overlay, source_root):
    require(overlay.get('schema_version') == 1, 'OVERLAY_VERSION')
    require(overlay.get('base_input_sha256') == digest(snapshot), 'OVERLAY_BASE_MISMATCH')
    cutoff = timestamp(overlay['information_cutoff'])
    root = Path(source_root).resolve()
    require(bool(overlay.get('source_policy')), 'SOURCE_POLICY_REQUIRED')
    require(bool(overlay.get('scope')) and bool(overlay.get('unresolved_gaps')), 'COVERAGE_DISCLOSURE_REQUIRED')
    sources = {}
    for s in overlay['sources']:
        require(s['id'] not in sources, 'DUPLICATE_SOURCE')
        parsed = urlparse(s['url'])
        require(parsed.scheme == 'https' and parsed.hostname, 'SOURCE_URL_REQUIRED')
        require(s['kind'] in {'issuer', 'regulator', 'vendor'}, 'SOURCE_KIND_REQUIRED')
        require(timestamp(s['published_at']) <= cutoff, 'SOURCE_AFTER_CUTOFF')
        retrieved = timestamp(s['retrieved_at'])
        require(timestamp(s['published_at']) <= retrieved, 'PUBLICATION_AFTER_RETRIEVAL')
        require(retrieved <= cutoff or bool(s.get('point_in_time_evidence')), 'LATER_RETRIEVAL_REQUIRES_POINT_IN_TIME_EVIDENCE')
        path = (root / s['file']).resolve()
        require(root in path.parents and path.is_file(), 'UNSAFE_OR_MISSING_SOURCE_FILE')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == s['content_sha256'], 'SOURCE_BYTES_MISMATCH')
        sources[s['id']] = s
    out = copy.deepcopy(snapshot)
    rows = {r['symbol']: r for r in out['rows']}
    cells = set()
    require(bool(overlay['changes']), 'NO_CHANGES')
    for c in overlay['changes']:
        key = (c['symbol'], c['table'], c['field'], c['period_end'])
        require(key not in cells, 'DUPLICATE_CELL'); cells.add(key)
        require(c['symbol'] in rows and c['table'] in FIELDS and c['field'] in FIELDS[c['table']], 'UNSUPPORTED_CELL')
        require(c.get('basis') == 'GAAP' and c.get('currency') == 'USD' and c.get('units') == 'USD', 'ACCOUNTING_BASIS_OR_UNITS')
        require(c.get('duration') == ('instant' if c['table'] == 'balance' else 'quarter'), 'QUARTER_NOT_YTD_REQUIRED')
        require(bool(c.get('locator')) and bool(c.get('derivation')), 'EXTRACTION_AUDIT_REQUIRED')
        require(c.get('conflict_reviewed') is True and bool(c.get('choice_reason')), 'SOURCE_CONFLICT_REVIEW_REQUIRED')
        require(c['source_ids'] and all(x in sources for x in c['source_ids']), 'UNKNOWN_SOURCE')
        end = date.fromisoformat(c['period_end'])
        require(all(end <= timestamp(sources[x]['published_at']).date() for x in c['source_ids']), 'FUTURE_FINANCIAL_PERIOD')
        value = number(c['value'])
        if c['table'] == 'balance': require(value >= 0 or c['field'] == 'CommonStockEquity', 'NEGATIVE_BALANCE')
        if c['field'] == 'CapitalExpenditure': require(value <= 0, 'CAPEX_OUTFLOW_SIGN')
        t = rows[c['symbol']][c['table']]
        table(t)  # Validate the starting table before extending it.
        if c['period_end'] not in t['columns']:
            t['columns'].append(c['period_end'])
            for values in t['data']: values.append(None)
        if c['field'] not in t['index']:
            t['index'].append(c['field']); t['data'].append([None] * len(t['columns']))
        i, j = t['index'].index(c['field']), t['columns'].index(c['period_end'])
        require(t['data'][i][j] == c.get('old_value'), 'OLD_VALUE_MISMATCH')
        t['data'][i][j] = str(value)
    out['source_overlay'] = {
        'version': 1, 'base_input_sha256': digest(snapshot), 'overlay_sha256': digest(overlay),
        'information_cutoff': overlay['information_cutoff'], 'source_policy': overlay['source_policy'],
        'scope': overlay['scope'], 'unresolved_gaps': overlay['unresolved_gaps'],
        'changed_cells': len(cells), 'source_kinds': sorted({s['kind'] for s in sources.values()}),
        'label': 'MULTISOURCE_CORRECTED_VENDOR_BASELINE_NOT_FILING_VERIFIED_UNIVERSE',
    }
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('snapshot', type=Path); p.add_argument('overlay', type=Path)
    p.add_argument('source_root', type=Path); p.add_argument('output', type=Path)
    a = p.parse_args()
    read = lambda path: json.loads(path.read_text(encoding='utf-8-sig'))
    out = apply_overlay(read(a.snapshot), read(a.overlay), a.source_root)
    with a.output.open('x', encoding='utf-8') as f: json.dump(out, f, separators=(',', ':'), allow_nan=False)
    print(json.dumps({'input_sha256': digest(out), 'provenance': out['source_overlay']}))


if __name__ == '__main__': main()
