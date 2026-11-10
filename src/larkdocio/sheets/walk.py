"""larkdocio.sheets.walk — what a whole-workbook read hands back when one tab is
unreachable (LD-383).

A workbook read is a **walk over tabs**, and a walk needs a failure shape. Before this module
it had none: the shipped pattern was a list comprehension over ``query_sheets`` calling
``read_used_range``, so the first tab Lark refused ended the walk and the caller got nothing —
including every tab that read perfectly. A consumer workbook with 20 refused tabs out of 22
returned **zero** rows.

The answer is the one this library already gives for the identical situation one surface over
— the folder reader's **skip-loudly** (:mod:`larkdocio.drive.read`), whose two promises are
copied here deliberately rather than re-invented:

1. **A tab that misses never fails the walk.** Every other tab is still read.
2. **A miss is never silent, and it is disclosed in Lark's own words** — the verbatim ``code``
   and ``msg``, attached to the tab they belong to, with no diagnosis layered on top. What a
   "ghost" tab actually *is* has not been measured (the bounded probe's capture is
   ``tests/captures/ghost-tabs-probe/captures/01-ghost-vs-real.json``, in the source repository), so nothing here
   claims to know.

The types are plain frozen dataclasses — inspectable, serializable, and total:
:meth:`SpreadsheetRead.accounted` is the invariant that **every enumerated tab appears exactly
once**, as a read or as a disclosed skip. The orchestration itself lives on the client
(:meth:`larkdocio.sheets.client.SheetsReadClient.read_spreadsheet`), beside the two reads it
composes.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

from larkdocio.sheets.extent import UsedRange
from larkdocio.sheets.models import SheetTab

#: The two outcome kinds a tab can land in. There is no third: a tab is read, or its miss is
#: disclosed. (The folder reader's third kind, ``folder``, has no analogue inside a workbook.)
TAB_READ = "read"
TAB_SKIPPED = "skipped"


def _describe(value) -> str:
    """``"str ('tok')"`` — what was passed, named by type and shown, and nothing diagnosed."""
    return f"{type(value).__name__} ({value!r})"


def _typed(owner: str, field: str, value, expected: type, *, optional: bool = False):
    """Refuse a wrongly-typed constructor argument **at the construction site**, loudly.

    The message names the field, what was expected and what arrived — and stops there. The
    walk's whole ethic is *disclose loudly, never silently short* (the two promises above);
    a result object that accepts a client where a token belongs is that ethic violated at
    the type level, and the ``AttributeError`` three calls later is the bill.
    """
    if value is None and optional:
        return
    if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
        raise TypeError(
            f"{owner}({field}=…) expects "
            f"{expected.__name__}{' or None' if optional else ''}; got {_describe(value)}")


@dataclass(frozen=True, kw_only=True)
class TabSkip:
    """Why one tab was skipped — loudly.

    ``code`` / ``msg`` are **Lark's own**, verbatim and unedited; ``reason`` is the sentence
    that frames them for a human and **quotes rather than diagnoses**. ``sheet_id`` / ``title``
    are the tab's own identity, so a disclosure is never orphaned from what it is about.

    **Keyword-only, and type-checked**: five same-shaped fields in a row is exactly
    the construction a positional call gets wrong silently, and a disclosure carrying a
    swapped code and message discloses nothing.
    """

    sheet_id: str
    title: Optional[str]
    code: Optional[int]
    msg: Optional[str]
    reason: str

    def __post_init__(self):
        _typed("TabSkip", "sheet_id", self.sheet_id, str)
        _typed("TabSkip", "title", self.title, str, optional=True)
        _typed("TabSkip", "code", self.code, int, optional=True)
        _typed("TabSkip", "msg", self.msg, str, optional=True)
        _typed("TabSkip", "reason", self.reason, str)


@dataclass(frozen=True, kw_only=True)
class TabOutcome:
    """What the walk decided for one tab — exactly one of read / skipped.

    A ``read`` carries its :class:`~larkdocio.sheets.extent.UsedRange`; a ``skipped`` carries
    its :class:`TabSkip`. Both carry the tab, so a caller iterating outcomes never has to join
    back to the enumeration to learn which tab it is looking at.

    **Keyword-only, and the read⇄used / skipped⇄skip pairing is enforced HERE** —
    it is :meth:`SpreadsheetRead.accounted`'s per-outcome half, and enforcing it at
    construction is cheap and honest: an outcome that violates it is wrong the moment it is
    made, so ``accounted()`` answering ``False`` long afterwards reports the mistake at the
    wrong end of the program. ``accounted()`` keeps its own checks — it is the promise stated
    as a boolean over the WHOLE result (including the whole-walk length identity, which no
    single outcome can know).
    """

    tab: SheetTab
    kind: str
    used: Optional[UsedRange] = None
    skip: Optional[TabSkip] = None

    @property
    def reason(self) -> Optional[str]:
        """A passthrough to ``skip.reason`` — ``None`` means *this tab read*, not *this skip
        had no reason* (``TabSkip.reason`` is a required field, so a skip always has one).
        The deeper spelling (``outcome.skip.reason``) keeps working; this is the one-level-up
        convenience a caller reaches for first."""
        return self.skip.reason if self.skip is not None else None

    def __post_init__(self):
        _typed("TabOutcome", "tab", self.tab, SheetTab)
        _typed("TabOutcome", "kind", self.kind, str)
        _typed("TabOutcome", "used", self.used, UsedRange, optional=True)
        _typed("TabOutcome", "skip", self.skip, TabSkip, optional=True)
        if self.kind not in (TAB_READ, TAB_SKIPPED):
            raise ValueError(
                f"TabOutcome(kind=…) is one of {TAB_READ!r} / {TAB_SKIPPED!r}; "
                f"got {self.kind!r}")
        if (self.used is not None) != (self.kind == TAB_READ):
            raise TypeError(
                f"TabOutcome(kind={self.kind!r}) pairs with used="
                f"{'a UsedRange' if self.kind == TAB_READ else 'None'}; "
                f"got {_describe(self.used)}")
        if (self.skip is not None) != (self.kind == TAB_SKIPPED):
            raise TypeError(
                f"TabOutcome(kind={self.kind!r}) pairs with skip="
                f"{'a TabSkip' if self.kind == TAB_SKIPPED else 'None'}; "
                f"got {_describe(self.skip)}")


@dataclass(frozen=True, kw_only=True)
class SpreadsheetRead:
    """The structured result of a whole-workbook read: every enumerated tab, its outcome, and
    the values of the ones that read.

    :attr:`pairs` is the ``(tab, used_range)`` list
    :func:`~larkdocio.sheets.table.render_spreadsheet` consumes, so the Markdown projection is
    one call away and unchanged in shape — **the skips ride alongside it rather than inside
    it**, which is what lets a caller render a partial workbook *and* say so
    (``render_spreadsheet(wb.pairs, skips=wb.skips)``).

    **Keyword-only, and ``outcomes`` is type-checked**. Built from a **client and a token
    string**, positionally, the frozen dataclass used to take it, and the failure surfaced three
    calls later as an ``AttributeError`` on ``.reads``. Both
    doors are shut here: the construction is keyword-only, and ``outcomes`` must be a sequence
    of :class:`TabOutcome` — the refusal names the value and what was expected, and diagnoses
    nothing further. A ``list`` is accepted and frozen to a tuple; a ``str``/``bytes`` is not
    a sequence of outcomes and is refused with everything else.
    """

    spreadsheet_token: str
    outcomes: Tuple[TabOutcome, ...] = ()

    def __post_init__(self):
        _typed("SpreadsheetRead", "spreadsheet_token", self.spreadsheet_token, str)
        outcomes = self.outcomes
        if isinstance(outcomes, (str, bytes)) or not isinstance(outcomes, (list, tuple)):
            raise TypeError(
                "SpreadsheetRead(outcomes=…) expects a sequence of TabOutcome; "
                f"got {_describe(outcomes)}")
        for index, outcome in enumerate(outcomes):
            if not isinstance(outcome, TabOutcome):
                raise TypeError(
                    "SpreadsheetRead(outcomes=…) expects a sequence of TabOutcome; "
                    f"got {_describe(outcome)} at index {index}")
        object.__setattr__(self, "outcomes", tuple(outcomes))

    @property
    def reads(self) -> Tuple[TabOutcome, ...]:
        return tuple(o for o in self.outcomes if o.kind == TAB_READ)

    @property
    def skips(self) -> Tuple[TabOutcome, ...]:
        return tuple(o for o in self.outcomes if o.kind == TAB_SKIPPED)

    @property
    def pairs(self) -> List[Tuple[SheetTab, UsedRange]]:
        """The ``(tab, used_range)`` pairs of the tabs that READ, in sheet order."""
        return [(o.tab, o.used) for o in self.reads]

    @property
    def skipped_any(self) -> bool:
        """Whether this read is **partial** — the one boolean a caller needs to branch on."""
        return bool(self.skips)

    def accounted(self) -> bool:
        """**The promise, as a boolean.** Every enumerated tab appears exactly once in the
        outcomes and the read/skipped partition is total and disjoint — so no tab the
        enumeration saw is dropped, and none is counted twice."""
        return (len(self.reads) + len(self.skips) == len(self.outcomes)
                and all(o.kind in (TAB_READ, TAB_SKIPPED) for o in self.outcomes)
                and all((o.used is not None) == (o.kind == TAB_READ) for o in self.outcomes)
                and all((o.skip is not None) == (o.kind == TAB_SKIPPED)
                        for o in self.outcomes))


def skip_sentence(code, msg) -> str:
    """The disclosure sentence — **Lark's own words, quoted**, and no cause claimed.

    The folder reader's :func:`larkdocio.drive.read._lark_sentence` one surface over. What
    makes a tab a ghost is unmeasured, and a sentence that guessed would be the library
    inventing a diagnosis it has no evidence for.
    """
    return (f"Lark refused this tab (code {code}: {msg}) and the workbook read continued; "
            "larkdocio quotes Lark's own words and diagnoses no further.")
