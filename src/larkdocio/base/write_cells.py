"""larkdocio.base.write_cells — the Base ``(type, ui_type)`` WRITE-shape encoder registry.

**The read registry answers "what did Lark send me?"; this one answers "what must I send
Lark?" — and for several types the two are different objects.** A Base cell write is right or
it is a lie that returns ``code:0``: the API accepts unrecognized keys, discards a value for
the opaque type without even moving ``table.revision``, synthesizes an ``mailto:`` prefix
server-side so the read-back shape cannot be fed back in, geocodes a longitude-first literal
but answers an *internal-error* code for the reversed order, and does not enforce a
single-valued link's own cardinality flag. So every shape here is taken **from a committed
capture**, and :data:`CAPTURE_ANCHORS` names the capture file each one came from.

**Why that is a rule rather than a nicety.** The comment-attribution work rides
``extra.notify_extra``, whose keys the prose predicted as ``record_id`` / ``table_id`` /
``view_id``; the wire keys are ``record``, ``table``, ``view``. On the *read* side a predicted
key yields a visibly empty result. On the *write* side it yields ``code:0`` and silence, so a
predicted shape is not a smaller version of the same mistake — it is an invisible one.

**Three kinds of local refusal, all of them before any call is built:**

* :class:`NonWritableFieldError` — one of the eight computed or opaque pairs, imported from
  the shared write vocabulary (:mod:`larkdocio.base.write_vocabulary`) and never re-listed
  here. The opaque one is the proof this matters: five value shapes each answered ``code:0``
  with the table revision provably unmoved, and a record created with such a value came back
  with the key absent from the echo *and* from the read. A library that forwarded that write
  would report success for data loss.
* :class:`UnsupportedFieldTypeError` — a pair no encoder is registered for. This is the whole
  answer for the action-launcher UI type as well: it is a maintainer-ruled will-not-support with a
  read identity and no authoring identity, and it gets **no encoder, no matrix write row and
  no bespoke refusal**, because a bespoke branch would be this library re-opening a ruling
  that an API fact explicitly does not reopen.
* :class:`WriteShapeError` — a writable type handed a value that is not its write shape. Its
  most common cause is the honest one: feeding back what a read returned.

**Ids only, for people (ruled).** A person value is a list of ``{"id": …}`` objects. A
name-shaped argument earns :class:`PersonNameNotResolvableError`, which names the two honest
id sources and points at the account-owner lookup — and **invents nothing else**, because the
other-user name→id gap is deferred for a comprehensive-solution investigation. A lookup table,
a scraped directory or a "best effort" match shipped here would contradict that.

**Cardinality is the server's business, not this module's.** A one-way link field created with
its own single-valued flag set accepted two record ids and echoed both, ``code:0``. So no
encoder enforces a cardinality the server does not, and none assumes one while validating.

Pure and offline: no client, no credential, no call of any kind — which is what makes "the
refusal fired before anything was sent" a testable claim rather than an intention.
"""
from typing import Dict, Mapping, Sequence, Tuple

from larkdocio.base.cells import FieldSpec
from larkdocio.base.write_vocabulary import (
    NON_WRITABLE_PAIRS,
    is_non_writable,
    non_writable_reason,
)
from larkdocio.common.citations import dev_repo
from larkdocio.errors import LarkConfigError

_CAPTURES = "tests/captures/base-study/captures"


class _Omit:
    """The sentinel for *"leave this key out of the request entirely"*."""

    __slots__ = ()

    def __repr__(self):  # pragma: no cover - debugging aid
        return "OMIT"


#: Distinct from ``None``. ``None`` is an explicit clear the caller asked for; :data:`OMIT`
#: means the key never appears in the request — which is also the shape an empty cell **reads
#: back** as (an empty cell is an absent key). Three states, three spellings.
OMIT = _Omit()


class BaseWriteRefusal(LarkConfigError):
    """A Base cell value this library refuses to send, decided **locally**.

    Under :class:`~larkdocio.errors.LarkConfigError` (an unsupported-input problem), so
    ``except LarkConfigError`` / ``except LarkDocIOError`` catch every refusal below.
    """


class NonWritableFieldError(BaseWriteRefusal):
    """The field's type is computed or opaque — the server owns the value."""


class UnsupportedFieldTypeError(BaseWriteRefusal):
    """No encoder is registered for this pair, or no such field is in the schema."""


class WriteShapeError(BaseWriteRefusal):
    """The value is not the write shape for this field's type."""


class PersonNameNotResolvableError(WriteShapeError):
    """A person value arrived name-shaped, and a name is not an id."""


#: Stated once, quoted by ``BASE.md`` (in the source repository) and by the refusal below so the three
#: cannot drift.
EMAIL_IS_NOT_ROUND_TRIPPABLE = (
    "AN EMAIL CELL CANNOT BE ROUND-TRIPPED. You write the address as a PLAIN STRING; Lark "
    "synthesizes the mailto: prefix server-side, and the cell reads back as a url-typed "
    "segment inside a text field. Feeding that read-back shape in again is refused 1254060 "
    "TextFieldConvFail. Note also that the API performs no address validation of its own: a "
    "malformed address is stored, code:0 — so 1254060 was always about the segment SHAPE, "
    "never the format, and this library does not invent a check Lark does not do. Validating "
    "the address is the caller's."
)

#: **The measurement that amends — and does not replace — the Text refusal below (LD-416).**
#: Scoped deliberately: this sentence is spoken for ``(1, "Text")`` and for no other pair,
#: because ``(1, "Text")`` is the only pair anybody probed. It is quoted by the shipped shape
#: docs, so the words a caller reads in the exception and the words the guide shows are one
#: object.
TEXT_SEGMENT_ARRAY_IS_SERVER_REFUSED_TOO = (
    "AND THIS IS NOT ONLY A LOCAL RULE. Fourteen segment spellings were sent to the "
    "record-write routes anyway, and all fourteen are named here because the claim rests on "
    "the enumeration rather than on the number — url-only, mixed text/url/text, "
    "the same text/url/text with its text segments untyped, the reverse order, text-only, an empty array, a mention segment, "
    "and seven malformed variants (a url segment with no link, a link spelled as an empty "
    "string, a segment with its kind unstated, the single segment unwrapped out of its list, "
    "an empty label, a mailto link, and a link with no scheme) — and Lark "
    "answered 1254060 TextFieldConvFail to every one of them, on BOTH the create and the "
    "update route, in a run whose bare-string control answered code:0 on both and read back as "
    "a segment array. So a labeled clickable link is not something this library is withholding: "
    "the platform stores segment arrays and hands them back, and does not take one as a Text "
    "WRITE on those two routes. The edge of that evidence, stated rather than implied, and it "
    "has since moved by exactly one route: records/batch_create has now been asked once, with "
    "the doc-mention chip a Base cell reads back after a human touches a pasted document url, "
    "against a disposable Base — and it answered 1254060 TextFieldConvFail too, so the "
    "refusal is not a property of the single-record routes. Its sibling records/batch_update "
    "and table-creation cell seeding were NOT asked, and a shape nobody sent is UNMEASURED, "
    "not refused. "
    "AND THE SCOPE OF THIS PARAGRAPH, because it has been read wider than it is: every "
    "sentence above is about a BASE Text field on the record create/update routes. It says "
    "nothing about a SPREADSHEET cell, where a labeled clickable link is a shipped write "
    "that works — RichCellWriteRequest.hyperlink(range, link, text=…), worked through in the "
    "guide's section 'Recipe: write a hyperlink and a styled run into a cell'. Two "
    "surfaces, two "
    "answers; this one is the Base's."
)

_PERSON_IDS_ONLY = (
    "A person cell takes IDS ONLY: a list of {\"id\": <open_id>} objects. A display name is "
    "not an id and this library will not turn one into one — the server refuses a name-shaped "
    "value with 1254066 UserFieldConvFail, and inferring which user was meant is exactly "
    "the mistake a silent write makes expensive. Two honest sources of an id: HARVEST it from "
    "a read of a cell that already names the person, or supply one the CALLER already holds. "
    "For the account owner's own id, larkdocio.contacts.resolve_user resolves a name to "
    "exactly one open_id or refuses in a typed way. A FOURTH source, and it is an ADDRESS "
    "route rather than a name one: larkdocio.contacts.resolve_colleague turns an EMAIL (or a "
    "mobile) into exactly one open_id or refuses the same typed way. Resolving an arbitrary "
    "OTHER USER's NAME is still deferred work with its own mandate, and nothing here stands in "
    "for it — an email is not a name, and neither verb stands in for the other."
)

_LOCATION_LITERAL = (
    "A location cell takes ONE literal shape: the string \"<lng>,<lat>\" — longitude first. "
    "Lark geocodes it server-side. An address string, or the {full_address, location} object "
    "a read returns, is refused 1254001 WrongRequestBody naming that format."
)

_LOCATION_REVERSED = (
    "A location cell is \"<lng>,<lat>\" — LONGITUDE FIRST. This value's second number is "
    "outside the latitude range, which is what a reversed pair looks like; sent as-is Lark "
    "answers 1255002, an INTERNAL-error code rather than a validation one, so the refusal is "
    "easy to misread as \"Lark is broken\". Note the limit of this check: a pair whose values "
    "are both in range is indistinguishable from its own reversal, and is sent as given."
)


# --------------------------------------------------------------------------- #
# Small shared helpers                                                         #
# --------------------------------------------------------------------------- #

def _members(value):
    """A multi-valued argument as a tuple, without flattening a mapping into its keys."""
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return (value,)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _refuse(field: FieldSpec, wanted: str, extra: str = "") -> "WriteShapeError":
    """A refusal that names the field, its identity and the wanted shape — and **never the
    value**, which for a person, a chat or an address is exactly the payload the name-only
    doctrine keeps out of messages and logs."""
    detail = f" {extra}" if extra else ""
    return WriteShapeError(
        f"the field {field.field_name!r} ({field.type} / {field.ui_type}) is written as "
        f"{wanted}.{detail}"
    )


# --------------------------------------------------------------------------- #
# The per-pair encoders                                                        #
# --------------------------------------------------------------------------- #

def _e_plain_string(value, field: FieldSpec):
    """A bare string. The read-back is a segment array, which is refused rather than joined:
    the two are different objects and unwrapping one would be a guess about which of its
    members carried the value.

    **Amended, not rewritten (LD-416).** The reason above is unchanged and still decides the
    paste-a-read-back-array case, which is a question about *unwrapping*. A caller handing over
    an explicitly **typed** segment array asks a different question — nothing is being inferred
    — so that question was put to the server, on ``(1, "Text")``, and the server refused every
    spelling of it (:data:`TEXT_SEGMENT_ARRAY_IS_SERVER_REFUSED_TOO`). The conclusion therefore
    does not narrow; what changes is that the refusal now **reports a measurement** instead of
    reading as a policy of ours. That amendment is spoken for ``(1, "Text")`` alone: ``(13,
    "Phone")`` and ``(1, "Barcode")`` share this encoder, nobody probed them, and an evidence
    label may never exceed what it was observed on.
    """
    if isinstance(value, str):
        return value
    extra = ""
    if isinstance(value, (list, tuple, dict)):
        extra = "a segment array is the READ shape; pass the string itself."
        if field.pair == (1, "Text"):
            extra = f"{extra} {TEXT_SEGMENT_ARRAY_IS_SERVER_REFUSED_TOO}"
    raise _refuse(field, "a plain string", extra)


def _e_email(value, field: FieldSpec):
    """The address as a plain string; the server adds the prefix."""
    if isinstance(value, str):
        return value
    raise _refuse(field, "a plain string — the address itself", EMAIL_IS_NOT_ROUND_TRIPPABLE)


def _e_option_name(value, field: FieldSpec):
    """One option **name**, as a bare string."""
    if isinstance(value, str):
        return value
    raise _refuse(field, "one option name, as a bare string")


def _e_option_names(value, field: FieldSpec):
    """A **list** of option names. A bare string is refused rather than wrapped: a
    single-option write is one character away and a wrap would be this module deciding what
    the caller meant."""
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        return list(value)
    raise _refuse(field, "a list of option names")


def _e_ms_epoch(value, field: FieldSpec):
    """Milliseconds since the epoch, as an ``int``.

    No date-like object is converted, because every conversion needs a zone and this module
    has no business choosing one.

    **That refusal is measured-correct and stays** (LD-463, probe ``ld463-01``): Lark stores the
    integer **verbatim** — 21 of 21 records read back what was sent — so nothing is lost by
    handing it the instant, and a zone this encoder invented would decide the calendar date on
    the caller's behalf. The other half of the same policy is where the zone *does* belong: the
    Base's create declares it, once, and the read side renders in it. One statement, both sides:
    :mod:`larkdocio.base.date_zone`.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise _refuse(field, "an integer number of MILLISECONDS since the epoch")


def _e_bool(value, field: FieldSpec):
    """``True`` / ``False``. ``False`` is a real write; it simply **reads back as an absent
    key**, which is the read side's own answer and not this encoder's problem."""
    if isinstance(value, bool):
        return value
    raise _refuse(field, "a boolean")


def _e_number(value, field: FieldSpec):
    """A JSON number. Presentation — the formatter, the currency code, the rating symbol —
    lives on the field's own configuration and is never encoded into the value."""
    if _is_number(value):
        return value
    raise _refuse(field, "a JSON number")


def _e_url_object(value, field: FieldSpec):
    """``{"link": …, "text": …}``.

    The read-back carries a third key naming the segment kind; it is dropped here — a
    deliberate normalization between two captured shapes, not a guess. A bare string is taken
    as a link that labels itself.
    """
    if isinstance(value, str):
        return {"link": value, "text": value}
    if isinstance(value, Mapping) and value.get("link"):
        link = value["link"]
        text = value.get("text")
        return {"link": link, "text": link if text is None else text}
    raise _refuse(field, 'a {"link": …, "text": …} object')


def _e_attachments(value, field: FieldSpec):
    """``[{"file_token": …}]``. A bare list of tokens is refused by the server (1254069), so
    the encoder builds the objects; the caller may pass either form.

    The read-back's name, size, type and its two **short-lived signed CDN links** are dropped:
    only the token is a write input, and the links are not something to echo back anywhere.
    Uploading the bytes is a separate leg this module has no part in — the token is the
    caller's.
    """
    out = []
    for item in _members(value):
        if isinstance(item, str) and item:
            out.append({"file_token": item})
        elif isinstance(item, Mapping) and item.get("file_token"):
            out.append({"file_token": item["file_token"]})
        else:
            raise _refuse(field, 'a list of {"file_token": …} objects (or of bare tokens)',
                          "a bare list of tokens is refused 1254069 AttachFieldConvFail.")
    return out


def _e_link_ids(value, field: FieldSpec):
    """A **bare** list of record ids — ``["rec…"]``.

    The read returns an object keyed on the ids instead, and the create echo returns the bare
    list, so two of the three shapes look alike and the third is the one a round-trip hands
    you. The read object is refused rather than unwrapped, which is what keeps the asymmetry
    visible at the seam where it bites.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        return list(value)
    raise _refuse(field, "a bare list of record ids",
                  'the read shape is {"link_record_ids": […]}; pass the list itself.'
                  if isinstance(value, Mapping) else "")


def _e_location(value, field: FieldSpec):
    """``"<lng>,<lat>"`` and nothing else."""
    if not isinstance(value, str):
        raise _refuse(field, "a coordinate string", _LOCATION_LITERAL)
    parts = value.split(",")
    if len(parts) != 2:
        raise _refuse(field, "a coordinate string", _LOCATION_LITERAL)
    try:
        lng, lat = (float(part.strip()) for part in parts)
    except ValueError:
        raise _refuse(field, "a coordinate string", _LOCATION_LITERAL) from None
    if not (-180.0 <= lng <= 180.0) or not (-90.0 <= lat <= 90.0):
        raise _refuse(field, "a coordinate string", _LOCATION_REVERSED)
    return value


def _e_chat_ids(value, field: FieldSpec):
    """``[{"id": …}]``. A bare list of ids is refused by the server — *"must be a list of
    object"* (1254001) — so the encoder builds the objects and accepts either form."""
    out = []
    for item in _members(value):
        if isinstance(item, str) and item:
            out.append({"id": item})
        elif isinstance(item, Mapping) and item.get("id"):
            out.append({"id": item["id"]})
        else:
            raise _refuse(field, 'a list of {"id": …} objects',
                          "a bare list of ids is refused 1254001 — the value must be a list "
                          "of objects.")
    return out


def _e_person_ids(value, field: FieldSpec):
    """``[{"id": <open_id>}]`` — **ids only** (ruled).

    Everything the read-back carries besides the id — the display names, the address, the
    avatar link — is dropped: none of it is a write input, and none of it belongs in a
    request this library builds.

    **Where the local refusal stops, stated rather than implied.** A value carrying a name and
    no id, or a string with whitespace in it, is name-shaped and is refused here, before
    anything is sent. A single-token display name is indistinguishable from an id and is sent
    as one, where the server refuses it 1254066. That boundary is honest; a heuristic that
    tried to close it would be the guess this refusal exists to prevent.
    """
    out = []
    for item in _members(value):
        if isinstance(item, Mapping):
            identity = item.get("id")
            if not identity:
                raise PersonNameNotResolvableError(_PERSON_IDS_ONLY)
            out.append({"id": identity})
        elif isinstance(item, str) and item and not any(ch.isspace() for ch in item):
            out.append({"id": item})
        else:
            raise PersonNameNotResolvableError(_PERSON_IDS_ONLY)
    return out


# --------------------------------------------------------------------------- #
# THE REGISTRY — 19 writable pairs                                             #
# --------------------------------------------------------------------------- #

#: One entry per writable ``(type, ui_type)``, in the read registry's own (picker) order so
#: ``BASE.md`` (in the source repository) and this table read the same way. **19 pairs** — the read
#: registry's 27 minus the 8 the shared vocabulary declares computed or opaque. The 4 pairs
#: that share storage type 2 share one encoder; presentation lives on the field, never in the value.
_ENCODERS = {
    # ── Basic ────────────────────────────────────────────────────────────────
    (1, "Text"): _e_plain_string,
    (3, "SingleSelect"): _e_option_name,
    (4, "MultiSelect"): _e_option_names,
    (11, "User"): _e_person_ids,
    (23, "GroupChat"): _e_chat_ids,
    (5, "DateTime"): _e_ms_epoch,
    (17, "Attachment"): _e_attachments,
    (2, "Number"): _e_number,
    (7, "Checkbox"): _e_bool,
    (15, "Url"): _e_url_object,
    # ── Business ─────────────────────────────────────────────────────────────
    (13, "Phone"): _e_plain_string,
    (1, "Email"): _e_email,
    (22, "Location"): _e_location,
    (1, "Barcode"): _e_plain_string,
    (2, "Progress"): _e_number,
    (2, "Currency"): _e_number,
    (2, "Rating"): _e_number,
    # ── Advanced ─────────────────────────────────────────────────────────────
    (21, "DuplexLink"): _e_link_ids,
    (18, "SingleLink"): _e_link_ids,
}

#: Every pair a value can be written to, in registry order.
WRITABLE_PAIRS: Tuple[Tuple[int, str], ...] = tuple(_ENCODERS)

#: **The capture each write shape was taken from — a filename, not a provenance claim.** A
#: predicted wire key answers ``code:0`` and stores nothing, so an encoder with no anchor is a
#: guess with a docstring; the suite resolves every one of these on disk.
CAPTURE_ANCHORS: Dict[Tuple[int, str], str] = {
    (1, "Text"): "p1-q6-01-value-writes.json",
    (1, "Barcode"): "p0-5-01-scalar-read-encodings.json",
    (1, "Email"): "p1-q6-01-value-writes.json",
    (13, "Phone"): "06-02-record-create-echo.json",
    (3, "SingleSelect"): "05-06-records-batch-create.json",
    (4, "MultiSelect"): "05-06-records-batch-create.json",
    (5, "DateTime"): "05-06-records-batch-create.json",
    (7, "Checkbox"): "06-02-record-create-echo.json",
    (2, "Number"): "05-06-records-batch-create.json",
    (2, "Progress"): "05-06-records-batch-create.json",
    (2, "Currency"): "p0-5-01-scalar-read-encodings.json",
    (2, "Rating"): "p0-5-01-scalar-read-encodings.json",
    (15, "Url"): "05-06-records-batch-create.json",
    (17, "Attachment"): "p0-4-01-attachment-population.json",
    (18, "SingleLink"): "p0-2-04-link-write-echo.json",
    (21, "DuplexLink"): "p0-2-04-link-write-echo.json",
    (22, "Location"): "p0-4-02-location-population.json",
    (23, "GroupChat"): "p0-4-03-groupchat-population.json",
    (11, "User"): "ld256-01-person-write-shapes.json",
}


def encoder_for(type_: int, ui_type: str):
    """The encoder for a ``(type, ui_type)`` pair, or ``None`` if none is registered."""
    return _ENCODERS.get((type_, ui_type))


def capture_anchor(type_: int, ui_type: str):
    """The capture file a pair's write shape was taken from.

    A path in the maintainer's repository, labelled as such — the wheel does not carry
    the captures, so the pointer is provenance rather than a file you can open.
    """
    name = CAPTURE_ANCHORS.get((type_, ui_type))
    return dev_repo(f"{_CAPTURES}/{name}") if name else None


def is_writable(pair) -> bool:
    """``True`` when a value can be written to this ``(type, ui_type)`` pair."""
    try:
        return tuple(pair) in _ENCODERS
    except TypeError:
        return False


def nearest_registered(type_: int, ui_type: str) -> str:
    """Which **coordinate** of an unregistered pair is the wrong one, in one clause.

    A pair is two coordinates, and an unregistered pair reads as *"this library cannot write
    this kind of field"* when usually only one of the two is wrong — a ``ui_type`` carried
    under a field_type it never has, or a field_type spelled against the wrong ``ui_type``.
    The answer is already in the registries, so it is **derived** from them (the write
    encoders, then the computed / opaque set) rather than restated as a table of guesses.
    Returns ``""`` when neither coordinate is known — an honest "never seen this".
    """
    for registry, writable in ((_ENCODERS, True), (NON_WRITABLE_PAIRS, False)):
        registered = [t for t, u in registry if u == ui_type and t != type_]
        if registered:
            where = ", ".join(str(t) for t in registered)
            if writable:
                return (f"; {ui_type!r} is registered at field_type {where}, not {type_} — "
                        "the field_type is the coordinate that does not match")
            return (f"; {ui_type!r} is registered at field_type {where}, where it is not "
                    "writable at all, and not at " f"{type_}")
    spellings = sorted({u for t, u in _ENCODERS if t == type_}
                       | {u for t, u in NON_WRITABLE_PAIRS if t == type_})
    if spellings:
        names = ", ".join(repr(u) for u in spellings)
        return (f"; field_type {type_} is registered as {names} — the ui_type is the "
                "coordinate that does not match")
    return ""


def encode_cell(value, field: FieldSpec):
    """One caller value → the wire value for ``field``, or a typed local refusal.

    ``None`` passes through as an explicit clear — distinct from :data:`OMIT`, which belongs
    to :func:`encode_fields` and means the key is left out of the request entirely.
    """
    if value is OMIT:
        raise UnsupportedFieldTypeError(
            "OMIT is a whole-request instruction: pass it through encode_fields, which leaves "
            "the key out, rather than to a single cell")
    if is_non_writable(field.pair):
        raise NonWritableFieldError(
            f"the field {field.field_name!r} ({field.type} / {field.ui_type}) cannot be "
            f"written. {non_writable_reason(field.pair)}")
    encoder = _ENCODERS.get(field.pair)
    if encoder is None:
        raise UnsupportedFieldTypeError(
            f"the field {field.field_name!r} has the identity ({field.type} / "
            f"{field.ui_type}), which this library registers no write encoding for"
            f"{nearest_registered(field.type, field.ui_type)}")
    if value is None:
        return None
    return encoder(value, field)


def encode_fields(values: Mapping[str, object], fields: Sequence[FieldSpec]) -> dict:
    """A caller's ``{field_name: value}`` mapping → the ``fields`` body of a record write.

    Keyed on the **field name**, which is what a record write is keyed on. Every name must be
    in ``fields`` — the table's own schema — because a name the schema does not know is
    silently ignored by the server, which is the R12 failure in its write costume.

    Three states are kept apart: a value of ``None`` is written as an explicit clear, ``""``
    is a real empty string, and :data:`OMIT` (or simply not naming the key) leaves the key out
    of the request altogether.
    """
    schema = {spec.field_name: spec for spec in fields}
    out = {}
    for name, value in values.items():
        spec = schema.get(name)
        if spec is None:
            raise UnsupportedFieldTypeError(
                f"no field named {name!r} is in this table's schema; a name the schema does "
                "not know is silently ignored by the server, so it is refused here instead")
        if value is OMIT:
            continue
        out[name] = encode_cell(value, spec)
    return out
