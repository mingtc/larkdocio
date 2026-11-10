"""larkdocio.auth — back-compat shim over :mod:`larkdocio.common.auth`.

Credential resolution + ``.env`` handling + the IPv4 pin were relocated into the
shared read/write core (:mod:`larkdocio.common.auth`) by LD-061,
so read and write share one hardened substrate. This module remains as a
**transparent** re-export so any existing importer (e.g. a wheel consumer doing
``from larkdocio.auth import get_read_credentials``) keeps working unchanged — the
names bound here are the *same objects* the core defines, not a fork.

New code should import from :mod:`larkdocio.common` instead.
"""
from larkdocio.common.auth import (  # noqa: F401
    DISABLE_IPV4_PIN_ENV,
    LEGACY_ENV,
    READ_ENV,
    WRITE_ENV,
    apply_ipv4_pin,
    get_read_credentials,
    get_write_credentials,
    init_env,
    pin_socket_to_ipv4,
    set_env_credentials,
)

__all__ = [
    "DISABLE_IPV4_PIN_ENV",
    "LEGACY_ENV",
    "READ_ENV",
    "WRITE_ENV",
    "apply_ipv4_pin",
    "get_read_credentials",
    "get_write_credentials",
    "init_env",
    "pin_socket_to_ipv4",
    "set_env_credentials",
]
