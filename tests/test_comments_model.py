"""The typed comment model — and THE SHAPE ASYMMETRY it exists to survive.

``is_whole`` is **absent** from the create and ``GET``-one bodies and **present** on
``list`` / ``batch_query``, for the very same comment. A model that defaults it — the
``getattr(fc, "is_whole", False)`` reflex — reports a whole-document comment as anchored
to a passage, which is a lie about *where a reviewer objected*. So the absent case is a
third state here, and both captured shapes are pushed through the **same** projection so
a per-endpoint special case cannot hide.

Every payload comes from ``tests/comments_payloads.py`` (verbatim probe captures).
"""
import json

import comments_payloads as payloads
import pytest
from lark_oapi.api.drive.v1 import FileComment

from larkdocio.comments import (
    SCOPE_ANCHORED,
    SCOPE_UNREPORTED,
    SCOPE_WHOLE_DOCUMENT,
    Comment,
    CommentReply,
    ReplyElement,
)


def _sdk(data: dict) -> FileComment:
    """The captured comment body as the pinned SDK's own typed model.

    The SDK is the normalizer on purpose: ``init`` assigns only the keys the payload
    actually carries, so an absent ``is_whole`` stays ``None`` while a present ``false``
    becomes ``False`` — the distinction the whole file turns on, made by the SDK rather
    than by our parsing.
    """
    return FileComment(data)


# --------------------------------------------------------------------------- #
# AC4 — THE ASYMMETRY, both captured shapes through ONE code path.              #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("payload_name", ["CREATE_WHOLE_DOC", "GET_ONE_WHOLE_DOC"])
def test_is_whole_is_absent_on_create_and_get_one_and_stays_unreported(payload_name):
    """The endpoints that do not report it must not be made to look like they did."""
    body = getattr(payloads, payload_name)["data"]
    assert "is_whole" not in body, (
        "fixture drift: this capture is the ABSENT-is_whole shape by definition")

    comment = Comment.from_file_comment(_sdk(body))

    assert comment.is_whole is None
    assert comment.is_whole is not False, "absent was collapsed into false"
    assert comment.scope == SCOPE_UNREPORTED
    assert comment.anchor_scope_reported is False


@pytest.mark.parametrize("payload_name,path", [
    ("LIST_ONE_PAGE", ("data", "items", 0)),
    ("BATCH_QUERY_ONE", ("data", "items", 0)),
])
def test_is_whole_is_present_on_list_and_batch_query_and_maps_to_whole_document(
        payload_name, path):
    """The endpoints that DO report it are believed exactly."""
    body = getattr(payloads, payload_name)
    for step in path:
        body = body[step]
    assert body["is_whole"] is True, "fixture drift: this capture is the PRESENT shape"

    comment = Comment.from_file_comment(_sdk(body))

    assert comment.is_whole is True
    assert comment.scope == SCOPE_WHOLE_DOCUMENT
    assert comment.anchor_scope_reported is True


def test_both_captured_shapes_run_through_THE_SAME_projection():
    """The amplifier's arm: one function, both shapes, and it is the *same* comment.

    If a per-endpoint branch existed, the two calls below would differ in more than
    ``is_whole`` / ``scope``. Everything else must be byte-identical, which is what proves
    the asymmetry is *handled* rather than special-cased away.
    """
    absent = Comment.from_file_comment(_sdk(payloads.CREATE_WHOLE_DOC["data"]))
    present = Comment.from_file_comment(_sdk(payloads.LIST_ONE_PAGE["data"]["items"][0]))

    assert absent.comment_id == present.comment_id     # the same comment, twice
    assert (absent.is_whole, absent.scope) == (None, SCOPE_UNREPORTED)
    assert (present.is_whole, present.scope) == (True, SCOPE_WHOLE_DOCUMENT)

    # Everything OUTSIDE the asymmetry agrees, field for field.
    a, p = absent.to_dict(), present.to_dict()
    del a["is_whole"], p["is_whole"]
    del a["scope"], p["scope"]
    assert a == p


def test_is_whole_false_is_anchored_and_distinct_from_absent():
    """The third state has to be reachable, or ``unreported`` means nothing."""
    body = dict(payloads.LIST_ONE_PAGE["data"]["items"][0], is_whole=False)
    comment = Comment.from_file_comment(_sdk(body))
    assert comment.is_whole is False
    assert comment.scope == SCOPE_ANCHORED
    assert comment.anchor_scope_reported is True


# --------------------------------------------------------------------------- #
# AC1 — typed, frozen, JSON-round-trippable, and it carries the named fields.   #
# --------------------------------------------------------------------------- #

def test_the_model_carries_every_field_the_read_promises():
    comment = Comment.from_file_comment(_sdk(payloads.LIST_ONE_PAGE["data"]["items"][0]))

    assert comment.comment_id == "7667710952829095653"
    assert comment.user_id == "ou_examplebot0000000000000000000001"
    assert comment.is_solved is False
    assert comment.solved_time is None
    assert comment.solver_user_id is None
    assert comment.quote is None
    assert comment.create_time == 1785278076
    assert comment.update_time == 1785278076
    assert comment.text == (
        "LD-156 hazard-drill comment ALPHA-9f15285c — disposable only.")
    assert len(comment.replies) == 1


@pytest.mark.parametrize("cls", [Comment, CommentReply, ReplyElement])
def test_every_model_class_is_frozen(cls):
    assert cls.__dataclass_params__.frozen is True


def test_the_model_round_trips_through_json_losslessly():
    comment = Comment.from_file_comment(
        _sdk(payloads.CREATE_WITH_PERSON_MENTION["data"]))
    text = json.dumps(comment.to_dict())
    assert Comment.from_dict(json.loads(text)) == comment


def test_the_json_projection_is_native_types_only():
    """No tuples, no dataclasses — the ``capabilities()`` projection discipline."""
    comment = Comment.from_file_comment(_sdk(payloads.LIST_ONE_PAGE["data"]["items"][0]))

    def check(value, where):
        assert isinstance(value, (dict, list, str, int, float, bool, type(None))), (
            f"{where} is {type(value).__name__}, not a JSON-native type")
        if isinstance(value, dict):
            for key, inner in value.items():
                assert isinstance(key, str), f"{where} has a non-string key {key!r}"
                check(inner, f"{where}.{key}")
        elif isinstance(value, list):
            for i, inner in enumerate(value):
                check(inner, f"{where}[{i}]")

    check(comment.to_dict(), "comment")


def test_the_absent_is_whole_survives_the_json_round_trip():
    """The trap's last hiding place: serialization. ``None`` must not become ``false``."""
    comment = Comment.from_file_comment(_sdk(payloads.CREATE_WHOLE_DOC["data"]))
    revived = Comment.from_dict(json.loads(json.dumps(comment.to_dict())))
    assert revived.is_whole is None
    assert revived.scope == SCOPE_UNREPORTED
    assert revived == comment
