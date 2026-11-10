"""THE BASE FRONT DOOR — the close-out that makes every consumer-reaching surface true.

Five stories built the Base read surface; this is the moment the **front door** describes it
everywhere a consumer meets it, and the moment the register in ``/BASE.md`` is checked for
**completeness** rather than merely for shape.

What each block here holds, and why it is a guard rather than a habit:

* **the registry** (``capabilities()``) reports the three Base surfaces read-only, each
  surface's scope list being the **union of its operations' own derived rows** — never a
  second assertion beside them;
* **the shipped guide** carries a Base section and a Base recipe that **executes** in the
  extract-and-run harness (a compile-only gate is blind to an undefined free variable);
* **the door proper** — ``README.md`` (the wheel ``METADATA`` body), the ``Summary``, the
  package docstring and the rendered ``larkdocio --help`` surface roll — names the surface,
  in both directions, against the code;
* **the wording calibrations that carry a product decision**: the roles family is a
  **feature gate**, not a scope denial (sending a consumer to the Lark console would be the
  wrong place), and the public-share fence is a statement about **this library** rather than
  an impossibility claim about Lark;
* **every honest gap is a TYPED row**, and nothing reads ``uncaptured`` where the surface was
  in fact captured.

The register's own completeness lives beside the rest of the matrix guard, in
``tests/test_base_md_matrix.py``.
"""
import re
from pathlib import Path

import pytest

import consumer_text
import front_door as fd
import guide_recipes
from consumer_text import dialect_hits
import capability_rows as rows
from larkdocio import capabilities, guide

from guard_kit import REPO_ROOT

_REPO = REPO_ROOT
_BASE_MD = (_REPO / "BASE.md").read_text(encoding="utf-8")

#: The three surface ids this story publishes.
BASE_SURFACES = ("base-read", "base-embedded-deep-read", "base-comments-read")


@pytest.fixture(scope="module")
def caps():
    return capabilities(full=True)


@pytest.fixture(scope="module")
def guide_text():
    return guide(full=True)


# --------------------------------------------------------------------------- #
# AC1 — capabilities() reports the Base surface honestly                        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("surface_id", BASE_SURFACES)
def test_ac1_the_registry_reports_the_base_surface_READ_ONLY(surface_id, caps):
    surface = caps["surfaces"][surface_id]
    assert surface["mode"] == "read", surface_id
    assert surface["domain"] == "base", surface_id
    # A read surface cannot bring a file into existence, so it declares no lifecycle.
    assert "lifecycle" not in surface, surface_id
    assert surface["levels"], f"{surface_id} declares no level model"


def test_ac1_the_base_read_scopes_are_the_UNION_OF_ITS_OPERATIONS_ROWS(caps):
    """The unification, asserted rather than assumed: the surface's ``scopes`` is exactly what
    its own operations require. A hand-written surface list is what drifts."""
    surface = caps["surfaces"]["base-read"]
    from_ops = set()
    for op in rows.call_sites(surface):
        from_ops |= rows.scope_strings(caps, op["permissions"])
    assert set(surface["credentials"]["scopes"]) == from_ops
    assert "bitable:app:readonly" in from_ops, (
        "the one scope without which no Base can be read at all is missing")


def test_ac1_every_base_operation_carries_a_DERIVED_permission_block(caps):
    for surface_id in BASE_SURFACES:
        for op in rows.call_sites(caps["surfaces"][surface_id], rows.OPERATION):
            block = op["permissions"]
            assert block["basis"] == "derived", (surface_id, op["name"])
            assert block["endpoints"], (
                f"{surface_id}.{op['name']} derived NO endpoint — its requirement would read "
                "as 'needs nothing', which is the one answer that cannot be checked")


def test_ac1_the_embedded_bridge_is_OPT_IN_and_composes_the_two_reads_it_runs_inside(caps):
    surface = caps["surfaces"]["base-embedded-deep-read"]
    assert surface["opt_in"] is True
    assert "deep_read_bases" in surface["gated_by"]
    assert surface["composes"] == ["docx-read", "base-read"]
    # It fires inside a document read, so the document scope is genuinely part of it.
    scopes = set(surface["credentials"]["scopes"])
    assert {"docx:document:readonly", "bitable:app:readonly"} <= scopes, sorted(scopes)


def test_ac1_the_deep_read_flag_has_a_row_and_is_OFF_by_default(caps):
    flag = caps["flags"]["deep_read_bases"]
    assert flag["default"] is False
    # LD-340: the decision was AMENDED — the Base deep read now HAS a command-line route, so
    # the descriptor's machine-readable half moved with it (was mode="config", cli named the
    # Parser argument). The in-code Parser(base_client=…) path still exists and the summary
    # names both; the mode/cli now describe the shipped switch a consumer can actually pass.
    assert flag["mode"] == "cli", (
        "the Base deep read now ships a real CLI flag; saying 'config' would hide it")
    assert flag["cli"] == "--deep-read-bases", flag["cli"]


def test_ac1_the_base_read_surface_STATES_ITS_LIMITATIONS(caps):
    """A surface row that lists operations and nothing else says the read is complete. These
    are the three facts a consumer plans differently around, and they are stated where the
    registry is read rather than only in a repository document."""
    summary = caps["surfaces"]["base-read"]["levels"]["summary"].lower()
    for needle in ("stage", "view", "name only"):
        assert needle in summary, f"the base-read level model never mentions {needle!r}"


def test_ac1_base_comments_read_is_the_SHIPPED_COMMENTS_CLIENT_not_a_second_one(caps):
    """The honest shape of LD-249's finding: a Base's comments are the drive comment family,
    so the surface is the shipped comments entry point with a third accepted file type — and
    the row has to say the write half is refused by the server, or a consumer plans a
    round trip that cannot exist."""
    surface = caps["surfaces"]["base-comments-read"]
    assert rows.names(surface, rows.OPERATION) == ["comments"]
    note = surface["credentials"]["note"]
    assert "bitable" in note
    assert "write" in note.lower()


# --------------------------------------------------------------------------- #
# AC2 — the shipped guide gains a Base section, and a recipe that EXECUTES      #
# --------------------------------------------------------------------------- #

BASE_RECIPE_SLUG = "read-a-base-to-markdown"


def test_ac2_the_guide_carries_a_base_recipe(guide_text):
    assert "### Recipe: read a Base to Markdown" in guide_text
    assert BASE_RECIPE_SLUG in guide_recipes.recipe_blocks(guide_text)


def test_ac2_the_base_recipe_has_NO_UNDEFINED_FREE_VARIABLES():
    """The shipped standard, and the reason the harness exists at all: a recipe can compile
    cleanly and ``NameError`` on its first line."""
    problems = guide_recipes.static_problems(guide_recipes.recipe_source(BASE_RECIPE_SLUG))
    assert problems == [], problems


def test_ac2_the_base_recipe_EXECUTES_against_an_injected_transport(monkeypatch, tmp_path):
    stage = guide_recipes.stage(monkeypatch, tmp_path)
    namespace = stage.run(BASE_RECIPE_SLUG)
    guide_recipes.SPEC_BY_SLUG[BASE_RECIPE_SLUG].check(namespace)


def test_ac2_the_guide_names_the_base_entry_points_a_consumer_calls(guide_text):
    for name in ("read_base", "read_base_markdown"):
        assert f"`{name}`" in guide_text, name


# --------------------------------------------------------------------------- #
# AC3 — scopes are authored in larkdocio.permissions and nowhere else           #
# --------------------------------------------------------------------------- #

def test_ac3_the_base_scope_string_is_KNOWN_TO_THE_REGISTRY():
    from larkdocio import permissions as perm

    known = {scope.scope for row in perm.ENDPOINT_SCOPES for scope in row[2]}
    assert "bitable:app:readonly" in known


def test_ac3_the_generated_permissions_documents_carry_the_base_rows():
    from larkdocio.permissions import (
        consumer_permissions_markdown,
        dev_permissions_markdown,
    )

    dev = dev_permissions_markdown()
    consumer = consumer_permissions_markdown()
    for surface_id in BASE_SURFACES:
        assert f"`{surface_id}`" in dev, f"{surface_id} has no row in the generated matrix"
        assert f"`{surface_id}`" in consumer, f"{surface_id} has no row in the guide's table"
    assert "`bitable:app:readonly`" in dev
    # …and the projections are what the two documents actually carry (byte-identity is
    # tests/test_permissions_docs.py's own contract; this is the membership half).
    assert dev in (_REPO / "PERMISSIONS.md").read_text(encoding="utf-8")
    assert consumer in guide(full=True)


# --------------------------------------------------------------------------- #
# AC4 — README / Summary / package docstring / --help                            #
# --------------------------------------------------------------------------- #

def test_ac4_the_readme_layout_row_no_longer_says_the_surface_is_INVISIBLE():
    readme = fd.readme_text()
    assert "src/larkdocio/base/" in fd.documented_layout_paths(readme)
    row = next(
        line for line in readme.splitlines()
        if line.strip().startswith("|") and "`src/larkdocio/base/`" in line
    )
    assert "reports no surface in `capabilities()`" not in row, (
        "the layout row still claims the surface is absent from the registry — it is not")
    assert "capabilities()" in row, (
        "the row should say what the registry now reports, not go silent about it")


def test_ac4_the_wheel_summary_names_the_base_surface():
    description = fd.pyproject()["project"]["description"]
    assert fd.description_surface_gaps(description) == []
    assert "base" in description.lower()


def test_ac4_the_package_docstring_names_every_shipped_surface_package():
    import larkdocio

    assert "base" in fd.surface_packages()
    assert fd.docstring_surface_packages(larkdocio.__doc__) == fd.surface_packages()


def test_ac4_the_rendered_group_help_names_the_three_base_surfaces():
    page = fd.group_help_page()
    missing, phantom = fd.surface_roll_diff(page)
    assert not missing and not phantom, (missing, phantom)
    for surface_id in BASE_SURFACES:
        assert surface_id in fd.help_surface_roll(page), surface_id


def test_ac4_the_help_page_still_says_the_command_line_IS_READ_ONLY():
    """The group page's read-only claim is about WRITING, and it survives LD-340: the Base
    deep read now ships a command-line route (`download --deep-read-bases`), but that is a
    READ, so 'NEVER WRITES' still holds.

    **TRANSFORMED by LD-440, not deleted.** The original reason is preserved exactly — the
    flag lives on `download` / `folder`, not on the group, so the group must not advertise it
    as a group-level option. Only the *mechanism* is superseded: the old check banned the
    string from the whole page, which made the page deny that the flag exists at all
    ("neither has a subcommand or a flag") — a false claim of absence. The ban now applies to
    the page's own `Options:` block, where the claim would actually be made.
    """
    page = fd.group_help_page()
    # TRANSFORMED AGAIN by LD-492: the group page no longer claims the command line
    # NEVER WRITES, because one verb now does. This story's claim is narrower and
    # unchanged — no BASE write is reachable from the command line — so that is what is
    # asserted, and the one writing verb is named so a reader can tell the two apart.
    assert "roundtrip push --apply" in page, (
        "the group page does not name the one command that writes")
    assert "The STANDALONE Base surface is a LIBRARY call too" in " ".join(page.split()), (
        "the group page no longer says the Base surface is a library call — a reader "
        "meeting a writing verb needs to be told it does not reach a Base")
    assert "--deep-read-bases" not in fd.group_option_block(page), (
        "the Base deep-read flag is a `download` / `folder` option, not a group option")
    assert "--deep-read-bases" in page, (
        "the group page must not deny a flag that ships — LD-440 finding 4")


# --------------------------------------------------------------------------- #
# AC5 — the roles family is a FEATURE GATE, not a scope denial                   #
# --------------------------------------------------------------------------- #

def _rows_mentioning(text, needle):
    return [line for line in text.splitlines()
            if line.strip().startswith("|") and needle in line]


def test_ac5_base_md_records_roles_as_a_feature_gate_the_BASE_OWNER_switches_on():
    rows = _rows_mentioning(_BASE_MD, "1254301")
    assert rows, "BASE.md never mentions the roles refusal code"
    joined = "\n".join(rows) + "\n" + _BASE_MD
    assert "is_advanced" in joined
    assert "1254302" in joined, (
        "the doubly-confirmed half is missing: the API also refuses to TURN IT ON")
    assert "feature gate" in joined.lower()


def test_ac5_no_shipped_or_matrix_text_calls_the_roles_refusal_a_SCOPE_DENIAL():
    """Calling it a scope denial would send a consumer to the Lark console, which cannot fix
    it: advanced permissions are switched on by the Base's owner, in the product. So a passage
    that names the refusal may only use the words *scope denial* to DENY that it is one."""
    for label, text in (("BASE.md", _BASE_MD), ("guide()", guide(full=True))):
        for line in text.splitlines():
            if "1254301" not in line:
                continue
            lowered = line.lower()
            if "scope denial" not in lowered and "scope denied" not in lowered:
                continue
            assert "not a scope denial" in lowered or "rather than a scope denial" in lowered, (
                f"{label} calls the roles feature gate a scope denial: {line.strip()[:200]}")


def test_ac5_the_guide_tells_a_consumer_where_the_switch_ACTUALLY_IS():
    text = guide(full=True).lower()
    assert "advanced permissions" in text
    assert "owner" in text


# --------------------------------------------------------------------------- #
# AC6 — the public-share policy row, worded as a statement about THIS library    #
# --------------------------------------------------------------------------- #

_IMPOSSIBILITY_CLAIMS = (
    "impossible", "永久", "can never", "cannot ever", "permanently forbidden",
    "will never be possible",
)


def test_ac6_base_md_carries_the_forms_shared_policy_row():
    rows = _rows_mentioning(_BASE_MD, "forms.shared")
    assert rows, "BASE.md has no forms.shared row"
    row = rows[0]
    assert "refused-by-policy" in row
    assert "does not control" in row and "shareability" in row


def test_ac6_the_share_fence_makes_NO_IMPOSSIBILITY_CLAIM_about_lark():
    """The maintainer's ruling was *for now*. A claim that the capability is impossible would be a
    claim about Lark that the API itself contradicts — the share PATCH exists."""
    for label, text in (("BASE.md forms.shared", "\n".join(_rows_mentioning(_BASE_MD, "forms.shared"))),
                        ("BASE.md share rows", "\n".join(_rows_mentioning(_BASE_MD, "shareability")))):
        lowered = text.lower()
        for claim in _IMPOSSIBILITY_CLAIMS:
            assert claim not in lowered, f"{label} claims {claim!r}"


def test_ac6_the_two_read_only_share_surfaces_are_TYPED_NOT_IN_SCOPE_rows():
    for endpoint in ("permissions/{app}/public", "members"):
        assert endpoint in _BASE_MD, f"BASE.md never records the {endpoint} surface"
    rows = _rows_mentioning(_BASE_MD, "permissions/{app}/public")
    assert rows and "refused-by-policy" in rows[0], rows


def test_ac6_the_surface_exposes_NO_PATH_to_a_share_write():
    """The fence is code truth, not only prose: no shipped Base op reaches a permissions or
    a members endpoint at all."""
    from larkdocio.base import ops

    for descriptor in ops.OPS:
        uri = descriptor.request_cls.builder().build().uri
        assert "permission" not in uri and "members" not in uri, descriptor.name
        assert descriptor.mutates is False, descriptor.name


# --------------------------------------------------------------------------- #
# AC7 — every honest gap is a TYPED capability gap, not silence                  #
# --------------------------------------------------------------------------- #

#: ``gap -> the token BASE.md's row for it must carry`` — the sweep, as a checklist the
#: document is held against. A gap whose row is deleted reddens here.
_TYPED_GAPS = {
    "dashboards": "1254050",
    "workflows": "800074800",
    "roles": "1254301",
    "forms.shared": "refused-by-policy",
    "permissions/{app}/public": "refused-by-policy",
    # LD-272 RETRACTED this deferral too, the ladder's second planned retraction: the media
    # leg SHIPS and its round trip is hash-verified, so the typed token the row must carry is
    # the shipped one. The gap stays in this map for the same reason link resolution's does —
    # the row still has to be typed, it is simply typed the other way now.
    "attachment media": "supported",
    # LD-269 RETRACTED the deferral: link resolution SHIPS, opt-in and off by default, so the
    # typed token the row must now carry is the shipped one. The gap stays in this map — the
    # row still has to be typed, it is simply typed the other way.
    "link resolution": "supported",
    "grouping": "refused-by-server",
    "comments.write": "refused-by-server",
}


@pytest.mark.parametrize("gap, token", sorted(_TYPED_GAPS.items()))
def test_ac7_each_named_gap_has_a_typed_row_carrying_its_evidence(gap, token):
    rows = _rows_mentioning(_BASE_MD, gap)
    assert rows, f"BASE.md has no row for the {gap!r} gap"
    assert any(token in row for row in rows), (
        f"the {gap!r} row does not carry {token!r} — a gap with no evidence is silence with a "
        "table around it")


def test_ac7_stage_is_OPAQUE_and_button_is_WILL_NOT_SUPPORT():
    stage = _rows_mentioning(_BASE_MD, "`24` / `Stage`")
    assert stage and "opaque" in stage[0] and "uncaptured" not in stage[0]
    button = [line for line in _BASE_MD.splitlines()
              if line.strip().startswith("| Button |")]
    assert button and "will-not-support" in button[0]


@pytest.mark.parametrize("ui_name", ["Lookup", "Email", "Flow"])
def test_ac7_no_field_row_reads_UNCAPTURED_for_lookup_email_or_stage(ui_name):
    rows = [line for line in _BASE_MD.splitlines()
            if line.strip().startswith(f"| {ui_name} |")]
    assert rows, f"the {ui_name} field row is gone"
    assert "uncaptured" not in rows[0], (
        f"{ui_name} is not uncaptured — it was captured, and what was captured is the finding")


# --------------------------------------------------------------------------- #
# AC9 — dialect-free at birth                                                   #
# --------------------------------------------------------------------------- #

def test_ac9_the_new_registry_strings_are_dialect_free(caps):
    offenders = {}
    for surface_id in BASE_SURFACES:
        surface = caps["surfaces"][surface_id]
        text = "\n".join([
            surface["title"], surface["credentials"].get("note") or "",
            surface["levels"]["summary"],
        ])
        if dialect_hits(text):
            offenders[surface_id] = dialect_hits(text)[:8]
    flag = caps["flags"]["deep_read_bases"]
    if dialect_hits(flag["summary"]):
        offenders["deep_read_bases"] = dialect_hits(flag["summary"])[:8]
    assert not offenders, offenders


def test_ac9_the_guides_base_section_is_dialect_free(guide_text):
    start = guide_text.find("### Recipe: read a Base to Markdown")
    assert start != -1
    section = guide_text[start:guide_text.find("\n### ", start + 10)]
    assert dialect_hits(section) == [], dialect_hits(section)[:8]


def test_ac9_the_decision_reference_guard_is_NOT_WEAKENED():
    """The trap a previous tranche hit: the fix for a decision reference in shipped text is
    plain language, never an addition to the guard's exclusion list."""
    assert dialect_hits("The ruling in D4 stands.") != []
    assert "_DECISION_REF" in (Path(consumer_text.__file__).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# AC10 — the stale url.py comment is retired                                    #
# --------------------------------------------------------------------------- #

def test_ac10_the_url_module_no_longer_claims_there_is_no_base_surface():
    source = (_REPO / "src" / "larkdocio" / "common" / "url.py").read_text(encoding="utf-8")
    # LD-279: the literal this used to forbid — "no Base surface of any kind" — was one
    # PHRASING of the claim, and the module went on carrying a different phrasing of the same
    # claim with this guard green. The check is the claim family now; the detector and the
    # corpus-wide sweep live in tests/test_base_surface_claim_is_gone.py.
    from test_base_surface_claim_is_gone import claim_hits

    assert claim_hits(source) == [], (
        f"the module still denies a surface that ships: {claim_hits(source)}")
    assert re.search(r"base.*read", source, re.IGNORECASE), (
        "the replacement should say what `base` now routes to, not merely delete the lie")
    # …and the discriminator itself is unchanged: this is a comment retirement, not a change.
    from larkdocio.common.url import URL_TYPE_SURFACES

    assert URL_TYPE_SURFACES["base"] == "base"
