"""larkdocio.sheets.ops._shared — the helpers MORE THAN ONE op family needs.

The package's root: the verification-leg value object every family that carries one stamps
its apply logs with, the unreadable-tab diagnostic the preview legs refuse through, the
post-write revision extraction the apply legs record, and the merge-cover probe the value and
formula previews share. Imports no family module — which is what makes the package a plain
DAG.

Split out of the flat 3,019-line ``sheets/ops.py`` by LD-532, **verbatim**. The
package's ``__init__`` holds the ``OPS`` registry, the dispatchers and the engine
loop, and re-exports every name defined here, so
``from larkdocio.sheets.ops import <name>`` is unchanged.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

from larkdocio.sheets.write_range import A1Cell, WriteRange
from larkdocio.sheets.merge_geometry import _normalize_merge
from larkdocio.sheets.plan import Refusal


# --------------------------------------------------------------------------- #
# THE VERIFICATION LEG (LD-223) — one value object for a fact four write        #
# families each used to hand-stamp: *which* leg verifies this write, and the    #
# caveat that goes with it.                                                     #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class VerificationLeg:
    """One write family's **verification leg**: the read that can see what the write did,
    plus the caveat prose that states the family's verification posture.

    **Why this is one object and not four constant pairs.** The tab, dimension, freeze and
    style families each answer the same two questions — *which read proves this landed?* and
    *is that read run inside* ``apply``\\ *, or is it deferred and why?* — and each used to
    answer them with its own ``*_LEG`` / ``*_NOTE`` pair stamped by hand into its own apply-log
    record. Four hand-stamps meant the *key* could drift, and it did: the style family's plan
    notes spelled it ``leg`` while every apply log spelled it ``verified_by``, one fact
    under two names in one module (LD-223; the maintainer ruled the rename onto ``verified_by`` and
    accepted the narrow consumer break — the divergence had shipped the same day).

    The two halves are deliberately **separately reachable**, because two different surfaces
    want different amounts of it:

    * :meth:`stamp` — the whole attribution, for an **apply log**: which leg, and the caveat.
    * :meth:`attribution` — the *which* alone, for a **preview note**, which already carries
      its own prose under its own ``note`` key and would otherwise say the same thing twice.

    Both spell the key in **one** place, which is what makes a third spelling impossible.
    """

    #: The leg's stable id — the string a consumer reads out of a log and greps for. Frozen
    #: by contract: renaming one is a consumer-visible break (LD-223 / B4).
    id: str

    #: The caveat prose recorded beside it, so a record states its own verification posture
    #: rather than leaving a bare "applied" to be mistaken for "verified".
    note: str

    def attribution(self) -> dict:
        """The ``verified_by`` half alone, as a one-key dict — **fresh** each call, so a
        caller that merges it into a note cannot mutate every other note sharing it."""
        return {"verified_by": self.id}

    def stamp(self, record: dict) -> dict:
        """Record both halves **into** ``record``, in place, and return it.

        In place and last, deliberately: the attribution is the final thing a family adds to
        its apply-log payload, so the resulting key order is byte-identical to the four
        hand-written pairs this replaced (pinned in
        ``tests/test_sheets_verification_leg_seam.py``).
        """
        record.update(self.attribution())
        record["verification_note"] = self.note
        return record



def _tab_pairs(client, spreadsheet_token) -> Optional[List[Tuple]]:
    """The spreadsheet's ``(sheet_id, title)`` pairs via ``query_tabs`` — or ``None`` when
    the listing is **unobtainable** (LD-131).

    ``None`` means "we cannot prove anything about this tab set": the client seam has no
    ``query_tabs``, the call raised, or it answered with nothing usable. The caller then
    degrades **honestly** to the staleness story rather than invent a did-you-mean or claim
    a tab never existed on no evidence.

    This is a **diagnostic** read on an already-failing path, so ANY exception it raises is
    swallowed into ``None``: enriching a refusal must never escalate that refusal into a
    crash (the caller already has a truthful, if less specific, refusal to return).
    """
    getter = getattr(client, "query_tabs", None)
    if not callable(getter):
        return None
    try:
        tabs = getter(spreadsheet_token)
    except Exception:
        return None
    if not isinstance(tabs, list) or not tabs:
        return None
    pairs = [
        (tab.get("sheet_id"), tab.get("title"))
        for tab in tabs
        if isinstance(tab, dict) and tab.get("sheet_id") is not None
    ]
    return pairs or None


def _did_you_mean(sheet_id, pairs) -> str:
    """The actionable half of an ``UNKNOWN_TAB`` refusal: name the wrong identifier, say
    what *kind* of identifier the range wants, and list the real ``(sheet_id, title)``
    pairs (LD-131 / the F4 improvement candidate, verbatim).

    Titles are ``repr``-quoted so a title containing a ``!`` (the A1 tab separator) — or a
    comma — cannot be misread as part of the range syntax. When the wrong identifier is
    **exactly** a real tab's title the message says so first: that is the F4 trap (Lark
    titles every new tab ``Sheet1``), and naming it turns a guess into a substitution.
    """
    listing = ", ".join(f"{sid} (title {title!r})" for (sid, title) in pairs)
    title_match = [sid for (sid, title) in pairs if title == sheet_id]
    lead = (
        f"{sheet_id!r} is the TITLE of tab {title_match[0]!r}, not a sheet_id"
        if title_match
        else f"{sheet_id!r} is not a sheet_id in this spreadsheet"
    )
    return (
        f"{lead} — an A1 write range addresses a tab by its sheet_id, never its title. "
        f"Did you mean one of: {listing}?"
    )


#: Lark's "the range you gave me is not a valid range" code (``validate RangeVal fail``).
#: A **clean, actionable signal about the RANGE** — never about the tab — so it must not be
#: laundered into the staleness story (LD-150 / dogfood **F20**).
MALFORMED_RANGE_CODE = 90202


def _unreadable_tab_refusal(client, spreadsheet_token, *, sheet_id, detail,
                            a1_range=None, error=None) -> Refusal:
    """Classify a **plan-time** unreadable range into the right refusal (LD-131 + LD-150).

    Three outcomes, in decision order:

    * ``MALFORMED_RANGE`` (LD-150 / F20) when Lark answered :data:`MALFORMED_RANGE_CODE` —
      the RANGE is the problem, so neither a did-you-mean nor a re-plan is the repair. Decided
      from the error's own ``code``, which means **no ``query_tabs`` read is spent** chasing a
      tab that is fine;
    * ``UNKNOWN_TAB`` when the tab listing positively PROVES ``sheet_id`` is not a tab of this
      spreadsheet (the identifier kind was wrong — a title, a typo, a stale id from another
      sheet);
    * ``TAB_VANISHED`` otherwise, which stays **reserved** for the staleness story (the tab is
      really there, or we cannot prove otherwise).

    The extra ``query_tabs`` read happens **only** on the middle path — the happy path is
    unchanged and costs nothing.
    """
    if error is not None and _is_malformed_range(error):
        return Refusal.malformed_range(
            a1_range=a1_range if a1_range is not None else getattr(error, "msg", None),
            detail=detail, lark_code=getattr(error, "code", MALFORMED_RANGE_CODE),
        )
    if sheet_id is None:
        return Refusal.tab_vanished(detail)
    pairs = _tab_pairs(client, spreadsheet_token)
    if pairs is None or any(sid == sheet_id for (sid, _title) in pairs):
        return Refusal.tab_vanished(detail)
    return Refusal.unknown_tab(f"{_did_you_mean(sheet_id, pairs)} (underlying: {detail})")


def _is_malformed_range(error) -> bool:
    """True iff ``error`` carries Lark's malformed-range code (representation-agnostic — the
    wire may hand back an int or a str, the same discipline as the rate-limit code)."""
    code = getattr(error, "code", None)
    return code is not None and str(code) == str(MALFORMED_RANGE_CODE)


def _covered_cell_hit(target: WriteRange, merges) -> Optional[str]:
    """The first merge whose **covered** (non-anchor) cell the ``target`` range intersects,
    as an actionable detail string — or ``None`` if the target touches no covered cell
    (LD-122 / D4). ``merges`` are 0-idx END-inclusive regions (v3 dicts or 4-tuples). The
    anchor (a merge's top-left cell) is writable; every other cell is covered."""
    for m in merges or []:
        sr, er, sc, ec = _normalize_merge(m)
        r_lo, r_hi = sr + 1, er + 1  # 0-idx end-inclusive → 1-idx WriteRange space
        c_lo, c_hi = sc + 1, ec + 1
        ir_lo, ir_hi = max(target.start.row, r_lo), min(target.end.row, r_hi)
        ic_lo, ic_hi = max(target.start.col, c_lo), min(target.end.col, c_hi)
        if ir_lo > ir_hi or ic_lo > ic_hi:
            continue  # no overlap with this merge region
        only_anchor = ir_lo == ir_hi == r_lo and ic_lo == ic_hi == c_lo
        if only_anchor:
            continue  # a write to exactly the anchor cell is allowed
        anchor = A1Cell(c_lo, r_lo).a1()
        return (
            f"target {target.a1()} intersects merge (0-idx {(sr, er, sc, ec)}, anchor "
            f"{anchor}) covering a non-anchor cell — a merge keeps only its anchor's value, "
            f"so a covered-cell write would be dropped or corrupt the merge"
        )
    return None


def _revision_of(reply) -> Optional[int]:
    """The post-write ``revision`` carried by a value-write reply ``data`` (or ``None`` —
    the dimension replies and some value replies omit it; the caller falls back to
    ``metainfo``, spike Q4)."""
    if isinstance(reply, dict):
        return reply.get("revision")
    return None


def _post_write_revision(reply, fallback, *, extract=_revision_of) -> Optional[int]:
    """The post-write ``revision`` for ONE apply leg: the reply's own, else the leg's fallback.

    The single ending every ``_apply_*_one`` shares (LD-223 / N3). Both variable parts are
    **parameters**, because the nine legs are not one shape — they are three, and two of them
    are load-bearing:

    * **Shape A** (7 legs) — the flat :func:`_revision_of`, falling back to one ``metainfo``
      ``read_revision``. The replies for dimension / merge / tab / dropdown and some value
      writes omit ``revision`` entirely (spike Q4), so the fallback really does fire.
    * **Shape B** (the FREEZE leg) — its fallback is the ``read_frozen_panes`` result **already
      in hand**, so verification and the compare-and-swap anchor cost ONE call between them.
    * **Shape C** (the STYLE leg) — its extractor is :func:`_style_reply_revision`, because
      ``PUT …/style`` reports the revision **nested** at ``data.updates.revision`` where the
      flat reader finds nothing.

    ``fallback`` is a **zero-argument callable and is called only when the reply carried
    nothing**. That laziness is the whole carve-out: an eagerly-evaluated fallback argument
    would spend Shape A's ``metainfo`` read on every write, and — worse — would turn the freeze
    leg's in-hand lookup into a second network read it has never made. Pinned by the ordered
    call journals in ``tests/test_sheets_verification_leg_seam.py``.
    """
    post_revision = extract(reply)
    if post_revision is None:
        post_revision = fallback()
    return post_revision
