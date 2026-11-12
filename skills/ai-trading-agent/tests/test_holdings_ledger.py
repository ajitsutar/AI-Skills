import copy
import sys
import unittest
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from holdings_ledger import replay

T0='2026-01-01T00:00:00Z'; T1='2026-01-02T00:00:00Z'; T2='2026-01-03T00:00:00Z'; T3='2026-01-04T00:00:00Z'
def mark(s,p,t=T0,kind='observed'):
    return dict(security_id=s,price=str(p),kind=kind,observed_at=t,available_at=t,source='fictional-fixture')
def base():
    return dict(currency='USD',as_of=T3,price_basis='unadjusted',valuation_policy='observed_only',tax_mode='explicit_event_amounts',equal_time_order='supplied_order',opening=dict(at=T0,cash='100',lots=[dict(lot_id='a',security_id='P',quantity='10',basis='500',acquired_at=T0)],marks=[mark('P',100)]),events=[])
def event(k,**kw):return dict(id=k,type=k,at=T1,source='fictional-fixture',**kw)

class HoldingsLedgerTests(unittest.TestCase):
    def test_spinoff_parent_sale_retains_child_and_basis(self):
        d=base();d['events']=[event('spinoff',security_id='P',child_security_id='C',child_ratio='.5',child_basis_fraction='.2',tax_amount='0'),dict(event('mark'),**mark('P',90,T1)),dict(event('mark'),id='childmark',**mark('C',20,T1)),event('sell',security_id='P',quantity='10',price='90',cost='0',lots=['a'],execution_price_basis='observed',settles_at=T2,tax_amount='0')]
        d['events'][1]['id']='parentmark'
        r=replay(d);self.assertEqual(r['final']['settled_cash'],'1000');self.assertEqual(r['final']['positions']['C']['quantity'],'5.0');self.assertEqual(r['lots'][0]['basis'],'100.0');self.assertEqual(r['final']['gross_nav'],'1100.0');self.assertEqual(r['realizations'][0]['realized_gain'],'500.0')

    def test_unquoted_child_not_zero_and_reference_optin(self):
        d=base();d['events']=[event('spinoff',security_id='P',child_security_id='C',child_ratio='.5',child_basis_fraction=None,tax_amount='0'),dict(event('mark'),**mark('P',90,T1))]
        self.assertIsNone(replay(d)['final']['gross_nav'])
        d['events'].append(dict(event('mark'),id='childmark',**mark('C',20,T1,'reference')))
        self.assertIsNone(replay(d)['final']['gross_nav']);d['valuation_policy']='allow_references'
        self.assertEqual(replay(d)['final']['valuation_status'],'REFERENCE_OR_MODEL_SCENARIO')

    def test_split_preserves_basis_and_requires_new_mark(self):
        d=base();d['events']=[event('split',security_id='P',factor='2')]
        r=replay(d);self.assertEqual(r['lots'][0]['quantity'],'20');self.assertEqual(r['lots'][0]['basis'],'500');self.assertIsNone(r['final']['gross_nav'])
        d['events'].append(dict(event('mark'),**mark('P',50,T1)));self.assertEqual(replay(d)['final']['gross_nav'],'1100')

    def test_special_dividend_cash_and_receivable_conservation(self):
        d=base();d['events']=[event('dividend',security_id='P',dividend_type='special',per_unit='10',settles_at=T3,tax_amount='0'),dict(event('mark'),**mark('P',90,T1))]
        r=replay(d);self.assertEqual(r['timeline'][1]['cash_receivables'],'100');self.assertEqual(r['final']['gross_nav'],'1100');self.assertEqual(r['cash_and_receivable_conservation_residual'],'0')

    def test_unsettled_sales_cannot_buy(self):
        d=base();d['events']=[event('sell',security_id='P',quantity='10',price='100',cost='0',lots=['a'],execution_price_basis='observed',settles_at=T3,tax_amount='0'),event('buy',security_id='C',quantity='20',price='50',cost='0',lot_id='b',execution_price_basis='observed',settles_at=T3)]
        with self.assertRaisesRegex(ValueError,'INSUFFICIENT_SETTLED'):replay(d)

    def test_tax_reserve_not_double_subtracted_and_funded_withdrawal(self):
        d=base();d['tax_mode']='positive_sale_gains';d['events']=[event('sell',security_id='P',quantity='10',price='100',cost='10',lots=['a'],execution_price_basis='observed',settles_at=T2,tax_rate='.2'),dict(event('tax_payment',amount='98'),at=T2),dict(event('withdrawal',amount='992'),at=T3)]
        r=replay(d);self.assertEqual(Decimal(r['final']['settled_cash']),0);self.assertEqual(Decimal(r['final']['declared_tax_liability']),0);self.assertEqual(Decimal(r['cash_and_receivable_conservation_residual']),0)
        d['events']=d['events'][:1];r=replay(d);self.assertEqual(r['final']['gross_nav'],'1090');self.assertEqual(r['final']['net_nav_after_declared_tax'],'992.0');self.assertEqual(r['final']['cash_available_after_tax_reserve'],'992.0')

    def test_unknown_tax_remains_unknown(self):
        d=base();d['tax_mode']='positive_sale_gains';d['events']=[event('sell',security_id='P',quantity='1',price='100',cost='0',lots=['a'],execution_price_basis='observed',settles_at=T2)]
        r=replay(d);self.assertIsNone(r['final']['net_nav_after_declared_tax']);self.assertEqual(r['status'],'UNRESOLVED')

    def test_tax_evidence_missing_versus_explicit_zero(self):
        d=base();d['events']=[event('sell',security_id='P',quantity='1',price='100',cost='0',lots=['a'],execution_price_basis='observed',settles_at=T2)]
        original=copy.deepcopy(d);unknown=replay(d)
        self.assertEqual(d,original)
        row=unknown['tax_evidence']['events'][0]
        self.assertEqual(row['event_pointer'],'/events/0')
        self.assertEqual(row['missing_inputs'],['tax_amount'])
        self.assertEqual(row['source_pointers'],[])
        self.assertIsNone(row['amount'])
        self.assertIsNone(unknown['tax_evidence']['total_scenario_liability_remaining'])
        d['events'][0]['tax_amount']='0';known=replay(d)
        row=known['tax_evidence']['events'][0]
        self.assertEqual(row['amount'],'0')
        self.assertEqual(row['tax_treatment'],'EXPLICIT_EVENT_AMOUNT')
        self.assertEqual(row['source_pointers'],['/events/0/tax_amount'])
        self.assertEqual(known['tax_evidence']['total_scenario_liability_remaining'],'0')
        self.assertIsNone(known['tax_evidence']['actual_tax_liability_amount'])
        self.assertEqual(unknown['final']['settled_cash'],known['final']['settled_cash'])
        self.assertIsNone(unknown['final']['net_nav_after_declared_tax'])
        self.assertIsNotNone(known['final']['net_nav_after_declared_tax'])

    def test_paid_declared_tax_and_comparator_deltas_do_not_resolve_missing_tax(self):
        d=base();d['opening']['tax_liability']='7'
        d['events']=[event('sell',security_id='P',quantity='1',price='100',cost='0',lots=['a'],execution_price_basis='observed',settles_at=T2),
                     event('tax_accrual',amount='4'),dict(event('tax_payment',amount='11'),at=T2)]
        target=replay(d);tax=target['tax_evidence']
        self.assertEqual(tax['opening_declared_liability'],{'amount':'7','source_pointer':'/opening/tax_liability','basis':'SUPPLIED'})
        self.assertEqual(tax['declared_accrual_total'],'4')
        self.assertEqual(tax['declared_payment_total'],'11')
        self.assertEqual(tax['declared_liability_remaining'],'0')
        self.assertEqual(tax['unresolved_event_ids'],['sell'])
        self.assertIsNone(tax['unresolved_scenario_liability_amount'])
        self.assertIsNone(tax['total_scenario_liability_remaining'])
        self.assertFalse(target['conclusion_facts']['unresolved_tax_amount_known'])
        self.assertIsNone(target['final']['net_nav_after_declared_tax'])
        for supplied_tax in ('13','29'):
            comparator=copy.deepcopy(d)
            comparator['events'][0]['tax_amount']=supplied_tax
            comparator['events'][2]['amount']=str(Decimal('11')+Decimal(supplied_tax))
            compared=replay(comparator)
            self.assertEqual(Decimal(target['final']['settled_cash'])-Decimal(compared['final']['settled_cash']),Decimal(supplied_tax))
            self.assertEqual(Decimal(compared['tax_evidence']['declared_payment_total'])-Decimal(tax['declared_payment_total']),Decimal(supplied_tax))
            self.assertEqual(replay(d)['tax_evidence'],tax)
            self.assertIsNone(tax['events'][0]['amount'])

    def test_rate_tax_evidence_and_missing_inputs(self):
        d=base();d['tax_mode']='positive_sale_gains'
        d['events']=[event('sell',security_id='P',quantity='1',price='100',cost='0',lots=['a'],execution_price_basis='observed',settles_at=T2,tax_rate='.3')]
        result=replay(d);row=result['tax_evidence']['events'][0]
        self.assertEqual(Decimal(row['amount']),Decimal('15'))
        self.assertEqual(row['tax_treatment'],'POSITIVE_GAIN_RATE_SCENARIO')
        self.assertEqual(row['source_pointers'],['/events/0/tax_rate'])
        self.assertEqual(row['derived_inputs']['result_pointer'],'/realizations/0/realized_gain')
        self.assertEqual(row['derived_inputs']['realized_gain'],result['realizations'][0]['realized_gain'])
        self.assertEqual(result['tax_evidence']['opening_declared_liability']['basis'],'DOCUMENTED_ZERO_DEFAULT')
        self.assertIsNone(result['tax_evidence']['opening_declared_liability']['source_pointer'])
        d['opening']['lots'][0]['basis']=None
        row=replay(d)['tax_evidence']['events'][0]
        self.assertEqual(row['missing_inputs'],['realized_gain']);self.assertIsNone(row['amount'])
        del d['events'][0]['tax_rate']
        self.assertEqual(replay(d)['tax_evidence']['events'][0]['missing_inputs'],['tax_rate','realized_gain'])

    def test_unmodeled_tax_evidence_does_not_promote_supplied_amount(self):
        d=base();d['tax_mode']='unmodeled'
        d['events']=[event('sell',security_id='P',quantity='1',price='100',cost='0',lots=['a'],execution_price_basis='observed',settles_at=T2,tax_amount='19')]
        r=replay(d);tax=r['tax_evidence']
        self.assertEqual(tax['events'][0]['tax_treatment'],'UNMODELED')
        self.assertIsNone(tax['events'][0]['amount'])
        self.assertEqual(tax['declared_accrual_total'],'0')
        self.assertEqual(tax['unresolved_event_ids'],['TAXES_NOT_MODELED'])
        self.assertIsNone(tax['total_scenario_liability_remaining'])

    def test_cash_stock_merger_and_terminal_zero(self):
        d=base();d['events']=[event('merger',security_id='P',child_security_id='C',child_ratio='2',cash_per_unit='5',settles_at=T2,terminal_outcome_confirmed=True,child_basis_by_parent_lot={'a':'450'},tax_amount='0'),dict(event('mark'),**mark('C',45,T1))]
        r=replay(d);self.assertEqual(r['final']['settled_cash'],'150');self.assertEqual(r['final']['positions']['C']['quantity'],'20');self.assertEqual(r['final']['gross_nav'],'1050')
        d=base();d['events']=[event('delisting',security_id='P',cash_per_unit='0',settles_at=T2,terminal_outcome_confirmed=True,tax_amount='0')];self.assertEqual(replay(d)['final']['gross_nav'],'100')
        d['events'][0]['terminal_outcome_confirmed']=False
        with self.assertRaisesRegex(ValueError,'UNCONFIRMED'):replay(d)

    def test_cash_in_lieu_and_nonexecution_marks(self):
        d=base();d['events']=[event('cash_in_lieu',security_id='P',quantity='.5',price='100',cost='0',lots=['a'],execution_price_basis='observed',settles_at=T2,tax_amount='0')]
        self.assertEqual(replay(d)['lots'][0]['quantity'],'9.5')
        d['events'][0]['execution_price_basis']='reference'
        with self.assertRaisesRegex(ValueError,'NONEXECUTABLE'):replay(d)

    def test_double_adjustment_future_mark_and_mutation(self):
        d=base();original=copy.deepcopy(d);replay(d);self.assertEqual(d,original)
        d['price_basis']='adjusted'
        with self.assertRaisesRegex(ValueError,'DOUBLE_COUNT'):replay(d)
        d=base();d['opening']['marks'][0]['available_at']=T1
        with self.assertRaisesRegex(ValueError,'FUTURE_MARK'):replay(d)

if __name__=='__main__':unittest.main()
