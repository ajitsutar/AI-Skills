"""Source-bound exchange-notice chronology; no live status or broker authority.

Complete retained JSON collections are filtered before latest selection. A
publication-only reconstruction never invents missing observation timestamps.
"""
import argparse
import json
from pathlib import Path

from news_evidence import decode, digest, pointer, read_source, timestamp

METHOD = 'retained-halt-review-1.0.0'
OBSERVATION_FIELDS = ('observed_at', 'first_seen_at', 'first_observed_at')
SCHEDULE_FIELDS = ('feed_dateline', 'quote_resume_at', 'trade_resume_at')
MAX_MESSAGES = 10000


def require(condition, code):
    if not condition:
        raise ValueError(code)


def keys(obj, allowed, required, code):
    require(isinstance(obj, dict) and not set(obj) - set(allowed) and
            set(required) <= set(obj), code)


def text(value, code):
    require(isinstance(value, str) and bool(value.strip()), code)
    return value


def source_document(reference, root):
    keys(reference, ('path', 'sha256'), ('path', 'sha256'), 'EXACT_SOURCE_REFERENCE_REQUIRED')
    return decode(read_source(root, reference))


def exact_clock(value, name):
    require(isinstance(value, str), name + '_TIMESTAMP_REQUIRED')
    try:
        return timestamp(value)
    except (ValueError, OverflowError, TypeError) as exc:
        raise ValueError(name + '_INVALID_TIMEZONE_AWARE_TIMESTAMP') from exc


def schedule(value, cutoff):
    return {'scheduled_at': value,
            'relative_to_cutoff': 'UNKNOWN' if value is None else
            'BEFORE' if timestamp(value) < cutoff else 'AT' if timestamp(value) == cutoff else 'AFTER',
            'actual_activity_verified': False}


def select_view(rows, cutoff, observed):
    eligible, excluded = [], []
    for row in rows:
        reasons = []
        if timestamp(row['published_at']) > cutoff:
            reasons.append('PUBLICATION_AFTER_CUTOFF')
        if observed:
            known = list(row['observation_clocks'].values())
            if not known:
                reasons.append('OBSERVATION_UNKNOWN')
            elif max(timestamp(value) for value in known) > cutoff:
                reasons.append('OBSERVATION_AFTER_CUTOFF')
        if reasons:
            excluded.append({'message_id': row['message_id'], 'source_pointer': row['source_pointer'],
                             'reasons': reasons})
        else:
            eligible.append(row)
    # Source publication orders notices. A late retrieval does not rewrite
    # publication order or turn an older notice into the latest exchange update.
    latest = None
    if eligible:
        newest = max(timestamp(row['published_at']) for row in eligible)
        tied = [row for row in eligible if timestamp(row['published_at']) == newest]
        require(len(tied) == 1, 'AMBIGUOUS_LATEST_NOTICE_AT_EQUAL_PUBLICATION')
        latest = tied[0]
    result = {
        'basis': 'SOURCE_PUBLICATION_AND_OBSERVATION' if observed else 'SOURCE_PUBLICATION_ONLY',
        'scope': 'Retained source clock selection; not independently verified availability.' if observed else
                 'Publication-only reconstruction; actual point-in-time observation is not established.',
        'eligible_message_ids': [row['message_id'] for row in eligible],
        'excluded': excluded,
        'selected_message_id': latest['message_id'] if latest else None,
        'selected_source_pointer': latest['source_pointer'] if latest else None,
        'selected_notice': latest,
        'quote_resumption': schedule(latest['quote_resume_at'] if latest else None, cutoff),
        'trade_resumption': schedule(latest['trade_resume_at'] if latest else None, cutoff),
        'announcement_state': 'NO_ELIGIBLE_NOTICE' if latest is None else
                              'TRADE_RESUMPTION_SCHEDULE_IN_SELECTED_NOTICE' if latest['trade_resume_at'] is not None else
                              'NO_TRADE_RESUMPTION_ANNOUNCEMENT_IN_SELECTED_NOTICE',
        'trades_observed': None, 'broker_clearance': None, 'execution_authorized': False,
    }
    return result


def review(request, root):
    """Review the entire declared collection without row selection or overrides."""
    keys(request, ('source', 'collection_pointer', 'as_of'),
         ('source', 'collection_pointer', 'as_of'), 'HALT_REVIEW_REQUEST_FIELDS')
    document = source_document(request['source'], root)
    require(isinstance(document, dict), 'HALT_SOURCE_OBJECT_REQUIRED')
    symbol = text(document.get('symbol'), 'SOURCE_SYMBOL_REQUIRED')
    exchange = document.get('exchange')
    if exchange is not None:
        text(exchange, 'SOURCE_EXCHANGE_REQUIRED')
    location = request['collection_pointer']
    require(isinstance(location, str) and location.startswith('/') and location != '/',
            'FULL_COLLECTION_POINTER_REQUIRED')
    # Identity belongs to the same source object that contains the collection.
    # A nested collection may have its own symbol/exchange context; this bounded
    # adapter does not silently substitute the root's identity for that context.
    require(location.count('/') == 1, 'TOP_LEVEL_MESSAGE_COLLECTION_REQUIRED')
    messages = pointer(document, location)
    require(isinstance(messages, list) and 0 < len(messages) <= MAX_MESSAGES,
            'NONEMPTY_BOUNDED_MESSAGE_COLLECTION_REQUIRED')
    cutoff_spec = request['as_of']
    keys(cutoff_spec, ('source', 'pointer'), ('source', 'pointer'), 'SOURCE_BOUND_AS_OF_REQUIRED')
    require(isinstance(cutoff_spec['pointer'], str) and
            cutoff_spec['pointer'].rsplit('/', 1)[-1] == 'as_of', 'AS_OF_ROLE_BINDING_REQUIRED')
    cutoff_doc = source_document(cutoff_spec['source'], root)
    cutoff_value = pointer(cutoff_doc, cutoff_spec['pointer'])
    cutoff = exact_clock(cutoff_value, 'AS_OF')
    rows, ids, halt_instants = [], set(), set()
    for index, message in enumerate(messages):
        require(isinstance(message, dict), 'MESSAGE_OBJECT_REQUIRED')
        identifier = text(message.get('message_id'), 'MESSAGE_ID_REQUIRED')
        require(identifier not in ids, 'DUPLICATE_MESSAGE_ID')
        ids.add(identifier)
        require(message.get('symbol', symbol) == symbol, 'MESSAGE_SYMBOL_MISMATCH')
        require(message.get('exchange', exchange) == exchange, 'MESSAGE_EXCHANGE_MISMATCH')
        publication = exact_clock(message.get('published_at'), 'PUBLICATION')
        halt = exact_clock(message.get('halt_event_time'), 'HALT_EVENT')
        halt_instants.add(halt)
        reason = text(message.get('reason'), 'SOURCE_REASON_REQUIRED')
        observations = {}
        for name in OBSERVATION_FIELDS:
            value = message.get(name)
            if value is not None:
                observed = exact_clock(value, name.upper())
                require(observed >= publication, 'OBSERVATION_PRECEDES_PUBLICATION')
                observations[name] = value
        for name in SCHEDULE_FIELDS:
            value = message.get(name)
            if value is not None:
                instant = exact_clock(value, name.upper())
                if name != 'feed_dateline':
                    require(instant >= halt, 'RESUMPTION_PRECEDES_HALT_EVENT')
        quote, trade = message.get('quote_resume_at'), message.get('trade_resume_at')
        require(not (quote is not None and trade is not None) or timestamp(trade) >= timestamp(quote),
                'TRADE_RESUMPTION_PRECEDES_QUOTE_RESUMPTION')
        rows.append({'message_id': identifier, 'source_pointer': location + '/' + str(index),
                     'source_record_sha256': digest(json.dumps(message, sort_keys=True, separators=(',', ':')).encode()),
                     'symbol': symbol, 'exchange': exchange, 'reason': reason,
                     'published_at': message['published_at'], 'halt_event_time': message['halt_event_time'],
                     'feed_dateline': message.get('feed_dateline'), 'quote_resume_at': quote,
                     'trade_resume_at': trade, 'observation_clocks': observations})
    require(len(halt_instants) == 1, 'MULTIPLE_HALT_EPISODES_REQUIRE_SEPARATE_REVIEW')
    rows.sort(key=lambda row: (timestamp(row['published_at']), row['message_id']))
    result = {
        'method': METHOD, 'as_of': cutoff_value, 'as_of_binding': cutoff_spec,
        'source': request['source'], 'collection_pointer': location,
        'collection_count': len(messages), 'symbol': symbol, 'exchange': exchange,
        'all_notices': rows,
        'publication_view': select_view(rows, cutoff, False),
        'observed_view': select_view(rows, cutoff, True),
        'clock_roles': {'feed_dateline': 'RETAINED_FEED_LABEL_NOT_EVENT_OR_PUBLICATION',
                        'halt_event_time': 'SOURCE_STATED_HALT_EVENT_TIME',
                        'quote_resume_at': 'SOURCE_STATED_QUOTE_SCHEDULE_NOT_TRADE_EXECUTION',
                        'trade_resume_at': 'SOURCE_STATED_TRADE_SCHEDULE_NOT_OBSERVED_EXECUTION'},
        'broker_state': 'UNKNOWN_NOT_ASSESSED', 'source_authenticity_verified': False,
        'live_exchange_status_verified': False, 'observed_execution_verified': False,
        'execution_authorized': False, 'new_skill_gate_created': False,
        'limitations': [
            'This checks the complete declared retained collection, not the completeness of an exchange feed.',
            'Source field roles and bytes are bound; authenticity and semantic truth are not independently verified.',
            'Scheduled times, even when elapsed, do not establish actual quoting, trades or broker clearance.',
            'Exchange and broker restrictions are external facts; this report creates no new execution permission or skill gate.',
        ],
        'input_sha256': digest(json.dumps(request, sort_keys=True).encode()),
        'implementation_sha256': digest(Path(__file__).read_bytes()),
    }
    return result


def brief_observations(request, root):
    """Render source-attributed halt facts for an authored brief from mixed event and quote files."""
    keys(request, ('events', 'quotes', 'symbol'), ('events', 'quotes', 'symbol'), 'HALT_BRIEF_REQUEST_FIELDS')
    symbol = text(request['symbol'], 'SOURCE_SYMBOL_REQUIRED')
    events = source_document(request['events'], root)
    tape = source_document(request['quotes'], root)
    require(isinstance(events, dict) and isinstance(events.get('observations'), list)
            and len(events['observations']) <= MAX_MESSAGES, 'EVENT_OBSERVATIONS_REQUIRED')
    require(isinstance(tape, dict) and isinstance(tape.get('quotes'), list)
            and len(tape['quotes']) <= MAX_MESSAGES, 'QUOTE_COLLECTION_REQUIRED')
    cutoff = exact_clock(tape.get('scenario_clock'), 'AS_OF')
    quote_times = []
    for i, quote in enumerate(tape['quotes']):
        require(isinstance(quote, dict) and isinstance(quote.get('symbol'), str), 'QUOTE_IDENTITY_REQUIRED')
        if quote['symbol'] == symbol and exact_clock(quote.get('quote_time'), 'QUOTE') <= cutoff:
            quote_times.append({'pointer': f'/quotes/{i}', 'quote_time': quote['quote_time']})
    halts, other_observations = [], []
    for i, event in enumerate(events['observations']):
        require(isinstance(event, dict) and isinstance(event.get('symbol'), str), 'EVENT_IDENTITY_REQUIRED')
        if event['symbol'] != symbol:
            continue
        published = exact_clock(event.get('published_at'), 'PUBLICATION')
        if published > cutoff:
            continue
        location = f'/observations/{i}'
        if event.get('event_kind') != 'exchange_halt':
            other_observations.append(location)
            continue
        halted = exact_clock(event.get('halt_time'), 'HALT_EVENT')
        require(halted <= published, 'REPORTED_HALT_AFTER_PUBLICATION')
        reason = text(event.get('reason'), 'SOURCE_REASON_REQUIRED')
        fields = {'source_pointer': location, 'published_at': event['published_at'],
                  'halt_time': event['halt_time'], 'reason': reason}
        sentences = [f"The source reported a halt for {symbol} at {event['halt_time']} ({reason})."]
        for activity in ('quote', 'trade'):
            scheduled = event.get(activity + '_resume_at')
            actual = event.get(activity + '_resumed_at')
            if scheduled is not None:
                require(exact_clock(scheduled, 'SCHEDULE') >= halted, 'SCHEDULE_BEFORE_HALT')
                sentences.append(f"The source scheduled {activity} resumption for {scheduled}.")
            if actual is not None:
                require(halted <= exact_clock(actual, 'REPORTED_RESUMPTION') <= published,
                        'REPORTED_RESUMPTION_OUTSIDE_HALT_PUBLICATION_INTERVAL')
                sentences.append(f"The source reports actual {activity} resumption at {actual}.")
            else:
                sentences.append(f"Actual {activity} resumption is unconfirmed in this record.")
            fields[activity + '_resume_at'] = scheduled
            fields[activity + '_resumed_at'] = actual
        fields['statement'] = ' '.join(sentences)
        halts.append(fields)
    halts.sort(key=lambda row: exact_clock(row['published_at'], 'PUBLICATION'))
    quote_times.sort(key=lambda row: exact_clock(row['quote_time'], 'QUOTE'))
    statements = [row['statement'] for row in halts]
    if not halts:
        statements.append(f"No eligible exchange-halt observation for {symbol} appears in this collection.")
    if quote_times:
        statements.append(f"The latest supplied {symbol} quote through the cutoff is timestamped {quote_times[-1]['quote_time']}.")
    statements.append('Quote timestamps alone establish neither resumption nor a continuing halt. Current exchange and broker status require separate evidence.')
    return {'method': 'halt-observation-brief-1', 'symbol': symbol, 'as_of': tape['scenario_clock'],
            'sources': {'events': request['events'], 'quotes': request['quotes']},
            'halt_observations': halts, 'eligible_quote_times': quote_times,
            'other_eligible_symbol_observation_pointers': other_observations,
            'current_exchange_status': None, 'broker_tradability': None,
            'statement': ' '.join(statements)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request')
    parser.add_argument('source_root')
    parser.add_argument('output')
    parser.add_argument('--brief-observations', action='store_true',
                        help='Render the halt-status passage and fields for a supplied intraday brief.')
    args = parser.parse_args(argv)
    request = decode(Path(args.request).read_bytes())
    result = brief_observations(request, args.source_root) if args.brief_observations else review(request, args.source_root)
    # Exclusive creation preserves any earlier result, including a failed attempt.
    with Path(args.output).open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    summary = {'method': result['method'], 'output': args.output}
    if args.brief_observations:
        summary['statement'] = result['statement']
    else:
        summary.update(publication_selected_message_id=result['publication_view']['selected_message_id'],
                       observed_selected_message_id=result['observed_view']['selected_message_id'])
    print(json.dumps(summary))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
