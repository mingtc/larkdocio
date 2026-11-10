"""LD-312 — the shared by-name walk (``base/_typed.py``), and the constraint it must never break.

LD-311 pinned what the *readers* answer through each door; this file pins the **primitive** they
now all walk through, and the one rule the audit made binding on the move:

> *"same keys, one walk"* — promote ``_step`` / ``_nested`` to a shared primitive, have the
> readers walk **by name** through it, and **leave each module's key list exactly where it is.**

So there are two halves below. The first is the walk itself, driven over **real captured
payloads through the pinned SDK's own deserializer** — the LD-281 failure shape is a chain of
*typed objects*, and a walk that required a mapping at any step is exactly what shipped a
refusal once (``base/loss_preview.py::_property_of``'s docstring is the post-mortem). The second
is structural: the shared module holds **no key list**, every adopter passes **its own** names at
**its own** call site, and the walk is defined in exactly one place.

``base/table.py::_property_dict`` is deliberately **not** an adopter — it round-trips the
property through the SDK's serializer to hand back the wire shape untouched, a different
technique for a different contract — and the guards below are written so that they say nothing
about it.
"""
import ast
import inspect
import json
from pathlib import Path

import pytest

from lark_oapi.api.bitable.v1 import AppTableField

from larkdocio.base import _typed
from larkdocio.base import table as base_table

from base_captures import CAPTURES, capture, unmarshal


# --------------------------------------------------------------------------- #
# Specimens — committed captures only.                                         #
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def lookup_field():
    """The raw ``type: 19`` Lookup field dict — the one Lookup this repository has.

    Its ``property`` is the only specimen whose provenance lives **nested**
    (``filter_info.target_table``), which is what makes it the walk's real test case.
    """
    payload = json.loads(
        (CAPTURES / "p1-q0-03-per-table.json").read_text(encoding="utf-8"))
    for table in payload["per_table"]:
        for field in table["fields"]["response"]["data"]["items"]:
            if field["type"] == 19:
                return field
    raise AssertionError("the Lookup specimen has vanished from the captures")


@pytest.fixture(scope="module")
def link_field():
    """A one-way link field whose target table is alive — a top-level two-key property."""
    return capture("p0-2-01-interconnection-field-create.json")[
        "response"]["data"]["SingleLink_multiple_false"]["field"]


def typed(payload):
    """The field as the read client hands it back: ``property`` is an SDK **object**."""
    field = unmarshal(payload, AppTableField)
    assert not isinstance(field.property, dict), (
        "the typed door must really be typed, or every assertion here compares one door "
        "with itself")
    return field


# =========================================================================== #
# The walk — by name, whatever the node is                                     #
# =========================================================================== #

def test_the_walk_crosses_a_chain_of_TYPED_OBJECTS_which_is_the_LD_281_FAILURE_SHAPE(
        lookup_field):
    """**B7.** Two nested levels, neither of them a mapping, and the answer comes out.

    This is the shape that bounced LD-281: on the live typed door ``property`` is an
    ``AppTableFieldProperty`` and ``property.filter_info`` is an
    ``AppTableFieldPropertyLookupFilter`` — *objects*. A walk that asked for a ``Mapping`` at
    either level stopped at the first one and answered ``None``, so a Lookup whose target table
    was right there read as one whose provenance had not arrived. The offline suite could not
    see it, because a fixture built from a raw capture is a dict all the way down.
    """
    field = typed(lookup_field)
    prop = field.property

    from collections.abc import Mapping
    assert not isinstance(prop, Mapping)
    assert not isinstance(prop.filter_info, Mapping), (
        "the nested level must be a typed object too — that is the level LD-281 stopped at")

    assert _typed._nested(prop, ("filter_info", "target_table")) == "tblvHhs6KA9QYNCo"
    assert _typed._step(prop, "filter_info") is prop.filter_info, (
        "one step off an object is that object's own attribute, not a conversion of it")


def test_the_SAME_walk_crosses_MAPPINGS_by_name_and_answers_IDENTICALLY(lookup_field):
    """The bridged and dict doors are mappings; one walk serves all three, with one answer."""
    path = ("filter_info", "target_table")
    answers = {
        "typed": _typed._nested(typed(lookup_field).property, path),
        "bridged": _typed._nested(base_table.field_spec(typed(lookup_field)).property, path),
        "dict": _typed._nested(base_table.field_spec(lookup_field).property, path),
    }
    assert set(answers.values()) == {"tblvHhs6KA9QYNCo"}, answers


def test_the_walk_crosses_a_MIXED_chain_mapping_then_object(lookup_field):
    """A mapping holding a real typed object — the bridge's own half-and-half shape.

    Nothing in the walk records which door it started at, so it may not require the whole chain
    to be of one kind. The node here is a mapping whose value is the SDK's own nested object.
    """
    field = typed(lookup_field)
    mixed = {"filter_info": field.property.filter_info}

    assert _typed._nested(mixed, ("filter_info", "target_table")) == "tblvHhs6KA9QYNCo"


def test_an_ABSENT_step_answers_None_and_a_SCALAR_or_SEQUENCE_is_never_an_error(lookup_field):
    """An absent nested key is a normal shape. Nothing here raises — not on a string, not on a
    list, not on ``None`` — because a reader asking what a property says must be able to be
    told *"it does not say"*."""
    field = typed(lookup_field)

    assert _typed._step(field.property, "no_such_key") is None
    assert _typed._step("a string", "target_table") is None
    assert _typed._step([1, 2, 3], "target_table") is None
    assert _typed._step(None, "target_table") is None
    assert _typed._nested(None, ("filter_info", "target_table")) is None
    assert _typed._nested(field.property, ("no_such_key", "deeper")) is None
    assert _typed._nested(field.property, ()) is field.property, (
        "an empty path is no walk at all — the node itself")


# =========================================================================== #
# The one-level copy — the caller's names, and only the caller's names          #
# =========================================================================== #

def test_by_name_copies_EXACTLY_the_names_IT_IS_GIVEN_absent_ones_as_None(lookup_field):
    """The names, in order, and nothing else; an absent name materialises as ``None``.

    Re-materialising the absent key is what makes an undeclared key on a typed object read the
    same as a key the wire sent as ``null`` — the equivalence ``referential._property_of``'s
    docstring rests on.
    """
    prop = typed(lookup_field).property

    copied = _typed._by_name(prop, ("filter_info", "no_such_key"))

    assert list(copied) == ["filter_info", "no_such_key"]
    assert copied["filter_info"] is prop.filter_info
    assert copied["no_such_key"] is None
    assert _typed._by_name(prop, ()) == {}, "no names asked for, no keys copied"


def test_by_name_reads_an_OBJECT_and_a_MAPPING_to_the_same_answer(link_field):
    """The two-key property, off the typed object and off the wire dict — one answer."""
    keys = ("table_id", "table_name")
    off_object = _typed._by_name(typed(link_field).property, keys)
    off_mapping = _typed._by_name(base_table.field_spec(link_field).property, keys)

    assert off_object == off_mapping
    assert off_object == {"table_id": "tblauNkOg3QoDL99",
                          "table_name": "p0zoo-Ref-033103"}


# =========================================================================== #
# The binding constraint, made structural                                      #
# =========================================================================== #

_BASE = Path(_typed.__file__).resolve().parent

#: Every field name any adopter copies. The shared module may name **none** of them.
_ADOPTER_KEYS = ("table_id", "table_name", "back_field_id", "back_field_name", "multiple",
                 "filter_info", "formula_expression", "formatter", "options", "id", "color")

#: Each adopter, and the key list it copies — **unchanged** by LD-312, and still local to it.
#: A row is added here in the same commit that makes that reader an adopter.
_KEY_LISTS = {
    "computed.py": [("filter_info", "formula_expression", "formatter")],
    "referential.py": [("table_id", "table_name")],
    # Two call sites, one adopter: the property copy, and the OPTION copy one level inside it
    # (LD-462 — a select option is `{id, name, color}` and the typed door nests it as an object,
    # so the shrink preview reads each option by name too). Both literal, both local.
    "loss_preview.py": [("table_id", "table_name", "back_field_id", "back_field_name",
                         "multiple", "filter_info", "options"),
                        ("id", "name", "color")],
    "hierarchy.py": [("table_id",)],
}


def _tree(name):
    return ast.parse((_BASE / name).read_text(encoding="utf-8"))


def _by_name_calls(tree):
    """Every ``_by_name(node, (…))`` call in a module, as its literal tuple of names."""
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_by_name"):
            continue
        keys = node.args[1]
        assert isinstance(keys, (ast.Tuple, ast.List)), (
            "an adopter's key list must be a literal at the call site — not a name, not a "
            "union, not something the shared module could be holding")
        found.append(tuple(ast.literal_eval(element) for element in keys.elts))
    return found


def test_the_SHARED_MODULE_holds_no_key_list_of_its_own():
    """**The binding constraint.** No default key set, no union, nowhere to hoist one to.

    A shared walk that carried names would widen every adopter to the union of them all the
    first time one reader gained a key — which is a question about what this library *reports*,
    and the audit routes it to a spec, not to a refactor.
    """
    signature = inspect.signature(_typed._by_name)
    assert signature.parameters["keys"].default is inspect.Parameter.empty, (
        "the names come from the caller; a default here IS the widening")

    tree = _tree("_typed.py")
    docstrings = {ast.get_docstring(node) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))}
    literals = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
                and node.value not in docstrings}
    assert not literals & set(_ADOPTER_KEYS), (
        f"the shared walk names a reader's field: {sorted(literals & set(_ADOPTER_KEYS))}")


@pytest.mark.parametrize("module", sorted(_KEY_LISTS))
def test_each_adopter_passes_its_OWN_key_list_at_its_OWN_call_site(module):
    """**Same keys, one walk.** Each list is a literal, in its own module, unchanged."""
    assert _by_name_calls(_tree(module)) == _KEY_LISTS[module], (
        f"{module}'s key list moved, widened or narrowed")


def test_the_walk_the_PROVENANCE_READER_used_to_own_is_now_IMPORTED_not_copied():
    """The reader the walk was lifted out of keeps no private copy: they are imported names."""
    tree = _tree("computed.py")
    defined = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert not defined & {"_step", "_nested", "_by_name"}, defined

    imported = {alias.name for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module == "larkdocio.base._typed"
                for alias in node.names}
    assert imported == {"_by_name", "_nested"}, imported


def test_the_WALK_IS_DEFINED_IN_EXACTLY_ONE_MODULE():
    """**B4.** One primitive; no module keeps a private copy of the step.

    Both halves matter: the three names are defined only in ``_typed.py``, and nothing in the
    package still open-codes the copy as ``{key: getattr(prop, key, None) for key in (…)}`` —
    the exact shape that stood in four places before this move. The second half is what keeps a
    fifth copy from being written next year by someone who never reads this file.
    """
    definitions, open_coded = [], []
    for path in sorted(_BASE.parent.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.FunctionDef)
                    and node.name in ("_step", "_nested", "_by_name")):
                definitions.append(f"{path.name}::{node.name}")
            if not isinstance(node, ast.DictComp):
                continue
            key, value = node.key, node.value
            if (isinstance(key, ast.Name) and isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name) and value.func.id == "getattr"
                    and any(isinstance(generator.target, ast.Name)
                            and generator.target.id == key.id
                            for generator in node.generators)):
                open_coded.append(f"{path.parent.name}/{path.name}:{node.lineno}")

    assert sorted(definitions) == ["_typed.py::_by_name", "_typed.py::_nested",
                                   "_typed.py::_step"], definitions
    assert not open_coded, f"a private copy of the by-name walk survives: {open_coded}"
