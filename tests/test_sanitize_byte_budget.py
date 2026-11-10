"""LD-659 AC2 — the filename budget is in BYTES, so a long CJK title stops crashing.

The defect, executed on `develop`: ``common/sanitize.py`` truncated to **100 characters**, and a
CJK codepoint is 3 UTF-8 bytes, so the ceiling was up to **300 bytes** against a 255-**byte**
``NAME_MAX``. A real Chinese document title of 79+ characters therefore failed the write —
``OSError`` — **after** the network fetch had already succeeded, which is the worst place to
fail: the caller paid for the download and received nothing.

Two ceilings now apply, and both are asserted here: the old character one (unchanged, so ASCII
names are byte-identical to what shipped) and the byte one (new, and the one the OS enforces).

The reserve held out of ``NAME_MAX`` for what CALLERS add to the name is **derived from the
call sites**, not trusted: two legs below compose the real filename and the real routed path
and subtract, a third reads the one literal decoration out of the source, and the enumeration
of call sites is an AST walk — so a new caller reddens rather than inheriting a budget nobody
checked against it. The pairing in :data:`DECLARED`'s second column is what keeps a site from
dropping silently out of the measured population instead of failing.
"""
import ast
import pathlib

import pytest

from larkdocio.common.sanitize import (
    DECORATION_RESERVE_BYTES,
    MAX_NAME_BYTES,
    MAX_NAME_CHARS,
    NAME_MAX_BYTES,
    UNTITLED,
    sanitize_path_string,
)
from larkdocio.read.config import new_config
from larkdocio.read.download import _apply_explicit_route, _write_markdown

SRC = pathlib.Path(__file__).resolve().parent.parent / "src"

#: Every call site of ``sanitize_path_string`` under ``src/``, and **how this module measures
#: what that site adds to the sanitized name**. The reserve is a claim about all of them, so a
#: site nobody assessed has to redden — and so does a site whose declared measurement stops
#: being possible, which is the failure this table's second column exists to prevent:
#:
#: * ``executed`` — the real composed filename is built here and subtracted (the only honest
#:   answer for ``f"[{stamp}]_{safe}.md"``, whose decoration is not a literal);
#: * ``literal`` — the call sits directly inside an f-string whose other parts are all
#:   constants, so the AST walk states the exact decoration;
#: * ``segment`` — the sanitized name becomes a whole path component with nothing added, which
#:   is executed below as well rather than taken on trust;
#: * ``predicate`` — the call answers a QUESTION about the name and its result never reaches a
#:   filesystem, so there is no decoration to measure and measuring one would be a fiction.
#:
#: **Amended by LD-665, and the amendment is this guard doing its job.** ``folder_cmd``'s
#: ``literal`` row and ``_write_markdown``'s composition both moved into the new composition
#: seam ``larkdocio.common.filename``; the population walk noticed on the first run and failed,
#: which is why this table is edited rather than the change landing unmeasured. No ``literal``
#: site remains today — the branch below is kept because the classification is still available
#: to a future site, not because anything currently exercises it, and that is said here rather
#: than left for a reader to discover.
DECLARED = {
    ("larkdocio/read/download.py", "_write_markdown"): "executed",
    ("larkdocio/read/download.py", "_apply_explicit_route"): "segment",
    ("larkdocio/common/filename.py", "compose_name"): "executed",
    ("larkdocio/common/sanitize.py", "truncates"): "predicate",
}


def call_sites():
    """``{(relative path, enclosing function): literal decoration bytes or None}`` — derived by
    :mod:`ast` over the real tree, never by import and never hand-listed.

    The value is the byte length of the constant parts of the f-string the call sits **directly**
    inside — the exact decoration when every other part of that f-string is a constant too.
    ``None`` means the source cannot answer (the call's result is carried through a variable, or
    the f-string interpolates something else), and then the site's measurement must be
    ``executed``: a guard that measured only the literals would report ``[{stamp}]_…md``'s 21
    bytes as 3 and pass.
    """
    found = {}
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for call in ast.walk(function):
                if not (isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Name)
                        and call.func.id == "sanitize_path_string"):
                    continue
                key = (path.relative_to(SRC).as_posix(), function.name)
                found.setdefault(key, None)
                for joined in ast.walk(function):
                    if not isinstance(joined, ast.JoinedStr):
                        continue
                    parts = [
                        part.value for part in joined.values
                        if isinstance(part, ast.FormattedValue)
                    ]
                    if not any(part is call for part in parts):
                        continue
                    if all(part is call for part in parts):
                        found[key] = sum(
                            len(part.value.encode("utf-8"))
                            for part in joined.values
                            if isinstance(part, ast.Constant) and isinstance(part.value, str)
                        )
    return found


# --------------------------------------------------------------------------- #
# The crash, as a regression test                                             #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("hanzi", [78, 79, 100, 200])
def test_a_long_CJK_title_writes_instead_of_raising(tmp_path, hanzi):
    """79 hanzi is the measured boundary: it raised ``OSError`` on ``develop``.

    The whole band is parametrized rather than just the boundary, because the failure was a
    function of BYTES and the 100- and 200-character cases are the ones a real document title
    reaches.
    """
    written = _write_markdown(new_config(), str(tmp_path), "doctoken", "汉" * hanzi, "# x\n")
    assert pathlib.Path(written).read_text(encoding="utf-8") == "# x\n"
    assert len(pathlib.Path(written).name.encode("utf-8")) <= NAME_MAX_BYTES


def test_the_truncation_never_emits_a_partial_utf8_sequence():
    """The cut walks back over continuation bytes, so what comes out is decodable text — and
    the byte length can land BELOW the ceiling because a 3-byte codepoint does not divide it."""
    out = sanitize_path_string("汉" * 200)
    assert out == out.encode("utf-8").decode("utf-8")
    assert len(out.encode("utf-8")) <= MAX_NAME_BYTES
    assert out == "汉" * (MAX_NAME_BYTES // 3)


def test_a_mixed_ascii_and_cjk_name_is_cut_by_whichever_ceiling_bites_first():
    ascii_only = sanitize_path_string("a" * 250)
    assert ascii_only == "a" * MAX_NAME_CHARS            # the character ceiling bites
    mixed = sanitize_path_string("a" * 50 + "汉" * 50)
    assert len(mixed) <= MAX_NAME_CHARS
    assert len(mixed.encode("utf-8")) <= MAX_NAME_BYTES  # 50 + 150 = 200 B, under both


def test_an_ascii_name_is_byte_identical_to_what_shipped():
    """The character ceiling is kept precisely so this stays true: no consumer's filenames
    move because of a fix for a crash they never hit."""
    for name in ("My Doc", "a" * 99, "a" * 100, "a" * 101, "a" * 250, "SPEC-001_v2"):
        assert sanitize_path_string(name) == name.replace(" ", "_")[:MAX_NAME_CHARS]


# --------------------------------------------------------------------------- #
# The reserve is derived from the call sites, not asserted about them          #
# --------------------------------------------------------------------------- #

def test_every_call_site_is_declared():
    """A new caller of the sanitizer reddens this, because the reserve is a claim about all of
    them. Non-empty is asserted first: a walk that found nothing would pass every other leg."""
    sites = call_sites()
    assert sites, "the AST walk found no call site at all — the walk itself is broken"
    assert set(sites) == set(DECLARED)


def test_each_site_is_measurable_THE_WAY_IT_SAYS_IT_IS():
    """The pairing that stops this guard from passing because it could not look: a site
    declared ``literal`` whose f-string the walk stops seeing reports ``None`` and fails here,
    instead of quietly dropping out of the measured population."""
    sites = call_sites()
    for key, method in DECLARED.items():
        if method == "literal":
            assert sites[key] is not None, f"{key} declares a literal decoration; the walk found none"
            assert sites[key] <= DECORATION_RESERVE_BYTES, (key, sites[key])
        else:
            assert sites[key] is None, (
                f"{key} is declared {method!r} but its decoration IS a literal now "
                f"({sites[key]} B) — re-declare it, do not leave it unmeasured"
            )


def test_the_reserve_covers_the_download_filename_MEASURED(tmp_path):
    """The ``executed`` site: compose the real filename and subtract the sanitized name.

    **The title here must NOT truncate, and LD-665 is why.** It used to be ``"汉" * 200``, which
    after LD-665 is disambiguated — the document's token joins the name — so the decoration
    measured would have been ``[stamp]_`` + ``.md`` + ``_`` + *the token*, and this leg would
    have been measuring the length of the string ``"tok"`` rather than the reserve. It passed,
    for the wrong reason. The reserve is a claim about what the sanitizer's own budget has to
    leave room for, which is the **uncut** path; the cut path budgets itself at the composition
    seam and is measured in ``tests/test_composed_filename_budget.py`` instead.
    """
    title = "汉" * 50  # 150 B, under both ceilings — reduced, never cut
    assert sanitize_path_string(title) == title
    written = pathlib.Path(_write_markdown(new_config(), str(tmp_path), "tok", title, "x"))
    decoration = len(written.name.encode("utf-8")) - len(
        sanitize_path_string(title).encode("utf-8"))
    assert 0 < decoration <= DECORATION_RESERVE_BYTES


def test_a_route_segment_really_gets_NO_decoration_MEASURED(tmp_path):
    """The ``segment`` site, executed rather than trusted: the sanitized segment is the whole
    path component, so the budget it needs is the whole of ``NAME_MAX``, not less."""
    routed = _apply_explicit_route(str(tmp_path), "汉" * 200)
    assert pathlib.Path(routed).name == sanitize_path_string("汉" * 200)
    assert len(pathlib.Path(routed).name.encode("utf-8")) <= NAME_MAX_BYTES


def test_the_byte_ceiling_is_derived_from_the_two_constants_above_it():
    assert MAX_NAME_BYTES == NAME_MAX_BYTES - DECORATION_RESERVE_BYTES
    assert MAX_NAME_BYTES + DECORATION_RESERVE_BYTES == NAME_MAX_BYTES == 255


def test_the_substitution_constant_is_still_what_the_download_keys_on(tmp_path):
    """``_write_markdown`` prefers the document token when the title sanitizes away, and it
    compares against this constant — so the constant and the comparison are one fact."""
    written = _write_markdown(new_config(), str(tmp_path), "doctoken", "***", "x")
    assert UNTITLED not in pathlib.Path(written).name
    assert "doctoken" in pathlib.Path(written).name
