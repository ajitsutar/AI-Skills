"""Date precision must never backdate unknown SEC publication times."""
import copy
from datetime import date, datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from research_data import point_in_time_fact


def facts(*rows):
    return {'facts':{'us-gaap':{'NetIncomeLoss':{'units':{'USD':list(rows)}}}}}


def row(filed='2026-07-01',val=100):
    return {'filed':filed,'start':'2026-01-01','end':'2026-03-31','val':val}


def select(body,as_of,**period):
    return point_in_time_fact(body,'us-gaap','NetIncomeLoss','USD',as_of,**(period or {'end':'2026-03-31'}))


class SecPointInTimeTests(unittest.TestCase):
    def test_same_filing_date_intraday_is_ineligible(self):
        body=facts(row())
        for cutoff in ['2026-07-01T13:30:00Z','2026-07-01T23:59:59-04:00','2026-07-02T03:59:59.999999Z']:
            self.assertIsNone(select(body,cutoff))

    def test_summer_exact_next_new_york_midnight(self):
        body=facts(row())
        for cutoff in ['2026-07-02T04:00:00Z','2026-07-02T00:00:00-04:00','2026-07-02T06:00:00+02:00']:
            self.assertEqual(select(body,cutoff)['val'],100)

    def test_winter_next_midnight_uses_standard_offset(self):
        body=facts(row('2026-01-20'))
        self.assertIsNone(select(body,'2026-01-21T04:59:59Z'))
        self.assertEqual(select(body,'2026-01-21T05:00:00Z')['val'],100)

    def test_dst_transition_uses_next_day_offset(self):
        for filed,before,at in [('2026-03-08','2026-03-09T03:59:59Z','2026-03-09T04:00:00Z'),
                                 ('2026-11-01','2026-11-02T04:59:59Z','2026-11-02T05:00:00Z')]:
            body=facts(row(filed))
            self.assertIsNone(select(body,before))
            self.assertEqual(select(body,at)['val'],100)

    def test_date_cutoff_means_start_of_new_york_day(self):
        body=facts(row())
        self.assertIsNone(select(body,'2026-07-01'))
        self.assertEqual(select(body,'2026-07-02')['val'],100)
        self.assertEqual(select(body,date(2026,7,2))['val'],100)
        self.assertIsNone(select(body,'2026-07-02T00:00:00Z'))

    def test_later_restatement_does_not_leak_on_filing_day(self):
        body=facts(row(),row('2026-08-01',20))
        self.assertEqual(select(body,'2026-08-01T23:00:00-04:00')['val'],100)
        self.assertEqual(select(body,'2026-08-02')['val'],20)

    def test_missing_dates_not_eligible_and_invalid_dates_rejected(self):
        missing=row();missing.pop('filed')
        self.assertIsNone(select(facts(missing,row(None)),'2026-07-02'))
        for invalid in ['2026-02-30','2026-7-1','2026-07-01T12:00:00Z',True,'']:
            with self.assertRaises(ValueError):select(facts(row(invalid)),'2026-07-02')

    def test_naive_timestamp_or_malformed_cutoff_rejected(self):
        for invalid in ['2026-07-02T12:00:00','2026-02-30','2026-07-02garbage',None,datetime(2026,7,2),
                        '2026-07-02T12:00:00+00:99','2026-07-02T12:00:00+01:60']:
            with self.assertRaises(ValueError):select(facts(row()),invalid)
        self.assertEqual(select(facts(row()),datetime(2026,7,2,4,tzinfo=timezone.utc))['val'],100)

    def test_original_row_and_input_are_preserved(self):
        original=row();body=facts(original);snapshot=copy.deepcopy(body)
        selected=select(body,'2026-07-02')
        self.assertIs(selected,original)
        self.assertEqual(body,snapshot)

    def test_exact_period_and_ambiguous_context_checks_preserved(self):
        with self.assertRaisesRegex(ValueError,'exact period'):
            point_in_time_fact(facts(row()),'us-gaap','NetIncomeLoss','USD','2026-07-02')
        self.assertIsNone(select(facts(row()),'2026-07-02',start='2025-01-01',end='2026-03-31'))
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            select(facts(row(),row(val=20)),'2026-07-02')


if __name__=='__main__':unittest.main()
