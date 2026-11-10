"""Every digest or length recorded for one block agrees across every capture file.

``tests/captures/README.md`` § 2 says replaced document content was replaced *together* with
every encoding of it, including its ``record_sha256_12``. A copy of a block's digest that the
replacement missed would still describe the original content — and nothing else reads it, so
no other test notices. This guard walks every capture, attaches each digest/length field to the
block id it describes (a ``block_id`` sibling, or a dict keyed by the block id), and requires
one value per (block id, field) across the whole tree. Where the record itself is present
beside its digest, the digest must also be the digest of that record.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

CAPTURES = Path(__file__).resolve().parent / "captures"

# A docx block / document id: 27 base62 characters (the replaced forms keep the length).
_BLOCK_ID = re.compile(r"^[A-Za-z0-9]{27}$")
# The fields that describe a block's content rather than its position.
_DIGEST_FIELD = re.compile(r"(?:^|_)(?:sha256(?:_\d+)?|sha1|md5|record_len)$")


def _walk(node, block_id, path, out):
    if isinstance(node, dict):
        own = node.get("block_id")
        here = own if isinstance(own, str) and _BLOCK_ID.match(own) else block_id
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                child_id = key if _BLOCK_ID.match(key) and isinstance(value, dict) else here
                _walk(value, child_id, f"{path}.{key}", out)
            elif here is not None and _DIGEST_FIELD.search(key) and not isinstance(value, bool):
                out.append((here, key, value, f"{path}.{key}"))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk(item, block_id, f"{path}[{i}]", out)


def _collect():
    seen = defaultdict(lambda: defaultdict(list))
    for f in sorted(CAPTURES.rglob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        found: list = []
        _walk(data, None, "$", found)
        rel = f.relative_to(CAPTURES).as_posix()
        for block_id, key, value, where in found:
            seen[(block_id, key)][json.dumps(value)].append(f"{rel}:{where}")
    return seen


def test_the_walk_finds_the_specimen_digest_in_both_files():
    """The guard is not vacuous: the specimen's digest is seen in both files that carry it."""
    seen = _collect()
    files = {
        site.split(":", 1)[0]
        for (bid, key), values in seen.items()
        if key == "record_sha256_12"
        for sites in values.values()
        for site in sites
    }
    assert "mermaid-gate-captures/20-specimen.json" in files
    assert "comments-probe-round2-captures/10-harvest-docx.json" in files


def test_every_digest_naming_one_block_has_one_value():
    conflicts = {
        f"{bid} {key}": dict(values) for (bid, key), values in _collect().items() if len(values) > 1
    }
    assert not conflicts, (
        "one block, two digests — a replaced block left a copy of the original's hash behind:\n"
        + json.dumps(conflicts, indent=1)
    )


def test_a_digest_beside_its_record_is_that_records_digest():
    checked = 0
    for f in sorted(CAPTURES.rglob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                raw, digest = node.get("record_raw"), node.get("record_sha256_12")
                if isinstance(raw, str) and isinstance(digest, str):
                    checked += 1
                    got = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
                    assert got == digest, f"{f.relative_to(CAPTURES)}: record_sha256_12 is not the record's"
                    if isinstance(node.get("record_len"), int):
                        assert node["record_len"] == len(raw.encode("utf-8"))
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    assert checked >= 1
