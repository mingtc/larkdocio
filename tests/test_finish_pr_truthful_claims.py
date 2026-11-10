"""LD-622 defects 2 and 3 — two claims ``scripts/finish-pr.sh`` made that it had not
established, both of which reach the **permanent** record (the squash commit and the board
note) rather than a scrollback an operator can re-read.

Same class as LD-616's false ``board-drift: clean ✓`` and the ``dist`` republish that
reports success and reverts: *an instrument asserting something it never established.*

**Defect 2 — a delete "confirmed gone" that a later reader measures present.**
``:417`` printed *"Deleted remote branch … (confirmed gone by ls-remote)"* and ``:447``
composed *"branch deleted (confirmed gone)"*. Measured false three times on 2026-09-02
(LD-618's, LD-620's and LD-621's QA legs each re-deleted the ref by hand).

WHICH PATH WAS LYING: **neither measurement — the WORDING.** ``:447``'s clause is derived
from ``:417``'s arm, and that arm really does re-measure with ``ls-remote``. But the read
is taken **~0 seconds after the push**, and this repo has already forensically established
(``process/GIT-HOSTING.md`` § 8.2, LD-542, reproduced three times by two observers) that
an external mirror **restores deleted refs at their original SHA 3–8 minutes later**. So a
true instantaneous measurement was written up as a **timeless, unqualified claim** — and
the permanent board note is the worse of the two, because it is read hours later, by which
time the ref is back and the note reads as a lie. Waiting out the window is not the fix
either: GIT-HOSTING's standing rule is *delete once, record it, never loop on re-deletes.*
So the confirmation is kept and **scoped to what was actually measured** — the elapsed
time is stated, the un-re-checked remainder is stated, and the residue hazard is named.
Deleting the message instead would be the same defect one step quieter (AC3).

**AMENDED BY LD-635 (AC4b) — the same defect, one verb over.** LD-622's scoping kept the
lead verb *"Deleted remote branch"*, which asserts an **achieved, durable** state from a read
taken **inside the window that state has to outlast**. Measured **three for three on
2026-09-03**: LD-627, LD-638 and LD-637 each read the ref empty at ~T+6s and each found it
back afterwards (two of those QA legs re-deleted **once** and read back empty, correctly,
without looping). The fix is neither a sleep nor a retry — that is precisely what LD-635's
AC1/AC4 forbid for ``push`` — but the **claim matching the measurement**: *the delete was
ACCEPTED and ls-remote read the ref EMPTY at T+Ns, inside the restoration window, not
re-checked since* (§ 8.2). An honest scoped claim beats a confident wrong one. The reason
above is unchanged and still binding; only the wording it produced is superseded.

**Defect 3 — the squash subject was composed from the TRUNK's copy of the issue.**
``:196`` read ``title:`` out of ``$SRC``, which resolves inside ``.kanban-wt`` — the trunk
copy — so LD-620's permanent commit subject said *"third occurrence"* while the branch's
own issue body said **fourth**, and LD-518's carried a stale ``PARKED — `` prefix. The
commit outlives the board file, so the record disagreed with the work it records. The
divergence between the two copies **is** the bug, which is why the test below gives trunk
and branch **different** titles: a same-title test would pass vacuously (AC4).

Both are exercised against a THROWAWAY sandbox — a work repo whose ``origin`` is a local
bare repo, seeded with a minimal board and the scripts-under-test copied in so they resolve
the sandbox as their root. Never the real board, never the real ``origin``. This mirrors
``scripts/test/run.sh``'s isolation, but lives in ``tests/**`` because that harness is
deliberately not wired into ``pytest``/``verify.sh`` and AC5 requires a guard that reddens
in the suite every role already runs.
"""
import os
import subprocess

import pytest

# LD-640: the sandbox bootstrap is imported, not forked. ``git`` keeps the live-repo safety
# invariant at its one definition (a mandatory ``cwd``); see git_sandbox.py's module docstring.
from git_sandbox import REPO_ROOT, SCRIPTS, bootstrap_origin_and_work, copy_scripts_into
from git_sandbox import git as _git
import private_tree  # noqa: E402  (LD-685)

STATUS_FOLDERS = ("todo", "in_progress", "dev_complete", "qa_complete", "blocked", "done")


class Sandbox:
    """A disposable work repo + bare ``origin``, with a seeded board."""

    def __init__(self, root):
        self.root = root
        self.origin = root / "origin.git"
        self.work = root / "work"

    def build(self):
        bootstrap_origin_and_work(self.root, self.origin, self.work)
        copy_scripts_into(self.work)

        for folder in STATUS_FOLDERS:
            (self.work / "progress" / folder).mkdir(parents=True)
            (self.work / "progress" / folder / ".gitkeep").write_text("", encoding="utf-8")
        (self.work / "ARCHIVE.md").write_text(
            "# ARCHIVE.md — condensed index of completed issues\n\n## Archived\n",
            encoding="utf-8")
        return self

    # -- board seeding ------------------------------------------------------ #
    def issue_path(self, folder, issue_id, slug):
        return self.work / "progress" / folder / f"{issue_id}-{slug}.md"

    def seed_issue(self, folder, issue_id, slug, title, branch):
        self.issue_path(folder, issue_id, slug).write_text(
            f"---\nid: {issue_id}\ntype: bug\ntitle: {title}\nbranch: {branch}\n"
            "created_at: 2026-09-02\ncreated_by: maintainer\n---\n\n"
            f"# {issue_id} — {title}\n\n## Activity\n\n"
            "- 2026-09-02 [PM] Seeded for the LD-622 sandbox guard.\n",
            encoding="utf-8")

    def publish(self):
        _git(self.work, "add", "-A")
        _git(self.work, "commit", "-m", "[PM] seed sandbox board", "--quiet")
        _git(self.work, "remote", "add", "origin", str(self.origin))
        _git(self.work, "push", "-u", "origin", "develop", "--quiet")
        _git(self.work, "remote", "set-head", "origin", "develop")

    def feature_branch(self, branch, *, filename, edits=()):
        _git(self.work, "checkout", "-b", branch, "develop", "--quiet")
        (self.work / filename).write_text("a real change\n", encoding="utf-8")
        for path, before, after in edits:
            target = self.work / path
            text = target.read_text(encoding="utf-8")
            assert before in text, f"sandbox edit anchor missing in {path}"
            target.write_text(text.replace(before, after), encoding="utf-8")
        _git(self.work, "add", "-A")
        _git(self.work, "commit", "-m", "[Dev] sandbox: a real change", "--quiet")
        _git(self.work, "push", "-u", "origin", branch, "--quiet")
        tip = _git(self.work, "rev-parse", branch).stdout.strip()
        _git(self.work, "checkout", "develop", "--quiet")
        return tip

    # -- running + reading back --------------------------------------------- #
    def finish_pr(self, issue_id, *extra):
        env = os.environ.copy()
        env.update({"FINISH_PR_TEST_ALLOW_STUB": "1",
                    "FINISH_PR_VERIFY_CMD": "true",
                    "FINISH_PR_PREMERGE_CMD": "true"})
        return subprocess.run(
            ["bash", str(self.work / "scripts" / "finish-pr.sh"), issue_id, *extra],
            cwd=str(self.work), capture_output=True, text=True, env=env, timeout=300,
        )

    def origin_show(self, path):
        _git(self.work, "fetch", "origin", "develop", "--quiet")
        return _git(self.work, "show", f"origin/develop:{path}").stdout

    def origin_subjects(self):
        _git(self.work, "fetch", "origin", "develop", "--quiet")
        return _git(self.work, "log", "origin/develop", "--format=%s").stdout

    def ls_remote(self, branch):
        return _git(self.work, "ls-remote", "--heads", "origin", branch).stdout

    def push_develop(self, message):
        """Commit whatever is staged and push develop ONLY — never touches a feature
        branch. Used to seed/move the issue file the way CLAUDE.md requires (metadata,
        direct to develop) AFTER a branch has already been cut, so the branch's tree
        never gains a copy (LD-653)."""
        _git(self.work, "add", "-A")
        _git(self.work, "commit", "-m", message, "--quiet")
        _git(self.work, "push", "origin", "develop", "--quiet")


@pytest.fixture()
def sandbox(tmp_path):
    return Sandbox(tmp_path).build()


# --------------------------------------------------------------------------- #
# AC3 — defect 2: the confirmation is TRUE (scoped to what was measured), not a
# timeless claim, and not silently deleted either.
# --------------------------------------------------------------------------- #

@private_tree.kit
def test_the_remote_delete_claim_is_scoped_to_the_measurement_it_made(sandbox):
    sandbox.seed_issue("dev_complete", "LD-9002", "sandbox",
                       "Scoped delete claim", "fix/LD-9002-work")
    sandbox.publish()
    tip = sandbox.feature_branch("fix/LD-9002-work", filename="CHANGE.txt")

    result = sandbox.finish_pr("LD-9002")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert sandbox.ls_remote("fix/LD-9002-work") == "", "test setup: the delete did not happen"

    out = result.stdout + result.stderr
    # It still reports the delete — a quieter honest message, never a deleted one (AC3).
    # LD-635 AC4b: and the VERB matches the measurement. "Deleted remote branch" asserts an
    # achieved, durable state from a read taken INSIDE the window that state has to outlast;
    # what was actually established is that the delete was accepted and the ref read empty.
    assert "delete was ACCEPTED" in out and "read the ref EMPTY" in out, (
        f"the delete arm does not report what it measured\nout={out!r}")
    assert "Deleted remote branch" not in out, (
        "the arm still asserts the delete as an achieved state — measured false three for "
        "three on 2026-09-03 (LD-627, LD-638, LD-637), each read back empty at ~T+6s and "
        f"each ref back afterwards\nout={out!r}")
    # ...and it says WHEN it read the remote back, so the claim carries its own scope.
    assert "T+" in out and "after the push" in out, (
        "the confirmation does not state when it measured — an instantaneous read written "
        f"as a timeless claim is the defect\nout={out!r}")
    # ...and it names the residue hazard no measurement taken now can see.
    assert "GIT-HOSTING.md" in out and "restor" in out, (
        f"the confirmation does not name the known resurrection window\nout={out!r}")
    # The exact strings that were measured false three times must be gone.
    assert "(confirmed gone by ls-remote)" not in out
    assert "not re-checked since" in out

    # LD-635 AC4b: the read is taken INSIDE the window it would have to outlast, and the
    # message says so rather than leaving the reader to infer it.
    assert "INSIDE" in out and "window" in out, (
        f"the claim does not disclose that its read sits inside the restoration window"
        f"\nout={out!r}")

    note = sandbox.origin_show("progress/qa_complete/LD-9002-sandbox.md")
    assert "origin branch deleted" not in note, (
        "the PERMANENT board note still asserts the remote delete as an achieved state; the "
        f"measurement was an empty read at T+{'{N}'}s inside the window\nnote={note!r}")
    assert "delete ACCEPTED" in note and "read back EMPTY" in note, (
        f"the board note's delete clause does not say what was measured\nnote={note!r}")
    assert "branch deleted (confirmed gone)" not in note, (
        "the PERMANENT board note still carries the unqualified claim — this is the copy "
        f"read hours later, when the ref may be back\nnote={note!r}")
    assert "T+" in note and "not re-checked since" in note, (
        f"the board note's delete clause is not scoped to the measurement\nnote={note!r}")

    # THE FIELD SHAPE: the mirror puts the ref back AFTER the run (3-8 min in the
    # field; here, immediately after, which is the same observable for the note).
    # The note was written before this and must STILL be true when read now.
    _git(sandbox.origin, "update-ref", "refs/heads/fix/LD-9002-work", tip)
    assert tip in sandbox.ls_remote("fix/LD-9002-work"), "test setup: the ref did not come back"
    assert "branch deleted (confirmed gone)" not in note
    assert "not re-checked since" in note


@private_tree.kit
def test_a_surviving_remote_branch_still_never_claims_a_confirmed_delete(sandbox):
    """The other side of AC3, preserved from LD-542: when the remote accepts the delete
    and restores the ref DURING the run, the re-measurement catches it and no confirmed
    claim reaches the board. Scoping the honest arm must not soften this one."""
    sandbox.seed_issue("dev_complete", "LD-9003", "sandbox",
                       "Resurrected ref", "fix/LD-9003-work")
    sandbox.publish()
    tip = sandbox.feature_branch("fix/LD-9003-work", filename="RESURRECT.txt")
    hook = sandbox.origin / "hooks" / "post-receive"
    hook.write_text(
        "#!/bin/sh\n"
        "while read -r old new ref; do\n"
        "  case \"$new\" in\n"
        "    0000000000000000000000000000000000000000) git update-ref \"$ref\" \"$old\" ;;\n"
        "  esac\n"
        "done\n", encoding="utf-8")
    hook.chmod(0o755)

    result = sandbox.finish_pr("LD-9003")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    out = result.stdout + result.stderr
    assert tip in sandbox.ls_remote("fix/LD-9003-work"), "test setup: the ref was not resurrected"
    assert "SURVIVED a delete that reported SUCCESS" in out
    assert "Deleted remote branch" not in out
    assert "delete was ACCEPTED" not in out, (
        "the honest arm's LD-635 wording leaked into the survived arm — an accepted delete "
        f"whose ref is still advertised is not an empty read\nout={out!r}")

    note = sandbox.origin_show("progress/qa_complete/LD-9003-sandbox.md")
    assert "STILL PRESENT after a delete that reported success" in note
    assert "confirmed gone" not in note


# --------------------------------------------------------------------------- #
# AC4 — defect 3: the squash subject comes from the BRANCH's own issue copy.
# The two titles DIVERGE on purpose: that divergence is the whole bug.
# --------------------------------------------------------------------------- #

TRUNK_TITLE = "PARKED — stale trunk title, third occurrence"
BRANCH_TITLE = "The title the work actually carries, fourth occurrence"


@private_tree.kit
def test_the_squash_subject_comes_from_the_branchs_issue_copy_not_the_trunks(sandbox):
    issue_rel = "progress/dev_complete/LD-9001-sandbox.md"
    sandbox.seed_issue("dev_complete", "LD-9001", "sandbox", TRUNK_TITLE, "fix/LD-9001-work")
    sandbox.publish()
    # The branch amends its own copy of the issue — the shape LD-620 and LD-518 hit.
    sandbox.feature_branch(
        "fix/LD-9001-work", filename="CHANGE.txt",
        edits=[(issue_rel, f"title: {TRUNK_TITLE}", f"title: {BRANCH_TITLE}")])
    assert f"title: {TRUNK_TITLE}" in sandbox.origin_show(issue_rel), (
        "test setup: the TRUNK copy must still hold the stale title — a same-title "
        "test would pass vacuously")

    result = sandbox.finish_pr("LD-9001")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    subjects = sandbox.origin_subjects()
    assert BRANCH_TITLE in subjects, (
        "the PERMANENT squash subject does not carry the branch's own title\n"
        f"subjects={subjects!r}")
    assert TRUNK_TITLE not in subjects, (
        f"the squash subject carries the STALE TRUNK title — the defect\nsubjects={subjects!r}")
    # The operator is told the two copies disagreed and which one was used.
    out = result.stdout + result.stderr
    assert "branch's own copy" in out and "differs" in out, (
        f"the divergence was resolved silently\nout={out!r}")


@private_tree.kit
def test_the_trunk_copy_is_still_used_when_the_branch_never_touched_the_issue(sandbox):
    """The control: most branches never amend their issue file, and for those the trunk
    copy IS the current one. The fix must not invent a divergence where there is none,
    nor fail when the branch carries no copy of the file at all."""
    sandbox.seed_issue("dev_complete", "LD-9004", "sandbox",
                       "An ordinary untouched title", "fix/LD-9004-work")
    sandbox.publish()
    sandbox.feature_branch("fix/LD-9004-work", filename="CHANGE.txt")

    result = sandbox.finish_pr("LD-9004")
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    subjects = sandbox.origin_subjects()
    assert "[QA] LD-9004: An ordinary untouched title (squash-merge fix/LD-9004-work)" in subjects
    out = result.stdout + result.stderr
    assert "differs" not in out, f"a divergence was reported where there is none\nout={out!r}"


# --------------------------------------------------------------------------- #
# LD-653 — a branch that CORRECTLY carries no copy of the issue file at all is
# the common case (CLAUDE.md: issue files are metadata, commit direct to
# develop), yet `git ls-tree ... | grep -E ... | head -1` used to run as ONE
# piped assignment under `set -o pipefail`. Zero matches makes grep exit 1;
# pipefail propagates that through the pipeline; the assignment itself returns
# 1; `set -e` killed the WHOLE SCRIPT with NO OUTPUT AT ALL — before the
# "Plan:" line, before any error message, before anything an operator could
# read.
#
# `test_the_trunk_copy_is_still_used_when_the_branch_never_touched_the_issue`
# above does NOT catch this: its branch is cut off a develop that ALREADY has
# the issue file (seed_issue + publish() happen first), so the branch's tree
# inherits a matching path regardless — the real bug needs the branch cut
# BEFORE the issue file exists on develop at all, with the issue then landing
# on develop alone (`push_develop`), exactly as CLAUDE.md prescribes.
# --------------------------------------------------------------------------- #

@private_tree.kit
def test_a_branch_that_carries_no_issue_file_at_all_still_lands(sandbox):
    """Red against the pre-LD-653 script: this reproduces the shape the issue calls
    'the common case' — the branch never carries a copy, because it was cut before
    the issue existed on develop and the issue landed on develop alone afterward."""
    sandbox.publish()  # develop's first commit: scaffold only, no issue file anywhere.
    sandbox.feature_branch("fix/LD-9005-work", filename="CHANGE.txt")

    # The issue lands on develop ONLY, after the branch already exists — the branch's
    # tree under progress/ has zero paths matching LD-9005 (not even a stale copy).
    sandbox.seed_issue("dev_complete", "LD-9005", "sandbox",
                        "Branch carries no issue file at all", "fix/LD-9005-work")
    sandbox.push_develop("[PM] move LD-9005 to dev_complete")

    result = sandbox.finish_pr("LD-9005")
    out = result.stdout + result.stderr
    assert result.returncode == 0, (
        "finish-pr.sh died on a branch that correctly carries no issue file — the "
        f"LD-653 silent-death shape (pre-fix: rc=1, no output at all)\nout={out!r}")
    assert out.strip() != "", (
        "finish-pr.sh produced NO OUTPUT AT ALL — the exact LD-653 failure signature "
        "even if the exit code were somehow 0")
    assert "differs between the two copies" not in out, (
        "a divergent-title note fired despite the branch carrying no issue file to diverge from")

    origin_note = sandbox.origin_show("progress/qa_complete/LD-9005-sandbox.md")
    assert origin_note, "LD-9005 was not advanced to qa_complete/ on origin/develop"
    # The squash-merged code change landed on origin/develop.
    _git(sandbox.work, "fetch", "origin", "develop", "--quiet")
    tree = _git(sandbox.work, "ls-tree", "-r", "--name-only", "origin/develop").stdout
    assert "CHANGE.txt" in tree, f"squash-merged change not on origin/develop\ntree={tree!r}"
