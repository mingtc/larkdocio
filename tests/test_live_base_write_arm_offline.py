"""The always-on offline half of ``test_live_base_write_arm``.

The live arm runs only with credentials and a network. What it *claims* — that it mutates only
a Base it created itself, that it resolves the WRITE pair and never the read one, that its
provisioner deletes in a ``finally``, and that it skips loudly rather than passing silently —
is exactly the class of claim a credential-less run verifies by not running. So it is verified
**here**, statically, on every plain ``pytest``:

* **disposables only** — the arm's every write target comes from ``base_write_harness``, and
  neither file names a configured document, sheet or Base variable anywhere. This is the one
  the two Base READ arms did not need, and the one that matters most: the configured Base holds
  hand-authored specimens the API cannot recreate;
* **delete in a ``finally``** — parsed out of the provisioner's own syntax tree, so the cleanup
  cannot quietly become happy-path-only;
* **mutating by construction** — every registered write op declares that it mutates, and the
  arm asserts it before its first call; the read registry is asserted still wholly read-only in
  the same test, which is the whole reason there are two registries;
* **the WRITE pair, never the read one** — the arm builds its writer from the write credentials
  and the write modules name no read credential;
* **loud skips** — the skip path goes through ``base_write_harness.missing_reason``, which
  names the missing variables, so an absent grant never reads as a pass;
* **a budget** — the arm asserts its call count rather than intending one.

It imports nothing from the live arm and runs no gate.
"""
import ast
from pathlib import Path

import pytest

import base_write_harness
from larkdocio.base import ops as base_ops
from larkdocio.base import write_ops

_TESTS = Path(__file__).resolve().parent
_ARM = _TESTS / "test_live_base_write_arm.py"
_HARNESS = _TESTS / "base_write_harness.py"

#: Every configured target this repository knows about. None of them may appear in either file.
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
def harness_source():
    return _HARNESS.read_text(encoding="utf-8")


def test_the_arm_exists_and_is_marked_live_write(arm_source):
    assert "pytestmark = pytest.mark.live_write" in arm_source, (
        "the arm must be deselected by default; an unmarked live write test would run in "
        "every plain pytest — and this one creates real Bases")


def test_the_write_registry_is_WHOLLY_MUTATING_and_the_read_one_still_is_not():
    assert write_ops.all_mutate() is True
    assert base_ops.read_only() is True
    assert not ({d.name for d in write_ops.WRITE_OPS} & {d.name for d in base_ops.OPS})


def test_the_arm_asserts_the_registry_BEFORE_it_calls_anything(arm_source):
    """The ordering matters: the posture check is worthless if it runs after the writes."""
    posture = arm_source.index("all_mutate()")
    first_call = arm_source.index("from_write_credentials()")
    assert posture < first_call, (
        "the registry assertion must come before the first client construction")


@pytest.mark.parametrize("env_name", _FORBIDDEN_TARGET_ENV)
def test_neither_the_arm_nor_the_harness_NAMES_a_configured_target(env_name, arm_source,
                                                                   harness_source):
    assert env_name not in arm_source, (env_name, "the arm writes only what it created")
    assert env_name not in harness_source, (env_name, "a token enters only through create")


def test_every_write_target_in_the_arm_comes_from_the_HARNESS(arm_source):
    assert "base_write_harness.disposable_base()" in arm_source
    # No hard-coded token shape anywhere: a Base token is a long opaque string, and a literal
    # one would mean the arm addressed something it did not create.
    tree = ast.parse(arm_source)
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    suspicious = [s for s in literals if len(s) > 20 and s.isalnum()]
    assert not suspicious, suspicious


def test_the_provisioner_deletes_in_a_FINALLY(harness_source):
    tree = ast.parse(harness_source)
    functions = [n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "disposable_base"]
    assert functions, "the provisioner must be a named function this guard can find"
    tries = [n for n in ast.walk(functions[0]) if isinstance(n, ast.Try) and n.finalbody]
    assert tries, "the delete must sit in a finally, not on the happy path"
    deletes = [n for t in tries for n in ast.walk(ast.Module(body=t.finalbody, type_ignores=[]))
               if isinstance(n, ast.Attribute) and n.attr == "delete"]
    assert deletes, "the finally must be the thing that deletes"


def test_the_harness_resolves_the_WRITE_pair_and_never_the_READ_one(harness_source):
    assert "get_write_credentials" in harness_source
    assert "get_read_credentials" not in harness_source
    assert "LARK_READ_APP" not in harness_source


def test_the_skip_is_LOUD_and_names_what_is_missing(monkeypatch, arm_source):
    monkeypatch.setattr(base_write_harness, "get_write_credentials", lambda: ("", ""))
    reason = base_write_harness.missing_reason()
    assert reason and "LARK_WRITE_APP_ID" in reason and "LARK_WRITE_APP_SECRET" in reason
    assert "pytest.skip(reason)" in arm_source, (
        "the arm must skip with the harness's own reason, never with a bare skip")


def test_the_harness_reports_READY_when_the_credentials_are_present(monkeypatch):
    monkeypatch.setattr(base_write_harness, "get_write_credentials",
                        lambda: ("an-app", "a-secret"))
    assert base_write_harness.missing_reason() is None


def test_the_arm_asserts_a_CALL_BUDGET(arm_source):
    assert "api_calls ==" in arm_source, (
        "gentleness is an assertion, not an intention — an unbudgeted arm can grow legs "
        "nobody notices until a rate limiter does")


def test_the_arm_verifies_every_write_THROUGH_THE_SHIPPED_READER(arm_source):
    """The effect assertions are the point: each write is confirmed by re-reading the table,
    never by the write call's own answer."""
    assert "BaseReadClient.from_read_credentials()" in arm_source
    assert arm_source.count("read.search_records(") >= 5


def test_the_harness_titles_are_GREPPABLE_disposables():
    title = base_write_harness.disposable_title()
    assert title.startswith(base_write_harness.DISPOSABLE_TITLE_PREFIX)
    assert base_write_harness.is_disposable_title(title)
    assert not base_write_harness.is_disposable_title("some real Base")


def test_nothing_in_the_harness_PROBES_a_rate_limit(harness_source):
    assert "99991400" not in harness_source
