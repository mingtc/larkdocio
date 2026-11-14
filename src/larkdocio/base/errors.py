"""larkdocio.base.errors — the Base error taxonomy, from the captured vocabulary (LD-247).

**Every code here was observed on the wire.** The Base study's three probe packs
between them refused this library in 23 distinct ways, and each one is written down with what a caller can actually *do* about it.
Nothing is invented: a code nobody has seen is not in the table, and a code in the table
that the table cannot explain would be a row with an empty ``meaning``, which the guard
rejects.

**Two entries carry a correction to an earlier reading, and they are the reason this module
is not just a dictionary:**

* ``1254301`` is a **FEATURE GATE, not a scope denial.** The Base's ``app.is_advanced`` is
  ``false``, and enabling advanced permissions is an action the **Base's owner** takes in
  the product. The API cannot do it either — ``PUT …/apps/{a} {"is_advanced": true}`` answers
  ``1254302 RolePermNotAllow``. So a message that pointed the reader at the scope console
  would point them at a place that cannot help them. It does not.
* ``99992402`` is **NOT opaque.** The P0 pack recorded it as *"error: null, no
  field_violations, no hint"*; the parity pack found that **every one of its 33 refusals**
  carried ``error.field_violations`` naming the offending field, the offending value **and
  the complete accepted enum**. :func:`field_violations` surfaces them and
  :func:`raise_for_base_code` puts them in the message, because discarding the one part of
  the body that says what would have worked is how a refusal becomes a mystery.

**The refusal shape is not re-invented here.** Every non-zero code on THIS module's path
leaves through :func:`larkdocio.errors.api_error` — so a genuine scope denial on a Base call
still arrives as a ``LarkPermissionError`` carrying its ``PermissionDenial``, and a rate limit
still arrives as a ``LarkRateLimitError``. The appositive this sentence used to carry, *"the
one seam the whole library refuses through"*, was measured false — 15 sites across four
modules built the error themselves — and the fix was not to route those legs here but to give
them a second door (:func:`larkdocio.errors.api_error_as`) that classifies identically and
keeps their own class, so ``larkdocio.base.media`` can still say *the attachment leg failed*.
Both doors are held by ``permissions.nonconforming_denial_sites()``.

**This module has a third shape, and it is a WRAPPER, not a door.**
:func:`table_created_view_not_named` re-raises a cause classified at the call seam, and it
forwards ``denial`` alongside ``code``/``msg`` rather than re-deriving them — so on
``create_table(..., default_view_name=...)``, where the CREATE lands and the rename is refused
for a missing grant, the partial outcome carries the scope, the console link and the credential
pair. Until it did, that was the one shipped path on which ``err.denial is not None`` answered
differently from every other surface. A wrapper that keeps a code and drops the classification
hands a caller a permissions problem wearing the costume of an ordinary one, which is the exact
failure this family exists to prevent. This module is outside the guard's derived module set
and is recorded as a cleared exception in
:data:`larkdocio.permissions.CLEARED_OUTSIDE_THE_GUARDS_REACH`. What this
module adds is the *actionable half* of the message.

**AND THE ROWS THEMSELVES NOW LIVE ONE LEVEL UP — LD-531 (2026-08-20). The reason above is
unchanged; only where the text is stored moved.** Everything this docstring claims still
holds — every code here was observed on the wire, nothing is invented, the two corrections
(``1254301`` is a feature gate, ``99992402`` is not opaque) are still recorded and still
enforced — but the ``code → (label, meaning, evidence)`` rows are authored in
:data:`larkdocio.common.error_codes.ERROR_CODES`, for every surface at once, and this module
selects the Base ones by code (:data:`BASE_TAXONOMY_CODES`). The reason for lifting them: the
shape LD-247 invented here was the best one in the repo, and four other surfaces were
explaining their own codes in their own separate branch tables, so a code that arrived twice
got explained twice. The reason for **not** lifting the classification with it: this surface's
reading of a code is its own — :func:`note_for` below still answers only about the Base
vocabulary, and :mod:`larkdocio.base.disposition`'s halt/continue split is D4′ and stays
exactly where it is.
"""
from typing import Optional, Tuple

from larkdocio.common.error_codes import ErrorCodeNote, notes_for
from larkdocio.errors import LarkAPIError, api_error

#: The row type, kept spelled the Base surface's own way. **LD-531 made it an alias rather than
#: a second dataclass**: the shape LD-247 authored here — ``code``/``label``/``meaning``/
#: ``evidence``, and the rule that a meaning which merely spells the label out has told the
#: caller nothing — is exactly the shape the package-level registry now carries for every
#: surface, so a second definition of it would be a second definition of the same idea. The
#: package row adds two fields the Base vocabulary never needed and does not use
#: (``verification``, ``denial_class``), both defaulted, so every existing construction and
#: every attribute read is unchanged. The name stays because it is public and because a Base
#: reader looking for the Base row should find it here.
BaseErrorNote = ErrorCodeNote


#: **The Base surface's own view of the one shared vocabulary** — code → note, in the family
#: order it has always read in. The rows themselves were relocated to
#: :data:`larkdocio.common.error_codes.ERROR_CODES` by **LD-531** so that a code's meaning and
#: evidence are authored ONCE for the whole library; what stays here is *which* codes the Base
#: surface explains, which is this surface's own question and nobody else's. Byte-identical to
#: what it held before: same 25 keys, same order, same note objects.
#:
#: :func:`larkdocio.common.error_codes.notes_for` refuses a code with no authored row at import
#: time, so a Base code this library cannot explain cannot ship.
BASE_TAXONOMY_CODES: Tuple[int, ...] = (
    # ---- the app itself ----
    1002, 91402, 1061003, 1254036,
    # ---- tables, records, views ----
    1254004, 1254041, 1254043, 1254023, 1254034, 1254001,
    # ---- the search parameters, and the vocabulary asymmetry ----
    1254016, 1254018, 1254044, 1254045, 99992402, 1254060, 1254069, 1255002,
    # ---- the feature gate: NOT a scope denial ----
    1254301, 1254302,
    # ---- neighbouring families a Base read can touch ----
    1254050, 800074800, 1069307, 1770001, 1770029,
)

BASE_ERROR_CODES = notes_for(BASE_TAXONOMY_CODES)

#: The codes that are a **product feature gate**, not a permission problem. Kept as data so
#: the distinction is checkable rather than a matter of message wording.
FEATURE_GATE_CODES = (1254301, 1254302)

#: **The WRITE vocabulary** — the subset of the taxonomy a record write can actually meet,
#: named as data so "which refusals does a writer have to be able to explain?" is a query
#: rather than a reading of the table. One taxonomy, two views: the codes here are the same
#: rows the read path uses, because a wrong table id refuses identically whichever verb asked.
#:
#: Three of them carry a correction that only matters on the write path. ``99992402`` is **not
#: opaque** — it names the offending field, the value sent and the complete accepted enum, all
#: of which reach the caller. ``1254301`` / ``1254302`` are a **product feature gate, not a
#: scope denial**, so their messages must not send anybody to a permission console. And
#: ``1255002`` was observed for a well-formed request carrying a semantically impossible value
#: — a Location written with its coordinates reversed — so it is a *re-check the value* answer
#: rather than a *retry* one.
WRITE_ERROR_CODES = (
    1002,      # the Base itself has been trashed
    91402,     # no Base at this app_token
    1254004,   # malformed table id
    1254041,   # no such table in this Base
    1254043,   # no such record in this table
    1254069,   # attachment conversion failed — the upload is a separate call
    1254060,   # text-shaped conversion failed — the read shape is not the write shape
    1254001,   # wrong request body, and the server names the offending path
    99992402,  # field validation failed, with the accepted enum in the body
    1255002,   # internal error — observed for a semantically impossible value
    1254301,   # feature gate, not a scope denial
    1254302,   # the other half of the feature gate
    1254036,   # the Base is still being copied — the one asynchronous operation
)


def _get(obj, key):
    """Read ``key`` off a dict payload or an SDK-style object — the two transports differ."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def _code_of(body):
    return _get(body, "code")


def _msg_of(body):
    return _get(body, "msg")


def field_violations(body) -> Tuple[dict, ...]:
    """The ``error.field_violations`` a ``99992402`` body carries, as plain dicts.

    Empty for a body that has none — an absent violation list is not an error, it is simply
    a refusal of a different kind.
    """
    error = _get(body, "error")
    raw = _get(error, "field_violations") or ()
    out = []
    for violation in raw:
        if isinstance(violation, dict):
            out.append(dict(violation))
        else:
            out.append({
                "field": _get(violation, "field"),
                "value": _get(violation, "value"),
                "description": _get(violation, "description"),
            })
    return tuple(out)


def server_detail(body) -> Optional[str]:
    """The precise ``error.message`` a body carries, or ``None``.

    The body-shape refusal is the reason this exists: it does not merely say *"the request body
    is wrong"* — it names the exact offending path and states the correct form. Discarding that
    turns an answerable refusal into a guess, so it is quoted into the message verbatim.
    """
    error = _get(body, "error")
    message = _get(error, "message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return None


def note_for(code) -> Optional[BaseErrorNote]:
    """The taxonomy row for a Lark code, or ``None`` for one nobody has captured."""
    try:
        return BASE_ERROR_CODES.get(int(str(code)))
    except (TypeError, ValueError):
        return None


def _violation_sentence(violations) -> str:
    parts = []
    for violation in violations:
        field = violation.get("field")
        value = violation.get("value")
        description = violation.get("description")
        clause = f"{field}={value!r}" if value is not None else str(field)
        if description:
            clause += f" ({description})"
        parts.append(clause)
    return "Lark named the offending field(s): " + "; ".join(parts) + "."


def raise_for_base_code(response, *, context: str, credential_env=()):
    """Return ``response`` on ``code:0``; otherwise raise this library's typed error.

    The message is ``"<context> failed: Code: …, Msg: …"`` — the shape every other surface
    uses — followed by the taxonomy's actionable sentence and, for a ``99992402``, the
    field violations verbatim. A code the taxonomy does not know still raises **typed**,
    carrying Lark's own answer; it just cannot add advice it does not have.
    """
    code = _code_of(response)
    if code in (0, None) or str(code) == "0":
        return response

    msg = _msg_of(response)
    parts = [f"{context} failed: Code: {code}, Msg: {msg}"]
    note = note_for(code)
    if note is not None:
        parts.append(note.meaning)
    detail = server_detail(response)
    if detail:
        parts.append(f"Lark's own detail: {detail}")
    violations = field_violations(response)
    if violations:
        parts.append(_violation_sentence(violations))

    error = api_error(" ".join(parts), code=code, msg=msg, body=response,
                      credential_env=credential_env)
    # Carried on the exception so a caller can branch on the violations rather than parse
    # the message back apart. Set on every API error this module raises, so the attribute
    # always exists and is simply empty when there was nothing to carry.
    error.field_violations = violations
    raise error


# --------------------------------------------------------------------------- #
# LD-356 — the CREATE-THEN-RENAME composite's PARTIAL OUTCOME                    #
# --------------------------------------------------------------------------- #
#
# The one place in this library where a single public call makes two writes, so the one place
# that can end **half done**. The seat's ruling on that state is recorded in LD-356 and
# implemented here and in `schema_client.create_table`: SURFACE IT, TYPED — no auto-rollback, no
# retry loop. A destructive rollback to undo a COSMETIC failure is the wrong risk class: a delete
# can itself fail, can race, and can need a permission the create did not, while the worst
# outcome of the honest path is a table whose view carries Lark's own name.

#: The non-atomicity, stated once and quoted everywhere it is disclosed (the client seam's
#: docstring, the plan seam's, and the family's). Truthful rather than reassuring: naming the
#: non-atomicity is what a caller can act on.
COMPOSITE_IS_NOT_ATOMIC = (
    "Naming a new table's default view is a COMPOSITE of two calls and it is NOT ATOMIC: Lark's "
    "create route REJECTS `default_view_name` outright (1254001 WrongRequestBody, and no table "
    "is created — measured twice in probe `ld344-01`), so the name can only be applied by "
    "renaming the view the table is born with. If the create succeeds and the rename does not, "
    "the table EXISTS, carrying the view name Lark chose in the tenant's locale, and "
    "`TableCreatedViewNotNamed` is raised carrying the table_id, the view_id and Lark's own "
    "denial. Nothing is rolled back and nothing is retried: one `update_view(app_token, "
    "table_id, view_id, view_name=...)` finishes the job, and the ids that call needs are on "
    "the exception."
)

#: What to do when the create's echo named no view at all — the honest third state. No listing
#: is made on the caller's behalf, because a write client that quietly starts reading is a
#: client whose call budget nobody can predict.
VIEW_ID_NOT_LEARNED = (
    "the create's own response carried no `default_view_id`, so this library never learned "
    "which view to rename and did NOT guess. `list_views(app_token, table_id)` on the read "
    "client returns the table's single view; one `update_view(...)` with its id applies the "
    "name."
)


class TableCreatedViewNotNamed(LarkAPIError):
    """**The table WAS created; its default view was NOT renamed.** A typed partial outcome.

    Raised by :meth:`larkdocio.base.schema_client.BaseSchemaClient.create_table` when it was
    asked for a ``default_view_name`` and the second leg did not apply it. A
    :class:`~larkdocio.errors.LarkAPIError` subclass, so ``except LarkAPIError`` /
    ``except LarkDocIOError`` already catch it and ``code`` / ``msg`` are **Lark's own**,
    unedited — but a caller who wants to finish the rename catches *this* type and reads the
    ids off it:

    * :attr:`table_id` — the table that **exists** on the Base right now;
    * :attr:`view_id` — the view to rename, or ``None`` with :attr:`view_id_learned` ``False``
      when the create's echo never named it;
    * :attr:`requested_view_name` — the name that was asked for and did not land;
    * ``code`` / ``msg`` — Lark's denial verbatim, or ``None``/``None`` when there was no denial
      to reproduce (the echo case), because nothing is invented.

    **Nothing was deleted and nothing was retried.** Both are the ruling, not an accident of
    implementation, and both are asserted structurally by the project's own test suite.
    """

    def __init__(self, message, *, table_id=None, view_id=None, view_id_learned=False,
                 requested_view_name=None, code=None, msg=None, denial=None):
        super().__init__(message, code=code, msg=msg, denial=denial)
        self.table_id = table_id
        self.view_id = view_id
        self.view_id_learned = bool(view_id_learned)
        self.requested_view_name = requested_view_name

    def to_dict(self) -> dict:
        """The partial state as plain data — for a log, a retry script, or a test."""
        return {"table_id": self.table_id, "view_id": self.view_id,
                "view_id_learned": self.view_id_learned,
                "requested_view_name": self.requested_view_name,
                "code": self.code, "msg": self.msg}


def table_created_view_not_named(table_id, view_id, requested_view_name, *, cause=None):
    """Build the partial outcome, with **Lark's own words** when there are any.

    One constructor so the sentence a caller reads is written once: what happened, what exists,
    what did not, what was NOT done about it, and the exact call that finishes the job.
    """
    learned = bool(view_id)
    code = getattr(cause, "code", None)
    msg = getattr(cause, "msg", None)
    # The local used to be called `denial`, which is now the name of the CLASSIFICATION
    # attribute one line below; the two are different things and must not share a name. This
    # one is the sentence quoting Lark, and its bytes are unchanged.
    larks_words = (f"Lark's own answer, unedited: Code: {code}, Msg: {msg}."
                   if cause is not None else VIEW_ID_NOT_LEARNED)
    return TableCreatedViewNotNamed(
        f"the table was CREATED and its default view was NOT renamed. "
        f"table_id={table_id!r}, view_id={view_id!r}, requested name="
        f"{requested_view_name!r}. {larks_words} NOTHING was rolled back — this library never "
        f"deletes a table to undo a cosmetic failure — and NOTHING was retried. "
        f"{COMPOSITE_IS_NOT_ATOMIC}",
        table_id=table_id, view_id=view_id, view_id_learned=learned,
        requested_view_name=requested_view_name, code=code, msg=msg,
        # FORWARDED, not re-derived. `cause` was classified once already, at the seam that
        # made the call, and it holds the console link that lives only in a response body —
        # re-classifying from code/msg here would silently drop it. Without this line the
        # promise `err.denial is not None` is false on exactly one shipped path:
        # `create_table(..., default_view_name=...)`, where the CREATE succeeded and the
        # rename was refused for a missing scope.
        denial=getattr(cause, "denial", None))
