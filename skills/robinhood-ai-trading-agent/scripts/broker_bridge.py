"""Schema-bound requests for official broker tools called by the Codex host.

No credential client or guessed Robinhood HTTP API. Codex owns its authenticated
MCP session. The host discovers actual tools/schemas, supplies exact mappings and
invokes the returned request only after the execution ledger permits it.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from risk_engine import canonical_hash, dec, timestamp


OFFICIAL_ENDPOINT = "https://agent.robinhood.com/mcp/trading"
OPERATIONS = {"quote", "positions", "orders", "account", "review", "submit", "cancel", "advanced_review", "advanced_submit"}


def pointer(document, path):
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("Mapping source must be an explicit JSON pointer")
    result = document
    for part in path[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        result = result[int(part)] if isinstance(result, list) else result[part]
    return result


def local_schema_only(value):
    if isinstance(value, dict):
        if "$ref" in value and not value["$ref"].startswith("#"):
            raise ValueError("Bundle external schema references before validation; no implicit network resolution")
        for child in value.values():
            local_schema_only(child)
    elif isinstance(value, list):
        for child in value:
            local_schema_only(child)


def binding_sources(binding):
    if 'object' in binding:
        return set().union(*(binding_sources(v) for v in binding['object'].values()))
    if 'array' in binding:
        return set().union(*(binding_sources(v) for v in binding['array']))
    return {binding['pointer']}


def resolve_binding(binding, inputs, redact=False):
    if 'object' in binding:
        return {k:resolve_binding(v,inputs,redact) for k,v in binding['object'].items()}
    if 'array' in binding:
        return [resolve_binding(v,inputs,redact) for v in binding['array']]
    if redact and binding['pointer'].startswith('/private_routing/'):
        return '<HOST_PRIVATE_ROUTING>'
    value = pointer(inputs,binding['pointer'])
    kind = binding['type']
    if 'enum_map' in binding:
        if binding['pointer'] not in {'/order/side','/order/order_type','/order/time_in_force'} or not binding.get('evidence'):
            raise ValueError('Enum translation needs observed semantic evidence')
        value = binding['enum_map'][value]
    if kind == 'integer':
        numeric = dec(value)
        if numeric != numeric.to_integral_value():
            raise ValueError('Noninteger quantity cannot be coerced into broker schema')
        return int(numeric)
    if kind == 'number':
        numeric = dec(value)
        value = float(numeric)
        if dec(str(value)) != numeric:
            raise ValueError('Numeric conversion loses precision; use a supported exact representation')
    elif kind == 'string':
        value = str(value)
    elif kind == 'boolean':
        if type(value) is not bool:
            raise ValueError('Broker Boolean must not be truthy text')
    elif kind != 'raw':
        raise ValueError('Unknown binding conversion')
    return value


def build_request(capabilities, operation, inputs, now, expected_alias, max_age_seconds=86400):
    """Bindings map broker argument -> {pointer, type}. No freehand argument rewrite.

    inputs separates order, approved constants and private broker routing. This
    function returns real arguments in memory: never print/save routing identifiers.
    Persist only request_hash and redacted_request from redact_request().
    """
    from jsonschema import Draft202012Validator
    if operation not in OPERATIONS:
        raise ValueError("Unsupported broker operation")
    if capabilities["endpoint"] != OFFICIAL_ENDPOINT or capabilities["account_alias"] != expected_alias:
        raise ValueError("Official endpoint and verified account alias required")
    if capabilities.get("source") != "connected_official_mcp_schema_observation":
        raise ValueError("Capabilities must come from the connected official broker tool schemas")
    if not 0 <= (now - timestamp(capabilities["checked_at"])).total_seconds() <= max_age_seconds:
        raise ValueError("Broker capabilities expired or future-dated")
    tool = capabilities["operations"][operation]
    if capabilities.get("account_routing_verified") is not True:
        raise ValueError("Account routing must be verified from the connected broker")
    if not tool.get("tool_name") or not tool.get("input_schema"):
        raise ValueError("Missing actual broker tool schema")
    local_schema_only(tool["input_schema"])
    if canonical_hash(tool["input_schema"]) != tool["schema_hash"]:
        raise ValueError("Broker schema changed; rediscover and revalidate mapping")
    arguments = {name:resolve_binding(binding,inputs) for name,binding in tool['bindings'].items()}
    if operation in {"submit", "advanced_submit", "review", "advanced_review"}:
        mapped = set().union(*(binding_sources(binding) for binding in tool['bindings'].values()))
        required = {"/order/symbol", "/order/side", "/order/quantity", "/order/limit_price",
                    "/order/order_type", "/order/time_in_force", "/order/extended_hours"}
        # Some broker tools fix semantics instead of exposing an argument. Each
        # such field needs an observed, documented value, never a guessed default.
        for field, observed in tool.get("fixed_semantics", {}).items():
            if field in {"order_type", "time_in_force", "extended_hours"} and observed.get("evidence"):
                if observed["value"] != inputs["order"][field]:
                    raise ValueError("Broker fixed semantics conflict with the approved order")
                required.discard("/order/" + field)
        if not required <= mapped:
            raise ValueError("Exact order identity/economics must map to broker arguments")
        if inputs["order"]["account_alias"] != expected_alias:
            raise ValueError("Order account alias differs from capability mapping")
        if operation in {"advanced_submit", "advanced_review"}:
            if not {"/order/stop_price", "/order/target_price"} <= mapped:
                raise ValueError("Attached protective prices must bind to the approved order")
            semantics = tool.get("protection_semantics", {})
            if (semantics.get("atomic_with_entry") is not True
                    or semantics.get("partial_fill_quantity_tracking") is not True
                    or semantics.get("mutually_exclusive_exits") is not True
                    or not semantics.get("evidence")):
                raise ValueError("Verified atomic, partial-fill-aware native protection required")
    routing = set().union(*(binding_sources(binding) for binding in tool['bindings'].values()))
    if not any(p.startswith("/private_routing/") for p in routing):
        scoped = tool.get("connection_scoped_account", {})
        if scoped.get("account_alias") != expected_alias or not scoped.get("evidence"):
            raise ValueError("Explicit private account binding or verified connection-scoped account required")
    if operation == "cancel" and "/private_routing/broker_order_id" not in routing:
        raise ValueError("Cancellation must bind the exact broker order identifier")
    Draft202012Validator.check_schema(tool["input_schema"])
    from jsonschema.exceptions import ValidationError
    try:
        Draft202012Validator(tool["input_schema"]).validate(arguments)
    except ValidationError as exc:
        raise ValueError("Broker arguments fail the observed schema; inspect privately in host memory") from None
    request = {"tool_name": tool["tool_name"], "arguments": arguments}
    return {"request": request, "request_hash": canonical_hash(request),
            "capability_hash": canonical_hash(capabilities), "operation": operation,
            "schema_hash": tool["schema_hash"], "execution_authorized": False}


def redact_request(prepared, capabilities):
    result = deepcopy(prepared)
    operation = capabilities["operations"][prepared["operation"]]
    def scrub(value,binding):
        if 'object' in binding:
            return {k:scrub(value[k],v) for k,v in binding['object'].items()}
        if 'array' in binding:
            return [scrub(value[i],v) for i,v in enumerate(binding['array'])]
        return '<HOST_PRIVATE_ROUTING>' if binding['pointer'].startswith('/private_routing/') else value
    for name, binding in operation["bindings"].items():
        result["request"]["arguments"][name] = scrub(result['request']['arguments'][name],binding)
    result["redacted"] = True
    result["execution_authorized"] = False
    return result


def receipt(prepared, returned_request_hash, broker_state, cumulative_filled, average_price, evidence_ref):
    """An acknowledged broker response is not assumed FILLED; explicit state needed."""
    if prepared["request_hash"] != returned_request_hash or not evidence_ref:
        raise ValueError("Broker response does not bind to the exact submitted request")
    if broker_state not in {"UNKNOWN", "OPEN", "PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING", "CANCELLED", "REJECTED"}:
        raise ValueError("Unknown status mapping: retain UNKNOWN and reconcile")
    if dec(cumulative_filled) < 0:
        raise ValueError("Negative cumulative fill")
    return {"state": broker_state, "cumulative_filled": str(dec(cumulative_filled)),
            "average_price": str(dec(average_price)) if average_price is not None else None,
            "request_hash": returned_request_hash, "evidence_ref": evidence_ref}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capabilities", type=Path)
    parser.add_argument("inputs", type=Path, help="Use only sanitized demo inputs on disk; private live routing stays in host memory")
    parser.add_argument("--operation", choices=sorted(OPERATIONS), required=True)
    parser.add_argument("--as-of", required=True, help="Offline binding verification clock; live host uses its actual clock")
    args = parser.parse_args()
    capabilities = json.loads(args.capabilities.read_text(encoding="utf-8-sig"))
    inputs = json.loads(args.inputs.read_text(encoding="utf-8-sig"))
    prepared = build_request(capabilities, args.operation, inputs, timestamp(args.as_of), capabilities["account_alias"])
    print(json.dumps(redact_request(prepared, capabilities), indent=2))


if __name__ == "__main__":
    main()
