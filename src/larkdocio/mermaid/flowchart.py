"""The flowchart compiler — a structured spec in, Lark-safe flowchart source out."""
from ..errors import LarkConfigError
from .escape import escape_label
from .ruleset import (
    DEFAULT_THEME,
    SHAPE_TEMPLATES,
    edge_arrow,
    init_line,
    require_direction,
    require_edge_style,
    require_identifier,
    require_length,
    require_no_control_chars,
    require_shape,
    require_theme,
    sanitize_id,
    warn_if_complex,
    warn_if_horizontal_and_wide,
)


def flowchart(spec: dict) -> str:
    """Compile ``spec`` to flowchart source.

    The spec carries the semantics — what the nodes are, how they connect, which of them
    belong together — and this function owns the syntax: identifier sanitizing, label
    escaping, shape and arrow spelling, and the rules the renderer needs to draw the result
    at all.

    Accepted keys, all optional except ``nodes``::

        {
          "title": "Onboarding",              # emitted as a comment, not a rendered title
          "direction": "TD",                  # or "LR"; anything else is refused
          "theme": "default",                 # one of the five themes, or it is refused
          "subgraphs": [
            {"id": "phase1", "label": "Phase one", "nodes": ["A", "B"]}
          ],
          "nodes": [
            {"id": "A", "label": "Start", "shape": "round"}
          ],
          "edges": [
            {"from": "A", "to": "B", "label": "yes", "style": "solid", "length": 1}
          ]
        }

    Layout advice worth following: group related steps into ``subgraphs`` rather than
    leaving every node loose — the layout engine untangles a bounded group far better than
    it untangles a flat graph. ``length`` and the ``invisible`` style are layout levers for
    a diagram that is already drawn and still crossing itself; reach for them second, not
    first.

    Returns the diagram source with no trailing newline.

    **Off-dialect input is refused, never guessed.** Every construct the renderer cannot draw
    raises :class:`~larkdocio.errors.LarkConfigError` naming the construct and its value: an
    unknown theme, direction, shape or edge style, a length outside the sanctioned range, a
    node or subgraph whose identifier sanitizes to nothing, an edge or subgraph member naming
    an identifier no node defines, and a label on an ``invisible`` edge (which draws nothing
    and so can carry no text). Nothing is dropped, substituted or clamped on the way through —
    a diagram that says something other than what the spec said is worse than no diagram,
    because nothing prompts a re-read. Identifiers are trimmed and their spaces closed up,
    symmetrically at every declaration and every reference. Two rules stay **advisory** and
    warn rather than refuse: diagram size, and a wide horizontal layout.
    """
    theme = require_theme(str(spec.get("theme") or DEFAULT_THEME))
    direction = require_direction(spec.get("direction"))

    config = {"flowchart": {"curve": "stepAfter"}}
    if theme != DEFAULT_THEME:
        config["theme"] = theme

    lines = [init_line(config), f"flowchart {direction}"]

    title = str(spec.get("title", "") or "")
    if title:
        # The title is composed into a `%%` COMMENT, and a comment is line-oriented too: a
        # newline here ends the comment and the remainder becomes a statement the renderer
        # obeys. It never passed through `escape_label`, so it needs the rule directly — the
        # same rule, not a second one.
        lines.append(f"    %% {require_no_control_chars(title, 'diagram title')}")

    definitions = _node_definitions(spec.get("nodes", []))
    grouped = _emit_subgraphs(lines, spec.get("subgraphs", []), definitions)

    for node_id, definition in definitions.items():
        if node_id not in grouped:
            lines.append(f"    {definition}")

    edges = _emit_edges(lines, spec.get("edges", []), definitions)

    warn_if_complex(len(definitions), edges)
    warn_if_horizontal_and_wide(direction, len(definitions))

    return "\n".join(lines)


def _node_definitions(nodes):
    """``{sanitized id: definition line}`` in the order the spec declares them."""
    definitions = {}
    for position, node in enumerate(nodes, start=1):
        node_id = require_identifier(node.get("id"), "node", position)
        label = escape_label(str(node.get("label", node_id)), f"label of node {node_id!r}")
        shape = require_shape(node.get("shape"))
        definitions[node_id] = SHAPE_TEMPLATES[shape].format(node_id=node_id, label=label)
    return definitions


def _emit_subgraphs(lines, subgraphs, definitions):
    """Append every subgraph block; return the set of ids a subgraph claimed."""
    grouped = set()
    for position, subgraph in enumerate(subgraphs, start=1):
        group_id = require_identifier(subgraph.get("id"), "subgraph", position)
        group_label = escape_label(str(subgraph.get("label", group_id)),
                                   f"label of subgraph {group_id!r}")
        lines.append(f"    subgraph {group_id}[{group_label}]")
        for member in subgraph.get("nodes", []):
            member_id = sanitize_id(member)
            if member_id not in definitions:
                raise LarkConfigError(
                    f"subgraph {group_id!r} names the member {member!r}, which no node "
                    f"defines — a subgraph can only group nodes the spec defines; "
                    f"{_defined(definitions)}"
                )
            lines.append(f"        {definitions[member_id]}")
            grouped.add(member_id)
        lines.append("    end")
    return grouped


def _emit_edges(lines, edges, definitions):
    """Append every edge; return how many were emitted."""
    emitted = 0
    for edge in edges:
        source = _require_endpoint(edge.get("from"), edge, definitions)
        target = _require_endpoint(edge.get("to"), edge, definitions)

        label = edge.get("label", "")
        style = require_edge_style(edge.get("style"))
        arrow = edge_arrow(style, require_length(edge.get("length")))
        if style == "invisible" and str(label or ""):
            raise LarkConfigError(
                f"the edge {edge.get('from')!r} → {edge.get('to')!r} is invisible and "
                f"carries the label {label!r}: an invisible link is a layout hint the "
                f"renderer draws nothing for, so it cannot carry a label — drop the label, "
                f"or give the edge a style that is drawn"
            )

        if label:
            escaped = escape_label(
                str(label), f"label of the edge {edge.get('from')!r} -> {edge.get('to')!r}"
            )
            lines.append(f"    {source} {arrow}|{escaped}| {target}")
        else:
            lines.append(f"    {source} {arrow} {target}")
        emitted += 1
    return emitted


def _require_endpoint(raw, edge, definitions):
    """Return one edge endpoint's identifier, refusing one no node defines.

    The renderer draws **nothing at all** for an edge to a node that does not exist, so the
    ported compiler dropped such an edge to keep the rest of the diagram drawable. That trade
    is the defect: the caller asked for a connection, got a diagram without it, and had no
    value to inspect. Refusing is the only signal a library caller can act on.
    """
    endpoint = sanitize_id(raw)
    if endpoint not in definitions:
        raise LarkConfigError(
            f"the edge {edge.get('from')!r} → {edge.get('to')!r} names {endpoint!r}, which "
            f"no node defines — the renderer draws nothing at all for an edge to a node that "
            f"does not exist; {_defined(definitions)}"
        )
    return endpoint


def _defined(definitions):
    """The nodes a spec defines, for a refusal that has to say what WAS available."""
    return f"the nodes this spec defines: {', '.join(definitions) or 'none'}"
