"""LD-283 — the Base recipe pass, and the guard that keeps the Base surface findable.

**The defect this file exists to prevent.** The Base surface shipped three tranches of
capability in one night and the guide did not keep up: 34 ``### Recipe:`` headings, of which
four were Base, against ~15 for sheets — with **five capability areas shipping zero recipes**
(views, attachments/media, link resolution, computed provenance, field creation). The machinery
was, a consumer reported, good once found — and it was found by
``pkgutil``-walking the installed package, which is not a documentation strategy.

**The guard, in one sentence:** a Base operation that ``capabilities()`` reports must be named
in the guide **somewhere a consumer reads prose** — outside the ``CAPABILITY-MATRIX`` region.
That distinction is the whole point. A matrix row is a *listing*; the matrix guard in
``tests/test_guide.py`` already holds it complete, and it held complete while fourteen Base
operations had no other mention in the document at all. Being listed is not being taught.

The second guard is the **map page**'s own bidirectional check: *"the Base surface, all of it"*
names every Base operation and **claims no other**, so the page cannot drift into advertising a
capability the library does not report (a phantom claim is the failure this pairing catches in
the direction the AC8 guard cannot).
"""
import pathlib
import re

import pytest

import capability_rows as rows
from guard_kit import md_tables
from larkdocio import capabilities, guide, guide_sections
import private_tree  # noqa: E402  (LD-685)

# --------------------------------------------------------------------------- #
# The corpus split: the matrix region, and everything else.                     #
# --------------------------------------------------------------------------- #

_BEGIN = "<!-- BEGIN CAPABILITY-MATRIX"
_END = "<!-- END CAPABILITY-MATRIX"

#: The map page's heading, as the document carries it.
MAP_HEADING = "The Base surface, all of it"
MAP_SLUG = "the-base-surface-all-of-it"

#: The recipes this issue adds, by slug — each is separately executed by
#: ``test_discovery_truth.py``'s ``RECIPE_SPECS`` parametrization, so this file asserts they
#: exist and say what the AC requires rather than re-running them.
NEW_RECIPE_SLUGS = (
    "add-a-column-and-change-one-s-name",
    # LD-418 renamed this heading (D-60, second application) so the group/sort/hidden
    # burn keywords hit through guide_sections(); the slug moved, the content did not.
    # LD-438 renamed it AGAIN, and this time the content moved too: the old heading promised
    # the opposite of what the library now does. The burn keywords survive the rename —
    # "hidden", "grouping" and "sort" are all still in it, per D-60.
    "create-configure-and-delete-a-view-hidden-columns-are-settable-grouping-and-a-saved-sort-are-not",
    "attach-a-file-to-a-record-and-prove-the-bytes-survived",
    "resolve-link-columns-to-names-and-find-the-ones-pointing-at-a-deleted-table",
    "read-what-a-lookup-or-formula-column-rolls-up-from",
    "price-a-bulk-import-before-you-send-it",
)

_TOKEN_RE = re.compile(r"`([^`]+)`")


def _guide_text() -> str:
    return guide(full=True)


def guide_outside_the_matrix() -> str:
    """The guide minus its ``CAPABILITY-MATRIX`` region — the prose a consumer reads."""
    text = _guide_text()
    begin, end = text.find(_BEGIN), text.find(_END)
    assert begin != -1 and end != -1 and end > begin, (
        "GUIDE.md must delimit its capability matrix with the BEGIN/END fences")
    return text[:begin] + text[end:]


def base_operations() -> dict:
    """``{op name: surface id}`` for every operation on every **Base** surface.

    Derived from ``capabilities()`` on every call, never listed here: a list would be a second
    copy of the registry, and a second copy rots. A surface is a Base surface by its id, which
    is how ``capabilities()`` itself names the family.
    """
    out = {}
    for surface_id, surface in capabilities(full=True)["surfaces"].items():
        if not surface_id.startswith("base"):
            continue
        for operation in rows.call_sites(surface, rows.OPERATION):
            out[operation["name"]] = surface_id
    return out


def _map_section() -> str:
    return guide(MAP_SLUG)


def _map_operation_rows() -> list:
    r"""The rows of the map page's **operation** table — the one with an ``operation`` column.

    On ``guard_kit.md_tables`` (LD-632) rather than a fourth hand-rolled header-keyed parse:
    the shared one honours a ``\|`` escape, which a ``strip("|").split("|")`` reads as a cell
    boundary — and a row it mis-splits is a row this guard silently stops checking.
    """
    return [
        row
        for headers, rows in md_tables(_map_section())
        if "operation" in [cell.lower() for cell in headers]
        for row in ({key.lower(): value for key, value in row.items()} for row in rows)
    ]


# --------------------------------------------------------------------------- #
# AC8 — the drift guard: a Base op with no guide reference outside the matrix.  #
# --------------------------------------------------------------------------- #

def test_every_base_operation_is_named_in_the_guide_outside_the_capability_matrix():
    """AC8: a Base operation ``capabilities()`` reports that the guide names **only** inside
    its capability matrix is listed, not taught — and this reddens for it.

    The pre-fix guide fails this for fourteen operations (``batch_get_records``, ``get_app``,
    ``list_views``, ``deep_read_embedded_base``, the four record-write batch/single verbs,
    ``create_app`` / ``rename_app`` / ``copy_app``, ``update_field`` and ``update_view``), which
    is the red half of this guard's red-then-green.
    """
    prose = guide_outside_the_matrix()
    missing = sorted(name for name in base_operations() if name not in prose)
    assert not missing, (
        "these Base operations are reported by capabilities() but appear NOWHERE in the guide "
        f"outside its capability matrix — listed, never taught: {missing}")


def test_excluding_the_matrix_region_is_what_makes_the_guard_bite():
    """Why the guard above searches **prose only**, proven rather than asserted.

    The matrix region names every Base operation by itself — it is generated against the same
    registry — so a guard that grepped the whole document would pass for free and could never
    fail. Excluding the region is the entire mechanism; this pins that, so a later edit that
    "simplifies" the guard into a whole-document grep is caught by a test that says why.
    """
    text = _guide_text()
    matrix_only = text[text.find(_BEGIN):text.find(_END)]
    unlisted = sorted(name for name in base_operations() if name not in matrix_only)
    assert not unlisted, (
        "the capability matrix is supposed to list every Base op — if it does not, the AC8 "
        f"guard's premise has changed: {unlisted}")


# --------------------------------------------------------------------------- #
# AC1 — the map page.                                                          #
# --------------------------------------------------------------------------- #

def test_the_map_page_ships_and_guide_sections_returns_it():
    """AC1: the map page is a real guide section, reachable by name."""
    index = {row["slug"]: row for row in guide_sections()}
    assert MAP_SLUG in index, sorted(index)
    assert index[MAP_SLUG]["heading"] == MAP_HEADING
    assert index[MAP_SLUG]["level"] == 2, "the map is a top-level page, not a recipe"
    assert guide(MAP_HEADING) == guide(MAP_SLUG), "heading and slug must name the same section"


def test_the_map_page_answers_the_six_questions_with_an_import_path():
    """AC1: the question → object map covers the six the exit interview asked for, and each
    entry names the **import path a consumer types** rather than only an object name."""
    section = _map_section()
    for wanted in (
        "from larkdocio.base import computed_columns",
        "from larkdocio.base.field_authoring import FIELD_PROPERTY_SHAPES",
        "from larkdocio.base import dangling_link_columns",
        "from larkdocio.base import read_base",
        "from larkdocio.base.media import BaseMediaClient",
        "from larkdocio.base.apply import dry_run",
    ):
        assert wanted in section, f"the map page never names the import path {wanted!r}"
    for question in ("provenance", "column shapes", "dangling", "files", "batch"):
        assert question in section.lower(), question


def test_the_map_page_names_every_base_operation_and_claims_no_other():
    """AC1 + AC9: the map's operation table is bidirectional against ``capabilities()``.

    Missing rows make the page an incomplete map; **phantom** rows make it a claim the library
    does not support, which is the failure the AC calls out by name.
    """
    documented = {_TOKEN_RE.search(row["operation"]).group(1)
                  for row in _map_operation_rows()
                  if _TOKEN_RE.search(row["operation"])}
    truth = set(base_operations())
    assert not documented - truth, (
        f"the map page claims operations capabilities() does not report: "
        f"{sorted(documented - truth)}")
    assert not truth - documented, (
        f"capabilities() reports Base operations the map page omits: "
        f"{sorted(truth - documented)}")


def test_every_map_row_says_where_the_operation_is_taught():
    """AC1: a map is a pointer, so every row carries one — no row may be a bare name."""
    rows = _map_operation_rows()
    assert rows, "the map page has no operation table"
    for row in rows:
        pointer = row.get("where it is taught", "")
        assert pointer and pointer not in {"-", "—"}, row


# --------------------------------------------------------------------------- #
# LD-473 AC3 — the ROUTING names, pinned against the real attributes.           #
#                                                                              #
# The map's routing row was wrong as written, twice — `.records` for the read   #
# model's `.rows`, and a `.raw()` method on an object that has none — and it    #
# cost a consumer two runs of `AttributeError`. Prose cannot be trusted to stay #
# true about an attribute name, so it is held against the attribute. No guard   #
# encoded the OLD spelling anywhere in this tree (grepped at landing), so       #
# there was nothing to transform: this pair is new coverage over a seam that    #
# had none.                                                                     #
# --------------------------------------------------------------------------- #

#: ``(the name the map page shows, its module, the container class, its row-container attribute,
#: the ROW class those rows are, and the attribute one row's wire body lives on)``. Both
#: directions are checked below, so neither the table nor the classes can move alone.
ROUTING_OBJECTS = (
    ("BaseTableRead", "larkdocio.base.table", "BaseTableRead", "rows", "BaseRow", "raw_fields"),
    ("BaseTableSnapshot", "larkdocio.base.model", "BaseTableSnapshot", "records",
     "SnapshotRecord", "raw_fields"),
)

#: The row objects those containers hold, and what a caller may ask of each. The **negative**
#: half is the load-bearing one: a ``BaseRow`` has no ``raw`` method, which is exactly the
#: ``AttributeError`` the old routing row taught.
ROUTING_ROW_OBJECTS = (
    ("larkdocio.base.table", "BaseRow", ("raw_fields",), ("raw", "raw_as_dict")),
    ("larkdocio.base.model", "SnapshotRecord", ("raw_fields", "raw", "raw_as_dict"), ()),
)


def _routing_table_cells() -> str:
    """The map page's routing table — every line of it that mentions one of the two objects."""
    section = _map_section()
    return "\n".join(line for line in section.splitlines()
                     if line.startswith("|") and any(name in line
                                                     for name, *_rest in ROUTING_OBJECTS))


@pytest.mark.parametrize("shown, module, cls_name, rows_attr, row_cls_name, raw_attr",
                         ROUTING_OBJECTS)
def test_the_routing_row_names_attributes_that_actually_exist(shown, module, cls_name,
                                                              rows_attr, row_cls_name,
                                                              raw_attr):
    """Direction one: every attribute the map page names on this object is really on it."""
    import importlib

    loaded = importlib.import_module(module)
    cls = getattr(loaded, cls_name)
    fields = set(getattr(cls, "__dataclass_fields__", {})) | set(dir(cls))
    assert rows_attr in fields, (
        f"the map page routes a consumer to {shown}.{rows_attr}, which does not exist — this is "
        f"the exact defect the row is guarded against: {sorted(fields)}")
    row_cls = getattr(loaded, row_cls_name)
    row_fields = set(getattr(row_cls, "__dataclass_fields__", {})) | set(dir(row_cls))
    assert raw_attr in row_fields, (
        f"{shown}.{rows_attr}[j].{raw_attr} does not exist — the page routes through the ROW "
        f"object, so the row object is what has to carry it: {sorted(row_fields)}")

    table = _routing_table_cells()
    assert f"`.{rows_attr}`" in table or f"`{rows_attr}`" in table, (
        f"the map page's routing table never spells {shown}'s row container {rows_attr!r}")
    assert raw_attr in table, (
        f"the map page's routing table never spells {shown}'s raw body {raw_attr!r}")


def test_the_routing_row_does_not_conflate_the_two_objects():
    """Direction two: the page must say `.rows` AND `.records` and say which is which.

    One sentence naming both objects at once is how the defect shipped. The table has one **row
    per object**, so the two spellings can be told apart by reading a single line.
    """
    table = _routing_table_cells()
    assert "`.rows`" in table and "`.records`" in table, table
    for line in table.splitlines():
        both = ("`.rows`" in line) and ("`.records`" in line)
        assert not both, (
            "one line of the routing table names BOTH row containers — that is the conflation "
            f"the split exists to prevent: {line}")


@pytest.mark.parametrize("module, cls_name, present, absent", ROUTING_ROW_OBJECTS)
def test_the_row_objects_have_exactly_the_accessors_the_page_promises(module, cls_name,
                                                                      present, absent):
    """The negative half: a ``BaseRow`` has **no** ``.raw()`` — the AttributeError itself."""
    import importlib

    cls = getattr(importlib.import_module(module), cls_name)
    names = set(getattr(cls, "__dataclass_fields__", {})) | set(dir(cls))
    for attr in present:
        assert attr in names, f"{cls_name}.{attr} is promised by the guide and does not exist"
    for attr in absent:
        assert attr not in names, (
            f"{cls_name} has grown a {attr!r} — the guide says plainly that it does not have "
            f"one, so the guide is now wrong and this is where it is caught")


def test_the_page_gives_RawNotRetained_the_import_path_it_really_has():
    """AC3's Dev call, pinned: the type is documented **with its real module**.

    ``RawNotRetained`` is raised by the snapshot's loud accessors and is **not** re-exported
    from ``larkdocio.base``. The guide names the module that defines it rather than the package
    root, and both halves of that sentence are asserted here — so an export added later reddens
    this and the sentence gets corrected with it.
    """
    import larkdocio.base as base_pkg
    from larkdocio.base.model import RawNotRetained

    assert RawNotRetained is not None
    assert not hasattr(base_pkg, "RawNotRetained"), (
        "`RawNotRetained` is now re-exported from `larkdocio.base` — the guide's sentence "
        "saying it is not must be corrected in the same change")
    section = _map_section()
    assert "from larkdocio.base.model import RawNotRetained" in section, (
        "the guide must name the import path a consumer types for the refusal the accessors "
        "raise, or the type stays documented-and-unreachable")


# --------------------------------------------------------------------------- #
# LD-473 AC4/AC5 — the seeding disclosure, and the two sections that must CITE  #
# EACH OTHER.                                                                   #
#                                                                              #
# AC5's defect was not a wrong sentence: BOTH sections were correct and neither #
# mentioned the other, so a reader who found one derived a conclusion the other #
# refutes. A cross-reference is therefore the FIX, and a fix that is one edit    #
# away from rotting is one a guard has to hold.                                 #
# --------------------------------------------------------------------------- #

#: The structural-handshake recipe, by slug — where the collision is told whole.
HANDSHAKE_SLUG = "recipe-create-rename-and-copy-a-base-the-structural-handshake"


def _handshake() -> str:
    return guide(HANDSHAKE_SLUG)


def test_the_column_order_section_cites_the_checkbox_refusal_and_the_forfeit():
    """AC5, direction one: the map's ORDER section must name the kinds the route refuses."""
    section = _map_section()
    order = section[section.find("Column ORDER is settable"):]
    assert order, "the map page no longer carries the column-order section"
    for wanted in ("Checkbox", "Rating", "forfeit", "create_field"):
        assert wanted in order, (
            f"the column-order section never mentions {wanted!r} — the reader who finds this "
            "section alone still derives the wrong plan, which is the defect")
    assert "the structural handshake" in order, (
        "…and it must point at the recipe that tells the collision whole")


def test_the_checkbox_refusal_section_cites_the_column_order_fact_and_the_forfeit():
    """AC5, direction two: the recipe's refusal paragraph must name the order consequence."""
    recipe = _handshake()
    collision = recipe[recipe.find("THIS ROUTE AUTHORS FEWER KINDS"):]
    assert collision, "the structural handshake no longer carries the refused-kinds paragraph"
    for wanted in ("Column ORDER is settable", "forfeit", "APPENDS", "append order"):
        assert wanted.lower() in collision.lower(), (
            f"the refused-kinds paragraph never says {wanted!r}: the consumer told to 'add them "
            "with create_field' still does not learn what that costs")


def test_the_local_refusal_itself_carries_the_forfeit():
    """AC5: the sentence a caller reads **in the exception** carries the cost, not only the
    guide. The refusal is where the decision is actually being made."""
    from larkdocio.base.schema_ops_app_table import NOT_AUTHORABLE_AT_CREATION_GUIDANCE as text

    assert "create_field" in text and "APPENDS" in text, text
    assert "FORFEITED" in text, (
        "the refusal says 'then add them with create_field' — without the forfeit that is a "
        "workaround whose price is discovered by reading the column order back")
    assert "APPEND ORDER IS DISPLAY ORDER" in text, (
        "…and the half that makes the workaround usable must travel with it")


def test_the_creation_recipe_discloses_what_a_new_base_ACTUALLY_CONTAINS():
    """AC4: the seeded table, its columns and its blank rows, where the create is taught."""
    recipe = _handshake()
    for wanted in ("Attachment", "ten blank rows", "default_table_id",
                   "list_tables(app_token)[0]"):
        assert wanted in recipe, (
            f"the creation recipe never discloses {wanted!r} — a consumer cannot tell the "
            "seeded table from theirs")
    assert "never yours" in recipe or "not yours" in recipe, (
        "the disclosure has to say plainly WHOSE table index 0 is")


# --------------------------------------------------------------------------- #
# AC2..AC7 — the five recipe-less areas, plus the bulk-import audit.            #
# --------------------------------------------------------------------------- #

def test_the_six_new_recipes_ship():
    """AC2–AC7: each area now has a ``### Recipe:`` heading of its own."""
    index = {row["slug"] for row in guide_sections()}
    missing = [slug for slug in NEW_RECIPE_SLUGS if f"recipe-{slug}" not in index]
    assert not missing, f"these recipes do not ship: {missing}"


def test_the_six_new_recipes_all_have_an_execution_spec():
    """AC2–AC7 + AC9: every new recipe EXECUTES in the offline harness (the LD-291 precedent),
    which is what ``RECIPE_SPECS`` being 1:1 with the guide's headings buys."""
    import guide_recipes as gr

    missing = [slug for slug in NEW_RECIPE_SLUGS if slug not in gr.SPEC_BY_SLUG]
    assert not missing, f"these recipes have no execution spec: {missing}"


def test_field_creation_recipe_names_the_pairing_registry():
    """AC2: the real import line, both worked examples, and the sentence that says where the
    ``(field_type, ui_type)`` pairing is authored — so nobody guesses a type int."""
    section = guide(f"recipe-{NEW_RECIPE_SLUGS[0]}")
    assert ("from larkdocio.base.schema_ops_fields import create_field, update_field, "
            "convert_field") in section
    assert "SingleSelect" in section and "options" in section
    assert "SingleLink" in section, "the link-column example is missing"
    assert "FIELD_PROPERTY_SHAPES[ui_type].field_type" in section
    assert "before you guess a type int" in section.lower() or \
           "read it before guessing" in section.lower(), section[:200]


def test_views_recipe_discloses_that_a_view_is_created_unconfigured():
    """AC3: create / update / delete, ``delete_view``'s lighter ceremony, and the honest
    deliverable stated **where a kanban-builder reads it** rather than inside the filter
    recipe."""
    section = guide(f"recipe-{NEW_RECIPE_SLUGS[1]}")
    for wanted in ("create_view", "update_view", "delete_view", "rename_view"):
        assert wanted in section, wanted
    lowered = section.lower()
    assert "unconfigured" in lowered
    assert "consent" in lowered, "delete_view's lighter ceremony must be stated"
    # LD-438 re-aimed the third assertion rather than dropping it: `hidden fields` moved from
    # the CANNOT list to the CAN list on measured evidence, so the recipe must still name all
    # three subjects a kanban-builder searches for — and must now say which side each is on.
    for named in ("grouping", "hidden columns", "sort"):
        assert named in lowered, named
    assert "set_view_hidden_fields" in section, (
        "the recipe must name the verb, not merely the capability")
    assert "open it in the product" in lowered


def test_media_recipe_states_the_permanence_disclosure_in_the_recipe():
    """AC4: upload → cell → read back → ``verify_round_trip`` by sha256, with the permanence
    disclosure in the RECIPE rather than only in the module docstring."""
    section = guide(f"recipe-{NEW_RECIPE_SLUGS[2]}")
    for wanted in ("BaseMediaClient", "verify_round_trip", "sha256", "file_token"):
        assert wanted in section, wanted
    lowered = section.lower()
    assert "purge" in lowered and "permanent" in lowered, (
        "media accretes and nothing in Lark's open API purges it — say so here")


def test_link_resolution_recipe_states_the_two_halves_rule():
    """AC5: the cost disclosure, the byte-stability reason for the default, and the two-halves
    rule that stops a consumer reading a free schema answer as a record-level one."""
    section = guide(f"recipe-{NEW_RECIPE_SLUGS[3]}")
    assert "resolve_links=True" in section
    assert "dangling_link_columns" in section
    assert "link_resolution" in section
    lowered = section.lower()
    assert "one batched read per" in lowered and "target table" in lowered
    assert "byte" in lowered, "the byte-stability reason it is off by default"
    assert "record was deleted" in lowered or "only a record" in lowered


def test_the_read_recipe_now_names_resolve_links():
    """AC5: ``read_base(..., resolve_links=True)`` appears in the **read** recipe — where a
    consumer meets the read — not only in a toggles table."""
    section = guide("recipe-read-a-base-to-markdown")
    assert "resolve_links=True" in section


def test_computed_provenance_recipe_says_whose_fault_the_gaps_are():
    """AC6: what a Lookup/Formula column rolls up from, and what the transport cannot tell
    you — attributed, not merely reported."""
    section = guide(f"recipe-{NEW_RECIPE_SLUGS[4]}")
    assert "computed_columns" in section
    for key in ("target_field", "roll_up", "formula"):
        assert key in section, key
    assert "unavailable" in section
    assert "Lark" in section, "an `unavailable` with no owner reads as a library defect"


def test_bulk_import_recipe_prices_the_batch_in_a_free_dry_run():
    """AC7: the three numbers a bulk importer needs, demonstrable with zero API calls."""
    section = guide(f"recipe-{NEW_RECIPE_SLUGS[5]}")
    for wanted in ("api_call_count", "call_index", "records_per_call"):
        assert wanted in section, wanted
    assert "records_per_call=25" in section
    lowered = section.lower()
    assert "one call per family per table" in lowered, "the shipped default must be stated"
    assert "unprobed" in lowered or "not probed" in lowered, (
        "the per-call ceiling is unprobed — say so rather than implying a limit")


# --------------------------------------------------------------------------- #
# AC9 — no new capability.                                                     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("slug", NEW_RECIPE_SLUGS)
def test_new_recipes_are_dialect_free(slug):
    """AC9 + the consumer-dialect doctrine: a shipped recipe carries no internal D-label or
    issue id — a consumer cannot resolve either."""
    section = guide(f"recipe-{slug}")
    assert not re.search(r"\bLD-\d{3}\b", section), section[:200]
    assert not re.search(r"\bD\d[′″‴]*\(?[a-z]?\)?\b", section), section[:200]


# --------------------------------------------------------------------------- #
# The wave's own corrections, guarded (two unfiled QA minors).                  #
#                                                                              #
# Both are the same shape: something this docs wave got RIGHT that nothing      #
# would notice going wrong again. A correction with no falsifier is a comment.  #
# --------------------------------------------------------------------------- #

#: The probe whose measurement the offline double models. Named as data so the failure
#: message can point a reader at the evidence rather than at an opinion.
SEEDING_CAPTURE = "tests/captures/base-study/captures/ld473-01-seeding-and-append-order.json"


def _seeding_capture():
    import json
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    return json.loads((root / SEEDING_CAPTURE).read_text(encoding="utf-8"))["response"]


@private_tree.dev_record
def test_the_measured_seeding_really_says_a_create_echo_carries_its_table():
    """The REASON half, read off the probe rather than restated: a create's own reply carries
    a ``default_table_id``, and that id is the table ``list_tables()`` returns at index 0.

    This is what makes the disclosure recipe teachable at all — if the measurement ever said
    otherwise, the recipe and the double below are both wrong and this is where it starts.
    """
    seeding = _seeding_capture()["seeding"]
    echoed = seeding["default_table_id_from_create"]
    assert echoed, f"{SEEDING_CAPTURE} records no default_table_id on the create's echo"
    assert seeding["tables"][0]["table_id"] == echoed
    assert seeding["list_tables_0_is_the_default_table"] is True
    assert seeding["row_count"] == 10 and seeding["rows_all_empty"] is True, (
        "the disclosure names ten blank rows; the capture is where that number comes from")


def test_the_offline_create_double_echoes_a_seeded_default_table_id():
    """A CREATE's echo carries its table; a COPY's does not. The double must model **both**.

    The distinction is the whole content of the disclosure: the recipes teach a consumer to
    read ``created.default_table_id`` instead of indexing ``list_tables(...)[0]`` and hoping,
    and a double that answered the copy's empty string for a create would let that recipe run
    green while teaching the opposite. Reverting ``create_app`` to the empty echo reddens here.
    """
    from offline_doubles import OfflineBaseReadClient, OfflineBaseSchemaClient

    saved_calls = list(OfflineBaseSchemaClient.calls)
    saved_name = OfflineBaseReadClient.app_name_override
    try:
        client = OfflineBaseSchemaClient("app-id", "app-secret")
        created = client.create_app("a base", "fldrXYZ")
        copied = client.copy_app("appOTHER", "a copy", folder_token="fldrXYZ")
    finally:
        OfflineBaseSchemaClient.calls[:] = saved_calls
        OfflineBaseReadClient.app_name_override = saved_name

    assert created.default_table_id, (
        "the offline create's echo carries no default_table_id — that is the COPY's shape. "
        f"The create was measured to carry one ({SEEDING_CAPTURE}: "
        "`default_table_id_from_create`), and the recipes read it, so this double would make "
        "them pass while teaching a consumer to index list_tables()[0] instead")
    assert copied.default_table_id == "", (
        "a copy's echo must stay empty — modelling it as filled is the mirror-image defect, "
        "and it is what would let a recipe teach that an echo is state")


def test_there_is_no_draft_create_and_the_denial_stays_where_a_consumer_reads_it():
    """The shipped NEGATIVE, pinned both ways — the ``RawNotRetained`` treatment applied to a
    claim about an absence.

    The guide and the release notes both say plainly that **creating a row is ``draft.add``
    and there is no ``draft.create``**, and a stated absence is a promise like any other: if
    the draft ever grows a ``create``, the sentence is wrong and the sentence is what a
    consumer plans against. So both halves are asserted here — the absence itself, so gaining
    the attribute reddens, and the denial's presence in shipped text, so deleting the sentence
    reddens too. Either alone can rot silently; that is why the pair exists.
    """
    from larkdocio.base.model import TableDraft

    assert not hasattr(TableDraft, "create"), (
        "TableDraft has grown a `create` — the guide and the release notes both state there is "
        "no `draft.create` and that an attempt is an AttributeError. Correct both sentences in "
        "the same change, or this ships as a documented lie about the library's own vocabulary")
    for verb in ("add", "set", "update", "delete"):
        assert hasattr(TableDraft, verb), (
            f"the draft's four-verb table names `{verb}` and the draft does not have it")

    recipe = guide("recipe-the-base-write-handshake")
    assert "THERE IS NO `draft.create`" in recipe, (
        "the write handshake no longer denies `draft.create` — the guess the library's own op "
        "names (`create_record`, `create_table`, `create_field`, `create_base`) invite is then "
        "answered only by an AttributeError with no message")
    # THE CANONICAL ROOT DOCUMENT, not the packaged copy — and the move is a supersession,
    # not a weakening. The reason is unchanged: a consumer re-pinning reads the release notes,
    # and that is where this absence was announced (1.35.0). What changed is that the copy
    # INSIDE THE WHEEL is a WINDOW of the newest 8 releases by design, so 1.35.0 aged out of it
    # the moment an 1.43.0 section landed (LD-591) — the announcement was not rewritten, it
    # simply passed the window's edge, exactly as the window's own preamble says it will. The
    # document a re-pinning consumer actually holds is the FULL one the refresh script drops
    # beside the wheel (`vendor/larkdocio-RELEASE_NOTES.md`), which is this file, so this is
    # where the claim is pinned now. The in-wheel arm above (the guide recipe) is untouched and
    # still carries the denial for a wheel-only reader.
    root_notes = (pathlib.Path(__file__).resolve().parent.parent / "RELEASE_NOTES.md").read_text("utf-8")
    assert "There is no `draft.create`." in root_notes, (
        "the release notes' denial is gone — a consumer re-pinning reads that document, and it "
        "is where the absence was announced")
