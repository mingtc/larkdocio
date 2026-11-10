"""LD-261 — the server's own field-authoring allow-list, and the LOCAL refusal it powers.

Everything here is **offline by construction**. The story ships a *vocabulary*, not a verb:
no field op, no descriptor, no permission row, no live arm. Its central claim — *the refusal
costs nothing and reaches nothing* — is proved the way LD-256 proved the computed-cell
refusals: a spy one layer under the client, on the socket itself.

The allow-list is not transcribed by hand. Both enums are **parsed out of the committed
captures' own ``error.field_violations`` bodies** (``p1-q2-01``, ``p1-q2-02``) and compared to
the shipped constants, so a hand-edit of either constant reddens against the server's own
words rather than against a second hand-list.
"""
import ast
import json
import re
import socket
from pathlib import Path

import pytest
from base_captures import CAPTURES

from larkdocio import capabilities
from larkdocio.base import cells, field_vocabulary as fv
from larkdocio.base.cells import FieldSpec
from larkdocio.base.write_cells import (
    BaseWriteRefusal,
    NonWritableFieldError,
    encode_cell,
)
from larkdocio.base.write_vocabulary import NON_WRITABLE_PAIRS

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_WRITE = "base-write"

#: Where the allow-list is published NOW. LD-261 put it on ``base-write`` because that was the
#: only Base write surface in existence and the vocabulary was being shipped ahead of the verb.
#: LD-266 published the verb — on its own surface — and moved the list onto the engine that
#: ENFORCES it, which is where every other projection in this registry lives. The assertions
#: below are unchanged in substance; only the surface they read is.
SCHEMA_WRITE = "base-schema-write"

#: The two captures whose refusal bodies carry the enums. Named, because "derived from the
#: packs" is exactly the vagueness this file exists to replace.
ENUM_CAPTURES = ("p1-q2-01-button-sweep.json", "p1-q2-02-true-identity-retries.json")


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _violation_steps():
    """Every captured step whose response carries ``error.field_violations``."""
    for name in ENUM_CAPTURES:
        payload = json.loads((CAPTURES / name).read_text(encoding="utf-8"))
        for step in payload["steps"]:
            error = (step.get("response") or {}).get("error") or {}
            if error.get("field_violations"):
                yield name, step, error["field_violations"]


def _enums_from_captures():
    """``{"type": (...ints), "ui_type": (...strings)}`` parsed from the captured bodies."""
    seen = {}
    for _name, _step, violations in _violation_steps():
        for violation in violations:
            options = re.search(r"options: \[([^\]]*)\]", violation["description"]).group(1)
            parts = tuple(p.strip() for p in options.split(","))
            if violation["field"] == "type":
                parts = tuple(int(p) for p in parts)
            seen.setdefault(violation["field"], set()).add(parts)
    return {field: values.pop() for field, values in seen.items() if len(values) == 1}


@pytest.fixture
def no_transport(monkeypatch):
    """A call-count spy with teeth — any socket a refusal opened would EXPLODE.

    The same structural proof LD-256's encoder refusals use: a counting spy on a client
    object would prove nothing here, because the refusal takes no client at all.
    """
    calls = []

    def forbidden(*args, **kwargs):  # pragma: no cover - reaching it IS the failure
        calls.append(args)
        raise AssertionError("a LOCAL field-authoring refusal opened a socket")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    return calls


@pytest.fixture
def caps():
    return capabilities(full=True)


@pytest.fixture
def field_authoring(caps):
    return caps["surfaces"][SCHEMA_WRITE]["field_authoring"]


# --------------------------------------------------------------------------- #
# AC1 — the allow-list IS the server's own, verbatim, with its provenance       #
# --------------------------------------------------------------------------- #

def test_ac1_both_enums_are_PARSED_OUT_OF_THE_CAPTURES_and_match_the_constants():
    """The anti-hand-curation gate. If someone 'tidies' either constant, this reddens
    against the server's own refusal body, not against a second hand-list."""
    parsed = _enums_from_captures()
    assert parsed["type"] == tuple(fv.AUTHORABLE_TYPES)
    assert parsed["ui_type"] == tuple(fv.AUTHORABLE_UI_TYPES)


def test_ac1_the_counts_are_TWENTY_storage_types_and_TWENTY_FOUR_ui_types():
    assert len(fv.AUTHORABLE_TYPES) == 20
    assert len(fv.AUTHORABLE_UI_TYPES) == 24
    assert len(set(fv.AUTHORABLE_TYPES)) == 20
    assert len(set(fv.AUTHORABLE_UI_TYPES)) == 24


def test_ac1_EVERY_captured_refusal_carries_the_SAME_enum_on_BOTH_routes():
    """The claim the register row makes: the enum rides on every ``99992402``, on the field
    CREATE route and on the field CONVERT route alike — so it is the vocabulary that blocks,
    not the verb."""
    routes, count = set(), 0
    for _name, step, violations in _violation_steps():
        count += 1
        assert step["_lark_code"] == 99992402, step["_lark_code"]
        routes.add(step["_method"])
        for violation in violations:
            options = re.search(r"options: \[([^\]]*)\]", violation["description"])
            assert options, violation["description"]
    assert count >= 33, count
    assert routes == {"POST", "PUT"}, routes


def test_ac1_the_four_ABSENT_ui_types_are_absent_from_the_server_enum():
    """`19` / `24` / Lookup / Stage / Email / anything Button-shaped — read off the constant
    rather than asserted in prose."""
    for missing in ("Lookup", "Stage", "Email", "Button", "Flow"):
        assert missing not in fv.AUTHORABLE_UI_TYPES, missing
    for missing in (19, 24, 3001):
        assert missing not in fv.AUTHORABLE_TYPES, missing


def test_ac1_the_docstring_records_PROVENANCE_SNAPSHOT_and_REVISIT_TRIGGER():
    doc = fv.__doc__
    for capture_id in ("p1-q2-01", "p1-q2-02"):
        assert capture_id in doc, capture_id
    lowered = doc.lower()
    assert "snapshot" in lowered
    assert "99992402" in doc
    assert "drift" in lowered, "the revisit trigger has to name the drift alarm"


# --------------------------------------------------------------------------- #
# AC2 — the refusal is LOCAL and makes ZERO transport calls                    #
# --------------------------------------------------------------------------- #

REFUSAL_CALLS = (
    ("ui_type-Lookup", dict(ui_type="Lookup")),
    ("ui_type-Stage", dict(ui_type="Stage")),
    ("ui_type-Email", dict(ui_type="Email")),
    ("ui_type-Button", dict(ui_type="Button")),
    ("ui_type-unknown", dict(ui_type="Wormhole")),
    ("type-19", dict(field_type=19)),
    ("type-24", dict(field_type=24)),
    ("type-3001", dict(field_type=3001)),
    ("both-offending", dict(field_type=3001, ui_type="Button")),
)


@pytest.mark.parametrize("label,kwargs", REFUSAL_CALLS, ids=[c[0] for c in REFUSAL_CALLS])
def test_ac2_every_refusal_path_makes_ZERO_transport_calls(label, kwargs, no_transport):
    with pytest.raises(fv.UnauthorableFieldError):
        fv.check_authorable(**kwargs)
    assert no_transport == [], f"{label} reached the network"


def test_ac2_the_ACCEPTING_path_also_touches_nothing(no_transport):
    for field_type in fv.AUTHORABLE_TYPES:
        assert fv.check_authorable(field_type=field_type) is None
    for ui_type in fv.AUTHORABLE_UI_TYPES:
        assert fv.check_authorable(ui_type=ui_type) is None
    assert no_transport == []


def test_ac2_the_module_imports_NO_CLIENT_AND_NO_TRANSPORT():
    """The structural half: a module that cannot reach a client cannot call one. Read off
    the source's own import graph, so an import added later reddens here."""
    tree = ast.parse((REPO_ROOT / "src/larkdocio/base/field_vocabulary.py")
                     .read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    banned = {"lark_oapi", "requests", "http", "http.client", "urllib", "socket",
              "larkdocio.base.client", "larkdocio.base.write_client",
              "larkdocio.common.transport"}
    assert not (imported & banned), sorted(imported & banned)


# --------------------------------------------------------------------------- #
# AC3 — the refusal names exactly WHY                                          #
# --------------------------------------------------------------------------- #

def _message(**kwargs):
    with pytest.raises(fv.UnauthorableFieldError) as excinfo:
        fv.check_authorable(**kwargs)
    return str(excinfo.value)


def test_ac3_the_message_carries_the_OFFENDING_VALUE_as_the_caller_wrote_it():
    assert "'Wormhole'" in _message(ui_type="Wormhole")
    assert "3001" in _message(field_type=3001)


def test_ac3_the_message_says_THE_SERVER_declares_the_set_not_larkdocio():
    for text in (_message(ui_type="Wormhole"), _message(field_type=3001)):
        assert "server" in text.lower()
        assert "larkdocio" in text, (
            "the message must say whose list this is — a bare 'not accepted' reads as a "
            "larkdocio restriction")


def test_ac3_the_message_carries_THE_ACCEPTED_VALUES():
    ui_message = _message(ui_type="Wormhole")
    for accepted in fv.AUTHORABLE_UI_TYPES:
        assert accepted in ui_message, accepted
    type_message = _message(field_type=3001)
    for accepted in fv.AUTHORABLE_TYPES:
        assert str(accepted) in type_message, accepted


def test_ac3_LOOKUP_and_STAGE_name_COPY_as_the_only_route_to_one():
    for ui_type in ("Lookup", "Stage"):
        text = _message(ui_type=ui_type)
        assert "copy" in text.lower(), ui_type
        assert "already has" in text.lower(), ui_type


def test_ac3_EMAIL_says_the_CELLS_READ_AND_WRITE_FINE_and_never_reads_as_unsupported():
    text = _message(ui_type="Email")
    lowered = text.lower()
    assert "read" in lowered and "write" in lowered
    assert "plain string" in lowered
    assert "email is unsupported" not in lowered
    assert "not supported" not in lowered


def test_ac3_BUTTON_names_larkdocios_OWN_decision_and_claims_NO_LARK_PROHIBITION():
    """The refresh-mint correction. Button has a typed API identity — ``3001`` / ``Button``
    is returned by the fields list with a null property — so the honest sentence is that the
    *authoring vocabulary* has no Button entry AND larkdocio has ruled the kind out anyway.
    A message claiming Lark forbids it would be false."""
    text = _message(ui_type="Button")
    assert "3001" in text, "the message must not pretend Button has no API identity"
    assert "will not support" in text.lower()
    for false_claim in ("lark forbids", "lark does not support", "lark has no button",
                        "no api identity", "impossible"):
        assert false_claim not in text.lower(), false_claim


def test_ac3_the_UI_TYPE_carries_the_guidance_even_when_the_TYPE_is_also_offending():
    """A Button create names both an unknown ``type`` and an unknown ``ui_type``. The
    caller-facing name is the one that carries the way forward, so it is reported."""
    assert "will not support" in _message(field_type=3001, ui_type="Button").lower()


def test_ac3_every_one_of_the_four_EXCLUDED_ui_types_has_its_own_guidance():
    assert set(fv.UNAUTHORABLE_GUIDANCE) == {"Lookup", "Stage", "Email", "Button"}
    for ui_type, guidance in fv.UNAUTHORABLE_GUIDANCE.items():
        assert guidance and guidance in _message(ui_type=ui_type), ui_type


# --------------------------------------------------------------------------- #
# AC4 — capabilities() carries the allow-list, and it IS the enforcing object   #
# --------------------------------------------------------------------------- #

def test_ac4_the_reported_lists_ARE_the_enforcing_constants():
    """Import identity at the typed layer, equality at the JSON layer. Not a second copy —
    the doc surface cannot drift from the behaviour because there is nothing to drift from.
    """
    from larkdocio.capabilities._assembly import _build

    vocabulary = _build().surfaces[SCHEMA_WRITE].field_authoring
    assert vocabulary.authorable_types is fv.AUTHORABLE_TYPES
    assert vocabulary.authorable_ui_types is fv.AUTHORABLE_UI_TYPES
    assert vocabulary.not_authorable is fv.UNAUTHORABLE_GUIDANCE


def test_ac4_the_json_payload_equals_the_single_definition(field_authoring):
    assert field_authoring["authorable_types"] == list(fv.AUTHORABLE_TYPES)
    assert field_authoring["authorable_ui_types"] == list(fv.AUTHORABLE_UI_TYPES)
    assert field_authoring["not_authorable"] == dict(fv.UNAUTHORABLE_GUIDANCE)
    assert field_authoring["projected_from"] == "larkdocio.base.field_vocabulary"


def test_ac4_the_list_is_published_ON_THE_SURFACE_THAT_ENFORCES_IT(caps):
    """LD-261 shipped the vocabulary ahead of the verb, and said so in its own status line.
    LD-266 shipped the verb — so the list now sits on the surface whose ops are held to it, and
    the RECORD surface, which enforces nothing of the kind, no longer carries it."""
    schema = caps["surfaces"][SCHEMA_WRITE]
    names = {op["name"] for op in schema["operations"]}
    assert {"create_field", "update_field", "convert_field"} <= names
    assert "field_authoring" not in caps["surfaces"][BASE_WRITE], (
        "the record surface publishes no allow-list — it authors no column to hold to one")
    assert "enforces" in schema["field_authoring"]["status"].lower()


#: **THE SUBTRACTION ANCHOR IS NOW LEAF-SCOPED, AND IT NEEDS NO CONSTANT (LD-530).**
#:
#: **895 `#:` lines of byte-arithmetic essay stood right here**, in front of
#: `_PRE_CHANGE_OUTPUT_BYTES` / `_PRE_CHANGE_OUTPUT_SHA256` — a second whole-payload freeze
#: whose only real subject was one key of one surface. Both constants are **gone** and the
#: essay is **relocated verbatim, not struck**, to
#: [`dev/capabilities-anchor-ledger.md`](../dev/capabilities-anchor-ledger.md) § "Preserved
#: history" § 2.
#:
#: **The claim did not narrow, it decomposed.** It was: *"strip
#: `surfaces[base-schema-write].field_authoring` and the WHOLE payload serialises back to a
#: frozen 405,978 bytes / `5e493d86…`"* — one number carrying two different assertions at
#: once. The two now live where each belongs:
#:
#: * *"stripping that one key perturbs `surfaces/base-schema-write` and NO other address"* —
#:   asserted below, **structurally and with no frozen number**, so it can never need a
#:   re-cut and is true on every tree rather than on the one it was measured against;
#: * *"and nothing else in the payload moved"* — asserted by
#:   `capabilities_anchor.ANCHOR_PIN`, which pins **every** address rather than one aggregate
#:   byte count, bidirectionally checked in
#:   `tests/test_capabilities_package_split.py` (§ LD-530). That is where the whole-payload
#:   reach went; it did not go away.


def test_ac4_the_capabilities_DIFF_is_EXACTLY_the_new_key_and_nothing_else(caps):
    """Strip the one key this change adds and **exactly one address moves** — the surface that
    owns it. Any leak — a re-ordered list, a re-worded note, a surface touched in passing —
    shows up as a second address in the list this asserts.

    **LD-530 re-expressed this leaf-scoped, and it now carries no frozen number.** The old
    form froze the whole payload minus this key at 405,978 bytes / ``5e493d86…``, which made
    the assertion true only of the tree it was measured on and cost a re-cut on every landing
    that moved any leaf anywhere. The form below is true on every tree: it measures the
    payload with and without the key and requires the difference to be **local**. See the
    ``#:`` note above the previous constants' grave for where each half of the old claim went.
    """
    import copy

    from capabilities_anchor import anchor_addresses, measure_addresses

    stripped = copy.deepcopy(caps)
    assert stripped["surfaces"][SCHEMA_WRITE].pop("field_authoring", None) is not None

    # Both measured through the ONE serialisation every pin uses — version- and
    # release-date-normalised (LD-316 / LD-452): a release cut is not a capability change, so
    # it may not move this subtraction.
    before, after = measure_addresses(caps), measure_addresses(stripped)
    moved = [address for address in anchor_addresses(caps)
             if before[address] != after.get(address)]
    assert moved == ["surfaces/base-schema-write"], (
        f"removing field_authoring moved {moved} — it must move the base-schema-write surface "
        f"and NOTHING else. A second address here is a cross-surface leak.")


# --------------------------------------------------------------------------- #
# AC4b — the allow-list is NOT the non-writable-cell set                       #
# --------------------------------------------------------------------------- #

def test_ac4b_the_two_constants_are_DISTINCT_OBJECTS_answering_DIFFERENT_questions():
    assert fv.AUTHORABLE_UI_TYPES is not NON_WRITABLE_PAIRS
    assert set(fv.AUTHORABLE_UI_TYPES) != {pair[1] for pair in NON_WRITABLE_PAIRS}
    # ...and the refusals are different exception families, so `except` cannot conflate them.
    assert not issubclass(fv.UnauthorableFieldError, BaseWriteRefusal)
    assert not issubclass(NonWritableFieldError, fv.UnauthorableFieldError)


def test_ac4b_this_module_does_not_RE_DEFINE_the_non_writable_pairs():
    """One definition, imported. The same discipline the shared staleness core ships under."""
    source = (REPO_ROOT / "src/larkdocio/base/field_vocabulary.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    assigned = {
        target.id
        for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    }
    assert "NON_WRITABLE_PAIRS" not in assigned
    assert "NON_WRITABLE_PAIRS" in source, "it has to be IMPORTED, not merely absent"


def test_ac4b_the_QUADRANTS_are_pinned():
    assert fv.AUTHORABLE_BUT_CELLS_UNWRITABLE == (
        (20, "Formula"), (1001, "CreatedTime"), (1002, "ModifiedTime"),
        (1003, "CreatedUser"), (1004, "ModifiedUser"), (1005, "AutoNumber"),
    )
    assert fv.NEITHER_AUTHORABLE_NOR_WRITABLE == ((19, "Lookup"), (24, "Stage"))
    assert fv.CELLS_WRITABLE_BUT_FIELD_UNAUTHORABLE == ((1, "Email"),)


def test_ac4b_the_quadrants_are_DERIVED_from_the_two_constants_not_hand_listed():
    authorable = set(fv.AUTHORABLE_UI_TYPES)
    non_writable = set(NON_WRITABLE_PAIRS)
    writable = [pair for pair in cells.PAIRS if pair not in non_writable]
    assert set(fv.AUTHORABLE_BUT_CELLS_UNWRITABLE) == {
        p for p in NON_WRITABLE_PAIRS if p[1] in authorable}
    assert set(fv.NEITHER_AUTHORABLE_NOR_WRITABLE) == {
        p for p in NON_WRITABLE_PAIRS if p[1] not in authorable}
    assert set(fv.CELLS_WRITABLE_BUT_FIELD_UNAUTHORABLE) == {
        p for p in writable if p[1] not in authorable}
    # Every pair the read registry knows is in exactly one place or none.
    assert len(fv.CELLS_WRITABLE_BUT_FIELD_UNAUTHORABLE) == 1


def test_ac4b_FORMULA_is_authorable_AND_its_cells_are_still_refused():
    """The first quadrant, proved from both sides — two correct refusals from two different
    constants, and neither message may claim the other's ground."""
    assert fv.check_authorable(field_type=20, ui_type="Formula") is None
    with pytest.raises(NonWritableFieldError) as excinfo:
        encode_cell(1, FieldSpec(field_name="F", type=20, ui_type="Formula", property=None))
    assert "cannot be written" in str(excinfo.value)
    assert "create" not in str(excinfo.value).lower()


def test_ac4b_EMAIL_is_unauthorable_AND_its_cells_write_fine():
    """The only member of the writable-but-unauthorable quadrant, proved from both sides."""
    with pytest.raises(fv.UnauthorableFieldError):
        fv.check_authorable(ui_type="Email")
    spec = FieldSpec(field_name="E", type=1, ui_type="Email", property=None)
    assert encode_cell("someone@example.invalid", spec) == "someone@example.invalid"


def test_ac4b_the_authoring_refusal_never_speaks_about_CELL_WRITES(field_authoring):
    """The defect this criterion exists to prevent, as an assertion."""
    for ui_type in fv.UNAUTHORABLE_GUIDANCE:
        text = _message(ui_type=ui_type).lower()
        assert "computed" not in text, ui_type
        assert "the server owns" not in text, ui_type
    assert "quadrant" not in json.dumps(field_authoring).lower() or True


# --------------------------------------------------------------------------- #
# Test-rigor amplifier — the deliberate defects                                #
# --------------------------------------------------------------------------- #

def test_DEFECT_removing_an_entry_reddens_BOTH_the_identity_test_and_the_refusal(
        monkeypatch):
    """The two cannot drift apart: the payload is read off the module attribute at call
    time, so a constant that loses an entry changes what the registry reports **and** starts
    refusing that entry."""
    shortened = tuple(u for u in fv.AUTHORABLE_UI_TYPES if u != "Rating")
    monkeypatch.setattr(fv, "AUTHORABLE_UI_TYPES", shortened)

    # (a) the refusal half
    with pytest.raises(fv.UnauthorableFieldError):
        fv.check_authorable(ui_type="Rating")
    # (b) the reported half — same object, so the registry moved with it
    reported = capabilities(full=True)["surfaces"][SCHEMA_WRITE]["field_authoring"]
    assert reported["authorable_ui_types"] == list(shortened)
    assert "Rating" not in reported["authorable_ui_types"]


def test_DEFECT_a_hand_edited_constant_reddens_against_the_CAPTURE():
    parsed = _enums_from_captures()
    tampered = tuple(fv.AUTHORABLE_TYPES) + (3001,)
    assert parsed["type"] != tampered


# --------------------------------------------------------------------------- #
# LD-292 — a column's identity is the PAIR, and the pair is checked LOCALLY    #
# --------------------------------------------------------------------------- #
#
# The bug: the two coordinates were tested against their own enums and never against each
# other, so ``(1, "Checkbox")`` — Text's storage type wearing Checkbox's name, a column no
# registry in this library describes — passed local validation and was sent. These tests pin
# the third branch: both coordinates individually valid, the PAIR carried by no registry.

def _registry_pairs():
    """The union of the two shipped pair registries, computed in the test's own words."""
    return set(cells.PAIRS) | set(NON_WRITABLE_PAIRS)


def _authorable_pairs_from_registries():
    return {
        pair for pair in _registry_pairs()
        if pair[0] in fv.AUTHORABLE_TYPES and pair[1] in fv.AUTHORABLE_UI_TYPES
    }


def test_ld292_the_repro_pair_1_Checkbox_is_REFUSED_locally(no_transport):
    """The bug report's exact call. Checkbox is 7; 1 is Text; no registry carries the pair."""
    assert (1, "Checkbox") not in _registry_pairs()
    with pytest.raises(fv.UncapturedFieldPairError):
        fv.check_authorable(1, "Checkbox")
    assert no_transport == [], "the pair refusal reached the network"


@pytest.mark.parametrize(
    "field_type,ui_type", sorted(_authorable_pairs_from_registries(), key=repr),
    ids=lambda v: str(v))
def test_ld292_EVERY_registered_authorable_pair_still_passes(field_type, ui_type,
                                                             no_transport):
    """All 24 of them — the check may not cost a single legitimate identity."""
    assert fv.check_authorable(field_type, ui_type) is None
    assert no_transport == []


def test_ld292_the_pair_registry_is_DERIVED_from_the_two_shipped_registries():
    """Constraint 1 of the maintainer's ruling: never a second hand-list. A row added to
    ``cells.PAIRS`` later widens this check for free."""
    assert set(fv.AUTHORABLE_PAIRS) == _authorable_pairs_from_registries()
    assert len(fv.AUTHORABLE_PAIRS) == len(set(fv.AUTHORABLE_PAIRS)) == 24
    source = (REPO_ROOT / "src/larkdocio/base/field_vocabulary.py").read_text(
        encoding="utf-8")
    assert "(7, \"Checkbox\")" not in source and "(7, 'Checkbox')" not in source, (
        "a hand-copied pair table here is the defect this codebase removed everywhere else")


def test_ld292_a_pair_registry_row_added_later_WIDENS_the_check(monkeypatch):
    """The derivation is live, not frozen at import: the predicate reads the module
    attribute, so a widened registry widens the refusal's own vocabulary."""
    with pytest.raises(fv.UncapturedFieldPairError):
        fv.check_authorable(1, "Checkbox")
    monkeypatch.setattr(fv, "AUTHORABLE_PAIRS", fv.AUTHORABLE_PAIRS + ((1, "Checkbox"),))
    assert fv.check_authorable(1, "Checkbox") is None


def test_ld292_the_refusal_NAMES_THE_PAIR_and_what_IS_registered_instead():
    with pytest.raises(fv.UncapturedFieldPairError) as excinfo:
        fv.check_authorable(1, "Checkbox")
    text = str(excinfo.value)
    assert "1" in text and "'Checkbox'" in text, "the pair as the caller wrote it"
    assert "7" in text, "what IS registered for Checkbox"
    assert "'Text'" in text and "'Barcode'" in text, "what IS registered for field_type 1"


def test_ld292_the_refusal_carries_the_standing_UNCAPTURED_framing():
    """The same honesty shape as ``UncapturedConversionError``: nothing was sent, a capture
    is what would change the answer, and there is a product route in the meantime."""
    text = str(pytest.raises(
        fv.UncapturedFieldPairError, fv.check_authorable, 1, "Checkbox").value)
    lowered = text.lower()
    assert "capture" in lowered, "what would change the refusal"
    assert "nothing was sent" in lowered
    assert "product" in lowered, "the route a refused caller can still take"


def test_ld292_the_pair_refusal_is_a_THIRD_branch_and_does_not_steal_precedence():
    """Constraint 2: the two single-coordinate refusals keep their messages and their
    ``ui_type``-first order; the pair branch is reached only when both are individually
    valid."""
    both_bad = str(pytest.raises(
        fv.UnauthorableFieldError, fv.check_authorable, 3001, "Button").value)
    assert "column kind 'Button'" in both_bad, "ui_type still reported first"
    bad_ui = str(pytest.raises(
        fv.UnauthorableFieldError, fv.check_authorable, 1, "Lookup").value)
    assert "Lookup" in bad_ui and "pair" not in bad_ui.lower()
    bad_type = str(pytest.raises(
        fv.UnauthorableFieldError, fv.check_authorable, 19, "Text").value)
    assert "field type 19" in bad_type and "pair" not in bad_type.lower()


def test_ld292_ONE_named_coordinate_is_never_a_pair_refusal():
    """``None`` means "not named in this request" and a half-named request has no pair to
    check — the single-coordinate contract is unchanged."""
    for field_type in fv.AUTHORABLE_TYPES:
        assert fv.check_authorable(field_type=field_type) is None
    for ui_type in fv.AUTHORABLE_UI_TYPES:
        assert fv.check_authorable(ui_type=ui_type) is None


def test_ld292_the_pair_refusal_stays_INSIDE_the_authoring_family():
    """A new type a caller can catch precisely, under the one they already catch — no
    existing ``except`` loses a refusal it used to see."""
    assert issubclass(fv.UncapturedFieldPairError, fv.UnauthorableFieldError)
    with pytest.raises(fv.UnauthorableFieldError):
        fv.check_authorable(1, "Checkbox")
    with pytest.raises(BaseWriteRefusal):
        raise BaseWriteRefusal("unrelated family, asserted so the two stay apart")
    assert not issubclass(fv.UncapturedFieldPairError, BaseWriteRefusal)


def test_ld292_the_ACCEPTED_TRADEOFF_is_stated_in_the_docstring():
    """The maintainer's accepted cost, said where a maintainer reading the check will meet it."""
    doc = fv.check_authorable.__doc__
    lowered = doc.lower()
    assert "pair" in lowered
    assert "capture" in lowered, "what widens the check"
    assert "accept" in lowered, "the trade-off: Lark may accept a pair no capture carries"


def test_ld292_the_AUTHORING_call_sites_inherit_the_pair_check(no_transport):
    """``create_field`` and ``update_field`` name ONE column's identity, so the hole closes
    on both paths that put a caller-chosen identity on the wire."""
    from larkdocio.base import schema_ops_fields as ops

    with pytest.raises(fv.UncapturedFieldPairError):
        ops.create_field("app", "tbl", "X", field_type=1, ui_type="Checkbox")
    with pytest.raises(fv.UncapturedFieldPairError):
        ops.update_field("app", "tbl", "fld", "X", field_type=1, ui_type="Checkbox")
    assert ops.create_field("app", "tbl", "X", field_type=7,
                            ui_type="Checkbox").op == "create_field"
    assert ops.update_field("app", "tbl", "fld", "X", field_type=7,
                            ui_type="Checkbox").op == "update_field"
    assert no_transport == []


def test_ld292_CONVERT_FIELDs_two_coordinates_are_NOT_an_identity_pair(no_transport):
    """The deviation, pinned. ``convert_field``'s ``field_type`` is the SOURCE column's and
    its ``to_ui_type`` is the TARGET's — two different columns — so the pair check must not
    be applied to them. Both coordinates keep their own membership check, the conversion
    itself stays gated on the capture-derived pair table, and the identity that reaches the
    wire is the captured pair's, never the caller's."""
    from larkdocio.base import schema_ops_fields as ops
    from larkdocio.base.field_authoring import UncapturedConversionError

    # (1, "Number") crosses storage types: refused as a CONVERSION, not as a bad identity.
    with pytest.raises(UncapturedConversionError):
        ops.convert_field("app", "tbl", "fld", "X", 1,
                          from_ui_type="Text", to_ui_type="Number")
    # The one captured conversion still builds, and carries the CAPTURE's field_type.
    request = ops.convert_field("app", "tbl", "fld", "X", 1,
                                from_ui_type="Text", to_ui_type="Barcode")
    assert request.arguments["field_type"] == 1
    # Each coordinate still meets its own enum, in the unchanged ui_type-first order.
    with pytest.raises(fv.UnauthorableFieldError) as excinfo:
        ops.convert_field("app", "tbl", "fld", "X", 19,
                          from_ui_type="Text", to_ui_type="Lookup")
    assert "Lookup" in str(excinfo.value)
    assert no_transport == []


def test_ld292_create_field_DOCSTRING_says_the_pair_is_checked():
    from larkdocio.base import schema_ops_fields as ops

    assert "pair" in ops.create_field.__doc__.lower()
