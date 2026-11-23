"""Compare prospective paper-journal identities from supplied local registers."""
import argparse
import json
from collections import Counter

from handoff_report import strict_json
from supplied_research import read, require


POPULATIONS = {
    'decisions': 'Every expected decision slot for the evaluated variant, including holds, warm-up and missing observations, against the journal entry for that slot.',
    'orders': 'Every intended order linked to its decision, against an evidenced disposition with executed and remaining quantities accounted for. Include missed submissions, rejected, canceled, open and partially filled orders.',
    'fills': 'Every independent execution ID and its intended order, against the journal link to the same order, execution and applicable quote evidence.',
}
EXCEPTIONS = 'Retain unresolved quote or lifecycle evidence, outstanding-quantity differences, and unexplained fees, cash or position discrepancies against the independent records.'
DISPOSITIONS = {
    'HOLD_FOR_RECONCILIATION': 'A missing, unexpected, duplicate, misparented or unresolved identity or unexplained discrepancy puts the affected research assessment on hold, even when a numerical quality tolerance passes.',
    'INCONCLUSIVE': 'Unknown register coverage or an empty execution denominator leaves execution untested. A hold decision adds no executed order. Report sparse primary execution separately from shadow variants.',
    'LINKS_RECONCILED': 'When the registers agree, evaluate the separately prespecified performance, risk, sample and execution-quality criteria. A fully evidenced rejection or missed fill can satisfy accounting and still fail an operational tolerance.',
}


def protocol():
    return {'method': 'forward-registers-1', 'status': 'DESIGN_ONLY_NO_OBSERVATIONS',
            'populations': dict(POPULATIONS), 'exceptions': EXCEPTIONS, 'dispositions': dict(DISPOSITIONS)}


def identities(rows, population):
    if rows is None:
        return None, 0
    require(isinstance(rows, list), 'REGISTER_LIST_OR_NULL_REQUIRED')
    entries = []
    for row in rows:
        if population == 'decisions':
            require(isinstance(row, str) and row.strip(), 'DECISION_ID_REQUIRED')
            entries.append((None, row))
        else:
            require(isinstance(row, list) and len(row) == 2, 'PARENT_AND_EVENT_REQUIRED')
            parent, key = row
            require(parent is None or isinstance(parent, str) and parent.strip(), 'PARENT_ID_OR_NULL_REQUIRED')
            require(isinstance(key, str) and key.strip(), 'EVENT_ID_REQUIRED')
            entries.append((parent, key))
    duplicates = sum(count - 1 for count in Counter(key for _, key in entries).values() if count > 1)
    return set(entries), duplicates


def assess(document):
    """Inspect one variant/window. The caller supplies register completeness and accounting exceptions."""
    require(isinstance(document, dict) and set(document) == {*POPULATIONS, 'unresolved_exceptions'},
            'THREE_REGISTERS_AND_EXCEPTIONS_REQUIRED')
    missing, broken, counts = [], {}, {}
    parents = {}
    executed = None
    for name in POPULATIONS:
        pair = document[name]
        require(isinstance(pair, dict) and set(pair) == {'reference', 'accounted'}, 'REFERENCE_AND_ACCOUNTED_REQUIRED')
        registers = {}
        for side, rows in pair.items():
            entries, duplicates = identities(rows, name)
            registers[side] = entries
            label = name + '.' + side
            if entries is None:
                missing.append(label)
                continue
            if duplicates:
                broken[label + '.duplicate_ids'] = duplicates
            if name != 'decisions':
                parent_ids = parents[side]
                orphaned = sum(parent is None or (parent_ids is not None and parent not in parent_ids)
                               for parent, _ in entries)
                if orphaned:
                    broken[label + '.orphan_links'] = orphaned
        reference, accounted = registers['reference'], registers['accounted']
        counts[name] = None if reference is None else len(reference)
        if reference is not None and accounted is not None and reference != accounted:
            broken[name + '.missing'] = len(reference - accounted)
            broken[name + '.unexpected'] = len(accounted - reference)
        if name == 'fills' and reference is not None and accounted is not None:
            executed = len({parent for parent, _ in reference & accounted if parent is not None})
        parents = {side: None if rows is None else {key for _, key in rows} for side, rows in registers.items()}
    issues = document['unresolved_exceptions']
    if issues is None:
        missing.append('unresolved_exceptions')
    else:
        require(isinstance(issues, list) and all(isinstance(key, str) and key.strip() for key in issues),
                'EXCEPTION_IDS_OR_NULL_REQUIRED')
        if issues:
            broken['unresolved_exceptions'] = len(set(issues))
    if broken:
        status = 'HOLD_FOR_RECONCILIATION'
    elif missing or not all(counts.values()):
        status = 'INCONCLUSIVE'
    else:
        status = 'LINKS_RECONCILED'
    return {'method': 'forward-registers-1', 'status': status, 'reference_counts': counts,
            'unavailable_registers': missing, 'differences': broken, 'matched_fill_parent_count': executed,
            'limits': 'Supplied identities and declared accounting exceptions only. Source completeness, amounts, sample adequacy and strategy quality require separate evidence.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('registers', help='One variant and window as described in references/strategy-evaluation.md')
    try:
        print(json.dumps(assess(strict_json(read(parser.parse_args().registers))), sort_keys=True))
    except (ValueError, OSError, TypeError) as exc:
        parser.exit(2, str(exc) + '\n')
