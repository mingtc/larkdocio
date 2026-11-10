from typing import Any, TYPE_CHECKING

from . import register_block
from larkdocio.model import IframeNode, Node
from larkdocio.common import unescape_url

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser


@register_block(26)  # Iframe
def handle_iframe(parser: "Parser", b: Any, indent_level: int) -> Node:
    """Parse an Iframe block (Type 26) into a model node (LD-047, Decision c).

    An iframe embeds an external component; the doc carries only its URL, in
    ``iframe.component.url``. That URL arrives **percent-encoded**
    (``https%3A%2F%2F…``), so we DECODE it with :func:`unescape_url` (the
    link/mention precedent) before constructing the node — the renderer then
    emits ``[url](url)`` with the real ``https://…`` target, not a broken
    percent-encoded string.

    Robustness (AC2): an absent ``iframe``/``component`` or an empty ``url``
    yields an ``IframeNode`` with ``url=None``, which the renderer emits as a
    visible ``[Iframe: missing url]`` marker — never a silent drop or a broken
    empty link (the image ``[Image: missing token]`` precedent).

    ``iframe_type`` (15 known-provider e.g. YouTube, 99 generic web-preview) is
    captured onto the node for a future writer but dropped at render (no portable
    Markdown form — consumed-into-model, dropped-at-render).
    """
    component = getattr(getattr(b, "iframe", None), "component", None)
    if not component:
        return IframeNode()

    iframe_type = getattr(component, "iframe_type", None)
    raw_url = getattr(component, "url", None)
    if not raw_url:
        # No usable url -> visible marker (never a silent drop / broken link).
        return IframeNode(iframe_type=iframe_type)
    return IframeNode(url=unescape_url(raw_url), iframe_type=iframe_type)
