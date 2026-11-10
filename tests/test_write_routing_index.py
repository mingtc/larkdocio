"""LD-422 — THE ROUTING CONTRACT for the guide's write chapter.

A consumer followed this library's own prescribed discovery order and hand-rolled a
**destructive** equivalent of a function the wheel exports. The documentation was complete;
the **routing** failed. The findings this module pins, each as a measured property of the
shipped index rather than a reading of the prose:

* the reconciliation recipe is reachable by the words a consumer actually types —
  **update**, **change**, **edit**, applied to an **existing** document (D-60: a recipe is
  named after the failure it cures, and ``guide_sections()`` indexes **names only**, on
  purpose);
* the report's own failing scan — a heading scan filtered on ``write|author|insert|markdown``
  — now **includes** the recipe it measured absent;
* the write chapter opens with a **task decision list** that is itself reachable through the
  index, and **every row names a heading that exists** and that ``guide(section=...)``
  returns (a dangling cross-link in a routing fix is the same defect one level down);
* the two entry recipes and the object-level "change a document" recipe **cross-link** to the
  reconciliation recipe;
* the **comment-anchor consequence** — block ids are what comments anchor to — is authored
  once and projected byte-identically to every surface that carries it.

These pin the PRODUCT (what a consumer can find), not this implementation of it, so the
module is conformance-marked.
"""

import re

import pytest

import larkdocio
from larkdocio.comments import BLOCK_ID_COMMENT_ANCHOR_CONSEQUENCE

pytestmark = pytest.mark.conformance


#: The reconciliation recipe's slug after LD-422's D-60 retitle. The heading is illustrative
#: prose; THIS is the contract, because it is what a consumer's search reaches.
RECONCILE_SLUG = (
    "recipe-update-an-existing-document-change-or-edit-many-blocks-at-once-without-re-authoring-it"
)

#: The task decision list at the write chapter head (AC4) — reachable in its own right.
DECISION_LIST_SLUG = (
    "which-write-recipe-do-you-need-add-change-update-or-delete-content-in-a-document"
)

#: The canonical "copy this" end-to-end update script (AC8).
COPY_THIS_SLUG = "recipe-copy-this-the-end-to-end-update-script-from-url-to-applied-edit"

#: The two entry recipes that pointed nowhere (finding 5) and the object-level recipe that
#: claimed the "change something" query without naming the alternative (finding 4).
ENTRY_SLUGS = (
    "recipe-write-into-an-empty-document",
    "recipe-author-a-markdown-fragment-into-a-document",
)
OBJECT_LEVEL_SLUG = "recipe-change-a-document-at-the-object-level-no-markdown-anywhere"


def _flat(text):
    """``text`` with every run of whitespace collapsed to one space.

    The guide is hard-wrapped at ~95 columns, so a cross-link sentence naming a long heading
    is split across lines in the source. Wrapping is a typesetting fact, not a routing one —
    what a consumer follows is the words. (The one thing NOT normalized is the projected
    comment-anchor sentence: that is pinned byte-identically, on purpose.)"""
    return " ".join(text.split())


def _sections():
    return larkdocio.guide_sections()


def _row(slug):
    for row in _sections():
        if row["slug"] == slug:
            return row
    raise AssertionError(
        f"no guide section with slug {slug!r}; the index has "
        f"{[r['slug'] for r in _sections()]}")


# --------------------------------------------------------------------------- #
# AC3 — the task keywords are MEASURED to hit through the section index.        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("keyword", ["update", "change", "edit", "existing"])
def test_the_reconciliation_recipe_is_reachable_by_the_task_words(keyword):
    """AC3: a consumer searching the index for the word they actually type reaches the
    recipe. The scan is over **headings**, because that is all the index carries."""
    hits = [row for row in _sections() if keyword in row["heading"].lower()
            and row["slug"] == RECONCILE_SLUG]
    assert hits, (
        f"the task word {keyword!r} does not reach the reconciliation recipe; its heading is "
        f"{_row(RECONCILE_SLUG)['heading']!r}")


def test_the_task_words_reach_the_recipe_together_not_one_at_a_time():
    """AC3: all four words on ONE heading — a consumer types a phrase, not a token."""
    heading = _row(RECONCILE_SLUG)["heading"].lower()
    missing = [w for w in ("update", "change", "edit", "existing") if w not in heading]
    assert not missing, f"heading {heading!r} misses {missing}"


def test_the_named_section_returns_the_recipes_own_body_not_merely_a_heading():
    """AC3: ``guide(section=...)`` on the task name returns the RECIPE, asserted on a phrase
    from its **body** — so a heading that merely carries the words cannot pass."""
    for name in (RECONCILE_SLUG, _row(RECONCILE_SLUG)["heading"]):
        body = larkdocio.guide(section=name)
        assert "reconcile()" in body, body[:400]
        assert "compile_reconciliation()" in body, body[:400]
        assert "conserved-block-re-created" in body, body[:400]


def test_the_reports_own_failing_scan_now_finds_the_recipe():
    """AC3 (the regression): the consumer's reproduce block was a heading scan over
    ``guide_sections()`` filtered on ``write|author|insert|markdown``. It missed the
    reconciliation recipe entirely — that miss is the whole report. It must now hit."""
    pattern = re.compile(r"write|author|insert|markdown", re.IGNORECASE)
    hits = [row["slug"] for row in _sections() if pattern.search(row["heading"])]
    assert RECONCILE_SLUG in hits, (
        "the report's own scan still misses the reconciliation recipe; it returned " + repr(hits))


# --------------------------------------------------------------------------- #
# AC4 — the task decision list, reachable, with every row routing somewhere real.#
# --------------------------------------------------------------------------- #

#: (the row's task question, the slug it must route to). The consumer's own six plus the
#: single-block / whole-document split the seat ruled.
DECISION_ROWS = (
    ("empty document", "recipe-write-into-an-empty-document"),
    ("add to an existing document", "recipe-author-a-markdown-fragment-into-a-document"),
    ("change an existing document — a single known block", OBJECT_LEVEL_SLUG),
    ("change an existing document — the whole document / many blocks", RECONCILE_SLUG),
    ("delete content", "recipe-the-docx-write-handshake"),
    ("change a diagram", "recipe-author-a-mermaid-diagram-and-change-one"),
    ("fix a table", "recipe-the-docx-write-handshake"),
    # LD-569 — the two rows the round measured consumers arriving for. Each routes to what
    # actually works today, because the gated route works for neither: the checkbox row to the
    # object-level recipe (create in the wanted state, or delete-and-recreate at the cost of a
    # block id), the table-grow row to the handshake (author the table again and delete the
    # old one). Enrolled here so they are guarded like every other row rather than shipping as
    # prose nothing reads.
    ("change a checkbox", OBJECT_LEVEL_SLUG),
    # LD-575 moved the table-grow row's destination, and only its destination: the gated
    # route now exists, so the row points at the recipe that performs the append instead of at
    # the handshake it used to send a caller to for author-again-and-delete. The row COUNT is
    # untouched (14).
    ("add or remove a table row", "recipe-add-a-row-to-a-table-that-already-exists"),
)


def test_the_decision_list_is_reachable_through_the_index():
    """AC4: a decision list buried inside another section's body is unreachable by the
    index — which is the exact failure D-60 names. It gets its own heading."""
    row = _row(DECISION_LIST_SLUG)
    assert row["level"] == 3, row
    heading = row["heading"].lower()
    for word in ("write", "change", "update", "delete"):
        assert word in heading, f"the decision list's heading must carry {word!r}: {heading!r}"


def test_every_decision_row_names_a_recipe_that_exists_and_resolves():
    """AC4/AC5/AC6: every row names its recipe **by that recipe's own heading**, the heading
    exists in the index, and ``guide(section=...)`` returns it. A dangling cross-link in a
    routing fix is a defect, not a nit."""
    body = _flat(larkdocio.guide(section=DECISION_LIST_SLUG))
    for task, slug in DECISION_ROWS:
        heading = _row(slug)["heading"]
        assert _flat(heading) in body, f"the {task!r} row does not name {heading!r}:\n{body}"
        assert larkdocio.guide(section=heading).startswith("### " + heading)


def test_the_decision_list_covers_every_task_the_consumer_named():
    """AC4: the seven rows, each recognisable by its own task words."""
    body = larkdocio.guide(section=DECISION_LIST_SLUG).lower()
    for task, _slug in DECISION_ROWS:
        head = task.split("—")[0].strip()
        assert head in body, f"the decision list has no row for {head!r}"


# --------------------------------------------------------------------------- #
# AC5 / AC6 — the cross-links, each pointing at the POST-RENAME heading.        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("slug", ENTRY_SLUGS)
def test_each_entry_recipe_points_at_the_reconciliation_recipe(slug):
    """AC5: *"One line in each would have prevented this entire report."*"""
    body = _flat(larkdocio.guide(section=slug))
    heading = _row(RECONCILE_SLUG)["heading"]
    assert _flat(heading) in body, f"{slug!r} never names {heading!r}:\n{body[:1200]}"
    assert "do not re-author it" in body.lower(), body[:1200]


def test_the_object_level_recipe_names_the_alternative_it_compares_against():
    """AC6: the recipe claimed the *"change something"* query and never named
    ``reconcile``. Its own claims are true and stay — the defect is the MISSING sentence."""
    body = _flat(larkdocio.guide(section=OBJECT_LEVEL_SLUG))
    assert _flat(_row(RECONCILE_SLUG)["heading"]) in body, body[:1200]
    assert "reconcil" in body.lower(), body[:1200]


def test_the_object_level_recipes_true_comparison_paragraph_is_intact():
    """AC6: a worker who "balances" the comparison by weakening a true statement has made
    the guide less accurate to make it friendlier. These three claims stay verbatim."""
    body = _flat(larkdocio.guide(section=OBJECT_LEVEL_SLUG))
    assert (
        "Three things it demonstrates that the projection cannot do. The block is found by "
        "walking the tree, so you are matching the block's **own** text, not "
        "escaped-and-normalized text. The target is the block's **own `block_id`**, so "
        "nothing has to be re-quoted and a repeated sentence is not ambiguous. And the "
        "review anchors printed alongside it are simply *there* on the node — the "
        "projection would have dropped them."
    ) in body, body[:2000]


# --------------------------------------------------------------------------- #
# AC7 — the comment-anchor consequence: authored ONCE, projected everywhere.    #
# --------------------------------------------------------------------------- #

def test_the_comment_anchor_consequence_states_the_join_the_library_ships():
    """AC7: the sentence names the consequence AND the join that proves it, because that
    join is why this library knows this better than its consumers do."""
    text = BLOCK_ID_COMMENT_ANCHOR_CONSEQUENCE
    assert "block ids" in text.lower() and "comment" in text.lower(), text
    assert "for_node" in text, text
    # Consumer dialect only — no internal pointer of any kind.
    assert "LD-" not in text and "dev/" not in text and "tests/" not in text, text


def test_the_comment_anchor_consequence_is_byte_identical_on_every_surface():
    """AC7: one authored sentence, projected — the guard is what stops one copy drifting.

    A **guarded literal** (not a splice) is the mechanism: ``GUIDE.md`` and
    ``write/README.md`` are static shipped documents that cannot import a constant, so the
    constant is the single authored source and this test pins each copy against it."""
    guide = larkdocio.guide(full=True)
    brief = larkdocio.writer_brief()
    assert guide.count(BLOCK_ID_COMMENT_ANCHOR_CONSEQUENCE) >= 2, (
        "the consequence must land in the write chapter AND beside the block-id cache "
        f"warning: found {guide.count(BLOCK_ID_COMMENT_ANCHOR_CONSEQUENCE)}")
    assert BLOCK_ID_COMMENT_ANCHOR_CONSEQUENCE in brief, (
        "the writer brief carries the same block-id cache warning and must carry the same "
        "consequence")


def test_the_consequence_sits_where_the_block_id_cache_warning_already_lives():
    """AC7: the projection targets are the two places that already warn about a block id
    not surviving an edit — the consequence belongs beside its cause."""
    diagram = larkdocio.guide(section="recipe-author-a-mermaid-diagram-and-change-one")
    assert "Do not cache a diagram's `block_id` across an edit" in _flat(diagram)
    assert BLOCK_ID_COMMENT_ANCHOR_CONSEQUENCE in diagram, diagram[:2000]


# --------------------------------------------------------------------------- #
# AC1 — the future-release section is gone, and no roadmap prose replaced it.   #
# --------------------------------------------------------------------------- #

def test_the_guide_promises_no_editable_markdown_projection_it_already_ships():
    """AC1: the section asserted a shipped capability had NOT shipped. Deleted outright —
    not softened, not rewritten to "this has now landed". Its reason (*the tree stays the
    source of truth*) survives in the recipe that does the job."""
    assert "a-future-release-may-add-an-editable-markdown-projection" not in [
        row["slug"] for row in _sections()]
    assert "A future release may add" not in larkdocio.guide(full=True)


def test_the_write_chapters_forward_looking_census_is_empty_where_it_was_swept():
    """AC1: the swept phrases carry no roadmap claim in the reconciliation region."""
    for slug in (RECONCILE_SLUG, DECISION_LIST_SLUG, COPY_THIS_SLUG, OBJECT_LEVEL_SLUG):
        body = larkdocio.guide(section=slug).lower()
        for phrase in ("future release", "may add", "a future rung", "does not ship today"):
            assert phrase not in body, f"{slug!r} carries roadmap prose: {phrase!r}"


# --------------------------------------------------------------------------- #
# AC8 — the canonical "copy this" script, with the preamble in the named order. #
# --------------------------------------------------------------------------- #

def _copy_this_code():
    """The copy-this recipe's python fence — the *steps*, with the import block and the
    surrounding prose left out, because the ORDER is a property of the steps."""
    body = larkdocio.guide(section=COPY_THIS_SLUG)
    fence = re.search(r"```python\n(.*?)```", body, re.DOTALL)
    assert fence, "the copy-this recipe carries no python fence"
    code = fence.group(1)
    return code[code.index('init_env(".env")'):]


def test_the_copy_this_script_ships_as_a_real_recipe():
    """AC8: the most-repeated boilerplate, once, presented as "copy this"."""
    row = _row(COPY_THIS_SLUG)
    assert row["heading"].startswith("Recipe:"), row
    assert "copy this" in row["heading"].lower(), row


def test_the_copy_this_script_covers_the_named_preamble_in_order():
    """AC8: url → token (with the wiki hop) → read → parse → project_block_ids → edit →
    reconcile → dry_run → apply. In that order, because the order is the boilerplate."""
    body = _copy_this_code()
    steps = [
        "validate_download_url",
        "get_wiki_node_info",
        "get_docx_content",
        "parse_docx_tree",
        "project_block_ids",
        "reconcile(",
        "compile_reconciliation(",
        "dry_run(",
        "apply(",
    ]
    at = -1
    for step in steps:
        found = body.find(step, at + 1)
        assert found > at, f"{step!r} is missing or out of order in the copy-this script"
        at = found


def test_the_copy_this_script_keeps_the_plan_gate():
    """AC8: the plan gate *"caught two mistakes"* for the reporting consumer. A copy-this
    script that skipped ``dry_run`` would ship the wrong habit to every consumer at once."""
    body = larkdocio.guide(section=COPY_THIS_SLUG)
    assert "dry_run(" in body and "plan.ok" in body, body
