"""LD-270 — computed-column provenance for Lookup (19) and Formula (20).

The reading this story adds is **provenance**, never a render: L1 already renders a Lookup
cell correctly (the Base read spec's § F1-S1 renderer), and this layer says where the column's numbers
came from. Every assertion below is measured against the committed specimen
``tests/captures/base-study/captures/p1-q0-03-per-table.json`` — the maintainer's own hand-authored Lookup —
rather than against a hand-mocked dict, because the whole point of the story is what the
**real** payload does on its way through the pinned SDK.

Three traps are pinned here and each one shipped wrong somewhere before:

1. the Lookup wrapper's ``type`` is the **target field's**, not ``19``;
2. ``LISTCOMBINE``'s ``","`` entries are **segments the server sent**, so the join is ``""``
   and the resulting comma ambiguity is disclosed rather than escaped around;
3. the pinned SDK's typed property model **silently drops three of the four keys** that say
   what a Lookup rolls up from — so the surface reports the one that survives and names the
   gap as a transport limitation.
"""
import json

import pytest

from lark_oapi.api.bitable.v1 import AppTableField

from larkdocio.base import cells as base_cells
from larkdocio.base import computed as base_computed
from larkdocio.base import table as base_table
from larkdocio.base import write_vocabulary
from larkdocio.base.cells import FieldSpec

from test_base_table import unmarshal

from guard_kit import REPO_ROOT
from domain_vocabulary import RETIRED_ID

_REPO = REPO_ROOT
_CAPTURES = _REPO / "tests" / "captures" / "base-study" / "captures"

#: The Lookup specimen. Hand-authored in the product by the maintainer and captured live — the only
#: Lookup this repository has, and the reason so much of this file reads off one file.
_LOOKUP_CAPTURE = _CAPTURES / "p1-q0-03-per-table.json"

#: The Formula specimen, from the field-zoo pack.
_FORMULA_CAPTURE = _CAPTURES / "06-01-field-schema.json"


# --------------------------------------------------------------------------- #
# Specimen loading — the captures, never a hand-mocked dict.                   #
# --------------------------------------------------------------------------- #

def _lookup_tables():
    return json.loads(_LOOKUP_CAPTURE.read_text(encoding="utf-8"))["per_table"]


@pytest.fixture(scope="module")
def lookup_field():
    """The raw ``type: 19`` field dict, exactly as Lark returned it."""
    for table in _lookup_tables():
        for field in table["fields"]["response"]["data"]["items"]:
            if field["type"] == 19:
                return field
    raise AssertionError("the Lookup specimen has vanished from the captures")


@pytest.fixture(scope="module")
def lookup_cells():
    """Every record's raw ``lookup`` cell — the typed wrapper, not a rendered string."""
    for table in _lookup_tables():
        records = table["records_search"]["response"]["data"]["items"]
        values = [r["fields"]["lookup"] for r in records if "lookup" in r.get("fields", {})]
        if values:
            return values
    raise AssertionError("the Lookup specimen's cells have vanished from the captures")


@pytest.fixture(scope="module")
def formula_field():
    """The raw ``type: 20`` field dict with a real ``formula_expression``."""
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == 20 and node.get("ui_type") == "Formula":
                yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)

    payload = json.loads(_FORMULA_CAPTURE.read_text(encoding="utf-8"))
    for field in walk(payload):
        if (field.get("property") or {}).get("formula_expression"):
            return field
    raise AssertionError("the Formula specimen has vanished from the captures")


def _bridged(raw):
    """The field as the SHIPPED path sees it — through the SDK-typed seam, not around it."""
    return base_table.field_spec(unmarshal(raw, AppTableField))


_MODULE_PATH = _REPO / "src" / "larkdocio" / "base" / "computed.py"


def _module_tree():
    import ast

    return ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))


def _called_names():
    """Every callable this module actually invokes, by name — the CODE, never the prose.

    A substring sweep over the file cannot tell a banned primitive from a docstring that
    names it in order to say it is not used, and this module's whole job is to say exactly
    that. So the ban is asserted against the syntax tree.
    """
    import ast

    names = set()
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _imported_modules():
    import ast

    imported = set()
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    return imported


def _shipped_strings():
    """Every string literal and docstring this module ships — the consumer-facing text."""
    import ast

    return [node.value for node in ast.walk(_module_tree())
            if isinstance(node, ast.Constant) and isinstance(node.value, str)]


# --------------------------------------------------------------------------- #
# AC1 — the wrapper dispatches on the TARGET field's type, not on 19.          #
# --------------------------------------------------------------------------- #

def test_ac1_the_provenance_reports_the_SAME_N_the_renderer_dispatched_on(
        lookup_field, lookup_cells):
    """The wrapper's ``type`` is the **target field's** — ``1`` in the specimen, not ``19``.

    The renderer is not this story's; the agreement is. If the provenance layer ever reported
    ``19`` (the field's own type) while the renderer dispatched on ``1``, the two halves of
    the surface would be describing different columns.
    """
    column = base_computed.computed_column(_bridged(lookup_field), values=lookup_cells)
    dispatched_on = base_cells.wrapper_type(lookup_cells[0])

    assert dispatched_on == 1, "the specimen's wrapper type moved"
    assert column.value_type == dispatched_on
    assert column.value_type != lookup_field["type"], (
        "the provenance reported the FIELD's type where the renderer dispatched on the "
        "TARGET field's — the two halves have drifted")


def test_ac1_the_value_type_is_read_from_the_CELL_because_the_schema_cannot_supply_it(
        lookup_field):
    """With no cell in hand there is nothing to report, and ``None`` says so.

    The target field's type lives in ``filter_info.conditions`` on the schema — which the
    transport drops (see AC3b) — so a schema-only reading genuinely cannot know it. Guessing
    ``19`` there would be the exact defect AC1 exists to prevent.
    """
    assert base_computed.computed_column(_bridged(lookup_field), values=()).value_type is None


def test_ac1_amplifier_a_LOOKUP_with_a_non_text_target_is_UNCAPTURED_not_fabricated():
    """Every captured Lookup has a text target, so the ``N != 1`` case is recorded as
    unmeasured rather than invented — and the nearest real evidence (a Formula whose wrapper
    is ``2``) is named instead of a fabricated Lookup fixture."""
    lookups = [field
               for table in _lookup_tables()
               for field in table["fields"]["response"]["data"]["items"]
               if field["type"] == 19]
    assert lookups, "the specimen is gone"
    assert base_computed.NON_TEXT_LOOKUP_TARGET_IS_UNCAPTURED
    assert "uncaptured" in base_computed.NON_TEXT_LOOKUP_TARGET_IS_UNCAPTURED.lower()


def test_ac1_amplifier_the_nearest_non_text_wrapper_evidence_is_a_REAL_capture():
    """A Formula cell's wrapper is ``2`` over the same code path — measured, not asserted."""
    payload = json.loads((_CAPTURES / "06-03-value-read-option-matrix.json")
                         .read_text(encoding="utf-8"))

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("Formula"), dict):
                yield node["Formula"]
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)

    wrappers = list(walk(payload))
    assert wrappers, "the Formula cell capture is gone"
    assert base_cells.wrapper_type(wrappers[0]) == 2


# --------------------------------------------------------------------------- #
# AC2 — LISTCOMBINE separators are literal segments; the ambiguity is real.    #
# --------------------------------------------------------------------------- #

def test_ac2_the_separators_are_SEGMENTS_the_server_sent_not_a_delimiter_we_insert(
        lookup_cells):
    """The captured stream literally contains ``{"text": ","}`` entries between the values."""
    members = lookup_cells[0]["value"]
    assert [seg["text"] for seg in members][1::2] == [","] * 4, (
        "the specimen's separator segments moved — the whole join rule rests on them")


def test_ac2_the_join_is_the_EMPTY_STRING_and_a_comma_join_DOUBLE_SEPARATES(lookup_cells):
    """The deliberate-defect half: join with ``", "`` and the render doubles every separator.

    This is the assertion that would redden if someone "helpfully" inserted a delimiter.
    """
    members = lookup_cells[0]["value"]
    rendered = base_cells.render_segments(members)
    assert rendered == (
        "Text 2 Test Data 2,Text 2 Test Data 3,Text 2 Test Data 1,"
        "Text 2 Test Data 5,Text 2 Test Data 4")

    doubled = ", ".join(seg["text"] for seg in members)
    assert doubled != rendered
    assert ", ,, " in doubled, (
        "the double-separation this rule prevents is not being produced — the server's own "
        "separator segment ends up beside an inserted one")
    assert base_computed.LISTCOMBINE_JOIN_IS_THE_EMPTY_STRING


def test_ac2_the_comma_AMBIGUITY_is_disclosed_and_no_escape_scheme_is_invented():
    """Once joined, an aggregation comma and a comma inside a value are the same byte.

    That is a property of the server's aggregation. The library says so and stops there — an
    escape scheme Lark did not use would make the reader's output disagree with the product.
    """
    text = base_computed.LISTCOMBINE_COMMA_IS_AMBIGUOUS
    lowered = text.lower()
    assert "indistinguishable" in lowered
    assert "escap" in lowered, "the disclosure must say the library invents no escaping"
    for invented in ("\\,", "&#44;", "%2C"):
        assert invented not in text, f"an escape scheme ({invented}) has been invented"


def test_ac2_amplifier_a_value_CONTAINING_a_comma_renders_indistinguishably():
    """The ambiguity demonstrated rather than described: two different segment streams — one
    where the comma is a separator, one where it is inside a value — render to the same
    string, and no assertion anywhere can tell them apart afterwards."""
    as_separator = [{"text": "a", "type": "text"},
                    {"text": ",", "type": "text"},
                    {"text": "b", "type": "text"}]
    inside_a_value = [{"text": "a,b", "type": "text"}]
    assert (base_cells.render_segments(as_separator)
            == base_cells.render_segments(inside_a_value) == "a,b")


# --------------------------------------------------------------------------- #
# AC3 — the provenance the transport delivers, and the gap it does not.        #
# --------------------------------------------------------------------------- #

def test_ac3a_the_target_table_comes_from_the_NESTED_filter_info_key(lookup_field):
    """``property.filter_info.target_table`` — nested inside the filter configuration, which
    is **not** where a reader looking for it at the top of the property would find it."""
    raw = lookup_field["property"]
    assert "target_table" not in raw, (
        "the specimen carries target_table at the TOP level after all — the reading below is "
        "then looking in the wrong place")
    expected = raw["filter_info"]["target_table"]

    column = base_computed.computed_column(_bridged(lookup_field))
    assert column.rolls_up_from_table == expected == "tblvHhs6KA9QYNCo"
    assert base_computed.TARGET_TABLE_PATH == ("filter_info", "target_table")


def test_ac3a_the_target_table_SURVIVES_the_sdk_typed_bridge(lookup_field):
    """The whole reading rests on this one key coming through, so it is pinned directly."""
    bridged = _bridged(lookup_field).property
    assert bridged["filter_info"]["target_table"] == "tblvHhs6KA9QYNCo"


def test_ac3a_the_target_table_is_READ_THROUGH_THE_TYPED_DOOR_TOO_not_only_the_bridge(
        lookup_field):
    """The **raw SDK object**, as the read client hands one back — the door this surface was
    blind on.

    ``field_spec`` bridges a typed field to a dict before the renderers see it, and every
    assertion above reads that bridged shape. But a caller that holds the client's own
    ``AppTableField`` — the destructive scan is one — reads this surface *directly*, and on
    that door ``property.filter_info`` is a typed ``AppTableFieldPropertyLookupFilter`` object
    rather than a mapping. Walking it as a mapping answered ``None`` for a Lookup whose target
    table was right there, which live meant a destructive op refusing on every Base carrying a
    Lookup (LD-281). One key, two doors, one answer.
    """
    typed = unmarshal(lookup_field, AppTableField)
    assert not isinstance(typed.property, dict), "the read client's door is a typed object"
    assert not isinstance(typed.property.filter_info, dict), (
        "the nested filter is a typed object too — the shape a mapping walk cannot see through")

    assert base_computed.target_table(typed) == "tblvHhs6KA9QYNCo"
    assert (base_computed.target_table(typed)
            == base_computed.target_table(_bridged(lookup_field))), (
        "the typed door and the bridged one must answer the same table for the same column")


def test_ac3b_the_three_dropped_keys_are_ABSENT_AFTER_THE_BRIDGE(lookup_field):
    """The gap is **pinned**, not described: present in Lark's answer, gone after the seam."""
    raw = lookup_field["property"]
    bridged = _bridged(lookup_field).property
    for key in ("target_field", "roll_up", "formula"):
        assert key in raw, f"the specimen no longer carries {key} — the gap has closed"
        assert key not in bridged, (
            f"{key} now survives the typed seam — the transport limitation this surface "
            "discloses has changed and the disclosure must change with it")
    assert base_computed.TRANSPORT_DROPPED_KEYS == ("formula", "roll_up", "target_field")


def test_ac3b_the_reading_reports_the_dropped_keys_as_UNAVAILABLE_per_column(lookup_field):
    column = base_computed.computed_column(_bridged(lookup_field))
    assert column.unavailable == base_computed.TRANSPORT_DROPPED_KEYS
    assert column.rolls_up_from_field is None
    assert column.aggregation is None


def test_ac3c_the_gap_is_named_as_a_TRANSPORT_limitation_in_plain_language():
    """Plainly, and without implying Lark withholds anything: the server sends all four keys;
    this library's client is what does not carry three of them through."""
    text = base_computed.TRANSPORT_DOES_NOT_CARRY_THESE_KEYS
    lowered = text.lower()
    assert "does not carry these keys through" in lowered
    for blame in ("withhold", "refus", "hides", "denies", "not returned by lark"):
        assert blame not in lowered, (
            f"the disclosure blames the server ({blame!r}) for a limitation of this "
            "library's own transport")
    assert "lark returns" in lowered, (
        "the disclosure must say the server DOES send them, or it reads as a Lark gap")


def test_ac3d_NO_FORMULA_PARSER_SHIPS_ANYWHERE_and_this_test_is_what_says_so():
    """The Non-Goal, inherited and enforced. A formula string is opaque provenance: carried,
    never parsed, tokenized or executed — in either direction, ever."""
    called = _called_names()
    for banned in ("eval", "exec", "compile", "parse", "split", "tokenize", "literal_eval"):
        assert banned not in called, f"a formula-evaluation primitive ({banned}) is CALLED here"
    for banned in ("ast", "re", "tokenize", "shlex", "operator", "parser"):
        assert banned not in _imported_modules(), (
            f"a formula-evaluation module ({banned}) is imported here")

    for name in dir(base_computed):
        if name.startswith("_"):
            continue
        assert not any(word in name.lower()
                       for word in ("parse", "token", "evaluate", "eval", "compile")), (
            f"{name} looks like a formula parser; this story ships none")


def test_ac3d_NO_MODULE_ANYWHERE_defines_a_formula_parser():
    """Repo-wide, because the Non-Goal is not this module's alone: no function in the shipped
    library reads inside a formula string."""
    import ast

    offenders = []
    for path in sorted((_REPO / "src" / "larkdocio").rglob("*.py")):
        # Inside the Base surface the ban is total; elsewhere it is a ban on READING INSIDE
        # the string. The Sheets surface legitimately REPORTS whether LARK evaluated a
        # formula (`ApplyLog.formula_not_evaluated`), which is an observation of the server's
        # answer and the opposite of doing the work locally.
        words = (("parse", "token", "compile", "lex", "eval")
                 if path.parent.name == "base" else ("parse", "token", "compile", "lex"))
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = node.name.lower()
            if "formula" in name and any(word in name for word in words):
                offenders.append(f"{path.name}::{node.name}")
    assert not offenders, f"a formula parser has shipped: {offenders}"


def test_ac3d_a_formula_string_is_carried_VERBATIM_and_never_reduced(formula_field):
    """``1+1`` stays ``1+1``. A surface that reported ``2`` here would have evaluated it."""
    column = base_computed.computed_column(_bridged(formula_field))
    assert column.formula_expression == "1+1"
    assert base_computed.A_FORMULA_STRING_IS_OPAQUE


# --------------------------------------------------------------------------- #
# AC4 — a Formula column carries its expression, on the same terms.            #
# --------------------------------------------------------------------------- #

def test_ac4_formula_expression_and_formatter_SURVIVE_the_seam(formula_field):
    """This half of the story has no transport gap, and that is worth pinning rather than
    assuming: both keys are declared by the pinned SDK and come through unchanged."""
    raw = formula_field["property"]
    bridged = _bridged(formula_field).property
    assert bridged["formula_expression"] == raw["formula_expression"]
    assert bridged["formatter"] == raw["formatter"]

    column = base_computed.computed_column(_bridged(formula_field))
    assert column.formula_expression == raw["formula_expression"]
    assert column.formatter == raw["formatter"]
    assert column.unavailable == (), (
        "a Formula column's own provenance is complete — it must not borrow the Lookup's gap")


def test_ac4_the_cell_is_UNWRAPPED_by_L1s_renderer_and_nothing_is_computed_here():
    """The server already computed it. ``{"type": 2, "value": [2]}`` renders ``2`` because
    the server said ``2`` — not because anything here added ``1 + 1``."""
    spec = FieldSpec(field_name="Formula", type=20, ui_type="Formula",
                     property={"formula_expression": "1+1", "formatter": ""})
    assert base_cells.render_cell({"type": 2, "value": [2]}, spec) == "2"
    assert base_computed.NOTHING_IS_COMPUTED_LOCALLY


# --------------------------------------------------------------------------- #
# AC5 — a Lookup is a constrained Formula, and fixtures inherit the consequence.#
# --------------------------------------------------------------------------- #

def test_ac5_the_specimens_rows_are_IDENTICAL_across_every_record(lookup_cells):
    """``LISTCOMBINE`` aggregates the whole target table, so every record's Lookup cell is
    the same string. A fixture author who "fixes" that has broken the specimen."""
    rendered = {base_cells.render_segments(cell["value"]) for cell in lookup_cells}
    assert len(lookup_cells) > 1
    assert len(rendered) == 1, "the specimen's rows are no longer identical"


def test_ac5_the_constrained_formula_fact_names_the_evidence_it_RESTS_ON(lookup_field):
    """The honest wrinkle: ``roll_up`` does **not** survive the typed seam, so this fact is
    stated from the CAPTURE and the wording has to say which evidence it rests on rather than
    implying the shipped reading can see it."""
    assert lookup_field["property"]["roll_up"] == 0
    assert lookup_field["property"]["formula"].endswith("LISTCOMBINE()")

    text = base_computed.LOOKUP_IS_A_CONSTRAINED_FORMULA
    assert "capture" in text.lower(), (
        "the fact must name the capture it rests on — the shipped reading cannot see roll_up")
    assert "roll_up" in text and "identical" in text.lower()


def test_ac5_the_fixture_docstring_warns_the_next_author_not_to_FIX_the_identical_rows():
    """This module's own docstring is one of the two places the warning lives; the other is
    the register row. Both, because this is the class of thing a contributor silently
    corrects."""
    assert "must not" in base_computed.LOOKUP_IS_A_CONSTRAINED_FORMULA.lower()


# --------------------------------------------------------------------------- #
# AC6 — the computed set is read-only, and the refusal is CITED.               #
# --------------------------------------------------------------------------- #

def test_ac6_the_provenance_surface_exposes_NO_write_path_to_any_computed_type():
    """Not a policy claim — a structural one. Nothing in the module is a verb that writes,
    and nothing in it imports a client, a transport or a write plan."""
    for module in _imported_modules():
        assert not any(seam in module for seam in
                       ("client", "apply", "plan", "ops", "http", "request", "lark_oapi")), (
            f"the provenance module imports a write or transport seam ({module})")
    for called in _called_names():
        assert not any(verb in called.lower() for verb in
                       ("write", "update", "create", "delete", "patch", "post", "apply")), (
            f"the provenance module CALLS a write-shaped verb ({called})")

    for name in dir(base_computed):
        if name.startswith("_"):
            continue
        assert not any(word in name.lower()
                       for word in ("write", "set_", "update", "create", "delete", "patch")), (
            f"{name} is a write-shaped name on a read-only surface")


def test_ac6_the_read_only_reason_IS_the_landed_refusal_not_a_copy_of_it():
    """Cited, never re-built: the reason a caller reads here is the same object the write
    encoder refuses with, so the two cannot drift into two different explanations."""
    for pair in write_vocabulary.NON_WRITABLE_PAIRS:
        assert base_computed.read_only_reason(pair) is (
            write_vocabulary.NON_WRITABLE_REASONS[pair])


def test_ac6_every_computed_and_opaque_pair_is_covered_by_the_landed_constant():
    """Eight pairs — Lookup, Formula, Stage and the five auto fields — and the set is the
    landed one, imported rather than re-declared."""
    assert base_computed.COMPUTED_PAIRS is write_vocabulary.NON_WRITABLE_PAIRS
    assert len(base_computed.COMPUTED_PAIRS) == 8
    for pair in ((19, "Lookup"), (20, "Formula"), (24, "Stage"), (1005, "AutoNumber"),
                 (1001, "CreatedTime"), (1002, "ModifiedTime"),
                 (1003, "CreatedUser"), (1004, "ModifiedUser")):
        assert pair in base_computed.COMPUTED_PAIRS


# --------------------------------------------------------------------------- #
# AC6b — three vocabularies, three answers; and the copy sentence is ASSERTED. #
# --------------------------------------------------------------------------- #

def test_ac6b_lookup_and_stage_are_NOT_AUTHORABLE_NOT_WRITABLE_but_ARE_READABLE():
    """Three different questions with three different answers, and none of the three landed
    constants is re-defined here — each is read from its own owner."""
    from larkdocio.base.field_vocabulary import AUTHORABLE_UI_TYPES

    for pair in ((19, "Lookup"), (24, "Stage")):
        assert pair[1] not in AUTHORABLE_UI_TYPES, f"{pair[1]} became authorable"
        assert write_vocabulary.is_non_writable(pair), f"{pair[1]} became cell-writable"
        assert pair in base_cells.PAIRS, f"{pair[1]} stopped being readable"


def test_ac6b_nothing_here_claims_lark_has_NO_BUTTON_TYPE():
    """``(3001, "Button")`` is a real read identity. The product ruling not to support it is
    a ruling, not a claim that the type does not exist."""
    source = (_REPO / "src" / "larkdocio" / "base" / "computed.py").read_text(encoding="utf-8")
    assert "Button" not in source, (
        "this story authors no Button wording at all — the two landed rows own it")


def test_ac6b_the_copy_clones_exotic_columns_sentence_is_ASSERTED_not_re_authored():
    """The sentence is landed in the schema-apply seam. This story asserts against it and
    writes no rival — two statements of one rule is how they drift."""
    landed = (_REPO / "src" / "larkdocio" / "base" / "schema_apply.py").read_text(
        encoding="utf-8")
    assert "The copy carries whatever it carries." in landed
    assert "filters nothing, warns about nothing and special-cases nothing" in landed

    for text in _shipped_strings():
        lowered = text.lower()
        assert "clone" not in lowered, (
            "a rival copy-clones-exotic-columns sentence has been authored here")
        assert not ("copy" in lowered and "column" in lowered), (
            "a rival copy-clones-exotic-columns sentence has been authored here")


# --------------------------------------------------------------------------- #
# AC7 — Stage stays a traceable marker; this story does not soften it.         #
# --------------------------------------------------------------------------- #

def test_ac7_the_stage_reading_does_not_imply_the_column_is_EMPTY():
    """An empty cell would silently assert "no data" about data that exists."""
    spec = FieldSpec(field_name="stage?", type=24, ui_type="Stage", property=None)
    column = base_computed.computed_column(spec)
    assert column is not None
    assert column.note is base_cells.STAGE_OPAQUE_MARKER or (
        base_cells.STAGE_OPAQUE_MARKER in column.note)
    for softening in ("empty", "blank", "no data", "nothing to show"):
        assert softening not in column.note.lower(), (
            f"the Stage reading now implies the column is empty ({softening!r})")


def test_ac7_the_stage_reading_agrees_with_LANDED_REGISTER_ROW_1():
    """Asserted against the landed row rather than restated: schema readable, value
    unreachable — the same two halves, in the same direction."""
    from base_md import register_rows as _register_rows

    base_md = (_REPO / "BASE.md").read_text(encoding="utf-8")
    row = [r for r in _register_rows(base_md) if r["#"] == "1"][0]
    text = row["Limitation / workaround"]
    assert "schema readable" in text and "value unreachable" in text

    marker = base_cells.STAGE_OPAQUE_MARKER
    assert "unreadable" in marker.lower() and "24" in marker


def test_ld284_register_row_40_records_a_MEASURED_RACE_not_one_runs_outcome_as_a_shape():
    """LD-284 — the row stated ONE live run's cell-less copy as *"the shape a real read
    produces"*, while the dogfood clone and `ui-parity-matrix-2026-08-03.md` § R13 both showed
    the copied Lookup **populated**. Re-probing settled it: read the instant `settle` returns,
    the values are absent 1.7 s later (2/2 copies); read 3.2 s after the same settle they are
    present (2/2), as on 2/2 content-carrying copies a throttled ladder could not reach sooner
    than 2.7 s. Both
    original captures were real — the discriminating factor is **elapsed time**, and the window
    is under 3 s.

    So the row must (a) never state the cell-less read as a shape except as a correction of
    what it used to say, (b) record the finding as a **race** with the settle-is-not-
    materialised distinction that causes it, (c) keep `without_content: true` apart as the
    separate genuinely cell-less case, and (d) cite the capture, so the next reader checks the
    measurement rather than the prose.
    """
    from base_md import register_rows as _register_rows

    base_md = (_REPO / "BASE.md").read_text(encoding="utf-8")
    row = [r for r in _register_rows(base_md) if r["#"] == "40"][0]
    text = row["Limitation / workaround"]

    falsified = "the shape a real read produces"
    assert text.count(falsified) <= 1, "row 40 states the falsified shape more than once"
    at = text.find(falsified)
    assert at == -1 or "previously stated" in text[max(0, at - 160):at], (
        "row 40 states the cell-less read as the shape a real read produces without marking it "
        "as what the row USED to say — LD-284 measured a sub-3-second race instead")

    assert "SETTLED IS NOT MATERIALISED" in text, (
        "row 40 must record the distinction the race turns on: the settle proves the app is "
        "readable, not that a mirrored column has recomputed")
    assert "materialisation window" in text and "under 3 s" in text, (
        "row 40 must record the MEASURED window, not merely that the two captures disagreed")
    assert "2 of 2" in text, (
        "row 40 must carry the replication counts on both sides of the window — a race stated "
        "without them is an anecdote")
    assert "without_content" in text, (
        "row 40 must keep the genuinely cell-less case (no rows at all) apart from the race")
    assert "ld284-01-copy-lookup-materialisation.json" in (
        text + row["Evidence"]), "row 40 must cite the re-probe capture"
    assert (_REPO / "tests" / "captures" / "base-study" / "captures"
            / "ld284-01-copy-lookup-materialisation.json").is_file(), (
        "the cited re-probe capture is not committed — a citation of a file that is not there "
        "is exactly the defect this row is being fixed for")


def test_ld284_row_40s_REPLICATION_COUNTS_are_the_ONES_ITS_OWN_CAPTURE_CARRIES():
    """LD-284, fix round — the defect the issue was filed for, committed a second time.

    The first rewrite of row 40 said the values were populated on **3 of 3** copies read
    outside the window, *"out to t+120 s, wrapper `type` = `1`"*, as one compound claim. The
    cited capture does not carry that compound: the third copy in that throttled ladder is the
    ``without_content: true`` control, which has **no rows at all** at every tick; only **one**
    ladder ran to t+120 s (the others stop at t+30 s); and the typed wrapper was returned by
    ``records/search`` only — the plain ``GET …/records`` list carried the same cells with no
    wrapper on any run.

    So this test derives every count from the committed capture and holds the row to it. It
    fails if the row over-claims again, in either direction.
    """
    from base_md import register_rows as _register_rows

    capture = json.loads(
        (_CAPTURES / "ld284-01-copy-lookup-materialisation.json").read_text(encoding="utf-8"))

    def _lookup(tick):
        return tick.get("reading", {}).get("columns", {}).get("lookup", {})

    throttled = [r for r in capture["runs"]
                 if any(t.get("route") == "records/search" for t in r["ticks"])]
    content_carrying = [r for r in throttled if not r["without_content"]]
    populated = [r for r in content_carrying
                 if all(_lookup(t).get("rows_with_a_cell", 0) > 0
                        for t in r["ticks"] if t.get("route") == "records/search")]
    controls = [r for r in throttled if r["without_content"]]
    reached_120 = [r for r in throttled
                   if any(t.get("actual_seconds_after_settle", 0) >= 120 for t in r["ticks"])]
    wrapper_routes = {t["route"] for r in throttled for t in r["ticks"]
                      if _lookup(t).get("wrapper_types")}

    # The capture's own numbers — stated here so a re-probe that changes them reddens too.
    assert (len(populated), len(content_carrying)) == (2, 2)
    assert len(controls) == 1 and all(
        _lookup(t).get("rows_with_a_cell", 0) == 0 for t in controls[0]["ticks"])
    assert len(reached_120) == 1
    assert wrapper_routes == {"records/search"}

    base_md = (_REPO / "BASE.md").read_text(encoding="utf-8")
    text = [r for r in _register_rows(base_md) if r["#"] == "40"][0]["Limitation / workaround"]
    plain = text.replace("**", "").replace("`", "")

    assert f"{len(populated)} of {len(content_carrying)} content-carrying" in plain, (
        "row 40 must count the copies the capture actually populated — the content-carrying "
        "ones — not the whole ladder, whose third member is the without_content control")
    assert "3 of 3" not in plain, (
        "row 40 counts the without_content control as a populated copy; it has no rows at all")
    assert "t+30 s" in plain and "t+120 s" in plain, (
        "row 40 must state the depth BOTH ladders reached as well as the one that went "
        "further — a claim carried by one run stated as if carried by all is the defect")
    assert "records/search" in plain and "without a typed wrapper" in plain, (
        "row 40 must attach the typed wrapper to the route that returned it; the plain GET "
        "records list carried the cells without one on every run")


def test_ld305_the_SETTLE_MODULES_OWN_HEADER_carries_row_40s_readable_vs_materialised_line():
    """LD-305 — the THIRD copy of row 40's claim, now held like the other two.

    The finding lives in three places: ``BASE.md`` register row 40, the live arm's docstring
    (``tests/test_live_base_computed_provenance.py``) and the settle contract's **own** module
    header — the one place a reader goes to learn what ``settle`` guarantees. Only the first
    two were pinned, and the header drifted: it stated the copied ``type:19`` Lookup as
    *"recomputed and populated"*, which is the arm of LD-284's measured race that row 40 was
    rewritten to stop asserting as the shape a copy has.

    So this guard holds the header to row 40's distinction — the settle proves the copied
    **app is readable**, not that a mirrored column has materialised — by **citation**, and
    forbids the header from re-deriving row 40's measurements (a second copy of a count is the
    thing that goes stale). What ``settle`` does promise stays asserted here too, so a future
    edit cannot buy the correction by deleting the contract.
    """
    from larkdocio.base import schema_settle

    text = schema_settle.__doc__
    plain = text.replace("**", "").replace("`", "")

    assert "recomputed and populated" not in plain, (
        "the settle header states the copied Lookup as recomputed and populated — the losing "
        "arm of LD-284's measured race; BASE.md register row 40 carries the landed wording")
    assert "SETTLED IS NOT MATERIALISED" in plain, (
        "the settle header must carry row 40's ruling phrase: the settle proves the app is "
        "readable, not that a mirrored column has recomputed")
    assert "register row 40" in plain, (
        "the header must CITE BASE.md register row 40 as the source of the race rather than "
        "author a competing sentence (the Base schema-write spec's standing instruction)")
    assert "re-read" in plain, (
        "row 40's consequence for a caller — one who needs the values must re-read — is the "
        "actionable half of the distinction")

    # No measurement re-derived here. Row 40 owns the counts; a second copy is what drifts.
    for measurement in ("3 of 3", "2 of 2", "1.7 s", "3.2 s", "2.7 s", "t+30 s", "t+120 s"):
        assert measurement not in plain, (
            f"the settle header re-derives row 40's measurement {measurement!r} — cite the "
            "row and quote nothing")

    # AC4: what settle DOES promise is not bought away by the correction.
    assert "readable" in plain
    assert "never a fixed sleep" in plain or "A fixed sleep is a defect" in plain, (
        "the header must keep saying the loop is response-driven and never a fixed sleep")
    assert "bounded" in plain


def test_ac7_a_stage_column_still_renders_the_marker_in_EVERY_row():
    """The provenance layer is additive: the render is untouched."""
    spec = FieldSpec(field_name="stage?", type=24, ui_type="Stage", property=None)
    rows = [base_cells.render_row({}, [spec]) for _ in range(3)]
    assert rows == [[base_cells.STAGE_OPAQUE_MARKER]] * 3


# --------------------------------------------------------------------------- #
# The assembled surface — provenance reaches a caller who read a Base.         #
# --------------------------------------------------------------------------- #

def test_the_assembled_table_carries_its_computed_columns_in_FIELD_ORDER(
        lookup_field, lookup_cells):
    """Derived at assembly, where the raw values are still in hand — the value type cannot be
    recovered from the rendered string afterwards."""
    fields = [
        FieldSpec(field_name="Text", type=1, ui_type="Text", property=None),
        base_table.field_spec(unmarshal(lookup_field, AppTableField)),
    ]
    records = [{"record_id": "r1", "fields": {"lookup": lookup_cells[0]}}]
    read = base_table.assemble_table(table_id="t", name="T", fields=fields, records=records)

    assert [c.field_name for c in read.computed_columns] == ["lookup"]
    assert read.computed_columns[0].value_type == 1
    assert read.computed_columns[0].rolls_up_from_table == "tblvHhs6KA9QYNCo"


def test_a_table_with_no_computed_column_carries_an_EMPTY_reading_not_a_None():
    read = base_table.assemble_table(
        table_id="t", name="T",
        fields=[FieldSpec(field_name="Text", type=1, ui_type="Text", property=None)],
        records=[])
    assert read.computed_columns == ()


def test_the_provenance_reading_makes_NO_CALL_and_imports_no_transport():
    """Free, like the link-column reading beside it: everything comes off a ``property`` the
    read already fetched, so nothing here needs a credential."""
    import ast

    tree = ast.parse((_REPO / "src" / "larkdocio" / "base" / "computed.py")
                     .read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    for banned in ("lark_oapi", "larkdocio.base.read", "larkdocio.base.client",
                   "larkdocio.common", "urllib", "http.client"):
        assert not any(name.startswith(banned) for name in imported), (
            f"the free reading imported a transport ({banned})")


# --------------------------------------------------------------------------- #
# AC8b — dialect-free at birth.                                                #
# --------------------------------------------------------------------------- #

def test_ac8b_no_shipped_string_here_carries_an_INTERNAL_DIALECT_TOKEN():
    """No decision references, no issue ids, no spec/AC/story refs — the transport limitation
    is stated in plain language or it is not consumer-facing text."""
    import re

    source = (_REPO / "src" / "larkdocio" / "base" / "computed.py").read_text(encoding="utf-8")
    for pattern in (r"\bLD-\d+", RETIRED_ID.pattern, r"\bAC\d+", r"\bD\d+[′″‴]", r"\bO\d+[′″‴]",
                    r"\bF\d+-S\d+"):
        assert not re.search(pattern, source), f"internal dialect {pattern} shipped"


# --------------------------------------------------------------------------- #
# LD-631 — the two accessors' own shipped promises, falsified.                  #
#                                                                              #
# `ComputedColumn.writable` and `.rolls_up` are in the docstring corpus a       #
# consumer reads through `help()`, and until now nothing in this repository     #
# read either name: a documented public promise with no falsifier. The tests    #
# below assert what each docstring SAYS, over the module's own kind vocabulary  #
# rather than over a hand-picked pair, so a kind added to `COMPUTED_PAIRS`      #
# enrols itself.                                                               #
# --------------------------------------------------------------------------- #

def _column_of(pair):
    """A reading with one kind's ``(field_type, ui_type)`` pair and nothing else asserted."""
    return base_computed.ComputedColumn(
        field_name="c", field_id="fld", field_type=pair[0], ui_type=pair[1],
        value_type=None, rolls_up_from_table=None, rolls_up_from_field=None,
        aggregation=None, formula_expression=None, formatter=None,
        unavailable=(), note="",
    )


def test_writable_is_FALSE_FOR_EVERY_KIND_THIS_SURFACE_REPORTS():
    """The docstring's promise is "always False", so the falsifier is the whole vocabulary:
    every pair in ``COMPUTED_PAIRS`` — which is the write side's own ``NON_WRITABLE_PAIRS``,
    imported rather than re-declared — reads back not writable."""
    assert base_computed.COMPUTED_PAIRS, "the kind vocabulary is empty; nothing was checked"
    for pair in base_computed.COMPUTED_PAIRS:
        assert _column_of(pair).writable is False, f"{pair} reported itself writable"


def test_writable_is_FALSE_ON_THE_REAL_LOOKUP_AND_FORMULA_SPECIMENS(
        lookup_field, formula_field):
    """The same promise through the shipped seam, on the two captured columns — a synthetic
    dataclass proves the property, a specimen proves the path that builds it."""
    for raw in (lookup_field, formula_field):
        assert base_computed.computed_column(_bridged(raw)).writable is False


def test_rolls_up_is_TRUE_ONLY_FOR_THE_LOOKUP_KIND(lookup_field, formula_field):
    """The docstring's promise is "``True`` for a Lookup — the one kind that mirrors another
    table", and "the one kind" is the falsifiable half: the real Lookup specimen says True,
    the real Formula specimen says False, and so does every other kind in the vocabulary."""
    assert base_computed.computed_column(_bridged(lookup_field)).rolls_up is True
    assert base_computed.computed_column(_bridged(formula_field)).rolls_up is False
    others = [p for p in base_computed.COMPUTED_PAIRS if p != base_computed.LOOKUP]
    assert others, "only the Lookup kind exists; the 'one kind' claim was not exercised"
    for pair in others:
        assert _column_of(pair).rolls_up is False, f"{pair} claimed to roll up"


def test_rolls_up_reads_THE_PAIR_and_not_the_type_number_alone():
    """The pair is what identifies a kind here, so a column carrying the Lookup type number
    under a different ui_type is NOT a Lookup — the mutation this accessor is easiest to get
    wrong in (``self.field_type == 19`` would pass the tests above and fail this one)."""
    assert _column_of((base_computed.LOOKUP[0], "Formula")).rolls_up is False
    assert _column_of((20, base_computed.LOOKUP[1])).rolls_up is False
