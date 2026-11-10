"""LD-612 G1 — ``release.sh`` gate c reports the canary's OWN answer, never a claim it
cannot see.

The defect
----------
Gate c used to warn ``LARKDOCIO_CANARY_DOC is unset — the canary will SKIP`` on the strength
of a **shell-environment** test (``[ -z "${LARKDOCIO_CANARY_DOC:-}" ]``). The canary reads a
different place: ``tests/canary_support.py::load_env()`` loads the repo-root ``.env`` into
``os.environ`` (via ``larkdocio.auth.init_env``) *before* ``canary_doc_url()`` reads it. Since
the value normally lives in ``.env`` and not in the shell, the two readers **disagreed by
construction** — the warning fired on the v1.42.0 and v1.43.0 cuts while the canary ran for
real (``46 passed, 2 skipped``, live arms ``deterministic=True``).

Harmless in that direction. **The direction that matters is the other one:** the same
blindness printed nothing unusual on a cut where the canary genuinely *did* skip — the one
case the warning exists for.

The fix, and why these tests are shaped this way
-----------------------------------------------
Gate c now **asks the canary**: ``scripts/canary-status.py`` imports the same
``tests/canary_support`` the live ring uses and prints ``RUN`` or ``SKIP <reason>``. No second
definition of the ``.env`` resolution order is introduced anywhere (AC1d) — a bash re-parse of
``.env`` would be the same defect wearing a different hat.

So there are two things to prove, and they need different instruments:

1. **The probe agrees with the resolver it delegates to** — proved by *executing* the probe on
   this host and comparing its verdict against ``canary_support.missing_reason()`` computed
   in-process. That is the guard behind AC1d.
2. **Gate c's report follows the probe in BOTH directions** — proved by *running* the real
   ``release.sh`` in a throwaway sandbox with the probe stubbed through the script's own
   documented ``RELEASE_CANARY_STATUS_CMD`` seam, once for each answer, plus a third case where
   the probe itself fails (the honest *I do not know*).

The sandbox is ``tests/test_release_gate_notes.py``'s, imported rather than rebuilt: building a
second one here would mean a second git-invoking site in ``tests/**``, and that register
(``tests/test_no_test_reads_live_git.py``) takes a new entry as a finding, not a line to add.
"""
import os
import pathlib
import subprocess
import sys

from test_release_gate_notes import TARGET, _sandbox
import private_tree  # noqa: E402  (LD-685)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RELEASE_SH = REPO_ROOT / "scripts" / "release.sh"
PROBE = REPO_ROOT / "scripts" / "canary-status.py"


def _probe_stub(root, name, body):
    """A stub probe script in the sandbox — a FILE, not a command string.

    It is written beside the sandbox rather than inside it — release.sh refuses to cut on a
    dirty working tree, and an untracked stub is exactly that.

    The script expands ``RELEASE_CANARY_STATUS_CMD`` unquoted (the same form gates b/c/d use
    for their own seams), so a stub carrying spaces has to be a single word: a path. Passing
    ``"echo 'SKIP …'"`` here would word-split into an argv whose first token is ``echo`` and
    whose second is a literal ``'SKIP`` — which is how this helper earned its existence.
    """
    stub = root.parent / name          # OUTSIDE the sandbox repo: a cut refuses on a dirty tree
    stub.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    stub.chmod(0o755)
    return str(stub)


def _run_gate_c(root, status_cmd):
    """Run the sandboxed ``release.sh --dry-run`` with the canary-status probe stubbed.

    ``RELEASE_LIVE_CMD=true`` stubs the canary *invocation* (this is not the live ring — AC7:
    no live ring runs for LD-612); ``RELEASE_CANARY_STATUS_CMD`` stubs the *report's* source,
    which is the thing under test.
    """
    env = dict(
        os.environ,
        GIT_CONFIG_NOSYSTEM="1",
        RELEASE_VERIFY_CMD="true",
        RELEASE_LIVE_CMD="true",
        RELEASE_BOARD_CMD=str(root / "board-clean.sh"),
        RELEASE_CANARY_STATUS_CMD=status_cmd,
    )
    result = subprocess.run(
        ["bash", str(root / "scripts" / "release.sh"), TARGET, "--dry-run"],
        cwd=root, capture_output=True, text=True, env=env,
    )
    return result.returncode, result.stdout + result.stderr


# --------------------------------------------------------------------------- #
# AC1d — the probe delegates; it does not re-derive the resolution order.       #
# --------------------------------------------------------------------------- #

def _probe_python():
    """The interpreter that runs the probe: an explicit ``PYTHON`` wins, else the suite's own
    ``sys.executable`` -- never PATH's ``python3``, which may lack larkdocio (LD-706)."""
    return os.environ.get("PYTHON") or sys.executable


@private_tree.kit
def test_the_probe_interpreter_defaults_to_sys_executable_not_path_python3(monkeypatch):
    monkeypatch.delenv("PYTHON", raising=False)
    monkeypatch.setenv("PATH", "/nonexistent")
    assert _probe_python() == sys.executable
    monkeypatch.setenv("PYTHON", "/explicit/python")
    assert _probe_python() == "/explicit/python"


@private_tree.kit
def test_the_probe_AGREES_with_the_canarys_own_resolver_on_this_host():
    """Executed, on whatever this host's ``.env`` actually is: the probe's verdict and
    ``canary_support.missing_reason()`` are the same answer, because they are the same code."""
    import canary_support

    canary_support.load_env()
    reason = canary_support.missing_reason()

    result = subprocess.run(
        [_probe_python(), str(PROBE)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"the probe failed: {result.stderr}"
    verdict = result.stdout.strip()

    if reason is None:
        assert verdict == "RUN", (
            f"canary_support says the canary can run; the probe says {verdict!r}")
    else:
        assert verdict.startswith("SKIP "), (
            f"canary_support says the canary will skip ({reason!r}); probe said {verdict!r}")
        assert reason in verdict, "the probe must carry the resolver's own reason, not its own"


@private_tree.kit
def test_the_probe_does_not_re_parse_dotenv_itself():
    """AC1d as a guard rather than a promise: the probe may not grow its own ``.env`` reader —
    that would be a second definition of the resolution order, free to drift from
    ``larkdocio.auth.init_env``."""
    source = PROBE.read_text(encoding="utf-8")
    assert "canary_support" in source, "the probe must delegate to the canary's own resolver"
    for smell in ('open(".env"', "'.env'", 'splitlines()', "dotenv_values"):
        assert smell not in source, f"the probe looks like it parses .env itself: {smell!r}"


@private_tree.kit
def test_release_sh_no_longer_tests_the_SHELL_env_for_the_canary_doc():
    """The removed defect, pinned so it cannot come back: gate c must not decide what the
    canary will do from a variable the canary does not read from there."""
    source = RELEASE_SH.read_text(encoding="utf-8")
    assert '[ -z "${LARKDOCIO_CANARY_DOC:-}" ]' not in source, (
        "gate c is testing the shell environment again — the canary reads .env through "
        "tests/canary_support.py::load_env(), so the two disagree by construction")
    assert "the canary will SKIP" not in source, (
        "gate c still states unconditionally what the canary will do")


@private_tree.kit
def test_release_sh_RECORDS_the_disagreement_as_the_cause():
    """AC1a — the next reader must not have to re-derive why a shell test was wrong here, so
    both readers are cited by path in the script itself."""
    source = RELEASE_SH.read_text(encoding="utf-8")
    assert "tests/canary_support.py" in source
    assert ".env" in source
    assert "LD-612" in source


# --------------------------------------------------------------------------- #
# AC1b / AC1c — both directions, EXECUTED against the real script.              #
# --------------------------------------------------------------------------- #

@private_tree.kit
def test_gate_c_prints_NO_SKIP_CLAIM_when_the_canary_will_run(tmp_path):
    """AC1b: the case that fired wrongly at v1.42.0 and v1.43.0 — the canary can run, so gate
    c may not say it will skip."""
    root = _sandbox(tmp_path, [TARGET], [TARGET])
    code, out = _run_gate_c(root, _probe_stub(root, "probe-run.sh", "echo RUN"))
    assert code == 0, out
    assert "SKIP" not in out, f"gate c claimed a skip while the canary will run:\n{out}"
    assert "WILL RUN" in out, f"gate c reported nothing about the canary:\n{out}"


@private_tree.kit
def test_gate_c_WARNS_UNMISSABLY_when_the_canary_genuinely_will_skip(tmp_path):
    """AC1c: the case the warning exists for, and the case the old shell test could not see."""
    reason = "LARKDOCIO_CANARY_DOC is unset — set it to the disposable scratch-doc URL"
    root = _sandbox(tmp_path, [TARGET], [TARGET])
    code, out = _run_gate_c(
        root, _probe_stub(root, "probe-skip.sh", f'echo "SKIP {reason}"'))
    assert code == 0, out
    assert "WILL SKIP" in out, f"the canary will skip and gate c did not warn:\n{out}"
    assert "⚠" in out, f"the warning is missable — no ⚠ marker:\n{out}"
    assert reason in out, f"the warning drops the canary's own reason:\n{out}"
    assert "no live round-trip" in out


@private_tree.kit
def test_gate_c_says_it_DOES_NOT_KNOW_when_the_probe_fails(tmp_path):
    """The third answer. A probe that cannot run (no venv, no larkdocio, no ``tests/``) must
    produce an honest *unknown* — never a silent pass and never a fabricated verdict."""
    root = _sandbox(tmp_path, [TARGET], [TARGET])
    code, out = _run_gate_c(
        root, _probe_stub(root, "probe-broken.sh", "echo 'boom' >&2; exit 3"))
    assert code == 0, out
    assert "UNKNOWN" in out, f"a failed probe was reported as something else:\n{out}"
    assert "WILL SKIP" not in out and "WILL RUN" not in out, (
        f"gate c invented a verdict from a failed probe:\n{out}")


@private_tree.kit
def test_the_seam_is_DOCUMENTED_in_the_scripts_own_test_seam_list(tmp_path):
    """A seam these tests depend on is part of the script's contract, not a private hook."""
    source = RELEASE_SH.read_text(encoding="utf-8")
    seams = source[source.index("TEST SEAMS"):source.index("set -euo pipefail")]
    assert "RELEASE_CANARY_STATUS_CMD" in seams
