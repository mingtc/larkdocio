"""``TabOutcome.reason`` — a one-property passthrough to ``skip.reason`` (LD-406).

A ``TabOutcome`` for a skipped tab keeps its human-facing sentence at
``outcome.skip.reason`` — one level deeper than every consumer reaches (`outcome.reason`),
forcing a ``getattr(o.skip, "reason", None)`` dance because ``skip`` is ``None`` on a read
outcome. This property closes that gap: additive, in the same idiom as
``SpreadsheetRead.reads``/``skips``, nothing renamed or removed.
"""
from larkdocio.sheets.extent import UsedRange
from larkdocio.sheets.models import SheetTab
from larkdocio.sheets.walk import TAB_READ, TAB_SKIPPED, TabOutcome, TabSkip


def _tab(sheet_id="444a1c", title="Types"):
    return SheetTab(sheet_id=sheet_id, title=title, index=0, row_count=10, column_count=5)


def _read_outcome():
    used = UsedRange(sheet_id="444a1c", a1_range="444a1c!A1:B2", revision=37,
                      values=[["Name", "Qty"], ["Widget", 3]])
    return TabOutcome(tab=_tab(), kind=TAB_READ, used=used)


def _skip_outcome(reason="Lark refused this tab (code 90215: not found sheetId)."):
    skip = TabSkip(sheet_id="gh0st1", title="Ghost A", code=90215, msg="not found sheetId",
                   reason=reason)
    return TabOutcome(tab=_tab(sheet_id="gh0st1", title="Ghost A"), kind=TAB_SKIPPED, skip=skip)


# --------------------------------------------------------------------------- #
# AC1/AC3 — both arms of the two-arm contract.                                #
# --------------------------------------------------------------------------- #

def test_a_READ_outcome_reason_is_None():
    """AC1. A tab that read has nothing to disclose — `.reason` is None, not an AttributeError
    and not a re-derivation of anything."""
    outcome = _read_outcome()

    assert outcome.reason is None


def test_a_SKIPPED_outcome_reason_is_the_EXACT_sentence_TabSkip_carries():
    """AC1/AC3. Identity, not a re-derivation: the property must not reformat, prefix or
    otherwise touch Lark-adjacent text."""
    sentence = "Lark refused this tab (code 90215: not found sheetId) and the workbook read continued."
    outcome = _skip_outcome(reason=sentence)

    assert outcome.reason is sentence
    assert outcome.reason == outcome.skip.reason


def test_the_deeper_spelling_KEEPS_WORKING_exactly_as_it_does_today():
    """AC1. Additive: nothing about `outcome.skip.reason` moves."""
    outcome = _skip_outcome()

    assert outcome.skip.reason == outcome.reason


# --------------------------------------------------------------------------- #
# AC3 — the arm that matters most in practice: iterating a whole SpreadsheetRead. #
# --------------------------------------------------------------------------- #

def test_iterating_a_SpreadsheetReads_outcomes_collects_None_for_reads_and_the_sentence_for_skips():
    """AC3. `[o.reason for o in book.outcomes]` — the one-line collection the consumer asked
    for, in place of the getattr dance."""
    from larkdocio.sheets.walk import SpreadsheetRead

    read = _read_outcome()
    skip = _skip_outcome(reason="Lark refused this tab (code 90215: not found sheetId).")
    book = SpreadsheetRead(spreadsheet_token="TOK", outcomes=[skip, read])

    assert [o.reason for o in book.outcomes] == [skip.skip.reason, None]
