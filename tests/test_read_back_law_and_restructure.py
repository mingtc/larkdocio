"""THE READ-BACK LAW, THE NO-MOVE ABSENCE AND THE WRITE ROUTER (LD-471).

Round 4's two most expensive incidents were the same incident twice: **the library told the
truth and nobody read it.** A batch recorded a typed refusal per entry and a caller discarded
the log; a batch of inserts landed in an order the plan never described, with every entry
``applied`` and no refusal anywhere, and only a re-read found it. The guide is what taught
those callers that a green run was a receipt.

What this module pins, and why each half is here rather than in a neighbour:

* **The law exists once, and every write recipe reaches it.** A rule stated in one recipe is a
  rule the next consumer does not meet, which is exactly how the no-move fact stayed buried in
  another recipe's prose for four releases.
* **Every write recipe models reading the ``ApplyLog``** — both sides of it, the landed and
  the refused, because a log read that only counts successes is the failure being cured.
  Behaviour belongs to ``apply()`` itself (it raises unless the caller opts into partial) and
  is pinned in ``tests/test_apply_refusal_policy.py``; this module owns only the DOCS half,
  and deliberately does not restate that rule in different words.
* **The router routes both directions.** The door every write consumer is told to start at
  named no recipe for the most common surgical job — change part of a paragraph — so a
  consumer who obeyed it silently lost styling. An omission there is the most expensive kind,
  so both directions are held: every recipe a row names exists, and every docx-write recipe is
  either reachable from the router or declared here as not-a-destination, with its reason.
* **The no-move absence is a contract-level fact** with its verification label, in the two
  places the question gets asked (the router, and ``capabilities()``).
* **The diff recipe finishes its own title**, with its bound check inside the pasteable code.
* **The ``revision=0`` claim is measured, on both parameters that carry the name.**
"""
import difflib
import re

import pytest

import guide_recipes as gr
from larkdocio import capabilities, guide, guide_sections

LAW_HEADING = "The read-back law — a green apply is not a receipt"
RESTRUCTURE_HEADING = ("Recipe: reorganise a document — there is no move, so a reorder is "
                       "delete-and-recreate")
ROUTER_HEADING = ("Which write recipe do you need? — add, change, update or delete content "
                  "in a document")
SUBSPAN_HEADING = "Recipe: edit part of a paragraph (a sub-span edit)"

#: The docx-write recipes that are deliberately NOT routing destinations, each with the reason
#: it is not one. A new docx-write recipe joins this list or joins the router — the point is
#: that the choice is made, once, by someone who thought about it.
NOT_A_ROUTING_DESTINATION = {
    "the-docx-write-handshake":
        "IS a destination — two rows point at it (delete a block, patch a table cell), and it "
        "is also the mechanism every other row's recipe runs on",
    "verify-what-you-authored-compose-equivalence-not-string-equality":
        "what you do AFTER a write, not a write you choose between",
    "anchor-a-follow-up-by-a-created-block-id":
        "an anchoring technique the other recipes use, reached from them, not a job",
    "edit-a-code-block-s-text":
        "a case of the whole-block change row (its target happens to be a code block); it is "
        "reached from the sub-span recipe and from the block-kind table",
    "leave-a-comment-on-a-document-and-take-it-back":
        "writes the review conversation, not the document body the router is about",
    "accumulate-edits-across-turns-a-multi-turn-request-queue":
        "a batching pattern over the rows above, not a fifth thing to do to a document",
    "reorganise-a-document-there-is-no-move-so-a-reorder-is-delete-and-recreate":
        "IS a destination — asserted separately below, because its row is this issue's own",
    "write-into-an-empty-document":
        "IS a destination — the first row",
    "a-rate-limit-interrupted-your-rewrite-and-the-re-push-refuses-stale-anchor-the-"
    "idempotent-repair":
        "a REPAIR for a write that already happened and stopped part-way, not one of the four "
        "jobs the router asks you to choose between — you arrive at it from a refusal, not "
        "from a decision. The recipe cites the reorganisation row rather than competing with "
        "it, which is the one route a consumer could confuse it with",
}


def _live_code(source):
    """*source* with every ``#`` comment stripped — a call named in a comment is not a call."""
    return "\n".join(line.split("#")[0] for line in source.splitlines())


def _recipe_text(slug):
    """The recipe's WHOLE section — preamble, code and the notes under it.

    Not ``recipe_preamble``, which stops at the first fence: the law pointer is a closing
    line, and a check that could not see it would be checking half the recipe.
    """
    heading = next(h for h in gr.recipe_headings() if gr._slug(h) == slug)
    return guide("Recipe: " + heading)


#: The opening words of the law POINTER a recipe closes with. Named once, here, because two
#: arms below share it: the population arm (a recipe that points at the law must be one this
#: file guards) and, by :func:`_reaches_the_law`, the check itself.
LAW_POINTER = "**The read-back law applies here**"

#: The calls that make a recipe a WRITE recipe — the population every arm in this file is
#: parametrized over.
#:
#: **Widened by LD-541 from ``apply|schema_apply|apply_field_migration`` alone, and the reason
#: is a measured hole rather than a tidy-up.** The guide restructure's safety-net check asked
#: the question this file exists to answer — *would anything catch a recipe silently losing its
#: read-back-law warning?* — and derived the census: **41** level-3 sections carried the law
#: pointer, and **40** of them were inside this population. The one outside it was
#: ``recipe-attach-a-file-to-a-document-the-attachment-card``, which mutates a document through
#: ``put_file_in_document(`` and never touches ``apply(`` at all. So one shipped recipe could
#: have dropped its warning in silence. The ``put_*_in_document`` verbs are document mutations
#: by the same contract ``apply()`` is held to — the block is created, and only a re-read says
#: what the document now contains — so they belong in the population, not in an exception list.
_MUTATING_CALL = re.compile(
    r"\b(apply|schema_apply|apply_field_migration|put_file_in_document|put_image_in_document)\("
)


#: The plan-through-``apply`` calls alone — the subset that really produces an ``ApplyLog``.
#: The log arms below are parametrized over THIS and not over :data:`_MUTATING_CALL`, because
#: ``put_file_in_document`` hands back a bound block rather than a log: asking it to "read both
#: sides of the log" would be asking a recipe to read an object the call does not return. The
#: LAW, by contrast, applies to both — which is why the two populations are separate constants
#: with separate reasons rather than one list doing two jobs.
_PLAN_GATED_CALL = re.compile(r"\b(apply|schema_apply|apply_field_migration)\(")


def _recipes_calling(pattern):
    out = []
    for slug, blocks in gr.recipe_blocks().items():
        code = _live_code("\n".join(block.source for block in blocks))
        if pattern.search(code):
            out.append(slug)
    return sorted(out)


#: Every recipe whose LIVE code mutates a document — the population the LAW covers.
WRITE_RECIPES = _recipes_calling(_MUTATING_CALL)

#: Every recipe that really produces an ``ApplyLog`` — the population the LOG arms cover.
PLAN_GATED_RECIPES = _recipes_calling(_PLAN_GATED_CALL)


def _docx_write_recipes():
    out = []
    for slug, blocks in gr.recipe_blocks().items():
        code = _live_code("\n".join(block.source for block in blocks))
        if re.search(r"from larkdocio\.write\b|import larkdocio\.write\b", code):
            out.append(slug)
    return sorted(out)


def _router_rows():
    body = guide(ROUTER_HEADING)
    rows = [line for line in body.splitlines() if line.startswith("|")]
    return [row for row in rows if not set(row) <= set("|- :")][1:]


def _cited_recipes(text):
    """Every ``§ "Recipe: …"`` citation in *text*, resolved to the recipe slug it names.

    A citation may name the heading up to its parenthetical (*"link a file from a sentence"*
    for a heading that goes on to quote the sentence itself), so resolution is by **unique
    prefix**: a citation that matches no recipe, or two, comes back as the raw slug and
    reddens the caller — which is the failure this exists to catch.
    """
    known = {gr._slug(heading) for heading in gr.recipe_headings()}
    out = set()
    for name in re.findall(r'§ "Recipe:\s*([^"]+)"', text):
        slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
        matches = [k for k in known if k == slug] or [k for k in known if k.startswith(slug)]
        out.add(matches[0] if len(matches) == 1 else slug)
    return out


# --------------------------------------------------------------------------- #
# AC1 — the law is stated ONCE, with its evidence, and it is not a library step #
# --------------------------------------------------------------------------- #

def test_ac1_the_law_is_a_section_a_consumer_can_be_pointed_at():
    slugs = {row["heading"]: row["slug"] for row in guide_sections()}
    assert LAW_HEADING in slugs, sorted(slugs)[:5]
    assert guide(section=slugs[LAW_HEADING]).strip(), "the law section is empty"


def test_ac1_the_law_names_BOTH_incidents_that_earned_it():
    """A rule with no evidence is a preference. Both shapes are named because they fail
    differently: one is a refusal the caller can ignore, the other is a clean log over a wrong
    document — and a reader who has only met the first will trust a refusal-free run."""
    text = guide(LAW_HEADING).lower()
    assert "ambiguous" in text and "refus" in text, text[:400]
    assert "order" in text and "no refusal anywhere" in text, text[:400]
    assert "a clean log has never been evidence of a correct document" in text


def test_ac1_the_law_says_it_is_YOURS_to_run_not_the_librarys():
    """The library does not silently re-download for anyone: a read is a call, and spending
    one the caller did not ask for is not a library's decision. Stated, or the rule reads as
    a promise that something else is checking."""
    text = guide(LAW_HEADING).lower()
    assert "not a step the library takes for you" in text
    assert "silently re-download" in " ".join(text.split())


def test_ac1_the_law_does_not_RESTATE_what_apply_does_about_a_refusal():
    """The behaviour is one rule with one home (the handshake recipe). A second wording of it
    here is worse than no wording: two statements of one contract drift."""
    text = guide(LAW_HEADING)
    assert '§ "Recipe: the docx write handshake"' in text
    assert "allow_partial" not in text, (
        "the law spells the opt-in itself — cross-reference the handshake instead, so the "
        "behaviour has exactly one authoring")


def _reaches_the_law(text):
    """THE CHECK ITSELF, as a predicate over the recipe's text.

    Extracted (LD-512) for one reason: its ``…_BITES`` twin at the foot of this file used to
    assert ``LAW_HEADING not in crippled`` — a statement about ``str.replace``, which never ran
    this check against anything. Now both the real guard below and the BITES proof call this,
    so a hole opened here is watched opening from both sides.
    """
    return LAW_HEADING in text


@pytest.mark.parametrize("slug", WRITE_RECIPES)
def test_ac1_every_write_recipe_reaches_the_law(slug):
    assert _reaches_the_law(_recipe_text(slug)), (
        f"write recipe {slug!r} neither performs the read-back nor points at the law — a "
        "consumer who pastes it learns that a green apply is a receipt")


def test_every_section_that_POINTS_AT_the_law_is_INSIDE_the_guarded_population():
    """**Residual zero, and no literal to re-cut** — the arm above only reaches the recipes
    :data:`WRITE_RECIPES` names, so its own reach is the half it cannot demonstrate.

    The claim: any guide section that closes with :data:`LAW_POINTER` is a write recipe this
    file already guards. A section that points at the law but sits outside the population is a
    warning nobody watches — which is exactly the hole LD-541's safety-net check found and
    :data:`_MUTATING_CALL` closed. Stated as a set relation rather than a count, so it needs no
    re-cut when a recipe lands: the census moves and the assertion does not.
    """
    guarded = set(WRITE_RECIPES)
    strays = []
    for row in guide_sections():
        if row["level"] != 3 or LAW_POINTER not in guide(section=row["slug"]):
            continue
        slug = row["slug"][len("recipe-"):] if row["slug"].startswith("recipe-") else row["slug"]
        if slug not in guarded:
            strays.append(row["slug"])
    assert not strays, (
        f"{len(strays)} guide section(s) point at the read-back law but are outside the "
        f"population every arm in this file is parametrized over: {strays} — each could drop "
        "its warning in silence. Widen _MUTATING_CALL to the verb the recipe really calls, or "
        "say in writing why that section is not a write recipe")


# --------------------------------------------------------------------------- #
# AC2 / AC3 — the recipes model reading the log, through the REAL accessors    #
# --------------------------------------------------------------------------- #

#: Read off ``larkdocio.write.model.applylog`` rather than invented: the accessors a recipe is
#: allowed to teach are the ones the object really has (AC3 — if the docs need something the
#: code does not have, report, do not build).
LANDED_READS = ("for entry in log", ".applied", ".entries", "len(log", "entry.outcome")
REFUSED_READS = ("LarkApplyRefusedError", ".refusals", "refusal.reason", "refusal.detail")


def _reads_both_sides_of_the_log(code):
    """``(reads_landed, reads_refused)`` — THE CHECK ITSELF, over a recipe's source.

    Extracted by LD-512 for the same reason :func:`_reaches_the_law` is: the BITES twin below
    asserted that removing the tokens removed the tokens, and never asked this question of the
    crippled text.
    """
    return (any(token in code for token in LANDED_READS),
            any(token in code for token in REFUSED_READS))


@pytest.mark.parametrize("slug", PLAN_GATED_RECIPES)
def test_ac2_every_write_recipe_reads_BOTH_SIDES_of_the_log(slug):
    code = "\n".join(gr.recipe_sources(slug))
    landed, refused = _reads_both_sides_of_the_log(code)
    assert landed, f"{slug!r} never reads what LANDED: {LANDED_READS}"
    assert refused, (
        f"{slug!r} never reads what was REFUSED — the half the marathon caller discarded: "
        f"{REFUSED_READS}")


def test_ac3_the_accessors_the_recipes_teach_are_the_ones_the_LOG_REALLY_HAS():
    """The ``TypeError``-after-a-live-write is what this asserts against: every idiom the
    recipes model is exercised here on a real ``ApplyLog``, so a recipe cannot teach a call
    that does not exist."""
    from larkdocio.write.model.applylog import ApplyLog, ApplyLogEntry
    from larkdocio.write.model.refusal import Refusal

    entry = ApplyLogEntry.applied(anchor={"kind": "by-id", "block_id": "b"},
                                  block_id="b", before="a", after="b")
    refused = ApplyLogEntry.refused(anchor={"kind": "by-id", "block_id": "c"},
                                    refusal=Refusal.not_found("nothing matched 'x'"))
    log = ApplyLog(entries=(entry, refused))
    assert list(log) == [entry, refused]          # iteration — the idiom that used to raise
    assert len(log) == 2
    assert log.applied == (entry,)
    assert log.refusals == (refused,)
    assert refused.refusal.reason and refused.refusal.detail


# --------------------------------------------------------------------------- #
# AC4 — the no-move absence, in the two places the question is asked           #
# --------------------------------------------------------------------------- #

def _absence():
    rows = capabilities(full=True)["surfaces"]["docx-write"]["absences"]
    return next(row for row in rows if row["id"] == "no-move-or-reorder-operation")


def test_ac4_the_absence_is_a_CAPABILITY_row_with_its_verification_label():
    row = _absence()
    assert row["verification"] == "derived-from-shipped-code", row
    assert "no move or reorder operation" in row["statement"].lower()
    assert "delete-and-recreate" in row["statement"].lower()


#: The words the ORIGINAL form of this guard required in the row's ``evidence`` — *"whether
#: LARK ships such a route is a different question and was not probed"*. **The REASON that
#: assertion existed is preserved and still binding**: the row's ``statement`` is about what
#: larkdocio ships, so it may not be dressed in a label its own half did not earn. Only the
#: CONCLUSION is superseded — the question *was* probed, on 2026-08-16, over eleven enumerated
#: candidate spellings, so requiring the row to keep calling it unmeasured would now require it
#: to ship a false sentence. The guard is therefore TRANSFORMED, not deleted
#: (``process/doctrine/supersession.md`` § A.1): it still refuses the over-label, and it now
#: also refuses the stale disclaimer.
_SUPERSEDED_DISCLAIMER = "unmeasured, not refuted"


def test_ac4_the_row_no_longer_calls_LARKS_side_of_the_question_unmeasured():
    """The transformed half of the guard above. The measurement exists; the disclaimer is a
    false sentence now, and a shipped machine-readable string is exactly where it would rot
    unnoticed."""
    row = _absence()
    assert _SUPERSEDED_DISCLAIMER not in row["evidence"].lower(), (
        "the row still ships the superseded disclaimer — Lark's side of the question was "
        "measured over eleven enumerated candidate spellings")


def test_ac4_the_rows_two_facts_wear_their_OWN_strengths():
    """Two facts of different strength in one row: larkdocio's closed request-family set
    (derived) and Lark's absence (measured). The weaker label stays on the row, because
    promoting it would claim larkdocio's own absence was established by a live call."""
    row = _absence()
    evidence = row["evidence"].lower()
    assert row["verification"] == "derived-from-shipped-code"
    assert "derived-from-shipped-code" in evidence, (
        "the row's own label has to be legible inside the evidence too, or a reader cannot "
        "tell which half of the sentence it covers")
    assert "measured" in evidence and "eleven" in evidence
    assert "docx v1" in evidence, "the measured claim is about ONE API version"


def test_ac4_the_measured_half_carries_its_SCOPE_and_its_unmeasured_list():
    """A negative claim about somebody else's API may not exceed the evidence's scope."""
    evidence = _absence()["evidence"].lower()
    for phrase in ("one tenant", "2026-08-16", "tenant_access_token", "larksuite.com",
                   "user_access_token", "wiki-wrapped", "internal reorder api",
                   "outside the eleven"):
        assert phrase in evidence, phrase


def test_ac4_the_row_ships_the_code_0_COPY_TRAP():
    """The sharpest thing the measurement found: a success code that means 'duplicated'."""
    evidence = _absence()["evidence"]
    assert "temporary_block_id" in evidence
    assert "code 0" in evidence
    assert "duplicate" in evidence.lower()
    assert "order was unchanged" in evidence.lower()


def test_ac4_the_evidence_states_its_provenance_even_though_the_files_are_gone():
    """SUPERSEDED IN PART by LD-676 (2026-09-18 prune). The reason stands: a negative claim must
    say where its evidence is, so a reader can tell measured from asserted. The conclusion moved:
    the probe's verdict and captures were pruned, so the note may no longer CITE them (a
    dangling path is LD-675's defect) — it must instead SAY they were retired, and carry its
    scope in full so the negative claim does not exceed what is stated."""
    from larkdocio.common.citations import dev_repo_paths

    evidence = _absence()["evidence"]
    assert "retired from the dev repo on 2026-09-18" in evidence, evidence
    assert "the eleven" in evidence and "UNMEASURED" in evidence
    assert not dev_repo_paths(evidence), "it cites a path — which one survived the prune?"


def test_ac4_the_absence_names_the_REAL_request_families_read_off_the_code():
    from larkdocio.write import (
        DeleteRequest,
        EditRequest,
        InsertRequest,
        SubSpanEditRequest,
    )

    statement = _absence()["statement"]
    for cls in (EditRequest, InsertRequest, DeleteRequest, SubSpanEditRequest):
        assert cls.__name__ in statement, cls.__name__
    assert "marker-order-changed" in statement, (
        "the reconciler's own refusal reason is the other side of the same absence")


def test_ac4_the_absence_points_at_a_guide_section_that_EXISTS():
    slugs = {row["slug"] for row in guide_sections()}
    named = re.search(r'guide\(section="([^"]+)"\)', _absence()["instead"]).group(1)
    assert named in slugs, named


def test_ac4_the_router_states_the_absence_where_the_question_is_asked():
    """Not inside a recipe's prose, which is where it lived and where nobody found it."""
    router = guide(ROUTER_HEADING)
    assert "THERE IS NO MOVE" in router
    assert "delete-and-recreate" in router.lower()
    assert '["absences"]' in router, "the router must name the machine-readable form"


def test_the_router_note_states_LARKS_absence_as_a_MEASUREMENT_not_as_an_unknown():
    """The note used to say Lark's side was *"unmeasured, not refuted — nothing here was
    probed for one"*. It was probed. A consumer deciding whether to wait for a move operation
    was being served by a sentence a measurement had overtaken."""
    router = guide(ROUTER_HEADING)
    assert "nothing here was probed for one" not in router
    assert "Verification label: measured" in router
    assert "eleven enumerated" in router
    assert "2026-08-16" in router


def test_the_router_note_states_the_MEASUREMENTS_SCOPE_and_what_it_did_NOT_cover():
    """A negative claim about somebody else's API carries the edge of its own evidence, or it
    is an over-claim. Both halves are asserted: what was covered, and what was not."""
    router = guide(ROUTER_HEADING)
    for covered in ("One\ntenant", "tenant_access_token", "larksuite.com", "created and"):
        assert covered in router, covered
    for uncovered in ("user_access_token", "wiki-wrapped", "internal reorder API",
                      "outside the\neleven"):
        assert uncovered in router, uncovered
    assert "unmeasured — neither refuted nor supported" in router


def test_the_router_note_ships_the_code_0_COPY_TRAP_where_a_consumer_would_fall_into_it():
    """The single most consumer-relevant thing the measurement found, and the reason stating
    the absence alone was not enough: the descendant route answers SUCCESS to a request that
    duplicates rather than moves."""
    router = guide(ROUTER_HEADING)
    assert "DOES NOT MEAN \"MOVED\"" in router
    assert "temporary_block_id" in router
    assert "block_id_relations" in router
    assert "order was **unchanged**" in router
    assert "ships\n> a duplicate" in router


def test_the_no_move_note_states_its_provenance():
    """SUPERSEDED IN PART by LD-676 — same reason, new conclusion as the arm above: the router's
    no-move note must still account for its evidence, now by saying it was retired."""
    router = guide(ROUTER_HEADING)
    assert "retired from the dev repo on 2026-09-18" in router, "the measurement's provenance is not stated at all"


def test_ac3_the_restructure_recipes_PREMISE_is_the_measurement_and_its_STEPS_are_UNTOUCHED():
    """A premise correction, not a rewrite. The recipe was right; only its reason for being
    right was weaker than the evidence now available — so the five steps keep their order and
    their reasons, and the heading is not renamed (every citation of it resolves by slug)."""
    recipe = guide(RESTRUCTURE_HEADING)
    assert "the premise is a measurement, not an inference" in recipe
    assert "eleven enumerated candidate spellings" in recipe
    assert "unmeasured, not refuted" in recipe, "the untried spellings stay disclosed"
    openers = [
        "**Comments FIRST, before anything is written.**",
        "**Insert the new content BEFORE deleting the old, never the reverse.**",
        "**Respect the insert cap.**",
        "**Preserve identity where you can",
        "**Verify by reading the order back**",
    ]
    positions = [recipe.index(opener) for opener in openers]
    assert positions == sorted(positions), "the five steps changed order"
    assert "**The five steps, and why each is not optional.**" in recipe


def test_ac3_the_restructure_recipes_HEADING_still_resolves_at_the_slug_everything_cites():
    """A rename would break `_DOCX_NO_MOVE_ABSENCE["instead"]` and every other citation the
    guide's own resolver walks."""
    slug = "recipe-reorganise-a-document-there-is-no-move-so-a-reorder-is-delete-and-recreate"
    assert slug in {row["slug"] for row in guide_sections()}
    assert slug in _absence()["instead"]


# --------------------------------------------------------------------------- #
# AC6 — the router routes, in BOTH directions                                  #
# --------------------------------------------------------------------------- #

def test_ac6_every_recipe_the_router_names_EXISTS():
    known = {gr._slug(heading) for heading in gr.recipe_headings()}
    cited = _cited_recipes(guide(ROUTER_HEADING))
    assert cited <= known, sorted(cited - known)


def _is_routed_or_declared(slug, router_body):
    """THE CHECK ITSELF, over whatever router text it is handed.

    Taking the router body as an argument (LD-512) is what lets the BITES twin below hand it a
    router with one real citation cut out and watch this answer ``False`` — the old twin asked
    whether an invented name was absent from a set it had just built, which no edit to the
    shipped router could ever have falsified.
    """
    return slug in _cited_recipes(router_body) or slug in NOT_A_ROUTING_DESTINATION


@pytest.mark.parametrize("slug", _docx_write_recipes())
def test_ac6_every_docx_write_recipe_is_routed_or_declared(slug):
    assert _is_routed_or_declared(slug, guide(ROUTER_HEADING)), (
        f"{slug!r} is a docx-write recipe the router does not name and this module does not "
        "declare — decide which it is, in writing. The router is the door every write "
        "consumer is told to start at, so an omission there is the most expensive kind")


def test_ac6_the_declarations_are_not_STALE():
    routed = _cited_recipes(guide(ROUTER_HEADING))
    known = {gr._slug(heading) for heading in gr.recipe_headings()}
    for slug, reason in NOT_A_ROUTING_DESTINATION.items():
        assert reason.strip(), slug
        assert slug in known, f"{slug!r} is declared but is no longer a recipe"
        if slug in routed:
            assert reason.startswith("IS a destination"), (
                f"{slug!r} is routed by the router AND declared not-a-destination")


def test_ac6_the_partial_paragraph_row_exists_and_states_the_CONSEQUENCE_where_it_is_chosen():
    """The row is only half the fix: the reason to take it — that the whole-block route
    flattens styling and says nothing — has to be at the point of choice, not three sections
    away inside the recipe it routes to."""
    row = next(r for r in _router_rows() if "PART of a paragraph" in r)
    assert '§ "Recipe: edit part of a paragraph (a sub-span edit)"' in row
    assert "flatten" in row.lower() and "unstyled" in row.lower(), row
    assert "applied" in row, (
        "the row must say the flattening is logged as a SUCCESS — that is why a green run "
        "never discloses it")


def test_ac6_the_restructure_row_exists_and_names_the_contract():
    row = next(r for r in _router_rows() if "Reorganise the whole document" in r)
    assert f'§ "{RESTRUCTURE_HEADING}"' in row
    assert "no move" in row.lower()


def test_ac6_the_subspan_recipes_own_warning_and_the_router_agree():
    """The defect was that they disagreed: the recipe said the whole-block route flattens
    styling and the router routed you to it anyway."""
    assert "flatten" in guide(SUBSPAN_HEADING).lower()


# --------------------------------------------------------------------------- #
# AC5 — the restructure recipe teaches the five steps, in order                #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("claim,phrases", [
    ("comments first", ("comments first", "orphan")),
    ("insert before delete", ("insert the new content before deleting", "duplication")),
    ("the cap", ("max_children_per_call", "insert cap")),
    ("identity", ("longest common subsequence",)),
    ("read-back asserts order", ("verify by reading the order back", "final order")),
])
def test_ac5_the_restructure_recipe_teaches_each_step_with_its_reason(claim, phrases):
    text = guide(RESTRUCTURE_HEADING).lower()
    missing = [phrase for phrase in phrases if phrase not in text]
    assert not missing, f"the {claim} step is missing {missing}"


def test_ac5_the_restructure_recipe_is_EXECUTED_not_merely_shipped():
    """The recipe runs end to end under the offline harness — its post-conditions live in
    ``guide_recipes._check_restructure`` and are exercised by ``test_discovery_truth``. This
    asserts the wiring exists, so the recipe cannot be shipped un-run."""
    specs = {spec.slug for spec in gr.RECIPE_SPECS}
    assert gr._slug(RESTRUCTURE_HEADING.split("Recipe: ", 1)[1]) in specs


def test_ac5_the_recipes_code_does_the_two_applies_in_the_taught_order():
    code = "\n".join(gr.recipe_sources(
        gr._slug(RESTRUCTURE_HEADING.split("Recipe: ", 1)[1])))
    inserts = code.index("InsertRequest(\n        reference=AnchorById(block_id=anchor")
    deletes = code.index("DeleteRequest(target=AnchorById(block_id=block_id))")
    assert inserts < deletes, "the recipe deletes before it inserts — that is the hole"
    assert code.index("comments(doc_token)") < inserts, (
        "the comments read must come before anything is written; it is the only moment the "
        "orphan risk can still change the plan")


# --------------------------------------------------------------------------- #
# AC8 — the diff recipe produces a diff, and guards its own pin                #
# --------------------------------------------------------------------------- #

DIFF_HEADING = ("Recipe: diff a named edition against head (pin a semantic version, not a "
                "keystroke counter)")
DIFF_SLUG = "diff-a-named-edition-against-head-pin-a-semantic-version-not-a-keystroke-counter"


def _produces_a_textual_diff(code):
    """THE CHECK ITSELF, over the diff recipe's source (LD-512).

    The twin below used to run ``difflib.unified_diff`` on two hand-written lists — a test of
    the standard library, which has its own. Now it runs *this* against a recipe crippled into
    exactly the boolean compare the check names.
    """
    return ("import difflib" in code
            and "difflib.unified_diff(" in code
            and "changed = then_markdown != now_markdown" not in code)


def test_ac8_the_runnable_code_produces_a_TEXTUAL_diff():
    code = "\n".join(gr.recipe_sources(DIFF_SLUG))
    assert "import difflib" in code and "difflib.unified_diff(" in code
    assert "changed = then_markdown != now_markdown" not in code, (
        "a recipe titled 'diff' that returns a boolean is three standard-library lines short "
        "of its own title")


def test_ac8_the_bound_check_is_IN_the_pasteable_code_not_beside_it():
    code = "\n".join(gr.recipe_sources(DIFF_SLUG))
    assert "read_document_revision(doc_token)" in code
    assert "is past head" in code, "the refusal message a bad pin gets"
    assert code.index("read_document_revision") < code.index("get_docx_content"), (
        "the bound must be read BEFORE the pin is spent on a content read — otherwise the "
        "over-range pin has already silently answered head")


def test_ac8_the_irreversibility_disclosure_sits_ABOVE_the_runnable_example():
    """It cost one reader permanent residue on somebody else's document by sitting below it."""
    section = guide(DIFF_HEADING)
    disclosure = section.index("PERMANENT RESIDUE")
    fence = section.index("```python")
    assert disclosure < fence, "the disclosure is below the example again"
    assert "no delete-version call" in section[disclosure:fence]


def test_ac8_a_document_that_really_moved_yields_a_NON_EMPTY_diff(monkeypatch, tmp_path):
    """The recipe run in the harness diffs a document nobody edited, so it prints "no change"
    — a true answer that proves nothing. Here head is made to genuinely differ between the
    pinned read and the head read (what the recipe's own "…the document goes on being
    edited…" comment describes), and the recipe must emit real diff LINES for it."""
    from larkdocio.read.parser import Parser

    gr.stage(monkeypatch, tmp_path)
    real = Parser.parse_docx_content
    seen = {"n": 0}

    def edited_head(self, doc_token, blocks):
        seen["n"] += 1
        text = real(self, doc_token, blocks)
        return text if seen["n"] == 1 else text + "\nA line somebody added since.\n"

    monkeypatch.setattr(Parser, "parse_docx_content", edited_head)
    ns = gr.run_recipe(DIFF_SLUG)
    assert ns["changed"] is True
    assert any(line.startswith("+A line somebody added since.") for line in ns["diff"]), (
        ns["diff"])
    assert ns["diff"][0].startswith("--- V1.3 (revision "), ns["diff"][:2]


# --------------------------------------------------------------------------- #
# AC9 — the revision=0 claim, MEASURED on both parameters that carry the name  #
# --------------------------------------------------------------------------- #

def test_ac9_the_READ_pin_really_is_refused_locally_before_a_call_is_spent():
    """Round 4 reported this claim false. Re-measured: it is TRUE of this parameter. The gate
    is a pure function reached before any client exists, so "no call is spent" is not a claim
    about a fixture — there is nothing there to call."""
    from larkdocio.read.history import HistoricalReadRefusedError, check_revision_pin

    with pytest.raises(HistoricalReadRefusedError) as zero:
        check_revision_pin(0)
    assert zero.value.code == 1770001, zero.value.code
    for bad in (-1, -5, "3", 3.0, True):
        with pytest.raises(HistoricalReadRefusedError) as refused:
            check_revision_pin(bad)
        assert refused.value.code == 99992402, (bad, refused.value.code)
    assert check_revision_pin(1) == 1


def test_ac9_the_WRITE_PLAN_parameter_of_the_same_name_is_NOT_refused():
    """…and this is what a reader who tried it on a plan actually met. Same spelling, different
    parameter, different — and deliberate — answer: the guard reports itself unavailable rather
    than arming on a number that cannot order two states."""
    from larkdocio.write import revision_guard_status

    assert revision_guard_status(0) == "unavailable"
    assert revision_guard_status(-1) == "unavailable"
    assert revision_guard_status(None) == "unavailable"
    assert revision_guard_status(1) == "active"


def test_ac9_the_guide_states_BOTH_measurements_and_scopes_the_claim():
    section = guide(DIFF_HEADING)
    assert "TWO parameters with one name" in section
    assert "1770001" in section and "99992402" in section
    assert "revision_guard" in section and "unavailable" in section
    assert "on THIS parameter" in "\n".join(gr.recipe_sources(DIFF_SLUG)), (
        "the in-code comment must scope itself to the read pin, which is the whole correction")


# --------------------------------------------------------------------------- #
# The guards bite — one red proof per class                                    #
# --------------------------------------------------------------------------- #

# All four were **decorative** until LD-512: each asserted something about the crippling it had
# just performed (``str.replace`` removes what it replaces; an invented name is absent from a set
# built without it; ``difflib`` diffs) and none of them ever ran the guard it is named after
# against the crippled text. So a hole opened in any of the four real checks above left its
# own BITES proof green — the exact class the 2026-08 audit was written to find. Each is now
# TRANSFORMED, not pruned: same node id, same claim, but the claim is now made by calling the
# real predicate (:func:`_reaches_the_law`, :func:`_reads_both_sides_of_the_log`,
# :func:`_is_routed_or_declared`, :func:`_produces_a_textual_diff`) — once on the shipped text,
# where it must hold, and once on a crippled copy, where it must not.


def test_the_law_pointer_guard_BITES():
    """Delete the citation from one recipe's text and **the real check** reports it."""
    slug = WRITE_RECIPES[0]
    text = _recipe_text(slug)
    assert _reaches_the_law(text), f"{slug!r} does not reach the law even before crippling"
    crippled = text.replace(LAW_HEADING, "something else entirely")
    assert crippled != text, "nothing was crippled — the proof would be vacuous"
    assert not _reaches_the_law(crippled), (
        "the law-pointer check passed a recipe whose law citation was removed")


def test_the_log_reading_guard_BITES():
    """Remove the refused-side accessors and **the real check** reports that half missing."""
    code = "\n".join(gr.recipe_sources("the-docx-write-handshake"))
    assert _reads_both_sides_of_the_log(code) == (True, True), (
        "the handshake recipe does not read both sides even before crippling")
    crippled = code
    for token in REFUSED_READS:
        crippled = crippled.replace(token, "REMOVED")
    assert crippled != code, "nothing was crippled — the proof would be vacuous"
    landed, refused = _reads_both_sides_of_the_log(crippled)
    assert landed and not refused, (
        "the log-reading check passed a recipe that reads only what LANDED — the half the "
        "marathon caller discarded")


def test_the_router_direction_guard_BITES():
    """A docx-write recipe that is neither routed nor declared is the failure this catches —
    so the router is crippled by cutting a REAL recipe's citation out of it, and **the real
    check** is asked about that recipe again."""
    router = guide(ROUTER_HEADING)
    routed = sorted(slug for slug in _docx_write_recipes()
                    if slug in _cited_recipes(router) and slug not in NOT_A_ROUTING_DESTINATION)
    assert routed, "no docx-write recipe is routed-and-not-declared — nothing to cripple"
    slug = routed[0]
    assert _is_routed_or_declared(slug, router)
    crippled = "\n".join(line for line in router.splitlines()
                          if not (line.startswith("|") and slug in _cited_recipes(line)))
    assert crippled != router, "the router lost no row — the proof would be vacuous"
    assert not _is_routed_or_declared(slug, crippled), (
        f"the router-direction check still calls {slug!r} routed after its row was cut — an "
        "omission at the door every write consumer is told to start at would ship green")


def test_the_diff_is_a_real_unified_diff_and_not_a_string_compare():
    """The diff recipe crippled into the boolean compare its own check names, run through
    **the real check** — which is what makes this a proof about the recipe rather than about
    ``difflib``, whose contract the standard library tests for itself."""
    code = "\n".join(gr.recipe_sources(DIFF_SLUG))
    assert _produces_a_textual_diff(code), "the shipped diff recipe fails its own check"
    crippled = re.sub(r"^.*difflib\.unified_diff\(.*$",
                      "changed = then_markdown != now_markdown",
                      code, count=1, flags=re.M)
    assert crippled != code, "nothing was crippled — the proof would be vacuous"
    assert not _produces_a_textual_diff(crippled), (
        "a recipe titled 'diff' that returns a boolean passed the check that exists to say it "
        "is three standard-library lines short of its own title")
