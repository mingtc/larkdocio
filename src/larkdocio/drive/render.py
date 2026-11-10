"""larkdocio.drive.render — the one-document rendering of a folder read (LD-326).

A :func:`render_folder` turns a :class:`~larkdocio.drive.read.FolderRead` into **one** Markdown
document with three regions, in this order:

1. a **tree index** a human recognises as the folder — every child by name, type and depth (the
   shape the spike printed at § VII.1);
2. each **read child's Markdown**, under its own heading;
3. a **``## Not read`` disclosure section** naming every skipped child with its reason —
   Lark's own words for a refusal. **An empty disclosure section is omitted, and its absence
   means zero misses**, so a reader can trust the section's silence.

This is a **pure function of the walk result** (AC6): the output derives only from the
:class:`FolderRead` it is handed — never from the host clock, the locale, the environment, dict
iteration order or the filesystem. Child ordering is the listing's own order, carried through
the walk's ``children`` tuple. Rendering the same result twice is byte-identical.
"""
from larkdocio.drive.read import FolderRead

_TREE_HEADING = "## Folder tree"
_DOCS_HEADING = "## Documents"
_MISS_HEADING = "## Not read"


def render_folder(result: FolderRead) -> str:
    """Render one :class:`~larkdocio.drive.read.FolderRead` to a single Markdown document."""
    lines = []
    lines += _title(result)
    lines += [""]
    lines += _tree_index(result)

    reads = result.reads
    if reads:
        lines += ["", _DOCS_HEADING]
        for outcome in reads:
            lines += ["", f"### {_display(outcome.child)}", "",
                      (outcome.markdown or "").rstrip("\n")]

    skips = result.skips
    if skips:
        lines += ["", _MISS_HEADING, ""]
        for outcome in skips:
            lines.append(f"- {_display(outcome.child)} ({_type(outcome.child)}) — "
                         f"{outcome.skip.reason}")

    return "\n".join(lines) + "\n"


def _title(result: FolderRead):
    """The document title — the folder's own name, or its token with the missing name
    disclosed (AC5). A name is never invented."""
    name = result.root_name
    if name.resolved:
        return [f"# {name.name}"]
    disclosure = name.disclosure or (
        f"Lark returned no title for {result.root_token}; named by its token, not by a title "
        "larkdocio would have to invent.")
    return [f"# {result.root_token}", "", f"> {disclosure}"]


def _tree_index(result: FolderRead):
    """The tree index: every walked child by name and type, indented by depth."""
    lines = [_TREE_HEADING, ""]
    if not result.walk.children:
        lines.append("_This folder is empty; it has no children._")
        return lines
    for walked in result.walk.children:
        indent = "  " * (walked.depth - 1)
        lines.append(f"{indent}- {_display(walked.child)} ({_type(walked.child)})")
    return lines


def _display(child) -> str:
    return child.name if child.name else child.token


def _type(child) -> str:
    return child.type if child.type else "unknown"
