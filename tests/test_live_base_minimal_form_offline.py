"""The always-on offline half of ``test_live_base_minimal_form`` (LD-317).

The live arm runs only with credentials and a network, so everything it *claims* about its own
posture is exactly the class of claim a credential-less run verifies by not running. It is
verified **here**, statically, on every plain ``pytest``:

* **disposables only** — every write target comes from ``base_write_harness``, no app-token
  literal appears anywhere, and the arm names **no** configured target: this sweep needs no
  read fixture, so — unlike its view sibling — it has no fence to write and nothing to excuse.
  That matters more here than almost anywhere: the arm's verb is *create a column of every kind
  the registry knows*, twenty-four of them, and ``LARKDOCIO_SCRATCH_BASE`` holds the only
  hand-authored ``Lookup`` / ``Email`` / ``Stage`` columns in existence;
* **the sweep is EXHAUSTIVE over the registry, not a hand-picked subset** — the defect it
  answers was a row nobody had looked at, so an arm that probed the suspects would have
  reproduced the defect's own shape one rung up;
* **both outcomes are a pass, and neither is silence** — the arm asserts that every row got an
  answer and that a refusing row also got a working-shape follow-up, never that a particular
  code came back. A probe that asserts only on success reports silence as a pass;
* **an answer that is not about the body is RETRIED before it is believed** — the first run of
  this sweep saw ``9499`` twice, on kinds that answer ``code:0`` on the retry. A transport
  hiccup written into a shipped registry flag is the same class of defect as the one being
  fixed;
* **the working-shape follow-up is built by the SHIPPED ``build_property``**, so what the
  capture proves is *"the body this library builds is accepted"* rather than *"some
  hand-written body is"*;
* **the WRITE pair and never the read one**, a **loud** skip, and the harness's own limiter;
* **no destructive verb of its own** — nothing here deletes a table, a field or a record; the
  disposable's own teardown is the whole cleanup.

**And the half no other companion has to check: the SHIPPED REGISTRY AGREES WITH THE CAPTURE.**
``FieldPropertyShape.required`` is now derived from this arm's capture, so this file also pins
that the derivation is real — that every row's control resolves inside the committed capture,
and that no code path fills a missing ``property`` in on the caller's behalf.

It imports nothing from the live arm and runs no gate.
"""
import ast
import json
import re
from pathlib import Path

import pytest

from larkdocio.base import field_authoring as fa

_ARM = Path(__file__).resolve().parent / "test_live_base_minimal_form.py"
_CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "base-study" / "captures"

#: Every configured target this repository knows about. The arm may name **none** of them.
_FORBIDDEN_TARGET_ENV = (
    "LARKDOCIO_CANARY_DOC",
    "LARKDOCIO_BLOCKZOO_DOC",
    "LARKDOCIO_SCRATCH_SHEET",
    "LARKDOCIO_SCRATCH_BASE",
)


@pytest.fixture(scope="module")
def arm_source():
    return _ARM.read_text(encoding="utf-8")


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


def test_the_arm_exists_and_is_marked_live_write(arm_source):
    assert _ARM.exists()
    assert "pytestmark = pytest.mark.live_write" in arm_source


def test_the_arm_NAMES_NO_CONFIGURED_TARGET_ANYWHERE(arm_source):
    code = arm_code(arm_source)
    for variable in _FORBIDDEN_TARGET_ENV:
        assert variable not in code, variable
    assert not re.search(r"[\"'](?:bascn|Cs|Q8|[A-Za-z0-9]{20,})[A-Za-z0-9]{6,}[\"']", code), (
        "an app-token-shaped literal in the arm would be a write target the harness did not "
        "mint")


def test_every_write_target_comes_from_the_HARNESS(arm_source):
    code = arm_code(arm_source)
    assert "base_write_harness.disposable_base(" in code
    assert "is_disposable_title(title)" in code


def test_the_arm_resolves_the_WRITE_pair_and_never_the_read_one(arm_source):
    code = arm_code(arm_source)
    assert "BaseSchemaClient.from_write_credentials()" in code
    assert "from_read_credentials" not in code


def test_the_arm_SKIPS_LOUDLY_rather_than_passing_without_credentials(arm_source):
    code = arm_code(arm_source)
    assert "base_write_harness.missing_reason()" in code
    assert "pytest.skip(reason)" in code


def test_the_sweep_is_EXHAUSTIVE_over_the_registry_not_a_hand_picked_subset(arm_source):
    """The defect was a row nobody looked at. A probe of the two named suspects would have
    reproduced that shape one rung up."""
    code = arm_code(arm_source)
    assert "sorted(FIELD_PROPERTY_SHAPES.items())" in code
    assert "set(observed) == set(FIELD_PROPERTY_SHAPES)" in code


def test_BOTH_OUTCOMES_are_a_pass_and_a_missing_answer_is_NOT(arm_source):
    code = arm_code(arm_source)
    assert "_BODY_VERDICTS" in code
    assert "'with_property' in entry" in code or '"with_property" in entry' in code
    assert not re.search(r"assert .*code.*== 1254001", code), (
        "the arm must not assert a particular refusal; it records what came back")


def test_a_NON_BODY_ANSWER_is_retried_before_it_is_believed(arm_source):
    code = arm_code(arm_source)
    assert "first_attempt_was" in code
    assert "def _attempt" in code and "def _post" in code


def test_the_working_shape_follow_up_is_built_by_the_SHIPPED_build_property(arm_source):
    code = arm_code(arm_source)
    assert "build_property(ui_type, **options)" in code


def test_the_arm_carries_NO_DESTRUCTIVE_VERB_of_its_own(arm_source):
    code = arm_code(arm_source)
    for verb in ("delete_field", "delete_table", "delete_record", "delete_view",
                 "batch_delete"):
        assert verb not in code, verb


def test_the_arm_WRITES_ITS_OWN_CAPTURE_under_the_captures_directory(arm_source):
    code = arm_code(arm_source)
    assert "ld317-01-minimal-form-sweep.json" in code
    assert "_verdict" in code and "_probe" in code
    # LD-620: the write goes through the sink, which redirects it out of the working tree
    # and says so out loud. What is pinned is that the arm still WRITES its capture — the
    # spelling moved, the property did not.
    assert "capture_sink.write_capture(CAPTURE," in code


# --------------------------------------------------------------------------- #
# The half no other companion needs: the SHIPPED registry agrees with the       #
# capture this arm writes.                                                      #
# --------------------------------------------------------------------------- #

def test_the_shipped_required_flag_is_DERIVED_FROM_THIS_ARMS_CAPTURE():
    sweep = json.loads((_CAPTURES / "ld317-01-minimal-form-sweep.json").read_text(encoding="utf-8"))
    observed = sweep["observations"]
    assert set(observed) == set(fa.FIELD_PROPERTY_SHAPES)
    for ui_type, shape in fa.FIELD_PROPERTY_SHAPES.items():
        measured = observed[ui_type]["minimal_form"]["code"]
        assert shape.minimal_form.code == measured, ui_type
        assert shape.required is (measured != 0), ui_type


def test_NO_CODE_PATH_fills_a_missing_property_in_on_the_callers_behalf():
    """The anti-goal, pinned. A required kind called with nothing raises; it never returns a
    property object the caller did not ask for."""
    for ui_type in fa.REQUIRED_PROPERTY_KINDS:
        with pytest.raises(fa.FieldAuthoringRefusal):
            fa.build_property(ui_type)
