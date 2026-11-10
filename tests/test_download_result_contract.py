"""The docx download verb answers with a VALUE, not with log lines (LD-598).

``handle_download_command`` returned ``None`` — zero ``return`` statements that yield a value —
so a programmatic caller could not learn **where the file landed** or **whether the router
fired and why** except by parsing log text. The ``--dump`` sidecar already answers the one
question of this shape (*what did this run not fetch*), but it is written **into the routed
directory the caller cannot learn**, so that answer sat behind the question.

Four things are pinned here, in the order the ACs put them:

* **the return value** — a typed, additive ``DownloadResult`` on every success path
  (``None`` → an object breaks no caller, which is the whole reason break-risk is low);
* **its grammar** — the dict-compatible shape the write side's typed create returns already
  ship, mirrored rather than re-invented (``CreatedDocument`` is the pinned twin below);
* **the sidecar's ``route`` record** — deterministic, and the SAME record the returned value
  carries, so the two cannot disagree;
* **the two fences** — the output path is NOT in the sidecar (its byte-identical determinism
  is a stated property and a path is machine- and invocation-specific), and the sidecar does
  NOT move out of the ``-o`` directory it lands in today.
"""

import inspect
import json
import pathlib

import pytest

import private_tree

from larkdocio.read import download
from larkdocio.read.download import DownloadResult
from larkdocio.write.client import CreatedDocument

from test_download_pipeline import DOCX_URL, _StubClient, _StubParser, _patch_env


#: Three INERT document bodies (LD-650). They used to be the router's three inputs — all
#: three metadata rows, two of the three, none — and the fixtures are kept in exactly that
#: shape ON PURPOSE: the arms below now assert that these bodies are indistinguishable to the
#: reader, which is a claim you can only make about the bodies that used to differ. Nothing
#: reads them for a destination any more; they are just markdown of three lengths.
TABLE_MD = "| Area | Sales |\n| Section | Billing |\n| Topic | Invoices |\n"
PARTIAL_TABLE_MD = "| Area | Sales |\n| Section | Billing |\n"
PLAIN_MD = "# plain\n\nno metadata table at all.\n"

#: The subpath the arms below pass as an EXPLICIT ``--route`` — the caller's instruction, the
#: only thing that moves output now. It is spelled the way the old derived one was so the
#: comparison with history stays legible.
EXPLICIT_SUBPATH = ("sales", "billing", "invoices")
EXPLICIT_ROUTE = "/".join(EXPLICIT_SUBPATH)


def run(monkeypatch, out_dir, markdown=PLAIN_MD, *, dump=False, route=None):
    """One whole download against the stubbed client/parser — no network, no ``.env``."""
    _patch_env(monkeypatch)
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient())
    monkeypatch.setattr(download, "Parser", lambda config: _StubParser(markdown=markdown))
    return download.handle_download_command(
        DOCX_URL, str(out_dir), "", dump, "", route=route
    )


def sidecar(directory):
    """The one ``<token>.json`` in ``directory``, parsed."""
    return json.loads((pathlib.Path(directory) / "AbCdEfG123.json").read_text(encoding="utf-8"))


def leaves(value):
    """Every scalar leaf in a nested JSON value — what a fence has to be checked against."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from leaves(item)
    else:
        yield value


# --------------------------------------------------------------------------- #
# AC1 — the verb returns a typed value, and the type is ADDITIVE.              #
# --------------------------------------------------------------------------- #

def test_ac1_the_signature_no_longer_annotates_None():
    """The literal evidence the AC names: the annotation is the result type, not ``None``."""
    assert inspect.signature(download.handle_download_command).return_annotation is DownloadResult
    assert "-> None:" not in inspect.getsource(download.handle_download_command).split("\n")[0]


def test_ac1_an_unrouted_download_answers_where_the_file_landed(monkeypatch, tmp_path):
    result = run(monkeypatch, tmp_path)

    assert isinstance(result, DownloadResult)
    assert result.output_dir == str(tmp_path)
    assert pathlib.Path(result.output_path).is_file()
    assert pathlib.Path(result.output_path).parent == tmp_path
    assert result.routed is False
    assert result.route_reason == download.ROUTE_DISABLED


def test_ac1_a_ROUTED_download_answers_the_directory_it_was_rerouted_INTO(monkeypatch, tmp_path):
    """The question the log line was the only answer to: ``-o`` was rewritten — to what?
    Driven by an explicit ``--route`` since LD-650, which is the only thing that rewrites it."""
    result = run(monkeypatch, tmp_path, TABLE_MD, route=EXPLICIT_ROUTE)

    routed = tmp_path.joinpath(*EXPLICIT_SUBPATH)
    assert result.routed is True
    assert result.route_reason == download.ROUTE_EXPLICIT
    assert result.output_dir == str(routed)
    assert pathlib.Path(result.output_path).parent == routed


def test_ac1_an_explicit_route_is_reported_as_the_CALLERS_instruction(monkeypatch, tmp_path):
    """``--route`` routes, and its reason is not the derivation's — the caller named the path,
    the library derived nothing."""
    result = run(monkeypatch, tmp_path, TABLE_MD, route="x/y")

    assert result.routed is True
    assert result.route_reason == download.ROUTE_EXPLICIT
    assert result.output_dir == str(tmp_path / "x" / "y")
    assert result.route["derivation_ran"] is False


def test_ac1_no_route_is_its_OWN_reason_and_a_stale_config_key_does_not_change_it(
    monkeypatch, tmp_path
):
    """TRANSFORMED (LD-650). The reason value and its meaning are unchanged — "nothing was
    detected, and that is different from detecting nothing" — but the fact it now reports is
    that the library never looks. A stand-in for a retired config key is passed here
    deliberately: a consumer's stale file must not raise and must not change the answer."""
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"output": {"a_retired_switch": False}}), encoding="utf-8")
    _patch_env(monkeypatch)
    monkeypatch.setattr(download, "Client", lambda *a, **k: _StubClient())
    monkeypatch.setattr(download, "Parser", lambda config: _StubParser(markdown=TABLE_MD))

    result = download.handle_download_command(
        DOCX_URL, str(tmp_path), "", False, str(config)
    )

    assert result.routed is False
    assert result.route_reason == download.ROUTE_DISABLED
    assert result.route["derivation_ran"] is False
    assert result.output_dir == str(tmp_path)


def test_ac1_the_three_BODIES_are_now_indistinguishable_to_the_reader(monkeypatch, tmp_path):
    """TRANSFORMED (LD-650) from the near-miss arm. It used to prove the record told a
    two-of-three near miss apart from a document carrying none of the rows; the fixtures are
    unchanged and the claim is inverted — all three answer the SAME record, because none of
    them is read. Both label lists are empty and PRESENT, which is the shape promise."""
    records = [
        run(monkeypatch, tmp_path / f"case-{i}", body).route
        for i, body in enumerate((TABLE_MD, PARTIAL_TABLE_MD, PLAIN_MD))
    ]
    assert records[0] == records[1] == records[2]
    assert records[0]["labels_found"] == [] and records[0]["labels_missing"] == []
    assert records[0]["derivation_ran"] is False


def test_ac1_the_result_names_the_sidecar_the_caller_could_not_otherwise_find(monkeypatch, tmp_path):
    """The stated problem, closed: the sidecar lands in the routed directory, and the value
    that reports the routed directory also reports the sidecar's own path."""
    with_dump = run(monkeypatch, tmp_path / "a", TABLE_MD, dump=True,
                    route=EXPLICIT_ROUTE)
    without = run(monkeypatch, tmp_path / "b", TABLE_MD, dump=False,
                  route=EXPLICIT_ROUTE)

    assert pathlib.Path(with_dump.dump_path).is_file()
    assert pathlib.Path(with_dump.dump_path).parent == pathlib.Path(with_dump.output_dir)
    assert without.dump_path is None, "no --dump, no sidecar — reported as such, not guessed"


def test_ac1_ADDITIVE_the_command_line_still_ignores_the_return_value(monkeypatch, tmp_path):
    """The break-risk argument, exercised: the one in-tree caller passes the value nowhere,
    so ``None`` → an object is observable by nobody who was not asking for it."""
    source = inspect.getsource(download.handle_download_command)
    assert source.count("return ") >= 1, "the verb must yield a value on the success path"

    import larkdocio.cli as cli_module

    call = [
        line for line in inspect.getsource(cli_module.download.callback).split("\n")
        if "handle_download_command(" in line
    ]
    assert call and not any("=" in line.split("handle_download_command")[0] for line in call), (
        "the CLI must keep calling the handler for effect, not bind its value"
    )


# --------------------------------------------------------------------------- #
# AC2 — the DICT-COMPATIBLE shape is FOLLOWED, not re-invented.                #
# --------------------------------------------------------------------------- #

def test_ac2_the_shape_MIRRORS_the_write_sides_typed_create_return():
    """The named twin: ``WriteClient.create_document`` → ``CreatedDocument``, a ``dict``
    subclass whose body is the payload and whose attributes are views onto it. The read side
    answers in the same grammar rather than a second one."""
    assert issubclass(CreatedDocument, dict)
    assert issubclass(DownloadResult, dict)


def test_ac2_every_dict_operation_answers_over_the_bodys_own_bytes(monkeypatch, tmp_path):
    result = run(monkeypatch, tmp_path)
    body = {**result}

    assert isinstance(result, dict)
    assert result["output_dir"] == str(tmp_path)
    assert result.get("output_dir") == str(tmp_path)
    assert result.get("not_a_key") is None
    assert "output_path" in result
    assert len(result) == len(body)
    assert set(result.keys()) == set(body)
    assert dict(result) == body
    assert result == body, "equality against the plain dict is the compatibility promise"
    assert json.loads(json.dumps(result)) == body


def test_ac2_the_attributes_are_VIEWS_onto_the_body_not_a_second_copy(monkeypatch, tmp_path):
    """D-103's own property: an attribute cannot drift from its key, because it IS the key."""
    result = run(monkeypatch, tmp_path)

    result["output_path"] = "/elsewhere/moved.md"
    assert result.output_path == "/elsewhere/moved.md"
    result["route"] = {"routed": True, "reason": "made-up"}
    assert result.routed is True and result.route_reason == "made-up"


def test_ac2_the_body_is_JSON_native_all_the_way_down(monkeypatch, tmp_path):
    """A result a ledger can write straight out — no coercion, no custom encoder."""
    result = run(monkeypatch, tmp_path, TABLE_MD, dump=True)
    assert json.loads(json.dumps(result, sort_keys=True)) == {**result}


def test_ac2_the_four_AC_named_fields_are_all_readable(monkeypatch, tmp_path):
    result = run(monkeypatch, tmp_path, TABLE_MD, route=EXPLICIT_ROUTE)
    assert result.output_path and result.output_dir
    assert result.routed is True and result.route_reason


# --------------------------------------------------------------------------- #
# AC3 — the route record lands in the sidecar, and it is DETERMINISTIC.        #
# --------------------------------------------------------------------------- #

def test_ac3_the_sidecar_carries_the_routing_DECISION(monkeypatch, tmp_path):
    run(monkeypatch, tmp_path, TABLE_MD, dump=True, route=EXPLICIT_ROUTE)
    record = sidecar(tmp_path.joinpath(*EXPLICIT_SUBPATH))["route"]

    assert record["routed"] is True
    assert record["reason"] == download.ROUTE_EXPLICIT
    assert record["derivation_ran"] is False
    # All five keys, unconditionally — the two label lists are empty rather than absent.
    assert record["labels_found"] == []
    assert record["labels_missing"] == []


def test_ac3_the_sidecars_record_and_the_RETURNED_records_are_the_same_record(monkeypatch, tmp_path):
    """One definition, two readers. A sidecar that could disagree with the returned value
    would be a second source of truth for the same decision."""
    result = run(monkeypatch, tmp_path, PARTIAL_TABLE_MD, dump=True)
    assert sidecar(tmp_path)["route"] == result.route


def test_ac3_two_dump_runs_over_an_unchanged_document_are_BYTE_IDENTICAL(monkeypatch, tmp_path):
    """The sidecar stays a pure function of the payload and the mode — the ``route`` record
    must not smuggle anything run-varying in."""
    for markdown in (TABLE_MD, PARTIAL_TABLE_MD, PLAIN_MD):
        first = tmp_path / f"first-{len(markdown)}"
        second = tmp_path / f"second-{len(markdown)}"
        a = run(monkeypatch, first, markdown, dump=True)
        b = run(monkeypatch, second, markdown, dump=True)
        assert (pathlib.Path(a.dump_path).read_bytes()
                == pathlib.Path(b.dump_path).read_bytes()), markdown


def test_ac3_the_reason_vocabulary_is_CLOSED_and_carries_no_internal_dialect():
    """The reason is consumer-reaching text inside a machine-read file: TWO values since
    LD-650 (the two that reported the retired derivation left with it), no issue ids, no repo
    paths, nothing that reads like a log sentence. The surviving pair keeps its exact old
    spellings, so the vocabulary is a strict SUBSET of what shipped before and a consumer
    validating against the set they know never meets a string they have not seen."""
    vocabulary = {
        download.ROUTE_EXPLICIT,
        download.ROUTE_DISABLED,
    }
    assert len(vocabulary) == 2
    assert vocabulary == {"explicit_route", "routing_disabled"}
    assert not [n for n in dir(download) if n.startswith("ROUTE_")] == [], "sanity"
    assert {n for n in dir(download) if n.startswith("ROUTE_")} == {
        "ROUTE_EXPLICIT", "ROUTE_DISABLED"
    }, "a third reason value may not appear without this arm being re-argued"
    for reason in vocabulary:
        assert reason == reason.lower() and " " not in reason
        assert "ld-" not in reason and "/" not in reason


# --------------------------------------------------------------------------- #
# AC4 — FENCE 1 (HARD): the output path is NOT in the sidecar.                 #
# --------------------------------------------------------------------------- #

def test_ac4_no_sidecar_value_is_the_runs_output_path_or_output_dir(monkeypatch, tmp_path):
    """The fence, stated as the AC states it. The reason is the file's own determinism: a path
    is machine- and invocation-specific, so writing one in breaks the property the sidecar is
    built on."""
    for markdown in (TABLE_MD, PARTIAL_TABLE_MD, PLAIN_MD):
        target = tmp_path / f"run-{len(markdown)}"
        result = run(monkeypatch, target, markdown, dump=True)
        payload = json.loads(pathlib.Path(result.dump_path).read_text(encoding="utf-8"))
        forbidden = {result.output_path, result.output_dir, result.dump_path, str(target)}
        offenders = [leaf for leaf in leaves(payload) if leaf in forbidden]
        assert offenders == [], offenders


def test_ac4_no_sidecar_STRING_even_mentions_the_output_root(monkeypatch, tmp_path):
    """Wider than equality, because a fence that only catches the whole path is trivially
    walked around by joining a prefix onto it."""
    result = run(monkeypatch, tmp_path, TABLE_MD, dump=True, route=EXPLICIT_ROUTE)
    body = pathlib.Path(result.dump_path).read_text(encoding="utf-8")
    assert str(tmp_path) not in body


def test_ac4_two_different_o_directories_produce_a_BYTE_IDENTICAL_sidecar(monkeypatch, tmp_path):
    """The AC's own second evidence: the same document dumped from two different ``-o`` roots.
    A path anywhere in the payload fails this and nothing else does."""
    for markdown in (TABLE_MD, PLAIN_MD):
        one = run(monkeypatch, tmp_path / f"one-{len(markdown)}", markdown, dump=True)
        two = run(monkeypatch, tmp_path / f"two-{len(markdown)}", markdown, dump=True)
        assert (pathlib.Path(one.dump_path).read_bytes()
                == pathlib.Path(two.dump_path).read_bytes()), markdown


def test_ac4_an_explicit_route_subpath_is_not_echoed_into_the_sidecar_either(monkeypatch, tmp_path):
    """``--route`` is a caller-supplied RELATIVE path, so echoing it is the same defect: two
    runs of one document under two different ``--route`` values must still match byte for
    byte."""
    one = run(monkeypatch, tmp_path / "one", PLAIN_MD, dump=True, route="alpha/beta")
    two = run(monkeypatch, tmp_path / "two", PLAIN_MD, dump=True, route="gamma")

    assert (pathlib.Path(one.dump_path).read_bytes()
            == pathlib.Path(two.dump_path).read_bytes())
    assert "alpha" not in pathlib.Path(one.dump_path).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# AC5 — FENCE 2 (HARD): the sidecar does NOT move.                             #
# --------------------------------------------------------------------------- #

def test_ac5_the_sidecar_stays_in_the_SAME_directory_as_the_markdown(monkeypatch, tmp_path):
    """The caller's inability to find the sidecar is fixed by the return value handing them
    the directory — never by relocating the file (the same-``-o``-directory clause)."""
    result = run(monkeypatch, tmp_path, TABLE_MD, dump=True, route=EXPLICIT_ROUTE)

    routed = tmp_path.joinpath(*EXPLICIT_SUBPATH)
    assert pathlib.Path(result.dump_path) == routed / "AbCdEfG123.json"
    assert pathlib.Path(result.output_path).parent == routed
    assert not (tmp_path / "AbCdEfG123.json").exists(), "the sidecar did not move to the root"


def test_ac5_the_sidecar_is_still_named_from_the_TOKEN_not_the_title(monkeypatch, tmp_path):
    """The other half of the same convention, pinned so the fence covers the whole naming
    rule rather than only the directory."""
    result = run(monkeypatch, tmp_path, PLAIN_MD, dump=True)
    assert pathlib.Path(result.dump_path).name == "AbCdEfG123.json"


# --------------------------------------------------------------------------- #
# AC6 — the front door moves in the same change.                               #
# --------------------------------------------------------------------------- #

def _shipped_guide():
    from larkdocio import guide

    return guide(full=True)


def _docx_recipe_section():
    """The docx-read recipe, heading to the next ``###`` — off the SHIPPED guide."""
    text = _shipped_guide()
    start = text.index("### Recipe: download a docx to Markdown")
    nxt = text.find("\n### ", start + 1)
    return text[start:] if nxt == -1 else text[start:nxt]


def _result_field_names():
    """Every public field of the result type, read off the TYPE — never restated here."""
    return sorted(
        name for name, value in vars(DownloadResult).items()
        if isinstance(value, property)
    )


def test_ac6_the_docx_read_recipe_SHOWS_the_returned_value_being_used():
    """A returned value nobody is shown using is a value nobody finds. Held against the type's
    own property names, so renaming a field without correcting the guide reddens."""
    section = _docx_recipe_section()
    assert "DownloadResult" in section
    missing = [name for name in _result_field_names() if f"result.{name}" not in section]
    assert missing == [], (
        f"the docx-read recipe never shows {missing} being read — the fields are the one "
        f"detail a hand-written recipe gets wrong")


def test_ac6_the_recipe_shows_the_DICT_access_the_shape_promises():
    """The other half of the dict-compatible grammar: a consumer must see that subscripting
    works, or the promise is invisible."""
    assert 'result["output_dir"]' in _docx_recipe_section()


def test_ac6_the_recipe_states_the_reason_VOCABULARY_the_code_can_emit():
    """Every reason the code can answer is named in the guide, and no reason it cannot."""
    section = _docx_recipe_section()
    live = {download.ROUTE_EXPLICIT, download.ROUTE_DISABLED}
    for reason in live:
        assert reason in section, reason
    # TIGHTENED by LD-650, and this is the half that was missing: the arm asserted only
    # PRESENCE, so a guide still naming a RETIRED reason passed it green. Now the two sets
    # must be equal — every reason the code can answer is named, and no reason it cannot.
    named = {
        token.strip("`,|")
        for line in section.splitlines() if "route_reason" in line
        for token in line.replace("#", " ").split()
    }
    assert live <= named, f"the recipe does not name every live reason: {sorted(named)}"


@private_tree.dev_record
def test_ac6_the_recipe_names_no_RETIRED_reason_value():
    """The LD-650 tightening's other half: no reason the code can no longer answer is named.
    The retired values are read from the private ledger (LD-704: the public tree does not
    carry them)."""
    from retired_particulars import load

    section = _docx_recipe_section()
    named = {
        token.strip("`,|")
        for line in section.splitlines() if "route_reason" in line
        for token in line.replace("#", " ").split()
    }
    retired = set(load("retired_route_reasons"))
    assert not (named & retired), f"the recipe still names a retired reason value: {sorted(named)}"
    assert not {r for r in retired if r in section}, "a retired reason value is in the recipe"


def test_ac6_the_routing_section_says_the_decision_is_returned_AND_carries_no_path():
    """The routing section is where a reader goes with *"where did my file go"*; it must point
    at the value, and it must state the fence rather than leaving it to be discovered."""
    text = _shipped_guide()
    start = text.index("### Where the file lands: `-o`, and `--route` when you name the subpath")
    section = text[start:text.find("\n### ", start + 1)]
    assert "result.route_reason" in section and "route`" in section
    assert "carries no path" in section


def test_ac6_the_new_consumer_prose_carries_NO_internal_dialect():
    """Consumer-reaching text: no issue id, no decision id, no repo path, no role tag."""
    import re as _re

    for section in (_docx_recipe_section(), ):
        assert not _re.search(r"\bLD-\d+\b", section)
        assert not _re.search(r"\bD-\d+\b", section)
        assert not _re.search(r"\bAC\d+\b", section)
        assert "src/" not in section and "tests/" not in section


# --------------------------------------------------------------------------- #
# The zero-drift half: the MARKDOWN is untouched by all of the above.          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("markdown", [TABLE_MD, PARTIAL_TABLE_MD, PLAIN_MD])
def test_the_written_markdown_is_byte_identical_to_its_input(monkeypatch, tmp_path, markdown):
    """Reporting a decision changes no output. The reader emits exactly what it emitted."""
    result = run(monkeypatch, tmp_path, markdown)
    assert pathlib.Path(result.output_path).read_text(encoding="utf-8") == markdown
