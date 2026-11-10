"""Every guide-section citation in shipped text must RESOLVE — through ``guide()``'s own resolver.

The failure this file exists to make structurally impossible
------------------------------------------------------------
A shipped document names a section of the packaged guide — ``larkdocio.guide("some-slug")``,
``guide(section="some-slug")``, ``larkdocio guide --section some-slug`` on the command line,
or (in the copyable router pack) a **bare backticked slug in a routing-table cell** — and the
guide has no such section, so the very call a consumer was told to make raises ``ValueError``.
Twice this shipped across a release boundary and once more mid-wave:

* the wheel's ``METADATA`` body cited ``guide("quick-start")`` (no slug containing ``quick`` or
  ``start`` has ever existed) and ``guide(section="permissions")`` **twice** (the real slug is
  ``permissions-what-to-ask-for``);
* a packaged changelog entry cited ``attach-a-file-to-a-document-the-attachment-card``, whose
  real slug carries the ``recipe-`` prefix that the full heading ``### Recipe: attach a file
  …`` derives.

Nothing resolved a cited name. The front-door guards held the layout table, the CLI options,
the ``Summary`` and the *existence* of a cited file; none of them evaluated a **section
address**. So the literals were hand-written, and a hand-written address rots silently.

Why ``guide()``'s OWN resolver, and not the recipe matcher
----------------------------------------------------------
``tests/guide_recipes.py`` has a slug function too, and it is **looser in exactly the place
that matters**: it slugifies a ``### Recipe: <name>`` heading with the ``Recipe: `` label
already stripped, so it answers ``attach-a-file-to-a-document-the-attachment-card`` where
``guide()`` answers ``recipe-attach-a-file-to-a-document-the-attachment-card``. A guard built
on that matcher would have resolved the changelog's citation happily and let the release
ship — which is precisely how the third instance escaped. **A citation is a promise about
what ``guide()`` will do, so only ``guide()`` can keep it**: every address below is checked by
calling :func:`larkdocio.guide` and catching its refusal, never by consulting a second index.
``test_the_recipe_matcher_would_have_missed_the_defect_this_guard_catches`` pins that reasoning
against the code, so the two matchers cannot quietly converge and make the distinction look
like a preference.

Scope
-----
The corpus is the full consumer-reaching one (``tests/consumer_text.py::consumer_corpus`` —
the packaged guide, the writer brief, the release notes, the README that **is** the wheel's
``METADATA`` body, the wheel ``Summary``/``Keywords``, every rendered CLI ``--help`` page,
every emitted string literal under ``src/``, every public docstring and every string inside a
real plan's / ``capabilities()``' JSON) **plus** the repository-root twins of the two release
documents, the packaged changelog and the contributor block-type reference — see
:data:`EXTRA_SOURCES` for why each is named there rather than left to the shared corpus.
"""
import pathlib
import re

import pytest

import consumer_text

import larkdocio


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# 1. EXTRACTION — the three spellings a citation is written in.                 #
# --------------------------------------------------------------------------- #

#: The Python-call spelling: ``guide("slug")`` and ``guide(section="slug")``, with or without
#: the ``larkdocio.`` prefix. The closing ``)`` is part of the pattern deliberately: a heading
#: may contain an apostrophe (``larkdocio's own test-suite policy``), and a pattern that
#: stopped at the first quote of any kind would truncate a single-quoted citation of it into a
#: name that resolves to nothing — a guard inventing its own false positive. Anchoring on
#: ``quote + )`` reads the whole address instead. Kept to one line so a stray quote further
#: down the document cannot be mistaken for a closing one.
_PY_CITATION = re.compile(r"""guide\(\s*(?:section\s*=\s*)?(['"])(?P<slug>[^\n]*?)\1\s*\)""")

#: The command-line spelling: ``larkdocio guide --section <name>``. Two alternatives, in this
#: order, because the option takes **either** spelling of a section name: a shell-quoted
#: heading (``--section "Capability matrix"``, which is the heading form ``guide()`` also
#: accepts) or a bare slug. Reading the quoted form first is what keeps a multi-word heading
#: from being truncated at its first space into a one-word name that resolves to nothing. The
#: separator class spans a newline because the guide's own index text wraps this sentence
#: mid-option, and a citation that wraps is still a citation.
_CLI_CITATION = re.compile(
    r"""guide\s+--section[=\s]+(?:(["'])(?P<quoted>[^"'\n]+)\1|(?P<slug>[A-Za-z0-9_<>-]+))"""
)


#: The SIBLING-ACCESSOR spelling (LD-512). ``guide()`` is not the only packaged document with a
#: section index: ``writer_brief()``, ``release_notes()`` and ``changelog()`` each take a
#: ``section=`` of their own, each with **its own resolver over its own document**, and the
#: shipped guide teaches all three by example. Until this pattern existed no test resolved one:
#: a heading rename in a *sibling* document stranded a shipped literal citation silently — the
#: same class LD-483 killed for ``guide()``, one door along.
#:
#: **This is INSURANCE, not a live bug.** The 2026-08 audit swept the shipped corpus for rotting
#: sibling literals and found **zero**; nothing was broken and nothing is fixed here. What lands
#: is the guard that would have caught it, before the wave-3 guide restructure gives it the
#: chance to happen.
#:
#: The accessor name is captured, because the name IS the resolver — a ``release_notes`` address
#: resolved through ``guide()`` would answer the wrong question and could only ever be wrong.
_SIBLING_CITATION = re.compile(
    r"""\b(?:larkdocio\.)?(?P<accessor>writer_brief|release_notes|changelog)"""
    r"""\(\s*section\s*=\s*(['"])(?P<slug>[^\n]*?)\2\s*\)"""
)

#: ``form -> the resolver that form's addresses are a promise about``. One entry per spelling,
#: so :func:`unresolved_citations` never has to guess. The guide's three spellings all resolve
#: through ``guide()``; each sibling accessor resolves through itself.
_RESOLVERS = {
    "python": "guide",
    "cli": "guide",
    "routing-table": "guide",
    "writer_brief": "writer_brief",
    "release_notes": "release_notes",
    "changelog": "changelog",
}


def resolve_citation(form, slug):
    """Call the accessor ``form``'s addresses are a promise about. Raises its ``ValueError``."""
    return getattr(larkdocio, _RESOLVERS[form])(section=slug)


def _citations(text):
    """``[(spelling, slug)]`` for every packaged-document section address in ``text``.

    Three spellings of a **guide** address — the Python call, the console option — plus (LD-512)
    the **sibling-accessor** spelling, whose ``form`` is the accessor's own name so
    :func:`resolve_citation` can send it to the right resolver.

    The router pack writes a fourth spelling that no packaged document uses — see
    :func:`_routing_addresses`, which is applied **only** to the pack's own files.
    """
    found = [("python", m.group("slug")) for m in _PY_CITATION.finditer(text)]
    for match in _CLI_CITATION.finditer(text):
        found.append(("cli", match.group("quoted") or match.group("slug")))
    for match in _SIBLING_CITATION.finditer(text):
        found.append((match.group("accessor"), match.group("slug")))
    return found


# --------------------------------------------------------------------------- #
# 1b. THE ROUTING-TABLE SPELLING — the pack's own, and only the pack's.         #
# --------------------------------------------------------------------------- #
#
# A router is a table: *for this task, read that section*. The right-hand cell holds the
# address bare — ``| A Base table | `recipe-read-a-base-to-markdown` |`` — because writing
# ``larkdocio.guide("…")`` in forty cells is noise a reader has to look past. That spelling is
# how the pack does the overwhelming majority of its pointing (41 of its 57 addresses when this
# arm was added), and until it was extracted here every one of them was resolved by **nothing**:
# a rename in the guide would have rotted them silently, in somebody else's repository, and the
# suite would have stayed green. LD-499's QA proved exactly that by rotting one cell.
#
# This extractor is deliberately **pack-specific** rather than a widening of ``_citations``
# above. ``_citations`` decides what a *packaged* document means, and every other corpus member
# — the README that is the wheel's METADATA body, the writer brief, BLOCK_TYPES.md — is full of
# backticked hyphenated identifiers (``lark-oapi``, ``py3-none-any``, ``pytest-xdist``) that are
# not addresses at all. Reading them as addresses would redden ~50 guards on text that is
# correct. The pack earns the looser reading because its files are **nothing but** addresses:
# the anti-restatement guard in ``tests/test_consumer_skill_pack.py`` is what keeps them that
# way. Resolution is still the one and only resolver — :func:`unresolved_citations` calls
# ``larkdocio.guide`` and catches its refusal, never a second index.

#: The label prefix ``consumer_text.skill_pack_docs`` gives every pack file. A corpus entry
#: with this prefix gets the routing-table arm; nothing else does.
PACK_LABEL_PREFIX = "consumers/skills/"

#: **Arm A — structural.** A markdown table cell whose *entire* content is one backticked
#: token of letters, digits and hyphens. Case is not constrained here on purpose: a rotted
#: cell is any string somebody typed, and the rot this guard was written for
#: (``…-THAT-DOES-NOT-EXIST``) carries capitals. A cell that holds only a bare token in a file
#: whose every table is a routing table *is* an address — there is nothing else it could be.
_TABLE_CELL_ADDRESS = re.compile(r"`([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)`")

#: **Arm B — lexical.** A backticked, lowercase, hyphenated token *anywhere* in a router, so an
#: address cited in a bullet or a sentence is covered too and an author is not forced to keep
#: every pointer inside a table. Stricter in shape than arm A precisely because it reads prose:
#: the lowercase-and-hyphenated shape is what a guide slug is, and it already excludes every
#: non-address the pack writes (``larkdocio``, ``larkdocio.roundtrip.pull()``,
#: ``scripts/update_larkdocio.sh``, ``larkdocio guide --section …``).
_PACK_SLUG_SPAN = re.compile(r"`([a-z0-9]+(?:-[a-z0-9]+)+)`")


def router_names():
    """The pack's own skill names — the one class of backticked slug that is **not** a guide
    address.

    Routers cross-reference each other (*"the push refused →* ``larkdocio-when-lark-refuses``*"*),
    and those names are directories in the pack, not sections of the guide. Derived from the
    same **directory sweep** that enrols the files, so a router added tomorrow excludes itself
    with no edit here — a hand-kept list would be the fifth copy this whole issue exists to
    avoid. ``test_every_excluded_router_name_is_really_a_ROUTER`` holds the exemption honest at
    both ends: each name must still be a real router, and must still be a name ``guide()`` does
    not have (so nothing can be quieted by dropping it in here).
    """
    names = set()
    for label in consumer_text.skill_pack_docs():
        parts = label[len(PACK_LABEL_PREFIX):].split("/")
        if len(parts) > 1:
            names.add(parts[0])
    return frozenset(names)


def _routing_addresses(text, exclude=frozenset()):
    """``[("routing-table", slug)]`` for the pack's bare-slug spelling, deduplicated."""
    seen, found = set(), []

    def note(slug):
        if slug not in exclude and slug not in seen:
            seen.add(slug)
            found.append(("routing-table", slug))

    for line in text.splitlines():
        row = line.strip()
        if len(row) > 1 and row.startswith("|") and row.endswith("|"):
            for cell in row[1:-1].split("|"):
                match = _TABLE_CELL_ADDRESS.fullmatch(cell.strip())
                if match:
                    note(match.group(1))
    for match in _PACK_SLUG_SPAN.finditer(text):
        note(match.group(1))
    return found


def citations_in(label, text, exclude=frozenset()):
    """Every address ``label``'s text carries, in the spellings that label is allowed to use."""
    found = _citations(text)
    if label.startswith(PACK_LABEL_PREFIX):
        found = found + _routing_addresses(text, exclude)
    return found


# --------------------------------------------------------------------------- #
# 2. THE CORPUS — the shared consumer corpus, plus the sources it does not hold.#
# --------------------------------------------------------------------------- #

#: ``(label, path, why this is not already in consumer_corpus())``. Each of these is text a
#: consumer or a contributor reads, carrying citations the shared corpus cannot see:
#:
#: * the two release documents' **repository-root** copies — the shared corpus enrols the
#:   *packaged* release notes (what a wheel-only consumer holds) and excludes the changelog
#:   from the dialect grep by a reasoned rule of its own. A citation, unlike internal
#:   vocabulary, is wrong in both copies and in both documents, and the root copies are what a
#:   reader browsing the repository or a release PR sees first;
#: * the **packaged changelog** — reachable through ``larkdocio.changelog()``, and the document
#:   the third instance of this defect actually shipped in;
#: * ``blocks/BLOCK_TYPES.md`` — the contributor reference, excluded from the dialect grep
#:   because its audience holds this repo. That exclusion is about *vocabulary*; a section
#:   address it cites raises for a contributor exactly as it does for a consumer.
EXTRA_SOURCES = (
    ("RELEASE_NOTES.md (repository root)", "RELEASE_NOTES.md"),
    ("CHANGELOG.md (repository root)", "CHANGELOG.md"),
    ("changelog() (the packaged CHANGELOG.md)", "src/larkdocio/CHANGELOG.md"),
    ("blocks/BLOCK_TYPES.md (packaged, contributor)", "src/larkdocio/blocks/BLOCK_TYPES.md"),
)


def citation_corpus():
    """``{label: text}`` — every surface a guide-section citation can ship in.

    The third member is the **copyable router skill pack** (``consumers/skills/``), enrolled by
    a **directory sweep** rather than a named list. The pack's whole job is to cite: each file
    answers a task shape with an address instead of an explanation, which makes it the densest
    concentration of section names outside the guide itself — and a copy that lives in someone
    else's repository, where a broken address is discovered by an agent mid-task rather than by
    a maintainer. A sweep is the only enrolment rule that cannot miss a router added tomorrow;
    ``tests/test_consumer_skill_pack.py`` asserts against the filesystem that it does not.
    """
    corpus = dict(consumer_text.consumer_corpus())
    for label, relative in EXTRA_SOURCES:
        corpus[label] = (REPO_ROOT / relative).read_text(encoding="utf-8")
    corpus.update(consumer_text.skill_pack_docs())
    return corpus


# --------------------------------------------------------------------------- #
# 3. THE WHITELIST — two classes, each with its reason, and each held honest.   #
# --------------------------------------------------------------------------- #

#: A placeholder, not an address: ``guide("<slug>")``, ``--section <name>``, ``guide("…")``.
#: These are shipped text teaching the SHAPE of the call — the angle brackets and the ellipsis
#: are how a reader is told to substitute their own name. Resolving one would be asking the
#: guide for a section literally called ``<slug>``. Both marks are needed: prose reaches for the
#: ellipsis where a code fence reaches for angle brackets, and a guard that knew only one of
#: them would report the other as a broken citation and teach the next author to write around
#: the guard instead of to the reader.
_PLACEHOLDER = re.compile(r"[<>]|\.\.\.|…")

#: A name the shipped text cites **because it refuses** — the demonstration is the point, so
#: resolving it would falsify the very sentence it appears in. Each entry carries its reason,
#: and ``test_every_whitelisted_name_is_really_a_refusal_demonstration`` holds both halves: the
#: name must still refuse, and it must still appear only in the teaching context named here.
REFUSAL_DEMOS = {
    "recipies": (
        "the guide's own misspelling demo: inside a `try:` / `except ValueError` block that "
        "shows the refusal names every section there is, so recovering from a wrong guess "
        "costs no second call. If this ever resolved, the demo would assert on a refusal that "
        "never came.",
        ("try:", "except ValueError"),
    ),
    "not a real release": (
        "the guide's own SIBLING-accessor refusal demo (LD-512): "
        "`larkdocio.release_notes(section=\"not a real release\")` is cited inside a `try:` / "
        "`except ValueError` block that shows the refusal points at `release_notes_sections`, "
        "the RIGHT index helper for that document rather than the guide's. The name has to be "
        "one `release_notes()` does not have, so resolving it would falsify the demonstration "
        "it is written to make.",
        ("except ValueError", "release_notes_sections"),
    ),
    "typo": (
        "the CLI's own unrecognised-name demonstration — `larkdocio guide --section typo > "
        "out.md` is cited to show that a refusal leaves stdout EMPTY rather than a "
        "half-written file. The name has to be one the guide does not have.",
        ("out.md",),
    ),
}


def _whitelisted(slug):
    """The reason ``slug`` is exempt, or ``None`` if it must resolve."""
    if _PLACEHOLDER.search(slug):
        return "placeholder — the shipped text is teaching the call's shape, not an address"
    if slug in REFUSAL_DEMOS:
        return REFUSAL_DEMOS[slug][0]
    return None


# --------------------------------------------------------------------------- #
# 4. THE CHECK — one function, so the real corpus and the planted defect below  #
#    are judged by identical code.                                             #
# --------------------------------------------------------------------------- #

def _exclusions_for(corpus):
    """The router-name exemption, computed once per sweep and only if the pack is in play."""
    if any(label.startswith(PACK_LABEL_PREFIX) for label in corpus):
        return router_names()
    return frozenset()


#: The root documents behind the two WINDOWED accessors. A release document's shipped copy is a
#: recent-N window (LD-540); the root file stays complete.
_ROOT_OF_WINDOWED_FORM = {
    "release_notes": "RELEASE_NOTES.md",
    "changelog": "CHANGELOG.md",
}

#: ``## [X.Y.Z]`` — a bare version address is a real, dated release section.
_VERSION_SLUG = re.compile(r"^\d+\.\d+\.\d+$")


def _evicted_by_the_window(form, slug, refusal):
    """The reason a citation is exempt because the WINDOW moved under it, or ``None``.

    **The third exemption class, and the only structural one (LD-658).** A release document's
    shipped copy carries a recent-N window while the root stays complete, so **every cut evicts
    the oldest section** — and a historical section that cites a release by its bare version
    (``release_notes(section="1.43.0")``) stops resolving the moment its subject falls out of the
    window. That citation was true when it was written, its section is dated history and is never
    edited, and the address is still good against the root document. Nothing is broken; the
    reader's copy simply no longer reaches that far back, which is what the accessor's
    **out-of-window** refusal says, in those words, distinctly from *unknown section*.

    Derived on all three counts, never listed: the slug must LOOK like a version, the accessor's
    own refusal must be the out-of-window one (an invented version still reddens — it refuses as
    unknown), and the ROOT document must still carry that section (so a citation of a release
    that never existed is not laundered through here). This is the D-111 discipline
    ``scripts/sync-packaged-notes.sh`` prints on every eviction: a guard over content an eviction
    can remove reads the root copy and keeps its wheel-facing arm conditional.
    """
    root_name = _ROOT_OF_WINDOWED_FORM.get(form)
    if root_name is None or not _VERSION_SLUG.match(slug):
        return None
    if not refusal.startswith("out-of-window section"):
        return None
    root = pathlib.Path(__file__).resolve().parents[1] / root_name
    if f"## [{slug}]" not in root.read_text(encoding="utf-8"):
        return None
    return (f"{slug} has been evicted from the shipped window of {root_name}; the address is "
            f"still good against the complete root document, and the citation sits in dated "
            f"history that is never edited (D-111)")


def unresolved_citations(corpus):
    """``[(label, form, slug, refusal)]`` for every cited section ``guide()`` will not serve."""
    exclude = _exclusions_for(corpus)
    broken = []
    for label, text in sorted(corpus.items()):
        for form, slug in citations_in(label, text, exclude):
            if _whitelisted(slug) is not None:
                continue
            try:
                resolve_citation(form, slug)
            except ValueError as refusal:
                first = str(refusal).split(".")[0]
                if _evicted_by_the_window(form, slug, str(refusal)) is not None:
                    continue
                broken.append((label, form, slug, first))
    return broken


def test_the_window_exemption_is_NARROW_in_all_three_directions():
    """The exemption above must not become a permission slip for any failing version address.

    Three arms, because the exemption has three conditions and dropping any one of them would
    launder a real defect: a version the root does not carry, a refusal that is *unknown* rather
    than *out-of-window*, and a non-version slug.
    """
    real = "out-of-window section '1.43.0' — the shipped copy carries a WINDOW"
    assert _evicted_by_the_window("release_notes", "9.99.9", real) is None, (
        "a version no root document carries must still redden")
    assert _evicted_by_the_window(
        "release_notes", "1.43.0", "unknown section '1.43.0'") is None, (
        "an UNKNOWN-section refusal is not an eviction and must still redden")
    assert _evicted_by_the_window("release_notes", "recipies", real) is None, (
        "a non-version slug is not an eviction case")
    assert _evicted_by_the_window("python", "1.43.0", real) is None, (
        "the guide is not a windowed release document")


def resolved_citation_census(corpus=None):
    """``(total, distinct, whitelisted)`` — what the sweep saw, for the floor assertion."""
    corpus = citation_corpus() if corpus is None else corpus
    exclude = _exclusions_for(corpus)
    total, names, exempt = 0, set(), set()
    for label, text in corpus.items():
        for _form, slug in citations_in(label, text, exclude):
            total += 1
            if _whitelisted(slug) is not None:
                exempt.add(slug)
            else:
                names.add(slug)
    return total, names, exempt


# --------------------------------------------------------------------------- #
# 5. THE GUARD                                                                 #
# --------------------------------------------------------------------------- #

def test_every_guide_section_citation_in_shipped_text_resolves():
    """The durable half of the slug-rot class: no shipped address raises.

    Failure names the document, the spelling and the slug, because those three are exactly
    what a fix needs — the refusal ``guide()`` itself raises already lists every section there
    is, so nothing here has to repeat the index.
    """
    broken = unresolved_citations(citation_corpus())
    assert not broken, (
        "shipped text cites guide sections that do not exist — the consumer's copy-paste "
        "raises ValueError:\n" + "\n".join(
            f"  {label}: {form} citation {slug!r} → {refusal}"
            for label, form, slug, refusal in broken)
        + "\n\nName the real slug (larkdocio.guide_sections()), or, if this is deliberate "
          "text about a refusal, add it to REFUSAL_DEMOS with its reason.")


@pytest.mark.parametrize("planted, why", [
    ("quick-start",
     "the README instance: the wheel's METADATA body's FIRST runnable line, whose own comment "
     "claimed the index had handed the reader this name"),
    ("permissions",
     "the pre-existing README instances — the real slug is permissions-what-to-ask-for"),
    ("attach-a-file-to-a-document-the-attachment-card",
     "the packaged-changelog instance: right name, missing the `recipe-` prefix the full "
     "heading derives"),
])
def test_the_guard_reddens_on_a_planted_broken_citation(planted, why):
    """DELIBERATE-DEFECT PROOF — each historically-shipped instance, replayed.

    The guard is only worth its runtime if it fails on the defect it was built for, so each
    address that really shipped broken is planted into a synthetic document and put through
    :func:`unresolved_citations` — the **same** function the real corpus goes through, not a
    re-implementation that could agree with the guard by construction.
    """
    document = f'Paste this:\n\n```python\nprint(larkdocio.guide("{planted}"))\n```\n'
    broken = unresolved_citations({"a planted document": document})
    assert broken == [("a planted document", "python", planted, broken[0][3])], (
        f"the guard did not catch {planted!r} — {why}")


def test_the_guard_reddens_on_a_broken_citation_in_a_COPIED_SKILL_FILE(monkeypatch):
    """DELIBERATE-DEFECT PROOF for the pack's enrolment — planted in situ, not in a synthetic
    corpus of one document.

    The pack is copied into a consumer's repository, so a rotted slug there is found by an
    agent in the middle of somebody else's task. The failure must name **the file and the
    slug**, because those two are what a fix needs and neither is guessable from the other.
    """
    dirty = dict(consumer_text.skill_pack_docs())
    assert dirty, "the skill pack is empty — this proof would be vacuous"
    victim = sorted(dirty)[0]
    dirty[victim] += '\n\nFor this, read `larkdocio.guide("recipe-publish-a-document")`.\n'
    monkeypatch.setattr(consumer_text, "skill_pack_docs", lambda: dirty)

    broken = unresolved_citations(citation_corpus())
    assert [(label, slug) for label, _form, slug, _refusal in broken] == [
        (victim, "recipe-publish-a-document")], broken

    message = "\n".join(f"  {label}: {form} citation {slug!r}"
                        for label, form, slug, _refusal in broken)
    assert victim in message and "recipe-publish-a-document" in message


def test_the_guard_reddens_on_a_ROTTED_ROUTING_TABLE_CELL(monkeypatch):
    """DELIBERATE-DEFECT PROOF for the pack's DOMINANT spelling — QA's own plant, made permanent.

    LD-499's fresh-eyes QA rotted one real routing-table cell —
    ``recipe-the-base-write-handshake`` → ``…-THAT-DOES-NOT-EXIST`` in
    ``larkdocio-write-rows-and-cells`` — ran the **full** suite, and got
    ``16562 passed, 3 skipped``: a dead pointer shipping inside a router with every guard
    green, because the bare-cell spelling was extracted by nothing. That is the fifth-copy rot
    this file exists to make impossible, so the plant lives here as a permanent test rather
    than as a paragraph in a review.

    The rot is planted **in situ** (the real file's real cell, edited in memory) and the
    failure must name the file and the slug — the two things a fix needs.
    """
    live = "recipe-the-base-write-handshake"
    rotted = f"{live}-THAT-DOES-NOT-EXIST"
    victim = "consumers/skills/larkdocio-write-rows-and-cells/SKILL.md"

    dirty = dict(consumer_text.skill_pack_docs())
    assert victim in dirty, f"{victim} is gone — re-point this proof at a real routing table"
    assert f"| `{live}` |" in dirty[victim], (
        f"{victim} no longer routes at {live!r} in a table cell — plant the rot in whatever "
        "cell it does route at; do not delete the proof")
    dirty[victim] = dirty[victim].replace(f"| `{live}` |", f"| `{rotted}` |")
    monkeypatch.setattr(consumer_text, "skill_pack_docs", lambda: dirty)

    broken = unresolved_citations(citation_corpus())
    assert [(label, form, slug) for label, form, slug, _refusal in broken] == [
        (victim, "routing-table", rotted)], broken

    message = "\n".join(f"  {label}: {form} citation {slug!r}"
                        for label, form, slug, _refusal in broken)
    assert victim in message and rotted in message


#: Text a router really writes that is **not** an address, each with the reason it must not
#: bite. The arm exists so an author can keep cross-referencing; an over-tightening that starts
#: reading these as guide sections reddens here rather than at an author's desk.
_MUST_NOT_BITE = (
    ("| Rows, columns and cells | `larkdocio-write-rows-and-cells` |",
     "an inter-router reference in a cell — routers route at each other"),
    ("- The push refused → `larkdocio-when-lark-refuses`",
     "an inter-router reference in a bullet"),
    ("- `larkdocio guide --section which-level-does-this-ask-need`",
     "a console invocation — AC3's verb guard owns this, and the CLI arm already resolves the "
     "section name inside it"),
    ("| The two calls | `larkdocio.roundtrip.pull()` |",
     "a dotted Python call sitting in a table cell"),
    ("Refresh it with `scripts/update_larkdocio.sh`, then copy the pack again.",
     "a script path"),
    ("This pack was copied from a `larkdocio` checkout and points at that wheel.",
     "the bare distribution name (no version literal here — "
     "`tests/test_version_bump_tolerance.py` forbids freezing the packaged one)"),
    ("The whole-document compare-and-swap is `STALE_DOCUMENT`; anchor with `AnchorById`.",
     "ordinary code identifiers — an underscore and a CamelCase name are not slugs"),
    ("Preview with `larkdocio roundtrip push -o ./edit/`, then add `--apply`.",
     "a command span and a bare option"),
)


@pytest.mark.parametrize("line, why", _MUST_NOT_BITE)
def test_the_routing_table_arm_does_NOT_bite_on_a_non_address(line, why):
    """MUST-NOT-BITE PROOF — judged by the same function the real pack goes through.

    The looser reading is granted to the pack because its files are nothing but addresses; the
    price of getting that wrong is an author who stops cross-referencing to keep the suite
    quiet. So every non-address spelling the pack actually contains is pinned here.
    """
    label = f"{PACK_LABEL_PREFIX}larkdocio-start-here/SKILL.md"
    broken = unresolved_citations({label: line})
    assert not broken, f"the routing-table arm bit on {why}: {broken}"


def test_every_excluded_router_name_is_really_a_ROUTER():
    """The one exemption the routing arm carries, held honest at both ends.

    A name is exempt because it addresses a **file in the pack**, not a section of the guide.
    So each must still be a directory the sweep finds (an exemption for a router that was
    deleted is dead weight), and each must still be a name ``guide()`` does **not** answer — if
    one ever became a real section, exempting it would hide a live address.
    """
    names = router_names()
    assert len(names) >= 5, f"only {sorted(names)} — the router sweep stopped matching"
    on_disk = {path.parent.name for path in consumer_text.skill_pack_files()}
    assert names <= on_disk, sorted(names - on_disk)
    for name in sorted(names):
        with pytest.raises(ValueError):
            larkdocio.guide(section=name)


# --------------------------------------------------------------------------- #
# 5b. THE COVERAGE CENSUS — counted off the corpus, not pinned to a number.     #
# --------------------------------------------------------------------------- #
#
# LD-483 asserted this arm's reach with three static floors — `routing-table >= 35`,
# `cli >= 10`, `total >= 50` — against counts that were 41 / 16 / 57 on the day. That is a
# guard whose reach DECAYS: every router added afterwards widens the gap between the floor and
# the truth, so an extraction regression can eat the accumulated headroom in silence, and the
# only remedy on offer is re-cutting three literals on every landing that touches the pack —
# the per-landing ceremony the 2026-08 round exists to abolish.
#
# LD-512 replaces the literals with a CENSUS the corpus counts for itself, spelled
# **deliberately differently** from the extractor it audits (a lone backticked cell found by
# splitting the row, not by `_TABLE_CELL_ADDRESS`; a plain substring search for the console
# verb, not `_CLI_CITATION`) — a census sharing the extractor's own regexes could only ever
# agree with it.
#
# ONE MEASURED FACT THAT BOUNDS WHAT ANY COUNT-BASED ARM CAN DO, recorded here so nobody
# re-derives it: the two routing-table arms are **fully redundant on today's pack** — arm A
# alone sees 41 addresses, arm B alone sees the same 41. So dropping *one* arm is invisible to
# any count, here or in the version this supersedes. What a count catches is a regression that
# costs the pack addresses outright, and what `test_every_routing_cell_the_pack_writes_is_
# ACCOUNTED_FOR` below catches is a cell nobody can explain. Neither is a substitute for the
# other.

#: A table cell whose entire content is one backticked token — the shape a routing row writes
#: an address in. Deliberately NOT :data:`_TABLE_CELL_ADDRESS`: this one is applied to a cell
#: already split off the row, so it is a second opinion rather than the same one twice.
_LONE_BACKTICKED_CELL = re.compile(r"^`[^` ]+`$")


def routing_cell_census():
    """``[(label, row)]`` — every pack table row that carries a lone backticked cell.

    That is the population the routing-table arm is supposed to reach, and it moves with the
    pack: add a router and the census grows on its own, which is the whole point.
    """
    census = []
    for label, text in sorted(consumer_text.skill_pack_docs().items()):
        for line in text.splitlines():
            row = line.strip()
            if len(row) <= 1 or not (row.startswith("|") and row.endswith("|")):
                continue
            if set(row) <= set("|- :"):                       # the header separator
                continue
            if any(_LONE_BACKTICKED_CELL.match(cell.strip()) for cell in row[1:-1].split("|")):
                census.append((label, row))
    return census


def cli_occurrence_census():
    """``[(label, window)]`` — every ``guide --section`` occurrence in the pack, found by a
    plain substring search so a regression in :data:`_CLI_CITATION` cannot hide inside the
    census that measures it."""
    census = []
    for label, text in sorted(consumer_text.skill_pack_docs().items()):
        for match in re.finditer(r"guide\s+--section", text):
            census.append((label, text[match.start():match.start() + 200]))
    return census


#: How far below its own census an arm may fall before this reddens.
#:
#: **Argued from the observed counts, not picked round.** Measured 2026-08-19: the routing
#: census is **46** rows and the arm extracts **41** addresses from them — and all **5** of the
#: shortfall are accounted for exactly, by the router-name exclusion (:func:`router_names`),
#: which is a deliberate non-address. That is a **10.9%** structural shortfall. The CLI census
#: is **17** occurrences, every one of them covered — a **0%** shortfall. So the worst observed
#: shortfall is 10.9%, and 20% is that with the same again in headroom: the exclusion set could
#: very nearly double *relative to the pack* before anyone re-cut a literal, while the failure
#: this exists to catch costs several addresses at once and lands outside the band.
#:
#: Compare what it replaces: ``>= 35`` tolerated a 24% shortfall on the day it was written and
#: would tolerate 42% once the pack reaches 60 rows. This band does not loosen with growth.
_CENSUS_SLACK = 0.20


def test_every_routing_cell_the_pack_writes_is_ACCOUNTED_FOR():
    """The exact arm, and the one with no slack in it: **residual zero**.

    Every lone backticked cell in a router is either an address this file extracts or a name
    the router-name exclusion owns. Nothing else may sit in one unexplained, because
    "unexplained" is precisely how 41 addresses sat unchecked while the suite was green.
    """
    exclude = router_names()
    unaccounted = []
    for label, row in routing_cell_census():
        if _routing_addresses(row, exclude):
            continue
        cells = [cell.strip().strip("`") for cell in row[1:-1].split("|")]
        if any(cell in exclude for cell in cells):
            continue                                   # a router cross-reference, by design
        unaccounted.append((label, row))
    assert not unaccounted, (
        f"{len(unaccounted)} routing cell(s) are neither extracted as an address nor a known "
        f"router name: {unaccounted} — either the extraction arm has stopped seeing a spelling "
        "the pack uses, or the pack has started writing a bare backticked token that is not an "
        "address. Both are the LD-483 defect; decide which, in writing, before quieting this")


def test_the_routing_table_arm_reaches_the_MAJORITY_of_the_packs_addresses():
    """Coverage is the half a passing guard cannot demonstrate about itself.

    Before this arm existed the pack's checked addresses were the 16 written as calls or
    console options while 41 more sat in table cells unchecked, and the suite was green. The
    reach is asserted **per spelling** so a regression that silently drops the bare-cell arm
    reddens here instead of quietly halving the coverage again.

    **Superseded in part by LD-512, reason preserved.** The reason — per-spelling reach, watched
    rather than assumed — is unchanged and is why this test still exists. Only the *conclusion*
    moved: the three static floors (``35`` / ``10`` / ``50``) become the corpus's own census
    with :data:`_CENSUS_SLACK` behind it, because a static floor's reach decays as the corpus
    grows and re-cutting it per landing is the ceremony this round abolishes.
    """
    pack = consumer_text.skill_pack_docs()
    exclude = router_names()
    by_form = {}
    for label, text in pack.items():
        for form, slug in citations_in(label, text, exclude):
            if _whitelisted(slug) is None:
                by_form.setdefault(form, set()).add(slug)

    routing_census = len(routing_cell_census())
    routing_floor = int(routing_census * (1 - _CENSUS_SLACK))
    seen_routing = len(by_form.get("routing-table", ()))
    assert seen_routing >= routing_floor, (
        f"the routing-table arm sees {seen_routing} addresses across the {routing_census} "
        f"routing cells the pack actually writes — below the {routing_floor} this census "
        f"allows ({_CENSUS_SLACK:.0%} slack). The pack's dominant citation spelling has stopped "
        "being extracted. Do NOT widen the slack to make this green: find the spelling the "
        "extractor stopped seeing, or — if the pack really did start writing non-addresses in "
        "those cells — say so at router_names() / REFUSAL_DEMOS, where a deliberate "
        "non-address belongs")

    cli_census = len(cli_occurrence_census())
    cli_floor = int(cli_census * (1 - _CENSUS_SLACK))
    seen_cli = len(by_form.get("cli", ()))
    assert seen_cli >= cli_floor, (
        f"the console spelling stopped being extracted: {seen_cli} distinct addresses against "
        f"the {cli_census} `guide --section` occurrences the pack writes (floor {cli_floor})")

    every = set().union(*by_form.values())
    total_census = routing_census + cli_census
    total_floor = int(total_census * (1 - _CENSUS_SLACK))
    assert len(every) >= total_floor, (
        f"the pack cites only {len(every)} distinct addresses against a census of "
        f"{total_census} citation sites (floor {total_floor})")
    for form, slug in sorted((form, slug) for form, slugs in by_form.items() for slug in slugs):
        resolve_citation(form, slug)    # raises ValueError if the pack points at nothing


# --------------------------------------------------------------------------- #
# THE SIBLING-ACCESSOR ARM, watched biting — both arms, because the corpus       #
# deliberately teaches one of them a REFUSAL (LD-512).                          #
# --------------------------------------------------------------------------- #
#
# MEASURED POPULATION, 2026-08-19, stated so nobody mistakes this arm for a busy one: the whole
# shipped corpus carries **exactly one** literal sibling-accessor address, and it is the taught
# refusal below. Every other sibling call the guide teaches passes a slug computed from that
# document's own ``*_sections()`` index, which cannot rot. That is why this landed as insurance
# at XS rather than as a fix — and why it is watched biting on a forged citation here, since a
# guard whose live population is one whitelisted entry would otherwise be indistinguishable
# from one that matches nothing at all.

def test_a_sibling_accessor_citation_that_points_at_NOTHING_is_caught():
    """The bite. Each sibling address is resolved through **its own** accessor, so a heading
    rename in a sibling document cannot strand a shipped literal the way it silently could
    before this arm existed."""
    forged = {"a doc citing sibling sections that do not exist":
              'larkdocio.writer_brief(section="a-heading-nobody-ever-wrote")\n'
              'larkdocio.release_notes(section="9.9.9")\n'
              'larkdocio.changelog(section="nope")\n'}
    broken = unresolved_citations(forged)
    assert sorted(row[1] for row in broken) == ["changelog", "release_notes", "writer_brief"], (
        f"the sibling arm did not catch all three forged addresses: {broken}")


def test_the_TAUGHT_sibling_REFUSAL_stays_resolvable_as_a_refusal():
    """The must-not-bite arm, and the reason the whitelist is here from day one rather than
    added after the first red: the guide **teaches** ``release_notes(section="not a real
    release")`` inside a ``try:`` / ``except ValueError`` block, to show that a wrong sibling
    name is refused by the RIGHT index helper. Reddening on it would delete a demonstration to
    satisfy a guard."""
    taught = {"the guide's own refusal demonstration":
              'try:\n'
              '    larkdocio.release_notes(section="not a real release")\n'
              'except ValueError as refusal:\n'
              '    assert "release_notes_sections" in str(refusal)\n'}
    assert _citations(taught["the guide's own refusal demonstration"]), (
        "the arm no longer even extracts the taught citation — the must-not-bite proof would "
        "be vacuous")
    assert unresolved_citations(taught) == []


def test_the_guard_catches_the_command_line_spelling_too():
    """The CLI spelling is a citation as much as the Python one: a consumer who pastes
    ``larkdocio guide --section <wrong>`` gets the same refusal on stderr and an empty stdout,
    so the sweep may not be Python-only."""
    document = "Run `larkdocio guide --section quick-start` to read it."
    assert [row[2] for row in unresolved_citations({"cli doc": document})] == ["quick-start"]


def test_the_recipe_matcher_would_have_missed_the_defect_this_guard_catches():
    """WHY the resolver is ``guide()``'s own — pinned against the code, not asserted in prose.

    ``guide_recipes._slug`` strips the ``Recipe: `` label before slugifying, so for the same
    heading the two matchers answer **different names**, and the recipe matcher's answer is the
    one the packaged changelog shipped. A guard resolving through it would have passed.
    """
    import guide_recipes

    heading = "Recipe: attach a file to a document (the 📎 attachment card)"
    recipe_name = guide_recipes._slug(heading.split("Recipe: ", 1)[1])
    guide_name = f"recipe-{recipe_name}"

    assert recipe_name in {spec.slug for spec in guide_recipes.RECIPE_SPECS}, (
        "the recipe matcher no longer answers this name — if the two matchers have been made "
        "to agree, say so here; until then this is the divergence that let the defect ship")
    with pytest.raises(ValueError):
        larkdocio.guide(section=recipe_name)
    assert larkdocio.guide(section=guide_name).startswith("### Recipe: attach a file")


def test_every_whitelisted_name_is_really_a_refusal_demonstration():
    """A whitelist entry is a claim about the shipped text, so it is checked against it.

    Both halves: the name must still be one ``guide()`` refuses (an entry that started
    resolving is dead weight hiding a real address), and it must still appear in the teaching
    context that earns the exemption — so nobody can quiet a genuine broken citation by adding
    its slug here.
    """
    corpus = citation_corpus()
    for slug, (_reason, context_markers) in REFUSAL_DEMOS.items():
        with pytest.raises(ValueError):
            larkdocio.guide(section=slug)
        windows = []
        for text in corpus.values():
            for match in re.finditer(re.escape(slug), text):
                windows.append(text[max(0, match.start() - 400): match.end() + 400])
        assert windows, f"{slug!r} is whitelisted and no longer appears in shipped text at all"
        assert any(all(marker in window for marker in context_markers) for window in windows), (
            f"{slug!r} is whitelisted as a refusal demonstration but no occurrence sits in one "
            f"(looked for {context_markers!r}) — either the demo was rewritten, in which case "
            "update the entry, or this is a real broken citation wearing the exemption")


def test_the_sweep_actually_reaches_the_documents_it_claims_to():
    """A grep that stops matching passes silently, so the corpus is asserted non-empty **per
    named surface** — the packaged guide, the wheel's METADATA body, the release documents in
    both copies, the writer brief, the contributor reference, the CLI pages and the
    docstrings. Coverage is the half a passing grep cannot demonstrate about itself."""
    corpus = citation_corpus()
    for expected in ("guide()", "README.md (the wheel METADATA body)",
                     "release_notes() (the packaged RELEASE_NOTES.md)", "writer_brief()",
                     "RELEASE_NOTES.md (repository root)", "CHANGELOG.md (repository root)",
                     "changelog() (the packaged CHANGELOG.md)",
                     "blocks/BLOCK_TYPES.md (packaged, contributor)",
                     "larkdocio guide --help"):
        assert expected in corpus, f"{expected} dropped out of the citation corpus"
    assert any(label.startswith("help(larkdocio") for label in corpus), (
        "the shipped docstrings dropped out of the citation corpus")

    # The copyable router pack, enrolled by directory sweep — asserted against the sweep
    # itself rather than against a name, so a router added tomorrow is covered with no edit.
    pack = consumer_text.skill_pack_docs()
    assert pack, "the copyable skill pack produced nothing — the sweep stopped matching"
    assert set(pack) <= set(corpus), sorted(set(pack) - set(corpus))

    total, resolvable, exempt = resolved_citation_census(corpus)
    assert total >= 25, (
        f"the sweep found only {total} citations across {len(corpus)} surfaces — the "
        "extraction patterns have stopped matching, which is a green guard guarding nothing")
    assert len(resolvable) >= 8, f"only {len(resolvable)} distinct real addresses cited"
    assert exempt <= set(REFUSAL_DEMOS) | {"<slug>", "<name>", "…"}, (
        f"an unexpected exempt spelling appeared: {sorted(exempt)}")
