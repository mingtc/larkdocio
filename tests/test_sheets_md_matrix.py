# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""Drift guard for /SHEETS.md — the Sheets-surface capability matrix (BLOCKS.md twin).

/SHEETS.md (repo root) is the living source of truth for what the Sheets surface
supports: three matrices — **cell-type**, **structural-features**, and **operations**
— each with a status vocabulary and per-row evidence links, seeded only from verified
evidence (the LD-100 read spike + the LD-107 write spike + the shipped L1 code).

The whole point of that file is that it stays truthful against the code that exists
**today**, so this guard cross-checks it against real code truth (mirroring the
BLOCKS.md registry↔matrix guard, ``tests/test_blocks_md_matrix.py``). Because most of
the write/L2 surface is spike-proven-but-unbuilt, the guard checks only the SHIPPED
subset against code, plus status-honesty everywhere:

- **Cell-type matrix ↔ renderer dispatch (bidirectional).** Every value/segment
  branch :func:`larkdocio.sheets.render.render_cell` actually dispatches on has ≥1
  matrix row that claims it (via the row's ``Render branch`` token), and every branch
  token used in the doc is a real renderer branch — no phantom, no gap.
- **Operations matrix ↔ shipped read client (bidirectional).** Every public read op on
  :class:`larkdocio.sheets.client.SheetsReadClient` is a ``shipped-L1`` operations row
  whose code anchor resolves back to it, and no ``shipped-L1`` client-method row names a
  method that doesn't exist.
- **Status honesty.** Any row claiming a ``shipped-L1`` status must name a real,
  importable code anchor (no phantom "shipped" row); every code anchor that a row DOES
  name (in any matrix) must resolve.
- **Vocabulary + evidence hygiene (the amplifier).** Every status slug is a recognised
  member of that matrix's vocabulary (a typo like ``shipped-L11`` reddens), and every
  row carries a non-empty evidence cell (a dropped evidence link reddens).

If the Sheets code gains/loses a renderer branch or a read op without /SHEETS.md being
updated (or a row is mislabelled / mis-anchored / left evidence-less), this guard goes
red — the matrix can't silently drift.
"""
import ast
import importlib
import inspect
import re
from pathlib import Path

import larkdocio.sheets.render as _render_mod
from larkdocio.sheets.client import SheetsReadClient
from larkdocio.sheets.write_client import SheetsWriteClient

import pytest

from guard_kit import md_ragged_rows, md_table_cells

# LD-370 — CONFORMANCE-tier: SHEETS.md is a corpus member; the matrix's completeness against the shipped ops is a product claim.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

_SHEETS_MD = Path(__file__).resolve().parent.parent / "SHEETS.md"

# --------------------------------------------------------------------------- #
# Status vocabularies (one small, explicit slug set per axis — BLOCKS.md's     #
# "Status vocabulary" precedent, adapted to the Sheets surface).              #
#                                                                              #
# LD-221 (N5): the five sets below are PROJECTIONS of ONE authored registry.    #
# A slug used to be typed once per set it belonged to — ``shipped-rich-structural``     #
# four times — and nothing held the copies together, so the sets could drift    #
# apart silently: a slug added to the vocabulary but forgotten in               #
# ``_SHIPPED_STATUSES`` buys a row that claims "shipped" and is never asked to  #
# name resolving code. Authoring the slug once with its ROLES makes that        #
# unrepresentable, and ``test_every_status_slug_is_authored_exactly_once_in_    #
# this_module`` holds the single-sourcing.                                     #
# --------------------------------------------------------------------------- #

#: Roles a status slug can carry. ``_OP`` / ``_CELL`` are the two axes (the
#: operations+structural matrices vs the cell-type matrix's ``Write support``
#: column); the other three are what a guard is entitled to demand of the row.
_OP = "op"                # a member of the operations / structural status vocabulary
_CELL = "cell"            # a member of the cell-type write-support vocabulary
_SHIPPED = "shipped"      # the row must name a resolving code anchor (status honesty)
_READ_OP = "read-op"      # the row is a shipped op on SheetsReadClient (bidirectional)
_WRITE_OP = "write-op"    # the row is a shipped op on SheetsWriteClient (bidirectional)
_UNDOC = "undoc"          # DECLARED gap: /SHEETS.md's vocabulary table does not define it
                          # (see _UNDOCUMENTED_IN_SHEETS_MD, at the ratchet that reads it)

#: **The one authored home for the Sheets status vocabulary.** One row per slug;
#: the roles decide which projections it lands in, and the per-slug evidence that
#: used to live beside each copy lives here once, beside the slug it is about.
_STATUS_REGISTRY = (
    (_OP, _SHIPPED, _READ_OP, "shipped-L1"),
    (_OP, _SHIPPED, _WRITE_OP, "shipped-value-write"),
    (_OP, _SHIPPED, "shipped-read-fidelity"),
    # (LD-221) `shipped-rich-structural` IS defined in /SHEETS.md — in the CELL-TYPE
    # write-support paragraph, not in the operations vocabulary table.
    (_OP, _CELL, _SHIPPED, _WRITE_OP, _UNDOC, "shipped-rich-structural"),
    (_OP, _SHIPPED, "shipped-harness"),
    # ``shipped-LD-127`` is the ``larkdocio.capabilities()`` projected-registry surface (the
    # arc-closing cleanup round, no spec): a shipped capability that must name resolving code
    # (its anchor ``larkdocio.capabilities.capabilities``) — the status-honesty guard enforces it.
    (_OP, _SHIPPED, _UNDOC, "shipped-LD-127"),
    # ``shipped-LD-128`` is the shipped consumer guide + ``larkdocio.guide()`` accessor (the
    # in-wheel ``GUIDE.md`` distilled from + drift-guarded against ``capabilities()``): a shipped
    # capability whose anchor ``larkdocio.guide.guide`` must resolve (status-honesty guard).
    (_OP, _SHIPPED, _UNDOC, "shipped-LD-128"),
    # LD-149 — the gated FORMULA write family (a dogfood-round-2 item, no spec).
    # ``shipped-LD-149`` is the gated FORMULA write family — its anchor
    # ``larkdocio.sheets.write_apply.FormulaWriteRequest`` must resolve (status-honesty guard).
    (_OP, _CELL, _SHIPPED, _UNDOC, "shipped-LD-149"),
    # LD-159 — the standalone comments READ surface (``src/larkdocio/comments/``), whose
    # spreadsheet leg belongs in this matrix while the surface itself is not part of the
    # Sheets L1 read client. Its own slug rather than ``shipped-L1`` precisely so the
    # bidirectional read-op guard above (which is pinned to ``SheetsReadClient``) is not
    # widened to a class that is not the Sheets read client.
    # ``shipped-LD-159`` is the comments read surface — its anchor
    # ``larkdocio.comments.read.comments`` must resolve (status-honesty guard).
    (_OP, _SHIPPED, "shipped-LD-159"),
    # LD-176 — the spreadsheet FILE lifecycle (create / delete a workbook), which used to
    # live only in the test harness. Its own slug rather than a spec one (the LD-149
    # precedent), and deliberately NOT one of the plan-gated write-op statuses: it is the
    # file's lifecycle, which capabilities() reports under `lifecycle`.
    # ``shipped-LD-176`` is the spreadsheet FILE lifecycle — its anchors
    # ``SheetsWriteClient.create_spreadsheet`` / ``.delete_spreadsheet`` must resolve.
    (_OP, _SHIPPED, _WRITE_OP, "shipped-LD-176"),
    # LD-185 — the dimension-property write (row height / column width / hide-show) + its own
    # verification leg (the xlsx export's row/column dimension read). Its own slug rather than
    # a spec one (the LD-149 / LD-176 precedent): it belongs to no spec.
    # LD-185 — `SheetsWriteClient.set_dimension_properties`.
    # ``shipped-LD-185`` is the dimension-property write + its export-based dimension read —
    # anchors ``SheetsWriteClient.set_dimension_properties``,
    # ``larkdocio.sheets.write_apply.SetRowProperties`` and
    # ``larkdocio.sheets.export_reader.ExportedDimension`` must resolve.
    (_OP, _SHIPPED, _WRITE_OP, "shipped-LD-185"),
    # LD-447 — the IN-CELL IMAGE write (`values_image`) + the verdict read it rides
    # (`read_value_range`). Its own slug rather than a spec one (the LD-149 / LD-176 / LD-185
    # precedent): it belongs to no spec. Deliberately a `_WRITE_OP` status — both anchors are
    # public `SheetsWriteClient` methods the bidirectional guard must answer for — while the
    # OP itself is a `legs` entry in capabilities(), not a plan-gated operation.
    (_OP, _SHIPPED, _WRITE_OP, "shipped-LD-447"),
    # LD-448 — the FLOAT IMAGE route: the upload bound to the WORKBOOK, the `float_images`
    # bind, and the fresh `float_images/query` that is the only verdict (plus the delete).
    # Its own slug for the same reason as LD-447's — no spec — and a `_WRITE_OP` status
    # because all three legs are public `SheetsWriteClient` methods the bidirectional guard
    # must answer for, while the two OPS are `legs` entries in capabilities(), not
    # plan-gated operations. A DIFFERENT PRODUCT from the in-cell image: that one IS the
    # cell's value, this one floats OVER a range.
    (_OP, _SHIPPED, _WRITE_OP, "shipped-LD-448"),
    # LD-186 — FREEZE PANES (`updateSheet` inside the already-shipped `sheets_batch_update`)
    # + the `metainfo` frozen READ leg it needed in order to be verifiable at all. Its own
    # slug rather than a spec one (the LD-149 / LD-176 / LD-185 precedent): it belongs to no spec.
    # LD-186 — `SheetsWriteClient.read_frozen_panes` (the freeze family's
    # plan-time read AND its post-write verification leg).
    # ``shipped-LD-186`` is FREEZE PANES + its metainfo frozen read leg — anchors
    # ``SheetsWriteClient.read_frozen_panes`` and
    # ``larkdocio.sheets.write_apply.FreezePanes`` must resolve.
    (_OP, _SHIPPED, _WRITE_OP, _UNDOC, "shipped-LD-186"),
    # LD-187 — the tab-PRESENTATION write (reorder / retitle / hide-show) on the SAME
    # `updateSheet` element seam, reusing `WriteOpKind.TAB` and the v3 tab-query leg. Its own
    # slug rather than a spec one (the LD-149 / LD-176 / LD-185 / LD-186 precedent).
    # ``shipped-LD-187`` is the gated tab-PRESENTATION family (reorder / retitle / hide-show) —
    # no new op kind and no new client method, so its anchor is the request class
    # ``larkdocio.sheets.write_apply.SetTabVisibility`` (status-honesty guard).
    (_OP, _SHIPPED, _UNDOC, "shipped-LD-187"),
    # ``shipped-LD-188`` is the gated CELL STYLE write family (fill / font / number-format) —
    # its anchors ``SheetsWriteClient.put_style`` / ``.batch_update_styles`` must resolve
    # (status-honesty guard). It replaced this matrix's own ``spike-proven`` /
    # "HARNESS-ONLY — there is NO shipped style write" wording, in the same change.
    # LD-188 — `SheetsWriteClient.put_style` / `.batch_update_styles`, the
    # style write PROMOTED out of the test harness into src/.
    (_OP, _SHIPPED, _WRITE_OP, _UNDOC, "shipped-LD-188"),
    # LD-189 — CELL BORDERS. Deliberately **not** a row of its own: `borderType` /
    # `borderColor` are fields of the style payload the `shipped-LD-188` rows already own, so
    # they added no endpoint, no client op and no op kind. The slug exists because the border
    # facts (the eight values, per-edge geometry, additivity, the clear, and the gate's blind
    # spot) are recorded IN those rows and need to be attributable.
    (_OP, _UNDOC, "shipped-LD-189"),
    # LD-189 — a status this matrix did not have before: **characterized live and found not to
    # exist.** `refuted-LD-189` is word wrap, and it is a different claim from `parked` (a
    # decision to defer) or `uncaptured` (nobody looked): nine candidate field names were
    # probed, every one answered `code 0 "success"` and landed nothing — exactly as a
    # deliberately nonsense field name did — so the row's anchor is honestly EMPTY and the
    # value of the row is the evidence, not an implementation. A refuted capability that is
    # recorded is worth more than one that is silently absent, because the absence is what a
    # consumer would otherwise re-probe.
    (_OP, _UNDOC, "refuted-LD-189"),
    (_OP, "spike-proven"),
    (_OP, "planned-value-write"),
    (_OP, "planned-read-fidelity"),
    (_OP, "planned-rich-structural"),
    (_OP, _CELL, "parked"),
    (_OP, _CELL, "uncaptured"),
    (_CELL, "proven-in-spike"),
    (_CELL, "planned"),
)


def _slugs_with_role(role):
    """The projection: every registry slug carrying ``role``, as a frozenset."""
    return frozenset(entry[-1] for entry in _STATUS_REGISTRY if role in entry[:-1])


#: The cell-type matrix's *write-support* column vocabulary. ``shipped-rich-structural`` marks a
#: cell type whose rich-cell **write encoder** ships in the gated engine
#: (``larkdocio.sheets.rich_encode`` + ``write_apply.RichCellWriteRequest``, LD-119) —
#: the write twin of ``proven-in-spike`` for the four encoded rich types
#: (hyperlink / styled-runs / @user mention / dropdown multi).
#: ``shipped-LD-149`` marks the **formula** cell type, whose object-form write ships in the
#: gated engine (``larkdocio.sheets.formula`` + ``write_apply.FormulaWriteRequest``) — a
#: dogfood-round-2 item with no spec, so it carries its own issue-keyed slug (the
#: ``shipped-LD-127`` / ``shipped-LD-128`` precedent, applied to the cell-type axis).
#:
#: DERIVED (LD-221) — the ``_CELL``-role projection of ``_STATUS_REGISTRY``.
_WRITE_SUPPORT_VOCAB = _slugs_with_role(_CELL)

#: The operations / structural matrices' status vocabulary. ``shipped-rich-structural`` marks a
#: **write op / structural feature** now built in the gated write engine (LD-120: the
#: dropdown-rule ``dataValidation`` family — ``SheetsWriteClient.set_data_validation`` +
#: ``write_apply.DropdownRuleWriteRequest``); the first the Sheets rich/structural-write spec op to graduate
#: ``spike-proven`` → shipped (the ops/structural twin of the cell-type
#: ``shipped-rich-structural`` LD-119 added).
#:
#: DERIVED (LD-221) — the ``_OP``-role projection of ``_STATUS_REGISTRY``.
_OP_STATUS_VOCAB = _slugs_with_role(_OP)

#: Statuses whose row is a SHIPPED op on :class:`SheetsWriteClient` (the bidirectional
#: write-op guard's target set): ``shipped-value-write`` (the Sheets value writes),
#: ``shipped-rich-structural`` (the LD-120 dropdown-rule write) and ``shipped-LD-176`` (the FILE
#: lifecycle — create/delete a workbook, which was harness-only). Every public write-client op
#: must be one of these, anchored back to the client.
#:
#: DERIVED (LD-221) — the ``_WRITE_OP``-role projection of ``_STATUS_REGISTRY``.
_WRITE_CLIENT_SHIPPED = _slugs_with_role(_WRITE_OP)

#: The read-side twin, made explicit by LD-221 so the bidirectional read-op guard stops
#: hard-coding its own copy of ``shipped-L1``: statuses whose row is a shipped op on
#: :class:`SheetsReadClient`.
_READ_CLIENT_SHIPPED = _slugs_with_role(_READ_OP)

#: Statuses that assert real, shipped code exists behind the row. ``shipped-L1``
#: is the read surface (:class:`SheetsReadClient`); ``shipped-value-write`` is the
#: value-write surface (:class:`SheetsWriteClient`, LD-109); ``shipped-read-fidelity`` is the
#: L2 read-fidelity surface (the stdlib xlsx-export reader ``larkdocio.sheets.export_reader``,
#: LD-114 — the ``export_tasks``→poll→download lifecycle + the ``zipfile``/``xml.etree``
#: parser); ``shipped-harness`` is the leak-proof self-provision **test harness**
#: (``tests/sheets_write_harness.py``, LD-112 — the create/delete lifecycle that provisions
#: disposables for the write gate, which lives in test infrastructure, not the shipped
#: ``src/`` surface). Each demands a resolving code anchor (status honesty, below); the
#: bidirectional read/write op checks stay pinned to the ``shipped-L1`` / ``shipped-value-write``
#: client classes specifically.
#:
#: DERIVED (LD-221) — the ``_SHIPPED``-role projection of ``_STATUS_REGISTRY``.
_SHIPPED_STATUSES = _slugs_with_role(_SHIPPED)

#: A cell holding "no code / not applicable". Note: the literal ``none`` is a real
#: *render-branch* token, so it is deliberately NOT an emptiness marker here — the
#: matrix uses ``—`` for an empty anchor/evidence cell.
_NONE_TOKENS = {"", "—", "-", "n/a", "N/A"}

# --------------------------------------------------------------------------- #
# Renderer dispatch "registry" — the render.py branches, derived FROM SOURCE   #
# (text-parse, no new tooling — the BLOCKS.md guard's posture). Each marker is #
# a stable literal in render.py; the branch is "implemented" iff its marker is #
# present. This is the sheets analogue of ``blocks.get_registry()``.          #
# --------------------------------------------------------------------------- #

_BRANCH_MARKERS = {
    "none": r"value is None",
    "bool": r"isinstance\(value, bool\)",
    "number": r"isinstance\(value, \(int, float\)\)",
    "string": r"isinstance\(value, str\)",
    "segments": r"isinstance\(value, list\)",
    "segment:text": r'seg_type == "text"',
    "segment:url": r'seg_type == "url"',
    "segment:multipleValue": r'seg_type == "multipleValue"',
    "segment:mention:user": r'seg_type == "mention"',
    "segment:mention:doc": r'get\("mentionType"\) == 22',
    "segment:embed-image": r'seg_type == "embed-image"',
}


def _implemented_render_branches() -> set:
    """The set of dispatch branches ``render.py`` actually implements today.

    Parsed from the renderer's own source (via the imported module's ``__file__``,
    so it is layout-agnostic) — a branch counts as implemented iff its stable
    marker literal is present. This is the "registry" the cell-type matrix is
    checked against, both directions.
    """
    src = Path(_render_mod.__file__).read_text(encoding="utf-8")
    return {name for name, pat in _BRANCH_MARKERS.items() if re.search(pat, src)}


def _shipped_read_ops() -> set:
    """Public read-op method names on :class:`SheetsReadClient` (the shipped L1
    read-API surface). Construction helpers (classmethods like
    ``from_read_credentials``) and private helpers are excluded — they are not
    read operations.
    """
    ops = set()
    for name, member in inspect.getmembers(SheetsReadClient):
        if name.startswith("_"):
            continue
        raw = SheetsReadClient.__dict__.get(name)
        if isinstance(raw, (classmethod, staticmethod)):
            continue
        if inspect.isfunction(member) or inspect.ismethod(member):
            ops.add(name)
    return ops


def _shipped_write_ops() -> set:
    """Public value-write op method names on :class:`SheetsWriteClient` (the
    LD-109 shipped write surface). Construction helpers (classmethods like
    ``from_write_credentials``) and private helpers are excluded — they are not
    value-write operations. The write twin of :func:`_shipped_read_ops`.
    """
    ops = set()
    for name, member in inspect.getmembers(SheetsWriteClient):
        if name.startswith("_"):
            continue
        raw = SheetsWriteClient.__dict__.get(name)
        if isinstance(raw, (classmethod, staticmethod)):
            continue
        if inspect.isfunction(member) or inspect.ismethod(member):
            ops.add(name)
    return ops


def _anchor_resolves(anchor: str) -> bool:
    """True iff a ``Code anchor`` cell names a real, importable symbol.

    Three shapes are accepted:
      * ``SheetsReadClient.<method>`` — an attribute on the read client class.
      * ``SheetsWriteClient.<method>`` — an attribute on the write client class.
      * ``larkdocio.<mod>.<...>.<symbol>`` — a dotted module path; the module is
        imported and the trailing attribute chain resolved.
    A ``—`` / empty anchor is "no code" and is never passed here.
    """
    anchor = anchor.strip().strip("`")
    if anchor.startswith("SheetsReadClient."):
        return hasattr(SheetsReadClient, anchor.split(".", 1)[1])
    if anchor.startswith("SheetsWriteClient."):
        return hasattr(SheetsWriteClient, anchor.split(".", 1)[1])
    # dotted module path: walk from the longest importable module prefix.
    parts = anchor.split(".")
    for split in range(len(parts) - 1, 0, -1):
        mod_name = ".".join(parts[:split])
        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            continue
        obj = mod
        try:
            for attr in parts[split:]:
                obj = getattr(obj, attr)
        except AttributeError:
            return False
        return True
    return False


# --------------------------------------------------------------------------- #
# Markdown-table parsing (text-parse, like the BLOCKS.md guard). Tables are    #
# classified by their header signature, so a column reorder does not break the #
# guard and the three matrices are found by *meaning*, not position.          #
# --------------------------------------------------------------------------- #

_SEP_RE = re.compile(r"^\|[\s:\-|]+\|$")


#: The one-row splitter, now imported rather than defined here (LD-632).
#:
#: This function's body *was* the repo's only escape-honouring splitter, and LD-242 lifted it
#: into ``guard_kit.md_table_cells`` **by copy** — leaving the original in place, so the seam's
#: own docstring says "``md_table_cells`` is ``test_sheets_md_matrix.py::_split_row``" about a
#: second copy it does not share. Two identical definitions of a parser is one too many: it
#: was the *other* header-keyed parse, the naive one in ``tests/base_md.py``, that then dropped
#: ``BASE.md``'s escaped-pipe row for want of exactly this logic. One definition now.
_split_row = md_table_cells


def _parse_tables():
    """Yield every Markdown table in /SHEETS.md as ``(headers, rows)`` where
    ``headers`` is the lower-cased header cells and ``rows`` is a list of dicts
    keyed by those headers."""
    lines = _SHEETS_MD.read_text(encoding="utf-8").splitlines()
    tables, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        is_row = line.strip().startswith("|") and line.strip().endswith("|")
        if is_row and i + 1 < n and _SEP_RE.match(lines[i + 1].strip()):
            headers = [h.lower() for h in _split_row(line)]
            rows, j = [], i + 2
            while j < n and lines[j].strip().startswith("|") and lines[j].strip().endswith("|"):
                cells = _split_row(lines[j])
                if not _SEP_RE.match(lines[j].strip()):
                    rows.append(dict(zip(headers, cells)))
                j += 1
            tables.append((headers, rows))
            i = j
            continue
        i += 1
    return tables


def _find_table(signature_col):
    """Return the ``rows`` of the single table whose header contains
    ``signature_col``; assert exactly one exists."""
    matches = [rows for headers, rows in _parse_tables() if signature_col in headers]
    assert len(matches) == 1, (
        f"/SHEETS.md must have exactly one table with a {signature_col!r} column; "
        f"found {len(matches)}."
    )
    return matches[0]


def _cell_type_rows():
    return _find_table("render branch")


def _structural_rows():
    return _find_table("write status")


def _operations_rows():
    return _find_table("gate coverage")


# --------------------------------------------------------------------------- #
# Tests                                                                        #
# --------------------------------------------------------------------------- #


def test_sheets_md_exists():
    assert _SHEETS_MD.is_file(), f"{_SHEETS_MD} is missing — it is the Sheets source of truth."


def test_NO_SHEETS_md_table_row_is_RAGGED():
    """LD-632's report, now unconditional — LD-639 fixed the two rows it had to register.

    **LD-632's reason, unchanged and still the reason this test exists.** Re-pointing the
    header-keyed parses onto ``guard_kit.md_tables`` and asking the shared parser what it
    could not key found two operations rows carrying **seven** cells against that table's
    **six** headers — an extra prose column the header does not declare. Because
    ``_parse_tables``'s ``dict(zip(headers, cells))`` **truncates rather than refuses**, a
    ragged row is read one column out of place by every guard over it: for those two rows the
    ``evidence`` cell resolved to the PROSE and the real citation was discarded, so their
    citations were unguarded in effect and free to rot into dead references with nothing to
    say so. That is why raggedness is asserted here at all, and the argument does not depend
    on which rows happened to be ragged.

    **What LD-639 superseded is only the conclusion, not that reason.** LD-632 was
    ``tests/**``-only and ``SHEETS.md`` is a shipped byte, so it could not fix the rows — it
    registered the pair (``KNOWN_RAGGED_SHEETS_ROWS``) to turn a silent truncation into a
    bounded, named one, deliberately reporting the defect rather than papering over it.
    LD-639 landed the ``SHEETS.md`` fix: both rows fold their displaced prose into the
    already-declared **Gate coverage** cell — the same cell every neighbouring six-cell row in
    that table already carries its prose in — leaving the citation where the ``Evidence``
    header says it is. With the two rows gone the register is spent, so the check now bites
    **unconditionally**: any ragged row in ``SHEETS.md``, anywhere, is a defect from here on
    and there is no allow-list to add one to.
    """
    ragged = md_ragged_rows(_SHEETS_MD.read_text(encoding="utf-8"))
    assert ragged == [], (
        f"SHEETS.md has ragged table row(s): "
        f"{[(cells[0], f'{len(cells)} cells vs {len(headers)} headers') for headers, cells in ragged]}. "
        f"A row whose cell count does not match its table's header count is read one column "
        f"out of place by every guard over it (``dict(zip(...))`` truncates), so its right-hand "
        f"cells — the evidence citation among them — are silently mis-keyed or dropped. Fix the "
        f"row (or the header) in SHEETS.md; folding displaced prose into an already-declared "
        f"cell is what LD-639 did, and declaring a new column forces an empty cell onto every "
        f"other row."
    )


def test_all_three_matrices_present_and_nonempty():
    for finder, label in (
        (_cell_type_rows, "cell-type"),
        (_structural_rows, "structural-features"),
        (_operations_rows, "operations"),
    ):
        rows = finder()
        assert rows, f"/SHEETS.md {label} matrix has no rows."


def test_cell_type_matrix_covers_every_renderer_branch_bidirectional():
    """The cell-type matrix ↔ ``render_cell`` dispatch, both directions:
    every branch the renderer implements is claimed by ≥1 row, and every branch
    token the doc uses is a real renderer branch (no phantom, no gap)."""
    implemented = _implemented_render_branches()
    documented = set()
    for row in _cell_type_rows():
        for tok in row["render branch"].replace("`", "").split(","):
            tok = tok.strip()
            if tok and tok not in _NONE_TOKENS:
                documented.add(tok)

    missing_from_doc = implemented - documented
    assert not missing_from_doc, (
        f"render.py dispatches on branches {sorted(missing_from_doc)} that NO "
        f"/SHEETS.md cell-type row claims — the matrix has drifted from the renderer."
    )
    phantom = documented - implemented
    assert not phantom, (
        f"/SHEETS.md cell-type rows claim render branches {sorted(phantom)} that "
        f"render.py does not implement — remove them or fix the token."
    )


def test_cell_type_write_support_and_evidence_are_valid():
    for row in _cell_type_rows():
        support = row["write support"].replace("`", "").strip()
        assert support in _WRITE_SUPPORT_VOCAB, (
            f"cell-type row {row.get('cell type')!r} has an unknown write-support "
            f"slug {support!r}; allowed: {sorted(_WRITE_SUPPORT_VOCAB)}."
        )
        assert row.get("evidence", "").strip() not in _NONE_TOKENS, (
            f"cell-type row {row.get('cell type')!r} has no evidence link."
        )


def test_operations_matrix_covers_every_shipped_read_op_bidirectional():
    """The operations matrix ↔ the shipped read client, both directions: every
    public ``SheetsReadClient`` read op is a ``shipped-L1`` row anchored back to
    it, and no ``shipped-L1`` client-method row names a method that doesn't exist."""
    shipped = _shipped_read_ops()
    documented = set()
    for row in _operations_rows():
        if row["status"].replace("`", "").strip() not in _READ_CLIENT_SHIPPED:
            continue
        anchor = row.get("code anchor", "").strip().strip("`")
        if anchor.startswith("SheetsReadClient."):
            documented.add(anchor.split(".", 1)[1])

    missing = shipped - documented
    assert not missing, (
        f"SheetsReadClient read ops {sorted(missing)} have no shipped-L1 operations "
        f"row in /SHEETS.md — the operations matrix has drifted from the client."
    )
    phantom = documented - shipped
    assert not phantom, (
        f"/SHEETS.md marks SheetsReadClient methods {sorted(phantom)} shipped-L1, but "
        f"they are not read ops on the client — remove them or fix the anchor."
    )


def test_operations_matrix_covers_every_shipped_write_op_bidirectional():
    """The operations matrix ↔ the shipped WRITE client, both directions: every
    public :class:`SheetsWriteClient` write op is a shipped write-client row
    (``shipped-value-write`` value writes **or** ``shipped-rich-structural`` the LD-120
    dropdown-rule write) anchored back to it, and no such client-method row names a
    method that doesn't exist. LD-109 extended the guard to cover the write client
    per the read op↔matrix guard's own pattern; LD-120 widened it to the first
    the Sheets rich/structural-write spec client op (``set_data_validation``)."""
    shipped = _shipped_write_ops()
    documented = set()
    for row in _operations_rows():
        if row["status"].replace("`", "").strip() not in _WRITE_CLIENT_SHIPPED:
            continue
        anchor = row.get("code anchor", "").strip().strip("`")
        if anchor.startswith("SheetsWriteClient."):
            documented.add(anchor.split(".", 1)[1])

    missing = shipped - documented
    assert not missing, (
        f"SheetsWriteClient write ops {sorted(missing)} have no shipped write-client "
        f"row (shipped-value-write / shipped-rich-structural) in /SHEETS.md — the operations matrix "
        f"has drifted from the write client."
    )
    phantom = documented - shipped
    assert not phantom, (
        f"/SHEETS.md marks SheetsWriteClient methods {sorted(phantom)} shipped, "
        f"but they are not write ops on the client — remove them or fix the anchor."
    )


def test_structural_and_operations_statuses_are_valid_and_evidenced():
    checks = (
        (_structural_rows(), ("read status", "write status"), "feature"),
        (_operations_rows(), ("status",), "operation"),
    )
    for rows, status_cols, key in checks:
        for row in rows:
            for col in status_cols:
                slug = row[col].replace("`", "").strip()
                assert slug in _OP_STATUS_VOCAB, (
                    f"row {row.get(key)!r} column {col!r} has an unknown status "
                    f"{slug!r}; allowed: {sorted(_OP_STATUS_VOCAB)}."
                )
            assert row.get("evidence", "").strip() not in _NONE_TOKENS, (
                f"row {row.get(key)!r} has no evidence link."
            )


def test_shipped_rows_name_real_code_and_every_anchor_resolves():
    """Status honesty: a ``shipped-L1`` row MUST name a resolving code anchor
    (no phantom 'shipped' row), and ANY code anchor a row names (any matrix) must
    resolve to a real symbol (no phantom anchor)."""
    for rows, status_cols, key in (
        (_structural_rows(), ("read status", "write status"), "feature"),
        (_operations_rows(), ("status",), "operation"),
    ):
        for row in rows:
            anchor = row.get("code anchor", "").strip()
            statuses = {row[c].replace("`", "").strip() for c in status_cols}
            claims_shipped = bool(statuses & _SHIPPED_STATUSES)

            if claims_shipped:
                assert anchor not in _NONE_TOKENS, (
                    f"row {row.get(key)!r} claims a shipped-L1 status but names no "
                    f"code anchor — a shipped row must point at real code."
                )
            if anchor not in _NONE_TOKENS:
                assert _anchor_resolves(anchor), (
                    f"row {row.get(key)!r} names code anchor {anchor!r} that does not "
                    f"resolve to a real symbol — fix or remove it."
                )


# --------------------------------------------------------------------------- #
# LD-210 — the two /SHEETS.md items of the guard-precision sweep.              #
# --------------------------------------------------------------------------- #

def test_no_matrix_row_opens_with_a_DOUBLED_space_after_the_pipe():
    """LD-210 AC11. A row opening ``|  `` renders identically to ``| `` and so no guard ever
    saw it — which is exactly why one row drifted into it (LD-186's QA found the file's only
    such line). Pinned as a whole-file rule rather than a one-off fix, so the next hand-edited
    row cannot re-introduce it."""
    offenders = [
        (number, line[:60])
        for number, line in enumerate(_SHEETS_MD.read_text(encoding="utf-8").splitlines(), 1)
        if re.match(r"^\|\s\s", line)
    ]
    assert not offenders, (
        f"/SHEETS.md rows must open with exactly one space after the pipe: {offenders}"
    )


def _comment_create_operations():
    """``[(surface_id, domain, operation)]`` for every comment-**create** op ``capabilities()``
    reports. The registry is the authority on the boundary /SHEETS.md's comments row states."""
    import larkdocio

    found = []
    for surface_id, surface in larkdocio.capabilities(full=True)["surfaces"].items():
        for operation in surface.get("operations", ()):
            if operation.get("name") == "comment-create":
                found.append((surface_id, surface.get("domain"), operation))
    return found


def _comments_read_row():
    rows = [row for row in _operations_rows() if "comments read" in row.get("operation", "")]
    assert len(rows) == 1, f"expected exactly one comments-read operations row, got {len(rows)}"
    return rows[0]


def test_the_comments_row_states_the_creation_BOUNDARY_the_registry_actually_has():
    """LD-210 AC12. The row used to end *"Comment creation is not a capability of this library
    at any granularity"* — true when written, **falsified by LD-202**, which shipped
    whole-document comment create. The clause is half right, and the half that is right is the
    half this row is about: creation on a **spreadsheet** really is refused by the server at
    every granularity (``99992402``, Lark's own ``options: [doc,docx]``).

    So the claim is held against the **live registry** rather than merely reworded — an
    anchored create, or a spreadsheet create, reddens this and forces the matrix to follow
    (CLAUDE.md § "Living capability matrices").
    """
    creates = _comment_create_operations()

    # (a) the registry side of the claim.
    sheets_creates = [surface_id for surface_id, domain, _op in creates if domain == "sheets"]
    assert not sheets_creates, (
        f"a spreadsheet comment-create op now exists ({sheets_creates}) — /SHEETS.md's comments "
        f"row says the server refuses it at every granularity; correct the row"
    )
    docx_creates = [op for _sid, domain, op in creates if domain == "docx"]
    assert docx_creates, (
        "no docx comment-create op in capabilities() — LD-202 shipped one, and /SHEETS.md's "
        "comments row now names it"
    )
    anchors = sorted({kind for op in docx_creates for kind in op.get("anchor_kinds", ())})
    assert anchors == ["WholeDocument"], (
        f"docx comment creation now anchors on {anchors} — /SHEETS.md's comments row says "
        f"whole-document only and that anchored creation does not exist; correct the row"
    )

    # (b) the document side, in the registry's own terms.
    prose = " ".join(_comments_read_row().values()).replace("**", "").lower()
    assert "not a capability of this library at any granularity" not in prose, (
        "/SHEETS.md still carries the pre-LD-202 claim that this library cannot create a "
        "comment at all — LD-202 shipped whole-document creation on a docx"
    )
    assert "creation is not available on a spreadsheet at any granularity" in prose, (
        "the comments row no longer states the spreadsheet refusal, which is the half of the "
        "old sentence that is TRUE and the half this row is about"
    )
    for needle in ("whole-document", "docx", "ld-202"):
        assert needle in prose, (
            f"the comments row never names {needle!r} — the boundary LD-202 actually shipped"
        )


# --------------------------------------------------------------------------- #
# LD-221 (N5) — the status slug is SINGLE-SOURCED.                             #
#                                                                              #
# Every new op family used to type its ``shipped-LD-NNN`` slug up to four times:#
# once per set it belongs to here, and once in /SHEETS.md's own vocabulary      #
# table. Nothing held the copies together, so a slug added to the vocabulary    #
# but forgotten in ``_SHIPPED_STATUSES`` bought a row that claims "shipped" and #
# is never asked to name resolving code — a guard hole that opens silently.    #
# --------------------------------------------------------------------------- #

def _status_slug_literals():
    """``{slug: [lineno, ...]}`` for every status slug written as a STRING LITERAL in
    this module's own source.

    AST-based so that prose cannot be mistaken for authorship: the slugs are named
    dozens of times in the docstrings and evidence comments that carry each one's
    reasoning (``the shipped-LD-149 precedent``), and that prose is the point — it is
    the *literals* that must not be duplicated.
    """
    known = set(_OP_STATUS_VOCAB) | set(_WRITE_SUPPORT_VOCAB)
    source = Path(__file__).resolve().read_text(encoding="utf-8")
    found = {}
    for node in ast.walk(ast.parse(source, filename=__file__)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in known:
                found.setdefault(node.value, []).append(node.lineno)
    return found


def test_every_status_slug_is_authored_exactly_once_in_this_module():
    """LD-221 AC-B2: one slug, one authored home. Each of the four status sets is a
    PROJECTION of the single registry, so no slug literal appears twice."""
    repeated = {
        slug: lines for slug, lines in sorted(_status_slug_literals().items())
        if len(lines) > 1
    }
    assert not repeated, (
        "these status slugs are typed more than once in tests/test_sheets_md_matrix.py — "
        f"each must be authored in the ONE registry and projected from there: {repeated}"
    )


def _documented_status_slugs():
    """The op-axis slugs /SHEETS.md's own § "Status vocabulary" table defines (its
    ``Status`` column, which bolds one or more slugs per row)."""
    documented = set()
    for row in _find_table("meaning"):
        documented.update(re.findall(r"\*\*([\w-]+)\*\*", row["status"]))
    return documented


#: **HAND-KEPT, declared** (LD-221). /SHEETS.md's own § "Status vocabulary" table is the
#: THIRD home of the slug and the one that cannot be derived: it is a **shipped consumer
#: doc**, and its ``Meaning`` prose is written for a consumer, not projectable from a set
#: of role flags. Deriving the *guard* from the doc instead would be worse than the
#: duplication — a slug typo'd identically in a matrix row and in the vocabulary table
#: would then validate itself, which is precisely the drift the vocabulary check exists
#: to catch. So the direction is fixed: the registry above is AUTHORED, the doc is
#: HAND-KEPT, and the ratchet below is what holds them together.
#:
#: **Failure mode, stated:** a new op family that registers a slug above and forgets the
#: /SHEETS.md row ships a consumer doc whose vocabulary section cannot explain a status
#: its own matrices use. ``test_the_SHEETS_md_status_vocabulary_documents_every_op_status_slug``
#: is the guard that catches it — for every slug EXCEPT the nine below.
#:
#: These nine were **measured** on 2026-08-01 (the LD-221 RED run) and are undocumented in
#: /SHEETS.md today. They are declared rather than fixed because closing them means adding
#: nine rows of new prose to a shipped consumer doc — a change to what /SHEETS.md *says*,
#: which LD-221 AC-B5 puts out of scope. Deleting an entry from this tuple (by writing the
#: row) is the intended way to shrink it; adding one needs the same argument these nine got.
#: (Single-sourced like every other per-slug fact: the nine carry the ``_UNDOC`` role in
#: ``_STATUS_REGISTRY`` rather than a second list of slug literals here.)
_UNDOCUMENTED_IN_SHEETS_MD = _slugs_with_role(_UNDOC)


def test_the_SHEETS_md_status_vocabulary_documents_every_op_status_slug():
    """LD-221 AC-B1/B2: /SHEETS.md's vocabulary table and this module's registry name the
    same op-axis slugs, both directions — minus the nine declared, measured gaps above.

    A **ratchet**: the gap is frozen at what it was when it was measured, so the next slug
    somebody registers cannot join it silently.
    """
    documented = _documented_status_slugs()
    declared = set(_UNDOCUMENTED_IN_SHEETS_MD)

    undocumented = set(_OP_STATUS_VOCAB) - documented - declared
    assert not undocumented, (
        f"these op-axis status slugs are guarded here but defined nowhere in /SHEETS.md's "
        f"§ 'Status vocabulary' table: {sorted(undocumented)} — add the row, or (with an "
        f"argument) declare it in _UNDOCUMENTED_IN_SHEETS_MD"
    )
    phantom = documented - set(_OP_STATUS_VOCAB)
    assert not phantom, (
        f"/SHEETS.md's vocabulary table defines status slugs this guard does not know: "
        f"{sorted(phantom)}"
    )
    stale = declared & documented
    assert not stale, (
        f"_UNDOCUMENTED_IN_SHEETS_MD still declares {sorted(stale)} as undocumented, but "
        f"/SHEETS.md now defines them — drop them from the declaration"
    )
    assert len(declared) == len(_UNDOCUMENTED_IN_SHEETS_MD), (
        "_UNDOCUMENTED_IN_SHEETS_MD lists a slug twice"
    )


# --------------------------------------------------------------------------- #
# LD-539 item (b) — every `src/**` / `tests/**` python path SHEETS.md cites     #
# must EXIST                                                                   #
# --------------------------------------------------------------------------- #

#: A backtick-quoted repo-relative python path. Deliberately narrow — only `src/` and
#: `tests/` trees, only `.py` — because those two are CODE under `CLAUDE.md` § "What counts
#: as CODE here" and so a citation into them is refutable by `Path.exists()` alone. A `dev/`
#: capture path is NOT in the pattern: those trees are parkable and a retired one is not a
#: defect (`process/doctrine/retention.md`).
_CITED_PY_PATH_RE = re.compile(r"`((?:src|tests)/[A-Za-z0-9_./-]+\.py)`")


def test_every_cited_src_or_tests_python_path_exists():
    """The class that produced LD-539 item (b): the row at `SHEETS.md:250` cited
    ``src/larkdocio/capabilities.py``, a **file** that stopped existing when LD-244 split it
    into the package ``src/larkdocio/capabilities/``.

    **Why no existing guard caught it.** ``test_shipped_rows_name_real_code_and_every_anchor_
    resolves`` resolves the **code anchor** column, and the evidence-hygiene arms
    (``test_cell_type_write_support_and_evidence_are_valid`` /
    ``test_structural_and_operations_statuses_are_valid_and_evidenced``) assert only that the
    **evidence** cell is NON-EMPTY — nothing ever resolved a path *inside* an evidence cell.
    The stale citation sat in an evidence cell of a row whose code anchor
    (``larkdocio.capabilities.capabilities``) resolved perfectly.

    This is the LD-520 ``test_ac7_every_indexed_target_exists`` pattern (that guard was retired
    2026-09-18 with the dev/ evidence tree; the PATTERN is what is cited): existence machinery
    for a pointer class, and it is honest about being existence-only — it cannot tell a
    citation that is the *wrong* real file from the right one (the LD-274 lesson), only one
    that names nothing at all.
    """
    cited = sorted(set(_CITED_PY_PATH_RE.findall(_SHEETS_MD.read_text(encoding="utf-8"))))
    assert len(cited) >= 40, (
        f"only {len(cited)} python-path citations parsed out of SHEETS.md — a regex matching "
        "near-zero is this arm's own quiet-death mode, never a clean file")
    missing = [p for p in cited if not (_SHEETS_MD.parent / p).exists()]
    assert not missing, (
        f"SHEETS.md cites {len(missing)} python path(s) that do not exist: {missing}. A "
        "citation into `src/**` or `tests/**` is refutable by existence alone — correct it to "
        "what the row's claim is actually about (LD-539 item (b)).")
