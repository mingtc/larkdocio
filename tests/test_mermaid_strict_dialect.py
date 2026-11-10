"""STRICT BY DEFAULT — every off-dialect construct refuses, and nothing is guessed.

The defect this file exists to close: the two compilers **dropped and substituted** content
and returned a clean string. An edge naming a node nobody defined vanished behind a log line
no library caller could see; an unknown shape became a rectangle, an unknown direction became
the vertical one, a label on an invisible edge disappeared, a node whose identifier sanitized
to nothing was skipped along with every edge that touched it, a subgraph with no identifier
was renamed to a literal, an out-of-range length was clamped, and an unknown style was drawn
solid. Ten constructs, silently rewritten into a **semantically different diagram** — a
decision that no longer looks like a decision, a flow arrow that is simply not there — with
no value the caller could inspect.

The one construct that already behaved was the theme whitelist, and its own docstring carries
the whole argument: *an unknown theme is stored verbatim by the document and then quietly
ignored at draw time, so refusing here is the only place that can be noticed.* Everything
below applies that sentence to the other ten.

**Four properties, and each is asserted rather than described:**

* **Every off-dialect construct raises** :class:`~larkdocio.errors.LarkConfigError`, and the
  detail names the offending construct *and* its value — with the valid set enumerated
  wherever the set is closed. One test per construct, plus a sweep that holds the detail
  non-empty for all of them at once.
* **There is exactly one behavior.** No compiler entry point takes a leniency parameter, and
  the check reads the real signatures, so adding one later reddens.
* **No silent side-channel survives**: no ``print``, no write to a standard stream, and no
  warn-then-discard anywhere in the package — asserted structurally over the source, and
  per-case through the log records a compile really emits.
* **The advisory rules are untouched.** Diagram size and a wide horizontal layout are
  judgments about a *valid* spec; they still warn and still compile. The cheapest way to pass
  the property above is to delete them, so their preservation is pinned by equality over the
  rule registry rather than by inspection.

The compatibility promise is held in :mod:`mermaid_compat_corpus` and checked here against
bytes captured before the change: a valid spec compiles to the same source it always did.
"""
import ast
import inspect
import json
import logging
import pathlib
import textwrap

import mermaid_compat_corpus
import pytest

from larkdocio import guide
from larkdocio.errors import LarkConfigError
from larkdocio.mermaid import flowchart, rules, sequence
from larkdocio.mermaid.ruleset import (
    ADVISORY,
    COMPLEXITY_LIMIT,
    DEFAULT_DIRECTION,
    DEFAULT_EDGE_STYLE,
    DEFAULT_MESSAGE_STYLE,
    DEFAULT_SHAPE,
    DIRECTION_SYNONYMS,
    DIRECTIONS,
    EDGE_LENGTH_RANGE,
    EDGE_STYLES,
    LEGACY_ARROWS,
    MESSAGE_ARROWS,
    RULES,
    SHAPE_ALIASES,
    VERTICAL_PREFERRED_ABOVE,
)

REPO = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = REPO / "src" / "larkdocio" / "mermaid"
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

COMPILERS = {"flowchart": flowchart, "sequence": sequence}


# --------------------------------------------------------------------------- #
# THE OFF-DIALECT TABLE — one row per construct, driving the sweeps below      #
# --------------------------------------------------------------------------- #

#: ``{row: (compiler, spec)}``. Every entry is a construct the dialect does not carry, so
#: every entry must raise. The row names are the ones the sweeps report and the ones the
#: per-construct tests below repeat, so a reader can line them up.
OFF_DIALECT = {
    "unknown-node-in-an-edge": ("flowchart", {
        "nodes": [{"id": "A", "label": "a"}], "edges": [{"from": "A", "to": "ZZ"}],
    }),
    "unknown-node-as-an-edge-source": ("flowchart", {
        "nodes": [{"id": "A", "label": "a"}], "edges": [{"from": "PHANTOM", "to": "A"}],
    }),
    "unknown-participant-in-a-message": ("sequence", {
        "participants": [{"id": "A"}],
        "messages": [{"from": "A", "to": "GHOST", "label": "x"}],
    }),
    "unknown-participant-as-a-sender": ("sequence", {
        "participants": [{"id": "A"}],
        "messages": [{"from": "PHANTOM", "to": "A", "label": "x"}],
    }),
    "unknown-shape": ("flowchart", {
        "nodes": [{"id": "A", "label": "a", "shape": "hexagon"}],
    }),
    "unknown-direction": ("flowchart", {
        "direction": "XX", "nodes": [{"id": "A", "label": "a"}],
    }),
    "label-on-an-invisible-edge": ("flowchart", {
        "nodes": [{"id": "A"}, {"id": "B"}],
        "edges": [{"from": "A", "to": "B", "style": "invisible", "label": "never appears"}],
    }),
    "node-with-no-usable-id": ("flowchart", {
        "nodes": [{"id": "", "label": "lost"}, {"id": "A"}],
    }),
    "node-with-a-whitespace-id": ("flowchart", {"nodes": [{"id": "   ", "label": "lost"}]}),
    "participant-with-no-usable-id": ("sequence", {
        "participants": [{"id": ""}, {"id": "A"}], "messages": [],
    }),
    "subgraph-member-nothing-defines": ("flowchart", {
        "subgraphs": [{"id": "g1", "label": "Phase one", "nodes": ["A", "MISSING"]}],
        "nodes": [{"id": "A", "label": "a"}],
    }),
    "subgraph-with-no-usable-id": ("flowchart", {
        "subgraphs": [{"label": "nameless", "nodes": ["A"]}],
        "nodes": [{"id": "A", "label": "a"}],
    }),
    "length-above-the-range": ("flowchart", {
        "nodes": [{"id": "A"}, {"id": "B"}],
        "edges": [{"from": "A", "to": "B", "length": 99}],
    }),
    "length-below-the-range": ("flowchart", {
        "nodes": [{"id": "A"}, {"id": "B"}],
        "edges": [{"from": "A", "to": "B", "length": 0}],
    }),
    "length-that-is-not-a-number": ("flowchart", {
        "nodes": [{"id": "A"}, {"id": "B"}],
        "edges": [{"from": "A", "to": "B", "length": "wide"}],
    }),
    "unknown-edge-style": ("flowchart", {
        "nodes": [{"id": "A"}, {"id": "B"}],
        "edges": [{"from": "A", "to": "B", "style": "wobbly"}],
    }),
    "unknown-message-style": ("sequence", {
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "label": "x", "style": "wobbly"}],
    }),
    "unknown-legacy-message-arrow": ("sequence", {
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "message": "x", "type": "==>"}],
    }),
}


def compile_row(row):
    """Compile one off-dialect row with its own compiler."""
    kind, spec = OFF_DIALECT[row]
    return COMPILERS[kind](spec)


# --------------------------------------------------------------------------- #
# AC1 — EVERY off-dialect construct REFUSES, and the detail names it           #
# --------------------------------------------------------------------------- #

def test_row_1_an_edge_naming_a_node_NOBODY_DEFINED_is_refused():
    """The consumer's headline repro, verbatim. It used to return a diagram with no edge."""
    with pytest.raises(LarkConfigError) as caught:
        compile_row("unknown-node-in-an-edge")
    message = str(caught.value)
    assert "ZZ" in message, message          # the unknown id
    assert "'A'" in message, message         # …and the edge that names it, both endpoints
    assert "no node defines" in message, message


def test_row_1_the_same_refusal_when_the_SOURCE_is_the_unknown_one():
    with pytest.raises(LarkConfigError) as caught:
        compile_row("unknown-node-as-an-edge-source")
    message = str(caught.value)
    assert "PHANTOM" in message and "'A'" in message, message


def test_row_2_a_message_naming_an_UNDECLARED_PARTICIPANT_is_refused():
    with pytest.raises(LarkConfigError) as caught:
        compile_row("unknown-participant-in-a-message")
    message = str(caught.value)
    assert "GHOST" in message, message
    assert "'A'" in message, message
    assert "no participant declares" in message, message


def test_row_2_the_same_refusal_when_the_SENDER_is_the_undeclared_one():
    with pytest.raises(LarkConfigError) as caught:
        compile_row("unknown-participant-as-a-sender")
    assert "PHANTOM" in str(caught.value)


def test_row_3_an_unknown_SHAPE_is_refused_and_the_valid_set_is_enumerated():
    with pytest.raises(LarkConfigError) as caught:
        compile_row("unknown-shape")
    message = str(caught.value)
    assert "hexagon" in message, message
    for spelling in SHAPE_ALIASES:
        assert spelling in message, (spelling, message)


def test_row_3_a_node_with_NO_shape_still_gets_the_default_one():
    """The default is not a guess: a spec that names no shape is asking for the rectangle."""
    assert "A[a]" in flowchart({"nodes": [{"id": "A", "label": "a"}]})
    assert DEFAULT_SHAPE == "rect"


def test_row_4_an_unknown_DIRECTION_is_refused_and_the_valid_set_is_enumerated():
    with pytest.raises(LarkConfigError) as caught:
        compile_row("unknown-direction")
    message = str(caught.value)
    assert "XX" in message, message
    for direction in DIRECTIONS:
        assert direction in message, (direction, message)
    for synonym in DIRECTION_SYNONYMS:
        assert synonym in message, (synonym, message)


def test_row_4_a_spec_that_names_NO_direction_still_gets_the_vertical_one():
    for absent in ({}, {"direction": None}, {"direction": ""}):
        spec = dict(absent, nodes=[{"id": "A", "label": "a"}])
        assert f"flowchart {DEFAULT_DIRECTION}" in flowchart(spec), spec


def test_row_5_a_LABEL_ON_AN_INVISIBLE_EDGE_is_refused_as_a_combination():
    """Neither part is off-dialect alone — the combination is, and it used to lose the label."""
    with pytest.raises(LarkConfigError) as caught:
        compile_row("label-on-an-invisible-edge")
    message = str(caught.value)
    assert "never appears" in message, message
    assert "'A'" in message and "'B'" in message, message
    assert "cannot carry a label" in message, message


def test_row_5_an_invisible_edge_with_NO_label_still_compiles():
    out = flowchart({
        "nodes": [{"id": "A"}, {"id": "B"}],
        "edges": [{"from": "A", "to": "B", "style": "invisible"}],
    })
    assert "A ~~~ B" in out


@pytest.mark.parametrize("row", ["node-with-no-usable-id", "node-with-a-whitespace-id"])
def test_row_6_a_node_whose_id_sanitizes_to_NOTHING_is_refused_by_position(row):
    """There is no identifier to quote, so the refusal names the position instead."""
    with pytest.raises(LarkConfigError) as caught:
        compile_row(row)
    message = str(caught.value)
    assert "position 1" in message, message
    assert "node" in message, message


def test_row_6_a_participant_whose_id_sanitizes_to_nothing_is_refused_by_position():
    with pytest.raises(LarkConfigError) as caught:
        compile_row("participant-with-no-usable-id")
    message = str(caught.value)
    assert "position 1" in message, message
    assert "participant" in message, message


def test_row_6_the_node_drop_used_to_take_EVERY_EDGE_TOUCHING_IT_with_it():
    """The compound failure: the node vanished silently and the edge then vanished too, so a
    caller lost two constructs and was told about at most one of them."""
    with pytest.raises(LarkConfigError) as caught:
        flowchart({
            "nodes": [{"id": "", "label": "lost"}, {"id": "A"}],
            "edges": [{"from": "", "to": "A"}],
        })
    assert "position 1" in str(caught.value)


def test_row_7_a_SUBGRAPH_MEMBER_nothing_defines_is_refused():
    with pytest.raises(LarkConfigError) as caught:
        compile_row("subgraph-member-nothing-defines")
    message = str(caught.value)
    assert "MISSING" in message, message
    assert "g1" in message, message


def test_row_8_a_SUBGRAPH_WITH_NO_USABLE_ID_is_refused_rather_than_renamed():
    """It used to become the literal ``group`` — so two of them collided under one name."""
    with pytest.raises(LarkConfigError) as caught:
        compile_row("subgraph-with-no-usable-id")
    message = str(caught.value)
    assert "position 1" in message, message
    assert "subgraph" in message, message


def test_row_8_two_unnamed_subgraphs_no_longer_COLLIDE_UNDER_ONE_NAME():
    with pytest.raises(LarkConfigError):
        flowchart({
            "subgraphs": [{"label": "one", "nodes": ["A"]}, {"label": "two", "nodes": ["B"]}],
            "nodes": [{"id": "A"}, {"id": "B"}],
        })


@pytest.mark.parametrize(
    "row", ["length-above-the-range", "length-below-the-range", "length-that-is-not-a-number"]
)
def test_row_9_a_LENGTH_outside_the_range_or_not_a_number_is_refused_with_the_range(row):
    with pytest.raises(LarkConfigError) as caught:
        compile_row(row)
    message = str(caught.value)
    low, high = EDGE_LENGTH_RANGE
    assert str(low) in message and str(high) in message, message
    offending = repr(OFF_DIALECT[row][1]["edges"][0]["length"])
    assert offending in message, (offending, message)


def test_row_9_every_length_INSIDE_the_range_still_compiles():
    low, high = EDGE_LENGTH_RANGE
    for length in range(low, high + 1):
        out = flowchart({
            "nodes": [{"id": "A"}, {"id": "B"}],
            "edges": [{"from": "A", "to": "B", "length": length}],
        })
        assert f"A {'-' * (length + 1)}> B" in out, (length, out)


def test_row_10_an_unknown_EDGE_STYLE_is_refused_with_the_valid_set():
    with pytest.raises(LarkConfigError) as caught:
        compile_row("unknown-edge-style")
    message = str(caught.value)
    assert "wobbly" in message, message
    for style in EDGE_STYLES:
        assert style in message, (style, message)


def test_row_10_an_unknown_MESSAGE_STYLE_is_refused_with_the_valid_set():
    with pytest.raises(LarkConfigError) as caught:
        compile_row("unknown-message-style")
    message = str(caught.value)
    assert "wobbly" in message, message
    for style in MESSAGE_ARROWS:
        assert style in message, (style, message)


def test_row_10_an_unknown_LEGACY_ARROW_is_refused_with_the_whitelist():
    with pytest.raises(LarkConfigError) as caught:
        compile_row("unknown-legacy-message-arrow")
    message = str(caught.value)
    assert "==>" in message, message
    for arrow in LEGACY_ARROWS:
        assert arrow in message, (arrow, message)


def test_row_10_the_default_styles_are_still_the_solid_ones():
    """A message or edge that names no style is not guessing — the default is the rule."""
    assert DEFAULT_EDGE_STYLE in EDGE_STYLES
    assert DEFAULT_MESSAGE_STYLE in MESSAGE_ARROWS
    assert "A --> B" in flowchart({
        "nodes": [{"id": "A"}, {"id": "B"}], "edges": [{"from": "A", "to": "B"}],
    })
    assert "A->>B: x" in sequence({
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "label": "x"}],
    })


@pytest.mark.parametrize("row", sorted(OFF_DIALECT))
def test_EVERY_off_dialect_row_raises_the_typed_error_with_a_NON_EMPTY_detail(row):
    """The sweep, so the ten constructs are covered as a set and not only one by one: the
    refusal detail is never empty (a typed error with nothing in it tells a caller nothing)."""
    with pytest.raises(LarkConfigError) as caught:
        compile_row(row)
    detail = str(caught.value).strip()
    assert detail, f"{row} raised with an empty detail"
    assert len(detail) > 20, (row, detail)


@pytest.mark.parametrize("row", sorted(OFF_DIALECT))
def test_no_off_dialect_row_PRODUCES_SOURCE_AT_ALL(row):
    """Nothing partial escapes: the refusal happens instead of a compile, not after one."""
    kind, spec = OFF_DIALECT[row]
    try:
        produced = COMPILERS[kind](spec)
    except LarkConfigError:
        return
    raise AssertionError(f"{row} compiled to source instead of refusing:\n{produced}")


# --------------------------------------------------------------------------- #
# AC2 — STRICT BY DEFAULT, and there is NO escape hatch                        #
# --------------------------------------------------------------------------- #

#: Names for a leniency switch. None of them may appear as a parameter anywhere in the
#: package's callables: a flag that makes the guessing reachable makes it reachable *by
#: accident*, and every caller who passes it re-creates the defect this file closes.
LENIENCY_PARAMETERS = ("strict", "lenient", "warn_only", "permissive", "force", "quiet")


def package_callables():
    """``{qualified name: callable}`` for every public callable the package exposes."""
    import larkdocio.mermaid as package
    from larkdocio.mermaid import ruleset

    found = {}
    for module in (package, ruleset):
        for name in dir(module):
            if name.startswith("_"):
                continue
            attribute = getattr(module, name)
            if inspect.isfunction(attribute):
                found[f"{module.__name__}.{name}"] = attribute
    return found


def test_no_compiler_entry_point_accepts_a_LENIENCY_PARAMETER():
    """Read off the real signatures, so adding one later reddens this."""
    offenders = {}
    for label, function in package_callables().items():
        parameters = set(inspect.signature(function).parameters)
        hits = parameters & set(LENIENCY_PARAMETERS)
        if hits:
            offenders[label] = sorted(hits)
    assert not offenders, offenders


def test_the_two_compilers_take_EXACTLY_ONE_ARGUMENT_EACH():
    """The narrow form of the same property, stated where a reader will look for it."""
    assert list(inspect.signature(flowchart).parameters) == ["spec"]
    assert list(inspect.signature(sequence).parameters) == ["spec"]


def test_the_signature_check_REALLY_BITES():
    """Otherwise the sweep above could be inspecting an empty set of callables."""
    def lenient_compiler(spec, strict=True):
        return spec

    assert set(inspect.signature(lenient_compiler).parameters) & set(LENIENCY_PARAMETERS)
    assert package_callables(), "no callable was inspected at all"


# --------------------------------------------------------------------------- #
# AC3 — NO silent side-channel survives                                        #
# --------------------------------------------------------------------------- #

def print_call_lines(source):
    """Line numbers where ``print`` is called."""
    return sorted(
        node.lineno for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    )


def warning_sites(source):
    """``{enclosing function name: [line, …]}`` for every ``…warning(…)`` / ``…warn(…)``."""
    sites = {}
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr in ("warning", "warn", "warn_explicit")
            ):
                sites.setdefault(node.name, []).append(inner.lineno)
    return sites


def package_sources():
    return {path.name: path.read_text(encoding="utf-8")
            for path in sorted(PACKAGE.rglob("*.py"))}  # LD-654: recursive population


def test_leg_a_NO_PRINT_and_no_write_to_a_standard_stream_anywhere_in_the_package():
    """Structural, so a future one reddens rather than being noticed in review."""
    offenders = {}
    for name, source in package_sources().items():
        lines = print_call_lines(source)
        if lines:
            offenders[name] = lines
        for stream in ("sys.stdout", "sys.stderr", "sys.__stdout__", "sys.__stderr__"):
            assert stream not in source, (name, stream)
    assert not offenders, offenders


def test_leg_b_the_ONLY_WARNINGS_LEFT_are_the_two_ADVISORY_RULES():
    """The warn-and-continue pattern is gone. Not a blanket ban on warning: the two advisory
    rules are judgments about a valid spec and must keep theirs (see the advisory section)."""
    everywhere = {}
    for name, source in package_sources().items():
        for function, lines in warning_sites(source).items():
            everywhere[f"{name}:{function}"] = lines
    assert set(everywhere) == {
        "ruleset.py:warn_if_complex",
        "ruleset.py:warn_if_horizontal_and_wide",
    }, everywhere


def test_the_structural_scans_REALLY_BITE():
    """Both legs, applied to a synthetic module that commits both defects."""
    sample = textwrap.dedent(
        """
        import logging

        logger = logging.getLogger("larkdocio")

        def _emit(items, known):
            for item in items:
                if item not in known:
                    print("dropping", item)
                    logger.warning("edge references unknown node id %r", item)
                    continue
                yield item
        """
    )
    assert print_call_lines(sample) == [9]
    assert warning_sites(sample) == {"_emit": [10]}


@pytest.mark.parametrize("row", sorted(OFF_DIALECT))
def test_every_off_dialect_row_RAISES_INSTEAD_OF_LOGGING(row, caplog):
    """The refusal REPLACES the log line rather than joining it — otherwise the same content
    would still be discarded, only more loudly."""
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        with pytest.raises(LarkConfigError):
            compile_row(row)
    assert not caplog.records, [record.getMessage() for record in caplog.records]


# --------------------------------------------------------------------------- #
# AC4 — THE ADVISORY CLASS IS UNTOUCHED                                        #
# --------------------------------------------------------------------------- #

#: The rules that warn and then honor the caller's choice. Held by EQUALITY, so a
#: reclassification in EITHER direction reddens: promoting one to a refusal would break valid
#: specs and falsify the shipped rule document, and demoting an enforced rule would re-open
#: the defect this file closes.
ADVISORY_RULE_KEYS = {"vertical", "complexity"}


def test_the_advisory_set_is_EXACTLY_the_two_layout_judgments():
    assert {rule.key for rule in RULES if rule.posture == ADVISORY} == ADVISORY_RULE_KEYS
    assert len([rule for rule in RULES if rule.posture == ADVISORY]) == 2


def test_a_diagram_PAST_THE_COMPLEXITY_CEILING_still_compiles_and_still_warns(caplog):
    nodes = [{"id": f"N{index}", "label": f"N{index}"} for index in range(17)]
    edges = [{"from": f"N{index}", "to": f"N{index + 1}"} for index in range(14)]
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        out = flowchart({"nodes": nodes, "edges": edges})
    assert f"flowchart {DEFAULT_DIRECTION}" in out          # compiled, not refused
    assert len(caplog.records) == 1, [r.getMessage() for r in caplog.records]
    message = caplog.records[0].getMessage()
    assert "complexity" in message and str(COMPLEXITY_LIMIT) in message, message


def test_a_WIDE_HORIZONTAL_diagram_still_compiles_and_still_warns(caplog):
    count = VERTICAL_PREFERRED_ABOVE + 1
    nodes = [{"id": f"N{index}", "label": f"N{index}"} for index in range(count)]
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        out = flowchart({"direction": "LR", "nodes": nodes})
    assert "flowchart LR" in out                            # the direction is honored
    assert len(caplog.records) == 1, [r.getMessage() for r in caplog.records]
    assert "LR" in caplog.records[0].getMessage()


def test_the_shipped_rule_document_still_TEACHES_BOTH_AS_ADVISORY():
    prose = rules()
    for title in ("Prefer the vertical direction", "The complexity ceiling"):
        section = prose.split(f"### {title}", 1)
        assert len(section) == 2, title
        body = section[1].split("\n### ", 1)[0]
        assert "advisory" in body.lower(), (title, body)
    assert "| Prefer the vertical direction | advisory |" in prose
    assert "| The complexity ceiling | advisory |" in prose


# --------------------------------------------------------------------------- #
# AC5 — VALID specs compile BYTE-IDENTICALLY to what the previous trunk emitted #
# --------------------------------------------------------------------------- #

def captured_bytes():
    """The compiled source each corpus spec produced BEFORE the strict-dialect change."""
    return json.loads((FIXTURES / "mermaid_compat_bytes.json").read_text(encoding="utf-8"))


def drifted(expected, corpus=None):
    """``{name: (expected, actual)}`` for every corpus spec whose bytes moved."""
    corpus = mermaid_compat_corpus.CORPUS if corpus is None else corpus
    moved = {}
    for name, (kind, spec) in corpus.items():
        actual = COMPILERS[kind](spec)
        if actual != expected[name]:
            moved[name] = (expected[name], actual)
    return moved


def test_the_captured_corpus_and_the_spec_corpus_are_THE_SAME_SET():
    assert set(captured_bytes()) == set(mermaid_compat_corpus.CORPUS)
    assert len(mermaid_compat_corpus.CORPUS) > 50, "the corpus is smaller than it was"


def test_every_valid_corpus_spec_compiles_BYTE_IDENTICALLY_to_the_captured_bytes():
    assert not drifted(captured_bytes())


def test_the_byte_comparison_REALLY_BITES():
    """Otherwise the harness above could be comparing nothing: one byte is moved in the
    expectation and the comparison must report exactly that spec."""
    expected = captured_bytes()
    name = "every-shape"
    doctored = dict(expected, **{name: expected[name].replace("[Rect]", "[RECT]")})
    assert set(drifted(doctored)) == {name}


def test_the_corpus_covers_the_SHAPES_THAT_HISTORICALLY_MATTERED():
    """The promise is about real historical shapes, so the corpus is checked for them rather
    than trusted to be representative."""
    joined = json.dumps(mermaid_compat_corpus.CORPUS)
    for construct in ("subgraphs", "invisible", "length", "rounded", "database", "type",
                      "message", "participants"):
        assert construct in joined, construct


# --------------------------------------------------------------------------- #
# AC6 — the guide's "caught HERE" claim is TRUE as shipped                     #
# --------------------------------------------------------------------------- #

def diagram_recipe():
    text = guide(full=True)
    heading = "### Recipe: author a mermaid diagram (and change one)"
    assert heading in text
    return text.split(heading, 1)[1].split("\n### ", 1)[0]


def test_the_guide_claims_a_REFUSAL_and_names_the_classes_that_refuse():
    """The claim used to spell out two examples, exactly one of which was true. It now names
    the classes, so a reader can tell what the compiler will and will not catch."""
    recipe = diagram_recipe().lower()
    assert "refused" in recipe or "refuse" in recipe, recipe
    for named in ("theme", "direction", "shape", "style", "invisible"):
        assert named in recipe, named


def test_the_guide_does_not_promise_a_FALLBACK_OR_A_DROP_anywhere_in_the_recipe():
    recipe = diagram_recipe().lower()
    for forbidden in ("falls back", "is dropped", "silently"):
        assert forbidden not in recipe, forbidden


def test_the_guide_still_says_which_rules_only_WARN():
    """The other half of an honest claim: two rules are advisory, and a reader who is told
    'off-dialect input refuses' would otherwise expect a refusal for a big diagram too."""
    recipe = diagram_recipe().lower()
    assert "advisory" in recipe or "warn" in recipe, recipe
