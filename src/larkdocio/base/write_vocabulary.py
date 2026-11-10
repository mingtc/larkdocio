"""larkdocio.base.write_vocabulary — the write-side facts about Base field types.

**One constant, authored once.** Eight ``(type, ui_type)`` pairs are **computed or opaque**:
the server owns their value, so a caller cannot set them and a write that names them is either
refused or silently dropped. Two later rungs need that truth — the value encoder, which must
refuse the pair before building a request, and the diff, which must refuse it before a plan is
compiled — and if each defined its own list the two would drift the first time Lark added a
computed type. So the set lives **here**, in a module both import and neither owns, and a guard
asserts no second definition exists anywhere under ``src/``.

**Why each pair is non-writable, and how it was established.** Formula and Lookup are derived
values the server recomputes from the formula or from the linked record. AutoNumber is assigned
by the server at create time. The four record-metadata types — created / modified time and
created / modified user — are the server's own audit trail. Stage is the awkward one: it is
**fully opaque**, and a write to it answers ``code:0`` while changing nothing, with the table's
revision provably unmoved. That last case is why this set exists as data rather than as a
comment: a refusal a caller can read beats a success that did nothing.

The pairs are stated in the same ``(type, ui_type)`` form the read-side renderer registry
(:mod:`larkdocio.base.cells`) dispatches on, and the guard cross-checks every one of them
against that registry, so the read half and the write half cannot disagree about what a pair is.
"""
from typing import Dict, Tuple

#: The eight computed / opaque pairs. **Authored here, once** — imported, never re-declared.
NON_WRITABLE_PAIRS: Tuple[Tuple[int, str], ...] = (
    (19, "Lookup"),
    (20, "Formula"),
    (24, "Stage"),
    (1001, "CreatedTime"),
    (1002, "ModifiedTime"),
    (1003, "CreatedUser"),
    (1004, "ModifiedUser"),
    (1005, "AutoNumber"),
)

#: Why each pair cannot be written, in terms a caller can act on.
NON_WRITABLE_REASONS: Dict[Tuple[int, str], str] = {
    (19, "Lookup"): (
        "A Lookup mirrors a field on a linked record: the server recomputes it from the link, "
        "so there is nothing to set here. Write the value on the LINKED record instead."
    ),
    (20, "Formula"): (
        "A Formula is computed by the server from the formula stored on the field. Change the "
        "inputs the formula reads, or the formula itself, not the cell."
    ),
    (24, "Stage"): (
        "Stage is fully opaque: the schema is readable, the values are not, and a write "
        "answers success while changing nothing — the table revision does not move. It cannot "
        "be written through the API at all, so this refuses instead of appearing to succeed. "
        "Move the record in the product instead — a Stage transition is a drag of the card "
        "into the next stage, and no API route reaches it."
    ),
    (1001, "CreatedTime"): (
        "The creation timestamp is the server's own audit trail; it is stamped at create time "
        "and no request can set it."
    ),
    (1002, "ModifiedTime"): (
        "The last-modified timestamp is maintained by the server on every edit; it cannot be "
        "set, only observed."
    ),
    (1003, "CreatedUser"): (
        "The creating user is the identity the record was created under; it is recorded by the "
        "server and no request can set it."
    ),
    (1004, "ModifiedUser"): (
        "The last-modifying user is recorded by the server on every edit; it cannot be set, "
        "only observed."
    ),
    (1005, "AutoNumber"): (
        "An AutoNumber is allocated by the server when the record is created. It is not a "
        "value a caller supplies, and supplying one does not reserve it."
    ),
}


def is_non_writable(pair) -> bool:
    """``True`` when ``pair`` is one of the computed / opaque types a caller cannot set."""
    try:
        return tuple(pair) in set(NON_WRITABLE_PAIRS)
    except TypeError:
        return False


def non_writable_reason(pair):
    """Why ``pair`` cannot be written, or ``None`` when it can be."""
    try:
        return NON_WRITABLE_REASONS.get(tuple(pair))
    except TypeError:
        return None
