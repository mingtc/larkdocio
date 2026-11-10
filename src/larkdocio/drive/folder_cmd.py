"""larkdocio.drive.folder_cmd — the ``larkdocio folder`` command (LD-327).

**The CLI shape is a delegated product decision.** The commission left the shape to Dev with a
Maintainer-review line; the recorded decision (see the issue's ``## Decision``) is **a new ``folder``
verb**, paired with ``download`` refusing a folder URL by *naming* this verb. The reasoning: a
folder read produces MANY documents, so ``download``'s ``-o`` (one document plus its images)
would mean two different things on one verb — a widened contract shipped under consumers who
pinned it. A separate verb keeps ``download``'s contract untouched and gives the folder read its
own clean output shape.

**The library writes no files; this verb does.** ``read_folder`` returns a structured result and
``render_folder`` serialises it to ONE Markdown document (maintainer ruling § D5); the on-disk shape was
left to the CLI on purpose (``larkdocio.drive.read`` says so). So this command is the wiring —
credentials, the read, the render, and the one file write — and nothing about the enumeration
itself, which has its own module and its own offline suite.
"""
import json
import logging
import os

from larkdocio.common import init_env
from larkdocio.drive.assets import fetch_folder_assets
from larkdocio.drive.manifest import folder_manifest
from larkdocio.drive.read import read_folder
from larkdocio.drive.render import render_folder
from larkdocio.common.filename import compose_name

logger = logging.getLogger("larkdocio")


def handle_folder_command(url: str, output_dir: str, env_file: str = None,
                          dump: bool = False, deep_read_sheets: bool = False,
                          fidelity_read_sheets: bool = False,
                          deep_read_bases: bool = False,
                          assets: bool = False) -> None:
    """Read a whole Drive folder and write its one rendered Markdown document under ``output_dir``.

    Returns ``None`` and reports by logging. A refusal (bad URL, missing READ credentials, a
    refused root folder) is a typed :class:`~larkdocio.errors.LarkConfigError` /
    :class:`~larkdocio.drive.errors.FolderRefusedError` raised by ``read_folder`` and surfaced by
    the CLI boundary as one ``Error:`` line — this function does not catch it, so **no file is
    written on a refusal.** A single unreadable child never fails the walk (LD-326): it comes
    back disclosed in the ``## Not read`` section of the rendered document.

    ``dump`` additionally writes the **machine-readable child manifest** beside the Markdown —
    ``<folder token>.json``, the naming and placement ``download --dump`` already uses. It is
    purely additive: the Markdown a person reads is byte-identical either way.

    ``deep_read_sheets`` / ``fidelity_read_sheets`` / ``deep_read_bases`` are ``download``'s own
    opt-ins, reaching the walk unchanged (LD-384) — same spelling, same semantics, same default
    (OFF). Off, this command is byte-identical to what it has always written and makes no
    Sheets or Base API call; on, the documents inside the folder deep-read their embeds exactly
    as ``download`` does, and a per-child deep-read failure degrades to the placeholder or is
    disclosed as that child's miss without failing the walk.

    ``assets`` (LD-386) additionally pulls every document's images and whiteboard PNGs into
    **one shared token-named pool** beside the Markdown — ``<output_dir>/static/``, the
    directory name and filename shape ``download`` already produces, with the layout decision
    and the collision argument written down in :mod:`larkdocio.drive.assets`. Off by default,
    because fetching binaries across a whole folder is expensive and nobody should pay it by
    surprise; off, this command fetches nothing, creates no pool directory, and writes exactly
    the bytes ``render_folder`` produced. A per-asset failure is disclosed in Lark's own words
    (in the log and in a ``## Assets not fetched`` section) and never fails the walk.
    """
    init_env(env_file)
    result = read_folder(
        url,
        deep_read_sheets=deep_read_sheets,
        fidelity_read_sheets=fidelity_read_sheets,
        deep_read_bases=deep_read_bases,
        assets=assets,
    )
    markdown = render_folder(result)

    os.makedirs(output_dir, exist_ok=True)
    fetch = None
    if assets:
        # AFTER the render and BEFORE the write: the relink rewrites tokens in the one
        # document the folder read produces, so it must see the rendered text, and the file on
        # disk must be the relinked one — never a first write that a second pass corrects.
        markdown, fetch = fetch_folder_assets(result, markdown, output_dir)
    name = result.root_name.name if result.root_name.resolved else result.root_token
    # LD-665: composed in ONE place (`larkdocio.common.filename`), with the folder's own root
    # token joining the name when — and only when — the folder name had to be CUT. This site
    # is the sharper of the two the issue names: it carries no timestamp at all, so two
    # same-named folders written into one `-o` collided at ANY distance in time, not just
    # within a clock minute.
    composed = compose_name(name, suffix=".md", token=result.root_token)
    path = os.path.join(output_dir, composed.name)
    # Before the truncating `open`, and log-only here. The asymmetry with `download` is real
    # and deliberate rather than an oversight: this command's contract is `-> None` ("returns
    # None and reports by logging", above), so there is no result object to carry a structured
    # field on, and inventing a return value for it would be a consumer-visible surface change
    # this issue does not own. Named in the LD-665 handoff.
    replaced = os.path.exists(path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(markdown)
    if replaced:
        logger.info(
            "A file already existed at %s and was replaced — if that was not this same folder "
            "being read again, two folders have converged on one name.", path)

    if dump:
        _dump_manifest(result, output_dir)

    reads, skips = len(result.reads), len(result.skips)
    logger.info(
        "Wrote %s — %d document(s) read, %d disclosed as not read, %d folder(s) walked.",
        path, reads, skips, len(result.folders))
    for outcome in result.skips:
        logger.info("  not read: %s — %s", outcome.name or outcome.token, outcome.skip.reason)
    if fetch is not None:
        logger.info(
            "  assets: %d fetched into %s, %d not fetched.",
            len(fetch.fetched), fetch.directory, len(fetch.misses))


def _dump_manifest(result, output_dir: str) -> str:
    """Write the folder's machine-readable child manifest and return its path.

    **The convention is ``download --dump``'s, deliberately reused rather than reinvented**: the
    same flag spelling, the same ``-o`` directory as the human output, ``indent=4`` /
    ``ensure_ascii=False``, and a filename built from the **token** — ``<folder token>.json``
    beside ``download``'s ``<document token>.json``. A ledger can therefore find the sidecar
    knowing only the folder URL it asked for, without knowing (or sanitising) the folder's
    title, which is what the Markdown file is named for.

    Unlike ``download``'s dump this does **not** swallow a serialisation failure: the manifest
    is built from built-in types alone, so a failure here would be a defect in this library, not
    an unserialisable payload from Lark, and hiding it behind a warning would hand a ledger a
    silent absence.
    """
    path = os.path.join(output_dir, f"{result.root_token}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(folder_manifest(result), handle, indent=4, ensure_ascii=False)
    logger.info("Wrote the machine-readable child manifest to %s", path)
    return path
