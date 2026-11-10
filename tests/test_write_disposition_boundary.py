"""LD-643 — the docx write engine's two safety gaps, both closed and both watched.

**(a) The disposition boundary.** ``larkdocio.write`` was the only plan-gated engine with no
``WriteWatch`` / ``classify_apply_exception``: a grep for either name across ``write/``
returned nothing while ``sheets/`` and both Base engines bound them, all three riding the
shared stdlib-only leaf ``larkdocio.common.disposition``. The docx entry loop had no
``except``, so a ``LarkAPIError`` from a create/patch/delete propagated out of ``apply()`` and
the consumer received **no apply-log at all** — including for the entries that had already
written, which is the exact state ``write/README.md`` argues the 1:1 log exists to prevent.

**(b) The unbounded walk.** ``WriteClient.list_document_blocks`` walked ``has_more`` /
``page_token`` with a bare ``while True:`` — no page cap, no seen-cursor guard — while
``comments/client.py`` and ``base/client.py`` both walk with ``for _ in range(MAX_PAGES)`` and
a ``seen`` set. Its own docstring said it walked *"exactly the way the reader walks the same
endpoint"*, and the reader's two walks of this endpoint family are the two **unguarded** ones
in the tree: it had copied the wrong sibling, in writing.

The two arms are tested together because they meet: a walk that now refuses raises **inside**
the boundary the first arm installed, so the pathological pagination becomes a typed apply-log
entry rather than an escape.

**What this file does NOT test, deliberately.** ``read/client.py``'s two walks are the same
class and are out of scope — the reader is the determinism-guaranteed path and a
pacing/termination change there needs its own decision. They are named, with evidence, by
:func:`test_the_readers_two_walks_are_reported_not_fixed`, which asserts they are still
unguarded so the report cannot go stale silently.
"""
import inspect
import pathlib
import re

import pytest

from larkdocio.common.disposition import ENTRY_SCOPED, SYSTEMIC
from larkdocio.common.disposition import WriteWatch as SharedWriteWatch
from larkdocio.errors import (
    LarkAPIError,
    LarkApplyRefusedError,
    LarkPaginationError,
    LarkPermissionError,
    LarkRateLimitError,
)
from larkdocio.write import disposition as docx_disposition
from larkdocio.write.apply import apply as docx_apply
from larkdocio.write.client import (
    BLOCK_LIST_PAGE_SIZE,
    MAX_BLOCK_LIST_PAGES,
    WriteClient,
)
from larkdocio.write.disposition import (
    FILE_LIFECYCLE_SEAMS,
    READ_SEAMS,
    WRITE_SEAMS,
    DocxWriteWatch,
    classify_apply_exception,
)
from larkdocio.write.model import ApplyLogEntry, RefusalReason
from larkdocio.write.preview import dry_run as docx_dry_run

from write_harness import (
    RoutingOpener,
    _block_payload,
    _client,
    _page,
    _para,
    _req,
    _run,
)

_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "larkdocio"


# =========================================================================== #
# The fixture: a three-entry batch whose SECOND write fails.                   #
# =========================================================================== #

class FailingPatchOpener(RoutingOpener):
    """:class:`RoutingOpener`, with the ``n``-th element PATCH answering a Lark error body.

    Counted over **write** calls rather than over all calls, so the per-entry re-validation
    reads do not shift which entry fails when a test changes the batch.
    """

    def __init__(self, *, fail_on_write, body, **kwargs):
        super().__init__(**kwargs)
        self._fail_on_write = fail_on_write
        self._body = body
        self._writes = 0

    def __call__(self, req, timeout=30):
        if req.get_method() in self.WRITE_METHODS:
            self._writes += 1
            if self._writes == self._fail_on_write:
                self.calls.append({"method": req.get_method(),
                                   "path": req.full_url.split(".com", 1)[-1],
                                   "body": None})
                from write_harness import _FakeHTTPResponse
                return _FakeHTTPResponse(self._body)
        return super().__call__(req, timeout)


_API_REJECTION = {"code": 1770002, "msg": "block not found"}


def _three_entry_batch(*, body=_API_REJECTION, fail_on_write=2):
    """A resolved three-entry plan over three paragraphs; write #``fail_on_write`` is refused.

    Returns ``(plan, client, opener)``.
    """
    tree = _page(_para("p1", "alpha"), _para("p2", "beta"), _para("p3", "gamma"))
    plan = docx_dry_run(
        [_req(q, replacement=f"{q}!") for q in ("alpha", "beta", "gamma")], tree)
    opener = FailingPatchOpener(
        fail_on_write=fail_on_write, body=body,
        blocks={
            "p1": _block_payload("p1", [_run("alpha")], parent_id="root"),
            "p2": _block_payload("p2", [_run("beta")], parent_id="root"),
            "p3": _block_payload("p3", [_run("gamma")], parent_id="root"),
            "root": _block_payload("root", [], block_type=1),
        })
    return plan, _client(opener), opener


# =========================================================================== #
# AC1 — the 1:1 contract holds under a mid-batch write failure.                #
# =========================================================================== #

def test_ac1_a_midbatch_api_failure_yields_a_complete_log_instead_of_escaping():
    """**The regression test.** On ``develop`` this raises ``LarkAPIError`` and the caller
    gets no log; here it raises the plan-gated ``LarkApplyRefusedError`` carrying a log that
    is 1:1 with the plan, in order."""
    plan, client, _opener = _three_entry_batch()

    with pytest.raises(LarkApplyRefusedError) as caught:
        docx_apply(plan, client, "doc-1")

    log = caught.value.log
    assert len(log.entries) == len(plan.entries) == 3
    assert [e.outcome for e in log.entries] == ["applied", "refused", "not-attempted"]

    # The failing entry carries the CLASSIFIED disposition, not a plan-time reason.
    failed = log.entries[1]
    assert failed.refusal.reason is RefusalReason.API_ERROR
    assert "1770002" in failed.refusal.detail or "code=" in failed.refusal.detail
    assert "NOTHING landed" in failed.refusal.detail

    # The remainder is classified the way the sibling engines classify a halt.
    assert log.entries[2].refusal.reason is RefusalReason.NOT_ATTEMPTED
    assert "NEVER ATTEMPTED" in log.entries[2].refusal.detail

    # And the entry that landed BEFORE the failure is visible — the whole point.
    assert log.entries[0].outcome == "applied"
    assert log.applied == (log.entries[0],)


def test_ac1_the_same_run_returns_that_log_under_the_partial_optin():
    """``allow_partial=True`` returns exactly the log the raise carries — no second shape."""
    plan, client, _opener = _three_entry_batch()
    log = docx_apply(plan, client, "doc-1", allow_partial=True)
    assert [e.outcome for e in log.entries] == ["applied", "refused", "not-attempted"]
    assert len(log) == 3
    assert list(log) == list(log.entries)


def test_ac1_the_halt_is_disclosed_on_the_log_and_serializes():
    plan, client, _opener = _three_entry_batch()
    log = docx_apply(plan, client, "doc-1", allow_partial=True)
    assert log.halt == {
        "index": 1,
        "reason": RefusalReason.API_ERROR.value,
        "detail": log.entries[1].refusal.detail,
        "landed": "no",
        "not_attempted": 1,
    }
    assert log.to_dict()["halt"] == log.halt


def test_ac1_a_halted_batch_issues_no_further_writes():
    """Halting is the PRE-EXISTING behaviour preserved: entries after the failure were never
    attempted before the boundary either, and they still are not. A safety fix that quietly
    started writing where the previous release stopped would be the worse defect."""
    plan, client, opener = _three_entry_batch()
    docx_apply(plan, client, "doc-1", allow_partial=True)
    # Two write attempts: entry 1's patch, entry 2's refused patch. Entry 3: none.
    assert len(opener.writes) == 2


def test_ac1_the_log_round_trips_through_json_with_every_new_outcome():
    from larkdocio.write.model import ApplyLog

    plan, client, _opener = _three_entry_batch()
    log = docx_apply(plan, client, "doc-1", allow_partial=True)
    back = ApplyLog.from_json(log.to_json())
    assert [e.outcome for e in back.entries] == [e.outcome for e in log.entries]
    assert [e.refusal for e in back.entries] == [e.refusal for e in log.entries]
    assert back.halt == log.halt


def test_ac1_an_unmodelled_exception_is_logged_failed_not_refused():
    """``failed`` means INDETERMINATE. Calling it ``refused`` would claim "nothing landed",
    which is the guess the boundary exists not to make."""
    plan, client, _opener = _three_entry_batch()

    class Boom(Exception):
        pass

    import larkdocio.write.ops as ops
    real = ops.apply_dispatch
    calls = {"n": 0}

    def exploding(entry, client_, document_id):
        calls["n"] += 1
        if calls["n"] == 2:
            raise Boom("something nobody modelled")
        return real(entry, client_, document_id)

    ops.apply_dispatch = exploding
    try:
        log = docx_apply(plan, client, "doc-1", allow_partial=True)
    finally:
        ops.apply_dispatch = real

    assert [e.outcome for e in log.entries] == ["applied", "failed", "not-attempted"]
    assert log.entries[1].refusal.reason is RefusalReason.UNEXPECTED_ERROR
    assert log.indeterminate == (log.entries[1],)
    assert log.entries[1] not in log.applied


def test_ac1_a_failure_after_the_write_returned_is_applied_unverified_never_refused():
    """The write-watch's whole job: a post-write step that fails must NOT be reported as
    "nothing landed"."""
    # No scripted API rejection here: the write must RETURN, and the failure comes after it.
    plan, client, _opener = _three_entry_batch(fail_on_write=0)

    import larkdocio.write.ops as ops
    real = ops.apply_dispatch
    calls = {"n": 0}

    def write_then_explode(entry, client_, document_id):
        calls["n"] += 1
        if calls["n"] == 2:
            # Enter and RETURN from a real write seam, then fail.
            client_._patch_block(document_id, "p2", {"update_text_elements": {"elements": []}})
            raise RuntimeError("the verification read blew up")
        return real(entry, client_, document_id)

    ops.apply_dispatch = write_then_explode
    try:
        log = docx_apply(plan, client, "doc-1", allow_partial=True)
    finally:
        ops.apply_dispatch = real

    entry = log.entries[1]
    assert entry.outcome == "applied-unverified"
    assert entry.refusal.reason is RefusalReason.UNVERIFIED_WRITE
    assert "_patch_block" in entry.refusal.detail
    assert "IS in the document" in entry.refusal.detail
    # It LANDED — so it is on `applied`, and it is not on the refusals-as-nothing-landed side
    # for the wrong reason: `gate_refusals` still raises, because the batch halted.
    assert entry in log.applied
    assert entry not in log.refusals


def test_ac1_the_boundary_does_not_swallow_baseexception():
    """The deliberate carve-out, pinned rather than left to be rediscovered."""
    plan, client, _opener = _three_entry_batch()

    import larkdocio.write.ops as ops
    real = ops.apply_dispatch

    def interrupted(entry, client_, document_id):
        raise KeyboardInterrupt

    ops.apply_dispatch = interrupted
    try:
        with pytest.raises(KeyboardInterrupt):
            docx_apply(plan, client, "doc-1", allow_partial=True)
    finally:
        ops.apply_dispatch = real


def test_ac1_a_plan_time_refusal_still_reads_exactly_as_it_did():
    """The boundary must not re-classify a refusal decided at dry-run. A plan-time refusal is
    carried into the log verbatim, no write, and it does NOT halt the batch."""
    tree = _page(_para("p1", "present"))
    plan = docx_dry_run([_req("absent"), _req("present")], tree)
    opener = RoutingOpener(blocks={
        "p1": _block_payload("p1", [_run("present")], parent_id="root"),
        "root": _block_payload("root", [], block_type=1),
    })
    log = docx_apply(plan, _client(opener), "doc-1", allow_partial=True)
    assert [e.outcome for e in log.entries] == ["refused", "applied"]
    assert log.entries[0].refusal.reason is RefusalReason.NOT_FOUND
    assert log.halt is None


# =========================================================================== #
# AC2 — the SHARED leaf is used, not a fourth copy.                            #
# =========================================================================== #

def test_ac2_the_watch_is_the_shared_leafs_class_with_only_a_seam_default_added():
    assert issubclass(DocxWriteWatch, SharedWriteWatch)
    assert DocxWriteWatch.DEFAULT_SEAMS == WRITE_SEAMS
    # Its ONLY content is that default: no method of the mechanism is re-authored here.
    own = {n for n in vars(DocxWriteWatch) if not n.startswith("__")}
    assert own == {"DEFAULT_SEAMS"}, own


def test_ac2_no_mechanism_is_copied_into_the_docx_module():
    """The leaf's own rule is *share the mechanism, never the classification*. So the docx
    module may hold rows, templates and seam sets — and must hold no second copy of the
    ``Disposition`` dataclass, the watch's forwarding, or the never-raising text helpers."""
    source = (_SRC / "write" / "disposition.py").read_text(encoding="utf-8")
    for copied in ("class Disposition", "def safe_text", "def safe_denial",
                   "def disposition_detail", "def __getattr__"):
        assert copied not in source, copied
    # …and it imports every one of them from the leaf instead.
    assert "from larkdocio.common.disposition import" in source


def test_ac2_the_write_seam_set_is_exhaustive_over_the_clients_real_surface():
    """A write op that forgets to register a seam would make the engine claim "nothing landed"
    about a call that landed something. Enumerated from the class, never from a list."""
    public = {n for n, v in vars(WriteClient).items()
              if callable(v) and not n.startswith("__")}
    # `_patch_block` is private but IS the seam the apply legs call, so it is named explicitly.
    declared = WRITE_SEAMS | FILE_LIFECYCLE_SEAMS | READ_SEAMS
    unclassified = {n for n in public if not n.startswith("_")} - declared
    assert unclassified == set(), unclassified
    assert "_patch_block" in WRITE_SEAMS
    # The three categories are disjoint — a method is a write, a lifecycle call, or a read.
    assert not (WRITE_SEAMS & READ_SEAMS)
    assert not (WRITE_SEAMS & FILE_LIFECYCLE_SEAMS)
    assert not (READ_SEAMS & FILE_LIFECYCLE_SEAMS)


def test_ac2_the_docx_classification_is_its_own_table_and_every_row_halts():
    """The vocabulary is shared; what this surface classifies into it is not. Every docx row
    is SYSTEMIC, because continuing would issue writes the engine did not issue before the
    boundary existed — the argument is in the module's own docstring."""
    for exc in (LarkRateLimitError("x", code="99991400"),
                LarkPermissionError("x", code="99991672"),
                LarkPaginationError("x"),
                LarkAPIError("x", code="1770002"),
                LarkAPIError("x"),
                RuntimeError("x")):
        assert classify_apply_exception(exc, wrote=False).scope == SYSTEMIC, exc
        assert classify_apply_exception(exc, wrote=False).halts
    # `wrote` is checked FIRST and overrides the exception's own class.
    landed = classify_apply_exception(LarkAPIError("x", code="1770002"), wrote=True)
    assert landed.reason is RefusalReason.UNVERIFIED_WRITE
    assert landed.landed == "yes"
    # ENTRY_SCOPED is imported as the shared vocabulary and used by NO row today.
    assert ENTRY_SCOPED not in {
        d.scope for d in vars(docx_disposition).values()
        if getattr(d, "scope", None) is not None}


def test_ac2_the_classification_is_total():
    """No exception a caller can provoke lacks a disposition."""
    class Exotic(Exception):
        pass

    assert classify_apply_exception(Exotic(), wrote=False).reason is \
        RefusalReason.UNEXPECTED_ERROR


@pytest.mark.parametrize("wrote", [False, True])
def test_ac2_every_disposition_produces_a_nonempty_actionable_detail(wrote):
    for exc in (LarkRateLimitError("x", code="99991400"),
                LarkPermissionError("x", code="99991672"),
                LarkPaginationError("x"),
                LarkAPIError("x", code="1770002"),
                LarkAPIError("x"),
                RuntimeError("x")):
        d = classify_apply_exception(exc, wrote=wrote)
        refusal = docx_disposition.disposition_refusal(
            d, exc, where="edit on 'p1'", wrote_seams=("_patch_block",))
        assert refusal.detail.strip()
        assert refusal.reason is d.reason


# =========================================================================== #
# AC3 — the raise/return policy, re-derived rather than assumed.                #
# =========================================================================== #

def test_ac3_apply_still_raises_typeerror_for_a_non_plan():
    with pytest.raises(TypeError):
        docx_apply({"not": "a plan"}, object(), "doc-1")


def test_ac3_the_cas_rate_limit_reraise_is_UNCHANGED_and_is_outside_the_boundary():
    """The one deliberate escape that survives: the whole-document compare-and-swap re-raises
    a rate-limit error rather than calling throttling drift. It runs BEFORE the entry loop, so
    it is not behind the boundary — and this is why the docx surface still states a position
    on the house apply-log invariant instead of declaring it."""
    tree = _page(_para("p1", "alpha"))
    plan = docx_dry_run([_req("alpha")], tree, document_revision_id=7)

    class Throttled:
        def read_document_revision(self, document_id):
            raise LarkRateLimitError("slow down", code="99991400")

    with pytest.raises(LarkRateLimitError):
        docx_apply(plan, Throttled(), "doc-1")


def test_ac3_gate_refusals_is_still_the_single_seam_and_its_signature_is_unmoved():
    sig = inspect.signature(docx_apply)
    assert list(sig.parameters) == ["plan", "client", "document_id", "allow_partial"]
    assert sig.parameters["allow_partial"].default is False
    source = (_SRC / "write" / "apply.py").read_text(encoding="utf-8")
    assert source.count("return gate_refusals(") == 2      # the CAS arm and the batch arm


def test_ac3_the_caller_that_already_handles_the_refusal_error_still_behaves():
    """``roundtrip.push`` catches ``LarkApplyRefusedError`` and re-raises it with its own
    recovery recipe; it never caught ``LarkAPIError``. So the class change moves a mid-batch
    API failure INTO the arm that already exists, rather than past it."""
    roundtrip = (_SRC / "roundtrip.py").read_text(encoding="utf-8")
    assert "except LarkApplyRefusedError as refused:" in roundtrip
    assert "except LarkAPIError" not in roundtrip


# =========================================================================== #
# AC5 — the walk is bounded, and both shapes are driven.                       #
# =========================================================================== #

class PaginatingOpener:
    """A ``urlopen`` double for ``list_document_blocks`` alone, scripted per page."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = 0

    def __call__(self, req, timeout=30):
        from write_harness import _FakeHTTPResponse
        page = self.pages[min(self.calls, len(self.pages) - 1)]
        self.calls += 1
        return _FakeHTTPResponse({"code": 0, "data": page})


def _page_body(n, *, has_more, token):
    return {"items": [{"block_id": f"b{n}", "block_type": 2}],
            "has_more": has_more, "page_token": token}


def test_ac5_a_repeated_page_token_terminates_with_a_typed_refusal():
    """The bug's own reproduction: ``has_more: true`` with the cursor just used. Before this
    change the loop never terminated and ``blocks`` grew without bound."""
    opener = PaginatingOpener([_page_body(1, has_more=True, token="T"),
                               _page_body(2, has_more=True, token="T")])
    client = _client(opener)
    with pytest.raises(LarkPaginationError) as caught:
        client.list_document_blocks("doc-1")
    assert "already used" in str(caught.value)
    assert "INCOMPLETE" in str(caught.value)
    assert caught.value.pages == 2 and caught.value.items == 2
    assert opener.calls == 2         # it STOPPED — it did not run forever


def test_ac5_has_more_with_no_cursor_at_all_terminates_the_same_way():
    opener = PaginatingOpener([_page_body(1, has_more=True, token="")])
    with pytest.raises(LarkPaginationError) as caught:
        _client(opener).list_document_blocks("doc-1")
    assert "no page_token at all" in str(caught.value)


def test_ac5_an_endless_chain_of_FRESH_cursors_stops_at_the_page_cap():
    """The shape no cursor-equality check can catch, so the cap is what stops it."""
    class Endless(PaginatingOpener):
        def __call__(self, req, timeout=30):
            from write_harness import _FakeHTTPResponse
            self.calls += 1
            return _FakeHTTPResponse({"code": 0, "data": _page_body(
                self.calls, has_more=True, token=f"T{self.calls}")})

    opener = Endless([])
    with pytest.raises(LarkPaginationError) as caught:
        _client(opener, max_writes_per_sec=100000).list_document_blocks("doc-1")
    assert opener.calls == MAX_BLOCK_LIST_PAGES
    assert caught.value.pages == MAX_BLOCK_LIST_PAGES
    assert "backstop" in str(caught.value)


def test_ac5_an_ordinary_multi_page_walk_is_UNCHANGED():
    """The guard costs a healthy walk nothing — the regression fence around the fix."""
    opener = PaginatingOpener([_page_body(1, has_more=True, token="T1"),
                               _page_body(2, has_more=True, token="T2"),
                               _page_body(3, has_more=False, token="")])
    blocks = _client(opener).list_document_blocks("doc-1")
    assert [b["block_id"] for b in blocks] == ["b1", "b2", "b3"]
    assert opener.calls == 3


def test_ac5_the_cap_is_the_sibling_precedent_and_says_so():
    """AC5 asks what the cap is and WHY that number. It is 200 because
    ``base/client.py`` and ``comments/client.py`` each cap a cursor walk at 200,
    independently — one answer to "how long may a walk run" instead of three."""
    from larkdocio.base.client import MAX_PAGES as BASE_MAX_PAGES
    from larkdocio.comments.client import MAX_PAGES as COMMENTS_MAX_PAGES

    assert MAX_BLOCK_LIST_PAGES == BASE_MAX_PAGES == COMMENTS_MAX_PAGES == 200
    source = (_SRC / "write" / "client.py").read_text(encoding="utf-8")
    assert "SIBLING PRECEDENT" in source
    # And the cap is unreachable by an ordinary document at this page size.
    assert MAX_BLOCK_LIST_PAGES * BLOCK_LIST_PAGE_SIZE == 100_000


def test_ac5_the_pagination_refusal_becomes_a_TYPED_LOG_ENTRY_inside_apply():
    """Where the two arms meet: the walk refuses, and the boundary turns that refusal into an
    apply-log entry rather than letting it escape."""
    from larkdocio.write.disposition import classify_apply_exception as classify

    d = classify(LarkPaginationError("x", pages=2, items=17), wrote=False)
    assert d.reason is RefusalReason.PAGINATION_UNTERMINATED
    assert d.outcome == "failed" and d.landed == "indeterminate"
    entry = ApplyLogEntry.failed(
        anchor=next(iter(docx_dry_run([_req("a")], _page(_para("p", "a"))).entries)).anchor,
        refusal=docx_disposition.disposition_refusal(d, LarkPaginationError("x"),
                                                     where="insert on 'p'"))
    assert entry.outcome == "failed"
    assert "may be SHORT" in entry.refusal.detail


# =========================================================================== #
# AC6 — the docstring stops citing the wrong sibling.                          #
# =========================================================================== #

def test_ac6_the_walk_no_longer_names_the_readers_unguarded_walk_as_its_model():
    source = (_SRC / "write" / "client.py").read_text(encoding="utf-8")
    walk = source.split("def list_document_blocks", 1)[1].split("def batch_delete", 1)[0]
    assert "exactly the way the reader walks the same endpoint" not in walk, (
        "the docstring still points at the unguarded model")
    # It names the GUARDED siblings instead, and says what it does differently.
    assert "comments/client.py" in walk and "base/client.py" in walk
    assert "MAX_BLOCK_LIST_PAGES" in walk


# =========================================================================== #
# AC7 — the reader's two walks are REPORTED, not swept.                        #
# =========================================================================== #

def test_the_readers_two_walks_are_reported_not_fixed():
    """``read/client.py`` has exactly TWO bare ``while True:`` cursor walks and they are
    **out of scope here**: the reader is the determinism-guaranteed path and a
    pacing/termination change there needs its own decision.

    Asserted rather than written down, so the report cannot go stale in silence: if somebody
    fixes them, this test reddens and the note gets deleted with the defect. If somebody adds
    a THIRD, it reddens too.
    """
    reader = (_SRC / "read" / "client.py").read_text(encoding="utf-8")
    lines = reader.splitlines()
    walks = [n for n, line in enumerate(lines, 1) if line.strip() == "while True:"]
    assert len(walks) == 2, walks
    for n in walks:
        window = "\n".join(lines[n - 1:n + 20])
        assert "has_more" in window and "page_token" in window
        assert "MAX_PAGES" not in window and "seen" not in window
    # The write engine's own walk is no longer one of them.
    writer = (_SRC / "write" / "client.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*while True:\s*$", writer, flags=re.M)


# =========================================================================== #
# The re-raise that NAMES THE BLOCK must not lose the error it re-raises.      #
# =========================================================================== #
#
# `apply.py::_naming_the_block` appends "[while writing block index N (kind: …)]" to any
# `LarkAPIError` raised by a create/grow call, so a consumer's bisect over 200 blocks becomes
# one line. It used to rebuild the error as a bare `LarkAPIError(message)`, which kept `str()`
# right and silently dropped `code`, `msg` and the SUBCLASS. Nothing noticed while the only
# reader was a human reading a traceback. The disposition boundary reads exactly those
# attributes: `code` tells "Lark answered about this entry" from "the call never reached Lark",
# and the class is what tells a scope denial and a rate limit apart from an ordinary rejection.
#
# So the re-raise now preserves class and attributes, and these are its OWN tests — before
# them the fix was pinned only indirectly, by one outcome string in another suite, and deleting
# the `LarkPermissionError` branch lost `denial` with nothing red.

def _named(exc):
    """Run ``exc`` through the block-naming re-raise and return what came back out."""
    from larkdocio.write.apply import _naming_the_block
    from larkdocio.write.encode import encode_content
    from larkdocio.write.model import NewBlock

    encoded = encode_content((NewBlock.table([["a"]]),))
    with pytest.raises(LarkAPIError) as caught:
        with _naming_the_block(encoded, (0,)):
            raise exc
    return caught.value


def _denial():
    from larkdocio.permissions import PermissionDenial

    return PermissionDenial(
        scopes=("docx:document",), code="99991672", msg="no permission",
        console_url="https://open.larksuite.com/app/cli_x/auth",
        credential_env=("LARKDOCIO_WRITE_APP_ID",))


def test_the_block_naming_reraise_preserves_a_SCOPE_DENIAL_whole():
    """The one this suite exists for: class, code, msg and — the field a bare rebuild lost
    without a sound — ``denial``, which is the only place Lark's own missing-scope answer,
    console link and credential pair survive."""
    denial = _denial()
    original = LarkPermissionError("create children failed: Code: 99991672, Msg: no permission",
                                   code="99991672", msg="no permission", denial=denial)
    out = _named(original)

    assert type(out) is LarkPermissionError, "a scope denial came back as a plain API error"
    assert out.code == "99991672" and out.msg == "no permission"
    assert out.denial is denial, "the denial record was dropped by the re-raise"
    # The message is the original's, verbatim, plus this library's own location — the
    # errors-module doctrine: this family adds attributes, it does not edit text.
    assert str(out).startswith(str(original))
    assert "block index 0 (kind: table)" in str(out)
    assert out.__cause__ is original


def test_the_preserved_denial_survives_all_the_way_INTO_the_apply_log_detail():
    """End to end, because preserving the attribute is only worth what the log does with it:
    the boundary classifies on the CLASS, and the detail relays Lark's own denial paragraph."""
    from larkdocio.write.disposition import disposition_refusal

    out = _named(LarkPermissionError("nope", code="99991672", msg="no permission",
                                     denial=_denial()))
    d = classify_apply_exception(out, wrote=False)
    assert d.reason is RefusalReason.PERMISSION_DENIED, (
        "a lost subclass would have classified this as a generic api-error")
    detail = disposition_refusal(d, out, where="insert on 'p1'").detail
    assert "docx:document" in detail, "Lark's own missing scope is not relayed"
    assert "https://open.larksuite.com/app/cli_x/auth" in detail


def test_the_block_naming_reraise_preserves_a_denial_carried_by_a_SURFACES_OWN_CLASS():
    """The GENERIC arm, which the denial-preserving arm above never covered.

    The arm above matches on ``LarkPermissionError``. A denial can now also arrive on a
    surface's own typed class — ``err.denial`` is on the base — and the generic re-raise
    rebuilt the error from ``code``/``msg`` alone, so the record was dropped exactly as it once
    was for the class.

    **Latent today**, and asserted anyway: nothing this walk can raise is a denial-carrying
    error of another class, because the docx write client refuses through the shared factory,
    which returns ``LarkPermissionError``. It is fixed so it cannot become live the next time
    a surface with its own family is reached from a composed write — the same reasoning that
    made the class-preserving fix worth making before anyone had lost a class in the field.
    """
    from larkdocio.base.media import MediaUploadError

    denial = _denial()
    original = MediaUploadError("the upload was refused: Code: 99991672, Msg: no permission",
                                code="99991672", msg="no permission", denial=denial)
    out = _named(original)

    assert type(out) is MediaUploadError, "the surface's own class must survive the re-raise"
    assert out.code == "99991672" and out.msg == "no permission"
    assert out.denial is denial, (
        "the denial record was dropped by the GENERIC arm of the re-raise — the promise "
        "`err.denial is not None` is false for anything that passes through it")
    assert str(out).startswith(str(original))
    assert "block index 0 (kind: table)" in str(out)
    assert out.__cause__ is original


def test_the_generic_reraise_cannot_TypeError_on_a_class_that_takes_no_denial_keyword():
    """Why the generic arm ASSIGNS the attribute instead of passing it to the constructor.

    ``type(refusal)(...)`` is whatever class arrived, and shipped subclasses exist whose
    ``__init__`` accepts neither a ``denial`` keyword nor needs one. Forwarding it as an
    argument would turn a re-raise into a ``TypeError`` **inside an except block** — a worse
    failure than the one being fixed, and one no caller could act on.
    """
    from larkdocio.drive.errors import DriveObjectNotFoundError
    import inspect

    assert "denial" not in inspect.signature(DriveObjectNotFoundError.__init__).parameters, (
        "this test's premise moved: pick another class that takes no `denial` keyword")
    out = _named(DriveObjectNotFoundError("no such object", code="1061003", msg="not found",
                                          token="fldcnX"))
    assert type(out) is DriveObjectNotFoundError
    assert out.denial is None and out.code == "1061003"


def test_the_block_naming_reraise_preserves_a_RATE_LIMIT_as_a_rate_limit():
    out = _named(LarkRateLimitError("slow down", code="99991400", msg="too many"))
    assert type(out) is LarkRateLimitError
    assert classify_apply_exception(out, wrote=False).reason is RefusalReason.RATE_LIMITED


def test_the_block_naming_reraise_preserves_the_CODE_so_an_answer_is_not_called_a_transport_failure():
    """The defect this fix closes, stated as its own case: a coded rejection whose ``code`` was
    dropped classifies as ``transport-failure`` — "the call never reached Lark" — about a call
    Lark answered, and INDETERMINATE about a write that plainly did not land."""
    out = _named(LarkAPIError("create children failed: Code: 1770001, Msg: invalid param",
                              code="1770001", msg="invalid param"))
    assert out.code == "1770001" and out.msg == "invalid param"
    d = classify_apply_exception(out, wrote=False)
    assert d.reason is RefusalReason.API_ERROR
    assert d.reason is not RefusalReason.TRANSPORT_FAILURE
    assert d.landed == "no", "a Lark answer about a call that did not land is not indeterminate"


# =========================================================================== #
# The no-exception path — DISCLOSED, and pinned so the disclosure stays true.  #
# =========================================================================== #

def test_a_post_write_failure_on_the_LAST_entry_RETURNS_rather_than_raising():
    """``applied-unverified`` LANDED, so it is not one of the entries ``gate_refusals`` raises
    on; on the last plan entry there is nothing after it to log ``not-attempted`` either, so
    the log holds no non-landing entry and ``apply()`` returns normally.

    That is house-consistent with the sibling engines and it is deliberate — but it means a
    caller who reads only the return/raise signal sees a clean run over a table with empty
    cells. It is DISCLOSED in the release notes rather than changed, and this test is what
    keeps the disclosure honest: if the behaviour ever changes, the words have to.
    """
    plan, client, _opener = _three_entry_batch(fail_on_write=0)

    import larkdocio.write.ops as ops
    real = ops.apply_dispatch

    def write_then_explode(entry, client_, document_id):
        client_._patch_block(document_id, "p1", {"update_text_elements": {"elements": []}})
        raise RuntimeError("the step after the write failed")

    ops.apply_dispatch = write_then_explode
    try:
        # ONE entry, and the default allow_partial=False — no opt-in anywhere.
        one = docx_dry_run([_req("alpha", replacement="x")],
                           _page(_para("p1", "alpha")))
        log = docx_apply(one, client, "doc-1")
    finally:
        ops.apply_dispatch = real

    assert [e.outcome for e in log.entries] == ["applied-unverified"]
    assert log.refusals == (), "nothing for gate_refusals to raise on — this is the path"

    # The two checks the release notes tell a caller to use instead, both true here.
    assert log.halt is not None
    assert [e for e in log if e.outcome == "applied-unverified"]
