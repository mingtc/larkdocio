"""larkdocio.sheets.ops._tabs — the TAB family — add / copy / delete plus the presentation half's dispatch.

The ``tab`` descriptor's own preview and apply legs and its verification leg (the v3 tab-query
diff). Its preview routes a presentation request on to ``_tab_presentation``. Named after
``requests/_tabs.py``.

Split out of the flat 3,019-line ``sheets/ops.py`` by LD-532, **verbatim**. The
package's ``__init__`` holds the ``OPS`` registry, the dispatchers and the engine
loop, and re-exports every name defined here, so
``from larkdocio.sheets.ops import <name>`` is unchanged.
"""
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.plan import ApplyLogEntry, PlanEntry

from ._shared import VerificationLeg, _post_write_revision
from ._tab_presentation import TAB_PRESENTATION_OPS, _preview_tab_presentation



#: The tab family's **own** verification leg — the v3 tab-query diff (``query_tabs``), which is
#: what :data:`~larkdocio.sheets.requests.WriteOpKind.TAB` has always been verified by.
#:
#: **Why this leg for the presentation fields too (LD-187).** All three of ``index`` / ``title``
#: / ``hidden`` are readable **here and only here** among the cheap reads: the v3 tab query
#: carries every one of them, while ``metainfo`` carries ``index`` and ``title`` but **no
#: ``hidden`` at all** — probed twice, once on a read taken while a tab really was hidden. So
#: the issue's expectation that hide would ride a ``metainfo`` leg is corrected by the evidence:
#: one leg serves all three fields, it is a single un-throttled GET, and — like the freeze
#: family's frozen read and unlike the dimension family's export — it therefore **runs inside**
#: ``apply``, so a presentation entry records what the tab now looks like rather than only that
#: the call returned.
TAB_VERIFICATION = VerificationLeg(
    id="v3-tab-query-leg",
    # Recorded in every tab-PRESENTATION apply-log entry, so the record states its own posture.
    note=(
        "verified by the tab family's own leg — the v3 tab-query diff (SheetsWriteClient."
        "query_tabs), which is the only cheap read carrying all three presentation fields: the "
        "metainfo read reports a tab's index and title but NOT whether it is hidden (probed, "
        "including a read taken while a tab was hidden). That leg IS run inside apply — one "
        "cheap un-throttled GET — so an entry carries the position, title and visibility "
        "OBSERVED after the write, and an answer that could not be established is recorded as "
        "unknown rather than as 'visible'. The op stays out of STYLE_LEG_OP_KINDS / "
        "MERGE_LEG_OP_KINDS: presentation is not cell content and not merge geometry."
    ),
)

#: The leg id / caveat as standalone names. **Authored on :data:`TAB_VERIFICATION` above** —
#: these are references to it, kept because the live gates import them and this module's own
#: docstrings cite them by name.
TAB_VERIFICATION_LEG = TAB_VERIFICATION.id
TAB_VERIFICATION_NOTE = TAB_VERIFICATION.note


def _preview_tab(request, client, spreadsheet_token, merges=None) -> PlanEntry:
    """Preview a tab write. **Add / copy / delete** (LD-122): a delete snapshots the removed
    tab's full identity at plan time (via ``query_tabs``) so the apply-log can carry it
    (D5, destructive-safe); add/copy carry only the op preview (the new ``sheetId`` is
    captured from the write reply at apply). **Reorder / retitle / hide-show** (LD-187) route
    to :func:`_preview_tab_presentation`, which reads the same tab list for its refusals and
    disclosures. Zero writes either way."""
    desc = request.descriptor()
    if desc["op"] in TAB_PRESENTATION_OPS:
        return _preview_tab_presentation(request, client, spreadsheet_token, desc)
    if desc["op"] == "delete-tab":
        identity = None
        try:
            for tab in client.query_tabs(spreadsheet_token) or []:
                if tab.get("sheet_id") == desc["sheet_id"]:
                    identity = tab
                    break
        except LarkAPIError:
            identity = None
        after = {"kind": "delete-tab", "removed_identity": identity,
                 "note": "the removed tab's identity is snapshot at plan time (destructive-safe)"}
        return PlanEntry.resolved_structural(structural=desc, after=after, write_kind="tab")
    return PlanEntry.resolved_structural(
        structural=desc, after={"kind": desc["op"]}, write_kind="tab")



def _observe_tab(client, spreadsheet_token, sheet_id):
    """The tab-presentation **verification leg** (:data:`TAB_VERIFICATION_LEG`), run inside
    ``apply``: ``(observed, reason)`` where ``observed`` is
    ``{"index", "title", "hidden"}`` read back after the write, or ``None`` with a ``reason``.

    Three distinct unavailable states, kept distinct (the LD-184 / LD-186 honesty rule — "I
    could not find out" is never reported as a state):

    * the read **failed** — the reason carries Lark's own message;
    * the read succeeded and the tab is **absent** from it — the reason names the tab;
    * the read succeeded and the tab is there, but its ``hidden`` flag is **not in the payload**
      — ``observed["hidden"]`` is ``None``, never ``False``.
    """
    try:
        tabs = client.query_tabs(spreadsheet_token)
    except LarkAPIError as e:
        return None, (f"the tab-query verification leg failed, so the tab's position, title and "
                      f"visibility after this write are UNKNOWN (not assumed unchanged): {e}")
    tab = next((t for t in (tabs or []) if t.get("sheet_id") == sheet_id), None)
    if tab is None:
        return None, (f"the tab-query verification leg succeeded but names no tab "
                      f"{sheet_id!r}, so what this write left behind is UNKNOWN")
    return {"index": tab.get("index"), "title": tab.get("title"),
            "hidden": tab.get("hidden")}, None


def _apply_tab_one(entry: PlanEntry, client, spreadsheet_token, expected_revision=None):
    """Execute ONE resolved TAB add/copy/delete entry (LD-122). Returns ``(log_entry,
    next_expected_revision)``.

    The revision compare-and-swap already passed in :func:`_apply_one`. A tab write has no
    A1 range and no scalar precondition; it:

    * writes the request element the request OWNS (``desc["request_element"]`` — an
      ``addSheet`` / ``copySheet`` / ``deleteSheet``) via ``sheets_batch_update``;
    * captures the **new** tab's ``sheetId`` from the reply (add / copy);
    * for a **copy**, re-reads the new tab's ``merges`` to record the duplicated geometry
      (content fidelity);
    * for a **delete**, carries the removed tab's identity (snapshot at plan time, D5) into
      the log (destructive-safe);
    * for a **presentation** write (LD-187 — reorder / retitle / hide-show), runs the family's
      verification leg (:data:`TAB_VERIFICATION_LEG`) **here**, because it is one cheap read:
      the tab's position, title and visibility are read back and recorded as ``observed``, so
      the log says what the tab now looks like rather than only that the call returned. An
      answer that could not be established is recorded as **unknown**, never as "visible".
    """
    desc = dict(entry.structural)
    op = desc["op"]
    reply = client.batch_update_sheets(spreadsheet_token, [desc["request_element"]])
    replies = (reply or {}).get("replies") or []
    first = replies[0] if replies else {}

    new_sheet_id = None
    result = None
    copied_merges = None
    if op == "add-tab":
        new_sheet_id = ((first.get("addSheet") or {}).get("properties") or {}).get("sheetId")
    elif op == "copy-tab":
        new_sheet_id = ((first.get("copySheet") or {}).get("properties") or {}).get("sheetId")
        if new_sheet_id is not None:
            geo = client.read_sheet_geometry(spreadsheet_token, new_sheet_id)
            copied_merges = (geo or {}).get("merges") or []
    elif op == "delete-tab":
        result = (first.get("deleteSheet") or {}).get("result")

    observed = None
    observation_note = None
    if op in TAB_PRESENTATION_OPS:
        observed, observation_note = _observe_tab(client, spreadsheet_token, desc["sheet_id"])

    post_revision = _post_write_revision(
        reply, lambda: client.read_revision(spreadsheet_token))

    tab_log = {**desc, "reply": first, "new_sheet_id": new_sheet_id}
    if op == "copy-tab":
        tab_log["copied_merges"] = copied_merges
    if op == "delete-tab":
        tab_log["result"] = result
        tab_log["removed_identity"] = (entry.after or {}).get("removed_identity")
    if op in TAB_PRESENTATION_OPS:
        tab_log["preview"] = entry.after
        tab_log["observed"] = observed
        tab_log["observation_note"] = observation_note
        TAB_VERIFICATION.stamp(tab_log)
    applied = ApplyLogEntry.applied_structural(
        structural=tab_log, revision=post_revision, write_kind="tab")
    return applied, post_revision
