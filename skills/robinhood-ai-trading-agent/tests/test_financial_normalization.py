"""Economic fixtures are invented; tests establish arithmetic, not alpha."""
import copy
import json
import sys
import unittest
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from deterministic_rank import digest
from filing_extract import extract_html, observations, numeric
from financial_normalize import normalize, policy, publication_bounds, review_source, materialize, diagnose
from vqm_research import calculate, prepare_document
from test_shared_strategy import snapshot, screen


def financial_source():
    return dict(source_id='financial', document_origin='regulatory_filing', delivery='issuer',
                distribution_host='example.org', uri='https://example.org/FICTIONAL', content_sha256=digest('FICTIONAL'),
                publication={'precision': 'timestamp', 'at': '2026-08-01T12:00:00Z'}, retrieved_at='2026-10-09T15:02:00Z',
                verification={'status': 'verified', 'method': 'FICTIONAL test declaration', 'evidence': ['FICTIONAL source']})


def record(concept, value, entity='DEMO0', start=None, end='2026-06-30', rid=None, source='financial'):
    row = dict(record_id=rid or ':'.join([entity, concept, start or '', end]), source_id=source,
               entity_id=entity, concept='reviewed:' + concept, value=str(value), unit='USD', decimals='INF',
               period_end=end, locator='FICTIONAL table line', quote='FICTIONAL reported observation',
               review={'status': 'reviewed', 'policy_sha256': digest(policy()), 'basis_evidence': 'FICTIONAL basis matches the frozen policy'})
    if start:
        row['period_start'] = start
    if concept in policy()['required_bases']:
        row['basis'] = policy()['required_bases'][concept]
    return row


def normalized_snapshot():
    result = snapshot()
    result['schema_version'] = 2
    norm = dict(schema_version=1, policy_sha256=digest(policy()), information_cutoff=result['information_cutoff'],
                sources=[financial_source()], issuers=[], transcriptions=[], documents=[])
    result['sources'] = [s for s in result['sources'] if s['kind'] != 'financial']
    direct = {'ebit_ttm': 'ebit', 'cfo_ttm': 'cfo', 'net_income_ttm': 'parent_income',
              'capex_ttm': 'ppe_capex', 'debt': 'debt_current'}
    for row in result['rows']:
        norm['issuers'].append(dict(issuer_id=row['issuer_id'], entity_id=row['issuer_id'], adapter='corporate',
            ttm_start=row['ttm_start'], financial_period_end=row['financial_period_end'],
            latest_public_period_review={'status': 'reviewed', 'information_as_of': result['information_cutoff'],
                'period_end': row['financial_period_end'], 'evidence': 'FICTIONAL latest-period review', 'source_ids': ['financial']}))
        for key, f in row['facts'].items():
            if key in {'market_cap', 'adv20', 'close_price'}:
                continue
            norm['transcriptions'].append(record(direct.get(key, key.removesuffix('_prior')), f['value'],
                entity=row['issuer_id'], start=f.get('period_start'), end=f.get('balance_date', f['period_end'])))
        for concept in ('debt_noncurrent', 'finance_leases_current', 'finance_leases_noncurrent', 'other_productive_capex'):
            norm['transcriptions'].append(record(concept, 0, entity=row['issuer_id'],
                start=row['ttm_start'] if concept == 'other_productive_capex' else None))
        row['facts'] = {k: v for k, v in row['facts'].items() if k in {'market_cap', 'adv20', 'close_price'}}
        for key in ('financial_period_end', 'ttm_start', 'accounting_basis', 'latest_public_period_checked', 'source_conflicts'):
            row.pop(key)
    result['financial_normalization'] = norm
    return result


class InlineTests(unittest.TestCase):
    @staticmethod
    def html():
        return '''<html xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:us-gaap="http://fasb.org/us-gaap/2025" xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:ixt="http://www.xbrl.org/inlineXBRL/transformation/2020-02-12"><xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">E</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period></xbrli:context><xbrli:unit id="totally_arbitrary"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit><ix:nonFraction id="f" name="us-gaap:Assets" contextRef="c" unitRef="totally_arbitrary" decimals="-6" scale="6" format="ixt:num-dot-decimal">200</ix:nonFraction></html>'''

    def test_scale_sign_and_decimals_have_different_roles(self):
        self.assertEqual(numeric({'format': 'ixt:num-dot-decimal', 'scale': '6', 'sign': '-', 'decimals': '-6'}, '1,234'), ('-1234000000', '-6'))
        self.assertEqual(numeric({'format': 'ixt:num-comma-decimal', 'scale': '0', 'decimals': '2'}, '1.234,50')[0], '1234.50')
        with self.assertRaises(ValueError):
            numeric({'scale': '0', 'decimals': '0'}, '1,23')

    def test_unit_resolves_measure_not_identifier(self):
        html = self.html()
        extracted = extract_html(html)
        rows, issues = observations(extracted, 's')
        self.assertFalse(issues)
        self.assertEqual(rows[0]['value'], '200000000')
        self.assertEqual(rows[0]['entity_id'], 'E')
        extracted = extract_html(html.replace('iso4217:USD', 'iso4217:EUR'))
        self.assertFalse(observations(extracted, 's')[0])

    def test_namespace_aliases_preserve_financial_meaning(self):
        standard = observations(extract_html(self.html()), 's')[0]
        html = self.html().replace('iso4217:', 'Currency:').replace('xmlns:iso4217=', 'xmlns:Currency=')
        html = html.replace('us-gaap:', 'GAAP:').replace('xmlns:us-gaap=', 'xmlns:GAAP=')
        html = html.replace('ix:', 'Inline:').replace('xmlns:ix=', 'xmlns:Inline=')
        html = html.replace('ixt:', 'Transform:').replace('xmlns:ixt=', 'xmlns:Transform=')
        self.assertEqual(observations(extract_html(html), 's'), (standard, []))

    def test_spoofed_namespaces_and_local_rebinding_do_not_map(self):
        for uri in ['http://fasb.org/us-gaap/2025', 'http://www.xbrl.org/2003/iso4217',
                    'http://www.xbrl.org/2013/inlineXBRL', 'http://www.xbrl.org/2003/instance',
                    'http://www.xbrl.org/inlineXBRL/transformation/2020-02-12']:
            rows, issues = observations(extract_html(self.html().replace(uri, 'http://example.org/custom')), 's')
            self.assertFalse(rows, uri)
            self.assertTrue(issues, uri)
        html = self.html().replace('<ix:nonFraction ', '<ix:nonFraction xmlns:us-gaap="http://example.org/custom" ')
        rows, issues = observations(extract_html(html), 's')
        self.assertFalse(rows)
        self.assertIn('UNSUPPORTED_CONCEPT_NAMESPACE', issues[0]['reason'])

    def test_unbound_qname_and_legacy_extract_need_review(self):
        html = self.html().replace('name="us-gaap:Assets"', 'name="unbound:Assets"')
        rows, issues = observations(extract_html(html), 's')
        self.assertFalse(rows)
        self.assertIn('UNRESOLVED_QNAME', issues[0]['reason'])
        legacy = extract_html(self.html()); legacy.pop('extract_schema_version')
        self.assertIn('REEXTRACT', observations(legacy, 's')[1][0]['reason'])

    def test_nil_alias_and_inline_exclusion_stay_missing(self):
        html = self.html().replace('<ix:nonFraction ', '<ix:nonFraction xmlns:nilAlias="http://www.w3.org/2001/XMLSchema-instance" nilAlias:nil="true" ')
        self.assertIn('NIL_FACT', observations(extract_html(html), 's')[1][0]['reason'])
        html = self.html().replace('>200</ix:nonFraction>', '>200<ix:exclude>extra</ix:exclude></ix:nonFraction>')
        self.assertIn('INLINE_CONSTRUCT_UNSUPPORTED', observations(extract_html(html), 's')[1][0]['reason'])

    def test_unsupported_transforms_and_entities_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_TRANSFORM'):
            numeric({'format':'ixt:unknown', 'decimals':'0'}, '123')
        with self.assertRaisesRegex(ValueError, 'ENTITY'):
            extract_html('<!ENTITY x SYSTEM "file:///secret">')
        with self.assertRaisesRegex(ValueError, 'CONTINUED'):
            numeric({'continuedat':'x','decimals':'0'}, '123')


class NormalizationTests(unittest.TestCase):
    def test_complete_pipeline_preserves_computed_order(self):
        old, new = calculate(snapshot()), calculate(normalized_snapshot())
        self.assertEqual(new['status'], 'COMPUTED')
        self.assertEqual(new['scores'], old['scores'])
        self.assertEqual(new['input_assurance'], 'SHARED_NORMALIZATION_REPLAY')

    def test_input_order_and_decimal_context_do_not_change_values(self):
        s = normalized_snapshot()
        before = calculate(s)
        s['financial_normalization']['transcriptions'].reverse()
        s['financial_normalization']['issuers'].reverse()
        with localcontext() as c:
            c.prec = 6
            after = calculate(s)
        self.assertEqual(before['scores'], after['scores'])
        self.assertEqual(before['normalization']['issuers'], after['normalization']['issuers'])

    def test_ttm_bridge_and_quarter_paths_reconcile(self):
        s = normalized_snapshot()['financial_normalization']
        s['transcriptions'] = [r for r in s['transcriptions'] if not (r['entity_id']=='DEMO0' and r['concept']=='reviewed:ebit')]
        s['transcriptions'] += [record('ebit', v, start=a, end=b) for v,a,b in
            [(8,'2025-01-01','2025-12-31'), (6,'2026-01-01','2026-06-30'), (4,'2025-01-01','2025-06-30'),
             (2,'2025-07-01','2025-09-30'), (2,'2025-10-01','2025-12-31'), (3,'2026-01-01','2026-03-31'), (3,'2026-04-01','2026-06-30')]]
        r = normalize(s)['issuers'][0]['fields']['ebit_ttm']
        self.assertEqual(Decimal(r['value']), 10)
        self.assertEqual(len(r['derivation']['paths']), 2)
        s['transcriptions'][-1]['value'] = '4'
        self.assertTrue(any('CONFLICTING_TTM_PATHS' in x['reason'] for x in normalize(s)['issuers'][0]['gaps']))

    def test_missing_components_are_not_implicit_zero(self):
        s = normalized_snapshot()
        s['financial_normalization']['transcriptions'] = [r for r in s['financial_normalization']['transcriptions'] if r['concept'] not in {'reviewed:other_productive_capex', 'reviewed:finance_leases_current'}]
        gaps = diagnose(s)['issues']
        self.assertTrue(any('other_productive_capex' in g['reason'] for g in gaps))
        self.assertTrue(any('finance_leases_current' in g['reason'] for g in gaps))
        self.assertFalse(calculate(s)['scores'])

    def test_conflicting_duplicate_is_not_resolved_by_order(self):
        s = normalized_snapshot()['financial_normalization']
        extra = copy.deepcopy(s['transcriptions'][0]); extra.update(record_id='conflict', value='999')
        s['transcriptions'].append(extra)
        self.assertTrue(any('CONFLICTING_OBSERVATIONS' in g['reason'] for g in normalize(s)['issuers'][0]['gaps']))

    def test_rounding_agreement_selects_more_precise(self):
        s = normalized_snapshot()['financial_normalization']
        original = next(r for r in s['transcriptions'] if r['entity_id']=='DEMO0' and r['concept']=='reviewed:assets' and r['period_end']=='2026-06-30')
        original.update(value='200.4', decimals='1')
        coarse = copy.deepcopy(original); coarse.update(record_id='coarse', value='200', decimals='0')
        s['transcriptions'].append(coarse)
        self.assertEqual(normalize(s)['issuers'][0]['fields']['assets']['value'], '200.4')

    def test_parent_income_is_not_profitloss_or_analyst_eps(self):
        s = normalized_snapshot()['financial_normalization']
        with self.assertRaisesRegex(ValueError, 'TRANSCRIPTION_CONCEPT'):
            s['transcriptions'].append(record('analyst_eps', 99))
            normalize(s)

    def test_unverified_mirror_returns_draft_values_without_scoring(self):
        s = normalized_snapshot()
        source = s['financial_normalization']['sources'][0]
        source['delivery'] = 'mirror'
        n = normalize(s['financial_normalization'])
        self.assertEqual(n['issuers'][0]['fields']['ebit_ttm']['status'], 'DRAFT_UNVERIFIED')
        self.assertFalse(calculate(s)['scores'])

    def test_issuer_pdf_does_not_require_byte_match_to_sec_html(self):
        self.assertEqual(normalize(normalized_snapshot()['financial_normalization'])['status'], 'READY')

    def test_unverified_duplicate_does_not_block_verified_complete_path(self):
        s=normalized_snapshot()['financial_normalization']
        bad=financial_source();bad.update(source_id='mirror',delivery='mirror')
        s['sources'].append(bad)
        extra=copy.deepcopy(s['transcriptions'][0]);extra.update(source_id='mirror',record_id='mirror-row',value='999')
        s['transcriptions'].append(extra)
        n=normalize(s)['issuers'][0]
        self.assertEqual(n['status'],'READY')
        self.assertEqual(n['fields']['assets']['value'],'200')

    def test_advanced_bank_capital_cannot_replace_standardized(self):
        s=normalized_snapshot()['financial_normalization'];s['issuers']=s['issuers'][:1];s['issuers'][0]['adapter']='bank'
        standard=record('risk_weighted_assets',150);advanced=record('risk_weighted_assets',140,rid='advanced')
        advanced['basis']='advanced';s['transcriptions'] += [advanced,standard]
        n=normalize(s)
        self.assertEqual(n['issuers'][0]['fields']['risk_weighted_assets']['value'],'150')
        self.assertTrue(any('BASIS_NOT_SELECTED' in r['reason'] for r in n['extraction_issues']))

    def test_day_precision_is_conservative_and_timezone_explicit(self):
        source = financial_source()
        source['publication'] = {'precision':'date','date':'2026-10-08','timezone':'America/New_York'}
        from price_audit import timestamp
        self.assertIn('PUBLICATION_AFTER_OR_STRADDLES_CUTOFF',review_source(source,timestamp('2026-10-08T20:00:00Z'))['issues'])
        source['publication']['date'] = '2026-10-07'
        self.assertTrue(review_source(source,timestamp('2026-10-08T20:00:00Z'))['ready'])
        source['publication'].pop('timezone')
        self.assertFalse(review_source(source,timestamp('2026-10-08T20:00:00Z'))['ready'])

    def test_post_cutoff_amendment_cannot_contaminate_old_values(self):
        s = normalized_snapshot()['financial_normalization']
        later = financial_source(); later.update(source_id='later', publication={'precision':'timestamp','at':'2026-10-09T12:00:00Z'})
        s['sources'].append(later)
        extra=copy.deepcopy(s['transcriptions'][0]);extra.update(source_id='later',record_id='future',value='999')
        s['transcriptions'].append(extra)
        n=normalize(s)
        self.assertEqual(n['issuers'][0]['fields']['assets']['value'],'200')
        self.assertTrue(any(x['reason']=='NOT_KNOWN_BY_CUTOFF' for x in n['extraction_issues']))

    def test_override_cutoff_policy_and_identity_rejected(self):
        s = normalized_snapshot(); s['rows'][0]['facts']['ebit_ttm']={'value':999}
        with self.assertRaisesRegex(ValueError,'FACT_OVERRIDE'): calculate(s)
        s = normalized_snapshot(); s['financial_normalization']['policy_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'POLICY_HASH'): calculate(s)
        s = normalized_snapshot(); s['financial_normalization']['information_cutoff']='2026-10-07T20:00:00Z'
        with self.assertRaisesRegex(ValueError,'CUTOFF_MISMATCH'): calculate(s)
        s = normalized_snapshot(); s['financial_normalization']['issuers'][0]['adapter']='bank'
        with self.assertRaisesRegex(ValueError,'ADAPTER_MISMATCH'): calculate(s)

    def test_negative_unsigned_component_cannot_hide_inside_total(self):
        s=normalized_snapshot()['financial_normalization']
        next(r for r in s['transcriptions'] if r['concept']=='reviewed:finance_leases_current')['value']='-1'
        self.assertTrue(any('NEGATIVE_UNSIGNED' in x['reason'] for x in normalize(s)['issuers'][0]['gaps']))

    def test_real_reports_require_pipeline_and_fictional_is_explicit(self):
        d=screen();d['vqm_snapshot'].pop('fictional')
        with self.assertRaisesRegex(ValueError,'NORMALIZATION_REQUIRED'):prepare_document(d)
        d=screen();d['fictional']=False
        with self.assertRaisesRegex(ValueError,'FICTIONAL_REPORT'):prepare_document(d)

    def test_bank_and_reit_use_fixed_reviewed_bases(self):
        base=normalized_snapshot()['financial_normalization']
        base['issuers']=base['issuers'][:1]
        for adapter, fields in [('bank',{'common_income':12,'tangible_common_equity':100,'cet1':20,'risk_weighted_assets':150,'nonperforming_loans':2,'gross_loans':120}),
                                ('equity_reit',{'ffo_common':15,'reit_property_purchases':5,'reit_development_improvements':2})]:
            s=copy.deepcopy(base);s['issuers'][0]['adapter']=adapter
            for name,value in fields.items():
                flow=name in {'common_income','ffo_common','reit_property_purchases','reit_development_improvements'}
                s['transcriptions'].append(record(name,value,start='2025-07-01' if flow else None))
            if adapter=='bank':
                s['transcriptions'].append(record('tangible_common_equity',90,end='2025-06-30'))
            n=normalize(s)['issuers'][0]
            self.assertEqual(n['status'],'READY')
            if adapter=='equity_reit': self.assertEqual(n['fields']['capex_ttm']['value'],'7')
            else:self.assertEqual(n['fields']['risk_weighted_assets']['value'],'150')

    def test_successor_alias_is_dated_and_does_not_relabel_new_periods(self):
        s=normalized_snapshot()['financial_normalization'];s['issuers']=s['issuers'][:1]
        issuer=s['issuers'][0];issuer['entity_id']='NEW'
        issuer['predecessors']=[dict(entity_id='DEMO0',successor_entity_id='NEW',effective_date='2026-07-01',
            reporting_basis_unchanged=True,evidence='FICTIONAL one-for-one filing note',source_ids=['financial'])]
        self.assertEqual(normalize(s)['issuers'][0]['status'],'READY')
        issuer['predecessors'][0]['effective_date']='2026-06-01'
        self.assertTrue(normalize(s)['issuers'][0]['gaps'])

    def test_bad_extract_binding_and_unaudited_transcription_fail(self):
        s=normalized_snapshot()['financial_normalization']
        s['documents']=[{'source_id':'financial','extract':{},'extract_sha256':'bad'}]
        with self.assertRaisesRegex(ValueError,'EXTRACT_HASH'):normalize(s)
        s=normalized_snapshot()['financial_normalization'];s['transcriptions'][0]['review']['status']='draft'
        with self.assertRaisesRegex(ValueError,'BASIS_REVIEW'):normalize(s)

    def test_replay_cannot_accept_changed_output(self):
        d=screen();d['vqm_snapshot']=normalized_snapshot()
        from research_bundle import create_bundle,verify_bundle
        bundle=create_bundle(d)
        self.assertEqual(verify_bundle(bundle)['status'],'REPLAY_MATCH')
        bundle['result']['shared_strategy']['normalization']['issuers'][0]['fields']['ebit_ttm']['value']='999'
        with self.assertRaisesRegex(ValueError,'result hash mismatch'):verify_bundle(bundle)


if __name__=='__main__':
    unittest.main()
