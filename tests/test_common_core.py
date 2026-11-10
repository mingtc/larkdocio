"""Shared read/write core surface tests (LD-061 + AC3).

The maintainer directive relocates everything genuinely shared between read and write —
tenant-token/auth management, the write transport (throttle + ``99991400``
backoff), URL validation, and the IPv4 pin — into a shared core
(``larkdocio.common``). The read path is refactored onto it, strictly
behavior-preserving; the old module paths remain as **transparent back-compat
shims** so any external (wheel-consumer) importer keeps working unchanged.

These tests pin:
* **AC1** — the shared primitives are importable from the shared location;
* **AC3** — the read path (``read.download``) resolves creds / validates URLs /
  pins IPv4 through the shared core (its bound names *are* the core's);
* back-compat — ``larkdocio.auth`` and ``larkdocio.utils.url`` re-export the
  *same* objects the core defines (the shim is transparent, not a fork).
"""


# --------------------------------------------------------------------------- #
# AC1 — the shared primitives are importable from the shared location          #
# --------------------------------------------------------------------------- #

def test_shared_primitives_importable_from_common():
    from larkdocio.common import (  # noqa: F401
        validate_download_url,
        unescape_url,
        get_read_credentials,
        set_env_credentials,
        init_env,
        pin_socket_to_ipv4,
        apply_ipv4_pin,
        READ_ENV,
        LEGACY_ENV,
        WRITE_ENV,
        WriteTransport,
        RateLimiter,
        fetch_tenant_access_token,
    )


def test_common_url_and_auth_submodules_exist():
    import larkdocio.common.url as url
    import larkdocio.common.auth as auth
    import larkdocio.common.transport as transport

    assert callable(url.validate_download_url)
    assert callable(auth.get_read_credentials)
    assert callable(transport.fetch_tenant_access_token)


# --------------------------------------------------------------------------- #
# AC3 — the read path is refactored onto the shared core                       #
# --------------------------------------------------------------------------- #

def test_read_download_uses_shared_core_symbols():
    from larkdocio.read import download
    from larkdocio.common import get_read_credentials, init_env, validate_download_url

    assert download.get_read_credentials is get_read_credentials
    assert download.init_env is init_env
    assert download.validate_download_url is validate_download_url


def test_config_cmd_uses_shared_core_symbols():
    from larkdocio.read import config_cmd
    from larkdocio.common import get_read_credentials, init_env, set_env_credentials

    assert config_cmd.get_read_credentials is get_read_credentials
    assert config_cmd.init_env is init_env
    assert config_cmd.set_env_credentials is set_env_credentials


# --------------------------------------------------------------------------- #
# Back-compat — the old module paths are transparent shims over the core        #
# --------------------------------------------------------------------------- #

def test_auth_shim_reexports_the_same_core_objects():
    import larkdocio.auth as shim
    import larkdocio.common.auth as core

    for name in (
        "get_read_credentials",
        "get_write_credentials",
        "set_env_credentials",
        "init_env",
        "pin_socket_to_ipv4",
        "apply_ipv4_pin",
    ):
        assert getattr(shim, name) is getattr(core, name), name
    assert shim.READ_ENV == core.READ_ENV
    assert shim.LEGACY_ENV == core.LEGACY_ENV
    assert shim.WRITE_ENV == core.WRITE_ENV


def test_utils_url_shim_reexports_the_same_core_objects():
    import larkdocio.utils.url as shim
    import larkdocio.common.url as core

    assert shim.validate_download_url is core.validate_download_url
    assert shim.unescape_url is core.unescape_url
