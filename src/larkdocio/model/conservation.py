"""Which blocks the projection invites you to edit, and which it only conserves.

A block-identity marker says *what* a piece of Markdown came from. It does not say
whether changing that piece can mean anything. Some of what the reader renders, the
authoring dialect cannot recreate at all — an image, a synced block, an embed, a
whiteboard, a block type this release has never heard of — and some of it the reader
renders in a **different shape** than the block's own, so the Markdown is a projection
of the block rather than its content: a table is a pipe grid (or raw HTML when merged),
a mermaid add-on is a fenced source listing.

Editing those in the projection can only ever be a wish. **So the projection marks them
opaque, and the contract on an opaque block is conservation** — see
:data:`CONSERVATION_CONTRACT`.

**The line is derived, never listed.** Three pieces of code already know the answer and
this module joins them, so a block type that becomes supported tomorrow lands on one side
by construction rather than by someone remembering to edit a set:

* :func:`larkdocio.blocks.get_registry` — does the reader handle this type at all? An
  unhandled type has no content of its own in the Markdown and cannot be authored back;
* :data:`larkdocio.write.encode.CREATABLE_BLOCK_TYPES` — can the authoring dialect bring
  a block of this type into existence? If not, an edit to it could never be compiled;
* :data:`larkdocio.blocks.read_support.READ_SUPPORT` — is the reader's Markdown the
  block's **own** shape (``full``) or a reshaping of it (anything else)? A reshaped
  projection is not a thing an edit can be applied back to.

A type is **editable** when all three say yes, and **opaque** otherwise. The two sets are
therefore complementary and exhaustive over everything the reader knows about, which is
the property that keeps a newly supported type from falling into an unspecified middle
(``tests/test_opaque_marker_conservation.py``).

The join is computed on demand and cached, not frozen into a literal, for the same reason
the shipped read projection reads ``handled`` off the live registry: a stored copy is a
thing that can be wrong.
"""
from functools import lru_cache
from typing import Dict, Optional

__all__ = [
    "CONSERVATION_CONTRACT",
    "OPAQUE_CONSTRUCTS",
    "PROJECTION_STATES",
    "PROJECTION_STATE_MEANINGS",
    "editable_block_types",
    "opaque_block_types",
    "opaque_kind",
    "projection_support",
    "unknown_opaque_kind",
]

#: The two states a block type can be in, and the closed vocabulary the matrix column and
#: the shipped projection both answer in.
PROJECTION_STATES = ("editable", "opaque")

EDITABLE = PROJECTION_STATES[0]
OPAQUE = PROJECTION_STATES[1]

#: What each state means, shipped WITH the answer — a consumer holding only the wheel
#: cannot open the block matrix these words are defined in.
PROJECTION_STATE_MEANINGS = {
    EDITABLE: (
        "The projection's Markdown for this block is the block's own content in a shape "
        "the authoring dialect can compile back, so an edit to it is a change a "
        "reconciler can express as a request against this block."
    ),
    OPAQUE: (
        "The projection marks this block "
        "`<!-- lark:block:<id> opaque=<kind> -->` and conserves it: either the "
        "authoring dialect cannot create a block of this type at all, or the reader "
        "renders it in a different shape than the block's own, so no edit to the "
        "Markdown could be applied back to it. The block's readable content is still "
        "shown — opaque means 'do not reconcile me', not 'hide me'."
    ),
}

#: THE CONSERVATION CONTRACT. Stated here, ship-side, so the projection's
#: consumers and the reconciler read the same words. *Stating* it is this module's job;
#: enforcing it at reconcile time is the reconciler's.
CONSERVATION_CONTRACT = (
    "An opaque-marked block is left exactly alone by any reconciliation: it is not "
    "edited, not deleted, and not re-created — even if the edited projection omits it "
    "entirely. Conservation is the default posture and destruction is never inferred: "
    "the absence of a block from edited Markdown is evidence about the Markdown, not an "
    "instruction about the document. A table is opaque as a whole and its cells are not "
    "individually addressable through the projection; the supported route for changing "
    "one is the table-cell patch path in larkdocio.write, which addresses a cell "
    "directly instead of inferring it from prose."
)

#: The opaque kinds that have a named counterpart in the compiler's closed refusal set,
#: mapped to that construct — so the projection's "why" and the compiler's "why" cannot
#: drift into two different vocabularies. Guarded against
#: :data:`larkdocio.write.compose.NOT_EXPRESSIBLE_CONSTRUCTS`.
OPAQUE_CONSTRUCTS = {
    "image": "image",
    "divider": "thematic-break",
    "table": "merged-table",
}

#: The kind an UNREGISTERED block type projects under. Deliberately the reader's own
#: words — it already warns ``Unknown block type N (block_id=…)`` for exactly these — so
#: the projection reuses that identity instead of minting a second vocabulary for it.
_UNKNOWN_KIND = "unknown-block-type-{block_type}"


def unknown_opaque_kind(block_type: int) -> str:
    """The opaque kind for a block type the reader has no handler for."""
    return _UNKNOWN_KIND.format(block_type=block_type)


@lru_cache(maxsize=None)
def projection_support() -> Dict[int, str]:
    """``{block_type: "editable" | "opaque"}`` for every type the reader knows about.

    The join described in this module's docstring. Imported inside the function because
    it reaches across the package (the block registry, the write encoder) and this module
    is reachable from the renderer, which those import in turn.

    Cached, and the cache is a fixture-level concern only: nothing at runtime registers a
    handler after import. A test that monkeypatches the registry clears it
    (``projection_support.cache_clear()``).
    """
    from larkdocio.blocks import get_registry
    from larkdocio.blocks.read_support import READ_SUPPORT
    from larkdocio.write.encode import CREATABLE_BLOCK_TYPES

    registered = set(get_registry())
    lossiness = {block_type: state for block_type, _n, state, _e in READ_SUPPORT}

    support = {}
    for block_type in sorted(registered | set(lossiness)):
        editable = (
            block_type in registered
            and block_type in CREATABLE_BLOCK_TYPES
            and lossiness.get(block_type) == "full"
        )
        support[block_type] = EDITABLE if editable else OPAQUE
    return support


@lru_cache(maxsize=None)
def _kinds() -> Dict[int, str]:
    """``{block_type: kind}`` for every opaque type — the matrix's own name for a type
    the reader handles, and the reader's unknown-block identity for one it does not."""
    from larkdocio.blocks import get_registry
    from larkdocio.blocks.read_support import READ_SUPPORT

    registered = set(get_registry())
    names = {block_type: name for block_type, name, _s, _e in READ_SUPPORT}
    return {
        block_type: (
            names[block_type]
            if block_type in registered and block_type in names
            else unknown_opaque_kind(block_type)
        )
        for block_type, state in projection_support().items()
        if state == OPAQUE
    }


def editable_block_types() -> frozenset:
    """The block types whose projected Markdown an edit can be applied back to."""
    return frozenset(t for t, s in projection_support().items() if s == EDITABLE)


def opaque_block_types() -> frozenset:
    """The conserved set — the block types :data:`CONSERVATION_CONTRACT` covers."""
    return frozenset(t for t, s in projection_support().items() if s == OPAQUE)


def opaque_kind(block_type: Optional[int]) -> Optional[str]:
    """The ``opaque=`` kind for ``block_type``, or ``None`` when it is editable.

    ``None`` for ``block_type`` itself — a node with no source block type (the empty
    sentinel a dangling child id resolves to, the synthesized headless root, a node a
    caller built by hand) makes no claim either way, and the projection annotates only
    what the parser stamped from a real block.

    A type the reader does not handle is opaque under
    :func:`unknown_opaque_kind`, whether or not it is one the matrix documents: at read
    time it took the unknown-type fallback, and that is the identity to conserve it by.
    """
    if block_type is None:
        return None
    if projection_support().get(block_type) == EDITABLE:
        return None
    return _kinds().get(block_type) or unknown_opaque_kind(block_type)


def _clear_caches() -> None:
    """Test hook: drop both derivations (see :func:`projection_support`)."""
    projection_support.cache_clear()
    _kinds.cache_clear()
