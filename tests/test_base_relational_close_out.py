"""THE BASE RELATIONAL GATE's offline half (LD-272) — the front-door RETRACTION and the ladder's
register CLOSE-OUT.

This module proves nothing about the API; the four live arms in
``tests/test_live_base_relational_gate.py`` do that. What it holds is the half a credential-less
run can check, and the half the whole ladder is judged on: **the front door is true, and the
limitation register is closed.**

**THE RETRACTION, and why a content test asserts an ABSENCE.** The Base surface's front door was
written when the surface really did not touch files: it said the bytes were the caller's, that no
upload leg shipped, and that pulling a file back was deferred. The attachment leg made all three
false the day it landed. A test that only checked the *new* sentence exists would pass with both
sentences sitting next to each other — which is how a front door rots while every guard stays
green. So the checks below are **the old sentence is GONE**, phrased as literals, and a
deliberate-defect test puts each literal back and proves the check reddens.

**THE CLOSE-OUT IS MOSTLY ASSERTION.** Seven of the register rows this story is accountable for
were authored by earlier rungs — Stage's marker, Button's two rows, dashboards, workflows, the
public-share fence and the Share-dialog families — and this story **writes none of them**. It
asserts they are there, carrying a recognised status slug, their evidence and their revisit
trigger, because a close-out that re-authored a landed row would be the second definition the
one-owner rule exists to prevent. The register's length is therefore **not moved by this
story**: no row here closes a gap that is still open.
"""
import json
import re
import subprocess
import sys

import front_door
import pytest

import private_tree  # noqa: E402  (LD-691)

import gate_registry
import capability_rows as rows
from larkdocio import capabilities, guide

from guard_kit import REPO_ROOT
from domain_vocabulary import RETIRED_ID

REPO = REPO_ROOT


# --------------------------------------------------------------------------- #
# AC1 — the O3‴ retraction: the OLD sentences are GONE                          #
# --------------------------------------------------------------------------- #

#: **The literal claims this story retracts**, each with the file it lived in. They are written
#: out in full rather than matched loosely on purpose: a fuzzy needle stops matching the moment
#: somebody rewords the lie, and then the guard reports a retraction that never happened.
RETRACTED_CLAIMS = {
    "BASE.md attachment cell row — the bytes disclaimer": (
        "BASE.md", "The bytes are the caller's — no upload leg here"),
    "BASE.md attachment cell row — the deferred download": (
        "BASE.md", "media download is out-of-band and deferred"),
}

#: What replaced them, per file. Asserted **beside** the absence rather than instead of it: a
#: door that merely stopped lying, without saying what is true, is still not a door.
REPLACEMENT_TRUTH = {
    "BASE.md": ("hash-verified", "upload"),
}


@pytest.fixture(scope="module")
def base_md():
    return (REPO / "BASE.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def cli_help():
    """The rendered group ``--help`` — the entire manual for anyone who installed the command."""
    out = subprocess.run([sys.executable, "-m", "larkdocio.cli", "--help"],
                         capture_output=True, text=True, cwd=str(REPO))
    return out.stdout


@pytest.mark.parametrize("label", sorted(RETRACTED_CLAIMS))
def test_the_RETRACTED_media_claim_is_GONE_not_merely_contradicted(label, base_md):
    """AC1. The sentence the Base write spec's front door shipped is **absent**, not sitting beside a newer
    one that disagrees with it."""
    filename, sentence = RETRACTED_CLAIMS[label]
    text = base_md if filename == "BASE.md" else (REPO / filename).read_text(encoding="utf-8")
    assert sentence not in text, (
        f"{filename} still carries the retracted claim {sentence!r}; the attachment leg made it "
        "false the day it landed")


def test_DEFECT_putting_a_retracted_sentence_BACK_reddens_the_check(base_md):
    """The proof the absence check bites. Re-insert each retracted literal into the text and the
    same assertion that passes above must fail — otherwise it is a guard that would pass whatever
    the file said."""
    for filename, sentence in RETRACTED_CLAIMS.values():
        text = base_md if filename == "BASE.md" else \
            (REPO / filename).read_text(encoding="utf-8")
        defective = text + "\n" + sentence + "\n"
        assert sentence in defective, "the defect injection itself did not take"


def _shipped_source_files():
    """Every ``.py`` / ``.md`` byte under ``src/`` plus the repo-root docs the AC named — the
    same raw-byte reach as ``test_base_surface_claim_is_gone.py``'s sweep, reused here because
    the RETRACTED_CLAIMS literals are a claim family of their own (LD-277): the check above only
    ever looked at ``BASE.md``, so the identical literal survived a SEVENTH time, in a private
    docstring the AC's enumerated-file list never reached.

    ``CHANGELOG.md`` (the packaged in-package copy under ``src/larkdocio/``) is excluded on the
    same ``test_base_surface_claim_is_gone.py`` precedent: it is a historical record, and *this
    very entry* quotes the retracted sentence verbatim in order to retract it — sweeping it in
    would make documenting the fix indistinguishable from the defect."""
    paths = [
        p for pattern in ("*.py", "*.md") for p in (REPO / "src").rglob(pattern)
        if p.name != "CHANGELOG.md"
    ]
    paths += [REPO / "BASE.md"]
    return sorted(set(paths))


def _normalize_whitespace(text):
    """Collapse all whitespace runs (including the newline+indent a wrapped docstring line
    breaks on) to a single space, so a literal search is not blind to line-wrapping. This is
    exactly the gap LD-277 found: ``cells.py``'s docstring wraps "media download is" onto its
    own line, so a raw ``sentence in text`` check — the shape the BASE.md-only guard used — never
    fires even though the same words, in the same order, ship right there."""
    return re.sub(r"\s+", " ", text)


def test_no_shipped_source_byte_carries_a_RETRACTED_media_claim():
    """AC1, widened. A retracted literal must be gone from every shipped byte, not merely the
    one file the AC happened to enumerate — the same claim sitting in an un-swept, line-wrapped
    docstring is still the claim (LD-277)."""
    sentences = {sentence for _filename, sentence in RETRACTED_CLAIMS.values()}
    offenders = {}
    for path in _shipped_source_files():
        text = _normalize_whitespace(path.read_text(encoding="utf-8"))
        hits = [sentence for sentence in sentences if sentence in text]
        if hits:
            offenders[str(path.relative_to(REPO))] = hits
    assert not offenders, (
        f"a retracted claim literal survives outside the file the AC enumerated: {offenders}")


@private_tree.internal_log
def test_the_changelog_exclusion_here_is_live_not_dead_weight():
    """Mirrors ``test_base_surface_claim_is_gone.py``'s check of the same shape: the changelog
    really does quote a RETRACTED_CLAIMS sentence (this issue's own disclosure entry does it), so
    excluding it from the sweep hides a true positive on purpose rather than by accident — if a
    future edit dropped the quote, this test catches the exclusion going stale.

    **LD-540 moved the liveness claim to the AUTHORING SOURCE, and kept it unconditional there.**
    The wheel now carries a recent-N window of the changelog, so whether the PACKAGED copy quotes a
    retraction depends on which release last disclosed one — a fluctuating property, and pinning it
    would make this guard redden at some future release with nothing wrong. The exclusion's
    justification, however, is permanent and it is a property of the DOCUMENT: the changelog quotes
    retracted claims in order to record their retraction, and the root copy keeps every one of them
    forever. So the root copy is asserted with the full original force, and the packaged copy is
    handled by ``notes_claim_copies``, which proves any absence there is the window's doing and not
    an edit. **What this used to prove and no longer can:** that the copy inside the wheel quotes a
    retraction at every moment. Under a window that is not a property of a correct tree."""
    from test_shipped_notes import notes_claim_copies

    sentences = {sentence for _filename, sentence in RETRACTED_CLAIMS.values()}
    root = _normalize_whitespace((REPO / "CHANGELOG.md").read_text(encoding="utf-8"))
    quoted = [sentence for sentence in sentences if sentence in root]
    assert quoted, (
        "CHANGELOG.md no longer quotes any retracted claim, so excluding it from the sweep now "
        "hides nothing and should be dropped")
    # And the packaged copy is either live too, or provably out of window — never silently empty.
    notes_claim_copies("CHANGELOG.md", quoted[0], normalize=_normalize_whitespace)


def test_DEFECT_the_widened_sweep_ALSO_reddens_on_a_line_wrapped_literal():
    """The proof this wider sweep bites on exactly the shape LD-277 found: a naive
    ``sentence in text`` check (the BASE.md-only guard's shape) is blind to a literal that wraps
    across a docstring line break, so the sweep must normalize whitespace first — proven here by
    injecting the retracted sentence pre-wrapped across two lines, the way it actually shipped."""
    sentences = {sentence for _filename, sentence in RETRACTED_CLAIMS.values()}
    sentence = next(iter(sentences))
    split_at = sentence.index(" ", len(sentence) // 2)  # break on a word boundary, not mid-word
    wrapped = sentence[:split_at] + "\n    " + sentence[split_at + 1:]
    assert sentence not in wrapped, "the injected text is not actually wrapped"
    assert sentence in _normalize_whitespace(wrapped), (
        "the sweep's own normalization does not undo the wrap it is meant to catch")


def test_the_attachment_MEDIA_row_is_no_longer_DEFERRED(base_md):
    """AC1 + AC11. The § Not in scope row for the file bytes recorded a Non-Goal; the leg ships,
    so the row's status is the shipped one and its wording says the deferral was retracted."""
    row = _not_in_scope_row(base_md, "attachment media")
    assert row["status"] == "supported", row
    assert "sha256" in row["why"].lower(), (
        "the row says the leg ships but not what makes the claim checkable")
    assert "retracted" in row["why"].lower(), (
        "a Non-Goal that shipped is a RETRACTION, and the row should say so rather than quietly "
        "changing its own mind")


def test_the_attachment_CELL_row_names_the_shipped_upload_leg(base_md):
    """The field matrix's own Attachment row carried the write-side disclaimer. It is a *cell*
    row, so what it must now say is where the token comes from — not a second copy of the leg's
    contract, which register row 19 owns."""
    row = [line for line in base_md.split("\n")
           if line.startswith("| Attachment |")]
    assert len(row) == 1, "the Attachment field row should appear exactly once"
    assert "larkdocio.base.media" in row[0], (
        "the cell row does not point at the module the file token comes from")


def test_the_README_layout_row_names_the_ATTACHMENT_MEDIA_leg():
    """AC1. The README **is** the wheel's METADATA body; a Base row that never mentions the file
    leg describes a surface that stopped existing."""
    row = [line for line in front_door.readme_text().split("\n")
           if line.startswith("| `src/larkdocio/base/`")]
    assert len(row) == 1
    assert "attachment media" in row[0].lower(), row[0][:200]
    assert "sha256" in row[0].lower(), (
        "the README says media moves but not that the round trip is verified by digest")
    assert "permanent" in row[0].lower(), (
        "the README sells the leg without naming its one irreversible consequence")


def test_the_wheel_SUMMARY_and_KEYWORDS_carry_the_media_leg():
    """AC1. The ``Summary`` is the one line a package index shows and ``Keywords`` are the words
    a search has to match; neither said the Base surface moves files at all."""
    project = front_door.pyproject()["project"]
    assert "attachment" in project["description"].lower(), project["description"]
    assert "attachments" in project["keywords"], project["keywords"]


def test_the_CLI_help_says_the_LIBRARY_moves_attachment_media(cli_help):
    """AC1. The command line stays read-only — what changes is that its description of the
    library no longer implies the Base surface never touches a file."""
    assert cli_help, "the group --help rendered empty"
    assert "attachment" in cli_help.lower(), cli_help[:400]
    # TRANSFORMED BY LD-492. This asserted the group page's blanket "NEVER WRITES", which was
    # never this story's claim — it was borrowed as a proxy for "the media leg is a LIBRARY
    # leg, not a command". The blanket claim became false when the roundtrip verb shipped, so
    # the proxy is replaced by the thing it stood for: the media leg still has no command-line
    # route, and the one verb that writes writes a docx.
    assert "roundtrip push --apply" in cli_help
    assert "A Base attachment also has a file leg" in " ".join(cli_help.split()), (
        "the group page no longer says the attachment leg is the LIBRARY's")


def test_capabilities_and_the_guide_still_carry_the_retraction_LD_268_landed():
    """AC1's other half, asserted rather than re-authored: the leg's own rung already corrected
    ``capabilities()`` and the packaged guide, and this story must not let that regress while it
    corrects the rest."""
    note = capabilities(full=True)["surfaces"]["base-write"]["credentials"]["note"]
    assert "no upload leg ships here" not in note
    assert "ATTACHMENT CELL NOW HAS ITS OWN FILE LEG" in note
    text = guide(full=True)
    assert "file token" in text.lower()
    assert "sha256" in text.lower(), "the guide never says how a caller verifies the round trip"


# --------------------------------------------------------------------------- #
# AC10 — capabilities() reports the RELATIONAL surface honestly                  #
# --------------------------------------------------------------------------- #

def test_the_media_legs_are_reported_with_the_DRIVE_family_named_and_UNGUESSED():
    """AC10. The surface's scopes are the **union of its operations' rows**, and those rows now
    span two endpoint families. The drive rows carry **no scope string** — none has ever been
    observed demanded — so the union stays the one bitable scope and the drive requirement is
    published as an honest unknown beside it. A guessed drive scope here would read as an answer.
    """
    surface = capabilities(full=True)["surfaces"]["base-write"]
    legs = rows.by_name(surface, rows.LEG)
    # LD-450 added the third leg — a READ on the drive META family, which is why this
    # guard's "both families are drive, and neither carries a guessed scope" claim now
    # spans three legs rather than two.
    assert set(legs) == {"upload_attachment_media", "download_attachment_media",
                         "permalink_attachment_media"}
    families = {endpoint.split("/")[2] for leg in legs.values()
                for endpoint in leg["permissions"]["endpoints"]}
    assert families == {"drive"}, families
    for leg in legs.values():
        assert leg["permissions"]["scopes"] == [], (
            "a drive scope string was written down that nobody has ever seen demanded")
        assert leg["permissions"]["unknown_requirements"], (
            "an empty requirement with no recorded reason is a guess wearing a blank")
    operation_families = {endpoint.split("/")[2] for op in rows.call_sites(surface, rows.OPERATION)
                          for endpoint in op["permissions"]["endpoints"]}
    assert operation_families == {"bitable"}
    assert surface["credentials"]["scopes"] == ["bitable:app"]


def test_NO_CONTACT_OR_IM_SCOPE_entered_the_Base_surfaces():
    """AC10's void clause. The person/chat disclosure added **no call site**, so no contact- or
    im-family scope may appear anywhere on a Base surface — a disclosure that quietly bought a
    grant would be the opposite of a disclosure."""
    surfaces = capabilities(full=True)["surfaces"]
    for surface_id, surface in surfaces.items():
        if not surface_id.startswith("base-"):
            continue
        creds = surface["credentials"]
        for scope in list(creds["scopes"]) + list(creds["optional_scopes"]):
            assert not scope.startswith(("contact:", "im:")), (surface_id, scope)


def test_the_resolution_flag_reports_DEFAULT_OFF_and_its_COST():
    """AC10. Opt-in is only opt-in if a consumer can see the switch, its default and its price."""
    flag = capabilities(full=True)["flags"]["resolve_base_links"]
    blob = json.dumps(flag).lower()
    assert flag["default"] is False
    assert "byte-identical" in blob
    assert "cost" in blob or "extra read" in blob


def test_the_relational_gate_is_a_MEMBER_of_the_base_write_ring():
    """AC10 + AC14. ``gate_coverage`` is a claim about which files prove this surface; a gate
    that exists and is not in the ring is coverage nobody can find."""
    members = {m["id"]: m for m in
               capabilities(full=True)["surfaces"]["base-write"]["gate_coverage"]["members"]}
    assert "base-relational-gate" in members, sorted(members)
    member = members["base-relational-gate"]
    assert member["module"] == "tests/test_live_base_relational_gate.py"
    assert (REPO / member["module"]).exists(), "the ring names a file that does not exist"
    assert set(member["arms"]) >= {
        "hash-verified-media", "record-delete-dangling", "table-delete-detector",
        "resolution-off-byte-identity"}


# --------------------------------------------------------------------------- #
# AC4's content half — the message POINTS at the loss preview                   #
# --------------------------------------------------------------------------- #

def test_the_table_delete_arm_POINTS_AT_the_loss_preview_and_does_NOT_restate_it():
    """AC4. The cross-table loss contract has exactly one owner —
    ``larkdocio.base.loss_preview`` — and the aftermath this arm reads is the thing that owner
    warns about. So the arm **names** the warning and must not carry a second copy of its text:
    two statements of one rule drift, and the drift is silent."""
    from larkdocio.base import loss_preview

    source = (REPO / "tests/test_live_base_relational_gate.py").read_text(encoding="utf-8")
    assert "loss_preview" in source, (
        "the table-delete arm never names the warning whose aftermath it exercises")
    assert "INBOUND_LINK_DANGLES_SILENTLY" in source, (
        "the arm points at the module but not at the sentence that owns this warning")
    warning = loss_preview.INBOUND_LINK_DANGLES_SILENTLY
    # A restatement, not a citation: any long run of the owner's own prose appearing verbatim.
    for chunk in _sentences(warning):
        assert chunk not in source, (
            f"the arm RESTATES the loss preview's own words ({chunk[:60]!r}) instead of "
            "pointing at them")


# --------------------------------------------------------------------------- #
# AC9 — every story in the rung has a live ring or a WRITTEN reason              #
# --------------------------------------------------------------------------- #

def test_the_relational_gate_and_its_companion_are_REGISTERED():
    """AC9. A new live gate with no registry row reddens ``tests/test_gate_registry.py``; this
    asserts the row is the right *kind* as well as present."""
    gate = gate_registry.REGISTRY["test_live_base_relational_gate.py"]
    companion = gate_registry.REGISTRY["test_live_base_relational_gate_offline.py"]
    assert gate.kind is gate_registry.Kind.HAS_COMPANION
    assert companion.kind is gate_registry.Kind.COMPANION
    assert len(gate.reason) > 400, "a gate row's reason is the record, not a label"


def test_the_stories_with_NO_live_ring_carry_a_WRITTEN_REASON_not_an_absence():
    """AC9's other half, and the reason this registry gained a second table. Two stories in this
    rung ship **no** live file at all — by their own AC, because each makes zero API calls — and
    an absence in a file-globbed registry is indistinguishable from an oversight. The reason is
    therefore recorded as data, keyed by the surface the story shipped."""
    reasons = gate_registry.rings_declined()
    assert set(reasons) == {"larkdocio.base.referential", "the person/chat disclosure"}
    for subject, reason in reasons.items():
        assert len(reason) > 120, f"{subject} declines a ring without a usable reason"
        assert "no call" in reason.lower() or "zero call" in reason.lower(), (
            f"{subject}'s reason does not say why a live ring would have nothing to run")


# --------------------------------------------------------------------------- #
# AC11 — the register is CLOSED OUT, mostly by assertion                        #
# --------------------------------------------------------------------------- #

#: The rows this story is accountable for and **did not author**: each was landed by an earlier
#: rung, and the close-out's job is to prove it is still there and still says what it said.
LANDED_ROWS = {
    1: "stage",
    4: "button",
    13: "button",
    14: "dashboard",
    15: "workflow",
    17: "form",
    18: "share",
}


@pytest.mark.parametrize("number", sorted(LANDED_ROWS))
def test_the_LANDED_register_rows_are_asserted_NOT_reauthored(number, base_md):
    """AC11 + O6‴ / O7‴ at **zero row cost**. Each row exists, is about what the close-out says
    it is about, carries a recognised status slug, evidence and a revisit trigger."""
    import test_base_md_matrix as matrix

    row = [r for r in matrix._register_rows(base_md) if r["#"] == str(number)][0]
    subject = LANDED_ROWS[number]
    assert subject in row["Limitation / workaround"].lower(), (
        f"register row {number} is no longer about {subject!r}")
    assert row["Status"].strip().strip("`") in matrix._STATUSES, row["Status"]
    assert row["Evidence"].strip(), f"row {number} carries no evidence"
    trigger = [value for key, value in row.items() if key.startswith("Revisit trigger")]
    assert trigger and trigger[0].strip(), f"row {number} carries no revisit trigger"


def test_this_story_APPENDS_NO_ROW_and_the_count_is_read_rather_than_assumed(base_md):
    """AC11. Every fact this rung had to say out loud was said by the rung that discovered it;
    the gate closes out by asserting, so the pinned length does not move for it. The number is
    read from the matrix guard rather than restated here, so the two cannot disagree.

    *(The literal moved 42 → 43 when the Formula-authoring fix APPENDED row 43, 44 → 45 when
    the search-filter-transport fix appended row 45, and 45 → 46 when the select-option keying fix
    appended row 46, 47 → 48 when the select-option-id fix appended row 48, and 48 → 49 when the
    Base record-history measured refusal appended row 49 — a later story appending its own row is
    exactly what this assertion permits; what it forbids is THIS story's rung growing one.)*"""
    import test_base_md_matrix as matrix

    assert len(matrix._register_rows(base_md)) == matrix._REGISTER_ROWS == 49


def test_the_DEFERRED_slug_leaves_the_CAPABILITY_rows_and_stays_in_the_REGISTER(base_md):
    """The retraction's book-keeping consequence, said out loud rather than quietly absorbed.

    Both Non-Goals the § Not in scope table declared — the file bytes and link resolution —
    have now **shipped**, so no capability row carries ``deferred`` any more. The slug is not
    retired: it still labels **register row 24**, the other-user name→id gap, which is a real
    deferral with a written mandate behind it. That is why the vocabulary keeps defining it —
    deleting a status because one table stopped using it would make the next deferral look like
    a new invention, and would leave a live row wearing an undefined slug.
    """
    import test_base_md_matrix as matrix

    statuses = {status for _cell, status in matrix._status_bearing_rows(base_md)}
    assert "deferred" not in statuses, (
        "a capability row still defers something; the close-out claims both Non-Goals shipped")
    assert "deferred" in matrix._STATUSES, "the slug was deleted rather than kept"
    register = {row["#"]: row["Status"].strip().strip("`")
                for row in matrix._register_rows(base_md)}
    assert register["24"] == "deferred", (
        "the one genuinely deferred thing left is the other-user name→id gap; if that row "
        "stopped saying so, the vocabulary entry below has nothing to describe")
    vocabulary = [line for line in base_md.split("\n")
                  if line.startswith("| **deferred** |")]
    assert len(vocabulary) == 1, "the vocabulary table no longer defines the slug"


# --------------------------------------------------------------------------- #
# AC12 — dialect-free                                                           #
# --------------------------------------------------------------------------- #

_DECISION_SHAPED = re.compile(r"\b[DOR]\d+[′″‴']*\b|\bLD-\d{3}\b|" + RETIRED_ID.pattern + r"|\bAC\d+\b")


def test_every_string_this_story_added_to_the_front_door_is_DIALECT_FREE(cli_help):
    """AC12. The corpus-wide guard runs elsewhere; this is the narrow one over exactly the four
    surfaces this story edited, so a failure names the edit rather than the corpus."""
    project = front_door.pyproject()["project"]
    for label, text in (
        ("the wheel Summary", project["description"]),
        ("the wheel Keywords", " ".join(project["keywords"])),
        ("the CLI group help", cli_help),
        ("the README Base row", "\n".join(
            line for line in front_door.readme_text().split("\n")
            if line.startswith("| `src/larkdocio/base/`"))),
    ):
        found = _DECISION_SHAPED.findall(text)
        assert not found, f"{label} carries internal dialect: {found}"


# --------------------------------------------------------------------------- #
# helpers                                                                       #
# --------------------------------------------------------------------------- #

def _not_in_scope_row(text, needle):
    """The § Not in scope row whose first cell contains ``needle``."""
    for line in text.split("\n"):
        if line.startswith("|") and needle in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 5:
                return {"family": cells[0], "reach": cells[1],
                        "status": cells[2].strip("`"), "why": cells[3], "evidence": cells[4]}
    raise AssertionError(f"no § Not in scope row mentions {needle!r}")


def _sentences(text, minimum=40):
    """The owner's prose, split into chunks long enough that a match means a restatement."""
    return [part.strip() for part in re.split(r"[.;]\s+", text)
            if len(part.strip()) >= minimum]
