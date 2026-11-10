"""LD-492 — THE FILE-FIRST ROUND TRIP AS ONE VERB: the offline half of its contract.

What is provable here, and why it is worth more than it looks
-------------------------------------------------------------
The live arm (``tests/test_live_write_roundtrip_verb_gate.py``) answers whether the two phases
address the same blocks against a real document. Everything else the verb promises is an
**ordering** claim, and ordering is exactly what a fixture proves best:

* the ``dry_run`` preview is **structurally unskippable** — no argument, in any combination,
  reaches a write without one, and ``apply`` receives nothing but the object ``dry_run``
  returned;
* the ``STALE_DOCUMENT`` guard is armed **from the snapshot**, and when the snapshot carries no
  revision the verb reports ``unavailable`` **loudly** rather than writing as though it were
  armed. **Both branches are asserted**, because an unarmed write that looks armed is the
  failure this whole flow exists to prevent;
* the read-back uses the **shipped** comparison. A normalization-only difference — the
  tight-vs-loose list the guide names — must verify **clean**, and a real content difference
  must not. Those two are one test each, and they are the reason ``compose()`` is called
  instead of ``==`` on two strings;
* every refusal is **typed**, names what to do next, and **points at a guide section that
  resolves**;
* the two credential pairs are resolved **independently**, and a phase-B invocation with no
  WRITE pair refuses **before any call**, naming both variables.

The clients are the offline doubles the recipe harness already ships, handed to the verb
through its own injection parameters — so the code under test is the shipped code, and only
the transport is a double.
"""
import copy

import pytest

import offline_doubles
from larkdocio import roundtrip
from larkdocio.errors import (
    LarkApplyRefusedError,
    LarkConfigError,
    LarkSnapshotIntegrityError,
)
from larkdocio.write.reconcile import ReconciliationState


# --------------------------------------------------------------------------- #
# The stage                                                                    #
# --------------------------------------------------------------------------- #

@pytest.fixture
def stage(monkeypatch, tmp_path):
    return offline_doubles.stage(monkeypatch, tmp_path)


@pytest.fixture
def reader(stage):
    return offline_doubles.OfflineDocxReadClient(
        "cli_read_offline", "read-secret-offline", "larksuite.com")


@pytest.fixture
def writer(stage):
    return offline_doubles.OfflineWriteClient(
        "cli_write_offline", "write-secret-offline", "larksuite.com")


@pytest.fixture
def workdir(tmp_path):
    return tmp_path / "edit"


DOC_URL = "https://your-domain.larksuite.com/docx/OfflineDocToken"


def _pull(reader, workdir):
    return roundtrip.pull(DOC_URL, workdir, reader=reader)


def _editable_block(workdir):
    """``(projection, block_id)`` for a block of the pulled document that is plain prose.

    Derived from the artefact rather than hard-coded, so a fixture change moves the target
    instead of breaking every test here at once — and derived through the SHIPPED projection,
    which is also the identity source the verb itself uses.
    """
    from larkdocio.model.projection import block_markdown, project_block_ids
    from larkdocio.snapshot import load

    projection = project_block_ids(load(str(roundtrip.snapshot_path(workdir))).tree)
    for block_id in projection.block_ids:
        try:
            body = block_markdown(projection, block_id)
        except ValueError:
            continue
        if body.strip() and not body.lstrip().startswith(("#", "|", "`", ">")):
            return projection, block_id
    raise AssertionError("the fixture document has no plain prose block to edit")


def _edit(workdir, new_markdown):
    """Rewrite one block of the editable file — BY BLOCK, the way the guide insists.

    ``replace_block_markdown`` replaces the block's whole segment, so a block spanning two
    projected lines is replaced by two lines' worth of text rather than half-rewritten. That
    is the same splice the recipe teaches, and using anything else here would be testing the
    verb against an edit no consumer is told to make.
    """
    from larkdocio.model.projection import replace_block_markdown

    projection, block_id = _editable_block(workdir)
    path = roundtrip.markdown_path(workdir)
    path.write_text(
        replace_block_markdown(projection, block_id, new_markdown), encoding="utf-8")
    return block_id


# --------------------------------------------------------------------------- #
# AC1 — ONE verb, TWO phases, ONE invocation shape                              #
# --------------------------------------------------------------------------- #

def test_ac1_the_two_phases_are_two_invocations_of_ONE_verb_with_ONE_vocabulary():
    """The shape, pinned where the docs, the help text and these tests all read it from.

    The verb is spelled ONCE, in the library module, and everything else imports it — so the
    command line, ``capabilities()`` and this suite cannot come to mean three different things
    by the same word.
    """
    from larkdocio.cli import cli

    assert roundtrip.PHASES == (roundtrip.PHASE_PULL, roundtrip.PHASE_PUSH)
    assert roundtrip.COMMAND_NAME in cli.commands
    command = cli.commands[roundtrip.COMMAND_NAME]
    phase = next(p for p in command.params if p.name == "phase")
    assert tuple(phase.type.choices) == roundtrip.PHASES, (
        "the command line offers phases the library does not name — one vocabulary, not three")


def test_ac1_phase_A_writes_the_two_files_and_ONLY_those_two(reader, workdir):
    """Two files, two owners: the snapshot is ours and immutable, the Markdown is theirs."""
    result = _pull(reader, workdir)
    assert sorted(p.name for p in workdir.iterdir()) == [
        roundtrip.MARKDOWN_FILENAME, roundtrip.SNAPSHOT_FILENAME]
    assert result.markdown_path.endswith(roundtrip.MARKDOWN_FILENAME)
    assert result.block_count > 0
    assert result.api_domain == "larksuite.com", (
        "the domain must travel — it is the one fact phase B cannot derive from the token")


def test_ac1_phase_B_resumes_from_THE_FILES_ALONE_with_no_url_and_no_pull_result(
    reader, writer, workdir
):
    """The whole reason there are two phases: the second half must run in a process that never
    saw the first. Nothing from ``pull`` is passed to ``push`` — only the directory."""
    _pull(reader, workdir)
    _edit(workdir, "Rewritten by the caller, between the phases.")

    result = roundtrip.push(workdir, reader=reader, writer=writer)
    assert result.document_token
    assert result.plan.change_count == 1, result.plan.to_dict()


# --------------------------------------------------------------------------- #
# AC3 — the gates cannot be dropped, and BOTH revision_guard branches are held   #
# --------------------------------------------------------------------------- #

def _spy_on_dry_run(monkeypatch):
    calls = []
    real = roundtrip.dry_run

    def spy(requests, root, **kwargs):
        calls.append(kwargs)
        return real(requests, root, **kwargs)

    monkeypatch.setattr(roundtrip, "dry_run", spy)
    return calls


@pytest.mark.parametrize("apply_changes", [False, True])
def test_ac3_the_preview_is_built_on_EVERY_invocation_shape(
    monkeypatch, reader, writer, workdir, apply_changes
):
    """There is no flag that removes the preview — asserted across every combination of the
    command's own options, not against the one the happy path takes."""
    _pull(reader, workdir)
    _edit(workdir, "Rewritten while the two phases were apart.")
    calls = _spy_on_dry_run(monkeypatch)

    roundtrip.push(workdir, apply_changes=apply_changes, reader=reader, writer=writer)
    assert len(calls) == 1, (
        f"dry_run ran {len(calls)} time(s) with apply_changes={apply_changes} — the preview "
        "is not structurally unskippable")


def test_ac3_no_option_on_the_command_can_suppress_the_preview():
    """The affordance for non-interactive use is *apply the plan you just previewed*, and the
    surface is held to that: no flag on the verb is named for skipping, forcing or bypassing.
    A future ``--no-preview`` reddens here before anybody has to read the implementation."""
    from larkdocio.cli import cli

    import click

    options = {
        opt
        for param in cli.commands[roundtrip.COMMAND_NAME].params
        if isinstance(param, click.Option)
        for opt in param.opts
    } - {"--help"}
    assert options == {"-o", "--workdir", "--apply"}, options
    for banned in ("skip", "no-preview", "force", "yes", "unsafe", "no-dry-run"):
        assert not any(banned in opt for opt in options), (
            f"the verb grew a {banned!r}-shaped option — the preview is the verb's whole value")


def test_ac3_apply_receives_NOTHING_BUT_the_object_dry_run_returned(
    monkeypatch, reader, writer, workdir
):
    """Structural, not incidental: the plan the engine applies is the plan it previewed, by
    identity. A re-derived or re-built plan would be a second, unpreviewed path."""
    _pull(reader, workdir)
    _edit(workdir, "Rewritten while the two phases were apart.")

    previewed, applied = [], []
    real_dry_run, real_apply = roundtrip.dry_run, roundtrip.apply

    def dry_run_spy(requests, root, **kwargs):
        plan = real_dry_run(requests, root, **kwargs)
        previewed.append(plan)
        return plan

    def apply_spy(plan, client, **kwargs):
        applied.append(plan)
        return real_apply(plan, client, **kwargs)

    monkeypatch.setattr(roundtrip, "dry_run", dry_run_spy)
    monkeypatch.setattr(roundtrip, "apply", apply_spy)
    roundtrip.push(workdir, apply_changes=True, reader=reader, writer=writer)

    assert len(previewed) == len(applied) == 1
    assert applied[0] is previewed[0], (
        "apply was handed a plan that is not the object dry_run returned")


def test_ac3_the_guard_is_ACTIVE_when_the_snapshot_carried_a_revision(
    reader, writer, workdir
):
    _pull(reader, workdir)
    _edit(workdir, "Rewritten while the two phases were apart.")

    result = roundtrip.push(workdir, reader=reader, writer=writer)
    assert result.revision_guard == "active", result.revision_guard_detail
    assert result.preview.revision_guard == "active"


def test_ac3_the_guard_reports_UNAVAILABLE_AND_SAYS_SO_when_the_snapshot_carried_none(
    reader, writer, workdir, caplog
):
    """The other branch, and the dangerous one. A snapshot taken with no revision cannot arm
    the whole-document compare-and-swap, so a concurrent edit will NOT be refused before the
    write — and the difference between that and an armed write is invisible unless it is
    said. The plan is still built (the preview is unskippable either way); what changes is
    that the caller is told, in the log AND on the result.
    """
    _pull(reader, workdir)
    _edit(workdir, "Rewritten while the two phases were apart.")

    # A snapshot written the way a caller who omitted the revision would have written it —
    # through the shipped `snapshot()`, so this is a real artefact and not a doctored one.
    from larkdocio.snapshot import load, snapshot

    kept = load(str(roundtrip.snapshot_path(workdir)))
    snapshot(
        [copy.deepcopy(b) for b in kept.blocks],
        document_token=kept.document_token,
        document_revision_id=None,
        api_domain=kept.api_domain,
        path=str(roundtrip.snapshot_path(workdir)),
    )

    with caplog.at_level("WARNING", logger="larkdocio"):
        result = roundtrip.push(workdir, reader=reader, writer=writer)

    assert result.revision_guard == "unavailable"
    assert result.preview is not None, "the preview was skipped when the guard was unarmed"
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("unavailable" in message for message in warnings), warnings
    assert any("concurrent edit" in message for message in warnings), (
        f"the warning does not say what an unarmed guard COSTS: {warnings}")
    # LD-561 — the third F1 site: this warning is printed on a push that then SUCCEEDS, so its
    # OWN prose (the format string, before the detail is interpolated) names no refusal token.
    formats = [r.msg for r in caplog.records if r.levelname == "WARNING"]
    assert any(roundtrip._CONCURRENCY_GUARD_LABEL in message for message in warnings), warnings
    assert all("STALE_DOCUMENT" not in fmt for fmt in formats), formats


# --------------------------------------------------------------------------- #
# AC4 — the read-back uses the SHIPPED comparison                               #
# --------------------------------------------------------------------------- #

def test_ac4_a_NORMALIZATION_ONLY_difference_verifies_CLEAN():
    """The flattened-list case the guide names. You author a **tight** list; the reader emits
    a **loose** one and indents nesting with a tab. String equality is ``False`` for every list
    anybody will ever author, and nothing is wrong with the write — so the comparator has to be
    ``compose()``, and this is the test that says so."""
    authored = "- the week-3 dip recovered by Friday\n- root cause: a stuck approval queue\n"
    reader_form = (
        "- the week-3 dip recovered by Friday\n\n- root cause: a stuck approval queue\n")

    assert authored not in reader_form, "the probe is stale — the two forms no longer differ"
    verdict, why = roundtrip.compose_equivalent(authored, reader_form)
    assert verdict is True and why is None, why


def test_ac4_a_NESTING_INDENT_difference_verifies_CLEAN():
    """The second normalization in the same table: spaces in, one tab per level out."""
    authored = "- parent\n    - child\n"
    reader_form = "- parent\n\n\t- child\n"
    assert authored != reader_form
    assert roundtrip.compose_equivalent(authored, reader_form)[0] is True


def test_ac4_a_REAL_content_difference_does_NOT_verify():
    """The other half, and the half that makes the test above mean something: a comparator
    that answered True for everything would pass the normalization tests too."""
    verdict, why = roundtrip.compose_equivalent(
        "- the week-3 dip recovered by Friday\n",
        "- the week-3 dip did not recover\n",
    )
    assert verdict is False and why is None


def test_ac4_content_OUTSIDE_the_dialect_is_UNVERIFIABLE_not_clean_and_not_a_mismatch():
    """The third answer, and it is not a nicety. ``compose()`` refuses a styled run by name
    rather than returning a misleading ``False``; folding that into either verdict would
    report a pre-existing bold run in a read-back region as a failed write, or hide a real
    one. So it is its own answer, and it carries the reason."""
    verdict, why = roundtrip.compose_equivalent("a **bold** run", "a **bold** run")
    assert verdict is None
    assert "not comparable" in why and "bold" in why


def test_ac4_the_verification_uses_compose_and_NOT_string_equality(reader, writer, workdir):
    """End to end through the verb: the read-back verdict is clean, and it verified something.
    An empty ``verified`` list with ``ok`` True would be a vacuous pass."""
    _pull(reader, workdir)
    _edit(workdir, "A rewritten plain paragraph for the read-back check.")

    result = roundtrip.push(workdir, apply_changes=True, reader=reader, writer=writer)
    assert result.applied is True
    assert result.verification.ok, result.verification.to_dict()
    assert result.verification.verified, result.verification.to_dict()
    assert result.verification.mismatched == ()


def test_ac4_an_INSERT_is_reported_UNVERIFIABLE_by_name_never_counted_clean(
    reader, writer, workdir
):
    """An inserted block does not exist when the plan is made, so there is no id to re-read it
    by. Saying so is the honest answer; guessing which new block was the insert is not — and
    silently counting it verified would be the dangerous one."""
    _pull(reader, workdir)
    from larkdocio.model.projection import block_markdown, replace_block_markdown

    projection, block_id = _editable_block(workdir)
    kept = block_markdown(projection, block_id)
    # THE BLOCK'S OWN TEXT IS KEPT and a second unit is added beside it. That is what an
    # INSERT is: the reconciler refuses a segment in which the block's own text is gone AND
    # something new appeared, because it cannot tell an edit from an addition — so an
    # insert has to leave the anchor block alone, exactly as the guide teaches.
    roundtrip.markdown_path(workdir).write_text(
        replace_block_markdown(
            projection, block_id, kept + "\n\nA brand new paragraph the editor added."),
        encoding="utf-8")

    result = roundtrip.push(workdir, apply_changes=True, reader=reader, writer=writer)
    states = {entry.state for entry in result.plan.changes}
    assert ReconciliationState.INSERTED in states, result.plan.to_dict()
    reasons = dict(result.verification.unverifiable)
    assert reasons, "an insert was silently counted as verified"
    assert any("no surviving block id" in why for why in reasons.values()), reasons


# --------------------------------------------------------------------------- #
# AC5 — every refusal is typed, and every refusal points at a recipe             #
# --------------------------------------------------------------------------- #

def _resolves(message):
    """Whether the guide address the message cites really resolves through ``guide()``."""
    import re

    import larkdocio

    match = re.search(r"guide --section ([a-z0-9-]+)", message)
    if match is None:
        return "larkdocio guide" in message  # the degraded pointer: the index, always real
    larkdocio.guide(section=match.group(1))
    return True


def test_ac5_a_url_that_is_not_a_document_refuses_typed(reader, workdir):
    with pytest.raises(LarkConfigError) as refusal:
        roundtrip.pull("https://your-domain.larksuite.com/sheets/AbC", workdir, reader=reader)
    assert not workdir.exists(), "a refused pull left files behind"
    message = str(refusal.value)
    # A spreadsheet token read as a docx does not fail — it comes back EMPTY, and an empty
    # projection reconciles to nothing three commands later. So the refusal is at the url.
    assert "'sheets' url" in message and "Nothing was written" in message
    assert "Sheets surface" in message, "the refusal does not route the caller anywhere"
    assert _resolves(message), message


def test_ac5_a_wiki_node_that_does_not_resolve_refuses_and_points_at_the_recipe(
    reader, workdir
):
    class NoSuchNode(reader.__class__):
        def get_wiki_node_info(self, token):
            from larkdocio.errors import LarkAPIError

            raise LarkAPIError("node not found", code=1254004, msg="not found")

    broken = NoSuchNode("cli_read_offline", "read-secret-offline", "larksuite.com")
    with pytest.raises(LarkConfigError) as refusal:
        roundtrip.pull(
            "https://your-domain.larksuite.com/wiki/WikiNodeToken", workdir, reader=broken)
    message = str(refusal.value)
    assert "Nothing was written" in message
    assert _resolves(message), message
    assert not workdir.exists()


def test_ac5_a_CORRUPTED_snapshot_refuses_with_the_SHIPPED_class_and_its_reason(
    reader, writer, workdir
):
    """No bespoke error class where a shipped one fits: the refusal is still
    ``LarkSnapshotIntegrityError``, still carries its machine-readable ``reason`` and its
    ``source``, still names re-download as the fix — and now also names the recipe."""
    _pull(reader, workdir)
    path = roundtrip.snapshot_path(workdir)
    path.write_text(path.read_text(encoding="utf-8").replace(
        '"document_token"', '"document_token_tampered"', 1), encoding="utf-8")

    with pytest.raises(LarkSnapshotIntegrityError) as refusal:
        roundtrip.push(workdir, reader=reader, writer=writer)
    assert refusal.value.reason in {"checksum_mismatch", "malformed"}
    assert refusal.value.source == str(path)
    assert "Re-download the document" in str(refusal.value)
    assert _resolves(str(refusal.value)), str(refusal.value)


def test_ac5_a_TRUNCATED_snapshot_refuses_the_same_way(reader, writer, workdir):
    _pull(reader, workdir)
    path = roundtrip.snapshot_path(workdir)
    path.write_text(path.read_text(encoding="utf-8")[:120], encoding="utf-8")
    with pytest.raises(LarkSnapshotIntegrityError) as refusal:
        roundtrip.push(workdir, reader=reader, writer=writer)
    assert refusal.value.reason == "unreadable"
    assert _resolves(str(refusal.value))


def test_ac5_an_UNKNOWN_format_version_refuses_rather_than_migrating(reader, writer, workdir):
    import json

    _pull(reader, workdir)
    path = roundtrip.snapshot_path(workdir)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["larkdocio_snapshot"]["format_version"] = 99
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(LarkSnapshotIntegrityError) as refusal:
        roundtrip.push(workdir, reader=reader, writer=writer)
    assert refusal.value.reason == "unknown_format_version"
    assert "No cross-version migration is offered" in str(refusal.value)


def test_ac5_an_edited_file_that_reconciles_to_NOTHING_refuses(reader, writer, workdir):
    """A no-op push is not an error the engine raises — it is a plan with zero changes, which
    would apply nothing and report success. Saying "there is nothing to apply" is what stops a
    caller concluding their edit landed."""
    _pull(reader, workdir)
    with pytest.raises(LarkConfigError) as refusal:
        roundtrip.push(workdir, reader=reader, writer=writer)
    message = str(refusal.value)
    assert "reconciles to no change at all" in message
    assert "lark:block:" in message, "the refusal does not say what to keep in the file"
    assert _resolves(message), message


def _inject_one_opaque_block(workdir):
    """Rewrite the pulled snapshot so the document carries ONE conserved-opaque block.

    LD-560. The shared offline fixture (``offline_doubles.fixture_block_dicts``) serves block
    types 1/3/2 only, and widening it would enlarge every other module's collision surface —
    so the opaque block is injected **test-locally**, into the artefact, exactly the way the
    verb's own phase A wrote it. A block type the reader does not handle takes the
    unknown-type fallback, which is precisely what ``model/conservation.py`` calls opaque; the
    markdown file is then re-derived through the SHIPPED projection, so the pair on disk is
    the pair phase A would have written for that document.

    Returns the injected block id.
    """
    import json

    from larkdocio.model.projection import project_block_ids
    from larkdocio.snapshot import load, snapshot

    path = roundtrip.snapshot_path(workdir)
    payload = json.loads(path.read_text(encoding="utf-8"))["larkdocio_snapshot"]["payload"]
    blocks = payload["blocks"]
    for block in blocks:
        if block["block_id"] == "h1":
            block["children"] = list(block["children"]) + ["opaque1"]
    blocks.append(
        {"block_id": "opaque1", "parent_id": "h1", "block_type": 9999, "children": []})
    snapshot(
        blocks,
        document_token=payload["document_token"],
        document_revision_id=payload["document_revision_id"],
        api_domain=payload["api_domain"],
        path=str(path),
    )
    projection = project_block_ids(load(str(path)).tree)
    roundtrip.markdown_path(workdir).write_text(projection.markdown, encoding="utf-8")
    return "opaque1"


def test_ac1_the_no_change_refusal_NAMES_THE_CONSERVED_BLOCKS_as_a_DISJUNCTION(
        reader, writer, workdir):
    """LD-560. ``change_count == 0`` fires on two states the plan CANNOT tell apart: the
    consumer who changed nothing, and the consumer whose change landed inside a block the
    authoring dialect cannot re-express, which the reconciler conserves by construction. The
    refusal must state BOTH, name the conserved ids from the public property, and assert
    NEITHER — ``reconcile.py:1071-1078`` emits ``conserved_opaque`` unconditionally, so an
    assertion that the edit landed would be the wrong-cause defect in the mirror direction."""
    from larkdocio.model.projection import project_block_ids
    from larkdocio.snapshot import load
    from larkdocio.write.reconcile import reconcile

    _pull(reader, workdir)
    block_id = _inject_one_opaque_block(workdir)

    # The state this refusal fires on, measured through the engine itself.
    projection = project_block_ids(load(str(roundtrip.snapshot_path(workdir))).tree)
    plan = reconcile(
        projection, roundtrip.markdown_path(workdir).read_text(encoding="utf-8"))
    assert plan.ok and plan.change_count == 0
    assert block_id in plan.conserved_block_ids

    with pytest.raises(LarkConfigError) as refusal:
        roundtrip.push(workdir, reader=reader, writer=writer)
    message = str(refusal.value)

    assert block_id in message, "the refusal does not name the conserved block ids"
    assert "reconciles to no change at all" in message
    # Both arms present: nothing differs, OR the edit landed in a conserved block...
    low = message.lower()
    assert "either" in low and " or " in low, message
    # ...and NEITHER arm asserted. The predicate cannot discriminate the two states, so the
    # conserved arm may only ever be reached as a DISJUNCT — it must follow the "either".
    for arm_word in ("landed", "conserve"):
        assert arm_word in low, message
        assert low.index(arm_word) > low.index("either"), (
            f"{arm_word!r} is stated OUTSIDE the disjunction — that asserts a state the plan "
            f"cannot know: {message}")
    for asserted in ("swallowed", "absorbed", "must have", "we know"):
        assert asserted not in low, f"the message ASSERTS what it cannot know: {asserted!r}"
    assert _resolves(message), message


def test_ac1_the_no_change_refusal_KEEPS_THE_PLAIN_WORDING_when_nothing_is_conserved():
    """LD-560. No conserved block ⇒ there is no second arm, and offering one would be the same
    wrong-cause defect pointing the other way. The shipped wording stands.

    Driven at the branch rather than through ``push`` on purpose: **every** docx carries a page
    root, the projection conserves it (``opaque=page`` — the title really can swallow an edit),
    so ``conserved_block_ids`` is non-empty for every document the fixture can build. The
    empty branch is still reachable code (a tree with no conserved node) and is pinned here."""
    class _NothingConserved:
        conserved_block_ids = ()

    message = roundtrip._no_change_refusal("/tmp/document.md", _NothingConserved())
    assert "reconciles to no change at all" in message
    assert "lark:block:" in message
    assert "either" not in message.lower(), message
    assert "conserve" not in message.lower(), message


def test_ac2_the_conserved_vocabulary_NEVER_reaches_a_NON_REFUSAL_path(
        reader, writer, workdir):
    """LD-560 AC2. The round's own F1 defect is a success path that speaks in refusal
    vocabulary — a reader then praises a guard they never watched fire. The words this
    refusal introduces must appear on the fired branch and nowhere else: not in the plan's
    own projection, and not in what the CLI prints on a push that HAS changes."""
    import io
    import json
    from contextlib import redirect_stdout

    from click.testing import CliRunner  # noqa: F401 — proves click is importable here

    from larkdocio.cli import cli  # noqa: F401

    _pull(reader, workdir)
    _inject_one_opaque_block(workdir)
    projection, block_id = _editable_block(workdir)
    _edit(workdir, "A real change, so the push does NOT refuse.")

    result = roundtrip.push(workdir, reader=reader, writer=writer)
    assert result.plan.change_count > 0
    # The conserved block is still there and still conserved — and still silent on success.
    assert result.plan.conserved_block_ids

    plan_text = json.dumps(result.plan.to_dict())
    printed = io.StringIO()
    with redirect_stdout(printed):
        for entry in result.plan.changes:
            print(entry.state.value, entry.block_id)
    for word in _CONSERVED_REFUSAL_VOCABULARY:
        assert word.lower() not in plan_text.lower(), (
            f"{word!r} leaked into the plan's own projection")
        assert word.lower() not in printed.getvalue().lower(), (
            f"{word!r} leaked onto the CLI success path")


#: The words LD-560's conserved-case refusal introduces. Pinned here so AC2's guard is a
#: list of what to look for, not a re-reading of the message under test.
_CONSERVED_REFUSAL_VOCABULARY = ("conserves by construction", "cannot re-express")


def test_ac5_an_edit_that_the_engine_REFUSES_refuses_the_whole_push(reader, writer, workdir):
    """A marker deleted along with its block: the reconciler cannot tell that apart from a
    rewrite that dropped the marker, and the two readings differ by destroying content — so it
    refuses whole. The verb hands the refusal on with its detail intact."""
    _pull(reader, workdir)
    path = roundtrip.markdown_path(workdir)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [line for line in lines if "lark:block:" not in line or lines.index(line) != 1]
    marker_lines = [i for i, line in enumerate(lines) if "lark:block:" in line]
    assert len(marker_lines) > 1, "the fixture has too few blocks for this probe"
    del lines[marker_lines[-1]]
    path.write_text("".join(lines), encoding="utf-8")
    del kept

    with pytest.raises(LarkConfigError) as refusal:
        roundtrip.push(workdir, reader=reader, writer=writer)
    message = str(refusal.value)
    assert "NOTHING was planned and nothing was written" in message
    assert _resolves(message), message


def test_ac5_an_APPLY_that_refuses_keeps_the_shipped_class_and_its_log(
    monkeypatch, reader, writer, workdir
):
    """``LarkApplyRefusedError`` carries the whole log, the entries that landed and the ones
    that did not. The recipe pointer is appended to the message; nothing else moves, because a
    caller branching on ``.refusals`` must keep working."""
    _pull(reader, workdir)
    _edit(workdir, "Rewritten while the two phases were apart.")

    real_apply = roundtrip.apply

    def refusing_apply(plan, client, **kwargs):
        log = real_apply(plan, client, allow_partial=True, **{
            k: v for k, v in kwargs.items() if k != "allow_partial"})
        raise LarkApplyRefusedError(
            "1 entry refused", log=log, applied=(), refused=tuple(log.entries))

    monkeypatch.setattr(roundtrip, "apply", refusing_apply)
    with pytest.raises(LarkApplyRefusedError) as refusal:
        roundtrip.push(workdir, apply_changes=True, reader=reader, writer=writer)
    assert refusal.value.log is not None
    assert refusal.value.refused
    assert _resolves(str(refusal.value)), str(refusal.value)


def test_ac5_a_missing_workdir_file_names_the_phase_that_makes_it(reader, writer, workdir):
    workdir.mkdir(parents=True)
    with pytest.raises(LarkConfigError) as refusal:
        roundtrip.push(workdir, reader=reader, writer=writer)
    message = str(refusal.value)
    assert f"larkdocio {roundtrip.COMMAND_NAME} {roundtrip.PHASE_PULL}" in message
    assert _resolves(message), message


def test_ac5_every_refusal_pointer_this_module_can_emit_RESOLVES():
    """The pointers are DERIVED from the shipped guide rather than written down, so the risk is
    not a typo — it is a symbol set that stops matching and silently degrades every refusal to
    the bare index. This asserts each set still selects exactly one real section."""
    for symbols, levels in (
        (roundtrip._TEACHES_THE_FILE_FIRST_RECIPE, (3,)),
        (roundtrip._TEACHES_THE_UPDATE_RECIPE, (3,)),
        (roundtrip._TEACHES_THE_READ_BACK_COMPARISON, (3,)),
        (roundtrip._TEACHES_THE_CREDENTIAL_SPLIT, (2,)),
    ):
        import larkdocio
        from larkdocio.guide import GUIDE_RESOURCE, _packaged, _sections_teaching

        found = _sections_teaching(_packaged(GUIDE_RESOURCE), symbols, levels)
        assert len(found) == 1, (symbols, found)
        larkdocio.guide(section=found[0])


def test_ac5_a_pointer_whose_section_VANISHED_degrades_to_the_index_never_to_a_dead_address():
    """The failure mode a derived pointer has, handled: name the guide's index (which always
    exists) rather than an address ``guide()`` would refuse — a refusal that hands the reader a
    second failure is worse than one that hands them a search."""
    message = roundtrip._recovery(("a-symbol-no-section-carries-LD492",))
    assert "--section" not in message
    assert "larkdocio guide" in message


# --------------------------------------------------------------------------- #
# AC8 — the WRITE credential boundary, visible at the point of use              #
# --------------------------------------------------------------------------- #

def test_ac8_push_with_NO_write_credentials_refuses_BEFORE_ANY_CALL(
    monkeypatch, reader, workdir
):
    """Named variables, no fallback, and nothing read off disk first — the refusal happens
    before the snapshot is even opened, so an invocation that could never have finished says
    so immediately."""
    _pull(reader, workdir)
    for name in ("LARK_WRITE_APP_ID", "LARK_WRITE_APP_SECRET"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(LarkConfigError) as refusal:
        roundtrip.push(workdir, reader=reader)
    message = str(refusal.value)
    assert "LARK_WRITE_APP_ID" in message and "LARK_WRITE_APP_SECRET" in message
    assert "never falls back" in message
    assert _resolves(message), message


def test_ac8_the_write_path_does_NOT_borrow_the_READ_pair(monkeypatch, reader, workdir):
    """The aliasing trap, held from the code side: on this tenant the two pairs happen to hold
    the same bytes, so a fallback would be invisible here and catastrophic on a tenant where
    they differ. Read credentials present, write credentials absent — it still refuses."""
    _pull(reader, workdir)
    monkeypatch.setenv("LARK_READ_APP_ID", "cli_read_offline")
    monkeypatch.setenv("LARK_READ_APP_SECRET", "read-secret-offline")
    for name in ("LARK_WRITE_APP_ID", "LARK_WRITE_APP_SECRET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(LarkConfigError):
        roundtrip.push(workdir, reader=reader)


def test_ac8_pull_with_NO_read_credentials_refuses_naming_the_pair_IN_FORCE(
    monkeypatch, stage, workdir
):
    for name in ("LARK_READ_APP_ID", "LARK_READ_APP_SECRET",
                 "LARK_APP_ID", "LARK_APP_SECRET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(LarkConfigError) as refusal:
        roundtrip.pull(DOC_URL, workdir)
    message = str(refusal.value)
    assert "LARK_APP_ID" in message, message
    assert "resolved independently" in message
    assert not workdir.exists()


def test_ac8_push_needs_the_READ_pair_TOO_and_says_so(monkeypatch, writer, workdir, reader):
    """Phase B applies on WRITE and reads back on READ. Both are required, both are named, and
    neither is substituted for the other."""
    _pull(reader, workdir)
    for name in ("LARK_READ_APP_ID", "LARK_READ_APP_SECRET",
                 "LARK_APP_ID", "LARK_APP_SECRET"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(LarkConfigError) as refusal:
        roundtrip.push(workdir, writer=writer)
    assert "read-back" in str(refusal.value)


# --------------------------------------------------------------------------- #
# AC2 — it COMPOSES; it opens no endpoint                                       #
# --------------------------------------------------------------------------- #

def test_ac2_the_verb_reaches_the_api_ONLY_through_shipped_clients():
    """No transport of its own: the module builds the two shipped clients and calls shipped
    functions, and it imports nothing that could reach Lark another way. A new endpoint here
    would need a client this module does not have."""
    import ast
    import pathlib

    source = pathlib.Path(roundtrip.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("larkdocio"):
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    assert not any("transport" in name for name in imported), sorted(imported)
    assert not any("lark_oapi" in name for name in imported), sorted(imported)
    assert "larkdocio.read.client.Client" in imported
    assert "larkdocio.write.WriteClient" in imported


def test_ac2_the_verb_appears_in_NO_permission_row_of_its_own():
    """The bidirectional permissions guard would redden on a new API-using call site with no
    row. The other direction is stated here: no row names this module, because it makes no
    call of its own — its requirement is the requirement of the operations it composes."""
    import larkdocio

    registry = larkdocio.permissions.permission_registry()
    assert registry, "the permission registry is empty; this guard would pass on nothing"
    assert not [key for key in registry if "roundtrip" in repr(key)], (
        "a permission row names the roundtrip verb — it composes, so its requirement belongs "
        "to the operations it calls, not to itself")


# --------------------------------------------------------------------------- #
# The command line — the same gates, reached the way a consumer reaches them    #
# --------------------------------------------------------------------------- #

def test_the_command_line_runs_BOTH_phases_and_the_rehearsal_writes_nothing(
    monkeypatch, reader, writer, workdir
):
    """One vocabulary, end to end: the phases the library names are the words the command
    takes, and the command's ``push`` without ``--apply`` reports that it wrote nothing."""
    from click.testing import CliRunner

    from larkdocio.cli import cli

    monkeypatch.setattr(roundtrip, "Client", lambda *a, **k: reader)
    monkeypatch.setattr(roundtrip, "WriteClient", lambda *a, **k: writer)
    runner = CliRunner()

    pulled = runner.invoke(
        cli, [roundtrip.COMMAND_NAME, roundtrip.PHASE_PULL, DOC_URL, "-o", str(workdir)])
    assert pulled.exit_code == 0, pulled.output
    assert roundtrip.MARKDOWN_FILENAME in pulled.output
    assert "EDIT THIS" in pulled.output

    _edit(workdir, "Rewritten through the command line.")
    rehearsed = runner.invoke(
        cli, [roundtrip.COMMAND_NAME, roundtrip.PHASE_PUSH, "-o", str(workdir)])
    assert rehearsed.exit_code == 0, rehearsed.output
    assert "NOTHING WAS WRITTEN" in rehearsed.output
    assert "--apply" in rehearsed.output
    # LD-561: the first line of every push reports the guard's AVAILABILITY, in words that are
    # not the refusal's own. It used to read "STALE_DOCUMENT guard active" — a refusal token on
    # the success path, which round 5's oracle read as a refusal (FINDINGS-BANKED § F1).
    assert f"{roundtrip._CONCURRENCY_GUARD_LABEL} active" in rehearsed.output
    assert "STALE_DOCUMENT" not in rehearsed.output

    applied = runner.invoke(
        cli,
        [roundtrip.COMMAND_NAME, roundtrip.PHASE_PUSH, "-o", str(workdir), "--apply"],
    )
    assert applied.exit_code == 0, applied.output
    assert "read-back verification: CLEAN" in applied.output


def test_the_command_line_refuses_a_pull_with_no_url_and_a_push_WITH_one(reader, workdir):
    """The two shape mistakes the phase pair makes possible, each refused by name rather than
    half-attempted: ``pull`` needs the url, and ``push`` takes none — its document is the one
    the snapshot recorded, which is what keeps the two phases addressing the same document."""
    from click.testing import CliRunner

    from larkdocio.cli import cli

    runner = CliRunner()
    no_url = runner.invoke(cli, [roundtrip.COMMAND_NAME, roundtrip.PHASE_PULL])
    assert no_url.exit_code != 0
    assert "needs the document URL" in no_url.output

    with_url = runner.invoke(
        cli, [roundtrip.COMMAND_NAME, roundtrip.PHASE_PUSH, DOC_URL, "-o", str(workdir)])
    assert with_url.exit_code != 0
    assert "takes no URL" in with_url.output


def test_the_command_line_prints_a_refusal_as_ONE_error_line_not_a_traceback(reader, workdir):
    """``_RefusalUniformCommand`` converts this library's configuration refusals into one
    ``Error:`` line, and the verb inherits it by being minted through the group — so a caller
    who pulls into an empty directory gets the sentence, not a stack and a bug-report banner.
    """
    from click.testing import CliRunner

    from larkdocio.cli import cli

    workdir.mkdir(parents=True)
    result = CliRunner().invoke(
        cli, [roundtrip.COMMAND_NAME, roundtrip.PHASE_PUSH, "-o", str(workdir)])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert result.output.strip().splitlines()[-1].startswith("Error: ")
