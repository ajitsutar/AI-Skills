"""Listing membership tests with synthetic records, no provider/network dependency."""
import contextlib
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from listed_universe import build_universe, issuer_name, security_type
from public_research_fetch import argument_parser, universe_spec


def documents():
    return {
        'nasdaqlisted': ("Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
            "AAA|Example Inc. - Class A Common Stock|Q|N|N|100|N|N\n"
            "AAB|Example Inc. - Class B Common Stock|Q|N|N|100|N|N\n"
            "ADR|Foreign Example - American Depositary Shares|G|N|N|100|N|N\n"
            "SMOL|Tiny Example - Common Stock|S|N|D|100|N|N\n"
            "ETF|Test Equity ETF|G|N|N|100|Y|N\n"
            "FAKE|Test Issue - Common Stock|G|Y|N|100|N|N\n"
            "File Creation Time: 1009202621:31|||||||\n").encode(),
        'otherlisted': ("ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n"
            "NYSE|Example NYSE Common Stock|N|NYSE|N|100|N|NYSE\n"
            "AMEX|Small Example Common Stock|A|AMEX|N|100|N|AMEX\n"
            "NEW|New Exchange Example Common Stock|F|NEW|N|100|N|NEW\n"
            "UNK|Unspecified Security|N|UNK|N|100|N|UNK\n"
            "PR$A|Example Depositary Shares representing Preferred Stock|N|PRpA|N|100|N|PR-A\n"
            "File Creation Time: 1009202621:31|||||||\n").encode()}


class ListedUniverseTests(unittest.TestCase):
    def test_all_exchanges_adrs_small_caps_and_classes_preserved(self):
        result = build_universe(documents(), '2026-10-09', '2026-10-11')
        rows = {r['symbol']: r for r in result['rows']}
        self.assertEqual(set(rows), {'AAA', 'AAB', 'ADR', 'SMOL', 'NYSE', 'AMEX', 'NEW', 'UNK'})
        self.assertEqual(rows['ADR']['security_type'], 'listed_adr')
        self.assertEqual(rows['SMOL']['financial_status'], 'D')
        self.assertEqual(rows['AAA']['issuer_id'], rows['AAB']['issuer_id'])
        self.assertEqual(rows['NEW']['listing_exchange_code'], 'F')
        self.assertEqual(result['evidence']['directory_record_count'], 11)
        self.assertEqual(result['evidence']['classification_unresolved_count'], 1)
        data = documents()
        data['otherlisted'] = data['otherlisted'].replace(b'Unspecified Security', b'Company Depositary Shares')
        parsed = build_universe(data, '2026-10-09', '2026-10-11')
        unresolved = next(r for r in parsed['rows'] if r['symbol'] == 'UNK')
        self.assertFalse(unresolved['provider_equity_resolution_allowed'])

    def test_nonstock_security_descriptions_and_similar_company_names(self):
        cases = {'Preferred Bank - Common Stock': 'common_equity',
            'Foreign Company American Depositary Shares each representing Ordinary Shares': 'listed_adr',
            'Example Depositary Shares each representing Preferred Stock': 'preferred_security',
            'Example - Warrants exercisable for Common Stock': 'warrant_or_right',
            'Example - Rights each convertible into Common Stock': 'warrant_or_right',
            'Example - Units consisting of Common Stock and Warrants': 'bundled_unit',
            'Example Common Units representing limited partner interests': 'common_equity',
            'Example Income Fund Common Shares': 'fund',
            'Example 5% Senior Notes due 2030': 'debt_security'}
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(security_type({'Security Name': name, 'ETF': 'N', 'Test Issue': 'N'}), expected)

    def test_issuer_class_and_adr_descriptions_normalize(self):
        self.assertEqual(issuer_name('Example Inc Class A Common Stock'),
                         issuer_name('Example Inc Class B Common Stock'))
        self.assertEqual(issuer_name('Example Inc American Depositary Shares'), 'example inc')

    def test_missing_file_stale_file_bad_footer_and_duplicate_fail(self):
        variants = []
        missing = documents(); del missing['otherlisted']; variants.append(missing)
        stale = documents(); stale['nasdaqlisted'] = stale['nasdaqlisted'].replace(b'10092026', b'10082026'); variants.append(stale)
        footer = documents(); footer['otherlisted'] = footer['otherlisted'].split(b'File Creation')[0]; variants.append(footer)
        duplicate = documents(); duplicate['otherlisted'] = duplicate['otherlisted'].replace(b'NYSE|Example', b'AAA|Example'); variants.append(duplicate)
        for data in variants:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    build_universe(data, '2026-10-09', '2026-10-11')

    def test_default_explicit_index_and_mutually_exclusive_cli(self):
        self.assertEqual(universe_spec(), {'kind': 'preset', 'name': 'us-listed'})
        self.assertEqual(universe_spec('sp500')['name'], 'sp500')
        required = ['--output', 'dummy', '--decision-at', '2026-10-11T10:00:00Z',
                    '--hold', 'P1M', '--prompt-file', 'dummy.txt']
        self.assertIsNone(argument_parser().parse_args(required).universe_preset)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            argument_parser().parse_args(required + ['--universe', 'custom.json', '--universe-preset', 'sp500'])

    def test_abbreviated_instruments_are_not_mistaken_for_common_equity(self):
        cases = {'Company - Units': 'bundled_unit', 'Company - Series B Right': 'warrant_or_right',
            'Company - Warrant.': 'warrant_or_right', 'Company Pfd Ser A': 'preferred_security',
            'Company Preferred Limited Partnership Units': 'preferred_security',
            'Company Index ETN': 'debt_security', 'Company First Mortgage Bonds': 'debt_security',
            'Company - Class C Capital Stock': 'common_equity',
            'Company - New York Registry Shares': 'common_equity'}
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(security_type({'Security Name': name, 'ETF': 'N', 'Test Issue': 'N'}), expected)


if __name__ == '__main__':
    unittest.main()
