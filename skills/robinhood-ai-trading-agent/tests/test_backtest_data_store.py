"""Portable storage/recovery behavior using fictional local streams, no network."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import research_data_store as data
import public_research_fetch as fetch


def request(symbol='GOOG', **changes):
    return {'provider': 'fictional', 'security_id': 'fictional:alphabet:' + symbol,
        'provider_symbol': symbol, 'start': '2021-01-01', 'end': '2021-01-05',
        'adjustment': 'split_and_dividend', 'schema_version': '1', 'parser_version': '1',
        'fields': ['Close', 'Volume'], 'source_role': 'native_response', 'vintage': 'run-1', **changes}


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = data.Store(self.root / 'data', 'fictional-owner', create=True, min_free_bytes=0)

    def tearDown(self):
        self.temp.cleanup()

    def capture(self, symbol='GOOG', payload=b'fictional bytes', **changes):
        return self.store.capture(request(symbol, **changes), lambda: iter([payload]),
                                  retrieved_at='2026-10-29T00:00:00+00:00', revision='revision-1')

    def test_completed_capture_resumes_without_network_after_parser_failure(self):
        producer = Mock(return_value=iter([b'not valid json but complete source response']))
        record = self.store.capture(request(), producer)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(self.store.read_bytes(record))
        recovered = self.store.capture(request(), producer, resume=True)
        self.assertEqual(record, recovered)
        producer.assert_called_once()
        with self.assertRaises(FileExistsError):
            self.store.capture(request(), producer)

    def test_interrupted_transport_retains_attempt_not_success(self):
        def broken():
            yield b'first bytes'
            raise TimeoutError('fictional transport interruption')
        with self.assertRaises(TimeoutError): self.store.capture(request(), broken)
        self.assertEqual(self.store.records(), [])
        attempts = list(self.store.path('attempts').glob('*.json'))
        self.assertEqual(json.loads(attempts[0].read_text())['status'], 'INCOMPLETE_OR_UNCOMMITTED')
        self.assertEqual(len(list(self.store.path('attempts').glob('*.gz'))), 1)
        record = self.capture()
        self.assertEqual(self.store.read_bytes(record), b'fictional bytes')

    def test_disk_reserve_before_dispatch_and_midstream(self):
        producer = Mock(return_value=iter([b'x']))
        with patch.object(data.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=0)):
            with self.assertRaisesRegex(OSError, 'RESERVE'): self.store.capture(request(), producer)
        producer.assert_not_called()
        calls = iter([10 * data.CHUNK, 10 * data.CHUNK, 0])
        with patch.object(data.shutil, 'disk_usage', side_effect=lambda _: types.SimpleNamespace(free=next(calls))):
            with self.assertRaisesRegex(OSError, 'RESERVE'):
                self.store.capture(request(), lambda: iter([b'a', b'b']))
        self.assertEqual(self.store.records(), [])

    def test_byte_limit_and_incomplete_capture_not_committed(self):
        self.store.max_capture_bytes = 3
        with self.assertRaisesRegex(OSError, 'BYTE_LIMIT'):
            self.store.capture(request(), lambda: iter([b'1234']))
        self.assertEqual(self.store.records(), [])

    def test_corruption_cannot_resume_or_reuse_incremental_seal(self):
        record = self.capture(payload=b'a' * (2 * data.CHUNK + 7))
        seal = self.store.verify()
        again = self.store.verify(seal)
        self.assertEqual(again['records'][0]['verification_mode'], 'COMPRESSED_BYTES_REHASHED_PRIOR_RAW_SEAL_REUSED')
        obj = self.store.path(record['object_path'])
        blob = obj.read_bytes(); obj.write_bytes(blob[:-1] + bytes([blob[-1] ^ 1]))
        with self.assertRaisesRegex(ValueError, 'OBJECT_MISMATCH'): self.store.verify(seal)
        with self.assertRaises(ValueError): self.store.capture(request(), Mock(), resume=True)

    def test_deduplicates_content_not_share_class_or_source_vintage(self):
        a, b = self.capture('GOOG'), self.capture('GOOGL')
        c = self.capture('GOOG', vintage='run-2')
        self.assertNotEqual(a['request_id'], b['request_id'])
        self.assertNotEqual(a['request_id'], c['request_id'])
        self.assertEqual(a['object_path'], b['object_path'])
        self.assertEqual(len(self.store.records()), 3)
        self.assertEqual(len(list(self.store.path('objects').glob('*.gz'))), 1)

    def test_explicit_reuse_requires_exact_revision_and_entire_history_check(self):
        record = self.capture()
        new = request(vintage='new-run', decision_at='2026-10-30T00:00:00Z')
        evidence = self.store.path('attempts/fictional-revision-index.txt'); evidence.write_text('fictional full index')
        check = {'request_id': record['request_id'], 'new_request_sha256': data.digest(new),
            'evidence_path': 'attempts/fictional-revision-index.txt', 'evidence_sha256': data.file_sha(evidence),
            'checked_at': datetime.now(timezone.utc).isoformat(), 'revision': 'revision-1',
            'scope': 'entire_retained_representation'}
        self.assertEqual(self.store.reuse_decision(record['request_id'], new, check=check)['decision'], 'FETCH_FRESH')
        self.assertEqual(self.store.reuse_decision(record['request_id'], new, partial_fetch=True, check=check)['decision'], 'REUSE')
        for field, value in [('revision', 'split-or-correction-2'), ('scope', 'new-tail-only')]:
            self.assertEqual(self.store.reuse_decision(record['request_id'], new, partial_fetch=True,
                check={**check, field: value})['decision'], 'FETCH_FRESH')
        self.assertEqual(self.store.reuse_decision(record['request_id'], new, partial_fetch=True,
            check={**check, 'checked_at': '2026-10-29T12:00:00Z'})['decision'], 'FETCH_FRESH')
        for changes in ({'parser_version': '2'}, {'adjustment': 'unadjusted'}, {'provider_symbol': 'GOOGL'}):
            changed = {**new, **changes}
            self.assertEqual(self.store.reuse_decision(record['request_id'], changed, partial_fetch=True,
                check={**check, 'new_request_sha256': data.digest(changed)})['decision'], 'FETCH_FRESH')

    def test_verified_scope_narrowing_preserves_former_member_benchmark_and_unrelated_files(self):
        current = self.capture('CURRENT', b'current')
        former = self.capture('FORMER', b'former', membership='historical_sp500')
        benchmark = self.capture('SPY', b'benchmark', role='benchmark')
        other = self.capture('OUTSIDE', b'outside')
        unrelated = self.store.path('SKILL.md'); unrelated.write_text('keep unrelated skill file')
        keep = [r['request_id'] for r in (current, former, benchmark)]
        scoped = data.scope_keys(self.store.records(), ['fictional:alphabet:CURRENT'],
            former_member_ids=['fictional:alphabet:FORMER'], benchmark_ids=['fictional:alphabet:SPY', 'MISSING'])
        self.assertEqual(set(scoped['request_ids']), set(keep))
        self.assertEqual(scoped['missing_security_ids'], ['MISSING'])
        proof = self.store.archive('archives/scoped.zip', keep)
        self.assertEqual(set(proof['record_ids']), set(keep))
        preview = self.store.prune_to(keep, 'archives/scoped.zip')
        self.assertEqual(preview['removed_request_ids'], [])
        result = self.store.prune_to(keep, 'archives/scoped.zip', delete=True)
        self.assertEqual(result['removed_request_ids'], [other['request_id']])
        self.assertEqual({r['request_id'] for r in self.store.records()}, set(keep))
        self.assertEqual(unrelated.read_text(), 'keep unrelated skill file')
        restored = self.root / 'different-location'
        data.restore_archive(self.store.path('archives/scoped.zip'), restored, 'fictional-owner')
        moved = data.Store(restored, 'fictional-owner', min_free_bytes=0)
        self.assertEqual(len(moved.verify()['records']), 3)
        with self.assertRaisesRegex(ValueError, 'RESTORE_BYTE_LIMIT'):
            data.restore_archive(self.store.path('archives/scoped.zip'), self.root / 'tiny-restore',
                                 'fictional-owner', max_restore_bytes=1)

    def test_archive_corruption_stops_before_any_prune(self):
        a, b = self.capture('A', b'a'), self.capture('B', b'b')
        self.store.archive('archives/scoped.zip', [a['request_id']])
        archive = self.store.path('archives/scoped.zip')
        archive.write_bytes(b'broken')
        with self.assertRaises(Exception): self.store.prune_to([a['request_id']], 'archives/scoped.zip', delete=True)
        self.assertEqual(len(self.store.records()), 2)

    def test_bound_ancestor_paths_and_ownership(self):
        for bad in ('../other', 'objects/../../other', 'C:/unrelated', '/absolute', 'objects/a:stream'):
            with self.assertRaises(ValueError): self.store.path(bad)
        self.assertEqual(self.store.path('a/b/c').relative_to(self.store.root).as_posix(), 'a/b/c')
        with self.assertRaisesRegex(ValueError, 'OWNERSHIP'): data.Store(self.store.root, 'different-owner')
        with self.assertRaises(FileExistsError): data.Store(self.store.root, 'fictional-owner', create=True)

    def test_forged_owned_object_path_cannot_delete_unrelated_file(self):
        a, b = self.capture('A', b'a'), self.capture('B', b'b')
        self.store.archive('archives/scoped.zip', [a['request_id']])
        unrelated = self.store.path('SKILL.md'); unrelated.write_text('keep')
        b['object_path'] = 'SKILL.md'
        self.store.path('records/' + b['request_id'] + '.json').write_text(json.dumps(b))
        with self.assertRaisesRegex(ValueError, 'OWNED_OBJECT'):
            self.store.prune_to([a['request_id']], 'archives/scoped.zip', delete=True)
        self.assertEqual(unrelated.read_text(), 'keep')

    def test_capture_and_maintenance_exclusion_and_concurrent_dedup(self):
        with self.store.lock('maintenance'):
            with self.assertRaisesRegex(ValueError, 'ACTIVE'): self.capture()
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = list(pool.map(lambda s: self.capture(s, b'same bytes'), ['A', 'B']))
        self.assertEqual(a['object_path'], b['object_path'])
        self.assertEqual(len(self.store.verify()['records']), 2)

    def test_explicit_global_capture_bound_and_same_request_exclusion(self):
        self.store.max_active_captures = 1
        with self.store.lock('first'):
            with self.assertRaisesRegex(ValueError, 'CAPTURE_LIMIT'):
                self.capture('second')
        self.store.max_active_captures = 2
        with self.store.lock(data.validate_request(request())):
            with self.assertRaises(FileExistsError): self.capture()

    def test_coverage_uses_filing_availability_not_period_end_or_query_alias(self):
        observations = [{'artifact_id': 'not-yet-filed', 'security_id': 'GOOG', 'provider_symbol': 'GOOG',
                         'usable_sessions': ['2021-01-04'], 'period_end': '2020-12-31',
                         'available_at': '2021-02-01T21:00:00Z'},
                        {'artifact_id': 'unknown-publication', 'security_id': 'GOOG',
                         'provider_symbol': 'GOOG', 'period_end': '2020-09-30'}]
        result = data.coverage(['GOOG', 'GOOGL'], observations,
                              ['2021-01-04', '2021-01-05'], '2021-01-15T21:00:00Z')
        self.assertEqual(result['rows'][0]['available_at_decision_artifact_ids'], [])
        self.assertEqual(result['rows'][0]['availability_unknown_artifact_ids'], ['unknown-publication'])
        self.assertEqual(result['rows'][1]['artifact_count'], 0)
        self.assertEqual(result['rows'][0]['missing_sessions'], ['2021-01-05'])
        self.assertFalse(result['point_in_time_certified'])
        observations[0]['available_at'] = '2021-01-01T00:00:00Z'
        observations[0]['published_at'] = '2021-02-01T21:00:00Z'
        again = data.coverage(['GOOG'], observations, decision_at='2021-01-15T21:00:00Z')
        self.assertEqual(again['rows'][0]['available_at_decision_artifact_ids'], [])
        self.assertEqual(again['rows'][0]['status'], 'NOT_ASSESSED')
        financial_only = data.coverage(['GOOG'], [observations[1]])
        self.assertEqual(financial_only['rows'][0]['usable_session_count'], 0)
        self.assertEqual(financial_only['rows'][0]['status'], 'NOT_ASSESSED')
        required = data.coverage(['GOOG'], [observations[1]], ['2021-01-04'])
        self.assertEqual(required['rows'][0]['status'], 'GAP')

    @unittest.skipUnless(importlib.util.find_spec('pyarrow'), 'Optional pyarrow unavailable')
    def test_actual_zstd_parquet_bounded_roundtrip_schema_and_corruption(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        schema = pa.schema([('security_id', pa.string()), ('value', pa.float64())])
        batches = [pa.record_batch([['GOOG', 'GOOGL'], [1., 2.]], schema=schema),
                   pa.record_batch([['SPY'], [3.]], schema=schema)]
        path = self.root / 'normalized.parquet'
        receipt = data.write_parquet_batches(path, iter(batches), schema)
        self.assertEqual(receipt['compression'], 'zstd')
        self.assertEqual(pq.ParquetFile(path).metadata.row_group(0).column(0).compression, 'ZSTD')
        read = list(data.read_parquet_batches(path, batch_size=1))
        self.assertEqual([r.column(0)[0].as_py() for r in read], ['GOOG', 'GOOGL', 'SPY'])
        with self.assertRaisesRegex(ValueError, 'BATCH_BYTE_LIMIT'):
            list(data.read_parquet_batches(path, max_batch_bytes=1))
        bad = self.root / 'bad.parquet'
        with self.assertRaisesRegex(ValueError, 'SCHEMA_CHANGED'):
            data.write_parquet_batches(bad, [pa.record_batch([[1]], names=['wrong'])], schema)
        self.assertFalse(bad.exists())
        changed_metadata = batches[0].replace_schema_metadata({b'currency': b'EUR'})
        with self.assertRaisesRegex(ValueError, 'SCHEMA_CHANGED'):
            data.write_parquet_batches(self.root / 'changed-metadata.parquet', [changed_metadata], schema)
        with self.assertRaisesRegex(ValueError, 'BATCH_BYTE_LIMIT'):
            data.write_parquet_batches(self.root / 'too-large.parquet', batches, schema, max_batch_bytes=1)
        with patch.object(data.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=0)):
            with self.assertRaisesRegex(OSError, 'STORAGE_RESERVE'):
                data.write_parquet_batches(self.root / 'no-space.parquet', batches, schema)
        path.write_bytes(b'not parquet')
        with self.assertRaises(Exception): list(data.read_parquet_batches(path))


class ProviderCheckpointTests(unittest.TestCase):
    def test_each_successful_component_survives_row_checkpoint_failure(self):
        identity = {'symbol': 'DEMO', 'issuer_id': 'fictional:demo'}
        old = {**identity, 'info': {}, 'errors': []}
        for key in ('income', 'balance', 'cashflow', 'history'):
            old[key] = {'index': ['demo'], 'columns': ['demo'], 'data': [[1]]}
        ticker = Mock(); ticker.get_info.return_value = {'sector': 'Industrials', 'secret_extra_source_field': 42}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); one = root / 'first'; two = root / 'retry'
            for p in (one, two): (p / 'raw').mkdir(parents=True)
            store = data.Store(root / 'store', 'frozen-run', create=True, min_free_bytes=0)
            with patch.dict(sys.modules, {'yfinance': types.SimpleNamespace(Ticker=Mock(return_value=ticker))}), \
                 patch.object(fetch, 'request_call', side_effect=lambda call: call()):
                with patch.object(fetch, 'save', side_effect=OSError('later row checkpoint failed')):
                    with self.assertRaises(OSError):
                        fetch.fetch_row(identity, [], one, old, component_store=store, contract_vintage='same-run')
                result = fetch.fetch_row(identity, [], two, old, component_store=store, contract_vintage='same-run')
            ticker.get_info.assert_called_once()
            self.assertEqual(result['component_acquisition']['info']['acquisition'], 'same_contract_component_resume')
            record = store.records()[0]
            self.assertEqual(json.loads(store.read_bytes(record))['secret_extra_source_field'], 42)
            self.assertEqual(result['component_retrieved_at']['info'], record['retrieved_at'])


if __name__ == '__main__': unittest.main()
