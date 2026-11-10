# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""Doc-drift guards — cheap tests that LOCK the LD-055..058 doc fixes (LD-059).

Model: ``tests/test_blocks_md_matrix.py`` — a doc<->code coverage guard that keeps
a documented fact truthful against the thing it describes. Each test here asserts a
piece of documentation still agrees with the code / config / filesystem it claims to
mirror, so the fixed state cannot silently re-drift. Everything here is an offline,
deterministic file-parse test (no network, no SDK objects, fast).

The guards, by AC:
  * AC1 — the roles tables in PROJECT.md and CLAUDE.md list exactly the active
    ``.claude/roles/*.md`` docs (parked ``archive/ui-designer.md`` excluded).
  * AC2 — the CLAUDE.md commit-prefix table matches the set DERIVED from the
    commit-msg hook's ``ROLE_PREFIXES`` line (never re-hardcoded here).
  * AC3 — the dev-extras documented in PROJECT.md match
    ``pyproject.toml [project.optional-dependencies].dev``.
  * AC4 — every ``OutputConfig`` field is documented in TOOLS.md.
  * AC5 — no file under ``.claude/templates/`` carries the forge-specific
    string ``PR opened``.
  * AC6 — every retired ``dev/handoffs/YYYY-MM-DD-*.md`` (older than the newest)
    carries a RETIRED / superseded banner AT ITS HEAD, recognised structurally;
    and (LD-627, 2026-09-03) the NEWEST one carries none, ``README.md`` is not
    mistaken for a handoff, and all three legs are exercised on fixtures too.
  * AC7 — every ``dev/*.md`` + ``dev/handoffs/*.md`` is linked from ``dev/README.md`` (in the dev repo),
    AND (LD-361) every immediate SUBDIRECTORY of ``dev/`` is indexed there too, AND
    (LD-520, 2026-08-19) every ``](target)`` the README carries actually resolves on
    disk — catching an indexed-and-deleted file, the shape a retirement sweep produces.
    (LD-522, 2026-08-19) every artifact under ``dev/`` sits in exactly one of TWO
    indexes and neither has a dead entry — the second, ``dev/RETIRED.md``, is the one
    narrow class ``process/doctrine/retention.md`` permits (a ledgered retirement).
  * AC8 — a planning-record status guard; moved to its own private-only module (LD-704).
  * AC9 — ``qa.md`` references the golden regression test in its regression section.
  * AC10 — the bare-URL autolink pin (LD-054) still exists (referenced, not duplicated).

LD-093 adds two writer-stage guards (below the LD-059 set): the shipped ``write/``
package must never let the pre-implementation "empty / reserved / design-brief" prose
return to PROJECT.md / README.md / write/README.md (it drifted undetected through the
whole write ladder because no guard tied the prose to the package's real contents).
"""
import ast
import os
import re
import subprocess

import pytest

from guard_kit import REPO_ROOT as ROOT
from guard_kit import md_table_cells
from larkdocio.read.config import OutputConfig
import private_tree  # noqa: E402  (LD-685)

ROLES_DIR = ROOT / ".claude" / "roles"


# --- shared helpers --------------------------------------------------------

def _active_role_stems():
    """Active role docs = ``.claude/roles/*.md`` (non-recursive, so the parked
    ``archive/ui-designer.md`` is excluded by construction)."""
    return {p.stem for p in ROLES_DIR.glob("*.md")}


def _table_rows(text):
    """Yield stripped lines that look like Markdown table rows (start with '|')."""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|"):
            yield s


def _is_separator(cell):
    return bool(cell) and set(cell) <= set("-: ")


# =====================================================================
# AC1 — roles table <-> .claude/roles/ directory (both PROJECT.md + CLAUDE.md)
# =====================================================================

# In CLAUDE.md the roles table LINKS each doc: [dev.md](.claude/roles/dev.md).
# The regex only matches a leaf under .claude/roles/ (no '/' after it), so the
# parked ...roles/archive/ui-designer.md link never matches — archive excluded.
_CLAUDE_ROLE_LINK_RE = re.compile(r"\]\(\.claude/roles/([a-z][a-z-]*)\.md\)")


def _claude_md_listed_roles():
    stems = set()
    for row in _table_rows((ROOT / "CLAUDE.md").read_text(encoding="utf-8")):
        if ".claude/roles/" not in row:
            continue
        for m in _CLAUDE_ROLE_LINK_RE.finditer(row):
            stems.add(m.group(1))
    return stems


def _project_md_active_roles():
    """PROJECT.md's roles table uses NAME + STATUS cells (no doc links). Return the
    lower-cased names of the rows marked active (parked rows excluded). Scoped to
    the '### Roles' subsection so the skills table below it can't leak in."""
    lines = (ROOT / "PROJECT.md").read_text(encoding="utf-8").splitlines()
    active = set()
    in_section = False
    for line in lines:
        if line.startswith("### Roles"):
            in_section = True
            continue
        if in_section and line.startswith("###"):
            break
        if not in_section:
            continue
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = md_table_cells(s)
        if len(cells) < 2:
            continue
        name, status = cells[0], cells[1]
        if name.lower() == "role" or _is_separator(name):
            continue
        status_l = status.lower()
        if "parked" in status_l:
            continue
        if "active" in status_l:
            active.add(name.lower())
    return active


@private_tree.process
def test_ac1_claude_md_roles_table_matches_dir():
    listed = _claude_md_listed_roles()
    active = _active_role_stems()
    assert listed == active, (
        f"CLAUDE.md roles table lists {sorted(listed)} but the active role docs are "
        f"{sorted(active)} — a role doc was added/removed without updating CLAUDE.md."
    )


@private_tree.process
def test_ac1_project_md_roles_table_matches_dir():
    listed = _project_md_active_roles()
    active = _active_role_stems()
    assert listed == active, (
        f"PROJECT.md roles table lists active {sorted(listed)} but the active role "
        f"docs are {sorted(active)} — update PROJECT.md § Roles."
    )


# =====================================================================
# AC2 — CLAUDE.md prefix table <-> commit-msg hook ROLE_PREFIXES (derived)
# =====================================================================

def _hook_role_prefixes():
    """DERIVE the accepted prefix set from the hook's single ROLE_PREFIXES line —
    never re-hardcode it here (that is the whole point of the guard)."""
    hook = (ROOT / "scripts" / "githooks" / "commit-msg").read_text(encoding="utf-8")
    m = re.search(r"^ROLE_PREFIXES='([^']+)'", hook, re.M)
    assert m, "commit-msg hook: ROLE_PREFIXES='...' line not found (guard can't derive)."
    return set(m.group(1).split("|"))


_PREFIX_ROW_RE = re.compile(r"^\|\s*`\[([A-Za-z]+)\]`\s*\|")


def _claude_md_prefix_tags():
    tags = set()
    for row in _table_rows((ROOT / "CLAUDE.md").read_text(encoding="utf-8")):
        m = _PREFIX_ROW_RE.match(row)
        if m:
            tags.add(m.group(1))
    return tags


@private_tree.kit
def test_ac2_prefix_table_matches_hook():
    derived = _hook_role_prefixes()
    documented = _claude_md_prefix_tags()
    assert documented == derived, (
        f"CLAUDE.md prefix table lists {sorted(documented)} but the commit-msg hook "
        f"accepts {sorted(derived)} — the audit-trail table drifted from the hook."
    )


@private_tree.kit
def test_ac2_architect_prefix_present():
    # Explicit belt-and-braces per AC2: the [Architect] seat prefix is in both.
    assert "Architect" in _hook_role_prefixes()
    assert "Architect" in _claude_md_prefix_tags()


# =====================================================================
# AC3 — dev-extras: PROJECT.md <-> pyproject.toml [optional-dependencies].dev
# =====================================================================

def _pyproject_dev_extras():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r"^dev\s*=\s*\[(.*?)\]", text, re.S | re.M)
    assert m, "pyproject.toml: [project.optional-dependencies].dev list not found."
    names = set()
    for line in m.group(1).splitlines():
        qm = re.search(r'"([^"]+)"', line)
        if not qm:
            continue
        # Strip any version specifier / marker → the bare distribution name.
        name = re.split(r"[<>=!~;\s]", qm.group(1), maxsplit=1)[0]
        if name:
            names.add(name)
    return names


def _project_md_dev_extras():
    """Extract the dev-extra package names from PROJECT.md's 'Dev extras:' clause
    (backticked tokens, up to the next markdown bullet). Path-like tokens such as
    ``scripts/mutation-check.sh`` are excluded — only distribution names.

    **The clause boundary is load-bearing (LD-504).** Every backticked token inside
    it counts as *documented*, so anything written there that is not a `dev` extra
    false-fails the guard below. That is a feature, not a trap to work around: it is
    what makes the clause a declaration rather than prose. LD-504 documents the
    separate `mutation` extra in its **own bullet** immediately after — outside this
    clause, and held against pyproject by
    :func:`test_ld504_mutation_extra_project_md_matches_pyproject` — so this guard
    keeps exactly the strength it had, in both directions, and was not widened."""
    text = (ROOT / "PROJECT.md").read_text(encoding="utf-8")
    i = text.index("Dev extras:")
    rest = text[i:]
    end = rest.find("\n- ", 1)          # first bullet after the clause ends it
    clause = rest if end == -1 else rest[:end]
    names = set()
    for tok in re.findall(r"`([^`]+)`", clause):
        if "/" in tok or " " in tok:    # drop paths / prose, keep dist names
            continue
        names.add(tok)
    return names


@private_tree.process
def test_ac3_dev_extras_project_md_matches_pyproject():
    documented = _project_md_dev_extras()
    declared = _pyproject_dev_extras()
    assert documented == declared, (
        f"PROJECT.md documents dev extras {sorted(documented)} but pyproject declares "
        f"{sorted(declared)} — the two drifted. NOTE (LD-504): `mutmut` is NOT a dev extra "
        "any more; it lives in the separate `mutation` extra, documented in PROJECT.md's own "
        "bullet just after the 'Dev extras:' clause."
    )


# --- LD-504: the SAME drift check for the `mutation` extra -------------------
# The dev-extras guard above is a set equality over one clause, and LD-504 did not
# touch it. The `mutation` extra needs the same protection or it becomes the one
# extra whose documentation may rot — so it gets its own two-directional check.

def _pyproject_mutation_extra():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r"^mutation\s*=\s*\[(.*?)\]", text, re.S | re.M)
    assert m, "pyproject.toml: [project.optional-dependencies].mutation list not found."
    names = set()
    for line in m.group(1).splitlines():
        qm = re.search(r'"([^"]+)"', line)
        if not qm:
            continue
        name = re.split(r"[<>=!~;\s]", qm.group(1), maxsplit=1)[0]
        if name:
            names.add(name)
    return names


@private_tree.process
def test_ld504_mutation_extra_project_md_matches_pyproject():
    """PROJECT.md's `mutation`-extra bullet ↔ pyproject's `mutation` list, both ways,
    plus the reason and the citation that keep the separation from being undone by
    someone who reads it as tidiness."""
    text = (ROOT / "PROJECT.md").read_text(encoding="utf-8")
    i = text.index("**Mutation extra**")
    rest = text[i:]
    end = rest.find("\n- ", 1)
    clause = rest if end == -1 else rest[:end]

    # The DECLARATION is the bullet's first line (same shape as the 'Dev extras:'
    # clause: backticked distribution names, paths and prose dropped). The lines
    # after it carry the reason, and may name other packages — `setproctitle`,
    # `pytest-xdist` — without that reading as a declaration.
    declaration = clause.splitlines()[0]
    documented = {tok for tok in re.findall(r"`([^`]+)`", declaration)
                  if "/" not in tok and " " not in tok and "." not in tok}
    declared = _pyproject_mutation_extra()
    assert documented == declared, (
        f"PROJECT.md's mutation-extra bullet declares {sorted(documented)} but pyproject "
        f"declares {sorted(declared)} — the two drifted."
    )
    # It must say where the meter runs, why the separation exists, and where to read it.
    assert "own virtualenv" in clause, \
        "the bullet must say scripts/mutation-check.sh runs it from its OWN virtualenv"
    for word in ("setproctitle", "pytest-xdist", "launchservicesd"):
        assert word in clause, f"the bullet dropped the mechanism word `{word}`"
    assert "dev/2026-08-18-verify-beachball-diagnosis.md" in clause, \
        "the bullet must cite the diagnosis"


# =====================================================================
# AC4 — every OutputConfig field is documented in TOOLS.md *and* in the
#       PACKAGED guide, which is the copy a wheel-only reader can open
# =====================================================================

def test_ac4_config_fields_documented_in_tools_md():
    fields = set(OutputConfig().to_dict().keys())
    tools = (ROOT / "TOOLS.md").read_text(encoding="utf-8")
    missing = sorted(f for f in fields if f not in tools)
    assert not missing, (
        f"OutputConfig fields {missing} are not documented in TOOLS.md — a config key "
        f"can't ship undocumented (analogue of test_blocks_md_matrix)."
    )


def test_ac4_config_fields_documented_in_the_PACKAGED_guide_too():
    """The guard follows the schema to its new home. TOOLS.md is not in the wheel, so a key
    documented only there is documented for contributors and nobody else; the schema is now a
    generated region the packaged guide carries as well, and this is the leg that keeps a new
    field from shipping unreachable. Byte-identity of the two regions to the projection is
    asserted in ``tests/test_download_output_docs.py``."""
    from larkdocio.guide import guide

    text = guide(full=True)
    missing = sorted(f for f in OutputConfig().to_dict() if f"`{f}`" not in text)
    assert not missing, (
        f"OutputConfig fields {missing} are absent from the packaged guide — a wheel-only "
        f"reader cannot open TOOLS.md, so a key documented only there is unreachable."
    )


# =====================================================================
# AC5 — no forge-specific 'PR opened' string under .claude/templates/
# =====================================================================

@private_tree.process
def test_ac5_templates_are_forge_agnostic():
    tdir = ROOT / ".claude" / "templates"
    offenders = [
        p.relative_to(ROOT).as_posix()
        for p in sorted(tdir.rglob("*"))
        if p.is_file() and "PR opened" in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert not offenders, (
        f"Forge-specific 'PR opened' found in templates {offenders} — the kit is "
        f"forge-agnostic (pure-git finish-pr.sh; there is no PR object)."
    )


# =====================================================================
# AC6 — retired handoffs carry a RETIRED / superseded banner
# =====================================================================
#
# (LD-627, 2026-09-03) THIS GUARD USED TO ENFORCE CLOSE TO THE OPPOSITE OF ITS
# OWN DOCSTRING, in two independent ways, and the pair was worse than either
# half. Both are stated here because both are easy to reintroduce:
#
#   A. It globbed ``*.md``, which includes ``dev/handoffs/README.md`` — the
#      CONVENTION doc, not a handoff (added by LD-548). ``'R'`` sorts after
#      ``'2'``, so ``sorted(...)[-1]`` was ALWAYS the README, the real newest
#      handoff was always in ``files[:-1]``, and the guard demanded a
#      retirement banner on the CURRENT handoff. It went red the moment a
#      correctly-unbannered current handoff landed. The selector below matches
#      the dated-name shape instead, which is what makes the "lexical ==
#      chronological" comment TRUE of the set rather than only of part of it.
#
#   B. It matched a whole-file lowercased substring, so prose about ANOTHER
#      file's retirement satisfied it. Not hypothetical: it is why a genuinely
#      stale handoff went unnoticed for two days —
#      ``2026-09-01-cluster-run-pause-handoff.md`` still said "This is the
#      CURRENT handoff" and passed, because its head contained the sentence
#      "``2026-08-31-v1.42.0-cut-handoff.md`` is stamped SUPERSEDED at its
#      head", a statement about a DIFFERENT file. The word was present; the
#      fact was not. Recognition is therefore STRUCTURAL (a verdict word in
#      banner POSITION) and bounded to the head of the file.
#
# And a third leg was missing entirely: nothing asserted that the newest dated
# handoff is NOT retired. Without it, A+B can be satisfied by a directory in
# which everything is stamped and nothing is current — the docstring's failure
# mode, reached with the guard green.
#
# All three legs are exercised on tmp_path fixtures as well as on the real
# directory, so no assertion here is one that has never failed on real input.

#: A handoff filename is ``YYYY-MM-DD-<kind>.md`` — ``dev/handoffs/README.md``
#: § Filename: *"the date first, so an ``ls`` sorts chronologically"*, and
#: *"the lexical-date filename IS the contract"*. Anything else in the
#: directory (today: only ``README.md``, the convention doc) is EXCLUDED, not
#: changed — see defect A above.
_DATED_HANDOFF_NAME = re.compile(r"^20\d{2}-\d{2}-\d{2}-.+\.md$")

#: The verdict words a retirement banner may OPEN with. The closed set is
#: ``process/doctrine/staleness.md`` § "A verdict word, from the closed set —
#: SPENT · SLATE LANDED · RETIRED · SUPERSEDED · DELIVERED — as its opening
#: words", plus CLOSED, which is this directory's own Rule 2 strike for a
#: standing handoff whose arc has ended (``dev/handoffs/README.md``: *"It is
#: CLOSED, not deleted, when the arc ends"*; the single in-corpus user is
#: ``2026-08-18-standing-handoff.md``).
_RETIREMENT_VERDICTS = (
    "retired",
    "superseded",
    "closed",
    "spent",
    "slate landed",
    "delivered",
)

_VERDICT_ALTERNATION = "|".join(_RETIREMENT_VERDICTS)

#: Banner form 1 — the house convention: a blockquote whose BOLD opening words
#: are the verdict, e.g. ``> **SUPERSEDED 2026-09-03 — the current handoff is …``.
#: 21 of the 21 retired dated handoffs on 2026-09-03 use this form.
_BANNER_BLOCKQUOTE = re.compile(
    rf"^\s*>\s*\*\*\s*({_VERDICT_ALTERNATION})\b", re.IGNORECASE
)

#: Banner form 2 — accepted because the corpus is EVIDENCE, not something to
#: normalise (LD-627 out-of-scope): three older files also carry the verdict as
#: the closing words of their ``#`` title line, e.g. ``# Architect seat #4 →
#: successor — handoff (2026-07-30, ~15:00 SGT) — RETIRED``. Either form counts;
#: no existing handoff was retro-edited to suit this guard.
_BANNER_TITLE_LINE = re.compile(
    rf"^#\s.*\b({_VERDICT_ALTERNATION})\s*$", re.IGNORECASE
)

#: How far into a file a banner still counts as being "at the head".
#: **The per-line split is NOT written here** — it is derived by
#: (the census that derived this bound was retired 2026-09-18 with the dev/ handoff corpus),
#: which reads the live corpus on every run. LD-627 stated it as "line 1 in 8
#: files, line 3 in 13"; LD-627's own QA re-measured 11 and 10 the next day, so
#: the comment was wrong about its own measurement while the bound stayed
#: right — exactly the defect class LD-628 came for
#: (`process/doctrine/staleness.md` § C).
#: **THE MORE USEFUL FACT, and the one that is stable: this bound is INERT.**
#: What rejects the stale 2026-09-01 handoff is FORM, not position — its only
#: keyword occurrence sat at line 9, comfortably inside this window (defect B) —
#: and LD-627's QA re-ran these legs at 3, 8, 12 and 40 with ``6 passed`` at
#: every value. 12 is headroom for a longer preamble, and no verdict word in a
#: file's body has ever reached it.
_BANNER_HEAD_LINES = 12


def _dated_handoffs(hdir):
    """The handoff set: dated files only, sorted (lexical == chronological)."""
    return sorted(p for p in hdir.glob("*.md") if _DATED_HANDOFF_NAME.match(p.name))


def _retirement_banner_line(path):
    """1-based line number of ``path``'s retirement banner, or ``None``.

    Structural: a verdict word in banner POSITION (bold blockquote opener, or
    the tail of the ``#`` title line) within the first ``_BANNER_HEAD_LINES``
    lines. Prose mentioning some other file's retirement does not count.
    """
    head = path.read_text(encoding="utf-8").splitlines()[:_BANNER_HEAD_LINES]
    for lineno, line in enumerate(head, start=1):
        if _BANNER_BLOCKQUOTE.match(line) or _BANNER_TITLE_LINE.match(line):
            return lineno
    return None


def _check_older_handoffs_are_retired(hdir):
    """AC1+AC2 leg, parameterised so the fixtures run the shipped code path."""
    files = _dated_handoffs(hdir)
    assert files, f"no dated handoff files (YYYY-MM-DD-*.md) found in {hdir}."
    newest = files[-1]
    for p in files[:-1]:
        assert _retirement_banner_line(p) is not None, (
            f"{p.name} is older than {newest.name} but carries no RETIRED/superseded "
            f"banner at its head — a stale handoff can be mistaken for the current "
            f"one. The banner is a bold blockquote opening with a verdict word "
            f"({', '.join(_RETIREMENT_VERDICTS)}) in the first "
            f"{_BANNER_HEAD_LINES} lines, or that word closing the '#' title line. "
            f"A sentence about ANOTHER file's retirement does not discharge it."
        )


def _check_newest_handoff_is_current(hdir):
    """AC3 leg — the one that enforces the docstring's actual intent."""
    files = _dated_handoffs(hdir)
    assert files, f"no dated handoff files (YYYY-MM-DD-*.md) found in {hdir}."
    newest = files[-1]
    lineno = _retirement_banner_line(newest)
    assert lineno is None, (
        f"{newest.name} is the NEWEST handoff — the plan-of-record — but carries a "
        f"retirement banner at line {lineno}. Either it is not actually retired (do "
        f"not banner the current handoff to make a guard green: "
        f"process/doctrine/retention.md) or the successor that retired it was never "
        f"written, and this directory now claims to have no current handoff at all."
    )


# RETIRED 2026-09-18 (pre-export evidence-tree retirement) — its corpus, dev/handoffs/*.md,
# went with the dev/ evidence tree; the synthetic tmp_path bite-proofs below still exercise
# _check_older_handoffs_are_retired and _check_newest_handoff_is_current, so the MECHANISM survives.


#


#


# RETIRED 2026-09-18 (pre-export evidence-tree retirement) — VACUITY: with the dated-handoff
# corpus gone this reduced to `set() == set()`.


def test_ac6_banner_is_not_satisfied_by_prose_about_another_file(tmp_path):
    """AC2's watched red, kept as a permanent regression (LD-627 defect B).

    The head below is the VERBATIM head of
    ``2026-09-01-cluster-run-pause-handoff.md`` as it stood at the time
    — genuinely stale, still asserting it was current, and green
    under the old whole-file substring check because of the line-9 sentence
    about ``2026-08-31-v1.42.0-cut-handoff.md``.
    """
    hdir = tmp_path / "handoffs"
    hdir.mkdir()
    stale = hdir / "2026-09-01-cluster-run-pause-handoff.md"
    stale.write_text(
        "# Handoff — the NIGHT RUN is live; 14 issues landed before it started, "
        "no cut (written 2026-09-01, kept current DURING the run)\n"
        "\n"
        "> **⚠ THIS FILE IS AMENDED AS THE RUN PROCEEDS**, at the maintainer's request\n"
        "> (*\"please keep that handoff updated throughout\"*).\n"
        "\n"
        "> **This is the CURRENT handoff** (newest file in `handoffs/` = current). "
        "Predecessor\n"
        "> [`2026-08-31-v1.42.0-cut-handoff.md`](2026-08-31-v1.42.0-cut-handoff.md) "
        "is stamped SUPERSEDED at\n"
        "> its head **in this same commit**.\n",
        encoding="utf-8",
    )
    (hdir / "2026-09-03-night-run-refactor-mandate.md").write_text(
        "# Night run — the refactor mandate\n\n> **The freshest thing in this file** …\n",
        encoding="utf-8",
    )

    # The word is present in the head — the old check passed on exactly this.
    assert "superseded" in stale.read_text(encoding="utf-8").lower()
    assert _retirement_banner_line(stale) is None, (
        "a sentence about another file's retirement must NOT read as a banner."
    )
    with pytest.raises(AssertionError, match="carries no RETIRED/superseded banner"):
        _check_older_handoffs_are_retired(hdir)


def test_ac6_banner_accepts_the_title_line_form(tmp_path):
    """AC2 — the three older files that carry the verdict in the ``#`` title line."""
    hdir = tmp_path / "handoffs"
    hdir.mkdir()
    (hdir / "2026-07-30-architect.md").write_text(
        "# Architect seat #4 → successor — handoff (2026-07-30, ~15:00 SGT) — RETIRED\n"
        "\n"
        "Body with no blockquote banner at all.\n",
        encoding="utf-8",
    )
    (hdir / "2026-07-31-architect.md").write_text(
        "# Architect seat #5 — handoff (2026-07-31)\n\nCurrent.\n", encoding="utf-8"
    )
    _check_older_handoffs_are_retired(hdir)
    _check_newest_handoff_is_current(hdir)


def test_ac6_newest_leg_rejects_a_fully_stamped_directory(tmp_path):
    """AC3's watched red — everything stamped, nothing current."""
    hdir = tmp_path / "handoffs"
    hdir.mkdir()
    (hdir / "2026-09-01-older.md").write_text(
        "# Older\n\n> **SUPERSEDED 2026-09-03** — see the newer one.\n", encoding="utf-8"
    )
    (hdir / "2026-09-03-newest.md").write_text(
        "# Newest\n\n> **RETIRED 2026-09-04** — banner-ed to make a guard green.\n",
        encoding="utf-8",
    )
    # AC1+AC2 are happy with this directory; only AC3 catches it.
    _check_older_handoffs_are_retired(hdir)
    with pytest.raises(AssertionError, match="is the NEWEST handoff"):
        _check_newest_handoff_is_current(hdir)


# =====================================================================
# AC7 — every dev doc AND every dev subdirectory is indexed in dev/README.md (in the dev repo)
# =====================================================================
#
# THE RULE THIS GUARD ENFORCES (LD-361 widened it; state it plainly so the next
# person adding something under dev/ knows what will be asked of them):
#
#   1. FILE granularity, for prose docs only — every ``dev/*.md`` (except
#      README.md) and every ``dev/handoffs/*.md`` must be linked as ``](<name>)``.
#   2. DIRECTORY granularity, for every immediate subdirectory of ``dev/`` — the
#      README must carry at least one markdown link POINTING INTO it, i.e. a
#      ``](<dir>/…)`` target (the directory itself, ``](dir/)``, satisfies it).
#
# Why directory-level and not file-level for subdirectories: these are retained
# EVIDENCE trees (probe scripts + hundreds of raw JSON captures). The audit's
# intent (dev/2026-08-09-code-health-audit.md § 4 #2) is *membership* — the next
# auditor must be able to tell a deliberate record from a leftover — not an
# exhaustive per-capture bibliography. Demanding every file be linked would make
# the index unmaintainable and would push people toward deleting evidence, which
# is exactly the failure mode "park beats delete" exists to prevent.
#
# So: add a new directory under dev/, add one line to dev/README.md (in the dev repo) linking into
# it. That is the whole contract.
#
# (LD-520, 2026-08-19; RETIRED 2026-09-18 with the dev/ evidence tree) THE THIRD LEG,
# walks README -> disk instead of disk -> README, catching the opposite defect: an
# indexed-and-deleted file — exactly the shape a retirement sweep produces.
#
# (LD-522, 2026-08-19) THE FOURTH AND FIFTH LEGS add the one narrow class this
# comment's own reasoning always implied but never had to name: a document may leave
# the FIRST index (README) only by landing, losslessly, in the SECOND
# (dev/RETIRED.md) — never by disappearing from both. See
# process/doctrine/retention.md for the reason (unchanged) and the five conditions
# that gate it (new).

def _dev_readme_missing_links():
    """Return (missing_docs, missing_dirs) for dev/README.md (in the dev repo) — the two granularities."""
    dev = ROOT / "dev"
    readme = (dev / "README.md").read_text(encoding="utf-8")

    docs = []
    for p in sorted(dev.glob("*.md")):
        if p.name != "README.md":
            docs.append(p.relative_to(dev).as_posix())
    for p in sorted((dev / "handoffs").glob("*.md")):
        docs.append(p.relative_to(dev).as_posix())
    missing_docs = [d for d in docs if f"]({d})" not in readme]

    missing_dirs = [
        p.name
        for p in sorted(dev.iterdir())
        if p.is_dir() and not p.name.startswith((".", "__"))
        and f"]({p.name}/" not in readme
    ]
    return missing_docs, missing_dirs


# RETIRED 2026-09-18 (pre-export evidence-tree retirement) — dev/README.md (in the dev repo), the evidence tree's
# index, went with the tree it indexed.


#


def _dev_readme_link_targets():
    """Extract every distinct ``](target)`` in dev/README.md (in the dev repo) and split it into
    (repo_relative, excluded) per ``_NON_REPO_RELATIVE_LINK_PREFIXES`` above."""
    readme = (ROOT / "dev" / "README.md").read_text(encoding="utf-8")
    targets = sorted(set(re.findall(r"\]\(([^)]+)\)", readme)))
    excluded = [t for t in targets if t.startswith(_NON_REPO_RELATIVE_LINK_PREFIXES)]
    repo_relative = [t for t in targets if t not in excluded]
    return repo_relative, excluded


#


# =====================================================================
# AC7 (LD-522) — the ledger legs: dev/RETIRED.md rows are HONEST and WELL-FORMED
# =====================================================================
#
# The retention doctrine (process/doctrine/retention.md § A.4) narrows park-beats-delete
# for exactly one class: a SPENT, unreferenced prose document, retired under a seven-field
# ledger row. These two legs are the guard TRANSFORMATION AC4 requires: the three legs
# above stay byte-for-byte — they still police everything still on disk — and these two
# move the assertion to the new truth: every dev/ artifact sits in exactly one of TWO
# indexes (dev/README.md (in the dev repo), live; dev/RETIRED.md, retired), and NEITHER index may carry a
# dead or malformed entry.
#
# NO GIT IS INVOKED — tests/test_no_test_reads_live_git.py forbids it suite-wide. Both legs
# are pure tree-content parse. A ledger row's FETCH-BACK is verified once, by a human, at
# retirement time (process/doctrine/retention.md § A.5) — these legs check that a row is
# SHAPED so that verification was possible and honest, never that the command was re-run.

RETIRED = ROOT / "dev" / "RETIRED.md"

#: The one documented row shape (LD-522) that is NOT a single file: a directory slice
#: added in one unmodified commit, whose ``blob`` is a note rather than a hash and whose
#: fetch-back is parametrized over ``<name>`` rather than a literal path. Recognised by
#: the "(N of M files)" suffix its own ``path`` carries — dev/RETIRED.md's own header names
#: this row and why it is shaped this way ("One row is a documented exception…").
_AGGREGATE_PATH_RE = re.compile(r"^(?P<dir>.+/) \((?P<n>\d+) of (?P<m>\d+) files\)$")

#: One ledger row is three content lines: the bullet (``path``), the field line
#: (``commit``/``blob``/``bytes``/``issue``), the "What it was" line, and the "Fetch back"
#: line — exactly the shape every row in dev/RETIRED.md already carries.
_ROW_RE = re.compile(
    r"^- \*\*`(?P<path>.+?)`\*\*$\n"
    r"^\s*· \*\*commit\*\* `(?P<commit>[^`]*)` · \*\*blob\*\* `(?P<blob>[^`]*)` · "
    r"\*\*bytes\*\* `(?P<bytes>[0-9,]+)` · \*\*retired by\*\* (?P<issue>LD-\d+), [0-9-]+$\n"
    r"^\s*· \*What it was:\* (?P<what>.+)$\n"
    r"^\s*· \*\*Fetch back:\*\* `(?P<fetchback>.+?)`$",
    re.MULTILINE,
)


def _dev_retired_rows():
    """Parse every row under dev/RETIRED.md's ``## Retired`` heading. Pure text parse — no
    git invocation of any kind, per the suite-wide prohibition."""
    if not RETIRED.exists():
        return []
    section = RETIRED.read_text(encoding="utf-8").split("## Retired", 1)[1]
    return [m.groupdict() for m in _ROW_RE.finditer(section)]


# RETIRED 2026-09-18 (pre-export evidence-tree retirement) — dev/RETIRED.md, the recoverability
# ledger, went with the tree; its own header states that a squash of develop invalidates every
# row at once, and a squash is what publishes this repository.


#


# =====================================================================
# STALENESS DOCTRINE (LD-523) — G2, the closure-pairing guard
# =====================================================================
#
# process/doctrine/staleness.md § B.3: "A pack is spent when a report names it."
# Domain: every markdown file under dev/, EXCLUDING dev/launch/*pack*.md (the packs
# themselves), dev/README.md (in the dev repo), and dev/handoffs/** — a HANDOFF citing a pack points
# at work IN FLIGHT (dev/handoffs/2026-08-18-standing-handoff.md legitimately cites
# the still-live wave-1 Lane B pack); a REPORT citing a pack is proof the pack ran.
# No maintained allowlist — the pairing is derived from the citation graph, so a new
# pack+report pair enrols itself.
#
# AMENDMENT (LD-523 fix round, 2026-08-20) — the ORIGINAL reason above is preserved,
# not struck (process/doctrine/supersession.md § A.1); only the domain's SHAPE is
# transformed, because the directory-only exclusion turned out narrower than its own
# reason. `dev/refactor-audit-2026-08/RECONCILIATION.md` (the Architect's refactor
# plan of record) reddened this guard for citing the wave-1 Lane B pack while it was
# genuinely still LIVE — but RECONCILIATION.md is not a report, it is a PLAN: its own
# prose says the pack is "launchable the moment wave 0 CLOSES", i.e. it cites
# SCHEDULED / in-flight work, functionally identical to what a handoff citation does.
# The bug was that the domain excluded IN-FLIGHT-describing documents only by
# directory (dev/handoffs/**), so it fired on any OTHER document that describes
# in-flight work too. The fix generalizes the SAME reason from a location (one
# directory) to a content property any document can carry: a citation sitting next
# to language that itself concedes the pack is scheduled / not yet run is not read as
# a report, by the same logic a handoff citation already isn't — still derived from
# the citation graph (a new pack+report pair enrols itself; a new pack+plan pair
# exempts itself the same way), never a per-path allowlist.
#
# For every dev/launch/*-pack.md path cited from an in-domain file, the cited pack's
# own top-of-file banner must carry a closure verdict word. The check is STRUCTURAL —
# the banner's own FIRST blockquote line must OPEN with the verdict, never a bare
# substring search of the whole pack, because § B.2's own lesson (a bare-substring
# guard produces false GREENS over a heterogeneous corpus) has an exact mirror here
# that produces a false RED: dev/launch/2026-08-19-wave1-laneB-pack.md's own template
# line reads "Stamp SPENT with the run-report name when closed", so a naive "SPENT"
# search anywhere in the pack's text would wrongly call a genuinely-still-live pack
# closed.
#
# A cited path that does not resolve on disk is NOT an unstamped pack — it is a
# retired document with its own dev/RETIRED.md ledger row (LD-521 deleted eight
# launch packs under DELETE-WITH-LEDGER); resolving against files on disk, not
# against the citation, is what keeps a retirement from reddening this guard.

_G2_PACK_CITATION_RE = re.compile(r"dev/launch/[A-Za-z0-9._-]+-pack\.md")
_G2_PACK_FILENAME_RE = re.compile(r"^dev/launch/.*pack.*\.md$")
_G2_VERDICT_WORDS = ("SPENT", "SLATE LANDED", "RETIRED", "SUPERSEDED", "DELIVERED")
_G2_BANNER_VERDICT_RE = re.compile(
    r"^>\s*(#+\s*)?(\*{1,2}\s*)?(✅\s*)?(STATUS:\s*)?(\*{1,2}\s*)?("
    + "|".join(_G2_VERDICT_WORDS) + r")\b"
)

# In-flight markers: language that ITSELF concedes, next to a pack citation, that the
# cited pack is scheduled / not yet run — the identical non-evidence a handoff
# citation already carries by virtue of its directory. This is the content-derived
# generalization of that same reason (see the AMENDMENT comment above): it is a fixed
# vocabulary check in the exact style already used for _G2_VERDICT_WORDS above, not a
# path allowlist, so it self-enrols for any future plan-shaped document without a
# maintained list of paths.
_G2_INFLIGHT_MARKERS_RE = re.compile(
    r"(not yet run|launchable|in[- ]flight|scheduled|still\s+live|status:\s*live)",
    re.IGNORECASE,
)
_G2_INFLIGHT_WINDOW = 160  # chars of context scanned around a citation, each side


def _g2_cites_pack_only_as_inflight(path):
    """True iff `path` cites at least one dev/launch/*-pack.md path, and EVERY such
    citation sits within _G2_INFLIGHT_WINDOW chars of in-flight/scheduled language.
    A file where even one citation makes no such concession stays in-domain, so a
    genuine offense sitting alongside an innocent forward reference is still caught."""
    text = path.read_text(encoding="utf-8")
    matches = list(_G2_PACK_CITATION_RE.finditer(text))
    if not matches:
        return False
    for m in matches:
        window = text[
            max(0, m.start() - _G2_INFLIGHT_WINDOW) : m.end() + _G2_INFLIGHT_WINDOW
        ]
        if not _G2_INFLIGHT_MARKERS_RE.search(window):
            return False
    return True


def _g2_domain_files():
    """Every markdown under dev/ that is not itself a pack, not dev/README.md (in the dev repo), not
    under dev/handoffs/ (the ORIGINAL, preserved exclusion — see the module comment
    above), and not a document whose own text concedes, beside every pack citation it
    carries, that the cited pack is scheduled / in flight (the AMENDMENT above)."""
    dev = ROOT / "dev"
    for p in sorted(dev.rglob("*.md")):
        rel = p.relative_to(ROOT).as_posix()
        if rel == "dev/README.md":
            continue
        if rel.startswith("dev/handoffs/"):
            continue
        if _G2_PACK_FILENAME_RE.match(rel):
            continue
        if _g2_cites_pack_only_as_inflight(p):
            continue
        yield p


def _g2_pack_has_verdict_banner(pack_path):
    """The pack's own first blockquote line must OPEN with a verdict word — a
    structured check, never a substring search (module comment above)."""
    for line in pack_path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "":
            continue
        if line.startswith(">"):
            return bool(_G2_BANNER_VERDICT_RE.match(line))
        if line.startswith("#"):
            continue  # the title line
        return False  # first substantive line has no banner at all
    return False


def _g2_unstamped_pack_citations():
    offenders = []
    for p in _g2_domain_files():
        text = p.read_text(encoding="utf-8")
        for m in _G2_PACK_CITATION_RE.finditer(text):
            pack_rel = m.group(0)
            pack_path = ROOT / pack_rel
            if not pack_path.exists():
                continue  # retired — see dev/RETIRED.md, not an unstamped pack
            if not _g2_pack_has_verdict_banner(pack_path):
                offenders.append((p.relative_to(ROOT).as_posix(), pack_rel))
    return sorted(set(offenders))


# RETIRED 2026-09-18 (pre-export evidence-tree retirement) — VACUITY, not cleanup. With every
# dev/launch/*-pack.md gone this guard's own `if not pack_path.exists(): continue` turned each
# citation into a silent skip: 0 citations, 0 resolving packs, structurally unable to fire.
# A guard that cannot fail is worse than a deleted one because it still reports coverage.


# =====================================================================
# AC8 — moved whole to its own module (LD-704): its subject is the private planning record
# against the board, which the public export does not carry, so the module that holds it is
# withheld from the export (`D-121` (8)).
# =====================================================================

# =====================================================================
# AC9 — qa.md references the golden regression test
# =====================================================================

@private_tree.process
def test_ac9_qa_md_references_golden_test():
    qa = (ROOT / ".claude" / "roles" / "qa.md").read_text(encoding="utf-8")
    assert "test_golden.py" in qa or "test_blocks_md_matrix.py" in qa, (
        "qa.md no longer references tests/test_golden.py (or test_blocks_md_matrix.py) "
        "in its regression section — the golden guard reference drifted."
    )


# =====================================================================
# AC10 — bare-URL autolink pin (LD-054): reference, do not duplicate
# =====================================================================

def test_ac10_bare_url_autolink_pin_exists():
    """AC10 is already covered behaviorally by ``tests/test_autolink_urls.py`` (LD-054):
    a bare URL inside a type-2 text block renders as a Markdown link. Per the issue we
    REFERENCE that suite as the drift guard rather than duplicate its assertions; this
    guard just pins its continued existence + type-2 coverage so the reference can't rot."""
    pin = ROOT / "tests" / "test_autolink_urls.py"
    assert pin.is_file(), "AC10 pin: tests/test_autolink_urls.py (LD-054) is missing."
    body = pin.read_text(encoding="utf-8")
    assert '"block_type": 2' in body, "AC10 pin: type-2 text-block coverage missing."
    assert "test_bare_url_in_plain_text_becomes_link" in body, (
        "AC10 pin: the canonical bare-URL-in-plain-text test is gone."
    )


# =====================================================================
# LD-093 — writer-stage drift guards: shipped write/ ⇒ no pre-impl prose
# =====================================================================
#
# The write/ package has shipped (v1.6.0..v1.9.0): ``write/apply.py`` exists and
# ``write/__init__.__all__`` exports a real engine surface. The stale "write/ ships
# empty / reserved, next" prose (PROJECT.md, README.md) and the "empty on purpose /
# design brief" framing (write/README.md) drifted UNDETECTED through the whole write
# ladder because no guard tied the writer-stage prose to the package's real contents.
# These two guards close that gap (LD-089 fixed the root docs, LD-090 the writer
# README; LD-093 pins them). Cheap, offline, deterministic file-parse tests.

WRITE_PKG = ROOT / "src" / "larkdocio" / "write"

# Guard (a) — PROJECT.md + README.md: forbidden pre-implementation writer-stage
# phrases (case-insensitive). Scoped to a WRITER context (see ``_writer_context_hits``)
# so an unrelated generic use elsewhere can't false-trip the guard.
_WRITER_STAGE_FORBIDDEN_ROOT = (
    "ships empty",
    "reserved but not yet built",
    "empty package",
)

# Guard (b) — the WRITER'S OWN PROSE, in both places it is written: write/README.md
# and the ``larkdocio.write`` package docstring (``help(larkdocio.write)``). Forbidden
# design-brief / pre-implementation framing. Both surfaces ARE writer context end to
# end, so a plain case-insensitive substring scan is enough (no proximity needed).
# Includes the audit's "lands in a later … session".
#
# LD-649 widened this in BOTH directions at once, because scoping it to the README is
# what let the identical defect live for the whole write era in the docstring next door:
#   * the SCAN now covers ``write/__init__.py``'s module docstring as well as the README
#     (see ``test_ld649_guard_b_extends_to_the_write_package_docstring``); and
#   * the PHRASE LIST gains "is still to come" — the form the drift actually took there
#     ("the binding write round-trip gate is still to come" while 21 live gate families
#     shipped). Widening the scan without the phrase would have enrolled the file behind
#     a list that could not see its defect: a guard green by construction.
# Phrases are only ever ADDED here; none has been removed (transform, never delete).
_WRITER_README_FORBIDDEN = (
    "empty on purpose",
    "No writer code lives here yet",
    "(design brief)",
    "lands in a later, separate session",
    "is still to come",
)


def _norm_ws(text):
    """Collapse every run of whitespace (incl. newlines) to a single space, so a
    forbidden phrase that a Markdown line-wrap split across two lines is still caught."""
    return re.sub(r"\s+", " ", text)


def _forbidden_hits(text, phrases):
    """Case-insensitive, whitespace-normalized substring scan → the (display-form)
    phrases present in ``text`` (a line-wrapped occurrence still matches)."""
    low = _norm_ws(text).lower()
    return sorted(p for p in phrases if _norm_ws(p).lower() in low)


def _writer_context_hits(text, phrases, window=80):
    """Like ``_forbidden_hits`` but a phrase only counts when ``write`` appears within
    ``window`` chars either side of an occurrence — so the guard fires on the
    *writer-stage* claim and not on some unrelated generic use of e.g. 'empty package'
    elsewhere in the file (AC1's writer-proximity scoping)."""
    low = _norm_ws(text).lower()
    hits = []
    for phrase in phrases:
        p = _norm_ws(phrase).lower()
        start = 0
        while True:
            idx = low.find(p, start)
            if idx == -1:
                break
            ctx = low[max(0, idx - window): idx + len(p) + window]
            if "write" in ctx:
                hits.append(phrase)
                break
            start = idx + len(p)
    return sorted(set(hits))


def _write_all_exports():
    """Parse ``write/__init__.__all__`` from source via ``ast`` (no import → no SDK
    dependency at collection time). Returns the export-name list (``[]`` if absent)."""
    src = (WRITE_PKG / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            value = ast.literal_eval(node.value)
            return list(value)
    return []


@private_tree.process
def test_ld093_guard_a_root_docs_no_writer_pre_impl_prose():
    """Guard (a): ``write/apply.py`` exists ⇒ PROJECT.md + README.md carry NONE of the
    pre-implementation writer-stage phrases in a writer context. Pins LD-089."""
    assert (WRITE_PKG / "apply.py").is_file(), (
        "guard precondition: src/larkdocio/write/apply.py must exist — the writer "
        "apply-engine has shipped (v1.6.0..v1.9.0); if this file is gone the guard's "
        "premise changed and the guard needs revisiting."
    )
    for doc in ("PROJECT.md", "README.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        hits = _writer_context_hits(text, _WRITER_STAGE_FORBIDDEN_ROOT)
        assert not hits, (
            f"{doc} carries pre-implementation writer-stage prose {hits} in a writer "
            f"context while src/larkdocio/write/apply.py ships — the writeback engine is "
            f"BUILT (LD-089 fixed this). Remove the stale 'ships empty / reserved / empty "
            f"package' framing; do not let the pre-W-ladder language return."
        )


def test_ld093_guard_b_write_readme_no_design_brief_framing():
    """Guard (b): ``write/__init__.__all__`` is non-empty (the engine ships) ⇒
    write/README.md carries NONE of the design-brief / pre-implementation phrases.
    Pins LD-090."""
    exports = _write_all_exports()
    assert exports, (
        "guard precondition: src/larkdocio/write/__init__.__all__ must be non-empty — "
        "the write package exports a real engine surface; an empty __all__ would mean "
        "the guard's premise changed."
    )
    text = (WRITE_PKG / "README.md").read_text(encoding="utf-8")
    hits = _forbidden_hits(text, _WRITER_README_FORBIDDEN)
    assert not hits, (
        f"src/larkdocio/write/README.md carries pre-implementation design-brief framing "
        f"{hits} while write/__init__ exports {len(exports)} engine names — the writer "
        f"has shipped (LD-090 rewrote this from design-brief → shipped-engine docs). Do "
        f"not let the 'empty on purpose / design brief' framing return."
    )


def test_ld649_guard_b_extends_to_the_write_package_docstring():
    """LD-649 — guard (b)'s blind spot, the same shape LD-142 found in guard (a).

    ``_WRITER_README_FORBIDDEN`` exists **specifically** to ban pre-implementation
    framing of the writer, but it was scanned over ``write/README.md`` only. The
    ``larkdocio.write`` package docstring — the text ``help(larkdocio.write)`` prints,
    which SHIPS IN THE WHEEL — carried "the binding **write round-trip gate** is still
    to come" through the entire write ladder, the Sheets arc and the Base era, while 21
    live gate families shipped and the README enumerated them. Same phrase list, same
    premise, one file over.
    """
    src = (WRITE_PKG / "__init__.py").read_text(encoding="utf-8")
    docstring = ast.get_docstring(ast.parse(src)) or ""
    assert docstring, (
        "larkdocio.write must carry a module docstring — it is help(larkdocio.write)"
    )
    exports = _write_all_exports()
    assert exports, (
        "guard precondition: src/larkdocio/write/__init__.__all__ must be non-empty — "
        "an empty __all__ would mean the guard's premise changed."
    )
    hits = _forbidden_hits(docstring, _WRITER_README_FORBIDDEN)
    assert not hits, (
        f"the larkdocio.write package docstring carries pre-implementation framing "
        f"{hits} while write/__init__ exports {len(exports)} engine names and the live "
        f"gate ring ships (write/README.md enumerates it against capabilities()' "
        f"gate_coverage). This is the docstring help(larkdocio.write) prints and it goes "
        f"out in the wheel; keep it true."
    )


def test_ld649_the_write_docstring_guard_flags_the_pre_ld649_text():
    """The RED half: the widened phrase list, applied to the verbatim pre-LD-649 clause,
    flags it — so the arm above would catch a regression rather than pass vacuously."""
    stale = (
        "transport, with an :class:`~larkdocio.write.model.ApplyLog` written for every "
        "attempt.\nThe binding **write round-trip gate** is still to come — see "
        "``README.md`` for\nthe design brief and the least-privilege two-app credential "
        "rationale.\n"
    )
    assert _forbidden_hits(stale, _WRITER_README_FORBIDDEN) == ["is still to come"]


def test_ld649_the_widened_phrase_does_not_false_trip_on_innocent_future_prose():
    """The new phrase is the FULL clause "is still to come", not "to come" — prose about
    a document's later section, or a refusal that is still to be typed, must not trip it."""
    innocent = (
        "The insert path is described below; the position algebra it depends on comes "
        "later in this file, and a caller reading top-down will meet the encoder first."
    )
    assert _forbidden_hits(innocent, _WRITER_README_FORBIDDEN) == []


# --- AC3: RED-proof against the exact pre-LD-089/090 stale text -------------
#
# Frozen snapshots of the drifted prose as it stood at v1.10.0 (verbatim, verified
# via ``git show v1.10.0:<file>``). Feeding the SAME guard logic these stale strings
# MUST flag them — proving the live guards above would go RED on a regression. Because
# LD-093 is blocked_by LD-089+090, the real docs on ``develop`` are already fixed, so
# the live guards are GREEN; these fixture tests are the RED half of the red/green proof.

_STALE_PROJECT_MD_V1_10 = (
    "  exists but ships empty (`src/larkdocio/write/`), with a design README. A writeback"
)
_STALE_README_MD_V1_10 = (
    "| `src/larkdocio/write/` | **Reserved** for the writeback apply-engine "
    "— empty package + design README. |"
)
_STALE_WRITE_README_V1_10 = (
    "# `larkdocio.write` — writeback apply-engine (design brief)\n\n"
    "This package is **empty on purpose** today. It reserves the home for the Lark\n"
    "docx *writeback* apply-engine so `larkdocio`'s package layout and credential\n"
    "scheme are ready for read/write separation **before** the writer is built. No\n"
    "writer code lives here yet — it lands in a later, separate session. This file is\n"
    "the **self-standing design brief** for that work."
)


def test_ld093_ac3_guard_a_logic_flags_v1_10_stale_prose():
    """AC3 (guard a): the guard-a logic flags the exact v1.10.0 stale strings — RED
    proof that the live guard would catch a regression of PROJECT.md / README.md."""
    assert _writer_context_hits(_STALE_PROJECT_MD_V1_10, _WRITER_STAGE_FORBIDDEN_ROOT) == [
        "ships empty"
    ]
    assert _writer_context_hits(_STALE_README_MD_V1_10, _WRITER_STAGE_FORBIDDEN_ROOT) == [
        "empty package"
    ]


def test_ld099_guard_b_phrase_ignores_innocent_later_prose():
    """LD-099: guard-(b)'s phrase is the FULL stale clause ``"lands in a later,
    separate session"`` — not the over-generic ``"lands in a later"``. Innocent future
    apply-engine prose that merely says an edit *lands in a later paragraph* must NOT
    false-trip the guard (the tightening's whole purpose)."""
    innocent = (
        "In a batched plan the writer applies edits in document order, so when an edit "
        "lands in a later paragraph than its anchor the offsets are recomputed."
    )
    assert _forbidden_hits(innocent, _WRITER_README_FORBIDDEN) == []


def test_ld142_guard_a_extends_to_the_top_level_package_docstring():
    """LD-142 rider — the guard-(a) blind spot that let the drift survive TWO cleanups.

    LD-089 fixed PROJECT.md + README.md and LD-093 pinned them, but the guard only ever
    scanned *Markdown*. ``src/larkdocio/__init__.py`` — the **first docstring a consumer
    reads**, and the module ``help(larkdocio)`` prints — still announced a ``write/`` package
    "reserved for the forthcoming writeback apply-engine; it ships empty today" through the
    whole W-ladder, the Sheets arc and the MD-authoring tranche. It is code, so no doc guard
    covered it. Now the package docstring carries the same premise as the docs it mirrors.
    """
    src = (ROOT / "src" / "larkdocio" / "__init__.py").read_text(encoding="utf-8")
    docstring = ast.get_docstring(ast.parse(src)) or ""
    assert docstring, "larkdocio.__init__ must carry a module docstring (it is the front door)"
    hits = _writer_context_hits(docstring, _WRITER_STAGE_FORBIDDEN_ROOT)
    assert not hits, (
        f"the larkdocio package docstring carries pre-implementation writer-stage prose "
        f"{hits} while src/larkdocio/write/apply.py ships — the writeback engine has been "
        f"BUILT since v1.6.0. This is the docstring help(larkdocio) prints; keep it true."
    )
    assert "forthcoming" not in docstring.lower(), (
        "the package docstring still calls a shipped surface 'forthcoming'")


def test_ld142_the_package_docstring_guard_flags_the_pre_ld142_text():
    """The RED half: the same guard logic applied to the verbatim pre-LD-142 docstring
    clause flags it — proof the guard above would catch a regression, not just pass."""
    stale = (
        "The single development home for the Lark ``docx`` reader (``read/``, ``blocks/``)\n"
        "and the shared block model. A ``write/`` package is reserved for the forthcoming\n"
        "writeback apply-engine (see ``write/README.md``); it ships empty today."
    )
    assert _writer_context_hits(stale, _WRITER_STAGE_FORBIDDEN_ROOT) == ["ships empty"]
    assert "forthcoming" in stale.lower()


def test_ld093_ac3_guard_b_logic_flags_v1_10_stale_prose():
    """AC3 (guard b): the guard-b logic flags the exact v1.10.0 write/README.md stale
    strings — RED proof that the live guard would catch a design-brief regression."""
    hits = _forbidden_hits(_STALE_WRITE_README_V1_10, _WRITER_README_FORBIDDEN)
    assert hits == sorted(
        [
            "empty on purpose",
            "No writer code lives here yet",
            "(design brief)",
            "lands in a later, separate session",
        ]
    )


# --------------------------------------------------------------------------- #
# LD-140 (the Markdown-authoring spec § F1-S7 AC6) — write/README.md § "Live-test discipline" must  #
# describe the REAL ring. It said "four gate families" for the whole tranche     #
# after LD-135 (table create) and LD-137 (by-id) each added one — the same class  #
# of drift LD-093 pinned, in the same file. Bound to capabilities()' gate         #
# coverage (itself bound to the test tree), so the prose, the registry and the     #
# filesystem now agree three ways.                                                #
# --------------------------------------------------------------------------- #

#: The gate-module names the README's live-discipline section may cite. Two prefixes, because
#: one member of the docx-write ring is READ-ONLY (LD-172: proving the reviewer-anchor contract
#: needs a document that already has inline anchors, and Lark has no anchored-comment create,
#: so no disposable can be given one). Matching only ``test_live_write_*`` would have made the
#: read-only arm undocumentable — the paragraph could not be seen by the guard that demands it.
_LIVE_DISCIPLINE_GATES = re.compile(
    r"`(test_live_(?:write|comment_anchor)_[a-z0-9_]+\.py)`")
_LIVE_DISCIPLINE_COUNT = re.compile(r"(\d+) gate families")


def _write_readme_text() -> str:
    return (WRITE_PKG / "README.md").read_text(encoding="utf-8")


def _coverage_members():
    from larkdocio import capabilities

    return capabilities(full=True)["surfaces"]["docx-write"]["gate_coverage"]["members"]


def test_ld140_write_readme_names_every_live_gate_family():
    """AC6 (both directions): the gate modules write/README.md names in its live-test
    discipline section equal the docx-write ring recorded in ``capabilities()``. A gate added
    without its paragraph (the LD-135 / LD-137 drift) reddens; a paragraph whose gate was
    deleted reddens too."""
    documented = set(_LIVE_DISCIPLINE_GATES.findall(_write_readme_text()))
    truth = {m["module"].rsplit("/", 1)[-1] for m in _coverage_members()}
    assert documented == truth, (
        f"write/README.md § Live-test discipline and capabilities()' gate coverage disagree: "
        f"only in the README {sorted(documented - truth)}; only in the registry "
        f"{sorted(truth - documented)}"
    )


def test_ld140_write_readme_gate_family_count_is_derived_not_stale():
    """The sentence that introduces the ring must carry the RIGHT number — "four gate
    families" survived two additions because no guard tied the count to anything."""
    match = _LIVE_DISCIPLINE_COUNT.search(_write_readme_text())
    assert match is not None, (
        "write/README.md must state how many gate families the live_write ring runs, as a "
        "digit, so the count can be guarded against the registry")
    assert int(match.group(1)) == len(_coverage_members()), (
        f"write/README.md claims {match.group(1)} gate families; the ring has "
        f"{len(_coverage_members())}")


def test_ld140_write_readme_documents_the_authoring_gate_and_its_concurrency_arm():
    """The tranche's own gate must be described where a maintainer reads about the ring —
    including that the concurrency arm proves the refusal is RECOVERABLE (the D9 posture),
    which is the part a reader would otherwise assume is a dead end."""
    text = _write_readme_text()
    assert "test_live_write_authoring_gate.py" in text
    for phrase in ("STALE_DOCUMENT", "re-plan"):
        assert phrase in text, (
            f"write/README.md's live-test discipline must mention {phrase!r} — the "
            f"authoring gate's concurrency arm is what proves it live")


# =====================================================================
# LD-219 — the `git am` hole in the role-prefix guard is closed
# =====================================================================
#
# A commit reached `develop` with no `[Role]` prefix despite the commit-msg hook.
# Reproduced in a scratch repo: `git format-patch` writes `Subject: [PATCH] [Dev] …`,
# `git am`'s mailinfo strips **both** bracketed tags, and `git am` runs
# `applypatch-msg` — NOT `commit-msg`. With no `applypatch-msg` hook the guard is
# simply absent on that path. The close is a delegating hook, so the two paths can
# never disagree about what a valid subject is.

APPLYPATCH_MSG = ROOT / "scripts" / "githooks" / "applypatch-msg"


@private_tree.citations
def test_ld219_the_applypatch_msg_hook_exists_and_is_executable():
    assert APPLYPATCH_MSG.is_file(), (
        "scripts/githooks/applypatch-msg is missing — `git am` runs applypatch-msg, not "
        "commit-msg, so a relocated commit bypasses the role-prefix guard entirely "
        "(that is how one commit landed prefix-less)"
    )
    assert os.access(APPLYPATCH_MSG, os.X_OK), "applypatch-msg is not executable"


@private_tree.kit
def test_ld219_the_applypatch_hook_DELEGATES_rather_than_restating_the_rule():
    """One authored copy of the rule. A second hand-rolled prefix regex would drift."""
    text = APPLYPATCH_MSG.read_text(encoding="utf-8")
    assert "commit-msg" in text, "applypatch-msg must delegate to the commit-msg guard"
    assert "ROLE_PREFIXES" not in text, (
        "applypatch-msg restates the prefix list — derive it by delegating instead"
    )


@pytest.mark.parametrize("subject,expected", [
    ("[Dev] LD-219: a relocated metadata commit", 0),
    ("LD-187: Handoff-to-QA notes (the prefix-less shape)", 1),
    ("[PATCH] [Dev] LD-219: what `git am -k` alone leaves behind", 1),
])
@private_tree.kit
def test_ld219_the_applypatch_hook_JUDGES_a_subject_the_same_way_commit_msg_does(
    subject, expected, tmp_path
):
    message = tmp_path / "msg"
    message.write_text(subject + "\n", encoding="utf-8")
    result = subprocess.run(
        [str(APPLYPATCH_MSG), str(message)],
        capture_output=True, text=True, cwd=str(ROOT),
        env={**os.environ, "MSG_OK": ""},
    )
    assert result.returncode == expected, (
        f"applypatch-msg returned {result.returncode} for {subject!r}, expected {expected}"
    )
