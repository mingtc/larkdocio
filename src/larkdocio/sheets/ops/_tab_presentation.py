"""larkdocio.sheets.ops._tab_presentation — the tab family's PRESENTATION half — reorder / retitle / hide-show.

The ``updateSheet`` half of the ``tab`` descriptor: its three ``structural['op']`` values and
the notes its preview discloses. Named after ``requests/_tab_presentation.py``; the family's
descriptor and its add / copy / delete half live in ``_tabs``.

Split out of the flat 3,019-line ``sheets/ops.py`` by LD-532, **verbatim**. The
package's ``__init__`` holds the ``OPS`` registry, the dispatchers and the engine
loop, and re-exports every name defined here, so
``from larkdocio.sheets.ops import <name>`` is unchanged.
"""
from dataclasses import replace
from typing import Optional

from larkdocio.errors import LarkAPIError
from larkdocio.sheets.plan import PlanEntry, Refusal, combine_preview_notes

from ._shared import _unreadable_tab_refusal

#: The ``entry.structural['op']`` values of the three PRESENTATION writes (LD-187) — the tab
#: family's ``updateSheet`` half, as opposed to LD-122's add / copy / delete half.
TAB_PRESENTATION_OPS = ("reorder-tab", "retitle-tab", "set-tab-visibility")


def hidden_tab_note(desc, tab) -> Optional[dict]:
    """The ``hidden-tab-fidelity`` preview note for a **hide** — or ``None`` for a show.

    **Hiding a tab makes real data invisible to a human while this library still emits it.**
    The tab is not deleted, its cells are not cleared, and a Markdown read of the spreadsheet
    still includes every one of them — probed: values were written to a hidden tab and read
    straight back. So a consumer who reaches for "hide" as a way to protect or remove something
    has to be told before the write, not after.

    Deliberately worded in the **shipped disclosure vocabulary** rather than a newly-coined one:
    it carries :func:`hidden_dimension_note`'s own sentences ("a fidelity event, not a
    formatting change", "The data is NOT deleted and larkdocio's reader still emits it") so the
    two hide disclosures read as one voice, and it composes through
    :func:`~larkdocio.sheets.plan.combine_preview_notes` so it can never displace another
    warning.

    Fires **only** for a hide. A show reveals data rather than hiding it, and a disclosure that
    rode every plan would be noise that teaches a consumer to skip notes.
    """
    if not desc.get("hidden"):
        return None
    title = (tab or {}).get("title")
    already = (tab or {}).get("hidden") is True
    named = f" ({title!r})" if title else ""
    already_clause = (
        " This tab is ALREADY hidden, so this write changes nothing about what a viewer sees "
        "(the spreadsheet revision does not even move for it — probed); the disclosure stands "
        "because the state it describes stands." if already else ""
    )
    return {
        "kind": "hidden-tab-fidelity",
        "sheet_id": desc.get("sheet_id"),
        "title": title,
        "hidden": True,
        "already": already,
        "note": (
            f"HIDE — a fidelity event, not a formatting change. Tab {desc.get('sheet_id')!r}"
            f"{named} becomes invisible to anyone viewing this spreadsheet, and NOTHING else "
            f"changes: the tab is not deleted, its cells are not cleared, and its data stays "
            f"FULLY READABLE through this library — a values read of that tab still returns "
            f"every cell, and a Markdown read of this spreadsheet still emits the whole tab. "
            f"The data is NOT deleted and larkdocio's reader still emits it, so hiding is "
            f"neither a way to protect a tab nor a way to remove one; it only changes what a "
            f"human sees.{already_clause} Show it again with "
            f"SetTabVisibility.show(sheet_id={desc.get('sheet_id')!r})."
        ),
    }


def retitle_join_note(desc, tab) -> Optional[dict]:
    """The ``retitle-breaks-title-joins`` preview note — or ``None`` when the new title equals
    the current one (nothing is renamed, so no join breaks; that case gets the no-op note).

    **A title is never a handle.** Every join from a human-readable tab name to a ``sheet_id``
    is a cache of a fact this write invalidates, and the ``sheet_id`` itself is **unchanged**
    (probed) — which is the point worth saying out loud: the stable handle is the id, and code
    that kept the id keeps working across a rename.

    Same register as the other disclosures: a ``kind`` + a ``note``, naming **both** titles, the
    id that did not move, and the repair.
    """
    new_title = desc.get("title")
    old_title = (tab or {}).get("title")
    if old_title is not None and old_title == new_title:
        return None
    sheet_id = desc.get("sheet_id")
    return {
        "kind": "retitle-breaks-title-joins",
        "sheet_id": sheet_id,
        "old_title": old_title,
        "new_title": new_title,
        "sheet_id_unchanged": True,
        "note": (
            f"RETITLE — the tab's NAME changes, its IDENTITY does not. Tab {sheet_id!r} is "
            f"renamed from {old_title!r} to {new_title!r}, and its sheet_id stays exactly "
            f"{sheet_id!r} (unchanged — probed). So any cached mapping from the title "
            f"{old_title!r} to a sheet_id is now stale, and so is any range, plan, report or "
            f"hand-off that addresses this tab by its name: a title is never a sheet_id. "
            f"Nothing is refused — Lark accepts the rename — but you are being told before the "
            f"write rather than discovering it after. Re-read the tab list (query_tabs(...)) "
            f"and re-join on sheet_id, which is the handle that survives a rename."
        ),
    }


def tab_presentation_noop_note(desc, tab) -> Optional[dict]:
    """The ``tab-presentation-no-op`` note — a presentation write that asks for the state the
    tab is already in, and therefore changes nothing at all.

    Worth a note rather than a refusal (and rather than silence) because of what the probe
    found: Lark **accepts** it and does **not** even bump the spreadsheet ``revision`` — which
    makes it invisible in every after-the-fact record, unlike a no-op *freeze*, which does bump.
    A caller who queued it in the belief that it would do something should learn that here.
    """
    if not isinstance(tab, dict):
        return None
    op = desc.get("op")
    if op == "reorder-tab":
        if tab.get("index") != desc.get("index"):
            return None
        asked = f"position {desc.get('index')}"
    elif op == "retitle-tab":
        if tab.get("title") != desc.get("title"):
            return None
        asked = f"the title {desc.get('title')!r}"
    elif op == "set-tab-visibility":
        if tab.get("hidden") is not desc.get("hidden"):
            return None
        asked = "hidden" if desc.get("hidden") else "visible"
    else:
        return None
    return {
        "kind": "tab-presentation-no-op",
        "sheet_id": desc.get("sheet_id"),
        "op": op,
        "note": (
            f"NO-OP: tab {desc.get('sheet_id')!r} is already at {asked}, so this write changes "
            f"nothing. It is still a call, and Lark accepts it — but it does not even move the "
            f"spreadsheet revision (probed), so nothing downstream will record that it "
            f"happened. Drop it from the batch if it was queued by mistake."
        ),
    }


def _preview_tab_presentation(request, client, spreadsheet_token, desc) -> PlanEntry:
    """Preview a tab REORDER / RETITLE / HIDE-SHOW write (LD-187). ZERO writes, and **one**
    read — the v3 tab query — that pays for five jobs:

    * the **tab-identity** refusal — ``UNKNOWN_TAB`` when the ``sheet_id`` is not a tab of this
      spreadsheet (with a did-you-mean), else ``TAB_VANISHED`` (the LD-131 split);
    * the **position** refusal — a target index past the last tab, which Lark *accepts* and
      silently clamps (probed), so the plan refuses rather than let a stated intent be
      reinterpreted;
    * the **duplicate-title** refusal — exact, case-sensitive, exactly as the API compares;
    * the **last-visible-tab** refusal — proven from the other tabs' ``hidden`` flags, never
      guessed from an unknown;
    * the **disclosures** — the hide fidelity note, the retitle join note, and the no-op note.

    The faults knowable from the caller's own arguments (a negative index, a bool/fractional
    index, an empty or non-string title, a non-bool visibility) never arrive here: they are
    refused at **construction**
    (:class:`~larkdocio.sheets.requests.TabPresentationError`) and cost zero calls.
    """
    preview = request.presentation_preview()
    sheet_id = desc["sheet_id"]
    try:
        tabs = client.query_tabs(spreadsheet_token)
    except LarkAPIError as e:
        return PlanEntry.refused(
            target=None,
            after=preview,
            refusal=_unreadable_tab_refusal(
                client, spreadsheet_token, sheet_id=sheet_id,
                detail=(
                    f"could not read the tab list for {desc['semantic']}, so neither the tab's "
                    f"identity nor the other tabs' titles and visibility can be checked — "
                    f"refusing rather than writing blind: {e}"
                ),
                error=e,
            ),
        )
    tabs = list(tabs or [])
    tab = next((t for t in tabs if t.get("sheet_id") == sheet_id), None)
    if tab is None:
        return PlanEntry.refused(
            target=None,
            after=preview,
            refusal=_unreadable_tab_refusal(
                client, spreadsheet_token, sheet_id=sheet_id,
                detail=(f"the tab list came back and names no tab {sheet_id!r} for "
                        f"{desc['semantic']}"),
            ),
        )

    op = desc["op"]
    if op == "reorder-tab" and desc["index"] > len(tabs) - 1:
        return PlanEntry.refused(
            target=None,
            after=preview,
            refusal=Refusal.tab_index_out_of_range(
                asked=desc["index"], count=len(tabs), sheet_id=sheet_id),
        )
    if op == "retitle-tab":
        holder = next((t for t in tabs
                       if t.get("sheet_id") != sheet_id and t.get("title") == desc["title"]),
                      None)
        if holder is not None:
            return PlanEntry.refused(
                target=None,
                after=preview,
                refusal=Refusal.duplicate_tab_title(
                    title=desc["title"], sheet_id=sheet_id,
                    holder_sheet_id=holder.get("sheet_id")),
            )
    if op == "set-tab-visibility" and desc["hidden"]:
        # PROOF, not a guess: only a tab whose `hidden` is KNOWN to be True is discounted, so
        # an unreadable visibility leaves the tab counted as possibly-visible.
        others_visible = [t for t in tabs
                          if t.get("sheet_id") != sheet_id and t.get("hidden") is not True]
        if not others_visible:
            return PlanEntry.refused(
                target=None,
                after=preview,
                refusal=Refusal.last_visible_tab(sheet_id=sheet_id, title=tab.get("title")),
            )

    entry = PlanEntry.resolved_structural(
        structural={**desc, "tab_before": {"index": tab.get("index"),
                                           "title": tab.get("title"),
                                           "hidden": tab.get("hidden")}},
        after=preview, write_kind="tab")
    hidden_note = hidden_tab_note(desc, tab)
    join_note = retitle_join_note(desc, tab) if op == "retitle-tab" else None
    # a hide of an ALREADY-hidden tab is a no-op AND a disclosure; the hide note carries the
    # `already` flag itself, so the no-op note would only repeat it.
    noop_note = None if hidden_note is not None else tab_presentation_noop_note(desc, tab)
    note = combine_preview_notes(noop_note, hidden_note, join_note)
    return entry if note is None else replace(entry, preview_note=note)
