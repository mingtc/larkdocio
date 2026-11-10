"""Auth credential-scheme tests (read/write separation) + ``.env`` bootstrap.

The read path resolves the ``LARK_READ_APP_*`` pair when both are set, else
falls back to the legacy ``LARK_APP_*`` pair, and must NEVER consult the
``LARK_WRITE_APP_*`` pair reserved for the writer.

The second half (LD-016) pins ``init_env``'s ``.env``
bootstrap side effect and ``set_env_credentials`` persistence.
"""
import os
from pathlib import Path

import pytest

import larkdocio.auth as auth
from larkdocio.errors import LarkConfigError


def _clear(monkeypatch):
    for name in (*auth.READ_ENV, *auth.LEGACY_ENV, *auth.WRITE_ENV):
        monkeypatch.delenv(name, raising=False)


def test_legacy_pair_accepted(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LARK_APP_ID", "legacy_id")
    monkeypatch.setenv("LARK_APP_SECRET", "legacy_sec")
    assert auth.get_read_credentials() == ("legacy_id", "legacy_sec")


def test_read_pair_preferred_over_legacy(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LARK_APP_ID", "legacy_id")
    monkeypatch.setenv("LARK_APP_SECRET", "legacy_sec")
    monkeypatch.setenv("LARK_READ_APP_ID", "read_id")
    monkeypatch.setenv("LARK_READ_APP_SECRET", "read_sec")
    assert auth.get_read_credentials() == ("read_id", "read_sec")


def test_write_pair_never_used_by_read_path(monkeypatch):
    _clear(monkeypatch)
    # Only write creds present -> the read path refuses (never the write pair). The CLAIM this
    # test makes is unchanged and is the point: the write pair is not borrowed for a read. What
    # changed is how "no read pair" is reported — it used to be an empty tuple this asserted on
    # (``rid == "" and rsec == ""``), and LD-580 made it the same typed refusal the write half
    # has always raised, so the assertion moves onto the refusal rather than being dropped.
    monkeypatch.setenv("LARK_WRITE_APP_ID", "w_id")
    monkeypatch.setenv("LARK_WRITE_APP_SECRET", "w_sec")
    with pytest.raises(LarkConfigError) as refusal:
        auth.get_read_credentials()
    assert "w_id" not in str(refusal.value) and "w_sec" not in str(refusal.value)
    # With legacy also present, write creds are still ignored.
    monkeypatch.setenv("LARK_APP_ID", "legacy_id")
    monkeypatch.setenv("LARK_APP_SECRET", "legacy_sec")
    assert auth.get_read_credentials() == ("legacy_id", "legacy_sec")


def test_no_pair_at_all_is_a_typed_refusal_not_a_blank_tuple(monkeypatch):
    """The retired sentinel, pinned where the resolution contract lives (LD-580). The full
    refusal contract — the in-force pair, the bootstrap, the ``.env`` doctrine, no echoed
    value — is fenced in ``tests/test_read_credential_fence.py``."""
    _clear(monkeypatch)
    with pytest.raises(LarkConfigError):
        auth.get_read_credentials()


def test_partial_read_pair_falls_back_to_legacy(monkeypatch):
    # A lone read id with no matching secret must NOT mix a read id with a
    # legacy secret — it falls back to the full legacy pair.
    _clear(monkeypatch)
    monkeypatch.setenv("LARK_READ_APP_ID", "read_id_only")
    monkeypatch.setenv("LARK_APP_ID", "legacy_id")
    monkeypatch.setenv("LARK_APP_SECRET", "legacy_sec")
    assert auth.get_read_credentials() == ("legacy_id", "legacy_sec")


# --------------------------------------------------------------------------- #
# get_write_credentials — write-only, NO read/legacy fallback (LD-063 / S4)     #
# --------------------------------------------------------------------------- #

def test_write_pair_resolved(monkeypatch):
    """Both write creds set -> get_write_credentials returns exactly them."""
    _clear(monkeypatch)
    monkeypatch.setenv("LARK_WRITE_APP_ID", "w_id")
    monkeypatch.setenv("LARK_WRITE_APP_SECRET", "w_sec")
    assert auth.get_write_credentials() == ("w_id", "w_sec")


def test_write_getter_strips_whitespace(monkeypatch):
    """Surrounding whitespace is stripped, mirroring the read getter."""
    _clear(monkeypatch)
    monkeypatch.setenv("LARK_WRITE_APP_ID", "  w_id  ")
    monkeypatch.setenv("LARK_WRITE_APP_SECRET", "\tw_sec\n")
    assert auth.get_write_credentials() == ("w_id", "w_sec")


def test_write_getter_no_read_or_legacy_fallback(monkeypatch):
    """AC1 — with read + legacy set but the write pair unset, the write getter
    must FAIL LOUD (never silently borrow a read/legacy credential)."""
    _clear(monkeypatch)
    monkeypatch.setenv("LARK_READ_APP_ID", "read_id")
    monkeypatch.setenv("LARK_READ_APP_SECRET", "read_sec")
    monkeypatch.setenv("LARK_APP_ID", "legacy_id")
    monkeypatch.setenv("LARK_APP_SECRET", "legacy_sec")
    with pytest.raises(LarkConfigError) as excinfo:
        auth.get_write_credentials()
    # The failure must not have leaked a read/legacy value into the message.
    text = str(excinfo.value)
    for leaked in ("read_id", "read_sec", "legacy_id", "legacy_sec"):
        assert leaked not in text


def test_write_getter_missing_raises_config_error(monkeypatch):
    """AC1 — nothing configured is a typed config error, not an empty borrow."""
    _clear(monkeypatch)
    with pytest.raises(LarkConfigError):
        auth.get_write_credentials()


def test_write_getter_lone_id_raises(monkeypatch):
    """A lone write id with no matching secret is an error (no mixing)."""
    _clear(monkeypatch)
    monkeypatch.setenv("LARK_WRITE_APP_ID", "w_id_only")
    with pytest.raises(LarkConfigError):
        auth.get_write_credentials()


def test_write_getter_lone_secret_raises(monkeypatch):
    """A lone write secret with no matching id is an error (no mixing)."""
    _clear(monkeypatch)
    monkeypatch.setenv("LARK_WRITE_APP_SECRET", "w_sec_only")
    with pytest.raises(LarkConfigError):
        auth.get_write_credentials()


def test_write_getter_error_message_leaks_no_values(monkeypatch):
    """The typed error must never print/leak a credential value."""
    _clear(monkeypatch)
    monkeypatch.setenv("LARK_WRITE_APP_ID", "SENTINEL_SECRET_VALUE")
    with pytest.raises(LarkConfigError) as excinfo:
        auth.get_write_credentials()
    assert "SENTINEL_SECRET_VALUE" not in str(excinfo.value)


def test_write_getter_importable_from_common():
    """New code imports the write getter from the shared core surface."""
    from larkdocio.common import get_write_credentials as core_getter

    assert core_getter is auth.get_write_credentials  # shim re-exports the same object


def test_read_package_never_references_write_getter():
    """AC3 — structural: no ``read/**`` source references the write getter or the
    ``LARK_WRITE_APP_*`` names. Read work must be provably write-credential-free."""
    read_dir = Path(auth.__file__).resolve().parent / "read"
    offenders = []
    for py in read_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if "get_write_credentials" in text or "LARK_WRITE_APP" in text:
            offenders.append(py.name)
    assert offenders == [], f"read package references write creds: {offenders}"


def _guard_legacy_env(monkeypatch):
    """``init_env`` calls ``load_dotenv(override=True)`` on the ``.env`` it writes,
    mutating ``os.environ`` directly. Touching these keys via monkeypatch ensures
    teardown restores the pre-test process state regardless of that mutation.

    Both accepted read schemes are guarded: the bootstrap writes the preferred pair,
    while a pre-existing legacy file is still loaded onto the legacy names."""
    for name in (*auth.READ_ENV, *auth.LEGACY_ENV):
        monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------- #
# init_env bootstrap side effect (AC1)                                        #
# --------------------------------------------------------------------------- #

def test_init_env_bootstraps_missing_env_file(monkeypatch, tmp_path):
    _guard_legacy_env(monkeypatch)
    env_path = tmp_path / ".env"
    assert not env_path.exists()

    returned = auth.init_env(str(env_path))

    assert env_path.exists()
    assert Path(returned) == env_path.resolve()
    text = env_path.read_text(encoding="utf-8")
    # The stub assigns the pair the read path PREFERS (the legacy pair is named in a
    # comment as the accepted fallback, never assigned) — see
    # tests/test_env_credential_bootstrap.py for the full contract.
    assert f"{auth.READ_ENV[0]}=" in text
    assert f"{auth.READ_ENV[1]}=" in text


def test_init_env_bootstraps_cwd_env_when_no_path(monkeypatch, tmp_path):
    """With no explicit path, ``<cwd>/.env`` is the bootstrap target (auth.py:52)."""
    _guard_legacy_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    returned = auth.init_env(None)

    assert (tmp_path / ".env").exists()
    assert Path(returned) == (tmp_path / ".env").resolve()


def test_init_env_does_not_clobber_existing_env(monkeypatch, tmp_path):
    """An existing ``.env`` is loaded, not overwritten (idempotent bootstrap)."""
    _guard_legacy_env(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text("LARK_APP_ID=already\nLARK_APP_SECRET=here\n", encoding="utf-8")

    auth.init_env(str(env_path))

    assert env_path.read_text(encoding="utf-8") == "LARK_APP_ID=already\nLARK_APP_SECRET=here\n"
    assert os.environ["LARK_APP_ID"] == "already"


# --------------------------------------------------------------------------- #
# set_env_credentials persistence (AC1)                                       #
# --------------------------------------------------------------------------- #

def test_set_env_credentials_persists_to_env_and_process(monkeypatch, tmp_path):
    _guard_legacy_env(monkeypatch)
    env_path = tmp_path / ".env"

    auth.set_env_credentials("my_app_id", "my_app_secret", str(env_path))

    text = env_path.read_text(encoding="utf-8")
    assert "my_app_id" in text
    assert "my_app_secret" in text
    # also written into the live process env for the current run, under the preferred names
    assert os.environ[auth.READ_ENV[0]] == "my_app_id"
    assert os.environ[auth.READ_ENV[1]] == "my_app_secret"


def test_set_env_credentials_only_sets_provided_fields(monkeypatch, tmp_path):
    """A blank field is not persisted (the ``if app_id`` / ``if app_secret`` guards)."""
    _guard_legacy_env(monkeypatch)
    env_path = tmp_path / ".env"

    auth.set_env_credentials("only_id", "", str(env_path))

    assert os.environ[auth.READ_ENV[0]] == "only_id"
    assert os.environ.get(auth.READ_ENV[1], "") == ""
