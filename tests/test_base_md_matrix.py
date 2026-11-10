# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""Drift guard for /BASE.md — the Base-surface capability matrix (LD-246).

/BASE.md (repo root) is the **fourth living matrix**, born with this story alongside
/BLOCKS.md, /SHEETS.md and /PERMISSIONS.md. It is the source of truth for what the Base
surface reads, keyed on **the maintainer's own picker names** with the API identity
``(type, ui_type)`` second — the matrix a consumer can check against their own field
picker.

The whole point of that file is that it stays truthful against the code that exists
**today**, so this guard cross-checks it against real code truth (mirroring
``tests/test_sheets_md_matrix.py`` / ``tests/test_blocks_md_matrix.py``):

- **Field matrix ↔ the renderer registry (bidirectional).** Every ``(type, ui_type)``
  :mod:`larkdocio.base.cells` dispatches on has exactly one field row, and every API
  identity the doc claims is a real registered pair — no phantom, no gap.
- **Status honesty.** Every status is a recognised slug, and any row claiming
  ``supported`` / ``opaque`` names a real, importable code anchor.
- **Evidence hygiene.** Every row carries a non-empty evidence cell, and every repo path
  an evidence cell cites actually exists.
- **The register (§ Limitations & revisit-triggers).** Exactly **21** rows (LD-246 born at
  11; LD-248 added the SDK-property-loss row; LD-252's live gate added row 13, the Button
  read-identity row — the first row the register gained from a REAL Base; LD-251's close-out
  swept LD-246..LD-250 and added rows 14-20, the seven the sweep found; LD-255's live WRITE
  arm added row 21, the eventually-consistent disposable teardown it measured); all four
  content cells non-empty on each; every evidence pointer resolves to a path that exists.
  The **revisit-trigger column is the whole point of the register** — an emptied one is a
  silent regression, so a deliberate-defect test proves the guard reddens on it.
- **The register's COMPLETENESS, bidirectionally (LD-251).** Every status-bearing row in the
  whole document whose status is not ``supported`` must have a **corresponding register row**
  or an explicit, reasoned exemption here — so a surface cannot refuse something without
  recording what would reopen it. A deliberate-defect test proves a new ``refused-*`` row with
  no register entry reddens.
- **Scopes are not authored here.** /BASE.md quotes ``larkdocio.permissions``; it does not
  invent a scope string. (The repo-wide membership half is
  ``tests/test_permissions_docs.py``; this is the local, file-scoped restatement.)
- **The operations table ↔ the op registry, bidirectionally (LD-247).** Every descriptor in
  :data:`larkdocio.base.ops.OPS` has exactly one row and vice-versa, and each row's
  ``Endpoint`` / ``Verb`` / ``mutates`` cells are checked against **the code**: the first two
  against the pinned SDK request class's own ``uri`` / ``http_method``, the third against the
  descriptor's explicit flag. A doc that said a POST read mutates would redden — which is the
  whole reason the flag is declared rather than inferred.
- **§ Assembly & the public read surface ↔ the shipped code (LD-248).** Every rendering row
  names a resolving anchor and carries evidence; every documented entry point exists **and
  is re-exported from the package**, so a row naming a function nobody can import reddens;
  the two empty markers are quoted **verbatim** from the constants; and the doc states that
  ``view_id`` is not a column selector, naming ``field_names`` as the only real projection.

If the Base code gains/loses a renderer pair without /BASE.md being updated (or a row is
mislabelled, mis-anchored, or left evidence-less), this guard goes red — the matrix
cannot silently drift.
"""
import importlib
import re
from pathlib import Path

import pytest

from domain_vocabulary import RETIRED_ID

from larkdocio.base import cells

# The BASE.md reading mechanics — where the document is, and how its tables are read — live
# in ``tests/base_md.py`` (LD-308), a helper module beside ``guard_kit``. They used to be
# authored here and imported *from* this ``test_*`` module by four other guards.
from base_md import BASE_MD as _BASE_MD  # noqa: E402
from base_md import field_rows as _field_rows  # noqa: E402
from base_md import register_rows as _register_rows  # noqa: E402
from base_md import table_with as _table_with  # noqa: E402
from base_md import tables as _tables  # noqa: E402,F401  (a documented parse primitive)
from guard_kit import REPO_ROOT as _REPO  # noqa: E402
import private_tree  # noqa: E402  (LD-685)

# LD-370 — CONFORMANCE-tier: BASE.md is a corpus member; its field/op rows are product claims a rewrite must still honour.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance


@pytest.fixture(scope="module")
def base_md():
    return _BASE_MD.read_text(encoding="utf-8")


#: An API identity cell like ``` `1` / `Text` ``` — the doc's own second key.
_IDENTITY = re.compile(r"`(\d+)`\s*/\s*`([A-Za-z]+)`")

#: A dotted code anchor inside backticks: ``larkdocio.base.cells._r_segments``.
_ANCHOR = re.compile(r"`(larkdocio(?:\.[A-Za-z_][A-Za-z0-9_]*)+)`")

#: A repository path cited in an evidence cell, optionally with a `§`/`::` suffix.
_REPO_PATH = re.compile(r"`?((?:dev|src|tests|requirements)/[\w./\-]+)")

_STATUSES = {
    "supported", "opaque", "uncaptured",
    "refused-by-server", "refused-by-policy", "will-not-support",
    # LD-251: a declared Non-Goal the API does not stand in the way of — neither an unknown
    # (``uncaptured``) nor a refusal by anyone (``refused-by-*``). The distinction is the whole
    # value of the slug: a consumer reading "deferred" knows the answer is a scope decision.
    "deferred",
}

#: Statuses whose row must name resolving code (the status-honesty rule).
_CODE_BEARING = {"supported", "opaque"}


def _status_of(row):
    for key, value in row.items():
        if "status" in key.lower():
            return value.strip().strip("`")
    raise AssertionError(f"row has no status column: {row}")


def _resolves(anchor):
    module, _, attr = anchor.rpartition(".")
    for candidate, name in ((anchor, None), (module, attr)):
        try:
            mod = importlib.import_module(candidate)
        except ImportError:
            continue
        return name is None or hasattr(mod, name)
    return False


# --------------------------------------------------------------------------- #
# AC9 — the field matrix ↔ the registry, both directions                       #
# --------------------------------------------------------------------------- #

def test_the_matrix_parses_at_all(base_md):
    rows = _field_rows(base_md)
    assert len(rows) == 28, f"28 picker types expected, parsed {len(rows)}"


def test_every_registered_pair_has_exactly_one_field_row(base_md):
    documented = {}
    for row in _field_rows(base_md):
        match = _IDENTITY.search(row["API identity (`type` / `ui_type`)"])
        if match:
            pair = (int(match.group(1)), match.group(2))
            assert pair not in documented, f"/BASE.md documents {pair} twice"
            documented[pair] = row
    missing = sorted(set(cells.PAIRS) - set(documented))
    assert not missing, (
        f"the registry dispatches on {missing} that NO /BASE.md row documents — "
        "touch the surface, update the matrix"
    )


#: The ONE identity /BASE.md documents that the registry deliberately does not dispatch on.
#:
#: Normally a documented identity with no renderer is a phantom and reddens — that is the
#: guard's whole point. ``(3001, "Button")`` is the reasoned exception, and it is authored here
#: rather than tolerated by a loosened rule: THE L1 GATE found the identity on a real Base
#: (BASE.md register row 13), so the matrix must *state* it or it is lying about the API — but
#: registering a renderer for it would reopen a maintainer ruling that an API fact explicitly does not
#: reopen (register row 4's two-part trigger). Documented, unregistered, and both halves tested.
_UNREGISTERED_BY_RULING = {(3001, "Button")}


def test_every_documented_identity_is_a_real_registered_pair(base_md):
    phantom = []
    for row in _field_rows(base_md):
        match = _IDENTITY.search(row["API identity (`type` / `ui_type`)"])
        if match:
            pair = (int(match.group(1)), match.group(2))
            if cells.renderer_for(*pair) is None and pair not in _UNREGISTERED_BY_RULING:
                phantom.append(pair)
    assert not phantom, (
        f"/BASE.md claims identities {phantom} that the registry does not dispatch on"
    )


def test_the_ONE_unregistered_identity_really_is_a_PM_RULING_and_not_a_gap(base_md):
    """The exemption above has to earn itself, or it is a hole in the guard.

    For every exempted pair: the registry really does not dispatch on it, its ``ui_type`` is
    on the shipped will-not-support list, and the /BASE.md row that documents it carries the
    ``will-not-support`` status. A pair that is merely *unimplemented* fails all three.
    """
    assert _UNREGISTERED_BY_RULING == {(3001, "Button")}, (
        "the exemption list is one pair by design; adding to it is a maintainer-ruling question, not "
        "a way to quiet the phantom guard")
    for pair in _UNREGISTERED_BY_RULING:
        assert cells.renderer_for(*pair) is None
        assert pair not in cells.PAIRS
        assert pair[1] in cells.WILL_NOT_SUPPORT, (
            f"{pair} is exempted from the phantom guard but is not a will-not-support ruling "
            "— then it is an unimplemented type, and the guard should be reddening")
        rows = [
            row for row in _field_rows(base_md)
            if (m := _IDENTITY.search(row["API identity (`type` / `ui_type`)"]))
            and (int(m.group(1)), m.group(2)) == pair
        ]
        assert len(rows) == 1 and _status_of(rows[0]) == "will-not-support"


def test_the_count_the_doc_states_is_the_count_the_code_has(base_md):
    assert "28 UI types → 27 `(type, ui_type)` pairs" in base_md
    assert "26 value renderers + the Stage opaque marker" in base_md
    assert len(cells.PAIRS) == 27
    assert len(cells.VALUE_RENDERED_PAIRS) == 26


def test_button_is_the_one_row_with_no_api_identity(base_md):
    rows = [r for r in _field_rows(base_md) if r["UI name"].strip() == "Button"]
    assert len(rows) == 1
    identity = rows[0]["API identity (`type` / `ui_type`)"]
    assert "no authoring identity exists" in identity.lower(), (
        "Button is the one row with no AUTHORING identity — it does have a read identity "
        "(`3001` / `Button`, found live; register row 13), and the earlier 'no API identity "
        "at all' wording was an over-strong inference from the authoring enums")
    assert _status_of(rows[0]) == "will-not-support"


# --------------------------------------------------------------------------- #
# AC9 — status honesty, anchors, evidence                                      #
# --------------------------------------------------------------------------- #

def test_every_status_slug_is_recognised(base_md):
    bad = []
    for row in _field_rows(base_md) + _register_rows(base_md):
        status = _status_of(row)
        if status not in _STATUSES:
            bad.append((row.get("UI name") or row.get("#"), status))
    assert not bad, f"unrecognised status slugs (a typo reddens here): {bad}"


def test_the_status_vocabulary_table_defines_every_slug_the_matrix_uses(base_md):
    defined = {
        row["Status"].strip().strip("*` ")
        for _h, rows in _table_with(base_md, "Status", "Meaning") for row in rows
    }
    used = {_status_of(r) for r in _field_rows(base_md) + _register_rows(base_md)}
    assert used <= defined, f"used but not defined in § Status vocabulary: {sorted(used - defined)}"
    assert defined == _STATUSES


def test_every_code_bearing_row_names_a_resolving_code_anchor(base_md):
    offenders = []
    for row in _field_rows(base_md):
        if _status_of(row) not in _CODE_BEARING:
            continue
        anchors = _ANCHOR.findall(row["Code anchor"])
        if not anchors:
            offenders.append((row["UI name"], "no anchor"))
            continue
        for anchor in anchors:
            if not _resolves(anchor):
                offenders.append((row["UI name"], anchor))
    assert not offenders, f"phantom 'shipped' rows / dead anchors: {offenders}"


def test_every_code_anchor_ANYWHERE_in_the_matrix_resolves(base_md):
    offenders = [
        anchor for row in _field_rows(base_md)
        for anchor in _ANCHOR.findall(row.get("Code anchor", ""))
        if not _resolves(anchor)
    ]
    assert not offenders, offenders


def test_every_field_row_carries_evidence(base_md):
    empty = [r["UI name"] for r in _field_rows(base_md)
             if r["Evidence"].strip() in ("", "—", "-", "n/a")]
    assert not empty, f"rows with a dropped evidence link: {empty}"


@private_tree.citations
def test_every_repo_path_cited_as_evidence_exists(base_md):
    missing = []
    for row in _field_rows(base_md) + _register_rows(base_md):
        for cell in row.values():
            for path in _REPO_PATH.findall(cell):
                target = path.split("::")[0].rstrip(".,;)`")
                if not (_REPO / target).exists():
                    missing.append(target)
    assert not missing, f"evidence points at paths that do not exist: {sorted(set(missing))}"


def test_scopes_are_NOT_authored_here_and_the_single_source_is_named(base_md):
    """A scope requirement is authored in ``larkdocio.permissions`` and nowhere else."""
    assert "larkdocio.permissions" in base_md
    invented = re.findall(r"`(?:docx|drive|bitable|sheets|contact|im):[a-z_:.]+`", base_md)
    assert not invented, (
        f"/BASE.md is authoring scope strings instead of quoting the registry: {invented}"
    )


# --------------------------------------------------------------------------- #
# AC10 — THE REGISTER                                                          #
# --------------------------------------------------------------------------- #

_REGISTER_COLUMNS = (
    "Limitation / workaround", "Status", "Evidence",
    "Revisit trigger — the observable API change",
)


#: The register's pinned length. **LD-246 born at 11; LD-248 made it 12** — the assembly
#: story discovered that the pinned SDK's typed field-``property`` model silently drops five
#: observed keys (row 12), which is exactly the kind of finding the register exists to hold.
#: **LD-252's live canary made it 13**: the first time the whole surface met a REAL Base it
#: discovered that Button has a **read** identity after all (``(3001, "Button")``, row 13),
#: refuting the offline packs' "no API identity at all".
#: **LD-251's close-out made it 20**: the sweep of LD-246..LD-250 for any consumer-reachable
#: limitation with no row found seven (rows 14-20) — dashboards and workflows (reachable, no
#: specimen), the roles feature gate, the public-share fence, the two read-only share
#: surfaces, and the two deferred Non-Goals (attachment media, link resolution).
#: **LD-256's write-encoder registry made it 24**: the write side brought three limitations a
#: read-only surface never had to state — the single-valued link flag the server does not
#: enforce (22), the one literal ordering a Location cell accepts (23), and person writes being
#: id-only with the other-user name→id resolution deferred (24). *(The story was minted expecting
#: 20 → 23; LD-255 landed row 21 first, so the second lander renumbered and re-pinned — the
#: LD-251/LD-252 rule.)*
#: **LD-259's plan gate made it 26**: the write ENGINE brought the two facts a consumer must
#: not get wrong about a Base write — that there is no server-side compare-and-swap, so
#: ``STALE_BASE`` is a client-side read-compare-write that cannot close the last microsecond
#: (25), and that ``table.revision`` bumps **+1 per batch, not per row** (26), which is what
#: makes the guard a single integer compare regardless of batch size. *(The story was minted
#: expecting 23 → 25; LD-256 landed a third encoder row first, so the real count was 24 and
#: this lander renumbered from it and re-pinned — the LD-251/LD-252 rule, stated in the AC.)*
#: **LD-261's field-authoring allow-list made it 27**: the write side's first *schema*-shaped
#: fact — that an authorable COLUMN and a writable CELL are two different sets, answered by two
#: different constants that cross (27). Row 11 was **extended, not re-authored**: its forward
#: pointer to a constant that had not shipped became that constant's address. *(The count was
#: read at start-of-work — 26 on ``develop`` — rather than taken from the requirement, which is
#: the LD-251/LD-252 rule.)*
#: **LD-263's app-scoped structural ops made it 28** — that an app-scoped op has no usable
#: anchor at all and every plan entry discloses the absence (28), a different fact from row 25's
#: ``table.revision`` one. **LD-262's field authoring made it 29**: that a column's KIND is only
#: converted for a pair a capture carries, every other pair refusing locally with zero transport
#: calls, and cross-storage pairs out entirely (29). *(Read at start-of-work — 28 on ``develop``
#: after LD-263 landed — rather than taken from the requirement; the row was APPENDED at the
#: tail, so nothing was renumbered.)*
#: **LD-264's view lifecycle made it 31** — hidden fields (30) and view sort (31).
#: **LD-265's destructive family made it 32**: that a destructive schema op whose loss cannot be
#: ENUMERATED refuses, and that on a Base the loss is app-scoped rather than table-scoped (32).
#: Row 9 (*DELETE is TRASH, not purge*) was **extended, not re-authored** — it already covered
#: apps, tables and copied apps, and gained the column-delete half and the no-API-undo
#: consequence; rows 10 and 20 are untouched. *(Read at start-of-work — 31 on ``develop`` after
#: LD-264's re-pin — rather than taken from the requirement; the row was APPENDED at the tail,
#: so nothing was renumbered.)*
#: **LD-267's referential facts made it 36** — the four things Lark does to a *reference* that
#: no earlier row said out loud: a two-way link's mirror column is auto-created in another
#: table and named for you (33), that mirror auto-populates with the reverse links with no
#: write to the target table at all (34), deleting a linked RECORD leaves a two-way link
#: maintained and a one-way link DANGLING (35), and deleting a link-target TABLE leaves the
#: source column dangling silently — with the ``table_name`` drop-out shipped as a free
#: column-level reading (36). *(Read at start-of-work — 32 on ``develop`` after LD-265's
#: re-pin — rather than taken from the requirement; the rows were APPENDED at the tail, so
#: nothing was renumbered.)* **The fifth referential fact — ``multiple: false`` is not a
#: cardinality guarantee — was NOT appended:** row 22 already owns it, on the read side and
#: the write side at once, so a second row would be the third definition of one rule. It is
#: **cited** instead, and ``test_row_22_is_the_ONE_OWNER_of_the_cardinality_fact`` pins that
#: the row and the enforcing code still agree.
#: **The person/chat disclosure made it 39** — the three things the identity story had to say
#: out loud and had nowhere to say: that an id-written person cell renders a **full name chip**
#: in the product and the round trip goes through the MODEL rather than the Markdown (37); that
#: the documented email-or-mobile → ``open_id`` route had (it was then believed) never been
#: called here, so its reach was ``uncaptured`` rather than refused (38) — **a claim LD-347
#: later corrected: the route HAD been called, and row 38 is now ``deferred``, recording a
#: measured capability and its own fired revisit trigger**; and that a chat's ids **are**
#: obtainable in
#: band while this library still ships no lister (39). *(Read at start-of-work — 36 on
#: ``develop`` after the referential rows landed — rather than taken from the requirement; the
#: rows were APPENDED at the tail, so nothing was renumbered.)* **Row 24 was NOT rewritten:** it
#: already owns *person writes are id-only, and the other-user name→id resolution is deferred*,
#: so the new rows **cite** it; a second statement of the refusal would be the defect the
#: one-definition rule exists to prevent.
#: **Opt-in link resolution left it at 39** — LD-269 RETRACTED AND REWROTE row 20 **in place**
#: (its own revisit trigger named that decision, and the story settles the display-field policy
#: it asked for), so the count does **not** move for it; its wave partner above is the wave's
#: one appender. *(Read at start-of-work — 39 on ``develop`` after the person/chat rows landed —
#: and re-read at merge, which is the second-lander rule. The rewrite reverses row 20's sentence
#: without changing its subject, so ``_REGISTER_CORRESPONDENCE``'s anchor phrase moves with it;
#: a bare number would have kept resolving and said nothing.)*
#: **Computed-column provenance made it 42** — three things the Lookup/Formula disclosure had
#: to say out loud and nowhere to say them: that a computed cell's typed wrapper carries the
#: **target field's** type and not the column's, and that this is the only place that type can
#: be read from (40); that ``LISTCOMBINE``'s separators are **segments the server sent**, so the
#: join is the empty string and the resulting comma ambiguity is **disclosed rather than escaped
#: around** (41); and that a Lookup is really a constrained Formula, so a specimen's identical
#: rows are correct and a fixture author must not "fix" them (42). *(Read at start-of-work —
#: **39** on ``develop`` after opt-in link resolution landed — rather than taken from the
#: requirement; the rows were APPENDED at the tail, so nothing was renumbered. The arithmetic:
#: 39 + 3 = **42**.)* **Row 12 was EXTENDED, not re-authored, and an extension does not move the
#: count:** its dropped set gains ``filter_info.conditions`` — a key its pin was blind to for as
#: long as the comparison was top-level-only — and its consequence half gains what a consumer
#: can and cannot be told about a Lookup's inputs. **Row 1 (Stage) and rows 4 / 13 (Button) were
#: not touched at all**; the provenance story asserts against them rather than restating them.
#: The number is not a target: it moves only with a row that carries its own evidence and
#: revisit trigger, in the same change.
#: **The Formula cell read made it 43** — the one limitation the whole register was missing a
#: place for: a create the server ACCEPTS whose result is inert. The ld262 rung recorded
#: ``captured`` on ``code:0`` plus a column read-back; LD-280 read the CELLS and found the key
#: absent for every expression a real formula has, so the row states the boundary INSIDE the
#: kind (constants compute, references do not) and the refusal it buys. *(Read at start-of-work
#: — **42** on ``develop`` — and re-read at merge, the second-lander rule; the row was APPENDED
#: at the tail, so nothing was renumbered. The arithmetic: 42 + 1 = **43**.)* No existing row
#: was touched: rows 40-42 keep the READ-side computed story, and this one is about AUTHORING.
#: **The ROW HIERARCHY made it 44** — the register had no place to say that a Lark row tree is
#: not a record concept at all: it is a self-referencing link column named by ONE view property
#: (``property.hierarchy_config.field_id``), the parent edge is an ordinary link-cell value, the
#: record search is hierarchy-blind so depth-first order is rebuilt CLIENT-SIDE, and the two
#: structures Lark accepts at ``code:0`` — a row with two parents, a row that is its own parent —
#: are **disclosed rather than guarded**, because no library can prevent a shape the server takes.
#: *(Read at start-of-work — **43** on ``develop`` — and re-read at merge, the second-lander rule
#: again; the row was APPENDED at the tail, so nothing was renumbered. The arithmetic:
#: 43 + 1 = **44**.)* No existing row was touched; row 43 keeps the Formula-authoring story.
#: **The SEARCH-FILTER TRANSPORT made it 45** — the register could say that a view's grouping is
#: swallowed (row 2) and that a view sort was never probed (row 31), and had nowhere to say that
#: *this library* builds a ``records/search`` filter body and sends it nowhere. No API change
#: caused that gap and none will close it, which is why the row wears ``deferred`` and its
#: revisit trigger is a decision rather than an observation. It exists because the shipped guide
#: had described the gap as a working round trip: the row is the register's copy of the corrected
#: sentence, pinned beside it by ``tests/test_base_read_filter_posture.py``.
#: *(Read at start-of-work — **44** on ``develop`` — and re-read at merge, the second-lander
#: rule again; the row was APPENDED at the tail, so nothing was renumbered, and the register's
#: own prose count moved with it. The arithmetic: 44 + 1 = **45**.)* No existing row was touched.
#: **THE SELECT-OPTION KEYING made it 46** (LD-318) — the register said the view route keys a
#: condition by ``field_id`` (row 45) and had nowhere to say that the same route keys that
#: condition's **VALUE** by ``opt…`` option id, which is the first defect a real consumer hit on
#: this surface: an option NAME passed ``dry_run`` and died at apply on Lark's own *"the option id
#: of 'Single Option' is not found"*. The row carries **both** dialects' measured answer — the
#: view route's id and ``records/search``'s NAME (``1254018`` for an id there), measured rather
#: than inferred from the field key's symmetry — and the fixture route that got them without
#: touching ``POST …/fields``. *(Read at start-of-work — **45** on ``develop`` — and re-read at
#: merge, the second-lander rule again; the row was APPENDED at the tail, so nothing was
#: renumbered, and the register's own prose count moved with it. The arithmetic: 45 + 1 = **46**.)*
#: No existing row was touched; row 45 keeps the transport story.
#: **FIELDS-AT-CREATION made it 47** (LD-336) — the register could say what a schema write sends
#: and what it deliberately does not, and had nowhere to say that the table-create route takes an
#: inline ``fields`` array at all, let alone the three things measuring it turned up: the array's
#: FIRST entry BECOMES the table's primary column (refuting the premise LD-322's spike was minted
#: on), this route authors FEWER kinds than ``POST …/fields`` does (``Rating`` / ``Checkbox`` answer
#: ``1254012`` and create nothing), and ``batch_create`` ACCEPTS a per-table kit and IGNORES it —
#: the swallow proved server-side, which is why that verb refuses the argument instead of sending
#: it. The row also carries the answer to the question this work opened with: the kitted create
#: applied in the same seconds a control ``POST …/fields`` answered ``9499``, so the route really
#: is immune to that outage. The parameter table's ``fields`` / ``default_view_name`` row is
#: **amended and SPLIT** in the same change — ``fields`` becomes *sent, gated* on the single
#: create and *refused locally* on the batch, while ``default_view_name`` stays *not sent* on a
#: row of its own. **LD-344 (Option A) then corrected THAT row's reason** to the measured truth:
#: the key is not withheld as *unprovable* — Lark's ``create_table`` **rejects** a body carrying
#: it (``1254001 WrongRequestBody``, no table created; probe ``ld344-01``), and the view name is
#: itself readable via ``list_views``. The conclusion (*not sent*) is unchanged; only the reason.
#: *(Read at start-of-work — **45** on ``develop`` — and re-read at merge, the second-lander rule
#: again: LD-318's row 46 had landed in between, so the arithmetic is 46 + 1 = **47**. The row was
#: APPENDED at the tail, so nothing was renumbered, and the register's own prose count moved with
#: it.)* No existing register row was touched.
#: **BASE RECORD-LEVEL EDIT HISTORY made it 49** (LD-412) — the register had nowhere to say that
#: a Base record's edit history is not served by the API at all: six ``bitable``-family route
#: spellings answer the gateway's own non-JSON HTTP 404, the drive versions family (LD-409)
#: refuses ``obj_type=bitable``, and the drive statistics family answers a bare ``code:0`` with
#: view counters and nothing about history. The row carries the measured refusal's TRIED and
#: NOT-TRIED lists verbatim (LD-404 § Leg 5) and the nearest served thing —
#: ``automatic_fields=true``'s ``last_modified_by`` / ``last_modified_time``, epoch
#: **milliseconds**, contrasted with the drive versions family's epoch-**second** strings — named
#: together with this library's own PII pin (``automatic_fields`` is ``False``, the Base read spec § D1), so
#: the "nearest served thing" cannot read as a workaround the wheel actually offers. *(Read at
#: start-of-work — **48** on ``develop`` — and re-read at merge, the second-lander rule again; the
#: row was APPENDED at the tail, so nothing was renumbered. The arithmetic: 48 + 1 = **49**.)* No
#: existing register row was touched. No new op, no new endpoint, no new call — this issue is
#: documentation of a measurement already taken (LD-404), not a probe of its own.
_REGISTER_ROWS = 49


def test_the_register_LENGTH_and_NUMBERING_are_pinned_TOGETHER(base_md):
    """The register's length and its numbering, pinned together against :data:`_REGISTER_ROWS`.

    **RENAMED by LD-547 — the name is the whole change; not one assertion moved.** It was
    ``test_the_register_has_EXACTLY_TWENTY_rows``, born when the pin was 20 and never re-cut
    while the pin walked 20 -> 24 -> ... -> 49 above. LD-256's QA saw it on 2026-08-04 and
    recorded it as a Minor it chose not to file (*"keeps a stale name now that the pin is 24 —
    cosmetic, the assertion reads ``_REGISTER_ROWS``"*, `progress/history/`
    `base-write-era-closed.md`); twenty-five rows later the name was wrong by 29. That is the
    2026-08 audit's *name-encoded-integer* class caught in its worse mode: not the tax of
    re-cutting a name per landing, but the name simply rotting because re-cutting it was
    optional. So the name now encodes **no integer at all** and cannot rot again — the pin
    stays where its 166-line dated ledger is, immediately above, which is the one place a
    reader should have to look.
    """
    rows = _register_rows(base_md)
    assert len(rows) == _REGISTER_ROWS, (
        f"the register is pinned at {_REGISTER_ROWS} rows; found {len(rows)} "
        f"(delta {len(rows) - _REGISTER_ROWS:+d}). A new limitation is added WITH its "
        "evidence and its revisit trigger, in the same change, and this count moves with it."
    )
    assert [r["#"] for r in rows] == [str(i) for i in range(1, _REGISTER_ROWS + 1)]


def test_row_12_records_the_SDK_PROPERTY_LOSS_and_says_L1_IS_UNAFFECTED(base_md):
    """LD-248's own finding. The row has to say three things at once, or it misleads: the
    keys really are dropped, no renderer reads one, and the dropped set is *pinned* rather
    than merely observed — the pin is what turns a future renderer-relevant drop into a red
    suite instead of a wrong render."""
    row = [r for r in _register_rows(base_md) if r["#"] == "12"][0]
    text = row["Limitation / workaround"]
    for key in ("back_field_id", "input_type", "formula", "roll_up", "target_field"):
        assert key in text, f"row 12 does not name the dropped key {key}"
    assert "None is read by any renderer" in text
    assert "pinned by a test" in text
    assert "test_base_table.py" in row["Evidence"]


def test_row_12_was_EXTENDED_to_the_NESTED_drop_and_keeps_BOTH_revisit_halves(base_md):
    """The row is the same row — same number, same subject — with a fact its own guard could
    not previously see. Three things have to be true at once or the extension misleads: the
    nested key is NAMED, the blindness that hid it is admitted, and the consequence a consumer
    can actually observe (which table a Lookup rolls up from, and which three inputs it can
    never be told) is stated rather than left in a docstring."""
    row = [r for r in _register_rows(base_md) if r["#"] == "12"][0]
    text = row["Limitation / workaround"]
    assert "filter_info.conditions" in text, "the nested drop is not named"
    assert "top-level" in text.lower(), (
        "the row must say WHY the drop was invisible, or the deepening reads as a tidy-up")
    assert "filter_info.target_table" in text and "unavailable" in text.lower(), (
        "the consumer-visible consequence — one key survives, three do not — is missing")
    assert "six" in text.lower(), "the dropped-set size did not move with the set"
    assert "test_reverting_the_row_12_pin_to_TOP_LEVEL_ONLY_goes_BLIND" in row["Evidence"], (
        "the deliberate-defect check that proves the deepening is not cited as evidence")

    trigger = row["Revisit trigger — the observable API change"]
    assert "shrinking" in trigger and "second assertion" in trigger, (
        "the trigger lost one of its two halves in the extension")


@pytest.mark.parametrize("number,needles", [
    (40, ("target", "19", "20", "uncaptured")),
    (41, ("LISTCOMBINE", "segment", "indistinguishable", "escap")),
    (42, ("roll_up", "constrained formula", "identical", "capture")),
])
def test_the_computed_provenance_rows_SAY_THEIR_WHOLE_FACT(base_md, number, needles):
    """Rows 40-42. Each is a trap someone would otherwise re-discover the hard way, so each
    has to carry the trap AND the reason it is not being worked around."""
    row = [r for r in _register_rows(base_md) if r["#"] == str(number)][0]
    text = row["Limitation / workaround"]
    for needle in needles:
        assert needle.lower() in text.lower(), f"row {number} does not say {needle!r}"
    assert _status_of(row) in _STATUSES
    assert "test_base_computed_provenance.py" in row["Evidence"]
    assert "p1-q0-03" in row["Evidence"], (
        f"row {number} does not cite the specimen it was measured on")


def test_row_41_DISCLOSES_the_comma_ambiguity_and_INVENTS_NO_ESCAPE(base_md):
    """The subtlest half of the whole story: the library is allowed to be unable to fix this,
    and is not allowed to paper over it with an escape Lark never used."""
    row = [r for r in _register_rows(base_md) if r["#"] == "41"][0]
    blob = " ".join(str(v) for v in row.values())
    assert "empty string" in blob.lower() or "joins with **nothing**" in blob.lower() \
        or "joined with nothing" in blob.lower() or "joins with nothing" in blob.lower()
    for invented in ("\\,", "&#44;", "%2C"):
        assert invented not in blob, f"an escape scheme ({invented}) reached the register"


def test_rows_40_to_42_do_NOT_re_author_stage_or_button(base_md):
    """This story asserts against rows 1 / 4 / 13; it writes no rival sentence about either."""
    for number in ("40", "41", "42"):
        row = [r for r in _register_rows(base_md) if r["#"] == number][0]
        blob = " ".join(str(v) for v in row.values())
        assert "Button" not in blob, f"row {number} authors Button wording"
        assert "Stage" not in blob, f"row {number} authors Stage wording"


def test_row_13_records_the_LIVE_BUTTON_READ_IDENTITY_and_does_NOT_reopen_row_4(base_md):
    """LD-252's own finding, and the register's purpose discharged: the canary is the first
    time the whole surface met a real Base, and the surprise is RECORDED rather than absorbed.

    The row has to say four things at once or it misleads: the read identity really is
    ``(3001, "Button")``; the offline claim it refutes was drawn from the *authoring* enums;
    **L1's output is unaffected today** (the key is absent from every record, so the column is
    blank); and the maintainer's will-not-support ruling is **not** reopened by an API fact — which is
    row 4's own two-part trigger, restated here rather than contradicted.
    """
    row = [r for r in _register_rows(base_md) if r["#"] == "13"][0]
    text = row["Limitation / workaround"]
    assert "3001" in text and "Button" in text
    assert "authoring" in text.lower(), (
        "the row must say WHERE the refuted claim came from, or it reads as the packs being "
        "careless rather than as an inference that was too strong")
    assert "unaffected" in text, "the row must state that L1's output does not move"
    assert "row 4" in text and "does not reopen" in text.lower(), (
        "an API fact does not reopen a product ruling — row 4's own trigger says so, and this "
        "row must agree with it instead of quietly superseding it")
    assert _status_of(row) == "will-not-support"
    assert "test_live_base_canary.py" in row["Evidence"], (
        "the finding's evidence IS the gate that found it")
    trigger = row["Revisit trigger — the observable API change"]
    assert "with a value" in trigger and "records/search" in trigger


def test_the_matrixs_BUTTON_row_and_register_row_13_AGREE(base_md):
    """The two places Button is described must not drift apart — that is the whole reason this
    file exists. Both must carry the read identity, and neither may claim a renderer."""
    button = [r for r in _field_rows(base_md) if r["UI name"].strip() == "Button"][0]
    identity = button["API identity (`type` / `ui_type`)"]
    assert "3001" in identity and "READ identity only" in identity
    assert "no authoring identity" in identity.lower()
    assert "no renderer" in button["Render"]
    assert not [p for p in cells.PAIRS if "Button" in p[1]], (
        "/BASE.md says Button has no renderer; the registry must agree")


def test_row_25_states_the_NO_SERVER_SIDE_CAS_fact_QUOTED_from_the_code(base_md):
    """LD-259's first row, and the one this surface most has to get right: the API silently
    ignored the `revision` / `last_modified_time` body keys and applied the write, so
    `STALE_BASE` is a CLIENT-SIDE read-compare-write. The row quotes the shipped constant
    rather than restating it, and it must not read as an atomicity claim."""
    from larkdocio.base.plan import NO_SERVER_SIDE_CAS

    row = [r for r in _register_rows(base_md) if r["#"] == "25"][0]
    text = row["Limitation / workaround"]
    assert NO_SERVER_SIDE_CAS in text, "the row restates the constant instead of quoting it"
    assert "atomic" not in text.lower()
    assert "05-08-staleness.json" in row["Evidence"]
    trigger = row[_REGISTER_COLUMNS[3]]
    assert "revision" in trigger and "code:0" in trigger


def test_row_26_states_the_BATCH_CONTRACT_QUOTED_from_the_code(base_md):
    """The second: `table.revision` is an OP counter. A post-apply expectation of +N per row
    would be wrong against `p0-2-06`, which is why the engine compares one integer."""
    from larkdocio.base.plan import BATCH_BUMPS_ANCHOR_ONCE

    row = [r for r in _register_rows(base_md) if r["#"] == "26"][0]
    assert BATCH_BUMPS_ANCHOR_ONCE in row["Limitation / workaround"]
    assert "p0-2-06-table-revision-granularity.json" in row["Evidence"]


def test_the_register_has_the_FOUR_content_columns(base_md):
    headers = _table_with(base_md, "Limitation / workaround", "Revisit trigger")[0][0]
    assert headers[0] == "#"
    assert tuple(headers[1:]) == _REGISTER_COLUMNS, headers


def test_every_register_cell_is_NON_EMPTY(base_md):
    empty = []
    for row in _register_rows(base_md):
        for column in _REGISTER_COLUMNS:
            if not row[column].strip() or row[column].strip() in ("—", "-", "n/a"):
                empty.append((row["#"], column))
    assert not empty, f"the register has empty cells: {empty}"


def test_every_revisit_trigger_names_an_OBSERVABLE_change(base_md):
    """The column is the point of the register: a trigger must describe something a
    maintainer can go and observe, not a sentiment."""
    for row in _register_rows(base_md):
        trigger = row[_REGISTER_COLUMNS[3]]
        assert len(trigger) > 40, (row["#"], trigger)


def test_row_4_BUTTON_is_worded_as_a_PRODUCT_RULING_not_an_api_limitation(base_md):
    row = [r for r in _register_rows(base_md) if r["#"] == "4"][0]
    assert row["Status"].strip().strip("`") == "will-not-support"
    assert "maintainer ruling" in row["Limitation / workaround"]
    trigger = row[_REGISTER_COLUMNS[3]]
    assert "An API change alone does NOT reopen this row" in trigger
    assert "maintainer re-opens the ruling" in trigger


def test_row_3_COMMENTS_states_the_server_declared_write_refusal(base_md):
    row = [r for r in _register_rows(base_md) if r["#"] == "3"][0]
    assert "[doc, docx]" in row["Limitation / workaround"]
    assert "99992402" in row[_REGISTER_COLUMNS[3]]


def test_row_11_SHIPPED_its_constant_and_it_is_STILL_NOT_in_the_read_registry(base_md):
    """Row 11's forward pointer is discharged — see
    :func:`test_register_row_11_was_EXTENDED_and_its_FORWARD_POINTER_is_gone` for the row's
    new content. What survives from the L1-era assertion is the half that is still load-
    bearing: the allow-list is an authoring constant with a module of its own, and it did
    **not** land inside the read registry."""
    row = [r for r in _register_rows(base_md) if r["#"] == "11"][0]
    assert not re.search(RETIRED_ID, row["Limitation / workaround"])
    assert not hasattr(cells, "FIELD_AUTHORING_ALLOW_LIST"), (
        "the 99992402 allow-list lives in larkdocio.base.field_vocabulary, not in the "
        "read-side renderer registry"
    )


# --------------------------------------------------------------------------- #
# LD-251 AC8 — THE REGISTER'S COMPLETENESS, bidirectionally                    #
#                                                                              #
# The register is where a maintainer looks up "what would reopen this?". A row  #
# elsewhere in the file that refuses, defers or cannot read something, with no  #
# register entry, is exactly the state the maintainer directive was issued against — so #
# the correspondence is mechanized rather than trusted.                        #
# --------------------------------------------------------------------------- #

#: ``needle in the row's FIRST cell -> (the register row that records it, an anchor phrase that
#: register row must still contain)``. A needle rather than a whole cell because a row's own
#: label carries its evidence inline and will be reworded; what must not silently change is
#: *that it is registered*. The **anchor** is why the pair is a pair rather than a bare number:
#: the register is renumbered whenever a row is inserted (LD-252 inserted row 13 and pushed
#: LD-251's seven down to 14-20), and a number alone would go on pointing at *some* row while
#: silently naming the wrong subject. The anchor is matched case-insensitively.
_REGISTER_CORRESPONDENCE = {
    "Flow": (1, "Stage"),                       # Stage — opaque
    "Button": (4, "Button"),                    # a maintainer ruling
    "comments.write": (3, "Commenting a Base"),  # refused by the server
    "dashboards": (14, "Dashboards"),
    "workflows": (15, "Workflows"),
    "roles": (16, "roles"),
    "forms.shared": (17, "public-share write"),
    "permissions/{app}/public": (18, "Share dialog"),
    "permissions/{app}/members": (18, "collaborator list"),
    "attachment media": (19, "Attachment media"),
    # LD-269 RETRACTED row 20's deferral in place — the subject is the same, the sentence is
    # the opposite, so the anchor phrase moves with it (a bare number would keep resolving).
    "link resolution": (20, "link cell is followed"),
    # LD-412 — the measured refusal: no route serves a Base record's edit history.
    "record-level edit history": (49, "record's edit history is not served"),
    # LD-264 — the view-writes matrix. Two point at rows this story ADDED; two point at rows
    # it EXTENDED, which is why extending beats authoring a second statement of the same fact.
    "views.group_info": (2, "Grouping"),
    "views.hidden_fields": (30, "hidden_fields"),
    "views.sort": (31, "view-level persistent SORT"),
    "views.form": (17, "public-share write"),
}

#: Rows deliberately NOT registered, each with the reason. Empty today, and it is meant to stay
#: that way: the exemption exists so a future genuine case is *recorded* rather than smuggled in
#: by widening the map above. Every entry is asserted to still describe a real row.
_REGISTER_EXEMPT: dict = {}

#: Tables that carry a ``Status`` column but are not capability rows: the vocabulary table
#: defines the slugs, and the register is the thing being corresponded *to*.
_NOT_CAPABILITY_TABLES = (("Status", "Meaning"), ("Limitation / workaround",))


def _status_bearing_rows(text):
    """``(first-cell, status)`` for every capability row in the file that declares a status."""
    out = []
    for headers, rows in _tables(text):
        if any(all(col in headers for col in signature)
               for signature in _NOT_CAPABILITY_TABLES):
            continue
        if not any("status" in col.lower() for col in headers):
            continue
        for row in rows:
            out.append((row[headers[0]], _status_of(row)))
    return out


def _register_reference(first_cell):
    """The register rows ``first_cell`` claims, via the needle map."""
    return sorted({
        number for needle, (number, _anchor) in _REGISTER_CORRESPONDENCE.items()
        if needle in first_cell
    })


def test_the_status_bearing_rows_PARSE_and_cover_the_three_tables(base_md):
    """The scope pin: field matrix + § Not in scope + § Comments + § View writes + § the
    guided migration. A table dropping out of this parse would make every completeness
    assertion below vacuous."""
    rows = _status_bearing_rows(base_md)
    # field matrix + Not-in-scope + Comments + LD-264's view-writes matrix + LD-291's ONE
    # guided-column-type-migration row (a `supported` composition, so it needs no register
    # entry — see the completeness test below, which only demands one of a non-supported row).
    # Not-in-scope gained its ninth row at LD-412 (record-level edit history).
    assert len(rows) == 28 + 9 + 2 + 5 + 1, len(rows)
    statuses = {status for _cell, status in rows}
    assert statuses <= _STATUSES, sorted(statuses - _STATUSES)
    # **Both declared Non-Goals have now SHIPPED** — link resolution (LD-269's retraction of
    # row 20) and the attachment media leg (LD-272's, the ladder's second planned retraction) —
    # so no CAPABILITY row defers anything any more. The slug is not retired: it still labels
    # register row 24, the other-user name→id gap, which is where the assertion moved to. A
    # capability row wearing `deferred` again is fine; what must never happen is the slug
    # meaning nothing anywhere, which is what this now checks.
    assert "deferred" not in statuses, (
        "a capability row defers something again — welcome, but the close-out's claim that both "
        "Non-Goals shipped needs re-reading before this line is simply deleted")
    register_statuses = {_status_of(row) for row in _register_rows(base_md)}
    assert "deferred" in register_statuses, (
        "nothing in the document is deferred any more, so the `deferred` slug describes no row "
        "— either a real deferral was dropped, or the vocabulary entry is now dead weight")


def test_EVERY_non_supported_row_has_a_REGISTER_ROW_or_a_reasoned_exemption(base_md):
    """AC8(c). ``supported`` needs nothing — it is not a limitation. Everything else is."""
    numbers = {int(row["#"]) for row in _register_rows(base_md)}
    unregistered = []
    for first_cell, status in _status_bearing_rows(base_md):
        if status == "supported":
            continue
        referenced = _register_reference(first_cell)
        if referenced:
            missing = [n for n in referenced if n not in numbers]
            assert not missing, (first_cell, missing)
            continue
        if any(needle in first_cell for needle in _REGISTER_EXEMPT):
            continue
        unregistered.append((first_cell[:70], status))
    assert not unregistered, (
        f"these rows refuse/defer something and no register row records what would reopen "
        f"them: {unregistered}"
    )


def test_every_exemption_is_REASONED_and_still_describes_a_real_row(base_md):
    cells = [cell for cell, _status in _status_bearing_rows(base_md)]
    for needle, reason in _REGISTER_EXEMPT.items():
        assert len(reason) > 60, f"{needle} is exempt without a usable reason"
        assert any(needle in cell for cell in cells), (
            f"the exemption for {needle!r} describes no row any more — delete it")


def test_the_correspondence_MAP_ITSELF_cannot_go_stale(base_md):
    """Anti-rot the other way: a needle that matches no row, or points at a register row that
    was removed, is a map that has stopped meaning anything."""
    cells = [cell for cell, _status in _status_bearing_rows(base_md)]
    numbers = {int(row["#"]) for row in _register_rows(base_md)}
    for needle, (number, _anchor) in sorted(_REGISTER_CORRESPONDENCE.items()):
        assert any(needle in cell for cell in cells), f"{needle!r} matches no row"
        assert number in numbers, f"{needle!r} points at absent register row {number}"


def test_each_correspondence_NUMBER_points_at_a_row_ABOUT_THAT_THING(base_md):
    """The renumbering guard. A register row inserted in the middle shifts every row below it,
    and a bare number would keep resolving — at the wrong subject. Each mapping therefore pins
    an anchor phrase that its target row must still contain, so a renumbering that forgets to
    move the map reddens here instead of quietly mis-attributing a limitation."""
    label = _REGISTER_COLUMNS[0]
    by_number = {int(row["#"]): row[label] for row in _register_rows(base_md)}
    for needle, (number, anchor) in sorted(_REGISTER_CORRESPONDENCE.items()):
        row = by_number[number]
        assert anchor.lower() in row.lower(), (
            f"{needle!r} points at register row {number}, which is not about {anchor!r} "
            f"any more — the register was renumbered and the map was not: {row[:90]!r}"
        )


def test_DEFECT_a_new_refused_row_with_NO_register_entry_REDDENS(base_md):
    """The proof that AC8(c)'s guard bites: append a plausible new refusal row to § Not in
    scope — a family nobody registered — and the completeness check reports it."""
    defective = base_md.replace(
        "| **link resolution — following a link cell to its target**",
        "| **the plugin family** (`GET …/plugins`) | `code:0` | `refused-by-server` | "
        "invented for this probe | `dev/base-study-2026-08-03.md` |\n"
        "| **link resolution — following a link cell to its target**",
        1,
    )
    rows = _status_bearing_rows(defective)
    unregistered = [
        (cell, status) for cell, status in rows
        if status != "supported" and not _register_reference(cell)
        and not any(n in cell for n in _REGISTER_EXEMPT)
    ]
    assert [c for c, _s in unregistered] == ["**the plugin family** (`GET …/plugins`)"], (
        f"a new unregistered refusal row did not redden the completeness check: {unregistered}")


def test_the_register_rows_LD_251_ADDED_carry_their_own_evidence_and_trigger(base_md):
    """AC8(b): the sweep's own seven rows, held to the same bar as the eleven before them."""
    rows = {int(r["#"]): r for r in _register_rows(base_md)}
    for number in range(13, 20):
        row = rows[number]
        assert _REPO_PATH.search(row["Evidence"]), (number, row["Evidence"])
        assert len(row[_REGISTER_COLUMNS[3]]) > 40, number


def test_the_policy_rows_make_NO_impossibility_claim_about_lark(base_md):
    """AC6/AC8(e) generalized: a `refused-by-policy` or `will-not-support` row states what THIS
    library does. A claim that Lark cannot do it is a different claim, and a false one here."""
    banned = ("impossible", "can never", "cannot ever", "permanently forbidden")
    for row in _register_rows(base_md):
        if _status_of(row) not in {"refused-by-policy", "will-not-support"}:
            continue
        text = " ".join(row.values()).lower()
        for claim in banned:
            assert claim not in text, (row["#"], claim)


def test_row_16_records_the_roles_FEATURE_GATE_in_the_binding_wording(base_md):
    """AC5. Two things have to be true at once, or a consumer is sent to the wrong place: the
    cause is the Base's own advanced-permissions switch, and the API cannot flip it either."""
    row = [r for r in _register_rows(base_md) if r["#"] == "16"][0]
    text = row["Limitation / workaround"]
    assert "is_advanced" in text and "1254301" in text
    assert "1254302" in text, "the doubly-confirmed half (cannot be enabled by API) is missing"
    assert "feature gate" in text.lower() and "not a scope denial" in text.lower()
    assert "owner" in text.lower()
    assert "scope denied" not in text.lower()


def test_default_view_name_row_carries_the_MEASURED_REJECTION_not_unprovability(base_md):
    """LD-344 (Option A truth-correction). ``default_view_name`` STAYS **not sent**, but the
    REASON is corrected to the measured truth: ``create_table`` **REJECTS** a body carrying the
    key — ``1254001 WrongRequestBody``, the table is not created at all — measured twice (raw
    core + pinned SDK) in probe ``ld344-01``. The old *"unprovable / which view a table ends up
    presenting"* clause is GONE: a view's NAME **is** readable (``list_views``, ``total:1``), so
    the parameter was never unprovable — it is simply refused. ``time_zone``'s own *unprovable*
    reason was left untouched here (the courtesy LD-336 paid this very row) — and **LD-463 later
    discharged it on its own terms**, which the tail of this test now checks instead.

    **LD-356 supersedes only the TAIL of the conclusion, and the row must show both halves.**
    The key stays *not sent* and the measured rejection stays cited — what changed is that the
    GOAL now ships, as a create-then-rename **composite** whose ``default_view_id`` comes from
    the create's own reply (probe ``ld356-01``), and whose **non-atomicity** is stated rather
    than implied. A row that announced the composite without keeping the measurement, or kept
    the measurement while still calling the composite a *candidate*, is stale either way."""
    line = next(l for l in base_md.splitlines()
                if l.startswith("| `default_view_name` |"))
    assert "not sent" in line, "the conclusion must stay 'not sent'"
    assert "1254001" in line, "the measured rejection code must be cited"
    lowered = line.lower()
    assert "reject" in lowered, "the reason is now that the server rejects the key"
    assert "unprovable" not in lowered, "the stale 'unprovable' clause must be dropped"
    assert "ld356-01" in lowered, "the composite's own measurement must be cited"
    assert "not atomic" in lowered, (
        "the composite is two calls and the row must say so — the honest consequence is the "
        "part a caller acts on")
    assert "tablecreatedviewnotnamed" in lowered.replace("`", ""), (
        "the typed partial outcome must be named where the doctrine is stated")
    assert "v1.30 candidate" not in lowered, (
        "the deferral is discharged — the composite ships, so calling it a candidate is stale")
    assert "which view a table ended up presenting" not in lowered, (
        "the wrong-question 'which view presents' clause must be dropped")
    tz = next(l for l in base_md.splitlines() if l.startswith("| `time_zone` |"))
    assert "unprovable" in tz.lower(), (
        "time_zone's own *unprovable* reason is PRESERVED — LD-463 ran the test that reason "
        "demanded and replaced only the conclusion; a rationale-free strike is what gets a "
        "settled argument re-litigated")


def test_the_time_zone_row_is_SUPERSEDED_reason_kept_conclusion_replaced(base_md):
    """LD-463. The row's conclusion flips *not sent* → **sent, only when given**, because probe
    ``ld463-01`` ran exactly the test the old reason demanded: ``POST …/apps`` accepts
    ``time_zone`` at ``code:0``, echoes it, and ``GET …/apps/{app}`` reads it back. So the row
    must carry **both halves** — the quoted original reason and the measurement that falsified
    it — plus the consequence a caller acts on: a Base created without the key reports no zone,
    the read side must then assume one, and a date-only value read back one calendar day early.

    A row that announced the new conclusion without keeping the reason would be the
    rationale-free strike the house rules forbid; a row still calling the parameter unprovable
    while the client sends it is stale the other way."""
    line = next(l for l in base_md.splitlines() if l.startswith("| `time_zone` |"))
    lowered = line.lower()
    assert "**sent**" in lowered, "the conclusion is now: sent, only when given"
    assert "only when given" in lowered
    assert "no test could show which zone a base ended up in" in lowered, (
        "the ORIGINAL reason must survive verbatim inside the amendment")
    assert "ld463-01" in lowered, "the measurement that discharged it must be cited"
    assert "16:00 utc" in lowered, (
        "the falsified UTC assumption is the reason this mattered — the measured server day "
        "boundary belongs in the row")
    assert "one calendar day early" in lowered, "the defect the row explains must be named"
    assert "date_zone" in lowered, "the one policy both sides reference must be pointed at"


def test_row_17_is_a_STATEMENT_ABOUT_THIS_LIBRARY_not_about_lark(base_md):
    """AC6's wording calibration, verbatim-bound."""
    row = [r for r in _register_rows(base_md) if r["#"] == "17"][0]
    text = row["Limitation / workaround"]
    assert "larkdocio does not control a Base's shareability" in text
    trigger = row[_REGISTER_COLUMNS[3]]
    assert "no api change alone reopens it" in trigger.lower()


def test_L1_SHIPS_NO_FIELD_AUTHORING_ALLOW_LIST_CONSTANT_ANYWHERE():
    """AC8(d), widened past ``cells``: row 11's forward pointer says the allow-list ships as a
    ``capabilities()`` constant in a LATER story, so L1 must ship none — in the registry either,
    where a constant would be a shipped claim rather than a pointer."""
    import larkdocio
    from larkdocio.base import cells as base_cells

    for module in (base_cells, larkdocio):
        assert not hasattr(module, "FIELD_AUTHORING_ALLOW_LIST"), module.__name__
    payload = larkdocio.capabilities(full=True)
    # TRANSFORMED, NOT WEAKENED (LD-508). The reason is unchanged — L1 must ship no
    # field-authoring allow-list constant, and naming the Base field-authoring refusal code in
    # the registry would BE that constant. What changed is that `99992402` turns out not to be
    # a Base word at all: Lark answers it on the docx image route too, for a `replace_image`
    # PATCH carrying a size, and the truth-knife pass ships that measurement in the docx-write
    # surface. So the search is scoped to the surfaces the claim was ever about — the Base
    # ones — instead of to the whole payload, where it was catching another surface's number.
    base = {name: surface for name, surface in payload["surfaces"].items()
            if name.startswith("base-")}
    assert base, sorted(payload["surfaces"])
    assert "99992402" not in str(base), (
        "the registry names the field-authoring refusal code on a Base surface — that is the "
        "later story's constant, not this level's")


# --------------------------------------------------------------------------- #
# The deliberate-defect tests — proof that the guard actually reddens          #
# --------------------------------------------------------------------------- #

def _without_field_row(text, ui_name):
    return "\n".join(
        line for line in text.splitlines()
        if not (line.strip().startswith(f"| {ui_name} |"))
    )


def test_DEFECT_removing_a_field_row_reddens_the_bidirectional_guard(base_md):
    """Direction one, through the real parse: delete Barcode's row and the pair it
    documented is reported as undocumented."""
    stripped = _without_field_row(base_md, "Barcode")
    assert len(_field_rows(stripped)) == len(_field_rows(base_md)) - 1
    documented = {
        (int(m.group(1)), m.group(2))
        for row in _field_rows(stripped)
        if (m := _IDENTITY.search(row["API identity (`type` / `ui_type`)"]))
    }
    assert (1, "Barcode") in set(cells.PAIRS) - documented


def test_DEFECT_a_phantom_identity_reddens_the_other_direction(base_md):
    documented = {
        (int(m.group(1)), m.group(2))
        for row in _field_rows(base_md)
        if (m := _IDENTITY.search(row["API identity (`type` / `ui_type`)"]))
    } | {(4242, "Wormhole")}
    phantom = [
        p for p in documented
        if cells.renderer_for(*p) is None and p not in _UNREGISTERED_BY_RULING
    ]
    assert phantom == [(4242, "Wormhole")], (
        "the injected phantom must be the ONLY one found — if a real documented identity also "
        f"shows up here it is not exempted and not registered either: {phantom}")


def test_DEFECT_a_dead_code_anchor_reddens_the_status_honesty_guard():
    assert _resolves("larkdocio.base.cells._r_segments")
    assert not _resolves("larkdocio.base.cells._r_does_not_exist")
    assert not _resolves("larkdocio.base.nonexistent_module")


def test_DEFECT_removing_a_register_row_reddens_the_count(base_md):
    """The register's own direction one — through the real parse, not set arithmetic."""
    victim = [r for r in _register_rows(base_md) if r["#"] == "10"][0]
    stripped = "\n".join(
        line for line in base_md.splitlines()
        if not line.strip().startswith("| 10 | **Uploaded media tokens")
    )
    assert victim["#"] == "10", "the probe is stale"
    assert len(_register_rows(stripped)) == _REGISTER_ROWS - 1, (
        "removing a row did not redden the count")


def test_DEFECT_emptying_a_REVISIT_TRIGGER_cell_reddens_the_guard(base_md):
    """The register's whole point. An emptied trigger is a silent regression — the row
    still looks complete, and the maintainer who needed it never learns what to watch."""
    lines = base_md.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("| 5 | **Email — the API performs NO"):
            parts = line.rstrip().rstrip("|").split("|")
            parts[-1] = "  "                      # empty the revisit trigger
            lines[i] = "|".join(parts) + "|"
            break
    else:
        raise AssertionError("register row 5 not found — the probe is stale")
    defective = "\n".join(lines)
    row = [r for r in _register_rows(defective) if r["#"] == "5"][0]
    assert not row[_REGISTER_COLUMNS[3]].strip(), "the probe did not actually empty the cell"
    empty = [
        (r["#"], c) for r in _register_rows(defective) for c in _REGISTER_COLUMNS
        if not r[c].strip()
    ]
    assert empty == [("5", _REGISTER_COLUMNS[3])]


def test_DEFECT_an_unrecognised_status_slug_reddens():
    assert "supportd" not in _STATUSES and "supported" in _STATUSES


# --------------------------------------------------------------------------- #
# LD-247 AC11 — THE CLIENT / OPERATIONS TABLE ↔ the op registry                 #
# --------------------------------------------------------------------------- #

_OPERATION_COLUMNS = ("Operation", "Endpoint", "Verb", "`mutates`", "Paged",
                      "Code anchor", "Evidence")

#: The WRITE operations table's columns. Identical to the read table's but for the fifth,
#: which is what lets each be selected unambiguously — a batch op is not a paged one.
_WRITE_OPERATION_COLUMNS = ("Operation", "Endpoint", "Verb", "`mutates`", "Batch",
                            "Code anchor", "Evidence")


def _operation_rows(text):
    tables = _table_with(text, "Operation", "`mutates`", "Paged")
    assert len(tables) == 1, "the read-operations table must be exactly one table"
    return tables[0][1]


def _write_operation_rows(text):
    tables = _table_with(text, "Operation", "`mutates`", "Batch")
    assert len(tables) == 1, "the write-operations table must be exactly one table"
    return tables[0][1]


def _op_name(row):
    """The op name in the first cell — the row may annotate it (`… — **the pinned read**`)."""
    match = re.search(r"`([a-z_]+)`", row["Operation"])
    assert match, row["Operation"]
    return match.group(1)


def _resolves_deep(anchor):
    """Resolve ``pkg.mod.Class.attr`` — the plain ``_resolves`` stops at module level."""
    parts = anchor.split(".")
    for split in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:split]))
        except ImportError:
            continue
        for name in parts[split:]:
            if not hasattr(obj, name):
                return False
            obj = getattr(obj, name)
        return True
    return False


def test_the_operations_table_has_the_seven_declared_columns(base_md):
    assert tuple(_table_with(base_md, "Operation", "`mutates`", "Paged")[0][0]) == \
        _OPERATION_COLUMNS


def test_every_registered_op_has_exactly_one_row_and_vice_versa(base_md):
    from larkdocio.base import ops

    documented = [_op_name(row) for row in _operation_rows(base_md)]
    assert len(documented) == len(set(documented)), f"a duplicated op row: {documented}"
    assert set(documented) == {desc.name for desc in ops.OPS}, (
        "the operations table and larkdocio.base.ops.OPS disagree — touch the surface, "
        f"update the matrix. Documented {sorted(documented)}")


def test_every_operation_row_states_the_MUTATES_VALUE_THE_REGISTRY_HAS(base_md):
    from larkdocio.base import ops

    for row in _operation_rows(base_md):
        descriptor = ops.op(_op_name(row))
        documented = row["`mutates`"].strip().strip("`*").lower()
        assert documented in ("true", "false"), (descriptor.name, documented)
        assert (documented == "true") is descriptor.mutates, (
            f"/BASE.md says {descriptor.name} mutates={documented}; the registry says "
            f"{descriptor.mutates}")


def test_every_operation_row_states_THE_ENDPOINT_AND_VERB_THE_SDK_ACTUALLY_CALLS(base_md):
    """Not checked against the descriptor's own strings — against the **SDK request class**,
    so the doc and the descriptor cannot agree with each other and both be wrong."""
    from larkdocio.base import ops

    for row in _operation_rows(base_md):
        descriptor = ops.op(_op_name(row))
        built = descriptor.request_cls.builder().build()
        assert row["Endpoint"].strip().strip("`") == built.uri, descriptor.name
        assert row["Verb"].strip().strip("`") == built.http_method.name, descriptor.name


def test_every_operation_row_names_a_RESOLVING_code_anchor(base_md):
    offenders = []
    for row in _operation_rows(base_md):
        anchors = _ANCHOR.findall(row["Code anchor"])
        if not anchors:
            offenders.append((_op_name(row), "no anchor"))
        offenders += [(_op_name(row), a) for a in anchors if not _resolves_deep(a)]
    assert not offenders, f"dead anchors in the operations table: {offenders}"


@private_tree.citations
def test_every_operation_row_carries_evidence_that_EXISTS(base_md):
    missing = []
    for row in _operation_rows(base_md):
        assert row["Evidence"].strip() not in ("", "—", "-", "n/a"), _op_name(row)
        for path in _REPO_PATH.findall(row["Evidence"]):
            target = path.split("::")[0].rstrip(".,;)`")
            if not (_REPO / target).exists():
                missing.append(target)
    assert not missing, f"the operations table cites paths that do not exist: {missing}"


def test_DEFECT_a_WRONG_mutates_value_in_the_doc_reddens(base_md):
    """The guard's own falsification: flip the pinned POST read to `true` — the exact drift a
    verb-derived flag would introduce — and the cross-check must catch it."""
    from larkdocio.base import ops

    defective = base_md.replace(
        "| `search_records` — **the pinned read** |", "| `search_records` |", 1)
    row = [r for r in _operation_rows(defective) if _op_name(r) == "search_records"][0]
    flipped = dict(row, **{"`mutates`": "`true`"})
    documented = flipped["`mutates`"].strip().strip("`*").lower()
    assert (documented == "true") is not ops.op("search_records").mutates, (
        "the mutates cross-check would not have noticed the flip")


# --------------------------------------------------------------------------- #
# LD-248 — § Assembly & the public read surface                                #
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# LD-632 — the parse must not DROP a row the document writes.                   #
# --------------------------------------------------------------------------- #
#
# ``base_md.tables()`` used to split a row with a naive ``strip("|").split("|")``, so a cell
# carrying a literal ``\|`` (which GFM requires, and which /BASE.md's own **GFM safety** row
# is *about*) yielded one cell too many and the row was silently discarded by the
# header-length check. The § Rendering-rule table has ten rows in the document and the parse
# returned nine — so the tenth row's anchor and evidence were never resolved by the guard
# below, and could have rotted to a dead anchor with nothing to say so.
#
# Two arms, because there are two ways to be wrong: a count that disagrees with the document,
# and a row that disappeared without anyone hearing about it.


def _document_row_count(base_md, header_fragment):
    """How many data rows the DOCUMENT writes for the table whose header names
    ``header_fragment`` — counted off the raw lines, independently of the parse under test."""
    lines = base_md.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not (stripped.startswith("|") and header_fragment in stripped):
            continue
        separator = lines[index + 1].strip()
        if not set(separator.strip("|")) <= set("-: |"):
            continue
        count, cursor = 0, index + 2
        while cursor < len(lines) and lines[cursor].strip().startswith("|"):
            count += 1
            cursor += 1
        return count
    raise AssertionError(f"no table header in BASE.md names {header_fragment!r}")


def test_the_parse_KEEPS_a_row_WHOSE_CELL_CARRIES_AN_ESCAPED_PIPE():
    r"""LD-632 AC7's watched red, kept as a permanent arm: the planted ``\|`` fixture.

    This is the minimal reproduction of the defect. Under the naive
    ``stripped.strip("|").split("|")`` the third line yields THREE cells against TWO headers
    and the row is discarded, so this asserted a row set of one and got zero.
    """
    fixture = (
        "| rule | emits |\n"
        "|---|---|\n"
        "| plain | nothing special |\n"
        r"| escaped | a `\|` inside one cell |"
        "\n"
    )
    parsed = _tables(fixture)
    assert len(parsed) == 1, f"one table expected, got {len(parsed)}"
    headers, rows = parsed[0]
    assert headers == ["rule", "emits"]
    assert [row["rule"] for row in rows] == ["plain", "escaped"], (
        "the row whose cell carries a literal \\| was dropped — the escape was read as a "
        "cell boundary, which is exactly the LD-632 defect"
    )
    assert rows[1]["emits"] == r"a `\|` inside one cell", (
        "the cell text must stay exactly what the document says — the parse does not unescape"
    )


def test_the_rendering_table_parse_DROPS_NO_ROW_THE_DOCUMENT_WRITES(base_md):
    """LD-632 AC1 — the row-count arm. Parsed rows == rows on disk, for the one table whose
    own subject is the escape that used to break the parse."""
    on_disk = _document_row_count(base_md, "Rendering rule")
    parsed = _rendering_rows(base_md)
    assert len(parsed) == on_disk, (
        f"/BASE.md writes {on_disk} rendering rows and the parse returns {len(parsed)} — a "
        f"dropped row is a row this guard never checks. Missing: "
        f"{on_disk - len(parsed)}"
    )
    assert any("GFM safety" in row["Rendering rule"] for row in parsed), (
        "the **GFM safety** row (BASE.md's escaped-pipe row, and the one the naive splitter "
        "used to drop) is not in the parsed set"
    )


def test_NO_table_row_anywhere_in_BASE_md_is_silently_dropped(base_md):
    """LD-632 AC1 — the whole-document arm. A ragged row is a real defect in the document
    (or in the parse); either way it must be LOUD, because the failure mode being fixed here
    is a drop nobody could see."""
    import guard_kit

    ragged = guard_kit.md_ragged_rows(base_md)
    assert ragged == [], (
        f"/BASE.md has table rows whose cell count does not match their header count, so the "
        f"parse drops them and every guard over those tables is vacuous for them: {ragged}"
    )


def _rendering_rows(base_md):
    tables = _table_with(base_md, "Rendering rule", "What it emits")
    assert len(tables) == 1, "the rendering table must be exactly one table"
    return tables[0][1]


def _surface_rows(base_md):
    tables = _table_with(base_md, "Entry point", "Returns", "Takes")
    assert len(tables) == 1, "the public-surface table must be exactly one table"
    return tables[0][1]


def test_every_rendering_row_names_a_RESOLVING_anchor_and_carries_evidence(base_md):
    for row in _rendering_rows(base_md):
        anchors = _ANCHOR.findall(row["Code anchor"])
        assert anchors, f"rendering row has no code anchor: {row['Rendering rule']}"
        for anchor in anchors:
            assert _resolves(anchor), f"{anchor} does not resolve"
        assert row["Evidence"].strip() not in ("", "—", "-", "n/a")


def test_every_documented_entry_point_EXISTS_and_is_re_exported(base_md):
    """The surface table is the consumer-facing half: a row naming a function nobody can
    import is worse than no row, so both the anchor and the package re-export are checked."""
    from larkdocio import base as base_pkg

    documented = set()
    for row in _surface_rows(base_md):
        anchors = _ANCHOR.findall(row["Code anchor"])
        assert len(anchors) == 1, row
        assert _resolves(anchors[0]), f"{anchors[0]} does not resolve"
        name = anchors[0].rpartition(".")[2]
        documented.add(name)
        assert hasattr(base_pkg, name), f"{name} is documented but not re-exported"
    assert {"read_base", "read_base_markdown"} <= documented, (
        "both entry points — the Markdown one and the structured one — must be documented")


def test_the_EMPTY_MARKERS_quoted_in_the_doc_are_the_BYTES_THE_CODE_EMITS(base_md):
    """A marker is a documented output shape, so the doc quoting a *near*-miss of it is a
    lie a consumer can be bitten by. Checked against the constants, not by eye."""
    from larkdocio.base import table as base_table

    for marker in (base_table.EMPTY_TABLE_MARKER, base_table.EMPTY_BASE_MARKER):
        assert marker in base_md, f"BASE.md does not quote the marker verbatim: {marker!r}"


def test_the_doc_states_the_view_is_not_a_projection_and_names_field_names(base_md):
    """AC3's documentation half, guarded here as well as in the story's own tests: the
    negative must be stated, and the one genuine server-side projection named beside it."""
    assert "not a column selector" in base_md
    assert "`field_names` is the only genuine server-side projection" in base_md


def test_DEFECT_a_rendering_row_pointing_at_dead_code_reddens():
    assert _resolves("larkdocio.base.table.render_base")
    assert not _resolves("larkdocio.base.table.render_the_whole_internet")


# --------------------------------------------------------------------------- #
# LD-255 — THE WRITE OPERATIONS TABLE ↔ the write op registry                    #
#                                                                              #
# The same bidirectional standard as the read table above, against the SECOND    #
# registry. Two tables rather than one is the design, not an accident: the read  #
# registry's `read_only()` is a shipped claim, and a mutating row appended to it #
# would falsify that claim without the read surface changing at all.            #
# --------------------------------------------------------------------------- #

def test_the_write_operations_table_has_the_seven_declared_columns(base_md):
    assert tuple(_table_with(base_md, "Operation", "`mutates`", "Batch")[0][0]) == \
        _WRITE_OPERATION_COLUMNS


def test_every_registered_WRITE_op_has_exactly_one_row_and_vice_versa(base_md):
    from larkdocio.base import write_ops

    documented = [_op_name(row) for row in _write_operation_rows(base_md)]
    assert len(documented) == len(set(documented)), f"a duplicated op row: {documented}"
    assert set(documented) == {desc.name for desc in write_ops.WRITE_OPS}, (
        "the write-operations table and larkdocio.base.write_ops.WRITE_OPS disagree — touch "
        f"the surface, update the matrix. Documented {sorted(documented)}")


def test_every_WRITE_row_states_the_MUTATES_VALUE_THE_REGISTRY_HAS(base_md):
    from larkdocio.base import write_ops

    for row in _write_operation_rows(base_md):
        descriptor = write_ops.write_op(_op_name(row))
        documented = row["`mutates`"].strip().strip("`*").lower()
        assert documented in ("true", "false"), (descriptor.name, documented)
        assert (documented == "true") is descriptor.mutates, (
            f"/BASE.md says {descriptor.name} mutates={documented}; the registry says "
            f"{descriptor.mutates}")


def test_every_WRITE_row_states_THE_ENDPOINT_AND_VERB_THE_SDK_ACTUALLY_CALLS(base_md):
    """Checked against the **SDK request class**, so the doc and the descriptor cannot agree
    with each other and both be wrong."""
    from larkdocio.base import write_ops

    for row in _write_operation_rows(base_md):
        descriptor = write_ops.write_op(_op_name(row))
        built = descriptor.request_cls.builder().build()
        assert row["Endpoint"].strip().strip("`") == built.uri, descriptor.name
        assert row["Verb"].strip().strip("`") == built.http_method.name, descriptor.name


def test_every_WRITE_row_states_the_BATCH_FLAG_THE_REGISTRY_HAS(base_md):
    from larkdocio.base import write_ops

    for row in _write_operation_rows(base_md):
        descriptor = write_ops.write_op(_op_name(row))
        documented = row["Batch"].strip().lower()
        assert documented in ("yes", "no"), (descriptor.name, documented)
        assert (documented == "yes") is descriptor.batch, descriptor.name


def test_every_WRITE_row_names_a_RESOLVING_code_anchor(base_md):
    offenders = []
    for row in _write_operation_rows(base_md):
        anchors = _ANCHOR.findall(row["Code anchor"])
        if not anchors:
            offenders.append((_op_name(row), "no anchor"))
        offenders += [(_op_name(row), a) for a in anchors if not _resolves_deep(a)]
    assert not offenders, f"dead anchors in the write-operations table: {offenders}"


@private_tree.citations
def test_every_WRITE_row_carries_evidence_that_EXISTS(base_md):
    missing = []
    for row in _write_operation_rows(base_md):
        assert row["Evidence"].strip() not in ("", "—", "-", "n/a"), _op_name(row)
        for path in _REPO_PATH.findall(row["Evidence"]):
            target = path.split("::")[0].rstrip(".,;)`")
            if not (_REPO / target).exists():
                missing.append(target)
    assert not missing, f"the write-operations table cites paths that do not exist: {missing}"


def test_the_TWO_operation_tables_are_DISJOINT_and_the_read_one_still_mutates_nothing(base_md):
    """The whole point of the split, asserted on the DOCUMENT as well as on the code: no op
    appears in both tables, and every documented read row still says `false`."""
    read_names = {_op_name(r) for r in _operation_rows(base_md)}
    write_names = {_op_name(r) for r in _write_operation_rows(base_md)}
    assert not (read_names & write_names)
    for row in _operation_rows(base_md):
        assert row["`mutates`"].strip().strip("`*").lower() == "false", _op_name(row)
    for row in _write_operation_rows(base_md):
        assert row["`mutates`"].strip().strip("`*").lower() == "true", _op_name(row)


def test_the_NON_WRITABLE_PAIR_SET_documented_here_is_the_ONE_the_code_exports(base_md):
    """The doc names the eight computed / opaque types in prose; the constant is the source of
    truth. A doc that named seven, or a ninth, would be describing a different library."""
    from larkdocio.base import write_vocabulary

    tail = base_md.split("**Non-writable field types")[1].split("**Error taxonomy")[0]
    count, section = tail.split(".**", 1)
    assert count.strip() == f"({len(write_vocabulary.NON_WRITABLE_PAIRS)})", count
    for type_id, ui_name in write_vocabulary.NON_WRITABLE_PAIRS:
        assert ui_name in section, ui_name
        assert f"({type_id})" in section, (ui_name, type_id)
    stated = re.findall(r"\((\d{1,4})\)", section)
    assert {int(n) for n in stated} == {t for t, _ui in write_vocabulary.NON_WRITABLE_PAIRS}


# --------------------------------------------------------------------------- #
# LD-256 AC9 — THE WRITE COLUMN, bidirectionally against the encoder registry  #
#                                                                              #
# The read half of this file has been guarded against the renderer registry    #
# since LD-246. The write half is guarded the same way and for a sharper        #
# reason: a wrong READ shape renders visibly wrong, while a wrong WRITE shape   #
# answers `code:0` and stores nothing. So the doc's write cell must name the    #
# encoder the code dispatches on AND the capture the shape was taken from.     #
# --------------------------------------------------------------------------- #

_WRITE_COLUMN = "Write"


def _write_cell(row):
    assert _WRITE_COLUMN in row, f"the field matrix has no {_WRITE_COLUMN!r} column: {row}"
    return row[_WRITE_COLUMN]


def _write_status(row):
    cell = _write_cell(row)
    for token in re.findall(r"`([a-z-]+)`", cell):
        if token in _STATUSES:
            return token
    raise AssertionError(f"no recognised write status in {cell[:80]!r}")


def _documented_write(base_md):
    """``{(type, ui_type): row}`` for every field row, keyed on its API identity."""
    out = {}
    for row in _field_rows(base_md):
        match = _IDENTITY.search(row["API identity (`type` / `ui_type`)"])
        if match:
            out[(int(match.group(1)), match.group(2))] = row
    return out


def test_every_ENCODER_PAIR_has_a_supported_write_cell_AND_VICE_VERSA(base_md):
    """The bidirectional half. An encoder with no `supported` write row is an undocumented
    capability; a `supported` write row with no encoder is a promise the code does not keep."""
    from larkdocio.base import write_cells

    documented = {
        pair for pair, row in _documented_write(base_md).items()
        if _write_status(row) == "supported"
    }
    assert documented == set(write_cells.WRITABLE_PAIRS), (
        f"only in /BASE.md: {sorted(documented - set(write_cells.WRITABLE_PAIRS))}; "
        f"only in the encoder registry: {sorted(set(write_cells.WRITABLE_PAIRS) - documented)}"
    )
    assert len(documented) == 19


def test_every_write_cell_uses_a_RECOGNISED_status_slug(base_md):
    for pair, row in _documented_write(base_md).items():
        assert _write_status(row) in _STATUSES, pair


def test_every_supported_write_cell_NAMES_ITS_ENCODER_and_it_resolves(base_md):
    from larkdocio.base import write_cells

    for pair, row in _documented_write(base_md).items():
        if _write_status(row) != "supported":
            continue
        anchors = [a for a in _ANCHOR.findall(_write_cell(row)) if ".write_cells." in a]
        assert len(anchors) == 1, (pair, anchors)
        assert _resolves(anchors[0]), (pair, anchors[0])
        assert anchors[0].rpartition(".")[2] == write_cells.encoder_for(*pair).__name__, (
            f"/BASE.md names a different encoder for {pair} than the registry dispatches on")


@private_tree.citations
def test_every_supported_write_cell_NAMES_THE_CAPTURE_THE_CODE_IS_ANCHORED_TO(base_md):
    """AC1's *"not derived from the packs, a filename"*, held on the doc side too — and held
    against `write_cells.CAPTURE_ANCHORS` rather than against a second hand-kept list."""
    from larkdocio.base import write_cells
    from larkdocio.common.citations import dev_repo_paths

    for pair, row in _documented_write(base_md).items():
        if _write_status(row) != "supported":
            continue
        # The shipped anchor wears its "in the dev repo" label, because a consumer reads it;
        # the path inside it is what has to resolve on disk and appear in the matrix.
        anchor = write_cells.capture_anchor(*pair)
        assert anchor, pair
        (expected,) = dev_repo_paths(anchor)
        assert (_REPO / expected).exists(), (pair, anchor)
        assert expected in _write_cell(row), (
            f"/BASE.md's write cell for {pair} does not cite {expected}")


def test_the_NON_WRITABLE_write_cells_QUOTE_THE_SHARED_SET_and_re_list_nothing(base_md):
    from larkdocio.base.write_vocabulary import NON_WRITABLE_PAIRS

    documented = _documented_write(base_md)
    for pair in NON_WRITABLE_PAIRS:
        cell = _write_cell(documented[pair])
        assert _write_status(documented[pair]) == "refused-by-server", pair
        assert "write_vocabulary.NON_WRITABLE_PAIRS" in cell, pair
        assert "locally" in cell, pair


def test_the_BUTTON_ROWS_WRITE_CELL_ships_NO_ENCODER_AND_NO_BESPOKE_REFUSAL(base_md):
    """AC7b's doc-side twin. The row must say the generic refusal covers it — a bespoke write
    refusal would be the library re-opening a ruling an API fact does not reopen."""
    from larkdocio.base import write_cells

    row = [r for r in _field_rows(base_md) if r["UI name"].strip() == "Button"][0]
    cell = _write_cell(row)
    assert _write_status(row) == "will-not-support"
    assert "no encoder" in cell and "no bespoke refusal" in cell
    assert not _ANCHOR.findall(cell)
    assert write_cells.encoder_for(3001, "Button") is None


def test_DEFECT_a_write_cell_naming_the_WRONG_ENCODER_reddens(base_md):
    """The guard has to bite on the mistake it exists for: a plausible-looking encoder name in
    the wrong row. Swapping the location encoder onto the email row must not pass."""
    from larkdocio.base import write_cells

    defective = base_md.replace(
        "`larkdocio.base.write_cells._e_email`",
        "`larkdocio.base.write_cells._e_location`", 1)
    assert defective != base_md
    row = _documented_write(defective)[(1, "Email")]
    named = [a for a in _ANCHOR.findall(_write_cell(row)) if ".write_cells." in a][0]
    assert named.rpartition(".")[2] != write_cells.encoder_for(1, "Email").__name__


def test_the_three_LD_256_register_rows_carry_their_own_evidence_and_trigger(base_md):
    rows = {int(r["#"]): r for r in _register_rows(base_md)}
    for number, needle in ((22, "multiple"), (23, "Location"), (24, "ID-ONLY")):
        row = rows[number]
        assert needle in row["Limitation / workaround"], (number, needle)
        assert _REPO_PATH.search(row["Evidence"]), (number, row["Evidence"])
        assert len(row[_REGISTER_COLUMNS[3]]) > 40, number


def test_register_row_24_CITES_the_deferred_mandate_and_INVENTS_NO_RESOLUTION_PATH(base_md):
    """D1‴ = (b): the other-user name→id gap is deferred for a comprehensive-solution
    investigation — *"no roster-table hack, no abandonment"*. The row cites that mandate rather
    than duplicating it, and must not describe a shortcut this library does not ship."""
    row = [r for r in _register_rows(base_md) if r["#"] == "24"][0]
    text = row["Limitation / workaround"]
    assert "dev/downtime-queue.md" in text
    assert "larkdocio.contacts.resolve_user" in text
    assert "no roster" in text.lower() and "best-effort match" in text.lower()


def test_register_rows_1_and_6_GAINED_their_write_halves_rather_than_being_duplicated(base_md):
    """AC9's *extend, do not re-author*: the opaque type and the email asymmetry were already
    registered on the read side; the write side belongs in the same rows, not in new ones."""
    rows = {int(r["#"]): r for r in _register_rows(base_md)}
    stage = rows[1]["Limitation / workaround"]
    assert "table.revision" in stage and "refuses a Stage write locally" in stage
    email = rows[6]["Limitation / workaround"]
    assert "EMAIL_IS_NOT_ROUND_TRIPPABLE" in email and "1254060" in email
    labels = [r["Limitation / workaround"] for r in _register_rows(base_md)]
    assert sum(1 for label in labels if "Stage (type 24" in label) == 1
    assert sum(1 for label in labels if label.startswith("**Email")) == 2, (
        "rows 5 and 6 are the two Email rows the register already had; a third would be a "
        "re-authored row rather than an extended one")


def test_register_row_11_was_EXTENDED_and_its_FORWARD_POINTER_is_gone(base_md):
    """The allow-list shipped, so the row that promised it must now give its address. The
    forward pointer is the thing being retired: a row that still says "will ship" after the
    thing shipped is the register lying about the code."""
    row = [r for r in _register_rows(base_md) if r["#"] == "11"][0]
    text = row["Limitation / workaround"]
    assert "Forward pointer" not in text and "ships as a" not in text
    assert "larkdocio.base.field_vocabulary" in text
    assert "check_authorable" in text and "zero transport calls" in text
    assert "src/larkdocio/base/field_vocabulary.py" in row["Evidence"]
    assert "API-drift alarm" in row[_REGISTER_COLUMNS[3]], (
        "the snapshot's revisit trigger is what stops a drifted enum being read as a caller "
        "error")


def test_register_row_27_pins_the_AUTHORABLE_vs_WRITABLE_quadrants(base_md):
    """The new row, and the only new row this change adds. It has to name both constants,
    all three quadrants, and Email as the single writable-but-unauthorable member."""
    from larkdocio.base import field_vocabulary as fv

    row = [r for r in _register_rows(base_md) if r["#"] == "27"][0]
    text = row["Limitation / workaround"]
    assert "field_vocabulary" in text and "NON_WRITABLE_PAIRS" in text
    for member in ("Formula", "AutoNumber", "CreatedTime", "ModifiedTime", "CreatedUser",
                   "ModifiedUser", "Lookup", "Stage", "Email"):
        assert member in text, member
    assert "only** member" in text or "the **only** member" in text
    assert len(fv.CELLS_WRITABLE_BUT_FIELD_UNAUTHORABLE) == 1, (
        "the row claims exactly one member; the derivation must still agree")
    assert _REPO_PATH.search(row["Evidence"])
    assert len(row[_REGISTER_COLUMNS[3]]) > 40


# --------------------------------------------------------------------------- #
# LD-308 — the BASE.md guard seam: ONE parser, ONE repo-root derivation        #
# --------------------------------------------------------------------------- #
# The register parser used to live *here*, in a ``test_*`` module, and three other
# guards imported it across pytest's rootdir-relative module namespace. It now lives in
# ``tests/base_md.py`` beside ``guard_kit`` — a helper module pytest does not collect —
# and the BASE.md readers take their repo root from ``guard_kit.REPO_ROOT`` instead of
# each re-answering "where am I?".

#: The BASE.md readers that take their repo root from ``guard_kit`` (LD-308 B3).
_SEAM_ADOPTERS = frozenset({
    "test_base_comments_read.py", "test_base_computed_provenance.py",
    "test_base_copy_folder_route_scope.py",
    "test_base_front_door.py", "test_base_md_matrix.py",
    "test_base_media_permalink.py", "test_base_mention_segment_link.py",
    "test_base_person_chat_addressability.py", "test_base_raw_values.py",
    "test_base_referential.py", "test_base_relational_close_out.py",
    "test_base_schema_client.py", "test_base_schema_destructive.py",
    "test_base_schema_matrix.py", "test_base_schema_views.py",
    "test_base_schema_write_front_door.py", "test_base_shape_docs.py",
    "test_base_surface_claim_is_gone.py",
    "test_base_table.py", "test_base_table_delete_link_semantics.py",
    "test_base_view_hidden_fields.py",
    "test_base_write_front_door.py",
    "test_embedded_base_deep_read.py", "test_live_base_canary_offline.py",
    "test_live_base_disposable_harness_offline.py", "test_live_base_schema_arm_offline.py",
})

#: BASE.md readers deliberately NOT migrated — each with the reason it stays put (LD-308).
_SEAM_EXCLUSIONS = {
    "guard_kit.py": "the seam itself — REPO_ROOT is authored here",
    "base_md.py": "the seam itself — it imports REPO_ROOT from guard_kit",
    "test_base_media.py": (
        "owned by LD-306 in the same wave; migrating it here would conflict with that "
        "leg's edits. Deferred to a later sweep."),
    "test_base_plan_gate.py": (
        "derives its root from the INSTALLED package (larkdocio.__file__.parents[2]), not "
        "from tests/ — swapping in REPO_ROOT would change which tree the guard reads."),
}

#: The names LD-308 moved out of this module. No test module may import them from here.
_MOVED_TO_BASE_MD = frozenset({"_tables", "_table_with", "_field_rows", "_register_rows"})

#: A hand-rolled repo-root derivation — what ``guard_kit.REPO_ROOT`` replaces.
_ROOT_DERIVATION = re.compile(
    r"Path\(__file__\)\.resolve\(\)\.(?:parent\.parent\b|parents\[1\])")

#: A path join onto the shipped matrix: ``… / "BASE.md"``.
_BASE_MD_JOIN = re.compile(r"/\s*\"BASE\.md\"")

#: The standing carve-outs (08-03 audit § T2b-ii) — deliberately fence-blind / non-fence-aware
#: slicers that must NOT be migrated onto the seam.
_SEAM_CARVE_OUTS = ("test_discovery_truth.py", "front_door.py", "test_front_door_doctrine.py")

_TESTS_DIR = _REPO / "tests"


def _test_sources():
    return {p.name: p.read_text(encoding="utf-8")
            for p in sorted(_TESTS_DIR.rglob("*.py"))}  # LD-654: recursive population


def test_the_register_parser_lives_in_a_NON_TEST_module_beside_guard_kit(base_md):
    """B1/B6 — ``tests/base_md.py`` owns the parser, and this module uses *that* definition."""
    import base_md as base_md_module

    assert Path(base_md_module.__file__).name == "base_md.py"
    assert _register_rows is base_md_module.register_rows
    assert len(base_md_module.register_rows(base_md)) == _REGISTER_ROWS
    assert not [n for n in dir(base_md_module) if n.startswith("test_")], (
        "tests/base_md.py is a helper module — it must collect no tests")


def test_NO_test_module_imports_the_moved_parsers_from_another_test_module():
    """B2 — the cross-``test_*``-module import of the register parser is gone."""
    offenders = {}
    for name, source in _test_sources().items():
        if name in _SEAM_EXCLUSIONS:
            continue
        for imported in re.findall(r"from test_base_md_matrix import ([^\n]+)", source):
            moved = {n.strip().split(" as ")[0] for n in imported.split(",")} & _MOVED_TO_BASE_MD
            if moved:
                offenders[name] = sorted(moved)
    assert not offenders, (
        f"these modules still import moved parsers from test_base_md_matrix: {offenders} — "
        "import them from base_md instead")


def test_every_BASE_MD_READER_takes_its_repo_root_from_guard_kit():
    """B3 — one derivation. Every BASE.md reader is an adopter or a documented exclusion."""
    unaccounted, unmigrated = [], []
    for name, source in _test_sources().items():
        if not _BASE_MD_JOIN.search(source):
            continue
        if name in _SEAM_EXCLUSIONS:
            continue
        if name not in _SEAM_ADOPTERS:
            unaccounted.append(name)
            continue
        if "guard_kit import" not in source or _ROOT_DERIVATION.search(source):
            unmigrated.append(name)
    assert not unaccounted, (
        f"{unaccounted} read BASE.md but are neither seam adopters nor documented exclusions")
    assert not unmigrated, (
        f"{unmigrated} still re-derive the repo root instead of importing guard_kit.REPO_ROOT")


def test_the_STANDING_CARVE_OUTS_are_not_dragged_onto_the_seam():
    """B4 — the three deliberately fence-blind sites stay off the adopter list."""
    for name in _SEAM_CARVE_OUTS:
        assert name not in _SEAM_ADOPTERS, f"{name} is a standing carve-out, not an adopter"
