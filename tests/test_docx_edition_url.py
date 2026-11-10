"""``common.doc_link.docx_edition_url`` — the named-edition link, minted and DISCLOSED.

A pure, offline function beside ``docx_block_url``, under the same rules: the tenant host
is an **input** (it arrives on the document's own URL), never derived from an API domain
and never invented; a hostless, non-``https``, non-``/docx/`` or **wiki-wrapped** URL is a
refusal rather than a guess.

**The disclosure is the hard part, not the string.** Two of the halves this URL is built from
are Lark's own answers — the document URL as ``drive/v1/metas/batch_query`` reports it, and
a version token the versions family returned. The **query half was settled by a click**
(LD-419): on 2026-08-11 the minted link was opened in the Lark WEB client, on one tenant,
against a harness-created document whose two states had first been proven to differ at the
API level, and it showed the named version's state only, with Lark's own UI labelling the
view an older version. So the helper ships **click-verified** — with the axes nobody clicked
(mobile, the desktop app, wiki-wrapped documents, any other tenant) still named as
**unmeasured** — in one sentence authored once and quoted into every surface a consumer
meets: the docstring, the shipped guide and the release notes.

The construction cases are **conformance-tier**
(``process/doctrine/conformance-tier.md``): they pin a product claim about Lark's own web
client that this project does not own, so a red here can mean *the world changed*, not only
*we broke it*.
"""
import inspect
import pathlib

import pytest

import larkdocio
import larkdocio.common as common
from larkdocio.common.doc_link import docx_block_url, docx_edition_url
from larkdocio.common.url import DOCX_EDITION_LINK_CLICK_MEASUREMENT

#: The document's URL exactly as **Lark itself reported it** (`with_url: true`), and the
#: version token Lark minted for a version named ``V1.3`` — the two measured halves.
DOC_URL = "https://your-domain.larksuite.com/docx/Exampled24cabecc0bbfb9e5fa3"
VERSION_TOKEN = "kb1v8q"
CONSTRUCTED = f"{DOC_URL}?edition_id={VERSION_TOKEN}"

#: AC4's sentence, verbatim. It is authored ONCE in ``larkdocio.common.url`` and quoted into
#: the docstring, the guide and the release notes; this literal is the third-party copy that
#: makes "someone edited the disclosure softer — or wider" a test failure rather than a
#: shipped lie. LD-419 moved the verdict from click-UNVERIFIED to click-VERIFIED; the literal
#: was transformed, not dropped, so the sentence stays load-bearing in both directions.
CLICK_VERIFIED_SENTENCE = (
    "click-verified — the `?edition_id=` grammar was clicked on 2026-08-11 in the Lark WEB "
    "client, on one tenant, and it opened the named version."
)


# --------------------------------------------------------------------------- #
# AC1 — the construction, from the two measured halves                          #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_builds_the_constructed_url_from_the_two_measured_halves():
    assert docx_edition_url(DOC_URL, VERSION_TOKEN) == CONSTRUCTED


@pytest.mark.conformance
def test_the_tenant_host_comes_from_the_input_url_not_an_api_domain():
    got = docx_edition_url("https://your-domain.feishu.cn/docx/TOKEN123", "v9")
    assert got == "https://your-domain.feishu.cn/docx/TOKEN123?edition_id=v9"


@pytest.mark.conformance
def test_token_and_version_token_are_carried_unaltered():
    got = docx_edition_url("https://h.larksuite.com/docx/Keeps_UnderScores", "Ed_1-9")
    assert got == "https://h.larksuite.com/docx/Keeps_UnderScores?edition_id=Ed_1-9"


@pytest.mark.conformance
def test_the_path_half_is_the_same_string_its_neighbour_mints():
    """The measured half is measured *because* it is the grammar `docx_block_url` ships;
    if the two ever diverge, one of them is guessing."""
    neighbour = docx_block_url(DOC_URL, "blk9")
    assert docx_edition_url(DOC_URL, VERSION_TOKEN).split("?")[0] == neighbour.split("#")[0]


# --------------------------------------------------------------------------- #
# AC3 — an incoming query or fragment is DROPPED (and the docstring says so)     #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_an_incoming_query_and_fragment_are_dropped():
    got = docx_edition_url(f"{DOC_URL}?from=space#share-oldtoken", VERSION_TOKEN)
    assert got == CONSTRUCTED
    assert "from=space" not in got and "#" not in got


def test_the_docstring_says_the_incoming_query_is_dropped():
    """This function ADDS a query of its own, so "my `?from=` survived" is the reasonable
    wrong assumption — it is pre-empted where the caller reads."""
    doc = (docx_edition_url.__doc__ or "").lower()
    assert "dropped" in doc and "query" in doc


# --------------------------------------------------------------------------- #
# AC2 — the refusals are the neighbour's, one for one                           #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("bad", ["", "not-a-url", "https:///docx/tok", "ftp://h/docx/t",
                                 "http://your-domain.larksuite.com/docx/TOK"])
@pytest.mark.conformance
def test_a_missing_hostless_or_non_https_url_is_a_refusal_not_a_default(bad):
    with pytest.raises(ValueError):
        docx_edition_url(bad, VERSION_TOKEN)


@pytest.mark.parametrize("bad", [None, 12345, b"https://h/docx/t"])
def test_a_non_string_doc_url_is_refused(bad):
    with pytest.raises(ValueError):
        docx_edition_url(bad, VERSION_TOKEN)


@pytest.mark.conformance
def test_a_non_docx_url_is_refused():
    with pytest.raises(ValueError) as excinfo:
        docx_edition_url("https://your-domain.larksuite.com/sheets/SHEET123", VERSION_TOKEN)
    assert "/docx/" in str(excinfo.value)


@pytest.mark.conformance
def test_a_WIKI_wrapped_url_is_refused_as_UNMEASURED_rather_than_guessed():
    with pytest.raises(ValueError) as excinfo:
        docx_edition_url("https://your-domain.larksuite.com/wiki/NODE123", VERSION_TOKEN)
    message = str(excinfo.value).lower()
    assert "wiki" in message and "unmeasured" in message


@pytest.mark.parametrize("bad", ["", None, 7, ()])
def test_an_empty_or_non_string_version_token_is_refused(bad):
    with pytest.raises(ValueError):
        docx_edition_url(DOC_URL, bad)


@pytest.mark.parametrize("call", [
    lambda: docx_edition_url("", VERSION_TOKEN),
    lambda: docx_edition_url("http://h.larksuite.com/docx/T", VERSION_TOKEN),
    lambda: docx_edition_url("https://h.larksuite.com/sheets/T", VERSION_TOKEN),
    lambda: docx_edition_url("https://h.larksuite.com/wiki/T", VERSION_TOKEN),
    lambda: docx_edition_url(DOC_URL, ""),
])
def test_every_refusal_names_the_function_and_what_to_pass_instead(call):
    with pytest.raises(ValueError) as excinfo:
        call()
    message = str(excinfo.value)
    assert "docx_edition_url" in message
    assert any(word in message for word in
               ("pass", "needs", "the document's own", "version token")), message


@pytest.mark.conformance
def test_the_refusal_fires_before_anything_else_D57():
    """A refusal the URL string alone can make fires before any credential or packet — so a
    bad URL *and* a bad token still raise, with no call spent either way."""
    with pytest.raises(ValueError):
        docx_edition_url("nonsense", "")


# --------------------------------------------------------------------------- #
# AC4 — the click-VERIFIED disclosure: authored once, on all three surfaces      #
# --------------------------------------------------------------------------- #

def test_the_constant_carries_the_click_verified_sentence_verbatim():
    assert CLICK_VERIFIED_SENTENCE in DOCX_EDITION_LINK_CLICK_MEASUREMENT


def test_the_docstring_quotes_the_disclosure_verbatim():
    assert DOCX_EDITION_LINK_CLICK_MEASUREMENT in (docx_edition_url.__doc__ or "")


def test_the_shipped_guide_quotes_the_disclosure_verbatim():
    assert DOCX_EDITION_LINK_CLICK_MEASUREMENT in larkdocio.guide(full=True)


def _release_notes_document():
    """The RELEASE NOTES **document** — the repository's complete copy, not the wheel's window.

    ``larkdocio.release_notes()`` returns a recent-N projection (LD-540), so a sentence quoted
    into an old release section legitimately ages out of the wheel; this disclosure was quoted
    into ``[1.33.0]``, which LD-560's ``[1.41.0]`` pushed past the window's edge. The claim
    these two tests make is *the disclosure is authored once and quoted into the document* —
    a claim about the document, which is this file. The separate claim that the disclosure
    stays reachable from an INSTALLED wheel is carried by the guide arm above, which reads a
    packaged surface that is not windowed.
    """
    import inspect
    import pathlib

    return (pathlib.Path(inspect.getfile(larkdocio)).parents[2]
            / "RELEASE_NOTES.md").read_text("utf-8")


def test_the_release_notes_quote_the_disclosure_verbatim():
    assert DOCX_EDITION_LINK_CLICK_MEASUREMENT in _release_notes_document()


def test_the_disclosure_cannot_be_edited_off_one_surface_and_left_on_the_others():
    """The point of authoring it once: three surfaces, one string, no drift between them."""
    surfaces = {
        "docstring": docx_edition_url.__doc__ or "",
        "guide": larkdocio.guide(full=True),
        "release notes": _release_notes_document(),
    }
    missing = [name for name, text in surfaces.items()
               if DOCX_EDITION_LINK_CLICK_MEASUREMENT not in text]
    assert not missing, f"the disclosure is missing from: {missing}"


# --------------------------------------------------------------------------- #
# AC5 — what IS measured is stated as measured, and no further                   #
# --------------------------------------------------------------------------- #

def test_the_disclosure_draws_the_line_between_the_measured_and_unmeasured_halves():
    text = DOCX_EDITION_LINK_CLICK_MEASUREMENT
    lowered = text.lower()
    assert "measured" in lowered and "unmeasured" in lowered
    assert "path" in lowered and "query" in lowered, (
        "the line is drawn between the PATH half and the QUERY half — name both")
    assert "state one" in lowered, (
        "what was SEEN is the evidence: the edition URL showed STATE ONE only; say so")
    assert "older version" in lowered, (
        "Lark's own UI labelled the edition view an older version — quote the label")
    assert "control" in lowered, (
        "the click was falsifiable because a control URL showed head; say so")


def test_the_disclosure_names_the_route_the_measured_halves_came_from():
    text = DOCX_EDITION_LINK_CLICK_MEASUREMENT
    assert "metas/batch_query" in text, "the document URL is Lark's own answer — cite it"
    assert "docx_block_url" in text, (
        "the path half is measured because it is the grammar the neighbour already mints")


def test_the_click_carries_its_own_particulars_not_a_bare_verdict():
    """A positive claim owes the same enumeration as a negative one (D-59): when, on which
    client, on how many tenants, and against what fixture."""
    text = DOCX_EDITION_LINK_CLICK_MEASUREMENT
    assert "2026-08-11" in text, "date the click"
    assert "WEB" in text, "name the client it was clicked on"
    assert "one tenant" in text, "one tenant is not every tenant — say which"
    assert "harness-created" in text, "name the fixture the click was made against"
    assert "at the api level" in text.lower(), (
        "the two states were proven to differ at the API level first — that is what makes "
        "the click falsifiable rather than reassuring")


def test_the_disclosure_keeps_the_unclicked_axes_disclosed_as_unmeasured():
    """AC2 — the click covers the web client, one tenant, one day. Everything else stays
    `unmeasured`, never `works` (negative-claims § A.1)."""
    lowered = DOCX_EDITION_LINK_CLICK_MEASUREMENT.lower()
    for axis in ("mobile", "desktop app", "wiki-wrapped", "any other tenant"):
        assert axis in lowered, f"the unmeasured axis {axis!r} must stay disclosed"
    assert "neither refuted nor supported" in lowered
    assert "only another click can" in lowered, (
        "no API call can widen a rendering measurement — say so")


def test_the_disclosure_does_not_widen_the_click_to_an_unclicked_client():
    """The failure this test exists for: an editor 'tightening' the verified wording into a
    promise about clients and tenants nobody clicked."""
    lowered = DOCX_EDITION_LINK_CLICK_MEASUREMENT.lower()
    for overclaim in ("every client", "all clients", "any client", "on every tenant",
                      "all tenants", "in the mobile client", "always opens"):
        assert overclaim not in lowered, f"the disclosure must not claim {overclaim!r}"


# --------------------------------------------------------------------------- #
# AC1/AC7 — pure, offline, and on the facade                                    #
# --------------------------------------------------------------------------- #

def test_docx_edition_url_is_reexported_on_the_common_facade():
    assert common.docx_edition_url is docx_edition_url
    assert "docx_edition_url" in common.__all__
    assert common.DOCX_EDITION_LINK_CLICK_MEASUREMENT is DOCX_EDITION_LINK_CLICK_MEASUREMENT
    assert "DOCX_EDITION_LINK_CLICK_MEASUREMENT" in common.__all__


def test_the_old_click_unverified_NAME_is_gone_from_the_public_surface():
    """LD-419 renamed the constant because its old name states a verdict that is no longer
    true, and a symbol whose name contradicts its body traps every reader who greps rather
    than reads. The rename is consumer-observable, so it is complete or it is a trap of its
    own: no alias, no stale `__all__` entry."""
    assert not hasattr(common, "DOCX_EDITION_LINK_CLICK_UNVERIFIED")
    assert "DOCX_EDITION_LINK_CLICK_UNVERIFIED" not in common.__all__
    import larkdocio.common.url as url_module
    assert not hasattr(url_module, "DOCX_EDITION_LINK_CLICK_UNVERIFIED")


def test_docx_edition_url_makes_no_api_call_and_derives_no_host_from_the_api_domain():
    src = pathlib.Path(inspect.getsourcefile(docx_edition_url)).read_text(encoding="utf-8")
    for forbidden in ("Client", "requests", "http.client", "validate_download_url",
                      ".request(", "api_base"):
        assert forbidden not in src, f"doc_link.py must not reference {forbidden!r}"


def test_the_two_link_minters_take_the_same_first_argument():
    """Same shape, same rules — the caller learns one contract, not two."""
    first = [list(inspect.signature(fn).parameters)[0]
             for fn in (docx_block_url, docx_edition_url)]
    assert first == ["doc_url", "doc_url"]


def test_ld429_no_hand_written_comment_still_calls_the_label_unclicked_or_weakest():
    """LD-429 — LD-419 renamed the constant to
    ``DOCX_EDITION_LINK_CLICK_MEASUREMENT`` (click-VERIFIED), and every *projected* surface
    followed, but two hand-written comments did not — they are not projections, so no guard
    reddened on the rename, and a reader of the source meets a false verdict one line above
    the very symbol that superseded it. 'unclicked axes' naming the axes nobody clicked is
    still correct disclosure (see `doc_link.py`'s own docstring and
    `test_the_disclosure_keeps_the_unclicked_axes_disclosed_as_unmeasured` above) — what must
    not survive is the label ITSELF being called unclicked, or called 'the weakest of the
    three'."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    targets = [
        repo_root / "src" / "larkdocio" / "common" / "__init__.py",
        repo_root / "tests" / "test_conformance_tier.py",
    ]
    for path in targets:
        lowered = path.read_text(encoding="utf-8").lower()
        assert "weakest of the" not in lowered, (
            f"{path}: the edition link's label must not be called the weakest of the three "
            "after LD-419's click-verified rename")
        assert "measured halves, and unclicked" not in lowered, (
            f"{path}: stale pre-LD-419 verdict — the label is click-verified, not unclicked")
        assert "measured halves, unclicked)" not in lowered, (
            f"{path}: stale pre-LD-419 verdict — the label is click-verified, not unclicked")
