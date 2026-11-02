"""Offline protocol and bounded read-only collection regressions; no broker access."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from mcp_response import classify_response, collect_readonly_pages, decode_rpc_body


def page(items=None, cursor=None, more=False):
    return {"content": [], "structuredContent": {
        "orders": [] if items is None else items, "next": cursor, "more": more,
    }}


def contract():
    return {
        "source": "connected_official_mcp_schema_observation", "operation": "orders",
        "tool_name": "get_demo_orders", "read_only": True, "evidence_ref": "fixture-schema",
        "scopes": {"account_alias": "DEMO", "account_verified": True, "statuses": "all",
                   "time": {"kind": "all"}, "filters": {}, "evidence_ref": "fixture-scope"},
        "payload_source": "structuredContent", "items_pointer": "/orders",
        "pagination": {"mode": "cursor", "next_cursor_pointer": "/next", "has_more_pointer": "/more",
                       "terminal_cursor": None, "evidence_ref": "fixture-pagination"},
    }


class ResponseTests(unittest.TestCase):
    def test_empty_never_means_success_or_rejection(self):
        for envelope in ({}, {"content": []}, {"structuredContent": {}},
                         {"jsonrpc": "2.0", "id": 1, "result": {}}):
            with self.subTest(envelope=envelope):
                result = classify_response(envelope)
                self.assertEqual(result["classification"], "empty")
                self.assertEqual(result["broker_outcome"], "UNKNOWN")

    def test_complete_envelope_preserved_and_detached(self):
        original = {"jsonrpc": "2.0", "id": 12, "result": {
            "content": [{"type": "text", "text": "No status available"}],
            "structuredContent": {"data": {}}, "isError": False, "_meta": {"trace": "fixture"}}}
        expected = deepcopy(original)
        result = classify_response(original)
        original["result"]["_meta"]["trace"] = "changed"
        self.assertEqual(result["envelope"], expected)
        self.assertEqual(result["classification"], "result_received")
        self.assertEqual(result["broker_outcome"], "UNKNOWN")

    def test_protocol_and_tool_errors_distinct_without_outcome(self):
        for envelope, expected in (
            ({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": "Internal"}}, "protocol_error"),
            ({"content": [{"type": "text", "text": "Failed"}], "isError": True}, "tool_error"),
        ):
            result = classify_response(envelope)
            self.assertEqual(result["classification"], expected)
            self.assertEqual(result["broker_outcome"], "UNKNOWN")

    def test_text_only_json_candidate_not_terminal_normalization(self):
        payload = {"state": "filled", "filled": "3.7878"}
        result = classify_response({"content": [{"type": "text", "text": json.dumps(payload)}]})
        self.assertEqual(result["candidate_payloads"], [{"source": "content[0].text", "payload": payload}])
        self.assertEqual(result["broker_outcome"], "UNKNOWN")

    def test_conflicting_text_and_structured_is_not_silently_selected(self):
        result = classify_response({"content": [{"type": "text", "text": '{"state":"filled"}'}],
                                    "structuredContent": {"state": "open"}})
        self.assertTrue(result["conflicting_payloads"])
        self.assertEqual(result["classification"], "malformed")
        self.assertEqual(len(result["candidate_payloads"]), 2)

    def test_equivalent_json_candidates_are_not_conflicts(self):
        result = classify_response({"content": [{"type": "text", "text": '{"b":2,"a":1}'}],
                                    "structuredContent": {"a": 1, "b": 2}})
        self.assertFalse(result["conflicting_payloads"])
        self.assertEqual(result["classification"], "result_received")

    def test_error_flag_does_not_get_overridden_by_success_payload(self):
        result = classify_response({"content": [], "structuredContent": {"state": "filled"}, "isError": True})
        self.assertEqual(result["classification"], "tool_error")
        self.assertEqual(result["broker_outcome"], "UNKNOWN")

    def test_async_is_unsupported_even_with_result_text(self):
        result = classify_response({"task": {"taskId": "demo"}, "content": [{"type": "text", "text": "Queued"}]})
        self.assertEqual(result["classification"], "unsupported_async")

    def test_malformed_shapes_and_flags(self):
        for envelope in (None, "{}", [], {"unexpected": "data"}, {"isError": "false", "content": []},
                         {"structuredContent": []}, {"content": {}}, {"content": [None]},
                         {"content": [{"type": "text", "text": 4}]},
                         {"content": [{"type": "unknown"}]},
                         {"jsonrpc": "2.0", "id": True, "result": {}},
                         {"jsonrpc": "2.0", "id": 1, "result": {}, "error": {}},
                         {"jsonrpc": "2.0", "id": 1, "error": {"code": True, "message": "x"}},
                         {"content": [], "structuredContent": {"n": float("nan")}}):
            with self.subTest(envelope=envelope):
                self.assertEqual(classify_response(envelope)["classification"], "malformed")

    def test_non_json_numeric_text_is_not_candidate(self):
        result = classify_response({"content": [{"type": "text", "text": '{"n":NaN}'}]})
        self.assertEqual(result["candidate_payloads"], [])
        self.assertEqual(result["broker_outcome"], "UNKNOWN")


class DecoderTests(unittest.TestCase):
    def test_plain_json_preserves_entire_matching_envelope(self):
        response = {"jsonrpc": "2.0", "id": 7, "result": {"content": [], "isError": False}}
        self.assertEqual(decode_rpc_body(json.dumps(response), 7), response)

    def test_notification_and_heartbeats_before_result(self):
        response = {"jsonrpc": "2.0", "id": 7, "result": {"content": []}}
        body = (': heartbeat\n\nevent: ping\ndata: ping\n\n'
                'event: message\ndata: {"jsonrpc":"2.0","method":"notifications/progress","params":{}}\n\n'
                'event: message\ndata: ' + json.dumps(response) + '\n\n')
        self.assertEqual(decode_rpc_body(body, 7), response)

    def test_multiline_sse_data_and_crlf(self):
        body = ('event: message\r\ndata: {"jsonrpc":"2.0",\r\n'
                'data: "id":"7",\r\ndata: "result":{"content":[]}}\r\n\r\n')
        self.assertEqual(decode_rpc_body(body, "7")["result"], {"content": []})

    def test_unicode_separators_inside_json_are_not_sse_line_breaks(self):
        response = {"jsonrpc": "2.0", "id": 7, "result": {"content": [{"type": "text", "text": "a\u2028b\u0085c"}]}}
        body = 'data: ' + json.dumps(response, ensure_ascii=False) + '\n\n'
        self.assertEqual(decode_rpc_body(body, 7), response)

    def test_wrong_ids_and_numeric_string_mismatch_rejected(self):
        for identifier in (8, "7", True, None):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                decode_rpc_body(json.dumps({"jsonrpc": "2.0", "id": identifier, "result": {}}), 7)

    def test_unrelated_response_does_not_hide_matching_response(self):
        body = ('data: {"jsonrpc":"2.0","id":2,"result":{}}\n\n'
                'data: {"jsonrpc":"2.0","id":7,"result":{"content":[]}}\n\n')
        self.assertEqual(decode_rpc_body(body, 7)["id"], 7)

    def test_duplicate_matching_messages_rejected_even_if_identical(self):
        message = 'data: {"jsonrpc":"2.0","id":7,"result":{}}\n\n'
        with self.assertRaises(ValueError):
            decode_rpc_body(message + message, 7)

    def test_protocol_error_returned_without_unwrapping(self):
        response = {"jsonrpc": "2.0", "id": 7, "error": {"code": -32603, "message": "Failure"}}
        self.assertEqual(decode_rpc_body('data: ' + json.dumps(response) + '\n\n', 7), response)

    def test_malformed_or_truncated_events_fail_even_after_match(self):
        message = 'data: {"jsonrpc":"2.0","id":7,"result":{}}\n\n'
        for suffix in ('data: {\n\n', 'data: {"jsonrpc":"2.0","method":"notifications/progress"}\n',
                       'data: {"jsonrpc":"2.0","id":7,"id":8,"result":{}}\n\n'):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                decode_rpc_body(message + suffix, 7)

    def test_only_notifications_and_invalid_request_ids_fail(self):
        with self.assertRaises(ValueError):
            decode_rpc_body('data: {"jsonrpc":"2.0","method":"notifications/progress"}\n\n', 7)
        for identifier in (True, None, 7.0):
            with self.assertRaises(ValueError):
                decode_rpc_body('{"jsonrpc":"2.0","id":7,"result":{}}', identifier)


class PageTests(unittest.TestCase):
    def test_two_pages_retained_in_order(self):
        calls = []
        def read(cursor):
            calls.append(cursor)
            return page([{"id": "a"}], "p2", True) if cursor is None else page([{"id": "b"}])
        result = collect_readonly_pages(read, contract())
        self.assertEqual(calls, [None, "p2"])
        self.assertEqual(result["items"], [{"id": "a"}, {"id": "b"}])
        self.assertTrue(result["complete"])
        self.assertTrue(result["coverage_complete"])
        self.assertEqual(result["broker_outcome"], "UNKNOWN")

    def test_empty_complete_history_still_unknown(self):
        result = collect_readonly_pages(lambda cursor: page(), contract())
        self.assertTrue(result["complete"])
        self.assertEqual(result["broker_outcome"], "UNKNOWN")
        self.assertIn("NO_MATCH_IS_NOT_PROOF_OF_REJECTION_OR_NON_SUBMISSION", result["reasons"])

    def test_write_or_undeclared_scopes_never_call_callback(self):
        variants = []
        for field in ("source", "read_only", "scopes", "evidence_ref"):
            value = contract()
            del value[field]
            variants.append(value)
        for field in ("account_alias", "account_verified", "statuses", "time", "filters", "evidence_ref"):
            value = contract()
            del value["scopes"][field]
            variants.append(value)
        value = contract()
        value["operation"] = "submit"
        variants.append(value)
        for value in variants:
            with self.subTest(value=value):
                calls = []
                result = collect_readonly_pages(lambda cursor: calls.append(cursor), value)
                self.assertFalse(result["complete"])
                self.assertEqual(calls, [])

    def test_repeated_cursor_incomplete_and_bounded(self):
        calls = []
        def read(cursor):
            calls.append(cursor)
            return page([{"id": len(calls)}], "repeat", True)
        result = collect_readonly_pages(read, contract())
        self.assertEqual(len(calls), 2)
        self.assertFalse(result["complete"])
        self.assertIn("MISSING_OR_REPEATED_CURSOR", result["reasons"])

    def test_missing_or_contradictory_metadata_incomplete(self):
        variants = [page(cursor=None, more=True), page(cursor="next", more=False), page(more="false")]
        missing = page()
        del missing["structuredContent"]["next"]
        variants.append(missing)
        for value in variants:
            with self.subTest(value=value):
                self.assertFalse(collect_readonly_pages(lambda cursor: value, contract())["complete"])

    def test_page_and_item_limits_never_claim_complete(self):
        result = collect_readonly_pages(lambda cursor: page([{"id": "a"}], "next", True), contract(), max_pages=1)
        self.assertIn("PAGE_LIMIT_REACHED", result["reasons"])
        self.assertFalse(result["complete"])
        result = collect_readonly_pages(lambda cursor: page([{"id": "a"}, {"id": "b"}]), contract(), max_items=1)
        self.assertEqual(len(result["items"]), 1)
        self.assertIn("ITEM_LIMIT_REACHED", result["reasons"])
        self.assertFalse(result["complete"])

    def test_errors_stop_without_retry_or_echoing_private_error(self):
        calls = []
        def read(cursor):
            calls.append(cursor)
            raise RuntimeError("PRIVATE-ROUTING")
        result = collect_readonly_pages(read, contract())
        self.assertEqual(calls, [None])
        self.assertFalse(result["complete"])
        self.assertNotIn("PRIVATE-ROUTING", json.dumps(result))

    def test_tool_error_and_conflict_stop_collection(self):
        for response in ({"content": [], "isError": True},
                         {"content": [{"type": "text", "text": "{}"}], "structuredContent": {"orders": []}}):
            self.assertFalse(collect_readonly_pages(lambda cursor: response, contract())["complete"])

    def test_filtered_history_explicitly_incomplete_coverage(self):
        spec = contract()
        spec["scopes"]["statuses"] = ["open"]
        result = collect_readonly_pages(lambda cursor: page(), spec)
        self.assertTrue(result["complete"])
        self.assertFalse(result["coverage_complete"])

    def test_text_source_requires_explicit_mapping(self):
        payload = page()["structuredContent"]
        response = {"content": [{"type": "text", "text": json.dumps(payload)}]}
        self.assertFalse(collect_readonly_pages(lambda cursor: response, contract())["complete"])
        spec = contract()
        spec["payload_source"] = "content[0].text"
        self.assertTrue(collect_readonly_pages(lambda cursor: response, spec)["complete"])

    def test_single_page_requires_positive_completeness_evidence(self):
        spec = contract()
        spec["pagination"] = {"mode": "single_page", "complete_pointer": "/complete", "evidence_ref": "fixture"}
        response = page()
        self.assertFalse(collect_readonly_pages(lambda cursor: response, spec)["complete"])
        response["structuredContent"]["complete"] = True
        self.assertTrue(collect_readonly_pages(lambda cursor: response, spec)["complete"])

    def test_invalid_limits_or_time_window_do_not_read(self):
        for limits in ({"max_pages": 0}, {"max_items": True}, {"max_pages": 1001}):
            calls = []
            result = collect_readonly_pages(lambda cursor: calls.append(cursor), contract(), **limits)
            self.assertFalse(result["complete"])
            self.assertEqual(calls, [])
        for start, end in (("2026-10-12", "2026-10-13"), ("2026-10-13T00:00:00Z", "2026-10-12T00:00:00Z")):
            spec = contract()
            spec["scopes"]["time"] = {"kind": "window", "start": start, "end": end}
            calls = []
            result = collect_readonly_pages(lambda cursor: calls.append(cursor), spec)
            self.assertFalse(result["complete"])
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
