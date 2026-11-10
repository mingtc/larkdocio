import json
import os
import logging
from dataclasses import KW_ONLY, dataclass, fields
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("larkdocio")

@dataclass
class OutputConfig:
    # Field order is BYTE-AFFECTING: to_dict() is json.dump'd (indent=2) to the
    # shipped config.json (Config.write_to_file), so declaration order == the
    # serialized key order. Do NOT reorder without re-pinning the byte tests.
    # Each default is declared here ONCE (from_dict derives them from the fields).
    image_dir: str = "static"
    title_as_filename: bool = True
    use_html_tags: bool = False
    skip_img_download: bool = False
    # KEYWORD-ONLY from here on (LD-704). A retired key used to sit at position 5 and is
    # gone; a caller who still passes a fifth positional meant that key, and letting the
    # argument rebind onto `download_attachments` would flip ON a NETWORK gate the maintainer
    # directive below says is never on by default — silently. So a fifth positional is
    # refused (`TypeError`), like any other argument this release does not have.
    _: KW_ONLY
    # Opt-in attachment download (LD-040). Default False: file attachments
    # (type-23, always view-wrapped) surface as the 📎 name+token marker only,
    # with ZERO network for attachments (maintainer directive — attachment binaries are
    # NEVER fetched by default). When True, the download pipeline best-effort
    # fetches each queued file token into the assets dir alongside images,
    # warn-and-continue on failure.
    download_attachments: bool = False
    # Opt-out @mention display-name resolution (LD-053). Default True (maintainer
    # directive — "pretty by default"): at download time the distinct
    # mention open_ids are resolved to display names via the contacts batch
    # API and substituted `@ou_id` → `@Name` (like image-token substitution;
    # the parser stays offline-pure). GRACEFUL DEGRADE: on a missing-scope /
    # permission error the whole run falls back to `@ou_id` after ONE info
    # log line (negative-cached), so a scope-less install stays byte-identical
    # to today. Set False to skip resolution entirely (never touch contacts).
    resolve_mentions: bool = True

    def to_dict(self) -> Dict[str, Any]:
        # Explicit ordered dict (not dataclasses.asdict) so the byte-affecting
        # key order is pinned right here — matches the field declaration order.
        return {
            "image_dir": self.image_dir,
            "title_as_filename": self.title_as_filename,
            "use_html_tags": self.use_html_tags,
            "skip_img_download": self.skip_img_download,
            "download_attachments": self.download_attachments,
            "resolve_mentions": self.resolve_mentions
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutputConfig":
        # Semantics preserved exactly: a known key present in `data` (even if
        # falsy) is used; a MISSING known key falls back to the field default;
        # unknown keys are ignored. Defaults come from the field declarations
        # (stated once) — absent keys are simply not passed to the constructor.
        #
        # A key retired in an earlier release is an unknown key like any other (LD-704): an
        # existing consumer's config.json carrying one still loads, and the key is ignored.
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


class Config:
    def __init__(self, output: Optional[OutputConfig] = None):
        self.output = output or OutputConfig()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output": self.output.to_dict()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        return cls(
            output=OutputConfig.from_dict(data.get("output", {}))
        )

    def write_to_file(self, config_path: str):
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

def new_config() -> Config:
    return Config(
        output=OutputConfig()
    )

def get_base_dir() -> Path:
    """Return the ``larkdocio`` package directory (parent of the ``read`` package).

    The default ``config.json`` ships as package data alongside the package
    modules, so it resolves relative to this directory whether the package is
    run from a source checkout or an installed wheel.
    """
    return Path(__file__).resolve().parent.parent

def get_default_config_path() -> str:
    """Default config file, shipped as package data in the larkdocio package."""
    return str(get_base_dir() / "config.json")

def read_config_from_file(config_path: str) -> Config:
    """Load a :class:`Config` from ``config_path``; return the defaults if it is not there.

    A missing file is not an error — it is the ordinary case, and the defaults are the same
    ones the shipped ``config.json`` carries. A file that IS there but is not valid JSON
    raises, because a typo'd config silently ignored is how a reader stops honouring settings.
    """
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return Config.from_dict(data)
    else:
        return new_config()
