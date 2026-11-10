"""LD-234 — the request compiler over the EXISTING engine.

Offline, every test. The compiler is a **pure function of a plan** — it makes no network
call, and the batches it produces are driven through the *shipped* ``dry_run`` → ``apply``
gate with the shared fake transport from :mod:`tests.write_harness` (the doubles are singly
owned there; nothing is re-authored here).

The amplifier is the same committed LD-197 corpus LD-233 reconciles
(``tests/fixtures/reconcile/``): real LLM edits of a marked projection, reconciled to a
plan and then compiled, so the AC scans run over agent output rather than over the shapes
this module happens to imagine.
"""
import json
from pathlib import Path

import pytest

import private_tree  # noqa: E402  (LD-691)

from log_reading_apply import reading_the_log
from larkdocio.model.projection import (
    BlockIdProjection,
    project_block_ids,
    strip_block_id_markers,
)
from larkdocio.model.renderer import (
    # ``_escape_literals`` is the reader's OWN escaper — the LD-239 fixtures escape their
    # marker with it rather than by hand, so the "escaped marker decodes back into a real
    # one" domain is the real one and not a plausible-looking spelling of it.
    _escape_literals,
    block_id_marker,
    unescape_literals,
)
from larkdocio.write import compile_reconciliation as _compile_from_package
from larkdocio.write.compiler import (
    COMPILED_REQUEST_FAMILIES,
    RECONCILIATION_COMPILER_CONTRACT,
    compile_reconciliation,
)
from larkdocio.write.encode import create_batches, encode_content
from larkdocio.write.model import (
    MAX_CHILDREN_PER_CALL,
    AnchorById,
    DeleteRequest,
    EditRequest,
    InsertPosition,
    InsertRequest,
    RefusalReason,
    RefusedError,
)
from larkdocio.write.apply import apply
apply = reading_the_log(apply)
from larkdocio.write.intrabatch import COMMIT_THEN_ANCHOR_RULE
from larkdocio.write.model import ApplyLog
from larkdocio.write.preview import Plan, dry_run
from larkdocio.write.reconcile import AbsentBlockDisposition, reconcile

# Shared fake-transport doubles + node builders (LD-088 / LD-212): singly owned in
# ``write_harness``, imported here — nothing re-authored.
from write_harness import (
    RoutingOpener,
    _block_payload,
    _client,
    _page,
    _para,
    _parent_payload,
    _run,
)

FIXTURES = Path(__file__).parent / "fixtures" / "reconcile"


# --------------------------------------------------------------------------- #
# Helpers — hand-built projections, and the committed corpus.                  #
# --------------------------------------------------------------------------- #

def projection(*blocks, opaque=()):
    """A :class:`BlockIdProjection` over ``(block_id, markdown)`` pairs, plus an optional
    leading unmarked head (a pair whose id is ``None``)."""
    parts = []
    ids = []
    for block_id, markdown in blocks:
        if block_id is None:
            parts.append(markdown)
            continue
        ids.append(block_id)
        parts.append(f"<!-- lark:block:{block_id} -->\n{markdown}")
    return BlockIdProjection(
        markdown="\n\n".join(parts) + "\n",
        block_ids=tuple(ids),
        opaque_block_ids=tuple(opaque),
    )


def edited(*blocks):
    """The same shape as :func:`projection`, but only the Markdown — what an agent hands
    back."""
    return projection(*blocks).markdown


def compiled(p, markdown, **kwargs):
    """Reconcile then compile, the whole round in one call."""
    plan = reconcile(p, markdown, **kwargs)
    assert plan.ok, [r.detail for r in plan.refusals]
    return compile_reconciliation(plan, p)


def corpus_sources():
    return json.loads((FIXTURES / "leg2-sources.json").read_text(encoding="utf-8"))


def corpus_trials():
    return sorted((FIXTURES / "leg2-trials").glob("*.json"))


def source_projection(name):
    src = corpus_sources()[name]
    return BlockIdProjection(
        markdown=src["markdown"],
        block_ids=tuple(src["block_ids"]),
        opaque_block_ids=tuple(src["opaque_block_ids"]),
    )


def corpus_batches():
    """Every committed trial that reconciles AND compiles, as ``(name, projection,
    requests)``.

    Both dispositions are tried so a trial that dropped a marker still contributes its
    delete shape rather than being silently skipped. A trial the compiler refuses is
    skipped **here** and asserted on its own in ``test_ac3_*`` — a refusal is a typed
    answer, not a corpus hole.
    """
    out = []
    for name, p, plan in corpus_plans():
        try:
            out.append((name, p, compile_reconciliation(plan, p)))
        except RefusedError:
            continue
    assert len(out) >= 15, f"the corpus amplifier went thin: {len(out)} batches"
    return out


def corpus_plans():
    """Every committed trial that reconciles, as ``(name, projection, plan)``."""
    out = []
    for path in corpus_trials():
        trial = json.loads(path.read_text(encoding="utf-8"))
        p = source_projection(trial["trial"]["doc"])
        for disposition in AbsentBlockDisposition:
            plan = reconcile(p, trial["edited_document"], absent=disposition)
            if plan.ok:
                out.append((f"{path.stem}:{disposition.value}", p, plan))
                break
    return out


# --------------------------------------------------------------------------- #
# AC1 — compiles to the SHIPPED request families ONLY, anchored by AnchorById.  #
# --------------------------------------------------------------------------- #

def test_ac1_a_mixed_reconciliation_introduces_no_new_request_type():
    p = projection(
        (None, "# Title"),
        ("p1", "one"),
        ("p2", "two"),
        ("p3", "three"),
    )
    requests = compiled(
        p,
        edited((None, "# Title"), ("p1", "one edited"), ("p2", "two\n\nadded beside"), ),
        absent=AbsentBlockDisposition.DELETE,
    )
    kinds = {type(r) for r in requests}
    assert kinds == {EditRequest, InsertRequest, DeleteRequest}
    assert kinds <= set(COMPILED_REQUEST_FAMILIES)


def test_ac1_every_compiled_request_is_one_of_the_three_shipped_families():
    for name, _p, requests in corpus_batches():
        for request in requests:
            assert type(request) in COMPILED_REQUEST_FAMILIES, f"{name}: {request!r}"


def test_ac1_every_compiled_anchor_is_an_anchor_by_id():
    for name, _p, requests in corpus_batches():
        for anchor in anchors_of(requests):
            assert isinstance(anchor, AnchorById), f"{name}: {anchor!r}"


def anchors_of(requests):
    for request in requests:
        if isinstance(request, EditRequest):
            yield request.anchor
        elif isinstance(request, InsertRequest):
            yield request.reference
        elif isinstance(request, DeleteRequest):
            yield request.target


def test_ac1_the_compiled_families_are_the_engines_own_shipped_types():
    """Not a list this module keeps: each family is the class the shipped engine already
    dispatches on, so a fourth family could not be added without the op registry
    knowing."""
    from larkdocio.write import ops

    registered = {desc.request_type for desc in ops.OPS}
    for family in COMPILED_REQUEST_FAMILIES:
        assert family in registered, family


# --------------------------------------------------------------------------- #
# The live-document doubles: the SHIPPED gate, driven end to end offline.       #
# --------------------------------------------------------------------------- #

def doc_tree():
    """A four-paragraph document whose block ids are the ones the projection emits."""
    return _page(
        _para("p1", "one"),
        _para("p2", "two"),
        _para("p3", "three"),
        _para("p4", "four"),
    )


def live(tree, **overrides):
    """``block_id -> get_block payload`` for every block in ``tree``, plus its parent."""
    blocks = {
        "root": _parent_payload("root", [c.block_id for c in tree.children]),
    }
    for child in tree.children:
        text = overrides.get(child.block_id, child.content[0].content)
        blocks[child.block_id] = _block_payload(
            child.block_id, [_run(text)], parent_id="root"
        )
    return blocks


def run_batch(requests, tree, opener, *, revision=None):
    """The SHIPPED gate, unchanged: dry_run → apply. No wrapper of this issue's own."""
    preview = dry_run(requests, tree, document_revision_id=revision)
    return preview, apply(preview, _client(opener), "doc-1")


# --------------------------------------------------------------------------- #
# AC2 — flows through the SHIPPED dry_run → apply gate; ordinary apply-log.     #
# --------------------------------------------------------------------------- #

def test_ac2_the_batch_previews_as_an_ordinary_plan_and_applies_to_an_ordinary_log():
    tree = doc_tree()
    p = project_block_ids(tree)
    requests = compiled(p, p.markdown.replace("\ntwo\n", "\ntwo edited\n"))
    opener = RoutingOpener(blocks=live(tree), document_revisions=["rev-1"])

    preview, log = run_batch(requests, tree, opener)

    assert isinstance(preview, Plan)
    assert isinstance(log, ApplyLog)
    assert [e.outcome for e in log.entries] == ["applied"]
    assert [e.block_id for e in log.entries] == ["p2"]
    # The ordinary vocabulary, round-tripping like any other apply-log.
    assert ApplyLog.from_dict(log.to_dict()).to_dict() == log.to_dict()


def test_ac2_the_compiler_owns_no_apply_path_and_no_second_gate():
    """Structural, not incidental: the module defines no gate of its own and cannot
    write — it imports no client and no apply engine."""
    import ast
    import inspect

    import larkdocio.write.compiler as module

    source = inspect.getsource(module)
    tree = ast.parse(source)
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert not defined & {"apply", "dry_run", "preview"}
    imported = {
        (n.module or "")
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
    }
    assert "larkdocio.write.apply" not in imported
    assert "larkdocio.write.client" not in imported
    assert "larkdocio.write.preview" not in imported


def test_ac2_a_plan_that_refused_compiles_to_nothing_at_all():
    p = projection(("p1", "one"))
    plan = reconcile(p, edited(("p1", "one"), ("doxcnNOTREAL", "smuggled")))
    assert not plan.ok
    with pytest.raises(RefusedError) as excinfo:
        compile_reconciliation(plan, p)
    assert excinfo.value.refusal.reason is RefusalReason.MARKER_INVENTED


# --------------------------------------------------------------------------- #
# AC3 — NO INTRA-BATCH DEPENDENCIES, proven by a scan over a corpus.            #
# --------------------------------------------------------------------------- #

def test_ac3_no_compiled_request_targets_a_block_the_batch_itself_creates():
    """The scan: every anchor names a block the PROJECTION emitted, so it exists at plan
    time. A dependency on the batch's own creation is unrepresentable — a created id does
    not exist until apply hands it back."""
    for name, p, requests in corpus_batches():
        emitted = set(p.block_ids)
        for anchor in anchors_of(requests):
            assert anchor.block_id in emitted, f"{name}: {anchor.block_id}"


@pytest.mark.parametrize("shape,edit", [
    ("insert beside an edit", lambda m: m.replace("\ntwo\n", "\ntwo\n\nadded\n")
                                         .replace("\nthree\n", "\nthree edited\n")),
    ("insert beside an insert", lambda m: m.replace("\ntwo\n", "\ntwo\n\nfirst\n\nsecond\n")),
    ("insert beside a later edit", lambda m: m.replace("\none\n", "\none\n\nadded\n")
                                              .replace("\nthree\n", "\nthree edited\n")),
])
def test_ac3_the_adjacency_corpus_is_dependency_free(shape, edit):
    tree = doc_tree()
    p = project_block_ids(tree)
    requests = compiled(p, edit(p.markdown))
    emitted = set(p.block_ids)
    assert requests, shape
    for anchor in anchors_of(requests):
        assert anchor.block_id in emitted, shape


def test_ac3_two_commits_are_named_when_the_intent_genuinely_needs_them():
    """Not an opaque refusal: the detail says the change needs two commits and carries the
    engine's own commit-then-anchor rule."""
    p = projection(("p1", "- a"))
    plan = reconcile(p, edited(("p1", "- a\n- b\n- c")))
    assert plan.ok, [r.detail for r in plan.refusals]
    with pytest.raises(RefusedError) as excinfo:
        compile_reconciliation(plan, p)
    detail = excinfo.value.refusal.detail
    assert "two separate commits" in detail
    assert COMMIT_THEN_ANCHOR_RULE in detail


def test_ac3_the_compiled_order_is_the_engines_index_semantics():
    """Edits (index-free) first, inserts bottom-up so none shifts an index another already
    computed, deletes last because a delete shifts every index below it."""
    tree = doc_tree()
    p = project_block_ids(tree)
    edited_markdown = (
        p.markdown
        .replace("\none\n", "\none\n\nafter one\n")
        .replace("\ntwo\n", "\ntwo\n\nafter two\n")
        .replace("\nthree\n", "\nthree edited\n")
        .replace("<!-- lark:block:p4 -->\nfour\n", "")
    )
    requests = compiled(p, edited_markdown, absent=AbsentBlockDisposition.DELETE)
    kinds = [type(r) for r in requests]
    assert kinds == [EditRequest, InsertRequest, InsertRequest, DeleteRequest]
    # bottom-up: the LATER anchor's insert is issued first.
    assert [r.reference.block_id for r in requests if isinstance(r, InsertRequest)] == [
        "p2", "p1",
    ]


# --------------------------------------------------------------------------- #
# AC4 — STALE_DOCUMENT inherited, unchanged (D5): whole batch, zero writes.     #
# --------------------------------------------------------------------------- #

def test_ac4_an_out_of_band_edit_between_plan_and_apply_refuses_the_whole_batch():
    tree = doc_tree()
    p = project_block_ids(tree)
    requests = compiled(
        p,
        p.markdown.replace("\ntwo\n", "\ntwo edited\n").replace("\nthree\n", "\nthree edited\n"),
    )
    assert len(requests) == 2
    # planned at revision 7; the document is at 9 by the time apply re-reads it.
    opener = RoutingOpener(blocks=live(tree), document_revisions=["rev-9"])

    _preview, log = run_batch(requests, tree, opener, revision="rev-7")

    assert [e.outcome for e in log.entries] == ["refused", "refused"]
    assert {e.refusal.reason for e in log.entries} == {RefusalReason.STALE_DOCUMENT}
    assert opener.writes == [], "a stale batch must issue ZERO writes"


def test_ac4_a_re_plan_at_the_current_revision_proceeds():
    tree = doc_tree()
    p = project_block_ids(tree)
    requests = compiled(p, p.markdown.replace("\ntwo\n", "\ntwo edited\n"))
    opener = RoutingOpener(blocks=live(tree), document_revisions=["rev-9"])

    _preview, log = run_batch(requests, tree, opener, revision="rev-9")

    assert [e.outcome for e in log.entries] == ["applied"]
    assert opener.writes, "the re-plan must actually write"


def test_ac4_the_guard_is_the_engines_own_and_the_compiler_offers_no_second_place():
    """``document_revision_id`` is a ``dry_run`` keyword; the compiler neither takes it nor
    caches one, so there is no second guard to fall out of step with the first."""
    import inspect

    from larkdocio.write.preview import dry_run as shipped_dry_run

    assert "document_revision_id" in inspect.signature(shipped_dry_run).parameters
    assert "document_revision_id" not in inspect.signature(compile_reconciliation).parameters
    # and no revision machinery of its own: the guard's module is not even imported.
    import larkdocio.write.compiler as module
    assert "larkdocio.write.revision" not in inspect.getsource(module)


# --------------------------------------------------------------------------- #
# AC5 — the existing batching is REUSED, not reinvented.                       #
# --------------------------------------------------------------------------- #

def test_ac5_a_nested_insert_is_split_by_the_engines_own_create_batches():
    tree = doc_tree()
    p = project_block_ids(tree)
    added = "- parent\n  - child one\n  - child two"
    requests = compiled(p, p.markdown.replace("\ntwo\n", f"\ntwo\n\n{added}\n"))
    inserts = [r for r in requests if isinstance(r, InsertRequest)]
    assert len(inserts) == 1

    opener = RoutingOpener(blocks=live(tree))
    run_batch(inserts, tree, opener)

    expected = create_batches(encode_content(inserts[0].content))
    creates = opener.of("POST", "/children")
    assert len(creates) == len(expected) > 1, "the nested content must actually split"
    assert [len(c["body"]["children"]) for c in creates] == [
        len(positions) for _parent, positions in expected
    ]


def test_ac5_a_group_wider_than_the_engines_limit_is_split_by_that_limit():
    p = projection(("p1", "one"))
    added = "\n\n".join(f"added {i}" for i in range(MAX_CHILDREN_PER_CALL + 10))
    requests = compiled(p, edited(("p1", f"one\n\n{added}")))
    inserts = [r for r in requests if isinstance(r, InsertRequest)]

    assert [len(r.content) for r in inserts] == [10, MAX_CHILDREN_PER_CALL]
    assert all(r.reference.block_id == "p1" for r in inserts)
    # bottom-up again: the LAST chunk is issued first, so the chunk issued after it lands
    # above it at the same plan-time index.
    assert inserts[0].content[0].text == f"added {MAX_CHILDREN_PER_CALL}"
    assert inserts[1].content[0].text == "added 0"


def test_ac5_the_limit_is_the_engines_constant_not_a_number_of_our_own():
    import inspect

    import larkdocio.write.compiler as module

    source = inspect.getsource(module)
    assert "MAX_CHILDREN_PER_CALL" in source
    assert str(MAX_CHILDREN_PER_CALL) not in source


# --------------------------------------------------------------------------- #
# AC6a — NO COMPILED *INSERT* BODY CARRIES A MARKER.                            #
# --------------------------------------------------------------------------- #

def carries_marker(text, block_ids):
    """Whether ``text`` holds a line that is a marker for one of ``block_ids`` — the
    marker-SET-aware question, asked with LD-230's own strip."""
    return strip_block_id_markers(text, block_ids) != text


def payload_texts(request):
    """Every string the apply path would actually send for an insert — read off the
    payloads the shipped ``encode_content`` builds, not re-derived here."""
    out = []
    for child in encode_content(request.content):
        out.append(json.dumps(child.payload, ensure_ascii=False))
        out.extend(child.cell_texts)
    return out


def test_ac6a_no_encoded_insert_payload_in_the_corpus_carries_a_marker():
    seen = 0
    for name, p, requests in corpus_batches():
        for request in requests:
            if not isinstance(request, InsertRequest):
                continue
            seen += 1
            for text in payload_texts(request):
                assert not carries_marker(text, p.block_ids), f"{name}: {text}"
    assert seen, "the corpus contributed no insert to scan"


def test_ac6a_the_shipped_barrier_is_what_refuses_marker_bearing_markdown():
    """Pinned, not assumed (LD-197 leg 3, offline): raw HTML is not in the dialect, so a
    marker written literally never reaches an insert body at all."""
    from larkdocio.write.compose import compose

    with pytest.raises(RefusedError) as excinfo:
        compose("<!-- lark:block:p1 -->")
    assert excinfo.value.refusal.reason is RefusalReason.NOT_IN_DIALECT


def test_ac6a_an_escaped_marker_for_a_block_this_document_never_emitted_survives():
    """The other half of LD-230's AC8: marker-SHAPED prose naming no emitted block is
    content, and an insert that carries it must still create it."""
    p = projection(("p1", "one"))
    requests = compiled(
        p, edited(("p1", "one\n\n<!\\-- lark:block:doxcnNotInThisDoc -->")),
    )
    inserts = [r for r in requests if isinstance(r, InsertRequest)]
    assert len(inserts) == 1
    payload = json.dumps(encode_content(inserts[0].content)[0].payload)
    assert "lark:block:doxcnNotInThisDoc" in payload
    assert not carries_marker(payload, p.block_ids)


# --------------------------------------------------------------------------- #
# AC6b — NO COMPILED *EDIT* REPLACEMENT CARRIES A MARKER — THE REAL ONE.        #
# --------------------------------------------------------------------------- #

def test_ac6b_no_compiled_edit_replacement_in_the_corpus_carries_a_marker():
    seen = 0
    for name, p, requests in corpus_batches():
        for request in requests:
            if not isinstance(request, EditRequest):
                continue
            seen += 1
            assert not carries_marker(request.replacement, p.block_ids), name
    assert seen, "the corpus contributed no edit to scan"


def test_ac6b_marker_shaped_content_in_a_blocks_own_text_survives_the_edit():
    """The adversarial input. The block's text legitimately contains marker-shaped content
    naming no emitted block; the edit must carry it through **verbatim** (LD-230 AC8) while
    never emitting a marker."""
    p = projection(("p1", "See <!\\-- lark:block:doxcnNotInThisDoc --> for details."))
    requests = compiled(
        p, edited(("p1", "See <!\\-- lark:block:doxcnNotInThisDoc --> for the details.")),
    )
    assert len(requests) == 1
    replacement = requests[0].replacement
    assert replacement == "See <!-- lark:block:doxcnNotInThisDoc --> for the details."
    assert not carries_marker(replacement, p.block_ids)


def test_ac6b_an_escaped_marker_for_an_EMITTED_block_refuses_rather_than_being_written():
    """The one route in, and the strip is the only thing that closes it: an EditRequest's
    replacement is a plain string nobody parses, and Lark stores marker-shaped text
    verbatim (LD-197 leg 3, live). The escaped form decodes back into a real marker, so it
    is refused — never written, and never quietly deleted either."""
    p = projection(("p1", "one"), ("p2", "two"))
    plan = reconcile(p, edited(("p1", "one"), ("p2", "two edited\n<!\\-- lark:block:p1 -->")))
    assert plan.ok, [r.detail for r in plan.refusals]
    with pytest.raises(RefusedError) as excinfo:
        compile_reconciliation(plan, p)
    assert excinfo.value.refusal.reason is RefusalReason.NOT_IN_DIALECT
    assert "identity marker" in excinfo.value.refusal.detail


def test_ac6b_the_marker_check_is_the_marker_set_aware_one_and_not_a_second_rule():
    import inspect

    import larkdocio.write.compiler as module

    source = inspect.getsource(module)
    assert "find_emitted_block_id_marker" in source, (
        "the set-aware question is the projection module's, not a second rule here")
    assert "lark:block" not in source, "a second marker pattern is a second definition"


# --------------------------------------------------------------------------- #
# LD-239 — THE GUARD IS POSITION-INDEPENDENT, and still marker-SET-aware.       #
#                                                                               #
# AC6b's own test puts the marker on a line of its own, which is exactly the    #
# shape the line-anchored matcher caught; a canonical marker for an EMITTED     #
# block sitting anywhere else rode the compiled body verbatim. The fix is a     #
# detection change (refuse anywhere), and the fence — a marker-SHAPED string    #
# naming an id this projection never emitted is content — is what keeps it safe.#
# --------------------------------------------------------------------------- #

#: Every place one marker can sit in a body. ``{m}`` is the marker.
MARKER_POSITIONS = (
    ("own line", "{m}"),
    ("mid-line", "see {m} above"),
    ("line start, trailing text", "{m} and the prose that follows it"),
    ("line end, after text", "the prose that precedes it {m}"),
    ("adjacent to text, no separating space", "before{m}after"),
    ("twice in one line", "{m} and again {m}"),
)

#: Both marker forms: the plain one and LD-231's ``opaque=`` variant.
MARKER_VARIANTS = (("plain", None), ("opaque", "image"))


def marker_shapes(block_id):
    """``(name, text)`` for every position × variant of a marker naming ``block_id``."""
    for position, template in MARKER_POSITIONS:
        for variant, kind in MARKER_VARIANTS:
            yield (
                f"{position} / {variant}",
                template.format(m=block_id_marker(block_id, kind)),
            )


def guard(text, known=("p1",)):
    """The shipped compile guard itself, called the way the compiler calls it."""
    import larkdocio.write.compiler as module

    return module._marker_guarded_text(text, known, "block 'p2'")


def as_projected(text):
    """``text`` escaped the way the projection escapes a block's literal content — the
    second domain the guard has to read, because an escaped marker decodes back into a
    real one on its way through the dialect."""
    escaped = _escape_literals(text)
    assert unescape_literals(escaped) == text, "the fixture must be a real escaped form"
    return escaped


def test_ld239_ac1_an_emitted_marker_at_every_position_refuses():
    for name, text in marker_shapes("p1"):
        with pytest.raises(RefusedError) as excinfo:
            guard(text)
        assert excinfo.value.refusal.reason is RefusalReason.NOT_IN_DIALECT, name
        assert "identity marker" in excinfo.value.refusal.detail, name


def test_ld239_ac1_an_emitted_marker_on_a_LATER_line_of_the_body_refuses():
    with pytest.raises(RefusedError):
        guard(f"a first line\nsee {block_id_marker('p1')} above\na third line")


def test_ld239_ac2_a_lookalike_at_every_position_survives_the_guard_verbatim():
    """The non-negotiable half (LD-230 AC8): marker-SHAPED prose naming an id this
    projection never emitted is the document's own content, at every position."""
    for name, text in marker_shapes("doxcnNotInThisDoc"):
        assert guard(text) == text, name


def test_ld239_ac1_ac3_every_position_refuses_end_to_end_and_compiles_NOTHING():
    """The decoded domain, driven through the shipped reconcile → compile chain: the
    projection escapes literal text, so this is the route a marker actually travels."""
    for name, text in marker_shapes("p1"):
        p = projection(("p1", "one"), ("p2", "two"))
        plan = reconcile(p, edited(("p1", "one"), ("p2", as_projected(text))))
        assert plan.ok, f"{name}: {[r.detail for r in plan.refusals]}"
        with pytest.raises(RefusedError) as excinfo:
            compile_reconciliation(plan, p)
        assert excinfo.value.refusal.reason is RefusalReason.NOT_IN_DIALECT, name


def test_ld239_ac1_the_RAW_form_compiles_NOTHING_at_any_position_either():
    """The raw domain, measured rather than assumed: a marker written unescaped is answered
    **earlier**, by whichever barrier sees it first — a second occurrence of a marker line
    (``marker-duplicated``), a marker-shaped line that is not byte-exact
    (``marker-mangled``), or raw HTML mid-sentence, which is not in the creatable dialect.
    Either way the round ends in a typed refusal with nothing compiled, which is why the
    ESCAPED form above — the one an editor hands back for prose the projection escaped — is
    the route that reached a body."""
    answered_by = {
        RefusalReason.MARKER_DUPLICATED,
        RefusalReason.MARKER_MANGLED,
        RefusalReason.NOT_IN_DIALECT,
    }
    for name, text in marker_shapes("p1"):
        p = projection(("p1", "one"), ("p2", "two"))
        plan = reconcile(p, edited(("p1", "one"), ("p2", f"two edited\n{text}")))
        with pytest.raises(RefusedError) as excinfo:
            compile_reconciliation(plan, p)
        assert excinfo.value.refusal.reason in answered_by, (name, excinfo.value.refusal)


def test_ld239_ac2_a_lookalike_at_every_position_reaches_the_compiled_body_verbatim():
    for name, text in marker_shapes("doxcnNotInThisDoc"):
        p = projection(("p1", "one"), ("p2", "two"))
        requests = compiled(p, edited(("p1", "one"), ("p2", as_projected(text))))
        assert len(requests) == 1, name
        assert requests[0].replacement == text, name


def test_ld239_ac3_text_that_cannot_be_decoded_is_read_as_not_a_marker():
    """Unchanged from today: a body the escape policy never produced is content, not an
    error — but a RAW marker in that same body is still caught."""
    undecodable = "a backslash the policy never emits: \\z"
    assert guard(undecodable) == undecodable
    with pytest.raises(RefusedError):
        guard(f"see {block_id_marker('p1')} above, and \\z")


def test_ld239_ac4_a_mid_line_marker_in_a_NESTED_CHILD_block_refuses():
    p = projection(("p1", "one"))
    child = as_projected(f"child: see {block_id_marker('p1')} inside")
    plan = reconcile(p, edited(("p1", f"one\n\n- parent\n  - {child}")))
    assert plan.ok, [r.detail for r in plan.refusals]
    with pytest.raises(RefusedError):
        compile_reconciliation(plan, p)


def test_ld239_ac4_a_mid_line_marker_in_a_TABLE_CELL_refuses():
    p = projection(("p1", "one"))
    cell = as_projected(f"see {block_id_marker('p1')} inside")
    table = f"| h1 | h2 |\n| --- | --- |\n| {cell} | c |"
    plan = reconcile(p, edited(("p1", f"one\n\n{table}")))
    assert plan.ok, [r.detail for r in plan.refusals]
    with pytest.raises(RefusedError):
        compile_reconciliation(plan, p)


def test_ld239_ac5_both_matchers_are_built_from_ONE_definition_of_the_marker():
    from larkdocio.model.renderer import BLOCK_ID_MARKER_LINE_RE, BLOCK_ID_MARKER_RE

    assert BLOCK_ID_MARKER_RE.pattern in BLOCK_ID_MARKER_LINE_RE.pattern, (
        "the line matcher must be the position-independent one plus its line anchors — a "
        "second spelling of the marker bytes is a second definition")
    for block_id, kind in (("p1", None), ("p1", "image")):
        marker = block_id_marker(block_id, kind)
        line = BLOCK_ID_MARKER_LINE_RE.match(marker)
        anywhere = BLOCK_ID_MARKER_RE.search(f"see {marker} above")
        assert line and anywhere, (block_id, kind)
        assert line.groups() == anywhere.groups() == (block_id, kind)


def test_ld239_ac5_the_set_aware_question_lives_beside_the_reader_side_strip():
    from larkdocio.model import projection as module

    assert module.find_emitted_block_id_marker(
        f"see {block_id_marker('p1')} above", ("p1",)) == "p1"
    assert module.find_emitted_block_id_marker(
        f"see {block_id_marker('p1')} above", ("p2",)) is None
    # The reader side keeps its LINE semantics — widening it would delete prose.
    text = f"see {block_id_marker('p1')} above\n"
    assert strip_block_id_markers(text, ("p1",)) == text


def test_ld239_ac6_the_refusal_detail_stops_saying_line_and_names_the_block():
    with pytest.raises(RefusedError) as excinfo:
        guard(f"see {block_id_marker('p1')} above")
    detail = excinfo.value.refusal.detail
    assert "'p1'" in detail, detail
    assert "anywhere" in detail, detail
    assert "marker line" not in detail and "a line that is" not in detail, detail


def test_ld239_ac8_the_compiler_contract_describes_a_position_independent_refusal():
    contract = RECONCILIATION_COMPILER_CONTRACT
    assert "anywhere in the text" in contract, contract
    assert "strip" not in contract, (
        "nothing is stripped on the edit path — a contract that still says so is false")


@private_tree.internal_log
def test_ld239_ac7_the_shipped_claim_is_corrected_in_all_four_copies():
    """AC7: the falsified wording is gone and the corrected one is in place, in every copy of
    either release document that carries the section it was written in.

    **LD-540 — the window, and why this is asserted over a DERIVED set of copies.** The wheel
    now carries a recent-N window of each release document while the repository keeps the whole
    history, so "this claim is written down" and "this claim ships" stopped being one sentence.
    ``test_shipped_notes.notes_claim_copies`` answers which copies must carry it: the root
    always (a deletion from the authoring source reddens with full force), and the packaged
    window whenever it still holds the section — and if it does not, that helper PROVES the
    section is genuinely out of window rather than letting the claim go missing. Nothing was
    weakened and no copy was dropped by hand.

    The **negative** half — the falsified wording appears NOWHERE — stays unconditional across all
    four files, because "this sentence must not exist" is not a claim a window can excuse.
    """
    from test_shipped_notes import notes_claim_copies

    root = Path(__file__).resolve().parent.parent
    for rel in ("RELEASE_NOTES.md", "CHANGELOG.md", "src/larkdocio/RELEASE_NOTES.md",
                "src/larkdocio/CHANGELOG.md"):
        assert "a **line** that is a marker" not in (root / rel).read_text(encoding="utf-8"), rel
    for name in ("RELEASE_NOTES.md", "CHANGELOG.md"):
        for label, text in notes_claim_copies(name, "anywhere in the text"):
            assert "anywhere in the text" in text, label


def test_ld239_ac9_the_filed_input_refuses_end_to_end_and_reaches_no_wire():
    """The filed input, pinned: an adversarial pass drove `see <!-- lark:block:p1 --> above`
    with p1 emitted to `applied` and observed it in the wire body. It travels as the editor
    hands it back — **escaped**, the way the projection wrote the prose it came from — and
    decodes into that exact body on the way through the dialect."""
    tree = doc_tree()
    p = project_block_ids(tree)
    leaking = f"see {block_id_marker('p1')} above"
    opener = RoutingOpener(blocks=live(tree), document_revisions=["rev-1"])

    plan = reconcile(p, p.markdown.replace("\none\n", f"\n{as_projected(leaking)}\n"))
    assert plan.ok, [r.detail for r in plan.refusals]
    with pytest.raises(RefusedError) as excinfo:
        run_batch(compile_reconciliation(plan, p), tree, opener, revision="rev-1")

    assert excinfo.value.refusal.reason is RefusalReason.NOT_IN_DIALECT
    assert opener.calls == [], opener.calls
    assert opener.writes == [], opener.writes
    wire = json.dumps(opener.calls, ensure_ascii=False)
    assert leaking not in wire and "update_text_elements" not in wire


# --------------------------------------------------------------------------- #
# AC7 — surgical writes: one edited block of many issues ONE request.          #
# --------------------------------------------------------------------------- #

def test_ac7_editing_one_block_of_many_issues_one_request_for_that_block_only():
    tree = doc_tree()
    p = project_block_ids(tree)
    requests = compiled(p, p.markdown.replace("\nthree\n", "\nthree edited\n"))

    assert len(requests) == 1
    assert isinstance(requests[0], EditRequest)
    assert requests[0].anchor.block_id == "p3"

    opener = RoutingOpener(blocks=live(tree))
    _preview, log = run_batch(requests, tree, opener)

    patched = {c["path"].rsplit("/blocks/", 1)[-1].split("?")[0] for c in opener.writes}
    assert patched == {"p3"}, "every other block must be untouched IN LARK, not rewritten"
    assert [e.block_id for e in log.entries] == ["p3"]


def test_ac7_an_unedited_projection_compiles_to_an_empty_batch_and_writes_nothing():
    tree = doc_tree()
    p = project_block_ids(tree)
    requests = compiled(p, p.markdown)

    assert requests == ()
    opener = RoutingOpener(blocks=live(tree))
    _preview, log = run_batch(requests, tree, opener)
    assert log.entries == ()
    assert opener.calls == [], "a no-op reconciliation touches nothing at all"


def test_ac7_a_conserved_opaque_block_compiles_to_nothing():
    p = projection(("p1", "one"), ("img", "![](tok)"), opaque=("img",))
    requests = compiled(p, edited(("p1", "one edited"), ("img", "![](tok) changed")))
    assert [type(r) for r in requests] == [EditRequest]
    assert requests[0].anchor.block_id == "p1"


# --------------------------------------------------------------------------- #
# AC9 — the front door: registered, reachable, and adding no endpoint.         #
# --------------------------------------------------------------------------- #

def test_ac9_the_compiler_is_exported_from_the_write_package():
    assert _compile_from_package is compile_reconciliation


def test_ac9_the_compiler_is_registered_on_the_docx_write_surface():
    """Registered on the surface's existing ``reconciliation`` answer rather than as a
    seventh operation: compiling reaches for the request families ``operations`` already
    lists, which is exactly what ``compiles_to`` names."""
    from larkdocio import capabilities

    surface = capabilities(full=True)["surfaces"]["docx-write"]
    registered = surface["reconciliation"]
    assert registered["compiler_entry_point"] == "larkdocio.write.compiler"
    assert registered["compiler_contract"] == RECONCILIATION_COMPILER_CONTRACT
    assert registered["compiles_to"] == [f.__name__ for f in COMPILED_REQUEST_FAMILIES]
    assert "compile_reconciliation" not in {op["name"] for op in surface["operations"]}


def test_ac9_every_compiled_family_is_a_request_family_the_surface_already_lists():
    """Bidirectional in the direction that matters: the compiler cannot claim a family the
    surface does not ship."""
    from larkdocio import capabilities

    surface = capabilities(full=True)["surfaces"]["docx-write"]
    listed = json.dumps(surface["operations"])
    for name in surface["reconciliation"]["compiles_to"]:
        assert name in listed, name


def test_ac9_the_compiler_introduces_no_endpoint_and_so_no_permission_row():
    """The permissions registry is bidirectional (an unnecessary row reddens too), so the
    honest statement is that this module calls nothing: it holds no URL and no client."""
    import inspect

    import larkdocio.write.compiler as module

    source = inspect.getsource(module)
    assert "open-apis" not in source
    assert "http" not in source.replace("https://", "")


def test_ac9_every_refusal_the_compiler_mints_is_already_in_the_registry():
    """Derived from the module's own source: a compile-time refusal whose reason is not one
    a reconciliation can answer with would mean two vocabularies for one round."""
    import ast
    import inspect

    import larkdocio.write.compiler as module
    from larkdocio.write.model import Refusal
    from larkdocio.write.reconcile import RECONCILIATION_REFUSAL_REASONS

    tree = ast.parse(inspect.getsource(module))
    minted = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "Refusal"
    }
    assert minted, "the AST scan found no refusal factories — the guard would be vacuous"
    for factory in sorted(minted):
        assert getattr(Refusal, factory)("probe").reason in RECONCILIATION_REFUSAL_REASONS


def test_ac1_content_added_ahead_of_the_first_marker_anchors_before_the_first_block():
    """The head segment carries no identifier of its own, so the only honest anchor is the
    first block the projection emitted — never another inserted block."""
    p = projection((None, "# Title"), ("p1", "one"))
    requests = compiled(p, edited((None, "# Title\n\nadded at the top"), ("p1", "one")))
    assert [type(r) for r in requests] == [InsertRequest]
    assert requests[0].reference == AnchorById(block_id="p1")
    assert requests[0].position is InsertPosition.BEFORE
    assert requests[0].content[0].text == "added at the top"


# --------------------------------------------------------------------------- #
# LD-240 — escape-only normalization compiles to NOTHING, and the real edit     #
# beside it compiles to exactly one request (the blast-radius half, in the      #
# currency the wire actually speaks).                                           #
# --------------------------------------------------------------------------- #

def test_ld240_a_normalized_block_compiles_to_nothing_and_its_neighbour_to_one_edit():
    p = projection(
        ("b1", "intro line\n\\- second line bullet"),
        ("b2", "untouched neighbour"),
        ("b3", "third block"),
    )

    requests = compiled(p, edited(
        ("b1", "intro line\n- second line bullet"),      # ONLY unescape_literals
        ("b2", "untouched neighbour"),
        ("b3", "third block, genuinely edited"),
    ))

    assert [type(r) for r in requests] == [EditRequest]
    assert requests[0].anchor.block_id == "b3"
    assert requests[0].replacement == "third block, genuinely edited"
