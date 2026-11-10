"""The referential-integrity reading: what a link column points at, read for FREE.

Lark maintains referential integrity for **one** of its two link types and not the other,
and the failure is silent. This suite pins the half a reader can answer with **no extra
call at all** — the column-level one — and the three properties that make it honest:

* it is read off the field ``property`` the reader **already fetched**, so a call-count spy
  over the whole read sees exactly the five calls a Base read always costs;
* it has **three** outcomes, not two: present-and-named, named-without-``table_name``, and
  ambiguous — and the ambiguous one is ``cannot-determine``, never a liveness claim;
* the signal **survives the SDK-typed property seam**. ``BASE.md`` register row 12 records
  that the pinned SDK's ``AppTableFieldProperty`` silently drops keys it does not declare,
  and this detector is built on the **absence** of a key: a transport that dropped
  ``table_name`` would report **every** link column as dangling, which is a false-positive
  data-honesty failure rather than a narrow gap. So the survival is a test, from a committed
  capture, and not an assumption.

Every fixture is a **real committed capture** — the post-delete field lists from
``p0-5-02``, the create echoes from ``p0-2-01`` — round-tripped through the pinned SDK's own
deserializer, never a hand-written approximation of them.
"""
import ast
import json

import pytest
from lark_oapi.api.bitable.v1 import AppTableField
from lark_oapi.core.json import JSON

from larkdocio.common.citations import dev_repo_paths
from larkdocio.base import referential
from larkdocio.base import table as base_table
from larkdocio.base.cells import FieldSpec

from guard_kit import REPO_ROOT
import private_tree  # noqa: E402  (LD-685)

_REPO = REPO_ROOT
_CAPTURES = _REPO / "tests" / "captures" / "base-study" / "captures"
_SRC = _REPO / "src" / "larkdocio" / "base"


def _capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def _sdk_field(payload):
    """One captured field dict → the SDK-typed object the read client hands back."""
    return JSON.unmarshal(json.dumps(payload), AppTableField)


@pytest.fixture(scope="module")
def live_link_field_payload():
    """A link column whose target table is ALIVE — the create echo, verbatim."""
    return _capture(
        "p0-2-01-interconnection-field-create.json"
    )["response"]["data"]["SingleLink_multiple_false"]["field"]


@pytest.fixture(scope="module")
def dead_link_field_payload():
    """The SAME kind of column after its whole target table was deleted (``p0-5-02``).

    ``table_id`` still names the dead table; ``table_name`` has dropped out; the cells still
    hold record ids and ``records/search`` on the source table stayed ``code:0``.
    """
    fields = _capture(
        "p0-5-02-symmetric-link-deletion.json"
    )["response"]["data"]["main_fields_after_target_table_delete"]
    return [f for f in fields if f["field_name"] == "SLink"][0]


# --------------------------------------------------------------------------- #
# AC1 — the detector ships, and it makes ZERO extra calls                      #
# --------------------------------------------------------------------------- #

def test_ac1_a_link_whose_TARGET_TABLE_IS_GONE_is_reported_as_such(dead_link_field_payload):
    spec = base_table.field_spec(_sdk_field(dead_link_field_payload))
    reading = referential.link_column(spec)
    assert reading is not None
    assert reading.state == referential.TARGET_TABLE_MISSING
    assert reading.dangling is True
    assert reading.target_table_id == "tblsT2Ons4CcdJgY"
    assert reading.target_table_name is None


def test_ac1_a_link_whose_TARGET_TABLE_IS_ALIVE_is_not(live_link_field_payload):
    spec = base_table.field_spec(_sdk_field(live_link_field_payload))
    reading = referential.link_column(spec)
    assert reading.state == referential.TARGET_TABLE_LIVE
    assert reading.dangling is False
    assert reading.target_table_name == "p0zoo-Ref-033103"


def test_ac1_the_reading_is_on_the_READ_RESULT_and_costs_NO_EXTRA_CALL(monkeypatch,
                                                                      dead_link_field_payload):
    """The whole point of this rung: the signal is in a field property the reader already
    fetched, so asking for it moves the call count by **zero**."""
    from base_captures import scratch_base

    import larkdocio.common.auth as auth
    from larkdocio.base import read as base_read

    def boom(*_a, **_kw):
        raise AssertionError("the referential reading consulted a WRITE credential")

    monkeypatch.setattr(auth, "get_write_credentials", boom, raising=False)

    app, tables, per_table = scratch_base()
    calls = []
    dead = _sdk_field(dead_link_field_payload)

    class _SpyClient:
        def get_app(self, app_token):
            calls.append("get_app")
            return app

        def list_tables(self, app_token):
            calls.append("list_tables")
            return tables

        def list_fields(self, app_token, table_id):
            calls.append("list_fields")
            # The dangling column joins the FIRST table's real captured field list, so the
            # reading is exercised on the shipped read path rather than on a bare spec.
            fields = list(per_table[table_id][0])
            if table_id == tables[0].table_id:
                fields.append(dead)
            return fields

        def search_records(self, app_token, table_id):
            calls.append("search_records")
            return per_table[table_id][1]

    doc = base_read.read_base("BaseScratchExample000000001", client=_SpyClient())
    before = len(calls)

    dangling = doc.tables[0].dangling_link_columns
    # Touched twice on purpose: a lazily-resolving implementation would show up here.
    assert doc.tables[0].dangling_link_columns == dangling
    assert [c.field_name for c in dangling] == ["SLink"]
    assert len(calls) == before == 6, calls


def test_ac1_the_reading_takes_NO_FLAG_and_is_therefore_ALWAYS_AVAILABLE():
    """It is not behind an opt-in, because it costs nothing to be right about."""
    prop = base_table.BaseTableRead.dangling_link_columns
    assert isinstance(prop, property)
    assert isinstance(base_table.BaseTableRead.link_columns, property)


def test_ac1_the_module_reaches_NO_CLIENT_AND_NO_TRANSPORT():
    """Structural, not incidental — the same AST posture the diff leg carries."""
    tree = ast.parse((_SRC / "referential.py").read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    for name in names:
        assert not name.startswith("lark_oapi"), name
        for forbidden in ("larkdocio.base.client", "larkdocio.base.write_client",
                          "larkdocio.base.schema_client", "requests", "http", "urllib"):
            assert not (name == forbidden or name.startswith(forbidden + ".")), name
    source = (_SRC / "referential.py").read_text(encoding="utf-8")
    for token in ("open.larksuite.com", "open.feishu.cn", "/open-apis/"):
        assert token not in source


# --------------------------------------------------------------------------- #
# AC2 — a HEURISTIC with its evidence, and cannot-determine where ambiguous    #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("prop,expected", [
    ({"multiple": True, "table_id": "tblX", "table_name": "Ref"},
     "TARGET_TABLE_LIVE"),
    ({"multiple": True, "table_id": "tblX"},
     "TARGET_TABLE_MISSING"),
    ({"multiple": True, "table_id": "tblX", "table_name": None},
     "TARGET_TABLE_MISSING"),
    # Ambiguous shapes: no claim is made in either direction.
    ({"multiple": True, "table_id": "tblX", "table_name": ""}, "TARGET_TABLE_UNKNOWN"),
    ({"multiple": True, "table_name": "Ref"}, "TARGET_TABLE_UNKNOWN"),
    ({}, "TARGET_TABLE_UNKNOWN"),
    (None, "TARGET_TABLE_UNKNOWN"),
])
def test_ac2_the_three_outcomes_are_pinned(prop, expected):
    spec = FieldSpec(field_name="SLink", type=18, ui_type="SingleLink", property=prop)
    assert referential.target_table_state(spec) == getattr(referential, expected)


def test_ac2_a_NON_LINK_column_makes_NO_LIVENESS_CLAIM():
    text = FieldSpec(field_name="Notes", type=1, ui_type="Text", property=None)
    assert referential.link_column(text) is None
    assert referential.target_table_state(text) == referential.TARGET_TABLE_UNKNOWN


@private_tree.citations
def test_ac2_the_code_path_says_OBSERVED_cites_its_capture_and_carries_a_REVISIT_TRIGGER():
    assert "observed" in referential.DANGLING_TARGET_IS_OBSERVED.lower()
    assert "p0-5-02" in referential.DANGLING_TARGET_EVIDENCE
    # LD-480 added the route-scoped re-measurement beside the original specimen, so the guard
    # holds EVERY cited path rather than exactly one — a count is not the property that matters.
    assert "ld480-table-delete-link-semantics.json" in referential.DANGLING_TARGET_EVIDENCE
    captured = dev_repo_paths(referential.DANGLING_TARGET_EVIDENCE)
    assert len(captured) >= 2
    # The constant is labelled for the consumer who cannot open it; the paths inside it still
    # have to resolve for the maintainer who can.
    for path in captured:
        assert (_REPO / path).exists(), path
    trigger = referential.DANGLING_TARGET_REVISIT_TRIGGER.lower()
    assert "table_name" in trigger and "live" in trigger
    # LD-480: the two-way sighting that did not reproduce is named as what would widen the reading.
    assert "two-way" in trigger and "second sighting" in trigger


def test_ac2_every_state_has_a_MEANING_and_the_set_is_exhaustive():
    assert set(referential.TARGET_TABLE_STATES) == set(referential.STATE_MEANINGS)
    assert len(referential.TARGET_TABLE_STATES) == 3
    for meaning in referential.STATE_MEANINGS.values():
        assert len(meaning) > 40


def test_ac2_the_HEURISTIC_IS_AUTHORED_ONCE_and_the_write_legs_DELEGATE():
    """A second spelling of the signature is the defect this asserts against: the model's
    dangling-target reading and the destructive scan's both resolve to this one function."""
    from larkdocio.base import diff as base_diff
    from larkdocio.base import loss_preview

    assert base_diff.has_dangling_target is referential.has_dangling_target
    for module_file in ("diff.py", "loss_preview.py"):
        source = (_SRC / module_file).read_text(encoding="utf-8")
        assert 'not self.target_table_name' not in source
        assert 'and not table_name' not in source
    scanned = loss_preview.ScannedField(
        table_id="tblMain", table_name="Main", field_id="fldA", field_name="SLink",
        field_type=18, ui_type="SingleLink",
        property={"multiple": True, "table_id": "tblGone"})
    assert scanned.dangling is True


# --------------------------------------------------------------------------- #
# AC2b — the signal must SURVIVE the SDK-typed property seam                   #
# --------------------------------------------------------------------------- #

def test_ac2b_table_name_SURVIVES_the_SDK_TYPED_SEAM_for_a_LIVE_target_table(
        live_link_field_payload):
    """``BASE.md`` register **row 12** records that the pinned SDK's typed field-property
    model silently drops every key it does not declare — ``back_field_id`` among them. This
    detector is built on the **absence** of ``table_name``, so a seam that dropped it would
    mark **every** link column as dangling: a false positive about data honesty, not a gap.

    The claim is therefore tested rather than assumed, and tested where it matters — on a
    column whose target table is ALIVE, driven from the committed capture through the very
    bridge the shipped read path uses.
    """
    typed = _sdk_field(live_link_field_payload)
    assert typed.property.table_name == "p0zoo-Ref-033103"

    spec = base_table.field_spec(typed)
    assert spec.property["table_name"] == "p0zoo-Ref-033103"
    assert referential.target_table_state(spec) == referential.TARGET_TABLE_LIVE


def test_ac2b_the_dropped_key_row_12_records_is_STILL_DROPPED_and_is_NOT_this_signal(
        live_link_field_payload):
    """The other side of the same seam, so the coupling is visible: ``back_field_id`` really
    does not survive — which is why nothing here reads it — while ``table_name`` does."""
    duplex = _capture(
        "p0-2-01-interconnection-field-create.json"
    )["response"]["data"]["DuplexLink"]["field"]
    assert duplex["property"]["back_field_id"] == "fldrYKsT0L"

    spec = base_table.field_spec(_sdk_field(duplex))
    assert "back_field_id" not in spec.property
    assert spec.property["back_field_name"] == "p0zoo-Main-033103-DuplexLink"
    assert spec.property["table_name"] == "p0zoo-Ref-033103"
    assert "back_field_id" not in (_SRC / "referential.py").read_text(encoding="utf-8")


def test_ac2b_a_seam_that_DROPPED_table_name_would_be_caught(live_link_field_payload):
    """The deliberate-defect proof for AC2b: simulate the drop and watch a LIVE column turn
    into a dangling one. This is exactly the false positive the test above exists to stop."""
    payload = json.loads(json.dumps(live_link_field_payload))
    payload["property"].pop("table_name")
    spec = base_table.field_spec(_sdk_field(payload))
    assert referential.target_table_state(spec) == referential.TARGET_TABLE_MISSING


# --------------------------------------------------------------------------- #
# The link-column recognition, and the whole-table reading                     #
# --------------------------------------------------------------------------- #

def test_a_link_column_is_recognised_even_when_the_capture_carries_NO_UI_TYPE(
        dead_link_field_payload):
    """The capture that proves the dangling signature carries no ``ui_type`` at all, so a
    detector keyed on the ``(type, ui_type)`` pair would be blind exactly where it matters."""
    assert "ui_type" not in dead_link_field_payload
    spec = base_table.field_spec(_sdk_field(dead_link_field_payload))
    assert spec.ui_type == ""
    assert referential.is_link_column(spec) is True


def test_the_whole_table_reading_keeps_FIELD_ORDER_and_names_only_link_columns(
        dead_link_field_payload, live_link_field_payload):
    specs = [
        FieldSpec(field_name="Notes", type=1, ui_type="Text"),
        base_table.field_spec(_sdk_field(live_link_field_payload)),
        base_table.field_spec(_sdk_field(dead_link_field_payload)),
    ]
    assert [c.field_name for c in referential.link_columns(specs)] == [
        "SingleLinkOne", "SLink"]
    assert [c.field_name for c in referential.dangling_link_columns(specs)] == ["SLink"]


def test_every_reading_carries_a_PLAIN_LANGUAGE_note():
    for prop in ({"table_id": "t", "table_name": "R"}, {"table_id": "t"}, {"table_name": "R"}):
        spec = FieldSpec(field_name="L", type=21, ui_type="DuplexLink", property=prop)
        note = referential.link_column(spec).note
        assert len(note) > 40 and note in referential.STATE_MEANINGS.values()


# --------------------------------------------------------------------------- #
# AC6 — no destructive verb anywhere on this surface                           #
# --------------------------------------------------------------------------- #

def _register_rows():
    from base_md import register_rows as rows

    return {r["#"]: r for r in rows((_REPO / "BASE.md").read_text(encoding="utf-8"))}


@pytest.fixture(scope="module")
def register():
    return _register_rows()


@pytest.fixture(scope="module")
def new_rows(register):
    return {n: register[n] for n in ("33", "34", "35", "36")}


_LIMITATION = "Limitation / workaround"
_TRIGGER = "Revisit trigger — the observable API change"


# --------------------------------------------------------------------------- #
# AC3 — the referential facts are register rows with evidence + triggers       #
# --------------------------------------------------------------------------- #

def test_ac3_each_new_row_names_its_EVIDENCE_its_CONSEQUENCE_and_its_TRIGGER(new_rows):
    for number, row in new_rows.items():
        assert len(row[_LIMITATION]) > 200, number
        assert "dev/base-study/" in row["Evidence"], number
        assert "tests/test_base_referential.py" in row["Evidence"], number
        assert len(row[_TRIGGER]) > 60, number


def test_ac3_i_the_MIRROR_row_names_the_AUTO_CREATE_and_the_NAMING_RULE(new_rows):
    text = new_rows["33"][_LIMITATION]
    assert "auto-created" in text.lower()
    assert "<source table name>-<source field name>" in text
    assert "another table" in text.lower()


def test_ac3_i_the_MIRROR_row_names_BACK_FIELD_NAME_and_CITES_row_12_for_the_id(new_rows):
    """The mint's own correction. A row claiming this library reads ``back_field_id`` would be
    false: the typed property bridge drops it, which is row 12's finding — cited, not
    re-authored here."""
    text = new_rows["33"][_LIMITATION]
    assert "back_field_name" in text
    assert "row 12" in text
    assert "drops" in text.lower()
    # The row must not claim the library reads the dropped key.
    assert "reads `back_field_id`" not in text
    assert "back_field_id" not in (_SRC / "referential.py").read_text(encoding="utf-8")


def test_ac3_ii_the_AUTO_POPULATE_row_says_NO_WRITE_TO_THE_TARGET_TABLE(new_rows):
    text = new_rows["34"][_LIMITATION]
    assert "NO WRITE TO THE TARGET TABLE" in text.upper()
    assert "auto-populates" in text.lower()


def test_ac3_iii_the_RECORD_DELETE_row_states_the_ASYMMETRY_IN_BOTH_DIRECTIONS(new_rows):
    text = new_rows["35"][_LIMITATION]
    assert "DANGLES" in text.upper()
    assert "maintained" in text.lower()
    assert "1254043" in text, (
        "the row must name the code a resolver will meet, or 'treat it as normal' is advice "
        "nobody can act on")


def test_ac3_iv_the_TABLE_DELETE_row_states_the_SILENCE_and_the_FREE_DETECTOR(new_rows):
    text = new_rows["36"][_LIMITATION]
    assert "table_name" in text and "table_id" in text
    assert "code:0" in text
    assert "ZERO extra calls" in text
    assert "cannot-determine" in text
    assert "observed" in text.lower()
    assert "row 12" in text, "the typed-seam coupling must be discoverable from the row"


def test_ac3_DEFECT_softening_a_row_from_DANGLES_to_MAY_BE_EMPTY_reddens(new_rows):
    """The test-rigor amplifier, made real: the wording *is* the product here, so a hedge
    that turns a broken reference back into an ordinary empty cell must fail a check."""
    softened = dict(new_rows["35"])
    softened[_LIMITATION] = softened[_LIMITATION].replace("DANGLES", "may be empty")
    with pytest.raises(AssertionError):
        assert "DANGLES" in softened[_LIMITATION].upper()
    assert "DANGLES" in new_rows["35"][_LIMITATION].upper()


def test_ac3_the_MIRROR_is_described_the_SAME_WAY_from_BOTH_SIDES(new_rows):
    """A two-way link read from the source side and from the target side is one relationship,
    and the register must not describe it as two."""
    duplex = _capture(
        "p0-2-01-interconnection-field-create.json")["response"]["data"]
    source = duplex["DuplexLink"]["field"]
    mirror_names = duplex["duplex_mirror_in_ref_table"]["ref_fields_after"]
    assert source["property"]["back_field_name"] in mirror_names
    from larkdocio.base.field_authoring import duplex_mirror_name
    assert duplex_mirror_name("p0zoo-Main-033103", "DuplexLink") in mirror_names
    # And both sides read as pointing at a live table, through the shipped reading.
    spec = base_table.field_spec(_sdk_field(source))
    assert referential.target_table_state(spec) == referential.TARGET_TABLE_LIVE
    assert referential.link_column(spec).symmetric is True


# --------------------------------------------------------------------------- #
# AC4 — the cardinality fact is CITED from its owner, never re-asserted        #
# --------------------------------------------------------------------------- #

def test_row_22_is_the_ONE_OWNER_of_the_cardinality_fact(register, new_rows):
    """``multiple: false`` is pinned on the read side by the link renderer and on the write
    side by the encoder registry, and register **row 22** is where a consumer meets both in
    one place. This story adds no second row for it — a third definition of one rule is the
    defect, not the coverage."""
    row = register["22"][_LIMITATION]
    assert "multiple: false" in row and "cardinality" in row.lower()
    for number, other in new_rows.items():
        assert "cardinality" not in other[_LIMITATION].lower(), number


def test_row_22s_CLAIM_and_the_ENFORCING_CODE_agree(register):
    """The row says the write side enforces no cardinality at all. The code has to still be
    doing exactly that, or the register is describing a library that no longer exists."""
    from larkdocio.base import write_cells
    from larkdocio.base.cells import _r_links

    assert "enforces no cardinality" in register["22"][_LIMITATION]
    assert "enforces a cardinality the server does not" in (write_cells.__doc__ or "")
    assert "**not** a cardinality guarantee" in (_r_links.__doc__ or "")

    spec = FieldSpec(field_name="SLink", type=18, ui_type="SingleLink",
                     property={"multiple": False, "table_id": "tblX", "table_name": "Ref"})
    two = _capture("p0-4-06-field-authoring-boundary.json")[
        "response"]["data"]["multiple_false_fed_two_ids"]["echo"]
    assert len(two) == 2
    encoded = write_cells.encode_cell(two, spec)
    assert encoded == two, "the encoder must pass both ids through, exactly as Lark accepted"


def test_ac4_the_TWO_EMPTY_FORMS_are_cited_and_NOT_redefined(new_rows):
    """The null and the empty id list are the read surface's own pin. This story points at
    them; it does not add a second statement of what an empty link cell is."""
    text = new_rows["34"][_LIMITATION]
    assert "two empty forms" in text.lower()
    assert "not** re-defined here" in text or "not re-defined here" in text
    source = (_SRC / "referential.py").read_text(encoding="utf-8")
    assert "link_record_ids" not in source, (
        "reading a link CELL is the resolution half; this module reads the COLUMN only")


# --------------------------------------------------------------------------- #
# AC4b — three vocabularies, kept distinct                                     #
# --------------------------------------------------------------------------- #

def test_ac4b_no_new_row_calls_a_READABLE_column_UNSUPPORTED(new_rows):
    for number, row in new_rows.items():
        assert "unsupported" not in row[_LIMITATION].lower(), number


def test_ac4b_no_new_row_claims_LARK_HAS_NO_BUTTON_TYPE(register, new_rows):
    """Button has a real read identity and its will-not-support status is a product ruling,
    not an API fact. Neither half may be contradicted by wording added here."""
    for number, row in new_rows.items():
        assert "button" not in row[_LIMITATION].lower(), number
    assert "3001" in register["13"][_LIMITATION]


def test_ac4b_NEITHER_LANDED_VOCABULARY_CONSTANT_IS_RE_SPELLED_HERE():
    """*Can I create this column?*, *can I write this cell?* and *can I read and render it?*
    are three different questions with three different owners. This module answers none of
    them and re-lists neither constant."""
    source = (_SRC / "referential.py").read_text(encoding="utf-8")
    for token in ("field_vocabulary", "write_vocabulary", "check_authorable",
                  "is_non_writable", "authorable", "NON_WRITABLE"):
        assert token not in source, token


# --------------------------------------------------------------------------- #
# AC5 — the mirror's cross-table effect, disclosed on the write side too       #
# --------------------------------------------------------------------------- #

def test_ac5_the_register_row_and_the_PLAN_ENTRY_DISCLOSURE_do_not_contradict(new_rows):
    """The in-memory model discloses a two-way link edit's effect in the other table on the
    plan entry; the register row is the consumer-facing half of the same disclosure. Both say
    the server does it and that no write to the target table is planned."""
    from larkdocio.base.diff import DUPLEX_MIRROR_EFFECT

    row = new_rows["34"][_LIMITATION]
    assert "no write to that table" in DUPLEX_MIRROR_EFFECT
    assert "server does that itself" in DUPLEX_MIRROR_EFFECT
    assert "NO WRITE TO THE TARGET TABLE" in row.upper()
    assert "done by the server" in row.lower()
    assert "performed as a second write" in row, (
        "the row must say the reverse population is NOT re-performed by this library, or a "
        "reader could conclude the plan owes a write to the other table")


def test_ac5_the_disclosure_is_reachable_from_a_real_DIFF():
    """Not a string test: a two-way link edit really does produce the cross-table effect."""
    from larkdocio.base import diff as base_diff

    spec = FieldSpec(field_name="DuplexLink", type=21, ui_type="DuplexLink",
                     property={"table_id": "tblRef", "table_name": "Ref"})
    effects = base_diff._effects_for(spec)
    assert [e.effect for e in effects] == [base_diff.DUPLEX_MIRROR_EFFECT]
    assert effects[0].dangling_target is False


# --------------------------------------------------------------------------- #
# AC6 — the destructive blast radius is CITED, never duplicated                #
# --------------------------------------------------------------------------- #

def test_ac6_every_row_about_a_DELETE_points_at_the_cross_table_loss_preview(new_rows):
    for number in ("35", "36"):
        text = new_rows[number][_LIMITATION]
        assert "loss_preview" in text, number
        assert "row 32" in text, number
        assert "cited" in text.lower() or "never duplicated" in text.lower(), number


def test_ac6_NO_LOSS_PREVIEW_LOGIC_IS_RE_IMPLEMENTED_HERE():
    source = (_SRC / "referential.py").read_text(encoding="utf-8")
    for token in ("loss_preview", "consent", "LossNotEnumerable", "threshold",
                  "AppScan", "ScannedField"):
        assert token not in source, token


# --------------------------------------------------------------------------- #
# AC7 — capabilities() reports them as LIMITATIONS, in exactly one place       #
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def base_read_surface():
    import larkdocio

    return larkdocio.capabilities(full=True)["surfaces"]["base-read"]


def test_ac7_the_referential_facts_are_LIMITS_of_the_read_surface(base_read_surface):
    summary = base_read_surface["levels"]["summary"]
    # The count word moves whenever a later story adds a limit beside these — LD-270 added a
    # fifth — so what this pins is that the referential facts are STATED AS LIMITS of the read
    # surface, not the arithmetic of how many other limits happen to sit next to them.
    assert "LIMITS TO PLAN AROUND" in summary
    for phrase in (
        "A REFERENCE CAN BREAK",
        "one of its two link kinds",
        "still answers success",
        "cannot-determine",
        "NO extra call",
        "mirror column in the target table",
        "no write to that table at all",
        "never a repair",
    ):
        assert phrase in summary, phrase


def test_ac7_they_are_NOT_reported_as_FEATURES(base_read_surface):
    """A limitation stated as an operation would read as something a caller can invoke.

    Scoped to the LINK-RESOLUTION limitation names (dangling / link-column helpers), not the
    bare substring ``link``: ``record_permalink`` is a genuine feature operation that legitimately
    carries the word, so it is excluded — the guard is about limitations posing as operations."""
    names = [op["name"] for op in base_read_surface["operations"]]
    offenders = [n for n in names
                 if "dangl" in n.lower() or ("link" in n.lower() and "permalink" not in n.lower())]
    assert not offenders, offenders


def test_ac7_the_limitation_is_stated_in_EXACTLY_ONE_PLACE():
    """The registry is projected into several documents; a second statement of the same rule
    is what makes two of them disagree later."""
    import json as _json

    import larkdocio

    blob = _json.dumps(larkdocio.capabilities(full=True), default=str, sort_keys=True)
    assert blob.count("cannot-determine") == 1
    assert blob.count("LIMITS TO PLAN AROUND") == 1


# --------------------------------------------------------------------------- #
# AC8 — dialect-free at birth                                                  #
# --------------------------------------------------------------------------- #

def test_ac8_every_shipped_string_this_story_adds_is_DIALECT_FREE():
    """No issue id, no requirement id, no criterion number, no decision label — every
    doctrine here is stated in plain language, and the shared guard is neither weakened nor
    given a new exclusion."""
    from consumer_text import dialect_hits

    texts = {"module": referential.__doc__}
    for name in referential.__all__:
        obj = getattr(referential, name)
        if isinstance(obj, str):
            texts[name] = obj
        elif getattr(obj, "__doc__", None):
            texts[name] = obj.__doc__
    texts.update({f"meaning:{k}": v for k, v in referential.STATE_MEANINGS.items()})
    texts["BaseTableRead.dangling_link_columns"] = (
        base_table.BaseTableRead.dangling_link_columns.fget.__doc__)
    texts["BaseTableRead.link_columns"] = base_table.BaseTableRead.link_columns.fget.__doc__

    offenders = {label: dialect_hits(text) for label, text in texts.items()
                 if text and dialect_hits(text)}
    assert not offenders, offenders


def test_ac6_this_surface_exposes_NO_DESTRUCTIVE_VERB_AT_ALL():
    """Rendering a broken reference honestly is the product. Repairing one is not this
    library's business, and the absence is asserted rather than intended."""
    forbidden = ("delete", "remove", "purge", "repair", "clean", "prune", "fix", "drop",
                 "write", "apply", "patch")
    for name in referential.__all__:
        assert not any(verb in name.lower() for verb in forbidden), name
    tree = ast.parse((_SRC / "referential.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert not any(node.name.lower().startswith(verb) for verb in forbidden), node.name
