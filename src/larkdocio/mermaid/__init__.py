"""``larkdocio.mermaid`` — compile a structured diagram spec to Lark-safe Mermaid text.

Two compilers and one sanitizer, all **pure**: a ``dict`` goes in, Mermaid source comes out.
Nothing here opens a network connection, reads a file, or touches a document — the output is
text, and where it goes is the caller's business.

    from larkdocio.mermaid import flowchart, rules, sequence

    source = flowchart({
        "direction": "TD",
        "nodes": [{"id": "A", "label": "Start"}, {"id": "B", "label": "Done"}],
        "edges": [{"from": "A", "to": "B"}],
    })

Why compile rather than write the source by hand: Lark's renderer accepts a narrow dialect
and **validates nothing** on the way in, so a diagram it cannot draw is stored exactly as
sent and then quietly fails to appear. The compilers are therefore the only place a guarantee
can live. Every constraint they enforce is a constant in
:mod:`larkdocio.mermaid.ruleset` and a section of the shipped rule document, which
:func:`rules` returns.

**Provenance, stated because it bounds what this module claims.** The dialect rules were
ported from an older standalone generator whose own documentation had gone stale, so that
documentation was treated as a set of claims to **re-validate** rather than as evidence:
every rule here is pinned by this package's own tests against the behavior of this package's
own compilers, and each is marked either enforced or advisory in the document. What offline
tests cannot establish is how a particular diagram *draws* once it reaches a real document —
that is confirmed by rendering one, which is outside this module.
"""
from .escape import escape_label
from .flowchart import flowchart
from .rules_doc import MERMAID_RULES
from .ruleset import (
    ADVISORY,
    BLANK_LINE_ALLOWED,
    COMMENT_PREFIX,
    COMPLEXITY_LIMIT,
    DEFAULT_DIRECTION,
    DEFAULT_THEME,
    DIRECTION_SYNONYMS,
    DIRECTIONS,
    EDGE_LENGTH_RANGE,
    EDGE_STYLES,
    ENFORCED,
    EXPLICIT_PARTICIPANTS_REQUIRED,
    HTML_TAG_RE,
    INIT_QUOTE,
    LABEL_BAD_CHARS,
    LABEL_CONTROL_CHARS,
    LABEL_LINE_BREAKS,
    LEGACY_ARROWS,
    MESSAGE_ARROWS,
    RULES,
    SANCTIONED_DECLARATIONS,
    SHAPE_ALIASES,
    SHAPE_TEMPLATES,
    SUPPORTED_DIAGRAM_TYPES,
    THEMES,
    UNSTABLE_DIAGRAM_TYPES,
    VERTICAL_PREFERRED_ABOVE,
    complexity_score,
)
from .sequence import sequence


def rules() -> str:
    """Return the shipped **Mermaid rule document** as text.

    The dialect Lark's renderer accepts, rule by rule, with each rule marked **enforced**
    (the compilers refuse or rewrite input that breaks it) or **advisory** (they warn and
    compile anyway), and with the constant that carries it named. Read it before writing
    Mermaid source by hand; :func:`flowchart` and :func:`sequence` already obey all of it.

    Shipped inside the package, so it reads identically from a source tree and from an
    installed wheel — a document a caller cannot open answers nobody.
    """
    return MERMAID_RULES


__all__ = [
    # the compilers + the shared sanitizer
    "flowchart",
    "sequence",
    "escape_label",
    # the shipped rule document + its accessor
    "rules",
    "MERMAID_RULES",
    # the rule registry
    "RULES",
    "ENFORCED",
    "ADVISORY",
    # the rule constants
    "SUPPORTED_DIAGRAM_TYPES",
    "SANCTIONED_DECLARATIONS",
    "UNSTABLE_DIAGRAM_TYPES",
    "DIRECTIONS",
    "DIRECTION_SYNONYMS",
    "DEFAULT_DIRECTION",
    "SHAPE_ALIASES",
    "SHAPE_TEMPLATES",
    "LABEL_BAD_CHARS",
    "LABEL_CONTROL_CHARS",
    "LABEL_LINE_BREAKS",
    "HTML_TAG_RE",
    "EDGE_STYLES",
    "EDGE_LENGTH_RANGE",
    "EXPLICIT_PARTICIPANTS_REQUIRED",
    "MESSAGE_ARROWS",
    "LEGACY_ARROWS",
    "THEMES",
    "DEFAULT_THEME",
    "COMMENT_PREFIX",
    "BLANK_LINE_ALLOWED",
    "INIT_QUOTE",
    "VERTICAL_PREFERRED_ABOVE",
    "COMPLEXITY_LIMIT",
    "complexity_score",
]
