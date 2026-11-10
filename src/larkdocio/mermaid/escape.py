"""The shared label sanitizer — the one implementation of the quoting rule.

Lark's Mermaid renderer is intolerant of unquoted punctuation inside a label and of raw
HTML anywhere in one. :func:`escape_label` is therefore applied by **both** compilers to
every human-readable string they emit — node labels, subgraph labels, edge labels,
participant aliases and message text — so the escaping cannot differ between diagram
kinds.

The rule, in order:

0. **refuse** a label carrying any character from ``ruleset.LABEL_CONTROL_CHARS`` — a line
   break ends the statement the label sits in, and no amount of quoting puts it back
   together (the fork and why it is a refusal rather than a rewrite: that constant);
1. strip HTML tags (the pattern is published as ``ruleset.HTML_TAG_RE``);
2. downgrade a literal double quote to a single quote, so the wrap below cannot be
   terminated early by the label's own content;
3. wrap the whole label in double quotes when it carries any character from
   ``ruleset.LABEL_BAD_CHARS`` or a space.

A label with none of those is emitted bare, which keeps simple diagrams readable.
"""
from .ruleset import HTML_TAG_RE, LABEL_BAD_CHARS, require_no_control_chars


def escape_label(label: str, what: str = "label") -> str:
    """Return ``label`` safe to place inside a Mermaid shape, alias or message.

    A label carrying a control character is **refused** —
    :class:`~larkdocio.errors.LarkConfigError`, naming the codepoint — because that is the one
    class the two rewrites below cannot make safe: the emitted syntax is line-oriented, so a
    newline inside a label splits one statement into two and the renderer draws a diagram that
    is not the one the spec described. ``what`` names the construct for that message and
    changes nothing else.

    Otherwise: HTML tags are removed, an embedded double quote becomes a single quote, and the
    result is wrapped in double quotes when it carries a space or any character the
    renderer treats as syntax. Returns the label unchanged when none of that applies.
    """
    clean = HTML_TAG_RE.sub("", require_no_control_chars(label, what))

    if any(char in clean for char in LABEL_BAD_CHARS) or " " in clean:
        clean = clean.replace('"', "'")
        return f'"{clean}"'

    return clean
