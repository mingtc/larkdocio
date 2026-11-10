"""The flowchart compiler — the ported suite plus the rules it now enforces.

The seventeen cases the standalone generator's own suite covered are all here (header and
direction, the title comment, every shape and alias, label escaping, HTML stripping, the
four arrow arithmetics, edge lengths, subgraph emission, and an edge naming a node nothing
defines). What is added is the enforcement the generator only *documented*: the theme
whitelist, one init-line dialect, no blank line inside the block, and the two advisory
ceilings.

**Seven of the ported cases are DELIBERATELY REWRITTEN, and each says so where it stands.**
They pinned the generator's leniency as expected behavior — an unknown direction becoming the
vertical one, an unknown shape becoming a rectangle, a label on an invisible edge disappearing,
an out-of-range or non-numeric length being clamped, an edge naming an undefined node being
dropped behind a log line, a node with no usable identifier being skipped. That is the defect
this module's compiler was fixed to stop committing: each of those specs asks for something
the renderer cannot draw, and a *substitution* answers it with a different diagram and no
signal. The cases are kept — same specs, same names where the name still describes the case —
and now assert the refusal. **The bytes a VALID spec compiles to did not move**: that promise
is held whole in ``tests/test_mermaid_strict_dialect.py`` against a captured corpus.
"""
import logging
import re

import pytest

from larkdocio.errors import LarkConfigError
from larkdocio.mermaid import flowchart
from larkdocio.mermaid.ruleset import (
    COMPLEXITY_LIMIT,
    SANCTIONED_DECLARATIONS,
    THEMES,
    VERTICAL_PREFERRED_ABOVE,
)

BLANK_LINE_RE = re.compile(r"^[ \t]*$", re.MULTILINE)


def _two_nodes(**edge):
    spec = {"nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}]}
    if edge:
        spec["edges"] = [{"from": "A", "to": "B", **edge}]
    return flowchart(spec)


# --------------------------------------------------------------------------- #
# The ported cases                                                            #
# --------------------------------------------------------------------------- #

def test_header_and_direction():
    out = flowchart({"direction": "LR", "nodes": [{"id": "A", "label": "Start"}]})
    assert "flowchart LR" in out
    # The init line forces the stepped curve, which is what keeps edges at right angles.
    assert "stepAfter" in out


def test_invalid_direction_is_REFUSED():
    """REWRITTEN (see the module docstring): the ported case asserted that ``SIDEWAYS`` became
    the vertical direction. Substituting an axis redraws the diagram along the other one, so
    the value is named back instead."""
    with pytest.raises(LarkConfigError) as caught:
        flowchart({"direction": "SIDEWAYS", "nodes": [{"id": "A", "label": "A"}]})
    assert "SIDEWAYS" in str(caught.value)


def test_title_comment():
    out = flowchart({"title": "My Flow", "nodes": [{"id": "A", "label": "A"}]})
    assert "    %% My Flow" in out


def test_node_shapes():
    out = flowchart({
        "nodes": [
            {"id": "R", "label": "Rect", "shape": "rect"},
            {"id": "O", "label": "Round", "shape": "round"},
            {"id": "C", "label": "Cyl", "shape": "cylinder"},
            {"id": "Dm", "label": "Dia", "shape": "diamond"},
        ],
    })
    assert "R[Rect]" in out
    assert "O((Round))" in out
    assert "C[(Cyl)]" in out
    assert "Dm{Dia}" in out


def test_node_shape_aliases():
    out = flowchart({
        "nodes": [
            {"id": "O", "label": "Round", "shape": "rounded"},
            {"id": "Dc", "label": "Dec", "shape": "decision"},
            {"id": "B", "label": "DB", "shape": "database"},
            {"id": "Cn", "label": "Cond", "shape": "condition"},
        ],
    })
    assert "O((Round))" in out
    assert "Dc{Dec}" in out
    assert "B[(DB)]" in out
    assert "Cn{Cond}" in out


def test_an_unknown_shape_is_REFUSED():
    """REWRITTEN: the ported case asserted that ``trapezoid`` was drawn as a rectangle. That is
    how a decision point stops looking like a decision with nothing to read anywhere."""
    with pytest.raises(LarkConfigError) as caught:
        flowchart({"nodes": [{"id": "A", "label": "A", "shape": "trapezoid"}]})
    assert "trapezoid" in str(caught.value)


def test_a_node_that_names_NO_shape_still_gets_the_rectangle():
    """The other half of the rewrite: the default is for an ABSENT key, not for a wrong one."""
    assert "A[A]" in flowchart({"nodes": [{"id": "A", "label": "A"}]})


def test_label_escaping_in_nodes():
    out = flowchart({"nodes": [{"id": "A", "label": "Process (New)"}]})
    assert 'A["Process (New)"]' in out


def test_html_stripped_in_nodes():
    """Pins the ported artifact: stripping the tag leaves the trailing space, which then
    forces the quotes. The label is emitted as authored minus the markup, not re-trimmed."""
    out = flowchart({"nodes": [{"id": "A", "label": "Dashboard <script>"}]})
    assert 'A["Dashboard "]' in out


def test_solid_arrow_arithmetic():
    assert "A --> B" in _two_nodes(**{"style": "solid"})
    assert "A --> B" in _two_nodes(style="solid", length=1)
    assert "A ---> B" in _two_nodes(style="solid", length=2)
    assert "A ----> B" in _two_nodes(style="solid", length=3)


def test_solid_is_the_default_style():
    assert "A --> B" in _two_nodes(**{"label": ""})


def test_dotted_arrow_arithmetic():
    assert "A -.-> B" in _two_nodes(style="dotted", length=1)
    assert "A -..-> B" in _two_nodes(style="dotted", length=2)


def test_thick_arrow_arithmetic():
    assert "A ==> B" in _two_nodes(style="thick", length=1)
    assert "A ===> B" in _two_nodes(style="thick", length=2)


def test_invisible_arrow_arithmetic():
    out = _two_nodes(style="invisible", length=1)
    assert "A ~~~ B" in out


def test_a_LABEL_on_an_invisible_edge_is_REFUSED():
    """REWRITTEN: the ported case passed ``label="hidden"`` alongside the invisible style and
    asserted the label was gone from the output. The combination is what is off-dialect — an
    invisible link draws nothing, so it can carry no text — and a caller who wrote a label
    meant it to appear."""
    with pytest.raises(LarkConfigError) as caught:
        _two_nodes(style="invisible", length=1, label="hidden")
    assert "hidden" in str(caught.value)


def test_invisible_length_two():
    assert "A ~~~~ B" in _two_nodes(style="invisible", length=2)


def test_edge_label_rendered_with_pipes():
    out = _two_nodes(label="Yes (Logged In)")
    assert 'A -->|"Yes (Logged In)"| B' in out


def test_the_longest_sanctioned_length_is_emitted_in_full():
    """What the clamp case was really guarding — that the top of the range draws — kept as a
    property of the range itself rather than of a value outside it."""
    assert "A ------> B" in _two_nodes(style="solid", length=5)


def test_a_length_ABOVE_the_range_is_REFUSED():
    """REWRITTEN: the ported case asked for ``99`` and asserted it was clamped to five. A
    clamped length is a layout the caller did not ask for, applied silently."""
    with pytest.raises(LarkConfigError) as caught:
        _two_nodes(style="solid", length=99)
    assert "99" in str(caught.value)


def test_a_length_BELOW_the_range_is_REFUSED():
    """REWRITTEN, same reason: ``0`` and ``-4`` were clamped up to the minimum."""
    for length in (0, -4):
        with pytest.raises(LarkConfigError) as caught:
            _two_nodes(style="solid", length=length)
        assert str(length) in str(caught.value)


def test_a_non_numeric_length_is_REFUSED():
    """REWRITTEN: ``"wide"`` became the minimum, so a typo silently chose a layout."""
    with pytest.raises(LarkConfigError) as caught:
        _two_nodes(style="solid", length="wide")
    assert "wide" in str(caught.value)


def test_subgraphs():
    out = flowchart({
        "subgraphs": [{"id": "g1", "label": "Phase 1", "nodes": ["A"]}],
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
    })
    assert 'subgraph g1["Phase 1"]' in out
    assert "    end" in out
    # A sits inside the subgraph; B floats free and is still emitted.
    assert "A[A]" in out
    assert "B[B]" in out


def test_unknown_edge_target_is_REFUSED(caplog):
    """REWRITTEN: the ported case asserted a WARNING and a dropped edge. The warning reached a
    library caller through nothing but ``logging.lastResort``, and the edge — the connection
    the whole spec exists to state — was simply absent from a clean return value. The refusal
    REPLACES the log line, which is why the record list is asserted empty."""
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        with pytest.raises(LarkConfigError) as caught:
            flowchart({
                "nodes": [{"id": "A", "label": "A"}],
                "edges": [{"from": "A", "to": "GHOST"}],
            })
    assert "GHOST" in str(caught.value)
    assert not caplog.records, [r.getMessage() for r in caplog.records]


def test_unknown_edge_source_is_REFUSED(caplog):
    """REWRITTEN for the same reason, on the other endpoint."""
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        with pytest.raises(LarkConfigError) as caught:
            flowchart({
                "nodes": [{"id": "A", "label": "A"}],
                "edges": [{"from": "PHANTOM", "to": "A"}],
            })
    assert "PHANTOM" in str(caught.value)
    assert not caplog.records, [r.getMessage() for r in caplog.records]


def test_a_node_with_no_id_is_REFUSED():
    """REWRITTEN: the ported case asserted the node was skipped. Nothing was logged for it at
    all, and every edge naming it then vanished too — one silent drop causing another."""
    with pytest.raises(LarkConfigError) as caught:
        flowchart({"nodes": [{"id": "", "label": "nameless"}, {"id": "A", "label": "A"}]})
    assert "position 1" in str(caught.value)


def test_a_node_id_carrying_a_space_is_sanitized_consistently():
    """The id is sanitized once and both the definition and the edge use the result."""
    out = flowchart({
        "nodes": [{"id": "Mobile App", "label": "Mobile App"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "Mobile App", "to": "B"}],
    })
    assert 'Mobile_App["Mobile App"]' in out
    assert "Mobile_App --> B" in out


# --------------------------------------------------------------------------- #
# One init-line dialect                                                       #
# --------------------------------------------------------------------------- #

def test_the_init_line_uses_single_quotes_and_no_stray_space():
    out = flowchart({"nodes": [{"id": "A", "label": "A"}]})
    assert out.splitlines()[0] == "%%{init: {'flowchart': {'curve': 'stepAfter'}}}%%"


def test_the_init_line_carries_the_theme_in_the_same_dialect():
    out = flowchart({"theme": "dark", "nodes": [{"id": "A", "label": "A"}]})
    assert out.splitlines()[0] == (
        "%%{init: {'flowchart': {'curve': 'stepAfter'}, 'theme': 'dark'}}%%"
    )


def test_the_default_theme_is_not_written_into_the_init_line():
    out = flowchart({"theme": "default", "nodes": [{"id": "A", "label": "A"}]})
    assert "theme" not in out


def test_no_double_quote_appears_in_the_init_line():
    out = flowchart({"theme": "forest", "nodes": [{"id": "A", "label": "A"}]})
    assert '"' not in out.splitlines()[0]


# --------------------------------------------------------------------------- #
# The theme whitelist — enforced, not asserted                                #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("theme", THEMES)
def test_every_whitelisted_theme_is_accepted(theme):
    out = flowchart({"theme": theme, "nodes": [{"id": "A", "label": "A"}]})
    assert "flowchart TD" in out


def test_a_theme_outside_the_whitelist_is_REFUSED():
    with pytest.raises(LarkConfigError) as caught:
        flowchart({"theme": "wobbly", "nodes": [{"id": "A", "label": "A"}]})
    assert "wobbly" in str(caught.value)


@pytest.mark.parametrize("absent", [None, ""])
def test_an_absent_theme_means_the_default_rather_than_a_refusal(absent):
    """A spec that carries the key with nothing in it is asking for the default, not for a
    theme called "None" — which is what a bare pass-through would have made of it."""
    out = flowchart({"theme": absent, "nodes": [{"id": "A", "label": "A"}]})
    assert "theme" not in out


def test_the_refusal_names_the_supported_themes():
    with pytest.raises(LarkConfigError) as caught:
        flowchart({"theme": "wobbly", "nodes": []})
    message = str(caught.value)
    assert all(theme in message for theme in THEMES)


# --------------------------------------------------------------------------- #
# No blank line inside the block                                              #
# --------------------------------------------------------------------------- #

def test_no_blank_line_anywhere_in_the_output():
    """Asserted over the WHOLE output, so a spacer at any position reddens this."""
    out = flowchart({
        "title": "Full Flow",
        "theme": "dark",
        "subgraphs": [{"id": "g1", "label": "Phase 1", "nodes": ["A"]}],
        "nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        "edges": [{"from": "A", "to": "B", "label": "next"}],
    })
    assert not BLANK_LINE_RE.search(out), repr(out)


def test_no_blank_line_in_the_minimal_output():
    assert not BLANK_LINE_RE.search(flowchart({"nodes": [{"id": "A", "label": "A"}]}))


def test_no_blank_line_when_there_are_no_nodes_at_all():
    assert not BLANK_LINE_RE.search(flowchart({}))


# --------------------------------------------------------------------------- #
# The declaration whitelist                                                   #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "direction,expected",
    [("TD", "flowchart TD"), ("LR", "flowchart LR"), ("td", "flowchart TD")],
)
def test_a_sanctioned_direction_is_emitted_verbatim(direction, expected):
    out = flowchart({"direction": direction, "nodes": [{"id": "A", "label": "A"}]})
    assert expected in out


def test_the_vertical_synonym_is_normalized_to_the_sanctioned_spelling():
    out = flowchart({"direction": "TB", "nodes": [{"id": "A", "label": "A"}]})
    assert "flowchart TD" in out
    assert "flowchart TB" not in out


def test_an_unsanctioned_direction_is_REFUSED():
    """REWRITTEN: ``RL`` used to become ``TD`` — the diagram drawn along the other axis."""
    with pytest.raises(LarkConfigError) as caught:
        flowchart({"direction": "RL", "nodes": [{"id": "A", "label": "A"}]})
    assert "RL" in str(caught.value)


@pytest.mark.parametrize("direction", ["TD", "LR", "TB", ""])
def test_the_declaration_is_always_one_of_the_sanctioned_ones(direction):
    """The same property the ported sweep asserted, now reached the other way. It used to
    include ``RL`` and ``SIDEWAYS`` and prove the property by *substitution*; those two are
    refused instead, which the companion test below asserts — so the property "every emitted
    declaration is sanctioned" still holds over the whole input space, by refusal where the
    input is off-dialect and by emission where it is not."""
    out = flowchart({"direction": direction, "nodes": [{"id": "A", "label": "A"}]})
    declaration = [
        line for line in out.splitlines() if line.startswith(("flowchart", "graph"))
    ]
    assert declaration, out
    assert declaration[0] in SANCTIONED_DECLARATIONS


@pytest.mark.parametrize("direction", ["RL", "SIDEWAYS", "BT", "sideways"])
def test_a_direction_NO_SANCTIONED_DECLARATION_CARRIES_never_reaches_the_output(direction):
    with pytest.raises(LarkConfigError) as caught:
        flowchart({"direction": direction, "nodes": [{"id": "A", "label": "A"}]})
    assert direction in str(caught.value)


# --------------------------------------------------------------------------- #
# The advisory ceilings — they warn, they do not refuse                       #
# --------------------------------------------------------------------------- #

def _wide_spec(node_count, edge_count, direction="TD"):
    nodes = [{"id": f"N{i}", "label": f"N{i}"} for i in range(node_count)]
    edges = [
        {"from": f"N{i}", "to": f"N{i + 1}"} for i in range(min(edge_count, node_count - 1))
    ]
    return {"direction": direction, "nodes": nodes, "edges": edges}


def test_the_complexity_ceiling_is_silent_AT_the_boundary(caplog):
    spec = _wide_spec(16, 14)  # 16 nodes + 14 edges == the ceiling exactly
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        flowchart(spec)
    assert "complexity" not in "\n".join(r.getMessage() for r in caplog.records)


def test_the_complexity_ceiling_warns_ONE_PAST_the_boundary(caplog):
    spec = _wide_spec(17, 14)  # 17 + 14 == one past
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        out = flowchart(spec)
    messages = "\n".join(r.getMessage() for r in caplog.records)
    assert "complexity" in messages
    assert str(COMPLEXITY_LIMIT) in messages
    # Advisory: the diagram is still compiled.
    assert "flowchart TD" in out


def test_the_horizontal_advisory_warns_past_the_node_count(caplog):
    spec = _wide_spec(VERTICAL_PREFERRED_ABOVE + 1, 0, direction="LR")
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        out = flowchart(spec)
    messages = "\n".join(r.getMessage() for r in caplog.records)
    assert "LR" in messages
    assert "flowchart LR" in out  # advisory, so the direction is honored


def test_the_horizontal_advisory_is_silent_at_the_node_count(caplog):
    spec = _wide_spec(VERTICAL_PREFERRED_ABOVE, 0, direction="LR")
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        flowchart(spec)
    assert not [r for r in caplog.records if "LR" in r.getMessage()]


def test_the_horizontal_advisory_is_silent_for_the_vertical_direction(caplog):
    spec = _wide_spec(20, 0, direction="TD")
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        flowchart(spec)
    assert not [r for r in caplog.records if "LR" in r.getMessage()]


# --------------------------------------------------------------------------- #
# Determinism                                                                 #
# --------------------------------------------------------------------------- #

def test_the_same_spec_compiles_byte_identically_twice():
    spec = {
        "title": "Repeatable",
        "theme": "neutral",
        "subgraphs": [{"id": "g1", "label": "Phase 1", "nodes": ["A", "B"]}],
        "nodes": [
            {"id": "A", "label": "A"},
            {"id": "B", "label": "B"},
            {"id": "C", "label": "C"},
        ],
        "edges": [{"from": "A", "to": "B"}, {"from": "B", "to": "C", "label": "then"}],
    }
    assert flowchart(spec) == flowchart(spec)


def test_the_spec_is_not_mutated_by_compiling_it():
    spec = {"nodes": [{"id": "A", "label": "A"}], "edges": []}
    before = repr(spec)
    flowchart(spec)
    assert repr(spec) == before
