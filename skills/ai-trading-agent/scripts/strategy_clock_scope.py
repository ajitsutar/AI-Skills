"""Clock provenance for a strategy selected by an original single-record request."""

def selected_clocks(record, selection, evaluation, pointers, lookup):
    if not isinstance(pointers, dict) or set(pointers) - {'decision', 'holding_period', 'horizon'}:
        raise ValueError('CLOCK_ROLES_MUST_IDENTIFY_SELECTED_STRATEGY_FIELDS')
    fields = {}
    for role in ('decision', 'holding_period', 'horizon'):
        path = pointers.get(role)
        if path is None:
            if role not in record:
                continue
            path = '/' + role
        if not isinstance(path, str) or not path.startswith('/'):
            raise ValueError('CLOCK_POINTER_RELATIVE_TO_SELECTED_RECORD_REQUIRED')
        value = lookup(record, path)
        if value is None:
            continue
        fields[role] = {'record_pointer': path, 'value': value}
    return {'source_path': selection['source_path'], 'source_sha256': selection['source_sha256'],
            'selected_record': selection['pointer'], 'decision_and_holding': fields,
            'registered_evaluation': evaluation}


def limitations(row):
    scope = row['clock_scope']
    return [row['limits'],
            f"Strategy clock evidence comes from {scope['source_path']}#{scope['selected_record']}. "
            "A decision interval, a position holding rule and the evaluation dates describe different "
            "clocks. Enclosing or sibling records supply no additional mandate for this selection."]
