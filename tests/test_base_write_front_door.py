"""THE BASE WRITE FRONT DOOR — the close-out that publishes a surface only once it exists.

LD-251 opened the door on the three Base **read** surfaces. This is the other half: the
record-write engine LD-255..LD-259 built is now described everywhere a consumer meets it, and
described **honestly** — it writes RECORDS and it does not write SCHEMA. Claiming a schema
write here would be the phantom-claim failure the front-door guards were built to catch.

What this module holds:

* **the registry** reports a fourth Base surface, ``base-write``, the first that is not
  read-only: its scopes the **union of its operations' own derived rows**, its safety contracts
  (``STALE_BASE``, the plan gate, and LD-254's house invariant **declared, not redefined**),
  and its real ``gate_coverage``;
* **``base-read``'s gate coverage too** (O6′) — LD-251 correctly refused to claim a ring that
  was still LD-252's unlanded product; LD-252 landed it, so the claim is now made from real
  files and bounded to what those two arms actually prove;
* **the door proper** — ``README.md`` (the wheel ``METADATA`` body), the ``Summary``, the
  package docstrings and the rendered ``larkdocio --help`` surface roll — says
  *writes records, does not write schema*;
* **the shipped guide** carries a Base-write recipe that **executes**, and states the
  no-``If-Match`` limitation in plain language;
* **dialect-free at birth**: every new consumer string passes the dialect guard, including
  its ``_DECISION_REF`` trap — a doctrine is stated in plain language, never as ``D3′(c)``.
"""
from pathlib import Path

import pytest

import consumer_text
import front_door as fd
import guide_recipes
from consumer_text import dialect_hits
import capability_rows as rows
from larkdocio import capabilities, guide
from larkdocio.capabilities._contracts import APPLY_LOG_COMPLETE

from guard_kit import REPO_ROOT

_REPO = REPO_ROOT
_BASE_MD = (_REPO / "BASE.md").read_text(encoding="utf-8")

#: The surface this story publishes — the fourth Base surface, and the first that writes.
BASE_WRITE = "base-write"

#: The landed live modules ``base-read``'s coverage may name, and nothing else. Three since the
#: raw-value arm joined the ring: retention's whole claim is about what the transport received
#: on THAT call, which is the one claim an offline fixture cannot make, so it is a live member
#: rather than an unregistered file. **Four** since the read-filter arm joined it on the same
#: reasoning turned inside out: whether ``records/search`` HONOURED a filter is unanswerable
#: offline, because an ignored body key and an honoured one both come back ``code:0``, so the
#: proof has to be a live comparison of two reads. Its ``view_id`` sibling is deliberately NOT
#: here — that one needs a view with a saved filter, which needs a write, so it rides a write
#: ring and self-provisions its target.
BASE_READ_RING = (
    "tests/test_live_base_canary.py",
    "tests/test_live_base_read_arm.py",
    "tests/test_live_base_read_filter.py",
    "tests/test_live_base_read_raw_values.py",
)

#: The landed live modules ``base-write``'s coverage may name. Three since LD-272 added the
#: relational gate — a record-surface member whose name is about what it PROVES rather than the
#: family it rides, which is why the ring's code-truth glob had to gain a second pattern.
BASE_WRITE_RING = (
    "tests/test_live_base_write_arm.py",
    "tests/test_live_base_write_gate.py",
    "tests/test_live_base_relational_gate.py",
)


@pytest.fixture(scope="module")
def caps():
    return capabilities(full=True)


@pytest.fixture(scope="module")
def guide_text():
    return guide(full=True)


# --------------------------------------------------------------------------- #
# AC7 — capabilities() reports base-write honestly                              #
# --------------------------------------------------------------------------- #

def test_ac7_the_registry_reports_the_base_RECORD_WRITE_surface_and_it_WRITES(caps):
    """LD-260 published this as the FOURTH Base surface and the only one that wrote. LD-266
    published a fifth, ``base-schema-write``, so the count moved — what this test still holds,
    and what it was really about, is that ``base-write`` is a Base write surface with the record
    engine under it. Its own shape is pinned below and did not move."""
    surface = caps["surfaces"][BASE_WRITE]
    assert surface["domain"] == "base"
    assert surface["mode"] == "write"
    base_surfaces = [sid for sid, s in caps["surfaces"].items() if s["domain"] == "base"]
    assert len(base_surfaces) == 5, base_surfaces
    assert sorted(sid for sid in base_surfaces
                  if caps["surfaces"][sid]["mode"] == "write") == [
        "base-schema-write", BASE_WRITE]


def test_ac7_the_base_write_scopes_are_the_UNION_OF_ITS_OPERATIONS_ROWS(caps):
    """Never a second assertion beside the operations — the same unification base-read got."""
    surface = caps["surfaces"][BASE_WRITE]
    from_ops = set()
    for op in rows.call_sites(surface):
        from_ops |= rows.scope_strings(caps, op["permissions"])
    assert set(surface["credentials"]["scopes"]) == from_ops
    assert from_ops == {"bitable:app"}, sorted(from_ops)


def test_ac7_every_base_write_operation_carries_a_DERIVED_permission_block(caps):
    for op in rows.call_sites(caps["surfaces"][BASE_WRITE], rows.OPERATION):
        block = op["permissions"]
        assert block["basis"] == "derived", op["name"]
        assert block["endpoints"], (
            f"{op['name']} derived NO endpoint — its requirement would read as 'needs "
            "nothing', which is the one answer that cannot be checked")


def test_ac7_the_six_record_families_are_PROJECTED_from_the_write_registry(caps):
    from larkdocio.base import write_ops

    names = rows.names(caps["surfaces"][BASE_WRITE], rows.OPERATION)
    assert names == [descriptor.name for descriptor in write_ops.WRITE_OPS]
    assert len(names) == 6, names
    for op in rows.call_sites(caps["surfaces"][BASE_WRITE], rows.OPERATION):
        assert op["projected_from"] == "larkdocio.base.write_ops.WRITE_OPS"


def test_ac7_it_runs_on_the_WRITE_credential_pair(caps):
    from larkdocio.common.auth import WRITE_ENV

    creds = caps["surfaces"][BASE_WRITE]["credentials"]
    assert creds["app"] == "write"
    assert creds["env_primary"] == list(WRITE_ENV)


def test_ac7_the_safety_contracts_are_declared_NOT_REDEFINED(caps):
    surface = caps["surfaces"][BASE_WRITE]
    assert sorted(surface["safety_contracts"]) == sorted(
        ["STALE_BASE", "dry-run-mandatory", "plan-gated", APPLY_LOG_COMPLETE])
    catalog = caps["safety_contracts"]
    for contract in surface["safety_contracts"]:
        assert contract in catalog, contract
        assert BASE_WRITE in catalog[contract]["applies_to"], contract


def test_ac7_the_house_invariant_is_declared_by_reference_and_EARNED(caps):
    """LD-254's rule: a surface may declare the invariant only if its package carries the
    disposition boundary that makes it true. The Base engine does."""
    from larkdocio.base import disposition as base_disposition
    from larkdocio.base.apply import DECLARED_SAFETY_CONTRACT

    assert DECLARED_SAFETY_CONTRACT is APPLY_LOG_COMPLETE
    assert callable(base_disposition.classify_apply_exception)
    assert APPLY_LOG_COMPLETE in caps["surfaces"][BASE_WRITE]["safety_contracts"]


def test_ac7_STALE_BASE_states_the_CLIENT_SIDE_compare_and_swap_without_promising_atomicity(
        caps):
    contract = caps["safety_contracts"]["STALE_BASE"]
    summary = contract["summary"]
    assert contract["applies_to"] == [BASE_WRITE]
    lowered = summary.lower()
    for phrase in ("client-side", "table.revision", "per-table", "zero writes"):
        assert phrase in lowered, phrase
    # It must NOT read as an atomicity claim — the engine cannot deliver one.
    for forbidden in ("atomic", "all-or-nothing", "transaction"):
        assert forbidden not in lowered, forbidden


def test_ac7_the_surface_states_its_LIMITATIONS_where_the_registry_is_read(caps):
    """A surface row that lists six operations and nothing else says the write is complete.
    These are the facts a consumer plans differently around."""
    note = caps["surfaces"][BASE_WRITE]["credentials"]["note"].lower()
    for needle in ("if-match", "schema", "record"):
        assert needle in note, f"the base-write credentials note never mentions {needle!r}"


def test_ac7_the_RECORD_surface_still_claims_no_schema_op_of_its_OWN(caps):
    """The fence, kept and re-pointed. Schema authoring shipped — on its own surface, with its
    own contracts and its own ring. What must stay true here is that the RECORD engine did not
    quietly absorb it: an op list that grew a ``create_field`` would tell a consumer the record
    handshake can change a Base's shape, which it cannot."""
    surface = caps["surfaces"][BASE_WRITE]
    assert "lifecycle" not in surface, (
        "a lifecycle pair claims a create AND a destroy; a Base has no purge verb at all")
    assert "content_constraints" not in surface
    names = set(rows.names(surface, rows.OPERATION))
    for phantom in ("create_field", "update_field", "create_table", "delete_table",
                    "create_view", "copy_app", "create_app"):
        assert phantom not in names, phantom
    # And they really do live next door, so the fence is a boundary rather than an absence.
    schema_names = set(rows.names(caps["surfaces"]["base-schema-write"], rows.OPERATION))
    assert {"create_field", "create_table", "create_view", "copy_app"} <= schema_names


def test_ac7_the_base_package_docstring_no_longer_says_NOT_YET_ON_THE_FRONT_DOOR():
    """Stale since LD-251 published the read surfaces; false twice over now."""
    import larkdocio.base as base_pkg

    doc = base_pkg.__doc__
    assert "Not yet on the front door" not in doc
    assert "no surface is registered in ``capabilities()``" not in doc
    assert "capabilities()" in doc, (
        "the docstring should say what the registry now reports, not go silent about it")


# --------------------------------------------------------------------------- #
# AC7b — base-read declares its gate coverage too (O6′)                         #
# --------------------------------------------------------------------------- #

def test_ac7b_base_read_declares_gate_coverage_naming_the_LANDED_ARMS(caps):
    coverage = caps["surfaces"]["base-read"]["gate_coverage"]
    assert coverage is not None, "LD-252's ring landed — base-read's coverage is declarable now"
    assert coverage["marker"] == "live"
    assert coverage["command"] == "pytest -m live"
    modules = [member["module"] for member in coverage["members"]]
    assert sorted(modules) == sorted(BASE_READ_RING), modules


def test_ac7b_no_coverage_is_claimed_for_a_surface_WITHOUT_a_landed_live_arm(caps):
    """The exact call LD-251 got right, kept: the two remaining Base read surfaces have no
    live arm of their own, so neither claims one."""
    for surface_id in ("base-comments-read", "base-embedded-deep-read"):
        assert caps["surfaces"][surface_id].get("gate_coverage") is None, surface_id


def test_ac7b_base_write_declares_gate_coverage_naming_its_OWN_RING(caps):
    coverage = caps["surfaces"][BASE_WRITE]["gate_coverage"]
    assert coverage is not None
    assert coverage["marker"] == "live_write"
    # LD-539: the payload states the command a consumer can TYPE, and the bare
    # command has not run the ring since LD-537 armed the consent fence.
    assert coverage["command"] == "LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-NNN pytest -m live_write"
    modules = [member["module"] for member in coverage["members"]]
    assert sorted(modules) == sorted(BASE_WRITE_RING), modules
    assert "self-provision" in coverage["target_policy"]
    assert "LARKDOCIO_SCRATCH_BASE" in coverage["target_policy"], (
        "the policy must name the Base it never writes — the hand-authored specimens on it "
        "cannot be recreated by any API route")


@pytest.mark.parametrize("surface_id", ["base-read", BASE_WRITE])
def test_ac7b_every_named_gate_member_EXISTS_and_carries_the_marker_it_is_claimed_under(
        surface_id, caps):
    coverage = caps["surfaces"][surface_id]["gate_coverage"]
    for member in coverage["members"]:
        path = _REPO / member["module"]
        assert path.exists(), member["module"]
        declared = member.get("marker") or coverage["marker"]
        statement = f"pytestmark = pytest.mark.{declared}"
        assert any(line.startswith(statement)
                   for line in path.read_text(encoding="utf-8").splitlines()), (
            f"{member['module']} is claimed as a {declared} member and does not carry it")


def test_ac7b_every_base_write_safety_contract_is_PROVED_BY_SOME_RING_MEMBER(caps):
    """The direction that matters: a contract nothing proves live is a claim, not a
    guarantee."""
    surface = caps["surfaces"][BASE_WRITE]
    proved = {c for m in surface["gate_coverage"]["members"] for c in m["proves_contracts"]}
    unproved = sorted(set(surface["safety_contracts"]) - proved)
    assert not unproved, unproved


# --------------------------------------------------------------------------- #
# AC8 — the shipped guide gains a base-write recipe that EXECUTES               #
# --------------------------------------------------------------------------- #

BASE_WRITE_RECIPE_SLUG = "the-base-write-handshake"


def test_ac8_the_guide_carries_a_base_write_recipe(guide_text):
    assert "### Recipe: the Base write handshake" in guide_text
    assert BASE_WRITE_RECIPE_SLUG in guide_recipes.recipe_blocks(guide_text)


def test_ac8_the_base_write_recipe_has_NO_UNDEFINED_FREE_VARIABLES():
    problems = guide_recipes.static_problems(
        guide_recipes.recipe_source(BASE_WRITE_RECIPE_SLUG))
    assert problems == [], problems


def test_ac8_the_base_write_recipe_EXECUTES_against_an_injected_transport(monkeypatch,
                                                                         tmp_path):
    stage = guide_recipes.stage(monkeypatch, tmp_path)
    namespace = stage.run(BASE_WRITE_RECIPE_SLUG)
    guide_recipes.SPEC_BY_SLUG[BASE_WRITE_RECIPE_SLUG].check(namespace)


def test_ac8_the_recipe_states_the_NO_IF_MATCH_limitation_in_plain_language():
    preamble = guide_recipes.recipe_preamble(BASE_WRITE_RECIPE_SLUG)
    lowered = preamble.lower()
    assert "if-match" in lowered
    for phrase in ("client-side", "re-plan"):
        assert phrase in lowered, phrase


# --------------------------------------------------------------------------- #
# AC9 — the WHOLE front door, corrected in this change                          #
# --------------------------------------------------------------------------- #

def test_ac9_the_generated_permissions_documents_carry_the_base_write_row():
    from larkdocio.permissions import (
        consumer_permissions_markdown,
        dev_permissions_markdown,
    )

    dev = dev_permissions_markdown()
    consumer = consumer_permissions_markdown()
    assert f"`{BASE_WRITE}`" in dev
    assert f"`{BASE_WRITE}`" in consumer
    assert "`bitable:app`" in dev
    assert dev in (_REPO / "PERMISSIONS.md").read_text(encoding="utf-8")
    assert consumer in guide(full=True)


def test_ac9_no_endpoint_scope_row_is_left_unreachable_by_this_publication():
    """LD-255 exempted its write row *temporarily by construction*: the exemption was written
    to expire the moment this surface published. It has."""
    from larkdocio import permissions as perm

    assert ("/open-apis/bitable/v1/apps", "write") not in perm.unreached_table_rows()


def test_ac9_the_readme_row_names_the_WRITE_surfaces_and_calls_nothing_read_only():
    """LD-260's row said *records writable, schema read-only*; LD-266 retracted the second half
    and the assertion moved with it. What survives is the half that was always the point: the
    layout row must not describe this surface as read-only, and it must name the write."""
    readme = fd.readme_text()
    assert "src/larkdocio/base/" in fd.documented_layout_paths(readme)
    row = next(line for line in readme.splitlines()
               if line.strip().startswith("|") and "`src/larkdocio/base/`" in line)
    lowered = row.lower()
    assert "surface, **read-only**:" not in lowered, (
        "the layout row still calls the whole surface read-only — it writes now")
    assert "base-write" in lowered and "base-schema-write" in lowered
    for phrase in ("record", "schema"):
        assert phrase in lowered, phrase


def test_ac9_the_wheel_summary_names_every_surface_word_including_the_write():
    description = fd.pyproject()["project"]["description"]
    assert fd.description_surface_gaps(description) == []
    lowered = description.lower()
    assert "base" in lowered and "write" in lowered


def test_ac9_the_package_docstring_still_names_every_shipped_surface_package():
    import larkdocio

    assert fd.docstring_surface_packages(larkdocio.__doc__) == fd.surface_packages()


def test_ac9_the_rendered_group_help_names_the_base_write_surface():
    page = fd.group_help_page()
    missing, phantom = fd.surface_roll_diff(page)
    assert not missing and not phantom, (missing, phantom)
    assert BASE_WRITE in fd.help_surface_roll(page)


def test_ac9_the_help_page_still_says_the_command_line_IS_READ_ONLY():
    """This story publishes a library surface, not a CLI verb.

    TRANSFORMED by LD-440 on the same reasoning as
    ``test_base_front_door.py::test_ac4_the_help_page_still_says_the_command_line_IS_READ_ONLY``:
    the flag is not a GROUP option, which is what the block below checks; denying its
    existence anywhere on the page was the defect.
    """
    page = fd.group_help_page()
    # TRANSFORMED AGAIN by LD-492 — see test_base_front_door.py for the reasoning. The
    # blanket claim is gone because it became false; this story's own claim (the BASE
    # write is a library surface, not a CLI verb) is what is held, and it still holds.
    assert "roundtrip push --apply" in page
    assert "The STANDALONE Base surface is a LIBRARY call too" in " ".join(page.split())
    assert "--deep-read-bases" not in fd.group_option_block(page)


def test_ac9_base_md_records_the_write_gate_and_its_limits():
    for token in ("STALE_BASE", "If-Match", "base-write"):
        assert token in _BASE_MD, token


def test_ac9_no_consumer_text_claims_A_CAPABILITY_THE_RUNG_DID_NOT_SHIP():
    """The phantom-claim fence, over the shipped corpus rather than one file.

    **It shrinks as the ladder climbs, and only then.** ``"create a view"`` left this list in
    LD-264, when the view lifecycle actually shipped — a fence against claiming a capability is
    a defect the moment the capability is real, because it would then be forbidding the truth.
    Everything still listed is still absent from the library.
    """
    banned = ("upload an attachment", "resolve a link", "create a base comment")
    for name, text in consumer_text.shipped_docs().items():
        lowered = " ".join(text.lower().split())
        for phrase in banned:
            assert phrase not in lowered, (name, phrase)


def test_ac9_every_new_registry_string_is_DIALECT_FREE(caps):
    surface = caps["surfaces"][BASE_WRITE]
    blobs = [surface["title"], surface["credentials"]["note"],
             caps["safety_contracts"]["STALE_BASE"]["summary"],
             surface["gate_coverage"]["target_policy"]]
    blobs += [member["summary"] for member in surface["gate_coverage"]["members"]]
    blobs += [member["summary"]
              for member in caps["surfaces"]["base-read"]["gate_coverage"]["members"]]
    for blob in blobs:
        assert dialect_hits(blob) == [], (blob[:80], dialect_hits(blob))


def test_ac9_the_person_by_id_limitation_is_CONSUMER_TEXT_in_plain_language(guide_text):
    """A person cell is written **by id**; the two honest id sources are named and the
    other-user name→id gap is described plainly, with no invented resolution path."""
    preamble = guide_recipes.recipe_preamble(BASE_WRITE_RECIPE_SLUG)
    lowered = preamble.lower()
    assert "open_id" in lowered
    for source in ("read_base", "batch_get_user_names"):
        assert source in preamble, source
    assert "resolve_user" in preamble, (
        "the forward lookup must be named as the narrow thing it is, not omitted")


def test_ac9_the_decision_reference_guard_is_NOT_WEAKENED_and_no_new_text_trips_it():
    """The trap the round-trip-editing spec hit. The guard is not weakened, its exclusion list is not extended, and
    the strings this story ships pass it."""
    source = (Path(consumer_text.__file__)).read_text(encoding="utf-8")
    assert "_DECISION_REF" in source
    for name, text in consumer_text.shipped_docs().items():
        assert dialect_hits(text) == [], (name, dialect_hits(text)[:3])
