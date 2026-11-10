"""larkdocio.common.disposition — the ONE apply-time disposition-boundary core (LD-533).

**What lives here: the MECHANISM a never-escaping write boundary is built out of** — the
scope vocabulary, the :class:`Disposition` value object, the :class:`WriteWatch` proxy that
answers *did it land*, the two never-raising text helpers, and the one detail formatter that
runs inside the boundary. Nothing else. This module is a **leaf**: standard library only, no
``larkdocio`` imports, so any write surface can import it with no cycle and no SDK — the
:mod:`larkdocio.common.staleness` shape.

**Why it exists (the drift it closes).** ``base/disposition.py`` and ``sheets/disposition.py``
each carried their own copy of this machinery — the base module's header said its shape *is*
the sheets module's, outright — and the copies had drifted in **both** directions:

* base's watch had gained a ``seams`` **parameter** (the schema engine needs the identical
  did-it-land accounting over a different set of client methods) while the sheets copy was
  still hardcoded to one module-level set;
* the sheets copy carried the fuller account of the three hazards
  :func:`safe_denial` handles, while base's said one line.

**The base module's own ``WriteWatch`` docstring named the cure before it existed:** *"a
parameter rather than a second class because … two copies of a safety boundary is one copy too
many."* That sentence was a prophecy about a copy that was still standing. What now holds, and
what it becomes: **there is ONE copy.** The parameter is here, the mechanism is here, and each
surface's module binds only its own default seam set — so a hazard fixed at this boundary is
fixed for every engine that imports it, which is the whole safety argument for the move.

**The measured resolution of the drift (LD-533).** Every value both surfaces genuinely shared
was already **byte-identical at runtime** — the two denial paragraphs (202 and 170 characters),
the two scope strings, and the bodies of both ``safe_*`` helpers — so unifying them changes no
text a consumer reads. The prose that differed was **documentation**, and the fuller account
won and travelled here; the only mechanical convergence is the sheets watch reading its seam
set from the instance rather than a module global, which is what makes the ``seams`` parameter
one class instead of two.

**What deliberately did NOT move here.** Each surface keeps its **own** classification table
(``classify_apply_exception`` and the ``Disposition`` rows behind it — base's are ruled and
differ from sheets' by design), its **own** seam sets, its **own** detail templates and
fallback wording, and its **own** typed refusal family. Base additionally keeps its read-vouch,
platform-anomaly and protected-last-advice machinery, none of which sheets has. **Share the
mechanism; never the classification.**

Both surfaces **re-export** every name they published before, so no import path moved (the
:mod:`larkdocio.common.staleness` precedent).

**The deliberate ``BaseException`` carve-out, stated once for both surfaces.** Nothing here
catches :class:`BaseException`: a ``KeyboardInterrupt`` / ``SystemExit`` / ``MemoryError`` is
the interpreter or the operator tearing the process down, and swallowing it into a log entry
would be a worse bug than the one this boundary prevents. The ``except Exception`` clauses
below are that carve-out, not an oversight.
"""
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Disposition scope — the vocabulary both engines state their split in          #
# --------------------------------------------------------------------------- #

#: The failure is attributable to **this call / this entry**: refuse its entries, keep going.
#: (On sheets this is the per-entry doctrine; on base it is the ruled entry-scoped arm. The
#: vocabulary is shared; what each surface classifies INTO it is not.)
ENTRY_SCOPED = "entry-scoped"
#: The failure is **not** call-local (or its blast radius is unknown): halt and log every
#: remaining entry ``not-attempted``.
SYSTEMIC = "systemic"


# --------------------------------------------------------------------------- #
# The write watch — the did-it-land answer, and the ONE copy of it              #
# --------------------------------------------------------------------------- #

class WriteWatch:
    """A proxy over the write client that records the **write** seams it ran.

    Wrapping the client keeps the apply legs untouched — the boundary is one seam, and a leg
    cannot forget to report. Every attribute is forwarded verbatim, so duck-typed probing still
    works: ``getattr(watch, "query_tabs", None)`` is ``None`` exactly when the underlying
    client has no ``query_tabs``.

    :attr:`issued` becomes true when a write seam is *entered*; :attr:`wrote` only when one
    **returned**, and that difference is the whole point: a write that raised did not land, a
    write that returned did — and a failure *after* that is a verification gap, not a refusal.
    Without it the boundary could only guess whether a failure left the target untouched, and a
    log that guesses is a log that lies: **a post-write anchor read that fails must NOT be
    reported as "nothing landed".**

    ``seams`` is which method names count as writes. It is a **parameter rather than a second
    class** because one engine needs the identical did-it-land accounting over a different set
    of client methods (base's schema engine, which passes its own set), and two copies of a
    safety boundary is one copy too many — the reason this class is here at all.

    **How the default is bound, and why it is not a value on this class.** This module is a
    leaf: it cannot import either surface's seam registry, so it cannot name a default without
    becoming a surface. A watch built with no ``seams`` therefore resolves
    :attr:`DEFAULT_SEAMS`, which each surface binds on a subclass whose only content IS that
    binding. Resolving to ``None`` **raises** rather than watching nothing: a watch that
    watched no seams would report "nothing landed" about a call that landed something, which is
    the one failure the whole boundary exists to prevent.
    """

    __slots__ = ("_client", "_issued", "_completed", "_seams")

    #: The seam set a bare ``WriteWatch(client)`` uses. ``None`` on this core — a surface binds
    #: it (see the class docstring); resolving ``None`` is an error, never an empty watch.
    DEFAULT_SEAMS = None

    def __init__(self, client, seams=None):
        if seams is None:
            seams = type(self).DEFAULT_SEAMS
        if seams is None:
            raise TypeError(
                f"{type(self).__name__} needs a write-seam set: pass seams=… or use a "
                "surface's watch, which binds DEFAULT_SEAMS. A watch with no seams would "
                "report 'nothing landed' about a call that landed something.")
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_issued", [])
        object.__setattr__(self, "_completed", [])
        object.__setattr__(self, "_seams", frozenset(seams))

    @property
    def issued(self) -> tuple:
        """The write seams **entered**, in call order."""
        return tuple(self._issued)

    @property
    def completed(self) -> tuple:
        """The write seams that **returned**, in call order."""
        return tuple(self._completed)

    @property
    def wrote(self) -> bool:
        """True iff at least one write seam **returned** — the change IS on the target."""
        return bool(self._completed)

    def __getattr__(self, name):
        # Only reached for names that are not slots — i.e. everything the engine calls.
        attr = getattr(self._client, name)
        if name not in self._seams or not callable(attr):
            return attr

        def _watched(*args, **kwargs):
            self._issued.append(name)
            reply = attr(*args, **kwargs)
            self._completed.append(name)
            return reply

        return _watched


# --------------------------------------------------------------------------- #
# Disposition — one exception → one typed, logged outcome                       #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Disposition:
    """How ONE failed apply step is recorded and what the batch does next.

    * ``scope`` — :data:`ENTRY_SCOPED` (continue) or :data:`SYSTEMIC` (halt);
    * ``reason`` — the surface's typed refusal reason constant;
    * ``outcome`` — the apply-log ``outcome`` (``refused`` / ``failed`` /
      ``applied-unverified``);
    * ``landed`` — ``"no"`` / ``"yes"`` / ``"indeterminate"``: whether the target changed. The
      honest third value is why ``failed`` is not called a refusal.

    The **rows** — which exception becomes which disposition — are each surface's own, and
    deliberately so; this is only the shape they are stated in.
    """

    scope: str
    reason: str
    outcome: str
    landed: str

    @property
    def halts(self) -> bool:
        return self.scope == SYSTEMIC

    @property
    def continues(self) -> bool:
        return self.scope == ENTRY_SCOPED


# --------------------------------------------------------------------------- #
# The never-raising text helpers — defense in depth inside the boundary         #
# --------------------------------------------------------------------------- #

#: What a scope-denial detail says when the exception carries no usable denial record. Its
#: whole job is to state an ABSENCE rather than fill it: no scope string is invented, ever (a
#: guessed grant sends someone to widen the wrong permission).
DENIAL_ABSENT = (
    "This refusal carries no structured denial record, so no scope name is stated here — none "
    "is invented. Read the code and message above: they are Lark's own answer, and they name "
    "the grant the call needs."
)

#: The same, for a denial record whose own rendering failed.
DENIAL_UNRENDERABLE = (
    "The structured denial record could not be rendered, so it is reported as unavailable "
    "rather than guessed at. Read the code and message above — they are Lark's own answer."
)


def safe_text(exc) -> str:
    """``str(exc)`` that cannot itself raise — a badly-behaved ``__str__`` must not be able to
    break the one path whose whole job is not raising (defense in depth)."""
    try:
        return str(exc)
    except Exception:   # noqa: BLE001 — a message is worth less than the invariant
        return f"<unprintable {type(exc).__name__}>"


def safe_denial(exc) -> str:
    """Lark's own denial paragraph for a scope refusal — and it cannot raise.

    Three hazards, all real and all handled, because this runs **inside** the boundary whose
    entire job is not raising: the attribute may be absent or ``None`` (a permission error
    built without a response body has no denial record), the attribute access itself may raise
    (a property), and ``detail()`` is someone else's code. An ``AttributeError`` / ``KeyError``
    escaping here would re-open the exact hole the disposition boundary exists to close — the
    same reasoning as :func:`safe_text`, one layer out.
    """
    try:
        denial = getattr(exc, "denial", None)
        if denial is None:
            return DENIAL_ABSENT
        text = denial.detail()
    except Exception:   # noqa: BLE001 — a paragraph is worth less than the invariant
        return DENIAL_UNRENDERABLE
    if not isinstance(text, str) or not text.strip():
        return DENIAL_ABSENT
    return text


def disposition_detail(disposition, exc, *, where, wrote_seams=(),
                       templates, fallback, extra=None) -> str:
    """The formatted ``detail`` for a classified failure — the skeleton both engines share.

    ``templates`` is the surface's own ``{reason: template}`` table and ``fallback`` its own
    last-resort wording; both stay per-surface because the words are surface-specific, and the
    fallback exists at all because this code runs **inside** the boundary that must never
    raise — a ``KeyError`` on an unmodelled reason would re-open the exact hole it closes.

    ``extra`` supplies whatever a surface's own templates name and this skeleton does not know
    (base's ``aftermath`` sentence is the one such field today). Unused keys are harmless:
    :meth:`str.format` ignores them, which is what lets one formatter serve two template sets.
    """
    template = templates.get(disposition.reason, fallback)
    return template.format(
        where=where,
        exc=safe_text(exc),
        exc_type=type(exc).__name__,
        code=getattr(exc, "code", None),
        msg=getattr(exc, "msg", None),
        wrote_seams=", ".join(wrote_seams) or "unknown seam",
        reason=disposition.reason,
        landed=disposition.landed,
        denial=safe_denial(exc),
        **(extra or {}),
    )
