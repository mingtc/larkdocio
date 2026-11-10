"""LD-223 — the ``VerificationLeg`` seam, the ruled ``"leg"`` → ``"verified_by"`` rename, and
the ``post_revision`` consolidation that must NOT move a single API call.

Two jobs, deliberately in one file because they guard each other:

**The characterization half (AC6 / B1 / B3).** ``sheets/ops.py`` stamped *"which leg verified
this write, and the caveat that goes with it"* at four sites, each with its own hand-written
key/note pair. Unifying them behind one value object is a pure restructure — so the four
families' apply-log payloads are pinned here **byte-exactly** (key ORDER, the leg value, and a
SHA-256 of the caveat prose) at the ``refactor-baseline-2026-08-01-LD-223`` tag, **before** any
move. Every pin in this half was green at the baseline and must stay green after; a diff here
is a bug in the move, not a fixture to update.

**The read-count half (AC7 / B3).** The nine ``post_revision`` endings collapse behind one
helper — and the audit's framing of them as *"eight identical fallbacks"* is **wrong**. There
are three shapes, and two of them are load-bearing:

* **Shape A** (7 sites) — ``_revision_of(reply)``, falling back to a ``metainfo``
  ``read_revision``. The control.
* **Shape B** (the FREEZE leg) — falls back to the ``read_frozen_panes`` result **already in
  hand**. Flattening it into Shape A would add a NETWORK READ per freeze. The pin below fixes
  the freeze leg's whole ordered call journal, so that flattening reddens.
* **Shape C** (the STYLE leg) — its primary extractor is ``_style_reply_revision``, which digs
  the revision out of the reply's ``updates`` envelope. Dropping back to the flat
  ``_revision_of`` would also add a network read. Pinned the same way.

The doubles are the families' own counting gateways, imported rather than re-declared: a
second copy of a gateway is a second definition of the surface, which is the defect this
tranche is removing elsewhere.
"""
import hashlib

import pytest

from larkdocio.sheets import ops as O
from larkdocio.sheets.requests import (
    CellStyle,
    FreezePanes,
    RetitleTab,
    SetRowProperties,
    StyleWriteRequest,
)
from larkdocio.sheets.write_apply import apply, dry_run

import test_sheets_dimension_properties as DIM
import test_sheets_freeze_panes as FRZ
import test_sheets_style_write as STY
import test_sheets_tab_presentation as TAB


def _sha(text):
    """A digest, not a paste: the caveat prose is 650–950 characters per family, and the point
    of the pin is that **no byte** of it moved, not that a reviewer re-reads it here."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# The four legs, driven end to end through their own family's gateway.          #
# Each returns (ordered call journal, the apply log's structural record).        #
# --------------------------------------------------------------------------- #

def _dimension_leg():
    gw = DIM.FakeDimensionGateway()
    log = apply(dry_run([SetRowProperties(DIM.SID, 2, 3, fixed_size=60)], gw, DIM.TOKEN), gw)
    return [c[0] for c in gw.calls], log.entries[0].structural


def _freeze_leg():
    gw = FRZ.FreezeGateway()
    log = apply(dry_run([FreezePanes(FRZ.SID, rows=2)], gw, FRZ.TOKEN), gw)
    return gw.api_calls(), log.entries[0].structural


def _tab_leg():
    gw = TAB.TabGateway()
    log = apply(TAB._plan([RetitleTab(TAB.SID, "Beta-2")], gw), gw)
    return [c[0] for c in gw.calls], log.entries[0].structural


def _style_leg():
    gw = STY.FakeStyleGateway()
    plan = dry_run([StyleWriteRequest(f"{STY.SID}!A1:A1", CellStyle(bold=True))], gw, STY.TOKEN)
    log = apply(plan, gw)
    return [c[0] for c in gw.calls], log.entries[0].structural


#: family → (driver, the record's key order, the leg id, the SHA-256 of the caveat prose).
#: Captured at ``refactor-baseline-2026-08-01-LD-223`` on ``develop``.
BASELINE = {
    "dimension": (
        _dimension_leg,
        ("op", "sheet_id", "major_dimension", "start_index", "end_index", "convention",
         "properties", "expected_count", "hides", "semantic", "reply", "preview",
         "verified_by", "verification_note"),
        "xlsx-export-dimension-leg",
        "11c53fef3cdb4898a68446ef4cdfc55d1e0d0acdbf7d86039b19e2b7ac4222e2",
    ),
    "freeze": (
        _freeze_leg,
        ("op", "sheet_id", "rows", "cols", "request_element", "unfreezes", "semantic",
         "frozen_before", "reply", "preview", "observed",
         "verified_by", "verification_note"),
        "metainfo-frozen-leg",
        "051839d5345ef3c1af1402196ed9006d0a84f054b1401fd4113465b52be2ce2d",
    ),
    "tab": (
        _tab_leg,
        ("op", "sheet_id", "request_element", "semantic", "title", "tab_before", "reply",
         "new_sheet_id", "preview", "observed", "observation_note",
         "verified_by", "verification_note"),
        "v3-tab-query-leg",
        "32d55b5ffc535ca164de9242a7dfd8865eebf8e68dc1ef1179fe0aefacd6b652",
    ),
    "style": (
        _style_leg,
        ("op", "batch", "sheet_id", "ranges", "spans", "style", "semantic", "reply",
         "preview", "verified_by", "verification_note"),
        "xlsx-export-style-leg",
        "04eb75bea28baabd76db9379ac2d6be25ad6177fb37039d36697d89480982d0f",
    ),
}


# =========================================================================== #
# AC6 / B1 — THE APPLY-LOG PAYLOAD IS BYTE-IDENTICAL ACROSS THE MOVE.           #
# =========================================================================== #

@pytest.mark.parametrize("family", sorted(BASELINE))
def test_the_apply_log_key_ORDER_is_unchanged_by_the_seam(family):
    """Not just "the keys are there" — the **order** they were inserted in.

    A seam that stamps the attribution by rebuilding the dict, or that stamps it before the
    family's own fields, produces a differently-ordered payload. That is observable to a
    consumer who serialises the log (``json.dumps`` preserves insertion order), so it is a
    behavior change and is refused here.
    """
    _driver, expected_keys, _leg, _note_sha = BASELINE[family]
    _calls, record = BASELINE[family][0]()
    assert tuple(record.keys()) == expected_keys, family


@pytest.mark.parametrize("family", sorted(BASELINE))
def test_the_leg_VALUE_and_the_caveat_PROSE_are_unchanged_by_the_seam(family):
    """B4: only the *key* changes in this issue, and only at the two style PREVIEW-note sites.
    The four leg ids and all four caveat texts are byte-frozen."""
    _driver, _keys, expected_leg, expected_note_sha = BASELINE[family]
    _calls, record = BASELINE[family][0]()
    assert record["verified_by"] == expected_leg, family
    assert _sha(record["verification_note"]) == expected_note_sha, (
        f"{family}: the caveat prose moved — a refactor may not rewrite a disclosure"
    )


@pytest.mark.parametrize("family", sorted(BASELINE))
def test_every_family_stamps_BOTH_halves_of_the_attribution(family):
    """The whole point of the seam: a family can no longer record *which* leg without the
    caveat that goes with it, because one object carries both."""
    _calls, record = BASELINE[family][0]()
    assert record["verified_by"] and record["verification_note"]
    # the two are adjacent and last — the stamp is applied as one act, after the family's
    # own fields, exactly as the four hand-written pairs did.
    assert tuple(record.keys())[-2:] == ("verified_by", "verification_note"), family


# =========================================================================== #
# AC7 / B3 — THE THREE `post_revision` SHAPES SURVIVE THE CONSOLIDATION.        #
#                                                                              #
# The whole ordered call journal is pinned, so an ADDED read reddens by name    #
# and by position rather than by a count that could be rebalanced elsewhere.    #
# =========================================================================== #

#: The FREEZE leg (Shape B) — note what is NOT here: a `read_revision` AFTER the write. The
#: fallback reuses the `read_frozen_panes` result already in hand, so the leg spends its
#: verification read and its compare-and-swap anchor on ONE call.
FREEZE_JOURNAL = ["read_revision", "read_frozen_panes", "read_revision",
                  "batch_update_sheets", "read_frozen_panes"]

#: The STYLE leg (Shape C) — the journal ENDS at the write: `_style_reply_revision` finds the
#: revision nested in the reply's `updates` envelope, so no `metainfo` read is owed at all.
STYLE_JOURNAL = ["read_revision", "read_sheet_geometry", "read_revision", "put_style"]

#: The DIMENSION leg (Shape A) — the control. Its reply carries no revision, so the fallback
#: DOES fire and the journal ends with the `metainfo` read the other two shapes avoid.
DIMENSION_JOURNAL = ["read_revision", "read_sheet_geometry", "read_revision",
                     "set_dimension_properties", "read_revision"]


def test_AC7_the_freeze_leg_makes_NO_network_read_for_its_post_revision():
    """**The carve-out this issue is most likely to break.** The freeze fallback is
    ``(state or {}).get("revision")`` — an in-hand value. Route it through a helper whose
    fallback is eager, or whose default is the Shape-A ``metainfo`` read, and a sixth call
    appears here.
    """
    calls, _record = _freeze_leg()
    assert calls == FREEZE_JOURNAL, calls
    assert calls[-1] == "read_frozen_panes", (
        "the freeze leg must END on its own verification read — a trailing read_revision "
        "means the in-hand fallback was replaced by a network read"
    )
    assert calls.count("read_revision") == 2, (
        "two: the plan's compare-and-swap anchor and apply's re-check. The post-write "
        "revision comes free with read_frozen_panes."
    )


def test_AC7_the_style_leg_keeps_its_NESTED_revision_extractor():
    """Shape C. ``_style_reply_revision`` reads ``data.updates.revision``; the flat
    ``_revision_of`` finds nothing there. A consolidation that defaults every site to the flat
    extractor would send this leg to ``metainfo`` for a revision the reply already carried.
    """
    calls, _record = _style_leg()
    assert calls == STYLE_JOURNAL, calls
    assert calls[-1] == "put_style", (
        "a trailing read_revision means the nested extractor was lost"
    )


def test_AC7_a_shape_A_leg_still_DOES_fall_back_to_metainfo_as_the_control():
    """The control that keeps the two pins above honest: if the helper simply never called any
    fallback, the two tests above would pass for the wrong reason. Shape A proves the fallback
    still fires where it is supposed to.
    """
    calls, _record = _dimension_leg()
    assert calls == DIMENSION_JOURNAL, calls
    assert calls[-1] == "read_revision", (
        "the dimension reply carries no revision — the metainfo fallback MUST fire here"
    )


def test_AC7_the_three_shapes_really_are_three_and_not_one():
    """Stated as one assertion so the carve-out cannot quietly become a single shape: the three
    journals END differently, which is exactly the difference the audit's "eight identical
    fallbacks" framing missed."""
    endings = {"freeze": _freeze_leg()[0][-1],
               "style": _style_leg()[0][-1],
               "dimension": _dimension_leg()[0][-1]}
    assert endings == {"freeze": "read_frozen_panes",
                       "style": "put_style",
                       "dimension": "read_revision"}, endings


def test_AC7_the_nested_style_extractor_is_the_reason_and_is_directly_observable():
    """The extractor pinned at the unit level too, so the journal pin above has a named cause:
    the flat reader finds nothing in the envelope the style reply actually uses."""
    nested = {"updates": {"revision": 42, "updatedCells": 1}}
    assert O._revision_of(nested) is None
    assert O._style_reply_revision(nested) == 42
    # …and the flat form still wins when it is there (every Shape-A reply)
    assert O._style_reply_revision({"revision": 7}) == 7


def test_AC7_the_consolidated_helper_calls_its_fallback_ONLY_when_it_must():
    """The helper itself, at the unit level — laziness is the whole carve-out.

    An eagerly-evaluated fallback argument would be *invisible* in the Shape-B journal only by
    luck; here it is refused directly. The fallback is a zero-argument callable and it is not
    called at all when the reply already answered.
    """
    fired = []

    def fallback():
        fired.append(1)
        return 99

    assert O._post_write_revision({"revision": 5}, fallback) == 5
    assert fired == [], "the fallback ran even though the reply carried a revision"

    assert O._post_write_revision({}, fallback) == 99
    assert fired == [1]

    # the extractor is a parameter, which is what lets Shape C keep its nested reader
    assert O._post_write_revision({"updates": {"revision": 3}}, fallback,
                                  extract=O._style_reply_revision) == 3
    assert fired == [1], "Shape C fell back despite its own extractor finding the revision"


def test_AC7_all_NINE_post_revision_endings_go_through_the_one_helper():
    """N3, stated structurally rather than counted by eye: no apply leg still spells the
    ``if post_revision is None:`` ending itself."""
    import inspect

    legs = (O._apply_dimension_property_one, O._apply_freeze_one, O._apply_style_one,
            O._apply_structural_one, O._apply_merge_one, O._apply_tab_one,
            O._apply_value_one, O._apply_formula_one, O._apply_dropdown_one)
    assert len(legs) == 9
    for leg in legs:
        src = inspect.getsource(leg)
        assert "_post_write_revision(" in src, leg.__name__
        assert "if post_revision is None" not in src, (
            f"{leg.__name__} still hand-writes the fallback ending"
        )


# =========================================================================== #
# AC1 — ONE SEAM: THE `VerificationLeg` VALUE OBJECT.                           #
# =========================================================================== #

#: The four families, by the name their instance is authored under.
INSTANCES = ("TAB_VERIFICATION", "DIMENSION_VERIFICATION", "FREEZE_VERIFICATION",
             "STYLE_VERIFICATION")


@pytest.mark.parametrize("name", INSTANCES)
def test_AC1_each_family_is_an_instance_of_the_ONE_value_object(name):
    leg = getattr(O, name)
    assert isinstance(leg, O.VerificationLeg), name
    assert isinstance(leg.id, str) and leg.id
    assert isinstance(leg.note, str) and leg.note


def test_AC1_there_are_exactly_four_and_they_are_distinct():
    legs = [getattr(O, name) for name in INSTANCES]
    assert len({leg.id for leg in legs}) == 4, [leg.id for leg in legs]


@pytest.mark.parametrize("name", INSTANCES)
def test_AC1_the_shipped_LEG_and_NOTE_constants_are_DERIVED_from_the_instance(name):
    """The value object is the single authoring site; the two long-standing module constants
    stay as references to it (they are imported by the live gates and quoted across the
    module's own docstrings), so nothing that used them breaks."""
    leg = getattr(O, name)
    assert getattr(O, f"{name}_LEG") is leg.id
    assert getattr(O, f"{name}_NOTE") is leg.note


def test_AC1_the_write_apply_facade_still_re_exports_every_name_it_did():
    import larkdocio.sheets.write_apply as facade

    for name in ("DIMENSION_VERIFICATION_LEG", "STYLE_VERIFICATION_LEG",
                 "STYLE_VERIFICATION_NOTE", "FREEZE_VERIFICATION_LEG",
                 "TAB_VERIFICATION_LEG"):
        assert hasattr(facade, name), name


def test_AC1_stamp_is_the_seam_and_records_BOTH_halves_in_place():
    """``stamp`` mutates the record it is handed and returns it, so the attribution lands
    **after** the family's own fields — which is what keeps the AC6 key order identical."""
    record = {"op": "set-cell-style"}
    returned = O.STYLE_VERIFICATION.stamp(record)
    assert returned is record
    assert tuple(record) == ("op", "verified_by", "verification_note")
    assert record["verified_by"] == "xlsx-export-style-leg"
    assert record["verification_note"] == O.STYLE_VERIFICATION_NOTE


def test_AC1_attribution_is_the_WHICH_alone_for_the_preview_notes():
    """A preview note states which leg is (or is not) going to verify the write; it does not
    carry the apply-log caveat, because the note already carries its own prose under ``note``.
    Splitting the two halves is what lets both shapes share one spelling of the key."""
    assert O.STYLE_VERIFICATION.attribution() == {"verified_by": "xlsx-export-style-leg"}
    # a fresh dict each time — a shared one would let a caller mutate every note at once
    first, second = O.STYLE_VERIFICATION.attribution(), O.STYLE_VERIFICATION.attribution()
    assert first == second and first is not second


@pytest.mark.parametrize("leg_name", ["_apply_dimension_property_one", "_apply_freeze_one",
                                      "_apply_style_one", "_apply_tab_one"])
def test_AC1_no_apply_leg_hand_stamps_its_own_key_note_pair_any_more(leg_name):
    import inspect

    src = inspect.getsource(getattr(O, leg_name))
    assert '"verification_note"' not in src, leg_name
    assert ".stamp(" in src, leg_name


def _package_source() -> str:
    """Every byte of the ``sheets/ops`` package, concatenated.

    ``O.__file__`` was the whole module until LD-532 split the flat ``sheets/ops.py`` into a
    package (one module per op family, the registry and engine loop in ``__init__``). Reading
    only ``__file__`` would now scan ``__init__.py`` alone and leave the family legs — the
    very code that used to hand-stamp the key — unscanned, which is how a text guard rots into
    a tautology. Derived from the tree, so a family module added tomorrow is scanned on its
    own.
    """
    from pathlib import Path

    directory = Path(O.__file__).parent
    return "".join(
        path.read_text(encoding="utf-8")
        for path in sorted(directory.rglob("*.py"))
        if "__pycache__" not in path.parts)


def test_AC1_the_key_is_SPELLED_in_exactly_one_place_in_the_module():
    """The defect this issue removes was two spellings of one key. The guard against a third is
    that the literal is authored once — inside the value object — and nowhere else."""
    assert _package_source().count('"verified_by"') == 1, (
        "the apply-log attribution key is spelled more than once in the sheets/ops package — "
        "it is authored on VerificationLeg and referenced everywhere else"
    )


# =========================================================================== #
# AC2 — THE maintainer-RULED RENAME: the two style PREVIEW-note sites lose `"leg"`.     #
#                                                                              #
# CONSUMER-VISIBLE. The old key shipped in v1.24.0 (cut 2026-08-01, the same    #
# day the style family landed) and is corrected here with no shim, per the      #
# Maintainer ruling recorded in the issue.                                              #
# =========================================================================== #

def _cost_note():
    return O.style_export_cost_note({"ranges": [f"{STY.SID}!A1:B2"]})


def _border_note():
    return O.style_border_not_verifiable_note({
        "sheet_id": STY.SID,
        "spans": [{"ranges": [f"{STY.SID}!A1:B2"],
                   "style": {"borderType": "FULL_BORDER"}}]})


@pytest.mark.parametrize("make_note, keys, prose_sha", [
    (_cost_note,
     ("kind", "verified_by", "scope", "ranges", "note"),
     "0cfd0e28af480973d7c1b5a5f2dcff8f6c075eb37f337a5e2d7f8b2c770817f9"),
    # The border note's prose was re-pinned once since: it cited a probe script by path, and
    # that path exists only in the maintainer's repository, so it now carries the
    # `in the dev repo` caveat the citation guard requires. Nothing else in the note moved.
    # Re-pinned a SECOND time by LD-676: that probe script was pruned from the dev repo on
    # 2026-09-18, so the labelled pointer led nowhere; the pointer is gone and the two things
    # a caller can actually do (read xl/styles.xml, or check the Lark UI) are unchanged.
    (_border_note,
     ("kind", "sheet_id", "border_ranges", "verified_by", "note"),
     "43785570dc94d92572ee0559b28699af1aa1bc70ca5d4b769e2faf55f45ab5b7"),
])
def test_AC2_the_style_preview_notes_now_spell_the_key_verified_by(make_note, keys, prose_sha):
    """Only the KEY moves. Its position in the note, the leg value it carries, and every byte
    of the note's own prose are pinned unchanged — so this is a rename and nothing else."""
    note = make_note()
    assert "leg" not in note, note
    assert note["verified_by"] == O.STYLE_VERIFICATION_LEG == "xlsx-export-style-leg"
    assert tuple(note) == keys, note
    assert _sha(note["note"]) == prose_sha, "the note's prose moved — only the key may change"


def test_AC2_the_old_key_is_gone_from_the_module_entirely():
    """AC2's own acceptance command, run as a test: ``grep -rn '"leg"' sheets/ops/`` returns
    nothing."""
    assert '"leg"' not in _package_source(), (
        'the sheets/ops package still spells the apply-log attribution key "leg"'
    )


def test_AC2_a_style_plan_carries_the_renamed_key_end_to_end():
    """Not just the note factory — the key a consumer really reads off a plan entry."""
    gw = STY.FakeStyleGateway()
    plan = dry_run([StyleWriteRequest(f"{STY.SID}!A1:A1", CellStyle(bold=True))], gw, STY.TOKEN)
    cost = next(n for n in plan.entries[0].preview_notes
                if n["kind"] == "style-verification-cost")
    assert cost["verified_by"] == "xlsx-export-style-leg"
    assert "leg" not in cost


def test_AC2_the_apply_log_and_the_preview_note_now_agree_on_ONE_spelling():
    """The defect, stated as the property that removes it: the plan-side disclosure and the
    apply-side record name the same leg under the same key."""
    gw = STY.FakeStyleGateway()
    plan = dry_run([StyleWriteRequest(f"{STY.SID}!A1:A1", CellStyle(bold=True))], gw, STY.TOKEN)
    cost = next(n for n in plan.entries[0].preview_notes
                if n["kind"] == "style-verification-cost")
    record = apply(plan, gw).entries[0].structural
    assert cost["verified_by"] == record["verified_by"]
