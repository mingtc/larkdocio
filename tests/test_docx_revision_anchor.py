"""LD-382 — the CHEAP docx revision anchor: metadata-only, single, and NOT bulk.

Base and Sheets expose a revision anchor without reading values; docx paid a full
``get_docx_content`` to learn its ``revision_id``. The probe that settled what is actually
available is committed at ``tests/captures/docx-revision-probe/captures/01-metadata-route.json`` (two
harness-created disposable docs, both trashed and independently re-queried; never the canary,
never a real document), and it answered AC1's four questions:

* **(i)** a metadata-only route exists — ``GET …/docx/v1/documents/{document_id}`` returns
  ``revision_id`` beside ``title`` / ``document_id`` / ``display_setting`` and **no blocks**;
* **(ii)** it **agrees** with what the full content read reports at the same moment (``2 == 2``
  before an edit, ``3 == 3`` after one), and it is stable across back-to-back reads;
* **(iii)** **no BULK revision route was found.** The one batch form that answers — the Drive
  metas batch query — returns ten keys per document and **not one of them is a revision**; the
  three docx-native batch spellings tried came back ``HTTP 404`` / ``99992402``;
* **(iv)** it costs **one** call (``0.119 s`` measured) against the **READ** pair on the scope
  the content read already needs — no new endpoint family, no scope moved.

So the AC2 fork lands **both ways**: the single cheap route ships, and the bulk half is a
**measured refusal** recorded in the library's own voice.

Every arm here is offline against a stubbed SDK, except the capture-truth arm, which reads the
committed probe so the shipped claims cannot drift away from what was measured.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from larkdocio.errors import LarkAPIError
from larkdocio.read.client import (
    BULK_DOCUMENT_REVISION_UNAVAILABLE,
    DOCUMENT_REVISION_SEMANTICS,
    Client,
)

_CAPTURE = (Path(__file__).resolve().parent.parent / "tests" / "captures" / "docx-revision-probe"
            / "captures" / "01-metadata-route.json")

TOKEN = "docxLD382TOKEN"


class _Calls:
    """Counts what the client actually reached for — the cheapness claim is a call count."""

    def __init__(self):
        self.meta = 0
        self.children = 0


def _resp(success=True, code=0, msg="ok", **data):
    return SimpleNamespace(success=lambda: success, code=code, msg=msg,
                           data=SimpleNamespace(**data))


def _stub_client(meta_resp, calls=None):
    calls = calls or _Calls()

    def meta_get(req):
        calls.meta += 1
        return meta_resp

    def children_get(req):                       # pragma: no cover - must never be called
        calls.children += 1
        return _resp(items=[], page_token="", has_more=False)

    client = Client.__new__(Client)
    client.lark_client = SimpleNamespace(
        docx=SimpleNamespace(v1=SimpleNamespace(
            document=SimpleNamespace(get=meta_get),
            document_block_children=SimpleNamespace(get=children_get),
        )),
    )
    return client, calls


# --------------------------------------------------------------------------- #
# AC2(a) — the cheap route ships, and it is CHEAP: one call, no block read.     #
# --------------------------------------------------------------------------- #

def test_the_metadata_route_returns_the_revision_in_one_call_and_reads_no_blocks():
    client, calls = _stub_client(_resp(document=SimpleNamespace(revision_id=7, title="t")))
    assert client.read_document_revision(TOKEN) == 7
    assert calls.meta == 1, "the anchor must cost exactly one call"
    assert calls.children == 0, (
        "asking 'did it change?' must not read the block tree — that is the whole point")


def test_zero_is_knowledge_and_is_reported_as_zero():
    client, _ = _stub_client(_resp(document=SimpleNamespace(revision_id=0)))
    assert client.read_document_revision(TOKEN) == 0


@pytest.mark.parametrize("raw", [None, "3", 3.0, True, False])
def test_a_non_integer_revision_is_not_known_and_is_never_rounded_to_zero(raw):
    client, _ = _stub_client(_resp(document=SimpleNamespace(revision_id=raw)))
    assert client.read_document_revision(TOKEN) is None


def test_a_document_object_that_is_absent_entirely_is_not_known():
    client, _ = _stub_client(_resp())
    assert client.read_document_revision(TOKEN) is None


def test_a_refused_read_raises_the_same_taxonomy_the_content_read_does():
    client, _ = _stub_client(_resp(success=False, code=99991672, msg="no permission"))
    with pytest.raises(LarkAPIError) as excinfo:
        client.read_document_revision(TOKEN)
    assert "99991672" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# AC3 — the anchor's MEANING is stated, and AC2(b) — the bulk refusal is        #
# ENUMERATED (the LD-380 negative-claim doctrine).                             #
# --------------------------------------------------------------------------- #

def test_the_semantics_state_what_the_value_is_comparable_to():
    text = DOCUMENT_REVISION_SEMANTICS.lower()
    for phrase in ("itself", "monotonic", "read", "not known"):
        assert phrase in text, f"the documented semantics never say {phrase!r}: {text}"


def test_the_bulk_refusal_enumerates_the_forms_ACTUALLY_TRIED():
    text = BULK_DOCUMENT_REVISION_UNAVAILABLE
    for form in ("drive/v1/metas", "batch_get", "document_ids", "batch-query"):
        assert form in text, f"the bulk refusal does not name the tried form {form!r}"
    assert "unmeasured" in text.lower(), (
        "a negative claim must say the untried forms are unmeasured, not refuted")


def test_the_shipped_guide_carries_the_docx_anchor_and_its_bulk_refusal():
    guide = (Path(__file__).resolve().parent.parent / "src" / "larkdocio"
             / "GUIDE.md").read_text(encoding="utf-8")
    assert "read_document_revision" in guide, (
        "the consumer guide never names the cheap route it ships")
    for form in ("metas/batch_query", "batch_get", "document_ids", "unmeasured"):
        assert form in guide, (
            f"the guide states no bulk route without naming the tried form {form!r} — a "
            f"negative claim ships with its enumeration")


# --------------------------------------------------------------------------- #
# The capture-truth arm — the shipped claims vs what the probe measured.        #
# --------------------------------------------------------------------------- #

def _answers():
    return json.loads(_CAPTURE.read_text(encoding="utf-8"))["observed"]["answers"]


def test_the_capture_shows_a_metadata_only_route_that_agrees_with_the_content_read():
    a = _answers()
    assert a["i_metadata_only_revision"] is not None
    assert a["i_meta_keys"] == ["display_setting", "document_id", "revision_id", "title"], (
        "the meta payload carried something other than the four keys the claim rests on")
    assert a["ii_agreement"] is True and a["ii_agreement_after_edit"] is True
    assert a["movement_meta_after"] == a["movement_meta_before"] + 1, (
        "one edit must move the anchor by one — the monotonic claim")
    assert a["movement_meta_stable_across_reads"] is True


def test_the_capture_shows_NO_bulk_revision_route():
    a = _answers()
    assert a["iii_batch_code"] == 0, "the batch form itself must have answered"
    assert a["iii_batch_carries_revision"] is False, (
        "the capture would contradict the shipped refusal")
    assert not any(k for k in a["iii_batch_row_keys"] if "revision" in k)
    for label, outcome in a["iii_speculative"].items():
        assert outcome["http"] != 200, f"{label} succeeded — the refusal must be re-examined"


def test_the_probe_tore_ITS_OWN_disposables_down():
    capture = json.loads(_CAPTURE.read_text(encoding="utf-8"))
    teardown = capture["teardown"]
    assert teardown, "a probe that created documents must record their teardown"
    for entry in teardown:
        assert entry["gone"] is True, f"a disposable leaked: {entry}"


# --------------------------------------------------------------------------- #
# AC7 — the binding live round-trip THROUGH THE SHIPPED ROUTE (capture 02).     #
# --------------------------------------------------------------------------- #

_AC7 = _CAPTURE.parent / "02-shipped-route-round-trip.json"


def test_the_live_round_trip_through_the_shipped_route_moved_the_anchor_by_one():
    capture = json.loads(_AC7.read_text(encoding="utf-8"))
    rt = capture["observed"]["round_trip"]
    assert rt["agreement_before"] is True and rt["agreement_after"] is True, (
        "the shipped cheap route disagreed with the content read — AC1(ii) makes that a "
        "refusal, not a feature")
    assert rt["stable_across_reads"] is True, "a read moved the anchor"
    assert rt["moved"] is True and rt["moved_by"] == 1, (
        "one edit must move the anchor by exactly one")
    assert capture["teardown"]["gone"] is True, (
        f"the AC7 disposable leaked: {capture['teardown']}")
