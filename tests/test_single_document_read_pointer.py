"""The single-document read is REACHABLE — the guide names it, and `capabilities()` reports it.

The defect this file exists for was **routing, not capability**: `read_folder` was named 17
times in the shipped guide and its single-document sibling
``larkdocio.drive.read_child_markdown`` — whose own docstring calls itself *"the published
… contract"* — was named **zero** times, and no `capabilities()` row carried it either. A
surface a consumer cannot find is, from the consumer's chair, a surface that does not exist.

**The pointer must not oversell, and that is the load-bearing half.** A sentence that says
"one call gets you the Markdown" and stops is how a consumer picks the wrong door and files
the next bug: the CLI ``download`` verb fetches images, writes files, and places output under
a caller-supplied ``--route``, and this function does **none** of the three. It also does not
resolve ``@mention`` ids — ``read.download._parse`` builds ``Parser(config)`` with no
``read_client`` and the substitution is a *separate* pipeline step ``download`` takes and this
leg does not — which the recipe's own ``read_client=`` paragraph makes the most confusable
difference of the four. So each exclusion is asserted here, and the mention one is asserted
**behaviorally** rather than taken off a docstring.
"""
import inspect

import larkdocio
import pytest
from domain_vocabulary import FORBIDDEN
import private_tree

from larkdocio import guide
from larkdocio.drive import read_child_markdown

import doc_prose
import guide_recipes as gr


RECIPE = "download-a-docx-to-markdown"

#: The pointer's own text, as the phrases a consumer must be able to read out of it. Asserted
#: at CONTENT level through :mod:`doc_prose` — the guide is hard-wrapped and these phrases are
#: emphasised, so a literal substring check would redden on a reflow and get weakened until it
#: guarded nothing.
DOES = ("larkdocio.drive.read_child_markdown", "read_child_markdown(")

#: The four things it does NOT do. Three are the CLI ``download`` verb's jobs; the fourth is
#: the pipeline step ``_read_docx_markdown`` skips.
#:
#: LD-650 RE-POINTED the third phrase rather than dropping it. The exclusion is still true and
#: still load-bearing — this function does not place output anywhere, because it writes no
#: file — but the thing it used to name (a body-sniffing derivation) no longer exists on
#: either side, so the phrase names the surviving CLI-side placement instead.
DOES_NOT = ("no image fetch", "no file write", "no routing at all",
            "no @mention resolution")


def _recipe_section(slug: str = RECIPE) -> str:
    """Recipe ``slug``'s whole section — heading to the next ``###`` — off the SHIPPED guide.

    The preamble alone is not the right window: the pointer sits below the recipe's first
    fenced block on purpose (a consumer meets the full pipeline first, then the one-call
    door), so a preamble-only assertion would force the pointer to the top of the recipe for
    the guard's convenience rather than the reader's.
    """
    text = guide(full=True)
    headings = {gr._slug(h): h for h in gr.recipe_headings(text)}
    heading = headings.get(slug)
    assert heading is not None, f"the guide has no recipe {slug!r}"
    start = text.index(f"### Recipe: {heading}")
    nxt = text.find("\n### ", start + 1)
    return text[start:] if nxt == -1 else text[start:nxt]


# --------------------------------------------------------------------------- #
# 1. The guide names it, and shows the call shape.                             #
# --------------------------------------------------------------------------- #

def test_the_docx_read_recipe_NAMES_the_single_document_read_verb():
    section = _recipe_section()
    missing = doc_prose.missing_phrases(section, DOES)
    assert missing == [], (
        f"the docx-read recipe does not name {missing} — the single-document read is back to "
        f"being undiscoverable, which is the whole defect")


def test_the_pointer_is_EXECUTED_by_the_recipe_harness_not_merely_named():
    """A named symbol can rot; an executed one cannot. The pointer ships as the recipe's
    SECOND python block, so ``test_discovery_truth.py``'s every-block-is-executed guard runs
    it against the offline fixtures and a rename reddens the suite."""
    sources = gr.recipe_sources(RECIPE)
    assert len(sources) == 2, (
        f"the docx-read recipe carries {len(sources)} python blocks; the pointer block is "
        f"the second and it must be executed, not merely read")
    assert "read_child_markdown" in sources[1], sources[1]


# --------------------------------------------------------------------------- #
# 2. IT SAYS WHAT IT DOES NOT DO. A pointer that only advertises is worse than #
#    no pointer.                                                              #
# --------------------------------------------------------------------------- #

#: THE TWO PLACES THE SAME FOUR EXCLUSIONS ARE PUBLISHED, and both are read (LD-650). The
#: guide is what a consumer browses; ``inspect.getdoc`` is what ``help()`` prints and what an
#: IDE shows — the docstring's own sentence even claims *"and the guide says all four"*, a
#: CROSS-CLAIM that is false the moment the two texts disagree.
#:
#: **Only the guide half was asserted before, and that is exactly how a stale claim survived**:
#: LD-650 corrected the guide's wording and left the docstring saying the verb still routed
#: one document shape's output by its body, green, in the text `help()` prints. A guard that reads one of two
#: published copies is a guard for one of them.
def _published_exclusion_texts():
    return {
        "the shipped guide's recipe": _recipe_section(),
        "inspect.getdoc(read_child_markdown)": inspect.getdoc(read_child_markdown),
    }


@pytest.mark.parametrize("where", sorted(_published_exclusion_texts()))
@pytest.mark.parametrize("phrase", DOES_NOT)
def test_the_pointer_states_what_the_function_does_NOT_do(phrase, where):
    text = _published_exclusion_texts()[where]
    assert doc_prose.prose(phrase) in doc_prose.prose(text), (
        f"{where} does not say {phrase!r}. The three CLI-only jobs (images, files, placement) "
        f"and the skipped mention step are what stop a consumer picking the wrong door; a "
        f"pointer that omits one has advertised a capability the function lacks")


@private_tree.dev_record  # the private set is read from the private ledger (LD-705)
def test_neither_published_copy_still_names_the_RETIRED_derivation():
    """The cross-claim's other half. Both texts described a body-sniffing router that LD-650
    removed; a copy still naming it is telling a consumer the verb does something it cannot."""
    offenders = {
        where: [ln for ln in text.splitlines() if FORBIDDEN.search(ln)]
        for where, text in _published_exclusion_texts().items()
    }
    assert not any(offenders.values()), offenders


def test_the_pointer_names_the_verb_a_consumer_should_use_INSTEAD():
    """The exclusions are only actionable with a destination attached."""
    section = _recipe_section()
    assert "download" in section.lower()


# --------------------------------------------------------------------------- #
# 3. The symbol exists where the pointer says it does — and the top-level      #
#    `__all__` asymmetry that hid it is NOTED, not silently fixed.             #
# --------------------------------------------------------------------------- #

def test_the_named_symbol_exists_and_is_exported_from_larkdocio_drive():
    from larkdocio import drive

    assert "read_child_markdown" in drive.__all__
    assert callable(read_child_markdown)


def test_it_is_STILL_NOT_in_the_top_level_all_and_that_is_why_it_escaped_the_index():
    """The mechanical reason nothing pointed at it: it lives in ``drive.__all__``, not
    ``larkdocio.__all__``, so any consumer or guard that learns the public surface from the
    top-level export list cannot see it. This change **notes** that and routes around it; it
    deliberately does **not** re-export the symbol, which would be a new published entry
    point and a second answer to one question. This test pins the note's premise — if a later
    change re-exports it, this reddens and the note gets rewritten rather than quietly
    becoming false."""
    assert "read_child_markdown" not in larkdocio.__all__


# --------------------------------------------------------------------------- #
# 5. The fourth exclusion, BEHAVIORALLY: the child read skips the mention step. #
# --------------------------------------------------------------------------- #

def test_the_docx_child_read_does_NOT_run_the_mention_resolution_STEP(monkeypatch):
    """``download`` calls ``_parse`` and then ``_resolve_mentions``; the child read calls
    ``_parse`` and stops. So a document full of ``@ou_…`` ids reads back with raw ids here and
    with display names through the CLI — the difference the pointer has to state, proven by
    watching the step rather than by reading a docstring."""
    from larkdocio.read import download as dl
    import larkdocio.drive.read as read_mod

    seen = {"parse": 0, "resolve": 0}

    def fake_parse(client, config, doc_token, **kw):
        seen["parse"] += 1
        return object(), [], object(), "title", "@ou_exampleowner00000000000000000001"

    monkeypatch.setattr(dl, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(dl, "get_read_credentials", lambda: ("id", "secret"))
    monkeypatch.setattr(dl, "_resolve_doc",
                        lambda *a, **k: (object(), object(), "docx", "d1"))
    monkeypatch.setattr(dl, "build_deep_read_clients", lambda *a, **k: (None, None, None))
    monkeypatch.setattr(dl, "_parse", fake_parse)
    monkeypatch.setattr(dl, "_resolve_mentions",
                        lambda *a, **k: seen.__setitem__("resolve", seen["resolve"] + 1))

    out = read_mod.read_child_markdown(
        "docx", url="https://x.larksuite.com/docx/d1", token="d1")

    assert seen["parse"] == 1, "the child read did not run the parse pipeline at all"
    assert seen["resolve"] == 0, (
        "the child read resolved mentions — the pointer's 'no @mention resolution' exclusion "
        "is now FALSE and the guide must be corrected, not this test")
    assert out == "@ou_exampleowner00000000000000000001", (
        "the raw open id came through unsubstituted, which is the observable consequence")
