"""The unfetched-references queue and its end-of-download summary (LD-334).

The reader's per-block honesty answers *"what is in this paragraph?"* — an embedded sheet,
Base or synced block that was not fetched **names itself and its token** where it sits,
rather than vanishing. At sixteen documents that is the wrong granularity: the operator's
question is *"what did this run not get?"*, and answering it meant grepping every output
file for four marker strings. This module lifts the **same** disclosure one level, from
per-block to per-run.

**It is a projection, never a second source of truth.** Every record here is appended by the
block handler that built the typed node, from the node's own state — never by scanning the
rendered Markdown for marker text. The per-block markers are unchanged and remain the place
the tokens are read; the summary adds a level, it does not replace one.

**"Unfetched" has four meanings, and flattening them teaches the operator the wrong thing.**
Three are run states carried on the record:

* :data:`NEVER_BY_DESIGN` — a synced block. Its content lives in another document and
  reading it needs a read grant the integration usually lacks: an intentional won't-do,
  never a flag away.
* :data:`NOT_ENABLED` — an embedded sheet or Base whose deep read was not turned on for this
  run (the default; also the state when a flag is on but no client was supplied).
* :data:`DEEP_READ_DEGRADED` — the deep read was enabled **with** a client and came back with
  nothing, so the block kept its placeholder. A download never fails because a reference
  could not be read, which is exactly why this state has to be *said*: silence and success
  look identical from the output.

The fourth — *no command-line route exists* — is deliberately **not** a fourth state, because
it is a property of the **caller's surface**, not of the run: the same Base node reached from
an in-process reader with the flag off is genuinely ``NOT_ENABLED``. It is carried by the
per-class guidance sentence instead, which is where the operator acts on it. A route that
does not exist is never presented as "just pass a flag".

Everything here is **offline-pure**: building the queue and the summary costs **zero** API
calls and never triggers a deep read.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# -- reference classes -------------------------------------------------------
#
# Three classes from four block types: the two Base embed types (18 = an embedded
# Base, 53 = the same Base switched to a named view) report as ONE class, because
# the question at volume is "which Bases did I not get", not "which of them was
# view-switched" — and the per-block marker keeps that distinction anyway.
EMBEDDED_SHEET = "embedded_sheet"
EMBEDDED_BASE = "embedded_base"
SYNCED_BLOCK = "synced_block"

# -- the three run states ----------------------------------------------------
NOT_ENABLED = "not_enabled"
DEEP_READ_DEGRADED = "deep_read_degraded"
NEVER_BY_DESIGN = "never_fetched_by_design"

#: Report order — fixed, so two runs over the same document read the same way.
CLASS_ORDER = (EMBEDDED_SHEET, EMBEDDED_BASE, SYNCED_BLOCK)
REASON_ORDER = (NOT_ENABLED, DEEP_READ_DEGRADED, NEVER_BY_DESIGN)

_LABELS = {
    EMBEDDED_SHEET: ("embedded sheet", "embedded sheets"),
    EMBEDDED_BASE: ("embedded Base", "embedded Bases"),
    SYNCED_BLOCK: ("synced block", "synced blocks"),
}

#: What the operator can DO about each class — the routes that exist, named; the ones
#: that do not, said plainly rather than implied away.
_GUIDANCE = {
    EMBEDDED_SHEET: (
        "Embedded sheets: pass --deep-read-sheets to read them as inline tables."
    ),
    EMBEDDED_BASE: (
        "Embedded Bases: pass --deep-read-bases to read them as inline tables."
    ),
    SYNCED_BLOCK: (
        "Synced blocks: never fetched — the content lives in another document, and "
        "reading it needs a grant this integration usually does not have."
    ),
}


@dataclass
class ReferenceNote:
    """One reference this document made, and whether the run actually got it.

    ``identifier`` is the id the block's own marker names first — the embed token for a
    sheet or Base, the source **document** id for a synced block — so a consumer reading
    the summary and a consumer reading the Markdown are looking at the same handle.
    ``reason`` is ``None`` for a fetched reference: a reference that came back as content
    has no unfetched-reason to give.
    """
    kind: str
    identifier: Optional[str]
    fetched: bool
    reason: Optional[str] = None


def note_reference(parser: Any, kind: str, identifier: Optional[str], *,
                   fetched: bool, reason: Optional[str]) -> None:
    """Append one record to ``parser.reference_notes``, if the parser keeps that queue.

    Called by the block handlers at the moment they build the node, exactly where
    ``img_tokens`` / ``file_tokens`` / ``mention_user_ids`` are appended. The
    ``getattr`` guard keeps a hand-built parser stand-in (a handler takes any
    parser-like) from turning a summary into a crash — a disclosure must never be able
    to fail a read.
    """
    notes = getattr(parser, "reference_notes", None)
    if notes is None:
        return
    notes.append(ReferenceNote(kind, identifier, fetched, reason))


def deep_read_reason(*, enabled: bool, fetched: bool) -> Optional[str]:
    """The run state for a deep-readable class (sheet / Base).

    ``enabled`` means the flag AND its client were both present — i.e. the read was
    actually attempted. Attempted-and-empty is :data:`DEEP_READ_DEGRADED`; not attempted
    is :data:`NOT_ENABLED`. A fetched reference has no reason (the caller does not ask).
    """
    if fetched:
        return None
    return DEEP_READ_DEGRADED if enabled else NOT_ENABLED


def _unfetched(notes: List[ReferenceNote]) -> List[ReferenceNote]:
    return [n for n in notes if not n.fetched]


def _phrase(counts: Dict[str, int]) -> str:
    """``2 embedded sheets, 1 embedded Base and 1 synced block`` — a mixed document's shape."""
    parts = [
        f"{counts[kind]} {_LABELS[kind][0 if counts[kind] == 1 else 1]}"
        for kind in CLASS_ORDER if counts.get(kind)
    ]
    if len(parts) == 1:
        return parts[0]
    return f"{', '.join(parts[:-1])} and {parts[-1]}"


def summary_lines(notes: List[ReferenceNote]) -> List[str]:
    """The summary as log records — a headline, then one guidance line per class present.

    Returns ``[]`` when nothing was left unfetched: the summary is a **disclosure, not a
    per-run banner**, so a clean document says nothing at all.
    """
    unfetched = _unfetched(notes)
    if not unfetched:
        return []

    counts = {kind: 0 for kind in CLASS_ORDER}
    for note in unfetched:
        if note.kind in counts:
            counts[note.kind] += 1

    total = len(unfetched)
    headline = (
        f"This document references {_phrase(counts)} that "
        f"{'was' if total == 1 else 'were'} not fetched. Each one names itself and its "
        "token where it sits in the Markdown."
    )

    degraded = [n for n in unfetched if n.reason == DEEP_READ_DEGRADED]
    if degraded:
        d_counts = {kind: 0 for kind in CLASS_ORDER}
        for note in degraded:
            if note.kind in d_counts:
                d_counts[note.kind] += 1
        if len(degraded) == 1:
            headline += (
                f" {_phrase(d_counts)} was deep-read and the read did not come back; "
                "it kept its placeholder."
            )
        else:
            headline += (
                f" {_phrase(d_counts)} were deep-read and the reads did not come back; "
                "they kept their placeholders."
            )

    return [headline] + [
        _GUIDANCE[kind] for kind in CLASS_ORDER if counts.get(kind)
    ]


def sidecar_payload(notes: List[ReferenceNote]) -> Dict[str, Any]:
    """The machine-readable counterpart written into the ``--dump`` sidecar.

    Unlike the log this states an explicit **zero**: to a ledger, an absent key and a clean
    run are indistinguishable. It is a function of the parse alone — counts, kinds, reasons
    and the identifying token; no clock, no network — so the sidecar stays deterministic.
    """
    unfetched = _unfetched(notes)
    return {
        "total": len(unfetched),
        "by_class": {
            kind: sum(1 for n in unfetched if n.kind == kind) for kind in CLASS_ORDER
        },
        "by_reason": {
            reason: sum(1 for n in unfetched if n.reason == reason)
            for reason in REASON_ORDER
        },
        "references": [
            {"kind": n.kind, "reason": n.reason, "id": n.identifier} for n in unfetched
        ],
    }
