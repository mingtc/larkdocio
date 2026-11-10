"""The two round-trip working-directory filenames are **derived**, and the shipped guide has to
say so in the symbols a caller can actually read them from.

**Why this file exists.** ``roundtrip pull`` leaves two files in the working directory, and the
names were documented as bare literals — ``document.snapshot`` and ``document.md`` appeared in
prose eleven times across the shipped and repository documents, while
``SNAPSHOT_FILENAME`` / ``MARKDOWN_FILENAME``, the ``snapshot_path()`` / ``markdown_path()``
helpers, and ``PullResult.snapshot_path`` / ``.markdown_path`` — the derived surface a caller
actually holds after ``pull()`` — appeared **zero** times. A reader therefore learned a filename
and never learned that it is derived, which is precisely the shape of doc rot that ships: the
literal stays plausible long after the derivation is the only thing that is true.

Every claim below is held against **code**, never against itself:

* the constant names are read out of ``roundtrip.__all__`` and the ``PullResult`` field names
  out of the real dataclass, so a rename reddens the document;
* the literal values shown in the guide are compared with the real constants;
* the one-liner the guide tells a reader to run is **extracted from the guide and executed**,
  and its output is compared with the constants — the slug-stability precedent's own shape
  (name the derivation, give the one-liner that prints the current value, say what to hold);
* the helpers' derivation is exercised.

Nothing here asserts a behavior change: the two filenames, the helpers and ``PullResult`` are
byte-untouched. These tests pin what the code already does, which is what makes the document
falsifiable.
"""
import dataclasses
import re
import subprocess
import sys

import pytest

from larkdocio import roundtrip
from larkdocio.guide import guide


#: The guide section that carries the two-file recipe and its "Two files, two owners." bullet.
_HEADING = (
    "### Recipe: copy this — the end-to-end update script, from url to applied edit"
)

#: The derived surface, in the order the document should introduce it. Names only — the values
#: are read off the module below so nothing here is a second definition.
_CONSTANT_NAMES = ("SNAPSHOT_FILENAME", "MARKDOWN_FILENAME")
_HELPER_NAMES = ("snapshot_path", "markdown_path")


def section(text: str = None) -> str:
    """The recipe section, from its heading to the next ``###`` heading."""
    text = guide(full=True) if text is None else text
    start = text.find(_HEADING)
    assert start != -1, (
        f"the guide has no {_HEADING!r} section — the round-trip filename rule has no home"
    )
    nxt = text.find("\n### ", start + len(_HEADING))
    return text[start:nxt if nxt != -1 else len(text)]


def flat(text: str) -> str:
    """Prose with its line breaks collapsed and lower-cased — a phrase is a phrase whatever
    column the paragraph wrapped at, and a guard a re-wrap can redden teaches the next editor
    to satisfy it by not re-wrapping."""
    return re.sub(r"\s+", " ", text).lower()


def missing_symbols(section_text: str) -> list:
    """Which names of the derived surface the given section text never mentions.

    A pure function of the text so the same extractor can be pointed at a MUTATED section in
    the red proof below — otherwise the guard and the proof that it bites would be two
    different pieces of code.
    """
    wanted = [f"{name}" for name in _CONSTANT_NAMES]
    wanted += [f"{name}(" for name in _HELPER_NAMES]
    wanted += [f"PullResult.{name}" for name in _HELPER_NAMES]
    return [needle for needle in wanted if needle not in section_text]


# --------------------------------------------------------------------------- #
# The derived surface exists, and the guide names all of it.                    #
# --------------------------------------------------------------------------- #

def test_the_two_filename_constants_are_really_exported():
    """Pinned against the module first: a guard reading names nobody exports would green
    every assertion below it vacuously."""
    for name in _CONSTANT_NAMES:
        assert name in roundtrip.__all__, f"{name} is not in roundtrip.__all__"
        assert isinstance(getattr(roundtrip, name), str)


def test_the_two_path_helpers_are_really_callable_module_level_names():
    for name in _HELPER_NAMES:
        assert callable(getattr(roundtrip, name)), f"roundtrip.{name} is not callable"


def test_pull_result_really_carries_the_two_derived_paths():
    fields = [f.name for f in dataclasses.fields(roundtrip.PullResult)]
    for name in _HELPER_NAMES:
        assert name in fields, f"PullResult has no {name} field: {fields}"


def test_the_guide_names_the_WHOLE_derived_surface_not_only_the_literals():
    """The drift guard. Rename a constant, a helper or a ``PullResult`` field and this reddens,
    because the document is held against the module's own names."""
    missing = missing_symbols(section())
    assert not missing, (
        f"the round-trip recipe never names {missing} — a reader learns the filename and "
        f"never learns it is derived, which is the rot this guard exists to catch"
    )


def test_the_symbol_guard_BITES_when_the_document_drops_a_name():
    """Red proof, through the same extractor the live guard uses."""
    mutilated = section().replace("PullResult.markdown_path", "the markdown file")
    assert missing_symbols(mutilated) == ["PullResult.markdown_path"]


# --------------------------------------------------------------------------- #
# The values, the derivation and the one-liner — all executed.                  #
# --------------------------------------------------------------------------- #

def test_the_literals_shown_in_the_guide_ARE_the_real_constants():
    """The literals stay in the document (a reader must recognise the files on their disk),
    but they are held against the constants — change a constant and the document goes red."""
    text = section()
    for name in _CONSTANT_NAMES:
        value = getattr(roundtrip, name)
        assert f"`{value}`" in text, (
            f"the recipe never shows {value!r}, the current value of {name}"
        )


def test_the_helpers_really_derive_the_paths_from_the_constants(tmp_path):
    assert roundtrip.snapshot_path(tmp_path).name == roundtrip.SNAPSHOT_FILENAME
    assert roundtrip.markdown_path(tmp_path).name == roundtrip.MARKDOWN_FILENAME
    assert roundtrip.snapshot_path(tmp_path).parent == tmp_path
    assert roundtrip.markdown_path(tmp_path).parent == tmp_path


def _one_liner(text: str) -> str:
    """The ``python -c "…"`` command the guide's filename paragraph tells a reader to run."""
    found = [
        m.group(1)
        for m in re.finditer(r'python -c "(.+?)"', text)
        if "SNAPSHOT_FILENAME" in m.group(1)
    ]
    assert len(found) == 1, (
        f"the recipe must carry exactly one one-liner that prints the current filenames, "
        f"found {len(found)}"
    )
    return found[0]


def test_the_one_liner_the_guide_PRINTS_IS_RUNNABLE_and_agrees_with_the_constants():
    """The precedent's shape, executed: a one-liner nobody runs is a guess, and a reader who
    pastes a broken one is worse off than a reader who was told nothing."""
    completed = subprocess.run(
        [sys.executable, "-c", _one_liner(section())],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    out = completed.stdout
    assert roundtrip.SNAPSHOT_FILENAME in out and roundtrip.MARKDOWN_FILENAME in out, (
        f"the guide's one-liner printed {out!r}, which does not carry the current filenames"
    )


# --------------------------------------------------------------------------- #
# The stability posture — stated, not left to inference.                        #
# --------------------------------------------------------------------------- #

def filename_paragraph(text: str = None) -> str:
    """The one blank-line-separated block of the recipe that names ``SNAPSHOT_FILENAME``.

    The posture assertions read this rather than the whole section, because the section already
    says the word "derived" about something else entirely (the projection is derived from the
    snapshot payload) — a whole-section grep would pass on a sentence about a different subject.
    """
    blocks = [b for b in section(text).split("\n\n") if "SNAPSHOT_FILENAME" in b]
    assert len(blocks) == 1, (
        f"the filename rule must live in exactly one block of the recipe, found {len(blocks)}"
    )
    return blocks[0]


def test_the_guide_states_that_the_NAMES_ARE_DERIVED():
    low = flat(filename_paragraph())
    assert "derived" in low, (
        "the recipe must say the two filenames are derived, not merely show them"
    )


def test_the_guide_states_WHAT_IS_NOT_PROMISED_about_the_two_names():
    """The posture, in the shape the guide-slug precedent used: say what a consumer should hold
    instead of a hard-coded string. A document that shows a literal and promises nothing at all
    is what sent a reader to hard-code it in the first place."""
    low = flat(filename_paragraph())
    assert "hard-code" in low or "hard code" in low, (
        "the recipe must say something explicit about hard-coding the two names"
    )
    assert "not promised" in low or "no promise" in low or "does not promise" in low, (
        "the recipe must state what is NOT promised about the two names"
    )


def test_the_guide_tells_a_SHELL_caller_what_to_do():
    """The honest limit of the posture: a shell script cannot import a Python constant, so the
    one-liner is the answer for that caller and the document has to point at it."""
    low = flat(filename_paragraph())
    assert "shell" in low, (
        "a shell caller cannot import a constant — the recipe must address that reader"
    )


@pytest.mark.parametrize("name", _HELPER_NAMES)
def test_the_guide_says_PullResult_is_what_a_caller_actually_holds(name):
    low = flat(section())
    assert f"pullresult.{name}" in low
    assert "pull()" in low, (
        "the strongest pointer is the value pull() hands back; the recipe must name the call"
    )
