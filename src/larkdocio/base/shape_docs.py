"""What a Base cell TAKES and what it HANDS BACK — authored once, projected everywhere.

A Base cell's **write shape** and its **read-back shape** are frequently different objects, and
for a long time nothing in the shipped documentation said so per type: a link cell is written
as ``["recvra1g7Vj6RQ"]`` and reads back as ``{"link_record_ids": [...]}``, and that difference
surfaced only as a ``TypeError`` or a server refusal, never as a table. The library already
knew every answer — the encoders know what they take, the cell registry knows what comes back,
and each of them was measured from a captured round trip — it simply never told a reader holding
only the wheel.

**This module is the one author.** Every shape claim lives here exactly once, and every landing
of one in a document is a byte-identical projection of this module:

* :func:`raw_shape_markdown` regenerates *"The raw wire shape of every field type"* — the
  per-``(type, ui_type)`` read table, which lands in **two** documents (the consumer guide and
  the maintainer's Base matrix in the source repository). It shipped hand-kept in both, held together
  only by a test comparing the copies; it is now a projection, so the copies cannot disagree
  because there is nothing left to copy.
* :func:`cell_shape_markdown` renders the consumer section this module exists for: per field
  type, the shape you **write** beside the shape you **read back**, what the difference is, and
  whether the type can be written at all.

Nothing here is a fresh assertion. The read shapes and their captures are the table that already
shipped; the write shapes are one sentence per **encoder** in
:mod:`larkdocio.base.write_cells`, whose registry says which pairs are writable and whose
``CAPTURE_ANCHORS`` names the capture each shape was measured from; the reasons a type cannot be
written are :data:`~larkdocio.base.write_vocabulary.NON_WRITABLE_REASONS`; and the sharpest
asymmetries are quoted verbatim from the refusal messages the library already speaks. A pair no
registry can back renders :data:`SHAPE_NOT_ESTABLISHED` rather than a reasoned guess — an
honest gap is documentation, an invented shape is not.
"""
import json
import textwrap
from typing import Dict, NamedTuple, Optional, Tuple

from larkdocio.base import cells as _cells
from larkdocio.base import write_cells as _write_cells
from larkdocio.base.write_vocabulary import NON_WRITABLE_REASONS

# The filter vocabulary is authored ONCE in view_filters and READ here, never re-spelled: the
# shipped operator set, the valueless pair, the conjunctions and Lark's own longer enum are the
# same objects the serialiser enforces, so the projected reference cannot claim an operator the
# library does not actually ship.
from larkdocio.base.view_filters import (  # noqa: F401  (read for the filter-shape projection)
    CONJUNCTIONS,
    FILTER_OPERATORS,
    SERVER_VIEW_OPERATOR_ENUM,
    VALUELESS_OPERATORS,
)

# The four refusal sentences below are authored ONCE, in the encoder module, and spoken by the
# library when it refuses. They are quoted here, never restated: a reader who hits the refusal
# and a reader who reads the guide must meet the same words.
from larkdocio.base.write_cells import (  # noqa: F401  (re-exported for the projection)
    EMAIL_IS_NOT_ROUND_TRIPPABLE,
    TEXT_SEGMENT_ARRAY_IS_SERVER_REFUSED_TOO,
    _LOCATION_LITERAL,
    _PERSON_IDS_ONLY,
)

__all__ = [
    "ReadShape",
    "WriteShape",
    "FilterShape",
    "Attempt",
    "MeasuredRefusal",
    "MEASURED_REFUSALS",
    "READ_SHAPES",
    "WRITE_SHAPES",
    "WRITE_SHAPE_EXAMPLES",
    "write_shape_for",
    "FILTER_SHAPES",
    "SHAPE_NOT_ESTABLISHED",
    "RAW_REGION_BEGIN",
    "RAW_REGION_END",
    "RAW_REGENERATE",
    "CELL_SHAPE_REGION_BEGIN",
    "CELL_SHAPE_REGION_END",
    "CELL_SHAPE_REGENERATE",
    "FILTER_SHAPE_REGION_BEGIN",
    "FILTER_SHAPE_REGION_END",
    "FILTER_SHAPE_REGENERATE",
    "raw_shape_markdown",
    "cell_shape_markdown",
    "filter_shape_markdown",
]


class ReadShape(NamedTuple):
    """One ``(type, ui_type)`` pair's READ-BACK shape, as a capture measured it.

    ``shape`` is the literal a reader compares against; ``note`` is what the literal does not
    say on its own (and is empty when the literal says all of it). The two are kept apart so a
    short table can carry the shape and a long one can carry both — **one author, two
    verbosities**, rather than two authored sentences that can disagree.

    ``captures`` holds bare **filenames**, the same convention
    :data:`larkdocio.base.write_cells.CAPTURE_ANCHORS` keeps and for the same reason: a bare
    filename is a pointer, and the directory it sits under belongs to the sentence that says
    where that directory is.
    """

    ui_name: str
    shape: str
    note: str
    captures: Tuple[str, ...]

    @property
    def cell(self) -> str:
        """The read shape as the raw table prints it: the literal, then its note."""
        return f"{self.shape} — {self.note}" if self.note else self.shape


class WriteShape(NamedTuple):
    """One ENCODER's WRITE shape — what the caller passes, and what makes it different.

    Keyed by encoder rather than by pair on purpose: the encoder is what actually decides the
    shape, four pairs share one number encoder, and a pair enrolled against an existing encoder
    therefore documents itself.
    """

    shape: str
    note: str


#: What a row says when no landed encoder, renderer or capture establishes its shape. Rendered
#: rather than reasoned around: a sentence with no evidence behind it is worse than a gap, even
#: when it happens to be right.
SHAPE_NOT_ESTABLISHED = "shape not established"


class Attempt(NamedTuple):
    """One value actually SENT to a live route, and the answer it actually got.

    ``value`` is the literal from the capture, not a paraphrase of it, so the suite can hold the
    enumeration and the probe against each other **both ways**: a shape the probe sent and this
    list omits is evidence the reader cannot see, and a shape this list claims and the probe
    never sent is an invention.
    """

    value: object
    note: str
    answer: str


class MeasuredRefusal(NamedTuple):
    """A shape the **server itself** refused, with the edge of its own evidence attached.

    The distinction this type exists to keep visible: a refusal a library makes locally is a
    design decision and can be argued with; a refusal the platform makes is a fact, and the only
    honest thing to do with it is to say what was asked and what was not. So a record carries
    the routes it was observed on (never a class of routes), the control that makes the refusals
    attributable, every attempt, and the list of spellings **nobody tried** — which stay
    ``unmeasured`` rather than becoming ``cannot``.
    """

    question: str
    routes: Tuple[str, ...]
    control: str
    attempts: Tuple[Attempt, ...]
    not_tried: Tuple[str, ...]
    captures: Tuple[str, ...]


class RouteShape(NamedTuple):
    """**ONE route's** filter value shape, and the evidence for *that route*.

    The unit exists because of what happened without it (LD-403). A ``FilterShape`` used to carry
    one ``evidence`` label for both halves, so the Checkbox row's view claim — never probed —
    wore the **search** route's ``consumer-observed`` label, and the field refuted it with four
    ``1254001``s. A label is a claim about an observation, an observation happens on **one
    route**, and there is now no field on which a single label could stand for two.

    ``evidence`` is the verification label, the way the permissions registry carries one per
    scope: ``"captured"`` (a committed capture behind it), ``"measured"`` (a shipped round-trip
    test exercises it) or ``"consumer-observed"`` (observed working outside this project and
    not captured by this library — a weaker class, and the table says so). ``captures`` holds the
    bare filenames a ``"captured"`` half is backed by; every other class carries ``()``.
    """

    value: str
    evidence: str
    captures: Tuple[str, ...] = ()

    @classmethod
    def unestablished(cls) -> "RouteShape":
        """The honest half: a route this library has not observed says so, and claims nothing."""
        return cls(SHAPE_NOT_ESTABLISHED, "unmeasured", ())


class FilterShape(NamedTuple):
    """One field type's FILTER-CONDITION value shape — **two route halves, two evidences**.

    A filter condition's value CONTENT is what varies by field type — the wrapper the two routes
    put around it (a real array for the search route, a string carrying an array for the view
    route) is a route fact, stated once in the projection's preamble rather than repeated per
    row. ``search`` and ``view`` are **two distinct answers** because they genuinely differ: for
    a SELECT field the search route matches on the option NAME and the view route on the option
    ID (:data:`larkdocio.base.view_filters.SEARCH_ROUTE_TAKES_OPTION_NAME` /
    :data:`~larkdocio.base.view_filters.VIEW_ROUTE_REQUIRES_OPTION_ID`), and for a Checkbox the
    search route takes the string while the view route takes an unquoted JSON boolean
    (:data:`~larkdocio.base.view_filters.VIEW_ROUTE_CHECKBOX_TAKES_JSON_BOOLEANS`).

    **The rule this shape enforces structurally: an evidence label may never exceed the route it
    was observed on.** A half nothing observed is :meth:`RouteShape.unestablished`, not the other
    half's label repeated.
    """

    search: RouteShape
    view: RouteShape


# --------------------------------------------------------------------------- #
# THE READ COLUMN — one row per pair the cell registry renders, in its order.   #
# --------------------------------------------------------------------------- #

#: The shape ``record.raw(...)`` hands back, per ``(type, ui_type)``, each taken from a
#: committed capture rather than from prose. Held bidirectionally against
#: :data:`larkdocio.base.cells.PAIRS`.
READ_SHAPES: Dict[Tuple[int, str], ReadShape] = {
    (1, "Text"): ReadShape(
        ui_name="Text",
        shape='`[{"text": "row", "type": "text"}]`',
        note="a segment array, never a joined string",
        captures=("p1-q0-03-per-table.json",),
    ),
    (3, "SingleSelect"): ReadShape(
        ui_name="Single Option",
        shape='`"Alpha"`',
        note="a bare string, the option **name**",
        captures=("06-03-value-read-option-matrix.json",),
    ),
    (4, "MultiSelect"): ReadShape(
        ui_name="Multiple Options",
        shape='`["Red", "Green"]`',
        note="a list, in the order stored",
        captures=("06-03-value-read-option-matrix.json",),
    ),
    (11, "User"): ReadShape(
        ui_name="Person",
        shape='`[{"id": …, "name": …, "en_name": …, "email": …, "avatar_url": …}]`',
        note="the whole object, **id included**, which the render drops",
        captures=("ld256-01-person-write-shapes.json",),
    ),
    (23, "GroupChat"): ReadShape(
        ui_name="Group",
        shape='`[{"id": …, "name": …, "avatar_url": …}]`',
        note="",
        captures=("p0-4-04-value-readback.json",),
    ),
    (5, "DateTime"): ReadShape(
        ui_name="Date",
        shape="`1785061011000`",
        note="**ms epoch, an int**; no timezone is applied and none is implied",
        captures=("06-03-value-read-option-matrix.json",),
    ),
    (17, "Attachment"): ReadShape(
        ui_name="Attachment",
        shape=('`[{"file_token": …, "name": …, "size": 108, "type": …, "url": …, '
               '"tmp_url": …}]`'),
        note="the two URLs are short-lived signed links",
        captures=("p0-4-04-value-readback.json",),
    ),
    (2, "Number"): ReadShape(
        ui_name="Number",
        shape="`42.5`",
        note="the JSON number, unformatted",
        captures=("06-03-value-read-option-matrix.json",),
    ),
    (7, "Checkbox"): ReadShape(
        ui_name="Checkbox",
        shape="`true`",
        note="and **the key is absent when false**",
        captures=("06-03-value-read-option-matrix.json",
                  "06-02-record-create-echo.json"),
    ),
    (15, "Url"): ReadShape(
        ui_name="Link",
        shape='`{"link": …, "text": …, "type": "url"}`',
        note="",
        captures=("06-03-value-read-option-matrix.json",),
    ),
    (20, "Formula"): ReadShape(
        ui_name="Formula",
        shape='`{"type": 2, "value": [2]}`',
        note="a typed wrapper whose `type` is the **result** type",
        captures=("06-03-value-read-option-matrix.json",),
    ),
    (19, "Lookup"): ReadShape(
        ui_name="Lookup",
        shape='`{"type": 1, "value": [segments…]}`',
        note="the wrapper's `type` is the **target field's**",
        captures=("p1-q0-03-per-table.json",),
    ),
    (24, "Stage"): ReadShape(
        ui_name="Flow",
        shape="**nothing at all**",
        note=("the key is absent from every read route, so raw is silent exactly where the "
              "render carries its marker"),
        captures=("p1-q1-02-stage-read-routes.json",),
    ),
    (1005, "AutoNumber"): ReadShape(
        ui_name="Numbering",
        shape='`"1"`',
        note="a **string**, not an int",
        captures=("p0-5-01-scalar-read-encodings.json",),
    ),
    (13, "Phone"): ReadShape(
        ui_name="Phone Number",
        shape='`"+12025550100"`',
        note="a bare string",
        captures=("06-03-value-read-option-matrix.json",),
    ),
    (1, "Email"): ReadShape(
        ui_name="Email",
        shape='`[{"link": "mailto:…", "text": "…", "type": "url"}]`',
        note=("the address **twice**, prefixed and plain: comparing the rendered form is how "
              "one address in two shapes reads as two vendors"),
        captures=("p1-q0-03-per-table.json",),
    ),
    (22, "Location"): ReadShape(
        ui_name="Location",
        shape=('`{"location": "103.8198,1.3521", "full_address": …, "pname": …, '
               '"cityname": …, "adname": …, "address": …, "name": …}`'),
        note="",
        captures=("p0-4-04-value-readback.json",),
    ),
    (1, "Barcode"): ReadShape(
        ui_name="Barcode",
        shape='`[{"text": "BC-9", "type": "text"}]`',
        note="a segment array, same as Text",
        captures=("p0-5-01-scalar-read-encodings.json",),
    ),
    (2, "Progress"): ReadShape(
        ui_name="Progress",
        shape="`0.35`",
        note="the fraction, not the rendered percent",
        captures=("p0-5-01-scalar-read-encodings.json",),
    ),
    (2, "Currency"): ReadShape(
        ui_name="Currency",
        shape="`12.5`",
        note="no code and no symbol; those live on the field",
        captures=("p0-5-01-scalar-read-encodings.json",),
    ),
    (2, "Rating"): ReadShape(
        ui_name="Rating",
        shape="`4`",
        note="an int, no glyph",
        captures=("p0-5-01-scalar-read-encodings.json",),
    ),
    (21, "DuplexLink"): ReadShape(
        ui_name="Two-way Link",
        shape='`{"link_record_ids": ["rec…"]}`',
        note=("an **object**; `null` means never written and `[]` means emptied by a delete, "
              "and raw keeps them apart"),
        captures=("p0-2-05-link-lookup-read-encodings.json",),
    ),
    (18, "SingleLink"): ReadShape(
        ui_name="One-way Link",
        shape="the same object shape",
        note="",
        captures=("p0-2-05-link-lookup-read-encodings.json",),
    ),
    (1003, "CreatedUser"): ReadShape(
        ui_name="Created By",
        shape="`[{person}]`",
        note="the same object shape as Person",
        captures=("05-07-record-read-option-matrix.json",),
    ),
    (1004, "ModifiedUser"): ReadShape(
        ui_name="Modified By",
        shape="`[{person}]`",
        note="",
        captures=("p0-5-01-scalar-read-encodings.json",),
    ),
    (1001, "CreatedTime"): ReadShape(
        ui_name="Date Created",
        shape="`1785693438000`",
        note="ms epoch, an int",
        captures=("05-07-record-read-option-matrix.json",),
    ),
    (1002, "ModifiedTime"): ReadShape(
        ui_name="Last Modified Date",
        shape="`1785693462000`",
        note="ms epoch, an int",
        captures=("05-07-record-read-option-matrix.json",),
    ),
}


# --------------------------------------------------------------------------- #
# THE WRITE COLUMN — one sentence per ENCODER, held against the registry.       #
# --------------------------------------------------------------------------- #

#: What each encoder in :data:`larkdocio.base.write_cells._ENCODERS` takes. Keyed by the
#: encoder's own name, so enrolling a pair against an existing encoder documents itself and a
#: NEW encoder with no sentence reddens the suite.
WRITE_SHAPES: Dict[str, WriteShape] = {
    "_e_plain_string": WriteShape(
        shape='`"row"`',
        note=("the bare string itself — the segment array is the READ shape and is refused "
              "rather than unwrapped, because unwrapping it would be a guess about which "
              "member carried the value"),
    ),
    "_e_email": WriteShape(
        shape='`"ada@example.com"`',
        note=("the address as a plain string; Lark synthesizes the `mailto:` prefix and the "
              "segment wrapper server-side, so what comes back is not what went in"),
    ),
    "_e_option_name": WriteShape(
        shape='`"Alpha"`',
        note="one option **name**, as a bare string — the same shape a read hands back",
    ),
    "_e_option_names": WriteShape(
        shape='`["Red", "Green"]`',
        note=("a **list** of option names; a bare string is refused rather than wrapped, "
              "since a one-option write is one character away"),
    ),
    "_e_ms_epoch": WriteShape(
        shape="`1785061011000`",
        note=("milliseconds since the epoch, as an `int` — no date object is converted, "
              "because every conversion needs a zone and this library will not choose one"),
    ),
    "_e_bool": WriteShape(
        shape="`True`",
        note=("a boolean; `False` is a real write that simply **reads back as an absent "
              "key**"),
    ),
    "_e_number": WriteShape(
        shape="`42.5`",
        note=("a JSON number; the formatter, the currency code and the rating symbol live on "
              "the field's own configuration, never in the value"),
    ),
    "_e_url_object": WriteShape(
        shape='`{"link": …, "text": …}`',
        note=("**without** the read shape's third `type` key; a bare string is accepted and "
              "taken as a link that labels itself"),
    ),
    "_e_attachments": WriteShape(
        shape='`[{"file_token": …}]`',
        note=("tokens only — a bare list of tokens is accepted here and wrapped, because the "
              "server refuses one; the name, size and the two signed URLs a read carries are "
              "not write inputs"),
    ),
    "_e_link_ids": WriteShape(
        shape='`["rec…"]`',
        note=('a **bare list** of record ids, not an object: the read shape '
              '`{"link_record_ids": […]}` is refused rather than unwrapped, which is what '
              "keeps the asymmetry visible where it bites"),
    ),
    "_e_location": WriteShape(
        shape='`"103.8198,1.3521"`',
        note=("the literal coordinate string, **longitude first** — an address, or the object "
              "a read returns, is refused"),
    ),
    "_e_chat_ids": WriteShape(
        shape='`[{"id": …}]`',
        note=("objects, not bare ids — a bare list is accepted here and wrapped, because the "
              "server refuses one"),
    ),
    "_e_person_ids": WriteShape(
        shape='`[{"id": <open_id>}]`',
        note=("**ids only**; everything else a read hands back — the display names, the "
              "address, the avatar link — is not a write input, and a display name is not an "
              "id"),
    ),
}

#: LD-441 — the per-PAIR write **example**, where a shared encoder's single example would
#: describe another pair's value. Only the example is overridden; the encoder's note is the
#: rule and stays shared.
#:
#: Two encoders serve several pairs each: ``_e_plain_string`` (Text / Phone / Barcode) and
#: ``_e_number`` (Number / Progress / Currency / Rating). Without this, the Phone row read
#: *write* ``"row"`` → *read back* ``"+12025550100"``, and the Rating row *write* ``42.5`` →
#: *read back* ``4`` — two columns describing two different values, which is the one thing
#: the table exists to line up. Each example is the same literal that pair's READ shape was
#: captured with, so the row is a real round trip rather than two plausible strings.
WRITE_SHAPE_EXAMPLES: Dict[Tuple[int, str], str] = {
    (13, "Phone"): '`"+12025550100"`',
    (1, "Barcode"): '`"BC-9"`',
    (2, "Progress"): "`0.35`",
    (2, "Currency"): "`12.5`",
    (2, "Rating"): "`4`",
}


# --------------------------------------------------------------------------- #
# THE FILTER-CONDITION COLUMN — per field type, the value each route matches on. #
# --------------------------------------------------------------------------- #

#: The per-field-type filter VALUE CONTENT, only where evidence establishes it. Every entry is
#: backed by a committed capture, a shipped round-trip test, or an explicitly consumer-observed
#: report; a type absent from this dict renders :data:`SHAPE_NOT_ESTABLISHED` on both routes
#: rather than a guess. The operator vocabulary is not a column here because it is a **route**
#: fact — the six are shared between the two routes (measured on a Text field) and are projected
#: once from :data:`larkdocio.base.view_filters.FILTER_OPERATORS`. Where a field TYPE was
#: measured to accept fewer, the row itself says so and the refusal is
#: :data:`~larkdocio.base.view_filters.VIEW_ROUTE_CHECKBOX_OPERATOR_SCOPE`'s to make.
FILTER_SHAPES: Dict[Tuple[int, str], FilterShape] = {
    (1, "Text"): FilterShape(
        search=RouteShape(
            value='the text you match on, e.g. `"Text 1"`',
            evidence="captured",
            captures=("p1-q3-01-filter-sort.json",),
        ),
        view=RouteShape(
            value="the same text",
            evidence="captured",
            captures=("ld403-01-checkbox-view-filter.json",),
        ),
    ),
    (3, "SingleSelect"): FilterShape(
        search=RouteShape(
            value='the option **name** (e.g. `"Done"`)',
            evidence="measured",
        ),
        view=RouteShape(
            value=("the option **id** (`opt…`) — `FieldRegistry.resolve()` translates a name "
                   "into its id for you, and refuses an unknown one naming the options that "
                   "exist"),
            evidence="measured",
        ),
    ),
    (4, "MultiSelect"): FilterShape(
        search=RouteShape(
            value=("each selected option's **name**; the SingleSelect half is the one proven "
                   "live and MultiSelect rides the identical path"),
            evidence="measured",
        ),
        view=RouteShape(
            value=("each option's **id** (`opt…`), resolved the same way; the SingleSelect half "
                   "is the one proven live and MultiSelect rides the identical path"),
            evidence="measured",
        ),
    ),
    (7, "Checkbox"): FilterShape(
        search=RouteShape(
            value=('the boolean, which this library sends as the string `"True"` — `("is", '
                   '(True,))`; `"true"` and `"1"` were accepted too, so this route is the '
                   "lenient one"),
            evidence="captured",
            captures=("ld403-01-checkbox-view-filter.json",),
        ),
        view=RouteShape(
            value=("ONE **unquoted JSON boolean** inside the array — `[true]` — which is what "
                   '`("is", (True,))` now serialises to. Every QUOTED spelling is refused '
                   '(`["true"]`, `["True"]`, `["1"]` and six more all answer `1254001`), as are '
                   "both valueless operators (which a text field takes) and `isNot` even "
                   "carrying the accepted value; a two-element array answers `code:0` and is "
                   "stored as its first element alone, so the read-back does not echo"),
            evidence="captured",
            captures=("ld403-01-checkbox-view-filter.json",
                      "ld403-02-checkbox-shipped-path.json"),
        ),
    ),
}

#: The verification labels a **route half** may carry, and the one that needs a capture on disk.
#: Held here so the guard and the renderer agree on the vocabulary rather than each spelling it.
#: ``unmeasured`` is the honest half — see :meth:`RouteShape.unestablished`.
FILTER_EVIDENCE_CLASSES: Tuple[str, ...] = (
    "captured", "measured", "consumer-observed", "unmeasured")

#: **The rule LD-403 pinned, authored once and projected.** It is stated in the consumer's own
#: document because the reader of a shape table is exactly the person a route-spanning label
#: misled: they read one cell and act on it.
EVIDENCE_IS_ROUTE_SCOPED = (
    "Each route half carries its OWN evidence label, and a label never covers the other route. "
    "That is not a formatting choice: this table once said a Checkbox view-route condition "
    "matched on \"the same boolean\" as the search route, on the strength of a SEARCH-route "
    "observation, and the view route refused every quoted spelling of it. So a half nobody has "
    "observed reads `shape not established` rather than borrowing the other half's proof."
)


#: The pairs whose two shapes differ sharply enough that meeting the difference at runtime is
#: expensive, each with the sentence the library **already speaks** when it refuses (or ``""``
#: when the two shape notes above already say it). Quoted, never restated.
_ASYMMETRIES: Tuple[Tuple[Tuple[int, str], str, str], ...] = (
    ((1, "Email"), "Email — you cannot round-trip what you read",
     EMAIL_IS_NOT_ROUND_TRIPPABLE),
    ((1, "Text"), "Text — a string goes in, a segment array comes out",
     TEXT_SEGMENT_ARRAY_IS_SERVER_REFUSED_TOO),
    ((21, "DuplexLink"), "Link — a list goes in, an object comes out", ""),
    ((22, "Location"), "Location — a coordinate string goes in, a geocoded object comes out",
     _LOCATION_LITERAL),
    ((11, "User"), "Person — ids go in, whole people come out", _PERSON_IDS_ONLY),
)


#: The link and label the LD-416 probe sent, so the enumeration below and the capture on disk
#: carry the same literals rather than two typings of them.
_LD416_LINK = "https://example.com/example-link"
_LD416_LABEL = "Example Link"

#: **The refusals the SERVER made, per pair — enumerated, so the reader can see the edge.**
#: Keyed by pair rather than by encoder (the way :data:`WRITE_SHAPES` is keyed) precisely
#: because a measurement belongs to what was measured: three pairs share the plain-string
#: encoder and exactly one of them was probed, so an encoder-keyed record would put a claim
#: on two pairs nobody asked about.
MEASURED_REFUSALS: Dict[Tuple[int, str], MeasuredRefusal] = {
    (1, "Text"): MeasuredRefusal(
        question=("Can a Text cell be WRITTEN as the segment array it reads back as — the "
                  "labeled clickable link, where the visible words are the link and no URL "
                  "shows?"),
        routes=("POST …/records (create one record)",
                "PUT …/records/{record_id} (update one record)"),
        control=("the bare string, sent through the same harness in the same run, answered "
                 "code:0 on both routes and read back as a segment array"),
        attempts=(
            Attempt([{"type": "url", "text": _LD416_LABEL, "link": _LD416_LINK}],
                    "one url segment and nothing else — the label-is-the-link cell",
                    "1254060 TextFieldConvFail"),
            Attempt([{"type": "text", "text": "see "},
                     {"type": "url", "text": _LD416_LABEL, "link": _LD416_LINK},
                     {"type": "text", "text": " for detail"}],
                    "text before and after a url segment",
                    "1254060 TextFieldConvFail"),
            Attempt([{"text": "see "},
                     {"link": _LD416_LINK, "text": _LD416_LABEL, "type": "url"},
                     {"text": " for detail"}],
                    "the same, spelled the way a read-back prints it — key order link/text/"
                    "type, and the text segments carrying no type key",
                    "1254060 TextFieldConvFail"),
            Attempt([{"type": "url", "text": _LD416_LABEL, "link": _LD416_LINK},
                     {"type": "text", "text": " — see above"}],
                    "url first, text last",
                    "1254060 TextFieldConvFail"),
            Attempt([{"type": "text", "text": "plain words"}],
                    "the degenerate case — an array of nothing but text",
                    "1254060 TextFieldConvFail"),
            Attempt([{"type": "url", "text": _LD416_LABEL}],
                    "malformed on purpose: a url segment with no link",
                    "1254060 TextFieldConvFail"),
            Attempt([{"type": "url", "text": _LD416_LABEL, "link": ""}],
                    "the same omission spelled as an empty string",
                    "1254060 TextFieldConvFail"),
            Attempt([{"text": _LD416_LABEL, "link": _LD416_LINK}],
                    "link and text with the kind unstated",
                    "1254060 TextFieldConvFail"),
            Attempt({"type": "url", "text": _LD416_LABEL, "link": _LD416_LINK},
                    "the single segment unwrapped out of its list",
                    "1254060 TextFieldConvFail"),
            Attempt([{"type": "url", "text": "", "link": _LD416_LINK}],
                    "no label at all — would the server substitute the link?",
                    "1254060 TextFieldConvFail"),
            Attempt([{"type": "url", "text": _LD416_LABEL,
                      "link": "mailto:nobody@example.invalid"}],
                    "a scheme the platform synthesizes itself on an Email cell",
                    "1254060 TextFieldConvFail"),
            Attempt([{"type": "url", "text": _LD416_LABEL, "link": "example.com/example-link"}],
                    "no scheme — the shape a human pastes",
                    "1254060 TextFieldConvFail"),
            Attempt([{"type": "mention", "text": "@nobody"}],
                    "a segment kind no write shape claims — is the type token validated?",
                    "1254060 TextFieldConvFail"),
            Attempt([], "the empty array — a clear, an empty string, or a refusal?",
                    "1254060 TextFieldConvFail"),
        ),
        not_tried=(
            "the BATCH record route `records/batch_update` — its sibling `records/batch_create` "
            "**was** asked, once, with the doc-mention chip a Base cell reads back after a human "
            "touches a pasted document url, and answered `1254060 TextFieldConvFail` like the "
            "two routes above, so the refusal is not a property of the single-record routes; "
            "`batch_update` itself remains unasked",
            "cell values seeded at TABLE-CREATION time",
            "any field type other than `1 / Text` — Phone and Barcode share the write rule and "
            "were deliberately left out of the question",
            "segment arrays longer than three members, and nested arrays",
            "a url segment carrying extra unrecognized keys beside link / text / type",
        ),
        captures=("ld416-01-text-url-segment-write.json",),
    ),
}


# --------------------------------------------------------------------------- #
# THE DOCUMENT PROJECTIONS — the registries write the documents, never the      #
# reverse. Every region is byte-checked against these renders, so a shape       #
# cannot be edited into a document and disagree with the code.                  #
# --------------------------------------------------------------------------- #

#: The fence around the read-shape table, which lands in two documents.
RAW_REGION_BEGIN = "<!-- BEGIN BASE-RAW-SHAPES (generated -->"
RAW_REGION_END = "<!-- END BASE-RAW-SHAPES -->"

#: The fence around the consumer's write-beside-read section.
CELL_SHAPE_REGION_BEGIN = "<!-- BEGIN BASE-CELL-SHAPES (generated -->"
CELL_SHAPE_REGION_END = "<!-- END BASE-CELL-SHAPES -->"

#: The fence around the per-type filter-condition shape section — the third sibling.
FILTER_SHAPE_REGION_BEGIN = "<!-- BEGIN BASE-FILTER-SHAPES (generated -->"
FILTER_SHAPE_REGION_END = "<!-- END BASE-FILTER-SHAPES -->"

#: The one-liner that regenerates a region, quoted into the region's own header so the
#: instruction cannot drift away from the thing it regenerates.
RAW_REGENERATE = (
    'python -c "from larkdocio.base.shape_docs import raw_shape_markdown as m; print(m())"'
)
CELL_SHAPE_REGENERATE = (
    'python -c "from larkdocio.base.shape_docs import cell_shape_markdown as m; print(m())"'
)
FILTER_SHAPE_REGENERATE = (
    'python -c "from larkdocio.base.shape_docs import filter_shape_markdown as m; print(m())"'
)

#: The label the guide already uses for a path a wheel-only reader cannot open. It goes into
#: the projections themselves, not into a hand-kept sentence beside them, so a reader can never
#: meet a capture path without being told first where those files live. The captures are
#: ``tests/captures/…``, which every clone carries, so it is the SOURCE-repository label
#: (``larkdocio.common.citations.SOURCE_REPO_LABEL``). The name is kept so the projections' call sites stay put.
_DEV_REPO_LABEL = "in the source repository"

#: The directory the captures sit in — a bare composition fragment, joined onto the filenames
#: the registry stores. Labelling a fragment would put the label in the middle of a path; the
#: sentence that carries the label is rendered into the same region, one line above the table.
_CAPTURE_DIR = "tests/captures/base-study/captures"


def _capture_cell(names) -> str:
    """The capture column for one row: each stored filename under :data:`_CAPTURE_DIR`."""
    cells = []
    for name in names:
        path = "/".join((_CAPTURE_DIR, name))
        cells.append(f"`{path}`")
    return " · ".join(cells)


def _documented_pairs() -> Tuple[Tuple[int, str], ...]:
    """Every pair either registry knows, in the read registry's order.

    The read registry leads because its order is the field picker's, which is what lets one row
    say *"the same object shape"* and mean the row above it. A pair the WRITE registry gained
    and the read registry has not is appended rather than dropped — a row stating what is not
    established beats a silent omission.
    """
    read = tuple(_cells.PAIRS)
    return read + tuple(p for p in _write_cells.WRITABLE_PAIRS if p not in read)


def _ui_name(pair) -> str:
    read = READ_SHAPES.get(pair)
    return read.ui_name if read else pair[1]


def write_shape_for(pair) -> Optional[WriteShape]:
    """The write shape a PAIR shows — the encoder's sentence, with the pair's own **example**.

    LD-441. Keying :data:`WRITE_SHAPES` by encoder is right and unchanged: the encoder is what
    decides the shape, and one sentence for all its pairs is what keeps a shared rule from
    drifting into two copies. What that keying cannot carry is the *example*, and the table's
    contract is the shape you WRITE beside the shape you READ BACK **for the same value** —
    so ``13 / Phone`` rendered as *write* ``"row"`` → *read back* ``"+12025550100"``, which is
    a round trip of nothing. :data:`WRITE_SHAPE_EXAMPLES` overrides the example only; the note
    stays the encoder's.
    """
    encoder = _write_cells.encoder_for(*pair)
    authored = WRITE_SHAPES.get(getattr(encoder, "__name__", ""))
    if authored is None:
        return None
    example = WRITE_SHAPE_EXAMPLES.get(pair)
    return authored if example is None else authored._replace(shape=example)


def _write_cell(pair) -> Tuple[str, str]:
    """``(shape, note)`` for a pair's write side — or why it has none."""
    if pair in _write_cells.WRITABLE_PAIRS:
        authored = write_shape_for(pair)
        if authored is None:
            return "—", SHAPE_NOT_ESTABLISHED
        return authored.shape, authored.note
    reason = NON_WRITABLE_REASONS.get(pair)
    return "—", reason or SHAPE_NOT_ESTABLISHED


def _measured_refusal_lines(pair) -> list:
    """The enumerated server refusal for one pair — or nothing, for a pair nobody probed.

    Rendered **under the pair's own callout** rather than in a section of its own, because the
    reader who needs it is the one already reading about that type's asymmetry, and a claim
    floating free of its pair is exactly how one pair's measurement becomes another's.
    """
    record = MEASURED_REFUSALS.get(pair)
    if record is None:
        return []
    routes = " and ".join(f"`{route}`" for route in record.routes)
    lines = [
        "",
        f"*What was actually asked, and what was not.* {record.question} It was put to "
        f"{routes} — and {record.control}. Every shape below came back the same way:",
        "",
        "| The value sent | What Lark answered |",
        "|---|---|",
    ]
    for attempt in record.attempts:
        literal = json.dumps(attempt.value, ensure_ascii=False)
        lines.append(f"| `{literal}` — {attempt.note} | `{attempt.answer}` |")
    lines += [
        "",
        "**Not tried, and therefore UNMEASURED rather than refused** — "
        + "; ".join(record.not_tried) + ". A spelling nobody sent is an open question, not a "
        "closed one, and this list is here so you can see which is which.",
    ]
    return lines


def raw_shape_markdown() -> str:
    """*"The raw wire shape of every field type"* — the READ table, generated.

    One row per ``(type, ui_type)`` pair the cell registry renders, in the registry's order,
    each shape carrying the capture it was measured from. This table lands in two documents;
    both landings are this render, so the two cannot drift apart.
    """
    lines = [
        RAW_REGION_BEGIN.replace(" -->", ""),
        f"     regenerate with:  {RAW_REGENERATE}  -->",
        "",
        "One row per `(type, ui_type)` pair the cell registry renders, each shape taken from a "
        "committed",
        f"capture rather than from prose. The capture files below live **{_DEV_REPO_LABEL}**.",
        "",
        "| API identity | UI name | What `raw` hands you | Capture it was read from |",
        "|---|---|---|---|",
    ]
    for pair in _cells.PAIRS:
        read = READ_SHAPES.get(pair)
        if read is None:
            lines.append(
                f"| `{pair[0]} / {pair[1]}` | {pair[1]} | {SHAPE_NOT_ESTABLISHED} | — |")
            continue
        lines.append(
            f"| `{pair[0]} / {pair[1]}` | {read.ui_name} | {read.cell} "
            f"| {_capture_cell(read.captures)} |")
    lines += ["", RAW_REGION_END]
    return "\n".join(lines)


def cell_shape_markdown() -> str:
    """The consumer section: the shape you WRITE beside the shape you READ BACK.

    Five columns, one row per field type, in the field picker's order: what it is, whether you
    can write it at all, the two shapes, and — the column the table exists for — what the
    difference between them is. Below the table, the handful of types whose two shapes differ
    sharply enough to cost an afternoon are called out by name, each quoting the sentence the
    library itself says when it refuses the wrong one.
    """
    lines = [
        CELL_SHAPE_REGION_BEGIN.replace(" -->", ""),
        f"     regenerate with:  {CELL_SHAPE_REGENERATE}  -->",
        "",
        "| Field type | Writable? | The shape you WRITE | The shape you READ BACK "
        "| What the difference is |",
        "|---|---|---|---|---|",
    ]
    for pair in _documented_pairs():
        writable = pair in _write_cells.WRITABLE_PAIRS
        write_shape, write_note = _write_cell(pair)
        read = READ_SHAPES.get(pair)
        read_shape = read.shape if read else SHAPE_NOT_ESTABLISHED
        answer = "yes" if writable else "**not writable**"
        lines.append(
            f"| `{pair[0]} / {pair[1]}` · {_ui_name(pair)} | {answer} | {write_shape} "
            f"| {read_shape} | {write_note} |")
    lines += [
        "",
        "**Where the two shapes differ enough to cost you an afternoon.** Each of these is a "
        "refusal the library makes locally, before anything is sent — so the words below are "
        "the words you will read in the exception, not a paraphrase of them.",
    ]
    for pair, title, spoken in _ASYMMETRIES:
        write_shape, write_note = _write_cell(pair)
        read = READ_SHAPES.get(pair)
        read_shape = read.shape if read else SHAPE_NOT_ESTABLISHED
        lines += [
            "",
            f"**{title}.** You write {write_shape}; you read back {read_shape} — "
            f"{write_note.rstrip('.')}.",
        ]
        if spoken:
            lines += ["", "```text", *textwrap.wrap(spoken, width=94), "```"]
        lines += _measured_refusal_lines(pair)
    lines += [
        "",
        "**Every shape above was measured, not reasoned out.** Each write shape is the one a "
        "captured round trip stored and read back, and each read shape is the one a captured "
        f"read returned; the capture files themselves live {_DEV_REPO_LABEL} and the "
        "library's own tests resolve every one of them, so a shape here that nothing measured "
        "cannot ship.",
        "",
        CELL_SHAPE_REGION_END,
    ]
    return "\n".join(lines)


def filter_shape_markdown() -> str:
    """The per-field-type FILTER-CONDITION shape — the third sibling of the two tables above.

    A Base filter is described once and serialised for one of two routes, and the two routes key
    a condition — and, for a SELECT field, its value — differently. The operator vocabulary,
    valueless pair, conjunctions and Lark's own longer enum are all READ from
    :mod:`larkdocio.base.view_filters` (never re-spelled), and stated once because they are a
    ROUTE fact — shared between the two routes, measured on a Text field. Per-TYPE acceptance is
    a separate question and is claimed only where a row answers it (LD-408): the preamble names
    the one measured exception rather than generalising over every type. The table is the VALUE
    CONTENT, filled only where evidence
    establishes it: a type with no measured filter value renders :data:`SHAPE_NOT_ESTABLISHED`
    rather than the guess the consumer had to make.
    """
    ops = ", ".join(f"`{op}`" for op in FILTER_OPERATORS)
    valueless = " / ".join(f"`{op}`" for op in VALUELESS_OPERATORS)
    conj = " / ".join(f"`{c}`" for c in CONJUNCTIONS)
    lines = [
        FILTER_SHAPE_REGION_BEGIN.replace(" -->", ""),
        f"     regenerate with:  {FILTER_SHAPE_REGENERATE}  -->",
        "",
        "A Base filter is described **once** — a `FilterSpec` of `Condition`s — and serialised "
        "for one of two routes, which key a condition differently and, for a SELECT field, key "
        "its VALUE differently too (that last part is the one that costs an afternoon):",
        "",
        "* **The search route** filters the rows one read returns. It keys a condition by the "
        "field's **name**, and carries the value as a **real JSON array**.",
        "* **The view route** filters the rows a person sees when they open the view. It keys a "
        "condition by the field's **id**, and carries the value as a **string containing** a "
        f"JSON array; a valueless operator ({valueless}) OMITS the value key entirely there.",
        "",
        f"**The operator vocabulary is shared BETWEEN THE TWO ROUTES:** {ops} — the six a "
        f"capture proved on both routes, on a **Text field** — with conditions joined by "
        f"{conj}. That is a claim about the two ROUTES and nothing more: **which operators a "
        "given field TYPE accepts is claimed only where a row below says so**, and one row "
        "already says otherwise — a `7 / Checkbox` condition on the **view** route was measured "
        "to take only `is`, with `isNot`, `contains`, `isEmpty` and `isNotEmpty` each answering "
        "`1254001`. `FieldRegistry.resolve()` refuses those four locally, before any call. "
        f'Lark\'s own view-route list is longer — "{SERVER_VIEW_OPERATOR_ENUM}" — but the four '
        "comparison operators in it are **not shipped and are not implied by any row below**: "
        "no capture shows one working, and the one that was tried answered `1254018` on a text "
        "field.",
        "",
        "The table is the value **CONTENT** per field type — what goes inside whichever wrapper "
        "the route puts around it. A type with no measured filter value reads "
        f"**{SHAPE_NOT_ESTABLISHED}** rather than a guess.",
        "",
        f"**{EVIDENCE_IS_ROUTE_SCOPED}**",
        "",
        "| Field type | Search route matches on (by name) | How we know (search) "
        "| View route matches on (by id) | How we know (view) |",
        "|---|---|---|---|---|",
    ]
    for pair in _documented_pairs():
        shape = FILTER_SHAPES.get(pair)
        if shape is None:
            shape = FilterShape(search=RouteShape.unestablished(),
                                view=RouteShape.unestablished())
        lines.append(
            f"| `{pair[0]} / {pair[1]}` · {_ui_name(pair)} | {shape.search.value} "
            f"| {shape.search.evidence} | {shape.view.value} | {shape.view.evidence} |")
    lines += [
        "",
        "**Every value form above was measured or is labelled by its evidence, never guessed.** The "
        f"captures and the shipped round-trip tests behind the `captured` and `measured` halves "
        f"live {_DEV_REPO_LABEL}; a `consumer-observed` half is a shape observed working "
        "outside this project that this library has not itself captured, and an `unmeasured` one is a route "
        "nobody has asked at all. Each says which it is rather than presenting itself as "
        "proven — which is exactly the difference that lets you plan against what is not yet "
        "established.",
        "",
        FILTER_SHAPE_REGION_END,
    ]
    return "\n".join(lines)
