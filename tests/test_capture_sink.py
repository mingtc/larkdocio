"""LD-620 — a capture write may NOT land inside a git working tree.

**The defect, four times.** An armed ``pytest -m live_write`` run rewrites committed
``dev/**/captures/*.json`` files belonging to CLOSED issues, because each live gate writes its
capture to the same in-tree path it was originally committed at. The occurrences:

1. **``ld317-01``** — the first, reverted.
2. **``LD-497``** — reverted on trunk, in a commit whose own subject records the rule it
   applied: *"the probe re-run rewrote a COMMITTED capture that landed tests PIN … the
   ld317-01 precedent applies, the capture is restored"*.
3. **LD-619's Dev leg** (2026-09-02) — **20** captures rewritten in one run.
4. **LD-619's QA** (2026-09-02, hours later, a different actor following the same documented
   procedure) — **19** captures rewritten. All 962 restored byte-identical.

Three reverts and zero fixes is not an incident, it is a missing fence: **it fires for anyone
who arms the ring.**

**The sharpest evidence is not the changed value.** In
``tests/captures/base-study/captures/ld336-01-fields-at-creation.json`` the same-window control was
laundered ``9499`` / *"Invalid parameter type…"* → ``0`` / *"success"* **while the same file's
own ``_note`` still argued** *"a kitted create that applied beside a 9499 control is the
premise HOLDING"*. The file contradicted itself: its prose reasoned from a ``9499`` its data no
longer contained. A stale capture is wrong **and readable as wrong**; a laundered one reads as
internally coherent to anyone who does not already know what it used to say, because the
surviving note lends the rewritten number its own authority. That is why the sink is **loud**
(AC3) rather than merely correct.

**What this module tests** — the two halves of :mod:`capture_sink`, against a scratch capture
in a **throwaway repo**, never a real one:

- the **mechanism**: the write is redirected to a run-scoped directory outside every working
  tree, and the tracked file it was aimed at is left byte-identical;
- the **refusal**: a destination that still resolves inside a git working tree raises
  :class:`capture_sink.TrackedCaptureWriteRefused`, naming the path.

The sandbox is driven with a real ``git init``/``add``/``commit`` so the file the raw pattern
launders is genuinely **tracked**, which is the whole claim. Registered in
``tests/test_no_test_reads_live_git.py``'s exemption register — hermetic, explicit ``git -C``.
:mod:`capture_sink` itself invokes no git at all; it walks for ``.git``.
"""
import json
import os
import subprocess

import pytest

import capture_sink

#: The committed body of the scratch capture — the ``9499`` shape the real laundering hit, so
#: the demonstration below is the defect's own shape and not a toy string.
COMMITTED = json.dumps(
    {
        "_probe": "ld620-scratch",
        "_note": "a kitted create that applied beside a 9499 control is the premise HOLDING",
        "control": {"code": 9499, "msg": "Invalid parameter type"},
    },
    indent=1,
) + "\n"

#: What a re-run would write over it: the same filename, a materially different measurement.
RERUN = json.dumps(
    {
        "_probe": "ld620-scratch",
        "_note": "a kitted create that applied beside a 9499 control is the premise HOLDING",
        "control": {"code": 0, "msg": "success"},
    },
    indent=1,
) + "\n"


def _git(root, *args):
    """A git command inside the sandbox, insulated from the developer's own config.

    Identity and hooks are set in the sandbox's OWN repo config (local config wins) and
    ``GIT_CONFIG_NOSYSTEM`` drops the system file, so a machine with a global signing key or
    hooks path cannot make this flaky. Every call names its repository with ``git -C``; the
    live checkout is never the target.
    """
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", "-C", str(root), *args], check=True, env=env, capture_output=True)


def _throwaway_repo(tmp_path):
    """A throwaway repo carrying ONE committed capture, at a real capture-shaped path."""
    root = tmp_path / "sandbox"
    capture = root / "tests" / "captures" / "base-study" / "captures" / "ld620-scratch.json"
    capture.parent.mkdir(parents=True)
    capture.write_text(COMMITTED, encoding="utf-8")
    _git(root.parent, "init", "-q", root.name)
    _git(root, "config", "user.email", "ld620@example.invalid")
    _git(root, "config", "user.name", "LD-620 sandbox")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "config", "core.hooksPath", str(root / ".no-hooks"))
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed the scratch capture")
    return root, capture


def test_ac1_a_capture_write_leaves_the_TRACKED_file_it_was_aimed_at_untouched(tmp_path):
    """**AC1's red, from the real mechanism.** Aim the sink at a committed capture.

    Before :mod:`capture_sink` existed the live gates wrote with a bare
    ``CAPTURE.write_text(json.dumps(...))``, and this assertion measured the laundering: the
    tracked file came back carrying ``code: 0`` under the same filename, beside its own
    ``_note`` still arguing from ``9499``.
    """
    root, capture = _throwaway_repo(tmp_path)
    before = capture.read_bytes()

    # THE MECHANISM UNDER TEST — the one the live gates call.
    destination = capture_sink.write_capture(capture, RERUN)

    assert capture.read_bytes() == before, (
        f"a capture write LAUNDERED the tracked file {capture} — its committed body is gone "
        f"and the filename no longer identifies a fixed measurement"
    )
    assert destination.read_text(encoding="utf-8") == RERUN, (
        "the run's own measurement must still be written somewhere a human can read it — "
        "refusing to record it would trade one silent loss for another"
    )
    assert capture_sink.working_tree_root(destination) is None, (
        f"the capture landed at {destination}, which is inside a git working tree"
    )
    assert destination.relative_to(capture_sink.run_root()), "the write must be run-scoped"


def test_the_RAW_pattern_is_the_defect_ITSELF_and_the_sandbox_proves_it(tmp_path):
    """The hazard kept demonstrated rather than remembered.

    ``Path.write_text`` cannot be fixed, so the only durable statements are (i) that the raw
    pattern really does launder a committed capture — measured here, in a sandbox — and (ii)
    that no capture-writing site in ``tests/**`` uses it, which is
    ``tests/test_capture_write_sites.py``'s census. Without (i) a reader has to take the
    census's word for why it exists.
    """
    _root, capture = _throwaway_repo(tmp_path)

    capture.write_text(RERUN, encoding="utf-8")

    body = capture.read_text(encoding="utf-8")
    assert '"code": 0' in body and "9499" not in body.split('"control"')[1], (
        "the raw pattern is expected to have replaced the control's 9499 with 0"
    )
    assert "premise HOLDING" in body, (
        "and this is what makes it worse than staleness: the file's own _note survives, still "
        "reasoning from a 9499 the data no longer contains — it reads as internally coherent"
    )


def test_ac3_the_redirect_NAMES_both_paths_and_says_why_in_words_a_human_reads(tmp_path,
                                                                              capsys,
                                                                              recwarn):
    """**AC3.** Silence is the defect. A redirect that nobody notices is a redirect nobody acts
    on, and the action — landing a genuinely new measurement as a dated supersession — is a
    human's."""
    _root, capture = _throwaway_repo(tmp_path)

    destination = capture_sink.write_capture(capture, RERUN)

    spoken = capsys.readouterr().out
    warned = "\n".join(str(w.message) for w in recwarn)
    for said in (spoken, warned):
        assert str(capture) in said, "the intended path is named"
        assert str(destination) in said, "the path actually written is named"
        assert "9499" in said and "LD-620" in said, "the reason travels with the redirect"
        assert "supersession" in said, "and so does what to do about it"


def test_ac3_a_destination_STILL_inside_a_working_tree_is_REFUSED_by_type(tmp_path,
                                                                         monkeypatch):
    """The fence half, at its one real seam: the override pointed back into a checkout.

    This is the case the run-scoped mechanism cannot fix by itself — and the reason the seat's
    leaning was a refusal. A path list would not have covered it; working-tree membership
    does.
    """
    root, capture = _throwaway_repo(tmp_path)
    before = capture.read_bytes()
    monkeypatch.setenv(capture_sink.RUN_ROOT_ENV, str(root / "dev" / "smuggled"))
    monkeypatch.setattr(capture_sink, "_RUN_ROOT", None)

    with pytest.raises(capture_sink.TrackedCaptureWriteRefused) as refusal:
        capture_sink.write_capture(capture, RERUN)

    assert str(root) in str(refusal.value), "the refusal names the working tree it protected"
    assert "REFUSED" in str(refusal.value) and str(capture) in str(refusal.value)
    assert capture.read_bytes() == before
    assert not (root / "dev" / "smuggled").exists(), "and it refused BEFORE creating anything"


def test_a_LINKED_worktree_is_a_working_tree_too_even_though_its_dot_git_is_a_FILE(tmp_path):
    """The evasion a naive ``.git`` check walks straight past.

    This project's tranche runners work in linked worktrees (``.kanban-wt/``, ``.worktrees/``),
    where ``.git`` is a pointer **file**. A fence blind to that would be off in exactly the
    places most runs happen.
    """
    linked = tmp_path / "wt-LD-620"
    (linked / "tests" / "captures" / "base-study" / "captures").mkdir(parents=True)
    (linked / ".git").write_text("gitdir: /elsewhere/.git/worktrees/wt-LD-620\n",
                                 encoding="utf-8")
    intended = linked / "tests" / "captures" / "base-study" / "captures" / "ld620-scratch.json"

    assert capture_sink.working_tree_root(intended) == linked
    assert capture_sink.destination_for(intended) != intended


def test_a_path_outside_every_working_tree_is_left_where_the_caller_put_it(tmp_path):
    """No tree, nothing to protect — and rewriting an explicit out-of-tree choice would be the
    sink deciding something it was not asked to decide."""
    free = tmp_path / "nowhere" / "c.json"
    assert capture_sink.working_tree_root(free) is None
    assert capture_sink.destination_for(free) == free


def test_the_destination_is_PURE_within_a_run_so_a_read_back_finds_what_was_written(tmp_path):
    """``test_live_base_relational_gate.py`` reads its own capture back to prove it carries no
    signed link and no media bytes. That check has to address the file the run wrote."""
    _root, capture = _throwaway_repo(tmp_path)

    first = capture_sink.destination_for(capture)
    written = capture_sink.write_capture(capture, RERUN)

    assert first == written == capture_sink.destination_for(capture)
    assert capture_sink.RUN_ID in str(written), "the destination is scoped to THIS run"


def test_two_working_trees_of_the_same_repo_do_not_collide_on_one_relative_path(tmp_path):
    """A checkout and a linked worktree share every relative capture path; the tree's own name
    keeps their run-scoped destinations apart."""
    paths = []
    for name in ("main-checkout", "wt-LD-620"):
        tree = tmp_path / name
        (tree / "tests" / "captures" / "base-study" / "captures").mkdir(parents=True)
        (tree / ".git").mkdir()
        paths.append(capture_sink.destination_for(
            tree / "tests" / "captures" / "base-study" / "captures" / "same-name.json"))

    assert paths[0] != paths[1]
