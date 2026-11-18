"""Optional schema-mapping utility for data supplied by a native broker host.

No credential client or guessed Robinhood HTTP API. Codex owns its authenticated
MCP session. The host discovers actual tools/schemas and supplies exact mappings.
This utility neither participates in the research handoff nor determines whether
an order may execute. Native host/broker tools own execution and permissions.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from risk_engine import canonical_hash, dec, timestamp


OFFICIAL_ENDPOINT = "https://agent.robinhood.com/mcp/trading"
OPERATIONS = {"quote", "positions", "orders", "fills", "account", "review", "submit", "cancel", "advanced_review", "advanced_submit"}


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
        value = binding['enum_map'][str(value).lower() if type(value) is bool else value]
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


def build_request(capabilities, operation, inputs, now, expected_alias, max_age_seconds=86400, *, execution_profile=None):
    """Bindings map broker argument -> {pointer, type}. No freehand argument rewrite.

    inputs separates order, supplied constants and private broker routing. This
    function returns real arguments in memory: never print/save routing identifiers.
    Persist only request_hash and redacted_request from redact_request().
    """
    from jsonschema import Draft202012Validator
    # Mapping validates only the caller-supplied schema and exact conversions.
    # Account permissions, freshness, order support and trading policy belong to
    # native host/broker tools. Legacy profile/clock parameters are not gates.
    tool = capabilities["operations"][operation]
    local_schema_only(tool["input_schema"])
    arguments = {name: resolve_binding(binding, inputs) for name, binding in tool['bindings'].items()}
    Draft202012Validator.check_schema(tool["input_schema"])
    from jsonschema.exceptions import ValidationError
    try:
        Draft202012Validator(tool["input_schema"]).validate(arguments)
    except ValidationError as exc:
        raise ValueError("Broker arguments fail the observed schema; inspect privately in host memory") from None
    request = {"tool_name": tool["tool_name"], "arguments": arguments}
    return {"request": request, "request_hash": canonical_hash(request),
            "capability_hash": canonical_hash(capabilities), "operation": operation,
            "schema_hash": canonical_hash(tool["input_schema"]), "adapter_role": "OPTIONAL_SCHEMA_MAPPING",
            "advisory_only": True, "enforces_execution": False}


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
    result["enforces_execution"] = False
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
    parser.add_argument("--as-of", help="Optional retained observation timestamp; not an execution requirement")
    args = parser.parse_args()
    capabilities = json.loads(args.capabilities.read_text(encoding="utf-8-sig"))
    inputs = json.loads(args.inputs.read_text(encoding="utf-8-sig"))
    prepared = build_request(capabilities, args.operation, inputs, timestamp(args.as_of) if args.as_of else None, capabilities.get("account_alias"))
    print(json.dumps(redact_request(prepared, capabilities), indent=2))


if __name__ == "__main__":
    main()
