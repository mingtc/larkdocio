"""The consumer permissions table is PASTE-READY — one row per scope, nothing repeated.

The generated consumer table exists so that nobody has to hand-write the list they send their
workspace administrator. A consumer did anyway: the *"what you lose"* column concatenated
several scopes' loss notes into one cell, and the resulting 90-word blob was repeated verbatim
in four rows of one table and five rows of the next. Accurate, and unreadable.

The fix is a shape change only: **one row per (surface, scope)**, with each scope's loss text
written **once** in a per-scope list below the tables. So the two halves guarded here are the
compaction *and* its anti-goal — a shorter table that dropped the honesty (a loss text, a
verification label, the credential pair, the field-level warning) would be a worse table than
the unreadable one.
"""
import re

import pytest

from larkdocio import capabilities, permissions as perm

# LD-370 — CONFORMANCE-tier: the shape of that list is what makes it usable by a workspace administrator.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance


#: Above this length, a repeated string is a paragraph a reader has to re-read, not a label.
LONG_ENOUGH_TO_BE_A_PARAGRAPH = 80

#: A cell wider than this stops being scannable in a plain Markdown viewer.
MAX_CELL_WIDTH = 120


def render():
    return perm.consumer_permissions_markdown()


def tables(text=None):
    """The rendered Markdown tables, each as a list of row-cell-lists (header/rule dropped)."""
    text = render() if text is None else text
    found, current = [], []
    for line in text.splitlines():
        if line.startswith("|"):
            current.append([cell.strip() for cell in line.strip("|").split("|")])
        elif current:
            found.append(current)
            current = []
    if current:
        found.append(current)
    return [rows[2:] for rows in found]  # drop the header row and its rule


def all_cells():
    return [cell for table in tables() for row in table for cell in row]


def surface_scope_pairs():
    """``{(surface_id, scope)}`` — every scope a surface asks for, from ``capabilities()``."""
    pairs = set()
    for surface_id, surface in capabilities(full=True)["surfaces"].items():
        creds = surface["credentials"]
        for scope in tuple(creds["scopes"]) + tuple(creds["optional_scopes"]):
            pairs.add((surface_id, scope))
    return pairs


def reachable_scopes():
    """Every ``Scope`` object a consumer-visible registry row references."""
    return {scope
            for row in perm.permission_registry().values()
            for scope in tuple(row.scopes) + tuple(row.optional_scopes)}


def registry_notes():
    return {scope.note for scope in reachable_scopes() if scope.note}


# --------------------------------------------------------------------------- #
# AC-C1 — one row per (surface, scope); no cell joins two scopes' notes.       #
# --------------------------------------------------------------------------- #

def test_the_surface_table_is_ONE_ROW_PER_SURFACE_AND_SCOPE():
    surface_table = tables()[0]
    rendered = set()
    for row in surface_table:
        surface_cell, scope_cell = row[0], row[2]
        scopes = re.findall(r"`([a-z][\w.:]*:[\w.:]+)`", scope_cell)
        if not scopes:
            continue  # a surface with no observed requirement still gets its row
        assert len(scopes) == 1, (
            f"{surface_cell} row names {len(scopes)} scopes in one row: {scopes}")
        rendered.add((surface_cell.strip("`"), scopes[0]))

    assert rendered == surface_scope_pairs(), (
        "the rendered rows are not exactly the (surface, scope) pairs "
        f"capabilities() reports; missing={surface_scope_pairs() - rendered}, "
        f"extra={rendered - surface_scope_pairs()}")


def test_NO_CELL_CONCATENATES_two_scopes_loss_notes():
    """The defect, stated directly: a cell carrying two scopes' notes semicolon-joined."""
    notes = registry_notes()
    for cell in all_cells():
        carried = [note for note in notes if note in cell]
        assert len(carried) <= 1, (
            f"one cell carries {len(carried)} scopes' loss notes: {cell[:160]!r}")


def test_every_row_of_every_table_names_AT_MOST_ONE_scope():
    """The per-call table gets the same treatment as the surface table — a row is one scope."""
    for index, table in enumerate(tables()):
        for row in table:
            for cell in row:
                scopes = re.findall(r"`([a-z][\w.]*:[\w.:]+)`", cell)
                assert len(scopes) <= 1, (
                    f"table {index} has a cell listing {len(scopes)} scopes: {cell[:120]!r}")


# --------------------------------------------------------------------------- #
# AC-C2 — no loss note repeated verbatim.                                     #
# --------------------------------------------------------------------------- #

def test_no_loss_NOTE_appears_more_than_once_in_the_whole_render():
    text = render()
    for note in registry_notes():
        if len(note) <= LONG_ENOUGH_TO_BE_A_PARAGRAPH:
            continue
        assert text.count(note) == 1, (
            f"a {len(note)}-character loss note is written {text.count(note)} times: "
            f"{note[:80]!r}")


def test_no_long_LINE_OR_CELL_is_written_twice():
    """The general form: nothing paragraph-length is duplicated anywhere in the render."""
    chunks = [chunk for chunk in all_cells() if len(chunk) > LONG_ENOUGH_TO_BE_A_PARAGRAPH]
    chunks += [line.strip() for line in render().splitlines()
               if line.strip().startswith(("-", "*")) and len(line) > 60]
    duplicated = {chunk for chunk in chunks if chunks.count(chunk) > 1}
    assert not duplicated, (
        f"{len(duplicated)} paragraph-length string(s) written more than once: "
        + "; ".join(sorted(chunk[:70] for chunk in duplicated)))


# --------------------------------------------------------------------------- #
# AC-C3 — THE ANTI-GOAL. Nothing is lost in the compaction.                    #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("scope", sorted(reachable_scopes(), key=lambda s: (s.scope, s.note or "")))
def test_every_scopes_LOSS_TEXT_survives_the_compaction(scope):
    text = render()
    assert f"`{scope.scope}`" in text, f"{scope.scope} is not named at all"
    if scope.note:
        assert scope.note in text, (
            f"{scope.scope}'s loss text was dropped by the compaction: {scope.note[:70]!r}")


def test_every_scopes_VERIFICATION_LABEL_survives_including_documented_unverified():
    text = render()
    labels = {scope.verification for scope in reachable_scopes()}
    assert "documented-unverified" in labels, (
        "the registry no longer carries a documented-unverified scope — this test's premise")
    for label in labels:
        assert label in text, f"the verification label {label!r} is not in the rendered table"


def test_the_CREDENTIAL_PAIR_still_says_which_app_a_scope_is_asked_for():
    text = render()
    for surface in capabilities(full=True)["surfaces"].values():
        creds = surface["credentials"]
        for env_var in creds["env_primary"]:
            assert f"`{env_var}`" in text, f"the credential pair lost {env_var}"
        assert f"{creds['app'].upper()} app" in text


def test_the_FIELD_LEVEL_grant_warning_survives_in_full():
    """The five-day shape. A compaction that lost this would be a worse table."""
    text = render()
    field_level = sorted({scope.scope for scope in reachable_scopes() if scope.field_level})
    assert field_level
    for scope in field_level:
        assert f"`{scope}`" in text
    assert "FIELD-level" in text
    assert "there is no such user" in text


# --------------------------------------------------------------------------- #
# AC-C5 — paste-ready: measured, not asserted to "look better".               #
# --------------------------------------------------------------------------- #

def test_NO_CELL_is_wider_than_a_plain_markdown_viewer_can_show():
    widest = max(all_cells(), key=len)
    assert len(widest) <= MAX_CELL_WIDTH, (
        f"the widest cell is {len(widest)} characters, over the {MAX_CELL_WIDTH} ceiling: "
        f"{widest[:160]!r}")


def test_the_render_is_measurably_flatter_than_the_shape_that_was_hand_rewritten():
    """The measured baseline: a 91-word cell repeated four times, an 8× 21-word cell."""
    cells = all_cells()
    assert max(len(cell.split()) for cell in cells) <= 20, (
        "a cell is still paragraph-shaped")
    assert not [cell for cell in cells
                if len(cell.split()) > 12 and cells.count(cell) > 1], (
        "a multi-clause cell is still repeated across rows")
