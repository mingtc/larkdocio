"""larkdocio.common.metas — the ONE reader of a ``metas/batch_query`` refusal (LD-606).

**A ``code:0`` with an empty ``metas`` array is not an answer; it is a refusal whose reason is
parked in a sibling key.** ``POST /open-apis/drive/v1/metas/batch_query`` reports success at the
envelope and puts the per-token verdict in ``failed_list`` — so a caller who checks only a truthy
``code`` reads a refused token as resolved. That is not hypothetical: it is the shape a consumer
filed against 1.41.0, and it is the shape :data:`larkdocio.base.media.
WRONG_DOC_TYPE_IS_AN_EMPTY_ANSWER` was written for.

Five call sites in this library reach that endpoint, and exactly one of them read the key. The
other four disclosed a **missing FIELD** — *"Lark returned no title"* — when the fact was a
**REFUSED TOKEN**, which a caller reasonably reads as *the folder has no title*. So the reader is
authored once, here, and every site quotes it.

**Why this module exists rather than an import of the ``base`` copy: the two SEAMS.** The answer
arrives in two shapes, and a reader written for one silently loses the other:

* an **SDK object** (``lark_oapi``'s ``drive.v1.meta.batch_query``) — ``base/media.py`` and
  ``drive/files_write.py``. Fields are **attributes**.
* a **plain dict** off the raw-HTTP core (``drive/ops``' declared endpoint) —
  ``drive/client.py`` and ``drive/access_write.py``. Fields are **keys**.

The original authoring reached ``failed_list`` through ``getattr`` alone, so against a dict it
returned its *"named no reason at all"* fallback: it would have looked like it worked and never
found a reason. Both seams are therefore read here, in one place, by one function.

A **leaf** module: standard library only, no ``larkdocio`` imports, the
:mod:`larkdocio.common.staleness` shape — so any surface can quote it with no cycle and no SDK.
"""
from collections.abc import Mapping
from typing import Any

__all__ = ["field_of", "failed_reason", "REASON_FOUND", "REASON_ABSENT"]

#: What is said when Lark named a reason for this token. The sentence is the **existing**
#: authoring from ``base/media.py``, kept verbatim: the four uncured sites APPEND it to the text
#: they already emit, and the cured one must keep saying exactly what it said.
REASON_FOUND = ("Lark's own reason for this token, from the answer's failed_list: "
                "Code: {code}.")

#: What is said when there was no reason to find — an honest admission, never an invented cause.
#: An empty ``metas`` with an empty ``failed_list`` is a real answer shape and it means the route
#: said nothing about this token at all.
REASON_ABSENT = ("The answer named no reason for this token at all — it carried no failed_list "
                 "entry for it either.")


def field_of(obj: Any, name: str):
    """One field of a meta / failure entry, **however the seam hands it over**.

    An attribute first (the SDK object), then a key (the raw-HTTP dict). ``None`` when neither
    carries it — an absent field is not an error here; it is what a degrade is for.
    """
    value = getattr(obj, name, None)
    if value is None and isinstance(obj, Mapping):
        value = obj.get(name)
    return value


def failed_reason(data: Any, token: str) -> str:
    """Lark's own reason for ``token``, read out of the answer's ``failed_list``.

    ``data`` is the reply's ``data`` member in **either** seam's shape (an SDK object, or the
    plain dict a raw-HTTP call returns). The entry is matched **by token**: the batch route
    answers in its own order and for its own set, so another token's refusal is not this one's
    reason — reading ``failed_list[0]`` would hand a caller someone else's cause under their own
    token, the quietest possible wrong answer.
    """
    for entry in (field_of(data, "failed_list") or ()):
        if field_of(entry, "token") == token:
            return REASON_FOUND.format(code=field_of(entry, "code"))
    return REASON_ABSENT
