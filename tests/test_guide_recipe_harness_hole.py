"""LD-152 AC4 — the extract-and-run harness hole that let an unrunnable line ship.

**The bug.** The shipped `read a sheet to Markdown` recipe offered the L2 fidelity render as

    # markdown = render_spreadsheet(pairs, fidelity=exported_by_sheet_id)   # + L2 emphasis

and `exported_by_sheet_id` was never bound anywhere — in a guide whose Recipes preamble
promises "no undefined free variables" and "every recipe runs as pasted". A consumer who
uncomments the line (which is the *only* reason the line exists) gets a `NameError`.

**The root cause is the harness, not the variable.** LD-133 built the extract-and-run
harness precisely so an unrunnable recipe could not ship, and it missed this one — because
**both** of its checks read only the code that *executes*:

* :func:`guide_recipes.undefined_free_names` parses the block with :mod:`ast`, and ``ast``
  discards comments — so a defect inside a comment is invisible to it;
* :func:`guide_recipes.run_recipe` ``exec``s the block, and a comment never runs.

So the harness's unit of verification was **executable source**, while a recipe's unit of
*teaching* is **every line a consumer may paste** — and a commented-out alternative is
pasted by uncommenting it. The gap between those two units is the hole.

**The closure, as a CLASS.** :func:`guide_recipes.static_problems` runs the checks over
every python line a consumer could paste — the live source **and** each commented-out
statement promoted to live code — and catches the three static defect classes a pasted line
can carry: an **undefined free variable**, a **non-existent symbol**, and a **syntax
error**. The probes below inject each class into a comment (the exact shape that shipped)
and into live code, and assert the gate reports it; they are the red-then-green proof that
the hole is closed for the class, not patched for the one variable.
"""
import re

import pytest

import guide_recipes as gr

# The verbatim line that shipped (dogfood F3) — the fixture every probe below mutates.
_SHIPPED_DEFECT = (
    "# markdown = render_spreadsheet(pairs, fidelity=exported_by_sheet_id)   # + L2 emphasis"
)

_CLEAN = (
    "from larkdocio.sheets.table import render_spreadsheet\n"
    "pairs = []\n"
    "markdown = render_spreadsheet(pairs)\n"
)


# --------------------------------------------------------------------------- #
# 1. The ROOT CAUSE, reproduced: the pre-LD-152 checks are blind to a comment. #
# --------------------------------------------------------------------------- #

def test_the_free_variable_check_is_structurally_blind_to_a_commented_line():
    """Root cause (a): ``undefined_free_names`` cannot see a commented-out defect.

    Not an oversight in how it was called — ``ast.parse`` discards comments, so the check
    is *structurally* incapable of seeing this class. Pinning that is what makes the new
    gate's existence necessary rather than decorative."""
    source = _CLEAN + _SHIPPED_DEFECT + "\n"
    assert gr.undefined_free_names(source) == [], (
        "if the ast-based check could see the commented line, LD-152's gate would be "
        "redundant — the whole point is that it cannot"
    )
    assert "exported_by_sheet_id" in source


def test_running_the_recipe_is_blind_to_a_commented_line_too(monkeypatch, tmp_path):
    """Root cause (b): executing the block cannot see it either — a comment never runs.

    Both halves of the LD-133 harness therefore passed a line that ``NameError``s the
    moment a consumer uses it, which is the only way the line was ever meant to be used."""
    st = gr.stage(monkeypatch, tmp_path)
    src = gr.recipe_source("read-a-sheet-to-markdown")
    with_defect = src + "\n" + _SHIPPED_DEFECT + "\n"
    ns = st.run("read-a-sheet-to-markdown", source=with_defect)
    assert "exported_by_sheet_id" not in ns
    gr._check_sheet_read(ns)


def test_the_new_gate_sees_what_both_old_checks_missed():
    """The hole, closed: the same source the two checks above wave through is reported."""
    problems = gr.static_problems(_CLEAN + _SHIPPED_DEFECT + "\n")
    assert problems, "the gate must report the shipped defect"
    joined = " ".join(problems)
    assert "exported_by_sheet_id" in joined, problems
    assert "commented" in joined.lower(), (
        "the report must say the defect is in a commented-out line — that IS the hole")


# --------------------------------------------------------------------------- #
# 2. The gate over the SHIPPED guide — every pasteable line, every recipe.      #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("block", gr.python_blocks(), ids=lambda b: (b.slug or "non-recipe"))
def test_no_python_line_in_the_guide_is_unrunnable_as_pasted(block):
    """AC4: no python line the guide ships — live **or commented out** — carries a static
    defect. This is the assertion that was missing when F3 shipped."""
    problems = gr.static_problems(block.source)
    assert not problems, (
        "the guide ships a python line that cannot run as pasted:\n"
        + "\n".join(problems)
        + f"\n\nin block:\n{block.source}"
    )


def test_the_guides_promise_is_the_one_the_gate_enforces():
    """The Recipes preamble promises exactly what the gate now checks, so the claim and
    the guard cannot drift apart."""
    preamble = gr.guide(full=True).split("## Recipes", 1)[1].split("### Recipe:", 1)[0]
    low = preamble.lower()
    assert "no undefined free variables" in low, preamble
    assert "runs as pasted" in low, preamble


# --------------------------------------------------------------------------- #
# 3. The CLASS closed — one probe per defect class, in a comment AND in code.   #
# --------------------------------------------------------------------------- #

#: (label, the line to inject, the substring the report must name).
_DEFECT_CLASSES = (
    # (a) the shipped shape: a free variable.
    ("free-variable", "markdown = render_spreadsheet(pairs, fidelity=exported_by_sheet_id)",
     "exported_by_sheet_id"),
    # (b) a symbol that does not exist in the module it is imported from.
    ("non-existent-symbol", "from larkdocio.sheets.table import render_spreadsheeet",
     "render_spreadsheeet"),
    # (c) a syntax error.
    ("syntax-error", "markdown = render_spreadsheet(pairs", "syntax"),
)


@pytest.mark.parametrize("label,line,needle", _DEFECT_CLASSES, ids=lambda x: x if isinstance(x, str) else "")
def test_the_gate_catches_the_class_when_it_hides_in_a_comment(label, line, needle):
    """AC4 (the load-bearing probe): each defect class, injected as a **commented-out**
    line — the exact shape that shipped — is reported."""
    problems = gr.static_problems(_CLEAN + f"# {line}\n")
    assert problems, f"{label!r} in a comment was not caught"
    joined = " ".join(problems).lower()
    assert needle.lower() in joined, (label, problems)
    assert "commented" in joined, (
        f"the {label!r} report must locate the defect in the commented line: {problems}")


@pytest.mark.parametrize("label,line,needle", _DEFECT_CLASSES, ids=lambda x: x if isinstance(x, str) else "")
def test_the_gate_catches_the_class_in_live_code_too(label, line, needle):
    """AC4: the same three classes in **live** code are reported by the same gate — so the
    closure is one rule over every pasteable line, not a second special-case checker."""
    problems = gr.static_problems(_CLEAN + line + "\n")
    assert problems, f"{label!r} in live code was not caught"
    assert needle.lower() in " ".join(problems).lower(), (label, problems)


def test_the_gate_greens_on_the_clean_equivalent_of_every_probe():
    """Not vacuous in the other direction: the *repaired* form of each probe passes, so the
    gate reports defects rather than merely disliking commented code."""
    assert gr.static_problems(_CLEAN) == []
    repaired = (
        "from larkdocio.sheets.export_reader import exported_by_sheet_id\n"
        "from larkdocio.sheets.table import render_spreadsheet\n"
        "pairs, tabs, workbook = [], [], None\n"
        "# markdown = render_spreadsheet(pairs, fidelity=exported_by_sheet_id(tabs, workbook))\n"
    )
    assert gr.static_problems(repaired) == []


# --------------------------------------------------------------------------- #
# 4. The detector's precision — it must not cry wolf on the guide's prose.      #
# --------------------------------------------------------------------------- #

def test_prose_comments_are_not_mistaken_for_code():
    """The detector promotes only comments that are genuinely a Python **statement**.

    Precision matters as much as recall here: a detector that treats every comment as code
    would redden on the guide's explanatory prose, and the first fix would be to weaken or
    delete it. Each line below is real guide prose that must stay a comment."""
    prose = (
        "# FIRST: nothing sees your creds until the .env is loaded",
        "# values-only (fidelity=None)",
        '# "LOUD WARNING: ... stored as INERT TEXT ..."',
        "# e.g. 21 — read back AFTER the write",
        "# [{sheet_id, title, index, ...}]",
        "# preview: ZERO writes",
        "# LARK_READ_APP_* (legacy pair fallback)",
        # Verbatim guide prose that the two riskiest shape rules must NOT claim: the first
        # names a keyword parameter with an `=` (an assignment shape) and carries balanced
        # parens; the second opens with a real call and then wraps mid-sentence, leaving a
        # LATER paren unclosed. Both are code-shaped by eye and neither is code.
        '# domain= is the API domain ("larksuite.com" | "feishu.cn"), not your tenant host.',
        "# apply() handed back one id per block it created, in authored order. Re-read (a plan",
    )
    for line in prose:
        assert gr.commented_code_lines(line + "\n") == [], (
            f"prose was mistaken for commented-out code: {line!r}")
    assert gr.static_problems("\n".join(prose) + "\n") == []


def test_the_detector_finds_real_commented_code_of_each_statement_shape():
    """Recall: the three statement shapes a consumer actually uncomments are detected."""
    for line in (
        "# markdown = render_spreadsheet(pairs)",
        "# from larkdocio.sheets.table import render_spreadsheet",
        "# print(plan.revision_guard)",
    ):
        found = gr.commented_code_lines(line + "\n")
        assert len(found) == 1, (line, found)
        assert found[0].code == line.lstrip("# ")


def test_the_promotion_preserves_indentation_and_line_position():
    """``uncommented_source`` promotes a comment **in place** — same line, same indent — so
    a reported syntax error's line number points at the guide's own line."""
    source = "if True:\n    pass\n    # markdown = render_spreadsheet(pairs)\n"
    (found,) = gr.commented_code_lines(source)
    promoted = gr.uncommented_source(source, found)
    assert promoted.splitlines()[2] == "    markdown = render_spreadsheet(pairs)"
    assert len(promoted.splitlines()) == len(source.splitlines())
    assert re.search(r"^\s+markdown", promoted, flags=re.MULTILINE)
