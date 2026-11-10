"""LD-487 — the READ-SIDE surfacing of a document's tenant SECURITY LEVEL.

The field rides ``POST /open-apis/drive/v1/metas/batch_query``, a **documented** open-API route
this library already calls through its own shipped endpoint constant, and until now larkdocio
dropped it for every object. The round-4 belief that a *private* API was needed was measured
false (LD-474: ``sec_label_name_key_present: True`` on a DOCUMENT token, ``residue: []``), so
this is a projection gap and nothing more.

Offline, against fixtures derived from the committed ``06-metas-batch-query`` capture — whose
own rows carry the key — so the payload shape is real rather than hand-mocked.
"""
import inspect
import pathlib
import re

import pytest

import drive_fixtures as fx
from larkdocio.drive import (
    SECURITY_LEVEL_NOT_SETTABLE,
    SECURITY_LEVEL_OUTCOMES,
    SECURITY_LEVEL_UNMEASURED,
    SecurityLevel,
)
from larkdocio.drive import ops
from larkdocio.drive.client import DriveClient
from larkdocio.drive.models import LEVEL_REPORTED, NO_LEVEL_SET, NOT_ANSWERED

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DRIVE_PACKAGE = pathlib.Path(inspect.getfile(ops)).parent
GUIDE = REPO_ROOT / "src" / "larkdocio" / "GUIDE.md"
DRIVE_MD = REPO_ROOT / "DRIVE.md"

TOKEN = "doccnLD487DISPOSABLE"


def client(metas):
    transport = fx.RecordingTransport(fx.listing_router({}, metas=metas))
    return DriveClient("app-id", "app-secret", urlopen=transport,
                       token_fetcher=fx.token_fetcher,
                       rate_limiter=fx.fast_limiter()), transport


# --------------------------------------------------------------------------- #
# AC1 — a shipped read-side operation answers the field, one token per call.   #
# --------------------------------------------------------------------------- #

def test_ac1_the_shipped_op_returns_the_documents_security_level():
    drive, transport = client(fx.document_meta_response(TOKEN, sec_label_name="Label A"))

    answer = drive.document_security_level(TOKEN)

    assert isinstance(answer, SecurityLevel)
    assert answer.level == "Label A"
    assert answer.token == TOKEN
    assert answer.disclosure is None
    assert transport.calls[0].path == ops.METAS_BATCH_QUERY_ENDPOINT
    assert transport.calls[0].method == "POST"


def test_ac1_it_sends_exactly_ONE_token_per_call_no_batch_form():
    """The named slice is the single-token document read; the batched form is not shipped."""
    drive, transport = client(fx.document_meta_response(TOKEN))

    drive.document_security_level(TOKEN)

    body = transport.calls[0].body
    assert body["request_docs"] == [{"doc_token": TOKEN, "doc_type": "docx"}]
    assert body["with_url"] is False
    assert set(body) == {"request_docs", "with_url"}
    parameters = inspect.signature(DriveClient.document_security_level).parameters
    assert set(parameters) == {"self", "document_token", "doc_type"}


def test_ac1_it_rides_the_SAME_shipped_endpoint_constant_as_the_folder_title_leg():
    source = (DRIVE_PACKAGE / "client.py").read_text(encoding="utf-8")
    assert source.count("ops.METAS_BATCH_QUERY_ENDPOINT") == 2
    assert ops.op("document_security_level").endpoint == ops.METAS_BATCH_QUERY_ENDPOINT
    assert ops.op("document_security_level").mutates is False


def test_ac1_the_result_type_is_reachable_from_the_public_package():
    import larkdocio.drive as drive_package

    assert "SecurityLevel" in drive_package.__all__
    assert drive_package.SecurityLevel is SecurityLevel


def test_ac1_an_unmeasured_doc_type_is_PASSED_THROUGH_not_refused_locally():
    """Object types beyond docx are unmeasured, not unsupported — Lark answers for them."""
    drive, transport = client(fx.document_meta_response(TOKEN, sec_label_name=""))

    drive.document_security_level(TOKEN, doc_type="sheet")

    assert transport.calls[0].body["request_docs"][0]["doc_type"] == "sheet"


# --------------------------------------------------------------------------- #
# AC2 — three outcomes, distinguished IN THE TYPE.                             #
# --------------------------------------------------------------------------- #

def test_ac2_a_reported_level_is_carried_verbatim():
    drive, _t = client(fx.document_meta_response(TOKEN, sec_label_name="Label A"))
    answer = drive.document_security_level(TOKEN)
    assert (answer.outcome, answer.reported, answer.no_level_set) == (
        LEVEL_REPORTED, True, False)


def test_ac2_an_EMPTY_string_means_NO_LEVEL_IS_SET_never_absent():
    drive, _t = client(fx.document_meta_response(TOKEN, sec_label_name=""))
    answer = drive.document_security_level(TOKEN)
    assert answer.level == ""
    assert (answer.outcome, answer.reported, answer.no_level_set) == (
        NO_LEVEL_SET, True, True)
    assert answer.disclosure is None


def test_ac2_a_MISSING_key_is_a_DISCLOSURE_and_never_an_invented_empty_string():
    drive, _t = client(fx.document_meta_response(TOKEN, drop_key=True))
    answer = drive.document_security_level(TOKEN)
    assert answer.level is None
    assert (answer.outcome, answer.reported, answer.no_level_set) == (
        NOT_ANSWERED, False, False)
    assert TOKEN in answer.disclosure
    assert "no level set" in answer.disclosure


def test_ac2_a_REFUSAL_degrades_to_the_same_disclosure_case_never_to_no_level():
    drive, _t = client(fx.refusal_response())
    answer = drive.document_security_level(TOKEN)
    assert answer.outcome == NOT_ANSWERED
    assert answer.level is None
    assert "1061002" in answer.disclosure


def test_ac2_an_EMPTY_metas_array_is_a_disclosure_too():
    drive, _t = client({"code": 0, "msg": "Success", "data": {"metas": []}})
    answer = drive.document_security_level(TOKEN)
    assert answer.outcome == NOT_ANSWERED and answer.disclosure


def test_ac2_the_three_outcomes_are_THREE_and_mutually_exclusive():
    cases = [SecurityLevel(TOKEN, level="Label A"),
             SecurityLevel(TOKEN, level=""),
             SecurityLevel(TOKEN, disclosure="could not answer")]
    assert [case.outcome for case in cases] == list(SECURITY_LEVEL_OUTCOMES)
    assert len({case.outcome for case in cases}) == 3


def test_ac2_the_shipped_docstrings_CITE_THE_CONTROL_PAIR_rather_than_asserting_it():
    """The ``""`` = *no level* reading is EARNED by a before-control and a negative control;
    the shipped text has to show that rather than assert the meaning bare."""
    for doc in (DriveClient.document_security_level.__doc__, SecurityLevel.__doc__):
        assert doc
        assert "before control" in doc
        assert "negative control" in doc
        assert "no level" in doc.lower()
    assert '"Label A"' in DriveClient.document_security_level.__doc__


def test_ac2_nothing_normalises_maps_or_ranks_the_value():
    """Whether ``"Label A"`` is a stable id or a localised display string is unknown, so the value
    is carried exactly as Lark said it — an odd value comes back untouched."""
    drive, _t = client(fx.document_meta_response(TOKEN, sec_label_name="标签 B / Label B"))
    assert drive.document_security_level(TOKEN).level == "标签 B / Label B"


# --------------------------------------------------------------------------- #
# AC3 — D-59-scoped claims; the unmeasured list by CITATION, not re-authored.   #
# --------------------------------------------------------------------------- #

def test_ac3_the_unmeasured_disclosure_is_REACHABLE_from_the_new_surface():
    answer = SecurityLevel(TOKEN, level="")
    assert answer.unmeasured is SECURITY_LEVEL_UNMEASURED
    for untried in ("user_access_token", "admin", "product-internal",
                    "localised display string", "gates the open API", "beyond docx"):
        assert untried in answer.unmeasured, untried
    assert "guide()" in answer.unmeasured
    assert "The document's SECURITY LEVEL" in answer.unmeasured


def test_ac3_the_surface_states_READABLE_and_NOT_SETTABLE_BY_ANY_ROUTE_SHIPPED():
    answer = SecurityLevel(TOKEN, level="Label A")
    assert answer.not_settable is SECURITY_LEVEL_NOT_SETTABLE
    assert "settable by NO route this library ships" in answer.not_settable
    assert "never sets, requests, widens or escalates" in answer.not_settable


def test_ac3_the_unmeasured_list_is_AUTHORED_IN_THE_GUIDE_and_only_cited_here():
    """One authored place: the citation must resolve to a section that really exists."""
    guide = GUIDE.read_text(encoding="utf-8")
    assert "### The document's SECURITY LEVEL" in guide
    assert "What is unmeasured, not refuted" in guide


# --------------------------------------------------------------------------- #
# AC5 — the call site is AUTHORED in larkdocio.permissions; nothing is guessed. #
# --------------------------------------------------------------------------- #

def test_ac5_the_new_operation_has_a_permission_row_on_the_read_surface():
    from larkdocio.permissions import permission_registry

    row = permission_registry()[("drive-read", "document_security_level")]
    assert row.mode == "read"
    assert row.endpoints == ("/open-apis/drive/v1/metas/batch_query",)
    assert row.api_using is True


def test_ac5_the_operation_JOINS_the_endpoints_existing_row_and_invents_NO_scope():
    """The endpoint's row records that no scope string has ever been observed demanded. A new
    caller adds no observation, so it adds no scope — the library never widens or guesses one."""
    from larkdocio.permissions import permission_registry, unknown_requirements_for

    rows = permission_registry()
    new = rows[("drive-read", "document_security_level")]
    existing = rows[("drive-read", "folder_name")]
    assert new.scopes == ()
    assert new.optional_scopes == ()
    assert new.scopes == existing.scopes
    unknown = unknown_requirements_for(new.endpoints, new.mode)
    assert unknown == unknown_requirements_for(existing.endpoints, existing.mode)
    assert unknown, "the honest-unknown reason must still travel"
    assert "no scope string has ever been observed demanded" in unknown[0]


# --------------------------------------------------------------------------- #
# AC6 — the matrices and the capability registry move in the same change.      #
# --------------------------------------------------------------------------- #

def test_ac6_capabilities_reports_the_operation_on_the_drive_read_surface():
    import larkdocio

    surface = larkdocio.capabilities(full=True)["surfaces"]["drive-read"]
    names = {op["name"] for op in surface["operations"]}
    assert "document_security_level" in names


def test_ac6_DRIVE_md_no_longer_says_the_library_reads_the_field_for_nothing():
    text = DRIVE_MD.read_text(encoding="utf-8")
    assert "nothing in this library reads or returns the field today" not in text
    assert "document_security_level" in text


def test_ac6_DRIVE_md_register_row_15_KEEPS_its_revisit_trigger():
    """The conclusion moved on the READ half only; the row's revisit trigger is preserved."""
    row = [line for line in DRIVE_MD.read_text(encoding="utf-8").splitlines()
           if line.startswith("| 15 |")]
    assert len(row) == 1
    assert "sets** a level" in row[0]
    assert "stable **id**/**type** pair" in row[0]
    assert "document_security_level" in row[0]


def test_ac6_the_guide_routes_the_reader_to_the_SHIPPED_CALL():
    guide = GUIDE.read_text(encoding="utf-8")
    assert "DriveClient.document_security_level" in guide
    # ...and no longer tells a consumer that no shipped operation returns it.
    assert "No shipped larkdocio operation returns `sec_label_name`" not in guide


# --------------------------------------------------------------------------- #
# AC8 — a READ credential answers the question; no write pair is needed.       #
# --------------------------------------------------------------------------- #

def test_ac8_the_new_path_resolves_the_READ_pair(monkeypatch):
    """Which pair the CODE resolves is testable offline — and it is the only claim made here.
    Under this tenant's credential aliasing a same-tenant live success would prove reach, not
    scope separation, so no such claim is made from a live run."""
    seen = {}

    def fake_read():
        seen["called"] = True
        return ("read-id", "read-secret")

    monkeypatch.setattr("larkdocio.drive.client.get_read_credentials", fake_read)
    monkeypatch.setattr("larkdocio.drive.client.apply_ipv4_pin", lambda: None)
    drive = DriveClient.from_read_credentials(token_fetcher=fx.token_fetcher)
    assert seen["called"] and drive._app_id == "read-id"


def test_ac8_reaching_the_security_level_needs_NO_write_environment(monkeypatch):
    """A run with every ``LARK_WRITE_APP_*`` variable removed still answers."""
    for name in ("LARK_WRITE_APP_ID", "LARK_WRITE_APP_SECRET"):
        monkeypatch.delenv(name, raising=False)
    drive, _t = client(fx.document_meta_response(TOKEN, sec_label_name="Label A"))
    assert drive.document_security_level(TOKEN).level == "Label A"


def test_ac8_the_security_level_leg_names_NO_write_credential_anywhere():
    source = (DRIVE_PACKAGE / "client.py").read_text(encoding="utf-8")
    for forbidden in ("LARK_WRITE_APP", "get_write_credentials", "resolved_write_env"):
        assert forbidden not in source


def test_ac8_the_permission_row_declares_the_READ_credential_pair():
    from larkdocio.permissions import permission_registry

    row = permission_registry()[("drive-read", "document_security_level")]
    assert row.credential_app == "read"
    assert not [env for env in row.credentials_env if "WRITE" in env]


# --------------------------------------------------------------------------- #
# OUT OF SCOPE, held: the folder-title leg is untouched.                       #
# --------------------------------------------------------------------------- #

def test_the_folder_title_legs_request_body_is_BYTE_IDENTICAL_to_before():
    drive, transport = client(fx.folder_meta_response("fldrX", "Plans & Proposals"))

    answer = drive.folder_name("fldrX")

    assert answer.name == "Plans & Proposals"
    assert transport.calls[0].body == {
        "request_docs": [{"doc_token": "fldrX", "doc_type": "folder"}],
        "with_url": False,
    }


def test_no_write_is_attempted_at_the_field_on_any_route():
    """Nothing here sends a security level anywhere: the only body this leg builds carries a
    doc token and a doc type, and the op declares ``mutates: False``."""
    source = (DRIVE_PACKAGE / "client.py").read_text(encoding="utf-8")
    body_lines = [line for line in source.splitlines()
                  if "sec_label_name" in line and "=" in line and "meta[" not in line]
    assert body_lines == []
    assert ops.op("document_security_level").mutates is False
    assert re.search(r'"document_security_level",\s*path=ops\.METAS_BATCH_QUERY_ENDPOINT',
                     source)


def test_the_registry_still_declares_BOTH_query_posts_as_reads():
    assert {d.name for d in ops.query_posts()} == {"folder_name", "document_security_level"}
    assert ops.read_only(ops.ENUMERATION_OPS) is True
    assert "document_security_level" not in {d.name for d in ops.ENUMERATION_OPS}


@pytest.mark.parametrize("name", ["folder_name", "document_security_level"])
def test_both_legs_on_the_shared_endpoint_declare_mutates_False(name):
    assert ops.op(name).mutates is False
