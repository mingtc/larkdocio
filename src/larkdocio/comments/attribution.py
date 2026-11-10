"""Record attribution for a Base's comments — read off the response's own bytes.

A comment on a Lark Base is listed by the **drive** comment family, exactly as a document's
is: one file token (the Base's app token), one ``file_type`` of ``bitable``, one paged list.
What makes it more than a file-level note is a small object the payload hangs off each
**reply**: ``extra.notify_extra``, carrying the id of the **record** the reviewer was looking
at, plus the table and the view. That is what makes a Base comment attributable to a *row*.

**Two facts decided the shape of this module, and both are payload facts.**

*The wire keys are ``record`` / ``table`` / ``view``.* The finding was recorded in prose as
``record_id`` / ``table_id`` / ``view_id``; the capture this surface is built on
(``tests/captures/base-study/captures/p1-q7-01-comments-populated.json``, in the source repository) shows the
shorter spellings,
holding exactly the ids the prose meant — they join to the same record and table an earlier
probe pack addressed by id. So the finding stands and its spelling did not. This module reads
**only** what was observed: a payload using the ``*_id`` spelling yields **no** attribution,
because accepting a shape no server has sent is how a projection begins inventing one. The
names it *exposes* stay ``record_id`` / ``table_id`` / ``view_id``, which is what those values
are.

*The pinned SDK drops the object entirely.* ``lark_oapi``'s ``ReplyExtra`` declares one key,
``image_list``, and its deserializer assigns only declared keys — so by the time a reply
reaches the typed model, ``notify_extra`` is gone. The attribution is therefore harvested
from the **same response's own raw bytes**, which the SDK hands back on every call as
``response.raw.content``. This costs **no extra API call**, adds **no second client** and
opens **no second HTTP path**: it is the one response, read twice — once by the SDK's
deserializer for everything it models, and once here for the one object it does not.

**Absence is typed, never halved.** A reply with no ``notify_extra``, with a
``notify_extra`` that is not a mapping, or with one that omits the record key, yields
``None`` — a **file-level** Base comment. There is no partial attribution: an attribution
without a record id would name a row it cannot point at.
"""
import json
from dataclasses import dataclass
from typing import Dict, Optional

#: The key the reply's ``extra`` hangs the attribution object off.
NOTIFY_EXTRA_KEY = "notify_extra"

#: The wire key holding the record id. **Observed**, and deliberately not the ``record_id``
#: the prose predicted — see this module's own documentation.
WIRE_KEY_RECORD = "record"
#: The wire key holding the table id.
WIRE_KEY_TABLE = "table"
#: The wire key holding the view id.
WIRE_KEY_VIEW = "view"

#: :attr:`~larkdocio.comments.models.Comment.attribution_state` for a comment the payload
#: attributes to one record of one table.
ATTRIBUTION_RECORD = "record-attributed"
#: :attr:`~larkdocio.comments.models.Comment.attribution_state` for a comment the payload
#: attributes to no record — a **file-level** comment on the Base itself. A named state, not
#: a missing one, and never a row this surface guessed at.
ATTRIBUTION_FILE_LEVEL = "file-level"


@dataclass(frozen=True)
class BaseAttribution:
    """The row a Base comment was written against.

    :attr:`record_id` is the attribution key and is always present on an instance — a
    :class:`BaseAttribution` cannot exist without one. :attr:`table_id` and :attr:`view_id`
    are the context the payload usually carries alongside it, and are ``None`` when it did
    not: reporting them as absent is the honest answer, and the record id alone is still a
    join key.
    """

    record_id: str
    table_id: Optional[str] = None
    view_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {"record_id": self.record_id, "table_id": self.table_id,
                "view_id": self.view_id}

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Optional[BaseAttribution]":
        if not d or not d.get("record_id"):
            return None
        return cls(record_id=d["record_id"], table_id=d.get("table_id"),
                   view_id=d.get("view_id"))


def attribution_from_extra(extra) -> Optional[BaseAttribution]:
    """The attribution one reply's ``extra`` carries, or ``None``.

    Tolerant of every shape that is not the observed one — an absent ``extra``, a
    non-mapping, a ``notify_extra`` that is a list or a string, a ``notify_extra`` with no
    record key — because each of those is *no attribution*, and none of them is an error
    worth failing a whole comment read over.
    """
    if not isinstance(extra, dict):
        return None
    notify = extra.get(NOTIFY_EXTRA_KEY)
    if not isinstance(notify, dict):
        return None
    record = notify.get(WIRE_KEY_RECORD)
    if not record:
        return None
    table = notify.get(WIRE_KEY_TABLE)
    view = notify.get(WIRE_KEY_VIEW)
    return BaseAttribution(
        record_id=str(record),
        table_id=str(table) if table else None,
        view_id=str(view) if view else None,
    )


def _walk_replies(items):
    """Every reply dict in a comment-family response body, at either nesting.

    The list and batch-fetch endpoints answer with comments whose replies are nested under
    ``reply_list.replies``; the reply-list endpoint answers with the replies themselves. Both
    shapes are walked, because a truncated thread is completed through the second one and its
    attribution must not be lost on the way.
    """
    for item in items or ():
        if not isinstance(item, dict):
            continue
        if "reply_id" in item:
            yield item
        reply_list = item.get("reply_list")
        if isinstance(reply_list, dict):
            for reply in reply_list.get("replies") or ():
                if isinstance(reply, dict):
                    yield reply


def attributions_from_body(body) -> Dict[str, BaseAttribution]:
    """``{reply_id: attribution}`` for every attributed reply in a parsed response body."""
    if not isinstance(body, dict):
        return {}
    data = body.get("data")
    if not isinstance(data, dict):
        return {}
    out: Dict[str, BaseAttribution] = {}
    for reply in _walk_replies(data.get("items")):
        reply_id = reply.get("reply_id")
        if not reply_id:
            continue
        found = attribution_from_extra(reply.get("extra"))
        if found is not None:
            out[str(reply_id)] = found
    return out


def attributions_from_raw(content) -> Dict[str, BaseAttribution]:
    """The same, from the raw response bytes the SDK hands back.

    Anything unreadable — no bytes at all, bytes that are not JSON, JSON that is not an
    object — is **no attribution**, not a failure: the typed read has already succeeded by
    the time this runs, and a comment read must not be lost to a side channel.
    """
    if not content:
        return {}
    try:
        if isinstance(content, (bytes, bytearray)):
            content = content.decode("utf-8")
        parsed = json.loads(content)
    except (UnicodeDecodeError, ValueError):
        return {}
    return attributions_from_body(parsed)
