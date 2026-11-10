"""LD-138 (the Markdown-authoring spec § F1-S5) — the discovery surfaces must tell the truth about AUTHORING.

The tranche lifted the creatable floor to the Markdown-expressible set (LD-134 kinds,
LD-135 tables), made it authorable from Markdown (LD-136 ``compose``) and addressable by id
(LD-137 ``AnchorById``). This module is the **truth-surface** contract for that work:

* **AC1** — ``capabilities()``'s docx-write floor carries the **new creatable set**,
  PROJECTED off code truth (the closed ``NewBlockKind`` enum + the encoder's
  ``CREATABLE_BLOCK_TYPES``), with the **D2 exclusions** named as future rungs and asserted
  **absent** from the creatable set. A hand-drifted floor reddens in both directions.
* **AC2** — an **EXECUTABLE authoring recipe** ships in ``guide()``: read →
  ``parse_docx_tree`` → ``compose(markdown)`` → ``InsertRequest`` (quote- **and**
  id-anchored) → ``dry_run`` → ``apply``. It runs in the LD-133 harness like every other
  recipe (``tests/test_discovery_truth.py`` §AC7 executes it), and the checks here pin what
  it must *teach* rather than merely what it produces.
* **AC3** — the **dialect + lossiness** are documented where the consumer reads
  (``guide()``), bound bidirectionally to ``NOT_EXPRESSIBLE_CONSTRUCTS`` and to the closed
  kind enum — including *MD tables cannot express merged cells*.
* **AC3b (D9)** — the **do-not-edit-concurrently warning** is present in the guide **and in
  every authoring recipe's preamble**, asserted at **content level** (the LD-132 lesson: a
  guard keyed on an id or a heading is blind to the prose actually rotting).
* **AC5** — the guide↔``capabilities()`` drift guard covers the new couplings, proven
  **red-then-green** with the same check that guards.
"""
import re

import pytest

import guide_recipes as gr
from doc_prose import missing_phrases, prose
from larkdocio import capabilities, guide
from larkdocio.write import NOT_EXPRESSIBLE_CONSTRUCTS
from larkdocio.write.encode import CREATABLE_BLOCK_TYPES
from larkdocio.write.model import NewBlockKind

# The same table/drift readers the LD-128/133 guards use — one parser and one comparison, so
# a guide edit cannot green here while reddening there (or vice-versa).
from test_guide import _parse_tables, _phantom_and_missing


def _floor() -> dict:
    return capabilities(full=True)["surfaces"]["docx-write"]["content_constraints"]


# --------------------------------------------------------------------------- #
# AC1 — the floor is the NEW truth, projected off code (no hand-drift).         #
# --------------------------------------------------------------------------- #

def test_ac1_the_floor_projects_the_creatable_kinds_off_the_closed_enum():
    """AC1: the floor names the **new creatable set** as KINDS — the answer a consumer
    actually needs ("can I create a heading?"), which the pre-LD-138 field could not give:
    it listed only the two *container* types (``NewBlock`` / ``NewParagraph``), so the
    kind set — the whole point of LD-134/135 — was discoverable nowhere in the projection.

    Projected off :class:`~larkdocio.write.model.NewBlockKind` (the CLOSED enum), never
    hand-listed, so a kind added to the enum widens the floor automatically."""
    floor = _floor()
    assert floor["creatable_kinds"] == sorted(k.value for k in NewBlockKind)
    for kind in ("heading", "paragraph", "bullet", "ordered", "todo", "code", "quote",
                 "table"):
        assert kind in floor["creatable_kinds"], floor["creatable_kinds"]


def test_ac1_the_floor_projects_the_creatable_block_types_off_the_encoder():
    """AC1: the floor also carries the **docx block types** those kinds create, projected
    off ``larkdocio.write.encode.CREATABLE_BLOCK_TYPES`` — the encoder's own truth, and the
    join key to /BLOCKS.md (whose rows are keyed by block type, not by kind)."""
    assert _floor()["creatable_block_types"] == sorted(CREATABLE_BLOCK_TYPES)


def test_ac1_the_kinds_and_the_block_types_agree_through_the_real_encoder():
    """AC1 ("matches the **op registry's real creatable content**"): the two projections are
    not merely two reads of the same constant — every projected kind is **encoded** here and
    the block type it really produces must be in the projected block-type set, and every
    projected block type must be reachable from a kind.

    The one exception is the join that would otherwise be invisible: **``table_cell`` (32)
    has no kind of its own** — a cell is provisioned *with* its table — which is exactly the
    nuance /BLOCKS.md has to spell out, so it is asserted as the single documented exception
    rather than papered over."""
    from larkdocio.write.encode import TABLE_CELL_BLOCK_TYPE, block_type_for
    from larkdocio.write.model import NewBlock

    floor = _floor()
    projected = set(floor["creatable_block_types"])
    samples = {
        NewBlockKind.HEADING: [NewBlock.heading(level, "H") for level in range(1, 10)],
        NewBlockKind.PARAGRAPH: [NewBlock.paragraph("p")],
        NewBlockKind.BULLET: [NewBlock.bullet("b")],
        NewBlockKind.ORDERED: [NewBlock.ordered("o")],
        NewBlockKind.TODO: [NewBlock.todo("t")],
        NewBlockKind.CODE: [NewBlock.code("c", language="python")],
        NewBlockKind.QUOTE: [NewBlock.quote("q")],
        NewBlockKind.TABLE: [NewBlock.table([["a"]])],
        NewBlockKind.MERMAID: [NewBlock.mermaid("graph TD\n  A --> B")],
    }
    assert {k.value for k in samples} == set(floor["creatable_kinds"]), (
        "every projected kind must be exercised here — a new kind needs a sample")

    produced = {block_type_for(block) for blocks in samples.values() for block in blocks}
    assert produced <= projected, (
        f"the encoder creates block types {sorted(produced - projected)} that the floor's "
        f"creatable_block_types omits")
    assert projected - produced == {TABLE_CELL_BLOCK_TYPE}, (
        f"the only creatable block type without a kind of its own is table_cell "
        f"({TABLE_CELL_BLOCK_TYPE}); found {sorted(projected - produced)}")

    # …and the set is not vacuously permissive: a not-creatable type is genuinely absent.
    assert 19 not in projected, "callout (19) is not creatable in this rung"


def test_ac1_the_kinds_and_block_types_projections_state_where_they_came_from():
    """AC1: every projected field says which code it was projected out of, so the "is this
    hand-maintained?" question is answerable from the payload alone."""
    floor = _floor()
    assert floor["kinds_projected_from"] == "larkdocio.write.model.NewBlockKind"
    assert floor["block_types_projected_from"] == (
        "larkdocio.write.encode.CREATABLE_BLOCK_TYPES")


def test_ac1_the_floor_projection_bites_in_both_directions():
    """AC1 (the amplifier's *deliberately-stale floor*, red-then-green): the SAME
    bidirectional comparison that guards the kind floor reports a stale field (a kind the
    code has and the floor omits) AND a phantom one (a kind the floor claims and the code
    lacks) — and is clean on the shipped truth."""
    truth = sorted(k.value for k in NewBlockKind)
    documented = _floor()["creatable_kinds"]

    phantom, missing = _phantom_and_missing(documented, truth)
    assert not phantom and not missing, (documented, truth)

    # stale: the pre-LD-134 floor (paragraph only) → RED, naming every missing kind.
    p1, m1 = _phantom_and_missing(["paragraph"], truth)
    assert not p1 and m1 == [k for k in truth if k != "paragraph"]
    # phantom: a kind that is NOT creatable in this rung → RED.
    p2, m2 = _phantom_and_missing(documented + ["callout"], truth)
    assert p2 == ["callout"] and not m2


@pytest.mark.parametrize("exclusion", [
    "image", "media", "board", "embed", "callout", "grid", "color",
])
def test_ac1_every_d2_exclusion_is_named_not_creatable_and_is_absent_from_creatable(
        exclusion):
    """AC1 / D2: each exclusion (images/media, boards, embedded surfaces, callouts, grids,
    colors) is named in ``not_creatable`` **and** absent from the creatable set — both
    halves, because a floor that lists an exclusion while also claiming it creatable is the
    dogfood **F14** lie in a new costume.

    **LD-433 transformed, not deleted, the images/media half.** The *reason* an image is not
    a creatable KIND is unchanged and still binding — the Markdown compiler holds no bytes
    and makes no network call, so ``![](…)`` is still refused and no ``NewBlockKind``
    creates one. What changed is the conclusion a reader draws: an image *can* now be
    authored, out of band, by a dedicated op. So the assertion stands (the exclusion is
    still named, still absent from the plan-gated creatable set) and the companion test
    below holds the entry to saying **which** it is."""
    floor = _floor()
    assert exclusion in " ".join(floor["not_creatable"]).lower(), floor["not_creatable"]
    creatable = " ".join(floor["creatable_kinds"] + floor["creatable"]).lower()
    assert exclusion not in creatable, floor["creatable_kinds"]


@pytest.mark.conformance
def test_ld433_the_floor_reports_the_out_of_band_creatable_set():
    """The call a consumer already used to get today's *"no"* about images must not keep
    answering "no" now that the op ships. The floor gains its own projected field — off the
    op's ``OUT_OF_BAND_CREATABLE_BLOCK_TYPES``, never hand-listed — and says where it came
    from, exactly like the other three projected sets."""
    from larkdocio.write.media import OUT_OF_BAND_CREATABLE_BLOCK_TYPES

    floor = _floor()
    assert floor["creatable_out_of_band_block_types"] == sorted(
        OUT_OF_BAND_CREATABLE_BLOCK_TYPES)
    assert floor["out_of_band_projected_from"] == (
        "larkdocio.write.media.OUT_OF_BAND_CREATABLE_BLOCK_TYPES")
    named = " ".join(floor["creatable_out_of_band"]).lower()
    assert "image" in named and "put_image_in_document" in named


@pytest.mark.conformance
def test_ld433_the_image_exclusion_says_which_exclusion_it_still_is():
    """The transformed conclusion, asserted: the ``not_creatable`` image entry may no longer
    read as a flat "images cannot be created". It must scope itself to the plan-gated /
    Markdown path AND point at the op that does it, or the projection is telling a consumer
    the thing that is now false."""
    entry = next(e for e in _floor()["not_creatable"] if "image" in e.lower())
    text = prose(entry)
    assert missing_phrases(text, ["put_image_in_document"]) == [], entry
    assert "markdown" in text or "plan-gated" in text, entry


@pytest.mark.conformance
def test_ld433_the_floor_and_the_block_matrix_agree_about_the_out_of_band_set():
    """The same join key the plan-gated sets use, on the other set: the matrix is keyed by
    block type and the floor projects block types, so the two truth surfaces are pinned
    equal instead of separately believed."""
    import re as _re
    from pathlib import Path

    matrix = Path(__file__).resolve().parents[1] / "BLOCKS.md"
    rows = set()
    for line in matrix.read_text(encoding="utf-8").splitlines():
        m = _re.match(r"^\|\s*(\d+)\s*\|[^|]*\|[^|]*\|\s*([^|]+?)\s*\|", line)
        if m and m.group(2).strip("* ") == "creatable-out-of-band":
            rows.add(int(m.group(1)))
    assert rows == set(_floor()["creatable_out_of_band_block_types"])


def test_ac1_the_floor_prose_says_the_exclusions_are_a_future_rung_not_a_refusal():
    """AC1: the exclusions are named as **not creatable in this rung** — a rung, i.e. a
    future one — and the floor keeps saying they are *structurally* inexpressible (a closed
    enum), which is what makes "not creatable" a guarantee rather than a to-do."""
    floor = prose(_floor()["floor"])
    assert "not creatable in this rung" in floor
    assert "rung" in floor and "closed enum" in floor
    assert "editable is not creatable" in floor


# --------------------------------------------------------------------------- #
# AC2 — an EXECUTABLE authoring recipe: compose → dry-run → apply, from a URL.   #
# --------------------------------------------------------------------------- #

_AUTHORING = "author-a-markdown-fragment-into-a-document"


def test_ac2_the_authoring_recipe_ships_and_composes_the_whole_chain():
    """AC2: the recipe exists and its own code walks the chain the AC names — read →
    ``parse_docx_tree`` → ``compose(markdown)`` → ``InsertRequest`` → ``dry_run`` →
    ``apply``. Asserted on the recipe *source*, so a step quietly dropped from the shipped
    text reddens even if what remains still runs."""
    assert f"### Recipe: {_AUTHORING.replace('-', ' ')}" in guide(full=True).replace(
        "Markdown", "markdown"), "the guide must ship the authoring recipe"
    src = gr.recipe_source(_AUTHORING)
    for needle in ("init_env", "validate_download_url", "get_docx_content",
                   "parse_docx_tree", "compose(", "InsertRequest(", "dry_run(", "apply("):
        assert needle in src, f"the authoring recipe never names {needle!r}:\n{src}"


def test_ac2_the_authoring_recipe_starts_from_a_url_a_consumer_pastes():
    """AC2 (dogfood **F13**): the chain starts from a URL, not from a token a previous
    snippet happened to leave lying around — the recipe derives the token itself."""
    src = gr.recipe_source(_AUTHORING)
    assert "https://" in src and "validate_download_url(url)" in src, src
    assert gr.undefined_free_names(src) == [], gr.undefined_free_names(src)


def test_ac2_the_authoring_recipe_anchors_both_ways(monkeypatch, tmp_path):
    """AC2: the recipe shows the ``InsertRequest`` **quote-anchored AND id-anchored** — the
    AC's "quote- **or** id-anchored" proven executably rather than promised in a comment:
    both inserts land in the one run."""
    src = gr.recipe_source(_AUTHORING)
    assert "Anchor(" in src and "AnchorById(" in src, src

    ns = gr.stage(monkeypatch, tmp_path).run(_AUTHORING)
    from larkdocio.write import Anchor, AnchorById

    assert isinstance(ns["plan"].entries[0].anchor, Anchor)
    (follow_up_entry,) = ns["follow_up_plan"].entries
    assert isinstance(follow_up_entry.anchor, AnchorById), follow_up_entry.to_dict()
    assert follow_up_entry.anchor.block_id in ns["created_block_ids"], (
        "the id-anchored follow-up must point at a block THIS recipe created")


def test_ac2_the_authoring_recipe_executes_and_lands_every_creatable_kind(
        monkeypatch, tmp_path):
    """AC2 (**the load-bearing one**): the recipe is extracted from the shipped guide
    verbatim, executed offline, and checked — including that its fragment covers **every**
    creatable kind and that the authored structure reads back through the shipped reader.

    ``test_discovery_truth.py`` §AC7 runs this same spec as part of the whole-recipe sweep
    (so a broken authoring recipe reddens the suite by the LD-133 mechanism); this test
    states the AC2 contract explicitly and fails with an authoring-specific message."""
    ns = gr.stage(monkeypatch, tmp_path).run(_AUTHORING)
    gr._check_authoring(ns)


def test_ac2_the_authoring_recipe_would_redden_if_the_compose_step_broke(
        monkeypatch, tmp_path):
    """AC2 (red-then-green on the recipe's own guard): drop the ``compose`` step from the
    recipe and the SAME runner that greens the shipped text fails — so "it executes" is a
    checked property, not a claim about a fenced block nobody runs."""
    src = gr.recipe_source(_AUTHORING)
    without = "\n".join(ln for ln in src.splitlines() if "content = compose(" not in ln)
    assert without != src, "the recipe has no `content = compose(...)` line to drop"

    st = gr.stage(monkeypatch, tmp_path)
    with pytest.raises(NameError):
        st.run(_AUTHORING, source=without)
    gr._check_authoring(st.run(_AUTHORING))


# --------------------------------------------------------------------------- #
# AC3 — the dialect + the lossiness table, where the consumer reads them.        #
# --------------------------------------------------------------------------- #

_DIALECT_HEADING = "## Authoring from Markdown — the dialect, and what it cannot express"


def _dialect_section(text=None) -> str:
    text = guide(full=True) if text is None else text
    start = text.find(_DIALECT_HEADING)
    assert start != -1, f"the guide has no {_DIALECT_HEADING!r} section"
    rest = text[start + len(_DIALECT_HEADING):]
    nxt = re.search(r"^## ", rest, flags=re.MULTILINE)
    return _DIALECT_HEADING + (rest[: nxt.start()] if nxt else rest)


def _guide_creatable_kinds(text=None) -> list:
    """The kinds the guide's dialect table claims are creatable (the ``kind`` column)."""
    for headers, rows in _parse_tables(_dialect_section(text)):
        if "kind" in headers and "the markdown you write" in headers:
            return sorted(
                m.group(1) for m in (re.search(r"`([^`]+)`", r["kind"]) for r in rows) if m)
    raise AssertionError("the dialect section has no `Kind | The Markdown you write` table")


def _guide_refused_constructs(text=None) -> set:
    """The constructs the guide's lossiness table says ``compose()`` refuses."""
    for headers, rows in _parse_tables(_dialect_section(text)):
        if "construct" in headers:
            return {
                m.group(1) for m in
                (re.search(r"`([a-z-]+)`", r["construct"]) for r in rows) if m}
    raise AssertionError("the dialect section has no `Construct | …` lossiness table")


def test_ac3_the_guide_states_the_dialect_is_the_readers_own_output_plus_escaping():
    """AC3: the guide says *which* Markdown it accepts — our reader's GFM subset, with the
    LD-130 escaping read in reverse — because "Markdown" in general is not the dialect and a
    consumer guessing that costs them a refusal per construct."""
    missing = missing_phrases(_dialect_section(), [
        "exactly what larkdocio's own reader emits",
        "commonmark",
        "gfm",
        "escaped metacharacter",
        "literal text",
    ])
    assert not missing, f"the dialect section no longer states {missing}"


def test_ac3_the_guide_dialect_table_lists_every_creatable_kind_bidirectional():
    """AC3/AC5: the per-kind syntax table equals the floor's projected ``creatable_kinds`` —
    the coupling that makes the guide a *view* of the code rather than a second opinion."""
    phantom, missing = _phantom_and_missing(
        _guide_creatable_kinds(), _floor()["creatable_kinds"])
    assert not phantom, f"the guide's dialect table claims non-creatable kinds: {phantom}"
    assert not missing, f"the guide's dialect table omits creatable kinds: {missing}"


def test_ac3_the_guide_lossiness_table_matches_the_compiler_bidirectional():
    """AC3: the guide carries the **lossiness table** (S3 AC4) and it is bound to
    ``NOT_EXPRESSIBLE_CONSTRUCTS`` both ways — a refusal a consumer cannot look up where
    they read is undocumented lossiness, and a documented refusal the compiler cannot
    actually raise is worse."""
    phantom, missing = _phantom_and_missing(
        _guide_refused_constructs(), set(NOT_EXPRESSIBLE_CONSTRUCTS))
    assert not phantom, f"the guide documents refusals the compiler lacks: {phantom}"
    assert not missing, f"the compiler can refuse constructs the guide omits: {missing}"


def test_ac3_the_guide_says_md_tables_cannot_express_merged_cells():
    """AC3 (named explicitly in the AC): the merged-cell lossiness — the one that survived
    LD-135 — is stated where the authoring dialect is documented."""
    missing = missing_phrases(_dialect_section(), [
        "merged cells are not expressible",
        "colspan",
        "rowspan",
        "ragged",
        "never padded or truncated",
    ])
    assert not missing, f"the dialect section no longer states {missing}"


def test_ac3_the_guide_points_at_the_fuller_treatment_in_the_wheel():
    """AC3: the compact table in the guide names where the long-form discussion lives, so a
    consumer chasing an edge case is not left believing the guide is the whole story. Both
    files ship in the wheel, so the pointer resolves offline."""
    assert "write/README.md" in _dialect_section()


# --------------------------------------------------------------------------- #
# AC3b (D9) — the do-not-edit-concurrently warning, in the guide AND in every     #
# authoring recipe's preamble. Content-level: the LD-132 lesson.                  #
# --------------------------------------------------------------------------- #

def test_ac3b_the_guide_states_the_concurrency_doctrine():
    """AC3b: the guide states the doctrine plainly — do not edit concurrently, the engine
    **refuses rather than guessing** when the document changed under the plan, and a busy
    document just needs a **re-download + re-plan** (cheap)."""
    missing = missing_phrases(guide(full=True), gr.CONCURRENCY_WARNING_PHRASES)
    assert not missing, f"the guide no longer states the D9 doctrine: {missing}"


def test_ac3b_the_doctrine_has_its_own_named_home_in_the_guide():
    """AC3b: the doctrine is a *section* a consumer can be pointed at, not a sentence buried
    in one recipe — and it says the refusal is BY DESIGN (a refusal read as a bug gets
    retried, which is the outcome D9 exists to prevent)."""
    section = _dialect_section()
    assert "concurrent" in prose(section)
    missing = missing_phrases(section, ["by design", "the engine refuses"])
    assert not missing, f"the concurrency section no longer states {missing}"


def test_ac3b_the_authoring_recipe_set_is_derived_from_the_recipes_themselves():
    """AC3b (anti-rot): "every authoring recipe" is **computed** — a recipe that imports the
    docx write surface and calls ``apply``. So the next write recipe is covered by the
    warning guard the moment it ships, instead of relying on its author to update a list."""
    slugs = gr.authoring_recipe_slugs()
    assert _AUTHORING in slugs
    for expected in ("the-docx-write-handshake",
                     "anchor-a-follow-up-by-a-created-block-id",
                     "write-into-an-empty-document"):
        assert expected in slugs, (expected, slugs)
    assert "the-sheets-write-handshake" not in slugs, (
        "the sheets recipe's staleness story is STALE_SHEET, documented on its own contract")
    assert "download-a-docx-to-markdown" not in slugs, "a read recipe authors nothing"


@pytest.mark.parametrize("slug", gr.authoring_recipe_slugs())
def test_ac3b_every_authoring_recipe_preamble_carries_the_warning(slug):
    """AC3b: the warning is in **each** authoring recipe's preamble — the text a consumer
    reads immediately before pasting. Block-level placement is the point (the LD-132
    anti-rot rule): the doctrine stated three sections away does not reach the person about
    to run an authoring batch against a document another user is editing."""
    missing = missing_phrases(gr.recipe_preamble(slug), gr.CONCURRENCY_WARNING_PHRASES)
    assert not missing, (
        f"authoring recipe {slug!r} does not warn about concurrent editing: {missing}")


def test_ac3b_the_warning_guard_bites_red_then_green():
    """AC3b (red-then-green on the content check itself): the same phrase check that greens
    the shipped preamble reports the missing claim when the sentence is deleted, and is
    unaffected by re-wrapping or emphasis — so it cannot be defeated by a reflow, and cannot
    be satisfied by a heading that says nothing."""
    preamble = gr.recipe_preamble(_AUTHORING)
    assert missing_phrases(preamble, gr.CONCURRENCY_WARNING_PHRASES) == []

    gutted = "\n".join(
        ln for ln in preamble.splitlines() if "concurrent" not in ln.lower())
    assert missing_phrases(gutted, gr.CONCURRENCY_WARNING_PHRASES), (
        "deleting the warning must be detected")

    reflowed = preamble.replace("\n", "\n   ").replace("**", "")
    assert missing_phrases(reflowed, gr.CONCURRENCY_WARNING_PHRASES) == [], (
        "a reflow / de-emphasis must NOT redden — a guard that cries wolf gets weakened")


def test_ac3b_the_execution_harness_still_binds_for_every_authoring_recipe():
    """AC3b's tail: the warning must not be bought by making a recipe unrunnable — every
    authoring recipe still has an execution spec, so it is still executed offline."""
    for slug in gr.authoring_recipe_slugs():
        assert slug in gr.SPEC_BY_SLUG, f"authoring recipe {slug!r} has no execution spec"


# --------------------------------------------------------------------------- #
# AC5 — the guide↔capabilities() drift guard covers the NEW couplings.            #
# --------------------------------------------------------------------------- #

def test_ac5_the_kinds_coupling_bites_red_then_green():
    """AC5: the kind coupling is proven with the REAL parser on a mutated guide — a phantom
    kind (the amplifier's "a guide mention of a kind that is not creatable") and a dropped
    kind both redden, and the shipped text greens the same check."""
    truth = _floor()["creatable_kinds"]
    text = guide(full=True)

    assert _phantom_and_missing(_guide_creatable_kinds(text), truth) == ([], [])

    phantom_row = text.replace(
        "| `quote` |", "| `callout` |\n| `quote` |", 1)
    assert phantom_row != text, "could not inject a phantom kind row"
    p, m = _phantom_and_missing(_guide_creatable_kinds(phantom_row), truth)
    assert p == ["callout"] and not m

    dropped = re.sub(r"^\| `table` \|.*\n", "", text, count=1, flags=re.MULTILINE)
    assert dropped != text, "could not drop the table kind row"
    p2, m2 = _phantom_and_missing(_guide_creatable_kinds(dropped), truth)
    assert not p2 and m2 == ["table"]


def test_ac5_the_lossiness_coupling_bites_red_then_green():
    """AC5: the same for the lossiness table — a phantom construct and a dropped construct
    both redden through the real parser."""
    truth = set(NOT_EXPRESSIBLE_CONSTRUCTS)
    text = guide(full=True)

    assert _phantom_and_missing(_guide_refused_constructs(text), truth) == ([], [])

    phantom = text.replace("| `image` |", "| `blink-tag` |\n| `image` |", 1)
    assert phantom != text
    p, m = _phantom_and_missing(_guide_refused_constructs(phantom), truth)
    assert p == ["blink-tag"] and not m

    dropped = re.sub(r"^\| `image` \|.*\n", "", text, count=1, flags=re.MULTILINE)
    assert dropped != text
    p2, m2 = _phantom_and_missing(_guide_refused_constructs(dropped), truth)
    assert not p2 and m2 == ["image"]


def test_ac5_the_authoring_recipe_names_only_ops_and_anchor_kinds_capabilities_projects():
    """AC5: the ops and anchor kinds the authoring recipe uses are **projected** ones — the
    recipe cannot teach a request family or an anchor kind the registry does not carry
    (dogfood **F19** in reverse: the discovery layer promising what the engine lacks)."""
    ops = {op["name"]: op for op in capabilities(full=True)["surfaces"]["docx-write"]["operations"]}
    src = gr.recipe_source(_AUTHORING)

    assert "insert" in ops, "the authoring recipe is an INSERT; the op must be projected"
    assert ops["insert"]["request_types"] == ["InsertRequest"], ops["insert"]
    for anchor_kind in ("Anchor", "AnchorById"):
        assert anchor_kind in src, src
        assert anchor_kind in ops["insert"]["anchor_kinds"], (
            f"the recipe anchors an insert with {anchor_kind}, which capabilities() does "
            f"not project for the family: {ops['insert']['anchor_kinds']}")


def test_ac5_the_floor_kinds_are_reachable_from_the_guide_and_the_projection_alike():
    """AC5 (the coupling stated as the consumer's question): "can I create a heading?" is
    answerable from ``capabilities()`` alone AND from ``guide()`` alone, with the same
    answer — which is the whole point of updating both in one tranche (D5)."""
    for kind in _floor()["creatable_kinds"]:
        assert kind in _guide_creatable_kinds(), kind
        assert kind in capabilities(full=True)["surfaces"]["docx-write"][
            "content_constraints"]["creatable_kinds"]
