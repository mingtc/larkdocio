"""The always-on offline half of ``test_live_base_computed_provenance`` (LD-270 AC9).

The live arm runs only with write credentials and a network. What it *claims* — that the
configured Base is a copy **template** and never a write target, that no ``parent_node`` or
folder token reaches anything, that every disposable it makes is ledgered before it can be
lost, that it settles the async copy rather than sleeping, and that it skips loudly rather
than passing silently — is exactly the class of claim a credential-less run verifies by not
running. So it is verified **here**, statically, on every plain ``pytest``:

* **the template is a SOURCE, structurally** — the configured token reaches exactly one call,
  ``copy_app``'s first argument, and every other call in the arm takes the copy's token. It is
  read off the arm's own **syntax tree** rather than out of its prose, so "it did not write the
  template" is a structural fact about the code rather than a promise its docstring makes;
* **no ``parent_node``, no folder token, anywhere** — a copy landing in a configured folder is
  the OTHER way a real Base gets touched, and a guard watching write targets alone would miss
  it entirely;
* **the copy is ledgered before anything else can fail**, and deleted in a ``finally``;
* **the settle is the shipped bounded one** — no ``sleep``, no hand-rolled poll;
* **loud skips, twice over** — the credential skip goes through
  ``base_write_harness.missing_reason`` (which names what is missing) and the no-template skip
  is its own message, because an arm that passes with no Lookup to read proves nothing;
* **the arm asserts its own premise** — that the copy really carries a Lookup — so a template
  that lost its Lookup reddens instead of passing vacuously.

It imports nothing from the live arm and runs no gate.
"""
import ast
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent
_ARM = _TESTS / "test_live_base_computed_provenance.py"


@pytest.fixture(scope="module")
def arm_source():
    return _ARM.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def arm_tree(arm_source):
    return ast.parse(arm_source)


def test_the_arm_exists_and_is_marked_live_write(arm_source):
    assert "pytestmark = pytest.mark.live_write" in arm_source, (
        "the arm must be deselected by default; an unmarked live test runs in every plain "
        "pytest and turns a credential-less clone red")


def test_the_arm_reads_the_template_TOKEN_from_the_canary_helper_and_not_a_LITERAL(arm_source):
    """A hard-coded app token is how a live arm ends up pointed at somebody's real Base."""
    assert "canary_support.scratch_base_url()" in arm_source
    assert "canary_support.parse_base_url" in arm_source
    for literal in ("app_token=\"", "bascn", "BaseScratchExample", "https://"):
        assert literal not in arm_source, f"a hard-coded target ({literal}) is in the arm"


def test_the_configured_token_reaches_EXACTLY_ONE_call_and_it_is_the_COPY_SOURCE(arm_tree):
    """The distinction the whole arm rests on: the template is read **from**, never written
    **to**. Structurally, that means the ``template_app_token`` fixture's value may appear as
    ``copy_app``'s source and in read-only assertions, and may never be handed to a mutating
    verb."""
    mutating = {"create_table", "rename_base", "rename_table", "batch_create_tables",
                "delete", "delete_app", "update_field", "batch_update", "batch_create",
                "create_field", "delete_field", "apply", "schema_apply"}
    offenders = []
    for node in ast.walk(arm_tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else (
            node.func.id if isinstance(node.func, ast.Name) else "")
        if name not in mutating:
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(arg, ast.Name) and arg.id == "template_app_token":
                offenders.append(name)
    assert not offenders, (
        f"the template is handed to a mutating verb {offenders} — it is a copy SOURCE and a "
        "read source, and nothing else")

    copies = [node for node in ast.walk(arm_tree)
              if isinstance(node, ast.Call)
              and isinstance(node.func, ast.Attribute) and node.func.attr == "copy_app"]
    assert len(copies) == 1, "the arm makes exactly one copy"
    assert isinstance(copies[0].args[0], ast.Name)
    assert copies[0].args[0].id == "template_app_token"


def test_NO_PARENT_NODE_and_the_ONLY_FOLDER_is_the_CONFIGURED_DISPOSABLES_ONE(
        arm_source, arm_tree):
    """The other way a real Base gets touched, and the one a write-target guard misses.

    TRANSFORMED, NOT DELETED. This used to forbid ``folder_token`` outright, reasoning that a
    copy naming a folder would land inside somebody's tree while a keyless copy went to the
    app's own default and touched no configured node. **The reason stands** — never write into
    a tree somebody else owns. **The conclusion does not**: the app's own default is a space
    with no human interface, whose trash cannot be listed, so the keyless copy was the
    unrecoverable option rather than the polite one. The arm now names exactly one folder: the
    account holder's own designated disposables folder, read through
    ``require_disposables_folder()``. ``parent_node`` / ``parent_type`` stay forbidden.
    """
    # Checked on the CODE, not on the prose: the arm's own docstring names `parent_node` in
    # order to say it is never passed, and a substring sweep cannot tell those two apart.
    keywords = {kw.arg for node in ast.walk(arm_tree) if isinstance(node, ast.Call)
                for kw in node.keywords if kw.arg}
    assert not any("parent" in kw for kw in keywords), keywords
    identifiers = {node.id for node in ast.walk(arm_tree) if isinstance(node, ast.Name)}
    identifiers |= {node.attr for node in ast.walk(arm_tree)
                    if isinstance(node, ast.Attribute)}
    for banned in ("parent_node", "parent_type", "parent_table"):
        assert banned not in identifiers, f"{banned} is referenced by the arm's code"
    assert "require_disposables_folder" in identifiers, (
        "the one destination the arm may name is the configured disposables folder")


def test_the_COPY_is_ledgered_BEFORE_anything_else_can_fail(arm_source):
    """An unrecorded disposable is a lost one, so the record happens between the call that
    mints the token and the first thing that could raise."""
    minted = arm_source.index("echo = schema.copy_app(")
    recorded = arm_source.index("ledger.record_create(token, title)")
    guarded = arm_source.index("    try:", minted)
    assert minted < recorded < guarded, (
        "the ledger write must sit between the copy and the try block — recorded inside the "
        "try, a failure before it would leave a Base nobody can name")
    assert "finally:" in arm_source and "record_delete" in arm_source


def test_the_arm_SETTLES_the_async_copy_and_never_SLEEPS_THROUGH_IT(arm_source, arm_tree):
    """Copy is the one asynchronous Base op. A fixed sleep fails on a Base large enough to
    take longer and wastes time on every Base that is already there — so the **settle** must
    stay a settle, and no wait may stand in for it.

    LD-284 found a **second** asynchrony behind the first: the settle answers when the copied
    app is readable, and the copy's computed columns materialise under 3 s later. Waiting that
    out needs a wait, so the ban is now precise rather than absolute — **the only wait allowed
    is inside the materialisation re-read, and it carries the same two properties the settle
    does: a bounded attempt ceiling, and spacing waited only between attempts.** A sleep
    anywhere else is the defect this test was written for.
    """
    assert "from larkdocio.base.schema_settle import settle" in arm_source
    assert "settle(lambda: read.get_app(token))" in arm_source

    waiter = _function(arm_tree, "_read_until_the_computed_cells_MATERIALISE")
    inside = {id(node) for node in ast.walk(waiter)}
    for node in ast.walk(arm_tree):
        if not isinstance(node, ast.Call):
            continue
        name = (node.func.attr if isinstance(node.func, ast.Attribute)
                else (node.func.id if isinstance(node.func, ast.Name) else ""))
        if name == "sleep":
            assert id(node) in inside, (
                "the arm sleeps outside the bounded materialisation re-read — the settle "
                "contract is not something a wait may stand in for")

    assert "_MATERIALISATION_ATTEMPTS = " in arm_source, (
        "the materialisation re-read must carry an attempt CEILING: a poll with no ceiling is "
        "a hang wearing a loop's clothes")
    assert "range(1, _MATERIALISATION_ATTEMPTS + 1)" in arm_source
    assert "if attempt < _MATERIALISATION_ATTEMPTS:" in arm_source, (
        "the spacing must be waited only BETWEEN attempts — never after the last, and never "
        "before the first")


def test_BOTH_skip_paths_are_LOUD(arm_source):
    """A silent pass is worse than a skip, and an arm with no Lookup to read proves nothing."""
    assert "base_write_harness.missing_reason()" in arm_source, (
        "the credential skip must name what is missing, which the harness helper does")
    assert "no template Base configured" in arm_source
    assert "LARKDOCIO_SCRATCH_BASE" in arm_source, (
        "the no-template skip must name the variable a reader has to set")
    assert arm_source.count("pytest.skip") >= 2


def test_the_arm_ASSERTS_ITS_OWN_PREMISE_rather_than_passing_vacuously(arm_source):
    """Every other assertion in the arm is about a Lookup column. If the template stopped
    carrying one, they would all pass on ``None`` — so one test exists to fail first."""
    assert "the copied Base carries no Lookup column" in arm_source
    assert "arm is proving nothing about a live Lookup" in arm_source


def _function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"the arm no longer defines {name}")


_DISPATCH_TEST = "test_the_live_wrapper_type_is_the_TARGET_FIELDS_not_the_columns"


def test_ld284_the_dispatch_arm_WAITS_OUT_the_window_and_then_ASSERTS(arm_source, arm_tree):
    """LD-284 — the arm used to **skip** when the copy's Lookup carried no values, on one run
    that had been written up as the shape a settled copy has.

    The re-probe measured it instead: the values are absent ≤1.7 s after the settle and present
    by ~2.7 s (2/2 copies read early, 2/2 content-carrying copies read later — both record
    routes, out to t+30 s on both ladders and t+120 s on one; the ladder's third copy is the
    ``without_content`` control, which has no rows at all). So
    there is a real **sub-3-second materialisation window** behind the settle — the settle
    proves the app is *readable*, not that a mirrored column has *recomputed* — and this arm was
    reading inside it. A skip was the wrong response twice over: it reported green having
    checked nothing, and it hard-coded one side of a race as a shape.

    The arm must therefore (a) carry no restatement of the falsified shape, (b) wait the window
    out on the settle's own bounded, response-driven discipline, and (c) **assert** the dispatch
    rule afterwards, citing the capture so the next reader checks the measurement, not the
    prose.
    """
    for falsified in ("a settled copy reads back",
                      "none of its computed cells",
                      "settled copy comes back with the Lookup",
                      "carries no cell values yet"):
        assert falsified not in arm_source, (
            f"the arm still restates the falsified cell-less shape ({falsified!r}) — LD-284 "
            "measured a sub-3-second window, not a shape")

    node = _function(arm_tree, _DISPATCH_TEST)
    skips = [c for c in ast.walk(node)
             if isinstance(c, ast.Call) and getattr(c.func, "attr", None) == "skip"]
    assert not skips, (
        f"{_DISPATCH_TEST} still skips instead of asserting — with the window waited out, a "
        "cell-less copy is a finding rather than the expected shape")

    assert "_read_until_the_computed_cells_MATERIALISE(read, token)" in arm_source, (
        "the fixture must wait the materialisation window out before the assertions read the "
        "document — otherwise the arm is back to reading inside the race")
    assert "LD-284" in arm_source and "ld284-01-copy-lookup-materialisation.json" in arm_source, (
        "the arm must cite the capture that measured the window, so the next reader can check "
        "the measurement rather than the prose")


def test_the_arm_uses_the_SHIPPED_read_path_and_not_a_private_re_derivation(arm_source):
    """What is under test is the provenance a consumer gets, so the arm reads the copy the way
    a consumer would and inspects ``table.computed_columns``."""
    assert "from larkdocio.base.read import read_base" in arm_source
    assert "read_base(token, client=read)" in arm_source
    assert "table.computed_columns" in arm_source


def _imported(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


def test_the_harness_leg_this_arm_leans_on_treats_ALREADY_DELETED_as_DELETED():
    """A harness gap this arm found on its second run, pinned here because it is the leg the
    arm's ``finally`` depends on.

    ``1061007`` (*"file has been delete"*) is the drive delete's answer for a token already in
    the trash — the outcome the caller asked for, reached by another route. It was classified
    as a genuine failure and raised, so a teardown over a ledger entry the tenant had since
    released turned a clean sweep into a red run. It is now a success-shaped code: reported
    ``deleted``, not raised, and not filed as a retryable lag either, because there is nothing
    left to retry.
    """
    import base_write_harness

    assert 1061007 in base_write_harness.ALREADY_DELETED_CODES
    assert not set(base_write_harness.ALREADY_DELETED_CODES) & set(
        base_write_harness.NOT_YET_ADDRESSABLE_CODES), (
        "an already-deleted code that is also a lag code would be retried against a token "
        "that is already gone")
