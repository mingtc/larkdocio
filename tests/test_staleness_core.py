"""LD-143 (T1) — ONE staleness-marker core: ``larkdocio.common.staleness``.

**The smell this closes.** The never-silent guard vocabulary was duplicated across the two
write surfaces — ``write/revision.py`` and ``sheets/plan.py`` (whose own docstring said
"mirrored from") each defined the two markers **and** their own ``revision_guard_status()``
— and the copies had **already drifted**: docx classified a **negative / negative-string**
anchor ``unavailable`` (the ``document_revision_id=-1`` "against latest" trap), sheets
classified the same value ``active``. Base is next on the roadmap and would have been copy #3.

**What this file pins.**

* The **one** core — two markers + one :func:`revision_guard_status` — lives in the shared
  leaf ``larkdocio.common.staleness``, and BOTH surfaces **re-export the identical objects**
  (identity, not merely equal values). No public path moved: every existing import path still
  resolves (the LD-061 / LD-126 shim precedent).
* Neither surface holds a **second definition** — the anti-redrift pin. A future copy pasted
  back into either module reddens here, structurally (AST), before it can drift.
* The **union of both surfaces' matrices** classifies identically through the one function,
  under the **adopted (docx / stricter) rule**: a negative or negative-string anchor is
  ``unavailable`` on **both** surfaces now.
* The reclassification **cannot weaken a guard.** On sheets the marker is *disclosure only* —
  enforcement is the independent ``live != expected`` compare in ``sheets/ops/`` — so a
  negative-anchor plan, now marked ``unavailable``, **still refuses ``STALE_SHEET`` with zero
  writes** when the live revision drifts, and still applies when it does not. That is the
  whole safety argument for adopting the stricter rule, and it is a test, not a claim.
* Each surface **keeps its own** ``revision_guard_semantics()`` — the detail wording is
  surface-specific and sheets adds its ``tiers`` key. Only the **status classification**
  unified; the semantics deliberately did not.
"""
import ast
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio.common import staleness as core
from larkdocio.sheets import plan as sheets_plan
from larkdocio.sheets.write_apply import Refusal, apply, dry_run
apply = reading_the_log(apply)
from larkdocio.write import revision as docx_revision

# The sheets engine harness — reused verbatim so the enforcement pin below exercises the
# REAL apply path (registry dispatch + the live compare), not a re-implementation of it.
from test_revision_guard_never_silent import TOKEN, _gw, _value_req

_SRC = Path(__file__).resolve().parents[1] / "src" / "larkdocio"
_CORE_PATH = _SRC / "common" / "staleness.py"
_SURFACE_PATHS = (_SRC / "write" / "revision.py", _SRC / "sheets" / "plan.py")


# --------------------------------------------------------------------------- #
# The union matrix — the ADOPTED (docx / strict) rule, through the ONE function. #
# --------------------------------------------------------------------------- #

#: The union of the docx matrix (``[None, 0, "0", "", "   ", -1, -155]`` —
#: ``test_stale_document_guard.py``) and the sheets matrix (``[0, None, "0", " 0 ", ""]`` —
#: ``test_revision_guard_never_silent.py``), plus the negative-string and non-comparable
#: shapes an API drift could hand back. Every one of these is an anchor a compare cannot
#: honestly use, so it is disclosed as unavailable rather than *treated* as healthy just
#: because it compares unequal to a later value.
UNAVAILABLE_UNION = (
    None, 0, "0", "", "   ", " 0 ", 0.0,        # both surfaces already agreed
    -1, -155, "-1", " -155 ", -0.5,             # RECLASSIFIED on sheets by LD-143
    [],                                          # an exotic anchor — the honest fallback
)

#: The union of both surfaces' "healthy anchor" rows. ``"abc"`` is the documented
#: opaque-but-comparable token: not numeric, but an equality compare against it still
#: observes an advance, so it stays active.
ACTIVE_UNION = (1, 37, 155, 9999, "37", "155", " 155 ", "abc")

#: The three call paths that must give the same answer: the core, and both re-exports.
_STATUS_PATHS = ("core", "docx", "sheets")


def _status(path, revision):
    fn = {"core": core.revision_guard_status,
          "docx": docx_revision.revision_guard_status,
          "sheets": sheets_plan.revision_guard_status}[path]
    return fn(revision)


@pytest.mark.parametrize("path", _STATUS_PATHS)
@pytest.mark.parametrize("revision", UNAVAILABLE_UNION, ids=repr)
def test_the_union_matrix_classifies_every_unusable_anchor_unavailable(path, revision):
    """B1 — the union of BOTH matrices against the ONE function, from all three paths."""
    assert _status(path, revision) == core.REVISION_GUARD_UNAVAILABLE


@pytest.mark.parametrize("path", _STATUS_PATHS)
@pytest.mark.parametrize("revision", ACTIVE_UNION, ids=repr)
def test_the_union_matrix_classifies_every_usable_anchor_active(path, revision):
    assert _status(path, revision) == core.REVISION_GUARD_ACTIVE


@pytest.mark.parametrize("revision", UNAVAILABLE_UNION + ACTIVE_UNION, ids=repr)
def test_both_surfaces_classify_the_union_identically(revision):
    """The drift is closed by construction: the two surfaces cannot disagree about any
    anchor shape, because there is only one classifier left."""
    assert (docx_revision.revision_guard_status(revision)
            == sheets_plan.revision_guard_status(revision)
            == core.revision_guard_status(revision))


def test_the_adopted_rule_is_the_stricter_docx_one_not_the_sheets_one():
    """The policy decision, stated as a test: a negative anchor — the
    ``document_revision_id=-1`` "against latest" trap — is UNAVAILABLE on **both** surfaces.
    Sheets used to call it ``active``; that is the one consumer-visible reclassification."""
    for negative in (-1, "-1"):
        assert sheets_plan.revision_guard_status(negative) == core.REVISION_GUARD_UNAVAILABLE
        assert docx_revision.revision_guard_status(negative) == core.REVISION_GUARD_UNAVAILABLE


# --------------------------------------------------------------------------- #
# B2 — both surfaces re-export the SAME objects (identity), and neither holds   #
# a second definition (the anti-redrift pin).                                   #
# --------------------------------------------------------------------------- #

def test_the_core_exports_the_two_markers_and_the_one_status_function():
    assert core.REVISION_GUARD_ACTIVE == "active"
    assert core.REVISION_GUARD_UNAVAILABLE == "unavailable"
    assert callable(core.revision_guard_status)


def test_both_surfaces_reexport_the_identical_core_objects():
    """B2 — identity, not merely equal values (the LD-061 shim precedent's own assertion
    shape in ``test_common_core.py``). One function object, reached by three paths."""
    for surface in (docx_revision, sheets_plan):
        assert surface.revision_guard_status is core.revision_guard_status
        assert surface.REVISION_GUARD_ACTIVE is core.REVISION_GUARD_ACTIVE
        assert surface.REVISION_GUARD_UNAVAILABLE is core.REVISION_GUARD_UNAVAILABLE


def test_the_shared_primitives_are_importable_off_the_common_package():
    """The ``larkdocio.common`` docstring promises the shared primitives straight off the
    package — a new shared primitive that skipped it would make that docstring a lie."""
    from larkdocio.common import (
        REVISION_GUARD_ACTIVE,
        REVISION_GUARD_UNAVAILABLE,
        revision_guard_status,
    )

    assert revision_guard_status is core.revision_guard_status
    assert REVISION_GUARD_ACTIVE is core.REVISION_GUARD_ACTIVE
    assert REVISION_GUARD_UNAVAILABLE is core.REVISION_GUARD_UNAVAILABLE


def test_the_public_import_paths_still_resolve_unchanged():
    """B5 — no public path moved. The three paths a consumer (or a wheel-vendoring
    downstream) may already import from keep working, unchanged."""
    from larkdocio.sheets.plan import revision_guard_status as from_sheets_plan
    from larkdocio.sheets.write_apply import revision_guard_status as from_write_apply
    from larkdocio.write import revision_guard_status as from_write_pkg
    from larkdocio.write.revision import revision_guard_status as from_revision

    assert (from_revision is from_write_pkg is from_sheets_plan is from_write_apply
            is core.revision_guard_status)


@pytest.mark.parametrize("path", _SURFACE_PATHS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_neither_surface_defines_a_second_copy_of_the_marker_vocabulary(path):
    """THE anti-redrift pin, structural. A copy pasted back into either surface — a marker
    re-assigned or ``revision_guard_status`` re-defined locally — reddens here **before** it
    can drift, which is exactly how this duplication got in."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assigned, defined = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            assigned |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(node.name)

    assert "REVISION_GUARD_ACTIVE" not in assigned, f"{path.name} re-assigns the marker"
    assert "REVISION_GUARD_UNAVAILABLE" not in assigned, f"{path.name} re-assigns the marker"
    assert "revision_guard_status" not in defined, (
        f"{path.name} defines a SECOND revision_guard_status — the classification lives in "
        f"larkdocio/common/staleness.py exactly once (LD-143)")


def test_the_core_is_a_leaf_importing_only_the_standard_library():
    """The vocabulary stays dumb and dependency-free (the ``write/revision.py`` doctrine,
    inherited): a leaf both surfaces can import with no cycle and no SDK."""
    import sys

    tree = ast.parse(_CORE_PATH.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
    assert roots <= set(sys.stdlib_module_names), roots


# --------------------------------------------------------------------------- #
# B4 — each surface KEEPS its own semantics(); only the status unified.          #
# --------------------------------------------------------------------------- #

def test_each_surface_keeps_its_own_semantics_function():
    """Deliberately NOT unified (audit § T1, and the audit's rejected candidate list): the
    detail wording is surface-specific and sheets carries a ``tiers`` key. Two functions,
    one classifier."""
    assert docx_revision.revision_guard_semantics is not sheets_plan.revision_guard_semantics
    assert not hasattr(core, "revision_guard_semantics"), (
        "the core owns the CLASSIFICATION only — sharing the disclosure wording would erase "
        "the per-surface story the never-silent contract is made of")

    docx = docx_revision.revision_guard_semantics(0)
    sheets = sheets_plan.revision_guard_semantics(0)

    assert set(docx) == {"status", "detail"}
    assert set(sheets) == {"status", "detail", "tiers"}
    assert "document_revision_id" in docx["detail"]        # the docx knob
    assert "tier 2" in sheets["detail"]                    # the sheets two-tier story


@pytest.mark.parametrize("revision", UNAVAILABLE_UNION + ACTIVE_UNION, ids=repr)
def test_both_surfaces_semantics_report_the_shared_status(revision):
    """The disclosure a consumer reads is derived from the one classifier on both surfaces —
    a surface cannot state a status the core would not agree with."""
    expected = core.revision_guard_status(revision)
    assert docx_revision.revision_guard_semantics(revision)["status"] == expected
    assert sheets_plan.revision_guard_semantics(revision)["status"] == expected
    assert sheets_plan.revision_guard_semantics(revision)["tiers"][
        "tier1_revision_compare_and_swap"] == expected


# --------------------------------------------------------------------------- #
# B3 — the sheets reclassification CANNOT WEAKEN a guard.                       #
# The marker is disclosure; enforcement is the independent live-compare.         #
# --------------------------------------------------------------------------- #

def test_a_negative_anchor_sheets_plan_marks_unavailable_and_still_refuses_on_drift():
    """The safety argument, end to end: the negative anchor is now disclosed
    ``unavailable`` (the reclassification) **and** the independent ``live != expected``
    compare still refuses ``STALE_SHEET`` with ZERO writes when the revision drifts."""
    gw = _gw(revision=-7)
    plan = dry_run([_value_req()], gw, TOKEN)
    assert plan.revision_guard == core.REVISION_GUARD_UNAVAILABLE      # reclassified
    gw.external_bumps = {gw._rev_reads + 1: 1}                         # -7 → -6

    log = apply(plan, gw)

    assert gw.puts == [], "the live-compare must still refuse — no write"
    (entry,) = log.entries
    assert entry.outcome == "stale"
    assert entry.refusal.reason == Refusal.STALE_SHEET


@pytest.mark.parametrize("revision", [-7, 37], ids=["reclassified-negative", "active"])
def test_the_live_compare_refuses_drift_identically_whatever_the_marker_says(revision):
    """Enforcement does not read the marker on sheets (``ops._apply_one`` compares
    ``live != expected`` unconditionally), so the refusal is byte-for-byte the same story
    for an anchor the marker calls ``unavailable`` and one it calls ``active``."""
    gw = _gw(revision=revision)
    plan = dry_run([_value_req()], gw, TOKEN)
    gw.external_bumps = {gw._rev_reads + 1: 1}

    log = apply(plan, gw)

    assert gw.puts == []
    assert log.entries[0].refusal.reason == Refusal.STALE_SHEET
    assert f"{revision} -> {revision + 1}" in log.entries[0].refusal.detail


def test_the_sheets_apply_path_never_BRANCHES_on_the_marker_only_docx_does():
    """The safety argument, structurally — and the reason adopting the stricter rule cannot
    weaken sheets: the sheets apply path reads ``revision_guard`` **only** to stamp it onto
    log entries, never to decide anything. Enforcement is the unconditional
    ``live != expected`` compare. On **docx** the same marker deliberately DOES gate the
    whole-document CAS (``write/apply.py``), which is why ``-1 → unavailable`` matters there.
    A future edit that made the sheets engine skip its compare when the marker is
    ``unavailable`` would redden here — that edit is the one thing this reclassification must
    never enable."""
    marker_names = {"revision_guard", "REVISION_GUARD_ACTIVE", "REVISION_GUARD_UNAVAILABLE"}

    def _branch_tests(path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found = {}      # keyed by source position, so one `if <compare>` counts ONCE
        for node in ast.walk(tree):
            tests = []
            if isinstance(node, (ast.If, ast.IfExp, ast.While)):
                tests = [node.test]
            elif isinstance(node, ast.Compare):
                tests = [node]
            for t in tests:
                names = {n.id for n in ast.walk(t) if isinstance(n, ast.Name)}
                names |= {n.attr for n in ast.walk(t) if isinstance(n, ast.Attribute)}
                if names & marker_names:
                    found[(t.lineno, t.col_offset, t.end_col_offset)] = ast.unparse(t)
        return [found[k] for k in sorted(found)]

    sheets_dir = _SRC / "sheets"
    # ``ops.py`` became the ``ops/`` package at LD-532 (one module per op family), so the scan
    # is DERIVED from the tree: the apply legs that must not branch on the marker now live in
    # the family modules, and a family module added tomorrow is scanned on its own.
    scanned = [sheets_dir / "write_apply.py"] + sorted(
        p for p in (sheets_dir / "ops").rglob("*.py") if "__pycache__" not in p.parts)
    for path in scanned:
        assert _branch_tests(path) == [], (
            f"{path.name} branches on the staleness MARKER — on sheets it is disclosure "
            f"only; enforcement must stay the unconditional live != expected compare")

    # The deliberate asymmetry, asserted so this file cannot be read as "the marker never
    # gates anything anywhere": on docx it gates the CAS, exactly once.
    docx_branches = _branch_tests(_SRC / "write" / "apply.py")
    assert len(docx_branches) == 1, docx_branches
    assert "revision_guard" in docx_branches[0]


def test_a_negative_anchor_that_does_not_drift_still_applies():
    """The other half of "cannot weaken": the reclassification is a disclosure change, not a
    blanket refusal — a negative-anchor plan whose sheet did not move still writes."""
    gw = _gw(revision=-7)

    log = apply(dry_run([_value_req()], gw, TOKEN), gw)

    assert log.entries[0].is_applied
    assert gw.puts
