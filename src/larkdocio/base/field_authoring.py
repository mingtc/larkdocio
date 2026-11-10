"""larkdocio.base.field_authoring — the CAPTURED shapes a column is authored from.

**A `property` shape nobody captured is a guess, and a guess authors the wrong column.** The
fields API takes a `property` object whose contents differ per column kind, and the differences
are not derivable from the type number: ``Location`` nests under ``property.location.input_type``,
``Currency`` uses ``property.currency_code``, ``Rating`` uses ``property.rating.symbol``, and
``Phone``'s ``ui_type`` is **``Phone``** — a create asking for ``PhoneNumber`` is refused
``99992402``. Every shape in :data:`FIELD_PROPERTY_SHAPES` is transcribed from a **committed
capture**, and each carries the capture's own filename so a reader can check it in one step.

**Those nested shapes are what goes ON THE WIRE, not what a caller writes.** Every key is
passed **flat** to :func:`build_property`, which does the nesting; a shape's
:attr:`FieldPropertyShape.call_shape` says that in the shape's own voice, generated from its
``keys`` so the sentence and the tuple cannot drift apart.

**A key no shape carries is REFUSED, never sent.** The Base API silently ignores body keys it
does not recognise (the bogus-key control ``{"zzz": 1}`` behaves exactly like four plausible
grouping keys), so a request carrying an invented key would answer ``code:0`` and author a
column missing the thing that was asked for. The refusal happens here, locally, before a client
is touched.

**Conversion is a PAIR TABLE keyed on evidence.** Changing a column's kind is a column-wide,
server-side, undo-less transformation of every value in it. Exactly one pair has been observed
end to end — ``Text (1) → Barcode (1)``, same storage type, the cells intact — so exactly one
pair is enabled. Every other pair is refused **locally, with zero transport calls**, as
:class:`UncapturedConversionError`. Cross-storage-type conversions are out entirely: no capture
shows whether Lark coerces the values, blanks them, or refuses, and a library that guessed on a
caller's behalf would be a data-loss weapon with a friendly name.

**Creating a ``DuplexLink`` creates a SECOND FIELD IN ANOTHER TABLE.** One call, two columns —
the mirror lands in the target table named ``<source table>-<source field>`` with
``back_field_id`` pointing home. That is a cross-table create the caller never asked for, so the
plan discloses it in the dry run, before it happens.
"""
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from lark_oapi.api.bitable.v1 import (
    AppFieldPropertyLocation,
    AppTableFieldProperty,
    AppTableFieldPropertyOption,
    Rating,
)

from larkdocio.base.errors import BASE_ERROR_CODES
from larkdocio.base.field_vocabulary import AUTHORABLE_UI_TYPES
from larkdocio.common.citations import DEV_REPO_LABEL, dev_repo
from larkdocio.errors import LarkConfigError

_CAPTURES = "tests/captures/base-study/captures"


class FieldAuthoringRefusal(LarkConfigError, ValueError):
    """A field-authoring request refused **locally, before any call**.

    Deliberately its own family, beside — not under —
    :class:`larkdocio.base.field_vocabulary.UnauthorableFieldError`: that one answers *"Lark
    will not author this column kind at all"*, and these answer *"this library has no evidence
    for the shape you asked for"*. Two different refusals with two different fixes.

    Both families do sit under :class:`~larkdocio.errors.LarkConfigError`, so
    ``except LarkConfigError`` / ``except LarkDocIOError`` catch either — being *beside* is
    about which refusal a caller reads, not about escaping the toolkit's one base.
    ``ValueError`` is **retained** here and, transitively, in the three subclasses below.
    """


class UncapturedFieldPropertyError(FieldAuthoringRefusal):
    """A ``property`` key or shape no committed capture carries."""


class UncapturedConversionError(FieldAuthoringRefusal):
    """A ``(from, to)`` conversion pair no committed capture carries."""


class SelectOptionIdRequiredError(FieldAuthoringRefusal):
    """An ``update_field`` on a select column whose body would re-mint every option id.

    The measured shape of a data loss, not a precaution — see
    :data:`SELECT_OPTION_ID_IS_THE_CELL_ANCHOR` for the numbers and the capture.
    """


class RefutedFieldAuthoringError(FieldAuthoringRefusal):
    """A shape the server **accepts** and leaves **inert** — refused on the capture that
    measured the inertness.

    The third refusal in this family, and the one the other two could not express. *Uncaptured*
    says **"nobody looked"**; this says **"somebody looked, and what came back was a dead
    column"**. The distinction matters to a caller: an uncaptured shape becomes authorable the
    moment a probe is taken, and a refuted one stays refused until the **server** changes.
    """


# --------------------------------------------------------------------------- #
# The captured property shapes                                                 #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class MinimalFormControl:
    """What a **property-less** create of one column kind answered, and where it was measured.

    This control is what ``required`` was missing. That flag decided whether a create carrying
    no ``property`` reached the wire, and it was a **hand-set boolean**: 22 of 24 rows carried
    the default ``False`` because nobody had typed ``True``, not because anything had been
    measured. A ``Progress`` create therefore passed the plan gate and was refused by the
    server — the one outcome a plan gate exists to prevent. So the flag is no longer set. It is
    **derived** from this record, and this record cites its capture the way a property shape
    does.

    * ``capture`` / ``path`` — the committed capture, and the key path **inside** it that
      resolves to the code below. Mechanical on purpose: a test walks the path and compares, so
      a row cannot claim an answer its capture does not carry;
    * ``code`` / ``msg`` — Lark's own answer to the property-less create. ``0`` means the kind
      needs no ``property`` to exist; anything else means it does, and the refusal quotes the
      code rather than a borrowed one — the link kinds answer ``1254089`` / ``1254092``, not the
      ``1254001`` the old hard-coded sentence claimed for everybody;
    * ``working`` — for a kind that refuses, the ``property`` body measured **accepted** in the
      same capture, verbatim JSON, quoted in the refusal so the caller learns what the column
      needs. **It is never filled in for them**: a library that supplied a default would author
      a column nobody asked for, silently, which is worse than the refusal it replaced. A
      probe's own values are in it — a link's ``table_id`` names the table that run pointed at
      — and that is said where it is quoted rather than tidied away.
    """

    capture: str
    path: Tuple[Any, ...]
    code: int
    msg: str
    working: str = ""

    @property
    def refused(self) -> bool:
        """Whether the server refused the property-less create. ``required``, one level down."""
        return self.code != 0


@dataclass(frozen=True)
class FieldPropertyShape:
    """One column kind's captured ``property`` shape.

    * ``keys`` — the settable option names this library accepts for the kind, each present in
      the capture named below. An option outside this tuple is refused;
    * ``minimal_form`` — the kind's :class:`MinimalFormControl`: what a **property-less** create
      of it actually answered, and where that was measured;
    * ``required`` — **derived from** ``minimal_form``, never set: whether the API refuses the
      kind when ``property`` is absent. Which kinds do is stated by
      :data:`REQUIRED_PROPERTY_SENTENCE`, **generated** from the table below rather than written
      here, because the hand-written version of this bullet shipped a claim the table already
      disagreed with — and every sweep moves it again;
    * ``capture`` — the committed capture filename the shape was transcribed from;
    * ``note`` — what a reader needs to know that the key names alone do not say. It describes
      the **kind**, never the call: see ``call_shape`` for the call, which is generated;
    * ``nests`` — ``(key, wire_container)`` pairs for the keys this library nests into a
      sub-object **on the wire**. They are still passed **flat** to :func:`build_property`,
      which is the whole point of recording them here: a note that told a caller to nest one
      earned them an :class:`UncapturedFieldPropertyError`, because the nesting is this
      function's job. The container is carried rather than guessed from ``ui_type`` — the two
      happen to match today and there is no rule that says they must — and it is **proved**
      against the object :func:`build_property` really builds, by a test.

    ``call_shape`` is **generated from** ``keys`` and ``nests`` rather than written beside
    them, so the sentence a caller reads and the tuple the call enforces cannot disagree.
    """

    ui_type: str
    field_type: int
    keys: Tuple[str, ...]
    capture: str
    minimal_form: MinimalFormControl
    note: str = ""
    nests: Tuple[Tuple[str, str], ...] = ()

    @property
    def required(self) -> bool:
        """Whether a ``property`` is mandatory — **read off the row's own measured control.**

        Kept as an attribute because it is the name consumers already read; changed from a
        field to a derivation because a field is what let it be wrong.
        """
        return self.minimal_form.refused

    @property
    def call_shape(self) -> str:
        """How to CALL this kind — one sentence, derived from this shape's own tuples."""
        if not self.keys:
            return f"a {self.ui_type} column takes no property options at all"
        flat = ", ".join(f"`{key}`" for key in self.keys)
        sentence = (f"pass {flat} FLAT as keyword(s) to "
                    f"build_property({self.ui_type!r}, …)")
        if self.nests:
            wire = "; ".join(
                f"`{key}` → property.{container}.{key}" for key, container in self.nests)
            sentence += (f" — this library nests {wire} on the wire, so you do not nest it "
                         "yourself")
        return sentence


_ZOO = "05-04-field-zoo-create-results.json"
_LD339 = "ld339-01-select-option-id-remint.json"
_LD339_PALETTE = "ld339-02-select-color-palette.json"
_LD462 = "ld462-01-select-option-shrink.json"
_SCHEMA = "06-01-field-schema.json"
_REMAINING = "p0-2-02-remaining-types-create.json"
_LINKS = "p0-2-01-interconnection-field-create.json"
_IDENTITY = "p1-q2-02-true-identity-retries.json"
_FORMULA_PROBE = "ld262-01-field-authoring-probes.json"
_LD280_PROBE = "ld280-01-formula-evaluation-probe.json"
_MINIMAL_FORM = "ld317-01-minimal-form-sweep.json"


def _minimal(ui_type, code, msg, working=""):
    """This kind's row in the minimal-form sweep — one property-less create, one answer.

    Every row comes from the **same** capture and the same uniform path, because the sweep took
    all twenty-four controls in one pass against one self-provisioned disposable: a flag read
    off a capture from another month is a flag nobody is checking, which is how ``Progress``
    came to say ``code:0`` in a 2026-07 zoo and ``1254001`` on the wire.
    """
    return MinimalFormControl(capture=_MINIMAL_FORM,
                              path=("observations", ui_type, "minimal_form", "code"),
                              code=code, msg=msg, working=working)


def _shape(ui_type, field_type, keys, capture, minimal_form, note="", nests=()):
    return FieldPropertyShape(ui_type=ui_type, field_type=field_type, keys=tuple(keys),
                              capture=capture, minimal_form=minimal_form, note=note,
                              nests=tuple(nests))


#: **Every allow-listed column kind whose authoring shape a capture carries**, keyed by
#: ``ui_type``. A kind whose shape no capture carries is in
#: :data:`UNCAPTURED_PROPERTY_UI_TYPES` instead, and is refused rather than guessed.
FIELD_PROPERTY_SHAPES: Dict[str, FieldPropertyShape] = {
    shape.ui_type: shape for shape in (
        _shape("Text", 1, (), _IDENTITY,
               _minimal("Text", 0, "success"),
               "a plain text column is created with no property at all"),
        _shape("Barcode", 1, ("allowed_edit_modes",), _SCHEMA,
               _minimal("Barcode", 0, "success"),
               "the server fills allowed_edit_modes itself when none is given"),
        _shape("Number", 2, ("formatter",), _ZOO,
               _minimal("Number", 0, "success")),
        _shape("Progress", 2, ("formatter", "min", "max"), _REMAINING,
               _minimal("Progress", 1254001, "WrongRequestBody",
                        '{"formatter": "0%", "max": 100, "min": 0}'),
               "the minimal form — name and type only — is refused 1254001; the 2026-07 zoo "
               "recorded it succeeding and the server no longer does, which is why the flag "
               "is derived from a sweep rather than transcribed once"),
        _shape("Currency", 2, ("currency_code", "formatter"), _SCHEMA,
               _minimal("Currency", 1254001, "WrongRequestBody",
                        '{"currency_code": "USD", "formatter": "0.00"}'),
               "the currency is a CODE on the property, not a symbol in the formatter"),
        _shape("Rating", 2, ("symbol", "formatter", "min", "max"), _REMAINING,
               _minimal("Rating", 1254001, "WrongRequestBody",
                        '{"formatter": "0", "max": 5, "min": 0, '
                        '"rating": {"symbol": "star"}}'),
               "the minimal form — name and type only — is refused 1254001",
               nests=(("symbol", "rating"),)),
        _shape("SingleSelect", 3, ("options",), _ZOO,
               _minimal("SingleSelect", 0, "success"),
               "each option is {id, name, color}; the server mints the id on a CREATE, and on "
               "an UPDATE the id it is given is the cell's anchor — see "
               "SELECT_OPTION_ID_IS_THE_CELL_ANCHOR"),
        _shape("MultiSelect", 4, ("options",), _ZOO,
               _minimal("MultiSelect", 0, "success"),
               "each option is {id, name, color}; the server mints the id on a CREATE, and on "
               "an UPDATE the id it is given is the cell's anchor — see "
               "SELECT_OPTION_ID_IS_THE_CELL_ANCHOR"),
        _shape("DateTime", 5, ("date_formatter", "auto_fill"), _ZOO,
               _minimal("DateTime", 0, "success")),
        _shape("Formula", 20, ("formula_expression", "formatter"), _FORMULA_PROBE,
               _minimal("Formula", 0, "success"),
               "the create answers code:0 and the column reads back as type 20 / Formula — "
               "but only a CONSTANT expression computes (measured in " + _LD280_PROBE + "); "
               "a referencing one authors an inert column and is refused here. Its cells "
               "stay unwritable either way — a different constant answers that question. Its "
               "property-less create is ACCEPTED by the server, so this row is not required; "
               "the refusal a caller meets for one is the expression refutation, which is a "
               "different sentence about a different fact",
               ),
        _shape("Checkbox", 7, (), _ZOO,
               _minimal("Checkbox", 0, "success")),
        _shape("User", 11, ("multiple",), _ZOO,
               _minimal("User", 0, "success")),
        _shape("Phone", 13, (), _ZOO,
               _minimal("Phone", 0, "success"),
               "the ui_type is Phone; a create asking for PhoneNumber is refused 99992402"),
        _shape("Url", 15, (), _ZOO,
               _minimal("Url", 0, "success")),
        _shape("Attachment", 17, (), _ZOO,
               _minimal("Attachment", 0, "success")),
        _shape("SingleLink", 18, ("table_id", "multiple"), _LINKS,
               _minimal("SingleLink", 1254089, "LinkFieldPropertyError",
                        '{"multiple": false, "table_id": "tblIozLzSCCOEInB"}'),
               "table_id names the table the link points at, and a create that does not name "
               "one is refused 1254089 — the zoo's property-less link, which the server used "
               "to answer by inventing a target table, is not a shape this API still takes"),
        _shape("DuplexLink", 21, ("table_id", "multiple"), _LINKS,
               _minimal("DuplexLink", 1254092, "DuplexLinkFieldPropertyError",
                        '{"multiple": false, "table_id": "tblIozLzSCCOEInB"}'),
               "the same call ALSO creates the mirror column in the target table"),
        _shape("Location", 22, ("input_type",), _ZOO,
               _minimal("Location", 0, "success"),
               "input_type is the only settable option a Location column has",
               nests=(("input_type", "location"),)),
        _shape("GroupChat", 23, ("multiple",), _ZOO,
               _minimal("GroupChat", 0, "success")),
        _shape("CreatedTime", 1001, ("date_formatter",), _ZOO,
               _minimal("CreatedTime", 0, "success")),
        _shape("ModifiedTime", 1002, ("date_formatter",), _ZOO,
               _minimal("ModifiedTime", 0, "success")),
        _shape("CreatedUser", 1003, (), _ZOO,
               _minimal("CreatedUser", 0, "success")),
        _shape("ModifiedUser", 1004, (), _REMAINING,
               _minimal("ModifiedUser", 0, "success")),
        _shape("AutoNumber", 1005, ("auto_serial",), _ZOO,
               _minimal("AutoNumber", 0, "success")),
    )
}

#: The ``(field_type, ui_type)`` identity of a **plain text** column — **derived from the one
#: shape table above, never restated as a literal.** It is published because the plainest column
#: there is has more than one caller: LD-322's ``primary_field_name=`` is exactly this identity,
#: normalised into a one-entry column kit, and a second hand-written ``1`` somewhere else would
#: be the beginning of the parallel shape table this module exists to prevent.
PLAIN_TEXT_FIELD: Tuple[Any, str] = (FIELD_PROPERTY_SHAPES["Text"].field_type, "Text")

#: The kinds whose ``property`` is **mandatory** — derived from the table's own controls, never
#: listed by hand. This is the tuple a consumer can branch on without reading every row.
REQUIRED_PROPERTY_KINDS: Tuple[str, ...] = tuple(sorted(
    ui_type for ui_type, shape in FIELD_PROPERTY_SHAPES.items() if shape.required))

#: The ``required`` story in one sentence, **generated** from the table above. The hand-written
#: version of it shipped saying *"exactly one kind is: Rating"* while a second row already
#: carried the flag — and the sweep that fixed the under-enforcement moved the count to five. So
#: the sentence counts the table instead of describing it from memory, the way ``call_shape``
#: already does for the keys.
REQUIRED_PROPERTY_SENTENCE: str = (
    f"{len(REQUIRED_PROPERTY_KINDS)} of the {len(FIELD_PROPERTY_SHAPES)} captured column kinds "
    f"refuse a create that carries no `property`, each one measured rather than assumed: "
    f"{', '.join(REQUIRED_PROPERTY_KINDS)}. Every other kind's property-less create was "
    f"observed succeeding."
)

#: The allow-listed kinds whose **authoring** shape no capture carries. **Empty today** — and
#: derived rather than hand-listed, so it fills itself the moment the server's enum grows a kind
#: this library has no shape for. A member is refused with an ``uncaptured`` message rather than
#: authored on a shape read off the *read* side, which is a different route.
UNCAPTURED_PROPERTY_UI_TYPES: Tuple[str, ...] = tuple(
    ui_type for ui_type in AUTHORABLE_UI_TYPES if ui_type not in FIELD_PROPERTY_SHAPES
)

#: **The CELL read** (LD-280). ``code:0`` and a column that reads back as type 20 prove the
#: column EXISTS; they cannot tell a computing column from a dead one, and a formula column
#: can be dead. So the cells were read, on two
#: routes, over a record written **before** the column and one written **after** it, re-read
#: across a bounded poll budget. **The boundary is inside the kind:** a CONSTANT expression
#: computes on every row (``1+1`` → ``{"type": 2, "value": [2]}``); a **referencing** one never
#: materialises — neither ``CurrentValue.[column]`` nor the server's **own** rebound form of
#: it (the one naming the table and field ids), sent back verbatim, which is the control that
#: rules out *"Lark rebinds names badly"*. The key is simply absent from every record.
FORMULA_EVALUATION: Dict[str, Any] = {
    "ui_type": "Formula",
    "evidence": _LD280_PROBE,
    "constant_computes": True,
    "reference_computes": False,
    "observed": (
        "a Formula column authored through POST …/fields computes ONLY when its expression "
        "references nothing. A constant answered on every row of a self-provisioned "
        "disposable; an expression naming another column in the same table — and the server's "
        "own rebound form of it, sent back verbatim — never materialised on either read route, "
        "over a record written before the column and one written after it, across a bounded "
        "poll budget. The cell key is absent, not empty"
    ),
    "what_instead": (
        "author the formula in the product, where the expression binds and the column "
        "computes. This library READS a formula cell and its expression fine once the column "
        "exists — what it will not do is mint a column that looks authored and is inert"
    ),
}


def formula_authoring_status(evaluation: Dict[str, Any]) -> str:
    """The capability status, **derived from the measurement** rather than typed beside it.

    ``captured`` when a referencing formula computes, ``partial`` when only a constant does,
    ``refuted`` when nothing does. A hand-written status is a claim; this one is a consequence,
    so re-capturing the probe re-prices the row and nothing else has to be remembered.
    """
    if evaluation["reference_computes"]:
        return "captured"
    return "partial" if evaluation["constant_computes"] else "refuted"


#: What was actually observed when this library probed ``Formula`` authoring. The ld262 rung
#: took the cheap half — ``POST …/fields`` with a ``formula_expression`` answered ``code:0``
#: and the column read back as type 20 / ``Formula`` — and recorded ``captured`` on it. LD-280
#: took the other half, the **cell** read, and the row is re-priced from it: the acceptance is
#: real, the computation is real only for the one expression class
#: :data:`FORMULA_EVALUATION` measured, and the status is **derived** from that measurement.
FORMULA_AUTHORING: Dict[str, Any] = {
    "ui_type": "Formula",
    "status": formula_authoring_status(FORMULA_EVALUATION),
    "evidence": _FORMULA_PROBE,
    "cell_evidence": _LD280_PROBE,
    "observed": (
        "POST …/fields with a formula_expression answered code:0 against a self-provisioned "
        "disposable, and the created column read back as type 20 / Formula — which proves the "
        "column EXISTS and nothing about whether it computes. Read back at the CELL: a "
        "constant expression computes on every row, and a referencing one never materialised "
        "at all, so the column that call authors is INERT for every expression a real formula "
        "has. Acceptance was never the question"
    ),
    "cells_stay_refused": (
        "authoring a Formula column does NOT make its cells writable. A formula, an "
        "auto-number and the four created/modified time and user columns are all columns you "
        "can create whose values the server owns — two different questions with two different "
        "answers, and this surface answers only the first"
    ),
}


#: The ONE expression class the capture shows computing: arithmetic over literal numbers,
#: naming nothing. An **allow-list, not a parser** — this library does not tokenize a formula
#: (``larkdocio.base.computed`` holds the standing rule that a formula string is opaque
#: provenance), so the question asked here is the conservative one: *is this provably free of
#: references?* Everything else is refused, including a shape that would have worked.
_CONSTANT_EXPRESSION = re.compile(r"[0-9\s+\-*/%().]+")


def formula_expression_is_captured(expression: Any) -> bool:
    """Whether ``expression`` is in the one class :data:`FORMULA_EVALUATION` measured live."""
    if not isinstance(expression, str) or not _CONSTANT_EXPRESSION.fullmatch(expression):
        return False
    return any(character.isdigit() for character in expression)


def check_formula_expression(expression: Any) -> str:
    """The expression, or :class:`RefutedFieldAuthoringError` — **locally, zero calls**."""
    if formula_expression_is_captured(expression):
        return expression
    raise RefutedFieldAuthoringError(
        f"this library will not author a Formula column for the expression "
        f"{expression!r}: it is not in the one expression class a capture shows COMPUTING. "
        f"{FORMULA_EVALUATION['observed']} — measured in "
        f"{_CAPTURES}/{_LD280_PROBE} ({DEV_REPO_LABEL}). The create would answer code:0 "
        f"and hand you a column "
        f"whose cell key is absent from every record, which is worse than a refusal because "
        f"it reads as success. So: {FORMULA_EVALUATION['what_instead']}. The only expressions "
        f"accepted here are arithmetic over literal numbers, which is what was measured. "
        f"Nothing was sent.")


#: The consumer-facing sentence a ``Formula`` create carries in the dry run, before anything
#: happens — the same shape as the ``DuplexLink`` mirror disclosure.
FORMULA_EVALUATION_WHAT = (
    "This creates a Formula column whose expression is a constant, which is the only kind "
    "measured to compute through this API. A formula that references another column is "
    "refused before the call: the create is accepted and the cell never materialises."
)


# --------------------------------------------------------------------------- #
# The select option id — measured, stated once, quoted everywhere              #
# --------------------------------------------------------------------------- #

#: The keys one select **option** carries. ``id`` is the one this library used to drop.
SELECT_OPTION_KEYS = ("id", "name", "color")

#: The ``ui_type`` / storage-type pairs whose cells are anchored to an option id.
SELECT_UI_TYPES = ("SingleSelect", "MultiSelect")
SELECT_FIELD_TYPES = (3, 4)

#: **Stated once, quoted everywhere.** The measurement that turns an options-carrying
#: ``update_field`` from a rename into a data loss.
SELECT_OPTION_ID_IS_THE_CELL_ANCHOR = (
    "A select cell stores the option's `id`, not its name — so `PUT …/fields/{f}` is a "
    "REPLACEMENT of the option set, matched on that id. Measured on a disposable with 6 "
    "populated cells per column (`" + f"{_CAPTURES}/{_LD339}" + f", {DEV_REPO_LABEL}`): a body "
    "carrying every existing option id preserved the ids and 6 of 6 cells, for SingleSelect and "
    "MultiSelect alike; the SAME body with the ids missing re-minted all three ids and left 0 "
    "of 6 cells resolving, even when name and colour were byte-identical; and a body with no "
    "`property` at all emptied the option set to [] and left 0 of 6. The id is therefore the "
    "anchor this route is keyed on, and an update that cannot name it is a wipe wearing a "
    "rename's clothes."
)

#: What the colour int is **measured** to accept. No hue is named: the API returns the int it
#: was given, this library never sees a colour, and a hue is a human's word for it.
SELECT_OPTION_COLOR_INTS = (
    "`option.color` is an int the server stores verbatim: 21 ints spread across 0-53 "
    "(0, 1, 2, 3, 4, 5, 8, 11, 14, 17, 20, 22, 24, 28, 33, 36, 40, 43, 46, 49, 53) were sent and "
    "EVERY ONE read back unchanged — nothing clamped, nothing normalised — and a separate "
    "probe accepted 54 and stored it, while -1, 99 and 1000 were each refused `99992402 field validation failed` "
    "(`" + f"{_CAPTURES}/{_LD339_PALETTE}" + f", {DEV_REPO_LABEL}`). WHICH SHADE EACH INT PAINTS "
    "IS NOT SOMETHING THIS LIBRARY READS, so it does not name one — set a column's colours at "
    "create time and look at the result. THE INTS BETWEEN THE ONES LISTED WERE NOT PROBED: "
    "this is a measured spread, not a claim about a whole range."
)


#: **THE THIRD DESTRUCTIVE SHAPE, measured.** LD-339 fenced the two shapes it measured — no ids
#: anywhere, and no option set at all — both decided on the request's own shape. What neither
#: covers is the body that carries every SURVIVING option with its id and simply **omits** one:
#: the SHRINK. It passes that fence, and it destroys the cells of the option it drops.
SELECT_OPTION_SHRINK_DESTROYS_CELLS = (
    "REMOVING an option from a select column's option set DESTROYS the cells that hold it. "
    "Measured on a disposable with three records per column (`" + f"{_CAPTURES}/{_LD462}"
    + f", {DEV_REPO_LABEL}`): a SingleSelect body keeping two options WITH their ids and "
    "omitting the third left the 2 of 3 cells that held the dropped option reading EMPTY and "
    "the survivor untouched; the same shape on a MultiSelect removed the dropped value from "
    "each cell it was in — `[B, C]` read back `[B]` — and EMPTIED the cell that held it alone. "
    "The two controls in the same run destroyed nothing: RENAMING an option while keeping every "
    "id kept every cell, which read back under the option's new name because the cell is "
    "anchored to the id, and dropping an option NO RECORD HELD left every cell byte-identical. "
    "So the loss is exactly the records that hold a dropped option — which is knowable only by "
    "reading the table, and this library reads it before it will send the write."
)

#: **AC5 — the ordering a caller otherwise has to derive for themselves**, said at the
#: refusal instead of in a recipe nobody reaches before the data is gone.
REMAP_THEN_SHRINK = (
    "THE SAFE ORDERING IS REMAP THEN SHRINK: first move every record off the option you are "
    "dropping (a records update onto an option you are keeping, through the record engine), "
    "then send the shrunken option set — at which point the shrink destroys nothing, needs no "
    "consent token, and its loss preview is measured empty. Doing it the other way round — "
    "shrink first, remap after — is what destroyed the cells before you could read them, "
    "because the values are gone by the time the remap has anything to address."
)


def select_label(field_type, ui_type) -> Optional[str]:
    """Which select kind this request targets, or ``None`` when it targets none.

    The discriminator is the request's own identity — ``ui_type``, or the storage type, since
    ``3``/``4`` are the select types — and it is authored **once** here so the shape fence
    (:func:`check_select_option_update`) and the shrink preview
    (:func:`larkdocio.base.loss_preview.select_option_shrink_loss`) cannot disagree about what a
    select column is.
    """
    if ui_type in SELECT_UI_TYPES:
        return ui_type
    if field_type in SELECT_FIELD_TYPES:
        return "SingleSelect" if field_type == 3 else "MultiSelect"
    return None


def is_select_option_replacement(field_type, ui_type, properties) -> bool:
    """Whether this request REPLACES a select column's option set — and can therefore destroy
    cells (:data:`SELECT_OPTION_SHRINK_DESTROYS_CELLS`).

    Decided on the request's shape alone, with **no read**: what a read is needed for is *which*
    cells the replacement destroys, and that is the loss preview's job
    (:func:`larkdocio.base.loss_preview.select_option_shrink_loss`). An options-carrying select
    update whose loss cannot be enumerated is refused rather than sent, so this predicate never
    has to be right about populated-ness — only about whether the question arises.
    """
    return (select_label(field_type, ui_type) is not None
            and bool((properties or {}).get("options")))


def select_option_refusal(reason: str, ui_type: str) -> str:
    """The one refusal text, built from the one measurement. ``reason`` is ``no-ids`` (an
    options array in which no option carries an id) or ``no-options`` (an update that sends no
    option set at all)."""
    if reason == "no-options":
        opening = (f"this update sends NO option set for a {ui_type!r} column, and `PUT "
                   f"…/fields/{{f}}` is a REPLACEMENT: the column's options would be emptied "
                   f"outright.")
    else:
        opening = (f"none of the options in this update carry an `id`, so the server would mint "
                   f"a fresh id for every one of them and every cell pointing at an old id "
                   f"would be orphaned.")
    return (
        f"refusing an options-carrying update of a {ui_type!r} column: {opening} "
        f"{SELECT_OPTION_ID_IS_THE_CELL_ANCHOR} "
        f"Nothing was sent. WHAT TO DO: read the column back with `list_fields`, and pass its "
        f"options through UNCHANGED — each with its `id` — alongside whatever you are changing; "
        f"an option with no `id` beside id-carrying ones is treated as an ADDITION and is "
        f"allowed. Colours are cheapest to get right at create time: set them in `create_field` "
        f"(or in a `create_table` fields kit), where there are no cells to orphan yet. "
        f"THIS REFUSAL DOES NOT ASK whether the column holds data — populated-ness is not "
        f"knowable from this request's shape, and an unknown blast radius is not a safe one, so "
        f"an EMPTY select column is refused on the same shape and pays the same price. "
        f"If you genuinely mean to DROP an option and the cells that hold it, that is a "
        f"destructive write and this library does ship it — through a plan: send the option set "
        f"you want (every option you keep carrying its `id`) to `update_field`, pass "
        f"`read_client=` to `schema_dry_run`, read the entry's `loss_preview`, which names every "
        f"record that loses a value, and apply with "
        f"`consent=consent_to_destroy(plan)` — the same door `delete_field` uses. "
        f"{REMAP_THEN_SHRINK}"
    )


def check_select_option_update(field_type, ui_type, properties) -> None:
    """Refuse the two measured-destructive ``update_field`` shapes on a select column.

    **Local, structural, and before any client exists.** The discriminator is the request's own
    shape — :func:`select_label` plus whether the option array names its ids — never a read.
    These two shapes are wrong *whatever* the table holds, so they are refused where they are
    cheapest to refuse and the refusal costs nothing.

    **What the ``ld462-01`` measurement amended, and what it did not.** The reason above is
    unchanged and both refusals stand exactly as they were: an unknown blast radius is not a safe
    one. What it supersedes is the old *conclusion* that a select column's cells therefore could
    never be dropped through this library at all — a shrink that carries every surviving option's
    ``id`` is a shape neither refusal here catches, and it destroys the cells of the option it
    omits
    (:data:`SELECT_OPTION_SHRINK_DESTROYS_CELLS`). That shape is not made safe by a local
    check; it is enumerated by a **read** and gated by the consent token ``delete_field``
    already uses, one level up in the plan
    (:func:`larkdocio.base.loss_preview.select_option_shrink_loss`). So this function's job is
    still exactly the two shapes below.
    """
    label = select_label(field_type, ui_type)
    if label is None:
        return
    options = (properties or {}).get("options")
    if not options:
        raise SelectOptionIdRequiredError(select_option_refusal("no-options", label))
    if not any(option.get("id") for option in options):
        raise SelectOptionIdRequiredError(select_option_refusal("no-ids", label))


def _build_option(option):
    """One typed option, with the ``id`` **sent** when the caller supplied one.

    The silent drop this replaces was the defect: two of the three keys were read and the
    third — the one the cells are anchored to — was discarded without a word.
    """
    for key in option:
        if key not in SELECT_OPTION_KEYS:
            raise UncapturedFieldPropertyError(
                f"{key!r} is not a key a select OPTION carries: the keys the pinned SDK's "
                f"option model and the captures both carry are "
                f"{', '.join(SELECT_OPTION_KEYS)}. Nothing was sent.")
    if not option.get("name"):
        raise UncapturedFieldPropertyError(
            "every select option needs a `name`: an option is identified to a human by its "
            f"name and to the server by its `id`, and this one carries neither a name nor a "
            f"usable one ({option!r}). Nothing was sent.")
    builder = AppTableFieldPropertyOption.builder() \
        .name(option["name"]).color(option.get("color", 0))
    if option.get("id"):
        builder = builder.id(option["id"])
    return builder.build()


def _property_builder():
    return AppTableFieldProperty.builder()


def _refuse_key(ui_type: str, key: str, shape: Optional[FieldPropertyShape]) -> None:
    accepted = ", ".join(shape.keys) if shape and shape.keys else "(none)"
    capture = (f" (captured in {_CAPTURES}/{shape.capture}, {DEV_REPO_LABEL})"
               if shape else "")
    raise UncapturedFieldPropertyError(
        f"{key!r} is not a property this library will send for a {ui_type!r} column: no "
        f"committed capture shows it on that kind, so sending it would be a guess. This API "
        f"silently IGNORES body keys it does not recognise, which means an invented key comes "
        f"back code:0 having authored a column without it. The keys captured for {ui_type!r} "
        f"are: {accepted}{capture}.")


def build_property(ui_type: str, **options):
    """The typed ``property`` for ``ui_type``, or ``None`` when the kind takes none.

    Every keyword must be a key the kind's captured shape carries; anything else raises
    :class:`UncapturedFieldPropertyError` **before any request is built**. The two nested traps
    — ``Rating``'s ``symbol`` and ``Location``'s ``input_type`` — are taken flat here and nested
    by this function, which is the trap being handled rather than documented.
    """
    if ui_type in UNCAPTURED_PROPERTY_UI_TYPES:
        raise UncapturedFieldPropertyError(
            f"the authoring property shape for a {ui_type!r} column is uncaptured: it is in "
            "the server's own allow-list, but no committed capture shows what a create for it "
            "sends, and this library does not guess a shape onto a schema write. Create the "
            "column in the product and read it back, or capture a probe first.")
    shape = FIELD_PROPERTY_SHAPES.get(ui_type)
    if shape is None:
        raise UncapturedFieldPropertyError(
            f"{ui_type!r} has no captured authoring shape at all. The kinds this library "
            f"authors are: {', '.join(sorted(FIELD_PROPERTY_SHAPES))}.")
    for key in options:
        if key not in shape.keys:
            _refuse_key(ui_type, key, shape)
    if ui_type == "Formula":
        # The one kind whose accepted shape authors a column that does not work. Refused on
        # the CELL capture, here, before a request exists — see FORMULA_EVALUATION.
        check_formula_expression(options.get("formula_expression"))
    if not options:
        if shape.required:
            control = shape.minimal_form
            raise UncapturedFieldPropertyError(
                f"a {ui_type!r} column cannot be created without a property: the minimal form "
                f"— name and type only — answered {control.code} {control.msg} in "
                f"{_CAPTURES}/{control.capture} ({DEV_REPO_LABEL}). "
                f"Pass {', '.join(shape.keys)}. The body measured ACCEPTED in that same sweep "
                f"was {control.working} — those are a probe's own values, so read it for the "
                f"SHAPE and supply your own; this library will not fill one in for you, "
                f"because a column authored from a guessed default is one nobody asked for. "
                f"Nothing was sent.")
        return None

    builder = _property_builder()
    for key, value in options.items():
        if key == "symbol":
            builder = builder.rating(Rating.builder().symbol(value).build())
        elif key == "input_type":
            builder = builder.location(
                AppFieldPropertyLocation.builder().input_type(value).build())
        elif key == "options":
            # LD-339: the `id` goes on the wire when the caller supplies one. It is what the
            # cells are anchored to, and dropping it silently is what orphaned 6 of 6.
            builder = builder.options([_build_option(option) for option in value])
        else:
            builder = getattr(builder, key)(value)
    return builder.build()


#: Stated once, quoted everywhere. Inherited from the read and record-write rungs and re-pinned
#: on the authoring side, because this is where the flag is **set**.
MULTIPLE_IS_NOT_A_CARDINALITY_GUARANTEE = (
    "`property.multiple: false` is NOT a cardinality guarantee. A link column created with it "
    "was fed two record ids and answered code:0, echoing both back, so the flag describes the "
    "field picker's intent rather than an invariant the server holds. This surface SETS the "
    "property because Lark takes it; it does not enforce anything from it, and a caller who "
    "needs one value per cell has to enforce that themselves."
)


# --------------------------------------------------------------------------- #
# The DuplexLink mirror — a cross-table CREATE                                  #
# --------------------------------------------------------------------------- #

#: The consumer-facing sentence a plan entry carries for a ``DuplexLink`` create.
CROSS_TABLE_CREATE_WHAT = (
    "Creating a two-way link column also creates a column in another table, in the same call. "
    "The mirror lands in the table this link points at, named after the source table and the "
    "source column, and the two point at each other. That second column is a change to a table "
    "you did not name in this request, which is why it is stated here before anything happens."
)

#: Where the mirror was observed, verbatim.
CROSS_TABLE_CREATE_EVIDENCE = dev_repo(f"{_CAPTURES}/{_LINKS}")


def duplex_mirror_name(source_table_name: str, source_field_name: str) -> str:
    """The name Lark gives the mirror column, pinned against the capture.

    ``p0zoo-Main-033103`` + ``DuplexLink`` → ``p0zoo-Main-033103-DuplexLink``.
    """
    return f"{source_table_name}-{source_field_name}"


#: What the disclosure says when the caller did not name the source table, so the mirror's name
#: cannot be predicted. The cross-table create still happens and is still disclosed — only the
#: predicted name is withheld, because a predicted name that is wrong is worse than none.
MIRROR_NAME_UNPREDICTED = (
    "The mirror column's name is built from the name of the table this column is being created "
    "in, which was not supplied, so it is not predicted here. Pass the source table's name to "
    "see it before the call."
)


def cross_table_create(ui_type: str, field_name: str, properties,
                       source_table_name: Optional[str]) -> Optional[dict]:
    """The dry-run disclosure for a create that reaches a second table, or ``None``.

    Only ``DuplexLink`` does. ``SingleLink`` points at another table and creates nothing in
    it — the difference is the whole reason this is disclosed for one and not the other.
    """
    if ui_type != "DuplexLink":
        return None
    return {
        "what": CROSS_TABLE_CREATE_WHAT,
        "table_id": (properties or {}).get("table_id"),
        "predicted_field_name": (duplex_mirror_name(source_table_name, field_name)
                                 if source_table_name else None),
        "unpredicted": None if source_table_name else MIRROR_NAME_UNPREDICTED,
        "evidence": CROSS_TABLE_CREATE_EVIDENCE,
    }


# --------------------------------------------------------------------------- #
# Conversion — the pair table                                                   #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ConversionPair:
    """One ``(from, to)`` conversion this library will perform.

    A pair is listed **only** with a committed capture showing the conversion's effect on the
    column's own cells. ``code:0`` is not admissible evidence for a destructive op: this API
    silently ignores what it does not recognise, so an accepted call is not an applied one, and
    an applied one is not necessarily a lossless one.
    """

    from_ui_type: str
    to_ui_type: str
    field_type: int
    cell_effect: str
    captures: Tuple[str, ...]


CONVERSION_PAIRS: Tuple[ConversionPair, ...] = (
    ConversionPair(
        from_ui_type="Text",
        to_ui_type="Barcode",
        field_type=1,
        cell_effect=(
            "the column keeps storage type 1 and every cell keeps the string it held — the "
            "change is the column's presentation and its allowed edit modes, not its values. "
            "Observed over a POPULATED column: the value written before the conversion read "
            "back unchanged after it"),
        captures=(_IDENTITY, _FORMULA_PROBE),
    ),
)

_CROSS_STORAGE_REASON = (
    "A conversion that changes the storage type underneath a column is out of scope here. No "
    "capture shows what Lark does with the existing values: whether it coerces them, blanks "
    "them, or refuses the whole call. Guessing on your behalf would mean guessing about every "
    "value in the column, and the transformation is server-side and cannot be undone."
)


def enabled_conversion_pairs() -> Tuple[str, ...]:
    """``("Text -> Barcode",)`` — the pairs, in the wording the refusal quotes."""
    return tuple(f"{pair.from_ui_type} -> {pair.to_ui_type}" for pair in CONVERSION_PAIRS)


def check_conversion(from_ui_type: str, to_ui_type: str) -> ConversionPair:
    """The pair, or :class:`UncapturedConversionError` — decided **locally, zero calls**."""
    for pair in CONVERSION_PAIRS:
        if (pair.from_ui_type, pair.to_ui_type) == (from_ui_type, to_ui_type):
            return pair
    raise UncapturedConversionError(
        f"converting a {from_ui_type!r} column to {to_ui_type!r} is uncaptured, so this "
        f"library will not do it. Changing a column's kind rewrites every value in it, "
        f"server-side and permanently, and a pair is enabled here only when a committed "
        f"capture shows what happened TO THE CELLS — not merely that the call was accepted. "
        f"The pair(s) with that evidence today: {', '.join(enabled_conversion_pairs())}. "
        f"{_CROSS_STORAGE_REASON} Nothing was sent. To change a column's kind outside that "
        f"list, do it in the product, where you can see the result and undo it.")


# --------------------------------------------------------------------------- #
# The anchor                                                                    #
# --------------------------------------------------------------------------- #

#: Proven in ``p0-2-06-table-revision-granularity.json``: a field create moved
#: ``table.revision`` 12 → 13 and a field delete moved it 14 → 15. One op, one bump.
FIELD_OP_BUMPS_TABLE_REVISION_ONCE = True

#: What a **field**-scoped structural op IS guarded by — the counterpart of the app-scoped
#: rung's disclosure of an absence. Quoted by every field plan entry.
FIELD_OPS_RIDE_TABLE_REVISION = (
    "This operation is guarded by `table.revision`, which moves by exactly +1 per field "
    "operation on the table — a field create is +1 and a field delete is +1, measured. The "
    "engine re-reads the anchor immediately before the write and refuses, with zero writes, if "
    "it moved since the plan was built; it re-reads it again afterwards, and a call that "
    "answered code:0 while leaving the anchor unmoved is reported as not having landed rather "
    "than as applied. The compare is CLIENT-SIDE: there is no If-Match on this API, so it "
    "closes the window between the plan and the write, not the last microsecond between the "
    "compare and the write itself. A table whose anchor reads 0 has none available; the "
    "read-back of the column itself is what verifies the op there."
)


# --------------------------------------------------------------------------- #
# The error vocabulary a field op can actually meet                             #
# --------------------------------------------------------------------------- #

#: The codes this rung's two endpoints have been observed to answer, or can answer by
#: construction. Every one of them is already typed in
#: :data:`larkdocio.base.errors.BASE_ERROR_CODES`; what is authored here is what a caller can
#: DO about each on **this** route, which is not the same on every route.
FIELD_OP_ERROR_CODES: Tuple[int, ...] = (
    99992402,   # field validation failed — pre-empted locally; an arrival is API drift
    1254001,    # wrong request body — in a shipped op, a defect on this side
    1254041,    # TableIdNotFound
    1254004,    # WrongTableId
    1002,       # the Base has been trashed
    91402,      # no Base at this app_token
)


def drift_alarm_detail() -> str:
    """The ``99992402`` alarm, quoting the enum **this library currently holds**.

    Built rather than stored so it cannot drift from the shipped constant it is about.
    """
    return (
        "The accepted column kinds this library holds are: "
        f"{', '.join(AUTHORABLE_UI_TYPES)}. Compare them with the `options:` list inside the "
        "refusal body you just received: the difference is what changed on the server.")


FIELD_OP_ERROR_GUIDANCE: Dict[int, str] = {
    99992402: (
        "This should not have reached the server. Every column kind outside the accepted set "
        "is refused locally, before the call, so a validation refusal arriving here means the "
        "server's own accepted set has DRIFTED away from the one this library holds. That is "
        "an API-drift alarm and not a caller error: read the `options:` enum in the body, "
        "which the server ships in full inside every refusal, and re-pin the constant from a "
        "fresh capture."),
    1254001: (
        "The request body was the wrong shape for this endpoint. Every body on this route is "
        "assembled by this library from the typed request builders, so a shape refusal here is "
        "a library defect rather than something to fix in your call. Read the path the message "
        "names, and file it — re-shaping the arguments will not reach the offending key."),
    1254041: (
        "No such table in this Base. The id is well formed but belongs to no table here: list "
        "the tables and take the id from the listing rather than from an earlier session, "
        "because a table id does not survive the table."),
    1254004: (
        "The table id is malformed. A Base table id looks like `tbl…`; check that a view id or "
        "a record id has not been passed here, which produces exactly this."),
    1002: (
        "The Base has been trashed. Lark's delete is a trash rather than a purge, so the drive "
        "metadata still resolves its title while the Base API reports it gone — use a token "
        "you have just listed rather than one you remember."),
    91402: (
        "No Base exists at this app token. Check the token you extracted from the URL: a "
        "Base's token is the `/base/<token>` segment, not a table or a view id."),
}

# Every code here is a row in the one shared taxonomy — this module adds a route-specific
# *action*, never a second definition of what the code means.
assert set(FIELD_OP_ERROR_CODES) <= set(BASE_ERROR_CODES), (
    "a field-op error code with no row in the Base error taxonomy")
assert set(FIELD_OP_ERROR_GUIDANCE) == set(FIELD_OP_ERROR_CODES)


__all__ = [
    "CONVERSION_PAIRS",
    "CROSS_TABLE_CREATE_EVIDENCE",
    "CROSS_TABLE_CREATE_WHAT",
    "ConversionPair",
    "FIELD_OPS_RIDE_TABLE_REVISION",
    "FIELD_OP_BUMPS_TABLE_REVISION_ONCE",
    "FIELD_OP_ERROR_CODES",
    "FIELD_OP_ERROR_GUIDANCE",
    "FIELD_PROPERTY_SHAPES",
    "FORMULA_AUTHORING",
    "FORMULA_EVALUATION",
    "FORMULA_EVALUATION_WHAT",
    "FieldAuthoringRefusal",
    "FieldPropertyShape",
    "MIRROR_NAME_UNPREDICTED",
    "MULTIPLE_IS_NOT_A_CARDINALITY_GUARANTEE",
    "PLAIN_TEXT_FIELD",
    "REMAP_THEN_SHRINK",
    "RefutedFieldAuthoringError",
    "SELECT_FIELD_TYPES",
    "SELECT_OPTION_COLOR_INTS",
    "SELECT_OPTION_ID_IS_THE_CELL_ANCHOR",
    "SELECT_OPTION_KEYS",
    "SELECT_OPTION_SHRINK_DESTROYS_CELLS",
    "SELECT_UI_TYPES",
    "SelectOptionIdRequiredError",
    "UNCAPTURED_PROPERTY_UI_TYPES",
    "UncapturedConversionError",
    "UncapturedFieldPropertyError",
    "build_property",
    "check_conversion",
    "check_formula_expression",
    "check_select_option_update",
    "is_select_option_replacement",
    "select_label",
    "select_option_refusal",
    "cross_table_create",
    "formula_authoring_status",
    "formula_expression_is_captured",
    "drift_alarm_detail",
    "duplex_mirror_name",
    "enabled_conversion_pairs",
]
