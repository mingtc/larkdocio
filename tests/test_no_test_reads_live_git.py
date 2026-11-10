"""SUITE-WIDE: no test may build a git invocation against the LIVE repo or working tree.

**The standing rule, and where it is written down.**
``tests/test_mermaid_port_fence.py``'s module docstring records it verbatim — *"a guard that
asserts the shape of a diff — or any other git or working-tree state — must not land on the
trunk; assert the content of the tree instead"*. This file is that rule with the whole test
tree in scope instead of one module.

**The three recurrences it exists to stop.** The defect is not hypothetical and it is not
rare; it is the *natural* thing to write while landing a change, because a diff-scoped
assertion answers "did I stay inside my fence?" precisely — and its failure mode only appears
on somebody else's branch, by which time its author has moved on.

1. ``tests/test_shipped_notes.py::test_ac8_the_shipped_notes_are_documents_not_code`` — caught
   and **rescoped** the first time.
2. The mermaid port's change fence — a live ``git diff <trunk>...HEAD`` plus
   ``git status --porcelain`` — which was true on exactly one branch and then reddened on
   **every** later one, naming that branch's own innocent paths as violations. It was
   **removed**, and the module-scoped scan
   ``test_no_test_here_asks_git_what_changed`` was left behind in its place.
3. That scan was module-scoped, so nothing stopped the *next* file. This is the promotion:
   one definition, the whole of ``tests/**``, and the module-scoped scan is **subsumed** into
   it rather than left standing beside it (two guards asserting one property invite one to be
   weakened while the other silently covers for it).

**What is forbidden, and what is not.** The rule is about **reading live git state**, not
about running programs: ``subprocess`` in a test is fine, and driving a real ``git`` inside a
**throwaway sandbox** is fine — that is what the register entries below do (how many there
are is the dict's business, not this sentence's). What no test
may do is ask git about *this* checkout: which branch is out, what it changed against the
trunk, what is still uncommitted, what the trunk's copy of a file says. Those questions have
no stable answer once the change under review has merged.

**The detection is structural, over the syntax tree**, so prose *about* the forbidden forms —
this docstring names several of them, and the sibling module's docstring quotes the retired
fence's own argv — is never a hit. Its envelope deliberately reaches past the list-literal
spelling the module-scoped version caught, to the four evasions its review named: a **tuple**
argv, a **``shell=True``** string, an **absolute path** (``/usr/bin/git``), and **name
indirection** (``G = "git"``) — plus the fifth this promotion added, **the composition of
them** (a tuple built through indirection), and a sixth: an invocation whose *program* is a
variable holding an absolute path.
"""
import ast
import re
import pathlib
import textwrap

REPO = pathlib.Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"

#: Callables that actually *invoke* a program. Membership here is what separates "builds a
#: git command line" from merely naming git: ``shutil.which("git")`` asks whether the binary
#: exists (an environment guard, no repository state read) and is not an invocation.
INVOKING = {
    "run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput",
    "system", "popen", "spawnl", "spawnv", "spawnvp", "spawnlp", "execv", "execvp",
}

#: Shell metacharacters a ``shell=True`` string can hide a second command behind.
_SHELL_SPLITS = ("&&", "||", ";", "|", "\n")


# =========================================================================== #
# THE EXEMPTION REGISTER — every entry with its own justification                 #
# =========================================================================== #

#: The **only** sites in ``tests/**`` allowed to build a git command line — this dict is the
#: whole list — named individually: one file *and one function* each, never a directory, a
#: glob or a prefix. The register's whole value is that a further entry has to be **argued in
#: the diff** rather than absorbed by a pattern that happens to match. (No count is written
#: here on purpose: the dict holds it, and the statement that restated it went stale the day
#: the register grew — LD-591 moved it, LD-612 removed the restatement. `staleness.md` § C.)
#: Each key is
#: ``<path relative to tests/>::<enclosing function>``; the line each occupied when this
#: guard landed is recorded in its reason, but the key is the function so that editing the
#: lines above it cannot redden the suite.
EXEMPTIONS = {
    "test_release_gate_notes.py::_git": (
        "HERMETIC SANDBOX, EXPLICIT ROOT. Drives git inside a tmp_path repository the test "
        "itself initialises, addressed by an explicit `git -C <root>` — the live repository "
        "is never the target, and the sandbox also sets its own identity/hooks config so a "
        "developer's global config cannot reach it. (Line 51 when this guard landed.)"
    ),
    "test_consumer_update_wheel_selection.py::_git": (
        "HERMETIC SANDBOX, EXPLICIT ROOT. Drives git inside a tmp_path stand-in dev repo the "
        "test itself initialises (seeded, tagged, and given an orphan publish branch), "
        "addressed by an explicit `git -C <root>` — the live repository is never the target, "
        "and the sandbox sets its own identity/hooks config so a developer's global config "
        "cannot reach it. The consumer script under test is pointed at that sandbox through "
        "its own `LARKDOCIO_REPO_URL` seam, so no call can reach the network either. "
        "(Line 88 when this entry landed.)"
    ),
    "test_capture_sink.py::_git": (
        "HERMETIC SANDBOX, EXPLICIT ROOT. Drives git inside a tmp_path repository the test "
        "itself initialises, addressed by an explicit `git -C <root>`, so that the capture "
        "the LD-620 fence protects is genuinely TRACKED and not merely a file on disk — the "
        "whole claim being that an armed live_write run laundered COMMITTED evidence. The "
        "sandbox sets its own identity, signing and hooks config so a developer's global "
        "config cannot reach it, and the live repository is never the target. Note the module "
        "under test invokes no git at all: `capture_sink` walks for `.git`, precisely so the "
        "fence never asks this checkout a question. (Line 80 when this entry landed.)"
    ),
    "test_shipped_notes.py::_git": (
        "HERMETIC SANDBOX, EXPLICIT CWD. Drives git inside a tmp_path stand-in for the dev "
        "repo (seeded, committed and tagged by the test) through a mandatory keyword-only "
        "`cwd=` — every call names its sandbox, so no call can fall back to the process's "
        "own working directory. (Line 361 when this guard landed.)"
    ),
    "test_reanchor_resolves_the_invoked_tree.py::_git": (
        "HERMETIC SANDBOX, EXPLICIT CWD. Drives git inside a tmp_path repo the test seeds "
        "from this tree's `src` / anchor / script, then adds a WORKTREE of that sandbox — "
        "through a mandatory positional `cwd`, so no call can reach this checkout. LD-622 "
        "defect 4 is only observable inside a real git worktree (the script resolved "
        "`larkdocio` from the main checkout instead of the tree it was invoked in), and the "
        "hazard survives the isolation for free: the interpreter's own editable-install "
        "`.pth` is the foreign tree that used to answer the import. (Line 61 when this "
        "entry landed.)"
    ),
    "git_sandbox.py::git": (
        "HERMETIC SANDBOX, EXPLICIT CWD — and THE ONE DEFINITION the origin/work sandbox "
        "family shares (LD-640; it replaced byte-identical `_git` copies in "
        "`test_finish_pr_truthful_claims.py` and `test_release_readback_claims.py`, and "
        "`test_push_readback_claims.py` already imported one of them). Drives git inside a "
        "tmp_path work repo whose `origin` is a tmp_path BARE repo, both built by the "
        "caller, through a mandatory positional `cwd` — the live repository and the real "
        "`origin` are never targets, and `bootstrap_origin_and_work` sets the sandbox's own "
        "identity/signing/hooks config so a developer's global config cannot reach it. "
        "THE REASONS THE THREE CALLERS NEED IT, preserved rather than collapsed: LD-622's "
        "claim is about what `scripts/finish-pr.sh` PRINTS and RECORDS after a real "
        "squash-merge-and-delete, including a remote that puts a deleted ref back; LD-625's "
        "is about what `scripts/release.sh` PRINTS after a push that is ACCEPTED AND THEN "
        "REVERTED, which needs a remote whose `post-receive` hook can put the ref back and "
        "a real cut to run against it (cutting a real release to test it is forbidden by "
        "that issue's own AC8); and the push-retry arm needs the same remote to observe a "
        "revert AFTER a successful read-back. None of that is readable from the tree, and "
        "all of it needs a remote it is safe to destroy. Moving `cwd` off mandatory is the "
        "way to break this — the module docstring enumerates what else would. "
        "(Line 70 when this entry landed.)"
    ),
}


# =========================================================================== #
# THE SCAN                                                                      #
# =========================================================================== #

class Invocation:
    """One git command line found in a source file: where it is, and how it was spelled."""

    def __init__(self, path, lineno, form, function):
        self.path = path
        self.lineno = lineno
        self.form = form
        self.function = function

    @property
    def key(self):
        return f"{self.path}::{self.function}"

    def __repr__(self):
        return f"{self.path}:{self.lineno} ({self.form}, in {self.function or '<module>'})"


def _is_git_program(value):
    """Is ``value`` a reference to the git binary — by bare name or by any path to it?

    The basename is compared **exactly**, so ``.gitignore``, ``git-history.md`` and a URL
    ending in ``/larkdocio.git`` are not programs.
    """
    if not isinstance(value, str) or not value.strip():
        return False
    tail = value.replace("\\", "/").rsplit("/", 1)[-1]
    if tail.endswith(".exe"):
        tail = tail[:-4]
    return tail == "git"


def _shell_string_runs_git(value):
    """Does a ``shell=True`` string start a git command — first, or after a shell operator?"""
    if not isinstance(value, str):
        return False
    text = value
    for sep in _SHELL_SPLITS:
        text = text.replace(sep, "\n")
    for segment in text.split("\n"):
        words = segment.split()
        while words and "=" in words[0] and not words[0].startswith("-"):
            words = words[1:]          # a leading VAR=value environment assignment
        if words and _is_git_program(words[0]):
            return True
    return False


def _string_env(tree):
    """``{name: {possible string values}}`` for plain string assignments in the module.

    This is what closes the **name-indirection** evasion: ``G = "git"`` followed by
    ``[G, "diff", …]`` builds the same command line as the literal did, and a scan that only
    looked at constants would walk straight past it.
    """
    env = {}
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        if not targets or node.value is None:
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in targets:
                if isinstance(target, ast.Name):
                    env.setdefault(target.id, set()).add(node.value.value)
    return env


def _strings(node, env):
    """Every string ``node`` could evaluate to, as far as a static reading can tell."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.Name):
        return set(env.get(node.id, ()))
    return set()


def _functions(tree):
    """``[(lineno, end_lineno, name)]`` innermost-last, for attributing a hit to its site."""
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spans.append((node.lineno, node.end_lineno or node.lineno, node.name))
    return spans


def _enclosing(spans, lineno):
    inner = [name for start, end, name in spans if start <= lineno <= end]
    return inner[-1] if inner else ""


def git_invocations(source, path="<string>"):
    """Every git command line built in ``source``, by any of the spellings in the envelope.

    Structural, not textual: a hit is a **sequence literal whose program is git** or a **call
    to an invoking callable whose program argument is git**. A string that merely mentions
    git — in a docstring, a comment, a URL, a branch name, a path fragment — is a constant in
    the tree and never either of those.
    """
    tree = ast.parse(source)
    env = _string_env(tree)
    spans = _functions(tree)
    found = {}

    def record(lineno, form):
        found.setdefault(lineno, Invocation(path, lineno, form, _enclosing(spans, lineno)))

    for node in ast.walk(tree):
        # (a)/(b) a list OR tuple argv, its program a literal or an indirected name.
        if isinstance(node, (ast.List, ast.Tuple)) and node.elts:
            if any(_is_git_program(v) for v in _strings(node.elts[0], env)):
                form = "list argv" if isinstance(node, ast.List) else "tuple argv"
                record(node.lineno, form)
        # (c)/(d) a call to something that runs a program, its program argument a string.
        if isinstance(node, ast.Call):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else (
                node.func.id if isinstance(node.func, ast.Name) else "")
            if name in INVOKING and node.args:
                for value in _strings(node.args[0], env):
                    if _is_git_program(value) or _shell_string_runs_git(value):
                        record(node.lineno, "string command")
                        break
    return sorted(found.values(), key=lambda hit: hit.lineno)


def scan_tree(root):
    """Every git command line under ``root``, over **all** ``*.py`` — modules and helpers."""
    hits = []
    for path in sorted(pathlib.Path(root).rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        hits.extend(git_invocations(path.read_text(encoding="utf-8"), rel))
    return hits


def unexempted(hits):
    return [hit for hit in hits if hit.key not in EXEMPTIONS]


def _explicit_root_lines(source):
    """Lines of git calls that name their repository explicitly (``cwd=`` or ``git -C``).

    Used to check the register's *justification* structurally rather than take its word.
    """
    tree = ast.parse(source)
    env = _string_env(tree)
    lines = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if any(kw.arg == "cwd" for kw in node.keywords):
            lines.add(node.lineno)
        for arg in node.args:
            if isinstance(arg, (ast.List, ast.Tuple)) and arg.elts:
                if any(_is_git_program(v) for v in _strings(arg.elts[0], env)) and any(
                        "-C" in _strings(elt, env) for elt in arg.elts):
                    lines.add(node.lineno)
    return lines


# =========================================================================== #
# AC1 + AC7 — the suite-wide property, and the number re-derived                 #
# =========================================================================== #

def test_NO_test_in_the_whole_suite_reads_live_git_state():
    """The rule itself, over the whole of ``tests/**``.

    A test that shells out to git against *this* checkout is asserting something about a
    branch, not about the repository: it is true while the change is under review and false
    forever after. Assert the content of the tree instead — as every other guard in this
    suite does.
    """
    offenders = unexempted(scan_tree(TESTS))
    assert not offenders, (
        "these test sites build a git command line against the live repository or working "
        "tree:\n" + "\n".join(
            f"  tests/{hit.path}:{hit.lineno} — {hit.form} in "
            f"{hit.function or '<module>'}()" for hit in offenders
        ) + "\n\nAssert the content of the tree instead of the state of a checkout (see this "
            "module's docstring). If the site genuinely drives git inside a HERMETIC "
            "SANDBOX with an explicit root/cwd, argue it into EXEMPTIONS — and expect the "
            "counted assertion to make that argument visible in the diff."
    )


def test_the_zero_sites_claim_is_MEASURED_not_assumed():
    """AC7: re-derive the number rather than trust the review that predicted it.

    Every git-invoking site in ``tests/**`` is registered in :data:`EXEMPTIONS`; everything
    else reads the tree. **The count is not written in this sentence.** It is asserted below,
    off the register itself — because this docstring restated it four times in four months and
    the restatement is what went stale (LD-591, LD-620, LD-622, LD-625 each moved it; the
    self-contradiction LD-628 found — *"exactly six … if a fifth has appeared"* — is what a
    retyped cross-reference does, `process/doctrine/staleness.md` § C). If a further site has
    appeared, the site gets fixed — not the register widened.

    **The number moved from two to three at LD-591**, and the move is the point of asserting
    it: the third site (``test_consumer_update_wheel_selection.py``) drives the consumer
    vendoring script the only way its defect is observable — a real run against a stand-in
    dev repo — so it is the same hermetic-sandbox argument the other two make, and it had to
    be made in the diff rather than absorbed silently. **It moved from three to four at
    LD-620** on the same terms: the capture fence's claim is that an armed ``live_write`` run
    laundered a **committed** capture, and a sandbox whose file was never committed would
    demonstrate a weaker thing than the one that happened four times. **It moved from four to
    six at LD-622**, and on the same terms twice over: that issue's two defects are claims a
    script PRINTS and RECORDS (a remote-delete confirmation, a squash subject) and a tree a
    script RESOLVES inside a worktree — neither readable from the tree, both needing a real
    remote and a real worktree, and both built in ``tmp_path``. **It moved from six to seven at
    LD-625**, on the narrowest version of that argument yet: what ``release.sh`` prints for a push
    that is ACCEPTED AND THEN REVERTED needs a remote whose ``post-receive`` hook can put the ref
    back, and the one alternative — cutting a real release — is forbidden by that issue's own AC8.
    The rule is unchanged: a site that reads THIS checkout is still a defect, and the register is
    not a place to put one.
    """
    hits = scan_tree(TESTS)
    # DERIVED, not retyped: the register is the one statement of the number (its own arity is
    # pinned by ``test_the_register_has_EXACTLY_the_argued_entries`` below), and this compares
    # the scan against it. A second git call inside an already-exempt function still reddens
    # here, because keys are per-function and ``len(hits)`` counts invocations.
    assert len(hits) == len(EXEMPTIONS), (
        f"the suite has {len(hits)} git-invoking sites against {len(EXEMPTIONS)} registered "
        f"entries: {hits}")
    assert {hit.key for hit in hits} == set(EXEMPTIONS), {hit.key for hit in hits}


#: Ceiling on the scan's **own CPU cost per byte of source it parses** — a bound on
#: ``scan_tree``'s efficiency, deliberately NOT on how long the suite waited for a core.
#: Cut 2026-08-26 (LD-584) at ~3.5x the cost measured on the host that cut it: 0.276 us/byte
#: quiet and 0.283-0.290 us/byte while the full ``-n auto`` suite saturated the same machine
#: (Apple Silicon, CPython 3.14.6) — i.e. the measure moved ~5% across a load range in which
#: wall clock moved ~20% and crossed the old 5.0 s bound three times in four.
#: What would legitimately move it: a host materially slower per byte than that one (the
#: headroom is sized for ~3x), or CPython's own ``ast.parse`` getting slower. What must NOT
#: move it: a busy machine, an xdist worker count, or a bigger ``tests/`` tree — the first two
#: are excluded by construction and the third divides out.
MAX_SCAN_CPU_MICROSECONDS_PER_BYTE = 1.0


def test_the_scan_over_the_whole_tree_stays_NEGLIGIBLE_PER_BYTE_OF_CPU():
    """It parses every test file on every run of the suite, so its cost is part of the deal.

    That reason is LD-201's and is unchanged: this guard must stay cheap enough to live in
    the suite. **The instrument was re-cut on 2026-08-26 (LD-584).** It used to be
    ``time.perf_counter()`` elapsed ``< 5.0`` — a wall-clock bound, which on a contended host
    counts every second this process spent *not running*, and so measured machine load rather
    than the scan. It refused landings across several issues on trees whose ``scan_tree`` had
    not changed a byte (a green pre-merge gate and a red post-merge gate minutes apart on the
    same tree). What is asserted now is ``time.process_time()`` — CPU this process actually
    burned, which another process cannot inflate — divided by the bytes of source actually
    scanned, so the corpus size is derived here rather than frozen as a literal.

    **The limit, named beside the guarantee:** CPU per byte cannot see a scan that turns slow
    by *waiting* — a network-mounted checkout, a cold page cache, a stalled filesystem — the
    very condition LD-201's QA named; nor can it see the ``tests/`` corpus itself growing
    without bound, since a linear cost divides out. It sees exactly one thing: this scan
    getting more expensive per unit of work it does.
    """
    import time

    corpus = sorted(TESTS.rglob("*.py"))
    scanned_bytes = sum(path.stat().st_size for path in corpus)
    assert scanned_bytes > 0, f"no python source found under {TESTS} to scan"

    start = time.process_time()
    scan_tree(TESTS)
    cpu_seconds = time.process_time() - start

    per_byte = cpu_seconds / scanned_bytes * 1e6
    assert per_byte < MAX_SCAN_CPU_MICROSECONDS_PER_BYTE, (
        f"the suite-wide scan burned {cpu_seconds:.2f}s of CPU over {len(corpus)} files / "
        f"{scanned_bytes} bytes = {per_byte:.3f} us/byte, above the "
        f"{MAX_SCAN_CPU_MICROSECONDS_PER_BYTE} us/byte ceiling. This is CPU, not wall clock, "
        f"so a busy machine did not cause it: the scan itself got more expensive per byte."
    )


# =========================================================================== #
# AC2 — the register: every entry justified, and a whitelist rather than a        #
#       pattern that happens to match them                                      #
# =========================================================================== #

def test_the_register_has_EXACTLY_the_argued_entries_each_with_a_real_reason():
    # The ONE place the number is written down, and deliberately a literal: widening the
    # register has to show up as a changed digit in this diff (LD-242's enrol-by-argument
    # doctrine). Everything else derives from ``len(EXEMPTIONS)``.
    assert len(EXEMPTIONS) == 6, (
        "the exemption register grew. A further site is a finding, not a line to add: fix the "
        f"site, or argue it here on the record. {sorted(EXEMPTIONS)}")
    for key, reason in EXEMPTIONS.items():
        assert "::" in key, f"{key} is not a file-and-function entry"
        assert not key.endswith("/") and "*" not in key, (
            f"{key} is a directory or glob exemption; entries are individual sites")
        assert len(reason) > 80 and "SANDBOX" in reason, (
            f"{key} is exempted without its hermetic justification")


def test_each_exempted_site_REALLY_IS_hermetic_and_takes_an_explicit_root():
    """The justification checked structurally, not taken on trust: each exempted site's own
    call must name its repository (``cwd=`` or ``git -C <root>``)."""
    for key in EXEMPTIONS:
        rel, function = key.split("::")
        source = (TESTS / rel).read_text(encoding="utf-8")
        sites = [hit for hit in git_invocations(source, rel) if hit.function == function]
        assert sites, f"{key} is registered but has no git invocation — a stale exemption"
        rooted = _explicit_root_lines(source)
        for hit in sites:
            assert hit.lineno in rooted, (
                f"{key} line {hit.lineno} runs git without naming its repository, so the "
                f"register's hermetic justification is not true of it")


def test_a_THIRD_git_invoking_test_is_REJECTED_not_absorbed(tmp_path):
    """The register is a whitelist of named sites, not a pattern that happens to match them.

    A sandbox tree carrying exempted files *and* an UNREGISTERED git-invoking test: only the
    unregistered one is reported, and it is reported by file and line.
    """
    (tmp_path / "test_release_gate_notes.py").write_text(
        'import subprocess\n\n\ndef _git(root, *args):\n'
        '    subprocess.run(["git", "-C", str(root), *args])\n', encoding="utf-8")
    (tmp_path / "test_shipped_notes.py").write_text(
        'import subprocess\n\n\ndef _git(*args, cwd):\n'
        '    return subprocess.run(["git", *args], cwd=str(cwd))\n', encoding="utf-8")
    (tmp_path / "test_a_brand_new_fence.py").write_text(
        'import subprocess\n\n\ndef test_my_change_stayed_in_its_fence():\n'
        '    changed = subprocess.run(\n'
        '        ["git", "diff", "--name-only", "origin/develop...HEAD"],\n'
        '        capture_output=True, text=True).stdout\n'
        '    assert changed\n', encoding="utf-8")

    offenders = unexempted(scan_tree(tmp_path))
    assert [(hit.path, hit.lineno) for hit in offenders] == [
        ("test_a_brand_new_fence.py", 6)], offenders
    assert offenders[0].function == "test_my_change_stayed_in_its_fence"


def test_the_failure_MESSAGE_names_the_file_and_the_line(tmp_path):
    """A suite-wide scan that said only "something reads git" would be worse than the
    module-scoped one it replaces."""
    (tmp_path / "test_planted.py").write_text(
        'import subprocess\n\n\ndef test_x():\n'
        '    subprocess.run(["git", "status", "--porcelain"])\n', encoding="utf-8")
    offenders = unexempted(scan_tree(tmp_path))
    message = "\n".join(
        f"  tests/{hit.path}:{hit.lineno} — {hit.form}" for hit in offenders)
    assert "test_planted.py:5" in message, message


# =========================================================================== #
# AC3 — the widened envelope: one independent RED proof per evasion              #
# =========================================================================== #

def _hit_lines(sample):
    return [hit.lineno for hit in git_invocations(textwrap.dedent(sample))]


def test_evasion_a_a_TUPLE_argv_is_caught():
    assert _hit_lines(
        """
        import subprocess

        def _ask():
            return subprocess.run(("git", "rev-parse", "HEAD"), capture_output=True)
        """
    ) == [5]


def test_evasion_b_a_SHELL_TRUE_string_is_caught():
    assert _hit_lines(
        """
        import subprocess

        def _ask():
            return subprocess.run("git status --porcelain", shell=True, text=True)
        """
    ) == [5]
    # …and hidden behind a shell operator, which is the same evasion one step along.
    assert _hit_lines(
        """
        import subprocess

        def _ask():
            return subprocess.check_output("cd .. && git log -1", shell=True)
        """
    ) == [5]


def test_evasion_c_an_ABSOLUTE_PATH_to_git_is_caught():
    assert _hit_lines(
        """
        import subprocess

        def _ask():
            return subprocess.run(["/usr/bin/git", "diff", "--stat"])
        """
    ) == [5]
    # …and the same absolute path held in a variable.
    assert _hit_lines(
        """
        import subprocess

        GIT = "/usr/local/bin/git"

        def _ask():
            return subprocess.run([GIT, "status"])
        """
    ) == [7]


def test_evasion_d_NAME_INDIRECTION_is_caught():
    assert _hit_lines(
        """
        import subprocess

        G = "git"

        def _ask():
            return subprocess.run([G, "diff", "--name-only", "origin/develop...HEAD"])
        """
    ) == [7]


def test_evasion_e_THE_COMPOSITION_of_them_is_caught():
    """A partial implementation can catch each simple form and still miss the combination:
    an absolute path, held in a variable, in a tuple argv, run through a renamed wrapper."""
    assert _hit_lines(
        """
        import subprocess as sp

        _PROGRAM = "/usr/bin/git"

        def _repo_state(*args):
            return sp.check_output((_PROGRAM, "status", "--porcelain", *args), text=True)
        """
    ) == [7]


def test_evasion_f_a_RENAMED_WRAPPER_cannot_hide_the_argv():
    """The fifth form this promotion added past the four the review named: the argv is a
    sequence whose program is git whatever the helper around it is called, and whether or not
    it is passed to the call directly."""
    assert _hit_lines(
        """
        ARGV = ["git", "for-each-ref", "--format=%(refname)"]

        def _refs(runner):
            return runner(ARGV)
        """
    ) == [2]


# =========================================================================== #
# AC4 — the must-not-bite arm, or the guard is unlivable                        #
# =========================================================================== #

def test_it_does_not_bite_THIS_MODULE_which_necessarily_DESCRIBES_the_forms():
    """The guard's own docstring names a tuple argv, a ``shell=True`` string, an absolute
    ``/usr/bin/git`` and ``G = "git"``. A textual scan would flag its own explanation."""
    assert git_invocations(
        pathlib.Path(__file__).read_text(encoding="utf-8"), "self") == []


def test_it_does_not_bite_the_SIBLING_docstring_that_records_the_SAME_LESSON():
    """``test_mermaid_port_fence.py`` tells the story of the retired fence and quotes the
    argv it built. Prose about a rule must never be a violation of it."""
    sibling = TESTS / "test_mermaid_port_fence.py"
    assert git_invocations(sibling.read_text(encoding="utf-8"), sibling.name) == []
    assert "git diff" in sibling.read_text(encoding="utf-8"), (
        "the must-not-bite proof is vacuous unless that docstring really does name the argv")


def test_it_does_not_bite_the_EXEMPTED_FILES_beyond_their_registered_sites():
    """Each exempted file gets its one registered site and nothing else."""
    for key in EXEMPTIONS:
        rel = key.split("::")[0]
        hits = git_invocations((TESTS / rel).read_text(encoding="utf-8"), rel)
        assert [hit.key for hit in hits] == [key], hits


def test_it_does_not_bite_SUBPROCESS_USED_FOR_SOMETHING_ELSE():
    """The rule is about reading live git state, not about running programs."""
    assert _hit_lines(
        """
        import subprocess
        import sys

        def test_determinism():
            out = subprocess.run([sys.executable, "-c", "print(1)"], capture_output=True)
            assert out.returncode == 0

        def test_the_build_runs():
            subprocess.run([sys.executable, "-m", "build"], check=True)
        """
    ) == []


def test_it_does_not_bite_the_WORD_GIT_in_a_NON_INVOCATION_context():
    """A URL, a branch name, a path fragment, a config key, an ignore file, a prose mention —
    every one of them a string that names git and invokes nothing."""
    assert _hit_lines(
        """
        URL = "https://example.invalid/team/larkdocio.git"
        TRUNK = "origin/develop"
        BRANCH = "fix/LD-201-no-test-reads-live-git"
        IGNORE = ".gitignore"
        HOOKS = "core.hooksPath"
        DOC = "the git history records the rescope"
        PATHS = [".gitignore", ".github/workflows/ci.yml"]

        def test_prose():
            '''Mentions git diff, git status --porcelain and ["git", "log"] in prose.'''
            assert URL.endswith(".git") and IGNORE == ".gitignore"
        """
    ) == []


def test_it_does_not_bite_an_ENVIRONMENT_GUARD_that_only_ASKS_IF_GIT_EXISTS():
    """``shutil.which("git")`` reads no repository state — it asks whether the binary is on
    PATH, which is exactly how a sandboxed test skips cleanly on a machine without git. The
    trunk has such a guard; banning it would force a rewrite of correct code."""
    assert _hit_lines(
        """
        import shutil

        import pytest

        def _require_git():
            if shutil.which("git") is None:
                pytest.skip("git is unavailable")
        """
    ) == []


# =========================================================================== #
# AC5 — the module-scoped predecessor is SUBSUMED, and cannot come back          #
# =========================================================================== #

def test_the_module_scoped_predecessor_is_GONE_and_this_file_is_the_one_definition():
    """AC5, decided: **subsume**. Two guards asserting one property invite one to be weakened
    while the other silently covers for it — and the narrow one's own subject
    (``test_mermaid_port_fence.py``) is covered here by construction, since this scan reads
    every file in the tree including that one.
    """
    source = (TESTS / "test_mermaid_port_fence.py").read_text(encoding="utf-8")
    assert "def test_no_test_here_asks_git_what_changed" not in source, (
        "the module-scoped scan is back beside the suite-wide one; one of them will be "
        "weakened while the other covers for it")
    assert "def git_command_lines" not in source, "its helper is back too"


def test_the_sibling_module_CITES_the_suite_wide_rule_it_handed_off_to():
    """AC6, the other half: a reader who lands on the file where the defect lived must be
    sent to the rule that replaced its local guard."""
    source = (TESTS / "test_mermaid_port_fence.py").read_text(encoding="utf-8")
    assert "test_no_test_reads_live_git" in source, (
        "the module the fence lived in must point at the suite-wide guard")


def test_THIS_guard_records_the_HISTORY_that_motivated_it():
    """AC6: the house pattern — a guard records the failures it exists to prevent, so a
    future author meets the history rather than a bare prohibition."""
    doc = __doc__.lower()
    assert "test_ac8_the_shipped_notes_are_documents_not_code" in __doc__, doc
    assert "assert the content of the tree instead" in doc, doc
    assert "git status --porcelain" in doc and "git diff" in doc, doc
    assert "test_no_test_here_asks_git_what_changed" in __doc__, doc


# =========================================================================== #
# LD-612 G3 — the register's SIZE is derived, dated, or not stated               #
# =========================================================================== #
#
# The register moved from two entries to three at LD-591, and three statements in this very
# module kept saying two: the register comment's "the **only** two sites", the ordinal it
# derives from that count ("a **third** entry has to be argued"), and a test NAME
# (`..._the_TWO_EXEMPTED_FILES_...`) that said TWO while iterating all three keys. That is
# `process/doctrine/staleness.md` § C: a number in a document presenting itself as current is
# **derived, dated, or not stated**.
#
# So the fix is not "write three" — it is to stop restating a number the dict already holds.
# The guards below hold that shape rather than the corrected wording, which is why they
# cannot go stale the next time the register grows.

def _register_comment_block():
    """The register's own ``#:`` comment block — from the banner to ``EXEMPTIONS = {``.

    The banner line itself is deliberately EXCLUDED — it is a section header, and it used to
    state the register's size (LD-628 took the number out of it; the banner had drifted to
    *"exactly six"* against seven entries). The register's arity is asserted, once, by
    :func:`test_the_register_has_EXACTLY_the_argued_entries_each_with_a_real_reason`, whose
    body holds the literal against ``len(EXEMPTIONS)`` — a *checked* number, not a bare one.
    """
    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    end = source.index("EXEMPTIONS = {")
    start = source.rindex("# ====", 0, end)
    banner_end = source.index("#:", start)
    return source[banner_end:end]


#: The quantity and ordinal words a statement of the register's size would use. ``one`` is
#: absent on purpose: "one file *and one function* each" and "one independent RED proof" are
#: ordinary English, not claims about how many entries the dict holds.
_SIZE_WORDS = ("two", "three", "four", "five", "six", "seven", "eight",
               "second", "third", "fourth")


def _size_words_in(text):
    """Every :data:`_SIZE_WORDS` member the text states — ONE definition, three callers
    (the register comment, the section banners, and the red proof that this rule bites)."""
    lowered = text.lower()
    return [word for word in _SIZE_WORDS if re.search(rf"\b{word}\b", lowered)]


def test_the_register_comment_states_no_bare_COUNT_of_its_own_size():
    """The comment above ``EXEMPTIONS`` may not restate how many entries the dict holds, nor
    an ordinal derived from that count — the dict is the count.

    ("one file *and one function* each" is not a size claim and stays: what is forbidden is a
    quantity word for the register's membership and the ordinal of the next entry.)
    """
    offenders = _size_words_in(_register_comment_block())
    assert not offenders, (
        f"the register comment restates its own size ({offenders}); it goes stale the next "
        "time the register grows — say it without a number, or derive it. See "
        "process/doctrine/staleness.md § C.")


def _section_banner_titles():
    """The title lines of this module's ``# ====`` section banners — the ruler lines and the
    prose paragraphs below them excluded, since only the titles present themselves as a
    heading a reader trusts without checking."""
    titles, inside = [], False
    for line in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines():
        if line.startswith("# ===="):
            inside = not inside
        elif inside and line.startswith("#"):
            titles.append(line)
    return titles


def test_no_SECTION_BANNER_here_states_the_registers_size_either():
    """AC0b (LD-640) — the register-comment guard above was not the only statement of the
    count. The ``AC2`` section banner hand-typed *"the register: exactly seven"*: true the day
    it was written, one edit from being a lie, and invisible to a guard that read only the
    ``#:`` block above ``EXEMPTIONS``. So the same rule now covers the headings too.

    LD-628 removed the number from the register's OWN banner (it had drifted to *"exactly
    six"* against seven entries) and this arm is why the AC2 banner cannot repeat that.
    """
    offenders = {title.strip(): _size_words_in(title)
                 for title in _section_banner_titles() if _size_words_in(title)}
    assert not offenders, (
        f"a section banner states a count of its own: {offenders}. A heading is the text a "
        "reader trusts WITHOUT checking, so it is the worst place to keep a number — say it "
        "without one, or let the assertion below it carry the figure. "
        "See process/doctrine/staleness.md § C.")


def test_the_size_word_rule_BITES_a_banner_that_states_a_count():
    """The anti-vacuity arm for the two live-corpus guards above: each reads a corpus that is
    currently clean, so on its own each is a claim that cannot fail. This one proves the rule
    discriminates, on synthetic text — must-bite and must-not-bite in the same test.
    """
    assert _size_words_in("# AC2 — the register: exactly seven, justified") == ["seven"]
    assert _size_words_in("#: a third entry has to be argued in the diff") == ["third"]
    assert _size_words_in("#: named individually: one file and one function each") == []
    assert _size_words_in("# AC3 — one independent RED proof per evasion") == []


#: A count word in a test NAME, as a whole ``_``-delimited token. "one" is excluded on
#: purpose: it is ordinary English in a name ("the one definition"), not a claim about how
#: many entries the register holds.
_COUNTED_NAME = re.compile(r"(?i)(?:^|_)(two|three|four|five|six|seven|eight)(?:$|_)")


def _names_stating_an_unheld_count(source):
    """Top-level test names in ``source`` that state a count **nothing in their own body
    holds them to**.

    Parameterised over the source text rather than reading ``__file__``, which is the whole
    reason the arm below can prove the rule bites: this module's live population is currently
    EMPTY (see :func:`test_no_test_NAME_here_hard_codes_a_count_it_does_not_assert`).
    """
    offenders = []
    for node in ast.parse(source).body:
        if not isinstance(node, ast.FunctionDef) or not _COUNTED_NAME.search(node.name):
            continue
        body = ast.dump(node)
        if "id='EXEMPTIONS'" not in body or "id='len'" not in body:
            offenders.append(node.name)
    return offenders


def test_no_test_NAME_here_hard_codes_a_count_it_does_not_assert():
    """A count word in a test *name* is allowed only when that test's body asserts the count
    against ``len(EXEMPTIONS)``.

    A name like ``test_the_register_has_EXACTLY_SIX_entries...`` qualified, because its body
    asserted the count against ``len(EXEMPTIONS)`` — LD-628 dropped the count word from that
    name anyway, so it no longer states one to be held to. The old
    ``test_it_does_not_bite_the_TWO_EXEMPTED_FILES_beyond_their_registered_sites`` did not: it
    iterated all three keys while its name said TWO, so nothing held the name to anything.

    **THIS GUARD'S LIVE POPULATION IS EMPTY, AND THAT IS RECORDED HERE RATHER THAN HIDDEN.**
    Dropping that count word took the last candidate name with it (1 → 0), so the rule kept
    passing — on nothing. *When you remove the last member of a corpus-driven guard's
    population, the guard does not fail; it goes quiet.* The remedy taken (LD-640 AC0a, and
    `D-116`'s second ruling: a corpus-driven negative guard owes a positive binding) is the
    synthetic red proof in
    :func:`test_the_unheld_count_rule_BITES_a_name_nothing_holds_to_it` — which is what keeps
    this arm meaningful while the population is empty, and must not be deleted with it.
    """
    offenders = _names_stating_an_unheld_count(
        pathlib.Path(__file__).read_text(encoding="utf-8"))
    assert not offenders, (
        f"these test names state a count nothing holds them to: {offenders}. Either assert "
        "the count against len(EXEMPTIONS) in the body, or leave the number out of the name.")


def test_the_unheld_count_rule_BITES_a_name_nothing_holds_to_it():
    """The positive binding for the arm above, on a synthetic module: a count word in a name
    is caught when the body does not check it, and NOT caught when the body does.

    Both directions in one place on purpose — a must-bite arm without its must-not-bite twin
    is how a rule this cheap starts crying wolf on ordinary prose in a name.
    """
    synthetic = (
        "def test_the_register_has_EXACTLY_SIX_entries():\n"
        "    assert len(EXEMPTIONS) == 6\n"
        "\n\n"
        "def test_it_does_not_bite_the_TWO_EXEMPTED_FILES():\n"
        "    for key in EXEMPTIONS:\n"
        "        assert key\n"
        "\n\n"
        "def test_the_one_definition_is_the_only_definition():\n"
        "    assert True\n"
    )
    assert _names_stating_an_unheld_count(synthetic) == [
        "test_it_does_not_bite_the_TWO_EXEMPTED_FILES"], (
        "the rule no longer discriminates: the SIX name checks its count against "
        "len(EXEMPTIONS) and must pass, the TWO name checks nothing and must be caught, and "
        '"one" in a name is ordinary English and must never be caught.')


def test_the_statements_that_are_ALREADY_CORRECT_are_still_there():
    """AC3b, checked rather than assumed: a fix that corrects the stale statements must not
    quietly take the correct ones with it.

    **THIS GUARD WAS VACUOUS AND LD-628 FIXED THAT FIRST.** It grepped its own module for its
    needle list — and the needle list lives in this function, so every needle matched itself.
    So the corpus is now the module **with this function's own source removed**, which is the
    only way the question "is that statement still there?" can be answered by this file at
    all. That is the same defect as the counts around it: a claim that cannot be false is not
    a check.

    **What it was green over, re-measured (LD-640 AC0c) rather than restated.** LD-628's own
    account of this said all four of its then-needles *"had been gone from the module for two
    issues"*; re-measured against ``origin/develop`` just before that change, that was true of three
    of them (*"assert len(hits) == 6"*, *"no longer six"*, and a test name renamed twice
    since) and **not** of *"exactly six entries"*, which was still sitting in the register's
    section banner at line 63 — the one needle a working guard would have found. Corrected
    here rather than dropped, because *which* claims a vacuous guard was blind to is the fact
    that makes the vacuity legible.

    **And the needles no longer restate a count.** They name the SHAPES that must survive —
    the derived comparison, the one deliberate literal, and one *"two"* that is about something
    else entirely and must not be "corrected" by a future count sweep.
    """
    import inspect

    source = pathlib.Path(__file__).read_text(encoding="utf-8")
    own = inspect.getsource(test_the_statements_that_are_ALREADY_CORRECT_are_still_there)
    assert own in source
    corpus = source.replace(own, "")
    for fragment in (
        "assert len(hits) == len(EXEMPTIONS)",          # the AC1 count assertion, DERIVED
        "assert len(EXEMPTIONS) == 6",                  # the ONE literal, kept in the diff
        "two guards asserting one property",            # a DIFFERENT two — not to be "fixed"
    ):
        assert fragment in corpus, f"an already-correct statement was lost: {fragment!r}"
