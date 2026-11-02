"""Explicit long-only holdings, entitlements, settled cash and declared-tax replay.

Caller-supplied dated events, not an execution simulator or tax-law engine. Prices
are unadjusted per-unit marks; corporate actions must not also be in adjusted NAV.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from quant_common import digest, require, timestamp, cli


def dec(x, name, minimum=None):
    require(type(x) in (str, int), 'DECIMAL_STRING_OR_INTEGER:'+name)
    try:
        v = Decimal(x)
    except InvalidOperation as exc:
        raise ValueError('INVALID_DECIMAL:'+name) from exc
    require(v.is_finite() and (minimum is None or v >= minimum), 'INVALID_RANGE:'+name)
    return v


def clean(x):
    if isinstance(x, Decimal): return str(x)
    if isinstance(x, dict): return {k:clean(v) for k,v in x.items()}
    if isinstance(x, list): return [clean(v) for v in x]
    return x


def replay(document):
    """Replay explicit events; unknown valuation or taxes stay unknown.

    Required: currency, as_of, opening{at,cash,lots,marks}, events,
    price_basis='unadjusted', valuation_policy='observed_only'|'allow_references',
    tax_mode='unmodeled'|'explicit_event_amounts'|'positive_sale_gains'.
    Equal-time events execute in the supplied order, never guessed exchange order.
    Buys debit cash at trade time conservatively; sell/dividend receipts must settle.
    """
    d = deepcopy(document)
    require(d['price_basis'] == 'unadjusted', 'ADJUSTED_PRICES_WOULD_DOUBLE_COUNT_ACTIONS')
    require(d['valuation_policy'] in {'observed_only','allow_references'}, 'VALUATION_POLICY')
    require(d['tax_mode'] in {'unmodeled','explicit_event_amounts','positive_sale_gains'}, 'TAX_MODE')
    require(isinstance(d['currency'], str) and len(d['currency']) == 3, 'CURRENCY_REQUIRED')
    end = timestamp(d['as_of']); start = timestamp(d['opening']['at'])
    require(start <= end, 'DATE_ORDER')
    require(d.get('equal_time_order') == 'supplied_order', 'EQUAL_TIME_ORDER_REQUIRED')
    cash = dec(d['opening']['cash'], 'cash', Decimal(0))
    floor = dec(d.get('cash_floor','0'), 'floor', Decimal(0))
    tax_due = dec(d['opening'].get('tax_liability','0'), 'tax_liability', Decimal(0))
    lots, marks, pending, seen_lots = {}, {}, [], set()
    mark_not_before = {}
    unknown_tax = []; realized = []; trace = []; external = Decimal(0); fees = Decimal(0)
    receipts_created=Decimal(0);buy_debits=Decimal(0);tax_payments=Decimal(0)
    if d['tax_mode'] == 'unmodeled': unknown_tax.append('TAXES_NOT_MODELED')

    def add_lot(identifier, sid, quantity, basis, acquired):
        require(isinstance(identifier,str) and identifier and identifier not in seen_lots,'UNIQUE_LOT_ID')
        require(isinstance(sid,str) and sid and quantity > 0, 'SECURITY_AND_POSITIVE_QUANTITY')
        require(timestamp(acquired) <= end, 'FUTURE_ACQUISITION')
        seen_lots.add(identifier)
        lots[identifier] = dict(lot_id=identifier, security_id=sid, quantity=quantity,
                                basis=basis, acquired_at=acquired)

    for row in d['opening']['lots']:
        require(timestamp(row['acquired_at']) <= start, 'OPENING_LOT_ACQUIRED_LATER')
        add_lot(row['lot_id'], row['security_id'], dec(row['quantity'],'quantity',Decimal(0)),
                None if row['basis'] is None else dec(row['basis'],'basis',Decimal(0)), row['acquired_at'])

    def put_mark(row, now):
        require(row.get('currency', d['currency']) == d['currency'], 'MARK_CURRENCY_MISMATCH')
        require(row['kind'] in {'observed','reference','modeled'}, 'MARK_KIND')
        require(timestamp(row['observed_at']) <= timestamp(row['available_at']) <= now, 'FUTURE_MARK')
        require(row['security_id'] not in mark_not_before or
                timestamp(row['observed_at']) >= mark_not_before[row['security_id']], 'PRE_ACTION_MARK_BASIS')
        require(row.get('source'), 'MARK_SOURCE_REQUIRED')
        price = None if row['price'] is None else dec(row['price'],'price',Decimal(0))
        marks[row['security_id']] = dict(row, price=price)

    def invalidate_mark(sid, now):
        marks.pop(sid, None)
        mark_not_before[sid] = now

    for row in d['opening']['marks']: put_mark(row, start)

    def settle(now):
        nonlocal cash, pending
        left=[]; settled=[]
        for row in pending:
            if timestamp(row['settles_at']) <= now:
                cash += row['amount']; settled.append(row['id'])
            else: left.append(row)
        pending=left
        return settled

    def quantity(sid): return sum((l['quantity'] for l in lots.values() if l['security_id']==sid),Decimal(0))

    def snapshot(at, label):
        positions={}; missing=[]; qualified=[]; total=Decimal(0)
        for sid in sorted({l['security_id'] for l in lots.values()}):
            qty=quantity(sid); mark=marks.get(sid)
            usable=mark and mark['price'] is not None and (mark['kind']=='observed' or d['valuation_policy']=='allow_references')
            value=qty*mark['price'] if usable else None
            if value is None: missing.append(sid)
            else: total+=value
            if mark and mark['kind']!='observed': qualified.append(sid)
            positions[sid]={'quantity':qty,'value':value,'mark':mark}
        receivable=sum((r['amount'] for r in pending),Decimal(0))
        gross=None if missing else cash+receivable+total
        return clean({'at':at,'label':label,'settled_cash':cash,'cash_receivables':receivable,
                      'declared_tax_liability':tax_due,'cash_available_after_tax_reserve':max(Decimal(0),cash-tax_due),
                      'tax_reserve_shortfall':max(Decimal(0),tax_due-cash),
                      'cash_floor_shortfall':max(Decimal(0),floor-max(Decimal(0),cash-tax_due)),
                      'positions':positions,'gross_nav':gross,
                      'net_nav_after_declared_tax':None if gross is None or unknown_tax else gross-tax_due,
                      'unknown_valuations':missing,'nonobserved_mark_securities':qualified,
                      'valuation_status':'UNKNOWN' if missing else 'REFERENCE_OR_MODEL_SCENARIO' if qualified else 'CALLER_SUPPLIED_OBSERVED_MARKS',
                      'unresolved_tax_events':list(unknown_tax)})

    def receivable(event, amount, suffix='cash'):
        nonlocal receipts_created
        require(timestamp(event['settles_at']) >= timestamp(event['at']), 'SETTLEMENT_BEFORE_EVENT')
        pending.append({'id':event['id']+':'+suffix,'amount':amount,'settles_at':event['settles_at']})
        receipts_created+=amount

    def consume(event, qty):
        sid=event['security_id']; selection=event['lots']
        require(selection and len(set(selection))==len(selection),'EXPLICIT_ORDERED_UNIQUE_LOTS_REQUIRED')
        remaining=qty; basis=Decimal(0); details=[]
        for lid in selection:
            require(lid in lots and lots[lid]['security_id']==sid,'LOT_SECURITY_MISMATCH')
            lot=lots[lid]; take=min(remaining,lot['quantity'])
            if take==0: continue
            allocated=None if lot['basis'] is None else lot['basis']*take/lot['quantity']
            details.append({'lot_id':lid,'quantity':take,'basis':allocated})
            basis=None if basis is None or allocated is None else basis+allocated
            lot['quantity']-=take
            if allocated is not None: lot['basis']-=allocated
            if lot['quantity']==0: del lots[lid]
            remaining-=take
            if remaining==0: break
        require(remaining==0,'INSUFFICIENT_SELECTED_LOTS')
        return basis,details

    def accrue(event, gain=None, sale=False):
        nonlocal tax_due
        if d['tax_mode']=='unmodeled': return
        if 'tax_amount' in event:
            tax_due+=dec(event['tax_amount'],'tax_amount',Decimal(0)); return
        if d['tax_mode']=='positive_sale_gains' and sale:
            if event.get('tax_rate') is not None and gain is not None:
                rate=dec(event['tax_rate'],'tax_rate',Decimal(0));require(rate<=1,'TAX_RATE_RANGE')
                tax_due+=max(Decimal(0),gain)*rate; return
        unknown_tax.append(event['id'])

    trace.append(snapshot(d['opening']['at'],'opening'))
    events=d['events'];require(len({e['id'] for e in events})==len(events),'UNIQUE_EVENT_IDS')
    previous=start
    for e in events:
        now=timestamp(e['at']);require(previous<=now<=end,'EVENT_ORDER_OR_CUTOFF');previous=now
        require(e.get('source'),'EVENT_SOURCE_REQUIRED')
        require(e.get('currency',d['currency'])==d['currency'],'FX_NOT_MODELED')
        settled=settle(now);kind=e['type']; detail={}
        if kind=='mark': put_mark(e,now)
        elif kind in {'deposit','withdrawal'}:
            amount=dec(e['amount'],'cash_flow',Decimal(0))
            if kind=='withdrawal':
                require(amount<=max(Decimal(0),cash-tax_due)-floor,'INSUFFICIENT_SETTLED_UNRESERVED_CASH')
                amount=-amount
            cash+=amount;external+=amount
        elif kind=='buy':
            require(e['execution_price_basis']=='observed','NONEXECUTABLE_REFERENCE_PRICE')
            qty=dec(e['quantity'],'quantity',Decimal(0));price=dec(e['price'],'price',Decimal(0));require(qty>0 and price>0,'POSITIVE_BUY')
            cost=dec(e['cost'],'cost',Decimal(0));debit=qty*price+cost
            require(debit<=max(Decimal(0),cash-tax_due)-floor,'INSUFFICIENT_SETTLED_UNRESERVED_CASH')
            require(timestamp(e['settles_at'])>=now,'SETTLEMENT_BEFORE_TRADE')
            cash-=debit;fees+=cost;buy_debits+=debit
            add_lot(e['lot_id'],e['security_id'],qty,debit,e['at'])
            put_mark(dict(security_id=e['security_id'],price=e['price'],kind='observed',observed_at=e['at'],available_at=e['at'],source=e['source']),now)
            detail={'buy_cash_debit':debit,'settles_at':e['settles_at'],'cash_convention':'Full purchase debit reserved at trade time; no unsettled-sale recycling.'}
        elif kind in {'sell','cash_in_lieu'}:
            require(e['execution_price_basis']=='observed','NONEXECUTABLE_REFERENCE_PRICE')
            qty=dec(e['quantity'],'quantity',Decimal(0));require(qty>0,'POSITIVE_DISPOSAL')
            price=dec(e['price'],'price',Decimal(0));cost=dec(e['cost'],'cost',Decimal(0));proceeds=qty*price-cost
            require(proceeds>=0,'NEGATIVE_NET_PROCEEDS');basis,selected=consume(e,qty);fees+=cost
            gain=None if basis is None else proceeds-basis
            receivable(e,proceeds);accrue(e,gain,True)
            put_mark(dict(security_id=e['security_id'],price=e['price'],kind='observed',observed_at=e['at'],available_at=e['at'],source=e['source']),now)
            detail={'realized_gain':gain,'basis':basis,'net_proceeds':proceeds,'lots':selected}
            realized.append(dict(event_id=e['id'],**detail))
        elif kind=='split':
            factor=dec(e['factor'],'split_factor',Decimal(0));require(factor>0,'POSITIVE_FACTOR')
            for lot in lots.values():
                if lot['security_id']==e['security_id']: lot['quantity']*=factor
            # Old marks use different share units; require a new explicit post-action mark.
            invalidate_mark(e['security_id'],now)
        elif kind=='dividend':
            require(e['dividend_type'] in {'ordinary','special'},'DIVIDEND_TYPE')
            amount=quantity(e['security_id'])*dec(e['per_unit'],'dividend',Decimal(0))
            receivable(e,amount);accrue(e);invalidate_mark(e['security_id'],now);detail={'entitlement':amount}
        elif kind=='spinoff':
            require(e['child_security_id']!=e['security_id'],'DISTINCT_CHILD_REQUIRED')
            ratio=dec(e['child_ratio'],'child_ratio',Decimal(0));require(ratio>0,'POSITIVE_CHILD_RATIO')
            fraction=None if e.get('child_basis_fraction') is None else dec(e['child_basis_fraction'],'basis_fraction',Decimal(0))
            require(fraction is None or fraction<=1,'BASIS_FRACTION_RANGE')
            for lot in list(lots.values()):
                if lot['security_id']!=e['security_id']: continue
                child_basis=None if fraction is None or lot['basis'] is None else lot['basis']*fraction
                lot['basis']=None if child_basis is None else lot['basis']-child_basis
                add_lot(e['id']+':'+lot['lot_id'],e['child_security_id'],lot['quantity']*ratio,child_basis,lot['acquired_at'])
            invalidate_mark(e['security_id'],now);invalidate_mark(e['child_security_id'],now)
            accrue(e);detail={'basis_allocation_known':fraction is not None}
        elif kind in {'merger','delisting'}:
            require(e.get('terminal_outcome_confirmed') is True,'UNCONFIRMED_TERMINAL_OUTCOME')
            per=dec(e['cash_per_unit'],'cash_per_unit',Decimal(0));total_qty=quantity(e['security_id'])
            require(total_qty>0,'NO_TERMINAL_POSITION')
            if kind=='merger':
                ratio=dec(e.get('child_ratio','0'),'child_ratio',Decimal(0))
                require(ratio==0 or e.get('child_security_id')!=e['security_id'],'DISTINCT_CHILD_REQUIRED')
            else: ratio=Decimal(0)
            basis_map=e.get('child_basis_by_parent_lot',{})
            for lid,lot in list(lots.items()):
                if lot['security_id']!=e['security_id']:continue
                if ratio:
                    child_basis=None if basis_map.get(lid) is None else dec(basis_map[lid],'child_basis',Decimal(0))
                    add_lot(e['id']+':'+lid,e['child_security_id'],lot['quantity']*ratio,child_basis,lot['acquired_at'])
                del lots[lid]
            receivable(e,total_qty*per);accrue(e)
            invalidate_mark(e['security_id'],now)
            if ratio: invalidate_mark(e['child_security_id'],now)
            detail={'removed_units':total_qty,'cash_entitlement':total_qty*per,'child_ratio':ratio,'tax_treatment':'Explicit supplied event tax only; merger/reorganization tax law is not inferred.'}
        elif kind=='tax_accrual': tax_due+=dec(e['amount'],'tax_amount',Decimal(0))
        elif kind=='tax_payment':
            amount=dec(e['amount'],'tax_payment',Decimal(0))
            require(amount<=tax_due and amount<=cash,'TAX_PAYMENT_EXCEEDS_LIABILITY_OR_CASH')
            cash-=amount;tax_due-=amount;tax_payments+=amount
        elif kind=='settlement': pass
        else: raise ValueError('UNSUPPORTED_EVENT:'+str(kind))
        settled+=settle(now)
        state=snapshot(e['at'],e['id']);state.update(event_type=kind,settled_receipts=settled,detail=clean(detail))
        trace.append(state)
    settle(end);final=snapshot(d['as_of'],'final')
    cash_identity=dec(d['opening']['cash'],'cash')+external+receipts_created-buy_debits-tax_payments-cash-sum((r['amount'] for r in pending),Decimal(0))
    require(abs(cash_identity)<Decimal('0.00000001'),'CASH_AND_RECEIVABLE_CONSERVATION_FAILURE')
    return {'method':'explicit-holdings-ledger-v1','currency':d['currency'],'input_sha256':digest(document),
            'status':'UNRESOLVED' if final['unknown_valuations'] or unknown_tax else 'COMPUTED_SCENARIO',
            'final':final,'lots':clean(list(lots.values())),'pending_receipts':clean(pending),'timeline':trace,
            'realizations':clean(realized),'net_external_cash_flows':str(external),'transaction_costs':str(fees),
            'cash_and_receivable_conservation_residual':str(cash_identity),
            'execution_authorized':False,'tax_law_verified':False,'source_authenticity_verified':False,
            'limitations':['Explicit supplied lots/events/prices only; not native fills or broker buying power.',
              'Tax rates/accruals are supplied scenarios; no wash-sale, state, holding-period or reorganization tax inference.',
              'Buys debit cash at trade time conservatively; no unsettled-sale funding.',
              'No automatic dividend reinvestment; an explicit later funded buy is required.',
              'Marks remain dated; no stale-price limit or liquidity certification is inferred.']}


if __name__=='__main__':cli({'replay':replay})
