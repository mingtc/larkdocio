"""larkdocio.permissions — the ONE source of scope truth, stated PER OPERATION and derived.

**The question this answers.** *"Which Lark permissions does this exact call need, and what
happens if I do not hold them?"* Before this module the answer existed only per **surface**
(``capabilities()`` carried a surface's ``scopes`` / ``optional_scopes``) and per
**credential pair** (a write gate named its ``credentials_env``) — so the join, *this
operation needs these scopes on that credential pair*, was stated nowhere and asserted in
prose in several places that could drift apart. That gap is not academic: a missing
**field-level** contacts grant once presented for five days as a data-range problem, because
the call it broke returned a success with null name fields.

**How a requirement is established — derivation first, evidence always.**

1. **Endpoints are DERIVED from the operation's own code.** :func:`endpoints_of` walks the
   callable that implements an operation and collects every Lark path **the derivation can
   resolve** — the ``uri`` of each pinned-SDK request class it builds, plus every raw
   ``/open-apis/…``
   literal or module constant it names, following calls into this package (through a
   parameter whose annotation names the client class it is handed, and through a
   function-local import of this package or the pinned SDK). So an operation that
   starts calling a different endpoint family moves in this registry with nobody
   remembering to move it.
   **The resolution is STATIC and therefore incomplete, and the qualifier above is where it
   says so (LD-609).** A seam it cannot resolve — a dynamically named import, a client-shaped
   parameter bound to no class — is not dropped: :func:`unresolved_call_sites_of` names it,
   every operation's block carries it as ``unresolved_call_sites``, and :func:`coverage_gaps`
   reports the operation as ``undetermined``. So *"is this operation API-using?"* is a derived
   property with three answers, not two: it reaches these paths, it reaches nothing (an empty
   endpoint set **and** nothing unresolved), or the derivation could not be completed and
   says which seam stopped it. **What this module will not do is publish the second answer
   when the truth is the third** — that was the LD-609 defect, and the guard that should have
   caught it could not, because :func:`operation_inventory` defined *API-using* as
   :func:`endpoints_of`'s own answer.
2. **Scopes come from ONE table**, :data:`ENDPOINT_SCOPES`, joined onto those endpoints by
   longest matching path prefix and by credential **mode** (the read/write app split, whose
   env tuples are code truth in :mod:`larkdocio.common.auth`). A Lark scope string exists
   nowhere in this codebase's own logic, so that table is the one irreducibly hand-listed
   thing here — and **every row carries an evidence pointer and a verification label.**
3. **A requirement we have never seen demanded or granted is RECORDED as unknown, never
   asserted.** Two shapes, and the difference is deliberate. Where a scope string is known
   but its necessity is not, the row carries it labelled ``documented-unverified``. Where **no
   scope string has ever been observed at all**, the row is **empty and carries the reason** —
   because the alternative would be to write down a plausible-looking scope name nobody has
   seen, and a guessed string labelled "unverified" still reads as an answer. An empty
   requirement is therefore never a claim that a call needs nothing: every consumer of this
   registry gets those reasons back as ``unknown_requirements``, and both documents give them
   their own table.

**The binding rule, stated verbatim here because this is where it has to hold:** This
library never widens, requests or escalates a scope. It only describes what a call requires
and reports, verbatim, what Lark said when a call was denied — including the console link
Lark hands back. Granting a scope is an action a workspace administrator takes in the Lark
console.

**Projected, not parallel.** ``capabilities()`` carries this registry's answer on every
operation it projects, and each surface's own ``scopes`` / ``optional_scopes`` are the
**union of its operations' rows** rather than a second assertion of the same fact. The
documents are projected from here too, so there is one place to change: the per-operation
matrix ``PERMISSIONS.md`` — in the source repository, not in the wheel — and the
consumer-facing section of the shipped guide (``larkdocio.guide()``, which is what a
wheel-only reader has) are both **generated** from these rows and byte-checked against them.
"""
import ast
import functools
import importlib
import inspect
import re
import textwrap
import typing
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, NamedTuple, Optional, Tuple


#: The rule, stated where the registry lives rather than only in a document.
NEVER_WIDENS = (
    "This library never widens, requests or escalates a scope. It only describes what a "
    "call requires and reports, verbatim, what Lark said when a call was denied — including "
    "the console link Lark hands back. Granting a scope is an action a workspace "
    "administrator takes in the Lark console."
)

#: How firmly a scope requirement is established. Ordered strongest-first.
#:
#: * ``denial-verified`` — a captured Lark denial body names this exact scope string;
#: * ``grant-verified`` — the app holds it and the calls succeed, so the requirement is
#:   behaviourally confirmed even though Lark never echoed the string back;
#: * ``documented-unverified`` — asserted from documentation only; never observed demanded
#:   and never behaviourally isolated. Read it as an honest unknown, not a fact;
#: * ``no-scope-required`` — verified to need no scope at all (app credentials only).
VERIFICATION_LABELS = (
    "denial-verified", "grant-verified", "documented-unverified", "no-scope-required",
)


# --------------------------------------------------------------------------- #
# The typed layer.                                                             #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Scope:
    """One Lark scope string a call requires, with the evidence that established it.

    * ``scope`` — the string exactly as Lark spells it;
    * ``verification`` — one of :data:`VERIFICATION_LABELS`;
    * ``evidence`` — where the requirement was established (a capture, a live gate, a
      document). Mandatory: a requirement with no evidence is a memory, not a fact;
    * ``degrades`` — ``True`` when a caller-visible graceful degrade exists without it, which
      is what makes it *optional* at the surface level while still being *required* for the
      one operation that calls the endpoint;
    * ``field_level`` — ``True`` for a grant whose absence lets the call SUCCEED and empties
      the fields it governs. The most dangerous shape there is, so it is a field rather than
      a footnote;
    * ``established`` — ``False`` for a **candidate**: a scope string this project carries for
      an endpoint but has never confirmed is actually required. A candidate is REPORTED (so a
      caller has something to try, and so a typo of it still reddens the guards) but is
      deliberately **excluded from any surface's asserted requirement**, because "we have seen
      this string written down" is not "you must hold this". Without this distinction the only
      two options are to assert something unproven or to delete a useful hint;
    * ``note`` — what its absence looks like, in one sentence.
    """

    scope: str
    verification: str
    evidence: str
    degrades: bool = False
    field_level: bool = False
    established: bool = True
    note: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "scope": self.scope,
            "verification": self.verification,
            "evidence": self.evidence,
            "degrades": self.degrades,
            "field_level": self.field_level,
            "established": self.established,
        }
        if self.note is not None:
            d["note"] = self.note
        return d


#: The registry's OWN statement of why a scope can be *optional* for a surface and still
#: *required* by one of its calls — lifted verbatim from :class:`Scope`'s ``degrades`` bullet
#: above and quoted into the consumer tables, never retyped. A hand-typed fourth statement of
#: this rule is what produced a label claiming the call "does not run at all", which is false
#: for every ``degrades=True`` row and was contradicted by the field-level paragraph of the
#: same generated region. A guard in the source repository (``tests/test_permissions_docs.py``) pins it
#: substring-of-docstring, and reddens on any hard-failure claim in either table's label.
_DEGRADES_DISCRIMINATOR = (
    "a caller-visible graceful degrade exists without it, which is what makes it *optional* "
    "at the surface level while still being *required* for the one operation that calls the "
    "endpoint"
)

#: The ONE place a missing scope's cost is written — one entry per scope, derived from each
#: scope's own note. Both consumer tables route here by this exact heading instead of
#: restating the cost in a label, because a label cannot state it: it is per row.
_LOSS_LIST_HEADING = "What you lose without each one"


@dataclass(frozen=True)
class Denial:
    """A scope denial Lark actually returned to this app, captured verbatim.

    The strongest evidence there is — Lark names the exact scope string and hands back a
    console link — so the captures are catalogued rather than paraphrased. **One field is
    not verbatim, deliberately:** ``help_url``'s app id segment is the placeholder
    ``<your-app-id>``, because the console link Lark returns names the *capturing* app, and
    a reader needs the page for their own. Everything else in the link is as Lark sent it. Several of these
    scopes are required by **no** shipped operation; they are kept because a denial that
    reaches a caller must still be legible, and because they are the fixtures a uniform
    permission refusal is proved against.
    """

    scope: str
    code: int
    msg: str
    capture: str
    help_url: Optional[str] = None
    required_by_a_shipped_operation: bool = False

    def to_dict(self) -> dict:
        d = {
            "scope": self.scope, "code": self.code, "msg": self.msg,
            "capture": self.capture,
            "required_by_a_shipped_operation": self.required_by_a_shipped_operation,
        }
        if self.help_url is not None:
            d["help_url"] = self.help_url
        return d


@dataclass(frozen=True)
class Permissions:
    """One operation's complete permission answer — the block ``capabilities()`` carries.

    **``scopes`` is the per-OPERATION answer: everything this operation's own calls require.**
    ``optional_scopes`` is the SUBSET of those whose absence *degrades* the surrounding
    capability instead of breaking it — so the two deliberately overlap, and the distinction
    is the one this registry exists to draw. The name-resolution call is the case: the two
    contacts scopes are **required** to make that call at all, while a document read that
    cannot resolve a mention still succeeds with the raw id. Reading them as *optional for the
    operation* is precisely the conflation that once hid a field-level gap for five days.

    ``api_using`` is derived from ``endpoints``: an operation for which **no** Lark path was
    derived needs no permission *that this registry could see*, and saying so explicitly is
    what keeps the coverage guard honest (it can then tell *"needs nothing"* from *"nobody
    wrote a row"*).

    **``api_using=False`` is only the claim it looks like when ``unresolved_call_sites`` is
    empty (LD-609).** That field names every seam inside the operation's reach where the
    static derivation stopped — a function-local import it may not follow, a client-shaped
    parameter bound to no class. It is the same discipline ``unknown_requirements`` applies
    one level down: where that one says *"this endpoint's requirement was never observed"*,
    this one says *"there may be an endpoint here I could not see"*. Read the two fields
    together; an empty ``endpoints`` **beside** a non-empty ``unresolved_call_sites`` is a
    recorded unknown and never a claim that the call needs nothing.
    """

    endpoints: Tuple[str, ...]
    credential_app: str
    credentials_env: Tuple[str, ...]
    scopes: Tuple[Scope, ...] = ()
    optional_scopes: Tuple[Scope, ...] = ()
    basis: str = "derived"
    evidence: Optional[str] = None
    unknown_requirements: Tuple[str, ...] = ()
    unresolved_call_sites: Tuple[str, ...] = ()

    @property
    def api_using(self) -> bool:
        return bool(self.endpoints)

    def to_dict(self) -> dict:
        d = {
            "endpoints": list(self.endpoints),
            "credential_app": self.credential_app,
            "credentials_env": list(self.credentials_env),
            "scopes": [s.to_dict() for s in self.scopes],
            "optional_scopes": [s.to_dict() for s in self.optional_scopes],
            "api_using": self.api_using,
            "basis": self.basis,
        }
        if self.unknown_requirements:
            d["unknown_requirements"] = list(self.unknown_requirements)
        # Emitted only when non-empty, the same rule the unknown requirements follow: a
        # complete derivation says nothing, so the key's PRESENCE is itself the information.
        if self.unresolved_call_sites:
            d["unresolved_call_sites"] = list(self.unresolved_call_sites)
        if self.evidence is not None:
            d["evidence"] = self.evidence
        return d


@dataclass(frozen=True)
class PermissionRow:
    """One row of the registry **view** — an operation, its surface, and its requirement.

    A view over the same objects ``capabilities()`` already carries, not a second copy: the
    scopes are re-joined from :data:`ENDPOINT_SCOPES` at read time, so a row cannot disagree
    with the table it came from.
    """

    surface: str
    operation: str
    #: ``"operation"`` (a kind the surface's engine dispatches) / ``"leg"`` (an API-using
    #: call site that is not one of those) / ``"lifecycle"`` (create or trash the file
    #: itself). A caller reads it to know whether a row is something they invoke by name.
    kind: str
    mode: str
    endpoints: Tuple[str, ...]
    credential_app: str
    credentials_env: Tuple[str, ...]
    scopes: Tuple[Scope, ...]
    optional_scopes: Tuple[Scope, ...]
    api_using: bool
    basis: str
    evidence: Optional[str] = None
    #: The seams the derivation could not resolve (LD-609). Non-empty means this row's
    #: ``endpoints`` — and therefore its ``scopes`` — may be SHORT, and the row says so
    #: instead of publishing a confident empty.
    unresolved_call_sites: Tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# THE ONE HAND-LISTED TABLE — endpoint prefix x credential mode -> scopes.      #
#                                                                              #
# Ordered longest-prefix-first is NOT required (the lookup sorts), but the      #
# rows are grouped by family for reading. Every scope carries its evidence.     #
# --------------------------------------------------------------------------- #

_SPIKE = "tests/captures/name-lookup-spike (in the source repository)"
#: The name-lookup spike's own record of the captures the source repository does NOT carry
#: (``P0``, ``P1``, ``P8``, ``P12``, ``R2``, ``R3``, ``R7``, the write-pair ``users/batch`` call):
#: their bodies were retired, so each citation below states the measured fact itself and names
#: this record as the provenance note it is (LD-703, round 5 V1).
_SPIKE_RECORD = "dev/name-lookup-spike/reprobe/reprobe-verdict.md (in the dev repo)"

#: ``(path_prefix, mode, scopes, reason_when_empty)``. ``mode`` is ``"read"`` / ``"write"``
#: (the credential pair the call is made on) or ``"*"`` for a row that holds on both.
ENDPOINT_SCOPES: Tuple[Tuple[str, str, Tuple[Scope, ...], Optional[str]], ...] = (
    # ---- docx documents + blocks ----
    (
        "/open-apis/docx/v1/documents", "read",
        (
            Scope(
                scope="docx:document:readonly",
                verification="grant-verified",
                evidence=(
                    "the read credential block in .env.example and the credential doctrine in "
                    "PROJECT.md (in the dev repo); behaviourally confirmed by the live reader "
                    "canary (pytest -m live), which downloads a real document twice"
                ),
                note="without it no document can be read at all",
            ),
        ),
        None,
    ),
    (
        "/open-apis/docx/v1/documents", "write",
        (
            Scope(
                scope="docx:document",
                verification="grant-verified",
                evidence=(
                    "the write credential block in .env.example and the writer brief's "
                    "credential doctrine; behaviourally confirmed by the live write ring "
                    "(pytest -m live_write) against self-provisioned disposables"
                ),
                note="without it no block can be created, patched or deleted",
            ),
        ),
        None,
    ),
    # ---- comments (they live under the drive file family) ----
    #
    # NOTE the asymmetry with the comment WRITES, which is about derivation rather than about
    # comments: the read side goes through the pinned SDK, so its request classes carry their
    # own full ``uri`` and the join lands on this exact path. The write side is raw HTTP, and a
    # raw path built with the token in the middle of an f-string leaves only its literal prefix
    # in the source — so comment writes derive ``/open-apis/drive/v1/files`` and are answered by
    # that row below, exactly as every other raw-HTTP write call site in this table is answered
    # at its own truncated prefix. A row keyed here for "write" would never be matched.
    (
        "/open-apis/drive/v1/files/:file_token/comments", "read",
        (
            Scope(
                scope="docx:document:readonly",
                verification="grant-verified",
                evidence=(
                    "the comments probe captures in tests/captures/comments-probe-captures (in the source "
                    "repository): the whole comment family answered with code 0 on the reader's "
                    "own scope, with no additional grant; re-confirmed by the live "
                    "read-only comments ring. Widening the read to a THIRD file type "
                    "widened no scope, and that is an observation rather than an "
                    "assumption: the same call site with file_type=bitable answered code 0 "
                    "on the same unchanged grants "
                    "(tests/captures/base-study/captures/p1-q7-01-comments-populated.json, in the source "
                    "repository)"
                ),
                note=(
                    "the comment family needs no extra grant beyond the reader's, on any of "
                    "its three file types; comment authors come back as raw ids either way"
                ),
            ),
        ),
        None,
    ),
    # ---- contacts: the name-resolution pair, and the field-level lesson ----
    (
        "/open-apis/contact/v3/users/batch", "*",
        (
            Scope(
                scope="contact:contact.base:readonly",
                verification="grant-verified",
                evidence=(
                    "capture R0 under " + _SPIKE + " (READ pair); the READ-pair capture P0 "
                    "and the write-pair call are recorded only in " + _SPIKE_RECORD + ": "
                    "the directory call answered code 0 with populated name fields on BOTH "
                    "pairs, which is what establishes it on each"
                ),
                degrades=True,
                note=(
                    "opens the directory call — without it no display name resolves at all. "
                    "What that costs depends on the caller: a document read still completes "
                    "with every mention left as a raw open id, and a spreadsheet plan still "
                    "builds, disclosing its mention check as unavailable rather than skipping "
                    "it silently"
                ),
            ),
            Scope(
                scope="contact:user.base:readonly",
                verification="grant-verified",
                evidence=(
                    "the same READ-pair capture R0 under " + _SPIKE + "; capture P0 and "
                    "the write-pair call are recorded only in " + _SPIKE_RECORD + " — the "
                    "name fields came back populated on both, which is what proves the "
                    "field-level grant is held on each"
                ),
                degrades=True,
                field_level=True,
                note=(
                    "the FIELD-LEVEL grant — without it the lookup SUCCEEDS and every name "
                    "field comes back null, which reads exactly like 'no such user'. A "
                    "document read degrades to raw open ids; a spreadsheet plan discloses its "
                    "mention check as unavailable"
                ),
            ),
        ),
        None,
    ),
    # ---- contacts: email-or-mobile -> open_id, the SECOND forward direction (LD-348) ----
    #
    # It needs its OWN row despite sitting under /contact/v3/users: without one, longest-prefix
    # would hand it the /users/batch pair above, and this table would then assert that the pair
    # authorises an endpoint no capture in this repository shows it authorising. Plausible is
    # not proven, and the whole point of this table is the difference.
    #
    # The row is deliberately EMPTY rather than a CANDIDATE. The board/v1/whiteboards row below
    # is the candidate precedent and it was the shape this row was expected to take — but a
    # candidate needs a STRING, and no string could be sourced. Lark's own reference page for
    # this endpoint was fetched at implementation time (2026-08-08,
    # open.larksuite.com/document/…/contact-v3/user/batch_get_id) and serves its permission
    # table from client-side script: the fetched bytes contain no scope string at all. No
    # capture in this repository contains one either, because none was ever demanded. Naming
    # one anyway would be a claim from memory, which is precisely what this field exists to
    # prevent — so the requirement is recorded UNKNOWN, and the /drive/v1/files row below is
    # the precedent for that shape.
    (
        "/open-apis/contact/v3/users/batch_get_id", "*",
        (),
        (
            "no scope string has ever been observed demanded for this endpoint, and none "
            "could be sourced to name as a candidate. NINE calls across TWO credential pairs "
            "answered code 0 on it — three on 2026-07-30 and six in the 2026-08-08 user "
            "probe, whose record and captures are at tests/captures/name-lookup-spike/ (in the source "
            "repository). "
            "code 0 proves the app holds ENOUGH; it cannot prove what is REQUIRED, so nothing "
            "here distinguishes 'required and held' from 'not required'. The contacts pair "
            "carried above for /contact/v3/users/batch is the plausible guess and is "
            "deliberately NOT asserted for this endpoint. If the call is ever denied, read "
            "the denial body — it names what Lark actually wants, and that is what gets "
            "recorded here"
        ),
    ),
    # ---- the directory search: name -> open_id, the FORWARD direction ----
    #
    # This row is the one place a denial-verified scope was upgraded to GRANT-verified by the
    # same endpoint. It sat in OBSERVED_DENIALS for five days as pure denial evidence; the
    # 2026-07-30 post-release run then answered code 0 on the same call, and the 2026-08-02
    # slice-2 arm re-confirmed it across ~33 read-only probes. Both halves are cited, because
    # the pair is more informative than either: it is the only scope in this table whose
    # necessity AND whose sufficiency have both been observed on the wire.
    (
        "/open-apis/directory/v1/employees/search", "read",
        (
            Scope(
                scope="directory:employee:search",
                verification="grant-verified",
                evidence=(
                    "the denial/grant PAIR on this exact endpoint, both under " + _SPIKE +
                    ": reprobe/captures/R1-search-owner-exact-READ.json is a "
                    "verbatim 99991672 naming this scope in permission_violations[].subject, and "
                    "reprobe/captures/R8-search-owner-exact-READ-POSTRELEASE-GO.json is a code 0 "
                    "on the identical call once it was granted. Re-confirmed live by the "
                    "name-lookup read-only arm (its slice-2 search capture, under slice2/captures/ "
                    "in the same directory) and by the credential-gated "
                    "tests/test_live_contacts_lookup.py"
                ),
                note=(
                    "without it a name cannot be turned into an open_id at all — the call is "
                    "denied outright and the lookup raises rather than reporting the person as "
                    "absent. There is no degrade: this library will not enumerate the directory "
                    "to approximate a name search"
                ),
            ),
        ),
        None,
    ),
    # ---- drive: media download, export tasks, and the trash ----
    (
        "/open-apis/drive/v1/medias", "read",
        (),
        (
            "no scope string has ever been observed demanded for the media download; it "
            "succeeds on the read app's granted set (the live reader canary asserts no "
            "image link is dropped), so the requirement is documented-but-unverified and "
            "deliberately not guessed"
        ),
    ),
    # ---- drive: the MEDIA out-of-band leg (upload, then download-verify) ---- #
    #
    # TWO rows on the WRITE pair, and they are DRIVE-family rows — not bitable ones, and not
    # docx ones. That is the fact worth stating loudly: a consumer who has been granted
    # `bitable:app` and expects the Base surface to work end to end, or `docx:document` and
    # expects to put a picture in a document, will find that attaching bytes reaches a
    # different service entirely, and will find it here rather than at the call. It is the
    # same family the document image *download* already documents (the row above), seen from
    # the write side. TWO call sites share these rows — the Base attachment leg and the docx
    # image-authoring op — and neither elicited a scope answer.
    (
        "/open-apis/drive/v1/medias/upload_all", "write",
        (),
        (
            "no scope string has ever been observed demanded for a media upload: it "
            "answered code:0 on the write app's already-granted set for BOTH Base parent "
            "types (tests/captures/base-study/captures/p0-4-01-attachment-population.json, in the source "
            "repository) and, on the same already-granted set, for the docx image parent type "
            "bound to a document's own image block (dev/media-spike/captures/105-, 122-, in "
            "the dev repo). No denial has ever been captured on it. So the requirement is "
            "grant-observed-but-unnamed and deliberately not guessed — writing down a "
            "plausible drive scope string nobody has seen would read as an answer. What IS "
            "established, and is the reason this row exists separately from the bitable and "
            "docx families: this call is on the DRIVE family, so holding the Base or the "
            "document scopes alone says nothing about whether it will be permitted"
        ),
    ),
    (
        "/open-apis/drive/v1/medias/:file_token/download", "write",
        (),
        (
            "no scope string has ever been observed demanded for the media download "
            "either — the same honest gap as the upload row above, seen from the other end of "
            "the round trip. The download answered HTTP 200 with a body whose "
            "sha256 matched the upload's, on the already-granted set, for the Base "
            "attachment leg and for a docx-bound image token — both verified by hash with no "
            "bytes inspected, both captures since retired from the dev repo (2026-09-18) — and "
            "named no scope in "
            "doing so. A THIRD call site now rides it, and it is the one that widens the "
            "warning rather than the requirement: an IN-CELL SHEET image whose token Lark "
            "MINTED ITSELF on the "
            "values_image call — nothing was uploaded — and which downloaded byte-identical "
            "on the same already-granted set. So a consumer holding only the spreadsheet "
            "grants still reaches the DRIVE family the moment they verify the bytes. The "
            "read "
            "app reaches this same endpoint family for document images, where the requirement "
            "is equally unobserved — see the medias row above"
        ),
    ),
    (
        "/open-apis/drive/v1/export_tasks", "read",
        (
            Scope(
                scope="drive:export",
                verification="grant-verified",
                evidence=(
                    "the export-fidelity capture in tests/captures/sheets-write-spike/captures (in the "
                    "source repository) plus the live style gate; SHEETS.md's export row records the "
                    "same result on the read pair"
                ),
                degrades=True,
                note=(
                    "the whole-cell style and number-format read needs it — without it that "
                    "read degrades to values only and nothing else changes"
                ),
            ),
        ),
        None,
    ),
    (
        # SIX call classes reach this row, and they share one evidence gap. (a) Moving a file
        # to the trash. (b) The COMMENT WRITES — creating a whole-document comment, listing a
        # thread's replies, deleting one — which are raw-HTTP drive/v1 calls and so derive this
        # prefix (see the note by the comments read row above). (c) The FOLDER ENUMERATION
        # READS (LD-324): listing a folder's children, paged and recursed, on the READ pair.
        # (d) THE FILE-OBJECT DELETE (LD-434, made legible by LD-442) — trashing a `type=file`
        # object this library itself uploaded, `DriveFilesWriteClient.delete`. It is class (a)
        # by a different token type rather than a family of its own, which is exactly why it
        # belongs on this row and not on one of its own: the upload and download rows next to
        # it took their own rows because filing an UPLOAD under a trash-move's non-observation
        # would attribute one family's silence to another, and a trash-move filed under a
        # trash-move's does not. It was reached by NO declared call site until LD-442 — see
        # `undeclared_endpoints` for how a shipped call nobody declared stayed invisible.
        # (e) THE WHOLE-BASE DELETE (LD-466) — `BaseSchemaClient.delete_base`, trashing a Base
        # through the same Drive path with `type=bitable`. Class (a) again, on a fifth token
        # type, for the same reason (d) is: a trash-move filed under a trash-move's own
        # non-observation attributes nothing to anybody.
        # (f) THE BY-NAME LOOKUP (LD-464) — `DriveClient.find_children_by_name`, the check a
        # caller runs before an upload. It is class (c) with a filter on top: the SAME listing
        # call, paged the same way, with the matching happening in memory afterwards. NO new
        # endpoint, and deliberately no row of its own — a row here would file a second
        # non-observation for a call that is already covered by the enumeration's.
        "/open-apis/drive/v1/files", "*",
        (),
        (
            "no scope string has ever been observed demanded for any drive/v1 file call this "
            "library makes. Moving a file to the trash succeeds on the write app's granted set "
            "(every live write ring trashes the disposable it created). So do the COMMENT "
            "WRITES: creating a whole-document comment, listing a thread's replies and "
            "deleting one all answered code 0 on that same already-granted set "
            "(tests/captures/comments-probe-round2-captures/14-demo.json, in the source "
            "repository, plus the live comment-op ring on self-provisioned disposables), and "
            "the one refusal that family produces — 1069303 forbidden, captured in "
            "16-delete-arm.json — is recorded there as an OWNERSHIP refusal, about who the "
            "caller is rather than about a missing scope, so it establishes nothing about the "
            "requirement. The write app does hold docx:document, but these are drive/v1 "
            "endpoints and nothing here distinguishes 'authorized by docx:document' from "
            "'authorized by a drive scope the app also holds' — so the requirement is recorded "
            "unknown and deliberately not guessed. The FOLDER ENUMERATION reads widen the same "
            "non-observation without closing it: the drive spike made 17 live calls across two "
            "rounds on the READ pair — 5 in round 1 and 12 in round 2, every one answered code "
            "0, with ZERO denials — listing a real 35-node tree to 4 levels. Zero denials on "
            "one tenant distinguishes nothing, and under the credential aliasing recorded in "
            "PROJECT.md (in the dev repo; on the tenant these measurements were made on, the "
            "READ and WRITE pairs named one app) a same-tenant success cannot attribute a "
            "scope at all. THE FILE-OBJECT DELETE is the same non-observation on a fourth "
            "token type: trashing a type=file object this library had just uploaded answered "
            "code 0 on the WRITE pair "
            "(dev/media-spike/captures/207-ac2-teardown-delete-the-uploaded-file.json, in the "
            "dev repo), named no scope in doing so, and no denial has ever been captured on "
            "it. It also carries the one measured EDGE this row's readers need: the delete is "
            "TRASH, NOT PURGE — after a successful delete the metadata route still resolves "
            "the token — so nothing here establishes the object's absence, and whether any "
            "route does is unmeasured rather than refuted. THE WHOLE-BASE DELETE is the same "
            "non-observation on a fifth token type, measured 2026-08-15 on two Bases the probe "
            "created itself: the identical route with the Base's own object type "
            "(type=bitable) answered code 0 on the WRITE pair "
            "(tests/captures/ld466-delete-base/captures/ld466-04-drive-delete-with-the-bases-own-type.json, "
            "in the source repository), named no scope in doing so, and drew no denial. It "
            "also re-measures this row's trash-not-purge edge on that type — after the landed "
            "delete, metas/batch_query still resolved the token with its title, owner and "
            "timestamps intact (ld466-07-*.json) — and it records the one code that is NOT a "
            "scope answer: the same request sent with the generic type=file answered 1061003 "
            "not found for a Base that plainly existed (ld466-01-*.json), which is a "
            "wrong-type answer and establishes nothing about a requirement. THE BY-NAME LOOKUP "
            "adds a sixth caller and no new observation: it is the folder enumeration above "
            "with an in-memory name filter after it, measured 2026-08-15 answering code:0 for "
            "a folder the probe created and swept "
            "(tests/captures/ld464-upload-identity/captures/ld464-20-list-the-folder.json, in "
            "the source repository), naming no scope and drawing no denial. What that capture "
            "DOES settle is a fact about the answer rather than about a grant: the listing "
            "reports eight keys per child and NO SIZE, and the metadata route reports none "
            "either (that recording is not published), so a by-name check can compare names "
            "and can never compare bytes"
        ),
    ),
    (
        # THE ENUMERATION'S SECOND LEG (LD-324) — a folder's OWN title. A documented QUERY POST
        # that mutates nothing, so it is filed on the READ pair: a row under 'write' would
        # quietly assert that reading a title needs write credentials. It does NOT resolve
        # under the /drive/v1/files prefix, which is why it needs a row of its own.
        "/open-apis/drive/v1/metas/batch_query", "read",
        (),
        (
            "no scope string has ever been observed demanded for this endpoint. It answered "
            "code 0 on the READ credential pair in the drive spike "
            "(tests/captures/drive-spike/captures/06-metas-batch-query.json, in the source "
            "repository), which establishes REACH and nothing about a requirement: the best a "
            "requirement could be labelled from documentation alone is documented-unverified, "
            "and no scope string is carried here because none has ever been seen — a "
            "plausible-looking drive scope name nobody has observed would read as an answer. "
            "Under the credential aliasing recorded in PROJECT.md (in the dev repo; on the "
            "tenant these measurements were made on, the READ and WRITE pairs named one app) a "
            "same-tenant success cannot attribute a scope at all, so the requirement is "
            "recorded unknown and deliberately not guessed"
        ),
    ),
    (
        # THE ENUMERATION'S THIRD LEG (LD-324) — the caller's OWN root folder, and a LEGACY
        # family: the pinned lark-oapi SDK models no request for explorer/v2 at all, so it is
        # reachable only through the shared raw-HTTP core.
        "/open-apis/drive/explorer/v2/root_folder/meta", "read",
        (),
        (
            "no scope string has ever been observed demanded for this endpoint. It is a legacy "
            "explorer/v2 family the pinned SDK does not model, reached raw, and it answered "
            "code 0 on the READ credential pair in the drive spike "
            "(tests/captures/drive-spike/captures/01-root-folder-meta.json, in the source "
            "repository). That establishes reach only: a requirement asserted from "
            "documentation alone would be documented-unverified at best, and no scope string "
            "is carried here because none has ever been seen. Under the credential aliasing "
            "recorded in PROJECT.md (in the dev repo; on the tenant these measurements were "
            "made on, the READ and WRITE pairs named one app) a same-tenant success cannot "
            "attribute a scope at all, so the requirement is recorded unknown and deliberately "
            "not guessed"
        ),
    ),
    (
        # THE FOLDER-UPLOAD SLICE (LD-434) — putting a real FILE object into a folder. Its own
        # row rather than the bare /drive/v1/files one for the reason every family here gets
        # one: longest prefix wins, and filing an UPLOAD under the non-observation recorded
        # for a trash-move and a folder listing would attribute one family's silence to
        # another's. This is also the row a consumer will look for first, because it is the
        # one that WRITES into somebody's Drive.
        "/open-apis/drive/v1/files/upload_all", "write",
        (),
        (
            "no scope string has ever been observed demanded for a single-shot file upload "
            "into a folder. It answered code:0 on the WRITE credential pair, uploading an html "
            "into a folder the harness itself created "
            "(dev/media-spike/captures/203-ac2-files-upload-all-parent-type-explorer-into-the-disposable-folder.json, "
            "in the dev repo), and no denial has ever been captured on it. That establishes "
            "REACH and attributes nothing: under the credential aliasing recorded in "
            "PROJECT.md (in the dev repo; on the tenant these measurements were made on, the "
            "READ and WRITE pairs named one app) a same-tenant success cannot attribute a "
            "scope at all. So the requirement is documented-unverified with NO scope string "
            "carried, because a plausible-looking drive scope name nobody has seen would read "
            "as an answer. ONE THING IS STILL OPEN AND IS NOT QUIETLY CLOSED HERE: whether "
            "this call succeeds on READ credentials is UNMEASURED — the spike ran entirely on "
            "the WRITE pair, and on the tenant these measurements were made on the two pairs named one app, so the question "
            "is not answerable here at all rather than merely untried. The CHUNKED upload "
            "family (upload_prepare / part / finish) has its own three rows below and nothing "
            "here describes it"
        ),
    ),
    (
        # THE ONE R3 ORGANIZE VERB (LD-467) — creating a FOLDER under a parent, opened by the maintainer
        # ruling on 2026-08-14. Its own row rather than the bare /drive/v1/files one for the
        # reason every family here gets one: longest prefix wins, and filing a CREATE under the
        # non-observation recorded for a trash-move and a folder listing would attribute one
        # family's silence to another's. The rest of the rung (move, rename, copy, delete a
        # folder, shortcut) has NO row here on purpose — this table declares the endpoints this
        # library CALLS, and a row for a verb nobody ships would read as a verb somebody could.
        "/open-apis/drive/v1/files/create_folder", "write",
        (),
        (
            "no scope string has ever been observed demanded for creating a folder under a "
            "parent. It answered code:0 on the WRITE credential pair repeatedly on 2026-08-15, "
            "every create going into a folder the probe itself made under the calling app's "
            "own root and swept afterwards "
            "(tests/captures/ld467-create-folder/captures/ld467-01-create-the-disposable-parent-under-the-bots-own-root.json "
            "and the ld467-02- / 03- duplicate pair, in the source repository), and no denial "
            "has ever been captured on it. That establishes REACH and attributes nothing: "
            "under the credential aliasing recorded in PROJECT.md (in the dev repo; on the "
            "tenant these measurements were made on, the READ and WRITE pairs named one app) a "
            "same-tenant success cannot attribute a scope at all, so the requirement is "
            "recorded UNKNOWN with NO scope string carried and is deliberately not guessed — a "
            "plausible-looking drive scope name nobody has seen would read as an answer. TWO "
            "THINGS ARE OPEN AND ARE NOT QUIETLY CLOSED HERE: whether the call succeeds on "
            "READ credentials is UNMEASURED and, on this tenant, not answerable at all; and "
            "the two refusals this route WAS measured producing are both about the request "
            "rather than about a permission — Lark's own field validation refuses an absent "
            "folder_token (ld467-05-) and 1061002 params error. for a parent nothing resolves "
            "and for a parent token that is a FILE rather than a folder (ld467-08- / "
            "ld467-11-) — so neither establishes anything about a scope either. What a DENIAL "
            "on this route looks like is therefore unmeasured rather than refuted"
        ),
    ),
    (
        # THE CHUNKED HALF OF THE UPLOAD RUNG (LD-449) — three rows, not one, because they are
        # three endpoints and a caller reading a matrix should find the one they are about to
        # call. Their own rows rather than the single-shot upload's for the same longest-prefix
        # reason every family here gets one: filing a partitioned upload under the non-
        # observation recorded for upload_all would attribute one call's silence to another's.
        "/open-apis/drive/v1/files/upload_prepare", "write",
        (),
        (
            "no scope string has ever been observed demanded for asking Lark how to partition "
            "an upload. It answered code:0 twice on the WRITE credential pair — for a 130-byte "
            "file and for a DECLARED 64 MiB that was never sent "
            "(tests/captures/drive-media-remainder-spike/captures/703- and 704-, in the source "
            "repository) — and named no scope in doing so. That establishes REACH and "
            "attributes nothing: under the credential aliasing recorded in PROJECT.md (in the "
            "dev repo; on the tenant these measurements were made on, the READ and WRITE pairs "
            "named one app) a same-tenant success cannot attribute a scope at all. So the "
            "requirement is recorded unknown with NO scope string carried, because a "
            "plausible-looking drive scope name nobody has seen would read as an answer, and "
            "it is deliberately never guessed"
        ),
    ),
    (
        "/open-apis/drive/v1/files/upload_part", "write",
        (),
        (
            "no scope string has ever been observed demanded for sending one block of an "
            "upload. ONE part was ever sent (seq 0, 130 bytes, one file type), on the WRITE "
            "credential pair, with the optional Adler-32 checksum OMITTED, and it was accepted "
            "with code:0 (tests/captures/drive-media-remainder-spike/captures/705-, in the "
            "source repository). That establishes REACH on one part and attributes nothing — "
            "under the credential aliasing recorded in PROJECT.md (in the dev repo) a "
            "same-tenant success cannot attribute a scope at all — so the requirement is "
            "recorded unknown and deliberately not guessed"
        ),
    ),
    (
        "/open-apis/drive/v1/files/upload_finish", "write",
        (),
        (
            "no scope string has ever been observed demanded for closing an upload "
            "transaction. It answered code:0 with a file_token on the WRITE credential pair "
            "(tests/captures/drive-media-remainder-spike/captures/706-, in the source "
            "repository), and that answer was an ACCEPTANCE rather than a verdict: only the "
            "re-download and its sha256 match made it a finding (707-). REACH is established "
            "and nothing is attributed — under the credential aliasing recorded in PROJECT.md "
            "(in the dev repo) a same-tenant success cannot attribute a scope at all — so the "
            "requirement is recorded unknown and deliberately not guessed"
        ),
    ),
    (
        # THE FILE-BYTES DOWNLOAD (LD-434) — the other end of the same round trip. Its own row
        # for the same longest-prefix reason, and because it is a DIFFERENT family from the
        # medias download two rows up: a drive FILE object is not drive MEDIA, and the two
        # differ in the one way a consumer cares about — a file can be deleted, media cannot.
        "/open-apis/drive/v1/files/:file_token/download", "write",
        (),
        (
            "no scope string has ever been observed demanded for downloading a file object's "
            "bytes. It answered with a body whose sha256 matched the upload's, on the WRITE "
            "pair's already-granted set "
            "(dev/media-spike/captures/206-ac2-byte-identity-drive-files-download-of-the-"
            "uploaded-html.json, in the dev repo — verified by hash, with no bytes "
            "inspected), and named no scope in doing so. The same honest gap as the upload "
            "row above, seen from the other end of the round trip, and recorded unknown "
            "rather than guessed"
        ),
    ),
    (
        # THE VERSIONS FAMILY, READ HALF (LD-409) — a file's NAMED versions. It needs a row of
        # its own for the same reason the comment family does: the longest matching prefix
        # wins, and answering it at the bare /drive/v1/files row would file a distinct
        # endpoint family under another family's non-observation.
        "/open-apis/drive/v1/files/:file_token/versions", "read",
        (),
        (
            "no scope string has ever been observed demanded for the file-versions family. "
            "Every versions route answered code 0 on BOTH credential pairs in the editions "
            "spike — the listing on the READ pair "
            "(tests/captures/editions-spike/captures/07-leg1-list-versions-read-pair-page-size-10.json, "
            "in the source repository) and the create on the WRITE pair "
            "(02-leg0-leg2-create-version-write-pair-drive-v1-files-versions.json), with the "
            "READ pair reaching the create route too (that recording is not published). That "
            "establishes REACH and attributes nothing: under the credential aliasing recorded "
            "in PROJECT.md (in the dev repo; on the tenant these measurements were made on, "
            "the READ and WRITE pairs named one app) a same-tenant success cannot attribute a "
            "scope at all, and no denial has ever named one here. No scope string is carried "
            "because none has ever been seen — a plausible-looking drive scope name nobody has "
            "observed would read as an answer, so the requirement is recorded unknown and "
            "deliberately not guessed"
        ),
    ),
    (
        # THE VERSIONS FAMILY, WRITE HALF (LD-409) — creating a named version. The Drive
        # surface's first mutating op, and its requirement is exactly as unobserved as the
        # read half's: the same non-observation, recorded under the write pair rather than
        # inherited from the read row (a mode is not a detail a reader should have to infer).
        "/open-apis/drive/v1/files/:file_token/versions", "write",
        (),
        (
            "no scope string has ever been observed demanded for creating a named version. It "
            "answered code 0 on the WRITE credential pair "
            "(tests/captures/editions-spike/captures/02-leg0-leg2-create-version-write-pair-drive-v1-files-versions.json, "
            "in the source repository) and, on the same route, on the READ pair (that "
            "recording is not published) — which under the credential aliasing recorded in "
            "PROJECT.md (in the dev repo; on the tenant these measurements were made on, the "
            "READ and WRITE pairs named one app) distinguishes nothing at all. The write app "
            "does hold docx:document, but this is a drive/v1 endpoint and nothing here "
            "separates 'authorized by docx:document' from 'authorized by a drive scope the app "
            "also holds', so the requirement is recorded unknown and deliberately not guessed. "
            "The one leg of create_version that DOES carry an established requirement is its "
            "head-revision read, which reaches the docx documents family and is answered by "
            "that family's own row"
        ),
    ),
    (
        # THE OWNER LEG ON THE WRITE PAIR (LD-432). The same endpoint as the row above, on the
        # OTHER credential pair, and it needs its own row rather than a widened mode: the
        # enumeration reads a folder's title on the READ pair, while the access surface reads a
        # document's OWNER on the WRITE pair, and collapsing them to "*" would quietly assert
        # that one non-observation covers both pairs.
        "/open-apis/drive/v1/metas/batch_query", "write",
        (),
        (
            "no scope string has ever been observed demanded for this endpoint on the WRITE "
            "pair. It answered code 0 there in the permissions spike "
            "(tests/captures/permissions-spike/captures/704-ld420-leg0-d-drive-meta-owner-id-and-url-for-the-fresh-disposable.json, "
            "in the source repository), reporting the owner of a document the app had just "
            "created. That establishes REACH and attributes nothing: a requirement labelled "
            "from documentation alone would be documented-unverified at best, no scope string "
            "has ever been seen for it, and under the credential aliasing recorded in "
            "PROJECT.md (in the dev repo; on the tenant these measurements were made on, the "
            "READ and WRITE pairs named one app) a same-tenant success cannot attribute a "
            "scope at all — so the requirement is recorded unknown and deliberately not guessed"
        ),
    ),
    (
        # THE PERMISSION MEMBER FAMILY (LD-432) — who may use a document. Its own row for the
        # same reason the comments and versions families have theirs: longest prefix wins, and
        # answering it at the bare /drive/v1/files row would file a distinct endpoint family
        # under another family's non-observation. All four verbs (GET/POST/PUT/DELETE) resolve
        # here, including the per-member paths under it.
        "/open-apis/drive/v1/permissions/:file_token/members", "write",
        (),
        (
            "no scope string has ever been observed demanded for the permission-member family. "
            "Every verb answered code 0 on the WRITE credential pair in the permissions spike "
            "(tests/captures/permissions-spike/captures/, in the source repository: 702- and "
            "708- list, 707- and 729- grant, 731- and 733- update, 736- revoke), and NO scope "
            "denial was elicited anywhere in that spike. That establishes REACH and attributes "
            "nothing: a requirement asserted from documentation alone would be "
            "documented-unverified at best, and no scope string is carried here because none "
            "has ever been seen — a plausible-looking drive scope name nobody has observed "
            "would read as an answer. The write app does hold docx:document, but this is a "
            "drive/v1 endpoint and nothing here separates 'authorized by docx:document' from "
            "'authorized by a drive scope the app also holds'; and under the credential "
            "aliasing recorded in PROJECT.md (in the dev repo; on the tenant these "
            "measurements were made on, the READ and WRITE pairs named one app) a same-tenant "
            "success cannot attribute a scope at all. So the requirement is recorded unknown "
            "and deliberately not guessed. NOTE the version: the member family is v1 — the v2 "
            "spelling of it is not a route at all (capture 703- in the same directory: '404 page not found' as "
            "plain text, not a Lark envelope)"
        ),
    ),
    (
        # THE PUBLIC-SETTINGS FAMILY (LD-432) — the document-level switches, of which this
        # library sets exactly two (copy_entity / security_entity). A v2 family, and a
        # different one from the members half above, so it carries its own row.
        "/open-apis/drive/v2/permissions/:file_token/public", "write",
        (),
        (
            "no scope string has ever been observed demanded for the public-settings family. "
            "Both the PATCH and the read-back GET answered code 0 on the WRITE credential pair "
            "in the permissions spike (tests/captures/permissions-spike/captures/705-, 709- to "
            "712-, in the source repository), and the two refusals that family did produce "
            "were about the KEY rather than about a scope: 1063001 Invalid parameter for "
            "lock_switch (721-, the same code an invented key gets, 725-) and 91009 for "
            "external_access_entity (715-). Neither names a scope, so neither establishes a "
            "requirement. A requirement asserted from documentation alone would be "
            "documented-unverified at best, and no scope string is carried here because none "
            "has ever been seen; under the credential aliasing recorded in PROJECT.md (in the "
            "dev repo; on the tenant these measurements were made on, the READ and WRITE pairs "
            "named one app) a same-tenant success cannot attribute a scope at all. The "
            "requirement is recorded unknown and deliberately not guessed"
        ),
    ),
    # ---- boards (the diagram image leg) ----
    (
        "/open-apis/board/v1/whiteboards", "read",
        (
            Scope(
                scope="board:whiteboard:node:read",
                verification="documented-unverified",
                evidence=(
                    "carried in this project's OWN prose for this endpoint since the diagram "
                    "handler was written (the docstring of larkdocio.blocks.diagram and the "
                    "board row of BLOCKS.md). It has never been observed demanded: no capture "
                    "in this repository shows Lark asking for it, and the whiteboard image "
                    "download succeeds on the read app's granted set, so nothing here "
                    "distinguishes 'required and held' from 'not required'"
                ),
                established=False,
                note=(
                    "a CANDIDATE, not a confirmed requirement — try it if the image download "
                    "is denied, and read the denial body, which names what Lark actually wants"
                ),
            ),
        ),
        (
            "the one scope string this project associates with the whiteboard image download "
            "is a CANDIDATE rather than an established requirement: no scope string has ever "
            "been observed demanded here, so it is reported unverified and is deliberately "
            "kept out of any surface's asserted requirement"
        ),
    ),
    # ---- wiki node resolution ----
    (
        "/open-apis/wiki/v2/spaces", "read",
        (),
        (
            "no scope string has ever been observed demanded for resolving a wiki node to "
            "its underlying document; it succeeds on the read app's granted set, so the "
            "requirement is documented-but-unverified and deliberately not guessed"
        ),
    ),
    # ---- spreadsheets ----
    (
        "/open-apis/sheets/v2/spreadsheets", "*",
        (),
        (
            "no scope string has ever been observed demanded for the spreadsheet values "
            "family; reachability is confirmed on both credential pairs, so the requirement "
            "is documented-but-unverified and deliberately not guessed. The IN-CELL IMAGE "
            "write joins this same family and changes nothing about it: values_image and "
            "the values read that is its verdict both answered code:0 on the write app's "
            "ALREADY-GRANTED set (tests/captures/sheets-media-spike/captures/202-, 203-, 305-, 306-, "
            "in the source repository), no scope was widened, requested or escalated, and because "
            "nothing was DENIED there is still no string to record"
        ),
    ),
    (
        "/open-apis/sheets/v3/spreadsheets", "*",
        (),
        (
            "no scope string has ever been observed demanded for the spreadsheet metadata "
            "family; reachability is confirmed on both credential pairs, so the requirement "
            "is documented-but-unverified and deliberately not guessed"
        ),
    ),
    # ---- Base (bitable) — the L1 READ surface (LD-247) ----
    #
    # ONE prefix row covers all five read families the Base client reaches (app meta, tables,
    # views, fields, records/search): they sit under the same path root and Lark governs them
    # with the same grant. The five endpoints are DERIVED from the client's own code and each
    # resolves here by longest-prefix, so the row cannot quietly stop covering one of them.
    #
    # `read` only, deliberately. L1 is read-only end to end (every op declares
    # `mutates: False`), so no bitable call is ever made on the write pair and a `write` row
    # would assert a requirement for a call that does not exist.
    (
        "/open-apis/bitable/v1/apps", "read",
        (
            Scope(
                scope="bitable:app:readonly",
                verification="grant-verified",
                evidence=(
                    "the Base opener's scope table (dev/base-study-2026-08-03.md § 3, in the "
                    "dev repo) records the family as EFFECTIVE on this tenant — every "
                    "app-meta, tables, views, fields and records/search read answered code:0 "
                    "across the committed captures tests/captures/base-study/captures/00-*, 01-* and "
                    "p1-q0-*. Lark never "
                    "echoed the string back (there was no denial to echo it), so this is "
                    "behavioural confirmation of a held grant, not a captured demand"
                ),
                note="without it no Base can be read at all",
            ),
        ),
        None,
    ),
    # ---- Base (bitable) — the WRITE families (LD-255 records, LD-262..LD-265 schema) ----
    #
    # ONE prefix row covers every Base write: the six record families — create, update and
    # delete, each singly and in batch — the nine non-destructive SCHEMA ops (Base create, app
    # rename, the async copy, table create, table batch_create, table rename, plus the field
    # family's create, non-type edit and captured-pair convert on `…/tables/{t}/fields` and
    # `…/tables/{t}/fields/{f}`), the three VIEW ops (view create, the view PATCH that carries
    # the persistent filter, view delete), and the three DESTRUCTIVE schema ops
    # (`DELETE …/tables/{t}/fields/{f}`, `DELETE …/tables/{t}`, `POST …/tables/batch_delete`).
    # They sit
    # under the same path root as the reads and Lark governs them with the same grant, but on
    # the WRITE credential pair, which is why this is a second row rather than a widening of the
    # read one: the read families must keep resolving to `bitable:app:readonly`, and a row that
    # answered both modes would quietly assert that a read needs write scope.
    #
    # Every endpoint is DERIVED from the calling code — the write client's and the schema
    # client's — and each resolves here by longest-prefix, so the row cannot quietly stop
    # covering one of them. **Four delete verbs reach this row.** One of them —
    # `DELETE …/views/{v}` — has a view for a blast radius and is floored by the server at one
    # view per table (`1254023`). The other three can lose DATA — a column, a table, and a batch
    # of tables — and they arrived WITH their fence rather than by widening this row: each is
    # declared destructive, each produces a cross-table loss preview in the dry run, and none is
    # reachable without explicit consent to that plan's own enumerated loss.
    # The drive-file delete that removes a Base still does NOT reach this row: it is not a
    # shipped op at all, only a live-harness primitive.
    # **No scope is widened by any of them**: a column create, a view write and a table delete
    # each need exactly what a record write needs, which is asserted in both directions in
    # tests/test_base_schema_fields.py, tests/test_base_schema_views.py and
    # tests/test_base_schema_destructive.py.
    (
        "/open-apis/bitable/v1/apps", "write",
        (
            Scope(
                scope="bitable:app",
                verification="grant-verified",
                evidence=(
                    "every record write the probe packs made answered code 0 on the write "
                    "credential pair (the captures below are in the source repository) — the create "
                    "echo and the batch create in "
                    "tests/captures/base-study/captures/06-02-record-create-echo.json and "
                    "tests/captures/base-study/captures/05-06-records-batch-create.json, the update and "
                    "the batch delete in tests/captures/base-study/captures/p1-q6-01-value-writes.json, "
                    "and the single delete in "
                    "tests/captures/base-study/captures/06-06-destructive-ops.json. Lark never echoed "
                    "the string back (there was no denial to echo it), so this is "
                    "behavioural confirmation of a held grant, not a captured demand"
                ),
                note="without it no record can be created, updated or deleted",
            ),
        ),
        None,
    ),
    # ---- the token mint every client does first ----
    (
        "/open-apis/auth/v3/tenant_access_token", "*",
        (),
        (
            "no scope is required to mint a tenant token — the app credentials alone are "
            "the whole requirement, and every live ring proves it by minting one"
        ),
    ),
)


#: Scope denials Lark actually returned to this app, captured verbatim. Several are required
#: by no shipped operation; they are kept as the evidence base a permission refusal is
#: proved against, and because they are the record of what a denial body actually contains.
OBSERVED_DENIALS: Tuple[Denial, ...] = (
    Denial(
        scope="directory:employee:search",
        code=99991672,
        msg=("Access denied. One of the following scopes is required: "
             "[directory:employee:search]"),
        capture=_SPIKE + ": reprobe/captures/R1-search-owner-exact-READ.json; the first "
                         "probe's capture P1 drew the same body, recorded in " + _SPIKE_RECORD,
        # The app id segment is a PLACEHOLDER, not what Lark returned (LD-678): a console
        # link is per-app, so substitute your own application id. The capture cited above
        # holds the link exactly as Lark sent it.
        help_url=("https://open.larksuite.com/app/<your-app-id>/auth"
                  "?q=directory:employee:search&op_from=openapi&token_type=tenant"),
        # Since LD-229 there IS a shipped call site: larkdocio.contacts. The denial rows are
        # kept as the evidence base a refusal is proved against, and this one is now also the
        # other half of a live requirement — see the endpoint row above.
        required_by_a_shipped_operation=True,
    ),
    Denial(
        scope="directory:employee:list",
        code=99991672,
        msg=("Access denied. One of the following scopes is required: "
             "[directory:employee:list]"),
        capture=("captures P8 and R3 of the name-lookup spike, recorded in "
                 + _SPIKE_RECORD),
    ),
    Denial(
        scope="directory:employee:read",
        code=99991672,
        msg=("Access denied. One of the following scopes is required: "
             "[directory:employee:read]"),
        capture="capture R2 of the name-lookup spike, recorded in " + _SPIKE_RECORD,
    ),
    Denial(
        scope="contact:group:readonly",
        code=99991672,
        msg=("Access denied. One of the following scopes is required: "
             "[contact:group:readonly]"),
        capture="capture P12 of the name-lookup spike, recorded in " + _SPIKE_RECORD,
    ),
    Denial(
        scope="admin:app.info:readonly",
        code=99991672,
        msg=("Access denied. One of the following scopes is required: "
             "[admin:app.info:readonly, application:application:self_manage]"),
        capture="capture R7 of the name-lookup spike, recorded in " + _SPIKE_RECORD,
    ),
    # The same body names a SECOND scope, and it earns its own row: Lark demanded it, so it is
    # denial-verified evidence, and recording only the first left its string unknown to the
    # registry while sitting in the message text above.
    Denial(
        scope="application:application:self_manage",
        code=99991672,
        msg=("Access denied. One of the following scopes is required: "
             "[admin:app.info:readonly, application:application:self_manage]"),
        capture="capture R7 of the name-lookup spike, recorded in " + _SPIKE_RECORD,
    ),
)


# --------------------------------------------------------------------------- #
# THE DERIVATION — an operation's endpoints, read off its own code.             #
# --------------------------------------------------------------------------- #

_PATH_RE = re.compile(r"/open-apis/[A-Za-z0-9_/:{}\-\.]*")

#: How deep the walk follows calls inside this package before giving up. Ten is far more
#: than any real chain here (the longest is four); the cap only exists so a cycle or a
#: pathological graph cannot hang a projection.
_MAX_DEPTH = 10


def _paths_in(text: Optional[str]) -> set:
    return {match.rstrip("/") for match in _PATH_RE.findall(text or "")}


def _sdk_request_uri(obj) -> Optional[str]:
    """The ``uri`` a pinned-SDK request class carries, or ``None`` if ``obj`` is not one.

    The SDK sets the path on the object its builder produces, so the class is asked for one
    the same way a caller would build it. This is what makes an SDK-typed call site as
    derivable as a raw-path one.
    """
    if not inspect.isclass(obj):
        return None
    if not (getattr(obj, "__module__", "") or "").startswith("lark_oapi"):
        return None
    if not obj.__name__.endswith("Request"):
        return None
    try:
        return getattr(obj.builder().build(), "uri", None)
    except Exception:  # pragma: no cover - a request class that cannot be built empty
        return None


def _annotated_classes(annotation) -> List[type]:
    """The concrete classes an annotation names — a bare class, or the members of a union
    (so ``Optional[CommentsReadClient]`` still resolves to the client class)."""
    if inspect.isclass(annotation):
        return [annotation]
    return [a for a in typing.get_args(annotation)
            if inspect.isclass(a) and a is not type(None)]


def _resolution_env(fn, seeds: Dict[str, type]) -> Dict[str, object]:
    """``{local name: object}`` for the attribute lookups in ``fn``'s body.

    Three sources, in increasing priority: a parameter's annotation (so ``client:
    WriteClient`` makes ``client._patch_block`` resolvable), the owning class for ``self``,
    and the caller's ``seeds`` — which is how an unannotated ``client`` parameter is bound to
    the client class the surface actually hands it.
    """
    env: Dict[str, object] = {}
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        hints = {}
    try:
        parameters = inspect.signature(fn).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins have no signature
        parameters = {}
    for name in parameters:
        for cls in _annotated_classes(hints.get(name)):
            env.setdefault(name, cls)
    qualname = getattr(fn, "__qualname__", "")
    if "." in qualname:
        owner = (getattr(fn, "__globals__", {}) or {}).get(qualname.rsplit(".", 2)[0])
        if owner is not None:
            env["self"] = owner
    for name, cls in seeds.items():
        if name in parameters:
            env[name] = cls
    return env


#: The ONLY module prefixes the derivation will import in order to resolve a function-local
#: import. Resolving one means executing an import at derivation time, so what may be
#: imported is fenced to this library and the pinned SDK — the two things already loaded in
#: any process that is asking. An import of anything else is DISCLOSED as unresolved rather
#: than executed: a registry that imported arbitrary third-party modules to answer a
#: permission question would be buying an answer with a side effect.
IMPORTABLE_PREFIXES = ("larkdocio", "lark_oapi")

#: The parameter names the surfaces' seed table exists for — a call site handed the object
#: whose methods reach Lark. Structural, not a guess about values: these are the names this
#: library uses for an injected client or reader (:data:`larkdocio.capabilities._permissions._IMPL_SEEDS`
#: binds exactly this shape), and one of them left bound to no class is a hole in the
#: derivation rather than an ordinary argument.
_CLIENT_SHAPED = re.compile(r"^(client|reader|.*_client|.*_reader)$")


class _Reach(NamedTuple):
    """What one walk found: the endpoints it RESOLVED, and the seams it could not.

    The second field is the whole point of LD-609. A walk that returned only endpoints could
    not distinguish *"reaches nothing"* from *"reaches something I cannot see"*, and every
    consumer of it — including the coverage guard — read the first meaning off a shape that
    could equally be the second.
    """

    endpoints: frozenset
    unresolved: frozenset


_NO_REACH = _Reach(frozenset(), frozenset())


def _site(fn) -> str:
    return f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__qualname__', '?')}"


def endpoints_of(fn, seeds: Optional[Dict[str, type]] = None) -> Tuple[str, ...]:
    """Every Lark endpoint ``fn`` can reach **that this derivation can resolve**.

    Derived from ``fn``'s own code: the pinned-SDK request classes it builds, the raw Lark
    REST paths it names as literals or module constants, the calls it makes into this
    package, and — since LD-609 — the symbols it binds through a **function-local import**
    of this package or the pinned SDK. (The path *prefix* is deliberately not spelled in this
    docstring: this function is itself in the corpus its own walk scans, and a literal here
    would derive as an endpoint reached by every caller of it.)

    **The qualifier in the first line is load-bearing and was once absent.** The name
    resolution is static, so a seam it cannot resolve — a dynamically named import, an object
    handed in as an unannotated parameter with no seed, a client constructed into a local
    variable — reaches endpoints that are **not in this tuple**. Those seams are not silently
    dropped: :func:`unresolved_call_sites_of` names them, every operation's permission block
    carries them, and :func:`coverage_gaps` reports the operation as ``undetermined``. **An
    empty tuple is therefore only a claim that the operation needs nothing when
    :func:`unresolved_call_sites_of` is also empty** — read the two together, exactly as a
    surface's ``scopes`` is read together with its ``unknown_requirements``.

    ``seeds`` binds a parameter name to the class the caller passes it, for the call sites
    that take an unannotated client. Returns a sorted tuple, so a registry built from this
    is deterministic.
    """
    return tuple(sorted(_reach_of(fn, _seed_items(seeds)).endpoints))


def unresolved_call_sites_of(fn, seeds: Optional[Dict[str, type]] = None) -> Tuple[str, ...]:
    """Every seam inside ``fn``'s reach where the derivation stopped, each naming its site.

    The honest-unknown discipline applied to the derivation itself rather than to the
    endpoint→scope join (:func:`unknown_requirements_for` is that one): where
    ``unknown_requirements`` says *"this endpoint's requirement was never observed"*, this
    says *"there may be an endpoint here that I could not see"*. Two kinds are recorded, both
    structural:

    * a **function-local import** the walk may not follow — outside
      :data:`IMPORTABLE_PREFIXES`, or dynamically named, so there is no static answer and
      none is invented;
    * a **client-shaped parameter bound to no class** — no annotation and no seed — whose
      methods are called in the body, so the calls made on it are not derivable.

    Empty means the walk resolved every seam it met, which is what entitles an empty
    ``endpoints_of`` to read as *needs no permission*.
    """
    return tuple(sorted(_reach_of(fn, _seed_items(seeds)).unresolved))


def _seed_items(seeds):
    return tuple(sorted((seeds or {}).items(), key=lambda kv: kv[0]))


@functools.lru_cache(maxsize=None)
def _reach_of(fn, seed_items) -> _Reach:
    return _walk(fn, seed_items, frozenset(), 0)


def _local_import_env(fn, tree, site) -> Tuple[Dict[str, object], frozenset]:
    """``({local name: object}, {unresolved record})`` for ``fn``'s function-local imports.

    **The LD-609 fix.** ``_resolution_env`` answers for parameters and ``self``; module
    globals answer for module-level imports; a symbol imported *inside* the body was in
    neither, so the endpoints behind it derived as nothing at all. An ``ast.ImportFrom`` in
    the body is now an operand: the module is imported (fenced to
    :data:`IMPORTABLE_PREFIXES`) and its names bound the way the function itself binds them
    at call time.

    A relative import resolves against ``fn``'s own module, so a leg that reaches its
    sibling through ``from . import x`` is derivable too. Anything this cannot resolve is
    returned as a record rather than dropped.
    """
    env: Dict[str, object] = {}
    unresolved = set()
    module_name = getattr(fn, "__module__", "") or ""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if node.col_offset == 0:  # the module's own imports; globals already carry them
            continue
        if isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                package = module_name.rsplit(".", node.level)[0]
                base = f"{package}.{base}" if base else package
            module = _importable(base)
            if module is None:
                unresolved.add(_unfollowed(site, base or "."))
                continue
            for alias in node.names:
                obj = getattr(module, alias.name, None)
                if obj is None:
                    obj = _importable(f"{base}.{alias.name}")
                if obj is None:
                    unresolved.add(_unfollowed(site, f"{base}.{alias.name}"))
                else:
                    env[alias.asname or alias.name] = obj
            continue
        for alias in node.names:
            # ``import a.b as x`` binds x to a.b; ``import a.b`` binds a.
            wanted = alias.name if alias.asname else alias.name.split(".")[0]
            module = _importable(wanted)
            if module is None:
                unresolved.add(_unfollowed(site, alias.name))
            else:
                env[alias.asname or wanted] = module
    return env, frozenset(unresolved)


def _importable(name: str):
    """*name*'s module if the derivation is allowed to import it, else ``None``."""
    if not name or not name.startswith(IMPORTABLE_PREFIXES):
        return None
    try:
        return importlib.import_module(name)
    except Exception:  # pragma: no cover - a module that will not import is unresolved
        return None


def _unfollowed(site: str, module: str) -> str:
    return (f"{site}: a function-local import of {module!r} the derivation cannot follow, so "
            "any endpoint reached through it is not in this operation's endpoint list")


def _unbound_client_parameters(fn, tree, env, site) -> frozenset:
    """The client-shaped parameters ``fn`` calls methods on and the derivation cannot resolve.

    The seed table (``_IMPL_SEEDS``) exists because a surface knows which class it hands a
    bare ``client``; where no seed and no annotation says so, the object whose methods reach
    Lark is not knowable from this source. That is recorded here rather than left to read as
    an operation that calls nothing — and it is recorded per **site**, so the record names
    the function whose signature would resolve it.
    """
    try:
        parameters = inspect.signature(fn).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins have no signature
        return frozenset()
    out = set()
    for name in parameters:
        if not _CLIENT_SHAPED.match(name) or inspect.isclass(env.get(name)):
            continue
        if not _calls_a_method_on(tree, name):
            continue
        out.add(f"{site}: parameter {name!r} is bound to no class — no annotation and no "
                "seed — so the calls made on it are not derivable")
    return frozenset(out)


def _calls_a_method_on(tree, name: str) -> bool:
    """Whether the body ever calls a method ON *name*.

    The narrowing that keeps this instrument sharp: a client-shaped parameter that is only
    passed along or stored reaches no endpoint *here*, and flagging it would drown the real
    records in noise — the failure mode of a check nobody can read.
    """
    return any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and isinstance(node.func.value, ast.Name)
               and node.func.value.id == name
               for node in ast.walk(tree))


def _walk(fn, seed_items, seen, depth) -> _Reach:
    key = (getattr(fn, "__module__", None), getattr(fn, "__qualname__", None))
    if key in seen or depth > _MAX_DEPTH:
        return _NO_REACH
    seen = seen | {key}
    try:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    except (OSError, TypeError, SyntaxError):  # pragma: no cover - no source available
        return _NO_REACH
    seeds = dict(seed_items)
    globals_ = getattr(fn, "__globals__", {}) or {}
    env = _resolution_env(fn, seeds)
    site = _site(fn)
    local_env, unresolved = _local_import_env(fn, tree, site)
    unresolved = set(unresolved) | _unbound_client_parameters(fn, tree, env, site)
    out: set = set()

    def holder_of(name):
        # A parameter's annotation or a seed WINS over a same-named local import: the caller
        # said which object is passed, and the import is how the module was reached.
        if name in env:
            return env[name]
        if name in local_env:
            return local_env[name]
        return globals_.get(name)

    def add(obj):
        reach = _resolve(obj, seed_items, seen, depth)
        out.update(reach.endpoints)
        unresolved.update(reach.unresolved)

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out |= _paths_in(node.value)
        elif isinstance(node, ast.Name):
            add(local_env.get(node.id, globals_.get(node.id)))
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            holder = holder_of(node.value.id)
            if holder is not None:
                add(getattr(holder, node.attr, None))
        else:
            name, attr = _getattr_pair(node)
            if name is not None:
                holder = holder_of(name)
                if holder is not None:
                    add(getattr(holder, attr, None))
    return _Reach(frozenset(out), frozenset(unresolved))


def _getattr_pair(node):
    """``("client", "validate_user_ids")`` for a ``getattr(client, "validate_user_ids", …)``
    call, else ``(None, None)``.

    A duck-typed seam reaches its method through :func:`getattr` with a string, which is
    invisible to an attribute walk — and the plan-time mention check is exactly that shape.
    Without this the one contacts call a spreadsheet write can make would derive as absent,
    which is the silent-incompleteness failure this registry exists to prevent.
    """
    if not isinstance(node, ast.Call):
        return None, None
    func = node.func
    if not (isinstance(func, ast.Name) and func.id == "getattr"):
        return None, None
    if len(node.args) < 2:
        return None, None
    base, attr = node.args[0], node.args[1]
    if isinstance(base, ast.Name) and isinstance(attr, ast.Constant) \
            and isinstance(attr.value, str):
        return base.id, attr.value
    return None, None


def _resolve(obj, seed_items, seen, depth) -> _Reach:
    """One referenced object's contribution: an SDK request class's path, a path constant,
    or — for a function in this package — whatever that function itself can reach, INCLUDING
    the seams that function could not resolve (they are this operation's holes too)."""
    if obj is None:
        return _NO_REACH
    uri = _sdk_request_uri(obj)
    if uri:
        return _Reach(frozenset(_paths_in(uri)), frozenset())
    if isinstance(obj, str):
        return _Reach(frozenset(_paths_in(obj)), frozenset())
    if inspect.isfunction(obj) or inspect.ismethod(obj):
        if (getattr(obj, "__module__", "") or "").startswith("larkdocio"):
            return _walk(obj, seed_items, seen, depth + 1)
    return _NO_REACH


def clear_caches() -> None:
    """Drop the derivation cache. Only a test that mutates the code or the table needs
    this — the projection is otherwise a pure function of both."""
    _reach_of.cache_clear()
    shipped_call_sites.cache_clear()


# --------------------------------------------------------------------------- #
# THE JOIN — endpoints x mode -> scopes.                                       #
# --------------------------------------------------------------------------- #

def _table_row(endpoint: str, mode: str):
    """The longest matching :data:`ENDPOINT_SCOPES` row for one endpoint, or ``None``.

    Longest prefix wins, so ``/drive/v1/files/:file_token/comments`` is answered by the
    comment family's row rather than by the file family's — which is the whole reason the
    table is keyed by path rather than by the first path segment.
    """
    best = None
    for prefix, row_mode, scopes, note in ENDPOINT_SCOPES:
        if row_mode not in (mode, "*"):
            continue
        if not endpoint.startswith(prefix):
            continue
        if best is None or len(prefix) > len(best[0]):
            best = (prefix, row_mode, scopes, note)
    return best


def scopes_for_endpoints(endpoints, mode: str) -> Tuple[Scope, ...]:
    """The scopes a set of endpoints requires on ``mode``'s credential pair, deduplicated
    and in table order."""
    out: List[Scope] = []
    for endpoint in endpoints:
        row = _table_row(endpoint, mode)
        if row is None:
            continue
        for scope in row[2]:
            if scope.scope not in {s.scope for s in out}:
                out.append(scope)
    return tuple(out)


def unknown_requirements_for(endpoints, mode: str) -> Tuple[str, ...]:
    """The reasons this operation's requirement is not fully known — one per endpoint whose
    table row is deliberately empty. Surfacing them is the honest-unknown discipline: the
    caller learns that we do not know, instead of reading an empty list as "needs nothing"."""
    out: List[str] = []
    for endpoint in endpoints:
        row = _table_row(endpoint, mode)
        if row is None or not row[3]:
            continue
        # The reason travels whenever the requirement is NOT ESTABLISHED — whether the row is
        # empty (no scope string ever observed) or carries only a CANDIDATE. Suppressing it in
        # the candidate case would let a plausible string read as a settled requirement, which
        # is the whole failure this field exists to avoid.
        if any(scope.established for scope in row[2]):
            continue
        reason = f"{row[0]}: {row[3]}"
        if reason not in out:
            out.append(reason)
    return tuple(out)


def permissions_for(impls, mode: str, credential_app: str, credentials_env,
                    seeds: Optional[Dict[str, type]] = None,
                    basis: str = "derived",
                    evidence: Optional[str] = None) -> Permissions:
    """One operation's :class:`Permissions`, derived from the callables that implement it.

    ``impls`` is one callable or several (a write op is implemented by its descriptor's
    several legs — resolve, preview, apply — and the union of what they reach is what the op
    requires).
    """
    if impls is None:
        impls = ()
    elif callable(impls):
        impls = (impls,)
    endpoints: set = set()
    unresolved: set = set()
    for impl in impls:
        endpoints |= set(endpoints_of(impl, seeds))
        unresolved |= set(unresolved_call_sites_of(impl, seeds))
    ordered = tuple(sorted(endpoints))
    scopes = scopes_for_endpoints(ordered, mode)
    return Permissions(
        endpoints=ordered,
        credential_app=credential_app,
        credentials_env=tuple(credentials_env),
        # Everything this operation requires, then the degrading SUBSET of it.
        scopes=scopes,
        optional_scopes=tuple(s for s in scopes if s.degrades),
        basis=basis,
        evidence=evidence,
        unknown_requirements=unknown_requirements_for(ordered, mode),
        unresolved_call_sites=tuple(sorted(unresolved)),
    )


def surface_projection(blocks, composed=()) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """A surface's ``(scopes, optional_scopes)`` as the UNION of its operations' rows.

    This is the unification: a surface no longer asserts a scope list of its own that could
    drift from its operations. ``composed`` carries the *required* scopes of any surface this
    one composes — the opt-in embedded-sheet bridge runs inside a document read, so the
    document scope is genuinely part of its requirement without any of its own calls naming
    it.
    """
    required: List[str] = []
    optional: List[str] = []
    for block in blocks:
        degrading = {scope.scope for scope in block.optional_scopes}
        for scope in block.scopes:
            # A CANDIDATE never becomes a surface requirement: the operation's own row reports
            # it as unverified, but a surface saying "you must hold this" would assert exactly
            # what the evidence does not support.
            if not scope.established:
                continue
            if scope.scope not in degrading and scope.scope not in required:
                required.append(scope.scope)
        for scope in block.optional_scopes:
            if not scope.established:
                continue
            if scope.scope not in optional:
                optional.append(scope.scope)
    for scope in composed:
        if scope not in required:
            required.append(scope)
    optional = [s for s in optional if s not in required]
    return tuple(sorted(required)), tuple(sorted(optional))


# --------------------------------------------------------------------------- #
# THE VIEW + THE DRIFT GUARD.                                                  #
# --------------------------------------------------------------------------- #

def _capabilities():
    """The capability registry — the WHOLE payload, imported lazily.

    ``capabilities`` imports this module to build its permission blocks, so the reverse
    direction has to be lazy — the same shape the packaged-documents projection uses.

    ``full=True`` because this module needs the rows, not the summary: ``capabilities()``'s
    no-argument answer is the names-only index a consumer reads first (LD-475), and a
    permission requirement is derived from the endpoints a row carries.
    """
    import importlib

    return importlib.import_module("larkdocio.capabilities").capabilities(full=True)


def _payload_keys():
    """``(CALL_SITES_KEY, CALL_KINDS)`` from the capability registry's typed layer, imported
    lazily for exactly the reason :func:`_capabilities` is: ``capabilities`` imports this
    module, so this module cannot import it back at module scope.

    Imported rather than re-spelled. The key name and the kind vocabulary are the payload's,
    authored once beside the dataclass that emits them; a copy of either here is how a walk
    of "the operations key" survives a rename of the operations key.
    """
    import importlib

    models = importlib.import_module("larkdocio.capabilities._models")
    return models.CALL_SITES_KEY, models.CALL_KINDS


def _surface_call_sites(surface):
    """Every call site of a surface, in one place: its dispatched operations, its
    non-dispatched **legs**, and its file-lifecycle calls.

    One helper because a call site the registry forgets to walk is a requirement written
    down nowhere — which is the exact failure this module exists to make impossible.

    **LD-459's reason, unchanged and load-bearing:** it walks the surface's **published**
    answer rather than a second hand-kept list of key names, so the enumeration a consumer
    reads and the enumeration the permission rows are built from are the same one — an
    operation cannot be in the registry and absent from the projection, the shape that hid 20
    API-using operations through 1.33.0.

    **LD-475 removed the premise rather than the rule.** That published answer was a pointer
    index (``operation_index``) because the rows lived under three sibling keys and a reader
    had to be told which. There is now **one** key — the one collapsed call-sites key — and every row in
    it carries its own ``kind``, so the walk *is* the published answer and there is no key
    list left for anything to keep a second copy of.
    """
    call_sites_key, _kinds = _payload_keys()
    return [(row.get("kind"), row) for row in surface.get(call_sites_key) or ()]


def permission_registry() -> Dict[Tuple[str, str], PermissionRow]:
    """``{(surface_id, operation): PermissionRow}`` for every operation in the library.

    A **view**: the scopes are re-joined from :data:`ENDPOINT_SCOPES` here, so a row cannot
    quietly differ from the table it came from. Lifecycle calls are rows too — creating and
    trashing a file is exactly the kind of call whose permission a caller needs before they
    try it.
    """
    rows: Dict[Tuple[str, str], PermissionRow] = {}
    for surface_id, surface in _capabilities()["surfaces"].items():
        mode = surface["mode"]
        for kind, op in _surface_call_sites(surface):
            block = op["permissions"]
            endpoints = tuple(block["endpoints"])
            scopes = scopes_for_endpoints(endpoints, mode)
            rows[(surface_id, op["name"])] = PermissionRow(
                surface=surface_id,
                operation=op["name"],
                kind=kind,
                mode=mode,
                endpoints=endpoints,
                credential_app=block["credential_app"],
                credentials_env=tuple(block["credentials_env"]),
                scopes=scopes,
                optional_scopes=tuple(s for s in scopes if s.degrades),
                api_using=block["api_using"],
                basis=block["basis"],
                evidence=block.get("evidence"),
                unresolved_call_sites=tuple(block.get("unresolved_call_sites") or ()),
            )
    return rows


def operation_inventory() -> Tuple[Tuple[Tuple[str, str], Tuple[str, ...]], ...]:
    """``((surface_id, operation), endpoints)`` for every operation that reaches Lark **or
    may reach it through a seam the derivation could not resolve**.

    The set the coverage guard is bidirectional against. Derived from the code, so an
    operation that starts calling Lark joins it without anyone deciding to add it.

    **LD-609 removed a circularity here, and the second clause of the first line is it.**
    This filtered on ``if endpoints:`` alone — so *API-using* was defined AS
    :func:`endpoints_of`'s own answer, and a call site the derivation could not see was, by
    this function's own definition, not API-using. It could therefore never be reported as an
    uncovered gap: the bidirectional guard greened over the hole and the door told a consumer
    they needed no permission. An operation whose derivation is INCOMPLETE now joins this
    inventory too — and, because the admission is keyed on the record and never on the
    endpoint tuple being empty, an operation that resolves three endpoints and loses a fourth
    joins it as well.
    """
    out = []
    for surface_id, surface in _capabilities()["surfaces"].items():
        for _kind, op in _surface_call_sites(surface):
            block = op["permissions"]
            endpoints = tuple(block["endpoints"])
            if endpoints or block.get("unresolved_call_sites"):
                out.append(((surface_id, op["name"]), endpoints))
    return tuple(out)


#: What a projected operation row looks like from the outside — a dict carrying a ``name`` and
#: the ``projected_from`` that says which code it came out of. Used to recognise a
#: callable-bearing key **without** consulting the field list the index is built from: two
#: independent derivations are what make :func:`projection_gaps` a real check rather than a
#: comparison of a thing with itself.
def _is_operation_row_list(value):
    return (isinstance(value, list) and bool(value)
            and all(isinstance(row, dict) and "name" in row and "projected_from" in row
                    for row in value))


def projection_gaps(surfaces=None):
    """THE PROJECTION direction — ``(unprojected, phantom)``, the direction that was broken.

    **The reason, unchanged (LD-459).** The 1.33.0 defect was that 20 API-using operations
    lived under sibling keys (``legs`` / ``lifecycle``) while the answer a consumer was
    pointed at was ``operations``, and the coverage check could not see it because the
    projection itself was never an operand. Whatever the payload's shape, a call site the
    projection publishes somewhere a consumer's one obvious read does not reach is the failure
    this direction exists to catch.

    **LD-475 changed only what "somewhere else" can be.** The three sibling keys are collapsed
    into the one collapsed call-sites key, so:

    * ``unprojected`` — ``(surface, key, operation)`` for a call site published under **any
      other** key. That is the same defect in the new shape: a fourth kind of call site added
      beside the collapsed key, reachable only by a reader who thought to look for it;
    * ``phantom`` — ``(surface, key, operation)`` for a row under the collapsed key whose
      ``kind`` is missing or outside the published kind vocabulary — a row a consumer cannot tell how to
      act on, which is the new shape of "a pointer a consumer cannot follow".

    The registry side stays duck-typed off the emitted dict
    (:func:`_is_operation_row_list`), NOT off ``Surface.CALLABLE_FIELDS`` — so adding a fourth
    kind of call site without joining it to the one key reddens here.
    """
    surfaces = _capabilities()["surfaces"] if surfaces is None else surfaces
    call_sites_key, kinds = _payload_keys()
    unprojected, phantom = [], []
    for surface_id, surface in sorted(surfaces.items()):
        for key, rows in sorted(surface.items()):
            if not _is_operation_row_list(rows):
                continue
            if key != call_sites_key:
                unprojected += [(surface_id, key, row["name"]) for row in rows]
                continue
            phantom += [(surface_id, key, row["name"]) for row in rows
                        if row.get("kind") not in kinds]
    return sorted(unprojected), sorted(phantom)


class CoverageGaps(NamedTuple):
    """The audit's directions, one field each — a NamedTuple so the next direction is an
    ADDITIVE field rather than a break (LD-459 changed the shape once; not twice)."""

    uncovered: list
    orphans: list
    unprojected: list
    phantom: list
    #: LD-609's field: ``(surface, operation)`` for a row whose derivation could not be
    #: completed. Additive, per this class's own rule.
    undetermined: list = []


def coverage_gaps(rows=None, inventory=None, surfaces=None) -> CoverageGaps:
    """THE drift check — ``(uncovered, orphans, unprojected, phantom)``.

    * ``uncovered`` — an operation that reaches Lark and has no permission row. Adding an
      API-using operation without one reddens here;
    * ``orphans`` — a row naming an operation that no longer exists;
    * ``undetermined`` — an operation whose derivation could not be COMPLETED (LD-609): a
      seam the static walk cannot resolve sits inside its reach, so its endpoints and its
      scopes may be short. **Keyed on the record, never on the endpoint tuple being empty** —
      an operation may resolve some endpoints through module globals and lose others to a
      seam, and an emptiness-keyed check greens on exactly that operation (LD-596's trap,
      which applies verbatim here);
    * ``unprojected`` / ``phantom`` — :func:`projection_gaps`, the **projection vs registry**
      direction (LD-459). The first two directions audit the registry against the CODE; a
      projection that omits an operation both of them know is invisible to them, which is
      exactly how ``([], [])`` was reported while 20 operations were unfindable.

    One function, used by the live guard AND by the tests that prove it bites, so the check
    that guards is provably the check that bites.

    **Shape change (1.34.0):** this returned a 2-tuple through 1.33.0. It is now a
    NamedTuple, five fields as of LD-609 — read ``gaps.uncovered`` / ``gaps.orphans`` /
    ``gaps.undetermined`` by name rather than unpacking.
    """
    rows = permission_registry() if rows is None else rows
    inventory = dict(operation_inventory()) if inventory is None else dict(inventory)
    # A row that DISCLOSES an unresolved seam is covered for this direction's purpose: it
    # exists, which is what ``uncovered`` asks. Its own defect is reported by
    # ``undetermined``, and conflating the two would say "nobody wrote a row" about a row.
    covered = {key for key, row in rows.items()
               if row.api_using or row.unresolved_call_sites}
    uncovered = sorted(set(inventory) - covered)
    orphans = sorted(covered - set(inventory))
    undetermined = sorted(key for key, row in rows.items() if row.unresolved_call_sites)
    return CoverageGaps(uncovered, orphans, *projection_gaps(surfaces),
                        undetermined=undetermined)


def unmapped_endpoints(inventory=None):
    """``[(surface, operation, endpoint)]`` for every reached endpoint with no table row.

    The third direction, and the one that catches a *changed* endpoint family rather than a
    new operation: move a call onto an endpoint the table does not know and its requirement
    would silently project as empty. This makes that a failure instead.
    """
    inventory = dict(operation_inventory()) if inventory is None else dict(inventory)
    modes = {sid: surface["mode"] for sid, surface in _capabilities()["surfaces"].items()}
    out = []
    for (surface_id, op_name), endpoints in sorted(inventory.items()):
        mode = modes.get(surface_id, "read")
        for endpoint in endpoints:
            if _table_row(endpoint, mode) is None:
                out.append((surface_id, op_name, endpoint))
    return out


#: ``{token}`` and ``:token`` are one path parameter in two spellings — the SDK's own ``uri``
#: uses the colon form, prose and docstrings often use the brace form. Normalised before any
#: comparison, so the scan cannot report this library's own documentation as a call site.
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")


def _normalised(endpoint: str) -> str:
    return _PLACEHOLDER_RE.sub(r":\1", endpoint)


def _package_modules():
    """Every module of this package, imported. Lazy for the same reason
    :func:`_capabilities` is: the import graph runs the other way at module load."""
    import importlib
    import pkgutil

    import larkdocio

    modules = [larkdocio]
    for found in pkgutil.walk_packages(larkdocio.__path__, "larkdocio."):
        try:
            modules.append(importlib.import_module(found.name))
        except Exception:  # pragma: no cover - a module that cannot import is not a call site
            continue
    return modules


@functools.lru_cache(maxsize=1)
def shipped_call_sites() -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    """``(dotted path, endpoints)`` for every PUBLIC callable this package ships **that reaches
    at least one Lark endpoint** — a callable that reaches none is not a call site.

    **Seeded from the CODE, not from the declaration** — which is the whole point. Every other
    completeness check in this module starts at ``capabilities()``: an operation, a leg, or a
    lifecycle call. All of them are therefore blind in exactly the same place — a public method
    that reaches Lark and is declared *nowhere* is missing from the inventory AND from the rows,
    so the bidirectional check compares two copies of the same omission and passes. That is not
    hypothetical: ``DriveFilesWriteClient.delete`` shipped, was exercised by the live round trip,
    and had no permission row for two releases while this suite stayed green (LD-442).

    The walk is module-level functions plus the public methods of public classes, each run
    through the SAME :func:`endpoints_of` derivation the registry uses, so the two cannot
    disagree about what a callable reaches. **Where the scan stops** (stated rather than
    implied): private callables, nested functions, and anything reached only through a name this
    package does not bind — the derivation's own limits, unchanged here.
    """
    seen: Dict[str, Tuple[str, ...]] = {}

    def consider(path, fn):
        if path in seen:
            return
        seen[path] = endpoints_of(fn)

    for module in _package_modules():
        name = getattr(module, "__name__", "")
        for attr, obj in vars(module).items():
            if attr.startswith("_"):
                continue
            if inspect.isfunction(obj) and getattr(obj, "__module__", None) == name:
                consider(f"{name}.{attr}", obj)
            elif inspect.isclass(obj) and getattr(obj, "__module__", None) == name:
                for method_name, method in vars(obj).items():
                    if method_name.startswith("_") or not inspect.isfunction(method):
                        continue
                    consider(f"{name}.{attr}.{method_name}", method)
    return tuple(sorted((path, eps) for path, eps in seen.items() if eps))


def undeclared_endpoints(sites=None, rows=None) -> List[Tuple[str, str]]:
    """THE FOURTH DIRECTION — ``[(dotted path, endpoint)]`` for every endpoint a shipped public
    callable can reach that **no permission row carries**.

    A requirement is authored per *call site*; a call site nobody declared has no row, and the
    three declaration-seeded checks above cannot see it. This one can. It says nothing about
    whether the endpoint has a scope-table row — the table is keyed by prefix, so a new call on
    an existing family resolves there and looks answered; what is missing is the row that tells
    a caller *this operation* needs it.
    """
    rows = permission_registry() if rows is None else rows
    carried = {_normalised(endpoint) for row in rows.values() for endpoint in row.endpoints}
    sites = shipped_call_sites() if sites is None else sites
    return [(path, endpoint)
            for path, endpoints in sites
            for endpoint in endpoints
            if _normalised(endpoint) not in carried]


def surface_scope_projection(surface_id: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """A surface's ``(scopes, optional_scopes)`` recomputed from its rows — the guard's half
    of the unification, so the two can never be asserted differently."""
    caps = _capabilities()["surfaces"]
    surface = caps[surface_id]
    rows = [row for key, row in permission_registry().items() if key[0] == surface_id]
    blocks = [
        Permissions(
            endpoints=row.endpoints, credential_app=row.credential_app,
            credentials_env=row.credentials_env, scopes=row.scopes,
            optional_scopes=row.optional_scopes,
        )
        for row in rows
    ]
    composed: List[str] = []
    for other in surface.get("composes", ()):
        composed.extend(caps[other]["credentials"]["scopes"])
    return surface_projection(blocks, composed)


# --------------------------------------------------------------------------- #
# THE DOCUMENT PROJECTIONS — the registry writes the documents, never the       #
# reverse. Both regions are byte-checked against these renders, so a scope      #
# string cannot be edited into a document and disagree with the code.           #
# --------------------------------------------------------------------------- #

#: The fence that delimits the generated region in the maintainer's matrix.
DEV_REGION_BEGIN = "<!-- BEGIN PERMISSIONS-MATRIX (generated -->"
DEV_REGION_END = "<!-- END PERMISSIONS-MATRIX -->"

#: The fence that delimits the generated region in the shipped consumer guide.
CONSUMER_REGION_BEGIN = "<!-- BEGIN PERMISSIONS (generated -->"
CONSUMER_REGION_END = "<!-- END PERMISSIONS -->"

#: The one-liner that regenerates a region, quoted into the region's own header so the
#: instruction cannot drift away from the thing it regenerates.
DEV_REGENERATE = (
    'python -c "from larkdocio.permissions import dev_permissions_markdown as m; '
    'print(m())"'
)
CONSUMER_REGENERATE = (
    'python -c "from larkdocio.permissions import consumer_permissions_markdown as m; '
    'print(m())"'
)


def region_of(text: str, begin: str, end: str) -> str:
    """The generated region of a document, fences included, or ``""`` when absent."""
    start = text.find(begin)
    stop = text.find(end)
    if start == -1 or stop == -1 or stop < start:
        return ""
    return text[start:stop + len(end)]


def _cell(value) -> str:
    """One table cell: a list becomes backticked items, empty becomes an em dash."""
    if isinstance(value, (list, tuple)):
        return " · ".join(f"`{item}`" for item in value) if value else "—"
    return str(value) if value else "—"


def dev_permissions_markdown() -> str:
    """The MAINTAINER-side per-operation matrix, generated from the registry.

    Every API-using call site in the library, its derived endpoints, the credential pair it
    is made on, and the exact scopes it needs — plus the endpoint→scope table with each row's
    evidence, the captured denial bodies, and an explicit list of the requirements that are
    genuinely not known. Nothing here is hand-written prose about a function's permissions:
    there is one source, and this is its projection.
    """
    rows = permission_registry()
    lines = [
        DEV_REGION_BEGIN.replace(" -->", ""),
        f"     regenerate with:  {DEV_REGENERATE}  -->",
        "",
        "### Every call site and what it needs",
        "",
        "| Surface | Call site | Kind | Credential pair | Endpoints reached (derived) "
        "| Scopes required | Degrades without | Basis |",
        "|---------|-----------|------|-----------------|------------------------------"
        "|-----------------|------------------|-------|",
    ]
    for (surface_id, name), row in sorted(rows.items()):
        if not row.api_using:
            continue
        lines.append(
            f"| `{surface_id}` | `{name}` | {row.kind} | {_cell(row.credentials_env)} "
            f"| {_cell(row.endpoints)} | {_cell([s.scope for s in row.scopes])} "
            f"| {_cell([s.scope for s in row.optional_scopes])} | {row.basis} |"
        )
    # TWO lists, because they are two different answers (LD-609). A row that derived no
    # endpoint AND resolved every seam it met genuinely needs no permission. A row whose
    # derivation stopped early does not know what it needs — and it used to be printed in
    # the same sentence as the first kind, under a header that called it needing nothing.
    quiet = sorted((surface_id, name) for (surface_id, name), row in rows.items()
                   if not row.api_using and not row.unresolved_call_sites)
    short = sorted((surface_id, name) for (surface_id, name), row in rows.items()
                   if row.unresolved_call_sites)
    lines += [
        "",
        f"**Makes no Lark call, so needs no permission ({len(quiet)}):** "
        + ", ".join(f"`{surface_id}`.`{name}`" for surface_id, name in quiet) + ".",
        "",
        "**Call sites whose derivation could not be completed "
        f"({len(short)}):** the endpoints and scopes above are what the derivation could "
        "resolve, and these call sites carry a seam it could not — so their requirement may "
        "be SHORT and is not a claim that they need nothing. Each one's own "
        "`unresolved_call_sites` in `capabilities(full=True)` names the seam and its site."
        + (" " + ", ".join(f"`{surface_id}`.`{name}`" for surface_id, name in short) + "."
           if short else " None today."),
        "",
        "### The endpoint → scope table, with the evidence for each row",
        "",
        "| Endpoint prefix | Credential pair | Scope | Verification | Field-level | "
        "Degrades | Evidence |",
        "|-----------------|-----------------|-------|--------------|-------------|"
        "----------|----------|",
    ]
    for prefix, mode, scopes, note in ENDPOINT_SCOPES:
        if not scopes:
            continue
        for scope in scopes:
            lines.append(
                f"| `{prefix}` | {mode} | `{scope.scope}` | {scope.verification} "
                f"| {'yes' if scope.field_level else 'no'} "
                f"| {'yes' if scope.degrades else 'no'} | {scope.evidence} |"
            )
    lines += [
        "",
        "### Requirements that are genuinely NOT known",
        "",
        "An empty requirement is not a claim that a call needs nothing — it is a recorded "
        "unknown. Each row below says why, and none of them guesses a scope string.",
        "",
        "| Endpoint prefix | Credential pair | Why the requirement is empty |",
        "|-----------------|-----------------|------------------------------|",
    ]
    for prefix, mode, scopes, note in ENDPOINT_SCOPES:
        if scopes or not note:
            continue
        lines.append(f"| `{prefix}` | {mode} | {note} |")
    lines += [
        "",
        "### Scope denials Lark actually returned, captured verbatim",
        "",
        "A denial body is the strongest evidence there is: it names the exact scope string "
        "and hands back a console link. Several of these are required by no shipped call "
        "site — they are kept because a denial that reaches a caller still has to be "
        "legible.",
        "",
        "| Scope | Code | Needed by a shipped call site | Capture |",
        "|-------|------|-------------------------------|---------|",
    ]
    for denial in OBSERVED_DENIALS:
        needed = "yes" if denial.required_by_a_shipped_operation else "no"
        lines.append(
            f"| `{denial.scope}` | `{denial.code}` | {needed} | {denial.capture} |")
    lines += ["", DEV_REGION_END]
    return "\n".join(lines)


def _scope_objects_by_surface(rows) -> Dict[str, Dict[str, List[Scope]]]:
    """``{surface_id: {scope string: [Scope, …]}}`` — the objects behind each surface's ask.

    A surface's ``capabilities()`` answer carries scope **strings**; the verification label and
    the loss note live on the :class:`Scope` objects its operations reference. This joins the
    two so the consumer table can state how firmly a requirement is established without any
    surface asserting a second copy of it. A string can carry more than one object (the reader
    scope is required by the document read and, separately, by the comment family, and the two
    notes say different things), so the value is a list and nothing is collapsed.
    """
    index: Dict[str, Dict[str, List[Scope]]] = {}
    for row in rows.values():
        for key in (row.surface, "*"):
            per_surface = index.setdefault(key, {})
            bucket_for = per_surface.setdefault
            for scope in tuple(row.scopes) + tuple(row.optional_scopes):
                bucket = bucket_for(scope.scope, [])
                if scope not in bucket:
                    bucket.append(scope)
    return index


def _scope_objects(index, surface_id: str, scope_string: str) -> List[Scope]:
    """The ``Scope`` objects behind one (surface, scope) row.

    Falls back to the ``"*"`` bucket — every object the registry carries for that string — for a
    **composed** surface, whose asked-for scopes include those of the surface it composes and so
    are not all reachable from its own rows. Without the fallback such a row would report its
    requirement as unestablished, which is a false unknown rather than an honest one.
    """
    per_surface = index.get(surface_id, {})
    return per_surface.get(scope_string) or index.get("*", {}).get(scope_string, [])


def _established_as(scopes) -> str:
    """The verification label(s) behind one table row — short enough to sit in a cell."""
    labels = sorted({scope.verification for scope in scopes})
    return " / ".join(labels) if labels else "—"


def _loss_glossary(scopes) -> List[str]:
    """The per-scope list: every scope named in the tables, once, with what its absence costs.

    **This is the compaction's whole trick, and its honesty check.** The loss texts are
    per-scope, not per-surface, so putting them in the table cells meant the same 90-word
    paragraph appeared in four rows of one table and five of the next — accurate and
    unreadable. Writing each one **once**
    here, keyed by the scope the row already names, removes the repetition without dropping a
    word of it: the loss text, the verification label, the FIELD-level flag and the
    candidate flag all stay, which is the part that must not be lost in becoming shorter.
    """
    by_scope: Dict[str, List[Scope]] = {}
    for scope in scopes:
        bucket = by_scope.setdefault(scope.scope, [])
        if scope not in bucket:
            bucket.append(scope)
    lines = []
    for scope_string in sorted(by_scope):
        objects = by_scope[scope_string]
        marks = sorted({scope.verification for scope in objects})
        if any(scope.field_level for scope in objects):
            marks.append("a FIELD-level grant")
        if any(not scope.established for scope in objects):
            marks.append("a candidate, never observed demanded")
        lines.append(f"- `{scope_string}` ({' · '.join(marks)}):")
        notes = []
        for scope in objects:
            note = scope.note or "without it the call is denied"
            if note not in notes:
                notes.append(note)
        lines += [f"    - {note}" for note in notes]
    return lines


def consumer_permissions_markdown() -> str:
    """The CONSUMER-side permissions section, generated from the same registry.

    Deliberately NOT the maintainer's list. It covers only what a consumer can actually
    call, says it in their terms, and answers the two questions they actually have: *what
    will fail without this*, and *what do I ask my workspace administrator for*. It carries
    no capture paths and no internal references — those answer a maintainer's question, not
    a caller's.

    **Shaped to be pasted into a request, one row per (surface, scope).** The point of
    generating this table is that nobody has to hand-write the list they send their workspace
    administrator — and a row per *surface* made it hand-written anyway, because it had to
    join several scopes' loss notes into one cell and then repeat the joined paragraph in every
    row that shared a scope. One row per scope makes every cell a label, and the loss texts go
    once each into the per-scope list below the tables. Nothing was dropped to get there; the
    labels the shorter table gained (how firmly each requirement is established, the
    FIELD-level and candidate flags) were not even in the long one.
    """
    caps = _capabilities()["surfaces"]
    rows = permission_registry()
    index = _scope_objects_by_surface(rows)
    named: List[Scope] = []
    lines = [
        CONSUMER_REGION_BEGIN.replace(" -->", ""),
        f"     regenerate with:  {CONSUMER_REGENERATE}  -->",
        "",
        "**What to ask for — one row per surface and scope, so a row is one thing you ask "
        "for.** *Must hold* means the surface does not work without it. *Optional* means the "
        "surface still works and something specific is lost. What each scope costs is written "
        "once, in the per-scope list below the tables, so no cell here carries a paragraph.",
        "",
        "**THIS TABLE ANSWERS THE per-SURFACE QUESTION** — *what does this surface stop doing "
        "without the scope*. The table after it answers the per-OPERATION one — *what must a "
        "grant include for one call to do its whole job* — and they are different questions, "
        "so the same scope can be `optional` here and still be listed there. Neither table "
        "overrides the other; read the one whose question is yours, and read the per-scope "
        f"list under *{_LOSS_LIST_HEADING}* for what any one of them actually costs. In code "
        "the per-operation answer is "
        "`larkdocio.preflight.requirements_for_operations([...])`, and it derives from this "
        "same registry.",
        "",
        "| Surface | Credential pair | Scope | Must hold? | How firmly established |",
        "|---------|-----------------|-------|------------|------------------------|",
    ]
    for surface_id, surface in caps.items():
        creds = surface["credentials"]
        pair = f"{creds['app'].upper()} app · {_cell(creds['env_primary'])}"
        required = [(scope, "must hold") for scope in creds["scopes"]]
        asks = required + [(scope, "optional") for scope in creds["optional_scopes"]]
        if not required:
            # THE ROW IS ABOUT WHAT MUST HOLD, so it is owed by every surface that requires
            # nothing — not only by one that has nothing to ask for at all. A surface whose
            # scopes are all optional used to print two `optional` rows and no statement about
            # requirement, which reads exactly like a table that forgot to mention one.
            lines.append(
                f"| `{surface_id}` | {pair} | — | — | no scope observed demanded |")
        for scope_string, holding in asks:
            objects = _scope_objects(index, surface_id, scope_string)
            named += objects
            lines.append(
                f"| `{surface_id}` | {pair} | `{scope_string}` | {holding} "
                f"| {_established_as(objects)} |")
    lines += [
        "",
        "**Per call, when a surface's answer is not the whole answer — THIS TABLE ANSWERS THE "
        "per-OPERATION QUESTION: what must a grant include for this call to do its whole "
        "job.** Most calls need exactly what their surface needs. These are the ones that need "
        "something extra, and they are the ones worth reading before you plan an integration. A "
        "scope listed `optional` above can appear here too, and that is not the two tables "
        f"disagreeing: {_DEGRADES_DISCRIMINATOR}. **What absence costs is per scope, not "
        "uniform** — for a FIELD-level grant the call even succeeds and the fields it governs "
        f"come back empty — so it is written once each below, under *{_LOSS_LIST_HEADING}*, "
        "and never guessed at here:",
        "",
        "| Call | Needs | How firmly established |",
        "|------|-------|------------------------|",
    ]
    for (surface_id, name), row in sorted(rows.items()):
        extra = [s for s in row.scopes
                 if s.scope not in caps[surface_id]["credentials"]["scopes"]]
        for scope in extra:
            named.append(scope)
            lines.append(
                f"| `{surface_id}` · `{name}` | `{scope.scope}` | {scope.verification} |")
    lines += [
        "",
        f"**{_LOSS_LIST_HEADING} — written once per scope, never repeated.** Read "
        "the entry for any scope a row above named; a scope required for more than one reason "
        "carries one line per reason.",
        "",
    ] + _loss_glossary(named)
    field_level = sorted({
        scope.scope for row in rows.values() for scope in row.scopes if scope.field_level})
    lines += [
        "",
        "**The one that does not look like a permission problem.** "
        + ", ".join(f"`{scope}`" for scope in field_level)
        + " is a FIELD-level grant. Without it the call still succeeds and the fields it "
        "governs come back empty, which reads exactly like *\"there is no such user\"*. If "
        "a name will not resolve and nothing looks like an error, check this one first.",
        "",
        "**Where the requirement is not known, this says so.** A surface listing no "
        "required scope is not a promise that none is needed — it means no scope string has "
        "ever been observed demanded for those calls, and none is guessed here. Read "
        "`larkdocio.capabilities(full=True)` for the per-call detail: each operation's "
        "`permissions`, and the top-level `unknown_requirements`, which gives that caveat's "
        "reason per endpoint.",
        "",
        "**When a call IS denied, you are told exactly what is missing.** The denial record "
        "is on `err.denial`, and it carries the exact missing scope(s), Lark's verbatim "
        "`code`/`msg`, the console link when Lark supplies one, which credential pair the "
        "call used, and the fallback that still works where there is one. `denial.detail()` "
        "is one paragraph you can relay as-is. **Test it with `err.denial is not None`, not "
        "with the class** — that check means the same thing on every surface. Most surfaces "
        "raise `LarkPermissionError` (a `LarkAPIError` subclass, so code that already catches "
        "API errors keeps working); a leg with an error family of its own raises its own type "
        "and carries the same record — an attachment upload raises `MediaUploadError`, a "
        "Drive file upload `DriveFileUploadError`, a chunked upload "
        "`DriveFileChunkedUploadError` with the `upload_id` it left behind. Those legs tell "
        "you WHICH leg failed and WHY; taking the family away to answer the second question "
        "would have cost you the first. **A denial is never "
        "reported as an absent thing** — including the case that does not look like a "
        "permission problem at all, where the call succeeds and the fields a field-level "
        "grant governs come back empty.",
        "",
        "**And you can ask before you start — advisory, optional, and honest about it.** "
        "`larkdocio.preflight.check_permissions(for_operations=[...])` derives what those "
        "operations need and, for the scopes a read can actually decide, checks them with one "
        "harmless call each against a deliberately nonexistent target — so nothing of yours is "
        "read, altered or created. `larkdocio.preflight.call_cost([...])` tells you how many "
        "calls that will be **before** you spend them. Every answer states HOW it knows "
        "(`probed`, `derived`, or `unknown`), and the result names its own blind spots: **a "
        "write scope cannot be proved by any read, and a field-level grant is invisible to "
        "this check** — which is exactly why it is advisory. It is never required: nothing in "
        "the library calls it, and skipping it changes nothing about how a real denial is "
        "reported.",
        "",
        "**Read `result.ok` together with `result.blind_spots` — the boolean on its own is "
        "not an answer.** `ok` says one thing only: no probe *found* a scope missing. Where "
        "nobody has ever observed what an operation requires, the check now says so as a "
        "blind spot naming that operation, and `result.requirements` states for every "
        "operation you asked about which kind of answer you got — `known`, `unmeasured` (it "
        "calls Lark and no scope string has ever been seen demanded), `no-api-call` (it "
        "reaches Lark not at all, so it needs nothing), or `unrecognised`. Ask about "
        "**operations**, not surfaces: `check_permissions(['docx-read'])` refuses with a "
        "`LarkConfigError` naming that surface's operations, rather than answering an empty "
        "result. The whole answer is JSON — `json.dumps(result.to_dict())`.",
        "",
        f"**{NEVER_WIDENS}** When a call is denied, what you get back carries Lark's own "
        "code and message — which name the missing scope — so the console link in it is the "
        "fix.",
        "",
        CONSUMER_REGION_END,
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# THE UNIFORM PERMISSION REFUSAL — one shape, every surface.                    #
#                                                                              #
# Lark's own denial body already carries the answer: the exact scope string in   #
# `permission_violations[].subject` AND in the message text, plus a console deep  #
# link in `helps[].url`. This turns that into one typed object so a denial can    #
# never again reach a caller wearing the costume of an absence.                   #
# --------------------------------------------------------------------------- #

#: The codes THIS surface classifies as a scope denial, in the order it has always listed them.
#: A per-surface classification — the object-ACL denials are **deliberately not here**.
SCOPE_DENIAL_CODES: Tuple[int, ...] = (99991672, 41050, 1069303)


#: Lark response codes that mean *"you do not hold the scope"*, with the evidence for each.
#:
#: Classification is deliberately **not** code-only: :func:`looks_like_scope_denial` also reads
#: the message shape, so a denial code we have never captured still classifies rather than
#: falling through as an ordinary failure. Codes named in our own documents but never seen on
#: the wire say so, instead of passing as observed.
#:
#: **The three rows' TEXT moved one level up (LD-531); the classification did not.** Each code's
#: ``verification`` and ``evidence`` are authored once, for the whole library, in
#: ``larkdocio.common.error_codes`` — and the ``denial-verified`` vs ``documented-unverified``
#: distinction travelled **byte-identically**, because it is a measurement and not a label. What
#: stays here is *which* codes this surface treats as a scope denial
#: (:data:`SCOPE_DENIAL_CODES`), which is this registry's own question and nobody else's: an
#: **object-ACL** denial — the application holds the scope and is simply not on the object's
#: access list — has a different fix and is a different class, so it is not in this set. That is
#: the whole reason the two are typed apart rather than forced into one shape.
#:
#: The lookup is imported **inside** the projection, not at module scope, because this module is
#: a leaf that nearly everything else imports (``larkdocio.errors.api_error`` says so where it
#: does the same thing) and tightening its load order buys nothing.
def _denial_rows() -> Dict[int, dict]:
    from larkdocio.common.error_codes import ERROR_CODES

    return {code: {"verification": ERROR_CODES[code].verification,
                   "evidence": ERROR_CODES[code].evidence}
            for code in SCOPE_DENIAL_CODES}


DENIAL_CODES = _denial_rows()

#: The message shapes Lark uses for a scope denial. Checked alongside the code so an
#: uncaptured denial code still classifies correctly.
_DENIAL_MSG_MARKERS = ("scopes is required", "scope is required", "access denied",
                       "permission denied", "no permission")

#: Matches the scope list Lark puts in the message text: ``… is required: [a:b, c:d]``.
_MSG_SCOPES_RE = re.compile(r"\[([a-z0-9_.:,\s\-]+)\]")


@dataclass(frozen=True)
class PermissionDenial:
    """A scope denial, in ONE shape, whatever surface it happened on.

    The fields exist because each one is something a caller had to guess before:

    * ``scopes`` — the **exact** missing permission(s), as Lark spells them;
    * ``code`` / ``msg`` — Lark's own answer, **verbatim**, never paraphrased;
    * ``console_url`` — the deep link Lark hands back, **when the body carries one**. Nothing
      is ever synthesized: a link we did not receive is simply not claimed;
    * ``credential_env`` — *which credential pair* made the call, so a caller with a read app
      and a write app knows which one to fix;
    * ``fallback`` — what still works without the scope, where anything does;
    * ``reported_success`` — ``True`` for the case that does not look like a permission problem
      at all: the call **succeeded** and the fields a field-level grant governs came back
      empty. Recorded rather than smoothed over, because reading that as an absence is the
      failure this whole shape exists to prevent.
    """

    scopes: Tuple[str, ...]
    code: object
    msg: str
    console_url: Optional[str] = None
    credential_env: Tuple[str, ...] = ()
    fallback: Optional[str] = None
    reported_success: bool = False

    def detail(self) -> str:
        """One actionable paragraph — the string a caller may relay verbatim.

        Assembled from what is actually present. A field we do not have contributes no clause
        at all, so the detail never carries a placeholder standing in for evidence.
        """
        parts = []
        if self.reported_success:
            parts.append(
                "Lark reported SUCCESS and the fields this grant governs came back empty, "
                "which is not the same as the data being absent. Missing permission(s): "
                + ", ".join(self.scopes) + "."
            )
        else:
            parts.append("Missing permission(s): " + ", ".join(self.scopes) + ".")
        parts.append(f"Lark said: code {self.code}, {self.msg}")
        if self.credential_env:
            parts.append("The call used the credential pair " + " / ".join(self.credential_env)
                         + ".")
        if self.console_url:
            parts.append("Grant it in the Lark console: " + self.console_url)
        else:
            parts.append(
                "Lark returned no console link for this one; grant the permission(s) above on "
                "the app in the Lark console.")
        if self.fallback:
            parts.append("Meanwhile this still works: " + self.fallback)
        parts.append(
            "A scope is granted by a workspace administrator in the Lark console; this "
            "library never requests one.")
        return " ".join(parts)

    def to_dict(self) -> dict:
        d = {
            "scopes": list(self.scopes),
            "code": self.code,
            "msg": self.msg,
            "credential_env": list(self.credential_env),
            "reported_success": self.reported_success,
            "detail": self.detail(),
        }
        if self.console_url is not None:
            d["console_url"] = self.console_url
        if self.fallback is not None:
            d["fallback"] = self.fallback
        return d


def looks_like_scope_denial(code, msg) -> bool:
    """Whether a Lark ``code``/``msg`` pair is a scope denial.

    Code **or** message shape: the captured denial code is the strong signal, and the message
    markers catch a denial code we have never seen, so an uncaptured one is not silently
    demoted to an ordinary failure.
    """
    try:
        numeric = int(str(code))
    except (TypeError, ValueError):
        numeric = None
    if numeric in DENIAL_CODES:
        return True
    lowered = (msg or "").lower()
    return any(marker in lowered for marker in _DENIAL_MSG_MARKERS)


def _scopes_from_body(body) -> Tuple[str, ...]:
    """The scopes named in a denial body's structured ``permission_violations``.

    Tolerates a plain ``dict`` (the raw-HTTP surfaces) and an SDK response object (attribute
    access), because the two transports hand back different things and the refusal shape must
    not depend on which one was used.
    """
    error = _get(body, "error")
    violations = _get(error, "permission_violations") or []
    out = []
    for violation in violations:
        subject = _get(violation, "subject")
        if subject and subject not in out:
            out.append(subject)
    return tuple(out)


def _console_url_from_body(body) -> Optional[str]:
    """The console deep link Lark supplied, or ``None``. Never synthesized."""
    error = _get(body, "error")
    for help_entry in (_get(error, "helps") or []):
        url = _get(help_entry, "url")
        if url:
            return url
    return None


def _get(obj, key):
    """``obj[key]`` for a mapping, ``obj.key`` for an object, ``None`` otherwise."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _scopes_from_msg(msg) -> Tuple[str, ...]:
    """The scopes named in the message text — the half that survives the SDK path, which
    hands back ``code``/``msg`` and no structured body."""
    match = _MSG_SCOPES_RE.search(msg or "")
    if not match:
        return ()
    out = []
    for piece in match.group(1).split(","):
        candidate = piece.strip()
        if ":" in candidate and candidate not in out:
            out.append(candidate)
    return tuple(out)


def _fallback_for(scopes) -> Optional[str]:
    """What still works without these scopes, drawn from the registry's own notes.

    Only a **degrading** scope has a fallback; claiming one for a scope that has none would
    send a caller down a path that cannot work, so this returns ``None`` in that case.
    """
    known = {}
    for _prefix, _mode, table_scopes, _note in ENDPOINT_SCOPES:
        for scope in table_scopes:
            known[scope.scope] = scope
    hints = []
    for name in scopes:
        scope = known.get(name)
        if scope is None or not scope.degrades:
            continue
        if scope.scope.startswith("contact:"):
            hint = ("everything except display-name resolution — a document still reads "
                    "completely, with each mention left as its raw open id")
        elif scope.scope == "drive:export":
            hint = ("everything except whole-cell style and number formats — a spreadsheet "
                    "still reads at values level")
        else:  # pragma: no cover - every degrading scope today has a stated fallback
            hint = None
        if hint and hint not in hints:
            hints.append(hint)
    return "; ".join(hints) if hints else None


def denial_from(code, msg, body=None, credential_env=()) -> Optional[PermissionDenial]:
    """A :class:`PermissionDenial` for a Lark answer, or ``None`` if it is not a scope denial.

    Returning ``None`` for an ordinary failure is as important as building the object for a
    denial: a resource that genuinely is not there must keep reporting itself as absent, or the
    distinction this shape exists to draw is lost in the other direction.
    """
    if not looks_like_scope_denial(code, msg):
        return None
    scopes = _scopes_from_body(body) or _scopes_from_msg(msg)
    if not scopes:
        return None
    return PermissionDenial(
        scopes=scopes,
        code=code,
        msg=msg or "",
        console_url=_console_url_from_body(body),
        credential_env=tuple(credential_env),
        fallback=_fallback_for(scopes),
    )


#: The scopes whose absence lets a call SUCCEED with the fields they govern emptied. Read off
#: the registry rather than named here, so the field-level set cannot drift from the table.
def field_level_scopes() -> Tuple[str, ...]:
    """Every field-level grant the registry knows — the ones whose absence is invisible."""
    return tuple(scope.scope
                 for _p, _m, scopes, _n in ENDPOINT_SCOPES
                 for scope in scopes if scope.field_level)


def suspected_field_level_gap(body, requested_ids, credential_env=()) -> \
        Optional[PermissionDenial]:
    """The case that does not look like a permission problem: **success with empty fields**.

    Lark answered ``code`` 0 and returned an entry for every id asked about, yet **every**
    governed field is empty. That is the shape a missing field-level grant produces, and
    reading it as *"there is no such user"* is the specific mistake that cost five days.

    Deliberately conservative, because crying wolf on the ordinary case would be its own bug:
    a **partial** answer (some names present, or fewer entries than ids requested) is an
    ordinary absence — an id outside the app's contacts range, or a bot — and is **not**
    flagged. Only *answered-for-everything and empty for everything* is.
    """
    code = _get(body, "code")
    if code not in (0, "0"):
        return None
    items = _get(_get(body, "data"), "items")
    if not items or not requested_ids:
        return None
    if len(items) != len(requested_ids):
        return None  # a partial answer is an ordinary absence, not a scope signal
    if any((_get(item, "name") or "").strip() for item in items):
        return None  # something resolved, so the grant is held
    scopes = field_level_scopes()
    if not scopes:  # pragma: no cover - the registry always knows at least one today
        return None
    return PermissionDenial(
        scopes=scopes,
        code=code,
        msg=str(_get(body, "msg") or "success"),
        credential_env=tuple(credential_env),
        fallback=_fallback_for(scopes),
        reported_success=True,
    )


# --------------------------------------------------------------------------- #
# AC4 — coverage, DERIVED from the registry: no surface may build a Lark-code   #
# error outside the shared factory, or its denials would not carry the shape.   #
# --------------------------------------------------------------------------- #


#: The "line number" an unreadable module is reported at. A file that does not parse is an
#: offender — a check that cannot read a source must not answer "no offenders" — and it needs a
#: site to be reported at, so it gets one no real line can be confused with.
UNPARSEABLE_SOURCE = 0


def api_error_class_names() -> FrozenSet[str]:
    """Every class name that **is** a :class:`~larkdocio.errors.LarkAPIError` — the class
    GRAPH, walked, not the one literal name.

    The subclasses are what the detector below used to be blind to. They are found by walking
    ``__subclasses__`` transitively **after** importing every denial-owning module, because a
    subclass exists on the graph only once its own module has been imported — and those
    modules are exactly the ones the detector reads.

    Names, not classes, because the detector's input is **source text**: a guard proven red on
    a synthetic ``{"larkdocio.made_up": "..."}`` source has no module to import, and a check
    that could only answer for importable modules would not be the check that bites.
    """
    from larkdocio.errors import LarkAPIError
    import importlib

    for name in denial_owning_modules():
        importlib.import_module(name)
    names, seen, stack = set(), set(), [LarkAPIError]
    while stack:
        cls = stack.pop()
        if cls in seen:  # a name is not the identity — two classes may share one
            continue
        seen.add(cls)
        names.add(cls.__name__)
        stack.extend(cls.__subclasses__())
    return frozenset(names)


def lark_code_error_constructions(source: str) -> Tuple[int, ...]:
    """The line numbers where ``source`` hands a Lark ``code`` to an api-error CLASS instead
    of to the factory — the shape that ships a non-uniform denial.

    Sites, not a yes/no, so the population is **derivable** rather than adopted: the guard can
    name where to look, and the enumeration is a command anyone can re-run
    (:func:`nonconforming_denial_sites`) instead of a number in a document.

    **An AST walk, not a regex — and for the second time in this module.** LD-200 shipped this
    as ``raise\\s+LarkAPIError\\s*\\([^)]*\\bcode\\s*=``, which had two independent false
    negatives, either of which alone made the check answer ``[]`` over the whole library:

    * **the literal name.** ``LarkAPIError`` has subclasses, in this module's own denial-owning
      set — ``MediaUploadError``, ``DriveFileChunkedUploadError``,
      ``LarkSpreadsheetUnreadableError`` and the rest — and a code-carrying raise of any of them
      bypasses the factory exactly as the base name would. The pattern could not see one;
      :func:`api_error_class_names` walks the graph instead of naming a class.
    * **the nesting window.** ``[^)]*`` cannot cross a nested ``)``, so
      ``LarkAPIError(f"...{helper(x)}...", code=code)`` stopped matching and passed silently —
      the SAME defect LD-210 AC9 found and fixed in :func:`_omits_the_credential_pair`, in this
      file, leaving its twin thirty lines above untouched. Argument nesting is irrelevant to a
      walk, at any depth, which is the whole point.

    **A construction, not only a ``raise``.** The rule this enforces is *build* — a surface that
    assembles the exception in a helper and raises the return value (``raise _all_skipped(...)``)
    bypasses the factory just as squarely, and a raise-only check would call that conforming.

    Code-carrying means a ``code=`` keyword, a ``**kwargs`` forward (which *may* carry one and
    cannot be shown not to), or more than one positional argument (the message is the only
    positional the family takes). The ``**`` case is deliberately the OPPOSITE conservatism from
    :func:`_omits_the_credential_pair`, which declines to accuse a forward: there, the obligation
    is re-proven at the caller, and here nothing downstream re-proves it, so an indeterminate
    forward is reported rather than waved through.

    Source that does not parse is reported as an offender — as line :data:`UNPARSEABLE_SOURCE`,
    a line no file has — for the same reason as its twin: a check that cannot read a file must
    not answer "no offenders".
    """
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return (UNPARSEABLE_SOURCE,)
    classes = api_error_class_names()
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _called_name(node.func) not in classes:
            continue
        if len(node.args) > 1 or any(
            keyword.arg == "code" or keyword.arg is None for keyword in node.keywords
        ):
            sites.append(node.lineno)
    return tuple(sorted(sites))


#: **THE LABELLED EXCEPTION — where this guard's reach stops, and why each site outside it is
#: cleared.** The guard's module set is DERIVED (:func:`denial_owning_modules`, read off the
#: registry's ``projected_from``), which is its strength: a new API-using operation brings its
#: module under the check with nobody adding it to a list. It is also its limit — a module that
#: builds a Lark-code error while owning no registry-projected call site is invisible to it, and
#: the invariant sentence in :func:`larkdocio.errors.api_error` reaches further than that.
#:
#: The limit is written down rather than left implicit, and it is CHECKED: every module below is
#: a **cleared** exception with its reason, and
#: :func:`constructions_outside_the_guards_reach` reddens when a module appears that is not
#: named here. So the narrowing is visible to a reader and to the suite, and a NEW out-of-reach
#: construction has to be triaged instead of arriving silently — which is the whole failure
#: mode this issue was about.
#:
#: Keyed by module, never by line: a line number is wrong the moment anything above it is edited.
CLEARED_OUTSIDE_THE_GUARDS_REACH = {
    # The key names the CORE module, not `larkdocio.errors`, because the taxonomy is authored
    # there and the re-export at `larkdocio.errors` constructs nothing: this walk reads the
    # shipped tree by PATH, so the key follows the FILE and not the import path. (The relocation
    # was LD-648; the id lives in this `#` comment and not in the string below, because the
    # value IS shipped text and the dialect guard over `emitted_literals()` forbids an issue id
    # there — an id resolves to nothing for somebody holding only the wheel.)
    "larkdocio.common.errors":
        "the factory itself — `api_error` and `api_error_as` ARE the classification seam, so "
        "their own constructions are the conforming path by definition. Keyed on the module "
        "that AUTHORS the taxonomy; the re-export a caller imports it from constructs nothing.",
    "larkdocio.common.transport":
        "two sites, both cleared: the rate-limit raise after the retries are spent (the class "
        "was already chosen by `errors._is_rate_limit_code`, and the rate-limit code is never a "
        "scope denial), and a success answer missing its token, which carries no non-zero code.",
    "larkdocio.write.apply":
        "the block-naming RE-RAISE, which relocates an error already classified once and now "
        "carries `denial` through both of its arms. It classifies nothing itself.",
    "larkdocio.base.errors":
        "the `TableCreatedViewNotNamed` builder — a WRAPPER around a cause classified at the "
        "call seam, forwarding `code`/`msg`/`denial` rather than re-deriving them.",
    "larkdocio.drive.errors":
        "`folder_refused` / `drive_not_found`: LOCAL refusals quoting a MEASURED code constant, "
        "not a code Lark returned on this call, so there is no answer to classify.",
    "larkdocio.drive.versions":
        "the `obj_type` and `name` gates: local, pre-call refusals quoting measured codes in "
        "Lark's own words. No call was made, so no denial can exist.",
}


def constructions_outside_the_guards_reach() -> Dict[str, Tuple[int, ...]]:
    """``{module: (line, …)}`` for code-carrying constructions the guard's module set misses.

    The **disclosure** half of :func:`nonconforming_denial_sites`, not a widening of it: the
    detector is unchanged and its module set is still derived from the registry. This walks the
    shipped package instead, so the gap between what the guard checks and what the invariant
    sentence claims is a measured, named set rather than a silence.

    Every module it can return is expected to be in :data:`CLEARED_OUTSIDE_THE_GUARDS_REACH`
    with a reason; the suite holds the two together.
    """
    import pathlib

    package = pathlib.Path(__file__).resolve().parent
    owned = set(denial_owning_modules())
    out: Dict[str, Tuple[int, ...]] = {}
    for path in sorted(package.rglob("*.py")):
        module = "larkdocio." + ".".join(path.relative_to(package).with_suffix("").parts)
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        if module in owned:
            continue
        try:
            sites = lark_code_error_constructions(pathlib_read(path))
        # An unreadable file is skipped; a file that will not DECODE is not. ``pathlib_read``
        # pins UTF-8 and ``UnicodeDecodeError`` is a ``ValueError``, so it flies past this
        # handler rather than turning a broken read into an empty answer (LD-660).
        except OSError:  # pragma: no cover - unreadable source
            continue
        if sites:
            out[module] = sites
    return out


def denial_owning_modules() -> Tuple[str, ...]:
    """The modules that own an API-using call site — **derived** from the registry.

    Read off each operation's ``projected_from``, so a new API-using operation brings its
    module into this set with nobody adding it to a list.
    """
    modules = set()
    for surface in _capabilities()["surfaces"].values():
        for _kind, op in _surface_call_sites(surface):
            if not op["permissions"]["endpoints"]:
                continue
            projected = op["projected_from"]
            # `projected_from` names either a module or a dotted class/table path inside one;
            # walk back to the importable module either way.
            parts = projected.split(".")
            while parts:
                candidate = ".".join(parts)
                try:
                    import importlib

                    importlib.import_module(candidate)
                except ImportError:
                    parts.pop()
                    continue
                modules.add(candidate)
                break
    return tuple(sorted(modules))


def denial_owning_sources() -> Dict[str, str]:
    """``{module name: its source text}`` for every denial-owning module.

    The read-from-disk step both source-level guards on this module share, authored once so the
    two cannot come to disagree about which files they are reading.
    """
    import importlib

    sources: Dict[str, str] = {}
    for name in denial_owning_modules():
        module = importlib.import_module(name)
        path = getattr(module, "__file__", None)
        if not path:  # pragma: no cover - namespace package
            continue
        try:
            sources[name] = pathlib_read(path)
        # Same as above: OSError skips, UnicodeDecodeError propagates (LD-660).
        except OSError:  # pragma: no cover - unreadable source
            continue
    return sources


def nonconforming_denial_sites(sources=None) -> Dict[str, Tuple[int, ...]]:
    """``{module: (line, ...)}`` for every module that builds a Lark-code error directly.

    **The enumeration, not the count.** A population stated as a number is a claim nobody can
    re-derive; this is the command that derives it, and the number is whatever it reports today.

    ``sources`` overrides the read-from-disk step (``{module_name: source}``), which is how the
    guard is proven to bite on a non-conforming path without adding one to the library.
    """
    sources = denial_owning_sources() if sources is None else sources
    found = {name: lark_code_error_constructions(source)
             for name, source in sources.items()}
    return {name: sites for name, sites in sorted(found.items()) if sites}


def nonconforming_denial_modules(sources=None) -> List[str]:
    """Modules owning an API-using call site that build a Lark-code error directly.

    The module-level view of :func:`nonconforming_denial_sites`, kept because the guard's
    question is *"is any module non-conforming"* and its answer reads as a list of names.
    """
    return sorted(nonconforming_denial_sites(sources))


def pathlib_read(path) -> str:
    """Read a source file. Split out so the coverage check has one I/O seam.

    **The encoding is pinned to UTF-8, not inherited from the host locale.** These sources are
    UTF-8 bytes on disk; ``read_text()`` with no ``encoding=`` decodes with
    :func:`locale.getencoding`, so on a cp1252/cp932 host the same file either raises
    ``UnicodeDecodeError`` or — worse — decodes to mojibake that the AST/regex scanners then
    read as if it were the source. Pinning the encoding makes this seam's answer the same on
    every host.

    A genuine decode failure is **not** swallowed anywhere: the two call sites catch ``OSError``,
    and ``UnicodeDecodeError`` is a ``ValueError``, so it propagates as a loud failure instead of
    presenting as "no sites found" — which is what a silent green would look like. Both halves
    are held by a guard in the source repository (``tests/test_host_assumptions.py``, LD-660).
    """
    import pathlib

    return pathlib.Path(path).read_text(encoding="utf-8")

def unreached_table_rows(inventory=None):
    """``[(prefix, mode)]`` for every :data:`ENDPOINT_SCOPES` row no call site reaches.

    The **other direction** of the table's bidirectionality, which the coverage guard did not
    cover: :func:`unmapped_endpoints` catches an endpoint with no row, and this catches a row
    with no endpoint. A row that outlives the call site it was written for is a requirement
    nobody can act on and a maintenance cost nobody can retire — the same reasoning that makes
    a phantom matrix row a failure everywhere else in this project.
    """
    inventory = dict(operation_inventory()) if inventory is None else dict(inventory)
    modes = {sid: surface["mode"] for sid, surface in _capabilities()["surfaces"].items()}
    reached = set()
    for (surface_id, _op), endpoints in inventory.items():
        mode = modes.get(surface_id, "read")
        for endpoint in endpoints:
            row = _table_row(endpoint, mode)
            if row is not None:
                reached.add((row[0], row[1]))
    return sorted((prefix, mode) for prefix, mode, _s, _n in ENDPOINT_SCOPES
                  if (prefix, mode) not in reached)


#: The factories a Lark ``code`` is raised or forwarded through. A call to any of them owes the
#: credential pair; nothing else on the module is this check's business. ``api_error_as``
#: (LD-644) is the class-preserving door and owes it for the same reason as the other two — a
#: denial has to say WHICH app to fix, and only the call site knows.
_CREDENTIAL_OBLIGED_CALLS = ("raise_for_lark_code", "api_error", "api_error_as")


def _called_name(func) -> str:
    """The bare name a call node invokes — ``f(...)`` and ``mod.f(...)`` alike."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _omits_the_credential_pair(source: str):
    """``True`` when ``source`` contains a Lark-code raise/forward naming no ``credential_env``.

    **An AST walk, not a regex (LD-210 AC9).** LD-200 shipped this as
    ``(?:raise_for_lark_code|api_error)\\s*\\((?:(?!credential_env)[^()]|\\([^()]*\\))*\\)``,
    whose body models **exactly one** level of paren nesting inside the call: at two levels the
    pattern stops matching, so the call is never examined and an omission passes SILENTLY —
    a false negative, which is the one direction a guard must not have. Its own QA found the
    window and named the fix; the technique was already in this module (:func:`_walk`).

    The walk answers the question directly instead of approximating it: a *call* to either
    factory that carries no ``credential_env`` keyword. Three consequences worth stating:

    * a ``def raise_for_lark_code(...)`` is a ``FunctionDef``, not a ``Call``, so the factory's
      own signature needs no special case any more — it simply is not a call site;
    * argument nesting is irrelevant, at any depth, which is the whole point;
    * a ``**kwargs`` forward counts as supplying the pair. That is deliberate and conservative:
      a forward *may* carry it and the walk cannot know, so the check declines to guess rather
      than accuse a call site that is fine. The obligation is proven at the caller instead.

    Source that does not parse is reported as an omission. A check that cannot read a file must
    not answer "no offenders" — the honest answer is to name the module.
    """
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return True
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _called_name(node.func) not in _CREDENTIAL_OBLIGED_CALLS:
            continue
        if any(
            keyword.arg == "credential_env" or keyword.arg is None
            for keyword in node.keywords
        ):
            continue
        return True
    return False


def modules_not_supplying_credential_env(sources=None) -> List[str]:
    """Modules owning an API-using call site that raise a Lark-code error **without** naming
    the credential pair.

    The uniform refusal promises five things, and *which credential pair the call used* is the
    one only the call site can supply — the shared factory cannot know it and must not guess,
    because attributing a denial to the wrong app sends someone to edit the wrong variable. So
    the obligation is on the call sites, and this is the guard that keeps it there.

    Derived from :func:`denial_owning_modules`, so a new API-using operation brings its module
    under the obligation with nobody adding it to a list. ``sources`` overrides the
    read-from-disk step, which is how the guard is proven to bite.
    """
    sources = denial_owning_sources() if sources is None else sources
    offenders = [
        name for name, source in sources.items() if _omits_the_credential_pair(source)
    ]
    return sorted(set(offenders))
