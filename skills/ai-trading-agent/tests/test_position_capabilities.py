import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from derivatives_toolkit import FUTURES_PNL_FIELDS, futures_pnl
from multi_asset_risk import scenario_book


class PositionCapabilitiesTests(unittest.TestCase):
    def setUp(self):
        self.future = dict(id="Q",kind="future",quantity=-3,multiplier=25,mark=7,
                           currency="USD",fx_to_base=1)
        self.equity = dict(id="E",kind="equity",quantity=8,multiplier=1,mark=40,
                           currency="EUR",fx_to_base=1.2)
        self.book = dict(positions=[self.future,self.equity],nav=5000,base_currency="USD",
            scenarios=[dict(name="test",positions={"Q":{"price_change":-10},"E":{"price_return":-.1}},
                            fx_returns={"EUR":-.2})])

    def test_scenario_and_research_routes_remain_distinct(self):
        before=copy.deepcopy(self.book)
        out=scenario_book(**self.book)
        future,equity=out["equity_and_futures_capabilities"]
        self.assertEqual(self.book,before)
        self.assertEqual([future["id"],equity["id"]],["Q","E"])
        self.assertEqual(equity["mark_source"],"/positions/1/mark")
        self.assertEqual(future["computed_operation"],"risk.scenarios")
        self.assertIn("Issuer fundamentals",equity["further_research"][0]["purpose"])
        self.assertIn("adjusted return",equity["further_research"][1]["required"])
        self.assertIn("expiry",future["further_research"][0]["required"])
        self.assertIn("collateral",future["further_research"][1]["required"])
        self.assertFalse(future["execution_authorized"])
        self.assertFalse(out["nav_reconciled"])
        self.assertAlmostEqual(out["scenarios"][0]["pnl_base"],750-107.52)

    def test_only_valid_contract_conversion_and_multiplier_survive(self):
        ledger=scenario_book(**self.book)["equity_and_futures_capabilities"][0]["observed_settlement"]
        fields=ledger["field_basis"]
        self.assertEqual(set(fields),set(FUTURES_PNL_FIELDS))
        self.assertEqual(fields["signed_contracts"],dict(status="derived_from_signed_quantity",
                          value=-3,source="/positions/0/quantity"))
        self.assertEqual(fields["multiplier"],dict(status="explicit_unvalidated",source="/positions/0/multiplier"))
        self.assertEqual(set(ledger["missing_fields"]),set(FUTURES_PNL_FIELDS)-{"signed_contracts","multiplier"})
        self.assertFalse(ledger["calculated"])

    def test_observed_inputs_are_position_local_and_zero_or_negative_can_be_real(self):
        self.equity.update(entry_at="2023-01-05T21:00:00Z",entry_price=7)
        self.future.update(fees=0,entry_price=-5,settlements=[])
        for mark in (-5,0,7):
            self.future["mark"]=mark
            ledger=scenario_book(**self.book)["equity_and_futures_capabilities"][0]["observed_settlement"]
            fields=ledger["field_basis"]
            self.assertEqual(fields["entry_price"]["source"],"/positions/0/entry_price")
            self.assertEqual(fields["fees"]["source"],"/positions/0/fees")
            self.assertIn("entry_at",ledger["missing_fields"])
            self.assertIn("settlements",ledger["missing_fields"])
        self.future["entry_price"]=0
        fields=scenario_book(**self.book)["equity_and_futures_capabilities"][0]["observed_settlement"]["field_basis"]
        self.assertEqual(fields["entry_price"]["status"],"explicit_unvalidated")

    def test_fractional_conflicting_and_invalid_sizes_cannot_be_called_valid_contracts(self):
        for quantity,explicit in ((2.5,None),(0,None),(2,5),(2,True),(2,2.0)):
            with self.subTest(quantity=quantity,explicit=explicit):
                self.future.update(quantity=quantity,signed_contracts=explicit)
                ledger=scenario_book(**self.book)["equity_and_futures_capabilities"][0]["observed_settlement"]
                self.assertIn("signed_contracts",ledger["missing_fields"]+ledger["invalid_fields"])
                self.assertFalse(ledger["calculated"])

    def test_even_complete_explicit_fields_require_full_settlement_validation(self):
        self.future.update(signed_contracts=-3,entry_price=2,entry_at="2025-01-02T21:00:00Z",
                           settlements=[{"at":"2025-01-03T21:00:00Z","price":-3}],
                           fees=0,price_unit="USD/point",rounding="unrounded_research",
                           currency_decimals=2,settlement_method="variation_margin",terminal_state="open")
        ledger=scenario_book(**self.book)["equity_and_futures_capabilities"][0]["observed_settlement"]
        self.assertEqual(ledger["missing_fields"],[])
        self.assertEqual(ledger["invalid_fields"],[])
        self.assertFalse(ledger["calculated"])
        self.assertEqual(futures_pnl({k:self.future[k] for k in FUTURES_PNL_FIELDS})["net_pnl"],375)

    def test_normal_cli_preserves_book_and_signed_shock_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp).resolve()
            request=directory/"scenario.json"
            request.write_text(json.dumps(dict(operation="scenarios",inputs=self.book)),encoding="utf8")
            command=[sys.executable,"-B",str(ROOT/"scripts/multi_asset_risk.py"),str(request)]
            result=subprocess.run(command,capture_output=True,text=True,check=True)
            out=json.loads(result.stdout)
            self.assertEqual(out["scenarios"][0]["positions"][0]["scenario_unit_price"],-3)
            self.assertIn("entry_price",out["equity_and_futures_capabilities"][0]["observed_settlement"]["missing_fields"])


if __name__ == "__main__":
    unittest.main()
