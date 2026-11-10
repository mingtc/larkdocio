"""LD-288 — the FINDABILITY batch: seven shipped capabilities a consumer could not find,
or found and was misled by.

Nothing here is a behavior change (AC8): six of the seven are docstring / guide text, and the
seventh is one constructor that gives the docx read client the ``from_read_credentials()``
its sibling read clients already had. What the tests below guard is that the text a consumer
actually reads **agrees with the code it describes** — and, where a list could fall behind,
that the list is DERIVED rather than typed twice:

* **AC1** — ``FIELD_PROPERTY_SHAPES``' notes no longer contradict the call they document. The
  two nested traps (``Rating.symbol``, ``Location.input_type``) are voiced **at the call
  site**, and the key list in that voicing is generated from the shape's own ``keys`` tuple,
  so the two cannot disagree again.
* **AC2/AC3** — the write-handshake recipe names ``records_per_call`` and reads its apply log
  through the accessors ``ApplyLog`` actually carries.
* **AC4** — ``comments()``'s docstring names every ``FILE_TYPE_*`` the function branches on,
  proved against the constants themselves.
* **AC5** — the reverse (id → name) verb has a front door: a ``from_read_credentials()`` on
  its own client, a re-export beside its inverse in ``larkdocio.contacts``, and the route
  named in the recipe where an ``ou_`` id actually surfaces.
* **AC6** — the Base read recipe names the vendored-SDK object seam and the ``field_spec``
  bridge across it.
* **AC7** — the copy recipe says what a clone REWIRES, PRESERVES and DROPS, each labelled
  with how it is known.
"""
import dataclasses
import inspect

import pytest

from guard_kit import section
from larkdocio import guide
from larkdocio.base import field_authoring as fa
from larkdocio.base.plan import ApplyLog
from larkdocio.comments import read as comments_read
from larkdocio.comments.client import CommentsReadClient
from larkdocio.contacts.client import ContactsSearchClient
from larkdocio.errors import LarkConfigError
from larkdocio.read.client import Client as DocxReadClient

GUIDE = guide(full=True)
WRITE_RECIPE = section(GUIDE, "### Recipe: the Base write handshake")
BASE_READ_RECIPE = section(GUIDE, "### Recipe: read a Base to Markdown")
COPY_RECIPE = section(
    GUIDE, "### Recipe: create, rename and copy a Base (the structural handshake)")
COMMENTS_RECIPE = section(GUIDE, "### Recipe: read the comments on a document")


# --------------------------------------------------------------------------- #
# AC1 — the property-shape notes stop contradicting their own call shape.       #
# --------------------------------------------------------------------------- #

def test_ac1_NO_shape_note_tells_a_caller_to_nest_a_key_the_call_takes_flat():
    """The defect, pinned: a note saying "symbol NESTS under property.rating.symbol" beside
    a flat ``keys`` tuple earns the reader an ``UncapturedFieldPropertyError``. The wire shape
    is real; the instruction was for the wrong layer."""
    for ui_type, shape in fa.FIELD_PROPERTY_SHAPES.items():
        assert "nest" not in shape.note.lower(), (ui_type, shape.note)


def test_ac1_every_shape_voices_its_CALL_and_names_every_key_it_accepts():
    for ui_type, shape in fa.FIELD_PROPERTY_SHAPES.items():
        voiced = shape.call_shape
        assert voiced, ui_type
        for key in shape.keys:
            assert key in voiced, (ui_type, key, voiced)
        if shape.keys:
            assert "flat" in voiced.lower(), (ui_type, voiced)
        else:
            assert "no property" in voiced.lower(), (ui_type, voiced)


def test_ac1_the_call_shape_is_DERIVED_from_keys_so_the_two_cannot_disagree():
    """The derivation proof: move ``keys`` and the voicing moves with it."""
    shape = fa.FIELD_PROPERTY_SHAPES["Rating"]
    mutated = dataclasses.replace(shape, keys=shape.keys + ("zzz_probe",))
    assert "zzz_probe" in mutated.call_shape
    assert "zzz_probe" not in shape.call_shape


def test_ac1_the_two_nested_traps_are_voiced_AT_THE_CALL_SITE_with_their_wire_path():
    rating = fa.FIELD_PROPERTY_SHAPES["Rating"]
    assert rating.nests == (("symbol", "rating"),)
    assert "property.rating.symbol" in rating.call_shape
    location = fa.FIELD_PROPERTY_SHAPES["Location"]
    assert location.nests == (("input_type", "location"),)
    assert "property.location.input_type" in location.call_shape

    # ...and the call really is flat, which is what the voicing now says.
    assert fa.build_property("Rating", symbol="star").rating.symbol == "star"
    assert fa.build_property(
        "Location", input_type="not_limit").location.input_type == "not_limit"


#: A settable value per nested key, so the declared wire container can be checked against the
#: property ``build_property`` really builds rather than against a spelling rule.
_NEST_PROBE = {"symbol": "star", "input_type": "not_limit"}


def test_ac1_every_declared_wire_path_is_PROVED_against_the_property_really_built():
    """The claim ``property.rating.symbol`` is not taken on trust and not derived from the
    ui_type's spelling: the shape names its container, and this walks every declared pair
    through ``build_property`` to see the value arrive exactly where the sentence says."""
    seen = 0
    for ui_type, shape in fa.FIELD_PROPERTY_SHAPES.items():
        for key, container in shape.nests:
            assert key in shape.keys, (ui_type, key)
            probe = _NEST_PROBE[key]
            built = fa.build_property(ui_type, **{key: probe})
            assert getattr(getattr(built, container), key) == probe, (ui_type, key, container)
            assert f"property.{container}.{key}" in shape.call_shape, (ui_type, key)
            seen += 1
    assert seen == 2, f"the two known nested traps, got {seen}"


# --------------------------------------------------------------------------- #
# AC2 — records_per_call is reachable from a recipe.                            #
# --------------------------------------------------------------------------- #

def test_ac2_the_write_handshake_recipe_names_records_per_call():
    assert "records_per_call" in WRITE_RECIPE


def test_ac2_it_is_named_beside_the_free_call_audit_it_makes_readable():
    assert "api_call_count" in WRITE_RECIPE
    assert "call_index" in WRITE_RECIPE


def test_ac2_the_knob_the_recipe_names_is_the_one_dry_run_takes():
    from larkdocio.base.apply import dry_run

    assert "records_per_call" in inspect.signature(dry_run).parameters


# --------------------------------------------------------------------------- #
# AC3 — the apply-log examples use the accessors that exist.                    #
# --------------------------------------------------------------------------- #

def test_ac3_the_guide_no_longer_hand_rolls_an_accessor_it_ships():
    assert 'entry.outcome == "applied"' not in GUIDE


def test_ac3_the_recipe_reads_the_log_through_its_accessors():
    for accessor in ("log.applied", "log.stale", "log.dropped", "log.refusals"):
        assert accessor in WRITE_RECIPE, accessor


def test_ac3_every_accessor_the_recipe_names_exists_on_ApplyLog():
    for name in ("applied", "dropped", "stale", "refusals", "indeterminate",
                 "not_attempted", "halted", "of_table"):
        assert hasattr(ApplyLog, name), name


def test_ac3_one_entries_walk_survives_where_per_entry_detail_is_the_point():
    assert "for entry in log.entries" in WRITE_RECIPE


def test_ac3_the_rule_is_STATED_a_refusal_is_a_value_on_the_log_AND_that_apply_now_raises():
    """**Transformed, not deleted (LD-458 / CLAUDE.md § Supersession).**

    The original guard pinned the words *"never raises"*, and its REASON survives unchanged:
    the recipe itself must tell a caller **how a refusal reaches them**, rather than leaving
    it to be discovered from a run that wrote nothing and exited 0. What the maintainer ruling
    inverted is the CONCLUSION — `apply()` now raises `LarkApplyRefusedError` on a refused
    entry unless the caller passes `allow_partial=True`, and the outcomes are still values on
    the log either way. So the rule is still stated; this asserts the statement it became.
    """
    assert "LarkApplyRefusedError" in WRITE_RECIPE
    assert "allow_partial=True" in WRITE_RECIPE
    assert "Every refusal is a value on the log" in WRITE_RECIPE


# --------------------------------------------------------------------------- #
# AC4 — comments()'s docstring names bitable, derived from the constants.        #
# --------------------------------------------------------------------------- #

def _file_type_constants():
    return {name: value for name, value in vars(comments_read).items()
            if name.startswith("FILE_TYPE_") and isinstance(value, str)}


def test_ac4_the_docstring_names_EVERY_file_type_the_function_branches_on():
    """Derived, not hand-listed: the assertion iterates the constants, so a fourth file type
    reddens this test instead of shipping a docstring that omits it."""
    doc = comments_read.comments.__doc__
    constants = _file_type_constants()
    assert len(constants) >= 3, constants
    for name, value in constants.items():
        assert f'``"{value}"``' in doc, (name, value)


def test_ac4_the_bitable_clause_says_what_a_base_thread_carries():
    doc = comments_read.comments.__doc__
    clause = doc[doc.index("``file_type``"):]
    clause = clause[:clause.index("\n\n")]
    for word in ("record", "table", "view"):
        assert word in clause, (word, clause)


# --------------------------------------------------------------------------- #
# AC5 — id → name has a front door.                                             #
# --------------------------------------------------------------------------- #

def test_ac5_the_docx_read_client_gains_the_constructor_its_siblings_had():
    for cls in (DocxReadClient, ContactsSearchClient, CommentsReadClient):
        member = inspect.getattr_static(cls, "from_read_credentials")
        assert isinstance(member, classmethod), cls.__module__


def test_ac5_from_read_credentials_resolves_the_READ_pair(monkeypatch):
    monkeypatch.setenv("LARK_READ_APP_ID", "cli_read")
    monkeypatch.setenv("LARK_READ_APP_SECRET", "secret_read")
    monkeypatch.delenv("LARK_APP_ID", raising=False)
    monkeypatch.delenv("LARK_APP_SECRET", raising=False)
    client = DocxReadClient.from_read_credentials()
    assert isinstance(client, DocxReadClient)
    assert hasattr(client, "batch_get_user_names")


def test_ac5_it_NEVER_borrows_the_write_pair(monkeypatch):
    for var in ("LARK_READ_APP_ID", "LARK_READ_APP_SECRET", "LARK_APP_ID", "LARK_APP_SECRET"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LARK_WRITE_APP_ID", "cli_write")
    monkeypatch.setenv("LARK_WRITE_APP_SECRET", "secret_write")
    with pytest.raises(LarkConfigError) as excinfo:
        DocxReadClient.from_read_credentials()
    assert "read" in str(excinfo.value).lower()


def test_ac5_the_reverse_verb_is_re_exported_beside_its_inverse():
    import larkdocio.contacts as contacts

    assert "ReadClient" in contacts.__all__
    assert contacts.ReadClient is DocxReadClient
    assert hasattr(contacts.ReadClient, "batch_get_user_names")


def test_ac5_the_contacts_docstring_ROUTES_to_the_reverse_direction():
    import larkdocio.contacts as contacts

    assert "ReadClient" in contacts.__doc__
    assert "batch_get_user_names" in contacts.__doc__


def test_ac5_the_comments_recipe_names_the_route_where_the_ou_id_surfaces():
    assert "batch_get_user_names" in COMMENTS_RECIPE
    assert "from_read_credentials" in COMMENTS_RECIPE


# --------------------------------------------------------------------------- #
# AC6 — the SDK-object seam is named.                                           #
# --------------------------------------------------------------------------- #

def test_ac6_the_base_read_recipe_names_the_seam_and_the_bridge_across_it():
    for token in ("field_spec", "`.type`", "`.field_name`", "`.ui_type`"):
        assert token in BASE_READ_RECIPE, token
    assert "SDK" in BASE_READ_RECIPE


def test_ac6_it_warns_about_the_name_that_does_NOT_exist_on_those_objects():
    assert "field_type" in BASE_READ_RECIPE


def test_ac6_the_bridge_is_importable_and_public_exactly_where_the_recipe_says():
    import larkdocio.base as base
    from larkdocio.base.table import field_spec

    assert callable(field_spec)
    assert "field_spec" in base.__all__
    assert base.field_spec is field_spec


# --------------------------------------------------------------------------- #
# AC7 — copy semantics are written down.                                        #
# --------------------------------------------------------------------------- #

def test_ac7_the_copy_recipe_says_what_a_clone_REWIRES():
    assert "filter_info.target_table" in COPY_RECIPE
    assert "rewired" in COPY_RECIPE.lower()


def test_ac7_it_says_which_ids_are_PRESERVED_and_which_are_new():
    assert "field_id" in COPY_RECIPE
    assert "table_id" in COPY_RECIPE


def test_ac7_it_says_a_fresh_clone_reads_revision_ZERO():
    assert "revision_guard" in COPY_RECIPE
    assert "unavailable" in COPY_RECIPE


def test_ac7_it_says_comments_do_NOT_follow_the_copy():
    assert "comment" in COPY_RECIPE.lower()


def test_ac7_every_claim_is_LABELLED_with_how_it_is_known():
    assert "measured" in COPY_RECIPE.lower()
