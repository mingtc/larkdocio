"""Typed exception taxonomy for larkdocio.

The toolkit historically raised a **bare ``Exception``** on every failure path,
so callers could not tell a credential problem from an API error from a
rate-limit hit. This module gives the whole toolkit one small typed family, born
here first, so the shared core and the write client are typed
from the start rather than retrofitted:

* :class:`LarkDocIOError` — the single base every larkdocio error subclasses, so
  a caller can ``except LarkDocIOError`` to catch anything the toolkit raises.
* :class:`LarkConfigError` — a configuration / credential / unsupported-input
  problem (no Lark API round-trip involved).
* :class:`LarkEscapeError` — a :class:`LarkConfigError` subclass raised when escaped
  Markdown cannot be turned back into its literal text without guessing; it carries a
  mandatory ``detail`` naming the sequence it refused.
* :class:`MissingDestinationError` — a :class:`LarkConfigError` (and :class:`ValueError`)
  subclass raised when a create-class call names **no destination**. It is local and pre-API by
  construction: the whole point is that nothing is sent. The rule it enforces, and the
  measurements behind it, live on :mod:`larkdocio.common.destination`.
* :class:`LarkSnapshotIntegrityError` — a :class:`LarkConfigError` subclass raised when a
  persisted read (:mod:`larkdocio.snapshot`) fails its integrity check; it carries a
  machine-readable ``reason`` and its message always names **re-download** as the fix.
* :class:`LarkAPIError` — a Lark API call failed; it **carries Lark's ``code``
  and ``msg``** as accessible attributes.
* :class:`LarkRateLimitError` — a :class:`LarkAPIError` subclass for Lark's
  rate-limit code (:data:`RATE_LIMIT_CODE`, ``99991400``). The transport that
  *catches* it and backs off is the shared transport; this module only defines the type.
* :class:`LarkPermissionError` — a :class:`LarkAPIError` subclass for a **scope denial**,
  carrying a :class:`larkdocio.permissions.PermissionDenial` that names the exact missing
  permission, Lark's verbatim answer, and the console link Lark handed back. It exists so
  *"I could not look"* is distinguishable from *"I looked and it is not there"*, which is the
  distinction whose absence once turned a missing field-level grant into a five-day
  misdiagnosis.
* :class:`LarkSpreadsheetUnreadableError` — a :class:`LarkAPIError` subclass for the one case the
  Sheets workbook walk refuses to survive: **every** tab missed. A partial miss is skipped
  loudly and the walk completes; a total miss must not come back as an empty success.
* :class:`LarkPaginationError` — a cursor-paged walk could not be run to exhaustion (a
  repeated cursor, or fresh cursors past the walk's page cap), so its result would be a short
  list indistinguishable from a whole one. A :class:`LarkDocIOError` and deliberately **not**
  a :class:`LarkAPIError`: every page answered successfully, and there is no Lark ``code`` to
  carry.
* :class:`LarkApplyRefusedError` — a plan-gated ``apply()`` finished with one or more entries
  **refused**, and the caller did not opt into partial application. The reasoning behind it, and
  the one seam every apply surface enforces it through (:func:`gate_refusals`), are documented
  on the class.

**Message preservation (byte-identical CLI behavior).** Each error's ``str()`` is
the caller-supplied message **verbatim** — the API family stores ``code``/``msg``
as *extra* attributes without altering the message text. This keeps the existing
operator-facing wording unchanged.

**The REASON above is unchanged; one CONCLUSION drawn from it has moved (2026-08-20).**
What this paragraph used to conclude, verbatim: *"This keeps the existing
operator-facing wording and ``read.download._report_error``'s substring routing
unchanged."* The reason it gave — a message is the caller's words and this family adds
attributes rather than editing text — is as binding as it ever was, and it is still why
``str(err)`` is untouched.

What moved is only the *dependency* named at the end of it. ``read.download._report_error``
no longer routes on substrings of the message: it asks the exception what it IS — the class
(:class:`LarkPermissionError`) and ``code`` this family carries precisely so a caller need
not re-parse prose. So message text is no longer load-bearing for that routing, and the
reader's own operator-facing text is byte-identical anyway. That is a strengthening of the
reason, not a retreat from it: the whole point of putting ``code``/``msg`` on the exception
was that nobody downstream should have to grep for them, and until this change the library's
own oldest surface still did.
"""

# THE MOVING ISSUE FOR THE SUPERSEDED PARAGRAPH ABOVE IS **LD-531** (2026-08-20), and this is
# a `#` comment rather than a line of that paragraph for a load-bearing reason: this module is
# enrolled BY NAME in the consumer-reaching corpus — the suite (in the source repository) seeds BOTH
# `larkdocio.errors` (the import path the guide names, now a transparent re-export) and
# `larkdocio.common.errors` (this file, which the docstring above ships from), because a
# consumer runs `help()` on the taxonomy it catches — and the dialect guard there forbids an
# issue id in that text, since an id resolves to nothing for somebody holding only the wheel.
# The two files are `tests/consumer_text.py` and `tests/test_consumer_dialect_guard.py` (in the
# source repository); the second seed was added by LD-648 in the same change that moved this file here,
# so relocating the taxonomy could not quietly take its own docstring out of the guard's reach.
# So the attribution lives here, at the site,
# where a maintainer reading the paragraph finds it and a consumer never does. Moving it up into
# the docstring reddens that guard; the paragraph it attributes is the message-preservation one,
# whose old conclusion is quoted verbatim inside it.

#: The one authored lookup, re-exported here so ``larkdocio.errors`` — the module a caller
#: reaches for when something failed — is also where they can ask what a Lark code MEANS.
#: A re-export, never a second table: these are the same objects
#: :mod:`larkdocio.common.error_codes` defines. Safe as a module-level import where
#: ``permissions`` (below, in :func:`api_error`) is not: the lookup is a leaf over the standard
#: library and the citation formatter, while ``permissions`` reaches back into this module.
#: Since this module was relocated into the shared core it is also an INTRA-TIER import — the
#: taxonomy and the lookup are now siblings, so the edge no longer leaves ``common/`` and
#: cannot pair with the four core modules that import the taxonomy back.
from larkdocio.common.error_codes import ERROR_CODES, ErrorCodeNote, note_for  # noqa: F401

# Lark's rate-limit / frequency-control error code. Kept as a string so the
# comparison is representation-agnostic (the SDK may hand back an int or a str).
#
# What the code MEANS, and the measurement behind it — the write spike's 12-read burst at
# 8.8 req/s drew three of these — are authored once, for every surface, in the lookup imported
# above. That import is what ended the state this module's own docstring used to describe: a
# package error module centralizing exactly ONE Lark code out of the forty-odd the library
# names. What stays here is the constant the transport compares against, because a code is
# worth centralizing and a comparison is not.
RATE_LIMIT_CODE = "99991400"


class LarkDocIOError(Exception):
    """Base class for every error larkdocio raises.

    ``except LarkDocIOError`` catches the whole toolkit's typed failures.

    **That is a measured claim, not a stated intention.** A guard walks the whole package and
    reddens on any exception class defined under ``larkdocio`` that is not a subclass of this
    one, unless it is allow-listed with a written reason — and reddens again if an allow-list
    entry stops being needed, so the list cannot become a rubber stamp. The promise was false
    for six shipped refusal families before that guard existed, which is why it exists: each
    had been minted against ``ValueError`` for local ergonomics, and nothing checked the class
    graph as a whole. A refusal that carries both meanings subclasses ``ValueError`` **as well
    as** this base, never instead of it.
    """


class LarkConfigError(LarkDocIOError):
    """A configuration / credential / unsupported-input problem.

    Raised for local, pre-API failures — missing credentials, or a document type
    the reader no longer supports — where there is no Lark ``code``/``msg`` to
    carry.
    """


class LarkEscapeError(LarkConfigError):
    """Escaped Markdown could not be turned back into the literal text it was made from.

    Raised by :func:`larkdocio.model.unescape_literals`, the exact inverse of the
    reader's escape-literals output policy. Under that policy a backslash always
    introduces exactly one escapable character, so decoding is unambiguous — but a
    backslash that introduces anything else, or one that ends the text, cannot have
    come from the escaper. There are then two readings (a literal backslash the
    escaper would have doubled, or a truncated sequence) and no way to tell which was
    meant, so the decode **refuses instead of guessing**.

    A :class:`LarkConfigError` subclass — it is a local, pre-API unsupported-input
    problem, so an existing ``except LarkConfigError`` still catches it. ``detail``
    is mandatory and names the offending position and character, because a refusal a
    caller cannot act on is not worth raising.
    """

    def __init__(self, detail):
        super().__init__(detail)
        #: What could not be decoded and where — the actionable half of the refusal.
        self.detail = detail


class MissingDestinationError(LarkConfigError, ValueError):
    """A create-class call named no destination, so nothing was sent.

    The caller-supplied-destination rule: a new document, spreadsheet, Base, folder or uploaded
    file is created **only where the caller says**. With no destination Lark files the object in
    the application identity's own space — which no human interface can browse, whose trash
    cannot be listed, and where ``delete`` is a trash rather than a purge — so the object is
    effectively unrecoverable. The library refuses rather than picking a place.

    A :class:`LarkConfigError` **and** a :class:`ValueError`: it is a local, pre-API refusal
    (there is no Lark ``code``/``msg`` to carry) and it is also a bad argument, which is the
    same dual meaning :class:`larkdocio.base.schema_client.BaseSchemaRefusal` carries. Raised by
    :func:`larkdocio.common.destination.require_destination`, which holds the rule's one
    statement of itself.
    """


class FencedPrimitiveError(LarkConfigError, AttributeError):
    """A name that is no longer part of the public surface was called, so nothing was sent.

    Raised when a caller reaches a **fenced** name: one the library keeps answering — as a
    permanent signpost — while refusing to perform what it used to perform, because the
    operation behind it bypassed the guarantees the library sells. **Nothing reaches Lark**:
    the refusal is local and pre-API, which is the class :class:`LarkConfigError` names.

    A :class:`LarkConfigError` **and** an :class:`AttributeError` — the same dual meaning
    :class:`MissingDestinationError` carries against ``ValueError``, and for the same kind of
    reason. An existing ``except LarkDocIOError`` (or ``except LarkConfigError``) catches it,
    **and** so does the ``except AttributeError`` a defensive caller would already have written
    around a name they were not sure of, because "this name is not part of the surface" is what
    ``AttributeError`` means in Python's own vocabulary. A bump therefore fails at **call**
    time, typed, in a shape a consumer's existing handler already recognises — never at import,
    and never silently.

    **Every message names the supported route**, not merely the fact of the fence: a refusal a
    caller cannot act on is not worth raising, and one that says only "deprecated" recreates
    the very disclosure defect a fence exists to close. The first fenced name is
    ``WriteClient.patch_block``, whose message is authored once as
    :data:`larkdocio.write.client.PATCH_BLOCK_FENCE`.
    """


class LarkSnapshotIntegrityError(LarkConfigError):
    """A persisted read (:mod:`larkdocio.snapshot`) could not be trusted, so it was refused.

    Raised by :func:`larkdocio.snapshot.load` on a checksum mismatch, a truncated or otherwise
    unreadable file, an unrecognized format version, or malformed content. Every message names
    what failed **and** names the fix — **re-download the document** — because a refusal a
    caller cannot act on is not worth raising; and the refusal is
    exactly-one-or-refuse: no repair, no salvage, no best-effort load, and never a
    partially-rehydrated tree.

    A :class:`LarkConfigError` subclass — it is a local, pre-API unsupported-input problem, so
    an existing ``except LarkConfigError`` still catches it.

    ``reason`` is the machine-readable half, one of ``"checksum_mismatch"``, ``"unreadable"``,
    ``"unknown_format_version"`` or ``"malformed"``, for a caller who wants to branch on which
    of them happened; ``source`` is the path it came from, or ``None`` when the artefact was
    handed over as bytes.

    **The checksum this reports on is for integrity only**: no security boundary exists between
    a local library and the caller, so what it detects is accidental corruption — a truncated
    write, a half-synced cloud folder, a corrupted disk, a hand-edited file — and nothing else.
    """

    def __init__(self, detail, *, reason, source=None):
        super().__init__(detail)
        #: What failed and what to do about it — the actionable half of the refusal.
        self.detail = detail
        #: Which failure mode this was, for a caller that branches on it.
        self.reason = reason
        #: The path the artefact came from, or ``None`` when it was passed as bytes.
        self.source = source


class LarkAPIError(LarkDocIOError):
    """A Lark API call failed. Carries Lark's ``code`` and ``msg``.

    ``str(err)`` is the caller-supplied ``message`` verbatim (so existing
    operator-facing text and substring-based error routing are preserved);
    ``err.code`` / ``err.msg`` expose the Lark error body for callers that want
    to branch on it programmatically.

    ``denial`` is on the BASE, not only on :class:`LarkPermissionError`, because a surface
    with its own typed family — a media upload, a folder create — must be able to keep saying
    *which leg failed* and still carry *why*. Those two facts are not in competition: the class
    answers the first, this attribute answers the second, and forcing a caller to choose was a
    measured defect on the media and file legs. It is ``None`` on every error whose ``code``
    did not classify as a scope denial, which is the ordinary case, and
    ``err.denial is not None`` is therefore the one check that means the same thing on every
    surface this library ships.
    """

    def __init__(self, message, *, code=None, msg=None, denial=None):
        super().__init__(message)
        self.code = code
        self.msg = msg
        #: The :class:`larkdocio.permissions.PermissionDenial` describing what is missing —
        #: ``None`` unless Lark's answer classified as a scope denial.
        self.denial = denial

    @property
    def is_rate_limit(self):
        """True when this error carries Lark's rate-limit code (``99991400``)."""
        return _is_rate_limit_code(self.code)


class LarkRateLimitError(LarkAPIError):
    """Lark rate-limit / frequency-control error (code ``99991400``).

    A subclass of :class:`LarkAPIError`, so a caller that only cares about "an API
    call failed" still catches it, while a caller that wants to back off can catch
    :class:`LarkRateLimitError` specifically.
    """


def _is_rate_limit_code(code):
    """Representation-agnostic check for Lark's rate-limit code."""
    return code is not None and str(code) == RATE_LIMIT_CODE


class LarkPermissionError(LarkAPIError):
    """Lark refused the call because the app does not hold a required **scope**.

    A :class:`LarkAPIError` subclass, so every existing ``except LarkAPIError`` keeps working
    and ``str(err)`` is unchanged — but a caller who wants to tell *"I could not look"* from
    *"I looked and it is not there"* can catch this specifically.

    That distinction is the reason the type exists. A scope denial that arrives wearing the
    costume of an ordinary failure is how a missing **field-level** grant once presented for
    five days as a data-range problem. ``denial`` carries the whole answer in one shape: the
    exact missing scope(s), Lark's verbatim ``code``/``msg``, the console link Lark supplied
    (when it supplied one — nothing is synthesized), which credential pair made the call, and
    the fallback that still works where there is one. See
    :class:`larkdocio.permissions.PermissionDenial`.

    ``denial`` is inherited from :class:`LarkAPIError` rather than declared here: a
    surface's own typed error can carry one too, so the attribute belongs to the family. What
    is special about THIS class is not that it has a denial — it is that it *is* one.
    """


class LarkSpreadsheetUnreadableError(LarkAPIError):
    """**Every** tab of a workbook read missed — the read produced nothing at all.

    The workbook walk (:meth:`larkdocio.sheets.client.SheetsReadClient.read_spreadsheet`) skips a
    per-tab miss **loudly** and keeps going, because one unreachable tab must never withhold
    the tabs that read. At 100 % skipped that reasoning inverts: handing back a cheerful empty
    workbook would let "I could not read any of it" pass for "it is empty", which is the
    quieter and worse of the two defects. So the all-skipped case **raises**, and the raise
    carries every disclosure (:attr:`skips`) so the caller loses no evidence by not getting a
    result object.

    A :class:`LarkAPIError` subclass — an existing ``except LarkAPIError`` still catches it —
    carrying the FIRST skip's ``code``/``msg`` so the usual attributes mean what they always
    did.
    """

    def __init__(self, message, *, code=None, msg=None, denial=None, skips=()):
        super().__init__(message, code=code, msg=msg, denial=denial)
        #: One :class:`larkdocio.sheets.walk.TabSkip` per tab, in sheet order.
        self.skips = tuple(skips)


class LarkPaginationError(LarkDocIOError):
    """A cursor-paged walk could not be run to exhaustion, so its result is **incomplete**.

    Raised when a server keeps saying *there is more* in a way the walk cannot follow: it
    hands back the cursor that was just used (which would replay the same page forever), or
    it keeps handing back fresh cursors past the walk's own page cap. Every page answered
    successfully — there is no Lark ``code`` to carry and nothing failed below Lark — so this
    is **not** a :class:`LarkAPIError`; what went wrong is the *shape* of the answers.

    It exists because the alternative is worse than an error. A walk that gives up quietly
    returns a **short list that looks like a whole one**, and a caller deriving write targets
    from that list writes to the wrong place, or to a subset, and never learns it. So the walk
    refuses instead, naming what it saw: the endpoint, how many pages it followed and how many
    items it had collected when it stopped.

    :attr:`pages` and :attr:`items` carry those two counts, so a caller (or an apply-log
    detail) can state the size of the truncation rather than describe it.
    """

    def __init__(self, message, *, pages=None, items=None):
        super().__init__(message)
        #: How many pages the walk followed before it refused.
        self.pages = pages
        #: How many items it had collected at that point.
        self.items = items


#: The ONE spelling of the partial-application opt-in, on every plan-gated apply this library
#: ships (docx, sheets, Base records, Base schema). Named once so a message, a doc and a
#: signature cannot drift into per-surface vocabulary — the per-surface inconsistency round 4
#: punished elsewhere.
ALLOW_PARTIAL = "allow_partial"


class LarkApplyRefusedError(LarkDocIOError):
    """A plan-gated ``apply()`` ended with **refused entries** and no opt-in to partial application.

    **Why it raises.** ``apply()`` used to record typed refusals in its log and return
    normally, so a caller who did not read the log got **silent partial application** — some
    entries landed, some did not, and the process exited 0. Edits that looked like they had
    "vanished" were never a library defect, they were ``ambiguous-N-candidates`` refusals recorded faithfully in the log with
    every candidate id named, and **the caller discarded the log**. The default is now an
    error; partial application is opt-in (``allow_partial=True``).

    **Nothing about the writes changes.** The same entries apply and the same entries refuse,
    in the same order, issuing the same calls — only return-vs-raise moves. So the entries that
    DID land are still landed when this is raised: it is a report, never a rollback (this
    library never rolls back — see :attr:`applied`).

    Everything the returned log carried travels on the error:

    * :attr:`log` — the **whole** log object, exactly what ``apply(..., allow_partial=True)``
      would have returned;
    * :attr:`applied` — the entries that landed;
    * :attr:`refused` — the entries that did not;
    * :attr:`refusals` — the machine-readable projection: one ``{"reason", "detail"}`` per
      refused entry, in log order, so a caller can branch without knowing each surface's own
      refusal class.
    """

    def __init__(self, message, *, log, applied=(), refused=()):
        super().__init__(message)
        #: The full apply-log — what the call would have returned under the opt-in.
        self.log = log
        #: The entries that LANDED. They stand: this raise rolls nothing back.
        self.applied = tuple(applied)
        #: The entries that did not land.
        self.refused = tuple(refused)

    @property
    def refusals(self):
        """One ``{"reason", "detail"}`` dict per refused entry, in log order.

        The reason is normalized to its **wire string** (a docx refusal reason is an ``Enum``,
        the sheets and Base vocabularies are plain strings), so a consumer's branch reads the
        same on every surface.
        """
        return tuple(_refusal_projection(entry) for entry in self.refused)


def _refusal_reason(entry):
    refusal = getattr(entry, "refusal", None)
    reason = getattr(refusal, "reason", None)
    # A docx reason is a `RefusalReason` Enum whose `.value` is the wire string; the sheets and
    # Base vocabularies are already those strings. Normalize without importing either.
    return getattr(reason, "value", reason)


def _refusal_projection(entry):
    refusal = getattr(entry, "refusal", None)
    return {"reason": _refusal_reason(entry), "detail": getattr(refusal, "detail", None)}


def _refusal_summary(entries):
    """``"not-found ×2, stale-anchor ×1"`` — first-appearance order, never sorted."""
    counts = {}
    for entry in entries:
        reason = _refusal_reason(entry) or "unstated"
        counts[reason] = counts.get(reason, 0) + 1
    return ", ".join(f"{reason} ×{n}" for reason, n in counts.items())


def gate_refusals(log, *, allow_partial, surface):
    """Return ``log``, or raise :class:`LarkApplyRefusedError` when it carries refusals.

    **The one seam the ruling is enforced through.** Every plan-gated apply this library ships
    ends in this call, so the policy, the message and the opt-in spelling
    (:data:`ALLOW_PARTIAL`) are authored once rather than four times. ``log`` is duck-typed on
    the two accessors every apply-log has — ``applied`` and ``refusals`` — so this module stays
    a leaf and imports no engine.

    ``surface`` is the qualified callable a consumer typed (``"larkdocio.write.apply.apply"``),
    named in the message because a batch that spans engines must say which one refused.
    """
    refused = tuple(log.refusals)
    if allow_partial or not refused:
        return log
    applied = tuple(log.applied)
    total = len(applied) + len(refused)
    raise LarkApplyRefusedError(
        f"{surface}(): {len(applied)} of {total} entries applied; {len(refused)} refused "
        f"({_refusal_summary(refused)}). The applied entries STAND — nothing was retried and "
        f"nothing was rolled back. Read err.refusals for each refusal's reason and detail, "
        f"err.applied for what landed, err.log for the whole record. To accept partial "
        f"application, pass {ALLOW_PARTIAL}=True.",
        log=log, applied=applied, refused=refused,
    )


def api_error(message, *, code=None, msg=None, body=None, credential_env=()):
    """Build the right API-error type for a Lark ``code``.

    Returns a :class:`LarkRateLimitError` for Lark's rate-limit code
    (:data:`RATE_LIMIT_CODE`), a :class:`LarkPermissionError` when the answer is a **scope
    denial**, and otherwise a plain :class:`LarkAPIError`. All three carry ``code``/``msg`` and
    keep ``message`` as their verbatim ``str()``.

    ``body`` is the full response when the caller has one. It is optional because the two
    transports differ — the raw-HTTP surfaces hold the parsed body while the SDK path holds
    only ``code``/``msg`` — and a denial classifies either way: Lark names the scope in the
    message text as well as in the structured ``permission_violations``. What the body adds is
    the **console deep link**, which is never invented when it is absent.

    ``credential_env`` is the env-var NAMES of the pair the call was made on. A caller holding
    a read app and a write app needs to know WHICH one to fix, and only the call site knows —
    so every call site passes it, and a guard over the registry's own denial-owning modules
    keeps it that way. It defaults to empty rather than to a guess: attributing a denial to the
    wrong credential pair would send someone to edit the wrong variable.

    **The CLASSIFICATION seam — one of two doors, and this is the one that also picks the
    class.** Every surface's non-zero Lark code is classified in this module, so a denial
    cannot be reported one way on the reader and another way on a write engine. A surface with
    no typed family of its own comes through here and takes the class this returns; a surface
    that must keep its own family — a media upload, a folder create — comes through
    :func:`api_error_as` instead, which classifies identically and only lets the CLASS come
    from the call site.

    The sentence used to say *"every non-zero code reaches a caller through here"*, full stop,
    and it was measured false at 15 sites across four modules — each one raising a
    ``LarkAPIError`` subclass with ``code=`` in hand, so a scope denial on the media and file
    legs arrived with no ``PermissionDenial``, no console link and no credential attribution.
    The sentence is narrowed to what is now true and enforced: **classification** has one home,
    not the class. Both doors are held there by
    :func:`larkdocio.permissions.nonconforming_denial_sites`, which walks the class graph and
    names any site that builds a Lark-code error outside them.

    **And a WRAPPER carries the record rather than re-deriving it.** A builder that re-raises an
    error someone else classified — the create-then-rename composite's partial outcome, the
    docx engine's block-naming re-raise — forwards ``denial`` alongside ``code``/``msg``, so
    ``err.denial is not None`` answers the same on a wrapped error as on the one it wraps.
    Without that, the promise would have been false on exactly one shipped path, which is how
    it was found.

    **Where the guard does not look is written down, not left implicit.** Its module set is
    derived from the registry, so a module owning no registry-projected call site is outside
    it; those modules are enumerated with a per-module reason in
    :data:`larkdocio.permissions.CLEARED_OUTSIDE_THE_GUARDS_REACH` and held by
    :func:`larkdocio.permissions.constructions_outside_the_guards_reach`, which reddens when a
    new one appears. The narrowing is labelled, never silent.
    """
    if _is_rate_limit_code(code):
        return LarkRateLimitError(message, code=code, msg=msg)
    denial = _denial_for(code, msg, body=body, credential_env=credential_env)
    if denial is not None:
        return LarkPermissionError(message, code=code, msg=msg, denial=denial)
    return LarkAPIError(message, code=code, msg=msg)


def _denial_for(code, msg, *, body, credential_env):
    """The scope-denial record for a Lark answer, or ``None``. Both doors classify here.

    Imported lazily: ``permissions`` is a leaf module, but this one is imported by nearly
    everything, so a module-level import would tighten the load order for no benefit.
    """
    from larkdocio.permissions import denial_from

    return denial_from(code, msg, body=body, credential_env=credential_env)


def api_error_as(error_class, message, *, code=None, msg=None, body=None,
                 credential_env=(), denial=None, **attributes):
    """Build ``error_class`` for a Lark ``code``, carrying the denial :func:`api_error` would.

    **The second door — classify, then wrap in the caller's own class.** Some surfaces raise a
    typed family of their own because the family answers a question the base class cannot:
    ``MediaUploadError`` says *the attachment leg failed, the record was never judged*,
    ``DriveFileChunkedUploadError`` carries the ``upload_id`` of a transaction no listing shows
    and no delete removes. Routing those through :func:`api_error` would answer *why* by
    discarding *what*, and losing a resumption handle to gain a classification is not a trade
    this library makes. So the class stays the caller's and the classification is shared.

    **What this does NOT do is change the class.** A rate-limit code still comes back as
    ``error_class`` here, where :func:`api_error` would return :class:`LarkRateLimitError` — a
    surface that asked for its own type gets its own type, on every code. ``message`` is
    likewise passed through verbatim: this family adds attributes, it does not edit text. The
    only thing that moves is ``denial``, from ``None`` to a
    :class:`larkdocio.permissions.PermissionDenial` when Lark's answer was a scope denial.

    ``body`` is the full response when the caller has one — the SDK's response object counts,
    since its ``error.helps`` is where the console deep link lives. ``credential_env`` is the
    env-var names of the pair the call was made on, and is obliged at every call site by
    :func:`larkdocio.permissions.modules_not_supplying_credential_env` exactly as it is on
    :func:`api_error`. ``**attributes`` are forwarded to ``error_class`` untouched, which is
    how the leg-specific evidence survives.

    ``denial`` is the **re-wrap** case: an error classified once already, being re-raised with
    more context (how many blocks a chunked upload had sent before it stopped). Classifying it
    a second time would work from ``code``/``msg`` alone and silently drop the console link the
    original ``body`` supplied, so a record that exists is carried, not rebuilt. Passing
    ``None`` — the default — means *not yet classified*, and the answer is derived here.
    """
    if denial is None:
        denial = _denial_for(code, msg, body=body, credential_env=credential_env)
    return error_class(message, code=code, msg=msg, denial=denial, **attributes)


#: The module's public surface, and the contract the ``larkdocio.errors`` re-export is held
#: against in both directions (in the source repository, by
#: ``tests/test_common_tier_import_layering.py``).
#:
#: **DERIVED, never curated.** These are exactly the non-underscore names this module bound at
#: the top level before it was relocated here — measured off the pre-move module's ``dir()``,
#: which is what ``import *`` and ``help()`` answered from when there was no ``__all__`` at
#: all. Authoring the list was forced by the relocation rather than chosen: without it,
#: ``pydoc`` documents only members a module DEFINES, so ``help(larkdocio.errors)`` on a
#: re-export would have rendered an empty page and a consumer's documented reference to the
#: taxonomy would have gone blank. Omitting a name here would make it invisible to
#: ``import *`` and to ``help()``, so the list is held equal to the live public surface from
#: both sides rather than maintained by hand.
__all__ = [
    "ALLOW_PARTIAL",
    "ERROR_CODES",
    "ErrorCodeNote",
    "FencedPrimitiveError",
    "LarkAPIError",
    "LarkApplyRefusedError",
    "LarkConfigError",
    "LarkDocIOError",
    "LarkEscapeError",
    "LarkPaginationError",
    "LarkPermissionError",
    "LarkRateLimitError",
    "LarkSnapshotIntegrityError",
    "LarkSpreadsheetUnreadableError",
    "MissingDestinationError",
    "RATE_LIMIT_CODE",
    "api_error",
    "api_error_as",
    "gate_refusals",
    "note_for",
]
