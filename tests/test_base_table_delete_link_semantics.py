"""THE TABLE-DELETE LINK SEMANTICS, RE-MEASURED — the offline companion (LD-480).

**A REPORT OF DRIFT THAT DID NOT REPRODUCE, AND WHAT WAS MEASURED INSTEAD.** LD-480 was filed on
one observation: LD-455's QA slice, on 2026-08-14, read a two-way (``DuplexLink``, 21) column
pointing INTO a deleted table as **surviving** the table's deletion, where LD-272 had measured on
2026-08-05 that it does **not**. Re-measuring the same route twice on 2026-08-14 read the
2026-08-05 answer both times: the inbound one-way column **survives and dangles**, and the inbound
two-way column is **destroyed along with its twin's table**. The single mechanism that would have
made both readings true — the source column's removal lagging the delete — was tested directly and
refuted within its own scope.

**BOTH OBSERVATIONS STAY ON THE RECORD.** The counter-observation is not explained away and the
re-measurement is not presented as if nothing had disagreed
(``process/doctrine/supersession.md`` § A.1; the precedent shape is ``BASE.md`` row 40 / LD-284 —
*both captures are real*). What the gate asserts is the reading that was measured; what would move
it is written down.

**This module makes no call.** Everything below is read off the capture the live gate writes
(``tests/captures/base-study/captures/ld480-table-delete-link-semantics.json``) and off the field payloads
that capture carries **as the API produced them** — deserialized through the same SDK bridge a
read goes through, never hand-mocked (``PROJECT.md`` § Quality bar).

**ROUTE SCOPING IS THE POINT (D-59).** Every observation in the capture names the exact route it
was made on, and the symmetric **field**-delete finding (``p0-5-02``:
``source_duplex_survived: false`` — deleting a duplex column deletes its twin) lives on a
**different** route, is **not** re-measured here, and may not borrow this measurement's proof.
The capture says so in a block of its own, and the assertions below hold it to that.
"""
import ast
import importlib
import json
import pkgutil
import re

import pytest
from guard_kit import REPO_ROOT
from lark_oapi.api.bitable.v1 import AppTableField
from lark_oapi.core.json import JSON

import larkdocio
from larkdocio.base import loss_preview
from larkdocio.base import referential
from larkdocio.base import schema_ops_destructive
from larkdocio.base import table as base_table

#: The one derivation of the repo root, taken off the guard seam rather than re-derived — this
#: module reads ``BASE.md``, so it is an adopter (``tests/test_base_md_matrix.py``'s B3 guard).
_ROOT = REPO_ROOT

#: The capture this issue's live run writes — the NEW measurement, carrying the OLD one.
CAPTURE = _ROOT / "tests/captures/base-study/captures/ld480-table-delete-link-semantics.json"

#: The gate whose assertion moved, read as text so the dated history is checked in the source
#: a maintainer actually meets.
GATE = _ROOT / "tests/test_live_base_relational_gate.py"

#: The route the table delete was measured on. Colon-style, the spelling ``BASE.md`` and
#: ``larkdocio.permissions`` use.
TABLE_DELETE_ROUTE = "DELETE /open-apis/bitable/v1/apps/:app_token/tables/:table_id"
FIELDS_READ_ROUTE = "GET /open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields"
RECORDS_SEARCH_ROUTE = (
    "POST /open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/search")
RECORD_DELETE_ROUTE = (
    "DELETE /open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/:record_id")

#: The route this issue deliberately does NOT measure (AC7 / D-59).
FIELD_DELETE_ROUTE = (
    "DELETE /open-apis/bitable/v1/apps/:app_token/tables/:table_id/fields/:field_id")

#: The capture the timing probe writes — the refutation of the one mechanism that would have let
#: both readings be true.
TIMING_CAPTURE = _ROOT / "tests/captures/base-study/captures/ld480-02-table-delete-cascade-timing.json"

#: The 2026-08-05 reading, verbatim from ``ld272-01-relational-round-trip.json``. Held here so the
#: re-confirmation block cannot drift into a paraphrase of the reading it re-confirms.
READING_2026_08_05 = {
    "one_way_survived": True,
    "two_way_survived": False,
    "link_columns_surviving": ["ld272-one-way"],
    "dangling_columns": ["ld272-one-way"],
    "states": {"ld272-one-way": "target-table-missing"},
    "detector_extra_calls": 0,
    "records_search_still_answers": 11,
    "table_is_gone": True,
}


@pytest.fixture(scope="module")
def capture():
    return json.loads(CAPTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def table_delete(capture):
    return capture["observations"]["table_delete"]


def _field(payload):
    """One captured field payload → the SDK-typed object a read hands back.

    The same bridge :mod:`tests.test_base_referential` uses. An undeclared key is absent on the
    typed object exactly as it is absent in the payload, which is the equivalence the detector's
    whole signature rests on.
    """
    return JSON.unmarshal(json.dumps(payload), AppTableField)


# --------------------------------------------------------------------------- #
# AC3 — the capture records BOTH readings                                      #
# --------------------------------------------------------------------------- #

def test_the_capture_exists_under_THIS_issues_own_id(capture):
    """A git diff is not a record. The re-measurement lands as its own capture, named for the
    issue that took it, rather than only as a rewrite of the file the gate overwrites on every
    run."""
    assert capture["_issue"] == "LD-480"
    assert capture["_measured_at"] == "2026-08-14"
    assert capture["_verdict"] == "OK"


def test_the_capture_QUOTES_the_2026_08_05_reading_VERBATIM_with_its_date(capture):
    """The dated-history discipline, as data: the 2026-08-05 measurement is quoted key for key,
    dated, attributed to the capture it came from, and carries **why it was recorded** — so a
    reader meets the argument rather than a bare value."""
    block = capture["_reconfirms"]
    assert block["date"] == "2026-08-05"
    assert block["issue"] == "LD-272"
    assert block["capture"] == "dev/base-study/captures/ld272-01-relational-round-trip.json"
    assert block["table_delete"] == READING_2026_08_05, (
        "the 2026-08-05 reading must be quoted VERBATIM, not paraphrased")
    assert "why_it_was_recorded" in block and len(block["why_it_was_recorded"]) > 80
    assert block["outcome"] == "re-measured 2026-08-14, UNCHANGED"


def test_the_COUNTER_OBSERVATION_is_recorded_rather_than_EXPLAINED_AWAY(capture):
    """The observation this issue was filed on did not reproduce — which is a reason to date it,
    not a reason to delete it. It carries its date, where it is written down, whether it
    reproduced, and the mechanism that was tested to try to reconcile the two."""
    block = capture["_counter_observation"]
    assert block["date"] == "2026-08-14"
    assert block["reading"] == "two_way_survived: true"
    assert block["reproduced_by_LD_480"] is False
    assert "progress.md" in block["source"]
    assert "REFUTED" in block["note"]
    assert "QUIET tenant" in block["note"], (
        "the refutation must state the condition it was taken under, never more")


def test_the_capture_carries_a_REVISIT_TRIGGER_for_the_reading_it_asserts(capture):
    """A reading that survived a challenge owes the next challenger a falsifier."""
    assert len(capture["_revisit_trigger"]) > 60
    assert "second" in capture["_revisit_trigger"].lower()


def test_the_TIMING_hypothesis_is_REFUTED_IN_ITS_OWN_CAPTURE_and_SCOPED():
    """The probe that reconciled nothing, and said so. It mints **no media** — which is why the
    question was asked there and not by re-running the gate."""
    probe = json.loads(TIMING_CAPTURE.read_text(encoding="utf-8"))
    verdict = probe["_verdict"]
    assert verdict["two_way_ever_present_after_delete"] is False
    assert verdict["two_way_presence_is_STABLE_across_the_window"] is True
    assert all(verdict["one_way_present_at_each_poll"])
    assert probe["_residue"].startswith("none")
    polls = probe["observations"]["polls"]
    assert polls[0]["seconds_after_delete_requested"] < 2, (
        "the first poll has to be the fast one — that is the read the gate has always taken")
    assert polls[-1]["seconds_after_delete_requested"] >= 40


# --------------------------------------------------------------------------- #
# AC1 — route-scoped, per link kind                                            #
# --------------------------------------------------------------------------- #

def test_EVERY_observation_names_THE_ROUTE_it_was_made_on(capture, table_delete):
    """D-59, checked structurally rather than trusted: every observation block carries a
    ``_route``, and the two routes in play here are the single-table DELETE and the two reads
    that follow it."""
    assert table_delete["_route"] == TABLE_DELETE_ROUTE
    assert table_delete["fields_read"]["_route"] == FIELDS_READ_ROUTE
    assert table_delete["records_search"]["_route"] == RECORDS_SEARCH_ROUTE
    assert capture["observations"]["record_delete"]["_route"] == RECORD_DELETE_ROUTE
    for name, arm in capture["observations"].items():
        assert arm.get("_route"), f"observation {name} carries no route label"


def test_the_TWO_LINK_KINDS_SPLIT_on_this_route_measured_PER_KIND(table_delete):
    """The measurement itself. The inbound **one-way** column survives and dangles; the inbound
    **two-way** column does not survive at all — its twin lived inside the doomed table and the
    source column went with it. Two kinds, one route, one run."""
    single = table_delete["per_kind"]["SingleLink"]
    assert single["survived"] is True
    assert single["state"] == referential.TARGET_TABLE_MISSING, single["state"]
    assert single["target_table_id_persists"] is True
    assert single["target_table_name_present"] is False

    duplex = table_delete["per_kind"]["DuplexLink"]
    assert duplex["survived"] is False
    assert duplex["state"] is None
    assert duplex["field_payload"] is None, (
        "a column that did not survive has no field payload; a shape recorded for it would be "
        "invented rather than measured")


def test_the_DETECTORS_WHOLE_SIGNATURE_is_recorded_for_the_SURVIVOR(table_delete):
    """``table_id`` persists while ``table_name`` drops out — the only free evidence there is,
    recorded as the two separate facts it is rather than inferred from the state slug."""
    single = table_delete["per_kind"]["SingleLink"]
    assert single["target_table_id"] == table_delete["deleted_table_id"]
    assert single["field_type"] == referential.SINGLE_LINK[0]
    assert single["symmetric"] is False


def test_what_became_of_the_AUTO_CREATED_MIRROR_is_recorded(table_delete):
    """The mirror lived inside the doomed table, so it went with it — and that is stated as an
    observation rather than left to inference. It is *also* the reason the source two-way column
    goes: the pair is destroyed together, which is what makes the two link kinds split here."""
    mirror = table_delete["mirror_column"]
    assert mirror["lived_in_the_deleted_table"] is True
    assert mirror["survives"] is False
    assert mirror["_route"] == TABLE_DELETE_ROUTE


def test_the_RECORD_SEARCH_still_answers_code_0(table_delete):
    """The silent half: nothing anywhere reports an error about the dangling columns."""
    search = table_delete["records_search"]
    assert search["code"] == 0
    assert search["records"] >= 1


def test_the_RECORD_DELETE_arm_is_recorded_STILL_UNCHANGED(capture):
    """What scopes the drift to the table-delete route: on the record route the two kinds still
    behave differently — the one-way dangles, the two-way self-heals."""
    arm = capture["observations"]["record_delete"]
    assert arm["one_way_still_holds_the_dead_id"] is True
    assert arm["two_way_self_healed"] is True
    assert arm["unchanged_since"] == "2026-08-05"


# --------------------------------------------------------------------------- #
# AC6 — the detector, against the payload the API actually produced            #
# --------------------------------------------------------------------------- #

def test_the_SHIPPED_DETECTOR_reads_the_MEASURED_SURVIVOR_as_DANGLING(table_delete):
    """The payload below is the field-list entry Lark returned for the surviving one-way column
    **after** its target table was deleted, marshalled straight out of the run — so this is the
    real shape, not a shape edited into agreement (``PROJECT.md`` § Quality bar).

    ``p0-5-02``'s specimen is the same kind, from a different Base on a different day; this one
    is from the route-scoped run that also looked at the two-way kind in the same breath, which
    is what makes "the two kinds split here" one measurement rather than two stitched together.
    """
    payload = table_delete["per_kind"]["SingleLink"]["field_payload"]
    assert payload["type"] == referential.SINGLE_LINK[0]
    assert "table_name" not in payload["property"]
    reading = referential.link_column(base_table.field_spec(_field(payload)))
    assert reading is not None
    assert reading.state == referential.TARGET_TABLE_MISSING
    assert reading.dangling is True
    assert reading.symmetric is False
    assert reading.target_table_id == table_delete["deleted_table_id"]
    assert reading.target_table_name is None


def test_the_TIMING_PROBES_payload_reads_the_SAME_WAY_on_a_SECOND_SHAPE(table_delete):
    """The same reading, on the independently built shape the probe used. Two Bases, two runs,
    one answer — which is what a re-measurement has to mean."""
    probe = json.loads(TIMING_CAPTURE.read_text(encoding="utf-8"))
    poll = probe["observations"]["polls"][0]
    payload = poll["ld480-one-way"]["field_payload"]
    reading = referential.link_column(base_table.field_spec(_field(payload)))
    assert reading.state == referential.TARGET_TABLE_MISSING
    assert reading.dangling is True
    assert poll["ld480-two-way"]["present"] is False


# --------------------------------------------------------------------------- #
# AC7 — the FIELD-delete route is not re-labelled from a TABLE-route reading   #
# --------------------------------------------------------------------------- #

def test_the_FIELD_DELETE_route_is_declared_NOT_MEASURED_HERE(capture):
    """D-59 in the negative direction. The field route appears in this capture exactly once —
    in the block that says it was **not** measured — so no later reader can mistake the table
    route's proof for the field route's."""
    unmeasured = capture["_not_measured_here"]
    assert unmeasured["route"] == FIELD_DELETE_ROUTE
    assert unmeasured["standing_reading"] == "p0-5-02: source_duplex_survived false"
    assert "not re-measured" in unmeasured["note"].lower()
    blob = json.dumps(capture)
    assert blob.count(FIELD_DELETE_ROUTE) == 1, (
        "the field-delete route may appear ONLY in the not-measured-here block")


# --------------------------------------------------------------------------- #
# AC2 — the gate keeps the dated history and gains a revisit trigger           #
# --------------------------------------------------------------------------- #

def test_the_GATE_carries_BOTH_DATED_READINGS_and_a_REVISIT_TRIGGER():
    """The assertion is **transformed, never struck**, and the disagreement is not tidied away: a
    maintainer reading the gate finds the 2026-08-05 reading with its reason, the 2026-08-14
    counter-observation with where it is written down, the re-measurement, and what would move
    the reading it asserts."""
    source = GATE.read_text(encoding="utf-8")
    assert "2026-08-05" in source and "2026-08-14" in source
    assert "TABLE_DELETE_READING_2026_08_05" in source
    assert "COUNTER_OBSERVATION_2026_08_14" in source
    assert "p0-5-02" in source, "the field-route reading is still cited, not erased"
    assert "ld480-table-delete-link-semantics.json" in source
    assert "REVISIT" in source


def test_the_GATE_does_NOT_relax_the_assertion_into_nothing():
    """A green gate bought by weakening it is the failure mode this issue exists to avoid: the
    arm still asserts both halves per kind and still asserts a state per surviving column."""
    source = GATE.read_text(encoding="utf-8")
    assert "one_way_survived" in source and "two_way_survived" in source
    assert "xfail" not in source
    assert "TARGET_TABLE_MISSING" in source


# --------------------------------------------------------------------------- #
# AC5 — THE CENSUS, not a spot-check: the claim is grepped off the shipped      #
#       surface itself, so a survivor cannot hide behind a list of names        #
# --------------------------------------------------------------------------- #

#: The superseded over-broad claim, in the shapes it was actually written in. Every one
#: predicates *dangling* of **every** inbound link, which is what the per-kind measurement
#: refutes: only the ONE-WAY kind survives to dangle at all.
#:
#: **Two shapes were added after a second miss, and they are the two the first set could not
#: see:** a claim written with the **backticked type names** in place of the word *link*
#: (``every inbound `SingleLink` / `DuplexLink` … dangling``) and a claim written in **reversed
#: clause order** (``… in EVERY OTHER TABLE left dangling``, rather than *leaves … dangling*).
#: Neither reads as an exception; both are the same sentence with different furniture.
OVER_BROAD_TABLE_DELETE_CLAIM = (
    re.compile(r"leaves\s+every\s+(?:inbound\s+)?link[^.]{0,90}?dangl", re.I),
    re.compile(r"every\s+(?:inbound\s+)?link\s+(?:into|pointing\s+at)\s+it\s+dangl", re.I),
    re.compile(r"dangling\s+in\s+every\s+other\s+table", re.I),
    # Reversed clause order — "…in EVERY OTHER TABLE left dangling" — and the bare
    # "every inbound link … dangle" a docstring can carry without the verb *leaves*.
    re.compile(r"every\s+inbound\s+link[^.]{0,90}?dangl", re.I),
    # Backticked type names standing in for the word "link".
    re.compile(r"leaves\s+every\s+inbound\s[^.]{0,120}?dangl", re.I),
)

#: The two documents the census does NOT read, and the reason is not convenience: a release
#: record is **dated history**. An entry published under a version already shipped says what was
#: claimed then, and rewriting it would destroy the record instead of superseding it (the reason
#: is preserved, only the conclusion moves). The correction is published as a NEW entry under the
#: open section instead — which is exactly what
#: :func:`test_the_DATED_RELEASE_RECORD_exclusion_is_ANSWERED_by_the_OPEN_SECTION` holds, so this
#: exclusion cannot become a hiding place.
DATED_RELEASE_RECORDS = ("CHANGELOG.md", "RELEASE_NOTES.md")


def _census_files():
    """Every file a consumer's claim could be shipped in, plus the dev-repo register.

    ``src/larkdocio/**`` is what the wheel carries — every module (docstrings, constants,
    refusal text) and every packaged document. ``BASE.md`` is the maintainer register whose
    row 32 says it *quotes* the invariant, so a divergence there is the same defect.
    """
    shipped = sorted((_ROOT / "src/larkdocio").rglob("*.py"))
    shipped += sorted((_ROOT / "src/larkdocio").rglob("*.md"))
    return [p for p in shipped + [_ROOT / "BASE.md"]
            if p.name not in DATED_RELEASE_RECORDS]


def _folded_string_values(path):
    """Reading (ii) for a module: every string literal **as the interpreter sees it**.

    CPython folds an implicit concatenation — adjacent literals with no operator between
    them — into a single constant at parse time, and folds the literal run of an
    f-string in with it. So walking the parsed tree yields the sentence a caller is
    handed, across the line breaks the author wrote it on. That is precisely the reading
    a source-text grep cannot take: a claim can be split at any character, and one was.
    """
    values = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            values.append("".join(
                part.value if isinstance(part, ast.Constant) and isinstance(part.value, str)
                else " " for part in node.values))
    return values


def _runtime_string_values():
    """Reading (ii), continued: the values the **imported** package actually holds.

    A constant composed at import time (``A + B``, an f-string interpolating another
    constant, a dict assembled from pieces) has no single literal anywhere in the source.
    Every module of the wheel is imported and every string it exposes — module attributes,
    docstrings, and the two published projections ``guide()`` and ``capabilities()`` — is
    read as a value. Between this and the folded literals above, a claim has nowhere left
    to hide: source text catches what only exists as text, values catch what only exists
    once assembled.
    """
    values = [larkdocio.guide(full=True),
              json.dumps(larkdocio.capabilities(full=True), ensure_ascii=False)]
    package = importlib.import_module("larkdocio")
    for info in pkgutil.walk_packages(package.__path__, prefix="larkdocio."):
        module = importlib.import_module(info.name)
        values.append(module.__doc__ or "")
        for name in dir(module):
            attribute = getattr(module, name, None)
            if isinstance(attribute, str):
                values.append(attribute)
            elif callable(attribute) and getattr(attribute, "__doc__", None):
                values.append(attribute.__doc__)
    return values


def test_NO_SHIPPED_TEXT_still_asserts_the_OVER_BROAD_table_delete_claim():
    """**The grep that was owed, run as a guard so it cannot be skipped again — and now run
    BOTH WAYS, because each single reading has already let a survivor through.**

    The per-kind measurement makes *"deleting a table leaves every link into it dangling"*
    false: an inbound one-way column survives and dangles, an inbound two-way column does not
    survive at all. Any shipped sentence still saying *every* link dangles is the superseded
    conclusion still on sale.

    **Reading (i) is the source text** — what a maintainer reads, including the prose that
    only ever exists as a comment or a document. **Reading (ii) is the values** — what a
    caller is handed, with implicit concatenations folded and import-time composition done.
    A value-level grep alone walked past a claim written across adjacent literals; a
    source-level grep alone walked past the same claim seen from the other side. Neither
    reading is a superset of the other, so the census takes both.
    """
    hits = []
    for path in _census_files():
        text = path.read_text(encoding="utf-8")
        for pattern in OVER_BROAD_TABLE_DELETE_CLAIM:
            for match in pattern.finditer(text):
                hits.append(("source", str(path.relative_to(_ROOT)),
                             text[:match.start()].count("\n") + 1,
                             match.group(0)))
        if path.suffix == ".py":
            for value in _folded_string_values(path):
                for pattern in OVER_BROAD_TABLE_DELETE_CLAIM:
                    for match in pattern.finditer(value):
                        hits.append(("value", str(path.relative_to(_ROOT)),
                                     None, match.group(0)))
    for value in _runtime_string_values():
        for pattern in OVER_BROAD_TABLE_DELETE_CLAIM:
            for match in pattern.finditer(value):
                hits.append(("runtime", None, None, match.group(0)))
    # One sentence can be reached twice by the same reading (a folded f-string run is also
    # walked as its own constant); a survivor is a place, not a count.
    unique = list(dict.fromkeys(hits))
    assert unique == [], unique


def test_the_DATED_RELEASE_RECORD_exclusion_is_ANSWERED_by_the_PUBLISHING_SECTION():
    """The two excluded documents are excluded as **history**, and history is only honest if the
    correction is published. A section of the packaged notes carries it, per kind, in the copy a
    wheel-only consumer reads.

    **TRANSFORMED, not weakened (LD-476) — the reason is preserved and only the locator moved.**
    The reason stands exactly as written above: the correction must be *published*, in the
    packaged file, split per kind. What moved is *where this guard looks*. It used to read the
    **topmost** section, which was right only while the entry was still **pending**: the
    correction was drafted under ``[1.34.0]``, that section was cut before it landed, so the
    pending entry was relocated into the section the change opened (``[1.36.0]``) — nothing cut
    was ever edited. Since ``[1.36.0]`` was cut and dated the entry is *landed history*, and the
    next change to open a section (``[1.37.0]``) must not drag it forward: **a cut, dated
    section is never edited, and its published text is never restated as if it were new.** So
    the section is now located **by content** — the one that published the correction — and all
    three per-kind phrases must live in that same section, which must still be a real
    ``## [X.Y.Z] — YYYY-MM-DD`` release section of the packaged notes. Deleting the correction,
    scattering the three phrases across sections, or demoting it out of a release section all
    still redden; a guard naming ``[1.34.0]`` or ``[1.36.0]`` outright would instead have gone
    green against history the moment a section was cut.

    **TRANSFORMED again (LD-592), and again only the locator moved.** The reason above is
    untouched: the correction must be *published*, in a real dated release section, split per
    kind, never restated. What expired is one premise this guard silently rested on — that the
    PACKAGED copy carries the publishing section forever. It does not: that copy is a window of
    the newest releases by design, and the window rolls at every cut, so the section aged past
    its edge with nothing rewritten (exactly what the copy's own banner says will happen, and
    the same amendment ``test_sheets_doc_truth_ld472.py``'s AC6 record arm already took). The
    invariant now reads the CANONICAL ROOT document — the complete history, which is what the
    refresh script drops beside the wheel as ``vendor/larkdocio-RELEASE_NOTES.md`` — and the
    wheel-facing arm is **kept for as long as it can be true**: while the publishing section is
    still inside the window, the packaged copy must carry it too, byte for byte. Deleting the
    correction, scattering the three phrases, or demoting it out of a release section all still
    redden, in both copies.
    """
    def _sections(text):
        return re.split(r"^(?=## \[\d+\.\d+\.\d+\] — \d{4}-\d{2}-\d{2}$)", text,
                        flags=re.MULTILINE)[1:]

    root = (_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    publishing = [s for s in _sections(root)
                  if "does NOT leave every inbound link dangling" in s]
    assert len(publishing) == 1, (
        "the per-kind table-delete correction must be published in exactly one release section "
        f"of RELEASE_NOTES.md — found {len(publishing)}"
    )
    section = publishing[0]
    header = section.splitlines()[0]
    assert re.match(r"^## \[\d+\.\d+\.\d+\] — \d{4}-\d{2}-\d{2}$", header)
    assert "does not survive at all" in section
    assert "survives and dangles" in section

    # The wheel-facing arm, while the window still reaches it: no separate expectation is
    # written down — the packaged copy either carries that section or the window has moved
    # past it, and only the first case is asserted.
    packaged = (_ROOT / "src/larkdocio/RELEASE_NOTES.md").read_text(encoding="utf-8")
    if header in packaged:
        in_wheel = [s for s in _sections(packaged) if s.splitlines()[0] == header]
        assert len(in_wheel) == 1 and in_wheel[0] == section, (
            "the packaged copy still carries the publishing section but not verbatim — the "
            "projection must never reflow or edit a byte"
        )


def test_the_INVARIANT_EVERY_REFUSAL_QUOTES_splits_the_two_KINDS_and_the_two_ROUTES():
    """``LOSS_MUST_BE_ENUMERABLE`` rides **every** destructive refusal on this surface and is the
    text ``BASE.md`` row 32 says it quotes. It keeps its own subject — an unenumerable loss
    refuses, app-scoped — and now states the table-delete outcome per kind, on the table route,
    without borrowing the column route's reading (**D-59**)."""
    invariant = loss_preview.LOSS_MUST_BE_ENUMERABLE
    assert "cannot be enumerated" in invariant
    assert "whole app" in invariant
    assert "under-report" in invariant.lower()
    lowered = invariant.lower()
    assert "one-way" in lowered and "two-way" in lowered
    assert "does not survive" in lowered or "not survive at all" in lowered
    assert "different call" in lowered, (
        "deleting a COLUMN and deleting a TABLE are different routes; the sentence must split "
        "them rather than blur them")


def test_the_CAPABILITY_CONTRACT_and_the_SHIPPED_GUIDE_row_AGREE_per_kind():
    """One contract id, two projections, one truth. ``capabilities()`` publishes the
    ``cross-table-loss-preview`` summary and the shipped guide carries a row for the same id;
    a consumer who reads both must not be told two different things."""
    summary = larkdocio.capabilities(full=True)["safety_contracts"][
        "cross-table-loss-preview"]["summary"].lower()
    # ``guide()`` returns the INDEX by default; the contract table lives in the body, so the
    # projection this test compares against is the full document.
    row = [line for line in larkdocio.guide(full=True).splitlines()
           if line.startswith("| `cross-table-loss-preview` |")]
    assert len(row) == 1, row
    for claim in (summary, row[0].lower()):
        assert "one-way" in claim and "two-way" in claim
        assert "dangle" in claim
        assert "twin" in claim
    # …and the contract has not lost what it was already for.
    for phrase in ("app-scoped", "mirror", "another table", "enumerate"):
        assert phrase in summary, phrase


def test_DELETE_TABLES_OWN_DOCSTRING_states_the_PER_KIND_outcome():
    """The op builder's docstring is the sentence a maintainer and ``help()`` meet first. It said
    a table delete leaves *every* link into it dangling; per kind it does not."""
    doc = schema_ops_destructive.delete_table.__doc__ or ""
    lowered = doc.lower()
    assert "one-way" in lowered and "two-way" in lowered
    assert "dangl" in lowered
    assert "silent" in lowered, "the whole point of the sentence is that nothing reports it"
