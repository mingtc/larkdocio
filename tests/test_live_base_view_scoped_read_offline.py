"""The always-on offline half of ``test_live_base_view_scoped_read``.

The view-scoped arm is the one leg of this story that has to **write**, because the claim it
makes cannot be made against a view with no saved filter — a ``code:0`` and a full table is what
an *ignored* ``view_id`` also returns. What it writes, and where, is therefore the thing a
credential-less run must still be able to check:

* every token it addresses comes from ``base_write_harness.disposable_base``, whose allow-list
  refuses every pre-existing Base — including the configured Scratch Base, which is a READ
  fixture — and whose ``finally`` deletes what it made;
* it names no configured target anywhere, not even inside a fence;
* it is **marked** ``live_write`` and **skips loudly**;
* and its proof is a **differential against the server's own saved filter**, read back through
  ``get_view``, with the unfiltered-view control run beside it — the control being precisely the
  shape of the earlier capture that was mistaken for evidence.
"""
import ast
from pathlib import Path

import pytest

from test_live_base_read_filter_offline import code

_TESTS = Path(__file__).resolve().parent
_ARM = _TESTS / "test_live_base_view_scoped_read.py"


@pytest.fixture(scope="module")
def arm():
    return code(_ARM)


def test_the_arm_is_MARKED_live_write_so_a_plain_pytest_never_dials_out(arm):
    assert "pytestmark = pytest.mark.live_write\n" in arm


def test_the_arm_SKIPS_LOUDLY_through_the_harnesss_own_reason(arm):
    assert "base_write_harness.missing_reason()" in arm
    assert "pytest.skip(reason)" in arm, "a skip with no reason reads as a pass in a log"


def test_the_arm_NEVER_NAMES_THE_CONFIGURED_SCRATCH_BASE(arm):
    """The binding fence: the writes this proof needs go to a harness-created disposable, and
    the Base holding the hand-authored specimens is never a write target."""
    assert "LARKDOCIO_SCRATCH_BASE" not in arm
    assert "canary_support.scratch_base_url" not in arm
    assert "base_write_harness.disposable_base()" in arm, (
        "every token this arm writes must come from the harness, which allow-lists its own "
        "creations and refuses every pre-existing Base by construction")
    assert "is_disposable_title(title)" in arm, (
        "the disposable's title is what makes it greppable in a human trash sweep")


def test_the_arm_HARD_CODES_NO_BASE_TOKEN(arm):
    for node in ast.walk(ast.parse(arm)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert not node.value.startswith(("bascn", "Bas", "BaseScratchExample")), (
                f"a Base token is hard-coded: {node.value!r}")


def test_the_arm_CHECKS_THE_ROWS_AGAINST_THE_SERVERS_OWN_SAVED_FILTER(arm):
    assert "get_view(app_token, table_id, view_id).property.filter_info" in arm, (
        "the claim is proven against the filter the SERVER stored, read back through get_view — "
        "not against the filter the arm asked for")
    assert "R12 control" in arm and "default_view.view_id" in arm, (
        "the unfiltered-view control is what makes the filtered-view result mean something: a "
        "view_id read of a filterless view returns everything, which is also what an IGNORED "
        "view_id returns")
    assert "len(control) == len(unscoped)" in arm


def test_the_arm_PINS_THE_REFUSED_COMBINATION_as_costing_no_call(arm):
    assert "uncaptured" in arm
    assert "read.api_calls == before" in arm, (
        "the refusal is local by design; an arm that did not assert the call count would not "
        "show that")


def test_the_ARM_IS_NAMED_BY_THE_SHIPPED_DOCSTRING_so_the_proof_is_findable():
    from larkdocio.base.client import BaseReadClient

    assert "tests/test_live_base_view_scoped_read.py" in BaseReadClient.search_records.__doc__
    assert _ARM.exists()
