"""LD-324 AC8 — the Drive enumeration's permission rows, landed in the same change.

``tests/test_permissions_registry.py`` is bidirectional and reddens on an API-using call site
with no row, so these are not optional. What is asserted here is the part a coverage guard
cannot: **that the rows say the honest thing.**

Five Drive calls across three endpoint families answered ``code 0`` on the READ app with zero
grants — and that proves **reach**, not a requirement. Nothing distinguishes *"authorized by
the document-read scope the app already holds"* from *"authorized by a drive scope the app also
holds"*; and under this tenant's credential aliasing (the READ and WRITE pairs are one app with
byte-identical secrets) **a same-tenant success cannot attribute a scope at all.** So the two
new rows are **empty with the reason recorded** — the registry's own shape for *"no scope
string has ever been observed"* — and **no scope string is guessed**.
"""
import pathlib

import pytest

from larkdocio import permissions as perm

FILES_ROW = "/open-apis/drive/v1/files"
METAS_ROW = "/open-apis/drive/v1/metas/batch_query"
ROOT_META_ROW = "/open-apis/drive/explorer/v2/root_folder/meta"

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def row(prefix, mode="read"):
    for candidate, row_mode, scopes, reason in perm.ENDPOINT_SCOPES:
        if candidate == prefix and row_mode in (mode, "*"):
            return (candidate, row_mode, scopes, reason)
    return None


# --------------------------------------------------------------------------- #
# (i) the EXISTING listing row, extended to record the enumeration reads.       #
# --------------------------------------------------------------------------- #

def test_the_listing_row_still_exists_and_still_GUESSES_NOTHING():
    _prefix, mode, scopes, reason = row(FILES_ROW)
    assert mode == "*"
    assert scopes == (), "no drive scope has ever been observed demanded — none may be asserted"
    assert "not guessed" in reason


def test_the_listing_rows_note_now_records_the_ENUMERATION_READS_and_their_evidence():
    """The row predates this surface; the reads it now answers are new, and a note that did not
    mention them would leave the widest-reaching drive row describing only half its callers."""
    _prefix, _mode, _scopes, reason = row(FILES_ROW)
    assert "enumerat" in reason.lower()
    assert "READ" in reason
    assert "17" in reason or ("5" in reason and "12" in reason), (
        "the two probe rounds' own call counts are the evidence")
    assert "denial" in reason.lower()


# --------------------------------------------------------------------------- #
# (ii) + (iii) the TWO NEW rows.                                                #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("prefix,capture", [
    (METAS_ROW, "06-metas-batch-query.json"),
    (ROOT_META_ROW, "01-root-folder-meta.json"),
])
def test_each_new_row_exists_is_EMPTY_and_carries_its_capture(prefix, capture):
    entry = row(prefix)
    assert entry is not None, f"{prefix} has no row — the registry guard reddens on this"
    _prefix, _mode, scopes, reason = entry
    assert scopes == (), "an empty requirement is the honest shape; a guessed string is not"
    assert capture in reason
    assert (REPO_ROOT / "tests" / "captures" / "drive-spike" / "captures" / capture).exists()
    assert "not guessed" in reason or "deliberately not guessed" in reason


@pytest.mark.parametrize("prefix", [METAS_ROW, ROOT_META_ROW])
def test_each_new_row_states_the_NON_OBSERVATION_AS_SUCH(prefix):
    """Zero denials on this tenant distinguishes nothing, and the aliasing fact is why. A row
    that recorded only *"it worked"* would read as an answer."""
    _prefix, _mode, _scopes, reason = row(prefix)
    lowered = reason.lower()
    assert "alias" in lowered, "the READ/WRITE aliasing is why a same-tenant success proves nothing"
    assert "documented-unverified" in lowered
    assert "code 0" in lowered or "answered" in lowered


def test_the_root_folder_row_records_that_it_is_a_LEGACY_NON_SDK_family():
    _prefix, _mode, _scopes, reason = row(ROOT_META_ROW)
    assert "legacy" in reason.lower()
    assert "sdk" in reason.lower()


def test_the_query_POST_row_is_not_mistaken_for_a_WRITE():
    """``metas/batch_query`` is a POST that mutates nothing; a row filed under the write pair
    would quietly assert that reading a folder's title needs write credentials."""
    _prefix, mode, _scopes, _reason = row(METAS_ROW)
    assert mode in ("read", "*")


# --------------------------------------------------------------------------- #
# NO SCOPE IS WIDENED, REQUESTED OR ESCALATED.                                  #
# --------------------------------------------------------------------------- #

def test_NO_NEW_SCOPE_STRING_was_added_by_this_change():
    """The one drive scope this project has ever proven is ``drive:export``. This change adds
    none — the two new rows are empty, and the library never widens a scope."""
    drive_scopes = sorted({
        scope.scope
        for _prefix, _mode, scopes, _reason in perm.ENDPOINT_SCOPES
        for scope in scopes
        if scope.scope.startswith("drive:")
    })
    assert drive_scopes == ["drive:export"]


def test_the_new_rows_are_reachable_by_LONGEST_PREFIX_and_do_not_shadow_the_listing_row():
    """``/drive/v1/metas/batch_query`` must not be answered by the ``/drive/v1/files`` row, and
    the listing row must keep answering its own family."""
    assert perm._table_row(METAS_ROW, "read")[0] == METAS_ROW
    assert perm._table_row(ROOT_META_ROW, "read")[0] == ROOT_META_ROW
    assert perm._table_row(FILES_ROW, "read")[0] == FILES_ROW
    assert perm._table_row(f"{FILES_ROW}/:file_token/comments", "read")[0] != METAS_ROW
