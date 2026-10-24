import copy
from decimal import Decimal, localcontext, Overflow, Inexact
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from paper_exchange import replay


def time(n): return '2026-10-23T14:00:%02dZ'%n
def asset(key='ABC',kind='equity',**extra):
    return dict(id=key,kind=kind,currency='USD',multiplier='1',quantity_step='1',price_tick='0.01',**extra)
def event(eid,kind,n,**extra): return dict(id=eid,type=kind,at=time(n),**extra)
def packet():
    return dict(schema_version=1,environment='paper',base_currency='USD',initial_cash={'USD':'1000'},instruments=[asset()],as_of=time(20),max_quote_age_seconds=60,max_fx_age_seconds=60,events=[
        event('q','quote',0,instrument='ABC',bid='9',ask='10',bid_size='100',ask_size='100'),
        event('o','order',1,order_id='o1',instrument='ABC',side='buy',quantity='10',order_type='market'),
        event('f','fill',2,order_id='o1',quantity='10',price='10',fee='1',settle_at=time(2))])


class PaperExchangeTests(unittest.TestCase):
    def test_funded_purchase_and_nav(self):
        result=replay(packet())
        self.assertEqual(Decimal(result['cash']['USD']),Decimal('899'))
        self.assertEqual(Decimal(result['nav_base']),Decimal('994'))
        self.assertEqual(result['orders']['o1']['state'],'FILLED')
        self.assertFalse(result['production_qualified'])

    def test_input_immutable_and_decimal_context(self):
        p=packet(); old=copy.deepcopy(p); first=replay(p)
        with localcontext() as ctx:
            ctx.prec=4
            self.assertEqual(first,replay(p))
        self.assertEqual(p,old)

    def test_exact_duplicate_and_conflict(self):
        p=packet(); p['events'].append(copy.deepcopy(p['events'][-1]))
        r=replay(p);self.assertEqual(r['events_applied'],3);self.assertEqual(r['duplicate_event_ids_ignored'],['f'])
        p['events'][-1]['fee']='2'
        with self.assertRaisesRegex(ValueError,'CONFLICTING_DUPLICATE'):replay(p)

    def test_restart_from_full_journal(self):
        p=packet(); prefix=copy.deepcopy(p);prefix['events']=p['events'][:2]
        self.assertEqual(replay(prefix)['orders']['o1']['state'],'OPEN')
        self.assertEqual(replay(p),replay(copy.deepcopy(p)))

    def test_stale_future_and_same_time(self):
        for change,expected in [(lambda p:p.update(max_quote_age_seconds=1),'STALE'),(lambda p:p.update(as_of=time(1)),'CUTOFF'),(lambda p:p['events'][-1].update(at=time(1)),'FOLLOW_ORDER')]:
            p=packet();change(p)
            with self.assertRaisesRegex(ValueError,expected):replay(p)

    def test_overfill_off_grid_and_quote_liquidity(self):
        for change,expected in [(lambda p:p['events'][-1].update(quantity='11'),'OVERFILL'),(lambda p:p['events'][-1].update(quantity='1.5'),'OFF_GRID'),(lambda p:p['events'][0].update(ask_size='5'),'LIQUIDITY')]:
            p=packet();change(p)
            with self.assertRaisesRegex(ValueError,expected):replay(p)

    def test_liquidity_consumed_by_multiple_fills(self):
        p=packet();p['events'][0]['ask_size']='8';p['events'][-1]['quantity']='5'
        p['events'].append(event('f2','fill',3,order_id='o1',quantity='5',price='10',fee='0',settle_at=time(3)))
        with self.assertRaisesRegex(ValueError,'LIQUIDITY'):replay(p)

    def test_cancel_race_partial_fill_and_ack(self):
        p=packet();p['events'][-1]['quantity']='3'
        p['events'] += [event('cr','cancel_request',3,order_id='o1'),event('f2','fill',4,order_id='o1',quantity='2',price='10',fee='0',settle_at=time(4)),event('ca','cancel_ack',5,order_id='o1')]
        r=replay(p);self.assertEqual(r['orders']['o1']['filled'],'5');self.assertEqual(r['orders']['o1']['state'],'CANCELLED')
        p['events'].append(event('late','fill',6,order_id='o1',quantity='1',price='10',fee='0',settle_at=time(6)))
        with self.assertRaisesRegex(ValueError,'NOT_FILLABLE'):replay(p)

    def test_limit_never_inferred_filled_from_touch(self):
        p=packet();p['events']=p['events'][:2];p['events'][1].update(order_type='limit',limit_price='10')
        self.assertEqual(replay(p)['positions']['ABC'],'0')
        p['events'].append(event('f','fill',2,order_id='o1',quantity='10',price='11',fee='0',settle_at=time(2)))
        with self.assertRaisesRegex(ValueError,'LIMIT_BREACH'):replay(p)

    def test_sale_cash_is_pending_until_settled(self):
        p=packet();p['events'] += [event('s','order',3,order_id='s',instrument='ABC',side='sell',quantity='10',order_type='market'),event('sf','fill',4,order_id='s',quantity='10',price='9',fee='1',settle_at=time(10))]
        r=replay(p);self.assertEqual(r['cash']['USD'],'899');self.assertEqual(r['pending_cash']['sf']['amount'],'89');self.assertEqual(r['nav_base'],'988')
        p['events'].append(event('settle','settle_cash',10,fill_id='sf'))
        self.assertEqual(replay(p)['cash']['USD'],'988')
        p['events'][-1]['at']=time(9)
        with self.assertRaisesRegex(ValueError,'NOT_DUE'):replay(p)

    def test_insufficient_cash_and_no_funded_short(self):
        p=packet();p['initial_cash']['USD']='50'
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT'):replay(p)
        p=packet();p['events'][1]['side']='sell';p['events'][-1]['price']='9'
        with self.assertRaisesRegex(ValueError,'SHORTING'):replay(p)

    def test_futures_negative_price_variation_and_margin(self):
        p=packet();p['instruments']=[asset(kind='future',expiry=time(50),margin_per_contract='20')]
        p['events'][0].update(bid='-11',ask='-10');p['events'][-1]['price']='-10'
        p['events'].append(event('vm','futures_settlement',3,instrument='ABC',price='-8',margin_per_contract='20',final=False))
        p['events'].append(event('q2','quote',4,instrument='ABC',bid='-8',ask='-8',bid_size='100',ask_size='100'))
        r=replay(p);self.assertEqual(r['cash']['USD'],'1019');self.assertEqual(r['nav_base'],'1019')
        p['events'][-2]['margin_per_contract']='200'
        with self.assertRaisesRegex(ValueError,'COLLATERAL'):replay(p)

    def test_futures_final_settlement_clears_position(self):
        p=packet();p['instruments']=[asset(kind='future',expiry=time(10),margin_per_contract='20')]
        p['events'].append(event('vm','futures_settlement',10,instrument='ABC',price='12',margin_per_contract='20',final=True))
        r=replay(p);self.assertEqual(r['cash']['USD'],'1019');self.assertEqual(r['positions']['ABC'],'0')

    def test_funded_fx_two_currency_accounting(self):
        p=packet();p['events']=[event('x','fx_convert',1,from_currency='USD',to_currency='EUR',amount='100',rate='0.9',fee='1'),event('r','fx_rate',2,currency='EUR',rate_to_base='1.111111111111111111111111111111111')]
        r=replay(p);self.assertEqual(r['cash'],{'USD':'899','EUR':'90.0'});self.assertAlmostEqual(float(r['nav_base']),999)
        p['max_fx_age_seconds']=1
        with self.assertRaisesRegex(ValueError,'STALE_FX'):replay(p)

    def test_split_invalidates_old_quote(self):
        p=packet();p['events'].append(event('split','split',3,instrument='ABC',ratio='2'))
        with self.assertRaisesRegex(ValueError,'QUOTE_REQUIRED'):replay(p)
        p['events'].append(event('newq','quote',4,instrument='ABC',bid='4.5',ask='5',bid_size='100',ask_size='100'))
        r=replay(p);self.assertEqual(r['positions']['ABC'],'20');self.assertEqual(r['nav_base'],'994.00')

    def option_packet(self):
        p=packet();o=asset('OPT','option',expiry=time(10),underlying='ABC',strike='8',right='call',exercise_style='american',settlement_type='physical');o['multiplier']='100'
        p['instruments'].append(o);p['initial_cash']['USD']='2000'
        p['events']=[event('u','quote',0,instrument='ABC',bid='9',ask='10',bid_size='100',ask_size='100'),event('q','quote',0,instrument='OPT',bid='1',ask='2',bid_size='10',ask_size='10'),event('o','order',1,order_id='o1',instrument='OPT',side='buy',quantity='1',order_type='market'),event('f','fill',2,order_id='o1',quantity='1',price='2',fee='1',settle_at=time(2))]
        return p

    def test_long_option_physical_exercise_conservation(self):
        p=self.option_packet();p['events'].append(event('ex','option_exercise',10,instrument='OPT',quantity='1'))
        r=replay(p);self.assertEqual(r['cash']['USD'],'999');self.assertEqual(r['positions']['ABC'],'100');self.assertEqual(r['positions']['OPT'],'0');self.assertEqual(r['nav_base'],'1949.0')

    def test_option_cannot_silently_expire_in_money(self):
        p=self.option_packet();p['events'].append(event('ex','option_expiry',10,instrument='OPT',underlying_settlement_price='10'))
        with self.assertRaisesRegex(ValueError,'EXPLICIT_EXERCISE'):replay(p)
        p['instruments'][1]['settlement_type']='cash'
        r=replay(p);self.assertEqual(r['cash']['USD'],'1999')

    def test_split_rejects_unheld_but_tradable_option_definitions(self):
        p=self.option_packet();p['as_of']=time(9);p['events']=p['events'][:3]
        p['events'].append(event('s','split',2,instrument='ABC',ratio='2'))
        with self.assertRaisesRegex(ValueError,'DELIVERABLE_ADJUSTMENT'):replay(p)
        p['events']=p['events'][:2]+[p['events'][-1]]
        with self.assertRaisesRegex(ValueError,'DELIVERABLE_ADJUSTMENT'):replay(p)

    def test_early_european_exercise_and_unresolved_expiry(self):
        p=self.option_packet()
        with self.assertRaisesRegex(ValueError,'EXPIRED'):replay(p)
        p['instruments'][1]['exercise_style']='european';p['events'].append(event('ex','option_exercise',5,instrument='OPT',quantity='1'))
        with self.assertRaisesRegex(ValueError,'EARLY_EUROPEAN'):replay(p)

    def test_bond_coupon_entitlement_and_redemption(self):
        p=packet();p['instruments']=[asset(kind='bond',expiry=time(10))]
        p['events'] += [event('coupon','distribution',3,instrument='ABC',entitled_quantity='10',amount_per_unit='0.5'),event('redeem','bond_redemption',10,instrument='ABC',principal_per_unit='10')]
        r=replay(p);self.assertEqual(r['cash']['USD'],'1004.0');self.assertEqual(r['positions']['ABC'],'0')

    def test_crypto_fractional_quantity(self):
        p=packet();p['instruments'][0].update(kind='crypto',quantity_step='0.001');p['events'][1]['quantity']='0.125';p['events'][2]['quantity']='0.125'
        self.assertEqual(replay(p)['positions']['ABC'],'0.125')

    def test_unknown_keys_and_live_mode_rejected(self):
        p=packet();p['environment']='live'
        with self.assertRaisesRegex(ValueError,'PAPER_ONLY'):replay(p)
        p=packet();p['events'][0]['secret']='unused'
        with self.assertRaisesRegex(ValueError,'UNKNOWN_FIELDS'):replay(p)

    def test_malformed_timezone_offsets_rejected(self):
        for timestamp in ['2026-10-23T14:00:20+00:99','2026-10-23T14:00:20+01:60','2026-W43-5T14:00:20Z']:
            p=packet();p['as_of']=timestamp
            with self.assertRaisesRegex(ValueError,'EXACT_AWARE'):replay(p)

    def test_all_ambient_decimal_controls_are_isolated(self):
        p=packet();expected=replay(p)
        with localcontext() as ctx:
            ctx.Emax=2;ctx.Emin=-2;ctx.prec=2;ctx.clamp=1
            ctx.traps[Overflow]=False;ctx.traps[Inexact]=True
            self.assertEqual(replay(p),expected)
            self.assertEqual(ctx.Emax,2)
            self.assertTrue(ctx.traps[Inexact])

    def test_extreme_cash_is_a_controlled_rejection(self):
        for amount in ('1e1000000','1e-1000000'):
            p=packet();p['initial_cash']['USD']=amount
            with self.assertRaisesRegex(ValueError,'DECIMAL_EXPONENT_RANGE'):replay(p)


if __name__=='__main__':unittest.main()
