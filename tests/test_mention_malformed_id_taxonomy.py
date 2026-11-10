"""A malformed id is not a permission denial (LD-290).

``batch_get_user_names`` treated **every** ``not resp.success()`` as the missing-scope case:
one message that said *denied*, advised granting "the scope named in the message", and
negative-cached the whole run. Code ``99992351`` — *"The request you send is not a valid
{open_id} or not exists … Invalid ids: [...]"* — is a **malformed-input** error. It names no
scope, no grant fixes it, and it is per-id: the body's ``error.field_violations[]`` says
exactly which ids were rejected. So one bad id both mis-diagnosed the failure and discarded
the valid names asked for alongside it.

The property under test is the same one the diagnosability work established for the quiet
paths, extended to the loud ones: **the families are distinguishable**. A denial keeps the
grant advice and the whole-run negative cache. A rejected id says the call was **not** denied,
names the ids Lark rejected, re-asks for the rest, and lets the run continue.
"""
import logging
from types import SimpleNamespace

import consumer_text
from larkdocio.read.client import Client


_MALFORMED_MSG = (
    "The request you send is not a valid {open_id} or not exists, and the example value is "
    "{ou_da5****************dfe}. Invalid ids: [ou_deadbeef00000000000000000000] . Please see "
    "field_violations for details and refer to API documentation to correct accordingly and "
    "resubmit"
)


def _user(open_id, name=None):
    return SimpleNamespace(open_id=open_id, name=name, en_name=None, nickname=None)


def _violation(value):
    return SimpleNamespace(field="user_ids", value=value, description="id not exist")


def _ok(items):
    return SimpleNamespace(success=lambda: True, code=0, msg="ok", error=None,
                           data=SimpleNamespace(items=items))


def _malformed(*invalid_ids, attributed=True, code=99992351):
    """A live-shaped ``99992351`` response (capture: dev repo, contacts bogus-id probe)."""
    error = SimpleNamespace(
        log_id="LOG-XYZ",
        field_violations=[_violation(i) for i in invalid_ids] if attributed else None,
    )
    return SimpleNamespace(success=lambda: False, code=code, msg=_MALFORMED_MSG,
                           error=error, data=None)


def _denied():
    return SimpleNamespace(
        success=lambda: False, code=99991672, error=None, data=None,
        msg="Access denied. One of the following scopes is required: [contact:user.base:readonly]",
    )


def _resolver_client(batch_fn):
    client = Client.__new__(Client)
    client.lark_client = SimpleNamespace(
        contact=SimpleNamespace(v3=SimpleNamespace(user=SimpleNamespace(batch=batch_fn)))
    )
    return client


def _resolve(ids, batch_fn, caplog):
    with caplog.at_level(logging.INFO, logger="larkdocio"):
        out = _resolver_client(batch_fn).batch_get_user_names(ids)
    return out, [r for r in caplog.records if r.levelno == logging.INFO]


def _scripted(*responses):
    """A batch stub answering the scripted responses in order, recording the ids asked."""
    asked = []
    queue = list(responses)

    def batch(req):
        asked.append(list(req.user_ids))
        return queue.pop(0)

    batch.asked = asked
    return batch


# --------------------------------------------------------------------------- #
# The reported bug: one bogus id, and the valid name asked for alongside it.   #
# --------------------------------------------------------------------------- #

def test_a_rejected_id_does_not_discard_the_valid_names_asked_for_alongside_it(caplog):
    """The reproduction: ``[valid, bogus]`` used to return ``{}``. The rejected id is dropped
    and the remaining ids are re-asked, so the valid name survives."""
    batch = _scripted(
        _malformed("ou_deadbeef00000000000000000000"),
        _ok([_user("ou_valid", name="Ada")]),
    )
    out, _lines = _resolve(["ou_valid", "ou_deadbeef00000000000000000000"], batch, caplog)

    assert out == {"ou_valid": "Ada"}
    assert batch.asked == [
        ["ou_valid", "ou_deadbeef00000000000000000000"],
        ["ou_valid"],
    ], batch.asked


def test_the_rejected_id_line_says_the_call_was_not_denied_and_advises_no_grant(caplog):
    """The diagnostic itself: no ``denied``, no grant advice — and the id shape named as the
    cause, because that is the only thing a reader can act on."""
    batch = _scripted(_malformed("ou_bad"), _ok([_user("ou_valid", name="Ada")]))
    _out, lines = _resolve(["ou_valid", "ou_bad"], batch, caplog)

    assert len(lines) == 1, [r.message for r in lines]
    message = lines[0].message
    lowered = message.lower()
    assert "grant" not in lowered, message
    assert "scope" not in lowered, message
    assert "not denied" in lowered, message
    assert "99992351" in message, message


def test_the_rejected_id_line_names_the_ids_lark_rejected(caplog):
    """``error.field_violations[]`` is per-id attribution — the one thing that makes the
    failure actionable, so it is reported rather than left in the raw body."""
    batch = _scripted(_malformed("ou_bad1", "ou_bad2"), _ok([_user("ou_valid", name="Ada")]))
    _out, lines = _resolve(["ou_valid", "ou_bad1", "ou_bad2"], batch, caplog)

    assert "ou_bad1" in lines[0].message and "ou_bad2" in lines[0].message, lines[0].message


def test_only_ids_we_actually_asked_about_are_reported_rejected(caplog):
    """A drifted or echoed violation value can never make the resolver drop an id the caller
    never asked about — the same falsification discipline the sheets id check uses."""
    batch = _scripted(_malformed("ou_bad", "ou_never_asked"), _ok([_user("ou_valid", name="Ada")]))
    _out, lines = _resolve(["ou_valid", "ou_bad"], batch, caplog)

    assert "ou_never_asked" not in lines[0].message, lines[0].message
    assert batch.asked[1] == ["ou_valid"], batch.asked


# --------------------------------------------------------------------------- #
# The negative cache DISTINGUISHES: a rejected id must not poison the run.     #
# --------------------------------------------------------------------------- #

def test_a_rejected_id_in_the_first_chunk_does_not_negative_cache_the_later_chunks(caplog):
    """The whole-run negative cache is for the denial and transport families. A rejected id
    is neither, so every later chunk is still asked and its names still resolve."""
    ids = ["ou_bad"] + [f"ou_{n}" for n in range(120)]
    asked = []

    def batch(req):
        asked.append(list(req.user_ids))
        if "ou_bad" in req.user_ids:
            return _malformed("ou_bad")
        return _ok([_user(i, name=f"n-{i}") for i in req.user_ids])

    out, _lines = _resolve(ids, batch, caplog)

    # chunk 1, chunk 1 re-asked without the rejected id, then chunks 2 and 3 — the run did
    # not stop at the rejection.
    assert len(asked) == 4, asked
    assert out["ou_0"] == "n-ou_0"
    assert out["ou_110"] == "n-ou_110"
    assert "ou_bad" not in out


def test_a_later_valid_id_retries_cleanly_after_a_rejected_one(caplog):
    """A second call on the same client — the cache is per run, and a run that saw a rejected
    id leaves nothing behind that suppresses the next lookup."""
    batch = _scripted(
        _malformed("ou_bad"),
        _ok([_user("ou_valid", name="Ada")]),
    )
    client = _resolver_client(batch)
    with caplog.at_level(logging.INFO, logger="larkdocio"):
        first = client.batch_get_user_names(["ou_bad"])
        second = client.batch_get_user_names(["ou_valid"])

    assert first == {}
    assert second == {"ou_valid": "Ada"}


def test_a_chunk_whose_every_id_is_rejected_makes_no_pointless_re_ask(caplog):
    """Nothing left to ask about is not a reason to call the endpoint with an empty list."""
    batch = _scripted(_malformed("ou_bad1", "ou_bad2"))
    out, lines = _resolve(["ou_bad1", "ou_bad2"], batch, caplog)

    assert out == {}
    assert len(batch.asked) == 1, batch.asked
    assert len(lines) == 1, [r.message for r in lines]


def test_a_rejected_id_is_not_re_reported_as_an_id_that_did_not_come_back(caplog):
    """The shortfall summary explains ids that vanished by the contacts data range. An id
    Lark rejected already has its explanation, so it is excluded rather than counted twice."""
    batch = _scripted(_malformed("ou_bad"), _ok([_user("ou_valid", name="Ada")]))
    _out, lines = _resolve(["ou_valid", "ou_bad"], batch, caplog)

    assert len(lines) == 1, [r.message for r in lines]
    assert "did not come back" not in lines[0].message, lines[0].message


# --------------------------------------------------------------------------- #
# The families stay apart: the denial path is untouched.                       #
# --------------------------------------------------------------------------- #

def test_a_real_denial_keeps_the_grant_advice_and_the_whole_run_negative_cache(caplog):
    """The regression guard on the other side: the message that exists for the missing-scope
    case still fires for the missing-scope case, and still stops the run."""
    batch = _scripted(_denied())
    out, lines = _resolve([f"ou_{n}" for n in range(120)], batch, caplog)

    assert out == {}
    assert len(batch.asked) == 1, batch.asked
    assert "denied" in lines[0].message.lower()
    assert "Grant the scope" in lines[0].message
    assert "contact:user.base:readonly" in lines[0].message


def test_an_unclassified_failure_reports_the_code_without_prescribing_a_grant(caplog):
    """A code that is neither a denial nor a rejected id gets Lark's own answer verbatim and
    no prescription — advice that cannot help is worse than none."""
    resp = SimpleNamespace(success=lambda: False, code=1254005, msg="something else",
                           error=None, data=None)
    out, lines = _resolve(["ou_1"], _scripted(resp), caplog)

    assert out == {}
    assert len(lines) == 1, [r.message for r in lines]
    assert "1254005" in lines[0].message
    assert "grant" not in lines[0].message.lower()


def test_a_rejected_id_code_with_no_per_id_attribution_claims_no_ids(caplog):
    """Positive proof only: the code says an id was rejected but the body names none, so none
    is dropped, none is claimed — and the run still is not negative-cached as a denial."""
    batch = _scripted(
        _malformed(attributed=False),
        _ok([_user("ou_50", name="Ada")]),
    )
    out, lines = _resolve([f"ou_{n}" for n in range(60)], batch, caplog)

    assert len(batch.asked) == 2, batch.asked          # the second chunk is still asked
    assert out == {"ou_50": "Ada"}
    assert "grant" not in lines[0].message.lower(), lines[0].message
    assert "ou_" not in lines[0].message.split("Msg:")[0], lines[0].message


# --------------------------------------------------------------------------- #
# The line is shipped text.                                                    #
# --------------------------------------------------------------------------- #

def test_every_failure_line_is_dialect_free_and_cites_no_dev_repo_path(caplog):
    """These are consumer-reaching strings: no issue id, no role, no path into a repo the
    consumer does not have."""
    shapes = (
        _scripted(_malformed("ou_bad"), _ok([])),
        _scripted(_denied()),
        _scripted(SimpleNamespace(success=lambda: False, code=1254005, msg="x",
                                  error=None, data=None)),
    )
    for batch in shapes:
        caplog.clear()
        _out, lines = _resolve(["ou_valid", "ou_bad"], batch, caplog)
        for record in lines:
            assert consumer_text.dialect_hits(record.message) == [], record.message
            assert "dev/" not in record.message, record.message
