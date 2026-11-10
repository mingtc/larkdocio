"""The ``section_addressing`` sentence — **derived per document, never asserted for all**.

LD-646. The sentence this module builds used to be one uniform string emitted for every
packaged document that had a ``<accessor>_sections`` sibling: *"Each ``###`` (and ``##``)
heading is individually retrievable"*. Two of the five documents — the release notes and the
changelog — are indexed at **level 2 only** (``RELEASE_NOTES_SECTION_LEVELS`` /
``CHANGELOG_SECTION_LEVELS``, and ``larkdocio.guide``'s comment above them records why: their
repeated per-release ``###`` headings would collide and make *every* call raise). So the
registry — the artifact this project tells consumers to trust over prose — shipped a
**generated false claim**, and a consumer following it got a ``ValueError``.

**The one rule this module keeps.** The levels in the sentence are read off the document's own
index rows, which :func:`larkdocio.guide._bounded_sections` produced from that document's
``*_SECTION_LEVELS`` constant. There is therefore **no second statement of a level anywhere** —
not a mapping here, not a tuple retyped beside the accessor table — and the claim cannot
advertise a level at which the document has no retrievable section, because every level in it
came from a section that exists. Under-claiming is the only failure mode left, and it is a
failure mode a consumer cannot be hurt by.
"""


def level_marks(rows) -> tuple:
    """The ATX marks (``##``, ``###`` …) the document's index rows actually sit at, ascending.

    Derived from the rows, so the answer is a fact about the packaged document as built, not a
    configuration read a second time.
    """
    return tuple("#" * level for level in sorted({row["level"] for row in rows}))


def section_addressing(name: str, rows) -> str:
    """The per-document addressability sentence, or ``None`` when there is nothing to address.

    *name* is the accessor's name (``guide``, ``release_notes`` …); *rows* its index rows.
    """
    marks = level_marks(rows)
    if not marks:  # a document whose index is empty claims nothing
        return None
    spelled = " and ".join(f"`{mark}`" for mark in marks)
    only = "" if len(marks) > 1 else " only"
    return (
        f"Indexed at {spelled}{only} — the heading levels THIS document is really addressable "
        f"at, derived from its own `sections` index above rather than assumed. Each such "
        f"heading is individually retrievable: `{name}(section=…)` takes either the heading "
        f"text or its slug, both case-insensitively. A heading at any other level is not a "
        f"section here and `section=` raises for it. Ask for one section rather than holding "
        f"the whole document."
    )
