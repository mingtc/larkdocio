"""The reply projection — all three element kinds, and the raw-id rule for mentions.

A comment's words live in its replies, and each reply's content is a list of elements of
three kinds: a run of text, a mention of a person, and a link to a document. All three are
projected here; a mention projects to its **raw id**, because no name is obtainable for it
and a guessed name would be a fabricated attribution.

Provenance: the single-element and mention arms are verbatim probe captures; the
``docs_link``, multi-reply and truncated-thread arms are composed on captured envelopes and
labelled as such in ``tests/comments_payloads.py``.
"""
import comments_payloads as payloads
from lark_oapi.api.drive.v1 import FileComment, FileCommentReply

from larkdocio.comments import (
    KIND_DOCS_LINK,
    KIND_PERSON,
    KIND_TEXT,
    KIND_UNKNOWN_PREFIX,
    Comment,
    CommentReply,
)


def _reply(data: dict) -> CommentReply:
    return CommentReply.from_sdk(FileCommentReply(data))


def _comment(data: dict) -> Comment:
    return Comment.from_file_comment(FileComment(data))


# --------------------------------------------------------------------------- #
# One arm per element kind.                                                     #
# --------------------------------------------------------------------------- #

def test_a_text_run_element_projects_to_its_text():
    reply = _reply(payloads.CREATE_WHOLE_DOC["data"]["reply_list"]["replies"][0])
    assert [e.kind for e in reply.elements] == [KIND_TEXT]
    assert reply.text == (
        "LD-156 hazard-drill comment ALPHA-9f15285c — disposable only.")
    assert reply.elements[0].user_id is None and reply.elements[0].url is None


def test_a_person_element_projects_to_the_RAW_id_and_never_a_name():
    """The captured mention: the payload carries a bare ``user_id`` and nothing else."""
    reply = _reply(
        payloads.CREATE_WITH_PERSON_MENTION["data"]["reply_list"]["replies"][0])

    assert [e.kind for e in reply.elements] == [KIND_TEXT, KIND_PERSON]
    mention = reply.elements[1]
    assert mention.user_id == "ou_examplebot0000000000000000000001"
    assert mention.text == "@ou_examplebot0000000000000000000001"
    assert reply.text == "mention arm: @ou_examplebot0000000000000000000001"
    assert reply.mentioned_user_ids == ("ou_examplebot0000000000000000000001",)


def test_a_docs_link_element_projects_to_its_url():
    reply = _reply(payloads.REPLY_WITH_ALL_THREE_ELEMENT_KINDS)
    link = [e for e in reply.elements if e.kind == KIND_DOCS_LINK]
    assert len(link) == 1
    assert link[0].url == "https://example.larksuite.com/docx/AbCdEf123456"
    assert link[0].text == "https://example.larksuite.com/docx/AbCdEf123456"
    assert link[0].user_id is None


# --------------------------------------------------------------------------- #
# The amplifier's arm: EVERY kind in ONE reply, mentioning an unresolvable id.   #
# --------------------------------------------------------------------------- #

def test_one_reply_carrying_every_element_kind_projects_all_of_them_in_order():
    reply = _reply(payloads.REPLY_WITH_ALL_THREE_ELEMENT_KINDS)

    assert [e.kind for e in reply.elements] == [
        KIND_TEXT, KIND_DOCS_LINK, KIND_TEXT, KIND_PERSON]
    assert reply.text == (
        "see https://example.larksuite.com/docx/AbCdEf123456 and "
        "@ou_examplebot0000000000000000000001")
    # The mentioned id is one the identity endpoint refuses on this library's scopes; it is
    # surfaced anyway, raw, because that is the only true thing to say about it.
    assert reply.mentioned_user_ids == ("ou_examplebot0000000000000000000001",)


def test_a_multi_reply_thread_projects_every_reply_in_order():
    comment = _comment(payloads.MULTI_REPLY_THREAD)

    assert [r.reply_id for r in comment.replies] == ["reply-1", "reply-2", "reply-3"]
    assert comment.text == (
        "Is this figure final?\n"
        "Not yet — audit pending.\n"
        "thanks @ou_examplebot0000000000000000000001")
    # Two different authors, both raw.
    assert [r.user_id for r in comment.replies] == [
        "ou_examplebot0000000000000000000001",
        "ou_second_reviewer_0000000000000000",
        "ou_second_reviewer_0000000000000000",
    ]
    assert comment.mentioned_user_ids == ("ou_examplebot0000000000000000000001",)


def test_a_thread_mentioning_the_same_id_twice_reports_it_once_at_comment_level():
    data = {
        **payloads.MULTI_REPLY_THREAD,
        "reply_list": {"replies": [
            payloads.REPLY_WITH_ALL_THREE_ELEMENT_KINDS,
            payloads.CREATE_WITH_PERSON_MENTION["data"]["reply_list"]["replies"][0],
        ]},
    }
    comment = _comment(data)
    assert comment.mentioned_user_ids == ("ou_examplebot0000000000000000000001",)
    # ...while each reply still reports its own, un-merged.
    assert all(r.mentioned_user_ids for r in comment.replies)


# --------------------------------------------------------------------------- #
# Absent / empty / unmodelled — the shapes that must not raise or invent.        #
# --------------------------------------------------------------------------- #

def test_a_reply_with_no_content_projects_to_no_elements_and_empty_text():
    reply = _reply(payloads.REPLY_WITHOUT_CONTENT)
    assert reply.elements == ()
    assert reply.text == ""
    assert reply.mentioned_user_ids == ()
    assert reply.reply_id == "reply-empty"


def test_a_comment_with_no_reply_list_projects_to_an_empty_thread():
    comment = _comment(payloads.COMMENT_WITHOUT_REPLY_LIST)
    assert comment.replies == ()
    assert comment.text == ""
    # The solver fields are the point of this payload: a resolved comment reports WHO and
    # never WHEN — `solved_time` is absent from every endpoint's body, so it reads None.
    assert comment.is_solved is True
    assert comment.solved_time is None
    assert comment.solver_user_id == "ou_examplebot0000000000000000000001"


def test_an_element_kind_we_do_not_model_is_LABELLED_not_silently_dropped():
    """Forward compatibility without invention: the element survives as itself, carrying the
    server's own type label and contributing no text it does not have."""
    reply = _reply(payloads.REPLY_WITH_UNMODELLED_ELEMENT)

    assert len(reply.elements) == 2, "the unmodelled element was dropped"
    assert reply.elements[0].kind == KIND_UNKNOWN_PREFIX + "sticker"
    assert reply.elements[0].text == ""
    assert reply.text == "tail"


def test_an_empty_elements_list_projects_to_empty_text():
    reply = _reply({**payloads.REPLY_WITHOUT_CONTENT, "content": {"elements": []}})
    assert reply.elements == ()
    assert reply.text == ""
