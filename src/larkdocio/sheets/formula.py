"""larkdocio.sheets.formula — the Sheets FORMULA cell: encoder, decoder, render-mode legs,
and the inert-``=``-string disclosure (LD-149 / dogfood round-2 **T23**).

**The bug this module closes.** Round 2 wrote ``ValueWriteRequest.for_a1(range,
[["=SUM(B3:B8)"]])``, applied it, and read back the **literal string** ``"=SUM(B3:B8)"``,
unevaluated — **silently**, not refused. A consumer could ship a "total" that is inert text
and never know. There was no formula write type and the word "formula" appeared nowhere in
``capabilities()`` / ``guide()``.

**What the LD-149 probe established (live, on a self-provisioned disposable created and
deleted in the same run — spreadsheet_token ``Exampled09268e885dd6d906728``, zero orphans;
the raw payloads are in the issue's Activity log).** The finding is **CONFIRMED**:

======================================= ============================================
write                                    read-back
======================================= ============================================
``{"type":"formula","text":"=SUM(B3:B8)"}``  ``Formula`` → ``"=SUM(B3:B8)"`` ·
(the documented object form, via the      ``UnformattedValue`` → ``21`` ·
values ``PUT``)                           ``FormattedValue`` → ``21`` ·
                                          ``ToString`` → ``"SUM(B3:B8)"`` (no ``=``)
``"=SUM(B3:B8)"`` (a plain string)        ``"=SUM(B3:B8)"`` under **all four** modes
======================================= ============================================

Three consequences the whole design turns on:

1. **The object form EVALUATES.** So a formula write is real, and it ships
   (:class:`~larkdocio.sheets.requests.FormulaWriteRequest`).
2. **A plain ``"=…"`` string can NEVER evaluate.** There is **no ``valueInputOption``** on
   this API: ``?valueInputOption=USER_ENTERED``, ``?valueInputOption=RAW`` and a body-level
   ``valueInputOption`` are each answered ``code 0 / "success"`` and have **zero effect**
   (probed all three ways). No flag exists to turn a string into a formula — hence
   :data:`INERT_STRING_NOTE`, the loud dry-run disclosure a ``=``-prefixed plain value gets.
3. **``Formula`` mode alone cannot tell them apart** — an inert ``=``-string reads back
   under ``Formula`` exactly like a real formula. The ONE discriminator is the
   **computed-value leg**: a cell evaluated iff its ``UnformattedValue`` read-back
   **differs** from its stored expression (:func:`formula_record`). Every verification in
   the engine keys on that, which is also why an **invalid** formula is caught: Lark
   **accepts** ``"=SUM("`` with ``code 0`` and stores it **inert**, so there is no API error
   to catch — only a read-back to compare.

**Why the precondition compares the EXPRESSION, not the computed value** (the maintainer-adopted
recommendation, AC3). The probe changed one operand (``B3`` ``1``→``100``) and the computed
value moved ``21``→``120`` while the expression stayed put. A computed value therefore drifts
**without anyone editing the cell**, so comparing it would manufacture spurious
``precondition-mismatch`` refusals on every batch that touches upstream data. The expression
is the author's intent, and it changes only when someone actually edits the formula.

Pure + offline — no network, no creds. The gated engine
(:mod:`larkdocio.sheets.ops`) is what writes these cells, through the same
``Plan`` → dry-run → apply gate every other family uses.
"""
from larkdocio.errors import LarkConfigError

#: The one-character marker that makes a string *look* like a formula.
EQUALS_PREFIX = "="

#: ``valueRenderOption`` for the **expression** leg — the precondition basis (AC3) and the
#: stored-expression half of the post-write verification. Reads back ``"=SUM(B3:B8)"``.
EXPRESSION_RENDER_OPTION = "Formula"
#: ``valueRenderOption`` for the **computed** leg — the raw evaluated value (``21``). The ONE
#: leg that can tell an evaluating formula from inert ``=``-text.
COMPUTED_RENDER_OPTION = "UnformattedValue"
#: ``valueRenderOption`` for the **display** leg — the formatted computed value. Recorded for
#: completeness (the probe found it agrees with the computed leg on a plain number).
DISPLAY_RENDER_OPTION = "FormattedValue"

#: Every render mode the probe characterized for a formula cell (the LD-100 four-mode matrix
#: discipline). ``ToString`` answers the expression with the leading ``=`` **stripped**.
FORMULA_RENDER_OPTIONS = (
    EXPRESSION_RENDER_OPTION,
    COMPUTED_RENDER_OPTION,
    DISPLAY_RENDER_OPTION,
    "ToString",
)

#: The spreadsheet error sentinels a *successfully parsed* formula can evaluate to. The probe
#: produced two of them live — ``"#NAME?"`` (``=NOTAFUNC(B3)``) and ``"#REF!"`` (a cross-tab
#: reference written by ``sheet_id`` instead of by title). A sentinel means the cell **IS** a
#: formula (Lark parsed it) whose evaluation failed — a different story from inert text, and
#: recorded as such.
ERROR_SENTINELS = frozenset({
    "#NAME?", "#REF!", "#VALUE!", "#DIV/0!", "#NULL!", "#NUM!", "#N/A", "#ERROR!",
})

#: **The loud dry-run note (AC5)** a ``=``-prefixed **plain string** value earns — the exact
#: text, so a consumer's approval UX (and the suite) can pin it verbatim. It states the
#: outcome, the proven cause (no ``valueInputOption`` exists), and the fix.
INERT_STRING_NOTE = (
    "LOUD WARNING: this value starts with '=' but is a PLAIN STRING, so it will be "
    "stored as INERT TEXT, not an evaluating formula. Lark's values API has NO "
    "valueInputOption / USER_ENTERED mode (probed 2026-07-28: the query- and body-level "
    "variants are both answered code 0 and have zero effect), so no flag can make a "
    "plain string evaluate. To write a formula that EVALUATES use "
    "FormulaWriteRequest.for_a1(range, \"=SUM(...)\"), which sends the documented "
    "{\"type\":\"formula\",\"text\":\"=...\"} object form. If you really do want the "
    "literal text, this is already what you get — nothing else changes."
)

#: What the plan's formula preview says about the computed read-back (AC2) — one string so
#: the plan, the log and the docs cannot drift.
COMPUTED_READ_BACK_NOTE = (
    f"after apply, this cell's computed value is read back with "
    f"valueRenderOption={COMPUTED_RENDER_OPTION} and recorded in the apply-log's `formula` "
    f"record (`computed_value` + `evaluated`). The expression itself is re-read with "
    f"valueRenderOption={EXPRESSION_RENDER_OPTION}. A computed value is NOT part of the "
    f"precondition: it drifts whenever the referenced data changes, so comparing it would "
    f"refuse writes nobody edited — the precondition compares the EXPRESSION."
)


class FormulaExpressionError(LarkConfigError):
    """The expression is not a writable formula — it does not start with ``=``, or it is
    not a non-empty string.

    Refused **at construction** (:meth:`~larkdocio.sheets.requests.FormulaWriteRequest.for_a1`),
    so a request that would silently store inert text cannot even be built. Under
    :class:`~larkdocio.errors.LarkConfigError` (an unsupported-input problem), so
    ``except LarkConfigError`` / ``except LarkDocIOError`` catch it — the sibling of
    :class:`~larkdocio.sheets.rich_encode.MultiSelectLabelError` /
    :class:`~larkdocio.sheets.rich_encode.DropdownColorsError`.
    """


class FormulaRenderOptionUnsupported(LarkConfigError):
    """The client seam cannot serve a render-mode read, so a formula write is impossible.

    A formula write **requires** ``read_values(..., value_render_option=…)``: the
    precondition reads the expression leg and the verification reads the computed leg. The
    shipped :class:`~larkdocio.sheets.write_client.SheetsWriteClient` provides it; a
    third-party duck-typed seam that does not gets this typed error, which the engine turns
    into an :data:`~larkdocio.sheets.plan.Refusal.INVALID_REQUEST` refusal (plan-time) rather
    than letting a ``TypeError`` escape the previewer.
    """


def normalize_expression(expression) -> str:
    """Validate ``expression`` as a writable formula and return it **verbatim**.

    A formula must be a non-empty ``str`` starting with ``=``. Anything else raises
    :class:`FormulaExpressionError` — including a leading-space ``" =SUM(...)"``, which Lark
    stores inert (the ``=`` is no longer the first character). Deliberately **no**
    auto-prefixing and **no** trimming: silently rewriting an expression is exactly the class
    of helpfulness that produced that bug.
    """
    if not isinstance(expression, str) or isinstance(expression, bool):
        raise FormulaExpressionError(
            f"a formula expression must be a str starting with '='; got "
            f"{type(expression).__name__} {expression!r}. Build it as text, e.g. "
            f"FormulaWriteRequest.for_a1(range, \"=SUM(B3:B8)\")."
        )
    if not expression.startswith(EQUALS_PREFIX):
        raise FormulaExpressionError(
            f"a formula expression must start with '='; got {expression!r}. Lark stores "
            f"anything else as INERT TEXT (probed live), so this is refused here rather "
            f"than discovered after the write. Write \"={expression.strip()}\" to mean the "
            f"formula, or use ValueWriteRequest if you really want the literal text."
        )
    if len(expression) == 1:
        raise FormulaExpressionError(
            "a formula expression must carry something after the '='; got \"=\"."
        )
    return expression


def encode_formula(expression: str) -> dict:
    """A formula cell — ``{"type":"formula","text":"=SUM(B3:B8)"}`` (the documented object
    form a live probe proved EVALUATES).

    The expression is validated (:func:`normalize_expression`) and placed on the wire
    **verbatim** — commas, quotes and nested calls untouched, so
    ``'=IF(SUM(B3:B8)>10,"big","small")'`` round-trips exactly (probe: → ``"big"``).
    """
    return {"type": "formula", "text": normalize_expression(expression)}


def formula_expression(cell):
    """The expression inside a formula **cell object**, or ``None``.

    The decoder half of :func:`encode_formula`, and deliberately its neighbour so the wire
    shape is defined once. Only a ``{"type": "formula", "text": <non-empty str>}`` mapping
    counts: a bare ``"=…"`` **string** is *not* a formula cell (that is exactly the
    trap — it is inert text), and neither is a list wrapping one.
    """
    if not isinstance(cell, dict) or cell.get("type") != "formula":
        return None
    text = cell.get("text")
    return text if isinstance(text, str) and text else None


def is_formula_cell(cell) -> bool:
    """True iff ``cell`` is the formula **object form** (see :func:`formula_expression`)."""
    return formula_expression(cell) is not None


def is_equals_prefixed(value) -> bool:
    """True iff ``value`` is a **plain string** whose first character is ``=`` — the T23
    shape that stores inert. A number, ``None``, a bool, or a structured cell is never it."""
    return isinstance(value, str) and value.startswith(EQUALS_PREFIX)


def equals_prefixed_cells(matrix) -> list:
    """Every ``=``-prefixed plain-string cell in ``matrix``, as
    ``[{"row", "col", "value"}, …]`` in row-major order (``[]`` when there are none).

    Row-major coordinates (not A1) because the matrix is the *proposed* payload — its
    position within the target range is what a reviewer needs, and it stays correct for a
    range of any shape. A row that is not a list is treated as a single-cell row, matching
    how the rest of the engine reads a values matrix.
    """
    hits: list = []
    for r, row in enumerate(matrix or []):
        cells = row if isinstance(row, list) else [row]
        for c, cell in enumerate(cells):
            if is_equals_prefixed(cell):
                hits.append({"row": r, "col": c, "value": cell})
    return hits


def equals_prefixed_note(matrix):
    """The **loud** dry-run preview note for a ``=``-prefixed plain-string payload, or
    ``None`` when the payload has none (AC5).

    ``{"kind": "equals-prefixed-plain-string", "cells": [...], "note": INERT_STRING_NOTE}``
    — stamped onto the plan entry by the previewer's single dispatch seam, so **every**
    values-bearing request family gets it and a future family cannot forget.
    """
    hits = equals_prefixed_cells(matrix)
    if not hits:
        return None
    return {
        "kind": "equals-prefixed-plain-string",
        "cells": hits,
        "note": INERT_STRING_NOTE,
    }


#: The note kind a write that will **destroy a live formula** carries (LD-150 / dogfood **F9**).
OVERWRITES_LIVE_FORMULA_KIND = "overwrites-live-formula"


def live_formula_cells(expression_values, computed_values, ref=None) -> list:
    """Every cell that currently holds a **live** (evaluating) formula, as
    ``[{"ref", "row", "col", "expression", "computed_value"}, …]`` (LD-150 / dogfood **F9**).

    ``expression_values`` is the target's ``Formula``-mode read and ``computed_values`` its
    ``UnformattedValue`` read (the precondition read the previewer already made). A cell is a
    live formula iff its expression leg is a ``=``-prefixed string **and** its computed leg
    **differs** from it — the same single discriminator :func:`formula_record` verifies a write
    with, and the only one Lark offers: an **inert** ``=``-string reads back identically under
    both legs (which is why it is deliberately NOT reported here — destroying inert text loses
    nothing computed, and crying wolf over it would teach a consumer to ignore the note).

    ``ref`` is an optional ``(row, col) -> str`` for the A1 label of a 0-based offset inside the
    target; row-major order throughout, as everywhere else in the engine.
    """
    hits: list = []
    for r, row in enumerate(expression_values or []):
        cells = row if isinstance(row, list) else [row]
        for c, expression in enumerate(cells):
            if not is_equals_prefixed(expression):
                continue
            computed = _cell_at(computed_values, r, c)
            if computed == expression:
                continue                      # identical under both legs ⇒ INERT text
            hits.append({
                "ref": ref(r, c) if ref is not None else None,
                "row": r, "col": c,
                "expression": expression,
                "computed_value": computed,
            })
    return hits


def _cell_at(matrix, r, c):
    """``matrix[r][c]`` or ``None`` — tolerant of a short/ragged read-back (the two render legs
    are separate API answers and need not agree in shape)."""
    rows = matrix or []
    if r >= len(rows):
        return None
    row = rows[r]
    cells = row if isinstance(row, list) else [row]
    return cells[c] if c < len(cells) else None


def overwrites_live_formula_note(cells, *, a1_range):
    """The preview note for a write/clear whose target holds one or more **live formulas** —
    or ``None`` when it holds none (LD-150 / dogfood **F9**).

    **The hole this closes.** The dry-run warned *loudly* about a value that merely **looks**
    like a formula (:data:`INERT_STRING_NOTE`) and said **nothing** about destroying a real one:
    clearing a column previewed ``before: [[11],[22],[33],[44],[110]]``, where ``110`` was a
    live ``=SUM(A1:A4)`` and reads exactly like data. The precondition read is
    ``UnformattedValue``, under which a formula answers its computed scalar — so the *before*
    can never show it. One extra ``Formula``-mode read can, and does.

    The precedent is :meth:`~larkdocio.sheets.requests.MergeCells.loss_preview`: **a destructive
    sheets write pays for a read**, and the preview ENUMERATES what it will destroy (the D6/D7
    delight this completes) rather than summarizing it.
    """
    if not cells:
        return None
    listing = ", ".join(
        f"{c['ref'] or f'''row {c['row']} col {c['col']}'''} ({c['expression']} → "
        f"{c['computed_value']!r})"
        for c in cells
    )
    return {
        "kind": OVERWRITES_LIVE_FORMULA_KIND,
        "a1_range": a1_range,
        "cells": cells,
        "count": len(cells),
        "note": (
            f"DESTRUCTIVE: {len(cells)} cell(s) in {a1_range} currently hold a LIVE FORMULA, and "
            f"this write will replace them with static content — each formula is DESTROYED, not "
            f"recalculated: {listing}. The plan's `before` shows each cell's COMPUTED value "
            f"(the precondition read is valueRenderOption={COMPUTED_RENDER_OPTION}, under which "
            f"a formula answers its result), so a computed number there is indistinguishable "
            f"from data without this note. If you meant to rewrite the formula, use "
            f"FormulaWriteRequest.for_a1(range, \"=…\"), which owns the expression precondition "
            f"and the computed read-back; if you meant to replace it with a static value, this "
            f"is correct — the expressions above are what you are discarding. (An INERT "
            f"'='-string is deliberately NOT reported here: it computes nothing, so nothing "
            f"computed is lost.)"
        ),
    }


def formula_preview_note(expression: str, *, current_expression, current_computed_value) -> dict:
    """The plan's **formula** preview disclosure: the expression that will be written, what
    the target holds now under **both** legs, and what the precondition compares (AC2/AC3).

    ``current_expression`` is the ``Formula``-mode read (the precondition basis, and the
    plan entry's ``before``); ``current_computed_value`` is the ``UnformattedValue`` read —
    carried for the reviewer's eyes only, deliberately **not** compared.
    """
    return {
        "kind": "formula",
        "expression": expression,
        "current_expression": current_expression,
        "current_computed_value": current_computed_value,
        "precondition_compares": "expression",
        "expression_render_option": EXPRESSION_RENDER_OPTION,
        "computed_render_option": COMPUTED_RENDER_OPTION,
        "read_back_note": COMPUTED_READ_BACK_NOTE,
    }


def _first_cell(matrix):
    """The top-left cell of a values matrix, or ``None`` — a formula write is one cell (D2),
    so the record reports scalars rather than making a reader unwrap a 1×1 twice."""
    for row in matrix or []:
        cells = row if isinstance(row, list) else [row]
        for cell in cells:
            return cell
    return None


def formula_record(*, expression: str, stored_expression, computed_value) -> dict:
    """The apply-log's **formula** record — did the write actually become a formula?

    * ``expression`` — what was sent;
    * ``stored_expression`` — the ``Formula``-mode read-back. Lark may **normalize** it (the
      probe's cross-tab case: ``=SUM(Other!A1:A2)`` came back ``=SUM('Other'!A1:A2)``), which
      is recorded as ``normalized`` rather than treated as a failure;
    * ``computed_value`` — the ``UnformattedValue`` read-back;
    * ``evaluated`` — **the discriminator**: ``True`` iff ``computed_value`` differs from
      ``stored_expression``. That is the only signal Lark gives, because an unparsable
      expression is **accepted** (``code 0``) and stored as inert text whose every render
      mode answers the same string. A falsy computed value (``0`` from ``=SUM(Z100:Z110)``,
      ``""``) is still evaluated — the test is inequality, not truthiness;
    * ``error_value`` — the computed value is a spreadsheet error sentinel
      (:data:`ERROR_SENTINELS`): the cell IS a formula and its evaluation failed;
    * ``detail`` — a mandatory, actionable WHY (the LD-131 discipline).

    **Known limit of the discriminator**, stated rather than hidden: a formula that
    legitimately computes to a string equal to its own expression (``=CONCATENATE("=x")``
    contrivances) would read as inert. Lark exposes nothing else to key on, and the
    alternative — assuming success — is exactly the silent trap T23 reported.
    """
    stored = _first_cell(stored_expression) if isinstance(stored_expression, list) \
        else stored_expression
    computed = _first_cell(computed_value) if isinstance(computed_value, list) \
        else computed_value
    evaluated = computed != stored
    error_value = isinstance(computed, str) and computed in ERROR_SENTINELS
    normalized = isinstance(stored, str) and stored != expression

    if stored is None and computed is None:
        # Both legs came back empty — the cell could not be read at all. Reported as
        # unevaluated (nothing is live there) but with its own WHY, so it is never confused
        # with the inert-text signature below.
        detail = (
            f"VERIFICATION EMPTY: both read-back legs answered nothing for this cell, so the "
            f"write cannot be confirmed to have produced a live formula. The write op itself "
            f"returned (the change is on the spreadsheet); re-read the cell to see what "
            f"landed. Sent expression: {expression!r}."
        )
    elif not evaluated:
        detail = (
            f"the cell did NOT evaluate: its {COMPUTED_RENDER_OPTION} read-back is the "
            f"expression string {computed!r} itself, which is Lark's signature for INERT "
            f"TEXT. Lark ACCEPTS an unparsable formula with code 0 and stores it as a "
            f"string (probed live with \"=SUM(\"), so there is no API error to catch — this "
            f"read-back IS the detection. The write DID land; the cell now holds that text. "
            f"Fix the expression and write it again."
        )
    elif error_value:
        detail = (
            f"the cell IS a formula and Lark evaluated it to the error sentinel "
            f"{computed!r} — the expression parsed but could not be computed (a bad function "
            f"name gives #NAME?; a cross-tab reference by sheet_id instead of by TITLE gives "
            f"#REF!, both probed live). The write landed; the formula is live and will "
            f"recompute if the cause is fixed."
        )
    else:
        detail = (
            f"the cell evaluated: {EXPRESSION_RENDER_OPTION} reads back {stored!r} and "
            f"{COMPUTED_RENDER_OPTION} reads back {computed!r}. The computed value is a "
            f"snapshot — it recomputes whenever the referenced data changes, which is why "
            f"the precondition compares the expression, not this."
        )
    if normalized:
        detail += (
            f" Lark NORMALIZED the expression on the way in: sent {expression!r}, stored "
            f"{stored!r} (it quotes cross-tab titles). The stored form is authoritative for "
            f"any later precondition."
        )
    return {
        "expression": expression,
        "stored_expression": stored,
        "computed_value": computed,
        "evaluated": bool(evaluated),
        "error_value": bool(error_value),
        "normalized": bool(normalized),
        "expression_render_option": EXPRESSION_RENDER_OPTION,
        "computed_render_option": COMPUTED_RENDER_OPTION,
        "detail": detail,
    }


def read_render(client, spreadsheet_token, a1_range, render_option):
    """``client.read_values(...)`` under an **explicit** ``value_render_option``.

    A client seam whose ``read_values`` does not accept the keyword cannot serve a formula
    write at all, so the ``TypeError`` is converted to a typed
    :class:`FormulaRenderOptionUnsupported` naming the requirement — which the previewer
    turns into an ``invalid-request`` refusal instead of raising out of ``dry_run`` (which
    has no disposition boundary). A ``TypeError`` from anywhere else is re-raised untouched.
    """
    try:
        return client.read_values(
            spreadsheet_token, a1_range, value_render_option=render_option)
    except TypeError as exc:
        if "value_render_option" not in str(exc):
            raise
        raise FormulaRenderOptionUnsupported(
            f"this write-client seam's read_values() does not accept "
            f"value_render_option, so a formula write cannot read its expression "
            f"({EXPRESSION_RENDER_OPTION}) or verify its computed value "
            f"({COMPUTED_RENDER_OPTION}). Use "
            f"SheetsWriteClient.from_write_credentials() (which does), or add the "
            f"value_render_option keyword to your seam. Underlying: {exc}"
        ) from exc
