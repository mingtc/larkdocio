"""Graceful degradation, the observed error table, and the spreadsheet leg.

**The posture being pinned.** A comments read that fails must not come back as "this file has
no comments". Those are different answers and only one of them is true, so the result says the
comment knowledge is unavailable and why — while the document's own content, which was read
by a different call entirely, is untouched. A note that lies is worse than no note.

Every code in the table gets its own injected failure and its own disclosure assertion,
because a table with one exercised row is a list, not a behaviour.

The spreadsheet arms pin the asymmetry the API really has — a read is accepted on a
spreadsheet token where a create is refused at the file-type list — and pin that a
spreadsheet comment is never presented as attached to a cell, however much its quoted text
looks like one.
"""
import comments_harness as harness
import comments_payloads as payloads
import pytest

from larkdocio.comments import (
    COMMENT_ERROR_CODES,
    FILE_TYPE_SHEET,
    SHEETS_NO_CELL_ANCHOR_NOTE,
    SHEETS_READ_ACCEPTED_CREATE_REJECTED_NOTE,
    Comment,
    comments,
)
from larkdocio.comments.read import UNAVAILABLE_NOTE
from larkdocio.model import PageNode, Text, TextNode

_ITEM = payloads.LIST_ONE_PAGE["data"]["items"][0]


def _anchored_root(*ids):
    return PageNode(title=[Text("Doc")], children=[
        TextNode(content=[Text("x")], block_id="b1", comment_ids=list(ids))])


# --------------------------------------------------------------------------- #
# AC9 — one injected failure per observed code, each disclosed.                  #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("code", sorted(COMMENT_ERROR_CODES))
def test_every_observed_code_degrades_gracefully_and_DISCLOSES_the_absence(code):
    client = harness.client({"list": harness.error_body(code, "server said so")})

    result = comments("doc-token", client=client)

    assert result.available is False, f"code {code} was smoothed over into a success"
    assert result.comments == ()
    assert result.unavailable_code == code
    assert COMMENT_ERROR_CODES[code] in result.unavailable_reason
    assert str(code) in result.unavailable_reason
    assert UNAVAILABLE_NOTE in result.notes
    # The disclosure is a sentence a caller can relay as-is.
    assert "unavailable" in result.disclosure.lower()
    assert "NO comment knowledge" in result.disclosure


@pytest.mark.parametrize("code", sorted(COMMENT_ERROR_CODES))
def test_a_failure_NEVER_raises_out_of_the_read(code):
    """The document read must survive a comments failure — so this call cannot throw."""
    client = harness.client({"batch_query": harness.error_body(code)})
    result = comments("doc-token", root=_anchored_root("c1"), client=client)
    assert result.available is False


def test_an_UNKNOWN_code_is_reported_with_its_number_and_the_servers_own_message():
    """Never dressed up as something understood."""
    client = harness.client({"list": harness.error_body(1234567, "brand new failure")})

    result = comments("doc-token", client=client)

    assert result.available is False
    assert result.unavailable_code == 1234567
    assert "1234567" in result.unavailable_reason
    assert "brand new failure" in result.unavailable_reason


def test_zero_comments_FOUND_is_a_DIFFERENT_answer_from_could_not_find_out():
    """The discriminator that makes the whole posture meaningful."""
    empty = {"code": 0, "msg": "Success",
             "data": {"items": [], "has_more": False, "page_token": "0"}}
    found_none = comments("doc-token", client=harness.client({"list": empty}))
    could_not = comments(
        "doc-token", client=harness.client({"list": harness.error_body(1069304)}))

    assert (found_none.available, found_none.comments) == (True, ())
    assert (could_not.available, could_not.comments) == (False, ())
    assert found_none != could_not
    assert "found none" in found_none.disclosure
    assert found_none.unavailable_reason is None
    assert could_not.unavailable_reason


def test_a_failed_batch_reports_every_requested_anchor_as_missing():
    """A batch rejected for one malformed id returns nothing at all — so no anchor may be
    reported as resolved."""
    client = harness.client({"batch_query": harness.error_body(9499, "bad id")})

    result = comments("doc-token", root=_anchored_root("c1", "c2"), client=client)

    assert result.requested_ids == ("c1", "c2")
    assert result.missing_ids == ("c1", "c2")
    assert result.comments == ()
    assert "whole batch" in result.unavailable_reason


def test_the_failure_is_countable_and_the_call_really_happened():
    client = harness.client({"list": harness.error_body(1069307)})
    result = comments("doc-token", client=client)
    assert result.api_calls == 1, "a failed call still cost a call, and says so"


def test_the_error_table_covers_exactly_the_codes_the_surface_has_seen():
    """Bidirectional against the issue's own observed set — a code added to the table without
    having been seen, or a seen code left out, is a drift in the disclosure."""
    assert set(COMMENT_ERROR_CODES) == {
        1069301, 1069302, 1069304, 1069307, 9499, 41050, 99992402}
    for code, meaning in COMMENT_ERROR_CODES.items():
        assert meaning and meaning[0].islower(), (
            f"code {code}'s meaning must read as a clause inside a sentence")


def test_the_captured_error_bodies_carry_the_codes_the_table_names():
    """The table is not a list of numbers someone remembered — these are the captures."""
    seen = {
        payloads.BATCH_QUERY_MALFORMED_ID["code"],
        payloads.GET_ONE_GONE["code"],
        payloads.PATCH_SOLVED_VANISHED["code"],
        payloads.EMPTY_REPLY_CONTENT["code"],
        payloads.CONTACT_RESOLVE_DENIED["code"],
        payloads.SHEETS_CREATE_ENUM_REJECTED["code"],
        payloads.LIST_ON_DELETED_FILE["code"],
    }
    assert seen == set(COMMENT_ERROR_CODES)


# --------------------------------------------------------------------------- #
# AC8 — the spreadsheet leg.                                                    #
# --------------------------------------------------------------------------- #

def test_a_spreadsheet_read_is_supported_and_sends_the_spreadsheet_file_type():
    client = harness.client({"list": payloads.SHEETS_LIST_ACCEPTED})

    result = comments("sheet-token", file_type=FILE_TYPE_SHEET, client=client)

    assert result.available is True
    assert client._sdk.requests_for("list")[0].file_type == "sheet"
    assert result.file_type == "sheet"


def test_the_captured_spreadsheet_read_really_succeeded_where_the_create_was_refused():
    """The asymmetry, straight off the captures — the same token, read accepted, create
    refused at the file-type list, and the wrong file type refused on the read too."""
    assert payloads.SHEETS_LIST_ACCEPTED["code"] == 0
    assert payloads.SHEETS_CREATE_ENUM_REJECTED["code"] == 99992402
    violation = payloads.SHEETS_CREATE_ENUM_REJECTED["error"]["field_violations"][0]
    assert violation["field"] == "file_type"
    assert violation["description"] == "file_type is optional, options: [doc,docx]"
    assert payloads.SHEETS_LIST_WRONG_FILE_TYPE["code"] == 1069307


def test_a_spreadsheet_read_DISCLOSES_both_the_asymmetry_and_the_missing_cell_anchor():
    client = harness.client({"list": payloads.SHEETS_LIST_ACCEPTED})
    result = comments("sheet-token", file_type=FILE_TYPE_SHEET, client=client)

    assert SHEETS_READ_ACCEPTED_CREATE_REJECTED_NOTE in result.notes
    assert SHEETS_NO_CELL_ANCHOR_NOTE in result.notes
    assert "CREATING one on a" in result.disclosure
    assert "no structured cell reference" in result.disclosure


def test_a_document_read_carries_NEITHER_spreadsheet_note():
    client = harness.client({"list": payloads.LIST_ONE_PAGE})
    result = comments("doc-token", client=client)
    assert SHEETS_READ_ACCEPTED_CREATE_REJECTED_NOTE not in result.notes
    assert SHEETS_NO_CELL_ANCHOR_NOTE not in result.notes


def test_a_cell_LOOKING_quote_is_NOT_turned_into_a_cell_anchor():
    """The trap the disclosure exists for: a quote of ``C3`` is text the server chose, and
    nothing here promotes it to a coordinate."""
    body = {"code": 0, "msg": "Success", "data": {
        "items": [dict(_ITEM, comment_id="c-sheet", quote="C3", is_whole=False)],
        "has_more": False, "page_token": "0"}}
    client = harness.client({"list": body})

    result = comments("sheet-token", file_type=FILE_TYPE_SHEET, client=client)
    comment = result.comments[0]

    assert comment.quote == "C3", "the quote is reported verbatim"
    for fabricated in ("cell", "cell_ref", "a1", "range", "row", "column", "coordinate"):
        assert fabricated not in Comment.__dataclass_fields__, (
            f"{fabricated!r} would present a spreadsheet comment as cell-anchored")
        assert fabricated not in comment.to_dict()
    assert SHEETS_NO_CELL_ANCHOR_NOTE in result.notes


def test_a_spreadsheet_failure_keeps_the_spreadsheet_notes_alongside_the_reason():
    client = harness.client({"list": harness.error_body(99992402, "field validation failed")})
    result = comments("sheet-token", file_type=FILE_TYPE_SHEET, client=client)

    assert result.available is False
    assert UNAVAILABLE_NOTE in result.notes
    assert SHEETS_READ_ACCEPTED_CREATE_REJECTED_NOTE in result.notes
