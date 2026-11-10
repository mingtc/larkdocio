"""LD-339 — the select option `id` is the cell's anchor, and the update route must carry it.

Measured on a harness-created disposable in `tests/captures/base-study/captures/
ld339-01-select-option-id-remint.json` (7 arms, 6 populated cells each):

* a `PUT …/fields/{f}` whose `property.options` carry every existing option `id` preserves the
  ids **and** all 6 cells — for `SingleSelect` **and** `MultiSelect`;
* the same body with the ids missing re-mints all three ids and orphans **all 6** cells, even
  when name and colour are byte-identical;
* a body with **no** `property` at all wipes the option set to `[]` and orphans all 6 cells.

So the consumer's report is **H2** — library-side. `build_property` built `{name, color}` and
dropped the caller's `id`, so the server received a fresh option list every time. These tests pin
both halves of the fix: the id now goes on the wire, and the two measured-destructive shapes are
refused **locally, before a client exists**.
"""
import json
import re
from pathlib import Path

import pytest

from larkdocio.base import field_authoring as fa
from larkdocio.base import schema_ops_fields as sof
import private_tree  # noqa: E402  (LD-685)

CAPTURES = Path(__file__).resolve().parents[1] / "tests" / "captures" / "base-study" / "captures"
CAPTURE = CAPTURES / "ld339-01-select-option-id-remint.json"
PALETTE = CAPTURES / "ld339-02-select-color-palette.json"

_WITH_IDS = [{"id": "optA", "name": "Todo", "color": 3},
             {"id": "optB", "name": "Doing", "color": 7}]


class _Sink:
    """A stand-in that records nothing but its own construction — used to prove a refusing path
    never reaches a transport at all."""

    constructed = 0

    def __init__(self, *_a, **_k):
        type(self).constructed += 1


# --------------------------------------------------------------------------- #
# The measurement itself — the capture says what the fence is for              #
# --------------------------------------------------------------------------- #

def test_the_capture_says_ids_on_the_wire_preserve_the_cells_and_omitting_them_does_not():
    arms = {row["arm"]: row for row in json.loads(CAPTURE.read_text(encoding="utf-8"))["arms"]}
    for label in ("raw-recolour-with-ids", "raw-identical-with-ids",
                  "multi-raw-recolour-with-ids"):
        arm = arms[label]
        assert arm["ids_preserved"] is True
        assert arm["cells_resolving_after"] == arm["cells_resolving_before"] == 6
    for label in ("ours-recolour", "ours-identical", "multi-ours-recolour"):
        arm = arms[label]
        assert arm["ids_preserved"] is False
        assert arm["cells_resolving_after"] == 0 and arm["cells_resolving_before"] == 6
    # The control the probe expected to be harmless, and which is the worse finding: a
    # name-only update on a SELECT column empties the option set outright.
    control = arms["control-name-only"]
    assert control["options_after"] == [] and control["cells_resolving_after"] == 0


def test_the_option_id_is_stated_once_as_a_measured_constant_and_cites_the_capture():
    assert "ld339-01" in fa.SELECT_OPTION_ID_IS_THE_CELL_ANCHOR
    assert "0 of 6" in fa.SELECT_OPTION_ID_IS_THE_CELL_ANCHOR


# --------------------------------------------------------------------------- #
# NO SILENT DROP — the id is sent, and an unknown per-option key is refused     #
# --------------------------------------------------------------------------- #

def test_build_property_now_SENDS_the_option_id_the_caller_supplied():
    built = fa.build_property("SingleSelect", options=_WITH_IDS)
    assert [option.id for option in built.options] == ["optA", "optB"]
    assert [option.name for option in built.options] == ["Todo", "Doing"]
    assert [option.color for option in built.options] == [3, 7]


def test_an_option_WITHOUT_an_id_still_builds_one_because_a_create_has_no_ids_to_send():
    built = fa.build_property("MultiSelect", options=[{"name": "New", "color": 5}])
    assert built.options[0].id is None and built.options[0].name == "New"


def test_an_unknown_PER_OPTION_key_is_refused_BY_NAME_rather_than_silently_dropped():
    with pytest.raises(fa.UncapturedFieldPropertyError) as excinfo:
        fa.build_property("SingleSelect", options=[{"name": "Todo", "colour": 3}])
    assert "'colour'" in str(excinfo.value)
    assert "id, name, color" in str(excinfo.value)


def test_an_option_with_no_NAME_is_refused_rather_than_KeyError():
    with pytest.raises(fa.UncapturedFieldPropertyError) as excinfo:
        fa.build_property("SingleSelect", options=[{"id": "optA", "color": 3}])
    assert "name" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# THE FENCE — refused at plan time, structurally, before a client exists       #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("ui_type,field_type", [("SingleSelect", 3), ("MultiSelect", 4)])
def test_an_options_carrying_update_with_NO_ids_is_refused(ui_type, field_type):
    with pytest.raises(fa.SelectOptionIdRequiredError) as excinfo:
        sof.update_field("app", "tbl", "fld", "Status", field_type, ui_type=ui_type,
                         properties={"options": [{"name": "Todo", "color": 3}]})
    assert str(excinfo.value) == fa.select_option_refusal("no-ids", ui_type)


@pytest.mark.parametrize("field_type,ui_type", [(3, None), (4, None),
                                                (3, "SingleSelect"), (4, "MultiSelect")])
def test_an_update_that_sends_NO_options_at_all_is_refused_because_it_WIPES_them(field_type,
                                                                                 ui_type):
    with pytest.raises(fa.SelectOptionIdRequiredError) as excinfo:
        sof.update_field("app", "tbl", "fld", "Status", field_type, ui_type=ui_type,
                         properties=None)
    expected = ui_type or ("SingleSelect" if field_type == 3 else "MultiSelect")
    assert str(excinfo.value) == fa.select_option_refusal("no-options", expected)


def test_the_refusal_teaches_the_consequence_the_create_time_rule_and_the_working_route():
    text = fa.select_option_refusal("no-ids", "SingleSelect")
    assert "0 of 6" in text                       # (1) the measured consequence
    assert "create_field" in text                 # (2) the create-time rule
    assert "list_fields" in text                  # (3) what a caller can actually do
    assert "ld339-01" in text                     # the evidence, named


def test_the_refusal_is_LOCAL_no_client_or_transport_is_constructed(monkeypatch):
    import larkdocio.base.schema_client as sc
    monkeypatch.setattr(sc, "BaseSchemaClient", _Sink, raising=False)
    before = _Sink.constructed
    with pytest.raises(fa.SelectOptionIdRequiredError):
        sof.update_field("app", "tbl", "fld", "Status", 3, ui_type="SingleSelect",
                         properties={"options": [{"name": "Todo"}]})
    with pytest.raises(fa.SelectOptionIdRequiredError):
        sof.build_update_request("app", "tbl", "fld", "Status", 3, ui_type="SingleSelect",
                                 properties={"options": [{"name": "Todo"}]})
    assert _Sink.constructed == before


def test_the_SAME_fence_guards_the_direct_client_route_not_only_the_plan():
    """`BaseSchemaClient.update_field` does not go through a plan, and it is the route this
    issue's own probe used to destroy 6 cells. It is fenced in the request builder, so both
    routes refuse identically."""
    with pytest.raises(fa.SelectOptionIdRequiredError):
        sof.build_update_request("app", "tbl", "fld", "Status", 4, ui_type="MultiSelect",
                                 properties={"options": [{"name": "a"}, {"name": "b"}]})


# --------------------------------------------------------------------------- #
# What the fence lets through                                                  #
# --------------------------------------------------------------------------- #

def test_an_options_carrying_update_WITH_every_id_is_planned_and_the_ids_reach_the_wire():
    request = sof.update_field("app", "tbl", "fld", "Status", 3, ui_type="SingleSelect",
                               properties={"options": _WITH_IDS})
    assert request.op == "update_field"
    built = sof.build_update_request("app", "tbl", "fld", "Status", 3, ui_type="SingleSelect",
                                     properties={"options": _WITH_IDS})
    assert [o.id for o in built.request_body.property.options] == ["optA", "optB"]


def test_ADDING_an_option_beside_id_carrying_ones_is_allowed_because_the_existing_ones_survive():
    request = sof.update_field(
        "app", "tbl", "fld", "Status", 3, ui_type="SingleSelect",
        properties={"options": _WITH_IDS + [{"name": "Blocked", "color": 11}]})
    assert len(request.arguments["properties"]["options"]) == 3


def test_the_plan_STOPS_LYING_an_options_carrying_update_no_longer_describes_a_rename():
    renaming = sof.update_field("app", "tbl", "fld", "Title", 1)
    assert renaming.describe == "edit column fld in table tbl to name 'Title'"
    optioned = sof.update_field("app", "tbl", "fld", "Status", 3, ui_type="SingleSelect",
                                properties={"options": _WITH_IDS})
    assert "rename" not in optioned.describe
    assert "2 select options" in optioned.describe and "ids preserved" in optioned.describe


# --------------------------------------------------------------------------- #
# AC3 — the counter-cases, byte-for-byte                                       #
# --------------------------------------------------------------------------- #

def test_AC3i_a_name_only_update_on_a_NON_select_column_is_untouched():
    """LD-319's taught rename of a locale-named primary TEXT column. Unchanged, and it must not
    acquire a read client, a consent token, or a new disclosure."""
    request = sof.update_field("app", "tbl", "fld", "Title", 1, revision=7)
    assert request.describe == "edit column fld in table tbl to name 'Title'"
    assert request.arguments["properties"] == {} and request.traits["read_cost"] == 3
    assert "consent" not in request.traits
    body = sof.build_update_request("app", "tbl", "fld", "Title", 1).request_body
    assert body.field_name == "Title" and body.type == 1 and body.property is None


@pytest.mark.parametrize("ui_type,field_type,properties", [
    ("Currency", 2, {"currency_code": "USD", "formatter": "0.00"}),
    ("DateTime", 5, {"date_formatter": "yyyy/MM/dd"}),
    ("Rating", 2, {"symbol": "star", "formatter": "0", "min": 0, "max": 5}),
])
def test_AC3ii_a_NON_options_property_update_is_untouched(ui_type, field_type, properties):
    request = sof.update_field("app", "tbl", "fld", "C", field_type, ui_type=ui_type,
                               properties=properties)
    assert request.describe == "edit column fld in table tbl to name 'C'"
    body = sof.build_update_request("app", "tbl", "fld", "C", field_type, ui_type=ui_type,
                                    properties=properties).request_body
    assert body.property is not None


def test_AC3iii_an_UNPOPULATED_select_column_is_refused_TOO_and_the_refusal_says_so():
    """Populated-ness is not knowable without a read, and UNKNOWN IS NOT SAFE — so the fence is
    on the request's SHAPE, and an empty column pays the same price. Said out loud."""
    with pytest.raises(fa.SelectOptionIdRequiredError) as excinfo:
        sof.update_field("app", "tbl", "fld", "Status", 3, ui_type="SingleSelect",
                         properties={"options": [{"name": "Todo"}]})
    assert "whether the column holds data" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# AC5 — the palette is MEASURED, and no hue is named                           #
# --------------------------------------------------------------------------- #

def test_the_palette_constant_states_only_what_was_measured():
    """The constant may claim the ints the probe actually SENT and nothing between them. The
    first draft said `0..54`, which reads as a contiguous range and is a promise 34 unsent ints
    wide — the capture is the arbiter, so the assertion is built from it."""
    payload = json.loads(PALETTE.read_text(encoding="utf-8"))
    assert all(row["stored_color"] == row["sent_color"] for row in payload["palette"])
    sent = [row["sent_color"] for row in payload["palette"]]
    assert len(sent) == 21
    accepted = {row["sent_color"] for row in payload["out_of_range"] if row["accepted"]}
    refused = {row["sent_color"] for row in payload["out_of_range"] if not row["accepted"]}
    assert accepted == {54} and refused == {-1, 99, 1000}

    text = fa.SELECT_OPTION_COLOR_INTS
    assert ", ".join(str(value) for value in sent) in text, "the measured spread, enumerated"
    assert "99992402" in text
    assert "NOT PROBED" in text.upper(), "the unmeasured gaps are said to be unmeasured"
    assert "0..54" not in text, "a contiguous range was never measured"


_MEASURED_SPREAD = "0, 1, 2, 3, 4, 5, 8, 11, 14, 17, 20, 22, 24, 28, 33, 36, 40, 43, 46, 49, 53"

#: Every home that carried the `0..54` overclaim. The four that a consumer reads to LEARN the
#: palette must enumerate what was sent; `CHANGELOG.md` summarises it for a reader and is held
#: only to not re-asserting the contiguous range.
_PALETTE_HOMES = ("src/larkdocio/GUIDE.md", "BASE.md", "RELEASE_NOTES.md",
                  "dev/base-study/ld339-colour-palette-card.md")


@private_tree.dev_record
@pytest.mark.parametrize("path", _PALETTE_HOMES + ("CHANGELOG.md",))
def test_NO_SHIPPED_OR_DEV_TEXT_CLAIMS_THE_CONTIGUOUS_RANGE(path):
    """Five homes carried the same overclaim; one guard keeps them honest together."""
    body = (Path(__file__).resolve().parents[1] / path).read_text(encoding="utf-8")
    assert "0..54" not in body, f"{path} still claims a contiguous 0..54 range"
    if path in _PALETTE_HOMES:
        assert _MEASURED_SPREAD in body, f"{path} does not enumerate what was actually sent"


def test_NO_HUE_NAME_IS_INVENTED_anywhere_in_the_shipped_colour_text():
    hues = ("blue", "red", "green", "yellow", "purple", "orange", "pink", "teal", "grey",
            "gray", "cyan", "magenta")
    words = set(re.findall(r"[a-z]+",
                           (fa.SELECT_OPTION_COLOR_INTS
                            + fa.SELECT_OPTION_ID_IS_THE_CELL_ANCHOR).lower()))
    assert not [hue for hue in hues if hue in words]
