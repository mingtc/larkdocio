"""larkdocio.sheets.requests._gates — the write op-kind vocabulary + the fidelity-leg gate certification.

The vocabulary every other module in this package classifies itself against
(:class:`WriteOpKind`) and the gate-leg trigger/certification functions the engine computes
from it. Depends on no request family — it is the package's root.

Split out of the flat 2,462-line ``sheets/requests.py`` by LD-224, **verbatim** —
pre-split lines 43–169. The package's ``__init__`` re-exports every name defined here,
so ``from larkdocio.sheets.requests import <name>`` is unchanged.
"""
from larkdocio.errors import LarkDocIOError


# --------------------------------------------------------------------------- #
# Write op-kinds + the write-gate fidelity-leg trigger (LD-116, D4). The         #
# two-leg (three-leg) write-gate differ proves a write **surgical**;            #
# WHICH legs it must run is a function of what the write TOUCHES — so the engine  #
# (which knows its op types) computes the trigger, not a caller's memory.        #
# --------------------------------------------------------------------------- #

class WriteOpKind:
    """What a sheet write TOUCHES — the classification the write-gate fidelity differ
 keys its leg selection on.

    The current engine emits only :data:`VALUE` writes (rich/structural writes are
    refused ``RICH_CELL_TARGET``); the :data:`STYLE` / :data:`NUMBER_FORMAT` /
    :data:`MERGE` / :data:`STRUCTURE` kinds classify a *future* write so the
    ``--verify-style`` auto-on trigger is wired **here in the engine**, not carried in a
    caller's memory. A string enum (not :class:`enum.Enum`) to stay trivially JSON/log
    friendly, matching the module's other typed-string vocabularies.
    """

    VALUE = "value"
    STYLE = "style"
    NUMBER_FORMAT = "number-format"
    MERGE = "merge"
    STRUCTURE = "structure"
    #: A tab (add/copy/delete via ``sheets_batch_update``) write (LD-122).
    #: A tab op changes the spreadsheet's tab SET, not a sheet's cell geometry, so it is
    #: deliberately **not** in :data:`STYLE_LEG_OP_KINDS` / :data:`MERGE_LEG_OP_KINDS` — it
    #: is verified by its own v3 tab-query diff (the "tab leg"), never the export style leg
    #: or the merge leg (the same posture as :data:`DATA_VALIDATION`).
    TAB = "tab"
    #: A dropdown (``dataValidation``) list-rule write (LD-120). It is
    #: deliberately **not** in :data:`STYLE_LEG_OP_KINDS` / :data:`MERGE_LEG_OP_KINDS` — a
    #: rule is verified by its own ``dataValidation`` GET (the S6/LD-124 "rule leg"), not the
    #: export style leg or the v3 merge leg, so it triggers neither ``--verify-style`` auto-on
    #: nor the merge leg.
    DATA_VALIDATION = "data-validation"
    #: A row/column **dimension-property** write — height / width / hide-show (LD-185,
    #: ``PUT …/dimension_range`` with ``dimensionProperties{visible, fixedSize}``). Like
    #: :data:`TAB` and :data:`DATA_VALIDATION` it is deliberately **not** in
    #: :data:`STYLE_LEG_OP_KINDS` / :data:`MERGE_LEG_OP_KINDS`: it changes **presentation**,
    #: not cell content and not merge geometry, so it is verified by **its own dimension leg**
    #: (:data:`~larkdocio.sheets.ops.DIMENSION_VERIFICATION_LEG`) and never by the export style
    #: leg — forcing an async whole-workbook export (~1.2 s, up to ~30 s) on a column-width
    #: change would be absurd.
    DIMENSION_PROPERTY = "dimension-property"
    #: A **freeze-panes** write — how many leading rows/columns a tab keeps pinned (LD-186,
    #: ``updateSheet`` objects inside the already-shipped ``sheets_batch_update``). The third
    #: member of the ``TAB`` / ``DATA_VALIDATION`` posture, and for the plainest reason yet:
    #: freeze is **view state**. It is not cell content (so the export style leg has nothing to
    #: compare), not merge geometry (so the v3 merge leg has nothing to compare) and not grid
    #: geometry (``rowCount`` / ``columnCount`` do not move — probed). It is verified by **its
    #: own frozen read** (:data:`~larkdocio.sheets.ops.FREEZE_VERIFICATION_LEG` — the
    #: ``metainfo`` frozen counts LD-186 also shipped), which is cheap enough to run inside
    #: ``apply``, unlike the dimension leg's export.
    FREEZE_PANES = "freeze-panes"


#: The op-kinds whose surgical proof needs the **export-based style/format leg** —
#: ``--verify-style`` AUTO-ON (D4): a style / number-format / merge / structure write.
STYLE_LEG_OP_KINDS = frozenset(
    {WriteOpKind.STYLE, WriteOpKind.NUMBER_FORMAT, WriteOpKind.MERGE, WriteOpKind.STRUCTURE}
)

#: The op-kinds whose surgical proof needs the live **v3 merges leg** (no export): a
#: merge / structure write.
MERGE_LEG_OP_KINDS = frozenset({WriteOpKind.MERGE, WriteOpKind.STRUCTURE})


class GateNotVerified(LarkDocIOError):
    """A write's fidelity gate cannot be certified surgical — a required leg did not run.

    Under :class:`~larkdocio.errors.LarkDocIOError` so ``except LarkDocIOError`` catches it
    alongside the API/config family. Raised by :func:`certify_gate_legs` — the invariant
    that a **style write cannot be gate-verified without the export-based style leg**.
    """


def requires_style_leg(op_kinds) -> bool:
    """True iff any op-kind in ``op_kinds`` needs the **export-based style/format leg** —
    i.e. the write touches style / number-format / merge / structure (the ``--verify-style``
    auto-on set). A plain value write → ``False`` (cheap values leg only, no export)."""
    return bool(set(op_kinds) & STYLE_LEG_OP_KINDS)


def requires_merge_leg(op_kinds) -> bool:
    """True iff any op-kind in ``op_kinds`` needs the live **v3 merges leg** — i.e. the
    write touches merge / structure geometry (no export)."""
    return bool(set(op_kinds) & MERGE_LEG_OP_KINDS)


def effective_verify_style(op_kinds, verify_style: bool = False) -> bool:
    """The **effective** ``--verify-style`` for a write of ``op_kinds``: the explicit flag
    **OR** the auto-on trigger. A plain value write leaves it ``False`` (no export)
    unless the caller forced it; a style/format/merge/structure write turns it ``True``
    regardless of the flag."""
    return bool(verify_style) or requires_style_leg(op_kinds)


def certify_gate_legs(op_kinds, *, values_leg_ran, style_leg_ran=False, merge_leg_ran=False):
    """Assert every fidelity leg a write of ``op_kinds`` requires actually ran — so a write
    can only be certified surgical once its required legs have proven it.

    * the **values leg** is ALWAYS required (the cheap live used-range diff);
    * the export-based **style/format leg** is required for a style / number-format /
      merge / structure write (``--verify-style`` auto-on);
    * the live **merge leg** is required for a merge / structure write.

    Raises :class:`GateNotVerified` NAMING the missing leg — the load-bearing invariant
    that a style write **cannot** be gate-verified on the cheap values leg alone.
    """
    kinds = set(op_kinds)
    if not values_leg_ran:
        raise GateNotVerified(
            "the always-on values leg did not run — no write can be certified surgical "
            "without it"
        )
    if requires_style_leg(kinds) and not style_leg_ran:
        raise GateNotVerified(
            f"write touches {sorted(kinds & STYLE_LEG_OP_KINDS)} — the export-based "
            f"style/format leg (--verify-style auto-on) is REQUIRED to prove it "
            f"surgical, but did not run"
        )
    if requires_merge_leg(kinds) and not merge_leg_ran:
        raise GateNotVerified(
            f"write touches {sorted(kinds & MERGE_LEG_OP_KINDS)} — the live v3 merges leg "
            f"is REQUIRED to prove merge geometry, but did not run"
        )
