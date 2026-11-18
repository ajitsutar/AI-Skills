from copy import deepcopy
from decimal import Decimal,localcontext
import unittest
import test_insider_disclosures as fixture
import institution_disclosures as institution
from source_claims import Corpus


class InstitutionDisclosureTests(unittest.TestCase):
 setUp=fixture.InsiderDisclosureTests.setUp
 write=fixture.InsiderDisclosureTests.write
 def result(self):return institution.analyze(Corpus(self.manifest,self.pin,self.sources))['datasets'][0]
 def test_original_and_amended_period_values_are_not_summed(self):
  data=self.result();self.assertEqual(len(data['rows']),3);later=data['snapshots'][1]
  self.assertEqual(later['effective_reported_shares'],'720');self.assertEqual(later['effective_record_index'],2)
  self.assertEqual(later['amendment_links'][0]['amendment_after_prior_calendar_days'],9)
 def test_comparison_uses_amended_same_period_not_later_position(self):
  row=self.result()['comparisons'][0];self.assertEqual(row['arithmetic']['reported_share_difference'],'120')
  self.assertEqual(Decimal(row['arithmetic']['percent_of_prior_reported_shares']),Decimal(20))
  self.assertFalse(row['current_holdings_established']);self.assertFalse(row['transactions_or_motives_established'])
 def test_unamended_comparison_explicitly_superseded(self):
  row=self.result()['comparisons'][0]['superseded_original_comparison']
  self.assertEqual(row['arithmetic']['reported_share_difference'],'250');self.assertIn('SUPERSEDED',row['status'])
 def test_availability_not_backdated_to_original_filing(self):
  row=self.result()['comparisons'][0];self.assertEqual(row['information_available_from'],'2034-05-12')
  self.assertEqual(row['superseded_original_comparison']['original_filing_available_from'],'2034-05-03')
 def test_lags_calendar_only_not_legal_deadline(self):
  row=self.result()['rows'][1];self.assertEqual(row['report_to_filing_calendar_days'],33)
  self.assertFalse(row['legal_lateness_or_compliance_established'])
 def test_unrelated_disclosures_are_not_positions(self):
  data=self.result();self.assertEqual(len(data['rows']),3);self.assertFalse(data['other_disclosure_populations_used_as_institution_positions'])
 def test_manager_and_security_scope_are_not_merged(self):
  self.doc['institutions'][2]['manager']='OTHER';self.write();data=self.result()
  self.assertEqual(len(data['snapshots']),3);self.assertTrue(any(s['unresolved'] for s in data['snapshots']))
  self.doc['institutions'][2]['manager']='SYN-M';self.doc['institutions'][2]['share_class']='B';self.write()
  self.assertEqual(len(self.result()['snapshots']),3)
 def test_unknown_scope_is_visible_without_invented_entity_perimeter(self):
  row=self.result()['comparisons'][0];self.assertIn('security_id',row['unknown_scope_dimensions'])
  self.assertFalse(row['complete_entity_perimeter_established']);self.assertFalse(row['security_identity_verified'])
 def test_explicit_account_subaccount_and_units_partition_period_comparisons(self):
  original=deepcopy(self.doc['institutions'])
  for key in ('account_id','subaccount_id','holding_unit','shares_unit','unit'):
   with self.subTest(dimension=key):
    self.doc['institutions']=deepcopy(original)
    for i,row in enumerate(self.doc['institutions']):row[key]='SCOPE-A' if i==0 else 'SCOPE-B'
    self.write();self.assertEqual(self.result()['comparisons'],[])
 def test_explicit_account_subaccount_and_units_partition_amendment_chains(self):
  original=deepcopy(self.doc['institutions'])
  for key in ('account_id','subaccount_id','holding_unit','shares_unit','unit'):
   with self.subTest(dimension=key):
    self.doc['institutions']=deepcopy(original)
    self.doc['institutions'][1][key]='SCOPE-A';self.doc['institutions'][2][key]='SCOPE-B';self.write()
    data=self.result();amendment=next(s for s in data['snapshots'] if 2 in s['all_record_indices'])
    self.assertIsNone(amendment['effective_record_index']);self.assertEqual(amendment['amendment_links'],[])
 def test_equal_explicit_scopes_allow_reported_comparison_but_do_not_prove_perimeter(self):
  for row in self.doc['institutions']:row.update(account_id='ACCOUNT-A',subaccount_id='SUB-A',holding_unit='shares')
  self.write();row=self.result()['comparisons'][0]
  self.assertEqual(row['arithmetic']['reported_share_difference'],'120');self.assertFalse(row['complete_entity_perimeter_established'])
 def test_missing_versus_declared_account_is_not_silently_equated(self):
  self.doc['institutions'][0]['account_id']='ACCOUNT-A';self.write();self.assertEqual(self.result()['comparisons'],[])
 def test_missing_manager_does_not_become_verified_comparison(self):
  for row in self.doc['institutions']:row.pop('manager')
  self.write();self.assertIsNone(self.result()['comparisons'][0]['arithmetic'])
 def test_unmatched_predecessor_remains_unresolved(self):
  self.doc['institutions'][2]['amends']='2034-04-01';self.write();data=self.result()
  self.assertIsNone(data['snapshots'][1]['effective_record_index']);self.assertIsNone(data['comparisons'][0]['arithmetic'])
 def test_duplicate_predecessor_does_not_choose_convenient_row(self):
  self.doc['institutions'].append(deepcopy(self.doc['institutions'][1]));self.write()
  self.assertIsNone(self.result()['snapshots'][1]['effective_record_index'])
 def test_branching_amendments_remain_unresolved(self):
  row=deepcopy(self.doc['institutions'][2]);row.update(filed='2034-05-16',shares=700);self.doc['institutions'].append(row);self.write()
  self.assertIsNone(self.result()['snapshots'][1]['effective_record_index'])
 def test_serial_amendments_resolve_only_exact_chain(self):
  row=deepcopy(self.doc['institutions'][2]);row.update(filed='2034-05-16',amends='2034-05-12',shares=700);self.doc['institutions'].append(row);self.write()
  data=self.result();self.assertEqual(data['snapshots'][1]['effective_reported_shares'],'700')
  self.assertEqual(data['comparisons'][0]['information_available_from'],'2034-05-16')
 def test_nonforward_amendment_not_applied(self):
  self.doc['institutions'][2]['filed']='2034-05-01';self.write();self.assertIsNone(self.result()['snapshots'][1]['effective_record_index'])
 def test_zero_prior_percentage_undefined(self):
  self.doc['institutions'][0]['shares']=0;self.write();row=self.result()['comparisons'][0]['arithmetic']
  self.assertIsNone(row['percent_of_prior_reported_shares']);self.assertEqual(row['reported_share_difference'],'720')
 def test_arithmetic_independent_of_ambient_precision(self):
  with localcontext() as ctx:
   ctx.prec=2;row=institution.difference(Decimal('12345678901234567890123456789'),Decimal('12345678901234567890123456799'))
  self.assertEqual(row['reported_share_difference'],'10')
 def test_malformed_schema_refused(self):
  self.doc['institutions'][0]['amendment']='false';self.write()
  with self.assertRaisesRegex(ValueError,'INSTITUTION_AMENDMENT_BOOLEAN'):self.result()


if __name__=='__main__':unittest.main()
