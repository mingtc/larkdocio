"""The always-on OFFLINE half of ``test_live_typed_create_returns_gate`` (LD-583 AC7).

A live arm proves what it runs. This companion proves what a credential-less run cannot see by
not running: the arm's **posture** — that it self-provisions and never names a standing object,
that it uses the WRITE pair and never the read one, that it skips **loudly**, that it declares
its budget before the spend, and that its teardown **names** its residue rather than counting it.

Three things this arm needs that no earlier arm did.

**ONE: the arm's subject is a NEGATIVE, so the negative has to be asserted rather than printed.**
``CreatedDocument``'s whole claim is that the docx v1 reply carries **no** ``url``. An arm that
only checked the positive fields would leave the load-bearing half unmeasured — and a reply that
grew a ``url`` key is a **finding**, not a pass. So this companion pins that the arm asserts
``"url" not in created`` with a sentence saying so.

**TWO: two of the four verbs return the SDK's ``App``, not a dict**, so the arm's compatibility
check has to iterate ``App._types`` rather than a hand-typed list — a hand-typed list is a second
definition that drifts the day the pinned SDK grows a field. This companion pins the iteration.

**THREE: the copy's measured fact is an EMPTINESS** (``default_table_id`` comes back empty because
the copy is asynchronous). The same rule as ONE: it is asserted, with a sentence saying a
non-empty answer is a finding.

And the permanent prohibition: **no URL is ever assembled from a host and a token**, which this
companion pins by refusing any string-formatting of a host beside a token anywhere in the arm.
"""
import ast
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ARM = REPO_ROOT / "tests" / "test_live_typed_create_returns_gate.py"


@pytest.fixture(scope="module")
def source():
    return ARM.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tree(source):
    return ast.parse(source)


# --------------------------------------------------------------------------- #
# Posture — the shape every write-ring arm lives by.                            #
# --------------------------------------------------------------------------- #

def test_the_arm_is_in_the_live_write_ring_and_the_conformance_tier(source):
    assert "pytestmark = pytest.mark.live_write" in source
    assert "pytest.mark.conformance" in source


def test_every_test_SKIPS_LOUDLY_rather_than_failing_without_credentials(source):
    assert "canary_support.live_write_missing_reason()" in source
    assert "pytest.skip(reason)" in source
    # every live test body goes through the one gate helper
    bodies = source.count("def test_")
    assert bodies >= 3
    assert source.count("_live_or_skip()") >= bodies


def test_the_destination_is_the_CONFIGURED_HUMAN_VISIBLE_folder_and_never_the_bots_root(source):
    assert "canary_support.require_disposables_folder()" in source
    assert "root_folder_token" not in source


def test_NO_STANDING_OBJECT_is_named_anywhere_in_the_arm(source):
    """Every token this arm touches is one it created in this run."""
    for forbidden in ("LARKDOCIO_CANARY_DOC", "LARKDOCIO_SCRATCH", "blockzoo",
                      "canary_doc_url", "scratch_sheet_url", "scratch_base_url"):
        assert forbidden not in source, forbidden


def test_no_token_shaped_literal_is_pasted_into_the_arm(source):
    """A Lark token is ~27 opaque characters. A literal one would mean a real object was
    named — the thing the disposables doctrine exists to prevent."""
    for literal in re.findall(r'"([A-Za-z0-9]{24,})"', source):
        pytest.fail(f"a token-shaped literal is pasted into the arm: {literal!r}")


def test_the_BUDGET_is_DECLARED_IN_THE_ARM_before_the_spend(source):
    """`process/doctrine/live-resources.md` — a budget declared after the spend is not a
    limit. The arm's own docstring carries the table, kind by kind, with its teardown."""
    doc = ast.get_docstring(ast.parse(source))
    assert "THE BUDGET, declared before the spend" in doc
    for kind in ("docx document", "spreadsheet", "Base", "copy of a Base"):
        assert kind in doc, kind
    assert "Four objects" in doc
    assert "none permanent" in doc
    assert "no media token minted" in doc


def test_NOTHING_IS_UPLOADED_so_no_permanent_media_token_can_be_minted(source):
    """The one residue class that cannot be reclaimed. This arm creates four **reclaimable**
    objects and mints nothing permanent, which is why its budget can promise a clean sweep."""
    for uploader in ("upload", "put_image_in", "put_file_in", "DocxMediaClient",
                     "SheetsMediaClient"):
        assert uploader not in source, uploader


def test_EVERY_created_object_is_torn_down_in_a_finally(source, tree):
    """A teardown outside `finally` is a teardown that does not run when the body fails."""
    assert source.count("finally:") >= 2
    assert "with docx_ledger.disposable(" in source     # the docx contextmanager's own finally
    assert "delete_spreadsheet" in source
    assert "delete_base" in source


def test_the_residue_is_NAMED_per_object_and_never_summarised_as_a_count(source):
    """`process/doctrine/live-resources.md` — an orphan is named, not counted."""
    assert "[LD-583 residue]" in source
    assert "base_write_harness.orphans(" in source
    assert "[LD-583 orphans()]" in source
    assert "remaining == []" in source


def test_NO_FAKE_PURGE_LEG_and_NO_INVENTED_VERB_appears(source):
    for invented in ("purge", "cancel_upload", "abort", "delete_document(",):
        if invented == "delete_document(":
            # the docx delete is the ledger helper's, not the arm's own hand-rolled call
            assert invented not in source
        else:
            assert invented not in source, invented


# --------------------------------------------------------------------------- #
# The three this arm exists for.                                               #
# --------------------------------------------------------------------------- #

def test_ONE_the_docx_NO_URL_negative_is_ASSERTED_and_a_url_would_be_a_FINDING(source):
    """The load-bearing half. An arm that checked only the positive fields would leave the
    claim `CreatedDocument` is built on unmeasured."""
    assert 'assert "url" not in created' in source
    assert "is a finding, not a pass" in source
    assert "not hasattr(created, \"url\")" in source
    assert "created.no_url_reason in str(raised.value)" in source


def test_TWO_the_SDK_attribute_check_ITERATES_App_types_rather_than_a_hand_typed_list(source):
    """A hand-typed attribute list is a second definition of the SDK's shape, and it drifts
    the day the pinned SDK grows a field."""
    assert "for attribute in App._types:" in source
    assert source.count("for attribute in App._types:") >= 2   # create AND copy
    assert "isinstance(created, App)" in source
    assert "isinstance(copied, App)" in source


def test_THREE_the_copys_EMPTY_default_table_id_is_ASSERTED_as_the_measured_fact(source):
    assert "assert not copied.default_table_id" in source
    assert "the async-copy claim is measured" in source


def test_NO_URL_IS_EVER_ASSEMBLED_from_a_host_and_a_token(source):
    """The permanent prohibition (the issue's Out of scope). The arm asserts identity with the
    reply's own bytes; it never builds a link."""
    assert "https://" not in source
    assert "created.url == created[\"url\"]" in source


def test_the_arm_names_its_authorising_issue_in_its_own_run_command(source):
    """The consent fence's value is an authorising issue id, never a truthy flag."""
    doc = ast.get_docstring(ast.parse(source))
    assert "LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-583" in doc
