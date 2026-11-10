"""LD-303 → LD-314 — THE READ-FILTER POSTURE: what ``search_filter()`` builds, a read now sends.

``larkdocio.base.view_filters`` ships two filter dialects behind one ``FilterSpec``. Under LD-303
only the **view** half had a transport, and this module guarded that silence: no shipped read
took a filter, a ``view_id`` or a sort, and the three places that said so were pinned together so
none could rot. LD-314 took the decision LD-303 deferred, and **all three moved in one change** —
which is exactly the event this module existed to force. It now guards the **positive** claim,
with the same three-way pinning, so the reverse rot is impossible too: a signature that quietly
lost a parameter, a guide that went back to describing a gap, or a registry that stopped
advertising what ships would each redden here.

**The lesson that outlived the gap.** What the dogfood consumer hit was never the absence — a gap
is allowed to exist — it was the shipped guide describing a round trip no shipped call could
make. So the tripwire is the *equivalence* (:func:`test_the_GUIDE_SENTENCE_and_the_SIGNATURE…`):
the guide and the signature must agree about whether a read can be filtered, in whichever
direction the truth happens to point.

**And R12 outlives it too.** ``records/search`` silently ignores body keys it does not recognise,
so nothing here treats the presence of a parameter as proof it is honoured — that is the live
arms' job (``tests/test_live_base_read_filter.py``,
``tests/test_live_base_view_scoped_read.py``), and this module asserts those arms are **cited by
the register row**, so the claim can never be re-grounded on a ``code:0``.
"""
import inspect
import json
import re

import pytest

from base_md import BASE_MD, register_rows, table_with
import capability_rows as rows
from larkdocio import guide
from larkdocio.base.client import BaseReadClient
from larkdocio.base.view_filters import SearchFilter, search_filter
from larkdocio.capabilities import capabilities

#: The recipe the consumer read, addressed the way a consumer addresses it — by slug, through
#: the shipped accessor. Pinned by ``guide_recipes.RECIPE_SPECS`` as well (which spells the same
#: heading without the ``recipe-`` stem), which is why both are quoted rather than derived: if
#: the heading moves, both pins say so.
FILTER_RECIPE_SLUG = (
    "recipe-filter-a-base-two-ways-the-rows-a-read-returns-and-the-rows-a-person-sees")
FILTER_RECIPE_SPEC_SLUG = FILTER_RECIPE_SLUG.removeprefix("recipe-")

#: The overclaim, verbatim as it shipped in the version the bug was filed on. Kept as a literal
#: even though the transport now exists, because the sentence was wrong about a **round trip
#: larkdocio makes for you** in a way that survives being true: it described a body being handed
#: back as if it had been sent. The recipe now says what happens; it never says this.
THE_OVERCLAIM = "larkdocio hands\nback that subset"

#: What LD-303 made the recipe say while the gap stood. It must be **gone** now — a shipped
#: sentence that still described the absence would be the same defect pointing the other way.
THE_RETIRED_CLAIM = "read client does not send it yet"

#: The record-reading entry points. ``get_view`` / ``list_views`` legitimately take a ``view_id``
#: (a view read is not a filtered record read), so the walk names the record reads on purpose.
RECORD_READS = ("search_records", "batch_get_records")

#: The parameters a filtered read introduces. LD-303's Decision bound them together — *"one
#: signature decision and one live proof, not three"* — so they are asserted as a set.
SENDING_PARAMS = ("filter", "view_id", "sort")


@pytest.fixture(scope="module")
def base_md():
    return BASE_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def recipe():
    return guide(FILTER_RECIPE_SLUG)


def _read_sends_a_filter():
    """True while a shipped record read has a way to send one. The single reading of the
    transport fact — every assertion below goes through it, so there is one place to be right."""
    for name in RECORD_READS:
        params = inspect.signature(getattr(BaseReadClient, name)).parameters
        if any(p in params for p in SENDING_PARAMS):
            return True
        for param in params.values():
            if "Filter" in str(param.annotation):
                return True
    return False


# --------------------------------------------------------------------------- #
# The transport fact itself                                                    #
# --------------------------------------------------------------------------- #

def test_search_filter_BUILDS_A_BODY_and_a_shipped_read_SENDS_IT():
    """Both halves in one test, because either alone is misleading. The producer works — the
    body is real and correctly keyed — and the read surface has the parameter that takes it."""
    from larkdocio.base.view_filters import Condition, FieldName, FilterSpec

    body = search_filter(FilterSpec(conditions=(Condition(FieldName("Done"), "isNotEmpty"),)))
    assert isinstance(body, SearchFilter)
    assert "field_name" in body.to_dict()["conditions"][0], (
        "the search dialect is name-keyed — that much has always been true and shipped")

    assert _read_sends_a_filter(), (
        "a shipped record read lost its way to send a filter, a view_id or a sort. Three "
        "statements now say a filtered read is possible and all three must move in the SAME "
        f"change: GUIDE.md's filter recipe ({FILTER_RECIPE_SLUG!r}), the base-read surface in "
        "capabilities(), and BASE.md's read-filter register row.")


def test_ALL_THREE_PARAMETERS_are_on_the_read_because_they_were_ONE_decision():
    """LD-303's Decision, enforced: a change that keeps the filter and drops ``view_id`` (or the
    reverse) is a half-move, and a half-move is what this guard is for."""
    params = inspect.signature(BaseReadClient.search_records).parameters
    missing = [name for name in SENDING_PARAMS if name not in params]
    assert not missing, (
        f"search_records no longer takes {missing}. The three are one signature decision — "
        "shipping some of them is a posture nobody took.")


def test_the_UNFILTERED_READ_is_still_the_DEFAULT_so_the_render_path_did_not_change():
    """The widening is opt-in. Every one of the three defaults to absent, which is what keeps
    the L1 render path's request byte-identical to the one the R12 restraint was written for."""
    params = inspect.signature(BaseReadClient.search_records).parameters
    for name in SENDING_PARAMS:
        assert params[name].default is None
        assert params[name].kind is inspect.Parameter.KEYWORD_ONLY


# --------------------------------------------------------------------------- #
# AC2 — the shipped guide                                                      #
# --------------------------------------------------------------------------- #

def test_the_OVERCLAIM_is_gone_from_the_shipped_guide(recipe):
    """The sentence the bug was filed on. It stays retired even now that a filtered read works:
    the recipe shows the call and its result rather than promising on the library's behalf."""
    normalized = " ".join(recipe.split())
    assert " ".join(THE_OVERCLAIM.split()) not in normalized, (
        "the guide's original overclaim sentence is back")


def test_the_RETIRED_CLAIM_is_gone_too_because_it_is_now_the_FALSE_one(recipe):
    """The mirror of the test above, and the one that catches a half-move: the transport shipped,
    so a guide still saying the read cannot send it would mislead in the other direction."""
    normalized = " ".join(recipe.split())
    assert THE_RETIRED_CLAIM not in normalized, (
        f"the filter recipe still says {THE_RETIRED_CLAIM!r}, which stopped being true when "
        "search_records grew its filter parameter")


def test_the_recipe_SHOWS_THE_FILTERED_READ_before_the_view_half(recipe):
    """A reader who stops at filter one must still leave with the working call, not with a body
    they are left holding — which is the failure mode the whole story is about."""
    normalized = " ".join(recipe.split())
    head = normalized.split("Filter two")[0]
    assert "filter=" in head or "search_records" in head, (
        "the read half of the recipe no longer shows the read that sends the filter")
    assert "sort=" in normalized and "view_id" in normalized, (
        "the recipe introduces the filter without the other two thirds of the same decision")


def test_the_CODE_BLOCK_actually_makes_the_filtered_call(recipe):
    """The fenced recipe is the part people paste, so the claim has to be in the code, not only
    in the prose above it."""
    fence = recipe.split("```python")[1].split("```")[0]
    assert "filter=search_filter(" in fence, (
        "the recipe's code block does not pass a filter to a read")
    read_filter_comment = [line for line in fence.splitlines()
                           if line.startswith("#") and "READ FILTER" in line.upper()]
    assert read_filter_comment, "the recipe's read-filter step lost its labelling comment"
    assert not any("not sent" in line.lower() or "nothing is sent" in line.lower()
                   for line in read_filter_comment), (
        f"the read-filter step's comment still says the body is not sent: {read_filter_comment}")


def test_the_recipe_TEACHES_THE_R12_CHECK_rather_than_asserting_the_filter_worked(recipe):
    """The consumer-facing half of R12: a reader is shown how to tell a honoured filter from an
    ignored one, because on this endpoint the response code cannot tell them."""
    normalized = " ".join(recipe.split())
    assert "IGNORED" in normalized or "ignored" in normalized, (
        "the recipe does not tell a reader that this endpoint ignores keys it does not know")


def test_the_GUIDE_SENTENCE_and_the_SIGNATURE_cannot_drift_apart(recipe):
    """The tripwire that makes this a guard rather than a snapshot, and the one assertion that
    never had to change: the guide and the signature must agree, whichever way the truth points.
    Move either side alone and this reddens."""
    says_it_cannot = THE_RETIRED_CLAIM in " ".join(recipe.split())
    assert says_it_cannot is not _read_sends_a_filter(), (
        "the shipped guide and the shipped signature disagree about whether a read can be "
        "filtered — one of them changed without the other")


def test_the_recipes_own_HEADING_pairing_is_untouched():
    """Correcting the prose must not renumber or rename the recipe corpus."""
    import guide_recipes

    slugs = [spec.slug for spec in guide_recipes.RECIPE_SPECS]
    assert FILTER_RECIPE_SPEC_SLUG in slugs, (
        "the filter recipe's slug moved, so the recipe↔heading pairing changed — that is a "
        "wider change than the one this story made")


# --------------------------------------------------------------------------- #
# AC3 — capabilities()                                                         #
# --------------------------------------------------------------------------- #

def test_the_base_read_surface_ADVERTISES_THE_READ_FILTER():
    """The registry is where a consumer discovers the surface without reading the guide, so the
    capability has to be sayable from ``capabilities()`` alone."""
    surface = capabilities(full=True)["surfaces"]["base-read"]
    blob = json.dumps(surface, default=str)
    hits = [m.group(0) for m in re.finditer(r".{0,60}filter.{0,60}", blob, re.I)]
    assert hits, (
        "the base-read surface says nothing about filtering, and a filtered read ships. "
        "GUIDE.md's filter recipe and BASE.md's register row say it; this must too.")
    assert "search_records takes view_id" in blob, (
        "the surface advertises a filter without the view_id half of the same decision")
    assert "does not combine" in blob, (
        "the surface must carry the refusal too — a registry that advertises `filter` and "
        "`view_id` without saying they do not combine promises a call that is refused")


def test_the_base_read_surface_DOES_NOT_CLAIM_MORE_THAN_WAS_PROVEN():
    """AC7's ceiling. Grouping is swallowed identically to a bogus key and must never appear as
    a capability; the operation set is re-read here so a new read is not filtered by accident."""
    surface = capabilities(full=True)["surfaces"]["base-read"]
    blob = json.dumps(surface, default=str)
    assert "group_by" not in blob and "grouping is" not in blob.lower(), (
        "the base-read surface mentions grouping, which records/search swallows exactly as it "
        "swallows {'zzz': 1} — it is not a capability and must not read as one")
    assert rows.names(surface, rows.OPERATION) == [
        "batch_get_records", "get_app", "get_view", "list_fields", "list_tables", "list_views",
        "search_records", "read_base", "read_base_markdown", "record_permalink"], (
        "the base-read operation set moved; re-read whether the new one takes a filter")


# --------------------------------------------------------------------------- #
# AC4 — BASE.md carries the truth                                              #
# --------------------------------------------------------------------------- #

def _read_filter_register_row(text):
    rows = [row for row in register_rows(text)
            if "search_filter" in row["Limitation / workaround"]]
    assert len(rows) == 1, (
        f"expected exactly ONE register row about the search-filter transport; found "
        f"{[r['#'] for r in rows]}. Two rows would be two competing sentences about one fact.")
    return rows[0]


def test_the_register_records_the_READ_FILTER_TRANSPORT_and_how_it_was_PROVEN(base_md):
    row = _read_filter_register_row(base_md)
    text = row["Limitation / workaround"]
    for needle in ("search_filter", "view_filter", "records/search", "view_id", "sort"):
        assert needle in text, f"the register row does not name {needle!r}"
    assert "has a transport" in text.lower() or "both travel" in text.lower(), (
        "the row does not state the posture: the body is built AND sent")
    status = next(v.strip().strip("`") for k, v in row.items() if "status" in k.lower())
    assert status == "supported", (
        f"status is {status!r}; the sending path shipped and was proven differentially live, "
        "which is what `supported` means in this register")


def test_the_register_row_GROUNDS_THE_CLAIM_ON_THE_LIVE_ARMS_not_on_a_code(base_md):
    """R12, carried forward into the row's own evidence column: the arms named here are the
    differential ones, so nobody can later re-ground this row on a ``code:0``."""
    row = _read_filter_register_row(base_md)
    for cited in ("src/larkdocio/base/view_filters.py", "src/larkdocio/base/client.py",
                  "tests/test_base_read_filter_posture.py",
                  "tests/test_live_base_read_filter.py",
                  "tests/test_live_base_view_scoped_read.py"):
        assert cited in row["Evidence"], f"the row does not cite {cited}"
    trigger = row["Revisit trigger — the observable API change"]
    assert "uncaptured" in trigger.lower() or "R12" in trigger, (
        "the trigger must carry forward what is still unmeasured — the combination and the "
        "nesting depth — rather than reading as if everything is settled")


def test_the_RECORD_READ_BODY_TABLE_agrees_with_that_register_row(base_md):
    """BASE.md's own parameter table is the place a maintainer looks first, so it must route to
    the register row rather than compete with it — and it must not still say `not sent`."""
    row = _read_filter_register_row(base_md)
    cell = [row
            for _headers, rows in table_with(base_md, "Parameter", "Placement", "Why")
            for row in rows if "`filter`" in row["Parameter"]]
    assert cell, "the record-read parameter table lost its filter/sort row"
    assert "not sent" not in cell[0]["Placement"].lower(), (
        f"the parameter table still places `filter` as not sent: {cell[0]['Placement']!r}")
    why = cell[0]["Why"]
    assert f"register row {row['#']}" in why, (
        f"the `filter` / `sort` row does not cite register row {row['#']}: {why!r}")
    assert "search_filter" in why
