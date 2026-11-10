"""THE TRUTH KNIFE — ``width`` / ``height`` are accepted at create and gone after the bind.

Four shipped sentences called ``width``/``height`` *"the only create-time image fields that
were measured"*. That is true and misleading in the same breath: they were measured
**accepted at create**, and the binding ``replace_image`` PATCH replaces the whole image
property, geometry included. This module is the census + the guard.

**The census is a CENSUS.** The mint named four sites; the sweep found **seven**, and this
file enumerates the sites that actually carry the claim's shape, across **both readings** — the source text of every
shipped surface, and the **folded** runtime values a consumer reads out of
``larkdocio.capabilities()``. Each site is pinned twice: the pre-change phrasing is
**forbidden** (so a revert reddens) and the whole truth is **required**, in four parts.

**The two measurements are reconciled, not averaged.** They disagree on the *number* and
agree on the *conclusion*, and the shipped text says both with their labels:

* *consumer-observed on one day, n=4* — authored ``560x560``, read back ``2560x2560``;
* *captured, 2026-08-19, n=1* — authored ``120x60``, read back ``1x1``, and the file that
  was uploaded was a 1x1 PNG.

Both are consistent with the bind writing the file's own pixel dimensions; neither sample
isolates that mechanism, so no site claims it as proven.
"""
import inspect
import logging
import pathlib
import re

import pytest

import larkdocio
from larkdocio.write.media import put_image_in_document

from consumer_text import capabilities_strings
import private_tree  # noqa: E402  (LD-685)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src" / "larkdocio"


# --------------------------------------------------------------------------- #
# AC1 — THE CENSUS.                                                           #
#                                                                              #
# The mint's list was four. The sweep found SEVEN carriers of the shape:        #
# the four, PLUS the guide recipe's own inline comment (a caller copies the    #
# code, not the prose around it), PLUS the MODULE docstring above the function  #
# (a second carrier in the same file, invisible to a grep for the function's    #
# own wording), PLUS the decision register the ruling is looked up in. Two      #
# further families were considered and EXCLUDED, and the                        #
# exclusions are pinned below so they cannot become silent.                    #
# --------------------------------------------------------------------------- #

#: ``label -> (path, the phrasing that must be GONE)``. Every value is a literal that
#: shipped before this change; each one bites if the sentence is reverted.
CENSUS = {
    "write/media.py MODULE docstring": (
        SRC / "write" / "media.py",
        "Create-time image fields beyond ``width``\nand ``height`` (alignment, scale, a "
        "caption) are **unmeasured** and are not offered.",
    ),
    "write/media.py docstring": (
        SRC / "write" / "media.py",
        "the only create-time image fields that were measured",
    ),
    "GUIDE.md — what is measured and what is not": (
        SRC / "GUIDE.md",
        "`width`/`height` are the only create-time image\nfields that were measured",
    ),
    "GUIDE.md — the image recipe's own inline comment": (
        SRC / "GUIDE.md",
        "width/height are the only measured create-time fields",
    ),
    "capabilities/_projections.py — the creatable_out_of_band authoring site": (
        SRC / "capabilities" / "_projections.py",
        "fields beyond width/height (alignment, scale, a caption) are UNMEASURED",
    ),
    "BLOCKS.md row 27": (
        REPO_ROOT / "BLOCKS.md",
        "Create-time fields beyond `width`/`height` (align, scale, captions) are "
        "**unmeasured** and not offered",
    ),
    "requirements/DECISIONS.md — the image-authoring ruling": (
        REPO_ROOT / "requirements" / "DECISIONS.md",
        "Create-time fields beyond `width`/`height` are unmeasured and not offered.",
    ),
}

#: Sites that pair ``width``/``height`` with a *different* route and are therefore NOT
#: carriers of this claim. Recorded so the exclusion is an argument, not an omission.
EXCLUDED_FROM_THE_CENSUS = {
    "GUIDE.md — the sheets FLOAT-IMAGE recipe": (
        "width/height are required: the route was only measured with them",
        "a different endpoint (the sheets float-image create), where the geometry is a "
        "required bind parameter rather than a create-time hint; whether it survives THERE "
        "is unmeasured, and the docx measurement may not be generalised onto it",
    ),
    "SHEETS.md / sheets cell_model — the IN-CELL image's geometry": (
        "`width`/`height` are captured",
        "a READ-side fact about a sheet cell's value, not a create-time field of the docx "
        "image block",
    ),
}


def _text(path):
    return path.read_text(encoding="utf-8")


def test_ac1_the_census_is_seven_sites_not_the_four_the_mint_named():
    """The count is asserted so a divergence from the mint's list is visible, not silent.

    The mint named four. The sweep found **seven**: the four, plus the guide recipe's inline
    comment, plus this module's own MODULE docstring (the same file, different paragraph, a
    different wording — which is why a grep for the function's sentence missed it), plus the
    decision register the ruling is looked up in."""
    assert len(CENSUS) == 7, sorted(CENSUS)


@private_tree.citations
@pytest.mark.parametrize("label", sorted(CENSUS))
def test_ac1_every_census_site_exists_and_no_longer_carries_the_old_phrasing(label):
    """THE BITE. Each literal below shipped; restoring one reddens this test in situ."""
    path, gone = CENSUS[label]
    assert path.exists(), path
    assert gone not in _text(path), (label, gone)


@pytest.mark.parametrize("label", sorted(EXCLUDED_FROM_THE_CENSUS))
def test_ac1_the_excluded_lookalikes_are_still_there_and_still_excluded(label):
    """An exclusion is only honest while the thing excluded still exists to be argued about."""
    needle, _why = EXCLUDED_FROM_THE_CENSUS[label]
    corpus = _text(SRC / "GUIDE.md") + _text(REPO_ROOT / "SHEETS.md")
    assert needle in corpus, label


# --------------------------------------------------------------------------- #
# AC2 — THE WHOLE TRUTH, in four parts, at every site.                        #
# --------------------------------------------------------------------------- #

#: ``part -> (regex, what the part says)``. Applied to every census site's own text.
FOUR_PARTS = {
    "1 — the create accepts, the bind overwrites, with BOTH measurements labelled": (
        re.compile(
            r"(do(es)? not survive|overwrit)"          # the fact
            r"(?s:.){0,1600}?2560"                     # the consumer's number
            r"(?s:.){0,1600}?(1x1|1×1)",               # this project's number
            re.IGNORECASE),
        "the values do not survive the bind; 560->2560 (consumer-observed) and "
        "120x60->1x1 (captured), each labelled with its source",
    ),
    "2 — no measured route resizes afterwards, D-59-scoped": (
        re.compile(r"99992402(?s:.){0,1200}?1770001", re.IGNORECASE),
        "the three refusals with their codes, scoped to those shapes on that route",
    ),
    "3 — the one lever that works: downscale the BYTES first": (
        re.compile(r"downscale(?s:.){0,240}?(byte|pixel)", re.IGNORECASE),
        "downscale the bytes before uploading, in the imperative",
    ),
    "4 — the extension can lie": (
        re.compile(r"JPEG(?s:.){0,240}?\.png", re.IGNORECASE),
        "Lark exports a whiteboard as JPEG under a .png filename",
    ),
}

#: Each site's own slice of its file — the paragraph the claim lives in, not the whole file,
#: so a part satisfied somewhere else entirely cannot pass for a part satisfied HERE.
SITE_SLICES = {
    "write/media.py MODULE docstring": lambda: _slice(
        SRC / "write" / "media.py",
        "**What is measured, and what is UNMEASURED.**",
        "**The RENDERING axis is UNMEASURED"),
    "write/media.py docstring": lambda: put_image_in_document.__doc__,
    "GUIDE.md — what is measured and what is not": lambda: _slice(
        SRC / "GUIDE.md", "**What is measured, and what is not.**", "### Recipe: attach a file"),
    "GUIDE.md — the image recipe's own inline comment": lambda: _slice(
        SRC / "GUIDE.md", "authored = put_image_in_document(", "print(authored.block_id"),
    # THE FOLDED READING for this one: the authoring site is a python string built out of
    # adjacent literals, so its *source* splits sentences mid-phrase. What a consumer reads
    # is the joined value, and that is what the four parts must hold. That this value came
    # from the authoring site and not from a hand-edited projection is pinned separately by
    # ``test_ac1_the_folded_payload_and_its_authoring_site_are_the_same_text``.
    "capabilities/_projections.py — the creatable_out_of_band authoring site":
        lambda: _folded_image_entry(),
    "BLOCKS.md row 27": lambda: _slice(REPO_ROOT / "BLOCKS.md", "| 27 | image |", "\n| 28 "),
    "requirements/DECISIONS.md — the image-authoring ruling": lambda: _slice(
        REPO_ROOT / "requirements" / "DECISIONS.md",
        "### D-71 —", "\n### D-72"),
}


def _slice(path, start, end):
    text = _text(path)
    head = text.index(start)
    return text[head:text.index(end, head)]


@private_tree.register
@pytest.mark.parametrize("label", sorted(CENSUS))
@pytest.mark.parametrize("part", sorted(FOUR_PARTS))
def test_ac2_every_site_ships_all_four_parts(label, part):
    pattern, what = FOUR_PARTS[part]
    assert pattern.search(SITE_SLICES[label]()), (label, part, what)


@private_tree.register
@pytest.mark.parametrize("label", sorted(CENSUS))
def test_ac2_the_measurements_carry_their_labels_and_their_dates(label):
    """A consumer report is labelled as one and never promoted to *measured by us*.

    TRANSFORMED by LD-700 (round 3 of the public-export review, T3; supersession.md § A.1). The
    reason is unchanged — each half carries its label and its scope. The conclusion moved for
    the consumer's half only: it is scoped to "one day" rather than dated, because a consumer
    report's date is the consumer's particular. Our own capture keeps its date."""
    text = SITE_SLICES[label]()
    assert re.search(r"consumer-observed", text, re.IGNORECASE), label
    assert "2026-08-19" in text, label
    if label.startswith("requirements/"):
        return  # the private decision register keeps the record as it was ruled
    assert re.search(r"consumer-observed\s+(#\s*)?on one day", text, re.IGNORECASE), label
    assert not re.search(r"consumer-observed[,\s#]*20\d\d-", text, re.IGNORECASE), label


@private_tree.register
@pytest.mark.parametrize("label", sorted(CENSUS))
def test_ac2_the_refusal_codes_are_fenced_to_their_evidence(label):
    """Three shapes were refused. Every other spelling is unmeasured, NOT refuted."""
    text = SITE_SLICES[label]()
    assert re.search(r"unmeasured,? (and )?not refuted", text, re.IGNORECASE), label


@private_tree.register
@pytest.mark.parametrize("label", sorted(CENSUS))
def test_ac2_no_site_claims_the_block_cannot_be_deleted(label):
    """The consumer's compounding premise is now FALSE: an image block anchored by its id
    deletes, measured 2026-08-19. No corrected sentence may carry the dead claim forward."""
    text = SITE_SLICES[label]().lower()
    for dead in ("cannot be deleted", "can neither be deleted", "no way to remove the block"):
        # A site is allowed to NAME the dead claim in order to retract it; what it may not do
        # is assert it. So the sentence carrying the phrase must also carry the retraction.
        for sentence in re.split(r"(?<=[.!?])\s", text):
            if dead in sentence:
                assert re.search(r"\bfalse\b|no longer|is removable|does delete", sentence), (
                    label, sentence)


# --------------------------------------------------------------------------- #
# AC1, THE FOLDED READING — what a consumer reads out of capabilities().       #
#                                                                              #
# The mint's fourth site is an AUTHORING site; this is the value it folds into.#
# Pinned separately because a projection edited by hand would pass the source   #
# check and fail the caller.                                                   #
# --------------------------------------------------------------------------- #

def _folded_image_entry():
    hits = [s for s in capabilities_strings().values()
            if isinstance(s, str) and "an IMAGE in the document body" in s]
    assert len(hits) == 1, [h[:80] for h in hits]
    return hits[0]


def test_ac1_the_folded_capabilities_payload_carries_the_corrected_sentence():
    entry = _folded_image_entry()
    assert "fields beyond width/height (alignment, scale, a caption) are UNMEASURED" \
        not in entry
    assert re.search(r"(do not survive|overwrit)", entry, re.IGNORECASE), entry[:200]


def test_ac1_the_folded_payload_and_its_authoring_site_are_the_same_text():
    """Corrected at the authoring site, never by editing a generated projection.

    The source is the joined literal, so a phrase may be split across adjacent string
    literals; the check is therefore on the words, each of which must appear in BOTH."""
    entry = _folded_image_entry().lower()
    source = _text(SRC / "capabilities" / "_projections.py").lower()
    for word in ("survive", "downscale", "99992402", "1770001", "2560", "jpeg"):
        assert word in entry, word
        assert word in source, word


# --------------------------------------------------------------------------- #
# AC2 part 4 — READ THE CODE, then state what you found.                       #
# --------------------------------------------------------------------------- #

def test_ac2_the_extension_warning_is_about_the_CALLERS_parser_not_this_librarys():
    """The claim shipped in part 4 is a warning to a caller sizing bytes. It is allowed only
    because the write path was read and carries **no** image-header or extension inspection
    at all: ``name`` and ``data`` go to the upload unread. Grep the write path and prove it."""
    forbidden = re.compile(r"IHDR|\\x89PNG|imghdr|Image\.open|splitext|\.suffix\b")
    write_path = [SRC / "write" / "media.py", SRC / "base" / "media.py"]
    for path in write_path:
        assert not forbidden.search(_text(path)), path


# --------------------------------------------------------------------------- #
# AC3 — THE DEAD-PARAMETER DECISION: (b), docstring + a runtime warning.       #
#                                                                              #
# (a) reaches nobody who copied a recipe; (c) is surface pruning and is not     #
# available this round. So the parameters stay, behave exactly as before, and   #
# SAY SO OUT LOUD the moment a caller passes one.                              #
# --------------------------------------------------------------------------- #

def _call(caplog, **geometry):
    """Drive the op far enough to reach the disclosure, and no further."""
    from test_docx_image_authoring import run

    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        run(**geometry)
    return [r for r in caplog.records
            if r.levelno == logging.WARNING and "width" in r.getMessage().lower()]


@pytest.mark.parametrize("geometry", [{"width": 560}, {"height": 560},
                                      {"width": 560, "height": 560}])
def test_ac3_passing_either_dimension_warns(caplog, geometry):
    (record,) = _call(caplog, **geometry)
    message = record.getMessage()
    assert "do not survive" in message.lower()
    assert "downscale" in message.lower()


def test_ac3_omitting_both_is_silent(caplog):
    assert _call(caplog) == []


def test_ac3_the_warning_is_a_WARNING_and_never_an_exception(caplog):
    """A disclosure, not a refusal: the op still does exactly what it did before."""
    from test_docx_image_authoring import TOKEN, run

    with caplog.at_level(logging.WARNING, logger="larkdocio"):
        result, _log = run(width=560, height=560)
    assert result.file_token == TOKEN and result.bytes_verified is True


def test_ac3_the_parameters_are_still_there_and_still_typed():
    """(c) — deprecation/removal — is NOT what this change did. The surface is unpruned."""
    parameters = inspect.signature(put_image_in_document).parameters
    for name in ("width", "height"):
        assert name in parameters
        assert parameters[name].default is None


def test_ac3_the_disclosure_is_reachable_without_reading_the_docstring():
    """The whole point of choosing (b): the words a caller who never opened the docstring
    still meets. The warning text names the fact and the lever."""
    from larkdocio.write import media

    assert "logging" in _text(SRC / "write" / "media.py")
    assert media._GEOMETRY_DOES_NOT_SURVIVE, media._GEOMETRY_DOES_NOT_SURVIVE
    assert "downscale" in media._GEOMETRY_DOES_NOT_SURVIVE.lower()


# --------------------------------------------------------------------------- #
# AC5 — the notes deliverable, in the OPEN section of both files.              #
# --------------------------------------------------------------------------- #

def _flat(text):
    """Markdown wraps; the sentence is what matters, not where the line broke."""
    return re.sub(r"\s+", " ", text).lower()


@pytest.mark.parametrize("relative", [pytest.param("CHANGELOG.md", marks=private_tree.internal_log), "RELEASE_NOTES.md"])
def test_ac5_the_open_section_carries_the_entry(relative):
    text = _text(REPO_ROOT / relative)
    open_section = _flat(text[text.index("## [1.37.0]"):text.index("## [1.36.0]")])
    assert "do not survive the bind" in open_section, relative
    assert "downscale" in open_section, relative
    assert "2560" in open_section, relative
    assert "99992402" in open_section and "1770001" in open_section, relative
    assert "jpeg" in open_section, relative
    assert "consumer-observed" in open_section, relative


def test_ac5_no_second_section_was_opened_ahead_of_the_packaged_version():
    """At most ONE section sits above the packaged version's own.

    **The reason is preserved; only the way it is enforced moved (LD-529).** The rule
    is what this test has always been named for: a landing writes into the topmost
    **un-cut** section, so exactly one section may sit ahead of what `pyproject.toml`
    packages — the one being written into. A *second* one means somebody opened a
    version ahead of the release train, which is what LD-508 refused and what the
    release script's own section gates would then trip over.

    What changed is that the version was spelled as a **literal** (`## [1.38.0]`,
    correct while the packaged version was 1.36.0 and `## [1.37.0]` was the open
    section). Once 1.37.0 was cut and packaged, `## [1.38.0]` became exactly the
    correct next open section, so the literal was asserting the opposite of the rule
    it was written for. The count is now **derived** from the packaged version, so it
    keeps biting for the same reason at every release without an edit per release.
    """
    import re as _re

    packaged = _re.search(
        r'^version = "([^"]+)"', _text(REPO_ROOT / "pyproject.toml"), _re.M).group(1)
    for relative in ("CHANGELOG.md", "RELEASE_NOTES.md"):
        sections = _re.findall(r"^## \[([^\]]+)\]", _text(REPO_ROOT / relative), _re.M)
        assert packaged in sections, (
            f"{relative} carries no section for the packaged version {packaged}")
        ahead = sections[: sections.index(packaged)]
        assert len(ahead) <= 1, (
            f"{relative}: {len(ahead)} sections sit ahead of the packaged version "
            f"{packaged} ({ahead}) — a landing writes into the topmost un-cut section, "
            f"so at most one may be open ahead of the release train.")


@private_tree.internal_log
def test_ac5_the_shipped_twins_carry_it_too():
    """AC5: what this issue wrote into the release documents actually reaches the wheel.

    **LD-540 narrowed the subject.** The wheel carries a recent-N window of each document rather
    than a byte-identical twin, so "reaches the wheel" is now *the packaged copy is byte-identical
    to the projection of the root file* — an exact equality against a derived expectation, checked
    by the one function that defines it instead of a second comparison here. The claim this
    issue's own entry makes is separately asserted, over the copies the window actually carries,
    by the test below it.
    """
    from test_shipped_notes import notes_claim_copies, notes_identity_report

    assert notes_identity_report() == []
    # Located through the same whitespace folding the accessor test below uses: markdown wraps,
    # and this sentence legitimately spans a line break in both documents.
    marker = "do not survive the bind"
    for relative in ("CHANGELOG.md", "RELEASE_NOTES.md"):
        for label, text in notes_claim_copies(relative, marker, normalize=_flat):
            assert marker in _flat(text), label


def test_ac5_the_public_accessor_serves_the_corrected_notes():
    """The folded reading of the notes: what ``release_notes()`` actually hands a consumer.

    **TRANSFORMED (LD-621, ruled by D-111), and only the CONDITION moved.** The claim is
    unchanged — a consumer's own call must serve the correction, folded exactly as the copies
    above are — and it is still asserted, against the accessor, whenever the accessor can carry
    it. What expired is the premise that it always can: ``release_notes()`` returns the WINDOW
    (LD-540), this correction was written into ``[1.37.0]``, and the window rolling past that
    section is the designed behaviour rather than a defect. The section-carries-it question is
    answered by ``notes_claim_copies`` in the test above — which reddens if the packaged copy has
    lost the claim while its section is still INSIDE the window — so the wheel-facing arm here is
    *kept for as long as it can be true* and asserts nothing the window has legitimately taken.
    """
    from test_shipped_notes import notes_claim_copies

    marker = "do not survive the bind"
    carried = [label for label, _text in notes_claim_copies(
        "RELEASE_NOTES.md", marker, normalize=_flat)]
    if any("packaged" in label for label in carried):
        assert marker in _flat(larkdocio.release_notes()), (
            "the packaged notes carry the correction but the public accessor does not serve it")
