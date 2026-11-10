"""The spreadsheet FILE-lifecycle surface — create / delete a workbook (LD-176).

The disposables doctrine is a whole section of the shipped guide, and until this issue a
consumer could not follow it for spreadsheets: ``SheetsWriteClient`` had no create and no
delete, and a package-wide sweep found no spreadsheet creator at all — so the round-3
dogfood seat left the library for raw ``urllib`` to make and trash its own disposable sheet.
The docx twins (``WriteClient.create_document`` / ``.delete_document``) existed but appeared
0 times in ``guide()`` and 0 times in ``capabilities()``.

This module is the offline half of the fix:

* **AC1** — the two shipped calls speak the proven wire shapes, byte-exact against the
  write spike's own captured create (``tests/captures/sheets-write-spike/captures/00-smoke.json``) and
  the delete the spike + the round-3 close-out both performed
  (``DELETE …/drive/v1/files/{tok}?type=sheet``), ride the shared ≤3/s WRITE throttle, and
  are typed on every failure;
* **AC2** — the harness's raw create/delete HTTP construction is GONE: its lifecycle
  gateway delegates to the shipped methods, so the shipped path is the exercised path;
* **AC3** — all FOUR lifecycle calls (the two new sheets ones and the two existing docx
  ones) surface in ``capabilities()``;
* **AC4** — the guide's disposables doctrine gains a runnable create → use → delete recipe
  whose ``finally``-delete fires even when the body raises;
* **AC6** — a delete's blast radius is unambiguous: it trashes the whole FILE, not a tab.

The live arm (create → use → delete → confirm-deleted, twice, zero orphans) is
``tests/test_live_sheets_lifecycle_gate.py``.
"""
import json
import tempfile
from pathlib import Path

import pytest

import capability_rows as rows
from larkdocio.common.transport import WriteTransport
from larkdocio.errors import LarkAPIError, MissingDestinationError
from larkdocio.sheets.write_client import (
    FILE_ALREADY_DELETED_CODE,
    SPREADSHEET_GONE_CODE,
    SheetsWriteClient,
    spreadsheet_is_gone,
)

from write_harness import CountingTransport, FakeClock, _FakeHTTPResponse

_ROOT = Path(__file__).resolve().parent.parent

# The write spike's own captured v3 create — a real, proven call (method / path / body /
# response), so AC1's wire assertions are byte-exact against Lark rather than plausible.
_SMOKE = json.loads(
    (_ROOT / "tests" / "captures" / "sheets-write-spike" / "captures" / "00-smoke.json")
    .read_text(encoding="utf-8")
)
_CREATE = _SMOKE["create"]

#: The delete the spike (``dev/sheets-write-spike/probes/_lib.py``) and the round-3 close-out
#: both performed on a disposable: ``DELETE /open-apis/drive/v1/files/{tok}?type=sheet``.
_DELETE_PATH = "/open-apis/drive/v1/files/{token}"
_DELETE_QUERY = "type=sheet"

_TOK = _CREATE["response"]["data"]["spreadsheet"]["spreadsheet_token"]


# --------------------------------------------------------------------------- #
# Offline doubles — a fake clock + a stub opener (the tests/test_sheets_write_ #
# client.py shape, so both write-client suites share one harness posture).      #
# --------------------------------------------------------------------------- #


class StubOpener:
    """Records each urllib request; answers the next queued payload."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.requests = []

    def __call__(self, req, timeout=30):
        body = json.loads(req.data.decode()) if req.data else None
        self.requests.append({
            "method": req.get_method(),
            "url": req.full_url,
            "body": body,
            "auth": req.headers.get("Authorization"),
        })
        return _FakeHTTPResponse(self._payloads[len(self.requests) - 1])


def client_for(opener, transport=None):
    clock = FakeClock()
    return SheetsWriteClient(
        "app", "secret", "larksuite.com",
        transport=transport or WriteTransport(
            max_writes_per_sec=3, time_fn=clock.time, sleep_fn=clock.sleep),
        urlopen=opener,
        token_fetcher=lambda *a, **k: "t-test",
    )


def _gone_payload():
    """What a **sheets** call against a trashed token answers (live-observed)."""
    return {"code": SPREADSHEET_GONE_CODE, "msg": "Path param :spreadsheet_token is deleted"}


def _already_deleted_payload():
    """What the **Drive file delete** answers for a file already in the trash — the live arm's
    own observation (2026-07-30), and a different code from the sheets one above."""
    return {"code": FILE_ALREADY_DELETED_CODE, "msg": "file has been delete."}


# --------------------------------------------------------------------------- #
# AC1 — create_spreadsheet: the proven v3 wire shape, byte-exact                #
# --------------------------------------------------------------------------- #

def test_create_spreadsheet_matches_the_captured_v3_create_method_path_body():
    """AC1: a TITLED create is byte-exact against the spike's captured live call — **plus the
    destination**, which is the one key the capture predates.

    The capture was taken when a destination was optional, so its body is ``{"title": …}`` and
    the workbook it made went into the application's own space. The route did not move: the
    method, the path and the auth header are still asserted against the capture verbatim, and
    the body is the capture's body **with the caller's folder_token added** — which is exactly
    what changed and all that changed.
    """
    opener = StubOpener([_CREATE["response"]])
    client = client_for(opener)

    spreadsheet = client.create_spreadsheet(_CREATE["request_body"]["title"],
                                            folder_token="fldrTOKEN")

    req = opener.requests[0]
    assert req["method"] == _CREATE["method"] == "POST"
    assert req["url"].endswith(_CREATE["path"])
    assert req["body"] == {**_CREATE["request_body"], "folder_token": "fldrTOKEN"}
    assert req["auth"] == "Bearer t-test"
    assert spreadsheet["spreadsheet_token"] == _TOK


def test_create_spreadsheet_untitled_still_sends_the_title_key():
    """AC1 (the amplifier's second body shape): an UNTITLED create still sends ``title: ""``
    — the docx twin's shape, so the body is one predictable form rather than two. The title
    stays optional; only the destination became required."""
    opener = StubOpener([_CREATE["response"]])
    client = client_for(opener)

    client.create_spreadsheet(folder_token="fldrTOKEN")

    assert opener.requests[0]["body"] == {"title": "", "folder_token": "fldrTOKEN"}


def test_create_spreadsheet_REFUSES_when_no_folder_token_is_given():
    """AC1, TRANSFORMED: ``folder_token`` used to be optional and omitted when absent, on the
    reading that the app owns what it creates in its own space. That space has no human
    interface — nothing can browse it, its trash cannot be listed, and a delete there is a
    trash rather than a purge — so an omitted destination made an object nobody could find
    again. The destination is now **required** and every spelling of "none" refuses locally,
    with **zero** calls. The wire shape when one IS given is unchanged."""
    opener = StubOpener([_CREATE["response"]])
    client = client_for(opener)

    for spelling in (None, "", "   "):
        with pytest.raises(MissingDestinationError):
            client.create_spreadsheet("t", folder_token=spelling)
    assert opener.requests == []

    client.create_spreadsheet("t", folder_token="fldrTOKEN")
    assert opener.requests[0]["body"] == {"title": "t", "folder_token": "fldrTOKEN"}


def test_create_spreadsheet_returns_the_spreadsheet_object_with_its_token():
    """AC1 (the amplifier): the created token is CAPTURED and handed back — a create whose
    token is dropped is an orphan by construction."""
    opener = StubOpener([_CREATE["response"]])
    client = client_for(opener)

    spreadsheet = client.create_spreadsheet("larkdocio-harness-DISPOSABLE-x",
                                            folder_token="fldrTOKEN")

    assert spreadsheet["spreadsheet_token"] == _TOK
    assert spreadsheet["url"].endswith(_TOK)


def test_create_spreadsheet_raises_loudly_when_the_payload_carries_no_token():
    """AC1: a code-0 reply with no ``spreadsheet_token`` is an API drift, not a success —
    returning it would hand back an unusable object and leak whatever was created."""
    opener = StubOpener([{"code": 0, "data": {"spreadsheet": {"title": "t"}}}])
    client = client_for(opener)

    with pytest.raises(LarkAPIError) as exc:
        client.create_spreadsheet("t", folder_token="fldrTOKEN")
    assert "spreadsheet_token" in str(exc.value)


def test_create_spreadsheet_types_a_non_zero_code():
    """AC1: a non-zero Lark code raises the typed taxonomy, carrying the code."""
    opener = StubOpener([{"code": 1310213, "msg": "no permission"}])
    client = client_for(opener)

    with pytest.raises(LarkAPIError) as exc:
        client.create_spreadsheet("t", folder_token="fldrTOKEN")
    assert exc.value.code == 1310213


# --------------------------------------------------------------------------- #
# AC1 / AC6 — delete_spreadsheet: the drive-v1 file trash, and WHAT it destroys  #
# --------------------------------------------------------------------------- #

def test_delete_spreadsheet_hits_drive_v1_files_with_type_sheet():
    """AC1: the delete is the proven ``DELETE …/drive/v1/files/{tok}?type=sheet`` — the
    file-level trash, which is why AC6 insists the docstring says so."""
    opener = StubOpener([{"code": 0, "data": {}}])
    client = client_for(opener)

    client.delete_spreadsheet(_TOK)

    req = opener.requests[0]
    assert req["method"] == "DELETE"
    assert req["url"].endswith(
        _DELETE_PATH.format(token=_TOK) + "?" + _DELETE_QUERY)
    assert req["body"] is None


def test_deleting_an_already_deleted_token_raises_the_typed_gone_error():
    """AC1 (the amplifier's idempotency case): a second delete is a clear TYPED error
    carrying Lark's already-deleted code — never a hang and never a silent success. Every
    ``finally``-delete hits this path whenever a test fails mid-run.

    The payload is the one the LIVE arm observed (2026-07-30): the Drive file delete answers
    **``1061007 file has been delete.``** for a file already in the trash — NOT the
    ``1310249`` a *sheets* call against a trashed token answers. Two endpoints, two codes;
    the offline doubles used to assume one, which is what the live run corrected."""
    opener = StubOpener([{"code": 0, "data": {}}, _already_deleted_payload()])
    client = client_for(opener)

    client.delete_spreadsheet(_TOK)
    with pytest.raises(LarkAPIError) as exc:
        client.delete_spreadsheet(_TOK)

    assert exc.value.code == FILE_ALREADY_DELETED_CODE == 1061007
    assert spreadsheet_is_gone(exc.value), (
        "an already-deleted delete must be recognisable as 'already gone' — that is the one "
        "outcome a finally-delete may forgive")


def test_the_two_gone_codes_are_shipped_with_one_predicate_over_them():
    """AC1: a consumer's ``finally`` must not have to know which endpoint answers which
    number. Both codes ship as constants, and ONE predicate spans them:

    * ``SPREADSHEET_GONE_CODE`` (``1310249``) — what a **sheets** call against a trashed
      token answers (``Path param :spreadsheet_token is deleted``). This is the
      **confirmation** code: it is how you prove a file is really gone.
    * ``FILE_ALREADY_DELETED_CODE`` (``1061007``) — what the **Drive file delete** answers for
      a file already in the trash. This is the code a teardown forgives.
    """
    from larkdocio.sheets import write_client

    assert write_client.SPREADSHEET_GONE_CODE == 1310249
    assert write_client.FILE_ALREADY_DELETED_CODE == 1061007

    for code in (SPREADSHEET_GONE_CODE, FILE_ALREADY_DELETED_CODE):
        assert spreadsheet_is_gone(LarkAPIError("gone", code=code))
        assert spreadsheet_is_gone(LarkAPIError("gone", code=str(code))), (
            "the check must be representation-agnostic — the wire may hand back a str")

    # ...and nothing else is forgiven: a permission error is a real failure.
    assert not spreadsheet_is_gone(LarkAPIError("nope", code=1310213))
    assert not spreadsheet_is_gone(LarkAPIError("below Lark", code=None))
    assert not spreadsheet_is_gone(None)


# --------------------------------------------------------------------------- #
# AC1 — both lifecycle calls ride the shared WRITE throttle                      #
# --------------------------------------------------------------------------- #

def test_both_lifecycle_calls_route_through_the_write_transport():
    """AC1 (the amplifier: acquisitions COUNTED, not timed): create and delete each spend
    one throttle acquisition, so neither can send a request behind the limiter's back."""
    opener = StubOpener([_CREATE["response"], {"code": 0, "data": {}}])
    clock = FakeClock()
    spy = CountingTransport(WriteTransport(
        max_writes_per_sec=3, time_fn=clock.time, sleep_fn=clock.sleep))
    client = client_for(opener, transport=spy)

    client.create_spreadsheet("t", folder_token="fldrTOKEN")
    client.delete_spreadsheet(_TOK)

    assert spy.executes == 2


# --------------------------------------------------------------------------- #
# AC1 / AC6 — the docstring standard: mirror the docx twins, and state the       #
# whole-FILE blast radius (a consumer conflating it with a tab delete loses a    #
# workbook).                                                                    #
# --------------------------------------------------------------------------- #

def test_the_teardown_vocabulary_is_re_exported_by_the_sheets_facade():
    """AC1: the two codes and the predicate ride the ``larkdocio.sheets`` facade, which already
    re-exports the write client they belong to.

    The same reasoning the filter-state slugs shipped under: this is vocabulary a consumer
    **branches on** in a ``finally``, and leaving it reachable only through the deep module path
    hands them half of one module — a smaller version of the discovery defect this whole issue
    is about."""
    import larkdocio.sheets as sheets

    for name in ("SPREADSHEET_GONE_CODE", "FILE_ALREADY_DELETED_CODE",
                 "spreadsheet_is_gone"):
        assert name in sheets.__all__, sorted(sheets.__all__)
        assert getattr(sheets, name) is getattr(
            __import__("larkdocio.sheets.write_client", fromlist=["x"]), name)


def test_the_lifecycle_methods_are_docstringed_like_the_docx_twins():
    """AC1: each new method carries a docstring at least as substantial as its docx twin's
    — the standard the issue names, checked rather than asserted in a review comment."""
    from larkdocio.write.client import WriteClient

    pairs = (
        (SheetsWriteClient.create_spreadsheet, WriteClient.create_document),
        (SheetsWriteClient.delete_spreadsheet, WriteClient.delete_document),
    )
    for new, twin in pairs:
        doc = (new.__doc__ or "").strip()
        assert doc, f"{new.__name__} ships with no docstring"
        assert len(doc) >= len((twin.__doc__ or "").strip()), (
            f"{new.__name__} is documented more thinly than {twin.__name__}")


def test_delete_spreadsheet_docstring_states_the_whole_file_blast_radius():
    """AC6: the docstring says PLAINLY that it trashes the whole FILE, not a tab — and
    names the tab-delete op it must not be confused with (that op already exists, and a
    consumer conflating the two loses a workbook)."""
    doc = SheetsWriteClient.delete_spreadsheet.__doc__ or ""
    low = doc.lower()
    assert "whole" in low and "file" in low, doc
    assert "not a tab" in low, doc
    assert "DeleteTab" in doc, (
        "the docstring must name the tab-delete request the delete is NOT, so the two "
        "destructive scopes cannot be confused")


# --------------------------------------------------------------------------- #
# AC2 — THE STRUCTURAL WIN: the harness's raw create/delete HTTP is GONE, so    #
# every future live_write run exercises the SHIPPED calls. One implementation,   #
# and the shipped path is the exercised path.                                    #
# --------------------------------------------------------------------------- #

def _harness_source() -> str:
    import sheets_write_harness as H

    return Path(H.__file__).read_text(encoding="utf-8")


def test_no_raw_spreadsheet_create_or_delete_http_survives_in_the_harness():
    """AC2: the harness constructs no raw request for EITHER lifecycle operation.

    Checked as an absence, because that is the defect: two implementations of the same call
    is how the harness's long-proven behaviour and a shipped guess drift apart. The create
    collection path and the whole Drive file path are gone from the harness — including its
    prose, so a future reader cannot copy a shape from a comment either."""
    src = _harness_source()

    assert "drive/v1/files" not in src, (
        "the harness still names the Drive file path — the delete must go through "
        "SheetsWriteClient.delete_spreadsheet, which is the only implementation")
    assert 'sheets/v3/spreadsheets"' not in src, (
        "the harness still builds the v3 spreadsheet-collection path — the create must go "
        "through SheetsWriteClient.create_spreadsheet")


def test_the_harness_imports_the_shipped_write_client_for_the_lifecycle():
    """AC2 (the other direction): an absence alone could be satisfied by a harness that no
    longer creates anything. It must IMPORT the shipped client — the only implementation —
    rather than merely mention it in prose."""
    import ast

    imported = set()
    for node in ast.walk(ast.parse(_harness_source())):
        if isinstance(node, ast.ImportFrom) and node.module.startswith("larkdocio"):
            imported.update(alias.name for alias in node.names)

    assert "SheetsWriteClient" in imported, sorted(imported)
    assert "SPREADSHEET_GONE_CODE" in imported, sorted(imported)


def test_the_harness_gateway_delegates_create_and_delete_to_the_shipped_client():
    """AC2: the gateway's two lifecycle ops ARE the shipped calls — asserted at the wire,
    through the gateway, so the disposables the live ring provisions really travel the
    shipped path."""
    import sheets_write_harness as H

    opener = StubOpener([_CREATE["response"], {"code": 0, "data": {}}])
    gateway = H.SheetsLifecycleGateway(
        lambda *a, **k: (200, {"code": 0, "data": {}}),
        client=client_for(opener),
    )

    gateway.create_spreadsheet("larkdocio-harness-DISPOSABLE-x", folder_token="fldrTOKEN")
    gateway.delete_spreadsheet(_TOK)

    create, delete = opener.requests
    assert create["method"] == "POST"
    assert create["url"].endswith(_CREATE["path"])
    assert create["body"] == {"title": "larkdocio-harness-DISPOSABLE-x",
                              "folder_token": "fldrTOKEN"}
    assert delete["method"] == "DELETE"
    assert delete["url"].endswith(_DELETE_PATH.format(token=_TOK) + "?" + _DELETE_QUERY)


def test_the_harness_gateway_delete_reports_a_code_instead_of_raising():
    """AC2: the shipped delete raises on a non-zero code (loud, typed) — and the harness's
    ``finally``-delete must still be able to LEDGER an outcome rather than blow up on the
    way out of a failing test. The gateway converts the typed error into the code the ledger
    records, so a gone token reads as gone and a real failure stays flagged."""
    import sheets_write_harness as H

    gone = H.SheetsLifecycleGateway(
        lambda *a, **k: (200, {"code": 0, "data": {}}),
        client=client_for(StubOpener([_gone_payload()])),
    )
    assert gone.delete_spreadsheet(_TOK)["code"] == SPREADSHEET_GONE_CODE

    refused = H.SheetsLifecycleGateway(
        lambda *a, **k: (200, {"code": 0, "data": {}}),
        client=client_for(StubOpener([{"code": 1310213, "msg": "no permission"}])),
    )
    assert refused.delete_spreadsheet(_TOK)["code"] == 1310213


def test_the_capability_matrix_moves_the_two_rows_onto_the_shipped_client():
    """AC7: /SHEETS.md's two lifecycle rows now claim the SHIPPED client, not the harness.

    The matrix's own drift guard already forces a row to exist for every public write-client
    method; what it cannot notice is a row that still describes the operation as test
    infrastructure — which is exactly what these two rows said, and what made the capability
    look unavailable to a consumer reading the matrix."""
    text = (_ROOT / "SHEETS.md").read_text(encoding="utf-8")
    rows = {
        "create": next(ln for ln in text.splitlines()
                       if ln.startswith("| create spreadsheet ")),
        "delete": next(ln for ln in text.splitlines()
                       if ln.startswith("| delete spreadsheet ")),
    }
    assert "SheetsWriteClient.create_spreadsheet" in rows["create"], rows["create"]
    assert "SheetsWriteClient.delete_spreadsheet" in rows["delete"], rows["delete"]
    for label, row in rows.items():
        assert "shipped-harness" not in row, (
            f"the {label} row still reads as harness-only: {row}")
        assert "live_write" in row, (
            f"the {label} row must state its live gate coverage: {row}")
    # AC6 in the matrix: the FILE delete says what it destroys, beside a tab-delete row that
    # says the other thing.
    assert "whole file" in rows["delete"].lower(), rows["delete"]


def test_the_harness_ledger_reads_the_drive_already_deleted_code_as_gone():
    """AC2 + the live correction: the harness's ledger judges "gone" by the code the DELETE
    really answers.

    Its notion of gone was ``0`` or ``1310249`` — the *sheets* code — so once the harness
    delegated to the shipped delete, an idempotent double-delete (which every ``finally`` hits
    when a test fails mid-run) would have answered ``1061007`` and left the token flagged as a
    possible orphan it is not. The live arm found the real code; the ledger now spans both."""
    import sheets_write_harness as H

    ledger = H.Ledger(Path(tempfile.mkdtemp(prefix="ld176-ledger-")) / "l.json")
    ledger.record_create("TOKX", "larkdocio-harness-DISPOSABLE-x")
    ledger.record_delete("TOKX", FILE_ALREADY_DELETED_CODE)

    assert ledger.entries()[0]["deleted"] is True, (
        "an already-deleted delete must mark the token deleted, not flag a phantom orphan")

    # ...and a genuine failure still leaves it flagged.
    ledger.record_create("TOKY", "larkdocio-harness-DISPOSABLE-y")
    ledger.record_delete("TOKY", 1310213)
    assert ledger.entries()[1]["deleted"] is False


def test_the_harness_reuses_the_shipped_gone_code_rather_than_redefining_it():
    """AC2: ONE definition of the deleted-token code. The harness's ``NOT_FOUND_CODE`` — the
    value its close-out judges "gone" by — is the shipped constant itself, not a second copy
    of the number that could drift from it."""
    import sheets_write_harness as H

    import re

    assert H.NOT_FOUND_CODE == SPREADSHEET_GONE_CODE
    assignments = re.findall(r"^\s*\w+\s*=\s*(\d{6,})\s*$", _harness_source(), re.M)
    assert str(SPREADSHEET_GONE_CODE) not in assignments, (
        "the harness assigns the deleted-token number to a name of its own — bind the "
        "shipped constant instead, so there is one definition")


# --------------------------------------------------------------------------- #
# AC4 — the guide's disposables doctrine gains a RUNNABLE create → use → delete  #
# recipe. The doctrine was a whole section with nothing a consumer could run.    #
# --------------------------------------------------------------------------- #

RECIPE_SLUG = "work-against-a-disposable-spreadsheet-create-use-delete"


def test_the_disposables_doctrine_points_at_the_runnable_recipe():
    """AC4: the doctrine section names the recipe that makes it followable — for SHEETS (new)
    and, for docx, the pair that already existed and was reported nowhere."""
    import guide_recipes as gr
    from larkdocio import guide

    text = guide(full=True)
    section = text.split("### The disposables doctrine", 1)
    assert len(section) == 2, "the guide lost its disposables-doctrine section"
    body = section[1].split("\n## ", 1)[0]

    assert "Recipe: work against a disposable spreadsheet" in body, body
    for pointer in ("create_spreadsheet", "delete_spreadsheet",
                    "create_document", "delete_document"):
        assert pointer in body, f"the doctrine never names {pointer}: {body}"
    assert RECIPE_SLUG in gr.SPEC_BY_SLUG, sorted(gr.SPEC_BY_SLUG)


def test_every_lifecycle_call_the_registry_reports_is_named_in_the_guide():
    """AC3 + AC4 coupled: a lifecycle call in ``capabilities()`` that the guide never names is
    the exact defect this issue closes — the docx pair was reported by neither surface and had
    to be found with ``dir()``. So the coupling is a guard, not a habit: a third lifecycle call
    cannot ship discoverable in one place and invisible in the other."""
    from larkdocio import capabilities, guide

    text = guide(full=True)
    for sid in ("docx-write", "sheets-write"):
        for op in rows.call_sites(capabilities(full=True)["surfaces"][sid], rows.LIFECYCLE):
            assert f"`{op['name']}" in text or f"{op['name']}(" in text, (
                f"capabilities() reports {sid} lifecycle call {op['name']!r} that the guide "
                f"never names")

    # ...and the check bites: a call the guide could not possibly mention fails it.
    assert "totally_made_up_lifecycle_call" not in text


def test_the_recipe_runs_create_use_delete_offline(monkeypatch, tmp_path):
    """AC4: the recipe EXECUTES in the extract-and-run harness — the whole cycle, against the
    offline doubles, with no undefined free variables. (The parametrized whole-corpus runners
    in ``tests/test_discovery_truth.py`` re-run it too; this is the shape assertion.)"""
    import guide_recipes as gr

    st = gr.stage(monkeypatch, tmp_path)
    ns = st.run(RECIPE_SLUG)

    client = ns["write_client"]
    assert ns["spreadsheet_token"], "the recipe never captured the created token"
    assert client.created == [ns["spreadsheet_token"]], client.created
    assert client.deleted == [ns["spreadsheet_token"]], (
        "the disposable was not deleted exactly once")
    assert ns["read_back"] == [["disposable"]], ns["read_back"]
    assert ns["confirmed_gone"] is True, (
        "the recipe must CONFIRM the delete by observing the deleted-token error, not assume "
        "it from a code-0 reply")


def test_the_recipe_teardown_forgives_gone_through_the_shipped_predicate():
    """AC4 + the live correction: the recipe's ``finally`` must forgive "already gone" via
    :func:`spreadsheet_is_gone`, not by comparing one code.

    A recipe that compared ``exc.code != SPREADSHEET_GONE_CODE`` would **re-raise on a real
    double delete**, because the Drive delete answers its own ``1061007`` — the exact trap the
    live arm walked into. The teaching surface must not carry it."""
    import guide_recipes as gr

    src = gr.recipe_source(RECIPE_SLUG)
    assert "spreadsheet_is_gone" in src, src
    assert "exc.code != SPREADSHEET_GONE_CODE" not in src, (
        "the recipe forgives ONE code — a real double delete answers the other one and this "
        "teardown would re-raise")


def test_the_recipe_teardown_still_reraises_a_real_failure(monkeypatch, tmp_path):
    """AC4: forgiving must stay narrow. With the disposable's delete answering a permission
    error, the recipe fails loudly instead of pretending it cleaned up."""
    import guide_recipes as gr

    st = gr.stage(monkeypatch, tmp_path)

    def _refuse(self, spreadsheet_token):
        raise LarkAPIError("delete refused", code=1310213, msg="no permission")

    monkeypatch.setattr(
        gr.OfflineSheetsWriteClient, "delete_spreadsheet", _refuse, raising=True)
    with pytest.raises(LarkAPIError) as exc:
        st.run(RECIPE_SLUG)
    assert exc.value.code == 1310213


def test_the_recipe_has_no_undefined_free_variables():
    """AC4 verbatim ("no undefined free variables") — the check a ``compile()`` gate cannot
    make, applied to every python line a consumer could paste, commented ones included."""
    import guide_recipes as gr

    assert gr.static_problems(gr.recipe_source(RECIPE_SLUG)) == []


def test_the_recipe_deletes_the_disposable_even_when_the_body_raises(monkeypatch, tmp_path):
    """AC4 (the amplifier): the recipe FAILS LOUDLY IF THE DELETE IS SKIPPED — proved by
    injecting an exception mid-recipe and asserting the ``finally`` still trashed the
    workbook. That is the doctrine's whole point: a run that dies half way must not leave a
    live spreadsheet behind."""
    import guide_recipes as gr

    src = gr.recipe_source(RECIPE_SLUG)
    marker = "    read_back = write_client.read_values("
    assert marker in src, "the recipe's shape changed — re-anchor the injection point"
    sabotaged = src.replace(
        marker, '    raise RuntimeError("injected mid-recipe failure")\n' + marker, 1)

    st = gr.stage(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="injected mid-recipe failure"):
        st.run(RECIPE_SLUG, source=sabotaged)

    from guide_recipes import OfflineSheetsWriteClient

    assert OfflineSheetsWriteClient.last_instance is not None
    assert OfflineSheetsWriteClient.last_instance.deleted, (
        "the injected failure left the disposable alive — the recipe's finally-delete is not "
        "load-bearing, which is the defect the doctrine exists to prevent")


def test_the_lifecycle_recipe_does_not_sit_beside_the_tab_delete_recipe():
    """AC6 verbatim: the recipe must NOT sit next to a tab-delete example where the two could
    be confused. Adjacency is the risk — a reader skimming two neighbouring recipes reads
    "delete" twice and cannot see that one destroys a workbook."""
    import guide_recipes as gr

    slugs = [gr._slug(h) for h in gr.recipe_headings()]
    here = slugs.index(RECIPE_SLUG)
    tab = slugs.index("add-copy-and-delete-a-tab")
    assert abs(here - tab) > 1, (
        f"the disposable-lifecycle recipe is adjacent to the tab recipe ({slugs[here]!r} vs "
        f"{slugs[tab]!r}) — separate them so a whole-file delete cannot be read as a tab one")
