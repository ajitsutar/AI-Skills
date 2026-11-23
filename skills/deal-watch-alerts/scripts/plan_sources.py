"""Plan owners for caller-vetted merchant hosts; no discovery, I/O or DNS in plan()."""

import argparse
import json
import re


LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
RESERVED = {"localhost", "local", "internal", "intranet", "corp", "lan", "home", "private",
            "localdomain", "test", "invalid", "example", "onion", "arpa", "alt",
            "example.com", "example.net", "example.org"}


def host(value):
    # Only normalize DNS spellings; do not guess registrable domains or strip paths.
    if not isinstance(value, str) or not value.isascii():
        raise ValueError("expected a bare ASCII merchant host")
    name = value.lower().removesuffix(".").removeprefix("www.")
    labels = name.split(".")
    if (len(name) > 253 or len(labels) < 2 or not re.fullmatch("[a-z]{2,63}", labels[-1])
            or any(not LABEL.fullmatch(label) or label.startswith("xn--") for label in labels)
            or any(".".join(labels[i:]) in RESERVED for i in range(len(labels)))
            or (len(labels) == 2 and len(labels[-1]) == 2
                and labels[0] in {"ac", "co", "com", "edu", "gov", "net", "org"})):
        raise ValueError("expected a public merchant host, not a URL, IP, private name or suffix")
    return name


def plan(seeds=(), proposed=(), excluded=(), paused=(), allowed=None, aliases=()):
    """None means unrestricted by allowlist; an empty allowlist admits nothing."""
    mapping = {}
    for pair in aliases:
        if pair.count("=") != 1:
            raise ValueError("expected alias=canonical-host")
        alias, root = map(host, pair.split("="))
        if mapping.setdefault(alias, root) != root:
            raise ValueError("conflicting canonical hosts for an alias")
    if any(alias != root and mapping.get(root, root) != root for alias, root in mapping.items()):
        raise ValueError("alias chains and cycles are ambiguous; map directly to the final host")

    def canonical(domain):
        return mapping.get(domain, domain)

    families = {}
    for alias, root in mapping.items():
        families.setdefault(root, set()).add(alias)

    def policy_hosts(values):
        result = set()
        for value in values:
            root = canonical(host(value))
            result.update({root, *families.get(root, ())})
        return result

    deny, hold = policy_hosts(excluded), policy_hosts(paused)
    allow = None if allowed is None else {canonical(host(value)) for value in allowed}
    candidates = {}
    for origin, values in (("seed", seeds), ("proposed", proposed)):
        for value in values:
            candidates.setdefault(canonical(host(value)), origin)

    eligible, skipped = [], []
    for root, origin in candidates.items():
        # Blocks also cover descendants, including descendants of a blocked alias.
        names = {root, *families.get(root, ())}
        ancestors = {".".join(parts[i:]) for name in names for parts in [name.split(".")]
                     for i in range(len(parts))}
        reason = ("excluded" if ancestors & deny else "paused" if ancestors & hold else
                  "not_allowlisted" if allow is not None and root not in allow else None)
        row = {"domain": root, "origin": origin}
        if reason:
            skipped.append({**row, "reason": reason})
        else:
            eligible.append(row)
    return {"eligible": eligible, "skipped": skipped, "coverage": "not_evaluated"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("seed", "discover", "exclude", "pause", "alias"):
        parser.add_argument("--" + flag, action="append", default=[],
                            metavar="ALIAS=HOST" if flag == "alias" else "HOST")
    parser.add_argument("--allow", action="append", metavar="HOST", help="exact allowlist (repeatable)")
    parser.add_argument("--only-listed", action="store_true", help="use seeds as the allowlist unless --allow is given")
    args = parser.parse_args()
    allowed = args.seed if args.only_listed and args.allow is None else args.allow
    try:
        result = plan(args.seed, args.discover, args.exclude, args.pause, allowed, args.alias)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
