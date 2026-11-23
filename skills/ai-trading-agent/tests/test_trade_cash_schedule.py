"""Source-schedule coverage at the normal planning.cash_plan entry point."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from planning_alignment import cash_plan


def schedule():
    return {'currency':'EUR','as_of':'2025-07-02T12:00:00+02:00','settled_cash':'1300.50',
            'reservations':'70.25','floor':100,'business_dates':['2025-07-03','2025-07-07','2025-07-08','2025-07-09'],
            'settlement_lag_business_days':1,'events':[
                {'id':'entry','at':'2025-07-03T14:00:00+02:00','kind':'buy','cash_effect':-810,'confirmed':False},
                {'id':'exit','at':'2025-07-07T15:00:00+02:00','kind':'sale','cash_effect':170,'confirmed':False},
                {'id':'bill','at':'2025-07-08T12:00:00+02:00','kind':'withdrawal','cash_effect':-460,'confirmed':True}]}


class TradeCashScheduleTests(unittest.TestCase):
    def test_buy_settlement_releases_only_that_trades_commitment(self):
        doc=schedule();original=copy.deepcopy(doc);result=cash_plan(doc);self.assertEqual(doc,original)
        s=result['scenarios']['buy_fills'];first,second=s['postings_by_source_event'][:2]
        self.assertEqual((first['phase'],first['settled_delta'],first['trade_reservation_delta'],first['available_delta']),
                         ('buy_commitment','0','810','-810'))
        self.assertEqual((second['at_or_date'],second['phase'],second['settled_delta'],second['trade_reservation_delta'],second['available_delta']),
                         ('2025-07-07','buy_settlement','-810','-810','0'))
        self.assertEqual(s['ending_after_all_postings'],{'settled':'30.50','reserved':'70.25','available_before_floor':'-39.75',
                                                        'signed_floor_headroom':'-139.75','floor_gap':'139.75'})
        self.assertEqual(result['scenarios']['confirmed_only']['included_fills'],[])

    def test_sale_credit_has_date_and_both_intraday_availability_orders(self):
        r=cash_plan(schedule());s=r['scenarios']['all_fills']
        sale=[x for x in s['postings_by_source_event'] if x['source_event']=='exit']
        self.assertEqual([(x['at_or_date'],x['available_delta']) for x in sale],[('2025-07-07T15:00:00+02:00','0'),('2025-07-08','170')])
        self.assertEqual(s['cash_bounds']['maximum_floor_gap_range'],{'lower':'0','upper':'139.75'})
        self.assertEqual(s['ending_after_all_postings']['floor_gap'],'0')
        self.assertEqual(r['calendar_timezone'],'+02:00')
        self.assertFalse(r['execution_authorized'])

    def test_confirmed_fill_and_later_cash_demand_with_two_day_lag(self):
        d=schedule();d['settlement_lag_business_days']=2
        d['events'][0]['confirmed']=True
        r=cash_plan(d)
        s=r['scenarios']['confirmed_only'];self.assertEqual(s['included_fills'],['entry'])
        self.assertEqual(s['postings_by_source_event'][1]['at_or_date'],'2025-07-08')
        self.assertEqual(s['ending_after_all_postings']['floor_gap'],'139.75')
        self.assertEqual(r['scenarios']['sale_fills']['postings_by_source_event'][3]['at_or_date'],'2025-07-09')

    def test_conflicting_calendar_signs_and_unmodeled_terms_require_clarification(self):
        for change in (lambda d:d.update(settlement_rule='three business days after fill'),lambda d:d['events'][0].update(cash_effect=22),
                       lambda d:d['events'][0].update(reservation_release=22),lambda d:d.update(settlement_lag_business_days=6),
                       lambda d:d['events'][0].update(currency='JPY'),lambda d:d['events'][0].update(at='2025-07-03T14:00:00-02:00')):
            with self.subTest(change=change),self.assertRaises(ValueError):
                d=schedule();change(d);cash_plan(d)
