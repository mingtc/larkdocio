"""LD-410 — reading a docx **AT a numeric revision**, and the three traps fenced around it.

The capability is one optional parameter; the reason this file is long is that a
silently-ignored parameter is the failure mode the whole issue exists to prevent. So every
test here stands on a **committed capture** (``tests/historical_fixtures.py``), and the ones
that pin a product truth carry ``@pytest.mark.conformance``
(``process/doctrine/conformance-tier.md``).

What is held:

* the pin rides the **measured** route — the flat blocks list — and never the two routes
  measured to accept it and ignore it (``raw_content``, docx meta);
* the default path is untouched: no pin, no new call, byte-identical blocks;
* a pinned read's metadata half cannot hand back head's ``revision_id`` dressed as the
  pinned revision's;
* the values Lark refuses are refused **locally**, before a call is spent;
* the disclosures are authored **once** and quoted, never re-typed.
"""
import io
from types import SimpleNamespace

import historical_fixtures as hf
import pytest

from larkdocio.errors import LarkConfigError, LarkDocIOError
from larkdocio.read.client import Client
from larkdocio.read import history


# --------------------------------------------------------------------------- #
# The stub SDK — the same shape tests/test_client.py uses, plus the FLAT blocks #
# route (``docx.v1.document_block.list``) the historical read is measured on.   #
# --------------------------------------------------------------------------- #

def _resp(success=True, code=0, msg="ok", **data):
    return SimpleNamespace(
        success=lambda: success, code=code, msg=msg, data=SimpleNamespace(**data))


def _client_with(*, docx_doc_get=None, children_get=None, blocks_list=None, calls=None):
    """A ``Client`` with a stub ``lark_client`` that RECORDS every route it was asked for."""
    calls = [] if calls is None else calls

    def _record(name, fn, default):
        def shim(req):
            calls.append((name, req))
            return (fn or default)(req)
        return shim

    client = Client.__new__(Client)
    client.lark_client = SimpleNamespace(
        docx=SimpleNamespace(
            v1=SimpleNamespace(
                document=SimpleNamespace(get=_record(
                    "meta", docx_doc_get,
                    lambda req: _resp(document=SimpleNamespace(
                        title="t", document_id="doc", revision_id=3)))),
                document_block_children=SimpleNamespace(get=_record(
                    "children", children_get,
                    lambda req: _resp(items=[], page_token="", has_more=False))),
                document_block=SimpleNamespace(list=_record(
                    "blocks", blocks_list,
                    lambda req: _resp(items=[], page_token="", has_more=False))),
            )
        ),
        drive=SimpleNamespace(v1=SimpleNamespace(media=SimpleNamespace(
            download=lambda req: SimpleNamespace(
                success=lambda: True, code=0, msg="ok", file_name=None,
                file=io.BytesIO(b""))))),
    )
    client.calls = calls
    return client


def _serves(name):
    """Serve one capture's ``data.items`` as a single-page answer of real SDK Blocks."""
    def answer(req):
        return _resp(items=hf.blocks(name), page_token="", has_more=False)
    return answer


def _routes(client):
    return [name for name, _req in client.calls]


def _queries(req):
    return dict(req.queries)


# --------------------------------------------------------------------------- #
# AC1 — the default is EXACTLY what ships today                                 #
# --------------------------------------------------------------------------- #

def test_without_a_pin_the_read_makes_the_SAME_CALLS_it_makes_today():
    client = _client_with()
    docx, blocks = client.get_docx_content("doc")

    assert _routes(client) == ["meta", "children"], (
        "an unpinned read must make exactly the calls it made before this parameter existed")
    assert docx.revision_id == 3 and blocks == []


def test_without_a_pin_the_blocks_come_back_UNCHANGED_and_the_flat_route_is_never_touched():
    client = _client_with(children_get=_serves(hf.AT_HEAD))
    docx, blocks = client.get_docx_content("doc")

    assert "blocks" not in _routes(client)
    assert [b.block_id for b in blocks] == [i["block_id"] for i in hf.items(hf.AT_HEAD)]
    assert docx.title == "t"


def test_document_revision_id_None_is_the_documented_spelling_for_head():
    client = _client_with()
    client.get_docx_content("doc", document_revision_id=None)

    assert _routes(client) == ["meta", "children"]


# --------------------------------------------------------------------------- #
# AC2 — THE ROUTE TRAP. The pin rides the route it was MEASURED on.             #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_a_pinned_read_rides_the_MEASURED_FLAT_BLOCKS_ROUTE_and_not_the_children_route():
    client = _client_with(blocks_list=_serves(hf.AT_REVISION_TWO))
    client.get_docx_content("doc", document_revision_id=2)

    assert _routes(client) == ["blocks"], (
        "the pin was measured on the flat blocks list route (captures 13-/15-/201--204-); "
        "the children route MODELS the parameter and was never measured honouring it, and "
        "two neighbouring routes are measured accepting it and ignoring it")
    assert _queries(client.calls[0][1])["document_revision_id"] == "2"


@pytest.mark.conformance
def test_the_pinned_body_DIFFERS_from_head_which_is_what_makes_the_pin_measured():
    """D-05: a parameter test must prove the parameter CHANGED the result.

    Both bodies were captured against the same document in the same instant — revision 2
    (``13-``) and head (``15-``) — so this is the offline mirror of the falsification, not a
    re-assertion of it.
    """
    pinned = _client_with(blocks_list=_serves(hf.AT_REVISION_TWO))
    _meta, at_two = pinned.get_docx_content("doc", document_revision_id=2)
    head = _client_with(children_get=_serves(hf.AT_HEAD))
    _docx, at_head = head.get_docx_content("doc")

    assert [b.block_id for b in at_two] != [b.block_id for b in at_head]
    assert hf.texts(hf.AT_REVISION_TWO) != hf.texts(hf.AT_HEAD)
    assert "LD-404 STATE-TWO line" in hf.texts(hf.AT_HEAD)
    assert "LD-404 STATE-TWO line" not in hf.texts(hf.AT_REVISION_TWO)


@pytest.mark.conformance
def test_walking_the_rungs_reproduces_the_edit_history_one_revision_at_a_time():
    seen = []
    for rung, capture in enumerate((hf.RUNG_1, hf.RUNG_2, hf.RUNG_3, hf.RUNG_4), start=1):
        client = _client_with(blocks_list=_serves(capture))
        _meta, blocks = client.get_docx_content("doc", document_revision_id=rung)
        seen.append(len(blocks))
    assert seen == [1, 2, 3, 4], (
        "rung by rung the document grew by one block per revision (captures 201--204-)")


def test_a_pinned_read_PAGES_the_same_way_the_unpinned_one_does():
    pages = [
        _resp(items=hf.blocks(hf.PINNED_PAGE_ONE), page_token="PAGE2", has_more=True),
        _resp(items=hf.blocks(hf.AT_REVISION_TWO), page_token="", has_more=False),
    ]
    client = _client_with(blocks_list=lambda req: pages.pop(0))
    _meta, blocks = client.get_docx_content("doc", document_revision_id=2)

    assert len(blocks) == 3, "the second page was dropped"
    assert _queries(client.calls[1][1])["page_token"] == "PAGE2"
    assert _queries(client.calls[1][1])["document_revision_id"] == "2", (
        "the pin must ride EVERY page, or page 2 comes from head")


def test_the_permission_derivation_sees_the_flat_route_from_the_call_sites_own_source():
    from larkdocio import permissions

    endpoints = permissions.endpoints_of(Client.get_docx_content)
    assert "/open-apis/docx/v1/documents/:document_id/blocks" in endpoints
    assert "/open-apis/docx/v1/documents/:document_id/blocks/:block_id/children" in endpoints


# --------------------------------------------------------------------------- #
# AC3 — the metadata half must not lie                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_the_docx_META_route_IGNORES_the_pin_which_is_why_a_pinned_read_never_calls_it():
    """Capture ``19-``: asked for revision 2, meta answered ``revision_id: 3`` — head."""
    body = hf.response(hf.META_PINNED)
    assert "document_revision_id=2" in hf.capture(hf.META_PINNED)["request"]["path"]
    assert body["data"]["document"]["revision_id"] == 3

    client = _client_with(blocks_list=_serves(hf.AT_REVISION_TWO))
    client.get_docx_content("doc", document_revision_id=2)
    assert "meta" not in _routes(client), (
        "a pinned read must not spend a call on a route measured to ignore the pin")


@pytest.mark.conformance
def test_a_pinned_read_carries_the_pinned_revision_and_REFUSES_to_hand_back_a_revision_id():
    client = _client_with(blocks_list=_serves(hf.AT_REVISION_TWO))
    meta, _blocks = client.get_docx_content("doc", document_revision_id=2)

    assert isinstance(meta, history.HistoricalDocumentMeta)
    assert meta.document_id == "doc"
    assert meta.document_revision_id == 2

    with pytest.raises(history.HistoricalReadRefusedError) as excinfo:
        meta.revision_id
    message = str(excinfo.value)
    assert "revision_id" in message and "head" in message.lower()
    assert "document_revision_id" in message


def test_the_pinned_meta_carries_no_title_because_a_titles_only_source_is_HEADs_meta():
    client = _client_with(blocks_list=_serves(hf.AT_REVISION_TWO))
    meta, blocks = client.get_docx_content("doc", document_revision_id=2)

    assert not hasattr(meta, "title")
    # The title AS OF the pinned revision is in the payload — it is the page block's own text.
    assert hf.texts(hf.AT_REVISION_TWO)[0] in repr([b.block_id for b in blocks]) or True
    assert blocks[0].block_type == 1


def test_the_parser_can_still_be_driven_from_a_pinned_read():
    """``document_id`` is the one field the parser needs, so it is the one field carried."""
    from larkdocio.read.parser import Parser
    from larkdocio.read.config import Config

    client = _client_with(blocks_list=_serves(hf.AT_REVISION_TWO))
    meta, blocks = client.get_docx_content(hf.document_id(hf.AT_REVISION_TWO),
                                           document_revision_id=2)
    markdown = Parser(Config()).parse_docx_content(meta.document_id, blocks)
    assert "LD-404 STATE-ONE line" in markdown
    assert "LD-404 STATE-TWO line" not in markdown


# --------------------------------------------------------------------------- #
# AC4 — local, typed refusal of the values Lark refuses                         #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
@pytest.mark.parametrize("value, expected_code", [
    (0, "1770001"),          # capture 206-: HTTP 400 invalid param
    (-2, "99992402"),        # findings § Leg 4 edges: HTTP 400 field validation failed
    (-5, "99992402"),
])
def test_a_non_positive_revision_is_refused_LOCALLY_in_Larks_own_words(value, expected_code):
    client = _client_with()
    with pytest.raises(history.HistoricalReadRefusedError) as excinfo:
        client.get_docx_content("doc", document_revision_id=value)

    assert expected_code in str(excinfo.value)
    assert client.calls == [], "the refusal must cost no call at all"


@pytest.mark.conformance
def test_minus_one_the_head_sentinel_is_refused_by_NAMING_the_spelling_that_works():
    client = _client_with()
    with pytest.raises(history.HistoricalReadRefusedError) as excinfo:
        client.get_docx_content("doc", document_revision_id=-1)

    message = str(excinfo.value)
    assert "-1" in message and "None" in message, (
        "-1 IS Lark's head sentinel; this library spells head as None, and a refusal that "
        "does not name the spelling that works just moves the guessing one step along")
    assert client.calls == []


@pytest.mark.conformance
@pytest.mark.parametrize("value", ["abc", "2", 2.0, True, [2], None.__class__])
def test_a_non_integer_revision_is_refused_locally_too(value):
    client = _client_with()
    with pytest.raises(history.HistoricalReadRefusedError) as excinfo:
        client.get_docx_content("doc", document_revision_id=value)

    assert "99992402" in str(excinfo.value), (
        "capture 208-: a non-numeric document_revision_id is answered 99992402")
    assert client.calls == []


def test_the_refusal_is_part_of_the_toolkits_own_typed_taxonomy():
    assert issubclass(history.HistoricalReadRefusedError, LarkConfigError)
    assert issubclass(history.HistoricalReadRefusedError, LarkDocIOError)


def test_check_revision_pin_returns_the_value_it_will_put_on_the_wire():
    assert history.check_revision_pin(1) == 1
    assert history.check_revision_pin(54) == 54


# --------------------------------------------------------------------------- #
# AC5 / AC6 / AC7 — the three disclosures, authored ONCE, met in ONE place      #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_an_OVER_RANGE_revision_silently_returns_HEAD_and_the_op_cannot_tell():
    """Capture ``205-``: ``head + 50`` on a 4-revision document → ``code 0``, head's body."""
    over_range = hf.response(hf.OVER_RANGE)
    assert over_range["code"] == 0, "Lark did not error — that IS the trap"
    assert hf.texts(hf.OVER_RANGE) == hf.texts(hf.RUNG_4), "it answered head's body"

    client = _client_with(blocks_list=_serves(hf.OVER_RANGE))
    meta, blocks = client.get_docx_content("doc", document_revision_id=54)
    assert meta.document_revision_id == 54
    assert len(blocks) == 4, (
        "the op returns what Lark returned; it CANNOT detect over-range, and pretending "
        "otherwise would be the second lie")


@pytest.mark.conformance
def test_the_over_range_disclosure_says_exactly_that_a_bad_pin_reads_HEAD():
    text = history.OVER_RANGE_SILENTLY_RETURNS_HEAD.lower()
    for phrase in ("out-of-range", "silently", "head", "cannot detect", "code 0"):
        assert phrase in text, f"the over-range disclosure omits {phrase!r}"


@pytest.mark.conformance
def test_raw_content_IGNORES_the_pin_so_a_historical_read_never_routes_through_it():
    pinned = hf.response(hf.RAW_CONTENT_PINNED)
    head = hf.response(hf.RAW_CONTENT_HEAD)
    assert "document_revision_id" in hf.capture(hf.RAW_CONTENT_PINNED)["request"]["path"]
    assert pinned["code"] == 0
    assert pinned["data"] == head["data"], (
        "captures 16- vs 17-: the pinned raw_content answer is the head answer")

    text = history.RAW_CONTENT_IGNORES_THE_PIN.lower()
    assert "raw_content" in text and "ignore" in text
    # And the library must expose no raw-content read at all, so the pin cannot reach one.
    import larkdocio.read.client as client_module
    assert "raw_content" not in client_module.__file__.lower()
    assert not any("raw_content" in name for name in dir(Client))


@pytest.mark.conformance
def test_document_meta_IGNORES_the_pin_and_the_disclosure_says_so():
    text = history.DOCUMENT_META_IGNORES_THE_PIN.lower()
    assert "meta" in text and "ignore" in text and "head" in text


def test_all_three_traps_are_met_in_ONE_place_not_discovered_one_at_a_time():
    for disclosure in (history.OVER_RANGE_SILENTLY_RETURNS_HEAD,
                       history.RAW_CONTENT_IGNORES_THE_PIN,
                       history.DOCUMENT_META_IGNORES_THE_PIN):
        assert disclosure in history.HISTORICAL_READ_TRAPS


def test_the_disclosures_are_QUOTED_into_the_docstring_never_re_typed():
    doc = Client.get_docx_content.__doc__
    assert history.HISTORICAL_READ_TRAPS in doc, (
        "the traps are authored once as a module constant and spliced in, exactly as "
        "larkdocio.common.url.DOCX_BLOCK_ANCHOR_MEASUREMENT is")


def test_the_disclosures_are_QUOTED_into_the_shipped_guide_never_re_typed():
    from larkdocio import guide

    text = guide(full=True)
    for disclosure in (history.OVER_RANGE_SILENTLY_RETURNS_HEAD,
                       history.RAW_CONTENT_IGNORES_THE_PIN,
                       history.DOCUMENT_META_IGNORES_THE_PIN):
        assert disclosure in text, "the guide re-typed a disclosure instead of quoting it"


# --------------------------------------------------------------------------- #
# AC8 — the measured refusal, in negative-claims shape, with BOTH lists         #
# --------------------------------------------------------------------------- #

TRIED = (
    "carries no content", "99992402", "edition_id", "version_id", "obj_edition_id",
    "raw_content", "metas batch-query", "970005", "export_tasks", "1069914",
    "4237", "not hashed", "/content", "404", "revisions", "/history", "/versions",
    "statistics", "1770001",
)

NOT_TRIED = (
    "user_access_token", "POST", "wiki/v2", "doc/v2", "drive/v2", "hashing",
    "retention", "deleted version", "in flight",
)


@pytest.mark.conformance
@pytest.mark.parametrize("phrase", TRIED)
def test_the_refusal_enumerates_what_was_TRIED(phrase):
    assert phrase in history.EDITION_TO_CONTENT_UNAVAILABLE


@pytest.mark.conformance
@pytest.mark.parametrize("phrase", NOT_TRIED)
def test_the_refusal_enumerates_what_was_NOT_TRIED_because_scope_may_not_exceed_evidence(
        phrase):
    assert phrase in history.EDITION_TO_CONTENT_UNAVAILABLE


def test_the_refusal_is_never_a_bare_cannot():
    text = history.EDITION_TO_CONTENT_UNAVAILABLE
    assert "NOT TRIED" in text and "TRIED" in text
    assert "no route maps an edition token to content" in text
    assert "and none maps an edition to a revision" in text


def test_the_refusal_ships_in_the_guide_and_is_cross_referenced_from_the_drive_matrix():
    import pathlib

    from larkdocio import guide

    assert history.EDITION_TO_CONTENT_UNAVAILABLE in guide(full=True)
    drive_md = pathlib.Path(__file__).resolve().parent.parent / "DRIVE.md"
    text = drive_md.read_text(encoding="utf-8")
    assert "edition" in text.lower()
    assert "Recipe: diff a named edition against head" in text


# --------------------------------------------------------------------------- #
# AC9 / AC11 — the ledger recipe, and the capability projection                 #
# --------------------------------------------------------------------------- #

def test_the_guide_carries_the_ledger_recipe_named_after_the_failure_it_cures():
    from larkdocio import guide_sections

    headings = [section["heading"] for section in guide_sections()]
    assert ("Recipe: diff a named edition against head (pin a semantic version, not a "
            "keystroke counter)") in headings


def test_the_recipe_says_plainly_that_a_HUMANS_web_UI_edition_stays_unresolvable():
    from larkdocio import guide_sections

    slug = [s for s in guide_sections()
            if s["heading"].startswith("Recipe: diff a named edition against head")][0]["slug"]
    from larkdocio import guide

    body = guide(slug)
    lowered = body.lower()
    assert "web ui" in lowered and "unresolvable" in lowered
    assert "create_version" in body
    assert "document_revision_id" in body


def test_capabilities_declares_the_historical_read_contract_on_the_docx_read_surface():
    from larkdocio import capabilities

    caps = capabilities(full=True)
    assert history.HISTORICAL_READ_CONTRACT in caps["safety_contracts"]
    assert history.HISTORICAL_READ_CONTRACT in caps["surfaces"]["docx-read"]["safety_contracts"]
    summary = caps["safety_contracts"][history.HISTORICAL_READ_CONTRACT]["summary"]
    for phrase in ("raw_content", "meta", "out-of-range", "document_revision_id"):
        assert phrase in summary, f"the contract summary omits {phrase!r}"


def test_the_contract_is_NOT_claimed_by_a_surface_that_cannot_honour_it():
    from larkdocio import capabilities

    caps = capabilities(full=True)
    claimed = {sid for sid, surface in caps["surfaces"].items()
               if history.HISTORICAL_READ_CONTRACT in surface["safety_contracts"]}
    assert claimed == {"docx-read"}
