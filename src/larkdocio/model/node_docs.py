"""The node-class index: for every shipped ``Node`` subclass, does ``plain_text`` return its
OWN text and does ``walk`` DESCEND into it — asked as two SEPARATE questions (LD-567).

**Why two questions, not one label.** The guide's reading recipe used to teach a binary
container/own-text split, and that split is factually wrong for nine of the model's node
classes — a ``FileNode``, a ``BitableNode``, a bare ``GridColumnNode`` and six others carry
**neither** a text field :func:`~larkdocio.model.tree.plain_text` would read nor a container
field :func:`~larkdocio.model.tree.walk` would descend into. Labelling those nine "containers"
sends a reader to ``walk()`` looking for text inside a ``FileNode`` that was never there. So
this module renders two independent yes/no columns per class instead of one taxonomy, and a
class answering no to both is visible **as such** rather than folded into either bucket.

**One author, mirroring** :mod:`larkdocio.base.shape_docs`. Nothing here is a fresh assertion:
:data:`larkdocio.model.tree._TEXT_FIELD_NAMES` / ``_TEXT_FALLBACK_FIELD_NAMES`` are the exact
field names :func:`~larkdocio.model.tree.plain_text` reads, and
:data:`larkdocio.model.tree._CHILD_SEQUENCE_FIELD_NAMES` / ``_GRID_COLUMNS_FIELD_NAME`` are the
exact field names :func:`~larkdocio.model.tree.walk` descends through — this module reads those
same names rather than retyping them, so a class the model gains, loses, or reshapes moves the
table on its own the next time it is regenerated, and a bidirectional guard (in the source repository)
reddens if a class or a row goes unmatched.

**No ``__all__`` entry, deliberately** (mirrors ``base/shape_docs.py``): this module is reached
only by dotted import (``larkdocio.model.node_docs``), never from ``larkdocio.model``'s own
namespace, because :func:`larkdocio.capabilities._projections._tree_helper_operations` projects
the docx-read surface's operations off ``larkdocio.model.tree.__all__`` — a new export there
would move ``capabilities()`` bytes for a documentation generator, not a reading capability.
"""
import dataclasses
from typing import Tuple, Type

from larkdocio.model import nodes as _nodes
from larkdocio.model.nodes import Node
from larkdocio.model.tree import (
    _CHILD_SEQUENCE_FIELD_NAMES,
    _GRID_COLUMNS_FIELD_NAME,
    _TEXT_FALLBACK_FIELD_NAMES,
    _TEXT_FIELD_NAMES,
)

#: The fence around the generated node-class index.
NODE_CLASS_REGION_BEGIN = "<!-- BEGIN NODE-CLASS-INDEX (generated -->"
NODE_CLASS_REGION_END = "<!-- END NODE-CLASS-INDEX -->"

#: The one-liner that regenerates the region, quoted into the region's own header.
NODE_CLASS_REGENERATE = (
    'python -c "from larkdocio.model.node_docs import node_class_markdown as m; print(m())"'
)


def node_classes() -> Tuple[Type[Node], ...]:
    """Every concrete :class:`~larkdocio.model.nodes.Node` subclass the model ships,
    alphabetically.

    Walks :mod:`larkdocio.model.nodes`' own namespace rather than an enumerated list, so a
    class the model gains or loses moves this tuple without an edit here — the bidirectional
    guard is what catches a class the table forgets, not a hand-kept census in this function.
    """
    found = [
        obj for name in dir(_nodes)
        if isinstance(obj := getattr(_nodes, name), type)
        and issubclass(obj, Node) and obj is not Node
    ]
    return tuple(sorted(found, key=lambda cls: cls.__name__))


def _field_names(cls: Type[Node]) -> set:
    return {f.name for f in dataclasses.fields(cls)}


def has_own_text(cls: Type[Node]) -> bool:
    """Whether :func:`~larkdocio.model.tree.plain_text` has a field on ``cls`` it would read
    for that node's own text — read off the SAME field-name tuples ``plain_text`` itself reads,
    never a second, hand-typed list."""
    names = _field_names(cls)
    return bool(names & set(_TEXT_FIELD_NAMES)) or bool(names & set(_TEXT_FALLBACK_FIELD_NAMES))


def walk_descends(cls: Type[Node]) -> bool:
    """Whether :func:`~larkdocio.model.tree.walk` has a container field on ``cls`` it would
    descend into — read off the same field names :func:`~larkdocio.model.tree._child_sequences`
    itself reads, never a second tuple."""
    names = _field_names(cls)
    return bool(names & set(_CHILD_SEQUENCE_FIELD_NAMES)) or _GRID_COLUMNS_FIELD_NAME in names


def node_class_markdown() -> str:
    """The generated node-class index — one row per class, the two questions asked separately.

    A class that answers **no to both** carries neither a text field nor a container field
    (``DividerNode``, a bare ``FileNode`` reference and the rest of that shape) — visible as
    two "no"s rather than mislabelled a container.
    """
    lines = [
        NODE_CLASS_REGION_BEGIN.replace(" -->", ""),
        f"     regenerate with:  {NODE_CLASS_REGENERATE}  -->",
        "",
        "Two separate questions per class, never folded into one container/own-text label — a "
        "class can answer **no to both** (it carries neither a text field `plain_text` reads "
        "nor a container field `walk` descends into), and a binary split would misname it a "
        "container:",
        "",
        "| Node class | `plain_text` returns its own text? | `walk` descends into it? |",
        "|---|---|---|",
    ]
    for cls in node_classes():
        own = "yes" if has_own_text(cls) else "no"
        descends = "yes" if walk_descends(cls) else "no"
        lines.append(f"| `{cls.__name__}` | {own} | {descends} |")
    lines += ["", NODE_CLASS_REGION_END]
    return "\n".join(lines)
