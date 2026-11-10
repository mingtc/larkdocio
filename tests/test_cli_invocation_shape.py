"""LD-394 — a discarded ``CliRunner`` result is a discarded failure cause.

Two guarantees, both about the TEST harness rather than the shipped CLI:

* the corpus guard — no test file throws away a ``CliRunner().invoke(...)`` result,
  because that is exactly the shape that turned "the CLI raised before reaching the
  patched handler" into a ``KeyError: 'kwargs'`` on the next line (LD-394's report);
* ``invoke_cli``'s own behaviour — it re-raises the swallowed exception, names a
  non-zero exit with the captured output, and otherwise hands back the result.
"""
import ast
from pathlib import Path

import click
import pytest
from cli_invoke import invoke_cli

TESTS_DIR = Path(__file__).resolve().parent


def _discarded_invocations():
    """Every ``CliRunner(...).invoke(...)`` used as a bare statement in ``tests/``."""
    found = []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
                continue
            func = node.value.func
            if not (isinstance(func, ast.Attribute) and func.attr == "invoke"):
                continue
            receiver = func.value
            if isinstance(receiver, ast.Call):
                receiver = receiver.func
            if isinstance(receiver, ast.Name) and receiver.id == "CliRunner":
                found.append(f"{path.relative_to(TESTS_DIR.parent)}:{node.lineno}")
    return found


def test_no_test_throws_away_a_clirunner_result():
    assert _discarded_invocations() == [], (
        "these invocations discard the result, so an exception raised inside the CLI "
        "is swallowed and re-surfaces as an unrelated failure later (LD-394). Use "
        "`from cli_invoke import invoke_cli` — it re-raises the real cause:\n  "
        + "\n  ".join(_discarded_invocations()))


# --------------------------------------------------------------------------- #
# invoke_cli itself.                                                            #
# --------------------------------------------------------------------------- #

@click.command()
def _boom():
    raise RuntimeError("the real cause")


@click.command()
def _refuses():
    raise click.ClickException("refused")


@click.command()
def _fine():
    click.echo("ok")


def test_invoke_cli_reraises_the_swallowed_exception_naming_the_real_cause():
    with pytest.raises(AssertionError) as excinfo:
        invoke_cli(_boom, [])
    assert "RuntimeError" in str(excinfo.value)
    assert "the real cause" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, RuntimeError)


def test_invoke_cli_names_a_nonzero_exit_and_quotes_the_output():
    with pytest.raises(AssertionError) as excinfo:
        invoke_cli(_refuses, [])
    message = str(excinfo.value)
    assert "exited 1" in message
    assert "refused" in message


def test_invoke_cli_can_assert_a_deliberate_refusal_exit_code():
    assert invoke_cli(_refuses, [], expect_exit=1).exit_code == 1


def test_invoke_cli_returns_the_result_on_success():
    assert invoke_cli(_fine, []).output == "ok\n"
