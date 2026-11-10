"""LD-441 — the SHIPPED PROSE says what the code says.

The register this closes is the 2026-08-13 pre-cut audit's shipped-prose family: the writer
brief still listed image creation under **Non-goals** as *"structurally inexpressible"* after
D-71 shipped `put_image_in_document`, and the guide's own capability prose agreed with it from
the other side. Every check here is a **projection** check — the prose is compared against
`capabilities()`, `guide_sections()` or the real parser, never against a second hand-list —
which is why none of it carries `pytest.mark.conformance` (`conformance-tier.md` § A.4:
internal projection ↔ internal projection is a **regression** tier).

The supersession discipline (`supersession.md` § A.1) is asserted as well as performed: each
corrected sentence keeps its original **reason** (the compiler holds no bytes; a created run is
unstyled) beside the replaced **conclusion**, and the guards below pin the reason as hard as
they pin the correction — an over-broad "fix" that deletes the reason, or that relicenses
boards and embeds, reddens exactly like the staleness did.
"""

import re

import pytest

import larkdocio
from larkdocio import capabilities, guide, guide_sections, writer_brief
from larkdocio.common.url import parse_deep_link
from larkdocio.common import docx_block_url, docx_edition_url


# --------------------------------------------------------------------------- #
# Helpers — the shipped text, read the way a wrapped claim survives a grep.     #
# --------------------------------------------------------------------------- #

def _flat(text: str) -> str:
    """One-line normalization. A flat substring grep walks straight past a claim that spans a
    Markdown line wrap, which is how the stale sentences survived so many sweeps."""
    return " ".join(text.split())


def _guide_flat() -> str:
    return _flat(guide(full=True))


def _brief_flat() -> str:
    return _flat(writer_brief())


def _section(heading: str) -> str:
    return guide(heading)


def _headings() -> set:
    return {_flat(row["heading"]) for row in guide_sections()}


def _brief_headings() -> set:
    return {_flat(s["heading"])
            for s in capabilities(full=True)["docs"]["writer_brief()"]["sections"]}


# --------------------------------------------------------------------------- #
# AC3 / AC4 / AC5 — the writer brief stops asserting impossibility.             #
# --------------------------------------------------------------------------- #

#: The two out-of-band authoring verbs D-71 and LD-434 shipped. Read off the module rather
#: than spelled twice, so a rename reddens here instead of leaving the brief pointing at a
#: symbol that no longer exists.
def _media_verbs():
    from larkdocio.write import media

    return ("larkdocio.write.media.put_image_in_document",
            "larkdocio.write.media.put_file_in_document",
            media.put_image_in_document.__name__,
            media.put_file_in_document.__name__)


def test_the_media_verbs_the_prose_points_at_actually_exist():
    """The pointer half of every correction below: a citation of a verb that does not exist
    would be a second defect wearing the first one's clothes."""
    from larkdocio.write import media

    assert callable(media.put_image_in_document)
    assert callable(media.put_file_in_document)


@pytest.mark.parametrize("verb", [
    "larkdocio.write.media.put_image_in_document",
    "larkdocio.write.media.put_file_in_document",
])
def test_ac3_the_briefs_non_goals_route_to_the_out_of_band_verbs(verb):
    """AC3: the Non-goals section — the one section a consumer reads to decide feasibility —
    names where an image and a file attachment ARE authored."""
    assert verb in _flat(writer_brief("Non-goals")), writer_brief("Non-goals")


def test_ac3_the_non_goals_preserve_the_reason_and_keep_boards_and_embeds_inexpressible():
    """AC3, both halves of `supersession.md` § A.1 at once.

    The **reason** the plan-gated path cannot create an image is unchanged and still stated —
    *the compiler holds no bytes*. Only the **conclusion** (*"structurally inexpressible"*,
    said of images) moved. And the correction may not over-reach: boards and embeds really are
    structurally inexpressible, and the section still says so.
    """
    non_goals = _flat(writer_brief("Non-goals")).lower()
    assert "holds no bytes" in non_goals, "the preserved reason was deleted, not kept"
    assert "structurally inexpressible" in non_goals, (
        "boards / embeds ARE structurally inexpressible — the correction over-reached")
    assert "boards" in non_goals and "embeds" in non_goals


#: A word that SCOPES an inexpressibility claim to the plan-gated Markdown path. The claim is
#: still true there — the compiler holds no bytes — so scoping is the correction, not deletion
#: (`supersession.md` § A.1: the reason survives, the conclusion narrows).
_SCOPED = ("plan-gated", "plan gate", "this path", "this rung", "newblockkind", "dialect",
           "markdown path", "compose(")


def test_ac3_no_shipped_sentence_calls_an_IMAGE_or_an_ATTACHMENT_FLATLY_inexpressible():
    """The register's actual finding, as a standing guard over both shipped documents.

    Every *inexpressible* claim is read as one clause: if it carries ``image``, ``media`` or
    ``attachment``, it must also carry a scope — because the shape that shipped was the
    unscoped *"No creation of images / boards / embeds — structurally inexpressible"*, and a
    consumer reading it concluded a capability that shipped had not shipped. Boards and embeds
    need no scope: for them the flat claim is simply true.
    """
    offenders = []
    for name, text in (("writer_brief()", _brief_flat()), ("guide()", _guide_flat())):
        for match in re.finditer(r"[^.;]{0,240}(?:structurally )?inexpressible[^.;]{0,120}",
                                 text):
            clause = match.group(0).lower()
            about_bytes = any(w in clause for w in ("image", "attachment", "media"))
            if about_bytes and not any(s in clause for s in _SCOPED):
                offenders.append((name, match.group(0).strip()))
    assert not offenders, (
        "an image / attachment is authored OUT OF BAND since D-71 — an UNSCOPED "
        f"inexpressibility claim about one is the defect this issue closed: {offenders}")


def test_ac4_the_briefs_overview_scopes_its_non_authoring_claim_to_the_plan_gated_path():
    """AC4 (findings 34/35): the opening capability paragraph is scoped to the
    ``NewBlockKind`` / plan-gated path and carries the out-of-band pointer, instead of
    generalising over the whole library."""
    overview = _flat(writer_brief("Public API surface"))
    assert "larkdocio.write.media.put_image_in_document" in overview, overview[:400]
    assert "NewBlockKind" in overview, "the preserved reason (a closed enum) was dropped"


def test_ac4_created_text_is_unstyled_carries_D73s_ONE_exception_everywhere_it_is_said():
    """AC4 (D-73): every shipped *"created text is unstyled"* sentence names the link anchor.

    Block-level granularity, the LD-132 anti-rot rule: the exception living *somewhere else*
    in the document does not stop the paragraph a consumer is actually reading from being
    false. Each occurrence is read with the window that follows it.
    """
    bare = []
    for name, text in (("writer_brief()", writer_brief()), ("guide()", guide(full=True))):
        for para in re.split(r"\n\s*\n", text):
            # A lossiness TABLE row saying "`italic` — a styled run, created text is
            # unstyled" is about that one style and is still exactly true; the claim this
            # guards is the standalone capability sentence.
            if para.lstrip().startswith("|"):
                continue
            flat = _flat(para)
            if not re.search(r"[Cc]reated text is \*{0,2}unstyled\*{0,2}", flat):
                continue
            if "link" not in flat.lower():
                bare.append((name, flat[:140]))
    assert not bare, (
        "D-73: a created run MAY carry a link anchor (`TextSpan.link_url`) — an unqualified "
        f"'created text is unstyled' is stale: {bare}")


def test_ac5_the_file_attachment_is_said_APART_from_the_embedded_surfaces():
    """AC5 (finding 26): the brief's not-creatable table gives the file attachment its own
    row pointing at `put_file_in_document`, and says the two products apart — the attachment
    BLOCK (type 23, in the body) versus the folder upload plus a `rich_paragraph` link."""
    brief = _brief_flat()
    row = next((line for line in writer_brief().splitlines()
                if line.startswith("|") and "put_file_in_document" in line), "")
    assert row, "no not-creatable row routes to put_file_in_document"
    assert "embedded surfaces" not in row.lower(), (
        "the file attachment is still rowed together with Base / Sheet / synced blocks")
    assert "put_file_in_folder" in brief and "rich_paragraph" in brief, (
        "the two products — the body BLOCK and the folder upload + link anchor — are not "
        "said apart")
    assert "no Markdown syntax to compose them from" in brief, (
        "the preserved reason (the dialect has no syntax for it) was deleted")


# --------------------------------------------------------------------------- #
# AC6 — the write-recipe chooser routes the media asks.                         #
# --------------------------------------------------------------------------- #

_CHOOSER = "Which write recipe do you need? — add, change, update or delete content in a document"


@pytest.mark.parametrize("intent,target", [
    ("picture", "Recipe: put an image in a document (create, upload, bind)"),
    ("link to something", "Recipe: link a file from a sentence"),
])
def test_ac6_the_chooser_routes_the_media_asks(intent, target):
    chooser = _flat(_section(_CHOOSER))
    assert intent in chooser.lower(), f"the chooser has no row for {intent!r}"
    assert target in chooser, f"the {intent!r} row does not route to {target!r}"


def test_ac6_every_recipe_the_chooser_routes_to_is_a_REAL_section():
    """The chooser is a chooser only if its destinations resolve — a row pointing at a
    heading `guide_sections()` does not carry is a dead end, which is the same trap AC10
    closes for the § references."""
    heads = _headings()
    for ref in re.findall(r'§ \*{0,2}"([^"]+)"', _section(_CHOOSER)):
        ref = _flat(ref)
        assert any(ref in h for h in heads), f"the chooser routes to a non-section: {ref!r}"


# --------------------------------------------------------------------------- #
# AC7 / AC8 — the guide's own account of what the library IS.                   #
# --------------------------------------------------------------------------- #

def _opening_definition() -> str:
    text = guide(full=True)
    start = text.index("larkdocio is a **Python toolkit")
    return _flat(text[start:text.index("\n\n", start)])


def test_ac7_the_opening_definition_names_every_surface_FAMILY_capabilities_reports():
    """AC7 (finding 12): the cheapest paragraph in the document to read is a projection of
    ``capabilities()['surfaces']``, the way `pyproject.toml`'s Summary already is — it named
    three surfaces while the library shipped sixteen across five families."""
    families = sorted({sid.split("-")[0] for sid in capabilities(full=True)["surfaces"]})
    definition = _opening_definition().lower()
    missing = [f for f in families if f not in definition]
    assert not missing, (
        f"the guide's definition of the library omits surface families {missing} — it is a "
        f"projection of capabilities()['surfaces'], not a snapshot of an older library")


def test_ac7_the_definition_says_the_base_and_drive_surfaces_are_WRITE_surfaces_too():
    """The half a reader plans around: Base and Drive are not read-only here, and a
    definition that lists them without their write halves is the same omission one level
    down. Derived — the surface ids themselves say which families write."""
    writing = sorted({sid.split("-")[0] for sid in capabilities(full=True)["surfaces"]
                      if capabilities(full=True)["surfaces"][sid]["mode"] != "read"})
    definition = _opening_definition().lower()
    for family in writing:
        assert family in definition, family
    assert "write" in definition


def test_ac8_the_markdown_call_site_enumeration_is_COMPLETE_and_every_name_resolves():
    """AC8 (finding 13): the closed count was *four* while the paragraph itself named five
    things and `render_folder` was missing. The two-level doctrine is the reason the sentence
    exists and it is preserved; only the count and the enumeration move. LD-705: the count said
    five while `project_block_ids` (the write-back projection) was a sixth; the count is now
    derived from the enumeration below rather than restated."""
    from larkdocio.base import render_base, read_base_markdown
    from larkdocio.model import project_block_ids
    from larkdocio.drive import render_folder
    from larkdocio.read.parser import Parser
    from larkdocio.sheets import render_spreadsheet, read_spreadsheet_markdown

    sites = {
        "parse_docx_content": Parser.parse_docx_content,
        "project_block_ids": project_block_ids,
        "render_spreadsheet": render_spreadsheet,
        "render_base": render_base,
        "render_folder": render_folder,
        "compose": larkdocio.compose,
    }
    paragraph = _flat(_section("Choose your level — the tree, or the Markdown projection"))
    for name, symbol in sites.items():
        assert callable(symbol), name
        assert f"`{name}`" in paragraph, (
            f"{name} produces or consumes Markdown and the enumeration omits it")
    count = {5: "five", 6: "six", 7: "seven", 8: "eight"}[len(sites)]
    assert f"**{count}**" in paragraph, "the closed count is still not the enumeration's size"
    for composite in (read_spreadsheet_markdown, read_base_markdown):
        assert f"`{composite.__name__}`" in paragraph, (
            f"{composite.__name__} is a read+render composite and the paragraph must say so")
    assert "without producing a byte of Markdown" in paragraph, (
        "the preserved reason — Markdown is optional end to end — was deleted")


# --------------------------------------------------------------------------- #
# AC9 — the deep-links chapter stops trapping its own reader.                   #
# --------------------------------------------------------------------------- #

_DEEP_LINKS = ("Deep links — what a Lark URL points at, what you can mint, and what you "
               "cannot")


def test_ac9a_the_links_the_library_MINTS_are_measurably_not_the_links_it_PARSES():
    """The measurement behind the prose. Both minted grammars answer `NotADeepLink`, and the
    chapter's exclusion clause (*"no fragment or query"*) does not cover either of them — a
    reader who round-trips his own minted link gets a refusal the chapter did not predict."""
    doc = "https://example.feishu.cn/docx/DOCTOKEN123"
    minted = (docx_block_url(doc, "blk123"), docx_edition_url(doc, "ver123"))
    for url in minted:
        assert type(parse_deep_link(url)).__name__ == "NotADeepLink", url
    assert "#" in minted[0] and "?" in minted[1], (
        "neither minted grammar is fragment-less or query-less, so the chapter's "
        "'no fragment or query' clause cannot be what excludes them")


def test_ac9a_the_chapter_STATES_the_asymmetry_and_names_both_minted_grammars():
    """AC9(a): one sentence, in the chapter, naming the two grammars the library mints and
    saying plainly that `parse_deep_link` answers `NotADeepLink` for them **deliberately**."""
    chapter = _flat(_section(_DEEP_LINKS))
    assert "docx_block_url" in chapter and "docx_edition_url" in chapter, chapter[:300]
    assert "NotADeepLink" in chapter
    asymmetry = re.search(
        r"[^.]{0,400}docx_edition_url[^.]{0,400}NotADeepLink[^.]{0,200}\.", chapter)
    assert asymmetry, (
        "the chapter must state the mint/parse asymmetry in one sentence, not leave a reader "
        "to discover it by round-tripping his own link")


def test_ac9b_the_mintable_deep_links_heading_counts_the_helpers_its_body_documents():
    """AC9(b): three helpers are documented under that heading — a spreadsheet tab, a docx
    block and a named edition — and `guide_sections()` derives the index from the heading, so
    a heading that counts two hides the third from every sectioned reader."""
    heading = next((h for h in _headings() if h.startswith("The mintable deep links")), None)
    assert heading, sorted(_headings())
    body = _flat(_section(heading))
    for helper in ("tab_url", "docx_block_url", "docx_edition_url"):
        assert helper in body, f"{helper} is documented elsewhere than under its own heading"
    assert "edition" in heading.lower(), (
        f"the heading counts two of the three helpers its body documents: {heading!r}")


# --------------------------------------------------------------------------- #
# AC10 — every § reference resolves.                                            #
# --------------------------------------------------------------------------- #

#: The one deliberate cross-document pointer: the guide cites the writer brief's own section
#: by name (GUIDE.md → `write/README.md`), which is a real heading in the OTHER shipped
#: document and so resolves against its section index rather than the guide's.
_CROSS_DOCUMENT_REFS = {"The composable Markdown dialect"}


def test_ac10_every_section_reference_in_the_guide_RESOLVES_to_a_real_heading():
    """AC10 (finding 18): a `§ "…"` citation is a promise that `guide(section=…)` answers.

    The audit found one dangling reference; the sweep this guard performs found **four**
    (§ *"Four honest sources of an id"*, § *"There is no bulk form"* in two spellings, and
    § *"An embedded Base inside a docx"*) — all bold prose, none of them a heading. Rather
    than promote four paragraphs and move the section census four times, each citation now
    names its **containing heading** and the bold paragraph inside it.
    """
    heads = _headings() | _brief_headings()
    unresolved = sorted({
        ref for ref in (_flat(r) for r in re.findall(r'§\s*[*_]{0,2}"([^"]+)"', guide(full=True)))
        if ref not in _CROSS_DOCUMENT_REFS
        and not any(ref in h for h in heads)
    })
    assert not unresolved, (
        "a § citation that is not a heading cannot be fetched with guide(section=…) — "
        f"re-word it to its containing heading: {unresolved}")


def test_ac10_the_reference_guard_bites_on_the_shape_that_shipped():
    """Red-then-green: the check that guards is the check that bites."""
    heads = _headings()
    assert not any("Four honest sources of an id" == h for h in heads), (
        "if that paragraph is ever promoted to a heading, delete this bite test with it")
    assert not any("Four honest sources of an id" in h for h in heads)


# --------------------------------------------------------------------------- #
# AC11 — the routing row tells the truth about name resolution.                 #
# --------------------------------------------------------------------------- #

def test_ac11_the_mention_routing_row_puts_the_EMAIL_on_it():
    """AC11 (finding 46): the front-of-book row routed another user's **name** through
    `resolve_user`, whose directory search was measured to reach at most the account owner.
    The row now names the input that actually reaches another user."""
    row = next((line for line in guide(full=True).splitlines()
                if line.startswith("|") and "@mention Ada" in line), "")
    assert row, "the routing table lost its @mention row"
    assert "resolve_colleague" in row, row
    assert "email" in row.lower(), row


def test_ac11_the_measurement_is_SCOPED_to_its_tenant_and_its_day_not_universal():
    """D-59 scoping, mandatory: one tenant, one day. A row that asserted the universal would
    be the same over-reach in the other direction."""
    row = next(line for line in guide(full=True).splitlines()
               if line.startswith("|") and "@mention Ada" in line)
    assert "measured" in row.lower(), row
    assert "tenant" in row.lower(), row


def test_ac11_the_mention_recipe_LEADS_with_the_email_verb():
    """The recipe the row routes to leads with `resolve_colleague`, not with the verb the
    measurement says does not reach another user."""
    recipe = _section("Recipe: author a sheet cell that @mentions a teammate")
    first_verb = min(
        (recipe.index(v), v) for v in ("resolve_colleague", "resolve_user") if v in recipe)
    assert first_verb[1] == "resolve_colleague", (
        "the recipe still leads with the name verb the measurement does not support")


# --------------------------------------------------------------------------- #
# AC12 / AC15 — the size literal, and the document count.                       #
# --------------------------------------------------------------------------- #

def test_ac12_the_guide_states_its_own_size_in_PROSE_not_as_a_hard_number():
    """AC12 (finding 17): the sentence's job is to justify a sectioned read, and a stale
    magnitude is exactly what defeats it. Same non-numeric form LD-440 adopted for the other
    three instances — the shared regex is `front_door.GUIDE_SIZE_LITERAL`."""
    import front_door as fd

    offenders = fd.guide_size_literal_offenders(["src/larkdocio/GUIDE.md"])
    assert not offenders, offenders
    assert "hundreds of KB as one string" in _guide_flat(), (
        "the magnitude still has to be STATED — de-numbering is not deleting the reason to "
        "read one section")


def test_ac15_the_vendor_drop_is_FOUR_and_the_WHEEL_carries_FIVE():
    """AC15 (finding 15): both counts are true and they are different numbers. Derived — the
    wheel's count is `capabilities()['docs']`, and the vendor drop is what
    `consumers/update_larkdocio.sh` actually writes.

    **LD-549 moved both numbers by one and the CLAIM is unchanged.** The Lark-application
    walkthrough now ships inside the wheel (a fifth accessor document) *and* drops beside the
    vendored wheel (a fourth drop), so the pair is four / five. The defect this guard exists
    for is the chapter stating ONE count for two different things — so both numbers are still
    asserted, and the document that accounts for the difference is still named."""
    assert len(capabilities(full=True)["docs"]) == 5, sorted(capabilities(full=True)["docs"])
    install = _flat(_section("Install (vendored wheel — the locked distribution model)"))
    assert "five" in install.lower(), (
        "the install chapter must say the WHEEL carries five documents — four is the vendor "
        "drop's count, and stating one number for both is the defect this guard is for")
    assert "writer_brief()" in install, (
        "the document the wheel carries and the drop does not is the writer brief, and the "
        "chapter must name it — a count with no name explains nothing")
    assert "four" in install.lower(), (
        "the vendor drop really is four files — the preserved fact, not a thing to delete")


# --------------------------------------------------------------------------- #
# LD-571 — the GENERATED front door, held against the module it projects.        #
# --------------------------------------------------------------------------- #

def _emphasis_free(text: str) -> str:
    """Flattened, with Markdown emphasis markers removed.

    The module docstring writes its scope word in bold and the registry note writes the same
    sentence in a plain-text register, so a raw substring check would compare typography instead
    of the claim. Nothing else is normalized: the words, the punctuation and the scope word all
    have to match.
    """
    return _flat(text.replace("**", "").replace("*", ""))


def _files_write_note() -> str:
    return _flat(capabilities(surface="drive-files-write")["credentials"]["note"])


def test_ld571_the_destination_rule_is_AUTHORED_ONCE_and_the_front_door_PROJECTS_it():
    """AC1. Three statements of one rule, and the projection was the one that went stale.

    The fix is not a corrected sentence — a corrected fourth copy is the same defect one release
    later. It is a **constant** the module authors beside its own docstring and the registry
    imports, pinned here from both sides: it is a substring of the docstring (the present-side
    check — a re-typed docstring sentence that drifts from the constant reddens) and a substring
    of the generated note (so the front door cannot spell the rule for itself).
    """
    from larkdocio.drive import files_write

    rule = files_write.DESTINATION_IS_THE_CALLERS
    assert _emphasis_free(rule) in _emphasis_free(files_write.__doc__), (
        "the module docstring no longer contains the constant it authors — one of the two was "
        "edited without the other, which is the drift the constant exists to make impossible")
    assert _emphasis_free(rule) in _emphasis_free(_files_write_note()), (
        "the generated drive-files-write note does not project the module's own destination "
        f"rule; it must carry it verbatim rather than restate it. Note: {_files_write_note()}")


def test_ld571_the_front_door_no_longer_denies_a_call_LISTED_IN_THE_SAME_PAYLOAD():
    """AC1's other half — the supersession, asserted rather than trusted.

    Only the **library-wide** half of the conclusion is superseded. The reason it was written is
    preserved word for word (a permanent write into a destination the library picked would be a
    surprise), the claim still binds where it is true (this module creates no folder), and the
    payload's own answer is what makes the old scope false: ``create_folder`` is right there.
    """
    payload = capabilities(full=True)
    folders = payload["surfaces"]["drive-folders-write"]
    assert "create_folder" in {op["name"] for op in folders["operations"]}, (
        "the falsifier moved — this guard is only meaningful while the library really does "
        "create folders somewhere")
    note = _files_write_note()
    assert "anywhere in this library" not in note.lower(), (
        "the generated note claims a library-wide absence again, and the payload it sits in "
        "carries create_folder — the exact contradiction this issue closed")
    assert "anywhere in this module" in note.lower(), (
        "the scoped claim was deleted rather than transformed; the module creates no folder and "
        "that is still worth saying")
    assert "would be a surprise" in note, (
        "the REASON was dropped in the correction — supersession replaces a conclusion and "
        "keeps the reason (process/doctrine/supersession.md)")


def test_ld571_the_destination_rule_is_NOT_RETYPED_anywhere_under_src():
    """The F9 arm: one authoring, however many readers. A grep for the rule's own distinctive
    clause finds it in the constant and nowhere else — a second literal spelling of it is a
    parallel definition of the sentence whose *scope* just proved able to rot."""
    import pathlib

    clause = "folder-creating call anywhere in this"
    hits = []
    for path in sorted(pathlib.Path("src/larkdocio").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        occurrences = _emphasis_free(text).lower().count(clause)
        if occurrences:
            hits.append((str(path), occurrences))
    assert hits == [("src/larkdocio/drive/files_write.py", 2)], (
        f"the destination rule is spelled in more places than the constant and the docstring "
        f"it is substituted into: {hits}")


def test_ld571_the_capability_matrix_ROUTES_a_task_WORD_to_the_index_that_answers_it():
    """AC4. *"Can it hide a tab?"* — measured, the matrix section carried **zero** occurrences
    of the consumer's own word, and neither did the surface payload one level down. The answer
    was reachable only from ``guide()``'s index, which the reader had not been sent to.

    So the section routes, and the routing is pinned to the code that owns the vocabulary: the
    op id comes from the tab-presentation op tuple, the request class from the shipped class's
    own name, and the index really does answer the question. The section's SIZE is deliberately
    not asserted — shrinking it is welcome and is a different issue.
    """
    from larkdocio.sheets.ops import TAB_PRESENTATION_OPS
    from larkdocio.sheets.requests import SetTabVisibility

    section = _flat(_section("Capability matrix"))
    op_id = next(op for op in TAB_PRESENTATION_OPS if "visib" in op)
    assert "hide" in section.lower(), (
        "the matrix section still cannot be searched for the word a consumer uses")
    assert op_id in section, (
        f"the section does not name the operation's own id {op_id!r}, which is the spelling a "
        "plan entry uses")
    assert SetTabVisibility.__name__ in section, (
        "the section does not name the request class, which is the spelling the recipe uses")
    answering = [row["heading"] for row in guide_sections() if "hide" in row["heading"].lower()]
    assert answering, (
        "the index the section routes to no longer answers the question — the routing is now "
        "the false instruction it was written to avoid")
    assert "larkdocio.guide()" in section, (
        "the section names no route to the index that does answer it")


# --------------------------------------------------------------------------- #
# LD-703 (round 5, V2) — a surface's note does not deny a surface the same      #
# registry ships.                                                               #
# --------------------------------------------------------------------------- #

def _surface_notes():
    """``{surface id: flattened text of every string under it}`` from ``capabilities(full=True)``."""
    def strings(node):
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for value in node.values():
                yield from strings(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                yield from strings(value)

    surfaces = capabilities(full=True)["surfaces"]
    return {sid: _flat(" ".join(strings(body))) for sid, body in surfaces.items()}


def test_ld703_the_drive_read_note_names_EVERY_drive_write_surface_the_registry_ships():
    """Round 5 found ``drive-read`` telling every consumer the Drive family had "exactly one
    mutating rung" and that sharing was "REFUSED BY POLICY … exposes no such call", while the
    same registry shipped four Drive write surfaces, ``drive-access-write`` (grant / update /
    revoke) among them. The set is derived from the registry, never retyped here."""
    surfaces = capabilities(full=True)["surfaces"]
    writes = sorted(sid for sid, body in surfaces.items()
                    if body["domain"] == "drive" and body["mode"] == "write")
    assert "drive-access-write" in writes and len(writes) >= 2
    note = _surface_notes()["drive-read"]
    named = sorted(set(re.findall(r"\bdrive-[a-z]+-write\b", note)))
    assert named == writes, (named, writes)
    for stale in ("exactly one mutating rung", "exposes no such call", "REFUSED BY POLICY"):
        assert stale not in note, stale


def test_ld703_no_surface_note_names_a_surface_id_the_registry_does_not_ship():
    """Every ``<family>-…-read`` / ``-write`` id a note names resolves to a shipped surface, so a
    renamed or retired surface cannot linger in another surface's prose."""
    notes = _surface_notes()
    stale = sorted({(sid, ref) for sid, text in notes.items()
                    for ref in re.findall(r"\b(?:docx|drive|sheets|base|contacts)"
                                          r"(?:-[a-z]+)*-(?:read|write)\b", text)
                    if ref not in notes})
    assert stale == []
