"""The guide's first routing table agrees with ``capabilities()``.

Round 2 of the public-export review found the shipped guide's "Which level does this ask
need?" table telling a reader that "A Base is **read-only** here" while the same library ships
``base-write`` and ``base-schema-write``. A row's family is derived from where the calls it
names live (``larkdocio.base.*`` → ``base``), and the family's write surfaces come from
``capabilities(full=True)["surfaces"]`` — so a later write surface makes a stale row red here.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import larkdocio

GUIDE = Path(larkdocio.__file__).resolve().parent / "GUIDE.md"
_HEADING = "### Which level does this ask need?"


def _rows():
    text = GUIDE.read_text(encoding="utf-8")
    start = text.index(_HEADING)
    body = text[start + len(_HEADING):]
    body = body[: body.index("\n### ")]
    rows = [ln for ln in body.splitlines() if ln.startswith("| ") and not ln.startswith("|---")]
    return rows[1:]  # drop the header row


def _family(name: str) -> str | None:
    obj = getattr(larkdocio, name, None)
    if obj is None:
        for mod in ("larkdocio.base", "larkdocio.drive", "larkdocio.sheets"):
            obj = getattr(importlib.import_module(mod), name, None)
            if obj is not None:
                break
    module = getattr(obj, "__module__", "") or ""
    parts = module.split(".")
    return parts[1] if len(parts) > 1 and parts[0] == "larkdocio" else None


def _writing_families() -> set[str]:
    surfaces = larkdocio.capabilities(full=True)["surfaces"]
    return {sid.split("-")[0] for sid, s in surfaces.items() if s["mode"] != "read"}


def test_the_table_is_found_and_names_a_base_and_a_folder_row():
    families = {_family(n) for row in _rows() for n in re.findall(r"`(\w+)`", row.split("|")[3])}
    assert {"base", "drive"} <= families


def test_no_row_calls_a_writing_family_read_only():
    writing = _writing_families()
    assert {"base", "drive"} <= writing
    for row in _rows():
        cells = row.split("|")
        names = re.findall(r"`(\w+)`", cells[3])
        families = {_family(n) for n in names} & writing
        if not families:
            continue
        assert "read-only" not in row.lower(), (
            f"the guide's routing row for {sorted(families)} says read-only, but capabilities() "
            f"reports a write surface for it:\n{row[:200]}")


def test_the_base_row_names_both_base_write_surfaces_and_their_recipes():
    (row,) = [r for r in _rows() if "`read_base`" in r]
    assert "record writes" in row and "schema writes" in row
    assert "Recipe: the Base write handshake" in row
    assert "Recipe: create, rename and copy a Base" in row
