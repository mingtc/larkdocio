"""larkdocio — Lark (Feishu) documents, spreadsheets, Bases and Drive toolkit.

One package carrying the shipped sub-packages below, plus the shared block model in
``larkdocio.blocks`` that the reader and the writer both build on (``capabilities()`` names the
surfaces they expose, one id per surface):

* ``read/`` — download a docx/wiki document and convert it to clean Markdown
  (shipped v1.0.0);
* ``write/`` — the **plan-gated writeback apply-engine** (shipped v1.6.0..v1.9.0):
  whole-paragraph and table-cell edits, insert / delete, style-preserving sub-span edits and
  Markdown authoring, every one of them ``dry_run`` → approve → ``apply``,
  exactly-one-or-refuse, with a live pre-write re-validation that refuses ``stale-anchor``
  rather than overwrite drift (see :func:`writer_brief`);
* ``sheets/`` — a standalone Sheets read + write surface (shipped v1.12.0..v1.15.0);
* ``base/`` — the Base (bitable) surface, **read plus a plan-gated write of BOTH the rows and
  the schema**: a Base's tables to titled Markdown tables (or to the structured intermediate,
  which is the source of truth), an opt-in bridge that inlines a Base embedded in a document,
  and a write engine that previews every change as a ``Plan`` before it sends one. The record
  write is ``base-write``; the **schema** write is its own surface, ``base-schema-write``, and
  it creates, renames, converts and deletes fields, tables and views, and creates, renames,
  copies and deletes the Base itself — ask ``capabilities()`` for the current operation list
  rather than trusting a count written into this paragraph. (Until 1.35 this sentence said the
  surface *did not write the schema*; it had by then done so for many releases, which is why
  the front door is now held against the registry by a test.) Reached by importing
  ``larkdocio.base``; it is deliberately **not** re-exported here,
  and there is no command-line flag for it. Facts it states rather than hides: a Flow column's
  values are returned by no read route, so those cells carry a visible absent-with-reason
  marker; people are rendered **name only** everywhere and written **by id**; and because this
  API has no compare-and-swap of its own, the write guard is client-side and says so;
* ``comments/`` — a read of the review conversation on a document or spreadsheet, resolved
  onto the block each comment is anchored to (shipped v1.16.0). A **Base's** comments come
  through this same client and entry point, with a third accepted file type, and carry the
  record / table / view the reviewer had open; creating one is refused by the server;
* ``contacts/`` — the **forward lookup**: a display name (``resolve_user``) or an email or
  mobile (``resolve_colleague``) in, **exactly one** ``open_id`` out, or a typed refusal saying
  which of *not-found* / *ambiguous* / *could-not-look* happened. The name search's measured
  reach is narrow (``larkdocio.contacts`` states it), so for another user an address is the
  route that works. The
  forward direction of the id↔name pair (the reverse lives on the reader), and the one whose
  answer is about to be written into someone else's document — so it refuses loudly where the
  reverse degrades quietly. It never fuzzy-matches, never takes the top hit, and never
  enumerates the directory to fake a name search;
* ``drive/`` — the **folder read**, plus four narrow Drive write rungs. The read: hand one
  folder link and it enumerates the tree and reads every document inside, returning a structured
  result plus one Markdown document (a tree index, each document, then a disclosure of what
  could not be read); **the walk itself issues no call on the write pair** and needs no write
  credentials. A child it cannot read is disclosed by name rather than dropped, and one
  unreadable child never fails the walk — including a raw ``file`` child, whose skip reason
  names ``DriveFilesWriteClient.download(file_token)``, the leg that **does** fetch its bytes.
  Alongside the read, on the WRITE pair and each on its own surface: one named **version**, a
  **file** into a caller-named folder, a **folder**, and **access** for a named human. Reached
  from the command line as ``larkdocio folder "<url>" -o ./out/`` or by importing
  ``larkdocio.drive``.

**What each surface supports is answered from the install, not from a file on disk:**
``capabilities()`` is the machine-readable registry — a JSON-serializable projection over the
op registries + read clients, naming every operation with its credentials and scopes, its
opt-in flags and its safety contracts. **With no argument it returns the summary**: every
surface, every operation name with its kind, and the scopes each surface is KNOWN to need —
beside a surface's scope list, ``unknown_requirements`` names the endpoints whose requirement was
never observed, so an empty scope list is never read as *needs no permission* — small enough to
read in one call and spelling the next one; ``capabilities(full=True)`` is the whole registry
and ``capabilities(surface=…)`` is one surface of it. Each surface's ``operations`` is the
complete list of its calls — one key, every kind of call, so no operation is discoverable only
by reading the source. And ``guide()`` is the human-readable matrix distilled
from it and drift-guarded against it. Neither needs a network round-trip or a source tree,
which is what the per-surface Markdown matrices kept at the root of the source repository
cannot offer a consumer holding only a wheel.

Public version is exposed as :data:`__version__` and drives the CLI's
``--version`` and the console entrypoint's reported version.

:func:`compose` / :func:`compose_insert` are the **authoring** entry point:
Markdown in our reader's own dialect → the typed creatable content an ``InsertRequest``
carries. They are re-exported here, beside :func:`capabilities` / :func:`guide`, because
authoring is a first stop for a consumer, and the complaint it answers was
discoverability; the implementation lives in ``larkdocio.write.compose``.

**Every document written for a consumer has an accessor** — the rule, and the five that keep
it: :func:`lark_setup` (the Lark-application walkthrough: the app, its scopes and its reach,
which is where a brand-new consumer starts because nothing here works until those hold),
:func:`guide` (the consumer guide), :func:`writer_brief` (the packaged ``write/README.md``,
the long-form dialect treatment the guide cites), :func:`release_notes` (the
consumer-filtered view of what changed, to read before re-pinning) and :func:`changelog`
(the project's changelog). All five read the **packaged resource**, so they work from
an installed or vendored wheel where there is no source tree to open — and
:func:`capabilities` lists them together under ``docs``, so ``dir()`` is not how a consumer
has to find them. They are also enumerated in ``larkdocio.guide``. (The wheel also carries one
contributor doc, the handler-authoring ``blocks/BLOCK_TYPES.md``, which has no accessor by
design; ``tests/test_release_notes_accessor.py`` holds the accessor set against the packaged
Markdown documents so a further *consumer* doc cannot ship unreadable-in-practice, allowing
exactly that one named exclusion.)
"""

__version__ = "1.53.2"

# Exposed AFTER ``__version__`` so the capabilities module can read it during import
# (it projects the version field off ``larkdocio.__version__``).
#
# **That order is load-bearing, and what it costs to break is the whole package, not a
# field.** ``larkdocio.capabilities`` does ``from larkdocio import __version__`` at its own
# module level, so the first submodule import below re-enters a half-initialized
# ``larkdocio``; if the assignment above sits under these imports instead, that name is not
# bound yet. **Measured by ablation (LD-629)** — with the assignment moved below this block,
# a bare ``import larkdocio`` fails outright with ``ImportError: cannot import name
# '__version__' from 'larkdocio'``, raised from ``capabilities/__init__.py``'s own
# module-level line. So: keep the assignment ABOVE the first submodule import. A tidy-up
# that reorders it does not degrade anything — it makes the library unimportable.
from larkdocio.capabilities import capabilities  # noqa: E402
from larkdocio.guide import (  # noqa: E402
    changelog, guide, lark_setup, release_notes, writer_brief,
)
# `guide_sections` is re-exported here for a reason the module path cannot solve: the name
# `larkdocio.guide` is bound to the accessor FUNCTION, so `larkdocio.guide.guide_sections`
# cannot resolve and `from larkdocio.guide import guide_sections` is the only other spelling —
# a symbol reachable only by knowing that is a discoverability failure: a public helper that
# can be found only by full-text-searching the guide.
# LD-414 generalizes this to the other packaged documents' own section indexes, for the
# identical reason: each is a sibling of the accessor function it indexes, not an attribute of
# it — and LD-549's `lark_setup_sections` joins them on the same reasoning.
from larkdocio.guide import (  # noqa: E402
    changelog_sections, guide_sections, lark_setup_sections, release_notes_sections,
    writer_brief_sections,
)
from larkdocio.write.compose import (  # noqa: E402
    compose, compose_check, compose_insert,
)

# The advisory permission pre-check. Exported as BOTH the module and its entry call because it
# was findable only through a full-text search of the guide: it was reachable
# (``larkdocio.preflight.check_permissions``), described in ``capabilities()`` and listed in the
# README's layout table, yet absent from ``__all__`` — so ``dir(larkdocio)``, ``help(larkdocio)``
# and ``from larkdocio import *`` all failed to mention it. It is **advisory and never
# mandatory**: nothing in the library calls it, and skipping it changes nothing about how a
# real denial is reported. See ``capabilities(full=True)["entry_points"]["preflight"]`` for its cost.
from larkdocio import preflight  # noqa: E402
from larkdocio.preflight import check_permissions  # noqa: E402

__all__ = [
    "__version__", "capabilities", "guide", "guide_sections", "writer_brief",
    "writer_brief_sections", "release_notes", "release_notes_sections", "changelog",
    "changelog_sections", "lark_setup", "lark_setup_sections", "compose", "compose_check",
    "compose_insert",
    "preflight", "check_permissions",
]
