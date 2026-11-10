"""The projection legs — operations read off the registries, never hand-listed.

LD-244: the verbatim pre-split slice, lines 813-1239 of the
2,770-line ``capabilities.py``. Nothing in it was rewritten.
"""
import dataclasses
import importlib
import inspect
import typing
from typing import List

from larkdocio.roundtrip import COMMAND_NAME as _ROUNDTRIP_COMMAND
from larkdocio.roundtrip import MARKDOWN_FILENAME as _ROUNDTRIP_MARKDOWN
from larkdocio.roundtrip import PHASE_PULL as _ROUNDTRIP_PULL
from larkdocio.roundtrip import PHASE_PUSH as _ROUNDTRIP_PUSH
from larkdocio.sheets.ops import OPS as _SHEETS_WRITE_OPS
from larkdocio.write.encode import CREATABLE_BLOCK_TYPES as _CREATABLE_BLOCK_TYPES
from larkdocio.write.media import (
    OUT_OF_BAND_CREATABLE_BLOCK_TYPES as _OUT_OF_BAND_BLOCK_TYPES,
)
from larkdocio.write.model import InsertRequest as _InsertRequest
from larkdocio.write.model import NewBlockKind as _NewBlockKind
from larkdocio.write.ops import OPS as _DOCX_WRITE_OPS

from . import _resolution
from ._models import (
    BlockProjectionSupport,
    BlockReadSupport,
    BlockTypeSupport,
    ContentConstraints,
    LifecycleOp,
    Operation,
    Reconciliation,
    Workflow,
)

# --------------------------------------------------------------------------- #
# The projection legs — operations come from the registries / clients, never   #
# a hand-list where a registry exists (AC2).                                   #
# --------------------------------------------------------------------------- #

def _public_ops(cls) -> List[str]:
    """The public read-op method names on a client class — non-underscore, and not a
    classmethod/staticmethod construction helper. The notion of a "public op" belongs to
    ``_shipped_read_ops``, in the drift guard of the matrix that lives in the source repository and
    not in the wheel — SHEETS.md — and is reused here so the read projection is guarded
    against the exact same set. Sorted for a deterministic registry."""
    ops = []
    for name, member in inspect.getmembers(cls):
        if name.startswith("_"):
            continue
        raw = cls.__dict__.get(name)
        if isinstance(raw, (classmethod, staticmethod)):
            continue
        if inspect.isfunction(member) or inspect.ismethod(member):
            ops.append(name)
    return sorted(ops)


def _docx_write_operations() -> List[Operation]:
    """Project :data:`larkdocio.write.ops.OPS` — one op per ``OpDescriptor`` (its
    ``kind``, the request class it classifies, and the **anchor kinds** that request family
    accepts, LD-137).

    ``impl`` is the descriptor's own legs — resolve, preview, apply — because what an op
    REQUIRES is the union of what its legs reach: the preview may read where the apply
    writes, and a caller needs both answers before they start.
    """
    return [
        Operation(
            name=desc.kind,
            projected_from="larkdocio.write.ops.OPS",
            resolves_by=_resolution.DESCRIPTORS_BY_KIND,
            request_types=[desc.request_type.__name__],
            anchor_kinds=_docx_anchor_kinds(desc),
            impl=(desc.resolve, desc.preview, desc.apply),
        )
        for desc in _DOCX_WRITE_OPS
    ]


def _sheets_write_operations() -> List[Operation]:
    """Project :data:`larkdocio.sheets.ops.OPS` — one op per ``SheetsOpDescriptor``,
    carrying BOTH projected keyings (``write_kind`` request-side, ``entry_ops``
    entry-side) and its request classes.

    The ``style`` family additionally projects **which cell-style attributes it can set**, off
    :class:`~larkdocio.sheets.requests.CellStyle`'s own fields, plus the one that was probed and
    refuted (LD-189's word-wrap) — see :class:`Operation`'s ``style_fields``.
    """
    return [
        Operation(
            name=desc.kind,
            projected_from="larkdocio.sheets.ops.OPS",
            resolves_by=_resolution.DESCRIPTORS_BY_KIND,
            request_types=[rt.__name__ for rt in desc.request_type],
            write_kind=desc.write_kind,
            entry_ops=list(desc.entry_ops),
            style_fields=_style_fields() if desc.kind == "style" else None,
            style_fields_not_writable=(
                list(NOT_WRITABLE_STYLE_FIELDS) if desc.kind == "style" else None),
            merge_types=_merge_types() if desc.kind == "merge" else None,
            merge_types_refused=(
                _refused_merge_types() if desc.kind == "merge" else None),
            fields_not_read_back=(
                list(NOT_READ_BACK_FIELDS[desc.kind])
                if desc.kind in NOT_READ_BACK_FIELDS else None),
            impl=(desc.preview, desc.apply),
        )
        for desc in _SHEETS_WRITE_OPS
    ]


def _base_write_operations() -> List[Operation]:
    """Project :data:`larkdocio.base.write_ops.WRITE_OPS` — one op per record-write family.

    A **second** registry from the Base read one, deliberately: the read registry answers *"is
    this op set read-only?"* about itself and that answer must stay true, so a mutating
    descriptor could never be appended to it. Each descriptor already names the client method
    that implements it, and ``impl_of`` resolves it — so ``impl`` is the real callable and the
    permission requirement is derived from the code that makes the call, exactly as everywhere
    else here.

    The list is six record families and nothing else. **The schema families are a DIFFERENT
    surface** — they register in their own aggregator and are projected by
    :func:`_base_schema_write_operations` — so this list stays exactly what it has always been:
    the rows. A schema row appearing here would tell a consumer that the record engine can
    change a Base's shape, which it cannot.
    """
    from larkdocio.base.write_ops import WRITE_OPS as _BASE_WRITE_OPS
    from larkdocio.base.write_ops import impl_of as _base_write_impl

    return [
        Operation(
            name=descriptor.name,
            projected_from="larkdocio.base.write_ops.WRITE_OPS",
            resolves_by=_resolution.DESCRIPTORS_BY_NAME,
            request_types=[descriptor.request_cls.__name__],
            impl=_base_write_impl(descriptor),
        )
        for descriptor in _BASE_WRITE_OPS
    ]


def _base_schema_write_operations() -> List[Operation]:
    """Project :func:`larkdocio.base.schema_ops.schema_ops` — every registered SCHEMA op.

    **The third Base op table, and the reason it is a third rather than an append.** The read
    registry ships ``read_only()``, which three landed test modules assert is ``True``, and the
    record-write registry ships ``all_mutate()`` about the rows; a schema descriptor in either
    would flip a shipped statement about a surface that had not changed. So the schema families
    register in their own aggregator, and this projection is the flattening of them — in
    registration order, which is the order a reader meets them: the app and table lifecycle,
    then fields, then views, then the destructive family.

    Projected rather than listed, exactly like every other surface here: the table that
    ENFORCES the op set is the table published, so a family that ships without registering
    cannot appear at the door, and a family that registers cannot ship unpublished.
    """
    from larkdocio.base import schema_ops as _schema_ops

    return [
        Operation(
            name=descriptor.name,
            projected_from="larkdocio.base.schema_ops.schema_ops",
            resolves_by=_resolution.CALLED_DESCRIPTORS_BY_NAME,
            request_types=[descriptor.request_cls.__name__],
            impl=_schema_ops.impl_of(descriptor),
        )
        for descriptor in _schema_ops.schema_ops()
    ]


#: Cell-style attributes **characterized live and found not writable** — the projection's honest
#: other half (LD-189). ``word-wrap`` is here rather than as a ``CellStyle`` field because nine
#: candidate field names all answered ``code 0 "success"`` and landed nothing, exactly like a
#: deliberately nonsense field name did; the evidence is
#: :data:`~larkdocio.sheets.requests.WORD_WRAP_NOT_WRITABLE`.
NOT_WRITABLE_STYLE_FIELDS = ("word-wrap",)


#: Per-family fields larkdocio can WRITE and cannot READ BACK (LD-190). Keyed by op kind, so the
#: projection stays a join rather than a second list of ops. The dropdown's ``options.colors``
#: is the only member: Lark answers with ``options.colorValueMap`` instead, and larkdocio ships
#: no data-validation read leg — the evidence and the consequence are in
#: :data:`~larkdocio.sheets.rich_encode.DROPDOWN_COLORS_NOT_READ_BACK`.
NOT_READ_BACK_FIELDS = {"dropdown": ("options.colors",)}


def _merge_types() -> List[str]:
    """The merge types a merge write accepts, projected off the code's own supported set — so a
    later rung that ships ``MERGE_ROWS`` properly widens this answer by widening that set."""
    from larkdocio.sheets.requests import SUPPORTED_MERGE_TYPES
    return sorted(SUPPORTED_MERGE_TYPES)


def _refused_merge_types() -> List[str]:
    """The variants characterized live and refused — the honest other half of
    :func:`_merge_types`, exactly as ``style_fields_not_writable`` is for the style fields."""
    from larkdocio.sheets.requests import MERGE_VARIANTS_REFUSED
    return list(MERGE_VARIANTS_REFUSED)


def _style_fields() -> List[str]:
    """The settable cell-style attributes, projected off ``CellStyle``'s dataclass fields — so
    "can a style write set a border?" is answered by the code, never by a hand-kept list."""
    from larkdocio.sheets.requests import CellStyle
    return [f.name for f in dataclasses.fields(CellStyle)]


def _lifecycle_operations(cls, projected_from: str, names) -> List[LifecycleOp]:
    """Project a write client's **file-lifecycle** calls off its own ``LIFECYCLE_OPS`` table.

    The table lives beside the methods (the packaged-docs accessor precedent), and each row is
    **resolved** here — so a row naming a method the class does not have raises at projection
    time rather than advertising a call a consumer cannot make. Each row's ``summary`` is that
    method's own first docstring line, which is why the registry cannot drift from the code:
    there is no second description to keep in step.
    """
    ops = []
    for name in names:
        method = getattr(cls, name)  # a phantom row cannot survive this
        lines = (inspect.getdoc(method) or "").strip().splitlines()
        ops.append(LifecycleOp(
            name=name,
            projected_from=projected_from,
            summary=lines[0] if lines else "",
            impl=method,
        ))
    return ops


def _read_operations(cls, projected_from: str) -> List[Operation]:
    """Project a read client's (or the parser's) introspected public ops."""
    return [
        Operation(name=name, projected_from=projected_from, impl=getattr(cls, name))
        for name in _public_ops(cls)
    ]


def _tree_helper_operations() -> List[Operation]:
    """Project the tree-reading helpers off ``larkdocio.model.tree.__all__``.

    A caller who reached the tree still has to read it, and the two functions that do that —
    visiting every block, and reducing one block to its words — are part of what this surface
    can do. Projected off the module's own export list rather than hand-named, so a helper
    added there is reported here without anyone remembering to.
    """
    from larkdocio import model

    return [
        Operation(name=name, projected_from="larkdocio.model.tree",
                  impl=getattr(model.tree, name))
        for name in model.tree.__all__
    ]


def _flatten_content_types(annotation) -> List[type]:
    """The concrete content classes an ``InsertRequest.content`` annotation accepts.

    ``Tuple[X, ...]`` yields ``X`` directly; ``Tuple[Union[X, Y], ...]`` yields both —
    a ``Union`` arg is not itself a ``type``, so it is descended into one level. Written
    as a flatten (rather than a plain ``isinstance(arg, type)`` filter) precisely so
    LD-134's widening of the union widens the projected floor automatically instead of
    silently projecting an EMPTY creatable set.
    """
    out: List[type] = []
    for arg in typing.get_args(annotation):
        if isinstance(arg, type):
            out.append(arg)
            continue
        for inner in typing.get_args(arg):
            if isinstance(inner, type):
                out.append(inner)
    return out


def _flatten_anchor_types(annotation) -> List[type]:
    """The concrete anchor classes an op's **anchor field** annotation accepts (LD-137).

    A bare class annotation *is* the single accepted type (nothing to flatten); a ``Union``
    (``Union[Anchor, AnchorById]``, or the ``NarrativeAnchor`` alias that resolves to one) is
    flattened through :func:`_flatten_content_types`. Written as a flatten for the same reason
    the content projection is: widening a family's anchor union must widen the projection
    **automatically**, so the discovery layer can never advertise an anchor kind the model
    does not accept — or omit one it does.
    """
    if isinstance(annotation, type):
        return [annotation]
    return _flatten_content_types(annotation)


def _docx_anchor_kinds(desc) -> List[str]:
    """The anchor-kind names one docx-write ``OpDescriptor`` accepts, projected off its
    request family's own ``anchor_field`` annotation (never hand-listed)."""
    annotation = typing.get_type_hints(desc.request_type)[desc.anchor_field]
    return sorted(cls.__name__ for cls in _flatten_anchor_types(annotation))


#: Small numbers as English words, so a DERIVED count can sit inside prose without
#: changing the prose's register — and so deriving one leaves a payload whose sha256 is
#: pinned (by an anchor in the development repository) byte-identical. Beyond the table a
#: digit is honest and still correct; the table only has to cover the counts this
#: projection can actually reach.
_COUNT_WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight",
                "nine", "ten", "eleven", "twelve")


def _spelled(count: int) -> str:
    return _COUNT_WORDS[count] if 0 <= count < len(_COUNT_WORDS) else str(count)


def _hostile_types_still_refusing_delete() -> int:
    """How many write-hostile block types still refuse a DELETE — **derived** (LD-634).

    ``WRITE_HOSTILE_NODE_TYPES`` minus ``DELETE_MEASURED_NODE_TYPES``: the measured
    narrowing is excluded **by name**, never by subtracting one, so a second measured type
    or a ninth hostile type moves this number instead of leaving a plausible wrong one.
    The set is guarded fourteen ways; the count this sentence ships used to be hand-typed
    at three sites, and all three would have gone stale together and silently the next time
    the set moved. A number in prose is derived, dated, or not stated.

    Read off the module at call time so the derivation is provable: substitute either tuple
    and the sentence follows.
    """
    # By module, not ``from larkdocio.write import resolve`` — the package exports a
    # ``resolve`` FUNCTION under that same name, which would shadow the module.
    resolve = importlib.import_module("larkdocio.write.resolve")

    return len([node_type for node_type in resolve.WRITE_HOSTILE_NODE_TYPES
                if node_type not in resolve.DELETE_MEASURED_NODE_TYPES])


#: The docx creatable-content floor's **disclosure prose**, relocated out of
#: :func:`_docx_content_constraints` verbatim (LD-633). It was ~200 long English strings
#: inlined into one ``ContentConstraints(...)`` call — 220 lines, 30% of this file and its only
#: outlier, around a projection whose actual logic is ten statements. **Relocated, not
#: rewritten:** every byte of every string is unchanged, which the capabilities payload anchor
#: proves — a pure move leaves ``capabilities(full=True)`` byte-identical, and the anchor moving
#: would have meant a shipped string changed.
#:
#: The lists stay module-level **data**; the projection below copies them into fresh lists per
#: call, so a consumer holding a returned list cannot mutate the next caller's answer.

#: Content that IS creatable, but only through a dedicated out-of-band op (media).
_CREATABLE_OUT_OF_BAND = [
    "an IMAGE in the document body (docx block type 27) — created by "
    "larkdocio.write.media.put_image_in_document, which does the three calls the "
    "route requires as a unit and in this order: create the empty image block, "
    "upload the bytes BOUND TO THAT BLOCK ID, then PATCH replace_image to bind "
    "them. Two traps make it one op rather than three: the BLOCK MUST EXIST BEFORE "
    "THE UPLOAD (an upload parented on the document yields a token no block will "
    "ever accept), and THE UPLOAD ANSWERING SUCCESS IS NOT A BIND (the block's "
    "image token stays empty until the PATCH) — so the verdict is a fresh read-back "
    "of the block, and the bytes are then downloaded again and compared by sha256 "
    "and length. The op returns the block id and the file token. WIDTH AND HEIGHT DO "
    "NOT SURVIVE THE BIND: the create accepts them and replace_image replaces the "
    "whole image property, so the block reads back at the uploaded file's own pixel "
    "size — authored 560x560 read back 2560x2560 (consumer-observed on one day, "
    "four images); authored 120x60 read back 1x1 on a 1x1 PNG (captured, "
    "2026-08-19, one image); passing either logs a warning. NO MEASURED ROUTE "
    "RESIZES IT AFTERWARDS — replace_image with size answers 99992402, update_image "
    "and a bare image property answer 1770001, update_image_scale and "
    "update_block_property were refused too, and every other spelling is "
    "unmeasured, not refuted. THE ONE LEVER THAT WORKS IS TO DOWNSCALE THE BYTES "
    "BEFORE UPLOADING, so the file's own pixel size is the display size — and the "
    "extension can lie while you do it: Lark exports a whiteboard as JPEG bytes "
    "under a .png filename, so dispatch on the bytes' header, not the name (a "
    "warning about the caller's sizing step; this library never inspects image "
    "bytes). Alignment, scale and a caption were never measured as create-time "
    "fields and are not offered; only a PNG has been uploaded, so every other "
    "media kind is unmeasured too. THE UPLOADED MEDIA TOKEN IS PERMANENT RESIDUE — the fact is "
    "stated once, where a teardown is planned: guide('The disposables doctrine — "
    "larkdocio's own test-suite policy, not an engine restriction'), and at the "
    "failure sites the recipes name. THE BLOCK, HOWEVER, IS REMOVABLE — a separate "
    "fact from the token, and MEASURED (2026-08-19): the docx child-delete route "
    "removes an image block and it stays removed (the parent stops listing it and a "
    "direct read answers not found), checked against a same-run control on a text "
    "block in the same parent. So a DeleteRequest anchored by AnchorById(block_id) "
    "resolves; a QUOTE anchor still refuses, because an image carries no quotable "
    "text of its own. Putting the picture back elsewhere is a NEW upload and a "
    "SECOND permanent token. WHETHER A CLIENT "
    "RENDERS the bound image is UNMEASURED — no API call can observe it; what is "
    "measured is that the block carries the token and the bytes round-trip "
    "byte-identical",
    "a FILE ATTACHMENT in the document body (docx block type 23) — created by "
    "larkdocio.write.media.put_file_in_document. SAME ROUTE AS THE IMAGE, PLUS ONE "
    "STEP NOBODY COULD GUESS: the create brings TWO blocks into existence and "
    "answers a TYPE-33 VIEW WRAPPER whose CHILD is the real file block. The wrapper "
    "cannot be created directly and cannot be patched, so the op resolves the "
    "child, reads it back to confirm it is a type-23 block BEFORE any upload "
    "happens, uploads with parent_type docx_file bound to the child, PATCHes "
    "replace_file on the child, re-reads and hash-verifies — and returns the "
    "CHILD's block id, because that is the id anything later must address. IT IS A "
    "DIFFERENT PRODUCT FROM AN INLINE SENTENCE LINK: it is an attachment BLOCK in "
    "the document body. To put a link inside a sentence, upload the file "
    "into a folder with larkdocio.drive.files_write.put_file_in_folder and author "
    "the anchor with NewBlock.rich_paragraph. THE UPLOADED MEDIA TOKEN IS PERMANENT "
    "RESIDUE, exactly as for an image — while a file uploaded into a FOLDER can be "
    "deleted, which is the difference between the two routes; the fact and what it "
    "means for a teardown are stated once, in guide('The disposables doctrine — "
    "larkdocio's own test-suite policy, not an engine restriction'). Only an .html has "
    "been uploaded through this route, so every other file kind is unmeasured, and "
    "WHETHER A CLIENT RENDERS the card is UNMEASURED",
]

#: What this rung cannot create at all — each entry carrying its own reason.
_NOT_CREATABLE = [
    "merged / spanned table cells (colspan / rowspan) — an authored table is "
    "always a plain grid",
    "callout",
    "an image / media upload THROUGH THE PLAN-GATED PATH — a Markdown ![](…) is "
    "refused and no NewBlock kind creates one, because the compiler holds no bytes "
    "and makes no network call. That is a statement about this path, not about the "
    "capability: an image IS creatable out of band, with "
    "larkdocio.write.media.put_image_in_document — see creatable_out_of_band",
    "board / whiteboard",
    "AN IN-PLACE UPDATE OF A MERMAID DIAGRAM (docx block type 40) — the diagram "
    "itself IS creatable (see creatable_kinds: mermaid), but the docx block-patch "
    "surface carries no add_ons updater at all, so a diagram's source cannot be "
    "edited in place. Changing one means DELETE the block and CREATE a new one at "
    "the same index, which gives it a NEW block_id: caching a type-40 block id "
    "across an edit is therefore unsound, and an anchor held over a diagram edit "
    "must be re-resolved",
    "embed (iframe / Base / Sheet)",
    "grid / column layout",
    "colors (text or background)",
    "styled runs on created text — with ONE exception, the LINK ANCHOR. Bold, "
    "italic, strikethrough, inline code and colour on a created run stay "
    "unauthorable: they are not fields on a TextSpan, so they are inexpressible by "
    "construction rather than refused at runtime. A LINK IS AUTHORABLE: "
    "NewBlock.rich_paragraph takes a sequence of TextSpan values and a span "
    "carrying link_url becomes a created run with text_element_style.link.url — "
    "which is how a sentence gets an anchor whose text is not the URL. A TABLE CELL "
    "TAKES THE SAME SPANS: a cell in NewBlock.table's rows is a plain string OR a "
    "sequence of TextSpan, and the Markdown dialect composes a [label](url) in that "
    "one position too. The URL is "
    "authored VERBATIM and a percent-encoded spelling is refused, because the "
    "reader percent-decodes a link URL on the way back out and an encoded spelling "
    "would not survive the round trip. Outside a table cell the Markdown compiler "
    "still refuses [text](url): the typed shape is deliberately not reached through "
    "the dialect there",
    "a styled run other than a link inside a table cell — NARROWED from an entry "
    "that read 'an anchored link inside a table cell', and the REASON that entry "
    "gave survives in the two clauses below; only its conclusion about the LINK has "
    "moved, because the platform was measured. A link-carrying run inside a docx "
    "table cell is accepted and STORED by Lark on both of the routes this library "
    "creates cells by, read back fresh rather than inferred from a create's success "
    "code — so an anchor in a cell IS creatable, authored as a TextSpan sequence in "
    "NewBlock.table's rows or as a [label](url) through the dialect. What is still "
    "not creatable in a cell is every OTHER run styling (bold, italic, "
    "strikethrough, inline code, underline, colour): none of them is a field on a "
    "TextSpan, so they are inexpressible by construction, and none of them was "
    "measured in a cell. And the anchor is a CREATE-time capability only: a cell's "
    "text is editable, but only as text — EditRequest carries a plain "
    "`replacement: str` and no spans at all, so a TableLocator-anchored edit cannot "
    "carry link_url, and the span-level path that could, SubSpanEditRequest, takes "
    "a NarrativeAnchor whose own contract puts a sub-span within a table cell out of "
    "scope. So a later whole-cell patch replaces an anchored cell with plain text",
]

#: The asymmetry: content an EDIT reaches that a CREATE cannot author.
_EDITABLE_NOT_CREATABLE = [
    "a MERGED table — it reads (as HTML) and its unmerged cells edit via a "
    "TableLocator anchor, but no merge can be authored: Markdown has no "
    "colspan/rowspan, so an authoring request implying a span is refused "
    "(merge-not-expressible), never approximated",
    "styled runs inside a block — an existing block's bold / italic / link "
    "survive a sub-span edit; created text carries EXACTLY ONE styling, the LINK "
    "ANCHOR (a TextSpan carrying link_url, through NewBlock.rich_paragraph), and "
    "is otherwise unstyled. A created table's CELLS reach exactly that one styling "
    "and no other: a cell authored as a TextSpan sequence carries the anchor, "
    "measured accepted and stored by Lark on both write routes. SUPERSEDED IN PART, "
    "reason preserved: this clause used to end 'the anchor included', on the reason "
    "that a cell reaches no styling — which stands for every styling except the "
    "anchor. And it stands for the EDIT direction without exception: a whole-cell "
    "patch replaces a cell with plain text, so an anchor that was created in a cell "
    "does not survive one",
    "a block a reviewer has commented INSIDE — a sub-span edit re-emits each "
    "rebuilt run's inline comment anchors, so it can edit such a block, but a "
    "WHOLE-BLOCK edit of one is refused (comment-anchors-present): the whole-block "
    "rebuild collapses the block to a single run, leaving per-passage anchors "
    "nowhere to attach, and the refusal's detail names the sub-span edit as the "
    "recovery. No flag overrides it; a block-LEVEL comment does not trigger it. "
    "A WHOLE-CELL (TableLocator) edit is refused on the same collapse, judged on "
    "the inline anchors of the cell's inner text block — the one block the patch "
    "rewrites — with a detail naming the row and column and, as the recovery, a "
    "sub-span edit anchored by that inner block's id (a row-key-and-column locator "
    "cannot name a span). "
    "Anchors themselves are never creatable — Lark's API has no anchored-comment "
    "create at all",
]

#: The floor's one-paragraph summary. A **template**, not an f-string, for one reason: its one
#: number is DERIVED and must be derived **at call time** (see
#: :func:`_hostile_types_still_refusing_delete` — reading the module at call time is what makes
#: the derivation provable), so interpolating it at import time would freeze it.
_FLOOR_TEMPLATE = (
    "CREATABLE CONTENT: a NewBlock of kind heading (level 1-9), paragraph, "
    "bullet / ordered / todo list item (NESTED, to a documented depth cap), code "
    "block (with a language), quote, or TABLE (an R x C grid whose cells are each "
    "plain text OR a TextSpan sequence carrying a link anchor, with an optional "
    "header row, to a documented cell cap) — plus the legacy "
    "NewParagraph (a plain paragraph, still valid and equivalent to "
    "kind=paragraph). Created text carries ONE styling and no other — the LINK "
    "ANCHOR, authored as a TextSpan with link_url through NewBlock.rich_paragraph. "
    "A created TABLE's cells reach that one styling too and no other: a cell "
    "authored as a TextSpan sequence carries the anchor (Lark was measured to "
    "accept and STORE the link-carrying run inside a docx table cell on both write "
    "routes), and the Markdown dialect composes a [label](url) in that one position. "
    "What a cell still cannot reach is any OTHER run styling, and the anchor is "
    "create-time only: a TableLocator-anchored edit carries a plain replacement "
    "string with no spans, so a later whole-cell patch replaces it with plain text "
    "(see not_creatable) — or a "
    "MERMAID DIAGRAM (docx block type 40, an add_ons block), taking "
    "already-compiled Mermaid source plus an optional theme; compile a structured "
    "spec to that source with larkdocio.mermaid.flowchart / .sequence. A DIAGRAM IS "
    "CREATE-ONLY: there is no add_ons updater on the docx block-patch surface, so "
    "editing one means DELETE + CREATE at the same index and the block_id CHANGES "
    "(do not cache a type-40 block id across an edit). Because a diagram is "
    "creatable, a ```mermaid fence the reader emitted composes back through "
    "compose(), so a document containing a diagram round-trips. NOT creatable in "
    "this rung: MERGED table cells, a callout, images / "
    "media, boards, embeds (iframe / Base / Sheet), grids and colors — each a "
    "future rung, never silently approximated. ONE OF THOSE HAS AN OUT-OF-BAND "
    "ROUTE: an image is not creatable HERE (the compiler holds no bytes) but IS "
    "creatable by a dedicated op — see creatable_out_of_band. TABLE HEADER ROW: header_row "
    "defaults True and is stored either way, but Lark omits a FALSE flag from the "
    "payload it returns and the reader renders an absent flag as promoted, so a "
    "header_row=False table reads back through Markdown with row 0 as the header "
    "(lossiness in the Markdown projection, not in the write). EDITABLE IS NOT "
    "CREATABLE: a "
    "merged table reads and its unmerged cells edit while no merge can be "
    "authored, and WRITE_HOSTILE_NODE_TYPES lists only what refuses an EDIT — it "
    "is not a list of what can be created, and it is not a list of what refuses a "
    "DELETE either: an IMAGE block deletes through the ordinary plan gate when it is "
    "anchored by AnchorById (measured 2026-08-19), while the other "
    "{hostile_delete_refusals} types on "
    "that list still refuse delete because their delete is UNMEASURED, NOT REFUTED. "
    "The not-creatable set is structurally "
    "inexpressible: NewBlockKind is a CLOSED enum and NewBlock carries no "
    "block-type escape, image token, embed url, sheet reference or cell-span "
    "field to smuggle a richer shape through."
)

def _docx_content_constraints() -> ContentConstraints:
    """Project the docx-write **creatable-content floor** off ``write/`` code truth.

    ``creatable`` comes from the type args of ``InsertRequest.content`` (the one field
    through which any content is created) and ``creatable_content_fields`` from those
    types' own dataclass fields — so the projection cannot claim a richer floor than the
    model actually accepts. ``creatable_kinds`` comes off the closed ``NewBlockKind`` enum
    and ``creatable_block_types`` off the encoder's ``CREATABLE_BLOCK_TYPES`` (LD-138), so
    the floor answers *which kinds* and *which docx block types* — the two questions the
    container-type list cannot. The prose lists state what those facts *mean* for a
    consumer planning an integration.
    """
    hints = typing.get_type_hints(_InsertRequest)
    creatable_types = _flatten_content_types(hints["content"])
    fields: List[str] = []
    for cls in sorted(creatable_types, key=lambda c: c.__name__):
        for f in dataclasses.fields(cls) if dataclasses.is_dataclass(cls) else ():
            if f.name not in fields:
                fields.append(f.name)
    return ContentConstraints(
        creatable=sorted(cls.__name__ for cls in creatable_types),
        creatable_kinds=sorted(kind.value for kind in _NewBlockKind),
        creatable_block_types=sorted(_CREATABLE_BLOCK_TYPES),
        creatable_out_of_band=list(_CREATABLE_OUT_OF_BAND),
        creatable_out_of_band_block_types=sorted(_OUT_OF_BAND_BLOCK_TYPES),
        creatable_content_fields=fields,
        not_creatable=list(_NOT_CREATABLE),
        editable_not_creatable=list(_EDITABLE_NOT_CREATABLE),
        floor=_FLOOR_TEMPLATE.format(
            hostile_delete_refusals=_spelled(_hostile_types_still_refusing_delete())),
        projected_from="larkdocio.write.model.InsertRequest.content",
        kinds_projected_from="larkdocio.write.model.NewBlockKind",
        block_types_projected_from="larkdocio.write.encode.CREATABLE_BLOCK_TYPES",
        out_of_band_projected_from=(
            "larkdocio.write.media.OUT_OF_BAND_CREATABLE_BLOCK_TYPES"),
    )


def _docx_block_read_support() -> BlockReadSupport:
    """Project the **per-block-type READ** answer — handled / what it emits / how lossy.

    A join, not a list: ``handled`` comes from the live handler registry and the other two
    answers come from the table that sits beside the handlers
    (:data:`larkdocio.blocks.read_support.READ_SUPPORT`, itself pinned cell-for-cell against
    the block matrix in the development repository).

    **A registered handler with no row cannot survive this.** The registry is the direction
    an omission hides in — a new handler simply would not appear — so the join is checked
    here and raises rather than shipping a projection that silently under-reports what the
    reader handles. It is the same posture the packaged-docs projection takes on a phantom
    row, turned on the opposite direction. Imported inside the function because this module
    is imported while the package is still initializing.
    """
    from larkdocio.blocks import get_registry
    from larkdocio.blocks import read_support

    handled = set(get_registry())
    rows = [
        BlockTypeSupport(
            block_type=block_type,
            name=name,
            handled=block_type in handled,
            emits=emits,
            lossiness=lossiness,
            lossy=lossiness != "full",
        )
        for block_type, name, lossiness, emits in read_support.READ_SUPPORT
    ]
    orphans = sorted(handled - {row.block_type for row in rows})
    if orphans:
        raise RuntimeError(
            "larkdocio.blocks.read_support.READ_SUPPORT has no row for registered block "
            f"types {orphans} — a handler cannot ship without its read-support row (add "
            "the row to the block matrix and to that table)."
        )
    return BlockReadSupport(
        summary=read_support.SUMMARY,
        projected_from=(
            "larkdocio.blocks.get_registry (handled) + "
            "larkdocio.blocks.read_support.READ_SUPPORT (emission + lossiness)"
        ),
        lossiness_vocabulary={state: meaning for state, meaning in read_support.LOSSINESS},
        unlisted_type=read_support.UNLISTED_TYPE,
        types=rows,
    )


def _docx_block_projection_support() -> BlockProjectionSupport:
    """Project the **round-trip** answer — per block type, editable or conserved.

    Nothing is stored: the states come straight off
    :func:`larkdocio.model.conservation.projection_support`, which is itself a live join
    of the handler registry, the write encoder's creatable set and the shipped
    read-lossiness. Imported inside the function for the same reason its neighbour is.
    """
    from larkdocio.model import conservation

    states = conservation.projection_support()
    return BlockProjectionSupport(
        summary=(
            "Per docx block type: when a document is projected for round-trip editing "
            "(project_block_ids), can an edit to this block's Markdown be applied back "
            "to it, or is the block conserved? A block that is conserved carries "
            "'<!-- lark:block:<id> opaque=<kind> -->' and is covered by the "
            "conservation contract below."
        ),
        contract=conservation.CONSERVATION_CONTRACT,
        projected_from=(
            "larkdocio.model.conservation.projection_support (a join of "
            "larkdocio.blocks.get_registry, larkdocio.write.encode."
            "CREATABLE_BLOCK_TYPES and larkdocio.blocks.read_support.READ_SUPPORT)"
        ),
        state_meanings=dict(conservation.PROJECTION_STATE_MEANINGS),
        types=dict(states),
        kinds={
            block_type: conservation.opaque_kind(block_type)
            for block_type in sorted(conservation.opaque_block_types())
        },
    )


def _docx_reconciliation() -> Reconciliation:
    """Project the docx write surface's round-trip reconciliation answer.

    Every value comes off the reconciler's own module — the plan's state vocabulary, the
    disposition vocabulary, the refusal reasons it can answer with and the contract text
    itself — so the registry cannot describe a reconciler other than the one that ships.
    Imported inside the function for the same reason its neighbours are.
    """
    # From the MODULE path, not the package: ``larkdocio.write.reconcile`` is re-exported
    # as the function, which would shadow the module on a package-level import.
    from larkdocio.write.compiler import (
        COMPILED_REQUEST_FAMILIES,
        RECONCILIATION_COMPILER_CONTRACT,
    )
    from larkdocio.write.reconcile import (
        ABSENT_DISPOSITION_MEANINGS,
        RECONCILIATION_CONTRACT,
        RECONCILIATION_REFUSAL_REASONS,
        RECONCILIATION_STATE_MEANINGS,
    )

    return Reconciliation(
        summary=(
            "Hand back an edited block-identity projection and get a typed, frozen, "
            "JSON-serializable plan saying, per block, whether it is unchanged, edited, "
            "newly inserted, deleted or conserved — before anything is applied. Offline: "
            "it makes no network call and issues no request."
        ),
        contract=RECONCILIATION_CONTRACT,
        projected_from="larkdocio.write.reconcile",
        entry_point="larkdocio.write.reconcile",
        returns="ReconciliationPlan",
        state_meanings=dict(RECONCILIATION_STATE_MEANINGS),
        absent_dispositions=dict(ABSENT_DISPOSITION_MEANINGS),
        refusal_reasons=[r.value for r in RECONCILIATION_REFUSAL_REASONS],
        compiler_entry_point="larkdocio.write.compiler",
        compiler_contract=RECONCILIATION_COMPILER_CONTRACT,
        # Off the compiler's own tuple of real classes, so a family it stopped compiling —
        # or a fourth one it started — cannot be described here without being true.
        compiles_to=[family.__name__ for family in COMPILED_REQUEST_FAMILIES],
    )


#: What kind of claim a workflow row is — shipped IN the payload, because a row of a
#: different evidence class sitting beside derived operation rows is precisely the thing a
#: later reader could mistake for the registry having gone soft.
WORKFLOW_EVIDENCE_CLASS = (
    "DESCRIPTIVE and guide-pointer-shaped — NOT endpoint-derived. A workflow row is a "
    "ROUTING answer: it names a task, the module that performs it, the request families it "
    "compiles down to, the plan gate those go through, and the guide sections that teach "
    "it. It asserts no endpoint, no scope and no request family of its own, and it is not "
    "projected off a call site the way an operation's row is. Every field it echoes is "
    "derived from the record named in 'detail', so it cannot drift from it."
)

#: And the guarantee that is NOT weakened by the row above — stated, not left to trust.
WORKFLOW_OPERATIONS_GUARANTEE = (
    "The operations lists keep their projection guarantee UNDIMINISHED. An operation is "
    "still exactly one wire request family, still projected off the code that dispatches "
    "it, and still guarded bidirectionally — an API-using call site with no permission row "
    "reddens, and a row whose call site has vanished reddens. This section adds a way to "
    "FIND a compound workflow; it adds nothing to any operations list, and changes nothing "
    "about what being in one means."
)

#: The plan-gate contracts a compound workflow's compiled requests still pass through. The
#: row claims only the ones its own surface actually lists, so a gate that stopped
#: governing the surface stops being claimed here.
_PLAN_GATE_CONTRACTS = ("plan-gated", "dry-run-mandatory", "exactly-one-or-refuse")

#: What IDENTIFIES a guide section as teaching the docx update round trip: **both** halves
#: of it, so a section that mentions the reconciler in passing is not claimed as teaching it.
#: Symbols, not section names — the section names are derived from the document itself (a
#: section name written down in ``src/`` is exactly what this repo forbids), which is also
#: what makes a heading rename move the pointer instead of dangling it.
_DOCX_UPDATE_TEACHING_SYMBOLS = ("reconcile(", "compile_reconciliation(")


def _docx_update_guide_sections() -> List[str]:
    """The shipped guide's sections that teach the docx update round trip, in document
    order — the one to read first at the front, because that is the order the guide itself
    puts them in."""
    from larkdocio.guide import GUIDE_RESOURCE, _packaged, _sections_teaching

    return list(_sections_teaching(_packaged(GUIDE_RESOURCE), _DOCX_UPDATE_TEACHING_SYMBOLS))


def _docx_update_workflow(
    surface_id: str, reconciliation: Reconciliation, safety_contracts,
) -> Workflow:
    """Index the docx write surface's reconciliation record as the compound workflow a
    consumer actually arrives with: *update a document that already has content*.

    Everything that could disagree with the record is taken FROM the record — the entry
    point and the request families it compiles to — and the contract text is not repeated
    at all, only pointed at. The gate list is filtered from the surface's own contracts for
    the same reason.
    """
    return Workflow(
        id="update-a-document-that-already-has-content",
        name=(
            "update a document that already has content — change or edit many blocks at "
            "once, without re-authoring it"
        ),
        surface=surface_id,
        entry_point=reconciliation.entry_point,
        # THE COMMAND-LINE ROUTE, derived from the verb's own name (LD-492). This workflow is
        # the one the packaged guide's file-first recipe teaches, and it now ships as a
        # console verb as well as a library call — so the registry says so rather than
        # leaving a consumer to conclude from `entry_point` that Python is the only way in.
        # The two phases are named because a single-invocation reading of this verb would be
        # wrong: the caller's edit happens BETWEEN them.
        command_line=(
            f"larkdocio {_ROUNDTRIP_COMMAND} {_ROUNDTRIP_PULL} \"<url>\" -o <dir>  →  "
            f"edit <dir>/{_ROUNDTRIP_MARKDOWN}  →  "
            f"larkdocio {_ROUNDTRIP_COMMAND} {_ROUNDTRIP_PUSH} -o <dir> [--apply]"
        ),
        compiles_to=list(reconciliation.compiles_to),
        plan_gate=[c for c in safety_contracts if c in _PLAN_GATE_CONTRACTS],
        gate_summary=(
            "It mints NO request family of its own: it diffs offline, then compiles to the "
            "families named in 'compiles_to' and hands them to this surface's ONE plan "
            "gate — nothing is applied until a plan has been built and dry-run, and each "
            "request in it is exactly-one-or-refuse. That is why it is indexed here rather "
            "than listed as an operation, and why using it is not a second write path."
        ),
        detail=f"capabilities(full=True)['surfaces']['{surface_id}']['reconciliation']",
        guide_sections=_docx_update_guide_sections(),
        evidence_class=WORKFLOW_EVIDENCE_CLASS,
        operations_guarantee=WORKFLOW_OPERATIONS_GUARANTEE,
    )


