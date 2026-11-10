"""larkdocio.base.plain — the PLAIN projection of a Base cell: :func:`cell_text` and
:func:`plain_value`.

**Why this exists.** A Base record's ``fields`` map hands a Text cell back as a *segment array*
(``[{"text": "Ship it", "type": "text"}]``), so the first thing a consumer writes — before they
can key a dict on a row's title — is a small flattener. This library had the knowledge and
published none of the convenience, so the same five lines had to be re-derived, slightly
differently, by every caller.

**It is a PROJECTION, never a mutation** — the :func:`~larkdocio.base.media.scrub_attachment_cell`
spirit: a new value comes back and the cell you passed in is untouched.

**It is a sibling of the Markdown walker, not a duplicate of it.**
:func:`larkdocio.base.cells.render_segments` walks the same segment array but renders
**Markdown**: the text is escaped (``*`` becomes ``\\*``) and a ``url`` segment becomes
``[text](link)``. That is the right string to *print* and the wrong string to *key a dict on*
or compare. So this module is the plain half of the same idea, and the part that must not
diverge — *what a segment says*, dispatched on **the segment's own ``type``** (R13, not the
field's: an Email cell is a ``type:1`` field whose segments are ``"type":"url"``) — is read
through the one shared core, :func:`larkdocio.base.cells._segment_parts`. There is deliberately
no second segment walker here.

**The doors it accepts.** A Base value reaches a consumer through more than one door: the
**wire dict** a capture or ``records/search`` carries verbatim, the same body after the SDK has
deserialized the response, and an **attribute**-bearing typed node. Every **segment** is read
**by name** through the shared walk :func:`larkdocio.base._typed._step`, so all three doors
answer identically for the segment families (Text / Barcode / Email / Url); this module holds no
walk of its own. The **mapping** families — person, link, attachment, select, Location, the
Formula/Lookup wrapper — are recognised on a ``Mapping``, which is the shape every shipped read
route hands ``fields`` back as; an attribute-bearing node of one of *those* families is not an
evidenced door and is **not** claimed here. Anything this does not recognise — that node
included — degrades to ``str(value)``: **never raises, never guesses** (the reader's standing
posture, ``cells.py:275-276``).

**What comes out, per cell family.** Stated, because a guess here is a bug a consumer inherits:

* **Text / Barcode / Email (segment arrays)** — the segments' text, joined with **nothing**
  (the server has already aggregated: a ``LISTCOMBINE`` Lookup's separators are themselves
  segments, so inserting one double-separates), **unescaped and undecorated**. A ``url``
  segment inside an array contributes its **label**; the array's projection is one string, so
  the link is dropped there. A **lone** ``url`` segment — the shape a ``Url`` cell returns —
  keeps both halves as ``{"text": …, "link": …}``, because nothing else in the projection
  carries the link.
* **person / User / GroupChat** — the **name** only: ``name`` → ``en_name`` →
  :data:`~larkdocio.base.cells.PERSON_NAME_UNAVAILABLE`. The read shape also carries ``id``,
  ``email`` and ``avatar_url``; all three are **dropped**, which is the shipped L1 rule (D1,
  :func:`larkdocio.base.cells._person_name`) rather than a new decision taken here.
* **link (SingleLink / DuplexLink)** — the record ids. The two empty forms are **different
  facts** and are kept apart: ``{"link_record_ids": null}`` (**never-set**) projects to
  ``None``, ``{"link_record_ids": []}`` (**emptied** — links were written and their targets
  deleted) projects to ``()``. :func:`~larkdocio.base.cells.link_state` names the state itself.
  :func:`cell_text` renders both empties as ``""``, so a caller that needs the distinction
  takes :func:`plain_value` or ``link_state``.
* **attachment** — the **durable** half only: ``file_token`` / ``name`` / ``size`` / ``type``,
  through :func:`~larkdocio.base.media.scrub_attachment_cell`. The ``url`` and ``tmp_url`` a
  read-back carries are short-lived **signed** links — credentials — and never leave here, from
  any cell family: the same scrub is applied to every mapping this module emits.
* **single / multi select** — the option **name(s)**, which is already what the wire carries
  (an ``opt…`` id resolving to its name needs the field's ``property`` and is
  :func:`~larkdocio.base.cells.render_cell`'s job, not this one's).
* **Number / Currency / Progress / Rating / Checkbox / DateTime / Phone / AutoNumber** — the
  scalar **as it arrived, with no ``property`` formatting applied**: a ``Checkbox`` is the bool
  ``True`` (and ``"True"`` from :func:`cell_text`), a ``DateTime`` is its **millisecond epoch
  integer**, a ``Currency`` is the bare number with no code and no rounding. Formatting is a
  function of the field's ``property`` and lives in ``render_cell``.
* **Formula / Lookup** — the typed wrapper ``{"type": N, "value": […]}`` projects to its inner
  ``value`` (``N`` is the **result** field's type, not ``19``/``20``).
* **Location** — the two helpers **split**, and the split is the point.
  :func:`cell_text` gives its ``full_address``, falling back to ``name`` then ``location``,
  mirroring ``cells._r_location``'s own precedence — that is the string to key a dict on.
  :func:`plain_value` keeps the **whole mapping** (``address`` / ``adname`` / ``cityname`` /
  ``full_address`` / ``location`` / ``name`` / ``pname``, scrubbed like every mapping this
  module emits), because the coordinate pair in ``location`` has no other survivor in the
  projection and a value-shaped caller should not have to re-fetch to get it.
* **Stage (type 24)** — **not established here.** Its value is invisible to every read route,
  so no cell of it has ever arrived; the absent-with-reason marker is
  :data:`~larkdocio.base.cells.STAGE_OPAQUE_MARKER`, and a field-aware render is what surfaces
  it. This projection is value-shaped and has no field to consult.
* **anything else** — surfaced rather than dropped or raised (R13): its ``text`` if it names
  one, else the scrubbed mapping / ``str()`` of it.

Nothing here makes a call, needs a credential or consults a field schema: every value it is
handed was already fetched, and the projection is a pure function of that value alone.
"""
from typing import Any, Mapping

from larkdocio.base._typed import _step
from larkdocio.base.cells import (
    _MULTI_JOIN,
    _person_name,
    _segment_parts,
    link_record_ids,
    wrapper_type,
)
from larkdocio.base.media import scrub_attachment_cell

__all__ = ["cell_text", "plain_value"]


# --------------------------------------------------------------------------- #
# Shape recognition — on the VALUE alone, each rule carrying its evidence       #
# --------------------------------------------------------------------------- #

def _is_segment(node: Any) -> bool:
    """A segment names its own ``text``. No other captured cell shape does: an attachment
    carries ``name``, a person carries ``name`` / ``en_name``, a link carries
    ``link_record_ids``."""
    return _step(node, "text") is not None


def _is_person(node: Mapping) -> bool:
    """The person / chat object: an ``id`` beside any of the identity keys the read shape
    carries (``p0-2-05`` for ``User``, ``p0-4-04`` for ``GroupChat``). ``email`` is one of
    them, so a person object carrying **neither** name reads as a person and answers the
    redacted marker rather than leaking the id."""
    return "id" in node and any(
        k in node for k in ("name", "en_name", "avatar_url", "email"))


def _segment_text(seg: Any) -> str:
    """One segment → its own text, plain. Dispatched on **the segment's own ``type``**
    through the shared :func:`~larkdocio.base.cells._segment_parts` — the Markdown walker's
    rule, with the Markdown left out.

    Every evidenced kind surfaces its text: a ``text`` segment is its text, a ``url`` segment
    is its **label** (the link is carried only where a lone url segment is the whole cell),
    and an unevidenced kind does the same rather than raising (R13).
    """
    _seg_type, text, _link = _segment_parts(seg)
    if isinstance(text, str):
        return text
    return "" if text is None else str(text)


def _is_segment_array(value) -> bool:
    return bool(value) and all(_is_segment(member) for member in value)


# --------------------------------------------------------------------------- #
# The two public projections                                                    #
# --------------------------------------------------------------------------- #

def plain_value(value):
    """One Base cell value → a **plain Python value**, ready to compare, key or serialize.

    Per-family behaviour — Text, person, link (``never-set`` vs emptied), attachment (signed
    links scrubbed), select, Checkbox, Formula — is stated in this module's docstring, which is
    the contract. Returns a **new** value; the cell passed in is never mutated.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return _plain_mapping(value)
    if isinstance(value, (list, tuple)):
        if _is_segment_array(value):
            return "".join(_segment_text(member) for member in value)
        return [plain_value(member) for member in value]
    if _is_segment(value):                      # the attribute door
        return _segment_text(value)
    return str(value)


def cell_text(value) -> str:
    """One Base cell value → **plain text**: unescaped, undecorated, safe as a dict key.

    The five-line flattener every Base consumer was writing, shipped once. ``cell_text([{"text":
    "Ship it", "type": "text"}])`` is ``"Ship it"`` — where
    :func:`~larkdocio.base.cells.render_segments` would escape it for Markdown.

    A multi-valued cell (persons, links, attachments, multi-select) joins with ``", "``, the
    same separator the Markdown renderers use; a segment array joins with **nothing**. The two
    empty link forms both render ``""`` here — :func:`plain_value` and
    :func:`~larkdocio.base.cells.link_state` are where that distinction survives.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bool, int, float)):
        return str(value)
    if isinstance(value, Mapping):
        return _text_of_mapping(value)
    if isinstance(value, (list, tuple)):
        if _is_segment_array(value):
            return "".join(_segment_text(member) for member in value)
        return _MULTI_JOIN.join(
            text for text in (cell_text(member) for member in value) if text
        )
    if _is_segment(value):                      # the attribute door
        return _segment_text(value)
    return str(value)


# --------------------------------------------------------------------------- #
# The mapping families — one rule each, in evidence order                       #
# --------------------------------------------------------------------------- #

def _plain_mapping(node: Mapping):
    if "link_record_ids" in node:
        return link_record_ids(node)            # None (never-set) / () (emptied) / the ids
    if "file_token" in node:
        return scrub_attachment_cell(node)
    if _is_person(node):
        return _person_name(node)
    if wrapper_type(node) is not None:
        return plain_value(node.get("value"))
    if _is_segment(node):
        seg_type, text, link = _segment_parts(node)
        if seg_type == "url":
            return {"text": text, "link": link}
        return _segment_text(node)
    return scrub_attachment_cell(node)          # any other mapping, credentials removed


def _text_of_mapping(node: Mapping) -> str:
    if "link_record_ids" in node:
        return _MULTI_JOIN.join(str(i) for i in (link_record_ids(node) or ()))
    if "file_token" in node:
        safe = scrub_attachment_cell(node)
        return str(safe.get("name") or safe.get("file_token") or "")
    if _is_person(node):
        return _person_name(node)
    if wrapper_type(node) is not None:
        return cell_text(node.get("value"))
    if _is_segment(node):
        return _segment_text(node)
    if any(k in node for k in ("full_address", "location")):
        return str(node.get("full_address") or node.get("name") or node.get("location") or "")
    return str(scrub_attachment_cell(node))
