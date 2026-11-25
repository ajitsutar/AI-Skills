import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from marked_position_review import deliver, digest, render


class MarkedPositionReviewTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.journal = {
            'positions':[{'symbol':'ALPHA','quantity':7,'basis_per_share':18,'current_mark':16,'as_of':'14:55 UTC'}],
            'pending_orders':[{'symbol':'BETA','side':'buy','quantity':5,'limit_price':12,'status':'accepted'}],
            'realized_trades':[{'symbol':'GAMMA','quantity':3,'buy_price':14,'sell_price':15,'fees':'0.25'}],
            'actual_host_evidence':False}
        self.request = {'exit_scenarios':[{'symbol':'ALPHA','quantity':3,'fill_price':15,'exit_fees':'0.30'}],
                        'metadata':{'case_id':'portfolio-note','runtime_model_metadata':{'host':'offline'},
                                    'evidence_paths':['journal.json']}}
        self.bind()

    def bind(self):
        raw = json.dumps(self.journal).encode()
        (self.root/'journal.json').write_bytes(raw)
        self.request['journal'] = {'path':'journal.json','sha256':digest(raw)}

    def result(self):
        files = render(self.request, self.root)
        result = json.loads(files['response.json'])
        prose = files['first-response.md'].decode()
        self.assertEqual(digest(files['first-response.md']), result['first_response_sha256'])
        self.assertTrue(all(row['statement'] in prose for row in result['rows']))
        self.assertTrue(all(s in prose for s in result['limitations']))
        return {r['kind']:r for r in result['rows']}, prose, result

    def test_delivered_partial_exit_at_changed_fill_and_fees(self):
        rows, prose, result = self.result()
        self.assertTrue({'case_id','candidate_version','runtime_model_metadata','input_hashes',
                         'rows','limitations','evidence_paths'} <= result.keys())
        self.assertEqual(rows['marked_long']['unrealized_pnl'], '-14')
        self.assertEqual(rows['closed_long']['net'], '2.75')
        self.assertEqual(rows['listed_component_sum']['amount'], '-11.25')
        exit_row = rows['hypothetical_exit']
        self.assertEqual((exit_row['gross_realized'],exit_row['net_realized'],exit_row['remaining_unrealized_at_mark']),
                         ('-9','-9.30','-8'))
        self.assertIn('full exit at the mark would realize -14 before exit fees', prose)
        self.assertIn('exit of 3 at 15: gross realized P&L -9, exit fees 0.30, net -9.30', prose)
        self.assertIn('Remaining 4 shares at the supplied mark have unrealized P&L -8', prose)
        self.assertIn('assuming a common monetary unit', prose)
        self.assertIn('completed only after broker acknowledgement', prose)
        self.assertIn('Actual host, broker, positions and order state are unavailable', prose)

    def test_unknown_fees_and_pending_acceptance(self):
        del self.request['exit_scenarios'][0]['exit_fees']
        del self.journal['realized_trades'][0]['fees']
        self.bind()
        rows, prose, _ = self.result()
        self.assertNotIn('listed_component_sum', rows)
        self.assertIsNone(rows['hypothetical_exit']['net_realized'])
        self.assertIsNone(rows['closed_long']['net'])
        p = rows['pending_buy_limit']
        self.assertEqual(p['maximum_full_order_principal'], '60')
        for key in ('filled_quantity','filled_principal','remaining_quantity'):
            self.assertIsNone(p[key])
        self.assertIn('Actual filled quantity, principal and remaining quantity are unconfirmed', prose)
        self.assertIn('exit fees and net result unknown', prose)

    def test_confirmed_partial_buy_and_separate_unlinked_snapshot(self):
        self.journal['pending_orders'][0].update(status='partially_filled',cumulative_filled=2,average_price=11,fee='0.15')
        self.journal['events']=[{'at':'12:05Z','broker_snapshot':{'id':'Z','status':'partially_filled',
                              'requested_quantity':6,'cumulative_filled':1,'average_price':9,'fee':'0.2'}}]
        self.bind()
        rows, prose, _ = self.result()
        p = rows['pending_buy_limit']
        self.assertEqual((p['filled_principal'],p['filled_cost_including_reported_fees'],
                          p['maximum_additional_principal']),('22','22.15','36'))
        self.assertIn('Observed filled principal 22',prose)
        self.assertIn('Reported filled principal plus fees 22.15',prose)
        self.assertIn('supplied snapshot Z, partially_filled: 1 of 6 filled, 5 remaining',prose)
        self.assertEqual(rows['listed_component_sum']['amount'],'-11.25')
        snapshot = rows['supplied_event']['fill_accounting']
        self.assertEqual(snapshot['gross_filled_notional'], '9')
        self.assertIsNone(snapshot['side'])
        self.assertIsNone(snapshot['signed_net_fill_cash_flow'])
        self.assertIn('Snapshot side unknown. Gross filled notional 9.', prose)

    def snapshot_result(self, **fields):
        snap = dict(id='EXAMPLE', status='reported', requested_quantity=3)
        snap.update(fields)
        self.journal['events'] = [{'at':'10:00Z', 'request':'buy unrelated shares', 'response':{}},
                                  {'at':'10:01Z', 'broker_snapshot':snap}]
        self.bind()
        rows, _, _ = self.result()
        row = rows['supplied_event']
        return row['fill_accounting'], row['statement']

    def test_side_specific_fill_cash_flow_and_unit_basis(self):
        for side, signed in [(' BUY ', '-6.45'), ('sell', '6.05')]:
            with self.subTest(side=side):
                a, s = self.snapshot_result(side=side, cumulative_filled='1.25', average_price=5,
                                            fee='0.20', currency='CAD')
                self.assertEqual((a['side'], a['remaining_quantity'], a['gross_filled_notional'],
                                  a['signed_net_fill_cash_flow']), (side.strip().lower(), '1.75', '6.25', signed))
                self.assertEqual(a['unit_basis'], 'reported_common_unit')
                self.assertIn(f'fill cash flow {signed} (in CAD', s)
        a, s = self.snapshot_result(side='sell', cumulative_filled=3, average_price=2, fee=0)
        self.assertEqual((a['signed_net_fill_cash_flow'], a['remaining_quantity']), ('6','0'))
        self.assertIn('assuming price and fee share a monetary unit', s)
        a, s = self.snapshot_result(side='sell', cumulative_filled=1, average_price=2, fee=3, currency='GBP')
        self.assertEqual(a['signed_net_fill_cash_flow'], '-1')
        self.assertIn('positive is a credit, negative a debit', s)

        for missing in (None, '', '  ', 'unknown'):
            for price_unit, fee_unit in ((missing, 'USD'), ('USD', missing)):
                with self.subTest(price_unit=price_unit, fee_unit=fee_unit):
                    a, statement = self.snapshot_result(
                        side='sell', cumulative_filled=1, average_price=100, fee=2,
                        currency='CAD', price_currency=price_unit, fee_currency=fee_unit)
                    self.assertEqual({a['price_currency'], a['fee_currency']}, {'CAD', 'USD'})
                    self.assertEqual(a['unit_basis'], 'different_reported_units')
                    self.assertIsNone(a['signed_net_fill_cash_flow'])
                    self.assertIn('different units', statement)

    def test_unknown_or_absent_side_never_inherits_another_order(self):
        for fields in ({}, {'side':None}, {'side':'unrecognized'}):
            with self.subTest(fields=fields):
                a, s = self.snapshot_result(**fields, cumulative_filled='1.5', average_price=8, fee=2)
                self.assertEqual(a['gross_filled_notional'], '12.0')
                self.assertIsNone(a['signed_net_fill_cash_flow'])
                self.assertIsNone(a['side'])
                self.assertIn('undetermined without a buy or sell side', s)

    def test_incomplete_or_zero_quantity_price_and_fee_and_different_units(self):
        for fields, principal in [
            ({'cumulative_filled':1}, None),
            ({'cumulative_filled':1, 'average_price':0, 'fee':2}, None),
            ({'average_price':8, 'fee':1}, None),
            ({'cumulative_filled':0, 'fee':1}, '0'),
            ({'cumulative_filled':1, 'average_price':8}, '8'),
            ({'cumulative_filled':1, 'average_price':'unavailable', 'fee':1}, None),
            ({'cumulative_filled':1, 'average_price':8, 'fee':'unknown'}, '8'),
            ({'cumulative_filled':1, 'average_price':8, 'fee':1, 'price_currency':'CAD','fee_currency':'EUR'}, '8'),
        ]:
            with self.subTest(fields=fields):
                a, s = self.snapshot_result(side='buy', **fields)
                self.assertEqual(a['gross_filled_notional'], principal)
                self.assertIsNone(a['signed_net_fill_cash_flow'])
                self.assertNotIn('Fee-adjusted fill cash flow -', s)
                if fields.get('fee_currency') == 'EUR':
                    self.assertEqual(a['unit_basis'], 'different_reported_units')
                    self.assertIn('different units', s)
        with self.assertRaisesRegex(ValueError, 'SNAPSHOT_OVERFILL'):
            self.snapshot_result(side='sell', cumulative_filled=4, average_price=2, fee=1)

    def test_mixed_currencies_stay_separate_and_hypotheses_do_not_replace_fills(self):
        self.journal['positions'][0]['currency']='CAD'
        self.journal['realized_trades'][0]['currency']='USD'
        self.request['exit_scenarios'].append({'symbol':'ALPHA','quantity':7,'fill_price':20,'exit_fees':1})
        self.bind()
        rows, prose, _ = self.result()
        self.assertNotIn('listed_component_sum',rows)
        self.assertIn('exit of 7 at 20: gross realized P&L 14, exit fees 1, net 13',prose)
        self.assertIn('Remaining 0 shares',prose)

    def test_invalid_quantity_overfill_and_sell_limit(self):
        self.request['exit_scenarios'][0]['quantity']=8
        with self.assertRaisesRegex(ValueError,'EXIT_EXCEEDS'):
            self.result()
        self.request['exit_scenarios']=[]
        for update in ({'side':'sell'},{'side':'buy','cumulative_filled':6},
                       {'side':'buy','cumulative_filled':2,'average_price':13}):
            self.journal['pending_orders'][0].update(update)
            self.bind()
            with self.assertRaises(ValueError):
                self.result()

    def test_verify_complete_rendered_outputs_and_source_bytes(self):
        out = self.root/'out'
        pins = deliver('build',self.request,self.root,out)
        self.assertEqual(pins,deliver('verify',self.request,self.root,out))
        for name in pins:
            path=out/name
            original=path.read_bytes()
            path.write_bytes(original+b' ')
            with self.assertRaisesRegex(ValueError,'DIFFERS_FROM_SOURCE'):
                deliver('verify',self.request,self.root,out)
            path.write_bytes(original)
        (self.root/'journal.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):
            deliver('verify',self.request,self.root,out)


if __name__ == '__main__':
    unittest.main()
