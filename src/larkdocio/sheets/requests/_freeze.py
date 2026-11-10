"""larkdocio.sheets.requests._freeze — FREEZE PANES — ``updateSheet`` objects riding the tab family's endpoint.

Its own :class:`_FreezeWrite` posture, but it builds its wire element through
``_tabs``' shared :func:`update_sheet_element`.

Split out of the flat 2,462-line ``sheets/requests.py`` by LD-224, **verbatim** —
pre-split lines 1977–2182. The package's ``__init__`` re-exports every name defined here,
so ``from larkdocio.sheets.requests import <name>`` is unchanged.
"""
from dataclasses import dataclass
from typing import Optional

from larkdocio.errors import LarkConfigError

from ._gates import WriteOpKind
from ._tabs import update_sheet_element


# --------------------------------------------------------------------------- #
# FREEZE PANES (LD-186) — `updateSheet` objects inside the ALREADY-SHIPPED      #
# `sheets_batch_update`, so this family adds ZERO new HTTP surface. It rides    #
# the same request-element seam the tab family owns (`request_element` in the   #
# descriptor), which is what lets a later tab-presentation op extend rather     #
# than fork it.                                                                #
#                                                                              #
# Everything below is PROBED, not inferred (tests/captures/sheets-freeze-probe/):          #
#                                                                              #
#   * `properties` is a PATCH, not a REPLACE. Naming only `frozenRowCount`      #
#     leaves the tab's title, index, hidden flag AND `frozenColCount` intact.   #
#     A REPLACE reading would have silently unfrozen the other axis.            #
#   * `frozenRowCount == rowCount` is ACCEPTED (all rows frozen, code 0);       #
#     `rowCount + 1` answers `90226 frozenRowCount must less than sheet         #
#     rowCount` — so the real ceiling is `<= count` and Lark's own message      #
#     misstates it. The refusal follows the PROBE, not the wording.             #
#   * `0` is accepted and UNFREEZES; `-1` answers `90226 … must larger than 0`. #
#   * `properties` naming only `sheetId` answers `90204 request body is wrong`. #
#   * a bool count answers `9499 Invalid parameter type in json:               #
#     FrozenRowCount`.                                                         #
# --------------------------------------------------------------------------- #

class FreezeError(LarkConfigError, ValueError):
    """A freeze-panes write is not writable **as given**.

    Raised at **construction**, so a request Lark would reject — or accept while doing
    something other than what the caller meant — **cannot be built** and costs zero API calls.
    Each message names the fault, the consequence, the repair and a valid-form example (the
    :class:`DimensionPropertyError` / :class:`~larkdocio.sheets.formula.FormulaExpressionError`
    house standard) and quotes the **probed** Lark answer it pre-empts:

    * **neither** axis given → ``90204 request body is wrong`` (an ``updateSheet`` naming only
      a ``sheetId`` asks for nothing);
    * a **negative** count → ``90226 frozenRowCount must larger than 0``;
    * a **bool** count → ``9499 Invalid parameter type in json: FrozenRowCount``;
    * a **non-whole** count (a float) — not expressible on the wire at all.

    A count **past the tab's grid** is deliberately NOT here: it is not knowable from the
    caller's arguments alone (it needs the tab's ``rowCount``), so it refuses at **plan time**
    off the read the preview already makes — :data:`~larkdocio.sheets.plan.Refusal
    .FROZEN_COUNT_OUT_OF_RANGE`.

    **Deliberately a subclass of BOTH** :class:`~larkdocio.errors.LarkConfigError` (so
    ``except LarkConfigError`` / ``except LarkDocIOError`` catches it, and the apply-time
    disposition boundary would classify it ``invalid-request``) **and** :class:`ValueError`,
    exactly as :class:`DimensionSpanError` and :class:`DimensionPropertyError` are.
    """


class _FreezeWrite:
    """Mixin marking a request as a **freeze-panes** write (LD-186).

    Its own :attr:`write_kind` and its own :data:`WriteOpKind.FREEZE_PANES`, and — like
    ``TAB`` / ``DATA_VALIDATION`` / ``DIMENSION_PROPERTY`` — deliberately **not** the
    structural family: a freeze moves nothing. No row shifts, no merge changes shape, no cell
    changes value, and the declared grid (``rowCount`` / ``columnCount``) is untouched, so
    ``is_structural`` is ``False`` and the structural leg's geometry-delta verification would
    only ever measure a zero.
    """

    write_kind = "freeze-panes"
    is_structural = False
    is_rich = False

    @property
    def op_kinds(self) -> tuple:
        return (WriteOpKind.FREEZE_PANES,)


def _freeze_count(name: str, value, *, sheet_id) -> int:
    """One validated frozen count, or a :class:`FreezeError` naming the probed refusal."""
    example = (f"FreezePanes(sheet_id={sheet_id!r}, rows=2)" if name == "rows"
               else f"FreezePanes(sheet_id={sheet_id!r}, cols=1)")
    wire = "frozenRowCount" if name == "rows" else "frozenColCount"
    if isinstance(value, bool):
        raise FreezeError(
            f"FreezePanes: `{name}` must be a whole number of {name} to freeze, got "
            f"{value!r}. A bool is refused rather than coerced — Lark answers this exact body "
            f"('9499 Invalid parameter type in json: {wire}. Invalid parameter value: "
            f"{str(value).lower()}'), and `True` would silently mean "
            f"\"freeze 1\" under Python's int-subclass rule, which nobody means. Write "
            f"{example}."
        )
    if not isinstance(value, int):
        raise FreezeError(
            f"FreezePanes: `{name}` must be a whole number, got {value!r}. A fractional count "
            f"is not expressible — a freeze pins whole {name}. Write {example}."
        )
    if value < 0:
        raise FreezeError(
            f"FreezePanes: `{name}` must be 0 or more, got {value}. Lark refuses a negative "
            f"count itself ('90226 {wire} must larger than 0'), a message that names neither "
            f"the fault nor the repair — so it is refused here, before any call. Note that "
            f"**0 is legal and means UNFREEZE** on that axis: write "
            f"FreezePanes.unfreeze(sheet_id={sheet_id!r}) to clear both axes, or {example} if "
            f"you meant that many {name}."
        )
    return value


def _freeze_semantic(rows, cols) -> str:
    """The English restatement of the intent (the ``semantic`` every gated op carries)."""
    parts = []
    if rows is not None:
        parts.append("unfreeze all rows" if rows == 0
                     else f"freeze the first {rows} row(s)")
    if cols is not None:
        parts.append("unfreeze all columns" if cols == 0
                     else f"freeze the first {cols} column(s)")
    return " and ".join(parts)


@dataclass(frozen=True)
class FreezePanes(_FreezeWrite):
    """Freeze (or unfreeze) a tab's leading rows and/or columns — an ``updateSheet`` request.

    ``rows`` / ``cols`` are **counts, not indexes**, so there is no index-convention trap on
    this op at all: ``rows=2`` pins the first two rows, and ``0`` means *nothing pinned on that
    axis* (the unfreeze). At least one axis must be given.

    **An axis you do not name is left alone.** ``properties`` is a **PATCH** — probed live: a
    request naming only ``frozenRowCount`` leaves the tab's ``frozenColCount``, title, index and
    ``hidden`` flag exactly as they were. So ``FreezePanes(sheet_id, rows=2)`` on a tab with a
    frozen column keeps that column frozen, and clearing **both** axes is
    :meth:`unfreeze`, never a rows-only ``0``.

    **What cannot be built** (all zero-cost, all quoting the probed Lark body they pre-empt):
    a request naming neither axis, a negative count, a bool, a fractional count — see
    :class:`FreezeError`. A count past the tab's own ``rowCount`` / ``columnCount`` refuses at
    **plan time** instead, because it is not knowable without reading the tab.
    """

    sheet_id: str
    rows: Optional[int] = None
    cols: Optional[int] = None

    def __post_init__(self):
        if self.rows is None and self.cols is None:
            raise FreezeError(
                f"FreezePanes: no axis to freeze — a freeze must carry `rows` and/or `cols`, "
                f"and this one carries neither, so it names a tab and asks for nothing (Lark "
                f"answers this exact body '90204 request body is wrong' for an updateSheet "
                f"whose properties hold only a sheetId; the request cannot be built, which is "
                f"why you see this instead of a surprise at apply). Write "
                f"FreezePanes(sheet_id={self.sheet_id!r}, rows=2), "
                f"FreezePanes(sheet_id={self.sheet_id!r}, cols=1), both together, or "
                f"FreezePanes.unfreeze(sheet_id={self.sheet_id!r}) to clear both axes."
            )
        if self.rows is not None:
            _freeze_count("rows", self.rows, sheet_id=self.sheet_id)
        if self.cols is not None:
            _freeze_count("cols", self.cols, sheet_id=self.sheet_id)

    @classmethod
    def unfreeze(cls, sheet_id: str) -> "FreezePanes":
        """Clear **both** axes — ``frozenRowCount: 0, frozenColCount: 0`` in one request.

        A named intent rather than a magic zero, and it names *both* axes deliberately: because
        ``properties`` is a PATCH, a rows-only ``0`` would leave a frozen column pinned, which
        is not what "unfreeze" means to anyone.
        """
        return cls(sheet_id=sheet_id, rows=0, cols=0)

    @property
    def properties(self) -> dict:
        """The validated ``updateSheet.properties`` wire dict.

        Only the axes the caller named appear — the PATCH contract, expressed structurally so a
        request cannot accidentally zero an axis it was never asked about.
        """
        props = {"sheetId": self.sheet_id}
        if self.rows is not None:
            props["frozenRowCount"] = _freeze_count("rows", self.rows, sheet_id=self.sheet_id)
        if self.cols is not None:
            props["frozenColCount"] = _freeze_count("cols", self.cols, sheet_id=self.sheet_id)
        return props

    def descriptor(self) -> dict:
        props = self.properties
        return {
            "op": "freeze-panes",
            "sheet_id": self.sheet_id,
            "rows": self.rows,
            "cols": self.cols,
            "request_element": update_sheet_element(props),
            "unfreezes": (self.rows == 0 and self.cols == 0),
            "semantic": _freeze_semantic(self.rows, self.cols) + f" on tab {self.sheet_id}",
        }

    def freeze_preview(self) -> dict:
        """The previewed change — what the write sets, and the explicit statement of what it
        leaves alone (which is why this op is off the export style leg and the merge leg)."""
        return {
            "kind": "freeze-panes",
            "frozen_rows": self.rows,
            "frozen_cols": self.cols,
            "unfreezes": (self.rows == 0 and self.cols == 0),
            "patch": True,
            "unnamed_axis_preserved": [
                axis for axis, asked in (("frozen_rows", self.rows), ("frozen_cols", self.cols))
                if asked is None
            ],
            "changes_values": False,
            "changes_geometry": False,
            "changes_merges": False,
        }
