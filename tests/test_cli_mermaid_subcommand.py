"""LD-211 — `larkdocio mermaid`: a spec in, STRICT Mermaid source out, on the right stream.

The command is a **transport**, so every assertion about the bytes it emits compares them to
what ``flowchart(spec)`` / ``sequence(spec)`` return for the same spec. A test that spelled the
expected source out by hand would prove that two hand-written strings agree and would go on
passing after the CLI started re-indenting, wrapping or newline-terminating its output.

Three properties carry the issue:

* **stdout carries ONLY diagram source.** ``cli.py``'s shared-logger handler used to be
  attached to ``sys.stdout``, and LD-207 deliberately **keeps** the two ADVISORY rules
  warning — so on a diagram big enough to trip the advisory ceiling the warning was emitted
  into the same stream as the source, producing a ``.mmd`` that is not valid Mermaid. That is
  a **corrupt artifact rather than an error**, so it is the one defect here a small fixture
  never shows: every stream-separation test below uses a diagram that really warns, and
  :func:`_advisory_lines` proves the warning happened rather than assuming it.
* **The kind is STATED, never guessed.** ``--flowchart`` / ``--sequence`` or a spec ``"kind"``
  key. Neither refuses; two that disagree refuse. The keys a spec happens to carry
  (``nodes``/``edges`` vs ``participants``/``messages``) are **never consulted** — that is the
  guessing LD-207 just finished removing from this module, and it must not reappear at its
  front door.
* **A refusal leaves nothing behind.** Non-zero exit, the compiler's own detail on stderr, no
  traceback, **empty stdout**, and — on the ``-o`` path — no output file created and a
  pre-existing one byte-unchanged. A half-written ``.mmd`` is a data-loss bug in miniature.
"""
import contextlib
import json
import logging
import pathlib
import re
import subprocess
import sys

import pytest
from click.testing import CliRunner

import consumer_text
import front_door as fd
from consumer_text import cli_group, dialect_hits
from larkdocio.cli import cli
from larkdocio.mermaid import COMPLEXITY_LIMIT, VERTICAL_PREFERRED_ABOVE, flowchart, sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Fixtures — a clean shared logger, and the two streams kept APART              #
# --------------------------------------------------------------------------- #

@contextlib.contextmanager
def _isolated_larkdocio_logger():
    """Snapshot/restore the shared ``larkdocio`` logger (the test_cli_logging_config contract).

    Load-bearing here, not hygiene: ``_configure_logging`` is idempotent per process, so a
    handler left over from an earlier test in this session would still be bound to that
    session's stream and the stream-separation assertions would read an empty ``stderr`` and
    pass for the wrong reason.
    """
    logger = logging.getLogger("larkdocio")
    saved_handlers, saved_level = logger.handlers[:], logger.level
    logger.handlers.clear()
    logger.setLevel(logging.NOTSET)
    try:
        yield logger
    finally:
        logger.handlers[:] = saved_handlers
        logger.setLevel(saved_level)


def run(args, stdin=None):
    """Invoke the CLI with stdout and stderr kept **separate**, on a clean shared logger."""
    with _isolated_larkdocio_logger():
        return CliRunner().invoke(cli, args, input=stdin, catch_exceptions=True)


def _advisory_lines(stderr):
    """The advisory-rule warnings in ``stderr`` — the proof a stream test is not trivial."""
    return [
        line for line in stderr.splitlines()
        if "past the advisory ceiling" in line or "is scaled down to fit the page width" in line
    ]


# --------------------------------------------------------------------------- #
# Specs                                                                        #
# --------------------------------------------------------------------------- #

FLOW = {
    "direction": "TD",
    "title": "Approval flow",
    "nodes": [
        {"id": "A", "label": "Draft"},
        {"id": "B", "label": "In review"},
        {"id": "C", "label": "Shipped"},
    ],
    "edges": [{"from": "A", "to": "B"}, {"from": "B", "to": "C", "label": "approved"}],
}

SEQ = {
    "title": "Authentication",
    "participants": [{"id": "Client", "label": "Mobile App"}, {"id": "Gateway"}],
    "messages": [
        {"from": "Client", "to": "Gateway", "label": "1. POST /login"},
        {"from": "Gateway", "to": "Client", "label": "2. token", "style": "dotted"},
    ],
}


def _big_flowchart():
    """A vertical flowchart whose complexity really exceeds the advisory ceiling.

    16 nodes + 15 edges = 31 > 30, and ``TD`` so the *other* advisory rule stays silent and
    the two are separable.
    """
    ids = [f"N{index}" for index in range(16)]
    return {
        "direction": "TD",
        "nodes": [{"id": node_id, "label": f"Step {node_id}"} for node_id in ids],
        "edges": [{"from": a, "to": b} for a, b in zip(ids, ids[1:])],
    }


def _wide_horizontal_flowchart():
    """An ``LR`` flowchart with more nodes than the vertical-preferred threshold, and a
    complexity **under** the ceiling — so exactly one advisory rule fires."""
    ids = [f"W{index}" for index in range(VERTICAL_PREFERRED_ABOVE + 1)]
    return {
        "direction": "LR",
        "nodes": [{"id": node_id} for node_id in ids],
        "edges": [{"from": ids[0], "to": ids[1]}],
    }


def _write(tmp_path, spec, name="spec.json"):
    path = tmp_path / name
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# AC1 — a spec from a FILE or STDIN, source to STDOUT or a FILE                  #
# --------------------------------------------------------------------------- #

def test_ac1_file_to_stdout(tmp_path):
    result = run(["mermaid", "--flowchart", str(_write(tmp_path, FLOW))])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == flowchart(FLOW)


def test_ac1_stdin_to_stdout_with_the_dash(tmp_path):
    result = run(["mermaid", "--flowchart", "-"], stdin=json.dumps(FLOW))
    assert result.exit_code == 0, result.stderr
    assert result.stdout == flowchart(FLOW)


def test_ac1_stdin_to_stdout_with_no_argument_at_all():
    """The pipeline shape the consumer review asked for verbatim:
    ``cat spec.json | larkdocio mermaid --flowchart > out.mmd``."""
    result = run(["mermaid", "--flowchart"], stdin=json.dumps(FLOW))
    assert result.exit_code == 0, result.stderr
    assert result.stdout == flowchart(FLOW)


def test_ac1_file_to_file(tmp_path):
    out = tmp_path / "out.mmd"
    result = run(["mermaid", "--flowchart", str(_write(tmp_path, FLOW)), "-o", str(out)])
    assert result.exit_code == 0, result.stderr
    assert out.read_text(encoding="utf-8") == flowchart(FLOW)


def test_ac1_stdin_to_file(tmp_path):
    out = tmp_path / "out.mmd"
    result = run(["mermaid", "--sequence", "-", "--output", str(out)], stdin=json.dumps(SEQ))
    assert result.exit_code == 0, result.stderr
    assert out.read_text(encoding="utf-8") == sequence(SEQ)


def test_ac1_the_output_file_path_is_NOT_echoed_onto_stdout(tmp_path):
    """``-o`` means the source went to a file; stdout still carries only diagram source, and
    with the file taking the source that means **nothing**."""
    out = tmp_path / "out.mmd"
    result = run(["mermaid", "--flowchart", str(_write(tmp_path, FLOW)), "-o", str(out)])
    assert result.stdout == ""


def test_ac1_the_sequence_compiler_is_reachable_too(tmp_path):
    result = run(["mermaid", "--sequence", str(_write(tmp_path, SEQ))])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == sequence(SEQ)


def test_ac1_the_cli_appends_NO_trailing_newline_the_library_does_not(tmp_path):
    """The transport property, stated as its own test because a stray ``\\n`` is exactly the
    divergence nobody notices until a byte comparison downstream fails."""
    source = flowchart(FLOW)
    assert not source.endswith("\n")
    result = run(["mermaid", "--flowchart", str(_write(tmp_path, FLOW))])
    assert result.stdout == source and not result.stdout.endswith("\n")


# --------------------------------------------------------------------------- #
# AC2 — the kind is STATED, never guessed                                       #
# --------------------------------------------------------------------------- #

def test_ac2_a_spec_KEY_declares_the_kind(tmp_path):
    spec = dict(FLOW, kind="flowchart")
    result = run(["mermaid", str(_write(tmp_path, spec))])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == flowchart(spec)


def test_ac2_no_kind_anywhere_REFUSES(tmp_path):
    result = run(["mermaid", str(_write(tmp_path, FLOW))])
    assert result.exit_code != 0
    assert result.stdout == ""
    assert "kind" in result.stderr
    assert "--flowchart" in result.stderr and "--sequence" in result.stderr


def test_ac2_the_no_kind_refusal_does_not_hint_that_the_KEYS_could_have_answered(tmp_path):
    """The refusal must not teach the guess it exists to prevent."""
    stderr = run(["mermaid", str(_write(tmp_path, FLOW))]).stderr
    assert "nodes" not in stderr and "edges" not in stderr


def test_ac2_two_flags_that_disagree_REFUSE(tmp_path):
    result = run(["mermaid", "--flowchart", "--sequence", str(_write(tmp_path, FLOW))])
    assert result.exit_code != 0
    assert result.stdout == ""
    assert "--flowchart" in result.stderr and "--sequence" in result.stderr


def test_ac2_a_flag_that_contradicts_the_spec_key_REFUSES_rather_than_picking_a_winner(tmp_path):
    spec = dict(FLOW, kind="sequence")
    result = run(["mermaid", "--flowchart", str(_write(tmp_path, spec))])
    assert result.exit_code != 0
    assert result.stdout == ""
    assert "'sequence'" in result.stderr and "--flowchart" in result.stderr


def test_ac2_a_flag_that_AGREES_with_the_spec_key_is_not_a_conflict(tmp_path):
    spec = dict(FLOW, kind="flowchart")
    result = run(["mermaid", "--flowchart", str(_write(tmp_path, spec))])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == flowchart(spec)


def test_ac2_an_unknown_kind_in_the_spec_REFUSES_naming_the_valid_set(tmp_path):
    result = run(["mermaid", str(_write(tmp_path, dict(FLOW, kind="mindmap")))])
    assert result.exit_code != 0
    assert result.stdout == ""
    assert "'mindmap'" in result.stderr
    assert "flowchart" in result.stderr and "sequence" in result.stderr


def test_ac2_THE_DECLARATION_WINS_AND_THE_KEYS_ARE_NEVER_CONSULTED(tmp_path):
    """The load-bearing anti-guessing test: a spec carrying ``nodes``/``edges`` — which *look*
    like a flowchart — but declaring ``sequence`` compiles as a **sequence diagram**, byte for
    byte what ``sequence(spec)`` returns. If the keys were consulted at all this comes back as
    flowchart source instead."""
    spec = dict(FLOW, kind="sequence")
    result = run(["mermaid", "--sequence", str(_write(tmp_path, spec))])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == sequence(spec)
    assert result.stdout != flowchart(dict(spec, kind="flowchart"))
    assert "flowchart" not in result.stdout


def test_ac2_and_the_mirror_image_participant_keys_declared_as_a_flowchart(tmp_path):
    """The other direction, so the property is not an artifact of one compiler being lenient
    about a spec shaped for the other."""
    spec = dict(SEQ, kind="flowchart")
    result = run(["mermaid", str(_write(tmp_path, spec))])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == flowchart(spec)
    assert result.stdout.splitlines()[1] == "flowchart TD"


def test_ac2_the_kind_key_never_reaches_the_compilers_as_a_spec_key(tmp_path):
    """``kind`` is the CLI's declaration, not a dialect widening: compiling with it and
    without it produces the same bytes."""
    with_kind = run(["mermaid", str(_write(tmp_path, dict(FLOW, kind="flowchart")))])
    assert with_kind.stdout == flowchart(FLOW)


# --------------------------------------------------------------------------- #
# AC3 — a refusal: non-zero, typed message on STDERR, no traceback, empty stdout #
# --------------------------------------------------------------------------- #

#: ``(id, argv-tail, spec-or-None, a fragment the message MUST name)``. ``spec=None`` means the
#: case supplies its own input; otherwise the spec is written to a file.
COMPILER_REFUSALS = [
    ("edge-names-no-node", ["--flowchart"],
     {"nodes": [{"id": "A"}], "edges": [{"from": "A", "to": "ZZ"}]}, "'ZZ'"),
    ("message-names-no-participant", ["--sequence"],
     {"participants": [{"id": "A"}], "messages": [{"from": "A", "to": "GHOST"}]}, "'GHOST'"),
    ("unknown-shape", ["--flowchart"],
     {"nodes": [{"id": "A", "shape": "hexagon"}]}, "'hexagon'"),
    ("unknown-direction", ["--flowchart"],
     {"direction": "XX", "nodes": [{"id": "A"}]}, "'XX'"),
    ("label-on-an-invisible-edge", ["--flowchart"],
     {"nodes": [{"id": "A"}, {"id": "B"}],
      "edges": [{"from": "A", "to": "B", "style": "invisible", "label": "never appears"}]},
     "invisible"),
    ("nameless-node", ["--flowchart"], {"nodes": [{"id": "   "}]}, "position 1"),
    ("nameless-participant", ["--sequence"], {"participants": [{"id": ""}]}, "position 1"),
    ("subgraph-names-no-node", ["--flowchart"],
     {"nodes": [{"id": "A"}], "subgraphs": [{"id": "g1", "nodes": ["MISSING"]}]}, "'MISSING'"),
    ("nameless-subgraph", ["--flowchart"],
     {"nodes": [{"id": "A"}], "subgraphs": [{"id": " ", "nodes": ["A"]}]}, "position 1"),
    ("edge-length-out-of-range", ["--flowchart"],
     {"nodes": [{"id": "A"}, {"id": "B"}],
      "edges": [{"from": "A", "to": "B", "length": 9}]}, "1 to 5"),
    ("edge-length-not-a-number", ["--flowchart"],
     {"nodes": [{"id": "A"}, {"id": "B"}],
      "edges": [{"from": "A", "to": "B", "length": "far"}]}, "not a whole number"),
    ("unknown-edge-style", ["--flowchart"],
     {"nodes": [{"id": "A"}, {"id": "B"}],
      "edges": [{"from": "A", "to": "B", "style": "wavy"}]}, "'wavy'"),
    ("unknown-message-style", ["--sequence"],
     {"participants": [{"id": "A"}],
      "messages": [{"from": "A", "to": "A", "style": "wavy"}]}, "'wavy'"),
    ("unknown-legacy-arrow", ["--sequence"],
     {"participants": [{"id": "A"}],
      "messages": [{"from": "A", "to": "A", "type": "=>"}]}, "'=>'"),
    ("unknown-theme", ["--flowchart"],
     {"theme": "purple", "nodes": [{"id": "A"}]}, "'purple'"),
]

#: This command's own refusal classes, on top of the compilers'.
TRANSPORT_REFUSALS = ["unreadable-file", "malformed-json", "not-an-object",
                      "no-kind", "conflicting-kinds", "unknown-kind"]


def _invoke_refusal(case, tmp_path, out=None):
    """Run one refusal case; returns ``(result, fragment)``."""
    tail = ["-o", str(out)] if out is not None else []
    if case == "unreadable-file":
        return run(["mermaid", "--flowchart", str(tmp_path / "absent.json")] + tail), "absent.json"
    if case == "malformed-json":
        path = tmp_path / "bad.json"
        path.write_text('{"nodes": [}', encoding="utf-8")
        return run(["mermaid", "--flowchart", str(path)] + tail), "line 1 column"
    if case == "not-an-object":
        path = tmp_path / "list.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        return run(["mermaid", "--flowchart", str(path)] + tail), "list"
    if case == "no-kind":
        return run(["mermaid", str(_write(tmp_path, FLOW))] + tail), "kind"
    if case == "conflicting-kinds":
        return run(
            ["mermaid", "--flowchart", "--sequence", str(_write(tmp_path, FLOW))] + tail
        ), "--sequence"
    if case == "unknown-kind":
        return run(
            ["mermaid", str(_write(tmp_path, dict(FLOW, kind="mindmap")))] + tail
        ), "'mindmap'"
    name, flags, spec, fragment = next(row for row in COMPILER_REFUSALS if row[0] == case)
    return run(["mermaid"] + flags + [str(_write(tmp_path, spec))] + tail), fragment


ALL_REFUSALS = [row[0] for row in COMPILER_REFUSALS] + TRANSPORT_REFUSALS


@pytest.mark.parametrize("case", ALL_REFUSALS)
def test_ac3_every_refusal_class_exits_nonzero_names_the_construct_and_leaves_stdout_EMPTY(
    case, tmp_path
):
    result, fragment = _invoke_refusal(case, tmp_path)
    assert result.exit_code != 0, f"{case} exited 0"
    assert result.stdout == "", f"{case} wrote to stdout: {result.stdout!r}"
    assert fragment in result.stderr, f"{case} stderr does not name {fragment!r}: {result.stderr!r}"
    assert "Traceback (most recent call last)" not in result.stderr
    assert "Traceback (most recent call last)" not in result.stdout
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        f"{case} let an exception escape to click's runner: {result.exception!r}"
    )


@pytest.mark.parametrize("case", ALL_REFUSALS)
def test_ac3_no_refusal_class_leaves_a_PARTIAL_OUTPUT_FILE_behind(case, tmp_path):
    out = tmp_path / "out.mmd"
    result, _ = _invoke_refusal(case, tmp_path, out=out)
    assert result.exit_code != 0
    assert not out.exists(), f"{case} created {out.name} anyway"


@pytest.mark.parametrize("case", ALL_REFUSALS)
def test_ac3_no_refusal_class_TRUNCATES_AN_EXISTING_OUTPUT_FILE(case, tmp_path):
    out = tmp_path / "out.mmd"
    out.write_bytes(b"flowchart TD\n    A[Keep me]")
    before = out.read_bytes()
    result, _ = _invoke_refusal(case, tmp_path, out=out)
    assert result.exit_code != 0
    assert out.read_bytes() == before, f"{case} rewrote an existing output file"


def test_ac3_the_malformed_json_refusal_names_the_PARSE_POSITION_not_merely_that_it_failed(
    tmp_path
):
    path = tmp_path / "bad.json"
    path.write_text('{\n  "nodes": [\n  {"id": "A"},,\n  ]\n}\n', encoding="utf-8")
    result = run(["mermaid", "--flowchart", str(path)])
    assert result.exit_code != 0
    assert re.search(r"line \d+ column \d+ \(char \d+\)", result.stderr), result.stderr
    assert str(path) in result.stderr


def test_ac3_an_EMPTY_stdin_refuses_rather_than_emitting_an_empty_diagram():
    result = run(["mermaid", "--flowchart", "-"], stdin="")
    assert result.exit_code != 0
    assert result.stdout == ""
    assert "Traceback (most recent call last)" not in result.stderr


def test_ac3_a_REAL_PROCESS_shows_no_traceback_and_exits_nonzero(tmp_path):
    """Click's runner never prints a traceback, so the no-traceback promise is also checked
    where a consumer would see one: a real child process with a real exit status."""
    path = tmp_path / "spec.json"
    path.write_text(json.dumps({"theme": "purple", "nodes": [{"id": "A"}]}), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "larkdocio.cli", "mermaid", "--flowchart", str(path)],
        cwd=str(tmp_path), capture_output=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO_ROOT / "src"),
             "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert proc.returncode != 0
    assert proc.stdout == b""
    stderr = proc.stderr.decode("utf-8", "replace")
    assert "'purple'" in stderr
    assert "Traceback (most recent call last)" not in stderr
    assert "LarkConfigError" not in stderr, "the exception class name leaked into the message"


# --------------------------------------------------------------------------- #
# AC4 — STDOUT CARRIES ONLY DIAGRAM SOURCE (the load-bearing test)              #
# --------------------------------------------------------------------------- #

def test_ac4_the_probe_diagram_really_TRIPS_the_advisory_ceiling():
    """Precondition, pinned first: if this stops being true the two tests below pass
    trivially and prove nothing — which is the whole failure mode AC4 exists for."""
    spec = _big_flowchart()
    assert len(spec["nodes"]) + len(spec["edges"]) > COMPLEXITY_LIMIT


def test_ac4_a_diagram_PAST_THE_CEILING_puts_source_on_stdout_and_the_warning_on_stderr(
    tmp_path
):
    spec = _big_flowchart()
    result = run(["mermaid", "--flowchart", str(_write(tmp_path, spec))])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == flowchart(spec), (
        "stdout is not byte-identical to the compiler's own return value — something other "
        "than diagram source reached it"
    )
    assert "advisory ceiling" not in result.stdout
    assert _advisory_lines(result.stderr) != [], (
        "the warning did not appear on stderr either, so this test proved nothing"
    )
    assert str(COMPLEXITY_LIMIT) in result.stderr


def test_ac4_the_WIDE_HORIZONTAL_rule_behaves_the_same_way(tmp_path):
    spec = _wide_horizontal_flowchart()
    assert len(spec["nodes"]) > VERTICAL_PREFERRED_ABOVE
    assert len(spec["nodes"]) + len(spec["edges"]) <= COMPLEXITY_LIMIT
    result = run(["mermaid", "--flowchart", str(_write(tmp_path, spec))])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == flowchart(spec)
    assert "scaled down" not in result.stdout
    warnings = _advisory_lines(result.stderr)
    assert len(warnings) == 1 and "scaled down" in warnings[0], result.stderr


def test_ac4_the_OUTPUT_FILE_carries_only_source_when_a_warning_fires(tmp_path):
    """The corrupt-artifact failure in its most literal form: the ``.mmd`` on disk."""
    spec = _big_flowchart()
    out = tmp_path / "out.mmd"
    result = run(["mermaid", "--flowchart", str(_write(tmp_path, spec)), "-o", str(out)])
    assert result.exit_code == 0, result.stderr
    assert out.read_text(encoding="utf-8") == flowchart(spec)
    assert "advisory ceiling" not in out.read_text(encoding="utf-8")
    assert _advisory_lines(result.stderr) != []


def test_ac4_a_REAL_PIPE_gets_only_the_source_bytes(tmp_path):
    """The property where it actually bites: a shell redirect into a file. Run as a child
    process so the streams are real file descriptors, not click's buffers."""
    spec = _big_flowchart()
    path = _write(tmp_path, spec)
    proc = subprocess.run(
        [sys.executable, "-m", "larkdocio.cli", "mermaid", "--flowchart", str(path)],
        cwd=str(tmp_path), capture_output=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO_ROOT / "src"),
             "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")[-2000:]
    assert proc.stdout == flowchart(spec).encode("utf-8")
    assert b"advisory ceiling" in proc.stderr


def test_ac4_the_CLI_LOG_HANDLER_IS_ON_STDERR_NOW(tmp_path):
    """The fix, at the level it was made: the shared logger's CLI handler. Stated as its own
    test because it is the **blast radius** — every INFO line `download` prints moves with it,
    which RELEASE_NOTES.md carries as a separately-stated observable change."""
    from larkdocio.cli import _configure_logging

    with _isolated_larkdocio_logger() as logger:
        _configure_logging()
        handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        assert len(handlers) == 1
        assert handlers[0].stream is sys.stderr
        assert handlers[0].stream is not sys.stdout


def test_ac4_a_diagram_UNDER_the_ceiling_writes_nothing_to_stderr_at_all(tmp_path):
    """The must-not-bite: routing warnings to stderr must not make the ordinary case noisy."""
    result = run(["mermaid", "--flowchart", str(_write(tmp_path, FLOW))])
    assert result.exit_code == 0
    assert result.stdout == flowchart(FLOW)
    assert result.stderr == ""


# --------------------------------------------------------------------------- #
# AC5 — truthful `--help`, and it does not overclaim                            #
# --------------------------------------------------------------------------- #

def _help_page():
    return consumer_text.cli_help_pages()["larkdocio mermaid --help"]


def test_ac5_the_help_page_is_ENROLLED_in_the_guarded_corpus():
    assert "larkdocio mermaid --help" in consumer_text.cli_help_pages()
    assert "larkdocio mermaid --help" in consumer_text.consumer_corpus()


@pytest.mark.parametrize("claim", [
    "no credentials",
    "no network",
    "no document is touched",
])
def test_ac5_the_help_states_the_PURITY_claim(claim):
    """The reason an agent can call this with no setup at all — so it has to be on the page,
    not merely true."""
    assert claim in _help_page().lower()


def test_ac5_the_help_says_what_goes_IN_and_what_comes_OUT():
    page = _help_page().lower()
    assert "spec" in page and "json" in page
    assert "mermaid source" in page
    assert "stdout" in page


def test_ac5_the_help_names_HOW_THE_KIND_IS_CHOSEN():
    page = _help_page()
    assert "--flowchart" in page and "--sequence" in page
    assert "kind" in page.lower()


def test_ac5_the_help_says_an_off_dialect_spec_REFUSES():
    page = _help_page().lower()
    assert "refuse" in page
    for silent in ("silently corrected", "falls back", "is dropped"):
        assert silent not in page


def test_ac5_the_help_does_NOT_claim_it_writes_a_diagram_into_a_document():
    page = _help_page()
    # Click hard-wraps the page, so the sentence is matched against collapsed whitespace —
    # the claim is the words, not where the renderer chose to break the line.
    assert "never writes a diagram into a Lark document" in " ".join(page.split()), page
    assert "insert" not in page.lower()
    assert "upload" not in page.lower()


def test_ac5_the_help_disambiguates_its_own_o_from_downloads_o():
    """``-o`` is an output **file** here and an output **directory** on ``download``: same
    letter, sibling subcommands, so the page must say which."""
    page = _help_page()
    assert re.search(r"-o, --output", page)
    assert "file" in page.lower()
    assert "directory" not in page.lower(), "the -o help must not read as a directory"


def test_ac5_the_help_page_is_DIALECT_FREE():
    assert dialect_hits(_help_page()) == []


def test_ac5_the_dialect_guard_BITES_on_a_string_added_to_THIS_page(monkeypatch):
    """The red-proof for the newly-enrolled page: an injection has to be caught *through the
    corpus*, so the enrolment is real and not a coincidence of the page being clean."""
    assert consumer_text.corpus_dialect_report() == [], "the corpus must be clean first"
    option = next(
        p for p in cli_group().commands["mermaid"].params if p.name == "output_file"
    )
    monkeypatch.setattr(option, "help", "Write the source here (see LD-207 § AC3).")
    caught = [
        (label, matched) for label, _n, matched, _s in consumer_text.corpus_dialect_report()
    ]
    assert ("larkdocio mermaid --help", "LD-207") in caught, caught


# --------------------------------------------------------------------------- #
# AC6 — it works FROM AN INSTALLED WHEEL (the LD-193 clean-venv standard)        #
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def clean_venv():
    """A throwaway venv with the built wheel installed **offline**, or a skip.

    LD-355: moved verbatim to ``front_door.clean_wheel_venv`` — this fixture and
    ``test_cli_front_door_truth``'s were byte-identical, and the venv is now produced once
    per RUN instead of once per worker that receives one of these tests.
    """
    return fd.clean_wheel_venv()


def _installed_source(clean_venv, tmp_path, kind, spec):
    """``flowchart(spec)`` / ``sequence(spec)`` as computed **by the installed wheel**."""
    probe = (
        "import json, sys\n"
        f"from larkdocio.mermaid import {kind}\n"
        "spec = json.load(sys.stdin)\n"
        f"sys.stdout.buffer.write({kind}(spec).encode('utf-8'))\n"
        "sys.stderr.write(__import__('larkdocio').__file__)\n"
    )
    out = subprocess.run([str(clean_venv["python"]), "-c", probe], cwd=str(tmp_path),
                         input=json.dumps(spec).encode("utf-8"),
                         capture_output=True, env=clean_venv["env"])
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")[-2000:]
    where = out.stderr.decode("utf-8", "replace")
    assert "/v/" in where or "\\v\\" in where, (
        f"the probe imported {where}, not the installed copy in the clean venv"
    )
    return out.stdout


def test_ac6_the_FILE_form_works_from_an_installed_wheel(clean_venv, tmp_path):
    path = _write(tmp_path, FLOW)
    expected = _installed_source(clean_venv, tmp_path, "flowchart", FLOW)
    run_out = subprocess.run(
        [str(clean_venv["console"]), "mermaid", "--flowchart", str(path)],
        cwd=str(tmp_path), capture_output=True, env=clean_venv["env"],
    )
    assert run_out.returncode == 0, run_out.stderr.decode("utf-8", "replace")[-2000:]
    assert run_out.stdout == expected
    assert run_out.stderr == b""


def test_ac6_the_STDIN_form_works_from_an_installed_wheel(clean_venv, tmp_path):
    expected = _installed_source(clean_venv, tmp_path, "sequence", SEQ)
    run_out = subprocess.run(
        [str(clean_venv["console"]), "mermaid", "--sequence", "-"],
        cwd=str(tmp_path), input=json.dumps(SEQ).encode("utf-8"),
        capture_output=True, env=clean_venv["env"],
    )
    assert run_out.returncode == 0, run_out.stderr.decode("utf-8", "replace")[-2000:]
    assert run_out.stdout == expected


def test_ac6_a_REFUSAL_exits_nonzero_from_an_installed_wheel(clean_venv, tmp_path):
    path = _write(tmp_path, {"nodes": [{"id": "A"}], "edges": [{"from": "A", "to": "ZZ"}]},
                  name="broken.json")
    run_out = subprocess.run(
        [str(clean_venv["console"]), "mermaid", "--flowchart", str(path)],
        cwd=str(tmp_path), capture_output=True, env=clean_venv["env"],
    )
    assert run_out.returncode != 0
    assert run_out.stdout == b""
    stderr = run_out.stderr.decode("utf-8", "replace")
    assert "'ZZ'" in stderr
    assert "Traceback (most recent call last)" not in stderr


def test_ac6_the_clean_venv_run_is_not_secretly_reading_THE_REPO(clean_venv, tmp_path):
    assert not (tmp_path / "src").exists()
    assert not (tmp_path / "pyproject.toml").exists()


# --------------------------------------------------------------------------- #
# AC7 — the front-door guards are satisfied HONESTLY, with both mutations        #
# --------------------------------------------------------------------------- #

def _readme():
    return fd.readme_text()


def test_ac7_every_option_of_the_new_command_is_in_the_README():
    readme = _readme()
    options = fd.all_command_options()["larkdocio mermaid"]
    assert options == {"-o", "--output", "--flowchart", "--sequence"}
    missing = sorted(option for option in options if option not in readme)
    assert missing == [], missing


def test_ac7_the_README_documents_the_subcommand_ITSELF_not_only_its_flags():
    readme = _readme()
    assert "`mermaid`" in readme
    assert "larkdocio mermaid" in readme


def test_ac7_MUTATION_removing_the_option_documentation_REDDENS(monkeypatch):
    """Direction one: strip the two kind flags out of the README and the forward guard fires."""
    stripped = _readme().replace("--flowchart", "").replace("--sequence", "")
    monkeypatch.setattr(fd, "readme_text", lambda: stripped)
    missing = {
        label: sorted(option for option in options if option not in fd.readme_text())
        for label, options in fd.all_command_options().items()
    }
    assert sorted(missing["larkdocio mermaid"]) == ["--flowchart", "--sequence"]


def test_ac7_MUTATION_an_undocumented_NEW_option_on_this_command_REDDENS():
    """Direction two: a flag nobody documented, measured through the real README."""
    readme = _readme()
    invented = fd.all_command_options()["larkdocio mermaid"] | {"--pretty"}
    assert sorted(o for o in invented if o not in readme) == ["--pretty"]


def test_ac7_the_README_shows_no_PHANTOM_flag_being_passed_to_larkdocio():
    real = set().union(*fd.all_command_options().values())
    phantom = sorted(fd.invocation_option_tokens(_readme()) - real)
    assert phantom == [], phantom


# --------------------------------------------------------------------------- #
# AC8 — the guide documents it where a consumer will meet it                     #
# --------------------------------------------------------------------------- #

#: The guide's CLI-variant heading inside the mermaid recipe.
CLI_VARIANT_HEADING = "**The CLI variant — `larkdocio mermaid`**"

_SHELL_FENCE_RE = re.compile(r"```bash\n(.*?)```", re.DOTALL)


def _guide_cli_variant(text=None):
    """The mermaid recipe's CLI-variant passage, from its heading to the next ``###``."""
    import larkdocio

    text = larkdocio.guide(full=True) if text is None else text
    start = text.find(CLI_VARIANT_HEADING)
    assert start != -1, "the guide has no `larkdocio mermaid` CLI variant"
    rest = text[start:]
    end = rest.find("\n### ")
    return rest if end == -1 else rest[:end]


def test_ac8_the_guide_carries_a_CLI_VARIANT_of_the_mermaid_recipe():
    passage = _guide_cli_variant()
    assert "larkdocio mermaid" in passage
    assert "--flowchart" in passage


def test_ac8_the_documented_HAPPY_PATH_command_really_runs_and_emits_what_it_says(tmp_path):
    """The guide's shell fences are the one thing the extract-and-run harness cannot execute,
    so they are executed here instead — through click's own runner, with the spec the guide
    shows, asserting the documented first lines really come back."""
    passage = _guide_cli_variant()
    spec = json.loads(_SHELL_FENCE_RE.findall(passage)[0].split("<<'JSON'\n", 1)[1]
                      .split("\nJSON", 1)[0])
    result = run(["mermaid", "--flowchart", str(_write(tmp_path, spec))])
    assert result.exit_code == 0, result.stderr
    assert result.stdout == flowchart(spec)
    for documented in ("%%{init:", "flowchart TD"):
        assert documented in passage, f"the guide does not show {documented!r}"
        assert documented in result.stdout


def test_ac8_the_documented_REFUSAL_example_really_refuses_with_the_documented_message(
    tmp_path
):
    """The refusal IS the feature, so the guide's refusal example is executed too."""
    passage = _guide_cli_variant()
    assert "exit status" in passage.lower() or "non-zero" in passage.lower()
    broken = {"nodes": [{"id": "A", "label": "Draft"}], "edges": [{"from": "A", "to": "ZZ"}]}
    assert '"to": "ZZ"' in passage, "the guide's refusal example no longer uses ZZ"
    result = run(["mermaid", "--flowchart", str(_write(tmp_path, broken))])
    assert result.exit_code != 0
    assert result.stdout == ""
    assert "which no node defines" in result.stderr
    assert "which no node defines" in passage


def test_ac8_the_guide_edit_SHIPS_in_the_wheel(clean_venv, tmp_path):
    """A guide edit that is not in the wheel answers nobody: the passage is read back out of
    the installed package's own ``guide()``."""
    import larkdocio

    out = subprocess.run(
        [str(clean_venv["python"]), "-c",
         "import sys, larkdocio; sys.stdout.buffer.write(larkdocio.guide(full=True).encode('utf-8'))"],
        cwd=str(tmp_path), capture_output=True, env=clean_venv["env"],
    )
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")[-2000:]
    shipped = out.stdout.decode("utf-8")
    assert shipped == larkdocio.guide(full=True), "the in-wheel guide is not the source guide"
    assert _guide_cli_variant(shipped) == _guide_cli_variant()


# --------------------------------------------------------------------------- #
# AC9 — the release documents carry BOTH observable changes                      #
# --------------------------------------------------------------------------- #

def test_ac9_the_release_notes_carry_the_new_subcommand():
    notes = (REPO_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert "larkdocio mermaid" in notes


def test_ac9_the_release_notes_carry_the_LOG_STREAM_move_as_its_OWN_change():
    """The second, separately-stated observable change: anyone piping ``larkdocio download``
    used to read its progress lines on stdout and now reads them on stderr."""
    notes = (REPO_ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert "stderr" in notes and "download" in notes
    window = notes[notes.find("stderr") - 1200: notes.find("stderr") + 1200]
    assert "stdout" in window, "the notes name the new stream without naming the old one"
