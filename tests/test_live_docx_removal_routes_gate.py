"""⛳ **THE LD-601 GATE — WHICH ROUTES STILL ANSWER FOR A DOCUMENT WE JUST DELETED.**

``@pytest.mark.live_write``, deselected by default (needs ``LARK_WRITE_APP_*``, the READ pair,
``LARKDOCIO_DISPOSABLES_FOLDER`` and network) **and refused at execution** unless the run names
the issue that authorised it::

    LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-601 pytest -m live_write \\
        tests/test_live_docx_removal_routes_gate.py

**Run the named file, and run the WHOLE file.** ``-k`` on a live gate re-runs the module's
provisioning and re-creates its disposable, which is how a budget overrun happened on
2026-08-16. There is nothing here worth selecting a subset of.

**WHY THIS EXISTS, and it is an evidence question before it is an API question.** A consumer
measured, on **their** tenant, how many routes still resolve a document after
``delete_document``. Their number is more precise than the shipped guide's. The maintainer declined the
class (LD-601, ``requirements/DECISIONS.md``): **a third-party measurement may not be the source
of a shipped claim** — it is a tenant we cannot inspect, obtained with request spellings we have
not seen, and the ``doc_type`` spelling on this endpoint family is load-bearing (LD-606: a wrong
spelling answers ``code:0`` with an empty ``metas``, which is a refusal in disguise). Declining
the class is not declining the question, so this arm **takes the measurement ourselves** and the
guide is corrected from *this* capture and from nothing else.

**What it does, once:**

1. create ONE disposable document in the caller-supplied disposables folder and seed one
   paragraph into it (so a body route has something to answer with);
2. probe **five already-shipped routes** for it — the *before* control leg;
3. delete it (``WriteClient.delete_document``, in ``docx_ledger``'s ``finally``);
4. probe the **same five routes again** — the *after* leg;
5. write every raw response body, with the request it sent **verbatim**, aimed at
   ``tests/captures/ld601-trashed-doc-routes/captures/`` — and since LD-620 **redirected out of the
   working tree** by ``capture_sink.write_capture``, loudly, so a re-run cannot overwrite the
   committed reading;
6. close out: ``docx_ledger.close_out`` re-queries the id independently, and
   ``base_write_harness.orphans()`` is read at close too, with any survivor **named**.

**The five routes, and every one is an endpoint this library already ships** — so the probe
needs no new permission row, no new scope and no new operation (LD-601 § Out of Scope):

===== ================================================================ ======== =====================================
route endpoint                                                          pair     the shipped call site that rides it
===== ================================================================ ======== =====================================
R1    ``POST /open-apis/drive/v1/metas/batch_query`` (``doc_type: docx``) READ   ``DriveClient.document_security_level``
R2    ``GET /open-apis/docx/v1/documents/{document_id}``                  WRITE  ``WriteClient.get_document``
R3    ``GET …/documents/{id}/blocks/{root}/children``                     READ   ``read.Client.get_docx_content``
R4    ``GET /open-apis/drive/v1/files`` (the folder listing)              READ   ``DriveClient.list_folder_children``
R5    ``GET /open-apis/drive/v1/files/{token}/versions``                  READ   ``DriveClient.list_versions``
===== ================================================================ ======== =====================================

**Target policy (D-12, binding).** The document is one this arm creates itself and trashes,
ledgered by :mod:`docx_ledger` and independently re-queried at close. **Never the read canary
(``LARKDOCIO_CANARY_DOC``), never ``LARKDOCIO_WRITE_SCRATCH_DOC``, never a real document** —
those two names appear in this file only as this fence.

**Permanent-media budget: ZERO BY CONSTRUCTION.** This arm uploads nothing — there is no
uploader call site in it at all, and it never sets the mint consent variable.

**Why the probe sends raw requests rather than calling the five shipped wrappers.** AC3 wants the
**raw response body** and the **exact spelling sent**; the shipped wrappers each return a typed
verdict with the envelope already digested, and a typed verdict is not a capture. So the probe
rides the same shared transport core the library's own raw clients ride
(:class:`larkdocio.common.transport.CredentialedRawHttpClient`) and sends, per route, the
identical path/params/body its shipped call site sends — named in the table above, so a reader
can check the two against each other.
"""
from __future__ import annotations

import json
import os
import pathlib
import time
import urllib.request

import pytest

import base_write_harness
import canary_support
import capture_sink
import docx_ledger
from larkdocio.common import get_read_credentials, get_write_credentials
from larkdocio.common.transport import (
    CredentialedRawHttpClient,
    api_base,
    fetch_tenant_access_token,
)
from larkdocio.write.client import WriteClient, text_block

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing the
# statement above (the ring guards read that literal line to prove ring membership).
pytestmark = [pytestmark, pytest.mark.conformance]

DOMAIN = "larksuite.com"

#: Where the evidence lands. Committed: the guide's corrected paragraph cites these files, so
#: they are the claim's provenance and not a scratch artifact.
CAPTURE_DIR = (pathlib.Path(__file__).resolve().parent.parent
               / "tests" / "captures" / "ld601-trashed-doc-routes" / "captures")

#: LD-606, restated at the one place this probe could get it wrong: on this endpoint family a
#: WRONG object-type spelling answers ``code: 0`` with an empty ``metas`` — the shape of an
#: answer with no answer in it. So every route below sends an EXPLICIT literal and the capture
#: records it; nothing here relies on a wrapper's default.
OBJECT_TYPE_SPELLING_IS_LOAD_BEARING = (
    "the doc_type / obj_type literal is recorded per route because a wrong spelling returns "
    "code:0 with metas:[] — indistinguishable from a refusal unless failed_list is read"
)

# The two standing fixtures this arm must never touch. Named, never consumed — the fence is the
# point (`tests/test_live_docx_removal_routes_gate_offline.py` greps for both).
FORBIDDEN_TARGETS = ("LARKDOCIO_CANARY_DOC", "LARKDOCIO_WRITE_SCRATCH_DOC")


class _ProbeClient(CredentialedRawHttpClient):
    """One raw JSON call per probe, on ONE named credential pair.

    Rides the shared transport core rather than a second HTTP implementation, so the request
    construction (URL, query params, JSON body, bearer) is the library's own.
    """

    def __init__(self, app_id, app_secret, domain=DOMAIN, timeout=30):
        self._app_id = app_id
        self._app_secret = app_secret
        self._domain = domain
        self._token_fetcher = fetch_tenant_access_token
        self._urlopen = urllib.request.urlopen
        self._base = api_base(domain)
        self._timeout = timeout
        self._token = None

    def probe(self, method, path, *, body=None, params=None):
        return self._send(method, path, body=body, params=params)


def _routes(document_id, folder_token):
    """The route table — ONE definition, run twice (before the delete and after it).

    Each row is ``(id, title, pair, method, path, body, params, call_site)``. The ``body`` and
    ``params`` are exactly what the named shipped call site puts on the wire.
    """
    return (
        (
            "r1", "drive metadata (metas/batch_query, doc_type=docx)", "read",
            "POST", "/open-apis/drive/v1/metas/batch_query",
            {"request_docs": [{"doc_token": document_id, "doc_type": "docx"}],
             "with_url": True},
            None,
            "DriveClient.document_security_level / DriveAccessWriteClient._read_owner",
        ),
        (
            "r2", "docx document meta", "write",
            "GET", f"/open-apis/docx/v1/documents/{document_id}",
            None, None,
            "WriteClient.get_document (also docx_ledger.close_out's re-query seam)",
        ),
        (
            "r3", "the reader's own body route (root block children)", "read",
            "GET",
            f"/open-apis/docx/v1/documents/{document_id}/blocks/{document_id}/children",
            None, {"document_revision_id": -1, "page_size": 500},
            "read.Client.get_docx_content",
        ),
        (
            "r4", "the disposables folder listing (is it still a child?)", "read",
            "GET", "/open-apis/drive/v1/files",
            None, {"folder_token": folder_token, "page_size": 200},
            "DriveClient.list_folder_children / list_folder_children_to_exhaustion",
        ),
        (
            "r5", "the file's named versions", "read",
            "GET", f"/open-apis/drive/v1/files/{document_id}/versions",
            None, {"obj_type": "docx", "page_size": 10},
            "DriveClient.list_versions",
        ),
    )


def _resolved(route_id, document_id, response):
    """Did this route RESOLVE the object? Read per route, never from the envelope ``code``.

    LD-606's lesson is the whole of this function: ``code: 0`` is an envelope verdict, and on
    ``metas/batch_query`` the per-token verdict lives in ``failed_list``. ``None`` means the
    answer does not decide it either way, which is recorded as such rather than rounded.
    """
    if not isinstance(response, dict):
        return None
    if response.get("code") != 0:
        return False
    data = response.get("data") or {}
    if route_id == "r1":
        metas = data.get("metas") or []
        return any(m.get("doc_token") == document_id for m in metas)
    if route_id == "r2":
        return bool((data.get("document") or {}).get("document_id"))
    if route_id == "r3":
        return "items" in data
    if route_id == "r4":
        return any((f.get("token") == document_id) for f in (data.get("files") or []))
    if route_id == "r5":
        return "items" in data or "has_more" in data
    return None


def _probe_all_routes(clients, document_id, folder_token, *, leg):
    """Run every route once and write one capture file per route. Returns the verdicts."""
    verdicts = {}
    for (route_id, title, pair, method, path, body, params, call_site) in _routes(
            document_id, folder_token):
        response = clients[pair].probe(method, path, body=body, params=params)
        verdicts[route_id] = _resolved(route_id, document_id, response)
        capture = {
            "issue": "LD-601",
            "leg": leg,
            "route": route_id,
            "route_title": title,
            "endpoint": path,
            "credential_pair": pair,
            "shipped_call_site": call_site,
            "subject_document_id": document_id,
            "disposables_folder_token": folder_token,
            "sent": {"method": method, "path": path, "body": body, "params": params},
            "object_type_literal_sent": (
                "docx" if route_id in ("r1", "r5") else "n/a (the path names the object)"),
            "object_type_note": OBJECT_TYPE_SPELLING_IS_LOAD_BEARING,
            "response": response,
            "failed_list": ((response.get("data") or {}).get("failed_list")
                            if isinstance(response, dict) else None),
            "resolved_the_object": verdicts[route_id],
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "tenant_note": (
                "one tenant, one document, one run — other tenants, regions and object types "
                "are unmeasured, not refuted"
            ),
        }
        capture_sink.write_capture(
            CAPTURE_DIR / f"ld601-{leg}-{route_id}.json",
            json.dumps(capture, indent=2, ensure_ascii=False) + "\n")
        time.sleep(0.4)     # be gentle: this is a purposeful probe, not a load test
    return verdicts


def test_which_routes_still_resolve_a_document_after_we_deleted_it(capsys, tmp_path):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)
    folder_token = canary_support.require_disposables_folder()
    assert folder_token, "the disposables folder token is the only destination this arm uses"
    for forbidden in FORBIDDEN_TARGETS:
        assert folder_token != os.environ.get(forbidden), (
            f"{forbidden} is a FORBIDDEN target for this arm — it writes only to a disposable "
            f"it created itself, inside the human-visible disposables folder"
        )

    write_client = WriteClient(*get_write_credentials(), DOMAIN)
    clients = {
        "read": _ProbeClient(*get_read_credentials()),
        "write": _ProbeClient(*get_write_credentials()),
    }
    ledger = docx_ledger.Ledger(tmp_path / "ledger.json")
    before = after = None
    document_id = None

    try:
        with docx_ledger.disposable(
            write_client, ledger,
            title=f"larkdocio-LD-601-removal-routes {int(time.time())}",
            folder_token=folder_token,
        ) as doc:
            document_id = doc.document_id
            # Seed one paragraph through the shipped raw create leg — the same call
            # `roundtrip_gate.seed_paragraphs` makes; a body route needs a body to answer with.
            write_client.create_children(
                document_id, document_id,
                [text_block("LD-601 removal-route probe subject")], index=0)
            before = _probe_all_routes(clients, document_id, folder_token, leg="before")
            # The BEFORE leg is the control: without it an "after" answer proves nothing about
            # the delete, only about the route.
            assert before["r2"] is True, (
                f"the docx meta route did not resolve a document we had just created "
                f"({document_id}) — the control failed, so nothing after this means anything"
            )
            assert before["r4"] is True, (
                f"the freshly created document {document_id} was not listed as a child of the "
                f"disposables folder — the control failed"
            )
        # ── the `with` has exited: docx_ledger deleted the document in its `finally`.
        after = _probe_all_routes(clients, document_id, folder_token, leg="after")
    finally:
        report = docx_ledger.close_out(write_client, ledger)
        base_orphans = base_write_harness.orphans()
        summary = {
            "issue": "LD-601",
            "subject_document_id": document_id,
            "before": before,
            "after": after,
            "still_resolving_after_the_delete": sorted(
                k for k, v in (after or {}).items() if v is True),
            "docx_close_out": report.to_dict(),
            "base_orphans_named": [
                {"token": o.get("app_token"), "kind": "bitable app", "row": o}
                for o in base_orphans
            ],
            "ledger": ledger.entries(),
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        capture_sink.write_capture(
            CAPTURE_DIR / "ld601-summary.json",
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
        print("LD-601 SUMMARY:", json.dumps(summary, ensure_ascii=False))

    # The finding itself is the capture; what is ASSERTED here is the discipline.
    assert after is not None, "the after leg must have run"
    assert report.ledger_count == 1, (
        f"this arm's budget is ONE reclaimable object; the ledger holds {report.ledger_count}"
    )
    # An orphan is NAMED, never counted — `raise_if_orphans` names the document_id.
    if report.orphans or report.indeterminate:
        print("LD-601 SURVIVOR(S) NAMED:", json.dumps(report.to_dict(), ensure_ascii=False))
    report.raise_if_orphans()
    assert not base_orphans, (
        "the Base orphan oracle named a survivor: "
        + json.dumps([o.get("app_token") for o in base_orphans])
    )
