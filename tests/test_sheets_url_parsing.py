"""The validator recognises a SHEETS and a BASE url and names its type (LD-183).

One gap seen from two sides, so one test module:

* the landed recommendation — accept ``/sheets/`` and ``/base/`` in the validator and return
  their type, making the sheets recipes symmetric with the docx ones — and
* the consumer critique's ask for a sheets-url parser and a deduplicated guide: the guide
  carried the same two-line URL→token expression in **both** sheets entry points because
  no parser existed to reference.

**One validator, not a twin.** A separate ``parse_sheets_url`` accessor would be a second
definition of the same parse, and the type discriminator the existing three-part return
already carries is what makes the sheets recipes symmetric with the docx ones. The absence
of that twin is asserted here, so it cannot arrive later by accident.

**What must not move.** The previously-accepted set and the ``ValueError`` type are
load-bearing and pinned by the recipe-completion module's own acceptance test, which passes
untouched. This module widens **path** shapes only — never host policy — and the download
path keeps refusing a spreadsheet, now by naming the surface that reads one.

**Accepting ``/base/`` was URL-type recognition and nothing else** — this issue built no Base
capability of its own, which is asserted below rather than promised. It never was a claim
that no Base surface would ever exist: the Base ladder has since shipped five of them, so the
fence is "this URL change added nothing", and the download path's refusal now **routes** a
Base URL at ``larkdocio.base.read_base_markdown`` instead of denying the surface (LD-279).
"""
import re
import urllib.parse

import pytest

from larkdocio.common import (
    DOCUMENT_URL_TYPES,
    URL_PATH_SHAPES,
    URL_TYPE_SURFACES,
    validate_download_url,
)


# --------------------------------------------------------------------------- #
# AC1 — the parse, table-tested across every axis that has ever varied.        #
# --------------------------------------------------------------------------- #

#: ``(url, allow_host, expected (domain, type, token))`` — the whole accepted surface in one
#: table, because every one of these axes has been a real bug or a real consumer question:
#: the tenant subdomain, the bare host, the two API domains, the opt-in extra host, a query
#: string, a trailing slash, and now the two newly-recognised path shapes.
_ACCEPTED = [
    # the three document shapes — unchanged, and still returning what they returned.
    ("https://your-domain.larksuite.com/docx/ABC123", "", ("larksuite.com", "docx", "ABC123")),
    ("https://x.feishu.cn/wiki/WIK1", "", ("feishu.cn", "wiki", "WIK1")),
    ("https://x.feishu.cn/docs/DOC1", "", ("feishu.cn", "docs", "DOC1")),
    ("https://larksuite.com/docx/BARE1", "", ("larksuite.com", "docx", "BARE1")),
    ("https://tenant.example.com/docx/T1", "example.com", ("example.com", "docx", "T1")),
    # …and the two this issue adds, over the same axes.
    ("https://your-domain.larksuite.com/sheets/Shtcn1234567890", "",
     ("larksuite.com", "sheets", "Shtcn1234567890")),
    ("https://your-domain.larksuite.com/sheets/Shtcn1234567890?sheet=3bf016", "",
     ("larksuite.com", "sheets", "Shtcn1234567890")),
    ("https://x.feishu.cn/sheets/Shtcn1/", "", ("feishu.cn", "sheets", "Shtcn1")),
    ("https://feishu.cn/sheets/Shtcn2", "", ("feishu.cn", "sheets", "Shtcn2")),
    ("https://x.feishu.cn/base/BasABC", "", ("feishu.cn", "base", "BasABC")),
    ("https://your-domain.larksuite.com/base/BasXYZ?table=tbl1&view=vew1", "",
     ("larksuite.com", "base", "BasXYZ")),
    ("https://tenant.example.com/sheets/S1", "example.com", ("example.com", "sheets", "S1")),
]


@pytest.mark.parametrize("url,allow_host,expected", _ACCEPTED)
@pytest.mark.conformance
def test_ac1_the_validator_parses_every_accepted_shape(url, allow_host, expected):
    """AC1: the existing three-part return shape gains the new types — same function, same
    tuple, one more value in its middle slot."""
    assert validate_download_url(url, allow_host) == expected


@pytest.mark.conformance
def test_ac1_the_discriminator_table_is_reachable_from_the_package_seam():
    """AC1: the table is exported beside the function it describes, so a caller routing on the
    returned type imports both from one place instead of reaching into a submodule."""
    import larkdocio.common as common
    from larkdocio.common import url as url_module

    for name in ("DOCUMENT_URL_TYPES", "URL_TYPE_SURFACES"):
        assert name in common.__all__, name
        assert getattr(common, name) is getattr(url_module, name)


@pytest.mark.conformance
def test_ac1_the_returned_type_is_the_discriminator_the_recipes_branch_on():
    """AC1: the middle value is a **usable discriminator**, not a label — it keys the
    surface table, which is what lets a caller route a URL without re-parsing it."""
    for url, _allow, (_domain, doc_type, _token) in _ACCEPTED:
        assert doc_type in URL_TYPE_SURFACES, (url, doc_type)

    assert URL_TYPE_SURFACES["sheets"] == "sheets"
    assert URL_TYPE_SURFACES["base"] == "base"
    for document_type in DOCUMENT_URL_TYPES:
        assert URL_TYPE_SURFACES[document_type] == "docx"
    # and the two axes agree: exactly the document types are the docx-surface ones.
    assert {t for t, s in URL_TYPE_SURFACES.items() if s == "docx"} == set(DOCUMENT_URL_TYPES)


def test_ac1_there_is_no_second_parser_entry_point():
    """AC1's documented call, mechanized: **one** validator names the type. A
    ``parse_sheets_url`` twin would be a second definition of the same parse, and the way to
    keep it from arriving is to assert its absence rather than to write it down."""
    import larkdocio
    import larkdocio.common as common
    import larkdocio.common.url as url_module
    import larkdocio.sheets as sheets

    for module in (larkdocio, common, url_module, sheets):
        assert not hasattr(module, "parse_sheets_url"), module.__name__
        for name in dir(module):
            assert "parse_sheets_url" not in name, (module.__name__, name)


# --------------------------------------------------------------------------- #
# AC2 — the previously-accepted set and the error type do not move.            #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac2_rejection_still_raises_the_same_builtin_error_type():
    """AC2: still a builtin ``ValueError`` — its established, tested contract. A typed
    error would be a break for every caller that catches this one."""
    with pytest.raises(ValueError):
        validate_download_url("https://evil.example.org/docx/ABC")


@pytest.mark.parametrize("url", [
    "https://evil.example.org/docx/ABC",          # host outside the accepted set
    "https://x.feishu.cn/minutes/MIN1",           # a path shape nobody claims
    "https://x.feishu.cn/drive/FLD1",             # drive WITHOUT the folder segment
    "https://x.feishu.cn/drive/folder/",          # the folder shape with NO token
    "https://x.feishu.cn/drive/file/FIL1",        # a drive shape this library does not claim
    "https://x.feishu.cn/sheets/",                # a sheets url with NO token
    "https://x.feishu.cn/sheets",                 # …not even the segment
    "https://x.feishu.cn/base/",                  # the same, for base
    "http://x.feishu.cn/docx/ABC",                # not https
    "https://x.feishu.cn/SHEETS/Shtcn1",          # the path segment is case-sensitive
])
@pytest.mark.conformance
def test_ac2_what_was_refused_is_still_refused(url):
    """AC2: this issue widens **path** shapes, not host policy and not tokenless URLs —
    a widening that swallowed a genuinely-wrong URL would be the regression."""
    with pytest.raises(ValueError):
        validate_download_url(url)


@pytest.mark.conformance
def test_ac2_the_extra_host_stays_opt_in():
    """AC2 / § Out of Scope: ``allow_host`` remains the only way to widen the host set, and
    it widens it for the new path shapes exactly as it did for the old ones."""
    with pytest.raises(ValueError):
        validate_download_url("https://tenant.example.com/sheets/S1")
    assert validate_download_url(
        "https://tenant.example.com/sheets/S1", "example.com")[0] == "example.com"


# --------------------------------------------------------------------------- #
# AC4 — the refusal message stays as good as it was made, and says more.       #
# --------------------------------------------------------------------------- #

#: The ``<a|b|c>`` enumeration inside the refusal message — the only ``<…>`` group carrying
#: pipes, which is what distinguishes it from ``<host>`` and ``<token>``.
_ENUMERATION_RE = re.compile(r"<([a-z/]+(?:\|[a-z/]+)+)>")


def _refusal_message():
    with pytest.raises(ValueError) as exc:
        validate_download_url("https://x.feishu.cn/minutes/MIN1")
    return str(exc.value)


def test_ac4_the_refusal_message_lists_every_accepted_shape():
    """AC4: for a URL that is genuinely wrong the message still names **what is accepted**
    — and now that the accepted set is wider, it names the wider set. A message that still
    said a spreadsheet URL is refused would be worse than the one it replaced.

    **LD-210 AC4 — asserted on the ENUMERATION, not on substrings.** The substring form was
    loose to the point of being decorative: ``docx`` / ``wiki`` / ``sheets`` / ``base`` each
    appear TWICE in the message (once in the enumeration, once in the trailing prose sentence),
    so dropping any of the four from the **enumeration** left the whole suite green — only
    ``docs``, with a single occurrence, was tightly pinned. The shipped message was and is
    correct; this is guard tightness. The enumeration is now parsed out and held against
    :data:`URL_TYPE_SURFACES` itself, so a token dropped from the list reddens even though the
    prose still says the word — and a new recognised URL type that never reaches the message
    reddens too.
    """
    message = _refusal_message()
    enumerations = _ENUMERATION_RE.findall(message)
    assert len(enumerations) == 1, (
        f"expected exactly one <a|b|c> path-shape enumeration in the refusal message, found "
        f"{enumerations}"
    )
    # LD-323 — held against the PATH-SHAPE table, which is what the message actually
    # enumerates. The two tables were one list until a Drive folder arrived at the two-segment
    # path ``drive/folder`` while reporting the one-word type ``drive``; comparing the message's
    # shapes against the *type* table would force the message to advertise a path
    # (``/drive/<token>``) that does not exist.
    assert enumerations[0].split("|") == list(URL_PATH_SHAPES), (
        f"the refusal message enumerates {enumerations[0].split('|')} while the recognised URL "
        f"path shapes are {list(URL_PATH_SHAPES)} — the message must list the real accepted "
        f"set, in its order"
    )
    assert set(URL_PATH_SHAPES.values()) == set(URL_TYPE_SURFACES), (
        "every accepted path shape must report a type the surface table knows, and every known "
        "type must be reachable from some accepted shape"
    )
    assert "allowHost" in message, "allowHost is the real public flag name"
    assert "feishu.cn" in message and "larksuite.com" in message


def test_ac4_the_message_no_longer_teaches_a_hand_rolled_parse():
    """AC4: the two lines the message used to teach were a workaround for this function not
    accepting the URL. It accepts it now, so teaching the workaround would send a consumer
    to hand-roll a parse the library performs."""
    with pytest.raises(ValueError) as exc:
        validate_download_url("https://x.feishu.cn/minutes/MIN1")
    message = str(exc.value)
    assert "urlparse" not in message, message
    assert "split('/')" not in message, message


def test_ac4_the_message_says_what_a_recognised_type_does_NOT_buy_you():
    """AC4: recognising a URL is not the same as being able to read what it points at, and
    the message is where a consumer meets that distinction."""
    with pytest.raises(ValueError) as exc:
        validate_download_url("https://x.feishu.cn/minutes/MIN1")
    assert "download" in str(exc.value).lower()


# --------------------------------------------------------------------------- #
# The download path — the refusal MOVES rather than disappearing.              #
# --------------------------------------------------------------------------- #

def test_a_spreadsheet_url_is_refused_by_the_DOWNLOAD_path_naming_the_read_surface():
    """The validator now recognises a spreadsheet URL, so the guard that keeps a document
    download from being handed one moves to the download path — where the unsupported legacy
    document type is already refused. The message names the surface that DOES read a
    spreadsheet, which the old bare validation error could not."""
    from larkdocio.errors import LarkConfigError
    from larkdocio.read.download import _resolve_doc

    with pytest.raises(LarkConfigError) as exc:
        _resolve_doc("https://x.feishu.cn/sheets/Shtcn1", "", None, "id", "secret")
    message = str(exc.value)
    assert "sheets" in message.lower()
    assert "SheetsReadClient" in message, message


def test_a_base_url_is_refused_by_the_download_path_and_ROUTED_at_the_base_reader():
    """The download still refuses a ``/base/`` URL — it reads documents — but the refusal
    now names the call that DOES read a Base.

    This test used to assert the opposite (``…_promises_no_base_surface``), and stayed green
    for five shipped Base surfaces because it only checked that the word "base" appeared. The
    claim-level guard is ``tests/test_base_surface_claim_is_gone.py``; this is the behavioral
    half, at the one place a consumer meets the message.
    """
    from larkdocio.errors import LarkConfigError
    from larkdocio.read.download import _resolve_doc

    with pytest.raises(LarkConfigError) as exc:
        _resolve_doc("https://x.feishu.cn/base/BasABC", "", None, "id", "secret")
    message = str(exc.value)
    assert "base" in message.lower()
    assert "read_base_markdown" in message, (
        "refusing without routing is what made the reader-era copy wrong: the surface exists")
    assert "SheetsReadClient" not in message, (
        "a Base is not a spreadsheet — pointing a Base URL at the sheets reader would be a "
        "wrong answer confidently given")


def test_no_base_surface_exists_anywhere_this_issue_could_have_leaked_one():
    """§ Out of Scope, asserted rather than promised: accepting ``/base/`` as a recognised
    URL type is the whole of **this** issue — no read, no write, no client, no capability
    surface came out of it.

    **LD-246 update.** ``larkdocio.base`` now EXISTS on purpose (the Base read spec's cell-renderer
    registry), so "the module cannot be imported" is no longer the right assertion — it
    would only be recording that Base is unbuilt, which is no longer true and would redden
    the day it was built regardless of whether LD-183 leaked anything. What this guard is
    actually for survives intact and is checked instead: LD-183 shipped **no reachable
    Base surface** — ``capabilities()`` still reports none (that is LD-251's job), the
    package re-exports nothing from ``larkdocio``, and the URL parse remains the only
    Base-aware thing the *sheets* surface does.

    **LD-248 update — the narrowing this issue's fence was always about.** The Base package
    now DOES re-export a public read surface, which is that story's whole point, so
    "``larkdocio.base`` exports nothing" has stopped being a statement about LD-183 and
    become a statement about how far the Base ladder has climbed. It is replaced by the two
    assertions that still belong to **this** issue and are the ones a leak would trip:
    accepting ``/base/`` as a URL type bought **no top-level re-export** and **no
    ``capabilities()`` surface** — the front door is LD-251's close-out, and the Base
    package's own exports are checked against its declared ``__all__`` by its own story's
    tests, not by this one.
    """
    import larkdocio

    # **LD-251 update — the fence's capabilities() half is DISCHARGED, by the story it named.**
    # This guard's remaining business is that accepting ``/base/`` as a URL type bought nothing
    # by itself: the Base surfaces exist because the Base ladder built them and the close-outs
    # published them.
    # **LD-260 update.** A fourth surface landed — the record-write engine — so "every Base
    # surface is read-only" has stopped being a statement about LD-183 and become a statement
    # about how far the ladder has climbed. What still belongs to THIS issue is that a
    # URL-parsing change produced no surface of its own: the set is exactly the four the Base
    # stories built, each carrying the mode its own story shipped.
    base_surfaces = {sid: s for sid, s in larkdocio.capabilities(full=True)["surfaces"].items()
                     if "base" in sid}
    assert {sid: s["mode"] for sid, s in base_surfaces.items()} == {
        "base-read": "read", "base-comments-read": "read",
        "base-embedded-deep-read": "read", "base-write": "write",
        "base-schema-write": "write"}
    # (``dir(larkdocio)`` gains the bare submodule NAME once anything imports it — that is
    # Python's own binding, not a re-export. What must stay empty is the export list.)
    assert not [name for name in getattr(larkdocio, "__all__", ()) if "base" in name.lower()]


# --------------------------------------------------------------------------- #
# AC5 — split_compound_token is a DIFFERENT problem, and stays one.            #
# --------------------------------------------------------------------------- #

def test_ac5_split_compound_token_is_not_a_url_parser():
    """AC5: ``split_compound_token`` splits an **embedded-sheet compound token**
    (``<spreadsheet_token>_<sheet_id>``) on its last underscore. It is not this parse and
    must never be merged with it — the same merge hazard a sibling pair of near-identically
    named text helpers already carries a guard for.

    Proven from both sides: the compound splitter cannot parse a URL, and the URL validator
    cannot split a compound token."""
    from larkdocio.sheets.embed import split_compound_token

    # a URL is not a compound token: no usable spreadsheet/sheet split comes out of one.
    url = "https://x.feishu.cn/sheets/Shtcn1"
    assert split_compound_token(url) is None or "/" in split_compound_token(url)[0]
    # a compound token is not a URL: the validator refuses it outright.
    with pytest.raises(ValueError):
        validate_download_url("Shtcn1234567890_3bf016")
    # and the compound splitter does what it is for.
    assert split_compound_token("Shtcn1234567890_3bf016") == ("Shtcn1234567890", "3bf016")


def test_ac5_the_distinction_is_recorded_where_the_two_could_be_merged():
    """AC5: the record is in the code, not only in a test name — both docstrings say which
    problem they solve, so a later reader consolidating "the two token parsers" is stopped
    by the source rather than by a test failure they might delete."""
    from larkdocio.common import url as url_module
    from larkdocio.sheets import embed

    compound = embed.split_compound_token.__doc__
    assert "not" in compound.lower() and "url" in compound.lower(), (
        "split_compound_token's docstring must say it is not the URL parse")
    assert "split_compound_token" in url_module.validate_download_url.__doc__, (
        "the validator's docstring must name the helper it must not be merged with")


# --------------------------------------------------------------------------- #
# AC3 — the guide dedupe changed the words, not the token.                      #
# --------------------------------------------------------------------------- #

_TOKEN_URL = "https://your-domain.larksuite.com/sheets/Shtcn1234567890?sheet=3bf016"


@pytest.mark.conformance
def test_ac3_the_shipped_call_yields_exactly_what_the_old_two_liner_yielded():
    """AC3: the dedupe is behavior-preserving, proven by comparison rather than by
    inspection — the recipe's new expression and the hand-rolled expression it replaced
    produce the same token for the same input, query string included."""
    hand_rolled = urllib.parse.urlparse(_TOKEN_URL).path.rstrip("/").split("/")[-1]
    _domain, doc_type, token = validate_download_url(_TOKEN_URL)
    assert token == hand_rolled == "Shtcn1234567890"
    assert doc_type == "sheets"


@pytest.mark.conformance
def test_ac3_the_shipped_call_also_hands_back_the_domain_the_hand_rolled_one_could_not():
    """AC3: the dedupe is a strict improvement, not a wash. Both sheets recipes carry a
    comment warning that the API domain is not the tenant host in the URL — and the
    hand-rolled expression could not produce the domain at all, so the recipes hard-coded
    it beside a URL that disagreed with it."""
    domain, _type, _token = validate_download_url(_TOKEN_URL)
    assert domain == "larksuite.com"
    assert domain not in ("your-domain.larksuite.com",)
