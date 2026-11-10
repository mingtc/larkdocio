"""THE CONSUMER SKILL PACK, held to the one promise that makes it shippable: **a router
POINTS; it never restates.**

What this file exists to prevent
--------------------------------
The wheel already ships the paved road — the packaged guide's sections, the console verbs, the
permission matrix. A thin pack of router skills in a consumer's repository fixes the *finding*
problem: each file fires on a task shape ("edit a document as a file", "why was I refused?")
and answers with an address, not with an explanation.

The danger is the same thing that makes the pack worth having. A hand-kept pack that *restates*
the guide is **a fifth copy of the truth, and the copy rots first** — it drifts the moment the
guide changes, and nothing notices, because prose has no resolver. So the pack ships with three
mechanical guards from its first commit:

1. **Anti-restatement** (:func:`test_no_router_RESTATES_the_shipped_guide`) — no contiguous
   :data:`OVERLAP_WORDS`-word span of a router's PROSE may also appear in the guide's prose.
   Quoted material — fenced blocks and inline code spans, which is where slugs, verbs and
   identifiers live — is removed from both sides first, because *citing* an address is the
   behaviour being encouraged, not the behaviour being caught. A second, blunter arm
   (:func:`test_every_router_stays_under_the_thinness_ceiling`) keeps a router from growing
   into an essay that happens to phrase everything freshly.
2. **Citations resolve** — every guide-section address a router names is resolved by calling
   ``larkdocio.guide`` and catching its refusal. That guard is
   ``tests/test_guide_citation_resolution.py``; the pack joins its corpus by a directory sweep
   (``tests/consumer_text.py::skill_pack_docs``), and :func:`test_the_citation_sweep_reaches_
   every_file_the_pack_has_on_disk` here pins that the sweep really reaches these files.
3. **Verbs resolve** (:func:`test_every_cli_verb_a_router_cites_is_a_real_command`) — a cited
   console verb is checked against click's own command tree, and a cited round-trip phase
   against the library's own ``PHASES``. Neither set is written down here; both are read out of
   the code, so a verb renamed tomorrow reddens instead of shipping a dead command.

Why the reach of arm 1 is MEASURED and not assumed
--------------------------------------------------
"Quoted material is removed from both sides first" is doing more work than it looks. The first
spelling of it was ``re.compile(r"```.*?```", re.S)``, and that regex **mis-pairs**: the guide
uses Markdown's own escape for showing a fence inside a sentence — a longer run of backticks,
```` ```mermaid ```` — which leaves a stray three-backtick run mid-prose, so the regex married a
*closing* fence to the next *opening* one and deleted **59% of the reference as if it were
code**. A guard cannot catch a paste into a part of the document it cannot see: 583 of the
guide's 710 substantial paragraphs were pastable into a router with the suite staying green.

Two things follow, and both are load-bearing:

* fences are parsed **line by line** (:func:`split_fences`), which is the only reading in which
  a fence is a property of a line rather than of a character offset — see that function for why
  it cannot mis-pair;
* the reference used by the *proofs* is read by **markdown-it-py**, not by this module's own
  normaliser (:func:`guide_paragraphs`). A plant drawn through the guard's own reading of the
  document can only ever come from the part the guard already sees, which is exactly how a proof
  covering 18% of the guide passed. :func:`test_EVERY_substantial_paragraph_of_the_shipped_guide_
  is_DETECTABLE` is the standing measurement.

Why the verb sweep reads COMMANDS and not prose
-----------------------------------------------
A command is a thing a reader copies, and a thing a reader copies is written in a code span.
Reading prose instead would make ``larkdocio is never auto-updated`` cite a verb called ``is``.
So the sweep reads code contexts only — and the hole that opens (a bogus command written as
prose) is closed from the other side by
:func:`test_no_command_line_call_HIDES_IN_PROSE`, which requires every ``larkdocio <word>`` in
the pack to be inside a code span in the first place. The two together leave nowhere for an
unresolvable verb to sit.

Not in ``consumer_corpus()``, and why
-------------------------------------
The pack is **copied into the consumer's repository, not packaged into the wheel** — an agent
harness discovers skills as files in the working repo, so an in-wheel copy would be inert until
something extracted it. ``tests/consumer_text.py::consumer_corpus`` means *text a consumer
reaches through the wheel*; enrolling the pack there would falsify that definition for every
guard that reuses it. It is a corpus of its own, and the guards that want it name it.
"""
import pathlib
import re
import subprocess

import pytest

import private_tree  # noqa: E402  (LD-691)

import consumer_text
from consumer_text import dialect_hits, skill_pack_docs, skill_pack_files

import larkdocio
from larkdocio.guide import _FENCE_DELIMITER

REPO_ROOT = pathlib.Path(consumer_text.REPO_ROOT)
SKILL_PACK = consumer_text.SKILL_PACK
INSTALLER = REPO_ROOT / "consumers" / "install-skills.sh"
SETUP = REPO_ROOT / "consumers" / "setup-consumer.sh"
CONSUMER_README = REPO_ROOT / "consumers" / "README.md"

#: The pack's size window. Fewer than five and the task shapes are too coarse to fire on
#: anything; more than eight and choosing between them is the same finding problem the pack
#: was built to remove.
PACK_MIN, PACK_MAX = 5, 8

#: The contiguous-word span that counts as restatement. Twelve is chosen so that a shared
#: technical phrase ("the plan is refused whole, with zero writes") cannot trip it while a
#: pasted sentence cannot escape it — a guide paragraph yields dozens of matching spans.
OVERLAP_WORDS = 12

#: A router that needs this many words of PROSE is explaining, and explaining is the guide's
#: job. Measured on prose alone (code spans and fences removed), so **adding a routing row
#: costs nothing and adding a paragraph costs everything** — which is the incentive the pack
#: needs. A ceiling over the raw file would have charged the same price for an address as for
#: an essay, and an author feeling that would drop addresses rather than prose.
#:
#: **Re-cut from 350 to 300 by LD-512, from a measurement rather than a feeling.** The reason
#: 350 was chosen — catch a slow slide, do not shave the current files — is preserved intact;
#: only the number moves, because 350 was not doing the first half. Measured 2026-08-19: the
#: six shipped routers carry **190, 194, 201, 203, 243 and 260** prose words, and the guide's
#: own paragraph census (:func:`guide_paragraphs`, markdown-it-py, ``minimum_words=40``) puts a
#: substantial guide paragraph at **40 words at its smallest** and **74 at the median** over
#: 710 paragraphs. At 350 the fattest router had **90** words of headroom — a whole median
#: paragraph of re-explanation, and then some — so the ceiling could not catch the one thing
#: its neighbouring check is paired with. 300 = the observed maximum (260) + 40, the census's
#: own floor for "a paragraph", so no router is shaved (the fattest keeps 40 words, the
#: leanest 110) and none can absorb even the *smallest* substantial guide paragraph on top of
#: its current length.
#:
#: **What this ceiling honestly does NOT do**, stated because the shipped wording used to
#: overclaim it (LD-499's residual, corrected in the same change): a single static ceiling
#: cannot make "a re-explanation in fresh words fails" true for *every* router at once. A file
#: at 190 words still has 110 to spend before it reddens. Making it true for the leanest file
#: would need a ceiling below 230, which would shave the two fattest — collateral this round
#: forbids. So the ceiling is what it says on the tin: a **slow-slide catcher** that bounds how
#: fat any router may get, and the overlap check next to it is what catches a copy.
#:
#: Measured on prose alone either way, so **adding a routing row still costs nothing**.
THINNESS_CEILING_WORDS = 300

#: How many equal slices of the guide the planted-restatement proof samples, front to back.
#: One paragraph is not a proof of reach: the guide's *first* paragraph is exactly the one a
#: mis-paired fence parse still handles correctly, which is how a guard covering 20% of the
#: document passed its own deliberate-defect test.
_PROOF_REGIONS = 8


# --------------------------------------------------------------------------- #
# TEXT NORMALISATION — one place, so the real pack and every planted defect     #
# below are judged by identical code.                                          #
# --------------------------------------------------------------------------- #

#: The fenced-code delimiter grammar, **imported rather than restated** —
#: :data:`larkdocio.guide._FENCE_DELIMITER` is the rule the shipped guide's own section index
#: is built with, and a guard carrying a second definition of a fence would drift from the
#: document it measures. Groups: the delimiter run, then the info string.
#:
#: It is anchored at **column 0**, as the library anchors it. An indented fence therefore reads
#: as prose — the safe direction for an anti-restatement guard, which must never see *less*
#: prose than there is. Neither the shipped guide nor the pack contains one (measured
#: 2026-08-17: 192 fence lines in the guide, 0 indented; 16 in the pack, 0 indented), and
#: :func:`test_the_fence_parse_agrees_with_the_LIBRARY_s_own_section_index` keeps that honest.
_FENCE_LINE = _FENCE_DELIMITER
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_WORD = re.compile(r"[a-z0-9]+")

#: A console invocation: ``larkdocio <verb> [<sub>]``, anchored to the START of its line.
#: The anchor is what keeps a Python fence honest — ``import larkdocio`` on one line and
#: ``print(...)`` on the next must not read as a verb called ``print``, and ``from larkdocio
#: import permissions`` must not read as a verb called ``import``. Both are false positives
#: that would teach an author to write around the guard rather than to the reader.
_COMMAND = re.compile(
    r"^larkdocio[ \t]+(?P<verb>[a-z][a-z0-9-]*)(?:[ \t]+(?P<sub>[a-z][a-z0-9-]*))?")

#: The prose-side arm of the same rule (see the module docstring).
_BARE_CALL = re.compile(r"\blarkdocio[ \t]+[a-z]")

#: The version-skew disclosure: one line naming the version the pack was copied from and the
#: script that refreshes the wheel it points at.
_VERSION = re.compile(r"\b(\d+\.\d+\.\d+)\b")
_CHANGELOG_SECTION = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.M)


def split_fences(text):
    """``(prose, blocks)`` — a **line-anchored** fenced-code parse.

    Why a state machine over lines and not a regex
    ----------------------------------------------
    The obvious spelling, ``re.compile(r"```.*?```", re.S)``, is the defect this function
    exists to remove. Markdown's own escape for showing a fence inside a code span is a
    **longer run of backticks** — ```` ```mermaid ```` — and the shipped guide uses it. That
    leaves a stray run of three backticks in the *middle of a prose line*, so the regex pairs a
    **closing** fence with the next **opening** one and deletes everything between them as if it
    were code. Measured on the guide of the day: the regex threw away 445,450 of 752,715
    characters — **59% of the reference, most of it prose** — and one single "match" swallowed
    24,881 characters of continuous explanation. An anti-restatement guard reading a reference
    with 59% of it missing cannot see a paste into the missing part.

    Why this cannot mis-pair
    ------------------------
    A fence is a property of a **line**, never of a character offset, and this parse only ever
    reads lines:

    * an **opening** run is recognised only at the start of a line (:data:`_FENCE_LINE` is
      anchored), so a longer run used *inside* a sentence is invisible to it;
    * an opening backtick run whose info string contains a backtick is **not** a fence — that is
      CommonMark's own rule, and it is exactly what makes ```` ```mermaid ```` at the head of a
      line a code span rather than an opener;
    * a **closing** run must be the same character, at least as long as the opener, and alone on
      its line — so a three-backtick line *inside* a four-backtick block is content, as a
      Markdown reader treats it.

    There is no offset arithmetic left for a pairing to go wrong in: prose can never be paired
    with prose, because prose never opens a fence.

    Every removed line is replaced by an **empty** line rather than deleted, so a fenced block
    stays a paragraph boundary instead of fusing the paragraphs either side of it into one.
    """
    prose, blocks, open_run, block = [], [], None, None
    for line in text.split("\n"):
        delimiter = _FENCE_LINE.match(line)
        run, info = delimiter.groups() if delimiter is not None else (None, None)
        if open_run is None:
            if run is not None and (run[0] == "~" or "`" not in info):
                open_run, block = run, [line]
                prose.append("")
            else:
                prose.append(line)
            continue
        block.append(line)
        prose.append("")
        if (run is not None and run[0] == open_run[0]
                and len(run) >= len(open_run) and not info.strip()):
            blocks.append("\n".join(block))
            open_run, block = None, None
    if block is not None:                      # an unterminated fence runs to end of document
        blocks.append("\n".join(block))
    return "\n".join(prose), blocks


def prose_of(text):
    """``text`` with fenced blocks and inline code spans removed.

    Both guards below read this rather than the raw file: a slug, a verb or an identifier is
    quoted material, and quoting the guide's own names is exactly what a router is for.
    """
    return _INLINE_CODE.sub(" ", split_fences(text)[0])


def words(text):
    return _WORD.findall(text.lower())


def code_contexts(text):
    """Every fenced block and inline code span in ``text`` — where a command is written."""
    stripped, blocks = split_fences(text)
    contexts = list(blocks)
    contexts.extend(match.group(0) for match in _INLINE_CODE.finditer(stripped))
    return contexts


# --------------------------------------------------------------------------- #
# THE THREE CHECKS, as pure functions over ``{label: text}``                    #
# --------------------------------------------------------------------------- #

def restated_spans(docs, reference, span=OVERLAP_WORDS):
    """``[(label, phrase)]`` for every contiguous ``span``-word run shared with ``reference``.

    ``reference`` is the guide as a consumer reads it. Both sides are reduced to prose words
    first, so an address in backticks is invisible here by construction.
    """
    haystack = words(prose_of(reference))
    grams = {tuple(haystack[i:i + span]) for i in range(len(haystack) - span + 1)}
    found = []
    for label, text in sorted(docs.items()):
        tokens = words(prose_of(text))
        for index in range(len(tokens) - span + 1):
            gram = tuple(tokens[index:index + span])
            if gram in grams:
                found.append((label, " ".join(gram)))
    return found


def command_lines(snippet):
    """Each line of a code context, reduced to what a reader would actually type.

    Leading fence/inline backticks and a shell prompt are stripped; nothing else is. A line
    that does not *begin* with the command is not an invocation of it.
    """
    for line in snippet.splitlines():
        yield line.strip().strip("`").strip().lstrip("$").strip()


def cited_commands(docs):
    """``[(label, verb, sub)]`` for every console invocation written in a code context."""
    found = []
    for label, text in sorted(docs.items()):
        for snippet in code_contexts(text):
            for line in command_lines(snippet):
                match = _COMMAND.match(line)
                if match:
                    found.append((label, match.group("verb"), match.group("sub")))
    return found


def unresolvable_commands(docs):
    """``[(label, verb, why)]`` for every cited invocation the shipped command tree refuses.

    The verb set and the round-trip phases are **read out of the code** — click's own
    ``commands`` mapping and ``larkdocio.roundtrip.PHASES`` — never written down here. A guard
    carrying its own copy of the answer is the fifth copy again.
    """
    from larkdocio.cli import cli
    from larkdocio.roundtrip import PHASES

    broken = []
    for label, verb, sub in cited_commands(docs):
        if verb not in cli.commands:
            broken.append((label, verb, f"no such command (the wheel ships "
                                        f"{', '.join(sorted(cli.commands))})"))
        elif verb == "roundtrip" and sub is not None and sub not in PHASES:
            broken.append((label, f"{verb} {sub}",
                           f"no such phase (the wheel ships {', '.join(PHASES)})"))
    return broken


def prose_hidden_calls(docs):
    """``[(label, snippet)]`` for a console invocation written outside a code context."""
    found = []
    for label, text in sorted(docs.items()):
        for match in _BARE_CALL.finditer(prose_of(text)):
            window = prose_of(text)[max(0, match.start() - 40):match.end() + 40]
            found.append((label, " ".join(window.split())))
    return found


def pack_docs():
    """The shipped pack, asserted non-empty so no check below can pass on nothing."""
    docs = skill_pack_docs()
    assert docs, (
        f"{SKILL_PACK} holds no files — every guard in this module would pass vacuously")
    return docs


def routers():
    """``{label: text}`` for the ``SKILL.md`` files only (the pack's routers)."""
    return {label: text for label, text in pack_docs().items() if label.endswith("SKILL.md")}


# =========================================================================== #
# THE PACK EXISTS, AND IS A PACK OF ROUTERS                                    #
# =========================================================================== #

def test_the_pack_holds_between_five_and_eight_routers():
    names = sorted(routers())
    assert PACK_MIN <= len(names) <= PACK_MAX, (
        f"the pack holds {len(names)} routers ({names}) — outside {PACK_MIN}..{PACK_MAX}")


def test_every_router_lives_at_its_own_directory_s_SKILL_md():
    """The layout a harness discovers: one directory per skill, one ``SKILL.md`` inside it."""
    for path in skill_pack_files():
        relative = path.relative_to(SKILL_PACK)
        assert relative.name == "SKILL.md" and len(relative.parts) == 2, (
            f"{relative} is not <skill-name>/SKILL.md — a harness discovers skills by that "
            "layout, and the installer copies whole directories on the strength of it")


def test_every_router_declares_the_TASK_SHAPE_it_fires_on():
    """A router that does not say when to reach for it is a document, not a router.

    The frontmatter ``description`` is the trigger a harness matches on, so it carries the
    task shape; ``name`` must equal the directory, which is how the copied file is addressed.
    """
    for label, text in sorted(routers().items()):
        directory = label.split("/")[2]
        assert text.startswith("---\n"), f"{label} has no frontmatter"
        front = text.split("---\n", 2)[1]
        name = re.search(r"^name:\s*(\S+)\s*$", front, re.M)
        description = re.search(r"^description:\s*(.+)$", front, re.M)
        assert name and name.group(1) == directory, (
            f"{label}: frontmatter name must be {directory!r}, got "
            f"{name.group(1) if name else None!r}")
        assert description and len(description.group(1).split()) >= 12, (
            f"{label}: the description IS the trigger — it must name the task shape this "
            "router fires on, in a sentence a matcher can actually discriminate on")


# =========================================================================== #
# AC1 — THE ANTI-RESTATEMENT MECHANISM                                         #
# =========================================================================== #

def test_no_router_RESTATES_the_shipped_guide():
    """The load-bearing guard: the pack points, it does not carry a copy of the guide.

    Failure names the file and the shared phrase, which is all a fix needs — delete the
    sentence and cite the section it came from instead.
    """
    offenders = restated_spans(routers(), larkdocio.guide(full=True))
    assert not offenders, (
        f"a router restates the shipped guide ({OVERLAP_WORDS}+ contiguous words of prose "
        "shared with it) — that makes the pack a second copy of the truth, and the copy rots "
        "first:\n" + "\n".join(f"  {label}: …{phrase}…" for label, phrase in offenders[:12])
        + "\n\nDelete the explanation and cite the section instead: a router POINTS.")


@pytest.mark.parametrize("region", range(_PROOF_REGIONS))
def test_the_anti_restatement_guard_REDDENS_on_a_planted_guide_paragraph(region):
    """DELIBERATE-DEFECT PROOF, driven through the SAME function the real pack goes through.

    Each paragraph is lifted out of the shipped guide at run time rather than pasted here, so
    the proof cannot rot into asserting on a sentence the guide stopped containing.

    **Why one paragraph was not enough.** This proof used to plant the guide's *first*
    substantial paragraph, and that is the one place a mis-paired fence parse cannot hide:
    everything before the guide's first quad-backtick escape survived the old regex, so the
    proof passed while 80% of the document was invisible to the guard. It now plants a
    paragraph from each of :data:`_PROOF_REGIONS` equal slices of the guide, front to back, so
    a reach that collapses anywhere reddens here instead of in a consumer's repository a year
    from now.
    """
    _line, paragraph = _guide_paragraph_in_region(region)
    planted = f"---\nname: x\ndescription: y\n---\n\n{paragraph}\n"
    offenders = restated_spans({"a planted router": planted}, larkdocio.guide(full=True))
    assert offenders, (
        f"the guard did not catch a paragraph copied verbatim out of region {region} of the "
        f"guide (GUIDE.md line {_line}) — a paste into that part of the document is invisible "
        f"to it:\n  …{paragraph[:160]}…")
    assert {label for label, _phrase in offenders} == {"a planted router"}


def test_the_permanent_proof_plants_a_paragraph_from_AFTER_the_first_QUAD_BACKTICK_escape():
    """The regression proof for the reach defect, in the one place it hid.

    The guide's CommonMark quad-backtick escape (```` ```mermaid ````) is what the old regex
    mis-paired on: everything **before** the first such line parsed correctly, and everything
    after it was liable to be swallowed. So this proof deliberately draws its paragraph from
    after that line — a proof that cannot pass on the surviving prefix.
    """
    escape = _first_quad_backtick_escape_line()
    line, paragraph = _first_guide_paragraph_after(escape)
    assert line > escape, "no substantial guide paragraph after the first quad-backtick escape"
    planted = f"---\nname: x\ndescription: y\n---\n\n{paragraph}\n"
    offenders = restated_spans({"a planted router": planted}, larkdocio.guide(full=True))
    assert offenders, (
        f"a paragraph from GUIDE.md line {line} — after the quad-backtick escape at line "
        f"{escape} — was pasted verbatim into a router and the guard stayed green:\n"
        f"  …{paragraph[:160]}…")


def test_EVERY_substantial_paragraph_of_the_shipped_guide_is_DETECTABLE():
    """The REACH of the guard, measured rather than assumed — the whole document, not a sample.

    AC1's protection is *"a router that starts restating the guide fails the build"*, and that
    sentence ships to a consumer in ``RELEASE_NOTES.md``. It is only true if a paste from
    **anywhere** in the guide reddens, so this test plants every substantial prose paragraph the
    reference parser finds and reports the ones that stay green. Measured 2026-08-17 on the
    merged guide: **710** paragraphs, **0** invisible; under the regex spelling this same census
    reported **583 of 710 invisible (82%)**.
    """
    paragraphs = guide_paragraphs()
    assert len(paragraphs) > 400, (
        f"only {len(paragraphs)} substantial paragraphs found in the guide — the reference is "
        "being read through something that is throwing prose away")
    reference = larkdocio.guide(full=True)
    haystack = words(prose_of(reference))
    grams = {tuple(haystack[i:i + OVERLAP_WORDS])
             for i in range(len(haystack) - OVERLAP_WORDS + 1)}
    invisible = []
    for line, paragraph in paragraphs:
        tokens = words(paragraph)
        if not any(tuple(tokens[i:i + OVERLAP_WORDS]) in grams
                   for i in range(len(tokens) - OVERLAP_WORDS + 1)):
            invisible.append((line, paragraph))
    assert not invisible, (
        f"{len(invisible)} of {len(paragraphs)} guide paragraphs could be pasted into a router "
        "undetected — the guard's reach is smaller than the claim it backs:\n"
        + "\n".join(f"  GUIDE.md:{line}: …{text[:120]}…" for line, text in invisible[:10]))


def test_the_fence_parse_SURVIVES_the_quad_backtick_escape_the_regex_spelling_mis_paired():
    """ROOT-CAUSE REGRESSION TEST — the two readings run side by side on the same six lines.

    The document below is the defect in miniature: two paragraphs of prose with a Markdown
    quad-backtick *escape* between them, which is how the guide writes a fence inside a
    sentence. The regex spelling pairs the stray closing run inside that sentence with the next
    opening fence and eats the paragraph in between; the line-anchored parse keeps both
    paragraphs and returns the one real block.
    """
    document = (
        "```python\nprint('a real block')\n```\n\n"
        "A sentence naming a ```` ```mermaid ```` fence in the middle of prose.\n\n"
        "The paragraph the regex spelling swallowed whole, which must stay visible.\n\n"
        "```bash\nlarkdocio download url\n```\n")
    prose, blocks = split_fences(document)
    assert "the regex spelling swallowed whole" in prose
    assert "naming a" in prose and "fence in the middle of prose" in prose
    assert len(blocks) == 2, blocks
    assert "print('a real block')" in blocks[0] and "larkdocio download url" in blocks[1]
    assert "print(" not in prose and "larkdocio download url" not in prose

    regex_reading = re.sub(r"```.*?```", " ", document, flags=re.S)
    assert "the regex spelling swallowed whole" not in regex_reading, (
        "the regex spelling no longer mis-pairs on this document — if that is a real change, "
        "this test has stopped demonstrating the defect and needs a new demonstration, not a "
        "deletion")


def test_the_fence_parse_keeps_a_SHORTER_run_inside_a_LONGER_block_as_content():
    """CommonMark's closing rule, which is the other half of not mis-pairing: a fence opened
    with four backticks is closed only by four or more, so the three-backtick lines inside it
    are content — not a close followed by a re-open that swallows the next paragraph."""
    document = (
        "````\n```python\nnested\n```\n````\n\n"
        "A paragraph after the block, which must survive.\n")
    prose, blocks = split_fences(document)
    assert "A paragraph after the block, which must survive." in prose
    assert len(blocks) == 1 and "nested" in blocks[0]


def test_the_fence_parse_agrees_with_the_LIBRARY_s_own_section_index():
    """The reference is the wheel's guide, so the guard must cut it where ``guide()`` cuts it.

    Every heading the library's index exposes has to survive into prose (a heading inside a
    fence is not a heading, and a heading the guard deleted as code is a section the reach
    measurement above never looks at). Held against ``guide_sections()`` rather than a count
    written down here.
    """
    unfenced, _blocks = split_fences(larkdocio.guide(full=True))
    headings = {line.strip() for line in unfenced.split("\n") if line.startswith("#")}
    missing = [section for section in larkdocio.guide_sections()
               if not any(section["heading"] in line for line in headings)]
    assert not missing, (
        f"{len(missing)} of {len(larkdocio.guide_sections())} sections the library indexes were "
        f"removed as code by the guard's fence parse: {[s['slug'] for s in missing][:8]}")


def test_the_shipped_guides_fences_are_BALANCED():
    """An unterminated fence runs to end of document, which would silently hide the tail of the
    guide from the reach measurement. Cheaper to assert the guide never has one."""
    _prose, blocks = split_fences(larkdocio.guide(full=True))
    assert blocks, "no fenced blocks found in the guide — the parse is not doing anything"
    for block in blocks:
        lines = block.split("\n")
        assert len(lines) >= 2 and _FENCE_LINE.match(lines[-1]), (
            "the shipped guide ends inside an unterminated fenced block, so everything after "
            f"its opener is invisible to the anti-restatement guard: …{lines[0][:60]}")


def test_the_anti_restatement_guard_does_NOT_bite_on_a_CITED_address():
    """The must-not-bite arm. Citing is the encouraged behaviour, so a router quoting a long
    slug, a heading and a full command must stay green — otherwise the guard would teach
    authors to paraphrase the guide, which is the defect wearing a disguise."""
    slug = "recipe-copy-this-the-end-to-end-update-script-from-url-to-applied-edit"
    cited = (
        "For this, read the section below and run the command.\n\n"
        f"- `larkdocio guide --section {slug}`\n"
        "- `larkdocio roundtrip pull \"<url>\" -o ./edit/`\n\n"
        f"```python\nimport larkdocio\nprint(larkdocio.guide(\"{slug}\"))\n```\n"
    )
    assert restated_spans({"a citing router": cited}, larkdocio.guide(full=True)) == []


def test_every_router_stays_under_the_thinness_ceiling():
    """The blunt second arm: a router phrased freshly but at essay length is still explaining.

    The overlap check above catches a *copy*; this catches a *paraphrase*, which is the same
    fifth copy written in different words and is exactly what an author reaches for once they
    know a copy will redden.
    """
    fat = {label: len(words(prose_of(text))) for label, text in routers().items()
           if len(words(prose_of(text))) > THINNESS_CEILING_WORDS}
    assert not fat, (
        f"these routers are past the {THINNESS_CEILING_WORDS}-word PROSE ceiling: {fat} — a "
        "router needing this many words of its own is explaining something the guide already "
        "explains; add the address and delete the explanation")


def guide_paragraphs(minimum_words=40):
    """``[(line_number, paragraph)]`` — every substantial prose paragraph of the shipped guide,
    read by **markdown-it-py**, deliberately NOT by :func:`prose_of`.

    THIS INDEPENDENCE IS THE WHOLE POINT, and it is the second half of the defect this file was
    reopened for. A plant drawn through the guard's own normaliser can never expose a hole in
    it: the old proof sampled the guide *after* the mis-paired regex had deleted 59% of it, so
    it could only ever plant a paragraph from the surviving part and could only ever pass.
    Measured: swapping :func:`split_fences` back to the regex spelling leaves the whole sampled
    proof **green** — but makes this census report 134 paragraphs where the reference parser
    finds 710.

    So the census comes from `markdown-it-py`, the CommonMark parser the wheel already depends
    on and the one ``compose()`` compiles the authoring dialect with — the same preset and
    extensions, imported rather than restated, so the reference reading is the library's own
    idea of Markdown and not a third one invented here. What a *paragraph* is, is that parser's
    answer; what the guard can *see* is measured against it.

    Inline code spans are removed from each paragraph because the guard removes them from the
    router side too: an address in backticks is what a router is supposed to carry.
    """
    from markdown_it import MarkdownIt

    from larkdocio.write.compose import _DIALECT_EXTENSIONS, _DIALECT_PRESET

    parser = MarkdownIt(_DIALECT_PRESET)
    for extension in _DIALECT_EXTENSIONS:
        parser = parser.enable(extension)

    tokens = parser.parse(larkdocio.guide(full=True))
    found = []
    for index, token in enumerate(tokens):
        if token.type != "paragraph_open":
            continue
        text = " ".join(_INLINE_CODE.sub(" ", tokens[index + 1].content).split())
        if len(words(text)) >= minimum_words:
            found.append((token.map[0] + 1, text))
    assert found, "the shipped guide has no substantial prose paragraph"
    return found


def _guide_paragraph_in_region(region):
    """One paragraph from slice ``region`` of :data:`_PROOF_REGIONS` equal slices, front to back."""
    paragraphs = guide_paragraphs()
    index = min(len(paragraphs) - 1, region * len(paragraphs) // _PROOF_REGIONS)
    return paragraphs[index]


def _first_quad_backtick_escape_line():
    """The guide's first line using the CommonMark quad-backtick escape (1-based)."""
    for number, line in enumerate(larkdocio.guide(full=True).split("\n"), 1):
        if "````" in line:
            return number
    raise AssertionError(
        "the shipped guide no longer uses the quad-backtick escape — this proof was written "
        "because that escape is what a regex fence-parse mis-pairs on; if the guide really "
        "stopped using it, re-point the proof at whatever the guide does instead rather than "
        "deleting it")


def _first_guide_paragraph_after(line_number):
    for line, paragraph in guide_paragraphs():
        if line > line_number:
            return line, paragraph
    raise AssertionError(f"no substantial guide paragraph after line {line_number}")


# =========================================================================== #
# AC2 — the citation sweep really reaches these files                          #
# =========================================================================== #

def test_the_citation_sweep_reaches_every_file_the_pack_has_on_disk():
    """The sweep is a DIRECTORY WALK, so a router added tomorrow enrols itself.

    Asserted against the filesystem rather than against a list, because a list is the one
    thing that can silently stop matching — which is a green guard guarding nothing.
    """
    import test_guide_citation_resolution as citations

    corpus = citations.citation_corpus()
    on_disk = {f"consumers/skills/{p.relative_to(SKILL_PACK).as_posix()}"
               for p in skill_pack_files()}
    assert on_disk, "no pack files on disk"
    missing = sorted(on_disk - set(corpus))
    assert not missing, (
        f"these pack files are not in the citation corpus: {missing} — the sweep stopped "
        "reaching the pack, so every slug in them is unchecked")


def test_the_pack_cites_the_guide_at_all():
    """A pack of routers that names no section is not routing anywhere.

    Counted through ``citations_in`` — the label-aware extractor — so this reads the pack's
    dominant spelling (a bare slug in a routing-table cell) as well as the console one. Read
    through ``_citations`` alone it would see 15 of the 54 addresses and still pass, which is
    exactly the blindness LD-499's QA caught.
    """
    import test_guide_citation_resolution as citations

    cited = set()
    exclude = citations.router_names()
    for label, text in pack_docs().items():
        cited.update(slug for _form, slug in citations.citations_in(label, text, exclude))
    assert len(cited) >= 10, (
        f"the pack cites only {len(cited)} guide sections ({sorted(cited)}) — a router pack "
        "that points nowhere has not replaced the finding problem it was built for")


# =========================================================================== #
# AC3 — every cited console verb resolves against click's real command tree     #
# =========================================================================== #

def test_every_cli_verb_a_router_cites_is_a_real_command():
    offenders = unresolvable_commands(pack_docs())
    assert not offenders, (
        "the pack cites console commands the wheel does not ship:\n"
        + "\n".join(f"  {label}: `larkdocio {verb}` → {why}" for label, verb, why in offenders))


def test_the_verb_guard_REDDENS_on_a_planted_nonexistent_verb():
    """DELIBERATE-DEFECT PROOF — the same function, over a planted document."""
    planted = {"a planted router": "Publish it with `larkdocio publish --all`.\n"}
    offenders = unresolvable_commands(planted)
    assert [(label, verb) for label, verb, _why in offenders] == [
        ("a planted router", "publish")], offenders
    assert "no such command" in offenders[0][2]


def test_the_verb_guard_REDDENS_on_a_planted_nonexistent_ROUND_TRIP_PHASE():
    """The second half of the same address: the phase is a real value in the library, so a
    router naming ``roundtrip sync`` is as broken as one naming a command that does not exist.
    """
    planted = {"a planted router": "Run `larkdocio roundtrip sync -o ./edit/`.\n"}
    offenders = unresolvable_commands(planted)
    assert [verb for _label, verb, _why in offenders] == ["roundtrip sync"], offenders


def test_the_verb_set_is_DERIVED_from_clicks_command_tree_not_hard_coded():
    """WHY the guard reads the code: a command renamed tomorrow must redden, and it only can
    if nothing here carries a second copy of the answer. Pinned by removing a real command
    from the tree and watching a citation of it break."""
    from larkdocio.cli import cli

    assert "download" in cli.commands
    document = {"doc": "Run `larkdocio download \"<url>\" -o ./out/`.\n"}
    assert unresolvable_commands(document) == []

    saved = cli.commands.pop("download")
    try:
        offenders = unresolvable_commands(document)
    finally:
        cli.commands["download"] = saved
    assert [verb for _label, verb, _why in offenders] == ["download"], (
        "the guard answered from its own list rather than from click's command tree")


def test_the_verb_sweep_reads_COMMANDS_and_not_PROSE():
    """The false-positive arm. A sweep over prose would read ``larkdocio is a toolkit`` as a
    citation of a command called ``is`` — and a guard that cries wolf gets written around."""
    assert cited_commands({"prose": "larkdocio is a Python toolkit for Lark documents.\n"}) == []
    assert cited_commands({"fence": "```bash\nlarkdocio folder \"<url>\"\n```\n"}) == [
        ("fence", "folder", None)]
    assert cited_commands({"span": "Run `larkdocio guide --section capability-matrix`.\n"}) == [
        ("span", "guide", None)]


@pytest.mark.parametrize("fence", [
    # the next statement must not become a verb named after it
    "```python\nimport larkdocio\nprint(larkdocio.guide())\n```\n",
    # `from larkdocio import permissions` must not cite a verb called `import`
    "```python\nfrom larkdocio import permissions\npermissions.permission_registry()\n```\n",
    # an attribute access is not an invocation
    "```python\nlarkdocio.capabilities()\n```\n",
])
def test_a_PYTHON_fence_is_not_read_as_a_console_invocation(fence):
    """The false positives the line anchor exists for. Each of these is real text a router
    wants to carry, and each would cite a command that does not exist if the sweep matched
    ``larkdocio`` anywhere on a line instead of at its start."""
    assert cited_commands({"py": fence}) == []


def test_no_command_line_call_HIDES_IN_PROSE():
    """The hole the code-context rule opens, closed from the other side.

    Every ``larkdocio <word>`` in the pack must sit inside a code span — which is also how a
    reader is meant to meet a command they will copy. Write ``the `larkdocio` wheel``, not
    ``the larkdocio wheel``.
    """
    offenders = prose_hidden_calls(pack_docs())
    assert not offenders, (
        "these console invocations are written as prose, where the verb guard cannot see "
        "them:\n" + "\n".join(f"  {label}: …{snippet}…" for label, snippet in offenders))


def test_the_prose_hiding_guard_REDDENS_on_a_verb_written_outside_a_code_span():
    planted = {"a planted router": "Then run larkdocio publish to ship it.\n"}
    assert [label for label, _s in prose_hidden_calls(planted)] == ["a planted router"]
    assert prose_hidden_calls({"ok": "Then run `larkdocio download` on it.\n"}) == []


# =========================================================================== #
# AC4 — the delivery mechanism, and the copy that cannot drift from the pack    #
# =========================================================================== #

def test_the_installer_EXISTS_and_is_executable():
    assert INSTALLER.is_file(), f"{INSTALLER} is missing — the pack has no copy step"
    assert INSTALLER.stat().st_mode & 0o111, f"{INSTALLER} is not executable"


def test_the_installer_copies_EVERY_file_in_the_pack(tmp_path):
    """Run the real installer into a throwaway consumer root and compare against the sweep.

    Not a parse of the script's text: the assertion is that the **files landed**. The expected
    set is the directory sweep, so a router added tomorrow is covered here with no edit.
    """
    result = subprocess.run(
        ["bash", str(INSTALLER), str(tmp_path)],
        capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

    target = tmp_path / ".claude" / "skills"
    installed = {p.relative_to(target).as_posix()
                 for p in target.rglob("*") if p.is_file()}
    expected = {p.relative_to(SKILL_PACK).as_posix() for p in skill_pack_files()}
    assert installed == expected, (
        f"the installer did not reproduce the pack: missing {sorted(expected - installed)}, "
        f"unexpected {sorted(installed - expected)}")
    # Byte-identical EXCEPT the version-skew banner, which the installer restamps with the
    # version and date of THIS copy (LD-694 F22 — see the next test). The rule this loop held,
    # "a copy is the pack, unaltered", still holds for every other line.
    for relative in sorted(expected):
        copied = (target / relative).read_text(encoding="utf-8").splitlines()
        source = (SKILL_PACK / relative).read_text(encoding="utf-8").splitlines()
        assert [ln for ln in copied if "Version skew" not in ln] == [
            ln for ln in source if "Version skew" not in ln], f"{relative} copied altered"


def test_the_installer_STAMPS_each_copy_with_the_version_it_was_copied_from(tmp_path):
    """LD-694 F22: the banner said "Copied from a larkdocio checkout, 1.43.0, on 2026-08-31"
    in every file, and a re-copy reproduced exactly that, whatever the checkout's version —
    so the stamp a consumer is told to rely on was stale from the first release after it was
    typed. The installer now writes the checkout's own ``__version__`` and the day of the
    copy into every banner it lands."""
    import datetime

    result = subprocess.run(["bash", str(INSTALLER), str(tmp_path)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    days = {datetime.date.today().isoformat(),
            datetime.datetime.now(datetime.timezone.utc).date().isoformat()}
    target = tmp_path / ".claude" / "skills"
    for label in sorted(routers()):
        copied = (target / pathlib.Path(label).relative_to("consumers/skills")
                  if label.startswith("consumers/skills/") else target / label)
        banner = _banner_line(copied.read_text(encoding="utf-8"))
        assert banner is not None, label
        assert f"**{larkdocio.__version__}**" in banner, (label, banner)
        assert f"newer than {larkdocio.__version__}?" in banner, (label, banner)
        assert any(f"**{day}**" in banner for day in days), (label, banner)


def test_the_installer_is_IDEMPOTENT(tmp_path):
    """Onboarding is re-run; a second pass must refresh rather than duplicate or refuse."""
    for _ in range(2):
        assert subprocess.run(["bash", str(INSTALLER), str(tmp_path)],
                              capture_output=True, text=True).returncode == 0
    target = tmp_path / ".claude" / "skills"
    assert {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()} == {
        p.relative_to(SKILL_PACK).as_posix() for p in skill_pack_files()}


def test_the_installer_ENUMERATES_the_directory_rather_than_listing_the_files():
    """A hand-written file list in the installer is the fifth copy again: it goes stale the
    first time somebody adds a router, and nothing reddens because the list is the guard."""
    text = INSTALLER.read_text(encoding="utf-8")
    named = sorted(path.parent.name for path in skill_pack_files())
    leaked = [name for name in named if name in text]
    assert not leaked, (
        f"{INSTALLER.name} names pack directories literally ({leaked}) — enumerate the pack "
        "directory instead, or the list rots the first time a router is added")


def test_setup_consumer_INVOKES_the_pack_installer_and_tells_the_reader():
    """The ruled delivery mechanism: the pack is installed alongside what onboarding already
    copies, and the printed to-do list says what landed and where."""
    text = SETUP.read_text(encoding="utf-8")
    assert "install-skills.sh" in text, (
        "setup-consumer.sh does not run the pack installer — the pack would exist and never "
        "be delivered")
    assert ".claude/skills" in text, (
        "setup-consumer.sh does not tell the reader where the pack landed")


@pytest.mark.parametrize("label", sorted(skill_pack_docs()))
def test_every_pack_file_carries_the_VERSION_SKEW_disclosure(label):
    """The stated cost of copying: a consumer's pack can outrun their vendored wheel.

    Each file therefore names the version it was copied from and the script that refreshes the
    wheel it points at. The version is checked to be one this repository's changelog actually
    declares — a fabricated version reddens, while a later release cut does not, because the
    version named stays a real one.
    """
    text = skill_pack_docs()[label]
    line = next((ln for ln in text.splitlines()
                 if "update_larkdocio.sh" in ln and _VERSION.search(ln)), None)
    assert line, (
        f"{label} carries no version-skew disclosure — one line naming the version this pack "
        "was copied from and pointing at `scripts/update_larkdocio.sh`")
    # LD-691 (maintainer ruling 2): "a real version" means one the RELEASE RECORD declares. That is
    # RELEASE_NOTES.md, the same in both trees and reaching back to 1.14.0; the root CHANGELOG.md
    # is the internal log here and a public changelog starting at 1.52.0 in the public tree.
    known = set(_CHANGELOG_SECTION.findall(
        (REPO_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")))
    disclosed = set(_VERSION.findall(line))
    assert disclosed <= known, (
        f"{label} discloses {sorted(disclosed - known)}, which this repository's "
        f"RELEASE_NOTES.md does not declare — name a real version")


def test_the_consumer_walkthrough_GAINS_the_pack():
    text = CONSUMER_README.read_text(encoding="utf-8")
    assert "skills/" in text and ".claude/skills" in text, (
        "consumers/README.md does not walk a reader through the pack")
    assert "install-skills.sh" in text


# =========================================================================== #
# AC1 — the version-skew banner: dated, both directions, one authoring site,   #
# and a path DERIVED from the install site rather than retyped six times       #
# =========================================================================== #

#: Where the canonical refresh script lands in the CONSUMER's own repo — parsed out of
#: ``setup-consumer.sh``'s own copy step rather than hard-coded here, so a change to where
#: onboarding installs the script is what the banner has to track, not a guess this test
#: carries separately (LD-573 AC1(c): a PRESENT-verification of a consumer-repo-relative path
#: that is correctly ABSENT in this repo).
_INSTALL_DEST = re.compile(r'cp\s+"\$UPDATE_SRC"\s+"\$CONSUMER/(?P<path>[^"]+)"')

#: A calendar date, ``YYYY-MM-DD`` — the banner's own "as of" stamp (AC1(a)).
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def _derived_update_script_path():
    """The path ``setup-consumer.sh`` installs the refresh script to, in the CONSUMER's repo.

    Not a literal this test carries: parsed from the install line itself, so a future change
    to where onboarding drops the script is exactly what the banner is checked against.
    """
    text = SETUP.read_text(encoding="utf-8")
    match = _INSTALL_DEST.search(text)
    assert match, (
        f"{SETUP} no longer shows a `cp $UPDATE_SRC $CONSUMER/...` install line — the banner's "
        "path has nothing to derive from")
    return match.group("path")


def _banner_line(text):
    """The single version-skew banner line in ``text``, or ``None``."""
    return next((ln for ln in text.splitlines() if "Version skew" in ln), None)


def test_the_version_skew_banner_is_BYTE_IDENTICAL_across_the_pack():
    """One authoring site: every one of the SIX packs carries the exact same banner line.

    A banner retyped six times is the fifth-copy defect this whole pack exists to avoid,
    wearing a disguise — six independent chances to drift, one of which already had (the
    five-vs-six count itself, corrected 2026-08-25). Byte identity is the only check that
    catches a silent divergence between copies that all still individually "look right".
    """
    banners = {label: _banner_line(text) for label, text in sorted(routers().items())}
    missing = [label for label, line in banners.items() if line is None]
    assert not missing, f"no version-skew banner line found in: {missing}"
    distinct = set(banners.values())
    assert len(distinct) == 1, (
        f"the version-skew banner is not byte-identical across the pack ({len(distinct)} "
        f"distinct lines found):\n" + "\n".join(f"  {label}: {line}" for label, line in banners.items()))


def test_the_version_skew_banner_is_DATED():
    """AC1(a): the banner names the version it was copied from AS OF A DATE, not just a bare
    version number that never says when that snapshot was taken."""
    banner = _banner_line(routers()[sorted(routers())[0]])
    assert banner is not None
    assert _DATE.search(banner), (
        f"the version-skew banner carries no YYYY-MM-DD date: {banner!r}")


def test_the_version_skew_banner_names_BOTH_skew_directions():
    """AC1(b), ADDITIVE: the existing direction (a consumer's wheel is OLDER than the pack) is
    correct and must survive; what was missing is the other direction (the PACK is older than
    the wheel, which is this repo's own state today) — both must be named, each with what to do.
    """
    banner = _banner_line(routers()[sorted(routers())[0]])
    assert banner is not None
    lowered = banner.lower()
    assert "older" in lowered, (
        "the banner dropped the EXISTING direction (a consumer's wheel can be older than the "
        "pack) — that direction is correct and must not be deleted, only joined by the other one")
    assert "newer" in lowered, (
        "the banner is missing the direction FIX-PROGRAM-SCRUTINY added: the pack itself can be "
        "older than the wheel (this repo's state today), which reads as the wheel being NEWER "
        "than what the pack was copied from")


def test_the_version_skew_banner_path_is_DERIVED_from_the_install_site():
    """AC1(c): the banner points at the path in the CONSUMER's repo that onboarding actually
    installs the refresh script to — derived from ``setup-consumer.sh``'s own copy step, never
    retyped as a second guess. ``scripts/update_larkdocio.sh`` is correctly ABSENT from this
    (the larkdocio dev) repo: it is consumer-repo-relative, and this is a PRESENT-verification
    of the derivation, not a filesystem check.
    """
    derived = _derived_update_script_path()
    assert derived == "scripts/update_larkdocio.sh", (
        f"setup-consumer.sh now installs the refresh script to {derived!r} — the banner's "
        "path derivation must track this, and so must every other row check below")
    banner = _banner_line(routers()[sorted(routers())[0]])
    assert banner is not None
    assert f"`{derived}`" in banner, (
        f"the banner does not cite the derived install path {derived!r} in a code span: {banner!r}")


def test_the_derived_path_MATCHES_the_consumer_README():
    """The same derivation, held against ``consumers/README.md``'s own mention (line ~169) — one
    fact, checked in both places it is written, rather than two independent guesses that could
    silently diverge."""
    derived = _derived_update_script_path()
    readme = CONSUMER_README.read_text(encoding="utf-8")
    assert f"`{derived}`" in readme, (
        f"consumers/README.md does not cite the derived install path {derived!r} — the banner "
        "and the walkthrough must agree on where the script lands")


# =========================================================================== #
# AC2 — the flatten/refuse claim matches what compose() actually does          #
# =========================================================================== #

def test_compose_ACTUALLY_refuses_bold_italics_and_a_labelled_link_but_not_a_bare_url_link():
    """The ground truth AC2's doc fix is held against — a real ``compose()`` run, not memory.

    ``[url](url)`` (the label IS the href) is the reader's own bare-URL autolink shape and is
    the one link form that composes as plain unstyled text; a link with any OTHER label is a
    styled run and refuses, same as bold and italics.
    """
    from larkdocio.write.compose import compose
    from larkdocio.write.model import NewBlock

    composed = compose("Reference: [https://x](https://x)")
    assert len(composed) == 1 and isinstance(composed[0], NewBlock)
    assert composed[0].text == "Reference: https://x", (
        "the bare-URL link shape stopped composing to plain text — the pack's stated exception "
        "no longer holds")

    for markdown, marker in (
        ("Reference: **bold** text", "bold"),
        ("Reference: *italic* text", "italic"),
        ("Reference: [a link](https://x)", "a labelled link"),
    ):
        with pytest.raises(Exception) as excinfo:
            compose(markdown)
        assert "styled" in str(excinfo.value).lower() or "not expressible" in str(excinfo.value).lower(), (
            f"compose() no longer refuses {marker} the way the pack's text assumes: {excinfo.value}")


def test_the_edit_pack_does_NOT_claim_a_bare_url_link_refuses():
    """The defect itself: the shipped sentence used to claim EVERY link inside a whole-block
    edit refuses, which is false for the one shape whose label is its own URL."""
    text = pack_docs()["consumers/skills/larkdocio-edit-a-document-as-a-file/SKILL.md"]
    lowered = prose_of(text).lower()
    assert "or a link inside such a block refuses" not in lowered, (
        "larkdocio-edit-a-document-as-a-file/SKILL.md still claims a bare blanket refusal for "
        "'a link' — the [url](url) shape composes successfully and the sentence must say so")
    assert "labelled link" in lowered or "labeled link" in lowered, (
        "the corrected sentence should name a LABELLED link as what refuses, distinguishing it "
        "from the bare-URL shape that does not")


# =========================================================================== #
# AC3 — a routing row for growing an existing table's row count, in the right  #
# file, pointing at a real (post-LD-569) destination                          #
# =========================================================================== #

_TABLE_ROW_HOOK = re.compile(r"table\b.*\brow\b|row\b.*\btable\b", re.I)


def test_a_table_row_routing_row_exists_ONLY_in_author_into_a_document():
    """AC3: the missing routing row lands in ``larkdocio-author-into-a-document`` (203/300
    words, the file with headroom) and NOT in ``larkdocio-edit-a-document-as-a-file`` (273/300,
    already AC1+AC2's target, with no room left for a new row)."""
    docs = pack_docs()
    target = "consumers/skills/larkdocio-author-into-a-document/SKILL.md"
    forbidden = "consumers/skills/larkdocio-edit-a-document-as-a-file/SKILL.md"

    assert _TABLE_ROW_HOOK.search(prose_of(docs[target])), (
        f"{target} carries no routing row for adding/removing a row of an existing table")
    assert not _TABLE_ROW_HOOK.search(prose_of(docs[forbidden])), (
        f"{forbidden} is at the thinness ceiling with no headroom for a new row — the table-row "
        "hook must land in larkdocio-author-into-a-document instead")


def test_the_table_row_routing_row_cites_a_REAL_guide_destination():
    """The row must point somewhere that actually answers the question.

    TRANSFORMED, not struck (LD-575). LD-573's reason holds: a stale citation here routes a
    reader to a section that says nothing about growing a table, so the destination is
    guarded. What changed is which destination answers the question — there is now a RECIPE
    that appends a row, so the row cites that instead of the router that used to list two
    costed workarounds. The demand is unchanged in kind: cite a destination that resolves,
    and one that is about this.
    """
    import test_guide_citation_resolution as citations

    target = "consumers/skills/larkdocio-author-into-a-document/SKILL.md"
    text = pack_docs()[target]
    exclude = citations.router_names()
    cited = {slug for _form, slug in citations._routing_addresses(text, exclude)}
    router_slug = "recipe-add-a-row-to-a-table-that-already-exists"
    assert router_slug in cited, (
        f"{target}'s table-row hook does not cite the write-recipe router "
        f"({router_slug!r}) — cited: {sorted(cited)}")
    # And that address must actually resolve (belt-and-suspenders with the citation-resolution
    # guard, which reads the whole pack rather than this one row).
    assert larkdocio.guide(section=router_slug)


def test_the_table_row_hook_carries_NO_issue_id():
    """AC3's hard constraint: consumer voice, no issue ids — ``dialect_hits`` is what the real
    guard (`test_the_pack_is_FREE_of_this_repository_s_internal_dialect`) reads; this asserts
    the same thing scoped to just the new hook so a future edit to it is caught early."""
    target = "consumers/skills/larkdocio-author-into-a-document/SKILL.md"
    text = pack_docs()[target]
    for line in text.splitlines():
        if _TABLE_ROW_HOOK.search(line):
            assert not dialect_hits(line), (
                f"the table-row routing line carries internal dialect: {line!r}")


# =========================================================================== #
# AC5 — the pack changes NO library behaviour                                  #
# =========================================================================== #

def test_the_pack_is_MARKDOWN_and_nothing_else():
    """No code, no data file, no dependency — the pack is text a harness reads."""
    wrong = [p.name for p in skill_pack_files() if p.suffix != ".md"]
    assert not wrong, f"non-Markdown files in the pack: {wrong}"


def test_no_shipped_MODULE_reaches_for_the_pack():
    """The pack is a consumer-repo artifact. If the library ever needed to read, extract or
    ship it, that is a packaging decision with its own issue — not a side effect of adding
    some Markdown to ``consumers/``.

    Scoped to **code**: the packaged release documents may of course *mention* the pack, and
    do — that is how a consumer finds out it exists. What must not happen is a module reaching
    for a path that only lives in the development repository. (Those mentions are held to the
    dev-repo labelling rule by ``tests/test_front_door_doctrine.py``, which is where that rule
    lives.)
    """
    src = REPO_ROOT / "src" / "larkdocio"
    offenders = [str(p.relative_to(REPO_ROOT)) for p in src.rglob("*.py")
                 if "consumers/skills" in p.read_text(encoding="utf-8", errors="ignore")]
    assert not offenders, f"a shipped module reaches for the copyable pack: {offenders}"


def test_the_pack_ships_in_NO_wheel():
    packaged = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "consumers/skills" not in packaged and "skills" not in packaged, (
        "the pack reached pyproject.toml — it is COPIED into a consumer repo, not packaged; "
        "an in-wheel copy is inert until something extracts it")


# =========================================================================== #
# AC6 — the purpose is recorded where the next reader looks                    #
# =========================================================================== #

def test_the_reason_the_pack_is_THIN_is_recorded_for_the_next_reader():
    """Without this, the next well-meaning reader "improves" a router into a restatement and
    the comparison the pack was built for measures nothing."""
    walkthrough = CONSUMER_README.read_text(encoding="utf-8")
    # TRANSFORMED, not weakened (LD-546 § A item 8, under process/doctrine/supersession.md
    # § A.1: preserve the reason, supersede only the conclusion). The REASON is unchanged and
    # is the docstring above. What is superseded is the ADDRESS FORM: this used to require
    # the literal ``progress/blocked/``, i.e. it pinned the citation to a BOARD COLUMN — and
    # a column citation rots the moment the issue moves, which is exactly what happened
    # (LD-479 reached ``progress/done/``). The guard now requires a STABLE address and, in the
    # added second leg, actively FORBIDS the column form — strictly more teeth than before.
    assert "LD-479" in walkthrough and "dev/dogfood5/DESIGN.md" in walkthrough, (
        "consumers/README.md does not point at the design that will measure this pack — a "
        "later reader has no way to know the thinness is deliberate")
    stale_columns = [c for c in ("progress/todo/", "progress/in_progress/", "progress/blocked/",
                                "progress/dev_complete/", "progress/qa_complete/", "progress/done/")
                     if f"`{c}" in walkthrough or f"]({c}" in walkthrough]
    assert not stale_columns, (
        "consumers/README.md cites a BOARD COLUMN as an address "
        f"({stale_columns}) — a column citation rots on the next board move; cite the issue id "
        "or the document's own permanent path instead (LD-546 § A item 8)")
    for phrase in ("A/B", "thin"):
        assert phrase in walkthrough, f"consumers/README.md does not say {phrase!r}"
    assert any("points" in text and "restate" in text.lower()
               for text in routers().values()), (
        "no router states the pack's own rule — the reader who edits one next reads the file, "
        "not the walkthrough")


# =========================================================================== #
# The pack is CONSUMER-VOICED text                                             #
# =========================================================================== #

def test_the_pack_is_FREE_of_this_repository_s_internal_dialect():
    """The pack is read in someone else's repository: an issue id, a role name or a word like
    ``dogfood`` resolves to nothing there. Same rule as every other consumer-reaching surface
    (``tests/test_consumer_dialect_guard.py``), applied to the pack's own corpus."""
    report = [(label, name, matched)
              for label, text in sorted(pack_docs().items())
              for name, matched in dialect_hits(text)]
    assert not report, (
        "internal dialect in the copyable skill pack:\n"
        + "\n".join(f"  {label}: [{name}] {matched!r}" for label, name, matched in report[:30]))
