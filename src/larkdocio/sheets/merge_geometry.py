"""larkdocio.sheets.merge_geometry — the merge-fate model (LD-122, D4).

Extracted verbatim from ``write_apply.py`` (LD-125 T3, behavior-preserving) — the
deterministic geometry math that predicts what happens to an existing merge under a
single structural edit: insert-INSIDE the span → **grow**, insert-OUTSIDE → **shift**,
delete-INTERSECTING → **shrink**, shrink-to-1×1 (or a fully deleted axis) → **dissolve**.
v3 ``merges`` are 0-indexed, END-inclusive ``(start_row, end_row, start_col, end_col)``;
the fate is deterministic (LD-107 Q4). Pure geometry — nothing here opens a socket or
reads the sheet.
"""
from dataclasses import dataclass
from typing import Optional

from larkdocio.errors import LarkDocIOError


def _normalize_merge(m) -> tuple:
    """A merge region → ``(start_row, end_row, start_col, end_col)`` (0-idx, END-inclusive),
    accepting a 4-tuple/list or a v3 ``merges`` dict (``start_row_index``/… keys)."""
    if isinstance(m, dict):
        return (m["start_row_index"], m["end_row_index"],
                m["start_column_index"], m["end_column_index"])
    return tuple(m)


@dataclass(frozen=True)
class MergeFate:
    """The predicted fate of ONE merge under a single structural edit.

    ``before`` is the region as it was; ``after`` is the region afterward — or ``None``
    when the merge **dissolves**. ``fate`` names it: ``"grow"`` / ``"shift"`` /
    ``"shrink"`` / ``"dissolve"`` / ``"unaffected"``. JSON-serializable for a preview.
    """

    before: tuple
    after: Optional[tuple]
    fate: str

    def to_dict(self) -> dict:
        return {
            "before": list(self.before),
            "after": list(self.after) if self.after is not None else None,
            "fate": self.fate,
        }


def _insert_axis(lo: int, hi: int, at: int, count: int):
    """One axis span ``[lo, hi]`` (0-idx inclusive) after inserting ``count`` at 0-idx ``at``.

    A position ``p >= at`` moves to ``p + count``; ``p < at`` stays. So ``lo``/``hi`` each
    shift iff they are ``>= at``. Returns ``(new_lo, new_hi, grew, shifted)`` — ``grew`` iff
    the insert landed strictly inside the span (``lo < at <= hi``), ``shifted`` iff the whole
    span moved (``at <= lo``)."""
    new_lo = lo + count if lo >= at else lo
    new_hi = hi + count if hi >= at else hi
    grew = lo < at <= hi
    shifted = at <= lo
    return new_lo, new_hi, grew, shifted


def _delete_axis(lo: int, hi: int, d_start: int, d_end: int):
    """One axis span ``[lo, hi]`` (0-idx inclusive) after deleting 0-idx ``[d_start, d_end]``
    (inclusive). Returns ``(new_lo, new_hi)`` or ``None`` if every position on this axis was
    deleted. ``k = d_end - d_start + 1`` positions are removed; a surviving position ``p >
    d_end`` shifts to ``p - k``, ``p < d_start`` stays."""
    k = d_end - d_start + 1
    overlap = max(0, min(hi, d_end) - max(lo, d_start) + 1)
    if (hi - lo + 1) - overlap <= 0:
        return None  # the whole span on this axis was deleted
    new_lo = lo if lo < d_start else (lo - k if lo > d_end else d_start)
    new_hi = hi - k if hi > d_end else (d_start - 1 if hi >= d_start else hi)
    return new_lo, new_hi


def predict_merge_fate(merge, *, kind: str, dimension: str,
                       at_index_0based: int, count: int) -> MergeFate:
    """Predict ONE merge's fate under a single structural edit.

    ``kind`` is ``"insert"`` or ``"delete"``; ``dimension`` is ``"ROWS"`` or ``"COLUMNS"``;
    ``at_index_0based`` is the edit's 0-idx position (an insert index, or the first deleted
    row/col); ``count`` is how many rows/cols were inserted/deleted. Only the edited axis
    can change — the other axis is carried through untouched. Returns a :class:`MergeFate`
    (``after is None`` ⇒ dissolved).
    """
    sr, er, sc, ec = _normalize_merge(merge)
    before = (sr, er, sc, ec)
    row_axis = dimension == "ROWS"
    lo, hi = (sr, er) if row_axis else (sc, ec)
    other = (sc, ec) if row_axis else (sr, er)

    if kind == "insert":
        new_lo, new_hi, grew, shifted = _insert_axis(lo, hi, at_index_0based, count)
        if grew:
            fate = "grow"
        elif shifted:
            fate = "shift"
        else:
            fate = "unaffected"
        new_axis = (new_lo, new_hi)
    elif kind == "delete":
        d_start, d_end = at_index_0based, at_index_0based + count - 1
        result = _delete_axis(lo, hi, d_start, d_end)
        if result is None:
            return MergeFate(before=before, after=None, fate="dissolve")
        new_lo, new_hi = result
        if d_start > hi:               # deletion entirely below/right of the merge
            fate = "unaffected"
        elif d_end < lo:               # deletion entirely above/left → whole shift
            fate = "shift"
        else:                          # the deletion intersected the span
            fate = "shrink"
        new_axis = (new_lo, new_hi)
    else:  # pragma: no cover — callers pass only insert/delete
        raise LarkDocIOError(f"unknown merge-fate edit kind {kind!r}")

    if row_axis:
        after = (new_axis[0], new_axis[1], other[0], other[1])
    else:
        after = (other[0], other[1], new_axis[0], new_axis[1])

    # a merge must span > 1 cell; a shrink to a lone 1×1 cell dissolves it.
    if (after[1] - after[0] + 1) <= 1 and (after[3] - after[2] + 1) <= 1:
        return MergeFate(before=before, after=None, fate="dissolve")
    return MergeFate(before=before, after=after, fate=fate)


def predict_merge_fates(merges, *, kind: str, dimension: str,
                        at_index_0based: int, count: int):
    """:func:`predict_merge_fate` over a list of merges — one :class:`MergeFate` per input,
    in order (dissolved merges carry ``after is None``)."""
    return [
        predict_merge_fate(m, kind=kind, dimension=dimension,
                           at_index_0based=at_index_0based, count=count)
        for m in merges
    ]
