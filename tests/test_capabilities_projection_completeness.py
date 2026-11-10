"""LD-459 — the projection a consumer is told is the machine-readable answer IS the
registry's answer, and the drift check reddens when it is not.

The defect this file pins: ``capabilities()`` scatters call sites across sibling keys
(``operations`` / ``legs`` / ``lifecycle``, a key set that varies per surface) while its own
docstring points a consumer at ``operations`` alone. At 1.33.0 that projected **96**
``(surface, op)`` pairs against ``permissions.operation_inventory()``'s **108** — 20
API-using operations, including ``put_image_in_document`` and ``create_document``, reachable
only by a consumer who already knew to look under another key. ``coverage_gaps()`` reported
clean because it audits the registry against the CODE and never the projection against the
registry — the one direction in which the defect lived.

The fix was a derived index, not a hand-list: every surface published ``operation_index``,
built from the surface's own callable-bearing fields, and the permission registry consumed
that index. The audit's two sides are derived INDEPENDENTLY — one off the typed dataclass
fields, the registry side off a duck-typed walk of the emitted dict — which is what makes the
check non-vacuous and what makes it bite when a fourth callable-bearing key is added without
joining the answer.

**LD-475 removed the premise instead of the rule.** An index existed because the rows lived
under three keys and a reader had to be told which one held what. There is now **one** key —
``operations`` — and every row carries the ``kind`` the key used to say by position, so the
index has no second location to point at and the completeness claim is structural: the
duck-typed walk must find call-site rows under **that key and no other**. Every assertion
below is the same claim in the collapsed shape; none was dropped, and the direction that was
broken is still the one being audited.
"""
import larkdocio
from larkdocio import permissions as perm
from larkdocio.capabilities._assembly import _build
from larkdocio.capabilities._models import CALL_KINDS, CALL_SITES_KEY


# --------------------------------------------------------------------------- #
# AC1/AC2 — the projection is COMPLETE, across every callable-bearing key.     #
# --------------------------------------------------------------------------- #

def _op_shaped_keys(surface):
    """Every key of an emitted surface dict whose value is a list of operation rows.

    Duck-typed on purpose: this is the audit's *registry* side and it must not inherit the
    key list the index is built from, or the check would be comparing a thing to itself.
    """
    return {key: value for key, value in surface.items()
            if isinstance(value, list) and value
            and all(isinstance(row, dict) and "name" in row and "projected_from" in row
                    for row in value)}


def test_every_registry_operation_appears_in_the_projection():
    """AC1 — the gap is zero: every ``(surface, operation)`` the permission registry knows is
    reachable from ``capabilities()`` through one published index."""
    caps = larkdocio.capabilities(full=True)
    projected = {(sid, row["name"])
                 for sid, surface in caps["surfaces"].items()
                 for row in surface[CALL_SITES_KEY]}
    inventory = {key for key, _endpoints in perm.operation_inventory()}
    assert not inventory - projected, (
        "these API-using operations are in the registry and absent from the projection: "
        f"{sorted(inventory - projected)}")


def test_ONE_key_carries_every_callable_bearing_row():
    """AC2, in the collapsed shape — ``operations`` / ``legs`` / ``lifecycle`` cannot hide an
    operation between them **because there is one key**, and this is what says so.

    Also the guard on a FOURTH key: add one to ``Surface``'s serialization and this reddens,
    because the side that finds it is duck-typed off the emitted dict rather than off the
    field list the emission is built from.
    """
    caps = larkdocio.capabilities(full=True)
    for sid, surface in caps["surfaces"].items():
        assert set(_op_shaped_keys(surface)) == {CALL_SITES_KEY}, (
            f"{sid} publishes call-site rows outside {CALL_SITES_KEY!r}: "
            f"{sorted(set(_op_shaped_keys(surface)) - {CALL_SITES_KEY})} — a consumer reading "
            f"the one key would miss them, which is the 1.33.0 defect in a new key")


def test_every_row_SAYS_WHICH_KIND_of_call_it_is():
    """The distinction the three keys carried by POSITION is carried by the row instead, so it
    travels with a row a consumer copied out — and it is derived from the authoring field the
    row came from, independently of the serialization being checked."""
    caps = larkdocio.capabilities(full=True)
    typed = _build().surfaces
    for sid, surface in caps["surfaces"].items():
        expected = [(op.name, kind) for kind, op in typed[sid].call_sites()]
        assert [(row["name"], row["kind"]) for row in surface[CALL_SITES_KEY]] == expected, sid
        for row in surface[CALL_SITES_KEY]:
            assert row["kind"] in CALL_KINDS, (sid, row["name"], row["kind"])


def test_the_permission_registry_derives_from_the_published_ANSWER():
    """AC1's 'so a new op joins both without anyone remembering': one enumeration feeds the
    consumer's answer AND the permission rows, rather than two hand-kept key lists."""
    caps = larkdocio.capabilities(full=True)
    registry = perm.permission_registry()
    for sid, surface in caps["surfaces"].items():
        for row in surface[CALL_SITES_KEY]:
            assert (sid, row["name"]) in registry, (sid, row["name"])
            assert registry[(sid, row["name"])].kind == row["kind"]


# --------------------------------------------------------------------------- #
# AC3/AC4 — the audit gains the direction that was broken, and it BITES.       #
# --------------------------------------------------------------------------- #

def _surface(**keys):
    surface = {"title": "t", "domain": "docx", "mode": "read"}
    surface.update(keys)
    return surface


def _op(name, kind="operation"):
    return {"name": name, "kind": kind, "projected_from": "larkdocio.x", "permissions": {}}


def test_the_projection_direction_greens_on_the_shipped_tree():
    assert perm.projection_gaps() == ([], [])


def test_the_projection_direction_bites_on_the_PRE_FIX_SHAPE():
    """AC4, the acceptance evidence, unchanged in force: the shape that shipped through 1.33 —
    call sites under ``legs`` / ``lifecycle`` beside the key a consumer is pointed at —
    REDDENS. It is the same specimen it always was; what changed is that the answer it is
    measured against is the one key rather than an index."""
    surfaces = {"docx-write": _surface(
        operations=[_op("insert")],
        legs=[_op("put_image_in_document", "leg")],
        lifecycle=[_op("create_document", "lifecycle")],
    )}
    unprojected, phantom = perm.projection_gaps(surfaces)
    assert unprojected == [("docx-write", "legs", "put_image_in_document"),
                           ("docx-write", "lifecycle", "create_document")]
    assert not phantom


def test_the_projection_direction_bites_on_a_ROW_A_CONSUMER_CANNOT_ACT_ON():
    """The other half of the direction: a row under the one key whose ``kind`` is missing or
    outside the published vocabulary. It is the successor of the phantom-index-row arm — the
    same failure ("a pointer a consumer cannot follow") in the shape the collapse leaves: the
    row is there, and nothing says what sort of call it is."""
    surfaces = {"docx-read": _surface(operations=[
        _op("get_docx_content"),
        _op("something_with_no_kind", None),
        _op("something_with_a_bogus_kind", "verb"),
    ])}
    unprojected, phantom = perm.projection_gaps(surfaces)
    assert phantom == [("docx-read", "operations", "something_with_a_bogus_kind"),
                       ("docx-read", "operations", "something_with_no_kind")]
    assert not unprojected


def test_coverage_gaps_SELF_REPORTS_the_projection_direction():
    """AC3 — one function, used by the live guard and by the tests that prove it bites. The
    projection direction is now one of ``coverage_gaps()``' own fields."""
    gaps = perm.coverage_gaps()
    assert (gaps.uncovered, gaps.orphans, gaps.unprojected, gaps.phantom) == ([], [], [], [])
    # TRANSFORMED, not deleted (LD-609 added the fifth direction this line predicted): the
    # REASON is unchanged — the answer is still a tuple, so a new direction is ADDITIVE and no
    # caller unpacking the first four breaks. What was wrong was stating that additivity as a
    # hard-coded arity, which is the one way of writing it that a fifth field falsifies.
    assert list(gaps) == [gaps.uncovered, gaps.orphans, gaps.unprojected, gaps.phantom,
                          gaps.undetermined], "still a tuple, in field order"
    assert list(gaps)[:4] == [[], [], [], []]

    broken = {"docx-write": _surface(
        operations=[_op("insert")], legs=[_op("put_image_in_document", "leg")])}
    biting = perm.coverage_gaps(surfaces=broken)
    assert biting.unprojected == [("docx-write", "legs", "put_image_in_document")]
