"""Characterization / safety-net tests for LD-079.

The `larkdocio` named logger is shared by every library module (client, parser,
download, config, common/auth). Configuring it at **import** time means merely
`import larkdocio.cli` mutates process-wide logging state — the classic
"library attaches a handler at import" anti-pattern.

LD-079 moves that configuration from module import to the `cli()` group
callback (CLI invocation). These tests pin both halves of the contract:

* B2 — importing `larkdocio.cli` attaches **no** handler to `'larkdocio'`.
* B1 — an invoked CLI still binds a single `StreamHandler` with the same
  formatter (`"%(message)s"` at the default INFO level) and level (INFO).
* B3 — repeated invocation in one process does not stack handlers (idempotent).

**REWRITTEN (LD-211): B1's stream is now `sys.stderr`, not `sys.stdout`.** This test used to
pin `handler.stream is stdout_during_invocation`, which was a faithful characterization of the
import-time configuration LD-079 moved — and a defect the moment a subcommand's *output* went
to stdout. The `mermaid` subcommand writes compiled diagram source there, and the two ADVISORY
mermaid rules warn while compiling anyway, so a warning on stdout landed inside the emitted
source and produced a file that is not valid Mermaid: a corrupt artifact rather than an error.
The rule the command line now follows is **stdout carries a command's output, stderr carries
everything said about the run**, so the assertion below is re-pointed rather than relaxed —
the handler count, the formatter, the level and the idempotence legs are all unchanged, and the
observable consequence (`download`'s progress lines move to stderr) is carried in
`RELEASE_NOTES.md` as its own behavior change.
"""

import contextlib
import importlib
import io
import logging
import sys


@contextlib.contextmanager
def _isolated_larkdocio_logger():
    """Snapshot and restore the shared 'larkdocio' logger around a test.

    The logger is a global; these tests deliberately clear its handlers to
    observe (re)configuration, so we must put it back exactly as we found it or
    we would leak state into unrelated tests.
    """
    logger = logging.getLogger("larkdocio")
    saved_handlers = logger.handlers[:]
    saved_level = logger.level
    try:
        yield logger
    finally:
        logger.handlers[:] = saved_handlers
        logger.setLevel(saved_level)


def test_importing_cli_attaches_no_handler():
    """B2: a fresh import of larkdocio.cli must not touch the shared logger."""
    with _isolated_larkdocio_logger() as logger:
        logger.handlers.clear()
        # Force the module body to re-execute so we observe *import-time*
        # side effects, not a cached module object.
        sys.modules.pop("larkdocio.cli", None)
        importlib.import_module("larkdocio.cli")

        assert logger.handlers == [], (
            "importing larkdocio.cli must attach no handler to the "
            "'larkdocio' logger (configuration belongs at CLI invocation)"
        )


def test_invoking_cli_configures_stderr_handler_with_same_formatter_and_level():
    """B1: invoking the CLI binds one **stderr** handler, formatter/level preserved.

    The stream is the LD-211 change (see the module docstring); everything else about B1 is the
    original contract. Both streams are redirected so the assertion is a real discrimination
    between them rather than a coincidence of one being the process's own.
    """
    from larkdocio.cli import cli

    with _isolated_larkdocio_logger() as logger:
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            # invoke_without_command=True -> the bare group prints help and
            # returns; standalone_mode=False suppresses click's sys.exit.
            with contextlib.suppress(SystemExit):
                cli([], standalone_mode=False)
            stdout_during_invocation = sys.stdout
            stderr_during_invocation = sys.stderr

        stream_handlers = [
            h for h in logger.handlers if isinstance(h, logging.StreamHandler)
        ]
        assert len(stream_handlers) == 1, (
            "invoking the CLI should configure exactly one StreamHandler"
        )
        handler = stream_handlers[0]

        # Bound to stderr as it stands at invocation time (the redirect buffer here).
        assert handler.stream is stderr_during_invocation
        assert handler.stream is not stdout_during_invocation, (
            "the CLI log handler is on stdout again — a subcommand whose output IS stdout "
            "(`larkdocio mermaid`) then emits warnings into its own product"
        )
        # Same formatter and level as the historical import-time config (INFO default).
        assert handler.formatter is not None
        assert handler.formatter._fmt == "%(message)s"
        assert logger.level == logging.INFO


def test_repeated_cli_invocation_does_not_stack_handlers():
    """B3: idempotent — two invocations in one process keep a single handler."""
    from larkdocio.cli import cli

    with _isolated_larkdocio_logger() as logger:
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            for _ in range(2):
                with contextlib.suppress(SystemExit):
                    cli([], standalone_mode=False)

        stream_handlers = [
            h for h in logger.handlers if isinstance(h, logging.StreamHandler)
        ]
        assert len(stream_handlers) == 1, (
            "repeated CLI invocation must not stack handlers on the shared logger"
        )
