"""ONE reader for a surface's call sites — the test-side seam for the collapsed key.

``capabilities(full=True)["surfaces"][sid]`` carries every call site under **one** key, each
row naming its own ``kind`` (LD-475 collapsed ``operations`` / ``legs`` / ``lifecycle``, whose
set varied per surface and which no shipped document defined). A test that wants "the
lifecycle rows" therefore filters by kind rather than reading a key, and it does it **here**,
once: twenty copies of the same filter is how a key rename becomes a twenty-file sweep, and
the key name itself is imported from the code that emits it rather than re-spelled.

The kind vocabulary is the library's own :data:`larkdocio.capabilities._models.CALL_KINDS`;
importing it is what makes a typo in a kind name a red test instead of an empty filter that
silently asserts nothing.
"""
from larkdocio.capabilities._models import CALL_KINDS, CALL_SITES_KEY

OPERATION, LEG, LIFECYCLE = CALL_KINDS


def call_sites(surface, kind=None):
    """Every call-site row of *surface*, or only those of *kind*, in serialization order."""
    if kind is not None:
        assert kind in CALL_KINDS, f"{kind!r} is not one of {CALL_KINDS}"
    rows = surface.get(CALL_SITES_KEY) or ()
    return [row for row in rows if kind is None or row.get("kind") == kind]


def names(surface, kind=None):
    """The names of :func:`call_sites`, in the same order."""
    return [row["name"] for row in call_sites(surface, kind)]


def by_name(surface, kind=None):
    """``{name: row}`` for :func:`call_sites` — refusing a duplicate name rather than letting
    one of two rows silently win every lookup (the ``guide_sections`` discipline)."""
    rows = call_sites(surface, kind)
    out = {row["name"]: row for row in rows}
    assert len(out) == len(rows), f"duplicate call-site name in {sorted(r['name'] for r in rows)}"
    return out


def scope_rows(payload, block, field="scopes"):
    """The ``scope_evidence`` rows a permission *block*'s *field* references.

    LD-475 moved the prose each requirement rests on into one top-level catalog and left the
    operation carrying its keys, so a test that wants the rows resolves them — here, once. The
    key is not parsed: the row's own ``scope`` field holds the string.
    """
    return [payload["scope_evidence"][key] for key in block.get(field) or ()]


def scope_strings(payload, block, field="scopes"):
    """The scope STRINGS a permission *block*'s *field* requires."""
    return {row["scope"] for row in scope_rows(payload, block, field)}
