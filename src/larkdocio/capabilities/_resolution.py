"""How an op row's name maps to the code it was projected out of — the **declared** shapes.

``projected_from`` has always named the code source a row was projected out of, but it was not
consistently a path you could *walk*: measured across ``capabilities()`` at v1.27.0, 39 of 88
rows named a path a plain ``getattr(<projected_from>, <name>)`` could not reach. Not because
the string was wrong — because the **shape** of the source differed per surface and was left
for the reader to guess: some sources are modules, some are classes, some are tuples of
descriptors keyed by a field, one is a function that returns such a tuple, and three rows are
internal ops whose real callable was carried only in the row's private ``impl``.

So the answer is not a fourth string convention. It is a **closed set of projection shapes**,
declared here, published per row as ``resolves_by``, and mechanically resolvable by
:func:`resolve` — which is what lets the resolvability
guard — ``tests/test_capabilities_op_resolution.py``, in the source repository, not in the wheel —
fail a row that stops resolving instead of letting it rot. A consumer reading a row gets the same
mechanism: the shape says how to follow the path, so the registry → code jump never needs a
``dir()``.
"""
import importlib
from typing import Optional

from larkdocio.errors import LarkDocIOError

#: ``getattr(<projected_from>, <name>)`` — ``projected_from`` is a **module** or a **class**
#: and the op name is an attribute of it. The default, and the shape of most read surfaces.
ATTRIBUTE = "attribute"

#: ``projected_from`` is an **iterable of descriptors** and the op name is a member's ``.name``.
DESCRIPTORS_BY_NAME = "descriptors[].name"

#: ``projected_from`` is an **iterable of descriptors** and the op name is a member's ``.kind``.
DESCRIPTORS_BY_KIND = "descriptors[].kind"

#: ``projected_from`` is a **zero-argument callable** returning such an iterable; the op name is
#: a member's ``.name``. (``larkdocio.base.schema_ops.schema_ops`` is the aggregator function.)
CALLED_DESCRIPTORS_BY_NAME = "descriptors()[].name"

#: The op name is **not** reachable at ``projected_from`` by any shape above — it is an
#: **internal op name**, and the row carries ``entry_point``: the dotted path of the symbol a
#: consumer should actually call. Never hand-authored; derived from the row's own ``impl``.
ENTRY_POINT = "entry_point"

#: The closed set — shape → what it means, in the terms a consumer follows it in.
PROJECTION_SHAPES = {
    ATTRIBUTE:
        "`projected_from` is a module or a class; the op name is an attribute of it "
        "(`getattr(projected_from, name)`).",
    DESCRIPTORS_BY_NAME:
        "`projected_from` is a collection of op descriptors; the op name is a member's "
        "`.name`.",
    DESCRIPTORS_BY_KIND:
        "`projected_from` is a collection of op descriptors; the op name is a member's "
        "`.kind`.",
    CALLED_DESCRIPTORS_BY_NAME:
        "`projected_from` is a zero-argument callable returning a collection of op "
        "descriptors; the op name is a member's `.name`.",
    ENTRY_POINT:
        "Internal op name — it is not a symbol at `projected_from`. The row's `entry_point` "
        "names the symbol to call and `note` says so in words.",
}


class UnresolvableOp(LarkDocIOError, LookupError):
    """A row's name could not be reached at its ``projected_from`` by its declared shape.

    Parented on the toolkit taxonomy (``except LarkDocIOError`` is the complete net) and on
    ``LookupError``, because that is what a failed lookup is to a caller who never imported
    larkdocio's error module."""


def object_at(path: str):
    """The object a dotted path names — a module, or an attribute inside the deepest module.

    ``larkdocio.base.media`` is a module; ``larkdocio.sheets.ops.OPS`` and
    ``larkdocio.base.media.BaseMediaClient.upload`` are attributes reached inside one. Resolved
    by importing the longest importable prefix and walking the remainder with ``getattr``, so
    one function answers all three without the caller classifying the path first.
    """
    parts = path.split(".")
    module = None
    consumed = 0
    for index in range(len(parts), 0, -1):
        try:
            module = importlib.import_module(".".join(parts[:index]))
        except ImportError:
            continue
        consumed = index
        break
    if module is None:
        raise UnresolvableOp(f"no importable module in path {path!r}")
    obj = module
    for attribute in parts[consumed:]:
        try:
            obj = getattr(obj, attribute)
        except AttributeError as exc:
            raise UnresolvableOp(f"{path!r}: {attribute!r} not found") from exc
    return obj


def _from_descriptors(table, name: str, key: str, path: str):
    for descriptor in table:
        if getattr(descriptor, key, None) == name:
            return descriptor
    raise UnresolvableOp(
        f"{path!r}: no descriptor whose .{key} is {name!r}")


def resolve(name: str, projected_from: str, resolves_by: str,
            entry_point: Optional[str] = None):
    """The object the row names, or raise :class:`UnresolvableOp`.

    This is the whole mapping, mechanically: a consumer (and the guard) hands over exactly the
    three fields the row publishes and gets back the module attribute, the descriptor, or the
    entry-point callable the op is.
    """
    if resolves_by not in PROJECTION_SHAPES:
        raise UnresolvableOp(
            f"unknown projection shape {resolves_by!r}; the declared set is "
            f"{sorted(PROJECTION_SHAPES)}")
    if resolves_by == ENTRY_POINT:
        if not entry_point:
            raise UnresolvableOp(f"{name!r} declares {ENTRY_POINT} with no entry_point")
        return object_at(entry_point)
    source = object_at(projected_from)
    if resolves_by == ATTRIBUTE:
        try:
            return getattr(source, name)
        except AttributeError as exc:
            raise UnresolvableOp(
                f"{projected_from!r} has no attribute {name!r}") from exc
    if resolves_by == CALLED_DESCRIPTORS_BY_NAME:
        if not callable(source):
            raise UnresolvableOp(f"{projected_from!r} is not callable")
        return _from_descriptors(source(), name, "name", projected_from)
    key = "name" if resolves_by == DESCRIPTORS_BY_NAME else "kind"
    return _from_descriptors(source, name, key, projected_from)


def entry_point_of(impl) -> str:
    """The dotted path of a callable — ``<module>.<qualname>``, never hand-authored.

    What makes an ``entry_point`` row un-fabricatable: the "use X" the registry publishes is X's
    own identity, read off the callable the row already carries in ``impl``.
    """
    return f"{impl.__module__}.{impl.__qualname__}"
