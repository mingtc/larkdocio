"""B2 — ``larkdocio config`` never auto-writes into the installed package dir (LD-016).

Settled semantics (decision #1 of the pipeline-fixes spec): **never auto-write** a config; write a
``config.json`` **only** to an explicitly-given ``--config`` path; **reading** falls
back to the packaged default **read-only**.

Env loading + credential resolution are neutralized so the suite never touches the
real repo ``.env`` and stays fully offline.
"""
import json

import pytest

from larkdocio.read import config_cmd
from larkdocio.read.config import (
    OutputConfig,
    get_default_config_path,
    read_config_from_file,
)


def _neutralize(monkeypatch):
    monkeypatch.setattr(config_cmd, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(config_cmd, "get_read_credentials", lambda: ("id", "sec"))


def test_config_no_explicit_path_never_writes_packaged_default(monkeypatch, tmp_path):
    """AC2 (B2): with no ``--config``, ``config`` must create NO file under the
    package dir. (Red before the fix: the old auto-write created it.)"""
    _neutralize(monkeypatch)
    fake_default = tmp_path / "site-packages" / "larkdocio" / "config.json"
    monkeypatch.setattr(config_cmd, "get_default_config_path", lambda: str(fake_default))

    config_cmd.handle_config_command("", "", "", None)  # no --config

    assert not fake_default.exists(), "B2: config must never auto-write the packaged default"


def test_config_explicit_path_writes_config_there(monkeypatch, tmp_path):
    """AC2 (B2): an explicit ``--config`` path is the only place ``config`` writes."""
    _neutralize(monkeypatch)
    target = tmp_path / "sub" / "c.json"  # parent does not exist yet

    config_cmd.handle_config_command("", "", str(target), None)

    assert target.exists()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert "output" in data
    # NARROWED by LD-650: a since-retired key was the one named here. The subject —
    # `config` writes a real schema, not an empty object — is held against the live field
    # set instead, so no future retirement re-breaks it.
    assert set(data["output"]) == set(OutputConfig().to_dict())


def test_config_explicit_path_not_clobbered_when_present(monkeypatch, tmp_path):
    """An existing explicit config is read, not overwritten with defaults."""
    _neutralize(monkeypatch)
    target = tmp_path / "c.json"
    target.write_text(
        json.dumps({"output": {"image_dir": "custom", "title_as_filename": False}}),
        encoding="utf-8",
    )

    config_cmd.handle_config_command("", "", str(target), None)

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["output"]["image_dir"] == "custom"
    assert data["output"]["title_as_filename"] is False


def test_config_sets_credentials_when_app_id_given(monkeypatch):
    """config_cmd.py:27-28 — when ``app_id``/``app_secret`` are given, credentials are
    persisted via ``set_env_credentials`` (stubbed so the real ``.env`` is untouched)."""
    _neutralize(monkeypatch)
    calls = []
    monkeypatch.setattr(
        config_cmd, "set_env_credentials",
        lambda app_id, app_secret, env_path=None: calls.append((app_id, app_secret, env_path)),
    )

    # No --config → reads the packaged default read-only (no write); app_id set → line 28.
    config_cmd.handle_config_command("APPID", "APPSECRET", "", None)

    assert calls == [("APPID", "APPSECRET", None)]


def test_config_error_handler_reraises(monkeypatch):
    """config_cmd.py:43-44 — an internal failure is routed through ``check_err``,
    which re-raises (the ``except Exception`` handler branch)."""
    _neutralize(monkeypatch)

    def _boom(path):
        raise RuntimeError("config boom")

    monkeypatch.setattr(config_cmd, "read_config_from_file", _boom)

    with pytest.raises(RuntimeError, match="config boom"):
        config_cmd.handle_config_command("", "", "", None)


def test_packaged_default_is_readable_fallback():
    """AC2 (B2): reading still falls back to the packaged default (read-only) — the
    shipped ``config.json`` exists and yields today's defaults."""
    cfg = read_config_from_file(get_default_config_path())
    assert cfg.output.image_dir == "static"
    assert cfg.output.title_as_filename is True


# --------------------------------------------------------------------------- #
# LD-033 (R-S0 net, AC3 / P0.2) — the `config` command through the CLICK ring. #
#                                                                             #
# The tests above call handle_config_command directly; the click WIRING       #
# (cli.py:40 no-subcommand help, cli.py:47 config-command arg passthrough via  #
# ctx.obj) and the config_cmd 46.7% cluster had no CliRunner coverage — the    #
# CLI live-ring gap named in dev/test-quality-2026-07-24.md § 3B. These invoke #
# the real group so the global `--config` / `--env-file` options and the       #
# `--appId` / `--appSecret` passthrough are exercised end-to-end.              #
# --------------------------------------------------------------------------- #

from click.testing import CliRunner  # noqa: E402

from larkdocio.cli import cli  # noqa: E402


def test_cli_no_subcommand_prints_help():
    """cli.py:39-40 — invoking the group with no subcommand echoes the help
    (invoke_without_command=True) and exits 0."""
    result = CliRunner().invoke(cli, [])
    assert result.exit_code == 0
    assert "Usage" in result.output
    assert "download" in result.output and "config" in result.output


def test_cli_config_command_passes_args_and_round_trips(monkeypatch, tmp_path):
    """cli.py:42-47 — the `config` command forwards `--appId`/`--appSecret` and the
    global `--config`/`--env-file` (via ctx.obj) into handle_config_command, and
    the real config_cmd path writes+reads the explicit --config file."""
    captured = {}
    monkeypatch.setattr(config_cmd, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(config_cmd, "get_read_credentials", lambda: ("RID", "RSEC"))
    monkeypatch.setattr(
        config_cmd, "set_env_credentials",
        lambda app_id, app_secret, env_path=None: captured.setdefault(
            "creds", (app_id, app_secret, env_path)),
    )

    cfg_path = tmp_path / "c.json"       # does not exist yet -> config writes it
    env_path = str(tmp_path / "none.env")

    result = CliRunner().invoke(cli, [
        "--config", str(cfg_path), "--env-file", env_path,
        "config", "--appId", "APPX", "--appSecret", "SECY",
    ])

    assert result.exit_code == 0, result.output
    # Arg passthrough through the click ring: appId/appSecret AND the global
    # --env-file all reached the handler (the wiring at cli.py:47 + ctx.obj).
    assert captured["creds"] == ("APPX", "SECY", env_path)
    # Round-trip: the explicit --config path was created and is readable back.
    assert cfg_path.exists()
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert "output" in data and set(data["output"]) == set(OutputConfig().to_dict())
