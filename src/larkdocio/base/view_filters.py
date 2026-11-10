"""larkdocio.base.view_filters — ONE filter model, TWO dialects, UNCROSSABLE by construction.

**The design fact this module owns.** A Base has two places you can put a filter, and they do
not speak the same language:

* ``POST …/records/search`` filters the rows **one read returns**, and its conditions are
  **``field_name``-keyed** (an ``fld…`` id there is a hard ``1254045`` in ``field_names`` and
  ``1254016`` in ``sort``);
* ``PATCH …/views/{view_id}`` with ``property.filter_info`` filters the rows **a human sees
  when they open that view**, and its conditions are **``field_id``-keyed**.

One model describes both — :class:`FilterSpec` — and **two serialisers** turn it into the two
wire shapes. What makes the split a *design* rather than a convention is that each serialiser
produces its **own type** (:class:`ViewFilterInfo` / :class:`SearchFilter`), neither type can be
hand-built (both constructors are token-guarded, the house's non-forgeable-value pattern), and
the view route's own signature accepts only the view type. **A contributor cannot send the wrong
dialect to the wrong route, because there is no expression that names one.**

**They also differ in how they encode a VALUE, which is the second reason there are two
serialisers rather than one with a flag.** Measured live in this story:

* ``records/search`` takes a real JSON **array** — ``"value": ["Text 1"]``, and ``[]`` for a
  valueless operator (``p1-q3-01``);
* the **view** route takes a **string carrying** a JSON array — ``"value": "[\\"Text 1\\"]"``,
  which answers ``code:0`` and reads back verbatim. The same array sent as an array answers
  ``9499``, an unquoted plain string answers ``1254001``, and for a valueless operator the key
  must be **omitted entirely** (``""`` answers ``1254001``, ``[]`` answers ``9499``; omitting it
  is ``code:0`` and reads back ``value: null``).

**And the view route's json-string is not uniformly a string INSIDE, either** — measured live
on a disposable, on a Checkbox field: its elements must be **unquoted JSON booleans**
(``"[true]"``), every quoted spelling answers ``1254001``, and both valueless operators are
refused where a text field takes them. So the view dialect preserves a ``bool`` and ``str()``s
everything else, and the search route — whose own measurement is of the string ``["True"]`` —
does not. See :data:`VIEW_ROUTE_CHECKBOX_TAKES_JSON_BOOLEANS` and the forms enumerated in
:data:`CHECKBOX_VIEW_PROBED_FORMS`.

**The operator vocabulary, by contrast, is SHARED.** ``p1-q3-01-filter-sort.json`` shows
``records/search`` taking exactly the camelCase operators the seat addendum proved on the view
route — ``is`` / ``isNot`` / ``contains`` / ``doesNotContain`` / ``isEmpty`` / ``isNotEmpty``.
:data:`VOCABULARY_PROBE` records the 2-call probe that separated the key from the operator case
at the view route, and what a shipped sentence may say about either is exactly what it found.
**Shared between the ROUTES is not the same claim as shared across every field TYPE**, and only
the first is what was observed (on a Text field): on the view route a **Checkbox** condition was
measured to take only ``is``, the other four probed operators each answering ``1254001``. That
per-type limit is refused locally by :meth:`FieldRegistry.resolve` and authored once in
:data:`VIEW_ROUTE_CHECKBOX_OPERATOR_SCOPE`.

**``isGreater`` is deliberately absent.** It answered ``1254018`` on a text field in the same
capture. An operator the library cannot show working is not in the vocabulary — a refusal a
caller can read beats a round trip to an opaque code.
"""
import json
from dataclasses import dataclass, replace
from typing import Any, Optional, Sequence, Tuple, Union

from larkdocio.base._typed import _nested, _step
from larkdocio.common.citations import DEV_REPO_LABEL, dev_repo
from larkdocio.errors import LarkConfigError

# --------------------------------------------------------------------------- #
# The vocabulary — every entry evidence-keyed                                  #
# --------------------------------------------------------------------------- #

_CAPTURES = "tests/captures/base-study/captures"

#: The six operators BOTH routes were proven to take. The comparison four — ``isGreater`` and
#: its siblings — are **not** shipped: the view route's own enum lists them (see
#: :data:`SERVER_VIEW_OPERATOR_ENUM`) but no capture shows one working, and the one that was
#: tried answered ``1254018`` on a text field (``p1-q3-01``). That is this library's evidence
#: bar, **not** a claim that Lark refuses them — and the refusal says so.
FILTER_OPERATORS: Tuple[str, ...] = (
    "is", "isNot", "contains", "doesNotContain", "isEmpty", "isNotEmpty")

#: The view route's accepted operator list **verbatim from Lark's own ``field_violations``
#: body**, captured by this story's probe. Quoted unedited, the way the ``view_type`` enum is:
#: a caller sees what Lark says, and then sees what larkdocio ships.
SERVER_VIEW_OPERATOR_ENUM = (
    "property.filter_info.conditions[*].operator is optional, options: "
    "[is,isNot,contains,doesNotContain,isEmpty,isNotEmpty,isGreater,isGreaterEqual,isLess,"
    "isLessEqual]")

#: The operators that take **no** value. The captured working shape carries ``value: []`` for
#: these — ``value: ""`` is exactly what answered ``1254001`` in ``p1-q3-02``.
VALUELESS_OPERATORS: Tuple[str, ...] = ("isEmpty", "isNotEmpty")

#: The two conjunctions, both proven (``p1-q3-01``: ``and`` and ``or`` each returned a
#: different, correct row set).
CONJUNCTIONS: Tuple[str, ...] = ("and", "or")


class BaseFilterRefusal(LarkConfigError, ValueError):
    """A filter refused **locally, before any call** — the house's refusal shape.

    Under :class:`~larkdocio.errors.LarkConfigError`, so ``except LarkConfigError`` /
    ``except LarkDocIOError`` catch it, as the base class promises. ``ValueError`` is
    **retained**, so an existing ``except ValueError`` loses nothing.
    """


#: The one authoring of what a name resolution IS. Quoted rather than restated, because the
#: honest statement is narrow: the library resolves against the field list it read, and a field
#: **deleted** between that read and the ``PATCH`` is a race no local check can win. The id goes
#: out as resolved and **Lark** answers; nothing here pretends the snapshot is still true.
RESOLUTION_IS_A_SNAPSHOT = (
    "A field name is resolved against the field list read at resolve time. That list is a "
    "SNAPSHOT: a field deleted (or renamed) between the resolve and the PATCH leaves this "
    "library holding an id the server no longer knows, and the refusal that follows is the "
    "server's, not a check this library could have made. Re-read the fields immediately "
    "before you plan if something else may be editing the table."
)

#: The **view** route's own requirement, authored once (O5″'s binding wording). It states the
#: half the evidence supports — the route is keyed by ``field_id`` — and deliberately makes no
#: claim about operator case, which the bundled probe could not separate from the key.
VIEW_ROUTE_REQUIRES_FIELD_ID = (
    "The view route keys its conditions by `field_id`, so a field NAME cannot be sent to it: "
    "Lark answers `99992402` to a name-keyed view condition on its own, measured with the "
    "operator held at a working value. Resolve the name first — "
    "FieldRegistry.from_read_client(read, app_token, table_id) reads the table's fields and "
    "hands back the id — or supply the `fld…` id you already hold."
)

#: The **search** route's own requirement, authored once. ``1254045`` is the captured refusal
#: for an ``fld…`` id in ``field_names``; ``1254016`` is the one for an id in ``sort``.
SEARCH_ROUTE_REQUIRES_FIELD_NAME = (
    "The records/search route keys its conditions by `field_name`, and a `fld…` id there is a "
    "hard refusal from Lark (`1254045` in `field_names`, `1254016` in `sort`). Send the "
    "field's human name."
)

#: **The option half of the view route's id-keying** (LD-318), authored once here and quoted by
#: every refusal about it — the same one-author rule :data:`VIEW_ROUTE_REQUIRES_FIELD_ID` follows
#: for the field key. The failure this exists to end: an option NAME sailed
#: through ``dry_run`` and died at ``apply`` on Lark's own *"the option id of 'Single Option' is
#: not found"*, which is the plan gate reporting a plan that could not work.
VIEW_ROUTE_REQUIRES_OPTION_ID = (
    "The view route keys a SELECT condition's VALUE by option `opt…` id, exactly as it keys the "
    "condition's field by `fld…` id: an option NAME sent there answers Lark's \"the option id "
    "of '<field>' is not found\" at PATCH time. So FieldRegistry.resolve() translates a known "
    "option name into its id from the field property it read, and refuses an unknown one here "
    "— naming the options that do exist — rather than letting the plan gate pass a body the "
    "apply cannot send. An `opt…` id you already hold passes through unresolved, for the same "
    "reason a `fld…` id does."
)

#: **The MEASURED answer for the VIEW route's CHECKBOX value** (LD-403) — and the one place the
#: view route's json-string carries something other than a string. Measured live on a disposable
#: the probe created and deleted (2026-08-11, ``ld403-01``), against a TEXT control on the same
#: view in the same run so a refusal is attributable to the field type rather than to the
#: harness. **Lark's own ``1254001`` body names the shape verbatim**, and it is quoted rather
#: than paraphrased.
VIEW_ROUTE_CHECKBOX_TAKES_JSON_BOOLEANS = (
    "The view route takes a CHECKBOX condition's value as a json-string whose elements are "
    "UNQUOTED JSON booleans — `\"[true]\"` — and Lark's own refusal body says so: \"the "
    "condition value of 'Checkbox' must be a legal json string, and the content is a list of "
    "booleans\". Every QUOTED spelling is a hard `1254001`: '[\"true\"]', '[\"True\"]' (which is "
    "what a blanket str() of Python's True produces), '[\"1\"]', '[\"0\"]', '[\"false\"]', "
    "'[\"False\"]', '[\"yes\"]', '[\"checked\"]' — as are the json numbers '[1]' and '[0]', a "
    "value key omitted from `is`, and BOTH valueless operators (`isEmpty` / `isNotEmpty`) whose "
    "omitted key is the only shape a TEXT field takes. So view_filter() sends a `bool` as a JSON "
    "boolean and str()s everything else; a caller writes Condition(FieldId(fld), 'is', (True,)) "
    "and this library spells it the one way the route accepts. The SEARCH route is NOT the same "
    "here — there the string '[\"True\"]' is what was measured working — which is why only the "
    "view dialect preserves the type. One further limit was measured through the shipped path "
    "and is NOT worked around locally, because Lark answers it itself: a TWO-element array is "
    "accepted with `code:0` and silently stored as the FIRST element alone — which echoes() "
    "reports as not-persisted rather than absorbing, exactly as it is meant to. A second limit "
    "was measured the same way — `isNot` on a Checkbox is a `1254001` even carrying the "
    "accepted value spelling (only `is` was seen working) — but unlike the array limit it no "
    "longer reaches Lark at all: `isNot`, and the three operators measured alongside it, are "
    "now refused LOCALLY, quoting Lark's own `1254001` before any call — see "
    "VIEW_ROUTE_CHECKBOX_OPERATOR_SCOPE."
)

#: The forms the probe actually sent, so a reader can see the EDGE of the evidence rather than
#: only its conclusion. A spelling absent from this tuple is **unmeasured**, not refused —
#: nothing here claims Lark takes nothing else.
CHECKBOX_VIEW_PROBED_FORMS: Tuple[Tuple[str, str, str], ...] = (
    ("is", '"[true]"', "code:0 — the ticked rows"),
    ("is", '"[false]"', "code:0 — reached by sending \"[]\", which Lark stored as \"[false]\""),
    ("is", '"true"', "code:0 — stored as \"[true]\", so the route wraps a bare boolean itself"),
    ("is", "true (a bare JSON boolean, not a string)", "code:0 — stored as \"[true]\""),
    ("is", '"[\\"True\\"]"', "1254001"),
    ("is", '"[\\"true\\"]"', "1254001"),
    ("is", '"[\\"1\\"]"', "1254001"),
    ("is", '"[\\"0\\"]"', "1254001"),
    ("is", '"[\\"false\\"]"', "1254001"),
    ("is", '"[\\"False\\"]"', "1254001"),
    ("is", '"[\\"yes\\"]"', "1254001"),
    ("is", '"[\\"checked\\"]"', "1254001"),
    ("is", '"[1]"', "1254001"),
    ("is", '"[0]"', "1254001"),
    ("is", "the value key omitted entirely", "1254001"),
    ("is", '["true"] (a real array, not a string)', "9499"),
    ("isNot", '"[\\"true\\"]"', "1254001"),
    ("isNot", '"[true]"', "1254001 — the ACCEPTED value spelling, so the operator is the "
                          "offender and only `is` was seen working"),
    ("contains", '"[\\"true\\"]"', "1254001"),
    ("isEmpty", "the value key omitted entirely", "1254001"),
    ("isNotEmpty", "the value key omitted entirely", "1254001"),
    ("is", '"[true, false]"', "code:0 — but stored as \"[true]\" alone, so the read-back does "
                              "NOT echo and the library reports it as not-persisted"),
)


def _refused_checkbox_view_operators() -> Tuple[str, ...]:
    """The operators every one of whose probed arms answered ``1254001`` — **derived** from
    :data:`CHECKBOX_VIEW_PROBED_FORMS`, never hand-listed beside it.

    Deriving is the point: the enumeration is the evidence, so a later probe that finds one of
    these working extends the tuple by appending an arm rather than by editing a second list that
    could disagree with the first. An operator with **no** probed arm is not in here at all —
    ``doesNotContain`` was never sent, and unmeasured is not refused.
    """
    answers: dict = {}
    for operator, _form, answer in CHECKBOX_VIEW_PROBED_FORMS:
        answers.setdefault(operator, []).append(answer)
    return tuple(operator for operator, seen in answers.items()
                 if all(answer.startswith("1254001") for answer in seen))


#: The view-route Checkbox operators **measured refused** (LD-403's ``ld403-01``), derived from
#: the probe's own arms. ``is`` is absent because it was seen working; ``doesNotContain`` is
#: absent because nobody sent it — an honest gap, and Lark answers it rather than this library.
VIEW_ROUTE_CHECKBOX_REFUSED_OPERATORS: Tuple[str, ...] = _refused_checkbox_view_operators()

#: **The per-type operator scope, authored once** (LD-408) and quoted verbatim by the refusal
#: that enforces it — the shape :data:`VIEW_ROUTE_REQUIRES_OPTION_ID` follows for the option key.
#: It is a report of a measurement, not a policy of this library's: Lark's own code is quoted,
#: the control that makes the refusals attributable is named, and the untried operator is called
#: unmeasured rather than refused.
VIEW_ROUTE_CHECKBOX_OPERATOR_SCOPE = (
    "On the VIEW route a Checkbox condition was measured to take only `is`. `isNot` answers "
    "Lark's `1254001` even carrying the ACCEPTED value spelling `\"[true]\"` — so the operator "
    "is the offender rather than the value — and `contains`, `isEmpty` and `isNotEmpty` answer "
    "the same code, in a run whose TEXT control on the same view took the valueless pair. "
    "`doesNotContain` was never sent to a Checkbox, so it is UNMEASURED rather than refused and "
    "passes through for Lark to answer. This is the VIEW route only: the search route's "
    "Checkbox operators are not what was probed, and nothing here claims them."
)

#: **The MEASURED answer for the search route's select VALUE** (LD-318, AC4) — established, not
#: assumed from the field key's symmetry. Measured live on a self-provisioned disposable
#: (2026-08-07): three records on a ``SingleSelect`` with options ``Done``/``Todo``, one
#: ``records/search`` per variant, in one run.
SEARCH_ROUTE_TAKES_OPTION_NAME = (
    "The records/search route takes a SELECT condition's value as the option NAME — the mirror "
    "of the view route, measured rather than inferred: `is` / 'Done' returned the 2 matching "
    "rows of 3, and the same condition carrying that option's `opt…` id answered `1254018 "
    "InvalidFilter` — the same code a name that does not exist answers, so the route cannot "
    "tell them apart and this library does not pretend to. search_filter() therefore sends the "
    "value as given and translates nothing; an option id is not something to send there. "
    "Because an `opt…`-shaped string is a legitimate value for a TEXT field, no local refusal "
    "guesses at the shape of a search value — this is a documented measurement, not a check."
)

#: The **result of the 2-call probe O5″ bought** — the one that separates the ``field_name`` key
#: from the operator case at the view route, which the earlier bundled probe moved together.
#: Written from the probe's own capture, run live on a self-provisioned disposable
#: (2026-08-04). **Both variables refuse INDEPENDENTLY**: call A held the key at its working
#: value and moved only the operator case, call B held the operator at its working value and
#: moved only the key, and both answered ``99992402`` — **each with the server naming its own
#: offender in ``error.field_violations``**, which is a stronger separation than the codes
#: alone. So a shipped sentence may name either, and the refusals name the one they are about.
VOCABULARY_PROBE = {
    "question": ("does the view route's 99992402 come from the field_name KEY, from the "
                 "operator case, or from both? The bundled probe moved them together."),
    "call_a": ("field_id + a snake_case operator (`is_not`) at PATCH …/views/{v} — 99992402, "
               "and the server's field_violations names "
               "`property.filter_info.conditions[*].operator` as the offender"),
    "call_b": ("field_name + a camelCase operator (`isNotEmpty`) at PATCH …/views/{v} — "
               "99992402, and the server's field_violations names "
               "`property.filter_info.conditions[*].field_id is required`"),
    "capture": dev_repo(f"{_CAPTURES}/ld264-01-view-filter-vocabulary.json"),
    "verdict": "both independently",
}


# --------------------------------------------------------------------------- #
# The model — dialect-neutral, and that is the point                           #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class FieldName:
    """A field referred to by the name a human sees. The **search** dialect's key."""

    name: str


@dataclass(frozen=True)
class FieldId:
    """A field referred to by its ``fld…`` id. The **view** dialect's key."""

    field_id: str


FieldRef = Union[FieldName, FieldId]


@dataclass(frozen=True)
class Condition:
    """One condition: which field, which operator, and the value(s) it compares against."""

    field: FieldRef
    operator: str
    values: Tuple[Any, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "values", tuple(self.values))


@dataclass(frozen=True)
class FilterSpec:
    """A whole filter — conditions joined by a conjunction, optionally with nested groups.

    ``children`` is proven on the **search** route (``p1-q3-01`` sent a nested tree and got the
    right single row back) and was never sent to a view, so the view serialiser refuses it as
    ``uncaptured`` rather than guessing a shape.
    """

    conditions: Tuple[Condition, ...] = ()
    conjunction: str = "and"
    children: Tuple["FilterSpec", ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "conditions", tuple(self.conditions))
        object.__setattr__(self, "children", tuple(self.children))

    @property
    def is_empty(self) -> bool:
        return not self.conditions and not self.children


@dataclass(frozen=True)
class SortKey:
    """One key of a ``records/search`` sort: which field, and which direction.

    **There is no view-dialect twin, and that asymmetry is the evidence, not an omission.**
    Sorting is a ``records/search`` body key; a view's saved sort is not something this library
    writes. So a sort key needs no dialect seal — there is only one route it can reach — and it
    is a plain frozen value rather than a token-guarded one.

    **The field is a NAME, and an id is refused here rather than on the wire.** ``p1-q3-01``
    step 7 sent ``{"field_name": "fldbbSDMOY"}`` and Lark answered ``1254016 InvalidSort``; step
    6 answered the same for a field name that does not exist. The first of those two this
    library can answer locally, so it does — the second is genuinely the server's to answer, and
    it is left to it.
    """

    field: FieldName
    desc: bool = False

    def __post_init__(self):
        if not isinstance(self.field, FieldName):
            got = (f"the id {self.field.field_id!r}" if isinstance(self.field, FieldId)
                   else f"{type(self.field).__name__}")
            raise BaseFilterRefusal(
                f"a sort key names the field by its human NAME and it was given {got}. "
                "`sort` is a records/search body key and a `fld…` id there is a hard `1254016 "
                f"InvalidSort` ({_CAPTURES}/p1-q3-01-filter-sort.json step 7, {DEV_REPO_LABEL}) "
                "— so this is refused here rather than sent to be refused there. Use "
                "SortKey(FieldName('Text')). Nothing was sent.")
        if not isinstance(self.desc, bool):
            raise BaseFilterRefusal(
                f"a sort key's `desc` is a bool; got {type(self.desc).__name__}. "
                "Nothing was sent.")


# --------------------------------------------------------------------------- #
# The two serialised products — non-forgeable, and DIFFERENT TYPES             #
# --------------------------------------------------------------------------- #

_VIEW_TOKEN = object()
_SEARCH_TOKEN = object()


class _SerialisedFilter(dict):
    """A serialised filter body. The constructor is token-guarded, so the only way to hold one
    is to have run its own dialect's serialiser — which is what makes the crossing impossible
    rather than merely discouraged.

    It **is** a ``dict``, so a plan carrying one still serialises to JSON with no special case;
    what it is not is *any* dict — a plain mapping, and a
    :class:`SearchFilter`, are both rejected by the view route's own signature, which asks for
    this exact type. Equality is type-aware for the same reason: two bodies that happen to look
    alike in different dialects are not the same value.
    """

    _token: object = None
    _dialect: str = ""

    def __init__(self, body=None, *, _token: object = None):
        if _token is not type(self)._token:
            raise TypeError(
                f"{type(self).__name__} values are produced only by "
                f"larkdocio.base.view_filters.{type(self)._dialect}_filter(...); a filter body "
                "is not something to hand-build, because the two Base filter dialects key "
                "their conditions differently and a hand-built one could reach the wrong "
                "route.")
        super().__init__(body or {})

    def to_dict(self) -> dict:
        """The wire body as a **plain** dict, deep-copied so a caller cannot mutate a
        serialised filter (or smuggle one back in as the other dialect)."""
        return _deepcopy_body(dict(self))

    def __eq__(self, other):
        if isinstance(other, _SerialisedFilter):
            return type(other) is type(self) and dict(other) == dict(self)
        return dict(self) == other

    def __ne__(self, other):
        return not self.__eq__(other)

    __hash__ = None

    def __repr__(self):
        return f"{type(self).__name__}({dict(self)!r})"


class ViewFilterInfo(_SerialisedFilter):
    """``property.filter_info`` for ``PATCH …/views/{view_id}`` — ``field_id``-keyed."""

    _token = _VIEW_TOKEN
    _dialect = "view"


class SearchFilter(_SerialisedFilter):
    """``filter`` for ``POST …/records/search`` — ``field_name``-keyed."""

    _token = _SEARCH_TOKEN
    _dialect = "search"


def _deepcopy_body(body):
    if isinstance(body, dict):
        return {key: _deepcopy_body(value) for key, value in body.items()}
    if isinstance(body, list):
        return [_deepcopy_body(item) for item in body]
    return body


# --------------------------------------------------------------------------- #
# The dialects                                                                 #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class FilterDialect:
    """One route's filter language: what it keys a condition by, which route reads it, which
    reference type it accepts, and which non-forgeable type its serialiser produces."""

    name: str
    key: str
    route: str
    accepts: type
    produces: type
    requirement: str
    supports_children: bool
    #: How the route encodes a condition's ``value``. ``"list"`` — a real JSON array, the
    #: ``records/search`` shape (``p1-q3-01``). ``"json-string"`` — a **string carrying** a JSON
    #: array, the view shape, measured live: ``"[\"Text 1\"]"`` is ``code:0`` and reads back
    #: verbatim, while the same array sent as an array answers ``9499`` and a plain unquoted
    #: string answers ``1254001``.
    value_encoding: str = "list"
    #: Whether a valueless operator must **omit** the key entirely. The view route requires it —
    #: ``value: ""`` answers ``1254001`` and ``value: []`` answers ``9499``, while omitting the
    #: key is ``code:0`` and reads back ``value: null``.
    omits_empty_value: bool = False
    #: Whether a ``bool`` keeps its JSON type inside the value rather than being ``str()``-ed
    #: with everything else. **The view route requires it for a Checkbox condition** and says so
    #: itself (:data:`VIEW_ROUTE_CHECKBOX_TAKES_JSON_BOOLEANS`); the search route's own
    #: measurement is of the STRING ``["True"]``, so it is left alone. One flag, one route, one
    #: type — never a general "send values as they came".
    preserves_json_booleans: bool = False
    operators: Tuple[str, ...] = FILTER_OPERATORS


VIEW_DIALECT = FilterDialect(
    name="view",
    key="field_id",
    route="/open-apis/bitable/v1/apps/:app_token/tables/:table_id/views/:view_id",
    accepts=FieldId,
    produces=ViewFilterInfo,
    requirement=VIEW_ROUTE_REQUIRES_FIELD_ID,
    supports_children=False,
    value_encoding="json-string",
    omits_empty_value=True,
    preserves_json_booleans=True,
)

SEARCH_DIALECT = FilterDialect(
    name="search",
    key="field_name",
    route="/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/search",
    accepts=FieldName,
    produces=SearchFilter,
    requirement=SEARCH_ROUTE_REQUIRES_FIELD_NAME,
    supports_children=True,
)

_TOKENS = {ViewFilterInfo: _VIEW_TOKEN, SearchFilter: _SEARCH_TOKEN}


def _key_of(dialect: FilterDialect, ref: FieldRef) -> str:
    if isinstance(ref, dialect.accepts):
        return ref.name if isinstance(ref, FieldName) else ref.field_id
    wrong = "a field NAME" if isinstance(ref, FieldName) else f"the id {ref.field_id!r}"
    raise BaseFilterRefusal(
        f"this filter is being serialised for the {dialect.name} route and it was given "
        f"{wrong}. {dialect.requirement} Nothing was sent.")


def _wire_value(dialect: FilterDialect, value):
    """One condition value, in the spelling its ROUTE was measured to take.

    Everything is ``str()``-ed — the coercion :data:`VALUE_RETYPED_ON_STORAGE` describes, and the
    one the read-back comparison meets on the way back — **except a ``bool`` on a dialect that
    preserves it**. That exception is not a loosening: it is the whole of
    :data:`VIEW_ROUTE_CHECKBOX_TAKES_JSON_BOOLEANS`, measured, and it is the only type whose
    quoted spelling the view route refuses outright. ``bool`` is tested **before** anything else
    because ``isinstance(True, int)`` is true in Python and an int must still stringify.
    """
    if isinstance(value, bool) and dialect.preserves_json_booleans:
        return value
    return str(value)


def _condition_body(dialect: FilterDialect, condition: Condition) -> dict:
    if condition.operator not in dialect.operators:
        raise BaseFilterRefusal(
            f"{condition.operator!r} is not a filter operator this library ships. The shipped "
            f"set is exactly what a capture proved working on BOTH routes: "
            f"{', '.join(dialect.operators)}. Lark's own accepted list for the view route is "
            f"longer — \"{SERVER_VIEW_OPERATOR_ENUM}\" — and the four comparison operators in "
            "it are not shipped because no capture shows one working (the one that was tried "
            "answered `1254018` on a text field). That is this library's evidence bar, not a "
            "refusal by Lark. An operator in NEITHER list answers `99992402`. Nothing was sent.")
    valueless = condition.operator in VALUELESS_OPERATORS
    if valueless and condition.values:
        raise BaseFilterRefusal(
            f"{condition.operator!r} takes no value, and {list(condition.values)!r} was given. "
            "Nothing was sent.")
    if not valueless and not condition.values:
        raise BaseFilterRefusal(
            f"{condition.operator!r} needs at least one value to compare against. "
            "Nothing was sent.")
    body = {dialect.key: _key_of(dialect, condition.field), "operator": condition.operator}
    values = [_wire_value(dialect, value) for value in condition.values]
    if valueless and dialect.omits_empty_value:
        return body                          # the key is OMITTED, not emptied — see the dialect
    body["value"] = json.dumps(values) if dialect.value_encoding == "json-string" else values
    return body


def _spec_body(dialect: FilterDialect, spec: FilterSpec, *, depth: int = 0) -> dict:
    if spec.conjunction not in CONJUNCTIONS:
        raise BaseFilterRefusal(
            f"{spec.conjunction!r} is not a conjunction Lark takes; the captured pair is "
            f"{', '.join(CONJUNCTIONS)}. Nothing was sent.")
    if spec.children and not dialect.supports_children:
        raise BaseFilterRefusal(
            "a nested filter tree is `uncaptured` on the view route: `children` is proven on "
            f"records/search ({_CAPTURES}/p1-q3-01-filter-sort.json, {DEV_REPO_LABEL}) and "
            "was never sent to a "
            "view, so this library refuses the depth rather than guessing a shape the server "
            "may or may not read. Flatten the conditions, or filter at read time with the "
            "search dialect. Nothing was sent.")
    body = {"conjunction": spec.conjunction,
            "conditions": [_condition_body(dialect, c) for c in spec.conditions]}
    if spec.children:
        body["children"] = [_spec_body(dialect, child, depth=depth + 1)
                            for child in spec.children]
    return body


def _serialise(dialect: FilterDialect, spec: FilterSpec):
    if not isinstance(spec, FilterSpec):
        raise BaseFilterRefusal(
            "a filter is a larkdocio.base.view_filters.FilterSpec — the one model both "
            f"dialects serialise; got {type(spec).__name__}.")
    if spec.is_empty:
        raise BaseFilterRefusal(
            "an empty filter is refused rather than sent: on the view route it would read as "
            "a request to clear the view's filter, and on the search route it would be a "
            "no-op body. Say what you mean explicitly. Nothing was sent.")
    body = _spec_body(dialect, spec)
    return dialect.produces(body, _token=_TOKENS[dialect.produces])


def view_filter(spec: FilterSpec) -> ViewFilterInfo:
    """Serialise ``spec`` for ``PATCH …/views/{view_id}`` — ``field_id``-keyed."""
    return _serialise(VIEW_DIALECT, spec)


def search_filter(spec: FilterSpec) -> SearchFilter:
    """Serialise ``spec`` for ``POST …/records/search`` — ``field_name``-keyed."""
    return _serialise(SEARCH_DIALECT, spec)


# --------------------------------------------------------------------------- #
# AC4 — name → id, locally, from a field read PAGED TO EXHAUSTION              #
# --------------------------------------------------------------------------- #

#: The select ``ui_type``s, and the ``type`` numbers behind them. A field is treated as a select
#: **only** when one of these arrives; the identification is the field list's own, never a guess
#: from the shape of a value (an ``opt…``-looking string is a legitimate Text value).
SELECT_UI_TYPES: Tuple[str, ...] = ("SingleSelect", "MultiSelect")
SELECT_FIELD_TYPES: Tuple[int, ...] = (3, 4)

#: The Checkbox field's own identification, in the same two spellings and read the same way —
#: from the field list, never inferred from the shape of a value. It exists because the view
#: route's Checkbox condition is the one pair whose OPERATOR acceptance was measured to differ
#: (:data:`VIEW_ROUTE_CHECKBOX_OPERATOR_SCOPE`).
CHECKBOX_UI_TYPES: Tuple[str, ...] = ("Checkbox",)
CHECKBOX_FIELD_TYPES: Tuple[int, ...] = (7,)

#: The property path this call site reads, walked with :func:`larkdocio.base._typed._nested`.
#: **The key list lives HERE, not in ``_typed``** — that module's docstring forbids it a name
#: list, because a shared default would widen every reader the first time one gained a key.
_OPTIONS_PATH: Tuple[str, ...] = ("property", "options")
#: The two names read off one option, by name, through the same walk.
_OPTION_KEYS: Tuple[str, ...] = ("id", "name")


def _is_select(ui_type, field_type) -> bool:
    return ui_type in SELECT_UI_TYPES or field_type in SELECT_FIELD_TYPES


def _is_checkbox(ui_type, field_type) -> bool:
    return ui_type in CHECKBOX_UI_TYPES or field_type in CHECKBOX_FIELD_TYPES


def _read_options(field):
    """A field's options as a tuple of ``(id, name)``, or ``None`` when the map did not arrive.

    ``None`` means **unreadable** — no ``property``, or no ``options`` key on it — and is what
    makes an absent map refusable rather than guessable; an empty tuple means the field really
    has no options yet, which is a different sentence to a caller. Every step is
    :func:`~larkdocio.base._typed._nested` / :func:`~larkdocio.base._typed._step`, the one
    by-name walk, because a field arrives through three doors (SDK-typed object, the bridged
    dict :func:`larkdocio.base.table.field_spec` produces, a raw capture dict) and a
    mapping-only walk is exactly the defect LD-281 cost a shipped refusal over.
    """
    raw = _nested(field, _OPTIONS_PATH)
    if raw is None:
        return None
    out = []
    for option in raw:
        option_id, name = (_step(option, key) for key in _OPTION_KEYS)
        if option_id is None or name is None:
            continue
        out.append((str(option_id), str(name)))
    return tuple(out)


class _Field:
    """What the registry retains per field: the two strings it always kept, plus **enough of
    ``property`` to answer the option question** — which the constructor used to discard."""

    __slots__ = ("name", "field_id", "ui_type", "field_type", "options")

    def __init__(self, name, field_id, ui_type, field_type, options):
        self.name, self.field_id = name, field_id
        self.ui_type, self.field_type, self.options = ui_type, field_type, options

    @property
    def is_select(self) -> bool:
        return _is_select(self.ui_type, self.field_type)

    @property
    def is_checkbox(self) -> bool:
        return _is_checkbox(self.ui_type, self.field_type)

    def option_catalogue(self) -> str:
        return ", ".join(f"{name!r} ({option_id})" for option_id, name in self.options or ())


class FieldRegistry:
    """A table's fields, and whether the list is **complete**.

    ``exhaustive`` is not decoration. Resolving a name against a partial list answers
    *sometimes* — and the name it cannot see is exactly the name that was truncated away — so a
    non-exhaustive registry refuses to resolve a name at all. An id needs no list, so it still
    passes straight through.

    **The registry also answers the OPTION question, and the exhaustive doctrine extends to it
    unchanged.** A select condition's *value* is keyed by ``opt…`` id on the view route
    (:data:`VIEW_ROUTE_REQUIRES_OPTION_ID`), so :meth:`resolve` translates a known option name
    into its id and refuses an unknown one **naming the options that exist** — and a select
    field whose options map is **absent or unreadable** refuses rather than passing the value
    through, for the same reason a partial field list refuses a name.
    """

    __slots__ = ("_by_name", "_by_id", "_names", "exhaustive")

    def __init__(self, fields: Sequence[Any], *, exhaustive: bool):
        self._by_name = {}
        self._by_id = {}
        names = []
        for field in fields:
            name = _step(field, "field_name")
            field_id = _step(field, "field_id")
            if name is None or field_id is None:
                continue
            names.append(name)
            self._by_name.setdefault(name, field_id)
            self._by_id.setdefault(field_id, _Field(
                name, field_id, _step(field, "ui_type"), _step(field, "type"),
                _read_options(field)))
        self._names = tuple(names)
        self.exhaustive = bool(exhaustive)

    @classmethod
    def from_read_client(cls, read_client, app_token: str, table_id: str) -> "FieldRegistry":
        """Build from ``BaseReadClient.list_fields``, which **pages to exhaustion** — which is
        why this constructor may declare the list complete."""
        return cls(read_client.list_fields(app_token, table_id) or (), exhaustive=True)

    @property
    def names(self) -> Tuple[str, ...]:
        return self._names

    def field_id_for(self, name: str) -> str:
        if not self.exhaustive:
            raise BaseFilterRefusal(
                f"cannot resolve the field name {name!r}: this field list was not read to "
                "exhaustion, and resolving against a partial list would answer for the names "
                "that happen to be on the page and silently fail for the ones that are not. "
                "Read the fields with BaseReadClient.list_fields(...), which pages to "
                "exhaustion. Nothing was sent.")
        try:
            return self._by_name[name]
        except KeyError:
            raise BaseFilterRefusal(
                f"there is no field named {name!r} on this table. The fields it does have "
                f"are: {', '.join(repr(n) for n in self._names)}. Nothing was sent.") from None

    def option_id_for(self, field_id: str, value: Any) -> str:
        """One select value → the ``opt…`` id the **view** route needs.

        An id this field already carries answers itself — the pass-through
        :meth:`resolve` gives a :class:`FieldId`, for the same reason. A name it carries answers
        that name's id. Anything else refuses, naming what exists.
        """
        field = self._by_id[field_id]
        text = value if isinstance(value, str) else str(value)
        if field.options is None:
            raise BaseFilterRefusal(
                f"cannot resolve the select value {text!r} on the field {field.name!r} "
                f"({field_id}): its options map did not arrive with the field list, so this "
                "library cannot tell a valid option from an invalid one and will not guess. "
                f"{VIEW_ROUTE_REQUIRES_OPTION_ID} Re-read the fields with "
                "BaseReadClient.list_fields(...), or supply the `opt…` id yourself. "
                "Nothing was sent.")
        for option_id, name in field.options:
            if text == option_id:
                return option_id
        for option_id, name in field.options:
            if text == name:
                return option_id
        catalogue = field.option_catalogue()
        raise BaseFilterRefusal(
            f"there is no option named (or id'd) {text!r} on the select field {field.name!r} "
            f"({field_id}). " + (
                f"The options it does have are: {catalogue}. " if catalogue
                else "That field has NO options at all yet, so no value can match it. ") +
            f"{VIEW_ROUTE_REQUIRES_OPTION_ID} {RESOLUTION_IS_A_SNAPSHOT} Nothing was sent.")

    def resolve(self, spec: FilterSpec) -> FilterSpec:
        """``spec`` with every :class:`FieldName` replaced by its :class:`FieldId`, **and every
        select condition's value replaced by its ``opt…`` option id**.

        A :class:`FieldId` the caller supplied is **passed through unresolved** — they already
        said which field they meant, and re-deriving it would only add a way to be wrong — and
        an option **id** they supplied is passed through for exactly the same reason.

        **What this resolves for, and what it cannot see.** The view route is the id-keyed one
        (:data:`VIEW_ROUTE_REQUIRES_FIELD_ID`), so this is the view direction's resolver and the
        translation follows :data:`VIEW_ROUTE_REQUIRES_OPTION_ID`. The search route is the
        mirror at the value too — **measured**, not assumed:
        :data:`SEARCH_ROUTE_TAKES_OPTION_NAME`, so a spec bound for ``search_filter()`` is not
        run through here at all (it would carry ``FieldId``s the search dialect refuses).
        A ``FieldId`` naming a field that is **not in the list this registry read** keeps the
        pass-through the field key has always had: nothing is translated on it and nothing is
        refused locally, because an id needs no list — see :data:`RESOLUTION_IS_A_SNAPSHOT`. A
        field the list carries **without** a ``ui_type``/``type`` is not a select as far as this
        library can tell, and its values are untouched; a live ``list_fields`` read carries both.
        **MultiSelect rides the same path** — its options live in the same property under the
        same key — so a name-valued MultiSelect condition translates too; only the SingleSelect
        half is proven live.

        **It also refuses the one per-TYPE operator limit there is evidence for**: on the view
        route a Checkbox takes only ``is``, and the four operators the probe measured refused
        (:data:`VIEW_ROUTE_CHECKBOX_REFUSED_OPERATORS`) are answered here, locally, quoting
        Lark's own ``1254001`` — rather than costing a call to learn it. A field whose type this
        registry cannot see is untouched, exactly as its values are.
        """
        return replace(
            spec,
            conditions=tuple(self._resolve_condition(c) for c in spec.conditions),
            children=tuple(self.resolve(child) for child in spec.children))

    def _resolve_condition(self, condition: Condition) -> Condition:
        if isinstance(condition.field, FieldId):
            resolved, field_id = condition, condition.field.field_id
        else:
            field_id = self.field_id_for(condition.field.name)
            resolved = replace(condition, field=FieldId(field_id))
        self._refuse_measured_refused_operator(resolved, field_id)
        return self._resolve_values(resolved, field_id)

    def _refuse_measured_refused_operator(self, condition: Condition, field_id: str) -> None:
        """The one per-TYPE operator refusal there is evidence for — locally, zero API calls.

        The allow-list precedent is ``view_plan.check_view_type``: a refusal Lark itself makes is
        met here rather than after a round trip, **quoting Lark's own code**, and an operator
        nobody sent is not refused at all. It lives on the resolver rather than on the serialiser
        because this is the only place that knows the field's TYPE — ``view_filter()`` sees a
        ``fld…`` id and could only guess — and it is view-scoped because
        :meth:`resolve` is the view direction's resolver.
        """
        field = self._by_id.get(field_id)
        if field is None or not field.is_checkbox:
            return
        if condition.operator not in VIEW_ROUTE_CHECKBOX_REFUSED_OPERATORS:
            return
        raise BaseFilterRefusal(
            f"the operator {condition.operator!r} was MEASURED refused on a view-route Checkbox "
            f"condition, on the field {field.name!r} ({field_id}). "
            f"{VIEW_ROUTE_CHECKBOX_OPERATOR_SCOPE} Use `is` with the boolean you mean — "
            "Condition(FieldId(fld), 'is', (True,)) — or filter at read time with the search "
            "dialect, whose Checkbox operators this measurement says nothing about. "
            f"The forms the probe sent are enumerated in CHECKBOX_VIEW_PROBED_FORMS "
            f"({_CAPTURES}/ld403-01-checkbox-view-filter.json, {DEV_REPO_LABEL}). "
            "Nothing was sent.")

    def _resolve_values(self, condition: Condition, field_id: str) -> Condition:
        field = self._by_id.get(field_id)
        if field is None or not field.is_select or not condition.values:
            return condition
        if condition.operator in VALUELESS_OPERATORS:
            return condition          # nothing to translate, and the serialiser refuses values
        if not self.exhaustive:
            raise BaseFilterRefusal(
                f"cannot resolve the select values {list(condition.values)!r} on the field "
                f"{field.name!r}: this field list was not read to exhaustion, so the options "
                "map it carries is a page rather than the field's own. The same reason a "
                "partial list cannot resolve a NAME applies to an option. Read the fields with "
                "BaseReadClient.list_fields(...), which pages to exhaustion. Nothing was sent.")
        return replace(condition, values=tuple(
            self.option_id_for(field_id, value) for value in condition.values))


# --------------------------------------------------------------------------- #
# AC5's comparison — semantic, explicit, and never a loose containment check    #
# --------------------------------------------------------------------------- #

#: The keys the **server** adds to a persisted condition. They are its answer, not the
#: caller's request, so the comparison drops them — and drops exactly these, by name, so a key
#: that starts arriving un-asked-for is a difference the read-back reports rather than absorbs.
SERVER_ADDED_CONDITION_KEYS: Tuple[str, ...] = ("condition_id", "field_type")

#: **The one difference the read-back comparison absorbs, and why it is not a loosening**
#: (LD-282). Authored once, quoted by the guide.
VALUE_RETYPED_ON_STORAGE = (
    "The view route carries a condition's value as a STRING containing a JSON array, and Lark "
    "parses that array before it stores it: an element that looks like a number comes back "
    "UNQUOTED. This library sends '[\"ExactDate\", \"1786147200000\"]' — it stringifies every "
    "value EXCEPT a bool, which the route itself refuses quoted "
    "(VIEW_ROUTE_CHECKBOX_TAKES_JSON_BOOLEANS); the reason the rest are stringified is "
    "unchanged, and so is the consequence that a caller cannot choose the spelling — and the "
    "same filter reads back as "
    "'[\"ExactDate\",1786147200000]'. The two strings differ; the two filters do not. So the "
    "read-back parses the json-string value on BOTH sides and compares the elements as text. "
    "It absorbs Lark's own re-typing and nothing else: a server that stored a DIFFERENT "
    "number, dropped an element, added one or reordered them still reads as not-persisted."
)


def _normalize_condition(condition) -> dict:
    """One persisted condition, reduced to the shape a serialiser would have produced.

    Two reductions, both **named** rather than general: the server's own
    :data:`SERVER_ADDED_CONDITION_KEYS` are dropped, and a ``value`` the server sent as
    ``null`` is dropped — because that is how the view route echoes back a valueless operator
    whose ``value`` key was **omitted**, which is the only shape it accepts (``""`` answers
    ``1254001``, ``[]`` answers ``9499``). Nothing else is touched: a ``value`` the server
    rewrote stays in the comparison and makes the read-back fail, which is the point.
    """
    out = {}
    for key, value in dict(condition).items():
        if key in SERVER_ADDED_CONDITION_KEYS:
            continue
        if key == "value" and value is None:
            continue
        out[key] = value
    return out


def normalize_persisted(persisted: Optional[dict]) -> Optional[dict]:
    """A read-back ``filter_info`` reduced to the shape a serialiser would have produced.

    Explicit and tested rather than loose: only :data:`SERVER_ADDED_CONDITION_KEYS` are
    dropped, and everything else the server sent stays in the comparison.
    """
    if not isinstance(persisted, dict):
        return None
    out = {"conjunction": persisted.get("conjunction"),
           "conditions": [_normalize_condition(condition)
                          for condition in (persisted.get("conditions") or ())]}
    children = persisted.get("children")
    if children:
        out["children"] = [normalize_persisted(child) for child in children]
    return out


def _comparable_value(value):
    """A condition ``value`` in the form the two sides are compared in.

    A ``json-string`` value is **parsed** and its elements rendered as text, because the JSON
    quoting of a numeric element is the one difference the wire introduces that is not a
    difference in the filter (:data:`VALUE_RETYPED_ON_STORAGE`). The text rendering is
    ``str()`` — the very coercion :func:`_condition_body` applies on the way out, so the two
    sides meet in the same place. Anything that is not a string carrying a JSON **array** is
    returned untouched, so nothing else is absorbed.
    """
    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except ValueError:
        return value
    if not isinstance(parsed, list):
        return value
    return ("json-array", tuple(str(element) for element in parsed))


def _comparable_condition(condition) -> dict:
    if not isinstance(condition, dict):
        return condition
    return {key: _comparable_value(value) if key == "value" else value
            for key, value in condition.items()}


def _comparable(body):
    """One side of the read-back comparison, with **only** each condition's ``value``
    canonicalised. Everything else — the conjunction, the operator, the field id, the number
    and the order of the conditions, and any key neither side expected — is compared
    verbatim, which is what keeps :func:`echoes` a whole-value equality."""
    if not isinstance(body, dict):
        return body
    out = {}
    for key, value in body.items():
        if key == "conditions" and isinstance(value, list):
            out[key] = [_comparable_condition(condition) for condition in value]
        elif key == "children" and isinstance(value, list):
            out[key] = [_comparable(child) for child in value]
        else:
            out[key] = value
    return out


def echoes(sent: ViewFilterInfo, persisted: Optional[dict]) -> bool:
    """Does the view's persisted ``filter_info`` **echo the conditions that were sent**?

    A whole-value equality after normalisation — never ``issubset`` and never ``in`` — so a
    read-back carrying an extra condition, a different operator or a merge of an older filter
    is reported as **not persisted**. That is the whole point: on this API a ``code:0``
    proves acceptance and nothing else.

    The **one** difference it absorbs is :data:`VALUE_RETYPED_ON_STORAGE` — the JSON quoting
    Lark itself changes when it parses a ``json-string`` value — and it absorbs it by parsing
    that value on **both** sides rather than by relaxing the equality, so a real swallow is
    still a real swallow: a different number, a dropped element, an added one, a reordering,
    or a ``code:0`` that stored nothing all still read as not-persisted.
    """
    if not isinstance(sent, ViewFilterInfo):
        raise TypeError(
            "echoes() compares a ViewFilterInfo against a view's read-back; a search-dialect "
            f"filter is a different language and cannot be compared here (got {type(sent).__name__}).")
    return _comparable(normalize_persisted(persisted)) == _comparable(sent.to_dict())


__all__ = [
    "BaseFilterRefusal",
    "CHECKBOX_FIELD_TYPES",
    "CHECKBOX_UI_TYPES",
    "CHECKBOX_VIEW_PROBED_FORMS",
    "CONJUNCTIONS",
    "Condition",
    "FILTER_OPERATORS",
    "FieldId",
    "FieldName",
    "FieldRegistry",
    "FilterDialect",
    "FilterSpec",
    "RESOLUTION_IS_A_SNAPSHOT",
    "SEARCH_DIALECT",
    "SEARCH_ROUTE_REQUIRES_FIELD_NAME",
    "SEARCH_ROUTE_TAKES_OPTION_NAME",
    "SELECT_FIELD_TYPES",
    "SELECT_UI_TYPES",
    "SERVER_ADDED_CONDITION_KEYS",
    "SearchFilter",
    "SERVER_VIEW_OPERATOR_ENUM",
    "SortKey",
    "VALUELESS_OPERATORS",
    "VALUE_RETYPED_ON_STORAGE",
    "VIEW_DIALECT",
    "VIEW_ROUTE_CHECKBOX_OPERATOR_SCOPE",
    "VIEW_ROUTE_CHECKBOX_REFUSED_OPERATORS",
    "VIEW_ROUTE_CHECKBOX_TAKES_JSON_BOOLEANS",
    "VIEW_ROUTE_REQUIRES_FIELD_ID",
    "VIEW_ROUTE_REQUIRES_OPTION_ID",
    "VOCABULARY_PROBE",
    "ViewFilterInfo",
    "echoes",
    "normalize_persisted",
    "search_filter",
    "view_filter",
]
