"""THE BASE SCHEMA-WRITE FRONT DOOR — and the RETRACTION of the sentence that preceded it.

LD-260 published ``base-write`` and, in the same breath, drew a line everywhere a consumer
reads: **"larkdocio writes records; it does not write schema."** That sentence was true when it
shipped. The field allow-list, the field create / update / convert engine, the app and table
lifecycle, the view lifecycle with its persistent filters and the destructive family behind a
loss preview and a consent fence have all landed since. **The sentence is now false, and this
module is where it dies** — asserted as an ABSENCE, not merely as the presence of a newer one,
because a front door that gains a true sentence while keeping a false one has not been
corrected, it has been made to contradict itself.

What this module holds:

* **the retraction**, site by site — ``README.md`` (the wheel ``METADATA`` body), the wheel
  ``Summary`` and ``Keywords``, ``capabilities()``, the shipped ``guide()``, the rendered
  ``larkdocio --help`` and ``BASE.md``. Every one of the six places LD-260 put the claim;
* **the replacement, bounded to what the rung actually shipped** — fields across an allow-list,
  tables, views with persistent FILTERS, the destructive family behind a preview and a consent
  fence. **Not one word more**: grouping, hidden fields and a view-level sort are not knobs this
  library offers, and a form view is refused by this library's own policy;
* **``capabilities()`` reporting a FIFTH Base surface, ``base-schema-write``** — its scopes the
  union of its operations' own derived rows, its real ``gate_coverage``, its safety contracts
  including the two this rung is the first to need, and the **asymmetry** of the revision guard
  stated rather than smoothed: a field op rides ``table.revision``; an app-scoped or
  view-scoped op carries no guard at all;
* **the register audit** — every CANNOT and every policy refusal this rung produces resolves to
  a real ``BASE.md`` register row with a recognised status slug, its evidence and its revisit
  trigger. **This story adds no row**; it verifies that the rows the rung owed are there.
"""
import re
from pathlib import Path

import pytest

import private_tree  # noqa: E402  (LD-691)

import consumer_text
import front_door as fd
from consumer_text import dialect_hits
import capability_rows as rows
from larkdocio import capabilities, guide
from larkdocio.base import Refusal
from larkdocio.capabilities._contracts import APPLY_LOG_COMPLETE

from guard_kit import REPO_ROOT

_REPO = REPO_ROOT
_BASE_MD = (_REPO / "BASE.md").read_text(encoding="utf-8")

#: The surface this story publishes — the fifth Base surface, and the second that writes.
SCHEMA_WRITE = "base-schema-write"

#: The landed live modules ``base-schema-write``'s coverage may name, and nothing else. The
#: guided COLUMN-TYPE MIGRATION arm is the sixth: it is a schema-write gate — it authors a
#: column, deletes a populated one and renames another — so a ring that did not name it would
#: be pricing this surface's live coverage short by its most destructive composition.
SCHEMA_WRITE_RING = (
    "tests/test_live_base_schema_arm.py",
    "tests/test_live_base_schema_fields.py",
    "tests/test_live_base_field_migration.py",
    "tests/test_live_base_views.py",
    "tests/test_live_base_destructive.py",
    "tests/test_live_base_schema_gate.py",
)

#: **THE SENTENCE THIS STORY RETRACTS**, in the shapes LD-260 actually wrote it. Matched over
#: whitespace-flattened, lower-cased text so a re-wrap cannot smuggle one back in.
RETRACTED_CLAIMS = (
    "does not write schema",
    "it does not write schema",
    "the schema is read-only",
    "schema read-only",
    "records writable, schema read-only",
    "the schema stays read-only",
    "deleting anything structural is not shipped at all",
    # The paraphrase the group ``--help`` used, which a literal-only list read straight past.
    "never the schema",
    "changes records and never the schema",
    "is created, renamed or deleted by anything here",
)

#: A literal list catches only the spellings someone thought to write down; the claim survived
#: one review inside a **paraphrase** of itself. These are the claim's SHAPES, so a re-wording
#: is caught by what it asserts rather than by how it happens to be spelled. Each is matched
#: against the same whitespace-flattened, lower-cased text.
#: A gap inside ONE clause. Crossing a sentence end, a semicolon or a dash joins two unrelated
#: statements into a claim neither of them makes — which is how the first draft of this net read
#: *"a view holds no data of its own; a table's last view cannot be deleted"* as the retraction.
_G = r"[^.;:—]"

RETRACTED_CLAIM_PATTERNS = (
    # "never writes / does not change / cannot touch … the schema"
    ("denies-writing-schema", re.compile(
        r"\b(never|not|no|cannot|can't)\b" + _G + r"{0,40}"
        r"\b(writ\w+|chang\w+|touch\w+|alter\w+|modif\w+)\b" + _G + r"{0,30}\bschema\b")),
    # "the schema is / stays / remains read-only (untouched, unchanged, immutable)" — but NOT
    # "the surface that is **not** read-only", which is the true sentence saying the opposite.
    ("schema-frozen", re.compile(
        r"\bschema\b" + _G + r"{0,40}\b(is|stays|remains)\b"
        r"(?:(?!\bnot\b)" + _G + r"){0,25}"
        r"\b(read-only|readonly|untouched|unchanged|immutable)\b")),
    # "changes RECORDS and never the SCHEMA" — the contrast the claim retreats into.
    ("records-but-not-schema", re.compile(
        r"\brecords?\b" + _G + r"{0,40}\b(and|but)\b" + _G + r"{0,20}"
        r"\b(never|not|no)\b" + _G + r"{0,30}\bschema\b")),
    # "no field, table or view is created, renamed or deleted" — the claim spelled out as a
    # denial of the structural verbs. Two of the three nouns are required inside one clause, so
    # a single honest refusal ("a table's last view cannot be deleted") is not swept up with it.
    ("denies-structural-verbs", re.compile(
        r"\b(no|not|never)\b" + _G + r"{0,40}\b(field|table|view)s?\b" + _G + r"{0,20}"
        r"\b(field|table|view)s?\b" + _G + r"{0,60}\b(created|renamed|deleted)\b")),
)

#: **Quoting the claim in order to retract it is the opposite of asserting it.** The release
#: notes have to be able to say *what* changed, and a guard that forbids naming the retracted
#: sentence would force the one document a consumer reads at upgrade time to be vague about it.
#: So a hit is forgiven only inside a clause that carries the retraction in the SAME sentence —
#: a bare restatement one sentence later is still a failure.
_RETRACTION_FRAME = re.compile(
    r"until this release|before this release|used to (draw|say|read)|no longer (true|says)"
    r"|(is|was|now) retracted|the sentence is gone|that line is gone")

#: The sentence as it actually shipped in the group ``--help``, kept verbatim as the guard's
#: own regression fixture: the widened guard must bite on THIS text, not merely on the text
#: that replaced it.
THE_SPELLING_THAT_SURVIVED = (
    "On a Base the write engine changes RECORDS and never the SCHEMA — no field, table or "
    "view is created, renamed or deleted by anything here."
)

#: What the door is allowed to say instead — the ruled surface and nothing wider.
_TRUE_SHAPE_WORDS = ("field", "table", "view", "filter")


@pytest.fixture(scope="module")
def caps():
    return capabilities(full=True)


@pytest.fixture(scope="module")
def guide_text():
    return guide(full=True)


def _flat(text):
    return " ".join(text.lower().split())


def _sentences(flat):
    return [s for s in re.split(r"(?<=[.!?]) ", flat) if s]


def retraction_hits(text):
    """Every place ``text`` still ASSERTS the retracted claim, as ``[(kind, matched)]``.

    Both nets at once — the literal spellings and the claim shapes — so a caller cannot use one
    and silently skip the other. Sentence by sentence, because the unit that asserts something
    is a sentence, and because that is what lets a sentence which names the claim *in order to
    retract it* be told apart from one that still makes it.
    """
    hits = []
    for sentence in _sentences(_flat(text)):
        found = [("literal", claim) for claim in RETRACTED_CLAIMS if claim in sentence]
        found += [(name, match.group(0))
                  for name, pattern in RETRACTED_CLAIM_PATTERNS
                  for match in pattern.finditer(sentence)]
        if found and not _RETRACTION_FRAME.search(sentence):
            hits += found
    return hits


# --------------------------------------------------------------------------- #
# AC1 — the retraction, asserted as an ABSENCE, at every site LD-260 wrote it   #
# --------------------------------------------------------------------------- #

def test_ac1_THE_GUARD_ITSELF_bites_on_the_spelling_that_once_slipped_through():
    """The gap this story's first pass left open, closed and pinned.

    A literal-only list read straight past the group ``--help``'s paraphrase, so the corpus
    test below was green while the claim was still shipping. The guard is only worth the
    absence it asserts, so it is run here against the offending sentence VERBATIM."""
    hits = retraction_hits(THE_SPELLING_THAT_SURVIVED)
    assert hits, (
        "the retraction guard does not recognise the very sentence it was written to remove")
    kinds = {kind for kind, _ in hits}
    assert kinds - {"literal"}, (
        "only the literal net fired — a further re-wording would slip past again, which is "
        "exactly how this one did")
    assert "records-but-not-schema" in kinds and "denies-structural-verbs" in kinds, kinds


@pytest.mark.parametrize("paraphrase", [
    "the write engine never writes the schema.",
    "this library does not change a Base schema.",
    "on a Base, schema stays read-only.",
    "it edits records but not the schema.",
    "no table or field is ever created or deleted.",
])
def test_ac1_THE_GUARD_bites_on_RE_WORDINGS_of_the_same_claim(paraphrase):
    assert retraction_hits(paraphrase), paraphrase


@pytest.mark.parametrize("true_sentence", [
    # The honest refusals the replacement text is allowed to make must survive the widening,
    # or the guard would force the door to stop saying true things.
    "a form view is refused by this library's own policy.",
    "view grouping, hidden fields and a view-level sort are not offered here.",
    "an app-scoped schema op carries no revision guard at all.",
    "the schema surface writes fields, tables and views with persistent filters.",
])
def test_ac1_THE_GUARD_does_NOT_bite_on_the_TRUE_post_rung_sentences(true_sentence):
    assert retraction_hits(true_sentence) == [], true_sentence


def test_ac1_NAMING_the_claim_in_order_to_RETRACT_it_is_allowed():
    """The release notes have to be able to say what changed."""
    assert retraction_hits(
        "Until this release every document said larkdocio writes records and does not write "
        "schema. That is no longer true.") == []


def test_ac1_but_the_FORGIVENESS_DOES_NOT_LEAK_into_the_next_sentence():
    """The exemption is per-sentence on purpose: a retraction paragraph is not a licence to
    restate the claim underneath it."""
    hits = retraction_hits(
        "Until this release the door said the schema is read-only. On a Base the write engine "
        "changes records and never the schema.")
    assert hits, "a bare restatement after a retraction frame must still fail"
    assert all(claim != "the schema is read-only" for _, claim in hits)


def test_ac1_NO_SHIPPED_CONSUMER_DOCUMENT_still_says_the_schema_is_read_only():
    """The whole guarded corpus at once: README, the Summary, the Keywords, the guide, every
    rendered ``--help`` page and the packaged release notes."""
    for name, text in consumer_text.shipped_docs().items():
        hits = retraction_hits(text)
        assert hits == [], (
            f"{name} still carries the retracted claim {hits!r} — the schema surface "
            "shipped, so the sentence is false where it stands")


def test_ac1_the_CAPABILITIES_REGISTRY_carries_the_claim_nowhere(caps):
    """The registry is read programmatically, so a stale sentence in it is a stale answer to a
    question a consumer asked in code."""
    import json

    assert retraction_hits(json.dumps(caps, ensure_ascii=False)) == []


def test_ac1_BASE_MD_no_longer_draws_the_line_it_drew(caps):
    assert retraction_hits(_BASE_MD) == []


def test_ac1_the_README_LAYOUT_ROW_describes_the_TRUE_post_rung_shape():
    readme = fd.readme_text()
    assert "src/larkdocio/base/" in fd.documented_layout_paths(readme)
    row = next(line for line in readme.splitlines()
               if line.strip().startswith("|") and "`src/larkdocio/base/`" in line)
    lowered = row.lower()
    assert SCHEMA_WRITE in lowered, "the layout row must name the surface that now ships"
    for word in _TRUE_SHAPE_WORDS:
        assert word in lowered, word
    assert retraction_hits(row) == []


def test_ac1_the_WHEEL_SUMMARY_names_every_surface_word_INCLUDING_schema():
    """``required_surface_keywords()`` is derived from the registry, so publishing a surface
    called ``base-schema-write`` widens the requirement on its own — the Summary cannot stay
    behind without reddening."""
    description = fd.pyproject()["project"]["description"]
    assert fd.description_surface_gaps(description) == []
    assert "schema" in description.lower()
    assert "no schema" not in _flat(description), (
        "the Summary's parenthetical denial is exactly the retracted claim, compressed")


def test_ac1_the_WHEEL_KEYWORDS_carry_the_schema_word():
    keywords = [k.lower() for k in fd.pyproject()["project"]["keywords"]]
    assert any("schema" in k for k in keywords), keywords


def test_ac1_the_rendered_GROUP_HELP_rolls_the_new_surface_and_stays_read_only():
    page = fd.group_help_page()
    missing, phantom = fd.surface_roll_diff(page)
    assert not missing and not phantom, (missing, phantom)
    assert SCHEMA_WRITE in fd.help_surface_roll(page)
    # This story publishes a LIBRARY surface, and it still does. TRANSFORMED by LD-492:
    # the command line gained a writing verb, so "NEVER WRITES" became false; what this
    # story actually claims is that no SCHEMA write is reachable from it, which is what
    # the Base sentence below says.
    assert "roundtrip push --apply" in page
    assert "The STANDALONE Base surface is a LIBRARY call too" in " ".join(page.split())


def test_ac1_the_GUIDE_retracts_the_no_structural_delete_sentence(guide_text):
    flat = _flat(guide_text)
    assert "deleting anything structural is not shipped at all" not in flat
    assert "delete_field" in guide_text and "delete_table" in guide_text, (
        "the guide must name the verbs that replaced the sentence")


def test_ac1_the_BASE_PACKAGE_DOCSTRING_names_the_schema_surface():
    import larkdocio.base as base_pkg

    doc = base_pkg.__doc__ or ""
    assert SCHEMA_WRITE in doc, "the package docstring is a front door too"
    assert retraction_hits(doc) == []


# --------------------------------------------------------------------------- #
# AC10 — capabilities() reports the schema-write surface HONESTLY               #
# --------------------------------------------------------------------------- #

def test_ac10_a_FIFTH_base_surface_exists_and_it_writes(caps):
    surface = caps["surfaces"][SCHEMA_WRITE]
    assert surface["domain"] == "base"
    assert surface["mode"] == "write"
    base_surfaces = [sid for sid, s in caps["surfaces"].items() if s["domain"] == "base"]
    assert len(base_surfaces) == 5, base_surfaces
    assert sorted(sid for sid in base_surfaces
                  if caps["surfaces"][sid]["mode"] == "write") == [SCHEMA_WRITE, "base-write"]


def test_ac10_the_operations_are_PROJECTED_from_the_schema_op_aggregator(caps):
    """Never a second list. The registry that ENFORCES the op set is the one published."""
    from larkdocio.base import schema_ops

    names = rows.names(caps["surfaces"][SCHEMA_WRITE], rows.OPERATION)
    assert names == [descriptor.name for descriptor in schema_ops.schema_ops()]
    assert len(names) == 15, names
    for op in rows.call_sites(caps["surfaces"][SCHEMA_WRITE], rows.OPERATION):
        assert op["projected_from"] == "larkdocio.base.schema_ops.schema_ops"
    # All four families reach the door, so no family can ship unpublished.
    assert {schema_ops.family_of(n).name for n in names} == {
        "app-and-table", "field", "view", "destructive"}


def test_ac10_the_scopes_are_the_UNION_OF_ITS_OPERATIONS_ROWS_and_widen_nothing(caps):
    surface = caps["surfaces"][SCHEMA_WRITE]
    from_ops = set()
    for op in rows.call_sites(surface):
        from_ops |= rows.scope_strings(caps, op["permissions"])
    assert set(surface["credentials"]["scopes"]) == from_ops
    assert from_ops == {"bitable:app"}, sorted(from_ops)
    # The schema surface asks for no scope the record surface did not already need.
    assert from_ops == set(caps["surfaces"]["base-write"]["credentials"]["scopes"])


def test_ac10_every_operation_carries_a_DERIVED_permission_block(caps):
    for op in rows.call_sites(caps["surfaces"][SCHEMA_WRITE], rows.OPERATION):
        block = op["permissions"]
        assert block["basis"] == "derived", op["name"]
        assert block["endpoints"], (
            f"{op['name']} derived NO endpoint — its requirement would read as 'needs "
            "nothing', which is the one answer that cannot be checked")


def test_ac10_it_runs_on_the_WRITE_credential_pair(caps):
    from larkdocio.common.auth import WRITE_ENV

    creds = caps["surfaces"][SCHEMA_WRITE]["credentials"]
    assert creds["app"] == "write"
    assert creds["env_primary"] == list(WRITE_ENV)


def test_ac10_the_safety_contracts_include_the_TWO_this_rung_is_first_to_need(caps):
    surface = caps["surfaces"][SCHEMA_WRITE]
    # LD-493 added a third the rung needs: this is where a Base is CREATED and COPIED, and
    # both now require a caller-supplied destination.
    assert sorted(surface["safety_contracts"]) == sorted([
        "plan-gated", "dry-run-mandatory", "destructive-consent-required",
        "cross-table-loss-preview", "revision-guard-field-scoped-only",
        "caller-supplied-destination", APPLY_LOG_COMPLETE])
    catalog = caps["safety_contracts"]
    for contract in surface["safety_contracts"]:
        assert contract in catalog, contract
        assert SCHEMA_WRITE in catalog[contract]["applies_to"], contract


def test_ac10_the_REVISION_GUARD_ASYMMETRY_is_stated_and_not_smoothed(caps):
    """``STALE_BASE`` covers **field-scoped** ops. App-scoped and view-scoped ops carry NO
    guard at all — and a surface that let the reader assume otherwise would be claiming a
    protection it does not have."""
    summary = caps["safety_contracts"]["revision-guard-field-scoped-only"]["summary"].lower()
    # LD-457 TRANSFORMED THE NEEDLE, NOT THE CHECK. The summary still has to name the record
    # engine's guard — what changed is HOW it names it: the SCREAMING spelling is a contract
    # id, while the string a consumer's `entry.refusal.reason ==` can match is the wire value
    # `Refusal.STALE_BASE` carries. The needle is derived from the engine so it cannot drift.
    for phrase in ("table.revision", Refusal.STALE_BASE, "no revision guard", "app-scoped",
                   "view-scoped", "read-back"):
        assert phrase in summary, phrase
    for forbidden in ("atomic", "all-or-nothing", "transaction"):
        assert forbidden not in summary, forbidden
    # And STALE_BASE itself is NOT claimed surface-wide, which would be false for 12 of 15 ops.
    assert "STALE_BASE" not in caps["surfaces"][SCHEMA_WRITE]["safety_contracts"]
    assert SCHEMA_WRITE not in caps["safety_contracts"]["STALE_BASE"]["applies_to"]


def test_ac10_the_CONSENT_FENCE_and_the_CROSS_TABLE_PREVIEW_say_what_they_do(caps):
    catalog = caps["safety_contracts"]
    consent = catalog["destructive-consent-required"]["summary"].lower()
    for phrase in ("consent", "its own plan", "delete"):
        assert phrase in consent, phrase
    preview = catalog["cross-table-loss-preview"]["summary"].lower()
    for phrase in ("app-scoped", "mirror", "another table", "enumerate"):
        assert phrase in preview, phrase


def test_ac10_the_ALLOW_LIST_CONSTANT_is_published_on_the_surface_that_ENFORCES_it(caps):
    from larkdocio.base import field_vocabulary as fv

    authoring = caps["surfaces"][SCHEMA_WRITE]["field_authoring"]
    assert authoring is not None
    assert tuple(authoring["authorable_types"]) == fv.AUTHORABLE_TYPES
    assert tuple(authoring["authorable_ui_types"]) == fv.AUTHORABLE_UI_TYPES
    for unauthorable in ("Lookup", "Stage", "Email"):
        assert unauthorable in authoring["not_authorable"], unauthorable


def test_ac10_the_surface_states_its_LIMITATIONS_where_the_registry_is_read(caps):
    """A surface row that lists fifteen operations and nothing else says the schema write is
    complete. It is not, and these are the facts a consumer plans differently around."""
    note = _flat(caps["surfaces"][SCHEMA_WRITE]["credentials"]["note"])
    for needle in ("allow-list", "filter", "grouping", "hidden", "sort", "form",
                   "revision", "read-back"):
        assert needle in note, f"the schema-write credentials note never mentions {needle!r}"


def test_ac10_NO_WIDER_CLAIM_than_the_rung_shipped_reaches_the_surface(caps):
    """The phantom fence in the other direction: a knob this library does not offer must not
    appear as though it does.

    **The lifecycle half is TRANSFORMED, not struck.** It used to assert the surface published
    **no** lifecycle at all, with the reason *"a lifecycle pair claims a create AND a destroy; a
    Base has no purge verb at all"*. The **purge** clause of that reason is still true and is
    still asserted below — no verb here purges, and the whole-object delete is a trash whose
    trashed token Drive metadata keeps resolving. What fell is the **destroy** clause: the delete
    now exists, so the honest assertion is not *absent* but *exactly one, and it is the trash*.
    An empty or missing lifecycle would now be the under-claim.
    """
    surface = caps["surfaces"][SCHEMA_WRITE]
    names = set(rows.names(surface, rows.OPERATION))
    for phantom in ("set_view_group", "hide_fields", "set_view_sort", "create_form_view",
                    "delete_app", "upload_attachment", "resolve_link"):
        assert phantom not in names, phantom
    lifecycle = rows.call_sites(surface, rows.LIFECYCLE)
    assert [op["name"] for op in lifecycle] == ["delete_base"], lifecycle
    assert not any("purge" in op["name"] for op in lifecycle), (
        "there is no purge verb on this surface and there is none on the API")
    assert "create_app" not in {op["name"] for op in lifecycle}, (
        "the create is a registered plan-gated schema op, and publishing it under both kinds "
        "would collapse its two permission rows into one")
    assert "create_app" in names


def test_ac10_the_GATE_COVERAGE_names_its_OWN_RING_and_every_member_EXISTS(caps):
    coverage = caps["surfaces"][SCHEMA_WRITE]["gate_coverage"]
    assert coverage is not None
    assert coverage["marker"] == "live_write"
    # LD-539: the payload states the command a consumer can TYPE, and the bare
    # command has not run the ring since LD-537 armed the consent fence.
    assert coverage["command"] == "LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-NNN pytest -m live_write"
    modules = [member["module"] for member in coverage["members"]]
    assert sorted(modules) == sorted(SCHEMA_WRITE_RING), modules
    for member in coverage["members"]:
        path = _REPO / member["module"]
        assert path.exists(), member["module"]
        statement = "pytestmark = pytest.mark.live_write"
        assert any(line.startswith(statement)
                   for line in path.read_text(encoding="utf-8").splitlines()), member["module"]
    assert "LARKDOCIO_SCRATCH_BASE" in coverage["target_policy"]


def test_ac10_every_safety_contract_is_PROVED_BY_SOME_RING_MEMBER(caps):
    """The phantom-claim direction ``tests/test_capabilities.py`` exists to catch: a schema
    ring reporting coverage its live arms do not actually run."""
    surface = caps["surfaces"][SCHEMA_WRITE]
    proved = {c for m in surface["gate_coverage"]["members"] for c in m["proves_contracts"]}
    unproved = sorted(set(surface["safety_contracts"]) - proved)
    assert not unproved, unproved


def test_ac10_no_ring_member_claims_a_contract_the_surface_does_not_carry(caps):
    surface = caps["surfaces"][SCHEMA_WRITE]
    catalog = caps["safety_contracts"]
    for member in surface["gate_coverage"]["members"]:
        for contract in member["proves_contracts"]:
            assert contract in catalog, (member["id"], contract)
            assert contract in surface["safety_contracts"], (member["id"], contract)


def test_ac10_the_BASE_WRITE_surface_is_UNCHANGED_except_for_its_retracted_prose(caps):
    """The record engine did not move. Its six operations, its scopes and its own contracts are
    exactly what LD-260 published — only the sentence about the schema is different."""
    from larkdocio.base import write_ops

    surface = caps["surfaces"]["base-write"]
    assert rows.names(surface, rows.OPERATION) == [
        d.name for d in write_ops.WRITE_OPS]
    assert sorted(surface["safety_contracts"]) == sorted(
        ["STALE_BASE", "dry-run-mandatory", "plan-gated", APPLY_LOG_COMPLETE])


# --------------------------------------------------------------------------- #
# AC11 — the BASE.md register audit. This story adds NO row.                    #
# --------------------------------------------------------------------------- #

def _register_rows():
    import test_base_md_matrix as matrix

    return matrix._register_rows(_BASE_MD)


def test_ac11_the_register_is_VERIFIED_AT_ITS_PINNED_HEIGHT_and_NOT_MOVED():
    """The audit's first move: this story adds nothing. Every row the rung needed was added by
    the issue that discovered it, which is where the evidence was."""
    import test_base_md_matrix as matrix

    rows = _register_rows()
    assert len(rows) == matrix._REGISTER_ROWS, (
        "LD-266 audits the register; it does not move it. A changed height here means a row "
        "was added by the gate rather than by the story that owed it")


@pytest.mark.parametrize("row_number,needle", [
    (2, "group"),          # grouping — extended, not new
    (11, "lookup"),        # Lookup / Stage / Email — un-authorable; copy is the route
    (16, "role"),          # advanced permissions — a product feature gate
    (17, "form"),          # form views — refused by this library's own policy
    (29, "convert"),       # conversion pairs — captured pairs only
    (28, "revision"),      # app-scoped ops carry no revision guard
    (30, "hidden_fields"),  # hidden fields — both observations
    (31, "sort"),          # view-level sort — uncaptured
    (32, "enumerat"),      # a loss that cannot be enumerated refuses
])
def test_ac11_every_CANNOT_this_rung_produces_RESOLVES_TO_A_REAL_ROW(row_number, needle):
    rows = {int(row["#"]): row for row in _register_rows()}
    assert row_number in rows, f"register row {row_number} is missing"
    blob = " ".join(str(v) for v in rows[row_number].values()).lower()
    assert needle in blob, (row_number, needle, blob[:160])


def test_ac11_every_audited_row_carries_ITS_EVIDENCE_AND_ITS_REVISIT_TRIGGER():
    rows = {int(row["#"]): row for row in _register_rows()}
    for number in (2, 11, 16, 17, 28, 29, 30, 31, 32):
        row = rows[number]
        assert len(row["Evidence"].strip()) > 20, number
        assert len(
            row["Revisit trigger — the observable API change"].strip()) > 20, number


def test_ac11_every_audited_row_uses_a_RECOGNISED_STATUS_SLUG():
    import test_base_md_matrix as matrix

    rows = {int(row["#"]): row for row in _register_rows()}
    for number in (2, 11, 16, 17, 28, 29, 30, 31, 32):
        assert rows[number]["Status"].strip().strip("`") in matrix._STATUSES, number


def test_ac11_BUTTON_is_still_WILL_NOT_SUPPORT_and_was_not_quietly_widened():
    rows = {int(row["#"]): row for row in _register_rows()}
    blob = " ".join(str(v) for v in rows[13].values()).lower()
    assert "button" in blob
    assert "will-not-support" in blob or "will not support" in blob


def test_ac11_the_MATRIX_GUARD_still_bites_on_a_row_stripped_from_the_register():
    """The completeness half, proved by running the real reader against a defect rather than
    by trusting it.

    The row it removes is the register's **LAST**, derived from the pinned count rather than
    written down: a row removed from the middle splits the table in the reader's parse and the
    count stops being the thing under test. It used to name row 32 because 32 was the tail at
    the time; a later story appending at the tail made that a stale literal, so the number now
    follows the pin.
    """
    import re

    import test_base_md_matrix as matrix

    last = matrix._REGISTER_ROWS
    stripped = re.sub(rf"^\| {last} \|.*$", "", _BASE_MD, count=1, flags=re.M)
    assert len(matrix._register_rows(stripped)) == last - 1


# --------------------------------------------------------------------------- #
# AC12 — dialect-free, and the _DECISION_REF trap respected                     #
# --------------------------------------------------------------------------- #

def test_ac12_every_new_registry_string_is_DIALECT_FREE(caps):
    surface = caps["surfaces"][SCHEMA_WRITE]
    catalog = caps["safety_contracts"]
    blobs = [surface["title"], surface["credentials"]["note"],
             surface["gate_coverage"]["target_policy"]]
    blobs += [member["summary"] for member in surface["gate_coverage"]["members"]]
    blobs += [catalog[cid]["summary"] for cid in ("destructive-consent-required",
                                                  "cross-table-loss-preview",
                                                  "revision-guard-field-scoped-only")]
    for blob in blobs:
        assert dialect_hits(blob) == [], (blob[:80], dialect_hits(blob))


def test_ac12_the_DECISION_REFERENCE_GUARD_is_NOT_WEAKENED_and_no_new_text_trips_it():
    source = Path(consumer_text.__file__).read_text(encoding="utf-8")
    assert "_DECISION_REF" in source
    for name, text in consumer_text.shipped_docs().items():
        assert dialect_hits(text) == [], (name, dialect_hits(text)[:3])


# --------------------------------------------------------------------------- #
# AC13 — the disclosure convention                                             #
# --------------------------------------------------------------------------- #

#: The disclosure section THIS STORY wrote into. It was the *uncut* heading at landing and the
#: constant was called ``_UNCUT``; v1.27.0 has since been cut, so the name now says what stays
#: true — **this story's prose lives under this heading, and no later cut may move it.** The
#: literal is legitimately version-shaped: it names one historic section, not the current
#: version (LD-316's sweep — see ``test_ac13_no_version_was_bumped_and_no_new_section_was_cut``,
#: which is the assertion that had to STOP naming a version).
_STORY_SECTION = "## [1.27.0]"


@private_tree.internal_log
def test_ac13_both_disclosure_files_gained_an_entry_under_THIS_STORYS_section():
    for name in ("CHANGELOG.md", "RELEASE_NOTES.md"):
        text = (_REPO / name).read_text(encoding="utf-8")
        section = text.split(_STORY_SECTION, 1)[1].split("\n## ", 1)[0]
        assert "schema" in section.lower(), name


def test_ac13_the_consumer_half_is_in_the_RELEASE_NOTES_and_carries_no_board_mechanics():
    text = (_REPO / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    section = text.split(_STORY_SECTION, 1)[1].split("\n## ", 1)[0]
    assert dialect_hits(section) == [], dialect_hits(section)[:3]
    hits = retraction_hits(section)
    assert hits == [], (
        f"this story's section still promises {hits!r} — the release a consumer will read "
        "cannot both ship the schema surface and deny it")


def test_ac13_the_PACKAGED_COPIES_are_shasum_identical_to_the_repo_root_ones():
    """AC13's claim was that this story's consumer-facing half actually ships — a section written
    only into the repository's copy would be invisible to the reader it was written for.

    **LD-540 narrowed the subject and dropped a third spelling of one rule.** The wheel carries a
    recent-N WINDOW of each release document now, so the claim is *the packaged copy is
    byte-identical to the projection of the root file*; and the comparison — previously a
    hand-rolled sha256 of each pair here, a second copy of a rule stated elsewhere — is delegated
    to the one function that defines it. A hash and a byte comparison prove the same thing; what
    mattered was that nothing weaker than exact equality was accepted, and nothing weaker is.
    """
    from test_shipped_notes import notes_identity_report

    assert notes_identity_report() == []


def test_ac13_no_version_was_bumped_and_no_new_section_was_cut():
    """The cut is the architect seat's. This story writes under the uncut heading and stops.

    **Stated as the INVARIANT, not as the landing-time literals (LD-316).** It used to read
    ``version == "1.26.0"`` and ``"## [1.28.0]" not in text`` — a photograph of the day it
    landed, which the v1.27.0 cut turned red without anything being wrong. What the assertion
    was *for* survives verbatim, in the form the house already owns
    (``tests/release_versions.py``, the AT-MOST-ONE-AHEAD rule):

    * this story's own section still exists, exactly once, and is still where its prose lives —
      it did not get moved, split or duplicated by a later cut;
    * **at most one** section sits ahead of the packaged version. One ahead is the cut in
      progress (``release.sh`` gates before it bumps, and refuses to tag an undocumented
      version); two would be pre-writing releases that do not exist — which is exactly the
      "no new section was cut" this test was written to refuse, and it still refuses it.
    """
    from release_versions import ahead_refusal, packaged_version, section_starts

    text = (_REPO / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert text.count(_STORY_SECTION) == 1
    versions = [version for version, _date, _line in section_starts(text.splitlines())]
    packaged = packaged_version((_REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert packaged == fd.pyproject()["project"]["version"], "the two readers disagree"
    refusal = ahead_refusal(versions, packaged)
    assert refusal is None, refusal
