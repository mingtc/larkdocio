"""LD-351 — the hand-kept README narrative absorbs the Drive surface and drops stale
surface-count numerals.

v1.29 shipped Drive folder read (its own ``folder`` CLI verb and ``drive-read`` capability
id). The machine-projected / guarded layers (``pyproject`` ``description``/``keywords``, the
CLI ``--help``, ``test_front_door_doctrine``) were corrected with it, but three lines of
**hand-kept prose no guard greps** still describe the pre-Drive world:

* the METADATA opening said "Five surfaces ship" (S1);
* the dev-section said "the single development home for all four surfaces" (S2);
* the ``capabilities()`` bullet under-stated the registry as "every docx + Sheets read/write
  operation" (N1).

This module pins the three corrected facts so the numerals cannot drift back.
"""
import re

import front_door as fd


def readme():
    return fd.readme_text()


def _capabilities_bullet(text):
    """The ``- `larkdocio.capabilities()`` — …`` bullet, up to the next top-level bullet."""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("- `larkdocio.capabilities()`"))
    end = next(
        (i for i, ln in enumerate(lines[start + 1:], start=start + 1) if ln.startswith("- ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


# --- AC1 (S1): the METADATA opening absorbs Drive -----------------------------------------

def test_ac1_the_opening_census_undercounts_no_surface():
    """TRANSFORMED by LD-440, not deleted (supersession § A.1).

    The reason is preserved: the METADATA opening must not undercount the surfaces — it said
    "Five surfaces ship" with six shipping, which is how this guard was earned. The
    conclusion — *state the count as the literal "Six surfaces ship"* — is superseded, because
    a hard count is the very thing that goes stale: sixteen surface ids ship as of LD-440 and
    the literal was still six. What replaces it is the derived check
    (``tests/test_front_door_census.py``): every surface family ``capabilities()`` reports is
    named in the opening, which cannot undercount by construction.
    """
    text = readme()
    assert "Five surfaces ship" not in text, (
        "the METADATA opening still says 'Five surfaces ship' — Drive is the sixth"
    )
    assert not re.search(r"\b(Five|Six|Seven|Eight) surfaces ship\b", text), (
        "the opening states a hard surface count again; it goes stale silently — the census "
        "guard in tests/test_front_door_census.py is what keeps it honest"
    )
    assert not fd.census_gaps(), fd.census_gaps()


def test_ac1_the_opening_enumerates_the_drive_surface():
    """The Drive clause is added to the opening enumeration, mirroring the guard-clean wording
    at README's layout row / cli.py (folder read)."""
    opening = fd.first_screenful(readme(), 12).lower()
    assert "**drive**" in opening or "drive**" in opening, (
        "the opening enumeration never names the drive surface"
    )
    assert "folder" in opening, "the Drive clause never mentions folder read"


# --- AC2 (S2): the stale dev-section numeral is dropped ------------------------------------

def test_ac2_no_stale_surface_count_numeral_survives():
    text = readme()
    assert "all four surfaces" not in text, (
        "the dev-section still says 'all four surfaces' — a numeral the layout table contradicts"
    )
    assert not re.search(r"\bfour surfaces\b", text), (
        "a 'four surfaces' numeral (contradicted by the layout table) remains in the README"
    )


# --- AC3 (N1): the capabilities() bullet stops under-stating the registry ------------------

def test_ac3_the_capabilities_bullet_names_the_full_span():
    bullet = _capabilities_bullet(readme())
    assert "docx +" not in bullet and "docx +\n" not in bullet, (
        "the capabilities() bullet still limits the registry to 'docx + Sheets'"
    )
    assert "across the surfaces" in bullet, (
        "the capabilities() bullet does not name the real span across the surfaces"
    )
