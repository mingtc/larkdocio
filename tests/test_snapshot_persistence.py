"""LD-444 — the file-first persistence seam: ``snapshot`` / ``load``.

**Tier: regression, unmarked** (``process/doctrine/conformance-tier.md`` § A.4). Every
assertion below pins *this library's own* behaviour — its artefact layout, its refusals, its
determinism — not measured Lark truth. No Lark numeric code is asserted anywhere here, and no
test in this file makes a call.

The load-bearing one is :func:`test_ac3_load_then_project_is_byte_identical_to_the_original`,
which is the property the whole feature rests on: an agent's edits still reconcile against a
projection made a day later only if the projection made a day later is the *same bytes*.
"""
import dataclasses
import inspect
import json
import re

import pytest

from harness import FIXTURES_DIR, build_blocks

from larkdocio import capabilities
from larkdocio import snapshot as snapshot_module
from larkdocio.errors import (
    LarkConfigError,
    LarkDocIOError,
    LarkSnapshotIntegrityError,
)
from larkdocio.model.projection import project_block_ids
from larkdocio.read.config import Config
from larkdocio.read.parser import Parser
from larkdocio.snapshot import SNAPSHOT_FORMAT_VERSION, Snapshot, load, snapshot

# A real payload, deserialized from hand-authored API JSON exactly as the rest of the suite
# does (PROJECT.md § Quality bar — pin real payload shapes, never hand-mocked dicts). Rich on
# purpose: a nested list, a table with cells, headings and an image.
REAL_FIXTURES = (
    "bullet_nested_table.input.json",
    "all_headings.input.json",
    "callout_with_list.input.json",
)


def fixture_dicts(name="bullet_nested_table.input.json"):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def read_of(name="bullet_nested_table.input.json"):
    """The shape a read hands over: ``(document_token, [Block], revision)``."""
    dicts = fixture_dicts(name)
    return dicts[0]["block_id"], build_blocks(dicts), 41


def envelope_of(artefact):
    return json.loads(artefact.decode("utf-8"))["larkdocio_snapshot"]


def corrupt(artefact, old, new):
    assert old in artefact, "the test's own corruption target is not in the artefact"
    return artefact.replace(old, new, 1)


# --------------------------------------------------------------------------- #
# AC1 — the artefact IS the lossless read, under one checksum                  #
# --------------------------------------------------------------------------- #

def test_ac1_the_artefact_carries_the_block_payloads_the_revision_and_the_token():
    token, blocks, revision = read_of()
    payload = envelope_of(snapshot(blocks, document_token=token,
                                   document_revision_id=revision))["payload"]

    assert payload["document_token"] == token
    assert payload["document_revision_id"] == revision
    assert [b["block_id"] for b in payload["blocks"]] == [
        d["block_id"] for d in fixture_dicts()]


def test_ac1_the_payload_is_the_BLOCK_shape_not_a_re_serialization_of_the_tree():
    """The tree is derived; the payload is the evidence. A block dict keeps the wire's own
    keys (``block_type``, the per-type content key), and carries none of the model's."""
    token, blocks, _ = read_of()
    payload = envelope_of(snapshot(blocks, document_token=token))["payload"]

    first = payload["blocks"][0]
    assert first["block_type"] == 1 and "page" in first
    text = json.dumps(payload)
    for model_word in ("TextNode", "HeadingNode", "TableNode", "markdown", "renderer"):
        assert model_word not in text, (
            f"{model_word!r} in the payload — that is the parsed tree leaking into the "
            "artefact, which is the one thing AC1 forbids"
        )


def test_ac1_the_artefact_is_versioned_and_checksummed_and_says_what_the_sum_covers():
    token, blocks, _ = read_of()
    envelope = envelope_of(snapshot(blocks, document_token=token))

    assert envelope["format_version"] == SNAPSHOT_FORMAT_VERSION
    integrity = envelope["integrity"]
    assert integrity["algorithm"] == "sha256"
    assert re.fullmatch(r"[0-9a-f]{64}", integrity["value"])
    assert "payload" in integrity["covers"]
    assert integrity["does_not_cover"], "the artefact must say what the sum does NOT cover"


def test_ac1_writing_the_same_read_twice_is_BYTE_IDENTICAL():
    token, blocks, revision = read_of()
    once = snapshot(blocks, document_token=token, document_revision_id=revision)
    twice = snapshot(build_blocks(fixture_dicts()), document_token=token,
                     document_revision_id=revision)
    assert once == twice


def test_ac1_the_file_is_readable_by_load_with_no_network(tmp_path):
    token, blocks, revision = read_of()
    path = tmp_path / "doc.larkdocio.json"
    written = snapshot(blocks, document_token=token, document_revision_id=revision,
                       path=path)
    assert path.read_bytes() == written
    assert load(path).document_token == token


# --------------------------------------------------------------------------- #
# AC2 — load rehydrates to the tree AND the revision/token                     #
# --------------------------------------------------------------------------- #

def test_ac2_load_returns_the_same_tree_the_parser_produced_plus_revision_and_token():
    token, blocks, revision = read_of()
    original = Parser(Config()).parse_docx_tree(token, blocks)

    loaded = load(snapshot(blocks, document_token=token, document_revision_id=revision))

    assert loaded.document_token == token
    assert loaded.document_revision_id == revision
    assert loaded.format_version == SNAPSHOT_FORMAT_VERSION
    assert project_block_ids(loaded.tree) == project_block_ids(original)


def test_ac2_the_rehydrated_blocks_are_there_too_so_a_caller_can_re_parse_their_own_way():
    token, blocks, _ = read_of()
    loaded = load(snapshot(blocks, document_token=token))
    assert [b.block_id for b in loaded.blocks] == [b.block_id for b in blocks]


# --------------------------------------------------------------------------- #
# AC3 — THE DETERMINISM PROPERTY: load-then-project is BYTE-IDENTICAL          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", REAL_FIXTURES)
@pytest.mark.parametrize("use_html_tags", [False, True])
def test_ac3_load_then_project_is_byte_identical_to_the_original(name, use_html_tags):
    """The pinned property, on a real fixture payload, both ``use_html_tags`` ways.

    Byte equality, not structural equality: the guarantee is that an agent's edits still
    reconcile against a projection taken a day later from the file.
    """
    token, blocks, revision = read_of(name)
    before = project_block_ids(Parser(Config()).parse_docx_tree(token, blocks),
                               use_html_tags=use_html_tags)

    after = project_block_ids(
        load(snapshot(blocks, document_token=token, document_revision_id=revision)).tree,
        use_html_tags=use_html_tags,
    )

    assert after.markdown == before.markdown
    assert after.block_ids == before.block_ids
    assert after.opaque_block_ids == before.opaque_block_ids


# --------------------------------------------------------------------------- #
# AC4 — a corrupted snapshot gets a TYPED refusal naming re-download           #
# --------------------------------------------------------------------------- #

def artefact():
    token, blocks, revision = read_of()
    return snapshot(blocks, document_token=token, document_revision_id=revision)


def test_ac4_a_flipped_byte_in_the_payload_is_a_CHECKSUM_MISMATCH():
    broken = corrupt(artefact(), b"Item with a table", b"Item with a tab1e")
    with pytest.raises(LarkSnapshotIntegrityError) as err:
        load(broken)
    assert err.value.reason == "checksum_mismatch"


def test_ac4_a_TRUNCATED_file_is_refused():
    with pytest.raises(LarkSnapshotIntegrityError) as err:
        load(artefact()[: len(artefact()) // 2])
    assert err.value.reason == "unreadable"


def test_ac4_an_UNKNOWN_or_NEWER_format_version_is_refused_not_upgraded():
    bumped = corrupt(artefact(), b'"format_version": 1',
                     b'"format_version": 99')
    with pytest.raises(LarkSnapshotIntegrityError) as err:
        load(bumped)
    assert err.value.reason == "unknown_format_version"
    assert "99" in str(err.value)


def test_ac4_MALFORMED_content_that_still_checksums_is_refused():
    """Valid JSON, honest digest, nonsense inside — the hand-written-file case."""
    with pytest.raises(LarkSnapshotIntegrityError) as err:
        load(snapshot_module._envelope_bytes({"document_token": 17, "blocks": "nope"}))
    assert err.value.reason == "malformed"


@pytest.mark.parametrize("breakage", [
    lambda a: corrupt(a, b"Item with a table", b"Item with a tab1e"),
    lambda a: a[: len(a) // 2],
    lambda a: corrupt(a, b'"format_version": 1', b'"format_version": 99'),
    lambda a: b"{}",
])
def test_ac4_every_refusal_is_TYPED_names_re_download_and_returns_no_tree(breakage):
    with pytest.raises(LarkSnapshotIntegrityError) as err:
        load(breakage(artefact()))

    assert isinstance(err.value, LarkConfigError)
    assert isinstance(err.value, LarkDocIOError)
    assert "re-download" in str(err.value).lower(), (
        "a refusal that does not name the fix is not actionable"
    )
    assert not hasattr(err.value, "tree"), "no partially-rehydrated tree may escape"


def test_ac4_the_refusal_is_exactly_one_or_refuse_no_repair_verb_ships():
    names = [n for n in dir(snapshot_module) if not n.startswith("_")]
    for verb in ("repair", "salvage", "recover", "fix", "best_effort", "force"):
        assert not any(verb in n.lower() for n in names), (
            f"{verb!r} appears in a public name — a snapshot is refused, never repaired"
        )
    assert "force" not in inspect.signature(load).parameters


# --------------------------------------------------------------------------- #
# AC5 — INTEGRITY, NEVER ENCRYPTION — and the reason ships with it             #
# --------------------------------------------------------------------------- #

def shipped_text():
    """Every string this feature ships: the module's own prose plus the artefact's."""
    module_prose = "\n".join(
        [snapshot_module.__doc__ or ""]
        + [(getattr(obj, "__doc__", "") or "")
           for name, obj in vars(snapshot_module).items() if not name.startswith("_")]
    )
    return module_prose + "\n" + artefact().decode("utf-8")


AFFIRMATIVE_SECURITY_CLAIMS = (
    r"\bis (?:secure|signed|encrypted|tamper[- ]proof|tamper[- ]resistant)\b",
    r"\btamper[- ](?:proof|resistant|evident)\b",
    r"\bdigital(?:ly)? sign",
)


def test_ac5_no_affirmative_security_claim_ships():
    text = shipped_text()
    for pattern in AFFIRMATIVE_SECURITY_CLAIMS:
        assert not re.search(pattern, text, re.IGNORECASE), (
            f"{pattern!r} matched the shipped text — this feature claims INTEGRITY only"
        )


def test_ac5_the_rulings_own_reason_ships_with_the_checksum():
    text = shipped_text().lower()
    assert "no security boundary exists between a local library and" in text
    assert "accidental corruption" in text
    for threat in ("truncated write", "corrupted disk", "hand-edited"):
        assert threat in text, f"the named threat {threat!r} is not stated"


def test_ac5_the_integrity_block_itself_carries_the_reason_not_only_the_docstring():
    why = envelope_of(artefact())["integrity"]["why"].lower()
    assert "no security boundary" in why and "accidental corruption" in why


# --------------------------------------------------------------------------- #
# AC6 — ours-immutable snapshot / theirs-editable draft / reconcile is the     #
#       boundary. THE ABSENCE IS THE CONTRACT.                                 #
# --------------------------------------------------------------------------- #

def test_ac6_no_public_FUNCTION_here_accepts_a_TREE():
    """``Snapshot`` *carries* a tree — it is the result. No **verb** takes one back."""
    for name, obj in vars(snapshot_module).items():
        if name.startswith("_") or not inspect.isfunction(obj):
            continue
        params = inspect.signature(obj).parameters
        assert not {"tree", "root", "node"} & set(params), (
            f"{name}() takes a tree — accepting a caller-mutated tree is the one thing the "
            "ruling forecloses"
        )


def test_ac6_the_snapshot_object_carries_NO_VERB_AT_ALL():
    """Not a setter, not an in-place edit helper, not a 'patch the snapshot' verb — the
    absence is the contract, so it is asserted as an absence rather than inferred."""
    verbs = [n for n in dir(Snapshot)
             if not n.startswith("_") and callable(getattr(Snapshot, n, None))]
    assert verbs == [], f"Snapshot ships callable(s) {verbs} — the snapshot is immutable"


def test_ac6_no_WRITE_path_entry_point_accepts_a_snapshot():
    """The boundary stays ``reconcile``: nothing in the write engine grew a snapshot door."""
    import larkdocio.write as write_pkg

    for name in dir(write_pkg):
        obj = getattr(write_pkg, name)
        if name.startswith("_") or not inspect.isfunction(obj):
            continue
        params = inspect.signature(obj).parameters
        assert "snapshot" not in params, (
            f"larkdocio.write.{name}() grew a snapshot parameter — the only bridge from a "
            "kept read to a write is project → edit the Markdown → reconcile()"
        )


def test_ac6_the_snapshot_is_IMMUTABLE():
    loaded = load(artefact())
    assert dataclasses.is_dataclass(Snapshot) and Snapshot.__dataclass_params__.frozen
    with pytest.raises(dataclasses.FrozenInstanceError):
        loaded.document_token = "somethingelse"


def test_ac6_no_mutator_verb_ships_on_the_snapshot_or_the_module():
    surface = [n for n in dir(snapshot_module) if not n.startswith("_")]
    surface += [n for n in dir(Snapshot) if not n.startswith("_")]
    for verb in ("set_", "patch", "edit", "mutate", "update", "insert", "replace",
                 "delete", "write_block"):
        assert not any(verb in n.lower() for n in surface), (
            f"{verb!r} appears on the public surface — no mutable tree API ships"
        )


def test_ac6_the_boundary_is_named_as_reconcile():
    doc = (snapshot_module.__doc__ or "").lower()
    assert "reconcile" in doc and "markdown" in doc


# --------------------------------------------------------------------------- #
# AC7 — the revision travels, and what it is FOR is said                       #
# --------------------------------------------------------------------------- #

def test_ac7_the_revision_survives_the_round_trip_including_when_absent():
    token, blocks, _ = read_of()
    assert load(snapshot(blocks, document_token=token,
                         document_revision_id=7)).document_revision_id == 7
    assert load(snapshot(blocks, document_token=token)).document_revision_id is None


def test_ac7_the_docs_say_what_the_revision_is_for_and_that_it_is_not_a_lock():
    doc = ((snapshot_module.__doc__ or "") + (Snapshot.__doc__ or "")).lower()
    assert "document_revision_id=" in doc and "stale_document" in doc
    assert "not a lock" in doc and "reserve" in doc
    assert "stale" in doc


# --------------------------------------------------------------------------- #
# AC8 — negative claims, enumerated and scoped                                 #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("claim", [
    "no cross-version migration",
    "unmeasured",
    "docx",
    "sheets",
    "base",
    "folder",
    "concurrent",
    "does not lock",
])
def test_ac8_each_negative_claim_is_stated_in_the_shipped_text(claim):
    assert claim in (snapshot_module.__doc__ or "").lower(), (
        f"the scoped negative claim about {claim!r} is not in the module's shipped text"
    )


def test_ac8_the_prose_carries_no_forward_looking_promise():
    """§ A.1b — a futurity claim is deleted, not shipped, unless it is registered."""
    doc = (snapshot_module.__doc__ or "").lower()
    for phrase in ("future release", "may add", "not yet", "a future rung",
                   "does not ship today", "later release"):
        assert phrase not in doc, f"forward-looking phrase {phrase!r} ships here"


# --------------------------------------------------------------------------- #
# AC10 — the front door moves in the SAME change                               #
# --------------------------------------------------------------------------- #

def test_ac10_capabilities_reports_snapshot_and_load_on_the_docx_read_surface():
    ops = capabilities(full=True)["surfaces"]["docx-read"]["operations"]
    by_name = {op["name"]: op for op in ops}
    assert {"snapshot", "load"} <= set(by_name)
    for name in ("snapshot", "load"):
        assert by_name[name]["projected_from"] == "larkdocio.snapshot"


def test_ac10_the_capability_states_that_it_reaches_NO_endpoint_and_needs_NO_credential():
    ops = {op["name"]: op for op in capabilities(full=True)["surfaces"]["docx-read"]["operations"]}
    for name in ("snapshot", "load"):
        permissions = ops[name]["permissions"]
        assert permissions["endpoints"] == [], (
            f"{name} derived an endpoint — this feature is offline end to end"
        )
        assert permissions["scopes"] == []


def test_ac10_the_integrity_refusal_is_a_declared_safety_contract_of_the_surface():
    registry = capabilities(full=True)
    surface = registry["surfaces"]["docx-read"]
    assert snapshot_module.SNAPSHOT_INTEGRITY_CONTRACT in surface["safety_contracts"]
    summary = registry["safety_contracts"][
        snapshot_module.SNAPSHOT_INTEGRITY_CONTRACT]["summary"].lower()
    assert "re-download" in summary and "never" in summary


# --------------------------------------------------------------------------- #
# LD-465 — THE API DOMAIN TRAVELS. The one fact a successor cannot derive from  #
#          the other three: a token does not say larksuite.com from feishu.cn.  #
# --------------------------------------------------------------------------- #

#: A snapshot written by **1.33.0** — the release before this field existed — committed
#: verbatim so the compatibility claim is measured against a real old artefact rather than
#: against a hand-shaped imitation of one. Generated at the v1.33.0 cut from
#: `bullet_nested_table.input.json`; `snapshot.py` was byte-identical from that tag to this
#: change, so this file IS what 1.33.0 wrote.
OLD_ARTEFACT = FIXTURES_DIR / "snapshot_v1_33_0_no_host.larkdocio.json"

A_DOMAIN = "larksuite.com"


def test_ld465_the_api_domain_travels_in_the_payload():
    token, blocks, revision = read_of()
    payload = envelope_of(snapshot(blocks, document_token=token,
                                   document_revision_id=revision,
                                   api_domain=A_DOMAIN))["payload"]
    assert payload["api_domain"] == A_DOMAIN
    assert sorted(payload) == ["api_domain", "blocks", "document_revision_id",
                               "document_token"], sorted(payload)


def test_ld465_the_domain_is_INSIDE_the_checksum_exactly_as_the_token_is():
    """Not beside the digest — under it. Repointing an artefact at the other tenant is
    corruption, and the digest is what says so."""
    artefact_with_domain = snapshot(read_of()[1], document_token=read_of()[0],
                                    api_domain=A_DOMAIN)
    repointed = corrupt(artefact_with_domain, b"larksuite.com", b"feishu.cn")
    with pytest.raises(LarkSnapshotIntegrityError) as err:
        load(repointed)
    assert err.value.reason == "checksum_mismatch"


def test_ld465_the_COVERS_statement_names_the_domain_it_now_covers():
    """`_COVERS` is the artefact's own statement of what the digest is over — it is the
    contract, so it moves in the same change as the field."""
    covers = envelope_of(snapshot(read_of()[1], document_token=read_of()[0],
                                  api_domain=A_DOMAIN))["integrity"]["covers"]
    assert "api_domain" in covers or "API domain" in covers, covers


def test_ld465_load_returns_the_domain_on_the_snapshot_object():
    token, blocks, revision = read_of()
    loaded = load(snapshot(blocks, document_token=token, document_revision_id=revision,
                           api_domain=A_DOMAIN))
    assert loaded.api_domain == A_DOMAIN


def test_ld465_a_snapshot_taken_without_a_domain_reports_it_ABSENT_never_defaulted():
    loaded = load(snapshot(read_of()[1], document_token=read_of()[0]))
    assert loaded.api_domain is None, (
        "an absent domain must read as absent — a default would point a successor at a "
        "tenant nobody chose")


def test_ld465_the_absence_is_documented_where_the_caller_reads_it():
    doc = ((Snapshot.__doc__ or "") + (snapshot_module.__doc__ or "")).lower()
    assert "api_domain" in doc
    assert "none" in doc and ("guess" in doc or "default" in doc), (
        "the meaning of the absent domain must ship with the field, not be inferred")


def test_ld465_a_non_string_domain_in_the_artefact_is_REFUSED_typed():
    bad = snapshot_module._envelope_bytes({
        "document_token": "root", "document_revision_id": None, "blocks": [],
        "api_domain": 17,
    })
    with pytest.raises(LarkSnapshotIntegrityError) as err:
        load(bad)
    assert err.value.reason == "malformed"


def test_ld465_writing_the_same_read_with_a_domain_twice_is_BYTE_IDENTICAL():
    token, blocks, revision = read_of()
    once = snapshot(blocks, document_token=token, document_revision_id=revision,
                    api_domain=A_DOMAIN)
    twice = snapshot(build_blocks(fixture_dicts()), document_token=token,
                     document_revision_id=revision, api_domain=A_DOMAIN)
    assert once == twice


# --- AC2: the pinned 1.33.0 artefact still loads ---------------------------- #

def test_ld465_the_pinned_fixture_really_is_the_OLD_shape():
    """Anti-vacuity: the compatibility test below proves nothing unless its fixture is the
    old payload — the three keys the dogfood round measured, and no domain."""
    envelope = json.loads(OLD_ARTEFACT.read_text(encoding="utf-8"))["larkdocio_snapshot"]
    assert sorted(envelope["payload"]) == ["blocks", "document_revision_id",
                                           "document_token"]
    assert envelope["format_version"] == 1


def test_ld465_a_1_33_0_ARTEFACT_STILL_LOADS_with_the_domain_reported_absent():
    loaded = load(OLD_ARTEFACT)
    assert loaded.api_domain is None
    assert loaded.document_token == "root"
    assert loaded.document_revision_id == 41
    assert loaded.blocks and loaded.tree is not None


def test_ld465_the_format_version_did_NOT_bump_so_both_directions_still_read():
    """Dev's call, pinned with its reason: the field is **additive and optional**, and the
    digest is taken over the payload's own content — so a 1.33.0 reader loads a 1.34.0
    artefact (ignoring a key it does not know) exactly as this release loads a 1.33.0 one.
    A bump would have refused every old artefact in every old consumer for nothing."""
    assert SNAPSHOT_FORMAT_VERSION == 1


def test_ld465_a_1_33_0_artefact_still_projects_BYTE_IDENTICALLY():
    token, blocks, _ = read_of()
    before = project_block_ids(Parser(Config()).parse_docx_tree(token, blocks))
    after = project_block_ids(load(OLD_ARTEFACT).tree)
    assert after.markdown == before.markdown
    assert after.block_ids == before.block_ids


# --- AC3: the successor's chain, offline, as far as it goes ----------------- #

def test_ld465_the_successor_can_validate_a_url_and_build_a_client_FROM_THE_FILE_ALONE(
        tmp_path):
    """The handoff, offline: everything the successor does before the network, done with
    nothing but the artefact — no URL, no environment beyond credentials."""
    from larkdocio.common import validate_download_url
    from larkdocio.read.client import Client

    token, blocks, revision = read_of()
    path = tmp_path / "document.snapshot"
    snapshot(blocks, document_token=token, document_revision_id=revision,
             api_domain=A_DOMAIN, path=path)

    snap = load(path)                                   # …a day later, another process
    url = f"https://{snap.api_domain}/docx/{snap.document_token}"
    domain, url_type, url_token = validate_download_url(url)

    assert (domain, url_type, url_token) == (A_DOMAIN, "docx", token)
    client = Client("app-id", "app-secret", snap.api_domain)
    assert f"https://open.{A_DOMAIN}" in repr(client.lark_client._config.domain)
