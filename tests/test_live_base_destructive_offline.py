"""The always-on offline half of ``test_live_base_destructive``.

The live arm runs only with credentials and a network. What it *claims* — that it writes only
Bases it created itself, that its preview really is read **before** the delete, that the mirror's
disappearance is asserted in the **other** table, that an out-of-band removal makes the next plan
refuse, that it uploads no media, that it skips loudly — is exactly the class of claim a
credential-less run verifies by not running. So it is verified **here**, statically, on every
plain ``pytest``.

This is the arm whose verbs can destroy data, so the companion carries three things no earlier
Base arm needed:

* **THE PREVIEW IS READ BEFORE THE DELETE, IN THE SOURCE ORDER.** A preview asserted *after* an
  apply would prove nothing about what a caller could have known beforehand, so the companion
  pins that every destructive leg reads ``loss_preview`` above its ``schema_apply``;
* **THE MIRROR IS ASSERTED IN THE OTHER TABLE.** The whole reason this rung exists is that the
  blast radius leaves the table you named, so a live arm that only checked the named table would
  be testing the wrong claim;
* **NO DELETE RUNS WITHOUT CONSENT MINTED FROM ITS OWN PLAN.** Every ``schema_apply`` in the arm
  that carries a destructive entry passes ``consent=consent_to_destroy(plan)``; a leg that found
  another way in would mean the fence has a hole the offline suite cannot see.

It imports nothing from the live arm and runs no gate.
"""
import ast
import re
from pathlib import Path

import pytest

from larkdocio.base import loss_preview as lp
from larkdocio.base import schema_ops
from larkdocio.base import schema_ops_destructive as destructive

_REPO = Path(__file__).resolve().parent.parent
_ARM = Path(__file__).resolve().parent / "test_live_base_destructive.py"

#: Every configured target this repository knows about. The arm may name the Base one only
#: inside its own fence — see :func:`test_the_arm_NAMES_A_CONFIGURED_TARGET_ONLY_TO_REFUSE_IT`.
_FORBIDDEN_TARGET_ENV = (
    "LARKDOCIO_CANARY_DOC",
    "LARKDOCIO_BLOCKZOO_DOC",
    "LARKDOCIO_SCRATCH_SHEET",
)


@pytest.fixture(scope="module")
def arm_source():
    return _ARM.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def arm_tree(arm_source):
    return ast.parse(arm_source)


def arm_code(source):
    """The arm with its docstrings removed — prose may discuss what code may not do."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


def _legs(source):
    """``{test name: its source}`` for every test in the arm."""
    out = {}
    for chunk in source.split("\ndef test_")[1:]:
        out["test_" + chunk.split("(")[0]] = chunk
    return out


def test_the_arm_exists_and_is_marked_live_write(arm_source):
    assert _ARM.exists()
    assert "pytestmark = pytest.mark.live_write" in arm_source


def test_the_destructive_family_is_WHOLLY_MUTATING_and_the_read_registry_still_is_not():
    from larkdocio.base import ops as base_ops

    assert schema_ops.all_mutate() is True
    assert base_ops.read_only() is True
    assert all(d.mutates is True for d in destructive.SCHEMA_OP_FAMILY.ops)
    assert schema_ops.destructive_ops() == set(destructive.DESTRUCTIVE_OPS)


def test_the_arm_NAMES_A_CONFIGURED_TARGET_ONLY_TO_REFUSE_IT(arm_source):
    """Two mentions of the Scratch Base variable are allowed and no more, and each one is
    pinned to the site that earns it: the runtime fence that proves this arm is not writing the
    read fixture, and the LOUD skip that tells a reader which variable the Lookup leg needs set
    to have a template to copy. Every other configured target stays absent outright.
    """
    code = arm_code(arm_source)
    for variable in _FORBIDDEN_TARGET_ENV:
        assert variable not in code, variable
    mentions = [line for line in code.splitlines() if "LARKDOCIO_SCRATCH_BASE" in line]
    assert len(mentions) == 2, (
        "the Scratch Base variable may appear exactly twice — the fence, and the loud skip of "
        f"the copy-template fixture: {mentions}")
    assert sum("pytest.skip" in line for line in mentions) == 1
    fence = code.split("def test_this_arm_NEVER_TOUCHES")[1].split("\ndef ")[0]
    assert "LARKDOCIO_SCRATCH_BASE" in fence
    assert "app_token not in configured" in fence


def test_the_TEMPLATE_is_a_COPY_SOURCE_and_NEVER_reaches_a_mutating_verb(arm_tree):
    """The distinction the Lookup leg rests on. A ``Lookup`` cannot be authored through the
    field API, so the only route to a live one is copying a Base that has one — and a copy
    creates a NEW app. Structurally that means ``template_app_token`` may be ``copy_app``'s
    source and may be compared against, and may never be handed to a verb that mutates: this is
    the arm whose verbs delete tables, so a template reaching one would be the worst outcome in
    the suite.
    """
    # `delete_base` joined the set at LD-466 and it is the sharpest member: the template is a
    # COPY of the read fixture holding the only hand-authored Lookup / Email / Stage columns in
    # existence, so a template token reaching the whole-object delete would destroy evidence no
    # API route can recreate. Nothing about the fence changed — the set grew with the surface.
    mutating = {"create_table", "batch_create_tables", "create_field", "delete_field",
                "delete", "delete_app", "delete_base", "update_field", "batch_update",
                "batch_create", "schema_apply", "schema_dry_run", "delete_table",
                "batch_delete_tables", "_make_tables"}
    offenders = []
    for node in ast.walk(arm_tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else (
            node.func.id if isinstance(node.func, ast.Name) else "")
        if name not in mutating:
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(arg, ast.Name) and arg.id == "template_app_token":
                offenders.append(name)
    assert not offenders, (
        f"the template is handed to a mutating verb {offenders} — it is a copy SOURCE and a "
        "read source, and nothing else")

    copies = [node for node in ast.walk(arm_tree)
              if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute) and node.func.attr == "copy_app"]
    assert len(copies) == 1, "the arm makes exactly one copy"
    assert isinstance(copies[0].args[0], ast.Name)
    assert copies[0].args[0].id == "template_app_token"

    # TRANSFORMED, NOT DELETED. This used to forbid EVERY folder/parent keyword, on the reading
    # that "a copy that named a folder would land inside somebody's tree" while a keyless copy
    # went to the app's own default and touched nothing configured. The reason — never write
    # into a tree somebody else owns — stands. The conclusion does not: the app's own default is
    # a space with no human interface, so a keyless copy was the *unrecoverable* option, not the
    # polite one. The one folder this arm may name is the account holder's OWN designated
    # disposables folder, read through require_disposables_folder(); a `parent_node` /
    # `parent_type` is still forbidden outright.
    keywords = {kw.arg for node in ast.walk(arm_tree) if isinstance(node, ast.Call)
                for kw in node.keywords if kw.arg}
    assert not any("parent" in kw for kw in keywords), keywords
    body = ast.unparse(arm_tree)
    for call in ast.walk(arm_tree):
        if not isinstance(call, ast.Call):
            continue
        for kw in call.keywords:
            if kw.arg == "folder_token":
                assert isinstance(kw.value, ast.Name), (
                    "the destination must be a name bound from require_disposables_folder(), "
                    "never a literal")
    assert "require_disposables_folder()" in body, (
        "the destination is the configured, human-visible disposables folder — and nothing "
        "else may supply one")


def test_the_COPY_is_LEDGERED_BEFORE_anything_else_can_fail(arm_source):
    """An unrecorded disposable is a lost one, so the record sits between the call that mints
    the token and the first thing that could raise — and the delete sits in a ``finally``."""
    minted = arm_source.index("token = schema.copy_app(")
    recorded = arm_source.index("ledger.record_create(token, title)")
    guarded = arm_source.index("    try:", minted)
    assert minted < recorded < guarded
    assert "adopt_from_ledger(ledger)" in arm_source and "record_delete" in arm_source


def test_THE_LOOKUP_LEG_asserts_the_PREDICTION_and_then_the_OBSERVED_LOSS(arm_source):
    """The leg's whole claim is that a preview is worth reading, so both halves are pinned: the
    Lookup is named BEFORE the delete (the ordering guard above covers every leg), the column is
    asserted to SURVIVE afterwards still naming the dead table, and the values it held are
    asserted GONE. A leg that only checked the preview would be testing a data structure.
    """
    leg = _legs(arm_source)["test_A_TABLE_DELETE_BLANKS_AN_INBOUND_LOOKUP_and_THE_PREVIEW_NAMES_IT_FIRST"]
    assert 'loss["inbound_lookups"]' in leg
    assert "assert lookup.field_id in survivors" in leg, (
        "the column SURVIVES the delete — a Lookup that vanished would be a different loss")
    assert "computed.target_table(survivors[lookup.field_id]) == doomed_id" in leg, (
        "and still names the table that is now gone")
    assert "assert after == []" in leg, "the observed blanking, not merely the predicted one"
    assert leg.index("before") < leg.index("schema_apply(plan"), (
        "the BEFORE reading must be taken before the delete or there is nothing to compare")
    assert "settle(lambda: read.get_app(token))" in leg, (
        "copy is the one asynchronous Base op — the arm consumes the shipped settle contract")


def test_EVERY_write_target_comes_from_the_harness(arm_tree):
    body = ast.unparse(arm_tree)
    assert body.count("base_write_harness.disposable_base()") >= 5
    tokens = [node.value for node in ast.walk(arm_tree)
              if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    suspicious = [text for text in tokens if re.fullmatch(r"[A-Za-z0-9]{27}", text or "")]
    assert not suspicious, f"an app-token-shaped literal in a live arm: {suspicious}"


def test_THE_PREVIEW_IS_READ_BEFORE_THE_DELETE_IN_EVERY_DESTRUCTIVE_LEG(arm_source):
    """A preview read after the apply would say nothing about what a caller could have known."""
    for name, leg in _legs(arm_source).items():
        if "loss_preview" not in leg:
            continue
        assert leg.index("loss_preview") < leg.index("schema_apply(plan"), (
            f"{name} reads the loss preview AFTER applying — the preview's whole point is that "
            "it comes first")


def test_NO_DESTRUCTIVE_APPLY_RUNS_WITHOUT_CONSENT_MINTED_FROM_ITS_OWN_PLAN(arm_source):
    code = arm_code(arm_source)
    for call in re.findall(r"schema_apply\((.{0,200}?)\)\n", code, flags=re.S):
        if "destructive" in call or "consent" in call:
            assert "consent_to_destroy(plan)" in call, call
    assert code.count("consent_to_destroy(plan)") >= 4, (
        "every destructive leg mints its own consent; a shared or reused one would not be "
        "consent to THIS plan")


def test_THE_MIRRORS_DISAPPEARANCE_IS_ASSERTED_IN_THE_OTHER_TABLE(arm_source):
    leg = _legs(arm_source)["test_THE_TWO_TABLE_DUPLEX_DELETE_takes_the_MIRROR_IN_THE_OTHER_TABLE"]
    assert "ref_id" in leg
    assert 'mirror_id not in _fields(read, app_token, ref_id)' in leg, (
        "the mirror must be asserted gone from the SECOND table — checking the named table "
        "would be testing the claim this rung does not need proving")
    assert 'tables == [main_id, ref_id]' in leg, (
        "and the preview must have named both tables before the delete")


def test_THE_INBOUND_LINK_LEG_asserts_the_DANGLE_and_the_SILENCE(arm_source):
    leg = _legs(arm_source)["test_A_TABLE_DELETE_PREVIEWS_AN_INBOUND_LINK_IN_A_THIRD_TABLE_and_DANGLES_IT"]
    assert "third_id" in leg and "target_id" in leg
    assert 'getattr(prop, "table_id", None) == target_id' in leg
    assert 'not getattr(prop, "table_name", None)' in leg, "the detector, live"
    assert "search_records" in leg, (
        "and the silence: the table holding the dangling link still reads with no error")


def test_THE_OUT_OF_BAND_LEG_asserts_a_REFUSAL_rather_than_a_partial_apply(arm_source):
    leg = _legs(arm_source)["test_AN_OUT_OF_BAND_REMOVAL_makes_the_NEXT_PLAN_REFUSE_rather_than_half_apply"]
    assert "Refusal.LOSS_NOT_ENUMERABLE" in leg
    assert "DestructiveConsentRequired" in leg
    assert "schema_apply" not in leg, (
        "a refusal leg that then applied anything would be proving the opposite")


def test_the_arm_UPLOADS_NO_MEDIA(arm_source):
    code = arm_code(arm_source).lower()
    for forbidden in ("upload", "bitable_file", "bitable_image", "media"):
        assert forbidden not in code, (
            f"{forbidden!r}: an uploaded media token has no purge verb at all, so a live arm "
            "that minted one would leave residue nothing can remove")


def test_the_arm_DELETES_ONLY_WITHIN_ITS_OWN_DISPOSABLES_and_never_a_BASE(arm_source):
    """**TRANSFORMED by LD-466, and the reason is kept.**

    It used to assert the arm never deleted a Base at all, because *"deleting a Base is the
    harness's own teardown, never this arm's business"*. That reason was true while the library
    shipped **no** Base delete — the only route was the harness's own drive-file primitive, which
    is test scaffolding and not a shipped behaviour, so an arm calling it would have been proving
    the harness rather than the library.

    The library now ships ``delete_base``, so the whole-object delete IS this arm's business: it
    is the surface's one destructive verb that is not plan-gated, and an arm that would not
    exercise it would leave the newest destructive capability with no live proof. What survives
    unchanged is the fence the old assertion actually protected: the arm still never reaches the
    **harness's** raw drive primitive, and it still deletes only tokens it created itself (the
    template fence below, and the LARKDOCIO_SCRATCH_BASE fence above).
    """
    code = arm_code(arm_source)
    assert "drive" not in code.lower(), (
        "the whole-object delete is reached through the SHIPPED verb, never through a raw "
        "drive-file call in the arm — that primitive is the harness's and proves nothing about "
        "the library")
    assert "delete_app" not in code, "the shipped verb is delete_base; delete_app is nobody's"
    assert "delete_base" in code, (
        "the arm must exercise the whole-object delete — it is the one destructive verb on this "
        "surface that no plan gate covers, so a live proof is the only proof it has")


def test_the_skip_is_LOUD_and_the_WRITE_pair_is_the_one_resolved(arm_source):
    assert "base_write_harness.missing_reason()" in arm_source
    assert "pytest.skip(reason)" in arm_source
    assert "from_write_credentials" in arm_source
    assert "from_read_credentials" in arm_source, (
        "the read client is the verification seam — the read pair reads, the write pair writes")


def test_the_TEARDOWN_is_the_harnesss_own_sweep(arm_source):
    leg = _legs(arm_source)["test_the_teardown_LEDGER_is_swept_and_every_survivor_is_NAMED"]
    assert "close_out()" in leg and "orphans()" in leg


def test_the_ORACLE_AGREEMENT_is_asserted_rather_than_imported(arm_source):
    """``src/larkdocio`` cannot import from ``tests/``, so the two definitions of "gone" are
    held equal by a live-arm assertion. The companion pins that the assertion exists."""
    leg = _legs(arm_source)["test_THE_OBJECT_GONE_ORACLE_is_the_HARNESSS_OWN_and_not_a_second_opinion"]
    assert "OBJECT_GONE_CODES" in leg
    assert "DELETED_CODES" in leg and "TABLE_DELETED_CODES" in leg


def test_the_shipped_INVARIANT_the_arm_exercises_is_the_ONE_the_library_authors():
    """The arm proves a behaviour; this pins that the behaviour has exactly one authoring."""
    import inspect

    source = inspect.getsource(lp)
    assert source.count("LOSS_MUST_BE_ENUMERABLE = (") == 1
    assert source.count("TRASH_NOT_PURGE = (") == 1


def test_the_gentleness_the_packs_sustained_is_the_clients_own():
    from larkdocio.base.schema_client import (
        BASE_SCHEMA_RATE_WINDOW_SECONDS,
        DEFAULT_MAX_SCHEMA_WRITES_PER_WINDOW,
    )

    spacing = BASE_SCHEMA_RATE_WINDOW_SECONDS / DEFAULT_MAX_SCHEMA_WRITES_PER_WINDOW
    assert spacing >= 1.2
