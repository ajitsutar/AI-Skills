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


class VqmFailureDiagnosticTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / 'selected snapshot.json'
        self.doc = snapshot()
        self.path.write_text(json.dumps(self.doc), encoding='utf8')

    @staticmethod
    def missing(name='exchange_calendars'):
        return ModuleNotFoundError("No module named '" + name + "'", name=name)

    def invoke(self):
        import contextlib, io
        from unittest.mock import patch
        import vqm_research as vqm
        stream = io.StringIO(); error = None
        with patch.object(sys, 'argv', ['vqm_research.py', str(self.path)]), contextlib.redirect_stdout(stream):
            try: vqm.main()
            except (Exception, SystemExit) as exc: error = exc
        return stream.getvalue(), error

    def direct(self, document=None, profile_doc=None):
        import vqm_diagnostics as diagnostic
        from vqm_research import profile
        raw = json.dumps(self.doc if document is None else document).encode()
        policy_raw = json.dumps(profile() if profile_doc is None else profile_doc).encode()
        return diagnostic.audit_vqm(raw, diagnostic.sha(raw), policy_raw, diagnostic.sha(policy_raw))

    def test_cli_computed_success_output_matches_accepted_baseline(self):
        # The unchanged legacy CLI serialized calculate's result with these options.
        expected = json.dumps(calculate(json.loads(self.path.read_text(encoding='utf-8-sig'))), indent=2, allow_nan=False) + '\n'
        actual, error = self.invoke()
        self.assertIsNone(error); self.assertEqual(actual, expected)

    def test_calculate_api_and_results_unchanged_without_diagnostic_import(self):
        from unittest.mock import patch
        expected = calculate(self.doc)
        with patch.dict(sys.modules, {'vqm_diagnostics': None}):
            self.assertEqual(calculate(copy.deepcopy(self.doc)), expected)
            text, error = self.invoke()
        self.assertIsNone(error); self.assertEqual(json.loads(text), expected)

    def test_cli_noncomputed_status_exit2_and_output_unchanged(self):
        from unittest.mock import patch
        import vqm_research as vqm
        result = {'status': 'INSUFFICIENT_DATA', 'details': ['synthetic missing input']}
        with patch.object(vqm, 'calculate', return_value=result), patch.dict(sys.modules, {'vqm_diagnostics': None}):
            text, error = self.invoke()
        self.assertEqual(text, json.dumps(result, indent=2, allow_nan=False) + '\n')
        self.assertIsInstance(error, SystemExit); self.assertEqual(error.code, 2)

    def test_missing_calendar_retains_nonzero_and_original_exception(self):
        from unittest.mock import patch
        import vqm_research as vqm
        failure = self.missing()
        with patch.object(vqm, 'session_grid', side_effect=failure): text, error = self.invoke()
        self.assertIs(error, failure); self.assertIsNone(json.loads(text)['score'])

    def test_missing_calendar_outputs_selected_snapshot_profile_diagnostic(self):
        from unittest.mock import patch
        import vqm_research as vqm
        with patch.object(vqm, 'session_grid', side_effect=self.missing()): text, error = self.invoke()
        out = json.loads(text)
        self.assertEqual(out['status'], 'SELECTED_SNAPSHOT_AUDIT_ONLY_SCORING_FAILED')
        self.assertEqual(out['audit']['coverage']['rows_audited'], len(self.doc['rows']))
        self.assertEqual(out['profile_binding']['canonical_sha256'], self.doc['profile_sha256'])

    def test_diagnostic_import_failure_preserves_original_calendar_error(self):
        from unittest.mock import patch
        import vqm_research as vqm
        failure = self.missing()
        with patch.object(vqm, 'session_grid', side_effect=failure), patch.dict(sys.modules, {'vqm_diagnostics': None}): text, error = self.invoke()
        self.assertEqual(text, ''); self.assertIs(error, failure)

    def test_diagnostic_generation_or_write_failure_preserves_original_error(self):
        from unittest.mock import patch
        import vqm_research as vqm
        import vqm_diagnostics as diagnostic
        for mode in ['generation', 'write']:
            failure = self.missing()
            target = patch.object(diagnostic, 'diagnose_snapshot', side_effect=ValueError('synthetic diagnostic failure')) if mode == 'generation' else patch('builtins.print', side_effect=OSError('synthetic output failure'))
            with patch.object(vqm, 'session_grid', side_effect=failure), target: _, error = self.invoke()
            self.assertIs(error, failure)

    def test_unrelated_missing_dependency_never_enters_diagnostic_branch(self):
        from unittest.mock import patch
        import vqm_research as vqm
        import vqm_diagnostics as diagnostic
        failure = self.missing('unrelated_optional_module')
        with patch.object(vqm, 'calculate', side_effect=failure), patch.object(diagnostic, 'diagnose_snapshot') as spy: text, error = self.invoke()
        self.assertIs(error, failure); self.assertEqual(text, ''); spy.assert_not_called()

    def test_invalid_profile_error_remains_native_and_no_audit_claim(self):
        self.doc['profile_sha256'] = '0' * 64
        self.path.write_text(json.dumps(self.doc), encoding='utf8')
        text, error = self.invoke()
        self.assertEqual(text, ''); self.assertIsInstance(error, ValueError)
        self.assertEqual(str(error), 'PROFILE_HASH_MISMATCH')

    def test_malformed_json_unicode_and_bom_newline_parsing_matches_baseline(self):
        from unittest.mock import patch
        import vqm_research as vqm
        for raw in [b'{\r\n"a":', b'\xff', b'\xef\xbb\xbf{\r\n"a":1\r}\r\n']:
            self.path.write_bytes(raw)
            try: expected = json.loads(self.path.read_text(encoding='utf-8-sig')); expected_error = None
            except Exception as exc: expected = None; expected_error = exc
            with patch.object(vqm, 'calculate', return_value={'status': 'COMPUTED'}) as calculation: _, actual_error = self.invoke()
            if expected_error is not None:
                self.assertIs(type(actual_error), type(expected_error)); self.assertEqual(str(actual_error), str(expected_error)); calculation.assert_not_called()
            else: self.assertIsNone(actual_error); calculation.assert_called_once_with(expected)

    def test_schema2_missing_calendar_diagnostic_explicitly_unsupported(self):
        from unittest.mock import patch
        import vqm_research as vqm
        self.path.write_text(json.dumps(normalized_snapshot()), encoding='utf8')
        failure = self.missing()
        with patch.object(vqm, 'session_grid', side_effect=failure): text, error = self.invoke()
        out = json.loads(text)
        self.assertIs(error, failure); self.assertEqual(out['status'], 'SELECTED_SNAPSHOT_AUDIT_UNAVAILABLE')
        self.assertIsNone(out['audit']); self.assertIn('SCHEMA1', out['diagnostic_error']['message'])

    def test_schema1_snapshot_byte_hash_and_packaged_profile_entry_bound(self):
        import hashlib
        import vqm_diagnostics as diagnostic
        raw = self.path.read_bytes(); out = diagnostic.diagnose_snapshot(raw, ROOT, self.missing())
        self.assertEqual(out['snapshot_raw_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(out['profile_binding']['raw_sha256'], json.loads((ROOT / 'PACKAGE-MANIFEST.json').read_bytes())['files']['profiles/vqm-fundamental-v1.json'])
        with self.assertRaisesRegex(ValueError, 'INPUT_BYTE_HASH_MISMATCH'): diagnostic.audit_vqm(raw, '0' * 64, b'{}', diagnostic.sha(b'{}'))

    def test_changed_packaged_profile_fails_diagnostic_without_hiding_native_error(self):
        from unittest.mock import patch
        import vqm_research as vqm
        (self.root / 'profiles').mkdir()
        (self.root / 'profiles/vqm-fundamental-v1.json').write_bytes((ROOT / 'profiles/vqm-fundamental-v1.json').read_bytes() + b' ')
        (self.root / 'PACKAGE-MANIFEST.json').write_bytes((ROOT / 'PACKAGE-MANIFEST.json').read_bytes())
        failure = self.missing()
        with patch.object(vqm, 'session_grid', side_effect=failure), patch.object(vqm, 'ROOT', self.root): text, error = self.invoke()
        self.assertEqual(text, ''); self.assertIs(error, failure)

    def test_alternate_bound_age_policy_and_future_publication_are_distinct(self):
        from vqm_research import profile
        p = profile(); p['max_financial_period_age_days'] = 20; d = copy.deepcopy(self.doc); d['profile_sha256'] = digest(p)
        self.assertEqual(self.direct(d, p)['rows'][0]['timing']['age_status'], 'OUTSIDE_BOUND_POLICY')
        d = copy.deepcopy(self.doc)
        for source in d['sources']:
            if source['kind'] == 'financial': source['published_at'] = '2099-01-01T00:00:00Z'
        self.assertIn('FUTURE_SOURCE', self.direct(d)['rows'][0]['facts']['net_income_ttm']['native_error'])

    def test_zero_denominator_and_negative_income_stay_typed_not_eps(self):
        for income in [0, -3]:
            d = copy.deepcopy(self.doc); d['rows'][0]['facts']['net_income_ttm']['value'] = income
            row = self.direct(d)['rows'][0]
            self.assertEqual(row['income_sign'], 'ZERO' if income == 0 else 'NEGATIVE')
            self.assertIsNone(row['reported_eps']); self.assertIsNone(row['actual_total_shares'])
            if income == 0: self.assertEqual(row['ratios']['aggregate_cap_over_income']['status'], 'UNDEFINED_ZERO_DENOMINATOR')
        d['rows'][0]['facts']['close_price']['value'] = 0
        self.assertEqual(self.direct(d)['rows'][0]['ratios']['conditional_share_equivalent']['status'], 'UNDEFINED_ZERO_DENOMINATOR')

    def test_universe_membership_and_declared_class_scope_preserved(self):
        result = self.direct(); self.assertEqual(len(result['rows']), len(self.doc['universe_symbols']))
        self.assertTrue(all(row['actual_total_shares'] is None for row in result['rows']))
        d = copy.deepcopy(self.doc); d['rows'].pop()
        with self.assertRaisesRegex(ValueError, 'COMPLETE_UNIVERSE_ROWS_REQUIRED'): self.direct(d)

    def test_snapshot_only_diagnostic_never_claims_full_ingress_or_score(self):
        import vqm_diagnostics as diagnostic
        out = diagnostic.diagnose_snapshot(self.path.read_bytes(), ROOT, self.missing())
        self.assertEqual(out['full_ingress'], 'NOT_BOUND'); self.assertIsNone(out['score']); self.assertIsNone(out['ranking'])
        self.assertFalse(out['source_authenticity_verified']); self.assertFalse(out['whole_answer_verified'])

    def test_cli_owned_file_paths_with_real_child_process_and_no_implicit_outputs(self):
        import os, subprocess
        env = dict(os.environ); env.pop('PYTHONPATH', None); env.pop('PYTHONHOME', None)
        before = set(self.root.iterdir())
        result = subprocess.run([sys.executable, '-S', '-B', str(ROOT / 'scripts/vqm_research.py'), str(self.path)], cwd=self.root, env=env, capture_output=True)
        self.assertEqual(result.returncode, 1); self.assertIn(b"No module named 'exchange_calendars'", result.stderr)
        self.assertEqual(json.loads(result.stdout)['full_ingress'], 'NOT_BOUND')
        self.assertEqual(set(self.root.iterdir()), before)


if __name__=='__main__':
    unittest.main()
