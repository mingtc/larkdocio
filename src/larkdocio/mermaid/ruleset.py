"""The rule set as DATA — every constraint the compilers obey, in code.

A rule that is only prose is a rumor. Every constraint here is a constant the compilers
read at run time, and the shipped rule document names each one, so the document and the
behavior cannot drift apart: one guard parses the document, compares it against
:data:`RULES` in both directions, and checks the compilers' real output against the
constants themselves.

Each rule carries a **posture**:

* :data:`ENFORCED` — the compilers refuse the input or rewrite it to comply. Breaking the
  rule is not expressible in their output.
* :data:`ADVISORY` — the compilers warn on the shared ``larkdocio`` logger and compile the
  diagram anyway. These are layout judgments, not correctness ones.
"""
import logging
import re
from collections import namedtuple

from ..errors import LarkConfigError

logger = logging.getLogger("larkdocio")


# --------------------------------------------------------------------------- #
# 1. Labels                                                                    #
# --------------------------------------------------------------------------- #

#: HTML is removed from every label before anything else — the renderer does not survive
#: raw markup inside a shape.
HTML_TAG_RE = re.compile(r"<[^>]+>")

#: The characters that force a label to be wrapped in double quotes. A space forces the
#: wrap too, and is kept separate because it is not punctuation.
LABEL_BAD_CHARS = ("(", ")", "[", "]", "{", "}", ",", '"', "'")

#: The characters that END A STATEMENT in the source both compilers write. Mermaid's syntax
#: is **line-oriented** — one node declaration, one edge, one message per line — so a label
#: carrying any of these does not produce a label with a line break in it: it closes the
#: statement early and hands the remainder of the label to the parser as diagram syntax.
#: ``{"nodes": [{"id": "A", "label": "Start\nflowchart LR"}]}`` emitted ``A[Start`` and then a
#: second, attacker-or-typo-chosen statement. Quoting does not help: the wrap in
#: :func:`~larkdocio.mermaid.escape.escape_label` is applied to a string that has already been
#: cut in two by the time the renderer reads it.
LABEL_LINE_BREAKS = ("\n", "\r", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85",
                     "\u2028", "\u2029")

#: Every character a label may not carry AT ALL — :data:`LABEL_LINE_BREAKS` plus the rest of
#: the C0 controls and ``DEL``. **Refused, not rewritten**, which is the opposite of how the
#: two other label rules behave, and the decision is recorded here because it was a real fork:
#:
#: 1. **Translating a line break to ``<br/>`` was rejected on the evidence already in this
#:    dialect.** The shipped rule document's *No HTML in labels* section states the measured
#:    conclusion — *"Line breaks are the common reason to reach for markup. There is no safe
#:    substitute in this dialect"* — and no measurement here overturns it (this compiler runs
#:    offline; nothing in this change put a ``<br/>`` in front of Lark's renderer). Under this
#:    project's supersession rule a recorded conclusion is not reversed by preference.
#: 2. **It would make one function answer the same request two opposite ways.**
#:    :func:`~larkdocio.mermaid.escape.escape_label` STRIPS a ``<br/>`` a caller writes
#:    themselves. A translation would insert the very token the next rule deletes, so
#:    ``"a<br/>b"`` and ``"a\nb"`` — the same request, spelled twice — would come out as ``ab``
#:    and ``a<br/>b``.
#: 3. **Refusing is what the compilers already do to everything that would silently change the
#:    diagram** (an unknown shape, an undefined edge endpoint, a label on an invisible edge).
#:    The caller wrote the label and can fix it; the alternative is a diagram that lost a title
#:    with nothing prompting a re-read.
#:
#: The other controls ride the same rule because none of them is renderable either, and a rule
#: with one member per codepoint would be a rule nobody could state.
LABEL_CONTROL_CHARS = tuple(
    sorted(set(chr(code) for code in range(0x00, 0x20)) | {"\x7f"} | set(LABEL_LINE_BREAKS))
)


# --------------------------------------------------------------------------- #
# 2. Diagram declarations                                                      #
# --------------------------------------------------------------------------- #

#: The diagram kinds the renderer draws. Two of them have compilers in this package
#: (``flowchart`` and ``sequenceDiagram``); the rest are listed because hand-written
#: source may use them.
SUPPORTED_DIAGRAM_TYPES = (
    "graph",
    "flowchart",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "mindmap",
    "gantt",
)

#: The exact opening lines a diagram may start with. Every declaration a compiler in this
#: package emits is one of these, which is what makes the list above a guard rather than a
#: claim.
SANCTIONED_DECLARATIONS = (
    "graph TD",
    "graph LR",
    "flowchart TD",
    "flowchart LR",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "mindmap",
    "gantt",
)

#: Diagram kinds to avoid: the renderer treats them as experimental and they draw
#: unreliably. Convert one of these to a flowchart instead.
UNSTABLE_DIAGRAM_TYPES = ("pie", "gitGraph", "journey", "quadrantChart")

#: The two flow directions the sanctioned declarations spell.
DIRECTIONS = ("TD", "LR")

#: Directions Mermaid accepts as synonyms of a sanctioned one, normalized on the way out so
#: the emitted declaration is always sanctioned. ``TB`` (top-bottom) and ``TD`` (top-down)
#: are the same layout.
DIRECTION_SYNONYMS = {"TB": "TD"}

#: Any direction that is neither sanctioned nor a synonym falls back to this one — the
#: vertical layout, because a horizontal diagram is scaled down to fit the page width.
DEFAULT_DIRECTION = "TD"


# --------------------------------------------------------------------------- #
# 3. Shapes                                                                    #
# --------------------------------------------------------------------------- #

#: Accepted ``shape`` values, each mapped to the canonical shape it selects. A value outside
#: this map is refused rather than drawn as something else.
SHAPE_ALIASES = {
    "rect": "rect",
    "round": "round",
    "rounded": "round",
    "diamond": "diamond",
    "decision": "diamond",
    "condition": "diamond",
    "cylinder": "cylinder",
    "database": "cylinder",
}

#: How each canonical shape is written. ``round`` is Mermaid's circle form — the name is
#: the one the dialect has always used, and it is kept so existing specs keep working.
SHAPE_TEMPLATES = {
    "rect": "{node_id}[{label}]",
    "round": "{node_id}(({label}))",
    "diamond": "{node_id}{{{label}}}",
    "cylinder": "{node_id}[({label})]",
}

#: The shape a node that names none is asking for. A *named* shape outside
#: :data:`SHAPE_ALIASES` is refused — this default applies only to the absence of the key.
DEFAULT_SHAPE = "rect"


# --------------------------------------------------------------------------- #
# 4. Edges                                                                     #
# --------------------------------------------------------------------------- #

#: Accepted edge styles. ``invisible`` draws no arrow — it only forces the layout engine to
#: place two nodes in sequence — and so carries no label.
EDGE_STYLES = ("solid", "dotted", "thick", "invisible")

#: The style an edge that names none is asking for. A *named* style outside
#: :data:`EDGE_STYLES` is refused — this default applies only to the absence of the key.
DEFAULT_EDGE_STYLE = "solid"

#: ``(minimum, maximum)`` for an edge's ``length``. A length outside the range, or one that is
#: not a whole number, is refused; an edge that names none gets the minimum.
EDGE_LENGTH_RANGE = (1, 5)


# --------------------------------------------------------------------------- #
# 5. Sequence diagrams                                                         #
# --------------------------------------------------------------------------- #

#: Every participant must be declared before it is used; a message naming an undeclared
#: participant is refused rather than emitted or dropped.
EXPLICIT_PARTICIPANTS_REQUIRED = True

#: The two sanctioned message arrows, by style. Nothing else is emitted for a ``style``, and a
#: ``style`` outside this map is refused.
MESSAGE_ARROWS = {"solid": "->>", "dotted": "-->>"}

#: The style a message that names none is asking for. A *named* style outside
#: :data:`MESSAGE_ARROWS` is refused — this default applies only to the absence of the key.
DEFAULT_MESSAGE_STYLE = "solid"

#: Literal arrows accepted from an older spec shape that named the arrow directly. Anything
#: outside this whitelist is refused.
LEGACY_ARROWS = ("->>", "-->>", "->", "-->")


# --------------------------------------------------------------------------- #
# 6. Cleanliness                                                               #
# --------------------------------------------------------------------------- #

#: The only comment marker the renderer understands.
COMMENT_PREFIX = "%%"

#: Whether a blank line may appear inside a diagram block. It may not: the compilers emit
#: none, so a spacer cannot reach the renderer's parser.
BLANK_LINE_ALLOWED = False

#: The quote character the ``init`` configuration line is written with — one dialect for
#: both compilers, because they share the emitter below.
INIT_QUOTE = "'"

#: The five themes the renderer draws. Anything else is refused rather than passed through,
#: because a theme it does not know is silently stored and then ignored.
THEMES = ("default", "dark", "neutral", "forest", "base")

#: The theme assumed when a spec names none. It is never written into the ``init`` line.
DEFAULT_THEME = "default"


# --------------------------------------------------------------------------- #
# 7. Sizing (advisory)                                                         #
# --------------------------------------------------------------------------- #

#: Above this many nodes the horizontal direction is scaled down until the text is
#: unreadable, so the vertical one is preferred. Advisory: a warning, never a refusal.
VERTICAL_PREFERRED_ABOVE = 5

#: Nodes plus connections. Past this, split the diagram into several. Advisory.
COMPLEXITY_LIMIT = 30


# --------------------------------------------------------------------------- #
# 8. The rule registry                                                         #
# --------------------------------------------------------------------------- #

#: A rule the compilers make unbreakable.
ENFORCED = "enforced"

#: A rule the compilers warn about and then honor the caller's choice.
ADVISORY = "advisory"

Rule = namedtuple("Rule", "key title posture constants")

#: Every rule, its posture, and the constants that carry it. The shipped rule document has
#: one section per row, named by ``title``, and the drift guard holds the two equal in both
#: directions — so a rule cannot be documented without a constant, and a constant cannot
#: exist without a rule that says whether it is enforced.
RULES = (
    Rule(
        "declarations",
        "Supported diagram declarations",
        ENFORCED,
        (
            "SUPPORTED_DIAGRAM_TYPES",
            "SANCTIONED_DECLARATIONS",
            "UNSTABLE_DIAGRAM_TYPES",
            "DIRECTIONS",
            "DIRECTION_SYNONYMS",
            "DEFAULT_DIRECTION",
        ),
    ),
    Rule("no-html", "No HTML in labels", ENFORCED, ("HTML_TAG_RE",)),
    Rule(
        "no-control-chars",
        "No control characters in label text",
        ENFORCED,
        ("LABEL_CONTROL_CHARS", "LABEL_LINE_BREAKS"),
    ),
    Rule(
        "shapes",
        "Sanctioned node shapes",
        ENFORCED,
        ("SHAPE_ALIASES", "SHAPE_TEMPLATES", "DEFAULT_SHAPE"),
    ),
    Rule("quoting", "Quoting labels that carry syntax", ENFORCED, ("LABEL_BAD_CHARS",)),
    Rule(
        "edges",
        "Edge styles and lengths",
        ENFORCED,
        ("EDGE_STYLES", "DEFAULT_EDGE_STYLE", "EDGE_LENGTH_RANGE"),
    ),
    Rule(
        "participants",
        "Explicit participants",
        ENFORCED,
        ("EXPLICIT_PARTICIPANTS_REQUIRED",),
    ),
    Rule(
        "arrows",
        "Sanctioned message arrows",
        ENFORCED,
        ("MESSAGE_ARROWS", "DEFAULT_MESSAGE_STYLE", "LEGACY_ARROWS"),
    ),
    Rule("themes", "The theme whitelist", ENFORCED, ("THEMES", "DEFAULT_THEME")),
    Rule("comments", "Comments", ENFORCED, ("COMMENT_PREFIX",)),
    Rule("blank-lines", "No blank line inside the block", ENFORCED, ("BLANK_LINE_ALLOWED",)),
    Rule("init-line", "One init-line dialect", ENFORCED, ("INIT_QUOTE",)),
    Rule(
        "vertical",
        "Prefer the vertical direction",
        ADVISORY,
        ("VERTICAL_PREFERRED_ABOVE",),
    ),
    Rule("complexity", "The complexity ceiling", ADVISORY, ("COMPLEXITY_LIMIT",)),
)


# --------------------------------------------------------------------------- #
# 9. The shared enforcement helpers                                            #
# --------------------------------------------------------------------------- #

def require_theme(theme):
    """Return ``theme`` when the renderer knows it, else raise.

    An unknown theme is stored verbatim by the document and then quietly ignored at draw
    time, so a caller who misspells one gets a diagram in the wrong colors and no error.
    Refusing here is the only place that can be noticed.
    """
    if theme not in THEMES:
        raise LarkConfigError(
            f"unsupported diagram theme {theme!r} — the renderer draws exactly "
            f"{len(THEMES)}: {', '.join(THEMES)}"
        )
    return theme


def require_direction(direction):
    """Return a sanctioned flow direction, refusing one the renderer cannot draw.

    A spec that names **no** direction is asking for :data:`DEFAULT_DIRECTION`; a spec that
    names one the sanctioned declarations do not carry is refused, because substituting the
    vertical layout for it silently redraws the diagram along the other axis.
    """
    asked = str(direction or "").strip().upper()
    if not asked:
        return DEFAULT_DIRECTION
    resolved = DIRECTION_SYNONYMS.get(asked, asked)
    if resolved not in DIRECTIONS:
        raise LarkConfigError(
            f"unsupported flow direction {direction!r} — the renderer draws "
            f"{', '.join(DIRECTIONS)} (and accepts {', '.join(DIRECTION_SYNONYMS)} as a "
            f"synonym for {DEFAULT_DIRECTION}); a spec that names no direction gets "
            f"{DEFAULT_DIRECTION}"
        )
    return resolved


def require_shape(shape):
    """Return the canonical shape for ``shape``, refusing a spelling the dialect lacks.

    An unknown shape used to be drawn as a rectangle, which is how a decision point stopped
    looking like a decision with nothing to read anywhere.
    """
    if shape is None or not str(shape).strip():
        return DEFAULT_SHAPE
    asked = str(shape).strip().lower()
    if asked not in SHAPE_ALIASES:
        raise LarkConfigError(
            f"unsupported node shape {shape!r} — the renderer draws exactly "
            f"{len(SHAPE_TEMPLATES)}, spelled: {', '.join(SHAPE_ALIASES)}"
        )
    return SHAPE_ALIASES[asked]


def require_no_control_chars(text, what):
    """Return ``text`` when it carries no :data:`LABEL_CONTROL_CHARS`, else raise.

    ``what`` names the construct the text belongs to — *node label*, *edge label*, *diagram
    title* — because the refusal has to be actionable from a spec that may hold dozens of
    strings, and a control character is invisible in the caller's own editor.

    Applied to the caller's text **before** the HTML strip and before the quoting wrap, so the
    subject of the refusal is what the caller wrote rather than what the earlier rules left of
    it. That order also closes the smuggling case: ``HTML_TAG_RE`` is ``<[^>]+>`` and ``[^>]``
    matches a newline, so ``"<a\\nb>"`` would otherwise be stripped to nothing and the label
    would silently lose its whole content instead of being refused.

    The reason this refuses rather than translating is recorded once, on
    :data:`LABEL_CONTROL_CHARS`.
    """
    for char in text:
        if char in LABEL_CONTROL_CHARS:
            breaks = char in LABEL_LINE_BREAKS
            consequence = (
                "the compilers write one statement per LINE, so it would end the statement "
                "early and the rest of the text would be parsed as diagram syntax"
                if breaks else
                "the renderer has no rendering for a control character, and quoting does not "
                "make one"
            )
            raise LarkConfigError(
                f"the {what} {text!r} carries U+{ord(char):04X}, which this dialect cannot "
                f"carry: {consequence}. Nothing is substituted for it — a `<br/>` would be "
                f"removed again by the no-HTML rule — so shorten the text, or split the "
                f"construct in two"
            )
    return text


def require_identifier(raw, what, position):
    """Return the sanitized identifier of ``raw``, refusing one that sanitizes to nothing.

    ``what`` names the construct (a node, a participant, a subgraph) and ``position`` its
    1-based place in the spec, because a construct with no identifier has nothing to quote.
    Dropping it used to remove every edge or message that named it as well.
    """
    identifier = sanitize_id(raw)
    if not identifier:
        raise LarkConfigError(
            f"the {what} at position {position} has no usable identifier — {raw!r} sanitizes "
            f"to nothing, and the identifier is what every reference to it is written with"
        )
    return identifier


def require_length(raw):
    """Return ``raw`` as an edge length, refusing one outside :data:`EDGE_LENGTH_RANGE`.

    An edge that names no length gets the range's minimum. Anything else is taken literally:
    clamping a longer one into range, or reading a non-numeric one as the minimum, quietly
    produced a different layout from the one that was asked for.
    """
    low, high = EDGE_LENGTH_RANGE
    if raw is None:
        return low
    try:
        length = int(str(raw).strip())
    except (TypeError, ValueError):
        raise LarkConfigError(
            f"edge length {raw!r} is not a whole number — the renderer draws lengths "
            f"{low} to {high}"
        ) from None
    if not low <= length <= high:
        raise LarkConfigError(
            f"edge length {raw!r} is outside the range the renderer draws: {low} to {high}"
        )
    return length


def require_edge_style(style):
    """Return the edge style ``style`` names, refusing one outside :data:`EDGE_STYLES`."""
    if style is None or not str(style).strip():
        return DEFAULT_EDGE_STYLE
    asked = str(style).strip().lower()
    if asked not in EDGE_STYLES:
        raise LarkConfigError(
            f"unsupported edge style {style!r} — the renderer draws exactly "
            f"{len(EDGE_STYLES)}: {', '.join(EDGE_STYLES)}"
        )
    return asked


def require_message_style(style):
    """Return the message style ``style`` names, refusing one outside :data:`MESSAGE_ARROWS`."""
    if style is None or not str(style).strip():
        return DEFAULT_MESSAGE_STYLE
    asked = str(style).strip().lower()
    if asked not in MESSAGE_ARROWS:
        raise LarkConfigError(
            f"unsupported message style {style!r} — the renderer draws exactly "
            f"{len(MESSAGE_ARROWS)}: {', '.join(MESSAGE_ARROWS)}"
        )
    return asked


def require_legacy_arrow(literal):
    """Return ``literal`` when it is an arrow the renderer draws, else refuse.

    The older spec shape names the arrow directly instead of naming a style. One outside the
    whitelist used to become the solid arrow, which turns a response into a request.
    """
    if literal in LEGACY_ARROWS:
        return literal
    raise LarkConfigError(
        f"unsupported message arrow {literal!r} — an arrow named directly must be one of: "
        f"{', '.join(LEGACY_ARROWS)}"
    )


def init_line(config):
    """Render an ``init`` configuration line — the ONE dialect both compilers use.

    ``config`` is a mapping whose values are scalars or nested mappings; insertion order is
    preserved, so the same configuration always renders the same bytes.
    """
    return "%%{init: " + _render_mapping(config) + "}%%"


def _render_mapping(mapping):
    body = ", ".join(
        f"{INIT_QUOTE}{key}{INIT_QUOTE}: {_render_value(value)}"
        for key, value in mapping.items()
    )
    return "{" + body + "}"


def _render_value(value):
    if isinstance(value, dict):
        return _render_mapping(value)
    return f"{INIT_QUOTE}{value}{INIT_QUOTE}"


def sanitize_id(raw):
    """Return the identifier form of ``raw`` — trimmed, with spaces closed up.

    Applied to every identifier at BOTH the place it is declared and every place it is
    referenced, so a declaration and its references can never disagree.
    """
    return str(raw or "").strip().replace(" ", "_")


def edge_arrow(style, length):
    """Return the arrow for an edge ``style`` at ``length`` — the ported arithmetic.

    Longer arrows push the target further down the layout, which is how crossing edges are
    given room. ``style`` has already passed :func:`require_edge_style`, so every branch here
    is a style the renderer draws and there is nothing to fall back to.
    """
    if style == "dotted":
        return "-." + ("." * (length - 1)) + "->"
    if style == "thick":
        return "=" * (length + 1) + ">"
    if style == "invisible":
        return "~" * (length + 2)
    return "-" * (length + 1) + ">"


def complexity_score(nodes, connections):
    """Return a diagram's complexity — its node count plus its connection count."""
    return nodes + connections


def warn_if_complex(nodes, connections):
    """Warn when a diagram is past the advisory complexity ceiling. Never refuses."""
    score = complexity_score(nodes, connections)
    if score > COMPLEXITY_LIMIT:
        logger.warning(
            "diagram complexity %s is past the advisory ceiling of %s "
            "(nodes plus connections); consider splitting it into several diagrams",
            score,
            COMPLEXITY_LIMIT,
        )


def warn_if_horizontal_and_wide(direction, nodes):
    """Warn when a horizontal diagram has enough nodes to be scaled unreadable."""
    if direction == "LR" and nodes > VERTICAL_PREFERRED_ABOVE:
        logger.warning(
            "direction LR with %s nodes is scaled down to fit the page width; "
            "the vertical direction is preferred past %s nodes",
            nodes,
            VERTICAL_PREFERRED_ABOVE,
        )
