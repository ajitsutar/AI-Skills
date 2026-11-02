import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyst_adapter import extract,earnings_basis
def request(text,fmt='markdown'):
 return {'as_of':'2026-11-01T00:00:00Z','issuer_id':'demo','currency':'USD','share_basis':'post-split','target_horizon':'unknown','format':fmt,'text':text,'source':{'id':'p','url':'https://example.test','available_at':'2026-10-31T00:00:00Z','access':'aggregate_table'}}
class AnalystAdapterTests(unittest.TestCase):
 def test_markdown_preserves_first_last_and_skips_navigation(self):
  text='Noise\nL99: Analyst | Firm | Rating | Price Target | Date\nL100: --- | --- | --- | --- | ---\nL101: A Name | Bank A | Buy | $100 → $90 | Oct 30, 2026\nL102: B Name | Bank B | Hold | $70 | Oct 29, 2026\nMore Analyst Ratings | More | More | 80 | Oct 30, 2026'
  r=extract(request(text));self.assertEqual([x['firm_name'] for x in r['records']],['Bank A','Bank B']);self.assertEqual(r['records'][0]['target'],90);self.assertEqual(r['records'][0]['previous_target'],100);self.assertEqual(r['records'][0]['target_horizon'],'unknown');self.assertFalse(r['full_report_access_inferred'])
 def test_column_reorder_html_and_offset(self):
  t='<p>extra</p><table><tr><th>Date</th><th>Target</th><th>Broker</th><th>Analyst Name</th></tr><tr><td>2026-10-30</td><td>$125.50</td><td>Firm</td><td><a href="x">Person</a></td></tr></table>'
  r=extract(request(t,'html'));self.assertEqual(r['records'][0]['analyst_name'],'Person');self.assertEqual(r['records'][0]['target'],125.5)
 def test_conflicts_and_bad_dates_retained(self):
  t='Analyst | Firm | Target | Date\nA | B | 100 | 2026-10-30\nA | B | 90 | 2026-10-30\nX | Y | 500 | 2027-01-01\nZ | Q | 5% upside | 2026-10-30'
  r=extract(request(t));self.assertEqual(r['status'],'CONFLICTS_PRESENT');self.assertEqual(len(r['excluded']),2);self.assertFalse(r['consensus_computed'])
 def test_earnings_periods_do_not_blend(self):
  r={'as_of':'2026-11-01T00:00:00Z','quote':{'price':200,'currency':'USD','share_basis':'post','available_at':'2026-10-30T20:00:00Z'},'estimates':[{'id':'a','eps':10,'period_start':'2026-01-01','period_end':'2026-12-31','period_type':'fiscal','accounting_basis':'adjusted','share_basis':'post','currency':'USD','source':'fixture','available_at':'2026-10-30T00:00:00Z'}]}
  b=copy.deepcopy(r['estimates'][0]);b.update(id='b',eps=12,period_type='rolling',period_end='2027-10-30');r['estimates'].append(b)
  u=copy.deepcopy(b);u.update(id='unknown',period_type=None);r['estimates'].append(u)
  o=earnings_basis(r);self.assertEqual(o['results'][0]['multiple'],20);self.assertIsNone(o['results'][2]['multiple']);self.assertFalse(o['averaged_multiples'])
if __name__=='__main__':unittest.main()
