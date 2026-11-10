"""LD-269 — opt-in cross-table link resolution.

Every test here is offline. The fixtures are the **committed probe captures**
(`tests/captures/base-study/captures/`) round-tripped through the pinned SDK's own deserializer, so an
API drift reddens **at deserialization** rather than travelling on as a wrong render
(PROJECT.md § Quality bar).

The four disciplines this file exists to hold:

1. **OFF is byte-identical.** The default read path makes no resolution call and renders the
   same bytes L1 always rendered — the opt-in deep-read precedent.
2. **The call count is a function of TARGET TABLES, never of cells.** The throttle posture
   (≥1.2 s spacing, limits deliberately unprobed) makes an N+1 resolver a rate-limit incident;
   the deliberate-defect test turns the batch into a loop and proves the guard reddens.
3. **`1254043 RecordIdNotFound` is a NORMAL case.** It never raises, and the per-cell answer
   is typed — resolved / dangling / unresolvable — with the honest third state carrying no
   claim in either direction (LD-267's `cannot-determine` discipline, per cell).
4. **The display field is the target's SCHEMA-DESIGNATED primary field**, never "the first
   column".
"""
import json
from pathlib import Path

import pytest
from lark_oapi.api.bitable.v1 import (
    AppTableField,
    AppTableRecord,
    BatchGetAppTableRecordResponse,
)
from lark_oapi.core.json import JSON

from larkdocio.base import cells as base_cells
from larkdocio.base import link_resolution as lr
from larkdocio.base import ops as base_ops
from larkdocio.base import table as base_table
from larkdocio.base.cells import FieldSpec, RenderContext
from larkdocio.errors import LarkAPIError, LarkConfigError

_REPO = Path(__file__).resolve().parent.parent
_CAPTURES = _REPO / "tests" / "captures" / "base-study" / "captures"

#: The two tables of the link zoo, as the field-schema probe read them back.
MAIN_TABLE = "tblMWxK1iJYvK56l"
REF_TABLE = "tblauNkOg3QoDL99"


def capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def unmarshal(payload, cls):
    return JSON.unmarshal(json.dumps(payload), cls)


def _schema():
    """`(main_fields, ref_fields)` — raw captured field dicts, in table order."""
    data = capture("p0-2-03-field-schema-full.json")["response"]["data"]
    return data["main"], data["ref"]


def _rows():
    """`(main_rows, ref_rows)` — raw captured records from the link-encoding probe."""
    data = capture("p0-2-05-link-lookup-read-encodings.json")["response"]["data"]
    return data["main_rows"], data["ref_rows"]


def sdk_fields(raw):
    """Captured field dicts → the SDK-typed objects the client hands back."""
    return [unmarshal(item, AppTableField) for item in raw]


def sdk_records(raw):
    return [unmarshal(item, AppTableRecord) for item in raw]


def specs(raw):
    return [base_table.field_spec(item) for item in sdk_fields(raw)]


def batch_get_body(records, *, absent=(), forbidden=()):
    """A `records/batch_get` response in the wire shape `03-records-batch-get.json` pins."""
    return unmarshal({
        "code": 0,
        "msg": "success",
        "data": {
            "records": list(records),
            "absent_record_ids": list(absent),
            "forbidden_record_ids": list(forbidden),
        },
    }, BatchGetAppTableRecordResponse).data


class SpyClient:
    """Stands in for `BaseReadClient`, exposing exactly the two methods the resolver uses.

    It counts every call and records what it was asked for, so a test can assert the *shape*
    of the traffic (K target tables, deduplicated ids, chunk boundaries) rather than only the
    answer that came back.
    """

    def __init__(self, tables, *, absent=(), forbidden=(), raise_code=None,
                 dead=(), dead_code=1254041, dead_msg="TableIdNotFound",
                 dead_on=("list_fields", "batch_get_records")):
        #: `{table_id: (raw_fields, raw_records)}`
        self._tables = tables
        self.absent = set(absent)
        self.forbidden = set(forbidden)
        self.raise_code = raise_code
        #: Tables that are GONE (LD-278). Every verb in `dead_on` answers `dead_code` for
        #: them — the state a deleted target table really leaves behind.
        self.dead = set(dead)
        self.dead_code = dead_code
        self.dead_msg = dead_msg
        self.dead_on = tuple(dead_on)
        self.calls = []
        self.api_calls = 0

    def _refuse_if_dead(self, verb, table_id):
        """The refusal is raised AFTER the call is counted — a call really was spent."""
        if table_id in self.dead and verb in self.dead_on:
            raise LarkAPIError(f"{verb} on {table_id} failed", code=self.dead_code,
                               msg=self.dead_msg)

    def list_fields(self, app_token, table_id):
        self.api_calls += 1
        self.calls.append(("list_fields", table_id, ()))
        self._refuse_if_dead("list_fields", table_id)
        return sdk_fields(self._tables[table_id][0])

    def batch_get_records(self, app_token, table_id, record_ids):
        ids = tuple(record_ids)
        self.api_calls += 1
        self.calls.append(("batch_get_records", table_id, ids))
        self._refuse_if_dead("batch_get_records", table_id)
        if self.raise_code is not None:
            raise LarkAPIError("boom", code=self.raise_code, msg="RecordIdNotFound")
        rows = {r["record_id"]: r for r in self._tables[table_id][1]}
        found = [rows[i] for i in ids
                 if i in rows and i not in self.absent and i not in self.forbidden]
        return batch_get_body(
            found,
            absent=[i for i in ids if i in self.absent or i not in rows],
            forbidden=[i for i in ids if i in self.forbidden],
        )

    @property
    def batch_calls(self):
        return [c for c in self.calls if c[0] == "batch_get_records"]

    @property
    def field_calls(self):
        return [c for c in self.calls if c[0] == "list_fields"]


def zoo_client(**kwargs):
    main_fields, ref_fields = _schema()
    main_rows, ref_rows = _rows()
    return SpyClient({MAIN_TABLE: (main_fields, main_rows),
                      REF_TABLE: (ref_fields, ref_rows)}, **kwargs)


def resolve(client, sources=None, **kwargs):
    main_fields, _ = _schema()
    main_rows, _ = _rows()
    if sources is None:
        sources = [(MAIN_TABLE, specs(main_fields), sdk_records(main_rows))]
    return lr.resolve_links(client=client, app_token="appX", sources=sources, **kwargs)


# --------------------------------------------------------------------------- #
# AC1 — resolution is OPT-IN, OFF by default, and OFF means BYTE-IDENTICAL.    #
# --------------------------------------------------------------------------- #

def test_ac1_a_default_render_of_link_cells_is_byte_identical_to_L1s():
    """The fixture carries all three shapes AC1 names — populated links, `null` links and
    `[]` links — and the default context renders exactly what it always did: the ids."""
    main_fields, _ = _schema()
    main_rows, _ = _rows()
    field_specs = specs(main_fields)
    default = base_table.assemble_table(
        table_id=MAIN_TABLE, name="main", fields=field_specs, records=sdk_records(main_rows))
    rendered = base_table.render_table(default)
    assert "recvrftvdQu0a2" in rendered, "L1 renders the record ids"
    assert "R1" not in rendered, "nothing was resolved with the flag absent"
    # The empty forms render empty, exactly as the Base read spec § F1-S1 AC3 pinned them.
    assert default.rows[0].cells[field_specs.index(
        next(f for f in field_specs if f.field_name == "SingleLinkOne"))] == ""


def test_ac1_the_render_context_carries_NO_resolution_by_default():
    assert RenderContext().links is None
    assert base_table._DEFAULT_CONTEXT.links is None


def test_ac1_a_resolution_attached_to_the_context_is_the_ONLY_thing_that_changes_bytes():
    """Same fixture, same assembler, one difference: the resolution. The two renders must
    differ in exactly the link columns and nowhere else."""
    main_fields, _ = _schema()
    main_rows, _ = _rows()
    field_specs = specs(main_fields)
    client = zoo_client()
    resolution = resolve(client)
    off = base_table.render_table(base_table.assemble_table(
        table_id=MAIN_TABLE, name="main", fields=field_specs, records=sdk_records(main_rows)))
    on = base_table.render_table(base_table.assemble_table(
        table_id=MAIN_TABLE, name="main", fields=field_specs, records=sdk_records(main_rows),
        context=RenderContext(links=resolution)))
    assert off != on
    assert "R1" in on and "R1" not in off
    # Every non-link column is untouched: the two renders differ only where an id was.
    assert off.replace("recvrftvdQu0a2", "R1").replace("recvrzucbGOfCz", "R2") \
        .replace("recvrwoqiEOlwS", "R3") == on


def test_ac1_the_default_read_path_makes_ZERO_resolution_calls():
    """The by-construction half: `read_base` without the flag never reaches the resolver."""
    from larkdocio.base import read as base_read
    import inspect

    signature = inspect.signature(base_read.read_base)
    assert signature.parameters["resolve_links"].default is False


# --------------------------------------------------------------------------- #
# AC2 — the resolved value is the target's SCHEMA-DESIGNATED primary field.    #
# --------------------------------------------------------------------------- #

def test_ac2_the_primary_field_comes_from_is_primary_not_from_position():
    """The fixture's primary field is moved OUT of first place, so a positional
    implementation resolves the wrong column and this test is what says so."""
    _, ref_fields = _schema()
    reordered = [f for f in ref_fields if not f.get("is_primary")] + \
                [f for f in ref_fields if f.get("is_primary")]
    assert not reordered[0].get("is_primary"), "the fixture must not have primary first"
    assert lr.primary_field_name(specs(reordered)) == "多行文本"
    assert lr.primary_field_name(specs(reordered)) != reordered[0]["field_name"]


def test_ac2_a_target_whose_primary_is_NOT_FIRST_resolves_the_RIGHT_column():
    main_fields, ref_fields = _schema()
    main_rows, ref_rows = _rows()
    reordered = [f for f in ref_fields if not f.get("is_primary")] + \
                [f for f in ref_fields if f.get("is_primary")]
    client = SpyClient({REF_TABLE: (reordered, ref_rows)})
    resolution = resolve(client)
    # "R1" is the primary (text) value; "10" is what the FIRST column (RefNum) would give.
    assert resolution.text_for(REF_TABLE, "recvrftvdQu0a2") == "R1"
    assert resolution.text_for(REF_TABLE, "recvrftvdQu0a2") != "10"


def test_ac2_the_target_table_id_comes_from_the_link_fields_own_property():
    main_fields, _ = _schema()
    main_rows, _ = _rows()
    wanted = lr.needed_record_ids(specs(main_fields), sdk_records(main_rows))
    assert set(wanted) == {REF_TABLE}, wanted
    # Encounter order — row by row, field by field — and deduplicated, never a set.
    assert wanted[REF_TABLE] == ("recvrftvdQu0a2", "recvrwoqiEOlwS", "recvrzucbGOfCz")


def test_ac2_a_table_with_NO_primary_field_resolves_to_a_typed_unresolvable():
    """No display-field policy is derivable, so nothing is claimed — and nothing crashes."""
    _, ref_fields = _schema()
    _, ref_rows = _rows()
    headless = [dict(f, is_primary=False) for f in ref_fields]
    client = SpyClient({REF_TABLE: (headless, ref_rows)})
    resolution = resolve(client)
    entry = resolution.record_for(REF_TABLE, "recvrftvdQu0a2")
    assert entry.state == lr.LINK_UNRESOLVABLE
    assert not client.batch_calls, "with no display policy there is nothing worth spending a call on"


def test_ac2_a_target_record_whose_PRIMARY_IS_EMPTY_is_a_typed_empty_not_a_placeholder():
    _, ref_fields = _schema()
    _, ref_rows = _rows()
    blanked = [dict(r) for r in ref_rows]
    blanked[0] = dict(blanked[0], fields={k: v for k, v in blanked[0]["fields"].items()
                                          if k != "多行文本"})
    client = SpyClient({REF_TABLE: (ref_fields, blanked)})
    resolution = resolve(client)
    entry = resolution.record_for(REF_TABLE, "recvrftvdQu0a2")
    assert entry.state == lr.LINK_RESOLVED
    assert entry.text == "", "an empty primary is an empty string, never an invented marker"


# --------------------------------------------------------------------------- #
# AC2b — `property.table_id` survives the SDK-typed property seam.             #
# --------------------------------------------------------------------------- #

def test_ac2b_table_id_survives_the_sdk_typed_property_bridge():
    """The resolver READS `property.table_id`, so its survival across `field_spec` is pinned
    on a real captured link column rather than assumed (BASE.md row 12)."""
    main_fields, _ = _schema()
    raw = next(f for f in main_fields if f["field_name"] == "SingleLinkOne")
    projected = base_table.field_spec(unmarshal(raw, AppTableField))
    assert projected.property["table_id"] == raw["property"]["table_id"] == REF_TABLE


def test_ac2b_table_id_is_IN_the_guarded_renderer_key_list():
    """Row 12's drift alarm asserts that no key a renderer READS is in the dropped set. This
    story made `table_id` such a key, so it joins the list the alarm is run against."""
    assert "table_id" in base_table.RENDERER_PROPERTY_KEYS


# --------------------------------------------------------------------------- #
# AC3 — batched, never N+1.                                                    #
# --------------------------------------------------------------------------- #

def test_ac3_the_call_count_is_a_function_of_TARGET_TABLES_not_of_cells():
    """N cells over M distinct records across K=1 table: one batched read, not one per cell."""
    client = zoo_client()
    resolution = resolve(client)
    cells = 9   # three link columns x three rows, of which six are populated
    assert len(client.batch_calls) == 1, client.calls
    assert set(client.batch_calls[0][2]) == {
        "recvrftvdQu0a2", "recvrzucbGOfCz", "recvrwoqiEOlwS"}
    assert resolution.api_calls == client.api_calls
    assert resolution.api_calls < cells


def test_ac3_two_link_columns_at_the_SAME_TARGET_share_ONE_batched_read():
    """The spec's rigor amplifier: `SingleLinkOne`, `SingleLinkMany` and `DuplexLink` all point
    at the ref table, and one read serves all three."""
    client = zoo_client()
    resolve(client)
    assert len(client.batch_calls) == 1
    assert {c[1] for c in client.batch_calls} == {REF_TABLE}


def test_ac3_ids_are_deduplicated_ACROSS_cells_and_ACROSS_rows():
    client = zoo_client()
    resolve(client)
    asked = client.batch_calls[0][2]
    assert len(asked) == len(set(asked))


def test_ac3_two_target_tables_cost_two_reads_and_no_more():
    main_fields, ref_fields = _schema()
    main_rows, ref_rows = _rows()
    client = zoo_client()
    sources = [
        (MAIN_TABLE, specs(main_fields), sdk_records(main_rows)),
        (REF_TABLE, specs(ref_fields), sdk_records(ref_rows)),
    ]
    resolve(client, sources=sources)
    assert {c[1] for c in client.batch_calls} == {MAIN_TABLE, REF_TABLE}
    assert len(client.batch_calls) == 2


def test_ac3_a_batch_bigger_than_the_endpoint_ceiling_is_CHUNKED():
    _, ref_fields = _schema()
    ids = [f"rec{n:08d}" for n in range(250)]
    rows = [{"record_id": i, "fields": {"多行文本": [{"text": i, "type": "text"}]}}
            for i in ids]
    link = FieldSpec(field_name="L", type=18, ui_type="SingleLink",
                     property={"table_id": REF_TABLE, "table_name": "ref"})
    record = type("R", (), {"record_id": "recA", "fields": {"L": {"link_record_ids": ids}}})()
    client = SpyClient({REF_TABLE: (ref_fields, rows)})
    resolution = lr.resolve_links(client=client, app_token="appX",
                                 sources=[("t", [link], [record])])
    assert len(client.batch_calls) == 3, "250 ids at a 100 ceiling is three chunks"
    assert [len(c[2]) for c in client.batch_calls] == [100, 100, 50]
    assert resolution.text_for(REF_TABLE, ids[-1]) == ids[-1]


def test_ac3_DEFECT_resolving_one_id_per_call_reddens_this_guard():
    """The deliberate-defect check the spec asks for: turn the batch into a loop and the
    call-count assertion above must fail."""
    client = zoo_client()
    real = lr.BATCH_GET_MAX_IDS
    try:
        lr.BATCH_GET_MAX_IDS = 1
        resolve(client)
    finally:
        lr.BATCH_GET_MAX_IDS = real
    assert len(client.batch_calls) == 3, "the defect model must actually be N calls"
    with pytest.raises(AssertionError):
        assert len(client.batch_calls) == 1


def test_ac3_a_target_table_ALREADY_READ_costs_no_extra_schema_call():
    """The Base read already holds every table's schema, so resolving inside the same Base
    spends its calls on records and not on re-reading a field list."""
    main_fields, ref_fields = _schema()
    main_rows, _ = _rows()
    client = zoo_client()
    resolve(client, known_schemas={REF_TABLE: specs(ref_fields)})
    assert not [c for c in client.calls if c[0] == "list_fields"]


# --------------------------------------------------------------------------- #
# AC4 — `1254043 RecordIdNotFound` is a NORMAL case and never raises.          #
# --------------------------------------------------------------------------- #

def test_ac4_a_cell_whose_ids_ALL_resolve():
    client = zoo_client()
    resolution = resolve(client)
    assert resolution.text_for(REF_TABLE, "recvrftvdQu0a2") == "R1"
    assert resolution.text_for(REF_TABLE, "recvrzucbGOfCz") == "R2"
    assert all(r.state == lr.LINK_RESOLVED for r in resolution.records.values())


def test_ac4_ONE_OF_TWO_dangling_is_the_partial_case_that_will_actually_happen():
    client = zoo_client(absent=["recvrzucbGOfCz"])
    resolution = resolve(client)
    assert resolution.record_for(REF_TABLE, "recvrftvdQu0a2").state == lr.LINK_RESOLVED
    assert resolution.record_for(REF_TABLE, "recvrzucbGOfCz").state == lr.LINK_DANGLING


def test_ac4_ALL_ids_dangling_still_completes_the_read():
    client = zoo_client(absent=["recvrftvdQu0a2", "recvrzucbGOfCz", "recvrwoqiEOlwS"])
    resolution = resolve(client)
    assert {r.state for r in resolution.records.values()} == {lr.LINK_DANGLING}
    assert resolution.api_calls == client.api_calls


def test_ac4_the_rest_of_the_table_is_UNAFFECTED_in_all_three_cases():
    """The exit status is *the read completed*: every non-link cell renders exactly what it
    renders with no resolution at all, whatever the link cells turned out to be."""
    main_fields, _ = _schema()
    main_rows, _ = _rows()
    field_specs = specs(main_fields)
    plain = base_table.assemble_table(
        table_id=MAIN_TABLE, name="main", fields=field_specs, records=sdk_records(main_rows))
    link_columns = {i for i, f in enumerate(field_specs) if f.type in (18, 21)}
    for kwargs in ({}, {"absent": ["recvrzucbGOfCz"]},
                   {"absent": ["recvrftvdQu0a2", "recvrzucbGOfCz", "recvrwoqiEOlwS"]}):
        client = zoo_client(**kwargs)
        resolved = base_table.assemble_table(
            table_id=MAIN_TABLE, name="main", fields=field_specs,
            records=sdk_records(main_rows),
            context=RenderContext(links=resolve(client)))
        for row_a, row_b in zip(plain.rows, resolved.rows):
            for index, (a, b) in enumerate(zip(row_a.cells, row_b.cells)):
                if index not in link_columns:
                    assert a == b, (index, kwargs)


def test_ac4_a_RAISED_1254043_is_caught_and_typed_never_propagated():
    """The batch shape reports absences in the body; a whole-call `1254043` is the defensive
    other half — a chunk of ONE names its id unambiguously, so that id reads dangling."""
    client = zoo_client(raise_code=1254043)
    real = lr.BATCH_GET_MAX_IDS
    try:
        lr.BATCH_GET_MAX_IDS = 1
        resolution = resolve(client)
    finally:
        lr.BATCH_GET_MAX_IDS = real
    assert {r.state for r in resolution.records.values()} == {lr.LINK_DANGLING}


def test_ac4_a_MULTI_ID_chunk_that_raises_1254043_claims_NOTHING_per_id():
    """Lark named the family, not the id. Guessing which of the batch was missing is exactly
    the confident-wrong-answer LD-267 refuses, so the answer is the honest third state."""
    client = zoo_client(raise_code=1254043)
    resolution = resolve(client)
    assert {r.state for r in resolution.records.values()} == {lr.LINK_UNRESOLVABLE}


def test_ac4_an_error_that_is_NOT_1254043_still_raises():
    """Only the not-found families are normal. A scope denial, or a refusal about the request
    this library built, is a real failure and swallowing it would hide a broken read behind
    plausible-looking markers.

    **The exemplar moved in LD-278** — it used to be `1254041`, which has since become a typed
    answer of its own (a target table that is GONE is exactly the state the flag exists to
    diagnose). `99992402` is the refusal this endpoint really answers for a request it will not
    accept, so the assertion is unchanged and only the code that carries it moved.
    """
    client = zoo_client(raise_code=99992402)
    with pytest.raises(LarkAPIError):
        resolve(client)


def test_ac4_a_FORBIDDEN_record_id_claims_nothing_about_existence():
    client = zoo_client(forbidden=["recvrftvdQu0a2"])
    resolution = resolve(client)
    assert resolution.record_for(REF_TABLE, "recvrftvdQu0a2").state == lr.LINK_UNRESOLVABLE


# --------------------------------------------------------------------------- #
# AC5 — the per-cell result is TYPED and its marker is in the HOUSE REGISTER.  #
# --------------------------------------------------------------------------- #

def test_ac5_the_dangling_markers_exact_bytes_are_pinned():
    assert lr.dangling_marker("recABC") == (
        "[dangling Base link: recABC — the linked record no longer exists in the "
        "target table]")


def test_ac5_the_unresolvable_markers_exact_bytes_are_pinned():
    assert lr.unresolvable_marker("recABC") == (
        "[unresolved Base link: recABC — the target could not be read, so no claim is "
        "made about whether the record exists]")


def test_ac5_both_markers_are_TRACEABLE_they_carry_the_record_id():
    for marker in (lr.dangling_marker("recXYZ"), lr.unresolvable_marker("recXYZ")):
        assert "recXYZ" in marker


def test_ac5_the_markers_are_in_the_SAME_HOUSE_REGISTER_as_the_readers():
    """`[unsupported inline: …]` / `[Unsupported Add-On block: …]` / the Stage cell's
    `[unreadable Base cell: …]` — bracketed, lower-cased opener, `subject: detail`."""
    house = [base_cells.STAGE_OPAQUE_MARKER, base_cells.PERSON_NAME_UNAVAILABLE]
    for marker in (lr.dangling_marker("rec1"), lr.unresolvable_marker("rec1")):
        assert marker.startswith("[") and marker.endswith("]")
        assert ": " in marker
        assert all(m.startswith("[") for m in house)


def test_ac5_the_marker_vocabulary_is_NOT_a_second_copy_of_LD267s():
    """LD-267 owns the COLUMN-level reading; this module owns the CELL-level one and must not
    redefine the column-level states. It imports them."""
    source = (_REPO / "src" / "larkdocio" / "base" / "link_resolution.py").read_text(
        encoding="utf-8")
    assert "from larkdocio.base.referential import" in source
    for slug in ("target-table-live", "target-table-missing", "cannot-determine"):
        assert f'"{slug}"' not in source, f"{slug} is LD-267's to define, not this module's"


def test_ac5_the_three_states_are_exhaustive_and_each_carries_its_meaning():
    assert lr.LINK_RESOLUTION_STATES == (
        lr.LINK_RESOLVED, lr.LINK_DANGLING, lr.LINK_UNRESOLVABLE)
    for state in lr.LINK_RESOLUTION_STATES:
        assert len(lr.STATE_MEANINGS[state]) > 40


def test_ac5_a_dangling_id_RENDERS_its_marker_in_the_cell():
    main_fields, _ = _schema()
    main_rows, _ = _rows()
    client = zoo_client(absent=["recvrftvdQu0a2"])
    table = base_table.assemble_table(
        table_id=MAIN_TABLE, name="main", fields=specs(main_fields),
        records=sdk_records(main_rows), context=RenderContext(links=resolve(client)))
    rendered = base_table.render_table(table)
    assert lr.dangling_marker("recvrftvdQu0a2") in rendered


# --------------------------------------------------------------------------- #
# AC6 — both link types go through ONE path.                                   #
# --------------------------------------------------------------------------- #

def test_ac6_the_resolver_does_not_branch_on_the_field_type():
    """`SingleLink` (18) and `DuplexLink` (21) are recognised by LD-267's storage-type set and
    read identically; the code carries no per-type branch at all."""
    source = (_REPO / "src" / "larkdocio" / "base" / "link_resolution.py").read_text(
        encoding="utf-8")
    import io
    import tokenize

    code = "\n".join(t.string for t in tokenize.generate_tokens(io.StringIO(source).readline)
                     if t.type not in (tokenize.STRING, tokenize.COMMENT))
    assert "SINGLE_LINK" not in code and "DUPLEX_LINK" not in code, (
        "a per-type branch would make the two kinds two code paths")


def test_ac6_one_path_serves_both_kinds_over_the_same_fixture():
    main_fields, _ = _schema()
    main_rows, _ = _rows()
    field_specs = specs(main_fields)
    client = zoo_client()
    resolution = resolve(client)
    table = base_table.assemble_table(
        table_id=MAIN_TABLE, name="main", fields=field_specs,
        records=sdk_records(main_rows), context=RenderContext(links=resolution))
    single = field_specs.index(next(f for f in field_specs if f.field_name == "SingleLinkOne"))
    duplex = field_specs.index(next(f for f in field_specs if f.field_name == "DuplexLink"))
    assert table.rows[1].cells[single] == "R1"
    assert table.rows[1].cells[duplex] == "R1"


def test_ac6_the_MIRROR_field_in_the_target_table_resolves_BACK():
    """The reverse direction is a link cell like any other: the ref table's own DuplexLink
    column points back at the main table and resolves against ITS primary field."""
    main_fields, ref_fields = _schema()
    main_rows, ref_rows = _rows()
    client = zoo_client()
    resolution = resolve(client, sources=[
        (REF_TABLE, specs(ref_fields), sdk_records(ref_rows))])
    assert {c[1] for c in client.batch_calls} == {MAIN_TABLE}
    assert resolution.text_for(MAIN_TABLE, "recvrhtjicR6ig") == "one-link"


def test_ac6_a_multiple_false_column_holding_TWO_ids_resolves_BOTH():
    """`p0-4-06`: `multiple:false` is not a cardinality guarantee — the column accepted two
    ids and the resolver must not silently keep one."""
    _, ref_fields = _schema()
    _, ref_rows = _rows()
    link = FieldSpec(field_name="L", type=18, ui_type="SingleLink",
                     property={"multiple": False, "table_id": REF_TABLE, "table_name": "ref"})
    record = type("R", (), {"record_id": "recA", "fields": {
        "L": {"link_record_ids": ["recvrftvdQu0a2", "recvrzucbGOfCz"]}}})()
    client = SpyClient({REF_TABLE: (ref_fields, ref_rows)})
    resolution = lr.resolve_links(client=client, app_token="appX",
                                 sources=[("t", [link], [record])])
    assert base_cells.render_cell(record.fields["L"], link,
                                  context=RenderContext(links=resolution)) == "R1, R2"


# --------------------------------------------------------------------------- #
# AC7 — the two empty forms are CITED, not re-pinned: zero calls for either.   #
# --------------------------------------------------------------------------- #

def test_ac7_the_two_empty_forms_cost_ZERO_transport_calls():
    _, ref_fields = _schema()
    link = FieldSpec(field_name="L", type=18, ui_type="SingleLink",
                     property={"table_id": REF_TABLE, "table_name": "ref"})
    never_set = type("R", (), {"record_id": "recA",
                               "fields": {"L": {"link_record_ids": None}}})()
    emptied = type("R", (), {"record_id": "recB", "fields": {"L": {"link_record_ids": []}}})()
    client = SpyClient({REF_TABLE: (ref_fields, [])})
    resolution = lr.resolve_links(client=client, app_token="appX",
                                 sources=[("t", [link], [never_set, emptied])])
    assert client.calls == [], "an empty link cell has nothing to resolve"
    assert resolution.api_calls == 0
    assert resolution.tables == ()


def test_ac7_the_two_empty_forms_RENDER_exactly_what_L1_rendered():
    link = FieldSpec(field_name="L", type=18, ui_type="SingleLink",
                     property={"table_id": REF_TABLE, "table_name": "ref"})
    resolution = lr.LinkResolution(records={}, api_calls=0, tables=())
    for value in ({"link_record_ids": None}, {"link_record_ids": []}):
        assert base_cells.render_cell(value, link) == ""
        assert base_cells.render_cell(
            value, link, context=RenderContext(links=resolution)) == ""


# --------------------------------------------------------------------------- #
# AC8 — the read cost is DISCLOSED.                                            #
# --------------------------------------------------------------------------- #

def test_ac8_the_disclosed_call_count_equals_the_OBSERVED_call_count():
    client = zoo_client()
    before = client.api_calls
    resolution = resolve(client)
    assert resolution.api_calls == client.api_calls - before


def test_ac8_the_disclosure_names_WHICH_TABLES_were_touched():
    main_fields, ref_fields = _schema()
    main_rows, ref_rows = _rows()
    client = zoo_client()
    resolution = resolve(client, sources=[
        (MAIN_TABLE, specs(main_fields), sdk_records(main_rows)),
        (REF_TABLE, specs(ref_fields), sdk_records(ref_rows)),
    ])
    assert set(resolution.tables) == {MAIN_TABLE, REF_TABLE}


def test_ac8_the_disclosure_reads_as_a_sentence_a_consumer_can_act_on():
    client = zoo_client()
    resolution = resolve(client)
    sentence = resolution.disclosure
    assert str(resolution.api_calls) in sentence
    assert REF_TABLE in sentence


def test_ac8_the_structured_read_CARRIES_the_disclosure():
    assert base_table.BaseRead(
        app_token="a", name="n", time_zone=None, tables=()).link_resolution is None


# --------------------------------------------------------------------------- #
# AC9 — R12 by construction: every parameter sent is pinned.                    #
# --------------------------------------------------------------------------- #

def test_ac9_the_shipped_request_sends_ONE_body_key():
    """`records/batch_get` is a POST read, and R12's family of trap is that an unrecognised
    body key behaves exactly like the bogus control. The defence is restraint: one key.

    **AMENDED by LD-345, guarantee intact.** The restraint this test names — *nothing is sent
    that the caller did not ask for* — is unchanged. What LD-345 added is `with_shared_url`,
    the one key that rides ONLY when a permalink is requested; the DEFAULT call below still
    sends `record_ids` and nothing else, byte-for-byte what it always sent. The flag-on body is
    pinned in `tests/test_base_record_permalink.py` so the two halves of the guarantee are each
    a test."""
    from larkdocio.base.client import BaseReadClient

    captured = []

    class _Leg:
        pass

    class _Recorder:
        def __call__(self, request, *a, **k):
            captured.append(request)
            return batch_get_response([])

    def batch_get_response(records):
        return unmarshal({"code": 0, "msg": "success",
                          "data": {"records": records, "absent_record_ids": [],
                                   "forbidden_record_ids": []}},
                         BatchGetAppTableRecordResponse)

    sdk = _Leg()
    sdk.bitable = _Leg()
    sdk.bitable.v1 = _Leg()
    sdk.bitable.v1.app_table_record = _Leg()
    sdk.bitable.v1.app_table_record.batch_get = _Recorder()

    class _Limiter:
        def __init__(self):
            self.acquisitions = 0

        def acquire(self):
            self.acquisitions += 1

    limiter = _Limiter()
    client = BaseReadClient("id", "secret", sdk_client=sdk, rate_limiter=limiter)
    client.batch_get_records("appX", REF_TABLE, ["recA", "recB"])
    request = captured[0]
    body = json.loads(JSON.marshal(request.request_body))
    assert list(body) == ["record_ids"], body
    assert body["record_ids"] == ["recA", "recB"]
    assert limiter.acquisitions == 1, "every call passes the shared limiter"

    # AMENDED (LD-345): the flag rides ONLY when the caller asks for a permalink — and the
    # default call above stayed byte-identical, which is the guarantee this test always made.
    client.batch_get_records("appX", REF_TABLE, ["recA"], with_shared_url=True)
    asked = json.loads(JSON.marshal(captured[1].request_body))
    assert set(asked) == {"record_ids", "with_shared_url"} and asked["with_shared_url"] is True


def test_ac9_the_response_is_a_FUNCTION_OF_the_ids_sent():
    """A test that a parameter is *sent* is not a test that it *works*. Offline, what can be
    shown is that the answer tracks the ask — a different ask, a different answer."""
    client = zoo_client()
    one = client.batch_get_records("appX", REF_TABLE, ["recvrftvdQu0a2"])
    two = client.batch_get_records("appX", REF_TABLE, ["recvrzucbGOfCz"])
    assert [r.record_id for r in one.records] == ["recvrftvdQu0a2"]
    assert [r.record_id for r in two.records] == ["recvrzucbGOfCz"]


def test_ac9_the_PARAMETER_FREE_CONTROL_IS_REFUSED_BY_LARK_and_that_is_recorded():
    """**The live arm's first run answered this better than the AC asked.** There is no
    parameter-free control at this endpoint: `record_ids: []` is refused `99992402` with Lark's
    own violation naming *"record_ids (the min len is 1)"*. The endpoint **validates** the key
    rather than swallowing it the way R12's family swallows an unrecognised one — which is the
    cleanest refutation of the hazard there is — so the code is recorded beside the call and
    the live arm asserts it. Nothing here designs around it: the empty ask is simply never sent
    (see the spy test below)."""
    from larkdocio.base.client import BATCH_GET_EMPTY_ASK_REFUSED_CODE
    from larkdocio.base import client as base_client

    assert BATCH_GET_EMPTY_ASK_REFUSED_CODE == 99992402
    doc = base_client.BaseReadClient.batch_get_records.__doc__
    assert "min len is 1" in doc and "99992402" in doc


def test_ac9_the_resolver_NEVER_SENDS_the_ask_lark_refuses():
    """The other half of the finding: a target with no ids is skipped rather than asked about
    with an empty list, so the refusal above is knowledge and never a path this library takes."""
    client = zoo_client()
    resolve(client)
    assert client.batch_calls, "the fixture must actually resolve something"
    assert all(call[2] for call in client.batch_calls), (
        "a batch call was made with zero ids — Lark refuses that, and the resolver must not "
        "be the thing that finds out")


def test_ac9_more_ids_than_the_endpoint_accepts_is_refused_LOCALLY():
    from larkdocio.base.client import BaseReadClient, BATCH_GET_MAX_IDS

    class _Boom:
        def __call__(self, *a, **k):
            raise AssertionError("an over-long batch must never reach Lark")

    class _Leg:
        pass

    sdk = _Leg()
    sdk.bitable = _Leg()
    sdk.bitable.v1 = _Leg()
    sdk.bitable.v1.app_table_record = _Leg()
    sdk.bitable.v1.app_table_record.batch_get = _Boom()

    class _Limiter:
        def acquire(self):
            pass

    client = BaseReadClient("id", "secret", sdk_client=sdk, rate_limiter=_Limiter())
    with pytest.raises(LarkConfigError):
        client.batch_get_records("appX", REF_TABLE, ["r"] * (BATCH_GET_MAX_IDS + 1))


def test_ac9_the_op_descriptors_endpoint_and_verb_match_the_SDK_request_class():
    descriptor = base_ops.op("batch_get_records")
    built = descriptor.request_cls.builder().build()
    assert built.uri == descriptor.endpoint
    assert built.http_method.name == descriptor.http_method == "POST"
    assert descriptor.mutates is False, "batch_get is the SECOND POST READ"


# --------------------------------------------------------------------------- #
# AC12 — determinism, scoped honestly to the SAME RUN.                          #
# --------------------------------------------------------------------------- #

def test_ac12_two_resolutions_of_an_unchanged_base_are_byte_identical():
    main_fields, _ = _schema()
    main_rows, _ = _rows()
    field_specs = specs(main_fields)

    def once():
        client = zoo_client()
        return base_table.render_table(base_table.assemble_table(
            table_id=MAIN_TABLE, name="main", fields=field_specs,
            records=sdk_records(main_rows),
            context=RenderContext(links=resolve(client))))

    assert once() == once()


def test_ac12_the_id_ORDER_asked_for_is_deterministic_not_set_ordered():
    first = zoo_client()
    second = zoo_client()
    resolve(first)
    resolve(second)
    assert first.batch_calls[0][2] == second.batch_calls[0][2]


def test_ac12_the_module_SCOPES_the_determinism_claim_to_the_SAME_RUN():
    doc = lr.__doc__.lower()
    assert "same-run" in doc
    assert "renamed" in doc or "changes between runs" in doc


# --------------------------------------------------------------------------- #
# LD-278 — a target TABLE that is GONE renders, and never raises.              #
#                                                                              #
# The bug: the per-target SCHEMA fetch was unguarded while the record fetch     #
# beside it was carefully typed, so the ONE state the flag exists to diagnose   #
# — a link column pointing at a deleted table — killed the whole read, healthy  #
# columns and healthy tables with it. The seam is WIDER than that one line:     #
# the table family (`1254041` / `1254004`) and the app family (`1002` /         #
# `91402`) can answer EITHER call, and both are answers about the target rather #
# than about a record in it.                                                    #
# --------------------------------------------------------------------------- #

#: The id the dogfood session's `Legacy record` column was left pointing at after its target
#: table was deleted. Carried verbatim so the regression is anchored to the real state.
DEAD_TABLE = "tbltWThUE2N5LHgm"

#: The ids the re-pointed `SingleLinkOne` column holds in the captured rows.
DEAD_IDS = ("recvrftvdQu0a2", "recvrwoqiEOlwS")


def main_schema_pointing_at(dead_table_id=DEAD_TABLE, columns=("SingleLinkOne",)):
    """The captured main schema with `columns` re-pointed at a table that is GONE.

    The id is kept and `table_name` is dropped, which is what a deleted target table really
    reads like (`p0-5-02-symmetric-link-deletion.json`, LD-267's captured signature).
    """
    main_fields, _ = _schema()
    out = []
    for raw in json.loads(json.dumps(main_fields)):
        if raw["field_name"] in columns:
            raw["property"]["table_id"] = dead_table_id
            raw["property"].pop("table_name", None)
        out.append(raw)
    return out


def dead_target_sources(**kwargs):
    main_rows, _ = _rows()
    return [(MAIN_TABLE, specs(main_schema_pointing_at(**kwargs)), sdk_records(main_rows))]


def dead_target_client(dead=(DEAD_TABLE,), **kwargs):
    return zoo_client(dead=dead, **kwargs)


def test_ld278_a_target_table_that_is_GONE_RENDERS_rather_than_raising():
    """The regression, in one line: this call used to raise `1254041` out of `list_fields`."""
    client = dead_target_client()
    resolution = lr.resolve_links(client=client, app_token="appX",
                                  sources=dead_target_sources())
    assert client.field_calls, "the schema call must really have been attempted"
    for record_id in DEAD_IDS:
        entry = resolution.record_for(DEAD_TABLE, record_id)
        assert entry is not None, record_id
        assert entry.state == lr.LINK_UNRESOLVABLE
        assert entry.dangling is False, "an unreadable target claims NOTHING in either direction"


def test_ld278_the_HEALTHY_targets_of_the_SAME_read_still_resolve():
    """The blast radius is the point: one dead target must not take the live ones with it."""
    client = dead_target_client()
    resolution = lr.resolve_links(client=client, app_token="appX",
                                  sources=dead_target_sources())
    live = resolution.record_for(REF_TABLE, "recvrftvdQu0a2")
    assert live.state == lr.LINK_RESOLVED and live.text
    assert resolution.record_for(DEAD_TABLE, "recvrftvdQu0a2").state == lr.LINK_UNRESOLVABLE, (
        "the same record id under two targets is two answers — the key is (table, record)")


@pytest.mark.parametrize("code", lr.TARGET_UNREADABLE_CODES + lr.BASE_UNREADABLE_CODES)
def test_ld278_the_WHOLE_SEAM_degrades_not_only_the_one_code(code):
    """`1254041` is the observed one; `1254004` (malformed id) and the app-level `1002` /
    `91402` are the same family — an answer about the target, not about a record in it."""
    client = dead_target_client(dead_code=code)
    resolution = lr.resolve_links(client=client, app_token="appX",
                                  sources=dead_target_sources())
    assert {resolution.record_for(DEAD_TABLE, i).state for i in DEAD_IDS} == {
        lr.LINK_UNRESOLVABLE}


def test_ld278_the_seam_covers_the_RECORD_call_too_not_only_the_schema_call():
    """A caller that hands the schema in (`known_schemas`) never makes the field call at all,
    so the FIRST call to meet the dead table is `records/batch_get` — the same answer, reached
    down the other half of the seam."""
    main_fields, ref_fields = _schema()
    client = dead_target_client(dead_on=("batch_get_records",))
    resolution = lr.resolve_links(
        client=client, app_token="appX", sources=dead_target_sources(),
        known_schemas={DEAD_TABLE: specs(ref_fields), MAIN_TABLE: specs(main_fields)})
    assert not [c for c in client.field_calls if c[1] == DEAD_TABLE]
    assert {resolution.record_for(DEAD_TABLE, i).state for i in DEAD_IDS} == {
        lr.LINK_UNRESOLVABLE}


def test_ld278_a_dead_target_is_ASKED_ABOUT_ONCE_however_many_chunks_it_would_take():
    """Gentleness, not tidiness: the pace is ≥1.2 s a call and the answer is about the TABLE,
    so re-asking per chunk would spend calls to be told the same thing."""
    _, ref_fields = _schema()
    client = dead_target_client(dead_on=("batch_get_records",))
    real = lr.BATCH_GET_MAX_IDS
    try:
        lr.BATCH_GET_MAX_IDS = 1
        resolution = lr.resolve_links(
            client=client, app_token="appX", sources=dead_target_sources(),
            known_schemas={DEAD_TABLE: specs(ref_fields)})
    finally:
        lr.BATCH_GET_MAX_IDS = real
    dead_batches = [c for c in client.batch_calls if c[1] == DEAD_TABLE]
    assert len(dead_batches) == 1, dead_batches
    assert {resolution.record_for(DEAD_TABLE, i).state for i in DEAD_IDS} == {
        lr.LINK_UNRESOLVABLE}


def test_ld278_an_APP_LEVEL_answer_spends_NO_call_on_the_remaining_targets():
    """`1002` / `91402` are answers about the BASE. Every remaining target would be refused
    identically, so the resolver stops calling and types the rest — the same blast-radius
    reading `larkdocio.base.disposition` calls SYSTEMIC on the write path."""
    other = "tblGONE0000000002"
    sources = dead_target_sources(columns=("SingleLinkOne",))
    second = [(MAIN_TABLE,
               specs(main_schema_pointing_at(other, columns=("SingleLinkMany",))),
               sdk_records(_rows()[0]))]
    client = dead_target_client(dead=(DEAD_TABLE, other), dead_code=1002, dead_msg="deleted")
    resolution = lr.resolve_links(client=client, app_token="appX",
                                  sources=sources + second)
    assert len(client.field_calls) == 1, client.calls
    assert {r.state for r in resolution.records.values()} == {lr.LINK_UNRESOLVABLE}


def test_ld278_an_error_OUTSIDE_the_family_still_raises_from_the_SCHEMA_call():
    """The other half of the contract, mirrored from AC4: swallowing everything would hide a
    broken read behind plausible-looking markers."""
    client = dead_target_client(dead_code=99992402, dead_msg="field validation failed")
    with pytest.raises(LarkAPIError):
        lr.resolve_links(client=client, app_token="appX", sources=dead_target_sources())


def test_ld278_the_degraded_answer_uses_the_SHIPPED_vocabulary_not_a_second_copy():
    """LD-267/LD-269's words, unchanged: the marker, the state and the meaning all come from
    what already ships. This fix adds no vocabulary."""
    client = dead_target_client()
    resolution = lr.resolve_links(client=client, app_token="appX",
                                  sources=dead_target_sources())
    entry = resolution.record_for(DEAD_TABLE, DEAD_IDS[0])
    assert entry.text == lr.unresolvable_marker(DEAD_IDS[0])
    assert entry.state in lr.LINK_RESOLUTION_STATES
    assert entry.note == lr.STATE_MEANINGS[lr.LINK_UNRESOLVABLE]
    assert "no claim is made" in entry.note.lower()


def test_ld278_the_code_family_is_the_ONE_taxonomys_rows_not_a_second_definition():
    from larkdocio.base import disposition
    from larkdocio.base.errors import BASE_ERROR_CODES

    family = set(lr.TARGET_UNREADABLE_CODES) | set(lr.BASE_UNREADABLE_CODES)
    assert family <= set(BASE_ERROR_CODES), "a code with no row in the Base error taxonomy"
    assert set(disposition.SYSTEMIC_CODES) <= family, (
        "the write path's systemic reading and the resolver's unreadable-target reading are "
        "the same blast-radius fact; a code in one and not the other is a drift")
    assert lr.RECORD_ID_NOT_FOUND_CODE not in family, (
        "a record that is gone is a DANGLING answer, never an unreadable target")


def test_ld278_read_base_with_the_flag_ON_RETURNS_A_DOCUMENT_when_a_target_table_is_gone():
    """The bug as the consumer met it: `read_base(app_token, resolve_links=True)` died on the
    one Base the flag exists for. End to end, through the shipped read path."""
    from base_captures import scratch_base
    from larkdocio.base import read as base_read

    app, tables, per_table = scratch_base()
    host = tables[0].table_id
    dead_column = unmarshal({
        "field_id": "fldLD278",
        "field_name": "Legacy record",
        "type": 18,
        "ui_type": "SingleLink",
        "property": {"multiple": False, "table_id": DEAD_TABLE},
    }, AppTableField)

    class _Client:
        def __init__(self):
            self.api_calls = 0
            self.dead_calls = 0

        def get_app(self, app_token):
            return app

        def list_tables(self, app_token):
            return tables

        def list_fields(self, app_token, table_id):
            self.api_calls += 1
            if table_id == DEAD_TABLE:
                self.dead_calls += 1
                raise LarkAPIError("list the fields of table failed", code=1254041,
                                   msg="TableIdNotFound")
            fields = list(per_table[table_id][0])
            return fields + [dead_column] if table_id == host else fields

        def search_records(self, app_token, table_id):
            self.api_calls += 1
            records = per_table[table_id][1]
            if table_id == host:
                for record in records:
                    record.fields["Legacy record"] = {"link_record_ids": ["recLD278GONE"]}
            return records

        def batch_get_records(self, app_token, table_id, record_ids):
            raise AssertionError("no record call is worth spending on a table that is gone")

    client = _Client()
    document = base_read.read_base("BaseScratchExample000000001", client=client,
                                   resolve_links=True)
    assert client.dead_calls == 1, "the dead target is asked about once, and only once"
    rendered = base_table.render_base(document)
    assert lr.unresolvable_marker("recLD278GONE") in rendered
    entry = document.link_resolution.record_for(DEAD_TABLE, "recLD278GONE")
    assert entry.state == lr.LINK_UNRESOLVABLE
    assert not document.link_resolution.dangling, "nothing is claimed to be gone"
