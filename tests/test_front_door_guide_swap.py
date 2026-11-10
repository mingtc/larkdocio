"""LD-468 — the front-door swap: ``guide()`` opens on the INDEX, the document moves behind a flag.

**The defect this file pins closed.** ``guide()`` with no argument returned the whole packaged
document — 563,718 characters at the time it was measured, *"a context-window incident for the
agent consumers this library is visibly built for"* — while the thing eight dogfood runs called
the best onboarding surface in the library, the failure-named section index, was the SECOND thing
a consumer found, by luck (`dev/dogfood4/verdict-grid.md` § 3 heat-map row 5; § 6 item 3). The maintainer
ruled it in two words: **"swap it"**.

So, after this issue:

* ``guide()`` → the **index**: one row per section, each row literally the call that fetches it,
  with a header that names the other two calls. Small enough to read in one breath and **bounded
  by a guard** (``test_ac4_the_default_is_BOUNDED_in_size``) so this specific regression — the
  default growing without limit — cannot recur silently.
* ``guide(full=True)`` → the **document**, byte for byte as the wheel carries it. Nothing about
  the bytes changed; only which call spells them.
* ``guide(section=…)``, the slug matching and the names-every-section ``ValueError`` are
  **untouched**, and the CLI (``larkdocio guide`` / ``--section`` / ``--full``) mirrors all three.

Every claim below is written against the packaged resource or against ``guide_sections()`` — never
against a copy of the index in this file — because the index is derived at call time and a pinned
copy here would be exactly the second copy the module refuses to keep.
"""

import inspect
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

import larkdocio
from larkdocio.capabilities import capabilities
from larkdocio.cli import cli
from larkdocio.guide import GUIDE_RESOURCE, guide, guide_sections
from test_index_ratio import is_index_sized  # LD-640 AC5: one spelling of the 20x ratio
from domain_vocabulary import RETIRED_ID

REPO_ROOT = Path(__file__).resolve().parents[1]


def run(args):
    return CliRunner().invoke(cli, args, catch_exceptions=True)


def packaged_text():
    """The wheel's own bytes for ``GUIDE.md``, read the way the accessor reads them."""
    import importlib.resources as resources

    return resources.files("larkdocio").joinpath(GUIDE_RESOURCE).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def index():
    return guide()


@pytest.fixture(scope="module")
def rows():
    return guide_sections()


# --------------------------------------------------------------------------- #
# AC1 — the no-argument default IS the index                                    #
# --------------------------------------------------------------------------- #

def test_ac1_the_no_argument_call_returns_the_index_not_the_document(index):
    """The swap itself. Stated in both directions so neither half can rot: what comes back is
    not the document, and it is not merely *smaller* than the document — it is the index."""
    document = packaged_text()
    assert index != document
    assert is_index_sized(len(index), len(document)), (
        f"the default is {len(index):,} chars against a {len(document):,}-char document; "
        "this is supposed to be an index, not a slightly shorter dump"
    )
    assert isinstance(index, str), "guide()'s return type must not change"
    assert index.endswith("\n")


def test_ac1_every_section_the_document_has_is_named_in_the_index(index, rows):
    """Complete in one direction: no section is unreachable because the index forgot it."""
    for row in rows:
        assert row["slug"] in index, f"the index never names {row['slug']!r}"
        assert row["heading"] in index, f"the index never shows the heading {row['heading']!r}"


def test_ac1_the_index_names_no_section_the_document_does_not_have(index, rows):
    """Complete in the other direction: every ``guide("…")`` call the index prints is a call
    that works. Read off the rendered text, not off the rows it was built from."""
    import re

    printed = {
        slug for slug in re.findall(r'guide\("([^"]+)"\)', index) if slug != "<slug>"
    }  # the header's own placeholder is teaching, not a row
    assert printed == {row["slug"] for row in rows}
    for slug in sorted(printed):
        assert guide(section=slug).startswith("#")


def test_ac1_the_index_is_SELF_DOCUMENTING_about_the_next_call(index):
    """A consumer's first call must leave them knowing their second. The index states the
    one-section call, the whole-document call, and the data form of itself."""
    for claim in (
        'larkdocio.guide("',            # one section
        "larkdocio.guide(full=True)",   # everything
        "larkdocio.guide_sections()",   # the same index as data
        "larkdocio guide --section",    # the CLI spellings, both of them
        "larkdocio guide --full",
    ):
        assert claim in index, f"the index never tells a reader about {claim!r}"


def test_ac1_the_index_says_how_many_sections_and_how_big_the_document_is(index, rows):
    """The two numbers that let a caller decide whether to ask for the whole thing."""
    assert f"{len(rows)} sections" in index
    assert f"{len(packaged_text()):,} characters" in index


def test_ac1_the_index_is_DERIVED_from_the_packaged_document_on_every_call(monkeypatch):
    """Not a snapshot: swap the document and the index follows it, with no code change. This
    is the same derive-at-call-time contract ``guide_sections()`` has always kept."""
    import importlib

    guide_module = importlib.import_module("larkdocio.guide")  # the MODULE, not the re-export
    fake = "# Doc\n\n## A heading here\n\ntext\n\n### A nested one\n\nmore\n"
    monkeypatch.setattr(guide_module, "_packaged", lambda *_a, **_k: fake)
    text = guide_module.guide()
    assert "A heading here" in text and "a-heading-here" in text
    assert "A nested one" in text and "a-nested-one" in text
    assert "2 sections" in text
    assert "Recipes" not in text, "the real document leaked into a derived index"


def test_ac1_the_nesting_is_visible_in_the_index(index, rows):
    """``level`` is what tells a reader a row CONTAINS the rows under it, so the rendering has
    to carry it. Indentation is that carrier: a ``###`` row sits deeper than the ``##`` above."""
    depths = {}
    for row in rows:
        line = next(l for l in index.splitlines() if f'guide("{row["slug"]}")' in l)
        depths.setdefault(row["level"], set()).add(len(line) - len(line.lstrip(" ")))
    assert set(depths) == {2, 3}
    assert len(depths[2]) == 1 and len(depths[3]) == 1
    assert min(depths[3]) > min(depths[2]), "a ### row is not indented under its ## parent"


# --------------------------------------------------------------------------- #
# AC2 — the document lives behind ONE explicit argument, byte for byte          #
# --------------------------------------------------------------------------- #

def test_ac2_full_true_is_the_packaged_resource_VERBATIM():
    """Not "equivalent" — the same bytes the wheel carries. This is the assertion that used to
    ride on the no-argument call (``test_guide_sections.py``); it is transformed, not dropped."""
    packaged = packaged_text()
    assert guide(full=True) == packaged
    assert guide(full=True).encode("utf-8") == packaged.encode("utf-8")


def test_ac2_the_full_path_does_not_route_through_the_section_machinery():
    """The whole-document answer is still the resource read — no slicing, joining or
    normalization between the file and the caller. Proved by making the index explode."""
    import importlib

    guide_module = importlib.import_module("larkdocio.guide")  # the MODULE, not the re-export

    def exploding(*_args, **_kwargs):
        raise AssertionError("guide(full=True) must not build the section index")

    original = guide_module._bounded_sections
    guide_module._bounded_sections = exploding
    try:
        assert guide(full=True) == packaged_text()
        # …and the DEFAULT path must, which is what makes the probe above non-vacuous and is
        # the new half of the contract: the index is derived, never stored.
        with pytest.raises(AssertionError):
            guide()
        with pytest.raises(AssertionError):
            guide(section="anything")
    finally:
        guide_module._bounded_sections = original


def test_ac2_the_signature_carries_both_and_full_is_keyword_only():
    signature = inspect.signature(guide)
    assert list(signature.parameters) == ["section", "full"]
    assert signature.parameters["section"].default is None
    assert signature.parameters["section"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    full = signature.parameters["full"]
    assert full.default is False
    assert full.kind is inspect.Parameter.KEYWORD_ONLY, (
        "full must be keyword-only: guide('x') has always meant a SECTION and a positional "
        "second argument would let a caller write guide('x', True) and mean neither"
    )


def test_ac2_section_behavior_is_UNCHANGED(rows):
    """The half the swap may not touch: slug and heading matching, case-insensitivity, the
    nesting rule, and a refusal that names every section there is.

    **TRANSFORMED, not struck (LD-592 / supersession).** The enumeration invariant — the refusal
    names EVERY section — is unchanged and still asserted below, and so is every matching rule.
    What moved is the pinned phrasing: ``the {n} it has are`` hard-coded a plural, so a
    one-section document read *"the 1 it has are"*. The verb now agrees with the count through
    the shared ``guide._agreeing`` helper, so the phrase is pinned here **as a function of this
    document's own count** rather than as a fixed string — which is what makes it keep biting on
    a document of any size. This document has many sections, so the bytes it emits are byte-for-
    byte what they were; the singular arm is pinned on a synthetic one-section document in
    ``test_ld592_…::test_ac7_the_unknown_section_refusal_reads_grammatically_at_one_section``.
    """
    row = next(r for r in rows if r["level"] == 2)
    by_slug = guide(section=row["slug"])
    assert by_slug == guide(section=row["heading"].upper())
    assert by_slug == guide(section=f"  {row['slug']}  ")
    assert by_slug.startswith("## ")
    with pytest.raises(ValueError) as refusal:
        guide(section="no-such-section-here")
    message = str(refusal.value)
    verb = "is" if len(rows) == 1 else "are"
    assert f"the {len(rows)} it has {verb}:" in message, message
    for other in rows:
        assert other["slug"] in message


def test_ac2_asking_for_a_section_AND_the_whole_document_refuses_typed(rows):
    """Two mutually exclusive requests in one call is a caller error, and it is answered the
    way this module answers every other one: a ``ValueError`` that says what to do instead."""
    with pytest.raises(ValueError) as refusal:
        guide(section=rows[0]["slug"], full=True)
    message = str(refusal.value)
    assert "full=True" in message and "section" in message


# --------------------------------------------------------------------------- #
# AC3 — the CLI door follows the same rule                                      #
# --------------------------------------------------------------------------- #

def test_ac3_the_cli_default_is_the_index_and_equals_the_api():
    result = run(["guide"])
    assert result.exit_code == 0, result.output
    assert result.stdout == guide()
    assert result.stderr == ""


def test_ac3_the_full_flag_exists_and_prints_the_document_byte_for_byte():
    option = next(
        (param for param in cli.commands["guide"].params if "--full" in param.opts), None
    )
    assert option is not None, "`larkdocio guide` has no --full option"
    assert option.is_flag and option.default is False
    assert option.opts == ["--full"], "no short alias is ruled; do not add one"
    result = run(["guide", "--full"])
    assert result.exit_code == 0, result.output
    assert result.stdout == packaged_text()


def test_ac3_the_two_flags_together_refuse_with_an_EMPTY_stdout(tmp_path):
    result = run(["guide", "--full", "--section", "recipes"])
    assert result.exit_code != 0
    assert result.stdout == "", "a refusal wrote to stdout; a shell redirect is half-written"
    assert "--full" in result.stderr and "--section" in result.stderr
    assert "Traceback (most recent call last)" not in result.stderr
    # …and in a real child process with a real redirect, the file is left empty.
    out = tmp_path / "out.md"
    with out.open("wb") as handle:
        proc = subprocess.run(
            [sys.executable, "-m", "larkdocio.cli", "guide", "--full", "--section", "recipes"],
            cwd=str(tmp_path), stdout=handle, stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO_ROOT / "src"),
                 "PYTHONDONTWRITEBYTECODE": "1"},
        )
    assert proc.returncode != 0
    assert out.read_bytes() == b""


def test_ac3_the_help_page_documents_the_new_default_and_the_full_flag():
    page = " ".join(run(["guide", "--help"]).stdout.split())
    assert "--full" in page
    for claim in ("index", "--section", "whole"):
        assert claim in page, f"the guide help never says {claim!r}"
    assert "LD-" not in page and not RETIRED_ID.search(page), "internal dialect in a shipped help page"


def test_ac3_the_cli_still_writes_no_logic_of_its_own():
    """The pass-through claim, re-checked against the new flag: the CLI decides nothing about
    what the index is or what a section is — it surfaces what ``guide()`` returns."""
    source = (REPO_ROOT / "src" / "larkdocio" / "cli.py").read_text(encoding="utf-8")
    for forbidden in ("_slugify", "_section_text", "_bounded_sections", "guide_sections",
                      "GUIDE_SECTION_LEVELS", "_index_text"):
        assert forbidden not in source, (
            f"cli.py re-implements guide.py's machinery ({forbidden!r})"
        )


# --------------------------------------------------------------------------- #
# AC4 — the guard the old shape LACKED: the default is bounded                  #
# --------------------------------------------------------------------------- #

#: The ceiling on ``guide()``'s no-argument answer, in characters. A budget, never a target.
#: The measured index at LD-468's landing is ~10 KB for ~100 sections; the ceiling is set at
#: **32,768** so a genuine doubling of the guide's section count still fits, while the failure
#: this issue exists to close — the default quietly becoming a document again — reddens long
#: before it reaches a context window. Raising it is allowed; raising it silently is not, and
#: raising it to hold prose rather than rows is the regression itself.
DEFAULT_ANSWER_CEILING = 32_768


def test_ac4_the_default_is_BOUNDED_in_size(index):
    assert len(index) <= DEFAULT_ANSWER_CEILING, (
        f"guide() now returns {len(index):,} characters, over the "
        f"{DEFAULT_ANSWER_CEILING:,} ceiling. If the guide legitimately grew, raise the "
        "ceiling WITH ITS REASON; if the default started carrying text instead of names, "
        "that is the LD-468 regression itself"
    )


def test_ac4_the_index_carries_NAMES_not_TEXT(index, rows):
    """The bound above is a symptom check; this is the mechanism. Every line of the index is a
    header line or one row, and a row is a few dozen bytes — so no section's body can hide in
    it. Measured against the document's own biggest section."""
    biggest = max(len(guide(section=row["slug"])) for row in rows)
    assert biggest > len(index), (
        "the whole index is larger than the largest section of the document it indexes; it is "
        "carrying text"
    )
    body_lines = [
        l for l in index.splitlines()
        if 'guide("' in l and l.startswith(" ") and "<slug>" not in l
    ]
    assert len(body_lines) == len(rows)
    # A row is its own heading, its slug and the call syntax around them — nothing else. Bound
    # each row by ITS OWN heading rather than by a flat number, so a document with one very long
    # heading (this one has a 100+ character heading) stays passable while a row that started
    # carrying a sentence of body text does not.
    for row in rows:
        line = next(l for l in body_lines if f'guide("{row["slug"]}")' in l)
        assert len(line) <= len(row["heading"]) + len(row["slug"]) + 40, (
            f"the index row for {row['slug']!r} carries more than the name: {line!r}"
        )


# --------------------------------------------------------------------------- #
# AC6 — the registry's own pointers still describe what guide() does            #
# --------------------------------------------------------------------------- #

def test_ac6_the_entry_point_note_names_the_new_default_and_the_full_spelling():
    note = capabilities(full=True)["entry_points"]["guide"]["summary"]
    assert "index" in note
    assert "full=True" in note


def test_ac6_the_docs_row_still_carries_the_section_index_and_its_addressing():
    row = capabilities(full=True)["docs"]["guide()"]
    assert [r["slug"] for r in row["sections"]] == [r["slug"] for r in guide_sections()]
    assert "guide(section=…)" in row["section_addressing"]


def test_ac6_the_docs_row_summary_names_the_new_default_and_the_full_spelling():
    """``section_addressing`` is authored ONCE for all four packaged documents and only the
    guide grew a ``full``, so the guide-specific truth belongs in the guide's own summary."""
    summary = capabilities(full=True)["docs"]["guide()"]["summary"]
    assert "index" in summary.lower()
    assert "full=True" in summary


# --------------------------------------------------------------------------- #
# AC7 — the index is SHIPPED TEXT, so it is held to the shipped-text standard   #
# --------------------------------------------------------------------------- #

def test_ac7_the_index_carries_no_internal_dialect(index):
    """The index is new consumer-reaching text: its rows are the document's own headings (already
    in the guarded corpus) but its header is authored in ``larkdocio.guide``. A consumer has only
    the wheel, so an issue id, a private-set id or an internal role name in it resolves to nothing."""
    import consumer_text

    assert consumer_text.dialect_hits(index) == []
