"""LD-311 — the typed-SDK door vs the dict/bridged door: three characterization tests.

**This file moves nothing and asserts nothing new.** It pins what three readers do *today*
when the same field arrives through the two doors the library actually has, so that LD-312
(the refactor audit's T3 — *"the typed-property walk: five copies, five key lists"*) can prove
its shared primitive changed no answer. Written per
``dev/refactor-audit-2026-08-06.md`` § T3 → *"Safety net — the one place characterization tests
are OWED"*, and modelled on the assertion that already exists for the **computed** reader
(``tests/test_base_computed_provenance.py`` — *"the typed door and the bridged one must answer
the same table for the same column"*).

**The doors.** Every Base field reaches these readers as one of three shapes, and all three are
shipped paths:

* **the typed door** — ``lark_oapi``'s own ``AppTableField``, whose ``property`` is an
  ``AppTableFieldProperty`` **object**. This is what the read client hands back and what a
  caller holding the client's own objects reads (the destructive scan is one).
* **the bridged door** — ``base.table.field_spec(typed)``, whose ``property`` is the dict the
  SDK's serializer produced. This is what the render path sees.
* **the dict door** — ``base.table.field_spec(payload)`` /
  ``FieldSpec.from_payload(payload)``, whose ``property`` is the wire dict **verbatim**. This
  is what a capture-driven read and every offline fixture sees.

**Why this file has to exist.** Each of the five walk sites hard-codes *which keys it copies*
off a typed property, and that key list only ever fires **on the typed door** — so a fixture
built from a raw capture cannot reproduce a mistake in it. That is not hypothetical: LD-281
shipped a walk that required a ``Mapping`` at every step while the live door hands objects, and
``base/loss_preview.py``'s ``_property_of`` docstring is a written post-mortem of the same
class. The offline suite is blind to it *unless a real SDK typed object is deserialized in the
test*, which is what every test below does.

**Every payload here is a committed capture** (``tests/captures/base-study/captures/``) round-tripped
through the pinned SDK's own deserializer — never a hand-mocked object (PROJECT.md § Quality
bar). Two payloads are copies of a capture with one key retargeted to ``null``; each says so at
its fixture and exists to reach the *absent-vs-null* seam the SDK's serializer creates.

**Two divergences are pinned AS THEY ARE, not repaired** (see the per-reader sections):
``hierarchy._field_property`` narrows to one key on the typed door and does not on the others,
and the SDK's property model drops keys it does not declare before ``table._property_dict`` ever
runs. Both are pre-existing, documented behaviour; LD-312 must **preserve** them, and may not
"fix" either under cover of a behaviour-preserving move.
"""
import copy
import json

import pytest

from lark_oapi.api.bitable.v1 import AppTableField
from lark_oapi.core.json import JSON

from larkdocio.base import hierarchy as base_hierarchy
from larkdocio.base import referential
from larkdocio.base import table as base_table

from base_captures import capture


# --------------------------------------------------------------------------- #
# The doors.                                                                   #
# --------------------------------------------------------------------------- #

def typed_door(payload: dict):
    """A captured field dict → **the SDK's own typed object**, as the read client hands it.

    The one door the offline suite was blind on: ``property`` here is an
    ``AppTableFieldProperty`` object, not a mapping.
    """
    field = JSON.unmarshal(json.dumps(payload), AppTableField)
    assert not isinstance(field.property, dict), (
        "the typed door must really be typed — if the SDK started deserializing `property` to "
        "a dict, every parity assertion below would be comparing the same door with itself")
    return field


def bridged_door(payload: dict):
    """The typed object put through ``field_spec`` — the shape the render path reads."""
    spec = base_table.field_spec(typed_door(payload))
    assert spec.property is None or isinstance(spec.property, dict)
    return spec


def dict_door(payload: dict):
    """The wire dict put through ``field_spec`` — the shape every capture-driven read sees."""
    spec = base_table.field_spec(payload)
    assert spec.property is None or isinstance(spec.property, dict)
    return spec


# --------------------------------------------------------------------------- #
# Specimens — committed captures, plus two null-retargeted copies of one.       #
# --------------------------------------------------------------------------- #

def _interconnection():
    return capture(
        "p0-2-01-interconnection-field-create.json")["response"]["data"]


@pytest.fixture(scope="module")
def live_link():
    """A one-way link whose target table is ALIVE — the create echo, verbatim."""
    return _interconnection()["SingleLink_multiple_false"]["field"]


@pytest.fixture(scope="module")
def duplex_link():
    """The two-way link — the specimen that carries ``back_field_id``, a key the SDK's
    property model does **not** declare (``BASE.md`` register row 12)."""
    return _interconnection()["DuplexLink"]["field"]


@pytest.fixture(scope="module")
def dead_link():
    """The same kind of column after its whole target table was deleted (``p0-5-02``):
    ``table_id`` still names the dead table and ``table_name`` has dropped **out of the
    payload entirely**."""
    fields = capture(
        "p0-5-02-symmetric-link-deletion.json"
    )["response"]["data"]["main_fields_after_target_table_delete"]
    return [f for f in fields if f["field_name"] == "SLink"][0]


@pytest.fixture(scope="module")
def explicitly_nulled_link(live_link):
    """``live_link`` with ``table_name`` retargeted to ``null`` — *derived from* the capture.

    No capture in the tree carries an explicitly ``null`` ``table_name``, and it is the one
    payload that reaches the seam the SDK's serializer creates: the serializer **omits** a
    null-valued key, so the bridged door loses the difference between *"the key was `null`"* and
    *"the key was absent"* while the dict door keeps it. ``base/table.py::_raw_fields``'
    docstring records exactly this asymmetry. Whether the readers below answer the same through
    both doors anyway is the question, and the answer is what LD-312 must not change.
    """
    payload = copy.deepcopy(live_link)
    payload["property"]["table_name"] = None
    return payload


def _self_link(kind: str):
    return capture(
        "subitems-b-04-selflink-field-create.json"
    )["response"]["data"]["attempts"][kind]["created_field"]


@pytest.fixture(scope="module")
def self_single_link():
    """The SELF-referencing one-way link the row-hierarchy spike created."""
    return _self_link("SelfSingleLink")


@pytest.fixture(scope="module")
def self_duplex_link():
    """The SELF-referencing two-way link — same capture, and it carries ``back_field_id``."""
    return _self_link("SelfDuplexLink")


# =========================================================================== #
# READER 1 — `base/referential.py::_property_of` (the two-key walk)             #
# =========================================================================== #

def test_referential_property_of_copies_EXACTLY_TABLE_ID_AND_TABLE_NAME_TODAY(duplex_link):
    """The key list as it stands: two keys, and the rest of the property does not come through.

    Pinned in **both** directions on purpose. ``multiple`` and ``back_field_name`` are right
    there on the typed object and are **not** copied — reading more keys would widen this
    surface's behaviour, which the audit rules a spec question rather than a refactor. So this
    test would redden both if a key stopped coming through and if a new one started.
    """
    walked = referential._property_of(typed_door(duplex_link))

    assert sorted(walked) == ["table_id", "table_name"], (
        "referential's walk copies exactly these two keys today; LD-312 may not widen or "
        "narrow that list under cover of a behaviour-preserving move")
    assert walked == {"table_id": "tblauNkOg3QoDL99",
                      "table_name": "p0zoo-Ref-033103"}


def test_referential_property_of_hands_a_MAPPING_BACK_UNCHANGED_when_it_already_is_one(
        live_link):
    """The mapping doors short-circuit: what came in is what goes out, by identity."""
    for spec in (bridged_door(live_link), dict_door(live_link)):
        assert referential._property_of(spec) is spec.property


@pytest.mark.parametrize("specimen", ["live_link", "duplex_link", "dead_link",
                                      "explicitly_nulled_link"])
def test_referential_link_column_is_IDENTICAL_THROUGH_ALL_THREE_DOORS(specimen, request):
    """**The net.** One field, three doors, one whole ``LinkColumn`` — equal, not merely truthy.

    Equality is on the entire returned record (target table id, target table name, the state
    and its note), so a walk that lost a key would redden here even if it still produced a
    plausible reading. The four specimens cover every outcome the reading has: a live target, a
    live target reached through the two-way kind, a target table that is **gone**, and a
    ``table_name`` that is explicitly ``null``.
    """
    payload = request.getfixturevalue(specimen)
    typed = referential.link_column(typed_door(payload))
    bridged = referential.link_column(bridged_door(payload))
    plain = referential.link_column(dict_door(payload))

    assert typed is not None
    assert typed == bridged, (
        "the typed door and the bridged one must answer the same link column for the same field")
    assert typed == plain, (
        "the typed door and the dict door must answer the same link column for the same field")
    assert (referential.target_table_state(typed_door(payload))
            == referential.target_table_state(bridged_door(payload))
            == referential.target_table_state(dict_door(payload))
            == typed.state)


def test_referential_a_MISSING_KEY_AND_AN_EXPLICIT_NULL_read_the_same_dangling_answer(
        dead_link, explicitly_nulled_link):
    """The equivalence ``_property_of``'s docstring rests on, made a test.

    *"On a typed object an undeclared key is simply absent, which reads identically to the key
    being ``None``."* Two payloads reach that claim from opposite sides — one where the wire
    never sent ``table_name``, one where the wire sent it as ``null`` — and the seam is real in
    between: the walk re-materialises the key as ``None`` on the typed door, the serializer
    **drops** it on the bridged door, and the dict door keeps it as ``None``. All the same
    answer.
    """
    for payload in (dead_link, explicitly_nulled_link):
        assert referential._property_of(typed_door(payload))["table_name"] is None
        assert "table_name" not in bridged_door(payload).property
        for door in (typed_door, bridged_door, dict_door):
            assert (referential.target_table_state(door(payload))
                    == referential.TARGET_TABLE_MISSING)
            assert referential.has_dangling_target(door(payload)) is True

    assert "table_name" not in dead_link["property"], (
        "the p0-5-02 specimen no longer omits table_name — the deleted-table signature changed")
    assert dict_door(explicitly_nulled_link).property["table_name"] is None


# =========================================================================== #
# READER 2 — `base/hierarchy.py::_field_property` (the one-key walk)            #
# =========================================================================== #

def test_hierarchy_field_property_copies_EXACTLY_TABLE_ID_TODAY_and_NARROWS_the_typed_door(
        self_duplex_link):
    """One key — and a **divergence between the doors that is pinned, not repaired.**

    ``hierarchy``'s walk copies ``table_id`` alone, so on the typed door it returns a
    one-key mapping while the mapping doors are handed straight back with every key the wire
    carried. That asymmetry is invisible in this reader's *output* (the next test proves it) —
    ``hierarchy_config`` reads ``table_id`` and nothing else — which is exactly why it survived
    unnoticed and exactly why it is written down here. **LD-312 must preserve today's answer,
    not today's intermediate**: a shared primitive that copies more keys is acceptable only if
    every assertion in the next test still holds.
    """
    typed_walk = base_hierarchy._field_property(typed_door(self_duplex_link))
    assert sorted(typed_walk) == ["table_id"]
    assert typed_walk == {"table_id": "tbljnCMElmG4kiQZ"}

    bridged = bridged_door(self_duplex_link)
    bridged_walk = base_hierarchy._field_property(bridged)
    assert bridged_walk is bridged.property, "a mapping is handed straight back"
    assert set(bridged_walk) > set(typed_walk), (
        "the mapping doors are NOT narrowed — this divergence is today's behaviour, recorded "
        "so LD-312 can see it rather than discover it")
    assert base_hierarchy._field_property(dict_door(self_duplex_link)) == (
        self_duplex_link["property"])


def test_hierarchy_field_property_answers_an_EMPTY_MAPPING_for_a_property_less_field():
    """``None`` in, ``{}`` out — so ``.get("table_id")`` at both call sites stays safe."""
    from larkdocio.base.cells import FieldSpec

    assert base_hierarchy._field_property(
        FieldSpec(field_name="Created", type=1001, ui_type="CreatedTime",
                  property=None, field_id="fldAuto0001")) == {}


@pytest.mark.parametrize("specimen", ["self_single_link", "self_duplex_link"])
@pytest.mark.parametrize("owning_table", ["self", "other", "unknown"])
def test_hierarchy_config_is_IDENTICAL_THROUGH_ALL_THREE_DOORS(specimen, owning_table,
                                                               request):
    """**The net.** One self-link, three doors, one whole ``HierarchyConfig`` — equal.

    Every part of the answer is compared, because the parts are what the reader is *for*: the
    wire body, whether the field list was actually checked, the self-referencing verdict, and
    the uncaptured-shape disclosure. The ``owning_table`` axis drives all three verdicts the
    reader can reach — the link points at its own table, at another table (the disclosure
    path), or the caller did not say (``None``, which claims nothing).
    """
    payload = request.getfixturevalue(specimen)
    table_id = {"self": payload["property"]["table_id"],
                "other": "tblSOMEOTHERTABLE",
                "unknown": None}[owning_table]
    field_id = payload["field_id"]

    answers = [base_hierarchy.hierarchy_config(field_id, fields=[door(payload)],
                                               table_id=table_id)
               for door in (typed_door, bridged_door, dict_door)]
    typed, bridged, plain = answers

    for other, label in ((bridged, "bridged"), (plain, "dict")):
        assert dict(typed) == dict(other), f"the wire body diverged on the {label} door"
        assert typed.to_dict() == other.to_dict(), f"the PATCH body diverged on the {label} door"
        assert typed.checked == other.checked, f"`checked` diverged on the {label} door"
        assert typed.self_referencing == other.self_referencing, (
            f"the self-referencing verdict diverged on the {label} door")
        assert typed.uncaptured_shape == other.uncaptured_shape, (
            f"the uncaptured-shape disclosure diverged on the {label} door")

    assert typed.checked is True
    assert typed.self_referencing == {"self": True, "other": False, "unknown": None}[
        owning_table]
    assert (typed.uncaptured_shape is not None) is (owning_table == "other"), (
        "only a link pointing at ANOTHER table is disclosed as an uncaptured shape")


# =========================================================================== #
# READER 3 — `base/table.py::_property_dict` (the JSON.marshal round trip)      #
# =========================================================================== #

def test_table_property_dict_IS_THE_SDK_SERIALIZER_and_not_a_key_list(duplex_link,
                                                                     self_duplex_link):
    """``table``'s technique is the odd one out and is characterized **as it is**.

    It names no keys at all: it hands the typed property to ``JSON.marshal`` — the SDK's own
    serializer, the same one the client's responses are deserialized with — and decodes the
    result. So its output is *defined* by the serializer, and that identity is the pin. This is
    § Don't-touch 5 of the audit: the round trip is characterized here precisely so LD-312 can
    prove it left ``table.py`` alone.
    """
    for payload in (duplex_link, self_duplex_link):
        prop = typed_door(payload).property
        assert base_table._property_dict(prop) == json.loads(JSON.marshal(prop))


def test_table_property_dict_passes_a_MAPPING_THROUGH_BY_IDENTITY(live_link):
    """A dict in is the *same* dict out — not a copy, not a normalization."""
    prop = live_link["property"]
    assert base_table._property_dict(prop) is prop


def test_table_property_dict_is_NONE_IN_NONE_OUT_never_an_empty_dict():
    """``property: null`` is what the auto fields (1001 / 1002) read back and the date
    renderer keys its documented default formatter off exactly that, so collapsing it to
    ``{}`` would erase a distinction the render depends on."""
    assert base_table._property_dict(None) is None
    assert base_table.field_spec({"field_name": "Created", "type": 1001,
                                  "ui_type": "CreatedTime",
                                  "property": None}).property is None


def test_table_field_spec_is_IDENTICAL_through_the_TYPED_and_DICT_doors(live_link,
                                                                       self_single_link):
    """**The net.** Whole ``FieldSpec`` equality for a property the SDK's model declares fully.

    Every key of these two payloads' ``property`` is declared by ``AppTableFieldProperty``, so
    the serializer round trip reproduces the wire dict exactly and the two doors agree on the
    entire record — name, storage type, ui type, property, id and primary flag.
    """
    for payload in (live_link, self_single_link):
        assert bridged_door(payload) == dict_door(payload)
        assert bridged_door(payload).property == payload["property"]


def test_table_the_UNDECLARED_KEY_DROP_is_pinned_AS_IT_IS_and_happens_BEFORE_the_walk(
        duplex_link):
    """The one place the doors genuinely disagree — pinned as a **carve-out**, not repaired.

    ``BASE.md`` register row 12 records that the pinned SDK's property model silently drops
    every key it does not declare, ``back_field_id`` among them, and
    ``tests/test_base_referential.py`` already pins that drop from the referential side. The
    point this test adds is **where** the key is lost: at ``JSON.unmarshal``, in the SDK's own
    model, *before* ``_property_dict`` is ever called — proven by the fact that
    ``_property_dict`` faithfully reproduces the serializer's view of the object it was handed.
    So it is not a defect in the walk, and it is **not** LD-312's to fix: no shared primitive
    can recover a key the deserializer already discarded.
    """
    assert "back_field_id" in duplex_link["property"], (
        "the specimen no longer carries back_field_id — the drop this pins cannot be seen")
    assert dict_door(duplex_link).property["back_field_id"] == "fldrYKsT0L"

    typed_prop = typed_door(duplex_link).property
    assert not hasattr(typed_prop, "back_field_id"), (
        "the SDK's property model started declaring back_field_id — row 12's finding has "
        "changed and the surfaces that cite it must change with it")
    assert "back_field_id" not in base_table._property_dict(typed_prop)
    assert base_table._property_dict(typed_prop) == json.loads(JSON.marshal(typed_prop)), (
        "the loss is the serializer's, faithfully relayed — never the walk's own")
    assert bridged_door(duplex_link) != dict_door(duplex_link), (
        "this inequality is TODAY'S BEHAVIOUR for an undeclared key; LD-312 may not close it")


def test_table_the_NULL_VALUED_KEY_OMISSION_is_pinned_AS_IT_IS(explicitly_nulled_link):
    """The second asymmetry ``_raw_fields``' docstring names: the serializer **omits** a
    null-valued key, so the bridged door loses *"the key was `null`"* vs *"the key was
    absent"*, while the dict door keeps it. Recorded rather than discovered later — and note
    that the referential reader is unharmed by it (its own test above), because that reading
    treats absent and ``None`` as one answer.
    """
    typed_prop = typed_door(explicitly_nulled_link).property
    assert typed_prop.table_name is None
    assert "table_name" not in base_table._property_dict(typed_prop)
    assert dict_door(explicitly_nulled_link).property["table_name"] is None
