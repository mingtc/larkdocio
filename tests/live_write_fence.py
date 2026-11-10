"""THE LIVE-WRITE CONSENT FENCE (LD-537) — the judgement half.

**Selection and consent are two different questions.** Until this module existed only the
first one was asked: ``pyproject.toml``'s ``addopts`` **deselects** the ``live_write`` ring, and
a deselection is a *selection* control that one typed ``-o addopts=""`` clears. That flag has
now been typed **twice** on runs that executed tests — wave 0 (≈3 permanent, unpurgeable media
tokens, ids lost) and wave 2 on 2026-08-20 (**15 disposable Bases created**, 14 self-deleted,
and the 15th — ``BaseGoneExample000000000001`` — read as **gone by the oracle on 2026-08-25**:
the bitable route no longer resolves it, while its ledger row still reads ``deleted: false``.
**Whether a human reclaimed it or it aged past the lag horizon is not established by that
reading**, and this module's reason does not depend on which: both incidents that earned the
fence were a *typed flag*.) The second was caught only by a ``sha256`` of
``.base-disposables.json`` taken before and after a leg, **after three self-reports and two
complete QA reviews missed it**. The rule this module enforces, in one sentence:

    **A ``live_write``-marked test does not EXECUTE unless the run NAMES the issue that
    authorized it — whatever the ``addopts`` state.**

So the deselection stays (it is the first of two fences, and its *reason* — a default run must
never reach the tenant — is preserved unchanged) and this is the second: ``-o addopts=""``
**re-selects** the ring but cannot **re-arm** it.

**KEYED ON THE MARKER, NOT ON A LIST — exhaustive by construction.** The activation condition
is the collected item's own ``live_write`` marker, so a write gate added tomorrow is fenced with
**no registration step anywhere**: no filename list, no ``gate_registry`` row, no per-gate edit.
This is the one place LD-505's media guardrail is deliberately **not** copied — that fence is
file-data-driven because *"which file uploads bytes"* is a judgement call, whereas *"is this
test in the write ring"* is already answered by the marker the test carries.

**NOTHING HERE READS THE RUN'S SELECTION STATE.** LD-505's hook first asks whether the ``-m``
expression *could* select a ring (``media_guardrail.hook_is_active``). This fence deliberately
does not need that question answered correctly: if no ``live_write`` item reaches execution
there is nothing to fence, and if one does the fence applies. The reading is not reused,
because reusing it would make a *precondition* out of something this fence is stronger without.

**THE SKIP IS LOUD, ALWAYS.** The house invariant is *"a live gate never silently passes"*
(PROJECT.md § The binding QA gate). A fenced run says, in the words a human reads: that the ring
creates real objects in the live Lark tenant, the exact variable that opts in, that the value
must be an authorizing issue id, that clearing ``addopts`` re-selects but does not arm, and
where the residue is ledgered so a reader who does fire it knows what to check afterwards.

**THE OPT-IN'S VALUE IS THE AUTHORIZING ISSUE ID, NOT A TRUTHY FLAG.**
``LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-537``. Here that is not symmetry with LD-505 for its own
sake, it is the fence's teeth: **both incidents were a typed flag**, and no plausible slip types
``LD-533``. What an issue id *is* comes from one definition, imported —
:data:`media_guardrail.ISSUE_ID_RE` — never restated here.

**THE ECHO IS A RECORDED CLAIM, NOT A PERMISSION CHECK.** This module does not decide which
issues may fire the write ring, and there is deliberately **no allow-list of issue ids anywhere
in this tree** — a list would have to be edited by the very leg it is meant to restrain. What
the mechanism does is **record a claim** and put it in the transcript a QA leg pastes. The
**authority** is the maintainer's word in the named issue file; QA reads both, and a run whose echoed id
does not match an issue that actually authorized it is a QA failure, not a passing run.

**THE DEFAULT OFFLINE SUITE IS UNTOUCHED.** The wiring in ``tests/conftest.py`` is an
execution-time hook plus one line written at ``pytest_collection_finish`` from the **final**
selected item set — so on the default selection, where no ``live_write`` item survives, no test
is marked, no line is written and no skip is added.

This module is pure: standard library plus :mod:`media_guardrail`'s one regex. It imports no
gate module, executes nothing, and makes no API call.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from media_guardrail import ISSUE_ID_RE

#: The consent variable. Its VALUE is the authorizing issue id — see the module docstring.
#: Deliberately the same dialect as ``LARKDOCIO_MEDIA_MINT_AUTHORIZED_BY``: a leg who knows one
#: knows the other, and one ``.env.example`` neighbourhood carries both.
OPT_IN_ENV = "LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY"

#: The marker the fence keys on. The ring's own membership test — not a file list.
RING_MARKER = "live_write"

#: Where the residue of a fired ring is ledgered, quoted into every message.
RESIDUE_LEDGER = ".base-disposables.json"

#: The harness verb that reports what a ring left behind.
RESIDUE_VERB = "tests/base_write_harness.py's orphans()"

_WHAT_IT_COSTS = (
    "this ring CREATES REAL OBJECTS IN THE LIVE LARK TENANT — documents, Bases, spreadsheets "
    "and folders it provisions for itself — and in eight of its files it uploads bytes that "
    "NOTHING can purge (no route in Lark's open API purges drive media: measured, D-95)"
)
_WHY_DESELECTION_IS_NOT_ENOUGH = (
    "clearing the default deselection (-o addopts=\"\") RE-SELECTS this ring but does NOT ARM "
    "it: selection and consent are two different questions, and this fence answers the second "
    "(LD-537, after two incidents in which the flag was typed on an executing run)"
)
_HOW_TO_OPT_IN = (
    f"to run it, set {OPT_IN_ENV} to the id of the issue that authorized the run, e.g. "
    f"{OPT_IN_ENV}=LD-537 — the value must be an authorizing issue id (LD-NNN), never a truthy "
    "flag, so the authorization travels in the run's own transcript"
)
_WHERE_THE_RESIDUE_IS = (
    f"what a fired ring leaves behind is ledgered in {RESIDUE_LEDGER} and reported by "
    f"{RESIDUE_VERB} — check both afterwards, and reclaim anything still live"
)


@dataclass(frozen=True)
class Consent:
    """The parsed opt-in. ``state`` is one of ``absent`` / ``malformed`` / ``claimed``."""

    state: str
    issue_id: str | None
    message: str

    @property
    def authorized(self) -> bool:
        return self.state == "claimed"


def consent(environ=None) -> Consent:
    """Read the opt-in out of ``environ`` (defaults to the real one) and say what it means.

    Three outcomes and **not one of them is a silent run**: unset ⇒ loud skip, unparseable ⇒
    loud skip whose message says the value must be an issue id, well-formed ⇒ the ring runs and
    the id is echoed into the run's own output.
    """
    env = os.environ if environ is None else environ
    raw = env.get(OPT_IN_ENV)
    if raw is None or not raw.strip():
        return Consent(
            "absent",
            None,
            f"LIVE-WRITE CONSENT FENCE: skipped because {OPT_IN_ENV} is not set — "
            f"{_WHAT_IT_COSTS}. {_WHY_DESELECTION_IS_NOT_ENOUGH}. {_HOW_TO_OPT_IN}. "
            f"{_WHERE_THE_RESIDUE_IS}.",
        )
    value = raw.strip()
    if not ISSUE_ID_RE.match(value):
        return Consent(
            "malformed",
            None,
            f"LIVE-WRITE CONSENT FENCE: skipped because {OPT_IN_ENV}={value!r} is not an issue "
            f"id — the value must be an authorizing issue id of the form LD-NNN (the issue "
            f"whose maintainer-declared authorization covers this run), never a truthy flag. "
            f"{_WHAT_IT_COSTS}. {_WHY_DESELECTION_IS_NOT_ENOUGH}. {_WHERE_THE_RESIDUE_IS}.",
        )
    return Consent(
        "claimed",
        value,
        f"LIVE-WRITE CONSENT FENCE: the live_write ring is ARMED, authorized by {value} (read "
        f"from {OPT_IN_ENV}). This is a RECORDED CLAIM, not a permission check — no allow-list "
        f"of issue ids exists in this tree; the authority is the maintainer's word in {value}'s own "
        f"issue file, and QA reads both. {_WHAT_IT_COSTS}. {_WHERE_THE_RESIDUE_IS}.",
    )


def in_the_write_ring(item) -> bool:
    """True when this collected item carries the ``live_write`` marker.

    The whole activation condition, and the reason the fence needs no registration step: a
    module-level ``pytestmark = pytest.mark.live_write`` (how every gate in the ring declares
    itself) is what ``get_closest_marker`` reads.
    """
    return item.get_closest_marker(RING_MARKER) is not None


def should_fence(item, decision: Consent) -> bool:
    """True when this item is in the write ring and nothing authorized the run."""
    return not decision.authorized and in_the_write_ring(item)


def compose(decision: Consent, other_reasons) -> str:
    """The fence's message, carrying any OTHER gate's reason for the same item alongside it.

    An item can be gated twice — 29 of the ring's tests across 8 files are also held by
    LD-505's media guardrail. pytest reports **one** skip reason per test, so a doubly gated
    test would otherwise lose a message. Both fences are independent and both reasons are true,
    so both travel.
    """
    extra = [r.strip() for r in other_reasons if r and r.strip()]
    if not extra:
        return decision.message
    return decision.message + "".join(f"  ||  ALSO GATED, INDEPENDENTLY: {r}" for r in extra)
