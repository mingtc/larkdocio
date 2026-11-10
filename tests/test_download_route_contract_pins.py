# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""The download verb's CONSUMER CONTRACT, pinned by EXECUTION rather than by inspection.

**Why this file exists (LD-650).** The library was losing its body-sniffing router: a
derivation from the document's own body that shared a file, a class and a join point — but not one
code path — with the caller-supplied ``--route``. A removal that takes *routing* rather than
*the derivation* is an outage for the downstream consumer (it calls
``handle_download_command(url=…, output_dir=…, allow_host=…, dump=…, config_file=…,
env_file=…, route=…)``, reads ``DownloadResult``, and parses two log shapes), and the naive cut
is worse than that: it breaks the ordinary no-``--route`` download for everyone, at runtime,
invisibly to a smoke import.

So the four preserved contract items are asserted here as **facts measured off the live
objects** — a signature bound with real arguments, a record built by the real constructor, an
AST walk over the real log-call arguments, a differential table run through the real refusal
path — never as a line number or a source-text grep. This module was written and proven green
**against the unchanged code, before the first byte of the cut**, so it pins the contract that
existed rather than whichever contract the cut happened to leave behind.

The five pins, and what each one is for:

1. **Signature shape.** All eleven parameters, under their current names, in their current
   order, all ``POSITIONAL_OR_KEYWORD``, with ``route`` defaulting to ``None`` — and the first
   six proven to bind POSITIONALLY, because our own ``cli.py`` passes six positionally. "The
   names are the wire, not the order" is false here: swapping ``allow_host`` and ``config_file``
   satisfies a names-only rule, binds silently (both ``str``), and misroutes the config path on
   every CLI download.
2. **The routing record's shape.** ``RoutedPath`` is a ``str`` subclass whose ``.record``
   answers all five keys UNCONDITIONALLY — including on a construction that passes neither
   label list, which is exactly the construction the no-route branch uses. Dropping
   ``labels_found``/``labels_missing`` "because nothing is looked for any more" would change
   the shape the consumer reads.
3. **The explicit-route record, byte for byte**, and ``DownloadResult``'s three routing
   properties.
4. **One emitter each** for the two log shapes the consumer parses — the INFO line prefixed
   ``"Downloaded markdown file to "`` and the WARNING shaped ``"Unknown block type <N>
   (block_id="`` — proven by an AST walk over log-call ARGUMENTS, which is immune to the prose
   occurrences of the same words in comments and docstrings. Plus the third, unprotected-but-
   load-bearing shape: the WARNING prefixed ``"Routing to the caller-supplied --route path: "``,
   which fires on every consumer run and whose only previous level assertion pinned the *other*
   warning (the derived one, which is leaving).
5. **The nine-input explicit-route differential** — return values AND exception message bodies,
   as literal expected strings, including the deliberate no-lowercasing case (the derived
   segments were the lowercasing caller, and they are the ones leaving).
"""

import ast
import inspect
import pathlib
import re

import click
import pytest

from domain_vocabulary import FORBIDDEN, RETIRED
import private_tree

from larkdocio.read import download as dl
from larkdocio.read.download import (
    DownloadResult,
    RoutedPath,
    _apply_explicit_route,
    handle_download_command,
)

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "larkdocio"

#: The eleven parameters, in order. Order is wire here, not just names (see item 1 above).
EXPECTED_PARAMS = [
    "url",
    "output_dir",
    "allow_host",
    "dump",
    "config_file",
    "env_file",
    "deep_read_sheets",
    "fidelity_read_sheets",
    "deep_read_bases",
    "local_time",
    "route",
]

#: The six our own ``cli.py`` passes POSITIONALLY.
POSITIONAL_WIRE = EXPECTED_PARAMS[:6]

#: The five keys of the routing record — unconditional, whichever branch built it.
RECORD_KEYS = ["routed", "reason", "derivation_ran", "labels_found", "labels_missing"]


def test_the_download_verb_keeps_its_eleven_parameters_in_order():
    params = list(inspect.signature(handle_download_command).parameters)
    assert params == EXPECTED_PARAMS


def test_every_parameter_still_binds_positionally_or_by_keyword():
    # None may become keyword-only: a consumer passing by keyword AND our CLI passing by
    # position must both keep working.
    kinds = {
        name: p.kind
        for name, p in inspect.signature(handle_download_command).parameters.items()
    }
    assert set(kinds) == set(EXPECTED_PARAMS)
    assert all(k is inspect.Parameter.POSITIONAL_OR_KEYWORD for k in kinds.values())


def test_route_still_defaults_to_None():
    assert inspect.signature(handle_download_command).parameters["route"].default is None


def test_the_first_six_arguments_still_bind_by_POSITION_to_the_same_names():
    # Executed, not read: bind six positional sentinels through the real signature and read
    # back WHICH parameter each one landed on. A reorder that type-checks fails here.
    sentinels = [f"<{name}>" for name in POSITIONAL_WIRE]
    bound = inspect.signature(handle_download_command).bind(*sentinels)
    assert [bound.arguments[name] for name in POSITIONAL_WIRE] == sentinels


def test_the_optional_tail_still_binds_by_keyword_with_route_last():
    bound = inspect.signature(handle_download_command).bind(
        "u", "o", "", False, None, env_file=".env", route="a/b"
    )
    assert bound.arguments["route"] == "a/b"
    assert bound.arguments["env_file"] == ".env"


def test_RoutedPath_is_still_a_str_subclass_that_compares_as_its_path():
    path = RoutedPath("/out/a/b", routed=True, reason="explicit_route", derivation_ran=False)
    assert isinstance(path, str)
    assert path == "/out/a/b"


def test_the_record_answers_all_five_keys_on_a_construction_that_passes_no_labels():
    # THE no-route construction. A record that drops the two label lists when nothing was
    # looked for would change the shape the consumer reads.
    path = RoutedPath("/out", routed=False, reason="routing_disabled", derivation_ran=False)
    assert list(path.record) == RECORD_KEYS
    assert path.record["labels_found"] == []
    assert path.record["labels_missing"] == []


def test_the_explicit_route_record_is_byte_identical_to_what_it_has_always_been():
    path = RoutedPath("/out/x/y", routed=True, reason=dl.ROUTE_EXPLICIT, derivation_ran=False)
    assert path.record == {
        "routed": True,
        "reason": "explicit_route",
        "derivation_ran": False,
        "labels_found": [],
        "labels_missing": [],
    }


def test_the_record_carries_no_path():
    # Stated property of the --dump sidecar's byte-identical determinism.
    record = RoutedPath(
        "/out/x/y", routed=True, reason=dl.ROUTE_EXPLICIT, derivation_ran=False
    ).record
    assert not any(isinstance(v, str) and "/out" in v for v in record.values())


@pytest.mark.parametrize("name", ["route", "routed", "route_reason"])
def test_DownloadResult_keeps_its_three_routing_properties(name):
    assert isinstance(getattr(DownloadResult, name, None), property)


def test_the_three_routing_properties_read_the_body_they_are_views_onto():
    record = RoutedPath(
        "/out/x/y", routed=True, reason=dl.ROUTE_EXPLICIT, derivation_ran=False
    ).record
    result = DownloadResult({"output_dir": "/out/x/y", "route": record})
    assert result.route == record
    assert result.routed is True
    assert result.route_reason == "explicit_route"


# --------------------------------------------------------------------------- #
# The log shapes the consumer parses — counted off CALL ARGUMENTS, not prose.  #
# --------------------------------------------------------------------------- #


def _literal_prefix(node):
    """The literal text a log-call argument STARTS with, or ``None`` if it starts with a
    substitution. Handles a plain constant, an f-string, and an implicit/`+` concatenation."""
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        node = node.left
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr) and node.values:
        head = node.values[0]
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            return head.value
    return None


#: The level-named methods, plus the generic ``.log(level, msg)`` form whose message is the
#: SECOND argument. ``.log`` is included even though the package uses it nowhere today —
#: precisely because that is the shape a second emitter of a protected line would most easily
#: arrive in without this walk seeing it.
_LEVEL_METHODS = ("debug", "info", "warning", "error", "critical")


def _log_message_arg(node):
    """The AST node holding the message of a logging call, or ``None`` if it is not one.

    Receiver-agnostic on purpose: ``logger.info(…)``, ``self.log.info(…)`` and
    ``logging.getLogger("larkdocio").info(…)`` are all the same emitter to a consumer reading
    the stream, so the walk keys on the METHOD, never on a variable named ``logger``.
    """
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None, None
    attr = node.func.attr
    if attr in _LEVEL_METHODS and node.args:
        return node.args[0], attr
    if attr == "log" and len(node.args) >= 2:
        level = node.args[0]
        name = level.attr.lower() if isinstance(level, ast.Attribute) else "log"
        return node.args[1], name
    return None, None


def _log_call_prefixes():
    """Every (path, lineno, level, literal-prefix) of a logging call in the shipped package.
    Walks the ARGUMENTS, so the eight prose occurrences of "Unknown block type" in comments
    and docstrings cannot be mistaken for emitters."""
    found = []
    for py in sorted(SRC.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            message, level = _log_message_arg(node)
            if message is None:
                continue
            prefix = _literal_prefix(message)
            if prefix is not None:
                found.append((py, node.lineno, level, prefix))
    return found


#: Logging calls whose message does NOT begin with a literal — a variable, or an f-string
#: opening on a substitution. The emitter walk above cannot read a prefix off these, so each
#: one is a place a protected line could be emitted invisibly. There are few enough to
#: DECLARE, which turns "the walk has a hole" into "the hole is enumerated and held at exactly
#: the per-file counts below": one more has to be justified rather than discovered later. The
#: total is deliberately NOT restated in prose — it is the sum of this table.
DYNAMIC_HEAD_LOG_CALLS = {
    "common/reporting.py": (2, "the exception's own str() and its banner, unknown-error path"),
    "read/client.py": (1, "a caller-supplied refusal string, relayed"),
    "read/config_cmd.py": (1, "a path built for the operator"),
    "read/download.py": (7, "a typed refusal carried into the credentials banner; one "
                            "already-composed line per unfetched reference; LD-658 AC1b's two "
                            "relays on the document-access arm — Lark's own str(e), and the "
                            "PermissionDenial's own detail(), both composed elsewhere; the same "
                            "str(e) relay on the IP arm and on the token-mint arm (LD-658's "
                            "post-AC1 ruling: the arm that fires on what the typed check "
                            "DECLINED is where Lark's own body is worth most); and the "
                            "token-mint arm's loop over the lines common/auth authors"),
    # LD-658's ruling completing AC4: the CLI seam covers `folder` and `roundtrip`, neither of
    # which reaches read/download.py at all. Both relays carry text composed elsewhere — Lark's
    # own str(e), and the lines common/auth.token_mint_refusal_lines authors — which is exactly
    # the class every other entry here is.
    "cli.py": (2, "a rejected credential pair's own str(e), and one already-composed guidance "
                  "line per iteration from common/auth.token_mint_refusal_lines"),
    # (read/config.py's entry — the retired-key notice, LD-659 AC4 — left with the notice
    # when LD-704 discharged the tolerance: the per-file count it declared is now zero.)
}


def _dynamic_head_log_calls():
    found = []
    for py in sorted(SRC.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            message, _level = _log_message_arg(node)
            if message is not None and _literal_prefix(message) is None:
                found.append((str(py.relative_to(SRC)), node.lineno))
    return found


def test_the_emitter_walks_HOLE_is_enumerated_and_does_not_grow():
    """A guard's blind spot, declared rather than left to be found.

    ``_log_call_prefixes`` reads a literal prefix; a call whose message starts with a
    substitution has none, so a second emitter of a consumer-parsed line could hide in one.
    Every one that exists relays text composed elsewhere. Holding the per-file COUNTS
    means a new one is a decision — and if it ever lands in a module owning a protected shape,
    the arm below is what says so.
    """
    found = _dynamic_head_log_calls()
    counted = {}
    for path, _line in found:
        counted[path] = counted.get(path, 0) + 1
    assert counted == {path: n for path, (n, _why) in DYNAMIC_HEAD_LOG_CALLS.items()}, found


def test_the_generic_log_form_is_WATCHED_even_though_the_package_never_uses_it():
    """``logger.log(logging.INFO, "Downloaded markdown file to …")`` is the shape a second
    emitter arrives in when someone avoids the level-named method. The walk must SEE it — a
    guard that only knows the spelling in use today is a guard against the past."""
    tree = ast.parse(
        'import logging\n'
        'logging.getLogger("x").log(logging.INFO, "Downloaded markdown file to %s")\n'
    )
    calls = [_log_message_arg(n) for n in ast.walk(tree) if isinstance(n, ast.Call)]
    seen = [(_literal_prefix(m), lvl) for m, lvl in calls if m is not None]
    assert seen == [("Downloaded markdown file to %s", "info")]


@pytest.mark.parametrize(
    "shape, level",
    [
        ("Downloaded markdown file to ", "info"),
        ("Unknown block type ", "warning"),
        ("Routing to the caller-supplied --route path: ", "warning"),
    ],
)
def test_each_parsed_log_shape_has_exactly_one_emitter_at_its_documented_level(shape, level):
    emitters = [c for c in _log_call_prefixes() if c[3].startswith(shape)]
    assert len(emitters) == 1, [f"{p}:{n}" for p, n, _, _ in emitters]
    assert emitters[0][2] == level


def test_the_unknown_block_type_warning_still_names_the_block_id():
    # The consumer parses "Unknown block type <N> (block_id=" — the tail matters as much as
    # the head, and it is a substitution away from it.
    emitter = [c for c in _log_call_prefixes() if c[3].startswith("Unknown block type ")][0]
    source = emitter[0].read_text(encoding="utf-8").splitlines()
    window = "\n".join(source[emitter[1] - 1 : emitter[1] + 3])
    assert "block_id=" in window


@pytest.mark.parametrize(
    "shape, module",
    [
        ("Downloaded markdown file to ", "download.py"),
        ("Unknown block type ", "parser.py"),
        ("Routing to the caller-supplied --route path: ", "download.py"),
    ],
)
def test_each_parsed_log_shape_is_emitted_from_the_module_it_has_always_been_in(shape, module):
    # read/parser.py owns the block-type warning, and LD-650 does not open that file at all.
    emitters = [c for c in _log_call_prefixes() if c[3].startswith(shape)]
    assert [p.name for p, _, _, _ in emitters] == [module]


# --------------------------------------------------------------------------- #
# The nine-input explicit-route differential.                                  #
# --------------------------------------------------------------------------- #

#: Return values. NOTE the second case: the caller's spelling is NOT lower-cased. The derived
#: segments were the lowercasing caller and they are the ones leaving; this must not follow.
EXPLICIT_ROUTE_ACCEPTS = [
    ("x/y", "/base/x/y"),
    ("My Area/Sub Section", "/base/My_Area/Sub_Section"),
    ("a/b/", "/base/a/b"),
    ("a:b*c/d", "/base/abc/d"),
]

#: Refusal bodies, verbatim. LD-650 kept these bytes deliberately: the four preserved contract
#: items do not cover refusal text, so rewording them would be a consumer-visible string change
#: made by accident. That reason stands. LD-705 made the one change on purpose: three of them
#: give the example subpath ``area/section/topic``, a neutral placeholder, and the release notes
#: say so.
EXPLICIT_ROUTE_REFUSALS = [
    (
        "../esc",
        "--route '../esc' may not contain a '..' segment — it would navigate outside the "
        "output root. Give a subpath that stays under -o.",
    ),
    (
        "./x",
        "--route './x' may not contain a '.' segment — it would navigate outside the "
        "output root. Give a subpath that stays under -o.",
    ),
    (
        "/abs",
        "--route must be a relative subpath under -o, but '/abs' is an absolute path. "
        "Give it as area/section/topic, not a rooted path.",
    ),
    ("", "--route was empty — give it as area/section/topic."),
    (
        "a//b",
        "--route 'a//b' has an empty path segment — give it as area/section/topic with "
        "no doubled separators.",
    ),
]

#: **LD-658 AC6 — the escape the guard could not see.** The check tested the RAW segment for
#: ``.`` / ``..`` and ``sanitize_path_string`` then MANUFACTURED ``..`` by stripping
#: ``\ / : * ? " < > |``. Executed at the pin: ``'..'``, ``'.'`` and ``'a/../b'`` were correctly
#: refused, while ``'.?.'``, ``'.:.'`` and ``'..*'`` all returned ``<out>/..`` and
#: ``'.?./.?./escaped'`` returned ``<out>/../../escaped`` — **materialized**. The docstring and
#: the rendered ``--help`` state the negation as an absolute (*"it cannot escape the output root
#: … never silently normalised"*), so this was a false promise in shipped bytes.
#:
#: Every case below is one the literal check passes and the sanitized check refuses. The refusal
#: NAMES the manufacture, because a message quoting only ``'..'`` for an input of ``'.?.'`` sends
#: the reader looking for a segment they did not type.
EXPLICIT_ROUTE_MANUFACTURED_ESCAPES = [
    ".?.",
    ".:.",
    "..*",
    '."."',
    "a/.?./b",
    ".?./.?./escaped",
    ".*",
    "<.>.",
]


@pytest.mark.parametrize("route", EXPLICIT_ROUTE_MANUFACTURED_ESCAPES)
def test_a_MANUFACTURED_navigation_segment_is_refused_like_a_literal_one(route):
    """AC6's guard: the manufactured cases, not just the literal ones."""
    import click
    import pytest as _pytest

    with _pytest.raises(click.ClickException) as caught:
        _apply_explicit_route("/base", route)
    message = str(caught.value)
    assert "may not contain" in message, message
    assert "navigate outside the output root" in message, message
    # the caller's OWN text is quoted, so the refusal is findable in their command line
    assert repr(route) in message or route in message, message


@pytest.mark.parametrize("route", EXPLICIT_ROUTE_MANUFACTURED_ESCAPES)
def test_the_manufactured_cases_really_ARE_manufactured_and_not_literal(route):
    """Non-vacuity: each input above must PASS the old literal test and FAIL the new sanitized
    one. Without this, a case that was already refused for another reason would let the guard
    above pass while the escape stayed open."""
    import re as _re

    from larkdocio.common.sanitize import sanitize_path_string

    segments = _re.split(r"[/\\]", route.strip().strip("/\\"))
    literal_hits = [s for s in segments if s in (".", "..")]
    sanitized_hits = [s for s in segments if sanitize_path_string(s) in (".", "..")]
    assert not literal_hits, (
        f"{route!r} contains a LITERAL navigation segment {literal_hits} — the old check "
        f"already refused it, so it proves nothing about the manufacture")
    assert sanitized_hits, (
        f"{route!r} does not manufacture a navigation segment; it does not belong in this list")


def test_the_manufactured_escape_no_longer_MATERIALIZES_a_path_outside_the_root(tmp_path):
    """The measured symptom was not a refusal that read oddly — it was a real directory outside
    ``-o``. Held on the filesystem, so a future refactor that returns a refusal-shaped string
    without refusing is caught."""
    import click
    import pytest as _pytest

    root = tmp_path / "out"
    root.mkdir()
    with _pytest.raises(click.ClickException):
        landed = _apply_explicit_route(str(root), ".?./.?./escaped")
        # if it ever returns instead of raising, prove the damage rather than passing quietly
        assert False, f"returned {landed!r} instead of refusing"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out"]
    assert not list(root.iterdir())


@pytest.mark.parametrize("route, expected", EXPLICIT_ROUTE_ACCEPTS)
def test_the_explicit_route_still_answers_the_same_path(route, expected):
    assert _apply_explicit_route("/base", route) == expected


@pytest.mark.parametrize("route, body", EXPLICIT_ROUTE_REFUSALS)
def test_the_explicit_route_still_refuses_with_the_same_message_body(route, body):
    with pytest.raises(click.ClickException) as excinfo:
        _apply_explicit_route("/base", route)
    assert str(excinfo.value) == body


def test_the_explicit_route_docstring_keeps_its_contract_by_negation():
    # "the library infers nothing — no title parsing, no title grammar, no filename heuristic,
    # no defaulting from document content." A vocabulary sweep that strikes the sentence
    # deletes what makes the guarantee meaningful. It is a contract BY NEGATION and it is
    # restated, never removed. (LD-704 generalised its example grammar, which named a document
    # type; the negations below are the contract and are unchanged.)
    doc = inspect.getdoc(_apply_explicit_route)
    assert "infers nothing" in doc
    assert "no filename heuristic" in doc
    assert "no defaulting from document content" in doc


# --------------------------------------------------------------------------- #
# AC2 (LD-650), TRANSFORMED BY LD-704 — THE SHIPPED SURFACE CARRIES NOTHING      #
#                FROM THE PRIVATE PATTERN SET, WITH NO ALLOWLIST.               #
#                                                                              #
# LD-650 stated this as a SET RELATION against a declared allowlist (generic   #
# phrases, a contract-by-negation example, the tolerated config key) and a      #
# per-section count for the release documents, whose dated sections were then  #
# history. `D-121` (8) removed every one of those occurrences — the tolerance   #
# is discharged, the phrases are generalised, and the released sections were   #
# edited for this class alone (disclosed once, in 1.53.0's notes). So the      #
# reason stands and the conclusion narrows to its limit: the allowlist is      #
# EMPTY, and the whole of every shipped file — release documents included — is #
# read. The file population is still a GLOB over the wheel's own bytes (the    #
# original audit's 13-file scope missed package-data config.json).             #
# The set comes from the private ledger through tests/domain_vocabulary.py    #
# (LD-705, LD-707), so this guard does not carry it; the arms that need it are #
# @private_tree.dev_record and skip, with that reason, in the public tree.     #
# --------------------------------------------------------------------------- #

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


#: The wheel's own bytes: the package tree plus the two root files that ship with it —
#: README.md IS the METADATA long_description body, and pyproject.toml carries the keywords.
def _shipped_files():
    files = [
        p for p in (REPO_ROOT / "src" / "larkdocio").rglob("*")
        if p.suffix in (".py", ".md", ".json") and p.is_file()
    ]
    files += [REPO_ROOT / "README.md", REPO_ROOT / "pyproject.toml"]
    return sorted(files)


#: The declared allowlist — EMPTY since LD-704, kept as a declaration rather than deleted: an
#: entry is ``(path, the matched line's own distinguishing text, how many lines carry it)``,
#: and adding one is a decision a reviewer sees in the diff. The two arms below hold it in
#: both directions, exactly as they did when it had five entries.
ALLOWED = set()


def _offending_lines():
    """Every shipped line carrying the private pattern set, bucketed.

    Returns (allowed, offending)."""
    allowed, offending = set(), []
    for path in _shipped_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # pragma: no cover - no binary ships in these suffixes
            continue
        rel = str(path.relative_to(REPO_ROOT / "src" / "larkdocio")) if (
            REPO_ROOT / "src" / "larkdocio") in path.parents else path.name
        for line in text.splitlines():
            if not FORBIDDEN.search(line):
                continue
            hit = next(
                (entry for entry in ALLOWED
                 if entry[0] == rel and entry[1].lower() in line.lower()),
                None,
            )  # the fragment must appear IN the line — never a whole-file opt-out
            if hit:
                allowed.add(hit)
            else:
                offending.append((rel, line.strip()[:120]))
    return allowed, offending


@private_tree.dev_record
def test_no_shipped_line_carries_the_private_pattern_set():
    _allowed, offending = _offending_lines()
    assert offending == [], (
        "the shipped surface has regrown a line from the private pattern set: "
        f"{offending} (LD-650, LD-704, LD-707)"
    )


def test_every_declared_allowlist_ENTRY_still_exists():
    """The other direction: an allowlist whose entries have quietly stopped existing is a
    permission slip, not a declaration. Empty since LD-704, so this holds the emptiness."""
    allowed, _offending = _offending_lines()
    assert allowed == ALLOWED, f"declared but not found: {sorted(ALLOWED - allowed)}"


def test_the_allowlist_cannot_exempt_a_WHOLE_FILE():
    """An allowlist entry is a permission for KNOWN LINES: every fragment is re-matched against
    the file it names and must still reach exactly the number of lines it declares."""
    offenders = []
    for rel, fragment, expected in sorted(ALLOWED):
        path = next((p for p in _shipped_files() if str(p).endswith(rel)), None)
        assert path is not None, rel
        hits = [ln for ln in path.read_text(encoding="utf-8").splitlines()
                if fragment.lower() in ln.lower()]
        if len(hits) != expected:
            offenders.append((rel, fragment, f"{len(hits)} lines, declared {expected}"))
    assert offenders == [], offenders


@private_tree.dev_record
def test_the_guard_is_LIVE_on_a_regrown_line(tmp_path, monkeypatch):
    """Non-vacuity, now that nothing is allowed: a planted line carrying a member of the
    private set in a shipped release document is reported."""
    planted = tmp_path / "RELEASE_NOTES.md"
    planted.write_text(f"## [9.9.9]\n- a line carrying {RETIRED} again\n", encoding="utf-8")
    import sys

    monkeypatch.setattr(sys.modules[__name__], "_shipped_files", lambda: [planted])
    _allowed, offending = _offending_lines()
    assert offending and RETIRED in offending[0][1], offending


@private_tree.dev_record
def test_the_wheel_keyword_list_carries_nothing_from_the_private_set():
    """The whole private pattern over the keyword list — one check for every member of the set,
    so the check names no member in particular (LD-710, round 9 Z8)."""
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    keywords = pyproject.split("keywords = ", 1)[1].split("]", 1)[0]
    assert not FORBIDDEN.search(keywords), keywords


# --------------------------------------------------------------------------- #
# LD-650 round 2 — THE LOG SHAPES ARE PINNED BY EMISSION, NOT ONLY BY SOURCE.   #
#                                                                              #
# The AST arms above count EMITTERS: they prove there is exactly one authored   #
# site per shape, in the right module, at the right level. What they cannot see #
# is whether that site still RUNS — an emitter made unreachable (an early       #
# return above it, a branch that no longer fires) leaves the AST node in place  #
# and the whole suite green while the consumer's log line stops arriving. The   #
# downstream parser reads bytes off a stream, not nodes out of a tree, so the   #
# two shapes it parses on our side of the wire are also driven end to end here. #
# --------------------------------------------------------------------------- #

from test_download_pipeline import DOCX_URL, _StubClient, _StubParser, _patch_env  # noqa: E402


def _run(monkeypatch, out_dir, **kwargs):
    _patch_env(monkeypatch)
    monkeypatch.setattr(dl, "Client", lambda *a, **k: _StubClient())
    monkeypatch.setattr(dl, "Parser", lambda config: _StubParser(markdown="# plain\n"))
    return dl.handle_download_command(DOCX_URL, str(out_dir), "", False, "", **kwargs)


def test_the_download_INFO_line_is_actually_EMITTED_with_the_path_substituted(
    monkeypatch, tmp_path, caplog
):
    """Contract item 3, driven rather than counted."""
    with caplog.at_level("INFO", logger="larkdocio"):
        result = _run(monkeypatch, tmp_path)
    records = [r for r in caplog.records
               if r.message.startswith("Downloaded markdown file to ")]
    assert len(records) == 1, [r.message for r in caplog.records]
    assert records[0].levelname == "INFO"
    assert records[0].message == f"Downloaded markdown file to {result.output_path}", (
        "the line must carry the real path — a consumer parses the path off this line"
    )


def test_the_explicit_route_WARNING_is_actually_EMITTED_with_the_directory_substituted(
    monkeypatch, tmp_path, caplog
):
    """The line that fires on every downstream run, driven end to end."""
    with caplog.at_level("INFO", logger="larkdocio"):
        result = _run(monkeypatch, tmp_path, route="x/y")
    records = [r for r in caplog.records
               if r.message.startswith("Routing to the caller-supplied --route path: ")]
    assert len(records) == 1, [r.message for r in caplog.records]
    assert records[0].levelname == "WARNING", (
        "WARNING is load-bearing: an in-process caller with no handler sees WARNING and above "
        "through logging.lastResort, and this line is how they learn -o was rewritten"
    )
    assert records[0].message.endswith(result.output_dir)


def test_a_download_with_NO_route_emits_that_warning_not_at_all(monkeypatch, tmp_path, caplog):
    """The negative half: the line is a report of a rewrite, so an unrouted run must be silent
    about routing entirely — otherwise the downstream parser sees a route where there is none."""
    with caplog.at_level("INFO", logger="larkdocio"):
        _run(monkeypatch, tmp_path)
    assert not [r for r in caplog.records if "--route" in r.message]


def test_an_EMPTY_route_is_refused_rather_than_treated_as_no_route(monkeypatch, tmp_path):
    """`if route is not None:` at the join point, pinned BEHAVIOURALLY.

    The statement carries a comment saying it is deliberately not truthiness, and nothing
    tested it: flipping it to `if route:` left the entire suite byte-identically green. That
    flip is not cosmetic — it turns `--route ''` from a NAMED refusal into a silent no-op, so
    a consumer whose route variable came back empty gets a file written somewhere they did not
    ask for, at exit 0, instead of an error naming the mistake.
    """
    with pytest.raises(click.ClickException) as excinfo:
        _run(monkeypatch, tmp_path, route="")
    assert str(excinfo.value) == "--route was empty — give it as area/section/topic."
    assert not list(tmp_path.glob("*.md")), "a refused route must not write a file"
