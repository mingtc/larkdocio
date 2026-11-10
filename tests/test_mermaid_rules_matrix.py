# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""THE THREE-PART DRIFT GUARD — rule prose ↔ rule constants ↔ compiler behavior.

The failure this exists to make impossible is the one the ported generator shipped with: a
rule document stating constraints that nothing checked. Four of its rules were prose only,
and one of them its own compiler broke — so the document was not a specification, it was a
hope.

The guard has three legs, and each is red-proved separately below:

* **Leg one — prose ↔ constants.** Every rule the document tabulates names constants that
  really exist, and every constant in the registry is documented. Both directions.
* **Leg two — constants ↔ tests.** Every constant a rule names is referenced by a test that
  exercises a compiler, so a constant cannot sit in the module unexercised.
* **Leg three — constants ↔ behavior.** The compilers' real output obeys the constants, and
  a rule that is not enforced is marked **advisory** in the document rather than reading like
  a guarantee.

The document is read through the public accessor, not off disk, because that is the call a
caller makes.
"""
import pathlib
import re

import pytest

from guard_kit import md_table_cells
from larkdocio.mermaid import escape_label, flowchart, rules, ruleset, sequence
from larkdocio.mermaid.ruleset import ADVISORY, ENFORCED, RULES

# LD-370 — CONFORMANCE-tier: the mermaid dialect rules are a published contract for what the library will and will not encode.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

TESTS = pathlib.Path(__file__).resolve().parent

#: The test modules that exercise the compilers — leg two's evidence base.
BEHAVIOR_TEST_FILES = (
    "test_mermaid_escape.py",
    "test_mermaid_flowchart.py",
    "test_mermaid_sequence.py",
    "test_mermaid_rules_matrix.py",
    "test_mermaid_port_fence.py",
    "test_mermaid_strict_dialect.py",
    # LD-659 AC1: the control-character refusal. Enrolled in the SAME change as the rule it
    # exercises — leg two reads this tuple, so a rule whose only tests live outside it reports
    # as "exercised by no test", which is the honest answer and not one to work around.
    "test_mermaid_control_chars.py",
)

_CODE_RE = re.compile(r"`([^`]+)`")
_BLANK_LINE_RE = re.compile(r"^[ \t]*$", re.MULTILINE)


# --------------------------------------------------------------------------- #
# The parsers — pure functions, so every leg can be applied to INJECTED input  #
# --------------------------------------------------------------------------- #

def prose_rows(prose):
    """``[(title, posture, (constants...))]`` parsed out of the document's rule table."""
    rows = []
    for line in prose.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = md_table_cells(stripped)
        if len(cells) != 3:
            continue
        title, posture, constants = cells
        if title.lower() == "rule" or set(title) <= set("-: "):
            continue
        rows.append((title, posture.lower(), tuple(_CODE_RE.findall(constants))))
    return rows


def prose_sections(prose):
    """``{heading: body}`` for every ``###`` section of the document."""
    sections = {}
    heading = None
    body = []
    for line in prose.splitlines():
        if line.startswith("### "):
            if heading is not None:
                sections[heading] = "\n".join(body)
            heading = line[4:].strip()
            body = []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections[heading] = "\n".join(body)
    return sections


def labelled_values(body, label):
    """The backticked tokens on the ``- <label>: …`` line of a section body."""
    for line in body.splitlines():
        stripped = line.strip().lstrip("-").strip()
        if stripped.lower().startswith(f"{label.lower()}:"):
            return tuple(_CODE_RE.findall(stripped))
    return ()


def leg_one_problems(rows, rules_registry=RULES, module=ruleset):
    """Prose ↔ constants, both directions."""
    problems = []
    documented = {title: (posture, constants) for title, posture, constants in rows}
    registered = {rule.title: (rule.posture, tuple(rule.constants)) for rule in rules_registry}

    for title in sorted(set(registered) - set(documented)):
        problems.append(f"rule {title!r} is in the registry but the document omits it")
    for title in sorted(set(documented) - set(registered)):
        problems.append(f"the document tabulates rule {title!r}, which the registry has not")

    for title in sorted(set(documented) & set(registered)):
        if documented[title][0] != registered[title][0]:
            problems.append(
                f"rule {title!r} is {documented[title][0]!r} in the document and "
                f"{registered[title][0]!r} in the registry"
            )
        if documented[title][1] != registered[title][1]:
            problems.append(
                f"rule {title!r} names {documented[title][1]} in the document and "
                f"{registered[title][1]} in the registry"
            )

    for title, _posture, constants in rows:
        for name in constants:
            if not hasattr(module, name):
                problems.append(
                    f"rule {title!r} names constant {name!r}, which does not exist"
                )
    return problems


def leg_two_problems(rules_registry=RULES, sources=None):
    """Constants ↔ tests: every constant a rule names is referenced by a behavior test."""
    if sources is None:
        sources = behavior_test_sources()
    joined = "\n".join(sources.values())
    problems = []
    for rule in rules_registry:
        for name in rule.constants:
            if name not in joined:
                problems.append(
                    f"constant {name!r} (rule {rule.title!r}) is exercised by no test"
                )
    return problems


def leg_three_problems(rows, sections):
    """Constants ↔ behavior: a rule that is not enforced must say so where it is read."""
    problems = []
    for title, posture, _constants in rows:
        body = sections.get(title)
        if body is None:
            problems.append(f"rule {title!r} has no section a reader can consult")
            continue
        says_advisory = "advisory" in body.lower()
        if posture == ADVISORY and not says_advisory:
            problems.append(
                f"rule {title!r} is advisory but its section does not say so — it reads "
                f"like a guarantee"
            )
        if posture == ENFORCED and says_advisory:
            problems.append(
                f"rule {title!r} is enforced but its section calls itself advisory"
            )
    return problems


def behavior_problems(outputs):
    """Every way a compiled diagram can contradict a rule constant."""
    problems = []
    for label, text in outputs.items():
        if _BLANK_LINE_RE.search(text) and not ruleset.BLANK_LINE_ALLOWED:
            problems.append(f"{label}: a blank line appears inside the block")
        declarations = [
            line for line in text.splitlines()
            if line and not line.startswith((" ", "%"))
        ]
        for declaration in declarations:
            if declaration not in ruleset.SANCTIONED_DECLARATIONS:
                problems.append(f"{label}: unsanctioned declaration {declaration!r}")
        for line in text.splitlines():
            if line.startswith("%%{init:") and '"' in line:
                problems.append(f"{label}: the init line is not in the declared quote style")
            if line.strip().startswith(("#", "//")):
                problems.append(f"{label}: a comment does not use the declared prefix")
        for node_id, tail in _DEFINITION_RE.findall(text):
            if any(tail.startswith(arrow) for arrow in _ARROWS):
                continue  # a sequence message, not a node definition
            rendered = {
                template.format(node_id=node_id, label=_label_of(tail))
                for template in ruleset.SHAPE_TEMPLATES.values()
            }
            if f"{node_id}{tail}" not in rendered:
                problems.append(f"{label}: shape {node_id}{tail!r} matches no template")
    return problems


#: An indented line whose identifier is followed immediately by punctuation — a node
#: definition, or a sequence message (which the arrow check below sorts out).
_DEFINITION_RE = re.compile(r"^\s+(\w+)([^\w\s].*)$", re.MULTILINE)

_ARROWS = set(ruleset.LEGACY_ARROWS) | set(ruleset.MESSAGE_ARROWS.values())


def _label_of(tail):
    """The label text inside a rendered shape's brackets."""
    return tail.strip("[]{}()")


def behavior_test_sources():
    """``{filename: source}`` for the test modules that exercise the compilers."""
    return {
        name: (TESTS / name).read_text(encoding="utf-8") for name in BEHAVIOR_TEST_FILES
    }


def real_outputs():
    """A representative compile from each compiler, exercising every emitting branch."""
    return {
        "flowchart": flowchart({
            "title": "Everything",
            "theme": "dark",
            "direction": "LR",
            "subgraphs": [{"id": "g1", "label": "Phase 1", "nodes": ["A", "B"]}],
            "nodes": [
                {"id": "A", "label": "Start (now)", "shape": "round"},
                {"id": "B", "label": "Check", "shape": "diamond"},
                {"id": "C", "label": "Store", "shape": "cylinder"},
                {"id": "Dd", "label": "Done", "shape": "rect"},
            ],
            "edges": [
                {"from": "A", "to": "B"},
                {"from": "B", "to": "C", "label": "yes", "style": "thick"},
                {"from": "B", "to": "Dd", "label": "no", "style": "dotted", "length": 2},
                {"from": "C", "to": "Dd", "style": "invisible"},
            ],
        }),
        "sequence": sequence({
            "title": "Authentication",
            "theme": "forest",
            "participants": [
                {"id": "Client", "label": "Mobile App"},
                {"id": "Gateway"},
                "Auth",
            ],
            "messages": [
                {"from": "Client", "to": "Gateway", "label": "1. POST /login"},
                {"from": "Gateway", "to": "Auth", "label": "2. validate", "style": "solid"},
                {"from": "Auth", "to": "Client", "label": "3. token", "style": "dotted"},
            ],
        }),
    }


@pytest.fixture(scope="module")
def prose():
    return rules()


@pytest.fixture(scope="module")
def rows(prose):
    return prose_rows(prose)


@pytest.fixture(scope="module")
def sections(prose):
    return prose_sections(prose)


# --------------------------------------------------------------------------- #
# The document is reachable at all                                            #
# --------------------------------------------------------------------------- #

def test_the_rule_document_is_reachable_through_the_accessor(prose):
    assert prose.strip(), "the accessor returned nothing"
    assert prose.startswith("# "), prose[:80]


def test_the_document_states_that_the_ported_rules_were_re_validated(prose):
    lowered = prose.lower()
    assert "stale" in lowered
    assert "re-validated" in lowered or "revalidated" in lowered


# --------------------------------------------------------------------------- #
# LEG ONE — prose ↔ constants                                                 #
# --------------------------------------------------------------------------- #

def test_leg_one_the_document_and_the_registry_agree(rows):
    assert rows, "the rule table could not be parsed at all"
    assert not leg_one_problems(rows)


def test_leg_one_every_registered_rule_is_documented(rows):
    documented = {title for title, _posture, _constants in rows}
    assert documented == {rule.title for rule in RULES}


def test_leg_one_RED_a_documented_rule_naming_a_constant_THAT_DOES_NOT_EXIST(prose):
    """Leg one, direction one, proven red through the real parse."""
    doctored = prose + "\n| Telepathy | enforced | `TELEPATHY_LIMIT` |\n"
    problems = leg_one_problems(prose_rows(doctored))
    assert any("TELEPATHY_LIMIT" in p for p in problems), problems
    assert any("Telepathy" in p for p in problems), problems


def test_leg_one_RED_a_registered_rule_the_document_omits(rows):
    """Leg one, direction two: a constant registry the document has not caught up with."""
    invented = ruleset.Rule("ghost", "A rule nobody wrote down", ENFORCED, ("THEMES",))
    problems = leg_one_problems(rows, rules_registry=RULES + (invented,))
    assert any("A rule nobody wrote down" in p for p in problems), problems


def test_leg_one_RED_a_posture_that_disagrees_with_the_registry(prose):
    doctored = prose.replace(
        "| The complexity ceiling | advisory |", "| The complexity ceiling | enforced |"
    )
    assert doctored != prose, "the posture cell was not found; the probe is stale"
    problems = leg_one_problems(prose_rows(doctored))
    assert any("complexity" in p.lower() for p in problems), problems


def test_leg_one_RED_a_dropped_constant_reference(prose):
    doctored = prose.replace(
        "| The theme whitelist | enforced | `THEMES`, `DEFAULT_THEME` |",
        "| The theme whitelist | enforced | `THEMES` |",
    )
    assert doctored != prose, "the theme row was not found; the probe is stale"
    problems = leg_one_problems(prose_rows(doctored))
    assert any("The theme whitelist" in p for p in problems), problems


# --------------------------------------------------------------------------- #
# LEG TWO — constants ↔ tests                                                 #
# --------------------------------------------------------------------------- #

def test_leg_two_every_rule_constant_is_exercised_by_a_test():
    assert not leg_two_problems()


def test_leg_two_RED_a_constant_no_test_mentions():
    # The name is assembled at run time so this file does not itself contain it — the
    # sources being scanned include this one.
    unexercised = "A_CONSTANT_" + "NOTHING_NAMES"
    invented = ruleset.Rule("ghost", "Unexercised", ENFORCED, (unexercised,))
    problems = leg_two_problems(rules_registry=(invented,))
    assert problems == [
        f"constant {unexercised!r} (rule 'Unexercised') is exercised by no test"
    ]


def test_leg_two_RED_the_check_reads_the_REAL_sources_not_an_empty_set():
    """The must-not-pass-vacuously half: with the sources emptied, every rule is reported."""
    problems = leg_two_problems(sources={"nothing.py": ""})
    assert len(problems) >= len(RULES)


# --------------------------------------------------------------------------- #
# LEG THREE — constants ↔ behavior                                            #
# --------------------------------------------------------------------------- #

def test_leg_three_the_real_compiler_output_obeys_every_constant():
    assert not behavior_problems(real_outputs())


def test_leg_three_every_advisory_rule_is_marked_advisory_where_it_is_read(rows, sections):
    assert not leg_three_problems(rows, sections)


def test_leg_three_at_least_one_rule_really_is_advisory(rows):
    """Otherwise the advisory arm would be dead machinery."""
    assert [row for row in rows if row[1] == ADVISORY]


def test_leg_three_RED_an_advisory_rule_that_does_not_say_so(rows, sections):
    doctored = dict(sections)
    advisory_title = next(title for title, posture, _c in rows if posture == ADVISORY)
    doctored[advisory_title] = re.sub(
        "advisory", "guaranteed", doctored[advisory_title], flags=re.IGNORECASE
    )
    problems = leg_three_problems(rows, doctored)
    assert any(advisory_title in p for p in problems), problems


def test_leg_three_RED_a_rule_with_no_section_at_all(rows, sections):
    doctored = {k: v for k, v in sections.items() if k != rows[0][0]}
    problems = leg_three_problems(rows, doctored)
    assert any("no section" in p for p in problems), problems


def test_leg_three_RED_a_COMPILER_that_violates_a_shape_constant(monkeypatch):
    """The behavior leg, red through a REAL compile: the shape template is changed so the
    compiler emits a shape the constant does not sanction."""
    monkeypatch.setitem(ruleset.SHAPE_TEMPLATES, "rect", "{node_id}<<{label}>>")
    out = flowchart({"nodes": [{"id": "A", "label": "A"}]})
    problems = behavior_problems({"doctored": out})
    assert problems, out


def test_leg_three_RED_a_COMPILER_that_emits_an_unsanctioned_declaration(monkeypatch):
    """The same leg through the other constant: the fallback direction is changed to one the
    sanctioned declarations do not carry.

    The probe reaches the fallback by naming **no** direction. It used to name a nonsense one
    and rely on the fallback catching it — that route is gone, because an off-dialect direction
    is now refused rather than replaced, and a probe that raised would prove nothing about the
    behavior leg.
    """
    monkeypatch.setattr(ruleset, "DEFAULT_DIRECTION", "RL")
    out = flowchart({"nodes": [{"id": "A", "label": "A"}]})
    assert "flowchart RL" in out
    problems = behavior_problems({"doctored": out})
    assert any("unsanctioned declaration" in p for p in problems), problems


def test_leg_three_RED_a_blank_line_inside_the_block():
    out = flowchart({"nodes": [{"id": "A", "label": "A"}]})
    doctored = out.replace("flowchart TD", "flowchart TD\n")
    problems = behavior_problems({"doctored": doctored})
    assert any("blank line" in p for p in problems), problems


def test_leg_three_RED_an_init_line_in_the_wrong_quote_style():
    out = flowchart({"theme": "dark", "nodes": [{"id": "A", "label": "A"}]})
    doctored = out.replace("'", '"')
    problems = behavior_problems({"doctored": doctored})
    assert any("quote style" in p for p in problems), problems


# --------------------------------------------------------------------------- #
# THE VALUES — every number and name in the prose is the constant's own        #
# --------------------------------------------------------------------------- #

def test_the_documented_declarations_are_the_sanctioned_ones(sections):
    body = sections["Supported diagram declarations"]
    assert labelled_values(body, "Declarations") == ruleset.SANCTIONED_DECLARATIONS
    assert labelled_values(body, "Diagram kinds") == ruleset.SUPPORTED_DIAGRAM_TYPES
    assert labelled_values(body, "Avoid") == ruleset.UNSTABLE_DIAGRAM_TYPES
    assert labelled_values(body, "Directions") == ruleset.DIRECTIONS
    assert labelled_values(body, "Fallback direction") == (ruleset.DEFAULT_DIRECTION,)


def test_the_documented_synonym_is_the_registered_one(sections):
    body = sections["Supported diagram declarations"]
    documented = labelled_values(body, "Synonyms")
    assert documented == tuple(
        item for pair in ruleset.DIRECTION_SYNONYMS.items() for item in pair
    )


def test_the_documented_themes_are_the_whitelist(sections):
    body = sections["The theme whitelist"]
    assert labelled_values(body, "Themes") == ruleset.THEMES
    assert labelled_values(body, "Default") == (ruleset.DEFAULT_THEME,)


def test_the_documented_theme_count_is_the_real_one(sections):
    body = sections["The theme whitelist"]
    assert str(len(ruleset.THEMES)) in body


def test_the_documented_shapes_render_exactly_as_the_templates_do(sections):
    """A behavioral pin: the example in the document is produced BY the template."""
    body = sections["Sanctioned node shapes"]
    documented = labelled_values(body, "Shapes")
    assert len(documented) == 2 * len(ruleset.SHAPE_TEMPLATES)
    pairs = dict(zip(documented[::2], documented[1::2]))
    assert set(pairs) == set(ruleset.SHAPE_TEMPLATES)
    for shape, example in pairs.items():
        assert example == ruleset.SHAPE_TEMPLATES[shape].format(
            node_id="A", label="<label>"
        ), shape


def test_the_documented_aliases_are_the_registered_ones(sections):
    body = sections["Sanctioned node shapes"]
    documented = labelled_values(body, "Aliases")
    aliases = tuple(
        name for name, canonical in ruleset.SHAPE_ALIASES.items() if name != canonical
    )
    assert documented == aliases


def test_the_documented_edge_styles_and_lengths_are_the_constants(sections):
    body = sections["Edge styles and lengths"]
    assert labelled_values(body, "Styles") == ruleset.EDGE_STYLES
    assert labelled_values(body, "Length") == tuple(
        str(bound) for bound in ruleset.EDGE_LENGTH_RANGE
    )


def test_the_documented_arrows_are_the_sanctioned_ones(sections):
    body = sections["Sanctioned message arrows"]
    documented = labelled_values(body, "Arrows")
    expected = tuple(
        item for pair in sorted(ruleset.MESSAGE_ARROWS.items()) for item in pair
    )
    assert documented == expected
    assert labelled_values(body, "Also accepted") == ruleset.LEGACY_ARROWS


def test_the_documented_bad_characters_are_the_constant(sections):
    body = sections["Quoting labels that carry syntax"]
    assert labelled_values(body, "Bad characters") == ruleset.LABEL_BAD_CHARS


def test_the_documented_html_example_is_what_the_escaper_really_does(sections):
    """Another behavioral pin: the before/after in the document is computed, not typed."""
    body = sections["No HTML in labels"]
    documented = labelled_values(body, "Example")
    assert len(documented) == 2, documented
    before, after = documented
    assert after == escape_label(before)


def test_the_documented_init_line_is_what_the_emitter_really_produces(sections):
    body = sections["One init-line dialect"]
    documented = labelled_values(body, "Example")
    assert documented == (ruleset.init_line({"theme": "dark"}),)
    assert labelled_values(body, "Quote") == (ruleset.INIT_QUOTE,)


def test_the_documented_comment_prefix_is_the_constant(sections):
    body = sections["Comments"]
    assert labelled_values(body, "Prefix") == (ruleset.COMMENT_PREFIX,)


def test_the_document_states_no_blank_line_and_the_constant_agrees(sections):
    body = sections["No blank line inside the block"]
    assert labelled_values(body, "Blank lines") == ("none",)
    assert ruleset.BLANK_LINE_ALLOWED is False


def test_the_documented_participant_rule_matches_the_constant(sections):
    body = sections["Explicit participants"]
    assert labelled_values(body, "Participants") == ("required",)
    assert ruleset.EXPLICIT_PARTICIPANTS_REQUIRED is True


def test_the_documented_advisory_numbers_are_the_constants(sections):
    vertical = sections["Prefer the vertical direction"]
    assert labelled_values(vertical, "Preferred above") == (
        str(ruleset.VERTICAL_PREFERRED_ABOVE),
    )
    complexity = sections["The complexity ceiling"]
    assert labelled_values(complexity, "Ceiling") == (str(ruleset.COMPLEXITY_LIMIT),)


def test_a_drifted_number_in_the_prose_is_caught(sections):
    """Red-proof for the value pins: the ceiling drifts in the document alone."""
    doctored = sections["The complexity ceiling"].replace(
        f"`{ruleset.COMPLEXITY_LIMIT}`", "`300`"
    )
    assert labelled_values(doctored, "Ceiling") == ("300",)
    assert labelled_values(doctored, "Ceiling") != (str(ruleset.COMPLEXITY_LIMIT),)
