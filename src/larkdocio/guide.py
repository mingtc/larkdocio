"""larkdocio.guide — the accessors for every document written for a consumer.

Six Markdown documents ship inside the wheel. Five are written for a consumer, and each has
an accessor here: :func:`guide` (the consumer guide), :func:`writer_brief` (the writer's
long-form brief), :func:`release_notes` (the consumer-filtered view of what changed),
:func:`changelog` (the project's changelog) and :func:`lark_setup` (the Lark-application
walkthrough — the ten minutes before a first download). Every one of them is read from the
**packaged resource** via ``importlib.resources`` — never a filesystem path — so it resolves
identically from a source checkout and from an installed/vendored wheel where no ``src/`` tree
exists. The sixth, ``blocks/BLOCK_TYPES.md``, is a **contributor** doc (how to add a block
handler to this repo's registry) and deliberately has no accessor — its audience holds the source
repository, the same reasoned exclusion the front-door consumer corpus already makes for it.

**The rule this module exists to keep:** a document *written for a consumer* that the wheel
carries but the public API cannot open is unreadable in practice. A consumer who installed
the wheel has no ``src/`` tree to browse, and a citation inside shipped text that names a
file rather than an accessor is a pointer they cannot follow. So: ship a consumer document,
ship its accessor — enforced by ``tests/test_release_notes_accessor.py``, which holds this
table against the packaged Markdown set minus a named, reasoned contributor-doc exclusion.

The guide distils :func:`larkdocio.capabilities` into a human-readable capability matrix,
carries the canonical copy-paste recipes (download docx→MD, read sheet→MD, the docx +
sheets write handshakes, creds/`.env` setup), and is drift-guarded against
``capabilities()`` by ``tests/test_guide.py`` so it cannot silently diverge from code.

**Section-level access, and why there is no registry.** The guide is one string and that
string is over 200 KB, so a caller who wants one recipe should not have to hold the whole
document. :func:`guide` therefore takes an optional ``section``, and :func:`guide_sections`
returns the index of what can be asked for. Both are **derived from the packaged document at
call time** by reading its own headings — there is no list of section names in this package,
in ``capabilities`` or in any docstring, because a list is a second copy and a second copy
rots. It is the same posture the per-block-type support projection inside
``larkdocio.capabilities`` states for its own table: a join, not a list. The concrete
consequence is that editing the document is the only way to change the index, and doing so
needs no code change at all.

**The seam was built generically and originally wired to only the guide; it now covers every
packaged consumer document** — :func:`writer_brief`, :func:`release_notes` and
:func:`changelog` all take the same ``section``, each with its own ``<accessor>_sections()``
index, through the exact ``_section_text`` / ``_bounded_sections`` machinery below rather than
a second implementation. The one thing that differs per document is **which heading levels are
indexed**, because that is a fact about each document's own structure, not a design choice
repeated per caller: the writer brief reuses the guide's ``(2, 3)``, while the release notes
and the changelog are indexed at ``(2,)`` alone, because both repeat the same ``###``
subsection headings under every release and an index that tried to name those individually
would refuse at build time on every call (see :data:`RELEASE_NOTES_SECTION_LEVELS`).
"""
import importlib.resources as _resources
import re as _re
import textwrap as _textwrap
from typing import Optional, Tuple

#: The packaged guide's resource name, relative to the ``larkdocio`` package root.
GUIDE_RESOURCE = "GUIDE.md"

#: The packaged **writer brief**'s resource name, relative to ``larkdocio.write``.
WRITER_BRIEF_PACKAGE = "larkdocio.write"
WRITER_BRIEF_RESOURCE = "README.md"

#: The two packaged **release documents**' resource names, relative to the ``larkdocio``
#: package root. Each is a byte-identical in-package copy of the canonical repository file;
#: the copy is what ``package-data`` can carry into the wheel.
RELEASE_NOTES_RESOURCE = "RELEASE_NOTES.md"
CHANGELOG_RESOURCE = "CHANGELOG.md"

#: The packaged **Lark-application walkthrough**'s resource name, relative to the ``larkdocio``
#: package root. Like the two release documents it is an in-package copy of a canonical
#: repository file at the root — the location a reader browsing the publishing repository finds
#: it in — because ``package-data`` can only carry what lives inside a package directory. Unlike
#: them the copy is the WHOLE document rather than a window: nothing in a setup walkthrough goes
#: out of date by being old, so there is nothing to trim and the projection is the identity
#: (see :func:`packaged_projection`).
LARK_SETUP_RESOURCE = "LARK_SETUP.md"


def _packaged(resource: str, package: str = "larkdocio") -> str:
    """Read a packaged Markdown resource as text — the one mechanism every accessor uses."""
    return _resources.files(package).joinpath(resource).read_text(encoding="utf-8")


#: The heading levels the guide's section index covers. Both, deliberately — and **the reason
#: changed with LD-541 while the levels did not.** It used to be a rescue: the guide's largest
#: ``##`` section was three quarters of the document, so a ``##``-only index would have
#: answered nearly every ask with most of the guide. That is no longer true — the recipe list
#: is grouped by consumer task, one ``##`` per task, and the largest ``##`` section is 22.5% of
#: the document (measured 2026-08-21 on this file's own copy, by line count between ``##``
#: boundaries). Both levels stay because each is now a thing a caller really asks for: a
#: ``##`` group is *"the recipes for this task"* and a ``###`` is *"this one recipe"*. The
#: boundary rule below generalizes to nesting for free, so a ``##`` name returns that whole
#: section *including* its ``###`` children while a ``###`` name returns just that one.
GUIDE_SECTION_LEVELS = (2, 3)

#: The writer brief's own census (measured at LD-414's mint, ``write/README.md``, 715 lines):
#: 9 ``##`` headings and 5 ``###`` headings, none of them slug-colliding. Small enough that a
#: ``##``-only index would already be useful, but the guide's own reasoning still applies —
#: reuse it rather than fork it.
WRITER_BRIEF_SECTION_LEVELS = (2, 3)

#: The Lark-application walkthrough's levels — the guide's ``(2, 3)``, **reused rather than
#: forked**, on the same reasoning the writer brief states for itself. At LD-549's landing the
#: document had ``##`` headings only, so ``(2, 3)`` and ``(2,)`` indexed the same rows; reusing
#: the pair is what made its later ``###`` steps addressable the moment they were written. (The
#: count is not restated here: it changes with the document.) The release documents' divergence
#: to ``(2,)`` is driven by their repeated per-release subsection headings, which this document
#: has none of.
LARK_SETUP_SECTION_LEVELS = (2, 3)

#: The release notes' and the changelog's own census (LD-414's mint) is the reason these two
#: DIVERGE from ``(2, 3)`` rather than reusing it. Both documents repeat the SAME ``###``
#: subsection headings under every release — ``### New capabilities``, ``### Behavior changes
#: you can observe``, ``### Upgrade & compatibility``, ``### Known limitations`` for the notes;
#: ``### Added`` / ``### Changed`` / ``### Fixed`` for the changelog — dozens of times over. An
#: index at ``(2, 3)`` would therefore find the SAME slug on every release and refuse at
#: index-build time on every single call (measured: 94 real headings in the notes at ``(2, 3)``,
#: with ``### New capabilities`` alone repeated 16 times; 117 in the changelog, ``### Added``
#: repeated 24 times) — the "collisions raise" contract this module already keeps, applied
#: faithfully, makes ``(2, 3)`` unusable here rather than merely imprecise. The ``## [X.Y.Z] —
#: date`` release headers, by contrast, are each unique by construction (20 in the notes, 34 in
#: the changelog, zero collisions measured) and a release IS the granularity the problem this
#: issue names asks for — *"what changed in 1.32"* takes the whole release, subsections
#: included by the boundary rule, with no third level exposed.
RELEASE_NOTES_SECTION_LEVELS = (2,)
CHANGELOG_SECTION_LEVELS = (2,)

#: **The number of release sections the WHEEL's copy of the CHANGELOG carries** — the newest
#: ``CHANGELOG_WINDOW_SECTIONS`` of them, oldest-first dropped. The repository's own copy stays
#: complete; only the packaged projection is windowed, and an exact byte-level equality against
#: that projection is what holds the two to each other.
#:
#: **How 8 was derived, so the next reader can re-derive it rather than trust it.** The reader
#: this copy exists for is whoever is deciding whether to re-pin: the consumer refresh script
#: reads the REPOSITORY's copy out of a cloned tag tree, never this one, so the in-wheel copy is
#: read by someone holding an installed wheel and nothing else.
#:
#: * **The largest update gap this project can evidence is six releases behind — SEVEN
#:   sections.** A six-release jump that could not see what changed is why these documents are
#:   packaged in the wheel at all (LD-164's back-fill of that span, then LD-165). Reading "what changed" across a six-release jump needs those six
#:   sections, and one more to re-read the release they were on: **seven sections** — and the notes begin at 1.14.0, so
#:   all seven exist. The three-release move on record is **four sections** by the
#:   same count: the second largest, not the largest.
#: * **The search is named rather than a "no longer gap exists anywhere" universal asserted**
#:   (a negative universal dies with its enumeration): searched 2026-08-21 across
#:   the maintainers' own records of consumer reports and the issues citing them.
#:   A gap recorded outside that reach would move this number, which is why the reach is stated.
#: * **The measured cadence over the 19 days to 2026-08-20 was 12 releases** (1.25.0 on
#:   2026-08-01 through 1.37.0 on 2026-08-20) — about 0.63 releases a day. That is the representative
#:   window rather than the whole history: by the same count (releases after the anchor, over
#:   the days between the two anchor dates) the 24 from 1.0.0 on 2026-07-23 to 1.24.0 on
#:   2026-08-01 landed in 9 days — 2.67 a day, **four times** the current rate — an opening
#:   burst a window sized for future readers should not be sized on.
#: * **8 sections is ONE section more than the evidenced worst case: a ×1.14 margin, not a
#:   comfortable multiple**, and about thirteen days at the measured cadence. Eight sections name
#:   every reader up to **seven releases behind**; a reader further behind than that is refused
#:   by name and pointed at the full history.
#: * **Why ×1.14 is enough HERE, and why 8 was KEPT once the worst case was corrected upward:**
#:   the six-release gap arose when the wheel carried NO notes at all, and this design does
#:   not restore that state — the repository's copies stay COMPLETE and the consumer refresh
#:   script drops the full history beside the vendored wheel on every refresh, so a reader
#:   that far behind is served by the root copy. This window serves only someone
#:   reading from inside an installed wheel with no refresh drop to hand, and every section
#:   added to it is subtracted from the shrink the window exists for. So the margin is stated
#:   honestly instead of enlarged.
#:
#: **What would change it:** a gap longer than seven sections actually recorded (this constant is
#: floored on evidence, not on imagination), or a cadence measurement that moves far enough that
#: eight sections stop spanning a plausible gap. Re-derive from the same steps; do not nudge it.
CHANGELOG_WINDOW_SECTIONS = 8

#: **The number of release sections the WHEEL's copy of the RELEASE NOTES carries.** Same value
#: as ``CHANGELOG_WINDOW_SECTIONS`` and **deliberately its own constant**, because the two
#: documents are not mirrors and a shared constant would hide the day they need different
#: windows.
#:
#: **Why the same number, stated rather than assumed.** Both documents carry one section per
#: release with no gaps — the changelog from 1.0.0, the notes from 1.14.0, measured 2026-08-21
#: (39 and 25 contiguous release sections, zero gaps in either) — so the newest eight
#: of each are **the same eight releases**. One number therefore means a reader who opens both
#: gets a matched pair rather than a lopsided one: every release the filtered view names, the
#: changelog beside it records, and vice versa. (Superseded in part from 1.53.0: the shipped
#: changelog is now the public one, which starts at 1.52.0, so it holds fewer than eight
#: sections and the pairing holds only for the releases it records; the notes' window is
#: unchanged.) The derivation above is a fact about the
#: READER's update gap, which is one fact, not two — what differs between these documents is
#: what a section contains, not how far back the reader needs to look.
RELEASE_NOTES_WINDOW_SECTIONS = 8

#: ``{resource: window size}`` — the lookup the projection and its guard share, so neither
#: writes a number of its own. The values are the two constants above; this is an index of
#: them, never a second copy.
NOTES_WINDOW_SECTIONS = {
    CHANGELOG_RESOURCE: CHANGELOG_WINDOW_SECTIONS,
    RELEASE_NOTES_RESOURCE: RELEASE_NOTES_WINDOW_SECTIONS,
}

#: ``{resource: the heading levels its release sections sit at}`` — the same two constants the
#: accessors index with, so the projection cuts on exactly the boundaries ``section=`` resolves.
NOTES_WINDOW_LEVELS = {
    CHANGELOG_RESOURCE: CHANGELOG_SECTION_LEVELS,
    RELEASE_NOTES_RESOURCE: RELEASE_NOTES_SECTION_LEVELS,
}

#: ``{resource: where the FULL history lives}`` — two openable addresses per document, named in
#: the packaged copy's own banner and repeated by the out-of-window refusal. Both are paths a
#: reader can open: the first is dropped beside the vendored wheel by the consumer refresh
#: script on every refresh, the second is the canonical file in the repository that publishes
#: this wheel. "The git history" is deliberately not among them — a history is not an address.
NOTES_FULL_HISTORY = {
    CHANGELOG_RESOURCE: (
        "`vendor/larkdocio-CHANGELOG.md`, which the consumer refresh script drops beside the "
        "vendored wheel on every refresh, and the publishing repository's own complete copy of "
        "this document at its root"
    ),
    RELEASE_NOTES_RESOURCE: (
        "`vendor/larkdocio-RELEASE_NOTES.md`, which the consumer refresh script drops beside "
        "the vendored wheel on every refresh, and the publishing repository's own complete copy "
        "of this document at its root"
    ),
}

#: Where a release document's history continues BEFORE its own first entry, when it does —
#: said in the banner whatever the window, because no copy of that document carries it. The
#: changelog is the project's public changelog, which starts at the last release made before
#: the project was public; the release notes reach further back (LD-691).
NOTES_OLDER_HISTORY = {
    CHANGELOG_RESOURCE: (
        "Releases older than this changelog's first entry are recorded per version in the "
        "release notes: the `vendor/larkdocio-RELEASE_NOTES.md` drop beside the wheel, or the "
        "publishing repository's root copy. The wheel's own `larkdocio.release_notes()` "
        "carries only a window of the newest releases."
    ),
}

#: A release version at the START of a section name a caller offered — ``1.20.0``, or the
#: leading ``1-20-0`` of the slug ``1-20-0-2026-07-29``. It is what lets the refusal tell an
#: OUT-OF-WINDOW release (a real release this copy no longer carries) from an UNKNOWN section
#: (a name that was never a release at all): two different failures that must not be laundered
#: into one message.
_RELEASE_PREFIX = _re.compile(r"^(\d+)-(\d+)-(\d+)(?:-|$)")

#: ------------------------------------------------------------------------------------------
#: The ONE place a count meets the word that has to agree with it. Six messages in this module
#: interpolate a count next to a noun or a verb — the unknown-section refusal, both halves of
#: the packaged window banner, both halves of the out-of-window refusal, and the guide index
#: header — and every one of them used to hard-code the plural, so a one-section document read
#: "the 1 it has are", "the newest 1 releases", "1 sections". Two of those sites write into the
#: packaged wheel, so it is shipped text. Fixed as a class rather than six times: at counts
#: above one the returned word is exactly what was hard-coded before, so no existing byte moves.
def _agreeing(count: int, singular: str, plural: Optional[str] = None) -> str:
    """``"release"`` at one, ``"releases"`` above it; ``_agreeing(n, "is", "are")`` for a verb."""
    return singular if count == 1 else (plural if plural is not None else singular + "s")


#: A fenced-code delimiter — three or more backticks or tildes, with an optional info string.
#: Heading detection has to know about these: the guide's fenced Python is full of
#: ``#``-prefixed comment lines, and a fence-blind line scan reads several times as many
#: "headings" out of this document as it really has.
_FENCE_DELIMITER = _re.compile(r"^(`{3,}|~{3,})(.*)$")

#: An ATX heading line — ``## Something`` — and the level it declares.
_ATX_HEADING = _re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")

#: Every run of non-alphanumeric characters, which the slug rule collapses to one ``-``.
_NON_ALPHANUMERIC = _re.compile(r"[^0-9a-zA-Z]+")


def _slugify(heading: str) -> str:
    """The slug rule, stated once: backticks dropped, lower-cased, every run of
    non-alphanumeric characters collapsed to a single ``-``, the ends trimmed.

    Applied to a *heading* it produces that section's slug; applied to a caller's argument it
    normalizes the spelling, which is what makes the slug and the heading text (in any case)
    two ways of naming the same thing rather than two lookups.
    """
    return _NON_ALPHANUMERIC.sub("-", heading.replace("`", "").lower()).strip("-")


def _atx_headings(text: str):
    """``[(level, heading, start_offset)]`` for every ATX heading **outside** a fenced block.

    All six levels, because the boundary rule needs them: a level-2 section ends at the next
    heading of level 2 **or above**, and a heading level the index does not expose can still be
    the thing that ends a section. A fence opened with N backticks (or tildes) is closed only by
    a run of N or more of the *same* character with nothing after it, so a shorter run — or the
    other character — inside a block is content, exactly as a Markdown reader treats it.
    """
    rows = []
    offset = 0
    open_run = None
    for line in text.split("\n"):
        start = offset
        offset += len(line) + 1
        delimiter = _FENCE_DELIMITER.match(line)
        if delimiter is not None:
            run, info = delimiter.groups()
            if open_run is None:
                open_run = run
            elif run[0] == open_run[0] and len(run) >= len(open_run) and not info.strip():
                open_run = None
            continue
        if open_run is not None:
            continue
        heading = _ATX_HEADING.match(line)
        if heading is not None:
            rows.append((len(heading.group(1)), heading.group(2), start))
    return rows


def _refuse_slug_collisions(rows) -> None:
    """Raise when two headings derive the same slug, instead of serving the first match.

    A document edit that creates two identical section names is a defect: every later call
    naming that slug would silently receive one of two sections with nothing to tell it which.
    Refusing at index-build time makes that a loud failure the moment the document changes.
    """
    by_slug = {}
    for _level, heading, slug, _start, _end in rows:
        by_slug.setdefault(slug, []).append(heading)
    collisions = {slug: names for slug, names in by_slug.items() if len(names) > 1}
    if collisions:
        detail = "; ".join(
            f"{slug!r} ← " + ", ".join(repr(name) for name in names)
            for slug, names in sorted(collisions.items())
        )
        raise ValueError(
            "two headings in the document derive the same section name, so naming it could "
            f"only be answered ambiguously: {detail}. Rename one of the headings."
        )


def _bounded_sections(text: str, levels: Tuple[int, ...] = GUIDE_SECTION_LEVELS):
    """``[(level, heading, slug, start, end)]`` — the index plus each section's slice bounds.

    **The boundary rule**, stated once and used everywhere: a section runs from its own heading
    line (inclusive) through the character before the next heading of the **same or higher**
    level (exclusive), or to the end of the document when none follows. Nothing is stripped and
    nothing is added, so a section is a verbatim slice: it keeps the newline ending its last
    line and any blank line sitting before the next heading, and the sections at one level tile
    the document with no gap and no overlap.

    ``levels`` is the ONE parameter this seam takes to serve a second document rather than
    forking a copy of it — every packaged document's ``_sections()`` helper and every
    accessor's ``section=`` path route through this same function, with its own document's
    levels (see ``GUIDE_SECTION_LEVELS`` and its siblings below it in this module).
    """
    headings = _atx_headings(text)
    rows = []
    for position, (level, heading, start) in enumerate(headings):
        if level not in levels:
            continue
        end = len(text)
        for next_level, _next_heading, next_start in headings[position + 1:]:
            if next_level <= level:
                end = next_start
                break
        rows.append((level, heading, _slugify(heading), start, end))
    _refuse_slug_collisions(rows)
    return tuple(rows)


def _section_index(text: str, levels: Tuple[int, ...] = GUIDE_SECTION_LEVELS) -> Tuple[dict, ...]:
    """``({"heading", "slug", "level"}, ...)`` in document order — names only, never text."""
    return tuple(
        {"heading": heading, "slug": slug, "level": level}
        for level, heading, slug, _start, _end in _bounded_sections(text, levels)
    )


def _sections_teaching(
    text: str, symbols: Tuple[str, ...], levels: Tuple[int, ...] = (3,),
) -> Tuple[str, ...]:
    """Slugs of the sections at ``levels`` whose body carries **every** symbol, in document
    order.

    The registry uses this to point a compound workflow at the sections that teach it
    **without any code writing a section name down**: the pointer is derived from the shipped
    document on every call, so a heading rename moves the slug and the pointer follows it,
    and a recipe added tomorrow is pointed at with no code change. Every symbol must be
    present, so a section that merely mentions one half of a round trip in passing is not
    claimed as teaching it.
    """
    return tuple(
        slug
        for _level, _heading, slug, start, end in _bounded_sections(text, levels)
        if all(symbol in text[start:end] for symbol in symbols)
    )


def _section_text(
    text: str, section: str, levels: Tuple[int, ...] = GUIDE_SECTION_LEVELS, *,
    sections_helper: str = "guide_sections", docs_key: str = "guide()",
    windowed_resource: Optional[str] = None,
) -> str:
    """One section of ``text``, named by its slug, its heading, or — for a release document —
    its bare version, all case-insensitively.

    Raises :class:`ValueError` naming **every** section the document has when the name matches
    none of them, so a caller who guessed wrong recovers without a second call. ``sections_helper``
    / ``docs_key`` name the refusal's own pointers back to the index — ``guide()`` by default,
    overridden by every other accessor so a refusal from ``release_notes(section=...)`` points
    at ``release_notes_sections()`` and not at the guide's.

    **The version arm is a FALLTHROUGH.** Both exact spellings are tried first; only when they
    miss is the name read as a release version and compared against the version each row's own
    slug parses to. A release heading carries its date, so it slugs to ``1-43-0-2026-08-31``
    and the bare ``1.43.0`` matched nothing — the release just cut being the one asked about
    first. A document whose headings are not versions has no row that can match, so it is
    unaffected.

    ``windowed_resource`` enrols a document whose packaged copy carries only a **window** of its
    sections (the two release documents). For those, a name that parses as a release version
    older than the window gets :func:`_out_of_window_refusal` instead — a real release this copy
    does not carry is a different failure from a name that was never a section, and the two
    messages stay distinct so neither can be read as the other.
    """
    rows = _bounded_sections(text, levels)
    wanted = section.strip()
    normalized = _slugify(wanted)
    lowered = wanted.lower()
    for _level, heading, slug, start, end in rows:
        if (normalized and slug == normalized) or heading.lower() == lowered:
            return text[start:end]
    # The VERSION arm, and it is deliberately a FALLTHROUGH: both exact matches above have
    # already missed. A release heading carries its date, so it slugs to ``1-43-0-2026-08-31``
    # and the bare ``1.43.0`` a caller actually types matched nothing — the release just cut
    # being the one asked about first, and the one that could not name itself. Nothing else
    # changes: a document whose headings do not parse as versions has no row to match, so the
    # guide, the writer brief and the walkthrough fall through to the same refusal as before.
    asked_version = _release_version(normalized)
    if asked_version is not None:
        for _level, _heading, slug, start, end in rows:
            if _release_version(slug) == asked_version:
                return text[start:end]
    if windowed_resource is not None:
        refusal = _out_of_window_refusal(
            section, wanted, rows, windowed_resource, sections_helper, docs_key,
        )
        if refusal is not None:
            raise ValueError(refusal)
    known = ", ".join(slug for _l, _h, slug, _s, _e in rows)
    raise ValueError(
        f"unknown section {section!r}: this document has no heading matching it. Name a "
        "section either by the heading exactly as it appears or by the slug derived from it "
        f"(both case-insensitive); the {len(rows)} it has "
        f"{_agreeing(len(rows), 'is', 'are')}: {known}. "
        f"larkdocio.{sections_helper}() returns that same index with each heading, its slug and "
        f"its level, and capabilities(full=True)['docs']['{docs_key}']['sections'] carries it too."
    )


#: ``{resource: the accessor a reader calls to get this document}`` — named in the banner and in
#: the out-of-window refusal, because a wheel-only reader has no file path to open and the
#: accessor is the only address that works from inside an installed wheel.
NOTES_ACCESSOR = {
    CHANGELOG_RESOURCE: "larkdocio.changelog",
    RELEASE_NOTES_RESOURCE: "larkdocio.release_notes",
}


#: The column the projection's banner wraps at. A fixed width, so the generated bytes are a
#: function of the projection's inputs and nothing else — a banner wrapped to the terminal, or to
#: the longest version string, would make the shipped file's bytes non-reproducible.
_BANNER_WIDTH = 92


def notes_window_banner(resource: str, kept: Tuple[str, ...], dropped_below: str) -> str:
    """The disclosure the projection writes into the packaged copy, immediately above its first
    release section — so a reader who opens the shipped document meets the narrowing at the top
    instead of discovering it from a refusal.

    Every number and version in it is derived from the projection being written: the count is
    ``len(kept)``, the span is the kept sections' own versions, the next-older release is the one
    the cut fell on, and the addresses come from :data:`NOTES_FULL_HISTORY`. Nothing is
    hand-kept, so no part of it can go stale independently of the bytes below it, and the wrap is
    at a fixed :data:`_BANNER_WIDTH` so the bytes are reproducible from the inputs alone.

    **No column-0 ``#`` line, deliberately.** A heading here would enter the document's heading
    census and its section index, and this is a preamble note, not a section: the reassembly
    contract — every top-level section tiles the document, and the preamble carries no top-level
    heading — has to keep holding on the projection exactly as it holds on the source.
    """
    accessor = NOTES_ACCESSOR[resource]
    span = kept[0] if len(kept) == 1 else f"{kept[-1]} up to {kept[0]}"
    whole = dropped_below == "nothing"
    if whole:
        # Nothing was cut (LD-691): the copy is the whole document, so it must not call itself a
        # window or point at a fuller copy that has nothing more in it.
        first = (
            f"**This copy carries every release this document records — {len(kept)} "
            f"{_agreeing(len(kept), 'release')}, {span} — verbatim.** The same entries are at "
            f"{NOTES_FULL_HISTORY[resource]}."
        )
        where = None
    else:
        first = (
            f"**This copy carries a WINDOW of the newest {len(kept)} "
            f"{_agreeing(len(kept), 'release')}, not the whole "
            f"history.** Everything below this line is verbatim — {kept[-1]} up to {kept[0]} — and "
            f"the releases older than {kept[-1]}, {dropped_below} and down, ship with the "
            "publishing repository instead of inside the wheel. That is deliberate: the reader "
            "this copy exists for is deciding whether to re-pin, and a full history costs them "
            "every release they can no longer act on before it reaches the one they can."
        )
        where = f"The full history is at {NOTES_FULL_HISTORY[resource]}."
    paragraphs = tuple(p for p in (
        first,
        where,
        NOTES_OLDER_HISTORY.get(resource),
        (f"`{accessor}(section=...)` refuses a release this copy does not carry by name and "
         f"says where to read it; `{accessor}_sections()` lists the {len(kept)} "
         f"{_agreeing(len(kept), 'release')} this copy carries.") if whole else
        (f"`{accessor}(section=...)` refuses a release older than the window by name and repeats "
         f"those addresses; `{accessor}_sections()` lists the {len(kept)} "
         f"{_agreeing(len(kept), 'release')} this copy carries."),
    ) if p)
    lines = []
    for index, paragraph in enumerate(paragraphs):
        if index:
            lines.append(">")
        lines.extend(
            f"> {line}"
            for line in _textwrap.wrap(paragraph, width=_BANNER_WIDTH, break_long_words=False)
        )
    return "\n".join(lines) + "\n\n"


def notes_window(text: str, resource: str) -> str:
    """The **recent-N projection** of a release document — the exact bytes the wheel carries.

    ``text`` is the complete, canonical document (the repository's own copy); the return value
    is its preamble verbatim, then :func:`notes_window_banner`, then the newest
    ``NOTES_WINDOW_SECTIONS[resource]`` release sections verbatim, and nothing else. A
    document with no more sections than the window is returned with its banner and all of its
    sections — the projection never invents or reflows a byte, so a cut, dated release section
    inside the window is the same bytes it is at the root, character for character.

    **Pure, and the single definition of the window.** Whatever writes the packaged file and
    whatever checks it both call this one function, so there is no second statement anywhere of
    where the cut falls — which is what makes "the shipped copy is exactly the projection of the
    canonical one" an equality a machine can check rather than a habit.
    """
    levels = NOTES_WINDOW_LEVELS[resource]
    keep = NOTES_WINDOW_SECTIONS[resource]
    rows = _bounded_sections(text, levels)
    if not rows:
        return text
    kept_rows = rows[:keep]
    first_start = kept_rows[0][3]
    end = rows[keep][3] if len(rows) > keep else len(text)
    kept = tuple(_release_version(row[2]) or row[1] for row in kept_rows)
    below = (
        _release_version(rows[keep][2]) or rows[keep][1] if len(rows) > keep else "nothing"
    )
    banner = notes_window_banner(resource, kept, below)
    return text[:first_start] + banner + text[first_start:end]


#: Every packaged document whose canonical copy lives at the **repository root** and whose
#: in-package copy is therefore MATERIALISED rather than hand-kept. ``package-data`` can only
#: carry a file that lives inside a package directory, so each of these has two copies; this
#: tuple is the enumeration that both the writer and the guards read, so none of them carries a
#: list of its own. Those live **in the source repository** — the writer is
#: ``scripts/sync-packaged-notes.sh`` and the guards are ``tests/test_shipped_notes.py`` (the
#: release documents) and ``tests/test_packaged_lark_setup.py`` (the walkthrough) — and a
#: consumer needs none of them: what reaches a consumer is the projected bytes below.
#: The other packaged documents — the guide, the writer brief, the handler-authoring
#: guide — are not here because they have exactly one copy each, already inside the package.
PACKAGED_TWIN_RESOURCES = (
    CHANGELOG_RESOURCE,
    RELEASE_NOTES_RESOURCE,
    LARK_SETUP_RESOURCE,
)


def packaged_projection(text: str, resource: str) -> str:
    """The exact bytes the wheel's copy of ``resource`` must carry, given its canonical text.

    **One function, two rules, and the rule is a property of the DOCUMENT rather than a choice
    made per caller.** A release document is projected through :func:`notes_window` — a
    recent-N window, because its reader is deciding whether to re-pin and the releases they can
    no longer act on cost them the ones they can. Everything else is projected through the
    **identity**: the whole document, byte for byte.

    Identity is not "no projection was designed"; it is the answer for a document that does not
    grow a section per release and does not go out of date by being old. The Lark-application
    walkthrough is exactly that shape — an app, its scopes, its reach — so a window would
    subtract truth and buy nothing. What makes the identity a *projection* rather than a hand
    copy is that this function is the only writer and the guard asserts byte equality against
    it, so a hand-edited packaged copy still reddens.
    """
    if resource in NOTES_WINDOW_SECTIONS:
        return notes_window(text, resource)
    return text


def _release_version(slug: str) -> Optional[str]:
    """``"1-31-0-2026-08-10"`` -> ``"1.31.0"``; ``None`` when the name is not a release at all.

    The one place a section name is read as a version. Used by the projection's banner (to say
    the span in the spelling a reader recognises) and by the out-of-window refusal (to tell a
    real release this copy no longer carries from a name that was never a release).
    """
    match = _RELEASE_PREFIX.match(slug)
    return ".".join(match.groups()) if match else None


def _version_tuple(version: str) -> Tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _out_of_window_refusal(
    section: str, wanted: str, rows, resource: str, sections_helper: str, docs_key: str,
) -> Optional[str]:
    """The refusal message for a section naming a release version OLDER than this windowed
    copy's oldest — or ``None`` when this is not that case and the unknown-section refusal
    applies.

    **The two cases are kept apart on purpose.** An unknown section is a caller who guessed a
    name that was never a heading; an out-of-window version is a caller who named something
    this copy deliberately does not carry. Laundering the second into the first would tell a
    reader their release does not exist — which this copy is in no position to say — and would
    not tell them where the history lives. So this returns a message only when the name parses
    as a release version OLDER than the oldest one in the window.

    **And it vouches for NOTHING.** The message used to open by asserting that the named
    version *"is a real release"*. That is an existence claim this wheel **cannot check**: it
    carries only the window, so a fabricated in-range version was vouched for, and every cut
    mints a fresh band of never-existed strings the assertion would cover. It now says only
    what it can substantiate — what the window is, that the name sorts below it, that this copy
    cannot settle whether such a release was ever cut, and the two addresses the full history
    sits at. The project had already written that argument down for the sibling arm, in the
    comment above the unknown-name mirror assertion in the packaged-doc section-access suite,
    which calls this same wording a lie; the fence had simply never been applied to this arm.
    """
    if resource not in NOTES_WINDOW_SECTIONS:
        return None
    versions = [v for v in (_release_version(row[2]) for row in rows) if v]
    if not versions:
        return None
    asked = _release_version(_slugify(wanted))
    if asked is None:
        return None
    oldest = min(versions, key=_version_tuple)
    if _version_tuple(asked) >= _version_tuple(oldest):
        return None
    newest = max(versions, key=_version_tuple)
    known = ", ".join(slug for _l, _h, slug, _s, _e in rows)
    if len(rows) < NOTES_WINDOW_SECTIONS[resource]:
        # Fewer sections than the window holds: this copy IS the whole document (LD-691 — the
        # public changelog starts at the last release made before the project was public), so
        # it must not call itself a window. Where the history continues before the document's first entry, it says so.
        return (
            f"out-of-window section {section!r}: this copy carries every release this document "
            f"records — {len(rows)} {_agreeing(len(rows), 'release')}, "
            f"{oldest if oldest == newest else f'{oldest} up to {newest}'} "
            f"— and {asked} sorts older than {oldest}, its first entry. "
            + (NOTES_OLDER_HISTORY.get(resource, "") + " " if resource in NOTES_OLDER_HISTORY
               else "")
            + f"The {len(rows)} {_agreeing(len(rows), 'release')} this copy does carry "
            f"{_agreeing(len(rows), 'is', 'are')}: {known}. larkdocio.{sections_helper}() "
            "returns that same index with each heading, its slug and its level, and "
            f"capabilities(full=True)['docs']['{docs_key}']['sections'] carries it too."
        )
    return (
        f"out-of-window section {section!r}: this wheel carries a WINDOW of the newest "
        f"{len(rows)} {_agreeing(len(rows), 'release')} ({oldest} up to {newest}), not the "
        f"whole history, and {asked} sorts older than {oldest}, the oldest one this copy "
        f"holds. Whether {asked} was ever cut is a question this copy cannot answer — it "
        f"carries no record of anything outside its window, so it neither confirms nor denies "
        f"that name. The full history is at {NOTES_FULL_HISTORY[resource]}; either address "
        f"settles {asked}. The {len(rows)} {_agreeing(len(rows), 'release')} this copy does "
        f"carry {_agreeing(len(rows), 'is', 'are')}: {known}. larkdocio.{sections_helper}() "
        "returns that same index with each heading, its slug and its level, and "
        f"capabilities(full=True)['docs']['{docs_key}']['sections'] carries it too."
    )


def _index_text(text: str, levels: Tuple[int, ...] = GUIDE_SECTION_LEVELS) -> str:
    """The guide's section index **rendered as text** — what :func:`guide` answers by default.

    Every row is literally the call that fetches that section, indented by its level so a
    ``##`` name visibly contains the ``###`` names under it, and the header names the other two
    calls a reader could want next. Derived from ``text`` on every call through the same
    :func:`_bounded_sections` machinery the index and the section slicer use, so there is no
    second copy of the section set anywhere and a heading edit moves this with no code change.

    **Why this is the default:** the document is over half a megabyte as one string — too big
    to read as a default — and this index, whose headings are named after the FAILURE each
    recipe cures, is the faster way in. The roles are swapped; the document is one explicit argument away
    and byte-identical.
    """
    # The ruling behind the swap is LD-468 (maintainer, 2026-08-14 — "swap it"); the issue id lives in
    # this comment rather than in the docstring above, which a consumer reads out of the wheel.
    rows = _bounded_sections(text, levels)
    shallowest = min(level for level, *_rest in rows) if rows else min(levels)
    body = "\n".join(
        f"{'    ' * (level - shallowest)}  {heading}"
        f'   →   larkdocio.guide("{slug}")'
        for level, heading, slug, _start, _end in rows
    )
    return (
        f"larkdocio.guide() — the SECTION INDEX of the packaged consumer guide: "
        f"{len(rows)} {_agreeing(len(rows), 'section')}.\n"
        "\n"
        "This is the index, not the document. Each heading below is named after the FAILURE its\n"
        "section cures, so scan for your symptom and fetch that one section — each row IS the\n"
        "call that fetches it. A name indented under another is contained by it.\n"
        "\n"
        '  larkdocio.guide("<slug>")   one section; its heading text names it too, either\n'
        "                              spelling case-insensitive. An unknown name refuses and\n"
        "                              lists every section there is.\n"
        f"  larkdocio.guide(full=True)  the whole document, byte for byte — {len(text):,} "
        "characters.\n"
        "  larkdocio.guide_sections()  this same index as data: {heading, slug, level} rows.\n"
        "\n"
        "  On the command line: `larkdocio guide` prints this index, `larkdocio guide --section\n"
        "  <slug>` prints one section, and `larkdocio guide --full` prints the whole document.\n"
        "\n"
        f"{body}\n"
    )


def guide(section: Optional[str] = None, *, full: bool = False) -> str:
    """Return the shipped consumer guide (``GUIDE.md``) — its **index**, one section, or all of it.

    Reads the packaged resource via :mod:`importlib.resources` (stdlib — no new
    dependency), so it works from an installed wheel as well as a source checkout.

    **With no argument you get the section index as text** — every heading, its slug and its
    level, in document order, each row spelled as the call that fetches it, and the text itself
    says how to ask for one section and how to ask for the whole document. That is the front
    door: small enough to read in one breath, and it names your next call.

    **Pass ``full=True`` for the whole document**, byte for byte as the wheel carries it —
    unchanged, and not routed through any of the machinery below. (This is what no argument
    used to return, up to and including v1.33.0; the two swapped roles because the document is
    over half a megabyte and the index is what a reader needs first. The bytes behind
    ``full=True`` are the same bytes as before — see ``release_notes()``.) ``full=True``
    together with ``section`` is two mutually exclusive requests in one call and raises
    :class:`ValueError`.

    Pass ``section`` to get one part of it instead, which is what a caller who wants a single
    recipe should do rather than hold 500 KB:

    * **Naming a section.** Either the heading exactly as it appears in the document, or the
      slug derived from it (backticks dropped, lower-cased, runs of non-alphanumerics collapsed
      to ``-``). Both are matched **case-insensitively** and surrounding whitespace is ignored,
      so a rename that only re-cases or re-punctuates a heading does not break a caller.
    * **What comes back.** The heading line itself, then that section's text up to the
      character before the next heading of the same or higher level — or the end of the
      document. A ``##`` name therefore includes its ``###`` children; a ``###`` name stops at
      the next ``###`` or the next ``##``, whichever comes first. The bytes are the document's
      own, so nothing is stripped or reflowed.
    * **What can be asked for.** The no-argument call above is the index in readable form;
      :func:`guide_sections` is the same index as data, and
      ``capabilities(full=True)["docs"]["guide()"]["sections"]`` carries the same rows.
    * **An unknown name raises** :class:`ValueError` whose message names **every** section the
      document has, so recovering takes no second call.
    """
    if full and section is not None:
        raise ValueError(
            f"guide(section={section!r}, full=True) asks for one section and for the whole "
            "document at once. Pass section= for one part of it, or full=True for all of it — "
            "not both; guide() with neither returns the index of what can be named. On the "
            "command line the same rule reads `larkdocio guide --section <name>` or "
            "`larkdocio guide --full`, never both."
        )
    text = _packaged(GUIDE_RESOURCE)
    if full:
        return text
    if section is None:
        return _index_text(text)
    return _section_text(text, section)


def guide_sections() -> Tuple[dict, ...]:
    """The shipped guide's section index — what :func:`guide`'s ``section`` accepts.

    One row per heading at a level the index covers, in document order:
    ``{"heading": str, "slug": str, "level": int}``. ``heading`` is the document's own text;
    ``slug`` is the shorter spelling of the same name; ``level`` says how deep it sits, which is
    what tells you a row **contains** the rows nested under it.

    **Names only, never text** — the whole point is to choose a section before paying for one,
    so a row is a few dozen bytes and the index is smaller than any section in it.

    Derived from the packaged document on **every call**, so it cannot disagree with the
    document it indexes: add a heading and the next call returns it, with no code change here.
    Raises :class:`ValueError` if two headings ever derive the same name, rather than letting one
    of the two silently win every lookup.
    """
    return _section_index(_packaged(GUIDE_RESOURCE))


def writer_brief(section: Optional[str] = None) -> str:
    """Return the shipped **writer brief** (``write/README.md``) as text — all of it, or one
    section.

    The long-form treatment of the authoring dialect — the normalizations, the asymmetries,
    and what ``compose()`` does when handed the reader's own emission for a non-creatable
    block — plus the writer's phased design, its credential doctrine and its live-write
    round-trip procedure. :func:`guide` cites it for the detail it deliberately does not
    repeat.

    It has always shipped in the wheel (``[tool.setuptools.package-data]``), but ``guide()``
    was the only text accessor exposed, so a consumer on a vendored wheel could read the
    citation and not the document. Same contract as :func:`guide`: the
    **packaged resource** via :mod:`importlib.resources`, never a filesystem path, so it
    resolves identically from a source checkout and from an installed wheel where no ``src/``
    tree exists.

    ``section`` takes the SAME seam :func:`guide` does — a heading exactly as it appears, or
    its slug, either case-insensitively, sliced by the same boundary rule (through the
    character before the next same-or-higher-level heading) — indexed at
    :data:`WRITER_BRIEF_SECTION_LEVELS`. :func:`writer_brief_sections` is the index; an unknown
    name raises :class:`ValueError` naming every section this document has.
    """
    text = _packaged(WRITER_BRIEF_RESOURCE, WRITER_BRIEF_PACKAGE)
    if section is None:
        return text
    return _section_text(
        text, section, levels=WRITER_BRIEF_SECTION_LEVELS,
        sections_helper="writer_brief_sections", docs_key="writer_brief()",
    )


def writer_brief_sections() -> Tuple[dict, ...]:
    """The shipped writer brief's section index — what :func:`writer_brief`'s ``section``
    accepts. Same shape and the same derive-at-call-time contract as :func:`guide_sections`."""
    return _section_index(
        _packaged(WRITER_BRIEF_RESOURCE, WRITER_BRIEF_PACKAGE), levels=WRITER_BRIEF_SECTION_LEVELS
    )


def release_notes(section: Optional[str] = None) -> str:
    """Return the shipped **release notes** (``RELEASE_NOTES.md``) as text — all of it, or one
    release's section.

    **The consumer-filtered view of what changed** — read this before you re-pin. It carries
    only what someone consuming larkdocio as a vendored wheel can observe, install, call or be
    broken by: public symbols and CLI flags added / renamed / removed, observable behavior
    changes (a change to the rendered Markdown is always one), new or renamed refusal codes and
    plan disclosures, every dependency add and pin move, credential and console-setting
    requirements, and the known limitations of each release. Its own header states the
    include/exclude criteria it is written to.

    **Deliberately distinct from** :func:`changelog`, which returns ``CHANGELOG.md`` — the
    project's changelog, one entry per release from the last release made before the project
    was public on. Neither replaces the other; these notes reach further back.

    Same contract as :func:`guide`: the **packaged resource** via :mod:`importlib.resources`,
    never a filesystem path. The reason this accessor exists is that a wheel-only consumer
    receives no copy beside the wheel — that copy is a convenience the refresh script drops
    for consumers who vendor — so a citation naming the file rather than this function is a
    pointer they cannot follow.

    ``section`` takes ONE release at a time — name it by its own ``## [X.Y.Z] — date`` heading,
    by the slug derived from it, or by the **bare version** (``"1.20.0"``, the spelling a
    consumer already has in their pin), all case-insensitively, which is *"what changed in
    X.Y.Z"* without holding every release ever written. Indexed at
    :data:`RELEASE_NOTES_SECTION_LEVELS` — ``## `` only, deliberately: every release repeats
    the same four ``###`` subsection headings, so a caller asking for one release gets its
    subsections too (the boundary rule), while nothing named after them is individually
    addressable. :func:`release_notes_sections` is the index; an unknown name raises
    :class:`ValueError` naming every release this document has.
    """
    text = _packaged(RELEASE_NOTES_RESOURCE)
    if section is None:
        return text
    return _section_text(
        text, section, levels=RELEASE_NOTES_SECTION_LEVELS,
        sections_helper="release_notes_sections", docs_key="release_notes()",
        windowed_resource=RELEASE_NOTES_RESOURCE,
    )


def release_notes_sections() -> Tuple[dict, ...]:
    """The shipped release notes' section index — one row per release. Same shape and the same
    derive-at-call-time contract as :func:`guide_sections`."""
    return _section_index(_packaged(RELEASE_NOTES_RESOURCE), levels=RELEASE_NOTES_SECTION_LEVELS)


def changelog(section: Optional[str] = None) -> str:
    """Return the shipped **changelog** (``CHANGELOG.md``) as text — all of it, or one
    release's section.

    **The project's changelog** — one entry per release, saying what changed in it, from the
    last release made before the project was public on, and a pointer to the release notes
    for earlier versions (the versions developed before the project was public are recorded
    only there).

    **If you want "what changed that affects me", read** :func:`release_notes` **instead** —
    ``RELEASE_NOTES.md`` is the consumer-facing counterpart, it is the one written to stated
    relevance criteria, and it reaches back to 1.14.0.

    Same contract as :func:`guide`: the **packaged resource** via :mod:`importlib.resources`,
    never a filesystem path, so it resolves identically from a source checkout and from an
    installed wheel.

    ``section`` takes ONE release at a time, named by its ``## [X.Y.Z] — date`` heading, its
    slug, or its bare version, all case-insensitively — the same reasoning
    :func:`release_notes` states for its
    own ``section``, and the same reason this document is also indexed at
    :data:`CHANGELOG_SECTION_LEVELS` (``## `` only: every release repeats the same ``###``
    subsection headings — ``Added`` / ``Changed`` / ``Fixed`` — so indexing them too would
    collide). :func:`changelog_sections` is the index; an unknown name raises
    :class:`ValueError` naming every release this document has.
    """
    text = _packaged(CHANGELOG_RESOURCE)
    if section is None:
        return text
    return _section_text(
        text, section, levels=CHANGELOG_SECTION_LEVELS,
        sections_helper="changelog_sections", docs_key="changelog()",
        windowed_resource=CHANGELOG_RESOURCE,
    )


def changelog_sections() -> Tuple[dict, ...]:
    """The shipped changelog's section index — one row per release. Same shape and the same
    derive-at-call-time contract as :func:`guide_sections`."""
    return _section_index(_packaged(CHANGELOG_RESOURCE), levels=CHANGELOG_SECTION_LEVELS)


def lark_setup(section: Optional[str] = None) -> str:
    """Return the shipped **Lark-application walkthrough** (``LARK_SETUP.md``) — all of it, or
    one step.

    The ten minutes before a first download: create the app, grant the starter scope, share the
    documents onto it, put the credentials where larkdocio reads them, prove one real call.
    **Nothing in this library works until those three facts hold** — an app exists, it holds the
    scopes, and it can reach the documents — and none of them is a code change, so this is the
    one document whose whole job is the part that happens outside the library.

    It deliberately does not enumerate scopes: the per-operation rows are generated from the
    code, and the guide's own permissions section is where a caller takes them — named in
    :func:`guide_sections`, never written down here (the reason is this module's own rule: a
    section name listed in code is a second copy of the document's headings).

    Same contract as :func:`guide`: the **packaged resource** via :mod:`importlib.resources`,
    never a filesystem path, so it resolves identically from a source checkout and from an
    installed wheel where no ``src/`` tree exists. That is the reason this accessor exists at
    all — the walkthrough is the document a brand-new consumer needs *first*, and until it
    shipped, the only reader who could open it was one who already had the publishing
    repository, which is precisely the reader who needs it least.

    ``section`` names one step, by its heading or the slug derived from it, either
    case-insensitively; :func:`lark_setup_sections` is the index and an unknown name raises
    :class:`ValueError` naming every section this document has.
    """
    text = _packaged(LARK_SETUP_RESOURCE)
    if section is None:
        return text
    return _section_text(
        text, section, levels=LARK_SETUP_SECTION_LEVELS,
        sections_helper="lark_setup_sections", docs_key="lark_setup()",
    )


def lark_setup_sections() -> Tuple[dict, ...]:
    """The shipped walkthrough's section index — one row per step. Same shape and the same
    derive-at-call-time contract as :func:`guide_sections`."""
    return _section_index(_packaged(LARK_SETUP_RESOURCE), levels=LARK_SETUP_SECTION_LEVELS)


#: ``(accessor name, the document's path inside the wheel, what it is for)`` for every
#: packaged document **written for a consumer** — the single place the set is written down, so
#: the accessors above and the ``docs`` registry :func:`larkdocio.capabilities` projects cannot
#: disagree. A consumer document added to the wheel without a row here has no accessor and is
#: unreadable in practice; ``tests/test_release_notes_accessor.py`` now holds this table
#: against the packaged Markdown set (minus one named contributor-doc exclusion,
#: ``blocks/BLOCK_TYPES.md``), so that failure reddens the suite instead of shipping — which is
#: the failure this table always claimed to make visible and, until then, nothing enforced.
DOC_ACCESSORS = (
    (
        "guide",
        f"larkdocio/{GUIDE_RESOURCE}",
        "The consumer guide: the capability matrix in human-readable form plus the "
        "copy-paste recipes for every surface (download a document to Markdown, read a "
        "sheet, both write handshakes, credential setup). Start here — guide() with no "
        "argument returns this document's section INDEX, whose headings are named after the "
        "failure each one cures; guide(section=...) returns one of them, and guide(full=True) "
        "the whole document byte for byte.",
    ),
    (
        "writer_brief",
        f"{WRITER_BRIEF_PACKAGE.replace('.', '/')}/{WRITER_BRIEF_RESOURCE}",
        "The writer's long-form brief: the composable Markdown dialect in full — its "
        "normalizations and asymmetries, what compose() does with the reader's own output "
        "for a block it cannot create, the phased design, the credential doctrine and the "
        "write round-trip procedure. The guide cites it for the detail it does not repeat.",
    ),
    (
        "release_notes",
        f"larkdocio/{RELEASE_NOTES_RESOURCE}",
        "What changed THAT AFFECTS YOU, release by release — the filtered view, written to "
        "stated relevance criteria: public symbols and CLI flags, observable behavior "
        "changes, new or renamed refusals and disclosures, every dependency pin move, "
        "credential and console-setting requirements, known limitations. Read it before you "
        "re-pin.",
    ),
    (
        "changelog",
        f"larkdocio/{CHANGELOG_RESOURCE}",
        "The project's changelog: one entry per release, and a pointer to the release notes for "
        "earlier versions. For 'what changed that affects me', read the release notes instead.",
    ),
    (
        "lark_setup",
        f"larkdocio/{LARK_SETUP_RESOURCE}",
        "The Lark-application walkthrough — the ten minutes before a first download: create "
        "the app, grant the starter scope, share the documents onto it, put the credentials "
        "where larkdocio reads them, prove one real call. Nothing in this library works until "
        "an app exists, holds the scopes and can reach the documents, and none of those three "
        "is a code change. Read it before the guide's recipes.",
    ),
)
