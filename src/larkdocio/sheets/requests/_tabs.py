"""larkdocio.sheets.requests._tabs — tab CRUD — add / copy / delete, and the ONE ``updateSheet`` wire-element builder.

Carries :class:`_TabWrite` (the base both tab families ride) and
:func:`update_sheet_element`, which the freeze and tab-presentation families both build
their wire element through — the seam is shared here rather than forked.

Split out of the flat 2,462-line ``sheets/requests.py`` by LD-224, **verbatim** —
pre-split lines 1874–1975. The package's ``__init__`` re-exports every name defined here,
so ``from larkdocio.sheets.requests import <name>`` is unchanged.
"""
from dataclasses import dataclass
from typing import Optional

from ._gates import WriteOpKind


# --------------------------------------------------------------------------- #
# Tab writes (LD-122, D5).                                                     #
#                                                                               #
# add / copy / delete via `sheets_batch_update` (`requests[]`). The reply's new #
# `sheetId` is captured; a DELETE snapshots the removed tab's identity at plan  #
# time so the apply-log carries it (D5, destructive-safe). Each request object  #
# OWNS its wire element (`request_element` in the descriptor) — a caller never  #
# hand-assembles the `addSheet`/`copySheet`/`deleteSheet` body.                 #
# --------------------------------------------------------------------------- #

class _TabWrite:
    """Mixin: a tab (``sheets_batch_update``) write — :data:`WriteOpKind.TAB`, verified by
    the v3 tab-query diff (never the style/merge legs)."""

    write_kind = "tab"
    is_rich = False

    @property
    def op_kinds(self) -> tuple:
        return (WriteOpKind.TAB,)


@dataclass(frozen=True)
class AddTab(_TabWrite):
    """Add a new tab titled ``title`` at ``index`` — an ``addSheet`` request. The reply
    carries the **new** tab's ``sheetId`` (captured into the apply-log).

    **``index=None`` PLACES THE NEW TAB FIRST — it does not append.** The guide claimed
    through 1.34 that leaving ``index`` out would append, and that was false; measured twice live (a
    field exercise, re-measured on a disposable for 1.35 — the live gate
    ``tests/test_live_sheets_ld472_doc_truth_gate.py``, in the source repository: a workbook reading
    ``[(0,'Sheet1'), (1,'Rollout')]`` came back ``[(0,'zz-no-index'), (1,'Sheet1'),
    (2,'Rollout')]``). **The behaviour is unchanged** — only the sentence about it is. To
    append, name the position: ``AddTab(title=…, index=len(client.query_tabs(token)))``,
    measured landing last in the same run. ``index`` is the same 0-based target position
    :class:`ReorderTab` takes.
    """

    title: str
    index: Optional[int] = None

    def descriptor(self) -> dict:
        props = {"title": self.title}
        if self.index is not None:
            props["index"] = self.index
        return {
            "op": "add-tab",
            "title": self.title,
            "index": self.index,
            "request_element": {"addSheet": {"properties": props}},
            "semantic": f"add tab {self.title!r}"
                        + (f" at index {self.index}" if self.index is not None else ""),
        }


@dataclass(frozen=True)
class CopyTab(_TabWrite):
    """Copy the tab ``source_sheet_id`` to a new tab titled ``dest_title`` — a ``copySheet``
    request. The copy duplicates the source's content INCLUDING its merges; the reply
    carries the new tab's ``sheetId`` (captured, and its duplicated merges re-read)."""

    source_sheet_id: str
    dest_title: str

    def descriptor(self) -> dict:
        return {
            "op": "copy-tab",
            "source_sheet_id": self.source_sheet_id,
            "dest_title": self.dest_title,
            "request_element": {"copySheet": {"source": {"sheetId": self.source_sheet_id},
                                              "destination": {"title": self.dest_title}}},
            "semantic": f"copy tab {self.source_sheet_id} -> {self.dest_title!r}",
        }


@dataclass(frozen=True)
class DeleteTab(_TabWrite):
    """Delete the tab ``sheet_id`` — a ``deleteSheet`` request. **Destructive-safe:**
    the dry-run snapshots the removed tab's identity (title / index / geometry / merges)
    so the apply-log carries it — a consumer could recreate the tab from the log."""

    sheet_id: str

    def descriptor(self) -> dict:
        return {
            "op": "delete-tab",
            "sheet_id": self.sheet_id,
            "request_element": {"deleteSheet": {"sheetId": self.sheet_id}},
            "semantic": f"delete tab {self.sheet_id}",
        }


# --------------------------------------------------------------------------- #
# THE ONE `updateSheet` REQUEST-ELEMENT BUILDER.                                #
#                                                                              #
# The freeze family (view state) and the tab-presentation family (index /       #
# title / hidden) both ride `updateSheet` inside the already-shipped            #
# `sheets_batch_update`. They share this builder rather than each assembling    #
# the wire dict, so the seam is EXTENDED and not forked; a second assembler     #
# anywhere in the package reddens `tests/test_sheets_tab_presentation.py`.      #
# --------------------------------------------------------------------------- #

def update_sheet_element(properties: dict) -> dict:
    """The ``{"updateSheet": {"properties": …}}`` wire element for a validated ``properties``.

    The single place this package names ``updateSheet`` as a wire key. A request object owns its
    own ``properties`` (validated at construction) and hands them here; a caller never
    hand-assembles the body, and no family gets to grow a second, subtly-different one.

    ``properties`` is **copied**, so a request cannot be mutated through the element it built.
    """
    return {"updateSheet": {"properties": dict(properties)}}
