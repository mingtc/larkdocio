"""larkdocio.common.filename — the one place a whole on-disk filename is composed (LD-665).

**Why this module exists at all.** :mod:`larkdocio.common.sanitize` budgets a *component* — the
piece of a name derived from document-supplied text. It cannot budget the **name**, because it
cannot see what its callers wrap around that component, and it cannot notice that a cut has
made two different titles into one filename. Both of those were live:

* a title of 100+ characters was truncated, and two documents whose titles first differ past the
  cut wrote to **one** path with a truncating ``open`` — the second silently destroying the
  first (executed on the shipped tree of the day: two 102-character titles, one file, the
  first document's bytes gone, no log line, no error, exit 0);
* and the same blindness is what let a 100-**character** budget produce a 300-**byte** name
  (LD-659, fixed in the sanitizer — the composed names measure 243 B and 225 B at their worst
  cases today, both under ``NAME_MAX``).

So the budget and the disambiguation both belong where the **whole** name is known. The rule
this module states is: *when, and only when, the text was CUT, the caller's own Lark-issued
token goes into the name, and the room for it is taken out of the cut text — never out of the
extension.*

**Why the token cannot itself collide.** It is not a hash, a counter or a clock reading — it is
the identifier Lark issued for the very object being written (``doc_token`` for a document,
``root_token`` for a folder), which is the same argument :mod:`larkdocio.drive.assets` already
makes for the token-named asset pool and already guards — that guard lives **in the source repository**,
not in the wheel:
``tests/test_drive_folder_assets.py::test_ac2_two_documents_sharing_a_TITLE_cannot_collide_because_layout_is_token_named``.
Two different objects have two different tokens, so two truncated names cannot
converge; the **same** object downloaded twice has the same token and the same stem, so it
still overwrites its own file rather than accumulating copies — which is behaviour consumers
depend on and this change deliberately preserves. And the token is never itself truncated: the
stem gives up the bytes, so the part carrying the uniqueness is always whole.

**What it does not close, stated rather than claimed away.** A name that was *not* cut is
faithful and is left exactly as it was, so two documents that genuinely share a title still
share a filename — a true fact about the user's Drive that this library discloses rather than
renames behind them (LD-665 AC4). The one residual of the disambiguation itself — an *uncut*
title that happens to end in ``_`` plus another document's whole token — is not argued to be
impossible; it is covered by the same disclosure, which fires on **any** replacement.
"""
from dataclasses import dataclass

from larkdocio.common.sanitize import (
    NAME_MAX_BYTES,
    sanitize_path_string,
    truncate_to_bytes,
    truncates,
)


@dataclass(frozen=True)
class ComposedName:
    """A filename and **how it was decided** — never just the string.

    ``disambiguated`` is the fact a caller has to be able to report: it means the name on disk
    is no longer a function of the title alone, which is exactly the case where a consumer
    keying on the old shape needs to know. It is returned as data rather than logged, for the
    reason :class:`larkdocio.read.download.DownloadResult` already records: a pipeline that can
    only learn something by parsing log text is a pipeline that will parse log text.
    """

    #: The whole filename — prefix, stem, any disambiguating token, and the extension.
    name: str
    #: Was the text-derived stem CUT to fit? (Not: was it reduced. See ``sanitize.truncates``.)
    truncated: bool
    #: Did the cut cause this module to put the caller's token into the name?
    disambiguated: bool


def compose_name(source: str, *, prefix: str = "", suffix: str = "", token: str) -> ComposedName:
    """Compose ``prefix`` + a sanitized stem from ``source`` + ``suffix`` into ONE filename.

    ``suffix`` carries the extension and ``prefix`` any fixed decoration (the download's
    timestamp). Both are **reserved, never cut** — trap (i) of LD-665 AC2 is that a naive slice
    of the finished name eats the ``.md``, so the fixed parts are subtracted from the budget
    up front and only the stem is shortened.

    ``token`` is the Lark-issued identifier of the object being written. It is used **only**
    when :func:`~larkdocio.common.sanitize.truncates` says the stem was cut; an uncut name is
    returned byte-identical to what this library has always written, which is what keeps this a
    fix for a collision rather than a rename of everybody's files.

    The budget is in **bytes** and the constant is
    :data:`~larkdocio.common.sanitize.NAME_MAX_BYTES`. It is a constant on purpose rather than
    ``os.pathconf(dir, "PC_NAME_MAX")``: that call returns ``255`` on both Linux/ext4 and
    macOS/APFS and means **bytes** on the first and **characters** on the second (measured
    while minting LD-665 — 255 hanzi, 765 bytes, was created successfully on APFS and 256
    raised ``[Errno 63]``). One number, two units, so reading it buys nothing over the constant
    and adds a syscall and a failure mode. Bytes is correct on Linux and merely conservative
    elsewhere.
    """
    stem = sanitize_path_string(source)
    if not truncates(source):
        return ComposedName(f"{prefix}{stem}{suffix}", truncated=False, disambiguated=False)

    marker = f"_{token}"
    budget = NAME_MAX_BYTES - len(f"{prefix}{marker}{suffix}".encode("utf-8"))
    # A stem cut to nothing is better than a name that is over the limit, and it is not a
    # data loss: the token that replaces it identifies the document exactly. `budget < 1`
    # needs a prefix or a token far longer than anything this library composes. Rather than
    # trust that, the real call sites are MEASURED by a guard that lives **in the source repository**
    # rather than in the wheel — ``tests/test_composed_filename_budget.py`` — which is the same
    # discipline LD-659 applied to its own reserve.
    stem = truncate_to_bytes(stem, budget) if budget > 0 else ""
    return ComposedName(
        f"{prefix}{stem}{marker}{suffix}" if stem else f"{prefix}{token}{suffix}",
        truncated=True,
        disambiguated=True,
    )
