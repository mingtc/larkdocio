"""The mention resolver says WHICH WAY it degraded (LD-184).

``batch_get_user_names`` had **three** ways to come back empty and **two** log lines. The two
loud paths had an exception or an error code to quote; the two quiet ones had neither:

* success, items returned, **every name field empty** — the loop finds nothing usable and the
  user is omitted, silently;
* success, but an **id simply absent** from the response — the loop never sees it, silently.

Both look identical to a caller, and identical to a zero-item response: ``{}``. That exact
indistinguishability cost about five days of misdiagnosis. The recorded diagnosis was the
contacts availability range; the truth was a missing **field-level** scope, invisible precisely
because a null-named user is dropped without a word.

Resolution works now, so this is **diagnosability, not behavior**: the same names resolve, the
same unresolved mentions render as their raw ``@open_id``, and the reader's output is
unchanged. What changes is that the next failure is legible in one line instead of five days.

The property this module exists for is **pairwise distinguishability**, so it is tested as one
— a direct string comparison of the three messages, not an eyeball.
"""
import logging
from types import SimpleNamespace

import consumer_text
from larkdocio.read.client import Client, _mention_resolution_summary


def _user(open_id, name=None, en_name=None, nickname=None):
    return SimpleNamespace(open_id=open_id, name=name, en_name=en_name, nickname=nickname)


def _contact_resp(success=True, code=0, msg="ok", items=None):
    return SimpleNamespace(
        success=lambda: success,
        code=code,
        msg=msg,
        get_log_id=lambda: "LOG-XYZ",
        data=SimpleNamespace(items=items or []),
    )


def _client_with_batch(batch_fn):
    client = Client.__new__(Client)
    client.lark_client = SimpleNamespace(
        contact=SimpleNamespace(v3=SimpleNamespace(user=SimpleNamespace(batch=batch_fn)))
    )
    return client


def _resolve(ids, batch_fn, caplog):
    with caplog.at_level(logging.INFO, logger="larkdocio"):
        out = _client_with_batch(batch_fn).batch_get_user_names(ids)
    return out, [r for r in caplog.records if r.levelno == logging.INFO]


# --------------------------------------------------------------------------- #
# AC2 — THE PROPERTY: the three cases are pairwise distinguishable.            #
# --------------------------------------------------------------------------- #

#: The three shapes that used to share one silent outcome, as
#: ``(requested_ids, returned_ids, resolved_ids)``. They were ``(requested, returned, named)``
#: integer triples until LD-210 AC6 made the invariant a SET difference — three counts cannot
#: express one, which is how an id the answer volunteered came to mask an id it omitted. The
#: shapes themselves are unchanged: two ids asked about, and the same three outcomes.
_ZERO_ITEMS = (("ou_a", "ou_b"), (), ())
_ALL_NULL_NAMED = (("ou_a", "ou_b"), ("ou_a", "ou_b"), ())
_SOME_IDS_ABSENT = (("ou_a", "ou_b"), ("ou_a",), ("ou_a",))

#: The mixed shape the AC7 arms below also sweep: one returned name-less, one absent.
_MIXED = (("ou_a", "ou_b"), ("ou_a",), ())


def test_ac2_the_three_cases_produce_pairwise_UNEQUAL_messages():
    """AC2: this is the property whose absence is the whole issue, so it is asserted as a
    direct string comparison rather than by reading the three lines and being satisfied."""
    messages = [
        _mention_resolution_summary(*_ZERO_ITEMS),
        _mention_resolution_summary(*_ALL_NULL_NAMED),
        _mention_resolution_summary(*_SOME_IDS_ABSENT),
    ]
    assert all(messages), messages
    assert len(set(messages)) == 3, messages
    for left in range(len(messages)):
        for right in range(left + 1, len(messages)):
            assert messages[left] != messages[right], (messages[left], messages[right])


def test_ac2_the_case_that_names_a_FIXABLE_cause_is_the_one_that_says_so():
    """AC2's point, not just its letter: the three lines differ *usefully*. Only the
    null-named line names a grant an administrator can make; the absent-id line names a
    console range instead, because pointing someone at a scope they already have is how the
    five days were spent."""
    null_named = _mention_resolution_summary(*_ALL_NULL_NAMED)
    absent = _mention_resolution_summary(*_SOME_IDS_ABSENT)
    zero = _mention_resolution_summary(*_ZERO_ITEMS)

    assert "field" in null_named.lower() and "scope" in null_named.lower()
    for other in (absent, zero):
        assert "field" not in other.lower(), other

    for other in (absent, zero):
        assert "range" in other.lower(), other


# --------------------------------------------------------------------------- #
# AC1 — the null-names line names the FIELD-SCOPE CLASS, not a literal scope.  #
# --------------------------------------------------------------------------- #

def test_ac1_the_null_names_line_names_the_field_scope_CLASS():
    """AC1: it says a **user-base field scope** is missing — the class a reader needs in order
    to act — and it says that a name-less user is that signature rather than a missing user,
    which is the inference nobody made for five days."""
    message = _mention_resolution_summary(*_ALL_NULL_NAMED)
    lowered = message.lower()
    assert "user-base field scope" in lowered, message
    assert "field" in lowered and "scope" in lowered
    assert "raw @open_id" in message, "the line must say what those mentions render as"


def test_ac1_the_line_does_NOT_hardcode_a_scope_STRING():
    """AC1, explicit: a literal scope name would rot the moment Lark renames one, and the
    class is what a reader needs anyway. The literal belongs where Lark itself supplies it —
    in the error body the permission-denied path already quotes verbatim."""
    for shape in (_ZERO_ITEMS, _ALL_NULL_NAMED, _SOME_IDS_ABSENT):
        message = _mention_resolution_summary(*shape)
        assert "contact:user.base" not in message, message
        assert "contact:contact.base" not in message, message
        assert ":readonly" not in message, message


def test_ac1_no_line_leaks_a_user_id_or_a_credential(caplog):
    """The amplifier: the line names a **class** and a **count**. An id would make it
    per-user (and chatty); a credential would make it a leak."""
    ids = ["ou_secret_alpha", "ou_secret_beta"]

    def batch(req):
        return _contact_resp(items=[_user(i) for i in ids])

    out, lines = _resolve(ids, batch, caplog)
    assert out == {}
    assert len(lines) == 1
    message = lines[0].message
    for identifier in ids:
        assert identifier not in message, message
    for secretish in ("app_id", "app_secret", "LARK_", "token"):
        assert secretish not in message, (secretish, message)


# --------------------------------------------------------------------------- #
# AC4 — five shapes, and the partial case is its own case.                     #
# --------------------------------------------------------------------------- #

def test_ac4_shape_1_all_resolved_stays_SILENT(caplog):
    """The common path emits nothing at all. A resolver that narrated its successes would
    train people to skip its lines, which is how the loud paths came to be ignored."""
    def batch(req):
        return _contact_resp(items=[_user("ou_1", name="Ada"), _user("ou_2", name="Bo")])

    out, lines = _resolve(["ou_1", "ou_2"], batch, caplog)
    assert out == {"ou_1": "Ada", "ou_2": "Bo"}
    assert lines == [], [r.message for r in lines]
    assert _mention_resolution_summary(("ou_1", "ou_2"), ("ou_1", "ou_2"), ("ou_1", "ou_2")) is None


def test_ac4_shape_2_all_null_named_logs_ONE_line(caplog):
    """The path that was silent and pointed at a fixable cause."""
    def batch(req):
        return _contact_resp(items=[_user("ou_1"), _user("ou_2")])

    out, lines = _resolve(["ou_1", "ou_2"], batch, caplog)
    assert out == {}
    assert len(lines) == 1, [r.message for r in lines]
    assert "user-base field scope" in lines[0].message.lower()


def test_ac4_shape_3_MIXED_uses_the_names_it_got_and_counts_the_rest(caplog):
    """AC4: the partial case is its own case — the resolved names are still used, and the
    line says **how many** were unresolvable rather than implying the whole run failed."""
    def batch(req):
        return _contact_resp(items=[_user("ou_1", name="Ada"), _user("ou_2")])

    out, lines = _resolve(["ou_1", "ou_2"], batch, caplog)
    assert out == {"ou_1": "Ada"}, "a partial result must still rewrite what it resolved"
    assert len(lines) == 1
    message = lines[0].message
    assert "1 of the 2" in message, message
    assert "user-base field scope" in message.lower()


def test_ac4_shape_4_zero_items_logs_its_OWN_line(caplog):
    """The response that used to be indistinguishable from the two above."""
    def batch(req):
        return _contact_resp(items=[])

    out, lines = _resolve(["ou_1", "ou_2"], batch, caplog)
    assert out == {}
    assert len(lines) == 1
    assert lines[0].message == _wrap(_mention_resolution_summary(*_ZERO_ITEMS))


def test_ac4_shape_5_an_id_ABSENT_from_the_response_is_reported(caplog):
    """The fifth shape, found from the other side: one of two ids — in practice the project's
    own bot ``open_id``, a real id that legitimately does not resolve — comes back simply
    **absent**, with no way to tell "no such user" from "outside the contacts range". Now
    there is."""
    def batch(req):
        return _contact_resp(items=[_user("ou_1", name="Ada")])

    out, lines = _resolve(["ou_1", "ou_bot"], batch, caplog)
    assert out == {"ou_1": "Ada"}
    assert len(lines) == 1
    message = lines[0].message
    assert "1 of the 2" in message, message
    assert "range" in message.lower(), message
    assert "field" not in message.lower(), (
        "an absent id is not the field-scope signature — saying so is the wrong diagnosis "
        "that cost the five days")


def test_ac4_both_at_once_reports_both_rather_than_picking_one(caplog):
    """A response that is null-named **and** short of ids is a real shape, and a line that
    reported only one of the two would send a reader to fix half the problem."""
    def batch(req):
        return _contact_resp(items=[_user("ou_1")])

    out, lines = _resolve(["ou_1", "ou_gone"], batch, caplog)
    assert out == {}
    assert len(lines) == 1
    lowered = lines[0].message.lower()
    assert "field" in lowered and "range" in lowered, lines[0].message


# --------------------------------------------------------------------------- #
# AC3 — once per RUN, not per user and not per chunk.                          #
# --------------------------------------------------------------------------- #

def test_ac3_many_null_named_ids_still_log_exactly_ONE_line(caplog):
    """AC3: a document with many mentions must not make the resolver chatty. 120 null-named
    ids span three chunks and produce **one** line."""
    ids = [f"ou_{n}" for n in range(120)]

    def batch(req):
        return _contact_resp(items=[_user(i) for i in ids[:50]])

    out, lines = _resolve(ids, batch, caplog)
    assert out == {}
    assert len(lines) == 1, [r.message for r in lines]


def test_ac3_a_second_chunk_that_is_null_named_is_not_SWALLOWED(caplog):
    """AC3, the case the negative-cache discipline could have eaten: the **first** chunk
    resolves cleanly and only the **second** is null-named. A per-chunk decision that stopped
    at the first success would emit nothing at all."""
    first = [f"ou_a{n}" for n in range(50)]
    second = [f"ou_b{n}" for n in range(10)]
    seen = []

    def batch(req):
        chunk = list(req.user_ids) if hasattr(req, "user_ids") else None
        seen.append(chunk)
        if len(seen) == 1:
            return _contact_resp(items=[_user(i, name=f"N{n}") for n, i in enumerate(first)])
        return _contact_resp(items=[_user(i) for i in second])

    out, lines = _resolve(first + second, batch, caplog)
    assert len(out) == 50, "the first chunk's names are still used"
    assert len(lines) == 1, [r.message for r in lines]
    assert "10 of the 60" in lines[0].message, lines[0].message


def test_ac3_the_summary_does_not_fire_on_top_of_a_loud_path(caplog):
    """AC3: a permission error already logs the line that names the cause, and it returns
    early. Adding a summary on top would make one failure look like two."""
    def batch(req):
        return _contact_resp(success=False, code=99991672, msg="Permission denied: ...")

    out, lines = _resolve(["ou_1", "ou_2"], batch, caplog)
    assert out == {}
    assert len(lines) == 1, [r.message for r in lines]
    assert "denied" in lines[0].message.lower()


def test_ac3_a_transport_failure_also_stays_ONE_line(caplog):
    def batch(req):
        raise RuntimeError("socket closed")

    out, lines = _resolve(["ou_1"], batch, caplog)
    assert out == {}
    assert len(lines) == 1
    assert "unavailable" in lines[0].message.lower()


# --------------------------------------------------------------------------- #
# The amplifier's remaining arms.                                             #
# --------------------------------------------------------------------------- #

def test_an_empty_string_name_counts_as_UNUSABLE_and_is_pinned_as_such(caplog):
    """Decided and pinned: ``name=""`` is not a usable display name. It is falsy, so the
    existing preference chain already skips it — substituting an empty string would render
    ``@`` with nothing after it, which is worse than the raw id. Because it is unusable, it is
    also **disclosed**, exactly as a null is."""
    def batch(req):
        return _contact_resp(items=[_user("ou_1", name="", en_name="", nickname="")])

    out, lines = _resolve(["ou_1"], batch, caplog)
    assert out == {}
    assert len(lines) == 1
    assert "user-base field scope" in lines[0].message.lower()


def test_the_new_line_is_INFO_matching_the_two_that_were_already_there(caplog):
    """The amplifier: info, so this does not become a warning that trains people to ignore
    warnings. The two existing degrade lines are info for the same reason."""
    def batch(req):
        return _contact_resp(items=[_user("ou_1")])

    with caplog.at_level(logging.DEBUG, logger="larkdocio"):
        _client_with_batch(batch).batch_get_user_names(["ou_1"])
    records = [r for r in caplog.records if r.name == "larkdocio"]
    assert [r.levelno for r in records] == [logging.INFO], [
        (r.levelname, r.message) for r in records]


def test_the_resolvers_return_shape_is_unchanged(caplog):
    """AC5: graceful degrade is preserved exactly — a dict of what resolved, nothing raised,
    and an unresolved id simply absent from it (which is what makes the caller render the raw
    id). The line is a log line; it is not output."""
    def batch(req):
        return _contact_resp(items=[_user("ou_1", name="Ada"), _user("ou_2")])

    out, _lines = _resolve(["ou_1", "ou_2"], batch, caplog)
    assert isinstance(out, dict)
    assert out == {"ou_1": "Ada"}
    assert "ou_2" not in out


def test_no_ids_still_makes_no_call_and_no_line(caplog):
    """The empty-input short circuit is untouched: no call, and nothing to disclose."""
    def batch(req):  # pragma: no cover - must not be called
        raise AssertionError("no call may be made for an empty id list")

    out, lines = _resolve([], batch, caplog)
    assert out == {}
    assert lines == []


# --------------------------------------------------------------------------- #
# AC6 / AC7 — the docstring and the guards.                                   #
# --------------------------------------------------------------------------- #

def test_ac6_the_docstring_no_longer_describes_the_silence():
    """AC6: the code and its documentation must agree. The docstring used to record the
    omission as silent — "a user with none usable is omitted (nothing to substitute)" — which
    is how the silence read as a decision rather than a gap."""
    doc = Client.batch_get_user_names.__doc__
    assert doc
    flat = " ".join(doc.split()).lower()
    assert "omitted" in flat, "the omission itself is still the behavior"
    assert "disclose" in flat, (
        "the docstring must say the omission is now disclosed, not merely performed")
    assert "field" in flat and "scope" in flat, (
        "the docstring must name what the null-named case points at")


def test_ac7_the_new_line_is_dialect_free():
    """AC7: an emitted message is consumer-reaching text, so it is held to the shipped
    vocabulary — no issue id, no decision letter, no internal role."""
    for shape in (_ZERO_ITEMS, _ALL_NULL_NAMED, _SOME_IDS_ABSENT, _MIXED):
        message = _mention_resolution_summary(*shape)
        assert consumer_text.dialect_hits(message) == [], (shape, message)


def test_ac7_the_new_line_carries_no_preservation_VERB():
    """AC7: the comment-anchor reassurance guard watches for preservation verbs. Its scope
    predicate is the docx **write** surface (or text naming the run-rebuild function), so a
    read-path log line is outside it structurally — but the register is house-wide, and this
    line reports a gap rather than reassuring anyone, so it is asserted verb-free anyway."""
    for shape in (_ZERO_ITEMS, _ALL_NULL_NAMED, _SOME_IDS_ABSENT, _MIXED):
        lowered = _mention_resolution_summary(*shape).lower()
        for verb in ("preserved", "never dropped", "nothing is lost", "survives"):
            assert verb not in lowered, (shape, verb)


def test_ac7_the_read_path_line_is_outside_the_anchor_claim_SCOPE():
    """AC7 verbatim ("check whether the anchor-token census applies to read/ strings" rather
    than assuming it does not) — checked, and recorded as a test so the answer is not
    re-derived. The census keys on references to the comment-anchor field; the reassurance
    scope predicate keys on the docx write surface. A read-path resolver line reaches
    neither, and this asserts that rather than trusting it."""
    import test_comment_anchor_claim_guard as guard

    surfaces = guard.preservation_claim_surfaces()
    assert not any("read/client" in label for label in surfaces), sorted(surfaces)
    for shape in (_ALL_NULL_NAMED, _SOME_IDS_ABSENT):
        assert "comment_ids" not in _mention_resolution_summary(*shape)


def _wrap(message):
    """The message as the logger emits it (no decoration today — pinned so a future prefix
    change cannot silently break the equality assertions above)."""
    return message


# --------------------------------------------------------------------------- #
# LD-210 AC6 — the invariant becomes SET-based. THE THREE PROBES.              #
# --------------------------------------------------------------------------- #
#
# LD-184's own QA recorded the residual: the invariant was COUNT-based (requested vs returned vs
# named), so a set difference was not expressible and three shapes came out wrong — one of them
# the very silence class this module exists to remove.
#
# These are the three probes, written against the PUBLIC path rather than the helper, because the
# silence that mattered was the one a caller met.

def test_ac6_probe_P1_an_UNREQUESTED_id_in_the_answer_no_longer_MASKS_an_absent_one(caplog):
    """P1, verbatim from the review: *"a response carrying an id that was NOT requested masks a
    genuinely absent one and goes SILENT (ask [A,B], answer [A,C] → resolved has 2 entries,
    summary None) — the one silence class this issue exists to remove, surviving in a shape the
    real API should never produce."*

    Counting cannot see it: two asked, two returned, two named. ``set(ids) - set(resolved)`` can.
    """
    def batch(req):
        return _contact_resp(items=[_user("ou_a", name="A"), _user("ou_c", name="C")])

    out, lines = _resolve(["ou_a", "ou_b"], batch, caplog)
    assert out == {"ou_a": "A", "ou_c": "C"}, "the substitution map itself is unchanged"
    assert len(lines) == 1, [record.message for record in lines]
    message = lines[0].message
    assert "did not come back" in message, message
    assert "range" in message.lower(), "an absent id points at the contacts data range"
    assert "field" not in message.lower(), (
        "nothing came back name-less here, so the field-scope class must not be named"
    )


def test_ac6_probe_P2_DUPLICATE_input_ids_no_longer_over_count_absence(caplog):
    """P2: *"duplicate input ids over-count 'absent'."* Counting says two were asked about and
    one came back; the set says the one id asked about resolved. The dedup precondition is
    stated in the docstring and honoured by both call sites, so this was never observed — which
    is exactly why it must not be the thing keeping the invariant honest."""
    def batch(req):
        return _contact_resp(items=[_user("ou_a", name="A")])

    out, lines = _resolve(["ou_a", "ou_a"], batch, caplog)
    assert out == {"ou_a": "A"}
    assert lines == [], [record.message for record in lines]


def test_ac6_probe_P3_a_record_with_NO_open_id_is_not_reported_as_absent(caplog):
    """P3: *"an item with no ``open_id`` is reported as absent."* The directory answered — the
    record simply cannot be matched to the id that asked for it — so both "returned no user at
    all" and the contacts-data-range diagnosis are false. Getting that wrong is the
    wrong-but-confident diagnosis this whole line exists to stop."""
    def batch(req):
        return _contact_resp(items=[_user(None, name="A")])

    out, lines = _resolve(["ou_a"], batch, caplog)
    assert out == {}
    assert len(lines) == 1, [record.message for record in lines]
    message = lines[0].message
    assert "returned no user at all" not in message, message
    assert "range" not in message.lower(), (
        "a record that came back without an open_id is not evidence of a contacts-range gap"
    )
    assert "open_id" in message, "the line must say WHAT came back unusable"


def test_ac6_probe_P3_an_idless_record_does_not_make_a_SIBLING_id_look_absent(caplog):
    """P3's mixed shape: one good record, one with no ``open_id``. The unmatched record could be
    the id that appears to be missing, so absence cannot be claimed for it — and claiming it
    would send a reader to the console setting for a payload problem."""
    def batch(req):
        return _contact_resp(items=[_user("ou_a", name="A"), _user(None, name="B")])

    out, lines = _resolve(["ou_a", "ou_b"], batch, caplog)
    assert out == {"ou_a": "A"}
    assert len(lines) == 1, [record.message for record in lines]
    message = lines[0].message
    assert "did not come back at all" not in message, message
    assert "range" not in message.lower(), message


def test_ac6_the_three_LD184_cases_are_STILL_pairwise_distinguishable(caplog):
    """AC6's carve-out condition, driven end to end rather than through the helper: LD-184's
    whole point was that *"zero users returned"*, *"users returned with every name field null"*
    and *"ids absent from the response"* must not collapse. Widening WHEN the line fires must not
    re-collapse WHAT it says."""
    shapes = {
        "zero returned": [],
        "all null-named": [_user("ou_a"), _user("ou_b")],
        "one absent": [_user("ou_a", name="A")],
    }
    messages = {}
    for label, items in shapes.items():
        caplog.clear()
        _out, lines = _resolve(["ou_a", "ou_b"], (lambda i: lambda req: _contact_resp(items=i))(items), caplog)
        assert len(lines) == 1, (label, [record.message for record in lines])
        messages[label] = lines[0].message
    assert len(set(messages.values())) == 3, messages
    assert "field" in messages["all null-named"].lower()
    assert "field" not in messages["one absent"].lower()
    assert "field" not in messages["zero returned"].lower()


def test_ac6_the_line_still_fires_AT_MOST_ONCE_per_run(caplog):
    """AC6's carve-out: the widening moves the CONDITION, not the volume. Two chunks, both
    short, one line."""
    calls = []

    def batch(req):
        calls.append(req)
        return _contact_resp(items=[])

    ids = [f"ou_{index}" for index in range(120)]   # more than one chunk
    _out, lines = _resolve(ids, batch, caplog)
    assert len(calls) > 1, "the probe must span more than one chunk to be worth anything"
    assert len(lines) == 1, [record.message for record in lines]
