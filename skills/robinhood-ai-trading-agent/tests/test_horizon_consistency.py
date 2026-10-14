"""Unknown entry expiry must not change the supplied proposed holding interval."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from evidence_semantics import event_window
from horizon_review import resolve_horizon, review_scenarios
from research_contracts import route_horizon
from screen_review import review_screen


def fixture():
    return json.loads((ROOT / 'examples/fictional-horizon-screen.json').read_text(encoding='utf-8'))


class HorizonConsistencyTests(unittest.TestCase):
    def test_omitted_and_null_expiry_preserve_proposed_fixed_exit(self):
        for omitted in (True, False):
            doc = fixture()
            expected = resolve_horizon(doc['horizon'])
            if omitted:
                doc['horizon'].pop('latest_entry_at')
            else:
                doc['horizon']['latest_entry_at'] = None
            original = copy.deepcopy(doc)
            result = review_screen(doc)
            resolved = result['horizon']
            with self.subTest(omitted=omitted):
                self.assertIsNone(resolved['latest_entry_at'])
                self.assertEqual(resolved['latest_entry_status'], 'UNKNOWN')
                self.assertEqual(resolved['exit_at'], expected['exit_at'])
                self.assertEqual(resolved['latest_possible_exit_at'], expected['exit_at'])
                self.assertEqual(resolved['calendar_scope'], 'proposed_entry_only')
                self.assertEqual(result['candidates'][0]['status'], 'Eligible')
                self.assertFalse(resolved['execution_authorized'])
                self.assertEqual(doc, original)
                json.dumps(result, allow_nan=False)

    def test_unknown_rolling_expiry_has_no_latest_possible_exit(self):
        spec = fixture()['horizon']
        spec.update(deadline_mode='rolling_from_entry', latest_entry_at=None)
        result = resolve_horizon(spec)
        self.assertEqual(result['exit_at'], '2026-04-15T19:45:00+00:00')
        self.assertIsNone(result['latest_possible_exit_at'])
        self.assertEqual(result['calendar_scope'], 'proposed_entry_only')
        spec['calendar_confirmed_through'] = '2026-04-14'
        self.assertTrue(resolve_horizon(spec)['calendar_refresh_required'])
        self.assertEqual(resolve_horizon(spec)['calendar_status'], 'PROVISIONAL')

    def test_supplied_expiry_still_bounds_rolling_calendar(self):
        spec = fixture()['horizon']
        spec.update(deadline_mode='rolling_from_entry', calendar_confirmed_through='2026-04-15')
        result = resolve_horizon(spec)
        self.assertEqual(result['latest_entry_at'], '2026-01-16T15:00:00+00:00')
        self.assertEqual(result['latest_entry_status'], 'SUPPLIED')
        self.assertEqual(result['calendar_scope'], 'entry_window')
        self.assertEqual(result['latest_possible_exit_at'], '2026-04-16T19:45:00+00:00')
        self.assertTrue(result['calendar_refresh_required'])

    def test_unknown_expiry_supports_intraday_but_does_not_relax_proposed_entry(self):
        spec = fixture()['horizon']
        spec.update(latest_entry_at=None, strategy_route='intraday',
                    duration={'unit': 'same_session', 'value': 1})
        self.assertEqual(resolve_horizon(spec)['exit_at'], '2026-01-15T20:45:00+00:00')
        for entry in ('2026-01-15T13:00:00Z', '2026-01-15T20:50:00Z', '2026-01-17T15:00:00Z'):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                resolve_horizon({**spec, 'entry_at': entry})

    def test_supplied_invalid_expiry_is_not_treated_as_unknown(self):
        for latest in ('', 'unknown', '2026-01-15T14:45:00Z',
                       '2026-01-17T15:00:00Z', '2026-04-15T19:45:00Z'):
            spec = fixture()['horizon']
            spec['latest_entry_at'] = latest
            with self.subTest(latest=latest), self.assertRaises(ValueError):
                resolve_horizon(spec)

    def test_fixed_horizon_adapter_retains_unknown_expiry(self):
        spec = fixture()['horizon']
        spec.pop('latest_entry_at')
        result = route_horizon({'mode': 'fixed_exit', 'fixed_spec': spec})['result']
        self.assertEqual(result['hard_exit_at'], '2026-04-15T19:45:00+00:00')
        self.assertIsNone(result['resolved_fixed_exit']['latest_entry_at'])
        self.assertEqual(result['resolved_fixed_exit']['latest_entry_status'], 'UNKNOWN')
        self.assertNotIn('latest_entry_at', spec)

    def test_close_time_terminal_scenarios_are_not_silently_reanchored(self):
        doc = fixture()
        spec = doc['horizon']
        spec.pop('latest_entry_at')
        section = doc['candidates'][0]['horizon_review']['terminal_scenarios']
        section['exit_at'] = '2026-04-15T20:00:00Z'
        original = copy.deepcopy(section)
        result = review_scenarios(section, resolve_horizon(spec))
        self.assertFalse(result['complete'])
        self.assertEqual(result['reasons'], ['SCENARIOS_USE_DIFFERENT_EXIT'])
        self.assertEqual(section, original)

    def test_cash_close_time_cannot_replace_buffered_comparison(self):
        doc = fixture()
        doc['horizon']['latest_entry_at'] = None
        section = doc['candidates'][0]['horizon_review']['terminal_scenarios']
        section['cash_benchmark']['exit_at'] = '2026-04-15T20:00:00Z'
        original = copy.deepcopy(section)
        result = review_scenarios(section, resolve_horizon(doc['horizon']))
        self.assertFalse(result['complete'])
        self.assertTrue(result['arithmetic_valid'])
        self.assertTrue(any('must match the resolved holding interval' in r for r in result['reasons']))
        self.assertTrue(all(case['excess_over_cash'] is None for case in result['cases']))
        self.assertEqual(section, original)

    def test_uncertain_renewal_range_overlaps_january_exit(self):
        for renewal in ('2027', '2027-01'):
            with self.subTest(renewal=renewal):
                result = event_window(renewal, '2026-10-15', '2027-01-15')
                self.assertEqual(result['status'], 'OVERLAP')
                self.assertEqual(result['ranges']['event']['input'], renewal)
        self.assertEqual(event_window('2027-02', '2026-10-15', '2027-01-15')['status'],
                         'DEFINITELY_AFTER')


if __name__ == '__main__':
    unittest.main()
