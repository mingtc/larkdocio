"""THE MEDIA-MINTING GUARDRAIL (LD-505) — the mechanism half.

:mod:`gate_registry` says which live files **mint permanent, unpurgeable drive media**. This
module turns that data into a decision, and ``tests/conftest.py`` wires the decision into
collection. The rule it enforces, in one sentence:

    **A ring that mints permanent drive media does not run unless the run NAMES the issue that
    authorized the spend.**

Why a default of *skip* rather than *run*. A media upload is the only thing a live ring does
that cannot be undone: **no route in Lark's open API purges drive media — measured, not
assumed** (``larkdocio.base.media.NO_ROUTE_PURGES_DRIVE_MEDIA``, ruled ``D-95``), and deleting
the parent does not remove it. Every other live cost is a disposable somebody deletes in a
``finally``; this one is permanent tenant residue. A default that spends it is a default that
spends it by accident.

**THE SKIP IS LOUD, ALWAYS.** The house invariant is *"a live gate never silently passes"*
(PROJECT.md § The binding QA gate), and this must not become a second way to look green while
doing nothing. So a gated run says, in the message a human reads: that the ring mints
permanent unpurgeable drive media, the exact variable that opts in, that the value must be an
authorizing issue id, and where the doctrine lives. ``conftest`` additionally writes one line
straight to the terminal reporter, because a skip *reason* is only shown under ``-rs``.

**THE OPT-IN'S VALUE IS THE AUTHORIZING ISSUE ID, NOT A TRUTHY FLAG.**
``LARKDOCIO_MEDIA_MINT_AUTHORIZED_BY=LD-507``. An id travels into the run's own transcript,
so the answer to *"who said yes?"* is in the evidence a QA leg pastes rather than in somebody's
shell history. A bare ``1`` is refused for exactly that reason.

**THE ECHO IS NOT A PERMISSION CHECK.** This module does **not** decide which issues may mint,
and there is deliberately **no allow-list of issue ids anywhere in this tree** — a list would
have to be edited by the very leg it is meant to restrain. What the mechanism does is **record
a claim** and put it in the transcript. The **authority** is the maintainer's word in the issue file
(a budget declared before the first send); QA reads both, and a run whose echoed id does not
match an issue that was actually authorized is a QA failure, not a passing run.

**THE DEFAULT OFFLINE SUITE IS UNTOUCHED, BY CONSTRUCTION.** :func:`hook_is_active` is false
for any ``-m`` expression that cannot select a ring test — which is exactly ``pyproject.toml``'s
default ``addopts`` — so a plain ``pytest`` collects the same items, skips the same 3 tests and
prints the same lines it did before this module existed. Nothing here reads the environment,
marks an item or writes a line on that path.

This module is pure: standard library plus :mod:`gate_registry`. It imports no gate module,
executes nothing, and makes no API call.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import gate_registry as gr

#: The opt-in. Its VALUE is the authorizing issue id — see the module docstring.
OPT_IN_ENV = "LARKDOCIO_MEDIA_MINT_AUTHORIZED_BY"

#: What a well-formed value looks like. ``ISSUE_PREFIX=LD`` (``scripts/config.sh``).
ISSUE_ID_RE = re.compile(r"^LD-\d{3,}$")

#: Where the doctrine lives, quoted into every message so the skip is a signpost.
DOCTRINE = "requirements/DECISIONS.md D-97"

#: Where to look BEFORE minting a new one.
REUSE_POINTER = "dev/media-token-ledger.md"

_WHAT_IT_COSTS = (
    "this ring UPLOADS BYTES and mints PERMANENT, unpurgeable drive media: no route in Lark's "
    "open API purges drive media (measured, D-95) and deleting the parent does not remove it"
)
_HOW_TO_OPT_IN = (
    f"to run it, set {OPT_IN_ENV} to the id of the issue that authorized the spend, e.g. "
    f"{OPT_IN_ENV}=LD-507 — the value must be an issue id (LD-NNN), not a truthy flag, so the "
    "authorization travels in the run's own transcript"
)
_WHERE_THE_DOCTRINE_IS = (
    f"the two grounds on which a mint is allowed are in {DOCTRINE}; what already exists, to "
    f"reuse instead of minting, is indexed in {REUSE_POINTER}"
)


@dataclass(frozen=True)
class Authorization:
    """The parsed opt-in. ``state`` is one of ``absent`` / ``malformed`` / ``claimed``."""

    state: str
    issue_id: str | None
    message: str

    @property
    def authorized(self) -> bool:
        return self.state == "claimed"


def authorization(environ=None) -> Authorization:
    """Read the opt-in out of ``environ`` (defaults to the real one) and say what it means.

    Three outcomes and **not one of them is a silent run**: unset ⇒ skip, unparseable ⇒ skip
    with a message about the value, well-formed ⇒ run with the id echoed.
    """
    env = os.environ if environ is None else environ
    raw = env.get(OPT_IN_ENV)
    if raw is None or not raw.strip():
        return Authorization(
            "absent",
            None,
            f"MEDIA-MINT GUARDRAIL: skipped because {OPT_IN_ENV} is not set — "
            f"{_WHAT_IT_COSTS}. {_HOW_TO_OPT_IN}. {_WHERE_THE_DOCTRINE_IS}.",
        )
    value = raw.strip()
    if not ISSUE_ID_RE.match(value):
        return Authorization(
            "malformed",
            None,
            f"MEDIA-MINT GUARDRAIL: skipped because {OPT_IN_ENV}={value!r} is not an issue id "
            f"— the value must be an issue id of the form LD-NNN (the issue whose maintainer-declared "
            f"budget authorizes the spend), never a truthy flag. {_WHAT_IT_COSTS}. "
            f"{_WHERE_THE_DOCTRINE_IS}.",
        )
    return Authorization(
        "claimed",
        value,
        f"MEDIA-MINT GUARDRAIL: media-minting rings are ENABLED, authorized by {value} "
        f"(read from {OPT_IN_ENV}). This is a RECORDED CLAIM, not a permission check — no "
        f"allow-list of issue ids exists in this tree; the authority is the maintainer's declared "
        f"budget in {value}'s own issue file, and QA reads both. {_WHAT_IT_COSTS}.",
    )


def gated_files() -> frozenset[str]:
    """The filenames the guardrail gates — read from the registry, never hand-typed."""
    return frozenset(gr.media_minting_gates())


def should_gate(nodeid: str, decision: Authorization) -> bool:
    """True when this collected item belongs to a minting file and nothing authorized it."""
    if decision.authorized:
        return False
    filename = nodeid.split("::", 1)[0].rsplit("/", 1)[-1]
    return filename in gated_files()


def hook_is_active(markexpr: str | None) -> bool:
    """True only when the run's ``-m`` expression can select a ring test.

    The default offline expression deselects every ring, so the hook does nothing at all
    there — no mark, no message, no perturbation of the plain suite (LD-505 AC2/AC6). The
    ring-selection reading is ``conftest.ring_selection_requires_serial``'s, reused rather
    than restated: one definition of *"can this run reach a live test?"*.
    """
    from conftest import ring_selection_requires_serial

    return ring_selection_requires_serial(markexpr)
