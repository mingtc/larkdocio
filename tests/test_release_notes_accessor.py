"""EVERY DOCUMENT WRITTEN FOR A CONSUMER HAS AN ACCESSOR — ``release_notes()`` / ``changelog()``.

Why this module exists
---------------------
``GUIDE.md`` had ``guide()``. ``write/README.md`` had ``writer_brief()``.
``RELEASE_NOTES.md`` and ``CHANGELOG.md`` had **nothing** — they shipped inside the wheel
(the packaging round put them there) and the public API offered no way to read them. The
consumer's own probe was::

    [n for n in dir(larkdocio) if n in ('guide','writer_brief','release_notes','changelog')]
    # -> ['guide', 'writer_brief']

Worse than a missing convenience: the shipped guide told the reader *"Before you re-pin, read
`larkdocio-RELEASE_NOTES.md`"* — the copy the refresh script drops **beside the vendored
wheel**, which a consumer who ran a plain ``pip install`` never receives — and then noted that
both documents "also ship inside the wheel" while giving no way to open them. That is a
**dangling pointer inside shipped text**, and it is verbatim the defect ``writer_brief()``
exists to fix: *"a consumer on a vendored wheel could read the citation and not the
document."* Two upgrade-critical facts were stranded behind it — what a whole-block edit does
to a reviewer's inline comment anchors, and the *contacts data range* console setting @mention
resolution needs.

**This overturns an earlier recommendation.** The consumer-critique intake reasoned that
*packaging* the files was enough and a dedicated accessor was unnecessary. A real consumer
agent then asked for exactly this on day one, hit the dangling pointer, and had to reach for
``importlib.resources`` by hand. The reversal is by **use**, not by drift — the earlier
reasoning was defensible on the evidence it had, and day-one consumer behavior is better
evidence.

The wheel-only arms (why a source-tree test is not enough)
----------------------------------------------------------
The whole defect is a **wheel-only** concern, so a test that imports the source tree would
pass while the artifact stayed broken. Two arms close that:

* :func:`test_the_accessors_work_from_the_BUILT_WHEEL_with_no_src_tree_importable` imports the
  package out of an **unpacked wheel** and pins ``larkdocio.__file__`` inside it, so the
  source tree provably is not what answered; and
* :func:`test_the_accessors_work_from_an_INSTALLED_WHEEL_IN_A_CLEAN_VENV` ``pip install``\\ s
  the wheel into a fresh virtualenv and probes it there.

Both run fully offline. Byte-identity between each root file and its in-package copy is
already pinned by ``tests/test_shipped_notes.py``'s drift guard, and the wheel ``RECORD``
membership by its build arm — cited here rather than re-tested.
"""
import importlib
import pathlib
import re
import subprocess
import sys
import sysconfig
import zipfile

import pytest

import consumer_text
import private_tree
import front_door
import larkdocio
from larkdocio.guide import DOC_ACCESSORS
from test_comment_anchor_claim_guard import packaged_markdown
from test_shipped_notes import NOTES, _built_wheel_record

# LD-370 — CONFORMANCE-tier: the promise must be READABLE from the wheel — release_notes() is a shipped API.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "larkdocio"

#: The discovery accessors — the whole point is that ``dir()`` is not how a consumer finds any
#: of them. LD-549 added the fifth, ``lark_setup`` (the Lark-application walkthrough), for the
#: same reason the release documents got theirs: the wheel carried the document and the public
#: API offered no way to open it, so the README could only NAME it in plain text. The tuple is
#: widened, never narrowed — every arm below runs over all of it.
DISCOVERY_ACCESSORS = ("guide", "writer_brief", "release_notes", "changelog", "lark_setup")

#: A ``## [X.Y.Z] — date`` release header, the section shape both documents are built from.
_RELEASE_HEADER = re.compile(r"^## \[\d+\.\d+\.\d+\] — \d{4}-\d{2}-\d{2}", re.MULTILINE)

#: The two upgrade-critical facts the report named as stranded inside the release notes.
#: A content check that makes the accessor's *purpose* testable rather than just its return
#: type: these are the sentences a consumer needs at the moment they decide to re-pin.
UPGRADE_CRITICAL_PHRASES = (
    "contacts data range",          # the @mention precondition that cost days to find
    "inline comment",               # what a whole-block edit does to a reviewer's anchors
)

#: **LD-540 — the second half of the claim, which the window made necessary and which the
#: original never checked.** The wheel now carries a recent-N window of the release notes, so a
#: fact announced in an old release stops being reachable *through the notes*. That is the
#: intended narrowing — the notes exist for someone deciding whether to re-pin, and they are
#: explicitly not a substitute for the guide — but it must not mean the FACT left the wheel. So
#: for every upgrade-critical phrase the window no longer carries, the wheel has to carry it on
#: another surface a consumer can open, and that surface is named here rather than assumed. Both
#: are read through their public accessors, so this is what a consumer's own call returns.
UPGRADE_CRITICAL_FALLBACK_SURFACES = ("guide", "writer_brief")

#: **An upgrade-critical phrase the window CURRENTLY carries** — the subject of the second arm
#: below, which asks whether the accessor still does the job it was added for.
#:
#: Deliberately its own constant rather than a third entry in ``UPGRADE_CRITICAL_PHRASES``:
#: that tuple is the consumer report's **dated enumeration** of what was stranded, and growing
#: it would rewrite a historical finding. This one is expected to be **re-pointed** as the
#: window slides — LD-560 opened ``[1.41.0]``, which slid ``[1.33.0]`` (where both historical
#: phrases lived) out of the wheel, and that is the intended narrowing, not a defect. The
#: phrase chosen is the one fact ``RELEASE_NOTES.md``'s own shape rule makes **mandatory in
#: every section** — the explicit dependency statement under *Upgrade & compatibility* — so
#: re-pointing is only ever needed if that rule changes. LAST-VERIFIED 2026-08-25.
IN_WINDOW_UPGRADE_CRITICAL_PHRASE = "dependency moved"


# --------------------------------------------------------------------------- #
# AC1 — the two accessors ship, exported, docstringed, reading the RESOURCE.    #
# --------------------------------------------------------------------------- #

def test_the_consumers_own_probe_now_finds_all_four_accessors():
    """AC1: the report's own one-liner. ``dir()`` was the only discovery mechanism there
    was, and it returned two of four."""
    found = [n for n in dir(larkdocio) if n in DISCOVERY_ACCESSORS]
    assert sorted(found) == sorted(DISCOVERY_ACCESSORS), (
        f"the public package still does not expose every packaged document: {found}"
    )


def test_both_accessors_are_public_exports():
    """AC1: exported in ``__all__``, not merely reachable — ``from larkdocio import *`` and
    every ``__all__``-driven enumeration (the dialect guard's docstring walk included) has to
    see them."""
    for name in ("release_notes", "changelog"):
        assert callable(getattr(larkdocio, name)), f"larkdocio.{name} is not callable"
        assert name in larkdocio.__all__, f"{name} is not in larkdocio.__all__"


def test_release_notes_returns_the_packaged_notes_with_a_release_section():
    """AC1: non-empty text carrying a known section header — a zero-byte or truncated
    resource cannot pass."""
    text = larkdocio.release_notes()
    assert isinstance(text, str) and text.strip()
    assert text.startswith("# Release notes"), text[:80]
    assert _RELEASE_HEADER.search(text), "the notes carry no '## [X.Y.Z] — date' section"
    assert "INCLUDE" in text and "EXCLUDE" in text, (
        "the notes lost the relevance criteria their header states"
    )


def test_changelog_returns_the_packaged_changelog_with_a_release_section():
    text = larkdocio.changelog()
    assert isinstance(text, str) and text.strip()
    assert _RELEASE_HEADER.search(text), "the changelog carries no '## [X.Y.Z] — date' section"


def test_the_two_accessors_return_DIFFERENT_documents():
    """The distinction is the whole reason there are two: the notes are the filtered view,
    the changelog the per-release log. One accessor returning the other's text would satisfy
    every shape check above.

    TRANSFORMED by LD-691 (maintainer ruling 2): the crossed-resources check used to be "the changelog is
    the longer one", true while it was the internal log. The packaged changelog is now the public
    one, which starts at the last release made before the project was public and is far
    shorter, so the check reads each document's own header instead — a crossed pair still reddens."""
    notes, log = larkdocio.release_notes(), larkdocio.changelog()
    assert notes != log
    assert log.startswith("# Changelog"), "changelog() does not return the changelog"
    assert notes.startswith("# Release notes"), "release_notes() does not return the notes"


def test_each_accessor_reads_its_own_packaged_resource():
    """AC1: the **packaged** resource, via ``importlib.resources`` — the same contract
    ``guide()`` / ``writer_brief()`` hold, so it resolves identically from a source checkout
    and from an installed wheel where no ``src/`` tree exists."""
    import importlib.resources as ir

    for name, resource in (("release_notes", "RELEASE_NOTES.md"),
                           ("changelog", "CHANGELOG.md")):
        packaged = ir.files("larkdocio").joinpath(resource).read_text(encoding="utf-8")
        assert getattr(larkdocio, name)() == packaged, (
            f"{name}() must read the PACKAGED resource, not a src/ path"
        )


def test_the_accessor_module_opens_no_filesystem_path():
    """AC1, the mechanism rather than the result: ``guide.py`` reaches resources only through
    ``importlib.resources``. A ``Path(...)`` / ``open(...)`` in there would work from a source
    checkout and fail from a zipped wheel — the failure this module exists to prevent. (The
    same assertion the writer-brief accessor is held to.)"""
    source = (SRC / "guide.py").read_text(encoding="utf-8")
    assert "open(" not in source and "Path(" not in source
    for resource in ("RELEASE_NOTES.md", "CHANGELOG.md"):
        assert resource in source, f"guide.py does not name the {resource} resource"


def test_each_docstring_states_WHAT_THE_DOCUMENT_IS_FOR():
    """AC1: the two documents are easy to confuse, so each docstring has to say which view it
    is — the notes are the **consumer-filtered** view, the changelog the **project's
    changelog** (the public one, LD-691). A consumer choosing between them reads only these."""
    notes_doc = larkdocio.release_notes.__doc__ or ""
    log_doc = larkdocio.changelog.__doc__ or ""
    assert "filtered" in notes_doc.lower(), (
        "release_notes()'s docstring must say it is the filtered, consumer-facing view"
    )
    assert "CHANGELOG" in notes_doc, "it must name the document it is distinct from"
    # TRANSFORMED by LD-691 (maintainer ruling 2): the packaged changelog is the PUBLIC changelog, so the
    # docstring must say THAT (and the older-history pointer), no longer "internal engineering log".
    assert "project's changelog" in log_doc.lower() and "earlier versions" in log_doc.lower(), (
        "changelog()'s docstring must say it is the project's changelog and where earlier "
        "versions are recorded"
    )
    assert "internal engineering log" not in log_doc.lower(), (
        "changelog()'s docstring still calls the shipped document the internal log"
    )
    assert "RELEASE_NOTES" in log_doc, "it must point at the consumer-facing counterpart"


def test_the_release_notes_carry_the_upgrade_critical_facts_that_were_stranded():
    """The purpose check. An accessor that returns *a* document is not the fix; the fix is that
    the facts a consumer needs before re-pinning are **reachable**.

    **LD-540 widened this from one surface to the wheel, and it got stronger.** It used to assert
    both phrases were in ``release_notes()``. The wheel now carries a recent-N window of the notes,
    so a fact announced in an old release stops being in that document — by decision, because the
    notes serve someone deciding whether to re-pin and are explicitly not a substitute for the
    guide. What must NOT happen is the fact leaving the wheel, and that is now what is checked: a
    phrase is either still in the notes, or it is on a named fallback surface a consumer can open
    with a public call. Nothing is excused; every phrase must land somewhere, and the failure
    message says which surfaces were searched.

    **What it used to prove and no longer can:** that ``release_notes()`` alone carries every
    upgrade-critical fact ever announced. Under a window that is not a property of a correct tree.
    """
    surfaces = {"release_notes()": larkdocio.release_notes()}
    for name in UPGRADE_CRITICAL_FALLBACK_SURFACES:
        accessor = getattr(larkdocio, name)
        surfaces[f"{name}()"] = (
            accessor(full=True) if name == "guide" else accessor()
        )
    unreachable = {
        phrase: sorted(surfaces)
        for phrase in UPGRADE_CRITICAL_PHRASES
        if not any(phrase in text for text in surfaces.values())
    }
    assert not unreachable, (
        f"an upgrade-critical fact is reachable from NO surface the wheel carries: {unreachable}"
    )
    # And the notes still carry upgrade-critical content of their own, or this test stopped
    # exercising the accessor it was written for. Asked of a phrase the window CURRENTLY
    # carries: the two historical phrases have both aged out of it (see the constant), and
    # asking it of them would fail for the one reason LD-540 decided was correct.
    assert IN_WINDOW_UPGRADE_CRITICAL_PHRASE in surfaces["release_notes()"], (
        "release_notes() carries no upgrade-critical fact at all — the window has narrowed "
        "past the point where the accessor serves the purpose it was added for"
    )


# --------------------------------------------------------------------------- #
# AC2 — the guide's DANGLING POINTER. A pure guard, driven red on demand.       #
# --------------------------------------------------------------------------- #

#: ``{document: the accessor that reads it}`` — a shipped-text block that cites one must name
#: the other, or a wheel-only reader is told to read something they cannot open.
NOTES_ACCESSORS = {
    "RELEASE_NOTES.md": "release_notes()",
    "CHANGELOG.md": "changelog()",
}


def unreachable_notes_citations(text, accessors=None):
    """``[(document, block)]`` for every block of ``text`` that cites a release document
    without naming the accessor that reads it.

    **Block-level on purpose** (the anti-rot rule the writer-brief citation guard established):
    a reachability note somewhere else in the document does not help the consumer reading the
    paragraph that cites it. That is exactly how the dangling pointer survived — the guide *did*
    say both files "also ship inside the wheel", three sentences from an instruction to read a
    file only a vendored-wheel consumer receives.
    """
    accessors = NOTES_ACCESSORS if accessors is None else accessors
    offenders = []
    for block in re.split(r"\n\n+", text):
        for document, accessor in accessors.items():
            if document in block and accessor not in block:
                offenders.append((document, block))
    return offenders


def test_no_guide_block_cites_a_release_document_without_naming_its_accessor():
    """AC2: the dangling pointer, fixed and guarded. The ``vendor/`` copy may still be
    mentioned as a convenience — what may not happen is a block whose only instruction is to
    read a file a plain ``pip install`` does not produce."""
    offenders = unreachable_notes_citations(larkdocio.guide(full=True))
    assert not offenders, (
        "a shipped-guide block sends the reader to a release document without saying how to "
        "read it from the wheel:\n\n"
        + "\n\n".join(f"[{document}]\n{block}" for document, block in offenders)
    )


def test_the_guide_still_tells_the_reader_to_read_the_notes_before_re_pinning():
    """AC2's other half: the instruction must survive the fix. Deleting the sentence would
    also empty the guard, and the advice is correct — read the notes before you re-pin."""
    blocks = [b for b in re.split(r"\n\n+", larkdocio.guide(full=True))
              if "release_notes()" in b and "re-pin" in b]
    assert blocks, (
        "the guide no longer tells a consumer to read the release notes before re-pinning"
    )


def test_the_dangling_pointer_guard_BITES_on_the_ORIGINAL_wording():
    """AC2, red-then-green over the same function that guards: restore the shipped sentence
    as it was and the guard reddens, naming the document."""
    original = (
        "**Before you re-pin, read `larkdocio-RELEASE_NOTES.md`.** It is the filtered view "
        "of what changed *that affects you*. `larkdocio-CHANGELOG.md` is the full internal "
        "log next to it. Both documents also ship inside the wheel, so they travel with the "
        "installed package."
    )
    offenders = unreachable_notes_citations(original)
    assert sorted(document for document, _block in offenders) == [
        "CHANGELOG.md", "RELEASE_NOTES.md"
    ], "the guard did not catch the original dangling pointer"

    fixed = original + " Read them with `larkdocio.release_notes()` and `larkdocio.changelog()`."
    assert unreachable_notes_citations(fixed) == []


def test_the_guard_is_BLOCK_scoped_not_document_scoped():
    """The precise claim: a reachability note in a *different* block does not excuse the
    citing block. Without this, the fix could be a footnote and the defect would persist."""
    two_blocks = (
        "Before you re-pin, read `larkdocio-RELEASE_NOTES.md`.\n\n"
        "Elsewhere: read it with `larkdocio.release_notes()`.\n"
    )
    assert [document for document, _ in unreachable_notes_citations(two_blocks)] == [
        "RELEASE_NOTES.md"
    ]


# --------------------------------------------------------------------------- #
# AC3 — the guarded consumer corpus reads what the ACCESSOR returns.            #
# --------------------------------------------------------------------------- #

RELEASE_NOTES_LABEL = "release_notes() (the packaged RELEASE_NOTES.md)"


def test_the_corpus_enrols_what_the_release_notes_ACCESSOR_returns():
    """AC3: the dialect guard must grep the text the accessor hands a consumer, not a
    filesystem read that happens to sit beside it. Same shape as ``guide()`` /
    ``writer_brief()``, so all three enrolments are the accessor's own output."""
    docs = consumer_text.shipped_docs()
    assert RELEASE_NOTES_LABEL in docs, sorted(docs)
    assert docs[RELEASE_NOTES_LABEL] == larkdocio.release_notes()
    # …and it is still the copy that actually ships (root-vs-package byte identity is
    # test_shipped_notes.py's drift guard; this is the packaged half of that pair).
    assert docs[RELEASE_NOTES_LABEL] == (SRC / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert "src/larkdocio/RELEASE_NOTES.md" in front_door.packaged_doc_paths()


def test_the_enrolled_release_notes_are_dialect_free():
    """AC3: the point of enrolling it — the notes a consumer reads carry no internal
    vocabulary."""
    hits = consumer_text.dialect_hits(larkdocio.release_notes())
    assert not hits, f"the shipped release notes carry internal dialect: {hits[:10]}"


def test_the_changelog_is_IN_the_dialect_corpus_and_says_why():
    """AC3 — TRANSFORMED by LD-691, not deleted (maintainer ruling 2, ``D-121`` (3)).

    Until LD-691 the packaged changelog was the internal engineering log, so it was **out** of the
    dialect corpus for a stated reason: enrolling it would fail permanently or force a historical
    record to be rewritten. That reason is upheld. Its conclusion is superseded because the
    premise moved: the wheel now ships the project's PUBLIC changelog in both trees — consumer
    prose — so it is enrolled, and the docstring has to say both what changed and why."""
    docstring = consumer_text.shipped_docs.__doc__ or ""
    assert "CHANGELOG.md" in docstring and "changelog()" in docstring
    assert "PUBLIC" in docstring, "the enrolment note must say which changelog ships"
    docs = consumer_text.shipped_docs()
    assert docs.get("changelog() (the packaged CHANGELOG.md)") == larkdocio.changelog(), (
        "the packaged changelog is consumer prose now and must be in the dialect corpus"
    )


def test_the_shipped_changelog_is_dialect_free():
    """The point of enrolling it, measured: the changelog a consumer reads carries no internal
    vocabulary. (Was: the exclusion IS load-bearing — hits > 50 — which held while the packaged
    copy was the internal log.)"""
    hits = consumer_text.dialect_hits(larkdocio.changelog())
    assert not hits, f"the shipped changelog carries internal dialect: {hits[:10]}"


@private_tree.internal_log
def test_the_INTERNAL_log_still_carries_the_dialect_so_it_must_never_ship():
    """The other half of the old load-bearing check, kept: the root ``CHANGELOG.md`` of the
    maintainers' copy is still the internal engineering log, and it really does carry the
    vocabulary the dialect grep forbids — so the packaged copy being the PUBLIC changelog is a
    decision this guard can see, not an accident."""
    internal = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    hits = consumer_text.dialect_hits(internal)
    assert len(hits) > 50, (
        f"the internal engineering log no longer carries internal vocabulary (hits: {len(hits)})"
    )
    assert internal != larkdocio.changelog()


# --------------------------------------------------------------------------- #
# AC4 — capabilities() lists all four accessors together.                      #
# --------------------------------------------------------------------------- #

def test_capabilities_lists_every_discovery_ACCESSOR():
    """AC4: ``dir()`` is not the discovery mechanism for any packaged document. The registry
    a consumer already reads for surfaces/flags/contracts answers "what can I read about
    this library, and how" too."""
    docs = larkdocio.capabilities(full=True)["docs"]
    assert set(docs) == {f"{name}()" for name in DISCOVERY_ACCESSORS}, sorted(docs)
    for label, entry in docs.items():
        assert entry["accessor"] == label
        assert entry["resource"].endswith(".md"), entry
        assert entry["summary"].strip(), f"{label} has no summary"


def test_every_capabilities_doc_entry_RESOLVES_through_its_named_accessor():
    """AC4: the registry is a projection, not a brochure — every row it advertises is called
    here and must return the resource it names."""
    for label, entry in larkdocio.capabilities(full=True)["docs"].items():
        accessor = getattr(larkdocio, label.rstrip("()"))
        text = accessor()
        assert text.strip(), f"{label} returned nothing"
        assert entry["resource"].rsplit("/", 1)[-1].endswith(".md")


def _exported_document_accessors():
    """Every export of ``larkdocio`` that really is a **packaged-document accessor**, decided
    by calling it and comparing what comes back with the bytes the wheel carries.

    This replaces a subtraction — ``__all__`` minus a hand-kept list of the exports that are
    not accessors — which was a seam pointing the wrong way: every new public callable had to
    be remembered here (LD-208 exported the advisory permission pre-check and would have
    reddened this for a reason that has nothing to do with documents). Deciding it by the
    return value keeps the anti-rot property — a fifth packaged document with a fifth accessor
    still cannot ship without a row — with nothing to maintain.

    **The probe asks two ways, and the reason is the front-door swap.** ``guide()`` with no
    argument now answers with the guide's section INDEX, not the document, and the document
    lives behind ``guide(full=True)``. An accessor is still identified by RETURNING a packaged
    document — never by a name written down here — so the probe simply tries both spellings;
    a fifth document whose accessor answers either way is still caught.
    """
    import types

    packaged = {path.read_text(encoding="utf-8")
                for path in packaged_markdown().values()}
    found = set()
    for name in larkdocio.__all__:
        target = getattr(larkdocio, name, None)
        if isinstance(target, types.ModuleType) or not callable(target):
            continue
        for call in (lambda: target(), lambda: target(full=True)):
            try:
                value = call()
            except TypeError:  # takes other arguments — not a document accessor
                continue
            if isinstance(value, str) and value in packaged:
                found.add(name)
                break
    return found


def test_the_capabilities_doc_registry_is_DERIVED_from_the_package_exports():
    """AC4's anti-rot half: a fifth packaged document with a fifth accessor must not be able
    to ship without a row here. The registry's keys are the exported accessors, so the two
    cannot disagree — asserted against ``__all__``, not against a literal list."""
    accessors = _exported_document_accessors()
    assert accessors == set(DISCOVERY_ACCESSORS), (
        f"the exports that return a packaged document are {sorted(accessors)}"
    )
    assert set(larkdocio.capabilities(full=True)["docs"]) == {f"{name}()" for name in accessors}


def test_the_capabilities_doc_entries_are_dialect_free():
    """The registry's strings are consumer-facing text (they travel through the dialect
    corpus's runtime pass), so this is the direct statement of that."""
    hits = []
    for label, entry in larkdocio.capabilities(full=True)["docs"].items():
        for value in entry.values():
            hits += [(label, name, matched)
                     for name, matched in consumer_text.dialect_hits(value)]
    assert not hits, f"capabilities()['docs'] carries internal dialect: {hits}"


# --------------------------------------------------------------------------- #
# LD-180 — THE LOOP THE ACCESSOR TABLE ALWAYS CLAIMED AND NOTHING ENFORCED.     #
#                                                                              #
# ``DOC_ACCESSORS``' own comment says a document added to the wheel without a   #
# row there "has no accessor and is unreadable in practice, which is the        #
# failure this table makes visible" — but no guard held the table against the   #
# set of packaged Markdown documents, so the "every document the wheel carries  #
# has an accessor" claim was written from the four docs in front of the author  #
# and shipped false by one: ``blocks/BLOCK_TYPES.md`` is packaged and has no    #
# accessor. These guards close that loop, BOTH ways, minus a named, reasoned    #
# exclusion — the same reasoned-exclusion shape the front-door consumer corpus   #
# and the shipped-citation guard already make for the contributor doc.          #
# --------------------------------------------------------------------------- #

#: Packaged Markdown that deliberately has NO accessor, each with the reason it is excluded.
#: A named, reasoned exclusion is documentation; a silent one is indistinguishable from the
#: bug this guard exists to catch. ``BLOCK_TYPES.md`` is the handler-AUTHORING guide — a
#: contributor doc whose audience holds the dev repo — which is the same reasoned exclusion
#: ``test_front_door_doctrine.CITATION_SCOPE_EXCLUSIONS`` and the guarded consumer corpus
#: already make for it. Whether a contributor doc should ship in a consumer wheel AT ALL is a
#: separate, open question this guard neither answers nor preempts — it only forces a
#: *decision* to be recorded before a doc can ship in the wheel unreadable-in-practice.
ACCESSOR_EXCLUDED_PACKAGED_DOCS = {
    "src/larkdocio/blocks/BLOCK_TYPES.md": (
        "the handler-authoring guide — a CONTRIBUTOR doc (how to add a block type to this "
        "repo's registry), whose audience stands in the dev repo where every path it cites "
        "resolves. The same reasoned exclusion the guarded consumer corpus and the "
        "shipped-citation guard already make for it."
    ),
}


def _accessor_resource_paths():
    """The repo-relative packaged path each ``DOC_ACCESSORS`` row reads.

    A row's ``resource`` is the path INSIDE the wheel (``larkdocio/GUIDE.md``); the wheel is
    built from ``src/``, so prefixing ``src/`` yields the repo-relative path
    ``front_door.packaged_doc_paths()`` reports — the two are then directly comparable.
    """
    return {f"src/{resource}" for _name, resource, _summary in DOC_ACCESSORS}


def _packaged_markdown():
    """Every Markdown document the wheel carries, repo-relative (derived from package-data)."""
    return {rel for rel in front_door.packaged_doc_paths() if rel.endswith(".md")}


def test_every_packaged_CONSUMER_document_has_an_accessor():
    """The loop the ``DOC_ACCESSORS`` comment always claimed and nothing enforced. Every
    packaged Markdown document except a named contributor exclusion has an accessor row — so a
    document can no longer ship in the wheel unreadable-in-practice without a recorded
    decision, which is exactly how the "every document" claim came to overshoot by one."""
    without_accessor = sorted(
        _packaged_markdown()
        - _accessor_resource_paths()
        - set(ACCESSOR_EXCLUDED_PACKAGED_DOCS)
    )
    assert not without_accessor, (
        f"these Markdown documents ship in the wheel with no accessor and no recorded "
        f"exclusion: {without_accessor} — add an accessor + a DOC_ACCESSORS row, or record a "
        f"reasoned exclusion in ACCESSOR_EXCLUDED_PACKAGED_DOCS"
    )


def test_every_accessor_points_at_a_document_the_wheel_actually_carries():
    """The other direction: an accessor row for a resource ``package-data`` does not carry is
    a call that raises from a wheel-only install — a phantom the loop must also catch."""
    phantom = sorted(_accessor_resource_paths() - _packaged_markdown())
    assert not phantom, (
        f"DOC_ACCESSORS names {phantom}, which the wheel does not carry as package data"
    )


def test_the_accessor_exclusions_are_real_and_still_earn_their_place():
    """A reasoned exclusion has to be true, or it is dead weight: each excluded doc must
    actually be packaged, must actually lack an accessor, and must carry a usable reason."""
    packaged = _packaged_markdown()
    accessors = _accessor_resource_paths()
    for excluded, reason in ACCESSOR_EXCLUDED_PACKAGED_DOCS.items():
        assert excluded in packaged, f"{excluded} is excluded but the wheel does not carry it"
        assert excluded not in accessors, (
            f"{excluded} is on the exclusion list but DOES have an accessor — delete the row"
        )
        assert len(reason) > 80, f"{excluded} is excluded without a usable reason"


def test_the_accessor_set_guard_BITES_both_directions():
    """Red-then-green over the SAME set arithmetic that guards, per direction — a bidirectional
    guard that only really checks one way is the classic silent failure. The first leg is the
    ORIGINAL bug made permanent: drop the named exclusion and ``BLOCK_TYPES.md`` is reported."""
    accessors = _accessor_resource_paths()
    packaged = _packaged_markdown()

    # Direction one, and the bug reproduction: with NO exclusion recorded, the real packaged
    # contributor doc is flagged as lacking an accessor — which is the false-by-one state.
    assert sorted(packaged - accessors) == ["src/larkdocio/blocks/BLOCK_TYPES.md"]

    # Direction one via a fresh doc: a newly-packaged doc with no accessor is reported.
    invented = packaged | {"src/larkdocio/NEWDOC.md"}
    without = sorted(invented - accessors - set(ACCESSOR_EXCLUDED_PACKAGED_DOCS))
    assert without == ["src/larkdocio/NEWDOC.md"]

    # Direction two: an accessor pointing at an un-packaged resource is reported.
    phantom_accessors = accessors | {"src/larkdocio/GONE.md"}
    assert sorted(phantom_accessors - packaged) == ["src/larkdocio/GONE.md"]

    # …and today, with the real sets and the recorded exclusion, both directions are empty.
    assert not (packaged - accessors - set(ACCESSOR_EXCLUDED_PACKAGED_DOCS))
    assert not (accessors - packaged)


# --------------------------------------------------------------------------- #
# THE PROSE GUARD — the accessor-table guard cannot see a SENTENCE.             #
#                                                                              #
# The table guard above pins DOC_ACCESSORS against the packaged Markdown set,   #
# and it would have caught a sixth document shipping with no accessor. It is    #
# structurally blind to the defect that actually shipped TWICE: a sentence in   #
# shipped text quantifying over "every packaged document" when one of them is   #
# a contributor doc with no accessor. The first round fixed six such sentences  #
# and a wheel-wide re-sweep found four more, all from the same squash — which   #
# is the evidence that this sentence shape needs a guard rather than a careful  #
# author.                                                                      #
# --------------------------------------------------------------------------- #

#: A universal quantifier **applied to the document noun itself** — ``every document``,
#: ``for every packaged document``, ``an accessor per packaged document``, ``each Markdown
#: document``. Only a short list of adjectives may sit between, which is the whole precision of
#: the pattern: it is what separates *"every document the wheel carries"* (the false claim) from
#: *"every ``python`` block from this document"* (a true sentence about something else entirely,
#: and a false positive the first draft of this guard produced).
#:
#: ``all``/``every`` followed by a NUMERAL is excluded: ``all three documents`` is a bounded
#: claim about three NAMED documents and can be perfectly true, which is the must-not-bite the
#: review named. ``one`` is deliberately NOT in that numeral list — ``each one`` is a universal.
_UNIVERSAL = (
    r"\b(?:every|each|any|per)\b(?!\s+(?:two|three|four|five|six|\d))"
    r"(?:\s+(?:markdown|packaged|shipped|consumer|public|other|of|the|its|own|single))*"
    r"\s+(?:document|documents|doc|docs)\b"
)

#: The context that makes it a claim about THIS wheel's documents rather than about documents in
#: general. Looked for anywhere in the sentence, because it legitimately precedes or follows.
_PACKAGING = re.compile(r"\b(?:wheel|packaged|package|accessor|ships?|carries|carry)\b", re.I)

_UNIVERSAL_DOC_CLAIM = re.compile(_UNIVERSAL, re.IGNORECASE)

#: Sentence-ish split on a terminator. Coarse on purpose: the unit only has to be small enough
#: that a scope qualifier in a *different* claim cannot excuse this one.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

#: The scope that makes such a claim TRUE of this wheel. Any of these nearby means the sentence
#: is talking about the four consumer documents (or naming the contributor exclusion), which is
#: exactly the correction this issue shipped.
_CONSUMER_SCOPE = re.compile(
    r"consumer|written for (?:a consumer|you)|contributor|BLOCK_TYPES", re.IGNORECASE
)

_WHITESPACE_RUN = re.compile(r"\s+")


def unscoped_packaged_document_claims(text):
    """``[sentence]`` for every universal claim over the wheel's documents lacking the scope.

    Whitespace is flattened first, because every shipped document is hard-wrapped and the claim
    is routinely split across a newline — a line-oriented check would have missed most of the
    sentences this guard exists for. Judged per SENTENCE: the quantifier must apply to the
    document noun, the sentence must be about packaging or accessors, and the scope qualifier
    must be in that same sentence, so a ``consumer`` three claims away cannot excuse it.
    """
    flat = _WHITESPACE_RUN.sub(" ", text or "")
    offenders = []
    for sentence in _SENTENCE_SPLIT.split(flat):
        if not _UNIVERSAL_DOC_CLAIM.search(sentence):
            continue
        if not _PACKAGING.search(sentence):
            continue
        if _CONSUMER_SCOPE.search(sentence):
            continue
        offenders.append(sentence.strip()[:200])
    return offenders


def _prose_surfaces():
    """``{label: text}`` — the shipped prose this claim can appear in.

    The guarded consumer corpus (README/``METADATA`` body, the ``Summary``, the guide, the
    writer brief, the release notes, every ``--help`` page) PLUS the three module docstrings a
    consumer reads through ``help()``. The docstrings are in scope because two of the four
    sentences the re-sweep found were in exactly those.
    """
    surfaces = dict(consumer_text.shipped_docs())
    surfaces["larkdocio.__doc__"] = larkdocio.__doc__ or ""
    surfaces["larkdocio.guide module __doc__"] = (
        importlib.import_module("larkdocio.guide").__doc__ or ""
    )
    surfaces["larkdocio.capabilities module __doc__"] = (
        importlib.import_module("larkdocio.capabilities").__doc__ or ""
    )
    surfaces["capabilities() __doc__"] = larkdocio.capabilities.__doc__ or ""
    # LD-210 AC3: the label used to say ``guide._docs`` while the line below it resolves
    # ``larkdocio.capabilities._docs``. A surface label that names the wrong module sends the
    # next reader of a failure to the wrong file, so it names the module it actually reads.
    surfaces["capabilities._docs __doc__"] = (
        importlib.import_module("larkdocio.capabilities")._docs.__doc__ or ""
    )
    return surfaces


@pytest.mark.parametrize("label", sorted(_prose_surfaces()))
def test_no_shipped_prose_quantifies_over_PACKAGED_DOCUMENTS_unscoped(label):
    """The guard proper. A universal claim about the documents the wheel carries has to name the
    scope it is true of — ``written for a consumer`` — because the wheel also carries one
    contributor doc with no accessor."""
    offenders = unscoped_packaged_document_claims(_prose_surfaces()[label])
    assert not offenders, (
        f"{label} quantifies over the documents the wheel carries without the consumer scope, "
        f"and the wheel carries a contributor doc with no accessor: {offenders}"
    )


def test_the_prose_guard_BITES_on_every_sentence_this_issue_had_to_FIX():
    """Red proof over the REAL shipped-before wording — all six of the first round's sentences
    and all four the wheel-wide re-sweep found. A guard that cannot be shown failing on the
    document it was written against proves nothing, and these are verbatim."""
    shipped_false = (
        # the first round's six
        "**Every document the wheel carries has an accessor**, so no document is reachable only"
        " by knowing where the package unpacked.",
        "larkdocio.guide — the accessors for every document the wheel carries.",
        "Every Markdown document the wheel carries is reachable through a public accessor.",
        "``(accessor name, the document's path inside the wheel, what it is for)`` for every"
        " packaged document.",
        "Every document the wheel carries has an accessor — the rule, and the four that keep it.",
        # the four the wheel-wide re-sweep found
        "an accessor per packaged document, each readable from an installed wheel.",
        '``{"accessor()": Doc}`` for every packaged document.',
        "``docs`` — one row per packaged document, each naming the accessor that returns its"
        " text, so no consumer has to discover a document through dir().",
    )
    missed = [s for s in shipped_false if not unscoped_packaged_document_claims(s)]
    # The one exception is deliberate and named: the ``docs`` sentence carries the word
    # "consumer" for an unrelated reason ("no consumer has to discover…"), so the scope check
    # cannot distinguish it. That sentence is therefore UNGUARDED — the shipped wording is
    # correct today but nothing holds it. (LD-210 AC1: the accessor-table guard above permits a
    # named exclusion, so it cannot make "one row per packaged document" true and does NOT
    # cover this; the earlier claim that it did was wrong.)
    allowed = ['``docs`` — one row per packaged document, each naming the accessor that returns'
               ' its text, so no consumer has to discover a document through dir().']
    missed = [s for s in missed if s not in allowed]
    assert not missed, (
        f"the prose guard does not bite on {len(missed)} shipped-false sentences: {missed}"
    )


def test_the_prose_guard_ACCEPTS_the_scoped_corrections_this_issue_shipped():
    """The other direction: every corrected sentence must pass, or the guard would forbid its
    own fix and the next author would weaken it."""
    corrected = (
        "**Every document written for a consumer has an accessor**, so none of them is"
        " reachable only by knowing where the package unpacked",
        "larkdocio.guide — the accessors for every document written for a consumer.",
        "Five Markdown documents ship inside the wheel. Four are written for a consumer, and"
        " each has an accessor here",
        "an accessor per packaged **consumer** document, each readable from an installed wheel",
        "``docs`` — one row per packaged **consumer** document, each naming the accessor that"
        " returns its text",
        "Four more documents written for you ship in the wheel beside this one, each with its"
        " own accessor",
    )
    rejected = {s: unscoped_packaged_document_claims(s) for s in corrected}
    rejected = {s: hits for s in rejected if (hits := rejected[s])}
    assert not rejected, f"the guard rejects its own corrections: {rejected}"


def test_the_prose_guard_MUST_NOT_BITE_on_the_TRUE_vendor_copies_claim():
    """The must-not-bite the review named explicitly.

    The shipped guide says the ``vendor/`` drops are extras because *"all four documents ship
    inside the wheel too"*. That is TRUE and must stay: it is a bounded claim about the NAMED
    documents the drop copies out, not a universal over the packaged set. The discriminator is
    the numeral — which is why ``all four`` is exempt while ``every`` is not — and it is
    asserted here over the real sentence, so a future tightening of the pattern cannot silently
    start flagging it. (LD-549 moved the numeral three -> four when the walkthrough joined the
    drop; the claim's SHAPE, which is what this must-not-bite is about, did not move.)
    """
    real = "all four documents ship **inside** the wheel too"
    assert not unscoped_packaged_document_claims(
        f"Those `vendor/` copies are extras: {real}, so `larkdocio.guide()` returns the same bytes."
    ), "the guard flags the TRUE vendor-copies sentence — a bounded count over named documents"
    # The probe is pinned against the SHIPPED text, so it cannot rot into decoration.
    assert real.replace("**", "") in _WHITESPACE_RUN.sub(" ", larkdocio.guide(full=True)).replace("**", ""), (
        "the probe is stale — the shipped guide no longer carries that sentence"
    )
    # …and the bounded-count exemption is not a blanket hole: drop the numeral and it bites.
    assert unscoped_packaged_document_claims(
        "every document ships inside the wheel and has an accessor."
    )


def test_the_guides_opening_COUNT_of_accessor_documents_is_DERIVED_not_asserted():
    """The tenth shipped-false sentence was a COUNT, not a quantifier — *"Three more documents
    ship in the wheel beside this one"* when four more do — and a prose regex is the wrong tool
    for a number. So the count is checked against ``DOC_ACCESSORS`` itself.

    The guide is one of the accessor documents, so the number it claims *beside this one* must be
    ``len(DOC_ACCESSORS) - 1``. A further consumer accessor would redden this the moment it
    shipped without the sentence being updated — and that is exactly what happened at LD-549,
    which is the record that this guard is load-bearing rather than decorative: the walkthrough's
    accessor reddened it, and the sentence was corrected three -> four.
    """
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}
    expected = len(DOC_ACCESSORS) - 1
    flat = _WHITESPACE_RUN.sub(" ", larkdocio.guide(full=True))
    match = re.search(
        r"\b(one|two|three|four|five|six)\b[^.]{0,40}?\bmore documents?\b[^.]{0,120}?accessor",
        flat, re.IGNORECASE,
    )
    assert match, "the guide's opening no longer counts the other accessor documents at all"
    assert match.group(1).lower() == words[expected], (
        f"the guide says {match.group(1)!r} more documents carry an accessor; DOC_ACCESSORS has "
        f"{len(DOC_ACCESSORS)} rows, so beside the guide there are {expected}"
    )


# --------------------------------------------------------------------------- #
# LD-210 AC2 — the COUNTED claim's SCOPE axis, adjacent to the noun.           #
# --------------------------------------------------------------------------- #
#
# ``_UNIVERSAL`` above deliberately exempts a numeral, because ``all three documents`` is a
# bounded claim that can be perfectly true (the must-not-bite the LD-180 review named). That
# exemption left a hole one document wide: ``GUIDE.md``'s opening is a COUNTED claim — *"Three
# more documents **written for you** ship in the wheel beside this one, each with its own
# accessor"* — so the prose guard sees a numeral and stands down, while the derived check below
# pins only the **number**. Dropping ``written for you`` therefore reddened nothing, and the
# sentence would silently go back to claiming the wheel's OTHER document (the contributor's
# ``BLOCK_TYPES.md``, which has no accessor) is one of them.
#
# The direction the review recorded for this and for the ``docs`` sentence together: **require
# the consumer scope ADJACENT to the quantified document noun.** Adjacency is the whole point —
# a ``consumer`` further along the sentence is what made the other check excusable in the first
# place — so it is expressed as an anchored match at the same offset, not a proximity window.

#: A counted claim about the wheel's OTHER documents having accessors — the shape the guide's
#: opening uses, and the shape the numeral exemption lets through.
_COUNTED_DOC_ACCESSOR_CLAIM = re.compile(
    r"\b(?:one|two|three|four|five|six)\s+more\s+documents?\b[^.]{0,160}?accessor",
    re.IGNORECASE,
)

#: The same claim WITH the consumer scope where it has to be: immediately after the noun.
_COUNTED_DOC_SCOPED = re.compile(
    r"\b(?:one|two|three|four|five|six)\s+more\s+documents?\s+"
    r"written for (?:you|a consumer)\b",
    re.IGNORECASE,
)


def counted_document_claims_missing_the_consumer_scope(text):
    """``[claim]`` for every counted "N more documents … accessor" claim whose consumer scope is
    not adjacent to the document noun.

    Anchored at the claim's own start offset, so a ``consumer`` elsewhere in the sentence cannot
    excuse it — the failure mode the unscoped-universal guard above still carries.
    """
    flat = _WHITESPACE_RUN.sub(" ", text or "")
    return [
        match.group(0)[:200]
        for match in _COUNTED_DOC_ACCESSOR_CLAIM.finditer(flat)
        if not _COUNTED_DOC_SCOPED.match(flat, match.start())
    ]


@pytest.mark.parametrize("label", sorted(_prose_surfaces()))
def test_no_shipped_prose_COUNTS_the_wheels_other_documents_unscoped(label):
    """AC2's guard proper, over the same corpus as the universal one. A counted claim about the
    other documents that carry accessors must name whose they are, right at the noun."""
    offenders = counted_document_claims_missing_the_consumer_scope(_prose_surfaces()[label])
    assert not offenders, (
        f"{label} counts the wheel's other accessor-carrying documents without the consumer "
        f"scope adjacent to the noun, and the wheel also carries a contributor doc with no "
        f"accessor: {offenders}"
    )


def test_the_guides_opening_COUNT_claim_IS_STILL_THERE_to_be_scoped():
    """"No unscoped counted claim" must not be reachable by deleting the sentence — the same
    trap ``test_ac6_the_quickstart_still_owns_those_handshakes`` closes for the README."""
    flat = _WHITESPACE_RUN.sub(" ", larkdocio.guide(full=True))
    assert _COUNTED_DOC_ACCESSOR_CLAIM.search(flat), (
        "the guide's opening no longer counts the other accessor documents at all — the scope "
        "guard above would pass vacuously"
    )
    assert _COUNTED_DOC_SCOPED.search(flat), (
        "the guide's counted claim no longer carries 'written for you' adjacent to the noun"
    )


def test_the_counted_claim_scope_rule_BITES_on_the_exact_wording_it_was_written_against():
    """The red proof AC2 exists for — the shipped sentence with ``written for you`` **dropped**,
    which is the mutation the LD-180 review ran and watched change nothing."""
    dropped = (
        "Three more documents ship in the wheel beside this one, each with its own accessor:"
        " `larkdocio.writer_brief()`."
    )
    assert counted_document_claims_missing_the_consumer_scope(dropped), (
        "the counted-claim scope rule does not bite on the unscoped wording — the whole point"
    )
    # …and the scoped form it must accept, so the rule cannot be satisfied by a reword.
    assert not counted_document_claims_missing_the_consumer_scope(
        "Three more documents written for you ship in the wheel beside this one, each with its"
        " own accessor."
    )


def test_the_counted_claim_scope_rule_MUST_NOT_BITE_on_the_TRUE_bounded_claims():
    """LD-154's twice-relearned lesson: a subject-scoped rule lands with the sentences it must
    NOT flag, or correct prose gets forced into a reword.

    The bounded vendor-copies claim is the named must-not-bite of the universal guard, and it
    must stay unflagged here too — it counts documents, but it makes no accessor claim about
    them. Neither does a count of something that is not a document.
    """
    for true_sentence in (
        "Those `vendor/` copies are extras: all four documents ship **inside** the wheel too,"
        " so `larkdocio.guide()` returns the same bytes.",
        "Six Markdown documents ship inside the wheel.",
        "Two more accessors are exported from `larkdocio.guide`.",
    ):
        assert not counted_document_claims_missing_the_consumer_scope(true_sentence), (
            f"the counted-claim scope rule flags a TRUE sentence: {true_sentence!r}"
        )


# --------------------------------------------------------------------------- #
# THE WHEEL-ONLY ARMS — the artifact, not the source tree.                     #
# --------------------------------------------------------------------------- #

_PROBE = r"""
import json, sys
import larkdocio
out = {
    "file": larkdocio.__file__,
    # The probe's filter is the consumer's own one-liner from the report, widened as accessors
    # ship (LD-549 added `lark_setup`) — spelled out here rather than imported, because this
    # source runs inside a SEPARATE interpreter that must not see this repository's tests.
    "dir": sorted(n for n in dir(larkdocio)
                  if n in ("guide", "writer_brief", "release_notes", "changelog",
                           "lark_setup")),
    "all": list(larkdocio.__all__),
    "notes_head": larkdocio.release_notes()[:64],
    "notes_len": len(larkdocio.release_notes()),
    "log_len": len(larkdocio.changelog()),
    "log_head": larkdocio.changelog()[:64],
    # LD-540: probed across the surfaces the wheel carries, not the notes alone — the notes ship
    # a recent-N window now, and the claim is that the FACT is reachable from the wheel.
    "notes_facts": [p for p in ("contacts data range", "inline comment")
                    if p in larkdocio.release_notes()
                    or p in larkdocio.guide(full=True)
                    or p in larkdocio.writer_brief()],
    "docs": sorted(larkdocio.capabilities()["docs"]),
    # LD-549: the walkthrough is the document a brand-new consumer needs FIRST, so the wheel-only
    # arms prove it is readable from the artifact rather than only from the source tree.
    "setup_len": len(larkdocio.lark_setup()),
    "setup_head": larkdocio.lark_setup()[:64],
}
print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory):
    """One wheel, built from a **pristine** copy of the packaging inputs, shared by both arms.

    ``_built_wheel_record`` is reused rather than re-implemented: it already excludes the two
    local artifacts (``build/lib/`` and the editable install's cached ``SOURCES.txt``) that can
    make an in-wheel assertion pass over a declaration that is no longer there.
    """
    return _built_wheel_record(tmp_path_factory.mktemp("wheel"))


def _probe(python, cwd, env_extra):
    import json
    import os

    proc = subprocess.run(
        [str(python), "-c", _PROBE], cwd=str(cwd), capture_output=True, text=True,
        env={**os.environ, **env_extra, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert proc.returncode == 0, f"the wheel-only probe failed:\n{proc.stderr[-2000:]}"
    return json.loads(proc.stdout)


def test_the_accessors_work_from_the_BUILT_WHEEL_with_no_src_tree_importable(
    built_wheel, tmp_path
):
    """The artifact arm: unpack the wheel, import ``larkdocio`` out of it, and pin
    ``__file__`` inside the unpacked tree — so the source checkout provably is not what
    answered. Run from a directory outside the repo, and the two documents must be readable
    **and** carry the upgrade-critical facts.

    The editable install puts ``src/`` on ``sys.path`` by ``.pth``, which is appended *after*
    ``PYTHONPATH``; the ``__file__`` assertion is what proves the precedence held rather than
    assuming it.
    """
    unpacked = tmp_path / "unpacked"
    with zipfile.ZipFile(built_wheel) as archive:
        record = next(n for n in archive.namelist() if n.endswith("/RECORD"))
        record_text = archive.read(record).decode("utf-8")
        for name in NOTES:
            assert f"larkdocio/{name}" in record_text, (
                f"larkdocio/{name} is not in the wheel RECORD — the accessor would raise"
            )
        archive.extractall(unpacked)

    out = _probe(sys.executable, tmp_path, {"PYTHONPATH": str(unpacked)})
    assert out["file"].startswith(str(unpacked)), (
        f"the probe imported {out['file']}, not the unpacked wheel — the arm proves nothing"
    )
    assert out["dir"] == sorted(DISCOVERY_ACCESSORS)
    assert "release_notes" in out["all"] and "changelog" in out["all"]
    assert out["notes_head"].startswith("# Release notes")
    # LD-691 (maintainer ruling 2): the shipped changelog is the PUBLIC one and much shorter than the
    # notes, so "the log is the longer" no longer tells crossed resources apart; each head does.
    assert out["notes_len"] > 10_000 and out["log_len"] > 0
    assert out["log_head"].startswith("# Changelog")
    assert out["notes_facts"] == list(UPGRADE_CRITICAL_PHRASES) or set(
        out["notes_facts"]) == set(UPGRADE_CRITICAL_PHRASES)
    assert out["docs"] == sorted(f"{n}()" for n in DISCOVERY_ACCESSORS)
    # LD-549 — the walkthrough answered from the ARTIFACT, which is the only reader it exists
    # for: content, not a truthy return (a zero-byte or truncated resource must not pass).
    assert out["setup_head"].startswith("# Setting up your Lark application")
    assert out["setup_len"] > 3_000


def test_the_accessors_work_from_an_INSTALLED_WHEEL_IN_A_CLEAN_VENV(tmp_path):
    """The installation arm: a fresh virtualenv, ``pip install`` the wheel, probe it there.

    Fully offline — ``--no-deps --no-index`` means nothing is fetched, and the runtime
    dependencies are supplied by pointing ``PYTHONPATH`` at this interpreter's own
    site-packages. That directory is not a *site* directory for the child, so its ``.pth``
    files are never processed and the editable ``src/`` entry never enters ``sys.path``; the
    ``__file__`` assertion pins that the installed copy is what answered.

    LD-355: the venv construction (identical to two other sites) moved to
    ``front_door.clean_wheel_venv`` and is produced once per RUN. It installs the same
    ``built_wheel`` this module's other arm unpacks — the pristine-inputs wheel — so this
    test no longer names that fixture; the ``__file__`` assertion below is what pins that
    the venv, and not the checkout, answered.
    """
    python = front_door.clean_wheel_venv()["python"]

    site = pathlib.Path(sysconfig.get_paths()["purelib"])
    out = _probe(python, tmp_path, {"PYTHONPATH": str(site)})
    assert "/venv/" in out["file"] or "\\venv\\" in out["file"], (
        f"the probe imported {out['file']}, not the installed copy in the clean venv"
    )
    assert out["dir"] == sorted(DISCOVERY_ACCESSORS)
    assert out["notes_head"].startswith("# Release notes")
    assert set(out["notes_facts"]) == set(UPGRADE_CRITICAL_PHRASES), (
        "an installed wheel's release notes are missing the upgrade-critical facts"
    )
    assert out["docs"] == sorted(f"{n}()" for n in DISCOVERY_ACCESSORS)
    # LD-549 — same claim through the pip-installed copy: the walkthrough is what a consumer who
    # ran a plain `pip install` receives, with no vendor drop and no clone to fall back on.
    assert out["setup_head"].startswith("# Setting up your Lark application")
    assert out["setup_len"] > 3_000
