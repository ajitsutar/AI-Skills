"""Model funded trades and cash availability on an explicit single-currency business calendar."""
from datetime import date, datetime, timezone
from decimal import Context, Decimal, localcontext
import re
from zoneinfo import ZoneInfo

from quant_common import require, timestamp


def settlement_lag(source):
    explicit = source.get('settlement_lag_business_days')
    require(explicit is None or type(explicit) is int, 'INTEGER_SETTLEMENT_LAG_REQUIRED')
    rule = source.get('settlement_rule')
    if rule is not None:
        match = re.fullmatch(
            r'(one|two|three|[1-9][0-9]*) (?:test |listed )?business days? after fill'
            r'(?:; unfilled sales are not confirmed credits)?[.]?', str(rule).strip(), re.IGNORECASE)
        require(match, 'UNRECOGNIZED_SETTLEMENT_RULE_SUPPLY_NORMALIZED_POSTINGS')
        word = match[1].lower()
        stated = int(word) if word.isdecimal() else {'one': 1, 'two': 2, 'three': 3}[word]
        require(explicit is None or explicit == stated, 'CONFLICTING_SETTLEMENT_LAGS')
        explicit = stated
    require(type(explicit) is int and explicit > 0, 'POSITIVE_LISTED_DAY_LAG_REQUIRED_OR_USE_EXPLICIT_POSTING_TIMES')
    return explicit


def trade_cash_plan(source):
    from planning_alignment import amount

    money = [amount(source[k]) for k in ('settled_cash','reservations','floor')]
    money.extend(amount(e['cash_effect']) for e in source['events'])
    precision = max(28, max(x.adjusted() for x in money) - min(x.as_tuple().exponent for x in money) + len(str(len(money))) + 6)
    with localcontext(Context(prec=precision)):
        return _trade_cash_plan(source)


def _trade_cash_plan(source):
    from planning_alignment import amount, _date_ambiguous_cash_plan, finish

    currency = source['currency']
    calendar = source.get('business_dates', source.get('test_business_dates'))
    require(isinstance(calendar, list) and calendar and all(isinstance(t, str) and date.fromisoformat(t).isoformat()==t for t in calendar)
            and sorted(set(calendar)) == calendar, 'ORDERED_LISTED_BUSINESS_DATES_REQUIRED')
    if 'business_dates' in source and 'test_business_dates' in source:
        require(calendar == source['test_business_dates'], 'CONFLICTING_BUSINESS_CALENDARS')
    lag = settlement_lag(source)
    settled = amount(source['settled_cash'], 'settled_cash')
    reserved = amount(source['reservations'], 'reservations', 0)
    floor = amount(source['floor'], 'floor', 0)
    events = source['events']
    require(isinstance(events, list) and all(isinstance(e, dict) for e in events), 'TRADE_CASH_EVENTS_REQUIRED')
    require(all(isinstance(e['id'], str) and e['id'].strip() for e in events) and
            len({e['id'] for e in events}) == len(events), 'UNIQUE_EVENT_IDS')
    require(all(set(e) <= {'id','kind','at','cash_effect','confirmed','currency','evidence'} for e in events),
            'UNMODELED_EVENT_TERMS_USE_EXPLICIT_POSTINGS')
    start = timestamp(source['as_of'])
    clocks = [datetime.fromisoformat(t.replace('Z','+00:00')) for t in [source['as_of'], *(e['at'] for e in events)]]
    zone_name = source.get('calendar_timezone')
    if zone_name in (None,'unknown'):
        offsets = {t.utcoffset() for t in clocks}
        require(len(offsets)==1 and None not in offsets, 'DECLARE_CALENDAR_TIMEZONE_FOR_MIXED_CLOCK_OFFSETS')
        zone = timezone(clocks[0].utcoffset())
        offset = clocks[0].strftime('%z')
        zone_name = offset[:3]+':'+offset[3:]
        zone_basis = 'Scenario calendar interpreted at the common offset of the supplied timestamps; no broker timezone was observed.'
    else:
        if re.fullmatch(r'[+-][0-9]{2}:[0-9]{2}', zone_name):
            zone = datetime.fromisoformat('2000-01-01T00:00:00'+zone_name).tzinfo
        else:
            zone = timezone.utc if zone_name in ('UTC','Z') else ZoneInfo(zone_name)
        zone_basis = 'Supplied calendar timezone.'
    trades = {}
    for e in events:
        require(type(e['confirmed']) is bool and e.get('currency', currency) == currency, 'EVENT_CONFIRMATION_AND_CURRENCY_REQUIRED')
        at = timestamp(e['at'])
        require(at > start, 'OPENING_ALREADY_INCLUDES_PRIOR_EVENTS')
        delta = amount(e['cash_effect'])
        kind = e['kind']
        if kind in ('planned_buy','planned_sale','buy','sale'):
            side = 'buy' if kind.endswith('buy') else 'sale'
            require(delta < 0 if side == 'buy' else delta > 0, 'TRADE_CASH_DIRECTION')
            day = at.astimezone(zone).date().isoformat()
            require(day in calendar and calendar.index(day)+lag < len(calendar), 'INSUFFICIENT_LISTED_SETTLEMENT_CALENDAR')
            trades[e['id']] = (side, calendar[calendar.index(day)+lag], delta)
        else:
            require(kind in ('withdrawal','confirmed_withdrawal','deposit','cash_credit','cash_debit','external_obligation'),
                    'UNSUPPORTED_CASH_EVENT_KIND')
            require(delta >= 0 if kind in ('deposit','cash_credit') else delta <= 0, 'CASH_EVENT_SIGN')
    require(trades, 'TRADE_EVENTS_REQUIRED_FOR_TRADE_SCHEDULE')
    def point(available):
        headroom = available-floor
        return {'available_before_floor': available, 'signed_floor_headroom': headroom, 'floor_gap': max(Decimal(0),-headroom)}
    def scenario(sides):
        legs = []
        changes = []
        def post(e, at, phase, settled_delta, reserve_delta):
            change = settled_delta-reserve_delta
            legs.append({'source_event': e['id'], 'phase': phase, 'at_or_date': at, 'settled_delta': settled_delta,
                         'trade_reservation_delta': reserve_delta, 'available_delta': change})
            if change:
                changes.append({'id':e['id'],'kind':'cash_credit' if change>0 else 'cash_debit','currency':currency,
                                'available_at':at,'amount':str(change),'confirmed':True,
                                'evidence': 'Conditional derived availability movement from '+e['id']})
        included = []
        for e in events:
            if e['id'] not in trades:
                if e['confirmed']:
                    post(e,e['at'],'confirmed_cash',amount(e['cash_effect']),Decimal(0))
                continue
            side,settle_day,delta = trades[e['id']]
            if not e['confirmed'] and side not in sides:
                continue
            included.append(e['id'])
            if side == 'buy':
                post(e,e['at'],'buy_commitment',Decimal(0),-delta)
                post(e,settle_day,'buy_settlement',delta,delta)
            else:
                post(e,e['at'],'sale_fill',Decimal(0),Decimal(0))
                post(e,settle_day,'sale_credit_on_assumed_settlement_date',delta,Decimal(0))
        normalized = {'as_of':source['as_of'],'currency':currency,'role':'hypothetical_scenario',
                      'settled_balances':{currency:str(settled)},'reservations':{currency:str(reserved)},
                      'floors':{currency:str(floor)},'events':changes}
        normalized['calendar_timezone']=zone_name
        result = _date_ambiguous_cash_plan(normalized)
        paths = {}
        for name, path in result['scenarios'].items():
            paths[name] = [{'source_event':row['id'],'source_available_at':row['source_available_at'],
                            'timing_placement':row['timing_placement'],**point(amount(row['available']))} for row in path['timeline']]
        ending_settled = settled+sum((r['settled_delta'] for r in legs),Decimal(0))
        ending_reserved = reserved+sum((r['trade_reservation_delta'] for r in legs),Decimal(0))
        ending = point(ending_settled-ending_reserved)
        for path in paths.values():
            require((path[-1]['available_before_floor'] if path else settled-reserved) == ending['available_before_floor'],
                    'AVAILABILITY_AND_SETTLEMENT_LEDGERS_DIFFER')
        return {'included_fills':included,'postings_by_source_event':legs,'availability_paths':paths,
                'ending_after_all_postings':{'settled':ending_settled,'reserved':ending_reserved,**ending},
                'cash_bounds':result['cash_bounds'][currency],'timing_basis':result['envelope_basis'],
                'timing_limitations':result['missing_data']}
    definitions = [('confirmed_only',set()),('buy_fills',{'buy'}),('sale_fills',{'sale'}),('all_fills',{'buy','sale'})]
    optional_sides = {trades[e['id']][0] for e in events if e['id'] in trades and not e['confirmed']}
    scenarios = {name:scenario(sides) for name,sides in definitions if not sides or sides <= optional_sides}
    return finish(dict(source,role=source.get('role','hypothetical_scenario')), 'trade-cash-plan',
                  opening={'settled':settled,'reserved':reserved,'advisory_floor':floor,**point(settled-reserved)},
                  settlement_lag_business_days=lag, scenarios=scenarios,calendar_timezone=zone_name,calendar_timezone_basis=zone_basis,
                  assumptions='Full fills at the stated cash effects only in the named scenarios. Existing opening reservations are separate from new trades. Sale credit on its calculated date is hypothetical; no intraday posting time is inferred.',
                  execution_authorized=False,spendable_cash=None)
