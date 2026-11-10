"""THE COMMENTS-READ GATE — the shipped read, proved against real Lark, on files it creates.

``@pytest.mark.live_write``, deselected by default. Run it explicitly::

    pytest -m live_write

**Why a write marker on a read gate.** The surface under test reads. Proving it needs a comment
to exist, and the only comment this API will create is a whole-file one — a write. So the gate
rides the write credentials and, more importantly, the write ring's discipline: it comments only
on a file **it created itself**, and it destroys both.

**Its comment writes are the SHIPPED ones.** They used to be hand-rolled scaffolding in the test
tree, because comment creation was not a capability. It is one now
(:class:`~larkdocio.write.model.CreateCommentRequest` and its removal sibling), so this gate
calls :class:`~larkdocio.write.client.WriteClient`'s own comment methods and the duplicate is
gone — one implementation, and the shipped one is the exercised one. It calls the **client**
rather than the plan-gated op deliberately: the create is this gate's *fixture*, and the removal
runs in a ``finally`` where a plan-time refusal would leave an orphan, which is the one outcome
the disposables doctrine will not accept. The plan-gated ops are proved as ops by
``tests/test_live_write_comment_op_gate.py``.

**The sequence, per disposable.**

1. create a disposable document (the write app owns what it creates, so the same credentials
   read it back);
2. put one whole-file comment on it — and keep the create response, because it is half of the
   asymmetry arm;
3. read the comment back **through the shipped surface** and assert the projection matches what
   was written: the thread text exactly, the author as a raw id, and no name anywhere;
4. assert the **shape asymmetry live** — the create response did not report the comment's scope
   at all, while the listing endpoint reports it as whole-file, for the same comment, through
   the same model;
5. remove the comment by deleting its only reply (the cascade), then confirm from the listing
   that it is gone;
6. trash the document.

Steps 5 and 6 run in a ``finally``, so a failure anywhere above still leaves nothing behind.
Every disposable and every comment is recorded with its removal confirmed, and the close-out
asserts **zero orphans**.

**It runs twice, on two fresh disposables.** A single clean close-out can be luck; the same
close-out twice, on files created seconds apart, is the procedure working.
"""
import time

import canary_support
import pytest
from lark_oapi.api.drive.v1 import FileComment

from larkdocio.comments import (
    SCOPE_UNREPORTED,
    SCOPE_WHOLE_DOCUMENT,
    Comment,
    CommentsReadClient,
    comments,
)
from larkdocio.common import get_write_credentials
from larkdocio.write.client import WriteClient, text_block

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

# The write app's tenant region — matches the toolkit's default OpenAPI domain. NOT a
# document reference: this gate never addresses a file it did not create.
DOMAIN = "larksuite.com"

#: A distinctive marker so the read-back assertion is exact and could not match anything else.
COMMENT_TEXT_PREFIX = "larkdocio comments-read gate :: OMEGA-"


def _remove_via_reply_cascade(wc, doc_id, comment_id):
    """Teardown: delete every reply on the comment; the comment goes with the last one.

    Two shipped client calls and no third implementation of either — the whole of what this
    used to be as scaffolding. Deliberately the *client* rather than the plan-gated removal
    op: this runs in a ``finally``, and the op's ownership pre-check would (correctly) refuse
    rather than delete if anything about the thread surprised it, which in a teardown means an
    orphan. The op is proved as an op by ``tests/test_live_write_comment_op_gate.py``.

    Returns the response code per deleted reply, so the caller records the removal rather than
    assuming it.
    """
    codes = []
    for reply in wc.list_comment_replies(doc_id, comment_id):
        reply_id = reply.get("reply_id")
        if not reply_id:
            continue
        resp = wc.delete_comment_reply(doc_id, comment_id, reply_id)
        codes.append(resp.get("code"))
    return codes


def _close_out(ledger):
    """Assert every disposable and every comment this gate made is confirmed gone."""
    orphans = [row for row in ledger if not row["confirmed_gone"]]
    assert not orphans, f"the gate left orphans behind: {orphans}"
    assert ledger, "the close-out ran with an empty ledger — nothing was recorded"


def _one_round(nonce, ledger, capsys):
    """One full create → comment → read → remove → delete cycle on a fresh disposable."""
    app_id, app_secret = get_write_credentials()
    wc = WriteClient(app_id, app_secret, DOMAIN)
    reader = CommentsReadClient(app_id, app_secret, DOMAIN)

    text = f"{COMMENT_TEXT_PREFIX}{nonce}"
    dest_folder = canary_support.require_disposables_folder()
    doc = wc.create_document(title=f"larkdocio-comments-read-gate {nonce}",
                             folder_token=dest_folder)
    doc_id = doc["document_id"]
    row = {"file_token": doc_id, "comment_id": None, "reply_delete_codes": [],
           "comment_absent_from_list": None, "file_deleted_code": None,
           "confirmed_gone": False}
    ledger.append(row)

    comment_id = None
    try:
        # A little body so the document is a real one, not an empty shell.
        wc.create_children(doc_id, doc_id, [text_block("gate body paragraph")], index=0)

        # (2) The one create the API accepts — through the SHIPPED client, and the
        #     asymmetry arm's first half.
        created = wc.create_whole_document_comment(doc_id, text)
        comment_id = created["comment_id"]
        row["comment_id"] = comment_id
        assert "is_whole" not in created, (
            "the create response reported a scope — the asymmetry this surface handles has "
            "changed shape and the model's tri-state needs re-deriving")

        # (3) Read it back THROUGH THE SHIPPED SURFACE.
        result = comments(doc_id, client=reader)
        assert result.available is True, result.unavailable_reason
        mine = [c for c in result.comments if c.comment_id == comment_id]
        assert len(mine) == 1, (
            f"the shipped read did not return the comment it was given: {result.disclosure}")
        got = mine[0]

        assert got.text == text, f"projected thread text {got.text!r} != written {text!r}"
        assert got.user_id and got.user_id.startswith("ou_"), (
            f"author must be a raw open id, got {got.user_id!r}")
        assert text not in (got.quote or ""), "a whole-file comment quotes no passage"
        assert got.is_solved is False
        assert len(got.replies) == 1
        assert got.replies[0].user_id == got.user_id

        # No name was fetched for the author, and the surface has nothing to put one in.
        assert "author_name" not in got.to_dict()
        assert "display_name" not in got.to_dict()

        # (4) THE ASYMMETRY, LIVE — both endpoint shapes, one model, opposite answers.
        from_create = Comment.from_file_comment(FileComment(created))
        assert from_create.comment_id == got.comment_id, "not the same comment"
        assert from_create.is_whole is None
        assert from_create.scope == SCOPE_UNREPORTED
        assert got.is_whole is True
        assert got.scope == SCOPE_WHOLE_DOCUMENT

        # And the join direction, on a real tree: this comment is whole-file, so the document's
        # blocks carry no anchors for it — asking about a document with no anchors costs
        # nothing, live as offline.
        from larkdocio.read.client import Client as ReadClient
        from larkdocio.read.config import new_config
        from larkdocio.read.parser import Parser

        docx, blocks = ReadClient(app_id, app_secret, DOMAIN).get_docx_content(doc_id)
        root = Parser(new_config()).parse_docx_tree(docx.document_id, blocks)
        before = reader.api_calls
        joined = comments(doc_id, root=root, client=reader)
        assert joined.api_calls == 0 and reader.api_calls == before, (
            "a whole-file comment leaves no block anchors, so the join must make no call")
        assert joined.comments == ()

        print(f"[comments-read gate {nonce}] comment_id={comment_id} "
              f"scope_from_list={got.scope} scope_from_create={from_create.scope} "
              f"author={got.user_id} api_calls={result.api_calls}")
    finally:
        # (5) Remove the comment via the reply cascade, then confirm from the listing.
        if comment_id:
            try:
                row["reply_delete_codes"] = _remove_via_reply_cascade(
                    wc, doc_id, comment_id)
            except Exception as exc:            # pragma: no cover - teardown must not mask
                row["reply_delete_codes"] = [f"error: {exc}"]
            try:
                after = comments(doc_id, client=CommentsReadClient(
                    app_id, app_secret, DOMAIN))
                row["comment_absent_from_list"] = (
                    after.available and comment_id not in after.by_id)
            except Exception as exc:            # pragma: no cover
                row["comment_absent_from_list"] = f"error: {exc}"

        # (6) Trash the disposable.
        try:
            resp = wc.delete_document(doc_id)
            row["file_deleted_code"] = resp.get("code")
        except Exception as exc:                # pragma: no cover
            row["file_deleted_code"] = f"error: {exc}"

        row["confirmed_gone"] = (
            row["file_deleted_code"] == 0
            and (comment_id is None or row["comment_absent_from_list"] is True)
        )
        with capsys.disabled():
            print(f"[comments-read gate close-out] {row}")

    assert row["comment_absent_from_list"] is True, (
        "the comment survived the reply cascade — removal is not confirmed")
    assert all(code == 0 for code in row["reply_delete_codes"]), row["reply_delete_codes"]
    return row


def test_the_comments_read_round_trips_on_its_own_disposables_twice(capsys):
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)

    ledger = []
    try:
        for i in range(2):
            _one_round(f"{int(time.time())}-{i}", ledger, capsys)
            time.sleep(1.0)   # gentle: two rounds, a second apart, nothing hammered
    finally:
        with capsys.disabled():
            print(f"[comments-read gate] ledger: {ledger}")

    assert len(ledger) == 2, "the gate must prove its close-out on TWO fresh disposables"
    assert len({row["file_token"] for row in ledger}) == 2, "the two rounds shared a file"
    _close_out(ledger)
