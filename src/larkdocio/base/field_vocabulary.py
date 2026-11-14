"""larkdocio.base.field_vocabulary — the SERVER's own field-authoring allow-list.

**One constant, and it is not ours.** Lark's fields API states, in the body of every refusal
it issues, exactly which columns it will author: a ``99992402`` carries
``error.field_violations`` with the offending field, the offending value **and the complete
accepted enum**. Both enums below are transcribed from that body — **20 storage types and 24
``ui_type``s** — so this module publishes the server's vocabulary rather than a curated guess
at it.

**Where it came from** (the captures are in the source repository, so they are provenance rather
than reading you can follow). ``tests/captures/base-study/captures/p1-q2-01-button-sweep.json`` and
``tests/captures/base-study/captures/p1-q2-02-true-identity-retries.json``: 35 refusals across the two
captures, every one carrying the same two enums, on the field-CREATE route
(``POST …/fields``) and on the field-CONVERT route (``PUT …/fields/{id}``) alike. So it is
the vocabulary that blocks, not the verb. ``tests/test_base_field_vocabulary.py`` parses
those bodies and compares them to the constants below, which is what makes a hand-edit here
redden against the server's own words.

**It is a SNAPSHOT of a server enum, and that is the revisit trigger.** A ``99992402`` whose
``field_violations`` enum differs from these constants is an **API-drift alarm** — Lark
widened or narrowed what it authors — and it is *not* a caller error. Re-transcribe from a
fresh capture and re-pin; do not "fix" a caller.

**Four column kinds are outside the vocabulary by server declaration** — ``Lookup``,
``Stage`` (the product calls it Flow), ``Email`` and anything Button-shaped — so a caller who
asks for one is refused **here**, locally, before any client is touched, with a message that
says what *is* possible instead. That is strictly better than a round trip to an
opaque-looking code.

**This is the AUTHORING vocabulary — not the cell-write set.** Two constants answer two
different questions and they cross:

* *Can I create this column?* — this module.
* *Can I write this cell?* — :data:`larkdocio.base.write_vocabulary.NON_WRITABLE_PAIRS`,
  imported below and **never re-declared** here.

Six kinds are authorable with unwritable cells (a formula, an auto-number and the four
created/modified time and user columns); two are neither (``Lookup``, ``Stage``); and exactly
one — ``Email`` — has fully writable cells and cannot be created. The three quadrants are
**derived** from the two constants rather than hand-listed, so they cannot drift from either.
"""
from typing import Dict, Optional, Tuple

from larkdocio.common.citations import dev_repo
from larkdocio.errors import LarkConfigError

from .cells import PAIRS as _READ_REGISTRY_PAIRS
from .write_vocabulary import NON_WRITABLE_PAIRS

_CAPTURES = "tests/captures/base-study/captures"

#: The 20 storage types the fields API will author, verbatim from ``error.field_violations``.
AUTHORABLE_TYPES: Tuple[int, ...] = (
    1, 2, 3, 4, 5, 7, 11, 13, 15, 17, 18, 20, 21, 22, 23, 1001, 1002, 1003, 1004, 1005,
)

#: The 24 ``ui_type``s the fields API will author, verbatim from ``error.field_violations``.
AUTHORABLE_UI_TYPES: Tuple[str, ...] = (
    "Text", "Barcode", "Number", "Progress", "Currency", "Rating", "SingleSelect",
    "MultiSelect", "DateTime", "Checkbox", "User", "GroupChat", "Phone", "Url",
    "Attachment", "SingleLink", "Formula", "DuplexLink", "Location", "CreatedTime",
    "ModifiedTime", "CreatedUser", "ModifiedUser", "AutoNumber",
)

#: Where the allow-list was established, for a reader who wants to check it.
VOCABULARY_EVIDENCE = dev_repo(
    f"{_CAPTURES}/p1-q2-01-button-sweep.json · "
    f"{_CAPTURES}/p1-q2-02-true-identity-retries.json"
)

#: What this surface does and does not claim, stated where the registry publishes the list.
VOCABULARY_STATUS = (
    "This is the vocabulary Lark's fields API declares, published so a caller can plan "
    "against it. It is also the list this surface ENFORCES: a column is created or converted "
    "only for a kind on it, and every other kind is refused locally, before any call, with "
    "what to do instead. Publishing the whole vocabulary rather than only the authorable part "
    "is deliberate — a caller planning a schema needs to know which columns exist as much as "
    "which ones this library can author."
)

_SERVER_OWNS_THE_LIST = (
    "THE SERVER declares this set, not larkdocio: Lark returns the whole list in the body of "
    "its own refusal, and larkdocio ships that list verbatim so the refusal can happen here "
    "instead of costing you a round trip."
)

#: The four column kinds outside the vocabulary, each with **what is possible instead**.
#: A caller who is refused one of these gets a way forward, not just a "no".
UNAUTHORABLE_GUIDANCE: Dict[str, str] = {
    "Lookup": (
        "A Lookup column mirrors a field on a linked record, and no request creates one. "
        "The only route to a Base that has one is COPYING a Base that already has it: the "
        "copy carries the column over, and it reads normally afterwards."
    ),
    "Stage": (
        "A Stage column (the product calls it Flow) cannot be created by any request. The "
        "only route to a Base that has one is COPYING a Base that already has it — and note "
        "that even then only its schema is visible: a Stage column's values stay unreadable "
        "and unwritable."
    ),
    "Email": (
        "An Email column cannot be CREATED, and creating it is the only thing you cannot do "
        "with one. Given a Base that already has an Email column, its cells read fine and "
        "write fine: you write the address as a plain string and Lark synthesizes the "
        "mailto: prefix itself."
    ),
    "Button": (
        "A Button column has no entry in the list above, and larkdocio will not support one "
        "in any case — a deliberate decision on this library's side about a column whose "
        "content is a configured action rather than a value. Lark itself does return a "
        "Button column when a Base has one (its identity is type 3001, ui_type Button), so "
        "this is a support decision here rather than a limit on Lark's side."
    ),
}

_AUTHORABLE_UI = frozenset(AUTHORABLE_UI_TYPES)
_NON_WRITABLE = set(NON_WRITABLE_PAIRS)

#: **Quadrant one** — the column can be created and its cells cannot be written. Two correct
#: refusals from two different constants; derived, never hand-listed.
AUTHORABLE_BUT_CELLS_UNWRITABLE: Tuple[Tuple[int, str], ...] = tuple(
    pair for pair in NON_WRITABLE_PAIRS if pair[1] in _AUTHORABLE_UI
)

#: **Quadrant two** — neither creatable nor writable. Only a Base copy produces one.
NEITHER_AUTHORABLE_NOR_WRITABLE: Tuple[Tuple[int, str], ...] = tuple(
    pair for pair in NON_WRITABLE_PAIRS if pair[1] not in _AUTHORABLE_UI
)

#: **Quadrant three** — the cells are fully writable and the column cannot be created.
#: Exactly one member, and the reason the two constants must never be conflated.
CELLS_WRITABLE_BUT_FIELD_UNAUTHORABLE: Tuple[Tuple[int, str], ...] = tuple(
    pair for pair in _READ_REGISTRY_PAIRS
    if pair not in _NON_WRITABLE and pair[1] not in _AUTHORABLE_UI
)

#: The one-sentence statement of the crossing, quoted by the registry so the two cannot drift.
QUADRANT_NOTE = (
    "AN AUTHORABLE COLUMN IS NOT A WRITABLE CELL. Whether a column can be CREATED and "
    "whether its cells can be WRITTEN are separate questions with separate answers: a "
    "formula, an auto-number and the four created/modified time and user columns can all be "
    "created while their cells never accept a value, and an Email column is the reverse — "
    "its cells write fine and the column itself cannot be created."
)


#: **The authorable IDENTITIES** — the ``(field_type, ui_type)`` pairs a shipped registry
#: carries *and* whose two coordinates are both inside the server's authoring vocabulary.
#: **Derived** from :data:`larkdocio.base.cells.PAIRS` and
#: :data:`~larkdocio.base.write_vocabulary.NON_WRITABLE_PAIRS` — never hand-listed here, so a
#: pair row added to either registry widens this check for free. Exactly one pair per
#: authorable ``ui_type`` today (24), which is what makes the pair check cost no legitimate
#: column: nothing this library can author is missing its identity row.
AUTHORABLE_PAIRS: Tuple[Tuple[int, str], ...] = tuple(
    dict.fromkeys(
        pair for pair in tuple(_READ_REGISTRY_PAIRS) + tuple(NON_WRITABLE_PAIRS)
        if pair[0] in AUTHORABLE_TYPES and pair[1] in _AUTHORABLE_UI
    )
)


class UnauthorableFieldError(LarkConfigError):
    """A column kind Lark's fields API will not author, refused **locally**.

    Deliberately **not** under ``larkdocio.base.write_cells.BaseWriteRefusal``: that family
    is about a CELL VALUE this library refuses to send, and this one is about a COLUMN this
    library refuses to ask for. Keeping them apart is what stops ``except`` from conflating
    "you cannot create this column" with "you cannot write this cell" — the two are neither
    the same set nor the same question.
    """


class UncapturedFieldPairError(UnauthorableFieldError):
    """A ``(field_type, ui_type)`` IDENTITY no shipped registry carries, refused **locally**.

    Deliberately a **subclass** of :class:`UnauthorableFieldError`: a caller already catching
    the authoring refusal keeps catching this one, and a caller who wants to tell the two
    apart can. The distinction is the fix, not the family — its parent says *"Lark will not
    author this column kind"*, and this says *"the two coordinates you named describe a column
    no capture in this library has ever seen"*. The standing **uncaptured** framing (the same
    one :class:`~larkdocio.base.field_authoring.UncapturedConversionError` carries) applies:
    nobody looked, so nothing is sent, and a committed capture is what changes the answer.
    """


def is_authorable_type(field_type) -> bool:
    """``True`` when ``field_type`` is one of the 20 storage types the API will author."""
    return field_type in AUTHORABLE_TYPES


def is_authorable_ui_type(ui_type) -> bool:
    """``True`` when ``ui_type`` is one of the 24 column kinds the API will author."""
    return ui_type in AUTHORABLE_UI_TYPES


def is_authorable_pair(field_type, ui_type) -> bool:
    """``True`` when the ``(field_type, ui_type)`` identity is carried by a shipped registry.

    Read off :data:`AUTHORABLE_PAIRS` at call time (never a frozen copy), so a registry row
    added later is honoured without touching this function.
    """
    return (field_type, ui_type) in AUTHORABLE_PAIRS


def _pair_refusal(field_type, ui_type) -> str:
    registered_types = [str(t) for t, u in AUTHORABLE_PAIRS if u == ui_type]
    registered_uis = [repr(u) for t, u in AUTHORABLE_PAIRS if t == field_type]
    for_ui = (f"The field type registered for {ui_type!r}: "
              f"{', '.join(registered_types)}. " if registered_types else "")
    for_type = (f"The column kind(s) registered for field type {field_type!r}: "
                f"{', '.join(registered_uis)}. " if registered_uis else "")
    return (
        f"the column identity (field_type={field_type!r}, ui_type={ui_type!r}) is carried by "
        f"no registry in this library, so it will not be sent. A column's identity is the "
        f"PAIR: each coordinate above is inside the server's own authoring vocabulary, but "
        f"this combination of them is one no committed capture has ever shown. "
        f"{for_ui}{for_type}"
        f"Nothing was sent. Lark may well accept a pair this library has not captured — that "
        f"is the accepted cost of refusing on evidence rather than on a guess, and a pair "
        f"enters the registry here the way every other fact in this library does, through a "
        f"committed capture. To create this column meanwhile, do it in the product, where you "
        f"can see what you got."
    )


def _ui_type_refusal(ui_type) -> str:
    accepted = ", ".join(AUTHORABLE_UI_TYPES)
    message = (
        f"the column kind {ui_type!r} is not one Lark's fields API will author. "
        f"{_SERVER_OWNS_THE_LIST} The accepted kinds are: {accepted}."
    )
    guidance = UNAUTHORABLE_GUIDANCE.get(ui_type)
    return f"{message} {guidance}" if guidance else message


def _type_refusal(field_type) -> str:
    accepted = ", ".join(str(t) for t in AUTHORABLE_TYPES)
    return (
        f"the field type {field_type!r} is not one Lark's fields API will author. "
        f"{_SERVER_OWNS_THE_LIST} The accepted types are: {accepted}."
    )


def check_authorable(field_type=None, ui_type: Optional[str] = None) -> None:
    """Refuse — **locally, with no client and no call** — a column this API will not author.

    ``field_type`` and ``ui_type`` are the request's own ``type`` and ``ui_type`` keys; pass
    either, or both, and ``None`` means "not named in this request", which is never refused.
    Returns ``None`` when the request is inside the vocabulary; raises
    :class:`UnauthorableFieldError` otherwise.

    The ``ui_type`` is reported first when both offend, because it is the caller-facing name
    and the one that carries a way forward.

    **A column's identity is the PAIR.** When both coordinates are named and both are
    individually inside the vocabulary, the pair itself is checked against
    :data:`AUTHORABLE_PAIRS` — a third branch, reached only there, raising
    :class:`UncapturedFieldPairError`. Two correct coordinates can still describe a column no
    registry in this library carries (``field_type=1, ui_type="Checkbox"``: ``1`` is Text and
    Checkbox is ``7``), and before LD-292 that went to the wire from the one module whose
    stated purpose is refusing before the call.

    **The accepted trade-off, stated where it is paid.** Lark's pair space is larger than what
    this library has captured, so this check **may refuse a pair Lark itself would accept**
    that no capture has proven. That cost is **accepted** (maintainer ruling, 2026-08-05): the
    capture-wins-over-prose bar that governs conversions and cell writes governs authoring
    identities too. Nothing is guessed and nothing is silently corrected — the refusal says
    what *is* registered for each coordinate, and a pair that turns out to be real enters
    :data:`larkdocio.base.cells.PAIRS` through a committed capture and widens this check
    without a line changing here.
    """
    if ui_type is not None and not is_authorable_ui_type(ui_type):
        raise UnauthorableFieldError(_ui_type_refusal(ui_type))
    if field_type is not None and not is_authorable_type(field_type):
        raise UnauthorableFieldError(_type_refusal(field_type))
    if (field_type is not None and ui_type is not None
            and not is_authorable_pair(field_type, ui_type)):
        raise UncapturedFieldPairError(_pair_refusal(field_type, ui_type))
    return None
