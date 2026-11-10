"""larkdocio.common.notes — the ONE preview-note convention both write surfaces share.

A ``preview_note`` is a plan entry's non-refusing disclosure: the op will proceed, and here is
what a human approving it needs to know first (a value that will overwrite a live formula, a
delete that intersects a merge, an edit into text reviewers have commented on). The convention
has one rule that matters more than its shape:

**a warning must never displace another warning.** An entry can legitimately earn several
disclosures, so a note is either a single ``{"kind": …, "note": …}`` dict or a
:data:`NOTE_KIND_MULTIPLE` envelope carrying a list of them, and :func:`preview_notes_of` is
the ONE accessor that flattens both. Before that composition existed, a second disclosure
overwrote the first and shipped one — the same class of defect as a warning lost between plan
and apply-log.

**ZERO-DRIFT on the wire.** :func:`combine_preview_notes` returns the note *itself* when
exactly one applies, so a single-note entry serializes byte-identically to what shipped before
the envelope existed; the envelope appears only from the second note onward.

**Why it lives in ``common``.** Both write surfaces need it — sheets for its value/structural
disclosures, docx for the reviewer-anchor disclosure on the sub-span path — and a second
hand-rolled copy of a convention whose whole purpose is *not losing a disclosure* would be
exactly the wrong thing to duplicate. Same reasoning as
:mod:`larkdocio.common.staleness`: one core, imported by both, so the two cannot drift.
"""
from typing import Optional, Tuple

#: The composite note kind — carries the individual notes in ``notes``.
NOTE_KIND_MULTIPLE = "multiple"


def preview_notes_of(note) -> Tuple[dict, ...]:
    """Every individual disclosure inside a ``preview_note`` value — ``()`` for ``None``, a
    1-tuple for a single note, and the unwrapped list for a :data:`NOTE_KIND_MULTIPLE`
    envelope. The one place the two shapes are flattened, so no consumer has to know both."""
    if not note:
        return ()
    if isinstance(note, dict) and note.get("kind") == NOTE_KIND_MULTIPLE:
        return tuple(note.get("notes") or ())
    return (note,)


def combine_preview_notes(*notes) -> Optional[dict]:
    """Compose zero or more preview notes into ONE ``preview_note`` value.

    ``None`` when nothing applies, the note itself when exactly one does (so every shipped
    single-note wire form is byte-identical), else a :data:`NOTE_KIND_MULTIPLE` envelope whose
    ``notes`` list carries each disclosure in the order it was discovered — the op's own leg
    first, then the seam-stamped ones. Duplicates collapse, so composing is idempotent.
    """
    flat: list = []
    for note in notes:
        for one in preview_notes_of(note):
            if one not in flat:
                flat.append(one)
    if not flat:
        return None
    if len(flat) == 1:
        return flat[0]
    return {
        "kind": NOTE_KIND_MULTIPLE,
        "note": (
            f"this entry carries {len(flat)} disclosures — read ALL of them (kinds: "
            f"{', '.join(n.get('kind', '?') for n in flat)}). They are listed under `notes`; "
            f"`PlanEntry.preview_notes` / `ApplyLogEntry.preview_notes` flatten this envelope "
            f"and a single note to the same tuple."
        ),
        "notes": flat,
    }
