"""The always-on offline half of ``test_live_base_schema_arm`` (LD-263).

The live arm runs only with credentials and a network. What it *claims* — that it changes only
Bases it created itself, that the copy it makes is **recorded before anything else can fail**,
that it resolves the WRITE pair and never the read one, that it skips loudly rather than passing
silently — is exactly the class of claim a credential-less run verifies by not running. So it is
verified **here**, statically, on every plain ``pytest``:

* **disposables only** — every write target comes from ``base_write_harness`` or from the arm's
  own copy of one, and the file names no configured document, sheet or Base variable anywhere.
  This is the one that matters most on this rung: the arm's verbs include *rename a Base* and
  *copy a Base*, and the configured Scratch Base holds hand-authored ``Lookup`` / ``Email`` /
  ``Stage`` fields the API cannot recreate;
* **the copy is LEDGERED at birth** — the arm records the copy's token in the harness ledger on
  the statement after the copy call, so a failure between the copy and the teardown leaves a
  *recorded* Base rather than a lost one. Checked in the syntax tree, not read out of prose;
* **trash, not purge, IN WRITING** — register row 9's fact is in the arm's own docstring, so a
  reader of the gate meets it, and the row and the docstring are held to agree;
* **mutating by construction** — every registered schema op declares that it mutates and the arm
  asserts it before its first call, with the read registry asserted still wholly read-only in the
  same breath — the whole reason there are three registries;
* **no destructive verb** — the arm calls no delete of its own; teardown is the harness's;
* **the settle is the shipped one** — the arm imports ``schema_settle.settle`` rather than
  sleeping, so the gate cannot quietly become the defect the contract forbids;
* **loud skips** and **a budget**, the shape every Base arm ships.

It imports nothing from the live arm and runs no gate.
"""
import ast
import re

import pytest

from larkdocio.base import ops as base_ops
from larkdocio.base import schema_ops
from larkdocio.base import write_ops

from guard_kit import REPO_ROOT

_REPO = REPO_ROOT
_TESTS = REPO_ROOT / "tests"
_ARM = _TESTS / "test_live_base_schema_arm.py"

#: Every configured target this repository knows about. None may appear in the arm.
_FORBIDDEN_TARGET_ENV = (
    "LARKDOCIO_SCRATCH_BASE",
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


def test_the_arm_exists_and_is_marked_live_write(arm_source):
    assert "pytestmark = pytest.mark.live_write" in arm_source, (
        "the arm must be deselected by default; an unmarked live write test would run in "
        "every plain pytest — and this one creates, renames and COPIES real Bases")


def test_the_schema_registry_is_WHOLLY_MUTATING_and_the_read_one_still_is_not():
    assert schema_ops.all_mutate() is True
    assert write_ops.all_mutate() is True
    assert base_ops.read_only() is True
    names = {d.name for d in schema_ops.schema_ops()}
    assert not (names & {d.name for d in base_ops.OPS})
    assert not (names & {d.name for d in write_ops.WRITE_OPS})


def test_the_arm_asserts_the_registry_BEFORE_it_calls_anything(arm_source):
    head = arm_source.split("def test_the_live_schema_arm_round_trips")[0]
    assert "schema_ops.all_mutate() is True" in head
    assert "base_ops.read_only() is True" in head


def arm_code(source):
    """The arm's source with every string literal and comment removed.

    The scan below asks *"does any CODE PATH read a configured target"*, and this arm's own
    docstring **names** the Scratch Base in prose — deliberately, because a reader has to be
    told why it is off limits. Prose that explains the fence must not trip the fence.
    """
    import io
    import tokenize

    return "\n".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type not in (tokenize.STRING, tokenize.COMMENT))


def test_the_arm_NAMES_NO_CONFIGURED_TARGET(arm_source):
    code = arm_code(arm_source)
    for variable in _FORBIDDEN_TARGET_ENV:
        assert variable not in code, (
            f"{variable} names a configured object; every live target on this rung is "
            "self-provisioned")
    assert "os.environ" not in code and "getenv" not in code
    docstring = ast.get_docstring(ast.parse(arm_source)) or ""
    assert "LARKDOCIO_SCRATCH_BASE" in docstring, (
        "the arm must SAY which configured Base it is refusing to touch, and why — an "
        "unexplained fence is one somebody removes")


def test_EVERY_write_target_comes_from_the_harness_or_from_the_arms_own_copy(arm_tree):
    """No app token is ever a literal. The parent comes from ``disposable_base``; the copy
    comes from the shipped ``copy_app`` of that parent, and from nowhere else."""
    body = ast.unparse(arm_tree)
    assert "base_write_harness.disposable_base()" in body
    assert "schema.copy_app(app_token, copy_title, folder_token=dest_folder)" in body
    tokens = [node.value for node in ast.walk(arm_tree)
              if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    suspicious = [text for text in tokens
                  if re.fullmatch(r"[A-Za-z0-9]{27}", text or "")]
    assert not suspicious, f"an app-token-shaped literal in a live arm: {suspicious}"


def test_THE_COPY_IS_LEDGERED_IMMEDIATELY_AFTER_IT_IS_MADE(arm_tree):
    """The one thing the harness cannot do for this arm: it did not create the copy. So the
    arm must record it, and must record it before anything else can fail."""
    body = ast.unparse(arm_tree)
    assert "ledger.record_create(copy_token, copy_title)" in body
    index_copy = body.index("copy_token = raw.app_token")
    index_record = body.index("ledger.record_create(copy_token, copy_title)")
    assert 0 < index_record - index_copy < 400, (
        "the copy must be ledgered on the statement after it exists — a gap is a window in "
        "which a failure loses a Base")
    assert "base_write_harness.disposable_title()" in body, (
        "the copy's title must carry the greppable disposable prefix, or a human trash sweep "
        "cannot find it")


def test_THE_PLACED_COPY_IS_LEDGERED_IMMEDIATELY_TOO_and_its_folder_is_THE_CONFIGURED_ONE(
        arm_tree):
    """LD-387's leg makes a **second** copy — the one carrying ``folder_token`` — so the same
    birth-record discipline applies to it.

    TRANSFORMED, NOT DELETED: the folder used to have to be **discovered live** (the bot's own
    root) rather than named from configuration, because a folder cannot be self-provisioned —
    ``create_folder`` is a permanent Drive write with no purge verb — and a configured folder
    was read as somebody else's tree. The no-self-provisioning half stands and is unchanged.
    What is superseded is the destination: the bot's own root is the space no human can browse,
    so the arm now uses the account holder's **own designated** disposables folder, which is
    configuration on purpose — it is how the account holder says *put your rubbish here*."""
    body = ast.unparse(arm_tree)
    assert "ledger.record_create(placed_token, placed_title)" in body
    index_copy = body.index("placed_token = entry.created_app_token")
    index_record = body.index("ledger.record_create(placed_token, placed_title)")
    assert 0 < index_record - index_copy < 400, (
        "the placed copy must be ledgered on the statement after it exists")
    assert "canary_support.require_disposables_folder()" in body, (
        "the target folder is the configured, human-visible disposables folder; a folder is "
        "still never self-provisioned here (create_folder is a permanent Drive write with no "
        "purge verb)")
    assert "root_folder_token()" not in body, (
        "the app's own root is no longer a destination this arm writes into")


def test_THE_FOLDER_CLAIM_IS_READ_BACK_FROM_THE_FOLDER_ITSELF_never_from_the_copys_echo(
        arm_source):
    """R12, in the shape LD-387's probe found: a ``code:0`` copy proves nothing about where the
    copy IS. The arm asks the **folder** for its children and matches on ``parent_token`` — and
    it ships the bad-value control beside it, because a key the server never reads could not
    refuse a folder that does not exist."""
    assert "list_folder_children_to_exhaustion" in arm_source
    assert "parent_token" in arm_source
    assert "1254702" in arm_source, (
        "the R12 control — a folder-shaped token naming nothing draws DriveNodeNotExist and "
        "creates no copy — is what distinguishes a key that is read from one that is decoration")


def test_the_arm_CALLS_NO_DESTRUCTIVE_VERB_of_its_own(arm_source):
    for verb in ("delete_app", "delete_table", "batch_delete", "drive.v1.files"):
        assert verb not in arm_source, verb
    assert "close_out()" in arm_source, "teardown is the harness's sweep, not a hand-rolled one"


def test_TRASH_NOT_PURGE_IS_IN_THE_ARMS_OWN_DOCSTRING_and_agrees_with_register_row_9(
        arm_source):
    docstring = ast.get_docstring(ast.parse(arm_source)) or ""
    assert "TRASH, NOT PURGE" in docstring.upper()
    assert "metas/batch_query" in docstring
    row = [line for line in (_REPO / "BASE.md").read_text(encoding="utf-8").splitlines()
           if line.startswith("| 9 |")]
    assert len(row) == 1
    assert "DELETE is TRASH, not purge" in row[0]
    assert "copied apps" in row[0], (
        "row 9 must still cover a COPIED app — this rung is what made that clause "
        "load-bearing")


def test_the_arm_uses_the_SHIPPED_SETTLE_and_never_sleeps(arm_source):
    assert "from larkdocio.base.schema_settle import settle" in arm_source
    assert "time.sleep" not in arm_source and "import time" not in arm_source


def test_the_arm_resolves_the_WRITE_pair_for_the_schema_client(arm_source):
    assert "BaseSchemaClient.from_write_credentials()" in arm_source
    assert "get_read_credentials" not in arm_source


def test_the_skip_is_LOUD_and_goes_through_the_harnesss_own_reason(arm_source):
    assert "base_write_harness.missing_reason()" in arm_source
    assert "pytest.skip(reason)" in arm_source


def test_the_arm_ASSERTS_a_call_budget_rather_than_intending_one(arm_source):
    assert "schema.api_calls == 1" in arm_source


def test_the_arm_VERIFIES_BY_READ_BACK_and_never_by_code_0(arm_source):
    assert "read_back" in arm_source
    assert "read.get_app(app_token).name == title" in arm_source
    assert 'read_back["read_backs"] == 1' in arm_source


def test_the_gate_is_CLASSIFIED_in_the_registry_with_a_written_reason():
    import gate_registry

    row = gate_registry.REGISTRY["test_live_base_schema_arm.py"]
    assert row.kind is gate_registry.Kind.HAS_COMPANION
    assert len(row.reason) > 120, "a classification without a usable reason is a shrug"
    companion = gate_registry.REGISTRY["test_live_base_schema_arm_offline.py"]
    assert companion.subject == "test_live_base_schema_arm.py"
