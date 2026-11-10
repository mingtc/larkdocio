"""Deep-link parsing — the four observed grammars, carried unaltered (groups (a)/M2).

The corpus is the four REAL strings the maintainer copied out of the Lark UI. Where the
round-2 spike abbreviates a host or a token with an ellipsis, the string is
reconstructed from the round-1 reverse-ask table, which carries the full URLs:

* docx section :  ``https://your-domain.larksuite.com/docx/DocCanaryExample00000000001#share-Example6927bf4fb83ebfc55a3a``
* sheets tab   :  ``https://your-domain.larksuite.com/sheets/SheetScratchExample00000001?sheet=7pg9wE``
* sheets range :  ``…/sheets/SheetScratchExample00000001?sheet=7pg9wE&rangeId=7pg9wE_jfPPffo2hw&rangeVer=1``
  (the range example abbreviates the spreadsheet token; it is the SAME sheet as the tab
  example, so the tab example's token is used)
* base record :  ``https://your-domain.larksuite.com/record/Example7c7a77cd34566f878ee6``
"""
import inspect

import pytest

from larkdocio.common.url import (
    DocAnchor,
    NotADeepLink,
    RecordAnchor,
    SheetAnchor,
    parse_deep_link,
    validate_download_url,
)
from larkdocio.sheets.embed import split_compound_token

HOST = "https://your-domain.larksuite.com"
DOCX_URL = f"{HOST}/docx/DocCanaryExample00000000001#share-Example6927bf4fb83ebfc55a3a"
SHEETS_TAB_URL = f"{HOST}/sheets/SheetScratchExample00000001?sheet=7pg9wE"
SHEETS_RANGE_URL = (
    f"{HOST}/sheets/SheetScratchExample00000001"
    "?sheet=7pg9wE&rangeId=7pg9wE_jfPPffo2hw&rangeVer=1"
)
RECORD_URL = f"{HOST}/record/Example7c7a77cd34566f878ee6"


# --------------------------------------------------------------------------- #
# AC2 — all four grammars parse, against the real strings                       #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_docx_section_anchor_parses():
    got = parse_deep_link(DOCX_URL)
    assert got == DocAnchor(
        doc_token="DocCanaryExample00000000001",
        share_token="Example6927bf4fb83ebfc55a3a",
    )


@pytest.mark.conformance
def test_sheets_tab_anchor_parses():
    got = parse_deep_link(SHEETS_TAB_URL)
    assert got == SheetAnchor(
        spreadsheet_token="SheetScratchExample00000001",
        sheet_id="7pg9wE",
        range_id=None,
        range_ver=None,
    )


@pytest.mark.conformance
def test_sheets_range_anchor_parses():
    got = parse_deep_link(SHEETS_RANGE_URL)
    assert got == SheetAnchor(
        spreadsheet_token="SheetScratchExample00000001",
        sheet_id="7pg9wE",
        range_id="7pg9wE_jfPPffo2hw",
        range_ver="1",
    )


@pytest.mark.conformance
def test_base_record_anchor_parses():
    got = parse_deep_link(RECORD_URL)
    assert got == RecordAnchor(record_token="Example7c7a77cd34566f878ee6")


# --------------------------------------------------------------------------- #
# AC2 — pass-through fidelity: every opaque part is byte-identical to its input #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_share_token_is_byte_identical_to_its_input_slice():
    got = parse_deep_link(DOCX_URL)
    assert got.share_token == DOCX_URL.split("#share-", 1)[1]


@pytest.mark.conformance
def test_range_id_and_ver_are_byte_identical_to_their_input_slices():
    got = parse_deep_link(SHEETS_RANGE_URL)
    assert got.range_id == "7pg9wE_jfPPffo2hw"
    # not normalised to an int, not stripped, not re-encoded
    assert got.range_ver == "1" and isinstance(got.range_ver, str)


@pytest.mark.conformance
def test_record_token_is_byte_identical_to_its_input_slice():
    got = parse_deep_link(RECORD_URL)
    assert got.record_token == RECORD_URL.rsplit("/record/", 1)[1]


@pytest.mark.parametrize(
    "opaque",
    ["Mixed_Case_AND_symbols", "UPPERlower123", "keeps_underscores_intact"],
)
@pytest.mark.conformance
def test_share_token_is_not_normalised(opaque):
    got = parse_deep_link(f"{HOST}/docx/DOC123#share-{opaque}")
    assert got.share_token == opaque  # not lower-cased, not split, not validated


# --------------------------------------------------------------------------- #
# AC2(i) — a #share- token is NEVER a block_id                                  #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_doc_anchor_has_no_block_id_field():
    fields = set(inspect.signature(DocAnchor).parameters)
    assert "share_token" in fields
    assert "block_id" not in fields  # the field is named so it cannot be mistaken


def test_doc_anchor_docstring_states_the_share_token_is_not_a_block_id():
    doc = DocAnchor.__doc__ or ""
    assert "block_id" in doc and "not" in doc.lower()


# --------------------------------------------------------------------------- #
# AC2(ii) — the rangeId is carried WHOLE, never fed to split_compound_token     #
# --------------------------------------------------------------------------- #

def test_range_id_is_not_split_by_the_compound_token_splitter():
    got = parse_deep_link(SHEETS_RANGE_URL)
    # the shape rhymes with the docx compound token, but the two are separate things:
    # the anchor carries the WHOLE rangeId, underscore and all.
    assert "_" in got.range_id
    # and it is emphatically not what split_compound_token would have produced
    assert got.range_id != split_compound_token(got.range_id)[0]


# --------------------------------------------------------------------------- #
# AC2(iii) — an unrecognised URL gets a typed answer, never a partial shape     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/whatever",
        f"{HOST}/wiki/SomeWikiToken",              # a recognised download type, but not a deep link
        f"{HOST}/sheets/SheetScratchExample00000001",  # bare sheet, no ?sheet= deep-link part
        f"{HOST}/docx/DocCanaryExample00000000001",     # bare doc, no #share- fragment
        "not-even-a-url",
        "",
    ],
)
@pytest.mark.conformance
def test_unrecognised_url_is_typed_not_a_deep_link(url):
    got = parse_deep_link(url)
    assert isinstance(got, NotADeepLink)
    assert got.url == url


@pytest.mark.conformance
def test_a_sheet_without_a_sheet_query_is_never_a_partially_filled_anchor():
    got = parse_deep_link(f"{HOST}/sheets/SheetScratchExample00000001")
    assert not isinstance(got, SheetAnchor)  # no half-built SheetAnchor(sheet_id=None)


# --------------------------------------------------------------------------- #
# The HOST + SCHEME policy — the regeneration spike's divergence C1.            #
#                                                                               #
# A module rebuilt from the corpus alone validated NEITHER host NOR scheme:     #
# `https://evil.invalid/record/Rec123` came back as `RecordAnchor(record_token=     #
# 'Rec123')`, and so did plain-http Lark URLs. The original refuses both, and   #
# nothing in the suite said so — the one foreign-host case in this file has no  #
# recognised path shape either, so both answers agreed for the wrong reason.    #
# These cases exercise the policy itself, and the sentence they pin now lives   #
# in the shipped guide (§ Deep links).                                          #
# --------------------------------------------------------------------------- #

#: The corpus sentence these cases mechanize, in the shipped guide's own words.
HOST_POLICY_FRAGMENTS = (
    "the same host and scheme policy as `validate_download_url`",
    "over `https` only",
    "a foreign host even over `https`, and plain `http` anywhere",
)


@pytest.mark.conformance
@pytest.mark.parametrize(
    "url",
    [
        # divergence C1, verbatim: a foreign host over https, every grammar
        "https://evil.invalid/record/Rec123",
        "https://evil.invalid/sheets/T?sheet=s",
        "https://evil.invalid/docx/DOC123#share-Example6927bf4fb83ebfc55a3a",
        # divergence C1, verbatim: plain http, on a real Lark host
        "http://x.feishu.cn/record/Rec",
        "http://x.feishu.cn/sheets/T?sheet=s",
        "http://x.feishu.cn/docx/DOC123#share-Example6927bf4fb83ebfc55a3a",
    ],
)
def test_a_foreign_host_or_plain_http_is_never_a_deep_link(url):
    """Divergence C1: a consumer that trusts the typed answer must never be handed an
    attacker-supplied token as a Lark address. The host and scheme policy is the same one
    `validate_download_url` applies, and it is applied BEFORE any grammar matches."""
    got = parse_deep_link(url)
    assert isinstance(got, NotADeepLink), f"{url} parsed as a Lark deep link: {got!r}"
    assert got.url == url


@pytest.mark.conformance
def test_the_allow_host_opt_in_still_widens_the_host_set_but_not_the_scheme():
    """The policy is a host ALLOWLIST with one opt-in door — and the door does not open
    for `http`: `allow_host` widens which hosts are Lark-family, never which schemes."""
    url = "https://tenant.example.com/record/Rec123"
    assert parse_deep_link(url, allow_host="example.com") == RecordAnchor(
        record_token="Rec123")
    assert isinstance(parse_deep_link(url), NotADeepLink)
    assert isinstance(
        parse_deep_link("http://tenant.example.com/record/Rec123",
                        allow_host="example.com"),
        NotADeepLink,
    )


@pytest.mark.conformance
def test_the_shipped_guide_states_the_host_and_scheme_policy():
    """Divergence C1's corpus half: the policy was real, unwritten and unpinned, so a
    reader rebuilding the parser from the corpus had no way to know it existed."""
    from larkdocio import guide

    text = guide(full=True)
    missing = [f for f in HOST_POLICY_FRAGMENTS if f not in text]
    assert missing == [], (
        "the guide's deep-link section no longer states the host/scheme policy: "
        f"{missing}")


# --------------------------------------------------------------------------- #
# Query pass-through fidelity — the regeneration spike's divergence C2.        #
#                                                                               #
# The promise is written twice in the library's own source — `parse_deep_link`'s #
# docstring ("**Pass-through fidelity is the contract.** The ``share_token``,    #
# the ``rangeId``, the ``rangeVer`` and the record token are returned            #
# **exactly** as they arrived — not normalised, lower-cased, split, re-encoded   #
# or validated.") and the inline reason at the parse itself ("Parse the raw      #
# query WITHOUT urllib's percent-decoding so every value is the exact input      #
# slice (pass-through fidelity)."). Written and untested is the worst pairing:   #
# a regeneration using `urllib.parse.parse_qs` turned `abc_OP%2Fq` into          #
# `abc_OP/q` and every gate stayed green.                                        #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_a_percent_encoded_range_id_is_carried_VERBATIM_not_decoded():
    """Divergence C2, verbatim: `rangeId=abc_OP%2Fq` stays `abc_OP%2Fq`. Decoding it —
    which is what `parse_qs` does — silently rewrites an opaque server-side token."""
    url = (f"{HOST}/sheets/SheetScratchExample00000001"
           "?sheet=abc&rangeId=abc_OP%2Fq&rangeVer=7")
    got = parse_deep_link(url)
    assert got == SheetAnchor(
        spreadsheet_token="SheetScratchExample00000001",
        sheet_id="abc",
        range_id="abc_OP%2Fq",
        range_ver="7",
    )
    assert "%2F" in got.range_id and "/" not in got.range_id


@pytest.mark.conformance
@pytest.mark.parametrize("encoded", ["7pg9wE%2B", "a%20b", "%3Dtail", "MiXeD%2Fcase"])
def test_every_query_value_is_the_exact_input_slice(encoded):
    """The contract names the sheet id and the rangeVer too, not only the rangeId."""
    url = f"{HOST}/sheets/TOK?sheet={encoded}&rangeId={encoded}&rangeVer={encoded}"
    got = parse_deep_link(url)
    assert (got.sheet_id, got.range_id, got.range_ver) == (encoded, encoded, encoded)


@pytest.mark.conformance
def test_the_pass_through_promise_is_WRITTEN_where_the_parse_happens():
    """The promise being pinned above is a shipped docstring, not a test's invention —
    if the wording goes, the pin has lost the thing it defends."""
    doc = parse_deep_link.__doc__ or ""
    assert "Pass-through fidelity is the contract." in doc
    assert "exactly** as they arrived" in doc


# --------------------------------------------------------------------------- #
# AC1 — validate_download_url is UNCHANGED, and the two cross-reference          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://foo.feishu.cn/docx/AbC123", ("feishu.cn", "docx", "AbC123")),
        ("https://x.larksuite.com/wiki/WkT0ken", ("larksuite.com", "wiki", "WkT0ken")),
        ("https://x.larksuite.com/sheets/ShT0ken", ("larksuite.com", "sheets", "ShT0ken")),
        ("https://x.larksuite.com/base/BsT0ken", ("larksuite.com", "base", "BsT0ken")),
        ("https://x.larksuite.com/drive/folder/FldTok", ("larksuite.com", "drive", "FldTok")),
    ],
)
@pytest.mark.conformance
def test_validate_download_url_return_unchanged(url, expected):
    assert validate_download_url(url) == expected


def test_validate_download_url_refusal_text_unchanged():
    with pytest.raises(ValueError) as exc:
        validate_download_url("https://example.com/not-a-lark-url")
    msg = str(exc.value)
    assert "not a recognised Lark URL" in msg
    assert "docs|docx|wiki|sheets|base|drive/folder" in msg


def test_validate_download_url_signature_unchanged():
    params = list(inspect.signature(validate_download_url).parameters)
    assert params == ["raw_url", "allow_host"]


def test_the_two_functions_cross_reference_each_other():
    assert "parse_deep_link" in (validate_download_url.__doc__ or "")
    assert "validate_download_url" in (parse_deep_link.__doc__ or "")
