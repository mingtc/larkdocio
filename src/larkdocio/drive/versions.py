"""larkdocio.drive.versions — a file's **named versions**: list them, create one.

A consumer's ingestion ledger wants to pin a *semantic* version of a document ("V1.3") rather
than a keystroke counter, and the numeric head ``revision_id`` cannot carry that. Lark's
``file_version`` family can:

* ``GET /open-apis/drive/v1/files/{token}/versions`` — a file's named versions, paged. Shipped
  as :meth:`larkdocio.drive.client.DriveClient.list_versions` (a **read**, on the READ pair);
* ``POST`` on the same path — creates one. Additive, name-required, **revision-inert**. Shipped
  as :meth:`larkdocio.drive.versions_write.DriveVersionsWriteClient.create_version` (a
  **write**, on the WRITE pair, and the Drive surface's **first mutating op**).

**This module is the READ-SAFE half** — the model, the absences and the ``obj_type`` / ``name``
policy both halves share. The mutating client lives in
:mod:`larkdocio.drive.versions_write`, because the read client is on the command line's own
import path and no console command reaches this write engine — the one console verb that
writes, ``roundtrip push --apply``, writes to a docx, guarded **in the source repository** by
``tests/front_door.py::write_reach_paths_bypassing()``, plus the per-command leg
``tests/test_cli_front_door_truth.py::test_ac1_the_reading_commands_own_handlers_reach_NO_write_module``,
and that guard says so.

**Everything stated here was measured** by the editions probe, whose captures are cited per
claim below by their number. Nothing is inferred from documentation, and the two things the
probe did **not** establish — the ``status`` vocabulary and any quota — are labelled
``unmeasured`` rather than filled in.

**What is NOT here, deliberately.** ``delete_version`` is measured working and does **not**
ship (see this project's decision register and the Drive capability matrix): deleting a named
version on a real user's document is a destruction this surface has measured no restore verb
for.
``GET …/versions/{version}`` (fetch one) is measured and cheap, and nobody asked for it.
Resolving a version token to *content* is a measured refusal, stated where the
Drive surface records its boundaries rather than attempted here.
"""
import datetime
from dataclasses import dataclass
from typing import NamedTuple, Optional, Tuple

from larkdocio.common.citations import dev_repo
from larkdocio.drive import ops
from larkdocio.drive.errors import DriveError

#: The **ten** fields a version object carries, read off the captures rather than curated.
#: ``token`` is the payload's ``version`` key — see :class:`Version` for the rename.
VERSION_FIELDS = (
    "token", "name", "create_time", "update_time", "creator_id", "owner_id",
    "obj_type", "parent_token", "parent_type", "status",
)

#: The payload key :class:`Version` renames — **once, here**. Lark calls the token ``version``,
#: which reads as "the version object" at every call site that touches it; the model calls it
#: ``token`` because that is what every other Lark identifier in this library is called.
PAYLOAD_TOKEN_KEY = "version"

#: What a version object does **not** carry, each with the consequence of assuming it did. A
#: ledger built on a guessed field mis-syncs invisibly, which is why these are data (and
#: asserted against the captures) rather than prose someone may not read.
ABSENCES = {
    "revision_id": (
        "THE make-or-break absence. A version object carries no revision at all, and a "
        "version token cannot be resolved to a revision or to content by any route tried "
        "(the probe tried the token as document_revision_id, as a document_id, and on the "
        "export-task and raw-content routes; all refused or ignored it). So a version name "
        "cannot be turned back into the bytes it named. Pair the name with a revision at "
        "CREATE time — create_version does exactly that — or the link is not recoverable "
        "later."),
    "url": (
        "no deep link to a version is served, so one cannot be handed to a human; the "
        "parent document's own URL is the only link this family yields"),
    "description": "no free-text field beyond the name — a name is the whole of the metadata",
    "size": "no byte size, so a version cannot be costed before it is fetched",
    "document_id": (
        "no alias of the parent under the docx family's own key; ``parent_token`` is the "
        "parent, and reading it as a docx ``document_id`` is the caller's own step"),
    "creator_name": (
        "the creator arrives as a raw ``creator_id`` open_id only — no display name, so "
        "showing a person needs the contacts surface and its own scope"),
    "is_latest": (
        "no 'is latest' marker on any version, so 'the newest' is a decision the caller "
        "makes from ``create_time`` (this library sorts by it; see list_versions)"),
}

#: ``status`` was ``0`` on **every** version observed, and no other value was elicited. So its
#: vocabulary is exactly this: unmeasured. It is never enumerated, and ``0`` is never given a
#: meaning this project cannot support.
STATUS_VOCABULARY = "unmeasured"

#: The default, and the only ``obj_type`` this library's own reader ecosystem centres on.
DOCX_OBJ_TYPE = "docx"


class RefusedObjType(NamedTuple):
    """One ``obj_type`` value **measured** being refused, with Lark's own body verbatim."""

    code: int
    msg: str
    capture: str


#: **Measured accepted** — ``docx`` (capture ``07-``) and ``sheet`` (``402-``, ``405-``, on a
#: disposable spreadsheet).
MEASURED_ACCEPTED_OBJ_TYPES = ("docx", "sheet")

#: **Measured refused** — refused locally, before the call, quoting Lark's own body. Two values,
#: and only two: this table grows by measurement, never by inference.
MEASURED_REFUSED_OBJ_TYPES = {
    "bitable": RefusedObjType(
        1068411, "params error, param [obj_type] is wrong",
        dev_repo("tests/captures/editions-spike/captures/308-")),
    "sheets": RefusedObjType(
        99992402, "field validation failed",
        dev_repo("tests/captures/editions-spike/captures/403-")),
}

#: Lark's own answer when ``obj_type`` is omitted (capture ``11-``) — mirrored, not invented.
OBJ_TYPE_REQUIRED_REFUSAL = (
    "99992402 field validation failed: obj_type is required. larkdocio always sends "
    "obj_type; pass one of the measured-accepted values "
    f"{MEASURED_ACCEPTED_OBJ_TYPES}.")

#: Lark's own answer when ``name`` is missing (capture ``04-``) — mirrored, not invented.
NAME_REQUIRED_REFUSAL = (
    "252804105 Params error, param [name] is wrong. A version must be named; larkdocio "
    "refuses an empty name here rather than spending a call to be told the same thing.")

#: The exactness condition of the ``(name, token, revision)`` triple, **as measured**: head
#: revision ``2`` before the create and ``2`` after it (captures ``101-`` / ``103-``).
PAIRING_EXACTNESS = (
    "creating a version is revision-inert — the head revision measured the same immediately "
    "before and immediately after the create — so the (name, token, revision) triple is exact "
    "absent a concurrent edit, and a concurrent edit is the one thing that can make it wrong"
)

#: Why no revision is paired for a non-docx file. A ``sheet`` version has no docx revision, so
#: none is read and none is invented.
REVISION_UNAVAILABLE_NOT_DOCX = (
    "no docx head revision was read: obj_type is {obj_type!r}, and the one-call docx meta read "
    "answers only for a docx. The version itself is unaffected; only the pairing is absent."
)

#: Why no revision is paired when the read itself failed. ``None`` means **not known** — never
#: a synthesized number, and never zero (which is a revision a real document can hold).
REVISION_UNAVAILABLE_READ_FAILED = (
    "the head revision could not be read immediately before the create: {error}. The version "
    "was created; the pairing is absent rather than guessed."
)


def _epoch_seconds_to_utc(value: Optional[str]) -> Optional[datetime.datetime]:
    """THE one conversion, in one place: a string of **epoch seconds** → an aware UTC datetime.

    Lark serves ``create_time`` / ``update_time`` as strings of epoch **seconds**
    (``"1786403223"``, capture ``07-``) — not milliseconds, not ISO — and serves **no timezone
    field**. Epoch is UTC by definition, so the conversion anchors there and assumes nothing;
    rendering it in a local zone is the caller's decision, made with information this library
    does not have. A value that is not an epoch string converts to ``None`` (not known) rather
    than to a guess.
    """
    if value in (None, ""):
        return None
    try:
        seconds = int(str(value))
    except (TypeError, ValueError):
        return None
    try:
        return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc)
    except (OverflowError, OSError, ValueError):  # pragma: no cover - absurd epoch
        return None


@dataclass(frozen=True)
class Version:
    """One **named version** of a Drive file, exactly as Lark described it.

    The fields are exactly what was measured — ``token`` (the payload's ``version`` key,
    renamed once, here, and stated so a reader meets the rename rather than discovering it),
    ``name``, ``create_time``, ``update_time``, ``creator_id``, ``owner_id``, ``obj_type``,
    ``parent_token``, ``parent_type``, ``status``.

    **Times are strings of epoch SECONDS, carried as served** — ``"1786403295"``, not
    milliseconds, not ISO — and **no timezone field is served**. :attr:`created_at` /
    :attr:`updated_at` are the one honest conversion (UTC-anchored, because epoch is),
    performed once by :func:`_epoch_seconds_to_utc`.

    **``update_time`` is present on LIST and on GET and ABSENT from the CREATE echo.** It is
    reported ``None`` there rather than defaulted to ``create_time``: a version that has never
    been updated has no update time, and copying one in would invent an event.

    **``status`` is ``0`` on every version observed and no other value was elicited**, so its
    vocabulary is ``unmeasured`` (:data:`STATUS_VOCABULARY`). It is deliberately not
    enumerated and ``0`` is deliberately not given a meaning.

    **What a version object does NOT carry** — stated because a ledger built on a guessed field
    mis-syncs invisibly, and each absence carries its consequence in :data:`ABSENCES`: no
    ``revision_id`` (a version token cannot be resolved to a revision or to content by any
    route tried; this is why the create op pairs
    the new token with the head revision at creation time), no ``url``, no ``description``, no
    ``size``, no ``document_id`` alias, no creator display name (``creator_name``), and no
    ``is_latest`` marker.
    """

    token: str
    name: Optional[str] = None
    create_time: Optional[str] = None
    update_time: Optional[str] = None
    creator_id: Optional[str] = None
    owner_id: Optional[str] = None
    obj_type: Optional[str] = None
    parent_token: Optional[str] = None
    parent_type: Optional[str] = None
    status: Optional[int] = None

    @classmethod
    def from_payload(cls, payload: dict) -> "Version":
        """Build from Lark's own object — the ``version`` → ``token`` rename happens here."""
        values = {name: payload.get(name) for name in VERSION_FIELDS if name != "token"}
        return cls(token=payload.get(PAYLOAD_TOKEN_KEY), **values)

    @property
    def created_at(self) -> Optional[datetime.datetime]:
        """:attr:`create_time` as an aware **UTC** datetime, or ``None`` if unparseable."""
        return _epoch_seconds_to_utc(self.create_time)

    @property
    def updated_at(self) -> Optional[datetime.datetime]:
        """:attr:`update_time` as an aware **UTC** datetime — ``None`` on a CREATE echo, which
        carries no ``update_time`` at all."""
        return _epoch_seconds_to_utc(self.update_time)

    def _sort_key(self):
        """Newest first, ties broken deterministically by token — see ``list_versions``."""
        seconds = _epoch_seconds_to_utc(self.create_time)
        return (-(seconds.timestamp() if seconds else 0.0), self.token or "")


@dataclass(frozen=True)
class VersionListing:
    """A file's named versions — **one list**, plus the truncation that fired collecting it.

    Iterable, sized and indexable, so a caller reads it as the list it is; the extra fields
    exist so a page budget that fires cannot be lost between the client and its caller (the
    Drive surface's standing rule: a cap that fires is visible in the output).
    """

    file_token: str
    obj_type: str
    versions: Tuple[Version, ...] = ()
    pages: int = 0
    truncation: Optional[object] = None

    def __iter__(self):
        return iter(self.versions)

    def __len__(self):
        return len(self.versions)

    def __getitem__(self, index):
        return self.versions[index]


class VersionRefusedError(DriveError):
    """A refusal larkdocio can make **locally**, in Lark's own words, before spending a call.

    Only ever raised for something *measured*: a missing ``obj_type`` / ``name`` and the two
    ``obj_type`` values observed being refused. An **unmeasured** value is never refused here —
    it goes on the wire and Lark answers, because a limit this library never observed is not
    this library's to assert.
    """

    def __init__(self, message, *, code=None, msg=None, value=None):
        super().__init__(message, code=code, msg=msg)
        self.value = value


def check_obj_type(obj_type) -> str:
    """The ``obj_type`` gate: required, two measured refusals, everything else passed through.

    Returns the value to put on the wire. Raises :class:`VersionRefusedError` for an absent
    value and for the two values **measured** being refused; an unmeasured value is returned
    unchanged, so Lark — not larkdocio — answers for it.
    """
    if not obj_type or not str(obj_type).strip():
        raise VersionRefusedError(OBJ_TYPE_REQUIRED_REFUSAL, code=99992402,
                                  msg="field validation failed", value=obj_type)
    value = str(obj_type)
    refused = MEASURED_REFUSED_OBJ_TYPES.get(value)
    if refused is not None:
        raise VersionRefusedError(
            f"Lark refuses obj_type={value!r} on the file-versions family: "
            f"{refused.code} {refused.msg} (measured, {refused.capture}). Measured accepted: "
            f"{MEASURED_ACCEPTED_OBJ_TYPES}.",
            code=refused.code, msg=refused.msg, value=value)
    return value


def check_name(name) -> str:
    """The ``name`` gate: required, refused locally in Lark's own words (capture ``04-``)."""
    if name is None or not str(name).strip():
        raise VersionRefusedError(NAME_REQUIRED_REFUSAL, code=252804105,
                                  msg="Params error, param [name] is wrong.", value=name)
    return str(name)


def versions_path(file_token) -> str:
    """The tokenised wire path for one file's versions.

    The registry's own shape (:data:`larkdocio.drive.ops.FILE_VERSIONS_ENDPOINT`) with the
    token substituted — so the constant a permission derivation can *see* in the source stays
    the single naming of this endpoint.
    """
    return ops.FILE_VERSIONS_ENDPOINT.replace(":file_token", str(file_token))


