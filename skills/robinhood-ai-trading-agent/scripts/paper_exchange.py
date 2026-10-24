"""Offline event-ledger replay; supplied fills are hypothetical, never broker orders.

Original implementation. Decimal accounting, ordered events, explicit settlement,
futures variation, funded FX conversion and bounded corporate actions. This is
an accounting/failure-test harness, not a queue simulator or live execution service.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from decimal import (Decimal, Context, DecimalException, localcontext, ROUND_HALF_EVEN,
                     InvalidOperation, DivisionByZero, Overflow, Underflow)
from pathlib import Path


def require(test, message):
    if not test:
        raise ValueError(message)


def shape(value, required, optional=()):
    require(isinstance(value, dict), 'OBJECT_REQUIRED')
    require(set(required) <= set(value), 'MISSING_FIELDS:' + ','.join(sorted(set(required)-set(value))))
    require(set(value) <= set(required)|set(optional), 'UNKNOWN_FIELDS:' + ','.join(sorted(set(value)-set(required)-set(optional))))


def number(value, minimum=None, positive=False):
    require(type(value) in (str, int, float), 'DECIMAL_NUMBER_REQUIRED')
    try:
        result = Decimal(str(value))
    except Exception:
        raise ValueError('INVALID_DECIMAL') from None
    require(result.is_finite(), 'FINITE_DECIMAL_REQUIRED')
    require(result.is_zero() or -999 <= result.adjusted() <= 999, 'DECIMAL_EXPONENT_RANGE')
    require(minimum is None or result >= minimum, 'NUMBER_BELOW_MINIMUM')
    require(not positive or result > 0, 'POSITIVE_NUMBER_REQUIRED')
    return result


def instant(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)',value), 'EXACT_AWARE_TIMESTAMP_REQUIRED')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('INVALID_TIMESTAMP') from None
    require(result.tzinfo is not None, 'TIMEZONE_REQUIRED')
    return result.astimezone(timezone.utc)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def output(value):
    if isinstance(value, Decimal):
        require(value.is_finite(), 'NONFINITE_ACCOUNTING_RESULT')
        return format(value, 'f')
    if isinstance(value, dict):
        return {k: output(v) for k, v in value.items()}
    if isinstance(value, list):
        return [output(v) for v in value]
    return value


def replay(document):
    # Isolate both input mutation and ambient Decimal settings.
    # A fresh Context also fixes exponent bounds, traps, flags and clamp; inheriting
    # only the caller's context could silently turn finite cash into Infinity.
    ctx = Context(prec=34, rounding=ROUND_HALF_EVEN, Emin=-999, Emax=999,
                  capitals=1, clamp=0, flags=[],
                  traps=[InvalidOperation, DivisionByZero, Overflow, Underflow])
    try:
        with localcontext(ctx):
            return _replay(deepcopy(document))
    except DecimalException as exc:
        raise ValueError('DECIMAL_ACCOUNTING_RANGE:'+type(exc).__name__) from None


def _replay(d):
    input_hash = digest(d)
    shape(d, ('schema_version', 'environment', 'base_currency', 'initial_cash', 'instruments', 'events', 'as_of', 'max_quote_age_seconds', 'max_fx_age_seconds'))
    require(type(d['schema_version']) is int and d['schema_version'] == 1, 'SCHEMA_VERSION_1_REQUIRED')
    require(d['environment'] == 'paper', 'PAPER_ONLY')
    require(isinstance(d['base_currency'], str) and d['base_currency'], 'BASE_CURRENCY_REQUIRED')
    as_of = instant(d['as_of'])
    quote_age = number(d['max_quote_age_seconds'], 0)
    fx_age = number(d['max_fx_age_seconds'], 0)
    require(isinstance(d['initial_cash'], dict) and d['initial_cash'], 'INITIAL_CASH_REQUIRED')
    cash = {k: number(v, 0) for k, v in d['initial_cash'].items()}
    require(all(isinstance(k, str) and k for k in cash), 'CURRENCY_NAMES_REQUIRED')
    assets, quotes, positions, basis, orders, pending, seen, fx = {}, {}, {}, {}, {}, {}, {}, {}
    records, duplicates = [], []
    require(isinstance(d['instruments'], list), 'INSTRUMENT_LIST_REQUIRED')
    for asset in d['instruments']:
        shape(asset, ('id', 'kind', 'currency', 'multiplier', 'quantity_step', 'price_tick'), ('expiry', 'underlying', 'strike', 'right', 'margin_per_contract','exercise_style','settlement_type'))
        key = asset['id']
        require(isinstance(key, str) and key and key not in assets, 'UNIQUE_INSTRUMENT_ID_REQUIRED')
        require(asset['kind'] in {'equity', 'etf', 'option', 'future', 'bond', 'crypto'}, 'INSTRUMENT_KIND_UNSUPPORTED')
        require(isinstance(asset['currency'], str) and asset['currency'], 'CURRENCY_REQUIRED')
        for field in ('multiplier', 'quantity_step', 'price_tick'):
            asset[field] = number(asset[field], positive=True)
        if asset['kind'] in {'option', 'future'}:
            require('expiry' in asset, 'EXPIRY_REQUIRED')
            instant(asset['expiry'])
            require(asset['quantity_step'] == 1, 'WHOLE_CONTRACTS_REQUIRED')
        if asset['kind'] == 'future':
            require('margin_per_contract' in asset, 'SUPPLIED_FUTURES_MARGIN_REQUIRED')
            asset['margin_per_contract'] = number(asset['margin_per_contract'], positive=True)
        else:
            require('margin_per_contract' not in asset, 'MARGIN_ONLY_FOR_FUTURES')
        if asset['kind'] == 'option':
            require({'underlying', 'strike', 'right','exercise_style','settlement_type'} <= set(asset), 'OPTION_TERMS_REQUIRED')
            asset['strike'] = number(asset['strike'], positive=True)
            require(asset['right'] in {'call', 'put'}, 'OPTION_RIGHT')
            require(asset['exercise_style'] in {'american','european'} and asset['settlement_type'] in {'cash','physical'}, 'OPTION_SETTLEMENT_CONVENTION')
        else:
            require(not ({'underlying', 'strike', 'right','exercise_style','settlement_type'} & set(asset)), 'OPTION_TERMS_ON_NONOPTION')
        cash.setdefault(asset['currency'], Decimal(0))
        assets[key], positions[key], basis[key] = asset, Decimal(0), Decimal(0)
    for a in assets.values():
        if a['kind'] == 'option':
            u = assets.get(a['underlying'])
            require(u is not None and u['kind'] in {'equity', 'etf'} and u['currency'] == a['currency'] and u['multiplier'] == 1, 'SUPPORTED_OPTION_UNDERLYING_REQUIRED')

    def check_cash():
        for currency, amount in cash.items():
            margin = sum((abs(positions[k])*a.get('margin_per_contract', 0) for k,a in assets.items() if a['currency'] == currency and a['kind'] == 'future'), Decimal(0))
            require(amount >= margin, 'INSUFFICIENT_SETTLED_CASH_OR_FUTURES_COLLATERAL:' + currency)

    def check_open(key, when):
        require(key in assets, 'UNKNOWN_INSTRUMENT')
        a = assets[key]
        require('expiry' not in a or when < instant(a['expiry']), 'INSTRUMENT_EXPIRED')

    def check_quote(key, when):
        require(key in quotes, 'QUOTE_REQUIRED')
        q = quotes[key]
        require(Decimal(str((when-instant(q['at'])).total_seconds())) <= quote_age, 'STALE_QUOTE')
        return q

    require(isinstance(d['events'], list), 'EVENT_LIST_REQUIRED')
    previous = None
    for event in d['events']:
        require(isinstance(event, dict) and {'id','type','at'} <= set(event), 'EVENT_HEADER_REQUIRED')
        eid, kind, when = event['id'], event['type'], instant(event['at'])
        require(isinstance(eid, str) and eid, 'EVENT_ID_REQUIRED')
        fingerprint = digest(event)
        if eid in seen:
            require(seen[eid] == fingerprint, 'CONFLICTING_DUPLICATE_EVENT')
            duplicates.append(eid)
            continue
        require(when <= as_of and (previous is None or when >= previous), 'EVENT_TIME_ORDER_OR_CUTOFF')
        previous = when
        common = ('id', 'type', 'at')
        if kind == 'quote':
            shape(event, common+('instrument', 'bid', 'ask', 'bid_size', 'ask_size'))
            key = event['instrument']; check_open(key, when)
            a = assets[key]
            bid, ask = number(event['bid']), number(event['ask'])
            require(bid <= ask and (a['kind'] == 'future' or (bid >= 0 and ask > 0)), 'INVALID_QUOTE')
            require(bid % a['price_tick'] == 0 and ask % a['price_tick'] == 0, 'QUOTE_OFF_TICK')
            quotes[key] = {'at': event['at'], 'bid': bid, 'ask': ask, 'bid_size': number(event['bid_size'], 0), 'ask_size': number(event['ask_size'], 0)}
        elif kind == 'order':
            shape(event, common+('order_id', 'instrument', 'side', 'quantity', 'order_type'), ('limit_price',))
            key = event['instrument']; check_open(key, when)
            oid = event['order_id']
            require(isinstance(oid, str) and oid and oid not in orders, 'UNIQUE_ORDER_ID_REQUIRED')
            require(event['side'] in {'buy', 'sell'}, 'SIDE_REQUIRED')
            require(event['order_type'] in {'market', 'limit'}, 'ORDER_TYPE_UNSUPPORTED')
            quantity = number(event['quantity'], positive=True)
            require(quantity % assets[key]['quantity_step'] == 0, 'QUANTITY_OFF_STEP')
            if event['order_type'] == 'limit':
                require('limit_price' in event, 'LIMIT_REQUIRED')
                limit = number(event['limit_price'])
                require(limit % assets[key]['price_tick'] == 0 and (assets[key]['kind'] == 'future' or limit >= 0), 'INVALID_LIMIT')
            else:
                require('limit_price' not in event, 'LIMIT_ON_MARKET_ORDER')
                limit = None
            orders[oid] = {'instrument':key, 'side':event['side'], 'quantity':quantity, 'filled':Decimal(0), 'state':'OPEN', 'at':event['at'], 'limit_price':limit}
        elif kind == 'fill':
            shape(event, common+('order_id','quantity','price','fee','settle_at'))
            require(event['order_id'] in orders, 'UNKNOWN_ORDER')
            order = orders[event['order_id']]
            require(order['state'] in {'OPEN','PARTIALLY_FILLED','CANCEL_PENDING'}, 'ORDER_NOT_FILLABLE')
            require(when > instant(order['at']), 'FILL_MUST_FOLLOW_ORDER')
            key = order['instrument']; check_open(key, when)
            a, q = assets[key], check_quote(key, when)
            qty, price, fee = number(event['quantity'], positive=True), number(event['price']), number(event['fee'], 0)
            require(qty % a['quantity_step'] == 0 and price % a['price_tick'] == 0, 'FILL_OFF_GRID')
            require(qty <= order['quantity']-order['filled'], 'OVERFILL')
            buy = order['side'] == 'buy'
            require((buy and price >= q['ask']) or (not buy and price <= q['bid']), 'FILL_BETTER_THAN_DECLARED_QUOTE_UNSUPPORTED')
            require(a['kind'] == 'future' or price >= 0, 'NEGATIVE_FUNDED_ASSET_PRICE')
            limit = order['limit_price']
            require(limit is None or (price <= limit if buy else price >= limit), 'LIMIT_BREACH')
            size = 'ask_size' if buy else 'bid_size'
            require(qty <= q[size], 'DISPLAYED_LIQUIDITY_EXCEEDED')
            settle_at = instant(event['settle_at'])
            require(settle_at >= when, 'SETTLEMENT_BEFORE_FILL')
            signed, currency = qty if buy else -qty, a['currency']
            if a['kind'] == 'future':
                require(settle_at == when, 'FUTURES_FILL_CASH_IS_IMMEDIATE')
                # Settle the entire old position to this fill price before changing it.
                cash[currency] += positions[key]*a['multiplier']*(price-basis[key])-fee
                positions[key] += signed
                basis[key] = price if positions[key] else Decimal(0)
            else:
                require(positions[key]+signed >= 0, 'FUNDED_ASSET_SHORTING_UNSUPPORTED')
                notional = qty*price*a['multiplier']
                if buy:
                    cash[currency] -= notional+fee
                else:
                    proceeds = notional-fee
                    require(proceeds >= 0, 'FEE_EXCEEDS_SALE_PROCEEDS')
                    if settle_at == when:
                        cash[currency] += proceeds
                    else:
                        pending[eid] = {'currency':currency,'amount':proceeds,'settle_at':event['settle_at']}
                positions[key] += signed
            order['filled'] += qty
            order['state'] = 'FILLED' if order['filled'] == order['quantity'] else ('CANCEL_PENDING' if order['state'] == 'CANCEL_PENDING' else 'PARTIALLY_FILLED')
            q[size] -= qty
        elif kind in {'cancel_request','cancel_ack'}:
            shape(event, common+('order_id',))
            require(event['order_id'] in orders, 'UNKNOWN_ORDER')
            order = orders[event['order_id']]
            if kind == 'cancel_request':
                require(order['state'] in {'OPEN','PARTIALLY_FILLED'}, 'ORDER_NOT_CANCELLABLE')
                order['state'] = 'CANCEL_PENDING'
            else:
                require(order['state'] == 'CANCEL_PENDING', 'CANCEL_ACK_WITHOUT_PENDING')
                order['state'] = 'CANCELLED'
        elif kind == 'settle_cash':
            shape(event, common+('fill_id',))
            require(event['fill_id'] in pending, 'UNSETTLED_FILL_REQUIRED')
            due = pending[event['fill_id']]
            require(when >= instant(due['settle_at']), 'CASH_NOT_DUE')
            cash[due['currency']] += due['amount']; del pending[event['fill_id']]
        elif kind == 'futures_settlement':
            shape(event, common+('instrument','price','margin_per_contract','final'))
            key = event['instrument']; require(key in assets and assets[key]['kind'] == 'future', 'FUTURE_REQUIRED')
            a = assets[key]; price = number(event['price'])
            require(type(event['final']) is bool and price % a['price_tick'] == 0, 'FUTURES_SETTLEMENT_FIELDS')
            if not event['final']:
                check_open(key, when)
            else:
                require(when == instant(a['expiry']), 'FINAL_SETTLEMENT_MUST_MATCH_EXPIRY')
                require(not any(o['instrument']==key and o['state'] in {'OPEN','PARTIALLY_FILLED','CANCEL_PENDING'} for o in orders.values()), 'OPEN_ORDERS_AT_SETTLEMENT')
            cash[a['currency']] += positions[key]*a['multiplier']*(price-basis[key])
            basis[key] = price
            a['margin_per_contract'] = number(event['margin_per_contract'], positive=True)
            if event['final']:
                positions[key] = Decimal(0); basis[key] = Decimal(0)
        elif kind == 'fx_rate':
            shape(event, common+('currency','rate_to_base'))
            require(event['currency'] != d['base_currency'], 'BASE_FX_IS_ONE')
            fx[event['currency']] = {'rate':number(event['rate_to_base'],positive=True),'at':event['at']}
        elif kind == 'fx_convert':
            shape(event, common+('from_currency','to_currency','amount','rate','fee'))
            src,dst = event['from_currency'],event['to_currency']
            require(src != dst and src in cash and isinstance(dst,str) and dst, 'FX_CURRENCIES')
            amount, rate, fee = number(event['amount'],positive=True),number(event['rate'],positive=True),number(event['fee'],0)
            cash[src] -= amount+fee; cash[dst] = cash.get(dst,Decimal(0))+amount*rate
        elif kind == 'distribution':
            shape(event, common+('instrument','entitled_quantity','amount_per_unit'))
            key=event['instrument']; require(key in assets and assets[key]['kind'] in {'equity','etf','bond','crypto'}, 'DISTRIBUTION_ASSET')
            # Entitlement is supplied evidence, not inferred from payment-date holdings.
            cash[assets[key]['currency']] += number(event['entitled_quantity'],0)*number(event['amount_per_unit'],0)
        elif kind == 'split':
            shape(event, common+('instrument','ratio'))
            key=event['instrument']; require(key in assets and assets[key]['kind'] in {'equity','etf'}, 'SPLIT_ASSET')
            require(not any(o['instrument']==key and o['state'] in {'OPEN','PARTIALLY_FILLED','CANCEL_PENDING'} for o in orders.values()), 'OPEN_ORDERS_REQUIRE_EXPLICIT_CORPORATE_ACTION_RESOLUTION')
            require(not any(a.get('underlying')==key and (positions[k] or instant(a['expiry'])>=when) for k,a in assets.items()), 'OPTION_DELIVERABLE_ADJUSTMENT_REQUIRED')
            positions[key] *= number(event['ratio'],positive=True)
            require(positions[key] % assets[key]['quantity_step'] == 0, 'FRACTIONAL_SPLIT_REQUIRES_CASH_IN_LIEU_MODEL')
            quotes.pop(key,None)
        elif kind in {'option_expiry','option_exercise'}:
            fields=('instrument','underlying_settlement_price') if kind=='option_expiry' else ('instrument','quantity')
            shape(event, common+fields)
            key=event['instrument']; require(key in assets and assets[key]['kind']=='option', 'OPTION_REQUIRED')
            a=assets[key]
            require(when <= instant(a['expiry']), 'OPTION_AFTER_EXPIRY')
            require(not any(o['instrument']==key and o['state'] in {'OPEN','PARTIALLY_FILLED','CANCEL_PENDING'} for o in orders.values()), 'OPEN_ORDERS_AT_SETTLEMENT')
            if kind=='option_expiry':
                require(when == instant(a['expiry']), 'OPTION_EXPIRY_TIME_REQUIRED')
                spot=number(event['underlying_settlement_price'],0)
                intrinsic=max((spot-a['strike']) if a['right']=='call' else (a['strike']-spot),Decimal(0))
                require(a['settlement_type']=='cash' or intrinsic==0, 'IN_THE_MONEY_PHYSICAL_OPTION_REQUIRES_EXPLICIT_EXERCISE')
                cash[a['currency']]+=positions[key]*a['multiplier']*intrinsic
                positions[key]=Decimal(0)
            else:
                require(a['settlement_type']=='physical', 'PHYSICAL_EXERCISE_REQUIRED')
                require(a['exercise_style']=='american' or when==instant(a['expiry']), 'EARLY_EUROPEAN_EXERCISE')
                qty=number(event['quantity'],positive=True)
                require(qty % a['quantity_step']==0 and qty<=positions[key], 'EXERCISE_QUANTITY')
                shares=qty*a['multiplier']; underlying=a['underlying']
                require(shares % assets[underlying]['quantity_step']==0,'EXERCISE_DELIVERABLE_OFF_STEP')
                sign=1 if a['right']=='call' else -1
                require(positions[underlying]+sign*shares>=0, 'PUT_EXERCISE_REQUIRES_OWNED_DELIVERABLE')
                cash[a['currency']]-=sign*shares*a['strike']
                positions[underlying]+=sign*shares
                positions[key]-=qty
        elif kind == 'bond_redemption':
            shape(event,common+('instrument','principal_per_unit'))
            key=event['instrument']; require(key in assets and assets[key]['kind']=='bond','BOND_REQUIRED')
            a=assets[key]
            require('expiry' in a and when==instant(a['expiry']),'BOND_MATURITY_REQUIRED')
            require(not any(o['instrument']==key and o['state'] in {'OPEN','PARTIALLY_FILLED','CANCEL_PENDING'} for o in orders.values()),'OPEN_ORDERS_AT_SETTLEMENT')
            cash[a['currency']]+=positions[key]*number(event['principal_per_unit'],0)
            positions[key]=Decimal(0)
        else:
            raise ValueError('EVENT_TYPE_UNSUPPORTED:'+str(kind))
        check_cash()
        seen[eid]=fingerprint
        records.append({'id':eid,'type':kind,'at':event['at'],'cash':dict(cash),'positions':dict(positions),'pending_cash':deepcopy(pending)})

    nav_by_currency = dict(cash)
    for order in orders.values():
        if order['state'] in {'OPEN','PARTIALLY_FILLED','CANCEL_PENDING'}:
            check_open(order['instrument'],as_of)
    for due in pending.values():
        nav_by_currency[due['currency']] += due['amount']
    marks = {}
    for key,qty in positions.items():
        if not qty:
            continue
        check_open(key,as_of)
        a,q=assets[key],check_quote(key,as_of)
        mark=(q['bid']+q['ask'])/2
        value=qty*a['multiplier']*(mark-basis[key] if a['kind']=='future' else mark)
        nav_by_currency[a['currency']]+=value
        marks[key]={'price':mark,'value':value,'currency':a['currency'],'basis':'bid_ask_midpoint_not_liquidation'}
    nav=Decimal(0)
    for currency,value in nav_by_currency.items():
        if value == 0: continue
        if currency == d['base_currency']: rate=Decimal(1)
        else:
            require(currency in fx, 'FX_VALUATION_RATE_REQUIRED:'+currency)
            require(Decimal(str((as_of-instant(fx[currency]['at'])).total_seconds()))<=fx_age, 'STALE_FX_RATE')
            rate=fx[currency]['rate']
        nav += value*rate
    result={'status':'PAPER_LEDGER_REPLAYED','environment':'paper','cash':cash,'pending_cash':pending,'positions':positions,'orders':orders,'marks':marks,'nav_by_currency':nav_by_currency,'nav_base':nav,'base_currency':d['base_currency'],'events_applied':len(records),'duplicate_event_ids_ignored':duplicates,'journal':records,'input_sha256':input_hash,'execution_authorized':False,'live_orders_submitted':0,'production_qualified':False,'limitations':['Hypothetical supplied fills; no queue, latency, market-impact or broker simulation.','Funded assets long-only; futures use supplied cash collateral; no portfolio margin or tax lots.','Buy cash is debited immediately; sell proceeds require explicit settlement event. No unsettled-cash reuse.','No pending-order buying-power reservations; each hypothetical fill must remain cash/collateral feasible.','Only explicit long vanilla option exercise/expiry and supplied bond redemption; no short assignment, adjusted option deliverables, default waterfall or futures physical delivery. Unresolved expiry is rejected.','FX conversion is supplied funded two-currency exchange, not leveraged spot FX, forwards or broker support.','Quotes, fills, distributions and FX are supplied assumptions, not independently authenticated market evidence.']}
    return output(result)


OPERATIONS={'replay':replay}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    args=parser.parse_args()
    def unique_keys(pairs):
        result={}
        for key,value in pairs:
            require(key not in result,'DUPLICATE_JSON_KEY:'+key)
            result[key]=value
        return result
    document=json.loads(args.input.read_text(encoding='utf-8-sig'),object_pairs_hook=unique_keys,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('NONFINITE_JSON:'+value)))
    print(json.dumps(replay(document),indent=2,allow_nan=False))


if __name__=='__main__': main()
