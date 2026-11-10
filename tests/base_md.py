"""The ``/BASE.md`` reading mechanics — the fourth living matrix's own parse seam (LD-308).

``guard_kit`` holds the *document-agnostic* text mechanics (``REPO_ROOT``, a fence-aware
``section``, ``md_table_rows``). This module holds the small amount that is specific to
``/BASE.md``'s own shape: where the document is, and how its tables are read.

Why it exists as a module of its own: the register parser was authored inside
``tests/test_base_md_matrix.py`` and then imported *from* that ``test_*`` module by four other
guards — a `test_*` file is not an importable helper surface, and the import coupled two guards
through pytest's rootdir-relative module namespace. One definition, which was right, in the
wrong kind of file. It now lives here, beside ``guard_kit``, named so pytest does not collect
it::

    from base_md import BASE_MD, register_rows

    rows = register_rows(BASE_MD.read_text(encoding="utf-8"))

Nothing here asserts anything — the assertions stay in the guards that own them. The functions
are byte-for-byte the ones that lived in ``test_base_md_matrix.py``; the only change is the
address.
"""

from guard_kit import REPO_ROOT, md_tables

#: The shipped Base capability matrix, resolved off the one repo-root derivation.
BASE_MD = REPO_ROOT / "BASE.md"


def tables(text):
    r"""Every pipe table in the document, as ``(headers, [row-dicts])``.

    **This is now one line, and that is the point (LD-632).** It used to carry its own parse,
    splitting a row with a naive ``stripped.strip("|").split("|")`` — and ``BASE.md``'s own
    ``**GFM safety**`` row, whose second cell contains a literal ``` `\|` ``` because the row
    is *about* that escape, yielded **five** cells against four headers and was dropped by the
    header-length check. The § Rendering-rule table has ten rows in the document and this
    function returned nine, so
    ``test_base_md_matrix.py::test_every_rendering_row_names_a_RESOLVING_anchor_and_carries_evidence``
    never resolved that row's anchor or its evidence: a guard that could not fail for the one
    row most likely to teach the parser something.

    The irony was that the fix already existed. ``guard_kit.md_table_cells`` was written to
    prevent exactly this and reads the same line as four cells; this module was the one helper
    beside ``guard_kit`` that imported only ``REPO_ROOT`` from it. It now delegates, so there
    is one escape-honouring definition instead of a correct one and a lossy one.
    """
    return md_tables(text)


def table_with(text, *required_headers):
    matches = [
        (h, r) for h, r in tables(text)
        if all(any(req.lower() in col.lower() for col in h) for req in required_headers)
    ]
    assert len(matches) >= 1, f"no table in BASE.md carries the headers {required_headers}"
    return matches


def field_rows(text):
    """The three field tables (Basic / Business / Advanced), concatenated."""
    rows = []
    for _headers, table_rows in table_with(text, "UI name", "API identity", "Read status"):
        rows.extend(table_rows)
    return rows


def register_rows(text):
    """§ Limitations & revisit-triggers — the register, as row-dicts."""
    matches = table_with(text, "Limitation / workaround", "Revisit trigger")
    assert len(matches) == 1, "the register must be exactly one table"
    return matches[0][1]
