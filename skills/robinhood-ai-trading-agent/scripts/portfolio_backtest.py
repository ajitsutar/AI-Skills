"""Period-return simulation of a precomputed, timestamped long-only policy.

This is a research accounting simulator, not a tick/queue/order-fill simulator.
Strategy decisions must be retained from a causal walk-forward process outside it.
"""
from __future__ import annotations

import numpy as np

from quant_common import cli, digest, require, scalar, timestamp, vector
from quant_validation import tail_risk


def simulate(document):
    symbols = document['symbols']
    require(symbols and len(set(symbols)) == len(symbols), 'UNIQUE_SYMBOLS')
    n = len(symbols)
    equity = scalar(document['initial_equity'], 'initial_equity', 1e-12)
    holdings = equity*vector(document['initial_weights'], 'initial_weights', n, 0)
    require(holdings.sum() <= equity+1e-9, 'UNLEVERED_INITIAL_WEIGHTS')
    cash = equity-float(holdings.sum())
    floor = scalar(document['cash_floor'], 'cash_floor', 0, 1)
    periods = document['periods']
    require(periods, 'PERIODS_REQUIRED')
    require(document.get('return_basis') == 'total_return_decimal', 'TOTAL_RETURN_BASIS')
    require(document.get('universe_evidence') and document.get('corporate_action_evidence'), 'UNIVERSE_AND_ACTION_EVIDENCE')
    previous_end, records, net_returns, benchmark_returns = None, [], [], []
    costs_paid, traded = 0., 0.
    for row in periods:
        start, end = timestamp(row['start']), timestamp(row['end'])
        require(start < end and (previous_end is None or start == previous_end), 'PERIODS_MUST_BE_CONTIGUOUS')
        previous_end = end
        require(set(row['returns']) == set(symbols), 'RETURN_UNIVERSE_MISMATCH')
        returns = vector([row['returns'][s] for s in symbols], 'total_return', n, -1)
        require(set(row['tradable']) == set(symbols) and all(type(v) is bool for v in row['tradable'].values()), 'TRADABILITY_REQUIRED')
        cash_return = scalar(row['cash_return'], 'cash_return', -1)
        benchmark = scalar(row['benchmark_return'], 'benchmark_return', -1)
        start_equity = cash+float(holdings.sum())
        require(start_equity > 0, 'PORTFOLIO_INSOLVENT')
        trade_cost = 0.
        trade = np.zeros(n)
        if row.get('decision') is not None:
            decision = row['decision']
            require(timestamp(decision['known_at']) < start, 'DECISION_MUST_PRECEDE_RETURN_INTERVAL')
            require(decision.get('evidence_hash'), 'CAUSAL_DECISION_EVIDENCE_REQUIRED')
            target_weights = vector(decision['weights'], 'target_weights', n, 0)
            require(target_weights.sum() <= 1+1e-9, 'UNLEVERED_TARGET_WEIGHTS')
            target = start_equity*target_weights
            trade = target-holdings
            fees = vector(row['one_way_costs'], 'one_way_costs', n, 0)
            impact = vector(row['impact_coefficients'], 'impact_coefficients', n, 0)
            capacity = vector(row['max_trade_values'], 'max_trade_values', n, 0)
            require(np.all(abs(trade) <= capacity+1e-8), 'LIQUIDITY_CAPACITY_EXCEEDED')
            require(all(row['tradable'][s] or abs(trade[i]) < 1e-8 for i, s in enumerate(symbols)), 'TRADE_IN_HALTED_OR_DELISTED_ASSET')
            trade_cost = float(fees @ abs(trade)+impact @ ((abs(trade)/start_equity)**1.5)*start_equity)
            cash = start_equity-float(target.sum())-trade_cost
            require(cash >= floor*start_equity-1e-8, 'CASH_FLOOR_AFTER_COSTS')
            holdings = target
        cash *= 1+cash_return
        holdings *= 1+returns
        equity = cash+float(holdings.sum())
        period_return = equity/start_equity-1
        net_returns.append(period_return)
        benchmark_returns.append(benchmark)
        costs_paid += trade_cost
        traded += float(abs(trade).sum())
        records.append({'start': start.isoformat(), 'end': end.isoformat(), 'equity': equity,
                        'cash': cash, 'net_return': period_return, 'trade_cost': trade_cost,
                        'traded_notional': float(abs(trade).sum())})
    metrics = tail_risk(net_returns)
    benchmark_total = float(np.prod(1+np.array(benchmark_returns))-1)
    return {'status': 'SIMULATED', 'curve': records, 'metrics': metrics,
            'benchmark_total_return': benchmark_total,
            'total_return_difference': metrics['total_return']-benchmark_total,
            'costs_paid': costs_paid, 'gross_traded_notional': traded,
            'input_sha256': digest(document), 'validated_for_live': False,
            'point_in_time_evidence_verified': False,
            'limitation': 'Inputs declare total returns/causal weights. No settlement recycling, market impact calibration, partial fills, queue priority, tax-lot or borrow model. Use event-driven strategy_lab and broker gates for intraday execution.'}


if __name__ == '__main__':
    cli({'simulate': simulate})
