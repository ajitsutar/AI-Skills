from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from portfolio_analytics import lookthrough


class PortfolioDatePrecisionTests(unittest.TestCase):
    def test_declared_date_preserves_holdings_math_without_invented_timestamp(self):
        positions=[{'symbol':'FUND','asset_type':'etf','quantity':2,'mark':75}]
        fund={'as_of':'2026-10-09','evidence':'dated holdings table','holdings':[
            {'symbol':'ISSUER','asset_type':'equity','fraction':.8,'sector':'industry'}]}
        dated=lookthrough(positions,200,{'FUND':fund})
        self.assertEqual(dated['fund_sources']['FUND']['as_of'],'2026-10-09')
        self.assertEqual(dated['fund_sources']['FUND']['as_of_precision'],'date')
        self.assertEqual(dated['issuer_exposure']['ISSUER'],120)
        self.assertAlmostEqual(dated['unknown_fund_value'],30)
        timed=lookthrough(positions,200,{'FUND':{**fund,'as_of':'2026-10-09T15:00:00Z'}})
        self.assertEqual(timed['fund_sources']['FUND']['as_of_precision'],'timestamp')
        self.assertEqual(timed['issuer_exposure'],dated['issuer_exposure'])
        with self.assertRaises(ValueError):lookthrough(positions,200,{'FUND':{**fund,'as_of':'2026-13-09'}})


if __name__=='__main__':unittest.main()
