"""The ``config.json`` output schema — a projection of ``OutputConfig``.

LD-244: the verbatim pre-split slice, lines 1419-1576 of the
2,770-line ``capabilities.py``. Nothing in it was rewritten.
"""
from dataclasses import dataclass
from typing import List

# --------------------------------------------------------------------------- #
# THE ``config.json`` OUTPUT SCHEMA — a projection of ``OutputConfig``, and the  #
# ONE authored copy of what each key means.                                     #
#                                                                              #
# The keys and the defaults are NOT written here: they are read off             #
# ``OutputConfig``'s own fields, so this table cannot disagree with the         #
# dataclass about what exists or what it defaults to. What IS written here is   #
# the MEANING of each key, once — and both documents that carry the schema (the #
# shipped guide a consumer can open from an installed wheel, and the repo-side  #
# CLI contract) hold a generated region byte-identical to the render below, the #
# same posture the permission matrix uses. A schema typed into two documents is #
# how a config key ends up documented two different ways.                       #
# --------------------------------------------------------------------------- #

#: What each ``output`` key in a ``config.json`` DOES, in a consumer's terms. One entry per
#: ``OutputConfig`` field; :func:`config_schema` refuses to project when the two sets differ in
#: either direction, so a new key cannot ship undocumented and a meaning cannot outlive its key.
CONFIG_KEY_MEANINGS = {
    "image_dir": (
        "Subfolder, created next to the output Markdown, that downloaded images and the "
        "flowchart / mindmap PNGs are written into. Image links in the Markdown are rewritten "
        "to point at it relatively."
    ),
    "title_as_filename": (
        "Name the output file after the document's own title, prefixed with a UTC "
        "`[YYYY-MM-DD_HHMM]_` stamp — so two downloads of the same document produce two files "
        "rather than overwriting one. When `false` the name is `<document token>.md` with no "
        "stamp at all, which is how to get a stable, repeatable filename."
    ),
    "use_html_tags": (
        "Emit HTML tags for the inline styles Markdown cannot express (`<u>` for underline). "
        "When `false` only Markdown-native styling is emitted and those styles are dropped."
    ),
    "skip_img_download": (
        "Leave image tokens unresolved: no network fetch, nothing written into the assets "
        "subfolder, and image links are not localized."
    ),
    "download_attachments": (
        "Opt in to best-effort binary download of file attachments. Default `false`: an "
        "attachment surfaces as its name+token marker and no attachment network happens at "
        "all. When `true` each queued file token is fetched into `image_dir` alongside the "
        "images, warning and continuing past a failure."
    ),
    "resolve_mentions": (
        "Resolve @mention open ids to display names at download time (`@ou_id` -> `@Name`) "
        "through the contacts batch call. A missing contacts scope, an id the directory does "
        "not cover, or a failing lookup keeps the raw `@ou_id` after one log line and never "
        "fails the read. When `false` resolution is skipped entirely and the contacts surface "
        "is never touched."
    ),
}

#: The fence that delimits the generated schema region in a document that carries it. The BEGIN
#: fence is the region's FIRST LINE VERBATIM — the HTML comment it opens is closed on the next
#: line, which carries the regeneration command — so a reader of these constants can find the
#: region with them unmodified.
CONFIG_REGION_BEGIN = "<!-- BEGIN CONFIG-SCHEMA (generated"
CONFIG_REGION_END = "<!-- END CONFIG-SCHEMA -->"

#: The one-liner that regenerates the region, quoted into the region's own header so the
#: instruction cannot drift away from the thing it regenerates.
CONFIG_REGENERATE = (
    'python -c "from larkdocio.capabilities import config_schema_markdown as m; print(m())"'
)


@dataclass(frozen=True)
class ConfigKey:
    """One ``output`` key of a ``config.json``: its name, its real default, what it does."""

    name: str
    default: object
    meaning: str

    def to_dict(self) -> dict:
        return {"name": self.name, "default": self.default, "meaning": self.meaning}


def _output_config_defaults() -> dict:
    """``{field name: declared default}`` for the read config's ``output`` object.

    The one place the projection reads the dataclass, so a test can point the projection at a
    mutated field set and observe the refusal without touching the shipped dataclass.
    """
    from larkdocio.read.config import OutputConfig

    return OutputConfig().to_dict()


def config_schema() -> List[ConfigKey]:
    """The ``config.json`` ``output`` schema, projected off ``OutputConfig``.

    Field order is the dataclass's declaration order, which is also the serialized key order of
    the shipped ``config.json``. Raises ``ValueError`` when the declared fields and the authored
    meanings disagree in either direction — a seventh field with no meaning cannot ship, and a
    meaning whose key was removed cannot linger.
    """
    defaults = _output_config_defaults()
    undocumented = [name for name in defaults if name not in CONFIG_KEY_MEANINGS]
    phantom = [name for name in CONFIG_KEY_MEANINGS if name not in defaults]
    if undocumented or phantom:
        raise ValueError(
            "the config.json output schema and its documented meanings disagree: "
            f"declared fields with no meaning {undocumented}, "
            f"meanings for fields that do not exist {phantom} "
            "(larkdocio.capabilities.CONFIG_KEY_MEANINGS is the one place to fix it)"
        )
    return [
        ConfigKey(name=name, default=default, meaning=CONFIG_KEY_MEANINGS[name])
        for name, default in defaults.items()
    ]


def config_schema_markdown() -> str:
    """The generated schema region: one row per key, plus the example file at its defaults.

    Both the shipped guide and the repo-side CLI contract carry these exact bytes, checked by
    ``tests/test_download_output_docs.py``, so the schema is authored once and read wherever the
    reader happens to be.
    """
    import json as _json

    rows = config_schema()
    lines = [
        CONFIG_REGION_BEGIN,
        f"     regenerate with:  {CONFIG_REGENERATE}  -->",
        "",
        "| Key | Default | What it does |",
        "|-----|---------|--------------|",
    ]
    for row in rows:
        lines.append(f"| `{row.name}` | `{_json.dumps(row.default)}` | {row.meaning} |")
    example = _json.dumps({"output": {row.name: row.default for row in rows}}, indent=2)
    lines += [
        "",
        "The whole file, every key at its default — which is exactly what the package ships as "
        "`larkdocio/config.json`, so omitting `--config` and passing this file are the same "
        "run:",
        "",
        "```json",
        example,
        "```",
        "",
        "Any subset is valid: a key you leave out keeps the default above, and a key the "
        "library does not know is ignored.",
        "",
        CONFIG_REGION_END,
    ]
    return "\n".join(lines)


