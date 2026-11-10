"""THE CAPTURE SINK (LD-620) — no test run may write inside a git working tree.

**The hazard, four times.** An armed ``pytest -m live_write`` run rewrote committed
``dev/**/captures/*.json`` files belonging to CLOSED issues, because every live gate wrote its
capture back to the same in-tree path it had been committed at. ``ld317-01`` → **``LD-497``**
(reverted on trunk: *"the probe re-run rewrote a COMMITTED capture that landed
tests PIN … the ld317-01 precedent applies, the capture is restored"*) → LD-619's Dev leg (20
files) → LD-619's QA (19 files, hours later, a different actor on the same documented
procedure). **Three reverts, zero fixes.** A hazard that recurs on a widening blast radius is
not an incident, it is a missing fence.

**Why a revert is not the fix, and why this module is LOUD.** In
``tests/captures/base-study/captures/ld336-01-fields-at-creation.json`` the same-window control was
laundered ``9499`` / *"Invalid parameter type…"* → ``0`` / *"success"* **while the same file's
own ``_note`` still argued** *"a kitted create that applied beside a 9499 control is the premise
HOLDING"*. The file contradicted itself: its prose reasoned from a ``9499`` its data no longer
carried. A stale capture is wrong **and readable as wrong**; a laundered one reads as internally
coherent to anyone who does not already know what it used to say, because the surviving note
lends the rewritten number its own authority. **A future reader gets no signal at all** — so
this sink never redirects quietly. Every write says, in the words a human reads, where it was
aimed, where it landed, and what to do with it.

**TWO HALVES, and the second is the one that fixes the CLASS.**

*(a) The mechanism — a run-scoped destination.* :func:`destination_for` maps an intended
in-tree capture path to ``<run root>/<working tree name>/<path relative to that tree>``. The
run root is created once per process, outside every git working tree
(:data:`RUN_ROOT_ENV` overrides where, never whether). So the default is fixed: a re-run's
capture lands beside its intended path's own shape, under a directory nothing tracks, and
``git status --porcelain -- 'dev/**/captures/*.json'`` is **empty** after an armed run — not
merely free of modifications, free of untracked litter too.

*(b) The fence — a refusal keyed on the working tree, not on a path list.*
:func:`write_capture` checks its **final destination** and raises
:class:`TrackedCaptureWriteRefused`, naming the path and the tree it fell inside, if that
destination resolves within any git working tree. A path list would have to be edited by the
very leg it restrains, and would miss whatever future code reaches a tracked path by a route
the list never enumerated. **Working-tree membership is the property that actually matters**,
and it is decided by walking for ``.git`` — so the rule holds for the live checkout, for a
linked worktree (where ``.git`` is a *file*), and for a throwaway sandbox in ``tmp_path``
identically.

**NO GIT IS INVOKED, deliberately.** ``tests/test_no_test_reads_live_git.py`` forbids a test
from asking git about this checkout, and it is right to: a guard whose answer depends on the
branch that is out is true once and false afterwards. This module asks a question git is not
needed for — *am I inside a working tree?* — by reading the tree, and so the fence works with
no repository, no index and no network.

**The third half is structural and lives elsewhere.** Nothing in Python can stop a future site
from calling ``Path.write_text`` directly, so the census that keeps every capture-writing site
routed through here is an AST guard: ``tests/test_capture_write_sites.py``. This module is the
mechanism; that guard is the exhaustiveness.

**What a genuinely new measurement does.** It is a **supersession with a dated second reading**
— the LD-480 precedent — copied in deliberately by a human under its own issue, never an
in-place overwrite by a re-run. The message below says so at every write.
"""
from __future__ import annotations

import os
import pathlib
import tempfile
import time
import warnings

#: Where a run's captures land, when a human wants somewhere other than the OS temp dir. It
#: overrides **where**, never **whether**: a value inside a git working tree is refused by
#: :func:`write_capture` exactly as an in-tree intended path is, which is the one seam the
#: refusal half of this module exists to hold.
RUN_ROOT_ENV = "LARKDOCIO_LIVE_CAPTURE_DIR"

#: The issue that landed the fence, quoted into every message so a reader who meets the
#: redirect for the first time has somewhere to read the reasoning.
ISSUE = "LD-620"

#: The occurrences the fence was earned by, quoted into the message. Named, never counted —
#: the fourth was measured by a second actor hours after the third, on the same procedure.
PRIOR_OCCURRENCES = "ld317-01, LD-497 (reverted on trunk), LD-619's Dev leg, LD-619's QA"


class TrackedCaptureWriteRefused(RuntimeError):
    """A capture write whose destination fell inside a git working tree. Refused, not skipped.

    Raised rather than swallowed on purpose: a writer that quietly skips is as bad as one that
    quietly overwrites, because both leave the reader with a filename whose relationship to a
    measurement is unknown.
    """


def working_tree_root(path):
    """The nearest ancestor of ``path`` that holds a ``.git`` — or ``None`` if there is none.

    ``.git`` is accepted as a **directory or a file**: a linked worktree carries a ``gitdir:``
    pointer file, and a fence that only recognised the directory would let every write through
    in exactly the worktrees this project's runners use.

    ``path`` need not exist; only its ancestry is read.
    """
    candidate = pathlib.Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = (pathlib.Path.cwd() / candidate).resolve()
    for directory in (candidate, *candidate.parents):
        if (directory / ".git").exists():
            return directory
    return None


def _new_run_id():
    return f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{os.getpid()}"


#: This process's run id. Fixed at import so :func:`destination_for` is **pure within a run**:
#: a gate that writes a capture and a later test in the same run that reads it back agree on
#: the path without passing it around.
RUN_ID = _new_run_id()

_RUN_ROOT = None


def run_root():
    """The directory this run's captures land under, created on first use.

    Cached per process, so every capture of one run is collected in one place a human can list,
    copy from, or delete wholesale.
    """
    global _RUN_ROOT
    if _RUN_ROOT is None:
        configured = os.environ.get(RUN_ROOT_ENV)
        base = (pathlib.Path(configured).expanduser() if configured
                else pathlib.Path(tempfile.gettempdir()) / "larkdocio-live-captures")
        _RUN_ROOT = base / RUN_ID
    return _RUN_ROOT


def destination_for(intended):
    """Where a capture aimed at ``intended`` actually gets written.

    An intended path inside a git working tree is mapped to
    ``run_root()/<tree name>/<path relative to the tree>`` — the tree's name is kept so two
    working trees (a checkout and a linked worktree of it) cannot collide on one relative
    path. An intended path already outside every working tree is returned unchanged: there is
    nothing there to protect, and rewriting a caller's explicit out-of-tree choice would be
    the sink deciding something it was not asked to decide.
    """
    target = pathlib.Path(intended).expanduser()
    if not target.is_absolute():
        target = (pathlib.Path.cwd() / target).resolve()
    tree = working_tree_root(target)
    if tree is None:
        return target
    return run_root() / tree.name / target.relative_to(tree)


def announcement(intended, destination):
    """The words a human reads when a capture is redirected. One place, so both are the same."""
    return (
        f"\n{'=' * 78}\n"
        f"CAPTURE REDIRECTED ({ISSUE}) — the intended path is inside a git working tree.\n"
        f"  aimed at: {intended}\n"
        f"  written : {destination}\n"
        f"  why     : an armed live_write re-run OVERWROTE committed captures belonging to\n"
        f"            closed issues on four occasions ({PRIOR_OCCURRENCES}), once laundering\n"
        f"            a 9499 control to code 0 beside a _note still arguing from the 9499.\n"
        f"            A filename that no longer identifies a fixed measurement is the quiet\n"
        f"            failure of the whole evidence regime.\n"
        f"  next    : if this run MEASURED something new, land it as a supersession with a\n"
        f"            dated second reading under its own issue (the LD-480 precedent) — copy\n"
        f"            the file in deliberately. Never let a re-run overwrite the original.\n"
        f"{'=' * 78}"
    )


def write_capture(intended, text, *, encoding="utf-8"):
    """Write a capture aimed at ``intended``, out of harm's way, and say so out loud.

    Returns the path actually written, so a caller that reads its own capture back reads the
    file it just wrote rather than the committed one it was aimed at.

    Raises :class:`TrackedCaptureWriteRefused` if the destination still resolves inside a git
    working tree — the case :data:`RUN_ROOT_ENV` pointed at a checkout, or a future caller
    handed in a destination this module was never able to redirect. Refusing is the whole
    point: the alternative is a run that reports success while rewriting evidence.
    """
    target = pathlib.Path(intended).expanduser()
    destination = destination_for(target)
    tree = working_tree_root(destination)
    if tree is not None:
        raise TrackedCaptureWriteRefused(
            f"REFUSED to write the capture {destination} — it is inside the git working tree "
            f"{tree}, and a test run must never write a path a repository tracks (aimed at: "
            f"{target}). {ISSUE}: four armed live_write runs overwrote committed captures "
            f"this way ({PRIOR_OCCURRENCES}). Point {RUN_ROOT_ENV} at a directory outside "
            f"every working tree, or leave it unset for the OS temp dir."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding=encoding)
    if destination != target:
        message = announcement(target, destination)
        print(message)
        # Printed AND warned: pytest captures stdout per test, and the warnings summary is
        # shown by default — so the redirect reaches a reader of a quiet run too.
        warnings.warn(message, stacklevel=2)
    return destination
