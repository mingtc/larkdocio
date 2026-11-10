"""SDK spec-conformance tests.

For each block payload model the handlers consume, read the model's ``_types``
(the authoritative field list, generated from the Feishu schema) and assert the
handler module either *reads* each field or the field is on an explicit
intentionally-dropped allowlist (colors, geometry, alignment, comment_ids,
etc.). This catches the silent-data-loss failure mode: a handler that ignores a
semantically meaningful field drops it from the Markdown with no warning.

Detection is intentionally source-text based ("does the handler module mention
this field name?") rather than runtime: it is a coarse but robust guard that
flags fields no code path touches. A field that is read indirectly (e.g. via a
shared helper in another module) is resolved by also scanning the helper
modules a handler imports.

The TextElement test enumerates all nine inline variants and asserts each one
renders OR emits a visible marker (no silent drop).

These assertions encode audit findings that have since been FIXED
(callout/source_synced/todo now render children; file surfaces its token; image
keeps its caption; every TextElement variant renders or emits a marker). They
are regression guards — the suite is green and these keep it that way.
"""
import importlib
import inspect

import pytest

# --- SDK model field lists (read from the SDK, not memory) -----------------


def model_fields(module_path, class_name):
    """Return the set of field names from an SDK model class's ``_types``."""
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return set(cls._types.keys())


SDK = "lark_oapi.api.docx.v1.model"


# Fields that are intentionally dropped in flat Markdown across all models.
# (border_color + geometry/size/scale/align are visual; sequence/folded/wrap are
# editor metadata.)
#
# NOTE (LD-042): the inline-text-run colors ``text_color`` / ``background_color``
# are NO LONGER globally dropped — ``blocks/text.py::_text_run_node`` now
# CONSUMES them into the ``StyledText`` model (consumed-into-model,
# dropped-at-render: the model is lossless for a future writer while the .md
# projection stays byte-identical). So the text:TextElementStyle case passes via
# the field-mention check on the handler source, not via the allowlist. They
# remain genuinely dropped on the CALLOUT container (visual-only container
# styling, no writer round-trip target), so they sit in that case's per-handler
# ``extra_allow`` below. ``border_color`` is a callout/cell field (never a
# text-run style — verified against ``TextElementStyle._types``) and stays here.
#
# NOTE (LD-158): ``comment_ids`` LEFT this list by the same mechanism, at BOTH
# granularities. It was classified here as "editor metadata", which mistook a
# review anchor for a formatting preference: the field is on ``Block``
# (block-level) AND on ``TextElementStyle`` (word-level), and it is the only data
# that can say which passage a reviewer objected to. ``blocks/text.py::
# _text_run_node`` now consumes the word-level list into ``StyledText`` (so the
# text:TextElementStyle case again passes via the field-mention check on the
# handler source, exactly like the colors) and ``read/parser.py::parse_docx_node``
# stamps the block-level list onto every parsed node. Both are
# consumed-into-model / dropped-at-render, so the .md projection is unmoved.
# Re-adding the field here would make this guard pass VACUOUSLY again — a test in
# ``tests/test_comment_id_capture.py`` reddens if anyone does.
GLOBAL_DROP_ALLOWLIST = {
    "border_color",
    "width", "height", "scale", "align",
    "folded", "wrap", "sequence", "indentation_level",
    "view_type", "obj_type", "fallback_type",
    "row_size", "column_width",
    "width_ratio",
}


# handler module under test -> (model module, model class, per-handler extra drops)
# The "reader modules" we scan for a field mention are the handler module plus
# any sibling block modules it imports (shared text helpers etc.).
HANDLER_CASES = [
    # (handler_module, model_module, model_class, extra_allow)
    # Callout container colors are visual-only (no portable MD form, no writer
    # round-trip target) — genuinely dropped, unlike the inline-run colors that
    # LD-042 now captures into StyledText. Allowlisted here, not globally.
    ("larkdocio.blocks.callout", f"{SDK}.callout", "Callout", {"text_color", "background_color"}),
    ("larkdocio.blocks.file", f"{SDK}.file", "File", set()),
    ("larkdocio.blocks.media", f"{SDK}.image", "Image", set()),
    ("larkdocio.blocks.diagram", f"{SDK}.add_ons", "AddOns", {"component_id"}),
    ("larkdocio.blocks.diagram", f"{SDK}.board", "Board", set()),
    ("larkdocio.blocks.synced", f"{SDK}.source_synced", "SourceSynced", set()),
    ("larkdocio.blocks.synced", f"{SDK}.reference_synced", "ReferenceSynced", set()),
    ("larkdocio.blocks.text", f"{SDK}.text_element_style", "TextElementStyle", set()),
    # Agenda item title (46, LD-046): the handler reads `elements` (via the
    # build_inline text helper it imports) and drops `align` (visual, on the
    # GLOBAL_DROP_ALLOWLIST). The empty structural wrappers 44/45/47 have empty
    # `{}` SDK models (no fields to consume), so they need no conformance case.
    ("larkdocio.blocks.container", f"{SDK}.agenda_item_title", "AgendaItemTitle", set()),
]


def _reader_source(handler_module):
    """Concatenate the source of the handler module and the sibling block
    modules it imports (so fields read via shared helpers still count)."""
    mod = importlib.import_module(handler_module)
    srcs = [inspect.getsource(mod)]
    for name, obj in vars(mod).items():
        m = getattr(obj, "__module__", None)
        if m and m.startswith("larkdocio.blocks") and m != handler_module:
            try:
                srcs.append(inspect.getsource(importlib.import_module(m)))
            except OSError:
                pass
    return "\n".join(srcs)


@pytest.mark.parametrize(
    "handler_module,model_module,model_class,extra_allow",
    HANDLER_CASES,
    ids=[f"{c[0].split('.')[-1]}:{c[2]}" for c in HANDLER_CASES],
)
def test_handler_consumes_model_fields(handler_module, model_module, model_class, extra_allow):
    fields = model_fields(model_module, model_class)
    allow = GLOBAL_DROP_ALLOWLIST | extra_allow
    src = _reader_source(handler_module)

    unconsumed = []
    for f in fields:
        if f in allow:
            continue
        # text_element_style nesting: handlers read it as `.text_element_style`
        if f not in src:
            unconsumed.append(f)

    assert not unconsumed, (
        f"{handler_module} does not appear to read SDK field(s) {sorted(unconsumed)} "
        f"of {model_class}, and they are not on the intentionally-dropped "
        f"allowlist. Either consume the field or add it to the allowlist with a "
        f"rationale."
    )


# --- TextElement variant coverage -----------------------------------------

# The nine inline TextElement variants (from text_element.py _types). Each must
# render its content OR emit a visible marker — never silently vanish.
TEXT_ELEMENT_VARIANTS = [
    "text_run",
    "mention_user",
    "mention_doc",
    "reminder",
    "file",
    "undefined",
    "inline_block",
    "equation",
    "link_preview",
]


def test_text_element_types_enumerated():
    """Lock the variant list against the SDK so a new variant forces an update."""
    fields = model_fields(f"{SDK}.text_element", "TextElement")
    assert fields == set(TEXT_ELEMENT_VARIANTS), (
        f"TextElement variants changed in the SDK: {sorted(fields)}. "
        f"Update TEXT_ELEMENT_VARIANTS and the renderer."
    )


def _render_element(variant):
    """Build a TextElement with just `variant` populated and render it via the
    text-element handler. Returns the produced string."""
    from larkdocio.read.parser import Parser
    from larkdocio.read.config import Config
    from larkdocio.blocks.text import parse_docx_text_element

    # Minimal plausible payload per variant.
    payloads = {
        "text_run": {"text_run": {"content": "RUN"}},
        "mention_user": {"mention_user": {"user_id": "U123"}},
        "mention_doc": {"mention_doc": {"title": "Doc", "url": "https://x/y"}},
        "reminder": {"reminder": {}},
        "file": {"file": {}},
        "undefined": {"undefined": {}},
        "inline_block": {"inline_block": {}},
        "equation": {"equation": {"content": "x^2"}},
        "link_preview": {"link_preview": {}},
    }
    from lark_oapi.api.docx.v1.model.text_element import TextElement

    e = TextElement(payloads[variant])
    parser = Parser(Config())
    return parse_docx_text_element(parser, e)


@pytest.mark.parametrize("variant", TEXT_ELEMENT_VARIANTS)
def test_text_element_variant_renders_or_marks(variant):
    """Each TextElement variant must produce visible output (rendered content or
    a marker). Regression guard: the renderer emits '[unsupported inline: …]'
    markers for reminder/file/undefined/inline_block/link_preview — variants the
    audit found silently dropped before the fix."""
    out = _render_element(variant)
    assert out and out.strip(), (
        f"TextElement variant '{variant}' rendered to empty output — it is "
        f"silently dropped. Render its content or emit a visible marker."
    )
