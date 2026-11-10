"""THE VERSION-AHEAD RULE for the release documents — one seam, no second definition.

Why this module exists (LD-169)
-------------------------------
The release path was, for one release, **impossible to walk**. Three pieces, each correct in
isolation, deadlocked:

1. ``scripts/release.sh`` runs **gate b — the whole suite — BEFORE it bumps the version**
   (the bump *is* the release commit; the script owns it atomically), so at every preflight
   ``pyproject.toml`` still carries the **old** version.
2. **Gate e** refuses to tag a version whose ``## [X.Y.Z]`` section is not already written in
   both release documents — by design, so no undocumented tag can ship.
3. The notes guard refused **any** section ahead of the packaged version.

Authoring what gate e requires made gate b red; not authoring it made gate e refuse the tag.
The guard was the wrong arm: it was born as a **scope fence for one issue** (*"this issue
must not pre-write the next release"*) and was generalized into a standing invariant that the
cut state can never satisfy.

**The corrected standing rule: AT MOST ONE version ahead of the packaged one.** One ahead is
the **cut in progress**; two or more is **pre-writing releases that do not exist** — which is
what the fence was really for, and which stays refused.

"One ahead" is **any single version greater than the packaged one — never a computed
successor.** larkdocio's version numbers carry **no major/minor semantics (maintainer directive; they
mean nothing beyond monotonic order)**, so ``1.20.1``, ``1.21.0`` and ``2.0.0`` are all
equally legitimate next cuts, and a skipped number is a legitimate choice. Successor
arithmetic would refuse valid cuts, so this module counts **distinct versions ahead** and
compares that count against :data:`AHEAD_ALLOWANCE`.

Why it lives in its own module
------------------------------
Two callers need the same rule and must not hold two copies of it:
``tests/test_release_notes.py`` (the guard over the real file) and the release-flow ordering
exercises (``tests/test_release_gate_notes.py`` and the ``scripts/test/run.sh`` sandbox case,
which drives the real cut state through the real script). Keeping it importable with **stdlib
only** — no ``larkdocio`` import, no venv required — is what lets the bash sandbox case call
this exact code rather than re-implementing it, so the case provably exercises the guard and
cannot drift from it.
"""
import re

#: ``## [X.Y.Z] — YYYY-MM-DD`` — the same anchored form ``scripts/release.sh``'s gate e greps.
SECTION_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\] — (\d{4}-\d{2}-\d{2})$")

#: A fenced-code delimiter (``` or ~~~, three or more, optionally indented, with an info
#: string). The parse is fence-aware: a *quoted example* of a section heading is not a
#: release. See :func:`section_starts`.
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")

#: How many distinct versions may sit ahead of the packaged one: exactly **one** — the cut in
#: progress. The number is the rule; nothing about a version's *shape* is inspected.
AHEAD_ALLOWANCE = 1


def version_key(text):
    """``"1.20.0" -> (1, 20, 0)`` — ordering only. No semantics are read off the parts."""
    return tuple(int(part) for part in text.split("."))


def section_starts(lines):
    """``[(version, date, line_index)]`` for every REAL release heading, in file order.

    **Fence-aware**: a heading inside a ``` / ~~~ fenced block is a quoted example, not a
    release. A closing fence must use the same character as the one that opened it, so a
    ``~~~`` line inside a ``` block is content.
    """
    fence = None
    found = []
    for index, line in enumerate(lines):
        match = FENCE_RE.match(line)
        if match:
            char = match.group(1)[0]
            if fence is None:
                fence = char
            elif fence == char:
                fence = None
            continue
        if fence is not None:
            continue
        match = SECTION_RE.match(line)
        if match:
            found.append((match.group(1), match.group(2), index))
    return found


def packaged_version(pyproject_text):
    """The version the package currently carries, read off ``pyproject.toml``'s text."""
    for line in pyproject_text.splitlines():
        match = re.match(r'^version = "(\d+\.\d+\.\d+)"$', line)
        if match:
            return match.group(1)
    raise AssertionError("pyproject.toml carries no `version = \"X.Y.Z\"` line")


def versions_ahead(versions, packaged):
    """The **distinct** authored versions greater than *packaged*, ascending."""
    ceiling = version_key(packaged)
    return sorted(
        {version for version in versions if version_key(version) > ceiling}, key=version_key
    )


def ahead_refusal(versions, packaged):
    """The refusal message when *versions* pre-writes releases, else ``None``.

    The message states the **rule** and names the offending versions — a reader who trips it
    must learn why one ahead is allowed without re-deriving the release-script ordering.
    """
    ahead = versions_ahead(versions, packaged)
    if len(ahead) <= AHEAD_ALLOWANCE:
        return None
    return (
        f"{len(ahead)} versions are authored ahead of the packaged {packaged}: {ahead}. "
        f"THE RULE: at most one section may sit ahead of the packaged version — that one is "
        f"the CUT IN PROGRESS (release.sh runs the whole suite BEFORE it bumps the version, "
        f"and refuses to tag a version with no section, so the cut state necessarily has one "
        f"section ahead). Two or more means pre-writing releases that do not exist yet: keep "
        f"{ahead[0]} (the cut) and remove {ahead[1:]} until each is actually being cut."
    )
