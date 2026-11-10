"""The sequence-diagram compiler — the ported suite, one ported test DELIBERATELY REWRITTEN.

Nineteen of the twenty cases the standalone generator's own suite covered port unchanged in
substance (header, title, the theme line's presence and absence, canonical and older
participant shapes, the style-to-arrow map, the older literal-arrow key, text escaping and
HTML stripping, and warn-and-skip on an undeclared participant).

**The twentieth pinned a bug.** The generator declared a participant id containing a space
through the label escaper — ``participant "Mobile App"`` — and then interpolated the *raw*
id into every message: ``Mobile App->>A: x``. The declaration and the reference disagree,
which is broken source, and its own test asserted the broken declaration as expected
behavior. That test is rewritten here: the id is sanitized once and used everywhere, which
is what the flowchart compiler always did. The failing case (an id with a space, declared
AND referenced) is asserted first below, so the fix is visible as behavior rather than as a
claim.

**A second round of rewrites, for the same class of reason.** Five further ported cases pinned
the generator's *leniency* as expected behavior — an unknown ``style`` and an unwhitelisted
literal arrow becoming the solid arrow, a message naming an undeclared participant being
dropped behind a log line, a participant with no usable identifier being skipped. Each of those
answers a spec the renderer cannot draw with a **different diagram** and no signal a caller can
read, so each now asserts the refusal. Every case is kept, with its own note; the bytes a
**valid** spec compiles to did not move, which ``tests/test_mermaid_strict_dialect.py`` holds
byte for byte against a captured corpus.
"""
import logging
import re

import pytest

from larkdocio.errors import LarkConfigError
from larkdocio.mermaid import sequence
from larkdocio.mermaid.ruleset import (
    COMPLEXITY_LIMIT,
    LEGACY_ARROWS,
    MESSAGE_ARROWS,
    SANCTIONED_DECLARATIONS,
    THEMES,
)

BLANK_LINE_RE = re.compile(r"^[ \t]*$", re.MULTILINE)


# --------------------------------------------------------------------------- #
# THE REWRITTEN CASE — an identifier is sanitized once and used everywhere      #
# --------------------------------------------------------------------------- #

def test_a_participant_id_with_a_space_is_declared_AND_REFERENCED_consistently():
    """The case the ported suite got wrong: declaration and reference must agree.

    Sanitized once, the id is ``Mobile_App`` in the declaration and in the message, and the
    human-readable form survives as the alias.
    """
    out = sequence({
        "participants": [{"id": "Mobile App", "label": "Mobile App"}, {"id": "B"}],
        "messages": [{"from": "Mobile App", "to": "B", "label": "hello", "style": "solid"}],
    })
    assert '    participant Mobile_App as "Mobile App"' in out
    assert "    Mobile_App->>B: hello" in out
    # The broken half the older test pinned must not be emitted.
    assert '    participant "Mobile App"' not in out
    assert "Mobile App->>" not in out


def test_an_older_bare_string_participant_with_a_space_is_sanitized_the_same_way():
    """The rewrite of the test that pinned the broken declaration.

    The older spec shape lets a participant be a bare string used as both id and label. The
    id is sanitized; the label is kept, so nothing readable is lost.
    """
    out = sequence({"participants": ["Mobile App"], "messages": []})
    assert '    participant Mobile_App as "Mobile App"' in out
    assert '    participant "Mobile App"' not in out


def test_a_message_naming_the_unsanitized_form_still_resolves():
    """A caller who wrote the id with a space in both places is not punished for it."""
    out = sequence({
        "participants": ["Mobile App", "Auth Service"],
        "messages": [{"from": "Mobile App", "to": "Auth Service", "label": "check"}],
    })
    assert "    Mobile_App->>Auth_Service: check" in out


def test_every_referenced_identifier_in_the_output_is_declared():
    """The property the rewrite buys: no message names an identifier no declaration does."""
    out = sequence({
        "participants": ["Mobile App", {"id": "Gate Way", "label": "API Gateway"}],
        "messages": [
            {"from": "Mobile App", "to": "Gate Way", "label": "a"},
            {"from": "Gate Way", "to": "Mobile App", "label": "b", "style": "dotted"},
        ],
    })
    declared = set(re.findall(r"^    participant (\S+)", out, re.MULTILINE))
    referenced = set()
    for line in out.splitlines():
        match = re.match(r"^    (\S+?)(->>|-->>|->|-->)(\S+?): ", line)
        if match:
            referenced.update({match.group(1), match.group(3)})
    assert referenced, out
    assert referenced <= declared, (referenced - declared, out)


# --------------------------------------------------------------------------- #
# The ported cases                                                            #
# --------------------------------------------------------------------------- #

def test_diagram_header():
    out = sequence({"participants": [{"id": "A"}], "messages": []})
    assert "sequenceDiagram" in out


def test_title_comment():
    out = sequence({"title": "Auth Flow", "participants": [{"id": "A"}], "messages": []})
    assert "    %% Auth Flow" in out


def test_non_default_theme_init_line():
    out = sequence({"theme": "dark", "participants": [{"id": "A"}], "messages": []})
    assert out.splitlines()[0] == "%%{init: {'theme': 'dark'}}%%"


def test_default_theme_no_init_line():
    out = sequence({"theme": "default", "participants": [{"id": "A"}], "messages": []})
    assert "init:" not in out


def test_canonical_participant_with_label_uses_alias():
    out = sequence({
        "participants": [{"id": "Client", "label": "Mobile App"}],
        "messages": [],
    })
    assert '    participant Client as "Mobile App"' in out


def test_canonical_participant_without_label():
    out = sequence({"participants": [{"id": "Client"}], "messages": []})
    assert "    participant Client" in out
    assert " as " not in out


def test_canonical_participant_label_equals_id_no_alias():
    out = sequence({
        "participants": [{"id": "Client", "label": "Client"}],
        "messages": [],
    })
    assert "    participant Client" in out
    assert " as " not in out


def test_a_null_label_is_treated_as_absent():
    out = sequence({"participants": [{"id": "Client", "label": None}], "messages": []})
    assert "    participant Client" in out
    assert " as " not in out


def test_older_bare_string_participants():
    out = sequence({"participants": ["User", "API"], "messages": []})
    assert "    participant User" in out
    assert "    participant API" in out


def test_canonical_style_solid_maps_to_arrow():
    out = sequence({
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "label": "req", "style": "solid"}],
    })
    assert "    A->>B: req" in out


def test_canonical_style_dotted_maps_to_arrow():
    out = sequence({
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "label": "resp", "style": "dotted"}],
    })
    assert "    A-->>B: resp" in out


def test_unknown_style_is_REFUSED():
    """REWRITTEN (see the module docstring's second note): the ported case asserted that
    ``wobbly`` became the solid arrow — which turns a response into a request."""
    with pytest.raises(LarkConfigError) as caught:
        sequence({
            "participants": [{"id": "A"}, {"id": "B"}],
            "messages": [{"from": "A", "to": "B", "label": "x", "style": "wobbly"}],
        })
    assert "wobbly" in str(caught.value)


def test_an_older_literal_arrow_is_kept():
    out = sequence({
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "message": "req", "type": "->"}],
    })
    assert "    A->B: req" in out


def test_an_invalid_literal_arrow_is_REFUSED():
    """REWRITTEN: ``==>`` used to become the solid arrow, silently."""
    with pytest.raises(LarkConfigError) as caught:
        sequence({
            "participants": [{"id": "A"}, {"id": "B"}],
            "messages": [{"from": "A", "to": "B", "message": "req", "type": "==>"}],
        })
    assert "==>" in str(caught.value)


def test_the_older_text_key_is_accepted():
    out = sequence({
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "message": "older text"}],
    })
    assert "older text" in out


def test_style_is_preferred_over_the_literal_arrow_when_both_are_present():
    out = sequence({
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [
            {"from": "A", "to": "B", "label": "x", "style": "dotted", "type": "->"}
        ],
    })
    assert "    A-->>B: x" in out


def test_message_text_is_escaped():
    out = sequence({
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "label": "POST (login)", "style": "solid"}],
    })
    assert '    A->>B: "POST (login)"' in out


def test_message_html_is_stripped():
    out = sequence({
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "label": "hi<script>", "style": "solid"}],
    })
    assert "<script>" not in out


def test_unknown_receiver_is_REFUSED(caplog):
    """REWRITTEN: the ported case asserted a WARNING and a dropped message. A library caller
    saw neither — no handler is attached outside the command line — and the exchange the spec
    exists to record was absent from a clean return value. The refusal replaces the log line,
    so the record list is asserted empty."""
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        with pytest.raises(LarkConfigError) as caught:
            sequence({
                "participants": [{"id": "A"}],
                "messages": [{"from": "A", "to": "GHOST", "label": "x", "style": "solid"}],
            })
    assert "GHOST" in str(caught.value)
    assert not caplog.records, [r.getMessage() for r in caplog.records]


def test_unknown_sender_is_REFUSED(caplog):
    """REWRITTEN for the same reason, on the other endpoint."""
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        with pytest.raises(LarkConfigError) as caught:
            sequence({
                "participants": [{"id": "A"}],
                "messages": [{"from": "PHANTOM", "to": "A", "label": "x", "style": "solid"}],
            })
    assert "PHANTOM" in str(caught.value)
    assert not caplog.records, [r.getMessage() for r in caplog.records]


def test_a_participant_with_no_id_is_REFUSED():
    """REWRITTEN: the ported case asserted the participant was skipped — and every message
    naming it then vanished too, with nothing logged for either."""
    with pytest.raises(LarkConfigError) as caught:
        sequence({"participants": [{"id": ""}, {"id": "A"}], "messages": []})
    assert "position 1" in str(caught.value)


# --------------------------------------------------------------------------- #
# The arrows are the sanctioned ones                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("style,arrow", sorted(MESSAGE_ARROWS.items()))
def test_each_mapped_style_emits_its_sanctioned_arrow(style, arrow):
    out = sequence({
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "label": "x", "style": style}],
    })
    assert f"    A{arrow}B: x" in out


@pytest.mark.parametrize("arrow", LEGACY_ARROWS)
def test_each_whitelisted_literal_arrow_survives(arrow):
    out = sequence({
        "participants": [{"id": "A"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "message": "x", "type": arrow}],
    })
    assert f"    A{arrow}B: x" in out


# --------------------------------------------------------------------------- #
# The theme whitelist — enforced in THIS compiler too                          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("theme", THEMES)
def test_every_whitelisted_theme_is_accepted(theme):
    out = sequence({"theme": theme, "participants": [{"id": "A"}], "messages": []})
    assert "sequenceDiagram" in out


def test_a_theme_outside_the_whitelist_is_REFUSED():
    with pytest.raises(LarkConfigError) as caught:
        sequence({"theme": "wobbly", "participants": [{"id": "A"}], "messages": []})
    assert "wobbly" in str(caught.value)


@pytest.mark.parametrize("absent", [None, ""])
def test_an_absent_theme_means_the_default_rather_than_a_refusal(absent):
    out = sequence({"theme": absent, "participants": [{"id": "A"}], "messages": []})
    assert "init:" not in out


def test_no_double_quote_appears_in_the_init_line():
    out = sequence({"theme": "forest", "participants": [{"id": "A"}], "messages": []})
    assert '"' not in out.splitlines()[0]


# --------------------------------------------------------------------------- #
# No blank line inside the block                                              #
# --------------------------------------------------------------------------- #

def test_no_blank_line_anywhere_in_the_output():
    out = sequence({
        "title": "Auth Flow",
        "theme": "dark",
        "participants": [{"id": "A", "label": "App"}, {"id": "B"}],
        "messages": [{"from": "A", "to": "B", "label": "x", "style": "solid"}],
    })
    assert not BLANK_LINE_RE.search(out), repr(out)


def test_no_blank_line_in_the_minimal_output():
    assert not BLANK_LINE_RE.search(sequence({}))


def test_the_declaration_is_a_sanctioned_one():
    out = sequence({"participants": [{"id": "A"}], "messages": []})
    assert "sequenceDiagram" in SANCTIONED_DECLARATIONS
    assert [line for line in out.splitlines() if line == "sequenceDiagram"]


# --------------------------------------------------------------------------- #
# The advisory complexity ceiling                                             #
# --------------------------------------------------------------------------- #

def _busy_spec(participants, messages):
    people = [{"id": f"P{i}"} for i in range(participants)]
    traffic = [
        {"from": f"P{i % participants}", "to": f"P{(i + 1) % participants}", "label": "x"}
        for i in range(messages)
    ]
    return {"participants": people, "messages": traffic}


def test_the_complexity_ceiling_is_silent_AT_the_boundary(caplog):
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        sequence(_busy_spec(5, COMPLEXITY_LIMIT - 5))
    assert "complexity" not in "\n".join(r.getMessage() for r in caplog.records)


def test_the_complexity_ceiling_warns_ONE_PAST_the_boundary(caplog):
    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        out = sequence(_busy_spec(5, COMPLEXITY_LIMIT - 4))
    messages = "\n".join(r.getMessage() for r in caplog.records)
    assert "complexity" in messages
    assert "sequenceDiagram" in out  # advisory: still compiled


# --------------------------------------------------------------------------- #
# Determinism                                                                 #
# --------------------------------------------------------------------------- #

def test_the_same_spec_compiles_byte_identically_twice():
    spec = {
        "title": "Repeatable",
        "theme": "base",
        "participants": [
            {"id": "Client", "label": "Mobile App"},
            {"id": "Gateway", "label": "API Gateway"},
            "Auth",
        ],
        "messages": [
            {"from": "Client", "to": "Gateway", "label": "1. POST /login", "style": "solid"},
            {"from": "Gateway", "to": "Auth", "label": "2. validate", "style": "solid"},
            {"from": "Auth", "to": "Client", "label": "3. token", "style": "dotted"},
        ],
    }
    assert sequence(spec) == sequence(spec)


def test_the_spec_is_not_mutated_by_compiling_it():
    spec = {"participants": ["A"], "messages": []}
    before = repr(spec)
    sequence(spec)
    assert repr(spec) == before
