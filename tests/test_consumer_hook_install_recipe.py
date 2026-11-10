"""EVERY consumer-facing statement of the hook-install recipe lets GIT name the directory.

The defect this file is the fence around
--------------------------------------
Four consumer-facing statements told an integrator to ``cp`` the advisory nag hook into
``.git/hooks/``. Once ``core.hooksPath`` is set, git reads hooks from **that** directory and
**only** that one, so the copied file is never called — and there is no warning, no error and
no non-zero exit. Measured on git 2.51.0: one repo, one hook file, the config the only
difference; with it set the merge completes normally and says nothing at all.

Two facts turn that from an inconvenience into a trap, and both are why this guard is
suite-wide rather than a note in one file:

* **This project's own process kit SETS ``core.hooksPath``** (``setup.sh``,
  ``scripts/kit-init.sh``), so the recipe was broken in precisely the class of repository it
  was written for — one that adopted this kit.
* **The nag is quiet on success by design** (one short line for *up to date*), so a consumer
  whose hook is in a directory git does not read sees the same nothing as a consumer who is
  genuinely current. Absence was indistinguishable from up-to-date, forever.

What is asserted, and why it is a TEXT guard
--------------------------------------------
``tests/test_shipped_notes.py`` runs the recipe extracted from the hook template and proves a
real merge fires it. That covers the canonical statement end to end; what it cannot cover is
the other three **restatements** of the same recipe, which are prose and are what a consumer
actually reads first. This file holds all four to one shape:

1. no statement writes a path **into** ``.git/hooks/`` (naming the bare directory while
   explaining the trap is fine, and deliberately still allowed);
2. every statement lets git answer where hooks live —
   ``git rev-parse --git-path hooks``, which is correct in all three configuration states
   (unset → ``.git/hooks``, a relative setting, an absolute setting), unlike
   ``git config --get core.hooksPath``, which prints nothing and exits 1 when unset;
3. the ``post-checkout`` variant — the same recipe one sentence down — moves with it, because
   a fix that corrected ``post-merge`` alone would have re-created the bug in the adjacent
   sentence;
4. every statement carries a way to **prove** the hook is wired, which is the half of the
   defect that the wrong directory did not cause: a silent nag cannot be audited by looking at
   it.
"""
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The four statements that carry the recipe. The last is the wheel's ``METADATA`` body
#: (``pyproject.toml``'s ``readme``), so its bytes are what a consumer meets on the package
#: page — a correction there is a *shipped* correction.
RECIPE_STATEMENTS = {
    "consumers/setup-consumer.sh": "the onboarding script's printed banner",
    "consumers/hooks/post-merge": "the hook template's own Install header",
    "consumers/README.md": "the step-by-step onboarding walkthrough",
    "README.md": "the root README — the wheel's METADATA body",
}

#: A path *into* ``.git/hooks`` — the destination that is silently wrong under
#: ``core.hooksPath``. The bare directory name is not matched: prose that explains the trap
#: has to be able to say where git stopped looking.
_HARDCODED_DESTINATION = re.compile(r"\.git/hooks/\S")

#: The primitive that answers in every configuration state, including the unset default.
_DERIVATION = "rev-parse --git-path hooks"

#: The proof step. ``git hook run <name>`` resolves the hook through git's own lookup, so it
#: fails loudly when the file is somewhere git does not read — the one command whose silence
#: means something.
_PROOF = "git hook run"


def _statement(rel):
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_no_statement_hardcodes_a_destination_inside_dot_git_hooks():
    """(1) The literal that was silently wrong appears in none of the four statements."""
    offenders = {}
    for rel in RECIPE_STATEMENTS:
        hits = [f"{rel}:{n}: {line.strip()}"
                for n, line in enumerate(_statement(rel).splitlines(), 1)
                if _HARDCODED_DESTINATION.search(line)]
        if hits:
            offenders[rel] = hits
    assert not offenders, (
        "a consumer-facing statement still names a destination inside `.git/hooks/`, which git "
        "never reads once core.hooksPath is set — and this project's own kit sets it:\n"
        + "\n".join(line for hits in offenders.values() for line in hits))


def test_every_statement_lets_GIT_name_the_hooks_directory():
    """(2) All four derive the destination instead of asserting one."""
    missing = [f"{rel} ({what})" for rel, what in RECIPE_STATEMENTS.items()
               if _DERIVATION not in _statement(rel)]
    assert not missing, (
        f"these statements do not let git answer where hooks live (`git {_DERIVATION}`), so "
        "each is an independent chance to be wrong again:\n  " + "\n  ".join(missing))


def test_the_onboarding_script_DERIVES_the_destination_for_the_repo_it_PRINTS_FOR():
    """(2), sharpened for the one statement that is a program rather than prose.

    The script knows the consumer's repo root, so the one-liner it prints can be *correct for
    that repo* rather than a general instruction the reader has to adapt. Prose that warns is
    second-best to a command that is already right. So the derivation must name ``$CONSUMER``,
    and the printed banner must interpolate the result rather than restate a literal.
    """
    text = _statement("consumers/setup-consumer.sh")
    assignment = re.search(
        r'^(?P<var>[A-Z_]+)="?\$\(\s*git -C "\$CONSUMER" ' + re.escape(_DERIVATION),
        text, re.MULTILINE)
    assert assignment, (
        "consumers/setup-consumer.sh does not derive the hooks directory for $CONSUMER — the "
        f'expected shape is VAR="$(git -C "$CONSUMER" {_DERIVATION})"')
    var = assignment.group("var")
    banner = text.split("Three things remain for you", 1)
    assert len(banner) == 2, "the printed banner's opening line moved — re-derive this split"
    assert "${%s}" % var in banner[1], (
        f"the banner does not interpolate the derived destination ${{{var}}}, so what it "
        "prints is a guess about the consumer's repo rather than a reading of it")


def test_the_post_checkout_VARIANT_moves_with_the_recipe():
    """(3) The same recipe, one sentence down. It is named in two of the four statements."""
    for rel in ("consumers/hooks/post-merge", "consumers/README.md"):
        text = _statement(rel)
        assert "post-checkout" in text, (
            f"{rel} dropped the post-checkout variant — it is an alternative the recipe "
            "offers, and deleting it is not how this bug gets fixed")
        for n, line in enumerate(text.splitlines(), 1):
            if "post-checkout" not in line:
                continue
            assert not _HARDCODED_DESTINATION.search(line), (
                f"{rel}:{n} still installs post-checkout under `.git/hooks/` — correcting "
                f"post-merge alone re-creates the bug in the adjacent sentence: {line.strip()}")


def test_every_statement_carries_a_way_to_PROVE_the_hook_is_WIRED():
    """(4) The silent-absence half: a nag that is quiet on success cannot be audited by eye."""
    missing = [f"{rel} ({what})" for rel, what in RECIPE_STATEMENTS.items()
               if _PROOF not in _statement(rel)]
    assert not missing, (
        f"these statements give a consumer no way to prove the hook fires (`{_PROOF} "
        "<hook>`), and this nag's silence on success is indistinguishable from its silence "
        "when it was never wired:\n  " + "\n  ".join(missing))


def test_the_REASON_for_this_primitive_survives_where_a_maintainer_reads_it():
    """Preserve the reason, not just the conclusion.

    The obvious primitive is ``git config --get core.hooksPath``, and it is the one the
    triage suggested. Measured: it prints nothing and exits 1 when the setting is absent, so
    it needs a second branch for the default case that ``git rev-parse --git-path hooks``
    handles by itself. Without that recorded, the next reader "simplifies" back to the config
    read and re-introduces a variant of this bug.
    """
    header = _statement("consumers/hooks/post-merge")
    assert "core.hooksPath" in header and "exits 1" in header, (
        "the hook template no longer records WHY the destination is derived with "
        f"`git {_DERIVATION}` rather than read from core.hooksPath directly (that read exits "
        "1 and prints nothing when the setting is absent)")
