"""``common.doc_link.docx_block_url`` — the docx twin of ``sheets.tab_url`` (LD-379).

A pure, offline function. The tenant host is an INPUT (it reaches the function on the
document's own URL), never derived from an API domain and never invented.

**The construction table below is the measurement, not an illustration.** Every expected
string is a row a human actually clicked on 2026-08-10 (one tenant, Lark **web** client),
recorded verbatim in ``dev/2026-08-10-docx-anchor-click-sheet.md`` § maintainer CLICK RESULTS; the
block ids come from the probe capture
``dev/docx-anchor-grammar-probe/captures/01-anchor-grammar-candidates.json`` (``arm2.targets``)
and the host from the server's own ``/drive/v1/metas/batch_query`` ``url``. So a change to
what this function builds is a change to a *clicked* string, which is what makes these
conformance-tier.
"""
import inspect
import pathlib

import pytest

import larkdocio.common as common
from larkdocio.common.doc_link import docx_block_url
from larkdocio.common.url import (
    DOCX_BLOCK_ANCHOR_MEASUREMENT,
    DOCX_SECTION_ANCHOR_UI_ONLY,
)

DOC_URL = "https://your-domain.larksuite.com/docx/Example300147d45d30d8297a47"

#: ``(block kind, block_id, the URL that was clicked, what the client did)`` — the six
#: rows of the click sheet's G1 family (rows 1, 4, 7, 10, 13, 16).
CLICKED = [
    ("heading1", "doxlgExampled71529fa60d41c2", f"{DOC_URL}#doxlgExampled71529fa60d41c2",
     "jump"),
    ("heading2", "doxlgExample941dc79279b6fe2", f"{DOC_URL}#doxlgExample941dc79279b6fe2",
     "jump"),
    ("paragraph", "doxlgExample7b6f24face57efe", f"{DOC_URL}#doxlgExample7b6f24face57efe",
     "jump"),
    ("table", "doxlgExample5312a3cfd2715fb", f"{DOC_URL}#doxlgExample5312a3cfd2715fb",
     "move+highlight"),
    ("bullet", "doxlgExample49cf68fda10cd19", f"{DOC_URL}#doxlgExample49cf68fda10cd19",
     "jump"),
    ("code", "doxlgExample6ef28054df67de0", f"{DOC_URL}#doxlgExample6ef28054df67de0",
     "move+highlight"),
]


# --------------------------------------------------------------------------- #
# AC2(a) — the six-kind construction table, every row a clicked string          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kind, block_id, clicked, _behaviour",
                         CLICKED, ids=[row[0] for row in CLICKED])
@pytest.mark.conformance
def test_builds_the_exact_string_that_was_clicked_for_every_measured_block_kind(
    kind, block_id, clicked, _behaviour
):
    assert docx_block_url(DOC_URL, block_id) == clicked


@pytest.mark.conformance
def test_the_tenant_host_comes_from_the_input_url_not_an_api_domain():
    # A different tenant host must be preserved verbatim — proving the host is an input.
    got = docx_block_url("https://your-domain.feishu.cn/docx/TOKEN123", "blk9")
    assert got == "https://your-domain.feishu.cn/docx/TOKEN123#blk9"


@pytest.mark.conformance
def test_a_doc_url_that_already_carries_a_fragment_or_query_is_rebuilt_cleanly():
    got = docx_block_url(f"{DOC_URL}?from=space#share-oldtoken", CLICKED[0][1])
    assert got == CLICKED[0][2]


@pytest.mark.conformance
def test_token_and_block_id_are_carried_unaltered():
    got = docx_block_url("https://h.larksuite.com/docx/Keeps_UnderScores", "Block_Id_9")
    assert got == "https://h.larksuite.com/docx/Keeps_UnderScores#Block_Id_9"


# --------------------------------------------------------------------------- #
# Refusals — the library's existing refusal grammar, never a default            #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("bad", ["", "not-a-url", "https:///docx/tok", "ftp://h/docx/t",
                                 "http://your-domain.larksuite.com/docx/TOK"])
@pytest.mark.conformance
def test_a_missing_hostless_or_non_https_url_is_a_refusal_not_a_default(bad):
    with pytest.raises(ValueError):
        docx_block_url(bad, "blk9")


@pytest.mark.conformance
def test_a_non_docx_url_is_refused():
    with pytest.raises(ValueError):
        docx_block_url("https://your-domain.larksuite.com/sheets/SHEET123", "blk9")


@pytest.mark.conformance
def test_a_missing_block_id_is_a_refusal():
    with pytest.raises(ValueError):
        docx_block_url(DOC_URL, "")


@pytest.mark.conformance
def test_a_WIKI_wrapped_url_is_refused_as_UNMEASURED_rather_than_guessed():
    """The wiki axis was never measured (no space existed to make a disposable node in), so
    the honest answer is a refusal that says so — not a link built on an untested grammar."""
    with pytest.raises(ValueError) as excinfo:
        docx_block_url("https://your-domain.larksuite.com/wiki/NODE123", "blk9")
    message = str(excinfo.value).lower()
    assert "wiki" in message and "unmeasured" in message


# --------------------------------------------------------------------------- #
# AC4 — the loud negatives: the share-token form is NEVER minted                #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_the_share_token_grammar_is_NEVER_MINTED_and_the_refusal_quotes_the_false_toast():
    """``#share-<block_id>`` is the plausible thing a caller tries, and it is the hazard:
    it navigates nowhere and shows a toast claiming intact content was deleted."""
    with pytest.raises(ValueError) as excinfo:
        docx_block_url(DOC_URL, f"share-{CLICKED[0][1]}")
    message = str(excinfo.value)
    assert '"The selection content has been deleted"' in message
    assert "share-" in message


@pytest.mark.conformance
def test_no_minted_url_can_carry_the_share_prefix_or_the_blockId_query():
    """The two measured no-ops are unreachable through this function by construction."""
    for kind, block_id, clicked, _behaviour in CLICKED:
        got = docx_block_url(DOC_URL, block_id)
        assert "#share-" not in got, kind
        assert "blockId=" not in got, kind
        assert got.count("#") == 1, kind


# --------------------------------------------------------------------------- #
# AC1/AC5 — the measurement ships WITH the helper (LD-380's doctrine)           #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_the_measurement_disclosure_enumerates_what_was_measured():
    text = DOCX_BLOCK_ANCHOR_MEASUREMENT
    assert "2026-08-10" in text
    assert "web" in text.lower()
    for kind in ("heading1", "heading2", "paragraph", "table", "bullet", "code"):
        assert kind in text, f"the disclosure does not name the {kind} row it rests on"
    assert "one tenant" in text.lower()


@pytest.mark.conformance
def test_the_measurement_disclosure_names_the_UNMEASURED_axes_as_unmeasured():
    text = DOCX_BLOCK_ANCHOR_MEASUREMENT
    lowered = text.lower()
    assert "unmeasured" in lowered
    for axis in ("mobile", "desktop", "wiki"):
        assert axis in lowered, f"the {axis} axis is not declared unmeasured"
    assert "not refuted" in lowered or "neither refuted" in lowered


@pytest.mark.conformance
def test_the_docstring_quotes_BOTH_authored_paragraphs_verbatim():
    doc = docx_block_url.__doc__ or ""
    assert DOCX_BLOCK_ANCHOR_MEASUREMENT in doc
    assert DOCX_SECTION_ANCHOR_UI_ONLY in doc


# --------------------------------------------------------------------------- #
# AC3 — the supersession ethic: the reason survives, only the conclusion narrows #
# --------------------------------------------------------------------------- #

#: 1.29's reason, verbatim from the pre-LD-379 constant. It is preserved unedited: the
#: share-token half of the claim was never refuted, and the probe re-confirmed it on a
#: fresh disposable (`1770001 invalid param` / `1770002 not found`).
PRESERVED_1_29_REASON = (
    "The fragment is a share token the Lark web client mints "
    "when a person copies a section link; it is NOT a block id (an exhaustive check of a "
    "real document's every block found no match, and the block-get endpoint returns "
    "not-found for the share token while returning the block for a real id), and no docx "
    "share or permalink endpoint exists to turn it into anything the API will accept."
)


@pytest.mark.conformance
def test_the_share_token_REASON_survives_the_rewrite_verbatim():
    assert PRESERVED_1_29_REASON in DOCX_SECTION_ANCHOR_UI_ONLY


@pytest.mark.conformance
def test_the_CONCLUSION_is_narrowed_to_the_share_token_grammar_alone():
    """1.29 generalised to *docx anchors* as a class; the bare-fragment grammar was never
    tried. The claim may not outrun its evidence (process/doctrine/negative-claims.md)."""
    text = DOCX_SECTION_ANCHOR_UI_ONLY
    assert "docx_block_url" in text, (
        "the narrowed claim must point at the grammar that IS mintable")
    assert "#<block_id>" in text, "the bare-fragment grammar must be named, not implied"


@pytest.mark.conformance
def test_the_false_toast_hazard_is_quoted_verbatim_and_called_FALSE():
    text = DOCX_SECTION_ANCHOR_UI_ONLY
    assert '"The selection content has been deleted"' in text
    assert "perfectly intact" in text
    assert "data-loss bug" in text


# --------------------------------------------------------------------------- #
# AC6/AC8 — pure, offline, on the facade                                        #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_docx_block_url_is_reexported_on_the_common_facade():
    assert common.docx_block_url is docx_block_url
    assert "docx_block_url" in common.__all__


def test_docx_block_url_makes_no_api_call_and_derives_no_host_from_the_api_domain():
    src = pathlib.Path(inspect.getsourcefile(docx_block_url)).read_text(encoding="utf-8")
    for forbidden in ("Client", "requests", "http.client", "validate_download_url",
                      ".request(", "api_base"):
        assert forbidden not in src, f"doc_link.py must not reference {forbidden!r}"
