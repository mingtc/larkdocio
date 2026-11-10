"""Keep the read you already paid for — one checksummed file, rehydrated exactly.

Every write integration this library serves begins with a read it then throws away. The
block-id projection an editing agent works from is derived from a tree that lived only in one
process's memory, so a crash, a handoff between processes, a queued review, or simply coming
back tomorrow costs a fresh download — and a fresh download is a **different document**:
revisions move, mention resolution can degrade, and the projection the agent's edits were made
against no longer exists to reconcile them with.

:func:`snapshot` writes the lossless read — the **raw block payloads**, the
``document_revision_id`` they were read at, the **document token**, and the **API domain** the
read was taken against — into one versioned, checksummed artefact. :func:`load` brings it back,
offline, and rehydrates it to the same node tree
:meth:`~larkdocio.read.parser.Parser.parse_docx_tree` produced::

    from larkdocio.snapshot import snapshot, load
    from larkdocio.model import project_block_ids

    docx, blocks = client.get_docx_content(token)
    snapshot(blocks, document_token=docx.document_id,
             document_revision_id=docx.revision_id, api_domain=domain,
             path="doc.larkdocio.json")

    # …a day later, another process, no network …
    kept = load("doc.larkdocio.json")
    projection = project_block_ids(kept.tree)          # byte-identical to the original
    client = Client(app_id, app_secret, kept.api_domain)   # …and the successor can call

**THE GUARANTEE — a load-then-project is byte-identical to the original projection.** Not
structurally equal: the same bytes. That is the whole point, because the reason to keep a read
is so that an agent's edits — made against a projection, reconciled by text — still line up
against a projection taken from the file a day later. (Byte-identity holds for the same
``use_html_tags`` setting and the same reader
:class:`~larkdocio.read.config.Config`; hand ``load`` the config the read used if it was not
the default.)

**THE SHAPE OF THE FLOW, WHICH THIS DOES NOT CHANGE.** The snapshot is **ours and immutable**;
the **Markdown draft is theirs and editable**; the boundary between them is
:func:`~larkdocio.write.reconcile.reconcile`. The only supported way to turn caller intent into
a write is unchanged and unwidened::

    project_block_ids(...) → the caller edits the MARKDOWN → reconcile()
        → compile_reconciliation() → dry_run() → apply()

There is deliberately **no mutable tree API** here — no setter, no in-place edit helper, no
"patch the snapshot" verb — and nothing in this module accepts a caller-mutated tree. A file on
disk that anybody could hand back edited would be a second source of truth whose divergence
from Lark nobody could detect. What this module does is make the **left** side of that flow
survivable across time and processes, and nothing else.

**INTEGRITY, NEVER ENCRYPTION.** The checksum answers accidental corruption and answers
nothing else: **no security boundary exists between a local library and the caller** — the
caller owns the file, the process and the disk — so the threat modelled here is a truncated
write, a half-synced cloud folder, a corrupted disk, or a hand-edited file. There is no
encryption, no key material and no access control anywhere in this module, and the digest is
not a signature: it says the bytes are the bytes that were written, and says nothing about who
wrote them.

**A corrupted snapshot is REFUSED, TYPED, and never repaired.** A checksum mismatch, a
truncation, an unrecognized format version and malformed content each raise
:class:`~larkdocio.errors.LarkSnapshotIntegrityError` naming what failed and naming the fix —
**re-download the document**. Exactly-one-or-refuse: no repair, no salvage, no best-effort
load, and never a partially-rehydrated tree.

**THE REVISION TRAVELS, AND HERE IS WHAT IT IS FOR.** ``document_revision_id`` is the value a
caller hands to ``dry_run(..., document_revision_id=…)`` to arm the ``STALE_DOCUMENT``
whole-document compare-and-swap. So a snapshot goes **stale** the moment somebody edits the
document, and the correct behaviour then is the guard **refusing the batch** — not this library
quietly reconciling against an old world. **A snapshot is not a lock: it does not reserve the
document, does not block anyone, and does not notice an edit.** It records what was true when
it was taken.

**And the anchor can be absent.** A snapshot taken without a revision persists ``None``; a plan
built from it then reports its ``revision_guard`` as ``unavailable`` rather than ``active``, and
the compare-and-swap is **not armed at all** — nothing raises, and nothing warns at write time.
So a caller who wants the guard passes the ``revision_id`` the read handed back when taking the
snapshot.

**THE DOMAIN TRAVELS TOO, AND IT IS THE ONE FACT A SUCCESSOR CANNOT DERIVE.** A document token
does not say whether it lives on ``larksuite.com`` or on ``feishu.cn``, and neither does a
revision or a block payload — so a process holding only the artefact could rehydrate the tree
and still have nothing to build a client with. ``api_domain`` closes that: it is written
**inside** ``payload``, under the same digest as the token and the revision, and comes back as
:attr:`Snapshot.api_domain`. It is a **routing fact, not a credential** — no app id, no secret,
no access token and no other secret is written into a snapshot, ever.

**An artefact that carries no domain says so, and still loads.** ``api_domain`` is ``None``
when the snapshot was taken without one *and* when it was written by a release older than the
field (1.33.0 and earlier, whose payload has no such key). Both load without raising, and
neither is filled in with a default: the two domains are two different tenants, so a guess
would point a successor at the wrong company's document. The ``format_version`` did **not**
move for this field — it is additive and optional, and the digest is taken over the payload's
own content — so an older release also still reads an artefact this one writes, ignoring the
key it does not know.

**WHAT THIS DOES NOT DO — enumerated, and scoped to the evidence.**

* **No cross-version migration is offered.** A ``format_version`` this release does not
  recognize is **refused**, never upgraded in place, in either direction. Migrating one would
  be a change that ships with its own tests.
* **A snapshot of a document whose blocks Lark later changes shape for is `unmeasured`.** The
  payload is pinned exactly as it arrived; what may drift is the *parser* that reads it back.
  No round trip across such a change has been measured, so nothing is claimed about it either
  way.
* **docx only.** **sheets** workbooks, **base** tables and **folder** walks are **not covered**
  here — this module persists a docx block read and says so rather than leaving parity to be
  assumed. A parity ask is separate work with its own evidence.
* **Concurrent writers to the same snapshot file are `unmeasured`, and this module
  does not lock.** Writing to a path replaces it atomically (a temporary file in the same
  directory, then :func:`os.replace`), which is what keeps a half-written artefact from
  replacing a good one; coordinating two processes that both want the same path is the
  caller's.
* **No cache, no index, no store, no sync loop, and no call.** One file, written when asked and
  read when asked. Nothing here refreshes, invalidates, or asks Lark whether the snapshot is
  still current — this module reaches **no endpoint** and needs **no credentials**.
"""
import dataclasses
import hashlib
import json
import os
import tempfile
from pathlib import Path as _Path
from typing import Any as _Any
from typing import Optional as _Optional
from typing import Tuple as _Tuple

from lark_oapi.api.docx.v1.model.block import Block as _Block
from lark_oapi.core.json import JSON as _SDK_JSON

from larkdocio.errors import LarkConfigError as _LarkConfigError
from larkdocio.errors import LarkSnapshotIntegrityError
from larkdocio.model.nodes import Node as _Node
from larkdocio.read.config import Config as _Config
from larkdocio.read.parser import Parser as _Parser

__all__ = [
    "SNAPSHOT_FORMAT_VERSION",
    "SNAPSHOT_INTEGRITY_CONTRACT",
    "LarkSnapshotIntegrityError",
    "Snapshot",
    "load",
    "snapshot",
]

#: The artefact's format version. Bumped only by a change to the layout below; an artefact
#: carrying anything else is refused rather than migrated.
SNAPSHOT_FORMAT_VERSION = 1

#: The capability-registry id of the refusal contract this module keeps
#: (``larkdocio.capabilities()``). Spelled once, imported by the declaration site.
SNAPSHOT_INTEGRITY_CONTRACT = "snapshot-integrity-refusal"

_ENVELOPE_KEY = "larkdocio_snapshot"
_CHECKSUM_ALGORITHM = "sha256"

#: Appended to every refusal, from one place, so a refusal cannot ship without its fix.
_THE_FIX = (
    "Re-download the document and take a fresh snapshot — a snapshot is never repaired, "
    "salvaged, or partially loaded."
)

_WHY_A_CHECKSUM = (
    "INTEGRITY, NEVER ENCRYPTION. No security boundary exists between a local library and "
    "the caller, who owns this file, the process and the disk; the threat this digest answers "
    "is accidental corruption — a truncated write, a half-synced cloud folder, a corrupted "
    "disk, a hand-edited file — and it answers nothing else. It is not a signature and says "
    "nothing about who wrote the file."
)

_COVERS = (
    "the CONTENT of `payload` (the block payloads, the document token, the "
    "document_revision_id and the api_domain the read was taken against), canonicalized — "
    "keys sorted, no insignificant whitespace — so reformatting this file is not corruption, "
    "while any change to a block, the token, the revision or the domain is."
)

_DOES_NOT_COVER = (
    "this envelope's own fields — `format_version` and this `integrity` block itself, which "
    "are checked by the version check and by the digest comparison rather than by the digest "
    "value; and anything outside this file, including images or board PNGs a read wrote "
    "beside it."
)


@dataclasses.dataclass(frozen=True)
class Snapshot:
    """A rehydrated read: the blocks that came off the wire, and the tree they parse to.

    Frozen, and deliberately without any way to change what it holds — the snapshot is ours
    and immutable, and the editable artefact is the **Markdown** a projection of
    :attr:`tree` produces. See this module's docstring for the boundary.

    :attr:`document_revision_id` is the value to hand to
    ``dry_run(..., document_revision_id=…)``; it is what arms the ``STALE_DOCUMENT``
    whole-document compare-and-swap, and it is **not a lock** — it reserves nothing and
    notices nothing. It is ``None`` when the snapshot was taken without one, in which case
    the guard cannot be armed from it.

    :attr:`api_domain` is the API domain the read was taken against — ``larksuite.com`` or
    ``feishu.cn``, the value :func:`~larkdocio.common.validate_download_url` returns first
    and :class:`~larkdocio.read.client.Client` takes last. It is the one fact a successor
    process **cannot derive** from the token, the revision or the blocks, which is why it
    travels. ``None`` means the artefact carries none — it was taken without one, or written
    by a release older than this field — and it is **never defaulted or guessed**, because
    the two domains are two different tenants and picking one would point a successor at the
    wrong company's document.
    """

    #: The document token the blocks were read from — also the id the tree is parsed under.
    document_token: str
    #: The document's ``revision_id`` as of the read, or ``None``.
    document_revision_id: _Optional[_Any]
    #: The rehydrated SDK ``Block`` objects, in the order they were persisted.
    blocks: _Tuple[_Any, ...] = dataclasses.field(repr=False)
    #: The parsed node tree — what ``Parser.parse_docx_tree`` returns.
    tree: _Node = dataclasses.field(repr=False)
    #: The API domain the read was taken against, or ``None`` when the artefact carries none.
    api_domain: _Optional[str] = None
    #: The artefact's format version.
    format_version: int = SNAPSHOT_FORMAT_VERSION
    #: The verified digest, hex, as the artefact carried it.
    checksum: str = ""


def snapshot(blocks, *, document_token, document_revision_id=None, api_domain=None,
             path=None) -> bytes:
    """Persist a docx read — ``blocks`` plus its token, revision and domain — as one artefact.

    ``blocks`` is what a read handed over: the SDK ``Block`` objects
    :meth:`~larkdocio.read.client.Client.get_docx_content` returns, or the block dicts they
    were deserialized from. Either way what is written is the **block payload** — not a
    re-serialization of the parsed tree, because the tree is derived and the payload is the
    evidence, and pinning the payload as it arrived is this project's defence against API
    drift.

    ``api_domain`` is the API domain the read was taken against — the ``domain`` half of
    :func:`~larkdocio.common.validate_download_url`'s 3-tuple, the argument
    :class:`~larkdocio.read.client.Client` takes. Pass it and a successor process can rebuild
    a client from **the artefact alone**; omit it and the artefact says so (:attr:`Snapshot
    .api_domain` is then ``None``, never a default). It is a routing fact and **not a
    credential** — no token, secret or credential is ever written here.

    Returns the artefact **bytes**, deterministically: the same read written twice is
    byte-identical. Pass ``path`` to write them as well — the write is atomic (a temporary
    file in the same directory, then :func:`os.replace`), so an interrupted write cannot
    replace a good snapshot with half of one.

    Nothing here reaches Lark. There is no encryption and no key material; the digest is for
    integrity only — see this module's docstring.
    """
    if not isinstance(document_token, str) or not document_token:
        raise _LarkConfigError(
            "snapshot() needs the document token the blocks were read from "
            f"(got {document_token!r}); it is the id the tree is parsed under."
        )
    if api_domain is not None and (not isinstance(api_domain, str) or not api_domain):
        raise _LarkConfigError(
            f"snapshot()'s api_domain is {api_domain!r}; it is the API domain the read was "
            "taken against (e.g. 'larksuite.com'), or None to write no domain at all."
        )
    artefact = _envelope_bytes({
        "document_token": document_token,
        "document_revision_id": document_revision_id,
        "api_domain": api_domain,
        "blocks": _block_payloads(blocks),
    })
    if path is not None:
        _write_atomically(_Path(path), artefact)
    return artefact


def load(source, *, config=None) -> Snapshot:
    """Rehydrate a snapshot from ``source`` — a path, or the artefact bytes themselves.

    Returns a :class:`Snapshot` carrying the same tree the read parsed, the same blocks, and
    the same token and revision. Offline: no call is made and no credentials are read.

    ``config`` is the reader :class:`~larkdocio.read.config.Config` to parse under; the
    default matches a default read. Byte-identity of the projection is guaranteed against a
    projection taken under the same config.

    Raises :class:`~larkdocio.errors.LarkSnapshotIntegrityError` — naming what failed and
    naming **re-download** as the fix — on a checksum mismatch, a truncated or unreadable
    file, an unrecognized ``format_version``, or malformed content. It never returns a
    partially-rehydrated tree.
    """
    origin, raw = _read_source(source)
    envelope = _envelope_of(raw, origin)
    _check_format_version(envelope, origin)
    integrity = _integrity_of(envelope, origin)
    payload = envelope.get("payload")
    _verify_checksum(payload, integrity, origin)
    document_token, revision, api_domain, block_dicts = _validated_payload(payload, origin)

    try:
        blocks = [_Block(d) for d in block_dicts]
        tree = _Parser(config or _Config()).parse_docx_tree(document_token, blocks)
    except LarkSnapshotIntegrityError:
        raise
    except Exception as exc:                       # noqa: BLE001 — any parse failure refuses
        _refuse("malformed",
                f"This snapshot's blocks could not be rehydrated ({exc!s}).", origin)

    return Snapshot(
        document_token=document_token,
        document_revision_id=revision,
        blocks=tuple(blocks),
        tree=tree,
        api_domain=api_domain,
        format_version=envelope["format_version"],
        checksum=integrity["value"],
    )


# --------------------------------------------------------------------------- #
# Writing                                                                      #
# --------------------------------------------------------------------------- #

def _block_payloads(blocks):
    """The block payloads as JSON-native data.

    A mapping is already the wire shape and is kept exactly. An SDK object is marshalled by
    **the SDK's own encoder** — the inverse of the deserializer that built it — rather than by
    a second, hand-rolled definition of the same mapping.
    """
    out = []
    for block in blocks or ():
        if isinstance(block, dict):
            out.append(block)
        else:
            out.append(json.loads(_SDK_JSON.marshal(block)))
    return out


def _canonical(obj) -> bytes:
    """The one canonical encoding the digest is taken over: sorted keys, no padding."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def _digest(payload) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _envelope_bytes(payload) -> bytes:
    """The whole artefact for ``payload`` — deterministic, and readable by a human.

    Indented on purpose: a hand-edited file is one of the named threats, which means people
    open these, and an artefact nobody can read is one nobody can diagnose.
    """
    envelope = {
        _ENVELOPE_KEY: {
            "format_version": SNAPSHOT_FORMAT_VERSION,
            "integrity": {
                "algorithm": _CHECKSUM_ALGORITHM,
                "value": _digest(payload),
                "covers": _COVERS,
                "does_not_cover": _DOES_NOT_COVER,
                "why": _WHY_A_CHECKSUM,
            },
            "payload": payload,
        }
    }
    text = json.dumps(envelope, sort_keys=True, ensure_ascii=False, indent=2)
    return (text + "\n").encode("utf-8")


def _write_atomically(path: _Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, staged = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".part")
    try:
        with os.fdopen(handle, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(staged, path)
    except BaseException:
        if os.path.exists(staged):
            os.unlink(staged)
        raise


# --------------------------------------------------------------------------- #
# Reading — every exit through _refuse, so the fix can never be dropped        #
# --------------------------------------------------------------------------- #

def _refuse(reason, detail, source):
    raise LarkSnapshotIntegrityError(f"{detail} {_THE_FIX}", reason=reason, source=source)


def _read_source(source):
    if isinstance(source, (bytes, bytearray)):
        return None, bytes(source)
    path = _Path(source)
    try:
        return str(path), path.read_bytes()
    except OSError as exc:
        _refuse("unreadable", f"This snapshot could not be read ({exc!s}).", str(path))


def _envelope_of(raw, origin):
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        _refuse("unreadable",
                "This snapshot is not readable as the JSON artefact snapshot() writes — it "
                f"looks truncated or corrupted ({exc!s}).", origin)
    envelope = document.get(_ENVELOPE_KEY) if isinstance(document, dict) else None
    if not isinstance(envelope, dict):
        _refuse("malformed",
                "This file is valid JSON but is not a larkdocio snapshot — its top level "
                f"carries no {_ENVELOPE_KEY!r} object.", origin)
    return envelope


def _check_format_version(envelope, origin):
    version = envelope.get("format_version")
    if version != SNAPSHOT_FORMAT_VERSION:
        _refuse("unknown_format_version",
                f"This snapshot declares format_version {version!r}, and this release reads "
                f"only {SNAPSHOT_FORMAT_VERSION!r}. No cross-version migration is offered, in "
                "either direction, so it is refused rather than upgraded in place.", origin)


def _integrity_of(envelope, origin):
    integrity = envelope.get("integrity")
    if not isinstance(integrity, dict) or not isinstance(integrity.get("value"), str):
        _refuse("malformed",
                "This snapshot carries no usable integrity block, so nothing about its "
                "contents can be confirmed.", origin)
    if integrity.get("algorithm") != _CHECKSUM_ALGORITHM:
        _refuse("malformed",
                f"This snapshot's checksum algorithm is {integrity.get('algorithm')!r}; this "
                f"release computes only {_CHECKSUM_ALGORITHM!r}.", origin)
    return integrity


def _verify_checksum(payload, integrity, origin):
    try:
        found = _digest(payload)
    except (TypeError, ValueError) as exc:
        _refuse("malformed",
                f"This snapshot's payload could not be canonicalized to check it ({exc!s}).",
                origin)
    if found != integrity["value"]:
        _refuse("checksum_mismatch",
                "This snapshot's contents do not match the checksum written with them "
                f"(expected {integrity['value']}, computed {found}), so it has been altered "
                "or damaged since it was written and nothing in it can be trusted.", origin)


def _validated_payload(payload, origin):
    if not isinstance(payload, dict):
        _refuse("malformed", "This snapshot carries no payload object.", origin)
    document_token = payload.get("document_token")
    blocks = payload.get("blocks")
    if not isinstance(document_token, str) or not document_token:
        _refuse("malformed",
                f"This snapshot's document_token is {document_token!r}, which is not a "
                "document token, so the tree cannot be parsed under it.", origin)
    if not isinstance(blocks, list) or any(not isinstance(b, dict) for b in blocks):
        _refuse("malformed",
                "This snapshot's blocks are not a list of block payloads.", origin)
    # ABSENT IS A VALUE HERE, AND IT IS NOT A DEFAULT. An artefact written before this field
    # existed carries no `api_domain` key at all, and one taken without a domain carries
    # null; both load, both report None, and neither is filled in with a guess — the two
    # domains are two different tenants.
    api_domain = payload.get("api_domain")
    if api_domain is not None and (not isinstance(api_domain, str) or not api_domain):
        _refuse("malformed",
                f"This snapshot's api_domain is {api_domain!r}, which is not an API domain "
                "(e.g. 'larksuite.com'); a successor cannot build a client from it.", origin)
    return document_token, payload.get("document_revision_id"), api_domain, blocks
