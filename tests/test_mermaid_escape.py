"""The shared label sanitizer — the quoting rule, proven as BEHAVIOR.

Ported from the standalone generator's own escape suite (all nine cases), plus the
crash-inducing character classes the ported rule set names (parentheses, commas,
brackets, quotes, HTML) asserted directly rather than cited.
"""
import pytest

from larkdocio.mermaid import escape_label
from larkdocio.mermaid.ruleset import HTML_TAG_RE, LABEL_BAD_CHARS


# --------------------------------------------------------------------------- #
# The nine ported cases                                                        #
# --------------------------------------------------------------------------- #

def test_plain_label_unquoted():
    assert escape_label("plain") == "plain"


def test_space_forces_quotes():
    assert escape_label("Hello World") == '"Hello World"'


def test_parentheses_forces_quotes():
    assert escape_label("Process (New)") == '"Process (New)"'


def test_comma_forces_quotes():
    assert escape_label("a,b") == '"a,b"'


def test_brackets_forces_quotes():
    assert escape_label("a[b]") == '"a[b]"'
    assert escape_label("a{b}") == '"a{b}"'


def test_double_quotes_downgraded_to_single_then_wrapped():
    assert escape_label('Say "hi"') == '"Say \'hi\'"'


def test_html_tags_stripped():
    # <script> is removed entirely; what is left carries no bad char -> unquoted.
    assert escape_label("<script>alert</script>") == "alert"


def test_html_tags_stripped_then_quoted_if_needed():
    # After stripping the tags a space remains, so the label gets quoted.
    assert escape_label("<b>Start</b> here") == '"Start here"'


def test_pipe_is_not_treated_as_bad_char():
    """Pins the ported behavior: ``|`` alone is not in the bad-character set.

    It is the edge-label delimiter, and the compiler emits it around an already-escaped
    label, so a bare pipe inside a label is left alone exactly as it was.
    """
    assert escape_label("a|b") == "a|b"
    # A co-occurring space still forces quoting.
    assert escape_label("a | b") == '"a | b"'


# --------------------------------------------------------------------------- #
# The crash-inducing classes, asserted as behavior (not as a citation)         #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("bad", list(LABEL_BAD_CHARS))
def test_every_declared_bad_character_really_forces_quoting(bad):
    """Every character the rule constant names is one the helper actually acts on.

    A bad-character list that the helper ignored would be prose in a tuple.
    """
    out = escape_label(f"x{bad}y")
    assert out.startswith('"') and out.endswith('"'), out


def test_a_quote_is_downgraded_before_the_wrap_so_the_result_stays_parseable():
    out = escape_label('a "b" (c)')
    assert '"' not in out[1:-1], out
    assert out == '"a \'b\' (c)"'


def test_html_is_stripped_even_when_it_is_the_whole_label():
    assert escape_label("<br/>") == ""


def test_html_stripping_uses_the_declared_pattern():
    """The no-HTML rule is one regex, and it is the one the rule constant publishes."""
    assert HTML_TAG_RE.sub("", "<b>x</b>") == "x"


def test_the_helper_is_total_over_the_named_classes():
    """One label carrying every named class at once still comes back single-quoted-safe."""
    out = escape_label('<b>Step (1), [a] {b} "q"</b>')
    assert out.startswith('"') and out.endswith('"')
    assert "<" not in out and ">" not in out
    assert '"' not in out[1:-1]


def test_escaping_is_deterministic():
    label = 'Step (1), "two" <i>three</i>'
    assert escape_label(label) == escape_label(label)
