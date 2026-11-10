"""larkdocio.capabilities — a typed, JSON-serializable capability registry PROJECTED
over the op registries + drift-guarded.

**What this is.** :func:`capabilities` returns a single machine-readable answer to
"what can this toolkit do, what credentials/scopes does each surface need, and what
opt-in flags + safety contracts govern it" — the same shape a consumer (or the shipped
guide) reads once instead of scraping code and two op registries.

**Two doors, one truth.** With **no argument** it returns the **summary**: every surface, every
operation name with its kind, and the scopes each surface is **known** to need — with
``unknown_requirements`` beside them naming the endpoints whose requirement was never observed, so
an empty scope list cannot be read as *needs no permission* — names only, never prose, and
more than **20×** smaller than the registry it indexes — the ratio its size guard enforces on
every run rather than a figure recorded here — with a ``reading`` block
that spells the next call. ``full=True`` returns the whole registry; ``surface="<id>"`` returns
one surface of it. The summary is **derived from the whole payload on every call** and holds no
fact of its own, so it cannot fall behind what it summarises — the same discipline the
permission projections ship under.

Each surface's ``operations`` is the **complete** enumeration of its call sites — dispatched
operations, API-using legs and file-lifecycle calls alike, each row carrying the ``kind`` that
says which sort of call it is. **One key, every verb:** "what can this surface do" is one list,
not three sibling keys a reader has to know about, whose set varied per surface and which no
shipped document defined. **One carve-out:** a composed function that reaches no endpoint its
surface's rows do not already report is listed only where it is that surface's URL-first front
door (``read_spreadsheet_markdown``, ``read_base_markdown``). ``drive-read``'s operations are the
``DriveClient`` methods alone: ``larkdocio.drive.read_folder`` composes them with the docx, Sheets
and Base readers, ``render_folder`` makes no call, and neither is a row.

**Projection, not a hand-list (the load-bearing discipline).** The operations are NOT
maintained here. They are **projected** from the code's own registries and clients:

* **docx write** ops ← :data:`larkdocio.write.ops.OPS` — one op per ``OpDescriptor``,
  carrying its projected **anchor kinds** (the anchor classes that request family's
  own anchor field accepts — quote+breadcrumb, table locator, by-id);
* **sheets write** ops ← :data:`larkdocio.sheets.ops.OPS` — one op per
  ``SheetsOpDescriptor``, carrying its projected ``write_kind`` / ``entry_ops`` keyings;
* **docx read** ops ← the introspected public methods of :class:`larkdocio.read.client.Client`
  **and** of :class:`larkdocio.read.parser.Parser` — the client fetches blocks, the parser
  turns them into Markdown (``parse_docx_content``) or into the **node tree the writer
  anchors against** (``parse_docx_tree``). The parser leg is part of the answer: the
  projection listed only *client* ops, so the one call that produces the writer's ``root``
  was discoverable nowhere in the discovery layer;
* **sheets read** ops ← the introspected public methods of
  :class:`larkdocio.sheets.client.SheetsReadClient` (the same notion of a "public op" used
  by the drift guard of SHEETS.md — a living matrix that lives **in the source repository**, not in
  the wheel).

**Content constraints — what a surface can CREATE, not just what it can touch.**
An op name alone cannot express "you may edit a table's cells but you may not create a
merged one". The ``docx-write`` surface therefore carries a
:class:`ContentConstraints` **floor**, itself projected off ``write/`` code truth
(``InsertRequest.content``'s type args + the creatable type's dataclass fields), because
that floor — which was *only unstyled paragraph text is creatable* in an earlier release
lifted it to the Markdown-expressible set — is the single most consequential constraint in
the library and used to live only in ``NewParagraph.__doc__`` ¶3.

Because the ops come from the registries, ``capabilities()`` cannot silently disagree with
the engine: ``tests/test_capabilities.py`` is the **bidirectional drift guard** (the
SHEETS.md / BLOCKS.md guard pattern — both matrices live **in the source repository**, not in the
wheel, and this projection is what a wheel-only reader has instead) — every enumerated op
resolves to a real symbol, and every registry entry appears here. Add a write family (append one descriptor to an ``OPS``
table) or a read-client method and it shows up here automatically; drop the projection out
of sync and the guard reddens.

**Per-block-type READ support — what a document turns INTO, not just what a write can
make.** The content constraints above are a *write* answer. The commonest read question —
*"will this document's callouts / images / boards survive, and what will they become?"* — is
per block type, and it was projected nowhere: the block matrix that holds it is a
repository-level document the wheel cannot carry, and the one packaged block document existed
largely to point at it. The ``docx-read`` surface therefore carries a
:class:`BlockReadSupport` projection answering, per type, all **three** parts —
``handled`` (a join against the live handler registry, so it cannot go stale), ``emits`` (the
Markdown the reader produces) and ``lossiness`` (a state, with its meaning shipped alongside).
A projection stopping at the first part would add nothing, because ``get_registry()`` already
answers it.

**Gate coverage — where a contract is proved LIVE.** A safety contract states what
the engine promises; :class:`GateCoverage` on a write surface states **where that promise is
kept honest against the real API** — the ``live_write`` ring's command, its credentials, its
disposables-only target policy, and one :class:`GateMember` per gate module with the contracts
(and the separately-named *arms*) it proves. A test tree is not importable from the package, so
the member list is the one hand-authored table here — and it is guarded in **both** directions
against that tree (``tests/test_capabilities.py``): a claimed module must exist and carry the
marker, every marked module must have a row, and every safety contract the surface claims must
be proved by some member. So a gate cannot ship undiscoverable, and a contract cannot ship
with no live proof.

**Permissions — the scope requirement, per OPERATION.** Every operation (and every
file-lifecycle call) carries a ``permissions`` block projected out of
:mod:`larkdocio.permissions`: the Lark endpoints it reaches — **derived from its own code** —
the credential pair it needs, and the exact scopes those endpoints require, each with the
evidence that established it. A surface's own ``scopes`` / ``optional_scopes`` are the
**union of its operations' blocks** rather than a second assertion of the same fact, so the
two cannot drift apart; the guard is ``tests/test_permissions_registry.py``, and the
two projections are generated from the same rows: the per-operation matrix in
``PERMISSIONS.md`` — **in the source repository**, not in the wheel — and the consumer-facing
permissions section of the shipped guide, ``larkdocio.guide()``, which is the one a
wheel-only reader has. The library never widens, requests or escalates a scope — it only
describes.

**Typed + JSON-serializable.** The registry is built from frozen dataclasses (the "typed"
layer — :class:`Operation`, :class:`Credentials`, :class:`Flag`, :class:`SafetyContract`,
:class:`GateMember`, :class:`GateCoverage`, :class:`Surface`, :class:`Capabilities`);
:func:`capabilities` returns their ``to_dict()`` projection — a plain ``dict`` of JSON-native types only (lists, never tuples/sets), so it
round-trips through ``json.dumps``/``loads`` losslessly. No new dependency — stdlib only.
"""
import dataclasses
from dataclasses import dataclass, field
import inspect
import typing
from typing import List, Optional

from larkdocio import __version__
from larkdocio import permissions as _perm
from larkdocio.comments.client import CommentsReadClient as _CommentsReadClient
from larkdocio.comments.read import comments as _comments_read
from larkdocio.common.auth import LEGACY_ENV, READ_ENV, WRITE_ENV
from larkdocio.contacts.client import ContactsSearchClient as _ContactsSearchClient
from larkdocio.contacts.lookup import resolve_colleague as _resolve_colleague
from larkdocio.contacts.lookup import resolve_user as _resolve_user
from larkdocio.model.projection import project_block_ids as _project_block_ids
from larkdocio.read.client import Client as _DocxReadClient
from larkdocio.read.parser import Parser as _DocxParser
from larkdocio.sheets.client import SheetsReadClient as _SheetsReadClient
from larkdocio.sheets.embed import deep_read_embedded_sheet as _deep_read_embedded_sheet
from larkdocio.sheets.export_reader import SheetsExportReader as _SheetsExportReader
from larkdocio.sheets.ops import OPS as _SHEETS_WRITE_OPS
from larkdocio.sheets.ops import dry_run as _sheets_dry_run
from larkdocio.sheets.write_client import LIFECYCLE_OPS as _SHEETS_LIFECYCLE_OPS
from larkdocio.sheets.write_client import SheetsWriteClient as _SheetsWriteClient
from larkdocio.write.client import LIFECYCLE_OPS as _DOCX_LIFECYCLE_OPS
from larkdocio.write.client import WriteClient as _DocxWriteClient
from larkdocio.write.encode import CREATABLE_BLOCK_TYPES as _CREATABLE_BLOCK_TYPES
from larkdocio.write.model import InsertRequest as _InsertRequest
from larkdocio.write.model import NewBlockKind as _NewBlockKind
from larkdocio.write.ops import OPS as _DOCX_WRITE_OPS



from ._models import (
    BlockProjectionSupport,
    BlockReadSupport,
    BlockTypeSupport,
    Capabilities,
    ContentConstraints,
    Credentials,
    Doc,
    EntryPoint,
    Flag,
    GateCoverage,
    GateMember,
    LevelDescriptor,
    LifecycleOp,
    Operation,
    Reconciliation,
    SafetyContract,
    Surface,
)
from ._projections import (
    NOT_READ_BACK_FIELDS,
    NOT_WRITABLE_STYLE_FIELDS,
    _docx_anchor_kinds,
    _docx_block_projection_support,
    _docx_block_read_support,
    _docx_content_constraints,
    _docx_reconciliation,
    _docx_write_operations,
    _flatten_anchor_types,
    _flatten_content_types,
    _lifecycle_operations,
    _merge_types,
    _public_ops,
    _read_operations,
    _refused_merge_types,
    _sheets_write_operations,
    _style_fields,
    _tree_helper_operations,
)
from ._credentials import _read_credentials, _write_credentials
from ._packaged_docs import _ENTRY_POINT_NOTES, _docs, _entry_points
from ._config import (
    CONFIG_KEY_MEANINGS,
    CONFIG_REGENERATE,
    CONFIG_REGION_BEGIN,
    CONFIG_REGION_END,
    ConfigKey,
    _output_config_defaults,
    config_schema,
    config_schema_markdown,
)
from ._flag_descriptors import _flags
from ._contracts import _safety_contracts
from ._gates import _comments_read_gate_coverage, _docx_write_gate_coverage
from ._levels import (
    _comments_read_levels,
    _contacts_read_levels,
    _docx_read_levels,
    _embedded_deep_read_levels,
    _sheets_read_levels,
)
from ._permissions import _IMPL_SEEDS, _surface_with_permissions, _with_permissions
from ._assembly import _build, capabilities
