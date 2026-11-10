"""The sequence-diagram compiler — a structured spec in, Lark-safe sequence source out."""
from ..errors import LarkConfigError
from .escape import escape_label
from .ruleset import (
    DEFAULT_THEME,
    MESSAGE_ARROWS,
    init_line,
    require_identifier,
    require_legacy_arrow,
    require_message_style,
    require_no_control_chars,
    require_theme,
    sanitize_id,
    warn_if_complex,
)


def sequence(spec: dict) -> str:
    """Compile ``spec`` to sequence-diagram source.

    Accepted keys, all optional except ``participants``::

        {
          "title": "Authentication",          # emitted as a comment, not a rendered title
          "theme": "default",                 # one of the five themes, or it is refused
          "participants": [
            {"id": "Client", "label": "Mobile App"}
          ],
          "messages": [
            {"from": "Client", "to": "Gateway", "label": "1. POST /login",
             "style": "solid"}
          ]
        }

    ``style`` is ``solid`` for a request and ``dotted`` for a response; those are the two
    arrows the renderer draws reliably. Groups have no equivalent here — a sequence diagram
    has no subgraphs — so structure comes from the participant order.

    Two older spec shapes are still accepted: a participant may be a bare string used as
    both id and label, and a message may name its arrow directly under ``type`` and its text
    under ``message``.

    Returns the diagram source with no trailing newline.

    **Off-dialect input is refused, never guessed.** An unknown theme, an unknown ``style``, an
    arrow outside the accepted literals, a participant whose id sanitizes to nothing, and a
    message naming a participant nothing declares each raise
    :class:`~larkdocio.errors.LarkConfigError` naming the construct and its value. A dropped
    message and a substituted arrow both produce a diagram that says something the spec did
    not, with nothing for the caller to inspect. **Every identifier is sanitized once** —
    trimmed, spaces closed up — and the sanitized form is what both the declaration and every
    message use, so a participant whose id carries a space cannot end up declared under one
    name and addressed under another. One rule stays **advisory** and warns rather than
    refuses: diagram size.
    """
    theme = require_theme(str(spec.get("theme") or DEFAULT_THEME))

    lines = []
    if theme != DEFAULT_THEME:
        lines.append(init_line({"theme": theme}))
    lines.append("sequenceDiagram")

    title = str(spec.get("title", "") or "")
    if title:
        # Composed into a `%%` COMMENT, which is line-oriented like every other statement —
        # see the twin comment in `flowchart`. One rule, applied at both sites.
        lines.append(f"    %% {require_no_control_chars(title, 'diagram title')}")

    declared = _emit_participants(lines, spec.get("participants", []))
    emitted = _emit_messages(lines, spec.get("messages", []), declared)

    warn_if_complex(len(declared), emitted)

    return "\n".join(lines)


def _emit_participants(lines, participants):
    """Append every participant declaration; return the set of sanitized ids."""
    declared = set()
    for position, participant in enumerate(participants, start=1):
        if isinstance(participant, dict):
            raw_id = participant.get("id", "")
            raw_label = participant.get("label", "")
            label = str(raw_label).strip() if raw_label is not None else ""
        else:
            # The older shape: one string is both the id and the label.
            raw_id = participant
            label = str(participant).strip()

        participant_id = require_identifier(raw_id, "participant", position)

        declared.add(participant_id)
        if label and label != participant_id:
            alias = escape_label(label, f"label of participant {participant_id!r}")
            lines.append(f"    participant {participant_id} as {alias}")
        else:
            lines.append(f"    participant {participant_id}")
    return declared


def _emit_messages(lines, messages, declared):
    """Append every message; return how many were emitted."""
    emitted = 0
    for message in messages:
        sender = _require_endpoint(message.get("from"), message, declared)
        receiver = _require_endpoint(message.get("to"), message, declared)

        lines.append(f"    {sender}{_arrow(message)}{receiver}: {_text(message)}")
        emitted += 1
    return emitted


def _arrow(message):
    """The arrow for one message — the style map first, then the older literal key."""
    if "style" in message:
        return MESSAGE_ARROWS[require_message_style(message.get("style"))]
    if "type" in message:
        return require_legacy_arrow(message.get("type"))
    return MESSAGE_ARROWS[require_message_style(None)]


def _text(message):
    """The escaped message text — the canonical key first, then the older one."""
    text = message.get("label")
    if text is None:
        text = message.get("message", "")
    return escape_label(
        str(text), f"text of the message {message.get('from')!r} -> {message.get('to')!r}"
    )


def _require_endpoint(raw, message, declared):
    """Return one message endpoint's identifier, refusing one no participant declares.

    The renderer invents a silent extra column for an undeclared participant, so the ported
    compiler dropped the message instead. That trade is the defect: the exchange the caller
    asked for is simply absent from the diagram, and no value says so.
    """
    endpoint = sanitize_id(raw)
    if endpoint not in declared:
        raise LarkConfigError(
            f"the message {message.get('from')!r} → {message.get('to')!r} names "
            f"{endpoint!r}, which no participant declares — the renderer would invent a "
            f"silent extra column for it; the participants this spec declares: "
            f"{', '.join(sorted(declared)) or 'none'}"
        )
    return endpoint
