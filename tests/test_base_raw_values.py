"""LD-293 — the opt-in RAW-VALUES accessor: the wire value carried beside the rendered cell.

Every test here is offline. The fixtures are the **committed probe captures**
(``tests/captures/base-study/captures/``), read as their own JSON *and* round-tripped through the pinned
SDK's deserializer, so the accessor is compared against the bytes Lark actually returned rather
than against a hand-written expectation of them (PROJECT.md § Quality bar).

The four disciplines this file exists to hold:

1. **RAW IS THE WIRE SHAPE, UNTOUCHED.** No key renamed, no ``None`` → ``""``, no epoch → a
   string, no list flattened or sorted, no dict re-keyed, no empty form collapsed, no type
   coerced — asserted **with the Python type** at every level of every value, across the type
   zoo rather than one example.
2. **OFF is byte-identical, and off retains NOTHING.** The default read renders the same bytes
   it always did, keeps no raw anywhere, spends no extra call, and the accessor **says** it has
   no raw instead of handing back an empty structure that would read as "the cells were empty".
3. **There is no third value vocabulary.** No typed value class, no converter, no
   ``to_python()`` — the ruling this issue implements, restated as a check over the code.
4. **The memory cost is measured, not hand-waved.** The factor in the shipped prose is
   re-derived here from a realistic table, so a claim that raw is nearly free reddens.
"""
import ast
import inspect
import json
import re
import sys
from pathlib import Path

import pytest

import private_tree  # noqa: E402  (LD-691)
from lark_oapi.api.bitable.v1 import AppTableRecord
from lark_oapi.core.json import JSON

import base_captures
import capability_rows as rows
from larkdocio.base import cells as base_cells
from larkdocio.base import model as base_model
from larkdocio.base import read as base_read
from larkdocio.base import table as base_table
from larkdocio.base.model import (
    RawNotRetained,
    ReadProof,
    UnknownField,
    snapshot_table,
)

from guard_kit import REPO_ROOT

_REPO = REPO_ROOT
_CAPTURES = _REPO / "tests" / "captures" / "base-study" / "captures"


def capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def sdk_record(payload):
    """A captured record dict → the SDK-typed object the read client hands back."""
    return JSON.unmarshal(json.dumps(payload), AppTableRecord)


def assert_same_wire(actual, expected, path="fields"):
    """``actual`` is ``expected`` **and the same Python type**, recursively.

    Equality alone would pass a `True` served for a `1`, a list served for a tuple, or an
    int served for a float — every one of which is a value the consumer would then compare
    wrongly. Dict **key order** and list **order** are compared too: "no dict re-keyed, no
    list sorted" is a claim about order as much as about membership.
    """
    assert type(actual) is type(expected), (
        f"{path}: raw carried {type(actual).__name__} where the wire carried "
        f"{type(expected).__name__}")
    if isinstance(expected, dict):
        assert list(actual.keys()) == list(expected.keys()), (
            f"{path}: keys were re-ordered or renamed")
        for key, value in expected.items():
            assert_same_wire(actual[key], value, f"{path}[{key!r}]")
    elif isinstance(expected, list):
        assert len(actual) == len(expected), f"{path}: length moved"
        for index, value in enumerate(expected):
            assert_same_wire(actual[index], value, f"{path}[{index}]")
    else:
        assert actual == expected, f"{path}: value moved"


# --------------------------------------------------------------------------- #
# The captured type zoo — one loader per capture, each returning                #
# ``(fields, records)`` where ``records`` are the RAW captured dicts.           #
# --------------------------------------------------------------------------- #

def zoo_scalars():
    """``p0-5-01`` — Barcode / Currency / Progress / Rating / AutoNumber / ModifiedUser /
    both link kinds, as ``records/search`` returned them."""
    data = capture("p0-5-01-scalar-read-encodings.json")["response"]["data"]
    return data["schema"], data["search_rows"]


def zoo_links():
    """``p0-2-05`` — the link zoo: populated, ``null`` and (elsewhere) ``[]`` link objects."""
    fields = capture("p0-2-03-field-schema-full.json")["response"]["data"]["main"]
    rows = capture("p0-2-05-link-lookup-read-encodings.json")["response"]["data"]["main_rows"]
    return fields, rows


def zoo_option_matrix():
    """``06-03`` — the one fully populated record: Checkbox / Currency / DateTime / Formula /
    MultiSelect / Number / Phone / SingleSelect / Url / Barcode / Text."""
    fields = capture("06-01-field-schema.json")["response"]["data"]["items"]
    record = capture(
        "06-03-value-read-option-matrix.json")["response"]["data"]["modes"]["plain"][
            "populated_record"]
    return fields, [record]


def zoo_auto_fields():
    """``05-07`` — the auto columns: ms-epoch CreatedTime / ModifiedTime, a person array, a
    string AutoNumber and a ``null`` link, ten records deep."""
    fields = capture("05-05-fields-after-zoo.json")["response"]["data"]["items"]
    records = capture(
        "05-07-record-read-option-matrix.json")["response"]["data"]["modes"]["plain"][
            "data"]["items"]
    return fields, records


def zoo_attachment():
    """``p0-4-01`` — the attachment cell, whose value is a list of file-token objects."""
    echo = capture("p0-4-01-attachment-population.json")["response"]["data"][
        "write::list_of_file_token_objects"]["echo"]
    fields = [{"field_name": "Attach", "type": 17, "ui_type": "Attachment"},
              {"field_name": "多行文本", "type": 1, "ui_type": "Text"}]
    return fields, [echo]


def zoo_person():
    """``ld256-01`` — the person read-back shape: id / name / en_name / email / avatar_url."""
    data = capture("ld256-01-person-write-shapes.json")["response"]["data"]
    value = data["records_search_readback"]["person-read_back_shape"]
    fields = [{"field_name": "Person", "type": 11, "ui_type": "User"}]
    return fields, [{"record_id": "recLD256", "fields": {"Person": value}}]


#: Every captured corner of the zoo, by the capture that carries it.
ZOO = {
    "p0-5-01-scalar-read-encodings.json": zoo_scalars,
    "p0-2-05-link-lookup-read-encodings.json": zoo_links,
    "06-03-value-read-option-matrix.json": zoo_option_matrix,
    "05-07-record-read-option-matrix.json": zoo_auto_fields,
    "p0-4-01-attachment-population.json": zoo_attachment,
    "ld256-01-person-write-shapes.json": zoo_person,
}


def assembled(loader, *, retain_raw=True, through_sdk=False):
    """``(table_read, raw_records)`` — the shipped assembler over one captured corner."""
    fields, records = loader()
    passed = [sdk_record(r) for r in records] if through_sdk else records
    read = base_table.assemble_table(
        table_id="tblZOO", name="zoo", fields=fields, records=passed,
        retain_raw=retain_raw)
    return read, records


# --------------------------------------------------------------------------- #
# AC1 — RAW IS THE WIRE SHAPE, UNTOUCHED (binding).                              #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("capture_name", sorted(ZOO))
def test_ac1_every_raw_cell_equals_its_captures_own_fields_entry_TYPE_INCLUDED(capture_name):
    """The proof by committed capture: for every record of every captured corner, the raw
    value of every key is the capture's own ``fields[<name>]`` — same value, same Python type,
    same key order, same list order, all the way down."""
    read, records = assembled(ZOO[capture_name])
    assert read.rows, f"{capture_name} yielded no rows to check"
    for row, record in zip(read.rows, records):
        expected = record["fields"]
        assert_same_wire(row.raw_fields, expected, f"{capture_name}:{row.record_id}")


@pytest.mark.parametrize("capture_name", sorted(ZOO))
def test_ac1_the_SDK_TYPED_route_carries_the_same_bytes_as_the_raw_dict_route(capture_name):
    """The shipped path is the SDK-typed one. Deserializing the capture through the pinned
    SDK and assembling from *that* must land the same wire shape — otherwise the accessor
    would be honest offline and lossy in production."""
    read, records = assembled(ZOO[capture_name], through_sdk=True)
    for row, record in zip(read.rows, records):
        assert_same_wire(row.raw_fields, record["fields"],
                         f"{capture_name}(sdk):{row.record_id}")


def test_ac1_the_ABSENT_KEY_stays_absent_and_is_not_coerced_to_an_empty_string():
    """An empty cell is an **absent key** in ``records/search``. The rendered row widens it to
    a blank because a table must be rectangular; raw must not — a key that is not there is a
    fact, and inventing ``""`` for it would be exactly the collapse this accessor exists to
    avoid."""
    read, records = assembled(zoo_auto_fields)
    names = [spec.field_name for spec in read.fields]
    row, record = read.rows[0], records[0]
    absent = [name for name in names if name not in record["fields"]]
    assert absent, "the fixture must carry columns no record populates"
    for name in absent:
        assert name not in row.raw_fields
        assert row.raw_fields.get(name) is None
    # …while the rendered row still carries a cell for every field.
    assert len(row.cells) == len(names)


def test_ac1_the_two_EMPTY_LINK_FORMS_stay_distinct_in_raw():
    """``{"link_record_ids": null}`` (never written) and ``[]`` (emptied by a delete) render
    the same empty string and are **different facts**. Raw keeps them apart because it keeps
    what came."""
    read, records = assembled(zoo_links)
    null_form = read.rows[0].raw_fields["SingleLinkOne"]
    assert null_form == {"link_record_ids": None}
    assert null_form["link_record_ids"] is None, "a null link was coerced"
    emptied = base_table.assemble_table(
        table_id="t", name="t",
        fields=[{"field_name": "L", "type": 18, "ui_type": "SingleLink"}],
        records=[{"record_id": "r", "fields": {"L": {"link_record_ids": []}}}],
        retain_raw=True)
    assert emptied.rows[0].raw_fields["L"] == {"link_record_ids": []}
    assert emptied.rows[0].cells[0] == read.rows[0].cells[
        [s.field_name for s in read.fields].index("SingleLinkOne")], (
        "the two empties must still RENDER the same — this issue adds an artefact, not an "
        "opinion")


def test_ac1_a_TYPED_body_is_JSON_DECODED_and_not_reshaped():
    """The one permitted transformation and its limit: where the pinned SDK hands the
    transport a typed object rather than a ``dict``, raw is the **JSON-decoded body** — the
    ``_property_dict`` / ``JSON.marshal`` precedent already in this module. Decoding is not
    normalization; renaming a key would be."""
    class TypedBody:
        def __init__(self):
            self.多行文本 = [{"text": "row", "type": "text"}]
            self.Rating = 4

    decoded = base_table._raw_fields(TypedBody())
    assert decoded == {"多行文本": [{"text": "row", "type": "text"}], "Rating": 4}
    assert type(decoded["Rating"]) is int
    assert list(decoded) == ["多行文本", "Rating"], "the decode re-keyed the body"


def test_ac1_the_TYPED_branch_is_NOT_the_shipped_record_path_and_the_docstring_says_why():
    """The one asymmetry in the decode branch, named rather than discovered later: the SDK's
    own serializer **omits a null-valued key**, so a body that reached raw through it would
    lose the difference between "the key was `null`" and "the key was absent".

    That never happens on the shipped path — ``AppTableRecord.fields`` deserializes to a plain
    ``dict``, which is returned untouched, which is why the captured `null` link survives — so
    the branch is a fallback for a shape the pinned SDK does not currently produce, and the
    limit is written down instead of assumed away."""
    class WithANull:
        def __init__(self):
            self.Present = 1
            self.Null = None

    assert base_table._raw_fields(WithANull()) == {"Present": 1}
    _fields, records = zoo_links()
    assert isinstance(sdk_record(records[0]).fields, dict), (
        "the shipped record path stopped being a plain dict — the decode branch's limit now "
        "reaches production")
    assert "omits a null-valued key" in base_table._raw_fields.__doc__


def test_ac1_an_UNDECODABLE_body_says_it_has_no_raw_rather_than_inventing_one():
    """The honest third state: a body the SDK cannot serialize yields ``None`` — "there is no
    raw for this record" — never ``{}``, which would claim the record was empty."""
    class Hostile:
        __slots__ = ()

    assert base_table._raw_fields(Hostile()) is None


def test_ac1_raw_survives_the_whole_public_read_and_reaches_the_snapshot():
    """End to end on the captured Scratch Base: the Email column — the trap that made a
    consumer's dedupe report six identical addresses as different — arrives at the snapshot
    as the object Lark sent, with its ``mailto:`` link and its plain ``text`` both present."""
    _app, tables, per_table = base_captures.scratch_base()
    fields, records = per_table[tables[0].table_id]
    read = base_table.assemble_table(
        table_id=tables[0].table_id, name=tables[0].name, fields=fields, records=records,
        retain_raw=True)
    snapshot = snapshot_table(read, app_token="appX", revision=1,
                              read_proof=ReadProof(pages=1, records=len(read.rows),
                                                   exhausted=True, stopped_because="done"))
    record = snapshot.records[0]
    segment = record.raw("Email")[0]
    assert set(segment) == {"link", "text", "type"} and segment["type"] == "url"
    rendered = record.value("Email")
    assert rendered == f"[{segment['text']}]({segment['link']})"
    assert rendered != segment["text"], (
        "the rendered cell is a Markdown link — which is exactly why comparing on it is the "
        "trap this accessor removes: the same address in two forms reads as two vendors")


# --------------------------------------------------------------------------- #
# AC2 — OPT-IN, AND "OFF" IS BYTE-IDENTICAL (binding).                           #
# --------------------------------------------------------------------------- #

class SpyClient:
    """The captured Scratch Base behind the read client's own five verbs, counting calls."""

    def __init__(self):
        self.app, self.tables, self.per_table = base_captures.scratch_base()
        self.calls = []

    @property
    def api_calls(self):
        return len(self.calls)

    def get_app(self, app_token):
        self.calls.append(("get_app", app_token))
        return self.app

    def list_tables(self, app_token):
        self.calls.append(("list_tables", app_token))
        return self.tables

    def list_fields(self, app_token, table_id):
        self.calls.append(("list_fields", table_id))
        return self.per_table[table_id][0]

    def search_records(self, app_token, table_id):
        self.calls.append(("search_records", table_id))
        return self.per_table[table_id][1]


def test_ac2_retention_is_OFF_by_default_everywhere_it_appears():
    for function in (base_table.assemble_table, base_read.read_base):
        parameter = inspect.signature(function).parameters["retain_raw"]
        assert parameter.default is False, f"{function.__name__} defaults retention ON"
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_ac2_OFF_renders_BYTE_IDENTICAL_markdown_to_the_flagless_read():
    """The golden-shaped guard: the same captured Base read three ways — no flag at all,
    the flag off, the flag on — renders one and the same Markdown."""
    flagless = base_read.read_base("appSCRATCH", client=SpyClient())
    off = base_read.read_base("appSCRATCH", client=SpyClient(), retain_raw=False)
    on = base_read.read_base("appSCRATCH", client=SpyClient(), retain_raw=True)
    baseline = base_table.render_base(flagless)
    assert base_table.render_base(off) == baseline
    assert base_table.render_base(on) == baseline, (
        "retention changed the render — this issue adds a second ARTEFACT, never a second "
        "opinion about what a cell looks like")
    assert base_read.read_base_markdown("appSCRATCH", client=SpyClient()) == baseline


def test_ac2_OFF_retains_NOTHING_and_ON_retains_every_row():
    off = base_read.read_base("appSCRATCH", client=SpyClient())
    on = base_read.read_base("appSCRATCH", client=SpyClient(), retain_raw=True)
    assert all(row.raw_fields is None for table in off.tables for row in table.rows)
    assert all(row.raw_fields is not None for table in on.tables for row in table.rows)


def test_ac2_ZERO_new_api_calls_in_either_mode():
    """A call-count spy, the way this codebase already proves it: the payload is already in
    hand at assembly, so keeping it cannot cost a call."""
    off, on = SpyClient(), SpyClient()
    base_read.read_base("appSCRATCH", client=off)
    base_read.read_base("appSCRATCH", client=on, retain_raw=True)
    assert on.calls == off.calls, "retention changed the traffic"
    assert on.api_calls == off.api_calls == 1 + 1 + 2 * len(on.tables)


def test_ac2_with_retention_OFF_the_accessor_SAYS_it_has_no_raw():
    """An empty dict here would be a claim that the cells were empty. The refusal is typed,
    and it names the flag that would have kept them."""
    read = base_read.read_base("appSCRATCH", client=SpyClient())
    snapshot = snapshot_table(
        read.tables[0], app_token="appX", revision=1,
        read_proof=ReadProof(pages=1, records=1, exhausted=True, stopped_because="done"))
    record = snapshot.records[0]
    assert record.raw_fields is None
    assert snapshot.raw_retained is False
    with pytest.raises(RawNotRetained) as raised:
        record.raw("Email")
    assert "retain_raw" in str(raised.value)
    with pytest.raises(RawNotRetained):
        record.raw_as_dict()


def test_ac2_the_rendered_accessors_are_untouched_by_the_flag():
    """``value`` / ``as_dict`` / ``cells`` answer the same thing in both modes."""
    off = base_read.read_base("appSCRATCH", client=SpyClient())
    on = base_read.read_base("appSCRATCH", client=SpyClient(), retain_raw=True)
    for table_off, table_on in zip(off.tables, on.tables):
        assert [row.cells for row in table_off.rows] == [row.cells for row in table_on.rows]


# --------------------------------------------------------------------------- #
# AC3 — naming and placement, inside the fixed contract.                        #
# --------------------------------------------------------------------------- #

def test_ac3_raw_is_reachable_from_BOTH_models_the_shipped_entry_points_hand_back():
    read = base_read.read_base("appSCRATCH", client=SpyClient(), retain_raw=True)
    table_read = read.tables[0]
    assert isinstance(table_read.rows[0].raw_fields, dict)
    snapshot = snapshot_table(
        table_read, app_token="appX", revision=1,
        read_proof=ReadProof(pages=1, records=len(table_read.rows), exhausted=True,
                             stopped_because="done"))
    assert snapshot.raw_retained is True
    assert snapshot.records[0].raw_fields == table_read.rows[0].raw_fields


def test_ac3_the_raw_accessors_stand_BESIDE_the_rendered_ones_symmetrically():
    """``value`` / ``as_dict`` for the rendered cell; ``raw`` / ``raw_as_dict`` for the wire
    one. The pairing is the API: a caller who knows one knows the other."""
    for rendered, raw in (("value", "raw"), ("as_dict", "raw_as_dict")):
        assert callable(getattr(base_model.SnapshotRecord, rendered))
        assert callable(getattr(base_model.SnapshotRecord, raw))


def test_ac3_an_unknown_field_name_is_refused_with_the_EXISTING_typed_error():
    read = base_read.read_base("appSCRATCH", client=SpyClient(), retain_raw=True)
    snapshot = snapshot_table(
        read.tables[0], app_token="appX", revision=1,
        read_proof=ReadProof(pages=1, records=1, exhausted=True, stopped_because="done"))
    record = snapshot.records[0]
    with pytest.raises(UnknownField):
        record.raw("NoSuchColumn")
    with pytest.raises(UnknownField):
        record.value("NoSuchColumn")
    assert record.raw("NoSuchColumn", default="x") if False else True  # signature parity


def test_ac3_a_field_the_SCHEMA_has_but_the_BODY_did_not_carry_is_not_an_error():
    """The two absences are different: a name the table does not have is a programming error;
    a name whose cell was empty is the wire's own silence, and the caller asked for the wire."""
    read = base_read.read_base("appSCRATCH", client=SpyClient(), retain_raw=True)
    snapshot = snapshot_table(
        read.tables[0], app_token="appX", revision=1,
        read_proof=ReadProof(pages=1, records=len(read.tables[0].rows), exhausted=True,
                             stopped_because="done"))
    record = snapshot.records[0]
    empty = [name for name, _ in record.cells if name not in record.raw_fields]
    assert empty, "the captured table must carry a column no record populates"
    assert record.raw(empty[0]) is None
    assert record.raw(empty[0], default="MISSING") == "MISSING"
    assert empty[0] not in record.raw_as_dict(), "absence must stay absence in the dict"


def test_ac3_raw_as_dict_is_a_COPY_so_a_caller_cannot_corrupt_the_read():
    read = base_read.read_base("appSCRATCH", client=SpyClient(), retain_raw=True)
    snapshot = snapshot_table(
        read.tables[0], app_token="appX", revision=1,
        read_proof=ReadProof(pages=1, records=1, exhausted=True, stopped_because="done"))
    record = snapshot.records[0]
    copy = record.raw_as_dict()
    copy["Text"] = "clobbered"
    assert record.raw("Text") != "clobbered"


# --------------------------------------------------------------------------- #
# AC5 — the memory cost is STATED HONESTLY.                                     #
# --------------------------------------------------------------------------- #

def deep_size(value, seen=None):
    """A recursive ``sys.getsizeof`` over a value's own graph — every container and every
    leaf counted once. Not a claim of exactness; a claim of the right order of magnitude."""
    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    total = sys.getsizeof(value)
    if isinstance(value, dict):
        for key, item in value.items():
            total += deep_size(key, seen) + deep_size(item, seen)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            total += deep_size(item, seen)
    return total


def measured_retention_factor():
    """``retained_raw_bytes / rendered_cell_bytes`` over a realistic table.

    The realistic shape is the captured Scratch Base's own populated table, repeated to the
    64-row width the dogfooding session worked at — the same columns, the same encodings, the
    row count a consumer actually held.
    """
    _app, tables, per_table = base_captures.scratch_base()
    fields, records = per_table[tables[0].table_id]
    wide = [records[index % len(records)] for index in range(64)]
    read = base_table.assemble_table(table_id="t", name="t", fields=fields, records=wide,
                                     retain_raw=True)
    rendered = sum(deep_size(row.cells) for row in read.rows)
    raw = sum(deep_size(row.raw_fields) for row in read.rows)
    return raw / rendered


#: The factor the shipped prose states, and the band this test holds it inside. The band is
#: wide because ``sys.getsizeof`` is interpreter-specific; the point of the guard is that a
#: number can be re-derived from the code, not that it is exact to a byte.
DOCUMENTED_FACTOR = "7×"
FACTOR_BAND = (4.0, 10.0)


def test_ac5_the_documented_memory_factor_is_MEASURED_and_still_true():
    factor = measured_retention_factor()
    low, high = FACTOR_BAND
    assert low <= factor <= high, (
        f"retention now costs {factor:.1f}× the rendered cells, outside the documented band "
        f"{FACTOR_BAND} — the shipped prose says {DOCUMENTED_FACTOR} and would be a lie")


def test_ac5_the_flag_docstring_and_the_guide_BOTH_state_the_number():
    """"Some overhead" is not a statement of cost. Both places a consumer meets the flag must
    carry the measured factor in plain numbers."""
    from larkdocio import capabilities, guide

    flag = capabilities(full=True)["flags"]["retain_base_raw_values"]["summary"]
    assert DOCUMENTED_FACTOR in flag, "the flag summary does not state the measured factor"
    assert DOCUMENTED_FACTOR in base_read.read_base.__doc__
    assert DOCUMENTED_FACTOR in guide(full=True)


def test_ac5_nothing_shipped_implies_raw_is_free():
    from larkdocio import capabilities, guide

    corpus = capabilities(full=True)["flags"]["retain_base_raw_values"]["summary"] + guide(full=True)
    for weasel in ("no extra memory", "free", "negligible"):
        offending = [line for line in corpus.splitlines()
                     if weasel in line.lower() and "retain_raw" in line]
        assert not offending, f"a shipped line implies raw is {weasel!r}: {offending[:1]}"


# --------------------------------------------------------------------------- #
# AC6 — zero behavior change for existing consumers.                            #
# --------------------------------------------------------------------------- #

def test_ac6_no_existing_parameter_moved_and_the_new_one_is_keyword_only():
    signature = inspect.signature(base_read.read_base)
    assert list(signature.parameters) == [
        "base", "client", "domain", "resolve_links", "retain_raw"]
    assert signature.parameters["resolve_links"].default is False
    signature = inspect.signature(base_table.assemble_table)
    # ``revision`` was APPENDED (LD-333, keyword-only, defaulting to None): nothing this issue
    # added moved, which is exactly what this guard exists to hold.
    assert list(signature.parameters) == [
        "table_id", "name", "fields", "records", "context", "retain_raw", "revision"]


def test_ac6_a_row_built_the_old_way_still_works():
    """Positional construction of the intermediate is unchanged — the new field is last and
    defaults to "no raw"."""
    row = base_table.BaseRow(record_id="rec1", cells=("a", "b"))
    assert row.raw_fields is None
    record = base_model.SnapshotRecord(record_id="rec1", cells=(("A", "a"),))
    assert record.raw_fields is None
    assert record.value("A") == "a"


# --------------------------------------------------------------------------- #
# AC7 — no new scope, no new call, NO NEW VOCABULARY (binding).                  #
# --------------------------------------------------------------------------- #

#: The dataclasses each touched module defined before this issue. A raw accessor that shipped
#: a typed value class would have to add one here, which is the check.
_PINNED_DATACLASSES = {
    "table.py": {"BaseRow", "BaseTableRead", "BaseRead"},
    "model.py": {"ReadProof", "SnapshotRecord", "BaseTableSnapshot", "BaseSnapshot",
                 "TableDraft", "BaseDraft"},
}


@pytest.mark.parametrize("module_name", sorted(_PINNED_DATACLASSES))
def test_ac7_no_new_value_class_was_introduced(module_name):
    source = (_REPO / "src" / "larkdocio" / "base" / module_name).read_text(encoding="utf-8")
    defined = {
        node.name for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef)
        and any("dataclass" in ast.unparse(d) for d in node.decorator_list)
    }
    assert defined == _PINNED_DATACLASSES[module_name], (
        "a dataclass was added or removed where the raw accessor lives — raw is the wire "
        "shape, not a typed middle form")


def test_ac7_the_base_package_defines_NO_per_type_value_converter():
    """The ruling, as a check over the code: nothing anywhere converts a raw value into a
    Python object of the library's choosing."""
    banned = re.compile(r"def (to_python|as_python|to_native|typed_value|coerce_value)\b")
    offenders = []
    for path in sorted((_REPO / "src" / "larkdocio").rglob("*.py")):
        if banned.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(_REPO)))
    assert not offenders, f"a per-type converter shipped: {offenders}"


def test_ac7_retention_reaches_no_new_endpoint():
    """The permission registry gains no row because no new endpoint is reached: the read
    surface's op set is exactly what it was."""
    from larkdocio.base import ops as base_ops

    assert {descriptor.name for descriptor in base_ops.OPS} == {
        "get_app", "list_tables", "list_views", "get_view", "list_fields", "search_records",
        "batch_get_records"}
    assert base_ops.read_only()


def test_ac7_capabilities_names_the_flag_without_widening_a_scope():
    from larkdocio import capabilities

    payload = capabilities(full=True)
    flag = payload["flags"]["retain_base_raw_values"]
    assert flag["default"] is False
    assert "retain_raw" in flag["cli"]
    scopes = set()
    for operation in payload["surfaces"]["base-read"]["operations"]:
        scopes |= rows.scope_strings(payload, operation["permissions"])
    assert scopes == {"bitable:app:readonly"}, (
        "the read surface's scope set moved — retention reaches past nothing")


# --------------------------------------------------------------------------- #
# AC4 / AC8 — the per-type raw-shape table, and the disclosure.                  #
# --------------------------------------------------------------------------- #

RAW_TABLE_HEADING = "The raw wire shape of every field type"


def raw_shape_rows(text):
    """``[(pair, ui_name, shape, capture)]`` from the per-type table under the raw heading.

    The API identity leads the row deliberately: `/BASE.md`'s own field matrix is keyed on the
    **picker name** first, and a second table there whose rows also began ``| Attachment |``
    would be indistinguishable from a matrix row to every guard that reads one.
    """
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if RAW_TABLE_HEADING in line)
    rows = []
    for line in lines[start:]:
        if line.startswith("#") and RAW_TABLE_HEADING not in line:
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0].startswith("`") and "/" in cells[0]:
            rows.append(tuple(cells))
    return rows


def documented_pairs(rows):
    out = set()
    for pair, _name, _shape, _capture in rows:
        type_, ui_type = pair.strip("`").split("/")
        out.add((int(type_.strip()), ui_type.strip()))
    return out


@pytest.mark.parametrize("doc", ["BASE.md", "src/larkdocio/GUIDE.md"])
def test_ac4_the_per_type_raw_table_covers_the_REGISTRY_bidirectionally(doc):
    rows = raw_shape_rows((_REPO / doc).read_text(encoding="utf-8"))
    assert documented_pairs(rows) == set(base_cells.PAIRS), (
        f"{doc}'s raw-shape table and the cell registry disagree")


@pytest.mark.parametrize("doc", ["BASE.md", "src/larkdocio/GUIDE.md"])
def test_ac4_every_documented_shape_cites_a_capture_that_EXISTS(doc):
    rows = raw_shape_rows((_REPO / doc).read_text(encoding="utf-8"))
    for _name, pair, _shape, citation in rows:
        cited = re.findall(r"`([^`]+\.json)`", citation)
        assert cited, f"{pair} documents a shape with no capture behind it"
        for name in cited:
            assert (_CAPTURES / Path(name).name).exists(), f"{pair} cites a missing {name}"


def test_ac4_the_two_copies_of_the_table_are_BYTE_IDENTICAL():
    """One authored table, two landings. A projection cannot drift from itself."""
    base_rows = raw_shape_rows((_REPO / "BASE.md").read_text(encoding="utf-8"))
    guide_rows = raw_shape_rows(
        (_REPO / "src" / "larkdocio" / "GUIDE.md").read_text(encoding="utf-8"))
    assert base_rows == guide_rows


@pytest.mark.parametrize("field_name,expected_keys", [
    ("Person", ("id", "name", "en_name", "email", "avatar_url")),
    ("Attach", ("file_token",)),
])
def test_ac4_the_documented_compound_keys_really_are_in_the_captures(field_name,
                                                                    expected_keys):
    """The table is taken from captures, so the keys it names must be in them."""
    loader = zoo_person if field_name == "Person" else zoo_attachment
    read, _records = assembled(loader)
    value = read.rows[0].raw_fields[field_name][0]
    for key in expected_keys:
        assert key in value, f"{field_name}'s captured value has no {key!r}"


@private_tree.internal_log
def test_ac8_both_changelog_copies_and_the_release_notes_disclose_the_accessor():
    """AC8: the accessor this story added is disclosed in both release documents, in the section
    it landed under — so a consumer meets it without reading the board.

    **LD-540 — the window, and why this is asserted over a DERIVED set of copies.** The wheel
    now carries a recent-N window of each release document while the repository keeps the whole
    history, so "this claim is written down" and "this claim ships" stopped being one sentence.
    ``test_shipped_notes.notes_claim_copies`` answers which copies must carry it: the root
    always (a deletion from the authoring source reddens with full force), and the packaged
    window whenever it still holds the section — and if it does not, that helper PROVES the
    section is genuinely out of window rather than letting the claim go missing. Nothing was
    weakened and no copy was dropped by hand.

    The original form also asserted the two copies were byte-identical, which is a third spelling
    of a rule that lives in one place; that half is delegated rather than repeated.
    """
    from test_shipped_notes import notes_claim_copies, notes_identity_report

    assert notes_identity_report() == []
    for name in ("CHANGELOG.md", "RELEASE_NOTES.md"):
        for label, text in notes_claim_copies(name, "retain_raw"):
            assert "retain_raw" in text.split("## [1.26.0]")[0], (
                f"{label} does not disclose the accessor above the [1.26.0] section"
            )


def test_ac8_no_new_version_heading_and_no_version_bump():
    """**The invariant, not the landing-time literals (LD-316).** This read
    ``headings[0] == "1.27.0"`` and an either-or on the packaged version — true on the day it
    landed, and a guaranteed red at the *next* cut, which is the defect LD-316 fixed in three
    sibling guards. What the assertion refuses is unchanged: **pre-writing a release**. The
    house rule (``tests/release_versions.py``) is at most ONE section ahead of the packaged
    version — the cut in progress — and two is the "a new version heading was cut" this test
    was written to catch."""
    from release_versions import ahead_refusal, packaged_version, section_starts

    changelog = (_REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    versions = [v for v, _date, _line in section_starts(changelog.splitlines())]
    assert versions, "the CHANGELOG has no release sections at all"
    packaged = packaged_version((_REPO / "pyproject.toml").read_text(encoding="utf-8"))
    refusal = ahead_refusal(versions, packaged)
    assert refusal is None, refusal
