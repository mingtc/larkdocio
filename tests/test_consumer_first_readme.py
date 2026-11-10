"""THE AUDIENCE GUARD — the wheel's front door is addressed to the reader it actually has.

The claims in this document were corrected once already, and the document was **still wrong**,
because *no guard checks audience*. For someone holding only the wheel — the reader
``pip show larkdocio`` hands the ``METADATA`` body to — the front door read like this:

* the **first actionable section** was ``./setup.sh`` plus "clone this repo". Neither is
  possible from an install;
* *"Package layout"* was a **fifteen-row table of ``src/larkdocio/…`` paths absent from their
  tree**;
* **thirty-seven citations dangled** across 322 lines (``src/…`` ×17, ``consumers/…`` ×9,
  ``.env.example`` ×4, ``TOOLS.md`` ×4, ``BLOCKS.md`` ×3);
* ``grep -c '```python' README.md`` returned **0** — not one line of Python in the front door
  of a Python library. The only code was ``./setup.sh``;
* and the one line that actually onboards anybody, ``print(larkdocio.guide())``, sat in prose
  at line 36 and **never appeared as a line anyone could run**.

The verdict the audit recorded is the impact: a reader who stopped at what ``pip show`` gave
them would have concluded they needed to clone a repository to use this library.

What this module pins
---------------------
Four structural facts, each tied to something derived rather than to prose:

1. **the quickstart leads**, needs no clone, and demonstrates all six steps (§ AC1);
2. **the layout table moved and its bidirectional guard moved with it** — the whole risk of
   this change, and the section below labelled AC2 is the one to read hardest. The table is now
   held **exactly equal** to the real top level at its new home, which is strictly stronger than
   the two-way diff it travelled with, and every direction is red-proved *through the real
   parse* over the *moved* text (§ AC2);
3. **the consumer half cites nothing the wheel does not carry** — label-blind, because a label
   does not conjure a file for someone who has only an install (§ AC3);
4. **runnable Python exists and the quickstart EXECUTES** on the same offline stage the shipped
   guide's recipes run on, so an unrunnable quickstart — the defect one layer along — reddens
   (§ AC4).

Plus the package docstring's surface count, derived from ``capabilities()`` ∩ the real
sub-packages so it cannot drift back to three (§ AC5), and the built wheel's ``METADATA``,
because the artifact is the deliverable (§ AC6).
"""
import re

import guide_recipes as gr
import pytest

import front_door as fd
from doc_prose import prose

import larkdocio

# LD-370 — CONFORMANCE-tier: the front door's AUDIENCE is a product decision (the reader who holds only the wheel).
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance


@pytest.fixture(scope="module")
def readme():
    return fd.readme_text()


@pytest.fixture(scope="module")
def halves(readme):
    return fd.split_at_development_heading(readme)


@pytest.fixture(scope="module")
def consumer_half(halves):
    return halves[0]


@pytest.fixture(scope="module")
def development_half(halves):
    return halves[1]


# =====================================================================
# AC1 — a consumer quickstart LEADS the document; the clone material is
#       behind a heading that says so.
# =====================================================================

#: Instructions that are *impossible* for the reader the consumer half addresses. Not
#: "discouraged" — a reader who follows one has nowhere to run it.
#:
#: ``git clone`` **used to be in this tuple as a bare token, and LD-194 narrowed it** — the one
#: narrowing in this module, so the reasoning is here rather than in a commit message. The
#: defect being guarded was *"the first actionable section told me to clone this repo and run*
#: ``./setup.sh``\\ *"*: cloning the **development repository** is what an installed reader cannot
#: use. Cloning the **`dist` distribution branch** is the opposite — it is how a consumer with
#: nothing *gets* the wheel, it needs no build and no source, and it is now step 0.
#:
#: So the guard keeps its intent and loses only its overreach: ``git clone`` is still forbidden,
#: except for the artifact clone, which is recognised by :func:`front_door.dev_repo_clone_lines`.
#: A bare ``git clone <repo>`` in the consumer half still reddens — proved by
#: :func:`test_ac1_a_DEV_REPO_clone_in_the_consumer_half_is_STILL_caught`, which is what keeps
#: this a narrowing rather than a hole.
#:
#: **LD-205 tightened the exemption** from ``"--branch dist" in line`` to the parsed ``--branch``
#: **argument**, because the substring form was satisfied by a trailing comment and by
#: ``--branch distribution``; the predicate now lives once, in ``tests/front_door.py``, and its
#: must-bite cases are
#: :func:`test_ac1_the_artifact_exemption_is_the_BRANCH_ARGUMENT_not_a_substring`.
_IMPOSSIBLE_FROM_A_WHEEL = ("./setup.sh",)

#: The shared predicate, re-exported under this module's historical name so the guards below
#: read as they always did. Identity with ``fd``'s is asserted by
#: :func:`test_ac1_the_clone_predicate_has_exactly_ONE_definition`.
dev_repo_clone_lines = fd.dev_repo_clone_lines


def test_ac1_the_consumer_facing_material_leads_the_document(readme):
    """The lead is the whole fix — **restated for the role router that now sits in front of the
    quickstart** (LD-193), and deliberately STRONGER than the assertion it replaces.

    This guard used to say "the first ``##`` heading is the quickstart". A router that lets the
    reader self-identify is now the first section, so a literal quickstart-first check would
    forbid the improvement while protecting nothing extra — the thing it was defending is that
    **a reader holding only a wheel meets material they can execute before anything else.**
    So all four legs are asserted here, and together they are a superset of the old one:

    1. the first section is the router (not the clone quickstart — the original defect);
    2. the router's **first arm is the consumer's**, so the primary role reads first;
    3. the quickstart still precedes the development heading — the consumer-first *ordering*
       this module exists to defend; and
    4. neither the router nor the quickstart is the clone-based ``(standalone)`` section.

    The router's own shape (three arms, resolving anchors, step 0 first) is
    ``tests/test_role_router_readme.py``'s subject; what is pinned here is the **ordering**,
    which is this module's.
    """
    headings = [line.strip() for line in readme.splitlines() if line.startswith("## ")]
    assert headings[0] == "## Start here — pick your path", (
        f"the README's first section is {headings[0]!r} — the role router must lead so the "
        f"reader can place themselves before reading anything"
    )
    assert "standalone" not in " ".join(headings).lower(), (
        "a clone-based `(standalone)` quickstart is back in the document's headings"
    )

    arms = [line.strip() for line in readme.splitlines() if line.startswith("### ")]
    assert arms and arms[0].lower().startswith("### consumer"), (
        f"the router's first arm is {arms[0] if arms else None!r} — the consumer is the "
        f"primary role and must not read someone else's arm first"
    )

    quickstart = next(i for i, h in enumerate(headings) if h.lower().startswith("## quickstart"))
    development = next(i for i, h in enumerate(headings) if h == fd.DEVELOPMENT_HEADING)
    assert quickstart < development, (
        "the quickstart no longer precedes the development heading — the consumer-first "
        "ordering is exactly what this module defends"
    )


def test_ac1_the_lead_check_bites_on_the_PRE_FIX_and_PRE_ROUTER_shapes():
    """Red proof for both defects the assertion above forecloses, so neither can come back.

    The pre-LD-178 shape led with a clone quickstart; the pre-LD-193 shape led with the
    consumer quickstart and offered no way to self-identify. A guard that cannot be shown
    failing on the documents it was written against proves nothing.
    """
    pre_178 = ["## Quickstart (standalone)", "## Developing larkdocio"]
    assert pre_178[0] != "## Start here — pick your path"
    assert "standalone" in " ".join(pre_178).lower()

    pre_193 = ["## Quickstart — six steps from an installed wheel", "## Developing larkdocio"]
    assert pre_193[0] != "## Start here — pick your path", (
        "the router-first leg does not bite on the pre-router document"
    )


def test_ac1_the_consumer_half_asks_for_nothing_a_wheel_reader_cannot_do(consumer_half):
    """The reproduction, closed: no ``./setup.sh`` and no **dev-repo** clone above the
    development heading. This is the assertion that fails on the pre-fix document."""
    present = [needle for needle in _IMPOSSIBLE_FROM_A_WHEEL if needle in consumer_half]
    assert not present, (
        f"the consumer half instructs {present}, which a reader holding only the wheel "
        f"cannot do — that is the whole defect: the first actionable section was impossible"
    )
    clones = dev_repo_clone_lines(consumer_half)
    assert not clones, (
        f"the consumer half tells the reader to clone something other than the `dist` "
        f"artifact branch: {clones} — cloning the development repository is exactly what an "
        f"installed reader cannot use"
    )


def test_ac1_the_impossible_instruction_detector_bites():
    """Red-proof: the check above is not vacuous — it flags the pre-fix opening verbatim."""
    pre_fix = (
        "## Quickstart (standalone)\n\nUse this when you've cloned the repo.\n\n"
        "```bash\n./setup.sh\n```\n"
    )
    assert [n for n in _IMPOSSIBLE_FROM_A_WHEEL if n in pre_fix] == ["./setup.sh"]


def test_ac1_a_DEV_REPO_clone_in_the_consumer_half_is_STILL_caught():
    """**The proof that LD-194's narrowing is a narrowing and not a hole.**

    ``git clone`` left the blanket-forbidden tuple so step 0 could be the shallow ``dist``
    clone — the command that *gets* a consumer the wheel. If that swap had simply deleted the
    protection, the original defect (*"I concluded I needed to clone a repo to use this
    library"*) could walk straight back in. So: the dev-repo clone is still reported, in every
    shape the pre-fix document used it, and only the artifact clone is exempt.
    """
    for shape in (
        "git clone ssh://git@host/larkdocio.git",
        "git clone https://example.com/larkdocio.git && cd larkdocio",
        "  git clone --depth 1 https://example.com/larkdocio.git",
    ):
        assert dev_repo_clone_lines(shape), f"a dev-repo clone was not caught: {shape!r}"

    # …and the one clone a consumer CAN run is permitted — in the exact form step 0 ships.
    assert not dev_repo_clone_lines(
        "git clone --branch dist --depth 1 <larkdocio-url> vendor   # 0. get the wheel"
    )
    # The discriminator is per LINE, so a `--branch dist` elsewhere cannot launder a dev clone.
    mixed = (
        "git clone --branch dist --depth 1 <url> vendor\n"
        "git clone ssh://git@host/larkdocio.git\n"
    )
    assert [line for _lineno, line in dev_repo_clone_lines(mixed)] == [
        "git clone ssh://git@host/larkdocio.git"
    ]


def test_ac1_the_artifact_exemption_is_the_BRANCH_ARGUMENT_not_a_substring():
    """**LD-205** — the same-line shapes the per-line narrowing never considered.

    The exemption used to be ``"--branch dist" not in line``: a raw substring over the whole
    line, comment included. So a genuine dev-repo clone could be laundered two ways, both
    verified green against every front-door guard before this test existed (275 passed):

    1. put the characters in a trailing ``#`` comment — the command still clones the dev repo;
    2. clone a **longer branch name** that merely starts with them (``distribution``, ``distro``).

    A protection that a comment can satisfy is weaker than its docstring claims, and the
    docstring is what the next author trusts. So the discriminator is now the ``--branch``
    **argument**, read after the comment is cut off — and these are its must-bite cases.
    """
    for laundered in (
        "git clone ssh://git@host/larkdocio.git   # 0. instead of --branch dist",
        "git clone --branch distribution ssh://git@h/larkdocio.git vendor",
        "git clone --branch distro --depth 1 <larkdocio-url> vendor",
        "git clone --branch=distribution <larkdocio-url> vendor",
        "git clone <larkdocio-url> vendor  # not --branch dist, the whole dev repo",
    ):
        assert dev_repo_clone_lines(laundered), (
            f"a dev-repo clone was exempted by characters that are not the `--branch` "
            f"argument: {laundered!r}"
        )

    # …and the real argument is still exempt, in every spelling that actually clones `dist`.
    for artifact in (
        "git clone --branch dist --depth 1 <larkdocio-url> vendor   # 0. get the wheel",
        "git clone --branch=dist --depth 1 <larkdocio-url> vendor",
        "git clone --depth 1 --branch dist <larkdocio-url> vendor",
        "git clone -b dist --depth 1 <larkdocio-url> vendor",
    ):
        assert not dev_repo_clone_lines(artifact), (
            f"the artifact clone was reported as a dev-repo clone: {artifact!r}"
        )


def test_ac1_the_clone_predicate_has_exactly_ONE_definition():
    """LD-205's second half: ``tests/test_role_router_readme.py`` re-implemented this predicate
    inline, so a fix could land in one copy and not the other. There is now one definition,
    in ``tests/front_door.py`` beside the rest of the front-door helpers, and both modules
    call **it** — asserted by identity, because a comment saying so cannot be tested."""
    import test_role_router_readme as router

    assert dev_repo_clone_lines is fd.dev_repo_clone_lines
    assert router.dev_repo_clone_lines is fd.dev_repo_clone_lines


#: AC1's six steps, as the shape each is checked by. Two are shell (install, credentials) and
#: four are Python; the fourth is the one the whole section exists to deliver, because the guide
#: it prints is where the good documentation already lives.
_SIX_STEPS = (
    ("1. install", "pip install"),
    ("2. credentials", ".env"),
    ("3. load them", "init_env("),
    ("4. read the guide", "print(larkdocio.guide())"),
    ("5. one read", "get_docx_content("),
    ("6. one write", "dry_run("),
)


def _quickstart_section(readme):
    """The text from the first ``## Quickstart`` heading to the next ``## `` heading."""
    lines = readme.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## Quickstart"))
    end = next(
        (i for i, line in enumerate(lines[start + 1:], start=start + 1)
         if line.startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def test_ac1_the_quickstart_demonstrates_all_six_steps(readme):
    """Each of the six is *shown*, not described: the read is a real call, the write is the real
    plan gate, and the guide is a line someone runs."""
    section = _quickstart_section(readme)
    missing = [label for label, needle in _SIX_STEPS if needle not in section]
    assert not missing, f"the quickstart never shows {missing}"


def test_ac1_the_quickstart_numbers_its_steps_so_a_reader_can_count_them(readme):
    """Six numbered steps, in order, across the section's fences — the promise the heading
    makes has to be checkable by the reader who reads it."""
    section = _quickstart_section(readme)
    numbers = [int(m.group(1)) for m in re.finditer(r"#\s*(\d)\.\s", section)]
    assert numbers == [1, 2, 3, 4, 5, 6], (
        f"the quickstart's numbered steps read {numbers} — six, in order, is the promise"
    )


def test_ac1_the_development_material_is_behind_the_development_heading(development_half):
    """Nothing is deleted — contributors still need every word of it. It moves."""
    assert development_half, f"the README has no {fd.DEVELOPMENT_HEADING!r} section"
    for needle in ("./setup.sh", "Package layout", "Consuming larkdocio", "pytest"):
        assert needle in development_half, (
            f"{needle!r} is not in the development half — it was deleted rather than moved"
        )


def test_ac1_the_development_half_declares_itself_dev_repo_only(development_half):
    """One note under the ``##`` heading, which is exactly the scope the citation guard reads —
    so every ``###`` subsection beneath inherits it and no fourteen-row table needs per-row
    labels."""
    head = "\n".join(development_half.splitlines()[:12])
    # LD-699: the development half is the CLONE — the source-repository label, not the private one.
    assert prose(fd.SOURCE_REPO_LABEL) in prose(head), (
        f"the development half must open by saying its contents are {fd.SOURCE_REPO_LABEL!r}"
    )


# =====================================================================
# AC2 — LD-167's BIDIRECTIONAL LAYOUT GUARD MOVED WITH THE TABLE
#
# THE RISK OF THIS WHOLE CHANGE. A restructure that reds a bidirectional
# guard and then relaxes it trades the audience fix for the truth fix —
# a net loss. So: the guard is not weakened (it is *strengthened* to an
# exact equality), it is pinned to the table's NEW home, and every
# direction is re-proved THROUGH THE REAL PARSE over the MOVED text.
# =====================================================================

def test_ac2_the_layout_table_now_lives_in_the_development_half(readme):
    """Where the table is, is now itself a checked claim — because "the table is correct" and
    "the table is in the half its reader can use" are different facts, and the second one is
    what this change is about."""
    heading, _start = fd.layout_table_section(readme)
    assert heading is not None, "no package-layout row could be found in the README at all"
    assert heading == fd.DEVELOPMENT_HEADING, (
        f"the package-layout table sits under {heading!r} — a table of `src/…` paths belongs "
        f"under {fd.DEVELOPMENT_HEADING!r}, where the reader has that tree"
    )


def test_ac2_every_layout_row_is_in_the_development_half(readme, development_half):
    """Not merely the first row: the whole table travelled, so a split table cannot pass."""
    offset = len(readme.splitlines()) - len(development_half.splitlines())
    stragglers = [n for n in fd.layout_table_rows(readme) if n <= offset]
    assert not stragglers, (
        f"layout rows at lines {stragglers} are still above the development heading"
    )


def test_ac2_the_moved_table_is_held_EXACTLY_equal_to_the_real_top_level(development_half):
    """The guard at its new home, and **stronger than it travelled with**: an equality, not a
    two-way diff over the whole file. Parsed from the development half alone, so a row that
    stayed behind in the consumer half cannot satisfy it."""
    documented = fd.documented_layout_paths(development_half)
    assert documented == fd.real_top_level(), (
        "the moved package-layout table and the real top level of src/larkdocio disagree: "
        f"missing rows {sorted(fd.real_top_level() - documented)}, "
        f"phantom rows {sorted(documented - fd.real_top_level())}"
    )


def test_ac2_adding_a_module_reddens_the_guard_AT_ITS_NEW_HOME(development_half):
    """Direction one, through the real parse of the MOVED text: a package ships with no row."""
    # LD-246: ``base/`` became REAL (and documented), so the probe moved to a name that
    # is not — the probe must be a package the README genuinely does not describe.
    invented = "src/larkdocio/nosuchpackage/"
    assert invented not in fd.real_top_level(), "the probe is stale; pick a name that is fake"
    documented = fd.documented_layout_paths(development_half)
    undocumented, _phantom = fd.two_way_diff(documented, fd.real_top_level() | {invented})
    assert undocumented == [invented], (
        f"a new package with no row did not redden the moved guard: {undocumented}"
    )


def test_ac2_removing_a_row_from_the_MOVED_table_reddens(development_half):
    """Direction two, through the real parse: delete a row from the development half's **text**
    and the module it described is reported missing. The parse is part of what is under test —
    a table parser that silently returned nothing after the move would pass direction one
    forever, which is precisely how a bidirectional guard becomes unidirectional."""
    victim = "src/larkdocio/comments/"
    stripped = "\n".join(
        line for line in development_half.splitlines()
        if not (line.strip().startswith("|") and f"`{victim}`" in line)
    )
    documented = fd.documented_layout_paths(stripped)
    assert victim not in documented, "the row was not actually removed; the probe is stale"
    undocumented, _phantom = fd.two_way_diff(documented, fd.real_top_level())
    assert undocumented == [victim]


def test_ac2_a_phantom_row_in_the_MOVED_table_reddens(development_half):
    """The other half of direction two, after the move: a row naming something absent."""
    invented = "| `src/larkdocio/telepathy/` | Reads the user's mind. |"
    documented = fd.documented_layout_paths(development_half + "\n" + invented)
    _undocumented, phantom = fd.two_way_diff(documented, fd.real_top_level())
    assert phantom == ["src/larkdocio/telepathy/"]


def test_ac2_the_section_pin_bites_when_the_table_drifts_back_out(readme):
    """The new half of the guard, red-proved: a layout table under a consumer-facing heading is
    reported as such. Without this the section claim would be an assertion nobody can fail."""
    rows = fd.layout_table_rows(readme)
    assert rows, "no layout rows to relocate; the probe is stale"
    relocated = "# larkdocio\n\n## Quickstart\n\n| Path | What |\n|---|---|\n" + "\n".join(
        line for line in readme.splitlines()
        if line.strip().startswith("|") and "`src/larkdocio/" in line
    )
    heading, _start = fd.layout_table_section(relocated)
    assert heading == "## Quickstart", heading
    assert heading != fd.DEVELOPMENT_HEADING


def test_ac2_the_row_finder_and_the_path_parser_agree_on_what_a_row_is(readme):
    """The two functions the AC2 assertions lean on must be the *same* rule seen two ways, or
    the section pin could be measuring a different table than the equality does."""
    assert len(fd.layout_table_rows(readme)) == len(fd.documented_layout_paths(readme))


def test_ac2_the_row_finder_ignores_prose_paths_exactly_as_the_parser_does():
    """The must-not-bite, inherited: only a table's FIRST COLUMN is a layout claim."""
    prose_only = (
        "Handler mechanics live in `src/larkdocio/blocks/BLOCK_TYPES.md`.\n"
        "\n| Path | What it is |\n|---|---|\n| `src/larkdocio/read/` | The reader. |\n"
    )
    assert fd.layout_table_rows(prose_only) == [5]
    assert fd.documented_layout_paths(prose_only) == {"src/larkdocio/read/"}


def test_ac2_no_fenced_comment_can_hijack_the_development_halfs_label_scope(development_half):
    """The trap this restructure walked into, once, and paid for in a debugging round.

    ``front_door.section_of_line`` treats **any** line matching ``#{1,6} `` as a heading, and a
    ``# comment`` at the start of a line inside a fenced shell block matches. The development
    half is full of shell. Such a line silently becomes "the section" for every citation below
    it, orphaning the single dev-repo note at the top of the half — which is exactly what
    happened: a ``# 3. Run it.`` comment in the clone quickstart made the layout table report
    its section as ``'# 3. Run it.'`` and turned fourteen labelled citations into offenders.

    The section-scoped helper was deliberately **left alone** — it is LD-167's, it is what the
    travelling guard reads, and quietly making it fence-aware would loosen the scope it grants a
    label. The document was changed instead, and this is the guard that keeps it that way.
    """
    offenders = []
    in_fence = False
    for lineno, line in enumerate(development_half.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and re.match(r"^#{1,6}\s", line):
            offenders.append((lineno, line))
    assert not offenders, (
        f"these fenced comment lines read as Markdown headings to the section-scoped citation "
        f"guard, which orphans the development half's dev-repo note: {offenders}. Put the "
        f"commentary in prose above the fence, or indent the comment."
    )


def test_ac2_the_travelling_guard_is_not_weakened_the_whole_file_still_agrees(readme):
    """LD-167's own assertion, restated here so this module fails too if the restructure ever
    trades it away: the whole-file two-way diff — the exact check that travelled — still holds
    after the move, unmodified."""
    undocumented, phantom = fd.two_way_diff(
        fd.documented_layout_paths(readme), fd.real_top_level()
    )
    assert not undocumented and not phantom


# =====================================================================
# AC3 — the thirty-seven dangling citations
# =====================================================================

#: The counted classes, as the audit counted them. Each is a path shape a wheel-only reader
#: cannot resolve; the counts are what made this a Major rather than a nit.
#:
#: ``TOOLS.md (×4)`` **left this table** — the exit condition stated below, exercised. The
#: config schema it was the only home of is now a generated region the **packaged guide**
#: carries too, so the consumer-facing pointer names a document a wheel reader can open and
#: the class is fixed rather than merely counted. The label-blind whole-half guard
#: (``test_ac3_the_consumer_half_cites_nothing_the_wheel_does_not_carry``) still covers it, and
#: ``tests/test_download_output_docs.py`` re-injects a ``TOOLS.md`` citation into the real consumer
#: half to prove the guard it left behind still bites.
_COUNTED_CLASSES = (
    ("src/larkdocio/… (×17)", "src/larkdocio/"),
    ("consumers/… (×9)", "consumers/"),
    (".env.example (×4)", ".env.example"),
    ("BLOCKS.md (×3)", "BLOCKS.md"),
)


def test_ac3_the_consumer_half_cites_nothing_the_wheel_does_not_carry(consumer_half):
    """Label-blind and deliberately so. Repo-wide, a labelled dev-repo pointer is fine — a
    contributor has the clone. In the half addressed to someone holding only an install, the
    label does not conjure the file, so the right number is zero."""
    offenders = fd.unshipped_citations(consumer_half)
    assert not offenders, (
        f"the consumer half sends a wheel-only reader to files the wheel does not carry "
        f"{offenders} — every one of these belongs below {fd.DEVELOPMENT_HEADING!r}"
    )


@pytest.mark.parametrize("label,token", _COUNTED_CLASSES, ids=[c[0] for c in _COUNTED_CLASSES])
def test_ac3_each_counted_class_is_at_zero_in_the_consumer_half(label, token, consumer_half):
    """Per class, so a failure names *which* of the five came back."""
    offenders = [
        (lineno, raw) for lineno, raw in fd.unshipped_citations(consumer_half) if token in raw
    ]
    assert not offenders, f"{label} still dangles in the consumer half: {offenders}"


@pytest.mark.parametrize("label,token", _COUNTED_CLASSES, ids=[c[0] for c in _COUNTED_CLASSES])
def test_ac3_each_counted_class_SURVIVES_in_the_development_half(
        label, token, development_half):
    """The other half of AC3, and the reason the guard is split rather than whole-file: these
    are legitimate contributor documentation. A "fix" that reached zero by deleting them would
    pass the test above and fail the project.

    Asserted over real **citations**, not over a substring of the prose. The mutation battery
    is why: deleting every real ``consumers/`` pointer left the word alive in the development
    half's own dev-repo note, so a substring check passed a document that had thrown the
    material away. A guard that a mere mention satisfies is not guarding the material.
    """
    cited = [raw for _lineno, raw in fd.cited_repo_paths(development_half) if token in raw]
    assert cited, (
        f"{label} is no longer CITED anywhere in the development half — moved, not deleted, "
        f"was the contract"
    )


def test_ac3_the_repo_wide_label_guard_still_holds(readme):
    """The travelling citation guard, restated: every remaining dev-repo citation anywhere in
    the document is labelled, section-scoped, exactly as it was."""
    assert not fd.unlabelled_dev_repo_citations(readme)


def test_ac3_the_label_blind_check_bites_where_the_label_aware_one_does_not():
    """The distinction between the two guards, red-proved in one test — otherwise the new
    function is indistinguishable from the old one and one of them is dead weight."""
    labelled_but_absent = (
        "## Quickstart\n\nThe files below are in the dev repo, not the wheel.\n\n"
        "See [`TOOLS.md`](TOOLS.md) for the CLI contract.\n"
    )
    assert not fd.unlabelled_dev_repo_citations(labelled_but_absent), (
        "the label-aware guard is satisfied — which is correct, and is why it cannot police "
        "the consumer half on its own"
    )
    assert [raw for _n, raw in fd.unshipped_citations(labelled_but_absent)] == ["TOOLS.md"]


def test_ac3_the_label_blind_check_permits_a_PACKAGED_citation():
    """The must-not-bite: a doc the wheel really carries is not a dangling reference, so the
    guard cannot be satisfied by removing all pointers indiscriminately."""
    packaged = "## Quickstart\n\nSee [`src/larkdocio/GUIDE.md`](src/larkdocio/GUIDE.md).\n"
    assert not fd.unshipped_citations(packaged)


def test_ac3_the_halves_split_is_not_vacuous(readme, consumer_half, development_half):
    """Both halves are real text, and they reconstruct the document exactly — a split helper
    that silently returned everything on one side would green every AC3 assertion at once."""
    assert consumer_half and development_half
    assert consumer_half + development_half == readme
    assert fd.DEVELOPMENT_HEADING not in consumer_half


def test_ac3_a_document_with_no_development_heading_fails_rather_than_passes():
    """The pre-fix shape: no heading ⇒ everything is the consumer half ⇒ the citations are
    reported. A split that defaulted the other way would have made this whole section vacuous
    on exactly the document it was written against."""
    pre_fix = "# larkdocio\n\n## Package layout\n\nSee [`TOOLS.md`](TOOLS.md).\n"
    consumer, development = fd.split_at_development_heading(pre_fix)
    assert development == ""
    assert [raw for _n, raw in fd.unshipped_citations(consumer)] == ["TOOLS.md"]


# =====================================================================
# AC4 — runnable Python exists, the guide line is one of them, and the
#       quickstart EXECUTES.
# =====================================================================

def test_ac4_the_consumer_half_contains_runnable_python(consumer_half):
    """``grep -c '```python' README.md → 0`` cannot come back."""
    fences = fd.python_fences(consumer_half)
    assert fences, (
        "the consumer half contains no ```python block — the measured condition was that a "
        "Python library's front door held not one line of Python in 322 lines"
    )
    for source in fences:
        compile(source, "<README consumer half>", "exec")


def test_ac4_print_guide_appears_as_a_RUNNABLE_LINE_near_the_top(readme):
    """The exact complaint: the one line that matters was in prose at line 36 and never as
    code. It is now a line inside a python fence, near the top, on its own."""
    hits = fd.fenced_line_numbers(readme, "print(larkdocio.guide())")
    assert hits, (
        "`print(larkdocio.guide())` appears nowhere as a runnable line — a prose mention is "
        "what the document already had"
    )
    assert hits[0] <= fd.GUIDE_LINE_BUDGET, (
        f"the first runnable `print(larkdocio.guide())` is at line {hits[0]}, past the "
        f"{fd.GUIDE_LINE_BUDGET}-line budget"
    )


def test_ac4_the_runnable_line_detector_tells_code_from_prose():
    """Red-proof both ways, or the assertion above could be passing on the pre-fix prose."""
    prose_only = (
        "# x\n\nThe real onboarding is `print(larkdocio.guide())`, one line.\n"
    )
    assert fd.fenced_line_numbers(prose_only, "print(larkdocio.guide())") == []
    as_code = "# x\n\n```python\nimport larkdocio\nprint(larkdocio.guide())   # the guide\n```\n"
    assert fd.fenced_line_numbers(as_code, "print(larkdocio.guide())") == [5]
    # …and a bash fence is not a python one.
    shell = "# x\n\n```bash\nprint(larkdocio.guide())\n```\n"
    assert fd.fenced_line_numbers(shell, "print(larkdocio.guide())") == []


def _quickstart_fences(readme):
    """The quickstart section's python blocks — the read one, then the write one."""
    return fd.python_fences(_quickstart_section(readme))


def test_ac4_the_quickstart_ships_three_self_contained_python_blocks(readme):
    """The guide block, the read block, the write block — in that order, and each one
    **self-contained** (its own imports, its own ``init_env``), because each is executed in a
    builtins-only namespace exactly as a consumer's own file is. A block that leaned on the
    previous one's variables is the ``NameError``-on-paste defect."""
    fences = _quickstart_fences(readme)
    assert len(fences) == 3, f"expected guide + read + write blocks, got {len(fences)}"
    guide_block, read_block, write_block = fences
    assert "print(larkdocio.guide())" in guide_block
    assert "get_docx_content" in read_block and "dry_run" not in read_block
    assert "dry_run" in write_block and "apply(" in write_block
    for source in fences:
        assert "init_env(" in source, f"a quickstart block skips init_env: {source!r}"
        assert source.lstrip().startswith(("import ", "from ")), (
            f"a quickstart block does not import what it uses: {source!r}"
        )


def test_ac4_the_quickstart_READ_block_EXECUTES_offline(readme, monkeypatch, tmp_path):
    """The amplifier, and the class this batch has already caught three times: an unrunnable
    quickstart is the same defect one layer along. The block is extracted from the shipped
    README **verbatim** and executed in a builtins-only namespace on the same offline stage the
    guide's own recipes run on — only the network boundary is replaced, so the parser, the node
    tree and the renderer are all the shipped code."""
    source = _quickstart_fences(readme)[1]
    stage = gr.stage(monkeypatch, tmp_path)
    namespace = stage.run("readme-quickstart-read", source=source)
    assert stage.init_env_calls, "the quickstart never called init_env"
    markdown = namespace["markdown"]
    assert isinstance(markdown, str) and markdown.strip(), markdown
    assert "Revenue grew 12.4% in Q3." in markdown, markdown


def test_ac4_the_quickstart_WRITE_block_EXECUTES_offline(readme, monkeypatch, tmp_path):
    """The write half through the same runner: a real ``dry_run`` → a non-forgeable ``Plan``
    with the whole-document guard **armed** → a real ``apply`` that reports one applied edit."""
    source = _quickstart_fences(readme)[2]
    stage = gr.stage(monkeypatch, tmp_path)
    namespace = stage.run("readme-quickstart-write", source=source)
    plan = namespace["plan"]
    assert plan.revision_guard == "active", plan.to_dict()
    outcomes = [entry.to_dict()["outcome"] for entry in namespace["log"].entries]
    assert outcomes == ["applied"], [e.to_dict() for e in namespace["log"].entries]


@pytest.mark.parametrize("block", (1, 2), ids=("read", "write"))
def test_ac4_the_execution_harness_bites_on_a_broken_quickstart(
        block, readme, monkeypatch, tmp_path):
    """Red-then-green on the harness itself: the same runner that greens the shipped block
    fails when the block is mutated. Two mutations, both real failure modes — the credential
    line deleted (the line whose load-bearingness is the reason it is shown at all) and a
    public symbol renamed."""
    source = _quickstart_fences(readme)[block]
    stage = gr.stage(monkeypatch, tmp_path)

    without_env = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("init_env(")
    )
    assert without_env != source, "the block has no init_env line to delete"
    with pytest.raises(Exception):
        stage.run("readme-quickstart-mutated", source=without_env)

    renamed = source.replace("get_docx_content", "get_docx_contents")
    assert renamed != source
    with pytest.raises(AttributeError):
        stage.run("readme-quickstart-mutated", source=renamed)


def test_ac4_the_quickstart_read_recipe_produces_MARKDOWN_not_a_tree(
        readme, monkeypatch, tmp_path):
    """The level claim the quickstart makes, checked: step 6 hands back the Markdown
    projection, which is what "show me what this says" needs."""
    stage = gr.stage(monkeypatch, tmp_path)
    namespace = stage.run(
        "readme-quickstart-read", source=_quickstart_fences(readme)[1]
    )
    assert namespace["markdown"].lstrip().startswith("#"), namespace["markdown"][:200]


# =====================================================================
# AC5 — the package docstring names all FOUR surfaces, derived
# =====================================================================

def test_ac5_the_required_surface_set_is_derived_from_code_in_both_directions():
    """Not a hand-kept list: ``capabilities()``' surface ids intersected with the real
    sub-packages of ``src/larkdocio``. A token naming no package drops out, a package no
    surface claims drops out, and a new surface family in a new package widens the demand."""
    assert fd.surface_packages() == {
        "read", "write", "sheets", "base", "comments", "contacts", "drive"}
    assert "blocks" not in fd.surface_packages(), (
        "blocks/ is the shared block model, not a surface — it must not be demanded"
    )


def test_ac5_the_package_docstring_names_every_shipped_surface():
    """The reported defect: ``larkdocio.__doc__`` said **three** where the ``METADATA`` says
    four, omitting ``comments/`` — which is in ``dir(larkdocio)`` and has a whole read surface.
    Held as an EQUALITY, so an invented surface reddens as loudly as a dropped one."""
    named = fd.docstring_surface_packages(larkdocio.__doc__)
    assert named == fd.surface_packages(), (
        f"the package docstring names {sorted(named)}; the shipped surfaces are "
        f"{sorted(fd.surface_packages())}"
    )


def test_ac5_the_docstring_count_drift_guard_bites_in_both_directions():
    """Red-proof: drop a surface from a docstring-shaped string, and invent one."""
    all_but_one = ("``read/``, ``write/``, ``sheets/``, ``base/``, ``drive/`` and "
                   "``contacts/`` ship.")
    assert fd.docstring_surface_packages(all_but_one) != fd.surface_packages()
    assert fd.surface_packages() - fd.docstring_surface_packages(all_but_one) == {
        "comments"}
    invented = ("``read/`` ``write/`` ``sheets/`` ``base/`` ``comments/`` ``contacts/`` "
                "``drive/`` ``telepathy/``")
    assert fd.docstring_surface_packages(invented) - fd.surface_packages() == {
        "telepathy"}


def test_ac5_neither_capability_matrix_ships_in_the_wheel():
    """The premise of the next assertion, checked against ``package-data`` rather than assumed —
    if a matrix ever *is* packaged, the citation stops being a defect and this must be revisited."""
    packaged = fd.packaged_doc_paths()
    for name in fd.MATRIX_DOCS:
        assert name not in packaged


def test_ac5_the_docstring_cites_no_matrix_the_wheel_does_not_carry():
    """The second half of the report: the docstring cited ``/BLOCKS.md`` and ``/SHEETS.md``,
    neither of which is in the wheel — so ``help(larkdocio)`` sent an installed reader to two
    paths that do not exist for them."""
    offenders = fd.unlabelled_matrix_citations(larkdocio.__doc__)
    assert not offenders, (
        f"the package docstring names {offenders} with no {fd.DEV_REPO_LABEL!r} label, and the "
        f"wheel carries neither — point at capabilities() / guide(full=True) instead"
    )


def test_ac5_the_matrix_citation_detector_bites_and_respects_the_label():
    """Red-proof plus the must-not-bite, so the labelled form stays available to anyone who
    needs it."""
    assert fd.unlabelled_matrix_citations("the matrix is ``/BLOCKS.md``") == ["BLOCKS.md"]
    assert fd.unlabelled_matrix_citations(
        "In the dev repo, the matrices are ``/BLOCKS.md`` and ``/SHEETS.md``."
    ) == []
    assert fd.unlabelled_matrix_citations("no matrix named here") == []


def test_ac5_the_docstring_points_at_the_accessors_a_wheel_reader_actually_has():
    """The replacement has to be *useful*, not merely correct: what a matrix answered offline is
    what ``capabilities()`` and ``guide()`` answer from an install."""
    doc = prose(larkdocio.__doc__)
    for phrase in ("capabilities()", "guide()"):
        assert prose(phrase) in doc, f"the docstring no longer points at {phrase}"


# =====================================================================
# AC6 — the BUILT wheel's METADATA, because the artifact is the deliverable
# =====================================================================

def _metadata_body():
    """The ``METADATA`` body of the wheel in ``dist/``, or ``None``."""
    wheel = fd.built_wheel()
    if wheel is None:
        return None
    return fd.wheel_metadata(wheel).split("\n\n", 1)[1]


def test_ac6_the_built_wheels_metadata_carries_the_consumer_first_front_door():
    """A source-only assertion would pass while ``pip show`` stayed wrong, which is the exact
    gap this AC names. Skips on a plain checkout (``pytest`` runs before ``build`` in
    ``verify.sh`` and this venv has no setuptools); ``python -m build`` arms it."""
    body = _metadata_body()
    if body is None:
        pytest.skip("no built wheel for the declared version in dist/ — run `python -m build`")

    consumer, development = fd.split_at_development_heading(body)
    assert development, "the shipped METADATA body has no development heading"
    present = [n for n in _IMPOSSIBLE_FROM_A_WHEEL if n in consumer]
    assert not present, f"the SHIPPED METADATA still opens by asking for {present}"
    assert fd.python_fences(consumer), "the shipped METADATA body carries no python block"
    hits = fd.fenced_line_numbers(body, "print(larkdocio.guide())")
    assert hits and hits[0] <= fd.GUIDE_LINE_BUDGET, hits


def test_ac6_the_shipped_metadata_body_really_is_this_readme():
    """Why guarding the README guards the wheel — restated over the *new* opening, so the tie
    is re-proved after the restructure rather than inherited from before it."""
    body = _metadata_body()
    if body is None:
        pytest.skip("no built wheel for the declared version in dist/ — run `python -m build`")
    assert prose(fd.first_screenful(fd.readme_text(), 12)) in prose(body)


def test_ac6_the_consumer_experiment_rerun_the_first_instruction_is_executable():
    """The audit's own experiment as the acceptance test: read ONLY what ``pip show`` gives you,
    and check that the first fenced instruction is something a reader with an install can run."""
    body = _metadata_body()
    if body is None:
        pytest.skip("no built wheel for the declared version in dist/ — run `python -m build`")
    first_fence = re.search(r"^```(\w*)[ \t]*\n(.*?)^```", body, re.MULTILINE | re.DOTALL)
    assert first_fence, "the shipped METADATA body has no fenced instruction at all"
    language, block = first_fence.group(1), first_fence.group(2)
    assert language in ("bash", "python"), language
    assert not [n for n in _IMPOSSIBLE_FROM_A_WHEEL if n in block], block
    assert "pip install" in block, (
        f"the first instruction a wheel reader meets is {block!r} — it must start from the "
        f"install they already have"
    )
