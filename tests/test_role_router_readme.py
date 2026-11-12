"""THE ROLE ROUTER — the front door directs traffic before it teaches anything.

Why this module exists
----------------------
LD-178 made the README **consumer-first**: a leading quickstart, the clone-based material
demoted behind a labelled *"Developing larkdocio"* heading. That fixed the *audience* of the
first section. What it did not fix is that the reader still has to **work out which parts are
theirs** — three roles read this file (a consumer who *uses* the library, a vendor-integrator
who *vendors and re-pins* the wheel, a developer who *works on* larkdocio) and the document
addressed them in one voice. The doctrine this closes: *only give information relevant to the
role.*

**And the fork exposed a concrete hole.** The quickstart opened at::

    pip install ./vendor/larkdocio-*-py3-none-any.whl    # 1. install the wheel you vendored

*"the wheel you vendored"* — step 1 assumed the wheel was **already there**. The one command
that actually **gets** it was documented in ``consumers/`` and nowhere near the top of the file
a new consumer reads, so the very first instruction could not be followed on a clean machine.
**Step 0 was missing for the primary role**, and that is what :func:`test_ac3_*` pins.

What this module pins, and what it deliberately does NOT
--------------------------------------------------------
* the router exists, **leads the document**, and offers exactly three self-identifying arms,
  each pointing somewhere that **resolves** (§ AC1);
* the consumer arm's **first actionable command is not** ``pip install`` — step 0 comes first
  (§ AC3);
* the arms **point rather than restate**, so there is one copy of every instruction (§ AC6);
* the ``dist`` fast path is **absent on purpose** — LD-194 inserts it when the branch exists,
  and this guard is what makes that insertion a deliberate act rather than a drift (§ AC4);
* the consumer arm is **shaped for that one-line insertion**: step 0 lives in its own fence, so
  a line can go in above the updater command without restructuring anything (§ AC4).

The **audience** guards (no ``git clone`` / ``./setup.sh`` above the development heading, no
citation of a file the wheel lacks, the layout table's bidirectional pin at its new home) are
LD-167/LD-178's and live in ``tests/test_consumer_first_readme.py`` /
``tests/test_front_door_*.py``. They are not restated here — they **travel** with this
restructure and are re-proved there, which is the constraint this issue was written around.

The pure helpers live in ``tests/front_door.py``.
"""
import re

import pytest

import front_door as fd
from doc_prose import prose
from front_door import dev_repo_clone_lines


@pytest.fixture(scope="module")
def readme():
    return fd.readme_text()


@pytest.fixture(scope="module")
def consumer_half(readme):
    return fd.split_at_development_heading(readme)[0]


# --------------------------------------------------------------------------- #
# The router's shape, as parseable data                                        #
# --------------------------------------------------------------------------- #

#: The heading that opens the router. One canonical phrase, like ``DEVELOPMENT_HEADING`` —
#: a guard with three accepted spellings is a guard nobody can predict.
ROUTER_HEADING = "## Start here — pick your path"

#: The three roles, and the word each arm's heading must carry so a reader can self-identify.
#: Derived nowhere — this IS the role map §J names, so it is written down once, here.
ROLES = ("consumer", "vendor-integrator", "developer")


def _section(text, heading, depth=None):
    """The slice of ``text`` under ``heading``, up to the next heading of the same depth.

    Fence-aware: a ``# comment`` at the start of a line inside a ```` ``` ```` block is not a
    heading. ``front_door.section_of_line`` is deliberately *not* fence-aware (loosening it
    would widen the scope a dev-repo label grants), so the arithmetic here is local.
    """
    lines = text.splitlines()
    depth = len(heading) - len(heading.lstrip("#")) if depth is None else depth
    start = next(
        (index for index, line in enumerate(lines) if line.strip() == heading), None
    )
    if start is None:
        return ""
    out, in_fence = [lines[start]], False
    for line in lines[start + 1:]:
        if line.strip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            stripped = line.strip()
            if stripped.startswith("#") and len(stripped) - len(stripped.lstrip("#")) <= depth:
                break
        out.append(line)
    return "\n".join(out)


def router_section(text):
    """The router's own text — the ``## Start here`` section, arms included."""
    return _section(text, ROUTER_HEADING)


def arm_headings(text):
    """``{role: heading}`` for every ``###`` heading inside the router that names a role."""
    found = {}
    for line in router_section(text).splitlines():
        stripped = line.strip()
        if not stripped.startswith("### "):
            continue
        lowered = prose(stripped)
        for role in ROLES:
            if role in lowered and role not in found:
                found[role] = stripped
    return found


def arm_heading_lines(text):
    """EVERY ``###`` heading inside the router, whether or not it names a role.

    :func:`arm_headings` is a role→heading **map**, so a heading naming no mapped role simply
    never enters it — which is how ``### Auditor`` was spliced into the router and the suite
    stayed green while this module promised *"a fourth arm is as much a defect as a missing
    one"* (LD-193's QA ran exactly that mutation; LD-210 AC7 closes it). The equality below is
    judged over **this** list, so it bites in both directions.
    """
    return [
        line.strip()
        for line in router_section(text).splitlines()
        if line.strip().startswith("### ")
    ]


def arm_section(text, role):
    """One arm's text, by role."""
    heading = arm_headings(text).get(role)
    return _section(router_section(text), heading) if heading else ""


#: A GitHub-style in-document link — ``[label](#anchor)``.
_ANCHOR_LINK = re.compile(r"\[[^\]]+\]\(#([^)]+)\)")

#: How GitHub slugifies a heading: drop the ``#``s, lower-case, strip anything that is not a
#: word character / space / hyphen, then spaces to hyphens.
_SLUG_STRIP = re.compile(r"[^\w\s-]")


def heading_slugs(text):
    """Every heading's GitHub anchor slug — what a ``](#…)`` link has to match."""
    slugs, in_fence = set(), False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not re.match(r"^#{1,6}\s", line):
            continue
        title = line.lstrip("#").strip()
        slugs.add(_SLUG_STRIP.sub("", title).lower().replace(" ", "-"))
    return slugs


def anchor_links(text):
    """The anchors ``text`` links to."""
    return _ANCHOR_LINK.findall(text)


# =====================================================================
# AC1 — the router LEADS, and offers three resolving arms
# =====================================================================

def test_ac1_the_router_is_the_documents_first_section(readme):
    """The whole point of a traffic director is that it comes **before** the traffic. The
    reader self-identifies first and reads one arm, rather than reading a consumer quickstart
    and working out which parts are theirs."""
    first = next(line.strip() for line in readme.splitlines() if line.startswith("## "))
    assert first == ROUTER_HEADING, (
        f"the README's first section is {first!r} — the role router must lead the document"
    )


def test_ac1_the_router_offers_exactly_the_three_roles(readme):
    """Held as an equality **in both directions**: a fourth arm is as much a defect as a
    missing one, because the value of a fork is that a reader can place themselves in it
    immediately.

    The two directions are separate assertions on purpose (LD-210 AC7). The first is over the
    role→heading map, which bites on a **missing** arm. The second is over every ``###``
    heading the router actually carries, which is the only thing that bites on an **extra**
    arm — the map alone never saw ``### Auditor``, so the equality held in one direction while
    this test's own name promised both.
    """
    found = arm_headings(readme)
    assert set(found) == set(ROLES), (
        f"the router's arms are {sorted(found)}; the role map is {sorted(ROLES)}"
    )
    unmapped = [
        heading for heading in arm_heading_lines(readme) if heading not in set(found.values())
    ]
    assert not unmapped, (
        f"the router carries {unmapped} — headings naming no role in the map {sorted(ROLES)}. "
        f"A fork with an arm a reader cannot place themselves in is worse than three clean ones"
    )


def test_ac1_each_arm_says_what_that_reader_WANTS_not_merely_who_they_are(readme):
    """A label a reader cannot match themselves against is not self-identification. Each arm
    names the reader's *intent* — use it / vendor and re-pin it / work on it."""
    intents = {
        "consumer": ("use",),
        "vendor-integrator": ("vendor", "re-pin"),
        "developer": ("work on",),
    }
    for role, needles in intents.items():
        arm = prose(arm_section(readme, role).splitlines()[0] if arm_section(readme, role) else "")
        router = prose(router_section(readme))
        assert any(prose(n) in arm or prose(n) in router for n in needles), (
            f"the {role} arm never states that reader's intent {needles}"
        )


def test_ac1_every_arm_points_somewhere_that_RESOLVES(readme):
    """A fork whose arms point at renamed headings is worse than no fork. Every in-document
    anchor the router links is checked against the document's real heading slugs."""
    slugs = heading_slugs(readme)
    broken = [anchor for anchor in anchor_links(router_section(readme)) if anchor not in slugs]
    assert not broken, (
        f"the router links anchors that match no heading in the document: {broken} — a fork "
        f"whose arms dangle is worse than no fork"
    )


def test_ac1_the_anchor_checker_bites_on_a_renamed_heading():
    """Red proof, and the must-not-bite: the slug rule is GitHub's, so a heading with an
    em-dash and punctuation still resolves."""
    doc = "## Start here — pick your path\n\nSee [x](#developing-larkdocio).\n\n## Developing larkdocio\n"
    assert anchor_links(doc) == ["developing-larkdocio"]
    assert "developing-larkdocio" in heading_slugs(doc)
    assert "start-here--pick-your-path" in heading_slugs(doc)
    renamed = doc.replace("## Developing larkdocio", "## Working on larkdocio")
    assert "developing-larkdocio" not in heading_slugs(renamed)


def test_ac1_the_developer_arm_points_at_LD178s_EXISTING_section_unmoved(readme):
    """The third arm's target is the section LD-178 created, which **stays where it is**. The
    fork routes to it; it does not re-home it."""
    assert fd.DEVELOPMENT_HEADING in readme
    slug = _SLUG_STRIP.sub("", fd.DEVELOPMENT_HEADING.lstrip("#").strip()).lower().replace(
        " ", "-"
    )
    assert slug in anchor_links(arm_section(readme, "developer")), (
        f"the developer arm does not link {fd.DEVELOPMENT_HEADING!r} (anchor #{slug})"
    )


def test_ac1_the_consumer_arm_carries_NOTHING_about_developing_larkdocio(readme):
    """The doctrine, mechanically: the consumer arm holds no clone / setup / repo-layout
    material. (The whole consumer *half* is held to the same bar by LD-178's audience guard —
    this is the arm-level statement of it, so a regression names the arm.)"""
    arm = arm_section(readme, "consumer")
    assert arm, "the consumer arm is empty"
    for forbidden in ("./setup.sh", "Package layout", "pytest"):
        assert forbidden not in arm, (
            f"the consumer arm mentions {forbidden!r} — a consumer needs none of it"
        )
    # `git clone` is judged per LINE rather than banned outright: cloning the DEV REPO is what a
    # consumer cannot use, while cloning the shallow `dist` artifact branch is how they get the
    # wheel and IS step 0. This used to be a second, inline copy of that predicate — LD-205
    # replaced it with a call to the ONE definition in tests/front_door.py, so the arm-level
    # statement and the half-level one in tests/test_consumer_first_readme.py cannot drift.
    dev_clones = [line for _lineno, line in dev_repo_clone_lines(arm)]
    assert not dev_clones, (
        f"the consumer arm clones something other than the dist artifact branch: {dev_clones}"
    )


def test_ac1_the_arm_LEVEL_clone_check_bites_on_SAME_LINE_laundering():
    """LD-205, at the arm level: the exemption is the ``--branch`` **argument**, not the
    characters. Both laundering shapes are asserted **through a real consumer arm**, because
    this module's subject is the arm — the predicate's own unit-level bite proof is
    ``tests/test_consumer_first_readme.py::test_ac1_the_artifact_exemption_is_the_BRANCH_ARGUMENT_not_a_substring``.
    """
    honest = (
        "### Consumer — use larkdocio in your project\n\n```bash\n"
        "git clone --branch dist --depth 1 <larkdocio-url> vendor   # 0. get the wheel\n```\n"
    )
    assert not dev_repo_clone_lines(honest), "the shipped step-0 shape is not exempt"

    for laundered in (
        "git clone ssh://git@host/larkdocio.git   # 0. instead of --branch dist",
        "git clone --branch distribution ssh://git@h/larkdocio.git vendor",
    ):
        arm = honest + laundered + "\n"
        assert [line for _lineno, line in dev_repo_clone_lines(arm)] == [laundered.strip()], (
            f"a dev-repo clone smuggled into the consumer arm was exempted: {laundered!r}"
        )


def test_ac1_each_arm_is_SHORT_a_heading_and_a_handful_of_lines(readme):
    """A router that grows into three manuals is not a router. The arms stay skimmable —
    generous ceiling, because the failure mode is drift into re-explanation, not tightness."""
    for role in ROLES:
        lines = [line for line in arm_section(readme, role).splitlines() if line.strip()]
        assert len(lines) <= 22, (
            f"the {role} arm is {len(lines)} non-blank lines — an arm directs traffic, it does "
            f"not restate the section it points at"
        )


# =====================================================================
# AC3 — STEP 0: the consumer arm's first command is the one that GETS the wheel
# =====================================================================

#: The install command that used to be step 1 — and cannot be the first thing a consumer is
#: told to do, because it consumes a file nothing has produced yet.
_INSTALL = "pip install"

#: What step 0 runs. The consumer's own copy of the refresh script: it builds the wheel at the
#: latest tag and drops it (plus the guide) into ``./vendor/``.
_STEP_ZERO = "update_larkdocio.sh"


def _fences(text):
    """``[(lineno, language, body)]`` for every fenced block, in document order."""
    out, in_fence, language, body, start = [], False, "", [], 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_fence:
                out.append((start, language, "\n".join(body)))
                in_fence, body = False, []
            else:
                in_fence, language, start = True, stripped[3:].strip(), lineno
            continue
        if in_fence:
            body.append(line)
    return out


#: Either command that GETS the wheel: the ``dist`` fast path (LD-194's, and now step 0) or the
#: build-from-tag fallback. Step 0 is satisfied by *a* command that produces the wheel — which
#: one leads is :func:`test_ac4_the_build_from_tag_path_SURVIVES_in_the_arm_as_the_fallback`'s
#: subject, so this check stays about the defect it was written for: the install came first.
_WHEEL_GETTERS = ("--branch dist", _STEP_ZERO)


def test_ac3_the_consumer_arms_FIRST_command_is_step_0_not_the_install(readme):
    """The reported hole, closed and pinned. The first actionable line in the consumer arm
    produces the wheel; the install that consumes it comes after."""
    fences = _fences(arm_section(readme, "consumer"))
    assert fences, "the consumer arm shows no commands at all"
    _lineno, language, first = fences[0]
    assert language == "bash", f"the consumer arm's first fence is {language!r}, not a command"
    lines = [line for line in first.splitlines() if line.strip()]
    assert any(getter in lines[0] for getter in _WHEEL_GETTERS), (
        f"the consumer arm's first command is {lines[0]!r} — step 0, the one command that GETS "
        f"the wheel, must lead"
    )
    assert _INSTALL not in lines[0], (
        f"the consumer arm still opens at {lines[0]!r} — that consumes a wheel nothing has "
        f"produced yet, which is exactly the defect"
    )


def test_ac3_step_0_precedes_the_install_everywhere_in_the_consumer_arm(readme):
    """Order, not mere presence: an arm that installs first and explains where the wheel comes
    from afterwards has the same defect in a politer form."""
    arm = arm_section(readme, "consumer")
    assert _INSTALL in arm
    for getter in _WHEEL_GETTERS:
        assert getter in arm, f"the consumer arm lost the {getter!r} path"
        assert arm.index(getter) < arm.index(_INSTALL), (
            f"the install appears before {getter!r} in the consumer arm"
        )


def test_ac3_the_step_0_command_names_where_the_wheel_LANDS(readme):
    """Step 0 is only followable if the reader knows what it produced — the install line
    globs ``./vendor/``, so the arm has to say that is where it goes."""
    arm = arm_section(readme, "consumer")
    assert "vendor/" in arm, "the consumer arm never says the wheel lands in ./vendor/"


def test_ac3_the_step_0_check_bites_on_the_PRE_FIX_arm():
    """Red proof over the shipped-before text: an arm whose first command is the install is
    reported. Without this the assertion above could be passing vacuously."""
    pre_fix = (
        "### Consumer — use larkdocio in your project\n\n"
        "```bash\n"
        "pip install ./vendor/larkdocio-*-py3-none-any.whl    # 1. install the wheel you vendored\n"
        "```\n"
    )
    fences = _fences(pre_fix)
    assert fences and _STEP_ZERO not in fences[0][2]
    assert _INSTALL in [line for line in fences[0][2].splitlines() if line.strip()][0]


# =====================================================================
# AC4 — the `dist` fast path is ABSENT ON PURPOSE (LD-194 adds it)
# =====================================================================

def test_ac4_the_dist_FAST_PATH_is_now_the_consumer_arms_step_0(readme):
    """**This guard was inverted by LD-194, which is the whole point of it.**

    LD-193 asserted the README referenced no ``dist`` branch, because the branch did not exist
    and a README pointing at an absent branch is the dangling-pointer defect. LD-194 creates the
    branch (``release.sh`` publishes it after the tag push), so the reference becomes correct —
    and the guard flips to demand it, rather than being deleted. Flipping rather than deleting is
    what keeps the claim guarded in *both* eras: before, the line could not appear by drift;
    now, it cannot silently disappear.
    """
    arm = arm_section(readme, "consumer")
    assert "--branch dist" in arm, (
        "the consumer arm no longer offers the dist fast path — the one-command entry the "
        "distribution branch exists to provide"
    )
    assert "--depth 1" in arm, (
        "the dist clone is not shallow in the arm — `--depth 1` is what makes it cheap, and "
        "the branch's replace-history policy assumes it"
    )
    lineno, language, first = _fences(arm, )[0]
    assert language == "bash"
    commands = [line for line in first.splitlines() if line.strip()]
    assert "--branch dist" in commands[0], (
        f"step 0 is no longer the dist clone: {commands[0]!r}"
    )


def test_ac4_the_build_from_tag_path_SURVIVES_in_the_arm_as_the_fallback(readme):
    """The inserted line is an *addition*, not a replacement. The updater has to stay: it is the
    vendor-integrator's command and the fallback whenever ``dist`` is absent or stale, and the
    updater script itself falls back to exactly it — so an arm offering only the fast path would
    describe a narrower library than the one that ships."""
    arm = arm_section(readme, "consumer")
    assert _STEP_ZERO in arm, (
        "the build-from-tag path was removed from the consumer arm; it remains the fallback"
    )
    commands = [line for line in _fences(arm)[0][2].splitlines() if line.strip()]
    dist_at = next(i for i, c in enumerate(commands) if "--branch dist" in c)
    updater_at = next(i for i, c in enumerate(commands) if _STEP_ZERO in c)
    assert dist_at < updater_at, (
        "the dist fast path must be offered ABOVE the build-from-tag command, which is the "
        "fallback rather than the first thing to try"
    )


# =====================================================================
# AC6 — the fork POINTS, it does not duplicate
# =====================================================================

#: The Quickstart's own material — the six numbered steps and the two real handshakes. An arm
#: that restated any of it would create a second copy to rot.
_QUICKSTART_ONLY = ("get_docx_content(", "dry_run(", "apply(")


def test_ac6_no_arm_restates_the_quickstarts_handshakes(readme):
    """One copy of every instruction: the arms route to the Quickstart, which keeps the real
    read and the real write."""
    for role in ROLES:
        arm = arm_section(readme, role)
        duplicated = [needle for needle in _QUICKSTART_ONLY if needle in arm]
        assert not duplicated, (
            f"the {role} arm restates {duplicated}, which belongs to the Quickstart — point at "
            f"the section instead of copying it"
        )


def test_ac6_the_quickstart_still_owns_those_handshakes(readme):
    """The other half: "not duplicated" must not be reached by deleting the original."""
    lines = readme.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## Quickstart"))
    end = next((i for i, line in enumerate(lines[start + 1:], start=start + 1)
                if line.startswith("## ")), len(lines))
    quickstart = "\n".join(lines[start:end])
    missing = [needle for needle in _QUICKSTART_ONLY if needle not in quickstart]
    assert not missing, f"the Quickstart no longer carries {missing} — it was moved, not kept"


def test_ac6_the_development_heading_appears_exactly_once(readme):
    """The developer arm points at one target. Two headings with the same slug make the
    anchor ambiguous and the AC1 resolution check meaningless."""
    assert readme.count(f"\n{fd.DEVELOPMENT_HEADING}\n") == 1


# =====================================================================
# AC5 — the vendor-integrator arm names the ACCESSORS, not just the files
# =====================================================================

def test_ac5_the_vendor_arm_names_the_release_document_ACCESSORS(readme):
    """The defect an earlier issue fixed was a citation a wheel-only reader could not open.
    A re-pinning integrator is told how to read the notes **from the wheel**, not only from a
    ``vendor/`` drop that a plain ``pip install`` never produces."""
    arm = prose(arm_section(readme, "vendor-integrator"))
    for accessor in ("release_notes()", "changelog()"):
        assert prose(accessor) in arm, (
            f"the vendor-integrator arm never names {accessor} — the one way to read the notes "
            f"from an installed wheel"
        )


def test_ac5_the_vendor_arm_carries_the_refresh_and_check_entry_points(readme):
    """Its own role's commands: refresh, report-only check, and the re-pin that follows."""
    arm = arm_section(readme, "vendor-integrator")
    for needle in (_STEP_ZERO, "--check"):
        assert needle in arm, f"the vendor-integrator arm never mentions {needle}"
    assert prose("re-pin") in prose(arm), "the vendor-integrator arm never mentions re-pinning"


# =====================================================================
# AC7 — the BUILT wheel's METADATA carries the router, in the first screenful
# =====================================================================

def _metadata_body():
    wheel = fd.built_wheel()
    if wheel is None:
        return None
    return fd.wheel_metadata(wheel).split("\n\n", 1)[1]


def test_ac7_the_shipped_metadata_body_opens_with_the_router():
    """The artifact is the deliverable: a source-only assertion would pass while ``pip show``
    still handed the reader an unforked document. Skips on a plain checkout;
    ``python -m build`` arms it."""
    body = _metadata_body()
    if body is None:
        pytest.skip("no built wheel for the declared version in dist/ — run `python -m build`")
    assert ROUTER_HEADING in body, "the shipped METADATA body carries no role router"
    first = next(line.strip() for line in body.splitlines() if line.startswith("## "))
    assert first == ROUTER_HEADING, f"the shipped METADATA body's first section is {first!r}"


def test_ac7_a_wheel_only_reader_reaches_the_router_in_the_FIRST_SCREENFUL():
    """The reader ``pip show`` hands the body to must be able to place themselves before
    scrolling — that is the entire value of a traffic director."""
    body = _metadata_body()
    if body is None:
        pytest.skip("no built wheel for the declared version in dist/ — run `python -m build`")
    screenful = fd.first_screenful(body, 24)
    assert ROUTER_HEADING in screenful, (
        "the router is not in the shipped body's first screenful — a reader has to scroll to "
        f"find out which parts are theirs:\n{screenful}"
    )
    named = [role for role in ROLES if prose(role) in prose(screenful)]
    assert len(named) == len(ROLES), f"the first screenful names only {named}"


def test_ac7_the_router_survives_in_the_METADATA_with_its_arms_resolving():
    """The arms are anchors, and an anchor is only useful if its target travelled too."""
    body = _metadata_body()
    if body is None:
        pytest.skip("no built wheel for the declared version in dist/ — run `python -m build`")
    slugs = heading_slugs(body)
    broken = [anchor for anchor in anchor_links(router_section(body)) if anchor not in slugs]
    assert not broken, f"the SHIPPED router links anchors absent from the shipped body: {broken}"


# =====================================================================
# LD-210 AC8 — AC6's repetitions are PINNED as intentional, both ways
# =====================================================================
#
# LD-193's AC6 carve-out asked for exactly this: *"if a short line is deliberately repeated for
# flow, that the repetition is intentional and pinned."* AC6's guard above pins only the
# Quickstart **handshakes** — the lines an arm must NOT restate — so the repetitions the router
# actually does introduce were unpinned in **both** directions: a new one could arrive unnoticed,
# and a load-bearing one could be deleted from either end.
#
# Every one of them is MANDATED by AC1's per-arm content list (the arm has to be followable on
# its own), which is why they are intentional rather than tolerated. Located STRUCTURALLY, by
# heading — the review's 44-46 / 388-390 offsets were already stale relative to LD-194's step-0
# insertion, and line numbers are exactly what this pin must not depend on.

#: Where a repetition's second copy lives. Matched as a heading PREFIX so a heading's tail can be
#: reworded without unpinning the repetition.
_QUICKSTART = "## Quickstart"
_CONSUMING = "### Consuming larkdocio"

#: ``(command, router arms carrying it, the section outside the router that also carries it,
#: why it is mandated)``. The command is the fence line with its trailing ``#`` comment stripped,
#: because the comment is deliberately tailored per site — the COMMAND is what is repeated.
_PINNED_REPETITIONS = (
    (
        "scripts/update_larkdocio.sh", ("consumer", "vendor-integrator"), _CONSUMING,
        "AC1's content list mandates the refresh entry point in the vendor arm, and the "
        "consumer arm's step 0 offers it as the build-it-yourself alternative to the dist "
        "clone. § Consuming larkdocio is the walkthrough both arms point AT, so it keeps the "
        "same fence.",
    ),
    (
        "scripts/update_larkdocio.sh vX.Y.Z", ("vendor-integrator",), _CONSUMING,
        "The specific-tag form: re-pinning to a named tag is the vendor-integrator's whole "
        "job, so the arm cannot omit it and point instead.",
    ),
    (
        "scripts/update_larkdocio.sh --check", ("vendor-integrator",), _CONSUMING,
        "AC1's vendor-arm content list mandates the report-only check, and "
        "test_ac5_the_vendor_arm_carries_the_refresh_and_check_entry_points requires it in "
        "the arm itself.",
    ),
    (
        "pip install ./vendor/larkdocio-*-py3-none-any.whl", ("consumer",), _QUICKSTART,
        "AC3's whole point: step 0 has to be shown ABOVE the install, so the consumer arm "
        "carries the install line the step-0 fence leads into. The Quickstart keeps it as its "
        "own step 1.",
    ),
    (
        "import larkdocio", ("consumer",), _QUICKSTART,
        "The two-line read-the-manual handshake has to be runnable from the arm — an arm that "
        "pointed at the Quickstart for `import larkdocio` would be pointing for the sake of "
        "not repeating a stdlib-shaped line.",
    ),
    (
        "print(larkdocio.guide())", ("consumer",), _QUICKSTART,
        "Same handshake. AC6 forbids an arm restating the Quickstart's real READ and WRITE "
        "(`get_docx_content(` / `dry_run(` / `apply(`); printing the packaged guide is the "
        "arm's own payload, not one of those.",
    ),
)


def _section_by_prefix(text, prefix):
    """The section under the first heading starting with ``prefix`` — structural, not by line."""
    heading = next(
        (line.strip() for line in text.splitlines() if line.strip().startswith(prefix)), None
    )
    assert heading is not None, f"the README no longer carries a heading starting {prefix!r}"
    return _section(text, heading)


def _fence_commands(text):
    """Every fenced-code line in ``text``, trailing ``#`` comment stripped."""
    commands, in_fence = [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence and line.strip():
            commands.append(re.split(r"\s{2,}#", line.strip())[0].strip())
    return commands


def router_repetitions(text):
    """Every fenced command inside the router that ALSO appears in a fence outside it.

    This is what "the repetitions the router introduces" means, expressed as data rather than as
    a claim in a handoff note.
    """
    router = router_section(text)
    outside = set(_fence_commands(text.replace(router, "")))
    return {command for command in _fence_commands(router) if command in outside}


def test_ac8_every_repetition_the_router_introduces_is_PINNED_with_its_reason(readme):
    """AC8, the completeness direction: the set of commands the router repeats is **exactly**
    the pinned set. A new duplicated fence line reddens here and has to be either removed or
    pinned with the reason it is mandated — which is the carve-out LD-193's AC6 asked for and
    did not get."""
    pinned = {command for command, _arms, _outside, _reason in _PINNED_REPETITIONS}
    found = router_repetitions(readme)
    assert found == pinned, (
        f"unpinned repetitions the router introduces: {sorted(found - pinned)}; pinned "
        f"repetitions the router no longer introduces: {sorted(pinned - found)}"
    )
    for command, _arms, _outside, reason in _PINNED_REPETITIONS:
        assert len(reason) > 40, f"{command!r} is pinned without a reason worth the pin"


@pytest.mark.parametrize(
    "command,arms,outside", [(c, a, o) for c, a, o, _r in _PINNED_REPETITIONS],
    ids=[c for c, _a, _o, _r in _PINNED_REPETITIONS],
)
def test_ac8_each_pinned_repetition_is_LOAD_BEARING_at_both_ends(readme, command, arms, outside):
    """AC8, the load-bearing direction: a pinned repetition is **mandated**, not merely
    tolerated, so deleting either copy reddens. Without this half, "pinned as intentional" would
    be a licence to delete."""
    for role in arms:
        assert command in _fence_commands(arm_section(readme, role)), (
            f"the {role} arm no longer carries {command!r} — it is mandated by that arm's "
            f"content list, not tolerated"
        )
    assert command in _fence_commands(_section_by_prefix(readme, outside)), (
        f"{outside} no longer carries {command!r} — the arm points there, so removing the "
        f"second copy makes the arm point at nothing"
    )
