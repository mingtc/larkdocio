"""larkdocio.sheets.requests._cells — the range/cell-targeted request family — value / formula / rich / dropdown-rule.

Carries its own shared base :class:`_CellWrite` (the mixin travels with the one family
it bases — see the package docstring).

Split out of the flat 2,462-line ``sheets/requests.py`` by LD-224, **verbatim** —
pre-split lines 172–457. The package's ``__init__`` re-exports every name defined here,
so ``from larkdocio.sheets.requests import <name>`` is unchanged.
"""
from dataclasses import dataclass

from larkdocio.sheets.formula import encode_formula, normalize_expression
from larkdocio.sheets.rich_encode import (
    encode_dropdown_rule,
    encode_hyperlink,
    encode_mention,
    encode_multi_select,
    encode_styled_runs,
)
from larkdocio.sheets.write_range import WriteRange, parse_write_range

from ._gates import WriteOpKind


# --------------------------------------------------------------------------- #
# _CellWrite — the shared base for the range/cell-targeted request trio (T4).   #
# --------------------------------------------------------------------------- #

class _CellWrite:
    """Shared base for the range/cell-targeted write-request trio — value / rich /
    dropdown-rule (LD-125 T4). Each carries a ``target``
    :class:`~larkdocio.sheets.write_range.WriteRange` and drives the gated value / rule
    path (never the structural / merge / tab seams), so the base holds their common
    dispatch defaults in ONE place (the sheets twin of the ``_Structural`` / ``_TabWrite``
    mixins the structural / tab families already had):

    * :attr:`is_rich` ``False`` — the plain-value structured-cell refusals apply; the rich
      sibling overrides it ``True`` to LIFT them for its encoded cell;
    * :attr:`write_kind` ``"value"`` — the request-side preview discriminator; a plain / rich
      cell writes through ``put_values``; the dropdown sibling overrides it
      ``"data-validation"`` to route through ``set_data_validation``;
    * :attr:`op_kinds` ``(WriteOpKind.VALUE,)`` — the cheap values leg only, no export; the
      dropdown sibling overrides it to :data:`WriteOpKind.DATA_VALIDATION`.
    """

    is_rich = False
    write_kind = "value"

    @property
    def op_kinds(self) -> tuple:
        return (WriteOpKind.VALUE,)


# --------------------------------------------------------------------------- #
# ValueWriteRequest — the findings-agnostic value-write request (target+values) #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ValueWriteRequest(_CellWrite):
    """One value-write intent — a target :class:`~larkdocio.sheets.write_range.WriteRange`
    (the shared A1 model) + a values matrix. **Findings-agnostic**: exactly a target and
    values, nothing about a consumer's findings / approval / status.

    Build via :meth:`for_a1` (parses + normalizes an A1 string through the shared A1 model — a
    single cell becomes ``A1:A1``) or with a pre-built :class:`WriteRange`.
    """

    target: WriteRange
    values: list
    @classmethod
    def for_a1(cls, a1_range: str, values: list) -> "ValueWriteRequest":
        return cls(target=parse_write_range(a1_range), values=values)

    def to_dict(self) -> dict:
        return {"target": self.target.a1(), "values": self.values}

    @classmethod
    def from_dict(cls, d: dict) -> "ValueWriteRequest":
        return cls.for_a1(d["target"], d["values"])


# --------------------------------------------------------------------------- #
# FormulaWriteRequest — the LD-149 formula write (the probe-confirmed object    #
# form). Its own family, NOT a value/rich variant, because it is the one write  #
# whose precondition and verification read a DIFFERENT render mode: the         #
# precondition compares the EXPRESSION (`Formula` mode) and the verification    #
# reads the COMPUTED value (`UnformattedValue`). See `larkdocio.sheets.formula`  #
# for the probe evidence the whole design rests on.                             #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class FormulaWriteRequest:
    """One **formula** write intent — a target
    :class:`~larkdocio.sheets.write_range.WriteRange` + an ``=``-leading ``expression``.

    **Why this type exists.** Round 2 wrote ``"=SUM(B3:B8)"`` as a plain
    :class:`ValueWriteRequest` value and got back the **literal string, unevaluated —
    silently**. A live probe confirmed the fix: the documented object form
    ``{"type":"formula","text":"=SUM(...)"}`` written through the same values ``PUT``
    **does** evaluate, and **no** ``valueInputOption`` exists that would make a plain string
    evaluate (probed three ways). So a formula is a **distinct intent**, expressed by a
    distinct type — and a ``=``-prefixed *plain* value still earns the loud dry-run note
    (:data:`~larkdocio.sheets.formula.INERT_STRING_NOTE`) either way.

    **Always a single cell** (the :class:`RichCellWriteRequest` posture): a formula is one
    cell, exposed as a 1×1 :attr:`values` matrix so it flows through the same gate as every
    other write. Build via :meth:`for_a1` — the expression is validated there
    (:class:`~larkdocio.sheets.formula.FormulaExpressionError` for anything not starting with
    ``=``), so a request that would silently store inert text **cannot be built**.

    **Its own gate legs.** :attr:`write_kind` ``"formula"`` routes the request to the formula
    preview/apply legs, which are the only ones that read by render mode:

    * the plan captures the target's current **expression** (``Formula``) as the precondition
      basis and its current **computed value** (``UnformattedValue``) as a preview note;
    * apply re-reads the **expression** and refuses ``precondition-mismatch`` on drift — the
      deliberate choice: a computed value moves whenever the referenced data moves
      (probed: ``21``→``120`` from one operand edit), so comparing it would refuse writes
      nobody made. The expression is the author's intent;
    * after the write, both legs are re-read into the apply-log's ``formula`` record, whose
      ``evaluated`` flag is the ONLY way to catch an unparsable formula — Lark **accepts**
      ``"=SUM("`` with ``code 0`` and stores it inert, so there is no error to catch.

    :attr:`op_kinds` is :data:`WriteOpKind.VALUE`: a formula touches a cell's value, not
    style / number-format / merge / structure, so the cheap values leg proves it and no
    export leg is triggered.

    **Findings-agnostic** (exactly a target + an expression) — that constraint is guarded
    by the test suite.
    """

    target: WriteRange
    expression: str

    #: The formula legs' dispatch key (the request-side preview discriminator).
    write_kind = "formula"
    #: A formula cell is not a *rich* cell — the LD-119 encoders' refusal-lifting does not
    #: apply to it, and its own leg is what handles the structured payload.
    is_rich = False

    def __post_init__(self):
        # Validated here too (not only in `for_a1`) so a directly-constructed request cannot
        # carry text Lark would store inert — the guard is on the type, not on one door.
        normalize_expression(self.expression)

    @property
    def op_kinds(self) -> tuple:
        return (WriteOpKind.VALUE,)

    @property
    def values(self) -> list:
        """The 1×1 values matrix carrying the **object form** — a formula is one cell."""
        return [[encode_formula(self.expression)]]

    @classmethod
    def for_a1(cls, a1_range: str, expression: str) -> "FormulaWriteRequest":
        """Build a formula write for ``a1_range`` (a single cell normalizes to ``A1:A1``).

        ``expression`` must be a non-empty ``str`` starting with ``=``; anything else raises
        :class:`~larkdocio.sheets.formula.FormulaExpressionError` **at build time** — there
        is deliberately no auto-prefixing, because silently rewriting an expression is the
        class of helpfulness that produced that bug.
        """
        return cls(target=parse_write_range(a1_range), expression=normalize_expression(expression))

    def to_dict(self) -> dict:
        return {"target": self.target.a1(), "expression": self.expression, "kind": "formula"}

    @classmethod
    def from_dict(cls, d: dict) -> "FormulaWriteRequest":
        return cls.for_a1(d["target"], d["expression"])


# --------------------------------------------------------------------------- #
# RichCellWriteRequest — the LD-119 rich-cell write (encoded types only)        #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class RichCellWriteRequest(_CellWrite):
    """One rich-cell write intent — a target
    :class:`~larkdocio.sheets.write_range.WriteRange` + a single **encoded** rich cell +
    its kind.

    A plain :class:`ValueWriteRequest` **refuses** a structured proposed / current cell
    (a rich cell is not a plain-value write — :data:`Refusal.RICH_CELL_TARGET`). A rich
    request carries a cell one of the encoders
    (:mod:`larkdocio.sheets.rich_encode`) produced — a **hyperlink** / **styled-runs** /
    **@mention** / **multi-select** — and the gate **LIFTS** the refuse-on-rich
    restriction **for the encoded types only** (:attr:`is_rich`): the plan's expectation
    for a rich target is the structured form, and the precondition compare-and-swap still
    guards it. Build via the four classmethods so the wire shape always comes from the
    shared encoder (a caller never hand-assembles a segment object); the comma-in-label
    refusal fires at build time inside :meth:`multi_select`.

    **Findings-agnostic** (exactly a target + an encoded cell + a kind) — that constraint
    is guarded by the test suite. Always a **single cell**: a rich value is one cell, exposed as a
    1×1 :attr:`values` matrix so it flows through the same gate as a plain write.
    """

    target: WriteRange
    cell: object
    kind: str

    HYPERLINK = "rich:hyperlink"
    STYLED_RUNS = "rich:styled-runs"
    MENTION = "rich:mention"
    MULTI_SELECT = "rich:multi-select"

    #: The gate marker: a rich request LIFTS the structured-cell refusals for its own
    #: (encoded) cell, while the plain path keeps refusing raw structured values.
    is_rich = True

    @property
    def values(self) -> list:
        """The 1×1 values matrix (`[[cell]]`) — a rich value is a single cell."""
        return [[self.cell]]

    @classmethod
    def hyperlink(cls, a1_range: str, link: str, text: str = None) -> "RichCellWriteRequest":
        """Build a **hyperlink** cell write: ``a1_range`` gets ``link``, labelled ``text``.

        **This ships and it works.** It carried no docstring for eight releases, and a
        capability with no ``__doc__`` and no recipe reads to a consumer as a capability that
        does not exist (one nearly reported the deliverable impossible before finding this
        method through ``dir()``). The worked example is the guide's
        § *"Recipe: write a hyperlink and a styled run into a cell"*.

        ``text`` is the **label** the cell shows; omit it and the link is its own label. Do
        not confuse this with a **cell-level deep link** — a URL pointing AT a cell, which is
        UI-only and is a different question entirely (§ "The mintable deep links"). What this
        writes is an ordinary cell whose value is a clickable link, and it goes through the
        same plan gate as every other write.
        """
        return cls(parse_write_range(a1_range), encode_hyperlink(link, text=text), cls.HYPERLINK)

    @classmethod
    def styled_runs(cls, a1_range: str, runs) -> "RichCellWriteRequest":
        """Build a **styled-runs** cell write: one cell whose text carries per-run styling.

        ``runs`` is a sequence of **mappings**, each a kwargs bundle for
        :func:`~larkdocio.sheets.rich_encode.encode_styled_run` —
        ``{"text": "…", "bold": True, "italic": …, "strikethrough": …, "underline": …,
        "fore_color": "#RRGGBB", "font_size": 12}``, of which only ``text`` is required. The
        encoder builds the wire shape, so a caller never hand-assembles a segment object.

        **This ships and it works** — like :meth:`hyperlink` it shipped with no ``__doc__``
        and no recipe for eight releases; the worked example is the guide's § *"Recipe: write a
        hyperlink and a styled run into a cell"*. Note the asymmetry the read side documents:
        a run's ``foreColor`` and ``fontSize`` are **written** but are **dropped at render**
        by this library's Markdown, so a colour written here is not one this library will read
        back to you.
        """
        return cls(parse_write_range(a1_range), encode_styled_runs(runs), cls.STYLED_RUNS)

    @classmethod
    def mention(cls, a1_range: str, open_id: str, *, notify: bool = False,
                grant_read_permission: bool = False) -> "RichCellWriteRequest":
        """Build an **@mention** cell write for ``open_id`` — never a name in a string.

        Resolve the person to an ``open_id`` FIRST (``larkdocio.contacts.resolve_colleague``
        by email, ``resolve_user`` by name), then pass it here; ``dry_run`` proves the id
        still exists and reports it in ``plan.mention_validation``. ``notify`` pings them;
        ``grant_read_permission`` gives them access to the spreadsheet. The worked example is
        the guide's § *"Recipe: author a sheet cell that @mentions a teammate"*.
        """
        return cls(
            parse_write_range(a1_range),
            encode_mention(open_id, notify=notify, grant_read_permission=grant_read_permission),
            cls.MENTION,
        )

    @classmethod
    def multi_select(cls, a1_range: str, labels) -> "RichCellWriteRequest":
        """Build a multi-select rich write. A **comma inside an option label** refuses
        here (a typed :class:`~larkdocio.sheets.rich_encode.MultiSelectLabelError`)
        — you cannot even build the request with an unrepresentable label."""
        return cls(parse_write_range(a1_range), encode_multi_select(labels), cls.MULTI_SELECT)

    def to_dict(self) -> dict:
        return {"target": self.target.a1(), "cell": self.cell, "kind": self.kind}


# --------------------------------------------------------------------------- #
# DropdownRuleWriteRequest — the LD-120 dropdown (dataValidation) rule write     #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class DropdownRuleWriteRequest(_CellWrite):
    """One dropdown (``dataValidation``) list-rule write intent.

    The **dataValidation family** — the rule the rich multi-select cell
    (:class:`RichCellWriteRequest` ``multi_select``) pairs with. It carries a target
    :class:`~larkdocio.sheets.write_range.WriteRange` + an **encoded rule** the encoder
    (:func:`~larkdocio.sheets.rich_encode.encode_dropdown_rule`) produced — a
    ``{"dataValidationType":"list","dataValidation":{"conditionValues":[…],"options":{…}}}``
    payload — so a caller never hand-assembles the wire shape. The **`90204` colors caveat**
    (``highlightValidData:true`` needs a 1:1 ``colors`` array) fires at build time inside
    :meth:`list_rule` (a typed :class:`~larkdocio.sheets.rich_encode.DropdownColorsError`),
    so an unrepresentable rule cannot even be constructed.

    A rule is **not a cell value**: it writes through the client's ``set_data_validation``
    seam (``POST …/dataValidation``), never ``put_values`` — so :attr:`write_kind` is
    ``"data-validation"`` and the engine skips the scalar value-precondition (there is no
    ``before`` value to compare). The gate is otherwise identical: the mandatory
    :func:`dry_run` previews it and the ``revision`` compare-and-swap (``STALE_SHEET``)
    guards it, so a rule write is never blind or unattended.

    **Findings-agnostic** (exactly a target + an encoded rule) — that constraint is guarded over
    it. Always a **single logical write** (one rule on a range), exposed as a resolved plan
    entry whose ``after`` is the rule payload.
    """

    target: WriteRange
    rule: dict

    #: The write endpoint this request drives: ``POST …/dataValidation`` via the client's
    #: ``set_data_validation`` seam (never ``put_values``).
    write_kind = "data-validation"

    @property
    def op_kinds(self) -> tuple:
        """A dropdown rule TOUCHES exactly :data:`WriteOpKind.DATA_VALIDATION` — verified by
        its own ``dataValidation`` GET (the rule leg), so it triggers **neither**
        the export style leg nor the v3 merge leg (``requires_style_leg`` /
        ``requires_merge_leg`` are ``False`` for it)."""
        return (WriteOpKind.DATA_VALIDATION,)

    @classmethod
    def list_rule(cls, a1_range: str, condition_values, *, multiple_values: bool = False,
                  highlight_valid_data: bool = False, colors=None) -> "DropdownRuleWriteRequest":
        """Build a dropdown list-rule write. ``multiple_values`` picks single- vs
        multi-select; the **`90204` colors caveat** (``highlight_valid_data`` needs a 1:1
        ``colors`` array) refuses at build time (a typed
        :class:`~larkdocio.sheets.rich_encode.DropdownColorsError`) — you cannot
        build the request with an unrepresentable rule."""
        return cls(
            parse_write_range(a1_range),
            encode_dropdown_rule(
                condition_values,
                multiple_values=multiple_values,
                highlight_valid_data=highlight_valid_data,
                colors=colors,
            ),
        )

    def to_dict(self) -> dict:
        return {"target": self.target.a1(), "rule": self.rule, "kind": "dropdown-rule"}
