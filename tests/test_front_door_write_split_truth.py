"""THE WRITE-SURFACE SPLIT, as the front door states it (LD-440).

Three claims in the door described a library that stopped existing during the
LD-403..LD-434 arc, and each is the same shape: **a closed enumeration or a universal
promise, written when it was true, never re-derived**.

1. the WRITE credential pair "used only by the document writer and Sheets writes" — seven
   surfaces answer ``app: 'write'`` today;
2. "Writes are plan-gated" as a universal — three of those seven carry **no** plan gate
   (``drive-versions-write`` / ``drive-files-write`` carry an empty ``safety_contracts``;
   ``drive-access-write`` carries only ``read-back-is-the-verdict``, a post-hoc read-back);
3. "neither has a subcommand or a flag" about the Base — ``--deep-read-bases`` ships on two
   commands.

The cure the guards below pin is not the corrected sentence (a rewrite may word it however
it likes) but the **shape**: the enumeration is a class, and the universality is qualified by
the surfaces that actually carry the gate. Regression-tier by the § A.1 question — the
product is not wrong if the prose reads differently, only if it re-freezes a closed list.
"""
import re

import pytest

import consumer_text
import front_door as fd
from consumer_text import cli_group


@pytest.fixture(scope="module")
def readme():
    return fd.readme_text()


@pytest.fixture(scope="module")
def surfaces():
    import larkdocio

    return larkdocio.capabilities(full=True)["surfaces"]


def _write_surfaces(surfaces):
    return sorted(
        sid
        for sid, spec in surfaces.items()
        if spec.get("credentials", {}).get("app") == "write"
    )


def _ungated_write_surfaces(surfaces):
    """Write surfaces with no pre-approval plan gate — the half the door promised away."""
    return sorted(
        sid
        for sid in _write_surfaces(surfaces)
        if "plan-gated" not in surfaces[sid].get("safety_contracts", [])
    )


# --------------------------------------------------------------------------- #
# AC1 — the credential split is a CLASS, never a closed pair                    #
# --------------------------------------------------------------------------- #

_CLOSED_PAIR = re.compile(
    r"(only by the write surfaces \(the\s+document writer and Sheets writes\))"
    r"|(the writer or a Sheets write)",
    re.DOTALL,
)


def test_ac1_the_readme_states_no_CLOSED_two_surface_write_credential_list(readme):
    assert not _CLOSED_PAIR.search(readme), (
        "the WRITE credential prose still names a closed two-surface list; it goes stale "
        "the next time a write surface ships, which is exactly how it got here"
    )


def test_ac1_the_write_credential_prose_points_at_a_DERIVED_list(readme):
    """The class, not the members: the paragraph sends the reader to something generated."""
    section = readme.split("## Credentials")[1].split("\n## ")[0]
    assert "LARK_WRITE_APP_ID" in section
    assert any(
        pointer in section
        for pointer in ("capabilities()", "PERMISSIONS.md", "larkdocio.permissions")
    ), "the write-credential paragraph names no derived source for which surfaces need it"


def test_ac1_the_requirements_bullet_does_not_re_freeze_todays_write_set(readme, surfaces):
    """Every write surface family is either named or covered by the class statement — proven
    by asking the registry, so a new write surface widens the requirement on its own."""
    consumer_half, _dev = fd.split_at_development_heading(readme)
    lowered = consumer_half.lower()
    for sid in _write_surfaces(surfaces):
        family = sid.split("-")[0]
        assert family in lowered, (
            f"{sid} needs the WRITE credential pair and its family {family!r} is never "
            f"mentioned in the half of the README a wheel-only consumer reads"
        )


# --------------------------------------------------------------------------- #
# AC3 — the plan-gating claim states the SPLIT                                  #
# --------------------------------------------------------------------------- #

def test_ac3_the_measured_split_is_real_and_this_guard_is_not_vacuous(surfaces):
    ungated = _ungated_write_surfaces(surfaces)
    assert ungated, (
        "every write surface is plan-gated, so the universal claim would be true — "
        "re-read this guard before deleting it"
    )
    assert surfaces["drive-access-write"]["safety_contracts"] == [
        "read-back-is-the-verdict"
    ]


def test_ac3_no_front_door_text_promises_plan_gating_UNIVERSALLY(readme):
    """Every sentence that promises the gate names who carries it. The check is the
    neighbourhood, not the wording: a plan-gating promise must sit within its own paragraph
    of the qualifier."""
    for paragraph in readme.split("\n\n"):
        low = paragraph.lower()
        if "plan-gated" not in low and "plan you approve" not in low:
            continue
        if "drive" not in low and "read-back" not in low:
            continue  # a paragraph about one gated surface is not a universal claim
        assert "read-back" in low or "no plan gate" in low or "direct" in low, (
            "a paragraph mentioning both the plan gate and drive must say which half is "
            f"which: {paragraph[:200]!r}"
        )


def test_ac3_the_quickstart_write_promise_is_scoped_to_the_gated_surfaces(readme):
    assert "Writes are **plan-gated**: `dry_run` returns" not in readme
    assert "Writes are plan-gated: `dry_run` returns" not in readme
    quickstart = readme.split("And one write")[1][:1200].lower()
    assert "docx" in quickstart or "writer" in quickstart
    assert "drive" in quickstart, (
        "the write promise never tells the reader the Drive write legs are not gated this way"
    )


def test_ac3_the_cli_read_only_paragraph_keeps_its_original_REASON(readme):
    """Supersession, one more turn of the same screw (LD-492) — and the REASON is what this
    test was always about, so the reason is what it now asserts.

    This story superseded the *universality* of the read-only claim (the LIBRARY writes, the
    command line does not) and required the README to keep saying the command line is
    read-only. LD-492 superseded the remaining half: one command writes now. Deleting this
    test would lose the thing it exists to protect, which is not the sentence but the reason
    under it — **a download must never be able to mutate the document it is reading** — so the
    assertion moves onto that: the README must still say which commands read, must say the
    reading ones cannot write, and must not carry the retired blanket sentence beside its
    replacement.
    """
    assert "The command line is read-only." not in readme, (
        "the retired blanket claim is still in the README beside its replacement; a false "
        "sentence next to a true one is worse than either"
    )
    assert "Exactly one command here writes to Lark: `roundtrip push --apply`." in readme, (
        "the README does not name the one writing command"
    )
    assert "a download must never be able to mutate the document it is reading" in readme, (
        "the README dropped the REASON the read-only claim existed — supersession preserves "
        "the reason and replaces only the conclusion"
    )


# --------------------------------------------------------------------------- #
# AC4 — the CLI group help stops denying a flag that ships                      #
# --------------------------------------------------------------------------- #

def _group_help():
    return cli_group().get_help(
        __import__("click").Context(cli_group(), info_name="larkdocio", terminal_width=80)
    )


def test_ac4_the_group_help_does_not_deny_a_flag_that_ships():
    help_text = " ".join(_group_help().split())
    assert "neither has a subcommand or a flag" not in help_text, (
        "the group help denies the flag `--deep-read-bases`, which ships on two commands"
    )


def test_ac4_the_group_help_names_the_base_flag_that_exists(surfaces):
    import larkdocio

    spelling = larkdocio.capabilities(full=True)["flags"]["deep_read_bases"]["cli"]
    assert spelling in " ".join(_group_help().split())


def test_ac4_the_group_help_prose_names_the_drive_writes(surfaces):
    help_text = " ".join(_group_help().split()).lower()
    for sid in _write_surfaces(surfaces):
        if not sid.startswith("drive-"):
            continue
        word = sid.split("-")[1]  # versions / access / files
        assert word in help_text, (
            f"the group help's capability paragraph never mentions {sid} ({word!r}), while "
            f"its own surface-id list below it does — the two disagree"
        )


def test_ac4_the_cli_gained_no_command_and_no_write_flag():
    """AC12, as a test: this issue moves text only — and LD-492 is the one issue that did not.

    Re-cut, not deleted: the five reading commands are still exactly the five and none of them
    gained a write flag (which is what AC12 was fencing), and the sixth is named against the
    module that defines it so a rename cannot quietly widen this list.
    """
    from larkdocio.roundtrip import COMMAND_NAME as THE_WRITING_VERB

    assert sorted(cli_group().commands) == sorted([
        "config",
        "download",
        "folder",
        "guide",
        "mermaid",
        THE_WRITING_VERB,
    ])
    for reader in ("config", "download", "folder", "guide", "mermaid"):
        options = {opt for param in cli_group().commands[reader].params
                   for opt in param.opts}
        assert not any("apply" in opt or "write" in opt for opt in options), (
            f"{reader} grew a write-shaped flag: {sorted(options)}"
        )


# --------------------------------------------------------------------------- #
# AC5 — the drive package docstring is RE-SCOPED, not deleted                   #
# --------------------------------------------------------------------------- #

def _drive_doc():
    import larkdocio.drive

    return " ".join((larkdocio.drive.__doc__ or "").split())


def test_ac5_the_drive_package_does_not_claim_to_be_read_only():
    doc = _drive_doc()
    assert "It is **read-only**: nothing is moved, uploaded or written." not in doc, (
        "the package docstring claims read-only while the same module re-exports two write "
        "clients"
    )


def test_ac5_the_read_only_claim_SURVIVES_where_it_is_true():
    """Re-scoped, not deleted (DRIVE.md § the surface now writes one thing)."""
    doc = _drive_doc().lower()
    assert "read-only" in doc
    assert re.search(r"(folder (walk|read)|enumeration)[^.]{0,120}read-only", doc) or (
        re.search(r"read-only[^.]{0,120}(folder (walk|read)|enumeration)", doc)
    ), f"the surviving read-only claim is not scoped to the walk: {doc[:400]!r}"


def test_ac5_the_docstring_names_every_drive_surface_capabilities_reports(surfaces):
    doc = _drive_doc()
    missing = [
        sid for sid in surfaces if sid.startswith("drive-") and sid not in doc
    ]
    assert not missing, f"the drive package docstring never names {missing}"


def test_ac5_the_files_write_leg_is_reachable_and_the_docstring_says_how():
    from larkdocio.drive.files_write import put_file_in_folder  # noqa: F401

    assert "larkdocio.drive.files_write" in _drive_doc()


# --------------------------------------------------------------------------- #
# AC6 — TOOLS.md                                                                #
# --------------------------------------------------------------------------- #

def _tools():
    return (fd.REPO_ROOT / "TOOLS.md").read_text(encoding="utf-8")


def test_ac6_tools_md_does_not_enumerate_a_hard_surface_count():
    text = _tools()
    assert "library with five surfaces" not in text
    assert not re.search(r"library with (three|four|five|six|seven|eight) surfaces", text)


def test_ac6_tools_md_scopes_its_read_only_claim_to_the_folder_command():
    drive_bullet = [
        block
        for block in _tools().split("\n\n")
        if "Drive folder read" in block or "drive folder read" in block
    ]
    assert drive_bullet, "TOOLS.md no longer describes the Drive folder read at all"
    block = " ".join(drive_bullet[0].split())
    assert "Read-only. This is what the `folder` command drives" not in block
    assert "read-only" in block.lower()
    assert "folder`" in block or "`folder`" in block


def test_ac6_tools_md_points_at_capabilities_for_what_the_cli_does_not_reach():
    assert "capabilities()" in _tools()


# --------------------------------------------------------------------------- #
# AC7 — the reference-doc index                                                 #
# --------------------------------------------------------------------------- #

def test_ac7_the_readme_states_no_hard_count_of_capability_matrices(readme):
    assert not re.search(r"(two|three|four|five) capability matrices", readme)


@pytest.mark.parametrize("doc", ["PERMISSIONS.md", "BASE.md", "DRIVE.md", "SHEETS.md",
                                 "BLOCKS.md", "TOOLS.md"])
def test_ac7_every_surface_document_is_in_the_reference_index(readme, doc):
    index = readme.split("### Reference docs")[1].split("\n### ")[0]
    assert f"`{doc}`" in index, f"{doc} is not listed among the reference docs"
    assert (fd.REPO_ROOT / doc).exists()


def test_ac7_the_permissions_entry_says_it_is_GENERATED(readme):
    index = readme.split("### Reference docs")[1].split("\n### ")[0]
    entry = [line for line in index.splitlines() if "`PERMISSIONS.md`" in line]
    assert entry and "generated" in " ".join(index.split()).lower()


# --------------------------------------------------------------------------- #
# AC2 — the census names the drive file write and contacts                      #
# --------------------------------------------------------------------------- #

def test_ac2_the_folder_upload_is_named_in_the_readme(readme):
    assert "put_file_in_folder" in readme
    assert "drive-files-write" in readme


def test_ac2_contacts_is_named_in_the_CONSUMER_half(readme):
    consumer_half, _dev = fd.split_at_development_heading(readme)
    assert "contacts" in consumer_half.lower()
    assert consumer_half.lower().count("contacts") >= 2, (
        "contacts is mentioned once, in troubleshooting — a reader never learns the surface "
        "exists"
    )


def test_ac2_the_readme_is_still_the_text_that_ships(readme):
    """Cheap sanity that the corpus this all rides on is unchanged in kind."""
    assert readme == consumer_text.shipped_docs()["README.md (the wheel METADATA body)"]
