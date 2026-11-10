"""larkdocio.base.schema_ops — THE SCHEMA-OP AGGREGATOR.

**A third registry, and the one place a schema-op family registers.** The Base surface already
carries two op tables that each answer a question about *itself*: the read registry
(:mod:`larkdocio.base.ops`) ships ``read_only()``, which three landed test files assert is
``True``; the record-write registry (:mod:`larkdocio.base.write_ops`) ships ``all_mutate()``.
Appending a mutating descriptor to the read tuple would flip a true shipped statement to false
while the read surface had not changed at all — so schema ops do not go there either. They go
here.

**Why this module is an aggregator rather than a fourth flat tuple.** A schema write is not one
family, it is three: apps and tables (shipped), fields and views (later rungs). If all
three had to edit one tuple they would be self-dependent — the second could not start until the
first landed. So **each family ships as its OWN descriptor module** and registers by adding its
dotted name to :data:`FAMILY_MODULES`: one new file plus one new line, with no shared body to
conflict over. The aggregation is the flattening of those families, in registration order.

**The registration point is a tuple of module names, not a mutable registry object.** A
registry a module mutates on import would make the op set depend on what a consumer happened to
import; a declared list makes it depend on what the library declares. And the flattening is
**lazy** (:func:`registered_families` is cached, not computed at import), which is what lets a
family module import its descriptor type from here without an import-order hazard: importing
the family first fully initialises this module, and importing this module first touches no
family until somebody asks.

``mutates`` is declared **explicitly and has no default**, as on both landed tables and for the
same reason: four of the six ops below are ``POST``, the same verb the pinned record *read*
uses, so a verb-derived flag would be wrong in both directions at once. ``endpoint`` and
``http_method`` are stated but **cross-checked against the SDK request class itself**, so a
descriptor cannot drift away from the call it actually builds.
"""
import importlib
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Callable, Mapping, Optional, Tuple


@dataclass(frozen=True)
class BaseSchemaOpDescriptor:
    """One Base **schema** op: what it calls, on which verb, that it mutates, and how it
    settles.

    * ``name`` — the op's name, and the name of the client method that implements it;
    * ``endpoint`` — the Lark path, cross-checked against ``request_cls``' own ``uri``;
    * ``http_method`` — the verb, likewise cross-checked;
    * ``mutates`` — **mandatory, explicit, never inferred**. Every op here declares ``True``;
    * ``family`` — which schema family it belongs to, so the flattened table stays readable;
    * ``settles`` — whether the op is **asynchronous** and needs the bounded settle contract
      (:mod:`larkdocio.base.schema_settle`). Exactly one op in the whole Base surface is:
      ``copy_app``, which answers ``1254036`` to an immediate read of the app it just made;
    * ``read_back`` — a one-line statement of how the op is **verified**. Every structural op
      here is verified by a read-back, never by ``code:0`` — the API silently ignores what it
      does not recognise, so an accepted call is not an applied one;
    * ``request_cls`` — the pinned-SDK request class the client builds;
    * ``evidence`` — where this op was proven to work on a live Base.
    """

    name: str
    endpoint: str
    http_method: str
    mutates: bool
    family: str
    settles: bool
    read_back: str
    request_cls: type
    evidence: str


@dataclass(frozen=True)
class SchemaOpFamily:
    """One registered family — its name, the module that authored it, and its ops."""

    name: str
    module: str
    ops: Tuple[BaseSchemaOpDescriptor, ...]


#: **THE REGISTRATION POINT.** One dotted module name per schema-op family, in the order the
#: flattened table reports them. A family module exposes exactly one name — ``SCHEMA_OP_FAMILY``
#: — and nothing here knows anything else about it.
#:
#: The field and view families each add **their own module** and **one line here**. That
#: is the whole contract, and it is why the two can be worked in parallel with each other: they
#: share a seam that already exists rather than one they would both have to author.
#:
#: **A MISSING LINE HERE IS A SAFETY HOLE, AND A GUARD — NOT A DISK WALK — CLOSES IT (LD-637).**
#: Every answer below is derived from this tuple, including :func:`destructive_ops`, which feeds
#: :func:`request_destroys_data` and the consent fence in
#: :mod:`larkdocio.base.schema_apply`; a family module that ships in the package and never gets
#: its line is invisible to all of it, and that was proved by ablation against the whole offline
#: suite rather than argued. This tuple is **still hand-written on purpose**: it publishes
#: **registration order**, which three landed assertions pin, so deriving it from a walk would
#: change shipped behavior. Instead a guard — in the source repository, not in the wheel:
#: ``tests/test_base_schema_family_registration.py`` — walks the package on disk (by
#: :mod:`ast`, never by import) and reddens on a family-shaped module this tuple does not
#: name. **Append** when a family arrives; never reorder.
FAMILY_MODULES: Tuple[str, ...] = (
    "larkdocio.base.schema_ops_app_table",
    "larkdocio.base.schema_ops_fields",
    "larkdocio.base.schema_ops_views",
    "larkdocio.base.schema_ops_destructive",
)


@lru_cache(maxsize=1)
def registered_families() -> Tuple[SchemaOpFamily, ...]:
    """Every registered family, in :data:`FAMILY_MODULES` order.

    Lazy and cached. Lazy because a family module imports :class:`BaseSchemaOpDescriptor` from
    here, so an eager import at the bottom of this file would break whenever a consumer
    imported the family first; cached because the answer is a property of the shipped library,
    not of the call.
    """
    families = []
    for name in FAMILY_MODULES:
        family = importlib.import_module(name).SCHEMA_OP_FAMILY
        if family.module != name:
            raise ValueError(
                f"{name} registers a family that names itself {family.module!r}: a family's "
                "module attribute is how a reader gets from the flattened table back to the "
                "file that authored the row, so it cannot be wrong.")
        families.append(family)
    return tuple(families)


def schema_ops() -> Tuple[BaseSchemaOpDescriptor, ...]:
    """The flattened schema-op table — every family's ops, in registration order."""
    return tuple(descriptor
                 for family in registered_families()
                 for descriptor in family.ops)


def schema_op(name: str) -> BaseSchemaOpDescriptor:
    """The schema descriptor named ``name``."""
    for descriptor in schema_ops():
        if descriptor.name == name:
            return descriptor
    raise KeyError(name)


def family_of(name: str) -> Optional[SchemaOpFamily]:
    """The registered family that authored the op called ``name``, or ``None``."""
    for family in registered_families():
        if any(descriptor.name == name for descriptor in family.ops):
            return family
    return None


def impl_of(descriptor: BaseSchemaOpDescriptor) -> Callable:
    """The client method that implements a schema op.

    Resolved lazily by name: the client imports the family modules for their descriptors, so
    the reverse direction cannot be a module-level import.
    """
    from larkdocio.base.schema_client import BaseSchemaClient

    return getattr(BaseSchemaClient, descriptor.name)


def all_mutate() -> bool:
    """``True`` when every registered schema op declares ``mutates``.

    The third of the three self-answers, and the reason all three can be asserted at once: one
    op set is wholly non-mutating, the other two wholly mutating, and no table makes a claim
    about another's rows.
    """
    return all(descriptor.mutates is True for descriptor in schema_ops())


def settling_ops() -> Tuple[BaseSchemaOpDescriptor, ...]:
    """Every registered op that is **asynchronous** and needs the settle contract."""
    return tuple(descriptor for descriptor in schema_ops() if descriptor.settles)


@lru_cache(maxsize=1)
def destructive_ops() -> frozenset:
    """Every registered op that can **lose data**, declared by the family that ships it.

    A family publishes ``DESTRUCTIVE_OPS``; this unions them. Declared rather than derived from
    the verb for the same reason ``mutates`` is: ``tables/batch_delete`` is a ``POST``, the very
    verb the pinned record *read* uses, so a verb-derived flag would be wrong immediately — and
    an op that could destroy a column while nothing called it destructive is the one mistake
    this rung cannot afford. Every name here is fenced by
    :func:`larkdocio.base.schema_apply.consent_to_destroy`.

    **WHAT THIS COVERS, AND — because it sits under :data:`FAMILY_MODULES`' own "A MISSING LINE
    HERE IS A SAFETY HOLE" warning and is one word away from reading as *every destructive verb
    on the Base surface is fenced* — WHAT IT DOES NOT.** It covers the **schema** registry only,
    and inside it only the ops that can lose **row data**. It is not the fence for, and says
    nothing about, three other deletes on this surface:

    * ``delete_view`` — a registered ``DELETE`` in the view family that destroys a view's
      configuration and not one cell. Its absence here is a **ruling**, argued in
      :mod:`larkdocio.base.schema_ops_views`, which declares an empty ``DESTRUCTIVE_OPS`` to say
      so rather than omitting the name;
    * ``delete_record`` and ``batch_delete_records`` — a **different registry**
      (:mod:`larkdocio.base.write_ops`), with a different fence: the record engine's mandatory
      :func:`larkdocio.base.apply.dry_run` enumerates every record a delete will remove into a
      non-forgeable ``Plan`` and :func:`larkdocio.base.apply.apply` accepts a ``Plan`` and
      nothing else. A record op can never appear in this set, because only schema families are
      unioned here;
    * ``delete_base`` — not a registered op at all
      (:data:`larkdocio.base.schema_client.LIFECYCLE_OPS`): a Drive-endpoint whole-object trash
      with no plan-time loss to enumerate, on the gate ``delete_document`` and
      ``delete_spreadsheet`` ride.

    And a **conditionally** destructive op — one destructive in some request shapes only — is not
    answered here either; that is :func:`destructive_shapes`, and the one question the engine
    actually asks is :func:`request_destroys_data`, which unions the two.
    """
    import importlib

    names: set = set()
    for family in registered_families():
        names |= set(getattr(importlib.import_module(family.module), "DESTRUCTIVE_OPS", ()))
    return frozenset(names)


@lru_cache(maxsize=1)
def destructive_shapes() -> Mapping[str, Callable]:
    """``{op name: predicate(request) -> bool}`` for ops that destroy data **in some shapes**.

    The third and last thing a family may declare about destructiveness, and it exists because
    one shipped op is destructive in exactly one shape: ``update_field`` REPLACES a select
    column's option set, so a body that omits an option the table's records hold destroys those
    cells (``ld462-01``), while every other ``update_field`` — a rename, a currency format, a
    date format — cannot lose a byte. Putting that op in :func:`destructive_ops` would make every
    column rename demand a read client and a consent token, and leaving it out is what let a
    populated option be dropped silently with ``outcome == 'applied'``.

    So the question is asked of the **request** rather than of the op name, by the family that
    ships it — the same declared-not-inferred rule ``DESTRUCTIVE_OPS`` lives by. A family
    publishes ``DESTRUCTIVE_SHAPES``; this unions them. Read-only: the mapping is frozen so a
    caller cannot register a fourth opinion at runtime.
    """
    import importlib

    shapes: dict = {}
    for family in registered_families():
        shapes.update(
            getattr(importlib.import_module(family.module), "DESTRUCTIVE_SHAPES", {}) or {})
    return MappingProxyType(shapes)


def request_destroys_data(request) -> bool:
    """Whether **this request, as shaped**, can destroy data — the ONE question the engine asks.

    True for every op that is destructive by its verb, and for a conditionally destructive op
    whose own family says this shape is one of the destructive ones. Asked in exactly three
    places — the dry run (which then demands a ``read_client`` and a loss preview), the consent
    helper, and the plan's ``destructive`` property — so the three cannot drift apart about what
    needs consent.

    Note what this does **not** answer: whether the loss turns out to be *empty*. That is a
    measurement, not a shape, and it is the loss preview's answer (an option shrink over an
    option no record holds destroys nothing and applies without a token). This predicate only
    decides whether the question has to be asked at all.
    """
    op = getattr(request, "op", None)
    if op in destructive_ops():
        return True
    predicate = destructive_shapes().get(op)
    return bool(predicate is not None and predicate(request))


__all__ = [
    "BaseSchemaOpDescriptor",
    "FAMILY_MODULES",
    "SchemaOpFamily",
    "all_mutate",
    "destructive_ops",
    "destructive_shapes",
    "request_destroys_data",
    "family_of",
    "impl_of",
    "registered_families",
    "schema_op",
    "schema_ops",
    "settling_ops",
]
