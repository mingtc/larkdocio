"""The always-on offline half of ``test_live_base_link_resolution`` (LD-269 AC13).

The live arm runs only with credentials and a network. What it *claims* — that it is
read-only, that it targets the disposable Scratch Base and nothing else, that it skips loudly
rather than passing silently, and that it really carries the R12 control the whole arm exists
for — is exactly the class of claim a credential-less run verifies by not running. So it is
verified **here**, statically, on every plain ``pytest``:

* **read-only by construction** — every registered op declares ``mutates: False`` (including
  the ``batch_get_records`` this story added, which is a **POST read**), and the arm asserts
  that *before* its first call;
* **the R12 control is really in the arm** — an arm that sent the parameter and never sent the
  parameter-free control would prove the parameter was *sent*, which is the exact non-proof
  R12 exists to warn about;
* **no write credential and no write verb** anywhere in the arm;
* **the right target** — ``LARKDOCIO_SCRATCH_BASE``, never the canary doc, the scratch sheet,
  the block zoo, a self-provisioned disposable or a hard-coded token;
* **loud skips, twice over** — the credential skip goes through
  ``canary_support.base_missing_reason`` (which names the missing variable), and the
  *no-records* skip is its own message, because an arm that passes on an empty ask proves
  nothing;
* **the CONSTRUCTED link column is disclosed, not hidden** — the Scratch Base carries no link
  column and this arm does not write one, so the column it resolves is built from that Base's
  own schema and its own record ids; the arm's docstring says so in those words, and this
  companion asserts the disclosure is there;
* **the no-write proof is really made** — the arm re-reads ``table.revision`` and compares.

It imports nothing from the live arm and runs no gate.
"""
import ast
from pathlib import Path

import pytest

from larkdocio.base import ops as base_ops
from larkdocio.base.client import BATCH_GET_EMPTY_ASK_REFUSED_CODE

_TESTS = Path(__file__).resolve().parent
_ARM = _TESTS / "test_live_base_link_resolution.py"


@pytest.fixture(scope="module")
def arm_source():
    return _ARM.read_text(encoding="utf-8")


def test_the_arm_exists_and_is_marked_live(arm_source):
    assert "pytestmark = pytest.mark.live" in arm_source, (
        "the arm must be deselected by default; an unmarked live test runs in every plain "
        "pytest and turns a credential-less clone red")


def test_the_registry_the_arm_leans_on_really_is_read_only():
    """The arm's first assertion, made here too — so the claim is checked on every run and not
    only on the runs that have credentials. ``batch_get_records`` is the newest member and is
    a POST, which is precisely why ``mutates`` is declared and never derived from the verb."""
    assert base_ops.read_only()
    assert all(descriptor.mutates is False for descriptor in base_ops.OPS)
    assert base_ops.op("batch_get_records").http_method == "POST"


def test_the_arm_asserts_read_only_BEFORE_it_calls_anything(arm_source):
    tree = ast.parse(arm_source)
    names = [n.name for n in tree.body
             if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    first = "test_the_registry_declares_the_whole_arm_read_only_BEFORE_it_calls_anything"
    assert first in names
    assert names.index(first) == 0, (
        "the read-only assertion must come first in file order, because that is the order "
        "pytest runs them in and the point is to fail before touching the Base")


def test_the_arm_really_carries_the_PARAMETER_FREE_CONTROL(arm_source):
    """The one thing this arm exists for. Without the control it proves the parameter was
    *sent*, and R12's whole lesson is that sending is not honouring."""
    assert "batch_get_records(app_token, table.table_id, [])" in arm_source, (
        "the parameter-free control is missing — the arm would prove nothing about R12")
    assert "BATCH_GET_EMPTY_ASK_REFUSED_CODE" in arm_source, (
        "the control's answer must be asserted against the RECORDED refusal code, so the day "
        "the endpoint starts swallowing the empty ask the arm reddens instead of passing")


def test_the_EMPTY_ASK_REFUSAL_is_recorded_beside_the_call_it_describes():
    """The live finding, shipped as knowledge rather than as a workaround: `records/batch_get`
    VALIDATES `record_ids` (`99992402`, *"the min len is 1"*) instead of ignoring it. That is
    the evidence the parameter is real, so the code is a named constant next to the method and
    the docstring says what it means."""
    from larkdocio.base import client as base_client

    assert BATCH_GET_EMPTY_ASK_REFUSED_CODE == 99992402
    doc = base_client.batch_get_records.__doc__ if hasattr(
        base_client, "batch_get_records") else base_client.BaseReadClient.batch_get_records.__doc__
    assert "min len is 1" in doc, "the refusal's own words belong beside the call"
    assert "the resolver skips a target with no ids" in doc, (
        "nothing in this library may send the ask Lark refuses")


def test_the_arm_targets_the_SCRATCH_BASE_and_nothing_else(arm_source):
    assert "canary_support.scratch_base_url()" in arm_source
    for forbidden in ("canary_doc_url", "scratch_sheet_url", "blockzoo",
                      "base_write_harness", "LARK_WRITE_APP"):
        assert forbidden not in arm_source, f"the arm reaches {forbidden}, which is not its target"


def test_the_arm_names_NO_write_credential_and_NO_write_verb(arm_source):
    for forbidden in ("WriteClient", "write_credentials", "batch_create", "batch_update",
                      "batch_delete", "apply(", "dry_run"):
        assert forbidden not in arm_source, f"a write surface ({forbidden}) reached the arm"


def test_both_skip_paths_are_LOUD(arm_source):
    assert "canary_support.base_missing_reason()" in arm_source, (
        "the credential skip must name the missing variable")
    assert "holds no records" in arm_source, (
        "an arm that passes on an empty ask is an arm that proves nothing")


def test_the_CONSTRUCTED_link_column_is_DISCLOSED_in_the_arms_own_words(arm_source):
    """The arm builds its link column instead of reading one (the Scratch Base has none and
    this arm does not write). That is a real limit on what the run proves, so it is stated in
    the arm rather than left for a reader to infer from the code."""
    assert "constructed from this Base" in arm_source.lower() or \
        "is built here rather than read" in arm_source
    assert "carries no link column" in arm_source
    assert "p0-2-05" in arm_source, (
        "the arm must name where the link CELL shape is really pinned — offline, on a Base "
        "that has link columns")


def test_the_arm_makes_its_NO_WRITE_proof_by_RE_READING_the_revision(arm_source):
    assert "revision_before" in arm_source and "after.revision == revision_before" in arm_source


def test_the_arm_checks_the_DISCLOSURE_against_the_OBSERVED_call_count(arm_source):
    """AC8's live half: a disclosure nobody checks against the transport is a comment."""
    assert "client.api_calls - before" in arm_source
    assert "resolution.api_calls == observed" in arm_source
