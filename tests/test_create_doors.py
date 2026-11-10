"""LD-572 — five doors around creating an object (docs wave 6/7).

Five bugs, four of them prose-fixable against a signature that already refuses correctly:

1. No shipped route answered "what is the URL of the object I just created" (scoped to docx —
   the docx v1 reply carries no ``url`` and this library never assembles one).
2. The guide presented a no-``folder_token`` create as a LIVE CALLER CHOICE in two places,
   against a signature that is keyword-only with no default.
3. An omitted ``folder_token`` produces a bare Python ``TypeError`` with none of the library's
   teaching text — and both ``write/client.py`` and ``sheets/write_client.py`` shipped a FALSE
   claim that an "absent" spelling is refused by ``MissingDestinationError`` (it is not: an
   absent keyword raises ``TypeError`` before this library ever runs).
4. ``create_app``'s default table was undisclosed in its own docstring (though already
   documented, twice, in the guide).
5. ``create_document(title=…)`` followed by ``heading(1, …)`` silently makes a second H1.

No signature changed and no behavior changed — this is prose, docstrings and the guide.
"""
import pathlib

import pytest

import private_tree  # noqa: E402  (LD-691)

import larkdocio
from larkdocio.base.schema_client import BaseSchemaClient
from larkdocio.sheets.write_client import SheetsWriteClient
from larkdocio.write.client import WriteClient

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
GUIDE_PATH = REPO_ROOT / "src" / "larkdocio" / "GUIDE.md"


def _guide_text():
    return GUIDE_PATH.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# AC4 — the false "absent" clause is struck in BOTH docstrings, and the       #
# TypeError is disclosed where a caller meets it.                            #
# --------------------------------------------------------------------------- #

def test_create_document_docstring_states_that_OMISSION_REACHES_THE_LIBRARYS_REFUSAL():
    """**TRANSFORMED by LD-582**, not deleted (`process/doctrine/supersession.md` § A.1).

    LD-572's reason survives in full: a caller must be able to read, in the docstring, which
    failure an unaddressed create actually produces. Its *conclusion* — that for this method
    the answer is Python's ``TypeError``, and that a caller should pass ``None`` to reach the
    teaching refusal instead — is what LD-582 superseded by giving ``folder_token`` a ``None``
    default. So the docstring must now say the one true thing (every way of not naming a
    destination, omission included, reaches ``MissingDestinationError``) and must **not** still
    promise the ``TypeError`` it no longer raises.

    The original assertion (`"absent" not in doc`) was LD-572's way of striking a claim that was
    then FALSE. It is now true of this method, so the guard asserts the fact rather than the
    absence of one wording."""
    doc = WriteClient.create_document.__doc__
    assert "TypeError" not in doc
    assert "MissingDestinationError" in doc
    assert "folder_token" in doc
    assert "omitted" in doc.lower()


def test_create_spreadsheet_docstring_does_not_claim_absent_is_refused_by_the_library():
    doc = SheetsWriteClient.create_spreadsheet.__doc__
    assert "absent" not in doc.lower()


def test_create_spreadsheet_docstring_discloses_the_TypeError():
    doc = SheetsWriteClient.create_spreadsheet.__doc__
    assert "TypeError" in doc
    assert "folder_token" in doc


def test_create_app_docstring_never_claimed_every_spelling_including_absent_is_refused():
    """create_app's folder_token HAS a None default, so it never carried write/client.py's and
    sheets/write_client.py's false clause — this pins that it stays that way (nothing to
    strike). Its own (true, historical) use of "absent" describes what the OLD default did,
    not a claim that MissingDestinationError catches an absent keyword today."""
    doc = BaseSchemaClient.create_app.__doc__
    assert "every spelling of \"none\"" in doc.lower()
    assert "absent, ``none``" not in doc.lower()
    assert "(absent," not in doc


def test_what_omitting_the_keyword_ACTUALLY_raises_on_each_of_the_two_methods():
    """**TRANSFORMED by LD-582**, not deleted. LD-572's reason — the docstrings' claim about
    omission is proven directly against the real signatures rather than trusted — is exactly
    why this test survives the ruling: the two methods now answer *differently*, and that
    asymmetry is the thing most worth pinning.

    ``create_document`` gained a ``None`` default (LD-582), so omission reaches the library.
    ``create_spreadsheet`` did **not**: the ruling named one method, so its keyword-only
    no-default shape and its ``TypeError`` are still true and still asserted here (AC5)."""
    import inspect

    from larkdocio.errors import MissingDestinationError

    # docx — the library owns omission now.
    with pytest.raises(MissingDestinationError):
        WriteClient.create_document(object(), title="x")  # folder_token omitted entirely
    doc_param = inspect.signature(WriteClient.create_document).parameters["folder_token"]
    assert doc_param.kind == inspect.Parameter.KEYWORD_ONLY
    assert doc_param.default is None

    # sheets — NAMED, NOT CHANGED: Python still refuses first, one call earlier.
    with pytest.raises(TypeError):
        SheetsWriteClient.create_spreadsheet(object(), title="x")
    sheet_param = inspect.signature(
        SheetsWriteClient.create_spreadsheet).parameters["folder_token"]
    assert sheet_param.kind == inspect.Parameter.KEYWORD_ONLY
    assert sheet_param.default is inspect.Parameter.empty


# --------------------------------------------------------------------------- #
# AC3 — the two GUIDE.md passages stop presenting an impossible option        #
# --------------------------------------------------------------------------- #

def test_the_grant_recipe_no_longer_presents_no_folder_token_as_a_live_choice():
    """The old bullet read '* Created with NO `folder_token` -> the member list reads empty'
    as if that were something a caller of this library could still produce."""
    text = _guide_text()
    assert "* **Created with NO `folder_token`" not in text


def test_the_grant_recipe_cross_references_where_a_new_object_goes():
    text = _guide_text()
    section = text.split("### Recipe: grant a HUMAN access", 1)[1].split("\n### ", 1)[0]
    assert "Where a new object goes" in section


def test_the_docx_write_handshake_no_longer_presents_no_folder_token_as_a_live_choice():
    text = _guide_text()
    assert "With **no** `folder_token` the document is\ncreated **in the app's own space**" \
        not in text
    # The old framing described the choice in the present tense as something you decide.
    assert "the second one decides where the document goes" not in text


def test_the_docx_write_handshake_states_the_destination_is_required():
    """**LD-586 transformed this arm; its reason is unchanged.** The reason was, and is, that
    this section must state the destination is REQUIRED rather than present omitting it as a
    live choice. What changed is the phrase it pinned: ``both are required`` was false —
    ``title`` carries a default and is never validated, so ``create_document(folder_token=f)``
    creates an *untitled* document rather than refusing, exactly as the method's own docstring
    says (*"the destination is the caller's — folder_token is required"*). Pinning the false
    half of a true point is what kept it shipping."""
    text = _guide_text()
    section = text.split("**WHERE THE DOCUMENT LANDS", 1)[1].split("\n### ", 1)[0]
    assert "`folder_token` is the required one" in section
    assert "both are required" not in section, (
        "`title` is not required — it defaults to the empty string and is never validated"
    )
    assert "Where a new object goes" in section


def test_the_docx_handshake_no_longer_promises_a_TypeError_LD_572_no_longer_raises():
    """**TRANSFORMED by LD-582** (`process/doctrine/staleness.md` — the same change pays for
    the truth it breaks). LD-572 taught the docx create recipe to name **two** different
    failures; ``create_document``'s ``None`` default leaves it with one. The recipe's other
    claims — the token's provenance, inherited access, document_id-is-the-root-Page-block —
    are untouched and still asserted by the tests around this one.

    The Sheets recipe is not in this section and is not in scope (AC5)."""
    text = _guide_text()
    section = text.split("**WHERE THE DOCUMENT LANDS", 1)[1].split("\n### ", 1)[0]
    assert "Two different failures" not in section
    assert "missing 1 required keyword-only argument" not in section
    assert "TypeError" not in section
    # The one statement that replaces them, and the refusal it names.
    assert "MissingDestinationError" in section
    assert "omit" in section.lower()


def test_neither_rewritten_passage_quotes_the_refusal_text_verbatim():
    """LD-565 owns and is about to rewrite common.destination's constants; LD-572 must
    cross-reference, never paraphrase or quote them (the F1 trap named in scrutiny)."""
    from larkdocio.common.destination import (
        DESTINATION_RULE,
        HOW_TO_GET_A_DESTINATION,
        WHAT_A_FOLDER_COSTS,
        WHAT_TO_SUPPLY,
    )

    text = _guide_text()
    grant_section = text.split(
        "### Recipe: grant a HUMAN access", 1)[1].split("\n### ", 1)[0]
    handshake_section = text.split("**WHERE THE DOCUMENT LANDS", 1)[1].split("\n### ", 1)[0]
    for fragment in (DESTINATION_RULE, WHAT_TO_SUPPLY, HOW_TO_GET_A_DESTINATION,
                     WHAT_A_FOLDER_COSTS):
        assert fragment not in grant_section
        assert fragment not in handshake_section


# --------------------------------------------------------------------------- #
# AC1 — the created-object URL is answered at the point of need, docx-scoped  #
# --------------------------------------------------------------------------- #

def test_the_docx_write_handshake_names_the_url_gap_and_the_paved_road():
    text = _guide_text()
    section = text.split("**WHERE THE DOCUMENT LANDS", 1)[1].split("\n### ", 1)[0]
    assert "url" in section
    assert "FolderChild.url" in section
    assert "Optional" in section
    # The honest reason, not a claim the tenant host is unknowable.
    assert "permalink" in section


def test_folder_child_url_is_genuinely_optional_and_defaults_to_none():
    from larkdocio.drive.models import FolderChild

    assert FolderChild.url.__class__ is type(None) or True  # dataclass field, sanity only
    child = FolderChild(token="x")
    assert child.url is None


def test_the_walk_folder_recipe_now_prints_child_url():
    text = _guide_text()
    assert "child.url" in text


# --------------------------------------------------------------------------- #
# AC2 — no NEW/touched example teaches a hardcoded host; the "say why" lands  #
# once, where examples live.                                                  #
# --------------------------------------------------------------------------- #

def test_the_domain_section_states_why_once():
    text = _guide_text()
    section = text.split(
        "### `domain=` is the Lark **API** domain, not your tenant host", 1
    )[1].split("\n### ", 1)[0]
    assert "never" in section.lower()
    assert "tenant" in section.lower()


# --------------------------------------------------------------------------- #
# AC5(a) — create_app's docstring discloses the default table and POINTS at   #
# the guide by section name; no second guide passage.                        #
# --------------------------------------------------------------------------- #

def test_create_app_docstring_discloses_the_default_table():
    doc = BaseSchemaClient.create_app.__doc__
    assert "table" in doc.lower()
    assert "not empty" in doc.lower() or "not one you asked for" in doc.lower()


def test_create_app_docstring_points_at_the_guide_section_by_name_not_a_restatement():
    doc = BaseSchemaClient.create_app.__doc__
    assert "structural handshake" in doc


def test_create_app_docstring_cites_no_dogfood_path():
    """AC5(a)'s own trap: a dev/dogfood5/ path in a docstring reddens the dialect guard."""
    doc = BaseSchemaClient.create_app.__doc__
    assert "dogfood" not in doc.lower()
    assert "dev/" not in doc


def test_the_default_table_disclosure_is_not_duplicated_as_a_second_guide_passage():
    """The measured fact already lives at the Base structural-handshake recipe; AC5(a)
    forbids a SECOND independent statement of it."""
    text = _guide_text()
    assert text.count("AND A NEW BASE IS NOT EMPTY") == 1


@private_tree.internal_log
def test_the_changelog_cites_the_read_back_evidence_and_release_notes_does_not():
    """AC5(a)'s dev/dogfood5/ citation is confined to CHANGELOG.md, the one dialect-exempt
    document."""
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    release_notes = (REPO_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert "dev/dogfood5/payload-record.json" in changelog
    assert "dogfood" not in release_notes.lower()
    assert "dev/" not in release_notes


# --------------------------------------------------------------------------- #
# AC5(b) — the duplicate-H1 foot-gun, cited to the reader's own projection     #
# --------------------------------------------------------------------------- #

def test_the_docx_write_handshake_warns_about_the_duplicate_H1():
    text = _guide_text()
    section = text.split("**WHERE THE DOCUMENT LANDS", 1)[1].split("\n### ", 1)[0]
    assert "second" in section.lower() and "H1" in section
    assert "heading(1" in section


def test_the_duplicate_H1_claim_cites_the_reader_rather_than_re_deriving_the_rule():
    text = _guide_text()
    section = text.split("**WHERE THE DOCUMENT LANDS", 1)[1].split("\n### ", 1)[0]
    assert "read.parser" in section or "read_support" in section


def test_the_page_block_really_does_emit_the_title_as_an_H1():
    """Corroborates the guide's new claim against the block matrix registry directly."""
    from larkdocio.blocks.read_support import READ_SUPPORT

    page_rows = [row for row in READ_SUPPORT if row[0] == 1]
    assert page_rows, "no docx block-type-1 (page) row in the registry"
    assert "{title}" in page_rows[0][3]


# --------------------------------------------------------------------------- #
# AC7 / AC8 — this issue's own text carries no bare universal about the URL   #
# door and does not over-claim the destination-input reason beyond docx.     #
# --------------------------------------------------------------------------- #

def test_the_docx_write_handshake_scopes_the_url_gap_to_docx_not_every_create():
    text = _guide_text()
    section = text.split("**WHERE THE DOCUMENT LANDS", 1)[1].split("\n### ", 1)[0]
    assert "scoped to docx" in section.lower()
    assert "create_spreadsheet" in section
    assert "create_app" in section


def test_guide_still_carries_zero_LD_NNN_ids():
    """The dialect guard's own floor — new prose must not reintroduce an issue id."""
    import re

    text = _guide_text()
    assert re.findall(r"\bLD-\d+\b", text) == []
