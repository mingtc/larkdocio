"""Offline unit tests for the **docx** disposables ledger (LD-236).

The zero-orphan discipline had exactly one implementation — ``tests/sheets_write_harness.py``
— and it re-queries through ``gateway.query_spreadsheet``, a **Sheets** call. The docx ring
proved gone-ness ad hoc, inline, once (``test_live_write_comment_op_gate.py`` § close-out).
``tests/docx_ledger.py`` is that discipline ported to the docx re-query seam
(``WriteClient.get_document``) and made reusable; these tests are its always-on half, so the
four the round-trip-editing spec arms inherit a ledger whose behaviour is pinned without credentials.

What is deliberately pinned here is the part a live run cannot show on a green day: a delete
that FAILED still leaves its token flagged, a re-query that could not be classified is loud
rather than clean, and a create that returned no id ledgers nothing.
"""
import json

import pytest

import docx_ledger as dl
from larkdocio.errors import LarkAPIError


#: The destination these offline cases hand the harness. An explicit token rather than the
#: environment's: nothing here creates anything on any tenant, so the disposables folder is
#: neither needed nor consulted, and a skip would be noise rather than protection. The key
#: still travels, so what these cases exercise is the shape a live run sends.
DEST = "fldrOFFLINEDOUBLEDESTINATION"


class FakeWriteClient:
    """The two calls the ledger needs, and nothing else.

    ``resolves`` is the set of document ids ``get_document`` still answers for; anything
    else raises the ``LarkAPIError`` a trashed docx really answers with.
    """

    def __init__(self, *, created="doc-1", delete_code=0, resolves=(), get_error=None):
        self._created = created
        self._delete_code = delete_code
        self.resolves = set(resolves)
        self.get_error = get_error
        self.calls = []

    def create_document(self, title="", *, folder_token):
        self.calls.append(("create", title))
        return {"document_id": self._created, "title": title} if self._created else {}

    def delete_document(self, document_id):
        self.calls.append(("delete", document_id))
        if isinstance(self._delete_code, Exception):
            raise self._delete_code
        return {"code": self._delete_code}

    def get_document(self, document_id):
        self.calls.append(("get", document_id))
        if document_id in self.resolves:
            return {"document_id": document_id, "revision_id": 1}
        if self.get_error is not None:
            raise self.get_error
        raise LarkAPIError("not found", code=1248007)


# --------------------------------------------------------------------------- #
# The ledger itself — a create-side record that never drops a token             #
# --------------------------------------------------------------------------- #

def test_a_created_document_is_recorded_undeleted(tmp_path):
    ledger = dl.Ledger(tmp_path / "l.json")
    ledger.record_create("doc-1", "t")
    (entry,) = ledger.entries()
    assert entry["document_id"] == "doc-1" and entry["title"] == "t"
    assert entry["deleted"] is False and entry["delete_code"] is None
    assert ledger.document_ids() == ["doc-1"]


def test_the_ledger_persists_so_a_later_process_can_still_close_it_out(tmp_path):
    path = tmp_path / "l.json"
    dl.Ledger(path).record_create("doc-1", "t")
    assert json.loads(path.read_text(encoding="utf-8"))[0]["document_id"] == "doc-1"
    assert dl.Ledger(path).document_ids() == ["doc-1"]


def test_a_failed_delete_leaves_the_token_flagged_never_dropped(tmp_path):
    ledger = dl.Ledger(tmp_path / "l.json")
    ledger.record_create("doc-1", "t")
    ledger.record_delete("doc-1", 1061004)
    (entry,) = ledger.entries()
    assert entry["deleted"] is False, "a non-zero delete code must NOT read as deleted"
    assert entry["delete_code"] == 1061004 and entry["deleted_at"]
    assert ledger.document_ids() == ["doc-1"], "the token must stay on the sweep list"


def test_a_successful_delete_is_recorded_and_is_idempotent(tmp_path):
    ledger = dl.Ledger(tmp_path / "l.json")
    ledger.record_create("doc-1", "t")
    ledger.record_delete("doc-1", 0)
    ledger.record_delete("doc-1", "error: already gone")
    (entry,) = ledger.entries()
    assert entry["deleted"] is True, "a second (failing) delete must not un-delete the row"


# --------------------------------------------------------------------------- #
# disposable() — create, yield, ALWAYS delete                                   #
# --------------------------------------------------------------------------- #

def test_disposable_records_create_yields_the_id_and_deletes_in_finally(tmp_path):
    client, ledger = FakeWriteClient(), dl.Ledger(tmp_path / "l.json")
    with dl.disposable(client, ledger, title="x", folder_token=DEST) as doc:
        assert doc.document_id == "doc-1" and doc.title == "x"
        assert ledger.entries()[0]["deleted"] is False
    assert ("delete", "doc-1") in client.calls
    assert ledger.entries()[0]["deleted"] is True


def test_disposable_deletes_even_when_the_body_raises(tmp_path):
    client, ledger = FakeWriteClient(), dl.Ledger(tmp_path / "l.json")
    with pytest.raises(RuntimeError, match="mid-round-trip"):
        with dl.disposable(client, ledger, folder_token=DEST):
            raise RuntimeError("mid-round-trip failure")
    assert ("delete", "doc-1") in client.calls, "teardown must run on the failure path too"
    assert ledger.entries()[0]["deleted"] is True


def test_a_delete_that_raises_is_recorded_rather_than_masking_the_body(tmp_path):
    client = FakeWriteClient(delete_code=LarkAPIError("no drive scope", code=99991672))
    ledger = dl.Ledger(tmp_path / "l.json")
    with dl.disposable(client, ledger, folder_token=DEST):
        pass
    entry = ledger.entries()[0]
    assert entry["deleted"] is False and "99991672" in str(entry["delete_code"])


def test_a_create_that_returned_no_id_ledgers_nothing_and_is_loud(tmp_path):
    client, ledger = FakeWriteClient(created=None), dl.Ledger(tmp_path / "l.json")
    with pytest.raises(dl.HarnessError, match="nothing ledgered"):
        with dl.disposable(client, ledger, folder_token=DEST):
            pass
    assert ledger.entries() == []


# --------------------------------------------------------------------------- #
# close_out() — the INDEPENDENT re-query, which is what "zero orphans" means     #
# --------------------------------------------------------------------------- #

def test_close_out_reports_a_still_resolving_document_as_an_orphan(tmp_path):
    ledger = dl.Ledger(tmp_path / "l.json")
    ledger.record_create("doc-1", "t")
    ledger.record_delete("doc-1", 0)
    report = dl.close_out(FakeWriteClient(resolves=["doc-1"]), ledger)
    assert report.ledger_count == 1 and not report.all_clean
    assert [o["document_id"] for o in report.orphans] == ["doc-1"]
    with pytest.raises(dl.OrphanLeakError, match="doc-1"):
        report.raise_if_orphans()


def test_close_out_reports_a_trashed_document_as_clean_and_records_larks_code(tmp_path):
    ledger = dl.Ledger(tmp_path / "l.json")
    ledger.record_create("doc-1", "t")
    ledger.record_delete("doc-1", 0)
    report = dl.close_out(FakeWriteClient(), ledger)
    assert report.all_clean and report.orphans == []
    assert report.clean[0]["recheck_code"] == 1248007, (
        "the code Lark answered the re-query with is EVIDENCE — record it, do not discard it")
    report.raise_if_orphans()


def test_a_re_query_that_could_not_be_classified_is_loud_not_clean(tmp_path):
    """A transport failure is not a deletion. Calling it clean is how a sweep goes quiet on
    exactly the run where the network was the problem."""
    ledger = dl.Ledger(tmp_path / "l.json")
    ledger.record_create("doc-1", "t")
    client = FakeWriteClient(get_error=OSError("connection reset"))
    report = dl.close_out(client, ledger)
    assert report.orphans == [] and report.clean == []
    assert [i["document_id"] for i in report.indeterminate] == ["doc-1"]
    assert not report.all_clean
    with pytest.raises(dl.OrphanLeakError, match="could not be confirmed"):
        report.raise_if_orphans()


def test_close_out_re_queries_every_ledgered_token_not_just_the_undeleted_ones(tmp_path):
    """The ledger is the create-side record; the close-out is the delete-side confirmation.
    Trusting the ledger's own ``deleted`` flag would make the audit circular."""
    ledger = dl.Ledger(tmp_path / "l.json")
    for i in (1, 2, 3):
        ledger.record_create(f"doc-{i}", "t")
        ledger.record_delete(f"doc-{i}", 0)
    client = FakeWriteClient(resolves=["doc-2"])
    report = dl.close_out(client, ledger)
    assert [c for c in client.calls if c[0] == "get"] == [
        ("get", "doc-1"), ("get", "doc-2"), ("get", "doc-3")]
    assert [o["document_id"] for o in report.orphans] == ["doc-2"]
    assert len(report.clean) == 2
