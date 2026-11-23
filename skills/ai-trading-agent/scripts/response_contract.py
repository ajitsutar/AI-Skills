"""Check the required top-level response fields declared by an original delivery contract."""
import hashlib
import re

import handoff_report as binding_json
from supplied_research import require


FIELD = r"[A-Za-z_][A-Za-z0-9_]*"
TOKEN = rf"(?:`{FIELD}`|{FIELD})"
CLAUSE = re.compile(
    r"\b`?response\.json`?\s+(?:containing|must contain|must include|with required fields)"
    r"\s*:?\s+(?P<names>[^.;\r\n]+)(?:\.|;|$)", re.IGNORECASE
)


def declared_fields(raw):
    """Use either an explicit required-key list or an unambiguous text clause."""
    text = raw.decode("utf-8-sig")
    if text.lstrip().startswith("{"):
        data = binding_json.strict_json(raw)
        require(isinstance(data, dict) and set(data) in ({"required"}, {"type", "required"})
                and data.get("type", "object") == "object", "REQUIRED_KEY_CONTRACT_FORMAT")
        names = data["required"]
        require(isinstance(names, list) and names and all(isinstance(n, str) and n for n in names),
                "NONEMPTY_REQUIRED_KEY_LIST")
        require(len(set(names)) == len(names), "DUPLICATE_REQUIRED_FIELD")
        return names
    clauses = list(CLAUSE.finditer(text))
    require(len(clauses) == 1, "ONE_EXPLICIT_RESPONSE_FIELD_LIST_REQUIRED")
    names_text = clauses[0]["names"].strip()
    separator = r"(?:\s*,\s*(?:and\s+)?|\s+and\s+)"
    require(re.fullmatch(rf"{TOKEN}(?:{separator}{TOKEN})*", names_text), "AMBIGUOUS_REQUIRED_FIELD_LIST")
    names = [word.strip("`") for word in re.split(separator, names_text)]
    require(len(set(names)) == len(names), "DUPLICATE_REQUIRED_FIELD")
    return names


def audit(raw, envelope):
    required = declared_fields(raw)
    require(isinstance(envelope, dict), "RESPONSE_OBJECT_REQUIRED")
    missing = [name for name in required if name not in envelope]
    require(not missing, "MISSING_REQUIRED_RESPONSE_FIELDS " + ", ".join(missing))
    return {"contract_sha256": hashlib.sha256(raw).hexdigest(), "required_fields_present": required,
            "scope": "top-level field presence; accuracy and evidence require separate review"}
