import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import issuer_evidence as issuer


def record(symbol='ALPHA'):
    point = lambda v: {'value':v,'unit':'USD','period_end':'2031-06-30'}
    flow = lambda v: {**point(v),'period_start':'2030-07-01'}
    return {'symbol':symbol,'currency':'USD','unit':'USD','period_start':'2030-07-01','period_end':'2031-06-30',
        'revenue':120,'revenue_prior':100,'gross_profit':48,'shares_diluted':55,'shares_diluted_prior':50,
        'share_count_as_of':'2031-06-30','interest_expense':2,'income_tax_expense':3,
        'raw_snapshot_facts':{'cash':point(12),'debt':point(24),'ebit_ttm':flow(18),'net_income_ttm':flow(13),
          'cfo_ttm':flow(20),'capex_ttm':flow(7),'market_cap':point(240),'preferred_equity':point(0),
          'noncontrolling_interest':point(0)},
        'cfo_reconciliation_items':{'depreciation_amortization':4,'stock_compensation':3,'working_capital_change':0},
        'capex_detail':{'maintenance':4,'growth':3},
        'capital_allocation':{'acquisitions_cash_paid':2,'dividends_paid':1,'buybacks':0},
        'expense_disclosures':{'restructuring':2,'acquisition_integration':1,'annual_repeated_restructuring_occurrences':4},
        'debt_maturities':[{'principal':12,'date':'2032-06-30'}],
        'revolver':{'commitment':6,'undrawn':5,'covenant':'net debt / EBITDA below 3'},
        'customer_concentration':{'largest_customer_revenue_fraction':0.2},
        'business_description':'Industrial products and maintenance services.'}


class IssuerEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='issuer-test-')
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def setup_sources(self, document=None, text=None, extra=None):
        document = {'issuers':[record()]} if document is None else document
        sources = []
        content = text.encode() if text is not None else json.dumps(document).encode()
        (self.root/'original.dat').write_bytes(content)
        sources.append({'id':'primary','path':'original.dat','sha256':hashlib.sha256(content).hexdigest(),
                        'format':'text' if text is not None else 'json'})
        for index, (raw, fmt) in enumerate(extra or []):
            path='extra'+str(index);(self.root/path).write_bytes(raw)
            sources.append({'id':path,'path':path,'sha256':hashlib.sha256(raw).hexdigest(),'format':fmt})
        manifest=self.root/'ingress.json';manifest.write_text(json.dumps({'schema_version':1,'sources':sources}))
        return manifest,hashlib.sha256(manifest.read_bytes()).hexdigest()

    def run_record(self, value=None, request=None):
        m,p=self.setup_sources({'issuers':[record() if value is None else value]})
        return issuer.analyze(request or {'issuer_record':{'source_id':'primary','pointer':'/issuers/0'}},m,p)

    def test_equal_is_not_shortfall_or_funding_assurance(self):
        result=self.run_record();row=result['funding_comparisons']['rows'][0]
        self.assertEqual(row['maturity_relative_to_reported_cash'],'EQUAL')
        self.assertEqual(row['nominal_cash_minus_maturity'],'0')
        self.assertEqual(row['future_available_liquidity'],'UNKNOWN')
        self.assertEqual(row['funding_sufficiency'],'NOT_ESTABLISHED')
        self.assertEqual(row['nominal_cash_plus_undrawn_borrowing']['value'],'17')

    def test_both_comparison_signs(self):
        for cash,relation,residual in [(9,'GREATER','-3'),(15,'LESS','3')]:
            r=record();r['raw_snapshot_facts']['cash']['value']=cash
            row=self.run_record(r)['funding_comparisons']['rows'][0]
            self.assertEqual((row['maturity_relative_to_reported_cash'],row['nominal_cash_minus_maturity']),(relation,residual))

    def test_unknown_prior_share_date_does_not_inherit_income_year(self):
        change=self.run_record()['point_changes']['shares']
        self.assertEqual(change['value'],'10.0');self.assertEqual(change['interval'],'UNKNOWN')
        self.assertFalse(change['annual_change_established']);self.assertIsNone(change['annualized_value'])
        self.assertIsNone(change['prior']['dates']['as_of'])

    def test_explicit_and_reversed_dates_preserved_without_annualization(self):
        r=record();r['share_count_prior_as_of']='2030-06-30'
        self.assertEqual(self.run_record(r)['point_changes']['shares']['interval_days'],365)
        r['share_count_prior_as_of']='2032-06-30'
        self.assertEqual(self.run_record(r)['point_changes']['shares']['interval'],'NONINCREASING_DATES')

    def test_unknown_prior_revenue_period(self):
        row=self.run_record()['point_changes']['revenue']
        self.assertEqual(row['value'],'20.0');self.assertEqual(row['interval'],'UNKNOWN')

    def test_covenant_is_not_compliance_even_below_text_threshold(self):
        row=self.run_record()['covenant_diagnostic']
        self.assertTrue(row['net_debt_to_ebitda_proxy']['value'].startswith('0.54545'))
        self.assertEqual(row['contractual_compliance'],'UNKNOWN')
        self.assertEqual(row['threshold_comparison'],'NOT_EVALUATED')
        self.assertEqual(row['clause']['original_value'],'net debt / EBITDA below 3')

    def test_cash_and_economic_proxy_are_separate(self):
        rows=self.run_record()['cash_operating']
        self.assertEqual(rows['cfo_less_capex']['value'],'13')
        self.assertEqual(rows['cfo_less_maintenance_capex']['value'],'16')
        self.assertEqual(rows['cash_after_capex_acquisitions_distributions']['value'],'10')
        self.assertEqual(rows['sbc_economic_proxy_after_capex_acquisitions']['value'],'8')
        self.assertTrue(rows['cfo_bridge_matches_reported'])

    def test_wrong_cfo_bridge_remains_visible(self):
        r=record();r['cfo_reconciliation_items']['working_capital_change']=-1
        self.assertFalse(self.run_record(r)['cash_operating']['cfo_bridge_matches_reported'])

    def test_numeric_bridge_equality_requires_reported_cfo_dimensions(self):
        for change in ({'unit_scale':1000},{'period_end':'2032-06-30'},{'period_start':None}):
            with self.subTest(change=change):
                r=record();r['raw_snapshot_facts']['cfo_ttm'].update(change)
                result=self.run_record(r)['cash_operating']
                self.assertIsNone(result['cfo_bridge_matches_reported'])
                self.assertTrue(result['cfo_reconciliation_comparison']['diagnostic_numeric_equal'])
                self.assertFalse(result['cfo_reconciliation_comparison']['compatible_original_dimensions'])

    def test_reversed_income_period_cannot_support_reconciliation(self):
        r=record();r['period_start']='2033-01-01'
        result=self.run_record(r)
        self.assertIn('REVERSED_ORIGINAL_PERIOD',result['original_facts']['depreciation']['problems'])
        self.assertIsNone(result['cash_operating']['cfo_bridge_matches_reported'])

    def test_missing_fields_do_not_become_zero(self):
        r=record();del r['capital_allocation']['acquisitions_cash_paid']
        result=self.run_record(r)
        self.assertIsNone(result['cash_operating']['cash_after_capex_acquisitions_distributions']['value'])
        self.assertEqual(set(result['topic_coverage']),set(issuer.TOPICS))
        self.assertEqual(result['valuation_objective']['DCF_DISCOUNT_CLOSURE'],'NOT_EVALUATED')

    def test_raw_currency_and_unit_conflicts_fail_arithmetic(self):
        for key,value in [('unit','EUR'),('currency','EUR')]:
            r=record();r['raw_snapshot_facts']['cash'][key]=value
            result=self.run_record(r)
            self.assertEqual(result['funding_comparisons']['rows'][0]['maturity_relative_to_reported_cash'],'UNKNOWN')
            self.assertIsNone(result['cash_operating']['net_debt']['value'])

    def test_explicit_scale_difference_blocks_addition(self):
        r=record();r['raw_snapshot_facts']['debt']['unit_scale']=1000
        result=self.run_record(r)
        self.assertEqual(result['cash_operating']['net_debt']['reason'],'INCOMPATIBLE_OR_UNKNOWN_UNIT_SCALES')

    def test_maturity_currency_conflict(self):
        r=record();r['debt_maturities'][0]['currency']='EUR'
        self.assertEqual(self.run_record(r)['funding_comparisons']['rows'][0]['maturity_relative_to_reported_cash'],'UNKNOWN')

    def test_magnitude_labels_cannot_mix_with_literal_cash(self):
        r=record();r['unit']='USD millions'
        result=self.run_record(r)
        self.assertEqual(result['funding_comparisons']['rows'][0]['maturity_relative_to_reported_cash'],'UNKNOWN')
        self.assertIsNone(result['cash_operating']['ebit_margin_fraction']['value'])
        r['unit']='USD (literal accounting amounts)'
        self.assertEqual(self.run_record(r)['funding_comparisons']['rows'][0]['maturity_relative_to_reported_cash'],'EQUAL')
        r['unit']='USD (literal millions)'
        self.assertEqual(self.run_record(r)['funding_comparisons']['rows'][0]['maturity_relative_to_reported_cash'],'UNKNOWN')

    def test_conflicting_entity_and_maturity_scale_rejected(self):
        r=record();r['debt_maturities'][0]['entity_id']='OTHER'
        self.assertEqual(self.run_record(r)['funding_comparisons']['rows'][0]['maturity_relative_to_reported_cash'],'UNKNOWN')
        r=record();r['debt_maturities'][0]['unit']='USD';r['debt_maturities'][0]['unit_scale']=1000
        self.assertEqual(self.run_record(r)['funding_comparisons']['rows'][0]['maturity_relative_to_reported_cash'],'UNKNOWN')

    def test_fractional_originals_preserve_precision(self):
        from decimal import Decimal
        raw=json.dumps({'issuers':[record()]}).replace('"value": 12', '"value": 12.12345678901234567890123456789').encode()
        m,p=self.setup_sources(extra=[(raw,'json')])
        result=issuer.analyze({'issuer_record':{'source_id':'extra0','pointer':'/issuers/0'}},m,p)
        row=result['funding_comparisons']['rows'][0]
        self.assertEqual(Decimal(row['nominal_cash_minus_maturity']),Decimal('0.12345678901234567890123456789'))

    def test_zero_denominator_is_unresolved(self):
        r=record();r['shares_diluted_prior']=0;r['revenue']=0
        result=self.run_record(r)
        self.assertIsNone(result['point_changes']['shares']['value'])
        self.assertIsNone(result['cash_operating']['gross_margin_fraction']['value'])

    def test_boolean_and_numeric_string_not_numbers(self):
        for value in (True,'12'):
            r=record();r['raw_snapshot_facts']['cash']['value']=value
            self.assertEqual(self.run_record(r)['funding_comparisons']['rows'][0]['maturity_relative_to_reported_cash'],'UNKNOWN')

    def test_negative_magnitudes_and_invalid_dates_retained(self):
        r=record();r['raw_snapshot_facts']['cash']['value']=-2;r['debt_maturities'][0]['date']='yesterday'
        result=self.run_record(r);row=result['funding_comparisons']['rows'][0]
        self.assertEqual(row['maturity_relative_to_reported_cash'],'UNKNOWN')
        self.assertEqual(row['maturity']['original_value'],12)
        self.assertIn('INVALID_ORIGINAL_DATE:due_date',row['maturity']['problems'])

    def test_duplicate_maturities_not_summed(self):
        r=record();r['debt_maturities'].append(copy.deepcopy(r['debt_maturities'][0]))
        rows=self.run_record(r)['funding_comparisons']['rows']
        self.assertEqual(len(rows),2);self.assertTrue(rows[1]['repeated_identical_row'])
        self.assertEqual(rows[1]['nominal_cash_minus_maturity'],'0')

    def test_metadata_dates_and_source_refs_survive(self):
        r=record();r['raw_snapshot_facts']['market_cap']['period_end']='2031-09-30'
        result=self.run_record(r)
        self.assertEqual(result['cash_operating']['enterprise_value_diagnostic']['date_compatibility'],'MIXED_OR_UNKNOWN_DATES')
        self.assertEqual(result['original_facts']['cash']['source_ref']['pointer'],'/issuers/0/raw_snapshot_facts/cash/value')

    def test_arbitrary_caller_fields_and_literal_values_rejected(self):
        m,p=self.setup_sources()
        for extra in ({'unverified_prose':'cash exceeds debt'},{'values':{'cash':0}},{'label':'Must refinance'},{'operations':[]}):
            with self.assertRaisesRegex(ValueError,'ISSUER_REQUEST_FIELDS'):
                issuer.analyze({'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},**extra},m,p)

    def test_monitoring_is_closed_hypotheses_not_must_conditions(self):
        request={'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'monitoring':['funding','dilution'],'research_stance':'watch'}
        result=self.run_record(request=request)
        self.assertEqual(len(result['monitoring_hypotheses']),2)
        self.assertTrue(all(not x['necessity_established'] and not x['execution_authority'] for x in result['monitoring_hypotheses']))
        request['monitoring']=['must_refinance']
        with self.assertRaisesRegex(ValueError,'MONITORING_TOPICS_REQUIRED'):self.run_record(request=request)

    def test_peer_distinctions_and_no_moat_claim(self):
        peer=record('BETA');peer['business_description']='Subscription software';peer['revenue']=200
        m,p=self.setup_sources({'issuers':[record(),peer]})
        result=issuer.analyze({'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'peers':[{'source_id':'primary','pointer':'/issuers/1'}]},m,p)
        self.assertEqual(result['business_context']['peer_diagnostics'][0]['economic_comparability'],'NOT_ESTABLISHED')
        self.assertEqual(result['business_context']['competitive_advantage'],'NOT_ESTABLISHED')

    def test_aliases_do_not_create_independent_peer(self):
        doc={'issuers':[record()]};raw=json.dumps(doc).encode();m,p=self.setup_sources(doc,extra=[(raw,'json')])
        with self.assertRaisesRegex(ValueError,'DUPLICATE_ORIGINAL_RECORD'):
            issuer.analyze({'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'peers':[{'source_id':'extra0','pointer':'/issuers/0'}]},m,p)

    def test_whole_ingress_verified_including_unselected(self):
        m,p=self.setup_sources(extra=[(b'opaque','bytes')]);req={'issuer_record':{'source_id':'primary','pointer':'/issuers/0'}}
        result=issuer.analyze(req,m,p)
        self.assertEqual(result['source_coverage']['sources_verified'],2)
        self.assertFalse(result['source_coverage']['all_corpus_semantics_reviewed'])
        (self.root/'extra0').write_bytes(b'tampered')
        with self.assertRaises(ValueError):issuer.analyze(req,m,p)

    def test_external_manifest_pin_required(self):
        m,p=self.setup_sources()
        with self.assertRaises(ValueError):issuer.analyze({'issuer_record':{'source_id':'primary','pointer':'/issuers/0'}},m,'0'*64)

    def test_embedded_json_requires_exact_original_span(self):
        inner=json.dumps(record());text='Original disclosure:\n'+inner+'\nEnd.';m,p=self.setup_sources(text=text)
        ref={'source_id':'primary','start':21,'end':21+len(inner),'excerpt':inner,'pointer':''}
        self.assertEqual(issuer.analyze({'issuer_record':ref},m,p)['issuer']['symbol'],'ALPHA')
        ref['excerpt']=inner.replace('ALPHA','OTHER')
        with self.assertRaises(ValueError):issuer.analyze({'issuer_record':ref},m,p)

    def test_source_nonfinite_and_duplicate_keys_rejected(self):
        for raw in (b'{"symbol":"A","symbol":"B","raw_snapshot_facts":{}}',b'{"symbol":"A","raw_snapshot_facts":{},"revenue":NaN}'):
            (self.root/'bad.json').write_bytes(raw);m=self.root/'bad-manifest.json'
            m.write_text(json.dumps({'schema_version':1,'sources':[{'id':'bad','path':'bad.json','sha256':hashlib.sha256(raw).hexdigest(),'format':'json'}]}))
            with self.assertRaises(ValueError):issuer.analyze({'issuer_record':{'source_id':'bad','pointer':''}},m,hashlib.sha256(m.read_bytes()).hexdigest())

    def test_report_hash_and_relocation_are_deterministic(self):
        m,p=self.setup_sources();req={'issuer_record':{'source_id':'primary','pointer':'/issuers/0'}}
        first=issuer.analyze(req,m,p);target=self.root/'relocated';target.mkdir()
        shutil.copyfile(m,target/m.name);shutil.copyfile(self.root/'original.dat',target/'original.dat')
        second=issuer.analyze(req,target/m.name,p)
        self.assertEqual(first,second);self.assertEqual(first['report']['sha256'],hashlib.sha256(first['report']['text'].encode()).hexdigest())
        self.assertFalse(first['report']['whole_report_semantic_pass'])

    def policy(self):
        return {'cadence':'QUARTERLY','rules':[
            {'purpose':'REVIEW_THESIS','metric':'ebit_margin_fraction','operator':'lt',
             'threshold':{'kind':'ANALYST_ASSUMPTION','value':0.2}},
            {'purpose':'INVALIDATE_HYPOTHESIS','metric':'cfo_less_capex','operator':'le',
             'threshold':{'kind':'ANALYST_ASSUMPTION','value':0}}]}

    def test_conditional_review_invalidation_and_rolling_cadence(self):
        request={'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'research_plan':self.policy()}
        plan=self.run_record(request=request)['research_plan']
        self.assertEqual([x['evaluation'] for x in plan['rules']],['CONDITION_MET','CONDITION_NOT_MET'])
        self.assertTrue(all(plan['purpose_coverage'].values()))
        self.assertEqual(plan['cadence_status'],'PROPOSAL_ONLY_NOT_SCHEDULED')
        self.assertTrue(all(not x['execution_authority'] and not x['general_necessity_established'] for x in plan['rules']))
        self.assertEqual(plan['rules'][0]['threshold']['kind'],'ANALYST_ASSUMPTION')

    def test_unknown_observation_is_not_pass_or_failure(self):
        value=record();del value['raw_snapshot_facts']['cfo_ttm']['period_start']
        result=self.run_record(value,{'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'research_plan':self.policy()})
        self.assertIsNone(result['research_plan']['rules'][1]['condition_met_on_retained_observation'])
        self.assertEqual(result['research_plan']['rules'][1]['evaluation'],'UNKNOWN')

    def test_source_threshold_requires_original_metric_unit_and_scale(self):
        document={'issuers':[record()],'threshold':{'metric':'cfo_less_capex','value':15,'unit':'USD','unit_scale':1}}
        m,p=self.setup_sources(document);plan=self.policy();plan['rules'][1]['threshold']={'kind':'SOURCE_THRESHOLD','source_ref':{'source_id':'primary','pointer':'/threshold'}}
        req={'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'research_plan':plan}
        result=issuer.analyze(req,m,p)['research_plan']['rules'][1]
        self.assertTrue(result['condition_met_on_retained_observation'])
        self.assertIn('source_sha256',result['threshold'])
        self.assertIsNone(result['threshold']['source_issuer'])
        self.assertEqual(result['threshold']['source_scope'],'UNSPECIFIED_RESEARCH_POLICY_SCOPE')
        for field,value in [('metric','shares_current'),('unit','EUR'),('unit_scale',1000),('issuer','BETA')]:
            bad=copy.deepcopy(document);bad['threshold'][field]=value;m,p=self.setup_sources(bad)
            with self.subTest(field=field),self.assertRaises(ValueError):issuer.analyze(req,m,p)

    def test_point_change_policy_uses_percent_not_percentage_points(self):
        plan=self.policy();plan['rules'][0]['metric']='shares_point_change_percent';plan['rules'][0]['threshold']['value']=12
        result=self.run_record(request={'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'research_plan':plan})
        row=result['research_plan']['rules'][0]
        self.assertEqual(row['observation']['unit'],'percent')
        self.assertEqual(row['threshold']['unit'],'percent')
        self.assertEqual(row['observation']['scope'],'SUPPLIED_POINT_CHANGE_NOT_ANNUAL')

    def test_rule_cannot_supply_cached_observation_or_arbitrary_prose(self):
        for key,value in [('value',9),('observed_metric',0),('reason','Guaranteed discount closure'),('text','Must refinance')]:
            plan=self.policy();plan['rules'][0][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'RESEARCH_RULE_FIELDS'):
                self.run_record(request={'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'research_plan':plan})

    def test_rule_rejects_wrong_metric_nonnumeric_and_universal_purpose(self):
        for key,value in [('metric','annual_dilution'),('purpose','PROVE_DCF_CLOSURE'),('operator','always')]:
            plan=self.policy();plan['rules'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.run_record(request={'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'research_plan':plan})
        plan=self.policy();plan['rules'][0]['threshold']['value']='0.2'
        with self.assertRaises(ValueError):self.run_record(request={'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'research_plan':plan})

    def test_source_event_dates_classify_calendar_window_not_occurrence(self):
        doc={'issuers':[record()],'as_of':'2031-07-01T12:00:00Z','events':[
            {'description':'Scheduled results update.','event_date':'2031-07-20'},
            {'description':'Later contract review.','event_date':'2034-01-01'}]}
        m,p=self.setup_sources(doc);plan=self.policy();plan.update(as_of_ref={'source_id':'primary','pointer':'/as_of'},event_window_days=30,
            events=[{'source_ref':{'source_id':'primary','pointer':'/events/'+str(i)+'/description'},
                     'date_ref':{'source_id':'primary','pointer':'/events/'+str(i)+'/event_date'}} for i in range(2)])
        result=issuer.analyze({'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'research_plan':plan},m,p)['research_plan']
        self.assertEqual([e['timing_status'] for e in result['events']],['WITHIN_SELECTED_REVIEW_WINDOW','OUTSIDE_SELECTED_REVIEW_WINDOW'])
        self.assertTrue(all(not e['occurrence_verified'] for e in result['events']))

    def test_event_missing_date_stays_unknown_and_cannot_borrow_other_record(self):
        doc={'issuers':[record()],'events':[{'description':'Review expected next quarter.'},{'description':'Separate event','event_date':'2031-07-20'}]}
        m,p=self.setup_sources(doc);plan=self.policy();plan['events']=[{'source_ref':{'source_id':'primary','pointer':'/events/0/description'}}]
        request={'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'research_plan':plan}
        self.assertEqual(issuer.analyze(request,m,p)['research_plan']['events'][0]['timing_status'],'UNKNOWN')
        plan['events'][0]['date_ref']={'source_id':'primary','pointer':'/events/1/event_date'}
        with self.assertRaisesRegex(ValueError,'EVENT_DATE_RECORD_MISMATCH'):issuer.analyze(request,m,p)

    def test_text_event_date_must_be_inside_exact_quote(self):
        text='Results on 2031-07-20. Other date 2032-01-01.'
        m,p=self.setup_sources(extra=[(text.encode(),'text')]);plan=self.policy()
        plan['events']=[{'source_ref':{'source_id':'extra0','start':0,'end':22,'excerpt':text[:22]},
                         'date_ref':{'source_id':'extra0','start':11,'end':21,'excerpt':text[11:21]}}]
        request={'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'research_plan':plan}
        event=issuer.analyze(request,m,p)['research_plan']['events'][0]
        self.assertEqual(event['event_calendar_date'],'2031-07-20');self.assertEqual(event['timing_status'],'UNKNOWN')
        plan['events'][0]['date_ref']={'source_id':'extra0','start':34,'end':44,'excerpt':text[34:44]}
        with self.assertRaisesRegex(ValueError,'EVENT_DATE_OUTSIDE_QUOTED_EVENT'):issuer.analyze(request,m,p)

    def test_rule_plan_cannot_add_unpinned_events_or_manual_dates(self):
        plan=self.policy();plan['events']=[{'source_ref':{'source_id':'not-in-manifest','pointer':'/description'}}]
        with self.assertRaises(ValueError):self.run_record(request={'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'research_plan':plan})
        plan=self.policy();plan['events']=[{'source_ref':{'source_id':'primary','pointer':'/issuers/0/business_description'},'date':'2031-12-31'}]
        with self.assertRaises(ValueError):self.run_record(request={'issuer_record':{'source_id':'primary','pointer':'/issuers/0'},'research_plan':plan})


if __name__=='__main__':unittest.main()
