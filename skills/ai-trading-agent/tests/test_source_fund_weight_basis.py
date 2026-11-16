"""Exact source fund fractions keep total-fund and immediate-list denominators separate."""
from copy import deepcopy
from decimal import Decimal, Inexact, Rounded, localcontext
from fractions import Fraction
from pathlib import Path
import hashlib
import json
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import source_exposure
import quant_workbench


def fixture(weights=('0.21','0.14'), coverage='0.35'):
    fund={'symbol':'FUND-X','holdings_as_of':'2033-04-05',
          'holdings':[{'symbol':'ALPHA','weight':weights[0]}, {'symbol':'BETA','weight':weights[1]}]}
    if coverage is not None:fund['holdings_coverage']=coverage
    return {'currency':'USD','identities':{'ALPHA':{'issuer_id':'issuer-a','sector':'services','kind':'common_stock'},
            'BETA':{'issuer_id':'issuer-b','sector':'transport','kind':'common_stock'}},'funds':[fund]}


def document(source=None, rows=None):
    text=json.dumps(fixture() if source is None else source,separators=(',',':'))
    return {'schema_version':1,'currency':'USD','role':'supplied_observation',
            'denominator':{'amount':'200','basis':'supplied account'},
            'rows':[{'id':'owned','symbol':'ALPHA','notional':'40','notional_basis':'gross_notional'}] if rows is None else rows,
            'sources':[{'id':'original','text':text,'sha256':hashlib.sha256(text.encode()).hexdigest(),
                        'role':'supplied_observation','provenance':{'label':'fictional source'},
                        'adapter':'portfolio_context_v1','bindings':{'root':''}}]}


def replace_text(doc, old, new):
    doc=deepcopy(doc);source=doc['sources'][0];assert old in source['text']
    source['text']=source['text'].replace(old,new)
    source['sha256']=hashlib.sha256(source['text'].encode()).hexdigest()
    return doc


def basis(doc):return source_exposure.source_allocation_context(doc)['fund_context'][0]['weight_basis_evidence']


class FundWeightBasisTests(unittest.TestCase):
    def test_partial_coverage_keeps_two_denominators(self):
        result=source_exposure.source_allocation_context(document());item=result['fund_context'][0]['weight_basis_evidence']
        row=item['rows'][0]
        self.assertEqual(Decimal(row['total_fund_fraction']['percent']),Decimal('21'))
        self.assertEqual(Decimal(row['supplied_slice_fraction']['percent']),Decimal('60'))
        self.assertEqual(row['total_fund_fraction']['denominator'],'1')
        self.assertEqual(row['supplied_slice_fraction']['denominator'],'0.35')
        self.assertEqual(item['coverage']['unrepresented_total_fund_fraction'],'0.65')
        self.assertFalse(item['account_notional_added'])
        self.assertIn('TOTAL_FUND_WEIGHT',result['fund_weight_report'])
        self.assertIn('SUPPLIED_IMMEDIATE_HOLDINGS_WEIGHT_SUM',result['fund_weight_report'])
        self.assertIn('60%',result['fund_weight_report'])

    def test_full_coverage_equal_fractions_distinct_bases(self):
        row=basis(document(fixture(('0.25','0.75'),'1')))['rows'][0]
        self.assertEqual(Decimal(row['total_fund_fraction']['fraction']),Decimal(row['supplied_slice_fraction']['fraction']))
        self.assertNotEqual(row['total_fund_fraction']['basis'],row['supplied_slice_fraction']['basis'])

    def test_unselected_fund_does_not_add_account_notional(self):
        result=source_exposure.source_allocation_context(document())
        self.assertEqual(len(result['normalized_allocation_input']['rows']),1)
        self.assertEqual(result['normalized_allocation_input']['rows'][0]['notional'],'40')
        self.assertEqual(result['complete_context_receipt']['selected_row_ids'],['owned'])
        self.assertNotIn('FUND-X',[r['symbol'] for r in result['normalized_allocation_input']['rows']])
        self.assertEqual(result['allocation_result'],source_exposure.allocation_context(result['normalized_allocation_input']))

    def test_source_bindings_exact_weight_and_complete_list(self):
        doc=document();b=basis(doc)
        self.assertEqual(b['rows'][1]['source_binding']['pointer'],'/funds/0/holdings/1/weight')
        self.assertEqual(b['rows'][1]['source_binding']['source_bytes_sha256'],doc['sources'][0]['sha256'])
        self.assertEqual(b['coverage']['supplied_holdings_pointer'],'/funds/0/holdings')
        self.assertEqual(b['coverage']['declared_pointer'],'/funds/0/holdings_coverage')

    def test_zero_sum_does_not_fabricate_slice(self):
        b=basis(document(fixture(('0','0'),'0')))
        self.assertEqual(b['reason'],'ZERO_SUPPLIED_WEIGHT_SUM')
        self.assertEqual(b['rows'][0]['supplied_slice_fraction']['status'],'UNAVAILABLE')
        self.assertEqual(b['rows'][0]['total_fund_fraction']['fraction'],'0')

    def test_missing_weight_withholds_complete_slice(self):
        b=basis(document(fixture(('0.21',None),'0.35')))
        self.assertEqual(b['coverage']['unusable_weight_count'],1)
        self.assertIsNone(b['coverage']['unrepresented_total_fund_fraction'])
        self.assertTrue(all(r['supplied_slice_fraction']['fraction'] is None for r in b['rows']))
        self.assertEqual(b['rows'][0]['total_fund_fraction']['numerator'],'0.21')

    def test_mismatch_preserves_original_weight_not_declared_divisor(self):
        b=basis(document(fixture(coverage='0.4')))
        self.assertEqual(b['coverage']['status'],'DECLARED_COVERAGE_WEIGHT_MISMATCH')
        self.assertEqual(b['coverage']['observed_known_weight_sum'],'0.35')
        self.assertEqual(b['rows'][0]['total_fund_fraction']['numerator'],'0.21')
        self.assertIsNone(b['rows'][0]['supplied_slice_fraction']['denominator'])

    def test_absent_declared_coverage_has_only_list_sum_interpretation(self):
        b=basis(document(fixture(coverage=None)))
        self.assertEqual(b['coverage']['status'],'NOT_SUPPLIED')
        self.assertEqual(b['rows'][0]['supplied_slice_fraction']['denominator'],'0.35')
        self.assertIn('Immediate supplied holdings',b['scope'])

    def test_invalid_weights_never_get_valid_slice(self):
        for bad in ['-0.1','1.1','NaN','Infinity','1e-129']:
            with self.subTest(bad=bad):
                try:b=basis(document(fixture((bad,'0.14'),None)))
                except (ValueError,ArithmeticError):continue  # Existing validation may reject the whole source.
                self.assertIsNone(b['rows'][0]['total_fund_fraction']['fraction'])
                self.assertTrue(all(r['supplied_slice_fraction']['fraction'] is None for r in b['rows']))

    def test_sum_exceeds_one_not_normalized(self):
        b=basis(document(fixture(('0.7','0.6'),None)))
        self.assertEqual(b['reason'],'SUPPLIED_WEIGHT_SUM_EXCEEDS_ONE')
        self.assertIsNone(b['rows'][0]['supplied_slice_fraction']['fraction'])

    def test_conflicting_fund_records_have_no_preferred_summary(self):
        doc=document();second=deepcopy(doc['sources'][0]);second['id']='second'
        changed=fixture(('0.22','0.13'));second['text']=json.dumps(changed);second['sha256']=hashlib.sha256(second['text'].encode()).hexdigest()
        doc['sources'].append(second);b=basis(doc)
        self.assertEqual(b['reason'],'CONFLICTING_FUND_RECORDS');self.assertEqual(b['rows'],[])
        self.assertEqual(len(b['source_bindings']),2)

    def test_identical_duplicate_records_keep_all_bindings(self):
        doc=document();second=deepcopy(doc['sources'][0]);second['id']='copy';doc['sources'].append(second)
        b=basis(doc);self.assertEqual(b['status'],'COMPUTED');self.assertEqual(len(b['source_bindings']),2)

    def test_exact_lexeme_survives_float_precision_boundary(self):
        doc=document(fixture((0.21,0.14),None))
        exact='0.21000000000000000000000000000000000001'
        doc=replace_text(doc,'0.21',exact);b=basis(doc);row=b['rows'][0]
        self.assertEqual(row['total_fund_fraction']['numerator'],exact)
        self.assertEqual(b['coverage']['observed_known_weight_sum'],'0.35000000000000000000000000000000000001')
        self.assertTrue(row['total_fund_fraction']['fraction_rounded'])

    def test_precision_conflict_not_lost_when_legacy_float_equal(self):
        doc=document(fixture((0.21,0.14),None));second=deepcopy(doc['sources'][0]);second['id']='second'
        second['text']=second['text'].replace('0.21','0.21000000000000000000000000000000000001')
        second['sha256']=hashlib.sha256(second['text'].encode()).hexdigest();doc['sources'].append(second)
        self.assertEqual(basis(doc)['reason'],'CONFLICTING_FUND_RECORDS')

    def test_rounding_declared_and_exact_operands_retained(self):
        row=basis(document(fixture(('0.1','0.2'),'0.3')))['rows'][0]['supplied_slice_fraction']
        self.assertEqual(Fraction(Decimal(row['numerator']))/Fraction(Decimal(row['denominator'])),Fraction(1,3))
        self.assertTrue(row['fraction_rounded']);self.assertTrue(row['percent_rounded'])
        self.assertEqual(row['rounding'],'ROUND_HALF_EVEN')

    def test_decimal_context_does_not_change_result(self):
        doc=document(fixture(('0.123456789123456789','0.2'),None))
        want=basis(doc)
        with localcontext() as ctx:
            ctx.prec=6
            actual=basis(doc)
        self.assertEqual(actual,want)

    def test_external_decimal_traps_do_not_break_fraction_rendering(self):
        doc=document(fixture(('0.1','0.2'),'0.3'))
        expected=basis(doc)
        with localcontext() as ctx:
            ctx.traps[Inexact]=True
            ctx.traps[Rounded]=True
            self.assertEqual(basis(doc),expected)

    def test_tampered_original_hash_rejected(self):
        doc=document();doc['sources'][0]['text']+=' '
        with self.assertRaisesRegex(ValueError,'SOURCE_BYTES_HASH_MISMATCH'):basis(doc)

    def test_changed_source_regenerates_text(self):
        original=source_exposure.source_allocation_context(document())
        changed=source_exposure.source_allocation_context(document(fixture(('0.14','0.21'),'0.35')))
        self.assertNotEqual(original['fund_weight_report'],changed['fund_weight_report'])
        self.assertEqual(Decimal(changed['fund_context'][0]['weight_basis_evidence']['rows'][0]['supplied_slice_fraction']['percent']),Decimal('40'))

    def test_reordered_holdings_preserve_ratio_with_new_pointer(self):
        source=fixture();source['funds'][0]['holdings'].reverse();b=basis(document(source))
        alpha=next(r for r in b['rows'] if r['symbol']=='ALPHA')
        self.assertEqual(Decimal(alpha['supplied_slice_fraction']['percent']),Decimal('60'))
        self.assertEqual(alpha['source_binding']['pointer'],'/funds/0/holdings/1/weight')

    def test_cash_and_opaque_nested_rows_are_immediate_only(self):
        source=fixture();source['funds'][0]['holdings']=[{'symbol':'CASH','weight':'0.21'},{'symbol':'OPAQUE','weight':'0.14'}]
        source['identities']['CASH']={'kind':'cash'};source['funds'].append({'symbol':'OPAQUE'})
        b=basis(document(source))
        self.assertEqual(Decimal(b['rows'][0]['supplied_slice_fraction']['percent']),Decimal('60'))
        self.assertIn('not terminal issuer',b['scope'])
        self.assertFalse(b['account_notional_added'])

    def test_share_classes_remain_bound_per_row(self):
        source=fixture();source['identities']['BETA']['issuer_id']='issuer-a'
        b=basis(document(source))
        self.assertEqual(len(b['rows']),2)
        self.assertNotEqual(b['rows'][0]['source_binding']['pointer'],b['rows'][1]['source_binding']['pointer'])

    def test_caller_cached_summary_cannot_override_source_projection(self):
        doc=document();doc['fund_weight_report']='Invented favorable fraction'
        doc['fund_context']=[{'symbol':'FUND-X','weight_basis_evidence':{'status':'COMPUTED'}}]
        actual=source_exposure.source_allocation_context(doc)
        self.assertNotEqual(actual['fund_weight_report'],doc['fund_weight_report'])
        self.assertEqual(actual['fund_context'][0]['weight_basis_evidence']['rows'][0]['supplied_slice_fraction']['numerator'],'0.21')
        self.assertEqual(actual['fund_context'][0]['weight_basis_evidence']['holdings_as_of'],'2033-04-05')

    def test_native_workbench_retains_and_replays_new_fields(self):
        packet={'schema_version':1,'contract':{'prompt':'Compare fund weight denominators','purpose':'fictional regression','base_currency':'USD','horizon_id':'P1Y','as_of':'2033-04-06T10:00:00Z'},
                'jobs':[{'id':'weights','operation':'planning.source_allocation_context','inputs':{'document':document()}}]}
        bundle=quant_workbench.freeze(packet)
        self.assertEqual(bundle['result']['results'][0]['status'],'COMPUTED')
        self.assertIn('fund_weight_report',bundle['result']['results'][0]['result'])
        self.assertEqual(quant_workbench.verify(json.loads(json.dumps(bundle)))['jobs_verified'],1)


if __name__=='__main__':unittest.main()
