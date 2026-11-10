"""LD-409 — the Drive **versions** family: ``list_versions`` + ``create_version``.

Offline, against fixtures **derived from the editions spike's committed captures**
(``tests/versions_fixtures.py`` carries the per-name provenance). One region per AC:

* **AC1** the listing pages to exhaustion on Lark's own cursor, with no caller-visible paging;
* **AC2** the typed ``Version`` — exactly the measured fields, epoch-SECOND strings converted
  once and honestly, ``update_time`` absent from the CREATE echo rather than defaulted;
* **AC3** the ABSENCES, stated as data — above all the missing ``revision_id``;
* **AC4** ``obj_type`` required on the wire, its measured refusals typed locally in Lark's own
  words, and an **unmeasured** value passed through rather than presented as refused;
* **AC5** ordering is this library's, and the server's order is never promised;
* **AC6** empty is an empty list; malformed is a typed error carrying Lark's verbatim body;
* **AC7** ``create_version`` with every measured edge (name required, duplicates allowed, no
  length ceiling claimed, no quota claimed);
* **AC8** THE PAIRING — the head revision read immediately BEFORE the create, honest ``None``
  where it is not available;
* **AC9** the op registry rows (``mutates`` explicit) and the permission rows (empty, with
  their reason);
* **AC10** no widen / request / escalate, and a denial arrives verbatim.

**Conformance-tier** (AC13): everything below that pins a product truth this project does not
own — the field set, the epoch-second encoding, the ``1068411`` / ``99992402`` / ``252804105``
refusal bodies, revision-inertness, the empty-vs-denial split — is marked
``@pytest.mark.conformance`` per ``process/doctrine/conformance-tier.md`` (a lens, not a gate).
"""
import datetime
import inspect
import pathlib

import pytest

import versions_fixtures as vfx
from larkdocio.drive import ops
from larkdocio.drive.client import DriveClient
from larkdocio.drive.versions import (
    ABSENCES,
    MEASURED_ACCEPTED_OBJ_TYPES,
    MEASURED_REFUSED_OBJ_TYPES,
    PAIRING_EXACTNESS,
    REVISION_UNAVAILABLE_NOT_DOCX,
    STATUS_VOCABULARY,
    VERSION_FIELDS,
    Version,
    VersionListing,
    VersionRefusedError,
)
from larkdocio.drive.versions_write import CreatedVersion, DriveVersionsWriteClient
from larkdocio.errors import LarkAPIError

DRIVE_PACKAGE = pathlib.Path(inspect.getfile(ops)).parent
VERSIONS_MODULE = DRIVE_PACKAGE / "versions_write.py"

DOC = "Example9668460258a2a652cfde"


def reader(route, **kwargs):
    """A READ-pair drive client whose whole transport is a recording stub."""
    transport = vfx.RecordingTransport(route)
    kwargs.setdefault("token_fetcher", vfx.token_fetcher)
    kwargs.setdefault("rate_limiter", vfx.fast_limiter())
    return DriveClient("app-id", "app-secret", urlopen=transport, **kwargs), transport


def writer(route, **kwargs):
    """A WRITE-pair versions client whose whole transport is a recording stub."""
    transport = vfx.RecordingTransport(route)
    kwargs.setdefault("token_fetcher", vfx.token_fetcher)
    kwargs.setdefault("rate_limiter", vfx.fast_limiter())
    return DriveVersionsWriteClient("app-id", "app-secret", urlopen=transport, **kwargs), \
        transport


class FixedRevision:
    """A stand-in revision reader — the pairing's dependency, injected."""

    def __init__(self, revision):
        self.revision = revision
        self.reads = []

    def read_document_revision(self, document_id):
        self.reads.append(document_id)
        if isinstance(self.revision, Exception):
            raise self.revision
        return self.revision


# --------------------------------------------------------------------------- #
# Provenance — the evidence base is real, and these tests move when it does.     #
# --------------------------------------------------------------------------- #

def test_the_fixtures_are_DERIVED_FROM_THE_COMMITTED_CAPTURES():
    assert vfx.CAPTURES.is_dir()
    assert vfx.response(vfx.LIST_ONE_PAGE)["code"] == 0
    assert len(vfx.items(vfx.LIST_ONE_PAGE)) == 3
    assert vfx.capture(vfx.LIST_PAGE_1)["request"]["path"].endswith(
        "?obj_type=docx&page_size=1&user_id_type=open_id")


# --------------------------------------------------------------------------- #
# AC1 — the listing pages to exhaustion; paging is never the caller's problem.   #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac1_the_walk_follows_the_REAL_page_token_pair_and_makes_EXACTLY_two_calls():
    """Captures 08 + 09: ``page_size=1``, page 2 fetched with page 1's own cursor. **Both**
    pages still report ``has_more: true`` (the document held three versions), so the walk is
    bounded by the page budget — and the budget firing is DISCLOSED, never silent."""
    route = vfx.versions_router([vfx.response(vfx.LIST_PAGE_1), vfx.response(vfx.LIST_PAGE_2)])
    drive, transport = reader(route)

    listing = drive.list_versions(DOC, page_size=1, max_pages=2)

    assert len(transport.calls) == 2
    assert [v.token for v in listing] == ["2fFuFO", "zk0Jss"]
    assert listing.pages == 2
    assert listing.truncation is not None, "a budget that fires silently makes the answer lie"
    assert "max_pages" in listing.truncation.describe()


def test_ac1_the_opaque_cursor_is_ECHOED_VERBATIM_and_never_parsed():
    route = vfx.versions_router([vfx.response(vfx.LIST_PAGE_1), vfx.response(vfx.LIST_PAGE_2)])
    drive, transport = reader(route)

    drive.list_versions(DOC, page_size=1, max_pages=2)

    served = vfx.response(vfx.LIST_PAGE_1)["data"]["page_token"]
    assert "page_token" not in transport.calls[0].params
    assert transport.calls[1].params["page_token"] == served


def test_ac1_a_single_page_listing_STOPS_IN_ONE_CALL():
    """Capture 07 — ``has_more: false``. Termination is Lark's word, not a guess."""
    drive, transport = reader(vfx.versions_router([vfx.response(vfx.LIST_ONE_PAGE)]))

    listing = drive.list_versions(DOC)

    assert len(transport.calls) == 1
    assert len(listing) == 3
    assert listing.truncation is None


def test_ac1_the_listing_rides_the_TOKENISED_endpoint_on_a_GET():
    drive, transport = reader(vfx.versions_router([vfx.response(vfx.LIST_ONE_PAGE)]))
    drive.list_versions(DOC)
    assert transport.calls[0].method == "GET"
    assert transport.calls[0].path == f"/open-apis/drive/v1/files/{DOC}/versions"


# --------------------------------------------------------------------------- #
# AC2 — the typed Version: exactly what was measured, converted once.            #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac2_the_model_carries_EXACTLY_the_keys_the_captures_carry():
    """Bidirectional against the LIST payload: a field the model invents, or one the payload
    carries that the model drops, both redden."""
    payload = vfx.items(vfx.LIST_ONE_PAGE)[0]
    renamed = {"token" if key == "version" else key for key in payload}
    assert renamed == set(VERSION_FIELDS)


@pytest.mark.conformance
def test_ac2_the_payloads_version_key_becomes_TOKEN_and_the_rename_is_stated():
    payload = vfx.items(vfx.LIST_ONE_PAGE)[0]
    version = Version.from_payload(payload)
    assert version.token == payload["version"] == "2fFuFO"
    assert not hasattr(version, "version"), "the rename happens once, in one place"
    assert "version" in Version.__doc__ and "token" in Version.__doc__


@pytest.mark.conformance
def test_ac2_create_time_is_a_STRING_OF_EPOCH_SECONDS_carried_AS_SERVED():
    payload = vfx.items(vfx.LIST_ONE_PAGE)[0]
    version = Version.from_payload(payload)
    assert version.create_time == "1786403295"
    assert isinstance(version.create_time, str), "not ms, not ISO — a string of seconds"


@pytest.mark.conformance
def test_ac2_the_ONE_honest_conversion_is_UTC_anchored_because_epoch_is():
    """No timezone field is served, so none is assumed: epoch is UTC by definition and the
    conversion says so rather than picking the machine's local zone."""
    version = Version.from_payload(vfx.items(vfx.LIST_ONE_PAGE)[0])
    assert version.created_at == datetime.datetime.fromtimestamp(
        1786403295, datetime.timezone.utc)
    assert version.created_at.tzinfo is datetime.timezone.utc
    assert version.updated_at == datetime.datetime.fromtimestamp(
        1786403295, datetime.timezone.utc)


@pytest.mark.conformance
def test_ac2_update_time_is_ABSENT_from_the_CREATE_echo_and_is_NOT_defaulted():
    """The make-or-break honesty of the create arm: capture 02's ``data`` carries no
    ``update_time``, so the model reports ``None`` rather than copying ``create_time`` into it
    and inventing an update that never happened."""
    echo = vfx.created_payload()
    assert "update_time" not in echo
    version = Version.from_payload(echo)
    assert version.update_time is None
    assert version.updated_at is None
    assert version.create_time == echo["create_time"]


@pytest.mark.conformance
def test_ac2_status_is_zero_everywhere_observed_and_its_vocabulary_is_UNMEASURED():
    observed = {row["status"] for row in
                vfx.items(vfx.LIST_ONE_PAGE) + vfx.items(vfx.SHEET_LIST)}
    assert observed == {0}
    assert STATUS_VOCABULARY == "unmeasured"
    assert "unmeasured" in Version.__doc__
    for word in ("enumerat", "means"):
        assert f"status {word}" not in Version.__doc__.lower()


def test_ac2_a_malformed_epoch_string_is_NOT_guessed_at():
    version = Version.from_payload(dict(vfx.items(vfx.LIST_ONE_PAGE)[0], create_time="soon"))
    assert version.create_time == "soon"
    assert version.created_at is None


# --------------------------------------------------------------------------- #
# AC3 — the ABSENCES, because a ledger built on a guessed field mis-syncs.       #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac3_the_captured_version_object_carries_NONE_of_the_absent_fields():
    carried = set()
    for name in (vfx.LIST_ONE_PAGE, vfx.SHEET_LIST):
        for row in vfx.items(name):
            carried |= set(row)
    carried |= set(vfx.created_payload())
    for absent in ABSENCES:
        assert absent not in carried, f"{absent} IS carried — the absence claim is stale"


def test_ac3_every_absence_STATES_ITS_CONSEQUENCE_and_revision_id_names_LD_410():
    for absent in ("revision_id", "url", "description", "size", "document_id",
                   "creator_name", "is_latest"):
        assert absent in ABSENCES, absent
        assert ABSENCES[absent].strip(), f"{absent} is listed with no reason"
    assert "cannot be resolved to a revision or to content" in ABSENCES["revision_id"]
    assert "create_version does exactly that" in ABSENCES["revision_id"], (
        "the absence must name the cure the library actually ships")


def test_ac3_the_model_docstring_states_the_absences_rather_than_only_the_data():
    for absent in ABSENCES:
        assert absent in Version.__doc__, absent


# --------------------------------------------------------------------------- #
# AC4 — obj_type: required on the wire, and a vocabulary that never over-claims. #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac4_obj_type_is_ALWAYS_ON_THE_WIRE_because_lark_refuses_its_absence():
    """Capture 11: omitting it is HTTP 400 ``99992402 field validation failed``."""
    assert vfx.response(vfx.LIST_NO_OBJ_TYPE)["code"] == 99992402
    drive, transport = reader(vfx.versions_router([vfx.response(vfx.LIST_ONE_PAGE)]))
    drive.list_versions(DOC)
    assert transport.calls[0].params["obj_type"] == "docx"


@pytest.mark.conformance
def test_ac4_an_EMPTY_obj_type_is_refused_LOCALLY_in_larks_own_words():
    drive, transport = reader(vfx.versions_router([]))
    with pytest.raises(VersionRefusedError) as excinfo:
        drive.list_versions(DOC, obj_type="")
    assert transport.calls == [], "a locally-knowable refusal never reaches the wire"
    assert "99992402" in str(excinfo.value)
    assert "obj_type is required" in str(excinfo.value)


@pytest.mark.conformance
@pytest.mark.parametrize("value,code", [("bitable", 1068411), ("sheets", 99992402)])
def test_ac4_a_MEASURED_REFUSED_obj_type_is_refused_locally_quoting_LARKS_OWN_BODY(value, code):
    drive, transport = reader(vfx.versions_router([]))
    with pytest.raises(VersionRefusedError) as excinfo:
        drive.list_versions(DOC, obj_type=value)
    assert transport.calls == []
    assert str(code) in str(excinfo.value)
    assert MEASURED_REFUSED_OBJ_TYPES[value].msg in str(excinfo.value)


@pytest.mark.conformance
def test_ac4_the_refusal_bodies_are_QUOTED_FROM_THE_CAPTURES_not_paraphrased():
    for value, capture_name in (("bitable", vfx.OBJ_TYPE_BITABLE_REFUSED),
                                ("sheets", vfx.OBJ_TYPE_SHEETS_REFUSED)):
        body = vfx.response(capture_name)
        assert MEASURED_REFUSED_OBJ_TYPES[value].code == body["code"]
        assert MEASURED_REFUSED_OBJ_TYPES[value].msg == body["msg"]


@pytest.mark.conformance
def test_ac4_the_MEASURED_ACCEPTED_pair_is_docx_and_sheet_and_sheet_really_works():
    assert MEASURED_ACCEPTED_OBJ_TYPES == ("docx", "sheet")
    drive, transport = reader(vfx.versions_router([vfx.response(vfx.SHEET_LIST)]))
    listing = drive.list_versions("Examplea1f244ad7022d85b5341", obj_type="sheet")
    assert transport.calls[0].params["obj_type"] == "sheet"
    assert [v.obj_type for v in listing] == ["sheet"]


def test_ac4_an_UNMEASURED_obj_type_is_PASSED_THROUGH_never_presented_as_refused():
    """The chosen policy (issue § Decision): this library refuses only what it MEASURED being
    refused. ``mindnote`` was never tried, so Lark answers for it — larkdocio does not author a
    limit it never observed."""
    served = {"code": 1068411, "msg": "params error, param [obj_type] is wrong"}
    drive, transport = reader(vfx.versions_router([served]))
    with pytest.raises(LarkAPIError) as excinfo:
        drive.list_versions(DOC, obj_type="mindnote")
    assert transport.calls[0].params["obj_type"] == "mindnote", "it reached the wire"
    assert "1068411" in str(excinfo.value)


def test_ac4_the_shipped_wording_says_UNMEASURED_NOT_REFUTED():
    doc = DriveClient.list_versions.__doc__
    assert "unmeasured" in doc.lower()
    assert "not refuted" in doc.lower()
    for untried in ("doc", "mindnote", "file", "slides", "wiki"):
        assert untried in doc, untried


# --------------------------------------------------------------------------- #
# AC5 — ordering is CLIENT-SIDE; the server's order is never promised.           #
# --------------------------------------------------------------------------- #

def test_ac5_a_shuffled_page_comes_back_NEWEST_FIRST():
    served = vfx.response(vfx.LIST_ONE_PAGE)
    shuffled = dict(served, data=dict(served["data"], items=list(
        reversed(served["data"]["items"]))))
    drive, _t = reader(vfx.versions_router([shuffled]))

    listing = drive.list_versions(DOC)

    assert [v.create_time for v in listing] == ["1786403295", "1786403291", "1786403291"]


def test_ac5_a_TIE_is_broken_DETERMINISTICALLY_by_token():
    """Two of the three captured versions share a ``create_time`` to the second, so the tie is
    real rather than hypothetical — and an unstable order would make a ledger diff noise."""
    served = vfx.response(vfx.LIST_ONE_PAGE)
    forward, _t = reader(vfx.versions_router([served]))
    backward, _t2 = reader(vfx.versions_router([dict(served, data=dict(
        served["data"], items=list(reversed(served["data"]["items"]))))]))

    assert [v.token for v in forward.list_versions(DOC)] == \
        [v.token for v in backward.list_versions(DOC)] == ["2fFuFO", "2sDlEF", "zk0Jss"]


def test_ac5_the_docstring_says_the_servers_own_order_was_OBSERVED_not_promised():
    doc = DriveClient.list_versions.__doc__.lower()
    assert "observed" in doc
    assert "not enough to rely on" in doc or "never promised" in doc


# --------------------------------------------------------------------------- #
# AC6 — empty is never a disguised denial.                                      #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac6_a_never_versioned_document_answers_an_EMPTY_LIST_and_no_error():
    body = vfx.response(vfx.LIST_EMPTY)
    assert body["code"] == 0 and body["data"]["items"] == []
    drive, _t = reader(vfx.versions_router([body]))

    listing = drive.list_versions("Example32b94e66a5ef64e659d2")

    assert list(listing) == []
    assert listing.truncation is None


@pytest.mark.conformance
def test_ac6_a_MALFORMED_request_raises_carrying_LARKS_VERBATIM_code_and_message():
    body = vfx.response(vfx.LIST_NO_OBJ_TYPE)
    drive, _t = reader(vfx.versions_router([body]))

    with pytest.raises(LarkAPIError) as excinfo:
        drive.list_versions(DOC)

    assert excinfo.value.code == 99992402
    assert excinfo.value.msg == "field validation failed"


def test_ac6_the_distinction_is_STATED_where_a_caller_will_read_it():
    doc = DriveClient.list_versions.__doc__.lower()
    assert "empty" in doc and "denial" in doc


# --------------------------------------------------------------------------- #
# AC7 — create_version, with every measured edge.                               #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac7_the_response_DATA_IS_THE_VERSION_OBJECT_with_no_wrapper():
    echo = vfx.created_payload()
    assert "version" in echo and "data" not in echo
    client, transport = writer(
        vfx.versions_router([], create=vfx.response(vfx.CREATE)))

    created = client.create_version(DOC, "LD-404 V1.0", revision_reader=FixedRevision(2))

    assert isinstance(created, CreatedVersion)
    assert created.version.token == "2sDlEF"
    assert created.version.name == "LD-404 V1.0"
    assert transport.calls[0].method == "POST"
    assert transport.calls[0].body == {"name": "LD-404 V1.0", "obj_type": "docx"}


@pytest.mark.conformance
@pytest.mark.parametrize("name", [None, "", "   "])
def test_ac7_a_MISSING_NAME_is_refused_LOCALLY_mirroring_larks_own_message(name):
    body = vfx.response(vfx.CREATE_NO_NAME)
    assert body["code"] == 252804105
    client, transport = writer(vfx.versions_router([], create=body))

    with pytest.raises(VersionRefusedError) as excinfo:
        client.create_version(DOC, name, revision_reader=FixedRevision(2))

    assert transport.calls == [], "the refusal is typed BEFORE the call"
    assert "252804105" in str(excinfo.value)
    assert "Params error, param [name] is wrong." in str(excinfo.value)


@pytest.mark.conformance
def test_ac7_DUPLICATE_names_are_ALLOWED_and_DISCLOSED_never_deduped():
    """Capture 104: a second ``V1.0`` came back as ``V1.0(1)`` with a distinct token. The
    library neither refuses it, nor warns it away, nor pretends the echoed name is the sent
    one."""
    echo = vfx.created_payload(vfx.CREATE_DUPLICATE)
    assert echo["name"] == "V1.0(1)" and echo["version"] == "jukIsS"
    client, _t = writer(
        vfx.versions_router([], create=vfx.response(vfx.CREATE_DUPLICATE)))

    created = client.create_version("Example923c2c2d4498ddcbef50", "V1.0",
                                    revision_reader=FixedRevision(2))

    assert created.version.name == "V1.0(1)", "the ECHO is what is reported, not the request"
    assert created.requested_name == "V1.0"
    assert created.name_was_changed_by_lark is True
    assert "duplicate" in DriveVersionsWriteClient.create_version.__doc__.lower()


@pytest.mark.conformance
def test_ac7_NO_LENGTH_CEILING_is_claimed_because_300_characters_were_ACCEPTED():
    sent = vfx.capture(vfx.CREATE_300_CHAR)["request"]["body"]["name"]
    echoed = vfx.created_payload(vfx.CREATE_300_CHAR)["name"]
    assert len(sent) == 300 and echoed == sent
    client, _t = writer(vfx.versions_router([], create=vfx.response(vfx.CREATE_300_CHAR)))

    created = client.create_version("Example923c2c2d4498ddcbef50", sent,
                                    revision_reader=FixedRevision(2))

    assert created.version.name == sent
    doc = DriveVersionsWriteClient.create_version.__doc__.lower()
    assert "300" in doc and "unmeasured" in doc


def test_ac7_NO_QUOTA_is_claimed_the_shipped_words_are_NO_QUOTA_DISCLOSED():
    doc = DriveVersionsWriteClient.create_version.__doc__
    assert "no quota disclosed" in doc.lower()
    assert "there is no quota" not in doc.lower()


# --------------------------------------------------------------------------- #
# AC8 — THE PAIRING, which is the whole point of shipping create.               #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac8_the_head_revision_is_read_BEFORE_the_create_and_returned_WITH_it():
    revision_reader = FixedRevision(vfx.head_revision(vfx.HEAD_BEFORE))
    client, transport = writer(vfx.versions_router([], create=vfx.response(vfx.CREATE)))

    created = client.create_version(DOC, "LD-404 V1.0", revision_reader=revision_reader)

    assert revision_reader.reads == [DOC]
    assert created.revision == 2
    assert created.triple == ("LD-404 V1.0", "2sDlEF", 2)


@pytest.mark.conformance
def test_ac8_the_revision_read_HAPPENS_FIRST_not_after_the_write():
    order = []

    class Ordered(FixedRevision):
        def read_document_revision(self, document_id):
            order.append("revision")
            return super().read_document_revision(document_id)

    def create(call):
        order.append("create")
        return vfx.response(vfx.CREATE)

    client, _t = writer(vfx.versions_router([], create=create))
    client.create_version(DOC, "LD-404 V1.0", revision_reader=Ordered(2))

    assert order == ["revision", "create"]


@pytest.mark.conformance
def test_ac8_the_exactness_condition_is_stated_AS_MEASURED_revision_INERTNESS():
    """Captures 101 / 103: head ``2`` before the create and ``2`` after. So the triple is exact
    absent a concurrent edit — and the concurrent edit is named as the one thing that breaks
    it, rather than the pairing being sold as unconditional."""
    assert vfx.head_revision(vfx.HEAD_BEFORE) == vfx.head_revision(vfx.HEAD_AFTER) == 2
    for phrase in ("revision-inert", "concurrent edit"):
        assert phrase in PAIRING_EXACTNESS, phrase
        assert phrase in DriveVersionsWriteClient.create_version.__doc__, phrase


def test_ac8_a_FAILED_revision_read_leaves_the_field_NONE_with_its_reason():
    client, _t = writer(vfx.versions_router([], create=vfx.response(vfx.CREATE)))

    created = client.create_version(
        DOC, "LD-404 V1.0", revision_reader=FixedRevision(RuntimeError("Lark said no")))

    assert created.revision is None, "never synthesized, and never zero"
    assert "Lark said no" in created.revision_note
    assert created.version.token == "2sDlEF", "the create still succeeded and is reported"


def test_ac8_a_SHEET_version_has_no_docx_revision_so_none_is_read_or_invented():
    revision_reader = FixedRevision(2)
    client, _t = writer(vfx.versions_router([], create=vfx.response(vfx.SHEET_CREATE)))

    created = client.create_version("Examplea1f244ad7022d85b5341", "LD-404 sheet",
                                    obj_type="sheet", revision_reader=revision_reader)

    assert revision_reader.reads == [], "no docx meta call is made for a sheet"
    assert created.revision is None
    assert created.revision_note == REVISION_UNAVAILABLE_NOT_DOCX.format(obj_type="sheet")


def test_ac8_the_DEFAULT_revision_reader_is_the_write_pairs_own_one_call_meta_read():
    """Not injected: the shipped default path, over the same recording transport, so the leg
    the permission derivation sees is the leg that actually runs."""
    route = vfx.meta_router(vfx.response(vfx.HEAD_BEFORE),
                            vfx.versions_router([], create=vfx.response(vfx.CREATE)))
    client, transport = writer(route)

    created = client.create_version(DOC, "LD-404 V1.0")

    assert [call.path for call in transport.calls] == [
        f"/open-apis/docx/v1/documents/{DOC}",
        f"/open-apis/drive/v1/files/{DOC}/versions",
    ]
    assert created.revision == 2


# --------------------------------------------------------------------------- #
# AC9 — the op registry rows, and the permission rows.                          #
# --------------------------------------------------------------------------- #

def test_ac9_both_ops_are_REGISTERED_with_mutates_declared_EXPLICITLY():
    assert ops.op("list_versions").mutates is False
    assert ops.op("list_versions").http_method == "GET"
    assert ops.op("list_versions").paged is True
    assert ops.op("create_version").mutates is True
    assert ops.op("create_version").http_method == "POST"


def test_ac9_the_endpoint_is_a_MODULE_LEVEL_CONSTANT_in_the_tokenised_shape():
    """``permissions.endpoints_of`` walks a call site's own source; an endpoint reachable only
    at runtime is invisible to it (LD-324's recorded reason)."""
    assert ops.FILE_VERSIONS_ENDPOINT == "/open-apis/drive/v1/files/:file_token/versions"
    assert ops.op("list_versions").endpoint == ops.FILE_VERSIONS_ENDPOINT
    assert ops.op("create_version").endpoint == ops.FILE_VERSIONS_ENDPOINT


def test_ac9_the_READ_ONLY_claim_is_TRANSFORMED_not_deleted():
    """D-24: preserve the reason, supersede only the conclusion. The R1 enumeration really was
    read-only end to end and still is — so the claim is re-scoped to the ops it was true of,
    and the surface-wide answer moves honestly to ``False``."""
    assert ops.read_only() is False, "create_version mutates; the whole-surface claim is over"
    assert ops.read_only(ops.ENUMERATION_OPS) is True
    assert {d.name for d in ops.ENUMERATION_OPS} == {
        "list_folder_children", "root_folder_token", "folder_name"}
    assert "create_version" in {d.name for d in ops.mutating_ops()}
    assert "LD-409" in ops.read_only.__doc__ or "LD-409" in ops.__doc__
    # The set itself is no longer this family's to pin: LD-432 registered the access ops and
    # re-applied the SAME rule (the reason is unchanged; only the conclusion for the whole
    # registry moved). What this family owns is that ITS op is in there and declares itself.
    assert ops.op("create_version").mutates is True


def test_ac9_the_declared_QUERY_POSTS_are_still_the_reason_mutates_is_not_derived():
    """Now provable from both sides: a POST that declares ``False`` and a POST that declares
    ``True`` live in the same registry.

    **RE-SCOPED by LD-487 (D-24), not weakened.** A second declared-read POST joined the
    registry (``document_security_level``), so the set is two; the argument this test carries —
    that ``mutates`` is a declaration and never a verb inference — is untouched, and both halves
    are still asserted by name so a silent reclassification reddens."""
    assert {d.name for d in ops.query_posts()} == {"folder_name", "document_security_level"}
    assert all(d.mutates is False for d in ops.query_posts())
    posts = {d.name for d in ops.OPS if d.http_method == "POST"}
    assert {"folder_name", "create_version"} <= posts


def test_ac9_the_permission_rows_land_EMPTY_WITH_THEIR_REASON_on_both_modes():
    from larkdocio import permissions

    rows = [row for row in permissions.ENDPOINT_SCOPES
            if row[0] == ops.FILE_VERSIONS_ENDPOINT]
    assert {row[1] for row in rows} == {"read", "write"}
    for _prefix, _mode, scopes, reason in rows:
        assert scopes == (), "no scope string has ever been observed demanded here"
        assert "alias" in reason.lower(), "the aliasing is why a same-tenant success proves nothing"
        assert "not guessed" in reason.lower()


def test_ac9_NO_INVENTED_SCOPE_STRING_rides_in_on_the_new_rows():
    from larkdocio import permissions

    known_before = {
        scope.scope
        for prefix, _m, scopes, _n in permissions.ENDPOINT_SCOPES
        for scope in scopes
        if prefix != ops.FILE_VERSIONS_ENDPOINT
    }
    added = {
        scope.scope
        for prefix, _m, scopes, _n in permissions.ENDPOINT_SCOPES
        for scope in scopes
        if prefix == ops.FILE_VERSIONS_ENDPOINT
    }
    assert added <= known_before, f"a scope string was authored here: {sorted(added)}"


def test_ac9_the_registry_DERIVES_both_ops_endpoints_from_their_own_source():
    from larkdocio import permissions

    listing = permissions.endpoints_of(DriveClient.list_versions)
    creating = permissions.endpoints_of(DriveVersionsWriteClient.create_version)
    assert ops.FILE_VERSIONS_ENDPOINT in listing
    assert ops.FILE_VERSIONS_ENDPOINT in creating
    assert any("/open-apis/docx/v1/documents" in e for e in creating), (
        "the pairing's revision read is a real leg and must derive as one")


def test_ac9_capabilities_reports_BOTH_OPS():
    import larkdocio

    surfaces = larkdocio.capabilities(full=True)["surfaces"]
    assert "list_versions" in {op["name"] for op in surfaces["drive-read"]["operations"]}
    versions_write = surfaces["drive-versions-write"]
    assert versions_write["mode"] == "write"
    assert "create_version" in {op["name"] for op in versions_write["operations"]}


def test_ac9_the_drive_read_surfaces_scopes_stay_the_UNION_OF_ITS_OPS_ROWS():
    import larkdocio

    from larkdocio import permissions

    surface = larkdocio.capabilities(full=True)["surfaces"]["drive-read"]
    projected, optional = permissions.surface_scope_projection("drive-read")
    assert tuple(surface["credentials"]["scopes"]) == projected
    assert tuple(surface["credentials"]["optional_scopes"]) == optional


# --------------------------------------------------------------------------- #
# AC10 — the library never widens, requests or escalates a scope.               #
# --------------------------------------------------------------------------- #

def test_ac10_a_DENIAL_arrives_with_larks_verbatim_code_and_message_and_is_NOT_retried():
    denial = {"code": 99991672,
              "msg": "Access denied. The app does not have the required scope."}
    client, transport = writer(vfx.versions_router([], create=denial))

    with pytest.raises(LarkAPIError) as excinfo:
        client.create_version(DOC, "V1.0", revision_reader=FixedRevision(2))

    assert excinfo.value.code == 99991672
    assert excinfo.value.msg == denial["msg"]
    assert len([c for c in transport.calls if c.method == "POST"]) == 1, "no retry"


def test_ac10_the_versions_module_NEVER_CROSSES_the_credential_split():
    source = VERSIONS_MODULE.read_text(encoding="utf-8")
    assert "get_read_credentials" not in source, (
        "a write op must never fall back to the read pair (PROJECT.md § Credential doctrine)")
    for widening in ("request_scope", "escalate", "grant_scope"):
        assert widening not in source, widening


def test_ac10_the_READ_client_never_names_the_WRITE_pair_either():
    source = (VERSIONS_MODULE.parent / "client.py").read_text(encoding="utf-8")
    assert "get_write_credentials" not in source
    assert "WRITE_ENV" not in source


# --------------------------------------------------------------------------- #
# The listing result is a LIST a consumer can just use.                         #
# --------------------------------------------------------------------------- #

def test_the_listing_is_iterable_indexable_and_sized_so_it_reads_as_ONE_LIST():
    drive, _t = reader(vfx.versions_router([vfx.response(vfx.LIST_ONE_PAGE)]))
    listing = drive.list_versions(DOC)
    assert isinstance(listing, VersionListing)
    assert len(listing) == 3
    assert listing[0].token == "2fFuFO"
    assert [v.token for v in listing] == list(v.token for v in listing.versions)
