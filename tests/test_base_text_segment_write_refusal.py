"""LD-416 — the labeled clickable link in a Base **Text** cell: a MEASURED refusal.

A consumer wanted the column where the label *is* the link, met this library's local refusal
(*"a segment array is the READ shape; pass the string itself"*) and reasonably read it as a
library policy — the platform plainly stores mixed segment arrays, because Lark's own
auto-linkifier puts them there and the reader has walked them since the cell registry shipped.
Nobody had ever asked the **server** whether a typed segment array is a legal Text *write*: the
refusal fires before anything reaches the wire, so the question had never been put.

**It has now.** ``tests/captures/base-study/captures/ld416-01-text-url-segment-write.json`` — live, against
a disposable Base the probe created and deleted — sent **fourteen** segment spellings to **both**
record-write routes (``POST …/records`` and ``PUT …/records/{rid}``): url-only, mixed
text/url/text, the consumer's exact example, the reverse order, text-only, an empty array, and
five malformed variants. Lark answered **1254060 TextFieldConvFail** to every one of them, on
both routes, in a run whose bare-string control answered ``code:0`` on both and read back as a
segment array. So the conclusion narrows in the opposite direction from the one the issue was
opened hoping for, and the library's refusal is now the server's refusal *reported*, not a
policy of ours.

**Supersession, not rewrite (D-24).** The original reason — unwrapping a read-back array would
be a guess about which member carried the value — is untouched and still decides the
paste-a-read-back-array case. What is added is a measurement, and it is scoped: **(1, "Text")
only**, on the **two record-write routes only**. ``(13, "Phone")`` and ``(1, "Barcode")`` share
the encoder and are deliberately left speaking exactly the words they spoke before (D-59: a
label covers the route — and the pair — it was observed on).

Marked ``conformance`` where the case pins the PRODUCT (what Lark does, what the library
therefore refuses, the scope fence, the enumerated evidence a consumer reads). The cases that
pin our own wording or docstring are deliberately left unmarked.
"""
import json
import socket

import pytest
from base_captures import CAPTURES, capture
from guard_kit import REPO_ROOT

from larkdocio.base import shape_docs as sd
from larkdocio.base import write_cells
from larkdocio.base.cells import FieldSpec
from larkdocio.permissions import region_of

CAPTURE = "ld416-01-text-url-segment-write.json"

#: The message ``(13, "Phone")`` and ``(1, "Barcode")`` spoke BEFORE this change, verbatim. The
#: fence is only a fence if it is pinned as a literal: a shared encoder makes "and one more
#: pair came along" the easiest mistake in the file.
FENCE_MESSAGE = ("the field 'F' ({t} / {u}) is written as a plain string. a segment array is "
                 "the READ shape; pass the string itself.")

#: The reason the refusal has always given, preserved verbatim (D-24).
PRESERVED_REASON = ("unwrapping one would be a guess about which of its members carried the "
                    "value")


def field(type_, ui_type, name="F"):
    return FieldSpec(field_name=name, type=type_, ui_type=ui_type)


def _probe():
    return capture(CAPTURE)


def _arms(route_key):
    """Every arm of one route EXCEPT the bare-string control."""
    return [row for row in _probe()[route_key] if not row["form"].startswith("CONTROL")]


def _control(route_key):
    return next(row for row in _probe()[route_key] if row["form"].startswith("CONTROL"))


@pytest.fixture
def no_transport(monkeypatch):
    """A refusal that opened a socket would EXPLODE — the same spy the encoder suite uses."""
    def forbidden(*args, **kwargs):  # pragma: no cover - reaching it IS the failure
        raise AssertionError("a LOCAL refusal opened a socket")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


# =========================================================================== #
# AC1-AC3 / AC5 — what the SERVER said, read out of the capture on disk        #
# =========================================================================== #

@pytest.mark.conformance
def test_ld416_lark_REFUSED_every_probed_segment_shape_on_BOTH_record_write_routes():
    """The product truth this issue exists to establish. Fourteen shapes, two routes, one
    answer — and the answer is the SERVER's, not this library's."""
    for route_key in ("create_route_arms", "update_route_arms"):
        arms = _arms(route_key)
        assert len(arms) == 14, f"{route_key}: the probed shape set changed size"
        for row in arms:
            assert row["code"] == 1254060 and row["msg"] == "TextFieldConvFail", (
                f"{route_key}/{row['form']}: expected 1254060 TextFieldConvFail, "
                f"got {row['code']} {row['msg']!r}")
            assert row["accepted"] is False


@pytest.mark.conformance
def test_ld416_the_bare_string_CONTROL_was_accepted_on_both_routes_and_read_back_as_segments():
    """Without a working control in the same run, a refusal measures the harness. The control
    also re-pins the asymmetry the whole issue turns on: a string goes in, an array comes out."""
    for route_key in ("create_route_arms", "update_route_arms"):
        control = _control(route_key)
        assert control["code"] == 0 and control["accepted"] is True, route_key
        assert control["read_back"] == [{"text": "Example Link", "type": "text"}], (
            f"{route_key}: the control did not read back as a segment array")


@pytest.mark.conformance
def test_ld416_the_probe_names_what_it_did_NOT_try_so_the_evidence_has_a_visible_EDGE():
    """An untried spelling is `unmeasured`, never `cannot` (negative-claims § A.1)."""
    not_tried = _probe()["_not_tried"]
    assert len(not_tried) >= 4
    blob = " ".join(not_tried)
    assert "batch" in blob and "create_table" in blob


# =========================================================================== #
# AC5 — the library refuses the same set, locally, before any transport        #
# =========================================================================== #

@pytest.mark.conformance
@pytest.mark.parametrize("row", _arms("create_route_arms"), ids=lambda r: r["form"])
def test_ld416_the_library_REFUSES_every_shape_the_server_refused(row, no_transport):
    with pytest.raises(write_cells.WriteShapeError):
        write_cells.encode_cell(row["value_sent"], field(1, "Text"))


@pytest.mark.conformance
def test_ld416_the_bare_string_write_is_UNCHANGED_and_still_the_one_accepted_shape():
    assert write_cells.encode_cell("Example Link", field(1, "Text")) == \
        _control("create_route_arms")["create_echo"]


def test_ld416_the_refusal_NAMES_the_measured_server_answer_and_its_route_scope():
    """Not conformance-marked: the *wording* is ours. What is conformance-tier is that the
    refusal happens (above) — this pins that we report the measurement rather than hiding it."""
    with pytest.raises(write_cells.WriteShapeError) as exc:
        write_cells.encode_cell([{"type": "url", "text": "L", "link": "https://e.invalid"}],
                                field(1, "Text", name="Source Link"))
    message = str(exc.value)
    assert "a segment array is the READ shape; pass the string itself." in message
    assert "1254060 TextFieldConvFail" in message
    assert "record-write routes" in message
    assert "UNMEASURED" in message


def test_ld416_the_ORIGINAL_reason_is_preserved_VERBATIM_in_the_encoder_docstring():
    """Supersession: preserve the reason, supersede only the conclusion (D-24). A rewrite that
    dropped the unwrap-guess sentence would erase why the paste-back case still refuses."""
    assert PRESERVED_REASON in " ".join(write_cells._e_plain_string.__doc__.split())


# =========================================================================== #
# AC6 — THE SCOPE FENCE: Phone and Barcode share the encoder and are untouched  #
# =========================================================================== #

@pytest.mark.conformance
@pytest.mark.parametrize("pair", [(13, "Phone"), (1, "Barcode")])
def test_ld416_the_fence_holds_PHONE_and_BARCODE_refuse_EXACTLY_as_they_did_before(pair):
    """The measurement was taken on `1 / Text`. A shared encoder must not let it leak onto two
    pairs nobody probed — that is the route-scoped-evidence rule (D-59) applied to a pair."""
    with pytest.raises(write_cells.WriteShapeError) as exc:
        write_cells.encode_cell([{"type": "url", "text": "L", "link": "https://e.invalid"}],
                                field(*pair))
    message = str(exc.value)
    assert message == FENCE_MESSAGE.format(t=pair[0], u=pair[1])
    assert "1254060" not in message and "TextFieldConvFail" not in message


@pytest.mark.conformance
@pytest.mark.parametrize("pair,value", [((13, "Phone"), "+12025550100"), ((1, "Barcode"), "BC-9")])
def test_ld416_the_fence_holds_the_PLAIN_STRING_write_is_byte_identical(pair, value):
    assert write_cells.encode_cell(value, field(*pair)) == value


@pytest.mark.conformance
def test_ld416_only_TEXT_carries_a_measured_refusal_record():
    assert set(sd.MEASURED_REFUSALS) == {(1, "Text")}


# =========================================================================== #
# AC5.1 / AC8 — the shape docs enumerate the evidence, and the guide shows it   #
# =========================================================================== #

@pytest.mark.conformance
def test_ld416_the_shape_docs_enumerate_EVERY_probed_SHAPE_both_ways():
    """Bidirectional against the capture: a shape the probe sent and the docs omit is evidence
    the reader cannot see; a shape the docs claim and the probe never sent is an invention."""
    authored = {json.dumps(a.value, sort_keys=True, ensure_ascii=False)
                for a in sd.MEASURED_REFUSALS[(1, "Text")].attempts}
    probed = {json.dumps(row["value_sent"], sort_keys=True, ensure_ascii=False)
              for row in _arms("create_route_arms")}
    assert authored == probed, (
        "the enumerated shapes and the probed shapes disagree — "
        f"docs-only={authored - probed}, probe-only={probed - authored}")


@pytest.mark.conformance
def test_ld416_every_enumerated_attempt_carries_LARKS_OWN_answer():
    for attempt in sd.MEASURED_REFUSALS[(1, "Text")].attempts:
        assert attempt.answer == "1254060 TextFieldConvFail"
        assert attempt.note, "an enumerated shape with no note says what, but never why"


@pytest.mark.conformance
def test_ld416_the_measured_refusal_names_its_ROUTES_its_CONTROL_and_what_was_NOT_tried():
    record = sd.MEASURED_REFUSALS[(1, "Text")]
    assert len(record.routes) == 2
    assert "code:0" in record.control
    assert len(record.not_tried) >= 4
    assert record.captures == (CAPTURE,)
    assert (CAPTURES / CAPTURE).exists()


@pytest.mark.conformance
def test_ld416_the_GUIDE_shows_the_enumeration_to_the_CONSUMER():
    region = region_of(_guide_text(), sd.CELL_SHAPE_REGION_BEGIN.replace(" -->", ""),
                       sd.CELL_SHAPE_REGION_END)
    assert region, "the guide carries no generated cell-shape region"
    for attempt in sd.MEASURED_REFUSALS[(1, "Text")].attempts:
        assert json.dumps(attempt.value, ensure_ascii=False) in region, (
            f"the guide does not show the probed shape {attempt.value!r}")
    assert "1254060 TextFieldConvFail" in region
    for fragment in ("dev/", "tests/", "progress/"):
        assert fragment not in region


@pytest.mark.conformance
def test_ld416_the_guide_does_NOT_attach_the_measurement_to_PHONE_or_BARCODE():
    """The fence, in the projection: the enumeration sits under the Text callout and nowhere
    else, so a reader of the Phone row cannot inherit a claim nobody measured for it."""
    region = region_of(_guide_text(), sd.CELL_SHAPE_REGION_BEGIN.replace(" -->", ""),
                       sd.CELL_SHAPE_REGION_END)
    measured_block = region.split("**Text — a string goes in")[-1].split("**Link —")[0]
    assert "1254060 TextFieldConvFail" in measured_block
    for row in region.splitlines():
        if row.startswith("| `13 / Phone`") or row.startswith("| `1 / Barcode`"):
            assert "1254060" not in row, (
                f"the Text measurement leaked onto a pair nobody probed: {row}")


def _guide_text():
    return (REPO_ROOT / "src" / "larkdocio" / "GUIDE.md").read_text(encoding="utf-8")
