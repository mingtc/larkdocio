"""LD-139 (D9) — ``STALE_DOCUMENT``: the whole-document revision CAS.

⚠ **CRITICAL-CLASS SAFETY.** Per-anchor ``STALE_ANCHOR`` (the narrative-apply spec) validates *the anchor*
and is **blind to drift AROUND it**: a human inserting paragraphs above a still-matching
anchor leaves the quote (or the by-id precondition) intact while the intended **position**
has moved, so an authoring batch lands **mispositioned** content. D9 (maintainer-settled, *"warn
then fail instead of trying to accommodate disastrous results"*) closes that with a
**whole-document compare-and-swap**: the plan caches the document ``revision_id`` at plan
time, the engine **re-reads it immediately before apply**, and **any advance refuses the
ENTIRE batch with ZERO writes** and an actionable ``detail`` (re-download + re-plan). No
partial application, and **no auto-mapping of drift** — maintainer-rejected as "messy".

The AC sections below are the contract:

* **AC1** — the ``revision_id`` availability finding, pinned as executable characterization:
  the docx meta ``GET /open-apis/docx/v1/documents/{id}`` → ``data.document.revision_id``,
  which the reader's own ``GetDocumentRequest`` leg already returns, and which advances one
  per write while staying stable across reads.
* **AC2** — plan-time capture + apply-time re-read → a typed ``STALE_DOCUMENT`` refusal for
  the whole batch, with a ``detail`` naming the drift and the re-plan guidance.
* **AC3** — **the centerpiece: ZERO writes issued on refusal**, proved by a *transport spy*
  that records every HTTP call — not by "no changes observed".
* **AC4** — the never-silent marker (the LD-132 pattern): ``revision_guard`` +
  ``revision_guard_detail`` on the plan and its JSON, unavailable-with-WHY when no revision
  is obtainable, absent-of-doubt ``active`` when it is, and self-activation.
* **AC5** — **no auto-mapping**: the only drift outcome is a refusal; no accommodation path
  exists (behavioural + an identifier-level AST guard).
* **AC6** — the injected-transport matrix both ways (unchanged / +1 / +many / unavailable at
  plan / unavailable at apply / a 10-request batch refusing all 10).
* **AC7** — findings-agnostic; the AST findings-vocabulary guard extends to the new symbols.
* **AC8** — truth rows: ``capabilities()`` safety contracts, the guide, BLOCKS.md.

Plus the maintainer's rigor amplifier: drift **between the dry-run and the apply** of a multi-request
batch, an unavailable→available transition, the refusal ``detail`` asserted to carry the
re-plan guidance **verbatim**, and the ``STALE_ANCHOR`` coexistence case that motivated D9 —
the document guard fires **even when every anchor still matches perfectly**.
"""
import ast
import json
import re
from pathlib import Path

import pytest

from log_reading_apply import reading_the_log
from larkdocio import capabilities
from larkdocio.errors import LarkRateLimitError
from larkdocio.write.apply import apply
apply = reading_the_log(apply)
from larkdocio.write.client import WriteClient
from larkdocio.write.model import (
    AnchorById,
    ApplyLog,
    InsertPosition,
    Refusal,
    RefusalReason,
)
from larkdocio.write.preview import Plan, dry_run
from larkdocio.write.revision import (
    CONCURRENCY_WARNING,
    REPLAN_GUIDANCE,
    REVISION_GUARD_ACTIVE,
    REVISION_GUARD_UNAVAILABLE,
    revision_guard_semantics,
    revision_guard_status,
)

from write_harness import (
    FakeClock,
    _block_payload,
    _insert,
    _page,
    _para,
    _patch_ok,
    _req,
    _run,
)
from larkdocio.common.transport import WriteTransport

_SRC = Path(__file__).resolve().parents[1] / "src" / "larkdocio"
_WRITE_DIR = _SRC / "write"
_DOC_META_RE = re.compile(r"/open-apis/docx/v1/documents/([^/?]+)(?:\?|$)")


# --------------------------------------------------------------------------- #
# The TRANSPORT SPY (AC3's centerpiece) — a urllib double that ROUTES by       #
# method+path (so a refusal that makes fewer calls does not desync a queue)     #
# and records EVERY call, so "zero writes" is a measurement, not a hope.        #
# --------------------------------------------------------------------------- #

class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b


class TransportSpy:
    """Records every HTTP call the client makes and answers it from a routing table.

    ``document_revisions`` is the sequence of ``revision_id`` values the document meta
    hands back, one per meta read (the last value repeats) — that is how "the revision
    advanced between plan and apply" is injected. ``blocks`` maps ``block_id`` → the
    ``get_block`` payload. Any write (POST / PATCH / DELETE) is recorded and answered
    generically.

    :attr:`writes` is the spy's whole point: a ``STALE_DOCUMENT`` refusal must leave it
    **empty**. Reads are recorded separately so the assertion can be exact rather than
    "nothing happened".
    """

    WRITE_METHODS = ("POST", "PATCH", "DELETE", "PUT")

    def __init__(self, *, document_revisions=(), blocks=None, meta_error=None,
                 meta_payload=None):
        self._revisions = list(document_revisions)
        self._blocks = dict(blocks or {})
        self._meta_error = meta_error
        self._meta_payload = meta_payload
        self.calls = []          # every call: (method, path)
        self.meta_reads = 0

    # -- introspection ------------------------------------------------------ #

    @property
    def writes(self):
        """Every WRITE call that reached the transport. **Must be empty on a refusal.**"""
        return [c for c in self.calls if c[0] in self.WRITE_METHODS]

    @property
    def reads(self):
        return [c for c in self.calls if c[0] == "GET"]

    def _next_revision(self):
        self.meta_reads += 1
        if not self._revisions:
            return None
        i = min(self.meta_reads - 1, len(self._revisions) - 1)
        return self._revisions[i]

    # -- the urlopen double -------------------------------------------------- #

    def __call__(self, req, timeout=30):
        method, url = req.get_method(), req.full_url
        path = url.split("larksuite.com", 1)[-1]
        self.calls.append((method, path))
        if method == "GET":
            meta = _DOC_META_RE.search(path)
            if meta is not None:                        # the document meta read
                if self._meta_error is not None:
                    return _Resp(self._meta_error)
                if self._meta_payload is not None:
                    return _Resp(self._meta_payload)
                return _Resp({"code": 0, "data": {"document": {
                    "document_id": meta.group(1),
                    "revision_id": self._next_revision(),
                    "title": "spy doc",
                }}})
            block_id = path.rsplit("/blocks/", 1)[-1].split("?")[0]
            payload = self._blocks.get(block_id)
            if payload is None:
                return _Resp({"code": 1770002, "msg": f"block {block_id} not found"})
            return _Resp(payload)
        if method == "POST":
            return _Resp({"code": 0, "data": {
                "children": [{"block_id": "new1"}], "document_revision_id": 99}})
        return _Resp(_patch_ok())


def _spy_client(spy):
    clock = FakeClock()
    transport = WriteTransport(max_writes_per_sec=3, time_fn=clock.time,
                               sleep_fn=clock.sleep)
    return WriteClient("app", "secret", "larksuite.com", transport=transport,
                       urlopen=spy, token_fetcher=lambda *a, **k: "t-test")


def _tree():
    return _page(_para("p1", "first line"), _para("p2", "second line"))


def _live_blocks(**texts):
    """``block_id -> get_block payload`` for the given live texts (all fresh / matching)."""
    return {bid: _block_payload(bid, [_run(text)], parent_id="root")
            for bid, text in texts.items()}


def _fresh_blocks():
    return _live_blocks(p1="first line", p2="second line")


# =========================================================================== #
# AC1 — the revision_id availability finding, pinned as characterization.      #
#                                                                              #
# LIVE FINDING (2026-07-28, harness-self-provisioned disposable doc, torn down): #
#   GET /open-apis/docx/v1/documents/{id} -> data.document keys                 #
#     ['display_setting', 'document_id', 'revision_id', 'title']                #
#   revision_id after create_document ............ 1   (int; create's own reply  #
#                                                       already carries it)      #
#   after one create_children ..................... 2   (advanced)               #
#   after one patch_block ......................... 3   (advanced)               #
#   two consecutive META READS .................... 3, 3 (stable — a read never  #
#                                                       bumps it)               #
#   the READER's own GetDocumentRequest leg                                     #
#     (Client.get_docx_content -> document.revision_id) 3 == the raw meta value  #
# So a whole-document CAS anchor IS available, and available for FREE on the      #
# read that builds the tree. The tests below pin that contract offline.          #
# =========================================================================== #

def test_ac1_the_write_client_exposes_the_document_meta_and_its_revision():
    spy = TransportSpy(document_revisions=[7])
    client = _spy_client(spy)
    doc = client.get_document("docABC")
    assert doc["document_id"] == "docABC"
    assert doc["revision_id"] == 7
    # ONE call, and it is a READ — reading the CAS anchor never writes.
    assert spy.writes == []
    assert spy.reads == [("GET", "/open-apis/docx/v1/documents/docABC")]


def test_ac1_read_document_revision_returns_the_scalar_anchor():
    spy = TransportSpy(document_revisions=[12])
    assert _spy_client(spy).read_document_revision("docABC") == 12


def test_ac1_read_document_revision_is_none_when_the_meta_omits_it():
    """The never-silent design covers the *other* finding: a meta with no ``revision_id``
    yields ``None``, which the marker reports as unavailable rather than guessing."""
    spy = TransportSpy(meta_payload={"code": 0, "data": {"document": {
        "document_id": "docABC", "title": "no revision here"}}})
    assert _spy_client(spy).read_document_revision("docABC") is None


def test_ac1_the_reader_document_object_carries_revision_id_by_sdk_shape():
    """The plan-time anchor costs ZERO extra calls: the SDK ``Document`` the reader's
    ``get_docx_content`` already returns has a ``revision_id`` field (pinned against the
    SDK model, so an SDK drift reddens here rather than silently disabling the guard)."""
    from lark_oapi.api.docx.v1.model.document import Document

    doc = Document({"document_id": "d1", "revision_id": 42, "title": "t"})
    assert doc.revision_id == 42


# =========================================================================== #
# AC4 — the never-silent marker (the LD-132 pattern).                          #
# =========================================================================== #

def test_ac4_status_classifies_a_usable_anchor_active():
    assert revision_guard_status(1) == REVISION_GUARD_ACTIVE
    assert revision_guard_status(155) == REVISION_GUARD_ACTIVE
    assert revision_guard_status("155") == REVISION_GUARD_ACTIVE


@pytest.mark.parametrize("revision", [None, 0, "0", "", "   ", -1, -155])
def test_ac4_status_classifies_an_unusable_anchor_unavailable(revision):
    """``None`` / absent, the ``0`` sentinel, and — the docx-specific trap — the **-1
    "latest" sentinel** a consumer might copy from the ``document_revision_id=-1`` query
    are all unusable anchors, so the guard says so instead of comparing them."""
    assert revision_guard_status(revision) == REVISION_GUARD_UNAVAILABLE


def test_ac4_semantics_always_carry_a_non_empty_why():
    for revision in (None, 0, -1, 7):
        s = revision_guard_semantics(revision)
        assert s["status"] in (REVISION_GUARD_ACTIVE, REVISION_GUARD_UNAVAILABLE)
        assert s["detail"].strip(), f"a marker with no WHY is a riddle: {revision!r}"
        assert json.loads(json.dumps(s)) == s      # JSON-serializable, losslessly


def test_ac4_the_unavailable_detail_names_the_value_and_how_to_activate():
    detail = revision_guard_semantics(None)["detail"]
    assert "UNAVAILABLE" in detail
    assert "document_revision_id" in detail          # the knob that activates it
    assert "revision_id" in detail                   # where to get the value
    assert "stale-anchor" in detail or "STALE_ANCHOR" in detail   # what still guards


def test_ac4_a_plan_without_a_revision_is_marked_unavailable():
    plan = dry_run([_req("first line")], _tree())
    assert plan.document_revision_id is None
    assert plan.revision_guard == REVISION_GUARD_UNAVAILABLE
    assert plan.revision_guard_detail.strip()


def test_ac4_a_plan_with_a_revision_is_marked_active_and_the_marker_is_not_a_riddle():
    plan = dry_run([_req("first line")], _tree(), document_revision_id=7)
    assert plan.document_revision_id == 7
    assert plan.revision_guard == REVISION_GUARD_ACTIVE
    assert "7" in plan.revision_guard_detail


def test_ac4_the_marker_is_visible_in_the_plan_json_both_ways():
    """AC4: consumer-visible + JSON-serializable — the plan's own wire form carries the
    guard state, so an approval UX shows it without reaching into python attributes."""
    off = dry_run([_req("first line")], _tree()).to_dict()
    on = dry_run([_req("first line")], _tree(), document_revision_id=7).to_dict()
    assert off["revision_guard"] == REVISION_GUARD_UNAVAILABLE
    assert off["document_revision_id"] is None
    assert off["revision_guard_detail"].strip()
    assert on["revision_guard"] == REVISION_GUARD_ACTIVE
    assert on["document_revision_id"] == 7
    for d in (off, on):
        assert json.loads(json.dumps(d)) == d


def test_ac4_the_marker_is_derived_not_stored_so_no_plan_can_lack_it():
    """The LD-132 structural point: the status is a **property of the revision**, computed
    in the constructor's own accessor — there is no writable slot a future op family's
    preview leg could forget to fill (and no way to stamp a lying 'active')."""
    plan = dry_run([_req("first line")], _tree())
    with pytest.raises(AttributeError):
        plan.revision_guard = REVISION_GUARD_ACTIVE
    assert "revision_guard" not in getattr(Plan, "__slots__", ())


def test_ac4_the_guard_self_activates_once_a_revision_is_obtainable():
    """Unavailable → available with no code change: the same requests, planned once
    without an anchor and once with, flip the marker (and the CAS with it)."""
    requests, tree = [_req("first line")], _tree()
    assert dry_run(requests, tree).revision_guard == REVISION_GUARD_UNAVAILABLE
    assert dry_run(requests, tree, document_revision_id=9).revision_guard == (
        REVISION_GUARD_ACTIVE)


def test_ac4_the_apply_log_discloses_the_guard_status_too():
    """Never-silent on the *apply* side: a consumer holding only the apply-log can tell
    whether the whole-document CAS was in force for that batch."""
    spy = TransportSpy(document_revisions=[5, 5], blocks=_fresh_blocks())
    log = apply(dry_run([_req("first line")], _tree(), document_revision_id=5),
                _spy_client(spy), "docABC")
    assert log.revision_guard == REVISION_GUARD_ACTIVE
    assert log.to_dict()["revision_guard"] == REVISION_GUARD_ACTIVE

    spy2 = TransportSpy(blocks=_fresh_blocks())
    log2 = apply(dry_run([_req("first line")], _tree()), _spy_client(spy2), "docABC")
    assert log2.revision_guard == REVISION_GUARD_UNAVAILABLE
    assert log2.to_dict()["revision_guard"] == REVISION_GUARD_UNAVAILABLE
    assert ApplyLog.from_dict(log2.to_dict()).revision_guard == REVISION_GUARD_UNAVAILABLE


# =========================================================================== #
# AC2 — plan-time capture + apply-time re-read → WHOLE-BATCH refusal.          #
# =========================================================================== #

def test_ac2_an_unchanged_revision_applies_normally():
    spy = TransportSpy(document_revisions=[5, 5], blocks=_fresh_blocks())
    log = apply(dry_run([_req("first line")], _tree(), document_revision_id=5),
                _spy_client(spy), "docABC")
    assert [e.outcome for e in log.entries] == ["applied"]
    assert spy.writes, "an unchanged document must actually write"


def test_ac2_an_advanced_revision_refuses_the_whole_batch_with_a_typed_reason():
    spy = TransportSpy(document_revisions=[6], blocks=_fresh_blocks())
    log = apply(dry_run([_req("first line"), _req("second line")], _tree(),
                        document_revision_id=5), _spy_client(spy), "docABC")
    assert [e.outcome for e in log.entries] == ["refused", "refused"]
    for entry in log.entries:
        assert entry.refusal.reason is RefusalReason.STALE_DOCUMENT
    # 1:1 with the plan, in order, anchors preserved so a consumer can correlate.
    assert [e.anchor.quote for e in log.entries] == ["first line", "second line"]


def test_ac2_the_refusal_detail_names_the_drift_and_the_replan_guidance_verbatim():
    spy = TransportSpy(document_revisions=[171], blocks=_fresh_blocks())
    log = apply(dry_run([_req("first line")], _tree(), document_revision_id=155),
                _spy_client(spy), "docABC")
    detail = log.entries[0].refusal.detail
    assert "155" in detail and "171" in detail          # names the drift
    assert REPLAN_GUIDANCE in detail                    # verbatim re-plan guidance
    assert CONCURRENCY_WARNING in detail                # verbatim concurrency warning
    assert "ZERO" in detail or "zero" in detail         # says no write was issued
    assert "docABC" in detail                           # names the document


def test_ac2_the_refusal_reason_string_is_stable_on_the_wire():
    assert RefusalReason.STALE_DOCUMENT.value == "stale-document"
    refusal = Refusal.stale_document(detail="d")
    assert refusal.to_dict() == {"reason": "stale-document", "detail": "d"}
    assert Refusal.from_dict(refusal.to_dict()) == refusal


def test_ac2_a_detail_less_stale_document_refusal_is_unconstructable():
    """The LD-131 mandatory-detail contract extends to the new reason."""
    with pytest.raises(TypeError):
        Refusal.stale_document()
    with pytest.raises(ValueError):
        Refusal.stale_document(detail="   ")


def test_ac2_the_re_read_happens_before_any_write_not_after():
    """"Immediately before apply": the meta read is the FIRST call of the apply, so no
    write can precede the check."""
    spy = TransportSpy(document_revisions=[5, 5], blocks=_fresh_blocks())
    apply(dry_run([_req("first line")], _tree(), document_revision_id=5),
          _spy_client(spy), "docABC")
    first = spy.calls[0]
    assert first[0] == "GET" and _DOC_META_RE.search(first[1]), spy.calls


# =========================================================================== #
# AC3 — THE CENTERPIECE: ZERO writes issued on refusal, proved by the spy.     #
# =========================================================================== #

def test_ac3_a_refusal_issues_zero_write_calls_at_the_transport():
    spy = TransportSpy(document_revisions=[6], blocks=_fresh_blocks())
    apply(dry_run([_req("first line")], _tree(), document_revision_id=5),
          _spy_client(spy), "docABC")
    assert spy.writes == [], f"a STALE_DOCUMENT refusal wrote: {spy.writes}"


def test_ac3_a_refusal_costs_exactly_one_call_and_it_is_the_meta_read():
    """Not merely "no writes" — the engine does not even re-read the anchored blocks,
    because the batch is already decided. One read, zero writes."""
    spy = TransportSpy(document_revisions=[6], blocks=_fresh_blocks())
    apply(dry_run([_req("first line"), _req("second line")], _tree(),
                  document_revision_id=5), _spy_client(spy), "docABC")
    assert len(spy.calls) == 1
    assert spy.calls[0][0] == "GET" and _DOC_META_RE.search(spy.calls[0][1])


def _write_family_request(op):
    """One request per write family, for the "every family refuses" parametrization."""
    from larkdocio.write.model import DeleteRequest, SubSpanEditRequest

    return {
        "edit": lambda: _req("first line"),
        "insert": lambda: _insert("first line", InsertPosition.AFTER, ["NEW"]),
        "delete": lambda: DeleteRequest(target=AnchorById(block_id="p1")),
        "subspan": lambda: SubSpanEditRequest(
            anchor=AnchorById(block_id="p1"), span="first", replacement="1st"),
    }[op]()


@pytest.mark.parametrize("op", ["edit", "insert", "delete", "subspan"])
def test_ac3_zero_writes_holds_for_every_write_family(op):
    """A destructive delete and a content-creating insert are exactly the ops where a
    leaked write would hurt most — the spy proves none of the four families slips past.

    The type check reads the expected request class off the **op registry**
    (:data:`~larkdocio.write.ops.OPS`), so this test cannot quietly exercise the same family
    four times: mis-wire a builder and it reddens here, naming both families. (LD-142 rider:
    it used to say ``isinstance(request, (EditRequest, DeleteRequest, SubSpanEditRequest))
    or True`` — the ``or True`` made the whole line vacuous, and it was there because the
    tuple had no ``InsertRequest`` in it.)
    """
    from larkdocio.write.ops import OPS

    request = _write_family_request(op)
    expected = {d.kind: d.request_type for d in OPS}[op]
    assert isinstance(request, expected), (
        f"the {op!r} case must exercise a {expected.__name__}, "
        f"got a {type(request).__name__}")

    spy = TransportSpy(document_revisions=[7], blocks=_fresh_blocks())
    log = apply(dry_run([request], _tree(), document_revision_id=5),
                _spy_client(spy), "docABC")
    assert log.entries[0].refusal.reason is RefusalReason.STALE_DOCUMENT
    assert spy.writes == []


def test_ac3_the_write_family_type_check_actually_bites():
    """The rider's proof (LD-142). The restored ``isinstance`` above is only worth writing if
    it FAILS on a mis-wired builder — with ``or True`` appended it could not fail at all.
    Feeding the check a request of the wrong family here shows it discriminates, without
    having to break the parametrization to find out."""
    from larkdocio.write.ops import OPS

    by_kind = {d.kind: d.request_type for d in OPS}
    for op in ("edit", "insert", "delete", "subspan"):
        request = _write_family_request(op)
        assert isinstance(request, by_kind[op])
        wrong = next(k for k in by_kind if k != op and not isinstance(request, by_kind[k]))
        assert not isinstance(request, by_kind[wrong]), (
            f"a {op!r} request must NOT satisfy the {wrong!r} family's type — the check "
            f"would not discriminate")


def test_ac3_partial_application_is_impossible_for_a_ten_request_batch():
    """The batch-wide refusal: 10 resolvable requests, drift detected → all 10 refused,
    and the spy shows **0** writes. There is no "the first three landed" outcome."""
    tree = _page(*[_para(f"b{i}", f"line {i}") for i in range(10)])
    blocks = _live_blocks(**{f"b{i}": f"line {i}" for i in range(10)})
    plan = dry_run([_req(f"line {i}", replacement=f"NEW {i}") for i in range(10)],
                   tree, document_revision_id=100)
    assert len(plan.resolved) == 10, "the batch must be fully resolvable pre-drift"
    spy = TransportSpy(document_revisions=[101], blocks=blocks)
    log = apply(plan, _spy_client(spy), "docABC")
    assert len(log.entries) == 10
    assert {e.outcome for e in log.entries} == {"refused"}
    assert {e.refusal.reason for e in log.entries} == {RefusalReason.STALE_DOCUMENT}
    assert spy.writes == []


def test_ac3_a_pre_existing_refusal_still_becomes_stale_document_not_a_write():
    """A batch that already carried a dry-run refusal (an ambiguous anchor) is still
    refused wholesale — the entry keeps *a* refusal either way, and nothing writes."""
    tree = _page(_para("d1", "twin"), _para("d2", "twin"), _para("p1", "first line"))
    plan = dry_run([_req("twin"), _req("first line")], tree, document_revision_id=5)
    assert plan.refusals[0].refusal.reason is RefusalReason.AMBIGUOUS
    spy = TransportSpy(document_revisions=[6], blocks=_live_blocks(p1="first line"))
    log = apply(plan, _spy_client(spy), "docABC")
    assert {e.refusal.reason for e in log.entries} == {RefusalReason.STALE_DOCUMENT}
    assert spy.writes == []


# =========================================================================== #
# AC6 — the injected-transport matrix, both ways.                              #
# =========================================================================== #

@pytest.mark.parametrize("cached,live,expected", [
    (5, 5, "applied"),          # unchanged            → applies
    (5, 6, "refused"),          # advanced by 1        → refuses
    (5, 500, "refused"),        # advanced by many     → refuses
    (155, 171, "refused"),      # the spike's real bump→ refuses
    (6, 5, "refused"),          # went BACKWARDS (impossible live) → still refuses
])
def test_ac6_matrix_revision_transitions(cached, live, expected):
    spy = TransportSpy(document_revisions=[live], blocks=_fresh_blocks())
    log = apply(dry_run([_req("first line")], _tree(), document_revision_id=cached),
                _spy_client(spy), "docABC")
    assert [e.outcome for e in log.entries] == [expected]
    if expected == "refused":
        assert spy.writes == []
    else:
        assert spy.writes


def test_ac6_unavailable_at_plan_applies_under_the_per_anchor_defenses_only():
    """No anchor to compare → no whole-doc CAS (and no wasted call), the marker says so,
    and the **existing** per-anchor re-validation is still the guard that runs."""
    spy = TransportSpy(blocks=_fresh_blocks())
    log = apply(dry_run([_req("first line")], _tree()), _spy_client(spy), "docABC")
    assert [e.outcome for e in log.entries] == ["applied"]
    assert log.revision_guard == REVISION_GUARD_UNAVAILABLE
    assert spy.meta_reads == 0, "an unavailable guard must not burn a throttled call"


def test_ac6_unavailable_at_plan_still_refuses_a_drifted_anchor_stale_anchor():
    """The per-anchor tier is untouched: with the document guard unavailable, a block that
    drifted under its anchor still refuses ``stale-anchor`` with no write."""
    spy = TransportSpy(blocks=_live_blocks(p1="something else entirely"))
    log = apply(dry_run([_req("first line")], _tree()), _spy_client(spy), "docABC")
    assert log.entries[0].refusal.reason is RefusalReason.STALE_ANCHOR
    assert spy.writes == []


def test_ac6_unavailable_at_apply_refuses_conservatively():
    """The plan HAS an anchor but the live revision reads back as ``None`` — the document
    cannot be *confirmed* unchanged, so the conservative posture refuses the whole batch
    rather than writing on an unverifiable assumption."""
    spy = TransportSpy(meta_payload={"code": 0, "data": {"document": {
        "document_id": "docABC", "title": "meta with no revision"}}},
        blocks=_fresh_blocks())
    log = apply(dry_run([_req("first line")], _tree(), document_revision_id=5),
                _spy_client(spy), "docABC")
    assert log.entries[0].refusal.reason is RefusalReason.STALE_DOCUMENT
    assert "could not" in log.entries[0].refusal.detail.lower()
    assert REPLAN_GUIDANCE in log.entries[0].refusal.detail
    assert spy.writes == []


def test_ac6_a_meta_read_that_errors_refuses_conservatively_with_larks_own_words():
    spy = TransportSpy(meta_error={"code": 1770001, "msg": "no permission"},
                       blocks=_fresh_blocks())
    log = apply(dry_run([_req("first line")], _tree(), document_revision_id=5),
                _spy_client(spy), "docABC")
    refusal = log.entries[0].refusal
    assert refusal.reason is RefusalReason.STALE_DOCUMENT
    assert "1770001" in refusal.detail and "no permission" in refusal.detail
    assert spy.writes == []


def test_ac6_a_rate_limit_on_the_meta_read_is_not_reported_as_staleness():
    """Throttling is not drift. Misreporting it as ``STALE_DOCUMENT`` would send a
    consumer to re-plan a document that never changed (the ``_live_or_stale`` doctrine)."""
    class _RateLimited(TransportSpy):
        def __call__(self, req, timeout=30):
            self.calls.append((req.get_method(), req.full_url))
            raise LarkRateLimitError("99991400 too many requests", code=99991400)

    spy = _RateLimited(blocks=_fresh_blocks())
    with pytest.raises(LarkRateLimitError):
        apply(dry_run([_req("first line")], _tree(), document_revision_id=5),
              _spy_client(spy), "docABC")
    assert spy.writes == []


def test_ac6_the_batch_wide_refusal_is_not_the_drifted_entry_alone():
    """The whole point of D9 over ``STALE_ANCHOR``: drift is a property of the DOCUMENT,
    so every entry refuses — including the ones whose own targets are pristine."""
    tree = _page(_para("p1", "first line"), _para("p2", "second line"),
                 _para("p3", "third line"))
    spy = TransportSpy(document_revisions=[9],
                       blocks=_live_blocks(p1="first line", p2="second line",
                                           p3="third line"))
    log = apply(dry_run([_req("first line"), _req("second line"), _req("third line")],
                        tree, document_revision_id=8), _spy_client(spy), "docABC")
    assert len(log.entries) == 3
    assert all(e.refusal.reason is RefusalReason.STALE_DOCUMENT for e in log.entries)
    assert spy.writes == []


def test_ac6_drift_landing_between_the_dry_run_and_the_apply_is_the_case_caught():
    """The amplifier's exact race: the plan is built, THEN somebody edits, THEN apply
    runs. Modelled by letting the meta read hand back a bumped revision only at apply."""
    tree, blocks = _tree(), _fresh_blocks()
    spy = TransportSpy(document_revisions=[5], blocks=blocks)
    client = _spy_client(spy)
    cached = client.read_document_revision("docABC")        # plan-time capture
    plan = dry_run([_req("first line"), _req("second line")], tree,
                   document_revision_id=cached)
    assert plan.revision_guard == REVISION_GUARD_ACTIVE
    spy._revisions = [6]                                   # ← the out-of-band edit lands
    spy.meta_reads = 0
    log = apply(plan, client, "docABC")
    assert all(e.refusal.reason is RefusalReason.STALE_DOCUMENT for e in log.entries)
    assert spy.writes == []


# =========================================================================== #
# AC5 — no auto-mapping / reconciliation: refusal is the ONLY drift outcome.    #
# =========================================================================== #

def test_ac5_the_document_guard_fires_even_when_every_anchor_still_matches():
    """**THE case that motivated D9.** Drift AROUND the anchor: an insertion above the
    target leaves every anchor's own precondition satisfied — the quote is still there,
    a by-id block's text is byte-identical — so ``STALE_ANCHOR`` sees nothing. The
    whole-document CAS is what refuses. Both guards fire independently."""
    tree = _page(_para("p1", "first line"))
    # The live block is PRISTINE: the quote and the by-id precondition both still hold,
    # so nothing about the anchor is stale...
    blocks = _live_blocks(p1="first line")
    quote_plan = dry_run([_req("first line")], tree, document_revision_id=5)
    id_plan = dry_run([_req("first line")], tree, document_revision_id=5)
    for plan in (quote_plan, id_plan):
        spy = TransportSpy(document_revisions=[6], blocks=blocks)
        log = apply(plan, _spy_client(spy), "docABC")
        # ...yet the batch refuses, because the DOCUMENT moved under the plan.
        assert log.entries[0].refusal.reason is RefusalReason.STALE_DOCUMENT
        assert spy.writes == []
    # Control: same pristine anchors, revision unchanged → it applies. So the refusal
    # above is attributable to the document guard alone, not to the anchor check.
    spy = TransportSpy(document_revisions=[5], blocks=blocks)
    control = apply(dry_run([_req("first line")], tree, document_revision_id=5),
                    _spy_client(spy), "docABC")
    assert control.entries[0].outcome == "applied"


def test_ac5_an_id_anchored_batch_refuses_the_document_before_the_block_cas():
    """The two compare-and-swaps compose without interfering: the document CAS is the
    outer one, so a drifted document refuses before any block is even re-read."""
    from larkdocio.write.model import EditRequest

    tree = _page(_para("p1", "first line"))
    plan = dry_run([EditRequest(anchor=AnchorById(block_id="p1"), replacement="X")],
                   tree, document_revision_id=5)
    spy = TransportSpy(document_revisions=[6], blocks=_live_blocks(p1="first line"))
    log = apply(plan, _spy_client(spy), "docABC")
    assert log.entries[0].refusal.reason is RefusalReason.STALE_DOCUMENT
    assert len(spy.calls) == 1                     # the block was never even read
    assert spy.writes == []


@pytest.mark.parametrize("live", [6, 7, 12, 9999])
def test_ac5_the_only_drift_outcome_is_a_refusal_never_an_accommodation(live):
    """No "best-effort" branch: across drift magnitudes the outcome shape is invariant —
    every entry refused, zero writes, no re-located anchor, no re-indexed insertion."""
    plan = dry_run([_insert("first line", InsertPosition.AFTER, ["NEW"])], _tree(),
                   document_revision_id=5)
    spy = TransportSpy(document_revisions=[live], blocks=_fresh_blocks())
    log = apply(plan, _spy_client(spy), "docABC")
    assert [e.outcome for e in log.entries] == ["refused"]
    assert log.entries[0].created_block_ids == ()       # nothing was created
    assert spy.writes == []


_NO_ACCOMMODATION_WORDS = (
    "remap", "relocate", "reindex", "reconcil", "accommodat",
    "besteffort", "best_effort", "fallback_position", "fuzzy", "nearest", "rebase",
)

#: The one exemption, and it is this guard's own subject seen from the other side: a
#: reconciliation refusal **named for the loss mode it refuses**. ``marker-relocated`` is
#: what the library answers when a surviving marker came back sitting on another block's
#: text — a refusal that plans nothing, never a re-location of anything. Any *other*
#: identifier carrying the accommodation vocabulary still reddens here.
_REFUSAL_NAMES_A_LOSS_MODE = {"marker_relocated"}

_GUARDED_SOURCES = (
    _WRITE_DIR / "apply.py",
    _WRITE_DIR / "preview.py",
    _WRITE_DIR / "revision.py",
    _WRITE_DIR / "ops.py",
    _WRITE_DIR / "model" / "refusal.py",
)


def _code_identifiers(tree):
    """Every code-level identifier — docstrings/comments excluded, so prose may *describe*
    what the engine refuses to do without the guard mistaking it for a code path."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            names.add(node.arg)
    return names


@pytest.mark.parametrize("path", _GUARDED_SOURCES, ids=lambda p: p.name)
def test_ac5_no_accommodation_vocabulary_exists_in_the_engine(path):
    """AC5, structurally: the engine has **no** identifier for re-locating an anchor,
    re-indexing a position, or reconciling drift. A future "helpful" accommodation path
    would have to name itself — and this reddens when it does."""
    idents = {n.lower() for n in _code_identifiers(ast.parse(path.read_text(encoding="utf-8")))}
    for word in _NO_ACCOMMODATION_WORDS:
        offenders = {n for n in idents if word in n} - _REFUSAL_NAMES_A_LOSS_MODE
        assert not offenders, f"drift-accommodation vocabulary in {path.name}: {offenders}"


def test_ac5_the_document_cas_has_exactly_one_call_site():
    """One gate, called once, from ``apply`` — not a helper a second code path could
    skip. (A second call site would be a second policy.)"""
    tree = ast.parse((_WRITE_DIR / "apply.py").read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "_document_cas"]
    assert len(calls) == 1, f"_document_cas is called {len(calls)} times"


def test_ac5_apply_returns_immediately_on_the_refusal_log():
    """The drift branch **returns**; it does not fall through into the write loop, and it is
    not a log-and-continue. Pinned at the AST level so a later "helpful" edit that turns the
    early return into a warning reddens instead of shipping."""
    tree = ast.parse((_WRITE_DIR / "apply.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "apply")
    # the statement that runs the CAS, and the guard immediately after it
    body = fn.body
    cas_at = next(i for i, s in enumerate(body)
                  if "_document_cas(" in ast.unparse(s))
    guard = body[cas_at + 1]
    assert isinstance(guard, ast.If), f"the CAS result is not guarded: {ast.unparse(guard)}"
    assert "is not None" in ast.unparse(guard.test)
    assert len(guard.body) == 1 and isinstance(guard.body[0], ast.Return), (
        f"the drift branch must RETURN immediately; got {ast.unparse(guard)}")
    assert not guard.orelse
    # ...and it happens before the entry loop (no write can precede it).
    loop_at = next(i for i, s in enumerate(body) if isinstance(s, ast.For))
    assert cas_at < loop_at


# =========================================================================== #
# AC7 — findings-agnostic; the AST findings-vocabulary guard extends.          #
# =========================================================================== #

@pytest.mark.parametrize("path", _GUARDED_SOURCES, ids=lambda p: p.name)
def test_ac7_the_new_modules_reference_no_findings_vocabulary(path):
    idents = {n.lower() for n in _code_identifiers(ast.parse(path.read_text(encoding="utf-8")))}
    for word in ("finding", "layer", "severity", "accepted", "rejected"):
        offenders = {n for n in idents if word in n}
        assert not offenders, f"findings-schema vocabulary in {path.name}: {offenders}"


def test_ac7_the_findings_guard_actually_sees_the_new_symbols():
    """A guard that scanned nothing would pass vacuously — prove the new module's own
    symbols are in the scanned set."""
    idents = _code_identifiers(ast.parse((_WRITE_DIR / "revision.py").read_text(encoding="utf-8")))
    assert {"revision_guard_status", "revision_guard_semantics",
            "stale_document_detail"} <= idents


def _import_roots(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module)
    return roots


def test_ac7_the_revision_module_stays_dependency_free():
    """AC7's dependency floor, kept exactly as strict through LD-143's extraction.

    The marker vocabulary moved to the shared leaf ``larkdocio.common.staleness`` (T1 — one
    core for docx + sheets, which had drifted), so this module's imports are now *the standard
    library plus that one leaf* — and the leaf itself is asserted stdlib-only below, which
    closes the transitive claim. Anything else appearing here (the SDK, a client, a model)
    would mean the vocabulary stopped being dumb, which is the property AC7 protects."""
    import sys

    stdlib = set(sys.stdlib_module_names)
    shared_leaf = "larkdocio.common.staleness"

    roots = _import_roots(_WRITE_DIR / "revision.py")
    non_stdlib = {r for r in roots if r.split(".")[0] not in stdlib}
    assert non_stdlib <= {shared_leaf}, non_stdlib

    # ...and the leaf is itself dependency-free, so the floor holds transitively.
    leaf_roots = _import_roots(_SRC / "common" / "staleness.py")
    assert {r.split(".")[0] for r in leaf_roots} <= stdlib, leaf_roots


# =========================================================================== #
# AC8 — truth rows: capabilities(), the guide, BLOCKS.md.                      #
# =========================================================================== #

def test_ac8_capabilities_gains_the_stale_document_safety_contract():
    caps = capabilities(full=True)
    assert "STALE_DOCUMENT" in caps["safety_contracts"]
    contract = caps["safety_contracts"]["STALE_DOCUMENT"]
    assert contract["applies_to"] == ["docx-write"]
    summary = contract["summary"].lower()
    for phrase in ("revision", "whole", "zero", "re-plan"):
        assert phrase in summary, f"the safety descriptor omits {phrase!r}: {summary}"


def test_ac8_the_docx_write_surface_lists_it_and_sheets_does_not():
    caps = capabilities(full=True)
    docx = caps["surfaces"]["docx-write"]["safety_contracts"]
    sheets = caps["surfaces"]["sheets-write"]["safety_contracts"]
    assert "STALE_DOCUMENT" in docx and "STALE_ANCHOR" in docx
    assert "STALE_DOCUMENT" not in sheets, "STALE_DOCUMENT is the docx-side guard"


def test_ac8_the_safety_descriptor_resolves_to_real_refusal_machinery():
    """A phantom safety claim is a lie — the descriptor names machinery that exists, by the
    same wire string the apply-log will actually carry."""
    assert callable(Refusal.stale_document)
    summary = capabilities(full=True)["safety_contracts"]["STALE_DOCUMENT"]["summary"]
    assert RefusalReason.STALE_DOCUMENT.value in summary
    assert "document_revision_id" in summary          # the knob a consumer needs
    assert "revision_guard" in summary                # the never-silent marker


def test_ac8_the_guide_documents_the_contract_and_the_refusal_vocabulary():
    from larkdocio import guide

    text = guide(full=True)
    assert "STALE_DOCUMENT" in text
    assert "stale-document" in text
    # The mechanism (LD-139) now joins LD-138's mechanism-free concurrency doctrine.
    doctrine = text.split("### Do not edit the document while an authoring session runs")[1]
    doctrine = doctrine.split("\n## ")[0]
    for phrase in ("document_revision_id", "revision_id", "STALE_DOCUMENT"):
        assert phrase in doctrine, f"the D9 doctrine section omits {phrase!r}"


def test_ac8_blocks_md_write_support_notation_references_the_document_guard():
    """AC8: the matrix's Write column cannot promise "creatable" without saying under what
    guard. Asserted at **content** level (the claims, not one token) so a reflow is fine and
    a gutted paragraph reddens — the LD-138 doctrine-guard shape."""
    text = (Path(__file__).resolve().parents[1] / "BLOCKS.md").read_text(encoding="utf-8")
    section = text.split("## Write-support vocabulary")[1].split("\n## ")[0]
    lowered = " ".join(section.lower().split())
    assert "STALE_DOCUMENT" in section, (
        "the BLOCKS.md write-support notation must reference the whole-document guard "
        "that governs every creation (LD-139 AC8)")
    for claim in ("whole-document", "entire", "zero writes", "previewed position"):
        assert claim in lowered, (
            f"the write-support notation names STALE_DOCUMENT but not what it does "
            f"({claim!r} missing) — a truth row that states the guarantee is the point")


# =========================================================================== #
# Amplifier — the wording is ONE source, coordinated with LD-138's guide prose. #
# =========================================================================== #

def test_the_concurrency_warning_is_the_same_sentence_the_guide_ships():
    """LD-138 shipped the do-not-edit-concurrently prose; LD-139 ships the mechanism.
    The refusal's own wording is bound to the guide's, so the two cannot drift."""
    from larkdocio import guide

    assert CONCURRENCY_WARNING.strip()
    assert CONCURRENCY_WARNING in guide(full=True), (
        "the refusal detail's concurrency warning must be the guide's own sentence")


def test_the_replan_guidance_is_one_source_used_by_every_stale_document_detail():
    from larkdocio.write.revision import (
        stale_document_detail,
        unconfirmable_document_detail,
    )

    drift = stale_document_detail(document_id="d", cached=1, live=2)
    unknown = unconfirmable_document_detail(document_id="d", cached=1, why="because")
    for detail in (drift, unknown):
        assert REPLAN_GUIDANCE in detail
        assert CONCURRENCY_WARNING in detail
        assert "no auto" in detail.lower() or "never" in detail.lower()
        Refusal.stale_document(detail=detail)      # constructible ⇒ non-empty
