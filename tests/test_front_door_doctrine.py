# GUARD-SET MEMBER (scripts/verify.sh's always-on --scope floor, LD-354) — a CROSS-CUTTING
# drift guard: it holds an artifact against real code ELSEWHERE in the tree, so it reddens for
# a change made somewhere else. Renaming, moving or retiring this file means editing that
# array in the SAME change; tests/test_verify_gate_reporting.py holds the two sides equal both
# ways (LD-649), and the runner refuses to start on a listed path that has vanished.
"""THE FRONT-DOOR DOCTRINE — consumer-doc truth as part of shipping, enforced.

What this module is for
-----------------------
A consumer critique read the wheel and nothing else, and found shipped-false claims in the
first thing it met: the ``Summary`` still called writeback "reserved" fourteen releases after
the writer shipped, the keywords omitted two whole surfaces, two real CLI flags were
undocumented, eight modules were missing from the layout table. Those claims were corrected
in the preceding issue. **This module fixes why they were there.**

The root cause was one function wide. ``tests/consumer_text.py::shipped_docs`` — the scope
every content guard and the internal-dialect grep flow from — returned exactly
``{"guide()": …, "writer_brief()": …}``. So two deep docs were held to a standard for months
while the README (which **is** the wheel's ``METADATA`` body, per ``readme = "README.md"``),
the ``METADATA`` header fields, and the rendered CLI ``--help`` were **never in scope at
all.** They did not decay through neglect; nothing was ever looking at them.

Three things close that, and they are deliberately different in kind:

1. **The corpus is widened** (``shipped_docs`` now returns the whole front door), which buys
   the existing dialect grep over all of it with **no new machinery** — the guard simply
   greps whatever that function returns.
2. **Completeness cross-checks**, because a dialect grep cannot notice an *absence*: it will
   never report that the layout table is missing ``sheets/`` or that a flag is undocumented.
   These copy the pattern this repo already trusts twice (``test_blocks_md_matrix.py`` /
   ``test_sheets_md_matrix.py``): pin the prose against **real code**, in **both** directions,
   so a capability change that skips the door reddens the suite. Auto-generating the README
   from click was considered and rejected — the guard buys the same protection far more
   cheaply and keeps the prose human.
3. **A shipped-citation check**, so a wheel-only reader is never sent to a file the wheel does
   not carry without being told so first.

Every cross-check here is **proven to bite, per direction, separately**, over synthetic text —
a bidirectional guard that only really checks one direction is the classic silent failure, and
the entire value of this module is that the guards are real. Each is also proven *not* to bite
on the legitimate shape it might be confused for, because a guard that cries wolf gets
weakened until it guards nothing.

The pure helpers live in ``tests/front_door.py``; the corpus itself lives in
``tests/consumer_text.py``.
"""
import pathlib
import re

import click
import pytest

import consumer_text
import front_door as fd
from consumer_text import cli_group, dialect_hits, shipped_docs
from doc_prose import missing_phrases, prose
import private_tree  # noqa: E402  (LD-685)

# LD-370 — CONFORMANCE-tier: the wheel's Summary, README and rendered --help are the first text a consumer meets; a rewrite that describes itself wrongly is wrong.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance


# =====================================================================
# (a) AC1 / AC2 / AC3 — the widened corpus
# =====================================================================

def _expected_help_labels():
    """The ``--help`` labels the click group itself demands — derived, never listed.

    This is the AC3 point: the subcommand set comes out of ``cli_group().commands``, so adding a
    command cannot slip past by simply not appearing in a literal list somewhere.
    """
    return {"larkdocio --help"} | {f"larkdocio {name} --help" for name in cli_group().commands}


def _expected_shipped_labels():
    return {
        "guide()",
        "writer_brief()",
        "README.md (the wheel METADATA body)",
        "pyproject description (the wheel Summary)",
        "pyproject keywords (the wheel Keywords)",
        "release_notes() (the packaged RELEASE_NOTES.md)",
        # LD-549 — the Lark-application walkthrough now ships in the wheel, so it is part of the
        # front door and part of what the dialect grep reads. The pin is widened, deliberately:
        # its job is that losing a member silently un-guards a shipped surface, and an addition
        # is exactly as much a change to the front door as a removal.
        "lark_setup() (the packaged LARK_SETUP.md)",
        # LD-691 (maintainer ruling 2) — the packaged changelog is the PUBLIC changelog in both trees,
        # consumer prose, so it joins the front door and the dialect grep. Widened deliberately.
        "changelog() (the packaged CHANGELOG.md)",
    } | _expected_help_labels()


def test_ac1_shipped_docs_covers_every_consumer_reaching_surface():
    """The scope pin. Losing a member here silently un-guards a shipped surface — which is
    exactly the state this issue found the front door in."""
    labels = set(shipped_docs())
    expected = _expected_shipped_labels()
    assert labels == expected, (
        f"the guarded consumer corpus is not the front door: missing "
        f"{sorted(expected - labels)}, unexpected {sorted(labels - expected)}"
    )


def test_ac1_the_enrolled_readme_is_the_text_that_ships_as_the_metadata_body():
    """Not a paraphrase of the README — the bytes ``pyproject`` declares as the body."""
    assert fd.pyproject()["project"]["readme"] == "README.md"
    assert shipped_docs()["README.md (the wheel METADATA body)"] == fd.readme_text()


def test_ac1_the_enrolled_metadata_fields_are_the_real_pyproject_values():
    project = fd.pyproject()["project"]
    docs = shipped_docs()
    assert docs["pyproject description (the wheel Summary)"] == project["description"]
    enrolled_keywords = docs["pyproject keywords (the wheel Keywords)"]
    for keyword in project["keywords"]:
        assert keyword in enrolled_keywords, f"keyword {keyword!r} is not in the corpus"


def test_ac1_the_enrolled_release_notes_are_the_copy_that_actually_ships():
    """The canonical file is at the repo root and the wheel carries a byte-identical copy
    under the package. The corpus reads the **packaged** one — through the public
    ``release_notes()`` accessor, so what is guarded is exactly what a consumer's own call
    returns — and a drift between the two copies is a separate guard's job."""
    packaged = fd.SRC / "RELEASE_NOTES.md"
    assert packaged.is_file(), "the packaged release notes are missing"
    enrolled = shipped_docs()["release_notes() (the packaged RELEASE_NOTES.md)"]
    assert enrolled == consumer_text.larkdocio.release_notes()
    assert enrolled == packaged.read_text(encoding="utf-8")
    assert "src/larkdocio/RELEASE_NOTES.md" in fd.packaged_doc_paths()


def test_ac1_the_reasoned_exclusions_are_recorded_not_silently_dropped():
    """A reasoned exclusion is documentation. ``BLOCK_TYPES.md`` (a contributor doc) and
    ``CHANGELOG.md`` were both packaged and both deliberately out of **this** corpus — the
    docstring has to say so, or the next reader cannot tell a decision from an oversight.
    LD-691 (maintainer ruling 2) moved the changelog IN — the packaged copy is now the public changelog —
    and the docstring has to say THAT just as plainly, so a reader of the old decision finds why
    it changed; ``tests/test_release_notes_accessor.py`` holds the distinction."""
    docstring = shipped_docs.__doc__ or ""
    for excluded in ("BLOCK_TYPES.md", "CHANGELOG.md"):
        assert excluded in docstring, (
            f"{excluded} is packaged but not in the corpus, and the docstring does not say "
            f"why — a silent exclusion is indistinguishable from a bug"
        )


# --------------------------------------------------------------------------- #
# AC3 — the `--help` enrolment is DERIVED, and complete                         #
# --------------------------------------------------------------------------- #

def test_ac3_a_help_page_is_enrolled_for_the_group_and_every_subcommand():
    labels = set(consumer_text.cli_help_pages())
    assert labels == _expected_help_labels(), (
        f"the --help enrolment does not match the real click group: missing "
        f"{sorted(_expected_help_labels() - labels)}, extra {sorted(labels - _expected_help_labels())}"
    )
    assert len(cli_group().commands) >= 2, "the group lost a subcommand; this pin has gone slack"


def test_ac3_every_enrolled_page_is_the_rendered_page_a_user_sees():
    """Rendered through click's own runner, so the guard reads the assembled page — wrapped
    option help, usage line and all — rather than the source strings the page is built from.
    A silently empty page would narrow the guard to nothing, so each is pinned non-trivial."""
    for label, text in consumer_text.cli_help_pages().items():
        assert text.startswith("Usage: larkdocio"), f"{label} is not a rendered help page"
        assert "Options:" in text, f"{label} renders no options section"
        assert len(text) > 80, f"{label} is suspiciously short: {text!r}"


def test_ac3_a_new_subcommand_enrols_itself_with_nobody_editing_a_list(monkeypatch):
    """The failure this forecloses: a future subcommand ships un-guarded because it was never
    added to a hand-kept list. The derived list grows on its own."""
    @click.command(name="zzprobe", help="A throwaway probe command for this test.")
    def probe():  # pragma: no cover — never invoked, only rendered
        pass

    before = set(consumer_text.cli_help_pages())
    monkeypatch.setitem(cli_group().commands, "zzprobe", probe)
    after = set(consumer_text.cli_help_pages())

    assert after - before == {"larkdocio zzprobe --help"}
    assert "throwaway probe command" in consumer_text.cli_help_pages()[
        "larkdocio zzprobe --help"
    ]


def test_ac3_the_help_pages_are_part_of_the_corpus_the_dialect_guard_greps():
    corpus = consumer_text.consumer_corpus()
    for label in _expected_help_labels():
        assert label in corpus, f"{label} is enrolled in shipped_docs but not in the corpus"


# --------------------------------------------------------------------------- #
# AC2 — the dialect guard applies to the widened corpus, and is BORN GREEN      #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("label", sorted(_expected_shipped_labels()))
def test_ac2_every_shipped_surface_is_dialect_free(label):
    """Born green: no new machinery, the existing pattern set simply now reaches here.

    A failure is a **finding** — fix the string, or record why the exclusion is legitimate.
    It is never a licence to weaken the pattern set.
    """
    hits = dialect_hits(shipped_docs()[label])
    assert hits == [], (
        f"{label} speaks this repo's internal dialect, which resolves nowhere for someone "
        f"holding only the wheel: {hits[:12]}"
    )


def test_ac2_the_dialect_guard_bites_on_a_string_added_to_a_NEWLY_enrolled_surface(
    monkeypatch,
):
    """Red-then-green in situ on the widening itself: the README was out of scope before this
    issue, so the injection has to be caught *through the corpus*, not merely by the pattern
    function."""
    assert consumer_text.corpus_dialect_report() == [], "the corpus must be clean first"

    real = fd.readme_text
    monkeypatch.setattr(
        fd, "readme_text", lambda: real() + "\nSee LD-149 for the rationale.\n"
    )
    report = consumer_text.corpus_dialect_report()
    caught = [(label, matched) for label, _n, matched, _s in report]
    assert caught == [("README.md (the wheel METADATA body)", "LD-149")], (
        f"a dialect string in the README was not caught through the widened corpus: {report}"
    )


def test_ac2_the_dialect_guard_bites_on_a_string_added_to_a_help_page(monkeypatch):
    """The other newly-enrolled *kind* of surface: a rendered page rather than a file."""
    option = next(p for p in cli_group().commands["download"].params if p.name == "dump")
    monkeypatch.setattr(option, "help", "Dump the raw payload (see LD-149 § F1).")
    report = consumer_text.corpus_dialect_report()
    # Both shapes in the injected sentence are caught, and only from the page they were
    # injected into — the enrolment is the whole rendered page, not a sampled fragment.
    assert sorted((label, name, matched) for label, name, matched, _s in report) == [
        ("larkdocio download --help", "decision-ref", "F1"),
        ("larkdocio download --help", "issue-id", "LD-149"),
    ], f"a dialect string in a --help page was not caught as expected: {report}"


@pytest.mark.parametrize(
    "legitimate",
    [
        "Download lark document to markdown file",
        "larkdocio v1.20.0",
        "the range D4:F9 spans two columns",
        "-o ./out/",
        "block type 30",
        "Python 3.11+",
        "at 9 PM the token expires",
    ],
)
def test_ac2_the_widened_corpus_does_not_make_the_guard_false_positive(legitimate):
    """The README's prose is far richer than ``guide()``'s, so the false-positive surface
    grew with the corpus. These are shapes the front door really contains."""
    assert dialect_hits(legitimate) == [], f"false positive on {legitimate!r}"


def test_ac2_the_front_door_really_does_contain_those_shapes():
    """…and the false-positive probes above are not hypothetical: pin that the text the
    corpus now carries actually contains them, so the probes cannot rot into decoration."""
    joined = "\n".join(shipped_docs().values())
    for shape in ("Download lark document to markdown file", "-o ./out/", "3.11+"):
        assert shape in joined, f"{shape!r} is no longer in the front door — probe is stale"


def _metadata_surfaces(metadata):
    """``{label: text}`` for the three shipped ``METADATA`` surfaces the corpus stands in for.

    The corpus reads the *sources* — ``pyproject.toml`` and ``README.md``. This reads the same
    three claims back out of the **built artifact**, which is what a consumer actually gets.
    """
    headers = fd.metadata_headers(metadata)
    return {
        "wheel METADATA Summary": " ".join(headers.get("Summary", [])),
        "wheel METADATA Keywords": " ".join(headers.get("Keywords", [])),
        "wheel METADATA body": metadata.split("\n\n", 1)[1],
    }


def test_ac1_the_BUILT_wheels_metadata_is_dialect_free_not_merely_its_source():
    """The deliverable is the wheel. The corpus greps ``README.md`` and ``pyproject.toml``
    because those are editable, but the claim being made is about the ``METADATA`` a consumer
    unpacks — so assert it there too. Skips on a plain checkout; ``python -m build`` arms it."""
    wheel = fd.built_wheel()
    if wheel is None:
        pytest.skip("no built wheel for the declared version in dist/ — run `python -m build`")
    surfaces = _metadata_surfaces(fd.wheel_metadata(wheel))
    offenders = {
        label: dialect_hits(text) for label, text in surfaces.items() if dialect_hits(text)
    }
    assert not offenders, f"the shipped wheel METADATA speaks the internal dialect: {offenders}"
    # …and the body really is the README, which is why guarding the README guards the wheel.
    assert prose(fd.first_screenful(fd.readme_text(), 8)) in prose(surfaces["wheel METADATA body"])


def test_ac1_the_metadata_dialect_check_bites_on_a_synthetic_wheel():
    """The red proof for the assertion above, over a METADATA payload shaped like a real one —
    the wheel is green today and a check that cannot be shown failing proves nothing."""
    synthetic = (
        "Metadata-Version: 2.1\nName: larkdocio\nSummary: A reader (see LD-149).\n"
        "Keywords: lark,docx\n\n# larkdocio\n\nPer the PM directive, W2 shipped first.\n"
    )
    surfaces = _metadata_surfaces(synthetic)
    caught = {label: sorted({name for name, _m in dialect_hits(text)})
              for label, text in surfaces.items() if dialect_hits(text)}
    assert caught == {
        "wheel METADATA Summary": ["issue-id"],
        "wheel METADATA body": ["ladder-rung", "role-attribution"],
    }, caught


# =====================================================================
# (b) AC4 / AC5 / AC6 — COMPLETENESS, bidirectional
#
# A dialect grep reads what the text says. None of it can notice what the
# text FAILS to say — which is the defect class that shipped: eight modules
# absent from the layout table, two flags absent from the options list, two
# surfaces absent from the Summary. So each claim below is pinned against
# the code it describes, in both directions, on the matrix-guard pattern.
# =====================================================================

@pytest.fixture(scope="module")
def readme():
    return fd.readme_text()


_DOWNLOAD_MARKER = "options (after the subcommand)"
_GLOBAL_MARKER = "options (before the subcommand)"
#: LD-492. The verb that WRITES documents its options as a bullet list of its own, and it is
#: held to click **exactly**, both ways — the same standard as `download` and the global
#: options, not the weaker all-commands-mention leg. A flag on the one writing command that
#: the README omits, or a bullet naming a flag click does not define, is a consumer told the
#: wrong thing about the only verb here that can change their document. The marker carries the
#: command name because it is the SECOND list ending in the shared phrase, and
#: ``documented_options`` reads the first line the marker matches.
_ROUNDTRIP_MARKER = "`roundtrip` options (after the subcommand)"


# --------------------------------------------------------------------------- #
# AC4 — the layout table ↔ the real top level of src/larkdocio                  #
# --------------------------------------------------------------------------- #

def test_ac4_the_layout_table_and_the_real_top_level_agree_both_ways(readme):
    documented = fd.documented_layout_paths(readme)
    assert documented, "the package-layout table could not be parsed at all"
    undocumented, phantom = fd.two_way_diff(documented, fd.real_top_level())
    assert not undocumented, (
        f"these ship but the package-layout table omits them: {undocumented} — a consumer "
        f"navigating by the table concludes they do not exist"
    )
    assert not phantom, (
        f"the layout table lists {phantom}, which does not exist — a reader is sent to a "
        f"path that is not there"
    )


def test_ac4_adding_a_module_reddens_the_guard_THROUGH_THE_REAL_PARSE(readme):
    """Direction one, end to end. Not set arithmetic on a hand-made set: the documented side
    is parsed out of the real README, and a module appears that has no row."""
    # LD-246: ``base/`` became REAL (and documented), so the probe moved to a name that
    # is not — the probe must be a package the README genuinely does not describe.
    invented = "src/larkdocio/nosuchpackage/"
    assert invented not in fd.real_top_level(), "the probe is stale; pick a name that is fake"
    documented = fd.documented_layout_paths(readme)
    undocumented, _phantom = fd.two_way_diff(documented, fd.real_top_level() | {invented})
    assert undocumented == [invented], (
        f"a new package with no table row did not redden the guard: {undocumented}"
    )


def test_ac4_removing_a_row_reddens_the_guard_THROUGH_THE_REAL_PARSE(readme):
    """Direction two, end to end: delete a row from the README **text** and the real module
    it described is reported missing. The parse is part of what is under test — a guard whose
    table parser silently returned nothing would pass the first direction forever."""
    victim = "src/larkdocio/sheets/"
    stripped = "\n".join(
        line for line in readme.splitlines()
        if not (line.strip().startswith("|") and f"`{victim}`" in line)
    )
    documented = fd.documented_layout_paths(stripped)
    assert victim not in documented, "the row was not actually removed; the probe is stale"
    undocumented, _phantom = fd.two_way_diff(documented, fd.real_top_level())
    assert undocumented == [victim]


def test_ac4_a_phantom_row_reddens_the_guard_THROUGH_THE_REAL_PARSE(readme):
    """The other half of direction two: a row naming something that does not exist."""
    invented = "| `src/larkdocio/telepathy/` | Reads the user's mind. |"
    documented = fd.documented_layout_paths(readme + "\n" + invented)
    _undocumented, phantom = fd.two_way_diff(documented, fd.real_top_level())
    assert phantom == ["src/larkdocio/telepathy/"]


def test_ac4_the_table_parser_does_not_confuse_prose_paths_for_rows():
    """The must-not-bite: the README cites ``src/larkdocio/...`` paths in prose too, and only
    a table's FIRST COLUMN is a layout claim."""
    prose_only = (
        "Handler-authoring mechanics live in `src/larkdocio/blocks/BLOCK_TYPES.md`.\n"
        "\n| Path | What it is |\n|---|---|\n| `src/larkdocio/read/` | The reader. |\n"
    )
    assert fd.documented_layout_paths(prose_only) == {"src/larkdocio/read/"}


# --------------------------------------------------------------------------- #
# AC5 — the documented CLI options ↔ click's own params                          #
#                                                                              #
# Scope call (Dev): `config` joins NOW, at the strength the README documents it #
# — it has no options bullet list, it is documented by showing the invocation,   #
# so the all-commands leg asserts every option of every command is documented   #
# SOMEWHERE, while the two real bullet lists are held EXACTLY, both ways.       #
# --------------------------------------------------------------------------- #

def test_ac5_every_option_of_every_command_is_documented_somewhere(readme):
    """The forward leg over the WHOLE CLI, `config` included — so a new option on any
    command, not just ``download``, cannot ship undocumented."""
    missing = {
        label: sorted(option for option in options if option not in readme)
        for label, options in fd.all_command_options().items()
    }
    missing = {label: gone for label, gone in missing.items() if gone}
    assert not missing, (
        f"these options exist on the CLI and the README never mentions them: {missing}"
    )


def test_ac5_the_all_commands_leg_really_covers_config_not_just_download():
    """The scope call, pinned: `config`'s options are in the checked set, so the leg cannot
    quietly have covered only the command that already had a bullet list."""
    covered = fd.all_command_options()
    assert set(covered) == {f"larkdocio {name}" for name in cli_group().commands} | {
        "larkdocio"
    }
    assert covered["larkdocio config"] == {"--appId", "--appSecret"}


def test_ac5_an_undocumented_option_on_ANY_command_reddens(readme):
    """Direction one, through the real README text: a new flag nobody documented."""
    invented = {"larkdocio config": {"--appId", "--appSecret", "--appTenant"}}
    missing = {
        label: sorted(option for option in options if option not in readme)
        for label, options in invented.items()
    }
    assert missing == {"larkdocio config": ["--appTenant"]}


def test_ac5_every_flag_the_readme_shows_being_PASSED_to_larkdocio_is_real(readme):
    """The reverse leg over the whole document, not just the two bullet lists: a flag shown in
    an invocation a reader will copy has to exist, or the copy fails."""
    real = set().union(*fd.all_command_options().values())
    phantom = sorted(fd.invocation_option_tokens(readme) - real)
    assert not phantom, (
        f"the README shows {phantom} being passed to `larkdocio`, and no command defines "
        f"them — a reader who copies the line gets an error"
    )


def test_ac5_the_invocation_scan_does_not_claim_a_CONSUMER_SCRIPTS_flags(readme):
    """The must-not-bite that decides whether this leg is livable at all.

    The README documents the consumer's own refresh script beside this CLI —
    ``scripts/update_larkdocio.sh --check`` — and ``--check`` is that script's flag, not a
    larkdocio one. A scan that could not tell the difference would report a permanent phantom
    and be deleted within a week.
    """
    assert "--check" in readme, "the probe is stale — the README no longer shows --check"
    assert "--check" not in fd.invocation_option_tokens(readme)
    assert fd.invocation_option_tokens(
        "scripts/update_larkdocio.sh --check    # report-only\n"
        "vendor/larkdocio-1.20.0-py3-none-any.whl\n"
    ) == set()


def test_ac5_the_invocation_scan_does_not_read_a_WHEEL_FILENAME_as_flags(readme):
    """The second must-not-bite, and it is not hypothetical — the README prints the pinned
    requirement line and the wheel name repeatedly. ``larkdocio-1.20.0-py3-none-any.whl``
    contains three hyphen-prefixed runs, none of which is a flag; the discriminator is that an
    option is a **separate word**."""
    assert "py3-none-any" in readme, "the probe is stale — the wheel name is gone"
    scanned = fd.invocation_option_tokens(readme)
    assert scanned and "-py3-none-any" not in scanned and "-py3" not in scanned
    assert fd.invocation_option_tokens(
        "larkdocio @ file:./vendor/larkdocio-<ver>-py3-none-any.whl\n"
        "pip install larkdocio-1.20.0-py3-none-any.whl\n"
    ) == set()


def test_ac5_the_invocation_scan_reads_a_real_invocation_including_a_global_option():
    scanned = fd.invocation_option_tokens(
        'larkdocio --env-file /path/to/.env download "<URL>" -o ./out/\n'
        "larkdocio config --appId YOUR_APP_ID --appSecret YOUR_APP_SECRET\n"
    )
    assert scanned == {"--env-file", "-o", "--appId", "--appSecret"}


def test_ac5_the_invocation_scan_bites_on_an_invented_flag():
    assert "--turbo" in fd.invocation_option_tokens('larkdocio download --turbo "<URL>"\n')


@pytest.mark.parametrize(
    "marker, command_path",
    [(_DOWNLOAD_MARKER, ("download",)), (_GLOBAL_MARKER, ()),
     (_ROUNDTRIP_MARKER, ("roundtrip",))],
)
def test_ac5_each_documented_bullet_list_matches_click_exactly(readme, marker, command_path):
    documented = fd.documented_options(readme, marker)
    assert documented, f"the options list at {marker!r} could not be parsed"
    undocumented, phantom = fd.two_way_diff(documented, fd.click_options(command_path))
    assert not undocumented, f"{marker!r}: click defines {undocumented}, the README omits them"
    assert not phantom, f"{marker!r}: the README documents {phantom}, click has no such option"


def test_ac5_dropping_a_bullet_reddens_THROUGH_THE_REAL_PARSE(readme):
    """Direction one, end to end: remove the bullet from the README text itself."""
    stripped = "\n".join(
        line for line in readme.splitlines() if "`--dump`" not in line
    )
    documented = fd.documented_options(stripped, _DOWNLOAD_MARKER)
    undocumented, _phantom = fd.two_way_diff(documented, fd.click_options(("download",)))
    assert undocumented == ["--dump"]


def test_ac5_inventing_a_bullet_reddens_THROUGH_THE_REAL_PARSE(readme):
    """Direction two, end to end: a documented flag click does not define.

    The insertion point is located **inside the download bullet list**, not at the README's
    first mention of ``--dump``: `folder` documents a ``--dump`` of its own further up, and a
    locator that grabbed the first mention would splice the phantom bullet into a different
    list and then assert the guard was blind.
    """
    lines = readme.splitlines()
    marker_at = next(index for index, line in enumerate(lines) if _DOWNLOAD_MARKER in line)
    at = next(index for index, line in enumerate(lines)
              if index > marker_at and "`--dump`" in line)
    lines.insert(at, "- `--turbo` — makes it faster, allegedly.")
    documented = fd.documented_options("\n".join(lines), _DOWNLOAD_MARKER)
    _undocumented, phantom = fd.two_way_diff(documented, fd.click_options(("download",)))
    assert phantom == ["--turbo"]


def test_ac5_the_rendered_help_page_shows_exactly_the_options_click_defines():
    """The ``--help`` page is itself a shipped surface now, so pin that the page a user reads
    and the params the README is checked against are the same set. A future ``hidden=True``
    option would be documented-but-invisible, and this is what says so."""
    for label, page in consumer_text.cli_help_pages().items():
        command_path = tuple(label.split()[1:-1])
        assert fd.help_page_options(page) == fd.click_options(command_path), label


def test_ac5_the_help_page_option_parser_bites_on_a_missing_entry():
    page = (
        "Usage: larkdocio download [OPTIONS] URL\n\nOptions:\n"
        "  -o, --output TEXT  output directory\n  --help             Show this message.\n"
    )
    assert fd.help_page_options(page) == {"-o", "--output"}
    assert fd.help_page_options(
        page.replace("  -o, --output TEXT  output directory\n", "")
    ) == set()


# --------------------------------------------------------------------------- #
# AC6 — the wheel Summary ↔ the surfaces capabilities() reports                  #
# --------------------------------------------------------------------------- #

def test_ac6_the_summary_names_every_surface_the_registry_reports():
    """Derived from ``capabilities()``, so shipping a new surface family widens the
    requirement with nobody editing a list."""
    description = fd.pyproject()["project"]["description"]
    gaps = fd.description_surface_gaps(description)
    assert not gaps, (
        f"the wheel Summary — the one line a package index shows — never says {gaps}, so "
        f"those surfaces are invisible to anyone who reads only it. Have: {description!r}"
    )


def test_ac6_dropping_a_surface_word_from_the_summary_reddens():
    """Proven red per surface word, one at a time, so the check cannot be satisfied by
    happening to mention just one of them."""
    for word in sorted(fd.required_surface_keywords()):
        crippled = (
            "Lark toolkit — reader, writer, sheets read/write, comments read, contacts "
            "lookup."
        ).replace(word, "thing")
        assert word in fd.description_surface_gaps(crippled, {word}), (
            f"removing {word!r} did not redden the Summary check"
        )


def test_ac6_the_check_is_WORD_LEVEL_and_does_not_dictate_the_prose():
    """The deliberate limit. Reword the Summary completely, keep the surface words, and it
    still passes — the guard owes the reader coverage, not a house style."""
    reworded = (
        "Feishu/Lark automation kit: docx to Markdown, gated writes, Sheets both ways, "
        "base tables and their schema, drive folders, their versions, their files and "
        "who has access, comments, and contacts name lookup."
    )
    assert fd.description_surface_gaps(reworded) == []
    stylish = ("docx · sheets · base · schema · write · drive · versions · access · "
               "files · folders · comments · contacts — a Lark kit.")
    assert fd.description_surface_gaps(stylish) == []


def test_ac6b_the_front_door_PARAGRAPH_denies_no_write_the_registry_reports():
    """**LD-474.** ``larkdocio.__doc__`` is the first paragraph a new reader meets, and it
    said of the Base surface *"It writes rows and it does not write the schema — nothing here
    creates, renames, converts or deletes a field, a table or a view"* while ``capabilities()``
    reported a **fifteen-operation** ``base-schema-write`` surface doing exactly those verbs;
    it also called ``drive/`` **Read-only** across four shipped Drive write surfaces.

    Nothing connected that paragraph to the registry, so it rotted in silence for several
    releases. This is that connection, and it is derived: a new write surface widens the check
    with nobody editing a list.
    """
    offenders = fd.front_door_write_denials()
    assert not offenders, (
        "larkdocio.__doc__ denies a write on a domain capabilities() reports a WRITE surface "
        f"for — the front door contradicting the registry: {offenders}")


@pytest.mark.parametrize("domain", sorted(fd.writing_domains()))
def test_ac6b_the_paragraph_guard_bites_per_domain_one_at_a_time(domain):
    """Proven red per writing domain, so the guard cannot be satisfied by happening to catch
    one of them — the synthetic bullet is the shape the real rot took: the denial in a
    **different sentence** from the surface word, which is why the unit is the bullet."""
    synthetic = (f"* ``{domain}/`` — the surface, and how to reach it.\n"
                 f"  It writes rows and it does not write the schema.\n")
    caught = {found for found, _phrase, _block in fd.front_door_write_denials(synthetic)}
    assert domain in caught, f"a write denial about {domain!r} did not redden the guard"


def test_ac6b_the_REAL_ROTTED_SENTENCES_are_what_the_guard_was_proven_on():
    """Red on the literal text that shipped through 1.34 — both defects, verbatim.

    A guard written after the fact is only worth what it catches, so it is run against the two
    real paragraphs rather than only against a synthetic of the same shape.
    """
    base_as_shipped = (
        "* ``base/`` — the Base (bitable) surface, **read plus a plan-gated RECORD write**: a\n"
        "  Base's tables to titled Markdown tables, and a write engine that previews every\n"
        "  change as a ``Plan`` before it sends one. **It writes rows and it does not\n"
        "  write the schema** — nothing here creates, renames, converts or deletes a field.\n"
    )
    drive_as_shipped = (
        "* ``drive/`` — the **folder read**: hand one folder link and it enumerates the tree\n"
        "  and reads every document inside. Read-only; a child it cannot read is disclosed by\n"
        "  name rather than dropped.\n"
    )
    assert {found for found, _p, _b in fd.front_door_write_denials(base_as_shipped)} == {"base"}
    assert {found for found, _p, _b in fd.front_door_write_denials(drive_as_shipped)} == {"drive"}


def test_ac6b_the_guard_still_allows_an_OPERATION_to_be_described_by_ITS_MECHANISM():
    """The deliberate limit, and the shape the fix took. A single op that makes no write call
    may say so — by naming the mechanism rather than reaching for an absolute the registry can
    contradict. And a domain with **no** write surface may still be called read-only."""
    honest = ("* ``drive/`` — the folder read enumerates a tree; the walk itself issues no "
              "call on the write pair and needs no write credentials.")
    assert fd.front_door_write_denials(honest) == []
    non_writing = "* ``contacts/`` — the name lookup. It is read-only and creates nothing."
    assert "contacts" not in fd.writing_domains()
    assert fd.front_door_write_denials(non_writing) == []


def test_ac6_the_required_words_come_out_of_the_registry_not_a_literal_list():
    surfaces = set(consumer_text.larkdocio.capabilities(full=True)["surfaces"])
    assert surfaces, "capabilities() reports no surfaces"
    required = fd.required_surface_keywords()
    assert required >= {"docx", "sheets", "write", "comments"}
    for word in required:
        assert any(word in surface_id for surface_id in surfaces), (
            f"{word!r} is not derived from any surface id — it is a hand-kept literal"
        )


# =====================================================================
# AC7 — THE SHIPPED-CITATION GUARD
#
# A wheel-only consumer clicking `tests/test_guide.py` finds nothing. So a
# citation inside a doc the wheel carries must either resolve INSIDE the
# wheel or warn the reader first, with one canonical label phrase.
#
# The scope is derived from `[tool.setuptools.package-data]`, so packaging a
# doc enrols it with nobody remembering to.
# =====================================================================

#: Packaged docs excluded on PRINCIPLE, each with the reason. Not a convenience list: the
#: reason is asserted present and the exclusion is asserted still necessary.
CITATION_SCOPE_EXCLUSIONS = {
    "src/larkdocio/blocks/BLOCK_TYPES.md": (
        "a CONTRIBUTOR document — how to add a handler to this repo's registry. Its audience "
        "stands in the dev repo, which is where every path it cites resolves; the same "
        "reasoning already keeps it out of the guarded consumer corpus."
    ),
}
# LD-691 (maintainer ruling 2, D-121 (3)) superseded the conclusion of the packaged CHANGELOG.md's
# exclusion, and upheld its reason. The reason: the internal log is a HISTORICAL RECORD whose
# entries cite where each release's work lived at the time, and relabelling them retroactively is
# the falsification, not the fix. The packaged copy is now the project's PUBLIC changelog in both
# trees — it carries no such citations — so the exclusion protected nothing
# (test_ac7_each_principled_exclusion_is_reasoned_and_still_earns_its_place reddened on it) and
# the document moved to ABSOLUTELY_CLEAN_DOCS below: held to the front door's full standard.

#: Pre-existing debt in the two docs this issue may not touch: they are ``guide()`` and
#: ``writer_brief()``, whose prose is out of scope here and whose labelling is parked as its
#: own piece of work. Enumerated **path by path** rather than waived per document, which is
#: what makes this a RATCHET: a NEW unlabelled citation in either doc still reddens, while the
#: debt already on the books does not block. Every entry is asserted to still be a real
#: offender, so a fixed citation must leave this table.
DEFERRED_CITATION_DEBT = {
    # LD-712 (round 10, R10-14) paid this doc's three test rows and its ``src`` row: those
    # citations now wear "(in the source repository)".
    "src/larkdocio/GUIDE.md": {
        ".env.example",
        "consumers/update_larkdocio.sh",
    },
    # LD-694 paid this module's two dev/ rows: they now wear the label (and are no longer links).
    "src/larkdocio/write/README.md": {
        "src/larkdocio/auth.py",
        "tests/authoring_gate.py",
        "tests/test_compose_roundtrip_corpus.py",
    },
}

#: The docs held to the standard with no allowance at all — the front door proper.
ABSOLUTELY_CLEAN_DOCS = ("README.md", "src/larkdocio/RELEASE_NOTES.md", "src/larkdocio/CHANGELOG.md")


def _offender_paths(doc_rel, text=None):
    text = fd.shipped_doc_texts()[doc_rel] if text is None else text
    return {raw.rstrip("/") for _lineno, raw, _heading in fd.unlabelled_shipped_citations(
        doc_rel, text
    )}


def test_ac7_the_scope_is_every_packaged_doc_plus_the_metadata_body():
    """Derived, not listed. ``README.md`` is in it because ``readme = "README.md"`` makes the
    wheel carry it as surely as a packaged file; everything else comes out of ``package-data``,
    which is what auto-enrolled the two release documents when they were packaged."""
    scope = set(fd.shipped_doc_texts())
    packaged_markdown = {
        rel for rel in fd.packaged_doc_paths() if rel.endswith(".md")
    }
    assert scope == packaged_markdown | {"README.md"}
    for auto_enrolled in ("src/larkdocio/CHANGELOG.md", "src/larkdocio/RELEASE_NOTES.md"):
        assert auto_enrolled in scope, (
            f"{auto_enrolled} is packaged but the citation guard does not see it — the "
            f"package-data derivation is broken"
        )


@pytest.mark.parametrize("doc_rel", ABSOLUTELY_CLEAN_DOCS)
def test_ac7_the_front_door_cites_nothing_the_wheel_lacks_without_the_label(doc_rel):
    offenders = fd.unlabelled_shipped_citations(doc_rel, fd.shipped_doc_texts()[doc_rel])
    assert not offenders, (
        f"{doc_rel} sends a wheel-only reader to a file the wheel does not carry, with no "
        f"{fd.DEV_REPO_LABEL!r} note at or before it in the section: {offenders}"
    )
    assert doc_rel not in DEFERRED_CITATION_DEBT and doc_rel not in CITATION_SCOPE_EXCLUSIONS


def test_ac7_no_shipped_doc_carries_an_unlabelled_citation_outside_the_recorded_debt():
    """The whole-scope guard. Anything not already on the books is a defect."""
    surprises = {}
    for doc_rel in fd.shipped_doc_texts():
        if doc_rel in CITATION_SCOPE_EXCLUSIONS:
            continue
        new = _offender_paths(doc_rel) - DEFERRED_CITATION_DEBT.get(doc_rel, set())
        if new:
            surprises[doc_rel] = sorted(new)
    assert not surprises, (
        f"these citations are new, unlabelled, and point at files the wheel does not carry: "
        f"{surprises}"
    )


@private_tree.citations
@pytest.mark.parametrize("doc_rel", sorted(DEFERRED_CITATION_DEBT))
def test_ac7_a_NEW_unlabelled_citation_in_a_deferred_doc_STILL_reddens(doc_rel):
    """The ratchet, which is what makes the deferral a deferral rather than a waiver."""
    dirtied = (
        fd.shipped_doc_texts()[doc_rel]
        + "\n## A new section\n\nSee [`scripts/release.sh`](scripts/release.sh) for details.\n"
    )
    new = _offender_paths(doc_rel, dirtied) - DEFERRED_CITATION_DEBT[doc_rel]
    assert new == {"scripts/release.sh"}, (
        f"a newly added unlabelled citation in {doc_rel} slipped past the ratchet: {new}"
    )


@private_tree.citations
@pytest.mark.parametrize("doc_rel", sorted(DEFERRED_CITATION_DEBT))
def test_ac7_the_debt_table_cannot_carry_a_citation_that_is_already_FIXED(doc_rel):
    """Anti-rot in the other direction: label a citation and its row must go. Otherwise the
    table slowly becomes a blanket exemption nobody rereads."""
    stale = sorted(DEFERRED_CITATION_DEBT[doc_rel] - _offender_paths(doc_rel))
    assert not stale, (
        f"{doc_rel} no longer has an unlabelled citation of {stale} — delete those rows from "
        f"DEFERRED_CITATION_DEBT; the debt is paid"
    )


def test_ac7_the_debt_table_names_only_docs_that_actually_ship():
    scope = set(fd.shipped_doc_texts())
    assert set(DEFERRED_CITATION_DEBT) <= scope
    assert set(CITATION_SCOPE_EXCLUSIONS) <= scope
    assert not set(DEFERRED_CITATION_DEBT) & set(CITATION_SCOPE_EXCLUSIONS), (
        "a doc cannot be both principally excluded and carrying enumerated debt"
    )


@pytest.mark.parametrize("doc_rel, reason", sorted(CITATION_SCOPE_EXCLUSIONS.items()))
def test_ac7_each_principled_exclusion_is_reasoned_and_still_earns_its_place(doc_rel, reason):
    """An exclusion with no reason is an oversight, and an exclusion protecting a doc that has
    nothing to protect should simply be deleted."""
    assert len(reason) > 80, f"{doc_rel} is excluded without a usable reason"
    assert _offender_paths(doc_rel), (
        f"{doc_rel} has no unlabelled citations at all — its exclusion is dead weight now"
    )


# --------------------------------------------------------------------------- #
# AC7's red proofs, and the release-documents coordination point                #
# --------------------------------------------------------------------------- #

def test_ac7_citing_a_non_packaged_file_without_the_label_is_reported():
    text = "## Recipes\n\nThe harness is [`tests/harness.py`](tests/harness.py).\n"
    offenders = fd.unlabelled_shipped_citations("src/larkdocio/GUIDE.md", text)
    assert [raw for _l, raw, _h in offenders] == ["tests/harness.py"]


def test_ac7_the_READERS_OWN_dot_git_directory_is_NOT_a_citation_of_a_repo_file():
    """The one path the existence heuristic cannot judge, and why it is excluded by name.

    ``cited_repo_paths`` decides "is this a claim about this repo's contents?" by asking
    whether the path exists here — which is right for a consumer-tree path like
    ``scripts/update_larkdocio.sh`` (absent, so left alone) and wrong for exactly one family:
    ``.git/…`` exists in **every** clone by construction, so a document telling a consumer
    where *their own* git reads hooks from was read as citing a file this wheel fails to
    carry. It never can carry one — ``.git`` is repository metadata, not a tracked file — so
    the label the guard would demand could only be a falsehood about the reader's own tree.

    The guard's reason is untouched: a wheel-only reader must not be sent to a file the wheel
    lacks. What changed is one family of path that was never such a citation.
    """
    text = ("## Advisory update nag\n\nGit reads hooks from `.git/hooks` unless "
            "`core.hooksPath` says otherwise; the stale copy in `.git/hooks/post-merge` is "
            "harmless.\n")
    assert fd.unlabelled_shipped_citations("src/larkdocio/RELEASE_NOTES.md", text) == []
    assert (pathlib.Path(fd.REPO_ROOT) / ".git" / "hooks").exists(), (
        "the exclusion is vacuous unless `.git/hooks` really does resolve in this checkout — "
        "which is the whole reason the existence heuristic mis-classified it")


def test_ac7_the_dot_git_exclusion_does_NOT_reach_a_TRACKED_dotfile():
    """Narrow by construction: ``.gitignore`` starts with the same four characters and is a
    real tracked file, so it must still be seen."""
    text = "## Recipes\n\nThe ignore rules are in [`.gitignore`](.gitignore).\n"
    offenders = fd.unlabelled_shipped_citations("src/larkdocio/GUIDE.md", text)
    assert [raw for _l, raw, _h in offenders] == [".gitignore"]


def test_ac7_the_same_citation_labelled_in_its_section_is_accepted():
    text = (
        "## Recipes\n\nThe files below live in the dev repo, not in the wheel.\n\n"
        "The harness is [`tests/harness.py`](tests/harness.py).\n"
    )
    assert not fd.unlabelled_shipped_citations("src/larkdocio/GUIDE.md", text)


def test_ac7_a_PACKAGED_SIBLING_citation_resolves_inside_the_wheel():
    """The coordination point with the release documents' packaging.

    Inside the wheel the two release documents are siblings under ``larkdocio/``, so the
    changelog's ``RELEASE_NOTES.md`` link really does resolve for a wheel-only reader — even
    though that spelling is not the repo-relative path. Resolving relative to the citing
    document is what makes the auto-enrolment actually work rather than merely widen a set.
    """
    text = "# Changelog\n\nConsumer-facing notes: [`RELEASE_NOTES.md`](RELEASE_NOTES.md).\n"
    assert not fd.unlabelled_shipped_citations("src/larkdocio/CHANGELOG.md", text)


def test_ac7_that_sibling_citation_becomes_an_OFFENDER_if_the_file_is_un_packaged():
    """The red half of the same claim: strip the declaration and the citation is a defect
    again. So the acceptance above comes from the packaging, not from a special case."""
    text = "# Changelog\n\nConsumer-facing notes: [`RELEASE_NOTES.md`](RELEASE_NOTES.md).\n"
    without = {
        rel for rel in fd.packaged_doc_paths() if rel != "src/larkdocio/RELEASE_NOTES.md"
    }
    offenders = fd.unlabelled_shipped_citations(
        "src/larkdocio/CHANGELOG.md", text, packaged=without
    )
    assert [raw for _l, raw, _h in offenders] == ["RELEASE_NOTES.md"]


def test_ac7_a_sibling_resolution_does_not_excuse_a_DIFFERENT_directorys_file():
    """The scoping must not be so generous that any basename passes: a citation only resolves
    from the directory it is written in."""
    text = "# Notes\n\nSee [`BLOCK_TYPES.md`](BLOCK_TYPES.md).\n"
    assert "src/larkdocio/BLOCK_TYPES.md" not in fd.packaged_doc_paths()
    assert not fd.wheel_carries("src/larkdocio/CHANGELOG.md", "BLOCK_TYPES.md",
                                fd.packaged_doc_paths())
    assert fd.wheel_carries("src/larkdocio/blocks/BLOCK_TYPES.md", "BLOCK_TYPES.md",
                            fd.packaged_doc_paths())
    assert not fd.unlabelled_shipped_citations("src/larkdocio/CHANGELOG.md", text)


def test_ac7_a_DANGLING_link_is_OUT_OF_SCOPE_and_the_decision_is_pinned():
    """The decision the amplifier asks for, recorded rather than left implicit.

    A citation of a path that exists **nowhere** is not reported. That is deliberate: these
    docs legitimately cite paths in the *consumer's* tree (``scripts/update_larkdocio.sh``,
    the reader's own ``.env``), which resolve for the reader and not here, so a
    "does it exist?" check would be a permanent false-positive generator. This guard answers
    exactly one question — *does the wheel carry what it sends you to?* — and a broken link is
    a different defect class, not this one's.
    """
    text = "## Section\n\nSee [`docs/nonexistent-file.md`](docs/nonexistent-file.md).\n"
    assert not fd.cited_repo_paths(text), "the probe path exists after all — pick another"
    assert not fd.unlabelled_shipped_citations("src/larkdocio/GUIDE.md", text)
    consumer_side = "## Refreshing\n\nRun `scripts/update_larkdocio.sh` in your repo.\n"
    assert not fd.unlabelled_shipped_citations("src/larkdocio/GUIDE.md", consumer_side)


def test_ac7_a_LABELLED_citation_is_still_COUNTED_as_a_citation():
    """The label is a warning, not an excuse to stop counting: the paths themselves are still
    reported by the citation scan, which is what lets the deferred debt be enumerated at all."""
    text = (
        "## Recipes\n\nThe files below live in the dev repo.\n\n"
        "See [`tests/harness.py`](tests/harness.py).\n"
    )
    assert [raw for _l, raw in fd.cited_repo_paths(text)] == ["tests/harness.py"]
    assert not fd.unlabelled_shipped_citations("src/larkdocio/GUIDE.md", text)


def test_ac7_the_readme_helper_and_the_shipped_helper_agree_on_the_readme():
    """The README-only function shipped by the truth-fix is now one call into the general one;
    pin that the generalization changed nothing for its original caller."""
    readme_text = fd.readme_text()
    assert fd.unlabelled_dev_repo_citations(readme_text) == fd.unlabelled_shipped_citations(
        "README.md", readme_text
    )


# =====================================================================
# (c) AC8-AC12 — THE DEFINITION-OF-DONE HALF, guarded
#
# The four process documents commit direct to `develop` (they are
# metadata, not code) while these guards ride the work branch. A written
# duty with nothing checking it is a habit, and habits are what let the
# front door rot in the first place — so the lines are pinned here.
# =====================================================================

#: What each process document owes the doctrine. Phrases are compared through
#: :func:`doc_prose.prose`, so emphasis, backticks, case and line wrapping are all free —
#: the assertion is about the words and only the words.
_FRONT_DOOR_CLAIMS = ("front door", "tests/test_front_door_doctrine.py", "README", "Summary",
                      "--help")

DOCTRINE_DOCS = {
    ".claude/roles/dev.md": ("## Definition of Done", _FRONT_DOOR_CLAIMS + (
        "in the same change",
    )),
    ".claude/roles/qa.md": (None, _FRONT_DOOR_CLAIMS + (
        "the front door must agree",
    )),
    "CLAUDE.md": ("## House rules", _FRONT_DOOR_CLAIMS + (
        "consumer-doc truth is part of shipping",
    )),
    "PROJECT.md": ("## Quality bar", _FRONT_DOOR_CLAIMS + (
        "consumer-doc truth is part of shipping",
    )),
}


def _section(text, heading):
    """The slice of ``text`` under ``heading``, up to the next heading of the same depth.

    ``None`` means the whole document. Section-scoped on purpose: a rule written into the
    *wrong* section is findable by a whole-file grep and useless to the person reading the
    checklist it belongs in.
    """
    if heading is None:
        return text
    lines = text.splitlines()
    depth = len(heading) - len(heading.lstrip("#"))
    start = next(
        (index for index, line in enumerate(lines) if line.strip() == heading), None
    )
    assert start is not None, f"{heading!r} is not a heading in this document"
    for offset, line in enumerate(lines[start + 1:], start=start + 1):
        stripped = line.strip()
        if stripped.startswith("#") and len(stripped) - len(stripped.lstrip("#")) <= depth:
            return "\n".join(lines[start:offset])
    return "\n".join(lines[start:])


def doctrine_gaps(text, heading, claims):
    """The claims the doctrine owes that ``text``'s ``heading`` section never makes."""
    return missing_phrases(_section(text, heading), claims)


@private_tree.process
@pytest.mark.parametrize("relative, spec", sorted(DOCTRINE_DOCS.items()))
def test_ac9_to_ac12_each_process_document_carries_the_front_door_duty(relative, spec):
    heading, claims = spec
    text = (fd.REPO_ROOT / relative).read_text(encoding="utf-8")
    gaps = doctrine_gaps(text, heading, claims)
    assert not gaps, (
        f"{relative}{'' if heading is None else ' ' + heading} does not state the front-door "
        f"duty — missing {gaps}. Without it the doctrine is a habit, and a habit is what let "
        f"the front door rot unwatched."
    )


@private_tree.process
@pytest.mark.parametrize("relative, spec", sorted(DOCTRINE_DOCS.items()))
def test_ac9_to_ac12_the_duty_check_bites_when_the_line_is_deleted(relative, spec):
    """Red proof per document, over the real file with the doctrine text stripped out — so a
    future edit that quietly drops the line cannot pass."""
    heading, claims = spec
    text = (fd.REPO_ROOT / relative).read_text(encoding="utf-8")
    stripped = "\n".join(
        line for line in text.splitlines()
        if "front door" not in line.lower() and "front-door" not in line.lower()
    )
    gaps = doctrine_gaps(stripped, heading, claims)
    assert "front door" in gaps, (
        f"deleting every front-door line from {relative} did not redden the check: {gaps}"
    )


@private_tree.process
def test_ac9_the_dev_dod_line_sits_BESIDE_the_capability_matrix_line():
    """Placement is the requirement, not just presence: same checklist, same register. A
    reader scanning the Definition of Done meets both duties together or neither."""
    text = (fd.REPO_ROOT / ".claude" / "roles" / "dev.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    matrix = next(
        index for index, line in enumerate(lines)
        if line.startswith("- [ ]") and "capability matrix updated" in line.lower()
    )
    door = next(
        index for index, line in enumerate(lines)
        if line.startswith("- [ ]") and "front door" in line.lower()
    )
    assert abs(door - matrix) <= 2, (
        f"the front-door duty is at line {door + 1} and the capability-matrix duty at "
        f"{matrix + 1} — they are meant to read as one rule"
    )
    assert lines[door] in _section(text, "## Definition of Done"), (
        "the front-door duty is not under the Definition of Done"
    )


@private_tree.process
def test_ac10_the_qa_check_sits_in_THE_SAME_CHECKLIST_as_the_sheets_matrix_check():
    lines = (fd.REPO_ROOT / ".claude" / "roles" / "qa.md").read_text(
        encoding="utf-8"
    ).splitlines()
    sheets = next(
        index for index, line in enumerate(lines)
        if "SHEETS.md" in line and "must agree" in line
    )
    door = next(
        index for index, line in enumerate(lines) if "the front door must agree" in line
    )
    assert lines[door].startswith(lines[sheets][:len("   - PR touches")]), (
        "the front-door check is not written as a sibling of the other 'PR touches …' bullets"
    )
    assert abs(door - sheets) <= 3, (
        f"the front-door check (line {door + 1}) is not in the same boundary checklist as the "
        f"Sheets-matrix check (line {sheets + 1})"
    )


@private_tree.process
def test_ac11_the_house_rule_reads_as_ONE_rule_not_two_habits():
    """The matrices bullet itself has to carry the front door, or a reader learns two
    unrelated habits instead of one standard."""
    house = _section(
        (fd.REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8"), "## House rules"
    )
    bullet = next(
        (block for block in house.split("\n- ") if "living capability matrices" in prose(block)),
        None,
    )
    assert bullet, "CLAUDE.md § House rules has no capability-matrices bullet any more"
    assert not missing_phrases(bullet, ("front door", "BLOCKS.md", "SHEETS.md")), (
        "the capability-matrices house rule does not name the front door, so the doctrine "
        "still reads as two separate habits"
    )


@private_tree.citations
def test_ac8_the_two_path_split_is_real_the_guards_are_code_the_duty_is_metadata():
    """AC8, mechanically: the guards live under ``tests/`` (they ride a feature branch) and
    every document carrying the duty is metadata (it commits direct to the trunk). If a
    doctrine document were ever moved under ``src/`` this pin would say so."""
    for relative in DOCTRINE_DOCS:
        assert not relative.startswith(("src/", "tests/")), relative
        assert (fd.REPO_ROOT / relative).is_file(), f"{relative} is missing"
    assert (fd.REPO_ROOT / "tests" / "test_front_door_doctrine.py").is_file()


# =====================================================================
# LD-300 — THE SHIPPED-SOURCE CITATION GUARD
#
# AC7 above holds every packaged MARKDOWN doc to "cite nothing the wheel
# lacks, or say so". A docstring is shipped text by exactly the same
# argument — `help(larkdocio.base)` and every IDE hover render it, and a
# vendoring consumer's whole view of this library is the wheel — but it
# was outside that scope, and the Base era put 28 `BASE.md` pointers plus
# one live `../../../BASE.md` relative link inside it.
#
# Same shape as AC7, one scope wider: derived pool, one canonical label,
# an enumerated debt table that ratchets in both directions.
# =====================================================================

#: What ``base/__init__.py`` — the package front door, and what ``help(larkdocio.base)`` prints
#: first — owes a wheel-only reader beyond the bare label: the two accessors that ARE in the
#: wheel. Stated in one place rather than 28: a label makes a pointer honest, and this makes it
#: useful, which is the answer to direction 3's own recorded cost ("honest but unhelpful").
SHIPPED_EQUIVALENTS = ("larkdocio.capabilities()", "larkdocio.guide()")

#: Why each family of pre-existing dead pointer is DEFERRED rather than fixed here, keyed by the
#: family :func:`_debt_family` sorts a path into. Every row of :data:`SOURCE_CITATION_DEBT` must
#: land in one of these, so a NEW *kind* of dead pointer cannot be parked without a reason being
#: written for it — the property that makes this a debt register and not an allow-list.
DEBT_FAMILY_REASONS = {
    # ``sibling-matrix`` was here — LD-300's AC5 deferral of ``BLOCKS.md`` / ``SHEETS.md`` /
    # ``PERMISSIONS.md``. **LD-313 PAID it** (22 pointers over 16 modules, labelled), so the
    # reason went with the rows: a reason guarding a family with no members is exactly what
    # ``test_ld300_every_deferred_family_is_reasoned_and_still_has_members`` deletes. The family
    # itself deliberately survives in :func:`_debt_family` — see the note there.
    "guard-test": (
        "A pointer at the test that PROVES the claim just made — ``tests/test_capabilities.py``, "
        "``tests/sheets_write_harness.py``. This repo's docstrings cite their own guard as the "
        "evidence for an assertion, which is a house convention worth keeping; what a wheel-only "
        "reader needs is to be told the file is not theirs. That is a one-line-per-module sweep "
        "across 30 modules on every surface, deliberately out of this fix's blast radius."
    ),
    "probe-capture": (
        "An evidence pointer at a probe capture or study document under ``dev/`` — the JSON body "
        "a behavioural claim was measured from. Same shape as the guard-test family and the same "
        "reason for deferring it: the pointers are true and load-bearing for the contributor who "
        "re-derives the claim, and relabelling them is a sweep over surfaces this issue does not "
        "touch. ``base/`` is the exception, paid here, because its captures sit beside the "
        "register pointers the note already covers."
    ),
    "process-doc": (
        "A pointer at this repo's own process documents — ``PROJECT.md``, ``CLAUDE.md``, "
        "``.env.example``. The reader is being told which rule governs a decision, and the rule "
        "lives where the project is developed. Deferred with the other two sweeps rather than "
        "fixed piecemeal, so one issue pays one family and the table shows what is left."
    ),
}


def _debt_family(cited):
    """Which reasoned family ``cited`` belongs to, or ``None`` — an unreasoned pointer.

    ``sibling-matrix`` is kept although LD-313 paid it and its reason is gone: the sorting is
    what makes a RELAPSE loud. Re-park one of the three and the row lands in a family with no
    written reason, so ``test_ld300_every_debt_row_belongs_to_a_reasoned_family`` reddens
    instead of the pointer quietly returning to the books.
    """
    if cited in ("BLOCKS.md", "SHEETS.md", "PERMISSIONS.md"):
        return "sibling-matrix"
    if cited.startswith("tests/"):
        return "guard-test"
    if cited.startswith("dev/") or cited.endswith(".json"):
        return "probe-capture"
    if cited in ("PROJECT.md", "CLAUDE.md", ".env.example"):
        return "process-doc"
    return None


#: Pre-existing dead pointers in shipped source, enumerated **path by path per module** — the
#: shape ``DEFERRED_CITATION_DEBT`` above proves for packaged docs, for the same reason: a
#: per-path table is a RATCHET (a new pointer still reddens) where a per-module waiver would be
#: a blanket exemption nobody rereads. ``BASE.md`` appears nowhere in it — that debt is PAID by
#: this issue, and ``test_ld300_the_register_is_cited_nowhere_without_the_label_before_it``
#: asserts it stays paid. Nor do ``BLOCKS.md`` / ``SHEETS.md`` / ``PERMISSIONS.md``: LD-313 paid
#: the whole ``sibling-matrix`` family the same way, and the LD-313 section asserts that too.
#: LD-694 moved four rows' ADDRESSES, not their debt: the probe captures they cite are carried
#: by the repository as ``tests/captures/<probe>/…`` (the public tree has no ``dev/``), so the
#: citation now names the copy a reader can open — still a file the wheel lacks, still unlabelled.
SOURCE_CITATION_DEBT = {
    "src/larkdocio/__init__.py": {"tests/test_release_notes_accessor.py"},
    "src/larkdocio/base/cells.py": {"tests/test_live_base_canary.py"},
    "src/larkdocio/base/client.py": {"03-records-batch-get.json"},
    "src/larkdocio/base/diff.py": {"tests/test_base_model.py"},
    "src/larkdocio/base/embed.py": {
        "02-bitable18-tables.json",
        "p0-1-05-fresh-embed-bridge.json",
    },
    "src/larkdocio/base/field_authoring.py": {"p0-2-06-table-revision-granularity.json"},
    "src/larkdocio/base/read.py": {".env.example"},
    "src/larkdocio/base/table.py": {"02-bitable18-tables.json", "p0-3-03-view-projection.json"},
    "src/larkdocio/base/view_filters.py": {"p1-q3-01-filter-sort.json"},
    "src/larkdocio/blocks/read_support.py": {"tests/test_blocks_md_matrix.py"},
    "src/larkdocio/blocks/synced.py": {"tests/test_synced.py"},
    "src/larkdocio/capabilities/_config.py": {"tests/test_download_output_docs.py"},
    "src/larkdocio/capabilities/_contracts.py": {
        "tests/test_apply_log_complete_house_invariant.py",
    },
    "src/larkdocio/capabilities/_gates.py": {"tests/test_capabilities.py"},
    "src/larkdocio/capabilities/_models.py": {"tests/test_release_notes_accessor.py"},
    "src/larkdocio/common/auth.py": {".env.example"},
    "src/larkdocio/common/staleness.py": {"tests/test_staleness_core.py"},
    "src/larkdocio/common/transport.py": {"dev/write-spike/07-report.md"},
    "src/larkdocio/contacts/client.py": {"dev/name-lookup-spike/reprobe/reprobe-verdict.md"},
    "src/larkdocio/guide.py": {"tests/test_guide.py", "tests/test_release_notes_accessor.py"},
    "src/larkdocio/model/conservation.py": {"tests/test_opaque_marker_conservation.py"},
    "src/larkdocio/model/nodes.py": {"tests/test_parser_spine.py"},
    "src/larkdocio/model/renderer.py": {"tests/test_heading_level_cap.py"},
    "src/larkdocio/permissions.py": {
        "tests/test_base_schema_destructive.py",
        "tests/test_base_schema_fields.py",
        "tests/test_base_schema_views.py",
    },
    "src/larkdocio/read/client.py": {"tests/test_comments_surface_truth.py"},
    "src/larkdocio/read/mentions.py": {"tests/test_mention_read_path_parity.py"},
    "src/larkdocio/sheets/__init__.py": {"tests/test_sheets_registration_seam.py"},
    "src/larkdocio/sheets/client.py": {"tests/test_sheets_client.py"},
    "src/larkdocio/sheets/disposition.py": {"tests/test_apply_disposition_invariant.py"},
    "src/larkdocio/sheets/export_reader.py": {"tests/test_sheets_export_reader.py"},
    # LD-532 split the flat ``sheets/ops.py`` into the ``sheets/ops/`` package (one module
    # per op family), so this row became three: the debt did not change, its ADDRESSES did.
    # Each pointer is still exactly where it was in the pre-split file, in the docstring or
    # the comment that moved with the code it describes.
    "src/larkdocio/sheets/ops/__init__.py": {
        "tests/sheets_write_harness.py",
        "tests/test_sheets_registration_seam.py",
    },
    "src/larkdocio/sheets/ops/_shared.py": {
        "tests/test_sheets_verification_leg_seam.py",
    },
    "src/larkdocio/sheets/ops/_styles.py": {
        "tests/sheets_write_harness.py",
    },
    "src/larkdocio/sheets/plan.py": {
        "tests/test_sheets_plan_disclosure_completion.py",
        "tests/test_sheets_registration_seam.py",
        "tests/test_staleness_core.py",
    },
    "src/larkdocio/sheets/render.py": {"03b-dropdown.json"},
    "src/larkdocio/sheets/requests/__init__.py": {
        "tests/test_sheets_requests_package_split.py",
    },
    "src/larkdocio/sheets/requests/_dimensions.py": {
        "tests/captures/sheets-dimension-probe/captures/01-put-dimension_range-INDEX-CONVENTION.json",
    },
    "src/larkdocio/sheets/requests/_styles.py": {
        "tests/captures/sheets-border-wrap-probe/captures/01-border-wrap-characterization.json",
        "tests/captures/sheets-style-write-probe/captures/01-style-write-characterization.json",
        "tests/sheets_write_harness.py",
    },
    "src/larkdocio/sheets/requests/_tabs.py": {"tests/test_sheets_tab_presentation.py"},
    "src/larkdocio/sheets/rich_encode.py": {"03-rich-cells.json", "03b-dropdown.json"},
    "src/larkdocio/sheets/write_apply.py": {"tests/test_sheets_registration_seam.py"},
    "src/larkdocio/sheets/write_client.py": {
        "tests/captures/sheets-freeze-probe/captures/01-updateSheet-FREEZE-and-metainfo-frozen-read.json",
        "tests/sheets_write_harness.py",
        "tests/test_sheets_write_client.py",
    },
    "src/larkdocio/write/client.py": {"tests/test_write_client.py"},
    "src/larkdocio/write/comments.py": {"14-demo.json"},
    "src/larkdocio/write/compose.py": {
        "tests/test_md_metachar_escaping.py",
        "tests/test_non_creatable_projection_refusal.py",
    },
    "src/larkdocio/write/model/applylog.py": {"tests/test_dry_run_preview.py"},
    "src/larkdocio/write/preview.py": {"tests/test_dry_run_preview.py"},
}


def _source_offenders(module_rel, text=None):
    text = fd.shipped_python_sources()[module_rel] if text is None else text
    return {
        raw.lstrip("/").rstrip("/")
        for _lineno, raw in fd.unlabelled_source_citations(module_rel, text)
    }


def _modules_citing(name):
    return {rel for rel, text in fd.shipped_python_sources().items() if name in text}


# --------------------------------------------------------------------------- #
# AC2 — the guard, over a pool derived from what the build produces             #
# --------------------------------------------------------------------------- #

def test_ld300_the_scope_is_every_python_module_the_wheel_carries():
    """Derived from the real tree, not listed — the property that makes the guard survive a
    module added tomorrow, and the same property AC7's scope has via ``package-data``."""
    scope = set(fd.shipped_python_sources())
    assert scope == {f"src/{module}" for module in fd.source_modules()}
    assert "src/larkdocio/base/__init__.py" in scope and len(scope) > 50


def test_ld300_the_wheel_POOL_is_the_modules_plus_the_packaged_docs_not_the_docs_alone():
    """The pool AC2 asks for: what the build actually produces. The wheel carries every ``.py``
    in the package, so a docstring naming ``schema_settle.py`` cites something a wheel-only
    reader really has — a docs-only pool would report it as a dead pointer. That this derivation
    equals the built wheel's ``RECORD`` is ``tests/test_packaging.py``'s claim, not this one's."""
    pool = fd.wheel_carried_paths()
    assert fd.packaged_doc_paths() < pool, "the pool lost the packaged docs"
    assert "src/larkdocio/base/schema_settle.py" in pool
    assert "src/larkdocio/GUIDE.md" in pool
    assert "BASE.md" not in pool and "BLOCKS.md" not in pool, (
        "a root matrix appears in the wheel pool — if one was genuinely enrolled in "
        "package-data this guard moves on its own and this assertion is what tells you"
    )


def test_ld300_enrolling_a_doc_in_package_data_MOVES_the_guard_on_its_own():
    """AC2's derivation claim, shown rather than asserted: feed the citation checker a pool that
    carries ``BASE.md`` and the same docstring stops being an offender. So the acceptances below
    come from the packaging + the label, never from a name special-cased in this file."""
    text = '"""A module.\n\nThe register is ``BASE.md`` row 13.\n"""\n'
    rel = "src/larkdocio/base/cells.py"
    assert _source_offenders(rel, text) == {"BASE.md"}
    widened = fd.wheel_carried_paths() | {"src/larkdocio/BASE.md"}
    assert not fd.unlabelled_source_citations(rel, text, widened)


def test_ld300_no_shipped_docstring_cites_an_unshipped_file_outside_the_recorded_debt():
    """The whole-scope guard (AC2). Anything not already on the books is a defect."""
    surprises = {}
    for module_rel in fd.shipped_python_sources():
        new = _source_offenders(module_rel) - SOURCE_CITATION_DEBT.get(module_rel, set())
        if new:
            surprises[module_rel] = sorted(new)
    assert not surprises, (
        f"these shipped docstrings/comments send a wheel-only reader to a file the wheel does "
        f"not carry, with no {fd.DEV_REPO_LABEL!r} note before them: {surprises}"
    )


# --------------------------------------------------------------------------- #
# AC4 — all 28 BASE.md pointers, and the one that rendered as a live link       #
# --------------------------------------------------------------------------- #

def test_ld300_the_register_is_cited_nowhere_without_the_label_before_it():
    """AC4, stated as a property rather than a count: **every** module citing ``BASE.md`` has
    zero unlabelled citations. A count would rot the moment a module gained a pointer; this
    cannot be satisfied by editing a number."""
    citing = _modules_citing("BASE.md")
    assert citing, "no shipped module cites BASE.md any more — this guard has lost its subject"
    unpaid = {
        rel: sorted(c for c in _source_offenders(rel) if c.endswith("BASE.md")) for rel in citing
    }
    unpaid = {rel: paths for rel, paths in unpaid.items() if paths}
    assert not unpaid, f"BASE.md is still cited without the label in: {unpaid}"
    on_the_books = {
        rel: sorted(c for c in paths if c.endswith("BASE.md"))
        for rel, paths in SOURCE_CITATION_DEBT.items()
        if any(c.endswith("BASE.md") for c in paths)
    }
    assert not on_the_books, (
        f"the register is deferred as debt in {on_the_books} — that debt is PAID by this issue, "
        f"delete the rows rather than parking them"
    )
    assert all(rel.startswith("src/larkdocio/base/") for rel in citing), sorted(citing)


def test_ld300_every_register_citing_module_carries_the_label_somewhere():
    """The weaker companion claim, and worth having on its own: not one of these modules relies
    on a label in a *different* file. Zero offenders is the contract; this says the reason is a
    label present here, rather than an extractor that stopped looking."""
    sources = fd.shipped_python_sources()
    for rel in sorted(_modules_citing("BASE.md")):
        assert fd.labelled(prose(sources[rel])), f"{rel} carries no label at all"  # LD-699: either


def test_ld300_the_package_front_door_names_what_a_wheel_only_reader_DOES_have():
    """Direction 3's recorded cost was "honest but unhelpful" — a reader told the answer exists
    somewhere they cannot reach. ``base/__init__.py`` is where that is paid off: the paragraph
    that de-links the register also names the two accessors the wheel really carries."""
    door = fd.shipped_python_sources()["src/larkdocio/base/__init__.py"]
    # LD-699: BASE.md is at the root of every clone, so the label it earns is the source one.
    assert not missing_phrases(door, SHIPPED_EQUIVALENTS + (fd.SOURCE_REPO_LABEL,)), (
        "the Base package docstring no longer tells a wheel-only reader both where the register "
        "is NOT and what to read instead"
    )
    import larkdocio

    for accessor in SHIPPED_EQUIVALENTS:
        assert hasattr(larkdocio, accessor.split("(")[0].split(".")[1]), (
            f"{accessor} is named as the shipped equivalent but is not on the package"
        )


def test_ld300_the_broken_relative_link_into_the_repo_root_is_GONE():
    """AC4's called-out instance: ``base/__init__.py`` rendered ``[/BASE.md](../../../BASE.md)``
    — the only citation of the four that was a *followable* link, and from
    ``site-packages/larkdocio/base/`` it followed to nothing. A label makes a prose pointer
    honest; it cannot make a broken link resolve, so the link itself had to go."""
    for rel, text in fd.shipped_python_sources().items():
        assert "../../../BASE.md" not in text, f"{rel} still carries the broken relative link"
    door = fd.shipped_python_sources()["src/larkdocio/base/__init__.py"]
    assert not missing_phrases(door, ("BASE.md", "fourth living matrix")), (
        "the front-door paragraph lost the register's name — the fix was to de-link it, not to "
        "stop naming it"
    )


# --------------------------------------------------------------------------- #
# AC3 — the debt table ratchets in BOTH directions; AC5 — every row is reasoned #
# --------------------------------------------------------------------------- #

@private_tree.citations
@pytest.mark.parametrize("module_rel", sorted(SOURCE_CITATION_DEBT))
def test_ld300_a_NEW_unlabelled_citation_in_a_debt_module_STILL_reddens(module_rel):
    """AC3(a) — the ratchet, which is what makes the deferral a deferral and not a waiver."""
    dirtied = fd.shipped_python_sources()[module_rel] + (
        '\n\ndef _added():\n    """See ``scripts/release.sh`` for the cut."""\n'
    )
    new = _source_offenders(module_rel, dirtied) - SOURCE_CITATION_DEBT[module_rel]
    assert new == {"scripts/release.sh"}, (
        f"a newly added unlabelled citation in {module_rel} slipped past the ratchet: {new}"
    )


@private_tree.citations
@pytest.mark.parametrize("module_rel", sorted(SOURCE_CITATION_DEBT))
def test_ld300_the_debt_table_cannot_carry_a_citation_that_is_already_FIXED(module_rel):
    """AC3(b) — anti-rot the other way: label a pointer and its row must go, or the table
    slowly becomes a blanket exemption nobody rereads."""
    stale = sorted(SOURCE_CITATION_DEBT[module_rel] - _source_offenders(module_rel))
    assert not stale, (
        f"{module_rel} no longer cites {stale} unlabelled — delete those rows from "
        f"SOURCE_CITATION_DEBT; the debt is paid"
    )


def test_ld300_the_debt_table_names_only_modules_that_actually_ship():
    assert set(SOURCE_CITATION_DEBT) <= set(fd.shipped_python_sources())


@pytest.mark.parametrize("family, reason", sorted(DEBT_FAMILY_REASONS.items()))
def test_ld300_every_deferred_family_is_reasoned_and_still_has_members(family, reason):
    """AC5's bar, generalized: a deferral with no written reason is a silent exclusion, and a
    reason protecting a family with no members left should simply be deleted."""
    assert len(reason) > 200, f"{family} is deferred without a usable reason"
    members = [
        cited for paths in SOURCE_CITATION_DEBT.values()
        for cited in paths if _debt_family(cited) == family
    ]
    assert members, f"the {family} family is empty — delete its reason"


def test_ld300_every_debt_row_belongs_to_a_reasoned_family():
    """No row may sit in the table unexplained — a NEW *kind* of dead pointer cannot be parked
    without someone writing why."""
    orphans = {
        module_rel: sorted(c for c in paths if _debt_family(c) not in DEBT_FAMILY_REASONS)
        for module_rel, paths in SOURCE_CITATION_DEBT.items()
        if any(_debt_family(c) not in DEBT_FAMILY_REASONS for c in paths)
    }
    assert not orphans, f"deferred with no reason written for their family: {orphans}"


def test_ld300_the_three_sibling_matrices_are_ALL_on_the_books_none_dropped():
    """AC5 read the other way: every sibling-matrix pointer in shipped source is *enumerated*
    as debt. A citation that is neither fixed nor listed would be silently excluded, which is
    the failure mode AC5 names by name. **LD-313 paid the family**, so both sides are now
    empty — the statement survives its own payment (nothing dropped, nothing parked), and the
    LD-313 section below carries the stronger property that replaced it."""
    listed = {
        (module_rel, cited) for module_rel, paths in SOURCE_CITATION_DEBT.items()
        for cited in paths if _debt_family(cited) == "sibling-matrix"
    }
    real = {
        (module_rel, cited)
        for module_rel in fd.shipped_python_sources()
        for cited in _source_offenders(module_rel)
        if _debt_family(cited) == "sibling-matrix"
    }
    assert real == listed, f"sibling-matrix pointers not on the books: {sorted(real - listed)}"


# --------------------------------------------------------------------------- #
# LD-313 — the sibling-matrix family, paid the way BASE.md was                  #
# --------------------------------------------------------------------------- #

SIBLING_MATRICES = ("BLOCKS.md", "SHEETS.md", "PERMISSIONS.md")


def test_ld313_no_sibling_matrix_is_cited_anywhere_without_the_label_before_it():
    """AC1/AC2 as a property, the shape ``BASE.md``'s payment took: **every** module citing one
    of the three sibling living matrices has zero unlabelled citations of it. A count would rot
    the moment a module gained a pointer; this cannot be satisfied by editing a number."""
    for matrix in SIBLING_MATRICES:
        citing = _modules_citing(matrix)
        assert citing, f"no shipped module cites {matrix} any more — this guard lost its subject"
        unpaid = {
            rel: sorted(c for c in _source_offenders(rel) if c.endswith(matrix))
            for rel in citing
        }
        assert not {rel: cited for rel, cited in unpaid.items() if cited}, (
            f"{matrix} is still cited unlabelled: "
            f"{ {rel: c for rel, c in unpaid.items() if c} }"
        )


def test_ld313_the_sibling_matrix_family_has_LEFT_the_debt_table_entirely():
    """AC2. The anti-rot test would redden on any single stale row; this says the same thing as
    a family-level statement, so the reason for the removal is legible without diffing."""
    on_the_books = {
        module_rel: sorted(c for c in paths if _debt_family(c) == "sibling-matrix")
        for module_rel, paths in SOURCE_CITATION_DEBT.items()
        if any(_debt_family(c) == "sibling-matrix" for c in paths)
    }
    assert not on_the_books, (
        f"the sibling matrices are deferred as debt in {on_the_books} — that debt is PAID by "
        f"LD-313, delete the rows rather than parking them"
    )
    assert "sibling-matrix" not in DEBT_FAMILY_REASONS, (
        "the family is empty; its written reason should have gone with the rows"
    )


def test_ld313_the_family_stays_a_family_so_a_RELAPSE_cannot_be_parked_silently():
    """The ratchet the payment leaves behind: ``_debt_family`` still sorts the three names into
    ``sibling-matrix``, which no longer has a written reason — so re-parking one of them in
    ``SOURCE_CITATION_DEBT`` lands as an orphan and
    ``test_ld300_every_debt_row_belongs_to_a_reasoned_family`` reddens. Paid debt cannot quietly
    come back on the books."""
    for matrix in SIBLING_MATRICES:
        assert _debt_family(matrix) == "sibling-matrix"
        assert _debt_family(matrix) not in DEBT_FAMILY_REASONS


def test_ld313_every_sibling_matrix_citing_module_carries_the_label_somewhere():
    """The weaker companion claim, worth having on its own for the same reason it was worth
    having for the register: not one of these modules relies on a label in a *different* file."""
    sources = fd.shipped_python_sources()
    citing = set().union(*(_modules_citing(m) for m in SIBLING_MATRICES))
    for rel in sorted(citing):
        assert fd.labelled(prose(sources[rel])), f"{rel} carries no label at all"  # LD-699: either


# --------------------------------------------------------------------------- #
# The red proofs — every rule of the extractor shown biting on synthetic text   #
# --------------------------------------------------------------------------- #

def test_ld300_a_BARE_document_name_in_a_docstring_is_a_citation():
    """The rule the packaged-doc helpers do not need. Docstring prose writes ``BASE.md register
    row 13``, not a link — four of this issue's pointers are spelled with no link and no
    directory at all, and a links-and-code-spans-only extractor would miss them."""
    text = '"""A module.\n\nBASE.md register row 13 carries the finding.\n"""\n'
    assert _source_offenders("src/larkdocio/base/cells.py", text) == {"BASE.md"}


def test_ld300_a_bare_name_the_wheel_DOES_carry_is_not_reported():
    """The other half: a bare name is answered by whether the wheel carries such a document
    anywhere, because ``BASE.md register row 13`` makes no claim about a directory."""
    text = '"""A module.\n\nThe settle contract lives in schema_settle.py, and GUIDE.md § Base.\n"""\n'
    assert not _source_offenders("src/larkdocio/base/cells.py", text)


def test_ld300_a_citation_that_SPELLS_a_directory_is_held_to_that_directory():
    """The resolution rule, both halves, over a pool of one. A bare name is answered by name; a
    citation that spells a directory is held to it — otherwise
    ``tests/captures/base-study/captures/02-bitable18-tables.json`` would pass on its basename the moment
    anything of that name shipped, and the guard would be a basename lottery."""
    pool, citing = {"src/larkdocio/GUIDE.md"}, "src/larkdocio/base/cells.py"
    assert fd.citation_resolves(citing, "GUIDE.md", pool)
    assert fd.citation_resolves(citing, "../GUIDE.md", pool)
    assert fd.citation_resolves(citing, "src/larkdocio/GUIDE.md", pool)
    assert not fd.citation_resolves(citing, "docs/GUIDE.md", pool)


def test_ld300_the_same_citation_labelled_EARLIER_in_the_module_is_accepted():
    text = (
        '"""A module.\n\nPointers in the dev repo, not in the wheel: the register below.\n\n'
        'BASE.md register row 13 carries the finding.\n"""\n'
    )
    assert not _source_offenders("src/larkdocio/base/cells.py", text)


def test_ld300_a_label_BELOW_the_citation_does_NOT_excuse_it():
    """Ordering is load-bearing on purpose — the note is a promise about the text under it, so a
    pointer added above it is still reported. Without this the label would be a file-wide
    waiver, and AC7 made exactly this choice for packaged docs."""
    text = (
        '"""A module.\n\nBASE.md register row 13 carries the finding.\n\n'
        'Those pointers are in the dev repo.\n"""\n'
    )
    assert _source_offenders("src/larkdocio/base/cells.py", text) == {"BASE.md"}


def test_ld300_a_label_in_a_COMMENT_counts_the_pointers_below_it_live_in_comments_too():
    """A third of the register pointers sit in ``#:`` attribute docs, not docstrings, so both
    halves of the prose have to be able to carry the label and to carry an offender."""
    text = (
        '"""A module."""\n\n#: The register is in the dev repo, not the wheel.\n'
        "#: ``BASE.md`` register row 40 carries the window.\nWINDOW = 1\n"
    )
    assert not _source_offenders("src/larkdocio/base/cells.py", text)
    assert _source_offenders(
        "src/larkdocio/base/cells.py", '"""A module."""\n\n#: ``BASE.md`` row 40.\nW = 1\n'
    ) == {"BASE.md"}


def test_ld300_an_EXECUTABLE_string_literal_is_not_in_scope():
    """Scope is docstrings and comments. An emitted refusal message is guarded by
    ``consumer_text``'s emitted-literal pass, and folding it in here would make one defect
    answer to two tables — recorded as a boundary, and shown."""
    text = '"""A module."""\n\n\ndef refuse():\n    return "documented in SHEETS.md § Limits"\n'
    assert not _source_offenders("src/larkdocio/sheets/ops.py", text)


def test_ld300_a_path_that_exists_NOWHERE_here_is_not_reported():
    """Same scoping as ``cited_repo_paths``: these docstrings legitimately name paths in the
    *consumer's* tree, which resolve for the reader and not here. The question the guard asks is
    only *does the wheel carry what it sends you to?*"""
    text = '"""A module.\n\nDrop it beside your own vendor/pins.toml.\n"""\n'
    assert not _source_offenders("src/larkdocio/base/cells.py", text)


# --------------------------------------------------------------------------- #
# LD-645 — the front door's DRIVE-VERIFICATION claim ↔ the census               #
#                                                                              #
# The defect this arm exists for: the README introduced "the four Drive write   #
# legs", enumerated THREE of them, and said the read-back was "on the access    #
# leg only" — a fourth count, in the wheel's own METADATA body, contradicting   #
# the census it then pointed the reader at. Every guard in this section derives  #
# its expectation from capabilities(); the split itself is authored once, in     #
# front_door.drive_verification_split.                                          #
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def census_surfaces():
    import larkdocio

    return larkdocio.capabilities(full=True)["surfaces"]


def _drive_contract_ids_in(text):
    """Which CLASSIFIED Drive contract ids a document names (the door's side of the diff)."""
    known = fd.DRIVE_VERIFYING_CONTRACTS | fd.DRIVE_NON_VERIFYING_CONTRACTS
    lowered = text.lower()
    return {cid for cid in known if cid in lowered}


def test_ld645_the_split_is_REAL_and_these_guards_are_not_vacuous(census_surfaces):
    legs, verified, unverified = fd.drive_verification_split(census_surfaces)
    assert legs, "no Drive write surfaces at all; every claim below has lost its subject"
    assert verified and unverified, (
        "the verified/unverified split collapsed to one side, so the door's 'stated per leg' "
        "shape may no longer be the right shape — re-read the paragraphs rather than "
        "re-pointing these guards"
    )


def test_ld645_every_front_door_paragraph_about_the_LEG_SET_names_EVERY_leg(
        readme, census_surfaces):
    """A paragraph that speaks of the legs as a set owes the whole set. The file leg was
    missing from both README passages while both counted to four."""
    legs, _verified, _unverified = fd.drive_verification_split(census_surfaces)
    paragraphs = fd.drive_leg_paragraphs(readme)
    assert paragraphs, (
        "no README paragraph mentions the Drive write legs as a set; either the door stopped "
        "describing them or this guard stopped finding them"
    )
    for paragraph in paragraphs:
        missing = fd.drive_legs_missing_from(paragraph, legs)
        assert not missing, (
            f"a front-door paragraph counts the Drive write legs as a set and never "
            f"identifies {missing}: …{paragraph[:180]}…"
        )


def test_ld645_the_front_door_names_the_CONTRACT_of_every_leg_that_verifies(
        readme, census_surfaces):
    """Both directions. A leg that verifies and is not said to reads as one that does not;
    a contract the door credits and no leg declares sends a consumer to a promise
    ``capabilities()`` will not confirm."""
    legs, verified, _unverified = fd.drive_verification_split(census_surfaces)
    owed = set()
    for sid in verified:
        owed |= (fd.DRIVE_VERIFYING_CONTRACTS
                 & set(legs[sid].get("safety_contracts") or ()))
    assert owed, "no verifying contract is declared by any leg; the probe has lost its subject"
    documented = _drive_contract_ids_in(readme)
    undocumented, phantom = fd.two_way_diff(documented, owed)
    assert not undocumented, (
        f"a Drive write leg declares {undocumented} and the front door never names it — the "
        f"reader concludes that leg verifies nothing"
    )
    declared_anywhere = set()
    for spec in legs.values():
        declared_anywhere |= set(spec.get("safety_contracts") or ())
    assert not (set(phantom) - declared_anywhere), (
        f"the front door credits the Drive legs with {sorted(set(phantom) - declared_anywhere)}, "
        f"which no leg declares"
    )


def test_ld645_the_door_does_not_restrict_verification_to_ONE_leg_when_TWO_verify(
        readme, census_surfaces):
    """The exact false clause: *"an independent read-back on the access leg only"*. Bound to
    the subject — an ``only`` that is not qualifying a verification claim is none of this
    guard's business — and gated on the derived count, so the phrasing becomes legitimate
    again the day only one leg verifies."""
    _legs, verified, _unverified = fd.drive_verification_split(census_surfaces)
    if len(verified) <= 1:
        pytest.skip("one leg verifies; restricting the claim to it would be true")
    for paragraph in fd.drive_leg_paragraphs(readme):
        for pattern in _ONLY_ONE_LEG_VERIFIES:
            assert not pattern.search(paragraph), (
                f"{len(verified)} Drive write legs verify in-library, and a front-door "
                f"paragraph restricts that to one: …{paragraph[:200]}…"
            )


#: Verification-claim-scoped ``only`` patterns. Each requires a verification word and the
#: restriction in the SAME clause (no sentence break between them), because "the folder leg
#: is only one call" is true prose and not this guard's business.
_ONLY_ONE_LEG_VERIFIES = (
    re.compile(r"(?:read-back|verif\w*)[^.;]{0,60}?\bon the \w+ leg only\b"),
    re.compile(r"\bonly the \w+ leg\b[^.;]{0,60}?(?:read-back|verif\w*)"),
)


# --- the bite proofs, per direction, separately ----------------------------- #

def test_ld645_dropping_a_leg_from_a_PARAGRAPH_reddens_it(readme, census_surfaces):
    """Direction one, through the real parse: the file leg's own words removed from the
    quickstart paragraph, exactly as the pre-LD-645 README had it."""
    legs, _v, _u = fd.drive_verification_split(census_surfaces)
    stripped = readme.replace("a file uploaded into a\nfolder", "a folder")
    stripped = re.sub(r"and `drive-files-write`\n?declares `bytes-verified-round-trip`[^.]*\.",
                      "", stripped)
    stripped = stripped.replace("a `sha256` + length\nre-download on the file leg,", "")
    offenders = [fd.drive_legs_missing_from(p, legs)
                 for p in fd.drive_leg_paragraphs(stripped)]
    assert any("drive-files-write" in miss for miss in offenders), (
        f"removing the file leg from the door did not redden the guard: {offenders}"
    )


def test_ld645_dropping_a_CONTRACT_id_from_the_door_reddens_it(readme, census_surfaces):
    """Direction one for the contract arm: the census declares it, the door stops saying so."""
    legs, verified, _u = fd.drive_verification_split(census_surfaces)
    owed = set()
    for sid in verified:
        owed |= fd.DRIVE_VERIFYING_CONTRACTS & set(legs[sid].get("safety_contracts") or ())
    victim = "bytes-verified-round-trip"
    assert victim in owed, "the probe is stale; pick a contract a leg really declares"
    documented = _drive_contract_ids_in(readme.replace(victim, "REDACTED"))
    undocumented, _phantom = fd.two_way_diff(documented, owed)
    assert undocumented == [victim]


def test_ld645_a_PHANTOM_contract_in_the_door_reddens_it(census_surfaces):
    """Direction two, over synthetic surfaces: the leg stops declaring, the door still says
    it does. Synthetic because the shipped pair currently agrees — which is the state a
    one-directional guard would preserve forever."""
    legs = {sid: dict(spec) for sid, spec in
            fd.drive_write_legs(census_surfaces).items()}
    legs["drive-files-write"]["safety_contracts"] = ["caller-supplied-destination"]
    owed = set()
    for sid, spec in legs.items():
        if fd.DRIVE_VERIFYING_CONTRACTS & set(spec["safety_contracts"]):
            owed |= fd.DRIVE_VERIFYING_CONTRACTS & set(spec["safety_contracts"])
    documented = {"read-back-is-the-verdict", "bytes-verified-round-trip"}
    _undocumented, phantom = fd.two_way_diff(documented, owed)
    assert phantom == ["bytes-verified-round-trip"]


def test_ld645_the_ONLY_clause_guard_bites_on_the_sentence_that_shipped():
    """The false clause itself, verbatim from the pre-LD-645 README."""
    shipped_false = prose(
        "the four Drive write legs (a named version, an access grant, a file into a folder, a "
        "folder you create) are direct calls, each verified in its own way — an independent "
        "read-back on the access leg only, a pre-write revision read on versions, and nothing "
        "read back on folder create."
    )
    assert any(p.search(shipped_false) for p in _ONLY_ONE_LEG_VERIFIES), (
        "the guard does not bite on the exact clause it was written for"
    )


def test_ld645_the_ONLY_clause_guard_does_NOT_bite_on_true_prose():
    """The must-not-bite, and the reason this pattern is clause-scoped: two true sentences
    that use ``only`` about something other than which leg verifies."""
    for legitimate in (
        "the folder-create leg is exactly one call and reads nothing back — the only organize "
        "verb on offer. an independent member read-back verifies the access leg.",
        "only the access leg is reached by an email address; the file leg is verified by a "
        "sha256 round trip.",
    ):
        assert not any(p.search(prose(legitimate)) for p in _ONLY_ONE_LEG_VERIFIES), (
            f"the guard rejects true prose: {legitimate!r}"
        )


def test_ld645_an_UNCLASSIFIED_drive_contract_refuses_to_be_split(census_surfaces):
    """The split raises rather than defaulting. A new Drive contract read as 'does not
    verify' by silence is the defect this whole issue was."""
    surfaces = {sid: dict(spec) for sid, spec in census_surfaces.items()}
    surfaces["drive-folders-write"] = dict(surfaces["drive-folders-write"])
    surfaces["drive-folders-write"]["safety_contracts"] = ["a-brand-new-promise"]
    with pytest.raises(AssertionError, match="unclassified Drive write contract"):
        fd.drive_verification_split(surfaces)


# --------------------------------------------------------------------------- #
# LD-707 (round 7, X2) — the plan-gate claim is stated PER LEG, the same at both #
# doors. The README and the group --help once said every docx, Sheets and Base  #
# write was plan-gated; the media legs and the whole-object lifecycle calls are #
# direct calls. The set is derived from capabilities(), so a new direct leg      #
# that the README does not name reddens here.                                   #
# --------------------------------------------------------------------------- #

#: Non-``operation`` rows on those surfaces that are NOT direct writes, each with its reason.
_NOT_DIRECT_WRITES = {
    "dry_run": "the plan itself (sheets-write publishes its previewer as a leg)",
    "migrate_field_type": "composes plan-gated schema and record steps (one plan, one consent)",
    "download_attachment_media": "a read",
    "permalink_attachment_media": "a read",
    "get_block": "a read (one live block, read back after a write)",
    "read_document_revision": "a read (the document's revision anchor)",
    "query_tabs": "a read (the workbook's tabs)",
    "query_float_images": "a read (the tab's float images)",
    "read_values": "a read (a range's values)",
    "read_value_range": "a read (a range's whole value range)",
    "read_sheet_geometry": "a read (a tab's row and column counts)",
    "read_frozen_panes": "a read (a tab's frozen panes)",
}
_PLAN_GATED_SURFACES = ("docx-write", "sheets-write", "base-write", "base-schema-write")


def _rows_of_the_plan_gated_surfaces():
    from larkdocio import capabilities
    surfaces = capabilities(full=True)["surfaces"]
    return [row for key in _PLAN_GATED_SURFACES for row in surfaces[key]["operations"]]


def test_x2_the_readme_names_every_direct_write_on_the_plan_gated_surfaces(readme):
    every = _rows_of_the_plan_gated_surfaces()
    rows = [row for row in every
            if row["kind"] != "operation" and row["name"] not in _NOT_DIRECT_WRITES]
    assert len(rows) >= 9, rows  # five lifecycle calls and at least four media legs
    for row in rows:
        entry = row.get("entry_point", "")
        names = {row["name"], ".".join(entry.split(".")[-2:])} - {""}
        assert any(f"`{name}`" in readme for name in names), (
            f"README states the plan gate per leg but omits the direct call {row['name']!r}")
    for name in _NOT_DIRECT_WRITES:
        assert name in {row["name"] for row in every}, f"{name!r} is excused but no longer exists"


def _direct_write_legs():
    """``{kind: {row name}}`` for the direct writes on the plan-gated surfaces, from capabilities().

    ``kind`` is the registry's own: ``leg`` (the media legs) and ``lifecycle`` (the
    whole-object calls). A surface whose create half is a registered plan-gated ``operation``
    (Base: ``create_app``) contributes only its delete, because only the delete is a lifecycle row.
    """
    legs = {}
    for row in _rows_of_the_plan_gated_surfaces():
        if row["kind"] != "operation" and row["name"] not in _NOT_DIRECT_WRITES:
            legs.setdefault(row["kind"], set()).add(row["name"])
    return legs


def _write_names_stated_in(passage):
    """The identifier-shaped write rows (and entry-point tails) a door's passage names."""
    stated = set()
    for row in _rows_of_the_plan_gated_surfaces():
        if row["name"] in _NOT_DIRECT_WRITES:
            continue
        entry = row.get("entry_point", "")
        spellings = {row["name"], ".".join(entry.split(".")[-2:])} - {""}
        if any("_" in s or "." in s for s in spellings) and any(
                re.search(rf"(?<![\w.]){re.escape(s)}(?![\w])", passage) for s in spellings):
            stated.add(row["name"])
    return stated


def _plan_gate_passage(text, anchor):
    """The one blank-line paragraph of ``text`` that carries ``anchor``, identifiers intact.

    ``prose()`` folds case and strips ``_``, so it locates the paragraph but the returned text
    is only whitespace-collapsed and de-backticked: the names have to survive to be matched.
    """
    hits = [para for para in re.split(r"\n\s*\n", text) if prose(anchor) in prose(para)]
    assert len(hits) == 1, (anchor, len(hits))
    return " ".join(hits[0].split()).replace("`", "")


def test_x2_both_doors_state_the_same_derived_per_leg_set(readme):
    """README and the group --help name exactly the direct legs capabilities() registers.

    Derived, not phrased: the set each door states is read off the door and compared to the
    registry's ``leg`` + ``lifecycle`` rows, so naming a plan-gated op (``create_app``) as
    direct, or dropping a direct leg, reddens at either door.
    """
    legs = _direct_write_legs()
    assert set(legs) == {"leg", "lifecycle"}, legs
    assert {"create_app", "copy_app"}.isdisjoint(legs["lifecycle"])
    derived = legs["leg"] | legs["lifecycle"]
    group_page = consumer_text.cli_help_pages()["larkdocio --help"]
    doors = {
        "README": _plan_gate_passage(readme, "Not every write on those three surfaces"),
        "--help": _plan_gate_passage(group_page, "a direct call, with no plan"),
    }
    for where, passage in doors.items():
        assert _write_names_stated_in(passage) == derived, (
            where, sorted(_write_names_stated_in(passage) ^ derived))


def test_ld712_both_doors_name_the_other_public_cell_writes_beside_put_values(readme):
    """LD-711 QA LOW 2 / LD-712 AC3: ``put_values`` is the one DOCUMENTED direct cell write,
    not the only one — ``SheetsWriteClient``'s other public value writes are direct calls too.
    Both doors scope the claim and name them, together; the bare "the one direct cell write"
    is refused at either door."""
    from larkdocio.sheets.write_client import SheetsWriteClient
    others = ("append_values", "prepend_values", "batch_update_values")
    assert all(callable(getattr(SheetsWriteClient, name, None)) for name in others)
    group_page = consumer_text.cli_help_pages()["larkdocio --help"]
    doors = {
        "README": _plan_gate_passage(readme, "Not every write on those three surfaces"),
        "--help": _plan_gate_passage(group_page, "a direct call, with no plan"),
    }
    for where, passage in doors.items():
        assert "the one direct cell write" not in passage, where
        assert "documented direct cell write" in passage, where
        missing = [n for n in others if not re.search(rf"(?<![\w.]){n}(?!\w)", passage)]
        assert not missing, (where, missing)


def test_x2_neither_door_carries_the_blanket_plan_gate_claim(readme):
    pages = " ".join(consumer_text.cli_help_pages().values())
    for where, text in (("README", prose(readme)), ("--help", prose(pages))):
        assert prose("The docx, Sheets and Base writes are plan-gated") not in text, where
        assert prose("for docx, Sheets and Base a plan you approve first") not in text, where
        # Round 7's QA: a generic "create and delete" leg is false for Base (create_app is a
        # plan-gated schema op); each door names the lifecycle calls instead.
        assert prose("whole-object create and delete calls") not in text, where
