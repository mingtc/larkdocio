# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""The permissions DOCUMENTS are projections of the registry — never the reverse.

Two documents, two roles, one source:

* the maintainer's per-call-site matrix, ``PERMISSIONS.md`` at the repository root, in the
  same living-matrix register as ``BLOCKS.md`` / ``SHEETS.md``;
* the consumer's permissions section inside the shipped guide, which covers only what a
  consumer can actually call and says it in their terms.

Both carry a **generated region** that is held byte-identical to the render, so a scope
string cannot be typed into a document and quietly disagree with the code. The unification
half is here too: every scope-string literal anywhere in the guarded text must be a scope
the registry knows, and every hand-maintained file that names one must also point at the
single source — so a reader never mistakes a local copy for the authority.
"""
import ast
import fnmatch
import os
import pathlib
import re

import pytest

from larkdocio import guide, permissions as perm
import private_tree  # noqa: E402  (LD-685)

# LD-370 — CONFORMANCE-tier: the generated permission projections are the consumer's paste-ready scope list.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEV_MATRIX = REPO_ROOT / "PERMISSIONS.md"

#: A Lark scope string: a family, a colon, then one to three more ``:``/``.``-joined segments
#: (``docx:document``, ``contact:user.base:readonly``, ``board:whiteboard:node:read``).
#: Anchored on a known family set so ordinary prose (``note: something``) cannot match.
#:
#: The segment count is deliberately generous: an earlier version capped it and silently
#: TRUNCATED ``board:whiteboard:node:read`` to ``board:whiteboard:node``, so the guard was
#: comparing a mangled string against the registry. A pattern that mis-reads the thing it
#: guards is worse than no pattern, so the four-segment form is pinned by its own test below.
SCOPE_LITERAL = re.compile(
    r"\b(?:docx|drive|sheets|contact|wiki|board|directory|admin|application|bitable|im)"
    r"(?::[a-z_]+(?:\.[a-z_]+)*){1,3}\b"
)

#: How a file points at the single source. Any one of these is enough.
SOURCE_POINTERS = ("larkdocio.permissions", "PERMISSIONS.md", "permission registry")


# --------------------------------------------------------------------------- #
# THE CORPUS — derived from what the repository TRACKS, minus named exclusions. #
#                                                                              #
# The rule, and the reason it is a derivation rather than a list: a hand-listed  #
# allowlist cannot notice a file it was never told about, so a scope asserted in  #
# an unlisted file is invisible however carefully the list was written. Every      #
# tracked file is therefore in the corpus UNLESS it falls in one of the four       #
# classes below — and each class is named WITH its reason, the same standard the   #
# registry holds itself to when it records an empty requirement.                  #
# --------------------------------------------------------------------------- #

#: Excluded directory prefixes, each with the reason it cannot be held to the membership rule.
EXCLUDED_PREFIXES = {
    "dev/": (
        "THE EVIDENCE RECORD. Probe captures quote Lark's own denial bodies verbatim, so they "
        "necessarily name scopes this app does not hold and the registry does not require. "
        "Editing a capture to satisfy a guard would falsify the evidence the registry is "
        "built on."
    ),
    "progress/": (
        "THE BOARD HISTORY. Issue files and review notes record what was said at the time, "
        "including scope strings that were later corrected. Rewriting history to match today's "
        "registry would destroy the record of the correction."
    ),
    "requirements/": (
        "Specs are historical statements of intent, superseded by what shipped; the same "
        "append-only reasoning as the board history."
    ),
    "tests/": (
        "A GUARD'S OWN FIXTURES. The red proofs in this very file must be able to name a "
        "deliberately INVALID scope (that is what proves the guard bites), so the test tree "
        "cannot be held to the rule it enforces without making the rule unprovable."
    ),
}

#: Excluded individual files, each with its reason.
EXCLUDED_FILES = {
    "progress.md": "the session log — append-only history, as above.",
    "ARCHIVE.md": "the archive index — append-only history, as above.",
    "CHANGELOG.md": (
        "append-only RELEASE history: a shipped release's entry describes what that release "
        "said, and amending it would misreport a version that is already in consumers' hands."
    ),
    "RELEASE_NOTES.md": "append-only release history, as above.",
    "src/larkdocio/CHANGELOG.md": "a byte-identical packaged copy of the root changelog.",
    "src/larkdocio/RELEASE_NOTES.md": "a byte-identical packaged copy of the root notes.",
}


def _ignore_rules():
    """The repository's **own** ``.gitignore``, parsed — patterns paired with their negations.

    Read out of the tree rather than hand-copied, so the one place that declares what is not
    part of the repository stays the only place: add ``htmlcov/`` there and the corpus walk
    below honours it with no second list to update.
    """
    rules = []
    for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        rules.append((line.lstrip("!").rstrip("/"), negated))
    return rules


IGNORE_RULES = _ignore_rules()


def _ignored(rel):
    """Is ``rel`` outside the repository — build output, a virtualenv, a cache, a secret?

    Last matching rule wins, so ``.env.*`` followed by ``!.env.example`` re-includes the
    example the way git does. A pattern with a slash is matched against the path (and each of
    its parent directories); a bare pattern is matched against any single component, which is
    how ``__pycache__/`` or ``*.pyc`` reach any depth.
    """
    parts = rel.split("/")
    ancestors = ["/".join(parts[:n]) for n in range(1, len(parts) + 1)]
    verdict = False
    for pattern, negated in IGNORE_RULES:
        if "/" in pattern:
            hit = any(fnmatch.fnmatch(path, pattern) for path in ancestors)
        else:
            hit = any(fnmatch.fnmatch(part, pattern) for part in parts)
        if hit:
            verdict = not negated
    return verdict or parts[0] == ".git"


def _repo_files(root=REPO_ROOT):
    """Every file the repository carries: the tree walked, minus what ``.gitignore`` disowns.

    **Why this is a walk and not ``git ls-files``.** The set wanted here is "the repository's
    own files", and asking git for it made the corpus depend on the state of a live checkout —
    the one shape ``tests/test_no_test_reads_live_git.py`` forbids suite-wide, and for a real
    reason: a guard that must run identically on every branch cannot be built on a question
    only a particular working copy can answer. The walk asks the **tree** instead, and defers
    to the repository's own ``.gitignore`` for what is not part of it, so build output,
    virtualenvs and caches still cannot drift **into** the corpus.

    **The one difference, and which way it fails.** An untracked-but-unignored scratch file
    would join the corpus, where ``git ls-files`` would have left it out. That direction is the
    safe one: it can only make a guard fire on a file a developer left lying around (a loud,
    locally-explained red), never hide a real assertion — and the corpus can still never
    **miss** a repository file, which is the failure this derivation exists to prevent. The
    churn-prone trees (``dev/``, ``progress/``, ``requirements/``, ``tests/``) are excluded
    from the corpus by name anyway.

    **``root`` is a parameter, and only for LD-358.** The default is and stays the working
    tree; a red proof passes a ``tmp_path`` copy so it can mutate a corpus file without any
    sibling test — on another xdist worker, mid-read — seeing the mutation. The ignore rules
    are the repository's own either way, which is what keeps the copied corpus equivalent.
    """
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = pathlib.Path(dirpath)
        dirnames[:] = sorted(
            name for name in dirnames
            if not _ignored((here / name).relative_to(root).as_posix()))
        for name in filenames:
            rel = (here / name).relative_to(root).as_posix()
            if not _ignored(rel):
                found.append(rel)
    return sorted(found)


def _excluded(rel):
    """The reason ``rel`` is out of the corpus, or ``None`` if it is in."""
    for prefix, reason in EXCLUDED_PREFIXES.items():
        if rel.startswith(prefix):
            return reason
    return EXCLUDED_FILES.get(rel)


def corpus(root=REPO_ROOT):
    """``{relative path: hand-maintained text}`` — the derived corpus, generated regions
    stripped.

    A generated region is not an assertion anyone could get wrong: it is a projection, held
    byte-identical to the registry by its own test above. Stripping it is what makes the count
    below a measure of what a HUMAN maintains.

    ``root`` defaults to the working tree; see ``_repo_files`` for why a red proof overrides it.

    **The encoding is pinned, and a file that will not decode is a FAILURE (LD-660).** This read
    used to be a bare ``read_text()`` inside ``except (OSError, UnicodeDecodeError): continue``,
    which is the worst shape an instrument can have: on a host whose locale is not UTF-8, every
    file that would not decode was **silently dropped from the corpus**, and this guard — the one
    that holds the shipped permissions documentation true — reported green having read almost
    nothing. Measured 2026-09-09 at this pin: 435 corpus files all decode as UTF-8, but **32 of
    them do not decode as cp1252**, so on a Windows-default host the corpus lost 32 files
    including the shipped guide, with no signal at all. Now the codec is UTF-8 whatever the host says, and an
    undecodable file raises with its own name in the message. Nothing is exempt — if a file ever
    genuinely must be skipped it belongs in :data:`EXCLUDED_FILES` with a reason, where a reader
    can see it.

    ``OSError`` still propagates too: this corpus is walked out of the tree that was just read,
    so a file that cannot be opened means the tree moved under the walk, which is a real failure
    and not something to shrug past.
    """
    out = {}
    for rel in _repo_files(root):
        if _excluded(rel):
            continue
        path = root / rel
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise AssertionError(
                f"{rel} is in the permissions corpus but does not decode as UTF-8 ({exc}). "
                "The corpus must not silently shrink: either the file is text and is broken, or "
                f"it belongs in EXCLUDED_FILES with a reason. Corpus read so far: {len(out)} "
                "file(s)."
            ) from exc
        out[rel] = _strip_generated(text)
    return out


def corpus_as_read_on_a_host_whose_locale_is(encoding, root=REPO_ROOT):
    """The corpus this guard would have built on a host whose locale codec is ``encoding``.

    **How the simulation is faithful.** The pre-LD-660 body was exactly
    ``read_text()`` — i.e. ``read_bytes().decode(locale.getencoding())`` — wrapped in
    ``except (OSError, UnicodeDecodeError): continue``. The *only* host-dependent input to that
    expression is the codec name, so substituting the codec reproduces the old behaviour on that
    host byte for byte, without needing a Windows machine or a re-exec under a different
    ``LC_ALL`` (which cannot even be done for cp932 on this platform). It reproduces the SILENT
    DROP too, which is the property under test.

    Used by the red proof that measures how blind the guard was; never by a real assertion.
    """
    out = {}
    for rel in _repo_files(root):
        if _excluded(rel):
            continue
        try:
            text = (root / rel).read_bytes().decode(encoding)
        except (OSError, UnicodeDecodeError):
            continue  # the old shape: silently dropped, exactly the defect
        out[rel] = _strip_generated(text)
    return out


def _strip_generated(text):
    for begin, end in ((perm.CONSUMER_REGION_BEGIN, perm.CONSUMER_REGION_END),
                       (perm.DEV_REGION_BEGIN, perm.DEV_REGION_END)):
        region = perm.region_of(text, begin.replace(" -->", ""), end)
        if region:
            text = text.replace(region, "")
    return text


def corpus_mentions(root=REPO_ROOT):
    """``{relative path: [scope literal, …]}`` for every corpus file that names one."""
    found = {}
    for rel, text in corpus(root).items():
        hits = SCOPE_LITERAL.findall(text)
        if hits:
            found[rel] = hits
    return found


def _text(rel):
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _hand_maintained_text(rel):
    """``rel``'s text with any GENERATED region removed.

    The measurement below counts what a **human maintains**, so generated text must not be
    counted: a projected matrix contains many scope strings by design and none of them is a
    place anyone could introduce a disagreement.
    """
    text = _text(rel)
    for begin, end in (
        (perm.CONSUMER_REGION_BEGIN, perm.CONSUMER_REGION_END),
        (perm.DEV_REGION_BEGIN, perm.DEV_REGION_END),
    ):
        region = perm.region_of(text, begin.replace(" -->", ""), end)
        if region:
            text = text.replace(region, "")
    return text


def _known_scopes():
    """Every scope string the registry knows — the endpoint table plus the captured
    denials, which are real scope strings even where no shipped call needs them."""
    known = {scope.scope
             for _prefix, _mode, scopes, _note in perm.ENDPOINT_SCOPES
             for scope in scopes}
    known |= {denial.scope for denial in perm.OBSERVED_DENIALS}
    return known


# --------------------------------------------------------------------------- #
# The maintainer's matrix.                                                     #
# --------------------------------------------------------------------------- #

def test_the_dev_matrix_exists_and_frames_a_generated_region():
    text = DEV_MATRIX.read_text(encoding="utf-8")
    assert perm.DEV_REGION_BEGIN.replace(" -->", "") in text
    assert perm.DEV_REGION_END in text


def test_the_dev_matrix_region_is_BYTE_IDENTICAL_to_the_projection():
    """The strongest form of "the registry projects into the document": not a cross-check of
    two lists, but the same bytes. A hand edit inside the region reddens immediately."""
    region = perm.region_of(
        DEV_MATRIX.read_text(encoding="utf-8"), perm.DEV_REGION_BEGIN.replace(" -->", ""),
        perm.DEV_REGION_END)
    assert region, "PERMISSIONS.md carries no generated region"
    assert region == perm.dev_permissions_markdown(), (
        "PERMISSIONS.md's generated region has drifted from the registry — regenerate it "
        f"with:  {perm.DEV_REGENERATE}")


def test_the_dev_matrix_carries_its_own_regeneration_command():
    """An instruction that lives away from the thing it regenerates goes stale. This one is
    inside the region it regenerates."""
    text = DEV_MATRIX.read_text(encoding="utf-8")
    assert perm.DEV_REGENERATE in text


def test_the_dev_matrix_names_every_api_using_call_site():
    """The other direction of the projection: the document cannot omit a row. A call site
    missing from the matrix is exactly the gap this issue closes."""
    region = perm.region_of(
        DEV_MATRIX.read_text(encoding="utf-8"), perm.DEV_REGION_BEGIN.replace(" -->", ""),
        perm.DEV_REGION_END)
    for (surface_id, name), row in perm.permission_registry().items():
        if not row.api_using:
            continue
        assert f"| `{surface_id}` | `{name}` |" in region, (
            f"{surface_id}.{name} reaches the Lark API and has no row in PERMISSIONS.md")


def test_the_dev_matrix_states_every_unknown_requirement_with_its_reason():
    """The honest-unknown discipline, in the document: an endpoint whose requirement is
    empty appears with the reason, so no reader can read the silence as "needs nothing"."""
    region = perm.region_of(
        DEV_MATRIX.read_text(encoding="utf-8"), perm.DEV_REGION_BEGIN.replace(" -->", ""),
        perm.DEV_REGION_END)
    empties = [(prefix, note) for prefix, _mode, scopes, note in perm.ENDPOINT_SCOPES
               if not scopes]
    assert empties
    for prefix, note in empties:
        assert f"| `{prefix}` |" in region, f"{prefix} has no recorded-unknown row"
        assert note in region


def test_the_dev_matrix_carries_the_captured_denial_bodies():
    region = perm.region_of(
        DEV_MATRIX.read_text(encoding="utf-8"), perm.DEV_REGION_BEGIN.replace(" -->", ""),
        perm.DEV_REGION_END)
    for denial in perm.OBSERVED_DENIALS:
        assert f"`{denial.scope}`" in region
        assert f"`{denial.code}`" in region


def test_the_dev_matrix_states_the_never_widens_rule():
    assert perm.NEVER_WIDENS in DEV_MATRIX.read_text(encoding="utf-8")


def test_the_dev_matrix_has_exactly_one_begin_and_one_end_fence_in_order():
    """LD-253: a stray duplicate END fence sat AFTER the region, invisible to the
    byte-identity check above because `region_of()` uses `find` (the first match). Pin the
    fence COUNT directly so a duplicate or misplaced fence reddens even when it sits outside
    the guarded slice."""
    text = DEV_MATRIX.read_text(encoding="utf-8")
    begin_marker = perm.DEV_REGION_BEGIN.replace(" -->", "")
    assert text.count(begin_marker) == 1, "expected exactly one BEGIN fence in PERMISSIONS.md"
    assert text.count(perm.DEV_REGION_END) == 1, "expected exactly one END fence in PERMISSIONS.md"
    assert text.index(begin_marker) < text.index(perm.DEV_REGION_END), (
        "the BEGIN fence must precede the END fence")


# --------------------------------------------------------------------------- #
# The consumer's section, inside the shipped guide.                            #
# --------------------------------------------------------------------------- #

def test_the_guide_region_is_BYTE_IDENTICAL_to_the_consumer_projection():
    region = perm.region_of(
        guide(full=True), perm.CONSUMER_REGION_BEGIN.replace(" -->", ""), perm.CONSUMER_REGION_END)
    assert region, "the guide carries no generated permissions region"
    assert region == perm.consumer_permissions_markdown(), (
        "the guide's permissions region has drifted from the registry — regenerate it "
        f"with:  {perm.CONSUMER_REGENERATE}")


def test_the_guide_region_has_exactly_one_begin_and_one_end_fence_in_order():
    """The consumer-side twin of the dev-matrix fence-count guard above (LD-253)."""
    text = guide(full=True)
    begin_marker = perm.CONSUMER_REGION_BEGIN.replace(" -->", "")
    assert text.count(begin_marker) == 1, "expected exactly one BEGIN fence in the guide"
    assert text.count(perm.CONSUMER_REGION_END) == 1, "expected exactly one END fence in the guide"
    assert text.index(begin_marker) < text.index(perm.CONSUMER_REGION_END), (
        "the BEGIN fence must precede the END fence")


def test_the_consumer_section_covers_every_surface_a_consumer_can_reach():
    from larkdocio import capabilities

    region = perm.region_of(
        guide(full=True), perm.CONSUMER_REGION_BEGIN.replace(" -->", ""), perm.CONSUMER_REGION_END)
    for surface_id in capabilities(full=True)["surfaces"]:
        assert f"`{surface_id}`" in region, f"the consumer section omits {surface_id}"


def test_the_consumer_section_answers_the_two_questions_a_scopeless_reader_HAS():
    """Read cold, by someone holding no scopes at all, it has to answer *what will fail* and
    *what do I ask my administrator for*. Both are structural, so both are assertable."""
    region = perm.region_of(
        guide(full=True), perm.CONSUMER_REGION_BEGIN.replace(" -->", ""), perm.CONSUMER_REGION_END)
    assert "Must hold" in region, "it must say which scopes are non-negotiable"
    assert "Optional" in region and "What you lose" in region, (
        "it must say what is lost rather than only that something is optional")
    assert "administrator" in region, "it must say who grants a scope"
    assert perm.NEVER_WIDENS in region


def _consumer_region():
    return perm.region_of(
        guide(full=True), perm.CONSUMER_REGION_BEGIN.replace(" -->", ""),
        perm.CONSUMER_REGION_END)


def _rows_for(region, surface_id):
    return [line for line in region.splitlines() if line.startswith(f"| `{surface_id}` |")]


_MUST_HOLD_ROW_TAIL = "| — | — | no scope observed demanded |"


def test_ld571_every_surface_with_NO_REQUIRED_SCOPE_carries_THE_MUST_HOLD_ROW():
    """LD-571 (AC5a) — the one thing that was genuinely broken.

    The honest *"no scope observed demanded"* row was emitted only for a surface with **nothing
    to ask for at all**, so a surface whose scopes are all *optional* lost the only statement in
    the table about what it MUST hold: ``drive-read`` got the row, ``sheets-read`` and
    ``sheets-write`` did not, and the difference is invisible to a reader — *"nothing is
    required"* and *"nobody wrote it down"* look identical when neither is printed.

    Derived from the payload, in both directions, so this cannot rot into a list of two ids.
    """
    from larkdocio import capabilities

    region = _consumer_region()
    surfaces = capabilities(full=True)["surfaces"]
    no_required = [sid for sid, s in surfaces.items() if not s["credentials"]["scopes"]]
    optional_only = [sid for sid in no_required
                     if surfaces[sid]["credentials"]["optional_scopes"]]
    assert optional_only, (
        "no surface has optional scopes and no required ones any more — this guard is only "
        "meaningful while that shape exists, so re-read it rather than deleting it")
    for surface_id in no_required:
        assert any(line.endswith(_MUST_HOLD_ROW_TAIL) for line in _rows_for(region, surface_id)), (
            f"{surface_id} requires no scope and the table never says so; its rows are "
            f"{_rows_for(region, surface_id)}")


def test_ld571_a_surface_that_DOES_require_a_scope_gets_NO_must_hold_row():
    """The inverse, so the row cannot quietly become noise printed on every surface — it is a
    statement about an absence, and it is false wherever something IS required."""
    from larkdocio import capabilities

    region = _consumer_region()
    for surface_id, surface in capabilities(full=True)["surfaces"].items():
        if not surface["credentials"]["scopes"]:
            continue
        offenders = [line for line in _rows_for(region, surface_id)
                     if line.endswith(_MUST_HOLD_ROW_TAIL)]
        assert not offenders, (
            f"{surface_id} requires {surface['credentials']['scopes']} and the table also says "
            f"no scope was observed demanded: {offenders}")


def test_ld571_each_TABLE_says_WHICH_QUESTION_IT_ANSWERS():
    """LD-571 (AC5b) — the legibility half, and the reason the two projections *looked* like
    they disagreed when they never did.

    The surface table answers a **per-SURFACE** question (what stops working, and what merely
    degrades); ``preflight``'s derive-only answer is **per-OPERATION** (what one call needs to be
    made at all). A scope can be optional for a surface and required by one of its calls — the
    registry's own vocabulary for that is asserted here rather than paraphrased, and the
    programmatic spelling of the per-call question is named by its real function name so a
    rename cannot leave the sentence pointing at nothing.
    """
    from larkdocio import preflight

    region = _consumer_region()
    assert "per-SURFACE" in region and "per-OPERATION" in region, (
        "neither table says which question it answers, which is how one reader concluded the "
        "two projections contradicted each other")
    assert "per-OPERATION" in perm.Permissions.__doc__, (
        "the label no longer uses the registry's own word for the per-call answer — the "
        "vocabulary is authored on Permissions and quoted here, not invented in the table")
    assert preflight.requirements_for_operations.__name__ in region, (
        "the table does not name the call that answers the per-operation question in code")


def _label_paragraph(region: str, marker: str) -> str:
    """The one paragraph of the generated region that announces which question a table
    answers — located by its own announcement rather than by a line number, so the arms
    below survive any edit above them."""
    paragraphs = [p for p in region.split("\n\n") if marker in p]
    assert len(paragraphs) == 1, (
        f"expected exactly one paragraph announcing {marker!r}, found {len(paragraphs)}")
    return paragraphs[0]


#: A LABEL may not make any of these claims, because the per-call table is not a table of
#: calls that stop working: most of its rows are ``degrades=True`` scopes whose absence costs
#: part of an answer, and one is ``field_level`` — the call SUCCEEDS and the fields come back
#: empty. The first attempt at the which-question label said "that call does not run at all"
#: directly above such rows, contradicting the field-level and per-scope-loss paragraphs of
#: the SAME generated region. Reviewable-by-eye is what let that ship; this is the bite.
_HARD_FAILURE_CLAIMS = (
    "does not run", "will not run", "never runs", "cannot be made", "cannot be called",
    "call fails", "calls fail", "will fail", "would fail", "fails outright", "refuses",
)


def test_ld571_NO_which_question_LABEL_CLAIMS_A_HARD_FAILURE_while_a_row_DEGRADES():
    """LD-571 (AC5b) — the label says which question a table answers; it must not also
    predict what a missing scope costs, because that is per row and the registry knows it.

    ``Scope.degrades`` and ``Scope.field_level`` are the registry's own discriminators, and
    they are what makes a blanket *"the call does not run"* false: measured here, and derived
    so the premise cannot silently vanish. Where absence actually costs something is written
    once per scope in the loss list, which is where both labels route.
    """
    from larkdocio import capabilities

    surfaces = capabilities(full=True)["surfaces"]
    degrading = [
        (surface_id, name, scope.scope)
        for (surface_id, name), row in perm.permission_registry().items()
        for scope in row.scopes
        if scope.degrades and scope.scope not in surfaces[surface_id]["credentials"]["scopes"]
    ]
    assert degrading, (
        "no per-call row carries a degrading scope any more — re-read this guard rather than "
        "deleting it; while such a row exists, a label that predicts a hard failure is false")

    region = _consumer_region()
    for marker in ("THIS TABLE ANSWERS THE per-SURFACE QUESTION",
                   "THIS TABLE ANSWERS THE per-OPERATION QUESTION"):
        label = _label_paragraph(region, marker).lower()
        offenders = [phrase for phrase in _HARD_FAILURE_CLAIMS if phrase in label]
        assert not offenders, (
            f"the {marker!r} label claims {offenders} while {len(degrading)} per-call row(s) "
            f"degrade instead of failing (e.g. {degrading[0]}) — and the same generated region "
            "says so itself, in the field-level paragraph and the per-scope loss list")


def test_ld571_the_per_OPERATION_LABEL_QUOTES_THE_REGISTRYS_OWN_DISCRIMINATOR():
    """The reason the first label was false is that it was a **fourth hand-typed statement**
    of a rule the registry already states on :class:`~larkdocio.permissions.Scope`. So it is
    authored once, quoted into the table, and pinned present-side: the constant must still be
    a substring of the docstring it was lifted from, and must still reach the label."""
    normalized_docstring = " ".join(perm.Scope.__doc__.split())
    assert perm._DEGRADES_DISCRIMINATOR in normalized_docstring, (
        "the quoted discriminator is no longer what Scope's docstring says — one of the two "
        "was edited alone, which is exactly the drift that produced the false label")

    label = _label_paragraph(_consumer_region(), "THIS TABLE ANSWERS THE per-OPERATION QUESTION")
    assert perm._DEGRADES_DISCRIMINATOR in " ".join(label.split()), (
        "the per-operation label no longer carries the registry's own reason a scope can be "
        "optional at the surface and still required for one call")


def test_ld571_both_LABELS_route_to_the_ONE_place_a_missing_scopes_COST_is_written():
    """A label that does not restate the cost must say where the cost IS — otherwise the fix
    for a false sentence is a missing one. The heading is a constant so the routing phrase and
    the section it routes to cannot drift apart."""
    region = _consumer_region()
    for marker in ("THIS TABLE ANSWERS THE per-SURFACE QUESTION",
                   "THIS TABLE ANSWERS THE per-OPERATION QUESTION"):
        label = _label_paragraph(region, marker)
        assert perm._LOSS_LIST_HEADING in label, (
            f"the {marker!r} label states no cost and points at none either")
    assert region.count(perm._LOSS_LIST_HEADING) == 3, (
        f"expected the loss list's heading plus one route from each of the two table labels, "
        f"found {region.count(perm._LOSS_LIST_HEADING)} occurrence(s) of "
        f"{perm._LOSS_LIST_HEADING!r}")


def test_ld571_every_OPTIONAL_ONLY_scope_is_ALSO_named_with_the_CALL_that_requires_it():
    """The both-directions arm AC5 asks for: a reader who meets a scope labelled *optional* must
    be able to find, in the same section, the call it is not optional for. This already held —
    it is pinned so a future edit to either table cannot break the agreement silently."""
    from larkdocio import capabilities

    region = _consumer_region()
    per_call = region.split("Per call, when")[-1]
    for surface_id, surface in capabilities(full=True)["surfaces"].items():
        creds = surface["credentials"]
        if creds["scopes"]:
            continue
        for scope in creds["optional_scopes"]:
            assert f"| `{surface_id}` · " in per_call and f"`{scope}`" in per_call, (
                f"{surface_id} lists {scope} as optional and no per-call row shows which call "
                "requires it — the reader is left with the conflation the registry warns about")


def test_the_consumer_section_warns_about_the_field_level_grant_by_name():
    """The five-day shape, stated where a consumer meets it: a grant whose absence looks
    like an empty answer rather than an error."""
    region = perm.region_of(
        guide(full=True), perm.CONSUMER_REGION_BEGIN.replace(" -->", ""), perm.CONSUMER_REGION_END)
    field_level = {scope.scope
                   for _p, _m, scopes, _n in perm.ENDPOINT_SCOPES
                   for scope in scopes if scope.field_level}
    assert field_level
    for scope in field_level:
        assert f"`{scope}`" in region
    assert "FIELD-level" in region


def test_the_consumer_section_carries_no_maintainer_evidence_pointer():
    """Role-appropriateness, mechanized. A capture path answers a maintainer's question, and
    a consumer cannot open it — so the consumer projection must not carry one, even though
    the registry it is generated from is full of them."""
    region = perm.region_of(
        guide(full=True), perm.CONSUMER_REGION_BEGIN.replace(" -->", ""), perm.CONSUMER_REGION_END)
    for leak in ("dev/", "captures/", "pytest", "tests/", "PERMISSIONS.md"):
        assert leak not in region, (
            f"the consumer permissions section leaks maintainer material: {leak!r}")


def test_the_consumer_and_maintainer_sections_are_NOT_the_same_document():
    """They answer different questions for different readers; if one were a copy of the
    other, one of the two roles is being served badly."""
    assert perm.consumer_permissions_markdown() != perm.dev_permissions_markdown()
    consumer_only = perm.consumer_permissions_markdown()
    assert "Endpoints reached" not in consumer_only, (
        "endpoint paths are maintainer material")


# --------------------------------------------------------------------------- #
# THE UNIFICATION — no scope string asserted in two places that could disagree.  #
# --------------------------------------------------------------------------- #

@private_tree.citations
def test_the_corpus_really_is_derived_and_covers_the_shipped_package():
    """The derivation itself, asserted — because the whole failure this replaces was a corpus
    that could not notice a file nobody listed.

    So: every tracked ``src/larkdocio/**`` source and every root Markdown document is in the
    corpus unless it is one of the named exclusions, and the file whose omission hid a live
    disagreement is specifically in it.
    """
    included = set(corpus())
    assert "src/larkdocio/blocks/diagram.py" in included, (
        "the file whose omission concealed a live scope disagreement must be in the corpus")
    for rel in ("src/larkdocio/permissions.py", "src/larkdocio/write/client.py",
                "src/larkdocio/sheets/export_reader.py", "BLOCKS.md", "SHEETS.md",
                "README.md", "PROJECT.md", ".env.example"):
        assert rel in included, f"{rel} is tracked and unexcluded, so it must be in the corpus"
    missing = [rel for rel in _repo_files()
               if rel.startswith("src/larkdocio/") and rel.endswith(".py")
               and rel not in included and not _excluded(rel)]
    assert not missing, f"these shipped sources fell out of the corpus: {missing}"


def test_the_corpus_WALK_honours_the_repositorys_own_ignore_rules():
    """The mechanism, pinned: build output, virtualenvs, caches and secrets stay OUT, and the
    one negated pattern stays IN.

    This is what makes the walk a faithful stand-in for the tracked set without asking a live
    checkout anything (see :func:`_repo_files`). Held here rather than assumed, because the
    mention ratchet below counts over this corpus: a walk that quietly swept ``.venv`` in would
    not fail loudly, it would fail *confusingly*.
    """
    for outside in (".venv/lib/python3.14/site-packages/x.py", "dist/larkdocio-1.0.0.tar.gz",
                    "build/lib/larkdocio/__init__.py", "src/larkdocio.egg-info/PKG-INFO",
                    "src/larkdocio/__pycache__/cli.cpython-314.pyc", ".pytest_cache/CACHEDIR.TAG",
                    "mutants/src/x.py", "htmlcov/index.html", ".kanban-wt/PROJECT.md",
                    ".worktrees/fix-x/README.md", ".git/config", ".env", ".env.local",
                    ".DS_Store", ".claude/session-role"):
        assert _ignored(outside), f"{outside} must not be able to reach the corpus"
    for inside in ("src/larkdocio/permissions.py", "README.md", ".env.example",
                   ".claude/roles/dev.md", "tests/fixtures/blocks.json"):
        assert not _ignored(inside), f"{inside} is a repository file and must be in the walk"
    # …and the walk really is the corpus's source, not an unused helper.
    walked = set(_repo_files())
    assert "src/larkdocio/permissions.py" in walked and ".env" not in walked
    assert not any(part in {".venv", "dist", "build", "__pycache__", ".git", ".kanban-wt"}
                   for rel in walked for part in rel.split("/"))


def test_every_exclusion_is_NAMED_with_its_reason():
    """The same standard the registry holds itself to for an empty requirement: an exclusion
    without a stated reason is indistinguishable from an oversight."""
    for prefix, reason in EXCLUDED_PREFIXES.items():
        assert reason and len(reason) > 40, f"{prefix} is excluded without a real reason"
    for rel, reason in EXCLUDED_FILES.items():
        assert reason and len(reason) > 20, f"{rel} is excluded without a real reason"
    assert set(EXCLUDED_PREFIXES) == {"dev/", "progress/", "requirements/", "tests/"}, (
        "the exclusion set changed — every class must be one of evidence, history, or a "
        "guard's own fixtures, and a new one needs its reason written down here")


@private_tree.walks_tree
def test_every_scope_string_ANYWHERE_IN_THE_REPO_is_one_the_registry_KNOWS():
    """The membership half, over the DERIVED corpus rather than an allowlist.

    A scope string the registry does not know is either a typo or a second, unguarded source
    of truth — and until this swept the whole repository it could hide in any file nobody had
    thought to list. That is not hypothetical: it hid an assertion of a scope for the very
    endpoint whose registry row deliberately records that no scope has ever been observed
    demanded for it.
    """
    known = _known_scopes()
    offenders = []
    for rel, text in sorted(corpus().items()):
        for lineno, line in enumerate(text.splitlines(), 1):
            for match in SCOPE_LITERAL.finditer(line):
                if match.group(0) not in known:
                    offenders.append(f"{rel}:{lineno}: {match.group(0)}")
    assert not offenders, (
        "these scope strings appear in the repository's own text but are unknown to "
        f"larkdocio.permissions: {offenders}")


@private_tree.walks_tree
def test_every_file_that_names_a_scope_ALSO_points_at_the_single_source():
    """The reference half, also over the derived corpus. A file may mention a scope string,
    but it must send the reader to the one place that owns it — otherwise the mention reads as
    authoritative and is free to drift."""
    offenders = []
    for rel, text in sorted(corpus_mentions().items()):
        full = corpus()[rel]
        if not any(pointer in full for pointer in SOURCE_POINTERS):
            offenders.append(rel)
    assert not offenders, (
        "these files name a scope string without pointing at the single source "
        f"({' / '.join(SOURCE_POINTERS)}): {offenders}")


def test_no_surface_asserts_a_scope_LIST_of_its_own_in_code():
    """The structural half, and the one that actually removed a source: the per-surface
    scope lists used to be hand-written arguments in ``capabilities.py``. They are projected
    now, so those literals are gone — and this keeps them gone."""
    # LD-244: ``capabilities`` is a package, so DERIVE the corpus from the tree instead of
    # naming one file — strictly stronger, since a submodule added tomorrow is scanned too.
    package = REPO_ROOT / "src" / "larkdocio" / "capabilities"
    members = sorted(package.rglob("*.py"))
    assert members, "the capabilities package has no modules to scan — the locator is stale"
    source = "\n".join(p.read_text(encoding="utf-8") for p in members)
    offenders = [line.strip() for line in source.splitlines()
                 if re.search(r"(?:optional_)?scopes\s*=\s*\[", line)]
    assert not offenders, (
        "a surface is asserting its own scope list again; it must be projected from the "
        f"permission registry instead: {offenders}")


#: The single source: the one file that is SUPPOSED to carry scope strings.
SINGLE_SOURCE = "src/larkdocio/permissions.py"

#: The count that measures the duplication AC4 exists to remove: scope-string mentions
#: **outside** the single source.
#:
#: Two numbers matter and only one of them is the metric. The *total* over the repository is
#: expected to GROW, because the registry itself now writes down the requirements it owns
#: (with an evidence pointer each) where previously nothing did. What must SHRINK is the count
#: everywhere else — every one of those is a reference that could drift. At the branch point
#: it was **44** with no single source at all; it is **29** now.
#:
#: The first version of this pinned 23 over a seven-file allowlist. That was not a smaller
#: number so much as an **incomplete** one: five more files asserted scopes and were never
#: measured, which falsifies a metric whose whole purpose is to show the surface shrinking.
#: This is measured over the derived corpus, so nothing can escape it again.
#:
#: **It went 29 -> 35 in this change, and the +6 is stated rather than absorbed.** All six are
#: in the new ``src/larkdocio/preflight.py``: five name the scope each read-only probe decides
#: (``PROBES``) or the scope it deliberately cannot decide (``NOT_PROBEABLE``), and one names
#: the field-level grant in the blind-spot text. None of them ASSERTS a requirement — the
#: registry still owns every requirement, and the membership guard above proves each of these
#: six is a scope the registry knows, so none can disagree with it. They are counted anyway,
#: because a metric that quietly exempts the new code is not a metric; the honest reading is
#: that a second module in the permission subsystem now keys on scope strings, and the
#: direction of travel from the branch point (44) still holds.
#: **It went 35 -> 38 in the cell-style write's change (LD-188), and the +3 is stated rather
#: than absorbed.** All three are REFERENCES to the export leg's extra scope, none of them an
#: authored requirement: (1) ``sheets/ops.py`` names it ONCE, in ``STYLE_LEG_SCOPE``, which the
#: gate-cost preview note, its disclosure text and the apply-log record all read from — the
#: alternative was the same string typed three times in one module; (2) ``GUIDE.md``'s style
#: recipe states the price of verifying a style, because a consumer who plans a style write and
#: then finds the proof needs a scope they have not granted was told nothing; (3) ``SHEETS.md``'s
#: ``style write`` row states the same in the matrix that owns capability truth. The membership
#: guard above proves each is a scope the registry knows, so none can disagree with it.
#: **It went 38 -> 43 in LD-302, and the +5 is stated rather than absorbed.** All five are in
#: ``.env.example`` — the file a consumer copies to ``.env`` and provisions their Lark app from,
#: which named 4 of the registry's 9 required scopes and so would have had a fresh consumer fail
#: every Base call. The five: ``bitable:app:readonly`` and ``directory:employee:search`` under
#: the READ pair, ``drive:export`` (optional) and the ``board:whiteboard:node:read`` CANDIDATE
#: — carried WITH its documented-unverified framing, because a setup document must not launder a
#: candidate into a requirement — and ``bitable:app`` under the WRITE pair. Every one is a
#: REFERENCE, never an authored requirement: the registry still owns every requirement, the
#: file's own preamble defers to it, the membership guard above proves each of the five is a
#: scope the registry knows, and the new ``tests/test_env_example_scope_completeness.py`` runs
#: the missing registry -> ``.env.example`` direction so a future registry scope cannot skip the
#: setup document. Counted anyway, because a metric that exempts the document it just corrected
#: is not a metric — and the direction of travel from the branch point (44) still holds: 43.
#: **LD-345 added the ``record_permalink`` operation and held this at 43.** Its call-site row in
#: PERMISSIONS.md's generated matrix names the read scope, but that region is a projection and is
#: stripped before counting; nothing outside the single source was added (the capabilities wiring
#: references base-read's read scope without naming the literal), so the human-maintained count
#: did not move.
MAX_MENTIONS_OUTSIDE_THE_SINGLE_SOURCE = 43

#: The branch-point figure, kept so the direction of travel is checkable rather than asserted.
MENTIONS_AT_BRANCH_POINT = 44


@private_tree.walks_tree
def test_the_duplication_COUNT_is_recorded_and_held():
    """The measurement AC4 exists for, as a ratchet over the WHOLE repository.

    Generated regions are stripped, so this counts what a **human maintains**; and the single
    source is counted separately, because a requirement written down in the one place that owns
    it is not duplication — it is the point.
    """
    counts = {rel: len(hits) for rel, hits in corpus_mentions().items()}
    outside = {rel: n for rel, n in counts.items() if rel != SINGLE_SOURCE}
    total_outside = sum(outside.values())
    assert total_outside <= MAX_MENTIONS_OUTSIDE_THE_SINGLE_SOURCE, (
        "scope-string mentions outside the single source have grown back; the registry is "
        f"the one place to author a requirement. Outside total {total_outside}. Per file: "
        f"{outside}")
    assert total_outside < MENTIONS_AT_BRANCH_POINT, (
        f"the whole point of the unification is that {total_outside} < "
        f"{MENTIONS_AT_BRANCH_POINT}")


@private_tree.citations
def test_the_ratchet_has_NO_SLACK_so_a_single_new_mention_reddens():
    """The review found the earlier ceiling carried slack, which lets duplication creep back a
    mention at a time without anything going red. The ceiling is now exactly the real count."""
    counts = {rel: len(hits) for rel, hits in corpus_mentions().items()}
    outside = sum(n for rel, n in counts.items() if rel != SINGLE_SOURCE)
    assert outside == MAX_MENTIONS_OUTSIDE_THE_SINGLE_SOURCE, (
        f"the ceiling must equal the real count with no slack: real {outside}, "
        f"ceiling {MAX_MENTIONS_OUTSIDE_THE_SINGLE_SOURCE}")


@private_tree.walks_tree
def test_the_registry_TABLE_is_the_densest_single_place_a_scope_is_written():
    """A sanity check on the shape of the win: the one file that OWNS the requirements should
    carry more mentions than any file that merely references them. If some other file
    overtakes it, the single source has stopped being single."""
    counts = {rel: len(hits) for rel, hits in corpus_mentions().items()}
    owner = "src/larkdocio/permissions.py"
    assert counts[owner] == max(counts.values()), (
        f"{owner} should be the densest place a scope string appears; counts={counts}")


#: The one seam LD-358 needed: a red proof MUTATES, and a mutation must never land in the
#: working tree, because every sibling test in this module (and in the sibling guard modules)
#: reads those same files — under the suite's default ``-n auto`` (LD-353), at the same instant,
#: on another worker. So the proof copies the file's REAL bytes to an isolated root, at its real
#: relative path, and runs the REAL check with ``root=`` pointed there. What is proven is
#: unchanged: real content, real corpus derivation, real regex, real pointer list.
def _corpus_copy(tmp_path, *rels):
    """An isolated corpus root holding a byte-identical copy of each named REAL repo file."""
    root = tmp_path / "corpus"
    for rel in rels:
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text((REPO_ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
    return root


def _membership_offenders(root, known):
    """The REAL membership check (as ``test_every_scope_string_…`` runs it), over ``root``."""
    return [
        f"{rel}:{match.group(0)}"
        for rel, text in corpus(root).items()
        for match in SCOPE_LITERAL.finditer(text)
        if match.group(0) not in known
    ]


def test_the_corpus_would_CATCH_an_invented_literal_in_A_SHIPPED_SOURCE_FILE(tmp_path):
    """THE regression proof for the bounce, run as the review ran it.

    The failing review's mutation: an invented scope literal added to
    ``src/larkdocio/blocks/diagram.py`` left every test green, because that file was not in the
    hand-listed corpus. The same mutation is applied to that file's REAL bytes and the REAL
    membership check is run over them — in an isolated corpus root (LD-358), so no sibling
    reader can observe the mutation. The unmutated copy is checked first, so the report is
    demonstrably caused by the mutation and not by the fixture.
    """
    rel = "src/larkdocio/blocks/diagram.py"
    root = _corpus_copy(tmp_path, rel)
    invented = "docx:document:inventedbythereviewer"
    assert SCOPE_LITERAL.fullmatch(invented)
    known = _known_scopes()
    assert corpus(root).keys() == {rel}, "the isolated corpus must contain the real file"
    assert not _membership_offenders(root, known), (
        "the control: the unmutated copy names no scope the registry does not know")
    target = root / rel
    target.write_text(target.read_text(encoding="utf-8") + f'\n# a mutation: {invented}\n', encoding="utf-8")
    offenders = _membership_offenders(root, known)
    assert any(invented in offender for offender in offenders), (
        "the widened corpus still fails to see an invented scope literal in a shipped "
        f"source file; offenders={offenders}")
    assert (REPO_ROOT / rel).read_text(encoding="utf-8") == (root / rel).read_text(encoding="utf-8").replace(
        f'\n# a mutation: {invented}\n', ""), "the working tree must be left exactly as found"


def test_the_four_segment_scope_form_is_matched_not_TRUNCATED():
    """The pattern bug the widening exposed: a four-segment scope was being clipped to three,
    so the guard compared a mangled string against the registry and could not have matched
    either way."""
    assert SCOPE_LITERAL.fullmatch("board:whiteboard:node:read")
    assert SCOPE_LITERAL.findall("needs board:whiteboard:node:read here") == [
        "board:whiteboard:node:read"]
    assert SCOPE_LITERAL.fullmatch("contact:user.base:readonly")
    assert SCOPE_LITERAL.fullmatch("docx:document")


def test_the_pointer_guard_bites_RED_on_a_REAL_file_stripped_of_its_pointer(tmp_path):
    """Direction two, proven by mutating a REAL corpus file and running the REAL check.

    The earlier version of this asserted set arithmetic over a made-up string, which proves
    only that Python works. Here the pointer is removed from a file that genuinely has one and
    the live check is run over it.

    **LD-358:** the stripping happens to ``SHEETS.md``'s real bytes in an ISOLATED corpus root,
    not in the working tree. It used to write the stripped text into the tracked file and
    restore it in a ``finally``; under ``-n auto`` the readers of the same file — chiefly
    ``test_every_file_that_names_a_scope_ALSO_points_at_the_single_source`` — ran on other
    workers inside that window and reported ``SHEETS.md`` as a real offender. Nothing about the
    proof weakens: the same real file's bytes, the same real corpus derivation, the same real
    pointer check — and the unstripped copy is checked first, so the report is demonstrably
    caused by the stripping and not by the fixture.
    """
    rel = "SHEETS.md"
    root = _corpus_copy(tmp_path, rel)
    target = root / rel
    original = target.read_text(encoding="utf-8")
    assert original == (REPO_ROOT / rel).read_text(encoding="utf-8"), "the copy must be the real file's bytes"
    assert any(pointer in original for pointer in SOURCE_POINTERS)

    def _pointerless(where):
        return [rel_ for rel_ in corpus_mentions(where)
                if not any(p in corpus(where)[rel_] for p in SOURCE_POINTERS)]

    assert _pointerless(root) == [], (
        "the control: the real file as it stands does point at the single source")
    stripped = original
    for pointer in SOURCE_POINTERS:
        stripped = stripped.replace(pointer, "the-pointer-was-removed")
    assert stripped != original, "the strip must actually change the file"
    target.write_text(stripped, encoding="utf-8")
    offenders = _pointerless(root)
    assert rel in offenders, (
        f"stripping the single-source pointer must be reported; offenders={offenders}")
    assert any(p in (REPO_ROOT / rel).read_text(encoding="utf-8") for p in SOURCE_POINTERS), (
        "the working tree's own SHEETS.md must never have been touched")


def test_a_hand_EDIT_inside_a_generated_region_REDDENS_the_real_byte_check(tmp_path):
    """The byte-exact guard, proven to bite by editing the REAL document and running the REAL
    comparison the live test performs — not by comparing two local strings.

    **LD-358:** the edit lands on a copy of ``PERMISSIONS.md``'s real bytes under ``tmp_path``,
    never in the working tree, where the module's own readers of the same document would see it
    from another xdist worker. The bytes edited, the region extraction and the render compared
    against are all the real ones.
    """
    rel = "PERMISSIONS.md"
    target = _corpus_copy(tmp_path, rel) / rel
    original = target.read_text(encoding="utf-8")
    assert original == DEV_MATRIX.read_text(encoding="utf-8"), "the copy must be the real document's bytes"
    region = perm.region_of(
        original, perm.DEV_REGION_BEGIN.replace(" -->", ""), perm.DEV_REGION_END)
    assert region and region == perm.dev_permissions_markdown(), "must start from truth"
    target.write_text(original.replace("docx:document:readonly",
                                       "docx:document:readonlyX", 1), encoding="utf-8")
    tampered = perm.region_of(
        target.read_text(encoding="utf-8"), perm.DEV_REGION_BEGIN.replace(" -->", ""),
        perm.DEV_REGION_END)
    assert tampered != perm.dev_permissions_markdown(), (
        "a hand edit inside the generated region slipped past the byte comparison")
    assert DEV_MATRIX.read_text(encoding="utf-8") == original, "the working tree must be left exactly as found"


def test_NO_test_in_this_module_WRITES_into_the_working_tree():
    """LD-358: the red-proof tests above must mutate a COPY, never a tracked repo file.

    The bug this pins: three of them used to ``write_text`` into ``SHEETS.md``,
    ``PERMISSIONS.md`` and ``blocks/diagram.py`` and restore them in a ``finally``. Every other
    test in this module (and several in sibling guard modules) READS those same files, and
    under the suite's default ``-n auto`` (LD-353) a reader runs on another worker *while* the
    mutation is on disk — so a guard reported a real repo file as an offender and a scoped run
    was reliably red (3/3 on ``verify.sh --scope``'s guard floor).

    The invariant, stated structurally rather than by re-running the race: **a path derived
    from ``REPO_ROOT`` is read-only in this module.** A red proof still mutates and still runs
    the real check — on an equivalent corpus under ``tmp_path``, where no sibling can see it.
    """
    tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    repo_paths = set()
    for node in ast.walk(tree):
        # ``target = REPO_ROOT / "SHEETS.md"`` (and any deeper ``/`` chain) binds a name to a
        # path inside the working tree.
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.BinOp):
            inner = node.value
            while isinstance(inner, ast.BinOp):
                inner = inner.left
            if isinstance(inner, ast.Name) and inner.id == "REPO_ROOT":
                repo_paths.update(t.id for t in node.targets if isinstance(t, ast.Name))
    offenders = [
        f"{node.func.value.id}.{node.func.attr}() at line {node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"write_text", "write_bytes", "unlink", "rename"}
        and isinstance(node.func.value, ast.Name) and node.func.value.id in repo_paths
    ]
    assert not offenders, (
        "a test in this module mutates a file in the working tree, which its own sibling "
        "readers observe on another xdist worker (LD-358). Mutate a copy under tmp_path and "
        f"run the real check against that root instead: {offenders}")


@pytest.mark.parametrize("render", [
    perm.dev_permissions_markdown, perm.consumer_permissions_markdown])
def test_both_renders_are_deterministic(render):
    """A document generated from a dict iteration order that wobbles would show a spurious
    diff on every regeneration, and the byte-exact guard would become noise."""
    assert render() == render()


@private_tree.walks_tree
def test_the_preflight_keys_on_scopes_but_ASSERTS_no_requirement():
    """The +6 in the ratchet above, pinned to the one file and the one purpose.

    A probe table has to name the scope each probe decides — that is not a second assertion of
    a requirement, and the membership guard proves every one of these strings is registry-known
    so none can disagree. Pinning the count here means a future change cannot hide new
    duplication inside the allowance this module was given.
    """
    counts = {rel: len(hits) for rel, hits in corpus_mentions().items()}
    assert counts.get("src/larkdocio/preflight.py") == 6, (
        "the preflight's scope-string count changed; if a probe was added or removed say so "
        f"and re-true the ratchet. counts={counts}")
    source = (REPO_ROOT / "src" / "larkdocio" / "preflight.py").read_text(encoding="utf-8")
    # It must not grow a requirement table of its own: the scopes it needs come from the
    # registry, via scopes_for_operations.
    assert "scopes_for_operations" in source
    assert "ENDPOINT_SCOPES" not in source, (
        "the preflight must ask the registry for requirements, never restate them")
