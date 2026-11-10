"""larkdocio.utils.sanitize — back-compat shim over :mod:`larkdocio.common.sanitize`.

Filename sanitisation was relocated into the shared read/write core
(:mod:`larkdocio.common.sanitize`) by LD-512, which folded the last two ``utils``
modules into ``common`` so there is one place to look for a shared primitive rather
than two. This module remains as a **transparent** re-export so existing importers
(``from larkdocio.utils.sanitize import sanitize_path_string`` in the download path
and the drive folder command, or a wheel consumer) keep working unchanged — the name
bound here is the *same object* the core defines. New code should import from
:mod:`larkdocio.common.sanitize` instead.

The discipline, and its precedent, is :mod:`larkdocio.utils.url` (LD-061).
"""
from larkdocio.common.sanitize import (  # noqa: F401
    sanitize_path_string,
)

__all__ = ["sanitize_path_string"]
