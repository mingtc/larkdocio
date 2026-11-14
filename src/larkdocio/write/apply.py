"""larkdocio.write.apply — the plan-gated apply engine: the only code that writes docx.

:func:`apply` executes an **approved dry-run plan** (LD-067) against Lark. It is the
single write seam of the whole ladder — **eight** reachable apply implementations ride this
one plan-gated pipeline, each with its own live re-validation and each producing exactly one
apply-log record:

* **whole-paragraph** edits (W1 / LD-068) → :func:`_apply_narrative`; re-validation via the
  shared :func:`_revalidated_or_stale`;
* **table-cell** patches (W2 / LD-072) → :func:`_apply_table_cell`, the DOUBLE check;
* **insert** (W3 / LD-076) → :func:`_apply_insert`, incl. the typed creatable-content
  family (LD-134) and table creation (LD-135);
* **delete** (W3 / LD-076) → :func:`_apply_delete`, destructive-safe;
* style-preserving **sub-span** edits (W3 / LD-077) → :func:`_apply_subspan`, re-validating
  the span's own offsets;
* **table grow** (LD-575) → :func:`_apply_grow_table`; it re-reads the live block and refuses
  ``stale-anchor`` **inline** when the block is no longer a table — its own re-validation, not
  the shared helper's, because appending a row does not depend on the current row count;
* **comment create** (LD-202) → :func:`~larkdocio.write.comments._apply_comment_create`; a
  **whole-document** comment, which has **no anchor to re-validate by construction**;
* **comment remove** (LD-202) → :func:`~larkdocio.write.comments._apply_comment_remove`, whose
  read → judge → delete sequence **is** the validation (every reply must be this
  application's own, decided before the first delete).

**THE COUNTING BASIS IS DECLARED, so a second reading cannot start.** Eight is *every
apply implementation reachable through the* :data:`larkdocio.write.ops.OPS` *dispatch* —
``_apply_edit`` counts as its two leaves (narrative and table-cell). The registry holds
**seven** op kinds, and counting those would undercount the dispatch by one and so certify a
path it never counted; the two predicates above are a **safety** claim, and the unit a safety
claim about writing must count is the implementation that touches the caller's document, not
the op kind that names it. Excluding the two comment ops (six) would leave two genuinely
writing paths outside a guarantee whose whole value is being exhaustive. **The number is not
hand-kept**: it is derived by one helper, in the source repository rather than in the wheel —
``tests/test_write_registration_seam.py::reachable_apply_implementations`` — which holds this
sentence and this list to the registry. The sentence above went stale for 35 days across two
op additions before that guard existed.

**And re-validation is a PROPERTY, never a helper call.** Three of the eight satisfy it
without :func:`_revalidated_or_stale`, as their bullets state; a census of *who calls the
helper* over these produces a confident, wrong *"three write paths skip the staleness gate"*
(measured: all eight validate appropriately, and there is no
safety gap). Read each path's bullet for its own answer.

Every text-replacing path patches via the W0 :class:`~larkdocio.write.client.WriteClient`
with an **element-level** ``update_text_elements`` body whose runs are rebuilt with the
style-preserving :func:`~larkdocio.write.client.to_write_elements` pattern — never a
lossy Markdown round-trip. For a whole-block edit the granularity is **whole-paragraph**
(§ Decision (d), maintainer-settled for phase 1): the replacement is the *entire* new paragraph
text as a single run, and a uniformly-styled paragraph keeps the leading run's style
(bold / italic / inline_code / strikethrough / underline / text_color /
background_color / link). Per-span styling is the sub-span path's business (W3), which
splits the matched run(s) and mutates only the span.

**Inline comment anchors ride with their run, and the three text paths differ.** A sub-span
edit splits at the span boundaries and every rebuilt run re-emits the ``comment_ids`` its
source run carried, so a sub-span edit's replacement run takes its region's anchors and a
run the split does not touch comes through anchors and all (a span whose runs disagree
about their anchors is refused instead — ``span-not-splittable`` — rather than guessing
which passage a reviewer meant). A whole-block edit collapses the block to one run, where
per-passage anchors have nowhere to attach, so it is **refused at plan time**
(``comment-anchors-present``) with the sub-span edit named as the way through. A whole-cell
edit rides that same collapse on the cell's inner text block, so it is **refused at plan
time too** when *that* block carries inline comment anchors — its ``detail`` names the row
and column and, since a cell locator cannot express a span, the sub-span edit anchored by
the inner block's id. What Lark does with the anchors a patch sends is Lark's own behaviour;
what these paths answer for is the payload.

**The hard gate (co-verified with LD-067's AC3).** :func:`apply` accepts **only** a
:class:`~larkdocio.write.preview.Plan` produced by
:func:`~larkdocio.write.preview.dry_run` — a bag of raw
:class:`~larkdocio.write.model.EditRequest`s can never reach it (a non-``Plan`` argument
raises :class:`TypeError`), and a ``Plan`` itself is non-forgeable (its constructor is
token-guarded), so there is structurally no path that applies an unresolved edit.

**Stale-anchor safety (§ Decision (e)).** docx writes default to
``document_revision_id=-1`` ("latest") — **not** a compare-and-swap lock (the spike's
load-bearing warning). So immediately before each write the engine
:meth:`~larkdocio.write.client.WriteClient.get_block`s the target and re-validates it; on
drift it **refuses with ``stale-anchor`` and skips** (no write). The re-validation is the
**anchor's own** (:func:`_stale_if_drifted`): a quote+breadcrumb anchor requires its **quote
to still be a substring** of the live text (W1, unchanged), while an
:class:`~larkdocio.write.model.AnchorById` — which has no quote, and whose id cannot come to
mean a different block — requires the block's live text to still **equal** what the plan
captured, i.e. a **compare-and-swap on the anchored block** (LD-137). A block that cannot be
re-read at all (the amplifier's stale race: deleted between plan and apply) likewise refuses
``stale-anchor`` rather than aborting the batch (:func:`_live_or_stale`). Every processed edit
— applied *or* refused — produces one :class:`~larkdocio.write.model.ApplyLogEntry`, returned
as an :class:`~larkdocio.write.model.ApplyLog`.

Those two halves — the live read and the anchor's own precondition — are composed **once**,
in :func:`_revalidated_or_stale`, which is the whole opening of the narrative / insert /
delete paths (LD-142). Sub-span and table-cell deliberately keep their own, different
re-validation (the span's own offsets; the row-identity + cell-content double read).

**Whole-document staleness (LD-139, D9).** Above the per-entry check sits an
optional whole-**document** compare-and-swap: when the plan carries a
``document_revision_id``, :func:`_document_cas` re-reads the document's revision once before
the batch and refuses the **entire** batch (``stale-document``, **zero** writes) if it moved —
the only way to catch drift *around* an anchor, where a per-entry check is structurally blind.
Its absence is never silent: the plan is marked ``revision_guard: "unavailable"`` with the WHY.

Writes are **throttled** because they route through the W0 ``WriteClient`` (which paces
every call through :class:`~larkdocio.common.transport.WriteTransport`); the engine never
opens a socket of its own. It touches **no** reader/model/render surface — reader Markdown
stays byte-identical (§ Decision (h)). The binding end-to-end gate is the live write
round-trip against a harness-provisioned disposable doc (``pytest -m live_write``).

**W2 / LD-072 — table-cell edits** ride the **same** plan-gated pipeline (no parallel
path). A resolved entry carrying a :class:`~larkdocio.write.resolve.ResolvedCell` (the S2
table resolver attached it) is dispatched to :func:`_apply_table_cell`, which patches the
cell's **inner text block** with the identical whole-block ``update_text_elements`` path a
paragraph uses (spike Test 5 — a cell patches like a paragraph; no new endpoint). Its
stale-anchor check is a **DOUBLE** re-validation, stricter than the narrative single check
(Decision f): the **key cell** (row identity — ``row_key`` still matches) **and**
the **target cell** (content unchanged since capture) are both re-read live, and **either**
drift → ``stale-anchor`` skip.

**W3 / LD-076 — insert / delete** also ride the same plan-gated pipeline (no new
endpoints — the raw W0 :meth:`~larkdocio.write.client.WriteClient.create_children` /
:meth:`~larkdocio.write.client.WriteClient.batch_delete` lifted into the gate). A resolved
**insert** entry → :func:`_apply_insert`: re-validate the reference (the anchor's own
precondition — quote still a substring, or the id's compare-and-swap), then create the
request's typed content at the plan's **computed insertion point** (parent + index
derived from the resolved reference at S2 —
before/after/append-into); the apply-log records the created block id(s). A resolved
**delete** entry → :func:`_apply_delete`: re-validate the target, then — because deletion
is **destructive** — capture the target's **full removed-block payload** (elements +
per-run style + block-level style) *before* removing it, so the destructive edit stays
reconstructable (Decision (c)), and ``batch_delete`` the single contiguous child
range located off the **live** parent's child order. Losing that payload is a FAIL.

**Creatable content (LD-134).** An insert's content is the typed
:class:`~larkdocio.write.model.NewBlock` family (heading / paragraph / bullet / ordered /
todo / code / quote, lists nestable) plus the legacy
:class:`~larkdocio.write.model.NewParagraph`; :mod:`larkdocio.write.encode` turns it into
real ``create_children`` payloads and, because that endpoint creates **one level deep**, a
nested tree is issued as **one call per parent** with each deeper call parented on the real
id Lark returned. Flat content stays exactly one call with a byte-identical body.

**The ONE-CALL table route (LD-482), and the one thing it is used for.** The
``descendant`` endpoint — a whole subtree in one call via a caller-minted temp-id map — was
this module's "documented future optimization" from LD-134 until LD-481's spike measured it
at real scale. It is now the route an insert takes when its content is **exactly one table
that fits the measured one-call envelope**
(:func:`~larkdocio.write.encode.fits_one_call` — ``2 × cells + 1 ≤ 1000``, so ≤ 499 cells),
and it is used for **nothing else**: a general subtree-authoring route over the other kinds
is a larger question this deliberately does not answer, and mixed content still goes through
``create_children`` unchanged. See :func:`_insert_table_in_one_call` for why the boundary is
drawn exactly there — placement, not appetite.

**Table creation (LD-135) — the one two-step create.** A table's ``create_children`` payload
is its **grid property** (``row_size`` / ``column_size`` / ``header_row``), and Lark
**auto-provisions the cell family** from it (each cell type 32 wrapping one inner text block
type 2 — the shape the W2 gate live-proved). So after the create, :func:`_fill_table_cells`
writes each authored cell by patching that inner block with the **same**
:func:`build_whole_paragraph_update` body a whole-cell edit uses: no new endpoint, no second
patch shape, and the whole table family lands through this one insert entry. An empty
authored cell is skipped (already provisioned empty), a cell that arrives without an inner
block gets one created rather than dropping the text, and a grid smaller than the one
requested raises instead of silently truncating the consumer's table.
"""
from contextlib import contextmanager
from typing import Dict, List, Optional

from larkdocio.common.transport import is_credential_rejection
from larkdocio.errors import (
    LarkAPIError,
    LarkPermissionError,
    LarkRateLimitError,
    gate_refusals,
)
from larkdocio.write.client import (
    MAX_BATCH_UPDATES_PER_CALL,
    WriteClient,
    text_block,
    to_write_elements,
)
from larkdocio.write.encode import (
    MAX_CREATE_GRID_AXIS,
    TABLE_BLOCK_TYPE,
    create_batches,
    encode_content,
    fits_one_call,
    span_elements,
    table_subtree,
)
from larkdocio.write.model import (
    AnchorById,
    ApplyLog,
    ApplyLogEntry,
    InsertPosition,
    Refusal,
)
from larkdocio.write.model.requests import APPEND_ROW_INDEX
from larkdocio.write.disposition import (
    WriteWatch,
    classify_apply_exception,
    disposition_refusal,
    not_attempted_refusal,
)
from larkdocio.write.preview import Plan
from larkdocio.write.revision import (
    REVISION_GUARD_ACTIVE,
    stale_document_detail,
    unconfirmable_document_detail,
)


def _not_drift(exc):
    """Let a **rejected app credential** through this engine untouched (LD-672).

    **The ``_live_or_stale`` doctrine, extended to the one failure that fires FIRST.** This
    engine converts a failed Lark call into its own vocabulary — a moved anchor, an
    unconfirmable revision, a refused entry — because those are what a failed call usually
    means here. A rejected App ID/Secret is not any of them: **no token was issued and no
    document was ever asked for**, so reporting it as *"the document has most likely been
    DELETED"* or *"0 of 1 applied (stale-document)"* is a lie of exactly the kind the rate-limit
    re-raise already exists to prevent — and a more likely one, because it fires on the run's
    very first call, on the second most common first-run mistake there is.

    Measured before this existed: ``roundtrip push --apply`` on a rejected pair printed **zero
    bytes** and escaped ``LarkApplyRefusedError('0 of 1 entries applied; 1 refused
    (stale-document ×1)')`` — a credential typo reported as document drift, with advice
    (*re-read and re-plan*) that could not possibly help.

    Ordinary Lark failures are **not** touched: this is only the token handshake's own
    refusals, and only the ones carrying Lark's code
    (:func:`larkdocio.common.transport.is_credential_rejection`).
    """
    if is_credential_rejection(exc):
        raise exc


# --------------------------------------------------------------------------- #
# Live-block introspection — read the target's own text off a raw get_block dict #
# --------------------------------------------------------------------------- #

def _content_container(block: dict) -> dict:
    """The block's text container: the type-named key holding ``{"elements": [...]}``.

    docx v1 nests a block's runs under a key named for its type (``text`` /
    ``heading1``…``heading9`` / ``bullet`` / ``ordered`` / ``code`` / ``quote`` / …),
    each an object with an ``elements`` list. Finding it by shape (the one value that is
    a dict carrying an ``elements`` list) keeps the engine block-type-agnostic without
    enumerating every textual type. A block with no such container → ``{}``.
    """
    for value in block.values():
        if isinstance(value, dict) and isinstance(value.get("elements"), list):
            return value
    return {}


def _live_elements(block: dict) -> list:
    """The live block's read ``elements`` (its runs), or ``[]`` if it carries none."""
    return _content_container(block).get("elements", [])


def _elements_plain_text(elements) -> str:
    """Concatenate the ``text_run`` contents of a live block — what the quote matches.

    Mirrors the resolver's plain-text basis: only ``text_run`` content is quotable
    verbatim text; mentions / equations carry no text a consumer would quote, so they
    contribute nothing to the re-validation string.
    """
    parts: List[str] = []
    for element in elements or []:
        run = element.get("text_run")
        if run is not None and isinstance(run.get("content"), str):
            parts.append(run["content"])
    return "".join(parts)


def _leading_text_run(elements) -> Optional[dict]:
    """The first ``text_run`` element (its style seeds the whole-paragraph replacement)."""
    for element in elements or []:
        if element.get("text_run") is not None:
            return element
    return None


# --------------------------------------------------------------------------- #
# Stale-anchor preamble — the shared "read live block + get plain text" idiom    #
# every resolved apply path opens with (narrative / insert / delete / subspan /   #
# table-cell), the narrative/insert/delete drift guard, and the ONE composed        #
# pre-write re-validation those three paths call (_revalidated_or_stale, LD-142).    #
# --------------------------------------------------------------------------- #

def _read_live_text(client: WriteClient, document_id: str, block_id: str):
    """Read one live block and its plain text: ``(block, live_elements, live_text)``.

    The single source for the read half every resolved apply path opens with — one
    ``get_block`` for ``block_id``, its content-container ``elements``, and the quotable
    ``text_run`` plain text. Callers keep only what they need (the narrative path uses
    ``live_elements`` + ``live_text``; insert uses ``live_text``; delete also uses the raw
    ``block`` for its parent + removed-payload capture; subspan/table-cell reuse the read
    then run their own differing checks).

    Callers reach it through :func:`_live_or_stale`, which turns a **failed** read into a
    ``stale-anchor`` refusal instead of letting it abort the batch.
    """
    block = client.get_block(document_id, block_id)
    live_elements = _live_elements(block)
    return block, live_elements, _elements_plain_text(live_elements)


def _live_or_stale(client: WriteClient, document_id: str, block_id: str, anchor):
    """``(read, stale)`` — the live read for the pre-write re-validation, or the refusal.

    Exactly one of the two is ``None``. When :func:`_read_live_text` succeeds, ``read`` is
    its ``(block, live_elements, live_text)`` triple. When the read itself **fails**, the
    anchored block could not be confirmed to be what the plan saw — which is *precisely*
    staleness — so this returns a typed ``stale-anchor`` :class:`ApplyLogEntry` carrying
    Lark's own ``code``/``msg`` in the mandatory ``detail`` (LD-131), and the caller returns
    it with **no write issued**.

    **Why a refusal and not the exception (LD-137).** The commonest cause is the amplifier's
    stale race: the block was **deleted between plan and apply**, so a read of it errors. An
    exception there breaks two engine contracts at once — every processed request yields
    exactly one apply-log entry, and a refusal is a *skip*, never a failure of the batch: the
    consumer would get no apply-log at all, with the earlier entries already written. A
    rate-limit error is deliberately **re-raised**: throttling is not staleness (the shared
    transport owns backoff), and misreporting it as a drifted anchor would be a lie.
    """
    try:
        return _read_live_text(client, document_id, block_id), None
    except LarkRateLimitError:
        raise
    except LarkAPIError as exc:
        _not_drift(exc)
        stale = ApplyLogEntry.refused(
            anchor=anchor,
            refusal=Refusal.stale_anchor(
                detail=(
                    f"block {block_id} could not be re-read for the pre-write "
                    f"re-validation, so what the plan previewed cannot be confirmed — the "
                    f"block has most likely been DELETED since the plan was built. NO write "
                    f"was issued. Lark said: code={exc.code!r} msg={exc.msg!r}. Re-read the "
                    f"document and re-plan"
                )
            ),
        )
        return None, stale


def _stale_if_drifted(anchor, live_text: str, block_id: str,
                      expected: Optional[str] = None) -> Optional[ApplyLogEntry]:
    """A refused ``stale-anchor`` entry when the block drifted under the anchor since the
    plan was built, else ``None`` — the narrative/insert/delete guard.

    **The precondition is the anchor's own** (LD-137), because the two anchor kinds identify
    their target differently:

    * a quote+breadcrumb :class:`~larkdocio.write.model.Anchor` — the **quote must still be a
      substring** of the live text. A quote is a fragile locator (the text it matched could
      have changed under it, leaving the anchor pointing at something else), so re-finding it
      is the check. Byte-unchanged W1 behavior, message included;
    * an :class:`~larkdocio.write.model.AnchorById` — the id cannot come to mean a different
      block, so there is nothing to re-find; what staleness means instead is *the content
      changed since you previewed it*. The plan captured the block's live-basis text
      (``expected``), and the live text must still **equal** it: a compare-and-swap on the
      anchored block, strictly stronger than the quote check, and the strict-concurrency
      posture D9 asks for (an edit racing yours refuses rather than being
      overwritten). ``expected is None`` can only happen for an entry rebuilt from a wire
      form that predates the field; the block's mere existence (proved by the read that got
      us here) is then the whole precondition.

    Reached by the three single-re-validation paths through :func:`_revalidated_or_stale`; the
    subspan and table-cell paths run their own, different re-validation and so do not call it.
    ``block_id`` rides along so the mandatory refusal ``detail`` can name the block that
    drifted (LD-131).
    """
    if isinstance(anchor, AnchorById):
        if expected is not None and live_text != expected:
            return ApplyLogEntry.refused(
                anchor=anchor,
                refusal=Refusal.stale_anchor(
                    detail=(
                        f"block {block_id} (anchored by block_id) changed since the plan was "
                        f"built: the plan previewed {expected!r}, the live block now holds "
                        f"{live_text!r}. An id-anchored write is a compare-and-swap on the "
                        f"block's content, so it refuses rather than overwrite somebody "
                        f"else's edit; re-read the document and re-plan"
                    )
                ),
            )
        return None

    if anchor.quote not in live_text:
        return ApplyLogEntry.refused(
            anchor=anchor,
            refusal=Refusal.stale_anchor(
                detail=(
                    f"the anchor quote {anchor.quote!r} is no longer present in the live "
                    f"text of block {block_id} — it changed since the plan was built; "
                    f"re-read the document and re-plan"
                )
            ),
        )
    return None


def _revalidated_or_stale(client: WriteClient, document_id: str, entry):
    """``(read, stale)`` — the WHOLE pre-write re-validation for one resolved entry.

    The single opening of the three single-re-validation write paths (narrative / insert /
    delete, LD-142): it **composes** the two halves above — :func:`_live_or_stale` (the live
    read, or the "could not be re-read / most likely deleted" refusal) and
    :func:`_stale_if_drifted` (the anchor's own precondition: an
    :class:`~larkdocio.write.model.AnchorById`'s compare-and-swap against the plan's captured
    ``precondition_text``, or a quote anchor's quote-still-a-substring check) — and hands the
    caller **exactly one** of:

    * ``(read, None)`` — the ``(block, live_elements, live_text)`` triple, freshly confirmed
      to still be what the plan previewed. Each caller keeps only the parts it needs (delete
      wants the raw ``block`` for its parent lookup + removed-payload capture, narrative wants
      ``live_elements`` for the style-preserving rebuild, insert needs none of it — the read
      was the *check*);
    * ``(None, stale)`` — a typed ``stale-anchor`` :class:`ApplyLogEntry` the caller returns
      as-is, with **no write issued**.

    **Why one function.** These six lines *were* copy-pasted verbatim into all three paths, at
    the one place in the engine where a missed edit means a write that should have refused —
    and LD-137 duly had to thread ``precondition_text`` through three copies. One seam makes
    the next such change one edit, and makes "did every write path re-validate?" answerable by
    reading one function. The **order is load-bearing**: a block that cannot be read at all has
    no live text to compare, so the read arm refuses first.

    **Deliberately not shared (LD-142 § Out of scope).** :func:`_apply_subspan` re-validates
    the *span* against the live text (a stricter, offset-bearing precondition) and
    :func:`_apply_table_cell` runs a **double** read (row identity *and* cell content,
    Decision f). Both reuse :func:`_live_or_stale` for the read half and keep their own check
    body; routing either through this guard would change behavior, not shape.
    """
    read, stale = _live_or_stale(client, document_id, entry.block_id, entry.anchor)
    if stale is not None:
        # The block could not even be re-read (deleted under us) — refuse before comparing.
        return None, stale
    _block, _live_elements, live_text = read

    stale = _stale_if_drifted(entry.anchor, live_text, entry.block_id, entry.precondition_text)
    if stale is not None:
        # The block drifted under the anchor since the plan was built — refuse, skip.
        return None, stale
    return read, None


# --------------------------------------------------------------------------- #
# Whole-paragraph patch body — one replacement run, leading style preserved       #
# --------------------------------------------------------------------------- #

def _without_comment_ids(elements):
    """``elements`` with every run's ``comment_ids`` removed (and an emptied style dropped).

    The collapsed-run guard. :func:`to_write_elements` re-emits a run's review anchors,
    which is right for a **split** (each region's anchors land on the run that replaced its
    text) and wrong for a **collapse**: the leading run's anchor on a single run spanning
    the whole new paragraph would move a reviewer's comment onto text they never commented
    on, and the other runs' anchors would be gone regardless — the two variants the product
    decision rejected in favour of refusing. The whole-block path refuses before it reaches
    this builder; a whole-**cell** edit rides the same builder without that plan-time check,
    so the guard lives here where the collapse happens rather than at one caller.
    """
    for element in elements:
        run = element.get("text_run")
        style = run.get("text_element_style") if run is not None else None
        if not style or "comment_ids" not in style:
            continue
        del style["comment_ids"]
        if not style:
            del run["text_element_style"]
    return elements


def build_whole_paragraph_update(live_elements, replacement: str) -> dict:
    """The element-level ``update_text_elements`` body for a whole-paragraph replacement.

    Whole-paragraph granularity (§ Decision (d)): the entire paragraph collapses to a
    **single** run carrying ``replacement``. The run is rebuilt from the live block's
    **leading** ``text_run`` via :func:`to_write_elements` (with a ``mutate`` that swaps
    in the replacement), so the leading run's clean style — bold / italic / inline_code /
    strikethrough / underline / text_color / background_color / link — survives; the
    trailing runs' per-span styles are intentionally dropped (that is sub-span territory).
    This is the element-level rebuild the spike prescribed — **never** a lossy Markdown
    round-trip, which would drop even the leading style.

    **Inline comment anchors reach no run of this body** (:func:`_without_comment_ids`).
    The collapse leaves one run where per-passage anchors have nowhere to attach, so an
    edit whose target carries inline comment anchors is **refused** at plan time
    (``comment-anchors-present``) with the sub-span edit named as the way through. That
    holds for **both** paths built on this builder: a whole-block edit is refused on the
    block's own inline comment anchors, and a whole-**cell** (table) edit is refused on the
    inline comment anchors of the cell's inner text block — the block this body would
    rewrite — with its ``detail`` naming the row and column and the by-id sub-span edit a
    cell locator cannot express. The body itself never carries the leading run's anchor onto
    the replacement, which would move a reviewer's comment onto text they never commented on.
    """
    lead = _leading_text_run(live_elements)
    source = [lead] if lead is not None else [{"text_run": {"content": ""}}]
    elements = _without_comment_ids(to_write_elements(source, mutate=lambda _c: replacement))
    return {"update_text_elements": {"elements": elements}}


def build_span_elements_update(spans) -> dict:
    """The ``update_text_elements`` body for a cell authored as a **span sequence** (LD-619).

    The same oneof, the same endpoint and the same batch as
    :func:`build_whole_paragraph_update` — only the elements differ, and they are
    :func:`~larkdocio.write.encode._span_elements`' output, which is the **measured** shape:
    Lark accepted this exact body on ``PATCH .../blocks/batch_update`` against a cell's
    **Lark-provisioned** inner text block and read the link back verbatim. The capture is kept
    in the source repository at ``tests/captures/ld517-in-cell-link/captures/001-in-cell-link-readback.json``
    § ``sent.route_B_batch_update_body``.

    **It does not go through the leading-run rebuild** the whole-paragraph builder performs,
    and that is deliberate rather than an omission: this builder writes into a **freshly
    provisioned** cell, which has no live run whose style could be preserved — the
    whole-paragraph builder over empty live elements produces exactly one bare run, so there
    is nothing here to inherit. It is therefore **not** a route for restyling an existing
    cell (that is the ``TableLocator`` whole-cell patch, whose ``replacement`` is a plain
    ``str``), and no caller reaches it with a block that already holds content.
    """
    return {"update_text_elements": {"elements": span_elements(tuple(spans))}}


def build_todo_done_update(done: bool) -> dict:
    """The block ``PATCH`` body that moves a ``todo``'s checkbox — the endpoint's **fifth**
    oneof this engine sends (LD-574), beside ``update_text_elements``, ``insert_table_row``,
    ``insert_table_column`` and ``replace_image``.

    **The spelling and the field mask are CITED, not derived here.** Round 5 measured them on
    a throwaway document — its verdict grid (§ 5 **M4**) was retired on 2026-09-18, so the
    result is stated here (masks ``[1]`` / ``[2]`` / ``[3]`` swept, the probe deleted with its deletion
    independently verified): mask ``2`` moves ``done`` and leaves ``align``, ``folded``, the
    item's own text and the nested child's id / text / state untouched. Without it a caller
    had to re-derive this spelling from the source and could fire an **unproven** mask at a
    document a refusal had just called concurrently edited — which is the reason it ships here,
    in one place, behind the plan gate, rather than being re-derived per caller.
    The repo re-proves it by read-back on a harness-created disposable in the
    ``live_write`` ring; the citation is why nobody guesses, not a substitute for that.

    The body carries **only** ``done`` under ``style``, so the untouched-properties claim is
    true by construction rather than by promise, and no new endpoint or scope is involved —
    it is the same ``_patch_block`` route a whole-paragraph edit uses.
    """
    return {"update_text_style": {"style": {"done": bool(done)}, "fields": [2]}}


# --------------------------------------------------------------------------- #
# Sub-span patch body — split matched run(s), mutate ONLY the span, keep styles   #
# (W3 / LD-077) — element-level, exactly-one-uniform-region-or-refuse             #
# --------------------------------------------------------------------------- #

#: Sentinel for a non-``text_run`` element's "style" — never equal to any real cleaned
#: style, so a non-text element can never be part of a uniform-style span region.
_NON_TEXT_RUN = object()


def _clean_run_style(element):
    """The cleaned write-side ``text_element_style`` of a ``text_run`` element (via the
    canonical :func:`to_write_elements` rebuild), a ``dict`` or ``None``; a non-text
    element → :data:`_NON_TEXT_RUN`. Two runs are "uniform" iff this compares equal — so a
    span's replacement inherits exactly one determinate style, or the span refuses.

    The rebuild re-emits a run's ``comment_ids``, so this comparison covers a run's
    **review anchors** as well as its styling, and by the same rule: a span whose runs
    carry *different* anchors has no single answer for the run that replaces it — giving it
    one region's ids would extend a reviewer's comment over text they never commented on,
    and giving it none is the silent loss this path exists to end. So it refuses, exactly as
    a disagreeing style already does."""
    rebuilt = to_write_elements([element])
    if not rebuilt:
        return _NON_TEXT_RUN
    tr = rebuilt[0].get("text_run")
    if tr is None:
        return _NON_TEXT_RUN
    return tr.get("text_element_style")


def build_subspan_update(live_elements, span: str, replacement: str):
    """The ``update_text_elements`` body that replaces ONLY ``span`` — or ``None`` to refuse.

    Splits the matched run(s) of ``live_elements`` at the span boundaries and rebuilds the
    **whole** element list with only the span mutated: runs before/after the span pass
    through :func:`to_write_elements` byte-identically, the boundary run(s)' pre-span
    prefix and post-span suffix keep their own style, and the span collapses to **one**
    replacement run carrying the region's single style. It is **element-level** (never a
    lossy Markdown rebuild — the spike's "silent killer"), so every surrounding run's
    bold / italic / inline_code / strikethrough / underline / text_color /
    background_color / link survives exactly.

    **Inline comment anchors ride with the run they belong to.** Every rebuilt run
    re-emits the ``comment_ids`` its source run carried, so a sub-span edit's replacement
    run takes its region's anchors along with its region's style, the boundary fragments
    keep the anchors of the text they are still part of, and a run the split never touches
    comes through byte-identically, anchors included. The **whole-block** path cannot do
    that — it collapses the block to a single run — so an edit there is **refused** when the
    block carries inline comment anchors (``comment-anchors-present``), and this path is the
    recovery that refusal names. The **whole-cell** path shares that collapse, so a cell edit
    is **refused** on the same reason when the cell's inner text block carries inline comment
    anchors, and this path is its recovery too — anchored by the inner block's id, because a
    row-key-and-column locator cannot name a span.

    Returns ``None`` — the caller refuses with
    :meth:`~larkdocio.write.model.Refusal.span_not_splittable` — when the span does not map
    to **exactly one uniformly-styled contiguous run region**:

    * it occurs ≠1 time in the live text (defensive — the caller checks this first);
    * the overlapped runs carry **differing** styles, or **differing review anchors** (the
      replacement's style or anchors would be a guess — refuse, never guess; see
      :func:`_clean_run_style`);
    * it **overlaps a non-text inline** (a mention / equation strictly inside the span,
      which cannot be split).

    ``replacement`` may be empty (the span is removed, prefix + suffix left adjacent).
    """
    text = _elements_plain_text(live_elements)
    start = text.find(span)
    if start < 0 or text.find(span, start + 1) != -1:
        return None
    end = start + len(span)

    overlapped = []  # (element_index, run_start_offset, element) for each run the span hits
    cursor = 0
    for i, element in enumerate(live_elements):
        run = element.get("text_run")
        if run is None:
            # A non-text inline (mention / equation) sits at offset `cursor`, zero-width in
            # the text-run basis. Strictly inside the span → the span cannot be split.
            if start < cursor < end:
                return None
            continue
        content = run.get("content", "")
        run_start, run_end = cursor, cursor + len(content)
        cursor = run_end
        if run_end <= start or run_start >= end:
            continue  # this run is entirely outside the span — a pure neighbour
        overlapped.append((i, run_start, element))

    if not overlapped:
        return None

    # Uniform-style-or-refuse: every overlapped run must share ONE cleaned style.
    styles = [_clean_run_style(element) for (_i, _s, element) in overlapped]
    if any(s != styles[0] for s in styles):
        return None
    uniform_style = styles[0]

    first_i, first_start, first_el = overlapped[0]
    last_i, last_start, last_el = overlapped[-1]
    prefix = first_el["text_run"].get("content", "")[: start - first_start]
    suffix = last_el["text_run"].get("content", "")[end - last_start:]

    middle = []
    if prefix:
        # the pre-span fragment of the first overlapped run — keeps that run's style.
        middle.extend(to_write_elements([first_el], mutate=lambda _c: prefix))
    if replacement:
        run = {"content": replacement}
        if uniform_style:
            run["text_element_style"] = uniform_style
        middle.append({"text_run": run})
    if suffix:
        # the post-span fragment of the last overlapped run — keeps that run's style.
        middle.extend(to_write_elements([last_el], mutate=lambda _c: suffix))

    rebuilt = (
        to_write_elements(live_elements[:first_i])
        + middle
        + to_write_elements(live_elements[last_i + 1:])
    )
    return {"update_text_elements": {"elements": rebuilt}}


# --------------------------------------------------------------------------- #
# The WHOLE-DOCUMENT compare-and-swap (LD-139, D9) — the outer gate               #
# every batch passes through BEFORE its first write. Per-anchor STALE_ANCHOR is    #
# blind to drift AROUND an anchor; this is not.                                     #
# --------------------------------------------------------------------------- #

def _refuse_whole_batch(plan: Plan, detail: str) -> ApplyLog:
    """The batch-wide refusal: **every** entry of ``plan`` refused ``stale-document``.

    All-or-refused, so the log stays 1:1 with the plan in order (each entry keeps its own
    anchor, so a consumer can still correlate every request it submitted) while carrying the
    one reason that applies to all of them. **No write has been issued at this point and none
    will be** — the caller returns this log immediately.
    """
    return ApplyLog(
        entries=tuple(
            ApplyLogEntry.refused(anchor=entry.anchor, refusal=Refusal.stale_document(detail))
            for entry in plan.entries
        ),
        revision_guard=plan.revision_guard,
    )


def _document_cas(plan: Plan, client: WriteClient, document_id: str):
    """The whole-document compare-and-swap, or ``None`` to proceed with the batch.

    Runs **once, immediately before the batch's first write** (D9 — the CAS is per apply
    batch). Three outcomes:

    * the plan carries **no usable anchor** (``revision_guard`` is not ``"active"``) →
      ``None``. There is nothing to compare, so no call is made — burning a throttled read to
      learn nothing would be worse than useless. The plan's marker already says the guard is
      unavailable and why (never silently off), and the per-entry ``STALE_ANCHOR``
      re-validation still runs on every write;
    * the live ``revision_id`` **equals** the plan's → ``None``: the document is confirmed to
      be the one previewed, and the batch proceeds;
    * the live revision **differs**, or could not be established at all → the batch-wide
      ``stale-document`` refusal log, with **zero writes issued**. Any difference counts, in
      either direction: a lower revision is impossible live, so seeing one means the anchor
      does not describe this document and refusing is the only honest answer. An unreadable
      revision refuses **conservatively** — a document that cannot be confirmed unchanged is
      treated exactly like one that changed.

    A rate-limit error is deliberately **re-raised** (the :func:`_live_or_stale` doctrine):
    throttling is not drift, and telling a consumer to re-plan a document that never changed
    would be a lie. There is deliberately **no fourth outcome** — no re-locating of anchors,
    no re-indexing of positions, no partial application (§ D9, maintainer-rejected as "messy").
    """
    if plan.revision_guard != REVISION_GUARD_ACTIVE:
        return None

    cached = plan.document_revision_id
    try:
        live = client.read_document_revision(document_id)
    except LarkRateLimitError:
        raise
    except LarkAPIError as exc:
        _not_drift(exc)
        return _refuse_whole_batch(plan, unconfirmable_document_detail(
            document_id=document_id, cached=cached,
            why=f"the document meta read failed — Lark said code={exc.code!r} "
                f"msg={exc.msg!r}",
        ))

    if live is None:
        return _refuse_whole_batch(plan, unconfirmable_document_detail(
            document_id=document_id, cached=cached,
            why="the document meta carried no revision_id, so the live revision is unknown",
        ))
    if live != cached:
        return _refuse_whole_batch(plan, stale_document_detail(
            document_id=document_id, cached=cached, live=live))
    return None


# --------------------------------------------------------------------------- #
# apply — execute a dry-run plan: whole-¶, style-preserving, stale-safe, logged   #
# --------------------------------------------------------------------------- #

def apply(plan: Plan, client: WriteClient, document_id: str,
          *, allow_partial: bool = False) -> ApplyLog:
    """Execute a dry-run ``plan`` against ``document_id`` via ``client``.

    Only a :class:`~larkdocio.write.preview.Plan` from
    :func:`~larkdocio.write.preview.dry_run` is accepted (the hard gate — a non-``Plan``
    raises :class:`TypeError`). Each entry is dispatched in plan order:

    * a **refused** entry (ambiguous / not-found / write-hostile / column-not-found /
      cannot-hold-children, decided at dry-run) is carried into the apply-log verbatim —
      **no write**;
    * a resolved **insert** entry → :func:`_apply_insert`: re-validate the reference, then
      ``create_children`` at the plan's computed parent + index; log the created id(s);
    * a resolved **delete** entry → :func:`_apply_delete`: re-validate the target, capture
      its full removed payload (destructive-safe), then ``batch_delete`` its live range;
    * a resolved **sub-span** entry → :func:`_apply_subspan`: re-validate the span against
      the live block, then split the matched run(s) at the span boundaries and patch ONLY
      the span (uniform-style-or-refuse; surrounding styles preserved);
    * a resolved **narrative** entry → :func:`_apply_narrative`: re-validate the anchor
      against the live block (quote still a substring?), then patch it whole-paragraph;
    * a resolved **table-cell** entry (carrying a
      :class:`~larkdocio.write.resolve.ResolvedCell`) → :func:`_apply_table_cell`: the
      DOUBLE re-validation (key cell + target cell), then patch the cell's inner text
      block whole-cell;
    * a resolved **table-grow** entry → :func:`_apply_grow_table`: re-read the live block and
      refuse if it is no longer a table, then append one row and report the cells that came
      into being;
    * a resolved **comment-create** entry →
      :func:`~larkdocio.write.comments._apply_comment_create`: create the whole-document
      comment and log its id and author (a whole-document comment has no anchor to
      re-validate);
    * a resolved **comment-remove** entry →
      :func:`~larkdocio.write.comments._apply_comment_remove`: read the thread, judge that
      every reply is this application's own, then delete — in that order, which is what makes
      the judgement the validation.

    Every write routes through the throttled shared transport. **EVERY plan entry — applied,
    refused, or failed mid-flight — yields exactly one**
    :class:`~larkdocio.write.model.ApplyLogEntry`, in plan order:
    ``len(log.entries) == len(plan.entries)`` on every run.

    **THE DISPOSITION BOUNDARY, and what it changed.** Each resolved entry is dispatched
    inside :mod:`larkdocio.write.disposition`: an exception raised while applying it is
    classified into a typed outcome instead of propagating. Before that boundary existed, a
    ``LarkAPIError`` from a create/patch/delete escaped this loop and the caller received **no
    log at all** — including for the entries that had already written, which is precisely the
    state a log exists to prevent. Now:

    * the failing entry is logged ``refused`` (nothing landed), ``failed`` (whether it landed
      is INDETERMINATE — never mislabelled a refusal) or ``applied-unverified`` (a write seam
      RETURNED and a step after it did not, so the change IS in the document);
    * **the batch HALTS** and every remaining entry is logged ``not-attempted``. Halting is
      the pre-existing behaviour preserved, not a new policy: entries after a mid-batch
      failure were never attempted before this boundary either. What is new is that they now
      SAY so. Every docx disposition is systemic for that reason — the argument is in
      :mod:`larkdocio.write.disposition`;
    * :attr:`~larkdocio.write.model.ApplyLog.halt` discloses which entry stopped the batch and
      why.

    **WHAT THIS RAISES, stated exactly.** ``TypeError`` for a non-``Plan`` (the gate, above,
    before any entry exists). :class:`~larkdocio.errors.LarkRateLimitError` from the
    whole-document compare-and-swap — deliberately re-raised, because throttling is not drift
    and it happens before the batch. And
    :class:`~larkdocio.errors.LarkApplyRefusedError` whenever the finished log holds entries
    that did not land, unless ``allow_partial=True``, because a caller who discards the log
    must not be able to mistake a half-applied batch for a clean run. **Nothing else.** A
    ``LarkAPIError``, a transport failure or a library bug raised while applying an entry no
    longer leaves this function: it becomes a log entry, and that log reaches the caller
    either as the return value (``allow_partial=True``) or on
    ``LarkApplyRefusedError.log``.

    **What that means for an existing caller.** The exception a mid-batch API failure produces
    changes class — ``LarkAPIError`` becomes ``LarkApplyRefusedError`` — and gains the log it
    never carried. Which entries apply and which do not is **unchanged**, and no call is
    issued that was not issued before. The refusals ARE the writes that did not happen, so the
    raise is a report, never a rollback.
    """
    if not isinstance(plan, Plan):
        raise TypeError(
            "apply() accepts ONLY a dry-run plan produced by "
            "larkdocio.write.preview.dry_run(...); got "
            f"{type(plan).__name__}. Build a plan via the previewer, not raw edits."
        )

    # The WHOLE-DOCUMENT compare-and-swap (D9) — the outer gate, BEFORE any write and
    # before any block is even re-read. A drifted (or unconfirmable) document refuses the
    # ENTIRE batch here, with zero writes issued; there is no path past this that
    # accommodates the drift.
    drifted = _document_cas(plan, client, document_id)
    if drifted is not None:
        # A drifted document refused EVERY entry with zero writes — so this raises too,
        # unless the caller opted into partial application (LD-458).
        return gate_refusals(drifted, allow_partial=allow_partial,
                             surface="larkdocio.write.apply.apply")

    # The resolved-entry write path is dispatched per op through the **one op-descriptor
    # registry** (:mod:`larkdocio.write.ops`) — insert → ``_apply_insert``, delete →
    # ``_apply_delete``, subspan → ``_apply_subspan``, edit → ``_apply_edit`` (which itself
    # routes table-cell vs narrative by ``entry.cell``). The *refused* arm is op-agnostic —
    # a refusal decided at dry-run is carried into the apply-log verbatim, NO write — so it
    # stays here rather than in the registry. Imported lazily to avoid a load-time cycle.
    from larkdocio.write import ops

    entries: List[ApplyLogEntry] = []
    halt: Optional[dict] = None      # set by the first classified failure

    total = len(plan.entries)
    # The loop walks EVERY plan entry unconditionally and appends EXACTLY ONE log entry per
    # iteration — the apply-log's completeness is structural here, not asserted after the fact.
    for index, entry in enumerate(plan.entries):
        if halt is not None:
            # The batch stopped earlier: this entry was never attempted, and says so.
            entries.append(ApplyLogEntry.not_attempted(
                anchor=entry.anchor,
                refusal=not_attempted_refusal(halt, total=total)))
            continue

        if not entry.is_resolved:
            entries.append(ApplyLogEntry.refused(anchor=entry.anchor, refusal=entry.refusal))
            continue

        # THE DISPOSITION BOUNDARY. The watch is what lets the classification tell "the write
        # never happened" from "the write happened and a later step did not" — a log that
        # guessed there would be a log that lies.
        watch = WriteWatch(client)
        try:
            entries.append(ops.apply_dispatch(entry, watch, document_id))
        except Exception as exc:   # noqa: BLE001 — THE invariant: nothing escapes the loop
            if not watch.wrote:
                # AFTER the wrote check, deliberately: once the change is in the document the
                # only truthful record is applied-unverified, whatever raised afterwards.
                _not_drift(exc)
            disposition = classify_apply_exception(exc, wrote=watch.wrote)
            refusal = disposition_refusal(
                disposition, exc,
                where=_entry_label(entry),
                wrote_seams=watch.completed,
            )
            entries.append(_disposition_log_entry(entry, disposition, refusal))
            # Every docx disposition halts (the surface's whole-batch doctrine — see
            # `larkdocio.write.disposition`), so this is unconditional in effect; it is
            # written as the predicate anyway, because the day a ruling earns an
            # entry-scoped arm the classification table is the only thing that should move.
            if disposition.halts:
                halt = {
                    "index": index,
                    "reason": disposition.reason,
                    "detail": refusal.detail,
                    "landed": disposition.landed,
                    "not_attempted": total - index - 1,
                }

    # The log carries the plan's whole-document guard status, so a consumer holding only the
    # apply-log can still tell whether the document-level CAS was in force (never silent) —
    # and, since the boundary, whether the batch stopped early and why.
    log = ApplyLog(entries=tuple(entries), revision_guard=plan.revision_guard,
                   halt=_wire_halt(halt))
    return gate_refusals(log, allow_partial=allow_partial,
                         surface="larkdocio.write.apply.apply")


def _entry_label(entry) -> str:
    """A short, human-readable "which entry" for a disposition detail — the op + its target,
    so a log line is actionable without cross-referencing the plan."""
    anchor = entry.anchor
    where = (getattr(anchor, "block_id", None)
             or getattr(anchor, "quote", None)
             or getattr(anchor, "comment_id", None)
             or type(anchor).__name__)
    return f"{entry.op} on {where!r}"


def _wire_halt(halt: Optional[dict]) -> Optional[dict]:
    """``halt`` with its typed reason rendered to the wire value, so the log serializes.

    The in-loop dict carries the :class:`~larkdocio.write.model.RefusalReason` member because
    that is what the classification produced and what the not-attempted wording reads; the log
    carries the string, because an :class:`~enum.Enum` is not JSON.
    """
    if halt is None:
        return None
    return dict(halt, reason=halt["reason"].value)


def _disposition_log_entry(entry, disposition, refusal: Refusal) -> ApplyLogEntry:
    """Build the apply-log entry for a classified per-entry failure.

    ONE place maps a :class:`~larkdocio.common.disposition.Disposition`'s ``outcome`` to its
    :class:`ApplyLogEntry` factory, so the outcome vocabulary cannot drift from the
    classification table.
    """
    if disposition.outcome == "applied-unverified":
        return ApplyLogEntry.applied_unverified(anchor=entry.anchor, refusal=refusal)
    if disposition.outcome == "failed":
        return ApplyLogEntry.failed(anchor=entry.anchor, refusal=refusal)
    return ApplyLogEntry.refused(anchor=entry.anchor, refusal=refusal)


# --------------------------------------------------------------------------- #
# ``_apply_edit``'s leaves — narrative (W1) and table-cell (W2). The count they used   #
# to be introduced by is derived now, in the module docstring's declared basis.         #
# --------------------------------------------------------------------------- #

def _apply_narrative(entry, client: WriteClient, document_id: str) -> ApplyLogEntry:
    """Apply one resolved **narrative** entry: single live re-validation, then patch.

    Re-reads the target block and requires the anchor's quote to still be a substring
    of the live text; on drift → ``stale-anchor``, no write. Otherwise patches the block
    whole-paragraph (element-level, style-preserving).

    **The checkbox half (LD-574).** An entry carrying ``todo_done`` moves a ``todo``'s bit
    through :func:`build_todo_done_update` — one more ``_patch_block`` on the same block, on
    the same endpoint, because the endpoint takes one oneof per call. Two rules keep that
    from costing anything it should not:

    * the **text patch is skipped when the live text already equals the replacement** and a
      bit is moving. :func:`build_whole_paragraph_update` collapses the block to a single run
      and drops every trailing run's per-span style, so writing a block's own text back for
      a flip nobody asked to reword would silently **flatten** its inline styling — a
      destructive side effect of a request that was supposed to change one boolean. Confined
      to this path: with no bit to move the text patch is unconditional exactly as it always
      was;
    * ``todo_done`` is ``None`` unless the bit actually moves (the compiler's rule), so a
      plain todo text edit issues the one call it always did.

    Everything else is unchanged W1 behavior — extracted verbatim from :func:`apply`'s former
    inline resolved branch.
    """
    read, stale = _revalidated_or_stale(client, document_id, entry)
    if stale is not None:
        return stale                       # deleted under us, or drifted — no write issued
    _block, live_elements, live_text = read

    if entry.todo_done is None or live_text != entry.replacement:
        update = build_whole_paragraph_update(live_elements, entry.replacement)
        client._patch_block(document_id, entry.block_id, update)
    if entry.todo_done is not None:
        client._patch_block(document_id, entry.block_id,
                           build_todo_done_update(entry.todo_done))
    return ApplyLogEntry.applied(
        anchor=entry.anchor,
        block_id=entry.block_id,
        before=live_text,          # the live text actually replaced (truthful)
        after=entry.replacement,
        todo_done=entry.todo_done,
    )


def _apply_table_cell(entry, client: WriteClient, document_id: str) -> ApplyLogEntry:
    """Apply one resolved **table-cell** edit — the DOUBLE re-validation (design decision f).

    A table can shift under the anchor, so immediately before writing the engine
    re-reads BOTH cells and refuses on **either** drift (stricter than W1's single
    check):

    1. **KEY cell (row identity)** — re-read the row's key cell (column 0) and require
       the ``row_key`` to still be a substring of its live text. If the row moved /
       relabelled, the anchor no longer names the intended row → ``stale-anchor``, no
       write (and the target is never even read);
    2. **TARGET cell (content unchanged)** — re-read the target cell and require its live
       text to still **equal** the captured ``before``. If the cell's content changed
       since the plan was built → ``stale-anchor``, no write.

    Only when both hold does it patch the target cell's **inner text block** whole-cell,
    via the **same** element-level :func:`build_whole_paragraph_update` +
    :meth:`WriteClient._patch_block` path a paragraph uses (spike Test 5 — no new
    endpoint). Every path returns exactly one :class:`ApplyLogEntry`; ``block_id`` is the
    resolved **cell** id (matching the plan), while the write targets the inner block.
    """
    cell = entry.cell

    # (1) KEY cell — row identity still holds? (shares the read idiom; own check body)
    read, stale = _live_or_stale(
        client, document_id, cell.key_text_block_id, entry.anchor)
    if stale is not None:
        # The row's key cell could not be re-read (the row/table went away) — refuse.
        return stale
    _key_block, _key_elements, live_key_text = read
    if entry.anchor.row_key not in live_key_text:
        return ApplyLogEntry.refused(
            anchor=entry.anchor,
            refusal=Refusal.stale_anchor(
                detail=(
                    f"the row_key {entry.anchor.row_key!r} is no longer present in the live "
                    f"key cell (block {cell.key_text_block_id}) of row {cell.row} — the row "
                    f"identity changed since the plan was built; re-read and re-plan"
                )
            ),
        )

    # (2) TARGET cell — content unchanged since capture?
    read, stale = _live_or_stale(
        client, document_id, cell.target_text_block_id, entry.anchor)
    if stale is not None:
        # The target cell could not be re-read (removed under us) — refuse, no write.
        return stale
    _target_block, live_target_elements, live_target_text = read
    if live_target_text != entry.before:
        return ApplyLogEntry.refused(
            anchor=entry.anchor,
            refusal=Refusal.stale_anchor(
                detail=(
                    f"the target cell (block {cell.target_text_block_id}, row {cell.row} / "
                    f"column {cell.column}) drifted since the plan was built: expected "
                    f"{entry.before!r}, live {live_target_text!r}; re-read and re-plan"
                )
            ),
        )

    # Both fresh → patch the inner text block whole-cell (element-level, style-preserving).
    update = build_whole_paragraph_update(live_target_elements, entry.replacement)
    client._patch_block(document_id, cell.target_text_block_id, update)
    return ApplyLogEntry.applied(
        anchor=entry.anchor,
        block_id=entry.block_id,     # the resolved CELL id (the user-facing target)
        before=live_target_text,     # the live cell text actually replaced (truthful)
        after=entry.replacement,
    )


def _subspan_not_splittable_detail(live_elements, span: str, block_id: str) -> str:
    """The ``span-not-splittable`` detail for a span the builder could not map to one region.

    Two shapes, because the two causes have **different recoveries** and a detail that names
    the wrong one is the lying-refusal defect the house standard exists to prevent. When the
    live block carries **inline comment anchors** the boilerplate advice "edit the whole
    paragraph instead" is a dead end — that path refuses on the very same anchors — so the
    detail says so and points at the recovery that works (narrow the span inside one run).
    With no anchor in the block the shipped wording is emitted **verbatim**, so the common
    case's message is unchanged.
    """
    if any(
        ((el.get("text_run") or {}).get("text_element_style") or {}).get("comment_ids")
        for el in live_elements or []
    ):
        return (
            f"the span {span!r} in block {block_id} does not map to exactly one region that "
            f"is uniform in BOTH style and review anchors — the block carries inline comment "
            f"anchors, and the span crosses runs that disagree about them (or about their "
            f"style), so the replacement run's anchors would be a guess: it would either "
            f"extend a reviewer's comment over text they never commented on or drop it. "
            f"Narrow the span so it lies inside a single run — one whose text is entirely "
            f"inside one reviewer's comment, or entirely outside every comment. Editing the "
            f"whole block instead will not help here: that path refuses on the same anchors "
            f"(comment-anchors-present), because it rebuilds the block as one run"
        )
    return (
        f"the span {span!r} in block {block_id} does not map to exactly "
        f"one uniformly-styled run region — it crosses runs of differing style "
        f"or overlaps a non-text inline (mention / equation), so the replacement "
        f"style would be a guess; edit the whole paragraph instead, or narrow "
        f"the span to one styled run"
    )


def _apply_subspan(entry, client: WriteClient, document_id: str) -> ApplyLogEntry:
    """Apply one resolved **sub-span** edit (W3 / LD-077): re-validate the span, then split.

    Re-reads the target block (its id was pinned at plan time) and re-validates the **span**
    against the LIVE text-run text — the authoritative exactly-one-or-refuse check at write
    time:

    * the span is **gone** from the live text → ``stale-anchor`` (it drifted since the plan
      was built), no write;
    * the span now occurs **>1** time → ``span-not-splittable`` (no longer exactly one
      region), no write.

    Then :func:`build_subspan_update` splits the matched run(s) at the span boundaries and
    mutates ONLY the span, preserving every surrounding run's style byte-identically. If the
    span cannot be mapped to exactly one **uniformly-styled** contiguous run region — it
    crosses runs of differing style, or overlaps a non-text inline — the builder returns
    ``None`` and the engine **refuses** ``span-not-splittable`` rather than guess a
    replacement style (the absolute exactly-one-or-refuse invariant; the spike's "silent
    killer" never fires because the patch is element-level, never a Markdown rebuild). The
    apply-log records the span (``before``) actually replaced and the ``replacement``
    (``after``).
    """
    read, stale = _live_or_stale(client, document_id, entry.block_id, entry.anchor)
    if stale is not None:
        # The block could not be re-read (deleted under us) — refuse, skip, no write.
        return stale
    _block, live_elements, live_text = read

    span = entry.span
    first = live_text.find(span)
    if first < 0:
        # the span drifted out from under the anchor since the plan was built.
        return ApplyLogEntry.refused(
            anchor=entry.anchor,
            refusal=Refusal.stale_anchor(
                detail=(
                    f"the span {span!r} is no longer present in the live text of block "
                    f"{entry.block_id} — it changed since the plan was built; re-read and "
                    f"re-plan"
                )
            ),
        )
    if live_text.find(span, first + 1) != -1:
        # the span now occurs more than once → not exactly one region → refuse (no guess).
        return ApplyLogEntry.refused(
            anchor=entry.anchor,
            refusal=Refusal.span_not_splittable(
                detail=(
                    f"the span {span!r} now occurs more than once in the live text of block "
                    f"{entry.block_id} — no longer EXACTLY one region, so the edit would be "
                    f"a guess; lengthen the span and re-plan"
                )
            ),
        )

    update = build_subspan_update(live_elements, span, entry.replacement)
    if update is None:
        # the span crosses differing run styles or review anchors, or overlaps a non-text
        # inline → the replacement's style/anchors are ambiguous → refuse (never guess).
        return ApplyLogEntry.refused(
            anchor=entry.anchor,
            refusal=Refusal.span_not_splittable(
                detail=_subspan_not_splittable_detail(live_elements, span, entry.block_id)
            ),
        )

    client._patch_block(document_id, entry.block_id, update)
    return ApplyLogEntry.applied(
        anchor=entry.anchor,
        block_id=entry.block_id,
        before=span,                 # the span actually replaced (truthful)
        after=entry.replacement,
    )


# --------------------------------------------------------------------------- #
# The two W3 block-level paths — insert (create_children) and delete (batch_delete) #
# --------------------------------------------------------------------------- #

def _live_insertion_point(client: WriteClient, document_id: str, entry, block: dict):
    """``((parent_block_id, index), None)`` — WHERE to create, read off the **LIVE** tree.

    **The LD-453 fix, and the one discipline this engine now has for child indexes: an
    insert derives its index off the live parent at write time, exactly as
    :func:`_apply_delete` always has.** The plan freezes *which* block the anchor means;
    it never freezes *where beside it*.

    Before this, ``entry.insertion_point.index`` — a plain ordinal of the **plan-time**
    snapshot — went straight to ``create_children``. Entries dispatch in plan order, so
    entry *k* wrote against a tree that *k−1* earlier entries had already grown: two or
    more inserts resolving to the **same parent** in one batch each landed one position
    early per earlier same-parent insert at a lower index, and a same-batch delete shifted
    a later insert the other way. Refusals were empty, every apply-log entry said
    ``inserted`` with real created ids, and only a full read-back showed it (dogfood round
    4; the measured capture was retired on 2026-09-18). Delete was immune the whole
    time because it already read its index live — which is why the same consumer's
    20-request delete batches were clean.

    Per position:

    * ``before`` / ``after`` — one ``get_block`` on the reference's **live** ``parent_id``,
      then ``child_ids.index(reference)`` (+1 for ``after``): the same three lines
      :func:`_apply_delete` runs. Cost: one extra read per insert entry, which is the
      price of the guarantee;
    * ``append-into`` — the reference **is** the parent and the ask is *last*, so the write
      goes at ``index=-1``, the API's own append. No extra read, and it cannot drift: two
      ``append-into`` entries into one parent now keep their authored order (before the
      fix both carried the plan-time child count and the second landed *before* the first).

    Returns ``(located, None)`` or ``(None, stale)`` — the same two-armed shape as
    :func:`_revalidated_or_stale`, and for the same reason: a parent that cannot be read,
    or that no longer lists the reference, means the plan's position **cannot be confirmed**,
    which is staleness. **Never a guessed index and never a silent fall back to the plan's
    stale ordinal** — a wrong index is exactly the silent-misplacement defect this exists to
    end. A rate-limit error is re-raised (throttling is not staleness).
    """
    if entry.insertion_point.position == InsertPosition.APPEND_INTO.value:
        return (entry.block_id, -1), None

    parent_id = block.get("parent_id")
    if parent_id is None:
        return None, ApplyLogEntry.refused(
            anchor=entry.anchor,
            refusal=Refusal.stale_anchor(
                detail=(
                    f"block {entry.block_id} no longer reports a parent, so the live "
                    f"position beside it cannot be derived and the plan's position cannot "
                    f"be confirmed. NO write was issued. Re-read the document and re-plan"
                )
            ),
        )
    try:
        parent = client.get_block(document_id, parent_id)
    except LarkRateLimitError:
        raise
    except LarkAPIError as exc:
        _not_drift(exc)
        return None, ApplyLogEntry.refused(
            anchor=entry.anchor,
            refusal=Refusal.stale_anchor(
                detail=(
                    f"the parent {parent_id} of reference block {entry.block_id} could not "
                    f"be read, so the live index to insert at cannot be derived. NO write "
                    f"was issued. Lark said: code={exc.code!r} msg={exc.msg!r}. Re-read the "
                    f"document and re-plan"
                )
            ),
        )
    child_ids = list(parent.get("children") or ())
    if entry.block_id not in child_ids:
        return None, ApplyLogEntry.refused(
            anchor=entry.anchor,
            refusal=Refusal.stale_anchor(
                detail=(
                    f"reference block {entry.block_id} is no longer a child of {parent_id} "
                    f"in the live document, so there is no position beside it to insert at "
                    f"— it moved since the plan was built. NO write was issued. Re-read the "
                    f"document and re-plan"
                )
            ),
        )
    index = child_ids.index(entry.block_id)
    if entry.insertion_point.position == InsertPosition.AFTER.value:
        index += 1
    return (parent_id, index), None


def _apply_insert(entry, client: WriteClient, document_id: str) -> ApplyLogEntry:
    """Apply one resolved **insert** entry: re-validate the reference, then create.

    Immediately before writing the engine re-reads the live **reference** block and
    requires the anchor's quote to still be a substring of its live text; on drift →
    ``stale-anchor``, no write (identical to the narrative single re-validation — you do
    not create relative to a reference that moved out from under the anchor).

    Otherwise it creates the request's typed content via
    :meth:`~larkdocio.write.client.WriteClient.create_children`. The content is first
    encoded to real docx payloads by :func:`~larkdocio.write.encode.encode_content` — a
    flat **pre-order** sequence with parent pointers, because ``create_children`` creates
    **one level deep** — and issued as **one call per parent**
    (:func:`~larkdocio.write.encode.create_batches`):

    * the ``None`` group (the top-level blocks) goes **beside the live reference** —
      :func:`_live_insertion_point` derives the parent and the child index off the **live**
      tree at write time (LD-453), the same discipline :func:`_apply_delete` has always
      used. The plan's ``insertion_point.index`` is the pre-batch ordinal and is
      deliberately **not** what is written: in a multi-entry batch it decays the moment an
      earlier entry lands in the same parent, which is how same-parent multi-insert batches
      used to silently misplace every insert after the first;
    * every deeper group is created under the **real block id Lark returned** for its
      parent, appended (``index=-1``) so the authored child order is the document order.

    **Flat content is byte-identical to the pre-LD-134 behaviour**: exactly one call, the
    same body. The apply-log entry records every created block id in pre-order (AC5).
    Encoding happens **before the first write** of this entry, so an unencodable tree
    cannot land a partial subtree.

    **One exception to all of the above, and only one (LD-482).** When the encoded content is
    **exactly one table** inside the measured one-call envelope, the whole subtree goes out
    through :func:`_insert_table_in_one_call` instead — at the **same parent and the same
    index** this function just derived. Everything else, including a table that shares its
    entry with another block or overflows the envelope, takes the route described above,
    unchanged.
    """
    read, stale = _revalidated_or_stale(client, document_id, entry)
    if stale is not None:
        return stale        # the reference went away or drifted — nothing is created
    # (the read's TEXT is the anchor check; its ``parent_id`` is what the live insertion
    # point below is derived from — an insert writes relative to the reference.)
    block, _live_elements, _live_text = read

    located, stale = _live_insertion_point(client, document_id, entry, block)
    if stale is not None:
        return stale        # the live position beside the reference cannot be confirmed
    point_parent_block_id, point_index = located
    encoded = encode_content(entry.content)          # before any write — no partial subtree

    # THE ONE-CALL TABLE ROUTE (LD-482) — same parent, same index, one atomic call.
    if len(encoded) == 1 and fits_one_call(encoded[0]):
        return _insert_table_in_one_call(
            entry, client, document_id, encoded,
            point_parent_block_id, point_index,
        )

    created_ids: List[Optional[str]] = [None] * len(encoded)
    created_records: List[Optional[dict]] = [None] * len(encoded)
    # The entry's COST, counted as it is spent (LD-562). Every mutating call this function
    # issues adds one; the reads (the re-validation, the grown grid's re-read, the block
    # listing) add none, because the unit the log publishes is mutating write calls. It is
    # deliberately NOT re-derived from the arithmetic _fill_table_cells documents: a second
    # implementation of the same number drifts silently the first time a ceiling moves.
    write_calls = 0

    for parent_position, positions in create_batches(encoded):
        if parent_position is None:
            parent_block_id, index = point_parent_block_id, point_index
        else:
            # a deeper level: parent on the id Lark just handed back, appended last.
            parent_block_id, index = created_ids[parent_position], -1
        with _naming_the_block(encoded, positions):
            data = client.create_children(
                document_id,
                parent_block_id,
                [encoded[position].payload for position in positions],
                index=index,
            )
        write_calls += 1
        for position, child in zip(positions, (data or {}).get("children", [])):
            created_ids[position] = child.get("block_id")
            created_records[position] = child

    # A TABLE's cells are Lark's to provision (LD-135); fill each authored cell now that
    # the grid exists. Done after the creates so the block structure is complete first —
    # a table is always a leaf, so no deeper batch depends on this. ``any(...)``: a grid of
    # only empty cells has nothing to write, so it does not even look up the cell ids.
    #
    # A grid bigger than MAX_CREATE_GRID_AXIS on either axis was created at the ceiling
    # (LD-431); grow it to its authored shape FIRST, so the cells the fill addresses are the
    # cells the caller authored.
    for position, child in enumerate(encoded):
        with _naming_the_block(encoded, (position,)):
            record = created_records[position]
            grew = _grow_table_grid(client, document_id, created_ids[position], child.grid)
            write_calls += grew
            if grew:
                # the create response listed the SEED's cells — that list is now short.
                record = None
            if any(child.cell_texts):
                write_calls += _fill_table_cells(
                    client, document_id, created_ids[position], child.cell_texts,
                    cell_spans=child.cell_spans, created=record,
                )

    return ApplyLogEntry.inserted(anchor=entry.anchor, created_block_ids=created_ids,
                                  mutating_write_calls=write_calls)


def _insert_table_in_one_call(entry, client: WriteClient, document_id: str, encoded,
                              parent_block_id, index) -> ApplyLogEntry:
    """Create a whole table — grid, cells and cell text — in ONE atomic ``descendant`` call.

    **What this buys, in the words of the failure it removes.** The other route builds a table
    in three movements (create a ≤9-per-axis seed grid → append a row per call → fill the
    cells), so a failure partway through leaves a **real, wrong table in a real document**:
    half-grown, or grown and half-filled. There is no such state here. Lark either takes the
    subtree whole or takes none of it — every over-envelope refusal the spike provoked read
    back as **nothing created** (the 2026-08-14 table-cell-creation spike, §§ 3a/3b; its
    write-up was retired on 2026-09-18) — and the cost collapses
    with it: a 6 × 36 = 216-cell grid measured
    **1 call / 0.82 s here against 463 calls / 158.41 s** through the pre-LD-481 fill (§ 3c).

    **WHY THE ROUTE IS CHOSEN THIS NARROWLY — it is placement, not appetite.** The route is
    taken only when the entry's encoded content is *exactly one* table
    (:func:`~larkdocio.write.encode.fits_one_call`), and that condition is doing real work.
    ``descendant`` takes the **same** ``(parent, index)`` pair ``create_children`` takes, so
    swapping one call for the other changes **nothing** about how this engine positions
    anything: :func:`_live_insertion_point` derives the position off the live tree exactly as
    it did before (LD-453), and hands it here unmodified. But an entry whose top-level group
    holds a table *and* other blocks could not be one call — it would have to become a
    *sequence* of calls at arithmetically-advanced indexes, which is new positional logic in
    the insert path rather than a swapped endpoint. LD-482's own escape clause names that as
    the split condition, so it is not built: mixed content keeps the shipped route, whole.

    **What comes back, and what the caller sees.** ``data.block_id_relations`` maps each
    temporary id to the real block id Lark minted; the apply-log entry carries the **table's**
    id and only the table's — the same single created id this entry has always reported for a
    table insert, in the same place, so ``AnchorById`` on the returned id keeps working
    identically. The cells' ids were never reported by the other route either, so nothing a
    consumer could hold changes hands here.

    **When Lark refuses**, the raised :class:`~larkdocio.errors.LarkAPIError` is re-raised by
    :func:`_naming_the_block` naming the block and kind, and :func:`apply`'s **disposition
    boundary** classifies it — which is the pre-existing behaviour of any API refusal
    mid-batch, not something this route introduces. Stated exactly, because a mixed batch's
    other entries are a caller's business: entries **before** this one in the plan have already
    applied and stay applied; this entry lands **nothing**; entries **after** it are never
    attempted. Two terms of that sentence have moved since it was first written, and both are
    corrections rather than new behaviour. It used to end *"and the apply-log is not returned
    (the exception carries the message)"*: **the log is now complete and it reaches the
    caller** — one entry per plan entry, this one carrying the classified refusal and the
    remainder ``not-attempted`` — on ``LarkApplyRefusedError.log``, or as the return value
    under ``allow_partial=True``. The middle term had already been corrected once: it used to
    be *"this entry lands part of a table"*.
    """
    child = encoded[0]
    root_temp_id, descendants = table_subtree(child)
    with _naming_the_block(encoded, (0,)):
        data = client.create_descendant(
            document_id, parent_block_id,
            children_id=[root_temp_id], descendants=descendants,
            index=index,
        )
    return ApplyLogEntry.inserted(
        anchor=entry.anchor,
        created_block_ids=[_minted_id(data, root_temp_id)],
        mutating_write_calls=1,          # this route IS the one call — counted, not assumed
    )


def _minted_id(data, temp_id):
    """The real block id Lark minted for ``temp_id``, off a ``descendant`` response.

    ``data.block_id_relations`` is the authoritative map and is read first, by name — its
    entries come back in **no particular order** (the spike's captures interleave them), so
    positional indexing into it would be a coin flip. ``data.children`` is the fallback for a
    response that carries the created blocks but no relation row: the subtree has exactly one
    root, so its first child is that root. ``None`` if neither is present, which is what the
    other route also reports when a create response carries no id — never a guessed id.
    """
    data = data or {}
    for relation in data.get("block_id_relations") or ():
        if relation.get("temporary_block_id") == temp_id:
            return relation.get("block_id")
    for child in data.get("children") or ():
        return child.get("block_id")
    return None


# --------------------------------------------------------------------------- #
# LD-431 — an API refusal says WHICH block, and a seeded grid grows to its shape  #
# --------------------------------------------------------------------------- #

@contextmanager
def _naming_the_block(encoded, positions):
    """Re-raise any :class:`LarkAPIError` naming the block(s) the engine was writing.

    The cheapest useful change to a refusal, and one this issue could make outright: an error
    that names the block index and kind being written when the API refused turns a diagnosis
    from a bisect over 200 blocks into a single line of output.

    Two rules hold the shape honest:

    * **Lark's own code and message are carried through unedited**, as the head of the
      message. This library never rewrites Lark's text; it appends its own location.
    * **The authored TEXT never enters the message** — index and kind only. A caller's
      content may be sensitive and an error string ends up in logs.

    ``create_children`` refuses a **batch**, not a block, and says nothing about which member
    it objected to. So a batch of one names that one exactly (``block index 7 (kind: table)``)
    and a wider batch names its **range and kind tally** — the slice of the composed content
    to look at — rather than guessing an index the API never gave. Guessing would be worse
    than the bisect it replaces.
    """
    try:
        yield
    except LarkAPIError as refusal:
        _not_drift(refusal)
        positions = tuple(positions)
        total = len(encoded)
        if len(positions) == 1:
            where = (f"block index {positions[0]} "
                     f"(kind: {encoded[positions[0]].kind or 'unknown'})")
        else:
            tally: Dict[str, int] = {}
            for position in positions:
                kind = encoded[position].kind or "unknown"
                tally[kind] = tally.get(kind, 0) + 1
            kinds = ", ".join(f"{kind}×{count}" for kind, count in sorted(tally.items()))
            where = (f"block indexes {positions[0]}-{positions[-1]} (kinds: {kinds})")
        # **The re-raise carries the ORIGINAL error's class and attributes.** Rebuilding it as
        # a bare `LarkAPIError(message)` kept `str()` right and silently dropped `code`/`msg`
        # and the subclass — so a scope denial came back out as a generic API error and a
        # coded rejection came back with `code is None`. Nothing noticed while the only reader
        # of this exception was a human reading a traceback; the apply-time disposition
        # boundary reads `code` to tell "Lark answered about this entry" from "the call never
        # reached Lark", and an answer with no code is classified INDETERMINATE. So the
        # location is still appended to the message and nothing else about the error moves —
        # the errors-module doctrine exactly: this family adds attributes, it does not edit
        # text.
        located = f"{refusal} [while writing {where} of {total} in the composed content]"
        if isinstance(refusal, LarkPermissionError):
            raise LarkPermissionError(located, code=refusal.code, msg=refusal.msg,
                                      denial=refusal.denial) from refusal
        located_error = type(refusal)(located, code=refusal.code, msg=refusal.msg)
        # The denial record travels too — LATENT here today (nothing this walk can raise is a
        # denial-carrying error of a class other than LarkPermissionError, which the arm above
        # already handles), fixed anyway so it cannot become live the next time a surface with
        # its own typed family is reached from a composed write. ASSIGNED rather than passed to
        # the constructor on purpose: `type(refusal)` is whatever class arrived, and three
        # shipped subclasses take neither a `denial` keyword nor need one, so forwarding it as
        # an argument would turn a re-raise into a TypeError inside an `except` block — a worse
        # failure than the one being fixed. The attribute exists on every api error.
        located_error.denial = refusal.denial
        raise located_error from refusal


def _grow_table_grid(client: WriteClient, document_id: str, table_block_id, grid) -> int:
    """Append the rows / columns the create call was not allowed to declare (LD-431).

    ``create_children``'s property form validates each axis at
    :data:`~larkdocio.write.encode.MAX_CREATE_GRID_AXIS` — the whole root cause of the bug
    where a 10-row table composed, planned, and then died at the API with earlier batches
    already written. The encoder therefore seeds at the ceiling and this appends the rest,
    one throttled ``PATCH`` per line, through the **existing** ``_patch_block`` (the docx
    update-block oneof; no new endpoint and no new scope).

    Measured on disposables the probes created and trashed (the table-row-boundary probe,
    § 2 rows B1/E1/E2 and § 4; its findings were retired on 2026-09-18, so they are stated here):

    * ``insert_table_row {"row_index": -1}`` **appends at the end** and leaves every
      pre-existing cell id untouched and in order — which is what lets the row-major cell
      fill stay exactly as it was;
    * the row axis grew to **200** with **no refusal at any row** — 200 was as far as
      LD-431's probe went, because it was then the
      :data:`~larkdocio.write.model.MAX_TABLE_CELLS` ceiling. That cap is now **500**
      (LD-481: the fill is batched, so the number is anchored on Lark's measured
      one-call envelope rather than on our per-cell cost), so rows **201–500 are
      unmeasured, not refused** — no platform row cap has ever been found, and this note
      does not invent one;
    * the column axis grew to **100**, and the 101st answers ``1770010 too many table
      column`` — which is why :data:`~larkdocio.write.model.MAX_TABLE_COLUMNS` refuses that
      grid at compile time and this function never meets one.

    Returns **how many mutating calls it issued** — zero when nothing had to grow, which is
    also the "did it grow?" answer the caller needs (a grown table's cell list is longer than
    the one the create response reported, so the caller must re-read rather than trust it).
    The count goes up into the entry's apply-log disclosure, which is why it is reported
    rather than re-derived from the grid: the two axes' ceilings are free to move.
    """
    if not grid:
        return 0
    rows, columns = grid
    extra_rows = max(0, rows - MAX_CREATE_GRID_AXIS)
    extra_columns = max(0, columns - MAX_CREATE_GRID_AXIS)
    if not (extra_rows or extra_columns):
        return 0
    if not table_block_id:
        raise LarkAPIError(
            f"the create response carried no block id for the {rows}×{columns} table just "
            f"created, so the rows/columns past the {MAX_CREATE_GRID_AXIS}-per-axis create "
            f"ceiling cannot be appended — re-read the document to see what was created "
            f"before retrying"
        )
    return _append_table_lines(client, document_id, table_block_id,
                               extra_rows=extra_rows, extra_columns=extra_columns)


def _append_table_lines(client: WriteClient, document_id: str, table_block_id: str, *,
                        extra_rows: int, extra_columns: int) -> int:
    """Append ``extra_rows`` rows and then ``extra_columns`` columns to an EXISTING table,
    one throttled ``PATCH`` per line — and return **how many mutating calls it issued**.

    **THE one grow loop in this package**, extracted at LD-575 so its two callers share it
    rather than each carrying a copy: :func:`_grow_table_grid` (the create path, which computes
    the shortfall against the create-time per-axis ceiling) and :func:`_apply_grow_table` (the
    shipped grow op, which appends exactly one row). A second loop would be two definitions of
    the same wire operation, free to drift the moment either learned something — the same
    defect a parallel arithmetic is, one layer down.

    The operation keys and the append index are the MEASURED spellings, and the index is read
    from :data:`~larkdocio.write.model.requests.APPEND_ROW_INDEX` rather than typed here, so
    the value on the wire and the value a request defaults to are one constant. What was
    measured of them — appends at the end, every pre-existing cell id untouched and in order,
    the row axis to 200, the 101st column refused by Lark itself — is recorded in
    :func:`_grow_table_grid`'s docstring, which names the captures; it is not restated here.

    Rows go before columns, unchanged from the create path's original order: a row append is
    priced by the current column count, so growing the columns first would make each subsequent
    row wider than the authored grid asked for.
    """
    grew = 0
    for _ in range(extra_rows):
        client._patch_block(document_id, table_block_id,
                           {"insert_table_row": {"row_index": APPEND_ROW_INDEX}})
        grew += 1
    for _ in range(extra_columns):
        client._patch_block(document_id, table_block_id,
                           {"insert_table_column": {"column_index": APPEND_ROW_INDEX}})
        grew += 1
    return grew


def _apply_grow_table(entry, client: WriteClient, document_id: str) -> ApplyLogEntry:
    """Apply a resolved **table-grow** entry: append one row, and report what came into being.

    Three calls, and only the middle one mutates:

    1. **the live re-read** of the table the plan resolved. Same discipline every other block
       path has — the plan is a snapshot and the write happens later — and here it does two
       jobs: it confirms the block is still a table (if it is not, the entry refuses
       ``stale-anchor`` and nothing is written), and it records the cell ids **before** the
       append, in order, which is what makes step 3 an answer rather than a guess.
    2. **the append**, through :func:`_append_table_lines` — the one grow loop, one throttled
       ``PATCH`` on the existing block route. No new endpoint and no new scope.
    3. **the read-back**, whose new cell ids become the entry's ``created_block_ids``. An
       ``inserted`` entry whose created list was empty would be precisely the receipt-shaped
       silence this operation exists to end, so the row's cells are named rather than left for
       the caller to re-derive. It is a **read**, so it is not counted: the entry's
       ``mutating_write_calls`` is what the append loop actually issued, and ``atomic`` follows
       from that number and from nothing else.

    The outcome is the existing ``inserted`` one, deliberately: nothing is added to a green log
    for a consumer to key on, and what happened here *is* an insertion of blocks — the cells of
    a new row.
    """
    table_block_id = entry.block_id
    if not table_block_id:
        # Defensive: the resolver only ever hands over a table it found by id, so an entry
        # with no id could not have been resolved. Loud rather than a call against ``None``.
        raise LarkAPIError(
            "a resolved table-grow entry carries no table block_id, so there is nothing to "
            "append to — re-read the document and re-plan"
        )

    live = client.get_block(document_id, table_block_id) or {}
    if live.get("block_type") != TABLE_BLOCK_TYPE:
        return ApplyLogEntry.refused(
            anchor=entry.anchor,
            refusal=Refusal.stale_anchor(
                f"block {table_block_id} is no longer a table (docx block type "
                f"{TABLE_BLOCK_TYPE}); it reads back as block_type "
                f"{live.get('block_type')!r}. The plan resolved a table and the live document "
                f"disagrees, so no row was appended and nothing was written — re-read the "
                f"document and re-plan"
            ),
        )
    before = list(live.get("children") or ())

    issued = _append_table_lines(client, document_id, table_block_id,
                                 extra_rows=1, extra_columns=0)

    grown = client.get_block(document_id, table_block_id) or {}
    known = set(before)
    created = [cell for cell in (grown.get("children") or ()) if cell not in known]
    return ApplyLogEntry.inserted(anchor=entry.anchor, created_block_ids=created,
                                  mutating_write_calls=issued)


# --------------------------------------------------------------------------- #
# Table creation's second half (LD-135) — Lark provisions the cell grid, the      #
# engine fills each cell by patching its inner text block (no new endpoint).       #
# --------------------------------------------------------------------------- #

def _provisioned_cell_ids(client: WriteClient, document_id: str, table_block_id: str,
                          created: Optional[dict]) -> List[str]:
    """The created table's cell ids, row-major — from the create response if it carried
    them, else by re-reading the table block.

    ``create_children`` returns the created block(s); when the returned table record
    already lists its auto-provisioned ``children`` that IS the grid, and re-reading it
    would burn a throttled call for nothing. The ``get_block`` fallback keeps the path
    working if the response ever omits them.
    """
    ids = list((created or {}).get("children") or ())
    if ids:
        return ids
    if not table_block_id:
        # No id came back for the table we just created, so there is nothing to address —
        # fail loudly instead of issuing a call against a ``None`` block id.
        raise LarkAPIError(
            "the create response carried no block id for the table just created, so its "
            "authored cells cannot be filled — re-read the document to see what was "
            "created before retrying"
        )
    block = client.get_block(document_id, table_block_id)
    return list(block.get("children") or ())


def _chunked(items, size):
    """``items`` in consecutive runs of at most ``size``, order preserved."""
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _fill_table_cells(client: WriteClient, document_id: str, table_block_id: str,
                      cell_texts, *, cell_spans=(),
                      created: Optional[dict] = None) -> int:
    """Write the authored cell texts into a freshly created table, row-major.

    Creating a ``block_type: 31`` table makes Lark **auto-provision the grid** — each cell
    (type 32) wrapping one inner text block (type 2), live-proven by the W2 gate — so the
    text is written by **patching each cell's inner block** with the identical
    ``update_text_elements`` body a whole-cell edit uses (:func:`build_whole_paragraph_update`
    over empty live elements, since a fresh cell has none). No new patch shape.

    **The cost shape (LD-481).** This used to spend **two throttled calls per non-empty
    cell** — a ``get_block`` to find the cell's inner text block, then a ``_patch_block`` on
    it — which measured **463 write API calls / 158.41 s** for a 6×36 table's 216 cells, 93%
    of them the fill (the same spike, § 3c; retired on 2026-09-18). Both halves are now batched
    against routes the same spike measured:

    * every cell's inner block id comes from **one paginated document block list**
      (:meth:`~larkdocio.write.client.WriteClient.list_document_blocks`) — the listing carries
      each block's ``children``, so the whole grid is learned in ~2 calls;
    * the texts go out through
      :meth:`~larkdocio.write.client.WriteClient.batch_update_blocks` in runs of
      :data:`~larkdocio.write.client.MAX_BATCH_UPDATES_PER_CALL`.

    A fill is therefore ``⌈(2×cells + 1)/500⌉ list + ⌈non-empty cells / 48⌉ batch`` instead of
    ``2 × cells``, and the whole authoring of a 6×36 table measured **37 calls / 12.4 s**
    against the per-cell path's **463 / 158.41 s**. **Same
    endpoint family, same throttle, same scope** — nothing about *what lands in a cell*
    changed, and the batched request body is the identical ``update_text_elements`` the
    per-cell patch sent (a test pins that, and pins that the per-cell ``get_block`` does not
    come back).

    The behaviours that were right stay exactly as they were:

    * an **empty** authored cell is skipped — the provisioned cell is already empty, so the
      write would be a no-op costing a throttled call, and a grid of only empty cells does
      not even read the block list;
    * a **rich** cell (a span sequence — the in-cell **link anchor**, LD-619) rides the
      identical oneof, endpoint, batch and throttle; only its ``elements`` differ
      (:func:`build_span_elements_update`). Nothing about the cost shape above changes, and a
      **plain** cell's body is byte-for-byte the one it always sent;
    * a cell that arrives **without** an inner block (defensive — never seen live) gets one
      **created** carrying the text, rather than dropping the authored content;
    * a grid **smaller** than the one requested raises :class:`LarkAPIError`: the remaining
      authored cells have nowhere to go, and silently truncating a consumer's table is the
      one outcome worse than a loud failure. A cell the document listing does not carry at
      all raises for the same reason — an id that cannot be addressed is content that would
      go unwritten in silence.

    Returns **how many mutating calls it issued** — the batched writes plus any create for a
    cell that arrived without an inner block, and none of the reads. That number is counted as
    it is spent and reported upward for the entry's apply-log disclosure; the arithmetic above
    describes the cost but is never the source of the published figure, because the two would
    part company the first time a batch size or the paging changed.
    """
    cell_ids = _provisioned_cell_ids(client, document_id, table_block_id, created)
    if len(cell_ids) < len(cell_texts):
        raise LarkAPIError(
            f"table {table_block_id} was provisioned with {len(cell_ids)} cells but "
            f"{len(cell_texts)} were authored — the remaining cell contents have nowhere "
            f"to go. Refusing to silently truncate the table; re-read the document to see "
            f"what was created."
        )
    spans_per_cell = tuple(cell_spans) or (None,) * len(cell_texts)
    authored = [(cell_id, text, spans)
                for cell_id, text, spans in zip(cell_ids, cell_texts, spans_per_cell)
                if text]
    if not authored:
        return 0                          # provisioned empty already — nothing to read

    children = {block.get("block_id"): list(block.get("children") or ())
                for block in client.list_document_blocks(document_id)}
    updates, bare = [], []
    for cell_id, text, spans in authored:  # row-major, and it stays row-major on the wire
        if cell_id not in children:
            raise LarkAPIError(
                f"cell {cell_id} of table {table_block_id} is not in the document's own "
                f"block list, so its authored content has no block to be written to. "
                f"Refusing to leave a cell silently unwritten; re-read the document to see "
                f"what was created."
            )
        inner_ids = children[cell_id]
        # A RICH cell (LD-619) rides the identical oneof, endpoint and batch — only its
        # elements carry the link. The body is the one Lark accepted on THIS route against a
        # cell it had provisioned itself (in the source repository:
        # tests/captures/ld517-in-cell-link/captures/001-in-cell-link-readback.json § sent.route_B_batch_update_body).
        body = (build_span_elements_update(spans) if spans
                else build_whole_paragraph_update([], text))
        if inner_ids:
            updates.append({"block_id": inner_ids[0], **body})
        else:
            bare.append((cell_id, text, spans))
    written = 0
    for batch in _chunked(updates, MAX_BATCH_UPDATES_PER_CALL):
        client.batch_update_blocks(document_id, batch)
        written += 1
    for cell_id, text, spans in bare:
        # The defensive arm (a cell that arrived without an inner block — never seen live)
        # carries the link too, or a rich cell would silently lose its anchor on the one
        # path nobody watches.
        client.create_children(document_id, cell_id, [
            {"block_type": 2, "text": {"elements": span_elements(spans)}} if spans
            else text_block(text)
        ])
        written += 1
    return written


def _apply_delete(entry, client: WriteClient, document_id: str) -> ApplyLogEntry:
    """Apply one resolved **delete** entry: re-validate, capture the FULL payload, delete.

    The DESTRUCTIVE-SAFE path (Decision (c) / AC4). Immediately before writing:

    1. re-read the live **target** and require the anchor's quote to still be a substring
       of its live text; on drift → ``stale-anchor``, no write (and nothing is captured or
       removed — a stale delete does nothing);
    2. **capture the target's full removed-block payload** (:func:`_capture_removed_payload`
       — id + type + the live ``elements`` with their per-run style + the block-level
       ``style``, plus the own content of a block that carries no ``elements`` container at
       all: a diagram's ``add_ons`` (LD-192) and an image's ``image`` object (LD-528))
       BEFORE deleting, so a consumer can say exactly what was removed. Losing this is a
       FAIL — deletion is irreversible;
    3. locate the target's parent + its index within the **live** parent's ordered child
       list (read off the live tree, never a stale offline index), and remove the single
       contiguous child range ``[index, index + 1)`` via
       :meth:`~larkdocio.write.client.WriteClient.batch_delete`.

    Contiguous-range delete is a phase-1 non-goal (S1): the anchor resolves to exactly one
    block, so the range is always one child wide. The apply-log entry carries the removed
    block id + the captured payload.
    """
    read, stale = _revalidated_or_stale(client, document_id, entry)
    if stale is not None:
        # Somebody else's delete won the race, or the target drifted under the anchor.
        # A stale delete is a no-op: nothing is captured and nothing is removed.
        return stale
    block, _live_elements, _live_text = read

    # DESTRUCTIVE-SAFE: capture the full removed payload BEFORE the irreversible delete.
    removed_payload = _capture_removed_payload(block, entry.block_id)

    # Locate the target's contiguous child range in its LIVE parent (index off live order).
    parent_id = block.get("parent_id")
    parent = client.get_block(document_id, parent_id)
    child_ids = parent.get("children") or []
    index = child_ids.index(entry.block_id)
    client.batch_delete(document_id, parent_id, index, index + 1)

    return ApplyLogEntry.deleted(
        anchor=entry.anchor,
        block_id=entry.block_id,
        removed_payload=removed_payload,
    )


def _capture_removed_payload(block: dict, block_id: str) -> dict:
    """The full removed-block payload for a destructive delete (AC4) — reconstructable.

    Captures, from the LIVE block read right before deletion, everything a consumer needs
    to recreate the removed block via ``create_children``: the block ``block_id`` and
    ``block_type``, the content container's ``elements`` **verbatim** (each ``text_run``
    keeps its own ``text_element_style`` — the per-run style), and the container's
    block-level ``style`` (alignment / fold / etc., or ``None`` when the block carries
    none). The elements are captured raw (not passed through
    :func:`~larkdocio.write.client.to_write_elements`) so the record is a **complete,
    lossless** snapshot — an incomplete payload is a FAIL. JSON-serializable throughout
    (plain dicts/lists straight off the API response).

    **A diagram carries no ``elements`` container at all (LD-192).** Its content is the
    ``add_ons`` object — three fields, one of them a JSON string — so the shape-based capture
    above finds nothing for it and would record an empty snapshot. That matters more than it
    looks: a type-40 block has **no in-place update**, so *delete + re-create* is this library's
    own documented way to change a diagram, which makes this the one route whose undo record
    must not be empty. ``add_ons`` is therefore captured **verbatim** whenever the block carries
    one — exactly enough to recreate the block through ``create_children``. The key is
    **absent** for every other block type, so existing records are byte-unchanged.

    **An image carries no ``elements`` container either (LD-528).** Its content is the
    ``image`` object — the file ``token`` plus the geometry the live block carried
    (``width`` / ``height`` / ``align`` / ``scale`` on every payload measured so far) — so
    the shape-based capture above finds nothing for it and recorded ``elements: []``: the
    undo record named the block that was destroyed and nothing about what was in it. That
    became reachable with LD-507, which measured Lark's child-delete route against an image
    and narrowed the fence to admit it, so the library now *recommends* a route whose record
    was empty. The ``image`` object is therefore captured **verbatim** — the whole object as
    read, never re-keyed, so a key a future payload carries survives too — and, like
    ``add_ons``, the key is **absent** for every other block type, leaving existing records
    byte-unchanged.

    **What the image half of the record is, and is not.** It is a **reference** record: the
    token names bytes that still exist (deleting the block does not delete the media, and no
    route in the open API purges drive media), so a consumer can say what was destroyed and
    fetch it back with :meth:`~larkdocio.base.media.DocxMediaClient.download`. It is **not**
    an undo button and promises no re-bind: nothing in this library re-attaches a captured
    token to a new block (:func:`~larkdocio.write.media.put_image_in_document` takes no
    pre-made token), so re-authoring the picture uploads it again and mints a **new**
    permanent token.
    """
    container = _content_container(block)
    payload = {
        "block_id": block.get("block_id", block_id),
        "block_type": block.get("block_type"),
        "elements": container.get("elements", []),
        "style": container.get("style"),
    }
    add_ons = block.get("add_ons")
    if add_ons is not None:
        payload["add_ons"] = add_ons
    image = block.get("image")
    if image is not None:
        payload["image"] = image
    return payload
