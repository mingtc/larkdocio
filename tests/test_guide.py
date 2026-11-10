"""Tests for the shipped consumer guide — ``src/larkdocio/GUIDE.md`` packaged IN
THE WHEEL + the :func:`larkdocio.guide` accessor + copy-paste recipes + a drift
guard against :func:`larkdocio.capabilities` (LD-128).

Five contracts, mirroring the AC:

* **AC1 — the guide ships in the wheel.** A wheel-inspection test builds the wheel
  and asserts ``larkdocio/GUIDE.md`` is in its ``RECORD`` (the ``write/README.md``
  in-wheel-packaging precedent). A fast always-on companion asserts the
  ``package-data`` declaration.
* **AC2 — ``larkdocio.guide()``.** A public callable that reads the PACKAGED resource
  via ``importlib.resources`` (never a filesystem path), returning non-empty text
  that carries the canonical recipe headings.
* **AC3 — recipes execute / verify.** Every ````python```` recipe block in the guide
  ``compile()``s (syntax-verified) and every ``larkdocio`` import it teaches resolves;
  the read recipes EXECUTE offline against fixtures, and the write recipes are verified
  against the offline injected-transport engine (the ``dry_run`` path) — none need live
  creds.
* **AC4/AC5 — the capability matrix is distilled from + drift-guarded against
  ``capabilities()``.** The guide's ``CAPABILITY-MATRIX`` region is cross-checked
  bidirectionally against :func:`larkdocio.capabilities` — every surface / op / flag /
  safety-contract the guide names exists in ``capabilities()`` and vice-versa. The
  bidirectional check is proven to bite red-then-green (the ``test_capabilities.py``
  pattern), so the guide's matrix cannot silently diverge from code truth.
"""
import re
import zipfile
from pathlib import Path

import pytest

import front_door
import capability_rows as rows
import larkdocio
from guard_kit import REPO_ROOT as _ROOT
from guard_kit import is_separator_row, md_table_cells
from log_reading_apply import reading_the_log
from larkdocio import capabilities, guide

_GUIDE_SRC = _ROOT / "src" / "larkdocio" / "GUIDE.md"


# --------------------------------------------------------------------------- #
# AC2 — larkdocio.guide(full=True) reads the PACKAGED resource, returns the guide text. #
# --------------------------------------------------------------------------- #

def test_guide_is_public_callable_returning_nonempty_text():
    """AC2: ``larkdocio.guide()`` is a public callable returning non-empty text."""
    assert callable(larkdocio.guide)
    text = guide(full=True)
    assert isinstance(text, str)
    assert text.strip()


def test_guide_reads_the_packaged_resource_via_importlib_resources():
    """AC2: the accessor reads the PACKAGED resource (``importlib.resources``), not a
    filesystem path — so it works from an installed wheel where no ``src/`` tree exists.
    Proven two ways: the accessor's return equals the packaged resource read directly,
    and the module's source uses ``importlib.resources`` rather than ``open()``/``Path``."""
    import importlib.resources as ir

    packaged = ir.files("larkdocio").joinpath("GUIDE.md").read_text(encoding="utf-8")
    assert guide(full=True) == packaged

    src = (Path(larkdocio.__file__).parent / "guide.py").read_text(encoding="utf-8")
    assert "importlib.resources" in src or "importlib_resources" in src


def test_guide_carries_the_canonical_recipe_headings():
    """AC2/AC3: the guide carries the canonical copy-paste recipes + the creds section."""
    text = guide(full=True)
    for needle in (
        "download a docx to Markdown",
        "read a sheet to Markdown",
        "docx write handshake",
        "sheets write handshake",
        "Credentials",       # the READ/WRITE app split + scopes + .env setup
        "disposable",        # the disposables doctrine for write testing
    ):
        assert needle in text, f"guide is missing the {needle!r} section"


# --------------------------------------------------------------------------- #
# AC1 — the guide ships IN THE WHEEL (unzip → RECORD), + the fast declaration   #
# companion.                                                                    #
# --------------------------------------------------------------------------- #

def test_guide_declared_in_package_data():
    """AC1 (fast, always-on): ``GUIDE.md`` is declared as ``larkdocio`` package data
    (the mechanism that lands it in the wheel) — mirrors ``test_packaging.py``'s
    entry-point declaration check."""
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    pkg_data = re.search(r"larkdocio\s*=\s*\[([^\]]*)\]", text)
    assert pkg_data and "GUIDE.md" in pkg_data.group(1), (
        "pyproject [tool.setuptools.package-data] larkdocio must list GUIDE.md"
    )


def test_guide_ships_in_the_wheel_record():
    """AC1 (the binding proof): assert ``larkdocio/GUIDE.md`` is in the built wheel's
    ``RECORD`` — the ``write/README.md`` in-wheel-packaging precedent.

    LD-221: the wheel comes from ``front_door.packaging_artifacts()``, the session-cached
    seam LD-215 built, instead of a fourth ``python -m build`` of its own. That also
    retires this test's ``pytest.skip`` pair — LD-215's arming posture (a packaging guard
    that can skip is absent from the dev loop) now applies here too.
    """
    _, wheel = front_door.packaging_artifacts()
    with zipfile.ZipFile(wheel) as z:
        record = next((n for n in z.namelist() if n.endswith("/RECORD")), None)
        assert record, "the built wheel has no RECORD"
        record_text = z.read(record).decode("utf-8")
    assert "larkdocio/GUIDE.md" in record_text, (
        "GUIDE.md is not in the wheel RECORD — it did not ship in the wheel"
    )


# --------------------------------------------------------------------------- #
# The CAPABILITY-MATRIX region parser (text-parse, the SHEETS.md guard posture).#
# --------------------------------------------------------------------------- #

_BEGIN = "<!-- BEGIN CAPABILITY-MATRIX"
_END = "<!-- END CAPABILITY-MATRIX"
_TOKEN_RE = re.compile(r"`([^`]+)`")


def _matrix_region() -> str:
    text = guide(full=True)
    b = text.find(_BEGIN)
    e = text.find(_END)
    assert b != -1 and e != -1 and e > b, (
        "GUIDE.md must delimit its capability matrix with the BEGIN/END "
        "CAPABILITY-MATRIX comment fences"
    )
    return text[b:e]


def _parse_tables(region: str):
    """Yield ``(headers, rows)`` for every Markdown table in ``region``; ``headers``
    is the lower-cased header cells, ``rows`` is a list of dicts keyed by those headers."""
    lines = region.splitlines()
    tables, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        is_row = line.strip().startswith("|") and line.strip().endswith("|")
        if is_row and i + 1 < n and is_separator_row(lines[i + 1]):
            headers = [h.lower() for h in md_table_cells(line)]
            rows, j = [], i + 2
            while j < n and lines[j].strip().startswith("|") and lines[j].strip().endswith("|"):
                if not is_separator_row(lines[j]):
                    rows.append(dict(zip(headers, md_table_cells(lines[j]))))
                j += 1
            tables.append((headers, rows))
            i = j
            continue
        i += 1
    return tables


def _find_table(*signature_cols):
    matches = [
        rows for headers, rows in _parse_tables(_matrix_region())
        if all(col in headers for col in signature_cols)
    ]
    assert len(matches) == 1, (
        f"the capability matrix must have exactly one table with columns {signature_cols}; "
        f"found {len(matches)}."
    )
    return matches[0]


def _first_token(cell: str):
    m = _TOKEN_RE.search(cell or "")
    return m.group(1) if m else None


def _guide_surface_ops() -> dict:
    """``{surface_id: sorted[op names]}`` parsed from the matrix surfaces table."""
    out = {}
    for row in _find_table("surface", "operations"):
        sid = _first_token(row["surface"])
        assert sid, f"a surfaces-table row names no surface id: {row}"
        out[sid] = sorted(_TOKEN_RE.findall(row["operations"]))
    return out


def _guide_flags() -> set:
    return {_first_token(row["flag"]) for row in _find_table("flag")}


def _guide_content_constraints(surface_id: str = "docx-write") -> list:
    """The creatable content types the matrix's **creatable-content floor** table claims
    for ``surface_id`` (LD-133 / AC8).

    The floor is the one capability fact an op list cannot carry — "you may edit a table's
    cells but you may not create a table" (dogfood F14 + F9). It lives in
    ``capabilities()['surfaces'][...]['content_constraints']`` and must be visible in the
    guide, so it is drift-guarded here like every other matrix coupling."""
    for row in _find_table("surface", "creatable"):
        if _first_token(row["surface"]) == surface_id:
            return sorted(_TOKEN_RE.findall(row["creatable"]))
    raise AssertionError(
        f"the capability matrix has no creatable-content floor row for {surface_id!r}")


#: LD-441: how one creatable-floor ENTRY is keyed for comparison. Every entry in
#: ``content_constraints`` is a full sentence — a head term, then an em-dash or parenthetical
#: clause carrying the reason. The head term is the stable part and the only part a table cell
#: can reasonably repeat, so it is what both sides are reduced to.
_FLOOR_HEAD_RE = re.compile(r" — |\(")

#: The separator the floor cells list their entries with.
_FLOOR_SEP = " · "


def _floor_key(entry: str) -> str:
    head = _FLOOR_HEAD_RE.split(entry, maxsplit=1)[0]
    return " ".join(head.replace("*", "").replace("`", "").lower().split())


def _floor_cell(column: str, surface_id: str = "docx-write") -> str:
    """One cell of the creatable-content floor row, by column name."""
    for row in _find_table("surface", "creatable"):
        if _first_token(row["surface"]) == surface_id:
            assert column in row, (
                f"the creatable-content floor table has no {column!r} column; it has "
                f"{sorted(row)}")
            return row[column]
    raise AssertionError(
        f"the capability matrix has no creatable-content floor row for {surface_id!r}")


def _floor_keys(column: str, surface_id: str = "docx-write") -> list:
    return sorted(_floor_key(item) for item in _floor_cell(column, surface_id).split(_FLOOR_SEP))


def _guide_contracts() -> set:
    return {_first_token(row["contract"]) for row in _find_table("contract")}


def _phantom_and_missing(documented, truth):
    """THE bidirectional drift check — reused by the live guard AND the red-then-green
    bite test, so the check that guards is provably the check that bites."""
    d, t = set(documented), set(truth)
    return sorted(d - t), sorted(t - d)


# --------------------------------------------------------------------------- #
# AC4/AC5 — the matrix is distilled from + drift-guarded against capabilities().#
# --------------------------------------------------------------------------- #

def test_guide_surfaces_match_capabilities_bidirectional():
    """AC4/AC5: the matrix's surface ids equal ``capabilities()``' surface ids — no
    phantom surface, no undocumented surface."""
    phantom, missing = _phantom_and_missing(
        _guide_surface_ops().keys(), capabilities(full=True)["surfaces"].keys())
    assert not phantom, f"guide names surfaces absent from capabilities(): {phantom}"
    assert not missing, f"capabilities() has surfaces the guide omits: {missing}"


def test_guide_ops_match_capabilities_per_surface_bidirectional():
    """AC4/AC5: within every surface, the ops the guide names equal the ops
    ``capabilities()`` projects — the matrix is distilled from the registry, not
    hand-maintained divergently."""
    caps = capabilities(full=True)
    guide_ops = _guide_surface_ops()
    for sid, ops in guide_ops.items():
        truth = rows.names(caps["surfaces"][sid], rows.OPERATION)
        phantom, missing = _phantom_and_missing(ops, truth)
        assert not phantom, f"{sid}: guide names ops absent from capabilities(): {phantom}"
        assert not missing, f"{sid}: capabilities() has ops the guide omits: {missing}"


def test_guide_legs_and_lifecycle_match_capabilities_per_surface_bidirectional():
    """LD-702 (U11): the surfaces table names every ``leg`` and ``lifecycle`` row too, in its own
    column — a call a surface carries is never left out of the matrix because its kind is not
    ``operation``."""
    caps = capabilities(full=True)
    table = _find_table("surface", "operations", "legs and lifecycle")
    for row in table:
        sid = _first_token(row["surface"])
        truth = (rows.names(caps["surfaces"][sid], rows.LEG)
                 + rows.names(caps["surfaces"][sid], rows.LIFECYCLE))
        phantom, missing = _phantom_and_missing(
            sorted(_TOKEN_RE.findall(row["legs and lifecycle"])), truth)
        assert not phantom, f"{sid}: guide names legs/lifecycle absent from capabilities(): {phantom}"
        assert not missing, f"{sid}: capabilities() has legs/lifecycle the guide omits: {missing}"


def test_guide_names_exactly_the_surfaces_that_carry_lifecycle_rows():
    """LD-702 (U11): the guide's sentence on ``lifecycle`` rows names the surfaces that carry
    them, derived from the registry in both directions — never "every write surface"."""
    caps = capabilities(full=True)
    truth = sorted(sid for sid, surface in caps["surfaces"].items()
                   if rows.names(surface, rows.LIFECYCLE))
    text = " ".join(guide(full=True).split())
    m = re.search(r"carry `lifecycle` \*\*rows\*\* \(((?:`[^`]+`(?:, | and )?)+)\)", text)
    assert m, "the guide's lifecycle-rows sentence must name its surfaces in one parenthesis"
    named = sorted(_TOKEN_RE.findall(m.group(1)))
    assert named == truth, (named, truth)
    numbers = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}
    assert f"{numbers[len(truth)]} write surfaces carry `lifecycle` **rows**" in text
    assert "every **write** surface carries `lifecycle`" not in text.lower()


def test_guide_flags_match_capabilities_bidirectional():
    """AC4/AC5: the matrix's flags equal ``capabilities()['flags']``."""
    phantom, missing = _phantom_and_missing(_guide_flags(), capabilities(full=True)["flags"].keys())
    assert not phantom, f"guide names flags absent from capabilities(): {phantom}"
    assert not missing, f"capabilities() has flags the guide omits: {missing}"


def test_guide_safety_contracts_match_capabilities_bidirectional():
    """AC4/AC5: the matrix's safety contracts equal ``capabilities()['safety_contracts']``."""
    phantom, missing = _phantom_and_missing(
        _guide_contracts(), capabilities(full=True)["safety_contracts"].keys())
    assert not phantom, f"guide names contracts absent from capabilities(): {phantom}"
    assert not missing, f"capabilities() has contracts the guide omits: {missing}"


def test_guide_content_constraints_match_capabilities_bidirectional():
    """LD-133 AC8: the matrix's creatable-content floor equals
    ``capabilities()[...]['content_constraints']['creatable']`` — the SAME bidirectional
    check, extended to the coupling LD-133 added. A floor that grows in code but not in the
    guide (or vice-versa) reddens; the guide's floor is the field's only human surface, and
    it going stale is precisely dogfood F14."""
    for sid, surface in capabilities(full=True)["surfaces"].items():
        cc = surface.get("content_constraints")
        if cc is None:
            continue
        phantom, missing = _phantom_and_missing(_guide_content_constraints(sid), cc["creatable"])
        assert not phantom, f"{sid}: guide claims creatable types code lacks: {phantom}"
        assert not missing, f"{sid}: code has creatable types the guide omits: {missing}"


#: LD-441 — the four floor fields that drifted through a whole arc while the guard watched
#: only ``creatable``. The NOT-creatable column is the one a consumer reads to decide a
#: capability is impossible, and it is the one nothing pinned.
_FLOOR_COLUMNS = {
    "creatable kinds": "creatable_kinds",
    "creatable out of band": "creatable_out_of_band",
    "not creatable": "not_creatable",
}


def _docx_floor():
    return capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]


@pytest.mark.parametrize("column,field", sorted(_FLOOR_COLUMNS.items()))
def test_guide_floor_columns_match_capabilities_bidirectional(column, field):
    """LD-441 AC2: the floor row is a **projection**, so every state it shows is pinned in
    both directions — a state that moves in code and not in the guide (D-71 moving an image
    to creatable-out-of-band is the exact case) reddens, and so does a table claiming a state
    the code does not have.

    ``creatable kinds`` compares backticked tokens; the two prose columns compare **head
    terms**, since the code's entries carry their reason clause and a table cell cannot.
    """
    truth = _docx_floor()[field]
    if field == "creatable_kinds":
        documented = sorted(_TOKEN_RE.findall(_floor_cell(column)))
        expected = sorted(truth)
    else:
        documented = _floor_keys(column)
        expected = sorted(_floor_key(entry) for entry in truth)
    phantom, missing = _phantom_and_missing(documented, expected)
    assert not phantom, f"the guide's {column!r} column claims states code lacks: {phantom}"
    assert not missing, f"code has {field} entries the guide omits: {missing}"


def test_guide_floor_out_of_band_block_types_match_capabilities():
    """The block types are the addressable half of the out-of-band state: 27 (image) and 23
    (file attachment). A consumer plans around the number, so the number is pinned."""
    documented = sorted(int(n) for n in re.findall(
        r"\b\d+\b", _floor_cell("creatable out of band")))
    assert documented == sorted(_docx_floor()["creatable_out_of_band_block_types"])


def test_the_floor_column_guard_bites_red_then_green():
    """LD-441 AC2 (the house red-then-green posture): the comparison that guards is the
    comparison that bites, on the very drift that shipped — an image sitting flatly on the
    NOT-creatable side with no out-of-band state anywhere."""
    truth = sorted(_floor_key(e) for e in _docx_floor()["creatable_out_of_band"])
    phantom, missing = _phantom_and_missing(_floor_keys("creatable out of band"), truth)
    assert not phantom and not missing

    p1, m1 = _phantom_and_missing([], truth)
    assert not p1 and m1 == truth, "a guide that shows NO out-of-band state must redden"
    p2, m2 = _phantom_and_missing(truth + ["a whiteboard in the document body"], truth)
    assert p2 == ["a whiteboard in the document body"] and not m2


def test_the_floor_key_reduction_keeps_the_REASON_out_of_the_comparison():
    """Why head terms: `supersession.md` § A.1 requires the code entry to keep its reason
    clause beside the superseded conclusion, and a table cell cannot repeat a paragraph. The
    key is the part both sides can honestly agree on — and it must not collapse two entries
    into one."""
    for field in ("not_creatable", "creatable_out_of_band"):
        keys = [_floor_key(e) for e in _docx_floor()[field]]
        assert len(set(keys)) == len(keys), f"{field}: two entries share a head term: {keys}"
        assert all(keys), field
    assert _floor_key("colors (text or background)") == "colors"
    assert _floor_key("**an image / media upload THROUGH THE PLAN-GATED PATH** — because "
                      "the compiler holds no bytes") == (
        "an image / media upload through the plan-gated path")


def test_every_surface_with_a_floor_in_code_has_a_floor_row_in_the_guide():
    """LD-133 AC8 (the other direction of the *table's existence*): if a surface gains a
    ``content_constraints`` field, the guide must gain a floor row for it — the lookup
    raises otherwise, so a new floor cannot ship invisible."""
    floored = [sid for sid, s in capabilities(full=True)["surfaces"].items()
               if s.get("content_constraints") is not None]
    assert floored == ["docx-write"], (
        f"a surface gained/lost a content_constraints floor: {floored} — add its row to "
        "the guide's creatable-content floor table and extend this pin")
    for sid in floored:
        assert _guide_content_constraints(sid)


def test_guide_level_descriptors_match_capabilities_bidirectional():
    """The same bidirectional posture, extended to the **level model**: every read surface's
    ``levels`` descriptor names its full-fidelity read and its projection, and the guide names
    every entry point the registry declares.

    Why it belongs in this family: the level model is the first-order product question — *must
    I round-trip through Markdown, or may I stay with the objects?* — and it is now answered in
    two places at once (the guide's own section, and ``capabilities()``). Two answers with no
    coupling is how a doc rots, so the coupling is a guard. The section-shaped assertions
    (the decision table, the wrong-level symptoms, the jargon ban, the derived lossiness list)
    live in ``tests/test_levels_delineation.py``; this is the registry half."""
    text = guide(full=True)
    caps = capabilities(full=True)["surfaces"]

    described = sorted(sid for sid, s in caps.items() if s.get("levels"))
    reads = sorted(sid for sid, s in caps.items() if s["mode"] == "read")
    assert described == reads, (
        f"every READ surface must declare its level model; described={described} reads={reads}")

    for sid in described:
        levels = caps[sid]["levels"]
        for key in ("object_entry_point", "projection_entry_point"):
            path = levels[key]
            if path is None:
                continue
            name = path.split(".")[-1]
            assert f"`{name}`" in text, (
                f"{sid}: capabilities() declares {key} {name!r} that the guide never names")


def test_drift_guard_bites_red_then_green():
    """AC5: the SAME bidirectional check that guards bites on drift and greens on truth
    — proven for a phantom op (guide claims an op the registry lacks) and a dropped op
    (guide omits a real op)."""
    truth = rows.names(capabilities(full=True)["surfaces"]["sheets-write"], rows.OPERATION)

    # phantom: an op the guide claims but the registry does not have → RED.
    phantom, missing = _phantom_and_missing(truth + ["totally-made-up-op"], truth)
    assert phantom == ["totally-made-up-op"] and not missing

    # dropped: a real op the guide omits → RED.
    dropped = truth[-1]
    phantom2, missing2 = _phantom_and_missing([o for o in truth if o != dropped], truth)
    assert not phantom2 and missing2 == [dropped]

    # truth greens the very same check → GREEN.
    phantom3, missing3 = _phantom_and_missing(truth, truth)
    assert not phantom3 and not missing3


# --------------------------------------------------------------------------- #
# AC3 — recipes are syntax-verified + every larkdocio import they teach resolves.#
# --------------------------------------------------------------------------- #

def _python_blocks() -> list:
    """Every ````python```` fenced block in the guide."""
    return re.findall(r"```python\n(.*?)```", guide(full=True), flags=re.DOTALL)


def test_guide_has_python_recipe_blocks():
    assert len(_python_blocks()) >= 4, (
        "the guide must carry ≥4 python recipe blocks (docx read, sheet read, docx "
        "write, sheets write)"
    )


def test_every_python_recipe_block_compiles():
    """AC3: every recipe block is syntactically valid Python (the literal guide text
    is compiled — a typo in a recipe reddens this)."""
    for i, block in enumerate(_python_blocks()):
        try:
            compile(block, f"<guide recipe {i}>", "exec")
        except SyntaxError as exc:  # pragma: no cover - failure path
            pytest.fail(f"recipe block {i} does not compile: {exc}\n---\n{block}")


def test_every_larkdocio_import_in_the_recipes_resolves():
    """AC3: every ``larkdocio`` import a recipe teaches resolves to a real symbol — a
    renamed / phantom public API in a recipe reddens this (binds the guide to code).

    Parsed with ``ast`` rather than line-by-line so a **parenthesized multi-line** import
    (which the LD-133 recipes use) is read as the one statement it is."""
    import ast

    statements = set()
    for block in _python_blocks():
        for node in ast.parse(block).body:
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("larkdocio"):
                statements.add(ast.unparse(node))
            elif isinstance(node, ast.Import) and any(
                    a.name.startswith("larkdocio") for a in node.names):
                statements.add(ast.unparse(node))
    assert statements, "no larkdocio imports found in the recipes"
    ns = {}
    for statement in sorted(statements):
        try:
            exec(statement, ns)
        except Exception as exc:  # pragma: no cover - failure path
            pytest.fail(f"recipe import does not resolve: {statement!r} → {exc}")


# --------------------------------------------------------------------------- #
# AC3 — the read recipes EXECUTE offline against fixtures.                       #
# --------------------------------------------------------------------------- #

def test_recipe_docx_read_renders_markdown_offline():
    """AC3 (docx read): the reader's parse→Markdown half runs offline against
    hand-authored block fixtures (the download recipe's post-fetch step)."""
    from harness import render  # tests/ is on sys.path (conftest)
    from builders import page, heading1, text_block

    blocks = [
        page("h1"),
        heading1("h1", "root", "Overview", ["p1"]),
        text_block("p1", "h1", "Revenue grew 12.4% in Q3."),
    ]
    md = render(blocks)
    assert "# Overview" in md
    assert "Revenue grew 12.4% in Q3." in md


def test_recipe_sheet_read_renders_markdown_offline():
    """AC3 (sheet read): the values→Markdown render runs offline — a titled GFM table,
    the fidelity flag left off (values-only, the byte-identical default)."""
    from larkdocio.sheets.models import SheetTab
    from larkdocio.sheets.extent import UsedRange
    from larkdocio.sheets.table import render_spreadsheet

    tab = SheetTab(sheet_id="s1", title="Sheet1", index=0, row_count=2, column_count=2)
    used = UsedRange(sheet_id="s1", a1_range="s1!A1:B2", revision=34,
                     values=[["Name", "Qty"], ["Widget", 3]])
    md = render_spreadsheet([(tab, used)])
    assert "Sheet1" in md
    assert "| Name | Qty |" in md
    assert "| Widget | 3 |" in md


# --------------------------------------------------------------------------- #
# AC3 — the write recipes are verified against the offline injected-transport   #
# engine (the dry_run path); none need live creds.                              #
# --------------------------------------------------------------------------- #

def test_recipe_docx_write_dry_run_offline():
    """AC3 (docx write handshake): resolve→dry_run against a parsed node tree yields a
    non-forgeable Plan carrying the target block_id + before/after — ZERO writes, no
    client (the offline dry-run path)."""
    from larkdocio.model import PageNode, TextNode, Text
    from larkdocio.write import Anchor, EditRequest, dry_run, Plan

    tree = PageNode(title=[Text("Doc")], block_id="root", children=[
        TextNode(content=[Text("The sky is blue.")], block_id="p1"),
    ])
    plan = dry_run(
        [EditRequest(anchor=Anchor(quote="The sky is blue.", breadcrumb=()),
                     replacement="The sky is grey.")],
        tree,
    )
    assert isinstance(plan, Plan)
    (entry,) = plan.entries
    assert entry.block_id == "p1"
    assert entry.after == "The sky is grey."


class _FakeSheetGateway:
    """Minimal duck-typed stand-in for the sheets write client seam (mirrors
    ``test_sheets_write_apply.FakeSheetGateway``): a monotonic ``revision`` (+1/write),
    a per-range value store, and an optional scheduled external bump to force STALE_SHEET."""

    def __init__(self, *, revision, values=None):
        self.revision = revision
        self.values = dict(values or {})
        self.puts = []
        self.external_bumps = {}
        self._rev_reads = 0

    def read_revision(self, spreadsheet_token):
        self._rev_reads += 1
        self.revision += self.external_bumps.pop(self._rev_reads, 0)
        return self.revision

    def read_values(self, spreadsheet_token, a1_range, value_render_option="UnformattedValue"):
        v = self.values.get(a1_range)
        return [] if v is None else v

    def put_values(self, spreadsheet_token, a1_range, values):
        self.puts.append((a1_range, values))
        self.values[a1_range] = values
        self.revision += 1
        return {"revision": self.revision}


def test_recipe_sheets_write_dry_run_and_apply_offline():
    """AC3 (sheets write handshake): dry_run (preview) → apply against the injected
    gateway writes exactly what was previewed and returns an apply-log — offline."""
    from larkdocio.sheets.write_apply import ValueWriteRequest, dry_run, apply, Plan
    apply = reading_the_log(apply)

    gw = _FakeSheetGateway(revision=34, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1("s1!A1:A1", [["new"]])], gw, "shtTOKEN")
    assert isinstance(plan, Plan)
    log = apply(plan, gw)
    assert gw.puts == [("s1!A1:A1", [["new"]])]
    assert log.entries  # a 1:1 apply-log


def test_recipe_sheets_write_refuses_stale_sheet_offline():
    """AC3 (sheets write handshake — STALE_SHEET semantics): an external revision bump
    between dry_run and the write refuses STALE_SHEET with NO write (compare-and-swap)."""
    from larkdocio.sheets.write_apply import ValueWriteRequest, dry_run, apply
    apply = reading_the_log(apply)

    gw = _FakeSheetGateway(revision=34, values={"s1!A1:A1": [["old"]]})
    plan = dry_run([ValueWriteRequest.for_a1("s1!A1:A1", [["new"]])], gw, "shtTOKEN")
    gw.external_bumps = {gw._rev_reads + 1: 1}  # bump on the next revision read (in apply)
    log = apply(plan, gw)
    assert gw.puts == [], "a stale sheet must refuse the write (no put)"
    assert any("stale" in str(e.to_dict()).lower() for e in log.entries), (
        "the apply-log must record the STALE_SHEET refusal"
    )
