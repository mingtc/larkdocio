"""larkdocio.sheets.requests._tab_presentation — tab PRESENTATION — reorder / retitle / hide-show.

The one family whose mixin genuinely subclasses another family's:
:class:`_TabPresentation` extends ``_tabs``' :class:`_TabWrite`, which is real inheritance
rather than an artifact of the split, so it travels here with the three requests it bases.

Split out of the flat 2,462-line ``sheets/requests.py`` by LD-224, **verbatim** —
pre-split lines 2185–2460. The package's ``__init__`` re-exports every name defined here,
so ``from larkdocio.sheets.requests import <name>`` is unchanged.
"""
from dataclasses import dataclass

from larkdocio.errors import LarkConfigError

from ._tabs import _TabWrite, update_sheet_element


# --------------------------------------------------------------------------- #
# TAB PRESENTATION (LD-187) — the other three `updateSheet` fields: `index`      #
# (reorder), `title` (retitle) and `hidden` (hide/show). They ride the SAME      #
# element builder and the SAME endpoint as freeze, and they reuse the SHIPPED    #
# `WriteOpKind.TAB`: what they change is the tab set's presentation and          #
# identity, which is what `TAB` already denotes, and they are verified by the    #
# tab family's own v3 tab-query diff.                                           #
#                                                                              #
# Everything asserted below is PROBED (tests/captures/sheets-tab-presentation-probe/):      #
#                                                                              #
#   * `index` is a TARGET POSITION, 0-based — not a delta. A tab at 0 asked for  #
#     `index: 2` lands at 2, and the tabs it passes close the gap.              #
#   * an index PAST the last tab is SILENTLY CLAMPED (`index: 4` and `index: 99` #
#     on a 4-tab spreadsheet both answer `code 0`, tab left last). Only `-1`     #
#     is refused: `90204 invalid parameter:                                     #
#     Requests[0].UpdateSheet.Properties.Index`.                                #
#   * a no-op reorder is accepted and does NOT bump `revision` (a no-op freeze   #
#     DOES bump — freeze and presentation genuinely differ here).               #
#   * an EMPTY title answers `90207 sheetTitle should not be empty`; a DUPLICATE #
#     answers `90210 sheetTitle already exist in snapshot` — but the uniqueness  #
#     check is CASE-SENSITIVE, so `gamma` beside `Gamma` is accepted.           #
#   * no title-length ceiling was found at 101 characters (100 and 101 both      #
#     answered `code 0` and the 101-character title landed), so none is invented.#
#   * a retitle leaves the `sheet_id` UNCHANGED — the id is the stable handle.   #
#   * hiding the LAST visible tab answers `95201 server error`.                  #
#   * a hidden tab's values stay fully readable through this library (written    #
#     and read back WHILE hidden).                                              #
# --------------------------------------------------------------------------- #

class TabPresentationError(LarkConfigError, ValueError):
    """A tab reorder / retitle / hide-show is not writable **as given**.

    Raised at **construction**, so a request Lark would reject — or accept while doing
    something other than what the caller meant — **cannot be built** and costs zero API calls.
    Each message names the fault, the consequence, the repair and a valid-form example (the
    :class:`FreezeError` / :class:`DimensionPropertyError` house standard) and quotes the
    **probed** Lark answer it pre-empts where there is one:

    * a **negative** index → ``90204 invalid parameter:
      Requests[0].UpdateSheet.Properties.Index``;
    * a **bool** / **fractional** / non-numeric index — a position is a whole number;
    * an **empty** title → ``90207 sheetTitle should not be empty``;
    * a **whitespace-only** or non-string title — this library's own stricter rule (a title
      that renders as blank is indistinguishable from the empty one Lark refuses), labelled as
      such rather than attributed to Lark;
    * a non-``bool`` visibility — ``hidden`` is a flag, and ``1`` / ``"true"`` would have to be
      guessed at.

    The faults that need the **tab set** to be known — an index past the last tab, a duplicate
    title, hiding the last visible tab — are not here: they refuse at **plan time** off the tab
    query the preview already makes (:data:`~larkdocio.sheets.plan.Refusal
    .TAB_INDEX_OUT_OF_RANGE` / ``DUPLICATE_TAB_TITLE`` / ``LAST_VISIBLE_TAB``).

    **Deliberately a subclass of BOTH** :class:`~larkdocio.errors.LarkConfigError` **and**
    :class:`ValueError`, exactly as :class:`FreezeError` is.
    """


class _TabPresentation(_TabWrite):
    """Mixin: the shared shape of the three presentation writes — a ``sheet_id`` plus one
    ``updateSheet`` property, on the shipped :data:`WriteOpKind.TAB` posture.

    ``is_structural`` is ``False``: a presentation write moves no row, no merge and no cell,
    and the declared grid does not change — probed. So the structural leg's geometry-delta
    verification would only ever measure a zero, exactly as for freeze.
    """

    is_structural = False

    def descriptor(self) -> dict:
        return {
            "op": self.op,
            "sheet_id": self.sheet_id,
            "request_element": update_sheet_element(self.properties),
            "semantic": self.semantic,
            **self.fields,
        }

    def presentation_preview(self) -> dict:
        """The previewed change — what the write sets, and the explicit statement of what it
        leaves alone (which is why this op is off the export style leg and the merge leg)."""
        return {
            "kind": self.op,
            **self.fields,
            "changes_values": False,
            "changes_geometry": False,
            "changes_merges": False,
        }


def _whole_index(value, *, sheet_id) -> int:
    """One validated 0-based target position, or a :class:`TabPresentationError`."""
    example = f"ReorderTab(sheet_id={sheet_id!r}, index=0)"
    if isinstance(value, bool):
        raise TabPresentationError(
            f"ReorderTab: `index` must be a whole tab position, got {value!r}. A bool is "
            f"refused rather than coerced — `True` would silently mean \"position 1\" under "
            f"Python's int-subclass rule, which nobody means. Write {example}."
        )
    if not isinstance(value, int):
        raise TabPresentationError(
            f"ReorderTab: `index` must be a whole number, got {value!r}. A tab position is not "
            f"fractional and is not a string. Write {example}."
        )
    if value < 0:
        raise TabPresentationError(
            f"ReorderTab: `index` must be 0 or more, got {value}. Positions are **0-based** — "
            f"index 0 IS the first tab, so there is no negative position to mean \"the front\", "
            f"and Lark refuses it itself ('90204 invalid parameter: "
            f"Requests[0].UpdateSheet.Properties.Index'), a message that names neither the "
            f"fault nor the repair — so it is refused here, before any call. Write {example} "
            f"for the first position, or index=<tab count - 1> for the last."
        )
    return value


@dataclass(frozen=True)
class ReorderTab(_TabPresentation):
    """Move the tab ``sheet_id`` to position ``index`` — an ``updateSheet`` request.

    ``index`` is a **TARGET POSITION and 0-based** (characterized live, never assumed): a tab
    sitting at position 0 asked for ``index=2`` ends at 2, and the tabs it passed **close the
    gap** — so a reorder is a move, not a swap and not a delta. ``index=0`` is the first tab.

    **What cannot be built** (zero-cost): a negative index, a bool, a fraction, a string — see
    :class:`TabPresentationError`. An index **past the last tab** refuses at **plan time**
    instead, because it needs the tab count: Lark itself **accepts** such a request and
    silently **clamps** the tab to the end (``code 0`` — probed), which means the stated intent
    is not what happens, so it is refused rather than quietly reinterpreted.

    **A reorder to the position the tab already holds is accepted, not refused** — and it is
    disclosed as a no-op, because Lark does not even bump the spreadsheet ``revision`` for it
    (probed; a no-op *freeze* does bump, so freeze and presentation genuinely differ here).
    """

    sheet_id: str
    index: int

    op = "reorder-tab"

    def __post_init__(self):
        _whole_index(self.index, sheet_id=self.sheet_id)

    @property
    def properties(self) -> dict:
        return {"sheetId": self.sheet_id,
                "index": _whole_index(self.index, sheet_id=self.sheet_id)}

    @property
    def fields(self) -> dict:
        return {"index": self.index, "index_is_target_position": True, "zero_based": True}

    @property
    def semantic(self) -> str:
        return (f"move tab {self.sheet_id} to position {self.index} "
                f"(0-based, a target position)")


@dataclass(frozen=True)
class RetitleTab(_TabPresentation):
    """Rename the tab ``sheet_id`` to ``title`` — an ``updateSheet`` request.

    **The ``sheet_id`` does not change** (probed), which is the whole point: the id is the
    stable handle and a title never was one. So a retitle **breaks any cached
    title→``sheet_id`` mapping**, and the plan says so before the write.

    **What cannot be built** (zero-cost): the empty string (Lark answers ``90207 sheetTitle
    should not be empty``), a whitespace-only title, a non-string — see
    :class:`TabPresentationError`. A **duplicate** title refuses at **plan time**, because it
    needs the other tabs' titles: Lark answers ``90210 sheetTitle already exist in snapshot``,
    and its uniqueness check is **case-SENSITIVE** — ``gamma`` beside an existing ``Gamma`` is
    accepted (probed), so the plan-time check is exact-match too and never case-folds.

    **No length ceiling is imposed.** A 100-character and a 101-character title were both
    accepted live and the 101-character one landed, so this library invents no limit it cannot
    demonstrate; a title Lark rejects for length would surface as its own API error.
    """

    sheet_id: str
    title: str

    op = "retitle-tab"

    def __post_init__(self):
        if isinstance(self.title, bool) or not isinstance(self.title, str):
            raise TabPresentationError(
                f"RetitleTab: `title` must be a string, got {self.title!r}. A tab title is "
                f"text; nothing else is expressible on the wire. Write "
                f"RetitleTab(sheet_id={self.sheet_id!r}, title='Q3 actuals')."
            )
        if not self.title:
            raise TabPresentationError(
                f"RetitleTab: `title` is empty. Lark refuses an empty tab title itself "
                f"('90207 sheetTitle should not be empty'), so the request cannot be built, "
                f"which is why you see this instead of a surprise at apply. Write "
                f"RetitleTab(sheet_id={self.sheet_id!r}, title='Q3 actuals')."
            )
        if not self.title.strip():
            raise TabPresentationError(
                f"RetitleTab: `title` is only whitespace ({self.title!r}). This is **this "
                f"library's own rule**, not an answer from Lark: a title that renders as blank "
                f"is indistinguishable to a reader from the empty title Lark does refuse, and "
                f"it makes the tab unnameable in any hand-off. Write "
                f"RetitleTab(sheet_id={self.sheet_id!r}, title='Q3 actuals')."
            )

    @property
    def properties(self) -> dict:
        return {"sheetId": self.sheet_id, "title": self.title}

    @property
    def fields(self) -> dict:
        return {"title": self.title}

    @property
    def semantic(self) -> str:
        return f"retitle tab {self.sheet_id} to {self.title!r}"


@dataclass(frozen=True)
class SetTabVisibility(_TabPresentation):
    """Hide or show the tab ``sheet_id`` — an ``updateSheet`` request.

    Use the named constructors :meth:`hide` / :meth:`show` rather than a bare boolean.

    **Hiding is not protecting and not removing.** A hidden tab's data is **still fully
    readable through this library** (probed: values were written to a hidden tab and read
    straight back), so the plan discloses that before the write — the same silent-fidelity
    class the filter and dimension-hide disclosures cover, arriving through a write you make
    yourself.

    **What cannot be built** (zero-cost): a non-``bool`` visibility. **Hiding the last visible
    tab** refuses at **plan time**, because it needs the other tabs' visibility: Lark answers
    ``95201 server error`` for it (probed — a message that names nothing), so the refusal is
    made here with a real one. Hide and show are **idempotent**: repeating either is accepted
    and does not move the spreadsheet ``revision`` (probed).

    ``hidden`` is read back from the **v3 tab query**, which is the only read that carries it —
    ``metainfo`` does not report ``hidden`` at all, not even for a tab that is hidden (probed).
    """

    sheet_id: str
    hidden: bool

    op = "set-tab-visibility"

    def __post_init__(self):
        if not isinstance(self.hidden, bool):
            raise TabPresentationError(
                f"SetTabVisibility: `hidden` must be True or False, got {self.hidden!r}. A "
                f"visibility is a flag, and a 1 / 0 / 'true' would have to be guessed at. "
                f"Write SetTabVisibility.hide(sheet_id={self.sheet_id!r}) or "
                f"SetTabVisibility.show(sheet_id={self.sheet_id!r})."
            )

    @classmethod
    def hide(cls, sheet_id: str) -> "SetTabVisibility":
        """Hide the tab — invisible in the UI, **still readable through this library**."""
        return cls(sheet_id=sheet_id, hidden=True)

    @classmethod
    def show(cls, sheet_id: str) -> "SetTabVisibility":
        """Show the tab again."""
        return cls(sheet_id=sheet_id, hidden=False)

    @property
    def properties(self) -> dict:
        return {"sheetId": self.sheet_id, "hidden": self.hidden}

    @property
    def fields(self) -> dict:
        return {"hidden": self.hidden}

    @property
    def semantic(self) -> str:
        return f"{'hide' if self.hidden else 'show'} tab {self.sheet_id}"
