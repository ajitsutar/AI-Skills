"""Build and verify an advisory marked-position and buy-limit journal review."""
import argparse
import json
from decimal import Decimal
from pathlib import Path

from news_evidence import decode, digest, read_source
from planning_alignment import amount
from quant_common import require


def positive(value, label):
    value = amount(value, label, 0)
    require(value > 0, 'POSITIVE_' + label)
    return value


def text(value):
    require(isinstance(value, str) and value.strip() and not any(c in value for c in '\r\n'), 'TEXT_REQUIRED')
    return value


def position_row(item):
    symbol = text(item['symbol'])
    qty = positive(item['quantity'], 'QUANTITY')
    basis = amount(item['basis_per_share'], minimum=0)
    mark = amount(item['current_mark'], minimum=0)
    pnl = qty * (mark - basis)
    as_of = text(item['as_of'])
    statement = (f'{symbol} at {as_of}: {qty} shares at basis {basis} and mark {mark}; '
                 f'cost {qty*basis}, marked value {qty*mark}, unrealized P&L {pnl}. '
                 f'A full exit at the mark would realize {pnl} before exit fees. '
                 'A sale realizes only the quantity sold times (actual sale price minus per-share basis), '
                 'less applicable exit fees. The unsold quantity stays exposed.')
    return dict(kind='marked_long', symbol=symbol, quantity=qty, basis_per_share=basis, mark=mark,
                as_of=as_of, cost=qty*basis, marked_value=qty*mark, unrealized_pnl=pnl, statement=statement)


def exit_row(position, scenario):
    qty = positive(scenario['quantity'], 'EXIT_QUANTITY')
    require(qty <= position['quantity'], 'EXIT_EXCEEDS_HOLDING')
    price = amount(scenario['fill_price'], minimum=0)
    fees = amount(scenario['exit_fees'], minimum=0) if scenario.get('exit_fees') is not None else None
    gross = qty * (price - position['basis_per_share'])
    net = None if fees is None else gross - fees
    remaining = position['quantity'] - qty
    remaining_pnl = remaining * (position['mark'] - position['basis_per_share'])
    fee_phrase = 'exit fees and net result unknown' if fees is None else f'exit fees {fees}, net {net}'
    statement = (f"Hypothetical {position['symbol']} exit of {qty} at {price}: gross realized P&L {gross}, "
                 f'{fee_phrase}. Remaining {remaining} shares at the supplied mark have unrealized P&L {remaining_pnl}.')
    return dict(kind='hypothetical_exit', symbol=position['symbol'], sold_quantity=qty, assumed_fill_price=price,
                exit_fees=fees, gross_realized=gross, net_realized=net, remaining_quantity=remaining,
                remaining_unrealized_at_mark=remaining_pnl, statement=statement)


def closed_row(item):
    qty = positive(item['quantity'], 'CLOSED_QUANTITY')
    buy = amount(item['buy_price'], minimum=0)
    sell = amount(item['sell_price'], minimum=0)
    fees = amount(item['fees'], minimum=0) if item.get('fees') is not None else None
    gross = qty * (sell - buy)
    net = None if fees is None else gross - fees
    fee_phrase = 'fees and net result unknown' if fees is None else f'fees {fees}, realized net {net}'
    symbol = text(item['symbol'])
    return dict(kind='closed_long', symbol=symbol, quantity=qty, buy_price=buy, sell_price=sell, gross=gross,
                fees=fees, net=net, statement=f'{symbol}: sold {qty} at {sell} against entry {buy}; '
                f'realized gross {gross}, {fee_phrase}.')


def pending_row(item):
    require(item['side'] == 'buy' and item['status'] in ('accepted', 'open', 'pending', 'partially_filled'),
            'PENDING_BUY_LIMIT_REQUIRED')
    symbol = text(item['symbol'])
    qty = positive(item['quantity'], 'REQUESTED_QUANTITY')
    limit = positive(item['limit_price'], 'LIMIT_PRICE')
    filled = item.get('cumulative_filled')
    avg = item.get('average_price')
    fees = item.get('fee')
    remaining = principal = cost = None
    if filled is not None:
        filled = amount(filled, minimum=0)
        require(filled <= qty and (item['status'] != 'partially_filled' or 0 < filled < qty), 'INVALID_FILLED_QUANTITY')
        remaining = qty - filled
    if avg is not None:
        avg = positive(avg, 'AVERAGE_FILL_PRICE')
        require(filled is not None and filled > 0 and avg <= limit, 'INVALID_BUY_LIMIT_FILL_PRICE')
        principal = filled * avg
    elif filled == 0:
        principal = Decimal(0)
    if fees is not None:
        fees = amount(fees, minimum=0)
        if principal is not None:
            cost = principal + fees
    statement = (f"{symbol} {item['status']} buy limit for {qty} at {limit}: {qty*limit} is the maximum principal "
                 'if the entire requested quantity fills at the limit. Fees are separate. '
                 'Acceptance alone creates no confirmed holding, exposure from fills or realized loss.')
    if filled is None:
        statement += ' Actual filled quantity, principal and remaining quantity are unconfirmed.'
    else:
        statement += f' Reported fills {filled} shares; remaining {remaining}, maximum additional principal {remaining*limit}.'
        statement += ' Filled principal is unknown.' if principal is None else f' Observed filled principal {principal}.'
    if cost is not None:
        statement += f' Reported filled principal plus fees {cost}.'
    return dict(kind='pending_buy_limit', symbol=symbol, status=item['status'], requested_quantity=qty, limit_price=limit,
                maximum_full_order_principal=qty*limit, filled_quantity=filled, average_fill_price=avg, fees=fees,
                filled_principal=principal, filled_cost_including_reported_fees=cost, remaining_quantity=remaining,
                maximum_additional_principal=None if remaining is None else remaining*limit, statement=statement)


def snapshot_amount(value):
    """Retain opaque source values in the observation, without using them in arithmetic."""
    try:
        return amount(value, minimum=0)
    except ValueError:
        return None


def snapshot_unit(value):
    if isinstance(value, str) and value.strip().lower() not in ('', 'unknown', 'unspecified', 'n/a'):
        return text(value.strip())
    return None


def snapshot_event(e, clock):
    snapshot = e['broker_snapshot']
    qty = positive(snapshot['requested_quantity'], 'SNAPSHOT_QUANTITY')
    raw_filled = snapshot.get('cumulative_filled')
    filled = amount(raw_filled, minimum=0) if raw_filled is not None else None
    require(filled is None or filled <= qty, 'SNAPSHOT_OVERFILL')
    remaining = qty - filled if filled is not None else None
    raw_side = snapshot.get('side')
    side = raw_side.strip().lower() if isinstance(raw_side, str) else None
    side = side if side in ('buy', 'sell') else None
    raw_price, raw_fee = snapshot.get('average_price'), snapshot.get('fee')
    price, fee = snapshot_amount(raw_price), snapshot_amount(raw_fee)
    principal = None
    if filled == 0:
        principal = Decimal(0)
    elif filled is not None and price is not None and price > 0:
        principal = filled * price

    common_unit = snapshot_unit(snapshot.get('currency'))
    price_unit = snapshot_unit(snapshot.get('price_currency')) or common_unit
    fee_unit = snapshot_unit(snapshot.get('fee_currency')) or common_unit
    both_units = price_unit is not None and fee_unit is not None
    comparable = not both_units or price_unit == fee_unit
    signed_net = None
    if side and principal is not None and fee is not None and comparable and filled > 0:
        signed_net = (principal if side == 'sell' else -principal) - fee
    unit_basis = ('reported_common_unit' if both_units and comparable else
                  'different_reported_units' if both_units else 'common_unit_unconfirmed')

    statement = f"{clock} supplied snapshot {text(snapshot['id'])}, {text(snapshot['status'])}: "
    if filled is None:
        statement += f'filled and remaining quantities unknown for {qty} requested.'
    else:
        statement += f'{filled} of {qty} filled, {remaining} remaining at this observation.'
    statement += (f" Average price {raw_price if raw_price is not None else 'unknown'}"
                  f"{' ' + price_unit if price_unit else ''}, fee {raw_fee if raw_fee is not None else 'unknown'}"
                  f"{' ' + fee_unit if fee_unit else ''}.")
    statement += f" Snapshot side {side or 'unknown'}."
    statement += ' Gross filled notional unknown.' if principal is None else f' Gross filled notional {principal}.'
    if signed_net is not None:
        basis = f'in {price_unit}' if both_units else 'assuming price and fee share a monetary unit'
        statement += f' Fee-adjusted fill cash flow {signed_net} ({basis}; positive is a credit, negative a debit).'
    elif side is None:
        statement += ' Cash-flow direction and fee-adjusted fill cash flow are undetermined without a buy or sell side.'
    elif not comparable:
        statement += ' Price and fee use different units; a fee-adjusted fill amount is unavailable.'
    elif filled == 0:
        statement += ' No filled shares; any reported fee is shown separately.'
    else:
        statement += ' Fee-adjusted fill cash flow is unknown.'
    statement += ' No later event or link to another request is established.'
    accounting = dict(side=side, filled_quantity=filled, remaining_quantity=remaining, gross_filled_notional=principal,
                      price_currency=price_unit, fee_currency=fee_unit, unit_basis=unit_basis,
                      signed_net_fill_cash_flow=signed_net)
    return dict(kind='supplied_event', observation=e, fill_accounting=accounting, statement=statement)


def event_row(e):
    clock = text(e['at'])
    if 'broker_snapshot' in e:
        return snapshot_event(e, clock)
    request = text(e['request'])
    response = e.get('response')
    statement = f'{clock} requested "{request}". '
    if response is None or response == {}:
        statement += f"Transport {e.get('transport','unknown')}; no usable response, so order state is unknown."
    else:
        statement += 'Reported response: ' + json.dumps(response, ensure_ascii=False, default=str) + '.'
    if e.get('broker_submission_performed') is False:
        statement += ' No broker submission was performed.'
    return dict(kind='supplied_event', observation=e, statement=statement)


def render(request, root):
    ref = request['journal']
    doc = decode(read_source(root, ref), exact_numbers=True)
    hashes = {ref['path']:ref['sha256']}
    for source in request.get('supporting_sources', []):
        require(source['path'] not in hashes, 'DUPLICATE_SOURCE')
        hashes[source['path']] = digest(read_source(root, source))
    rows = []
    positions = {}
    currencies = set()
    for field, builder in (('positions', position_row), ('realized_trades', closed_row), ('pending_orders', pending_row)):
        require(isinstance(doc[field], list), 'JOURNAL_LIST_REQUIRED')
        for item in doc[field]:
            currency = item.get('currency', doc.get('currency'))
            row = builder(item)
            row['currency'] = currency
            if currency is not None:
                row['statement'] += f' Monetary unit: {text(currency)}.'
            if field != 'pending_orders':
                currencies.add(currency)
            if field == 'positions':
                require(row['symbol'] not in positions, 'ONE_BASIS_PER_SYMBOL_REQUIRED')
                positions[row['symbol']] = row
            rows.append(row)
    for s in request.get('exit_scenarios', []):
        symbol = text(s['symbol'])
        require(symbol in positions, 'UNKNOWN_EXIT_POSITION')
        row = exit_row(positions[symbol], s)
        row['currency'] = positions[symbol]['currency']
        rows.append(row)
    values = [r['net'] if r['kind'] == 'closed_long' else r['unrealized_pnl']
              for r in rows if r['kind'] in ('marked_long','closed_long')]
    if values and None not in values and len(currencies) == 1:
        unit = currencies.pop()
        total = sum(values)
        scope = f'in {unit}' if unit else 'assuming a common monetary unit, which is unspecified'
        rows.append(dict(kind='listed_component_sum', amount=total, currency=unit,
                         statement=f'Listed unrealized plus realized net P&L is {total} ({scope}). '
                                   'This subtotal excludes hypothetical exits and pending orders. '
                                   'Complete session or portfolio performance is unestablished.'))
    rows.extend(event_row(e) for e in doc.get('events', []))
    limits = ['Prices and order states describe the supplied observations. A stale mark, thin closing liquidity '
              'or wider spread may worsen an exit fill; an overnight gap can increase the remaining loss. '
              'A pending buy can fill and create exposure while unattended. Refresh prices, spreads and order status.',
              'Advisory choices include holding with gap exposure, trimming or closing at available fills, '
              'or reviewing/amending/canceling a pending order after confirming its current status. '
              'Report an amendment or cancellation as completed only after broker acknowledgement. No action has been taken.']
    if doc.get('actual_host_evidence') is False or doc.get('data_kind') == 'explicit_mock_host_observations':
        limits.append('These observations are simulated. Actual host, broker, positions and order state are unavailable.')
    else:
        limits.append('Source authenticity and current host/broker state have not been independently verified.')
    metadata = request.get('metadata', {})
    require(isinstance(metadata,dict) and set(metadata) <= {'case_id','run_id','runtime_model_metadata','evidence_paths'},
            'UNKNOWN_REPORT_METADATA')
    first = ('# Marked positions, trades and pending orders\n\n' +
             '\n\n'.join([r['statement'] for r in rows] + limits) + '\n').encode()
    result = {**metadata, 'method':'marked-position-review-1',
              'candidate_version':(Path(__file__).resolve().parents[1]/'VERSION').read_text().strip(),
              'input_hashes':hashes, 'rows':rows, 'limitations':limits,
              'first_response_sha256':digest(first)}
    return {'first-response.md':first, 'response.json':(json.dumps(result,indent=2,default=str)+'\n').encode()}


def deliver(operation, request, root, output):
    files = render(request, root)
    out = Path(output).absolute()
    require(out == out.resolve() and not any(p.is_symlink() or
            (p.exists() and getattr(p.lstat(),'st_file_attributes',0) & 1024)
            for p in (out,*out.parents)), 'REDIRECTED_OUTPUT_PATH')
    if operation == 'build':
        out.mkdir()
        for name, content in files.items():
            with (out/name).open('xb') as stream:
                stream.write(content)
    require(operation in ('build', 'verify') and out.is_dir() and {p.name for p in out.iterdir()} == set(files)
            and all((out/n).is_file() and not (out/n).is_symlink() and not
                    getattr((out/n).lstat(),'st_file_attributes',0) & 1024 and (out/n).read_bytes() == content
                    for n,content in files.items()), 'MARKED_REPORT_DIFFERS_FROM_SOURCE_REPLAY')
    return {n:digest(content) for n,content in files.items()}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('operation', choices=('build','verify'))
    cli.add_argument('request', type=Path)
    cli.add_argument('source_root', type=Path)
    cli.add_argument('output', type=Path)
    args = cli.parse_args()
    files = deliver(args.operation, decode(args.request.read_bytes(), exact_numbers=True), args.source_root, args.output)
    print(json.dumps({'status':'SOURCE_REPLAY_VERIFIED','files':files}))


if __name__ == '__main__':
    main()
