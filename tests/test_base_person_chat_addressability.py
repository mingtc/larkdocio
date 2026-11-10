"""Person & chat addressability — the DISCLOSURE-ONLY rung (the Base relational spec § F1-S4).

This story ships **honesty instead of capability**, so almost every assertion here is a
*content* assertion over shipped text, plus two structural ones that are the whole reason the
story is safe to run beside another: **it adds no API-using call site** and **it authors no
second person refusal** — the landed one is asserted against instead.

The four things the wording has to get right, in the order a reader meets them:

1. **The product fact first.** An id-written person cell renders a **full name chip** in the
   Lark UI. The limitation is about *addressing* another user, never about how a written cell
   looks, and a consumer left believing an id-written cell shows an id has been misled by
   omission. So the chip sentence is asserted to come **before** the limitation, not merely to
   exist.
2. **The three honest id sources**, named: harvest one from a read, supply one the caller
   holds, or resolve the **account owner's own** through ``larkdocio.contacts``.
3. **The reach, without euphemism.** On the tenant this was measured against, the directory
   search returns only the account owner — and that is a statement about what *this library*
   can do, not a claim about what Lark forbids.
4. **The asymmetry.** A person cell round-trips through the **model**, which keeps the id it
   read, and **not** through the **Markdown**, which by the name-only doctrine does not.

The ``batch_get_id`` route is recorded ``deferred`` (**corrected by LD-347**, which found the
original ``uncaptured`` reading rested on a repo-wide negative drawn from a Base-pack-only
check): the route **has** been called from this repo and it **resolved another user's**
``open_id``, so the honest record is a measured capability nobody has built a verb for — and
the reach is stated as measured, n = 2 identifiers, never as tenant-wide. The
comprehensive-solution mandate behind the gap is
**cited, never restated**: one definition, in ``dev/downtime-queue.md``, and a test below holds
it there.
"""
import ast
import json
import re
import socket
from pathlib import Path

import pytest

import consumer_text
import front_door
import larkdocio
from larkdocio.base import cells, field_vocabulary, write_cells
from larkdocio.base.write_vocabulary import NON_WRITABLE_PAIRS

import guide_recipes

from guard_kit import REPO_ROOT
import private_tree  # noqa: E402  (LD-685)

SRC = REPO_ROOT / "src" / "larkdocio"
BASE_MD = REPO_ROOT / "BASE.md"
BASE_WRITE = "base-write"
BASE_WRITE_RECIPE_SLUG = "the-base-write-handshake"

#: The register rows this story appends, at the tail — nothing is renumbered.
_APPENDED_ROWS = (37, 38, 39)


# --------------------------------------------------------------------------- #
# Fixtures + tiny parsers (the register table is /BASE.md's own shape)          #
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def base_md():
    return BASE_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def caps():
    return larkdocio.capabilities(full=True)


@pytest.fixture(scope="module")
def write_note(caps):
    return _norm(caps["surfaces"][BASE_WRITE]["credentials"]["note"])


@pytest.fixture(scope="module")
def preamble():
    """The prose a consumer reads before pasting, whitespace-collapsed — the guide is
    hard-wrapped, and a content assertion must not depend on where a line broke."""
    return _norm(guide_recipes.recipe_preamble(BASE_WRITE_RECIPE_SLUG))


def _register_row(text, number):
    for line in text.splitlines():
        if line.strip().startswith(f"| {number} |"):
            return [cell.strip() for cell in line.strip().strip("|").split("|")]
    raise AssertionError(f"/BASE.md has no register row {number} — the append did not land")


def _row_text(text, number):
    return _norm(_register_row(text, number)[1])


def _status(text, number):
    return _register_row(text, number)[2].strip("`")


def _evidence(text, number):
    return _register_row(text, number)[3]


def _trigger(text, number):
    return _register_row(text, number)[4]


def _norm(text):
    """Whitespace-collapsed. The guide is hard-wrapped, so a phrase the prose really carries
    can still straddle a line break — content is what these tests are about, never wrapping."""
    return " ".join(text.split())


def _person_sentences(text):
    """The sentences that are ABOUT a person, a user or a chat.

    Scoped deliberately: the surrounding note says *"eight kinds of cell cannot be written at
    all"* about computed columns, which is both true and none of this story's business. A
    vocabulary check that swept the whole note would either fail on that sentence or be
    weakened until it proved nothing.
    """
    sentences = re.split(r"(?<=[.!?])\s+", _norm(text))
    wanted = ("person", "other user", "chat")
    return [s for s in sentences if any(word in s.lower() for word in wanted)]


def _before(haystack, first, second):
    """``first`` occurs, ``second`` occurs, and ``first`` comes first."""
    lowered = haystack.lower()
    left, right = lowered.find(first.lower()), lowered.find(second.lower())
    assert left != -1, f"missing: {first!r}"
    assert right != -1, f"missing: {second!r}"
    return left < right


# --------------------------------------------------------------------------- #
# AC1 — the round-trip asymmetry is disclosed                                  #
# --------------------------------------------------------------------------- #

def test_ac1_the_MODEL_keeps_the_id_and_the_MARKDOWN_does_not_in_every_shipped_surface(
        base_md, write_note, preamble):
    """The name-only doctrine's consequence, stated where a consumer meets it rather than
    left to be discovered by a failed round trip. The in-memory model exists, so the sentence
    names it instead of gesturing at "the read result"."""
    for label, text in (("BASE.md row 37", _row_text(base_md, 37)),
                        ("capabilities() base-write note", write_note),
                        ("guide() base-write recipe", preamble)):
        lowered = text.lower()
        assert "model" in lowered, label
        assert "markdown" in lowered, label
        assert "keeps the raw id" in lowered or "keeps the id" in lowered, label
        assert "a name is not an id" in lowered, label


def test_ac1_the_asymmetry_claim_is_TRUE_of_the_two_real_projections():
    """The wording is only honest if the code does what it says: the renderer emits the name
    and drops the id, and the structured read keeps it. Asserted, not assumed."""
    person = {"id": "ou_deadbeefdeadbeef", "name": "Ada Lovelace",
              "email": "ada@example.invalid"}
    field = cells.FieldSpec(field_name="Owner", type=11, ui_type="User")
    rendered = cells.render_cell([person], field)
    assert rendered == "Ada Lovelace"
    assert "ou_" not in rendered
    # …and the raw object a caller holds still carries the id the encoder needs.
    assert write_cells.encode_cell([{"id": person["id"]}], field) == [{"id": person["id"]}]


# --------------------------------------------------------------------------- #
# AC1b — the product fact comes FIRST                                          #
# --------------------------------------------------------------------------- #

def test_ac1b_the_FULL_NAME_CHIP_fact_is_stated_and_comes_BEFORE_the_limitation(
        base_md, write_note, preamble):
    """A consumer must never be left believing an id-written cell shows an id. The chip
    sentence is therefore required to *precede* the other-user-name limitation in the prose."""
    for label, text in (("BASE.md row 37", _row_text(base_md, 37)),
                        ("capabilities() base-write note", write_note),
                        ("guide() base-write recipe", preamble)):
        assert "full name chip" in text.lower(), label
        assert _before(text, "full name chip", "other user"), (
            f"{label}: the limitation is stated before the display fact, which leaves a "
            "reader believing an id-written cell renders an id")


def test_ac1b_the_chip_sentence_is_an_OBSERVATION_not_an_api_claim(base_md, write_note,
                                                                  preamble):
    """It is a statement about what the product shows, so it must not read as an API
    guarantee this library could be held to."""
    for label, text in (("BASE.md row 37", _row_text(base_md, 37)),
                        ("capabilities() base-write note", write_note),
                        ("guide() base-write recipe", preamble)):
        lowered = text.lower()
        assert "display is unaffected" in lowered or "the display is unaffected" in lowered, \
            label
        for overclaim in ("the api guarantees", "lark guarantees", "always renders"):
            assert overclaim not in lowered, (label, overclaim)


# --------------------------------------------------------------------------- #
# AC2 — the three honest id sources, and the real reach                        #
# --------------------------------------------------------------------------- #

def test_ac2_the_THREE_id_sources_are_named_in_every_shipped_surface(base_md, write_note,
                                                                    preamble):
    for label, text in (("BASE.md row 37", _row_text(base_md, 37)),
                        ("capabilities() base-write note", write_note),
                        ("guide() base-write recipe", preamble)):
        lowered = text.lower()
        assert "harvest" in lowered, f"{label}: source (i), harvest from a read"
        assert "caller already holds" in lowered or "already holds" in lowered, \
            f"{label}: source (ii), caller-supplied"
        assert "account owner" in lowered, f"{label}: source (iii), the account-owner case"
        assert "larkdocio.contacts" in text or "resolve_user" in text, label


def test_ac2_the_TENANT_REACH_is_stated_without_euphemism(base_md, write_note, preamble):
    """"Only the account owner" is the measured fact; anything softer is a euphemism for it."""
    for label, text in (("BASE.md row 37", _row_text(base_md, 37)),
                        ("capabilities() base-write note", write_note),
                        ("guide() base-write recipe", preamble)):
        lowered = text.lower()
        assert "only the account owner" in lowered, label
        assert "other user" in lowered, label


def test_ac2_the_wording_is_about_LARKDOCIO_not_about_what_lark_forbids(base_md, write_note,
                                                                       preamble):
    """The the Base read spec calibration, generalized to this surface: the library states what it does.
    A claim that Lark forbids it is a different claim, and a false one — the reach was
    measured on ONE tenant."""
    banned = ("lark forbids", "lark does not allow", "impossible", "can never",
              "no tenant can", "permanently")
    for label, text in (("BASE.md row 37", _row_text(base_md, 37)),
                        ("BASE.md row 38", _row_text(base_md, 38)),
                        ("capabilities() base-write note", write_note),
                        ("guide() base-write recipe", preamble)):
        lowered = text.lower()
        for claim in banned:
            assert claim not in lowered, (label, claim)
        assert "tenant" in lowered, f"{label}: the reach must be qualified to a tenant"


# --------------------------------------------------------------------------- #
# AC3 — batch_get_id is UNCAPTURED, and the mandate is CITED not duplicated    #
# --------------------------------------------------------------------------- #

def test_ac3_the_batch_get_id_row_records_the_route_AS_CALLED_and_its_TRIGGER_AS_FIRED(
        base_md):
    """LD-347 **transformed** this guard; it did not delete it.

    What it used to pin was the ``uncaptured`` slug plus the words *never* / *called* /
    *unknown* — a **repo-wide negative** (*"no pack has ever called this endpoint"*) that was
    already false when it landed: three committed captures dated 2026-07-30 call the route, and
    the 2026-08-08 round called it six more times and **resolved another user's id**, which is
    verbatim the revisit condition the row itself named.

    So the job is the same and the fact is the opposite. This now pins that the row records the
    route **as called**, cites the captures that call it, records the trigger **as fired**
    rather than deleting it, and states the reach **as measured** and never as tenant-wide. The
    banned phrasings are the exact shape of the original defect, so a future edit that
    re-generalises a scoped negative back into a repo-wide one reddens this again.
    """
    row, status, trigger = (_row_text(base_md, 38), _status(base_md, 38),
                            _trigger(base_md, 38))
    assert status == "deferred", (
        "`uncaptured` is spent — the route is probed and the answer is a capability, not a "
        "refusal — and `supported` would be false while no verb ships; `deferred` is the "
        f"register's own slug for captured-understood-and-not-built — got {status!r}")
    lowered = row.lower()
    assert "batch_get_id" in lowered
    assert "has been called" in lowered, (
        "the row must record that the route WAS called from this repo")
    assert "other user" in lowered and "resolved" in lowered, (
        "the decisive fact — another user's id resolved — belongs in the row")
    for banned in ("never been called", "no pack has ever called", "never called"):
        assert banned not in lowered, (
            f"the repo-wide negative is back in row 38: {banned!r}")
    assert "measured" in lowered and "tenant-wide" in lowered, (
        "the reach is stated AS MEASURED and the tenant-wide reading disclaimed by name")
    cited = row + _evidence(base_md, 38)
    for capture in ("P6-batch-get-id-real-READ.json", "B3-SECOND-USER-email-DECISIVE.json"):
        assert capture in cited, f"the row does not cite {capture}"
    lowered_trigger = trigger.lower()
    assert "fired" in lowered_trigger, (
        "a register RECORDS a trigger that fired — deleting it loses the fact that the row's "
        "own condition was met")
    assert "resolved" in lowered_trigger and "capture" in lowered_trigger, trigger


def test_ac3_the_row_points_at_the_deferred_investigation_WITHOUT_restating_its_terms(
        base_md):
    row = _row_text(base_md, 38)
    assert "dev/downtime-queue.md" in row, "the row must send a reader to the one definition"
    assert "roster" in row.lower() and "ruled out" in row.lower(), (
        "a roster/lookup table is ruled out BY NAME, so the row must not read as if one were "
        "the workaround in the meantime")


#: The mandate's own TERMS, assembled at runtime so this guard does not itself become a
#: second copy of the wording it is holding to one place.
_MANDATE_TERMS = (
    " ".join(("takes maintenance and it will", "look weird if I keep requesting")),
    " ".join(("not giving up on it but", "just deferring the investigation")),
    " ".join(("directory reach, batch_get_id", "semantics, caching posture")),
)

_MANDATE_HOME = "dev/downtime-queue.md"


def _tracked_text_files():
    """Every repository text file a maintainer or a consumer could read the terms from.

    ``progress/`` and ``requirements/`` are out for the reason they are out of the permission
    corpus: an issue file and a spec are historical statements of intent, and the ruling that
    *produced* the mandate is recorded in both by construction.
    """
    for path in sorted(REPO_ROOT.rglob("*")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if not path.is_file() or path.suffix not in {".md", ".py", ".txt", ".toml"}:
            continue
        if _out_of_tree(rel):
            continue
        yield rel, path.read_text(encoding="utf-8", errors="ignore")


def _out_of_tree(rel):
    """Is ``rel`` outside the corpus — a churn tree, build output, or the TRANSIENT
    ``larkdocio-<version>/`` sdist staging copy ``python -m build`` puts at the repo root
    (LD-353: under `-n auto` another worker walks the tree mid-build and would read the
    mandate's terms out of the staged duplicate, reporting two homes for one definition)."""
    if rel.startswith((".git/", ".venv/", ".kanban-wt/", ".worktrees/", "build/",
                       "dist/", "progress/", "requirements/", "src/larkdocio.egg-info/")):
        return True
    return front_door.is_build_staging(rel.split("/", 1)[0])


@private_tree.citations
def test_ac3_the_mandate_wording_lives_in_EXACTLY_ONE_PLACE():
    """One definition. A second copy in a shipped string, a docstring or a matrix row is a
    defect — it is the copy that goes stale when the investigation is scheduled."""
    for term in _MANDATE_TERMS:
        homes = sorted(rel for rel, text in _tracked_text_files() if term in text)
        assert homes == [_MANDATE_HOME], (
            f"the mandate term {term[:40]!r}... is stated in {homes} — it is authored in "
            f"{_MANDATE_HOME} and cited everywhere else")


def test_ac3_NO_SHIPPED_STRING_restates_the_mandate():
    """The consumer half of the same rule, over the corpus a wheel-only reader can reach."""
    offenders = []
    for label, text in consumer_text.consumer_corpus().items():
        for term in _MANDATE_TERMS:
            if term in text:
                offenders.append((label, term[:40]))
    assert not offenders, offenders


# --------------------------------------------------------------------------- #
# AC4 — the chat-id source is the easier twin, and it ships as a DISCLOSURE    #
# --------------------------------------------------------------------------- #

def test_ac4_the_chat_row_names_the_endpoint_its_scope_family_and_the_reach_caveat(base_md):
    row, status, trigger = (_row_text(base_md, 39), _status(base_md, 39),
                            _trigger(base_md, 39))
    assert status == "deferred", (
        "nothing refuses the chat list — the answer is a scope decision, which is exactly "
        f"what `deferred` means in this vocabulary; got {status!r}")
    lowered = row.lower()
    assert "im/v1/chats" in lowered, "the endpoint is named or the row is not actionable"
    assert "code:0" in lowered
    assert "one" in lowered and "chat" in lowered
    assert "readonly" in lowered or "read-only" in lowered, "the scope FAMILY must be named"
    assert "larkdocio.permissions" in row, (
        "a scope requirement is authored in one place; a row that names a family must send "
        "the reader there rather than spelling a scope string of its own")
    assert len(trigger) > 40


def test_ac4_the_row_is_a_POINTER_and_no_chat_lister_ships(base_md):
    """Under the disclosure-only ruling this is a documented route, not a shipped call —
    the same new-endpoint-family purchase that was declined for person."""
    assert "oc_" in _row_text(base_md, 39), "the GroupChat write shape is the point of the row"
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "im/v1/chats" in text or "ListChatRequest" in text:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert not offenders, f"a chat lister shipped after all: {offenders}"


def test_ac4_the_groupchat_encoder_is_LD_256s_and_is_only_CONSUMED_here():
    """Cited, never re-authored — the story owns no encoder."""
    field = cells.FieldSpec(field_name="Chat", type=23, ui_type="GroupChat")
    assert write_cells.encode_cell([{"id": "oc_x1"}], field) == [{"id": "oc_x1"}]


# --------------------------------------------------------------------------- #
# AC5 — PII discipline, re-asserted on this surface                            #
# --------------------------------------------------------------------------- #

#: The seven detectors AC5 names, as PROSE detectors rather than the capture sweep's
#: JSON-shaped ones (the text under test is sentences, not payloads).
_PROSE_PII = {
    "1-email": re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.invalid)[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "2-person-id": re.compile(r"\b(?:ou_|on_|ug_)[A-Za-z0-9]{6,}"),
    "3-chat-id": re.compile(r"\boc_[A-Za-z0-9]{6,}"),
    "4-avatar-or-cdn-url": re.compile(r"avatar[a-z_]*\s*[:=]\s*https?://"),
    "5-user-token": re.compile(r"\b(?:t-|u-)[A-Za-z0-9_.\-]{12,}"),
    "6-unredacted-en-name": re.compile(r"en_name\s*[:=]\s*\"?[A-Z]"),
    "7-tenant-host": re.compile(
        r"https?://(?!open\.|www\.)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)?"
        r"\.(?:larksuite|feishu)\.com"),
}


def test_ac5_the_sweep_really_is_SEVEN_detectors():
    assert len(_PROSE_PII) == 7, sorted(_PROSE_PII)


def test_ac5_nothing_this_story_ships_carries_a_person_or_chat_identifier(base_md, write_note,
                                                                         preamble):
    """Chat ids are tenant data of the same class as a person's, so the bar is identical on
    both — a placeholder is written ``oc_…``, never a plausible id."""
    hits = {}
    for label, text in (("BASE.md row 37", _row_text(base_md, 37)),
                        ("BASE.md row 38", _row_text(base_md, 38)),
                        ("BASE.md row 39", _row_text(base_md, 39)),
                        ("capabilities() base-write note", write_note),
                        ("guide() base-write recipe", preamble)):
        for name, pattern in _PROSE_PII.items():
            found = pattern.findall(text)
            if found:
                hits.setdefault(label, []).append((name, sorted(set(found))[:3]))
    assert hits == {}, f"PII sweep is NOT clean on this story's own text: {hits}"


_PERSON_BEARING = ((11, "User"), (23, "GroupChat"), (1003, "CreatedUser"),
                   (1004, "ModifiedUser"))


def _rendered_corpus():
    """Every person-bearing type PLUS ``automatic_fields``' record-level attribution."""
    person = {"id": "ou_deadbeefdeadbeef", "name": "Ada Lovelace", "en_name": "Ada English",
              "email": "ada@tenant.invalid",
              "avatar_url": "https://s1-imfile.example.invalid/avatar/x.png"}
    chat = {"id": "oc_deadbeefdeadbeef", "name": "Team Chat",
            "avatar_url": "https://s1-imfile.example.invalid/chat.png"}
    out = []
    for type_, ui in _PERSON_BEARING:
        field = cells.FieldSpec(field_name=ui, type=type_, ui_type=ui)
        out.append(cells.render_cell([chat if ui == "GroupChat" else person], field))
    fields = (cells.FieldSpec(field_name="Text", type=1, ui_type="Text"),)
    record = {"fields": {"Text": [{"text": "hi", "type": "text"}]},
              "created_by": person, "last_modified_by": person}
    out.extend(cells.render_row(record["fields"], fields))
    return "\n".join(out)


def test_ac5_the_amplifier_corpus_of_every_person_bearing_type_leaks_nothing():
    blob = _rendered_corpus()
    hits = {name: pattern.findall(blob)
            for name, pattern in _PROSE_PII.items() if pattern.findall(blob)}
    assert hits == {}, hits
    assert "Ada English" not in blob, "en_name never wins over name"


def test_ac5_a_person_whose_NAME_IS_ABSENT_falls_back_to_en_name():
    field = cells.FieldSpec(field_name="Owner", type=11, ui_type="User")
    assert cells.render_cell([{"en_name": "Ada English", "id": "ou_x"}], field) == "Ada English"


def test_ac5_DEFECT_re_introducing_the_id_into_the_markdown_projection_REDDENS(monkeypatch):
    """The amplifier's deliberate defect: put the id back into the projection and the sweep
    above must catch it. A guard that cannot fail is not a guard."""
    monkeypatch.setattr(cells, "_person_name",
                        lambda person: (person or {}).get("id", "") if isinstance(person, dict)
                        else "")
    blob = _rendered_corpus()
    assert _PROSE_PII["2-person-id"].findall(blob), (
        "the id was re-introduced into the Markdown projection and the sweep stayed green")


# --------------------------------------------------------------------------- #
# AC6 — no scope widened, and ZERO new API-using call sites                    #
# --------------------------------------------------------------------------- #

#: Read at start-of-work on ``develop`` — 85 permission rows over 12 surfaces, of which the
#: contacts family is 2. **This story adds none**, which is what makes it documentation-only
#: and safe to run beside a story that owns the wave's one new row.
#:
#: **86 since LD-405**, which added the sheets walk's composed front door
#: (`sheets-read` · `read_spreadsheet_markdown`) — a row this story still did not add. The
#: number is re-cut rather than the claim: what this pin means is "*this* story adds no call
#: site", and that is still what it checks.
#: **88 since LD-409**, which added the two named-version call sites (`drive-read` ·
#: `list_versions` and `drive-versions-write` · `create_version`) — rows this story still did
#: not add. The number is re-cut rather than the claim: what this pin means is "*this* story
#: adds no call site", and that is still what it checks.
#: **89 since LD-433**, which added the docx image-authoring leg (`docx-write` ·
#: `put_image_in_document`) — a row this story still did not add. The number is re-cut rather
#: than the claim: what this pin means is "*this* story adds no call site", and that is still
#: what it checks.
#: **91 since LD-434**, which added the folder-upload op (`drive-files-write` ·
#: `put_file_in_folder`) and the docx attachment leg (`docx-write` · `put_file_in_document`)
#: — rows this story still did not add. Re-cut, not loosened: the claim is unchanged.
#: **STILL 91 after LD-444**, and that is the interesting case rather than an omission. That
#: story added two registry rows (`docx-read` · `snapshot` / `load`) which reach **no
#: endpoint at all** — a registry row is minted per public operation, and the guard's own
#: subject is an *API-using* call site. So the rows are named in
#: :data:`_ENDPOINT_FREE_ROWS_ADDED_SINCE` and excluded, and the exclusion is not a rubber
#: stamp: the test below asserts each named row really does derive zero endpoints, so the day
#: one of them buys an endpoint the count reddens exactly as it always would have.
#: **92 since LD-442**, which DECLARED the Drive file-object delete (`drive-files-write` ·
#: `delete`) as that surface's lifecycle destroy half. The verb is not new — it shipped with
#: the folder-upload slice and was exercised by the live round trip — but it was declared
#: nowhere, so no permission row existed for it and the registry's own completeness check
#: could not see the gap (D-78). A row this story still did not add: re-cut, not loosened,
#: and the claim is unchanged.
#: **93 since LD-447**, which added the sheets in-cell image leg (`sheets-write` ·
#: `put_image_in_sheet`) — an API-using row (it derives the spreadsheet values family AND the
#: drive media download the opt-in byte proof reaches), and one this story still did not add.
#: Re-cut, not loosened: the claim is unchanged.
#: **95 since LD-448**, which added the sheets FLOAT-image pair (`sheets-write` ·
#: `put_float_image_in_sheet` / `remove_float_image_from_sheet`) — API-using rows (the write
#: derives the drive media upload AND download plus the sheets v3 float-image collection; the
#: removal derives the last of those), and ones this story still did not add. Re-cut, not
#: loosened: the claim is unchanged.
#: **96 since LD-450**, which added the Base attachment PERMALINK leg (`base-write` ·
#: `permalink_attachment_media`) — an API-using row (it derives
#: `drive/v1/metas/batch_query`, the endpoint the drive legs already reach), and one
#: this story still did not add. Re-cut, not loosened: the claim is unchanged.
#: **97 since LD-466**, which added the whole-Base delete (`base-schema-write` · `delete_base`)
#: as that surface's lifecycle destroy half — an API-using row (it derives
#: `drive/v1/files/:file_token`, the endpoint the drive file delete already reaches), and one
#: this story still did not add. Re-cut, not loosened: the claim is unchanged.
#: **98 since LD-467**, which added the ONE Drive organize verb a product ruling opened
#: (`drive-folders-write` · `create_folder`) — an API-using row (it derives
#: `drive/v1/files/create_folder`, a row of its own in the permission table), and one this
#: story still did not add. Re-cut, not loosened: the claim is unchanged.
#: **99 since LD-487**, which added the document SECURITY-LEVEL read (`drive-read` ·
#: `document_security_level`) — an API-using row (it derives `drive/v1/metas/batch_query`, the
#: endpoint the folder-title leg already reaches, and joins that row rather than adding a
#: scope), and one this story still did not add. Re-cut, not loosened: the claim is unchanged.
#: **100 since LD-575**, which added the docx table-GROW op (`docx-write` · `grow-table`) — an
#: API-using row (it derives `docx/v1/documents`, the endpoint every other docx-write op already
#: reaches, so it joins that row and adds no scope), and one this story still did not add.
#: Re-cut, not loosened: the claim is unchanged.
_CALL_SITES_AT_START_OF_WORK = 100
#: Rows minted for public operations that reach NO Lark endpoint, added after this story's
#: start-of-work. Excluded from the count above because the claim it pins is about *API-using*
#: call sites; each is re-verified endpoint-free on every run, so the list cannot silt up.
_ENDPOINT_FREE_ROWS_ADDED_SINCE = (("docx-read", "snapshot"), ("docx-read", "load"))
#: AMENDED by LD-348 (2026-08-08), with its reason, rather than deleted or loosened to ``>=``.
#: It read **2** at this story's start-of-work and the assertion below still means what it
#: meant: *this documentation story extended no contacts row*. It now reads **4** because a
#: LATER issue, under the maintainer's explicit ruling, bought the ``contact/v3/users/batch_get_id``
#: family on purpose — ``resolve_colleague`` plus the client method under it. That is a ruled
#: purchase named in one place, not a drift; any FIFTH contacts row still reddens here.
_CONTACTS_ROWS_AT_START_OF_WORK = 4

#: The wave partner's ONE row, named rather than absorbed into the count — opt-in link
#: resolution (the Base relational spec § F1-S1) buys exactly one new call site, and it is a **read** on the
#: ``base-read`` surface. Naming it is what keeps this guard's bite after the second lander
#: merged: any OTHER new row still reddens here, and this story's own claim — *it added none* —
#: is still literally what the assertion checks.
#: The guided column-type migration's ONE row is named the same way and for the same reason:
#: it is a ``legs`` entry on ``base-schema-write`` that composes operations already in this
#: registry and **reaches no endpoint of its own**, so it buys no scope — but it is still a row,
#: and absorbing it into the count below would blunt the guard instead of keeping it honest.
#: LD-296's ONE row is named the third time for the third time's reason — the row-hierarchy
#: read is a ``legs`` entry on ``base-read`` that reaches **no endpoint of its own** (it is
#: pure over records a read already holds), so it buys no scope and no call; naming it keeps
#: this guard biting on anything else instead of quietly absorbing it into the count.
#: LD-332's TWO rows are named for the fourth time's reason: the sheets read paths' revision
#: anchor is read off ``metainfo``, an endpoint the ``sheets-read`` surface already reached
#: (``get_frozen_panes`` / ``read_tabs_frozen``), so the two new rows buy **no new endpoint and
#: no new scope** — but they are still rows, and absorbing them into the count below would blunt
#: the guard instead of keeping it honest.
#: LD-348's TWO rows are named for the fifth time's reason, and it is the loudest one: they DO
#: buy a new endpoint family (``contact/v3/users/batch_get_id``) and they were minted to, under
#: the maintainer's ruling of 2026-08-08. Naming them here is what keeps the count below an assertion
#: about THIS story — which still added none — instead of quietly absorbing a ruled purchase.
#: LD-345 adds ``("base-read", "record_permalink")`` — a genuinely new api-using call site, but
#: another story's (the record permalink fetch), not this one's. It reaches the already-rowed
#: ``records/batch_get`` endpoint, so it buys no new endpoint family and no new scope; naming it
#: here keeps the count an assertion about THIS story, which still added none.
#: LD-327's FOUR rows are named for the same reason: the Drive folder-read surface it published
#: reaches the enumeration endpoints (a ruled R1 purchase, the Drive spec), and naming them here keeps
#: the count below an assertion about the base-person-chat story — which still added none —
#: rather than silently absorbing a later surface's call sites.
#: LD-382's ONE row is named for the same reason the LD-332 pair was: the docx revision anchor
#: is read off ``…/docx/v1/documents/{id}``, the endpoint the ``docx-read`` surface already
#: reached (``get_docx_content`` opens it), so the row buys **no new endpoint family and no new
#: scope** — but it is still a row, and absorbing it into the count below would blunt the guard
#: instead of keeping it honest.
#: LD-383's ONE row is named for that same reason once more: the spreadsheet walk composes
#: ``query_sheets`` + ``read_used_range``, so it reaches only endpoint families the
#: ``sheets-read`` surface already opened and buys **no new endpoint family and no new scope**
#: — but it is still a row, and absorbing it into the count below would blunt the guard.
#: LD-432's SIX rows are named for the loudest reason since LD-348's: the docx ACCESS surface
#: (grant / update / revoke / list members / set the copy levers, plus the address -> id leg)
#: buys TWO new endpoint families — the drive permission members family and the drive public
#: settings family — and it was minted to, on a measured spike. It also REACHES
#: ``batch_get_id``, through the shipped ``resolve_colleague`` and no second resolver, which is
#: why the permitted list below names it rather than the count absorbing it. Naming the rows
#: here keeps the count an assertion about THIS story, which still added none.
#: LD-464's ONE row is named for the LD-332 / LD-382 reason: the Drive by-name lookup is
#: the folder enumeration this surface already reached (``GET /drive/v1/files``) with an
#: in-memory name filter after it, so it buys **no new endpoint family and no new scope**
#: — but it is still a row, and absorbing it into the count below would blunt the guard.
_WAVE_PARTNER_ROWS = (("contacts-read", "resolve_colleague"),
                      ("drive-access-write", "grant_access"),
                      ("drive-access-write", "update_access"),
                      ("drive-access-write", "revoke_access"),
                      ("drive-access-write", "list_members"),
                      ("drive-access-write", "set_copy_permissions"),
                      ("drive-access-write", "resolve_grantee_email"),
                      ("sheets-read", "read_spreadsheet"),
                      ("docx-read", "read_document_revision"),
                      ("contacts-read", "batch_get_id"),
                      ("base-read", "batch_get_records"),
                      ("base-schema-write", "migrate_field_type"),
                      ("base-read", "read_hierarchy"),
                      ("base-read", "record_permalink"),
                      ("sheets-read", "read_revision"),
                      ("sheets-read", "read_tabs_revision"),
                      ("drive-read", "list_folder_children"),
                      ("drive-read", "list_folder_children_to_exhaustion"),
                      ("drive-read", "root_folder_token"),
                      ("drive-read", "folder_name"),
                      ("drive-read", "find_children_by_name"),
                      # LD-710 (round 9, Z2): two public verbs that shipped long before and
                      # were declared nowhere — named here, not absorbed into the count.
                      ("drive-files-write", "download"),
                      ("drive-files-write", "permalink"),
                      # LD-711: two public WriteClient reads the guide sends a consumer to,
                      # hidden while the census exempted the whole class — named, not counted.
                      ("docx-write", "get_block"),
                      ("docx-write", "read_document_revision"),
                      # LD-711, the same class on the Sheets write client: the seven calls the
                      # guide's recipes make by name.
                      *(("sheets-write", name) for name in (
                          "put_values", "query_tabs", "query_float_images", "read_values",
                          "read_value_range", "read_sheet_geometry", "read_frozen_panes")))


def test_ac6_this_story_adds_ZERO_api_using_call_sites():
    from larkdocio import permissions as perm

    rows = perm.permission_registry()
    contacts = [key for key in rows if key[0] == "contacts-read"]
    endpoints_by_row = dict(perm.operation_inventory())
    for row in _ENDPOINT_FREE_ROWS_ADDED_SINCE:
        assert row in rows, (
            f"{row} is named as an endpoint-free exclusion but is gone from the registry — "
            "an exclusion that claims nothing is how this guard would silt up")
        assert not endpoints_by_row.get(row), (
            f"{row} is excluded from the count as endpoint-free, but it now reaches "
            f"{endpoints_by_row.get(row)} — the exclusion has stopped being true")
    excluded = set(_WAVE_PARTNER_ROWS) | set(_ENDPOINT_FREE_ROWS_ADDED_SINCE)
    this_story = {key for key in rows if key not in excluded}
    assert set(_WAVE_PARTNER_ROWS) <= set(rows), (
        f"the wave partner's row(s) {_WAVE_PARTNER_ROWS} are gone from the registry — this "
        "constant names them so the count below stays an assertion about THIS story")
    assert len(this_story) == _CALL_SITES_AT_START_OF_WORK, (
        f"the registry holds {len(this_story)} call sites besides the wave partner's, not the "
        f"{_CALL_SITES_AT_START_OF_WORK} this story started from — a documentation-only "
        "story that moved this number has stopped being documentation-only")
    assert len(contacts) == _CONTACTS_ROWS_AT_START_OF_WORK, (
        "the contacts-family rows are neither extended nor duplicated here")


#: The ONLY call sites permitted to reach ``batch_get_id`` — the deliberately-minted purchase
#: of LD-348, under the maintainer's ruling of 2026-08-08. This guard was written so a *documentation*
#: story could not quietly buy an endpoint family, and that is still exactly what it enforces:
#: the family is bought ONCE, by name, by an issue that argued for it, and by nothing else.
#: The ``/im/`` half below is UNCHANGED and absolute — no chat lister ships, that purchase stays
#: declined, and no exception list exists for it.
#: LD-432 adds FOUR more, and they are the same kind of purchase made the same way: the docx
#: access surface resolves a grantee's EMAIL through the shipped ``resolve_colleague`` — never a
#: second resolver — so the family is reached from the grant, update and revoke verbs and from
#: the address -> id leg itself. It is still bought ONCE, by name, by an issue that argued for
#: it on measured evidence; a site that nobody argued for still reddens here. (No count is
#: written in this comment: the tuple below holds it, and the retyped number is what went
#: stale — it said *"a fifth"* against six rows. `process/doctrine/staleness.md` § C.)
_BATCH_GET_ID_CALL_SITES_BOUGHT_ON_PURPOSE = (
    ("contacts-read", "resolve_colleague"),
    ("contacts-read", "batch_get_id"),
    ("drive-access-write", "resolve_grantee_email"),
    ("drive-access-write", "grant_access"),
    ("drive-access-write", "update_access"),
    ("drive-access-write", "revoke_access"),
)


def test_ac6_no_call_site_anywhere_reaches_the_im_or_batch_get_id_families():
    """TRANSFORMED by LD-348, never deleted, and it still bites in both halves.

    * ``/im/`` — **absolute**. Any call site reaching a chat endpoint fails here, with no
      permitted list to be added to.
    * ``batch_get_id`` — narrowed from *"nobody"* to *"exactly the deliberately-minted call
      sites named in :data:`_BATCH_GET_ID_CALL_SITES_BOUGHT_ON_PURPOSE`, and no other"*. A
      further one, or the same family reached from a surface that did not argue for it, still
      reddens; so does a permitted site that has quietly disappeared. The register is named
      rather than counted here on purpose: it grew from two to six (LD-432) and the sentence
      that counted it did not.
    """
    from larkdocio import permissions as perm

    inventory = perm.operation_inventory()
    chat_offenders = [(key, endpoints) for key, endpoints in inventory
                      for endpoint in endpoints if "/im/" in endpoint]
    assert not chat_offenders, (
        f"a chat endpoint family was bought: {chat_offenders} — that purchase stays declined")

    reached = {key for key, endpoints in inventory
               for endpoint in endpoints if "batch_get_id" in endpoint}
    assert reached == set(_BATCH_GET_ID_CALL_SITES_BOUGHT_ON_PURPOSE), (
        f"batch_get_id is reachable from exactly the "
        f"{len(_BATCH_GET_ID_CALL_SITES_BOUGHT_ON_PURPOSE)} call sites minted on purpose "
        f"(LD-348, widened by LD-432) and from no other; found {sorted(reached)}")


def test_ac6_nothing_shipped_asks_a_reader_to_widen_a_scope(write_note, preamble):
    """The house rule, on this surface's own text: the library describes requirements; a
    grant is a console action, and no wording here may read as a request for one."""
    for label, text in (("capabilities() base-write note", write_note),
                        ("guide() base-write recipe", preamble)):
        lowered = text.lower()
        for ask in ("request the scope", "add the scope", "grant yourself",
                    "widen the scope", "escalate"):
            assert ask not in lowered, (label, ask)


# --------------------------------------------------------------------------- #
# AC7 — the landed refusal is ASSERTED against, never re-authored              #
# --------------------------------------------------------------------------- #

@pytest.fixture
def no_transport(monkeypatch):
    """A call-count spy with teeth: any socket the refusal opened would EXPLODE."""
    calls = []

    def forbidden(*args, **kwargs):  # pragma: no cover - reaching it IS the failure
        calls.append(args)
        raise AssertionError("a LOCAL refusal opened a socket")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    return calls


def _refuse(value):
    field = cells.FieldSpec(field_name="Owner", type=11, ui_type="User")
    with pytest.raises(write_cells.PersonNameNotResolvableError) as caught:
        write_cells.encode_cell(value, field)
    return str(caught.value)


def test_ac7_a_name_shaped_argument_is_refused_LOCALLY_with_zero_transport(no_transport):
    for value in ("Ada Lovelace", ["Ada Lovelace"], [{"name": "Ada Lovelace"}],
                  [{"en_name": "Ada Lovelace"}]):
        _refuse(value)
    assert no_transport == []


def test_ac7_the_LANDED_message_names_the_three_id_sources():
    message = _refuse([{"name": "Ada Lovelace"}])
    lowered = message.lower()
    assert "harvest" in lowered, "source (i)"
    assert "caller" in lowered, "source (ii)"
    assert "account owner" in lowered, "source (iii)"
    assert "larkdocio.contacts.resolve_user" in message


def test_ac7_the_landed_message_NEVER_advises_requesting_a_scope():
    lowered = _refuse([{"name": "Ada Lovelace"}]).lower()
    for ask in ("scope", "grant", "console", "permission"):
        assert ask not in lowered, (
            f"the refusal tells a caller to go and get {ask!r} — the library never asks for a "
            "grant, and this failure is a real one rather than a wording preference")


def test_ac7_the_landed_message_never_implies_LARK_FORBIDS_what_this_tenant_cannot_reach():
    lowered = _refuse([{"name": "Ada Lovelace"}]).lower()
    for claim in ("lark forbids", "not allowed", "impossible", "never possible"):
        assert claim not in lowered, claim


def test_ac7_this_story_AUTHORS_NO_SECOND_refusal():
    """One definition. A competing refusal is the defect this AC was corrected to prevent —
    so the person refusal class and its message must still be declared in exactly one module.
    """
    declarers = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "PersonNameNotResolvableError":
                declarers.append(path.relative_to(REPO_ROOT).as_posix())
    assert declarers == ["src/larkdocio/base/write_cells.py"], declarers


# --------------------------------------------------------------------------- #
# AC7b — the three vocabularies stay distinct                                  #
# --------------------------------------------------------------------------- #

def test_ac7b_User_is_authorable_AND_cell_writable_and_the_wording_never_says_otherwise(
        base_md, write_note, preamble):
    """The limitation is about **obtaining an id**, not about the type's support. A reader
    who comes away thinking Person columns cannot be made or written has been misinformed."""
    assert (11, "User") not in set(NON_WRITABLE_PAIRS)
    assert 11 in field_vocabulary.AUTHORABLE_TYPES
    assert "User" in field_vocabulary.AUTHORABLE_UI_TYPES
    for label, text in (("BASE.md row 37", _row_text(base_md, 37)),
                        ("BASE.md row 38", _row_text(base_md, 38)),
                        ("capabilities() base-write note", write_note),
                        ("guide() base-write recipe", preamble)):
        for sentence in _person_sentences(text):
            lowered = sentence.lower()
            for wrong in ("person cells are unsupported", "person is unsupported",
                          "cannot be written", "not writable", "unauthorable",
                          "cannot be created", "is unsupported"):
                assert wrong not in lowered, (label, wrong, sentence[:120])


def test_ac7b_the_quadrant_table_and_the_writability_constant_are_CITED_not_redefined(base_md):
    """Row 27 owns the authorable-vs-writable quadrants and the two constants own the sets.
    This story's rows point at them; a second listing here would be a third definition."""
    assert "row 27" in _row_text(base_md, 37).lower(), (
        "the row must cite the quadrant row rather than restate what a Person column is")
    for number in _APPENDED_ROWS:
        row = _row_text(base_md, number)
        assert "NON_WRITABLE_PAIRS" not in row, number
        assert "AUTHORABLE_UI_TYPES" not in row, number


# --------------------------------------------------------------------------- #
# AC8 — the three surfaces carry it, and the diff is exactly the intended lines #
# --------------------------------------------------------------------------- #

def test_ac8_the_register_APPENDED_at_the_tail_and_renumbered_nothing(base_md):
    import test_base_md_matrix as matrix

    # The register was read at 36 at start-of-work and this story appended THREE rows, at the
    # tail, renumbering nothing. It has since grown behind them — a later appender takes the
    # next free numbers, which is the same rule this story followed — so the claim is stated
    # as what it always was: this story's rows are 37-39, and everything above them is
    # somebody else's. A bare `== 39` would have turned "I appended" into "nobody may append".
    assert _APPENDED_ROWS == (37, 38, 39)
    assert matrix._REGISTER_ROWS >= max(_APPENDED_ROWS), (
        "the register is shorter than this story's own rows — they were removed, not moved")
    numbers = [int(line.strip().split("|")[1].strip())
               for line in base_md.splitlines()
               if re.match(r"^\|\s*\d+\s*\|", line.strip())]
    assert numbers == list(range(1, matrix._REGISTER_ROWS + 1)), numbers
    # …and the rows it did NOT write are byte-identical to what it found.
    assert "the SDK-typed property" not in _row_text(base_md, 37)


def test_ac8_every_appended_row_carries_evidence_and_a_revisit_trigger(base_md):
    for number in _APPENDED_ROWS:
        row = _register_row(base_md, number)
        assert row[3].strip(), f"row {number} has no evidence"
        assert len(row[4]) > 40, f"row {number}'s revisit trigger is not observable"
        assert re.search(r"(?:dev|src|tests)/[\w./-]+", row[3]), row[3]


def test_ac8_no_appended_row_authors_a_scope_string(base_md):
    """A scope requirement is authored in ``larkdocio.permissions`` and nowhere else — so a
    row that has to name a scope FAMILY names the family and points at the registry."""
    for number in _APPENDED_ROWS:
        row = " ".join(_register_row(base_md, number))
        assert not re.findall(r"`(?:docx|drive|bitable|sheets|contact|im):[a-z_:.]+`", row), row


def test_ac8_the_DECISION_REF_trap_is_respected_by_every_new_shipped_string(write_note,
                                                                           preamble):
    """No decision letters, no issue ids, no story refs — and the guard's own exclusion list
    is NOT extended to make that true."""
    source = Path(consumer_text.__file__).read_text(encoding="utf-8")
    assert "_DECISION_REF" in source
    for label, text in (("capabilities() base-write note", write_note),
                        ("guide() base-write recipe", preamble)):
        assert consumer_text.dialect_hits(text) == [], (
            label, consumer_text.dialect_hits(text)[:3])


def test_ac8_the_whole_shipped_corpus_is_still_dialect_free():
    for label, text in consumer_text.shipped_docs().items():
        assert consumer_text.dialect_hits(text) == [], (
            label, consumer_text.dialect_hits(text)[:3])


def test_ac8_the_capabilities_delta_is_ONE_LEAF_and_it_is_the_base_write_note(caps):
    """The anchor moved; this is the assertion that says WHY. Everything except
    ``surfaces/base-write/credentials/note`` must be untouched by this story — and **LD-530
    re-expressed that leaf-scoped, with no frozen number**: blank the leaf and require the set
    of addresses that move to be exactly ``["surfaces/base-write"]``. A second address in that
    list is a cross-surface leak. See the ``#:`` note below the previous constant's grave for
    where each half of the old whole-payload claim went."""
    import copy

    from capabilities_anchor import anchor_addresses, measure_addresses

    stripped = copy.deepcopy(caps)
    assert stripped["surfaces"][BASE_WRITE]["credentials"]["note"], "the leaf is already blank"
    stripped["surfaces"][BASE_WRITE]["credentials"]["note"] = ""

    before, after = measure_addresses(caps), measure_addresses(stripped)
    moved = [address for address in anchor_addresses(caps)
             if before[address] != after.get(address)]
    assert moved == ["surfaces/base-write"], (
        f"blanking the base-write credentials note moved {moved} — it must move the base-write "
        f"surface and NOTHING else.")


#: **THE RAW NO-NOTE ANCHOR IS NOW LEAF-SCOPED, AND IT NEEDS NO CONSTANT (LD-530).**
#:
#: **825 `#:` lines of byte-arithmetic essay stood right here**, in front of
#: `_PAYLOAD_WITHOUT_THE_NOTE` — the **third** whole-payload freeze, and the only one over the
#: **RAW** `json.dumps(payload, default=str, sort_keys=True)` with no normalisation at all.
#: That second serialisation is the whole reason the LD-490 rule existed (a per-row byte cost
#: is not portable between a raw anchor and a normalised one), and it is why every re-cut cost
#: fresh two-ended measurement *per anchor*. The constant is **gone** and the essay is
#: **relocated verbatim, not struck**, to
#: [`dev/capabilities-anchor-ledger.md`](../dev/capabilities-anchor-ledger.md) § "Preserved
#: history" § 3 — including the two `LANDED 2026-08-20 atop …` merged-tree re-derivations that
#: are now part of the LD-490 rule's own recorded reason
#: (`tests/capabilities_anchor.py` § *A per-row byte cost is not portable between anchors …
#: CONCLUSION SUPERSEDED IN PART BY LD-530*).
#:
#: **The claim did not narrow, it decomposed** — the same way its sibling in
#: `tests/test_base_field_vocabulary.py` did. It was: *"blank
#: `surfaces/base-write/credentials/note` and the WHOLE RAW payload is a frozen 404,368
#: bytes"*. Now:
#:
#: * *"blanking that one leaf perturbs `surfaces/base-write` and NO other address"* — asserted
#:   below, structurally, with no frozen number, true on every tree;
#: * *"and nothing else in the payload moved"* — asserted by `capabilities_anchor.ANCHOR_PIN`,
#:   every address, bidirectionally checked in `tests/test_capabilities_package_split.py`;
#: * *the raw serialisation itself* — still live as `capabilities_anchor.canonical_json`, and
#:   still load-bearing: the two normalisation-invariance guards use raw-vs-normalised
#:   divergence to prove the substitutions are not no-ops. What went away is the hand-authored
#:   raw byte COUNT, not the raw serialisation.
