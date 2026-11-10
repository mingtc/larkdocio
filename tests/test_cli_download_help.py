from click.testing import CliRunner

from larkdocio.cli import cli


def _normalize(text: str) -> str:
    """Collapse all whitespace so assertions survive click's line-wrapping."""
    return " ".join(text.split())


def test_download_help_shows_canonical_usage_example():
    result = CliRunner().invoke(cli, ["download", "--help"])

    assert result.exit_code == 0

    normalized = _normalize(result.output)

    # AC2: the help is clearly labelled as an example.
    assert "example" in normalized.lower()

    # AC1: the README's canonical invocation appears in full.
    assert "larkdocio download" in normalized
    assert "-o ./out/" in normalized


def _output_option():
    """``download``'s own ``-o/--output`` option object."""
    options = [p for p in cli.commands["download"].params if p.name == "output_dir"]
    assert len(options) == 1, "download no longer has exactly one -o/--output option"
    return options[0]


def test_the_o_option_states_the_DIRECTORY_contract_in_its_first_sentence():
    """``-o`` is always a directory and never a filename — said plainly, and said FIRST.

    Every other command line's ``-o`` means *output file*; this one does not, and a reader who
    meets the contract only after a clause about routing has already formed the wrong
    expectation. (``mermaid``'s ``-o`` help documented this command's contract before this
    command did.)
    """
    help_text = _normalize(_output_option().help).lower()

    assert "director" in help_text, "the -o help never says it is a directory"
    assert "never a file" in help_text, (
        "the -o help never rules out a filename, which is what a reader assumes")
    # Said FIRST: before the placement clause, not after it. The needle was the retired
    # document type's name until LD-650 scrubbed the word from the help — `help_text.index` RAISES on a missing needle,
    # so the ordering claim is re-pointed at the clause that survived (`--route`) rather than
    # left to fail as a ValueError nobody reads as an ordering defect.
    assert help_text.index("never a file") < help_text.index("--route"), (
        "the directory contract must lead the -o help, not trail the placement clause")


def test_the_help_PAGE_points_at_the_switch_that_governs_the_FILENAME():
    """A consumer who does not want ``[YYYY-MM-DD_HHMM]_<title>.md`` must find the switch from
    the help — the help is where they are standing when the question arrives.

    Asserted over the rendered page rather than the ``-o`` help string: the option help is
    bounded to a help *line* (``tests/test_download_output_docs.py`` holds it no longer than the
    shortest explanatory option on the page), so the filename rule is stated in the epilog,
    where it can be a sentence. Either place answers the reader; the page is what they see.
    """
    normalized = _normalize(CliRunner().invoke(cli, ["download", "--help"]).output)

    assert "title_as_filename" in normalized, (
        "the help page does not name the switch that governs the generated filename")
    assert "larkdocio guide" in normalized, (
        "the help page names the switch but not where to read it")
    # And the directory contract survives click's wrapping into the page a consumer runs.
    assert "never a filename" in normalized.lower()

    # The filename SHAPE reaches the reader unbroken — click wraps the epilog at eighty
    # columns whatever the terminal width, so the sentence carrying it is a no-rewrap block.
    assert "[YYYY-MM-DD_HHMM]_<title>.md" in normalized, (
        "the help page does not say what the generated filename looks like")
