"""LD-394 — invoke the CLI so a failure names ITSELF.

``CliRunner().invoke`` **swallows** every exception raised inside the invocation and
parks it on the result object. A test that throws that result away therefore cannot
fail with its own cause: when the command dies before reaching a monkeypatched
handler, the capture dict stays empty and the test dies two lines later on a
``KeyError`` — the symptom, with the real exception discarded (LD-394; the class was
root-caused in LD-393, but the assertion shape is what destroyed the evidence).

``invoke_cli`` is the one way this suite invokes a click CLI when it expects the
invocation to succeed: it re-raises the swallowed exception (chained, so the original
traceback is printed) and otherwise asserts the exit code, quoting the captured
output. ``tests/test_cli_invocation_shape.py`` holds the corpus to it.
"""
from click.testing import CliRunner


def invoke_cli(cli, args, *, expect_exit=0, runner=None, **kwargs):
    """Invoke ``cli`` with ``args`` and assert it exited with ``expect_exit``.

    Returns the ``click.testing.Result`` so a caller can still read ``.output``.
    Raises the *real* exception the runner swallowed, if there was one.
    """
    result = (runner or CliRunner()).invoke(cli, args, **kwargs)
    exc = result.exception
    if exc is not None and not isinstance(exc, SystemExit):
        raise AssertionError(
            f"CLI invocation {list(args)!r} raised {type(exc).__name__}: {exc}\n"
            f"--- captured output ---\n{result.output}"
        ) from exc
    assert result.exit_code == expect_exit, (
        f"CLI invocation {list(args)!r} exited {result.exit_code}, "
        f"expected {expect_exit}\n--- captured output ---\n{result.output}"
    )
    return result
