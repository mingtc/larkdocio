"""LD-425 — Base column GROUPING (measured refusal) and column ORDERING (create-time route
already ships), shipped as prose the consumer can look up.

LD-417 § *WHAT TO MINT* rows 1 and 2 (``dev/base-authoring-spike/findings.md`` § Leg A, §
Leg B) measured both. This story mints **no op, no endpoint, no call, no parameter** — it is
documentation only: one refusal paragraph in ``BASE.md`` and the shipped guide's Base section
for grouping, one answer-then-refusal paragraph for ordering, a one-sentence discoverability
fix in ``create_table``'s own docstring(s), and a reasoned no-new-parameter statement on
``create_field``'s.
"""
import pathlib
import re

import larkdocio

import pytest

from base_md import BASE_MD as _BASE_MD
import private_tree  # noqa: E402  (LD-685)

pytestmark = pytest.mark.conformance

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def base_md_text():
    return _BASE_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def guide_text():
    from larkdocio import guide

    return guide(full=True)


# --------------------------------------------------------------------------- #
# AC1 — column GROUPING: a measured refusal, with its full enumeration        #
# --------------------------------------------------------------------------- #

GROUPING_TABLE_KEYS = (
    "field_groups", "column_groups", "groups", "field_group_info",
    "property.field_groups", "property.column_groups", "property.group_info",
)
GROUPING_FIELD_KEYS = (
    "group_id", "field_group_id", "group_name", "column_group",
    "property.group_id", "property.group_name",
)
GROUPING_ENDPOINT_SPELLINGS = (
    "field_groups", "fields/groups", "column_groups",
)
GROUPING_FIELD_READ_MODEL = (
    "field_id", "field_name", "is_extend", "is_primary", "is_synced", "property",
    "type", "ui_type",
)
GROUPING_NOT_TRIED = (
    "user_access_token", "product-internal", "bitable/v2", "dashboard", "automation",
    "form",
)


@pytest.mark.parametrize("text_name", ["base_md_text", "guide_text"])
class TestGroupingRefusalShipsInBothPlaces:
    def test_states_no_api_route(self, request, text_name):
        text = request.getfixturevalue(text_name)
        assert "no API route" in text or "no route" in text

    def test_the_1254001_code_and_the_invented_key_control(self, request, text_name):
        text = request.getfixturevalue(text_name)
        assert "1254001" in text
        assert "invented" in text.lower()

    def test_the_seven_table_keys_are_counted(self, request, text_name):
        text = request.getfixturevalue(text_name)
        assert re.search(r"\b7\b", text)

    def test_the_eight_field_keys_are_counted_and_attributable(self, request, text_name):
        text = request.getfixturevalue(text_name)
        assert re.search(r"\b8\b", text)
        assert "attribut" in text.lower()  # attributable / attributably

    def test_the_five_endpoint_spellings_and_404(self, request, text_name):
        text = request.getfixturevalue(text_name)
        assert re.search(r"\b5\b", text)
        assert "404" in text

    def test_the_field_read_model_has_no_group_concept(self, request, text_name):
        text = request.getfixturevalue(text_name)
        for key in GROUPING_FIELD_READ_MODEL:
            assert key in text, key
        assert "no group" in text.lower()

    def test_the_scope_sentence_survives(self, request, text_name):
        text = request.getfixturevalue(text_name)
        assert "tenant token" in text.lower() or "tenant" in text.lower()
        assert "cannot group columns" in text.lower() or "the product" in text.lower()

    def test_the_subject_confusion_sentence_ships(self, request, text_name):
        text = request.getfixturevalue(text_name)
        lowered = text.lower()
        assert "column" in lowered and "group" in lowered
        assert "record" in lowered  # view RECORD grouping, the thing this is NOT


def test_base_md_names_the_grouping_table_keys(base_md_text):
    for key in GROUPING_TABLE_KEYS:
        assert key in base_md_text, key


def test_base_md_names_the_grouping_field_keys(base_md_text):
    for key in GROUPING_FIELD_KEYS:
        assert key in base_md_text, key


def test_base_md_names_the_endpoint_spellings(base_md_text):
    for spelling in GROUPING_ENDPOINT_SPELLINGS:
        assert spelling in base_md_text, spelling


def test_base_md_names_the_grouping_not_tried_list(base_md_text):
    for phrase in GROUPING_NOT_TRIED:
        assert phrase in base_md_text, phrase


def test_guide_carries_no_internal_dialect_in_the_new_paragraphs(guide_text):
    """AC10 — the added prose is consumer dialect only: no LD-NNN, no dev/ or tests/
    pointer, in the column-shaping paragraphs specifically."""
    start = guide_text.find("Column / field GROUPING")
    if start == -1:
        start = guide_text.lower().find("column grouping")
    assert start != -1, "the grouping paragraph was not found in the shipped guide"
    end = guide_text.find("---", start)
    window = guide_text[start:end if end != -1 else start + 4000]
    assert not re.search(r"\bLD-\d{2,4}\b", window)
    assert "dev/" not in window
    assert "tests/" not in window


# --------------------------------------------------------------------------- #
# AC2 — the subject-confusion cross-pointer resolves to a REAL guide heading   #
# --------------------------------------------------------------------------- #

def test_the_cross_pointer_resolves_to_a_real_guide_sections_heading(guide_text):
    from larkdocio import guide_sections

    headings = [section["heading"] for section in guide_sections()]
    matches = [h for h in headings
               if "view" in h.lower() and "grouping" in h.lower()]
    assert matches, f"no guide heading names the view-grouping recipe: {headings}"
    heading = matches[0]
    # the pointer text in the new paragraph must NAME this heading
    assert heading in guide_text


# --------------------------------------------------------------------------- #
# AC3 — column ORDERING: the answer first, then the refusal, then not-tried   #
# --------------------------------------------------------------------------- #

ORDERING_CREATE_TIME_SPELLINGS = (
    "index", "position", "field_index", "order", "column_index", "insert_index",
    "pre_field_id", "after_field_id", "insert_after", "insert_before",
)
ORDERING_UPDATE_SPELLINGS = ("index", "position", "field_index", "column_index",
                            "pre_field_id")
ORDERING_MOVE_ROUTES = (
    "fields/move", "batch_move", "fields/sort", "batch_update",
)
ORDERING_NOT_TRIED = (
    "non-grid", "data-destroying",
)


@pytest.mark.parametrize("text_name", ["base_md_text", "guide_text"])
class TestOrderingAnswerAndRefusalShipTogether:
    def test_the_true_answer_comes_first(self, request, text_name):
        text = request.getfixturevalue(text_name)
        answer_idx = text.find("settable")
        assert answer_idx != -1
        # the refusal enumeration ("12" create-time spellings) must come AFTER the answer
        twelve_idx = text.find("12", answer_idx)
        assert twelve_idx != -1
        assert twelve_idx > answer_idx

    def test_create_table_fields_array_order_IS_column_order(self, request, text_name):
        text = request.getfixturevalue(text_name)
        assert "create_table" in text
        assert "fields=" in text or "fields=[" in text or "`fields`" in text

    def test_the_reversed_control_is_named(self, request, text_name):
        text = request.getfixturevalue(text_name)
        assert "reversed control" in text.lower() or "reversed" in text.lower()

    def test_twelve_and_five_and_six_are_all_present(self, request, text_name):
        text = request.getfixturevalue(text_name)
        assert re.search(r"\b12\b", text)
        assert re.search(r"\b5\b", text)
        assert re.search(r"\b6\b", text)

    def test_the_not_tried_delete_and_recreate_rebuild_is_named(self, request, text_name):
        text = request.getfixturevalue(text_name)
        lowered = text.lower()
        assert "rebuild" in lowered or "data-destroying" in lowered
        assert "non-grid" in lowered


def test_base_md_names_the_ordering_create_time_spellings(base_md_text):
    for spelling in ORDERING_CREATE_TIME_SPELLINGS:
        assert spelling in base_md_text, spelling


def test_base_md_names_the_ordering_move_routes(base_md_text):
    for route in ORDERING_MOVE_ROUTES:
        assert route in base_md_text, route


# --------------------------------------------------------------------------- #
# AC4 — the discoverability fix lands in create_table's OWN docstring          #
# --------------------------------------------------------------------------- #

def test_create_table_client_docstring_states_the_array_order_is_the_column_order():
    from larkdocio.base.schema_client import BaseSchemaClient

    doc = BaseSchemaClient.create_table.__doc__
    assert "order" in doc.lower()
    assert "column order" in doc.lower() or "the column order" in doc.lower()


def test_create_table_plan_docstring_states_the_array_order_is_the_column_order():
    from larkdocio.base.schema_plan import create_table

    doc = create_table.__doc__
    assert "column order" in doc.lower()


# --------------------------------------------------------------------------- #
# AC5 — no new parameter, and the reasoning ships where a maintainer meets it #
# --------------------------------------------------------------------------- #

def test_create_field_signature_gained_no_position_parameter():
    import inspect

    from larkdocio.base.schema_ops_fields import create_field

    params = list(inspect.signature(create_field).parameters)
    forbidden = {"position", "index", "after", "before", "order"}
    assert not (set(params) & forbidden), params


def test_create_field_docstring_explains_why_no_position_parameter_exists():
    from larkdocio.base.schema_ops_fields import create_field

    doc = create_field.__doc__.lower()
    assert "position" in doc or "index" in doc
    assert "ignored" in doc or "accepted and ignored" in doc


# --------------------------------------------------------------------------- #
# AC6 — a DECISIONS.md row, minted at a re-checked free id                    #
# --------------------------------------------------------------------------- #

@private_tree.register
def test_decisions_md_carries_a_well_formed_D66_heading():
    text = (REPO_ROOT / "requirements" / "DECISIONS.md").read_text(encoding="utf-8")
    assert re.search(r"^### D-66 — .+$", text, re.MULTILINE), (
        "D-66 heading not found or malformed")


@private_tree.register
def test_decisions_md_D66_cites_LD_425_and_LD_417():
    text = (REPO_ROOT / "requirements" / "DECISIONS.md").read_text(encoding="utf-8")
    start = text.index("### D-66")
    end = text.find("### D-", start + 1)
    section = text[start:end if end != -1 else start + 3000]
    assert "LD-425" in section
    assert "LD-417" in section


# --------------------------------------------------------------------------- #
# AC7 — BASE.md's register-completeness arithmetic, or the "unmoved" measure  #
# --------------------------------------------------------------------------- #

def test_base_md_register_count_is_UNMOVED_at_49():
    """This story adds prose paragraphs, not a new status-bearing row, so the pinned
    register count does not move — the measurement AC7 asks for when no row is added."""
    from base_md import register_rows

    text = _BASE_MD.read_text(encoding="utf-8")
    assert len(register_rows(text)) == 49


# --------------------------------------------------------------------------- #
# AC8 — the anchor re-cut ceremony (or the "nothing moved" measurement)        #
# --------------------------------------------------------------------------- #

def test_the_guides_SHAPE_holds_without_a_census_to_re_cut():
    """The guide's stable shape invariant — **three arms and not one literal between them.**

    **This replaces ``test_guide_sections_count_is_UNMOVED_at_103`` (LD-541), and the reason it
    replaces it is the reason it exists.** That guard was 86 lines of docstring ledger in front
    of ``assert len(sections) == 103``, walking 86 -> 87 -> ... -> 103 across seventeen dated
    re-cuts. Every re-cut was honest work — a capability behind the number, measured on a
    baseline tree and *"never computed from the +1 delta"* — and that is exactly why it was
    unsustainable: the guard taxed each of seventeen landings for a fact none of them was about.
    LD-530 deferred the transformation and named this issue as its home; the ledger is relocated
    **verbatim** to
    [`dev/guide-heading-census-ledger.md`](../dev/guide-heading-census-ledger.md), whose banner
    carries LD-530's own reason for refusing `dev/capabilities-anchor-ledger.md` as the home.

    **A bare ``assert len(sections) == <new number>`` was refused by name**: it re-creates the
    ceremony under a new integer and hands the next seventeen landings the same tax. So each arm
    below is a *property*, and a property does not need re-cutting when a heading lands:

    * **Unique slugs.** The half of the old body that was a genuine invariant, kept: a slug
      collision is a real defect (``guide()`` refuses at index-build time on every call), and
      unlike a count it cannot be satisfied by an arithmetic accident.
    * **No ``##`` section is the document.** The largest ``##`` section must be smaller than all
      the other ``##`` sections put together. This is the restructure's own win, pinned: before
      it, one flat ``## Recipes`` was 83.0% of the guide, which is why ``guide.py`` had to index
      at ``(2, 3)`` at all — its comment said so in as many words. A ``##``-level answer that is
      most of the document is not section-level access, and *"most"* is what a majority is. The
      arm is expressed as ``largest * 2 < total`` so there is no percentage to invent, argue
      about or re-cut.
    * **No task group holds a majority of the recipes.** The second route back to the old shape:
      re-merging two groups keeps every ``##`` under the size arm for a while and still rebuilds
      the flat list. Also literal-free.
    """
    from larkdocio import guide_sections
    text = larkdocio.guide(full=True)

    sections = guide_sections()
    slugs = [s["slug"] for s in sections]
    assert len(set(slugs)) == len(slugs), (
        "the guide has a slug collision — guide(section=…) refuses at index-build time on "
        f"EVERY call when this happens: {sorted(s for s in slugs if slugs.count(s) > 1)}")

    h2_starts = [text.index("\n## " + s["heading"]) for s in sections if s["level"] == 2]
    bounds = h2_starts + [len(text)]
    sizes = {}
    h2_slugs = [s["slug"] for s in sections if s["level"] == 2]
    for slug, lo, hi in zip(h2_slugs, bounds, bounds[1:]):
        sizes[slug] = text.count("\n", lo, hi)
    largest = max(sizes.values())
    total = sum(sizes.values())
    assert largest * 2 < total, (
        f"one ## section is {largest} lines against {total - largest} in all the others put "
        f"together — a ##-level index answer is most of the guide again, which is not "
        f"section-level access. Largest: "
        f"{max(sizes, key=sizes.get)!r}. Split it by the task a reader is doing, the way "
        "LD-541 did; do NOT relax this arm")

    recipes = [s for s in sections if s["level"] == 3 and s["heading"].startswith("Recipe: ")]
    per_group = {}
    for s in recipes:
        at = text.index("\n### " + s["heading"])
        owner = max(((lo, slug) for slug, lo in zip(h2_slugs, bounds[:-1]) if lo < at))[1]
        per_group[owner] = per_group.get(owner, 0) + 1
    assert per_group, "no ### Recipe: headings found — the recipe list has stopped being one"
    fattest, count = max(per_group.items(), key=lambda kv: kv[1])
    assert count * 2 < len(recipes), (
        f"the {fattest!r} group holds {count} of the guide's {len(recipes)} recipes — a "
        "majority, so the flat accretion list is being rebuilt one merge at a time")


# --------------------------------------------------------------------------- #
# AC9 — RELEASE_NOTES.md / CHANGELOG.md accumulate into the uncut head         #
# --------------------------------------------------------------------------- #

def test_release_notes_head_carries_the_ld425_entry():
    text = (REPO_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    start = text.find("## [1.33.0]")
    end = text.find("## [1.32.0]")
    section = text[start:end]
    assert "column" in section.lower() and "group" in section.lower()


@private_tree.internal_log
def test_changelog_head_carries_the_ld425_entry():
    text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = text.find("## [1.33.0]")
    end = text.find("## [1.32.0]")
    section = text[start:end]
    assert "LD-425" in section


def test_packaged_notes_are_byte_identical_to_root():
    """This issue's entries had to reach the wheel, not just the repository — that is what this
    test was written for and it is unchanged.

    **LD-540 narrowed the subject, exactly as LD-453 narrowed the census below.** The wheel now
    carries a recent-N WINDOW of each release document rather than a byte-identical twin, so
    "reaches the wheel" is *the packaged copy is byte-identical to the projection of the root*,
    and — like the census — the number and the rule are read from the ONE place that owns them
    instead of spelled out a second time here. A duplicate of a rule is a guard that reddens for
    an ordinary, correct event; delegating is what stops that.
    """
    from test_shipped_notes import notes_identity_report

    assert notes_identity_report() == []


def test_changelog_atx_heading_census_still_MATCHES_THE_ONE_PINNED_CENSUS():
    """LD-425's original claim: *it* added no heading to CHANGELOG.md — bullets only — so
    LD-414's fence census stayed at ``(0, 118, 118)``.

    **The reason is preserved; the way it is enforced has now moved twice, each time for the same
    stated reason.** LD-453 first: spelling the number here as a second literal made this guard a
    duplicate of LD-414's own census, and a duplicate of a *census* is a guard that reddens for
    every later release section — an ordinary, correct event that LD-425 never meant to forbid. So
    the count was read from the **one** place that owns it,
    ``test_packaged_doc_section_access._FENCE_MEASUREMENTS``.

    **LD-540 second, and further along the same line.** The wheel now ships a recent-N WINDOW of
    the changelog, so a release section rolls off the BACK as well as onto the front, and an
    absolute heading count of the packaged document would move at every release with no authored
    change at all. That one place therefore stopped pinning a census for this document and now
    pins the invariant — ``fences == 0`` and ``naive == real``. This test follows it there rather
    than re-deriving a number of its own, which is the whole point of having one owner: what LD-425
    claimed (it opened no heading) is still enforced by the section-level assertions above, and
    what this test adds is that the changelog still has no fence-blind path for the scanner to get
    wrong. **What it used to prove and no longer can:** that the changelog's absolute heading count
    is exactly what it was at some past landing. Under a window that is not a stable property of a
    correct tree, so it is not asserted anywhere — by decision, not by omission."""
    from larkdocio import changelog

    from test_packaged_doc_section_access import FENCE_BLIND_ONLY, _FENCE_MEASUREMENTS

    assert _FENCE_MEASUREMENTS["changelog"] is FENCE_BLIND_ONLY, (
        "the changelog row went back to pinning an absolute census — under a recent-N window "
        "that reddens at every release with no authored change"
    )
    text = changelog()
    assert [line for line in text.split("\n") if re.match(r"^(`{3,}|~{3,})", line)] == []
    naive = [line for line in text.split("\n") if re.match(r"^#{1,6}\s", line)]
    real = [line for line in text.split("\n") if re.match(r"^#{1,6}[ \t]+\S", line)]
    assert len(naive) == len(real), (naive, real)


# --------------------------------------------------------------------------- #
# AC5/AC10 — no code, no signature change anywhere in the Base schema surface  #
# --------------------------------------------------------------------------- #

def test_create_table_client_signature_is_unchanged():
    import inspect

    from larkdocio.base.schema_client import BaseSchemaClient

    sig = inspect.signature(BaseSchemaClient.create_table)
    assert list(sig.parameters) == [
        "self", "app_token", "name", "fields", "primary_field_name", "default_view_name",
    ]


def test_create_table_plan_signature_is_unchanged():
    import inspect

    from larkdocio.base.schema_plan import create_table

    sig = inspect.signature(create_table)
    assert list(sig.parameters) == [
        "app_token", "name", "fields", "primary_field_name", "default_view_name",
    ]
