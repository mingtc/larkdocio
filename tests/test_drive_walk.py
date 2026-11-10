"""LD-324 — the Drive **walker**: depth-first recursion, the visited-set, and the caps.

* **AC3** — recursion is the same endpoint with one parameter changed, carried by a ``seen``
  set exactly as the round-2 probe's ``walk()`` does. The 4-level tree is reproduced offline
  from ``tests/captures/drive-spike/captures/11-real-tree-walk.json`` — 35 children, 6 subfolders,
  depth 4, **7 listing calls** — and the cycle guard is proven against a **synthetic** cyclic
  fixture, because **neither probe tree contained a `shortcut` child** (the Drive spec § O5): the
  hazard is asserted from the SDK model, which is exactly why the guard is built now.
* **AC4** — every cap is an explicit parameter with a documented default, and hitting one is a
  **disclosed truncation** naming which cap, where, and what was not visited. A silent
  truncation makes the enumeration lie about the folder.
"""
import inspect

import pytest

import drive_fixtures as fx
from larkdocio.drive.client import DriveClient
from larkdocio.drive.walk import (
    DEFAULT_MAX_CALLS,
    DEFAULT_MAX_CHILDREN,
    DEFAULT_MAX_DEPTH,
    walk_folder,
)


def walker(listings, **kwargs):
    transport = fx.RecordingTransport(fx.listing_router(listings))
    client = DriveClient("app-id", "app-secret", urlopen=transport,
                         token_fetcher=fx.token_fetcher,
                         rate_limiter=fx.fast_limiter(), **kwargs)
    return client, transport


def real_tree_walk(**kwargs):
    client, transport = walker(fx.real_tree_listings())
    return walk_folder(client, fx.real_tree_root(), **kwargs), transport


# --------------------------------------------------------------------------- #
# AC3 — depth-first recursion over the maintainer's real tree, reproduced offline.      #
# --------------------------------------------------------------------------- #

def test_ac3_the_walk_reproduces_the_spikes_own_numbers():
    """35 children · 6 subfolders · max depth 4 · **7 listing calls** — the capture's own
    ``_total_children`` / ``_subfolders`` / ``_max_depth`` / ``_calls_used``, read from the
    capture rather than typed in, so a re-probe that changed the tree reddens here."""
    capture = fx.real_tree()
    walk, transport = real_tree_walk()

    assert len(walk.children) == capture["_total_children"] == 35
    assert len(walk.subfolders) == capture["_subfolders"] == 6
    assert walk.max_depth_reached == capture["_max_depth"] == 4
    assert walk.listing_calls == capture["_calls_used"] == 7
    assert len(transport.calls) == 7


def test_ac3_the_walk_order_is_DEPTH_FIRST_exactly_as_the_probe_walked_it():
    walk, _t = real_tree_walk()
    expected = [(node["depth"], node["token"]) for node in fx.real_tree()["nodes"]]
    assert [(w.depth, w.child.token) for w in walk.children] == expected


def test_ac3_recursion_is_THE_SAME_ENDPOINT_with_one_parameter_changed():
    walk, transport = real_tree_walk()
    assert {call.path for call in transport.calls} == {"/open-apis/drive/v1/files"}
    listed = [call.params["folder_token"] for call in transport.calls]
    assert listed[0] == fx.real_tree_root()
    assert set(listed[1:]) == {w.child.token for w in walk.subfolders}


def test_ac3_the_per_type_totals_match_the_capture():
    walk, _t = real_tree_walk()
    assert walk.by_type() == fx.real_tree()["_by_type"] == {"folder": 6, "docx": 27, "file": 2}


def test_ac3_a_clean_walk_carries_NO_truncation_and_NO_cycle():
    walk, _t = real_tree_walk()
    assert walk.truncations == ()
    assert walk.cycles == ()
    assert walk.complete is True


# --- the visited-set, on a SYNTHETIC cyclic fixture (O5: never observed live) --- #

def cyclic_listings():
    """``root -> [A(folder)]``; ``A -> [root(folder), leaf]``. A child whose token re-enters an
    ancestor — the shape a ``shortcut`` could produce, and which no probe has ever seen."""
    root = {"code": 0, "msg": "success", "data": {"files": [
        fx.child_payload("fldrA", "fldrROOT", "folder")], "has_more": False}}
    a = {"code": 0, "msg": "success", "data": {"files": [
        fx.child_payload("fldrROOT", "fldrA", "folder"),
        fx.child_payload("docxLEAF", "fldrA", "docx")], "has_more": False}}
    return {"fldrROOT": root, "fldrA": a}


def test_ac3_a_CYCLE_TERMINATES_the_walk_rather_than_spinning():
    client, transport = walker(cyclic_listings())
    walk = walk_folder(client, "fldrROOT")
    assert walk.listing_calls == 2, "root and A, and never root again"
    assert len(transport.calls) == 2


def test_ac3_each_token_is_VISITED_ONCE():
    client, _t = walker(cyclic_listings())
    walk = walk_folder(client, "fldrROOT")
    tokens = [w.child.token for w in walk.children]
    assert len(tokens) == len(set(tokens))


def test_ac3_the_cycle_is_DISCLOSED_never_silently_pruned():
    client, _t = walker(cyclic_listings())
    walk = walk_folder(client, "fldrROOT")

    assert len(walk.cycles) == 1
    cycle = walk.cycles[0]
    assert cycle.token == "fldrROOT"
    assert cycle.path and cycle.first_seen_path
    assert "cycle" in cycle.note.lower() or "already" in cycle.note.lower()
    assert walk.complete is False, "a disclosed cycle is not a clean walk"


def test_ac3_the_visited_set_is_MANDATORY_even_though_its_hazard_is_UNPROVEN():
    """The Drive spec § O5 written into the code: the walker's docstring must say the guard stands on
    the SDK model rather than on an observation, or the next reader will assume it was seen."""
    from larkdocio.drive import walk as walk_module

    doc = walk_module.__doc__ + inspect.getdoc(walk_folder)
    assert "shortcut" in doc.lower()
    assert "never been observed" in doc.lower() or "no probe" in doc.lower()


# --------------------------------------------------------------------------- #
# AC4 — every cap explicit, defaulted, finite; hitting one is DISCLOSED.         #
# --------------------------------------------------------------------------- #

def test_ac4_every_cap_is_an_EXPLICIT_PARAMETER_with_a_DOCUMENTED_DEFAULT():
    params = inspect.signature(walk_folder).parameters
    for name, default in (("max_depth", DEFAULT_MAX_DEPTH),
                          ("max_children", DEFAULT_MAX_CHILDREN),
                          ("max_calls", DEFAULT_MAX_CALLS),
                          ("page_size", None)):
        assert name in params, name
        if default is not None:
            assert params[name].default == default, name
            assert isinstance(default, int) and 0 < default < 10 ** 6, (name, default)
    doc = inspect.getdoc(walk_folder)
    for default in (DEFAULT_MAX_DEPTH, DEFAULT_MAX_CHILDREN, DEFAULT_MAX_CALLS):
        assert str(default) in doc, f"the default {default} is not documented where it is used"


def test_ac4_the_runaway_depth_guard_is_the_PROBES_OWN_EIGHT():
    assert DEFAULT_MAX_DEPTH == 8


def test_ac4_MAX_DEPTH_fires_as_a_DISCLOSED_TRUNCATION():
    walk, _t = real_tree_walk(max_depth=2)

    assert walk.truncations, "a cap that fires must appear in the result"
    truncation = walk.truncations[0]
    assert truncation.cap == "max_depth"
    assert truncation.limit == 2
    assert truncation.at_folder and truncation.at_path
    assert truncation.not_visited, "the record must say what was NOT visited"
    assert walk.complete is False
    assert len(walk.children) < 35


def test_ac4_MAX_CHILDREN_fires_as_a_DISCLOSED_TRUNCATION():
    walk, _t = real_tree_walk(max_children=6)

    assert len(walk.children) == 6
    assert [t.cap for t in walk.truncations] == ["max_children"]
    assert walk.truncations[0].limit == 6
    assert walk.truncations[0].not_visited
    assert walk.complete is False


def test_ac4_MAX_CALLS_fires_as_a_DISCLOSED_TRUNCATION():
    walk, transport = real_tree_walk(max_calls=3)

    assert walk.listing_calls == len(transport.calls) == 3
    assert [t.cap for t in walk.truncations] == ["max_calls"]
    assert walk.truncations[0].limit == 3
    assert walk.truncations[0].not_visited
    assert walk.complete is False


def test_ac4_a_PAGE_BUDGET_truncation_inside_a_folder_reaches_the_WALK_result():
    """The per-folder page cap is disclosed by the client; the walk must carry it up rather
    than swallow it — a truncation that stops at the folder boundary is still a lie."""
    def endless(call):
        cursor = call.params.get("page_token", "")
        return fx.page([fx.child_payload(f"docx{len(cursor)}-{len(call.url)}", "fldrROOT")],
                       has_more=True, next_page_token=fx.opaque_page_token() + cursor + "x")

    client, _t = walker({"fldrROOT": endless})
    walk = walk_folder(client, "fldrROOT", max_pages=2)

    assert [t.cap for t in walk.truncations] == ["max_pages"]
    assert walk.complete is False


def test_ac4_NO_CAP_IS_INFINITE():
    for default in (DEFAULT_MAX_DEPTH, DEFAULT_MAX_CHILDREN, DEFAULT_MAX_CALLS):
        assert default == default and default != float("inf") and default > 0


def test_ac4_a_truncation_record_reads_as_a_SENTENCE_a_consumer_can_act_on():
    walk, _t = real_tree_walk(max_depth=1)
    rendered = walk.truncations[0].describe()
    assert "max_depth" in rendered and "1" in rendered
    assert "not visited" in rendered.lower()


# --------------------------------------------------------------------------- #
# The walk is READ-ONLY and paced, like everything else on this surface.        #
# --------------------------------------------------------------------------- #

def test_the_walk_makes_only_GET_listing_calls():
    _walk, transport = real_tree_walk()
    assert transport.methods == ["GET"]
    for call in transport.calls:
        assert "option" not in call.params


def test_the_walk_refuses_a_bad_root_token_with_the_honest_refusal():
    from larkdocio.drive.errors import REFUSAL_SENTENCE, FolderRefusedError

    client, _t = walker({})
    with pytest.raises(FolderRefusedError) as excinfo:
        walk_folder(client, "fldrNOTAREALTOKEN0000")
    assert REFUSAL_SENTENCE in str(excinfo.value)


def test_a_REFUSED_SUBFOLDER_never_fails_the_whole_walk_and_is_DISCLOSED():
    """A child that refuses mid-walk is disclosed, not fatal — the enumeration still has to
    describe the rest of the folder honestly. (LD-326 owns the same rule for *reads*.)"""
    listings = fx.real_tree_listings()
    victim = next(token for token in listings if token != fx.real_tree_root())
    del listings[victim]

    client, _t = walker(listings)
    walk = walk_folder(client, fx.real_tree_root())

    assert walk.refusals, "the refused subfolder must be disclosed"
    assert walk.refusals[0].token == victim
    assert "1061002" in walk.refusals[0].note
    assert walk.complete is False
