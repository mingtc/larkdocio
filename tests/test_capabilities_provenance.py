"""LD-475 — the permission provenance is carried ONCE, BY REFERENCE, and nothing is lost.

The measured defect (on the branch base): 93,818 of the payload's 409,557 bytes
were **repeated long strings**, and almost all of them were permission provenance — one drive
endpoint's 3,593-character *"no scope string has ever been observed demanded…"* paragraph
serialized **nine** times, the spreadsheet-values one **21** times, the record-write evidence
**21** times. Each is authored exactly once, in ``permissions.ENDPOINT_SCOPES``; only the
projection re-typed it, because every operation reaching an endpoint carries the same ``Scope``
object.

**The provenance is the point — eight copies of it are not.** So the requirement here is not
"smaller": it is that the same paragraphs are all still in the payload, once each, and that an
operation's row still leads to the one it rests on. The load-bearing arm is therefore the
**round trip**: :func:`larkdocio.capabilities._provenance.inflate` of the shipped payload is
held **byte-identical** to the same payload built with no catalog at all. A reference that
cannot be resolved back is a deletion wearing a better name, and this is what tells the two
apart.
"""
import collections
import json

import pytest

import larkdocio
from larkdocio.capabilities import _models, _provenance
from larkdocio.capabilities._provenance import CATALOG_KEYS, dedupe, inflate


def _canonical(payload):
    return json.dumps(payload, default=str, sort_keys=True).encode("utf-8")


@pytest.fixture(scope="module")
def payload():
    return larkdocio.capabilities(full=True)


@pytest.fixture
def uncatalogued(monkeypatch):
    """The payload as it would serialize with the deduplication switched off — the shape every
    provenance paragraph was inlined into, built by the real assembler."""
    monkeypatch.setattr(_models, "_dedupe_provenance", lambda payload: payload)
    return larkdocio.capabilities(full=True)


# --------------------------------------------------------------------------- #
# 1. THE ROUND TRIP — by reference, not by deletion.                            #
# --------------------------------------------------------------------------- #

def test_INFLATING_the_shipped_payload_reproduces_the_INLINE_SHAPE_BYTE_FOR_BYTE(
        payload, uncatalogued):
    """The arm this whole change rests on. Not "equivalent", not "same keys" — the exact
    canonical serialization, so a paragraph that was silently trimmed, re-ordered or attached
    to the wrong operation fails here."""
    assert _canonical(inflate(payload)) == _canonical(uncatalogued)


def test_the_catalogs_are_the_ONLY_difference_between_the_two_shapes(payload, uncatalogued):
    """Said from the other side: the deduplication touches the permission blocks and adds the
    catalogs, and nothing else in the registry moves."""
    assert set(payload) - set(uncatalogued) == set(CATALOG_KEYS)
    assert set(uncatalogued) - set(payload) == set()


def test_DEDUPING_the_inline_shape_reproduces_THE_SHIPPED_PAYLOAD(payload, uncatalogued):
    """The forward direction, so neither half of the pair is assumed: the function is what
    ``capabilities()`` applies, run again on an inline payload, and it lands on the same bytes
    the wheel ships."""
    assert _canonical(dedupe(uncatalogued)) == _canonical(payload)


def test_it_is_SMALLER_and_the_saving_is_MEASURED_not_claimed(payload, uncatalogued):
    """The size claim, derived at run time — the only kind of size claim this repo states."""
    catalogued, inline = len(_canonical(payload)), len(_canonical(uncatalogued))
    assert catalogued < inline, (catalogued, inline)
    # A quarter of the registry was repeated provenance when this was measured; assert an
    # order of magnitude less than that so the arm is about the mechanism, not the day's figure.
    assert inline - catalogued > inline // 40, (
        f"the catalogs saved only {inline - catalogued} of {inline} bytes — if the repetition "
        f"is genuinely gone from the source, this arm has outlived its subject")


# --------------------------------------------------------------------------- #
# 2. EVERY REFERENCE RESOLVES, AND EVERY ROW IS REFERENCED — both directions.   #
# --------------------------------------------------------------------------- #

def _blocks(payload):
    return list(_provenance._permission_blocks(payload))


def test_every_reference_an_operation_carries_RESOLVES(payload):
    """A pointer a consumer cannot follow is worse than the repetition it replaced."""
    for block in _blocks(payload):
        for field in ("scopes", "optional_scopes"):
            for key in block.get(field) or ():
                assert key in payload["scope_evidence"], (field, key)
        for key in block.get("unknown_requirements") or ():
            assert key in payload["unknown_requirements"], key


def test_no_catalog_row_is_UNREFERENCED(payload):
    """The other direction: a catalog is a projection of what the operations require, so a row
    nothing points at means the catalog has outlived a requirement."""
    referenced = collections.defaultdict(set)
    for block in _blocks(payload):
        for field in ("scopes", "optional_scopes"):
            referenced["scope_evidence"] |= set(block.get(field) or ())
        referenced["unknown_requirements"] |= set(block.get("unknown_requirements") or ())
    for catalog in CATALOG_KEYS:
        orphans = sorted(set(payload[catalog]) - referenced[catalog])
        assert not orphans, f"{catalog} rows nothing references: {orphans}"


def test_a_KEY_IS_NEVER_PARSED_to_recover_the_thing_it_names(payload):
    """Where two different requirements share one scope string the later key carries a ``#2``
    suffix — so the row keeps its own ``scope`` field, and a caller reads the string from the
    row rather than stripping the key."""
    for key, row in payload["scope_evidence"].items():
        assert key.split("#")[0] == row["scope"], (key, row["scope"])
        assert row["evidence"], f"{key} carries no evidence — a requirement with none is a memory"
    for key, row in payload["unknown_requirements"].items():
        assert key.split("#")[0] == row["endpoint"], (key, row["endpoint"])
        assert row["reason"], key


def test_the_scope_rows_carry_EVERY_FIELD_the_inline_rows_did(payload, uncatalogued):
    """Nothing was quietly dropped on the way into the catalog: the field set of a catalogued
    scope row is exactly the field set the inline rows had."""
    inline_fields = {frozenset(row)
                     for block in _blocks(uncatalogued)
                     for row in (block.get("scopes") or []) + (block.get("optional_scopes") or [])
                     if isinstance(row, dict)}
    assert inline_fields, "the inline shape carried no scope row at all — the arm is vacuous"
    assert {frozenset(row) for row in payload["scope_evidence"].values()} == inline_fields


def test_the_scopes_a_SURFACE_reports_are_still_the_union_of_its_OPERATIONS_rows(payload):
    """The permission projection's own rule, re-checked through the catalog: a surface's
    ``scopes`` are the union of its operations' requirements, not a second assertion. The
    references have to resolve for this to hold at all, which is the point."""
    for sid, surface in payload["surfaces"].items():
        from_ops = set()
        for row in surface["operations"]:
            for key in row["permissions"]["scopes"]:
                if payload["scope_evidence"][key]["established"]:
                    from_ops.add(payload["scope_evidence"][key]["scope"])
        credentials = surface["credentials"]
        declared = set(credentials["scopes"]) | set(credentials["optional_scopes"])
        assert not from_ops - declared, (sid, sorted(from_ops - declared))
        # The only thing a surface may declare beyond its own operations' rows is the
        # requirement of a surface it RUNS INSIDE, and it says which one under ``composes``.
        composed = set()
        for other in surface.get("composes") or ():
            other_creds = payload["surfaces"][other]["credentials"]
            composed |= set(other_creds["scopes"]) | set(other_creds["optional_scopes"])
        assert not declared - from_ops - composed, (sid, sorted(declared - from_ops - composed))


# --------------------------------------------------------------------------- #
# 3. THE REPETITION IS ACTUALLY GONE — the finding, re-measured.                #
# --------------------------------------------------------------------------- #

def _repeated_long_strings(payload, floor=200):
    counts = collections.Counter()

    def walk(obj):
        if isinstance(obj, dict):
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)
        elif isinstance(obj, str) and len(obj) >= floor:
            counts[obj] += 1

    walk(payload)
    return {text: n for text, n in counts.items() if n > 1}


def test_NO_LONG_PROSE_STRING_IS_SERIALIZED_TWICE(payload):
    """The finding, stated as a property rather than as a number: a paragraph appears once.

    The floor is 200 characters — a *paragraph*, not a scope string or an endpoint path, which
    are supposed to repeat because they are how rows are joined.
    """
    repeated = _repeated_long_strings(payload)
    assert not repeated, (
        "these paragraphs are still serialized more than once: "
        + json.dumps({text[:70] + "…": n for text, n in repeated.items()}, indent=2))


def test_the_repetition_guard_BITES_on_the_shape_that_shipped(uncatalogued):
    """…and it would have caught it: the un-catalogued payload is the shape that shipped, and
    the property above is false of it."""
    repeated = _repeated_long_strings(uncatalogued)
    assert repeated, "the inline shape carried no repeated paragraph — the arm is vacuous"
    assert max(repeated.values()) > 5


# --------------------------------------------------------------------------- #
# 4. THE PURE FUNCTIONS, red-proved on specimens.                               #
# --------------------------------------------------------------------------- #

_ROW = {"scope": "a:scope", "verification": "grant-verified", "evidence": "a capture",
        "degrades": False, "field_level": False, "established": True}


def _specimen(*scope_rows, unknown=()):
    return {"surfaces": {"s": {"operations": [
        {"name": "op", "kind": "operation", "projected_from": "larkdocio.x",
         "permissions": {"endpoints": ["/e"], "scopes": list(scope_rows),
                         "optional_scopes": [], "unknown_requirements": list(unknown)}}]}}}


def test_two_operations_sharing_a_requirement_share_ONE_row():
    payload = _specimen(_ROW)
    payload["surfaces"]["s"]["operations"].append(
        dict(payload["surfaces"]["s"]["operations"][0], name="op2"))
    out = dedupe(json.loads(json.dumps(payload)))
    assert list(out["scope_evidence"]) == ["a:scope"]
    assert [row["permissions"]["scopes"] for row in out["surfaces"]["s"]["operations"]] == [
        ["a:scope"], ["a:scope"]]


def test_two_DIFFERENT_requirements_sharing_a_SCOPE_STRING_get_two_rows():
    """The disambiguation, on a specimen: same string, different evidence, two rows — because
    merging them would state one requirement's evidence for another's."""
    other = dict(_ROW, evidence="a different capture", note="and a different absence")
    payload = _specimen(_ROW)
    payload["surfaces"]["s"]["operations"].append(
        {"name": "op2", "kind": "operation", "projected_from": "larkdocio.x",
         "permissions": {"endpoints": ["/e"], "scopes": [other], "optional_scopes": [],
                         "unknown_requirements": []}})
    out = dedupe(json.loads(json.dumps(payload)))
    assert sorted(out["scope_evidence"]) == ["a:scope", "a:scope#2"]
    assert {row["scope"] for row in out["scope_evidence"].values()} == {"a:scope"}
    assert _canonical(inflate(out)) == _canonical(payload)


def test_the_KEY_A_ROW_GETS_depends_on_its_CONTENT_not_on_the_traversal_order():
    """Two payloads carrying the same two rows in opposite orders catalog them identically —
    which is why the keys are stable across a reshuffle of the surfaces above them."""
    other = dict(_ROW, evidence="a different capture")
    forward = _specimen(_ROW, other)
    backward = _specimen(other, _ROW)
    first = dedupe(json.loads(json.dumps(forward)))["scope_evidence"]
    second = dedupe(json.loads(json.dumps(backward)))["scope_evidence"]
    assert first == second


def test_an_unknown_requirement_is_keyed_by_ITS_ENDPOINT():
    payload = _specimen(unknown=["/open-apis/x: nothing has ever been observed demanded"])
    out = dedupe(json.loads(json.dumps(payload)))
    assert out["unknown_requirements"] == {
        "/open-apis/x": {"endpoint": "/open-apis/x",
                         "reason": "nothing has ever been observed demanded"}}
    assert out["surfaces"]["s"]["operations"][0]["permissions"]["unknown_requirements"] == [
        "/open-apis/x"]
    assert _canonical(inflate(out)) == _canonical(payload)


def test_a_payload_with_NO_PERMISSION_BLOCK_grows_NO_EMPTY_CATALOG():
    """An empty catalog would promise a fact the payload does not have."""
    out = dedupe({"surfaces": {"s": {"title": "t"}}, "version": "0.0.0"})
    assert set(out) == {"surfaces", "version"}
