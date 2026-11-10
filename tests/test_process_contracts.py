"""The gate-contract guard (LD-377) — ``process/contracts/`` held complete, BOTH ways.

**The ruling this guard serves** (maintainer, 2026-08-09): *"descriptions or even sample scripts for all
of our deterministic gates and rituals. The project need not use python or shell if they don't
want to but the spirit needs to be there."*

Everything this kit *enforces* was, until these sheets, defined **only** inside its shell
implementations. A contract sheet states what any implementation — in any language — must
guarantee, must refuse, and must be able to show as green. The sheets are the spirit; the
scripts are one carrier of it.

**Both directions, front-door-doctrine style** (the shape borrowed from
``tests/test_front_door_doctrine.py`` by way of ``tests/test_corpus_manifest.py``):

1. **Direction 1** — every script that owes a contract **has a sheet**. A new gate arriving with
   no contract reddens the build, which is the only thing that keeps the set complete as the kit
   grows.
2. **Direction 2** — every implementation a sheet **cites** exists. A sheet describing a gate
   that no longer exists is a fiction, and a fiction is worse than a gap: a gap is visible.

**THE CLASS RULE — which scripts owe a sheet** (LD-377 AC7). Every file under ``scripts/``
carries a one-line ``KIT-CLASS:`` marker (the convention is ``process/EXTRACTION.md``'s), and the
class decides the duty:

* ``KIT``     — travels unedited. **Owes a sheet.** The contract *is* the thing that travels
  when the script does not.
* ``MIXED``   — travels, but carries project law you must edit. **Owes a sheet, and the sheet
  describes the KIT HALF only** — the pattern, never this project's gate commands, version
  files or prefix set. Each such sheet says so in its own reference section, and
  :func:`test_a_MIXED_scripts_sheet_declares_that_it_describes_the_KIT_HALF` checks it.
* ``PROJECT`` — does not travel. **Owes nothing, and no sheet may claim it** — a contract over a
  file the adopter will never receive is noise that reads as an obligation.

**The marker trap this guard is written around:** a script may *contain* a second ``KIT-CLASS:``
line because it **writes** one into a file it generates (``kit-init.sh`` emits a ``verify.sh``
header). Only the **first** marker in a file is that file's own class; a naive whole-file grep
classifies the initializer as ``MIXED``. See :func:`kit_class`.

**No git is invoked** (``tests/test_no_test_reads_live_git.py`` forbids it suite-wide). This
guard reads the tree and reads Markdown as text.
"""
import pathlib
import re

from guard_kit import REPO_ROOT, section
import private_tree  # noqa: E402  (LD-685)

CONTRACTS_DIR = REPO_ROOT / "process" / "contracts"
SCRIPTS_DIR = REPO_ROOT / "scripts"
INDEX = CONTRACTS_DIR / "README.md"
MANUAL = REPO_ROOT / "process" / "MANUAL.md"
EXTRACTION = REPO_ROOT / "process" / "EXTRACTION.md"

#: The six sections every sheet carries, in this order. The shape is the whole point: an
#: adopter reading the fifth sheet already knows where the refusals are.
SECTIONS = (
    "## 1. PURPOSE",
    "## 2. HARD INVARIANTS",
    "## 3. REFUSAL CONDITIONS",
    "## 4. WHAT GREEN MEANS",
    "## 5. MINIMAL INTERFACE",
    "## 6. REFERENCE IMPLEMENTATION",
)

#: Sections 1–5 are the **language-agnostic** half; section 6 is the only place an
#: implementation may be named. The reader test is *"could a Rust implementer satisfy this
#: without opening the script?"* — so the scan below runs over these five and not the sixth.
AGNOSTIC_SECTIONS = SECTIONS[:5]

#: "≤ one page", made measurable. A limit nobody can check is not a limit; these two numbers
#: are the operational definition of the issue's page bound (long lines cannot buy space back).
LINE_LIMIT = 120
CHAR_LIMIT = 8500

#: The **eleven minimum contracts** LD-377 names, each mapped to the sheet that carries it.
#: Dev may add (see the index's "Additions" table) but may not drop.
REQUIRED_CONTRACTS = {
    "verify-gate.md": "the verify gate",
    "board-mover.md": "the board mover",
    "landing-gate.md": "the landing gate",
    "commit-attribution.md": "commit attribution",
    "id-minting.md": "id minting",
    "issue-creation.md": "issue / spec creation",
    "archive-sweep.md": "the archive sweep",
    "drift-report.md": "the drift report",
    "kanban-worktree.md": "the kanban-worktree invariant",
    "release-ritual.md": "the release ritual",
    "liveness-watchdog.md": "the liveness / watchdog ritual",
}

#: Terms that give an implementation away. A rule stated in any of these is stated in terms of
#: the carrier rather than the cargo — which is exactly the failure this issue exists to
#: prevent. Each maps to the reason it is banned, so the failure message teaches.
IMPLEMENTATION_TERMS = {
    r"\bbash\b": "the shell that happens to carry this contract today",
    r"\bzsh\b": "a shell name",
    r"\bshell\b": "a shell is one runtime, not the rule",
    r"\bpytest\b": "one project's test runner",
    r"\bpython\b": "one project's language",
    r"\bgrep\b": "a Unix tool name",
    r"\bsed\b": "a Unix tool name",
    r"\bawk\b": "a Unix tool name",
    r"\bmktemp\b": "a Unix tool name",
    r"\bheredoc\b": "a shell construct",
    r"\.sh\b": "a script filename — implementations live in section 6 only",
    r"(?<![\w-])--[a-z]": "a command-line flag; a reimplementation owes the information flow, "
    "not the command line",
    r"\bscripts/": "a path internal to one implementation",
    r"\.kanban-wt\b": "the donor's directory name for the auxiliary checkout",
}

#: A sheet that answers an invariant with a pointer has failed its only job.
DEFERRAL_RE = re.compile(
    r"see (?:the )?(?:script|implementation|source|reference implementation)\b", re.I
)

#: Backticked tokens that look like repository paths. Extension-or-slash, because two of the
#: kit's own files (``githooks/commit-msg``, ``githooks/applypatch-msg``) carry no extension.
_TICKED_RE = re.compile(r"`([^`\s]+)`")
_PATHY_RE = re.compile(r"^[A-Za-z0-9_.][A-Za-z0-9_./-]*$")
_EXT_RE = re.compile(r"\.(?:md|sh|py|toml|json|js|example)$")

#: A version literal that could be mistaken for this project's real one. LD-377 mandates the
#: obviously-fictional ``42.x`` convention, which this pattern deliberately never matches (its
#: minor is not a digit) — so any hit here is a real-looking version that must go.
VERSION_LITERAL_RE = re.compile(r"(?<![\w.])(v\d+\.\d+(?:\.\d+)?|\d+\.\d+\.\d+)(?![\w.])")

#: Not a sheet — the index. Excluded from the per-sheet shape checks by name and on purpose,
#: and held complete against the sheets by its own test instead.
INDEX_NAME = "README.md"


# --------------------------------------------------------------------------- #
# Mechanics — every one of these takes its root as an argument, so the         #
# both-directions failures can be PROVEN against a synthetic tree instead of   #
# asserted about the real one.                                                 #
# --------------------------------------------------------------------------- #

_MARKER_RE = re.compile(r"KIT-CLASS:\s*(KIT|MIXED|PROJECT)\b")


def kit_class(path: pathlib.Path) -> str:
    """The file's OWN class — the **first** ``KIT-CLASS:`` marker, or ``UNMARKED``.

    First, not any: a generator script writes marker lines into the files it emits, so a
    whole-file search reports the class of something the script *produces*.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:  # pragma: no cover - unreadable file is a tree problem, not a rule
        return "UNMARKED"
    hit = _MARKER_RE.search(text)
    return hit.group(1) if hit else "UNMARKED"


def scripts_by_class(scripts_dir: pathlib.Path, root: pathlib.Path) -> dict:
    """Every file under ``scripts_dir`` as ``repo-relative posix path -> class``.

    Compiled bytecode is skipped: a ``.pyc`` cannot carry a marker, the duty belongs to the
    source it came from, and ``__pycache__`` is gitignored — so including it made the
    classification red depend on whether anything had imported a ``scripts/`` module yet.
    """
    return {
        p.relative_to(root).as_posix(): kit_class(p)
        for p in sorted(scripts_dir.rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


def scripts_owing_a_sheet(scripts_dir: pathlib.Path, root: pathlib.Path) -> dict:
    """The KIT and MIXED files — the ones that travel, and so owe a contract."""
    return {
        path: klass
        for path, klass in scripts_by_class(scripts_dir, root).items()
        if klass in ("KIT", "MIXED")
    }


def sheet_paths(contracts_dir: pathlib.Path) -> list:
    """The contract sheets — every ``*.md`` in the directory except the index."""
    return [p for p in sorted(contracts_dir.rglob("*.md"))  # LD-654: recursive population
            if p.name != INDEX_NAME]


def cited_paths(sheet_text: str) -> list:
    """Repository paths a sheet's REFERENCE IMPLEMENTATION section cites, in order."""
    body = section(sheet_text, SECTIONS[5])
    out = []
    for token in _TICKED_RE.findall(body):
        if not _PATHY_RE.match(token):
            continue
        if "/" in token or _EXT_RE.search(token):
            out.append(token.rstrip("/"))
    return out


def unsheeted_scripts(contracts_dir: pathlib.Path, scripts_dir: pathlib.Path, root: pathlib.Path):
    """DIRECTION 1 — scripts owing a contract that no sheet cites, with the fix in the message."""
    claimed = set()
    for sheet in sheet_paths(contracts_dir):
        claimed.update(cited_paths(sheet.read_text(encoding="utf-8")))
    missing = sorted(p for p in scripts_owing_a_sheet(scripts_dir, root) if p not in claimed)
    return missing


def dangling_references(contracts_dir: pathlib.Path, root: pathlib.Path):
    """DIRECTION 2 — ``(sheet name, cited path)`` for every citation that does not resolve."""
    out = []
    for sheet in sheet_paths(contracts_dir):
        for cited in cited_paths(sheet.read_text(encoding="utf-8")):
            if not (root / cited).exists():
                out.append((sheet.name, cited))
    return out


def _agnostic_text(sheet_text: str) -> str:
    return "\n".join(section(sheet_text, head) for head in AGNOSTIC_SECTIONS)


def _invariant_bullets(sheet_text: str) -> list:
    """The HARD INVARIANTS section as BLOCKS — each top-level bullet with its wrapped lines.

    Block, not line: an invariant worth stating rarely fits on one line, and its *Why:* clause
    belongs with it rather than counting as a separate rule.
    """
    blocks, current = [], None
    for line in section(sheet_text, SECTIONS[1]).splitlines():
        if line.startswith("- "):
            if current is not None:
                blocks.append("\n".join(current))
            current = [line]
        elif current is not None:
            if line.strip() and not line.startswith(" "):
                blocks.append("\n".join(current))
                current = None
            else:
                current.append(line)
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


def _sheets():
    return sheet_paths(CONTRACTS_DIR)


def _read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# AC1 — the directory, the six sections, the page bound                        #
# --------------------------------------------------------------------------- #


@private_tree.citations
def test_the_contracts_live_beside_the_kit_manifest_they_belong_to():
    assert CONTRACTS_DIR.is_dir(), (
        f"{CONTRACTS_DIR} is missing — the gate contracts are the language-agnostic half of "
        "the kit and live beside process/EXTRACTION.md"
    )
    assert _sheets(), "process/contracts/ holds no contract sheet"


@private_tree.process
def test_every_sheet_carries_ALL_SIX_SECTIONS_IN_ORDER():
    for sheet in _sheets():
        text = _read(sheet)
        found = [head for head in SECTIONS if head in text]
        assert found == list(SECTIONS), (
            f"{sheet.name}: sections must be exactly {list(SECTIONS)} in order; found {found}. "
            "Add the missing heading(s) verbatim."
        )
        assert [text.find(h) for h in SECTIONS] == sorted(text.find(h) for h in SECTIONS), (
            f"{sheet.name}: the six sections appear out of order"
        )


@private_tree.process
def test_every_sheet_fits_ON_ONE_PAGE():
    for sheet in _sheets():
        text = _read(sheet)
        lines = len(text.splitlines())
        assert lines <= LINE_LIMIT and len(text) <= CHAR_LIMIT, (
            f"{sheet.name}: {lines} lines / {len(text)} chars exceeds the one-page bound "
            f"({LINE_LIMIT} lines, {CHAR_LIMIT} chars). Cut prose or split the contract — "
            "a sheet nobody finishes reading is not reimplementable."
        )


@private_tree.process
def test_no_sheet_is_a_STUB_every_section_says_something():
    for sheet in _sheets():
        text = _read(sheet)
        for head in SECTIONS:
            body = [ln for ln in section(text, head).splitlines()[1:] if ln.strip()]
            assert len(body) >= 2, (
                f"{sheet.name}: section {head!r} has {len(body)} content line(s) — "
                "a heading with nothing under it is a promise, not a contract"
            )


# --------------------------------------------------------------------------- #
# AC2 — the eleven minimum contracts, and the index that accounts for the rest #
# --------------------------------------------------------------------------- #


@private_tree.citations
def test_the_ELEVEN_MINIMUM_CONTRACTS_are_all_present():
    have = {p.name for p in _sheets()}
    missing = sorted(set(REQUIRED_CONTRACTS) - have)
    assert not missing, (
        f"the LD-377 minimum set is incomplete — missing {missing}. "
        "The table in the issue is a floor: write the sheet, or record the merge and why."
    )


@private_tree.process
def test_every_sheet_is_LISTED_in_the_index_and_the_index_lists_NO_PHANTOM():
    index = _read(INDEX)
    names = {p.name for p in _sheets()}
    for name in sorted(names):
        assert f"({name})" in index or f"`{name}`" in index, (
            f"{name} is not listed in process/contracts/README.md — add its row"
        )
    for ticked in re.findall(r"\(([a-z0-9-]+\.md)\)", index):
        assert ticked in names or ticked == INDEX_NAME, (
            f"the index lists {ticked}, which is not a sheet — delete the row or write the sheet"
        )


# --------------------------------------------------------------------------- #
# AC3 — THE LANGUAGE-AGNOSTIC TEST                                             #
# --------------------------------------------------------------------------- #


@private_tree.process
def test_NO_SHEET_states_a_rule_in_IMPLEMENTATION_TERMS():
    for sheet in _sheets():
        text = _agnostic_text(_read(sheet))
        for pattern, why in IMPLEMENTATION_TERMS.items():
            hit = re.search(pattern, text, re.I)
            assert hit is None, (
                f"{sheet.name}: sections 1–5 contain {hit.group(0)!r} — {why}. "
                "Move it to section 6 (REFERENCE IMPLEMENTATION) and restate the rule in terms "
                "of what must be TRUE."
            )


@private_tree.process
def test_NO_SHEET_substitutes_A_POINTER_for_an_invariant():
    for sheet in _sheets():
        text = _agnostic_text(_read(sheet))
        hit = DEFERRAL_RE.search(text)
        assert hit is None, (
            f"{sheet.name}: sections 1–5 say {hit.group(0)!r}. Write the rule out — a reader "
            "who will never open the implementation is the only reader this sheet has."
        )


@private_tree.process
def test_every_reference_section_marks_itself_ONE_IMPLEMENTATION_NOT_THE_DEFINITION():
    for sheet in _sheets():
        body = section(_read(sheet), SECTIONS[5]).lower()
        assert "one implementation, not the definition" in body, (
            f"{sheet.name}: section 6 must carry the phrase 'One implementation, not the "
            "definition' — without it the citation reads as the spec"
        )


# --------------------------------------------------------------------------- #
# AC4 — the hard-won lessons, as invariants with their why                     #
# --------------------------------------------------------------------------- #

#: ``sheet -> phrases that must appear in its HARD INVARIANTS section``. Each is a lesson this
#: project paid for once; a lesson that lives only in a retrospective gets re-learned.
LESSON_INVARIANTS = {
    "landing-gate.md": ["caller-supplied"],
    "release-ritual.md": ["before the version", "after the push"],
    "liveness-watchdog.md": [
        "freshness",
        "absence of news",
        "symbolic link",
        "buffered",
        "probe",
    ],
}


@private_tree.process
def test_the_HARD_WON_LESSONS_are_INVARIANTS_not_anecdotes():
    for name, phrases in LESSON_INVARIANTS.items():
        body = section(_read(CONTRACTS_DIR / name), SECTIONS[1]).lower()
        for phrase in phrases:
            assert phrase in body, (
                f"{name}: HARD INVARIANTS does not state the {phrase!r} rule. This lesson was "
                "learned by incident; state it as a rule an implementation must hold."
            )


@private_tree.process
def test_every_HARD_INVARIANT_carries_its_ONE_LINE_WHY():
    for sheet in _sheets():
        bullets = _invariant_bullets(_read(sheet))
        assert bullets, f"{sheet.name}: HARD INVARIANTS has no bullet"
        for bullet in bullets:
            assert "*Why:*" in bullet, (
                f"{sheet.name}: invariant {bullet[:60]!r}… has no '*Why:*' clause. An "
                "unexplained rule is the first one an adopter drops."
            )


# --------------------------------------------------------------------------- #
# AC5 / AC6 — the bidirectional guard, and PROOF that it reddens both ways     #
# --------------------------------------------------------------------------- #


@private_tree.citations
def test_DIRECTION_1_every_TRAVELLING_SCRIPT_has_a_contract_sheet():
    missing = unsheeted_scripts(CONTRACTS_DIR, SCRIPTS_DIR, REPO_ROOT)
    assert not missing, (
        "these travelling (KIT/MIXED) scripts have no contract sheet: "
        + ", ".join(missing)
        + " — write a sheet under process/contracts/ (or extend an existing sheet's section 6 "
        "if the gate is already contracted), then list it in the index."
    )


@private_tree.process
def test_DIRECTION_2_every_CITED_IMPLEMENTATION_EXISTS():
    dangling = dangling_references(CONTRACTS_DIR, REPO_ROOT)
    assert not dangling, (
        "these contract sheets cite an implementation that does not exist: "
        + ", ".join(f"{name} → {path}" for name, path in dangling)
        + " — correct the citation, or delete the sheet if the gate is gone."
    )


def _fake_tree(tmp_path, sheet_body: str, script_marker: str = "# KIT-CLASS: KIT — x.\n"):
    (tmp_path / "process" / "contracts").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "newcomer.sh").write_text(script_marker, encoding="utf-8")
    (tmp_path / "process" / "contracts" / "sample.md").write_text(sheet_body, encoding="utf-8")
    return tmp_path


_SHEET_STUB = "## 6. REFERENCE IMPLEMENTATION\n\nOne implementation, not the definition.\n\n- `%s`\n"


def test_a_NEW_TRAVELLING_SCRIPT_WITH_NO_SHEET_is_reported_BY_NAME(tmp_path):
    root = _fake_tree(tmp_path, _SHEET_STUB % "scripts/other.sh")
    missing = unsheeted_scripts(root / "process" / "contracts", root / "scripts", root)
    assert missing == ["scripts/newcomer.sh"]


def test_a_PROJECT_CLASS_NEWCOMER_owes_NOTHING(tmp_path):
    root = _fake_tree(
        tmp_path,
        _SHEET_STUB % "scripts/newcomer.sh",
        script_marker="# KIT-CLASS: PROJECT — does not travel.\n",
    )
    assert unsheeted_scripts(root / "process" / "contracts", root / "scripts", root) == []


def test_a_SHEET_POINTING_AT_A_VANISHED_IMPLEMENTATION_is_reported_BY_NAME(tmp_path):
    root = _fake_tree(tmp_path, _SHEET_STUB % "scripts/gone.sh")
    assert dangling_references(root / "process" / "contracts", root) == [
        ("sample.md", "scripts/gone.sh")
    ]


def test_BOTH_REFUSALS_say_WHAT_TO_DO_not_merely_what_is_wrong(tmp_path):
    root = _fake_tree(tmp_path, _SHEET_STUB % "scripts/gone.sh")
    missing = unsheeted_scripts(root / "process" / "contracts", root / "scripts", root)
    dangling = dangling_references(root / "process" / "contracts", root)
    for message in (
        "these travelling (KIT/MIXED) scripts have no contract sheet: "
        + ", ".join(missing)
        + " — write a sheet under process/contracts/ (or extend an existing sheet's section 6 "
        "if the gate is already contracted), then list it in the index.",
        "these contract sheets cite an implementation that does not exist: "
        + ", ".join(f"{n} → {p}" for n, p in dangling)
        + " — correct the citation, or delete the sheet if the gate is gone.",
    ):
        assert "—" in message and any(
            verb in message for verb in ("write a sheet", "correct the citation")
        ), "a refusal must name the remedy, not only the defect"


@private_tree.kit
def test_the_FIRST_MARKER_WINS_so_a_GENERATOR_is_not_misclassified():
    """``kit-init.sh`` writes a ``MIXED`` header into the gate runner it emits."""
    initializer = SCRIPTS_DIR / "kit-init.sh"
    assert kit_class(initializer) == "KIT"
    assert initializer.read_text(encoding="utf-8").count("KIT-CLASS:") > 1


# --------------------------------------------------------------------------- #
# AC7 — MIXED and PROJECT, handled honestly                                    #
# --------------------------------------------------------------------------- #


@private_tree.process
def test_NO_SHEET_CLAIMS_A_PROJECT_CLASS_SCRIPT():
    project = {p for p, k in scripts_by_class(SCRIPTS_DIR, REPO_ROOT).items() if k == "PROJECT"}
    assert project, "the class rule is untested if nothing in scripts/ is PROJECT-class"
    for sheet in _sheets():
        overclaimed = sorted(project.intersection(cited_paths(_read(sheet))))
        assert not overclaimed, (
            f"{sheet.name} cites {overclaimed}, which does not travel — a contract over a file "
            "the adopter never receives reads as an obligation they do not have"
        )


@private_tree.process
def test_a_MIXED_scripts_sheet_declares_that_it_describes_the_KIT_HALF():
    mixed = {p for p, k in scripts_by_class(SCRIPTS_DIR, REPO_ROOT).items() if k == "MIXED"}
    assert mixed, "the MIXED rule is untested if nothing in scripts/ is MIXED-class"
    for sheet in _sheets():
        body = section(_read(sheet), SECTIONS[5])
        if mixed.intersection(cited_paths(_read(sheet))):
            assert "kit half" in body.lower(), (
                f"{sheet.name} cites a MIXED implementation but does not say the contract "
                "describes the KIT HALF only — an adopter would inherit this project's law"
            )


def test_the_CLASS_RULE_is_stated_in_THIS_GUARDS_OWN_COMMENTS():
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    head = source.split("import pathlib", 1)[0]
    for token in ("KIT", "MIXED", "PROJECT", "KIT HALF"):
        assert token in head, (
            f"the class rule must state {token!r} in this guard's own comments so the next "
            "reader does not re-derive it from the assertions"
        )


@private_tree.process
def test_EVERY_SCRIPT_IS_CLASSIFIED_so_the_duty_is_never_ambiguous():
    unmarked = sorted(
        p for p, k in scripts_by_class(SCRIPTS_DIR, REPO_ROOT).items() if k == "UNMARKED"
    )
    assert not unmarked, (
        f"unclassified script(s): {unmarked} — add the one-line KIT-CLASS marker; without it "
        "nobody can say whether the file owes a contract"
    )


@private_tree.process
def test_the_classification_scan_ignores_COMPILED_BYTECODE():
    """A ``.pyc`` is not a script and cannot carry a marker.

    Found by LD-612: the first test to *import* a ``scripts/*.py`` module left a
    ``scripts/__pycache__/*.pyc`` behind, and the scan above reported it UNMARKED — a red with
    no possible fix, because the duty belongs to the source file it was compiled from.
    ``__pycache__`` is gitignored, so the red also depended on whether the tree had been run.
    """
    cache = SCRIPTS_DIR / "__pycache__"
    cache.mkdir(exist_ok=True)
    (cache / "ld612_probe.cpython-000.pyc").write_bytes(b"\x00\x00\x00\x00not text")
    try:
        scanned = scripts_by_class(SCRIPTS_DIR, REPO_ROOT)
    finally:
        (cache / "ld612_probe.cpython-000.pyc").unlink()
    assert not [path for path in scanned if "__pycache__" in path], sorted(scanned)


# --------------------------------------------------------------------------- #
# AC8 — the KIT-CLASS marker and the version-literal trap                      #
# --------------------------------------------------------------------------- #


@private_tree.process
def test_every_sheet_carries_the_KIT_CLASS_KIT_MARKER():
    for sheet in _sheets() + [INDEX]:
        first = _read(sheet).splitlines()[0]
        assert "KIT-CLASS: KIT" in first, (
            f"{sheet.name}: the first line must carry the KIT-CLASS: KIT marker — the contracts "
            "travel unedited, and the marker is what says so where it cannot be missed"
        )


@private_tree.process
def test_NO_REAL_VERSION_LITERAL_appears_in_any_sheet():
    for sheet in _sheets() + [INDEX]:
        hits = VERSION_LITERAL_RE.findall(_read(sheet))
        assert not hits, (
            f"{sheet.name}: version-shaped literal(s) {hits} — use the obviously-fictional "
            "42.x convention so no example can be mistaken for this project's real version "
            "or rot into a lie when the real one moves"
        )


@private_tree.process
def test_THE_FICTIONAL_CONVENTION_IS_ACTUALLY_USED_where_a_version_is_needed():
    assert "42.x" in _read(CONTRACTS_DIR / "release-ritual.md"), (
        "the release contract needs a version in its examples; it must be the fictional 42.x"
    )


# --------------------------------------------------------------------------- #
# AC9 — the two doors that must lead here                                      #
# --------------------------------------------------------------------------- #


@private_tree.process
def test_THE_MANUAL_points_at_the_contracts_as_its_MACHINE_FACING_COMPLEMENT():
    assert "process/contracts/" in _read(MANUAL), (
        "process/MANUAL.md must point at process/contracts/ — the manual is the prose, the "
        "contracts are the enforceable half of the same rules"
    )


@private_tree.process
def test_EXTRACTION_routes_the_NON_BASH_ADOPTER_at_the_contracts():
    text = _read(EXTRACTION)
    assert "process/contracts/" in text, (
        "process/EXTRACTION.md must route the adopter at process/contracts/ — an adopter who "
        "takes none of the scripts still owes the contracts"
    )
