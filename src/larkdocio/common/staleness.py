"""larkdocio.common.staleness — the ONE staleness-marker core (LD-143 / T1).

**What lives here: the vocabulary a never-silent staleness guard is stated in** — the two
availability markers and the **single** :func:`revision_guard_status` classifier that both
write surfaces (docx ``write/`` and ``sheets/``) share. Nothing else. This module is a
**leaf**: standard library only, no larkdocio imports, so any surface can import it with no
cycle and no SDK.

**Why it exists (the drift it closes).** ``write/revision.py`` and ``sheets/plan.py`` each
carried their own copy of the markers *and* their own classifier — the sheets docstring said
"mirrored from" outright — and the copies had **already drifted**: docx classified a
**negative / negative-string** anchor ``unavailable``; sheets classified the same value
``active``. Two hand-maintained definitions of one safety vocabulary is one definition too
many, and a third (Base) was next on the roadmap.

**The adopted policy: the docx (stricter) rule.** Any non-positive anchor — ``None``, ``0``,
a negative number, and the string shapes of each — is **unavailable**. This *reclassifies*
the sheets treatment of a negative anchor (``active`` → ``unavailable``), the one
consumer-visible change LD-143 makes, and it **cannot weaken a guard**:

* on **sheets** the marker is **disclosure only** — enforcement is the independent
  ``live != expected`` compare-and-swap in ``sheets/ops/__init__.py::_apply_one``, which never reads
  the marker — so a negative-anchor plan still refuses ``STALE_SHEET`` with zero writes on
  drift (pinned by ``tests/test_staleness_core.py``), and no sheets ``revision`` can be
  negative anyway;
* on **docx** the marker *does* gate the whole-document compare-and-swap, and there
  ``-1 → unavailable`` is the **correct** answer: ``-1`` is the *"against latest"* pin in the
  ``document_revision_id=-1`` query every block call carries, not a revision. Arming a
  compare-and-swap against a request option would be the lying-``active`` failure the
  never-silent contract exists to prevent.

**What deliberately did NOT move here.** Each surface keeps its own
``revision_guard_semantics()`` — the ``detail`` wording is surface-specific (docx names
``document_revision_id`` and the per-entry ``STALE_ANCHOR`` fallback; sheets tells the
two-tier story and carries a ``tiers`` key) — and each surface keeps its own **enforcement**
semantics (per-entry skip vs whole-batch-zero-writes vs resync-and-continue), a divergence the
refactor audit and the maintainer both settled as deliberate. **Share the vocabulary; never the
semantics.**

Both surfaces **re-export** these names from their existing public paths, so no import path
moved (the LD-061 / LD-126 shim precedent).
"""

#: The plan-time anchor is usable: a difference before the write is observable, so the
#: compare-and-swap is live and a drifted target refuses. (docx: the whole-document CAS;
#: sheets: tier 1, the ``revision`` CAS.)
REVISION_GUARD_ACTIVE = "active"
#: The plan carries no usable anchor (none was supplied, the payload had none, or the value
#: cannot anchor a comparison), so that compare-and-swap cannot observe an advance. **Never**
#: silently: the plan says so, and each surface's other guard still enforces — the per-entry
#: ``STALE_ANCHOR`` re-validation on docx, the tier-2 value precondition on sheets.
REVISION_GUARD_UNAVAILABLE = "unavailable"


def revision_guard_status(revision) -> str:
    """:data:`REVISION_GUARD_ACTIVE` / :data:`REVISION_GUARD_UNAVAILABLE` for a plan-time
    ``revision`` — the anchor's **availability**, never a guess about the document or sheet.

    The one classifier both write surfaces use. ``None`` — no revision supplied to
    the previewer, or a meta payload that carried none — is **unavailable**: there is nothing
    to compare. So is any **non-positive** value:

    * ``0`` — the sheets per-spreadsheet sentinel: comparing ``0 == 0``
      before every write cannot observe an advance and would make the guard silently inert.
      Never observed on a docx (a fresh document is ``1``), and classified the same way there;
    * a **negative** value — the docx-specific trap: ``-1`` is the *"against latest"* pin in
      the ``document_revision_id=-1`` query every block call carries, and a consumer copying
      that literal into the previewer would otherwise arm a guard that compares a request
      option against a document revision. It is not an anchor; say so. (This is the stricter
      rule both surfaces adopted.)

    The string shapes an API drift could hand back (``"0"``, ``"-1"``, ``""``, whitespace) are
    classified unavailable rather than *treated* as healthy just because they compare unequal
    to a later value. A non-numeric string stays **active**: an opaque token still compares
    exactly, so an advance is observable. An anchor that cannot be ordered at all falls back
    to unavailable — an honest answer beats an exception at the safety boundary.
    """
    if revision is None:
        return REVISION_GUARD_UNAVAILABLE
    if isinstance(revision, str):
        text = revision.strip()
        if text in ("", "0"):
            return REVISION_GUARD_UNAVAILABLE
        try:
            return (REVISION_GUARD_UNAVAILABLE if int(text) <= 0
                    else REVISION_GUARD_ACTIVE)
        except ValueError:
            return REVISION_GUARD_ACTIVE      # an opaque but comparable token
    try:
        return REVISION_GUARD_UNAVAILABLE if revision <= 0 else REVISION_GUARD_ACTIVE
    except TypeError:      # an exotic, unorderable anchor type; the honest fallback
        return REVISION_GUARD_UNAVAILABLE
