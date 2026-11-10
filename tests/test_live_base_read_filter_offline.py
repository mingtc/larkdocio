"""The always-on offline half of ``test_live_base_read_filter``.

A live arm's claims about **what it targets** and **how it skips** are exactly the claims a
credential-less run verifies by not running. They are verified here instead, statically, on
every plain ``pytest``:

* the arm is **read-only** — it imports no write client, creates nothing, and compares the
  Scratch Base's app + table revisions across its own run, which is the one reliable write
  detector this repository has;
* it is **marked**, so a plain ``pytest`` never dials out, and it **skips loudly** through the
  shared reason helper that names the missing variable;
* and — the point of the whole story — it really contains its **differential**: a comparison of
  two reads, not a reading of a response code. A live arm that had quietly become a ``code:0``
  assertion would still pass live and would prove nothing, so the shape is pinned here.
"""
import ast
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent
_ARM = _TESTS / "test_live_base_read_filter.py"


def code(path):
    """The arm's source with its MODULE DOCSTRING removed.

    The docstring is where the arm explains what it deliberately does **not** touch, so a
    raw-text grep for a forbidden name would be tripped by the very sentence that promises it.
    The fence is about what the code does; the code is what is grepped.
    """
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    doc = module.body[0]
    assert isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant), (
        f"{path.name} lost its module docstring, which is where its fences are stated")
    return "\n".join(source.splitlines()[doc.end_lineno:])


@pytest.fixture(scope="module")
def arm():
    return code(_ARM)


def test_the_arm_is_MARKED_so_a_plain_pytest_never_dials_out(arm):
    assert "pytestmark = pytest.mark.live\n" in arm


def test_the_arm_SKIPS_LOUDLY_through_a_reason_that_names_what_is_missing(arm):
    assert "canary_support.base_missing_reason()" in arm
    assert "pytest.skip(reason)" in arm, "a skip with no reason reads as a pass in a log"


def test_the_arm_imports_NO_WRITE_CLIENT_and_creates_nothing(arm):
    """It targets the configured Scratch Base, which is legitimate for a READ feature and only
    for one: that Base holds the only hand-authored Lookup / Email / Stage fields in existence
    and the write harness refuses it as a target by allow-list."""
    for forbidden in ("write_client", "BaseWriteClient", "BaseSchemaClient",
                      "get_write_credentials", "schema_apply", "base_write_harness"):
        assert forbidden not in arm, (
            f"the read-filter arm names {forbidden!r}; it runs against a READ FIXTURE")


def test_the_arm_proves_it_moved_nothing_by_COMPARING_revisions(arm):
    assert "BASELINE[\"app_revision\"]" in arm
    assert "after_app == BASELINE[\"app_revision\"]" in arm
    assert "after_tables == BASELINE[\"tables\"]" in arm, (
        "the read-only claim must be a comparison, not an assertion of the obvious")


def test_the_arm_HARD_CODES_NO_BASE_TOKEN(arm):
    """A Base token spelled into a test is a target nobody chose."""
    for node in ast.walk(ast.parse(arm)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert not node.value.startswith(("bascn", "Bas", "BaseScratchExample")), (
                f"a Base token is hard-coded: {node.value!r}")


def test_the_arm_COMPARES_TWO_READS_rather_than_reading_a_code(arm):
    assert "search_records(app_token, table_id)" in arm, (
        "there is no unfiltered control read to compare against")
    assert "set(filtered_ids) < set(all_ids)" in arm, (
        "the subset assertion must be strict — a filtered read that returns the whole table is "
        "what an IGNORED filter returns")
    assert "assert nothing == []" in arm, (
        "the match-nothing read is the sharpest R12 tell and must be present")
    assert "list(reversed(asc_ids))" in arm, (
        "the sort proof must be an ORDER assertion, and reversing asc is the one statement that "
        "holds under any collation the server uses")
    assert ".code == 0" not in arm


def test_the_ARM_IS_NAMED_BY_THE_SHIPPED_DOCSTRING_so_the_proof_is_findable():
    """A consumer reading ``help(BaseReadClient.search_records)`` is told where the differential
    proof lives; this keeps that citation from rotting into a dead path."""
    from larkdocio.base.client import BaseReadClient

    doc = BaseReadClient.search_records.__doc__
    assert "tests/test_live_base_read_filter.py" in doc
    assert _ARM.exists()
