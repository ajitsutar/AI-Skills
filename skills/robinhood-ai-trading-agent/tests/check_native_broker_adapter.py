"""Optional offline check of a host's rh-call adapter after migration.

Usage: python tests/check_native_broker_adapter.py /absolute/path/to/rh-call
This is installation validation, never an execution prerequisite. The actual
adapter is loaded with a fictional auth module and denied network access.
No credentials, real accounts, broker calls, or research runtime are used.
The interception covers this inspected urllib-based adapter, not arbitrary code.
"""
from contextlib import ExitStack, redirect_stdout, redirect_stderr
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sys
import types
import unittest
from unittest.mock import patch
import urllib.request


ADAPTER = None


class Response:
    def __init__(self, data, status=200):
        self.stream = io.BytesIO(data)
        self.status = status
        self.headers = {'Mcp-Session-Id': 'offline-fictional-session'}

    def read(self, size=-1):
        return self.stream.read(size)

    def close(self):
        self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()


class NativeAdapterOfflineTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.posts = []
        self.auth_calls = 0
        self.authenticated_requests = []
        self.reject_auth = False
        self.mode = 'success'
        self.network_attempts = []
        auth = types.ModuleType('dynamic_credentials')
        auth.add_surrogate_to_request = self.fake_auth
        self.stack.enter_context(patch.dict(sys.modules, {'dynamic_credentials': auth}))
        self.stack.enter_context(patch.object(socket, 'socket', self.no_network))
        self.stack.enter_context(patch.object(socket, 'create_connection', self.no_network))
        self.stack.enter_context(patch.object(urllib.request, 'urlopen', self.fake_urlopen))
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith('AI_TRADING_')}
        self.stack.enter_context(patch.dict(os.environ, clean_env, clear=True))
        old_path = list(sys.path)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), old_path))
        loader = importlib.machinery.SourceFileLoader('offline_native_adapter', str(ADAPTER))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        self.adapter = importlib.util.module_from_spec(spec)
        loader.exec_module(self.adapter)
        self.arguments = {'account_number': 'FICTIONAL-ACCOUNT', 'symbol': 'DEMO',
                          'side': 'buy', 'type': 'market', 'dollar_amount': '133.33',
                          'time_in_force': 'gfd', 'market_hours': 'regular_hours',
                          'ref_id': '7d819dd6-b66e-46ee-b19d-fb41eedbe018'}

    def fake_auth(self, request, *args, **kwargs):
        self.auth_calls += 1
        if self.reject_auth:
            raise RuntimeError('FICTIONAL_NATIVE_AUTH_DENIAL')
        self.authenticated_requests.append(request)
        return request

    def no_network(self, *args, **kwargs):
        self.network_attempts.append('attempt')
        raise AssertionError('Live network is disabled in this test')

    def expected_response(self):
        if self.mode == 'broker_error':
            return {'jsonrpc': '2.0', 'id': 2,
                    'error': {'code': -32000, 'message': 'FICTIONAL_BROKER_ERROR'}}
        if self.mode == 'tool_error':
            return {'jsonrpc': '2.0', 'id': 2, 'result': {'isError': True,
                    'content': [{'type': 'text', 'text': 'FICTIONAL_TOOL_ERROR'}]}}
        if self.mode == 'empty_content':
            return {'jsonrpc': '2.0', 'id': 2, 'result': {'content': []}}
        return {'jsonrpc': '2.0', 'id': 2, 'result': {'content': [{'type': 'text',
                'text': '{"id":"FICTIONAL-ORDER","state":"queued"}'}]}}

    def fake_urlopen(self, request, *args, **kwargs):
        self.assertTrue(any(request is observed for observed in self.authenticated_requests),
                        'Every native request must pass through authentication')
        self.assertEqual(request.full_url, 'https://agent.robinhood.com/mcp/trading')
        payload = json.loads(request.data)
        self.posts.append(payload)
        method = payload.get('method')
        if method == 'initialize':
            result = {'jsonrpc': '2.0', 'id': 1, 'result': {
                'protocolVersion': '2025-03-26', 'capabilities': {'tools': {}},
                'serverInfo': {'name': 'offline-fixture', 'version': '1'}}}
            return Response(json.dumps(result).encode())
        if method == 'notifications/initialized':
            return Response(b'', 202)
        self.assertEqual(method, 'tools/call')
        if self.mode == 'empty_body':
            return Response(b'')
        return Response(json.dumps(self.expected_response()).encode())

    def call_adapter(self, arguments=None, tool='place_equity_order'):
        out, err = io.StringIO(), io.StringIO()
        payload = self.arguments if arguments is None else arguments
        with patch.object(sys, 'stdin', io.StringIO(json.dumps(payload))), \
                redirect_stdout(out), redirect_stderr(err):
            try:
                code = self.adapter.main(['rh-call', '--full-response', tool, '--stdin'])
            except SystemExit as exc:
                code = exc.code
        self.assertEqual(self.network_attempts, [])
        return code, out.getvalue()

    def tool_calls(self):
        return [p for p in self.posts if p.get('method') == 'tools/call']

    def assert_exact_single_call(self, tool, arguments):
        self.assertEqual(len(self.tool_calls()), 1)
        self.assertEqual(self.tool_calls()[0]['params'], {'name': tool, 'arguments': arguments})
        self.assertGreater(self.auth_calls, 0)

    def test_dollar_market_without_research_runtime(self):
        code, out = self.call_adapter()
        self.assertEqual(code, 0)
        self.assert_exact_single_call('place_equity_order', self.arguments)
        self.assertEqual(json.loads(out), self.expected_response())

    def test_fractional_quantity_unmodified(self):
        arguments = dict(self.arguments)
        del arguments['dollar_amount']
        arguments['quantity'] = '0.000123'
        code, out = self.call_adapter(arguments)
        self.assertEqual(code, 0)
        self.assert_exact_single_call('place_equity_order', arguments)

    def test_cancel_has_no_skill_allowlist(self):
        arguments = {'account_number': 'FICTIONAL-ACCOUNT', 'order_id': 'FICTIONAL-ORDER'}
        code, out = self.call_adapter(arguments, 'cancel_equity_order')
        self.assertEqual(code, 0)
        self.assert_exact_single_call('cancel_equity_order', arguments)

    def test_unsupported_tool_is_decided_by_native_stub(self):
        self.mode = 'broker_error'
        code, out = self.call_adapter({'fixture': True}, 'fictional_native_operation')
        self.assert_exact_single_call('fictional_native_operation', {'fixture': True})
        self.assertEqual(json.loads(out), self.expected_response())

    def test_native_auth_remains_required(self):
        self.reject_auth = True
        try:
            code, out = self.call_adapter()
        except RuntimeError as exc:
            self.assertEqual(str(exc), 'FICTIONAL_NATIVE_AUTH_DENIAL')
        else:
            self.assertNotEqual(code, 0)
        self.assertGreater(self.auth_calls, 0)
        self.assertEqual(self.posts, [])

    def test_broker_error_preserved_without_retry(self):
        self.mode = 'broker_error'
        code, out = self.call_adapter()
        self.assert_exact_single_call('place_equity_order', self.arguments)
        self.assertEqual(json.loads(out), self.expected_response())

    def test_tool_error_preserved_without_retry(self):
        self.mode = 'tool_error'
        code, out = self.call_adapter()
        self.assert_exact_single_call('place_equity_order', self.arguments)
        self.assertEqual(json.loads(out), self.expected_response())

    def test_empty_content_stays_empty_without_fabricated_fill(self):
        self.mode = 'empty_content'
        code, out = self.call_adapter()
        self.assert_exact_single_call('place_equity_order', self.arguments)
        self.assertEqual(json.loads(out), self.expected_response())

    def test_empty_transport_body_reports_error_without_retry(self):
        self.mode = 'empty_body'
        code, out = self.call_adapter()
        self.assert_exact_single_call('place_equity_order', self.arguments)
        self.assertNotEqual(code, 0)
        self.assertNotIn('FICTIONAL-ORDER', out)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: check_native_broker_adapter.py /absolute/path/to/rh-call')
    ADAPTER = Path(sys.argv[1]).resolve(strict=True)
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(NativeAdapterOfflineTests))
    raise SystemExit(0 if result.wasSuccessful() else 1)
