"""THE COMMENT-OP GATE — the two shipped comment ops, proved against real Lark.

``@pytest.mark.live_write``, deselected by default. Run it explicitly::

    pytest -m live_write

**What only a live run can establish.** Offline tests pin the request bytes against committed
captures; they cannot tell you what Lark *made*. Two things here are live-only:

1. **The created comment really is whole-document.** The create response does not report the
   scope at all, so ``code 0`` says nothing about what exists. This gate reads the comment back
   through the shipped comments reader and requires ``is_whole is True`` and ``quote is None``
   from the listing endpoint — the assertion the whole feature rests on, made against the
   server's own answer rather than inferred from a success code.
2. **The removal really removed it.** The cascade deletes replies; whether the comment went with
   the last one is a fact about the listing afterwards. So removal is confirmed by **re-reading**
   and finding the comment absent — never by trusting a return code (the same discipline the
   file teardown uses: verify by re-fetch).

**Two arms write nothing at all, and that is structural.** The anchored-create refusal and the
spreadsheet refusal are decided at plan time, so ``apply`` is handed a client whose transport
**raises on contact**. A refusal that failed to fire therefore errors instead of quietly writing
— zero-API-calls is proved by construction rather than by counting.

**Disposables only.** Every round creates its own document and trashes it in a ``finally``,
then verifies the deletion by re-fetch. It names no pre-existing document, no canary, no zoo, no
scratch surface, and it touches no spreadsheet — the sheets refusal arm never sends anything.

**It runs twice, on two fresh disposables**, so a clean close-out is the procedure working
rather than luck.
"""
import time

import canary_support
import pytest

from log_reading_apply import reading_the_log
from larkdocio.comments import CommentsReadClient, comments
from larkdocio.common import get_write_credentials
from larkdocio.errors import LarkAPIError
from larkdocio.write import apply, dry_run
from larkdocio.write.client import WriteClient, text_block
from larkdocio.write.model import (
    CreateCommentRequest,
    RefusalReason,
    RemoveCommentRequest,
)

# This gate's subject is the LOG — which entry landed, which refused, with which typed
# reason — not the return-vs-raise policy (pinned offline in
# tests/test_apply_refusal_policy.py, proved live in
# tests/test_live_write_refusal_policy_gate.py). So it opts into partial application
# once, here, the same way the offline log-reading suites do.
apply = reading_the_log(apply)

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

#: The write app's tenant region — matches the toolkit's default OpenAPI domain. NOT a document
#: reference: this gate never addresses a file it did not create.
DOMAIN = "larksuite.com"

#: A distinctive marker so the read-back assertion is exact and could not match anything else.
COMMENT_TEXT_PREFIX = "larkdocio comment-op gate :: SIGMA-"

#: The block id the anchored-refusal arm asks for. Deliberately **not** token-shaped — the
#: companion guard rejects any literal that could be a real document handle, and a gate has no
#: business carrying one. It is never sent anywhere (the refusal happens before any call), which
#: is exactly what the arm proves.
UNSENDABLE_BLOCK_ID = "not-a-real-block-id-refusal-arm-only"


class RaisesOnContact:
    """A transport that fails the moment anything tries to send.

    Wired into a ``WriteClient`` for the two refusal arms, so "this costs zero API calls" is a
    structural property of the run: if a refusal did not fire, the attempted call raises here and
    the test errors rather than writing to Lark.
    """

    def execute(self, call):
        raise AssertionError(
            "a refusal that should have been decided at plan time reached the transport")


def _refusing_client():
    return WriteClient("cli_never_used", "secret_never_used", DOMAIN,
                       transport=RaisesOnContact(),
                       token_fetcher=lambda *a, **k: pytest.fail(
                           "a plan-time refusal fetched a token"))


def _close_out(ledger):
    """Assert every disposable and every comment this gate made is confirmed gone."""
    orphans = [row for row in ledger if not row["confirmed_gone"]]
    assert not orphans, f"the gate left orphans behind: {orphans}"
    assert ledger, "the close-out ran with an empty ledger — nothing was recorded"


def _refusal_arms_touch_nothing():
    """The two plan-time refusals, against a client that cannot send. No document needed."""
    wc = _refusing_client()

    anchored = dry_run([CreateCommentRequest(
        text="this must never be created", anchor_block_id=UNSENDABLE_BLOCK_ID)], None)
    log = apply(anchored, wc, "no-document-is-touched")
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.COMMENT_ANCHOR_NOT_CREATABLE
    assert "code 0" in entry.refusal.detail

    sheets = dry_run([CreateCommentRequest(text="nor this", file_type="sheet")], None)
    log = apply(sheets, wc, "no-spreadsheet-is-touched")
    (entry,) = log.entries
    assert entry.outcome == "refused"
    assert entry.refusal.reason is RefusalReason.COMMENT_SURFACE_UNSUPPORTED
    assert "options: [doc,docx]" in entry.refusal.detail
    return {"anchored_refused": True, "sheets_refused": True}


def _one_round(nonce, ledger, capsys):
    """One full create → read-back → remove → confirm-gone → delete cycle on a disposable."""
    app_id, app_secret = get_write_credentials()
    wc = WriteClient(app_id, app_secret, DOMAIN)
    reader = CommentsReadClient(app_id, app_secret, DOMAIN)

    text = f"{COMMENT_TEXT_PREFIX}{nonce}"
    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-comment-op-gate {nonce}",
                             folder_token=dest_folder)
    doc_id = doc["document_id"]
    row = {"file_token": doc_id, "comment_id": None, "author_id": None,
           "is_whole_from_list": None, "quote_from_list": "unset",
           "removed_reply_ids": None, "comment_absent_after_removal": None,
           "file_deleted_code": None, "file_absent_after_delete": None,
           "confirmed_gone": False}
    ledger.append(row)

    comment_id = None
    try:
        wc.create_children(doc_id, doc_id, [text_block("gate body paragraph")], index=0)
        time.sleep(0.7)

        # (1) CREATE through the shipped plan-gated op.
        plan = dry_run([CreateCommentRequest(text=text)], None)
        (planned,) = plan.entries
        assert planned.is_resolved and planned.op == "comment-create"
        authorship = [n for n in planned.preview_notes
                      if n["kind"] == "comment-lands-as-the-app-bot"]
        assert authorship, "the plan did not disclose the bot authorship"

        log = apply(plan, wc, doc_id)
        (created,) = log.entries
        assert created.outcome == "commented", created.to_dict()
        comment_id = created.comment_record["comment_id"]
        author_id = created.comment_record["author_id"]
        row["comment_id"] = comment_id
        row["author_id"] = author_id
        assert comment_id and author_id and author_id.startswith("ou_")
        time.sleep(0.7)

        # (2) READ IT BACK — what was MADE, not what was returned. This is the assertion the
        #     whole feature rests on: the listing endpoint's own scope answer.
        result = comments(doc_id, client=reader)
        assert result.available is True, result.unavailable_reason
        mine = [c for c in result.comments if c.comment_id == comment_id]
        assert len(mine) == 1, f"the created comment is not in the listing: {result.disclosure}"
        got = mine[0]
        row["is_whole_from_list"] = got.is_whole
        row["quote_from_list"] = got.quote

        assert got.is_whole is True, (
            f"the comment is not whole-document: is_whole={got.is_whole!r}")
        assert got.quote is None, (
            f"a whole-document comment must quote no passage; got {got.quote!r}")
        assert got.text == text, f"projected text {got.text!r} != written {text!r}"
        assert got.user_id == author_id, (
            "the author the apply-log disclosed is not the author Lark recorded: "
            f"{author_id!r} vs {got.user_id!r}")
        time.sleep(0.7)

        # (3) REMOVE through the shipped op, using the author id the create handed back —
        #     the loop the disclosure exists for.
        plan = dry_run([RemoveCommentRequest(comment_id=comment_id, author_id=author_id)], None)
        log = apply(plan, wc, doc_id)
        (removed,) = log.entries
        assert removed.outcome == "comment-removed", removed.to_dict()
        row["removed_reply_ids"] = removed.comment_record["removed_reply_ids"]
        assert row["removed_reply_ids"], "the removal reported deleting no replies"
        comment_id_removed = comment_id
        time.sleep(0.7)

        # (4) CONFIRM GONE BY RE-READING — never by the return code.
        after = comments(doc_id, client=CommentsReadClient(app_id, app_secret, DOMAIN))
        assert after.available is True, after.unavailable_reason
        row["comment_absent_after_removal"] = comment_id_removed not in after.by_id
        assert row["comment_absent_after_removal"], (
            "the comment survived the cascade — removal is not confirmed")
        comment_id = None       # nothing left for the teardown to clean

        print(f"[comment-op gate {nonce}] comment_id={comment_id_removed} "
              f"author={author_id} is_whole={row['is_whole_from_list']} "
              f"quote={row['quote_from_list']!r} removed={row['removed_reply_ids']}")
    finally:
        # Teardown: anything the body left behind, then the document — verified by re-fetch.
        if comment_id:
            try:
                for reply in wc.list_comment_replies(doc_id, comment_id):
                    wc.delete_comment_reply(doc_id, comment_id, reply.get("reply_id"))
            except Exception as exc:            # pragma: no cover - teardown must not mask
                row["removed_reply_ids"] = f"teardown error: {exc}"
        try:
            resp = wc.delete_document(doc_id)
            row["file_deleted_code"] = resp.get("code")
        except Exception as exc:                # pragma: no cover
            row["file_deleted_code"] = f"error: {exc}"

        # ZERO ORPHANS, verified INDEPENDENTLY: re-fetch the document and require Lark to say
        # it is gone. A delete that returned 0 and left the file is exactly what this catches.
        try:
            wc.get_document(doc_id)
            row["file_absent_after_delete"] = False
        except LarkAPIError as exc:
            row["file_absent_after_delete"] = True
            row["delete_confirm_code"] = exc.code

        row["confirmed_gone"] = (
            row["file_absent_after_delete"] is True
            and row["comment_absent_after_removal"] is not False
        )
        with capsys.disabled():
            print(f"[comment-op gate close-out] {row}")

    assert row["file_absent_after_delete"] is True, (
        f"the disposable survived its delete — an orphan: {row}")
    return row


def test_the_comment_ops_round_trip_on_their_own_disposables_twice(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    refusals = _refusal_arms_touch_nothing()
    ledger = []
    try:
        for i in range(2):
            _one_round(f"{int(time.time())}-{i}", ledger, capsys)
            time.sleep(1.0)   # gentle: two rounds, a second apart, nothing hammered
    finally:
        with capsys.disabled():
            print(f"[comment-op gate] refusal arms: {refusals}")
            print(f"[comment-op gate] ledger: {ledger}")

    assert len(ledger) == 2, "the gate must prove its close-out on TWO fresh disposables"
    assert len({row["file_token"] for row in ledger}) == 2, "the two rounds shared a file"
    _close_out(ledger)
