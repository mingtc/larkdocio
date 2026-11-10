from typing import Any, List, TYPE_CHECKING
from larkdocio.blocks import register_block
from larkdocio.model import (
    CodeNode,
    EquationBlockNode,
    Inline,
    InlineEquation,
    MentionDoc,
    MentionUser,
    Node,
    StyledText,
    Text,
    TextNode,
    UnsupportedInline,
)
from larkdocio.common import unescape_url

#: The docx code-language enum → MD fence token map. Its single definition moved to
#: :mod:`larkdocio.langs` in LD-134 so the **writer** could derive the reverse direction
#: from the same literal instead of duplicating ~65 rows (a drift bomb). Re-exported here
#: so this module's long-standing import path is unchanged.
from larkdocio.langs import DOCX_CODE_LANG_TO_MD

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser

def _text_run_node(parser: "Parser", tr: Any) -> Inline:
    """Build the typed inline node for one ``text_run`` TextElement member.

    A run with no style maps to a literal :class:`Text` (escapable); a styled or
    linked run maps to :class:`StyledText` carrying the style booleans, the
    already-URL-unescaped link, and the fg/bg color-enum ints. The renderer (the
    ONE serializer) composes the Markdown/HTML wrappers per its ``use_html_tags``
    policy — this is why the composition no longer lives here.

    The colors (``text_color`` / ``background_color``) are captured into the
    model but the renderer ignores them (LD-042, consumed-into-model /
    dropped-at-render): Markdown has no portable color form, so the projection
    stays byte-identical, but the model is now lossless for a future writer.
    Absent on the SDK run ⇒ ``None`` (pass the raw attr through unchanged — a
    valid enum int is never falsy-coerced away).

    ``comment_ids`` — the WORD-level review-anchor list, also on
    ``text_element_style`` — is captured the same way and on the same terms
    (LD-158): the renderer ignores it, so the projection does not move, while the
    model can say which passage a reviewer anchored to. The raw attribute is passed
    through unchanged, so an absent field stays ``None`` while a present-but-empty
    list stays ``[]`` (two different facts), in the API's own order, with no sorting
    and no de-duplication.

    The node-selection edge, characterized against the pinned SDK rather than
    assumed: the SDK deserializes ANY present ``text_element_style`` — even ``{}`` —
    into a real ``TextElementStyle`` object, and a plain object is truthy, so a run
    whose style carries ONLY ``comment_ids`` fails the ``if not style`` guard and
    reaches ``StyledText`` with every flag falsy. A word-level anchor on
    otherwise-unremarkable text therefore lands on the model with no change to which
    node class a run maps to, and ``Text`` needs no list of its own (a run with no
    style object has none of these ids to begin with — the field lives on the style).
    """
    content = getattr(tr, "content", "") or ""
    style = getattr(tr, "text_element_style", None)
    if not style:
        return Text(content)
    link = getattr(style, "link", None)
    link_url = unescape_url(getattr(link, "url", "")) if link else None
    return StyledText(
        content=content,
        bold=bool(style.bold),
        italic=bool(style.italic),
        strikethrough=bool(style.strikethrough),
        underline=bool(style.underline),
        inline_code=bool(style.inline_code),
        link_url=link_url,
        text_color=getattr(style, "text_color", None),
        background_color=getattr(style, "background_color", None),
        comment_ids=getattr(style, "comment_ids", None),
    )


def _element_inlines(parser: "Parser", e: Any) -> List[Inline]:
    """Build the typed inline node(s) for one ``TextElement``.

    ``TextElement`` is a union, but the SDK may populate several members; each
    populated member contributes a node in the same fixed order the legacy
    string formatter emitted — text_run, mention_user, mention_doc, equation,
    then the unsupported-variant markers (reminder/file/inline_block/
    link_preview/undefined) — so the rendered string is byte-identical.

    Inline equation elements in normal text flow are always ``$...$``; block
    (type 16) equations are handled by :func:`handle_equation` directly to avoid
    double-wrapping.
    """
    if not e:
        return []
    out: List[Inline] = []
    if getattr(e, "text_run", None):
        out.append(_text_run_node(parser, e.text_run))
    if getattr(e, "mention_user", None):
        user_id = getattr(e.mention_user, "user_id", "")
        # Offline-pure: the node keeps the raw id (renders `@ou_id` today). Queue
        # the distinct open_id on the parser (dedup, first-seen order) for the
        # download-time name-resolution pass (LD-053), mirroring parser.file_tokens.
        if user_id and user_id not in parser.mention_user_ids:
            parser.mention_user_ids.append(user_id)
        out.append(MentionUser(user_id))
    if getattr(e, "mention_doc", None):
        title = getattr(e.mention_doc, "title", "")
        url = unescape_url(getattr(e.mention_doc, "url", ""))
        out.append(MentionDoc(title, url))
    if getattr(e, "equation", None):
        out.append(InlineEquation(e.equation.content.rstrip("\n")))
    if getattr(e, "reminder", None):
        out.append(UnsupportedInline("reminder"))
    if getattr(e, "file", None):
        out.append(UnsupportedInline("file"))
    if getattr(e, "inline_block", None):
        out.append(UnsupportedInline("inline_block"))
    if getattr(e, "link_preview", None):
        out.append(UnsupportedInline("link_preview"))
    if getattr(e, "undefined", None):
        out.append(UnsupportedInline("undefined"))
    return out


def build_inline(parser: "Parser", b: Any) -> List[Inline]:
    """Build the inline-model sequence for a text-bearing block payload.

    The text family is now on the inline model (LD-025): every ``TextElement``
    becomes real typed inline nodes (:class:`Text`, :class:`StyledText`,
    :class:`MentionUser`, :class:`MentionDoc`, :class:`InlineEquation`,
    :class:`UnsupportedInline`) — no more ``RawInline`` bridge. The renderer
    serializes them byte-identically to the prior string formatter.

    This does NOT append a trailing ``"\\n"`` — that newline is a block-level
    convention the block serializers re-add.
    """
    if not b or not hasattr(b, "elements"):
        return []
    out: List[Inline] = []
    for e in (b.elements or []):
        out.extend(_element_inlines(parser, e))
    return out


def parse_docx_text_element(parser: "Parser", e: Any) -> str:
    """Serialize one ``TextElement`` to Markdown (still-string families/tests).

    Thin wrapper over the inline model.
    """
    return parser.renderer.render_inline(_element_inlines(parser, e))


@register_block(2) # Text
def handle_text(parser: "Parser", b: Any, indent_level: int) -> Node:
    # Construct a model node (LD-025). content None models the text attr being
    # absent (renders nothing, exactly as the legacy handler did); present maps
    # to the inline sequence (renderer re-adds the block newline).
    text = getattr(b, "text", None)
    if not text or not hasattr(text, "elements"):
        return TextNode(content=None)
    return TextNode(content=build_inline(parser, text))


@register_block(14) # Code
def handle_code(parser: "Parser", b: Any, indent_level: int) -> Node:
    # Construct a model node (LD-025). The renderer fences the (stripped) inline
    # body; the ~65-language map is resolved here (PlainText/unmapped -> "").
    lang = DOCX_CODE_LANG_TO_MD.get(b.code.style.language, "") if getattr(b.code, 'style', None) else ""
    return CodeNode(lang=lang, content=build_inline(parser, b.code))


@register_block(16) # Equation
def handle_equation(parser: "Parser", b: Any, indent_level: int) -> Node:
    # Construct a model node (LD-025). The block-level equation's content lives
    # in equation elements. Pull the raw equation content directly and let the
    # renderer fence it as $$...$$ exactly once; routing through the inline path
    # would re-wrap each element in $...$ and produce malformed nested $$.
    eq = getattr(b, "equation", None)
    elements = getattr(eq, "elements", None) or [] if eq else []
    parts = []
    for e in elements:
        el_eq = getattr(e, "equation", None)
        if el_eq is not None:
            parts.append((el_eq.content or "").rstrip("\n"))
    content = "".join(parts)
    return EquationBlockNode(content=content)
