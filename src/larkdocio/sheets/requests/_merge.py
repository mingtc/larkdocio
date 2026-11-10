"""larkdocio.sheets.requests._merge — merge / unmerge — the destructive-safe merge family and the merge-variant fence.

The only family with no mixin base: a merge request is neither cell-, structural- nor
tab-shaped, and its two members share their posture inline.

Split out of the flat 2,462-line ``sheets/requests.py`` by LD-224, **verbatim** —
pre-split lines 1654–1871. The package's ``__init__`` re-exports every name defined here,
so ``from larkdocio.sheets.requests import <name>`` is unchanged.
"""
from dataclasses import dataclass

from larkdocio.errors import LarkConfigError
from larkdocio.sheets.write_range import A1Cell, WriteRange, parse_write_range

from ._gates import WriteOpKind


# --------------------------------------------------------------------------- #
# Merge / unmerge writes (LD-122, D4).                                         #
#                                                                               #
# ANCHOR-VALUE semantics: MERGE_ALL keeps the top-left (anchor) cell's value;   #
# every COVERED cell's value is LOST. The mandatory dry-run PREVIEWS that loss  #
# explicitly (delete-log parity). The write flows through the gated engine      #
# (revision compare-and-swap, STALE_SHEET) and the merge leg (LD-116's v3       #
# `merges` diff) verifies the geometry after the write.                         #
#                                                                               #
# ONE MERGE TYPE (LD-190). Those semantics are MERGE_ALL's, and only            #
# MERGE_ALL's: MERGE_ROWS / MERGE_COLUMNS were characterized live and produce   #
# ONE MERGE PER ROW / PER COLUMN, keeping every row leader / column top — so    #
# the single-anchor loss preview above OVER-REPORTED the loss for them (it      #
# called a surviving cell LOST) on a DESTRUCTIVE write. The variants are        #
# therefore REFUSED at construction rather than shipped half-modelled; see      #
# MERGE_VARIANTS_NOT_GATE_COVERED for the evidence and the repair.              #
# --------------------------------------------------------------------------- #

#: The one merge type larkdocio supports, gate-covers and models correctly.
MERGE_ALL = "MERGE_ALL"

#: The merge types the endpoint accepts and larkdocio **refuses** — characterized live, refused
#: because the shipped loss preview does not describe them (see below).
MERGE_VARIANTS_REFUSED = ("MERGE_ROWS", "MERGE_COLUMNS")

#: The merge types a caller may pass. A ``frozenset`` of exactly one member, deliberately:
#: ``capabilities()``'s ``merge_types`` is projected off THIS, so a later rung that ships a
#: variant properly widens the published answer by widening this — never by editing a doc.
SUPPORTED_MERGE_TYPES = frozenset({MERGE_ALL})

#: Lark's code for a ``mergeType`` it does not accept — the same generic ``90204`` the style
#: family uses, so again the ``msg`` is what names the cause.
MERGE_TYPE_REFUSAL_CODE = 90204

#: Lark's **verbatim** answer to a ``mergeType`` it rejects (probed three ways: a nonsense value,
#: lower-case ``"merge_rows"``, and whitespace-padded ``" MERGE_ROWS "``).
MERGE_TYPE_REFUSAL_BODY = "invalid mergeType"

#: **The limit, stated once, loudly** — quoted verbatim by ``GUIDE.md`` and, in the source repository
#: rather than in the wheel, by ``SHEETS.md``, so the three cannot drift. This is not
#: "untested": the shipped preview was **wrong** for these two, and a destructive write whose
#: disclosure over-reports the loss teaches a consumer to accept a
#: loss that is not happening — or, worse, trains them not to read the preview at all.
MERGE_VARIANTS_NOT_GATE_COVERED = (
    "MERGE_ROWS AND MERGE_COLUMNS ARE REFUSED, and not merely untested: larkdocio's merge loss "
    "preview DESCRIBES THEM WRONG. Probed live on a disposable — MERGE_ROWS over a 2x2 produced "
    "TWO merged regions, one per row, and BOTH rows' leading cells kept their values; "
    "MERGE_COLUMNS is the same fault transposed, one region per column with every column's top "
    "cell kept. The shipped preview reports ONE anchor and ONE rectangle, so on that same 2x2 it "
    "named a cell as lost that the write KEPT. An over-reported loss on a destructive op is a "
    "MIS-DISCLOSURE, so the variants are refused at construction (zero API calls) rather than "
    "offered with a preview that cannot be trusted. What to do instead: express the merge you "
    "want as MERGE_ALL merges, one per row or per column — a single-row range under MERGE_ROWS "
    "is exactly MERGE_ALL, which the same probe confirmed — and each one previews its own loss "
    "correctly. Lark itself is strict about the value: a nonsense mergeType, 'merge_rows' and "
    "' MERGE_ROWS ' each answered the generic '90204' with msg 'invalid mergeType' and landed nothing, so nothing is "
    "silently repaired here either. Evidence: "
    "tests/captures/sheets-merge-variant-probe/captures/01-merge-variant-characterization.json "
    "in the source repository."
)


class MergeTypeError(LarkConfigError, ValueError):
    """A merge was asked for with a ``merge_type`` larkdocio does not support.

    Raised at **construction**, so a merge whose loss larkdocio cannot preview correctly cannot
    be built and costs zero API calls — the :class:`StyleError` / :class:`DimensionPropertyError`
    house standard, and **deliberately a subclass of BOTH**
    :class:`~larkdocio.errors.LarkConfigError` and :class:`ValueError` exactly as they are.
    """


def _require_supported_merge_type(value) -> None:
    """The one place a ``merge_type`` is checked. **Exact** string equality — no up-casing, no
    stripping: Lark refuses ``'merge_rows'`` and ``' MERGE_ROWS '`` itself (probed), and quietly
    repairing a caller's value would hide that strictness."""
    if isinstance(value, str) and value in SUPPORTED_MERGE_TYPES:
        return
    supported = ", ".join(repr(t) for t in sorted(SUPPORTED_MERGE_TYPES))
    raise MergeTypeError(
        f"MergeCells: merge_type must be exactly {supported}, got {value!r}. "
        f"{MERGE_VARIANTS_NOT_GATE_COVERED} Write MergeCells('<sheet_id>!A1:C1') — "
        f"{MERGE_ALL} is the default and needs no argument."
    )


def _region_of(a1_range: str) -> tuple:
    """The 0-idx END-inclusive merge region ``(sr, er, sc, ec)`` of an A1 range (the v3
    ``merges`` convention) — a 1-idx ``WriteRange`` translated to the merge coordinate space."""
    wr = parse_write_range(a1_range)
    return (wr.start.row - 1, wr.end.row - 1, wr.start.col - 1, wr.end.col - 1)


@dataclass(frozen=True)
class MergeCells:
    """Merge ``a1_range`` on its tab (``merge_cells``, :data:`MERGE_ALL` — the only type).

    **Anchor-value semantics:** the top-left cell keeps its value; every covered
    cell's value is DISCARDED. The mandatory dry-run reads the range and previews the
    loss EXPLICITLY (:meth:`loss_preview` — every covered non-null value enumerated,
    delete-log parity), so a merge is never a blind data-losing write. The ``a1_range``
    carries the ``{sheet_id}!`` prefix (the tab the merge lives on + the geometry re-read).

    **``merge_type`` is validated at construction** and accepts only :data:`MERGE_ALL`.
    ``MERGE_ROWS`` / ``MERGE_COLUMNS`` raise :class:`MergeTypeError` because the loss preview
    above is MERGE_ALL's model and was measured to **over-report the loss** for them — the
    reason, the live evidence and the MERGE_ALL-per-row repair are in
    :data:`MERGE_VARIANTS_NOT_GATE_COVERED`.
    """

    a1_range: str
    merge_type: str = MERGE_ALL

    def __post_init__(self):
        _require_supported_merge_type(self.merge_type)

    write_kind = "merge"
    is_rich = False

    @property
    def op_kinds(self) -> tuple:
        """A merge write TOUCHES merge geometry — :data:`WriteOpKind.MERGE` (the live v3
        merge leg proves it; the export style leg is also auto-on for a merge)."""
        return (WriteOpKind.MERGE,)

    @property
    def target(self) -> WriteRange:
        return parse_write_range(self.a1_range)

    def descriptor(self) -> dict:
        wr = self.target
        return {
            "op": "merge",
            "sheet_id": wr.sheet_id,
            "a1_range": self.a1_range,
            "merge_type": self.merge_type,
            "region": list(_region_of(self.a1_range)),
            "semantic": f"merge {self.a1_range} ({self.merge_type})",
        }

    def loss_preview(self, before_values) -> dict:
        """Preview the anchor-value loss: the anchor kept, every covered cell enumerated,
        and the covered cells whose current value is **non-null** flagged as LOST."""
        wr = self.target
        sr, er = wr.start.row, wr.end.row
        sc, ec = wr.start.col, wr.end.col
        rows = before_values or []

        def _cell(r, c):
            i, j = r - sr, c - sc
            if 0 <= i < len(rows):
                row = rows[i]
                if isinstance(row, list) and 0 <= j < len(row):
                    return row[j]
            return None

        anchor_ref = A1Cell(sc, sr).a1()
        anchor_value = _cell(sr, sc)
        covered, lost = [], []
        for r in range(sr, er + 1):
            for c in range(sc, ec + 1):
                if r == sr and c == sc:
                    continue  # the anchor
                ref = A1Cell(c, r).a1()
                val = _cell(r, c)
                cell = {"ref": ref, "value": val}
                covered.append(cell)
                if val is not None and val != "":
                    lost.append(cell)
        return {
            "kind": "merge",
            "merge_region": list(_region_of(self.a1_range)),
            "anchor": {"ref": anchor_ref, "value": anchor_value},
            "covered": covered,
            "covered_count": len(covered),
            "lost_values": lost,
            "lost_count": len(lost),
        }


@dataclass(frozen=True)
class UnmergeCells:
    """Dissolve the merge covering ``a1_range`` (``unmerge_cells``).

    After the unmerge the covered cells become independent (empty) cells; the anchor
    retains its value — **no** value is restored to the covered cells (characterized,
    not reconstructed; a value restore would be a separate destructive-safe concern).
    The dry-run previews the region being dissolved (deterministic — no read)."""

    a1_range: str

    write_kind = "merge"
    is_rich = False

    @property
    def op_kinds(self) -> tuple:
        return (WriteOpKind.MERGE,)

    @property
    def target(self) -> WriteRange:
        return parse_write_range(self.a1_range)

    def descriptor(self) -> dict:
        wr = self.target
        return {
            "op": "unmerge",
            "sheet_id": wr.sheet_id,
            "a1_range": self.a1_range,
            "region": list(_region_of(self.a1_range)),
            "semantic": f"unmerge {self.a1_range}",
        }

    def dissolve_preview(self) -> dict:
        return {
            "kind": "unmerge",
            "merge_region": list(_region_of(self.a1_range)),
            "note": ("after unmerge the covered cells become independent empty cells; "
                     "the anchor retains its value (no value restored to covered cells)"),
        }
