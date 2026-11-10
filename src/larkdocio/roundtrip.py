"""larkdocio.roundtrip — the file-first round trip, as ONE verb instead of eighty lines.

**What this is.** The packaged guide's own highest-fidelity write flow — § *"Recipe: copy
this — the end-to-end update script, from url to applied edit"*, its **file-first Part A /
Part B variant** — promoted from prose a caller retypes into a callable. Two phases, in the
order they have to happen:

* **PULL** (phase A, READ credentials): a url → the wiki hop → the read → the block-id
  projection → **two files on disk**. ``document.snapshot`` is **ours and immutable**;
  ``document.md`` is **theirs and editable**. Nothing else is written and nothing is
  reserved.
* **PUSH** (phase B, WRITE credentials for the apply, READ credentials for the read-back):
  load the snapshot → project → reconcile the **edited** Markdown against that projection →
  **``dry_run`` preview** → apply → re-read and verify by **compose-equivalence**.

They are two calls because the caller's edit happens **between** them — in another process,
or tomorrow.

**IT COMPOSES; IT INVENTS NOTHING.** Every step below is a shipped operation called by name
(:func:`~larkdocio.snapshot.snapshot` / :func:`~larkdocio.snapshot.load`,
:func:`~larkdocio.model.projection.project_block_ids`,
:func:`~larkdocio.write.reconcile.reconcile`,
:func:`~larkdocio.write.compiler.compile_reconciliation`,
:func:`~larkdocio.write.preview.dry_run`, :func:`~larkdocio.write.apply.apply`,
:class:`~larkdocio.read.client.Client`, :class:`~larkdocio.write.WriteClient`). **No endpoint
is opened here, no request family is minted here, and no scope moves** — this module reaches
the API only through those callers, so its permission requirement is theirs.

**THE PREVIEW IS STRUCTURALLY UNSKIPPABLE, and that is the point of the verb.** :func:`push`
builds the plan and calls ``dry_run`` **before it branches on anything**, and
:func:`~larkdocio.write.apply.apply` accepts only the :class:`~larkdocio.write.preview.Plan`
that call returned — so there is no argument, flag or ordering that reaches a write without a
preview. The affordance for non-interactive use is ``apply_changes=True`` (``--apply`` on the
command line): it says *apply the plan you just previewed*, not *skip the preview*. The guide's
own warning is the reason: *"Deleting the preview to save a line is the one edit to this script
that costs something."*

**THE STALENESS GUARD IS ARMED FROM THE SNAPSHOT, OR ITS ABSENCE IS SAID OUT LOUD.** The
persisted ``document_revision_id`` is what arms the ``STALE_DOCUMENT`` whole-document
compare-and-swap, so a snapshot that carried one previews ``revision_guard == "active"``. A
snapshot that carried none previews ``"unavailable"`` — and this module **logs a warning
naming it** rather than letting an unarmed write look like an armed one.

**THE READ-BACK USES THE SHIPPED COMPARISON.** A docx read-back is verified by
``compose(authored) == compose(read_back)``, **never** by string equality of two Markdown
projections: the reader emits loose lists and tab-indented nesting, so a string diff reports a
phantom change on every list anybody will ever author (§ *"Recipe: verify what you authored —
compose-equivalence, not string equality"*). Content ``compose()`` refuses is reported
**unverifiable, by name** — never silently counted clean, and never counted as a mismatch
either, because a refusal to compile is not evidence in either direction.

**THE TWO CREDENTIAL PAIRS ARE RESOLVED INDEPENDENTLY.** Phase A runs on the READ pair; phase
B needs the WRITE pair to apply and the READ pair to read back. Nothing here collapses them,
infers one from the other, or falls back across them — a read-only app is never promoted into
a write, and a write app is never assumed to be able to read.

**WHAT THIS MODULE DOES NOT DO.** It does not launch an editor, batch a second document,
create anything, upload anything, or touch Sheets or Base. It does not redesign a single step
it calls: a defect in ``reconcile`` is a defect in ``reconcile``.
"""
import dataclasses
import logging
from pathlib import Path
from typing import Any, Optional, Tuple

from larkdocio.common import (
    get_read_credentials,
    get_write_credentials,
    validate_download_url,
)
from larkdocio.common.staleness import REVISION_GUARD_ACTIVE
from larkdocio.errors import LarkApplyRefusedError, LarkConfigError, LarkDocIOError
from larkdocio.model.projection import block_markdown, project_block_ids
from larkdocio.read.client import Client
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.snapshot import LarkSnapshotIntegrityError, load, snapshot
from larkdocio.write import (
    RefusedError,
    WriteClient,
    apply,
    compile_reconciliation,
    compose,
    dry_run,
    reconcile,
)
from larkdocio.write.reconcile import ReconciliationState

__all__ = [
    "COMMAND_NAME",
    "MARKDOWN_FILENAME",
    "PHASES",
    "PHASE_PULL",
    "PHASE_PUSH",
    "SNAPSHOT_FILENAME",
    "PullResult",
    "PushResult",
    "Verification",
    "compose_equivalent",
    "pull",
    "push",
]

_LOG = logging.getLogger("larkdocio")

#: The console subcommand this module is reached through. Spelled **once**, here, and imported
#: by the command line and by the capability registry — so the verb's name cannot come to mean
#: one thing in the help text and another in ``capabilities()``.
COMMAND_NAME = "roundtrip"

#: The two phases, in the order they run. They are the words the docs, the help text and the
#: tests all use; there is one vocabulary for this verb, not three.
PHASE_PULL = "pull"
PHASE_PUSH = "push"
PHASES = (PHASE_PULL, PHASE_PUSH)

#: The two files phase A leaves behind, and phase B picks up. The names are the guide's own.
#: **Two files, two owners:** the snapshot is ours and immutable, the Markdown is theirs and
#: editable, and ``reconcile()`` is the only bridge between them.
SNAPSHOT_FILENAME = "document.snapshot"
MARKDOWN_FILENAME = "document.md"

#: **HOW THIS SURFACE NAMES THE WHOLE-DOCUMENT COMPARE-AND-SWAP WHEN IT REPORTS ITS
#: AVAILABILITY** — the push line the CLI prints on every push, and the warning below when the
#: snapshot could not arm it. LD-561: the two of them used to say ``STALE_DOCUMENT guard
#: <state>``, which spends a **refusal** token on the **success** path — a guard that is armed
#: described in the words of a guard that fired, in the stream that reports outcomes (round 5's
#: own oracle read a verbatim successful push as ``outcome: 'refused'``).
#:
#: The noun is checked against the live ``RefusalReason`` enumeration rather than against
#: intuition, because the obvious replacement — *"revision anchor"* — is itself a refusal token
#: (``STALE_ANCHOR``); that check lives in the source repository, not in this wheel, as the suite's
#: ``test_armed_vs_fired_vocabulary.py``.
#:
#: **PRIVATE and surface-local on purpose** (no ``__all__`` entry, never in
#: ``larkdocio.common.staleness``, which both write surfaces re-export): the two statements of
#: it project from here so they cannot drift, and that is all it is for.
_CONCURRENCY_GUARD_LABEL = "concurrency guard"

#: WHICH GUIDE SECTION EACH REFUSAL POINTS AT — **as symbols, never as a section name.**
#:
#: **Refusals point at recipes.** The moment of failure is the highest-attention moment a
#: consumer will ever give this library, so a refusal that names only what went wrong wastes
#: it. But a section *name* written into this module would be a second copy of something the
#: document already says, and a second copy rots — the same reason ``capabilities()`` derives
#: its workflow pointers instead of listing them. So each entry below is the set of symbols
#: that **identify** a section by what it teaches, resolved against the shipped guide at call
#: time by :func:`~larkdocio.guide._sections_teaching`: rename the heading and the pointer
#: follows it; delete the recipe and the pointer degrades to the guide's own index rather than
#: sending a reader at an address that raises.
#:
#: Every symbol must be present, so a section that merely mentions half a round trip is not
#: claimed as teaching it, and each set below is measured to select exactly one section.
_TEACHES_THE_FILE_FIRST_RECIPE = ("snapshot(blocks", "PART A", "PART B")
_TEACHES_THE_UPDATE_RECIPE = (
    "reconcile(", "compile_reconciliation(", "without re-authoring",
)
_TEACHES_THE_READ_BACK_COMPARISON = ("reader_form", "same_content")
#: The credential split is a ``##`` section, not a recipe, so it is looked up at that level.
_TEACHES_THE_CREDENTIAL_SPLIT = ("LARK_WRITE_APP_SECRET", "LARK_READ_APP_SECRET")


def _section_teaching(symbols, levels=(3,)) -> Optional[str]:
    """The slug of the guide section carrying every symbol, or ``None`` if none does."""
    from larkdocio.guide import GUIDE_RESOURCE, _packaged, _sections_teaching

    found = _sections_teaching(_packaged(GUIDE_RESOURCE), tuple(symbols), levels)
    return found[0] if found else None


def _recovery(symbols, levels=(3,)) -> str:
    """The pointer every refusal in this module ends with — one spelling, never a family.

    A pointer that cannot be resolved is **not printed as an address**: naming a section the
    installed guide does not have would hand the reader a call that raises, at the exact
    moment they are least able to absorb a second failure.
    """
    slug = _section_teaching(symbols, levels)
    if slug is None:
        return (
            "The recovery is in the packaged guide — run `larkdocio guide` for its index."
        )
    return f"The recovery is in the packaged guide: `larkdocio guide --section {slug}`."


def _refuse(detail: str, symbols, levels=(3,)):
    raise LarkConfigError(f"{detail} {_recovery(symbols, levels)}")


# --------------------------------------------------------------------------- #
# The two files                                                                #
# --------------------------------------------------------------------------- #

def snapshot_path(workdir) -> Path:
    """Where phase A writes the snapshot and phase B reads it — derived, never guessed."""
    return Path(workdir) / SNAPSHOT_FILENAME


def markdown_path(workdir) -> Path:
    """Where phase A writes the editable projection — **this is the file you edit**."""
    return Path(workdir) / MARKDOWN_FILENAME


# --------------------------------------------------------------------------- #
# Credentials — two pairs, resolved independently, refused before any call     #
# --------------------------------------------------------------------------- #

def _read_credentials_or_refuse(what: str):
    """The READ pair, or the shipped typed refusal naming the pair the read path is reading.

    ``get_read_credentials`` used to return **blanks** rather than raising — it has a legacy
    fallback and a blank pair looked like a legitimate answer for a read-free process — so the
    refusal was authored here, naming the pair :func:`resolved_read_env` says is in force rather
    than the other one, which would send a reader to edit a variable nothing is consulting.
    **LD-580 moved that refusal into the getter itself**, same F8 shape and same in-force pair,
    so the reason above survives and only its conclusion is superseded: a second authoring here
    would now be a second thing to keep true, exactly as :func:`_write_credentials_or_refuse`
    says. This delegates and adds only the recovery pointer.

    *what* stays in the signature: the caller-naming it supplied is what tells a reader which
    phase refused, and it is preserved in the message rather than dropped.
    """
    try:
        return get_read_credentials()
    except LarkConfigError as refusal:
        raise LarkConfigError(
            f"{what}: {refusal} "
            f"{_recovery(_TEACHES_THE_CREDENTIAL_SPLIT, (2,))}") from None


def _write_credentials_or_refuse():
    """The WRITE pair, or the shipped typed refusal naming ``LARK_WRITE_APP_*``.

    Delegates to :func:`~larkdocio.common.auth.get_write_credentials`, which already refuses
    with both variable names and says the write path never borrows read credentials — a second
    authoring of that refusal here would be a second thing to keep true.
    """
    try:
        return get_write_credentials()
    except LarkConfigError as refusal:
        raise LarkConfigError(f"{refusal} {_recovery(_TEACHES_THE_CREDENTIAL_SPLIT, (2,))}") from None


# --------------------------------------------------------------------------- #
# Phase A — PULL                                                               #
# --------------------------------------------------------------------------- #

@dataclasses.dataclass(frozen=True)
class PullResult:
    """What phase A left behind, and the facts phase B will not have to be told again."""

    #: The directory holding the two files.
    workdir: str
    #: The snapshot artefact — ours, immutable, checksummed.
    snapshot_path: str
    #: The Markdown projection — **theirs**, editable. This is the file to hand an agent.
    markdown_path: str
    #: The docx token the read was taken from (the wiki hop already applied).
    document_token: str
    #: The API domain the read was taken against — the one fact phase B cannot derive.
    api_domain: str
    #: The revision the read was at, or ``None``. It is what arms the staleness guard.
    document_revision_id: Optional[Any]
    #: How many blocks the projection emitted an identity marker for.
    block_count: int

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def pull(url: str, workdir, *, reader=None) -> PullResult:
    """Phase A: read ``url`` and write the two files into ``workdir``.

    ``reader`` is an already-built :class:`~larkdocio.read.client.Client`; omit it and one is
    built from the READ pair. It exists so the flow can be exercised without a network, not as
    a way around the credential boundary.

    Refuses — typed, and pointing at the recipe — for a url that is not a document url, a wiki
    node that does not resolve, and an absent READ pair. Writes nothing when it refuses.
    """
    domain, doc_type, doc_token = validate_download_url(url)
    # `validate_download_url` recognises six surface types and only two of them are documents.
    # Reading a spreadsheet or Base token as a docx does not fail — it comes back EMPTY, and an
    # empty projection reconciles to nothing three commands later, which is the least
    # diagnosable failure this verb could produce. So the type is checked where it is known.
    if doc_type not in ("docx", "wiki"):
        _refuse(
            f"that is a {doc_type!r} url, and this verb round-trips a DOCUMENT (docx or wiki). "
            "Nothing was written. A spreadsheet is read and written through the Sheets "
            "surface and a Base through the Base surface, each a library call.",
            _TEACHES_THE_FILE_FIRST_RECIPE,
        )

    if reader is None:
        reader = Client(*_read_credentials_or_refuse("`roundtrip pull`"), domain)

    # THE WIKI HOP. A wiki url wraps the real docx token; skip this branch and the read
    # returns an empty document while every later step politely refuses — which is the
    # failure this verb exists to stop a caller from re-implementing.
    if doc_type == "wiki":
        try:
            node = reader.get_wiki_node_info(doc_token)
        except LarkDocIOError as failure:
            _refuse(
                f"the wiki url resolved to node {doc_token!r} and the node could not be "
                f"read ({failure}), so there is no docx token to read from. Nothing was "
                "written.",
                _TEACHES_THE_FILE_FIRST_RECIPE,
            )
        doc_type, doc_token = node.obj_type, node.obj_token
        if not doc_token:
            _refuse(
                "the wiki node carries no document token, so it does not wrap a document "
                "this verb can read. Nothing was written.",
                _TEACHES_THE_FILE_FIRST_RECIPE,
            )

    docx, blocks = reader.get_docx_content(doc_token)
    root = Parser(Config()).parse_docx_tree(doc_token, blocks)
    projection = project_block_ids(root)

    workdir = Path(workdir)
    # The snapshot persists the READ, not the projection: the payload is the evidence and the
    # projection is derived from it, which is why phase B's projection comes back
    # byte-identical. `api_domain` travels because it is the one fact a successor process
    # cannot derive from a token.
    snapshot(
        blocks,
        document_token=doc_token,
        document_revision_id=docx.revision_id,
        api_domain=domain,
        path=str(snapshot_path(workdir)),
    )
    target = markdown_path(workdir)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(projection.markdown, encoding="utf-8")

    return PullResult(
        workdir=str(workdir),
        snapshot_path=str(snapshot_path(workdir)),
        markdown_path=str(target),
        document_token=doc_token,
        api_domain=domain,
        document_revision_id=docx.revision_id,
        block_count=len(projection.block_ids),
    )


# --------------------------------------------------------------------------- #
# The read-back comparison — the SHIPPED one                                    #
# --------------------------------------------------------------------------- #

def compose_equivalent(authored: str, read_back: str) -> Tuple[Optional[bool], Optional[str]]:
    """``(verdict, why_not_comparable)`` for two Markdown strings, by **compose-equivalence**.

    ``compose()`` returns a tuple of frozen ``NewBlock`` values, so ``==`` is the entire
    comparison — there is no normalizer to write and no diff library to reach for. What this
    adds over the two bare calls is the third answer: content outside the authoring dialect
    makes ``compose()`` **refuse**, and a refusal is *not comparable*, which is a different
    fact from *different*. Returning ``None`` for it is what keeps a pre-existing bold run in
    a read-back region from being reported as a failed write.

    A string comparison is deliberately not offered here at all: the reader emits **loose**
    lists and **tab**-indented nesting, so ``authored in read_back`` is ``False`` for every
    list anybody will ever author, for a rendering reason.
    """
    try:
        left = compose(authored)
    except (RefusedError, LarkDocIOError, ValueError) as refusal:
        return None, f"the authored Markdown is not comparable: {refusal}"
    try:
        right = compose(read_back)
    except (RefusedError, LarkDocIOError, ValueError) as refusal:
        return None, f"the read-back Markdown is not comparable: {refusal}"
    return left == right, None


@dataclasses.dataclass(frozen=True)
class Verification:
    """What the read-back found, per block, in the three answers the comparison has."""

    #: Block ids whose read-back composed equal to what was authored.
    verified: Tuple[str, ...] = ()
    #: ``(block_id, why)`` for a block whose read-back composed to something else. **A real
    #: content difference, not a rendering one** — the whole reason the comparator is
    #: ``compose()`` and not ``==`` on two strings.
    mismatched: Tuple[Tuple[str, str], ...] = ()
    #: ``(block_id, why)`` for a block one of whose sides ``compose()`` refused, and for a
    #: change whose block has no id to re-read by (an insert's block does not exist until it
    #: is applied, and a delete's is gone). Reported **loudly**; never counted as clean.
    unverifiable: Tuple[Tuple[str, str], ...] = ()

    @property
    def ok(self) -> bool:
        """Whether nothing came back different. Unverifiable entries are **not** failures —
        they are disclosed, and a caller who needs them settled re-reads the document."""
        return not self.mismatched

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "verified": list(self.verified),
            "mismatched": [list(row) for row in self.mismatched],
            "unverifiable": [list(row) for row in self.unverifiable],
        }


def verify_read_back(plan, read_back_projection) -> Verification:
    """Verify an applied reconciliation against a **fresh projection** of the document.

    Per **edited** block: its id survives an edit (that is what makes an update an update), so
    the block that was authored can be found again by identity rather than by searching text,
    and the two Markdown strings are compared by :func:`compose_equivalent`.

    An **inserted** or **deleted** entry is reported unverifiable **by construction**: an
    insert's block did not exist when the plan was made, so there is no id to look it up by,
    and a delete's block is meant to be gone. Saying so is the honest answer; guessing which
    new block was the insert is not.
    """
    verified, mismatched, unverifiable = [], [], []
    for entry in plan.changes:
        if entry.state is not ReconciliationState.EDITED:
            unverifiable.append((
                entry.block_id or f"<{entry.state.value}>",
                f"a {entry.state.value!r} change carries no surviving block id to re-read "
                "by, so the read-back cannot address it — re-read the document to see it",
            ))
            continue
        try:
            found = block_markdown(read_back_projection, entry.block_id)
        except ValueError:
            unverifiable.append((
                entry.block_id,
                "the block is not in the re-read projection — it no longer carries the id "
                "the plan named",
            ))
            continue
        verdict, why = compose_equivalent(entry.after_markdown or "", found)
        if verdict is None:
            unverifiable.append((entry.block_id, why))
        elif verdict:
            verified.append(entry.block_id)
        else:
            mismatched.append((
                entry.block_id,
                "the document composed to different content from what was authored",
            ))
    return Verification(
        verified=tuple(verified),
        mismatched=tuple(mismatched),
        unverifiable=tuple(unverifiable),
    )


# --------------------------------------------------------------------------- #
# Phase B — PUSH                                                               #
# --------------------------------------------------------------------------- #

@dataclasses.dataclass(frozen=True)
class PushResult:
    """What phase B did — and, when it applied nothing, what it would have done."""

    workdir: str
    document_token: str
    api_domain: Optional[str]
    #: The offline reconciliation — every block's verdict.
    plan: Any
    #: The :class:`~larkdocio.write.preview.Plan` ``dry_run`` built. **Always present**: it is
    #: built before anything branches, and it is the only object ``apply`` accepts.
    preview: Any
    #: ``"active"`` when the snapshot carried a revision, ``"unavailable"`` when it did not.
    revision_guard: str
    revision_guard_detail: Optional[str]
    #: Whether the plan was applied. ``False`` is the default: a bare push is a rehearsal.
    applied: bool = False
    #: The apply-log, or ``None`` for a rehearsal.
    log: Any = None
    #: The read-back verdict, or ``None`` for a rehearsal.
    verification: Optional[Verification] = None

    def to_dict(self) -> dict:
        return {
            "workdir": self.workdir,
            "document_token": self.document_token,
            "api_domain": self.api_domain,
            "plan": self.plan.to_dict(),
            "preview": self.preview.to_dict(),
            "revision_guard": self.revision_guard,
            "revision_guard_detail": self.revision_guard_detail,
            "applied": self.applied,
            "verification": self.verification.to_dict() if self.verification else None,
        }


#: The remedy for the *nothing differs* arm — the one this refusal has always carried, and
#: still the ONLY true remedy when the plan conserves nothing.
_EDIT_THE_FILE_REMEDY = (
    "Edit that file (keep every `<!-- lark:block:… -->` marker exactly where it is — "
    "identity is not content) and push again."
)


def _no_change_refusal(markdown_file, plan) -> str:
    """The detail for ``change_count == 0`` — a DISJUNCTION when the plan conserves blocks.

    Two different callers reach this branch: the one who changed nothing, and the one whose
    real change landed inside a block the authoring dialect cannot re-express, which the
    reconciler conserves by construction so it reconciles to nothing. **The plan cannot
    settle which** — ``ReconciliationEntry.conserved_opaque`` is emitted for every surviving
    opaque block whether or not anything was edited — so this message asserts **neither**. It
    discloses what the plan does know: *which* blocks are conserved, read straight off the
    public :attr:`~larkdocio.write.reconcile.ReconciliationPlan.conserved_block_ids`.

    It also narrows the conserved arm as far as the plan can, and no further: each conserved
    entry carries ``body_differs``, so
    :attr:`~larkdocio.write.reconcile.ReconciliationPlan.conserved_block_ids_that_read_back_differently`
    says which of those bodies came back changed — itself an ambiguous fact by construction
    (the consumer edited it, or the projection reshaped it and the editor normalised the
    reshaping), which is why it names where to look first and still asserts nothing. Both the
    ids and that bit are **read off the plan, never re-derived here**: the reason the old
    wording gave for having no such signal stands unchanged — re-parsing the edited Markdown
    to compute a discriminating signal would be a second, divergent definition of the
    reconciler's own transforms — and it is exactly why the signal is computed once, at its
    home in the reconciler, where those transforms live. What is superseded is only the
    conclusion that no such signal exists.

    With nothing conserved there is no second arm, and offering one would be the same
    wrong-cause defect pointing the other way — so the plain wording stands unchanged. So does
    the wording when nothing is disclosed: a plan with no read-back difference to report reads
    exactly as it did before the disclosure existed.
    """
    opening = (
        f"the edited Markdown at {str(markdown_file)!r} reconciles to no change at all, "
        "so there is nothing to apply."
    )
    conserved = plan.conserved_block_ids
    if not conserved:
        return f"{opening} {_EDIT_THE_FILE_REMEDY}"
    differing = plan.conserved_block_ids_that_read_back_differently
    disclosure = ""
    if differing:
        disclosure = (
            f" Of those, {', '.join(repr(block_id) for block_id in differing)} read back "
            f"differently from the Markdown this file was written from — which says where to "
            f"look first and settles nothing on its own: EITHER an edit landed there, OR the "
            f"projection reshaped that body and the editor normalised the reshaping."
        )
    return (
        f"{opening} Two different things reconcile to nothing and this refusal cannot tell "
        f"them apart, so it states both: EITHER nothing in that file differs from what the "
        f"document already holds — {_EDIT_THE_FILE_REMEDY} — OR the change landed inside one "
        f"of the blocks this document conserves: "
        f"{', '.join(repr(block_id) for block_id in conserved)}.{disclosure} The authoring "
        f"dialect cannot re-express those blocks, so the reconciler conserves them by "
        f"construction and an edit made inside one reconciles to no change and is NOT "
        f"written. For that arm, re-editing the file cannot help: move the content into a "
        f"block outside them, or make that change in Lark itself."
    )


def push(workdir, *, apply_changes: bool = False, reader=None, writer=None) -> PushResult:
    """Phase B: reconcile the edited Markdown against the snapshot, preview, and (opt) apply.

    ``apply_changes`` is the *apply the plan you just previewed* affordance, and it is the
    **only** thing it is: the preview is built either way, before this flag is read, and
    ``apply`` takes nothing but the object that call returned. There is no argument here that
    removes a gate.

    ``reader`` / ``writer`` are already-built clients; omit them and they are built from their
    **own** credential pairs. Both pairs are resolved **first**, before anything is loaded or
    called, so an invocation that could never have finished says so immediately and by name.

    Refuses — typed, pointing at the recipe — for a missing workdir file, a snapshot that
    fails its integrity check, an edited file that reconciles to nothing, a reconciliation the
    engine refuses, and a snapshot carrying no API domain to build a client from.
    """
    workdir = Path(workdir)
    snapshot_file, markdown_file = snapshot_path(workdir), markdown_path(workdir)

    # THE CREDENTIAL BOUNDARY, honoured before a single byte is read: phase B is the WRITE
    # phase, and a rehearsal you could not have performed is not information. The two pairs
    # are resolved INDEPENDENTLY — neither is inferred from, or falls back to, the other.
    write_credentials = None if writer is not None else _write_credentials_or_refuse()
    if reader is None:
        _read_credentials_or_refuse("`roundtrip push`'s read-back")

    for path, what in ((snapshot_file, "the snapshot"), (markdown_file, "the edited Markdown")):
        if not path.exists():
            _refuse(
                f"{what} file {str(path)!r} is not there, so there is nothing to push. Run "
                f"`larkdocio {COMMAND_NAME} {PHASE_PULL} \"<url>\" -o {str(workdir)}` first — "
                "the two files it writes are what this phase resumes from.",
                _TEACHES_THE_FILE_FIRST_RECIPE,
            )

    # A PERSISTED READ IS REHYDRATED EXACTLY OR REFUSED TYPED — NEVER REPAIRED. `load` already
    # names what failed and names re-download as the fix; the recipe pointer is appended and
    # the class, the reason and the source travel unchanged.
    try:
        snap = load(str(snapshot_file))
    except LarkSnapshotIntegrityError as broken:
        raise LarkSnapshotIntegrityError(
            f"{broken.detail} {_recovery(_TEACHES_THE_FILE_FIRST_RECIPE)}",
            reason=broken.reason,
            source=broken.source,
        ) from None

    projection = project_block_ids(snap.tree)
    edited = markdown_file.read_text(encoding="utf-8")

    plan = reconcile(projection, edited)
    if not plan.ok:
        _refuse(
            "the edited Markdown did not reconcile against the snapshot, so NOTHING was "
            "planned and nothing was written: "
            + "; ".join(f"{r.reason}: {r.detail}" for r in plan.refusals),
            _TEACHES_THE_UPDATE_RECIPE,
        )
    if plan.change_count == 0:
        _refuse(_no_change_refusal(markdown_file, plan), _TEACHES_THE_UPDATE_RECIPE)

    try:
        requests = compile_reconciliation(plan, projection)
    except RefusedError as refused:
        _refuse(
            f"the reconciliation could not be compiled into requests and nothing was "
            f"written: {refused}",
            _TEACHES_THE_UPDATE_RECIPE,
        )

    # THE GATE. Built before anything branches on `apply_changes`, armed with the revision the
    # snapshot persisted, and the only object `apply` will accept.
    preview = dry_run(requests, snap.tree, document_revision_id=snap.document_revision_id)
    if preview.revision_guard != REVISION_GUARD_ACTIVE:
        # LOUDLY, never silently unarmed: a snapshot taken with no revision cannot arm the
        # whole-document compare-and-swap, so a concurrent edit will NOT be refused before the
        # write. The caller is told, in the log and on the result.
        #
        # It says the guard's AVAILABILITY, never an outcome (LD-561): this warning is printed
        # on a push that then SUCCEEDS, so a refusal token in it would be read as a refusal.
        _LOG.warning(
            "roundtrip: the %s is %s — this snapshot carries no "
            "document_revision_id, so a concurrent edit will not be refused before the write. "
            "%s",
            _CONCURRENCY_GUARD_LABEL,
            preview.revision_guard,
            preview.revision_guard_detail or "Take a fresh snapshot with `roundtrip pull`.",
        )

    result = PushResult(
        workdir=str(workdir),
        document_token=snap.document_token,
        api_domain=snap.api_domain,
        plan=plan,
        preview=preview,
        revision_guard=preview.revision_guard,
        revision_guard_detail=preview.revision_guard_detail,
    )
    if not apply_changes:
        return result

    if writer is None:
        if not snap.api_domain:
            _refuse(
                "this snapshot carries no api_domain, so there is no way to know which "
                "tenant to build a write client for — and the two domains are two different "
                "companies, so it is never guessed. Take a fresh snapshot with "
                f"`larkdocio {COMMAND_NAME} {PHASE_PULL}`.",
                _TEACHES_THE_FILE_FIRST_RECIPE,
            )
        writer = WriteClient(*write_credentials, snap.api_domain)

    try:
        log = apply(preview, writer, document_id=snap.document_token)
    except LarkApplyRefusedError as refused:
        raise LarkApplyRefusedError(
            f"{refused} {_recovery(_TEACHES_THE_UPDATE_RECIPE)}",
            log=refused.log,
            applied=refused.applied,
            refused=refused.refused,
        ) from None

    # THE READ-BACK LAW: a green apply is not a receipt. The log says what was ACCEPTED; only
    # a re-read says what the document now CONTAINS, and only compose-equivalence reads that
    # re-read correctly.
    if reader is None:
        reader = Client(*get_read_credentials(), snap.api_domain)
    _docx, blocks = reader.get_docx_content(snap.document_token)
    read_back = project_block_ids(
        Parser(Config()).parse_docx_tree(snap.document_token, blocks)
    )
    verification = verify_read_back(plan, read_back)

    return dataclasses.replace(
        result, applied=True, log=log, verification=verification
    )
