""""CHOOSE YOUR LEVEL" — the intent-driven delineation of the object level vs the
Markdown level, guarded.

**Why this module exists.** A real consumer could not tell from the shipped documentation
whether Markdown round-tripping is *required* or *optional*. The architecture answers that
emphatically — the object model is the source of truth, Markdown is opt-in at exactly three
call sites — but the guide stated it only as the **writer's** mental model, below the install
section, and said nothing at all about Sheets.

**Who the shipped text is written for, and what that changes.** The reader is a consumer
**agent** relaying to an end user who knows none of these words. The failure mode is a broken
telephone: the agent half-understands the level model and its user ends up with a mangled
document and no idea why. So the guards below are not "a section exists" checks —

* the section's core is a **decision table** keyed on what an end user actually asks for, and
  **every row is asserted individually**: the row is present, it names its entry points, each
  named entry point **really exists in the public surface** (resolved, never trusted from the
  prose), and it points at a **worked recipe the harness executes**;
* the **jargon ban** is a negative grep, one assertion per banned term, so "DOM"/"AST" and
  friends cannot creep back into the one section written for someone who does not know them;
* the **dropped-field list is derived from the model itself**, so a future field added to the
  tree with the same contract reddens this module until the prose names it (the living-matrix
  discipline, applied to prose);
* the two object-level recipes carry a **zero-Markdown call spy** — the run is asserted to
  have made **no** ``parse_docx_content`` / ``render_spreadsheet`` / ``compose`` call at all.
  That last assertion is this work's whole thesis made executable, and the spy is proven
  non-vacuous by asserting the projection recipes DO trip it.
"""
import importlib
import json
import re

import pytest

import consumer_text
import guide_recipes as gr
from doc_prose import missing_phrases, prose
from guard_kit import is_separator_row, md_table_cells, section
from larkdocio import capabilities, guide
from domain_vocabulary import RETIRED_ID

# --------------------------------------------------------------------------- #
# Shared readers over the shipped section.                                      #
# --------------------------------------------------------------------------- #

SECTION_HEADING = "## Choose your level"

#: The two object-level recipes (slugs). Named here so a rename reddens loudly.
DOCX_OBJECT_RECIPE = "change-a-document-at-the-object-level-no-markdown-anywhere"
SHEETS_OBJECT_RECIPE = "change-a-spreadsheet-at-the-object-level-no-markdown-anywhere"

#: The call sites at which Markdown enters the library, and nowhere else. **LD-251 made it
#: four:** the Base surface's projection entry point ``read_base_markdown`` is a fourth, and the
#: section's stated count moved with it — which is exactly what the count is there to force.
MARKDOWN_CALL_SITES = ("parse_docx_content", "render_spreadsheet", "compose",
                       "read_base_markdown")


def _section(heading: str = SECTION_HEADING) -> str:
    """The guide text from ``heading`` to the next same-or-higher heading, **fence-aware**.

    A ``# ``-prefixed comment inside a fenced block looks exactly like a heading to a
    line-anchored regex, which would cut the section at its first code sample and make every
    content guard here silently vacuous.

    LD-242: the walk is :func:`guard_kit.section`; this keeps the default-argument reader
    over the shipped guide that every test in this module calls.
    """
    return section(guide(full=True), heading)


_TOKEN_RE = re.compile(r"`([^`]+)`")
#: A cross-reference to another section of the guide — ``§ "read a sheet to Markdown"``.
_XREF_RE = re.compile(r"§\s*\"([^\"]+)\"")


def _tables(region: str):
    """``[(headers, rows)]`` for every Markdown table in ``region`` (headers lower-cased)."""
    lines = region.splitlines()
    out, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i].strip()
        if (line.startswith("|") and line.endswith("|") and i + 1 < n
                and is_separator_row(lines[i + 1])):
            headers = [re.sub(r"[*`]", "", c).strip().lower()
                       for c in md_table_cells(line)]
            rows, j = [], i + 2
            while j < n and lines[j].strip().startswith("|") and lines[j].strip().endswith("|"):
                if not is_separator_row(lines[j]):
                    rows.append(dict(zip(headers, md_table_cells(lines[j]))))
                j += 1
            out.append((headers, rows))
            i = j
            continue
        i += 1
    return out


def _table_with(*signature):
    region = _section()
    matches = [rows for headers, rows in _tables(region)
               if all(col in headers for col in signature)]
    assert len(matches) == 1, (
        f"the section must carry exactly one table with columns {signature}; "
        f"found {len(matches)}")
    return matches[0]


def _decision_rows():
    """The decision table's rows — the section's core."""
    return _table_with("the ask, in your user's words", "the level", "the call")


def _symptom_rows():
    """The self-diagnosis table's rows."""
    return _table_with("what you are seeing", "what actually happened", "the fix")


# --------------------------------------------------------------------------- #
# The public surface, DERIVED — so "the entry point exists" is resolved, never   #
# trusted from the prose.                                                       #
# --------------------------------------------------------------------------- #

#: The modules + classes a consumer reaches the two levels through. Only the *names* the
#: guide may claim are derived from these; the list itself is the surface under test.
_SURFACE_OWNERS = (
    "larkdocio",
    "larkdocio.write",
    "larkdocio.comments",
    "larkdocio.read.parser:Parser",
    "larkdocio.read.client:Client",
    "larkdocio.sheets.client:SheetsReadClient",
    "larkdocio.sheets.table",
    "larkdocio.sheets.write_apply",
    "larkdocio.sheets.write_client:SheetsWriteClient",
    "larkdocio.sheets.models:SheetTab",
    "larkdocio.comments.read:CommentsRead",
    # LD-229 — the mention ENCODER a name lookup feeds. It is a public authoring helper on the
    # sheets surface, and the decision table now names it, so it belongs in the set a claimed
    # entry point is checked against rather than being an unresolvable backtick.
    "larkdocio.sheets.rich_encode",
    "larkdocio.contacts",
    # LD-327 — the Drive folder read: the decision table now names `read_folder` / `render_folder`
    # (drive-read's object level and its one-document rendering), so the package they live in
    # joins the set a claimed entry point is checked against.
    "larkdocio.drive",
)


def _resolve_owner(spec: str):
    module_name, _, class_name = spec.partition(":")
    owner = importlib.import_module(module_name)
    return getattr(owner, class_name) if class_name else owner


def public_surface_symbols() -> set:
    """Every public name a consumer can reach through the level surfaces, plus every op
    ``capabilities()`` projects — the set a claimed entry point must be a member of."""
    names = set()
    for spec in _SURFACE_OWNERS:
        owner = _resolve_owner(spec)
        names.update(n for n in dir(owner) if not n.startswith("_"))
    for surface in capabilities(full=True)["surfaces"].values():
        names.update(op["name"] for op in surface["operations"])
    return names


def _claimed_calls(cell: str) -> list:
    """The entry points a table cell names — backticked tokens, calls stripped of ``(...)``."""
    return [re.sub(r"\(.*\)$", "", t).strip() for t in _TOKEN_RE.findall(cell or "")]


def _named_recipe_slugs(cell: str) -> list:
    """The recipe slugs a table cell cross-references."""
    return [gr._slug(name.removeprefix("Recipe: ")) for name in _XREF_RE.findall(cell or "")]


# --------------------------------------------------------------------------- #
# AC1 — an intent-driven section, TOP-PLACED, built around a decision table.     #
# --------------------------------------------------------------------------- #

def test_the_section_ships_and_is_the_guide_s_first_section():
    """The level model is what a consumer meets FIRST — before install, before the matrix.

    Placement is part of the claim: the same three sentences existed already, buried below
    the install section and framed as the writer's own mental model, and a real consumer
    still could not answer "must I go through Markdown?" from them."""
    text = guide(full=True)
    h2s = [ln for ln in text.splitlines() if ln.startswith("## ")]
    assert h2s, "the guide has no H2 sections"
    assert h2s[0].startswith(SECTION_HEADING), (
        f"the level section must be the guide's FIRST section; found {h2s[0]!r}")


def test_the_section_states_the_level_model_for_the_whole_library():
    """The model is claimed for **read + write + sheets**, not for the writer alone: the
    object model is the source of truth, the Markdown projection is a lossy one-way read
    projection AND an optional authoring front-end, and writes never work at the Markdown
    level at all."""
    missing = missing_phrases(_section(), [
        "the tree is the source of truth",
        "the markdown projection is optional",
        "writes never work at the markdown level",
        "without producing a byte of markdown",
    ])
    assert not missing, f"the section does not state the whole-library model: {missing}"


def test_the_section_names_the_three_markdown_call_sites_and_no_others():
    """Markdown is opt-in at a small, stated set of call sites; the section says which, and the
    count is stated so a further one cannot be added silently to the prose — LD-251 is the proof
    that it works: publishing the Base projection moved the number from three to four here."""
    section = _section()
    assert "four" in prose(section), "the section must state the COUNT of Markdown call sites"
    for site in MARKDOWN_CALL_SITES:
        assert f"`{site}`" in section, f"the section never names the {site!r} call site"


def test_the_decision_table_carries_at_least_the_seven_required_intents():
    """The table is the section's core: an end-user ask → the level → the exact entry point
    → a worked recipe → a one-line why."""
    rows = _decision_rows()
    assert len(rows) >= 7, f"the decision table has {len(rows)} rows; ≥7 intents are required"
    for row in rows:
        for column in ("the ask, in your user's words", "the level", "the call",
                       "worked recipe", "why that level"):
            assert row.get(column), f"a decision row leaves {column!r} empty: {row}"


#: One entry per required intent: ``(id, words that identify the ask, entry points it MUST
#: name)``. Asserted **individually** so a partially-written table cannot pass.
REQUIRED_INTENTS = (
    ("show-or-summarize-for-a-human", ("show", "summarize"),
     ("parse_docx_content", "render_spreadsheet")),
    ("extract-structured-data-for-a-tool", ("pull", "figures"),
     ("parse_docx_tree", "read_used_range")),
    ("find-and-change-existing-text", ("find", "change"),
     ("EditRequest", "SubSpanEditRequest")),
    ("add-new-content", ("add", "new"), ("compose",)),
    ("change-spreadsheet-values", ("spreadsheet", "values"), ("ValueWriteRequest",)),
    ("verify-my-own-write", ("landed",), ("compose",)),
    ("what-did-reviewers-comment", ("reviewers", "comment"), ("comments",)),
)


def _row_for(words) -> dict:
    hits = [row for row in _decision_rows()
            if all(w in prose(row["the ask, in your user's words"]) for w in words)]
    assert len(hits) == 1, (
        f"expected exactly one decision row whose ask names {words}; found {len(hits)}")
    return hits[0]


@pytest.mark.parametrize("intent, words, entry_points", REQUIRED_INTENTS,
                         ids=[i for i, _w, _e in REQUIRED_INTENTS])
def test_each_required_intent_has_a_row_naming_its_entry_points(intent, words, entry_points):
    """Per-intent: the row exists and names the entry points that answer it."""
    row = _row_for(words)
    claimed = _claimed_calls(row["the call"])
    missing = [ep for ep in entry_points if ep not in claimed]
    assert not missing, (
        f"the {intent!r} row must name {missing} in its call column; it names {claimed}")


@pytest.mark.parametrize("intent, words, entry_points", REQUIRED_INTENTS,
                         ids=[i for i, _w, _e in REQUIRED_INTENTS])
def test_each_required_intent_points_at_a_recipe_the_harness_executes(
        intent, words, entry_points):
    """A row pointing at nothing runnable is not done: every row names ≥1 worked recipe, and
    every recipe the guide carries is EXECUTED offline by the extract-and-run harness."""
    row = _row_for(words)
    slugs = _named_recipe_slugs(row["worked recipe"])
    assert slugs, f"the {intent!r} row cross-references no worked recipe: {row['worked recipe']}"
    known = set(gr.recipe_blocks())
    unknown = [s for s in slugs if s not in known]
    assert not unknown, (
        f"the {intent!r} row points at recipes the guide does not have: {unknown}")
    specced = [s for s in slugs if s in gr.SPEC_BY_SLUG]
    assert specced, f"the {intent!r} row's recipes are not executed by the harness: {slugs}"


def test_every_entry_point_the_table_names_exists_in_the_public_surface():
    """DERIVED, not transcribed: each backticked call in the table resolves in the real
    public surface (or in ``capabilities()``' projected ops). A transcribed list is a future
    lie — this is what makes it one the suite catches."""
    surface = public_surface_symbols()
    phantom = []
    for row in _decision_rows():
        for call in _claimed_calls(row["the call"]):
            if call not in surface:
                phantom.append((row["the ask, in your user's words"], call))
    assert not phantom, f"the decision table names calls the library does not have: {phantom}"


def test_every_recipe_the_table_names_is_a_real_recipe():
    """Every cross-reference in the table resolves to a ``### Recipe:`` heading the guide
    really carries (and therefore to a recipe the harness runs)."""
    known = set(gr.recipe_blocks())
    dangling = []
    for row in _decision_rows():
        for slug in _named_recipe_slugs(row["worked recipe"]):
            if slug not in known:
                dangling.append(slug)
    assert not dangling, f"the table cross-references non-existent recipes: {dangling}"


# --------------------------------------------------------------------------- #
# AC2 — worked, EXECUTING object-level recipes with no Markdown anywhere.        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("slug", [DOCX_OBJECT_RECIPE, SHEETS_OBJECT_RECIPE])
def test_each_object_level_recipe_ships_specced_and_single_blocked(slug):
    """Both recipes exist, carry exactly one runnable block, and are wired into the
    extract-and-run harness (so the 1:1 spec guard executes them every run)."""
    assert slug in gr.recipe_blocks(), sorted(gr.recipe_blocks())
    assert slug in gr.SPEC_BY_SLUG, sorted(gr.SPEC_BY_SLUG)
    assert len(gr.recipe_blocks()[slug]) == 1


@pytest.mark.parametrize("slug", [DOCX_OBJECT_RECIPE, SHEETS_OBJECT_RECIPE])
def test_neither_object_level_recipe_mentions_a_markdown_call(slug):
    """Static half of the thesis: the recipes' own source contains no render / compose call
    at all — not in the code, not in a commented-out alternative."""
    source = gr.recipe_source(slug)
    for site in MARKDOWN_CALL_SITES:
        assert site not in source, (
            f"the object-level recipe {slug!r} names {site!r} — it must contain no Markdown "
            f"call anywhere:\n{source}")


@pytest.mark.parametrize("slug", [DOCX_OBJECT_RECIPE, SHEETS_OBJECT_RECIPE])
def test_each_object_level_recipe_runs_and_makes_zero_markdown_calls(
        slug, monkeypatch, tmp_path):
    """THE THESIS, MADE TESTABLE: the recipe executes end to end against an injected
    transport and the call spy records **zero** calls to every Markdown call site.

    Not "it ran": a spy on ``parse_docx_content`` / ``render_spreadsheet`` / ``compose``
    counts every invocation the run makes, so the object-level path is *proved* never to
    touch Markdown rather than merely appearing not to."""
    st = gr.stage(monkeypatch, tmp_path)
    ns = st.run(slug)
    gr.SPEC_BY_SLUG[slug].check(ns)
    calls = gr.markdown_calls()
    assert set(calls) == set(MARKDOWN_CALL_SITES), (
        f"the spy must cover every Markdown call site; it covers {sorted(calls)}")
    assert calls == {site: 0 for site in MARKDOWN_CALL_SITES}, (
        f"the object-level recipe {slug!r} made a Markdown call: {calls}")


@pytest.mark.parametrize("slug, site", [
    ("download-a-docx-to-markdown", "parse_docx_content"),
    ("read-a-sheet-to-markdown", "render_spreadsheet"),
    ("author-a-markdown-fragment-into-a-document", "compose"),
])
def test_the_markdown_call_spy_is_not_vacuous(slug, site, monkeypatch, tmp_path):
    """The spy BITES: each projection / authoring recipe trips exactly the call site it is
    built on. A spy that counted nothing would make the zero-assertion above worthless."""
    st = gr.stage(monkeypatch, tmp_path)
    ns = st.run(slug)
    gr.SPEC_BY_SLUG[slug].check(ns)
    assert gr.markdown_calls()[site] >= 1, (
        f"the spy recorded no {site!r} call for {slug!r} — it is not observing the call site")


@pytest.mark.parametrize("slug, injected", [
    (DOCX_OBJECT_RECIPE,
     "Parser(Config()).parse_docx_content(doc_token, blocks)"),
    (SHEETS_OBJECT_RECIPE,
     "__import__('larkdocio.sheets.table', fromlist=['x'])"
     ".render_spreadsheet([(tab, used)])"),
])
def test_the_zero_markdown_assertion_bites_red_then_green(
        slug, injected, monkeypatch, tmp_path):
    """RED-THEN-GREEN on the thesis itself: the same check that greens the shipped recipe
    FAILS when one Markdown call is spliced into it.

    Without this, "the object-level path made no Markdown call" could be an assertion that
    can never fail — a spy installed on the wrong object, or a check that reads an empty dict
    as success. Here the mutation is a real render call on the recipe's own variables, and the
    shipped check must reject it."""
    st = gr.stage(monkeypatch, tmp_path)
    mutated = gr.recipe_source(slug) + "\n" + injected + "\n"
    ns = st.run(slug, source=mutated)
    with pytest.raises(AssertionError, match="made a Markdown call"):
        gr.SPEC_BY_SLUG[slug].check(ns)

    # ...and the shipped text greens the very same check through the very same runner.
    ns_ok = st.run(slug)
    gr.SPEC_BY_SLUG[slug].check(ns_ok)


def test_the_object_level_docx_recipe_targets_the_block_by_its_own_id():
    """The docx recipe teaches the whole object-level chain: read the tree, take the
    block's OWN id off it, anchor by that id, preview, apply."""
    source = gr.recipe_source(DOCX_OBJECT_RECIPE)
    for needle in ("parse_docx_tree", "block_id", "AnchorById", "dry_run(", "apply("):
        assert needle in source, f"the docx object-level recipe never names {needle!r}"


def test_the_object_level_sheets_recipe_writes_a_typed_request_against_a_range():
    """The sheets equivalent: values as objects, a typed request against the tab's own
    opaque id, preview, apply."""
    source = gr.recipe_source(SHEETS_OBJECT_RECIPE)
    for needle in ("read_used_range", "sheet_id", "ValueWriteRequest", "dry_run(", "apply("):
        assert needle in source, f"the sheets object-level recipe never names {needle!r}"


# --------------------------------------------------------------------------- #
# AC3 — "symptoms you picked the wrong level", the field self-diagnosis.         #
# --------------------------------------------------------------------------- #

#: ``(id, words that identify the symptom, phrases the fix must state)``.
REQUIRED_SYMPTOMS = (
    ("spurious-diffs-on-every-list", ("every list",),
     ("compose(authored) == compose(read_back)",)),
    ("anchor-quote-refuses-not-found", ("not-found",), ("anchorbyid",)),
    ("colors-comments-merges-missing", ("missing",), ("parse_docx_tree",)),
    ("a-write-that-seems-to-need-markdown", ("round-trip markdown",), ("anchor",)),
)


def test_the_symptoms_subsection_ships_with_a_row_per_signature():
    section = _section()
    assert "### Symptoms you picked the wrong level" in section, (
        "the section must carry a 'symptoms you picked the wrong level' subsection")
    assert len(_symptom_rows()) >= 4, (
        f"the self-diagnosis table has {len(_symptom_rows())} rows; ≥4 are required")


@pytest.mark.parametrize("symptom, words, fix_phrases", REQUIRED_SYMPTOMS,
                         ids=[s for s, _w, _f in REQUIRED_SYMPTOMS])
def test_each_wrong_level_symptom_is_diagnosed_and_corrected(symptom, words, fix_phrases):
    """Each observable signature maps to what happened AND to the correction — the row is
    useless as a diagnosis if it names only one of the two."""
    hits = [row for row in _symptom_rows()
            if all(w in prose(row["what you are seeing"]) for w in words)]
    assert len(hits) == 1, (
        f"expected exactly one symptom row naming {words}; found {len(hits)}")
    row = hits[0]
    assert row["what actually happened"], f"the {symptom!r} row diagnoses nothing"
    missing = missing_phrases(row["the fix"], list(fix_phrases))
    assert not missing, f"the {symptom!r} row's fix does not state {missing}"


# --------------------------------------------------------------------------- #
# AC4 — plain language: two self-defined terms, and a NEGATIVE grep for jargon.  #
# --------------------------------------------------------------------------- #

def test_the_section_defines_its_two_terms_in_one_sentence_each():
    """The section teaches its own vocabulary before using it: **the tree** (the document's
    real structure as Lark stores it, everything preserved) and **the Markdown projection**
    (a flattened rendering for people, which drops detail by design)."""
    missing = missing_phrases(_section(), [
        "the tree",
        "as lark stores it",
        "the markdown projection",
        "drops detail by design",
    ])
    assert not missing, f"the section does not define its two terms: {missing}"


#: Vocabulary a reader who "has even less clue about the inner workings" cannot resolve.
#: Each is asserted SEPARATELY so a partial clean-up cannot pass. Case-sensitive with word
#: boundaries, so "last"/"past" are not "AST" and "domain" is not "DOM".
BANNED_JARGON = (
    "DOM", "AST", "abstract syntax tree", "document object model", "parse tree",
    "serializer", "deserialize", "renderer",
)


def jargon_hits(text: str) -> list:
    """Every banned term present in ``text`` (case-sensitive, word-bounded)."""
    return [term for term in BANNED_JARGON
            if re.search(r"\b" + re.escape(term) + r"\b", text)]


@pytest.mark.parametrize("term", BANNED_JARGON)
def test_the_section_uses_no_internal_vocabulary(term):
    """The negative grep, one assertion per banned term."""
    assert not re.search(r"\b" + re.escape(term) + r"\b", _section()), (
        f"the section uses {term!r} — the one section written for a reader who does not know "
        "that word")


def test_the_jargon_ban_bites_red_then_green():
    """Red-then-green on the checker itself: the same grep that greens the shipped section
    flags an injected term, and is not tripped by innocent words that merely contain one."""
    assert jargon_hits(_section()) == []
    assert jargon_hits("the section walks the DOM to find a block") == ["DOM"]
    assert jargon_hits("compose parses the fragment into an AST first") == ["AST"]
    assert jargon_hits("the last cell of the past domain, rendered") == [], (
        "the grep must not fire on 'last' / 'past' / 'domain' / 'rendered'")


# --------------------------------------------------------------------------- #
# AC5 — lossiness, PRECISE and DIRECTIONAL, with the dropped list DERIVED.       #
# --------------------------------------------------------------------------- #

#: The contract the model declares on a field it captures and never renders.
_CONTRACT = "consumed into model"


def _model_norm(text: str) -> str:
    """A docstring reduced for phrase matching: hyphens and underscores become spaces."""
    return re.sub(r"[\s`*]+", " ", (text or "").replace("-", " ")).lower().replace("_", " ")


def dropped_model_fields() -> list:
    """``[(class, field)]`` for every tree field carrying the **consumed-into-model,
    dropped-at-render** contract — DERIVED from ``larkdocio.model.nodes`` itself.

    A field qualifies when its own class declares the contract in the same paragraph that
    names it. So a future field added to the tree under that contract reddens the prose guard
    below until the section names it — the living-matrix discipline, applied to prose.
    """
    import dataclasses
    import inspect

    from larkdocio.model import nodes

    found = []
    classes = sorted(
        ((name, obj) for name, obj in vars(nodes).items()
         if inspect.isclass(obj) and dataclasses.is_dataclass(obj)),
        key=lambda kv: kv[0],
    )
    for name, cls in classes:
        doc = cls.__doc__ or ""
        if _CONTRACT not in _model_norm(doc):
            continue
        own = set(inspect.get_annotations(cls))
        paragraphs = re.split(r"\n\s*\n", doc)
        for f in dataclasses.fields(cls):
            if f.name not in own:
                continue
            label = f.name.replace("_", " ")
            for paragraph in paragraphs:
                normalized = _model_norm(paragraph)
                if (_CONTRACT in normalized
                        and re.search(r"\b" + re.escape(label) + r"\b", normalized)):
                    found.append((name, f.name))
                    break
    return found


def test_the_derivation_finds_the_real_contract_fields():
    """The derivation is not vacuous: it finds the fields the model really captures and
    never renders, at BOTH granularities (a block's own list and a run's own list)."""
    derived = dropped_model_fields()
    assert derived, "the derivation found no consumed-into-model fields — it is broken"
    names = {field for _cls, field in derived}
    for expected in ("block_id", "comment_ids", "text_color", "background_color"):
        assert expected in names, (expected, sorted(names))
    granularities = {cls for cls, field in derived if field == "comment_ids"}
    assert len(granularities) >= 2, (
        f"comment_ids exists at two granularities (a block and a run inside it): "
        f"{sorted(granularities)}")


def test_the_prose_names_every_field_the_projection_drops():
    """AC5 direction 1: the enumeration is DERIVED from the model, and the prose must name
    every field that carries the contract."""
    section = _section()
    missing = sorted({field for _cls, field in dropped_model_fields()
                      if f"`{field}`" not in section})
    assert not missing, (
        "the section's lossiness list omits fields the tree really drops at render: "
        f"{missing} — enumerate them, do not summarize them")


def test_the_derived_lossiness_guard_bites():
    """Red-then-green: dropping one field name from the section reddens the very same
    check that greens the shipped text."""
    derived = sorted({field for _cls, field in dropped_model_fields()})
    section = _section()
    gutted = section.replace(f"`{derived[0]}`", "something")
    assert [f for f in derived if f"`{f}`" not in gutted] == [derived[0]]
    assert [f for f in derived if f"`{f}`" not in section] == []


def test_the_lossiness_is_stated_in_three_separate_directions():
    """AC5: three directions, stated separately — the tree → the projection drops named
    things; the projection → typed requests is dialect-bound to the reader's own output; and
    what the projection dropped cannot be recovered from it, **which is why** targeting is
    tree-level. That last clause is the causal link the docs used to leave implicit."""
    missing = missing_phrases(_section(), [
        "the markdown projection drops",
        "the markdown this library's own reader emits",
        "cannot get back out of the projection what it dropped",
        "which is why",
    ])
    assert not missing, f"the section's lossiness statement is not directional: {missing}"


def test_the_heading_level_cap_and_the_sheet_merge_loss_are_named():
    """The two lossinesses that are not model fields: a heading level past the projection's
    cap, and a spreadsheet's merge geometry (a covered cell renders blank)."""
    section = prose(_section())
    assert "######" in _section(), "the section must name the projection's heading-marker cap"
    for claim in ("merge", "blank"):
        assert claim in section, f"the section never mentions {claim!r}"


# --------------------------------------------------------------------------- #
# AC6 — capabilities() gains a level / projection descriptor.                    #
# --------------------------------------------------------------------------- #

def _level_surfaces() -> dict:
    return {sid: s for sid, s in capabilities(full=True)["surfaces"].items() if s.get("levels")}


def test_every_read_surface_declares_a_level_descriptor_and_no_write_surface_does():
    """AC6: the descriptor is a property of a READ surface (which entry point is the
    full-fidelity object read, which is the projection). A write surface has one level, so
    claiming a projection for it would be a lie — pinned in both directions, so a new
    surface cannot ship without deciding."""
    surfaces = capabilities(full=True)["surfaces"]
    read = sorted(sid for sid, s in surfaces.items() if s["mode"] == "read")
    write = sorted(sid for sid, s in surfaces.items() if s["mode"] == "write")
    assert read, "capabilities() reports no read surfaces"
    for sid in read:
        assert surfaces[sid].get("levels"), (
            f"read surface {sid!r} declares no level descriptor")
    for sid in write:
        assert surfaces[sid].get("levels") is None, (
            f"write surface {sid!r} claims a level descriptor; a write has ONE level")


def test_the_level_descriptor_is_small_and_typed():
    """AC6: a framing descriptor, not a second matrix — a fixed, small key set per surface,
    every value a string or ``None``."""
    expected = {"summary", "object_entry_point", "object_returns",
                "projection_entry_point", "projection_returns"}
    for sid, surface in _level_surfaces().items():
        levels = surface["levels"]
        assert set(levels) == expected, (sid, sorted(levels))
        assert levels["summary"], f"{sid}: the descriptor summarizes nothing"
        for key, value in levels.items():
            assert value is None or isinstance(value, str), (sid, key, value)
        assert levels["object_entry_point"] or levels["projection_entry_point"], (
            f"{sid}: the descriptor names neither an object read nor a projection")


def test_every_level_entry_point_resolves_to_a_real_symbol():
    """DERIVED: each entry point is a dotted path that really resolves, so the registry
    cannot advertise a call the library does not have."""
    unresolved = []
    for sid, surface in _level_surfaces().items():
        for key in ("object_entry_point", "projection_entry_point"):
            path = surface["levels"][key]
            if path is None:
                continue
            try:
                _resolve_dotted(path)
            except Exception as exc:                      # noqa: BLE001 — reported, not raised
                unresolved.append((sid, key, path, str(exc)))
    assert not unresolved, f"level entry points that do not resolve: {unresolved}"


def _resolve_dotted(path: str):
    """Resolve ``a.b.C.method`` by importing the longest importable prefix, then walking."""
    parts = path.split(".")
    for cut in range(len(parts), 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:cut]))
        except ImportError:
            continue
        for attr in parts[cut:]:
            obj = getattr(obj, attr)
        return obj
    raise ImportError(f"no importable prefix in {path!r}")


def test_the_section_and_the_registry_name_the_same_entry_points_bidirectionally():
    """AC6's coupling — the guide↔``capabilities()`` drift guard, extended to the level
    model: every entry point the registry declares is named in the section, and the section
    names no projection call the registry does not know about."""
    section = _section()
    registry = set()
    for surface in _level_surfaces().values():
        for key in ("object_entry_point", "projection_entry_point"):
            path = surface["levels"][key]
            if path:
                registry.add(path.split(".")[-1])
    missing = sorted(name for name in registry if f"`{name}`" not in section)
    assert not missing, f"capabilities() declares entry points the section omits: {missing}"

    projections = {
        surface["levels"]["projection_entry_point"].split(".")[-1]
        for surface in _level_surfaces().values()
        if surface["levels"]["projection_entry_point"]
    }
    phantom = sorted(projections - set(MARKDOWN_CALL_SITES))
    assert not phantom, (
        f"the registry declares projection calls the section's three-call-site claim omits: "
        f"{phantom}")


def test_the_registry_still_round_trips_through_json():
    """The descriptor keeps ``capabilities()`` JSON-serializable (no tuples, no dataclasses
    leaking through)."""
    caps = capabilities(full=True)
    assert json.loads(json.dumps(caps)) == caps


# --------------------------------------------------------------------------- #
# AC7 — the level model survives the editable projection, dialect-free.         #
# --------------------------------------------------------------------------- #
#
# **TRANSFORMED, not deleted.** This guard was written when the id-anchored **editable**
# Markdown projection was a roadmap item: it required the level section to carry a
# forward-compatibility note ("a future release may add … the tree stays the source of truth"),
# so that a consumer designing against the tree today would not have to re-learn the model when
# the projection arrived.
#
# **The reason is unchanged; only the conclusion moved.** The projection SHIPPED —
# ``project_block_ids()`` / ``reconcile()`` — so a section asserting it had not is a shipped
# document contradicting the wheel it ships in, and confident prose about the future ages
# badly. The claim it carried is still owed to a consumer, and is now owed by the recipe that
# does the job: whoever uses the editable projection is the reader who needs to hear that the
# tree is still the ground truth. So the guard follows the claim to the recipe rather than
# being struck — a rationale-free strike is what gets a settled argument re-litigated.

def test_the_editable_projection_does_not_displace_the_tree_as_the_source_of_truth():
    """AC7 (transformed): the shipped editable-projection recipe states that the level model
    above is unchanged by it — in consumer terms only, naming no internal project id."""
    recipe = guide(
        section="recipe-update-an-existing-document-change-or-edit-many-blocks-at-once-"
                "without-re-authoring-it")
    flat = " ".join(recipe.split())
    missing = missing_phrases(flat, [
        "the tree stays the source of truth",
        "written back",
        "one more optional front-end onto it",
    ])
    assert not missing, f"the recipe does not carry the level model's claim: {missing}"
    assert not re.search(r"\bLD-\d+\b|" + RETIRED_ID.pattern, recipe), (
        "the claim must be dialect-free — an internal id resolves to nothing for a consumer")


def test_the_level_section_makes_no_roadmap_promise_about_the_projection():
    """AC7 (the other half of the transform): the superseded future-tense conclusion is gone
    from the level section, and nothing has quietly replaced it."""
    section = _section()
    for phrase in ("a future release may add", "a future release", "may add", "not yet ship"):
        assert phrase not in section.lower(), (
            f"the level section carries roadmap prose again: {phrase!r}")


# --------------------------------------------------------------------------- #
# AC8 — every new string is dialect-free at birth.                              #
# --------------------------------------------------------------------------- #

def test_the_whole_section_is_dialect_free():
    """The section is inside the guarded consumer corpus already; asserted here too so a
    failure names THIS section rather than "somewhere in the corpus"."""
    hits = consumer_text.dialect_hits(_section())
    assert hits == [], f"internal dialect in the level section: {hits}"


@pytest.mark.parametrize("slug", [DOCX_OBJECT_RECIPE, SHEETS_OBJECT_RECIPE])
def test_each_new_recipe_is_dialect_free(slug):
    assert consumer_text.dialect_hits(gr.recipe_preamble(slug)) == []
    assert consumer_text.dialect_hits(gr.recipe_source(slug)) == []
