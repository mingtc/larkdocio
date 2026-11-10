"""LD-659 AC1 — a label can no longer corrupt the diagram it sits in.

The defect, executed on `develop` before this file existed: `escape_label` performed no
whitespace/control sanitization at all, and both compilers compose labels into a
**line-oriented** syntax. So

    flowchart({"nodes": [{"id": "A", "label": "Start\\nflowchart LR\\n  X-->Y"}]})

returned source whose node declaration was cut in half and which carried a **second diagram
declaration** as a statement — a valid-looking diagram that says something the spec did not,
with nothing anywhere to prompt a re-read. The `title` key was worse still: it never went
through `escape_label`, and it lands in a `%%` comment, which is line-oriented too.

Every case below is asserted as BEHAVIOR — the compiler's own output or its refusal — never as
a citation of the constant.
"""
import pytest

from larkdocio.errors import LarkConfigError
from larkdocio.mermaid import escape_label, flowchart, sequence
from larkdocio.mermaid.ruleset import (
    LABEL_CONTROL_CHARS,
    LABEL_LINE_BREAKS,
    RULES,
    require_no_control_chars,
)

#: The spec shape the defect was measured on.
_INJECTION = "Start\nflowchart LR\n  X-->Y"


# --------------------------------------------------------------------------- #
# The refusal itself                                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("char", list(LABEL_CONTROL_CHARS))
def test_every_declared_control_character_is_really_refused(char):
    """A constant the escaper ignored would be prose in a tuple.

    Parametrized over the whole constant rather than over a sample: the tab and the C0
    oddities are exactly the members a hand-picked sample would have left out.
    """
    with pytest.raises(LarkConfigError) as raised:
        escape_label(f"x{char}y")
    assert f"U+{ord(char):04X}" in str(raised.value)


def test_the_refusal_names_the_construct_so_a_big_spec_is_searchable():
    with pytest.raises(LarkConfigError) as raised:
        flowchart({"nodes": [{"id": "A", "label": _INJECTION}]})
    message = str(raised.value)
    assert "label of node 'A'" in message
    assert "U+000A" in message


def test_a_line_break_and_another_control_character_give_DIFFERENT_reasons():
    """The two halves of the rule are not one sentence: a newline ends a statement, a NUL is
    merely unrenderable. A single message for both would over- or under-claim."""
    with pytest.raises(LarkConfigError) as newline:
        escape_label("a\nb")
    with pytest.raises(LarkConfigError) as nul:
        escape_label("a\x00b")
    assert "one statement per LINE" in str(newline.value)
    assert "one statement per LINE" not in str(nul.value)
    assert "no rendering for a control character" in str(nul.value)


def test_the_refusal_says_what_to_do_and_forecloses_the_br_workaround():
    with pytest.raises(LarkConfigError) as raised:
        escape_label("a\nb")
    message = str(raised.value)
    assert "<br/>" in message and "no-HTML rule" in message
    assert "split the construct in two" in message


# --------------------------------------------------------------------------- #
# The four flowchart doors and the two sequence doors                          #
# --------------------------------------------------------------------------- #

def test_a_node_label_cannot_inject_a_statement():
    with pytest.raises(LarkConfigError):
        flowchart({"nodes": [{"id": "A", "label": _INJECTION}]})


def test_a_subgraph_label_cannot_inject_a_statement():
    with pytest.raises(LarkConfigError) as raised:
        flowchart({
            "nodes": [{"id": "A", "label": "Start"}],
            "subgraphs": [{"id": "phase1", "label": _INJECTION, "nodes": ["A"]}],
        })
    assert "label of subgraph 'phase1'" in str(raised.value)


def test_an_edge_label_cannot_inject_a_statement():
    with pytest.raises(LarkConfigError) as raised:
        flowchart({
            "nodes": [{"id": "A", "label": "a"}, {"id": "B", "label": "b"}],
            "edges": [{"from": "A", "to": "B", "label": "yes\nA-->A"}],
        })
    assert "label of the edge 'A' -> 'B'" in str(raised.value)


def test_the_flowchart_TITLE_cannot_inject_a_statement():
    """The title never passed through `escape_label` at all, and `%%` is a LINE comment: the
    newline ended the comment and the remainder became a statement the renderer obeys."""
    with pytest.raises(LarkConfigError) as raised:
        flowchart({"title": "T\nflowchart LR\n  X-->Y",
                   "nodes": [{"id": "A", "label": "Start"}]})
    assert "diagram title" in str(raised.value)


def test_a_participant_label_and_a_message_text_cannot_inject_a_statement():
    base = {"participants": [{"id": "Client", "label": "Mobile App"},
                             {"id": "Gateway", "label": "Gateway"}]}
    with pytest.raises(LarkConfigError) as alias:
        sequence({"participants": [{"id": "Client", "label": "App\nparticipant Rogue"}]})
    assert "label of participant 'Client'" in str(alias.value)
    with pytest.raises(LarkConfigError) as text:
        sequence(dict(base, messages=[{"from": "Client", "to": "Gateway",
                                       "label": "1. POST /login\nRogue->>Client: x"}]))
    assert "text of the message 'Client' -> 'Gateway'" in str(text.value)


def test_the_sequence_TITLE_cannot_inject_a_statement():
    with pytest.raises(LarkConfigError) as raised:
        sequence({"title": "Auth\nRogue->>X: hi",
                  "participants": [{"id": "Client", "label": "App"}]})
    assert "diagram title" in str(raised.value)


# --------------------------------------------------------------------------- #
# What did NOT change                                                          #
# --------------------------------------------------------------------------- #

def test_the_ordinary_diagram_is_byte_unchanged():
    """The refusal is a new door on a narrow class, not a new escaping regime: a spec with no
    control character anywhere compiles to exactly the source it always did."""
    assert flowchart({
        "title": "Onboarding",
        "nodes": [{"id": "A", "label": "Start (here)"}, {"id": "B", "label": "End"}],
        "edges": [{"from": "A", "to": "B", "label": "yes"}],
    }) == (
        "%%{init: {'flowchart': {'curve': 'stepAfter'}}}%%\n"
        "flowchart TD\n"
        "    %% Onboarding\n"
        '    A["Start (here)"]\n'
        "    B[End]\n"
        "    A -->|yes| B"
    )


def test_a_space_is_still_only_a_quoting_trigger_not_a_refusal():
    """The rule is about CONTROL characters. A space — the one whitespace character that is
    ordinary label content — must keep its old behavior, or every label with two words breaks."""
    assert " " not in LABEL_CONTROL_CHARS
    assert escape_label("Hello World") == '"Hello World"'


def test_a_caller_written_br_is_still_STRIPPED_which_is_why_this_refuses():
    """The second reason on `LABEL_CONTROL_CHARS`, as behavior: translating `\\n` into `<br/>`
    would have made these two spellings of one request disagree."""
    assert escape_label("a<br/>b") == "ab"


# --------------------------------------------------------------------------- #
# The rule is a REGISTERED rule, so the shipped document cannot omit it        #
# --------------------------------------------------------------------------- #

def test_the_rule_is_in_the_registry_with_both_of_its_constants():
    rule = [r for r in RULES if r.key == "no-control-chars"]
    assert rule, [r.key for r in RULES]
    assert rule[0].posture == "enforced"
    assert set(rule[0].constants) == {"LABEL_CONTROL_CHARS", "LABEL_LINE_BREAKS"}


def test_the_helper_returns_its_input_unchanged_when_there_is_nothing_to_refuse():
    """It is a `require_`, not a sanitizer: the text it accepts is the text it returns, which
    is what lets it stand in the middle of `escape_label`'s pipeline."""
    assert require_no_control_chars("Start (here)", "label") == "Start (here)"


def test_the_line_break_subset_is_a_subset_of_the_refused_set():
    """Two constants, one rule: a line break that was refused as "unrenderable" would give the
    caller the wrong reason, and one that was not refused at all would be the original bug."""
    assert set(LABEL_LINE_BREAKS) <= set(LABEL_CONTROL_CHARS)
    assert "\n" in LABEL_LINE_BREAKS and "\u2028" in LABEL_LINE_BREAKS
