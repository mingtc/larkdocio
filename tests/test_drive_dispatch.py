"""LD-325 — the child-``type`` → reader dispatcher (the Drive spec § F1 § S3).

The dispatcher is **pure and offline**: it *selects* the outcome for one ``FolderChild``, it
does not fetch, it does not import a reader, and it does not render (that is LD-326's per-child
degradation contract). Every test here runs with **no network** and no client.

The two honesty debts the issue exists to pay are tested as first-class facts, not prose:

* the ``sheet``→``sheets`` / ``bitable``→``base`` vocabulary **seam** is translated in exactly
  one place and pinned against both vocabularies read from real code (AC2), and
* the ``shortcut`` branch is built against the SDK's model and **never observed** — its chain
  resolves, and a loop is disclosed rather than followed (AC3).
"""
import ast
from collections import Counter

import drive_fixtures as fx
from guard_kit import REPO_ROOT, section
import larkdocio.drive.dispatch as D
from larkdocio.common.url import URL_TYPE_SURFACES
from larkdocio.drive.dispatch import DISPATCH
from larkdocio.drive.models import FolderChild

DRIVE_MD = REPO_ROOT / "DRIVE.md"
DRIVE_PKG = REPO_ROOT / "src" / "larkdocio" / "drive"

#: Lark's own six child types, from the listing response and the SDK's ``File`` model.
_CHILD_TYPES = {"docx", "sheet", "bitable", "folder", "shortcut", "file"}


def _dispatch_rows():
    """``DRIVE.md``'s dispatch table as ``{lark_word: {status, evidence, ...}}``.

    Reuses the shipped matrix guard's own parser so this test cannot drift from the guard's
    idea of what a row is.
    """
    import test_drive_md_matrix as matrix

    text = DRIVE_MD.read_text(encoding="utf-8")
    rows = {}
    for row in matrix.dispatch_rows(text):
        lark_word = row["Child `type` (Lark's word)"].strip("` ")
        rows[lark_word] = {
            "status": matrix._status_of(row),
            "evidence": next(v for k, v in row.items() if "evidence" in k.lower()),
            **row,
        }
    return rows


# --------------------------------------------------------------------------- #
# AC1 — the dispatch table, all six types, one branch each; the dry-run.        #
# --------------------------------------------------------------------------- #

def test_the_dispatch_table_has_one_branch_per_lark_child_type():
    assert set(DISPATCH) == _CHILD_TYPES


def test_docx_dispatches_to_the_docx_reader_FED_THE_LISTINGS_OWN_URL():
    child = FolderChild(token="d1", type="docx",
                        url="https://x.larksuite.com/docx/d1")
    out = D.dispatch(child)
    assert out.kind == D.READ and out.surface == "docx"
    assert out.url == "https://x.larksuite.com/docx/d1", "the listing's url is handed over"


def test_sheet_dispatches_to_the_SHEETS_surface():
    out = D.dispatch(FolderChild(token="s1", type="sheet"))
    assert out.kind == D.READ and out.surface == "sheets"


def test_bitable_dispatches_to_the_BASE_surface():
    out = D.dispatch(FolderChild(token="b1", type="bitable"))
    assert out.kind == D.READ and out.surface == "base"


def test_folder_dispatches_to_RECURSE():
    out = D.dispatch(FolderChild(token="f1", type="folder"))
    assert out.kind == D.RECURSE


def test_the_dry_run_reproduces_27_readable_2_no_reader_6_structure_OFFLINE():
    """AC1's evidence: the maintainer-tree shape from capture 15, dispatched offline."""
    kinds = Counter(D.dispatch(child).kind for child in fx.dispatch_dry_run_children())
    assert kinds[D.READ] == 27
    assert kinds[D.NO_READER] == 2
    assert kinds[D.RECURSE] == 6


# --------------------------------------------------------------------------- #
# AC2 — the vocabulary seam: one place, pinned to both vocabularies.            #
# --------------------------------------------------------------------------- #

def test_the_seam_maps_larks_words_onto_larkdocio_surface_names_from_REAL_CODE():
    assert D.SEAM == {"sheet": "sheets", "bitable": "base"}
    for lark_word, our_word in D.SEAM.items():
        assert our_word in URL_TYPE_SURFACES, (
            f"the seam's larkdocio side {our_word!r} is not a surface common/url.py knows")


def test_the_seam_is_translated_in_EXACTLY_ONE_PLACE():
    """The dispatch branches read their surface off ``SEAM``; the literal translation appears
    once in the module. A second copy is how the two halves drift apart."""
    assert DISPATCH["sheet"].surface == D.SEAM["sheet"]
    assert DISPATCH["bitable"].surface == D.SEAM["bitable"]
    source = (DRIVE_PKG / "dispatch.py").read_text(encoding="utf-8")
    assert source.count('"bitable": "base"') == 1


def test_the_seam_words_are_grounded_in_real_data_or_LABELLED_sdk_modeled():
    observed = fx.observed_child_types()
    assert "bitable" in observed, "bitable was seen in round 1's root listing (capture 02)"
    assert "sheet" not in observed, (
        "no capture ever contained a spreadsheet — the sheet leg is SDK-modeled, which is "
        "exactly why the shipped text must label it asserted-not-demonstrated")


def test_DRIVE_MD_seam_rows_are_SHIPPED_but_labelled_asserted_not_demonstrated():
    rows = _dispatch_rows()
    for lark_word in ("sheet", "bitable"):
        row = rows[lark_word]
        assert row["status"] == "shipped", (lark_word, row)
        cell = row["evidence"].lower()
        assert "asserted" in cell and "not demonstrated" in cell, (lark_word, cell)


def test_no_shipped_text_describes_the_sheet_or_base_leg_as_PROVEN():
    region = section(DRIVE_MD.read_text(encoding="utf-8"),
                     "## The child-`type` → reader dispatch table")
    assert "asserted-not-demonstrated" in region.lower().replace("**", "")
    rows = _dispatch_rows()
    for lark_word in ("sheet", "bitable"):
        cell = " ".join(rows[lark_word].values()).lower()
        assert "proven" not in cell, (lark_word, "a seam leg is claimed proven")


# --------------------------------------------------------------------------- #
# AC3 — shortcut resolution, its cycle guard, its unproven status.              #
# --------------------------------------------------------------------------- #

def test_a_shortcut_resolves_to_its_target_and_REDISPATCHES_on_the_target_type():
    shortcut = FolderChild(
        token="s1", type="shortcut", name="a link",
        shortcut_info={"target_type": "docx", "target_token": "d1"})
    out = D.dispatch(shortcut)
    assert out.kind == D.RESOLVE
    assert out.target.kind == D.READ and out.target.surface == "docx"


def test_a_shortcut_CHAIN_resolves_shortcut_to_shortcut_to_docx():
    docx = FolderChild(token="d1", type="docx", url="https://x/docx/d1")
    inner = FolderChild(token="s2", type="shortcut",
                        shortcut_info={"target_type": "docx", "target_token": "d1"})
    outer = FolderChild(token="s1", type="shortcut",
                        shortcut_info={"target_type": "shortcut", "target_token": "s2"})
    resolve = {"s2": inner, "d1": docx}.get
    out = D.dispatch(outer, resolve=resolve)
    final = out
    while final.kind == D.RESOLVE:
        final = final.target
    assert final.kind == D.READ and final.surface == "docx"


def test_a_SELF_REFERENTIAL_shortcut_is_DISCLOSED_not_followed():
    loop = FolderChild(token="s1", type="shortcut", name="loop",
                       shortcut_info={"target_type": "shortcut", "target_token": "s1"})
    out = D.dispatch(loop)
    assert out.kind == D.CYCLE
    assert "s1" in out.reason


def test_a_shortcut_into_the_VISITED_SET_is_disclosed_never_looped():
    shortcut = FolderChild(token="s1", type="shortcut",
                           shortcut_info={"target_type": "docx", "target_token": "ancestor"})
    out = D.dispatch(shortcut, seen={"ancestor"})
    assert out.kind == D.CYCLE


def test_DRIVE_MD_shortcut_row_is_UNCAPTURED_for_the_live_half():
    row = _dispatch_rows()["shortcut"]
    assert row["status"] == "uncaptured", row


# --------------------------------------------------------------------------- #
# AC4 — type:"file": list-and-disclose, never a silent drop, never a fetch.     #
# --------------------------------------------------------------------------- #

def test_a_file_child_is_DISCLOSED_never_read():
    out = D.dispatch(FolderChild(token="f1", type="file", name="example-spec.yaml"))
    assert out.kind == D.NO_READER
    assert out.reader is None and out.surface is None
    assert "no reader" in out.reason.lower()
    assert "download" in out.reason.lower(), "the bytes verb is named at the point of the skip"


def test_the_skip_reason_NAMES_THE_VERB_THAT_FETCHES_THE_BYTES(capsys):
    """**LD-474 — the transformed guard.** This assertion used to read *"the R4 pointer is named
    as not-shipped"*, and the sentence it pinned said the download leg was not shipped. It is
    shipped (``larkdocio.drive.files_write.DriveFilesWriteClient.download``, hash-verified by
    ``tests/test_drive_files_write.py`` and by the live ring), and a consumer who believed the
    skip reason concluded that Drive file bytes were unreachable — the round-4 cost.

    The *reason* R4 scoped the walk out of fetching bytes is untouched and still asserted
    (the test above: no reader, nothing fetched). What is asserted here is the replacement of
    the false conclusion: the reason names the verb, at the point of the skip, which is where a
    consumer reads it.
    """
    out = D.dispatch(FolderChild(token="f1", type="file", name="example-spec.yaml"))
    assert "DriveFilesWriteClient.download" in out.reason, out.reason
    assert "FETCHABLE" in out.reason, (
        "the reason must say the bytes ARE obtainable, not merely mention a verb")
    for absence in ("is not shipped", "not shipped", "cannot be fetched", "unreachable"):
        assert absence not in out.reason, (
            f"the skip reason claims {absence!r} about a leg that ships: {out.reason!r}")


def test_the_TWO_REAL_FILE_CHILDREN_appear_by_name_with_a_no_reader_outcome():
    files = [D.dispatch(child) for child in fx.dispatch_dry_run_children()
             if child.type == "file"]
    assert {out.name for out in files} == {"example-spec.yaml", "example-reference.html"}
    assert all(out.kind == D.NO_READER for out in files)


def test_NO_DRIVE_CODE_PATH_calls_the_file_download_endpoint():
    """AC4: R1 lists and discloses a ``file`` child, it never fetches its bytes. The dispatcher
    **names** the download verb (required, and proven by the reason above — LD-474 replaced the
    old *"not shipped"* wording with the verb, and the walk still does not call it); the modules
    that actually **issue requests** must not reach it, and the dispatcher issues none at all
    (see the no-client test below)."""
    for name in ("client.py", "ops.py", "walk.py"):
        source = (DRIVE_PKG / name).read_text(encoding="utf-8")
        assert "/download" not in source, (
            f"{name} references a download endpoint — forbidden in R1 (AC4)")


# --------------------------------------------------------------------------- #
# AC5 — an unknown type is disclosed with a traceable marker, byte-pinned.       #
# --------------------------------------------------------------------------- #

def test_an_UNKNOWN_type_is_disclosed_with_a_marker_naming_it():
    out = D.dispatch(FolderChild(token="x1", type="mindnote", name="a mind map"))
    assert out.kind == D.UNKNOWN
    assert out.reason == "[Unsupported Drive child type: mindnote]"


def test_the_unknown_marker_BYTE_FORM_is_pinned():
    assert D.UNKNOWN_TYPE_MARKER == "[Unsupported Drive child type: {child_type}]"


# --------------------------------------------------------------------------- #
# AC7 — the dispatcher SELECTS; it does not orchestrate.                         #
# --------------------------------------------------------------------------- #

def test_the_dispatcher_takes_NO_CLIENT_and_reaches_no_transport():
    """Every branch is exercised with nothing on hand to make a call with — the strongest
    offline proof there is: there is no client in scope to fetch anything."""
    for child_type in _CHILD_TYPES:
        child = FolderChild(token="t", type=child_type,
                            shortcut_info={"target_type": "docx", "target_token": "d"}
                            if child_type == "shortcut" else None)
        assert D.dispatch(child) is not None


def test_the_dispatcher_module_IMPORTS_NO_READER():
    """The readers' import cost is real; AC7 says the dispatcher **names** them, it does not
    **import** them. Proven against the module's own import statements (the umbrella
    ``larkdocio`` package is eager for unrelated reasons, so ``sys.modules`` is the wrong lens —
    the honest question is what *this module* imports)."""
    tree = ast.parse((DRIVE_PKG / "dispatch.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    readers = {name for name in imported
               if name.startswith(("larkdocio.read", "larkdocio.sheets", "larkdocio.base"))}
    assert not readers, f"the dispatcher imports readers it should only name: {sorted(readers)}"


# --------------------------------------------------------------------------- #
# LD-474 — the corpus grep: a leg that SHIPS may not be called absent anywhere.  #
# --------------------------------------------------------------------------- #

#: Every spelling of the false conclusion, as it was actually shipped and as a future edit
#: would most plausibly re-write it. The **reason** R4 scoped the walk out is not in this list
#: and is not forbidden — only the claim that the download leg does not exist.
_BYTES_LEG_ABSENCE_SPELLINGS = (
    "is not shipped (R4)",
    "bytes leg is not shipped",
    "the bytes leg does not ship",
    "no code path from a Drive file token to bytes",
)


def _corpus():
    """``{label: text}`` — every shipped consumer surface, plus the two dev-repo matrices."""
    import consumer_text

    corpus = dict(consumer_text.shipped_docs())
    corpus["DRIVE.md"] = DRIVE_MD.read_text(encoding="utf-8")
    corpus["src/larkdocio/drive/dispatch.py"] = (
        DRIVE_PKG / "dispatch.py").read_text(encoding="utf-8")
    return corpus


def test_NO_SHIPPED_TEXT_calls_the_bytes_leg_UNSHIPPED():
    """**LD-474's grep guard.** ``DriveFilesWriteClient.download`` ships and is hash-verified;
    a shipped sentence saying otherwise is what made one round-4 consumer stop looking and
    return partial results on five of seven items while another already held the bytes.

    This does not forbid saying *the walk does not fetch them* — that is true and is said in
    several places. It forbids saying the **leg** is absent.
    """
    offenders = []
    for label, text in _corpus().items():
        lowered = text.lower()
        for spelling in _BYTES_LEG_ABSENCE_SPELLINGS:
            if spelling.lower() in lowered:
                offenders.append(f"{label}: {spelling!r}")
    assert not offenders, (
        "a shipped surface claims the Drive file-bytes leg is not shipped — it is "
        f"(larkdocio.drive.files_write.DriveFilesWriteClient.download): {offenders}")
