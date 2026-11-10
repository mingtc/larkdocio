"""The plan entry's ``before`` / ``after`` shape index: for every write op that previews a
text pair, WHAT that pair actually holds — generated off the serializers in
:mod:`larkdocio.write.ops`, never hand-kept.

**Why this is generated.** ``before`` does not mean one thing. It means the block's whole
text, or a table cell's descendant text, or a span, or a grid phrase that is not text at all,
or the text a delete would remove with no ``after`` beside it, or — on a checkbox flip — the
same string ``after`` holds, with the real change riding on a separate field. That list grew a
member the last time a write op shipped, which is precisely why a hand-kept table would be
wrong again at the next one. So the rows come off the code.

**The trap this module is built around: FIVE serializers, SIX shapes.** ``write/ops.py`` has
one serializer per registered op, and a generator keyed on those functions emits one row per
function and silently drops two shapes — the table-cell patch and the checkbox flip both ride
*inside* the edit serializer, as conditional branches on a
:class:`~larkdocio.write.preview.PlanEntry` field. So the basis here is **the shape**, not the
function: each serializer that emits a ``before`` key contributes its base shape, **plus one
shape for every** ``if entry.<field> is not None`` **branch in its body**, and each such field
must be a real field of the record. A branch added tomorrow becomes a row by existing; a
branch removed stops being one.

**Three answers per shape are read off the code and never typed**: whether the wire form
carries an ``after`` key at all (does the serializer emit one), whether ``before`` is *text*
(a serializer that captures a text precondition is previewing text — the table-grow op
captures none precisely because it rewrites no text), and which conditional field makes a
variant a variant. What is authored here is the one human sentence per shape, and a shape with
no sentence **raises** rather than shipping a blank cell.

**One author, mirroring** :mod:`larkdocio.model.node_docs` — the same fence shape, the same
byte-identical projection into the shipped guide, the same bidirectional guard (in the source
repository) that reddens when a shape has no row or a row has no shape.

**No** ``__all__`` **entry, deliberately** (mirrors ``model/node_docs.py``): this module is
reached only by dotted import, never from :mod:`larkdocio.write`'s own namespace, because a
new public export there would move :func:`larkdocio.capabilities` bytes for a documentation
generator rather than a writing capability.
"""
import ast
import dataclasses
import inspect
import textwrap
from typing import Dict, Optional, Tuple

from larkdocio.errors import LarkConfigError
from larkdocio.write import ops as _ops
from larkdocio.write.preview import PlanEntry

#: The fence around the generated before/after-shape table.
PLAN_FIELD_REGION_BEGIN = "<!-- BEGIN PLAN-BEFORE-AFTER-SHAPES (generated -->"
PLAN_FIELD_REGION_END = "<!-- END PLAN-BEFORE-AFTER-SHAPES -->"

#: The one-liner that regenerates the region, quoted into the region's own header.
PLAN_FIELD_REGENERATE = (
    'python -c "from larkdocio.write.plan_field_docs import plan_field_markdown as m; '
    'print(m())"'
)

#: The two wire keys this whole module is about — read off the serializers rather than
#: assumed, so an op that stops emitting one stops claiming it.
_BEFORE_KEY = "before"
_AFTER_KEY = "after"

#: The shared refusal key every serializer emits on its refused arm. Excluded when a
#: pair-less op's own fields are listed, because it is not one of that op's own fields.
_REFUSAL_KEY = "refusal"

#: The name of the shared helper each text-previewing serializer calls to attach its
#: compare-and-swap basis. Read from the function itself, so a rename follows.
_PRECONDITION_HELPER = _ops._serialize_precondition.__name__

#: The parameter name every serializer takes — the object whose fields the branches test.
_ENTRY_PARAM = "entry"


@dataclasses.dataclass(frozen=True)
class BeforeAfterShape:
    """One distinct answer to *what does this entry's* ``before`` *hold?*

    ``op`` is the registered op kind; ``variant`` is the
    :class:`~larkdocio.write.preview.PlanEntry` field whose presence makes this a variant of
    that op (``None`` for the op's base shape). ``has_after`` and ``before_is_text`` are read
    off the op's serializer, never asserted here.
    """

    op: str
    variant: Optional[str]
    has_after: bool
    before_is_text: bool


# --------------------------------------------------------------------------- #
# The derivation — three questions, each answered from the serializer's own syntax #
# --------------------------------------------------------------------------- #

def _serializer_ast(fn) -> ast.FunctionDef:
    """The parsed body of one serializer function."""
    return ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]


def _emitted_keys(fn_ast) -> Tuple[str, ...]:
    """Every wire key the serializer assigns into its dict, in first-seen order.

    Both spellings the serializers use are read: the ``{"key": …}`` literal a serializer
    starts from and the ``d["key"] = …`` assignments it adds.
    """
    keys: list = []

    def _add(name):
        if name not in keys:
            keys.append(name)

    for node in ast.walk(fn_ast):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)
                ):
                    _add(target.slice.value)
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    _add(key.value)
    return tuple(keys)


def _variant_fields(fn_ast) -> Tuple[str, ...]:
    """The record fields the serializer branches on with ``is not None`` — each one a VARIANT.

    This is the half that keeps the count honest: a serializer is one function but can emit
    more than one shape, and the branches are where the extra shapes live. A precondition
    capture is deliberately NOT one of them — it is a helper call, not a branch in this body,
    and a precondition does not change what ``before`` holds.
    """
    found: list = []
    # Sorted by position, because ``ast.walk`` is breadth-first: a branch nested inside the
    # resolved arm would otherwise be reported after a top-level one that follows it in the
    # source, and the table's row order would not be the code's own order.
    for node in sorted(ast.walk(fn_ast),
                       key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0))):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1:
            continue
        if not isinstance(test.ops[0], ast.IsNot):
            continue
        comparator = test.comparators[0]
        if not (isinstance(comparator, ast.Constant) and comparator.value is None):
            continue
        left = test.left
        if (
            isinstance(left, ast.Attribute)
            and isinstance(left.value, ast.Name)
            and left.value.id == _ENTRY_PARAM
            and left.attr not in found
        ):
            found.append(left.attr)
    return tuple(found)


def _captures_precondition(fn_ast) -> bool:
    """Whether the serializer attaches a text compare-and-swap basis — the code signal that
    its ``before`` is the target's TEXT.

    An op that rewrites no text has nothing for a per-entry compare-and-swap to hold, so it
    captures none; that is why the table-grow op's ``before`` is a grid phrase rather than
    text, and reading the signal here beats retyping the conclusion.
    """
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == _PRECONDITION_HELPER
        for node in ast.walk(fn_ast)
    )


def _record_fields() -> frozenset:
    return frozenset(f.name for f in dataclasses.fields(PlanEntry))


def _shapes_for(kind: str, fn_ast) -> Tuple[BeforeAfterShape, ...]:
    """Every shape one op contributes: its base shape plus one per conditional variant."""
    keys = _emitted_keys(fn_ast)
    if _BEFORE_KEY not in keys:
        return ()
    has_after = _AFTER_KEY in keys
    is_text = _captures_precondition(fn_ast)
    shapes = [BeforeAfterShape(op=kind, variant=None, has_after=has_after,
                               before_is_text=is_text)]
    known = _record_fields()
    for field in _variant_fields(fn_ast):
        if field not in known:
            raise LarkConfigError(
                "The %r write op's serializer branches on %r, which is not a field of the "
                "plan entry record. A branch on a field that does not exist cannot be a "
                "previewable shape; fix the serializer rather than the table."
                % (kind, field)
            )
        shapes.append(BeforeAfterShape(op=kind, variant=field, has_after=has_after,
                                       before_is_text=is_text))
    return tuple(shapes)


def before_after_shapes() -> Tuple[BeforeAfterShape, ...]:
    """Every shape a write op can serialize a ``before`` for, in registry order.

    Derived from the op registry and each op's serializer: nothing here enumerates ops, and
    nothing counts shapes. An op that joins the registry joins this answer by existing.
    """
    shapes: list = []
    for desc in _ops.OPS:
        shapes.extend(_shapes_for(desc.kind, _serializer_ast(desc.serialize)))
    return tuple(shapes)


def ops_without_before_after() -> Tuple[str, ...]:
    """The registered ops whose entries carry NEITHER field, in registry order.

    The other half of the same partition: every op is in exactly one of the two answers, so
    an op cannot join the registry and be absent from both.
    """
    return tuple(
        desc.kind for desc in _ops.OPS
        if _BEFORE_KEY not in _emitted_keys(_serializer_ast(desc.serialize))
    )


def _own_fields_of(kind: str) -> Tuple[str, ...]:
    """A pair-less op's own wire keys — what it previews INSTEAD of a text pair."""
    keys = _emitted_keys(_serializer_ast(_ops.BY_KIND[kind].serialize))
    return tuple(key for key in keys if key != _REFUSAL_KEY)


def shape_label(shape: BeforeAfterShape) -> str:
    """The row's first cell: how a caller RECOGNISES this shape on an entry it is holding.

    Derived, and the guard parses it — so a row and a shape are matched by the same string
    the generator emitted, never by a prose name somebody could reword.
    """
    base = '`entry.op == "%s"`' % shape.op
    if shape.variant is None:
        return base
    return "%s, `entry.%s` set" % (base, shape.variant)


# --------------------------------------------------------------------------- #
# The authored half — ONE sentence per shape, and a missing one is a refusal      #
# --------------------------------------------------------------------------- #

#: ``(op, variant) -> (what the shape IS, what ``before`` holds, what ``after`` holds)``.
#: The third member is ``None`` for a shape whose wire form carries no ``after`` key — and
#: that is cross-checked against the serializer, so the two cannot disagree.
_SHAPE_PROSE: Dict[Tuple[str, Optional[str]], Tuple[str, str, Optional[str]]] = {
    ("edit", None): (
        "a whole-paragraph replace",
        "The resolved block's current plain text, whole.",
        "The replacement text, whole.",
    ),
    ("edit", "cell"): (
        "a table-cell patch",
        "The **cell's** own descendant text — never the whole container block's text.",
        "The replacement text for that cell.",
    ),
    ("edit", "todo_done"): (
        "a checkbox flip",
        "The same string `after` holds: `before` == `after`, because this entry moves a "
        "checkbox and not the text. Reading the pair alone shows no change.",
        "Equal to `before`. The change is carried by the separate `entry.todo_done` field, "
        "and nowhere else — an entry whose pair matches is not a no-op.",
    ),
    ("subspan", None): (
        "an edit of part of a paragraph",
        "The span only, verbatim — the words being replaced, never the block's whole text.",
        "The replacement for that span only, likewise not the block's whole text.",
    ),
    ("grow-table", None): (
        "a row appended to a table that already exists",
        "A grid phrase — the table's shape as it stands, such as `3 rows × 2 columns`.",
        "The same phrase for the grid as it would be, such as `4 rows × 2 columns`. This pair "
        "*is* the whole preview, because appending a row changes no text.",
    ),
    ("delete", None): (
        "a block removal",
        "The text that would be removed.",
        None,
    ),
}

#: Prefixed onto the ``before`` cell of a shape whose ``before`` is not text at all.
_NOT_TEXT_PREFIX = "**Not text.** "

#: The ``after`` cell of a shape whose wire form carries no ``after`` key.
_NO_AFTER = "**Absent — this shape carries no `after` key at all.**"


def _prose_for(shape: BeforeAfterShape) -> Tuple[str, str, str]:
    """The three authored cells for one derived shape, with the derived answers folded in.

    A derived shape with no sentence **raises**: shipping a blank cell would make this a
    hand-kept table wearing a generator's clothes, which is the whole thing it replaces.
    """
    try:
        name, before, after = _SHAPE_PROSE[(shape.op, shape.variant)]
    except KeyError:
        raise LarkConfigError(
            "The write layer can serialize a %r shape (variant %r) that this table has no "
            "sentence for. A generated row cannot be left blank: say what its `before` and "
            "`after` hold, in the same change that added the shape."
            % (shape.op, shape.variant)
        ) from None
    if (after is None) != (not shape.has_after):
        raise LarkConfigError(
            "The %r shape (variant %r) says one thing about its `after` key and its "
            "serializer says the other. The serializer is the source; correct the sentence."
            % (shape.op, shape.variant)
        )
    if not shape.before_is_text:
        before = _NOT_TEXT_PREFIX + before
    return name, before, _NO_AFTER if after is None else after


def plan_field_markdown() -> str:
    """The generated before/after-shape table — one row per shape the write layer can preview.

    More rows than there are serializer functions, on purpose: two of them ride inside one
    function as conditional branches, and a table keyed on functions would drop them.
    """
    shapes = before_after_shapes()
    lines = [
        PLAN_FIELD_REGION_BEGIN.replace(" -->", ""),
        f"     regenerate with:  {PLAN_FIELD_REGENERATE}  -->",
        "",
        "A plan entry's `before` and `after` do **not** mean one thing. What they hold depends "
        "on which shape the entry is — and on one shape there is no `after` key at all, on "
        "another `before` is not text, and on a third the two are equal while the entry still "
        "changes something. Recognise the shape first, then read the pair. (The edit op is the "
        "tagless one: its entries carry no `\"op\"` key on the wire, so `entry.op` reads "
        "`\"edit\"` by default.)",
        "",
        "| Plan entry | The shape | What `before` holds | What `after` holds |",
        "|---|---|---|---|",
    ]
    for shape in shapes:
        name, before, after = _prose_for(shape)
        lines.append(f"| {shape_label(shape)} | {name} | {before} | {after} |")
    pairless = ops_without_before_after()
    if pairless:
        described = " · ".join(
            "`%s` (%s)" % (kind, ", ".join(f"`{f}`" for f in _own_fields_of(kind)))
            for kind in pairless
        )
        lines += [
            "",
            "The remaining ops carry **neither** field, because there is no old-text / "
            "new-text pair to show: what each one previews is the fields named beside it — "
            + described
            + ". A refused entry of any op carries `refusal` instead, and still carries the "
            "intent it was refused for.",
        ]
    lines += ["", PLAN_FIELD_REGION_END]
    return "\n".join(lines)
