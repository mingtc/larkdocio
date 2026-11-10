"""larkdocio.errors — the typed exception taxonomy, re-exported from the shared core.

**This is the import path to use, and it is not going anywhere.** Every recipe in the shipped
guide says ``from larkdocio.errors import ...``, and that keeps working exactly as written.
What moved is only where the family is *authored*: the taxonomy now lives in the shared
read/write core, at :mod:`larkdocio.common.errors`, because the whole core raises these types
and nearly every module in the library imports them — so the definitions belong at the bottom
of the dependency stack rather than beside the command-line entry point. With the module at the
top level, the core imported the taxonomy while the taxonomy imported a core lookup back, at
import time, in both directions at once; one further import in either of two core files was
enough to make ``import larkdocio`` fail outright. Relocating the definitions into the core
made that impossible instead of merely absent, and a shipped check now holds the core to it.

**Transparent, and identity is the property that matters.** The names bound here are the *same
objects* :mod:`larkdocio.common.errors` defines, never a fork or a subclass. So
``except larkdocio.errors.LarkAPIError`` catches an error raised anywhere in the library,
``isinstance`` answers the same on both paths, and ``larkdocio.errors.LarkAPIError is
larkdocio.common.errors.LarkAPIError`` is true. A test holds the two name sets equal in both
directions, and asserts identity rather than importability, so a name cannot be added to the
core and silently miss this door — nor left behind here after the core drops it.

**The one thing a reader can see that did move.** A class reports where it is defined, so a
traceback and ``repr()`` now print ``larkdocio.common.errors.LarkConfigError`` where they
printed ``larkdocio.errors.LarkConfigError``. Nothing a program does with these types changes
— the class object, its name, its bases, its constructor and every message string are
untouched — but text scraped out of a log line is text, so it is written down here rather than
left to be discovered.

``help()`` on this module documents the whole family, because ``__all__`` below names it; the
authoritative prose for each type is that type's own docstring, and the taxonomy's overview is
``help(larkdocio.common.errors)``.
"""
from larkdocio.common.errors import (  # noqa: F401
    ALLOW_PARTIAL,
    ERROR_CODES,
    RATE_LIMIT_CODE,
    ErrorCodeNote,
    FencedPrimitiveError,
    LarkAPIError,
    LarkApplyRefusedError,
    LarkConfigError,
    LarkDocIOError,
    LarkEscapeError,
    LarkPaginationError,
    LarkPermissionError,
    LarkRateLimitError,
    LarkSnapshotIntegrityError,
    LarkSpreadsheetUnreadableError,
    MissingDestinationError,
    api_error,
    api_error_as,
    gate_refusals,
    note_for,
)

#: Held equal to :data:`larkdocio.common.errors.__all__` in BOTH directions, by identity, so
#: this door cannot drift from the core it fronts. Not decoration: without ``__all__``,
#: ``pydoc`` documents only what a module DEFINES, so ``help()`` here would render an empty
#: page — and this module is the one a consumer is pointed at when something failed.
__all__ = [
    "ALLOW_PARTIAL",
    "ERROR_CODES",
    "ErrorCodeNote",
    "FencedPrimitiveError",
    "LarkAPIError",
    "LarkApplyRefusedError",
    "LarkConfigError",
    "LarkDocIOError",
    "LarkEscapeError",
    "LarkPaginationError",
    "LarkPermissionError",
    "LarkRateLimitError",
    "LarkSnapshotIntegrityError",
    "LarkSpreadsheetUnreadableError",
    "MissingDestinationError",
    "RATE_LIMIT_CODE",
    "api_error",
    "api_error_as",
    "gate_refusals",
    "note_for",
]
