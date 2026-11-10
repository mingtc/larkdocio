"""larkdocio.utils.common — back-compat shim over :mod:`larkdocio.common.reporting`.

The two operator-facing reporting helpers — ``pretty_print`` (a config dict, formatted
for a human to read) and ``check_err`` (log an unexpected exception with the
report-this-if-it-is-a-bug banner, then re-raise it) — were relocated into the shared
read/write core (:mod:`larkdocio.common.reporting`) by LD-512, which folded the last
two ``utils`` modules into ``common``. They are named ``reporting`` there rather than
``common`` because ``larkdocio.common.common`` would say nothing; what they have in
common is that both are how the CLI reports something to the person running it.

This module remains as a **transparent** re-export so existing importers
(``from larkdocio.utils.common import pretty_print, check_err`` in the config command
and the download path, or a wheel consumer) keep working unchanged — the names bound
here are the *same objects* the core defines. New code should import from
:mod:`larkdocio.common.reporting` instead.

The discipline, and its precedent, is :mod:`larkdocio.utils.url` (LD-061).
"""
from larkdocio.common.reporting import (  # noqa: F401
    check_err,
    logger,
    pretty_print,
)

__all__ = ["check_err", "pretty_print", "logger"]
