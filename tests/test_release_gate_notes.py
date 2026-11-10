"""THE RELEASE-GATE GUARD — ``release.sh`` refuses to tag a version undocumented in
EITHER ``CHANGELOG.md`` **or** ``RELEASE_NOTES.md``, with DISTINCT refusal messages (LD-164).

Why a second arm at all
-----------------------
A consumer-facing notes file that nothing enforces stops being maintained by the second
release. The release script already refused to tag a version whose ``CHANGELOG.md`` section
was missing; that same protection now extends to the notes. The two refusals must NOT share
a message — a shared one would leave the author guessing which file to write.

How these tests drive the real script
-------------------------------------
Each case builds a throwaway git repo in ``tmp_path``, copies ``scripts/release.sh`` into it
(the script resolves its repo root from its own location, so the copy resolves the SANDBOX —
never this repo, never the real remote), seeds the version-bearing files, and runs the script
with ``--dry-run``: every preflight gate runs, then the script STOPS before mutating
anything. The heavier gates are stubbed through the script's own documented test seams
(``RELEASE_VERIFY_CMD`` / ``RELEASE_LIVE_CMD`` / ``RELEASE_BOARD_CMD``) so the ONLY gate
under test is the documentation gate.

``scripts/test/run.sh`` carries the same arms as full sandbox cases that also prove the
non-mutation contract against a real remote; these tests are the fast, always-run half that
rides in ``pytest -q``.
"""
import os
import pathlib
import re
import shutil
import subprocess

import pytest

from release_versions import ahead_refusal, packaged_version, section_starts
import private_tree  # noqa: E402  (LD-685)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RELEASE_SH = REPO_ROOT / "scripts" / "release.sh"

TARGET = "1.99.0"
OTHER = "1.9.0"          # a *different* version, present in both files as noise


def _git(root, *args):
    """A git command inside the sandbox, insulated from the developer's own config.

    The sandbox sets its identity, signing and hooks path in its OWN repo config (local
    config wins), and ``GIT_CONFIG_NOSYSTEM`` drops the system file — so a machine with a
    global signing key or a global hooks path cannot make these tests flaky. The rest of the
    environment (notably ``PATH``, so ``git`` resolves wherever it lives) is inherited.
    """
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", "-C", str(root), *args], check=True, env=env, capture_output=True)


def _write_doc(path, versions, title):
    body = [f"# {title}", ""]
    for version in versions:
        body += [f"## [{version}] — 2026-07-29", "seeded section", ""]
    path.write_text("\n".join(body), encoding="utf-8")


def _sandbox(tmp_path, changelog_versions, notes_versions, notes_file=True):
    """A throwaway repo on `develop` with a clean tree; returns its root."""
    root = tmp_path / "sandbox"
    (root / "scripts").mkdir(parents=True)
    (root / "src" / "larkdocio").mkdir(parents=True)
    shutil.copy2(RELEASE_SH, root / "scripts" / "release.sh")

    (root / "pyproject.toml").write_text(
        '[project]\nname = "larkdocio"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (root / "src" / "larkdocio" / "__init__.py").write_text(
        '__version__ = "1.0.0"\n', encoding="utf-8"
    )
    _write_doc(root / "CHANGELOG.md", changelog_versions, "Changelog")
    if notes_file:
        _write_doc(root / "RELEASE_NOTES.md", notes_versions, "Release notes")

    board = root / "board-clean.sh"
    board.write_text('#!/usr/bin/env bash\necho "── board-drift: clean ✓"\n', encoding="utf-8")
    board.chmod(0o755)

    _git(root, "init", "-q")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/develop")
    for key, value in (
        ("user.email", "test@sandbox.local"),
        ("user.name", "Sandbox Test"),
        ("init.defaultBranch", "develop"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", str(root / ".git" / "hooks")),
    ):
        _git(root, "config", key, value)
    _commit(root, "seed")
    return root


def _commit(root, message):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def _run_release(root, version=TARGET):
    """Run the sandboxed release.sh --dry-run; returns (returncode, combined output)."""
    result = subprocess.run(
        ["bash", str(root / "scripts" / "release.sh"), version, "--dry-run"],
        cwd=root,
        capture_output=True,
        text=True,
        env=dict(
            os.environ,
            GIT_CONFIG_NOSYSTEM="1",
            # The script's own documented test seams: stub the heavy gates so the ONLY
            # gate under test is the documentation gate. The board stub prints the marker
            # gate d looks for.
            RELEASE_VERIFY_CMD="true",
            RELEASE_LIVE_CMD="true",
            RELEASE_BOARD_CMD=str(root / "board-clean.sh"),
        ),
    )
    return result.returncode, result.stdout + result.stderr


def _unmutated(root):
    """--dry-run must mutate nothing — the version files stay at their seeded value."""
    assert 'version = "1.0.0"' in (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "1.0.0"' in (
        root / "src" / "larkdocio" / "__init__.py"
    ).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# AC5 — both arms pass when both files document the version                     #
# --------------------------------------------------------------------------- #

@private_tree.kit
def test_both_files_documented_passes_the_gate(tmp_path):
    root = _sandbox(tmp_path, [TARGET, OTHER], [TARGET, OTHER])
    code, output = _run_release(root)
    assert code == 0, f"gate refused a fully documented version:\n{output}"
    assert "all gates green" in output
    _unmutated(root)


# --------------------------------------------------------------------------- #
# AC5 — the NEW arm bites: notes section missing                                #
# --------------------------------------------------------------------------- #

@private_tree.kit
def test_missing_notes_section_refuses(tmp_path):
    root = _sandbox(tmp_path, [TARGET, OTHER], [OTHER])
    code, output = _run_release(root)
    assert code != 0, f"gate tagged a version absent from RELEASE_NOTES.md:\n{output}"
    assert "RELEASE_NOTES.md" in output, (
        f"the refusal never names RELEASE_NOTES.md, so the author must guess:\n{output}"
    )
    assert TARGET in output, "the refusal does not name the version it wants documented"
    _unmutated(root)


@private_tree.kit
def test_missing_notes_file_entirely_refuses(tmp_path):
    """A deleted notes file must refuse exactly like an undocumented one (grep on a
    nonexistent path must not read as 'documented')."""
    root = _sandbox(tmp_path, [TARGET], [], notes_file=False)
    code, output = _run_release(root)
    assert code != 0, f"gate passed with no RELEASE_NOTES.md at all:\n{output}"
    assert "RELEASE_NOTES.md" in output


@private_tree.kit
def test_restoring_the_notes_section_turns_the_gate_green(tmp_path):
    """Red → green on the new arm alone: the ONLY thing that changes is the notes section."""
    root = _sandbox(tmp_path, [TARGET, OTHER], [OTHER])
    red_code, _red = _run_release(root)
    assert red_code != 0

    _write_doc(root / "RELEASE_NOTES.md", [TARGET, OTHER], "Release notes")
    _commit(root, "add the notes section")
    green_code, green = _run_release(root)
    assert green_code == 0, f"restoring the notes section did not turn the gate green:\n{green}"


# --------------------------------------------------------------------------- #
# AC5 — the EXISTING changelog arm still bites INDEPENDENTLY (unweakened)       #
# --------------------------------------------------------------------------- #

@private_tree.kit
def test_missing_changelog_section_still_refuses(tmp_path):
    root = _sandbox(tmp_path, [OTHER], [TARGET, OTHER])
    code, output = _run_release(root)
    assert code != 0, f"extending the gate weakened its original arm:\n{output}"
    assert "CHANGELOG.md" in output
    _unmutated(root)


@private_tree.kit
def test_the_two_refusal_messages_are_not_equal(tmp_path):
    """A string comparison, not a human read: a shared message is the failure mode."""
    changelog_missing = _run_release(_sandbox(tmp_path / "a", [OTHER], [TARGET, OTHER]))[1]
    notes_missing = _run_release(_sandbox(tmp_path / "b", [TARGET, OTHER], [OTHER]))[1]

    def refusal(output):
        lines = [line for line in output.splitlines() if line.startswith("release.sh:")]
        assert lines, f"no 'release.sh:' refusal line in:\n{output}"
        return lines[-1]

    changelog_line, notes_line = refusal(changelog_missing), refusal(notes_missing)
    assert changelog_line != notes_line, (
        f"both arms emit the SAME refusal ({changelog_line!r}) — the author cannot tell "
        "which file is missing a section"
    )
    assert "CHANGELOG.md" in changelog_line and "RELEASE_NOTES.md" not in changelog_line
    assert "RELEASE_NOTES.md" in notes_line and "CHANGELOG.md" not in notes_line


@private_tree.kit
def test_both_missing_refuses_deterministically_naming_the_changelog_first(tmp_path):
    """DOCUMENTED CALL (AC5): with both sections absent the gate reports the FIRST arm
    (``CHANGELOG.md``) deterministically — the arms run in order and abort on the first
    failure, matching every other preflight gate's fail-fast posture. Fixing that one then
    surfaces the notes arm.
    """
    root = _sandbox(tmp_path, [OTHER], [OTHER])
    code, output = _run_release(root)
    assert code != 0
    refusals = [line for line in output.splitlines() if line.startswith("release.sh:")]
    assert len(refusals) == 1, f"expected exactly one refusal line, got {refusals}"
    assert "CHANGELOG.md" in refusals[0]
    _unmutated(root)


# --------------------------------------------------------------------------- #
# The rigor amplifier — the new arm's regex must be as STRICT as the old one     #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "seeded_heading",
    [
        "## [1.99.0-rc] — 2026-07-29",     # a version string the target is a PREFIX of
        "## [1.99.01] — 2026-07-29",
        "### [1.99.0] — 2026-07-29",       # right version, wrong heading level
        "## 1.99.0 — 2026-07-29",          # unbracketed
        "notes for ## [1.99.0]",           # not at line start
    ],
)
@private_tree.kit
def test_the_notes_arm_does_not_match_a_near_miss_heading(tmp_path, seeded_heading):
    root = _sandbox(tmp_path, [TARGET], [])
    (root / "RELEASE_NOTES.md").write_text(
        f"# Release notes\n\n{seeded_heading}\nseeded\n", encoding="utf-8"
    )
    _commit(root, "near miss")
    code, output = _run_release(root)
    assert code != 0, (
        f"the notes arm accepted {seeded_heading!r} as documenting {TARGET} — its grep is "
        f"not anchored strictly enough:\n{output}"
    )
    assert "RELEASE_NOTES.md" in output


@private_tree.kit
def test_the_notes_arm_does_not_match_a_different_version(tmp_path):
    """``1.21.0`` must not satisfy a request for ``1.2.1`` (dot-escaping / substring)."""
    root = _sandbox(tmp_path, ["1.2.1"], ["1.21.0"])
    code, output = _run_release(root, version="1.2.1")
    assert code != 0, f"the notes arm matched a different version's section:\n{output}"
    assert "RELEASE_NOTES.md" in output


@private_tree.kit
def test_the_changelog_arm_keeps_the_same_strictness(tmp_path):
    """The original arm's anchoring is untouched by the extension."""
    root = _sandbox(tmp_path, [], [TARGET])
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [1.99.0-rc] — 2026-07-29\nseeded\n", encoding="utf-8"
    )
    _commit(root, "near miss")
    code, output = _run_release(root)
    assert code != 0
    assert "CHANGELOG.md" in output


# --------------------------------------------------------------------------- #
# The gate's own documentation must describe BOTH files                         #
# --------------------------------------------------------------------------- #

@private_tree.kit
def test_the_release_script_header_documents_both_files():
    header = RELEASE_SH.read_text(encoding="utf-8").split("set -euo pipefail", 1)[0]
    assert "RELEASE_NOTES.md" in header, (
        "release.sh's header comment still describes gate e as CHANGELOG-only"
    )
    assert "CHANGELOG.md" in header


@private_tree.kit
def test_the_gate_greps_both_files_from_the_repo_root():
    """Both arms read the repo root — not the caller's cwd."""
    source = RELEASE_SH.read_text(encoding="utf-8")
    for filename in ("CHANGELOG.md", "RELEASE_NOTES.md"):
        assert re.search(
            rf'grep -qE "\^## \\\[\$NUM_RE\\\]" "\$REPO_ROOT/{filename}"', source
        ), f"the {filename} arm does not grep an anchored section at $REPO_ROOT"


# --------------------------------------------------------------------------- #
# LD-169 — THE CUT-STATE ORDERING EXERCISE: the guard and gate e must be         #
# satisfiable AT THE SAME TIME. This is the integration that was never run.      #
# --------------------------------------------------------------------------- #
#
# The deadlock this pins closed: gate b (the whole suite) runs BEFORE the version bump, so
# during a cut the documents necessarily carry one section AHEAD of the packaged version —
# exactly the state gate e demands and exactly the state the old guard refused. Neither
# LD-164's tests nor its QA could reach it without cutting a real release; these two cases
# reach it in a throwaway repo, on both sides of the boundary.

CUT = "1.1.0"            # the version being cut — one ahead of the sandbox's packaged 1.0.0
PRE_WRITTEN = "1.2.0"    # a SECOND version ahead: pre-writing a release that does not exist


def _cut_state(root):
    """The sandbox's real state as the guard sees it: (authored notes versions, packaged)."""
    lines = (root / "RELEASE_NOTES.md").read_text(encoding="utf-8").splitlines()
    authored = [version for version, _date, _index in section_starts(lines)]
    packaged = packaged_version((root / "pyproject.toml").read_text(encoding="utf-8"))
    return authored, packaged


@private_tree.kit
def test_the_real_cut_state_satisfies_the_guard_AND_both_gate_e_arms(tmp_path):
    """THE ACCEPTANCE SHAPE OF A CUT: next version's sections authored, ``pyproject.toml``
    still at the old version — the guard accepts it **and** the release script walks every
    preflight to "all gates green". A future change to either the guard's ceiling or the
    script's preflight ordering that re-creates the deadlock reddens here.
    """
    root = _sandbox(tmp_path, [CUT, "1.0.0"], [CUT, "1.0.0"])

    authored, packaged = _cut_state(root)
    assert packaged == "1.0.0", "the sandbox must still carry the OLD version at preflight"
    assert CUT in authored, "the cut state must have the next version's section authored"
    assert ahead_refusal(authored, packaged) is None, (
        "the guard refuses the very state gate e requires — the release path is deadlocked "
        f"again: {ahead_refusal(authored, packaged)}"
    )

    code, output = _run_release(root, version=CUT)
    assert code == 0, f"gate e refused the documented cut state:\n{output}"
    assert "all gates green" in output, f"the preflight did not complete:\n{output}"
    assert f"CHANGELOG.md has a ## [{CUT}] section" in output, "the changelog arm did not run"
    assert f"RELEASE_NOTES.md has a ## [{CUT}] section" in output, "the notes arm did not run"
    _unmutated(root)


@private_tree.kit
def test_a_two_ahead_cut_state_is_refused_by_the_guard_inside_the_sandbox(tmp_path):
    """The case bites both ways — and it bites via the REAL rule (imported from
    :mod:`release_versions`, the one seam the shipped guard uses), not a copy of it.

    Note which arm refuses: gate e only asks "is the version being cut documented?", so it
    passes here — **the guard is the only thing standing between the repo and a pre-written
    release**, which is why its ceiling had to be corrected rather than removed.
    """
    root = _sandbox(tmp_path, [PRE_WRITTEN, CUT, "1.0.0"], [PRE_WRITTEN, CUT, "1.0.0"])

    authored, packaged = _cut_state(root)
    refusal = ahead_refusal(authored, packaged)
    assert refusal is not None, (
        f"the guard accepted TWO versions ahead of {packaged} ({authored}) — pre-writing "
        "releases that do not exist is no longer refused"
    )
    assert PRE_WRITTEN in refusal and "at most one" in refusal.lower()

    code, _output = _run_release(root, version=CUT)
    assert code == 0, "gate e is not the arm that catches pre-writing — it must stay unaware"


def test_the_sandbox_case_drives_the_same_rule_the_shipped_guard_uses():
    """A guard proven by a copy of itself proves nothing: pin that both this module and the
    notes guard resolve the rule to the SAME function object.
    """
    import test_release_notes

    assert test_release_notes.ahead_refusal is ahead_refusal
    assert test_release_notes.section_starts is section_starts


# =====================================================================
# LD-210 AC10 — ``release.sh --help`` shows its usage examples
# =====================================================================
#
# ``usage()`` was ``sed -n '2,9p'`` while the five examples live at 10-14, so ``--help``
# rendered a synopsis with NO example at all. Maintainer's call was to widen the window; the AC forbids
# hard-coding ``2,14``, because that is the same defect with a bigger number. So the window is
# DERIVED from the header block, and these tests are what hold it derived.

#: A usage example inside the header comment block, and the line a reader should see.
_USAGE_EXAMPLE_RE = re.compile(r"^#\s+(\./scripts/release\.sh\s.*)$")


def _header_lines(script=RELEASE_SH):
    """The script's leading comment block — everything above the first non-comment line."""
    lines = script.read_text(encoding="utf-8").splitlines()
    end = next(index for index, line in enumerate(lines) if not line.startswith("#"))
    return lines[:end]


def _header_examples(script=RELEASE_SH):
    return [
        match.group(1)
        for line in _header_lines(script)
        if (match := _USAGE_EXAMPLE_RE.match(line))
    ]


def _run_help(script=RELEASE_SH):
    proc = subprocess.run(
        ["bash", str(script), "--help"], capture_output=True, text=True,
        cwd=str(script.parent),
    )
    assert proc.returncode == 0, f"--help exited {proc.returncode}:\n{proc.stderr[-2000:]}"
    return proc.stdout


@private_tree.kit
def test_the_header_really_carries_usage_examples_to_show():
    """The premise, asserted so the two tests below cannot pass vacuously by the examples
    being deleted from the header instead of shown in ``--help``."""
    examples = _header_examples()
    assert len(examples) >= 5, f"release.sh's header lost its usage examples: {examples}"


@private_tree.kit
def test_release_sh_help_RENDERS_every_usage_example():
    """AC10. ``--help`` is where a reader learns ``--dry-run`` and ``--publish-only`` exist at
    all; a synopsis with the examples cut out sends them to open the script."""
    rendered = _run_help()
    missing = [example for example in _header_examples() if example not in rendered]
    assert not missing, (
        f"release.sh --help renders no usage example for {missing} — the help window stops "
        f"short of the header's examples"
    )


@private_tree.kit
def test_the_help_window_is_DERIVED_so_a_SIXTH_example_cannot_fall_outside_it(tmp_path):
    """The real AC10 requirement, and the reason a widened literal (``2,14``) would not have
    satisfied it: the window has to be keyed on the header block, so the next example added is
    shown without anybody remembering to move a number.

    Driven against a COPY with a sixth example spliced in after the last one — the script
    resolves its own repo root from its location, and ``--help`` exits before any gate, so the
    copy touches nothing.
    """
    original = RELEASE_SH.read_text(encoding="utf-8")
    lines = original.splitlines()
    last_example = max(
        index for index, line in enumerate(_header_lines()) if _USAGE_EXAMPLE_RE.match(line)
    )
    sixth = "#   ./scripts/release.sh 9.9.9 --sixth-example  # spliced in by the AC10 guard"
    lines.insert(last_example + 1, sixth)

    sandbox = tmp_path / "scripts"
    sandbox.mkdir(parents=True)
    copy = sandbox / "release.sh"
    copy.write_text("\n".join(lines) + "\n", encoding="utf-8")
    copy.chmod(0o755)

    rendered = _run_help(copy)
    assert "./scripts/release.sh 9.9.9 --sixth-example" in rendered, (
        "a sixth usage example falls outside the --help window — the window is still keyed on "
        "a literal line number rather than on the header block"
    )
    # …and the widening is bounded: --help stays a synopsis, not the whole 55-line header.
    assert "WHAT IT DOES" not in rendered, (
        "the --help window now swallows the header's WHAT-IT-DOES walkthrough — widened past a "
        "synopsis"
    )
