"""Build and replay a complete intraday brief from retained session, quote, event and volume records."""
import argparse
import csv
from datetime import date, datetime
from decimal import Decimal
import io
import json
from pathlib import Path
import re

from halt_review import brief_observations, exact_clock, keys, require, text
from news_evidence import decode, digest, read_source
from response_contract import audit, declared_fields
from strategy_intake import original_contract

ROLES = {'prompt', 'session', 'universe', 'scope', 'events', 'quotes', 'history'}
METHOD = 'retained-intraday-brief-3'


def number(value, field):
    require(not isinstance(value, bool) and value is not None, field + '_NUMBER_REQUIRED')
    result = Decimal(str(value))
    require(result.is_finite() and result >= 0, field + '_NONNEGATIVE_FINITE_REQUIRED')
    return result


def quoted_liquidity(quote):
    """This tape profile supports share-count sizes and a count of displayed book levels."""
    mapped = {}
    for name in ('bid_size_shares', 'ask_size_shares', 'book_depth_levels'):
        value = quote.get(name)
        mapped[name] = None if value is None else str(number(value, name))
    if mapped['book_depth_levels'] is not None:
        levels = Decimal(mapped['book_depth_levels'])
        require(levels == levels.to_integral_value(), 'INTEGRAL_BOOK_DEPTH_REQUIRED')
    require(not (set(quote) & {'bid_size','ask_size','depth','order_book','market_depth','book_depth'}),
            'UNMAPPED_QUOTE_SIZE_OR_DEPTH_REVIEW_ORIGINAL_UNITS')
    return mapped


def quote_metrics(quotes, symbol, cutoff, currency):
    eligible = []
    for i, row in enumerate(quotes):
        if row['symbol'] == symbol:
            clock = exact_clock(row.get('quote_time'), 'QUOTE')
            if clock <= cutoff:
                eligible.append((clock, i, row))
    if not eligible:
        return None
    clock = max(t for t, _, _ in eligible)
    latest = [(i, row) for t, i, row in eligible if t == clock]
    require(len(latest) == 1, 'AMBIGUOUS_LATEST_QUOTE')
    i, row = latest[0]
    require(row.get('currency') == currency, 'QUOTE_SECURITY_CURRENCY_MISMATCH')
    bid, ask = number(row['bid'], 'BID'), number(row['ask'], 'ASK')
    require(0 < bid <= ask, 'POSITIVE_NONCROSSED_TWO_SIDED_QUOTE_REQUIRED')
    mid = (bid + ask) / 2
    return {'pointer':f'/quotes/{i}', 'quote_time':row['quote_time'],
            'age_seconds':(cutoff-clock).total_seconds(), 'currency':currency,
            'bid':str(bid), 'ask':str(ask), 'midpoint':str(mid), 'spread':str(ask-bid),
            'spread_bps':str((ask-bid)*10000/mid), **quoted_liquidity(row)}


def historical_volume(history, symbol, session_date):
    days = {}
    for row in history:
        if row['symbol'] != symbol:
            continue
        trading_date = date.fromisoformat(row['session_date'])
        if trading_date >= session_date:
            continue
        require(trading_date not in days, 'DUPLICATE_VOLUME_SESSION')
        shares = number(row['shares_volume'], 'SHARES')
        days[trading_date] = (shares, shares * number(row['unadjusted_close_usd'], 'CLOSE_USD'))
    if not days:
        return {'sessions':0}
    return {'sessions':len(days), 'start':min(days).isoformat(), 'end':max(days).isoformat(),
            'mean_shares':str(sum(x[0] for x in days.values())/len(days)),
            'mean_dollar_volume_usd':str(sum(x[1] for x in days.values())/len(days))}


def published_events(document, symbol, cutoff):
    rows = []
    for i, event in enumerate(document['observations']):
        if event['symbol'] != symbol or exact_clock(event['published_at'], 'PUBLICATION') > cutoff:
            continue
        kind = text(event.get('event_kind'), 'EVENT_KIND_REQUIRED')
        # A later announced event or earnings window can be known at the cutoff.
        summary = [f"Published {event['published_at']} ({kind})."]
        if event.get('body') is not None:
            summary.append(text(event['body'], 'EVENT_BODY_REQUIRED'))
        if event.get('earnings_release') is not None:
            exact_clock(event['earnings_release'], 'EARNINGS')
            summary.append('Reported earnings release: ' + event['earnings_release'] + '.')
        window = event.get('earnings_release_window')
        if window is not None:
            require(isinstance(window, list) and len(window)==2 and
                    date.fromisoformat(window[0]) <= date.fromisoformat(window[1]), 'EARNINGS_WINDOW_REQUIRED')
            summary.append('Reported earnings window: ' + ' through '.join(window) + '.')
        if kind == 'exchange_status':
            status_clock = exact_clock(event.get('status_as_of'), 'EXCHANGE_STATUS')
            require(status_clock <= exact_clock(event['published_at'], 'PUBLICATION'), 'STATUS_AFTER_PUBLICATION')
            status = text(event.get('status'), 'STATUS_VALUE_REQUIRED')
            summary.append(f"Venue status was reported as {status} at {event['status_as_of']}.")
        rows.append({'pointer':f'/observations/{i}', 'record':event, 'statement':' '.join(summary)})
    return rows


def catalyst_assessment(events, session_day, clock, source_offset):
    """Classify what the retained publication establishes; market impact is unobserved."""
    reported, pending, earlier, unresolved, calendar = [], [], [], [], []
    kinds = []
    as_of = exact_clock(clock, 'AS_OF')
    for item in events:
        record, pointer = item['record'], item['pointer']
        kind = record['event_kind']
        pub = exact_clock(record['published_at'], 'PUBLICATION')
        this_session = pub.astimezone(source_offset).date() == session_day
        disposition = record.get('event_status')
        if disposition in ('pending','rumor','unconfirmed') or (
                kind == 'exchange_halt' and record.get('reason') == 'pending_news'):
            pending.append(pointer)
        elif disposition in ('scheduled','planned'):
            calendar.append(pointer)
        elif kind in ('issuer_calendar','earnings_calendar') and record.get('earnings_released_at') is not None:
            actual = exact_clock(record['earnings_released_at'], 'REPORTED_EARNINGS_RELEASE')
            require(actual <= pub, 'ACTUAL_EARNINGS_RELEASE_AFTER_PUBLICATION')
            if this_session and actual.astimezone(source_offset).date() == session_day:
                reported.append(pointer)
                kinds.append('reported earnings release at ' + record['earnings_released_at'])
            else:
                earlier.append(pointer)
        elif kind in (
                'issuer_calendar','earnings_calendar','exchange_halt','exchange_status'):
            calendar.append(pointer)
        elif kind == 'earnings_release' and record.get('earnings_release') and (
                exact_clock(record['earnings_release'], 'EARNINGS') > as_of):
            calendar.append(pointer)
        elif kind in ('contract_award','earnings_release','guidance_update','regulatory_decision',
                      'merger_announcement','dividend_announcement','product_launch') and (
                disposition in (None,'reported','confirmed','published') and record.get('body')):
            (reported if this_session else earlier).append(pointer)
            if this_session:
                kinds.append(kind.replace('_',' '))
        else:
            unresolved.append(pointer)
    if reported:
        state = 'SESSION_DATE_DEVELOPMENT_REPORTED'
        assessment = 'The supplied records report a development published on the supplied local session date (' + ', '.join(kinds) + '). Its price impact is unverified.'
    elif unresolved:
        state = 'SUBSTANCE_OR_FRESHNESS_UNRESOLVED'
        assessment = 'The supplied records leave the presence of a fresh substantive catalyst unresolved.'
    else:
        state = 'NO_CONFIRMED_FRESH_CATALYST_SUPPLIED'
        assessment = 'No confirmed fresh catalyst was supplied for this symbol.'
    if pending:
        assessment += ' The source flags pending or unconfirmed news. Its substance remains unconfirmed in those records.'
    if earlier:
        assessment += ' Earlier reported developments remain relevant context; their ongoing impact is unknown.'
    if unresolved and reported:
        assessment += ' Additional event records have unclassified or uncertain catalyst significance.'
    if calendar and not (reported or unresolved or pending or earlier):
        assessment += ' The available calendar or status observations do not independently establish a new substantive development.'
    return {'as_of':clock,'freshness_basis':'publication on the supplied local session date through the cutoff',
            'state':state,'session_date_reported':reported,'prior_reported':earlier,
            'pending_or_unconfirmed':pending,'calendar_or_status':calendar,'unclassified':unresolved,
            'statement':f'Catalyst assessment through {clock}: {assessment}'}


def liquidity_text(quote, history):
    if quote:
        currency = quote['currency']
        quote_facts = (f"At {quote['quote_time']} ({quote['age_seconds']:g} seconds before the cutoff), "
                       f"bid/ask was {quote['bid']}/{quote['ask']} {currency}, midpoint {quote['midpoint']}, "
                       f"spread {quote['spread']} {currency} ({Decimal(quote['spread_bps']):.2f} bps).")
        sizes = [f"{side} size " + ('unavailable' if quote[side+'_size_shares'] is None else
                                    quote[side+'_size_shares'] + ' displayed shares') for side in ('bid','ask')]
        depth = quote['book_depth_levels']
        depth_text = 'book depth unavailable' if depth is None else depth + ' displayed book levels'
        display = 'At that quote: ' + ', '.join([*sizes, depth_text]) + '.'
    else:
        quote_facts = 'No eligible two-sided quote for this symbol was supplied through the cutoff.'
        display = 'Bid size, ask size and book depth are unavailable for this snapshot.'
    if history['sessions']:
        historical = (f"Across {history['sessions']} supplied prior sessions ({history['start']} through {history['end']}), "
                      f"mean volume was {Decimal(history['mean_shares']):,.2f} shares/session and mean daily "
                      f"unadjusted close × shares was USD {Decimal(history['mean_dollar_volume_usd']):,.2f}/session.")
    else:
        historical = 'No completed prior-session volume observations were supplied for this symbol.'
    return ' '.join((quote_facts, display, historical, 'Historical volume and quote snapshots do not measure current traded volume or confirm the quantity a new order would fill.'))


def symbol_limits(row):
    """Describe only coverage gaps in this symbol's observations through the cutoff."""
    gaps = []
    quote = row['quote']
    if quote is None:
        gaps.append('an eligible two-sided quote')
    else:
        for field, label in (('bid_size_shares','displayed bid size'),
                             ('ask_size_shares','displayed ask size'),
                             ('book_depth_levels','displayed book depth')):
            if quote[field] is None:
                gaps.append(label)
    if not row['history']['sessions']:
        gaps.append('prior-session volume history')
    if row['reported_venue_status_at_cutoff'] is None:
        gaps.append('venue status as of the cutoff')
    if row['broker_tradability'] is None:
        gaps.append('broker tradability')
    limits = [f"{row['symbol']}: the supplied records do not establish {', '.join(gaps)}."] if gaps else []
    for halt in row['halt_review']['halt_observations']:
        missing = [leg for leg in ('quote','trade') if halt[leg+'_resumed_at'] is None]
        if missing:
            limits.append(f"{row['symbol']}: the halt record at {halt['halt_time']} leaves actual "
                          + ' and '.join(missing) + ' resumption unconfirmed.')
    return limits


def render(request, root):
    keys(request, ('symbols','sources','metadata'), ('symbols','sources'), 'INTRADAY_REQUEST_FIELDS')
    symbols = request['symbols']
    require(isinstance(symbols,list) and symbols and all(isinstance(s,str) and s.strip()==s and s for s in symbols)
            and len(set(symbols))==len(symbols),'DISTINCT_REQUESTED_SYMBOLS_REQUIRED')
    refs = request['sources']
    keys(refs, ROLES | {'context','response_contract'}, ROLES, 'INTRADAY_SOURCE_BINDINGS')
    blobs = {}
    for role, reference in refs.items():
        keys(reference, ('path','sha256'), ('path','sha256'), 'EXACT_SOURCE_REFERENCE_REQUIRED')
        blobs[role] = read_source(root, reference)
    require(len({r['path'] for r in refs.values()})==len(refs),'DISTINCT_SOURCE_PATHS_REQUIRED')
    prompt = text(blobs['prompt'].decode('utf-8-sig').strip(),'ORIGINAL_PROMPT_REQUIRED')
    docs = {key:decode(blobs[key], exact_numbers=True) for key in ('session','scope','universe','quotes','events')}
    session, tape, events = docs['session'], docs['quotes'], docs['events']
    named = {r['symbol'] for r in docs['universe']['rows']
             if re.search(r'(?<![\w.-])' + re.escape(r['symbol']) + r'(?![\w-]|\.[\w])',prompt)}
    require(named == set(symbols),'REQUEST_NAMED_SECURITY_SCOPE_MISMATCH')
    if any(k in doc for doc in (tape,events,session)
           for k in ('bars','trades','order_book','market_depth','entry_signal','intraday_volume','relative_volume')):
        raise ValueError('ADDITIONAL_INTRADAY_DATA_REQUIRES_BROADER_ANALYSIS')
    cutoff = exact_clock(session['scenario_clock'],'CLOCK')
    require(cutoff == exact_clock(tape['scenario_clock'],'QUOTE_CLOCK'), 'SESSION_QUOTE_CLOCK_MISMATCH')
    if docs['scope'].get('as_of') is not None:
        require(cutoff == exact_clock(docs['scope']['as_of'],'SOURCE_SCOPE_CUTOFF'),'SOURCE_SCOPE_CLOCK_MISMATCH')
    opening = exact_clock(session['regular_open'],'SESSION_OPEN')
    closing = exact_clock(session['regular_close'],'SESSION_CLOSE')
    require(opening < closing, 'INVALID_SESSION')
    retained_open = datetime.fromisoformat(session['regular_open'].replace('Z','+00:00'))
    retained_close = datetime.fromisoformat(session['regular_close'].replace('Z','+00:00'))
    session_date = date.fromisoformat(session['session_date'])
    require(retained_open.date()==retained_close.date()==session_date and
            retained_open.utcoffset()==retained_close.utcoffset(),'SAME_LOCAL_DATE_AND_OFFSET_SESSION_REQUIRED')
    market = 'during' if opening <= cutoff < closing else ('before' if cutoff<opening else 'after')
    local = cutoff.astimezone(retained_open.tzinfo).isoformat()
    require(exact_clock(docs['universe']['as_of'],'UNIVERSE') <= cutoff,'FUTURE_SECURITY_MASTER')
    history = csv.DictReader(io.StringIO(blobs['history'].decode('utf-8-sig')))
    require(history.fieldnames and set(history.fieldnames) >= {'symbol','session_date','unadjusted_close_usd','shares_volume'}
            and len(set(history.fieldnames))==len(history.fieldnames),'VOLUME_HISTORY_COLUMNS')
    volumes = list(history)
    require(tape.get('broker_tradability') is None and events.get('broker_state') is None,
            'SUPPLIED_BROKER_FACTS_REQUIRE_SEPARATE_COVERAGE')
    results=[]
    for symbol in symbols:
        securities = [r for r in docs['universe']['rows'] if r['symbol']==symbol]
        require(len(securities)==1,'SINGLE_MATCHING_SECURITY_REQUIRED')
        security = securities[0]
        halt = brief_observations(dict(symbol=symbol,events=refs['events'],quotes=refs['quotes']),root)
        quote = quote_metrics(tape['quotes'],symbol,cutoff,security['currency'])
        history_result = historical_volume(volumes,symbol,session_date)
        event_rows = published_events(events,symbol,cutoff)
        catalyst = catalyst_assessment(event_rows,session_date,session['scenario_clock'],retained_open.tzinfo)
        current_reports = [item for item in event_rows if item['record']['event_kind']=='exchange_status'
                           and exact_clock(item['record']['status_as_of'],'EXCHANGE_STATUS')==cutoff]
        current_states = {item['record']['status'] for item in current_reports}
        require(len(current_states)<=1, 'CONFLICTING_VENUE_STATUS_AT_CUTOFF')
        setup = 'No setup is confirmed by the supplied quote, dated events and prior-session history alone.'
        results.append({'symbol':symbol,'security':security,'quote':quote,'history':history_result,
                        'events':event_rows,'catalyst_assessment':catalyst,'halt_review':halt,'liquidity_statement':liquidity_text(quote,history_result),
                        'reported_venue_status_at_cutoff':next(iter(current_states),None),
                        'setup_statement':setup,'broker_tradability':None})
    md = ['# Intraday brief', '', f"Cutoff {session['scenario_clock']} ({local}, {session['timezone']}), "
          f"{market} the stated regular session of {session['regular_open']} to {session['regular_close']}.",'']
    if session.get('special_close_notice'):
        md.extend(['Calendar notice: ' + str(session['special_close_notice']), ''])
    limitations = []
    for key in ('scope', 'source_authenticity', 'external_acquisition'):
        if docs['scope'].get(key):
            limitations.append(str(docs['scope'][key]))
            md.extend([limitations[-1], ''])
    snapshot_limit = ('This brief uses supplied dated observations. No independent live venue or broker check was performed. '
                      'Displayed quote sizes, depth and any timestamped venue status are reported below. '
                      'Prior-session volume supplies no same-time intraday volume baseline. This snapshot profile does not '
                      'evaluate completed intraday bars, trade prints or actual fill capacity.')
    limitations.append(snapshot_limit)
    md.extend(['## Evidence limits', '', snapshot_limit, ''])
    for row in results:
        limitations.extend(symbol_limits(row))
        security = row['security']
        md.extend([f"## {row['symbol']} — {security['issuer']} ({security['exchange']})", '',
                   row['liquidity_statement'], ''])
        md.extend([event['statement'] for event in row['events']] or ['No eligible event record was supplied for this symbol.'])
        md.extend(['',row['catalyst_assessment']['statement'],'',row['halt_review']['statement'],'',row['setup_statement'],''])
    md.extend(['Setup evaluation requires a defined price/volume trigger, current evidence for it and dated venue and broker status. A quote or a scheduled resumption cannot establish tradability.'])
    metadata=request.get('metadata',{})
    keys(metadata,('case_id','run_id','runtime_model_metadata','evidence_paths'),(), 'METADATA_CANNOT_OVERRIDE_BRIEF')
    first=('\n'.join(md)+'\n').encode()
    response={**metadata,'method':METHOD,'candidate_version':(Path(__file__).resolve().parents[1]/'VERSION').read_text().strip(),
              'request':prompt,'source_bindings':refs,'input_hashes':{r['path']:r['sha256'] for r in refs.values()},
              'session':session,'local_clock':local,'session_position':market,'symbols':results,
              'rows':results,'limitations':limitations,
              'first_response_sha256':digest(first)}
    prompt_dir = (Path(root).absolute() / refs['prompt']['path']).parent
    contract = original_contract(blobs['prompt'], prompt_dir)
    explicit = blobs.get('response_contract')
    if explicit is not None:
        if contract is not None:
            require(set(declared_fields(explicit)) == set(declared_fields(contract)),
                    'CONFLICTING_ORIGINAL_RESPONSE_DECLARATIONS')
        contract = explicit
    if contract is not None:
        checked = audit(contract, response)
        fields = checked['required_fields_present']
        if 'case_id' in fields:
            text(metadata['case_id'], 'DECLARED_CASE_ID_REQUIRED')
        if 'runtime_model_metadata' in fields:
            require(isinstance(metadata['runtime_model_metadata'],dict) and metadata['runtime_model_metadata'],
                    'DECLARED_RUNTIME_METADATA_REQUIRED')
        if 'evidence_paths' in fields:
            paths = metadata['evidence_paths']
            require(isinstance(paths,list) and paths and all(isinstance(p,str) and p.strip() for p in paths),
                    'DECLARED_EVIDENCE_PATHS_REQUIRED')
        response['response_contract'] = checked
    return {'first-response.md':first,'response.json':(json.dumps(response,indent=2,ensure_ascii=False,default=str)+'\n').encode()}


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('operation',choices=('build','verify'))
    cli.add_argument('request',type=Path)
    cli.add_argument('source_root',type=Path)
    cli.add_argument('output',type=Path)
    args=cli.parse_args()
    files=render(decode(args.request.read_bytes()),args.source_root)
    out=args.output.absolute()
    require(out == out.resolve() and not any(p.is_symlink() or
            (p.exists() and getattr(p.lstat(),'st_file_attributes',0) & 1024)
            for p in (out,*out.parents)), 'REDIRECTED_OUTPUT_PATH')
    if args.operation=='build':
        out.mkdir()  # Exclusive output reservation. Retain any interrupted partial write for inspection.
        for name, content in files.items():
            with (out/name).open('xb') as stream:
                stream.write(content)
    require(out.is_dir() and not out.is_symlink() and {p.name for p in out.iterdir()}==set(files)
            and all((out/n).is_file() and not (out/n).is_symlink() and (out/n).read_bytes()==b for n,b in files.items()),
            'INTRADAY_DELIVERY_DIFFERS_FROM_SOURCE_REPLAY')
    print(json.dumps({'status':'SOURCE_REPLAY_VERIFIED','files':{n:digest(b) for n,b in files.items()}}))


if __name__=='__main__':
    main()
