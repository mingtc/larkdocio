"""Offline unit tests for the findings-agnostic edit-request + apply-log model
(LD-065).

W1-S1 ships the *pure-offline* surface consumers express an edit against without
leaking their findings schema into the library: a typed :class:`EditRequest`
(anchor = verbatim quote + breadcrumb heading-path + whole-paragraph replacement),
the typed refusal reasons the resolver (S2) and apply engine (S4) both return
(ambiguous-N / not-found / write-hostile / stale-anchor), and a JSON-serializable
apply-log record. No resolution, no write — that is S2..S5. These tests pin the
four offline ACs; AC5 (goldens zero-drift + build + board) is a suite/gate matter.
"""
import ast
import dataclasses
import json
from pathlib import Path

import pytest

from larkdocio.write.model import (
    Anchor,
    ApplyLog,
    ApplyLogEntry,
    DeleteRequest,
    EditRequest,
    InsertPosition,
    InsertRequest,
    NewParagraph,
    Refusal,
    RefusalReason,
    TableLocator,
    _request_from_dict,
)


# --------------------------------------------------------------------------- #
# LD-131 — `detail` is a MANDATORY constructor argument on every docx refusal.   #
# These model-level constructions therefore pass one. Justification (dogfood      #
# report § F5, quoted): "`BEFORE` and `AFTER` return `{"reason": "not-found"}` —  #
# with no `detail` field at all … an empty `{"reason": "not-found"}` gives an      #
# agent NOTHING to recover from." The reason-mapping assertions below are          #
# unchanged — only the (now required) detail is supplied. Consumer-visible          #
# contract change, consented in LD-131 AC5.                                        #
# --------------------------------------------------------------------------- #

_D = "why this refusal fired (LD-131: every docx refusal carries a detail)"


# --------------------------------------------------------------------------- #
# AC1 — typed EditRequest: quote + breadcrumb + whole-paragraph replacement    #
# --------------------------------------------------------------------------- #

def test_edit_request_carries_anchor_and_replacement():
    """An EditRequest is anchor (verbatim quote + breadcrumb heading-path) plus a
    whole-paragraph replacement; the anchor + replacement read back."""
    req = EditRequest(
        anchor=Anchor(quote="Revenue grew 12%.", breadcrumb=("Results", "Q3")),
        replacement="Revenue grew 12.4%.",
    )
    assert req.anchor.quote == "Revenue grew 12%."
    assert req.anchor.breadcrumb == ("Results", "Q3")
    assert req.replacement == "Revenue grew 12.4%."


def test_anchor_breadcrumb_normalized_to_tuple():
    """A breadcrumb passed as a list is stored as an immutable tuple so an anchor
    is hashable/immutable and two equal breadcrumbs compare equal."""
    a = Anchor(quote="q", breadcrumb=["Top", "Sub"])
    assert a.breadcrumb == ("Top", "Sub")
    assert isinstance(a.breadcrumb, tuple)
    assert a == Anchor(quote="q", breadcrumb=("Top", "Sub"))


def test_edit_request_is_immutable():
    """EditRequest / Anchor are frozen value objects — a request is a request."""
    req = EditRequest(anchor=Anchor(quote="q", breadcrumb=()), replacement="r")
    with pytest.raises(Exception):
        req.replacement = "mutated"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# AC2 — typed refusal reasons: four distinct, inspectable values                #
# --------------------------------------------------------------------------- #

def test_all_four_refusal_reasons_defined_and_distinct():
    """All four reasons exist as distinct enum values — including stale-anchor,
    which only S4 (LD-068) actually produces, defined here for the whole chain."""
    reasons = {
        RefusalReason.AMBIGUOUS,
        RefusalReason.NOT_FOUND,
        RefusalReason.WRITE_HOSTILE,
        RefusalReason.STALE_ANCHOR,
    }
    assert len(reasons) == 4


def test_ambiguous_refusal_carries_candidate_detail():
    """The ambiguous-N-candidates refusal carries the candidate ids and count."""
    r = Refusal.ambiguous(candidate_ids=["blk_a", "blk_b", "blk_c"], detail=_D)
    assert r.reason is RefusalReason.AMBIGUOUS
    assert r.candidate_ids == ("blk_a", "blk_b", "blk_c")
    assert r.candidate_count == 3


def test_non_ambiguous_refusals_carry_no_candidates():
    """not-found / write-hostile / stale-anchor carry no candidate detail."""
    for r in (Refusal.not_found(detail=_D), Refusal.write_hostile(detail=_D), Refusal.stale_anchor(detail=_D)):
        assert r.candidate_ids == ()
        assert r.candidate_count == 0
    assert Refusal.not_found(detail=_D).reason is RefusalReason.NOT_FOUND
    assert Refusal.write_hostile(detail=_D).reason is RefusalReason.WRITE_HOSTILE
    assert Refusal.stale_anchor(detail=_D).reason is RefusalReason.STALE_ANCHOR


def test_refusals_with_different_reasons_are_distinct():
    assert Refusal.not_found(detail=_D) != Refusal.write_hostile(detail=_D)
    assert Refusal.not_found(detail=_D) == Refusal.not_found(detail=_D)


# --------------------------------------------------------------------------- #
# AC3 — JSON-serializable apply-log: applied / refused round-trips losslessly   #
# --------------------------------------------------------------------------- #

def test_applied_entry_round_trips_through_json():
    """An applied entry carries target block_id + before/after and survives a
    json.dumps → loads → from_dict round-trip byte-for-byte on to_dict."""
    entry = ApplyLogEntry.applied(
        anchor=Anchor(quote="old text", breadcrumb=("H1",)),
        block_id="blk_123",
        before="old text",
        after="new text",
    )
    restored = ApplyLogEntry.from_dict(json.loads(json.dumps(entry.to_dict())))
    assert restored == entry
    assert restored.to_dict() == entry.to_dict()
    assert restored.block_id == "blk_123"
    assert restored.before == "old text"
    assert restored.after == "new text"


def test_refused_entry_round_trips_through_json():
    """A refused entry carries the typed refusal (with candidate detail) and
    survives the same round-trip losslessly."""
    entry = ApplyLogEntry.refused(
        anchor=Anchor(quote="dup", breadcrumb=("H1", "H2")),
        refusal=Refusal.ambiguous(candidate_ids=["b1", "b2"], detail=_D),
    )
    restored = ApplyLogEntry.from_dict(json.loads(json.dumps(entry.to_dict())))
    assert restored == entry
    assert restored.refusal.reason is RefusalReason.AMBIGUOUS
    assert restored.refusal.candidate_ids == ("b1", "b2")


def test_apply_log_aggregate_round_trips():
    """The whole apply-log (a sequence of mixed applied/refused entries) round-trips
    through JSON losslessly."""
    log = ApplyLog(
        entries=[
            ApplyLogEntry.applied(
                anchor=Anchor(quote="a", breadcrumb=("H",)),
                block_id="b1",
                before="a",
                after="A",
            ),
            ApplyLogEntry.refused(
                anchor=Anchor(quote="c", breadcrumb=()),
                refusal=Refusal.not_found(detail=_D),
            ),
        ]
    )
    restored = ApplyLog.from_json(log.to_json())
    assert restored == log
    assert len(restored.entries) == 2


def test_entry_outcome_field_discriminates_applied_vs_refused():
    """The serialized form has a discriminator so a consumer can branch offline."""
    applied = ApplyLogEntry.applied(
        anchor=Anchor(quote="a", breadcrumb=()), block_id="b", before="a", after="A"
    ).to_dict()
    refused = ApplyLogEntry.refused(
        anchor=Anchor(quote="a", breadcrumb=()), refusal=Refusal.stale_anchor(detail=_D)
    ).to_dict()
    assert applied["outcome"] == "applied"
    assert refused["outcome"] == "refused"


# --------------------------------------------------------------------------- #
# AC4 — findings-agnostic: no consumer / findings / layer / status coupling     #
# --------------------------------------------------------------------------- #

# LD-087 split the single write/model.py into a write/model/ subpackage
# (anchors/requests/refusal/applylog) behind a re-export shim. The AST
# findings-vocabulary guards scan the WHOLE package so a symbol counts no matter which
# concern-group submodule now houses it — the assertions are unchanged; only the source
# the guard reads widened from one file to the package.
_MODEL_DIR = Path(__file__).resolve().parents[1] / "src" / "larkdocio" / "write" / "model"


def _model_trees():
    """Every submodule of the write-model package, parsed to an AST."""
    return [ast.parse(p.read_text(encoding="utf-8"))
            for p in sorted(_MODEL_DIR.rglob("*.py"))]  # LD-654: recursive population


def test_module_imports_only_stdlib_and_larkdocio():
    """AST-scan every import: each top-level module is stdlib or larkdocio — no
    consumer package, no third-party findings library leaks in."""
    roots = set()
    for tree in _model_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # a relative import stays inside larkdocio
                    continue
                if node.module:
                    roots.add(node.module.split(".")[0])
    import sys
    allowed = set(sys.stdlib_module_names) | {"larkdocio"}
    assert roots <= allowed, f"non-stdlib/non-larkdocio imports: {roots - allowed}"


def _code_identifiers(tree: ast.AST):
    """Every code-level identifier (names, attributes, args, def/class names,
    keyword-arg names) — excludes docstrings/comments, which may *describe* the
    agnostic boundary (e.g. the word 'findings-agnostic') without coupling to it."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
    return names


def _all_code_identifiers():
    """Union of code-level identifiers across every write-model submodule (LD-087)."""
    idents = set()
    for tree in _model_trees():
        idents |= _code_identifiers(tree)
    return idents


def test_module_references_no_findings_vocabulary():
    """The library never learns a consumer's findings schema — no CODE identifier
    couples to findings / layer / severity / accept-reject vocabulary. Docstrings
    that *name* the agnostic boundary are fine; a symbol named for it is not."""
    idents = {n.lower() for n in _all_code_identifiers()}
    for word in ("finding", "layer", "severity", "accepted", "rejected"):
        offenders = {n for n in idents if word in n}
        assert not offenders, f"findings-schema vocabulary in identifiers: {offenders}"


# =========================================================================== #
# LD-070 — table-locator anchor variant (W2-S1)                                #
#                                                                             #
# A bare quote cannot locate a table cell (spike Test 5: `97.2%` appeared in  #
# 6 blocks). The table anchor variant is a `TableLocator` — a verbatim        #
# key-cell quote (picks the row) + a column-target (picks the cell) +         #
# breadcrumb (narrows WHICH table for S2) — carried on an `EditRequest` in    #
# place of the narrative `Anchor`. The paragraph path is untouched (additive).#
# =========================================================================== #


# --------------------------------------------------------------------------- #
# LD-070 AC1 — table_locator anchor variant: row-key + column-target + repl.    #
# --------------------------------------------------------------------------- #

def test_table_locator_carries_row_key_and_column_header():
    """A TableLocator locates a cell by its row's key-cell quote + a column-target
    given as a verbatim header-cell quote; both read back."""
    loc = TableLocator(row_key="On-time delivery", column_header="Q3")
    assert loc.row_key == "On-time delivery"
    assert loc.column_header == "Q3"
    assert loc.column_index is None


def test_table_locator_column_target_may_be_a_zero_based_index():
    """The column-target designation may instead be a 0-based column index
    (representation is 'either header quote OR index' — Dev's documented call)."""
    loc = TableLocator(row_key="On-time delivery", column_index=2)
    assert loc.column_index == 2
    assert loc.column_header is None


def test_table_locator_carries_breadcrumb_for_table_disambiguation():
    """The locator carries a breadcrumb (heading path) so S2 can narrow WHICH
    table when the same key cell appears under more than one heading. Normalized
    to an immutable tuple like the narrative Anchor's breadcrumb."""
    loc = TableLocator(row_key="rk", column_index=0, breadcrumb=["Results", "Q3"])
    assert loc.breadcrumb == ("Results", "Q3")
    assert isinstance(loc.breadcrumb, tuple)


def test_table_locator_requires_exactly_one_column_target():
    """Exactly one column-target must be supplied — neither (no column) nor both
    (ambiguous designation) is a valid locator."""
    with pytest.raises(ValueError):
        TableLocator(row_key="rk")  # neither
    with pytest.raises(ValueError):
        TableLocator(row_key="rk", column_header="Q3", column_index=2)  # both


def test_edit_request_carries_table_locator_and_whole_cell_replacement():
    """An EditRequest's anchor may be a TableLocator instead of a narrative Anchor;
    the replacement is the whole-cell text. Row-key, column-target and replacement
    all read back off the request."""
    req = EditRequest(
        anchor=TableLocator(row_key="On-time delivery", column_header="Q3"),
        replacement="98.1%",
    )
    assert req.anchor.row_key == "On-time delivery"
    assert req.anchor.column_header == "Q3"
    assert req.replacement == "98.1%"


# --------------------------------------------------------------------------- #
# LD-070 AC2 — immutable + JSON round-trip (incl. the table_locator)            #
# --------------------------------------------------------------------------- #

def test_table_locator_is_immutable():
    """The table anchor variant is frozen like Anchor / EditRequest."""
    loc = TableLocator(row_key="rk", column_index=0)
    with pytest.raises(Exception):
        loc.row_key = "mutated"  # type: ignore[misc]


def test_table_edit_request_round_trips_through_json_header_target():
    """An EditRequest carrying a header-quote table_locator survives a
    json.dumps → loads → from_dict round-trip losslessly."""
    req = EditRequest(
        anchor=TableLocator(
            row_key="On-time delivery",
            column_header="Q3",
            breadcrumb=("Results", "Ops"),
        ),
        replacement="98.1%",
    )
    restored = EditRequest.from_dict(json.loads(json.dumps(req.to_dict())))
    assert restored == req
    assert isinstance(restored.anchor, TableLocator)
    assert restored.anchor.row_key == "On-time delivery"
    assert restored.anchor.column_header == "Q3"
    assert restored.anchor.breadcrumb == ("Results", "Ops")


def test_table_edit_request_round_trips_through_json_index_target():
    """The index-based column-target also round-trips losslessly."""
    req = EditRequest(
        anchor=TableLocator(row_key="rk", column_index=2),
        replacement="new",
    )
    restored = EditRequest.from_dict(json.loads(json.dumps(req.to_dict())))
    assert restored == req
    assert restored.anchor.column_index == 2
    assert restored.anchor.column_header is None


def test_narrative_edit_request_still_round_trips_unchanged():
    """The paragraph path is untouched: a narrative Anchor EditRequest still
    round-trips to an Anchor (not a TableLocator) — the variant is additive."""
    req = EditRequest(
        anchor=Anchor(quote="Revenue grew 12%.", breadcrumb=("Results",)),
        replacement="Revenue grew 12.4%.",
    )
    restored = EditRequest.from_dict(json.loads(json.dumps(req.to_dict())))
    assert restored == req
    assert isinstance(restored.anchor, Anchor)


def test_apply_log_entry_round_trips_a_table_anchor():
    """An apply-log entry carrying a table anchor round-trips through JSON too, so
    the whole chain shares one serialization discipline (the anchor discriminates
    on a 'kind' tag; the narrative anchor, tagless, stays byte-compatible)."""
    entry = ApplyLogEntry.refused(
        anchor=TableLocator(row_key="On-time delivery", column_header="Q3"),
        refusal=Refusal.column_not_found(detail=_D),
    )
    restored = ApplyLogEntry.from_dict(json.loads(json.dumps(entry.to_dict())))
    assert restored == entry
    assert isinstance(restored.anchor, TableLocator)


# --------------------------------------------------------------------------- #
# LD-070 AC3 — table refusals expressible; W1 reasons reused; mapping pinned    #
# --------------------------------------------------------------------------- #

def test_table_refusal_cases_map_to_documented_reasons():
    """Each table refusal case is expressible and yields an inspectable, typed
    refusal per the documented mapping:

      table-not-found  -> NOT_FOUND        (reuse W1)
      ambiguous-table  -> AMBIGUOUS + ids  (reuse W1)
      row-not-found    -> NOT_FOUND        (reuse W1)
      ambiguous-row    -> AMBIGUOUS + ids  (reuse W1)
      covered/merged   -> WRITE_HOSTILE    (reuse W1)
      column-not-found -> COLUMN_NOT_FOUND (NEW — the W1 four don't fit)
    """
    assert Refusal.table_not_found(detail=_D).reason is RefusalReason.NOT_FOUND
    assert Refusal.row_not_found(detail=_D).reason is RefusalReason.NOT_FOUND

    amb_t = Refusal.ambiguous_table(candidate_ids=["tbl_a", "tbl_b"], detail=_D)
    assert amb_t.reason is RefusalReason.AMBIGUOUS
    assert amb_t.candidate_ids == ("tbl_a", "tbl_b")
    assert amb_t.candidate_count == 2

    amb_r = Refusal.ambiguous_row(candidate_ids=["row_a", "row_b", "row_c"], detail=_D)
    assert amb_r.reason is RefusalReason.AMBIGUOUS
    assert amb_r.candidate_count == 3

    # covered / merged target reuses the existing write-hostile reason
    assert Refusal.write_hostile(detail=_D).reason is RefusalReason.WRITE_HOSTILE


def test_column_not_found_is_a_new_distinct_reason():
    """column-not-found is a NEW typed reason — the W1 four (ambiguous / not-found
    / write-hostile / stale-anchor) don't fit 'row found, column absent'. It is
    distinct from NOT_FOUND and carries no candidate detail."""
    cnf = Refusal.column_not_found(detail=_D)
    assert cnf.reason is RefusalReason.COLUMN_NOT_FOUND
    assert cnf.reason is not RefusalReason.NOT_FOUND
    assert cnf.candidate_ids == ()
    assert cnf.candidate_count == 0
    assert cnf != Refusal.not_found(detail=_D)


def test_table_refusals_surface_the_full_distinct_reason_set():
    """Collectively the table cases surface a distinct set of inspectable reasons:
    AMBIGUOUS, NOT_FOUND, WRITE_HOSTILE, and the new COLUMN_NOT_FOUND."""
    reasons = {
        Refusal.ambiguous_table(["t"], detail=_D).reason,
        Refusal.ambiguous_row(["r"], detail=_D).reason,
        Refusal.table_not_found(detail=_D).reason,
        Refusal.row_not_found(detail=_D).reason,
        Refusal.write_hostile(detail=_D).reason,
        Refusal.column_not_found(detail=_D).reason,
    }
    assert reasons == {
        RefusalReason.AMBIGUOUS,
        RefusalReason.NOT_FOUND,
        RefusalReason.WRITE_HOSTILE,
        RefusalReason.COLUMN_NOT_FOUND,
    }


def test_column_not_found_refusal_round_trips():
    """The new refusal reason serializes / deserializes losslessly."""
    r = Refusal.column_not_found(detail=_D)
    assert Refusal.from_dict(json.loads(json.dumps(r.to_dict()))) == r
    assert r.to_dict()["reason"] == "column-not-found"


# --------------------------------------------------------------------------- #
# LD-070 AC4 — findings-agnostic AST guard EXTENDED to the new symbols           #
# --------------------------------------------------------------------------- #

def test_table_locator_symbols_are_present_and_findings_agnostic():
    """The W1 AST findings-vocabulary guard is extended to explicitly cover the new
    table symbols: they exist in the module (guard is live, not vacuous) and none of
    them — nor anything else in the module — couples to consumer findings / layer /
    status vocabulary."""
    idents = _all_code_identifiers()
    new_symbols = {
        "TableLocator",
        "row_key",
        "column_header",
        "column_index",
        "table_not_found",
        "ambiguous_table",
        "row_not_found",
        "ambiguous_row",
        "column_not_found",
        "COLUMN_NOT_FOUND",
    }
    missing = new_symbols - idents
    assert not missing, f"new table symbols absent from module: {missing}"

    lowered = {n.lower() for n in idents}
    for word in ("finding", "layer", "severity", "accepted", "rejected", "status"):
        offenders = {n for n in lowered if word in n}
        assert not offenders, f"findings-schema vocabulary in identifiers: {offenders}"


def test_table_locator_exported_from_write_package():
    """TableLocator is part of the write package's public surface, alongside the
    W1 model symbols."""
    import larkdocio.write as w
    assert w.TableLocator is TableLocator
    assert "TableLocator" in w.__all__


# =========================================================================== #
# LD-074 — insertion/deletion request model (W3-S1)                            #
#                                                                             #
# W3 adds two operations to the gated engine — block insertion and block      #
# deletion — and needs their findings-agnostic REQUEST TYPES first. An        #
# `InsertRequest` (reference `Anchor` + a position before/after/append-into + #
# new content as text-bearing paragraphs ONLY — hostile types image/board/    #
# bitable/sheet/mermaid are structurally INEXPRESSIBLE) and a `DeleteRequest` #
# (target `Anchor`). The apply-log record gains an insert's created-ids and a #
# delete's full removed-block payload (populated later by S3). New refusals    #
# only where the existing five don't fit; reuse + document the mapping.        #
# Same frozen / JSON / AST-guard discipline. Pure offline.                     #
# =========================================================================== #


# --------------------------------------------------------------------------- #
# LD-074 AC1 — InsertRequest: reference anchor + position + text-bearing        #
#              paragraph content; hostile creatable types inexpressible         #
# --------------------------------------------------------------------------- #

def test_insert_request_carries_reference_position_and_content():
    """An InsertRequest is a reference Anchor (quote + breadcrumb) + a position
    (before/after/append-into) + new content as one or more text-bearing
    paragraphs; all three read back."""
    req = InsertRequest(
        reference=Anchor(quote="Results summary.", breadcrumb=("Results", "Q3")),
        position=InsertPosition.AFTER,
        content=[NewParagraph(text="A newly inserted paragraph.")],
    )
    assert req.reference.quote == "Results summary."
    assert req.reference.breadcrumb == ("Results", "Q3")
    assert req.position is InsertPosition.AFTER
    assert [p.text for p in req.content] == ["A newly inserted paragraph."]


def test_insert_position_has_the_three_values():
    """The position value covers exactly before / after / append-into."""
    assert {p.value for p in InsertPosition} == {"before", "after", "append-into"}


def test_insert_request_content_may_be_several_paragraphs():
    """New content expresses one OR MORE text-bearing paragraphs; the sequence
    is normalized to an immutable tuple."""
    req = InsertRequest(
        reference=Anchor(quote="ref"),
        position=InsertPosition.BEFORE,
        content=[NewParagraph(text="para one"), NewParagraph(text="para two")],
    )
    assert isinstance(req.content, tuple)
    assert [p.text for p in req.content] == ["para one", "para two"]


def test_insert_request_requires_at_least_one_paragraph():
    """An insertion with no content is meaningless — empty content is rejected."""
    with pytest.raises(ValueError):
        InsertRequest(
            reference=Anchor(quote="ref"),
            position=InsertPosition.AFTER,
            content=[],
        )


def test_new_content_is_structurally_text_bearing_only():
    """Hostile creatable types (image/board/embed/bitable/sheet/mermaid) are
    INEXPRESSIBLE by construction: NewParagraph carries text only — there is no
    block-type field, no image token, no embed url to smuggle a hostile type in.
    This asserts the structural exclusion at the type level, not a runtime refusal."""
    fields = {f.name for f in dataclasses.fields(NewParagraph)}
    assert fields == {"text"}
    # No attribute exists through which a hostile type could be requested.
    p = NewParagraph(text="plain")
    for hostile_attr in ("block_type", "type", "image", "token", "embed", "url", "sheet", "bitable", "mermaid", "board"):
        assert not hasattr(p, hostile_attr)


# --------------------------------------------------------------------------- #
# LD-074 AC2 — DeleteRequest: target anchor designating the block to remove      #
# --------------------------------------------------------------------------- #

def test_delete_request_carries_target_anchor():
    """A DeleteRequest is a single target Anchor designating the block to remove;
    the target reads back."""
    req = DeleteRequest(target=Anchor(quote="Obsolete note.", breadcrumb=("Appendix",)))
    assert req.target.quote == "Obsolete note."
    assert req.target.breadcrumb == ("Appendix",)


# --------------------------------------------------------------------------- #
# LD-074 AC3 — frozen + JSON round-trip, discriminated from EditRequest/each other
# --------------------------------------------------------------------------- #

def test_insert_and_delete_requests_are_immutable():
    """InsertRequest / DeleteRequest / NewParagraph are frozen value objects."""
    ins = InsertRequest(
        reference=Anchor(quote="r"), position=InsertPosition.AFTER,
        content=[NewParagraph(text="p")],
    )
    dele = DeleteRequest(target=Anchor(quote="r"))
    with pytest.raises(Exception):
        ins.position = InsertPosition.BEFORE  # type: ignore[misc]
    with pytest.raises(Exception):
        dele.target = Anchor(quote="x")  # type: ignore[misc]
    with pytest.raises(Exception):
        ins.content[0].text = "mutated"  # type: ignore[misc]


def test_insert_request_round_trips_through_json():
    """An InsertRequest survives json.dumps → loads → from_dict losslessly."""
    req = InsertRequest(
        reference=Anchor(quote="Results summary.", breadcrumb=("Results",)),
        position=InsertPosition.APPEND_INTO,
        content=[NewParagraph(text="child one"), NewParagraph(text="child two")],
    )
    restored = InsertRequest.from_dict(json.loads(json.dumps(req.to_dict())))
    assert restored == req
    assert restored.position is InsertPosition.APPEND_INTO
    assert [p.text for p in restored.content] == ["child one", "child two"]


def test_delete_request_round_trips_through_json():
    """A DeleteRequest survives the same round-trip losslessly."""
    req = DeleteRequest(target=Anchor(quote="Obsolete note.", breadcrumb=("Appendix",)))
    restored = DeleteRequest.from_dict(json.loads(json.dumps(req.to_dict())))
    assert restored == req
    assert restored.target.quote == "Obsolete note."


def test_request_dispatch_discriminates_edit_insert_delete():
    """The module's `_request_from_dict` dispatch reads each request kind back to
    its own type — discriminated from the others. EditRequest stays tagless
    (byte-compatible with its W1 form); insert/delete carry an `op` tag."""
    edit = EditRequest(anchor=Anchor(quote="q"), replacement="r")
    ins = InsertRequest(
        reference=Anchor(quote="r"), position=InsertPosition.AFTER,
        content=[NewParagraph(text="p")],
    )
    dele = DeleteRequest(target=Anchor(quote="t"))

    assert "op" not in edit.to_dict()  # W1 EditRequest serialization unchanged
    assert ins.to_dict()["op"] == "insert"
    assert dele.to_dict()["op"] == "delete"

    assert _request_from_dict(json.loads(json.dumps(edit.to_dict()))) == edit
    assert _request_from_dict(json.loads(json.dumps(ins.to_dict()))) == ins
    assert _request_from_dict(json.loads(json.dumps(dele.to_dict()))) == dele
    assert isinstance(_request_from_dict(edit.to_dict()), EditRequest)
    assert isinstance(_request_from_dict(ins.to_dict()), InsertRequest)
    assert isinstance(_request_from_dict(dele.to_dict()), DeleteRequest)


# --------------------------------------------------------------------------- #
# LD-074 AC4 — new refusals only where needed; mapping documented               #
# --------------------------------------------------------------------------- #

def test_insert_delete_refusals_reuse_existing_reasons_where_they_fit():
    """The insert/delete refusal cases that genuinely match the existing set REUSE
    it (one vocabulary): a not-found/ambiguous/write-hostile reference or target
    maps to NOT_FOUND / AMBIGUOUS / WRITE_HOSTILE respectively."""
    assert Refusal.reference_not_found(detail=_D).reason is RefusalReason.NOT_FOUND
    assert Refusal.target_not_found(detail=_D).reason is RefusalReason.NOT_FOUND
    assert Refusal.reference_write_hostile(detail=_D).reason is RefusalReason.WRITE_HOSTILE
    assert Refusal.target_write_hostile(detail=_D).reason is RefusalReason.WRITE_HOSTILE

    amb_ref = Refusal.ambiguous_reference(candidate_ids=["b1", "b2"], detail=_D)
    assert amb_ref.reason is RefusalReason.AMBIGUOUS
    assert amb_ref.candidate_ids == ("b1", "b2")
    amb_tgt = Refusal.ambiguous_target(candidate_ids=["b3", "b4", "b5"], detail=_D)
    assert amb_tgt.reason is RefusalReason.AMBIGUOUS
    assert amb_tgt.candidate_count == 3


def test_cannot_hold_children_is_a_new_distinct_reason():
    """`append-into` a resolved block that cannot parent children is a NEW kind of
    failure — the reference WAS found (not not-found), is a friendly paragraph (not
    write-hostile), is unique (not ambiguous), unchanged (not stale). None of the
    five fit, so it earns its own typed reason, exactly as column-not-found did."""
    r = Refusal.cannot_hold_children(detail=_D)
    assert r.reason is RefusalReason.CANNOT_HOLD_CHILDREN
    assert r.reason is not RefusalReason.NOT_FOUND
    assert r.reason is not RefusalReason.WRITE_HOSTILE
    assert r.candidate_ids == ()
    assert r.candidate_count == 0
    assert r != Refusal.not_found(detail=_D)


def test_insert_delete_refusal_cases_are_each_distinct_and_inspectable():
    """Each insert/delete refusal case is a distinct, inspectable typed refusal;
    collectively they surface NOT_FOUND, AMBIGUOUS, WRITE_HOSTILE and the new
    CANNOT_HOLD_CHILDREN (only that last one is new — the rest reuse W1)."""
    reasons = {
        Refusal.reference_not_found(detail=_D).reason,
        Refusal.ambiguous_reference(["b"], detail=_D).reason,
        Refusal.reference_write_hostile(detail=_D).reason,
        Refusal.target_not_found(detail=_D).reason,
        Refusal.ambiguous_target(["b"], detail=_D).reason,
        Refusal.target_write_hostile(detail=_D).reason,
        Refusal.cannot_hold_children(detail=_D).reason,
    }
    assert reasons == {
        RefusalReason.NOT_FOUND,
        RefusalReason.AMBIGUOUS,
        RefusalReason.WRITE_HOSTILE,
        RefusalReason.CANNOT_HOLD_CHILDREN,
    }


def test_cannot_hold_children_refusal_round_trips():
    """The new refusal reason serializes / deserializes losslessly."""
    r = Refusal.cannot_hold_children(detail=_D)
    assert Refusal.from_dict(json.loads(json.dumps(r.to_dict()))) == r
    assert r.to_dict()["reason"] == "cannot-hold-children"


# --------------------------------------------------------------------------- #
# LD-074 AC5 — apply-log record can represent insert + delete outcomes           #
# --------------------------------------------------------------------------- #

def test_inserted_apply_log_entry_carries_created_block_ids():
    """An insert apply-log entry carries the created block id(s) and round-trips
    through JSON losslessly. (Population with real ids is S3; S1 is the shape.)"""
    entry = ApplyLogEntry.inserted(
        anchor=Anchor(quote="ref", breadcrumb=("H1",)),
        created_block_ids=["blk_new1", "blk_new2"],
    )
    restored = ApplyLogEntry.from_dict(json.loads(json.dumps(entry.to_dict())))
    assert restored == entry
    assert restored.outcome == "inserted"
    assert restored.created_block_ids == ("blk_new1", "blk_new2")


def test_deleted_apply_log_entry_carries_full_removed_payload():
    """A delete apply-log entry carries the FULL removed-block payload (elements +
    per-run style) so a consumer can reconstruct what was removed — DESTRUCTIVE-SAFE.
    Round-trips through JSON losslessly. (Real payload capture is S3; S1 is the shape.)"""
    removed = {
        "block_id": "blk_gone",
        "block_type": 2,
        "elements": [
            {"text_run": {"content": "Obsolete ", "text_element_style": {"bold": True}}},
            {"text_run": {"content": "note.", "text_element_style": {}}},
        ],
        "style": {"align": 1},
    }
    entry = ApplyLogEntry.deleted(
        anchor=Anchor(quote="Obsolete note.", breadcrumb=("Appendix",)),
        block_id="blk_gone",
        removed_payload=removed,
    )
    restored = ApplyLogEntry.from_dict(json.loads(json.dumps(entry.to_dict())))
    assert restored == entry
    assert restored.outcome == "deleted"
    assert restored.block_id == "blk_gone"
    assert restored.removed_payload == removed


def test_apply_log_mixes_insert_delete_and_edit_outcomes():
    """The whole apply-log can carry a mix of applied/refused/inserted/deleted
    entries and round-trips as a whole losslessly."""
    log = ApplyLog(entries=[
        ApplyLogEntry.applied(
            anchor=Anchor(quote="a"), block_id="b1", before="a", after="A"),
        ApplyLogEntry.inserted(
            anchor=Anchor(quote="ref"), created_block_ids=["blk_new"]),
        ApplyLogEntry.deleted(
            anchor=Anchor(quote="t"), block_id="blk_gone",
            removed_payload={"elements": [], "style": {}}),
        ApplyLogEntry.refused(
            anchor=Anchor(quote="c"), refusal=Refusal.cannot_hold_children(detail=_D)),
    ])
    restored = ApplyLog.from_json(log.to_json())
    assert restored == log
    assert [e.outcome for e in restored.entries] == [
        "applied", "inserted", "deleted", "refused"]


# --------------------------------------------------------------------------- #
# LD-074 AC6 — findings-agnostic; AST guard EXTENDED to the new symbols          #
# --------------------------------------------------------------------------- #

def test_insert_delete_symbols_present_and_findings_agnostic():
    """The AST findings-vocabulary guard is extended to cover the new W3-S1 symbols:
    they exist in the module (guard is live, not vacuous) and none of them — nor
    anything else in the module — couples to consumer findings / layer / status
    vocabulary."""
    idents = _all_code_identifiers()
    new_symbols = {
        "InsertRequest",
        "DeleteRequest",
        "InsertPosition",
        "NewParagraph",
        "reference",
        "position",
        "content",
        "target",
        "created_block_ids",
        "removed_payload",
        "inserted",
        "deleted",
        "reference_not_found",
        "ambiguous_reference",
        "reference_write_hostile",
        "target_not_found",
        "ambiguous_target",
        "target_write_hostile",
        "cannot_hold_children",
        "CANNOT_HOLD_CHILDREN",
    }
    missing = new_symbols - idents
    assert not missing, f"new insert/delete symbols absent from module: {missing}"

    lowered = {n.lower() for n in idents}
    for word in ("finding", "layer", "severity", "accepted", "rejected", "status"):
        offenders = {n for n in lowered if word in n}
        assert not offenders, f"findings-schema vocabulary in identifiers: {offenders}"


def test_insert_delete_symbols_exported_from_write_package():
    """InsertRequest / DeleteRequest / InsertPosition / NewParagraph join the
    write package's public surface alongside the W1/W2 model symbols."""
    import larkdocio.write as w
    for name in ("InsertRequest", "DeleteRequest", "InsertPosition", "NewParagraph"):
        assert name in w.__all__
    assert w.InsertRequest is InsertRequest
    assert w.DeleteRequest is DeleteRequest
