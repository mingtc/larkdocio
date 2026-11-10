"""LD-324 — the Drive folder **enumeration client** (the Drive spec § F1 § S2).

Offline, against fixtures **derived from the committed captures** (``tests/drive_fixtures.py``
carries the per-builder provenance). What is pinned here, one region per AC:

* **AC1** the listing leg and its nine-field child shape, with each child's ``url`` carried
  through verbatim — the field that makes the shipped docx reader reachable without
  synthesising a URL;
* **AC2** pagination to exhaustion on an **opaque** token: echoed, never parsed, and the three
  termination conditions that stop a spin;
* **AC5** the ``1061002`` refusal, which names both possibilities and diagnoses neither, and
  stays distinct from ``1061003``;
* **AC6** ``option`` — and ``order_by`` / ``direction`` — never sent, on every code path;
* **AC7** the two non-SDK legs on the existing raw-HTTP core, and the name leg's degrade;
* **AC9** READ credentials only, throttled on the shipped path;
* **AC10** GET-only by construction, plus the one declared query ``POST``.

The walker's own ACs (AC3 recursion + visited-set, AC4 the disclosed caps) are in
``tests/test_drive_walk.py``.
"""
import inspect
import pathlib

import pytest

import drive_fixtures as fx
from larkdocio.common.transport import RateLimiter
from larkdocio.drive import ops
from larkdocio.drive.client import (
    DEFAULT_MAX_PAGES,
    DEFAULT_PAGE_SIZE,
    DriveClient,
)
from larkdocio.drive.errors import (
    REFUSAL_SENTENCE,
    DriveObjectNotFoundError,
    FolderRefusedError,
    PaginationStalledError,
)
from larkdocio.errors import LarkConfigError

DRIVE_PACKAGE = pathlib.Path(inspect.getfile(ops)).parent


def client(route, **kwargs):
    """A client whose whole transport is a recording stub — no network, real request shapes."""
    transport = fx.RecordingTransport(route)
    kwargs.setdefault("token_fetcher", fx.token_fetcher)
    kwargs.setdefault("rate_limiter", fx.fast_limiter())
    return DriveClient("app-id", "app-secret", urlopen=transport, **kwargs), transport


class CountingLimiter(RateLimiter):
    """The real limiter, counting acquisitions — so "throttled" is observed, not assumed."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.acquisitions = 0

    def acquire(self):
        self.acquisitions += 1
        return super().acquire()


# --------------------------------------------------------------------------- #
# AC1 — the listing leg, against the captured response shape.                   #
# --------------------------------------------------------------------------- #

def test_ac1_the_fixtures_are_DERIVED_FROM_THE_COMMITTED_CAPTURES():
    """Provenance first: if the evidence base moves, these tests must move with it."""
    assert (fx.CAPTURES / fx.LISTING_CAPTURE).exists()
    assert fx.listing_capture()["_endpoint"] == "/open-apis/drive/v1/files"
    assert fx.listing_capture()["_lark_code"] == 0
    assert len(fx.listing_children()) == 9


def test_ac1_all_NINE_captured_fields_survive_parsing():
    listings = {"fldrROOT": fx.listing_response()}
    drive, _t = client(fx.listing_router(listings))
    contents = drive.list_folder_children("fldrROOT")

    assert len(contents.children) == 9
    for parsed, raw in zip(contents.children, fx.listing_children()):
        for field in fx.CHILD_FIELDS:
            assert getattr(parsed, field) == raw.get(field), field


def test_ac1_the_childs_URL_is_carried_through_VERBATIM():
    """The listing hands over a ready-to-use ``url`` — the single field that makes the shipped
    docx reader reachable without synthesising one. A client that drops it makes LD-325
    impossible, so it is pinned rather than assumed."""
    listings = fx.real_tree_listings()
    drive, _t = client(fx.listing_router(listings))
    contents = drive.list_folder_children(fx.real_tree_root())

    assert contents.children
    for child in contents.children:
        assert child.url, f"{child.token} lost its url"
        assert child.url == _raw_url(child.token)


def _raw_url(token):
    for node in fx.real_tree()["nodes"]:
        if node["token"] == token:
            return node["url"]
    raise AssertionError(token)


def test_ac1_the_raw_type_string_is_carried_through_UNTOUCHED():
    """The ``type``→reader translation is LD-325's (the ``sheet``/``bitable`` seam). This
    client must not pre-translate: it carries Lark's own word."""
    drive, _t = client(fx.listing_router({"f": fx.listing_response()}))
    types = {child.type for child in drive.list_folder_children("f").children}
    assert types == {row["type"] for row in fx.listing_children()}
    assert types <= {"docx", "sheet", "bitable", "folder", "shortcut", "file"}


# --------------------------------------------------------------------------- #
# AC2 — pagination to exhaustion, on an OPAQUE token.                           #
# --------------------------------------------------------------------------- #

def _paged_router(page1, page2, folder="fldrPAGED"):
    def answer(call):
        return page2 if call.params.get("page_token") else page1

    return fx.listing_router({folder: answer})


def test_ac2_the_loop_pages_to_exhaustion_and_returns_every_child_in_order():
    page1, page2, expected = fx.pagination_pages()
    drive, transport = client(_paged_router(page1, page2))

    contents = drive.list_folder_children_to_exhaustion("fldrPAGED")

    assert [c.token for c in contents.children] == expected
    assert contents.pages == 2
    assert len(transport.calls) == 2
    assert contents.truncation is None


def test_ac2_THE_FIRST_PAGE_IS_NEVER_THE_FOLDER():
    """The negative control for the test above: one page is a page, not the folder."""
    page1, page2, expected = fx.pagination_pages()
    drive, _t = client(_paged_router(page1, page2))
    first = drive.list_folder_children("fldrPAGED")
    assert first.has_more is True
    assert [c.token for c in first.children] != expected


def test_ac2_no_dupes_and_no_gaps_across_the_two_captured_pages():
    """Capture 12's own proven properties, reproduced offline: zero token overlap between
    pages, and page 1 + page 2 = the folder's full child set."""
    page1, page2, expected = fx.pagination_pages()
    drive, _t = client(_paged_router(page1, page2))
    tokens = [c.token for c in drive.list_folder_children_to_exhaustion("fldrPAGED").children]

    assert len(tokens) == len(set(tokens)), "a duplicate crossed the page boundary"
    assert set(tokens) == set(expected), "a child fell into the gap between pages"
    first = {c["token"] for c in page1["data"]["files"]}
    second = {c["token"] for c in page2["data"]["files"]}
    assert first & second == set()


@pytest.mark.parametrize("token", [
    fx.opaque_page_token(),
    "1234567890",            # numeric-LOOKING: still opaque, still echoed
    "a+b/c=d==",             # base64-ish punctuation must survive urlencoding
    "  leading and trailing  ",
])
def test_ac2_the_page_token_is_ECHOED_VERBATIM_and_never_parsed(token):
    """The token is opaque (135 chars, non-numeric in capture 12). The client echoes what it
    was given: it never parses, increments or reconstructs it — so a token of any shape flows
    through unchanged and the page sequence is unaffected by its content."""
    page1, page2, expected = fx.pagination_pages()
    page1 = fx.page(page1["data"]["files"], has_more=True, next_page_token=token)
    drive, transport = client(_paged_router(page1, page2))

    contents = drive.list_folder_children_to_exhaustion("fldrPAGED")

    assert [c.token for c in contents.children] == expected
    assert transport.calls[1].params["page_token"] == token


def test_ac2_the_client_source_NEVER_INSPECTS_the_tokens_CONTENT():
    """The structural half of the property above: no arithmetic, no slicing, no int() and no
    comparison against a shape anywhere near the cursor."""
    source = (DRIVE_PACKAGE / "client.py").read_text(encoding="utf-8")
    for forbidden in ("int(page_token", "page_token[", "page_token +", "len(page_token)",
                      "page_token.isdigit", "page_token.split"):
        assert forbidden not in source, f"the client inspects the opaque cursor: {forbidden}"


def test_ac2_TERMINATION_a_repeated_token_raises_rather_than_spinning():
    token = fx.opaque_page_token()
    stuck = fx.page(fx.listing_children()[:1], has_more=True, next_page_token=token)
    drive, transport = client(fx.listing_router({"f": stuck}))

    with pytest.raises(PaginationStalledError) as excinfo:
        drive.list_folder_children_to_exhaustion("f")

    assert "repeated" in str(excinfo.value).lower()
    assert len(transport.calls) <= 3, "it must notice on the repeat, not grind to a cap"


def test_ac2_TERMINATION_has_more_with_NO_token_raises():
    broken = fx.page(fx.listing_children()[:2], has_more=True)
    drive, _t = client(fx.listing_router({"f": broken}))

    with pytest.raises(PaginationStalledError) as excinfo:
        drive.list_folder_children_to_exhaustion("f")

    assert "no next_page_token" in str(excinfo.value)


def test_ac2_TERMINATION_an_empty_page_that_claims_more_raises():
    empty = fx.page([], has_more=True, next_page_token=fx.opaque_page_token())
    drive, _t = client(fx.listing_router({"f": empty}))

    with pytest.raises(PaginationStalledError) as excinfo:
        drive.list_folder_children_to_exhaustion("f")

    assert "empty page" in str(excinfo.value)


def test_ac2_an_EMPTY_FOLDER_is_not_a_stall():
    """The must-not-bite: zero children with ``has_more: false`` is an empty folder, and an
    empty folder is an answer."""
    drive, _t = client(fx.listing_router({"f": fx.page([])}))
    contents = drive.list_folder_children_to_exhaustion("f")
    assert contents.children == () and contents.truncation is None


def test_ac2_the_PAGE_BUDGET_is_a_DISCLOSED_truncation_not_a_silent_stop():
    def endless(call):
        return fx.page(
            [fx.child_payload(f"t{len(call.params.get('page_token', ''))}-{id(call)}", "f")],
            has_more=True, next_page_token=fx.opaque_page_token() + str(id(call)))

    drive, _t = client(fx.listing_router({"f": endless}))
    contents = drive.list_folder_children_to_exhaustion("f", max_pages=3)

    assert contents.pages == 3
    assert contents.truncation is not None
    assert contents.truncation.cap == "max_pages"
    assert contents.truncation.limit == 3
    assert "f" in contents.truncation.at_folder


def test_ac2_the_documented_defaults_are_real_and_finite():
    assert DEFAULT_PAGE_SIZE == 50 and 0 < DEFAULT_PAGE_SIZE <= 200
    assert isinstance(DEFAULT_MAX_PAGES, int) and DEFAULT_MAX_PAGES > 0
    doc = inspect.getdoc(DriveClient.list_folder_children_to_exhaustion)
    assert str(DEFAULT_MAX_PAGES) in doc


# --------------------------------------------------------------------------- #
# AC5 — the 1061002 refusal names both possibilities and guesses neither.       #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("cause", sorted(fx.REFUSAL_CAPTURES))
def test_ac5_every_captured_1061002_cause_raises_the_SAME_honest_refusal(cause):
    """Three distinct causes, one code, one refusal — captures 04, 13 and 14."""
    drive, _t = client(fx.listing_router({}, refusals={"f": fx.refusal_response(cause)}))

    with pytest.raises(FolderRefusedError) as excinfo:
        drive.list_folder_children("f")

    assert excinfo.value.code == 1061002
    assert REFUSAL_SENTENCE in str(excinfo.value)


def test_ac5_the_refusal_names_BOTH_possibilities_and_DIAGNOSES_NEITHER():
    message = REFUSAL_SENTENCE
    assert "1061002" in message
    assert "may not exist" in message
    assert "may not have access" in message
    assert "does not guess" in message
    lowered = message.lower()
    for diagnosis in ("does not exist", "no such folder", "not found",
                      "you do not have access", "permission denied"):
        assert diagnosis not in lowered, (
            f"the refusal presents {diagnosis!r} as the diagnosis; nothing in the response "
            "establishes which of the three causes applied")


def test_ac5_the_error_carries_the_THREE_CAUSES_as_data_with_their_captures():
    drive, _t = client(fx.listing_router({}, refusals={"f": fx.refusal_response()}))
    with pytest.raises(FolderRefusedError) as excinfo:
        drive.list_folder_children("f")
    causes = excinfo.value.causes
    assert len(causes) == 3
    for _cause, capture_name in causes:
        assert (fx.CAPTURES / capture_name).exists(), capture_name


def test_ac5_1061003_KEEPS_ITS_OWN_TYPE_and_is_not_conflated():
    """``1061003`` is the family's captured not-found code (``larkdocio.base.media``). It is a
    different answer and it keeps a different type; folding it into the 1061002 refusal would
    throw away the one drive code that DOES distinguish something."""
    drive, _t = client(fx.listing_router({}, refusals={"f": fx.not_found_response()}))

    with pytest.raises(DriveObjectNotFoundError) as excinfo:
        drive.list_folder_children("f")

    assert excinfo.value.code == 1061003
    assert not isinstance(excinfo.value, FolderRefusedError)
    assert REFUSAL_SENTENCE not in str(excinfo.value)


# --------------------------------------------------------------------------- #
# AC6 — `option` is never sent. Nor `order_by` / `direction`.                   #
# --------------------------------------------------------------------------- #

#: Every query parameter this client is allowed to put on the wire.
_ALLOWED_PARAMS = {"folder_token", "page_size", "page_token", "user_id_type"}


def test_ac6_NO_CODE_PATH_sends_option_order_by_or_direction():
    """Exercised over every call path the client has: a single page, a paged exhaustion, the
    root-folder leg and the name leg."""
    page1, page2, _expected = fx.pagination_pages("fldrPAGED")
    listings = dict(fx.real_tree_listings())

    def answer(call):
        return page2 if call.params.get("page_token") else page1

    listings["fldrPAGED"] = answer
    drive, transport = client(fx.listing_router(
        listings, root_token=fx.real_tree_root(),
        metas=fx.folder_meta_response(fx.real_tree_root(), "Root")))

    drive.list_folder_children(fx.real_tree_root())
    drive.list_folder_children_to_exhaustion("fldrPAGED")
    drive.root_folder_token()
    drive.folder_name(fx.real_tree_root())

    assert len(transport.calls) >= 5
    for call in transport.calls:
        assert "option" not in call.params, call.url
        assert "order_by" not in call.params, call.url
        assert "direction" not in call.params, call.url
        assert set(call.params) <= _ALLOWED_PARAMS, call.url
        assert set(call.body or {}) <= {"request_docs", "with_url"}, call.body


def test_ac6_the_word_option_is_not_even_a_PARAMETER_of_the_shipped_client():
    """The decision is pinned in the signature too, so a later contributor meets it rather
    than adding a parameter that silently reshapes pagination (the Drive spec § O6)."""
    for method in (DriveClient.list_folder_children,
                   DriveClient.list_folder_children_to_exhaustion):
        params = set(inspect.signature(method).parameters)
        assert not params & {"option", "order_by", "direction"}, method


def test_ac6_the_client_records_WHY_it_never_sends_option():
    source = (DRIVE_PACKAGE / "client.py").read_text(encoding="utf-8")
    assert "14-option-param.json" in source
    assert "1061002" in source


# --------------------------------------------------------------------------- #
# AC7 — the two non-SDK legs ride the existing raw-HTTP core.                    #
# --------------------------------------------------------------------------- #

def test_ac7_the_client_IS_a_CredentialedRawHttpClient_no_new_infrastructure():
    from larkdocio.common.transport import CredentialedRawHttpClient

    assert issubclass(DriveClient, CredentialedRawHttpClient)


def test_ac7_the_root_folder_leg_answers_the_bots_own_root():
    drive, transport = client(fx.listing_router({}, root_token="nodlROOTTOKEN"))
    assert drive.root_folder_token() == "nodlROOTTOKEN"
    assert transport.calls[0].path == "/open-apis/drive/explorer/v2/root_folder/meta"
    assert transport.calls[0].method == "GET"


def test_the_root_folder_leg_answers_a_TYPED_token_that_the_fence_can_refuse():
    """LD-581. The accessor's own value is the one that reproduced the measured harm, so it
    comes back marked: a ``str`` subclass every string use still accepts, and the only thing
    ``require_destination`` can refuse without a client, a credential or a call."""
    from larkdocio.common.destination import ApplicationRootToken, require_destination
    from larkdocio.errors import MissingDestinationError

    drive, _ = client(fx.listing_router({}, root_token="nodlROOTTOKEN"))
    token = drive.root_folder_token()

    assert isinstance(token, ApplicationRootToken)
    assert isinstance(token, str) and token == "nodlROOTTOKEN"
    with pytest.raises(MissingDestinationError):
        require_destination(token, what="a document")


def test_the_root_folder_leg_types_its_EMPTY_answer_too_without_changing_its_meaning():
    """A response carrying no token still answers ``""`` — falsy, equal to the empty string,
    and refused by the blank branch that already existed."""
    from larkdocio.common.destination import ApplicationRootToken

    drive, _ = client(fx.listing_router({}, root_token=""))
    token = drive.root_folder_token()

    assert isinstance(token, ApplicationRootToken)
    assert token == "" and not token


def test_ac7_the_root_folder_capture_is_the_shape_this_leg_parses():
    body = fx.root_folder_meta_response()
    assert body["code"] == 0 and body["data"]["token"].startswith("nodl")


def test_ac7_the_NAME_leg_resolves_a_folders_own_title():
    """The listing returns a folder's *children*, never the folder's own title — so a rendered
    heading needs this leg."""
    drive, transport = client(fx.listing_router(
        {}, metas=fx.folder_meta_response("fldrX", "Plans & Proposals")))

    answer = drive.folder_name("fldrX")

    assert answer.name == "Plans & Proposals"
    assert answer.disclosure is None
    assert transport.calls[0].path == "/open-apis/drive/v1/metas/batch_query"
    assert transport.calls[0].method == "POST"
    assert transport.calls[0].body["request_docs"] == [
        {"doc_token": "fldrX", "doc_type": "folder"}]


def test_ac7_the_NAME_leg_DEGRADES_and_never_invents_a_name():
    """The leg is degradable by construction: a refusal leaves the folder rendered by its token
    with the missing name DISCLOSED.

    ``batch_query`` **does** resolve a folder token — measured on a control pair (LD-606:
    ``ld467-25`` / ``ld514-04``'s 4 live folder rows positive, ``ld467-13`` / ``ld514-04``'s 36
    trashed rows negative) — so this degrade is what the measured NEGATIVE looks like, not a
    hedge against an unmeasured route."""
    drive, _t = client(fx.listing_router({}, metas=fx.refusal_response()))

    answer = drive.folder_name("fldrX")

    assert answer.name is None
    assert answer.token == "fldrX"
    assert "1061002" in answer.disclosure
    assert "fldrX" in answer.disclosure


def test_ac7_the_NAME_leg_degrades_on_an_EMPTY_metas_array_too():
    drive, _t = client(fx.listing_router(
        {}, metas={"code": 0, "msg": "Success", "data": {"metas": []}}))
    answer = drive.folder_name("fldrX")
    assert answer.name is None and answer.disclosure


def test_ac7_every_op_declares_MUTATES_explicitly_and_the_ENUMERATION_is_all_False():
    """The flag is a declaration, never derived from the verb — the ``larkdocio.base.ops``
    rule, and this surface has its own POST read to prove why.

    **TRANSFORMED, not deleted (LD-409, D-24).** This asserted ``all of them are False`` while
    the whole registry was R1's enumeration. LD-409 registered ``create_version``, so the
    surface-wide conclusion moved — but the claim this guard existed to protect did not: R1's
    three enumeration legs are still read-only, and that is what is asserted now. The
    surface-wide answer is asserted too, in its new form, so a mutating op cannot be added
    silently either way.
    """
    assert ops.OPS
    assert "mutates" in {f.name for f in ops.dataclasses_fields()}
    for descriptor in ops.ENUMERATION_OPS:
        assert descriptor.mutates is False, descriptor.name
    assert ops.read_only(ops.ENUMERATION_OPS) is True
    assert ops.read_only() is False, (
        "the whole-registry claim must move with the registry — create_version mutates")
    assert {d.name for d in ops.mutating_ops()} == MUTATING_OPS


def test_ac7_the_module_docstring_records_WHY_each_raw_leg_is_raw():
    source = (DRIVE_PACKAGE / "client.py").read_text(encoding="utf-8")
    assert "explorer/v2" in source and "legacy" in source.lower()
    assert "RawHttpClient" in source or "raw-HTTP" in source


# --------------------------------------------------------------------------- #
# AC9 — READ credentials only, throttled by construction.                       #
# --------------------------------------------------------------------------- #

#: The ONE module in this package allowed to name the write pair — LD-409's mutating client,
#: which is a write op and must resolve WRITE credentials. Everything else in the package is
#: read-side and the fence below still holds it. **Transformed, not deleted (D-24):** the
#: reason the fence exists — the read path must never reach the write pair — is unchanged, and
#: naming the one exception explicitly is what keeps a second one from arriving unnoticed.
#: The package's MUTATING modules — the ones the read-side fences below deliberately exclude.
#: Grown, not rewritten: LD-409 added the named-version client and LD-432 the access client,
#: and each arrived in its own module for the same reason (a surface carries one credential
#: pair, and the CLI's read-only reachability guard walks module paths). LD-467 added the
#: folder-creation client on the same terms — one verb, its own module, the WRITE pair only.
WRITE_SIDE_MODULES = {"versions_write.py", "access_write.py", "files_write.py",
                      "folders_write.py"}

#: Every op in the registry that DECLARES it mutates — one name per mutating rung, listed here
#: so adding one is a deliberate act in this guard as well as in the registry.
MUTATING_OPS = {
    "create_version",
    "grant_access", "update_access", "revoke_access", "set_copy_permissions",
    # LD-467 — the ONE R3 organize verb a product ruling opened. The rest of the rung is
    # deliberately unregistered, so this set is also the fence on how far it opened.
    "create_folder",
}


def test_ac9_the_READ_SIDE_of_the_package_NEVER_NAMES_a_write_credential():
    for path in sorted(DRIVE_PACKAGE.rglob("*.py")):  # LD-654: recursive population
        if path.name in WRITE_SIDE_MODULES:
            continue
        source = path.read_text(encoding="utf-8")
        for forbidden in ("LARK_WRITE_APP", "get_write_credentials", "resolved_write_env"):
            assert forbidden not in source, f"{path.name} reaches for the write pair"


def test_ac9_the_ONE_write_side_module_NEVER_NAMES_a_read_credential_either():
    """The fence is symmetric: the mutating client may not fall back to the read pair, which is
    the other half of "read and write credentials never cross"."""
    for name in sorted(WRITE_SIDE_MODULES):
        source = (DRIVE_PACKAGE / name).read_text(encoding="utf-8")
        for forbidden in ("LARK_READ_APP", "get_read_credentials", "resolved_read_env"):
            assert forbidden not in source, f"{name} reaches for the read pair"


def test_ac9_from_read_credentials_resolves_the_READ_pair(monkeypatch):
    seen = {}

    def fake_read():
        seen["called"] = True
        return ("read-id", "read-secret")

    monkeypatch.setattr("larkdocio.drive.client.get_read_credentials", fake_read)
    monkeypatch.setattr("larkdocio.drive.client.apply_ipv4_pin", lambda: None)
    drive = DriveClient.from_read_credentials(token_fetcher=fx.token_fetcher)
    assert seen["called"] and drive._app_id == "read-id"


def test_ac9_missing_read_credentials_are_a_LOUD_config_error(monkeypatch):
    monkeypatch.setattr("larkdocio.drive.client.get_read_credentials", lambda: (None, None))
    monkeypatch.setattr("larkdocio.drive.client.apply_ipv4_pin", lambda: None)
    with pytest.raises(LarkConfigError) as excinfo:
        DriveClient.from_read_credentials()
    assert "READ" in str(excinfo.value)


def test_ac9_the_throttle_is_applied_ON_THE_SHIPPED_PATH_not_merely_available():
    limiter = CountingLimiter(10 ** 6, window=0.000001)
    page1, page2, _expected = fx.pagination_pages()

    def answer(call):
        return page2 if call.params.get("page_token") else page1

    route = fx.listing_router({"fldrPAGED": answer}, root_token="nodlROOT",
                              metas=fx.folder_meta_response("fldrPAGED", "Paged"))
    drive, transport = client(route, rate_limiter=limiter)

    drive.list_folder_children_to_exhaustion("fldrPAGED")
    drive.root_folder_token()
    drive.folder_name("fldrPAGED")

    assert limiter.acquisitions == len(transport.calls) == drive.api_calls
    assert drive.limiter is limiter


def test_ac9_the_documented_gentle_read_cap_is_quoted_and_NOT_PROBED():
    from larkdocio.drive import client as client_module

    assert client_module.DEFAULT_MAX_READS_PER_WINDOW == 50
    assert client_module.DRIVE_MIN_REQUEST_SPACING_SECONDS == pytest.approx(1.2)
    doc = client_module.__doc__ + inspect.getdoc(client_module.DriveClient)
    assert "1.2" in doc, "the evidence for the pace is the spike's own 1.2 s spacing"
    source = (DRIVE_PACKAGE / "client.py").read_text(encoding="utf-8")
    assert "99991400" not in source, (
        "rate limits are documented, never hunted — nothing here walks into one")


# --------------------------------------------------------------------------- #
# AC10 — GET-only by construction, plus the ONE declared query POST.             #
# --------------------------------------------------------------------------- #

def test_ac10_the_declared_verbs_are_GET_plus_DECLARED_query_POSTs_and_write_POSTs():
    """**Transformed twice, deleted never (LD-409 then LD-432, D-24).** The point of this guard
    was never the count: it was that a verb here is a *declaration*, not an inference. LD-409
    made that provable from both sides — one POST declares ``False`` and one declares ``True``.
    LD-432 widened the verb set (the access family adds PUT, DELETE and PATCH), and LD-467
    added a fourth POST (``create_folder``), so the surface-wide count moved again while the
    claim did not: the ENUMERATION's own verbs are still GET plus exactly one query POST, and
    every POST still says for itself.

    **Transformed a third time by LD-487, and again the reason is untouched.** A second
    *declared-read* POST joined (``document_security_level``, the tenant security level on the very
    endpoint ``folder_name`` already rides), so ``query_posts()`` is two rather than one. The
    enumeration set is unchanged — the new leg is not one of R1's three — and what this guard
    protects is unchanged too: no verb is inferred anywhere."""
    enumeration_verbs = sorted({d.http_method for d in ops.ENUMERATION_OPS})
    assert enumeration_verbs == ["GET", "POST"]
    posts = {d.name: d for d in ops.OPS if d.http_method == "POST"}
    assert set(posts) == {"folder_name", "document_security_level", "create_version",
                          "grant_access", "create_folder"}
    assert posts["create_folder"].endpoint == ops.FILES_CREATE_FOLDER_ENDPOINT
    assert posts["create_folder"].mutates is True
    assert posts["folder_name"].endpoint == "/open-apis/drive/v1/metas/batch_query"
    assert posts["folder_name"].mutates is False
    assert posts["document_security_level"].endpoint == "/open-apis/drive/v1/metas/batch_query"
    assert posts["document_security_level"].mutates is False
    assert posts["create_version"].endpoint == ops.FILE_VERSIONS_ENDPOINT
    assert posts["create_version"].mutates is True
    assert posts["grant_access"].endpoint == ops.PERMISSION_MEMBERS_ENDPOINT
    assert posts["grant_access"].mutates is True
    assert {d.name for d in ops.query_posts()} == {"folder_name", "document_security_level"}
    # Every verb the surface can now put on the wire is declared by an op that owns it — and
    # the mutating half is exactly the ops that say they mutate, never a verb inference.
    assert sorted(ops.http_verbs()) == ["DELETE", "GET", "PATCH", "POST", "PUT"]
    assert {d.http_method for d in ops.OPS if d.mutates} == {"POST", "PUT", "DELETE", "PATCH"}


def test_ac10_the_WIRE_verbs_over_every_path_match_the_declared_set():
    listings = fx.real_tree_listings()
    drive, transport = client(fx.listing_router(
        listings, root_token=fx.real_tree_root(),
        metas=fx.folder_meta_response(fx.real_tree_root(), "Root")))

    drive.root_folder_token()
    drive.folder_name(fx.real_tree_root())
    drive.list_folder_children_to_exhaustion(fx.real_tree_root())

    assert transport.methods == ["GET", "POST"]
    by_path = {call.path: call.method for call in transport.calls}
    for path, method in by_path.items():
        descriptor = ops.descriptor_for_path(path)
        assert descriptor is not None, path
        assert descriptor.http_method == method
        assert descriptor.mutates is False


def test_ac10_the_client_cannot_MOVE_COPY_DELETE_UPLOAD_SHORTCUT_or_RENAME():
    """R1 is read-only *in code, not just in prose* — the round-2 probe's own posture.

    **Transformed, not deleted (D-24).** The claim was always about the READ side: the
    enumeration client cannot mutate anything, whatever else the package grows. Two mutating
    modules have since arrived (``versions_write.py``, ``access_write.py``), each with a
    surface and a credential pair of its own, so they are excluded BY NAME — which keeps the
    exclusion a deliberate, listed act rather than a loosened pattern. Everything else in the
    package is still held to the original bar.
    """
    forbidden = ("move", "copy", "delete", "upload", "create_folder", "create_shortcut",
                 "rename", "permission")
    checked = []
    for path in sorted(DRIVE_PACKAGE.rglob("*.py")):  # LD-654: recursive population
        # `ops.py` is excluded for a different reason from the write clients: it is the one
        # place a mutating verb is DECLARED, so naming "DELETE" is exactly its job — and the
        # declaration is asserted, op by op, by the two guards above.
        if path.name in WRITE_SIDE_MODULES or path.name == "ops.py":
            continue
        checked.append(path.name)
        source = path.read_text(encoding="utf-8").lower()
        for verb in forbidden:
            assert f'"{verb}"' not in source.replace("/files/:file_token", ""), (path.name, verb)
        assert '"delete"' not in source and '"put"' not in source and '"patch"' not in source
    assert "client.py" in checked, "the enumeration client itself must still be in the set"


def test_ac10_every_send_takes_its_VERB_FROM_THE_DESCRIPTOR():
    """Structural, so a new call cannot arrive with a hand-typed verb: the client has exactly
    one send seam and it reads ``descriptor.http_method``."""
    source = (DRIVE_PACKAGE / "client.py").read_text(encoding="utf-8")
    assert source.count("self._send(") == 1
    assert "descriptor.http_method" in source
