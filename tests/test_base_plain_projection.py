"""LD-321 — the PLAIN cell projection: `cell_text()` / `plain_value()`.

A consumer reported that every consumer would write the same short ``cell_text()`` flattener
before using titles as keys. The library already had a segment walker — `cells.render_segments` —
but it renders **Markdown**: the text is escaped and a `url` segment becomes `[text](link)`,
which is the wrong string to key a dict on. So this is a **plain sibling**, not a duplicate,
and these tests hold it to the same evidence bar as the renderer: every payload shape below is
read from a **committed capture** (`tests/captures/base-study/captures/`).
"""
import copy
import json
from pathlib import Path

import pytest

from larkdocio.base import cells
from larkdocio.base import plain as plain_mod
from larkdocio.base.plain import cell_text, plain_value

_REPO = Path(__file__).resolve().parent.parent
_CAPTURES = _REPO / "tests" / "captures" / "base-study" / "captures"

#: Every capture these tests read, named so AC6 is checkable at a glance.
CAPTURES_USED = (
    "06-03-value-read-option-matrix.json",   # text / barcode / select / number / checkbox / url / formula
    "p1-q0-03-per-table.json",               # the Email cell — a type-1 field whose segment is `url`
    "p0-2-05-link-lookup-read-encodings.json",  # link NEVER-SET (`null`) + the person cells
    "p0-2-07-link-deletion-behaviour.json",  # link EMPTIED (`[]`) — the other empty
    "p0-4-04-value-readback.json",           # attachment (WITH url/tmp_url), location, group chat
)


def _capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def _populated_row():
    """The `records/search` row `06-03` calls `populated_record` — the pinned read route."""
    return _capture(
        "06-03-value-read-option-matrix.json"
    )["response"]["data"]["modes"]["plain"]["populated_record"]["fields"]


def _every_captured_fields_body():
    """Every `fields` body in every committed capture — the sweep AC4/AC6 rest on."""
    out = []
    for path in sorted(_CAPTURES.glob("*.json")):
        stack = [json.loads(path.read_text(encoding="utf-8"))]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                body = node.get("fields")
                if isinstance(body, dict):
                    out.append((path.name, body))
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return out


# --------------------------------------------------------------------------- #
# AC6 — the specimens are real and on disk                                     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", CAPTURES_USED)
def test_ac6_every_capture_these_tests_read_exists_on_disk(name):
    assert (_CAPTURES / name).is_file(), name


def test_ac6_the_sweep_really_covers_the_committed_captures():
    bodies = _every_captured_fields_body()
    assert len(bodies) >= 20, len(bodies)


# --------------------------------------------------------------------------- #
# AC1 — the helpers ship, are REACHABLE, and are a PROJECTION                   #
# --------------------------------------------------------------------------- #

def test_ac1_the_helpers_are_reachable_beside_field_spec_without_a_dir():
    """The consumer names `field_spec` as the neighbour; `larkdocio.base` is the import
    path they would guess, and both helpers are in its `__all__` — unlike
    `render_segments`, which is `dir()`-only to this day."""
    import larkdocio.base as base

    assert base.cell_text is cell_text
    assert base.plain_value is plain_value
    assert "cell_text" in base.__all__ and "plain_value" in base.__all__
    assert "field_spec" in base.__all__
    assert set(plain_mod.__all__) >= {"cell_text", "plain_value"}


def test_ac1_the_consumers_own_example_returns_the_bare_string():
    assert cell_text([{"text": "Ship it", "type": "text"}]) == "Ship it"
    assert plain_value([{"text": "Ship it", "type": "text"}]) == "Ship it"


def test_ac1_the_plain_projection_is_UNESCAPED_where_the_markdown_one_escapes():
    """The whole reason this is a sibling and not a duplicate: a Markdown-escaped string
    is the wrong dict key."""
    segs = [{"text": "a_b *c* [d]", "type": "text"}]
    assert cells.render_segments(segs) == "a_b \\*c\\* [d]"
    assert cell_text(segs) == "a_b *c* [d]"


def test_ac1_a_url_segment_is_NOT_link_decorated_in_the_plain_projection():
    segs = [{"link": "mailto:ok@example.invalid", "text": "ok@example.invalid", "type": "url"}]
    assert cells.render_segments(segs) == "[ok@example.invalid](mailto:ok@example.invalid)"
    assert cell_text(segs) == "ok@example.invalid"


def test_ac1_the_helpers_MUTATE_NOTHING():
    """The `scrub_attachment_cell` spirit: a projection returns a new value and leaves the
    input `==` to the copy taken before the call."""
    for _name, body in _every_captured_fields_body():
        before = copy.deepcopy(body)
        for value in body.values():
            cell_text(value)
            plain_value(value)
        assert body == before


def test_ac1_the_returned_mapping_is_not_the_input_mapping():
    cell = _capture("p0-4-04-value-readback.json")[
        "response"]["data"]["items"][0]["fields"]["Attach"]
    out = plain_value(cell)
    assert out[0] is not cell[0]


# --------------------------------------------------------------------------- #
# AC2 — placement, and NEVER a second by-name walk                              #
# --------------------------------------------------------------------------- #

def test_ac2_the_plain_module_walks_through_the_LD312_primitive():
    source = (_REPO / "src" / "larkdocio" / "base" / "plain.py").read_text(encoding="utf-8")
    assert "from larkdocio.base._typed import" in source, (
        "door tolerance goes through the shared walk, never a fork of it")
    assert "getattr(" not in source, (
        "a getattr fallback here IS the second by-name walk `_typed` exists to prevent")


def test_ac2_typed_py_still_holds_no_field_name_list():
    typed = (_REPO / "src" / "larkdocio" / "base" / "_typed.py").read_text(encoding="utf-8")
    assert "This module holds no list of field names, and it must not gain one." in typed
    assert typed.count("def ") == 3, "the shared walk gained or lost a function"


@pytest.mark.parametrize("module,key_list", [
    ("computed.py", '_by_name(prop, ("filter_info", "formula_expression", "formatter"))'),
    ("loss_preview.py", '_by_name(prop, ("table_id", "table_name", "back_field_id", '
                        '"back_field_name",'),
    ("referential.py", '_by_name(prop, ("table_id", "table_name"))'),
    ("hierarchy.py", '_by_name(prop, ("table_id",))'),
])
def test_ac2_the_four_LD312_walkers_still_own_their_own_key_lists(module, key_list):
    """LD-312's ruling: each module's key list stays exactly where it is. A helper that
    widened one of them would be answering a question about what this library *reports*."""
    source = (_REPO / "src" / "larkdocio" / "base" / module).read_text(encoding="utf-8")
    assert key_list in source


# --------------------------------------------------------------------------- #
# AC3 — every door it claims, answering identically                             #
# --------------------------------------------------------------------------- #

class _TypedSegment:
    """The attribute door: a segment that is an object rather than a mapping — the shape
    `_typed._step` exists for (`_typed.py:39-55`)."""

    def __init__(self, text, type):
        self.text = text
        self.type = type


def _doors_for_the_text_cell():
    from lark_oapi.api.bitable.v1 import SearchAppTableRecordResponse
    from lark_oapi.core.json import JSON

    wire = _populated_row()["Text"]
    sdk = JSON.unmarshal(
        json.dumps({"code": 0, "data": {"items": [{"fields": {"Text": wire},
                                                   "record_id": "rec1"}]}}),
        SearchAppTableRecordResponse,
    ).data.items[0].fields["Text"]
    typed = [_TypedSegment(text=s["text"], type=s["type"]) for s in wire]
    return {"wire dict": wire, "SDK-deserialized": sdk, "attribute door": typed}


@pytest.mark.parametrize("door", sorted(_doors_for_the_text_cell()))
def test_ac3_every_accepted_door_answers_identically(door):
    value = _doors_for_the_text_cell()[door]
    assert cell_text(value) == "THE ROW", door
    assert plain_value(value) == "THE ROW", door


def test_ac3_an_unaccepted_shape_degrades_and_never_raises():
    """The stated posture for a door this does not accept: `str()`, never an exception."""
    class _Opaque:
        def __repr__(self):
            return "<opaque>"

    assert cell_text(_Opaque()) == "<opaque>"
    assert plain_value(_Opaque()) == "<opaque>"


def test_ac3_the_docstring_names_the_doors():
    doc = plain_mod.__doc__
    for word in ("wire dict", "attribute", "door"):
        assert word in doc, word


# --------------------------------------------------------------------------- #
# AC4 — per-type behaviour, STATED and tested, family by family                 #
# --------------------------------------------------------------------------- #

def test_ac4_text_segments_join_with_nothing():
    """The server has already aggregated (a LISTCOMBINE Lookup's separators are themselves
    segments) — so the plain join is `""`, exactly as `render_segments` joins."""
    segs = [{"text": "a", "type": "text"}, {"text": "b", "type": "text"}]
    assert cell_text(segs) == "ab"


def test_ac4_email_is_a_type1_cell_whose_segment_is_a_url_and_it_flattens_to_the_label():
    row = _capture("p1-q0-03-per-table.json")[
        "per_table"][0]["records_search"]["response"]["data"]["items"][0]["fields"]["Email"]
    assert row[0]["type"] == "url"            # the capture really is the url-segment shape
    assert cell_text(row) == row[0]["text"]   # the address, plain — not `[addr](mailto:addr)`
    assert "[" not in cell_text(row)


def test_ac4_a_LONE_url_segment_keeps_BOTH_halves_because_nothing_else_carries_the_link():
    """A `Url` cell is a lone url segment, not an array — `06-03`."""
    cell = _populated_row()["Url"]
    assert plain_value(cell) == {"text": "Example", "link": "https://example.invalid/x"}
    assert cell_text(cell) == "Example"


def test_ac4_person_surfaces_the_NAME_and_drops_id_email_and_avatar():
    """D1, the shipped L1 rule quoted at `cells._person_name`: name → en_name → the redacted
    marker, and **never** an id, an email or an avatar URL."""
    cell = _capture("p0-2-05-link-lookup-read-encodings.json")[
        "response"]["data"]["main_rows"][0]["fields"]["ModifiedUser"]
    assert set(cell[0]) >= {"id", "email", "avatar_url", "name"}   # the door really carries them
    assert cell_text(cell) == cell[0]["name"]
    assert plain_value(cell) == [cell[0]["name"]]
    rendered = json.dumps(plain_value(cell))
    assert cell[0]["id"] not in rendered
    assert cell[0]["avatar_url"] not in rendered


def test_ac4_a_person_with_no_name_is_the_redacted_marker_not_an_id():
    assert cell_text([{"id": "ou_x", "email": "e@x.invalid"}]) == cells.PERSON_NAME_UNAVAILABLE


def test_ac4_group_chat_reads_through_the_same_person_rule():
    cell = _capture("p0-4-04-value-readback.json")[
        "response"]["data"]["items"][2]["fields"]["Chat"]
    assert cell_text(cell) == cell[0]["name"]


def test_ac4_link_NULL_and_link_EMPTY_are_kept_apart():
    """`null` = nobody ever wrote a link; `[]` = links were written and their targets were
    deleted. The two empties are different FACTS (`cells.link_state`), and a projection that
    returned `[]` for both would erase one of them."""
    never = _capture("p0-2-05-link-lookup-read-encodings.json")[
        "response"]["data"]["main_rows"][0]["fields"]["SingleLinkOne"]
    assert never == {"link_record_ids": None}
    assert cells.link_state(never) == cells.LINK_NEVER_SET
    assert plain_value(never) is None
    assert cell_text(never) == ""

    emptied = None
    for _name, body in _every_captured_fields_body():
        for value in body.values():
            if isinstance(value, dict) and value.get("link_record_ids") == []:
                emptied = value
    assert emptied is not None, "no captured EMPTIED link cell — the other empty must be real"
    assert cells.link_state(emptied) == cells.LINK_EMPTIED
    assert plain_value(emptied) == ()
    assert cell_text(emptied) == ""
    assert plain_value(emptied) is not plain_value(never)


def test_ac4_a_populated_link_projects_its_record_ids():
    populated = None
    for _name, body in _every_captured_fields_body():
        for value in body.values():
            if isinstance(value, dict) and value.get("link_record_ids"):
                populated = value
    assert populated is not None
    ids = tuple(populated["link_record_ids"])
    assert plain_value(populated) == ids
    assert cell_text(populated) == ", ".join(ids)


def test_ac4_an_attachment_NEVER_LEAKS_A_SIGNED_LINK():
    """The binding one. The `p0-4-04` capture's attachment cell really does carry both
    ephemeral keys, and neither survives the projection — the `scrub_attachment_cell`
    doctrine (`media.py:194-204`), reused rather than re-stated."""
    from larkdocio.base.media import EPHEMERAL_ATTACHMENT_KEYS

    cell = _capture("p0-4-04-value-readback.json")[
        "response"]["data"]["items"][0]["fields"]["Attach"]
    assert set(EPHEMERAL_ATTACHMENT_KEYS) <= set(cell[0]), "the specimen must carry them"
    projected = plain_value(cell)
    assert projected == [{"file_token": cell[0]["file_token"], "name": cell[0]["name"],
                          "size": cell[0]["size"], "type": cell[0]["type"]}]
    assert not set(EPHEMERAL_ATTACHMENT_KEYS) & set(projected[0])
    assert cell_text(cell) == cell[0]["name"]


def test_ac4_NO_EPHEMERAL_KEY_SURVIVES_ANY_CAPTURED_CELL():
    """The sweep, not one specimen: every cell in every committed capture, through both
    helpers, and no ephemeral key and no signed-link substring anywhere in the output."""
    from larkdocio.base.media import EPHEMERAL_ATTACHMENT_KEYS

    for name, body in _every_captured_fields_body():
        for key, value in body.items():
            for out in (plain_value(value), cell_text(value)):
                blob = json.dumps(out, default=str)
                for ephemeral in EPHEMERAL_ATTACHMENT_KEYS:
                    assert f'"{ephemeral}"' not in blob, (name, key, ephemeral)
                assert "batch_get_tmp_download_url" not in blob, (name, key)
                assert "/medias/" not in blob, (name, key)


def test_ac4_select_cells_are_already_option_NAMES():
    row = _populated_row()
    assert plain_value(row["SingleSelect"]) == "Alpha"
    assert cell_text(row["SingleSelect"]) == "Alpha"
    assert plain_value(row["MultiSelect"]) == ["Red", "Green"]
    assert cell_text(row["MultiSelect"]) == "Red, Green"


def test_ac4_scalars_come_back_as_themselves_with_NO_property_formatting():
    row = _populated_row()
    assert plain_value(row["Number"]) == 42.5
    assert plain_value(row["Checkbox"]) is True
    assert cell_text(row["Checkbox"]) == "True"
    assert plain_value(row["DateTime"]) == 1785061011000    # the ms epoch, verbatim
    assert plain_value(row["Phone"]) == "+12025550100"


def test_ac4_a_typed_wrapper_projects_its_inner_value():
    """Formula / Lookup: `{"type": N, "value": […]}` where `N` is the RESULT type."""
    row = _populated_row()
    assert row["Formula"] == {"type": 2, "value": [2]}
    assert plain_value(row["Formula"]) == [2]
    assert cell_text(row["Formula"]) == "2"


def test_ac4_location_projects_its_full_address():
    cell = _capture("p0-4-04-value-readback.json")[
        "response"]["data"]["items"][1]["fields"]["Loc"]
    assert cell_text(cell) == "Central Singapore,Singapore"


def test_ac4_location_the_TWO_helpers_SPLIT_and_the_docstring_says_which_does_what():
    """The QA bounce: the Location bullet promised the `full_address` precedence for BOTH
    helpers, but only `cell_text` honours it — `plain_value` keeps the whole mapping (the
    coordinate pair in `location` has no other survivor in the projection). The behaviour is
    the right one; the sentence was the bug. Both halves are asserted here, so neither can
    drift unevidenced again."""
    cell = _capture("p0-4-04-value-readback.json")[
        "response"]["data"]["items"][1]["fields"]["Loc"]

    # cell_text — the stated precedence, and it really is a fallback chain
    assert cell_text(cell) == cell["full_address"]
    # the capture's own `name` is empty, so dropping `full_address` falls PAST it to `location`
    assert cell["name"] == ""
    assert cell_text({k: v for k, v in cell.items() if k != "full_address"}) == cell["location"]
    # the middle rung, with the capture's keys and a name that is actually set
    assert cell_text({**cell, "full_address": "", "name": "Example Place"}) == "Example Place"
    assert cell_text({"location": "103.8198,1.3521"}) == "103.8198,1.3521"

    # plain_value — the whole mapping, a NEW dict, nothing dropped and nothing added
    out = plain_value(cell)
    assert out == dict(cell) and out is not cell
    assert "location" in out and "," in out["location"]      # the coordinate pair survives

    # ...and the docstring states exactly that split, in the Location bullet itself
    bullet = plain_mod.__doc__.split("* **Location**", 1)[1].split("\n* **", 1)[0]
    assert "cell_text" in bullet and "plain_value" in bullet
    assert "full_address" in bullet and "whole mapping" in bullet


def test_ac3_the_door_claim_is_narrowed_to_the_families_that_really_answer_identically():
    """QA's second finding: the doors sentence was broader than the code. The shared `_step`
    walk covers the SEGMENT families; the mapping families are `Mapping`-gated (every shipped
    read route hands `fields` back as raw dicts), so an attribute-door person is NOT an
    evidenced door and degrades by the standing R13 posture instead."""
    class _AttrPerson:
        id = "ou_x"
        name = "Ada"

        def __repr__(self):
            return "<attr-person>"

    assert cell_text(_AttrPerson()) == "<attr-person>"     # degrades, never raises
    assert plain_value(_AttrPerson()) == "<attr-person>"

    doors = plain_mod.__doc__.split("**The doors it accepts.**", 1)[1].split("\n\n", 1)[0]
    assert "segment" in doors and "Mapping" in doors
    assert "all three answer identically" not in doors     # the over-broad claim is gone


def test_ac4_an_unevidenced_shape_surfaces_something_and_never_raises():
    """R13's standing posture (`cells.py:275-276`) — never raise, never guess."""
    assert cell_text({"weird": 1}) == "{'weird': 1}"
    assert plain_value({"weird": 1}) == {"weird": 1}
    assert cell_text([{"text": 7, "type": "martian"}]) == "7"


def test_ac4_the_docstring_states_each_family_rather_than_leaving_it_to_be_discovered():
    doc = plain_mod.__doc__ + (cell_text.__doc__ or "") + (plain_value.__doc__ or "")
    for word in ("Text", "person", "link", "attachment", "select", "Checkbox",
                 "Formula", "never-set", "signed"):
        assert word in doc, word


# --------------------------------------------------------------------------- #
# AC5 — one dispatch rule, shared: never a second segment walker                 #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("seg,md,plain_out", [
    ({"text": "x", "type": "text"}, "x", "x"),
    ({"text": "lbl", "link": "https://e.invalid/a", "type": "url"},
     "[lbl](https://e.invalid/a)", "lbl"),
    ({"text": "u", "type": "martian"}, "u", "u"),
])
def test_ac5_both_walkers_dispatch_on_the_segments_OWN_type(seg, md, plain_out):
    """R13 (`cells.py:262-265`): on the segment's own `type`, never the field's. Every kind
    `render_segment` handles is asserted on both sides here."""
    assert cells.render_segment(seg) == md
    assert cell_text([seg]) == plain_out


def test_ac5_the_dispatch_INPUTS_are_read_in_ONE_place():
    """Not a second walker: both sides read `(type, text, link)` off a segment through the
    same `cells._segment_parts`."""
    cells_src = (_REPO / "src" / "larkdocio" / "base" / "cells.py").read_text(encoding="utf-8")
    plain_src = (_REPO / "src" / "larkdocio" / "base" / "plain.py").read_text(encoding="utf-8")
    assert "def _segment_parts(" in cells_src
    body = cells_src.split("def render_segment(", 1)[1].split("\ndef ", 1)[0]
    assert "_segment_parts(" in body, "the Markdown walker must read through the shared core"
    assert "_segment_parts" in plain_src, "the plain walker must read through the same core"
    assert 'seg.get("type")' not in plain_src


def test_ac5_the_docstring_states_the_relationship_to_render_segments():
    doc = plain_mod.__doc__
    assert "render_segments" in doc
    assert "Markdown" in doc


def test_ac5_the_markdown_walker_is_byte_identical_over_every_captured_cell():
    """The sibling must not have moved the shipped renderer: every captured cell, rendered."""
    field = cells.FieldSpec(field_name="Text", type=1, ui_type="Text")
    for _name, body in _every_captured_fields_body():
        for value in body.values():
            assert isinstance(cells.render_cell(value, field), str)
    segs = [{"text": "write to ", "type": "text"},
            {"link": "mailto:ok@example.invalid", "text": "ok@example.invalid", "type": "url"}]
    assert cells.render_cell(segs, field) == (
        "write to [ok@example.invalid](mailto:ok@example.invalid)")


# --------------------------------------------------------------------------- #
# AC7 — discoverability is the docstring + the export; the plain projection      #
#       still owns NO section of GUIDE.md of its own                             #
# --------------------------------------------------------------------------- #

def test_ac7_the_plain_projection_still_owns_NO_section_of_the_guide():
    """**Superseded in its conclusion, not in its reason (LD-497).** This guard was written
    as *"`cell_text` appears nowhere in GUIDE.md — LD-319 owns GUIDE.md this round"*: a
    round-scoped fence that stopped two concurrent stories from both authoring guide prose
    about the same surface. The **reason survives** — this module ships its contract in its
    own docstring and its export, and it does not grow a recipe of its own in the guide.

    The **conclusion** is replaced, because a later story earned it: LD-497's consumer asked,
    in as many words, for the guide to say what a Base Markdown read does and does not
    preserve, and the honest version of that sentence has to say that the *plain* projection
    deliberately drops the link. So `cell_text` is named in the guide **exactly once**, inside
    the Base Markdown link-fidelity paragraph, as the contrast — never as a section, a recipe
    or a heading of its own.
    """
    guide = (_REPO / "src" / "larkdocio" / "GUIDE.md").read_text(encoding="utf-8")
    assert guide.count("cell_text") == 1, (
        "the plain projection is named once in the guide, as the contrast inside the Base "
        "Markdown link-fidelity paragraph — a second mention means it has grown a section")
    line = [ln for ln in guide.splitlines() if "cell_text" in ln][0]
    assert not line.startswith("#"), "the plain projection owns no heading in the guide"
    window = guide[guide.index("cell_text") - 2000:guide.index("cell_text") + 400]
    assert "link-lossless" in window and "plain_value" in window
