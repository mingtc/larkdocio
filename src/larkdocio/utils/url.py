"""larkdocio.utils.url — back-compat shim over :mod:`larkdocio.common.url`.

URL validation / unescaping were relocated into the shared read/write core
(:mod:`larkdocio.common.url`) by LD-061. This module remains as a
**transparent** re-export so existing importers (e.g.
``from larkdocio.utils.url import unescape_url`` in the block handlers, or a wheel
consumer) keep working unchanged — the names bound here are the *same objects* the
core defines. New code should import from :mod:`larkdocio.common` instead.
"""
from larkdocio.common.url import (  # noqa: F401
    unescape_url,
    validate_download_url,
)

__all__ = ["unescape_url", "validate_download_url"]
