"""@mention display-name resolution — the ONE substitution every read path shares.

**Why this module exists.** The substitution used to live inside the download pipeline
alone, so the pipeline resolved ``@ou_id`` → ``@Display Name`` while the documented
in-process read — a ``Parser`` built by hand — could not: the resolver is a method on the
read client, and a ``Parser`` had no seam to reach one through. Two read paths, one of them
structurally unable to do what the other did by default, and a consumer following the guide
got raw open ids with no explanation.

The fix is this module: **one** implementation, called from **both** seams —
:meth:`larkdocio.read.parser.Parser.parse_docx_content` (when a ``read_client`` is injected)
and the download pipeline's post-pass. Parity between the command and the documented Python
recipe is therefore structural rather than coincidental, and it is asserted byte-for-byte in
``tests/test_mention_read_path_parity.py``.

**The contract.**

* The parser stays offline by itself. It only *collects* the distinct mention open ids while
  it renders (``parser.mention_user_ids``); nothing here runs unless a caller hands over a
  client, exactly like the image-token substitution it mirrors.
* **Graceful degrade, always.** A read must never fail because of mention resolution: an id
  the contacts data range does not cover, a user whose name fields are all null, a missing
  scope, or a resolver that raises outright all leave the raw ``@ou_id`` in place. A partial
  result rewrites only the ids that resolved.
* **Deterministic within a run.** The ids arrive deduped in first-seen order and the names
  come back in a single dict, so the same document yields the same substitution set.
"""
import logging
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger("larkdocio")


def resolve_mentions(
    markdown: str,
    ids: Optional[Iterable[str]],
    client: Any,
    *,
    enabled: bool = True,
) -> str:
    """Rewrite ``@open_id`` → ``@Display Name`` in ``markdown`` for the ids that resolve.

    ``ids`` are the distinct mention open ids the parse collected; ``client`` is anything
    exposing ``batch_get_user_names(ids) -> {open_id: name}`` (the read client). With
    ``enabled=False``, with no ids, or when nothing resolves, ``markdown`` is returned
    **byte-identical** — the raw ``@ou_id`` passthrough.
    """
    if not enabled:
        return markdown

    ids = list(ids or [])
    if not ids:
        return markdown

    try:
        names: Dict[str, str] = client.batch_get_user_names(ids)
    except Exception as e:
        # Belt-and-suspenders: batch_get_user_names is already best-effort, but a mention
        # lookup must NEVER fail a read (the warn-and-continue precedent).
        logger.warning(f"Could not resolve @mention names: {e}")
        return markdown

    # Substitute the longest ids first so an id that is a prefix of another
    # (e.g. `ou_1` vs `ou_da`) can never corrupt the longer one. Each distinct id
    # rewrites all of its occurrences (a user may be mentioned more than once).
    for uid in sorted(names, key=len, reverse=True):
        markdown = markdown.replace(f"@{uid}", f"@{names[uid]}")

    return markdown
