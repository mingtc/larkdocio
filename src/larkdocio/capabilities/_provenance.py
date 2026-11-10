"""THE PROVENANCE CATALOGS — the prose a permission requirement rests on, carried ONCE.

The problem, measured (2026-08-20, over the un-catalogued shape :func:`inflate` reproduces,
as Σ len(s)×(occurrences−1) over the 18 distinct strings of ≥200 characters — this module's own
threshold — that occur 132 times between them): **87,012 of that shape's 402,275 bytes were
duplicate copies of long strings**, and almost all of them were permission provenance. One
drive endpoint's *"no scope string has ever
been observed demanded…"* paragraph is 3,593 characters and was serialized **nine** times; the
spreadsheet-values one, 21 times; the record-write evidence, 21 times. They are authored
**once** — in :data:`larkdocio.permissions.ENDPOINT_SCOPES`, one row per endpoint family — and
it is only the *projection* that re-typed them per operation, because every operation reaching
that endpoint carries the same ``Scope`` object.

**Deduplicated by REFERENCE, never by deletion.** The provenance is the point: a scope
requirement with no evidence is a memory, not a fact. So nothing is dropped — every paragraph
is still in the payload, exactly once, under a top-level catalog, and each operation names the
catalog entry its requirement rests on. The proof that this is a reference and not a loss is
:func:`inflate`, the exact inverse: it puts every paragraph back where it was, and the guard
(``tests/test_capabilities_provenance.py``, in the source repository — a test tree is not importable
from the wheel) holds ``inflate(payload)`` **byte-identical** to the un-deduplicated
serialization. A round trip that loses a byte is a red test.

**A pure function of the payload**, applied after assembly rather than during it — so the keys
are computed with the whole payload in view (which is what makes them deterministic and
content-ordered rather than traversal-ordered), and so nothing in the typed layer has to know
that a catalog exists.

What the two catalogs hold
--------------------------
* ``scope_evidence`` — one row per DISTINCT scope requirement: the scope string, how firmly it
  is verified, the evidence that established it, what its absence looks like, and the
  ``degrades`` / ``field_level`` / ``established`` flags. Keyed by the **scope string**, which
  is what a caller has in hand; where two genuinely different requirements share one string —
  the document read's own grant and the comment family's are the same string with different
  evidence and different notes — the later key carries a ``#2`` suffix and the row's own
  ``scope`` field still holds the real string, so a key is never parsed to recover it. (Merging
  them would state one requirement's evidence for another's, which is the one thing a registry
  of evidence may not do.)
* ``unknown_requirements`` — one row per endpoint whose requirement is **not known**, keyed by
  the endpoint itself: what the honest-unknown discipline records instead of guessing a
  plausible scope name.

An operation's ``permissions`` block therefore reads: ``scopes`` and ``optional_scopes`` are
lists of ``scope_evidence`` keys (so *"what do I need"* is a list of scope strings — the answer
in the shape the question is asked), and ``unknown_requirements`` is a list of
``unknown_requirements`` keys.
"""
import json

#: The top-level catalog keys, and the per-operation field each one is referenced from. One
#: place: :func:`dedupe`, :func:`inflate` and the anchor's ownership table all read this rather
#: than spelling a key name three times.
#:
#: ``(catalog key, permission-block fields that reference it, the row field holding the key)``
CATALOGS = (
    ("scope_evidence", ("scopes", "optional_scopes"), "scope"),
    ("unknown_requirements", ("unknown_requirements",), "endpoint"),
)

#: The catalog keys, in the order they serialize.
CATALOG_KEYS = tuple(name for name, _fields, _key in CATALOGS)

#: The separator between an unknown-requirement's endpoint and its recorded reason, as
#: :func:`larkdocio.permissions.unknown_requirements_for` composes it.
_UNKNOWN_SEPARATOR = ": "


def _canonical(obj):
    return json.dumps(obj, default=str, sort_keys=True)


def _assign_keys(rows, name_of):
    """``({key: row}, {canonical row: key})`` for *rows*, keyed by each row's own name.

    Content-ordered: rows sharing a name are sorted by their canonical JSON and the second and
    later ones take a ``#N`` suffix, so the key a row gets depends on the row's **content**
    and not on where the traversal happened to meet it.
    """
    by_name = {}
    for row in rows:
        by_name.setdefault(name_of(row), {})[_canonical(row)] = row
    catalog, refs = {}, {}
    for name in sorted(by_name):
        for index, canonical in enumerate(sorted(by_name[name])):
            key = name if index == 0 else f"{name}#{index + 1}"
            catalog[key] = by_name[name][canonical]
            refs[canonical] = key
    return catalog, refs


def _permission_blocks(payload):
    """Every operation's ``permissions`` block, in serialization order.

    Duck-typed off the row shape, so a new call-site-bearing key joins this walk by existing —
    the discipline :func:`larkdocio.permissions.projection_gaps` is built on.
    """
    for surface in (payload.get("surfaces") or {}).values():
        if not isinstance(surface, dict):
            continue
        for rows in surface.values():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict) and isinstance(row.get("permissions"), dict):
                    yield row["permissions"]


def dedupe(payload: dict) -> dict:
    """*payload* with its permission provenance moved into top-level catalogs and referenced.

    Mutates and returns the payload it is handed (it is called on a freshly built one). A
    payload with no permission block anywhere is returned untouched and grows no empty
    catalog — an empty catalog would be a promise of a fact the payload does not have.
    """
    scope_rows, unknown_rows = [], []
    for block in _permission_blocks(payload):
        for field in ("scopes", "optional_scopes"):
            scope_rows += [row for row in block.get(field) or () if isinstance(row, dict)]
        for reason in block.get("unknown_requirements") or ():
            endpoint, _, text = str(reason).partition(_UNKNOWN_SEPARATOR)
            unknown_rows.append({"endpoint": endpoint, "reason": text})
    scope_catalog, scope_refs = _assign_keys(scope_rows, lambda row: row["scope"])
    unknown_catalog, unknown_refs = _assign_keys(unknown_rows, lambda row: row["endpoint"])
    for block in _permission_blocks(payload):
        for field in ("scopes", "optional_scopes"):
            if field in block:
                block[field] = [scope_refs[_canonical(row)] for row in block[field]]
        if "unknown_requirements" in block:
            block["unknown_requirements"] = [
                unknown_refs[_canonical(dict(zip(
                    ("endpoint", "reason"),
                    str(reason).partition(_UNKNOWN_SEPARATOR)[::2])))]
                for reason in block["unknown_requirements"]]
    if scope_catalog:
        payload["scope_evidence"] = scope_catalog
    if unknown_catalog:
        payload["unknown_requirements"] = unknown_catalog
    return payload


def inflate(payload: dict) -> dict:
    """THE INVERSE — a deep copy of *payload* with every reference resolved back to its prose.

    This is what makes the deduplication a reference rather than a loss, and it is why the
    catalogs may be trusted: the guard holds ``inflate`` of the shipped payload byte-identical
    to the same payload built without any catalog at all, so the two shapes carry exactly the
    same facts.

    It is also the two-line recipe a consumer who wants the old shape writes for themselves.
    """
    import copy

    inflated = copy.deepcopy(payload)
    scope_catalog = inflated.pop("scope_evidence", {})
    unknown_catalog = inflated.pop("unknown_requirements", {})
    for block in _permission_blocks(inflated):
        for field in ("scopes", "optional_scopes"):
            if field in block:
                block[field] = [copy.deepcopy(scope_catalog[key]) for key in block[field]]
        if "unknown_requirements" in block:
            block["unknown_requirements"] = [
                unknown_catalog[key]["endpoint"] + _UNKNOWN_SEPARATOR
                + unknown_catalog[key]["reason"]
                for key in block["unknown_requirements"]]
    return inflated
