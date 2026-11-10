"""The validator recognises a DRIVE FOLDER url and names its type (LD-323).

**One line of vocabulary, measured.** The Drive spike walked a real tenant tree and found that
**27 of its 29 documents (93%) are already readable by shipped larkdocio code, and not one of
them is reachable** — because the enumeration that would produce their urls cannot be entered
from a link: ``…/drive/folder/<token>`` was refused before anything could start
(``dev/drive-spike/2026-08-07-drive-surface-map.md`` § VII.2, *"the single highest-leverage line
in this whole document"*).

**What this module pins, and what it deliberately does not.** It pins the parse, the
discriminator, the widening-only property, and the two refusals a consumer actually meets. It
does **not** pin any Drive capability: nothing enumerates, dispatches or reads a folder yet, and
the two refusal messages are asserted to keep saying so — a message that promised a folder read
before one shipped would be the defect. The type/shape-table split is the module's own second
subject, because a Drive folder is the first accepted path with **two** segments.
"""
import re

import pytest

from larkdocio.common import URL_PATH_SHAPES, URL_TYPE_SURFACES, validate_download_url


# --------------------------------------------------------------------------- #
# AC1 — the parse, over every axis the older shapes are tested on.             #
# --------------------------------------------------------------------------- #

#: ``(url, allow_host, expected (domain, type, token))``. The maintainer's real folder url is the first
#: row, verbatim from the spike's § VII (the maintainer disclosed the token); the rest walk the same axes
#: the five older shapes are held to — the two API domains, a multi-subdomain tenant host, a bare
#: host, the opt-in extra host, a query string and a trailing slash.
_ACCEPTED_FOLDERS = [
    ("https://your-domain.larksuite.com/drive/folder/FolderRootExample0000000001", "",
     ("larksuite.com", "drive", "FolderRootExample0000000001")),
    ("https://x.feishu.cn/drive/folder/FLD1", "", ("feishu.cn", "drive", "FLD1")),
    ("https://a.b.c.larksuite.com/drive/folder/FLD2", "",
     ("larksuite.com", "drive", "FLD2")),
    ("https://feishu.cn/drive/folder/FLD3", "", ("feishu.cn", "drive", "FLD3")),
    ("https://tenant.example.com/drive/folder/FLD4", "example.com",
     ("example.com", "drive", "FLD4")),
    ("https://x.feishu.cn/drive/folder/FLD5?from=space", "", ("feishu.cn", "drive", "FLD5")),
    ("https://x.feishu.cn/drive/folder/FLD6/", "", ("feishu.cn", "drive", "FLD6")),
]


@pytest.mark.parametrize("url,allow_host,expected", _ACCEPTED_FOLDERS)
@pytest.mark.conformance
def test_ac1_a_folder_url_parses_into_the_same_three_tuple(url, allow_host, expected):
    """AC1: same function, same 3-tuple, one more value in its middle slot — and the first
    value is still the **API** domain, not the tenant host the url carries."""
    assert validate_download_url(url, allow_host) == expected


@pytest.mark.conformance
def test_ac1_the_domain_is_the_api_domain_not_the_tenant_host():
    """AC1: the established API-domain-not-tenant-host semantics, on the new shape. The maintainer's
    real url spells ``your-domain.larksuite.com``; a caller needs ``larksuite.com``."""
    domain, url_type, token = validate_download_url(_ACCEPTED_FOLDERS[0][0])
    assert (domain, url_type) == ("larksuite.com", "drive")
    assert domain != _ACCEPTED_FOLDERS[0][0].split("/")[2] == "your-domain.larksuite.com"
    assert token == "FolderRootExample0000000001"


@pytest.mark.conformance
def test_ac1_the_type_keys_the_surface_table_so_a_caller_ROUTES_instead_of_REPARSING():
    """AC1: the returned type is a usable discriminator, not a label — the whole reason the
    middle slot exists. ``drive`` keys the surface table like every other type."""
    _domain, url_type, _token = validate_download_url("https://x.feishu.cn/drive/folder/FLD1")
    assert URL_TYPE_SURFACES[url_type] == "drive"
    assert URL_PATH_SHAPES["drive/folder"] == url_type


@pytest.mark.conformance
def test_ac1_the_two_tables_are_the_SAME_SET_seen_from_two_sides():
    """AC1: the shape table and the type table must agree — every accepted path shape reports a
    type the surface table knows, and no known type is unreachable from any shape. This is the
    invariant that used to be free (the tables were one list) and is now load-bearing."""
    assert set(URL_PATH_SHAPES.values()) == set(URL_TYPE_SURFACES)
    assert URL_PATH_SHAPES["drive/folder"] == "drive"
    # and the shape vocabulary is where the two-segment shape lives — the type table must NOT
    # carry it, or a caller routing on the type would branch on a path.
    assert "drive/folder" not in URL_TYPE_SURFACES


# --------------------------------------------------------------------------- #
# AC2 — a WIDENING ONLY, proven rather than assumed.                           #
# --------------------------------------------------------------------------- #

#: The five shapes accepted before this change, with the tuple each returned before it, quoted
#: here as literals so the comparison is against **recorded** behaviour and not against the
#: current code re-reading itself.
_PRE_EXISTING = [
    ("https://your-domain.larksuite.com/docx/ABC123", "", ("larksuite.com", "docx", "ABC123")),
    ("https://x.feishu.cn/wiki/WIK1", "", ("feishu.cn", "wiki", "WIK1")),
    ("https://x.feishu.cn/docs/DOC1", "", ("feishu.cn", "docs", "DOC1")),
    ("https://x.feishu.cn/sheets/Shtcn1", "", ("feishu.cn", "sheets", "Shtcn1")),
    ("https://x.feishu.cn/base/BasABC", "", ("feishu.cn", "base", "BasABC")),
    ("https://larksuite.com/docx/BARE1", "", ("larksuite.com", "docx", "BARE1")),
    ("https://tenant.example.com/docx/T1", "example.com", ("example.com", "docx", "T1")),
]


@pytest.mark.parametrize("url,allow_host,expected", _PRE_EXISTING)
@pytest.mark.conformance
def test_ac2_every_pre_existing_shape_returns_a_byte_identical_tuple(url, allow_host, expected):
    """AC2: the five older shapes return exactly what they returned. The pattern is now built
    from a different table, so "unchanged" is a claim that has to be checked, not assumed."""
    assert validate_download_url(url, allow_host) == expected


@pytest.mark.parametrize("url", [
    "https://x.feishu.cn/drive/FLD1",           # the folder segment is REQUIRED
    "https://x.feishu.cn/drive/folder",         # …and so is a token
    "https://x.feishu.cn/drive/folder/",
    "https://x.feishu.cn/drive/file/FIL1",      # a real Lark shape this library does not claim
    "https://x.feishu.cn/drive/me/FLD1",
    "https://x.feishu.cn/folder/FLD1",          # not the path Lark uses
    "https://x.feishu.cn/drive/FOLDER/FLD1",    # the path segments stay case-sensitive
    "http://x.feishu.cn/drive/folder/FLD1",     # not https
    "https://evil.example.org/drive/folder/FLD1",   # host policy is untouched
])
@pytest.mark.conformance
def test_ac2_the_widening_is_EXACTLY_ONE_SHAPE(url):
    """AC2: a widening that swallowed a neighbouring drive path, a tokenless url or a foreign
    host would be the regression. Only ``/drive/folder/<token>`` was added."""
    with pytest.raises(ValueError):
        validate_download_url(url)


@pytest.mark.conformance
def test_ac2_host_policy_is_untouched_for_the_new_shape_too():
    """AC2: ``allow_host`` remains the single opt-in, and rejection remains a builtin
    ``ValueError`` — the established, tested contract, extended to nothing."""
    with pytest.raises(ValueError):
        validate_download_url("https://tenant.example.com/drive/folder/FLD4")
    assert validate_download_url(
        "https://tenant.example.com/drive/folder/FLD4", "example.com")[0] == "example.com"


# --------------------------------------------------------------------------- #
# AC3 — RECOGNITION IS NOT REACH: the two refusals, and the promise not made.  #
# --------------------------------------------------------------------------- #

def _validator_refusal():
    with pytest.raises(ValueError) as exc:
        validate_download_url("https://x.feishu.cn/minutes/MIN1")
    return str(exc.value)


def test_ac3_the_validator_refusal_names_the_new_shape_and_keeps_drawing_its_LINE():
    """AC3: the message names what is accepted — including the folder shape, spelled as the
    two-segment path it really is — and keeps saying that recognising a url is not reaching
    what it points at."""
    message = _validator_refusal()
    assert "drive/folder" in message, message
    assert "docx|wiki|sheets|base|drive/folder" in message, message
    for expected in ("Sheets surface", "Base surface", "read_base_markdown", "Drive folder"):
        assert expected in message, (expected, message)
    assert "download" in message.lower()


def test_ac3_the_download_path_REFUSES_a_folder_url_by_ROUTING_it():
    """AC3, updated by LD-327: handing a folder url to the document download is a routing
    answer, not a parse error — and now that the folder read has shipped, it routes to the verb
    that handles it (``larkdocio folder``) rather than saying nothing can follow it."""
    from larkdocio.errors import LarkConfigError
    from larkdocio.read.download import _resolve_doc

    with pytest.raises(LarkConfigError) as exc:
        _resolve_doc("https://x.feishu.cn/drive/folder/FLD1", "", None, "id", "secret")
    message = str(exc.value)
    assert "DRIVE FOLDER" in message, message
    # it ROUTES: it names the verb that reads a folder (§ D2), not merely refuses.
    assert "larkdocio folder" in message, message
    assert "SheetsReadClient" not in message and "read_base_markdown" not in message, (
        "a folder is neither a spreadsheet nor a Base — routing it at either reader would be a "
        "wrong answer confidently given")


#: Alternative folder-read spellings a reader might GUESS at that still do not exist anywhere,
#: so none may be named by any shipped text — the fence AC3 holds. LD-327 update: ``read_folder``,
#: ``walk_folder`` and ``larkdocio.drive`` LEFT this list, because the folder read has now
#: shipped and the routing refusals legitimately name it (``larkdocio.drive.read_folder``); what
#: remains is genuinely nonexistent, which is what keeps the grep below non-vacuous.
_UNSHIPPED_ENTRY_POINTS = (
    "read_drive", "list_folder", "enumerate_folder",
    "read_folder_markdown", "DriveReadClient",
)


def test_ac3_NO_SHIPPED_TEXT_NAMES_AN_ENTRY_POINT_THAT_DOES_NOT_EXIST():
    """AC3 / § Out of Scope: the messages route to a *surface*; they may not promise a call.
    Grepped over the shipped strings a consumer can actually reach."""
    from larkdocio.common import url as url_module
    from larkdocio.read import download as download_module

    texts = {
        "the validator refusal": _validator_refusal(),
        "the validator docstring": validate_download_url.__doc__,
        "the url module docstring": url_module.__doc__,
        "the download path's folder refusal":
            download_module._NON_DOCUMENT_URL_MESSAGES["drive"],
    }
    for label, text in texts.items():
        for name in _UNSHIPPED_ENTRY_POINTS:
            assert name not in text, f"{label} names the unshipped {name!r}"


#: The subset that is STILL unshipped after LD-326 landed the folder read. The composition
#: itself (``read_folder`` / ``render_folder``) shipped here — but **inside** ``larkdocio.drive``,
#: not at the package's top level: LD-327 owns the front door (``capabilities()`` / the CLI /
#: the top-level re-export), and this issue's § Out of Scope forbids moving it. So these
#: alternative spellings a reader might guess at still do not exist anywhere, and they are what
#: keeps the grep above non-vacuous.
_STILL_UNSHIPPED_ENTRY_POINTS = (
    "read_drive", "list_folder", "enumerate_folder",
    "read_folder_markdown", "DriveReadClient",
)

#: Shipped by LD-326 **inside** ``larkdocio.drive`` — but deliberately NOT at the top level
#: ``larkdocio`` (the front door is LD-327's). The fence proves both halves of that division.
_SHIPPED_IN_DRIVE_BELOW_THE_FRONT_DOOR = ("read_folder", "render_folder")


def test_ac3_and_the_thing_it_does_NOT_name_really_is_unshipped():
    """AC3, from the other side: the grep above would be vacuous if every one of those names
    existed. The alternative composition spellings still do not exist anywhere, and even the
    ones LD-326 shipped (``read_folder`` / ``render_folder``) live **inside** ``larkdocio.drive``
    and are still absent from the package top level — the level the greped texts would send a
    reader to, and the front door LD-327 owns."""
    import larkdocio

    for attribute in _UNSHIPPED_ENTRY_POINTS:
        assert not hasattr(larkdocio, attribute), attribute
    for attribute in _STILL_UNSHIPPED_ENTRY_POINTS:
        assert not hasattr(larkdocio, attribute), attribute
        assert not _resolves_in_drive(attribute), (
            f"{attribute} now exists inside larkdocio.drive — this fence, and the texts it "
            "guards, need re-reading rather than a quiet pass")
    for attribute in _SHIPPED_IN_DRIVE_BELOW_THE_FRONT_DOOR:
        assert not hasattr(larkdocio, attribute), (
            f"{attribute} reached the top-level front door — that is LD-327's, not LD-326's")
        assert _resolves_in_drive(attribute), attribute


def _resolves_in_drive(attribute):
    """Whether ``attribute`` is reachable on the Drive package, if that package exists yet."""
    import importlib

    try:
        package = importlib.import_module("larkdocio.drive")
    except ImportError:
        return False
    return hasattr(package, attribute)


# --------------------------------------------------------------------------- #
# AC4 — no prose in the url module contradicts the code.                       #
# --------------------------------------------------------------------------- #

#: A prose enumeration of the accepted shapes, in either spelling the module uses:
#: ``docs|docx|wiki|sheets|base|drive/folder`` or ``docs``/``docx``/… in a sentence.
_PIPED_ENUMERATION = re.compile(r"docs\|docx\|wiki[|\w/]*")


def test_ac4_every_piped_shape_enumeration_in_the_module_lists_the_NEW_shape():
    """AC4: a docstring that contradicts the code is the defect this test exists to prevent.
    Every pipe-separated enumeration in the module's own source — docstrings and ``#:``
    comments alike — must carry the folder shape."""
    from pathlib import Path

    import larkdocio.common.url as url_module

    source = Path(url_module.__file__).read_text(encoding="utf-8")
    found = _PIPED_ENUMERATION.findall(source)
    assert found, "the module used to enumerate the shapes in prose; it must still"
    for enumeration in found:
        assert enumeration.endswith("drive/folder"), enumeration


def test_ac4_the_module_prose_counts_the_shapes_CORRECTLY():
    """AC4: the prose said "all five path shapes" while five was right. It is six now, and the
    number is the kind of thing a widening leaves behind."""
    from pathlib import Path

    import larkdocio.common.url as url_module

    source = Path(url_module.__file__).read_text(encoding="utf-8")
    assert len(URL_PATH_SHAPES) == 6
    assert "all five path" not in source, "the shape count moved; the prose did not"
    assert "all six path" in source


def test_ac4_the_docstrings_that_ENUMERATE_the_types_name_drive():
    """AC4: the function docstring lists the discriminators in prose. It must list the new one
    — this is the sweep, done on the two places that enumerate rather than on every mention."""
    doc = validate_download_url.__doc__
    assert "``drive``" in doc, doc
    assert "drive/folder" in doc


def test_ac4_the_backcompat_shim_is_CORRECTLY_SILENT():
    """AC4: ``larkdocio.utils.url`` re-exports the two functions and enumerates nothing, so it
    has nothing to update — asserted rather than assumed, because "the shim was fine" is the
    kind of claim that rots. It must also still be the SAME objects."""
    from pathlib import Path

    from larkdocio.common import url as core
    from larkdocio.utils import url as shim

    source = Path(shim.__file__).read_text(encoding="utf-8")
    assert not _PIPED_ENUMERATION.findall(source), (
        "the shim now enumerates the shapes and so has become a second place to update")
    for name in ("docs", "sheets", "base", "drive"):
        assert f"`{name}`" not in source, name
    assert shim.validate_download_url is core.validate_download_url
    assert shim.unescape_url is core.unescape_url


# --------------------------------------------------------------------------- #
# AC7 — this issue ships a url line, a document and a guard. No Drive code.    #
# --------------------------------------------------------------------------- #

@pytest.mark.conformance
def test_ac7_the_FRONT_DOOR_now_reports_the_drive_surface():
    """AC7, retired-and-inverted by LD-327 (the pass this fence explicitly handed off to).

    LD-323 recognised a folder URL and bought nothing else; LD-324 shipped the enumeration
    package; **LD-327 is the front-door pass**, so ``capabilities()`` reports the Drive surfaces.
    The top-level namespace still exports nothing Drive-shaped — a folder read is reached
    through ``larkdocio.drive``, not a top-level re-export, and the CLI ``folder`` verb is the
    command-line door.

    **Transformed four times, deleted never (LD-409, LD-432, LD-434, LD-467; D-24).** This pinned
    ``exactly one``
    Drive surface while there was exactly one; LD-409 added a second (``drive-versions-write``)
    LD-432 a third (``drive-access-write``, who may use a document), LD-434 a fourth
    (``drive-files-write``, putting a file in a folder) and LD-467 a fifth
    (``drive-folders-write``, the one organize verb a product ruling opened) — and the reason
    this fence exists is unchanged: the front door must report every Drive surface and the top
    level must still re-export none. So the list is pinned exactly, at its new membership, and
    the mode split is pinned too — a write filed under the read surface is the specific
    mis-statement this now catches.
    """
    import larkdocio

    surfaces = larkdocio.capabilities(full=True)["surfaces"]
    drive_surfaces = [sid for sid in surfaces if "drive" in sid]
    assert drive_surfaces == [
        "drive-read", "drive-versions-write", "drive-access-write",
        "drive-files-write", "drive-folders-write"], drive_surfaces
    assert surfaces["drive-read"]["mode"] == "read"
    assert surfaces["drive-versions-write"]["mode"] == "write"
    assert surfaces["drive-access-write"]["mode"] == "write"
    assert surfaces["drive-files-write"]["mode"] == "write"
    assert not [name for name in getattr(larkdocio, "__all__", ()) if "drive" in name.lower()]
    assert "folder" in __import__("larkdocio.cli", fromlist=["cli"]).cli.commands
