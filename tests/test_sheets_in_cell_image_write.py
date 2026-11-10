"""LD-447 — ``put_image_in_sheet``: a picture that IS the cell's value, in ONE call.

The measured route (LD-435, 2026-08-12, **one tenant, one day**, ``tenant_access_token``
on the WRITE pair, ``larksuite.com``, **one 88-byte PNG**, on **one** workbook the harness
created and then trashed):

* ``POST …/values_image`` with ``{range, image: [ints], name}`` → ``code 0`` (capture ``202-``);
* the verdict is a **fresh** ``GET …/values/{range}`` whose cell value is an ``embed-image``
  dict carrying a ``fileToken`` (capture ``203-``);
* the bytes re-download **byte-identical** (capture ``302-``);
* the clear is an ordinary ``""`` **value write** (captures ``305-`` / ``306-``).

Every payload below is the spike's own capture — **deserialized, never hand-mocked**
(PROJECT.md § *API-drift is an expected hazard*).

**Tier (`conformance-tier.md` § A.4).** The tests pinning **measured external truth** — the
one-call request shape, the ``embed-image`` read-back shape, the int-array inflation, and
the clear being an ordinary value write — carry ``pytest.mark.conformance``. The plumbing
(local refusals, the orphan-token report, the reuse of the shared round-trip check) is
ordinary regression, unmarked.

**No Lark refusal number is asserted anywhere here.** ``90215 "can not found sheetId"`` is
what a bad tab answered (capture ``204-``); it lives in prose and in the capture, never in
an assertion that a renumbering could redden (the LD-417 AC10 precedent).

**Scope of the evidence, and it is narrow.** One tenant, one day, one 88-byte PNG, one
workbook, ``tenant_access_token``; a ``user_access_token`` is **unmeasured**; media kinds
other than PNG are **unmeasured**; images larger than 88 bytes and the route's documented
size ceilings are **unmeasured**; a write into a cell that already holds a value,
multi-cell / merged-cell ranges, the ``STALE_SHEET`` interaction and concurrent writers are
**unmeasured**; whether the picture survives an xlsx export is **unmeasured**; whether a
human *sees* a picture is **unmeasurable by API**.
"""
import json
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
from larkdocio.sheets import media as sheets_media
from larkdocio.sheets.media import (
    IN_CELL_IMAGE_MOUNT_POINT,
    InCellImage,
    SheetsInCellImageBindError,
    SheetsInCellImageError,
    SheetsMediaClient,
    put_image_in_sheet,
)
from larkdocio.sheets.write_client import SheetsWriteClient

from write_harness import FakeClock, StubOpener

_CAPTURES = (
    Path(__file__).resolve().parent.parent / "tests" / "captures" / "sheets-media-spike" / "captures"
)


def _capture(name):
    """One LD-435 capture, by its numeric prefix."""
    matches = sorted(_CAPTURES.glob(f"{name}-*.json"))
    assert matches, f"no LD-435 capture {name}- under {_CAPTURES}"
    return json.loads(matches[0].read_text(encoding="utf-8"))


WRITE = _capture("202")          # the one call
READ_BACK = _capture("203")      # the verdict
CLEAR = _capture("305")          # the clear — an ordinary value write
CLEARED = _capture("306")        # and its own read-back

TOK = WRITE["request"]["body"]["range"]  # placeholder, replaced below
TOK = READ_BACK["response"]["data"]["spreadsheetToken"]
RANGE = WRITE["request"]["body"]["range"]
NAME = WRITE["request"]["body"]["name"]
#: The 88-byte PNG the spike sent, reconstructed from the capture's own int array — so the
#: fixture is the measured payload rather than a second invented one.
PNG = bytes(WRITE["request"]["body"]["image"])
FILE_TOKEN = READ_BACK["response"]["data"]["valueRange"]["values"][0][0]["fileToken"]


# --------------------------------------------------------------------------- #
# Test doubles — offline, fed from the captures.                               #
# --------------------------------------------------------------------------- #

def _sheets_client(opener):
    clock = FakeClock()
    return SheetsWriteClient(
        "app", "secret", "larksuite.com",
        transport=WriteTransport(max_writes_per_sec=3, time_fn=clock.time,
                                 sleep_fn=clock.sleep),
        urlopen=opener,
        token_fetcher=lambda *a, **k: "t-test",
    )


class FakeMedia:
    """A download-only media leg. Records what it was asked for; never uploads."""

    def __init__(self, payload=PNG):
        self.downloaded = []
        self._payload = payload

    def download(self, file_token):
        self.downloaded.append(file_token)
        return self._payload


def _round_trip_opener(read_back=None):
    """The two answers the op's two calls get: the write, then the fresh read-back."""
    return StubOpener([WRITE["response"], read_back or READ_BACK["response"]])


# --------------------------------------------------------------------------- #
# AC1 — ONE call, over the measured route (CONFORMANCE)                        #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_the_write_leg_speaks_the_captured_method_path_and_body():
    """The request this op puts on the wire is the request the spike measured —
    ``POST …/values_image`` with ``{range, image: [ints], name}``, byte-for-byte."""
    opener = _round_trip_opener()
    put_image_in_sheet(client=_sheets_client(opener), spreadsheet_token=TOK,
                       a1_range=RANGE, data=PNG, name=NAME)

    sent = opener.requests[0]
    assert sent["method"] == WRITE["request"]["method"]
    assert sent["url"].endswith(WRITE["request"]["path"])
    assert sent["body"] == WRITE["request"]["body"]


@pytest.mark.conformance
def test_there_is_NO_upload_leg_on_this_route():
    """The whole shape of this product: the bytes travel in the ``values_image`` body, so
    exactly two calls happen and neither is ``medias/upload_all``. An implementation that
    added one would be describing the float route, a different product."""
    opener = _round_trip_opener()
    put_image_in_sheet(client=_sheets_client(opener), spreadsheet_token=TOK,
                       a1_range=RANGE, data=PNG, name=NAME)

    assert len(opener.requests) == 2
    for request in opener.requests:
        assert "upload_all" not in request["url"]
        assert "medias" not in request["url"]


def test_a_multi_cell_range_is_refused_locally_as_UNMEASURED():
    """Only a single cell was ever measured. A wider range is refused **before any call**
    — nothing is sent, so no permanent media token is minted on a guess."""
    opener = _round_trip_opener()
    with pytest.raises(SheetsInCellImageError) as exc:
        put_image_in_sheet(client=_sheets_client(opener), spreadsheet_token=TOK,
                           a1_range="61a0cd!B2:C4", data=PNG, name=NAME)

    assert "unmeasured" in str(exc.value).lower()
    assert opener.requests == []


def test_a_bare_single_cell_range_is_normalized_to_start_end():
    """The ``90202`` guard the whole sheets write surface lives under, reused rather than
    re-derived: a bare ``B2`` cannot reach the wire."""
    opener = _round_trip_opener()
    put_image_in_sheet(client=_sheets_client(opener), spreadsheet_token=TOK,
                       a1_range="61a0cd!B2", data=PNG, name=NAME)

    assert opener.requests[0]["body"]["range"] == "61a0cd!B2:B2"


def test_empty_bytes_are_refused_before_any_call():
    opener = _round_trip_opener()
    with pytest.raises(SheetsInCellImageError):
        put_image_in_sheet(client=_sheets_client(opener), spreadsheet_token=TOK,
                           a1_range=RANGE, data=b"", name=NAME)
    assert opener.requests == []


# --------------------------------------------------------------------------- #
# AC2 — the verdict is a FRESH READ-BACK, never the call's own code 0          #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_the_verdict_is_the_read_back_and_it_carries_token_range_and_revision():
    """The op's answer is built from the **second** call — the fresh values read — and
    carries the token Lark minted, the range it reports, and its revision."""
    opener = _round_trip_opener()
    written = put_image_in_sheet(client=_sheets_client(opener), spreadsheet_token=TOK,
                                 a1_range=RANGE, data=PNG, name=NAME)

    read_back = READ_BACK["response"]["data"]["valueRange"]
    assert isinstance(written, InCellImage)
    assert written.file_token == FILE_TOKEN
    assert written.range == read_back["range"]
    assert written.revision == read_back["revision"]
    assert written.spreadsheet_token == TOK
    assert written.size == len(PNG)
    assert written.sha256 == sha256_of(PNG)
    assert written.bytes_verified is False

    # ...and the second call really is a fresh GET of the target range.
    verdict = opener.requests[1]
    assert verdict["method"] == READ_BACK["request"]["method"]
    assert verdict["url"].endswith(READ_BACK["request"]["path"])


@pytest.mark.conformance
def test_the_read_back_carries_the_geometry_and_the_UNMEASURED_link():
    """``width``/``height`` are the cell-image geometry; ``link`` is an internal-api host
    URL with no signature parameter whose resolvability was never established. Both are
    surfaced as Lark reported them, and the link is never presented as a working URL."""
    opener = _round_trip_opener()
    written = put_image_in_sheet(client=_sheets_client(opener), spreadsheet_token=TOK,
                                 a1_range=RANGE, data=PNG, name=NAME)

    cell = READ_BACK["response"]["data"]["valueRange"]["values"][0][0]
    assert (written.width, written.height) == (cell["width"], cell["height"])
    assert written.link == cell["link"]


def test_an_accepted_call_that_stored_nothing_is_a_REFUSAL_not_a_success():
    """``code 0`` proves an answer arrived. If the fresh read-back shows no image, the op
    raises rather than reporting a success nobody observed."""
    empty = json.loads(json.dumps(CLEARED["response"]))   # the measured 'cell is ""' shape
    opener = StubOpener([WRITE["response"], empty])
    with pytest.raises(SheetsInCellImageBindError) as exc:
        put_image_in_sheet(client=_sheets_client(opener), spreadsheet_token=TOK,
                           a1_range=RANGE, data=PNG, name=NAME)

    assert exc.value.spreadsheet_token == TOK
    assert "read back" in str(exc.value).lower()


def test_the_read_back_parse_REUSES_the_shipped_typed_segment():
    """LD-446 already types an ``embed-image`` cell. This op reuses that parse rather than
    minting a second one — so a shape change is corrected in one place."""
    source = Path(sheets_media.__file__).read_text(encoding="utf-8")
    assert "parse_segments" in source
    for reparse in ('get("fileToken")', '["fileToken"]', 'get("embed-image")',
                    '== "embed-image"'):
        assert reparse not in source, (
            f"the wire shape is re-read here ({reparse}) — the typed segment already owns "
            f"that parse")


# --------------------------------------------------------------------------- #
# AC3 — the bytes are proven with the EXISTING verify_round_trip               #
# --------------------------------------------------------------------------- #

def test_byte_verification_is_OPT_IN_and_runs_the_SHIPPED_round_trip():
    """Opt-in by construction: no download client, no download. With one, the token is
    fetched and compared by ``larkdocio.base.media.verify_round_trip``."""
    assert sheets_media.verify_round_trip is base_media.verify_round_trip

    opener = _round_trip_opener()
    media = FakeMedia()
    written = put_image_in_sheet(client=_sheets_client(opener), spreadsheet_token=TOK,
                                 a1_range=RANGE, data=PNG, name=NAME, media=media)

    assert media.downloaded == [FILE_TOKEN]
    assert written.bytes_verified is True


def test_bytes_that_do_not_round_trip_raise_the_SHIPPED_error():
    opener = _round_trip_opener()
    with pytest.raises(MediaRoundTripError):
        put_image_in_sheet(client=_sheets_client(opener), spreadsheet_token=TOK,
                           a1_range=RANGE, data=PNG, name=NAME,
                           media=FakeMedia(payload=PNG + b"\x00"))


def test_the_round_trip_anchor_quotes_larks_own_mount_point():
    """The comparison anchor is an :class:`UploadedMedia` — the shared function's own
    input type, reused. Its parent fields are **quoted from Lark's read-back**
    (``mount_point`` / ``mount_node_token`` on the value's link), because this route sends
    no parent of its own: it has no upload leg."""
    assert IN_CELL_IMAGE_MOUNT_POINT == "sheet_image"
    link = READ_BACK["response"]["data"]["valueRange"]["values"][0][0]["link"]
    assert f"mount_point={IN_CELL_IMAGE_MOUNT_POINT}" in link
    assert f"mount_node_token={TOK}" in link


def test_there_is_no_SECOND_hash_comparison_in_the_module():
    """The one definition of *the bytes that came back are the bytes that went up* stays
    the one definition — this module hashes nothing itself."""
    source = Path(sheets_media.__file__).read_text(encoding="utf-8")
    assert "hashlib" not in source
    for smell in ("sha256(", "digest()", "== got", "!= got"):
        assert smell not in source, smell


def test_the_download_leg_can_never_upload():
    """The client this op takes is the drive media family's **download** leg. An upload is
    refused locally, because this route has none and a stray upload would mint permanent
    residue nothing on a sheet would ever point at."""
    assert SheetsMediaClient.ALLOWED_PARENT_TYPES == ()
    media = SheetsMediaClient("app", "secret", sdk_client=object())
    with pytest.raises(MediaUploadError):
        media.upload(data=PNG, name=NAME, parent_type="sheet_image", parent_node=TOK)


# --------------------------------------------------------------------------- #
# AC5 — the int-array body is a SIZE CEILING, and it is measurable             #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_the_int_array_body_inflates_the_wire_about_three_to_four_times():
    """The disclosure, driven rather than recited: the bytes go up as a JSON array of
    integers, so the payload on the wire is ~3–4× the file's own size. A consumer sizing
    an upload budget from the file's size will under-provision."""
    opener = _round_trip_opener()
    put_image_in_sheet(client=_sheets_client(opener), spreadsheet_token=TOK,
                       a1_range=RANGE, data=PNG, name=NAME)

    on_the_wire = len(json.dumps(opener.requests[0]["body"]["image"]).encode())
    assert 3 * len(PNG) <= on_the_wire <= 5 * len(PNG)


# --------------------------------------------------------------------------- #
# AC4 — the three disclosures ship WITH the op                                 #
# --------------------------------------------------------------------------- #

def test_the_op_discloses_its_own_permanent_token_the_clear_and_the_bad_tab():
    """All three measured disclosures are in the shipped docstrings, not only in an issue:
    the call mints its OWN permanent token, the clear is an ordinary ``""`` write, and a
    bad tab is what ``90215`` answers."""
    text = (sheets_media.__doc__ or "") + (put_image_in_sheet.__doc__ or "")
    lowered = text.lower()
    assert "mints" in lowered and "own" in lowered
    assert "permanent" in lowered and "purge" in lowered
    assert '""' in text and "clear" in lowered
    assert "90215" in text
    assert "int" in lowered and "3" in text and "ceiling" in lowered


def test_the_orphan_token_is_REPORTED_when_the_verification_leg_fails():
    """A failure after the write leaves a permanent token behind. Nothing here issues an
    unrequested cleanup (none exists) — the exception carries the token so the residue is
    nameable rather than lost."""
    opener = _round_trip_opener()
    with pytest.raises(MediaRoundTripError) as exc:
        put_image_in_sheet(client=_sheets_client(opener), spreadsheet_token=TOK,
                           a1_range=RANGE, data=PNG, name=NAME,
                           media=FakeMedia(payload=b"not the bytes"))
    assert getattr(exc.value, "orphan_file_token", None) == FILE_TOKEN


# --------------------------------------------------------------------------- #
# The clear — an ordinary value write, over the same client (CONFORMANCE)      #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_the_clear_is_an_ordinary_empty_value_write():
    """There is no delete verb for an in-cell image: writing ``""`` over the cell is what
    removes it (captures ``305-`` / ``306-``), and it goes through the value-write op this
    library already ships."""
    opener = StubOpener([CLEAR["response"]])
    client = _sheets_client(opener)
    client.put_values(TOK, RANGE, [[""]])

    sent = opener.requests[0]
    assert sent["method"] == CLEAR["request"]["method"]
    assert sent["url"].endswith(CLEAR["request"]["path"])
    assert sent["body"] == CLEAR["request"]["body"]
    assert CLEARED["response"]["data"]["valueRange"]["values"] == [[""]]


# --------------------------------------------------------------------------- #
# The write-side read leg the verdict rides                                    #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_read_value_range_sends_the_captured_GET_with_no_render_option():
    """The measured verdict read carried **no** ``valueRenderOption`` (capture ``203-``),
    and that is the request this leg makes — the shape the ``embed-image`` value was
    observed under."""
    opener = StubOpener([READ_BACK["response"]])
    value_range = _sheets_client(opener).read_value_range(TOK, RANGE)

    sent = opener.requests[0]
    assert sent["method"] == "GET"
    assert sent["url"].endswith(READ_BACK["request"]["path"])
    assert "valueRenderOption" not in sent["url"]
    assert value_range == READ_BACK["response"]["data"]["valueRange"]


def test_read_values_still_asks_for_the_raw_values_it_always_asked_for():
    """The compare-and-swap's before-read is unchanged: ``read_values`` still sends
    ``UnformattedValue`` and still answers the bare matrix."""
    opener = StubOpener([READ_BACK["response"]])
    values = _sheets_client(opener).read_values(TOK, RANGE)

    assert "valueRenderOption=UnformattedValue" in opener.requests[0]["url"]
    assert values == READ_BACK["response"]["data"]["valueRange"]["values"]


def test_uploaded_media_anchor_is_the_shared_type():
    """Not a look-alike: the anchor handed to the shared check is the shared type."""
    anchor = UploadedMedia(file_token=FILE_TOKEN, parent_type=IN_CELL_IMAGE_MOUNT_POINT,
                           parent_node=TOK, size=len(PNG), sha256=sha256_of(PNG))
    assert base_media.verify_round_trip(anchor, PNG) == sha256_of(PNG)
