"""LD-289 — the refusals are excellent; four of them broke the pattern the others set.

The refusal prose was named one of the top three best things in the 2026-08-05 Base
dogfooding session: every refusal names a **next move**. Which is exactly why the places
that name none cost more than they look — a consumer who has learned the pattern reads a
refusal that names no route as *"there is no route"*.

Nothing here changes **whether** a refusal fires. Every test in this file is about what a
refusal SAYS, plus the two additive spellings (``FieldSpec(field_type=)`` / ``.field_type``)
that stop a naming seam being discovered by ``TypeError``.
"""
import dataclasses
import inspect
from pathlib import Path

import pytest

from larkdocio.base import write_cells
from larkdocio.base.cells import FieldSpec
from larkdocio.base.write_vocabulary import NON_WRITABLE_PAIRS, NON_WRITABLE_REASONS
from larkdocio.write.model.requests import DeleteRequest, InsertRequest

GUIDE = (Path(__file__).resolve().parents[1]
         / "src" / "larkdocio" / "GUIDE.md").read_text(encoding="utf-8")

STAGE = (24, "Stage")


def field(type_, ui_type, name="F"):
    return FieldSpec(field_name=name, type=type_, ui_type=ui_type)


def encode(value, type_, ui_type):
    return write_cells.encode_cell(value, field(type_, ui_type))


def _body():
    """The module source with its docstring stripped — prose may name a pair, code may not."""
    return inspect.getsource(write_cells).split('"""', 2)[-1]


# --------------------------------------------------------------------------- #
# AC1 — Stage's refusal names its escape hatch, like every sibling            #
# --------------------------------------------------------------------------- #

def test_ac1_stage_refusal_names_the_product_route_the_siblings_all_name():
    """Its two computed neighbours hand the caller a next move. Stage stopped at *why*."""
    reason = NON_WRITABLE_REASONS[STAGE].lower()
    assert "drag" in reason, reason
    assert "in the product" in reason, reason


def test_ac1_the_stage_escape_hatch_is_APPENDED_not_a_rewrite():
    """The evidence clause is why the pair is in the set at all; it stays, verbatim."""
    reason = NON_WRITABLE_REASONS[STAGE]
    assert "the table revision does not move" in reason
    assert "fully opaque" in reason
    assert reason.index("fully opaque") < reason.lower().index("drag")


def test_ac1_the_shape_matches_its_two_computed_neighbours():
    """The pattern being matched: a computed pair says why, then where to go instead."""
    assert "LINKED record" in NON_WRITABLE_REASONS[(19, "Lookup")]
    assert "the formula itself" in NON_WRITABLE_REASONS[(20, "Formula")]
    assert "in the product" in NON_WRITABLE_REASONS[STAGE]


def test_ac1_the_raised_refusal_carries_the_route_not_just_the_dict():
    with pytest.raises(write_cells.NonWritableFieldError) as caught:
        encode("Stage A", *STAGE)
    message = str(caught.value).lower()
    assert "drag" in message and "in the product" in message, message


# --------------------------------------------------------------------------- #
# AC2 — UnsupportedFieldTypeError says WHICH coordinate is wrong               #
# --------------------------------------------------------------------------- #

def test_ac2_a_wrong_field_type_coordinate_names_the_registered_one():
    """The consumer's case: ``(1021 / GroupChat)`` read as a missing capability, though
    GroupChat writes perfectly at 23. The library already knew."""
    with pytest.raises(write_cells.UnsupportedFieldTypeError) as caught:
        encode(["oc_x"], 1021, "GroupChat")
    message = str(caught.value)
    assert "'GroupChat' is registered at field_type 23, not 1021" in message, message


def test_ac2_the_nearest_pair_is_DERIVED_from_the_registry_not_hard_coded():
    """Every writable pair answers the same way under a bogus field_type — a hard-coded
    special case for the one pair the consumer hit would pass the test above and fail here."""
    for type_, ui_type in write_cells.WRITABLE_PAIRS:
        with pytest.raises(write_cells.UnsupportedFieldTypeError) as caught:
            encode("anything", type_ + 9000, ui_type)
        message = str(caught.value)
        assert f"{ui_type!r} is registered at field_type {type_}" in message, message
    assert "1021" not in _body()


def test_ac2_a_wrong_ui_type_coordinate_names_the_field_types_registered_spelling():
    with pytest.raises(write_cells.UnsupportedFieldTypeError) as caught:
        encode(["oc_x"], 23, "Groupchat")
    message = str(caught.value)
    assert "field_type 23 is registered as 'GroupChat'" in message, message


def test_ac2_a_non_writable_ui_type_under_a_wrong_field_type_says_where_it_lives():
    """Stage at 1024 is two facts, not one: the pair is wrong AND the right pair refuses."""
    with pytest.raises(write_cells.UnsupportedFieldTypeError) as caught:
        encode("Stage A", 1024, "Stage")
    message = str(caught.value)
    assert "'Stage' is registered at field_type 24" in message, message
    assert "not writable" in message, message


def test_ac2_a_pair_the_library_has_never_seen_INVENTS_no_coordinate():
    """The honest case stays honest: neither coordinate is registered, so nothing is offered."""
    with pytest.raises(write_cells.UnsupportedFieldTypeError) as caught:
        encode("anything", 4242, "SomethingNew")
    message = str(caught.value)
    assert "registers no write encoding for" in message, message
    assert "is registered at field_type" not in message, message
    assert "is registered as" not in message, message


def test_ac2_the_missing_field_name_refusal_is_untouched():
    with pytest.raises(write_cells.UnsupportedFieldTypeError) as caught:
        write_cells.encode_fields({"Nope": 1}, [field(1, "Text", name="Text")])
    assert "silently ignored by the server" in str(caught.value)


# --------------------------------------------------------------------------- #
# AC3 — reference= / target= stop being discovered by TypeError                #
# --------------------------------------------------------------------------- #

def test_ac3_insert_and_delete_docstrings_each_name_the_other_spelling():
    assert "target" in InsertRequest.__doc__ and "DeleteRequest" in InsertRequest.__doc__
    assert "reference" in DeleteRequest.__doc__ and "InsertRequest" in DeleteRequest.__doc__


def test_ac3_the_docx_recipe_names_the_keyword_difference_in_text():
    """A consumer must meet the difference in prose before they meet it in a traceback."""
    assert "the keyword differs by request type" in GUIDE
    marker = GUIDE.index("the keyword differs by request type")
    window = GUIDE[marker:marker + 600]
    for keyword in ("reference", "target", "anchor"):
        assert keyword in window, window


# --------------------------------------------------------------------------- #
# AC4 — the field_type spellings are reconciled and named once                 #
# --------------------------------------------------------------------------- #

def test_ac4_fieldspec_accepts_field_type_as_an_alias_for_type():
    spec = FieldSpec(field_name="Chat", field_type=23, ui_type="GroupChat")
    assert spec.type == 23 and spec.pair == (23, "GroupChat")


def test_ac4_fieldspec_exposes_field_type_as_a_readable_spelling():
    assert FieldSpec(field_name="N", type=2, ui_type="Number").field_type == 2


def test_ac4_the_alias_is_ADDITIVE_the_old_spelling_is_untouched():
    by_type = FieldSpec(field_name="N", type=2, ui_type="Number")
    by_alias = FieldSpec(field_name="N", field_type=2, ui_type="Number")
    positional = FieldSpec("N", 2, "Number")
    assert by_type == by_alias == positional
    assert [f.name for f in dataclasses.fields(FieldSpec)] == [
        "field_name", "type", "ui_type", "property", "field_id", "is_primary"]
    assert dataclasses.replace(by_alias, ui_type="Text").ui_type == "Text"
    assert FieldSpec.from_payload({"field_name": "N", "type": 2, "ui_type": "Number"}) == by_type


def test_ac4_naming_the_integer_twice_in_one_call_is_a_refusal_not_a_coin_toss():
    with pytest.raises(TypeError) as caught:
        FieldSpec(field_name="N", type=2, field_type=3, ui_type="Number")
    message = str(caught.value)
    assert "type" in message and "field_type" in message


def test_ac4_the_guide_names_the_spelling_seam_once():
    assert "the same integer wears three spellings" in GUIDE
    marker = GUIDE.index("the same integer wears three spellings")
    window = GUIDE[marker:marker + 700]
    assert "create_field(field_type=" in window, window
    assert "FieldSpec(type=" in window, window
    assert "ComputedColumn.field_type" in window, window


# --------------------------------------------------------------------------- #
# AC5 — no behavior change beyond the aliases                                  #
# --------------------------------------------------------------------------- #

def test_ac5_every_refusal_still_refuses_the_same_things():
    assert len(NON_WRITABLE_PAIRS) == 8
    for pair in NON_WRITABLE_PAIRS:
        with pytest.raises(write_cells.NonWritableFieldError):
            encode("anything", *pair)
    assert len(write_cells.WRITABLE_PAIRS) == 19
    for pair in write_cells.WRITABLE_PAIRS:
        assert write_cells.is_writable(pair)
        assert not write_cells.is_non_writable(pair)


def test_ac5_a_writable_pair_still_encodes_exactly_as_before():
    assert encode("hello", 1, "Text") == "hello"
    assert encode(True, 7, "Checkbox") is True
    assert encode(None, 1, "Text") is None
