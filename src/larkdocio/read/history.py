"""larkdocio.read.history — reading a docx **at a past revision**, and the traps around it.

One route serves docx history:
``GET …/docx/v1/documents/{id}/blocks?document_revision_id=<n>`` — the **flat blocks
list**. It was measured falsifiably: on a document with two states, ``document_revision_id=2``
returned the 2-block earlier body while ``-1`` returned the 3-block head **in the same
instant**, and a 4-revision document walked rung by rung reproduced its edit history exactly.
That measurement is what :meth:`larkdocio.read.client.Client.get_docx_content` rides when it is
given a pin, and it is the reason it rides *that* route and no other.

**Three neighbouring behaviours make the naive exposure a footgun**, all measured, all
disclosed here once and quoted everywhere else (:data:`HISTORICAL_READ_TRAPS`): an
**out-of-range** revision silently returns head; **``raw_content``** accepts the pin and
ignores it; the document **meta** route accepts the pin and ignores it.

**And the thing a caller usually WANTS — "read the edition someone named V1.3" — is a measured
refusal** (:data:`EDITION_TO_CONTENT_UNAVAILABLE`): no route maps an edition token to content,
and none maps an edition to a revision. What IS available is to record the pair yourself at
creation time, because creating a version is revision-inert — which is exactly what
:meth:`larkdocio.drive.versions_write.DriveVersionsWriteClient.create_version` returns. The
shipped guide's *"diff a named edition against head"* recipe walks it.

Every claim in this module was measured by LD-404's editions probe; the captures are cited per
claim by their number.
"""
from dataclasses import dataclass

from larkdocio.common.citations import dev_repo
from larkdocio.errors import LarkConfigError

#: The capabilities-registry id under which this module's contract is declared, so a caller can
#: meet all three traps in ``capabilities()`` rather than only in a docstring.
HISTORICAL_READ_CONTRACT = "historical-read-rides-the-measured-route"

#: The spelling that means **head**. ``-1`` is Lark's own head sentinel on the wire and is
#: deliberately NOT exposed: one spelling for head, and it is the absence of a pin.
HEAD = None

#: Lark's answer to ``document_revision_id=0`` (capture ``206-``, in the dev repo) — mirrored, not invented.
REVISION_ZERO_REFUSAL_CODE = 1770001

#: Lark's answer to a negative or non-numeric ``document_revision_id`` (the edges table and
#: capture ``208-`` in the dev repo, whose ``field_violations`` name the ``document_revision_id`` field).
REVISION_INVALID_REFUSAL_CODE = 99992402

#: **TRAP (a).** Authored once, quoted verbatim into the docstring and the guide.
OVER_RANGE_SILENTLY_RETURNS_HEAD = dev_repo(
    "AN OUT-OF-RANGE REVISION SILENTLY RETURNS HEAD. Measured: a revision 50 past head on a "
    "4-revision document answered code 0 and head's body, with no error and no marker "
    "(tests/captures/editions-spike/captures/205-, in the source repository). So this operation CANNOT DETECT "
    "over-range, and it does not pretend to: a caller who pins a bad number is silently reading head. If that "
    "matters, bound the number yourself — read the head revision first "
    "(read_document_revision) and refuse a pin above it, which is a check larkdocio cannot "
    "make for you without spending a call you did not ask for."
)

#: **TRAP (b).**
RAW_CONTENT_IGNORES_THE_PIN = dev_repo(
    "raw_content IGNORES THE PIN, so a historical read is never routed through it. Measured: "
    "raw_content with a numeric document_revision_id returned code 0 and HEAD's content, "
    "byte-identical to the plain head call (tests/captures/editions-spike/captures/16- vs 17-, in the "
    "source repository), and the same route with an edition token did the same (116-, in the dev repo). larkdocio exposes no raw-content "
    "read at all, so the pin cannot reach one here; if you call that endpoint yourself, know "
    "that the parameter is accepted and discarded."
)

#: **TRAP (c).**
DOCUMENT_META_IGNORES_THE_PIN = dev_repo(
    "THE DOCUMENT META ROUTE IGNORES THE PIN. Measured: GET …/docx/v1/documents/{id} asked "
    "for revision 2 answered revision_id 3 — head (tests/captures/editions-spike/captures/19-, in the "
    "source repository). So a pinned read does not call it, and hands back no revision_id at all rather than head's "
    "number wearing the pinned revision's name; the revision you pinned is carried on the "
    "result as document_revision_id, and the title as of that revision is the page block's "
    "own text in the blocks the read returned."
)

#: The three traps in ONE place, so a caller meets all of them rather than discovering the
#: third after trusting the first two. Quoted verbatim into the docstring and the guide.
HISTORICAL_READ_TRAPS = "\n\n".join((
    OVER_RANGE_SILENTLY_RETURNS_HEAD,
    RAW_CONTENT_IGNORES_THE_PIN,
    DOCUMENT_META_IGNORES_THE_PIN,
))

#: **The measured refusal**, in the shape a negative claim has to take: what was
#: tried, what came back, and — because a claim's scope may not exceed its evidence's — what
#: was NOT tried. Never a bare "cannot".
EDITION_TO_CONTENT_UNAVAILABLE = dev_repo(
    "READING A DOCUMENT AT A NAMED EDITION IS NOT SERVED: no route maps an edition token to "
    "content, and none maps an edition to a revision. Measured 2026-08-11 against "
    "harness-created disposable documents on tenant_access_token "
    "(dev/editions-spike/findings.md § Leg 4, in the dev repo). "
    "TRIED — (1) GET one version: the version object carries no content, no url, no revision "
    "and no pointer of any kind (captures 12-, 122-); (2) blocks?document_revision_id=<version "
    "token> → 99992402, the parameter is an int; (3) blocks?edition_id= / ?version= / "
    "?version_id= / ?obj_edition_id= → code 0 but HEAD, silently ignored (112--115-); (4) "
    "raw_content with a numeric pin and with edition_id → head (16-; 116- in the dev repo); (5) the meta route "
    "with a numeric pin → head (19-); (6) the version token used as a docx document_id → "
    "99992402 on meta and 1770001 on blocks (20-, 21-); (7) the drive metas batch-query verb on the "
    "version token → failed_list [{code: 970005}], so it is not a file token (22-); (8) "
    "export_tasks with the version token as the file token → 1069914 export file token "
    "invalid (25-); (9) export_tasks with a speculative version field and with a speculative "
    "edition_id field → accepted and IGNORED, the result's file_size 4237 identical to the "
    "plain export (123--128-) — and byte-identity was not hashed, so it is unmeasured at the "
    "byte level; (10) the speculative sub-route …/versions/{version}/content → 404 (26-); "
    "(11) docx/v1/documents/{id}/revisions, /history and /versions, and "
    "drive/v1/files/{id}/revisions → 404 on all four (117--120-); (12) "
    "drive/v1/files/{id}/statistics → pv/uv/like counters only, no version or revision "
    "anything (121-). "
    "NOT TRIED, stated because a claim's scope may not exceed its evidence's — a "
    "user_access_token session on any of the above (everything measured was a "
    "tenant_access_token; the web client is a user session); POST/PUT/PATCH spellings of the "
    "unknown paths, deliberately, because a probe never risks a mutation on an unknown verb; "
    "the wiki/v2 node family at an edition; the legacy doc/v2 family; drive/v2 explorer "
    "routes; downloading the export artefacts and hashing them; retention — how far back "
    "document_revision_id reaches on an old document, and whether a deleted version's content "
    "survives; and whether an edition created while an edit is in flight snapshots before or "
    "after it. "
    "WHAT WORKS INSTEAD: record the pair yourself at creation time. create_version reads the "
    "head revision immediately before it creates the version and hands back (name, token, "
    "revision) — exact absent a concurrent edit, because creating a version is revision-inert "
    "(101-, 103-) — after which \"diff edition vs head\" is a pinned read against a head read. "
    "For an edition a HUMAN created in the web UI, resolution is a measured refusal: nothing "
    "above resolves it, and this library will not guess."
)


class HistoricalReadRefusedError(LarkConfigError):
    """A pin larkdocio refuses **locally**, before a call is spent — in Lark's own words.

    Only ever raised for something *measured*: ``0`` (Lark: ``1770001 invalid param``), a
    negative value and a non-integer (Lark: ``99992402 field validation failed``), and the
    ``-1`` head sentinel, which is refused by naming the spelling that works here rather than
    by being quietly accepted as a second way to say head.

    It also guards the one attribute a pinned read must never answer: ``revision_id`` on the
    result's metadata half, because the route that would supply it is measured to ignore the
    pin (:data:`DOCUMENT_META_IGNORES_THE_PIN`).
    """

    def __init__(self, message, *, code=None, value=None):
        super().__init__(message)
        self.code = code
        self.value = value


@dataclass(frozen=True)
class HistoricalDocumentMeta:
    """The metadata half of a **pinned** read — deliberately smaller than head's.

    A pinned read returns ``(HistoricalDocumentMeta, [Block])`` where an unpinned read returns
    ``(Document, [Block])``, and the difference is the point: the docx meta route **ignores**
    ``document_revision_id`` and answers head, so there is no honest way to fill a
    ``revision_id`` or a ``title`` field for the revision that was asked for.

    * :attr:`document_id` — the document that was read, which is the one field the parser
      needs (``parse_docx_content(meta.document_id, blocks)``).
    * :attr:`document_revision_id` — the revision **you pinned**, carried so a ledger can
      record what it read without holding on to its own argument.
    * ``revision_id`` — **raises** :class:`HistoricalReadRefusedError`. Handing back head's
      number here is the exact failure this type exists to prevent: it would arm a
      whole-document compare-and-swap (``dry_run(..., document_revision_id=…)``) with a
      number that describes a different document state than the blocks beside it.
    * ``title`` — absent for the same reason. The title **as of the pinned revision** is the
      page block's own text, inside the blocks the read returned.
    """

    document_id: str
    document_revision_id: int

    @property
    def revision_id(self):
        raise HistoricalReadRefusedError(
            "a pinned historical read has no revision_id to give you: the docx meta route "
            "IGNORES document_revision_id and reports HEAD's revision, so this object "
            "deliberately carries none rather than handing head's number back wearing the "
            "pinned revision's name. The revision you pinned is document_revision_id "
            f"({self.document_revision_id}); head's is one read away "
            "(read_document_revision), and it is the one to use for a compare-and-swap "
            f"write. {DOCUMENT_META_IGNORES_THE_PIN}",
            value=self.document_revision_id)


def check_revision_pin(value) -> int:
    """The pin gate: return the integer to put on the wire, or refuse locally.

    Refused, each in Lark's own words because each was measured: ``0`` (``1770001 invalid
    param``), any other non-positive number (``99992402 field validation failed``), and
    anything that is not a real :class:`int` — a digit string, a float and a ``bool`` included
    (``99992402``, capture ``208-``, in the dev repo). ``-1`` is Lark's head sentinel and is refused **by
    naming the spelling that works**: head is the absence of a pin.

    A ``bool`` is an ``int`` subclass in Python and is rejected on purpose: ``True`` would
    otherwise silently read revision 1.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise HistoricalReadRefusedError(
            f"document_revision_id must be a positive int; got {value!r}. Lark answers a "
            f"non-numeric document_revision_id with {REVISION_INVALID_REFUSAL_CODE} field "
            "validation failed, attributed to that field by name, so larkdocio refuses it "
            "here rather than spending a call to be told the same thing. Head is not a "
            "number: omit the parameter (or pass None).",
            code=REVISION_INVALID_REFUSAL_CODE, value=value)
    if value == -1:
        raise HistoricalReadRefusedError(
            "-1 IS Lark's head sentinel on the wire, and larkdocio deliberately does not "
            "accept it as a second spelling of head: pass None (or omit "
            "document_revision_id entirely) to read head. A positive number reads that "
            "revision.",
            code=REVISION_INVALID_REFUSAL_CODE, value=value)
    if value == 0:
        raise HistoricalReadRefusedError(
            f"document_revision_id=0 is refused by Lark itself: {REVISION_ZERO_REFUSAL_CODE} "
            "invalid param (HTTP 400). Revisions start at 1; head is None.",
            code=REVISION_ZERO_REFUSAL_CODE, value=value)
    if value < 0:
        raise HistoricalReadRefusedError(
            f"document_revision_id={value} is refused by Lark itself: "
            f"{REVISION_INVALID_REFUSAL_CODE} field validation failed (HTTP 400). Revisions "
            "start at 1; head is None.",
            code=REVISION_INVALID_REFUSAL_CODE, value=value)
    return value


def pinned_meta(doc_token: str, document_revision_id: int) -> HistoricalDocumentMeta:
    """The metadata half of a pinned read — built from what was asked, never from head."""
    return HistoricalDocumentMeta(document_id=doc_token,
                                  document_revision_id=document_revision_id)


__all__ = [
    "HEAD",
    "HISTORICAL_READ_CONTRACT",
    "HISTORICAL_READ_TRAPS",
    "OVER_RANGE_SILENTLY_RETURNS_HEAD",
    "RAW_CONTENT_IGNORES_THE_PIN",
    "DOCUMENT_META_IGNORES_THE_PIN",
    "EDITION_TO_CONTENT_UNAVAILABLE",
    "HistoricalDocumentMeta",
    "HistoricalReadRefusedError",
    "check_revision_pin",
    "pinned_meta",
]
