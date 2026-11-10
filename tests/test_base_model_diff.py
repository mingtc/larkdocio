"""LD-257 — the in-memory Base table model: the DIFF half.

Offline, from the committed probe captures. The snapshot half is
`tests/test_base_model.py`; this file holds the properties the *diff* exists for:

* **AC3** — every record gets exactly one typed disposition, and the set is exhaustive over
  the model (the apply-log-completeness property, one layer earlier where it is cheap);
* **AC4** — computed fields are a **mirror, never a master**: carried for reading, refused on
  write, with the Lookup trap pinned from `p1-q0-03`;
* **AC5** — the cross-table boundary is explicit: a dangling link is a normal state
  (`p0-2-07`), a DuplexLink edit **discloses** its mirror effect rather than performing it
  (`p0-2-05`), and a dropped `property.table_name` is a dangling *target* (`p0-5-02`);
* **AC8** — determinism: same snapshot, same edits, byte-identical plan structure, ordered by
  the schema rather than by dict iteration.

Plus the spec's test-rigor amplifiers: the absent-key rule meeting the diff, a record deleted
in Lark between snapshot and diff, and a record added beside the one it was cloned from.
"""
import copy
import json

import pytest

from base_captures import capture, scratch_base
from larkdocio.base import diff as base_diff
from larkdocio.base.cells import FieldSpec, render_row
from larkdocio.base.model import (
    NEW_RECORD_PREFIX,
    BaseModelError,
    ReadProof,
    UnknownField,
    UnknownRecord,
    snapshot_base,
    snapshot_table,
)
from larkdocio.base.table import assemble_base, assemble_table
from larkdocio.base.write_vocabulary import (
    NON_WRITABLE_PAIRS,
    NON_WRITABLE_REASONS,
)

EXHAUSTED = ReadProof(pages=1, records=0, exhausted=True,
                      stopped_because="the last page said there is no more")


def snapshot_of(table_read, revision=7, app_token="appXXX"):
    return snapshot_table(table_read, app_token=app_token, revision=revision,
                          read_proof=EXHAUSTED)


# --------------------------------------------------------------------------- #
# Fixtures — the captured Scratch Base, and the captured link zoo              #
# --------------------------------------------------------------------------- #

def scratch_tables():
    """`(main, ref)` — the captured Scratch Base's two tables, through L1's assembler.

    Table 1 carries a **Lookup** and a **Stage**; table 2 is plain text. Two tables is what
    makes the per-table anchor property (AC7) and the no-write-to-the-other-table property
    (AC5-ii) expressible at all.
    """
    app, tables, per_table = scratch_base()
    return app, tables, [
        assemble_table(table_id=table.table_id, name=table.name,
                       fields=per_table[table.table_id][0],
                       records=per_table[table.table_id][1])
        for table in tables
    ]


def link_field_payloads():
    """The captured link fields of the P0 zoo, by name — real `GET …/fields` items."""
    payloads = {}

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") in (18, 21) and "field_name" in node and "ui_type" in node:
                payloads.setdefault(node["field_name"], node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(capture("p0-2-03-field-schema-full.json"))
    return payloads


def link_zoo_after_target_record_delete():
    """`(fields, records)` for the P0 zoo's main table **after its linked record was
    deleted** — the `p0-2-07` shape, verbatim.

    The three link columns disagree on purpose, and that disagreement is the evidence:
    `SingleLinkOne` / `SingleLinkMany` still hold the id of the record that was deleted, while
    the symmetric `DuplexLink` reads back `[]`.
    """
    rows = capture("p0-2-07-link-deletion-behaviour.json")["response"]["data"][
        "main_rows_after_linked_record_delete"]
    payloads = link_field_payloads()
    fields = [
        FieldSpec.from_payload(payloads["SingleLinkOne"]),
        FieldSpec.from_payload(payloads["SingleLinkMany"]),
        FieldSpec.from_payload(payloads["DuplexLink"]),
        FieldSpec(field_name="多行文本", type=1, ui_type="Text", field_id="fldText"),
    ]
    return fields, rows


def dangling_target_field():
    """A `SingleLink` whose **target table was deleted**.

    The `property` is the captured one from `p0-5-02` — `{"multiple": true, "table_id":
    "tblsT2Ons4CcdJgY"}`, with `table_name` **dropped out**. That capture's field listing is
    the abbreviated one and carries no `ui_type`, so the pair comes from the captured
    `SingleLinkMany` schema of the same type; nothing about the detector is invented.
    """
    healthy = FieldSpec.from_payload(link_field_payloads()["SingleLinkMany"])
    dropped = None
    for entry in capture("p0-5-02-symmetric-link-deletion.json")["response"]["data"][
            "main_fields_after_target_table_delete"]:
        if entry["field_name"] == "SLink":
            dropped = entry["property"]
    assert dropped == {"multiple": True, "table_id": "tblsT2Ons4CcdJgY"}
    return FieldSpec(field_name="SLink", type=healthy.type, ui_type=healthy.ui_type,
                     property=dropped, field_id="fldSLink")


def one_field_table(spec, value=None):
    """A one-column table carrying one record — the smallest fixture a refusal needs."""
    fields = [FieldSpec(field_name="Text", type=1, ui_type="Text", field_id="fldT"), spec]
    record = {"record_id": "rec1", "fields": {"Text": [{"text": "row", "type": "text"}]}}
    if value is not None:
        record["fields"][spec.field_name] = value
    return assemble_table(table_id="tbl1", name="t", fields=fields, records=[record])


# --------------------------------------------------------------------------- #
# AC3 — every record gets a typed disposition                                  #
# --------------------------------------------------------------------------- #

def test_ac3_the_disposition_set_is_exhaustive_over_the_model():
    """Every record in the snapshot **and** every record added in memory appears exactly
    once. This is the apply-log-completeness property, enforced where it is cheap."""
    _, _, (main, _ref) = scratch_tables()
    snapshot = snapshot_of(main)
    draft = snapshot.edit()
    draft.set(snapshot.records[0].record_id, "Text", "moved")
    draft.delete(snapshot.records[1].record_id)
    new_one = draft.add(Text="brand new")
    new_two = draft.add(Text="also new")

    diff = draft.diff()
    seen = [entry.record_id for entry in diff.dispositions]
    assert len(seen) == len(set(seen))
    assert set(seen) == set(snapshot.record_ids) | {new_one, new_two}
    for entry in diff.dispositions:
        assert entry.disposition in base_diff.DISPOSITIONS


def test_ac3_each_disposition_is_the_right_one():
    _, _, (main, _ref) = scratch_tables()
    snapshot = snapshot_of(main)
    edited, deleted, untouched = snapshot.records[0], snapshot.records[1], snapshot.records[2]
    draft = snapshot.edit()
    draft.set(edited.record_id, "Text", "moved")
    draft.delete(deleted.record_id)
    created = draft.add(Text="brand new")
    diff = draft.diff()

    assert diff.record(edited.record_id).disposition == base_diff.EDITED
    assert diff.record(deleted.record_id).disposition == base_diff.DELETED
    assert diff.record(untouched.record_id).disposition == base_diff.UNCHANGED
    assert diff.record(created).disposition == base_diff.CREATED
    assert created.startswith(NEW_RECORD_PREFIX)
    assert [entry.record_id for entry in diff.of(base_diff.CREATED)] == [created]


def test_ac3_an_edited_record_carries_field_level_detail():
    """Which cells moved, from what, to what — the plan is not a boolean."""
    _, _, (main, _ref) = scratch_tables()
    snapshot = snapshot_of(main)
    record = snapshot.records[0]
    before = record.value("Text")
    draft = snapshot.edit()
    draft.set(record.record_id, "Text", "Text 1 — moved")
    change, = draft.diff().record(record.record_id).changes

    assert (change.field_name, change.before, change.after) == (
        "Text", before, "Text 1 — moved")
    assert change.pair == (1, "Text")
    assert change.field_id == snapshot.field("Text").field_id


def test_ac3_a_no_op_edit_leaves_the_record_unchanged():
    """Writing back the value that is already there is not a change, and the plan says so —
    an edit that moves nothing must not become a request."""
    _, _, (main, _ref) = scratch_tables()
    snapshot = snapshot_of(main)
    record = snapshot.records[0]
    draft = snapshot.edit()
    draft.set(record.record_id, "Text", record.value("Text"))
    entry = draft.diff().record(record.record_id)
    assert entry.disposition == base_diff.UNCHANGED
    assert entry.changes == ()


def test_ac3_the_disposition_vocabulary_is_closed():
    _, _, (main, _ref) = scratch_tables()
    diff = snapshot_of(main).edit().diff()
    with pytest.raises(ValueError):
        diff.of("probably-fine")
    assert diff.touches_nothing is True


# --------------------------------------------------------------------------- #
# AC4 — computed fields are a mirror, never a master                           #
# --------------------------------------------------------------------------- #

def test_ac4_the_model_carries_every_computed_value_for_reading():
    """A consumer can *see* a Lookup and a Stage. The model just never lets one be written."""
    app, tables, (main, _ref) = scratch_tables()
    snapshot = snapshot_of(main)
    names = [spec.field_name for spec in snapshot.fields]
    assert "lookup" in names and "stage?" in names
    assert snapshot.records[0].value("lookup") != ""


@pytest.mark.parametrize("pair", NON_WRITABLE_PAIRS, ids=lambda pair: pair[1])
def test_ac4_one_refusal_per_non_writable_type(pair):
    """All eight computed / opaque pairs, **imported** from LD-255's constant — this story
    does not re-list them. An edit to one is a typed refusal at diff time, naming the type,
    with LD-255's own reason quoted rather than paraphrased."""
    field_type, ui_type = pair
    spec = FieldSpec(field_name=ui_type, type=field_type, ui_type=ui_type,
                     field_id=f"fld{ui_type}")
    snapshot = snapshot_of(one_field_table(spec))
    draft = snapshot.edit()
    draft.set("rec1", ui_type, "a value the server owns")
    entry = draft.diff().record("rec1")

    assert entry.disposition == base_diff.REFUSED
    refusal, = entry.refusals
    assert refusal.pair == pair
    assert refusal.field_name == ui_type
    assert refusal.reason == NON_WRITABLE_REASONS[pair]


def test_ac4_a_refusal_is_a_disposition_not_an_exception():
    """The caller gets a plan that says why, not a traceback — and the plan does not
    half-apply: one refused cell refuses the whole record."""
    spec = FieldSpec(field_name="Formula", type=20, ui_type="Formula", field_id="fldF")
    snapshot = snapshot_of(one_field_table(spec))
    draft = snapshot.edit()
    draft.set("rec1", "Text", "this one is writable")
    draft.set("rec1", "Formula", "this one is not")
    entry = draft.diff().record("rec1")
    assert entry.disposition == base_diff.REFUSED
    assert [change.field_name for change in entry.changes] == ["Text", "Formula"]
    assert len(entry.refusals) == 1


def test_ac4_a_created_record_that_names_a_computed_field_is_refused_too():
    spec = FieldSpec(field_name="AutoNumber", type=1005, ui_type="AutoNumber", field_id="fldA")
    snapshot = snapshot_of(one_field_table(spec))
    draft = snapshot.edit()
    local_id = draft.add(Text="new row", AutoNumber="42")
    entry = draft.diff().record(local_id)
    assert entry.disposition == base_diff.REFUSED
    assert entry.refusals[0].pair == (1005, "AutoNumber")


def test_ac4_lookup_is_a_formula_style_wrapper_typed_as_its_TARGET_field():
    """**The Lookup trap** (`p1-q0-03` § 2). A Lookup cell is *not* encoded as `type: 19`: it
    is a Formula-style typed wrapper whose `type` is the **TARGET field's** type — here `1`,
    a Text field — and whose `value` is a **segment array in which `LISTCOMBINE`'s separators
    are themselves segments**, so the join is `""` and inserting one would double every comma.

    Render what the server sent; never re-derive it, and never write it back.
    """
    per_table = capture("p1-q0-03-per-table.json")["per_table"]
    entry = per_table[0]
    raw = entry["records_search"]["response"]["data"]["items"][0]["fields"]["lookup"]
    assert raw["type"] == 1, "the wrapper's type is the TARGET field's, not 19"
    assert [seg["text"] for seg in raw["value"]][1] == ","

    app, tables, (main, _ref) = scratch_tables()
    snapshot = snapshot_of(main)
    specs = list(snapshot.fields)
    expected = render_row(
        entry["records_search"]["response"]["data"]["items"][0]["fields"], specs)
    assert tuple(value for _, value in snapshot.records[0].cells) == tuple(expected)
    # The separators are segments, so consecutive values sit comma-joined with no extra one.
    assert ",," not in snapshot.records[0].value("lookup")

    draft = snapshot.edit()
    draft.set(snapshot.records[0].record_id, "lookup", "something else")
    refused = draft.diff().record(snapshot.records[0].record_id)
    assert refused.disposition == base_diff.REFUSED
    assert refused.refusals[0].pair == (19, "Lookup")


# --------------------------------------------------------------------------- #
# AC5 — the cross-table boundary is explicit                                   #
# --------------------------------------------------------------------------- #

def test_ac5_i_a_dangling_single_link_is_a_normal_state_not_an_error():
    """`p0-2-07`: after the linked record `recvrftvdQu0a2` was deleted, `SingleLinkOne` and
    `SingleLinkMany` **still hold its id**. The model represents that verbatim — it never
    dereferences a link, so it has no way to know the id is dead and no business raising."""
    fields, rows = link_zoo_after_target_record_delete()
    snapshot = snapshot_of(assemble_table(table_id="tblMain", name="main",
                                          fields=fields, records=rows))
    dangler = snapshot.record("recvrhtjicR6ig")
    assert "recvrftvdQu0a2" in dangler.value("SingleLinkMany")
    assert "recvrftvdQu0a2" in dangler.value("SingleLinkOne")
    # The symmetric link read back `[]` on the same row — a different fact about emptiness.
    assert dangler.value("DuplexLink") == ""
    # And the diff of an untouched model is quiet about all of it.
    assert snapshot.edit().diff().touches_nothing is True


def test_ac5_i_a_dangling_id_can_still_be_edited_away():
    fields, rows = link_zoo_after_target_record_delete()
    snapshot = snapshot_of(assemble_table(table_id="tblMain", name="main",
                                          fields=fields, records=rows))
    draft = snapshot.edit()
    draft.set("recvrhtjicR6ig", "SingleLinkOne", "")
    entry = draft.diff().record("recvrhtjicR6ig")
    assert entry.disposition == base_diff.EDITED
    assert entry.changes[0].before == "recvrftvdQu0a2"
    assert entry.cross_table == ()  # a one-way link has no mirror


def test_ac5_ii_an_edit_to_a_duplexlink_discloses_its_cross_table_effect():
    """`p0-2-05`: writing a symmetric link auto-populates the mirror field in the **linked**
    table — the server does it, with **no write to that table at all**. So the plan discloses
    the effect and names the other table; it does not perform it."""
    fields, rows = link_zoo_after_target_record_delete()
    snapshot = snapshot_of(assemble_table(table_id="tblMain", name="main",
                                          fields=fields, records=rows))
    draft = snapshot.edit()
    draft.set("recvrivuozcodN", "DuplexLink", "recvrftvdQu0a2")
    entry = draft.diff().record("recvrivuozcodN")

    effect, = entry.cross_table
    assert effect.field_name == "DuplexLink"
    assert effect.pair == (21, "DuplexLink")
    assert effect.table_id == "tblauNkOg3QoDL99"
    assert effect.table_name == "p0zoo-Ref-033103"
    assert effect.dangling_target is False
    assert "mirror" in effect.effect


def test_ac5_ii_the_mirror_effect_puts_no_entry_in_the_other_tables_plan():
    """The disclosure is the whole of it: the linked table's own diff stays empty, because
    nothing in this plan writes there."""
    app, tables, assembled = scratch_tables()
    base_read = assemble_base(app_token=app.app_token, name=app.name,
                              time_zone=app.time_zone, tables=assembled)
    main_id, ref_id = (table.table_id for table in base_read.tables)
    snapshot = snapshot_base(
        base_read,
        revisions={main_id: 18, ref_id: 0},
        read_proofs={main_id: EXHAUSTED, ref_id: EXHAUSTED})
    draft = snapshot.edit()
    draft.table(main_id).set(snapshot.table(main_id).records[0].record_id, "Text", "moved")
    diff = draft.diff()
    assert diff.table(main_id).touches_nothing is False
    assert diff.table(ref_id).touches_nothing is True
    assert diff.table(ref_id).of(base_diff.EDITED) == ()


def test_ac5_iii_a_link_whose_table_name_dropped_out_is_a_dangling_target():
    """`p0-5-02`, found by accident and kept as a detector: delete the whole **target table**
    and the link field's schema keeps `property.table_id` while `table_name` **vanishes**. A
    healthy link field carries both, so the asymmetry is the signal."""
    dangling = dangling_target_field()
    healthy = FieldSpec.from_payload(link_field_payloads()["SingleLinkMany"])
    assert base_diff.has_dangling_target(dangling) is True
    assert base_diff.has_dangling_target(healthy) is False

    table = assemble_table(
        table_id="tblMain", name="main", fields=[healthy, dangling],
        records=[{"record_id": "rec1",
                  "fields": {"SLink": {"link_record_ids": ["recvrsK0tN2SKV"]}}}])
    snapshot = snapshot_of(table)
    assert snapshot.dangling_link_targets == ("SLink",)

    draft = snapshot.edit()
    draft.set("rec1", "SLink", "")
    effect, = draft.diff().record("rec1").cross_table
    assert effect.dangling_target is True
    assert effect.table_id == "tblsT2Ons4CcdJgY"
    assert effect.table_name is None


def test_ac5_the_model_holds_no_resolution_of_any_link():
    """Resolution is the Base relational spec's. Nothing here turns a record id into a record."""
    fields, rows = link_zoo_after_target_record_delete()
    snapshot = snapshot_of(assemble_table(table_id="tblMain", name="main",
                                          fields=fields, records=rows))
    for name in ("resolve", "resolve_links", "dereference", "fetch"):
        assert not hasattr(snapshot, name)


# --------------------------------------------------------------------------- #
# AC8 — determinism                                                            #
# --------------------------------------------------------------------------- #

def test_ac8_the_same_snapshot_and_edits_twice_yield_an_identical_plan():
    _, _, (main, _ref) = scratch_tables()
    snapshot = snapshot_of(main)

    def build():
        draft = snapshot.edit()
        draft.set(snapshot.records[0].record_id, "Text", "moved")
        draft.delete(snapshot.records[1].record_id)
        draft.add(Text="brand new")
        return draft.diff()

    assert build() == build()


def test_ac8_cell_changes_come_out_in_field_order_not_the_order_they_were_named():
    """Ordering is the **schema's** — `GET …/fields` order, the same projection L1 renders a
    row against — so naming the cells backwards cannot change the plan."""
    _, _, (main, _ref) = scratch_tables()
    snapshot = snapshot_of(main)
    record = snapshot.records[0]
    names = [spec.field_name for spec in snapshot.fields if spec.field_name in ("Text", "Email")]
    assert names == ["Text", "Email"]

    draft = snapshot.edit()
    draft.update(record.record_id, {"Email": "later@example.invalid", "Text": "moved"})
    entry = draft.diff().record(record.record_id)
    assert [change.field_name for change in entry.changes] == ["Text", "Email"]


def test_ac8_added_records_follow_the_snapshot_in_the_order_they_were_added():
    _, _, (main, _ref) = scratch_tables()
    snapshot = snapshot_of(main)
    draft = snapshot.edit()
    first = draft.add(Text="one")
    second = draft.add(Text="two")
    order = [entry.record_id for entry in draft.diff().dispositions]
    assert order == list(snapshot.record_ids) + [first, second]


# --------------------------------------------------------------------------- #
# The spec's test-rigor amplifiers                                              #
# --------------------------------------------------------------------------- #

def test_amplifier_the_absent_key_rule_meets_the_diff():
    """An empty cell is an **absent key** in `records/search` — a populated-but-empty column
    appears in no record at all. So a `before` here is what that field's *absence* renders as,
    not a `KeyError`, and an edit to it is an ordinary change."""
    per_table = capture("p1-q0-03-per-table.json")["per_table"][0]
    fields = per_table["fields"]["response"]["data"]["items"]
    records = copy.deepcopy(per_table["records_search"]["response"]["data"]["items"])
    del records[0]["fields"]["Email"]          # the ragged shape, made explicit
    snapshot = snapshot_of(assemble_table(table_id="tbl1", name="t",
                                          fields=fields, records=records))
    ragged = snapshot.records[0]
    assert ragged.value("Email") == ""

    draft = snapshot.edit()
    draft.set(ragged.record_id, "Email", "someone@example.invalid")
    change, = draft.diff().record(ragged.record_id).changes
    assert (change.before, change.after) == ("", "someone@example.invalid")


def test_amplifier_a_record_deleted_in_lark_since_the_snapshot_is_invisible_to_the_diff():
    """The model still holds it; the diff **cannot know**. Nothing here re-reads, so the only
    thing that catches it is LD-259's compare-and-swap against the anchor this diff carries —
    and the test asserts that is the only signal available."""
    per_table = capture("p1-q0-03-per-table.json")["per_table"][0]
    fields = per_table["fields"]["response"]["data"]["items"]
    records = per_table["records_search"]["response"]["data"]["items"]
    snapshot = snapshot_of(assemble_table(table_id="tbl1", name="t",
                                          fields=fields, records=records), revision=18)

    # Lark, meanwhile: one record is gone and the table's revision has moved.
    fresh = snapshot_of(assemble_table(table_id="tbl1", name="t", fields=fields,
                                       records=records[1:]), revision=19)

    draft = snapshot.edit()
    draft.set(snapshot.records[0].record_id, "Text", "moved")
    diff = draft.diff()
    # Blind: the vanished record is still `unchanged`, and the edit is still `edited`.
    assert diff.record(snapshot.records[0].record_id).disposition == base_diff.EDITED
    assert len(diff.dispositions) == len(snapshot.records)
    assert snapshot.records[0].record_id not in fresh.record_ids
    # The one signal that exists is the anchor, and it is the diff's own.
    assert diff.revision == 18 != fresh.revision


def test_amplifier_a_record_added_beside_the_one_it_was_cloned_from_being_deleted():
    _, _, (main, _ref) = scratch_tables()
    snapshot = snapshot_of(main)
    original = snapshot.records[0]
    draft = snapshot.edit()
    clone = draft.add(dict(original.as_dict()))
    draft.delete(original.record_id)
    diff = draft.diff()

    assert diff.record(original.record_id).disposition == base_diff.DELETED
    created = diff.record(clone)
    assert created.disposition == base_diff.REFUSED, "the clone carries the Lookup and Stage"
    assert {refusal.pair for refusal in created.refusals} == {(19, "Lookup"), (24, "Stage")}

    writable = {name: value for name, value in original.cells
                if name in ("Text", "Email")}
    second = snapshot.edit()
    second.delete(original.record_id)
    clean = second.add(writable)
    assert second.diff().record(clean).disposition == base_diff.CREATED


# --------------------------------------------------------------------------- #
# Edit-time refusals — a typo is a programming error, not a plan entry         #
# --------------------------------------------------------------------------- #

def test_an_edit_naming_an_unknown_field_is_refused_at_edit_time():
    _, _, (main, _ref) = scratch_tables()
    snapshot = snapshot_of(main)
    with pytest.raises(UnknownField):
        snapshot.edit().set(snapshot.records[0].record_id, "Txet", "typo")
    with pytest.raises(UnknownField):
        snapshot.edit().add(Txet="typo")


def test_an_edit_naming_an_unknown_record_is_refused_at_edit_time():
    """Identity comes from the record id, never from content — so an id the snapshot does not
    hold is not a create, it is a mistake."""
    _, _, (main, _ref) = scratch_tables()
    with pytest.raises(UnknownRecord):
        snapshot_of(main).edit().set("recNOPE", "Text", "x")


def test_a_record_cannot_be_both_written_and_removed():
    _, _, (main, _ref) = scratch_tables()
    snapshot = snapshot_of(main)
    record_id = snapshot.records[0].record_id
    draft = snapshot.edit()
    draft.delete(record_id)
    with pytest.raises(BaseModelError):
        draft.set(record_id, "Text", "moved")

    other = snapshot.edit()
    other.set(record_id, "Text", "moved")
    other.delete(record_id)
    assert other.pending_edits == {}
    assert other.diff().record(record_id).disposition == base_diff.DELETED


def test_the_draft_never_changes_the_snapshot_it_was_taken_from():
    _, _, (main, _ref) = scratch_tables()
    snapshot = snapshot_of(main)
    frozen = json.dumps([[record.record_id, list(record.cells)]
                         for record in snapshot.records], ensure_ascii=False)
    draft = snapshot.edit()
    draft.set(snapshot.records[0].record_id, "Text", "moved")
    draft.delete(snapshot.records[1].record_id)
    draft.add(Text="new")
    draft.diff()
    assert json.dumps([[record.record_id, list(record.cells)]
                       for record in snapshot.records], ensure_ascii=False) == frozen


# --------------------------------------------------------------------------- #
# LD-631 — `RecordDisposition.is_new`, falsified.                              #
#                                                                              #
# The accessor is public on a public dataclass and nothing in this repository   #
# read the name, so the one-line rule it encodes — "new" means CREATED and      #
# nothing else — had no test. It is asserted over the WHOLE disposition         #
# vocabulary, so a disposition added to `DISPOSITIONS` enrols itself instead of #
# quietly reading as not-new.                                                  #
# --------------------------------------------------------------------------- #

def test_is_new_is_TRUE_FOR_CREATED_AND_FALSE_FOR_EVERY_OTHER_DISPOSITION():
    """Over the closed vocabulary, not over a hand-picked pair: exactly one member of
    ``DISPOSITIONS`` reads as new, and it is ``CREATED``."""
    assert base_diff.DISPOSITIONS, "the vocabulary is empty; nothing was checked"
    new_ones = [d for d in base_diff.DISPOSITIONS
                if base_diff.RecordDisposition(record_id="r", disposition=d).is_new]
    assert new_ones == [base_diff.CREATED]


def test_is_new_agrees_with_the_REAL_DIFF_on_every_record_it_produced():
    """The same rule through the shipped path: the record added in memory is the only one the
    diff reports as new, and `is_new` and `disposition` cannot disagree about any of them."""
    _, _, (main, _ref) = scratch_tables()
    snapshot = snapshot_of(main)
    draft = snapshot.edit()
    draft.set(snapshot.records[0].record_id, "Text", "moved")
    draft.delete(snapshot.records[1].record_id)
    created = draft.add(Text="brand new")

    diff = draft.diff()
    assert [e.record_id for e in diff.dispositions if e.is_new] == [created]
    for entry in diff.dispositions:
        assert entry.is_new is (entry.disposition == base_diff.CREATED)
