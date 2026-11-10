"""The two loud negatives are authored ONCE and quoted verbatim wherever they appear
(group (b)/M3), and parsing claims nothing about reachability (AC3).
"""
import pathlib

import pytest

import larkdocio.sheets as sheets
from larkdocio import capabilities, guide
from larkdocio.common.url import (
    DOCX_BLOCK_ANCHOR_MEASUREMENT,
    DOCX_SECTION_ANCHOR_UI_ONLY,
    SHEETS_CELL_LINK_UI_ONLY,
)

REPO = pathlib.Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# AC4 — authored once, quoted verbatim, loud where it must be loud              #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_the_range_toast_is_quoted_verbatim_in_the_cell_negative():
    assert '"The cell was deleted"' in SHEETS_CELL_LINK_UI_ONLY
    assert "perfectly intact" in SHEETS_CELL_LINK_UI_ONLY


@pytest.mark.conformance
def test_both_negatives_disclaim_a_permissions_cause_in_the_exact_words():
    phrase = ("the data does not exist in the API at all, so no grant would change "
              "either answer")
    assert phrase in DOCX_SECTION_ANCHOR_UI_ONLY
    assert phrase in SHEETS_CELL_LINK_UI_ONLY


@pytest.mark.conformance
def test_docx_negative_points_at_emit_block_ids_as_the_in_band_alternative():
    assert "emit_block_ids" in DOCX_SECTION_ANCHOR_UI_ONLY


@pytest.mark.conformance
def test_the_cell_negative_is_reexported_on_the_sheets_facade():
    assert sheets.SHEETS_CELL_LINK_UI_ONLY is SHEETS_CELL_LINK_UI_ONLY
    assert "SHEETS_CELL_LINK_UI_ONLY" in sheets.__all__


def _caps_note(surface):
    return capabilities(full=True)["surfaces"][surface]["credentials"]["note"]


@pytest.mark.parametrize(
    "where, text_fn, constant",
    [
        ("guide(full=True)", lambda: guide(full=True), DOCX_SECTION_ANCHOR_UI_ONLY),
        ("guide(full=True)", lambda: guide(full=True), SHEETS_CELL_LINK_UI_ONLY),
        ("capabilities docx-read", lambda: _caps_note("docx-read"),
         DOCX_SECTION_ANCHOR_UI_ONLY),
        ("capabilities sheets-read", lambda: _caps_note("sheets-read"),
         SHEETS_CELL_LINK_UI_ONLY),
        ("SHEETS.md", lambda: (REPO / "SHEETS.md").read_text(encoding="utf-8"),
         SHEETS_CELL_LINK_UI_ONLY),
        ("BLOCKS.md", lambda: (REPO / "BLOCKS.md").read_text(encoding="utf-8"),
         DOCX_SECTION_ANCHOR_UI_ONLY),
        # The POSITIVE docx claim rides the same rail (LD-379): a capability claim owes its
        # enumeration exactly as a negative one does, so its measurement paragraph is
        # authored once and quoted at the same three landing sites.
        ("guide(full=True)", lambda: guide(full=True), DOCX_BLOCK_ANCHOR_MEASUREMENT),
        ("capabilities docx-read", lambda: _caps_note("docx-read"),
         DOCX_BLOCK_ANCHOR_MEASUREMENT),
        ("BLOCKS.md", lambda: (REPO / "BLOCKS.md").read_text(encoding="utf-8"),
         DOCX_BLOCK_ANCHOR_MEASUREMENT),
    ],
)
@pytest.mark.conformance
def test_the_constant_is_quoted_verbatim_at_each_landing_site(where, text_fn, constant):
    assert constant in text_fn(), f"{where} does not quote the negative verbatim"


def test_each_negative_has_exactly_one_string_literal_authoring_site():
    """The paraphrase-forbidding half: the sentence's closing clause exists as a source
    string literal in exactly ONE module (common/url.py). Everywhere else is a reference or
    a quotation of that one object — never a second hand-authored copy that could drift."""
    src = REPO / "src" / "larkdocio"
    for tail in ("a share URL is not available.", "but cell-level ones are not."):
        authoring = sorted(
            p.relative_to(REPO).as_posix()
            for p in src.rglob("*.py")
            if tail in p.read_text(encoding="utf-8")
        )
        assert authoring == ["src/larkdocio/common/url.py"], (
            f"expected exactly one authoring site for {tail!r}, got {authoring}"
        )


# --------------------------------------------------------------------------- #
# AC3 — parsing claims nothing about reachability: no fetch path consumes the   #
# parsed anchor types                                                           #
# --------------------------------------------------------------------------- #

def test_no_source_module_feeds_a_parsed_anchor_into_a_fetch():
    """A grep proof: the fetch-forbidden anchor type names appear only in their own
    authoring module, so nothing turns a parsed address into a call."""
    src = REPO / "src" / "larkdocio"
    offenders = []
    for p in src.rglob("*.py"):
        if p.parent.name == "common" and p.name == "url.py":
            continue
        text = p.read_text(encoding="utf-8")
        for typ in ("DocAnchor", "RecordAnchor"):
            if typ in text:
                offenders.append((p.relative_to(REPO).as_posix(), typ))
    assert offenders == [], f"a parsed anchor type is consumed by: {offenders}"
