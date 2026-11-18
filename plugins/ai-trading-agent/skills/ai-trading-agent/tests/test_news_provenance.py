"""Synthetic final-artifact provenance consistency tests, without external access."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import news_provenance as np

PUB = 'https://harbor.invalid/story/7'
ORIGIN = 'https://kestrel.invalid/releases/alpha'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class NewsProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = self.root / 'originals'; self.sources.mkdir()
        self.artifacts = self.root / 'artifacts'; self.artifacts.mkdir()
        self.manifest = self.root / 'ingress.json'
        self.source_entries = []

    def source(self, text=None, identity='source-1', format='text'):
        if text is None:
            text = f'Canonical identifier: {PUB}\nOriginal source: <{ORIGIN}>\n'
        raw = text.encode('utf-8') if isinstance(text, str) else text
        name = identity + '.txt'
        (self.sources / name).write_bytes(raw)
        self.source_entries.append({'id': identity, 'path': name, 'sha256': sha(raw), 'format': format})
        self.manifest.write_text(json.dumps({'schema_version': 1, 'sources': self.source_entries}), encoding='utf-8')

    def request(self, rows=None, bindings=None):
        rows = rows if rows is not None else [{'id': 'item-1', 'publication_url': PUB, 'underlying_origin': ORIGIN}]
        raw = json.dumps({'records': rows}).encode('utf-8')
        (self.artifacts / 'final.json').write_bytes(raw)
        return {'schema_version': 1,
                'final_ledger': {'path': 'final.json', 'sha256': sha(raw), 'rows_pointer': '/records',
                                 'id_pointer': '/id', 'publication_pointer': '/publication_url', 'origin_pointer': '/underlying_origin'},
                'bindings': bindings if bindings is not None else
                    [{'row_id': 'item-1', 'source_id': 'source-1', 'adapter': np.ADAPTER}]}

    def audit(self, request):
        return np.audit(request, self.artifacts, self.sources, self.manifest, sha(self.manifest.read_bytes()))

    def origin(self, result, index=0):
        return result['records'][index]['fields'][1]

    def test_actual_final_field_copy_is_detected_despite_correct_notes(self):
        self.source()
        request = self.request([{'id': 'item-1', 'publication_url': PUB, 'underlying_origin': PUB,
                                 'notes': 'The declared original link is ' + ORIGIN}])
        result = self.audit(request)
        self.assertEqual(self.origin(result)['status'], 'DIFFERS_FROM_SELECTED_DECLARATION')
        self.assertEqual(self.origin(result)['actual_value'], PUB)
        self.assertEqual(self.origin(result)['literal_url_candidates'], [ORIGIN])
        self.assertEqual(self.origin(result)['pointer'], '/records/0/underlying_origin')

    def test_matching_literal_fields_still_do_not_certify_semantics(self):
        self.source()
        result = self.audit(self.request())
        self.assertEqual(self.origin(result)['status'], 'MATCHES_SELECTED_DECLARATION')
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertFalse(result['source_authenticity_verified'])
        self.assertFalse(result['semantic_relation_verified'])
        self.assertEqual(result['coverage']['fields_compared_to_unique_declaration'], 2)

    def test_later_final_artifact_edit_invalidates_prior_request(self):
        self.source()
        request = self.request()
        self.audit(request)
        (self.artifacts / 'final.json').write_text('{"records": []}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'FINAL_LEDGER_HASH_MISMATCH'):
            self.audit(request)

    def test_no_origin_default_from_canonical_navigation_or_citation(self):
        self.source(f'Canonical identifier: {PUB}\nNavigation: {ORIGIN}\nCitation: {ORIGIN}\n')
        result = self.audit(self.request())
        self.assertEqual(self.origin(result)['status'], 'UNRESOLVED_NO_DECLARATION')
        self.assertEqual(self.origin(result)['literal_url_candidates'], [])

    def test_context_role_spoof_quote_negation_example_are_unresolved(self):
        for line in (f'Not Original source: {ORIGIN}', f'"Original source: {ORIGIN}"',
                     f'Example Original source: {ORIGIN}', f'> Original source: {ORIGIN}',
                     f'Origin note calls this Original source: {ORIGIN}'):
            with self.subTest(line=line):
                observed = np.declarations(line)['declared_original_link']
                self.assertEqual(np.role_status(observed), 'UNRESOLVED_CONTEXT')

    def test_unrelated_independence_caveat_does_not_negate_label(self):
        text = f'This distributor is not independent journalism. Original source: <{ORIGIN}>'
        self.assertEqual(np.role_status(np.declarations(text)['declared_original_link']), 'UNIQUE_LITERAL_DECLARATION')

    def test_multiline_quotes_fences_and_explicit_negating_suffix_unresolved(self):
        for text in (f'"Quoted passage\nOriginal source: <{ORIGIN}>\n"',
                     f'```text\nOriginal source: <{ORIGIN}>\n```',
                     f'<blockquote>\nOriginal source: <{ORIGIN}>\n</blockquote>',
                     f'Example:\nOriginal source: <{ORIGIN}>',
                     f'Original source: <{ORIGIN}> is not the original.'):
            with self.subTest(text=text):
                self.assertEqual(np.role_status(np.declarations(text)['declared_original_link']), 'UNRESOLVED_CONTEXT')

    def test_malformed_ports_are_not_url_candidates(self):
        for token in ('https://publisher.invalid:abc/a', 'https://publisher.invalid:99999/a'):
            self.assertFalse(np.valid_url(token))
            observations = np.declarations('Original source: <' + token + '>')['declared_original_link']
            self.assertEqual(observations[0]['candidates'], [])
            self.assertEqual(np.role_status(observations), 'UNRESOLVED_CONTEXT')

    def test_qualifier_words_inside_urls_are_not_prose_context(self):
        publication = 'https://publisher.example.invalid/quoted/template?illustrative=example'
        origin = 'https://issuer.example.invalid/news/hypothetical/quotation#incorrect'
        self.source(f'Canonical identifier: <{publication}>\nOriginal source: <{origin}>')
        request = self.request([{'id': 'item-1', 'publication_url': publication, 'underlying_origin': origin}])
        result = self.audit(request)
        self.assertEqual([field['status'] for field in result['records'][0]['fields']],
                         ['MATCHES_SELECTED_DECLARATION', 'MATCHES_SELECTED_DECLARATION'])
        self.assertEqual(self.origin(result)['literal_url_candidates'], [origin])
        for text in (f'Example: Original source: <{origin}>', f'Original source: <{origin}> is not the original.'):
            self.assertEqual(np.role_status(np.declarations(text)['declared_original_link']), 'UNRESOLVED_CONTEXT')

    def test_utf8_bytes_format_preserved_and_audited_without_relabeling(self):
        self.source(f'Canonical identifier: {PUB}\nOriginal source: <{ORIGIN}>\n<html>Local body</html>', format='bytes')
        manifest_before = self.manifest.read_bytes()
        result = self.audit(self.request())
        self.assertEqual(self.origin(result)['status'], 'MATCHES_SELECTED_DECLARATION')
        self.assertEqual(result['records'][0]['source']['format'], 'bytes')
        self.assertEqual(self.manifest.read_bytes(), manifest_before)

    def test_binary_bytes_format_reports_encoding_limit(self):
        self.source(b'\x89PNG\r\n\xff', format='bytes')
        result = self.audit(self.request())
        self.assertEqual(result['records'][0]['source']['format'], 'bytes')
        self.assertEqual(result['records'][0]['diagnostic'], 'UNSUPPORTED_SOURCE_ENCODING_UTF8')
        self.assertEqual(self.origin(result)['status'], 'INVALID_PROVENANCE')

    def test_competing_and_repeated_same_declarations_are_not_first_match(self):
        for second in (ORIGIN, 'https://another.invalid/release'):
            observed = np.declarations(f'Original source: <{ORIGIN}>\nOriginal source: <{second}>')['declared_original_link']
            self.assertEqual(len(observed), 2)
            self.assertEqual(np.role_status(observed), 'UNRESOLVED_MULTIPLE_DECLARATIONS')

    def test_full_document_scan_cannot_hide_competing_link(self):
        self.source(f'Canonical identifier: {PUB}\nOriginal source: <{ORIGIN}>\nOriginal source: <https://other.invalid/x>')
        result = self.audit(self.request())
        self.assertEqual(self.origin(result)['status'], 'UNRESOLVED_MULTIPLE_DECLARATIONS')
        self.assertEqual(len(self.origin(result)['literal_url_candidates']), 2)
        self.assertTrue(result['records'][0]['source']['full_document_scanned'])

    def test_terminal_period_alternatives_never_silently_normalized(self):
        self.source(f'Canonical identifier: {PUB}\nOriginal source: {ORIGIN}. More commentary follows.')
        wrong = self.request([{'id': 'item-1', 'publication_url': PUB, 'underlying_origin': PUB}])
        field = self.origin(self.audit(wrong))
        self.assertEqual(field['status'], 'UNRESOLVED_URL_BOUNDARY')
        self.assertEqual(field['literal_comparison'], 'DIFFERS_FROM_ALL_LITERAL_CANDIDATES')
        self.assertEqual(set(field['literal_url_candidates']), {ORIGIN, ORIGIN + '.'})
        matching = self.origin(self.audit(self.request()))
        self.assertEqual(matching['status'], 'UNRESOLVED_URL_BOUNDARY')
        self.assertEqual(matching['literal_comparison'], 'MATCHES_ONE_LITERAL_CANDIDATE')

    def test_query_fragment_and_same_domain_different_path_are_exact(self):
        source_origin = PUB + '?edition=2#origin'
        self.source(f'Publication URL: <{PUB}>\nOriginal source URL: <{source_origin}>')
        result = self.audit(self.request([{'id': 'item-1', 'publication_url': PUB, 'underlying_origin': PUB}]))
        self.assertEqual(self.origin(result)['status'], 'DIFFERS_FROM_SELECTED_DECLARATION')
        self.assertEqual(self.origin(result)['literal_url_candidates'], [source_origin])

    def test_explicit_self_publication_is_allowed(self):
        self.source(f'Publication identifier: <{PUB}>\nOriginal source: <{PUB}>')
        result = self.audit(self.request([{'id': 'item-1', 'publication_url': PUB, 'underlying_origin': PUB}]))
        self.assertEqual(self.origin(result)['status'], 'MATCHES_SELECTED_DECLARATION')
        self.assertFalse(result['semantic_relation_verified'])

    def test_missing_body_has_no_invented_origin(self):
        self.source('Subscription required. Article body unavailable.')
        result = self.audit(self.request([{'id': 'item-1', 'publication_url': None, 'underlying_origin': None}]))
        self.assertEqual(self.origin(result)['status'], 'UNRESOLVED_NO_DECLARATION')

    def test_partial_binding_inventory_and_unmatched_binding_visible(self):
        self.source()
        rows = [{'id': value, 'publication_url': PUB, 'underlying_origin': ORIGIN} for value in ('item-1', 'item-2', 'item-3')]
        bindings = [{'row_id': value, 'source_id': 'source-1', 'adapter': np.ADAPTER} for value in ('item-1', 'item-2', 'extra')]
        result = self.audit(self.request(rows, bindings))
        self.assertEqual(result['coverage']['rows_in_selected_collection'], 3)
        self.assertEqual(result['coverage']['fields_in_scope'], 6)
        self.assertFalse(result['coverage']['all_selected_rows_bound'])
        self.assertEqual(result['unmatched_binding_row_ids'], ['extra'])
        self.assertEqual(self.origin(result, 2)['status'], 'UNAUDITED_FIELD')

    def test_reordered_rows_use_ids_and_actual_field_pointers(self):
        self.source()
        rows = [{'id': 'other', 'publication_url': PUB, 'underlying_origin': ORIGIN},
                {'id': 'item-1', 'publication_url': PUB, 'underlying_origin': PUB}]
        result = self.audit(self.request(rows))
        self.assertEqual(self.origin(result, 0)['status'], 'UNAUDITED_FIELD')
        self.assertEqual(self.origin(result, 1)['pointer'], '/records/1/underlying_origin')
        self.assertEqual(self.origin(result, 1)['status'], 'DIFFERS_FROM_SELECTED_DECLARATION')

    def test_missing_duplicate_ids_bindings_and_missing_field_retained(self):
        self.source()
        rows = [{'id': 'item-1'}, {'id': 'item-1'}, {'publication_url': PUB}]
        result = self.audit(self.request(rows))
        self.assertEqual(len(result['records']), 3)
        self.assertTrue(all(row['diagnostic'] == 'MISSING_OR_DUPLICATE_FINAL_ROW_ID' for row in result['records']))
        request = self.request()
        request['bindings'].append(deepcopy(request['bindings'][0]))
        self.assertEqual(self.audit(request)['records'][0]['diagnostic'], 'DUPLICATE_SOURCE_BINDING')

    def test_no_source_role_or_expected_value_override_in_schema(self):
        self.source()
        request = self.request()
        request['bindings'][0]['expected_origin'] = PUB
        with self.assertRaisesRegex(ValueError, 'INVALID_BINDING_SCHEMA'):
            self.audit(request)

    def test_unmanifested_source_and_nontext_source_are_invalid(self):
        self.source('{}', format='json')
        request = self.request()
        self.assertEqual(self.audit(request)['records'][0]['diagnostic'], 'TEXT_OR_UTF8_BYTES_SOURCE_REQUIRED')
        request['bindings'][0]['source_id'] = 'caller-authored-unlisted'
        self.assertEqual(self.audit(request)['records'][0]['diagnostic'], 'SOURCE_NOT_IN_PINNED_INGRESS')

    def test_tampered_source_or_manifest_never_reuses_match(self):
        self.source()
        request = self.request()
        (self.sources / 'source-1.txt').write_text('tampered', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'INGRESS_SOURCE_HASH_MISMATCH'):
            self.audit(request)
        with self.assertRaisesRegex(ValueError, 'INGRESS_MANIFEST_HASH_MISMATCH'):
            np.audit(request, self.artifacts, self.sources, self.manifest, '0' * 64)

    def test_unsupported_encoding_explicit_invalid_row(self):
        self.source(b'\xff\xfe\x00')
        result = self.audit(self.request())
        self.assertEqual(result['records'][0]['binding_status'], 'INVALID')
        self.assertEqual(self.origin(result)['status'], 'INVALID_PROVENANCE')

    def test_invalid_field_type_and_pointer_do_not_pass(self):
        self.source()
        request = self.request([{'id': 'item-1', 'publication_url': PUB, 'underlying_origin': 9}])
        self.assertEqual(self.origin(self.audit(request))['status'], 'UNAUDITED_FIELD')
        request['final_ledger']['origin_pointer'] = '/missing'
        self.assertEqual(self.origin(self.audit(request))['status'], 'UNAUDITED_FIELD')
        request['final_ledger']['origin_pointer'] = '/bad~2escape'
        with self.assertRaisesRegex(ValueError, 'INVALID_POINTER_ESCAPE'):
            self.audit(request)

    def test_path_escape_and_pointer_collision_rejected(self):
        self.source()
        request = self.request()
        for path in ('../outside.json', 'C:\\outside.json', '/outside.json'):
            request['final_ledger']['path'] = path
            with self.assertRaises(ValueError):
                self.audit(request)
        request['final_ledger']['path'] = 'final.json'
        request['final_ledger']['origin_pointer'] = request['final_ledger']['publication_pointer']
        with self.assertRaisesRegex(ValueError, 'PUBLICATION_ORIGIN_POINTER_COLLISION'):
            self.audit(request)

    def test_declared_inputs_preserved_and_exact_spans_hash(self):
        text = f'Publication URL: {PUB}\r\nOriginal source: <{ORIGIN}>\r\n'
        self.source(text)
        request = self.request(); before = deepcopy(request)
        result = self.audit(request)
        self.assertEqual(request, before)
        self.assertEqual(result['declared_input'], before)
        observation = result['records'][0]['source']['observations']['declared_original_link'][0]
        self.assertEqual(text[observation['start']:observation['end']], observation['excerpt'])
        self.assertEqual(sha(observation['excerpt'].encode('utf-8')), observation['excerpt_sha256'])

    def test_duplicate_json_keys_nonfinite_and_empty_collection_rejected(self):
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":1e999}'):
            with self.assertRaises(ValueError):
                np.parse(raw)
        self.source()
        with self.assertRaisesRegex(ValueError, 'NONEMPTY_FINAL_ROW_COLLECTION_REQUIRED'):
            self.audit(self.request([]))

    def test_cli_audits_actual_file_and_refuses_overwriting_evidence(self):
        self.source()
        request = self.request([{'id': 'item-1', 'publication_url': PUB, 'underlying_origin': PUB}])
        request_path = self.root / 'request.json'; request_path.write_text(json.dumps(request), encoding='utf-8')
        output = self.root / 'audit.json'
        command = [sys.executable, '-B', str(SCRIPTS / 'news_provenance.py'), 'audit', str(request_path),
                   str(self.artifacts), str(output), '--source-root', str(self.sources),
                   '--ingress-manifest', str(self.manifest), '--ingress-sha256', sha(self.manifest.read_bytes())]
        run = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.origin(json.loads(output.read_text()))['status'], 'DIFFERS_FROM_SELECTED_DECLARATION')
        run_again = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(run_again.returncode, 0)
        command[6] = str(self.artifacts / 'final.json')
        before = (self.artifacts / 'final.json').read_bytes()
        rejected = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual((self.artifacts / 'final.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
