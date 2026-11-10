"""LD-255 — the Base WRITE client, its own op registry, and the write vocabulary.

Every test here is offline. The fixtures are the **committed probe captures**
(`tests/captures/base-study/captures/`) round-tripped through the pinned SDK's own deserializer, the same
way `tests/test_base_client.py` does for the read half, so an API drift reddens **at
deserialization** rather than travelling on as a plausible-looking `None`.

**The discipline this file exists to enforce (R12).** `records/search` treats an unrecognized
body key exactly like the bogus control `{"zzz": 1}` (`p1-q3-01`), and `page_size` in the body
is silently ignored while in the query string it works (`p1-q1-01`). So **a test that a
parameter is sent is not a test that it works.** Every parameter the write client ships is
pinned by an assertion that the response **differs** from the parameter-free control, measured
against an R12 server model built from those captures — and a deliberate-defect check moves one
parameter to the wrong place and proves the discipline reddens.

**AC2b, the trap.** `base_ops.read_only()` is a shipped claim asserted by three landed test
files, two of them live gates. The write descriptors therefore live in **their own registry**
(`larkdocio.base.write_ops.WRITE_OPS`), and the three landed assertions are pinned here
verbatim so this story cannot quietly edit them.
"""
import ast
import inspect
import io
import json
import re
import tokenize
from pathlib import Path

import pytest
from lark_oapi.api.bitable.v1 import (
    AppTableRecord,
    BatchCreateAppTableRecordResponse,
    BatchDeleteAppTableRecordRequestBody,
    BatchDeleteAppTableRecordResponse,
    BatchUpdateAppTableRecordResponse,
    CreateAppTableRecordResponse,
    DeleteAppTableRecordResponse,
    UpdateAppTableRecordResponse,
)
from lark_oapi.core.json import JSON

from larkdocio import permissions as perm
from larkdocio.base import cells
from larkdocio.base import errors as base_errors
from larkdocio.base import ops as base_ops
from larkdocio.base import write_client as base_write_client
from larkdocio.base import write_ops as base_write_ops
from larkdocio.base import write_vocabulary
from larkdocio.base.write_client import BaseWriteClient
from larkdocio.errors import LarkConfigError, LarkPermissionError
import private_tree  # noqa: E402  (LD-685)

_REPO = Path(__file__).resolve().parent.parent
_CAPTURES = _REPO / "tests" / "captures" / "base-study" / "captures"
_SRC = _REPO / "src" / "larkdocio"
_BASE_PKG = _SRC / "base"

#: The Base modules that make up the WRITE half. `tests/test_base_client.py` scans the READ
#: half; between them they must cover the package with no module in neither.
WRITE_MODULE_NAMES = ("media.py", "write_client.py", "write_ops.py",
                      "write_vocabulary.py")


# --------------------------------------------------------------------------- #
# Fixtures: the committed captures, through the SDK deserializer.              #
# --------------------------------------------------------------------------- #

def capture(name):
    return json.loads((_CAPTURES / name).read_text(encoding="utf-8"))


def unmarshal(payload, cls):
    return JSON.unmarshal(json.dumps(payload), cls)


def value_write_steps():
    """The nine live steps of `p1-q6-01`, keyed by the probe's own note prefix."""
    return {step["_note"].split(" :: ")[0]: step
            for step in capture("p1-q6-01-value-writes.json")["steps"]}


def create_echo():
    return unmarshal(capture("06-02-record-create-echo.json")["response"],
                     CreateAppTableRecordResponse)


def batch_create_echo():
    return unmarshal(capture("05-06-records-batch-create.json")["response"],
                     BatchCreateAppTableRecordResponse)


def destructive():
    return capture("06-06-destructive-ops.json")["response"]["data"]


class _Leg:
    """A bare attribute holder standing in for one SDK resource namespace."""


class _Recorder:
    """One SDK resource method: records the request it was handed, hands back the next canned
    response (repeating the last one once the script runs out)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, *args, **kwargs):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("the fake SDK was called with no canned response")
        index = min(len(self.requests) - 1, len(self.responses) - 1)
        return self.responses[index]


class _Forbidden:
    """A leg the shipped write client must never call."""

    def __init__(self, why):
        self.why = why

    def __call__(self, *args, **kwargs):
        raise AssertionError(self.why)


def fake_sdk(*, create=(), update=(), delete=(), batch_create=(), batch_update=(),
             batch_delete=()):
    sdk = _Leg()
    sdk.bitable = _Leg()
    sdk.bitable.v1 = v1 = _Leg()
    v1.app_table_record = rec = _Leg()
    rec.create = _Recorder(create)
    rec.update = _Recorder(update)
    rec.delete = _Recorder(delete)
    rec.batch_create = _Recorder(batch_create)
    rec.batch_update = _Recorder(batch_update)
    rec.batch_delete = _Recorder(batch_delete)
    # The record READS belong to the read client. A write client that reached for one would be
    # doing the reader's job on the write credential pair.
    rec.search = _Forbidden("the record read is the READ client's, on the read pair")
    rec.list = _Forbidden("the legacy record list is not this client's")
    rec.get = _Forbidden("the point read is not this client's")
    rec.batch_get = _Forbidden("batch_get is not this client's")
    # No schema write in this rung: no field, table or view leg is even wired.
    v1.app = _Forbidden("Base create/copy is not in this rung")
    v1.app_table = _Forbidden("no table write in this rung")
    v1.app_table_field = _Forbidden("no field write in this rung")
    v1.app_table_view = _Forbidden("no view write in this rung")
    return sdk


class _CountingLimiter:
    """Stands in for the shared `RateLimiter` and counts acquisitions."""

    def __init__(self):
        self.acquisitions = 0

    def acquire(self):
        self.acquisitions += 1


def client(**legs):
    return BaseWriteClient("id", "secret", sdk_client=fake_sdk(**legs),
                           rate_limiter=_CountingLimiter())


def write_source():
    """Every shipped Base WRITE module's source, concatenated."""
    return "\n".join((_BASE_PKG / name).read_text(encoding="utf-8")
                     for name in sorted(WRITE_MODULE_NAMES))


def write_code():
    """The WRITE modules' source with every string literal and comment removed.

    The scans below ask *"does any CODE PATH do X"*, and prose that explains why the code
    deliberately does **not** do X would otherwise trip them.
    """
    out = []
    for name in sorted(WRITE_MODULE_NAMES):
        text = (_BASE_PKG / name).read_text(encoding="utf-8")
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type not in (tokenize.STRING, tokenize.COMMENT):
                out.append(token.string)
    return "\n".join(out)


#: A realistic Lark scope-denial body.
DENIAL_BODY = {
    "code": 99991672,
    "msg": "Access denied. The app does not hold the required permission.",
    "error": {
        "permission_violations": [{"type": "TenantAccessToken", "subject": "bitable:app"}],
        "helps": [{"description": "grant it", "url": "https://open.larksuite.com/app/x/auth"}],
    },
}


# --------------------------------------------------------------------------- #
# AC1 — WRITE credentials only, and the aliasing rider is honored.              #
# --------------------------------------------------------------------------- #

def test_ac1_the_write_path_resolves_WRITE_and_never_consults_READ(monkeypatch):
    monkeypatch.setenv("LARK_READ_APP_ID", "read-app")
    monkeypatch.setenv("LARK_READ_APP_SECRET", "read-secret")
    monkeypatch.setenv("LARK_WRITE_APP_ID", "write-app")
    monkeypatch.setenv("LARK_WRITE_APP_SECRET", "write-secret")

    from larkdocio.common import auth

    def explode(*args, **kwargs):
        raise AssertionError("the Base write path consulted the READ credential pair")

    monkeypatch.setattr(auth, "get_read_credentials", explode)
    monkeypatch.setattr(base_write_client, "get_write_credentials",
                        lambda: ("write-app", "write-secret"))

    captured = {}

    class _Probe(BaseWriteClient):
        def __init__(self, app_id, app_secret, domain="larksuite.com", **kwargs):
            captured["pair"] = (app_id, app_secret)
            super().__init__(app_id, app_secret, domain, sdk_client=fake_sdk(), **kwargs)

    _Probe.from_write_credentials()
    assert captured["pair"] == ("write-app", "write-secret")


def test_ac1_no_base_WRITE_module_NAMES_a_read_credential():
    source = write_code()
    assert "LARK_READ_APP" not in source
    assert "get_read_credentials" not in source


def test_ac1_missing_write_credentials_is_a_typed_config_error(monkeypatch):
    monkeypatch.setattr(base_write_client, "get_write_credentials", lambda: ("", ""))
    with pytest.raises(LarkConfigError):
        BaseWriteClient.from_write_credentials()
    with pytest.raises(LarkConfigError):
        BaseWriteClient("", "")


def test_ac1_the_credential_env_named_on_a_denial_is_the_WRITE_pair():
    from larkdocio.common.auth import WRITE_ENV

    with pytest.raises(LarkPermissionError) as exc:
        base_errors.raise_for_base_code(DENIAL_BODY, context="write a record",
                                        credential_env=WRITE_ENV)
    assert exc.value.denial.credential_env == tuple(WRITE_ENV)
    assert not any("READ" in name for name in exc.value.denial.credential_env)


def test_ac1_the_shipped_write_path_REFUSES_through_the_taxonomy_on_the_write_pair():
    """Not the helper in isolation — the client's own refusal seam, and the denial it
    produces names the WRITE pair rather than the read one."""
    from larkdocio.errors import LarkAPIError

    c = client(delete=[unmarshal(DENIAL_BODY, DeleteAppTableRecordResponse)])
    with pytest.raises(LarkPermissionError) as exc:
        c.delete_record("app", "tbl", "rec")
    assert isinstance(exc.value, LarkAPIError)
    assert not any("READ" in name for name in exc.value.denial.credential_env)
    assert any("WRITE" in name for name in exc.value.denial.credential_env)


def test_ac1_the_docstring_refuses_to_cite_a_same_tenant_probe_as_scope_separation():
    """On this tenant the two pairs are the same app with byte-identical secrets, so an
    isolation test passing here proves nothing about scopes. The module says so."""
    assert "alias" in base_write_client.__doc__.lower()


# --------------------------------------------------------------------------- #
# AC2 — the op registry carries an EXPLICIT `mutates`, and every op is True.     #
# --------------------------------------------------------------------------- #

def test_ac2_mutates_has_NO_DEFAULT_so_a_write_descriptor_cannot_omit_it():
    field = base_write_ops.BaseWriteOpDescriptor.__dataclass_fields__["mutates"]
    import dataclasses

    assert field.default is dataclasses.MISSING
    assert field.default_factory is dataclasses.MISSING


def test_ac2_every_op_this_story_ships_declares_mutates_TRUE():
    assert base_write_ops.WRITE_OPS, "the write registry is empty"
    assert all(desc.mutates is True for desc in base_write_ops.WRITE_OPS)
    assert base_write_ops.all_mutate() is True


def test_ac2_the_flag_is_NOT_derived_from_the_verb_and_the_write_registry_proves_it():
    """Three of the six write families are `POST` — the same verb the pinned record READ
    uses. A verb-derived flag would make `mutates` unanswerable in both directions."""
    verbs = {desc.http_method for desc in base_write_ops.WRITE_OPS}
    assert verbs == {"POST", "PUT", "DELETE"}
    read_verbs = {desc.http_method for desc in base_ops.OPS}
    assert "POST" in verbs and "POST" in read_verbs


def test_ac2_the_declared_verb_and_endpoint_MATCH_the_sdk_request_class():
    for desc in base_write_ops.WRITE_OPS:
        built = desc.request_cls.builder().build()
        assert desc.endpoint == built.uri, desc.name
        assert desc.http_method == built.http_method.name, desc.name


def test_ac2_every_write_descriptor_names_a_real_client_method():
    for desc in base_write_ops.WRITE_OPS:
        assert callable(base_write_ops.impl_of(desc)), desc.name


def test_ac2_the_write_registry_covers_exactly_the_six_record_write_families():
    assert {desc.name for desc in base_write_ops.WRITE_OPS} == {
        "create_record", "update_record", "delete_record",
        "batch_create_records", "batch_update_records", "batch_delete_records",
    }


@private_tree.citations
def test_ac2_every_write_descriptor_carries_evidence_that_EXISTS():
    for desc in base_write_ops.WRITE_OPS:
        assert desc.evidence, desc.name
        for path in re.findall(r"((?:dev|src|tests)/[\w./\-]+)", desc.evidence):
            assert (_REPO / path).exists(), (desc.name, path)


def test_ac2_every_write_op_is_a_RECORD_op_no_schema_write_in_this_rung():
    for desc in base_write_ops.WRITE_OPS:
        assert "/records" in desc.endpoint, desc.name
        assert "/fields" not in desc.endpoint and "/views" not in desc.endpoint


# --------------------------------------------------------------------------- #
# AC2b — L1's read-only proof survives, and the three landed assertions are      #
#        pinned VERBATIM so this story cannot edit them.                        #
# --------------------------------------------------------------------------- #

def test_ac2b_the_read_registry_is_STILL_wholly_read_only():
    assert base_ops.read_only() is True
    assert all(desc.mutates is False for desc in base_ops.OPS)


def test_ac2b_the_two_registries_are_SEPARATELY_QUERYABLE_and_disjoint():
    read_names = {d.name for d in base_ops.OPS}
    write_names = {d.name for d in base_write_ops.WRITE_OPS}
    assert not (read_names & write_names)
    assert not any(d.mutates for d in base_ops.OPS)
    assert all(d.mutates for d in base_write_ops.WRITE_OPS)
    # And the write descriptors are NOT reachable through the read registry's accessor.
    for name in write_names:
        with pytest.raises(KeyError):
            base_ops.op(name)


@pytest.mark.parametrize("path,lineno,expected", [
    # LD-260 moved this one from 247 to 259, and LD-269 from 259 to 263 — the LINE moved
    # twice, the assertion did not. LD-269 added `batch_get_records` (a SECOND POST read,
    # `mutates: False`) to the read registry, which grew the comment above the pinned line by
    # four lines; the read-only claim it makes is untouched. The pinned TEXT below is
    # byte-identical, which is what this guard is actually about.
    # LD-370 moved the two live arms' lines again (45→49, 186→190) by overlaying the
    # `conformance` marker on their module-level ring mark — four lines above each pin, and
    # zero characters inside it. Same story as the two moves above: the LINE moved, the
    # assertion did not.
    # LD-685 moved the first pin again (263→264): a `private_tree` decorator landed above an
    # unrelated test earlier in that file. The line moved; the assertion did not.
    ("tests/test_base_client.py", 264, "assert base_ops.read_only() is True"),
    ("tests/test_live_base_read_arm.py", 49,
     "def test_the_registry_declares_the_whole_arm_read_only_BEFORE_it_calls_anything():"),
    ("tests/test_live_base_canary.py", 190,
     "def test_the_registry_declares_the_whole_gate_read_only_BEFORE_it_reads_anything():"),
])
def test_ac2b_the_three_landed_read_only_assertions_are_UNMODIFIED(path, lineno, expected):
    """Editing any of the three to accommodate the write registry is a FAIL, so the exact
    line is pinned here — including its line number, which is what the story was handed."""
    lines = (_REPO / path).read_text(encoding="utf-8").splitlines()
    assert lines[lineno - 1].strip() == expected, (path, lineno, lines[lineno - 1])


def test_ac2b_the_shipped_read_only_claim_is_still_TRUE_of_the_read_op_set():
    """`capabilities()` tells consumers every operation on the base-read surface declares
    `mutates=False`. That sentence is about the READ op set, and it stays true because the
    write descriptors never enter it."""
    assert base_ops.read_only() is True
    assert not any(d in base_ops.OPS for d in base_write_ops.WRITE_OPS)


# --------------------------------------------------------------------------- #
# AC2c — the non-writable pair set is authored HERE, once.                      #
# --------------------------------------------------------------------------- #

_EIGHT = (
    (19, "Lookup"), (20, "Formula"), (24, "Stage"),
    (1001, "CreatedTime"), (1002, "ModifiedTime"),
    (1003, "CreatedUser"), (1004, "ModifiedUser"), (1005, "AutoNumber"),
)


def test_ac2c_the_constant_is_EXACTLY_the_eight_computed_or_opaque_pairs():
    assert set(write_vocabulary.NON_WRITABLE_PAIRS) == set(_EIGHT)
    assert len(write_vocabulary.NON_WRITABLE_PAIRS) == 8


def test_ac2c_every_non_writable_pair_is_a_REAL_pair_in_the_landed_read_registry():
    """Cross-checked against `base/cells.py` so the write vocabulary and the read registry
    cannot disagree about what a pair even is."""
    for pair in write_vocabulary.NON_WRITABLE_PAIRS:
        assert pair in cells.PAIRS, pair


def test_ac2c_every_pair_carries_a_REASON_a_caller_can_act_on():
    for pair in write_vocabulary.NON_WRITABLE_PAIRS:
        reason = write_vocabulary.non_writable_reason(pair)
        assert reason and len(reason) > 30, pair


def test_ac2c_is_non_writable_answers_both_ways():
    assert write_vocabulary.is_non_writable((20, "Formula")) is True
    assert write_vocabulary.is_non_writable((1, "Text")) is False
    assert write_vocabulary.is_non_writable(("nonsense",)) is False


def test_ac2c_NO_SECOND_DEFINITION_of_the_pair_set_exists_in_src():
    """The `common/staleness.py` discipline: two later stories import this constant, so a
    second definition anywhere in `src/` would let them drift apart silently."""
    home = _BASE_PKG / "write_vocabulary.py"
    definers = [p for p in sorted(_SRC.rglob("*.py"))
                if re.search(r"^NON_WRITABLE_PAIRS\s*[:=]", p.read_text(encoding="utf-8"),
                             re.MULTILINE)]
    assert definers == [home], [str(p) for p in definers]


#: The modules allowed to name all eight, each for a reason that is checked below rather
#: than merely asserted here. ``cells.py`` is the READ renderer registry, which necessarily
#: names all eight and is held in agreement with the home constant by the cross-check above.
#: ``field_vocabulary.py`` is the FIELD-AUTHORING allow-list, and it names them **as two
#: different sets that cross**: six of the eight are in the server's authorable enum
#: (a formula, an auto-number and the four created/modified columns can be CREATED while
#: their cells can never be WRITTEN), and the other two are in its own excluded set. A word
#: count cannot tell that apart from a second definition, so the exemption is paid for by
#: :func:`test_ac2c_an_EXEMPT_module_still_proves_it_holds_no_second_definition`.
#: ``shape_docs.py`` is the third, and it is the ``cells.py`` case exactly: it authors one row
#: per pair the READ registry renders, so it necessarily names all eight, and it is held
#: bidirectionally against ``cells.PAIRS`` by ``test_base_shape_docs.py`` — which is the same
#: cross-check that pays for ``cells.py``. It also pays structurally, below: it holds the
#: writability answer nowhere, deriving it from the home constant's own registry at render time.
_EIGHT_NAME_EXEMPT = ("cells.py", "field_vocabulary.py", "shape_docs.py")


def test_ac2c_NO_OTHER_MODULE_gathers_the_eight_names_into_one_collection():
    """The other half: a module could re-derive the set without reusing the name."""
    home = _BASE_PKG / "write_vocabulary.py"
    exempt = {home} | {_BASE_PKG / name for name in _EIGHT_NAME_EXEMPT}
    names = {ui for _t, ui in _EIGHT}
    offenders = []
    for path in sorted(_SRC.rglob("*.py")):
        if path in exempt:
            continue
        words = set(re.findall(r"[A-Za-z]+", path.read_text(encoding="utf-8")))
        if names <= words:
            offenders.append(str(path.relative_to(_REPO)))
    assert not offenders, offenders


def test_ac2c_an_EXEMPT_module_still_proves_it_holds_no_second_definition():
    """The exemption is not a hole.

    ``cells.py`` pays for its exemption with the cross-check above, which holds the read
    registry and the home constant in agreement pair by pair. ``field_vocabulary.py`` has no
    such cross-check available — it is a *different* set — so it pays structurally instead:
    it must **import** the home constant rather than restate it, and no name it binds may be
    a literal collection carrying all eight ``ui_type``s. Checked on the parse tree, not by
    counting words, which is exactly what the word-count guard above cannot do.
    """
    import ast

    path = _BASE_PKG / "field_vocabulary.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "NON_WRITABLE_PAIRS" in source, "it has to be imported, not merely absent"
    assigned = {}
    for node in ast.walk(tree):
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        for target in targets:
            if isinstance(target, ast.Name):
                assigned[target.id] = node
    assert "NON_WRITABLE_PAIRS" not in assigned
    for bound, node in assigned.items():
        literals = {n.value for n in ast.walk(node)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        assert not {ui for _t, ui in _EIGHT} <= literals, bound


def test_ac2c_the_SHAPE_DOCS_exemption_is_paid_for_the_same_structural_way():
    """The projection module names all eight because it documents all 27 pairs — and it must
    not carry a second answer to *which* eight cannot be written.

    It binds no collection of the eight, and it reaches the writability answer through the home
    module's own tables (``NON_WRITABLE_REASONS`` for the reason, the encoder registry for the
    yes), so the set it renders is the set the library enforces.
    """
    import ast

    path = _BASE_PKG / "shape_docs.py"
    source = path.read_text(encoding="utf-8")
    assert "NON_WRITABLE_REASONS" in source, "it has to be imported, not restated"
    assert not re.search(r"^NON_WRITABLE_(PAIRS|REASONS)\s*[:=]", source, re.MULTILINE)
    for node in ast.walk(ast.parse(source)):
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            literals = {n.value for n in ast.walk(node)
                        if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            if {ui for _t, ui in _EIGHT} <= literals:
                # Naming all 27 pairs is the exemption itself; what a binding may not do is
                # pair those names with a writability verdict of its own.
                segment = ast.get_source_segment(source, node) or ""
                assert "writable" not in segment, target.id


# --------------------------------------------------------------------------- #
# AC3 — R12 by construction: every parameter pinned by an EFFECT assertion.      #
#                                                                              #
# The server model below is built from the captures: an unrecognized body key    #
# behaves identically to the bogus control, and a query-string parameter placed  #
# in the body is silently ignored. So "the response differs from the control"    #
# is the only assertion that proves a parameter was honoured.                    #
# --------------------------------------------------------------------------- #

class R12Server:
    """Lark's OBSERVED behavior, modelled: recognized body keys change the answer, and every
    other key — bogus or merely misplaced — behaves exactly like the parameter-free control.

    Evidence: `p1-q3-01` (the bogus key `{"zzz": 1}` and four plausible grouping keys all
    behave identically to `{}`) and `p1-q1-01` (`?page_size=2` returns 2 items; `{"page_size":
    2}` returns all 6). Both are recorded in this repository's captures.
    """

    #: What each write endpoint actually reads off the body, from the captures' own bodies.
    RECOGNIZED = {
        "create": ("fields",),
        "update": ("fields",),
        "batch_create": ("records",),
        "batch_update": ("records",),
        "batch_delete": ("records",),
    }

    def answer(self, op, body):
        """The response the model returns — a pure function of the RECOGNIZED keys only."""
        recognized = self.RECOGNIZED[op]
        seen = {k: v for k, v in (body or {}).items() if k in recognized}
        return json.dumps(seen, sort_keys=True, default=str)


def wire_body(request):
    """The JSON body an SDK request will actually put on the wire."""
    body = getattr(request, "request_body", None)
    if body is None:
        return {}
    return json.loads(JSON.marshal(body))


def sent_body(recorder, index=0):
    return wire_body(recorder.requests[index])


def test_ac3_the_module_docstring_RECORDS_the_discipline_and_why_it_exists():
    doc = base_write_client.__doc__
    assert "R12" in doc
    assert "silently" in doc.lower()
    assert "control" in doc.lower()


@pytest.mark.parametrize("op,call,leg", [
    ("create", lambda c: c.create_record("app", "tbl", {"Text": "x"}), "create"),
    ("update", lambda c: c.update_record("app", "tbl", "rec", {"Text": "x"}), "update"),
    ("batch_create", lambda c: c.batch_create_records("app", "tbl", [{"Text": "x"}]),
     "batch_create"),
    ("batch_update", lambda c: c.batch_update_records("app", "tbl", [("rec", {"Text": "x"})]),
     "batch_update"),
    ("batch_delete", lambda c: c.batch_delete_records("app", "tbl", ["rec"]), "batch_delete"),
])
def test_ac3_EVERY_body_parameter_CHANGED_THE_RESULT_versus_the_bare_control(op, call, leg):
    """The effect assertion, one per shipped body. The control is the same call with an empty
    body — exactly what the server answers when a key is silently ignored."""
    c = client(**{leg: [_canned(leg)]})
    call(c)
    body = sent_body(getattr(c._sdk.bitable.v1.app_table_record, leg))
    server = R12Server()
    assert server.answer(op, body) != server.answer(op, {}), (
        f"{op}: the shipped body is indistinguishable from the parameter-free control")


@pytest.mark.parametrize("op,wrong_body,indistinguishable_from", [
    # THE DELIBERATE DEFECT: `batch_get` keys its body `record_ids`; `batch_delete` keys its
    # own `records`. Sending the neighbouring family's key is a wrong-PLACE parameter — and the
    # answer collapses onto the parameter-free control, deleting nothing while reporting
    # success. This is the case a `code:0` assertion would pass and an effect assertion fails.
    ("batch_delete", {"record_ids": ["rec"]}, {}),
    # The named `page_size` trap, in the shape a write body could carry it: the misplaced key
    # contributes nothing, so the request is indistinguishable from the one without it.
    ("create", {"fields": {"Text": "x"}, "page_size": 2}, {"fields": {"Text": "x"}}),
])
def test_ac3_THE_DELIBERATE_DEFECT_a_wrong_place_parameter_REDDENS(
        op, wrong_body, indistinguishable_from):
    """Proof that the discipline BITES rather than merely being stated."""
    server = R12Server()
    assert server.answer(op, wrong_body) == server.answer(op, indistinguishable_from), (
        "a misplaced parameter must contribute nothing — that is what the server does")


def test_ac3_THE_DELIBERATE_DEFECT_makes_the_effect_assertion_FAIL():
    """The bite, made explicit: run the very assertion the shipped bodies pass against a
    wrong-place body, and it does not hold. The discipline is what catches this; `code:0`
    would not, because the server answers `code:0` to both."""
    server = R12Server()
    control = server.answer("batch_delete", {})
    shipped = server.answer("batch_delete", {"records": ["rec"]})
    defective = server.answer("batch_delete", {"record_ids": ["rec"]})
    assert shipped != control, "the shipped body passes the effect assertion"
    assert defective == control, "the wrong-place body fails it — which is the point"


def test_ac3_the_shipped_batch_delete_body_uses_RECORDS_not_record_ids():
    """The wrong-place trap, checked against the shipped code rather than the model."""
    c = client(batch_delete=[_canned("batch_delete")])
    c.batch_delete_records("app", "tbl", ["recA", "recB"])
    body = sent_body(c._sdk.bitable.v1.app_table_record.batch_delete)
    assert body == {"records": ["recA", "recB"]}
    assert "record_ids" not in body


def test_ac3_BY_CONSTRUCTION_every_body_is_a_typed_builder_never_a_hand_dict():
    code = write_code()
    assert "json.dumps" not in code and "request_body({" not in code
    c = client(create=[_canned("create")], batch_delete=[_canned("batch_delete")])
    c.create_record("app", "tbl", {"Text": "x"})
    c.batch_delete_records("app", "tbl", ["rec"])
    assert isinstance(
        c._sdk.bitable.v1.app_table_record.create.requests[0].request_body, AppTableRecord)
    assert isinstance(
        c._sdk.bitable.v1.app_table_record.batch_delete.requests[0].request_body,
        BatchDeleteAppTableRecordRequestBody)


def test_ac3_the_EXACT_wire_shape_of_every_parameter_is_pinned():
    """The complete inventory, so a parameter cannot be added without a test noticing.
    Nothing rides the query string at all, and no body carries a key beyond the one each
    endpoint recognises."""
    c = client(create=[_canned("create")], update=[_canned("update")],
               delete=[_canned("delete")], batch_create=[_canned("batch_create")],
               batch_update=[_canned("batch_update")], batch_delete=[_canned("batch_delete")])
    c.create_record("app", "tbl", {"Text": "x"})
    c.update_record("app", "tbl", "rec", {"Text": "y"})
    c.delete_record("app", "tbl", "rec")
    c.batch_create_records("app", "tbl", [{"Text": "x"}])
    c.batch_update_records("app", "tbl", [("rec", {"Text": "y"})])
    c.batch_delete_records("app", "tbl", ["rec"])

    rec = c._sdk.bitable.v1.app_table_record
    assert sent_body(rec.create) == {"fields": {"Text": "x"}}
    assert sent_body(rec.update) == {"fields": {"Text": "y"}}
    assert sent_body(rec.delete) == {}
    assert sent_body(rec.batch_create) == {"records": [{"fields": {"Text": "x"}}]}
    assert sent_body(rec.batch_update) == {
        "records": [{"record_id": "rec", "fields": {"Text": "y"}}]}
    assert sent_body(rec.batch_delete) == {"records": ["rec"]}
    for leg in ("create", "update", "delete", "batch_create", "batch_update", "batch_delete"):
        for request in getattr(rec, leg).requests:
            assert not (request.queries or []), (leg, request.queries)


def test_ac3_user_id_type_and_client_token_are_NOT_SENT():
    """Both are real SDK parameters. Neither ships: no test here could prove either changed
    anything, and an unprovable parameter does not ship."""
    c = client(create=[_canned("create")])
    c.create_record("app", "tbl", {"Text": "x"})
    request = c._sdk.bitable.v1.app_table_record.create.requests[0]
    assert not [q for q in (request.queries or []) if q[0] in
                ("user_id_type", "client_token", "ignore_consistency_check")]
    code = write_code()
    for parameter in ("user_id_type", "client_token", "ignore_consistency_check"):
        assert parameter not in code, parameter


def test_ac3_THE_BOGUS_KEY_CONTROL_ships_as_a_test():
    """`p1-q3-01`, live: the bogus key `{"zzz": 1}` and four plausible grouping keys all
    behave identically to `{}`. This is the recorded control the model is built on."""
    steps = capture("p1-q3-01-filter-sort.json")["steps"]
    notes = {step["_note"].split(" :: ")[0]: step["_note"] for step in steps}
    baseline = notes["no filter / no sort"].split(" :: ", 1)[1].split(" body=")[0]
    for control in ("bogus body key 'zzz' (baseline for silent-ignore)",
                    "body key 'group_by' (ignored-key control)"):
        observed = notes[control].split(" :: ", 1)[1].split(" body=")[0]
        assert observed == baseline, (control, observed, baseline)


def test_ac3_the_page_size_placement_anomaly_is_the_OTHER_half_of_the_evidence():
    steps = {s["_note"]: s for s in capture("p1-q1-01-pagination-anomaly.json")["steps"]}
    with_it = steps["page_size in the QUERY STRING"]["response"]["data"]["items"]
    without = steps["page_size in the BODY — the seat's anomaly reproduced?"][
        "response"]["data"]["items"]
    assert len(with_it) != len(without)


# --------------------------------------------------------------------------- #
# AC4 — the write error taxonomy.                                               #
# --------------------------------------------------------------------------- #

_AC4_CODES = (1002, 91402, 1254004, 1254041, 1254043, 1254069, 1254060, 1254001,
              99992402, 1255002, 1254301, 1254302, 1254036)


def test_ac4_the_write_vocabulary_is_EXACTLY_the_codes_the_packs_observed():
    assert set(base_errors.WRITE_ERROR_CODES) == set(_AC4_CODES)


@pytest.mark.parametrize("code", _AC4_CODES)
def test_ac4_every_write_code_maps_to_a_typed_entry_with_an_ACTIONABLE_message(code):
    note = base_errors.note_for(code)
    assert note is not None, code
    assert note.label, code
    assert len(note.meaning) > 60, (code, note.meaning)
    assert note.meaning.strip() != note.label.strip()


@private_tree.citations
@pytest.mark.parametrize("code", _AC4_CODES)
def test_ac4_every_write_code_carries_evidence_that_RESOLVES(code):
    note = base_errors.note_for(code)
    for path in re.findall(r"((?:dev|src|tests)/[\w./\-]+)", note.evidence):
        assert (_REPO / path).exists(), (code, path)


def test_ac4_1254301_and_1254302_are_a_FEATURE_GATE_and_advise_NO_scope():
    for code in base_errors.FEATURE_GATE_CODES:
        assert code in base_errors.WRITE_ERROR_CODES
        meaning = base_errors.note_for(code).meaning.lower()
        assert "scope" not in meaning
        assert "permission console" not in meaning


def test_ac4_99992402_is_NOT_OPAQUE_and_the_violations_reach_the_caller_verbatim():
    body = {
        "code": 99992402,
        "msg": "field validation failed",
        "error": {"field_violations": [
            {"field": "Stage", "value": "Nope",
             "description": "accepted values: Todo, Doing, Done"}]},
    }
    from larkdocio.errors import LarkAPIError

    with pytest.raises(LarkAPIError) as exc:
        base_errors.raise_for_base_code(body, context="write a record")
    assert exc.value.field_violations
    assert "Stage" in str(exc.value) and "Todo, Doing, Done" in str(exc.value)


def test_ac4_1254001_QUOTES_the_precise_server_path_it_names():
    """The typed body-shape error is NOT a bare refusal: `error.message` names the offending
    path exactly. Discarding it would turn an answerable refusal into a guess."""
    step = [s for s in capture("p1-q3-02-view-grouping.json")["steps"]
            if s["_lark_code"] == 1254001][0]
    body = step["response"]
    from larkdocio.errors import LarkAPIError

    with pytest.raises(LarkAPIError) as exc:
        base_errors.raise_for_base_code(body, context="write a record")
    assert "property.filter_info.conditions[0].value" in str(exc.value)


def test_ac4_the_server_detail_is_EMPTY_when_the_body_carries_none():
    assert base_errors.server_detail({"code": 1, "msg": "x"}) is None
    assert base_errors.server_detail({"code": 1, "msg": "x", "error": {}}) is None


def test_ac4_1255002_names_the_reversed_location_trap():
    meaning = base_errors.note_for(1255002).meaning.lower()
    assert "longitude" in meaning and "latitude" in meaning


def test_ac4_the_client_raises_the_taxonomy_on_a_failed_write():
    refusal = unmarshal({"code": 1254069, "msg": "AttachFieldConvFail"},
                        CreateAppTableRecordResponse)
    c = client(create=[refusal])
    from larkdocio.errors import LarkAPIError

    with pytest.raises(LarkAPIError) as exc:
        c.create_record("app", "tbl", {"Attachment": "nope"})
    assert exc.value.code == 1254069
    assert "file_token" in str(exc.value)


# --------------------------------------------------------------------------- #
# AC5 — be gentle: throttled by construction, limits documented not hunted.      #
# --------------------------------------------------------------------------- #

def test_ac5_the_throttle_is_applied_ON_THE_SHIPPED_WRITE_PATH_of_every_op():
    c = client(create=[_canned("create")], update=[_canned("update")],
               delete=[_canned("delete")], batch_create=[_canned("batch_create")],
               batch_update=[_canned("batch_update")], batch_delete=[_canned("batch_delete")])
    c.create_record("app", "tbl", {"Text": "x"})
    c.update_record("app", "tbl", "rec", {"Text": "y"})
    c.delete_record("app", "tbl", "rec")
    c.batch_create_records("app", "tbl", [{"Text": "x"}])
    c.batch_update_records("app", "tbl", [("rec", {"Text": "y"})])
    c.batch_delete_records("app", "tbl", ["rec"])
    assert c.api_calls == 6
    assert c.limiter.acquisitions == c.api_calls, (
        "every call passes the limiter; a leg that bypassed it would show here")


def test_ac5_the_default_pace_is_the_ONE_the_probe_packs_evidenced():
    assert base_write_client.BASE_WRITE_RATE_WINDOW_SECONDS == 60.0
    assert base_write_client.DEFAULT_MAX_WRITES_PER_WINDOW == 50
    spacing = (base_write_client.BASE_WRITE_RATE_WINDOW_SECONDS
               / base_write_client.DEFAULT_MAX_WRITES_PER_WINDOW)
    assert spacing >= 1.2


def test_ac5_a_real_client_gets_a_real_limiter_not_none():
    from larkdocio.common.transport import RateLimiter

    c = BaseWriteClient("id", "secret", sdk_client=fake_sdk())
    assert isinstance(c.limiter, RateLimiter)


def test_ac5_nothing_here_PROBES_a_rate_limit():
    code = write_code()
    assert "99991400" not in code, (
        "rate limits are documented from the packs' evidence, deliberately never probed; a "
        "retry-on-rate-limit loop here would be a probe by another name")


# --------------------------------------------------------------------------- #
# AC6 — the permission rows land in THIS change.                                 #
# --------------------------------------------------------------------------- #

def test_ac6_the_endpoints_are_DERIVED_from_the_client_code_not_hand_listed():
    derived = set()
    for desc in base_write_ops.WRITE_OPS:
        derived |= set(perm.endpoints_of(base_write_ops.impl_of(desc)))
    assert derived == {
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records",
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/:record_id",
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/batch_create",
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/batch_update",
        "/open-apis/bitable/v1/apps/:app_token/tables/:table_id/records/batch_delete",
    }, sorted(derived)


def test_ac6_every_endpoint_this_client_reaches_HAS_A_WRITE_ROW_in_the_scope_table():
    unmapped = []
    for desc in base_write_ops.WRITE_OPS:
        for endpoint in perm.endpoints_of(base_write_ops.impl_of(desc)):
            if perm._table_row(endpoint, "write") is None:
                unmapped.append((desc.name, endpoint))
    assert not unmapped, unmapped


def test_ac6_the_bitable_WRITE_row_carries_its_evidence_and_a_verification_label():
    rows = [row for row in perm.ENDPOINT_SCOPES
            if row[0].startswith("/open-apis/bitable/") and row[1] == "write"]
    assert len(rows) == 1, "the record-write families need exactly one write-mode row"
    _prefix, _mode, scopes, _reason = rows[0]
    assert scopes
    for scope in scopes:
        assert scope.verification in perm.VERIFICATION_LABELS
        assert len(scope.evidence) > 40
        assert scope.note


def test_ac6_the_derived_scope_for_every_write_op_is_NON_EMPTY_and_write_mode():
    for desc in base_write_ops.WRITE_OPS:
        endpoints = perm.endpoints_of(base_write_ops.impl_of(desc))
        scopes = perm.scopes_for_endpoints(endpoints, "write")
        assert scopes, desc.name
        assert all(s.established for s in scopes), desc.name


def test_ac6_the_write_row_does_NOT_widen_the_READ_surfaces_requirement():
    """The read families still resolve to the read row, unchanged: a write row must not
    become the answer for a read-mode question."""
    for desc in base_ops.OPS:
        for endpoint in perm.endpoints_of(base_ops.impl_of(desc)):
            row = perm._table_row(endpoint, "read")
            assert row is not None and row[1] == "read", (desc.name, endpoint)
            assert [s.scope for s in row[2]] == ["bitable:app:readonly"]


def test_ac6_the_write_modules_AUTHOR_no_scope_string():
    source = write_source()
    assert not re.findall(r"\b(?:bitable|drive|docx|sheets|contact):[a-z_.:]+", source), (
        "a scope requirement is authored in larkdocio.permissions and nowhere else")


def test_ac6_NO_SCOPE_IS_WIDENED_requested_or_escalated_anywhere_in_the_write_path():
    code = write_code()
    for forbidden in ("request_scope", "grant_scope", "escalate", "add_scope"):
        assert forbidden not in code, forbidden


# --------------------------------------------------------------------------- #
# AC7 — the offline ring over the committed captures, and the harness.          #
# --------------------------------------------------------------------------- #

def _canned(leg):
    """The canned response for one SDK leg, from a real capture wherever one exists."""
    if leg == "create":
        return create_echo()
    if leg == "update":
        step = value_write_steps()["PUT Email on probe record"]
        return unmarshal(step["response"], UpdateAppTableRecordResponse)
    if leg == "delete":
        return unmarshal(destructive()["delete_record"], DeleteAppTableRecordResponse)
    if leg == "batch_create":
        return batch_create_echo()
    if leg == "batch_update":
        return unmarshal({"code": 0, "msg": "success", "data": {"records": [
            {"record_id": "rec", "fields": {"Text": "y"}}]}},
            BatchUpdateAppTableRecordResponse)
    if leg == "batch_delete":
        step = value_write_steps()["batch_delete 3 probe records"]
        return unmarshal(step["response"], BatchDeleteAppTableRecordResponse)
    raise AssertionError(leg)


def test_ac7_the_create_echo_capture_round_trips_into_TYPED_objects():
    record = create_echo().data.record
    assert record.record_id == "recvrymubKYG8P"
    assert record.fields["Text"] == "THE ROW"


def test_ac7_the_WHOLE_write_client_runs_over_the_committed_captures():
    c = client(create=[create_echo()], batch_create=[batch_create_echo()],
               delete=[_canned("delete")], batch_delete=[_canned("batch_delete")],
               update=[_canned("update")], batch_update=[_canned("batch_update")])
    created = c.create_record("app", "tbl", {"Text": "THE ROW"})
    assert created.record_id == "recvrymubKYG8P"

    rows = c.batch_create_records("app", "tbl", [{"Text": "row-one"}, {"Text": "row-two"}])
    assert [r.fields["Text"] for r in rows] == ["row-one", "row-two"]

    updated = c.update_record("app", "tbl", "recvrktfSlDhV7", {"Email": "x@example.invalid"})
    assert updated.record_id

    assert c.delete_record("app", "tbl", "recvrymubKYG8P") is True
    assert c.batch_delete_records("app", "tbl", ["recvrktfSlDhV7"])


def test_ac7_a_deleted_record_REFETCHES_as_1254043_which_is_why_delete_returns_a_bool():
    """`06-06`, live: the delete answers `deleted: true` and the re-fetch answers
    `RecordIdNotFound`. Records are deleted permanently — there is no trash."""
    data = destructive()
    assert data["delete_record"]["data"]["deleted"] is True
    assert data["refetch_deleted_record"]["code"] == 1254043


def test_ac7_the_batch_delete_capture_confirms_the_RECORDS_key_on_the_wire():
    note = value_write_steps()["batch_delete 3 probe records"]["_note"]
    assert '"records"' in note and '"record_ids"' not in note


def test_ac7_the_disposable_harness_lives_at_its_FINAL_path():
    harness = _REPO / "tests" / "base_write_harness.py"
    assert harness.exists(), (
        "the minimal provisioner is born at the path the hardening story will keep")
    source = harness.read_text(encoding="utf-8")
    assert "larkdocio-DISPOSABLE-" in source
    assert "finally" in source


def test_ac7_the_harness_NEVER_names_a_non_disposable_target():
    """The load-bearing invariant: a token can only enter the harness through its own create.
    The read fixtures are never a write destination."""
    source = (_REPO / "tests" / "base_write_harness.py").read_text(encoding="utf-8")
    for env_name in ("LARKDOCIO_SCRATCH_BASE", "LARKDOCIO_CANARY_DOC",
                     "LARKDOCIO_BLOCKZOO_DOC"):
        assert env_name not in source, env_name


def test_ac7_the_harness_deletes_in_a_FINALLY_so_a_crash_still_cleans_up():
    import base_write_harness

    source = inspect.getsource(base_write_harness.disposable_base)
    tree = ast.parse(source.lstrip())
    tries = [n for n in ast.walk(tree) if isinstance(n, ast.Try)]
    assert tries and any(t.finalbody for t in tries), (
        "the provisioner must delete in a finally, not on the happy path")


def test_ac7_the_harness_title_is_the_GREPPABLE_disposable_prefix():
    import base_write_harness

    title = base_write_harness.disposable_title()
    assert title.startswith("larkdocio-DISPOSABLE-")
    assert base_write_harness.is_disposable_title(title)
    assert not base_write_harness.is_disposable_title("Larkdocio Scratch Base")


def test_ac7_the_harness_module_docstring_says_the_hardening_story_keeps_this_path():
    import base_write_harness

    doc = base_write_harness.__doc__.lower()
    assert "minimal" in doc
    assert "harden" in doc


def test_ac7_the_LIVE_ARM_skips_loudly_when_the_credentials_are_absent(monkeypatch):
    import base_write_harness

    monkeypatch.setattr(base_write_harness, "get_write_credentials", lambda: ("", ""))
    reason = base_write_harness.missing_reason()
    assert reason and "LARK_WRITE_APP" in reason


# --------------------------------------------------------------------------- #
# The package-scan completeness rule: no module escapes BOTH scans.             #
# --------------------------------------------------------------------------- #

def test_every_base_module_is_covered_by_exactly_one_of_the_source_scans():
    """`tests/test_base_client.py` scans the READ half by construction, this file scans the
    record-WRITE half, and `tests/test_base_schema_client.py` the SCHEMA half (LD-263). A
    module in none of the three would be unscanned — the read-only proofs and the
    credential-isolation proofs would both simply stop seeing it."""
    import test_base_client
    import test_base_schema_client

    read_paths = {Path(p).name for p in test_base_client.read_module_paths()}
    write_paths = set(WRITE_MODULE_NAMES)
    schema_paths = set(test_base_schema_client.SCHEMA_MODULE_NAMES)
    covered = read_paths | write_paths | schema_paths
    every = {p.name for p in _BASE_PKG.rglob("*.py")}
    assert covered == every, {
        "unscanned": sorted(every - covered),
        "phantom": sorted(covered - every),
    }
    assert not (read_paths & write_paths)
    assert not (read_paths & schema_paths)
    assert not (write_paths & schema_paths)
    assert schema_paths == set(test_base_client.SCHEMA_MODULE_NAMES), (
        "the two spellings of the schema module list must not drift")
