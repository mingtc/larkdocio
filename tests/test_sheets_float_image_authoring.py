"""The FLOAT-image route on a spreadsheet — upload bound to the WORKBOOK, bind, fresh query.

Offline, over the **LD-435 captures themselves** (``tests/captures/sheets-media-spike/captures/``, in the
dev repo): the client-level tests feed the captured response bodies through the shipped
transport's stub opener, and the op-level tests drive fakes whose replies are the captured
``data`` objects verbatim. Nothing here is a hand-mocked dict.

The four traps this file exists to hold, each measured with its own control:

1. ``parent_node`` is **the spreadsheet token** — the docx habit (bind the upload to the
   BLOCK) is the one that misleads here (``103-``);
2. the upload's own ``code 0`` is **not a bind** — a fresh query before any create answers
   ``{"items": []}`` (``105-``), so the verdict is the query;
3. a bind given a bad token answers an HTTP 500 whose message says *"Retry Later"* and is a
   **refusal** (``108-``) — nothing was created (``201-``) — so it must never be retried;
4. the bind does **not** police image-vs-file tokens (``207-``, ``208-``).

Tests pinning **measured external truth** carry ``@pytest.mark.conformance``
(``process/doctrine/conformance-tier.md``); the plumbing tests are unmarked regression.

**No refusal number is asserted as a literal.** Where a code is asserted it is read out of the
capture that measured it, so the day Lark renumbers the answer this suite reddens on the
capture it was told to trust rather than on a magic constant (LD-417 AC10 precedent).
"""
import inspect
import json
import zlib
from pathlib import Path

import pytest

from larkdocio.base import media as base_media
from larkdocio.base.media import (
    MediaRoundTripError,
    MediaUploadError,
    UploadedMedia,
    sha256_of,
)
from larkdocio.common.transport import WriteTransport
from larkdocio.errors import LarkAPIError
from larkdocio.sheets import media as sheets_media
from larkdocio.sheets.media import (
    SHEET_FILE_PARENT_TYPE,
    SHEET_IMAGE_PARENT_TYPE,
    FloatImage,
    SheetFloatImageBindError,
    SheetFloatImageRemoveError,
    FloatImageMediaClient,
    put_float_image_in_sheet,
    remove_float_image_from_sheet,
)
from larkdocio.sheets.write_client import SheetsWriteClient

from write_harness import FakeClock, StubOpener
import private_tree  # noqa: E402  (LD-685)

# --------------------------------------------------------------------------- #
# The captures — the ONLY source of a payload shape in this file.              #
# --------------------------------------------------------------------------- #

_CAPTURES = (Path(__file__).resolve().parent.parent
             / "tests" / "captures" / "sheets-media-spike" / "captures")


def capture(prefix):
    """The one capture whose file name starts with ``prefix``, parsed."""
    matches = sorted(_CAPTURES.glob(f"{prefix}-*.json"))
    assert len(matches) == 1, f"expected exactly one capture {prefix}-*: {matches}"
    return json.loads(matches[0].read_text(encoding="utf-8"))


UPLOAD = capture("103")          # upload_all, parent_type sheet_image, parent_node WORKBOOK
EMPTY_QUERY = capture("105")     # the fresh query BEFORE any create: {"items": []}
CREATE = capture("106")          # the bind
VERDICT = capture("107")         # the fresh query AFTER the create
MIS_TYPED = capture("108")       # the invented-token control: HTTP 500, "Retry Later"
NO_PHANTOM = capture("201")      # the re-query proving the refusal created nothing
CROSS_TYPE = capture("207")      # a sheet_file token accepted by the float-image bind
CROSS_TYPE_QUERY = capture("208")  # ...and listed as a float image
DELETED = capture("303")         # DELETE .../float_images/{id}
GONE = capture("304")            # the fresh query proving it is gone

TOKEN = UPLOAD["request"]["form_fields"]["parent_node"]        # the SPREADSHEET token
SHEET_ID = CREATE["request"]["body"]["range"].split("!", 1)[0]
RANGE = CREATE["request"]["body"]["range"]
FILE_TOKEN = UPLOAD["response"]["data"]["file_token"]
FLOAT_IMAGE = CREATE["response"]["data"]["float_image"]
FLOAT_IMAGE_ID = FLOAT_IMAGE["float_image_id"]


def png_bytes(rgb=(0, 0, 0)):
    """A 1x1 PNG, authored from source — never a committed binary blob.

    The spike uploaded a PNG and nothing else; the offline fixture keeps the same media kind
    rather than inventing a second claim.
    """
    def chunk(kind, payload):
        body = kind + payload
        return (len(payload).to_bytes(4, "big") + body
                + zlib.crc32(body).to_bytes(4, "big"))

    ihdr = (1).to_bytes(4, "big") + (1).to_bytes(4, "big") + bytes((8, 2, 0, 0, 0))
    raw = bytes((0,)) + bytes(rgb)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


PNG = png_bytes()


# --------------------------------------------------------------------------- #
# The fakes. Every call is recorded IN ORDER, because the order IS the contract. #
# --------------------------------------------------------------------------- #

class FakeSheetsWriteClient:
    """Replies with the captured ``data`` objects; ``queries`` is a script of answers."""

    def __init__(self, log, *, queries=None, create_error=None, created=None):
        self.log = log
        self._queries = list(queries) if queries is not None else [
            VERDICT["response"]["data"]["items"]]
        self._create_error = create_error
        self._created = created if created is not None else FLOAT_IMAGE

    def create_float_image(self, spreadsheet_token, sheet_id, *, float_image_token,
                           a1_range, width, height, offset_x=0, offset_y=0):
        self.log.append(("create_float_image", spreadsheet_token, sheet_id,
                         float_image_token, a1_range, width, height, offset_x, offset_y))
        if self._create_error is not None:
            raise self._create_error
        return dict(self._created)

    def query_float_images(self, spreadsheet_token, sheet_id):
        self.log.append(("query_float_images", spreadsheet_token, sheet_id))
        return list(self._queries.pop(0)) if self._queries else []

    def delete_float_image(self, spreadsheet_token, sheet_id, float_image_id):
        self.log.append(("delete_float_image", spreadsheet_token, sheet_id, float_image_id))
        return dict(DELETED["response"]["data"])


class FakeMediaClient:
    def __init__(self, log, *, upload_error=None, downloaded=None):
        self.log = log
        self._upload_error = upload_error
        self._downloaded = downloaded

    def upload(self, *, data, name, parent_type, parent_node):
        self.log.append(("upload", name, parent_type, parent_node, len(data)))
        if self._upload_error is not None:
            raise self._upload_error
        return UploadedMedia(file_token=FILE_TOKEN, parent_type=parent_type,
                             parent_node=parent_node, size=len(data),
                             sha256=sha256_of(data))

    def download(self, file_token):
        self.log.append(("download", file_token))
        return PNG if self._downloaded is None else self._downloaded


def run(log=None, *, data=PNG, **kwargs):
    """Drive the op over the fakes; returns ``(result, call log)``."""
    log = [] if log is None else log
    client_kwargs = {k: kwargs.pop(k) for k in ("queries", "create_error", "created")
                     if k in kwargs}
    media_kwargs = {k: kwargs.pop(k) for k in ("upload_error", "downloaded")
                    if k in kwargs}
    result = put_float_image_in_sheet(
        client=FakeSheetsWriteClient(log, **client_kwargs),
        media=FakeMediaClient(log, **media_kwargs),
        spreadsheet_token=TOKEN, sheet_id=SHEET_ID, a1_range=RANGE,
        data=data, name="ld435.png",
        width=FLOAT_IMAGE["width"], height=FLOAT_IMAGE["height"], **kwargs)
    return result, log


def calls(log):
    return [entry[0] for entry in log]


# --------------------------------------------------------------------------- #
# AC1 / AC2 — the three beats as one unit, and the WORKBOOK trap.              #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_the_three_beats_happen_in_a_fixed_order_and_the_query_is_the_verdict():
    """AC1/AC3. Upload → create → **a fresh query**. The order is the measured route
    (``103-`` → ``106-`` → ``107-``), and the read-back is last because it is the verdict."""
    result, log = run()
    assert calls(log) == [
        "upload", "create_float_image", "query_float_images", "download"]
    assert isinstance(result, FloatImage)
    assert result.float_image_id == FLOAT_IMAGE_ID
    assert result.float_image_token == FILE_TOKEN
    assert result.a1_range == RANGE
    assert result.bytes_verified is True


@pytest.mark.conformance
def test_the_upload_binds_to_the_WORKBOOK_not_the_tab_and_not_a_cell():
    """AC2 — the docx trap. ``parent_node`` is the **spreadsheet token**; the tab appears
    only later, in the bind's range. Held against the capture's own form fields (``103-``)."""
    _, log = run()
    upload = [entry for entry in log if entry[0] == "upload"][0]
    _, _, parent_type, parent_node, _ = upload
    assert parent_type == UPLOAD["request"]["form_fields"]["parent_type"]
    assert parent_node == UPLOAD["request"]["form_fields"]["parent_node"]
    assert parent_node == TOKEN
    # ...and the tab id is NOT what was uploaded against — the trap, stated as an assertion.
    assert parent_node != SHEET_ID


@pytest.mark.conformance
def test_the_shipped_text_states_the_WORKBOOK_trap_as_a_warning():
    """AC2 — in the shipped text, not only in a parameter list."""
    for text in (sheets_media.__doc__, put_float_image_in_sheet.__doc__,
                 SheetsWriteClient.create_float_image.__doc__):
        lowered = " ".join((text or "").lower().split())
        assert "spreadsheet token" in lowered or "workbook" in lowered, text
    module = " ".join((sheets_media.__doc__ or "").lower().split())
    assert "not a cell, not a sheet_id" in module
    assert "docx" in module, "the docx habit is the trap; the text must name it"


def test_the_op_takes_no_pre_made_token_so_the_wrong_order_cannot_be_driven_from_outside():
    """AC1. Three calls as a unit: there is no ``float_image_token`` parameter, so a caller
    cannot hand in a token minted somewhere else (which is also why the op cannot swallow a
    ``sheet_file`` token — see the swallow test below)."""
    parameters = inspect.signature(put_float_image_in_sheet).parameters
    assert "float_image_token" not in parameters
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())


# --------------------------------------------------------------------------- #
# AC3 — an accepted upload is not a stored picture.                            #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_an_upload_answering_success_is_NOT_a_bind_and_the_empty_query_refuses():
    """AC3, driven by ``105-`` verbatim: the fresh query answers ``{"items": []}``. The op
    refuses rather than reporting a success nobody observed, and says the token is permanent."""
    assert EMPTY_QUERY["response"]["data"]["items"] == []
    with pytest.raises(SheetFloatImageBindError) as raised:
        run(queries=[EMPTY_QUERY["response"]["data"]["items"]])
    message = str(raised.value).lower()
    assert "permanent" in message
    assert raised.value.float_image_token == FILE_TOKEN
    assert "the fresh query" in message or "fresh query" in message


def test_a_query_listing_a_DIFFERENT_float_image_is_still_a_refusal():
    """The verdict is *this* float image being listed — not the query answering something."""
    other = dict(FLOAT_IMAGE, float_image_id="someoneElses")
    with pytest.raises(SheetFloatImageBindError):
        run(queries=[[other]])


# --------------------------------------------------------------------------- #
# AC4 — the mis-typed refusal. The highest-consequence disclosure here.        #
# --------------------------------------------------------------------------- #

def test_the_bind_refusal_is_sent_ONCE_and_never_retried():
    """AC4. The client is fed the captured HTTP-500 body (``108-``) and must make **exactly
    one** request: a refusal wearing a server error's clothes is still a refusal."""
    opener = StubOpener([MIS_TYPED["response"]])
    client = stub_client(opener)
    with pytest.raises(LarkAPIError) as raised:
        client.create_float_image(TOKEN, SHEET_ID, float_image_token="boxExample0001",
                                  a1_range=RANGE, width=60, height=60)
    assert len(opener.requests) == 1, opener.requests
    # The code is read out of the capture, never typed as a literal.
    assert str(raised.value.code) == str(MIS_TYPED["response"]["code"])


@pytest.mark.conformance
def test_the_refusal_message_says_the_route_MIS_TYPES_a_refusal_as_a_server_error():
    """AC4. Lark's verbatim body plus this library's own words about what it means."""
    opener = StubOpener([MIS_TYPED["response"]])
    client = stub_client(opener)
    with pytest.raises(LarkAPIError) as raised:
        client.create_float_image(TOKEN, SHEET_ID, float_image_token="boxExample0001",
                                  a1_range=RANGE, width=60, height=60)
    message = " ".join(str(raised.value).lower().split())
    assert MIS_TYPED["response"]["msg"].lower() in message, "Lark's own words must survive"
    assert "refusal" in message
    assert "do not retry" in message or "never retried" in message


@pytest.mark.conformance
def test_the_refusal_created_NOTHING_and_the_re_query_is_what_proves_it():
    """AC4, driven by ``201-``: after the invented-token control the tab still lists only the
    real item — no phantom. The op's own answer to a refused bind is the same: it reports the
    permanent media token and creates nothing."""
    listed = {item["float_image_id"]
              for item in NO_PHANTOM["response"]["data"]["items"]}
    assert listed == {FLOAT_IMAGE_ID}, NO_PHANTOM

    refusal = LarkAPIError("Code: %s, Msg: %s" % (MIS_TYPED["response"]["code"],
                                                  MIS_TYPED["response"]["msg"]),
                           code=MIS_TYPED["response"]["code"])
    log = []
    with pytest.raises(LarkAPIError) as raised:
        run(log, create_error=refusal)
    # Exactly one create attempt — no retry — and no query after it: nothing was created.
    assert calls(log) == ["upload", "create_float_image"]
    assert getattr(raised.value, "orphan_file_token", None) == FILE_TOKEN


def test_a_partial_success_is_reported_as_what_it_is_a_permanent_token_and_no_picture():
    """AC1. The upload landed, the bind did not: the caller is told a permanent, unpurgeable
    media token exists and no picture does — never that nothing happened."""
    refusal = LarkAPIError("Code: 1315203, Msg: Server Error, Retry Later", code=1315203)
    with pytest.raises(LarkAPIError) as raised:
        run(create_error=refusal)
    assert raised.value.orphan_file_token == FILE_TOKEN
    hint = " ".join(str(getattr(raised.value, "residue_disclosure", "")).lower().split())
    assert "permanent" in hint and "no picture" in hint, hint


# --------------------------------------------------------------------------- #
# AC5 — the swallow.                                                           #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_the_bind_does_not_police_image_vs_file_tokens_and_the_capture_says_so():
    """AC5, driven by ``207-``/``208-``: a ``sheet_file`` token is **accepted** (``code 0``)
    and listed as a float image. The shipped text discloses it."""
    assert CROSS_TYPE["response"]["code"] == 0
    swallowed = CROSS_TYPE["response"]["data"]["float_image"]["float_image_token"]
    assert swallowed in {item["float_image_token"]
                         for item in CROSS_TYPE_QUERY["response"]["data"]["items"]}
    disclosure = " ".join((sheets_media.__doc__ or "").lower().split())
    assert "does not police" in disclosure
    assert SHEET_FILE_PARENT_TYPE in disclosure


def test_the_op_CANNOT_swallow_because_it_mints_its_own_token_and_refuses_the_file_family():
    """AC5, this library's half of the answer: ``put_float_image_in_sheet`` mints the token it
    binds, and the media client refuses the ``sheet_file`` spelling **locally, before any
    call**. So the swallow is disclosed for the low-level bind and impossible through the op."""
    assert FloatImageMediaClient.ALLOWED_PARENT_TYPES == (SHEET_IMAGE_PARENT_TYPE,)
    client = FloatImageMediaClient("app", "secret", sdk_client=object())
    with pytest.raises(MediaUploadError) as raised:
        client.upload(data=PNG, name="x.png", parent_type=SHEET_FILE_PARENT_TYPE,
                      parent_node=TOKEN)
    assert SHEET_FILE_PARENT_TYPE in str(raised.value)


# --------------------------------------------------------------------------- #
# AC6 — the bytes, proven with the EXISTING round-trip definition.             #
# --------------------------------------------------------------------------- #

def test_the_round_trip_check_is_the_SHARED_definition_not_a_second_one():
    """AC6. Identity, not similarity: one definition of *"the bytes that came back are the
    bytes that went up"* in this library."""
    assert sheets_media.verify_round_trip is base_media.verify_round_trip
    source = inspect.getsource(sheets_media)
    assert "hashlib" not in source, "no second hash implementation may live here"
    assert "sha256(" not in source.replace("sha256_of(", "")


def test_a_byte_mismatch_raises_the_shared_round_trip_error():
    with pytest.raises(MediaRoundTripError):
        run(downloaded=png_bytes((255, 0, 0)))


def test_verification_is_OPT_OUT_and_the_result_says_which_it_was():
    result, log = run(verify_bytes=False)
    assert "download" not in calls(log)
    assert result.bytes_verified is False


# --------------------------------------------------------------------------- #
# AC7 — removal ships with the create, and its verdict is the query.           #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_removal_is_verdicted_by_a_FRESH_QUERY_never_by_the_deletes_own_code_0():
    """AC7, driven by ``303-``/``304-``: the delete answers ``code 0`` and the *query* is what
    proves the picture is gone."""
    assert DELETED["response"]["code"] == 0
    log = []
    remaining = remove_float_image_from_sheet(
        client=FakeSheetsWriteClient(log, queries=[GONE["response"]["data"]["items"]]),
        spreadsheet_token=TOKEN, sheet_id=SHEET_ID, float_image_id=FLOAT_IMAGE_ID)
    assert calls(log) == ["delete_float_image", "query_float_images"]
    assert FLOAT_IMAGE_ID not in remaining
    # 304- still lists the OTHER float image; the removal claim is about one id, not the tab.
    assert remaining == tuple(item["float_image_id"]
                              for item in GONE["response"]["data"]["items"])


def test_a_delete_whose_query_still_lists_the_picture_is_a_REFUSAL_not_a_success():
    log = []
    with pytest.raises(SheetFloatImageRemoveError):
        remove_float_image_from_sheet(
            client=FakeSheetsWriteClient(
                log, queries=[VERDICT["response"]["data"]["items"]]),
            spreadsheet_token=TOKEN, sheet_id=SHEET_ID, float_image_id=FLOAT_IMAGE_ID)


# --------------------------------------------------------------------------- #
# The three client legs speak the captured method, path and body.              #
# --------------------------------------------------------------------------- #

def stub_client(opener):
    clock = FakeClock()
    return SheetsWriteClient(
        "app", "secret", "larksuite.com",
        transport=WriteTransport(max_writes_per_sec=3, time_fn=clock.time,
                                 sleep_fn=clock.sleep),
        urlopen=opener, token_fetcher=lambda *a, **k: "t-test")


@pytest.mark.conformance
@pytest.mark.parametrize("name,cap,method", [
    ("create", CREATE, "POST"),
    ("query", VERDICT, "GET"),
    ("delete", DELETED, "DELETE"),
])
def test_each_float_image_leg_speaks_the_captured_method_and_path(name, cap, method):
    opener = StubOpener([cap["response"]])
    client = stub_client(opener)
    if name == "create":
        client.create_float_image(TOKEN, SHEET_ID, float_image_token=FILE_TOKEN,
                                  a1_range=RANGE, width=FLOAT_IMAGE["width"],
                                  height=FLOAT_IMAGE["height"])
    elif name == "query":
        client.query_float_images(TOKEN, SHEET_ID)
    else:
        client.delete_float_image(TOKEN, SHEET_ID, FLOAT_IMAGE_ID)
    sent = opener.requests[0]
    assert sent["method"] == cap["request"]["method"] == method
    assert sent["url"].endswith(cap["request"]["path"]), sent["url"]


@pytest.mark.conformance
def test_the_create_body_is_the_captured_body():
    opener = StubOpener([CREATE["response"]])
    client = stub_client(opener)
    client.create_float_image(TOKEN, SHEET_ID, float_image_token=FILE_TOKEN,
                              a1_range=RANGE, width=FLOAT_IMAGE["width"],
                              height=FLOAT_IMAGE["height"])
    assert opener.requests[0]["body"] == CREATE["request"]["body"]


def test_a_bare_single_cell_range_is_normalized_to_Start_End_like_every_other_write():
    """The ``90202`` guard is the write client's, reused — not re-decided here."""
    opener = StubOpener([CREATE["response"]])
    client = stub_client(opener)
    client.create_float_image(TOKEN, SHEET_ID, float_image_token=FILE_TOKEN,
                              a1_range=f"{SHEET_ID}!A1", width=120, height=120)
    assert opener.requests[0]["body"]["range"] == RANGE


def test_the_query_returns_the_items_list_and_an_empty_answer_is_an_empty_list():
    opener = StubOpener([EMPTY_QUERY["response"]])
    assert stub_client(opener).query_float_images(TOKEN, SHEET_ID) == []


# --------------------------------------------------------------------------- #
# AC9 — the negative claims ship with the edge of their evidence.              #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("phrase", [
    "one tenant",
    "tenant_access_token",
    "unmeasured",
    "88-byte png",
    "user_access_token",
    "patch",
])
def test_the_module_carries_the_scope_of_what_was_measured(phrase):
    """AC9 (``negative-claims.md`` § A.1): every negative/absence claim here names the forms
    actually tried, and the untried ones are labelled unmeasured rather than refuted."""
    text = " ".join((sheets_media.__doc__ or "").lower().split())
    assert phrase in text, f"the module docstring does not carry {phrase!r}"


# --------------------------------------------------------------------------- #
# AC15 — the standing ruling, guarded by its CITATION rather than its number.  #
# --------------------------------------------------------------------------- #

_DECISIONS = (Path(__file__).resolve().parent.parent
              / "requirements" / "DECISIONS.md")


def _the_ld448_ruling() -> str:
    """The register entry whose Provenance cites LD-448 — found by **citation, not number**.

    Keyed this way on purpose: a `D-NN` is read at landing and can be renumbered by a
    concurrent branch, and a guard pinned to the digits would redden on a merge rather than on
    a missing ruling (the LD-446 precedent).
    """
    text = _DECISIONS.read_text(encoding="utf-8")
    entries = [f"### {chunk}" for chunk in text.split("\n### ")[1:]]
    owned = [entry for entry in entries if "LD-448" in entry]
    assert len(owned) == 1, [entry.splitlines()[0] for entry in owned]
    return owned[0]


@private_tree.register
def test_the_ruling_is_RECORDED_where_it_is_looked_up():
    """AC15. An Activity line records *this issue*; the register is where the next reader
    looks up *what is currently true*."""
    heading = _the_ld448_ruling().splitlines()[0].lower()
    assert "float" in heading and "workbook" in heading
    assert "refusal" in heading and "retryable" in heading


@pytest.mark.parametrize("claim", [
    "the spreadsheet token",     # parent_node is the WORKBOOK
    "fresh query",               # the verdict, for the bind AND the removal
    "does not police",           # the swallow
    "never be retried",          # the mis-typed refusal
    "unpurgeable",               # the residue law, re-inherited
    "unmeasured, not refuted",   # the edge of the evidence (§ A.1)
])
@private_tree.register
def test_the_ruling_carries_every_claim_this_issue_settled(claim):
    assert claim in _the_ld448_ruling().lower(), claim
