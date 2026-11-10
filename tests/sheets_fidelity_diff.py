"""THE two-leg (three-leg) write-gate fidelity differ (LD-116).

The LD-113 gate proved a Sheets **value** write surgical with a used-range values diff
(``tests/sheets_values_diff.py``). The Sheets read-fidelity spec upgrades that gate to the **full** fidelity
differ so a **style / number-format / merge / structural** write can also be proven
surgical. The differ has **three legs**:

* the **values leg** — the live used-range values diff, **always**, cheap. It is the
  the value-write gate's leg, **kept as-is**: this module simply **re-exports** the same pure functions
  (:func:`assert_surgical` / :func:`assert_identical` / :func:`changed_cells` /
  :func:`cells_in_range`) from :mod:`sheets_values_diff`, so a plain value write stays on
  exactly the cheap leg the LD-113 gate already uses (no export, no scope);

* the **style/format leg** — **export-based**, behind ``--verify-style`` (AUTO-ON for a
  style/format/merge/structure write; the auto-on trigger itself lives in the engine,
  :mod:`larkdocio.sheets.write_apply`). It diffs the LD-114 export reader's
  ``xl/styles.xml``-derived per-cell resolved style — **bold / italic / fill (ARGB) /
  numFmt pattern** — plus the per-cell ``s=`` style index it resolves, between a
  **baseline** and a **post-write** export (:class:`~larkdocio.sheets.export_reader.ParsedWorkbook`).
  Every finding NAMES the offending sheet + cell + attribute (before→after), actionable
  like the docx gates' evidence lines;

* the **merge leg** — the live v3 ``merges`` array diff (0-idx **end-inclusive**;
  :class:`larkdocio.sheets.models.Merge`), cheap, **no export** — the geometry a values
  read alone can never reconstruct (every covered cell reads ``null``).

Like ``sheets_values_diff`` this is a **pure** gate tool with **no** network/creds surface,
so the live gate (LD-118/S5) asserts a style write surgical live, and the offline suite
(``tests/test_sheets_fidelity_diff.py``) proves each leg red-then-green on synthesized
baseline/post workbooks. It lives in **test infrastructure** (the ``shipped-harness``
posture), not the shipped ``src/`` surface; the shipped half of S3 — the ``--verify-style``
auto-on trigger — is in :mod:`larkdocio.sheets.write_apply`.
"""
from dataclasses import dataclass

from larkdocio.sheets.models import Merge
from larkdocio.sheets.write_range import parse_write_range

# The values leg — re-exported UNCHANGED (the LD-113 leg; plain value writes stay here).
from sheets_values_diff import (  # noqa: F401  (re-export is the point)
    assert_identical,
    assert_surgical,
    cells_in_range,
    changed_cells,
)

# --------------------------------------------------------------------------- #
# The style/format leg — diff the export reader's resolved per-cell style        #
# --------------------------------------------------------------------------- #

#: The resolved style attributes the LD-114 export reader recovers from
#: ``xl/styles.xml`` (via each cell's ``s=`` index) — the style/format leg's diff axes.
_STYLE_ATTRS = ("bold", "italic", "fill_rgb", "num_fmt")

#: The default (no-style) value of each attribute — used when a cell is absent from one
#: side of the diff (a cell that appeared/vanished) so its style change is still caught.
_STYLE_DEFAULTS = {"bold": False, "italic": False, "fill_rgb": None, "num_fmt": None}


@dataclass(frozen=True)
class StyleDiff:
    """One per-cell style/format difference: its ``sheet`` + A1 ``ref`` + the ``attr``
    that changed (``bold`` / ``italic`` / ``fill_rgb`` / ``num_fmt``) + ``before`` →
    ``after``. :meth:`describe` is the actionable one-line evidence string."""

    sheet: str
    ref: str
    attr: str
    before: object
    after: object

    def describe(self) -> str:
        return f"{self.sheet}!{self.ref}.{self.attr}: {self.before!r} -> {self.after!r}"


def _ref_sort_key(ref: str):
    """Deterministic (row, col) sort key for an A1 cell ref, reusing the LD-110 A1 model
    so the differ never forks a parallel parser."""
    wr = parse_write_range(ref)
    return (wr.start.row, wr.start.col)


def _attr(cell, attr):
    """A cell's resolved ``attr`` (or its no-style default when ``cell`` is ``None`` — a
    cell present on only one side of the diff)."""
    return _STYLE_DEFAULTS[attr] if cell is None else getattr(cell, attr)


def style_diffs(before_wb, after_wb):
    """Every per-cell style/format difference between two parsed workbooks (the baseline
    vs post-write export), across every sheet, as an ordered list of :class:`StyleDiff`
    (sheet, then row/col, then attribute order). Compares only the resolved style axes —
    values are the values leg's job.
    """
    b_sheets = {s.name: s for s in before_wb.sheets}
    a_sheets = {s.name: s for s in after_wb.sheets}
    diffs = []
    for name in sorted(set(b_sheets) | set(a_sheets)):
        b_cells = b_sheets[name].cells if name in b_sheets else {}
        a_cells = a_sheets[name].cells if name in a_sheets else {}
        for ref in sorted(set(b_cells) | set(a_cells), key=_ref_sort_key):
            bc = b_cells.get(ref)
            ac = a_cells.get(ref)
            for attr in _STYLE_ATTRS:
                bv = _attr(bc, attr)
                av = _attr(ac, attr)
                if bv != av:
                    diffs.append(StyleDiff(name, ref, attr, bv, av))
    return diffs


def assert_style_clean(before_wb, after_wb):
    """Assert **no** style/format change anywhere (a no-op or value-only write leaves the
    style byte-identical). Raises :class:`AssertionError` naming every drifted cell +
    attribute — the false-positive guard."""
    diffs = style_diffs(before_wb, after_wb)
    assert not diffs, (
        "style/format leg expected NO change, but found: "
        + "; ".join(d.describe() for d in diffs)
    )


#: The style attributes :func:`assert_cell_style` can pin, in a deterministic report
#: order (bold, italic, fill_rgb, num_fmt) — the same axes the export reader resolves.
_ASSERTABLE_ATTRS = ("bold", "italic", "fill_rgb", "num_fmt")


def assert_cell_style(cell, *, ref=None, bold=None, italic=None, fill_rgb=None, num_fmt=None):
    """Assert a parsed :class:`~larkdocio.sheets.export_reader.ExportedCell` carries the
    **exact** resolved-style attributes named — the L2 gate's absolute per-cell fidelity
    check (LD-118).

    Unlike :func:`style_diffs` (a baseline→post *relative* diff), this pins a cell's style
    to explicit expected values: pass ``bold=True, fill_rgb="FFFFFF00", num_fmt="0.00%"`` and
    it asserts the parsed cell resolves to **exactly** those — reproducing LD-107 Q2 through
    the shipped export reader. Only the attributes you NAME are checked (an unnamed
    ``italic`` is ignored), so the gate pins precisely the three it wrote.

    Fails **actionably**: raises :class:`AssertionError` naming the cell ``ref`` and **every**
    attribute that is missing/wrong (``expected -> actual``) in one message — so a QA sees the
    complete gap at once, not one attribute at a time. A ``None`` ``cell`` (the target vanished
    from the export) is a total miss reported the same way, never an ``AttributeError``.
    """
    ref = ref if ref is not None else (getattr(cell, "ref", None) if cell is not None else None)
    expected = {"bold": bold, "italic": italic, "fill_rgb": fill_rgb, "num_fmt": num_fmt}
    mismatches = []
    for attr in _ASSERTABLE_ATTRS:
        want = expected[attr]
        if want is None:
            continue  # unnamed attribute — not asserted
        got = None if cell is None else getattr(cell, attr)
        if got != want:
            mismatches.append(f"{attr} expected {want!r} -> got {got!r}")
    assert not mismatches, (
        f"cell {ref} style fidelity mismatch: " + "; ".join(mismatches)
    )


def assert_style_surgical(before_wb, after_wb, target_refs):
    """Assert the style/format leg is **surgical**: every style change lies **within**
    ``target_refs`` (the cells the write targeted). Raises :class:`AssertionError` naming
    each offending **neighbour** cell + attribute (before→after) when a cell *outside* the
    target changed style — the stray-style catch (a fill/numFmt changed on a neighbour).
    Returns the (in-target) style diffs on success.
    """
    targets = set(target_refs)
    diffs = style_diffs(before_wb, after_wb)
    stray = [d for d in diffs if d.ref not in targets]
    assert not stray, (
        "style/format leg is NOT surgical — style changed OUTSIDE the target(s) "
        f"{sorted(targets)}: " + "; ".join(d.describe() for d in stray)
    )
    return diffs


# --------------------------------------------------------------------------- #
# The merge leg — diff the v3 merges array (0-idx end-inclusive), no export      #
# --------------------------------------------------------------------------- #

def _merge_tuple(m):
    """Normalize a merge region to a ``(start_row, end_row, start_col, end_col)`` tuple
    (0-idx, end-inclusive) — accepting a :class:`~larkdocio.sheets.models.Merge`, a raw
    4-tuple/list, or a v3 ``merges`` dict (``start_row_index``/… keys)."""
    if isinstance(m, Merge):
        return (m.start_row, m.end_row, m.start_col, m.end_col)
    if isinstance(m, (tuple, list)):
        return tuple(m)
    if isinstance(m, dict):
        return (
            m.get("start_row_index"),
            m.get("end_row_index"),
            m.get("start_column_index"),
            m.get("end_column_index"),
        )
    raise TypeError(f"unsupported merge region {m!r}")


def merge_delta(before_merges, after_merges):
    """The ``(added, removed)`` sets of merge-region tuples between two v3 ``merges``
    arrays — cheap, live, **no export**. Each side may hold :class:`Merge` objects, raw
    tuples, or v3 dicts (mixed freely)."""
    before = {_merge_tuple(m) for m in before_merges}
    after = {_merge_tuple(m) for m in after_merges}
    return (after - before, before - after)


def assert_merges_identical(before_merges, after_merges):
    """Assert merge geometry is **unchanged** (a non-merge write must not touch merges).
    Raises :class:`AssertionError` naming the added/removed region(s) — the merge-geometry
    drift catch."""
    added, removed = merge_delta(before_merges, after_merges)
    assert not added and not removed, (
        "merge geometry drifted (v3 merges, 0-idx end-inclusive): "
        f"added={sorted(added)} removed={sorted(removed)}"
    )


def assert_merge_change(before_merges, after_merges, *, added=(), removed=()):
    """Assert the merge delta is **exactly** the expected add/remove — the surgical proof
    for a merge write. Raises :class:`AssertionError` naming the mismatch (got vs
    expected)."""
    got_added, got_removed = merge_delta(before_merges, after_merges)
    exp_added = {_merge_tuple(m) for m in added}
    exp_removed = {_merge_tuple(m) for m in removed}
    assert got_added == exp_added and got_removed == exp_removed, (
        f"merge delta mismatch: got added={sorted(got_added)} removed={sorted(got_removed)}; "
        f"expected added={sorted(exp_added)} removed={sorted(exp_removed)}"
    )


# --------------------------------------------------------------------------- #
# The destructive-safe leg — a delete's apply-log removed payload must be        #
# COMPLETE enough to reconstruct what was destroyed (LD-123/D5, raised here to   #
# a reusable gate assertion for the arc's final live gate, LD-124/AC3).          #
# --------------------------------------------------------------------------- #

#: The reconstruct-critical fields a dimension delete's removed payload MUST carry so the
#: apply-log ALONE reconstructs what was destroyed (the snapshot
#: ``larkdocio.sheets.ops._snapshot_removed_dimension`` records at plan time): the
#: addressing ``a1_range``, the removed ``values``, and the pre-write ``geometry``.
_REMOVED_PAYLOAD_FIELDS = ("a1_range", "values", "geometry")


def assert_removed_payload_complete(removed, *, expected_values=None):
    """Assert a destructive dimension delete's apply-log removed payload is **complete** —
    enough to **reconstruct** what the delete destroyed (the LD-123/D5 destructive-safe
    contract, raised here to a reusable gate assertion for the arc's final live gate,
    LD-124/AC3).

    ``removed`` is the ``entry.structural["removed"]`` an applied row/col delete carries
    (:func:`larkdocio.sheets.ops._snapshot_removed_dimension`). A complete payload
    carries the addressing :data:`a1_range`, the removed :data:`values`, and the pre-write
    :data:`geometry`. This assertion:

    * raises :class:`AssertionError` naming **every** missing/``None`` field in one message
      (a QA sees the whole gap at once), never a ``KeyError``/``TypeError`` on a ``None`` or
      partial payload — so an engine snapshot regression that drops a field reddens the live
      gate loudly rather than passing a broken destructive write;
    * when ``expected_values`` is given, additionally asserts the removed values equal it
      byte-exact — the removal is **reconstructable**, not merely present.

    Returns the removed values on success (the reconstructed grid).
    """
    assert removed is not None, (
        "no removed payload on the delete's apply-log — the destructive-safe engine must "
        "snapshot the removed values + geometry (or REFUSE the delete); there is nothing "
        "to reconstruct from"
    )
    missing = [
        f for f in _REMOVED_PAYLOAD_FIELDS
        if (removed.get(f) if isinstance(removed, dict) else None) is None
    ]
    have = sorted(removed) if isinstance(removed, dict) else repr(removed)
    assert not missing, (
        "removed payload is INCOMPLETE — cannot reconstruct the destroyed cells; missing "
        f"reconstruct-critical field(s): {', '.join(missing)} (have: {have})"
    )
    values = removed["values"]
    if expected_values is not None:
        assert values == expected_values, (
            "removed payload does not reconstruct the expected destroyed grid "
            f"(expected {expected_values!r}, got {values!r})"
        )
    return values
