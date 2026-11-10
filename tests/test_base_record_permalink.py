"""LD-345 — `base.record_permalink()`: the server-minted Base record URL, fetched via
`with_shared_url=true`, per-selection by signature, with a typed absent state.

Offline. The API measurements (AC1/AC2) are asserted from the committed probe capture
`tests/captures/anchor-links-spike/captures/04-permalink-route.json` — the same capture→fixture discipline
the rest of the Base suite uses — so a re-probe that disagreed with the shipped shape would
redden here, not travel on.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from larkdocio.base.permalink import (
    PERMALINK_ABSENT,
    PERMALINK_FORBIDDEN,
    PERMALINK_RESOLVED,
    PERMALINK_STATES,
    PERMALINK_UNMINTED,
    RecordPermalink,
    STATE_MEANINGS,
    record_permalink,
)
from larkdocio.base.client import BaseReadClient, BATCH_GET_MAX_IDS

_REPO = Path(__file__).resolve().parents[1]
_CAPTURE = _REPO / "tests" / "captures" / "anchor-links-spike" / "captures" / "04-permalink-route.json"


def _capture():
    return json.loads(_CAPTURE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# A fake batch client — the composed entry point takes an injectable `client`. #
# --------------------------------------------------------------------------- #

class _Rec(SimpleNamespace):
    pass


class FakeBatchClient:
    """Records every batch_get_records call and returns a canned partition. `catalog` maps a
    record id to (shared_url, record_url); ids not in it and not in absent/forbidden are simply
    not returned (the pathological case)."""

    def __init__(self, catalog=None, absent=(), forbidden=()):
        self.catalog = catalog or {}
        self.absent = list(absent)
        self.forbidden = list(forbidden)
        self.calls = []

    def batch_get_records(self, app_token, table_id, record_ids, *, with_shared_url=False):
        ids = list(record_ids)
        self.calls.append({"app_token": app_token, "table_id": table_id,
                           "ids": ids, "with_shared_url": with_shared_url})
        records = [_Rec(record_id=rid,
                        shared_url=self.catalog[rid][0], record_url=self.catalog[rid][1])
                   for rid in ids if rid in self.catalog]
        return SimpleNamespace(
            records=records,
            absent_record_ids=[r for r in ids if r in self.absent],
            forbidden_record_ids=[r for r in ids if r in self.forbidden])


# --------------------------------------------------------------------------- #
# AC1 — the two remaining field questions, measured and recorded.               #
# --------------------------------------------------------------------------- #

def test_ac1_flag_off_control_the_single_get_does_NOT_carry_the_url_without_asking():
    """The flag's necessity is proven, not assumed: without `with_shared_url` neither url key
    arrives on the single GET, and the record LIST carries none either (round 1 call 4)."""
    cap = _capture()
    off = cap["AC1_i_flag_off_control"]
    assert off["single_get_carries_record_url_without_flag"] is False
    assert off["list"]["any_record_url_on_list"] is False


def test_ac1_shared_url_is_the_field_on_the_batch_route_and_it_is_an_ADDRESS_not_a_credential():
    """AC1(ii): `shared_url` IS populated on the batch route, and its MEASURED shape is the bare
    /record/<opaque> permalink grammar — no query params, no signature, no expiry, no fragment.
    The credential-class marks are exactly what it does not carry."""
    cap = _capture()
    shape = cap["AC2_batch_route"]["with_flag"]["per_record_url_keys"][0]["shared_url"]["shape"]
    assert cap["AC1_ii_shared_url_ever_populated"] is True
    assert shape["path_form"] == "/record/<27ch>"
    assert shape["query_param_names"] == []
    assert shape["has_fragment"] is False
    assert shape["scheme"] == "https"


def test_ac1_the_field_route_identity_the_batch_shared_url_IS_the_stable_record_url():
    """The crux: the batch route's `shared_url` is byte-identical to the single-GET's
    `record_url` for the same record — so it is the SAME address the spike proved stable across
    sessions (U5), arriving under a different key, not a coincidentally-same-grammar credential.
    And no credential value was captured to reach this verdict."""
    cap = _capture()
    ident = cap["AC1_field_route_identity"]
    assert ident["batch_shared_url_EQUALS_single_get_record_url"] is True
    assert ident["single_get_field_is_record_url"] is True
    assert ident["single_get_shared_url_null"] is True
    assert ident["batch_field_is_shared_url"] is True
    assert cap["no_credential_value_captured"] is True


# --------------------------------------------------------------------------- #
# AC2 — the real cost: the batch route honours the flag (only the url appearing proves it).     #
# --------------------------------------------------------------------------- #

def test_ac2_the_batch_route_HONOURS_with_shared_url_proven_by_the_url_appearing_not_code_zero():
    """R12: `code:0` proves nothing on this family. The admissible proof is the url actually
    present with the flag and ABSENT without it — both recorded in the capture."""
    cap = _capture()
    on = cap["AC2_batch_route"]["with_flag"]
    off = cap["AC2_batch_route"]["without_flag"]
    assert on["any_record_has_shared_url"] is True
    assert off["any_record_has_record_url"] is False and off["any_record_has_shared_url"] is False


def test_ac2_the_shipped_cost_is_ONE_CALL_per_BATCH_GET_MAX_IDS_not_one_per_record():
    """Fork (a): the batch route honours it, so a request for many ids costs one call per
    chunk of BATCH_GET_MAX_IDS — not one per record. Reuses the existing ceiling."""
    catalog = {f"rec{i}": (f"https://h/record/{i}", None) for i in range(BATCH_GET_MAX_IDS + 5)}
    fake = FakeBatchClient(catalog=catalog)
    out = record_permalink("app", "tbl", list(catalog), client=fake)
    assert len(fake.calls) == 2, "BATCH_GET_MAX_IDS+5 ids ⇒ two batch calls, not N calls"
    assert len(out) == BATCH_GET_MAX_IDS + 5
    assert all(c["with_shared_url"] is True for c in fake.calls)


def test_ac2_the_docstring_states_the_measured_cost():
    doc = record_permalink.__doc__
    assert "one" in doc.lower() and "BATCH_GET_MAX_IDS" in doc


# --------------------------------------------------------------------------- #
# AC3 — per-selection by construction: the signature cannot express the whole table.            #
# --------------------------------------------------------------------------- #

def test_ac3_a_bare_string_is_refused_not_iterated_character_by_character():
    with pytest.raises(TypeError) as exc:
        record_permalink("app", "tbl", "recSingleId", client=FakeBatchClient())
    assert "SEQUENCE" in str(exc.value)


def test_ac3_a_table_shaped_input_is_refused():
    """A non-iterable table-shaped object, and a sequence of non-strings, are both refused —
    there is no way to hand this function 'the whole table'."""
    with pytest.raises(TypeError):
        record_permalink("app", "tbl", object(), client=FakeBatchClient())
    with pytest.raises(TypeError):
        record_permalink("app", "tbl", [{"record_id": "rec1"}], client=FakeBatchClient())


def test_ac3_there_is_no_all_or_whole_table_parameter():
    import inspect
    params = set(inspect.signature(record_permalink).parameters)
    assert "all" not in params and "table" not in params
    assert params == {"app_token", "table_id", "record_ids", "client", "domain"}


def test_ac3_an_empty_ask_costs_zero_calls():
    fake = FakeBatchClient()
    assert record_permalink("app", "tbl", [], client=fake) == ()
    assert fake.calls == [], "the empty ask Lark refuses is never sent"


# --------------------------------------------------------------------------- #
# AC4 — the absent state is TYPED, and absence is not an error.                  #
# --------------------------------------------------------------------------- #

def test_ac4_the_four_outcomes_are_the_closed_vocabulary_each_with_a_meaning():
    assert PERMALINK_STATES == (
        PERMALINK_RESOLVED, PERMALINK_UNMINTED, PERMALINK_ABSENT, PERMALINK_FORBIDDEN)
    assert set(STATE_MEANINGS) == set(PERMALINK_STATES)
    for state in PERMALINK_STATES:
        assert len(STATE_MEANINGS[state]) > 40


def test_ac4_a_resolved_record_carries_its_url_and_only_that_state_does():
    fake = FakeBatchClient(catalog={"recA": ("https://h/record/AAA", None)})
    (out,) = record_permalink("app", "tbl", ["recA"], client=fake)
    assert out.state == PERMALINK_RESOLVED and out.resolved is True
    assert out.url == "https://h/record/AAA"
    assert out.note == STATE_MEANINGS[PERMALINK_RESOLVED]


def test_ac4_an_absent_record_is_typed_absent_never_raised_never_bare_none():
    fake = FakeBatchClient(absent=["recGone"])
    (out,) = record_permalink("app", "tbl", ["recGone"], client=fake)
    assert out.state == PERMALINK_ABSENT and out.resolved is False and out.url is None


def test_ac4_a_forbidden_record_is_typed_forbidden():
    fake = FakeBatchClient(forbidden=["recSecret"])
    (out,) = record_permalink("app", "tbl", ["recSecret"], client=fake)
    assert out.state == PERMALINK_FORBIDDEN and out.url is None


def test_ac4_a_read_record_with_no_permalink_is_UNMINTED_not_an_error():
    """A found record Lark returns no url for is a value it does not have — reported, not
    raised, and distinct from 'the record is gone' and 'you cannot see it'."""
    fake = FakeBatchClient(catalog={"recBlank": (None, None)})
    (out,) = record_permalink("app", "tbl", ["recBlank"], client=fake)
    assert out.state == PERMALINK_UNMINTED and out.url is None


def test_ac4_the_four_states_come_back_together_each_typed():
    fake = FakeBatchClient(
        catalog={"recA": ("https://h/record/AAA", None), "recBlank": (None, None)},
        absent=["recGone"], forbidden=["recSecret"])
    out = record_permalink("app", "tbl", ["recA", "recBlank", "recGone", "recSecret"],
                           client=fake)
    assert [o.state for o in out] == [
        PERMALINK_RESOLVED, PERMALINK_UNMINTED, PERMALINK_ABSENT, PERMALINK_FORBIDDEN]


def test_ac4_the_result_is_in_asked_order_and_deduplicated():
    fake = FakeBatchClient(catalog={"recA": ("u", None), "recB": ("v", None)})
    out = record_permalink("app", "tbl", ["recB", "recA", "recB"], client=fake)
    assert [o.record_id for o in out] == ["recB", "recA"], "first-seen order, no repeats"


def test_ac4_the_batch_route_field_shared_url_is_read_and_record_url_is_the_fallback():
    """On the batch route the permalink is `shared_url` (measured); a `record_url`-only record
    (as the single GET returns) is read too — the address, whichever key it lands in."""
    fake = FakeBatchClient(catalog={
        "recShared": ("https://h/record/SHARED", None),
        "recQdmRcxwuwScy": (None, "https://h/record/RECORDURL")})
    a, b = record_permalink("app", "tbl", ["recShared", "recQdmRcxwuwScy"], client=fake)
    assert a.url == "https://h/record/SHARED"
    assert b.url == "https://h/record/RECORDURL"


# --------------------------------------------------------------------------- #
# AC5 — the recorded decision is amended; the guard is transformed, not deleted. #
# --------------------------------------------------------------------------- #

def test_ac5_the_default_batch_body_stays_byte_identical_flag_off():
    """The restraint the old test asserted still holds: a DEFAULT batch_get_records call sends
    `record_ids` and nothing else. The flag rides ONLY when asked."""
    from lark_oapi.core import JSON
    captured = []

    class _Leg:
        pass

    class _Recorder:
        def __call__(self, request, *a, **k):
            captured.append(request)
            return _batch_response()

    def _batch_response():
        from lark_oapi.api.bitable.v1 import BatchGetAppTableRecordResponse
        return JSON.unmarshal(json.dumps(
            {"code": 0, "msg": "success",
             "data": {"records": [], "absent_record_ids": [], "forbidden_record_ids": []}}),
            BatchGetAppTableRecordResponse)

    sdk = _Leg(); sdk.bitable = _Leg(); sdk.bitable.v1 = _Leg()
    sdk.bitable.v1.app_table_record = _Leg()
    sdk.bitable.v1.app_table_record.batch_get = _Recorder()

    class _Limiter:
        def acquire(self):
            pass

    c = BaseReadClient("id", "secret", sdk_client=sdk, rate_limiter=_Limiter())
    c.batch_get_records("app", "tbl", ["recA", "recB"])
    default_body = json.loads(JSON.marshal(captured[0].request_body))
    assert list(default_body) == ["record_ids"], default_body

    c.batch_get_records("app", "tbl", ["recA"], with_shared_url=True)
    asked_body = json.loads(JSON.marshal(captured[1].request_body))
    assert set(asked_body) == {"record_ids", "with_shared_url"}
    assert asked_body["with_shared_url"] is True


def test_ac5_the_amended_docstring_states_which_field_ships_and_that_the_rule_did_not_change():
    doc = BaseReadClient.batch_get_records.__doc__
    assert "shared_url" in doc and "record_url" in doc
    assert "AMENDS" in doc
    assert "byte-identical" in doc
    # the media.py precedent is preserved, scoped rather than weakened
    assert "media" in doc.lower()
    assert "scope was measured" in doc


def test_ac5_media_pys_credential_class_rule_still_stands():
    """The sibling rule that short-lived signed links are credentials is NOT weakened — the
    ephemeral attachment keys are still never surfaced."""
    from larkdocio.base import media
    assert media.EPHEMERAL_ATTACHMENT_KEYS == ("url", "tmp_url")


# --------------------------------------------------------------------------- #
# AC6 (partial, module side) — the public entry point is exported.              #
# --------------------------------------------------------------------------- #

def test_ac6_record_permalink_and_its_vocabulary_are_public_from_larkdocio_base():
    import larkdocio.base as base
    for name in ("record_permalink", "RecordPermalink", "PERMALINK_RESOLVED",
                 "PERMALINK_UNMINTED", "PERMALINK_ABSENT", "PERMALINK_FORBIDDEN",
                 "PERMALINK_STATES"):
        assert name in base.__all__, name
        assert hasattr(base, name), name
