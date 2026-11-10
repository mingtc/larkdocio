"""larkdocio.base.cells — the Base ``(type, ui_type)`` cell-renderer registry (LD-246).

**A Base cell is not a scalar.** The storage ``type`` and the presentation ``ui_type``
riding on top of it *together* decide the encoding, so ``type:2`` is ``Number`` **or**
``Progress`` **or** ``Currency`` **or** ``Rating``, and a registry keyed on ``type``
alone is wrong by construction. Everything here dispatches on the **pair**.

**The shape, and it is checkable.** The maintainer's picker names **28** field types; **Button has
no AUTHORING identity** (nothing Button-shaped is in either server enum — parity matrix
§ 1.1, 23 refused create attempts) and is a maintainer-ruled WILL-NOT-SUPPORT, so there are **27**
pairs: **26 render a value** and ``(24, "Stage")`` renders the absent-with-reason marker.
``3`` (type 1) + ``4`` (type 2) + ``20`` singletons = 27.

**Button DOES have a read identity, and the offline packs said otherwise.** THE L1 GATE
(``tests/test_live_base_canary.py``) found a UI-created Button field returned by
``…/fields`` as ``type: 3001``, ``ui_type: "Button"``, ``property: null`` — so *"no API
identity at all"* was an over-strong inference drawn from the **authoring** enums. It stays
**unregistered**: an API fact does not reopen a maintainer ruling, and the key is absent from every
record, so the column renders blank. ``BASE.md`` — in the source repository, not in the wheel — carries
register row **13**'s finding and its revisit trigger.

**Read pin.** Every shape below is the one ``POST …/records/search`` returns. The other
three read routes disagree — the legacy ``GET …/records`` reports an empty cell as an
explicit ``null`` key where ``search`` **omits** it, and a create **echo** returns a
bare string where ``search`` returns a segment array — so a fixture pinned to anything
but ``search`` is a bug (parity § "Verdict"; opener R7).

The five facts that are not guessable, each with a test:

1. **A text cell is a SEGMENT ARRAY and the walker dispatches PER SEGMENT** (R13).
   ``type:1`` reads back ``[{"text":…,"type":"text"}]`` — *including* ``ui_type:
   Barcode`` — and an **Email** field is a ``type:1`` field whose segments carry
   ``"type":"url"`` with a ``mailto:`` link. A walker that assumes a type-1 array holds
   only ``text`` segments emits nothing for Email.
2. **A link cell is an OBJECT with two distinct empty forms** — ``{"link_record_ids":
   [...]}``, ``null`` when never written, ``[]`` after a linked record is deleted. A
   renderer keying on ``isinstance(v, list)`` gets **every** link cell wrong; one keying
   on truthiness conflates the two empties. :func:`link_state` keeps them apart.
3. **An empty cell is an ABSENT KEY.** Rows project against the **field list**
   (:func:`render_row`), never against the union of observed keys. ``Checkbox`` is the
   sharpest case: ``true`` is present, **false is an absent key**.
4. **A Lookup cell is a Formula-style typed wrapper whose ``value`` is a segment array**,
   and the wrapper's ``"type"`` is the **target field's** type, not ``19``.
   ``LISTCOMBINE``'s separators are **themselves segments**, so the join is ``""`` —
   joining with ``", "`` double-separates.
5. **Stage (type 24) is fully opaque** — schema readable, values invisible to 17 read
   routes, writes provably dropped. A type-24 column can hold UI-set data that no API
   read returns (R14), so an empty cell would silently assert "no data" about data that
   exists. It renders :data:`STAGE_OPAQUE_MARKER`, never a guess and never a blank.

**Why a Base-local segment walker rather than a lift into ``common/`` (the AC2 Dev
call, recorded here as the AC asks).** Three walkers exist in this repo and they are
not the same idea at three sites:

* the docx one (:func:`larkdocio.blocks.text._element_inlines`) walks **typed SDK
  ``TextElement`` objects** — a union of populated members, not JSON at all;
* the Sheets one (``larkdocio.sheets.render._segment_to_str``) walks a **different JSON
  vocabulary** (``segmentStyle``, ``mentionType``, ``multipleValue``) and — load-bearing
  — is pinned **by source text**: ``tests/test_sheets_md_matrix.py::_BRANCH_MARKERS``
  greps ``sheets/render.py`` for literals like ``seg_type == "text"`` to derive the
  branch registry /SHEETS.md is checked against. Lifting that function out of that file
  reddens a shipped drift guard and turns a feature story into a shipped-surface
  refactor;
* Base's vocabulary carries no style, and **three** segment kinds have now been seen in a
  Base cell: ``text``, ``url`` and — observed on one Base outside this project's tenant,
  on one day, with a released wheel installed — ``mention``, the chip Lark mints when a
  human touches a cell holding a pasted document url. *(This clause previously asserted that
  the first two kinds were the only evidenced ones and that no chip kind existed here at all.
  That was an EVIDENCE claim, and a production Base falsified it; the three-walkers reason
  above is untouched by it and stands. The kind is Base's own spelling of a chip — it is NOT
  the Sheets vocabulary arriving, which is why the walker still does not lift.)* What is
  measured and what is not is stated once, in :data:`SEGMENT_KIND_DISCLOSURE`.

So what is genuinely one idea **is** single-sourced: the **Markdown composition itself**
— escaping, link form, emphasis — is :class:`larkdocio.model.MarkdownRenderer`, the same
serializer docx and Sheets both compose through, so a Base ``url`` segment and a docx
link emit **byte-identical** Markdown. What is Base-local is a dozen lines of
vocabulary dispatch. A shared *JSON-segment* walker is a worthwhile follow-up, but it is
a refactor of the Sheets surface (and of its guard), not a rung of this story.

**Scope.** This renders **one cell**, and one row against a field list. Table assembly
— GFM pipe escaping, the newline → ``<br>`` fold, the header row — is **LD-248**, the
same split the shipped Sheets surface uses (``sheets/render.py`` vs ``sheets/table.py``),
so a pipe and a newline survive cell scope verbatim here on purpose.
"""
import datetime
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Sequence, Tuple

from larkdocio.base import date_zone
from larkdocio.base._typed import _step
from larkdocio.common import unescape_url
from larkdocio.model import MarkdownRenderer, StyledText, Text

#: ``FieldSpec`` has a field literally called ``property`` (Lark's own key), which
#: shadows the builtin inside the class body — so the decorator is bound here first.
_py_property = property

# --------------------------------------------------------------------------- #
# Markers and constants (exact bytes are pinned by tests)                      #
# --------------------------------------------------------------------------- #

#: The Stage (type 24) absent-with-reason marker, in the reader's own house register
#: (``[unsupported inline: …]`` / ``[Unsupported Add-On block: …]``). R14: a bare empty
#: cell would silently assert "no data" about data that demonstrably exists.
STAGE_OPAQUE_MARKER = (
    "[unreadable Base cell: Stage (type 24) — Lark returns no value for this "
    "field on any read route]"
)

#: A person / chat object that carries neither ``name`` nor ``en_name``. **Never** an
#: id, an email or an avatar URL (D1: name-only, and no flag widens it in L1).
PERSON_NAME_UNAVAILABLE = "[name unavailable]"

#: The UI types this library will not support. Button is a **product ruling** (maintainer,
#: 2026-08-03) that survives the API gaining the capability — it is an action launcher
#: spanning the automation space, not a value-bearing field.
WILL_NOT_SUPPORT = ("Button",)

#: Used when a date-bearing field carries no ``date_formatter`` of its own — the
#: auto fields (1001 / 1002) read back ``property: null``.
DEFAULT_DATE_FORMATTER = "yyyy/MM/dd HH:mm"

#: Used when the app carries no ``time_zone`` — a docx-born embedded Base has none at
#: all (P0 addendum § P1; ``p0-1-06`` records it as literally ABSENT). Rendering is a
#: pure function of ``(value, date_formatter, time_zone)`` and never of the host clock
#: or locale, so the fallback must be a fixed zone, not "local".
#:
#: **LD-463: it is the same object as** :data:`larkdocio.base.date_zone.ASSUMED_ZONE`, not a
#: second spelling of it. The zone is no longer *only* a default — it is an **assumption**, it
#: was measured wrong for a zone-less Base on the tenant probed (Lark's own day boundary sat at
#: 16:00 UTC), and every read that falls back to it now says so through
#: :func:`larkdocio.base.date_zone.zone_disclosure`. The constant's value does not change, so no
#: rendered byte moves; what changes is that the assumption is named where a consumer can see it
#: and that a Base this library creates can declare its zone instead.
DEFAULT_TIME_ZONE = date_zone.ASSUMED_ZONE

#: Link-cell states. The two empties are **different facts** about the same cell.
LINK_NEVER_SET = "never-set"        # ``{"link_record_ids": null}``
LINK_EMPTIED = "emptied"            # ``{"link_record_ids": []}`` — after a target delete
LINK_POPULATED = "populated"
LINK_NOT_AN_OBJECT = "not-an-object"   # a legacy / create-echo bare list, not the pin

#: Join between the members of a multi-valued cell (multi-select, persons, links,
#: attachments). NOT used for a segment array — see :func:`render_segments`.
_MULTI_JOIN = ", "

#: The segment kinds a Base cell has actually been **seen** to carry, in the order they were
#: evidenced. ``text`` and ``url`` came from the Base study's own captures; ``mention``
#: arrived from a consumer's production Base (LD-497), and until then this module's own note
#: said the vocabulary was the first two and nothing else.
MEASURED_SEGMENT_KINDS = ("text", "url", "mention")

#: The ``mentionType`` values a captured mention segment has actually carried — **one**.
MEASURED_MENTION_TYPES = ("Docx",)

#: The ``mentionType`` values nobody has captured. They are **unmeasured, not refuted**, and
#: they are named so a reader can see where the evidence stops — the disclose-the-unmeasured
#: shape ``process/doctrine/negative-claims.md`` prescribes, in the dev repo, not in the
#: wheel. Nothing branches on them:
#: :func:`render_segment` keys on the presence of a ``link``, so a chip of one of these kinds
#: is rendered by the same rule the moment one arrives — what is unknown is what they carry,
#: not what this library would do with it.
UNMEASURED_MENTION_TYPES = ("Chat", "User")

#: WHAT A BASE MARKDOWN READ PRESERVES, AND WHERE THE EVIDENCE STOPS — the one authored copy
#: of the claim. The packaged guide states the same truth in a consumer's vocabulary; this is
#: where it is settled, so the two cannot disagree about which kinds were measured.
SEGMENT_KIND_DISCLOSURE = (
    "A Base text cell reads back as a segment array, and three segment kinds have been seen "
    "in one: `text`, `url` and `mention` — the chip Lark mints when a human touches a cell "
    "holding a pasted document url. A mention that carries a `link` renders `[text](link)`, "
    "byte-identical to a `url` segment, because both go through the same serializer. "
    "A mention that carries no link renders its text alone. "
    "The edge of the evidence: what has been observed is one tenant's `Docx` mentions, on "
    "the records/search read route, on a `1 / Text` field, observed outside this project's "
    "tenant on one day. The chips a "
    "person (@user, `mentionType` User) or a group chat (@chat, `mentionType` Chat) produce "
    "are UNMEASURED — nobody has captured one, so nothing here claims what they carry or "
    "whether a Base cell can hold one at all. Until one is captured, a Base Markdown read is "
    "link-preserving for the kinds listed here and is not established as link-lossless for "
    "every cell a human has touched. The plain projection (`cell_text` / `plain_value`) is a "
    "separate contract and drops the link on purpose."
)

#: Rating symbol glyphs. Only ``star`` is evidenced (``p0-2-03``); anything else falls
#: back to the raw symbol name rather than inventing a glyph.
_RATING_GLYPHS = {"star": "★"}

_DEFAULT_RENDERER = MarkdownRenderer()

_DATE_TOKENS = (
    ("yyyy", "%Y"), ("yy", "%y"), ("MM", "%m"), ("dd", "%d"),
    ("HH", "%H"), ("mm", "%M"), ("ss", "%S"),
)


# --------------------------------------------------------------------------- #
# Typed views of the two payloads a renderer needs                             #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class FieldSpec:
    """One row of ``GET …/fields`` — the schema half a renderer dispatches on.

    ``property`` is the field's own configuration and is where **all** formatting comes
    from: a number's ``formatter``, a currency's ``currency_code``, a rating's
    ``rating.symbol``, a date's ``date_formatter``, a select's ``options``. Nothing is
    inferred from the value.

    **The storage integer answers to both spellings.** It is ``type`` here — the name the
    payload uses — but ``field_type`` elsewhere in this library (``create_field(field_type=)``,
    ``ComputedColumn.field_type``), so ``FieldSpec(field_type=2, …)`` is accepted as an alias
    of ``type=`` and ``.field_type`` reads the same integer back. Naming **both** in one call
    is a ``TypeError``, not a coin toss.
    """

    field_name: str
    type: int
    ui_type: str
    property: Optional[dict] = None
    field_id: str = ""
    is_primary: bool = False

    @_py_property
    def pair(self) -> Tuple[int, str]:
        return (self.type, self.ui_type)

    @_py_property
    def field_type(self) -> int:
        """``type``, under the spelling the field-authoring surface uses for the same integer."""
        return self.type

    @classmethod
    def from_payload(cls, item: dict) -> "FieldSpec":
        """Build from one ``GET …/fields`` item, verbatim."""
        return cls(
            field_name=item.get("field_name", ""),
            type=item.get("type"),
            ui_type=item.get("ui_type", ""),
            property=item.get("property"),
            field_id=item.get("field_id", "") or "",
            is_primary=bool(item.get("is_primary")),
        )


_fieldspec_init = FieldSpec.__init__


def _fieldspec_init_accepting_the_other_spelling(self, *args, **kwargs):
    """``FieldSpec(field_type=…)`` → ``type=…``, an **additive** alias over the generated init.

    The same integer is ``field_type`` on ``create_field`` and on ``ComputedColumn`` and
    ``type`` on the payload this dataclass mirrors; a consumer who has just called one meets
    the other's spelling as a bare ``TypeError`` whose did-you-mean suggests ``field_name``.
    The alias is a keyword the generated ``__init__`` forwards — no field is added, so
    ``dataclasses.fields``, equality, ``repr`` and ``replace`` are untouched.
    """
    field_type = kwargs.pop("field_type", None)
    if field_type is not None:
        if "type" in kwargs or len(args) >= 2:
            raise TypeError(
                "FieldSpec got both 'type' and 'field_type' — they are two spellings of the "
                "same storage integer; pass exactly one")
        kwargs["type"] = field_type
    _fieldspec_init(self, *args, **kwargs)


FieldSpec.__init__ = _fieldspec_init_accepting_the_other_spelling


@dataclass(frozen=True)
class RenderContext:
    """Everything a cell needs that is not the cell or its field.

    ``time_zone`` comes from ``GET /bitable/v1/apps/{app}`` (``Asia/Singapore`` on the
    scratch tenant) and may be **absent** entirely on a docx-born embedded Base. When it is
    absent, :data:`DEFAULT_TIME_ZONE` is an **assumption** and not a fact about the Base —
    :mod:`larkdocio.base.date_zone` carries the one policy and the disclosure the read result
    hands a consumer.

    ``links`` is the **opt-in** cross-table link resolution
    (:class:`larkdocio.base.link_resolution.LinkResolution`). It is ``None`` by default and
    ``None`` means *byte-identical to L1*: with no resolution attached, a link cell renders the
    record ids exactly as it always has, and no code path here can ask for one.
    """

    time_zone: Optional[str] = None
    renderer: Optional[MarkdownRenderer] = None
    links: Optional[object] = None

    @property
    def md(self) -> MarkdownRenderer:
        return self.renderer or _DEFAULT_RENDERER


_DEFAULT_CONTEXT = RenderContext()


# --------------------------------------------------------------------------- #
# The segment walker (R13) — dispatches on EACH SEGMENT'S OWN type             #
# --------------------------------------------------------------------------- #

def render_segments(segments, ctx: RenderContext = _DEFAULT_CONTEXT) -> str:
    """Walk a segment array, joining with **nothing**.

    The server has already aggregated: a ``LISTCOMBINE`` Lookup puts its ``","``
    separators into the stream as literal segments, so inserting a separator here
    double-separates.
    """
    if segments is None:
        return ""
    if not isinstance(segments, (list, tuple)):
        return render_segment(segments, ctx)
    return "".join(render_segment(seg, ctx) for seg in segments)


def _segment_parts(seg):
    """``(type, text, link)`` read off one segment **by name, whatever door it came through**
    (:func:`larkdocio.base._typed._step`) — the single definition of the R13 dispatch inputs.

    Two projections read a segment: this module's **Markdown** one and the **plain** one in
    :mod:`larkdocio.base.plain`. They must not disagree about *what a segment says* — only
    about how to write it down — so the reading happens here, once, and each side composes its
    own output from the same three parts. The names are this call site's own list, which is why
    they are here and not in ``_typed`` (that module's docstring, ``:20-26``).
    """
    return _step(seg, "type"), _step(seg, "text") or "", _step(seg, "link")


def render_segment(seg, ctx: RenderContext = _DEFAULT_CONTEXT) -> str:
    """One segment → Markdown, dispatched on **the segment's own ``type``** (R13).

    Never on the field's type: an Email cell is a ``type:1`` field whose segments are
    ``"type":"url"``. The plain sibling — :func:`larkdocio.base.plain.cell_text` — dispatches
    on the same rule, off the same :func:`_segment_parts`.
    """
    if seg is None:
        return ""
    if isinstance(seg, str):
        return ctx.md.render_inline([Text(seg)])
    if isinstance(seg, dict):
        seg_type, seg_text, link = _segment_parts(seg)
        # A MENTION CARRYING A LINK **IS** A LINK, and takes the very same door `url` takes.
        # Lark mints a mention whenever a human touches a cell holding a pasted document url,
        # converting it into a chip that carries the document's title in `text` and the real
        # url — block anchor included — in `link`. Routing it into `_url_segment` rather than
        # writing a second link-emitting branch is what makes the two byte-identical by
        # construction instead of by coincidence (LD-497; the consumer's first-preference ask).
        # The rule keys on the PRESENCE OF A LINK, never on `mentionType`: no kind of chip has
        # been captured except `Docx`, and a kind nobody measured earns no branch of its own
        # (:data:`SEGMENT_KIND_DISCLOSURE`).
        if seg_type == "url" or (seg_type == "mention" and link):
            return _url_segment(seg, ctx)
        if seg_type == "text":
            return ctx.md.render_inline([Text(seg_text)])
        # A link-less mention, and a genuinely unevidenced segment kind — surface the text,
        # never raise, never guess. A link-less mention is not an error: the chip simply
        # carries nothing this projection could write down.
        return ctx.md.render_inline([Text(str(seg_text))])
    return str(seg)


def _url_segment(seg: dict, ctx: RenderContext) -> str:
    """``{"link": …, "text": …, "type": "url"}`` → ``[text](link)``.

    Composed by the **shared** serializer, so a Base link and a docx link are
    byte-identical. An Email cell's ``link`` is the server-synthesized ``mailto:`` —
    rendered as read; it is **not** round-trippable on write (``1254060``).
    """
    text = seg.get("text") or ""
    link = seg.get("link")
    if not link:
        return ctx.md.render_inline([Text(text)])
    return ctx.md.render_inline([StyledText(content=text, link_url=unescape_url(link))])


# --------------------------------------------------------------------------- #
# Link cells (AC3 / AC8)                                                        #
# --------------------------------------------------------------------------- #

def link_state(value) -> str:
    """Which of the link cell's four states this value is.

    The two empties are **different facts**: ``null`` means nobody ever wrote a link;
    ``[]`` means links were written and the target records were deleted.
    """
    if not isinstance(value, dict) or "link_record_ids" not in value:
        return LINK_NOT_AN_OBJECT
    ids = value.get("link_record_ids")
    if ids is None:
        return LINK_NEVER_SET
    if not ids:
        return LINK_EMPTIED
    return LINK_POPULATED


def link_record_ids(value):
    """The record ids in a link cell — ``None`` for never-set, ``()`` for emptied.

    Distinct on purpose: a caller that wants to know *why* a link cell is empty can,
    and a caller that only renders treats both as "".
    """
    state = link_state(value)
    if state == LINK_NEVER_SET:
        return None
    if state == LINK_EMPTIED:
        return ()
    if state == LINK_POPULATED:
        return tuple(value["link_record_ids"])
    # A legacy list / create echo — accepted defensively, but `search` is the pin.
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return ()


# --------------------------------------------------------------------------- #
# Scalar formatting helpers — all pure, all driven from `property`             #
# --------------------------------------------------------------------------- #

def _plain_number(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _format_number(value, formatter: Optional[str]) -> str:
    """Apply a Lark numeric ``formatter`` pattern (``0``, ``0.00``, ``0%``, ``#,##0.0``).

    Half-up rounding — the display convention a spreadsheet uses; Python's default
    banker's rounding would render ``42.5`` under ``"0"`` as ``42``.
    """
    if value is None:
        return ""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "" if value == "" else str(value)
    pattern = (formatter or "").strip()
    if not pattern:
        return _plain_number(value)
    percent = pattern.endswith("%")
    core = pattern[:-1] if percent else pattern
    grouping = "," in core
    core = core.replace(",", "")
    decimals = len(core.split(".", 1)[1]) if "." in core else 0
    number = Decimal(str(value))
    if percent:
        number *= 100
    quantum = Decimal(1).scaleb(-decimals)
    number = number.quantize(quantum, rounding=ROUND_HALF_UP)
    text = f"{number:,.{decimals}f}" if grouping else f"{number:.{decimals}f}"
    return text + ("%" if percent else "")


def _zone(name: Optional[str]):
    """The tzinfo to render in — :func:`larkdocio.base.date_zone.load_zone`, and nothing else.

    This function used to own the fallback itself: it caught ``ZoneInfoNotFoundError`` and
    returned UTC, while the disclosure a caller reads was decided separately from
    ``time_zone``'s truthiness. Two independent decisions about one fact, and only this one knew
    — so on a host with no tz database every date was converted in the wrong zone and the result
    reported the zone it had been *asked* for (LD-659 AC3). The fallback still happens; what
    changed is that the function that DISCLOSES it is the same one that DECIDES it.
    """
    tzinfo = date_zone.load_zone(name)
    # Unreachable through `_format_datetime`, which passes `resolve_zone(...).zone` — already
    # either a loadable name or the always-loadable assumed zone. Kept because this helper is
    # callable with a bare name and returning `None` from it would be the silent-wrongness class
    # one layer down.
    return tzinfo if tzinfo is not None else datetime.timezone.utc


def _format_datetime(value, formatter: Optional[str], time_zone: Optional[str]) -> str:
    """A ms-epoch int → its ``date_formatter`` rendering in the app's ``time_zone``.

    Never a function of the host's local clock, zone or locale (PROJECT.md, in the dev repo, § Quality bar →
    Determinism): the three arguments are what it reads.

    **The one host fact it cannot avoid, stated because it used to be hidden**: turning a zone
    NAME into a zone needs a tz database, and where the host has none the rendering falls back
    to UTC. So two machines can render one payload differently — they always could — and the
    read result now DISCLOSES that (``date_zone_assumed`` / ``date_zone_requested`` /
    ``date_zone_disclosure``) instead of reporting the zone it was asked for. Adding ``tzdata``
    as a runtime dependency is a separate decision (LD-664) and would not change this
    function.

    ``time_zone`` falsy means the Base declared none, and then this renders in
    :data:`larkdocio.base.date_zone.ASSUMED_ZONE` — an **assumption**, disclosed on the read
    result rather than rendered into the cell, so no output byte depends on it being new
    (LD-463; the one policy is :data:`larkdocio.base.date_zone.POLICY`).
    """
    if value is None or value == "":
        return ""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    moment = datetime.datetime.fromtimestamp(value / 1000,
                                             _zone(date_zone.resolve_zone(time_zone).zone))
    pattern = formatter or DEFAULT_DATE_FORMATTER
    out, i = [], 0
    while i < len(pattern):
        for token, directive in _DATE_TOKENS:
            if pattern.startswith(token, i):
                out.append(moment.strftime(directive))
                i += len(token)
                break
        else:
            out.append(pattern[i])
            i += 1
    return "".join(out)


def _option_name(value, prop: Optional[dict]) -> str:
    """A select's value is already the option **name**; an ``opt…`` id resolves to it."""
    if not isinstance(value, str):
        return "" if value is None else str(value)
    for option in ((prop or {}).get("options") or ()):
        if isinstance(option, dict) and option.get("id") == value:
            return option.get("name") or value
    return value


def _person_name(person) -> str:
    """``name`` → ``en_name`` → the redacted marker. **Never** ``email``, ``avatar_url``
    or the id, at any setting in L1 (D1; no flag widens this)."""
    if not isinstance(person, dict):
        return "" if person is None else str(person)
    name = person.get("name") or person.get("en_name")
    return name if name else PERSON_NAME_UNAVAILABLE


def _as_list(value):
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)


# --------------------------------------------------------------------------- #
# The per-pair renderers                                                        #
# --------------------------------------------------------------------------- #

def _r_segments(value, field: FieldSpec, ctx: RenderContext) -> str:
    if isinstance(value, str):          # the create-echo bare string; `search` is the pin
        return ctx.md.render_inline([Text(value)])
    return render_segments(value, ctx)


def _r_number(value, field: FieldSpec, ctx: RenderContext) -> str:
    return _format_number(value, (field.property or {}).get("formatter"))


def _r_currency(value, field: FieldSpec, ctx: RenderContext) -> str:
    prop = field.property or {}
    text = _format_number(value, prop.get("formatter"))
    code = prop.get("currency_code")
    return f"{code} {text}" if (code and text) else text


def _r_rating(value, field: FieldSpec, ctx: RenderContext) -> str:
    prop = field.property or {}
    text = _format_number(value, prop.get("formatter"))
    symbol = ((prop.get("rating") or {}).get("symbol")) or ""
    if not text or not symbol:
        return text
    return f"{text} {_RATING_GLYPHS.get(symbol, symbol)}"


def _r_single_select(value, field: FieldSpec, ctx: RenderContext) -> str:
    return _option_name(value, field.property)


def _r_multi_select(value, field: FieldSpec, ctx: RenderContext) -> str:
    return _MULTI_JOIN.join(
        name for name in (_option_name(v, field.property) for v in _as_list(value)) if name
    )


def _r_datetime(value, field: FieldSpec, ctx: RenderContext) -> str:
    return _format_datetime(
        value, (field.property or {}).get("date_formatter"), ctx.time_zone
    )


def _r_checkbox(value, field: FieldSpec, ctx: RenderContext) -> str:
    return "[x]" if value is True else "[ ]"


def _r_persons(value, field: FieldSpec, ctx: RenderContext) -> str:
    return _MULTI_JOIN.join(
        name for name in (_person_name(p) for p in _as_list(value)) if name
    )


def _r_text_scalar(value, field: FieldSpec, ctx: RenderContext) -> str:
    if value is None:
        return ""
    return ctx.md.render_inline([Text(str(value))])


def _r_url(value, field: FieldSpec, ctx: RenderContext) -> str:
    if isinstance(value, dict):
        return _url_segment(value, ctx)
    return render_segments(value, ctx)


def _r_attachment(value, field: FieldSpec, ctx: RenderContext) -> str:
    """The attachment **metadata** L1 reads — its ``name``. The ``url`` / ``tmp_url``
    are short-lived signed CDN links and never reach Markdown; the file bytes ship
    on their own hash-verified leg, ``larkdocio.base.media``, not through this cell
    renderer."""
    names = []
    for item in _as_list(value):
        if isinstance(item, dict):
            names.append(item.get("name") or item.get("file_token") or "")
        elif item is not None:
            names.append(str(item))
    return _MULTI_JOIN.join(n for n in names if n)


def _r_links(value, field: FieldSpec, ctx: RenderContext) -> str:
    """The **record ids** — unless a resolution is attached, and then the linked records.

    ``ctx.links`` is ``None`` on every default render, and ``None`` is byte-identical to what
    L1 always emitted: the ids, joined. With an opt-in
    :class:`~larkdocio.base.link_resolution.LinkResolution` attached, each id is replaced by
    whatever following it produced — the target's primary field, or the typed dangling /
    unresolved marker. **An id the resolution never saw still renders as itself**, because
    "not asked about" is not a finding.

    ``property.multiple: false`` is **not** a cardinality guarantee (AC8): a
    ``multiple:false`` SingleLink accepted and echoed two ids, ``code:0`` — so every id is
    rendered, never just the first, resolved or not.
    """
    ids = link_record_ids(value)
    if not ids:
        return ""
    resolution = ctx.links
    if resolution is None:
        return _MULTI_JOIN.join(str(i) for i in ids)
    target = (field.property or {}).get("table_id") if isinstance(field.property, dict) else None
    out = []
    for record_id in ids:
        text = resolution.text_for(target, str(record_id)) if target else None
        out.append(str(record_id) if text is None else text)
    return _MULTI_JOIN.join(out)


def _r_location(value, field: FieldSpec, ctx: RenderContext) -> str:
    if not isinstance(value, dict):
        return "" if value is None else str(value)
    text = value.get("full_address") or value.get("name") or value.get("location") or ""
    return ctx.md.render_inline([Text(text)]) if text else ""


def _r_typed_wrapper(value, field: FieldSpec, ctx: RenderContext) -> str:
    """A Formula (20) / Lookup (19) cell: ``{"type": N, "value": [ … ]}``.

    ``N`` is the **target / result** field's type — ``1`` for the specimen Lookup, not
    ``19`` — so the inner ``value`` dispatches on the **wrapper's** type. When that type
    is text-shaped the members are segments and join with ``""`` (their separators are
    already in the stream); otherwise they are scalars of that type.
    """
    inner = wrapper_type(value)
    if inner is None:
        # A bare legacy value (`GET …/records` returns `2` where search returns the
        # wrapper). Degrade rather than raise; `search` is the pinned read.
        return "" if value is None else str(value)
    members = value.get("value")
    if members is None:
        return ""
    if not isinstance(members, (list, tuple)):
        members = [members]
    if inner == 1 or any(isinstance(m, dict) for m in members):
        return render_segments(members, ctx)
    proxy = FieldSpec(
        field_name=field.field_name, type=inner,
        ui_type=_PRIMARY_UI_TYPE.get(inner, ""), property=field.property,
    )
    renderer = _RENDERERS.get(proxy.pair)
    if renderer is None:
        return _MULTI_JOIN.join(str(m) for m in members if m is not None)
    return _MULTI_JOIN.join(
        text for text in (renderer(m, proxy, ctx) for m in members) if text
    )


def _r_stage(value, field: FieldSpec, ctx: RenderContext) -> str:
    """Type 24 is OPAQUE — schema readable, value unreachable on 17 read routes, value
    unwritable. The marker renders whatever arrives (nothing ever does)."""
    return STAGE_OPAQUE_MARKER


def wrapper_type(value):
    """The ``type`` of a Formula / Lookup typed wrapper, or ``None`` if this is not one.

    ``None`` for a bare legacy value — which is exactly how a fixture pinned to the
    wrong read route announces itself.
    """
    if isinstance(value, dict) and "value" in value and "type" in value:
        return value.get("type")
    return None


#: For the typed-wrapper proxy: the ``ui_type`` a storage type renders as by default.
_PRIMARY_UI_TYPE = {
    1: "Text", 2: "Number", 3: "SingleSelect", 4: "MultiSelect", 5: "DateTime",
    7: "Checkbox", 11: "User", 13: "Phone", 15: "Url", 17: "Attachment",
    18: "SingleLink", 20: "Formula", 21: "DuplexLink", 22: "Location",
    23: "GroupChat", 24: "Stage", 1001: "CreatedTime", 1002: "ModifiedTime",
    1003: "CreatedUser", 1004: "ModifiedUser", 1005: "AutoNumber",
}


# --------------------------------------------------------------------------- #
# THE REGISTRY — 27 `(type, ui_type)` pairs                                    #
# --------------------------------------------------------------------------- #

#: One entry per evidenced ``(type, ui_type)``. Grouped as the maintainer's picker groups them
#: (Basic / Business / Advanced) so /BASE.md — in the source repository — and this table read in the
#: same order.
_RENDERERS = {
    # ── Basic ────────────────────────────────────────────────────────────────
    (1, "Text"): _r_segments,
    (3, "SingleSelect"): _r_single_select,
    (4, "MultiSelect"): _r_multi_select,
    (11, "User"): _r_persons,
    (23, "GroupChat"): _r_persons,
    (5, "DateTime"): _r_datetime,
    (17, "Attachment"): _r_attachment,
    (2, "Number"): _r_number,
    (7, "Checkbox"): _r_checkbox,
    (15, "Url"): _r_url,
    (20, "Formula"): _r_typed_wrapper,
    (19, "Lookup"): _r_typed_wrapper,
    # ── Business ─────────────────────────────────────────────────────────────
    (24, "Stage"): _r_stage,
    (1005, "AutoNumber"): _r_text_scalar,
    (13, "Phone"): _r_text_scalar,
    (1, "Email"): _r_segments,
    (22, "Location"): _r_location,
    (1, "Barcode"): _r_segments,
    (2, "Progress"): _r_number,
    (2, "Currency"): _r_currency,
    (2, "Rating"): _r_rating,
    # ── Advanced ─────────────────────────────────────────────────────────────
    (21, "DuplexLink"): _r_links,
    (18, "SingleLink"): _r_links,
    (1003, "CreatedUser"): _r_persons,
    (1004, "ModifiedUser"): _r_persons,
    (1001, "CreatedTime"): _r_datetime,
    (1002, "ModifiedTime"): _r_datetime,
}

#: Every dispatchable pair, in registry (picker) order. **27** — 28 picker types minus
#: Button, which is a maintainer-ruled WILL-NOT-SUPPORT. It *does* have a read identity
#: (``(3001, "Button")``, found live — BASE.md register row 13, in the source repository); it is
#: deliberately absent here, so it dispatches to nothing and the column renders blank.
PAIRS: Tuple[Tuple[int, str], ...] = tuple(_RENDERERS)

#: The one pair that renders a marker instead of a value.
OPAQUE_PAIRS: Tuple[Tuple[int, str], ...] = ((24, "Stage"),)

#: The **26** pairs that render an actual value.
VALUE_RENDERED_PAIRS: Tuple[Tuple[int, str], ...] = tuple(
    p for p in PAIRS if p not in OPAQUE_PAIRS
)

#: Pairs whose renderer emits its marker even when the key is ABSENT — i.e. the cell's
#: emptiness is not evidence of emptiness.
_ABSENT_MARKERS = {(24, "Stage"): STAGE_OPAQUE_MARKER}

#: Pairs whose ABSENT form is a real value rather than a blank. ``Checkbox`` false is an
#: absent key, so absent must render the unchecked box, not "unknown".
_ABSENT_VALUES = {(7, "Checkbox"): "[ ]"}


def renderer_for(type_: int, ui_type: str):
    """The renderer for a ``(type, ui_type)`` pair, or ``None`` if it is not registered."""
    return _RENDERERS.get((type_, ui_type))


def render_cell(value, field: FieldSpec, *, context: RenderContext = _DEFAULT_CONTEXT) -> str:
    """Render one Base cell to Markdown. Never raises on cell content.

    An unregistered pair degrades to ``str(value)`` — the reader's standing posture:
    surface *something* traceable rather than drop a column or crash a download.
    """
    renderer = _RENDERERS.get(field.pair)
    if renderer is None:
        return "" if value is None else str(value)
    return renderer(value, field, context)


def render_absent(field: FieldSpec, *, context: RenderContext = _DEFAULT_CONTEXT) -> str:
    """What a field renders when the record **omits its key** — the normal empty case.

    Not always ``""``: ``Checkbox`` false *is* an absent key, and ``Stage`` is absent
    from every read while its column may hold UI-set data (R14).
    """
    if field.pair in _ABSENT_MARKERS:
        return _ABSENT_MARKERS[field.pair]
    return _ABSENT_VALUES.get(field.pair, "")


def render_row(
    record_fields: dict,
    fields: Sequence[FieldSpec],
    *,
    context: RenderContext = _DEFAULT_CONTEXT,
) -> list:
    """One record → one cell per field, **in field order**.

    Projected against the **field list**, never against the record's own keys: no
    populated-but-empty field appears in a ``records/search`` record at all, so a
    union-of-observed-keys implementation silently drops columns and mis-aligns rows.
    """
    values = record_fields if isinstance(record_fields, dict) else {}
    out = []
    for spec in fields:
        if spec.field_name in values:
            out.append(render_cell(values[spec.field_name], spec, context=context))
        else:
            out.append(render_absent(spec, context=context))
    return out
