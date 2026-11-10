# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""LD-647 — the Base surface's DESTRUCTIVE-FENCE and FRONT-DOOR claims, held against the code.

The shipped ``base/__init__.py`` docstring is what ``help(larkdocio.base)`` prints, so it is
consumer-reaching text by the same argument that puts the README in the guarded corpus. Three
of its claims were measurably false:

* *"every delete behind a Base-wide loss preview and a consent token"* — **two of the surface's
  five** deletes are behind neither, one deliberately (``delete_base``, the fifth, which carries
  no descriptor and so appears in no registry) and one undeclared (``delete_view``);
* *"both halves of this surface are reached by importing ``larkdocio.base``"* — ``__all__``
  names **zero** write entry points, and the reach is a submodule import;
* ``larkdocio.base.apply`` resolving to the **module** while the sentence above it implies a
  function — an accident of ``__init__``'s transitive import list, published as if it were a
  surface.

**Why a guard and not a proofread.** Every one of those sentences was true when written and rotted
when the surface grew, and nothing looked. So each claim here is asserted against the thing it
describes — the three op registries, ``__all__``, and the live attribute namespace — and the
census below is derived from the registries rather than typed, which is what makes it survive the
next family that ships a delete.

**THE CENSUS IS THE LOAD-BEARING PART** (:func:`test_every_destructive_verb_op_is_DECLARED_or_REASONED`).
A negative claim — *"nothing else on this surface deletes unfenced"* — dies with its enumeration,
so the enumeration is computed from all three registries and every **gap** (a destructive-verb op
that ``destructive_ops()`` does not name) must appear in :data:`REASONED_GAPS` with a written
reason **and** ship that reason in the module a consumer reads. Bidirectional: a reason whose op
stopped being a gap reddens too, so the table cannot rot into a rubber stamp.
"""
import json
import re
import subprocess
import sys
import types

import pytest

from larkdocio.base import ops as read_ops
from larkdocio.base import schema_ops, write_ops
from larkdocio.base import schema_ops_views
from larkdocio.base.schema_client import LIFECYCLE_OPS

import larkdocio.base as base_pkg


#: A verb that can remove something. ``POST`` is on the list **only** through the
#: ``batch_delete`` endpoint spelling, because ``POST`` is also the verb the pinned record
#: *read* uses — the same reason ``mutates`` is declared and never inferred.
def _destroys_by_verb(descriptor):
    return (descriptor.http_method == "DELETE"
            or descriptor.endpoint.rstrip("/").endswith("batch_delete")
            or "delete" in descriptor.name)


def _census():
    """``{registry label: [(op name, verb, declared destructive?)]}`` — derived, never typed."""
    schema_fenced = schema_ops.destructive_ops()
    return {
        "read": [(d.name, d.http_method, d.name in schema_fenced)
                 for d in read_ops.OPS if _destroys_by_verb(d)],
        "record-write": [(d.name, d.http_method, d.name in schema_fenced)
                         for d in write_ops.WRITE_OPS if _destroys_by_verb(d)],
        "schema": [(d.name, d.http_method, d.name in schema_fenced)
                   for d in schema_ops.schema_ops() if _destroys_by_verb(d)],
    }


#: **Every destructive-verb op that ``destructive_ops()`` does NOT name, and why.** One row per
#: gap, keyed ``registry/op``; the value is the reason, and each is additionally asserted to ship
#: in the module a consumer reads (see the guard). A gap with no row here reddens; a row whose op
#: is now declared destructive reddens too.
REASONED_GAPS = {
    "record-write/delete_record": (
        "A DIFFERENT REGISTRY WITH ITS OWN FENCE. destructive_ops() unions the SCHEMA "
        "families' declarations, so a record op can never appear in it. A record delete is "
        "fenced by the record engine's mandatory dry_run and its per-record diff — every "
        "record that will be deleted is enumerated in the Plan before apply() will accept it — "
        "not by a consent token."
    ),
    "record-write/batch_delete_records": (
        "The batch form of the row above, same registry and same fence: the Plan enumerates "
        "each record and apply() takes a Plan and nothing else."
    ),
    "schema/delete_view": (
        "RULED, NOT OVERLOOKED: a view delete destroys CONFIGURATION and not one cell — the "
        "property the three fenced ops all share and it does not — so there is no loss to "
        "enumerate and nothing to consent to. It is still mutates=True, still plan-gated and "
        "still verified by read-back, and the server floors the last view in a table."
    ),
}

#: Where each reasoned gap's reason must be **shipped**, so a consumer meets it: the object whose
#: ``__doc__`` (or module docstring) has to carry the phrase.
REASON_SHIPS_IN = {
    "record-write/delete_record": schema_ops.destructive_ops,
    "record-write/batch_delete_records": schema_ops.destructive_ops,
    "schema/delete_view": schema_ops_views,
}


def _door():
    return base_pkg.__doc__


def _fence_doc():
    return schema_ops.destructive_ops.__doc__


# --------------------------------------------------------------------------- #
# THE CENSUS — AC6                                                             #
# --------------------------------------------------------------------------- #

def test_the_census_enumerator_is_not_VACUOUS():
    """A sweep whose enumerator quietly returned ``()`` would pass forever."""
    census = _census()
    assert census["read"] == [], (
        "the READ registry grew a destructive verb, which would falsify read_only()'s own "
        f"shipped answer: {census['read']}")
    assert read_ops.read_only() is True
    assert [name for name, _, _ in census["record-write"]] == [
        "delete_record", "batch_delete_records"]
    assert [name for name, _, _ in census["schema"]] == [
        "delete_view", "delete_field", "delete_table", "batch_delete_tables"]


def test_every_destructive_verb_op_is_DECLARED_or_REASONED():
    """The negative claim, with its enumeration attached — in both directions."""
    gaps = {f"{label}/{name}"
            for label, rows in _census().items()
            for name, _verb, declared in rows if not declared}
    assert gaps == set(REASONED_GAPS), (
        "a destructive-verb op is outside destructive_ops() with no written reason (or a "
        f"written reason outlived its gap). unreasoned={sorted(gaps - set(REASONED_GAPS))} "
        f"stale={sorted(set(REASONED_GAPS) - gaps)}")


@pytest.mark.parametrize("key", sorted(REASONED_GAPS))
def test_every_reasoned_gap_SHIPS_its_reason_where_a_consumer_reads_it(key):
    """A reason that lives only in this test file is a reason the consumer never receives."""
    text = REASON_SHIPS_IN[key].__doc__ or ""
    op = key.split("/", 1)[1]
    assert op in text, f"{key}: the reason is not shipped in {REASON_SHIPS_IN[key]!r}"


def test_delete_base_is_the_FIFTH_delete_and_is_in_NEITHER_enumeration_by_design():
    """It is not in the census at all — it has no descriptor — so it is asserted separately."""
    assert LIFECYCLE_OPS == ("delete_base",)
    assert "delete_base" not in {d.name for d in schema_ops.schema_ops()}
    assert "delete_base" not in schema_ops.destructive_ops()


# --------------------------------------------------------------------------- #
# THE SHIPPED FENCE SENTENCE — AC1 + AC2                                       #
# --------------------------------------------------------------------------- #

def test_the_front_door_no_longer_claims_EVERY_DELETE_is_fenced():
    assert "every delete behind" not in _door(), (
        "the unqualified claim is back: two of the four deletes on this surface are behind "
        "neither a loss preview nor a consent token")


def test_the_front_door_names_the_THREE_FENCED_OPS_and_they_are_the_ones_returned():
    door = _door()
    for name in sorted(schema_ops.destructive_ops()):
        assert f"``{name}``" in door, f"{name} is fenced and the front door does not name it"


@pytest.mark.parametrize("exception", ["delete_view", "delete_base"])
def test_the_front_door_names_each_UNFENCED_delete_as_the_deliberate_exception_it_is(exception):
    door = _door()
    assert f"``{exception}``" in door
    assert "deliberately" in door


def test_the_front_door_cites_WHERE_delete_bases_exclusion_IS_ARGUED_and_does_not_repair_it():
    """AC1's fence: named as the deliberate exception, citing the argument — never 'fixed'."""
    assert "LIFECYCLE_OPS" in _door()
    assert "delete_base" not in schema_ops.destructive_ops()


def test_the_VIEW_FAMILY_ships_the_sentence_saying_why_its_delete_is_UNFENCED():
    """AC2's ruled branch: the reason ships in the family module, and the ruling is a
    docs-and-precedent one — ``DESTRUCTIVE_OPS`` stays empty here."""
    text = schema_ops_views.__doc__
    assert "delete_view" in text
    assert "configuration" in text
    assert schema_ops_views.DESTRUCTIVE_OPS == frozenset(), (
        "the view family declares an EMPTY destructive set on purpose — silence was the "
        "defect, and an empty declaration is the statement")
    assert "delete_view" not in schema_ops.destructive_ops()


def test_the_view_family_leaves_a_PRECEDENT_for_the_next_family_that_ships_a_delete():
    assert "DESTRUCTIVE_OPS" in schema_ops_views.__doc__


# --------------------------------------------------------------------------- #
# destructive_ops()'s OWN docstring — AC5                                      #
# --------------------------------------------------------------------------- #

def test_destructive_ops_says_what_it_does_NOT_cover():
    doc = _fence_doc()
    for owed in ("delete_view", "delete_record", "delete_base", "destructive_shapes"):
        assert owed in doc, (
            f"destructive_ops' docstring sits next to FAMILY_MODULES' 'A MISSING LINE HERE IS "
            f"A SAFETY HOLE' warning and does not say that {owed} is outside its scope")


# --------------------------------------------------------------------------- #
# THE REACH — AC3                                                              #
# --------------------------------------------------------------------------- #

#: The write-engine entry points the old sentence implied were importable off this package.
WRITE_ENTRY_POINTS = (
    "dry_run", "apply", "schema_dry_run", "schema_apply", "consent_to_destroy",
    "snapshot_table", "snapshot_base", "BaseWriteClient", "BaseSchemaClient",
)


def test_the_reach_sentence_is_TRUE_ZERO_write_entry_points_are_exported():
    assert [n for n in WRITE_ENTRY_POINTS if n in base_pkg.__all__] == []
    assert "both halves of this surface are reached by importing" not in _door(), (
        "the sentence whose truth depended on an accident of the import list is back")


#: Every ``from larkdocio.base.<mod> import …`` the front door prints, **read out of the door
#: itself** rather than hand-listed. The hand-listed version is what let one printed path ship
#: unexecuted: the docstring named five and the guard ran four, and the fifth was the one whose
#: execution would have broken the sibling arm below. Deriving it means a SIXTH printed path
#: reddens instead of joining it.
_PRINTED_REACH_RE = re.compile(r"from (larkdocio\.base\.\w+) import")

#: The modules :func:`test_the_front_door_describes_the_REAL_reach_and_every_path_it_prints_IMPORTS`
#: actually imports. Held equal to what the door prints, in both directions.
EXECUTED_REACH_MODULES = frozenset({
    "larkdocio.base.apply",
    "larkdocio.base.schema_apply",
    "larkdocio.base.write_client",
    "larkdocio.base.schema_client",
    "larkdocio.base.view_plan",
})


def test_the_front_door_describes_the_REAL_reach_and_every_path_it_prints_IMPORTS():
    """The route the door documents is the submodule import — and **every** path it prints is
    executed here, so the door cannot document one that does not resolve.

    ``view_plan`` is executed too, which it was not before. It could not be while the sibling
    negative arm was measured **in-process**: importing it here would have made
    ``hasattr(larkdocio.base, 'view_plan')`` true for the rest of the session and killed that
    arm. Both halves were one weakness, and moving the negative half into a **cold interpreter**
    (:data:`_COLD_REACHABILITY_PROBE`) is what freed this one to run whole.
    """
    door = _door()
    printed = frozenset(_PRINTED_REACH_RE.findall(door))
    assert printed == EXECUTED_REACH_MODULES, (
        "the door prints a submodule reach path this guard does not execute, or executes one it "
        f"no longer prints. printed_only={sorted(printed - EXECUTED_REACH_MODULES)} "
        f"executed_only={sorted(EXECUTED_REACH_MODULES - printed)}")
    assert "from larkdocio.base.apply import dry_run, apply" in door

    from larkdocio.base.apply import apply, dry_run           # noqa: F401
    from larkdocio.base.schema_apply import (                 # noqa: F401
        consent_to_destroy, schema_apply, schema_dry_run)
    from larkdocio.base.schema_client import BaseSchemaClient  # noqa: F401
    from larkdocio.base.write_client import BaseWriteClient    # noqa: F401
    from larkdocio.base.view_plan import delete_view           # noqa: F401


# --------------------------------------------------------------------------- #
# THE ACCIDENTAL ATTRIBUTE REACHABILITY — AC4                                  #
# --------------------------------------------------------------------------- #

def test_larkdocio_base_apply_is_the_MODULE_and_the_door_says_so():
    assert isinstance(base_pkg.apply, types.ModuleType)
    assert "is the **module**" in _door()
    from larkdocio.base.apply import apply as apply_fn
    assert callable(apply_fn)


def test_the_door_discloses_that_attribute_ACCESS_is_not_the_contract():
    door = _door()
    assert "not a contract" in door
    assert "view_plan" in door, (
        "the disclosure names the submodule that does NOT resolve off this namespace, which is "
        "what makes the accident visible rather than described")


#: **THE COLD PROBE, and why it is a subprocess.** This arm asserts a NEGATIVE about
#: ``sys.modules`` — that importing ``larkdocio.base`` alone leaves ``view_plan`` unreachable —
#: and ``sys.modules`` is shared by the whole test session. **Eight** test modules import
#: ``larkdocio.base.view_plan`` at module scope, and both pytest and xdist import every selected
#: module at COLLECTION, so in a canonical run the name is always already there. Measured in
#: place of assumed: this file alone gave ``19 passed, 0 skipped``; this file plus
#: ``tests/test_base_schema_views.py`` gave ``65 passed, 1 skipped`` — the arm was dead in 100%
#: of real runs, in the shape that reads like a pass. A ``pytest.skip`` was the wrong answer for
#: exactly the reason this whole guard exists: **a guard that goes quiet has stopped guarding**,
#: and this one announced its own diligence ("measured, not asserted") while measuring nothing.
#:
#: A fresh interpreter has a clean ``sys.modules``, so the answer is deterministic and the arm
#: **fails** — never skips — when it cannot establish it. It proves three things at once, in the
#: one order where they are meaningful: unreachable BEFORE, the fifth printed path IMPORTS, and
#: reachable AFTER, which is the accident itself demonstrated rather than described.
_COLD_REACHABILITY_PROBE = """
import json
import larkdocio.base as b
before = hasattr(b, "view_plan")
from larkdocio.base.view_plan import delete_view
after = hasattr(b, "view_plan")
print(json.dumps({
    "reachable_before_importing_it_by_name": before,
    "the_fifth_printed_path_imports": callable(delete_view),
    "reachable_after_importing_it_by_name": after,
}))
"""


def test_the_named_NON_reachable_submodule_really_is_unreachable_IN_A_COLD_INTERPRETER():
    """The disclosure is **measured**, in the only process where the measurement means anything.

    No skip branch exists on purpose: an arm that cannot establish its answer must fail, and a
    non-zero return code or unparseable output is a failure here, not a shrug.
    """
    proc = subprocess.run([sys.executable, "-c", _COLD_REACHABILITY_PROBE],
                          capture_output=True, text=True)
    assert proc.returncode == 0, (
        "the cold reachability probe did not run, so nothing was measured — that is a FAILURE "
        f"of this guard, never a skip:\n{proc.stderr[-3000:]}")
    assert proc.stdout.strip(), f"the probe printed nothing:\n{proc.stderr[-3000:]}"
    assert json.loads(proc.stdout) == {
        "reachable_before_importing_it_by_name": False,
        "the_fifth_printed_path_imports": True,
        "reachable_after_importing_it_by_name": True,
    }, proc.stdout


def test_this_SESSION_is_exactly_the_contamination_the_cold_probe_exists_for():
    """The probe's own non-vacuity, asserted from the other side.

    If ``view_plan`` were somehow NOT in this session's ``sys.modules``, the subprocess above
    would be ceremony and an in-process assertion would have done. It is there — the sibling
    reach guard imports it, and eight other modules do at import time — so this records the
    reason the cold interpreter is not optional.
    """
    __import__("larkdocio.base.view_plan")
    assert "larkdocio.base.view_plan" in sys.modules
    assert hasattr(base_pkg, "view_plan"), (
        "importing the submodule by name is what makes the attribute appear; if this is false "
        "the accident being disclosed has changed shape")
