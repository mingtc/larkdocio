# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""LD-274 — the LD-263 CHANGELOG bullet must cite `BASE.md` register row 28, not row 27.

Wave-1 pair LD-261 (row 27, the authorable-vs-writable quadrants) and LD-263 (row 28, the
no-`app.revision`-CAS disclosure) both appended one register row. LD-261 landed first and
took row 27; LD-263's merge-with-develop commit renumbered `BASE.md` itself and re-pinned
`_REGISTER_ROWS`, but the CHANGELOG prose citation was left pointing at row 27 — a row that
*exists*, so a bare "does this row number exist" guard would not have caught it. This test
instead pins the LD-263 bullet's own sentence to the row whose *content* it actually
describes (`NO_APP_REVISION_CAS` / the async-settle bullet), and separately guards LD-261's
row-27 citation against drifting the same way in the future.

A generic "every CHANGELOG row-citation resolves to *some* row in `BASE.md`" guard was
considered (LD-274's own suggested-fix section) and deliberately not built: it is existence
machinery for a defect class that is about *content*, not *range* — row 27 was always a
valid row number, just the wrong one. One targeted regression test per landed citation is
cheaper and more honest than a generic check that would have passed right through this bug.
"""
import pathlib

import pytest

import private_tree  # noqa: E402  (LD-691)

#: LD-691: every test here reads bullets of the INTERNAL engineering log (the root CHANGELOG.md;
#: the packaged copy is now the public changelog).
pytestmark = private_tree.internal_log

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ROOT_CHANGELOG = REPO_ROOT / "CHANGELOG.md"
PACKAGED_CHANGELOG = REPO_ROOT / "src" / "larkdocio" / "CHANGELOG.md"


#: The marker that locates the era these four citations were written in — the register rows they
#: cite sit in the same release sections as this string. Used to ask, per copy, whether the claim
#: is expected to be present at all.
_ERA_MARKER = "NO_APP_REVISION_CAS"


@pytest.fixture(params=[ROOT_CHANGELOG, PACKAGED_CHANGELOG], ids=["root", "packaged"])
def changelog_text(request):
    """The copy under test — or a skip, when the WINDOW no longer carries the era these citations
    were written in.

    **LD-540 — the window, and why this is asserted over a DERIVED set of copies.** The wheel
    now carries a recent-N window of each release document while the repository keeps the whole
    history, so "this claim is written down" and "this claim ships" stopped being one sentence.
    ``test_shipped_notes.notes_claim_copies`` answers which copies must carry it: the root
    always (a deletion from the authoring source reddens with full force), and the packaged
    window whenever it still holds the section — and if it does not, that helper PROVES the
    section is genuinely out of window rather than letting the claim go missing. Nothing was
    weakened and no copy was dropped by hand.

    Here that helper is used as the *precondition* rather than the loop, because this file's four
    tests each locate their own bullet by content: it is called for its assertions (the root copy
    carries the era; the packaged copy's silence is the window's doing and not a lost claim), and
    the ``packaged`` parametrization is skipped only once that has been PROVEN. The node id stays,
    the skip reason names the release span, and the ``root`` arm keeps every tooth these four
    tests ever had — which is where the citations are authored and therefore where a wrong row
    number is a defect.
    """
    from test_shipped_notes import notes_claim_copies

    carried = {label.split()[0] for label, _text in notes_claim_copies(
        "CHANGELOG.md", _ERA_MARKER)}
    text = request.param.read_text(encoding="utf-8")
    if request.param is PACKAGED_CHANGELOG and _ERA_MARKER not in text:
        assert carried == {"CHANGELOG.md"}, carried
        pytest.skip(
            "the packaged changelog carries a recent-N window and these register-row citations "
            "were written in a release that has rolled out of it; notes_claim_copies has "
            "verified the section is genuinely out of window rather than missing. The root copy "
            "— where the citations are authored — is still asserted in full."
        )
    return text


def test_ld263_bullet_cites_register_row_28_the_no_revision_guard_row(changelog_text):
    """The async-settle / `NO_APP_REVISION_CAS` sentence must cite row 28 (its real row)."""
    idx = changelog_text.index("NO_APP_REVISION_CAS")
    window = changelog_text[idx : idx + 900]
    assert "register **row 28**" in window, (
        "the LD-263 bullet's `NO_APP_REVISION_CAS` sentence must cite `BASE.md` register "
        "row 28 (the no-revision-guard row) — found stale/absent citation in:\n" + window
    )
    assert "register **row 27**" not in window, (
        "the LD-263 bullet still cites row 27 (LD-261's quadrant row), not its own row 28"
    )


def test_ld261_bullet_still_cites_register_row_27_the_quadrant_row(changelog_text):
    """LD-261's own bullet (the authorable-vs-writable quadrants) must keep citing row 27."""
    idx = changelog_text.index("authorable with unwritable cells")
    window = changelog_text[max(0, idx - 400) : idx + 200]
    assert "register **row 27**" in window, (
        "LD-261's bullet must cite `BASE.md` register row 27 (the quadrant row) — "
        "found:\n" + window
    )


def test_ld284_bullet_cites_register_row_40_and_its_REPROBE_CAPTURE(changelog_text):
    """LD-284 rewrote register row 40 on the strength of a live re-probe. The bullet is the
    only place a reader meets that rewrite without opening `BASE.md`, so it must name the row
    it changed **and** the capture that settled it — a rewrite whose evidence is unnameable is
    the same defect as the claim it replaced.
    """
    assert "LD-284" in changelog_text, "the LD-284 rewrite is not disclosed in the CHANGELOG"

    # LD-284 is named in more than one place — the disclosure bullet, and the one-clause
    # supersession marker on the LD-270 bullet that carried the falsified claim. The bullet is
    # whichever mention carries the citations, so every mention is tried rather than the first.
    windows = []
    at = changelog_text.find("LD-284")
    while at != -1:
        windows.append(changelog_text[max(0, at - 900): at + 3000])
        at = changelog_text.find("LD-284", at + 1)

    assert any("register **row 40**" in w for w in windows), (
        "the LD-284 bullet must cite `BASE.md` register row 40 (the computed-wrapper row) — "
        "found:\n" + windows[0]
    )
    assert any("ld284-01-copy-lookup-materialisation.json" in w for w in windows), (
        "the LD-284 bullet must name the re-probe capture that settled the evidence conflict"
    )


def test_the_LD270_bullet_that_carried_the_FALSIFIED_claim_is_marked_superseded(
        changelog_text):
    """The CHANGELOG is append-only, so LD-270's bullet still states the cell-less copy as a
    finding. It is shipped text (`src/larkdocio/CHANGELOG.md` rides in the wheel), and the
    correction lands ~500 lines further down, so the claim carries an inline pointer rather
    than waiting for a reader to keep scrolling."""
    idx = changelog_text.index("a **settled copy reads back with the Lookup's schema intact")
    window = changelog_text[idx: idx + 700]
    assert "superseded by LD-284" in window, (
        "the LD-270 bullet asserts the falsified cell-less copy with no pointer to the "
        "re-probe that superseded it — found:\n" + window
    )
