"""larkdocio.write.intrabatch — the intra-batch ``not-found`` hedge (LD-151 / dogfood F14).

**ONE TREE, ONE BATCH — and that is the design, not a gap.** Every entry of a docx write
batch is resolved against a **single consistent snapshot** of the parsed document tree. That
snapshot is precisely what makes ``STALE_ANCHOR`` and ``STALE_DOCUMENT`` mean anything: the
plan a consumer approved describes one document at one instant, and the apply engine refuses
rather than re-interpreting it. So **a batch cannot depend on its own writes**: every queued
request must target content that exists at commit time.

**The rule, and the sanctioned idiom.** Queue an
:class:`~larkdocio.write.model.InsertRequest` and then, in the *same* batch, an
:class:`~larkdocio.write.model.EditRequest` anchored on the text that insert will create, and
the second request refuses ``not-found`` — **correctly**, because at plan time the block does
not exist. The working shape is two commits: commit the insert, take the
``created_block_ids`` :func:`~larkdocio.write.apply.apply` hands back, and anchor the
follow-up by one of them (:class:`~larkdocio.write.model.AnchorById`). That is
:data:`COMMIT_THEN_ANCHOR_RULE`, stated once here and quoted by the shipped guide.

**Why the engine is NOT fixed instead (recorded so this reads as deliberate).** Supporting
intra-batch dependencies would require **sequential re-planning inside apply()** — re-reading
and re-resolving between entries — which dissolves the snapshot guarantee, and the
whole-batch-zero-writes contract (``STALE_DOCUMENT``) with it: an approved plan would no
longer describe what will happen. **Do not fix this in the engine.** Revisit only if and when
a **session layer** lands, where a multi-commit conversation is a first-class object and the
re-planning has somewhere honest to live. A future reader finding this module should read the
limitation as a choice, not an oversight.

**What this module DOES do — disclosure, at plan time, for free.** The one real bug in F14 was
not the refusal, it was the *advice*: the ``not-found`` detail ended "re-read the document and
copy the quote verbatim", which for this case **can never succeed** (the text exists only in
the batch's own queued content), so an agent that trusts it loops — re-read, re-copy, refuse,
repeat. :func:`hedge_intra_batch_not_found` therefore compares each ``not-found`` anchor's
quote against the **same batch's queued insert content** and, on a hit, appends
:data:`INTRA_BATCH_HEDGE`: the intra-batch cause plus the recovery that works.

Three properties make that safe to run on every plan:

* **Zero I/O.** The scan reads the requests the caller already handed over.
  :func:`~larkdocio.write.preview.dry_run` takes no client and still structurally cannot
  write.
* **Zero semantic change.** The refusal **reason** stays ``not-found``, the resolver is
  untouched and remains batch-blind, resolved entries are byte-identical, and the ordinary
  detail survives verbatim as the hedged detail's prefix. Only refused entries whose text the
  batch itself would create are enriched.
* **Exact matching, never normalized.** The quote must be an exact substring of **one**
  authored block's own text — the same rule
  :func:`~larkdocio.write.resolve.block_plain_text` applies at commit time, one string per
  block, never the concatenation. A case-folded or whitespace-collapsed match would hedge
  anchors the post-commit retry would *still* refuse, i.e. promise a recovery that fails,
  which is worse than the plain refusal.

Pure data-in/data-out; depends only on the standard library and
:mod:`larkdocio.write.model`.
"""
from dataclasses import replace
from typing import Iterable, Tuple

from larkdocio.write.model import RefusalReason

#: **The rule**, in one sentence — the single place it is written down. The shipped guide
#: quotes it verbatim (and its doc guard derives the required wording from *this* constant, so
#: the prose cannot drift from the code's own words).
COMMIT_THEN_ANCHOR_RULE = (
    "every queued request must target content that exists at commit time; commit the insert, "
    "then anchor follow-ups by created_block_ids"
)

#: The clause appended to a ``not-found`` detail when the failing anchor's text appears in the
#: **same batch's** queued insert content. Deliberately **additive** — the ordinary diagnosis
#: stays intact as the prefix, so nothing a consumer already parses is lost — and deliberately
#: explicit that the re-read advice it follows cannot help *here*, because a hedge that merely
#: adds a sentence leaves the misdirection standing.
INTRA_BATCH_HEDGE = (
    " — BUT this batch queues an insert containing this text, so re-reading the document "
    "cannot help: a batch cannot depend on its own writes. Every request in a batch is "
    "resolved against a single consistent snapshot of the document (one tree, one batch), so "
    "the block this anchor means does not exist yet and no re-read will make it appear. "
    "Commit the insert first, then anchor by created_block_ids — apply() returns them, and "
    "AnchorById(block_id=...) goes anywhere an Anchor goes"
)


def authored_own_texts(content: Iterable) -> Tuple[str, ...]:
    """Every block-OWN text string ``content`` would bring into existence, in authored order.

    One entry per block that would be created, mirroring
    :func:`~larkdocio.write.resolve.block_plain_text`'s rule that a block's text is **its
    own**, never its children's: a nested list item contributes its own string, and a table
    contributes **one string per cell** (each cell's text lands in its own inner text block).
    The legacy tagless :class:`~larkdocio.write.model.NewParagraph` is covered by the same
    ``text`` attribute read, so no content shape is invisible to the scan.

    Empty strings are dropped — a marker block with no text can never carry an anchor quote,
    and keeping ``""`` would make every quote "match" it under a substring test.
    """
    out = []
    for block in content or ():
        text = getattr(block, "text", None)
        if isinstance(text, str) and text:
            out.append(text)
        for row in getattr(block, "rows", ()) or ():
            out.extend(cell for cell in row if isinstance(cell, str) and cell)
        out.extend(authored_own_texts(getattr(block, "children", ()) or ()))
    return tuple(out)


def queued_insert_texts(entries: Iterable) -> Tuple[str, ...]:
    """The batch's own **insert** corpus: every authored own-text of every queued insert.

    Insert entries only. An edit's ``replacement`` and a delete's target are **not** content
    the batch creates — committing them mints no block to anchor by id — so folding them in
    would hedge with an insert-specific recovery that does not apply (the false-hedging case
    the AC pins).

    A **refused** insert still counts: the batch *queues* it either way, so the follow-up's
    refusal has the same intra-batch cause, and the consumer sees the insert's own refusal
    alongside it.
    """
    out = []
    for entry in entries:
        if getattr(entry, "op", None) == "insert":
            out.extend(authored_own_texts(getattr(entry, "content", ()) or ()))
    return tuple(out)


def _anchor_quote(entry):
    """The verbatim quote the entry's anchor carries, or ``None`` when it carries none.

    Duck-typed on purpose: a narrative :class:`~larkdocio.write.model.Anchor` has a ``quote``;
    an :class:`~larkdocio.write.model.AnchorById` (a bare id — which cannot "appear in queued
    content", and whose shipped detail already names ``created_block_ids``) and a
    :class:`~larkdocio.write.model.TableLocator` (row-key + column, addressing a cell of a
    table that must already exist) have none, and are therefore never hedged.
    """
    quote = getattr(getattr(entry, "anchor", None), "quote", None)
    return quote if isinstance(quote, str) and quote else None


def hedge_intra_batch_not_found(entries):
    """Return ``entries`` with the intra-batch hedge appended to the details it applies to.

    A ``not-found`` entry is hedged when its anchor's quote is an exact substring of one
    authored own-text in the batch's queued insert content. Everything else is returned
    **unchanged and identical** — other reasons, id/table anchors, quotes absent from the
    batch, and every resolved entry.

    Order-independent by construction: inside one batch there is no dependency order (all
    entries resolve against the same snapshot), so a consumer who "fixes" the shape by
    reordering gets the same guidance rather than silence. Idempotent — the hedge is appended
    only when it is not already there — and total, so running it on a batch with no insert is
    the identity.
    """
    entries = tuple(entries)
    corpus = queued_insert_texts(entries)
    if not corpus:
        return entries
    return tuple(_hedged(entry, corpus) for entry in entries)


def _hedged(entry, corpus: Tuple[str, ...]):
    refusal = getattr(entry, "refusal", None)
    if refusal is None or refusal.reason is not RefusalReason.NOT_FOUND:
        return entry
    if INTRA_BATCH_HEDGE in refusal.detail:
        return entry
    quote = _anchor_quote(entry)
    if quote is None or not any(quote in authored for authored in corpus):
        return entry
    return replace(entry, refusal=replace(refusal, detail=refusal.detail + INTRA_BATCH_HEDGE))
