"""larkdocio.base — the Lark **Base** (bitable) surface.

**The read half is what a consumer can reach today.** Four rungs are in place: the ``(type, ui_type)``
cell-renderer registry (:mod:`larkdocio.base.cells`), the throttled SDK-typed read client and
its op registry / error taxonomy (:mod:`larkdocio.base.client`, :mod:`~larkdocio.base.ops`,
:mod:`~larkdocio.base.errors`), the Markdown assembly and the structured intermediate
(:mod:`larkdocio.base.table`), and the **public read surface**
(:mod:`larkdocio.base.read`) — the first point at which a consumer can call larkdocio and
get a Base back. On top of them sits the **opt-in embedded-Base deep-read bridge**
(:mod:`larkdocio.base.embed`), which both docx embed block types — ``bitable`` (18) and
``reference_base`` (53) — ride to render an embedded Base inline instead of a placeholder.
It is **default-off** and degrades to that placeholder on every failure. Beside it sits the
**opt-in cross-table link resolver** (:mod:`larkdocio.base.link_resolution`), reached through
``read_base(url, resolve_links=True)``: a link cell's ids are followed to their target records
and each renders as its target table's **schema-designated primary field**. It is
**default-off and byte-identical when off**, its call count is a function of **target tables**
rather than of cells, its read cost is disclosed on the result, and a link whose target record
was deleted is a **typed, normal** outcome rather than an error.

Beside *that* sits the **row-hierarchy accessor** (:mod:`larkdocio.base.hierarchy`), which is
composition rather than construction: a Lark row tree is a **link column pointed at its own
table** named by **one view property**, so the edge is an ordinary link cell and
:func:`~larkdocio.base.hierarchy.read_hierarchy` turns it into parent/child structure in
depth-first order — **pure, opt-in and zero-call**, because the record search this surface reads
with is blind to the hierarchy in every direction. It never guesses which column is the
hierarchy, it exposes a **parent pointer and never nesting**, and the two structures Lark accepts
at ``code:0`` that no tree can contain — a row with two parents, a row that is its own parent —
are **disclosed rather than refused**, typed on the way back so the read never lies and the
traversal always terminates.

**Two entry points, on purpose.** :func:`~larkdocio.base.read.read_base_markdown` returns
the reading form; :func:`~larkdocio.base.read.read_base` returns the structured
intermediate, so a consumer is not forced through a string to reach the data. Either takes
a **Base URL or a bare ``app_token``**.

**And a record-WRITE half, whole.** :mod:`larkdocio.base.write_client` creates, updates and deletes
records on the **write** credential pair, against its own op registry
(:mod:`larkdocio.base.write_ops`, where every descriptor declares that it mutates) and the
shared write vocabulary (:mod:`larkdocio.base.write_vocabulary`, which names the eight computed
or opaque field types no caller can set). It is deliberately a **second** registry: the read
registry answers *"is this op set read-only?"* about itself, and that answer must stay true.

:mod:`larkdocio.base.write_cells` is the mirror of :mod:`~larkdocio.base.cells` on the way out
— the ``(type, ui_type)`` **write-shape** registry. It matters more than a symmetry: for
several types the write shape and the read shape are *different objects*, and a wrong write
answers ``code:0`` and stores nothing, so every shape it emits is taken from a committed
capture and the computed/opaque set is refused **locally, before any call**.

**And above them, the gate.** :mod:`larkdocio.base.model` snapshots a table and holds the
edits, :mod:`larkdocio.base.diff` types what happens to every record, :mod:`~larkdocio.base.compiler`
turns that into batch calls, and :mod:`larkdocio.base.apply` is the one seam every write passes
through: a **mandatory** ``dry_run`` builds a non-forgeable ``Plan`` and ``apply`` takes a
``Plan`` and nothing else. ``STALE_BASE`` is a **client-side** read-compare-write on
``table.revision`` — this API has no ``If-Match``, and a precondition body key is silently
ignored — so no precondition key is sent, and a ``code:0`` that did not move the anchor is
reported ``dropped`` rather than applied.

**And a SCHEMA-write half, on its own surface.** :mod:`larkdocio.base.schema_client` and the
schema-op aggregator :mod:`larkdocio.base.schema_ops` carry a **third** Base op table — a third
rather than an append, for the same reason the record one is a second: the read registry's
``read_only()`` and the record registry's ``all_mutate()`` are statements about themselves, and
a schema descriptor in either would flip a shipped answer about a surface that had not changed.
The families are the app and table lifecycle (:mod:`~larkdocio.base.schema_ops_app_table`),
columns (:mod:`~larkdocio.base.schema_ops_fields`, held to the allow-list in
:mod:`~larkdocio.base.field_vocabulary`), views (:mod:`~larkdocio.base.schema_ops_views`, whose
persistent filter is verified by read-back because this API answers success and persists
nothing for a sibling key) and the destructive family
(:mod:`~larkdocio.base.schema_ops_destructive`), fenced by the app-scoped loss preview in
:mod:`~larkdocio.base.loss_preview` and the consent token in
:mod:`~larkdocio.base.schema_apply`.

**On the front door, and described for what it is.** ``capabilities()`` reports **five** Base
surfaces — the three reads (``base-read``, ``base-comments-read``, ``base-embedded-deep-read``)
and two writes, ``base-write`` and ``base-schema-write``. ``base-write`` writes **records** —
the rows — and changes no shape; ``base-schema-write`` is where a Base, its tables, its columns
and its filtered views are authored, with **every delete that can lose row data** behind a
Base-wide loss preview and a consent token minted from its own plan: ``delete_field``,
``delete_table`` and ``batch_delete_tables``, which is exactly the set
:func:`larkdocio.base.schema_ops.destructive_ops` returns.

**Two of this surface's five deletes are deliberately OUTSIDE that fence, and neither is a gap
to be repaired.** ``delete_view`` destroys a view's **configuration** and not one cell — the
property the three fenced ops all share and it does not — so it is registered, plan-gated and
verified by read-back like every other view op, and declares no loss because there is none to
enumerate; the reason ships in :mod:`larkdocio.base.schema_ops_views`' own docstring, beside its
deliberately **empty** ``DESTRUCTIVE_OPS``. ``delete_base`` is not a registered schema op at
all: it trashes the whole object through a **Drive** endpoint, on the same whole-object gate
:meth:`larkdocio.write.client.WriteClient.delete_document` and
:meth:`larkdocio.sheets.write_client.SheetsWriteClient.delete_spreadsheet` ride, and it carries
no descriptor because it has nothing a descriptor describes — a whole Base's loss is every
table, column, record and view it holds, which no read enumerates at plan time, so there is
neither a loss list to consent to nor a bitable read-back to verify with. That argument is
stated where the op is published, at :data:`larkdocio.base.schema_client.LIFECYCLE_OPS` and on
the method itself.

Neither surface offers grouping, hidden fields or a
view-level sort, and a form view is out by this library's own policy. There is still
deliberately **no top-level re-export and no CLI flag** — no console command reaches either
write half of this surface; the one console verb that writes,
``roundtrip push --apply``, writes to a docx, guarded **in the source repository** by
``tests/front_door.py::write_reach_paths_bypassing()``, plus the per-command leg
``tests/test_cli_front_door_truth.py::test_ac1_the_reading_commands_own_handlers_reach_NO_write_module``,
and that guard says so.

**HOW THE WRITE HALVES ARE ACTUALLY REACHED — by SUBMODULE import, never off this package's own
namespace.** ``__all__`` below is the read surface plus the pure offline helpers; it names
**no** write entry point, deliberately, because the no-top-level-re-export rule above governs
this package's own front door as much as ``larkdocio``'s. So a caller imports the module that
owns the engine:

.. code-block:: python

    from larkdocio.base.apply import dry_run, apply            # the record engine
    from larkdocio.base.schema_apply import (                  # the schema engine
        schema_dry_run, schema_apply, consent_to_destroy)
    from larkdocio.base.write_client import BaseWriteClient
    from larkdocio.base.schema_client import BaseSchemaClient
    from larkdocio.base.view_plan import delete_view           # a view plan entry

**And the trap that route closes rather than relies on.** Importing this package pulls in most
of the subtree, so ``larkdocio.base.<name>`` happens to resolve for most submodules as an
ordinary side effect of Python's import machinery — which makes *what resolves that way* a
property of the import list above and not a published surface. Two consequences, both live:
``larkdocio.base.apply`` is the **module** :mod:`larkdocio.base.apply`, never the ``apply``
function inside it (``from larkdocio.base.apply import apply`` is how the function is reached);
and a submodule nothing above imports — ``view_plan``, the view-plan builder a schema caller
needs — does not resolve off this namespace at all until it is imported by name. **The
supported reach is the explicit submodule import printed above. Attribute access off this
package is not a contract**, it is not enumerated anywhere, and a name that resolves today can
stop resolving the moment the import list changes.
**The capability matrix is in the source repository, not in the wheel.** It is ``BASE.md``, the fourth
living matrix, drift-guarded by ``tests/test_base_md_matrix.py``; from an installed package
the shipped equivalents are ``larkdocio.capabilities()`` and ``larkdocio.guide()``.
"""
from larkdocio.base.embed import (
    deep_read_embedded_base,
    split_compound_token,
)
from larkdocio.base.deep_link import (
    table_url,
    view_url,
)
from larkdocio.base.link_resolution import (
    LINK_DANGLING,
    LINK_RESOLUTION_STATES,
    LINK_RESOLVED,
    LINK_UNRESOLVABLE,
    LinkResolution,
    ResolvedLink,
    resolve_links,
)
from larkdocio.base.field_migration import (
    MIGRATION_IS_NOT_ATOMIC,
    MIGRATION_IS_NOT_A_CONVERSION,
    MIGRATION_STEPS,
    TRANSCODABLE_TARGETS,
    FieldMigrationPlan,
    FieldMigrationRefused,
    UntranscodableValueError,
    apply_field_migration,
    plan_field_migration,
)
from larkdocio.base.hierarchy import (
    Hierarchy,
    HierarchyConfig,
    HierarchyRow,
    hierarchy_config,
    hierarchy_field_id,
    hierarchy_write_preview,
    parent_write_disclosure,
    read_hierarchy,
    render_hierarchy,
)
from larkdocio.base.permalink import (
    PERMALINK_ABSENT,
    PERMALINK_FORBIDDEN,
    PERMALINK_RESOLVED,
    PERMALINK_STATES,
    PERMALINK_UNMINTED,
    RecordPermalink,
    record_permalink,
)
from larkdocio.base.plain import (
    cell_text,
    plain_value,
)
from larkdocio.base.read import (
    read_base,
    read_base_markdown,
    resolve_base,
)
from larkdocio.base.computed import (
    LOOKUP_IS_A_CONSTRAINED_FORMULA,
    TRANSPORT_DOES_NOT_CARRY_THESE_KEYS,
    TRANSPORT_DROPPED_KEYS,
    ComputedColumn,
    computed_column,
    computed_columns,
    is_computed_column,
)
from larkdocio.base.referential import (
    TARGET_TABLE_LIVE,
    TARGET_TABLE_MISSING,
    TARGET_TABLE_STATES,
    TARGET_TABLE_UNKNOWN,
    LinkColumn,
    dangling_link_columns,
    link_columns,
    target_table_state,
)
from larkdocio.base.plan import (
    REFUSAL_REASONS,
    Refusal,
    RefusalReason,
)
from larkdocio.base.table import (
    EMPTY_BASE_MARKER,
    EMPTY_TABLE_MARKER,
    BaseRead,
    BaseRow,
    BaseTableRead,
    assemble_base,
    assemble_table,
    escape_cell,
    field_spec,
    render_base,
    render_table,
)

__all__ = [
    "BaseRead",
    "BaseRow",
    "BaseTableRead",
    "ComputedColumn",
    "EMPTY_BASE_MARKER",
    "EMPTY_TABLE_MARKER",
    "FieldMigrationPlan",
    "FieldMigrationRefused",
    "Hierarchy",
    "HierarchyConfig",
    "HierarchyRow",
    "LINK_DANGLING",
    "LINK_RESOLUTION_STATES",
    "LINK_RESOLVED",
    "LINK_UNRESOLVABLE",
    "LinkColumn",
    "LOOKUP_IS_A_CONSTRAINED_FORMULA",
    "LinkResolution",
    "MIGRATION_IS_NOT_ATOMIC",
    "MIGRATION_IS_NOT_A_CONVERSION",
    "MIGRATION_STEPS",
    "PERMALINK_ABSENT",
    "PERMALINK_FORBIDDEN",
    "PERMALINK_RESOLVED",
    "PERMALINK_STATES",
    "PERMALINK_UNMINTED",
    "RecordPermalink",
    # The write engine's typed refusal + its reason vocabulary. Exported so a retry guard
    # compares against an imported constant instead of a hand-typed spelling (`reason` is a
    # plain string, so only the wire value ever matches).
    "REFUSAL_REASONS",
    "Refusal",
    "RefusalReason",
    "ResolvedLink",
    "TRANSCODABLE_TARGETS",
    "UntranscodableValueError",
    "TARGET_TABLE_LIVE",
    "TARGET_TABLE_MISSING",
    "TARGET_TABLE_STATES",
    "TARGET_TABLE_UNKNOWN",
    "TRANSPORT_DOES_NOT_CARRY_THESE_KEYS",
    "TRANSPORT_DROPPED_KEYS",
    "apply_field_migration",
    "assemble_base",
    "assemble_table",
    "cell_text",
    "computed_column",
    "computed_columns",
    "dangling_link_columns",
    "deep_read_embedded_base",
    "escape_cell",
    "hierarchy_config",
    "hierarchy_field_id",
    "hierarchy_write_preview",
    "field_spec",
    "is_computed_column",
    "link_columns",
    "parent_write_disclosure",
    "plain_value",
    "plan_field_migration",
    "read_base",
    "read_base_markdown",
    "record_permalink",
    "read_hierarchy",
    "render_base",
    "render_hierarchy",
    "render_table",
    "resolve_base",
    "resolve_links",
    "split_compound_token",
    # The two pure, offline deep-link builders. Zero API calls, so no permission row —
    # the host is read off the Base's own url and never derived from the API domain.
    "table_url",
    "target_table_state",
    "view_url",
]
