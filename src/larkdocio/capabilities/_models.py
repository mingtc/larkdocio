"""The typed layer — the 17 frozen dataclasses ``capabilities()`` is built from.

LD-244: the verbatim pre-split slice, lines 115-812 of the
2,770-line ``capabilities.py``. Nothing in it was rewritten.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from . import _resolution
from ._provenance import dedupe as _dedupe_provenance

# --------------------------------------------------------------------------- #
# The typed layer — frozen dataclasses whose ``to_dict()`` emits JSON-native   #
# types ONLY (lists, never tuples/sets), so the registry round-trips losslessly.#
# --------------------------------------------------------------------------- #

#: The ONE per-surface key that carries call sites, spelled once here and imported by
#: everything that walks it. A second spelling of a key name is how three sibling keys came
#: to hold a surface's verbs with no shipped definition between them.
CALL_SITES_KEY = "operations"

#: The key a call-site row carries its permission block under, and — inside that block — the
#: key holding the endpoint keys whose scope requirement was **never observed**. Spelled here
#: beside :data:`CALL_SITES_KEY` for the same reason and for one more: the summary must be able
#: to reach the payload's key *vocabulary* while reaching nothing that holds capability truth,
#: so a key it walks has to be importable from this module or it would have to be typed there.
#: An unrecorded requirement is data, not a to-do — no code may read it as *needs nothing*.
PERMISSIONS_KEY = "permissions"
UNKNOWN_REQUIREMENTS_KEY = "unknown_requirements"

#: The closed set of ``kind`` values a call-site row can carry, strongest-commitment first:
#: ``operation`` — a kind this surface's engine dispatches (a write op family, a read
#: client's public op); ``leg`` — an API-using call site that is not one of those;
#: ``lifecycle`` — a call that brings the file itself into existence or destroys it. The kind
#: is what the three keys used to say by position, said in the row instead, so it travels with
#: the row a consumer copied out.
CALL_KINDS = ("operation", "leg", "lifecycle")


def _call_site_row(op, kind: str) -> dict:
    """One serialized call site: the op's own row with its ``kind`` beside its ``name``.

    The kind is written by the surface (it knows which authoring field the row came out of),
    never by the row itself — an :class:`Operation` does not know whether it was registered as
    a dispatched op or as a leg, and inventing a field for it to guess with would be a second
    place for the same fact to live.
    """
    row = op.to_dict()
    return {"name": row.pop("name"), "kind": kind, **row}


@dataclass(frozen=True)
class Operation:
    """One capability operation. ``projected_from`` names the code source it was
    projected out of (a registry table or a client class) — never hand-authored.
    Write ops carry the registry keyings (``write_kind`` / ``entry_ops`` for sheets);
    read ops carry neither.

    ``anchor_kinds`` is the docx-write answer to "**how** do I point this request
    family at its target": the anchor classes the family's own anchor field accepts, projected
    off that field's annotation. An op *name* cannot carry it — ``delete`` reads as one
    capability whether it can target a ``block_id`` or only a verbatim quote, and a
    consumer left to discover the difference the hard way has been failed.

    ``impl`` is the callable (or callables) that implement the op, carried so its **permission
    requirement can be derived from its own code** rather than hand-listed beside it. It is
    deliberately absent from ``to_dict()`` — a function is not JSON, and the serialized answer
    a consumer reads is the ``permissions`` block it produces.
    """

    name: str
    projected_from: str
    #: **How** the op name maps to code at ``projected_from`` — one of the closed set declared
    #: in :mod:`._resolution` (LD-320). ``projected_from`` alone was not walkable: a module, a
    #: class, a descriptor tuple keyed by ``.name`` and one keyed by ``.kind`` are followed
    #: four different ways, and a consumer was left to guess which. This says which, so the
    #: registry → code jump is mechanical (:func:`._resolution.resolve` performs it) and the
    #: resolvability guard — in the source repository, not in the wheel,
    #: ``tests/test_capabilities_op_resolution.py`` — can fail a row that stops resolving. The
    #: default is the majority shape; a projection whose source is not an attribute holder
    #: must say so, and the guard is what makes a wrong default visible.
    resolves_by: str = _resolution.ATTRIBUTE
    request_types: List[str] = field(default_factory=list)
    write_kind: Optional[str] = None
    entry_ops: Optional[List[str]] = None
    anchor_kinds: Optional[List[str]] = None
    #: The **cell-style attributes** a style write can set — the sheets-write answer to the same
    #: question ``anchor_kinds`` answers for docx: an op *name* cannot carry it. ``style`` reads as
    #: one capability whether or not it can set a border, and a consumer who plans a bordered
    #: report around a guess has been failed. **Projected** off ``CellStyle``'s own dataclass
    #: fields, so widening the style widens this automatically and it cannot drift.
    style_fields: Optional[List[str]] = None
    #: Cell-style attributes that were **probed and are NOT writable** — the honest other half of
    #: ``style_fields``, because an absence is not self-explaining. A consumer reading only the
    #: settable list cannot tell "not implemented yet" from "characterized live and refuted";
    #: this says which; the shipped guide carries the evidence, and so does — in the source repository,
    #: not in the wheel — SHEETS.md (LD-189: word-wrap).
    style_fields_not_writable: Optional[List[str]] = None
    #: The merge types a merge write accepts, **projected** off
    #: :data:`~larkdocio.sheets.requests.SUPPORTED_MERGE_TYPES` — and, beside it, the ones that
    #: were characterized live and are **refused**. Same reasoning as ``style_fields``: ``merge``
    #: reads as one capability whether or not it can merge per-row, and a consumer who plans a
    #: row-merge around a guess has been failed. The refusal is not shyness — the shipped loss
    #: preview over-reported the loss for those two (LD-190), and a mis-disclosing destructive
    #: op is worse than an absent one.
    merge_types: Optional[List[str]] = None
    merge_types_refused: Optional[List[str]] = None
    #: Fields a family can WRITE but larkdocio cannot read back — the asymmetry a consumer
    #: discovers the hard way otherwise (LD-190: a dropdown's ``options.colors``, which Lark
    #: reports under ``options.colorValueMap`` and no larkdocio read leg touches).
    fields_not_read_back: Optional[List[str]] = None
    impl: object = field(default=None, repr=False, compare=False)
    permissions: object = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        d: dict = {"name": self.name, "projected_from": self.projected_from,
                   "resolves_by": self.resolves_by}
        if self.resolves_by == _resolution.ENTRY_POINT:
            # The "use X" answer is X's OWN identity, read off the callable this row already
            # carries — so an internal op cannot publish a fabricated entry point, and cannot
            # keep publishing a stale one after the callable moves.
            entry_point = _resolution.entry_point_of(self.impl)
            d["entry_point"] = entry_point
            d["note"] = f"internal op — use {entry_point}"
        if self.request_types:
            d["request_types"] = list(self.request_types)
        if self.write_kind is not None:
            d["write_kind"] = self.write_kind
        if self.entry_ops is not None:
            d["entry_ops"] = list(self.entry_ops)
        if self.anchor_kinds is not None:
            d["anchor_kinds"] = list(self.anchor_kinds)
        if self.style_fields is not None:
            d["style_fields"] = list(self.style_fields)
        if self.style_fields_not_writable is not None:
            d["style_fields_not_writable"] = list(self.style_fields_not_writable)
        if self.merge_types is not None:
            d["merge_types"] = list(self.merge_types)
        if self.merge_types_refused is not None:
            d["merge_types_refused"] = list(self.merge_types_refused)
        if self.fields_not_read_back is not None:
            d["fields_not_read_back"] = list(self.fields_not_read_back)
        if self.permissions is not None:
            d["permissions"] = self.permissions.to_dict()
        return d


@dataclass(frozen=True)
class LifecycleOp:
    """One **file-lifecycle** call on a write surface — bring a document / spreadsheet into
    EXISTENCE, or destroy it.

    Deliberately not an :class:`Operation`. ``operations`` is the plan-gated write registry —
    everything ``dry_run`` can preview and ``apply`` can perform — and a lifecycle call is
    neither: it has no plan, no anchor and no target inside a file, because it *is* the file.
    Listing it as a write op would say the engine can create a document, which it cannot.

    It nevertheless belongs in this registry, and its absence was a real failure: the docx
    pair shipped well documented and appeared **zero** times here, so the one capability a
    consumer needs before any write experiment — make a throwaway file, work in it, trash it
    — was reachable only through ``dir()``, and the spreadsheet half did not exist at all.

    * ``name`` / ``projected_from`` — the method and the class it was projected off (a row
      naming a method that does not exist fails at projection time);
    * ``summary`` — the method's **own** first docstring line, so the registry cannot describe
      a call differently from the code that implements it. That is also what carries a
      delete's blast radius: trashing a whole file and removing one tab are different acts,
      and the registry names both.
    """

    name: str
    projected_from: str
    summary: str
    #: The same declared projection shape :class:`Operation` carries (LD-320). A lifecycle row
    #: is always a method on the class its ``projected_from`` names, so the default holds for
    #: every row today — it is published anyway, because a consumer walking rows should not
    #: have to know which of the three row-bearing keys answers the question.
    resolves_by: str = _resolution.ATTRIBUTE
    impl: object = field(default=None, repr=False, compare=False)
    permissions: object = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        d = {"name": self.name, "projected_from": self.projected_from,
             "resolves_by": self.resolves_by, "summary": self.summary}
        if self.permissions is not None:
            d["permissions"] = self.permissions.to_dict()
        return d


@dataclass(frozen=True)
class Credentials:
    """A surface's credential + scope requirement — the READ/WRITE app split (code
    truth: the ``common.auth`` env tuples) plus the documented scope strings."""

    app: str  # "read" | "write"
    env_primary: List[str]
    env_fallback: List[str]
    scopes: List[str] = field(default_factory=list)
    optional_scopes: List[str] = field(default_factory=list)
    note: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "app": self.app,
            "env_primary": list(self.env_primary),
            "env_fallback": list(self.env_fallback),
            "scopes": list(self.scopes),
            "optional_scopes": list(self.optional_scopes),
        }
        if self.note is not None:
            d["note"] = self.note
        return d


@dataclass(frozen=True)
class ContentConstraints:
    """A write surface's **creatable-content floor** — what it can bring into EXISTENCE,
    which an op name alone cannot express.

    The distinction the fields draw, and why it matters: ``edit`` and ``insert`` are both
    just op names, so a consumer reading the projection would reasonably budget for
    creating a heading, a list, or a table — and in an earlier release,
    none of those was possible. What survives the lift is the **merge** nuance: a merged
    table reads (as HTML) and its unmerged cells edit, but Markdown has no colspan/rowspan
    so no merge can be authored — and ``WRITE_HOSTILE_NODE_TYPES`` excludes ``TableNode``,
    which reads as "everything about a table is writable". Fields:

    * ``creatable`` — the ONLY content types a create op accepts, **projected** from
      ``InsertRequest.content``'s type args (never hand-listed; a ``Union`` of accepted
      content types is flattened, so widening the union widens the floor automatically);
    * ``creatable_kinds`` — the **kinds** those types express, projected off the
      CLOSED ``NewBlockKind`` enum. The container types alone cannot answer the question a
      consumer actually asks — ``creatable: ["NewBlock", "NewParagraph"]`` is true and says
      nothing about whether a *heading* or a *table* can be created, which is the entire
      subject of the creatable-floor widening;
    * ``creatable_block_types`` — the docx ``block_type`` integers those kinds
      create, projected off ``encode.CREATABLE_BLOCK_TYPES``. This is the **join key to
      BLOCKS.md** — in the source repository, not in the wheel — whose matrix is keyed by block type
      rather than by kind, so the two truth surfaces can be cross-checked instead of
      separately believed;
    * ``creatable_out_of_band`` / ``creatable_out_of_band_block_types`` — what this library
      can bring into existence **without** the plan-gated path, because it needs *bytes* and
      a network call the Markdown compiler has neither of. A separate field rather than a
      widening of ``creatable_kinds``, because the two answer different questions: a kind is
      something ``compose`` can compile, and an image is not — it is a dedicated op. The
      block types are projected off that op's own set, so this cannot drift from the code
      any more than the plan-gated pair can;
    * ``creatable_content_fields`` — those types' own dataclass fields, projected, so the
      floor's shape is provable rather than asserted;
    * ``not_creatable`` — the shapes a consumer will otherwise plan an architecture around;
    * ``editable_not_creatable`` — the nuance that editable ≠ creatable;
    * ``floor`` — the one-sentence statement of the floor;
    * ``projected_from`` / ``kinds_projected_from`` / ``block_types_projected_from`` — the
      code each set was projected out of, so "is this hand-maintained?" is answerable from
      the payload alone.
    """

    creatable: List[str]
    creatable_kinds: List[str]
    creatable_block_types: List[int]
    creatable_out_of_band: List[str]
    creatable_out_of_band_block_types: List[int]
    creatable_content_fields: List[str]
    not_creatable: List[str]
    editable_not_creatable: List[str]
    floor: str
    projected_from: str
    kinds_projected_from: str
    block_types_projected_from: str
    out_of_band_projected_from: str

    def to_dict(self) -> dict:
        return {
            "creatable": list(self.creatable),
            "creatable_kinds": list(self.creatable_kinds),
            "creatable_block_types": list(self.creatable_block_types),
            "creatable_out_of_band": list(self.creatable_out_of_band),
            "creatable_out_of_band_block_types": list(
                self.creatable_out_of_band_block_types),
            "creatable_content_fields": list(self.creatable_content_fields),
            "not_creatable": list(self.not_creatable),
            "editable_not_creatable": list(self.editable_not_creatable),
            "floor": self.floor,
            "projected_from": self.projected_from,
            "kinds_projected_from": self.kinds_projected_from,
            "block_types_projected_from": self.block_types_projected_from,
            "out_of_band_projected_from": self.out_of_band_projected_from,
        }


@dataclass(frozen=True)
class FieldAuthoringVocabulary:
    """A Base write surface's **field-authoring allow-list** — which columns the API will
    bring into existence, declared by the SERVER rather than by this library.

    Distinct from :class:`ContentConstraints`, which answers the same shape of question for
    docx content. This one is not projected off larkdocio's own registry at all: both enums
    are transcribed from ``error.field_violations``, the body Lark's fields API returns with
    every refusal, so the payload publishes Lark's vocabulary verbatim. ``status`` states
    what is NOT being claimed — no operation on the surface authors a field — and the three
    quadrant lists answer the question the allow-list alone cannot: whether a column that
    CAN be created has cells that can be WRITTEN. They are two different sets and they cross.

    The sequences here are the enforcing constants themselves, not copies of them, so the
    refusal a caller meets and the list the registry publishes cannot drift apart.
    """

    authorable_types: tuple
    authorable_ui_types: tuple
    not_authorable: dict
    declared_by: str
    status: str
    quadrant_note: str
    authorable_but_cells_unwritable: tuple
    neither_authorable_nor_writable: tuple
    cells_writable_but_field_unauthorable: tuple
    projected_from: str
    evidence: str

    def to_dict(self) -> dict:
        return {
            "authorable_types": list(self.authorable_types),
            "authorable_ui_types": list(self.authorable_ui_types),
            "not_authorable": dict(self.not_authorable),
            "declared_by": self.declared_by,
            "status": self.status,
            "quadrant_note": self.quadrant_note,
            "authorable_but_cells_unwritable": [
                list(pair) for pair in self.authorable_but_cells_unwritable],
            "neither_authorable_nor_writable": [
                list(pair) for pair in self.neither_authorable_nor_writable],
            "cells_writable_but_field_unauthorable": [
                list(pair) for pair in self.cells_writable_but_field_unauthorable],
            "projected_from": self.projected_from,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class LevelDescriptor:
    """A READ surface's **level model** — which entry point hands back the full-fidelity
    objects, and which hands back the lossy Markdown projection.

    The one question an op list cannot answer. ``parse_docx_tree`` and
    ``parse_docx_content`` are two names in the same ``operations`` list, and nothing about
    that list says the first one preserves everything while the second is a deliberately
    lossy rendering for people to read — so a consumer reading the projection cannot tell
    whether going through Markdown is **required** or merely **available**. It is available:
    the objects are the source of truth on every surface, and the projection is optional.

    Deliberately a **framing** descriptor rather than a second matrix — five fields, all
    strings or absent:

    * ``object_entry_point`` / ``object_returns`` — the full-fidelity read, as a dotted path
      that really resolves (so the registry cannot advertise a call the library lacks), and
      what it hands back;
    * ``projection_entry_point`` / ``projection_returns`` — the Markdown projection of the
      same read, or ``None`` on a surface that has none;
    * ``summary`` — the one paragraph a consumer (or an agent relaying to one) can read to
      pick a level.

    A **write** surface deliberately carries none: a write targets a block or a cell, never
    text, so claiming a projection for it would be a lie.
    """

    summary: str
    object_entry_point: Optional[str] = None
    object_returns: Optional[str] = None
    projection_entry_point: Optional[str] = None
    projection_returns: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "object_entry_point": self.object_entry_point,
            "object_returns": self.object_returns,
            "projection_entry_point": self.projection_entry_point,
            "projection_returns": self.projection_returns,
        }


@dataclass(frozen=True)
class BlockTypeSupport:
    """One docx block type's **READ** support — the three answers a consumer asks about a
    document before reading it, per type.

    The registry projected the **write** side per block type and nothing whatsoever for
    read, so *"will this document's callouts / images / boards survive the read, and what
    will they turn into?"* was unanswerable from shipped material: the block matrix that
    holds the answer is a repository-level document the wheel does not carry, and the one
    packaged block document existed largely to point at it.

    * ``handled`` — is a handler registered for this type. **Derived** from
      :func:`larkdocio.blocks.get_registry` at projection time, never stored, so it cannot
      be a stale copy of the registry. It is also the *only* one of the three a consumer
      could already get, which is why a projection that stopped here would add nothing;
    * ``emits`` — the Markdown the reader produces for a block of this type;
    * ``lossiness`` — one state from the shipped vocabulary
      (:data:`larkdocio.blocks.read_support.LOSSINESS`), and ``lossy`` its boolean
      shorthand, derived from it so the two cannot disagree. A state rather than a bare
      boolean because "lossy" is the same word for a heading that comes back one level
      shallower and for a whiteboard whose pixels are a separate file, and a consumer plans
      differently for each.

    Deliberately carries **no write status**: that axis is the creatable-content floor on
    the write surface, and duplicating it here would rot the moment a type became creatable.
    """

    block_type: int
    name: str
    handled: bool
    emits: str
    lossiness: str
    lossy: bool

    def to_dict(self) -> dict:
        return {
            "block_type": self.block_type,
            "name": self.name,
            "handled": self.handled,
            "emits": self.emits,
            "lossiness": self.lossiness,
            "lossy": self.lossy,
        }


@dataclass(frozen=True)
class BlockReadSupport:
    """A READ surface's **per-block-type** support projection, plus the vocabulary it
    answers in.

    The vocabulary travels with the rows on purpose: a consumer holding only the wheel
    cannot open the document those state names are defined in, so a slug with no shipped
    meaning would be a word they have to guess at. ``unlisted_type`` closes the one hole a
    per-type table structurally cannot: what happens to a block type Lark adds after this
    release.
    """

    summary: str
    projected_from: str
    lossiness_vocabulary: dict  # state -> what it means
    unlisted_type: str
    types: List[BlockTypeSupport]

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "projected_from": self.projected_from,
            "lossiness_vocabulary": dict(self.lossiness_vocabulary),
            "unlisted_type": self.unlisted_type,
            "types": [t.to_dict() for t in self.types],
        }


@dataclass(frozen=True)
class BlockProjectionSupport:
    """A READ surface's **round-trip projection** answer: which block types an edit to the
    projected Markdown can be applied back to, and which the projection only conserves.

    A **fourth axis**, distinct from both the read-support projection above and the write
    surface's creatable floor: a table is creatable *and* readable *and* still conserved,
    because the reader's Markdown for it is a reshaping of the block rather than the
    block's own content. ``contract`` ships the conservation promise itself, because a
    consumer holding only the wheel has nowhere else to read it, and a per-type answer
    with no contract attached is a label rather than a guarantee. ``kinds`` is the
    ``opaque=<kind>`` word each conserved type projects under, so a consumer can key off
    the marker without inferring anything from the block's content.
    """

    summary: str
    contract: str
    projected_from: str
    state_meanings: dict  # state -> what it means
    types: dict  # block_type -> state
    kinds: dict  # block_type -> the opaque= kind (conserved types only)

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "contract": self.contract,
            "projected_from": self.projected_from,
            "state_meanings": dict(self.state_meanings),
            "types": {str(t): s for t, s in sorted(self.types.items())},
            "kinds": {str(t): k for t, k in sorted(self.kinds.items())},
        }


@dataclass(frozen=True)
class Reconciliation:
    """A WRITE surface's **round-trip reconciliation** answer: the entry point that turns
    an edited block-identity projection back into a typed plan, and the vocabulary that
    plan answers in.

    Deliberately **not** an :class:`Operation`. ``operations`` is the plan-gated write
    registry — one entry per request family the engine can compile — and the reconciler
    compiles none of its own: it is an offline diff that produces a plan for those
    families to be built from, so listing it there would say the surface has a seventh
    request family it does not have. It is registered here instead, whole: the states a
    plan can report, the dispositions the caller chooses between, the refusal reasons it
    can answer with, and the contract itself — shipped WITH the answer, because a consumer
    holding only the wheel cannot open the document those rules were written in.
    """

    summary: str
    contract: str
    projected_from: str
    entry_point: str
    returns: str
    state_meanings: dict  # plan state -> what it means
    absent_dispositions: dict  # disposition -> what it means
    refusal_reasons: list  # every reason a reconciliation can answer with
    #: The **write** half: which shipped request families a plan compiles to, where the
    #: compiler is, and what it promises. Still not an ``Operation`` — compiling adds no
    #: request family, it reaches for the ones ``operations`` already lists, which is
    #: exactly what ``compiles_to`` names.
    compiler_entry_point: str = ""
    compiler_contract: str = ""
    compiles_to: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "contract": self.contract,
            "projected_from": self.projected_from,
            "entry_point": self.entry_point,
            "returns": self.returns,
            "state_meanings": dict(self.state_meanings),
            "absent_dispositions": dict(self.absent_dispositions),
            "refusal_reasons": list(self.refusal_reasons),
            "compiler_entry_point": self.compiler_entry_point,
            "compiler_contract": self.compiler_contract,
            "compiles_to": list(self.compiles_to),
        }


@dataclass(frozen=True)
class Workflow:
    """One **compound workflow** — a task a consumer arrives with, indexed at the level the
    discovery order lands on.

    ``operations`` answers *which wire request families exist*; a consumer's question is
    *how do I update a document*. Both are legitimate, and they are not the same question:
    a compound workflow compiles DOWN to request families and mints none of its own, so it
    cannot be an :class:`Operation` without claiming a family that does not exist — which
    is exactly the reason :class:`Reconciliation` states, and that reason is untouched.
    What was missing was the **route**: the registry held the answer under a sibling key
    the reader had no reason to look at.

    So this is an **index, not a description**. The row carries what routes — the task in
    the consumer's own words, the module that performs it, the request families it compiles
    to, the plan gate those go through, the guide sections that teach it — and ``detail``,
    a path to the record that holds the contract. It restates none of that record's text,
    and every field it echoes is **derived** from the record rather than typed a second
    time, so the two cannot drift apart.

    ``evidence_class`` and ``operations_guarantee`` ship **in the output**, not merely in
    this docstring: a row of a different evidence class sitting beside derived operation
    rows is exactly the thing a later reader could mistake for the registry going soft.
    Said out loud, in the payload, it cannot be mistaken for one.
    """

    id: str
    #: The task, in the consumer's words — not the internal verb.
    name: str
    #: The surface this workflow belongs to; the key it is found under in ``surfaces``.
    surface: str
    #: The module a consumer imports to do it. Derived, never typed twice.
    entry_point: str
    #: The shipped request families it compiles DOWN to. Derived, never typed twice.
    compiles_to: List[str]
    #: The safety contracts every one of those requests still goes through — this
    #: surface's own, filtered from its ``safety_contracts``, so a gate that stopped
    #: governing the surface stops being claimed here.
    plan_gate: List[str]
    gate_summary: str
    #: Where the full record lives, as a path a consumer can follow key by key.
    detail: str
    #: Section names for ``guide(section=…)``, the one to read first at the front.
    guide_sections: List[str]
    evidence_class: str
    operations_guarantee: str
    #: The console invocation that performs the whole workflow, or ``None`` when it has no
    #: command-line route and is a library call only.
    #:
    #: **Why a workflow carries this and an operation does not.** ``flags`` already reports
    #: command-line reachability per *switch*, which answers "can I turn this on from a shell"
    #: — and answered nothing at all about "can I *do this task* from a shell", because a task
    #: is not a switch. The gap was invisible while the command line only read; the moment one
    #: workflow shipped as a verb (LD-492) a consumer reading this registry could see the
    #: module to import and could not see that they need not import anything. Derived from the
    #: command's own name, never typed twice.
    command_line: Optional[str] = None

    def __post_init__(self):
        # A workflow with nothing to point at is worse than no workflow row: it says the
        # library can do the task and then routes the reader nowhere. The pointers are
        # DERIVED from the shipped document, so an emptied list means the recipe was
        # deleted or its markers moved — which is a change to disclose, not to publish
        # silently. Refused at construction, so ``capabilities()`` itself reddens.
        if not self.guide_sections:
            raise ValueError(
                f"workflow {self.id!r} points at no guide section — the shipped guide no "
                "longer teaches it, or the symbols it is derived from moved"
            )
        if not self.entry_point:
            raise ValueError(f"workflow {self.id!r} names no entry point")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "surface": self.surface,
            "entry_point": self.entry_point,
            "command_line": self.command_line,
            "compiles_to": list(self.compiles_to),
            "plan_gate": list(self.plan_gate),
            "gate_summary": self.gate_summary,
            "detail": self.detail,
            "guide_sections": list(self.guide_sections),
            "evidence_class": self.evidence_class,
            "operations_guarantee": self.operations_guarantee,
        }

    def to_index_row(self) -> dict:
        """The **stub** a surface carries: enough to know the workflow exists and where the
        row is, and deliberately not the row itself — one authoring, printed twice would be
        two places to keep true."""
        return {
            "id": self.id,
            "name": self.name,
            "see": f"capabilities(full=True)['workflows']['{self.id}']",
        }


@dataclass(frozen=True)
class GateMember:
    """One member of a surface's **live gate ring** — where a capability is proved against
    the real API rather than against a double.

    A safety contract's ``summary`` states what the engine promises; a member states **where
    that promise is kept honest**. The distinction is not academic: ``STALE_DOCUMENT`` can be
    proved offline with an injected transport, but only a real out-of-band editor bumping a
    real ``revision_id`` proves the refusal fires in production — so the member that does it
    is part of the capability, not test trivia.

    * ``id`` / ``module`` — the member's name and the test module that **is** it (the join key
      the drift guard resolves against the test tree: a claimed module that does not exist, or
      does not carry the marker, reddens; a marked module with no row reddens too — that is
      "zero orphans", mechanized);
    * ``summary`` — what the member exercises end to end;
    * ``proves_contracts`` — the surface's own safety-contract ids this member proves **live**
      (guarded against the catalog, so it cannot claim a contract that does not exist);
    * ``arms`` — the separately-named arms inside one member, because a member id alone cannot
      say that a *second* independent proof rides along (the authoring member's
      ``STALE_DOCUMENT-concurrency`` arm is exactly that case);
    * ``marker`` — the pytest marker this member runs under, when it is **not** the ring's own.
      ``None`` (the usual case) means the ring's marker. It exists because one contract cannot
      be proved by a write gate at all: Lark has **no anchored-comment create**, so a
      self-provisioned disposable cannot be given an inline review anchor, and the only honest
      live proof of the reviewer-anchor contract is a **read-only** arm against a document that
      already has real ones. Recording the override is the point — a read-only arm labelled a
      write gate would be a claim about credentials and target policy that is not true of it.
    """

    id: str
    module: str
    summary: str
    proves_contracts: List[str] = field(default_factory=list)
    arms: List[str] = field(default_factory=list)
    marker: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "module": self.module,
            "summary": self.summary,
            "proves_contracts": list(self.proves_contracts),
            "arms": list(self.arms),
        }
        # Emitted only when it really overrides the ring's marker, so every member that runs
        # under the ring's own marker serializes exactly as it did before the field existed.
        if self.marker is not None:
            d["marker"] = self.marker
        return d


@dataclass(frozen=True)
class GateCoverage:
    """How a write surface's contracts are proved **live** — the ring, its command, its
    credentials, and its target policy.

    Answerable from the registry alone: *what do I run to re-prove this surface* (``command``),
    *what does it need* (``credentials_env``), *what does it write to* (``target_policy`` — the
    disposables-only rule), and *what does each member prove* (``members``).
    """

    marker: str
    command: str
    credentials_env: List[str]
    target_policy: str
    members: List[GateMember]

    def to_dict(self) -> dict:
        return {
            "marker": self.marker,
            "command": self.command,
            "credentials_env": list(self.credentials_env),
            "target_policy": self.target_policy,
            "members": [member.to_dict() for member in self.members],
        }


@dataclass(frozen=True)
class Surface:
    """One capability surface (docx/sheets × read/write, plus the embedded deep-read
    bridge): its credentials, opt-in status, gating flags, safety contracts, its
    PROJECTED operation list, (write surfaces) its **file lifecycle** and its
    creatable-content floor, (read surfaces) its **level model**, and — where one exists —
    the **live gate coverage** that proves its contracts against the real API."""

    title: str
    domain: str  # "docx" | "sheets"
    mode: str  # "read" | "write"
    credentials: Credentials
    operations: List[Operation]
    opt_in: bool = False
    gated_by: List[str] = field(default_factory=list)
    #: Other surface ids this one RUNS INSIDE, so its permission requirement genuinely
    #: includes theirs even though none of its own calls names them. The opt-in
    #: embedded-sheet bridge is the case: it fires inside a document read, so the document
    #: scope is part of what it needs. Structural, not a scope assertion — the scope strings
    #: still come from the composed surface's own projected requirement.
    composes: List[str] = field(default_factory=list)
    #: API-using **legs** of this surface that are NOT one of its dispatched operations.
    #:
    #: ``operations`` means one precise thing everywhere it is read — the kinds this
    #: surface's engine dispatches (a write op family, a read client's public op) — and
    #: several guards depend on that meaning. But a surface can own a call site that is not
    #: one of those, and two of them were carrying real, undocumented scope requirements:
    #: the spreadsheet reader's xlsx-export fidelity leg (the only thing that needs the
    #: export scope, and it had no row anywhere), and the spreadsheet writer's PLAN-TIME
    #: leg (building a plan proves an @mention's ids exist with one contacts read, on the
    #: WRITE pair). Projected exactly like an operation, and covered by the permission
    #: registry's coverage guard, so such a leg can never again hold a requirement that is
    #: written down nowhere.
    legs: List[Operation] = field(default_factory=list)
    safety_contracts: List[str] = field(default_factory=list)
    levels: Optional[LevelDescriptor] = None
    content_constraints: Optional[ContentConstraints] = None
    #: A **Base write** surface's field-authoring allow-list — the server's own vocabulary
    #: for what a column can be, plus the authorable-vs-writable quadrants. ``None``
    #: everywhere else, and emitted only when present, so no other surface's serialization
    #: moves by a byte.
    field_authoring: Optional[FieldAuthoringVocabulary] = None
    gate_coverage: Optional[GateCoverage] = None
    #: A READ surface's **per-block-type** support projection (handled / what it emits /
    #: whether it is lossy). ``None`` on a write surface and on a read surface with no block
    #: model of its own, and emitted only when present.
    block_read_support: Optional[BlockReadSupport] = None
    #: A READ surface's **round-trip projection** answer — per block type, editable or
    #: conserved, plus the conservation contract itself. ``None`` wherever there is no
    #: block-identity projection, and emitted only when present.
    block_projection_support: Optional[BlockProjectionSupport] = None
    #: A **WRITE** surface's round-trip reconciliation answer — the offline entry point
    #: that diffs an edited projection back into a typed plan, plus that plan's own
    #: vocabulary and contract. ``None`` wherever there is no reconciler, and emitted only
    #: when present. Not an operation: it compiles no request family of its own.
    reconciliation: Optional[Reconciliation] = None
    #: The **compound workflows** this surface answers — tasks that compile down to its
    #: operations rather than being one of them. Serialized as STUBS (id / name / where the
    #: full row is), because the rows themselves live once, at the registry's top level.
    #: Empty everywhere else, and emitted only when present, so no other surface's
    #: serialization moves by a byte.
    workflows: List[Workflow] = field(default_factory=list)
    #: A **write** surface's file-lifecycle pair (create / destroy the file itself). ``None``
    #: on a read surface, and emitted only when present: a read cannot bring a file into
    #: existence, so claiming a lifecycle for one would be a lie.
    lifecycle: Optional[List[LifecycleOp]] = None
    #: **Contract-level ABSENCES** — operations this surface does not ship, stated where a
    #: consumer asks the question rather than left to be inferred from a list that does not
    #: contain them. Each row carries its ``statement``, its ``verification`` label (the same
    #: vocabulary every other recorded absence uses) and what a caller does ``instead``. The
    #: first row is the docx surface's **no move / reorder operation**: an absence is the
    #: reason a whole-document reorganisation is delete-and-recreate, and a reader who cannot
    #: find it concludes they are holding it wrong. Empty everywhere else, and emitted only
    #: when present, so no other surface's serialization moves by a byte.
    absences: List[dict] = field(default_factory=list)

    #: **THE** enumeration of this surface's callable-bearing AUTHORING fields —
    #: ``(field, kind)``, in the order they serialize. One list, in one place (LD-459): the
    #: serialized answer is derived from it, and :mod:`larkdocio.permissions` walks that
    #: published answer rather than keeping a second copy of these key names. A surface that
    #: grows a fourth kind of call site joins the consumer's answer AND the permission
    #: registry by being added here — and if it is added WITHOUT being added here, the
    #: duck-typed projection audit (:func:`larkdocio.permissions.projection_gaps`) reddens
    #: rather than shipping a call site nobody can find.
    #:
    #: These are three fields **here**, on the typed layer, because they hold different
    #: things: a dispatched :class:`Operation` and a :class:`LifecycleOp` are not the same
    #: shape and never were. They are **one key** in the serialized answer (LD-475) —
    #: :data:`CALL_SITES_KEY`, every row carrying its own ``kind`` — because a *reader* asking
    #: "what can this surface do" was answered by three sibling keys no shipped document
    #: defined and whose set varied per surface, and read the one obvious key.
    CALLABLE_FIELDS = (("operations", "operation"), ("legs", "leg"),
                       ("lifecycle", "lifecycle"))

    def call_sites(self):
        """``[(kind, op)]`` for every callable this surface carries, in serialization order.

        The projection's own answer to *what can this surface do* — complete by construction,
        because it walks :data:`CALLABLE_FIELDS` rather than one key a reader happened to
        think of. It used to be ``operations`` alone, which omitted 20 API-using operations
        (``put_image_in_document`` and ``create_document`` among them) that lived under the
        sibling keys and were findable only by reading the source.
        """
        out = []
        for field_name, kind in self.CALLABLE_FIELDS:
            for op in getattr(self, field_name) or ():
                out.append((kind, op))
        return out

    def to_dict(self) -> dict:
        d = {
            "title": self.title,
            "domain": self.domain,
            "mode": self.mode,
            "opt_in": self.opt_in,
            "gated_by": list(self.gated_by),
            "credentials": self.credentials.to_dict(),
            "safety_contracts": list(self.safety_contracts),
            # THE COMPLETE ANSWER to "what can this surface do", under ONE key (LD-475).
            # Every call site this surface owns is a row here — dispatched operation, API-using
            # leg, and file lifecycle alike — and each row says which ``kind`` it is. There is
            # no sibling key for a verb to hide under, so the reader of the one obvious key
            # cannot miss a shipped one; the three sibling keys this replaced were defined by
            # no shipped document and their set varied per surface.
            CALL_SITES_KEY: [_call_site_row(op, kind) for kind, op in self.call_sites()],
        }
        # Emitted only when it really composes another surface, so every surface that
        # composes nothing serializes exactly as it did before the field existed.
        if self.composes:
            d["composes"] = list(self.composes)
        if self.levels is not None:
            d["levels"] = self.levels.to_dict()
        if self.content_constraints is not None:
            d["content_constraints"] = self.content_constraints.to_dict()
        if self.field_authoring is not None:
            d["field_authoring"] = self.field_authoring.to_dict()
        if self.gate_coverage is not None:
            d["gate_coverage"] = self.gate_coverage.to_dict()
        if self.block_read_support is not None:
            d["block_read_support"] = self.block_read_support.to_dict()
        if self.block_projection_support is not None:
            d["block_projection_support"] = self.block_projection_support.to_dict()
        if self.reconciliation is not None:
            d["reconciliation"] = self.reconciliation.to_dict()
        if self.absences:
            d["absences"] = [dict(row) for row in self.absences]
        if self.workflows:
            d["workflows"] = [w.to_index_row() for w in self.workflows]
        return d


@dataclass(frozen=True)
class Flag:
    """A behavior switch — a CLI flag (``mode="cli"``, e.g. ``--deep-read-sheets``), an
    engine trigger (``mode="engine"``, e.g. the write-gate ``verify_style`` auto-on), or a
    **read configuration knob** (``mode="config"``, e.g. ``resolve_mentions``).

    ``mode="config"`` exists because a knob that is not a CLI flag was, in practice,
    undiscoverable: ``resolve_mentions`` is set through the read ``Config`` (or the shipped
    ``config.json``), is **on** by default, and had no row here at all — so the one flag that
    changes what a read *returns* was the one flag a consumer could not find. ``cli`` then
    carries where the knob is set rather than a flag string.

    ``default`` is the shipped default, and it is load-bearing information: three of these
    are opt-**in** (off), one is opt-**out** (on).
    """

    id: str
    cli: str
    default: bool
    mode: str  # "cli" | "engine" | "config"
    summary: str
    requires: List[str] = field(default_factory=list)
    auto_on: Optional[bool] = None

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "cli": self.cli,
            "default": self.default,
            "mode": self.mode,
            "summary": self.summary,
            "requires": list(self.requires),
        }
        if self.auto_on is not None:
            d["auto_on"] = self.auto_on
        return d


@dataclass(frozen=True)
class SafetyContract:
    """A safety-contract descriptor (plan-gated / dry-run-mandatory / a staleness guard /
    exactly-one-or-refuse) and the surfaces it applies to. ``applies_to`` is the census:
    each surface's published ``safety_contracts`` is derived from it."""

    id: str
    summary: str
    applies_to: List[str]

    def to_dict(self) -> dict:
        return {"id": self.id, "summary": self.summary, "applies_to": list(self.applies_to)}


@dataclass(frozen=True)
class Doc:
    """A packaged **document** and the accessor that reads it.

    Every Markdown document the wheel carries **for a consumer** is reachable through a public
    accessor, and this is where that set is advertised — so finding the guide, the writer's
    brief, the release notes or the changelog does not require knowing ``dir()`` or
    ``importlib.resources``. The one packaged doc with no accessor is the contributor-facing
    ``blocks/BLOCK_TYPES.md``, a named exclusion the accessor-set guard
    (``tests/test_release_notes_accessor.py``) records rather than flags.
    """

    accessor: str
    resource: str
    summary: str
    #: A **document too large to want whole**, indexed by its own headings so a caller can ask
    #: for one part of it. ``None`` — and omitted from :meth:`to_dict` — on a document with no
    #: section accessor, so every other row serializes exactly as it did before the field
    #: existed; the ``Surface.block_read_support`` precedent for an optional field that is
    #: present on one row and a lie anywhere else. Carries **names only, never section text**:
    #: this registry is a dict agents call, and a document body inside it would be a regression.
    sections: Optional[tuple] = None
    #: **That the sections are individually retrievable** — the half of the answer the index
    #: alone never gave (LD-320). ``sections`` listed 72 names and nothing said a caller could
    #: ask for one, so the discoverable move from "this document is 200 KB" to "hand me that
    #: one heading" was left to be guessed. Present exactly where ``sections`` is, and omitted
    #: with it: a document with no section accessor must make no addressability claim.
    section_addressing: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"accessor": self.accessor, "resource": self.resource, "summary": self.summary}
        if self.sections is not None:
            d["sections"] = [dict(row) for row in self.sections]
        if self.section_addressing is not None:
            d["section_addressing"] = self.section_addressing
        return d


@dataclass(frozen=True)
class EntryPoint:
    """A **public top-level symbol** — what you can call from ``import larkdocio`` alone.

    The sibling of :class:`Doc`, and deliberately a different index: ``docs`` answers *"what
    documents does the wheel carry and how do I read them"*, this answers *"what can I call
    from the top level, and what does calling it cost me"*. The distinction is why the advisory
    permission pre-check belongs here and not there — it is not a document.

    ``cost`` is a required field, not a courtesy. The one entry point that spends API calls is
    the pre-check, and a consumer deciding whether to run it needs the price in the same place
    they discover it exists.
    """

    name: str
    kind: str  # "module" | "function"
    summary: str
    cost: str

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "summary": self.summary,
                "cost": self.cost}


@dataclass(frozen=True)
class Capabilities:
    """The whole registry — version + surfaces + flags + safety contracts + packaged docs +
    the public top-level entry points + the compound workflows the surfaces answer."""

    version: str
    surfaces: dict  # id -> Surface
    flags: dict  # id -> Flag
    safety_contracts: dict  # id -> SafetyContract
    docs: dict  # "accessor()" -> Doc
    entry_points: dict  # public name -> EntryPoint
    #: id -> Workflow. COLLECTED from the surfaces rather than authored here, so a workflow
    #: is written down once, beside the surface that answers it.
    workflows: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """The whole registry as JSON-native types — with its permission provenance carried
        ONCE (:mod:`._provenance`).

        The deduplication is a post-pass over the assembled dict rather than a rule the typed
        layer obeys, so nothing above has to know a catalog exists and the catalog keys are
        computed with the whole payload in view. :func:`._provenance.inflate` is its exact
        inverse; the paragraphs are referenced, never dropped.
        """
        return _dedupe_provenance({
            "version": self.version,
            "surfaces": {sid: s.to_dict() for sid, s in self.surfaces.items()},
            "workflows": {wid: w.to_dict() for wid, w in self.workflows.items()},
            "flags": {fid: f.to_dict() for fid, f in self.flags.items()},
            "safety_contracts": {cid: c.to_dict() for cid, c in self.safety_contracts.items()},
            "docs": {did: d.to_dict() for did, d in self.docs.items()},
            "entry_points": {eid: e.to_dict() for eid, e in self.entry_points.items()},
        })


