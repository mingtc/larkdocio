"""LD-235 — the reconciliation REFUSAL SET.

The loss taxonomy the marker-preservation probe produced is adopted **verbatim** as the
library's typed refusal vocabulary: every way a marker round-trip can go wrong is a row,
every row has a typed reason with a ``detail`` that names a recovery which **actually
works**, and every row has a test here. Two rows are deliberately **not** refusals — content
appended into a segment is the *insert path*, and a marker on the write path is an
*invariant assertion* over compiled requests — and their tests assert exactly that, so a
test-per-row count is not a refusal-per-row count.

Offline, every test: the reconciler makes zero API calls and this module re-proves it over
every refusing input it builds.

**The amplifier** is ``tests/fixtures/reconcile/leg2-classifier-selfcheck.json`` — the
committed classifier self-check, **9 synthetic mutations whose verdict is known by
construction** — copied here deliberately (the suite never imports the probe code under
``dev/``). Each mutation is rebuilt from the committed ``S`` source projection and the
reconciler's answer is checked against the corpus's own recorded verdict, including the
clean edit that must **NOT** be reported as a loss.
"""
from domain_vocabulary import RETIRED_ID
import json
import re
import socket
import urllib.request
from pathlib import Path

import pytest

from larkdocio.model.projection import (
    BlockIdProjection,
    strip_block_id_markers,
)
from larkdocio.model.renderer import BLOCK_ID_MARKER_LINE_RE, block_id_marker
from larkdocio.write import compile_reconciliation
from larkdocio.write.model import RefusalReason, RefusedError
from larkdocio.write.reconcile import (
    RECONCILIATION_REFUSAL_REASONS,
    AbsentBlockDisposition,
    ReconciliationState,
    reconcile,
)

FIXTURES = Path(__file__).parent / "fixtures" / "reconcile"

DELETE = AbsentBlockDisposition.DELETE


# --------------------------------------------------------------------------- #
# Helpers — hand-built projections, and the committed corpora.                 #
# --------------------------------------------------------------------------- #

def projection(*blocks, opaque=(), kinds=None):
    kinds = kinds or {}
    parts = []
    ids = []
    for block_id, markdown in blocks:
        if block_id is None:
            parts.append(markdown)
            continue
        ids.append(block_id)
        parts.append(f"{block_id_marker(block_id, kinds.get(block_id))}\n{markdown}")
    return BlockIdProjection(
        markdown="\n\n".join(parts) + "\n",
        block_ids=tuple(ids),
        opaque_block_ids=tuple(opaque),
    )


def edited(*blocks, kinds=None):
    return projection(*blocks, kinds=kinds).markdown


def reasons(plan):
    return [r.reason for r in plan.refusals]


def details(plan):
    return [r.detail for r in plan.refusals]


def source_projection(name):
    src = json.loads((FIXTURES / "leg2-sources.json").read_text(encoding="utf-8"))[name]
    return BlockIdProjection(
        markdown=src["markdown"],
        block_ids=tuple(src["block_ids"]),
        opaque_block_ids=tuple(src["opaque_block_ids"]),
    )


def selfcheck():
    """The committed 9-mutation classifier self-check — the amplifier, verdicts known by
    construction."""
    return json.loads(
        (FIXTURES / "leg2-classifier-selfcheck.json").read_text(encoding="utf-8")
    )


#: An opaque block's content, in the two opaque kinds ``compose()`` can actually CREATE.
#: Image and embed are opaque too, but a plan that duplicated one of them is caught later
#: at compile as not-in-dialect — that is luck, not a guard, so the proof runs on these.
TABLE = "| head | count |\n| --- | --- |\n| alpha | 1 |"
MERMAID = "```mermaid\ngraph TD;\n  A-->B;\n```"
CREATABLE_OPAQUE = {"table": TABLE, "mermaid": MERMAID}


def opaque_projection(content, kind):
    """A document whose middle block is opaque: paragraph, opaque block, paragraph."""
    return projection(
        ("p0", "one"), ("tb", content), ("p1", "two"),
        opaque=("tb",), kinds={"tb": kind},
    )


def marker_eaten(content):
    """What an editor leaves behind when it drops the opaque block's MARKER and keeps its
    CONTENT — the content then sits, unmarked, inside the preceding block's segment."""
    return edited(("p0", "one"), (None, content), ("p1", "two"))


# --------------------------------------------------------------------------- #
# AC1 — THE TAXONOMY IS THE REFUSAL SET: eleven rows, a test per row.          #
# --------------------------------------------------------------------------- #

#: The ELEVEN INHERITED rows of the loss taxonomy, adopted verbatim, each mapped to what
#: this module proves about it. ``None`` marks the two rows that are deliberately not
#: refusals. The rider about a mode appended by the cross-vendor arm is **N/A by the maintainer
#: ruling (2026-08-02)**: that arm never ran and the requirement was dropped, so it
#: contributes NO row here — the twelfth row below comes from an entirely different
#: source (a defect found in the plan itself) and must not be conflated with it.
INHERITED_ROWS = {
    "dropped": RefusalReason.MARKER_DROPPED,
    "content-absent": RefusalReason.MARKER_ABSENT,
    "duplicated": RefusalReason.MARKER_DUPLICATED,
    "relocated": RefusalReason.MARKER_RELOCATED,
    "invented": RefusalReason.MARKER_INVENTED,
    "mangled": RefusalReason.MARKER_MANGLED,
    "orphaned": RefusalReason.MARKER_ORPHANED,
    "content appended into a segment": None,   # the insert path
    "marker order changed": RefusalReason.MARKER_ORDER_CHANGED,
    "forged marker in content": RefusalReason.MARKER_INVENTED,
    "marker on the write path": None,          # an invariant over compiled requests
}

#: The ONE row that is not inherited: it was ruled in later, from a defect in the plan
#: itself — an opaque block whose marker an editor ate was reported conserved *and*
#: planned as an insert of its own content, so applying it would have held the block
#: twice. Its proof lives in this module's own AC9 section.
PM_RULED_ROWS = {
    "conserved block re-created": RefusalReason.CONSERVED_BLOCK_RE_CREATED,
}

#: Eleven inherited + one ruled in = twelve.
TAXONOMY_ROWS = {**INHERITED_ROWS, **PM_RULED_ROWS}


def test_ac1_the_taxonomy_has_eleven_inherited_rows_plus_one_ruled_in():
    """A test per row, checked mechanically rather than by counting bullets by eye — and
    the two provenances kept apart, because they are the thing easiest to conflate."""
    assert len(INHERITED_ROWS) == 11
    assert len(PM_RULED_ROWS) == 1
    assert len(TAXONOMY_ROWS) == 12
    source = Path(__file__).read_text(encoding="utf-8")
    for rows, prefix in ((INHERITED_ROWS, "ac1"), (PM_RULED_ROWS, "ac9")):
        for row in rows:
            slug = re.sub(r"[^a-z0-9]+", "_", row.lower()).strip("_")
            assert f"def test_{prefix}_row_{slug}" in source, row


def test_ac1_every_refusing_row_reason_is_in_the_registered_vocabulary():
    """A mode whose reason the registry does not carry is a mode a consumer cannot look
    up before hitting it."""
    for row, reason in TAXONOMY_ROWS.items():
        if reason is not None:
            assert reason in RECONCILIATION_REFUSAL_REASONS, row


def test_ac1_row_dropped():
    """Marker gone, block plainly still there: REFUSE naming the block and quoting its
    surviving text. Never infer deletion; never re-attach by content similarity."""
    p = projection(("p1", "one"), ("p2", "the paragraph whose marker was lost"))
    plan = reconcile(p, edited(("p1", "one\n\nthe paragraph whose marker was lost")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.MARKER_DROPPED]
    detail = plan.refusals[0].detail
    assert "p2" in detail
    assert "the paragraph whose marker was lost" in detail
    assert plan.entries == ()


def test_ac1_row_content_absent():
    """Marker and content both gone: REFUSE by default naming the block; delete ONLY
    under the explicit disposition."""
    p = projection(("p1", "one"), ("p2", "the paragraph nobody meant to lose"))
    gone = edited(("p1", "one"))
    plan = reconcile(p, gone)
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.MARKER_ABSENT]
    assert "p2" in plan.refusals[0].detail

    disposed = reconcile(p, gone, absent=DELETE)
    assert disposed.ok
    assert [(e.state, e.block_id) for e in disposed.changes] == [
        (ReconciliationState.DELETED, "p2")
    ]


def test_ac1_row_duplicated():
    """An id appearing more than once: REFUSE pre-I/O naming the id AND both
    occurrences. Never pick one."""
    p = projection(("p1", "one"), ("p2", "two"))
    plan = reconcile(p, edited(("p1", "one"), ("p2", "two"), ("p1", "one again")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.MARKER_DUPLICATED]
    detail = plan.refusals[0].detail
    assert "p1" in detail
    # both occurrences, by their line numbers in the Markdown that came back.
    numbers = [int(n) for n in re.findall(r"line (\d+)", detail)]
    assert len(numbers) == 2 and numbers[0] < numbers[1]
    assert plan.entries == ()


def test_ac1_row_relocated():
    """Marker now on other content: REFUSE naming BOTH blocks. An applied relocation
    rewrites two blocks with each other's text — the worst silent corruption there is."""
    p = projection(("p1", "the first paragraph"), ("p2", "the second paragraph"))
    plan = reconcile(
        p, edited(("p1", "the second paragraph"), ("p2", "the first paragraph"))
    )
    assert not plan.ok
    assert set(reasons(plan)) == {RefusalReason.MARKER_RELOCATED}
    joined = " ".join(details(plan))
    assert "p1" in joined and "p2" in joined
    assert plan.entries == ()


def test_ac1_row_invented():
    """An id never projected: REFUSE naming the id. This is the anti-forgery check."""
    p = projection(("p1", "one"))
    plan = reconcile(p, edited(("p1", "one"), ("doxcnNOTREAL", "smuggled")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.MARKER_INVENTED]
    assert "doxcnNOTREAL" in plan.refusals[0].detail


@pytest.mark.parametrize(
    "line",
    [
        "<!--lark:block:p1-->",                 # the self-check's own mangling
        "<!-- lark:block:p1-->",
        "<!--lark:block:p1 -->",
        "<!-- lark:block: p1 -->",
        "<!-- lark:block:p1 --> and then some prose",
    ],
)
def test_ac1_row_mangled(line):
    """Marker-shaped but not byte-exact: REFUSE quoting the mangled bytes and the
    canonical form. DO NOT NORMALIZE — a mangled marker may be forged content."""
    p = projection(("p1", "one"), ("p2", "two"))
    plan = reconcile(p, f"{line}\none\n\n{block_id_marker('p2')}\ntwo\n")
    assert not plan.ok
    assert RefusalReason.MARKER_MANGLED in reasons(plan)
    detail = next(
        r.detail for r in plan.refusals if r.reason is RefusalReason.MARKER_MANGLED
    )
    assert line in detail                       # the mangled bytes, quoted
    assert "<!-- lark:block:" in detail          # the canonical form, shown
    assert plan.entries == ()


def test_ac1_row_mangled_is_never_normalized_into_a_working_marker():
    """The refusal is the whole answer: nothing anywhere repairs the bytes into the
    marker they resemble, so no plan is ever built from a mangled line."""
    p = projection(("p1", "one"), ("p2", "two"))
    plan = reconcile(p, f"<!--lark:block:p1-->\none edited\n\n{block_id_marker('p2')}\ntwo\n")
    assert not plan.ok
    assert plan.entries == ()
    assert plan.change_count == 0


def test_ac1_row_orphaned():
    """Marker kept, content gone: REFUSE naming the block — an emptied block is a
    deletion expressed ambiguously."""
    p = projection(("p1", "one"), ("p2", "the paragraph that was emptied"))
    plan = reconcile(p, f"{block_id_marker('p1')}\none\n\n{block_id_marker('p2')}\n")
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.MARKER_ORPHANED]
    assert "p2" in plan.refusals[0].detail
    assert plan.entries == ()


def test_ac1_row_content_appended_into_a_segment():
    """NOT a failure — the insert path. Unmarked content following a surviving marker is
    planned as an insert anchored to that marker."""
    p = projection(("p1", "one"), ("p2", "two"))
    plan = reconcile(p, edited(("p1", "one\n\nbrand new paragraph"), ("p2", "two")))
    assert plan.ok, details(plan)
    assert plan.refusals == ()
    inserted = [e for e in plan.changes if e.state is ReconciliationState.INSERTED]
    assert [(e.after, e.anchor_block_id, e.anchor_position) for e in inserted] == [
        ("brand new paragraph", "p1", "after")
    ]


def test_ac1_row_marker_order_changed():
    """Projected-id order != document order, nothing lost: REFUSE naming why."""
    p = projection(("p1", "one"), ("p2", "two"))
    plan = reconcile(p, edited(("p2", "two"), ("p1", "one")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.MARKER_ORDER_CHANGED]
    assert plan.entries == ()


def test_ac1_row_forged_marker_in_content():
    """A marker-shaped id the projection never emitted refuses AS `invented` — and the
    strip stays marker-set-aware, so consumer content is not destroyed on the way in."""
    p = projection(("p1", "one"))
    plan = reconcile(p, edited(("p1", "one"), ("doxcnForged", "content under a forgery")))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.MARKER_INVENTED]

    # The strip is marker-set-aware: a marker-shaped line for an id this document never
    # emitted is CONTENT and survives; only an emitted one is stripped.
    text = f"{block_id_marker('p1')}\none\n{block_id_marker('doxcnForged')}\nmine\n"
    stripped = strip_block_id_markers(text, p.block_ids)
    assert block_id_marker("p1") not in stripped
    assert block_id_marker("doxcnForged") in stripped


def test_ac1_row_marker_on_the_write_path():
    """An invariant assertion over every compiled request, not a plan-time refusal: an
    edit body that would carry an identity marker for one of THIS document's blocks is
    refused at compile time, while marker-shaped prose naming no emitted block survives."""
    p = projection(("p1", "one"), ("p2", "two"))
    leaking = reconcile(
        p, edited(("p1", "one"), ("p2", "two edited\n<!\\-- lark:block:p1 -->"))
    )
    assert leaking.ok, details(leaking)
    with pytest.raises(RefusedError):
        compile_reconciliation(leaking, p)

    harmless = projection(("p1", "See <!\\-- lark:block:doxcnNotHere --> for details."))
    requests = compile_reconciliation(
        reconcile(
            harmless,
            edited(("p1", "See <!\\-- lark:block:doxcnNotHere --> for the details.")),
        ),
        harmless,
    )
    assert len(requests) == 1
    assert requests[0].replacement == (
        "See <!-- lark:block:doxcnNotHere --> for the details."
    )


# --------------------------------------------------------------------------- #
# AC2 — every detail names a recovery that ACTUALLY WORKS.                     #
# --------------------------------------------------------------------------- #

#: One refusing input per mode, with the recovery its ``detail`` names — expressed as the
#: Markdown that recovery produces. The test does not read the recovery out of the prose
#: and hope: it **performs** it and asserts the reconciliation then succeeds. That is the
#: whole point of the row — a detail advising something that can never succeed is the
#: failure mode that makes an agent loop.
def _recovery_cases():
    two = projection(("p1", "one"), ("p2", "two"))
    dropped_src = projection(("p1", "one"), ("p2", "the paragraph whose marker was lost"))
    emptied = projection(("p1", "one"), ("p2", "the paragraph that was emptied"))
    mangled_extra = projection(("p1", "one"))
    conserved = opaque_projection(TABLE, "table")
    return [
        # (name, projection, edited-that-refuses, expected reason, recovery markdown,
        #  a phrase the detail must contain)
        (
            "dropped",
            dropped_src,
            edited(("p1", "one\n\nthe paragraph whose marker was lost")),
            RefusalReason.MARKER_DROPPED,
            dropped_src.markdown,
            "marker",
        ),
        (
            "content-absent",
            two,
            edited(("p1", "one")),
            RefusalReason.MARKER_ABSENT,
            two.markdown,
            "marker",
        ),
        (
            "duplicated",
            two,
            edited(("p1", "one"), ("p2", "two"), ("p1", "one again")),
            RefusalReason.MARKER_DUPLICATED,
            two.markdown,
            "occurrence",
        ),
        (
            "relocated",
            two,
            edited(("p1", "two"), ("p2", "one")),
            RefusalReason.MARKER_RELOCATED,
            two.markdown,
            "own marker",
        ),
        (
            "invented",
            two,
            edited(("p1", "one"), ("p2", "two"), ("doxcnNOTREAL", "smuggled")),
            RefusalReason.MARKER_INVENTED,
            two.markdown,
            "Remove it",
        ),
        (
            "mangled",
            mangled_extra,
            "<!--lark:block:p1-->\none\n",
            RefusalReason.MARKER_MANGLED,
            mangled_extra.markdown,
            "canonical",
        ),
        (
            "orphaned",
            emptied,
            f"{block_id_marker('p1')}\none\n\n{block_id_marker('p2')}\n",
            RefusalReason.MARKER_ORPHANED,
            emptied.markdown,
            "text back",
        ),
        (
            "order-changed",
            two,
            edited(("p2", "two"), ("p1", "one")),
            RefusalReason.MARKER_ORDER_CHANGED,
            two.markdown,
            "order",
        ),
        (
            "block-type-mutation",
            two,
            edited(("p1", "# one"), ("p2", "two")),
            RefusalReason.BLOCK_TYPE_MUTATION,
            two.markdown,
            "delete",
        ),
        (
            "conserved-block-re-created",
            conserved,
            marker_eaten(TABLE),
            RefusalReason.CONSERVED_BLOCK_RE_CREATED,
            conserved.markdown,
            "marker line back",
        ),
    ]


RECOVERY_CASES = _recovery_cases()
RECOVERY_IDS = [c[0] for c in RECOVERY_CASES]


@pytest.mark.parametrize("case", RECOVERY_CASES, ids=RECOVERY_IDS)
def test_ac2_the_recovery_each_detail_names_actually_works(case):
    name, p, bad, reason, recovered, phrase = case
    plan = reconcile(p, bad)
    assert not plan.ok, name
    assert reason in reasons(plan), name

    detail = next(r.detail for r in plan.refusals if r.reason is reason)
    assert phrase.lower() in detail.lower(), (name, detail)

    # PERFORM the recovery the detail names. It must actually succeed.
    after = reconcile(p, recovered)
    assert after.ok, (name, details(after))


#: The identifier each refusal must NAME — the block, the forged id, or the mangled bytes.
#: A refusal that does not name what it is about is one a consumer cannot act on.
SUBJECTS = {
    "dropped": "p2",
    "content-absent": "p2",
    "duplicated": "p1",
    "relocated": "p2",
    "invented": "doxcnNOTREAL",
    "mangled": "<!--lark:block:p1-->",
    "orphaned": "p2",
    "order-changed": "p2",
    "block-type-mutation": "p1",
    "conserved-block-re-created": "tb",
}


@pytest.mark.parametrize("case", RECOVERY_CASES, ids=RECOVERY_IDS)
def test_ac2_every_detail_names_the_thing_it_is_about_and_a_next_action(case):
    name, p, bad, reason, _recovered, _phrase = case
    detail = next(
        r.detail for r in reconcile(p, bad).refusals if r.reason is reason
    )
    assert detail.strip()
    assert detail == detail.strip()
    # a concrete next action, in the imperative — not a diagnosis and a shrug.
    assert re.search(
        r"\b(remove|restore|put|keep|make|re-run|edit|delete|insert|replace)\b",
        detail,
        re.IGNORECASE,
    ), (name, detail)
    # the identifier the refusal is about.
    assert SUBJECTS[name] in detail, (name, detail)


@pytest.mark.parametrize("case", RECOVERY_CASES, ids=RECOVERY_IDS)
def test_ac2_no_detail_advises_an_action_the_situation_makes_impossible(case):
    """The explicit lesson: a detail that offers the deletion disposition as a step that
    suffices, where it does not, sends an agent into a loop. So wherever a detail offers
    it, it is offered together with what it actually needs — and where the disposition
    alone genuinely resolves the refusal, it is offered plainly."""
    name, p, bad, reason, _recovered, _phrase = case
    detail = next(
        r.detail for r in reconcile(p, bad).refusals if r.reason is reason
    )
    if "deletion disposition" not in detail:
        return
    if reconcile(p, bad, absent=DELETE).ok:
        return
    # It does not suffice on its own, so the detail must say what must accompany it.
    assert "remove" in detail.lower(), (name, detail)


@pytest.mark.parametrize("case", RECOVERY_CASES, ids=RECOVERY_IDS)
def test_ac2_no_detail_advises_guessing_repairing_or_re_attaching(case):
    """The taxonomy forbids exactly three repairs — normalizing a mangled marker,
    re-attaching a dropped one by content similarity, and picking one of two duplicate
    occurrences. No detail may send a consumer down any of them."""
    name, p, bad, reason, _recovered, _phrase = case
    detail = next(
        r.detail for r in reconcile(p, bad).refusals if r.reason is reason
    ).lower()
    for forbidden in ("normali", "closest match", "best match", "most similar", "pick one"):
        assert forbidden not in detail, (name, forbidden)


# --------------------------------------------------------------------------- #
# AC3 — refusals are pre-I/O wherever the information already is.              #
# --------------------------------------------------------------------------- #

def test_ac3_every_plan_time_refusal_makes_zero_api_calls(monkeypatch):
    """The call-count spy, over every refusing input this module builds, under BOTH
    dispositions. Everything knowable from the plan refuses before a single write."""
    calls = []
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *a, **k: calls.append("urlopen") or (_ for _ in ()).throw(AssertionError),
    )
    monkeypatch.setattr(
        socket.socket, "connect",
        lambda *a, **k: calls.append("connect") or (_ for _ in ()).throw(AssertionError),
    )
    for name, p, bad, reason, _recovered, _phrase in RECOVERY_CASES:
        for disposition in (AbsentBlockDisposition.REFUSE, DELETE):
            reconcile(p, bad, absent=disposition)
    for case in selfcheck()["cases"]:
        reconcile(source_projection("S"), mutation(case))
    assert calls == []


@pytest.mark.parametrize("case", RECOVERY_CASES, ids=RECOVERY_IDS)
def test_ac3_a_refusing_reconciliation_compiles_to_nothing_at_all(case):
    """Pre-I/O is structural, not a promise: a refusing plan has no entries and the
    compiler refuses it rather than emitting a partial batch."""
    name, p, bad, _reason, _recovered, _phrase = case
    plan = reconcile(p, bad)
    assert plan.entries == (), name
    assert plan.change_count == 0, name
    with pytest.raises(RefusedError):
        compile_reconciliation(plan, p)


# --------------------------------------------------------------------------- #
# AC4 — THE SYNTHETIC MUTATION CORPUS IS THE AMPLIFIER (offline).              #
# --------------------------------------------------------------------------- #

def split_source(p):
    """``(head, [(marker_line, text), …])`` for a projection, from its own markdown."""
    head = []
    items = []
    for line in p.markdown.split("\n"):
        if BLOCK_ID_MARKER_LINE_RE.match(line):
            items.append([line, []])
        elif items:
            items[-1][1].append(line)
        else:
            head.append(line)
    return (
        "\n".join(head).strip("\n"),
        [(marker, "\n".join(body).strip("\n")) for marker, body in items],
    )


def assemble(head, items):
    parts = [head] if head.strip() else []
    for marker_line, text in items:
        chunk = "\n".join(x for x in (marker_line, text) if x)
        if chunk.strip():
            parts.append(chunk)
    return "\n\n".join(parts) + "\n"


def _index(items, block_id):
    needle = block_id_marker(block_id)
    return next(i for i, (marker, _) in enumerate(items) if marker == needle)


def mutation(case):
    """Rebuild one of the self-check's 9 synthetic mutations from the committed ``S``
    source. Each is a single, deliberate edit whose verdict is known **by
    construction** — which is what makes the corpus an amplifier rather than a second
    opinion."""
    head, items = split_source(source_projection("S"))
    if case == "clean-edit":
        i = _index(items, "s03")
        items[i] = (items[i][0], "The rollout is staged: early consumers, then the rest.")
    elif case == "dropped":
        i = _index(items, "s03")
        items[i] = (None, items[i][1])
    elif case == "dropped-after-rewrite-is-AMBIGUOUS":
        i = _index(items, "s03")
        items[i] = (None, "Staging: the internal set goes first and the wider set follows.")
    elif case == "content-absent":
        del items[_index(items, "s06")]
    elif case == "duplicated":
        i = _index(items, "s03")
        items.insert(i + 1, items[i])
    elif case == "relocated":
        a, b = _index(items, "s02"), _index(items, "s03")
        items[a], items[b] = (items[a][0], items[b][1]), (items[b][0], items[a][1])
    elif case == "invented":
        i = _index(items, "s07")
        items[i] = (items[i][0], "")
        items.insert(i + 1, (block_id_marker("s99"), "## Status"))
    elif case == "mangled":
        i = _index(items, "s05")
        items[i] = ("<!--lark:block:s05-->", items[i][1])
    elif case == "orphaned":
        i = _index(items, "s03")
        items[i] = (items[i][0], "")
    else:  # pragma: no cover - the corpus is closed
        raise AssertionError(f"unknown self-check case {case!r}")
    return assemble(head, items)


#: The corpus records its verdict per marker; this is the taxonomy row each verdict word
#: names. Derived from the corpus, so a mutation that stopped refusing reddens here.
VERDICT_REASONS = {
    "dropped": RefusalReason.MARKER_DROPPED,
    "content-absent": RefusalReason.MARKER_ABSENT,
    "duplicated": RefusalReason.MARKER_DUPLICATED,
    "relocated": RefusalReason.MARKER_RELOCATED,
    "orphaned": RefusalReason.MARKER_ORPHANED,
    "mangled": RefusalReason.MARKER_MANGLED,
}

#: The one case where identity short-circuits the rest: an invented marker stops the
#: reconciliation before any per-segment work, so the corpus's *second* recorded loss for
#: that mutation (the block the forged marker orphaned) is not reached. The refusal set is
#: still a subset of what the corpus recorded — never a mode the corpus did not.
IDENTITY_SHORT_CIRCUIT = {"invented"}


def corpus_reasons(record):
    out = {VERDICT_REASONS[v] for v in record["per_marker"].values() if v != "preserved"}
    if record["invented"]:
        out.add(RefusalReason.MARKER_INVENTED)
    if record["mangled"]:
        out.add(RefusalReason.MARKER_MANGLED)
    return out


def test_ac4_the_corpus_is_the_committed_nine_synthetic_mutations():
    corpus = selfcheck()
    assert corpus["all_pass"] is True
    assert len(corpus["cases"]) == 9
    assert set(corpus["cases"]) == {
        "clean-edit",
        "dropped",
        "dropped-after-rewrite-is-AMBIGUOUS",
        "content-absent",
        "duplicated",
        "relocated",
        "invented",
        "mangled",
        "orphaned",
    }


@pytest.mark.parametrize("case", sorted(selfcheck()["cases"]))
def test_ac4_each_synthetic_mutation_refuses_with_the_verdict_it_was_built_to_have(case):
    record = selfcheck()["cases"][case]
    plan = reconcile(source_projection("S"), mutation(case))
    expected = corpus_reasons(record)

    if not expected:                    # the clean edit — see its own test below.
        assert plan.ok, details(plan)
        return

    got = set(reasons(plan))
    assert got, f"{case}: a mutation the corpus records as a loss did not refuse"
    assert got <= expected, f"{case}: refused with a mode the corpus never recorded"
    if case not in IDENTITY_SHORT_CIRCUIT:
        assert got == expected, case
        # the refusal names the marker the corpus flagged.
        joined = " ".join(details(plan))
        for marker_id, verdict in record["per_marker"].items():
            if verdict != "preserved":
                assert marker_id in joined, (case, marker_id)
    assert plan.entries == ()


def test_ac4_the_clean_edit_case_must_NOT_be_reported_as_a_loss():
    """The guard on the guard. An over-eager loss detector is the failure mode a taxonomy
    invites, and this is the case that catches one: eight markers preserved, one block's
    prose tightened, and the reconciliation must plan that ONE edit and refuse nothing."""
    record = selfcheck()["cases"]["clean-edit"]
    assert set(record["per_marker"].values()) == {"preserved"}
    assert record["invented"] == [] and record["mangled"] == []

    p = source_projection("S")
    plan = reconcile(p, mutation("clean-edit"))
    assert plan.ok, details(plan)
    assert plan.refusals == ()
    assert [(e.state, e.block_id) for e in plan.changes] == [
        (ReconciliationState.EDITED, "s03")
    ]
    # and the opaque table is conserved, untouched, as it always is.
    assert "s08" not in plan.touched_block_ids


def test_ac4_an_unedited_projection_is_still_not_a_loss():
    """The other half of the must-not-refuse guard: the identity case."""
    p = source_projection("S")
    plan = reconcile(p, p.markdown)
    assert plan.ok, details(plan)
    assert plan.change_count == 0


def test_ac4_the_corpus_is_committed_here_and_not_imported_from_the_probe():
    """The corpus is a COMMITTED fixture, copied deliberately. This module reads nothing
    outside ``tests/fixtures`` and imports no probe code, so the suite cannot start
    depending on a tree the wheel does not ship."""
    assert (FIXTURES / "leg2-classifier-selfcheck.json").is_file()
    assert FIXTURES.parent.name == "fixtures"
    source = Path(__file__).read_text(encoding="utf-8")
    assert re.findall(r'Path\(__file__\)\.parent / "([^"]+)"', source) == ["fixtures"]
    assert not re.search(r"^\s*(?:import|from)\s+dev\b", source, re.MULTILINE)


# --------------------------------------------------------------------------- #
# AC5 — partial-application posture: docx whole-batch-zero-writes.             #
# --------------------------------------------------------------------------- #

def test_ac5_a_refusal_mid_document_leaves_the_whole_batch_unplanned(monkeypatch):
    """Three clean edits and one loss. The docx contract is whole-batch-zero-writes, so
    the plan carries NOTHING — not the three that were fine — and there is no batch to
    half-apply. The spy proves zero writes over plan and compile alike."""
    calls = []
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *a, **k: calls.append("urlopen") or (_ for _ in ()).throw(AssertionError),
    )
    monkeypatch.setattr(
        socket.socket, "connect",
        lambda *a, **k: calls.append("connect") or (_ for _ in ()).throw(AssertionError),
    )
    p = projection(
        ("p1", "one"), ("p2", "two"), ("p3", "three"), ("p4", "the one that was emptied")
    )
    plan = reconcile(p, edited(
        ("p1", "one edited"), ("p2", "two edited"), ("p3", "three edited"), ("p4", ""),
    ))
    assert not plan.ok
    assert reasons(plan) == [RefusalReason.MARKER_ORPHANED]
    assert plan.entries == ()
    assert plan.change_count == 0
    assert plan.touched_block_ids == ()
    with pytest.raises(RefusedError):
        compile_reconciliation(plan, p)
    assert calls == []


# --------------------------------------------------------------------------- #
# AC6 — dialect-free at birth.                                                 #
# --------------------------------------------------------------------------- #

#: The internal dialect a consumer cannot resolve: issue ids, story labels, acceptance-criterion
#: numbers, decision numbers, internal folders; plus one arm read from the private pattern set
#: (:mod:`domain_vocabulary`, inert in the public tree).
DIALECT = re.compile(
    RETIRED_ID.pattern + r"|\bLD-\d|\bF\d-S\d\b|\bAC\d|\bD\d{1,2}\b|progress/|requirements/"
)


def test_ac6_no_reconciliation_refusal_detail_carries_internal_dialect():
    seen = 0
    for _name, p, bad, _reason, _recovered, _phrase in RECOVERY_CASES:
        for refusal in reconcile(p, bad).refusals:
            seen += 1
            assert not DIALECT.search(refusal.detail), refusal.detail
    for case in selfcheck()["cases"]:
        for refusal in reconcile(source_projection("S"), mutation(case)).refusals:
            seen += 1
            assert not DIALECT.search(refusal.detail), refusal.detail
    assert seen


def test_ac6_the_refusal_vocabulary_itself_is_dialect_free():
    from larkdocio.write.model.refusal import RefusalReason as R

    for reason in RECONCILIATION_REFUSAL_REASONS:
        assert isinstance(reason, R)
        assert not DIALECT.search(reason.value)
        assert reason.value == reason.value.lower()
        assert " " not in reason.value


# --------------------------------------------------------------------------- #
# AC8 — the front door: capabilities() reflects the refusal surface.           #
# --------------------------------------------------------------------------- #

def test_ac8_capabilities_carries_every_new_refusal_reason():
    from larkdocio import capabilities

    registered = capabilities(full=True)["surfaces"]["docx-write"]["reconciliation"]
    assert registered["refusal_reasons"] == [
        r.value for r in RECONCILIATION_REFUSAL_REASONS
    ]
    for reason in (
        RefusalReason.MARKER_DROPPED,
        RefusalReason.MARKER_RELOCATED,
        RefusalReason.MARKER_MANGLED,
        RefusalReason.MARKER_ORPHANED,
    ):
        assert reason.value in registered["refusal_reasons"]


def test_ac8_capabilities_carries_the_ruled_in_row_too():
    from larkdocio import capabilities

    registered = capabilities(full=True)["surfaces"]["docx-write"]["reconciliation"]
    assert RefusalReason.CONSERVED_BLOCK_RE_CREATED.value in registered["refusal_reasons"]


def test_ac8_the_refusal_set_adds_no_operation_and_therefore_no_scope():
    """A refusal vocabulary is text, not an endpoint: the reconciler contributes no
    operation to the request-family registry, so the permission registry is untouched."""
    from larkdocio import capabilities

    surface = capabilities(full=True)["surfaces"]["docx-write"]
    assert "reconcile" not in {op["name"] for op in surface["operations"]}
    assert "reconciliation" not in {op["name"] for op in surface["operations"]}


# --------------------------------------------------------------------------- #
# AC9 — the twelfth row: a conserved block is never ALSO re-created.           #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kind", sorted(CREATABLE_OPAQUE))
@pytest.mark.parametrize(
    "disposition", list(AbsentBlockDisposition), ids=lambda d: d.value
)
def test_ac9_row_conserved_block_re_created(kind, disposition):
    """Marker gone, opaque content kept: the plan used to report the block CONSERVED and,
    in the same breath, plan an INSERT carrying that same block's content — applying it
    would have left the document holding the block twice while claiming conservation,
    which is precisely what the module's own contract says never happens. It REFUSES,
    naming the block, under BOTH dispositions."""
    content = CREATABLE_OPAQUE[kind]
    p = opaque_projection(content, kind)
    plan = reconcile(p, marker_eaten(content), absent=disposition)

    assert not plan.ok, [(e.state, e.block_id) for e in plan.entries]
    assert reasons(plan) == [RefusalReason.CONSERVED_BLOCK_RE_CREATED]
    assert "tb" in plan.refusals[0].detail
    assert plan.entries == ()
    assert plan.change_count == 0
    assert plan.touched_block_ids == ()
    with pytest.raises(RefusedError):
        compile_reconciliation(plan, p)


@pytest.mark.parametrize("kind", sorted(CREATABLE_OPAQUE))
def test_ac9_the_kinds_this_is_proven_on_are_ones_compose_can_really_create(kind):
    """The proof would be hollow on a kind the authoring dialect cannot create: the
    duplicate insert would never survive compilation and the row would be guarded by
    luck. Both kinds here compile to real new blocks."""
    from larkdocio.write import compose

    assert compose(CREATABLE_OPAQUE[kind])


def test_ac9_no_conserved_block_is_ever_ALSO_planned_as_an_insert():
    """The invariant behind the row, stated once over the whole plan rather than per
    case: for every plan this module can build, no INSERTED entry carries the content of
    a block the same plan marked conserved."""
    for kind, content in CREATABLE_OPAQUE.items():
        p = opaque_projection(content, kind)
        for disposition in (AbsentBlockDisposition.REFUSE, DELETE):
            plan = reconcile(p, marker_eaten(content), absent=disposition)
            conserved = {
                e.before
                for e in plan.entries
                if e.state is ReconciliationState.CONSERVED_OPAQUE
            }
            for entry in plan.entries:
                if entry.state is ReconciliationState.INSERTED:
                    assert entry.after not in conserved, (kind, disposition)


def test_ac9_the_insert_is_REFUSED_not_silently_dropped():
    """Dropping the insert would be the wrong fix: genuinely new content that legitimately
    appears in the same segment would be discarded silently. So the guard fires only on
    content that IS a conserved block's own — brand-new content beside it still plans its
    insert, and the block stays conserved."""
    p = opaque_projection(TABLE, "table")
    plan = reconcile(p, edited(
        ("p0", "one\n\nbrand new paragraph"), ("tb", TABLE), ("p1", "two"),
        kinds={"tb": "table"},
    ))
    assert plan.ok, details(plan)
    assert [(e.state, e.after) for e in plan.changes] == [
        (ReconciliationState.INSERTED, "brand new paragraph")
    ]
    assert "tb" not in plan.touched_block_ids


def test_ac9_a_deliberate_second_copy_under_a_SURVIVING_marker_is_still_an_insert():
    """The recovery the refusal names, performed: with the block's own marker back in
    place, a second copy of its content is an ordinary insert. The guard is scoped to the
    ambiguity it exists for — a marker that is NOT there — so it cannot eat the case where
    a consumer really did want another copy."""
    p = opaque_projection(TABLE, "table")
    plan = reconcile(p, edited(
        ("p0", "one"), ("tb", f"{TABLE}\n\n{TABLE}"), ("p1", "two"),
        kinds={"tb": "table"},
    ))
    assert plan.ok, details(plan)
    assert [(e.state, e.after) for e in plan.changes] == [
        (ReconciliationState.INSERTED, TABLE)
    ]


def test_ac9_restoring_the_marker_resolves_the_refusal():
    """The other half of the recovery: put the marker back exactly where it was and the
    reconciliation succeeds with nothing to do."""
    for kind, content in CREATABLE_OPAQUE.items():
        p = opaque_projection(content, kind)
        assert not reconcile(p, marker_eaten(content)).ok
        after = reconcile(p, p.markdown)
        assert after.ok, details(after)
        assert after.change_count == 0
