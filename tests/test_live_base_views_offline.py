"""The always-on offline half of ``test_live_base_views`` (LD-264).

The live arm runs only with credentials and a network. What it *claims* — that it writes only a
Base it created itself, that it carries a **negative control** beside its positive result, that
its two raw calls exist because the typed client refuses those shapes rather than in spite of it,
that it resolves the WRITE pair, that it skips loudly — is exactly the class of claim a
credential-less run verifies by not running. So it is verified **here**, statically, on every
plain ``pytest``:

* **disposables only** — every write target comes from ``base_write_harness``, no app-token
  literal appears, and the file names no configured target except in the one place it must: the
  runtime fence that asserts the Base it writes is not the configured one;
* **THE NEGATIVE CONTROL EXISTS, AND IT IS ON THE SAME VIEW** — the arm patches
  ``property.group_info``, asserts ``code:0``, and asserts nothing persisted, then lands a
  filter on that same view. A control on a different Base would be a difference between Bases;
* **the read-back of the control is RAW** — the pinned SDK's view model carries no
  ``group_info`` field at all, so asking the typed model about it could not tell a swallow from
  a model gap (register row 12's class). The arm reads the raw body;
* **the raw probe lives in tests/** — nothing in ``src/larkdocio`` can build a ``group_info``
  body or a wrong-dialect filter, which is the dialect boundary working;
* **the 2-call probe moves ONE variable per call** and writes its verdict to a committed
  capture, which the shipped ``VOCABULARY_PROBE`` must agree with;
* **loud skips**, the harness's own sweep as teardown, and the gentleness the packs sustained.

It imports nothing from the live arm and runs no gate.
"""
import ast
import re
from pathlib import Path

import pytest

from larkdocio.common.citations import dev_repo_paths
from larkdocio.base import schema_ops
from larkdocio.base import view_filters
from larkdocio.base import schema_ops_views as views

_REPO = Path(__file__).resolve().parent.parent
_ARM = Path(__file__).resolve().parent / "test_live_base_views.py"

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


def test_the_arm_exists_and_is_marked_live_write(arm_source):
    assert _ARM.exists()
    assert "pytestmark = pytest.mark.live_write" in arm_source


def test_the_view_family_is_WHOLLY_MUTATING_and_the_read_registry_still_is_not():
    from larkdocio.base import ops as base_ops

    assert schema_ops.all_mutate() is True
    assert base_ops.read_only() is True
    assert all(d.mutates is True for d in views.SCHEMA_OP_FAMILY.ops)


def test_the_arm_NAMES_A_CONFIGURED_TARGET_ONLY_TO_REFUSE_IT(arm_source):
    code = arm_code(arm_source)
    for variable in _FORBIDDEN_TARGET_ENV:
        assert variable not in code, variable
    mentions = [line for line in code.splitlines() if "LARKDOCIO_SCRATCH_BASE" in line]
    assert len(mentions) == 1, (
        "the Scratch Base variable may appear exactly once — in the fence that proves this "
        f"arm is not writing it: {mentions}")
    fence = code.split("def test_this_arm_NEVER_TOUCHES")[1].split("\ndef ")[0]
    assert "LARKDOCIO_SCRATCH_BASE" in fence
    assert "app_token not in configured" in fence


def test_EVERY_write_target_comes_from_the_harness(arm_tree):
    body = ast.unparse(arm_tree)
    assert body.count("base_write_harness.disposable_base()") >= 3
    tokens = [node.value for node in ast.walk(arm_tree)
              if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    suspicious = [text for text in tokens if re.fullmatch(r"[A-Za-z0-9]{27}", text or "")]
    assert not suspicious, f"an app-token-shaped literal in a live arm: {suspicious}"


def test_THE_NEGATIVE_CONTROL_EXISTS_and_lands_on_THE_SAME_VIEW(arm_source):
    """The claim the whole story rests on. The swallow and the persist must be the same view on
    the same Base in the same test, or the control is a comparison between two situations."""
    control = arm_source.split("def test_THE_SWALLOW_CONTROL")[1].split("\ndef ")[0]
    assert '"group_info"' in control
    assert 'str(answer.get("code")) == "0"' in control, (
        "the control must ASSERT the swallow answered code:0 — that is the half that makes it "
        "a swallow rather than a refusal")
    assert "not (prop or {}).get(\"group_info\")" in control
    landed = control.index("set_view_filter")
    swallowed = control.index('"group_info"')
    assert swallowed < landed, "the control comes first, then the positive result beside it"
    assert control.count("disposable_base()") == 1, (
        "one Base, one view — a control on a second Base would prove nothing about the first")


def test_THE_CONTROLS_READ_BACK_IS_RAW_because_the_SDK_MODEL_CANNOT_SEE_group_info(arm_source):
    from lark_oapi.api.bitable.v1 import AppTableViewProperty

    assert not hasattr(AppTableViewProperty(), "group_info"), (
        "if the pinned SDK ever models group_info, the control may read it typed — until then "
        "a typed read could not tell a swallow from a model gap")
    control = arm_source.split("def test_THE_SWALLOW_CONTROL")[1].split("\ndef ")[0]
    assert 'probe.call("GET", path)' in control


def test_THE_RAW_PROBE_LIVES_IN_TESTS_and_reaches_ONLY_the_view_route(arm_source):
    """The dialect boundary is the feature: a probe that needed a hole cut in the shipped
    client would have been the defect. So the raw shapes live here, and nothing in the library
    can express them."""
    src = _REPO / "src" / "larkdocio"
    for path in src.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # A REQUEST KEY, precisely — not the word. The library discusses the swallow at
            # length in its own prose (that is the disclosure); what it may never do is put
            # `group_info` in a body it builds or name it as a keyword it accepts.
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    assert not (isinstance(key, ast.Constant)
                                and key.value == "group_info"), path.name
            if isinstance(node, ast.keyword):
                assert node.arg != "group_info", path.name
            if isinstance(node, ast.arg):
                assert node.arg != "group_info", path.name
    assert "class _RawProbe(CredentialedRawHttpClient)" in arm_source
    paths = re.findall(r'f"(/open-apis/[^"]*)"', arm_source)
    assert paths and all("/views/" in path for path in paths), paths


def test_THE_2_CALL_PROBE_MOVES_ONE_VARIABLE_PER_CALL(arm_source):
    probe = arm_source.split("def test_AC3_THE_2_CALL")[1].split("\ndef ")[0]
    assert '"field_id": field.field_id, "operator": "is_not"' in probe, (
        "call A holds the KEY at the working value and moves only the operator case")
    assert '"field_name": field.field_name, "operator": "isNotEmpty"' in probe, (
        "call B holds the OPERATOR at the working value and moves only the key")
    assert probe.count("probe.call(") == 0 or "def patch(" in probe
    # LD-620: routed through the capture sink — the probe still writes its capture, out of
    # the working tree instead of over the committed one.
    assert "capture_sink.write_capture(VOCABULARY_CAPTURE," in probe


def test_THE_SHIPPED_VERDICT_AND_THE_COMMITTED_CAPTURE_AGREE():
    """AC3's honesty clause, held offline: whatever the probe found, the shipped constant says
    that and nothing more. An `inconclusive` verdict is a pass; an overstated one is not."""
    capture = (_REPO / "tests" / "captures" / "base-study" / "captures" /
               "ld264-01-view-filter-vocabulary.json")
    shipped = view_filters.VOCABULARY_PROBE
    (cited,) = dev_repo_paths(shipped["capture"])
    assert cited.endswith("ld264-01-view-filter-vocabulary.json")
    if not capture.exists():
        assert shipped["verdict"] == "inconclusive", (
            "with no capture committed the shipped verdict may only be `inconclusive`")
        return
    import json

    assert json.loads(capture.read_text(encoding="utf-8"))["verdict"] == shipped["verdict"]


def test_the_arm_CALLS_NO_DESTRUCTIVE_VERB_beyond_its_own_views(arm_source):
    for verb in ("delete_app", "delete_table", "batch_delete", "drive.v1.files", "/forms/"):
        assert verb not in arm_source, verb
    assert "close_out()" in arm_source, "teardown is the harness's sweep"


def test_the_arm_resolves_the_WRITE_pair(arm_source):
    assert "BaseSchemaClient.from_write_credentials()" in arm_source
    assert "get_read_credentials" not in arm_source


def test_the_skip_is_LOUD_and_goes_through_the_harnesss_own_reason(arm_source):
    assert "base_write_harness.missing_reason()" in arm_source
    assert "pytest.skip(reason)" in arm_source


def test_the_raw_probe_is_GENTLE_at_the_pace_the_packs_sustained(arm_source):
    assert "time.sleep(1.2)" in arm_source, (
        "the raw probe bypasses the client's limiter, so it must pace itself — the shipped "
        "calls in this arm go through BaseSchemaClient's own limiter")


def test_the_arm_VERIFIES_BY_READ_BACK_and_never_by_code_0(arm_source):
    assert 'read_back["echoes"] is True' in arm_source
    assert 'read_back["persisted"] == first.to_dict()' in arm_source
    assert 'read_back["persisted"] == second.to_dict()' in arm_source
    assert 'read_back["gone"] is True' in arm_source


def test_the_gate_is_CLASSIFIED_in_the_registry_with_a_written_reason():
    import gate_registry

    row = gate_registry.REGISTRY["test_live_base_views.py"]
    assert row.kind is gate_registry.Kind.HAS_COMPANION
    assert len(row.reason) > 120, "a classification without a usable reason is a shrug"
    companion = gate_registry.REGISTRY["test_live_base_views_offline.py"]
    assert companion.subject == "test_live_base_views.py"
