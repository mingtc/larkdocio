"""LD-659 AC1b — a name the sanitizer empties stops being substituted in silence.

`sanitize_path_string` has two `"untitled"` returns and they are **not** the same thing. The
first (input already empty) is a sensible default and is unchanged: there was no name to lose.
The second — *"fallback if stripping made it empty"* — was a **silent substitution**: `"***"`,
`"::"`, `"???"` and `"--"` all came back as `untitled` with no disclosure anywhere, so a caller
asked for one name and received another and nothing said so.

LD-658 AC6 made that worse, correctly: it moved the `--route` traversal check onto the
**sanitized** segment, so `--route '***'` no longer looks empty to the guard — it looks like the
literal directory `untitled`, and the file lands in `<out>/untitled/`. A path the user never
named, created silently, past a guard working exactly as designed.

The two cases are answered **differently and on purpose**, which is what this module pins:

* a name this library DERIVED (a document title) is substituted **and disclosed** — something
  has to be written and the caller has nothing to correct;
* a name the CALLER supplied (a `--route` segment) is **refused** — they can fix their input,
  and this library refuses rather than guesses.
"""
import logging

import click
import pytest

from larkdocio.common.sanitize import UNTITLED, sanitize_path_string, sanitizes_to_nothing
from larkdocio.read.config import new_config
from larkdocio.read.download import _apply_explicit_route, _write_markdown

#: The measured inputs from the issue, verbatim, plus the two the strip half produces.
EMPTIED = ["***", "::", "???", "--", "__", "///:::", "   ", '"?"']


# --------------------------------------------------------------------------- #
# The derived case: substitute, and DISCLOSE                                   #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", EMPTIED)
def test_the_substitution_is_disclosed_and_names_both_the_input_and_the_answer(caplog, name):
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        assert sanitize_path_string(name) == UNTITLED
    assert len(caplog.records) == 1, caplog.records
    record = caplog.records[0]
    assert record.levelno == logging.WARNING
    assert repr(name) in record.getMessage()
    assert UNTITLED in record.getMessage()


def test_the_disclosure_is_WARNING_because_it_fires_only_for_a_name_that_WAS_supplied(caplog):
    """WARNING, not INFO: an in-process caller with no handler attached sees WARNING and above
    through `logging.lastResort`, and that is exactly the caller a silent substitution
    misleads. The same reasoning the retired-config-key notice is set at."""
    with caplog.at_level(logging.DEBUG, logger="larkdocio"):
        sanitize_path_string("***")
    assert [record.levelno for record in caplog.records] == [logging.WARNING]


def test_the_EMPTY_INPUT_case_is_still_silent(caplog):
    """The first `untitled` return stays as it was, and stays undisclosed: there was no name to
    lose, and a notice here would fire for every genuinely untitled document."""
    with caplog.at_level(logging.DEBUG, logger="larkdocio"):
        assert sanitize_path_string("") == UNTITLED
        assert sanitize_path_string(None) == UNTITLED
    assert caplog.records == []


def test_an_ordinary_name_discloses_nothing(caplog):
    """A disclosure that fires on the ordinary case is a disclosure nobody reads."""
    with caplog.at_level(logging.DEBUG, logger="larkdocio"):
        assert sanitize_path_string("Example Value Bundle") == "Example_Value_Bundle"
        assert sanitize_path_string("a/b:c") == "abc"
    assert caplog.records == []


def test_a_document_TITLE_that_empties_still_produces_a_file(tmp_path, caplog):
    """The derived half, end to end: the download does not refuse — it names the file after the
    document token (which it already preferred) and the substitution is disclosed on the way."""
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        written = _write_markdown(new_config(), str(tmp_path), "doctoken", "***", "# x\n")
    assert "doctoken" in written and UNTITLED not in written
    assert any("untitled" in record.getMessage() for record in caplog.records)


# --------------------------------------------------------------------------- #
# The caller-supplied case: REFUSE                                             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("segment", ["***", "::", "???", "--", '"?"'])
def test_a_route_segment_that_empties_is_REFUSED_not_substituted(tmp_path, segment):
    with pytest.raises(click.ClickException) as raised:
        _apply_explicit_route(str(tmp_path), segment)
    message = str(raised.value)
    assert repr(segment) in message
    assert "nothing usable" in message
    assert "will not invent a directory name" in message


def test_the_refusal_fires_for_an_INTERIOR_segment_too(tmp_path):
    with pytest.raises(click.ClickException) as raised:
        _apply_explicit_route(str(tmp_path), "area/***/topic")
    assert repr("***") in str(raised.value)


def test_the_untitled_DIRECTORY_the_route_used_to_produce_is_no_longer_reachable(tmp_path):
    """The LD-658 interaction, pinned as behavior: this is the exact call that returned
    `<out>/untitled` — past the traversal guard, because `untitled` traverses nothing."""
    with pytest.raises(click.ClickException):
        _apply_explicit_route(str(tmp_path), "***")


def test_a_caller_who_REALLY_MEANS_untitled_still_gets_it(tmp_path):
    """Why the refusal asks `sanitizes_to_nothing` instead of comparing the result against
    `UNTITLED`: the string is a legal directory name and this caller typed it."""
    assert _apply_explicit_route(str(tmp_path), "untitled").endswith("untitled")
    assert _apply_explicit_route(str(tmp_path), "a/untitled/b").endswith("a/untitled/b")


def test_the_ordinary_route_is_unchanged(tmp_path):
    assert _apply_explicit_route(str(tmp_path), "area/section/topic").endswith(
        "area/section/topic")


# --------------------------------------------------------------------------- #
# The predicate answers by construction, not by comparing to the substitution  #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", EMPTIED + ["", None])
def test_the_predicate_agrees_with_the_sanitizer_on_every_emptied_name(name):
    assert sanitizes_to_nothing(name) is True
    assert sanitize_path_string(name) == UNTITLED


@pytest.mark.parametrize("name", [UNTITLED, "Untitled", "domain", "a-b_c", "汉字", "x***"])
def test_the_predicate_is_FALSE_for_a_name_that_survives(name):
    assert sanitizes_to_nothing(name) is False
    assert sanitize_path_string(name) != UNTITLED or name == UNTITLED


def test_the_predicate_and_the_sanitizer_read_ONE_definition_of_the_reduction():
    """Not a taste point: two copies of the strip rule would let the `--route` refusal and the
    substitution disagree about the same segment, which is the defect one level up. Asserted
    across the whole punctuation cross-product rather than by reading the source."""
    from itertools import product
    for parts in product('*:?"<>|\\/-_ a', repeat=2):
        name = "".join(parts)
        assert sanitizes_to_nothing(name) == (sanitize_path_string(name) == UNTITLED
                                              and name != UNTITLED), name
