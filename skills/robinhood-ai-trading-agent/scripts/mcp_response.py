"""Conservative MCP evidence handling; no trading, state transitions, or credentials.

The host must retain this module's returned envelopes privately: broker responses
can contain account and order identifiers. A valid MCP result is transport evidence,
never proof that an order was rejected, accepted, or filled. The injected page
reader is a trusted read-only host boundary, not an arbitrary command runner.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import math
import re


READ_OPERATIONS = frozenset({"orders", "fills", "positions"})


def _json_value(value):
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_value(item) for key, item in value.items())
    return False


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _reject_constant(value):
    raise ValueError("Non-JSON numeric constant")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _decode_json(text):
    value = json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    if not _json_value(value):
        raise ValueError("Non-finite or unsupported JSON value")
    return value


def decode_rpc_body(body, expected_id):
    """Select one exact-ID JSON-RPC response from a JSON body or complete SSE.

    Preserve the original body privately in the host before calling this helper.
    Notification and heartbeat events are ignored; malformed or truncated events,
    duplicate matching messages, and missing matches fail closed. No result is
    unwrapped and no transport, retry, authentication, or broker action occurs.
    """
    if not isinstance(body, str) or type(expected_id) not in (str, int):
        raise ValueError("Body must be text and request ID must be string or integer")
    text = body.lstrip("\ufeff").strip()
    if not text:
        raise ValueError("Empty JSON-RPC response body")
    messages = []
    if text.startswith(("{", "[")):
        messages.append(_decode_json(text))
    else:
        data, event_name = [], ""
        pending = False
        # SSE recognizes only CR/LF line endings. Unicode separators inside JSON
        # strings must survive. A final data newline is not a blank terminator.
        stream = body.lstrip("\ufeff")
        lines = re.split(r"\r\n|\r|\n", stream)
        if stream.endswith(("\r", "\n")):
            lines.pop()
        for line in lines:
            if not line:
                if data:
                    joined = "\n".join(data)
                    if not (event_name in {"ping", "heartbeat"} and joined.strip() in {"", "ping", "heartbeat"}):
                        messages.append(_decode_json(joined))
                data, event_name, pending = [], "", False
                continue
            if line.startswith(":"):
                continue
            field, separator, value = line.partition(":")
            if separator and value.startswith(" "):
                value = value[1:]
            if field == "data":
                data.append(value)
                pending = True
            elif field == "event":
                event_name = value
                pending = True
            elif field in {"id", "retry"}:
                pending = True
            # Unrecognized SSE fields are ignored by the event stream protocol.
        if pending or data:
            raise ValueError("Truncated SSE event")
    matches = []
    for message in messages:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise ValueError("Invalid JSON-RPC event")
        if "method" in message:
            if (not isinstance(message["method"], str) or not message["method"]
                    or "result" in message or "error" in message or "id" in message):
                raise ValueError("Unsupported server request or malformed notification")
            continue
        if ("id" not in message or type(message["id"]) not in (str, int, type(None))
                or ("result" in message) == ("error" in message)):
            raise ValueError("Invalid JSON-RPC response event")
        if "error" in message:
            error = message["error"]
            if (not isinstance(error, dict) or type(error.get("code")) is not int
                    or not isinstance(error.get("message"), str)):
                raise ValueError("Invalid JSON-RPC error event")
        if type(message["id"]) is type(expected_id) and message["id"] == expected_id:
            matches.append(message)
    if len(matches) != 1:
        raise ValueError("Expected exactly one response matching the request ID")
    return matches[0]


def classify_response(envelope):
    """Preserve a JSON-RPC response or direct CallToolResult without normalizing it.

    Candidate payloads require an explicit observed mapping before use. Different
    JSON text and structured payloads are a conflict, not an invitation to select
    whichever reports success. Plain text remains in the envelope, unmodified.
    """
    result = {
        "classification": "malformed", "envelope": deepcopy(envelope),
        "candidate_payloads": [], "reasons": [], "conflicting_payloads": False,
        "broker_outcome": "UNKNOWN", "evidence_only": True,
    }

    def finish(classification, reason=None):
        result["classification"] = classification
        if reason:
            result["reasons"].append(reason)
        return result

    if not isinstance(envelope, dict) or not _json_value(envelope):
        return finish("malformed", "RESPONSE_MUST_BE_A_FINITE_JSON_OBJECT")
    if not envelope:
        return finish("empty", "EMPTY_RESPONSE_OBJECT")
    payload = envelope
    if any(key in envelope for key in ("jsonrpc", "result", "error", "id")):
        if (envelope.get("jsonrpc") != "2.0" or "id" not in envelope
                or type(envelope["id"]) not in (str, int, type(None))):
            return finish("malformed", "INVALID_JSONRPC_RESPONSE_HEADER")
        if ("result" in envelope) == ("error" in envelope):
            return finish("malformed", "JSONRPC_REQUIRES_EXACTLY_ONE_RESULT_OR_ERROR")
        if "error" in envelope:
            error = envelope["error"]
            if (not isinstance(error, dict) or type(error.get("code")) is not int
                    or not isinstance(error.get("message"), str)):
                return finish("malformed", "INVALID_JSONRPC_ERROR")
            return finish("protocol_error", "JSONRPC_ERROR_DOES_NOT_ESTABLISH_BROKER_OUTCOME")
        payload = envelope["result"]
        if not isinstance(payload, dict):
            return finish("malformed", "CALL_RESULT_MUST_BE_AN_OBJECT")
    if not payload:
        return finish("empty", "EMPTY_CALL_RESULT")
    if "isError" in payload and type(payload["isError"]) is not bool:
        return finish("malformed", "IS_ERROR_MUST_BE_BOOLEAN")
    # Task responses need a separate, explicitly supported task-status adapter.
    if any(key in payload for key in ("task", "taskId", "task_id")):
        return finish("unsupported_async", "TASK_RESULT_REQUIRES_OBSERVED_STATUS_ADAPTER")
    if "structuredContent" in payload:
        structured = payload["structuredContent"]
        if not isinstance(structured, dict):
            return finish("malformed", "STRUCTURED_CONTENT_MUST_BE_OBJECT")
        result["candidate_payloads"].append({"source": "structuredContent", "payload": deepcopy(structured)})
    content = payload.get("content", [])
    if not isinstance(content, list):
        return finish("malformed", "CONTENT_MUST_BE_ARRAY")
    for index, block in enumerate(content):
        if not isinstance(block, dict) or not isinstance(block.get("type"), str):
            return finish("malformed", "INVALID_CONTENT_BLOCK")
        kind = block["type"]
        if kind == "text":
            if not isinstance(block.get("text"), str):
                return finish("malformed", "TEXT_CONTENT_MUST_BE_STRING")
            try:
                decoded = _decode_json(block["text"])
            except (ValueError, TypeError):
                continue
            if isinstance(decoded, (dict, list)):
                result["candidate_payloads"].append({"source": f"content[{index}].text", "payload": decoded})
        elif kind in {"image", "audio"}:
            if any(not isinstance(block.get(field), str) for field in ("data", "mimeType")):
                return finish("malformed", "INVALID_MEDIA_CONTENT")
        elif kind == "resource":
            resource = block.get("resource")
            if not isinstance(resource, dict) or not isinstance(resource.get("uri"), str):
                return finish("malformed", "INVALID_EMBEDDED_RESOURCE")
        elif kind == "resource_link":
            if any(not isinstance(block.get(field), str) for field in ("uri", "name")):
                return finish("malformed", "INVALID_RESOURCE_LINK")
        else:
            return finish("malformed", "UNSUPPORTED_CONTENT_TYPE")
    distinct = {_canonical(item["payload"]) for item in result["candidate_payloads"]}
    result["conflicting_payloads"] = len(distinct) > 1
    if result["conflicting_payloads"]:
        result["reasons"].append("CONFLICTING_JSON_PAYLOADS_REQUIRE_OBSERVED_RECONCILIATION")
    if payload.get("isError") is True:
        return finish("tool_error", "TOOL_ERROR_DOES_NOT_ESTABLISH_BROKER_OUTCOME")
    if result["conflicting_payloads"]:
        return finish("malformed")
    if "content" not in payload and "structuredContent" not in payload:
        return finish("malformed", "MISSING_CALL_TOOL_RESULT_FIELDS")
    if not content and not payload.get("structuredContent"):
        return finish("empty", "NO_NONEMPTY_TOOL_EVIDENCE")
    return finish("result_received")


def _pointer(value, pointer):
    if pointer == "":
        return value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("Explicit JSON pointer required")
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not token.isdigit():
                raise ValueError("Array pointer needs nonnegative index")
            value = value[int(token)]
        elif isinstance(value, dict):
            value = value[token]
        else:
            raise ValueError("Pointer traverses scalar")
    return value


def _instant(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp must be text")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Timestamp needs timezone")
    return result


def _validate_contract(contract):
    if not isinstance(contract, dict) or not _json_value(contract):
        raise ValueError("CONTRACT_MUST_BE_JSON_OBJECT")
    if (contract.get("source") != "connected_official_mcp_schema_observation"
            or contract.get("read_only") is not True or contract.get("operation") not in READ_OPERATIONS
            or not isinstance(contract.get("tool_name"), str) or not contract["tool_name"]
            or not isinstance(contract.get("evidence_ref"), str) or not contract["evidence_ref"]):
        raise ValueError("OBSERVED_READ_ONLY_CONTRACT_REQUIRED")
    scopes = contract["scopes"]
    if (not isinstance(scopes, dict) or not isinstance(scopes.get("account_alias"), str)
            or not scopes["account_alias"] or scopes.get("account_verified") is not True
            or not isinstance(scopes.get("filters"), dict) or not scopes.get("evidence_ref")):
        raise ValueError("EXPLICIT_VERIFIED_ACCOUNT_AND_FILTER_SCOPE_REQUIRED")
    statuses = scopes["statuses"]
    if not (statuses in ("all", "not_applicable")
            or isinstance(statuses, list) and statuses and all(isinstance(item, str) and item for item in statuses)):
        raise ValueError("EXPLICIT_STATUS_SCOPE_REQUIRED")
    if statuses == "not_applicable" and contract["operation"] != "positions":
        raise ValueError("ORDER_OR_FILL_STATUS_SCOPE_REQUIRED")
    time = scopes["time"]
    if not isinstance(time, dict) or time.get("kind") not in {"all", "current", "window"}:
        raise ValueError("EXPLICIT_TIME_SCOPE_REQUIRED")
    if time["kind"] == "current" and contract["operation"] != "positions":
        raise ValueError("CURRENT_POSITIONS_ARE_NOT_ORDER_HISTORY")
    if time["kind"] == "window" and _instant(time["start"]) >= _instant(time["end"]):
        raise ValueError("INVALID_TIME_WINDOW")
    if not isinstance(contract["payload_source"], str) or not contract["payload_source"]:
        raise ValueError("OBSERVED_PAYLOAD_SOURCE_REQUIRED")
    for name in ("items_pointer",):
        if not isinstance(contract[name], str) or not (contract[name] == "" or contract[name].startswith("/")):
            raise ValueError("EXPLICIT_ITEMS_POINTER_REQUIRED")
    paging = contract["pagination"]
    if not isinstance(paging, dict) or not paging.get("evidence_ref"):
        raise ValueError("OBSERVED_PAGINATION_CONTRACT_REQUIRED")
    if paging.get("mode") == "cursor":
        if paging.get("terminal_cursor", object()) not in (None, ""):
            raise ValueError("EXPLICIT_NULL_OR_EMPTY_TERMINAL_CURSOR_REQUIRED")
        for name in ("next_cursor_pointer", "has_more_pointer"):
            if not isinstance(paging[name], str) or not paging[name].startswith("/"):
                raise ValueError("EXPLICIT_CURSOR_AND_COMPLETION_POINTERS_REQUIRED")
    elif paging.get("mode") == "single_page":
        if not isinstance(paging["complete_pointer"], str) or not paging["complete_pointer"].startswith("/"):
            raise ValueError("EXPLICIT_SINGLE_PAGE_COMPLETION_POINTER_REQUIRED")
    else:
        raise ValueError("UNSUPPORTED_PAGINATION_MODE")


def collect_readonly_pages(read_page, contract, *, max_pages=20, max_items=10000):
    """Collect bounded evidence with a trusted read_page(cursor) callback.

    The callback must issue only the observed read operation with the declared
    scopes. This function neither creates a broker client nor executes commands.
    `complete` applies to pages within `scopes`; `coverage_complete` additionally
    excludes restricted statuses/extra filters. Neither establishes an attempt's
    outcome, even when every page is empty. Returned envelopes are PRIVATE.
    """
    result = {"complete": False, "coverage_complete": False, "items": [], "pages": [],
              "scopes": deepcopy(contract.get("scopes")) if isinstance(contract, dict) else None,
              "reasons": [], "broker_outcome": "UNKNOWN", "evidence_only": True}
    if (type(max_pages) is not int or not 1 <= max_pages <= 1000
            or type(max_items) is not int or not 1 <= max_items <= 1000000):
        result["reasons"].append("INVALID_COLLECTION_LIMITS")
        return result
    try:
        _validate_contract(contract)
    except (KeyError, TypeError, ValueError, IndexError):
        result["reasons"].append("INVALID_OR_INCOMPLETE_OBSERVED_READ_CONTRACT")
        return result
    paging = contract["pagination"]
    cursor, seen = None, set()
    for _ in range(max_pages):
        cursor_key = _canonical(cursor)
        if cursor_key in seen:
            result["reasons"].append("REPEATED_CURSOR")
            return result
        seen.add(cursor_key)
        try:
            response = classify_response(read_page(cursor))
        except Exception as exc:
            # Error strings can echo private routing; retain only the exception class.
            result["reasons"].append("READ_CALLBACK_FAILED:" + type(exc).__name__)
            return result
        result["pages"].append({"cursor": cursor, "response": response})
        if response["classification"] != "result_received" or response["conflicting_payloads"]:
            result["reasons"].append("UNUSABLE_READ_RESPONSE:" + response["classification"])
            return result
        candidates = [item["payload"] for item in response["candidate_payloads"]
                      if item["source"] == contract["payload_source"]]
        if len(candidates) != 1:
            result["reasons"].append("OBSERVED_PAYLOAD_SOURCE_MISSING_OR_AMBIGUOUS")
            return result
        try:
            payload = candidates[0]
            items = _pointer(payload, contract["items_pointer"])
            if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
                raise ValueError("Items must be object array")
            remaining = max_items - len(result["items"])
            result["items"].extend(deepcopy(items[:remaining]))
            if len(items) > remaining:
                result["reasons"].append("ITEM_LIMIT_REACHED")
                return result
            if paging["mode"] == "single_page":
                if _pointer(payload, paging["complete_pointer"]) is not True:
                    raise ValueError("Single page lacks explicit completeness")
                result["complete"] = True
                break
            has_more = _pointer(payload, paging["has_more_pointer"])
            next_cursor = _pointer(payload, paging["next_cursor_pointer"])
            if type(has_more) is not bool or type(next_cursor) not in (str, int, type(None)):
                raise ValueError("Invalid pagination values")
            terminal = next_cursor == paging["terminal_cursor"]
            if has_more == terminal:
                raise ValueError("Cursor and completeness disagree")
            if not has_more:
                result["complete"] = True
                break
            if next_cursor in (None, "") or _canonical(next_cursor) in seen:
                result["reasons"].append("MISSING_OR_REPEATED_CURSOR")
                return result
            if len(result["items"]) >= max_items:
                result["reasons"].append("ITEM_LIMIT_REACHED")
                return result
            cursor = next_cursor
        except (KeyError, TypeError, ValueError, IndexError):
            result["reasons"].append("MISSING_MALFORMED_OR_CONTRADICTORY_PAGE_METADATA")
            return result
    if not result["complete"]:
        result["reasons"].append("PAGE_LIMIT_REACHED")
        return result
    scopes = contract["scopes"]
    result["coverage_complete"] = scopes["statuses"] in ("all", "not_applicable") and not scopes["filters"]
    if not result["coverage_complete"]:
        result["reasons"].append("RESTRICTED_STATUS_OR_FILTER_COVERAGE")
    if not result["items"]:
        result["reasons"].append("NO_MATCH_IS_NOT_PROOF_OF_REJECTION_OR_NON_SUBMISSION")
    return result
