"""Section-level access to the shipped consumer guide — ``guide(section=...)``.

**Why this exists.** ``larkdocio.guide()`` returns one string, and that string is now over
200 KB. An agent consumer that wants the sheet-read recipe took the whole document into its
context to find it. This suite holds the section access that fixes that, and — more
importantly — holds the *derivation*: the sections are the guide's **own headings**, parsed out
of the packaged document at call time, so there is no list of section names anywhere in ``src/``
to fall out of date. That is the same posture ``capabilities._docx_block_read_support()`` states
in its own docstring — *"A join, not a list"*.

**The two proofs that matter most.**

* **Reassembly** — the preamble plus every ``##`` section, concatenated, is **byte-identical**
  to ``guide()``. It turns "the slicer looks right" into "the slicer provably loses nothing",
  and it stays true as the guide grows.
* **The derivation is proved by editing the DOCUMENT, not the code** — a copy of the package
  tree with one extra heading appended to its ``GUIDE.md`` gains that section in the index, in
  the ``capabilities()`` field and in the slicer, with **zero** code change, in a subprocess
  that imports the copy rather than the repo.

**Fence-awareness is not a nicety here.** The guide carries dozens of fenced blocks whose
Python is full of ``#``-prefixed comment lines, so a naive scan for ``^#`` finds several times
as many "headings" as the document really has. This suite cross-checks the shipped index against
a **second, independent** fence-aware reading written here, and against the naive count it must
not equal.
"""
import ast
import json
import pathlib
import re
import shutil
import subprocess
import sys
import zipfile

import pytest

import larkdocio
from larkdocio import capabilities, guide
from larkdocio.guide import GUIDE_SECTION_LEVELS, _section_index, guide_sections
from test_index_ratio import is_index_sized  # LD-640 AC5: one spelling of the 20x ratio

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"


# --------------------------------------------------------------------------- #
# A SECOND, INDEPENDENT fence-aware reading of the document — the cross-check.  #
# --------------------------------------------------------------------------- #

def _module():
    """The ``larkdocio.guide`` MODULE.

    Not ``import larkdocio.guide as m`` — that binds the accessor **function**, because the
    package re-exports it under the module's own name. This is the shadowing trap the
    ``guide_sections`` export decision turns on, and it bites a test the same way it bites a
    consumer, so every test that needs the module resolves it through ``sys.modules``.
    """
    return sys.modules["larkdocio.guide"]


def _independent_headings(text):
    """``[(level, heading)]`` for every ATX heading OUTSIDE a fenced block.

    Deliberately a different implementation from the shipped one (line list + a two-state
    machine, no offsets), so agreement between the two is evidence rather than a tautology.
    """
    out = []
    open_delim = None
    for line in text.split("\n"):
        fence = re.match(r"^(`{3,}|~{3,})(.*)$", line)
        if fence:
            run, info = fence.groups()
            if open_delim is None:
                open_delim = run
            elif run[0] == open_delim[0] and len(run) >= len(open_delim) and not info.strip():
                open_delim = None
            continue
        if open_delim is not None:
            continue
        heading = re.match(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", line)
        if heading:
            out.append((len(heading.group(1)), heading.group(2)))
    return out


def _naive_headings(text):
    """Every ``^#``-prefixed line, fence-blind — the wrong answer, kept to measure the gap."""
    return [line for line in text.split("\n") if re.match(r"^#{1,6}[ \t]+\S", line)]


def _slug(heading):
    """The slug rule, restated here so the shipped rule is checked against a second copy."""
    return re.sub(r"[^0-9a-zA-Z]+", "-", heading.replace("`", "").lower()).strip("-")


@pytest.fixture(scope="module")
def text():
    return guide(full=True)


@pytest.fixture(scope="module")
def rows():
    return guide_sections()


def _headings(rows):
    return [r["heading"] for r in rows]


def _slugs(rows):
    return [r["slug"] for r in rows]


# --------------------------------------------------------------------------- #
# AC1 — the no-argument call is BYTE-IDENTICAL to the packaged resource.        #
# --------------------------------------------------------------------------- #

def test_ac1_guide_with_FULL_is_the_packaged_resource_verbatim():
    """AC1: not "equivalent" — the same bytes the wheel carries, read straight through
    ``importlib.resources``, with the section machinery in the module and not in the way.

    **Transformed, not deleted (the front-door swap).** This assertion used to ride on the
    NO-ARGUMENT call; the document moved behind ``full=True`` and the claim moved with it. The
    reason it exists is unchanged: the whole document must come back byte-exact, from the
    packaged resource, with nothing in between."""
    import importlib.resources as resources

    from larkdocio.guide import GUIDE_RESOURCE

    packaged = resources.files("larkdocio").joinpath(GUIDE_RESOURCE).read_text(encoding="utf-8")
    assert guide(full=True) == packaged
    assert guide(full=True).encode("utf-8") == packaged.encode("utf-8")


def test_ac1_the_section_parameter_is_optional_and_keyword_capable():
    """AC1: ``section`` is optional and can be passed by keyword — the spelling every consumer
    document teaches. **What its default MEANS changed** (the front-door swap): omitting it
    used to mean *the whole document* and now means *the index of what can be named*, with the
    document behind ``full=True``. The optionality and the keyword-capability are what this
    test has always pinned, and both still hold."""
    import inspect

    signature = inspect.signature(guide)
    assert list(signature.parameters) == ["section", "full"]
    parameter = signature.parameters["section"]
    assert parameter.default is None
    assert parameter.kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY,
    )
    assert guide(section=None) == guide()
    assert guide(section=None, full=True) == guide(full=True)


def test_ac1_the_WHOLE_DOCUMENT_path_does_not_route_through_the_section_machinery(text):
    """AC1's explicit-equality half: the whole-document answer is the resource read, so no
    slicing, joining or normalization sits between the file and the caller. Proved by making
    the index raise: the ``full=True`` call must be untouched by that. (Before the front-door
    swap the untouched call was the no-argument one; the claim followed the document.)"""
    guide_module = _module()

    def exploding(_text, *_args, **_kwargs):
        # LD-414: `_bounded_sections` grew a `levels` parameter so a second document can
        # reuse it, so the fake has to accept (and ignore) it too.
        raise AssertionError("guide() with no section must not build the section index")

    original = guide_module._bounded_sections
    guide_module._bounded_sections = exploding
    try:
        assert guide(full=True) == text
    finally:
        guide_module._bounded_sections = original
    # and the same machinery IS what the section path uses, so the probe above is not vacuous
    guide_module._bounded_sections = exploding
    try:
        with pytest.raises(AssertionError):
            guide(section="anything")
    finally:
        guide_module._bounded_sections = original


# --------------------------------------------------------------------------- #
# AC2 — the boundary rule, pinned case by case, and the reassembly proof.      #
# --------------------------------------------------------------------------- #

def test_ac2_the_index_covers_the_two_documented_levels(rows):
    assert GUIDE_SECTION_LEVELS == (2, 3)
    assert {r["level"] for r in rows} == {2, 3}


def test_ac2_the_index_is_every_level_2_and_3_heading_in_document_order(text, rows):
    expected = [(lv, h) for lv, h in _independent_headings(text) if lv in (2, 3)]
    assert [(r["level"], r["heading"]) for r in rows] == expected


def test_ac2_the_heading_line_itself_is_included(rows):
    for row in rows:
        section = guide(section=row["slug"])
        first = section.split("\n", 1)[0]
        assert first == "#" * row["level"] + " " + row["heading"], (
            f"{row['slug']}: the section does not begin with its own heading line"
        )


def test_ac2_a_section_ends_at_the_character_before_the_next_same_or_higher_heading(text, rows):
    """The boundary rule stated as an offset assertion: the slice is a contiguous run of the
    document, and the character immediately after it starts the next same-or-higher heading."""
    all_headings = _independent_headings(text)
    for index, row in enumerate(rows):
        section = guide(section=row["slug"])
        start = text.index("\n" + section) + 1 if text.index(section) else text.index(section)
        assert text[start:start + len(section)] == section
        after = text[start + len(section):]
        if not after:
            continue
        level, heading = next(
            (lv, h) for lv, h in all_headings[
                all_headings.index((row["level"], row["heading"])) + 1:
            ] if lv <= row["level"]
        )
        assert after.startswith("#" * level + " " + heading), (
            f"{row['slug']} does not stop exactly where the next level-≤{row['level']} "
            f"heading begins"
        )


def test_ac2_a_level_2_section_contains_its_level_3_children(text, rows):
    parents = [r for r in rows if r["level"] == 2]
    for parent in parents:
        section = guide(section=parent["slug"])
        children = _children_of(rows, parent)
        for child in children:
            assert "\n### " + child["heading"] in section, (
                f"{parent['slug']} does not contain its child {child['slug']}"
            )


def _children_of(rows, parent):
    """The ``###`` rows that follow ``parent`` before the next ``##`` row."""
    order = list(rows)
    start = order.index(parent) + 1
    out = []
    for row in order[start:]:
        if row["level"] <= parent["level"]:
            break
        out.append(row)
    return out


def test_ac2_a_level_3_section_stops_at_the_next_level_3_or_the_next_level_2(rows):
    """Both terminators, each with a real instance: a ``###`` followed by another ``###``, and
    the LAST ``###`` under a ``##`` (whose terminator is the next ``##``)."""
    sibling_terminated = last_under_parent = 0
    for parent in [r for r in rows if r["level"] == 2]:
        children = _children_of(rows, parent)
        for position, child in enumerate(children):
            section = guide(section=child["slug"])
            assert "\n## " not in section, f"{child['slug']} ran past its parent's boundary"
            for other in children[position + 1:]:
                assert "\n### " + other["heading"] not in section, (
                    f"{child['slug']} ran into its sibling {other['slug']}"
                )
            if position + 1 < len(children):
                sibling_terminated += 1
            else:
                last_under_parent += 1
    assert sibling_terminated and last_under_parent, (
        "the guide no longer exercises both level-3 terminators"
    )


def test_ac2_the_last_section_runs_to_end_of_document(text, rows):
    last = rows[-1]
    section = guide(section=last["slug"])
    assert text.endswith(section)
    assert section.startswith("#" * last["level"] + " " + last["heading"])


def test_ac2_the_documents_own_bytes_are_preserved_including_the_trailing_newline(rows):
    """The trailing-newline handling is **stated**, not left to luck: a section is a verbatim
    slice of the document, so it keeps the newline that ends its last line and any blank line
    that sits before the next heading. Nothing is stripped and nothing is added."""
    for row in rows:
        section = guide(section=row["slug"])
        assert section.endswith("\n"), f"{row['slug']} lost the newline ending its last line"
        assert not section.endswith("\n\n\n"), f"{row['slug']} gained blank lines"


def test_ac2_REASSEMBLY_preamble_plus_every_level_2_section_is_byte_identical_to_guide(
        text, rows):
    """**The proof that the slicer loses nothing.** Concatenate every ``##`` section in
    document order; the result must be the exact tail of ``guide()``, and what precedes it must
    contain no ``##`` heading at all — so the sections tile the document with no gap and no
    overlap."""
    tail = "".join(guide(section=r["slug"]) for r in rows if r["level"] == 2)
    assert text.endswith(tail), "the level-2 sections do not tile the end of the document"
    preamble = text[:len(text) - len(tail)]
    assert preamble + tail == text
    assert "\n## " not in preamble and not preamble.startswith("## "), (
        "the preamble carries a level-2 heading, so a section was dropped from the index"
    )
    assert preamble.startswith("# "), "the preamble no longer starts with the document title"


def test_ac2_REASSEMBLY_each_level_2_section_is_its_own_prefix_plus_its_children(rows):
    """The nested form of the same proof, one level down: a parent section is its own text up
    to its first child plus every child section, concatenated."""
    checked = 0
    for parent in [r for r in rows if r["level"] == 2]:
        children = _children_of(rows, parent)
        if not children:
            continue
        section = guide(section=parent["slug"])
        tail = "".join(guide(section=c["slug"]) for c in children)
        assert section.endswith(tail), f"{parent['slug']}'s children do not tile its tail"
        checked += 1
    assert checked >= 5, "too few parent sections with children to make this test meaningful"


# --------------------------------------------------------------------------- #
# AC3 — slug OR exact heading text, case-insensitive; collisions REFUSE.        #
# --------------------------------------------------------------------------- #

def test_ac3_the_three_spellings_of_one_section_all_resolve_to_it(rows):
    """The maintainer's alias tolerance, on the section the wishlist named."""
    heading = "Recipe: read a sheet to Markdown"
    slug = "recipe-read-a-sheet-to-markdown"
    assert slug in _slugs(rows) and heading in _headings(rows), (
        "the guide no longer carries the sheet-read recipe this test is written against"
    )
    by_slug = guide(section=slug)
    assert guide(section=heading) == by_slug
    assert guide(section=heading.upper()) == by_slug
    assert guide(section=slug.upper()) == by_slug
    assert guide(section=f"  {heading}  ") == by_slug
    assert by_slug.startswith("### " + heading)


@pytest.mark.conformance
def test_ac3_ld407_the_ghost_tabs_walk_is_findable_by_the_burn_keywords(rows):
    """LD-407 AC3 — the CONTRACT. A consumer who was burned by ghost tabs searches with the
    words for the disaster ("ghost", "workbook", "every tab"), not the words for the
    technique. A row's heading must carry all three, and naming it through ``guide()`` must
    return the walk's own text — the skip-on-refusal disclosure, not the plain values-read
    recipe next to it."""
    burned = [r for r in rows if all(
        keyword in r["heading"].lower() for keyword in ("ghost", "workbook", "tab"))]
    assert burned, (
        "no guide section heading carries all three burn keywords a consumer searches "
        f"after ghost tabs; headings: {_headings(rows)}"
    )
    heading = burned[0]["heading"]
    text = guide(section=heading)
    assert text.startswith("### " + heading)
    assert "book.skips" in text or "skipped_any" in text, (
        "the section named by the burn keywords must be the WALK's own text, not a "
        f"heading that merely mentions the words: {text}"
    )
    # And the recipe it displaces stays reachable under its own, technique-named heading —
    # the convention is additive, not a rename of the existing recipe (AC2/AC8).
    assert "Recipe: read a sheet to Markdown" in _headings(rows)


@pytest.mark.conformance
def test_ac1_ld427_the_ghost_payload_claim_is_measured_not_unmanufacturable(rows):
    """LD-427 AC1/AC2/AC3 — the ghost tabs recipe used to say a ghost's own listing payload
    "could not be manufactured" and that `resource_type` was "untried rather than refuted".
    Both are now false: the payload is captured and `resource_type` is refuted. The section
    must say so, keep the surviving conclusion (skip on the refusal, not a predicate), ship
    the `title == sheet_id` count+reason together (AC2), and state the still-unmeasured edge
    (AC3) rather than imply completeness."""
    burned = [r for r in rows if all(
        keyword in r["heading"].lower() for keyword in ("ghost", "workbook", "tab"))]
    assert burned, "the ghost-tabs recipe heading vanished from the guide"
    text = guide(section=burned[0]["heading"])
    flat = re.sub(r"\s+", " ", text)  # tolerate the guide's own hard-wrapping

    # The retracted claims must be GONE.
    assert "could not be manufactured" not in flat
    assert "untried rather than refuted" not in flat

    # The measurement that replaces them.
    assert "resource_type" in flat and "\"sheet\"" in flat
    assert "code:0" in flat or "code`:0" in flat or "code:0`" in flat

    # AC2 — the title==sheet_id hazard, count AND reason together, not the count alone.
    assert "21 of 21" in flat
    assert "0 of 2" in flat
    assert "naming accident" in flat

    # AC3 — the still-unmeasured list, and the refutation's own evidence edge.
    assert "why a ghost exists" in flat
    assert "21 ghost tabs and 2 readable tabs" in flat

    # The surviving conclusion — the reader skips on the refusal, never a predicate.
    assert "skip" in flat.lower() and "predicate" in flat.lower()


@pytest.mark.conformance
def test_ac2_ld418_the_view_classification_is_findable_by_the_burn_keywords(rows):
    """LD-418 AC2 — the CONTRACT, D-60's second measured application. A consumer burned by
    hand-configuring view grouping/sort/hidden fields searches with the words for the
    disaster ("group", "sort", "hidden"), not the words for the technique ("create, configure
    and delete a view"). A row's heading must carry all three, and naming it through
    ``guide()`` must return the classification's OWN text — the ``property.group_info`` /
    ``property: null`` sentence — not a heading that merely mentions the words."""
    burned = [r for r in rows if all(
        keyword in r["heading"].lower() for keyword in ("group", "sort", "hidden"))]
    assert burned, (
        "no guide section heading carries all three burn keywords a consumer searches after "
        f"hand-configuring a view; headings: {_headings(rows)}"
    )
    heading = burned[0]["heading"]
    text = guide(section=heading)
    assert text.startswith("### " + heading)
    assert "accepted and not stored" in text, (
        "the section named by the burn keywords must be the CLASSIFICATION's own text, not a "
        f"heading that merely mentions the words: {text}"
    )
    # The classification's content mostly outlives LD-418 unchanged, but LD-426 measured two
    # of its four bullets and corrected them (D-24: the conclusion survives, the reason per
    # key does not have to). Transformed here, not deleted, per that same rule: the
    # hidden-fields assertion below replaces the pre-measurement "the probe packs contradict
    # each other" (now false — LD-426 resolved the contradiction) with the settled fact the
    # correction landed; the gantt assertion and the closing-conclusion assertion still hold
    # because LD-426's own AC4 left that bullet's CLAIM verbatim (its wording had to be
    # spelled out once "same" stopped pointing at the sort bullet's old text) and left the
    # "open it once in the product" paragraph untouched.
    # LD-438 transformed the hidden-fields assertion AGAIN, on the same rule (D-24) and in the
    # same shape: the measurement it pinned ("no observable effect") turned out to be an
    # artefact of a probe that read back only field NAMES, so what the section must now carry
    # is the CORRECTED premise — the per-view `is_hidden` flag and the validation refusal —
    # together with the reason the old refusal was right to exist. Re-aimed, never struck.
    assert "is_hidden" in text and "1254044" in text, (
        "the hidden-fields half of the classification must carry its LD-438 measurement — "
        f"stored, validated, reversible, and observable per view: {text}"
    )
    assert "cannot be observed" in text, (
        "the REASON the other three stay out must survive the supersession of the "
        f"hidden-fields conclusion: {text}"
    )
    assert "no route was ever established" in text
    assert "open it in the product" in text


def test_ac3_the_slug_rule_is_the_stated_one(rows):
    """Backticks dropped, lower-cased, every run of non-alphanumerics collapsed to one ``-``,
    the ends trimmed. Checked against a second copy of the rule over all 48 headings, and on
    the two headings that actually exercise the interesting parts."""
    for row in rows:
        assert row["slug"] == _slug(row["heading"])
    backticked = [r for r in rows if "`" in r["heading"]]
    assert backticked, "no heading carries a backtick, so the drop-backticks rule is untested"
    for row in backticked:
        assert "`" not in row["slug"]
    assert _slug("Output configuration (`config.json`)") == "output-configuration-config-json"
    assert _slug("Choose your level — the tree, or the Markdown projection") == (
        "choose-your-level-the-tree-or-the-markdown-projection"
    )


def test_ac3_every_derived_slug_is_unique(rows):
    slugs = _slugs(rows)
    assert len(set(slugs)) == len(slugs)


def test_ac3_a_slug_COLLISION_raises_at_index_build_time(rows):
    """A document edit that makes two headings share a slug is a defect the library refuses
    rather than serving ambiguously — so the *first match* can never silently win."""
    document = "# T\n\n## Read a sheet\n\nx\n\n## Read a Sheet!\n\ny\n"
    with pytest.raises(ValueError) as excinfo:
        _section_index(document)
    message = str(excinfo.value)
    assert "read-a-sheet" in message
    assert "Read a sheet" in message and "Read a Sheet!" in message, (
        "the collision refusal must name the colliding headings, not only the slug"
    )
    # the real document is fine, which is what makes the guard meaningful rather than fatal
    assert len(_section_index(guide(full=True))) == len(rows)


# --------------------------------------------------------------------------- #
# AC4 — the parse is FENCE-AWARE, proved on the REAL document.                  #
# --------------------------------------------------------------------------- #

def test_ac4_the_real_document_has_many_fences_full_of_hash_prefixed_lines(text):
    """The precondition this AC rests on, measured rather than asserted from memory."""
    fences = [line for line in text.split("\n") if re.match(r"^(`{3,}|~{3,})", line)]
    assert len(fences) >= 60, f"only {len(fences)} fence delimiters — the measurement moved"
    assert len(fences) % 2 == 0, "the guide has an unbalanced fence"


def test_ac4_the_index_count_is_the_FENCE_AWARE_one_not_the_naive_one(text, rows):
    """The gap **is** the test: a naive ``^#`` scan finds several times as many "headings" as
    this document really has, because its Python fences are full of comment lines."""
    fence_aware = [h for h in _independent_headings(text) if h[0] in (2, 3)]
    naive = _naive_headings(text)
    assert len(rows) == len(fence_aware)
    assert len(naive) > 3 * len(rows), (
        f"the naive scan finds {len(naive)} against {len(rows)} real sections — if that gap "
        "closed, this test no longer proves fence-awareness"
    )
    assert len(rows) not in (len(naive), len(naive) - 1)


def test_ac4_a_heading_looking_line_INSIDE_a_fence_is_not_a_section():
    """The synthetic decoy: an in-fence ``## Not A Heading`` must neither appear in the index
    nor truncate the section it sits in."""
    document = (
        "# Title\n\nintro\n\n"
        "## Real\n\n"
        "```python\n"
        "# a comment\n"
        "## Not A Heading\n"
        "print('#### also not one')\n"
        "```\n\n"
        "tail of Real\n\n"
        "## Second\n\nz\n"
    )
    rows = _section_index(document)
    assert [(r["level"], r["heading"]) for r in rows] == [(2, "Real"), (2, "Second")]
    real = _slice(document, "real")
    assert "## Not A Heading" in real, "the in-fence decoy truncated the section it sits in"
    assert real.endswith("tail of Real\n\n")


def test_ac4_a_tilde_fence_and_a_longer_closing_run_are_both_handled():
    document = (
        "# T\n\n## A\n\n"
        "~~~\n## in a tilde fence\n~~~\n\n"
        "````text\n## in a four-backtick fence\n```\nstill inside\n````\n\n"
        "## B\n\nq\n"
    )
    rows = _section_index(document)
    assert [r["heading"] for r in rows] == ["A", "B"]
    assert "## in a tilde fence" in _slice(document, "a")
    assert "still inside" in _slice(document, "a")


def _slice(document, name):
    """``guide(section=...)`` against an arbitrary document — the module's own private seam,
    so the synthetic-document tests exercise the shipped slicer and not a copy of it."""
    from larkdocio.guide import _section_text

    return _section_text(document, name)


# --------------------------------------------------------------------------- #
# AC5 — an unknown section is a TYPED refusal NAMING THE FULL VALID SET.        #
# --------------------------------------------------------------------------- #

def test_ac5_an_unknown_section_raises_ValueError_naming_every_valid_section(rows):
    """LD-131's discipline applied to a caller mistake: the detail is non-empty, actionable and
    **complete**, so the caller needs no second call to recover. Asserted against the DERIVED
    index — never a literal list."""
    with pytest.raises(ValueError) as excinfo:
        guide(section="recipies")
    message = str(excinfo.value)
    assert "recipies" in message, "the refusal does not echo what the caller passed"
    missing = [row["slug"] for row in rows if row["slug"] not in message]
    assert not missing, f"the refusal omits {len(missing)} valid section names: {missing[:5]}"
    assert "guide_sections" in message, (
        "the refusal should name the index helper, so the caller learns where the set lives"
    )


def test_ac5_the_near_miss_that_must_SUCCEED_and_the_one_that_must_FAIL():
    """``"recipes"`` differs from the heading only in case, so AC3 resolves it; ``"recipies"``
    is a typo, so AC5 refuses it. The pair is what proves the tolerance has an edge."""
    assert guide(section="recipes").startswith("## Recipes")
    with pytest.raises(ValueError):
        guide(section="recipies")


@pytest.mark.parametrize("bad", ["", "   ", "Recipes ", "recipe-read-a-sheet"])
def test_ac5_other_caller_mistakes_refuse_the_same_way(bad):
    """Empty, whitespace and a truncated slug all take the same path — except ``"Recipes "``,
    which is a spelling AC3 tolerates, so it must NOT refuse."""
    if bad.strip() == "Recipes":
        assert guide(section=bad).startswith("## Recipes")
        return
    with pytest.raises(ValueError):
        guide(section=bad)


def test_ac5_the_refusal_is_not_a_bare_exception():
    """The type is ``ValueError`` — a caller-argument mistake, which is what ``ValueError``
    means in Python, and the same choice ``capabilities.config_schema()`` makes when its own
    projection disagrees. It is deliberately NOT a new ``LarkDocIOError`` subclass: nothing
    reached Lark, no credential was involved and no document was touched, so the toolkit's
    typed API/config family would misdescribe it — and a new exception class is a public
    symbol, which this refusal does not need to be."""
    from larkdocio.errors import LarkDocIOError

    with pytest.raises(ValueError) as excinfo:
        guide(section="nope")
    assert type(excinfo.value) is ValueError
    assert not isinstance(excinfo.value, LarkDocIOError)


# --------------------------------------------------------------------------- #
# AC6 — the index is on the capabilities docs row AND a module-level helper.     #
# --------------------------------------------------------------------------- #

def test_ac6a_the_guides_docs_row_carries_the_section_index(rows):
    row = capabilities(full=True)["docs"]["guide()"]
    assert row["sections"] == [dict(r) for r in rows]
    assert isinstance(row["sections"], list)


def test_ac6a_every_docs_row_now_carries_a_sections_field():
    """LD-214 shipped the field on **one** row — the ``Surface.block_read_support``
    precedent for an optional field present on one row and absent elsewhere. LD-414
    generalizes the seam to the other three packaged documents, so the field is now on
    every row — this is the update to that precedent, not a second one beside it."""
    docs = capabilities(full=True)["docs"]
    with_sections = [label for label, row in docs.items() if "sections" in row]
    assert sorted(with_sections) == sorted(docs)
    for label, row in docs.items():
        assert set(row) == {"accessor", "resource", "summary", "sections", "section_addressing"}


def test_ac6a_the_docs_row_carries_NAMES_ONLY_never_section_text(text):
    """``capabilities()`` is a dict agents call; 200 KB of body in it would be a regression,
    not a feature. Every value is a name, a slug or a level, and the whole registry stays a
    tiny fraction of the document it indexes."""
    row = capabilities(full=True)["docs"]["guide()"]
    for entry in row["sections"]:
        assert set(entry) == {"heading", "slug", "level"}
        assert isinstance(entry["level"], int)
        assert "\n" not in entry["heading"] and "\n" not in entry["slug"]
    serialized = json.dumps(row)
    assert is_index_sized(len(serialized), len(text)), (
        f"the guide's docs row is {len(serialized)} characters against a {len(text)}-character "
        "guide — section text has leaked into the registry"
    )
    # the direct statement: no section's BODY is anywhere in the registry, only its name
    whole = json.dumps(capabilities(full=True))
    for row_ in guide_sections():
        section = guide(section=row_["slug"])
        body = section.split("\n", 1)[1] if "\n" in section else ""
        for line in [ln for ln in body.split("\n") if len(ln) > 40][:1]:
            assert line not in whole, (
                f"{row_['slug']}'s body line is inside capabilities(): {line[:60]!r}"
            )


def test_ac6a_the_registry_still_round_trips_through_json():
    registry = capabilities(full=True)
    assert json.loads(json.dumps(registry)) == registry


def test_ac6a_the_docs_row_field_is_DERIVED_from_the_accessor_module(monkeypatch):
    """The field is not a special case for one accessor: the projection looks for a
    ``<accessor>_sections`` helper beside the accessor, so a second document that ever grows
    one gains the field with no change here. Proved by removing the helper — the field must
    disappear rather than fall back to a hand-kept copy."""
    monkeypatch.delattr(_module(), "guide_sections")
    assert "sections" not in capabilities(full=True)["docs"]["guide()"]


def test_ac6b_the_helper_is_reachable_from_the_top_level_and_exported():
    """The shadowing trap this decision turns on: ``larkdocio.guide`` is the **function**, so
    ``larkdocio.guide.guide_sections`` cannot work and the module path alone would repeat the
    discoverability failure that made a consumer full-text-search the guide for a symbol."""
    assert callable(larkdocio.guide)
    assert not hasattr(larkdocio.guide, "guide_sections")
    assert larkdocio.guide_sections is guide_sections
    assert "guide_sections" in larkdocio.__all__
    namespace = {}
    exec("from larkdocio import *", namespace)
    assert callable(namespace["guide_sections"])


def test_ac6b_the_export_carries_its_entry_point_row():
    """``_ENTRY_POINT_NOTES`` raises for an undescribed export, so this is the positive
    statement of what that projection now says."""
    entry = capabilities(full=True)["entry_points"]["guide_sections"]
    assert entry["kind"] == "function"
    assert entry["summary"].strip() and entry["cost"].strip()
    assert "no api call" in entry["cost"].lower()


def test_ac6b_the_helper_returns_the_same_index_the_slicer_uses(rows):
    assert isinstance(rows, tuple)
    assert all(isinstance(row, dict) for row in rows)
    for row in rows:
        assert guide(section=row["slug"]).startswith(
            "#" * row["level"] + " " + row["heading"]
        )


# --------------------------------------------------------------------------- #
# AC7 — everything is DERIVED AT CALL TIME, so it cannot drift.                 #
# --------------------------------------------------------------------------- #

def _src_python_files():
    return [p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts]


def test_ac7_no_section_name_literal_exists_anywhere_in_src(rows):
    """No hand-kept list of section names — not in ``guide.py``, not in ``capabilities.py``,
    not in a constant and not in a docstring a guard then pins. Two prongs: no **string
    literal** in any shipped module equals a heading or a slug (that is what a hand-kept list
    or an ``if section == "..."`` branch looks like), and no hyphenated slug appears in the
    source text at all (a lowercase hyphenated slug is never English prose)."""
    slugs = {row["slug"] for row in rows}
    headings = {row["heading"].lower() for row in rows}
    offenders = []
    for path in _src_python_files():
        source = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value.strip().lower()
                if value in slugs or value in headings:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} {value!r}")
        for slug in slugs:
            if "-" in slug and slug in source:
                offenders.append(f"{path.relative_to(REPO_ROOT)} carries the slug {slug!r}")
    assert not offenders, (
        "a section name is written down in src/ — the index must be derived from the document "
        f"at call time, never listed: {offenders}"
    )


def test_ac7_the_guard_above_BITES(rows, tmp_path):
    """The anti-vacuity twin: the same scan over a module that *does* list a section name must
    find it, so a green result above means "nothing is listed" rather than "nothing is
    scanned"."""
    slugs = {row["slug"] for row in rows}
    hyphenated = sorted(s for s in slugs if "-" in s)[0]
    planted = tmp_path / "planted.py"
    planted.write_text(f'SECTIONS = ("{hyphenated}", "Recipes")\n', encoding="utf-8")
    source = planted.read_text(encoding="utf-8")
    found = [
        node.value for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and (node.value.strip().lower() in slugs
             or node.value.strip().lower() in {r["heading"].lower() for r in rows})
    ]
    assert len(found) == 2, f"the literal scan would not have caught a planted list: {found}"
    assert hyphenated in source


_DERIVATION_PROBE = r"""
import json, larkdocio
from larkdocio import guide_sections
rows = list(guide_sections())
print(json.dumps({
    "file": larkdocio.__file__,
    "slugs": [r["slug"] for r in rows],
    "capability_slugs": [
        r["slug"] for r in larkdocio.capabilities(full=True)["docs"]["guide()"]["sections"]
    ],
    "synthetic_text": larkdocio.guide(section="synthetic section for the derivation proof"),
}))
"""


def test_ac7_adding_a_heading_to_THE_DOCUMENT_moves_all_three_answers_with_zero_code_change(
        tmp_path, rows):
    """**The whole "no registry" claim in one observation.** Copy the package tree, append one
    ``##`` heading to the COPY's ``GUIDE.md``, and import the copy in a subprocess: the helper,
    the ``capabilities()`` field and the slicer all gain that section, with not one byte of
    code changed. Then confirm the repo tree is byte-clean — the document that was edited was
    the copy."""
    before = (SRC / "larkdocio" / "GUIDE.md").read_bytes()
    staged = tmp_path / "src"
    shutil.copytree(
        SRC, staged,
        ignore=shutil.ignore_patterns("*.egg-info", "__pycache__", "build", "dist"),
    )
    document = staged / "larkdocio" / "GUIDE.md"
    heading = "Synthetic section for the derivation proof"
    document.write_text(
        document.read_text(encoding="utf-8") + f"\n## {heading}\n\nappended by a test.\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, "-c", _DERIVATION_PROBE], cwd=str(tmp_path), capture_output=True,
        text=True, env={"PYTHONPATH": str(staged), "PYTHONDONTWRITEBYTECODE": "1",
                        "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, f"the derivation probe failed:\n{proc.stderr[-2000:]}"
    out = json.loads(proc.stdout)
    assert out["file"].startswith(str(staged)), (
        f"the probe imported {out['file']}, not the staged copy — it proves nothing"
    )
    expected = "synthetic-section-for-the-derivation-proof"
    assert out["slugs"] == [r["slug"] for r in rows] + [expected]
    assert out["capability_slugs"] == out["slugs"]
    assert out["synthetic_text"] == f"## {heading}\n\nappended by a test.\n"

    # the repo's own document never moved — the one that was edited was the copy — so the
    # installed index never gained the section either
    assert expected not in [r["slug"] for r in guide_sections()]
    assert (SRC / "larkdocio" / "GUIDE.md").read_bytes() == before, (
        "the probe changed the repository's own document instead of the staged copy"
    )


def test_ac7_the_index_is_rebuilt_on_every_call_not_cached_at_import(monkeypatch):
    """Derived at CALL time. If the packaged bytes change, the very next call reflects it —
    which is also what makes the subprocess proof above a property rather than a coincidence."""
    guide_module = _module()

    document = "# T\n\n## Only\n\nx\n"
    monkeypatch.setattr(guide_module, "_packaged", lambda *a, **k: document)
    assert [r["heading"] for r in guide_module.guide_sections()] == ["Only"]
    assert guide_module.guide(section="only") == "## Only\n\nx\n"


# --------------------------------------------------------------------------- #
# AC8 — the guide documents its OWN section access, and the example RUNS.       #
# --------------------------------------------------------------------------- #

#: The section AC8 adds. Named by its slug, because that is how the feature addresses it — and
#: reading it with the feature it documents is the point.
_SELF_DOC_SLUG = "reading-one-section-of-this-guide"


def test_ac8_the_guide_carries_a_section_about_section_access(rows):
    assert _SELF_DOC_SLUG in _slugs(rows), (
        "the guide does not document its own section access, so a consumer who reads it "
        "cannot learn the feature from it"
    )
    row = next(r for r in rows if r["slug"] == _SELF_DOC_SLUG)
    assert row["level"] == 3
    parent = "## Reading the shipped documents programmatically"
    assert parent in guide(section="reading-the-shipped-documents-programmatically")
    assert _SELF_DOC_SLUG in [
        r["slug"] for r in _children_of(
            rows, next(r for r in rows if r["heading"].startswith("Reading the shipped"))
        )
    ]


def test_ac8_that_section_states_the_boundary_rule_both_spellings_and_the_refusal():
    section = guide(section=_SELF_DOC_SLUG).lower()
    for claim, phrase in (
        ("the boundary rule", "same or higher level"),
        ("the slug spelling", "slug"),
        ("the heading spelling", "case-insensitive"),
        ("where the index lives", "guide_sections"),
        # LD-475: the registry's own index moved behind an explicit argument, so the section
        # names the call that returns the rows rather than the bare one that returns a summary.
        ("the capabilities index", "capabilities(full=true)"),
        ("what an unknown name does", "valueerror"),
    ):
        assert phrase in section, f"the new section does not state {claim} ({phrase!r})"


def test_ac8_the_added_example_EXECUTES_in_the_repos_recipe_harness():
    """A ``python`` fence that does not run is worse than prose. Extracted **with the feature
    it documents** — the section is read by slug — and executed in the harness's builtins-only
    namespace, so it has to import everything it uses exactly as a consumer's file does."""
    import guide_recipes

    section = guide(section=_SELF_DOC_SLUG)
    blocks = re.findall(r"```python\n(.*?)```", section, flags=re.DOTALL)
    assert len(blocks) == 1, f"expected exactly one python fence in the new section, got {len(blocks)}"
    namespace = guide_recipes.run_recipe(_SELF_DOC_SLUG, source=blocks[0])
    assert namespace, "the example produced an empty namespace"


def test_ac8_the_section_that_documents_the_feature_is_ADDRESSABLE_BY_it():
    """The recursion, asserted: the subsection added to teach section access is itself one of
    the sections it teaches you to ask for, by slug and by heading text alike."""
    by_slug = guide(section=_SELF_DOC_SLUG)
    heading = next(
        r["heading"] for r in guide_sections() if r["slug"] == _SELF_DOC_SLUG
    )
    assert guide(section=heading) == by_slug
    assert guide(section=heading.upper()) == by_slug
    assert by_slug.startswith("### " + heading)


# --------------------------------------------------------------------------- #
# AC8's artifact arm — the text SHIPS and a section reads out of the WHEEL.      #
# --------------------------------------------------------------------------- #

def test_ac8_a_section_reads_out_of_the_BUILT_WHEEL_with_no_src_tree_importable(tmp_path):
    """The LD-193 standard: the bytes are in the wheel, and a consumer with no repo on
    ``sys.path`` reads a section by slug and by heading text from a directory outside the
    repository."""
    from test_shipped_notes import _built_wheel_record

    wheel = _built_wheel_record(tmp_path)
    with zipfile.ZipFile(wheel) as archive:
        record = next((n for n in archive.namelist() if n.endswith("/RECORD")), None)
        assert record and "larkdocio/GUIDE.md" in archive.read(record).decode("utf-8")
        shipped = archive.read("larkdocio/GUIDE.md").decode("utf-8")
        assert shipped == (SRC / "larkdocio" / "GUIDE.md").read_text(encoding="utf-8"), (
            "the GUIDE.md inside the wheel is not the source document's bytes"
        )
        unpacked = tmp_path / "unpacked"
        archive.extractall(unpacked)

    probe = r"""
import json, larkdocio
from larkdocio import guide_sections
row = next(r for r in guide_sections() if r["slug"] == "%s")
print(json.dumps({
    "file": larkdocio.__file__,
    "by_slug": larkdocio.guide(section=row["slug"])[:80],
    "identical": larkdocio.guide(section=row["heading"]) == larkdocio.guide(section=row["slug"]),
    "count": len(guide_sections()),
}))
""" % _SELF_DOC_SLUG
    proc = subprocess.run(
        [sys.executable, "-c", probe], cwd=str(tmp_path), capture_output=True, text=True,
        env={"PYTHONPATH": str(unpacked), "PYTHONDONTWRITEBYTECODE": "1",
             "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, f"the wheel-only probe failed:\n{proc.stderr[-2000:]}"
    out = json.loads(proc.stdout)
    assert out["file"].startswith(str(unpacked)), (
        f"the probe imported {out['file']}, not the unpacked wheel — the arm proves nothing"
    )
    assert out["identical"]
    assert out["by_slug"].startswith("### ")
    assert out["count"] == len(guide_sections())


# --------------------------------------------------------------------------- #
# AC10 — the release note, and the sentence it must not falsify.                #
# --------------------------------------------------------------------------- #

def test_ac10_the_release_note_announces_the_new_capability_in_both_copies():
    """AC10: section access is announced under [1.23.0]'s New capabilities, in every copy of the
    notes that carries that release.

    **LD-540 — the window, and why this is asserted over a DERIVED set of copies.** The wheel
    now carries a recent-N window of each release document while the repository keeps the whole
    history, so "this claim is written down" and "this claim ships" stopped being one sentence.
    ``test_shipped_notes.notes_claim_copies`` answers which copies must carry it: the root
    always (a deletion from the authoring source reddens with full force), and the packaged
    window whenever it still holds the section — and if it does not, that helper PROVES the
    section is genuinely out of window rather than letting the claim go missing. Nothing was
    weakened and no copy was dropped by hand.
    """
    from test_shipped_notes import notes_claim_copies

    for label, notes in notes_claim_copies("RELEASE_NOTES.md", "## [1.23.0]"):
        section = notes.split("## [1.23.0]", 1)[1].split("\n### Behavior changes", 1)[0]
        assert "guide(section=" in section, (
            f"{label} does not announce section access under [1.23.0] New capabilities"
        )
        assert "guide_sections()" in section


def test_ac10_the_no_options_sentence_stays_PUT_IN_1_23_0_and_is_superseded_not_edited():
    """The caution recorded at mint was that a ``--section`` CLI flag would falsify this
    sentence. LD-228 shipped that flag, and the ruling is that release history is **immutable**:
    the 1.23.0 sentence keeps describing what 1.23.0 shipped, and the ``[1.26.0]`` entry is what
    supersedes it. So both halves are pinned the other way round now — the historical sentence
    is still there, unedited, and the flag it predates is disclosed in the newer section.
    """
    from larkdocio.cli import cli

    notes = (REPO_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    history = notes.split("## [1.23.0]", 1)[1].split("## [1.22.0]", 1)[0]
    assert "It takes no options" in history, "a past release section was rewritten"
    assert "--section" not in history
    superseding = notes.split("## [1.26.0]", 1)[1].split("## [1.25.0]", 1)[0]
    assert "--section" in superseding, (
        "larkdocio guide grew an option and no later release section discloses it"
    )
    # The flag set grew a second member with the front-door swap (`--full`, the whole document
    # now that the index is the default) — and it, too, is disclosed in a later release section
    # rather than by editing history.
    assert [p.name for p in cli.commands["guide"].params] == ["section", "full"]


# --------------------------------------------------------------------------- #
# LD-219 — no heading in the guide is unreachable through the index.            #
# --------------------------------------------------------------------------- #

def test_every_heading_below_the_title_sits_at_an_INDEXED_level(text):
    """LD-214 recorded one ``####`` in the guide — the single heading ``guide_sections()``
    deliberately could not name, in a document whose whole point is that a consumer can ask
    for one part of it. A heading nobody can name is a navigation hole, so below the one
    ``#`` title every heading sits at a level in ``GUIDE_SECTION_LEVELS``; a passage that
    does not deserve its own indexed section is written as prose, not as a heading the index
    silently swallows.
    """
    headings = _independent_headings(text)
    titles = [h for level, h in headings if level == 1]
    assert len(titles) == 1, f"the guide should carry exactly one `#` title, found {titles}"
    unreachable = [
        (level, heading)
        for level, heading in headings
        if level != 1 and level not in GUIDE_SECTION_LEVELS
    ]
    assert unreachable == [], (
        f"headings at a level the index does not cover {GUIDE_SECTION_LEVELS}: {unreachable} "
        "— each is unnameable through guide(section=...), so re-level it or write it as prose"
    )
