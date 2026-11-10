"""LD-446 — an in-cell image stops being a blank cell with no disclosure.

The measured failure (LD-435, 2026-08-12, **one tenant, one day**,
``tenant_access_token`` on the WRITE pair, ``larksuite.com``, **one 88-byte PNG**, on
**one** harness-created-and-trashed workbook): a workbook holding an in-cell image at
``B2`` read back through this library as a table of empty cells. Root cause: an
``embed-image`` segment carries ``text: ""`` and fell through to *"Unknown segment type
— surface its text"* (``sheets/render.py`` / ``sheets/cell_model.py``).

The payload fixture is the spike's own capture — ``tests/captures/sheets-media-spike/captures/203-``
— **deserialized, never hand-mocked** (PROJECT.md § *API-drift is an expected hazard*).

**Tier (conformance-tier.md § A.4).** The one test that pins **measured external truth**
— *Lark returns an in-cell image as a value of this shape* — carries
``pytest.mark.conformance``. Everything else here pins **this library's** rendering
choice and is ordinary regression, unmarked.

**Scope of the evidence, and it is narrow.** One tenant, one day, one PNG, one workbook,
``tenant_access_token``; a ``user_access_token`` is **unmeasured**; media kinds other than
PNG (video, audio, pdf, gif, svg) are **unmeasured**; multi-cell and merged-cell ranges are
**unmeasured**; whether the picture survives an xlsx export (the L2 leg) is **unmeasured**;
whether a human *sees* a picture is **unmeasurable by API**.
"""
import json
import re
from pathlib import Path

import pytest

from larkdocio.model import ImageNode, MarkdownRenderer
from larkdocio.sheets.cell_model import EmbedImage, TypedCell, parse_segments
from larkdocio.sheets.render import render_cell
import private_tree  # noqa: E402  (LD-685)

_CAPTURE = (
    Path(__file__).resolve().parent.parent
    / "tests" / "captures" / "sheets-media-spike" / "captures"
    / "203-b2-the-verdict-fresh-values-read-back-of-the-in-cell-image-target.json"
)


def _capture_cell():
    """The B2 cell value exactly as the values API returned it (capture ``203-``)."""
    payload = json.loads(_CAPTURE.read_text(encoding="utf-8"))
    return payload["response"]["data"]["valueRange"]["values"][0][0]


# --------------------------------------------------------------------------- #
# The wire shape — measured external truth (CONFORMANCE)                       #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_in_cell_image_wire_shape_is_an_embed_image_value():
    """Lark returns a picture-in-a-cell as a ``embed-image`` dict carrying a
    ``fileToken`` + geometry, whose ``text`` is the **empty string** — which is
    exactly why the catch-all text branch made it invisible."""
    cell = _capture_cell()
    assert cell["type"] == "embed-image"
    assert cell["fileToken"] == "Example01e5441c8fb74fe6adf8"
    assert cell["width"] == 24 and cell["height"] == 24
    assert cell["text"] == ""
    # The link is on an INTERNAL-API host and carries no signature parameter; whether
    # it resolves for a browser, a collaborator, or at all, is UNMEASURED (AC5).
    assert cell["link"].startswith("internal-api-space-sg.larksuite.com/")


# --------------------------------------------------------------------------- #
# AC1 — the typed segment                                                      #
# --------------------------------------------------------------------------- #

def test_embed_image_parses_to_a_typed_segment_not_a_text_run():
    (seg,) = parse_segments(_capture_cell())
    assert isinstance(seg, EmbedImage)
    assert seg.file_token == "Example01e5441c8fb74fe6adf8"
    assert seg.width == 24 and seg.height == 24
    assert seg.text == ""


def test_embed_image_link_is_captured_on_the_model_labelled_unmeasured():
    """AC5 — the raw ``link`` is kept as structure (the model is the differ's source
    of truth) but is never a rendered URL; see the render test below."""
    (seg,) = parse_segments(_capture_cell())
    assert seg.link and seg.link.startswith("internal-api-space-sg.larksuite.com/")


def test_embed_image_segment_round_trips_through_json():
    cell = TypedCell.from_values(display=_capture_cell())
    again = TypedCell.from_dict(json.loads(json.dumps(cell.to_dict())))
    assert again.segments == cell.segments


def test_unknown_segment_dict_still_falls_through_to_its_text():
    """supersession.md § A.1 — the fallback is TRANSFORMED, never deleted: a
    genuinely unknown segment type still surfaces its text rather than raising."""
    (seg,) = parse_segments({"type": "some-future-thing", "text": "still here"})
    assert not isinstance(seg, EmbedImage)
    assert seg.text == "still here"


# --------------------------------------------------------------------------- #
# AC2 — the Markdown form, aligned with the docx image dialect                 #
# --------------------------------------------------------------------------- #

def test_in_cell_image_renders_visibly_instead_of_an_empty_cell():
    assert render_cell(_capture_cell()) == "![](Example01e5441c8fb74fe6adf8)"


def test_the_form_is_the_DOCX_image_dialect_character_for_character():
    """A docx image and a sheet image must read alike — so the sheet cell is rendered
    by the **same serializer** that emits a docx ``ImageNode``, not by a second
    hand-rolled spelling. The only deviation is the trailing newline, which a docx
    block carries and a table cell cannot (the table assembly turns ``\\n`` into
    ``<br>``)."""
    cell = _capture_cell()
    docx_form = MarkdownRenderer().render(
        ImageNode(token=cell["fileToken"], caption=cell["text"])
    )
    assert docx_form.endswith("\n")
    assert render_cell(cell) == docx_form.rstrip("\n")


def test_a_caption_bearing_in_cell_image_uses_the_caption_as_the_alt_text():
    value = dict(_capture_cell(), text="a diagram")
    assert render_cell(value) == "![a diagram](Example01e5441c8fb74fe6adf8)"


def test_the_unmeasured_link_is_NEVER_emitted_as_a_working_url():
    """AC5 — the measured retrieval path is ``medias/{fileToken}/download``; the
    internal-api ``link`` ships as structure only."""
    out = render_cell(_capture_cell())
    assert "internal-api" not in out and "http" not in out


def test_a_tokenless_embed_image_emits_the_visible_missing_token_marker():
    """No silent drop, ever — the docx ``[Image: missing token]`` precedent."""
    out = render_cell({"type": "embed-image", "text": "", "width": 24, "height": 24})
    assert out == "[Image: missing token]"


def test_an_embed_image_inside_a_rich_segment_list_renders_the_same():
    cell = _capture_cell()
    assert render_cell([cell]) == "![](Example01e5441c8fb74fe6adf8)"


# --------------------------------------------------------------------------- #
# AC4 / AC6 — determinism, and no new endpoint                                 #
# --------------------------------------------------------------------------- #

def test_two_parses_of_the_same_payload_are_byte_identical():
    cell = _capture_cell()
    assert render_cell(cell) == render_cell(_capture_cell())
    assert parse_segments(cell) == parse_segments(_capture_cell())


def test_the_read_surfaces_the_token_it_was_GIVEN_and_fetches_nothing():
    """AC6 — the ``fileToken`` is surfaced from a value the values read **already
    returned**: it reaches the Markdown character-identical, unresolved, and neither
    module can reach an endpoint at all (no transport import anywhere in either import
    graph). No ``medias/download``, no metadata call, no byte fetch — so
    ``PERMISSIONS.md`` does not move for this change, and its silence is a fact rather
    than an omission."""
    import ast

    import larkdocio.sheets.cell_model as cell_model_mod
    import larkdocio.sheets.render as render_mod

    cell = _capture_cell()
    assert cell["fileToken"] in render_cell(cell)

    forbidden = {"http", "httpx", "requests", "urllib", "urllib3", "socket",
                 "lark_oapi", "larkdocio.common.transport", "larkdocio.sheets.client"}
    for mod in (render_mod, cell_model_mod):
        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        assert not (imported & forbidden), f"{mod.__name__} imports {imported & forbidden}"


# --------------------------------------------------------------------------- #
# AC15 — the standing ruling in requirements/DECISIONS.md                      #
# --------------------------------------------------------------------------- #

_DECISIONS_MD = Path(__file__).resolve().parent.parent / "requirements" / "DECISIONS.md"

#: The register files rulings **by theme, not by number**, and its own rule is that the
#: ``D-NN`` is READ AT LANDING (this branch was minted when D-75 was the highest and lands
#: after several siblings). So this guard finds the ruling by its CITATION, never by a
#: hard-coded number — a renumbering at merge time must not redden it, while a missing or
#: duplicated ruling must. Uniqueness/well-formedness of the ids themselves is LD-413's
#: guard (``tests/test_decisions_register_guard.py``); this one only asserts LD-446's
#: entry exists, is a real ``### D-NN`` section, and states both halves of the ruling.
_D_HEADING = re.compile(r"^### D-(\d{2,}) — (.*)$", re.MULTILINE)


def _decisions_sections():
    """``[(id, title, body), ...]`` for every ``### D-NN`` section of the register."""
    text = _DECISIONS_MD.read_text(encoding="utf-8")
    marks = list(_D_HEADING.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((int(m.group(1)), m.group(2), text[m.end():end]))
    return out


def _the_ld446_ruling():
    hits = [s for s in _decisions_sections() if "LD-446" in s[2] or "LD-446" in s[1]]
    assert len(hits) == 1, (
        "expected exactly ONE requirements/DECISIONS.md ruling citing LD-446, found "
        f"{len(hits)}: {[h[0] for h in hits]}"
    )
    return hits[0]


@private_tree.register
def test_decisions_md_carries_the_LD446_ruling():
    id_, title, _body = _the_ld446_ruling()
    assert id_ >= 78, f"D-{id_:02d} is below the numbers already landed on develop"
    assert title.strip(), "the ruling's heading carries no title"


@private_tree.register
def test_the_LD446_ruling_states_BOTH_halves_and_the_consent():
    """The AC's own wording: an ``embed-image`` cell is read as a **typed segment** and
    rendered in the reader's **own image dialect**; a **float** image is **invisible** to a
    values read and its absence is **disclosed** rather than implied. The consented
    output change is named too — the ruling is the register's memory of *why* a reader
    output moved."""
    _id, title, body = _the_ld446_ruling()
    whole = f"{title}\n{body}".lower()
    for needle in ("embed-image", "typed", "dialect", "float", "disclos", "consent"):
        assert needle in whole, f"the LD-446 ruling never says {needle!r}"
    assert "docx" in whole or "document image" in whole, (
        "the ruling must name the dialect it reuses (the docx image form)"
    )
