"""The always-on offline half of ``test_live_base_canary`` (LD-252).

THE L1 GATE runs only with credentials and a network. Everything it *claims about itself* —
that it is read-only, that it targets the disposable Scratch Base and nothing else, that it
pins **same-run** determinism rather than a committed cross-time baseline, that it depends on
no hand-authored specimen, and that it skips **loudly** rather than passing silently — is
exactly the class of claim a credential-less run "verifies" by not running. So it is verified
**here**, statically, on every plain ``pytest``.

This companion also carries the three obligations that are *about* the gate rather than
inside it, because they are checkable offline and nowhere else:

* **AC6** — the gate's :mod:`gate_registry` row exists, is ``HAS_COMPANION``, and points at
  this file (the registry's own guard holds the pairing exhaustive; this asserts the
  classification the row was given);
* **AC7** — D3's liveness definition really is in the gate's docstring, in plain words, and
  **agrees with `BASE.md` register rows 8, 9 and 10** rather than paraphrasing them loosely;
* **AC8/AC10** — ``capabilities()``'s gate coverage for any Base surface names gate modules
  that exist and are registered (written **order-independently**, so it holds both before and
  after LD-251 registers the surface), and the register still carries its rows.

It imports nothing from the live gate and runs no gate.
"""
import ast
import re
from pathlib import Path

import canary_support
import pytest

import larkdocio
from larkdocio.base import cells as base_cells
from larkdocio.base import ops as base_ops

import gate_registry as gr

from guard_kit import REPO_ROOT

_TESTS = REPO_ROOT / "tests"
_REPO_ROOT = REPO_ROOT
_GATE = _TESTS / "test_live_base_canary.py"


@pytest.fixture(scope="module")
def gate_source():
    return _GATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def gate_docstring():
    return ast.get_docstring(ast.parse(_GATE.read_text(encoding="utf-8"))) or ""


@pytest.fixture(scope="module")
def gate_body(gate_source, gate_docstring):
    """The gate minus its module docstring — what the gate *does*, not what it explains.

    The distinction matters for exactly one check: the docstring is *required* (AC1) to name
    the hand-authored specimens it must not depend on, so a naive grep over the whole file
    would forbid the very sentence that records the rule.
    """
    return gate_source.replace(gate_docstring, "", 1)


# ---------------------------------------------------------------------------
# AC5 — deselected by default, and it skips LOUDLY
# ---------------------------------------------------------------------------


def test_the_gate_exists_and_is_marked_live(gate_source):
    assert "pytestmark = pytest.mark.live" in gate_source, (
        "the gate must be deselected by default; an unmarked live test runs in every plain "
        "pytest and turns a credential-less clone red")


def test_the_gate_SKIPS_LOUDLY_rather_than_passing(gate_source):
    assert "base_missing_reason" in gate_source and "pytest.skip" in gate_source, (
        "AC5: the gate must route its unavailability through canary_support."
        "base_missing_reason and skip — never a silent pass")


def test_the_skip_reason_NAMES_the_variable_that_is_missing(monkeypatch):
    monkeypatch.delenv(canary_support.SCRATCH_BASE_ENV, raising=False)
    reason = canary_support.base_missing_reason()
    assert reason and canary_support.SCRATCH_BASE_ENV in reason


# ---------------------------------------------------------------------------
# AC4 — READ-ONLY, and provably so
# ---------------------------------------------------------------------------


def test_the_registry_the_gate_leans_on_really_is_read_only():
    """The gate's first assertion, made here too — so the claim is checked on every run and
    not only on the runs that have credentials."""
    assert base_ops.read_only()
    assert all(descriptor.mutates is False for descriptor in base_ops.OPS)


def test_the_gate_asserts_read_only_BEFORE_it_reads_anything(gate_source):
    tree = ast.parse(gate_source)
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    first = "test_the_registry_declares_the_whole_gate_read_only_BEFORE_it_reads_anything"
    assert first in names, f"{first} is missing from the gate"
    others = [n for n in names if n.startswith("test_") and n != first]
    assert others, "the gate has no other test — the ordering claim would be vacuous"
    assert names.index(first) < min(names.index(n) for n in others), (
        "the read-only assertion must come first in file order, because that is the order "
        "pytest runs them in and the point is to fail before touching the Base")


def test_the_gate_names_NO_write_credential_and_NO_write_verb(gate_source):
    for forbidden in ("LARK_WRITE_APP", "from_write_credentials", "get_write_credentials",
                      ".create(", ".update(", ".patch(", ".delete("):
        assert forbidden not in gate_source, forbidden


def test_the_gate_PROVES_it_wrote_nothing_by_re_reading_the_revision(gate_source):
    """AC4's live half: ``table.revision`` before and after. The packs proved this is the one
    reliable write detector on a Base, so its absence would gut the claim."""
    assert "revisions_before" in gate_source and "revisions_after" in gate_source
    assert "revisions_after == revisions_before" in gate_source


# ---------------------------------------------------------------------------
# AC1 — the right target, and no dependence on a specimen it did not seed
# ---------------------------------------------------------------------------


def test_the_gate_targets_the_SCRATCH_BASE_and_nothing_else(gate_source):
    assert "scratch_base_url" in gate_source
    for other_target in ("LARKDOCIO_CANARY_DOC", "LARKDOCIO_SCRATCH_SHEET",
                         "LARKDOCIO_BLOCKZOO_DOC", "canary_doc_url", "scratch_sheet_url",
                         "blockzoo_doc_url"):
        assert other_target not in gate_source, (
            f"the Base canary must not reach for {other_target}")
    assert "parse_base_url" in gate_source, (
        "the app token comes from the env var, parsed by the shipped URL validator")
    # A Base token belongs in .env, never in a test file — whole OR truncated to a display
    # prefix. LD-695: this used to name two literal 5-character prefixes; once the real tokens
    # were faked one of them read `Exampl`, which forbade the word "Example", not a token. Now:
    # no string literal is token-shaped, and none carries the scratch Base token .env.example
    # documents, or a 6+ character prefix of it.
    env = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    (scratch,) = re.findall(r"^LARKDOCIO_SCRATCH_BASE=\S*/base/([A-Za-z0-9]+)", env, re.M)
    literals = [node.value for node in ast.walk(ast.parse(gate_source))
                if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    for text in literals:
        assert not re.search(r"(?<![A-Za-z0-9])[A-Za-z0-9]{27}(?![A-Za-z0-9])", text), (
            f"a Base token belongs in .env, never in a test file: {text[:12]}…")
        assert scratch[:6] not in text, "a (truncated) scratch Base token in the gate"


def test_the_gate_depends_on_NO_specimen_it_did_not_ITSELF_seed(gate_body):
    """AC1's binding caveat: **a human owns this Base.** The maintainer hand-authors the Lookup /
    Email / Stage / comment specimens on it, and the parity pack left ``ok@example.invalid``
    in an Email cell. So the gate may characterize what it finds, but it may not assert a
    specimen's *value*, its row count, or a table's name."""
    for specimen in ("ok@example.invalid", "not-an-email"):
        assert specimen not in gate_body, (
            f"the gate asserts on {specimen!r} — a value the maintainer can change by hand. "
            "Characterize it; never depend on it.")
    # Nor may it compare the Base's own name, a table's name or a cell to a literal.
    comparisons = re.findall(r"\.name\s*==\s*[\"']|==\s*[\"']Scratch", gate_body)
    assert comparisons == [], f"the gate compares a hand-owned value to a literal: {comparisons}"
    # No hand-typed row/table/field census either: a count is a specimen too.
    censuses = re.findall(
        r"len\((?:tables|document\d?\.tables|table\.rows|table\.fields)\)\s*==\s*\d+",
        gate_body)
    assert censuses == [], f"the gate pins a hand-typed census: {censuses}"


def test_the_gate_CHARACTERIZES_what_it_found(gate_source):
    """AC1's substance: because ``BaseScratchExample…`` was pristine at grant time, the gate's own reading
    IS the characterization — tables, fields and row counts recorded as the baseline."""
    assert "[base-canary]" in gate_source, "the characterization line is the record"
    for recorded in ("tables=", "fields=", "rows=", "sha256="):
        assert recorded in gate_source, f"the characterization omits {recorded}"


# ---------------------------------------------------------------------------
# AC2 — SAME-RUN byte-identity, and no committed cross-time baseline
# ---------------------------------------------------------------------------


def test_the_gate_reads_TWICE_and_compares_the_two_reads_BYTE_FOR_BYTE(gate_source):
    assert "md1 == md2" in gate_source, (
        "AC2: the two back-to-back reads must be compared byte-for-byte")
    assert gate_source.count("_read_base_once(") >= 3, (
        "two independent read cycles plus the helper's own definition")


def test_the_gate_pins_SAME_RUN_identity_and_commits_NO_cross_time_baseline(gate_source):
    """A human edits this Base, so a committed expected-output file would redden on the maintainer's
    next edit rather than on a drift. PROJECT.md § Quality bar → Determinism."""
    assert "same-run" in gate_source.lower()
    for forbidden in ("write_text", "read_text(", "fixtures/", ".golden"):
        assert forbidden not in gate_source, (
            f"{forbidden!r} in the gate — a cross-time baseline is exactly what AC2 forbids")


# ---------------------------------------------------------------------------
# AC3 — sane output, the live PII invariant, and markers exactly where the registry says
# ---------------------------------------------------------------------------


def test_the_gate_asserts_SANE_OUTPUT_not_merely_no_exception(gate_source):
    for claim in ("document.tables", "field_name", "GFM"):
        assert claim in gate_source, f"the sanity assertions omit {claim}"


def test_the_gate_carries_the_LIVE_PII_invariant(gate_source):
    """D1, live: zero person-sourced email strings, zero avatar/CDN URLs, zero person ids."""
    assert "_PERSON_PAIRS" in gate_source, (
        "the person-bearing columns must be DERIVED from the registry, not hand-listed")
    for detector in ("avatar", "ou_", "oc_", "@"):
        assert detector in gate_source, f"the live PII sweep has no {detector!r} detector"


def test_the_person_bearing_pairs_are_DERIVABLE_from_the_registry():
    """The gate derives its person-bearing column set by renderer identity. Proven here so a
    new person-bearing pair joins the live sweep automatically."""
    persons = base_cells.renderer_for(11, "User")
    assert persons is not None
    derived = tuple(p for p in base_cells.PAIRS if base_cells.renderer_for(*p) is persons)
    assert (11, "User") in derived and (23, "GroupChat") in derived
    assert (1003, "CreatedUser") in derived and (1004, "ModifiedUser") in derived
    assert (1, "Text") not in derived, "a text column is not person-sourced"


def test_the_gate_asserts_the_STAGE_MARKER_IS_PRESENT_and_confined(gate_source):
    """AC3's amendment: the Base carries a real type-24 field, so its absent-with-reason
    marker is **correct output**. The assertion is *markers exactly where the registry says
    they should be, and nowhere else.*"""
    assert "STAGE_OPAQUE_MARKER" in gate_source
    assert "OPAQUE_PAIRS" in gate_source, (
        "which columns may carry the marker is the registry's fact, not a literal")


def test_the_registrys_opaque_set_is_the_ONE_pair_the_gate_licenses():
    assert base_cells.OPAQUE_PAIRS == ((24, "Stage"),)
    assert base_cells.STAGE_OPAQUE_MARKER.startswith("[unreadable Base cell: Stage (type 24)")


def test_the_gate_refuses_a_TYPED_UNKNOWN_where_a_known_type_was_expected(gate_source):
    assert "PAIRS" in gate_source and "WILL_NOT_SUPPORT" in gate_source, (
        "AC3: every field must resolve to a registered pair, and the one exemption is the "
        "maintainer's will-not-support ruling — recorded, not silently tolerated")


# ---------------------------------------------------------------------------
# AC6 — the classified gate_registry row
# ---------------------------------------------------------------------------


def test_the_gate_has_a_CLASSIFIED_registry_row_pointing_at_THIS_file():
    row = gr.REGISTRY.get(_GATE.name)
    assert row is not None, f"{_GATE.name} has no gate_registry row (AC6)"
    assert row.kind is gr.Kind.HAS_COMPANION, (
        f"the Base canary ships WITH its mirror, so its row is HAS_COMPANION, not "
        f"{row.kind.name}")
    assert row.companion == Path(__file__).name
    assert row.reason.strip(), "every row carries a written reason — that is the point"
    back = gr.REGISTRY[row.companion]
    assert back.kind is gr.Kind.COMPANION and back.subject == _GATE.name


def test_the_new_gate_adds_NO_new_GAP():
    """The 2026-08-03 ruling's direction, applied to the tranche's own gate: a new live gate
    no longer means a new unmirrored gap."""
    assert _GATE.name not in [row.filename for row in gr.gap_list()]
    assert len(gr.gap_list()) == 10


# ---------------------------------------------------------------------------
# AC7 — D3's liveness definition is in the gate's docstring, and agrees with the register
# ---------------------------------------------------------------------------

#: The plain-words obligations AC7 puts in the docstring. Each is a *substring* rather than a
#: paraphrase, so the doctrine cannot be softened into vagueness and still pass.
_D3_DOCSTRING_OBLIGATIONS = (
    "1002",
    "91402",
    "1254041",
    "/drive/v1/metas/batch_query",
    "inert residue",
    "larkdocio-DISPOSABLE-",
    "trash accretes",
    "no purge verb",
    "copied apps",
    "deleted tables",
    "1254036",
    "async",
    "register rows 8, 9 and 10",
)


@pytest.mark.parametrize("obligation", _D3_DOCSTRING_OBLIGATIONS)
def test_D3s_liveness_definition_is_stated_in_the_gates_docstring(gate_docstring, obligation):
    """AC7: this is the FIRST Base gate, so it is where the doctrine is written down for
    the Base write spec to inherit rather than re-derive."""
    assert obligation in gate_docstring, (
        f"the gate's docstring does not state {obligation!r} — D3's definition must be "
        "readable without running anything")


def test_the_docstring_defines_liveness_against_BITABLE_and_NOT_against_drive_metadata(
        gate_docstring):
    lowered = gate_docstring.lower()
    assert "bitable" in lowered
    assert "never" in lowered and "drive" in lowered, (
        "the definition's teeth are the NEGATIVE half: never against Drive metadata")


def test_the_docstrings_trash_and_media_residue_is_stated_in_PLAIN_WORDS(gate_docstring):
    """AC7 asks for a content test on exactly this: not the codes, the consequence."""
    assert "accretes" in gate_docstring
    assert "media" in gate_docstring


#: Register rows 8, 9 and 10 — the three the docstring must agree with. Keyed by the row
#: number AC7 names, valued by a token that identifies the row in ``BASE.md``.
_REGISTER_ROWS_8_9_10 = {
    8: "Base copy is ASYNC-ONLY",
    9: "DELETE is TRASH, not purge",
    10: "Uploaded media tokens are UN-PURGEABLE",
}


def test_the_docstring_and_BASE_MDs_register_AGREE_on_rows_8_9_and_10():
    """AC7: *"the docstring and the register must agree"*. So the row numbers are resolved out
    of ``BASE.md`` itself rather than trusted — if the register is renumbered, this reddens
    instead of the docstring quietly pointing at the wrong rows."""
    register = (_REPO_ROOT / "BASE.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\|\s*(\d+)\s*\|\s*(.*?)\s*\|", register, re.MULTILINE)
    numbered = {int(n): body for n, body in rows}
    for number, token in _REGISTER_ROWS_8_9_10.items():
        assert number in numbered, f"BASE.md has no register row {number}"
        assert token in numbered[number], (
            f"BASE.md register row {number} no longer reads as {token!r} — it is now "
            f"{numbered[number][:80]!r}. The gate's docstring names rows 8/9/10 by number; "
            "renumbering the register means correcting the docstring in the same change.")


def test_the_gates_docstring_carries_the_error_codes_the_REGISTER_carries():
    """The codes are the observable, so they must not diverge between the two documents."""
    register = (_REPO_ROOT / "BASE.md").read_text(encoding="utf-8")
    docstring = ast.get_docstring(ast.parse(_GATE.read_text(encoding="utf-8"))) or ""
    for code in ("1254036", "1002"):
        assert code in register and code in docstring, code


# ---------------------------------------------------------------------------
# AC8 / AC10 — the front door's gate coverage, and the register's survival
# ---------------------------------------------------------------------------


def test_any_BASE_surface_gate_coverage_names_gate_MODULES_THAT_EXIST():
    """AC8, written **order-independently on purpose.**

    ``capabilities()`` carried no Base surface when this was written — registering it was
    LD-251's AC1, running in parallel — so the assertion was the invariant that must hold
    **either way**: any Base surface's gate coverage names live modules that really exist in
    the tree and are classified in the registry. **LD-260 made it load-bearing**, declaring
    coverage on ``base-read`` and on the new ``base-write``.
    """
    surfaces = larkdocio.capabilities(full=True)["surfaces"]
    base_surfaces = {sid: s for sid, s in surfaces.items() if sid.startswith("base")}
    for sid, surface in base_surfaces.items():
        coverage = surface.get("gate_coverage")
        if not coverage:
            continue
        for member in coverage["members"]:
            module = member["module"]
            # `module` is a repo-relative path ("tests/test_x.py"). This read the value as a
            # bare stem while no Base surface reported coverage, so the arithmetic was never
            # exercised; LD-260 made it live, and the fix is to take the file NAME.
            filename = Path(module).name
            assert (_TESTS / filename).is_file(), (
                f"{sid}'s gate coverage names {module}, which is not in tests/")
            assert filename in gr.REGISTRY, (
                f"{sid}'s gate coverage names {module}, which has no gate_registry row")


def test_this_gate_is_the_module_a_BASE_read_surfaces_coverage_would_name():
    """The other direction of AC8, also order-independent: if a Base **read** surface reports
    gate coverage at all, THE L1 GATE is what it must name — a Base surface claiming live
    coverage that does not include this canary would be claiming coverage it does not have."""
    surfaces = larkdocio.capabilities(full=True)["surfaces"]
    for sid, surface in surfaces.items():
        if not (sid.startswith("base") and surface.get("mode") == "read"):
            continue
        coverage = surface.get("gate_coverage")
        if not coverage:
            continue
        modules = {Path(member["module"]).name for member in coverage["members"]}
        assert _GATE.name in modules, (
            f"{sid} reports live gate coverage without THE L1 GATE ({_GATE.stem}) in it")


def test_the_register_SURVIVES_the_gate():
    """AC10: the canary is the first time the whole surface meets a real Base. The register's
    row count is pinned by ``tests/test_base_md_matrix.py``; what is asserted here is that
    this story did not quietly shrink it, and that any row it *added* is above the pinned
    floor of twelve rather than instead of one."""
    register = (_REPO_ROOT / "BASE.md").read_text(encoding="utf-8")
    numbers = [int(n) for n in re.findall(r"^\|\s*(\d+)\s*\|", register, re.MULTILINE)]
    assert numbers[:12] == list(range(1, 13)), (
        f"BASE.md § Limitations & revisit-triggers lost or renumbered a row: {numbers}")
    assert numbers == sorted(numbers) and len(numbers) == len(set(numbers)), (
        f"the register's numbering is not a clean ascending sequence: {numbers}")


# ---------------------------------------------------------------------------
# Discipline — the companion never runs the gate
# ---------------------------------------------------------------------------


def test_this_companion_never_imports_or_runs_the_gate():
    source = Path(__file__).read_text(encoding="utf-8")
    dynamic = ("import" + "lib", "ex" + "ec(", "__im" + "port__", "pytest." + "main")
    for forbidden in dynamic:
        assert forbidden not in source, forbidden
    assert ("import " + _GATE.stem) not in source, (
        "the companion classifies the gate by reading it, never by importing it")


def test_the_gate_keeps_a_live_call_BUDGET(gate_source):
    """Being gentle is an acceptance criterion, not a courtesy (the tranche riders), so the
    gate bounds its own call count."""
    assert "api_calls" in gate_source
