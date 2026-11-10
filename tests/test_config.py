"""Config round-trip + the exposed output switches (LD-016).

Pins:
* **AC1 (net):** ``OutputConfig``/``Config`` ``to_dict``/``from_dict`` round-trip and
  ``read_config_from_file`` (existing-file read + missing-file fallback to defaults).
* **AC3 (B4):** ``title_as_filename`` is an exposed switch in ``to_dict``/``from_dict``
  (default ``True`` → byte-identical default posture).

**LD-650 NARROWED THIS MODULE, IT DID NOT EMPTY IT.** The other half of the B4 pair was a
key that switched off an output-relocating derivation; LD-650 retired the derivation, and
LD-704 (absorbing LD-674) retired the key's one-release tolerance. Every arm whose subject was
the ROUND TRIP kept its subject and lost one key; the arms whose subject was the tolerance now
hold the rule that replaced it — **a retired key is an UNKNOWN key**: ignored in a
``config.json`` like any other, refused (``TypeError``) as a constructor keyword or a fifth
positional argument, and never rebound onto the field that used to sit after it.
"""
import dataclasses
import json
import os
from types import SimpleNamespace

import pytest

import private_tree

from larkdocio.read import download
from larkdocio.read.config import (
    Config,
    OutputConfig,
    new_config,
    read_config_from_file,
)

#: An ordinary document body for the end-to-end arms below: a key/value table whose cells
#: could be read as directory names, ON PURPOSE (LD-650) — the library never relocates output
#: off a document's contents, so such a document is treated like any other and lands flat.
BODY_MD = "| Area | Sales |\n| Section | Billing |\n| Topic | Invoices |\n"


# --------------------------------------------------------------------------- #
# AC1 + AC3 — OutputConfig round-trip (both B4 switches serialized)            #
# --------------------------------------------------------------------------- #

def test_output_config_defaults_include_all_switches():
    """Default ``to_dict()`` carries today's defaults incl. both B4 switches
    (byte-identical default posture)."""
    assert OutputConfig().to_dict() == {
        "image_dir": "static",
        "title_as_filename": True,
        "use_html_tags": False,
        "skip_img_download": False,
        "download_attachments": False,
        "resolve_mentions": True,
    }


def test_output_config_to_dict_exposes_the_surviving_b4_switch():
    """AC3: ``title_as_filename`` is present in the serialized form — and nothing but the
    declared fields is (the retired other half of the B4 pair left with LD-650 and LD-704)."""
    d = OutputConfig().to_dict()
    assert "title_as_filename" in d
    assert set(d) == {f.name for f in dataclasses.fields(OutputConfig)}


def test_output_config_from_dict_round_trips_all_fields():
    src = {
        "image_dir": "assets",
        "title_as_filename": False,
        "use_html_tags": True,
        "skip_img_download": True,
        "download_attachments": True,
        "resolve_mentions": False,
    }
    oc = OutputConfig.from_dict(src)
    assert oc.image_dir == "assets"
    assert oc.title_as_filename is False
    assert oc.use_html_tags is True
    assert oc.skip_img_download is True
    assert oc.download_attachments is True
    assert oc.resolve_mentions is False
    assert oc.to_dict() == src


def test_an_older_config_json_with_a_RETIRED_key_still_loads_and_the_key_is_ignored(caplog):
    """TRANSFORMED, not deleted (LD-650 → LD-704). The back-compat property a consumer depends
    on: the file they already have on disk keeps loading, every known key still lands, and a
    key this release no longer knows is ignored like any other unknown key — no special case,
    no notice. The real retired name is held by the private-ledger arm below; this arm uses a
    stand-in because the rule, not the name, is the subject."""
    with caplog.at_level("WARNING", logger="larkdocio"):
        oc = OutputConfig.from_dict({"image_dir": "static", "a_retired_switch": False})
    assert oc.image_dir == "static"
    assert oc.title_as_filename is True
    assert "a_retired_switch" not in oc.to_dict()
    assert not hasattr(oc, "a_retired_switch")
    assert not [r for r in caplog.records if r.name == "larkdocio"], (
        "an unknown key is ignored in silence — the tolerance notice was discharged (LD-704)")


# --------------------------------------------------------------------------- #
# LD-040 (AC4) — download_attachments additive knob (default False)           #
# --------------------------------------------------------------------------- #

def test_output_config_default_download_attachments_is_false():
    """AC4: the knob defaults False — attachments are NEVER fetched by default
    (maintainer directive). Default ``to_dict()`` surfaces it as ``false``."""
    assert OutputConfig().download_attachments is False
    assert OutputConfig().to_dict()["download_attachments"] is False


def test_output_config_from_dict_defaults_missing_download_attachments_to_false():
    """An older ``config.json`` without the key defaults to False (additive switch,
    byte-identical default posture — no attachment network unless opted in)."""
    oc = OutputConfig.from_dict({"image_dir": "static"})
    assert oc.download_attachments is False


def test_output_config_download_attachments_round_trips_true():
    """When explicitly enabled it survives a ``to_dict``/``from_dict`` round-trip."""
    oc = OutputConfig.from_dict({"download_attachments": True})
    assert oc.download_attachments is True
    assert oc.to_dict()["download_attachments"] is True


# --------------------------------------------------------------------------- #
# LD-053 (AC1) — resolve_mentions additive knob (default TRUE per maintainer)          #
# --------------------------------------------------------------------------- #

def test_output_config_default_resolve_mentions_is_true():
    """AC1: the knob defaults **True** (maintainer directive: pretty by default). Default
    ``to_dict()`` surfaces it as ``true``. Graceful-degrade keeps a scope-less
    install byte-identical (falls back to ``@ou_id`` + one log line)."""
    assert OutputConfig().resolve_mentions is True
    assert OutputConfig().to_dict()["resolve_mentions"] is True


def test_output_config_from_dict_defaults_missing_resolve_mentions_to_true():
    """An older ``config.json`` without the key defaults to True (additive switch,
    matching the maintainer's default-TRUE directive)."""
    oc = OutputConfig.from_dict({"image_dir": "static"})
    assert oc.resolve_mentions is True


def test_output_config_resolve_mentions_round_trips_false():
    """When explicitly disabled it survives a ``to_dict``/``from_dict`` round-trip."""
    oc = OutputConfig.from_dict({"resolve_mentions": False})
    assert oc.resolve_mentions is False
    assert oc.to_dict()["resolve_mentions"] is False


# --------------------------------------------------------------------------- #
# AC1 — Config round-trip + new_config default posture                        #
# --------------------------------------------------------------------------- #

def test_config_to_from_dict_round_trip():
    cfg = Config(OutputConfig(title_as_filename=False))
    d = cfg.to_dict()
    assert d == {
        "output": {
            "image_dir": "static",
            "title_as_filename": False,
            "use_html_tags": False,
            "skip_img_download": False,
            "download_attachments": False,
            "resolve_mentions": True,
        }
    }
    assert Config.from_dict(d).to_dict() == d


def test_new_config_matches_default_config():
    """Default posture unchanged: ``new_config`` == default ``Config``."""
    assert new_config().to_dict() == Config().to_dict()


# --------------------------------------------------------------------------- #
# AC1 — read_config_from_file                                                 #
# --------------------------------------------------------------------------- #

def test_read_config_from_existing_file(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(
        json.dumps({"output": {"image_dir": "imgs", "title_as_filename": False}}),
        encoding="utf-8",
    )
    cfg = read_config_from_file(str(p))
    assert cfg.output.image_dir == "imgs"
    assert cfg.output.title_as_filename is False


def test_read_config_from_missing_file_returns_defaults_without_creating_it(tmp_path):
    missing = tmp_path / "nope.json"
    cfg = read_config_from_file(str(missing))
    assert cfg.to_dict() == new_config().to_dict()
    # Reading a missing config must never create it (read-only fallback).
    assert not missing.exists()


# --------------------------------------------------------------------------- #
# LD-650 — NO config key gates output placement any more, and the end-to-end     #
# proof is that a body which USED to self-route no longer does.                 #
# --------------------------------------------------------------------------- #

DOCX_URL = "https://example.larksuite.com/docx/AbCdEfG123"


class _StubClient:
    def get_docx_content(self, doc_token):
        return SimpleNamespace(title="Doc", document_id="D"), []

    def download_image(self, *a, **k):  # pragma: no cover - not reached (no tokens)
        raise AssertionError("no images expected")

    def download_board_image(self, *a, **k):  # pragma: no cover - not reached
        raise AssertionError("no boards expected")


class _StubParser:
    def __init__(self, config):
        self.img_tokens = []
        self.board_tokens = []

    def parse_docx_content(self, document_id, blocks):
        return BODY_MD


def _patch_pipeline(monkeypatch):
    monkeypatch.setattr(download, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(download, "get_read_credentials", lambda: ("id", "sec"))
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient())
    monkeypatch.setattr(download, "Parser", lambda config: _StubParser(config))


def test_a_document_carrying_the_old_metadata_rows_lands_FLAT(monkeypatch, tmp_path):
    """TRANSFORMED, not deleted (LD-650) — the pair of end-to-end arms that proved the gate
    worked in both positions now proves the gate is GONE. The body is the one that used to
    self-route into ``sales/billing/invoices``; it must land in ``-o`` like any other
    document, and nothing may exist at the derived path."""
    _patch_pipeline(monkeypatch)
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"output": {}}), encoding="utf-8")
    out = tmp_path / "out"

    result = download.handle_download_command(DOCX_URL, str(out), "", False, str(cfg))

    assert list(out.glob("*.md")), "markdown should be written at the base dir"
    assert not (out / "sales").exists(), "no derivation may survive"
    assert result.output_dir == str(out)
    assert result.routed is False and result.route_reason == download.ROUTE_DISABLED


def test_a_stale_config_carrying_the_retired_key_changes_NOTHING(monkeypatch, tmp_path):
    """The consumer who switched the feature off years ago and never touched their file:
    their run must behave exactly like the one above — not raise, and not relocate. A
    stand-in key: the rule is the same for every unknown key, and the real name is held by the
    private-ledger census below."""
    _patch_pipeline(monkeypatch)
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"output": {"a_retired_switch": False}}), encoding="utf-8")
    out = tmp_path / "out"

    result = download.handle_download_command(DOCX_URL, str(out), "", False, str(cfg))

    assert list(out.glob("*.md")) and not (out / "sales").exists()
    assert result.output_dir == str(out)


# --------------------------------------------------------------------------- #
# LD-081 — OutputConfig → @dataclass. CHARACTERIZATION + BYTE-PIN.             #
#                                                                             #
# `Config.to_dict()` is `json.dump`'d (indent=2) to the shipped `config.json` #
# (write_to_file), so the serialized KEY ORDER is byte-affecting. These pins  #
# were authored BEFORE the dataclass conversion and must stay byte-identical  #
# after it (the refactor is behavior-preserving on the serialized artifact).  #
# --------------------------------------------------------------------------- #

# The exact, order-sensitive key sequence of OutputConfig's SERIALIZED form.
LD081_KEY_ORDER = [
    "image_dir",
    "title_as_filename",
    "use_html_tags",
    "skip_img_download",
    "download_attachments",
    "resolve_mentions",
]

# The DECLARED FIELD order is the serialized order again (LD-704 discharged the retired
# placeholder that held position 5). It is pinned separately because it is load-bearing for a
# different reason: the first four are POSITIONAL parameters, and a caller who wrote
# `OutputConfig("static", True, False, False, True)` meant the retired key by that fifth
# argument. With the placeholder gone it must NOT rebind onto `download_attachments` — a
# network gate the maintainer directive says is never on by default — so every field after
# the fourth is KEYWORD-ONLY and the fifth positional is refused (`TypeError`).
LD650_FIELD_ORDER = list(LD081_KEY_ORDER)
POSITIONAL_FIELDS = LD081_KEY_ORDER[:4]

# Exact bytes `json.dump(Config().to_dict(), f, indent=2)` writes to config.json
# for a DEFAULT config (mirrors the shipped src/larkdocio/config.json).
LD081_DEFAULT_CONFIG_JSON = (
    "{\n"
    '  "output": {\n'
    '    "image_dir": "static",\n'
    '    "title_as_filename": true,\n'
    '    "use_html_tags": false,\n'
    '    "skip_img_download": false,\n'
    '    "download_attachments": false,\n'
    '    "resolve_mentions": true\n'
    "  }\n"
    "}"
)

# Exact bytes for a FULLY-CUSTOMIZED OutputConfig (every field flipped off its
# default), dumped the same way OutputConfig is embedded in config.json.
LD081_CUSTOM_OUTPUT_JSON = (
    "{\n"
    '  "image_dir": "assets",\n'
    '  "title_as_filename": false,\n'
    '  "use_html_tags": true,\n'
    '  "skip_img_download": true,\n'
    '  "download_attachments": true,\n'
    '  "resolve_mentions": false\n'
    "}"
)


def test_ld081_output_config_to_dict_key_order_is_pinned():
    """B1: the serialized key order is exactly this sequence (byte-affecting)."""
    assert list(OutputConfig().to_dict().keys()) == LD081_KEY_ORDER


def test_ld081_default_config_json_bytes_are_byte_identical():
    """B1: default Config serializes to the exact config.json bytes."""
    assert json.dumps(Config().to_dict(), indent=2) == LD081_DEFAULT_CONFIG_JSON


def test_ld081_write_to_file_default_bytes_are_byte_identical(tmp_path):
    """B1: the on-disk artifact write_to_file produces is byte-identical, and
    matches the shipped default config.json (no trailing newline)."""
    p = tmp_path / "config.json"
    Config().write_to_file(str(p))
    assert p.read_text(encoding="utf-8") == LD081_DEFAULT_CONFIG_JSON


def test_ld081_fully_customized_output_config_bytes_are_byte_identical():
    """B1: a fully-customized OutputConfig serializes byte-identically."""
    oc = OutputConfig(
        image_dir="assets",
        title_as_filename=False,
        use_html_tags=True,
        skip_img_download=True,
        download_attachments=True,
        resolve_mentions=False,
    )
    assert json.dumps(oc.to_dict(), indent=2) == LD081_CUSTOM_OUTPUT_JSON


def test_ld081_from_dict_missing_keys_use_field_defaults():
    """B2/B3: an empty dict yields every field at its default (missing → default)."""
    assert OutputConfig.from_dict({}).to_dict() == OutputConfig().to_dict()


def test_ld081_from_dict_ignores_unknown_keys():
    """B2: unknown keys are ignored — never set as attributes, never leak into
    the serialized form; known keys still take their supplied values."""
    oc = OutputConfig.from_dict(
        {"image_dir": "x", "bogus": 123, "resolve_mentions": False, "nope": "q"}
    )
    assert oc.image_dir == "x"
    assert oc.resolve_mentions is False
    assert not hasattr(oc, "bogus")
    assert not hasattr(oc, "nope")
    assert oc.to_dict() == {
        "image_dir": "x",
        "title_as_filename": True,
        "use_html_tags": False,
        "skip_img_download": False,
        "download_attachments": False,
        "resolve_mentions": False,
    }


def test_ld081_from_dict_present_falsy_values_are_preserved_not_defaulted():
    """B2: a present-but-falsy value is kept (get/membership defaults only on a
    MISSING key, never on a falsy one) — guards the semantics across the rewrite."""
    oc = OutputConfig.from_dict(
        {"image_dir": "", "title_as_filename": False, "use_html_tags": False}
    )
    assert oc.image_dir == ""
    assert oc.title_as_filename is False
    assert oc.use_html_tags is False


def test_ld081_output_config_is_a_dataclass_with_pinned_field_order():
    """The refactor's intent: OutputConfig is a @dataclass whose fields carry
    their defaults once, declared in the exact byte-affecting order."""
    assert dataclasses.is_dataclass(OutputConfig)
    assert [f.name for f in dataclasses.fields(OutputConfig)] == LD650_FIELD_ORDER


def test_the_fields_after_the_fourth_are_KEYWORD_ONLY():
    """TRANSFORMED (LD-650 → LD-704). The retired placeholder held position 5 so that a fifth
    positional could not rebind onto the attachment gate; the placeholder is gone, and the same
    guarantee is now held by the signature itself: positional parameters stop after the fourth
    field. Reddens if a later field becomes positional again."""
    import inspect

    params = list(inspect.signature(OutputConfig).parameters.values())
    positional = [p.name for p in params
                  if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD]
    keyword_only = [p.name for p in params if p.kind is inspect.Parameter.KEYWORD_ONLY]
    assert positional == POSITIONAL_FIELDS, positional
    assert keyword_only == LD081_KEY_ORDER[4:], keyword_only


def test_a_FIFTH_POSITIONAL_argument_is_REFUSED_never_rebound_onto_the_attachment_gate():
    """The executed proof, on the call an existing consumer may still have written. Before
    LD-650 fixed the shape, `OutputConfig("static", True, False, False, True)` answered
    `download_attachments is True` — a silent network-gate flip. Now that the retired key is
    gone the call names something this release does not have, so it is refused like any other
    unknown argument, whatever the value."""
    for value in (True, False):
        with pytest.raises(TypeError):
            OutputConfig("static", True, False, False, value)
    assert OutputConfig("static", True, False, False).download_attachments is False


# --------------------------------------------------------------------------- #
# LD-704 (absorbs LD-674) — THE RETIRED KEY IS AN UNKNOWN KEY AT EVERY DOOR.     #
#                                                                              #
# LD-650 tolerated it for one release with a notice at four doors (config.json, #
# constructor keyword, positional, attribute assignment); the window was        #
# extended three times. Discharged: no door special-cases it. config.json       #
# ignores it like any unknown key (test_ld081_from_dict_ignores_unknown_keys),  #
# the constructor refuses it like any unknown keyword, and the positional door  #
# is closed by the keyword-only signature above.                                #
# --------------------------------------------------------------------------- #

def _larkdocio_warnings(caplog, call):
    caplog.clear()
    with caplog.at_level("WARNING", logger="larkdocio"):
        call()
    return [r.message for r in caplog.records if r.name == "larkdocio"]


def _doors_for(key):
    def _keyword():
        with pytest.raises(TypeError):
            OutputConfig(**{key: False})

    def _assign():
        cfg = OutputConfig()
        setattr(cfg, key, False)
        assert key not in cfg.to_dict(), "an assigned unknown attribute must not serialize"

    return {
        "config.json (from_dict)": lambda: OutputConfig.from_dict({key: False}),
        "constructor keyword (refused)": _keyword,
        "attribute assignment (inert)": _assign,
    }


def test_an_unknown_key_meets_the_same_rule_at_every_door(caplog):
    """The rule, on a stand-in: ignored in config.json, refused as a keyword, inert as an
    attribute — and silent everywhere (no notice names it)."""
    counts = {name: _larkdocio_warnings(caplog, call)
              for name, call in _doors_for("a_retired_switch").items()}
    assert counts == {name: [] for name in counts}, counts


@private_tree.dev_record
def test_the_REAL_retired_key_is_no_longer_special_cased_at_any_door(caplog):
    """The same census on the real retired name, read from the private ledger (the public tree
    does not carry it — `D-121` (8)). Reddens if any door regrows a tolerance for it."""
    from retired_particulars import load

    import larkdocio.read.config as config_module

    for key in load("retired_output_keys"):
        assert key not in {f.name for f in dataclasses.fields(OutputConfig)}, key
        counts = {name: _larkdocio_warnings(caplog, call)
                  for name, call in _doors_for(key).items()}
        assert counts == {name: [] for name in counts}, (key, counts)
        assert key not in open(config_module.__file__, encoding="utf-8").read(), (
            f"read/config.py still names the retired key {key!r}")


def test_no_construction_logs_anything(caplog):
    """The other direction, kept from the LD-650 census: ordinary constructions are silent."""
    quiet = {
        "default construction": lambda: OutputConfig(),
        "one positional": lambda: OutputConfig("static"),
        "four positional": lambda: OutputConfig("static", True, False, False),
        "keywords only": lambda: OutputConfig(image_dir="x", resolve_mentions=False),
        "from_dict": lambda: OutputConfig.from_dict({"image_dir": "x"}),
        "the whole Config": lambda: Config(),
        "dataclasses.replace": lambda: dataclasses.replace(OutputConfig(), image_dir="y"),
    }
    counts = {name: _larkdocio_warnings(caplog, call) for name, call in quiet.items()}
    assert counts == {name: [] for name in quiet}, counts
