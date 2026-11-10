"""The always-on offline half of ``test_live_drive_assets_gate`` (LD-386 AC8).

The live arm runs only with credentials and a network. Everything it **claims about itself** is
exactly the class of claim a credential-less run "verifies" by not running, so it is verified
here, on every plain ``pytest``:

* **READ-ONLY, and it names no write.** No write credential variable, no Drive write verb, no
  ``create_folder`` — the arm is a reader and the only thing it writes is a pytest ``tmp_path``.
* **Disposables only.** Its subjects are the bot's own root folder (or the optional
  ``LARKDOCIO_CANARY_FOLDER`` override) and the standing disposable block zoo. It never names
  the write scratch doc, and it never hard-codes a document or folder token.
* **It skips LOUDLY, three ways** — no credentials, no zoo document, and the one that matters
  most: a subject folder that contains **no asset-bearing document** produces an explicit skip
  naming the count, not a quiet pass on an empty set.
* **The un-provisionable resource is recorded, not glossed.** The arm's docstring states *why*
  a disposable folder cannot be self-provisioned (``create_folder`` is a permanent Drive write
  with no purge verb), which is the honest limit on AC8 and must not evaporate.
* **The layout ruling is what it asserts.** The arm checks a flat, token-named pool under
  ``-o`` — not a per-document directory — and the collision leg asserts one file per token.

The last two obligations are proven **against fakes** rather than read as text: the arm's own
``_zoo_result`` builder and the shipped ``fetch_folder_assets`` are driven with an injected
fetcher, so the layout assertions this file makes are the arm's real ones.
"""
import ast
from pathlib import Path

import pytest

import gate_registry as gr
from larkdocio.drive import read as drive_read
from larkdocio.drive.assets import ASSET_DIR, BOARD, IMAGE, fetch_folder_assets
from larkdocio.drive.models import AssetRef
from larkdocio.drive.render import render_folder

import test_live_drive_assets_gate as arm

_TESTS = Path(__file__).resolve().parent
_GATE = _TESTS / "test_live_drive_assets_gate.py"


@pytest.fixture(scope="module")
def gate_source():
    return _GATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def gate_docstring(gate_source):
    return ast.get_docstring(ast.parse(gate_source)) or ""


@pytest.fixture(scope="module")
def gate_body(gate_source, gate_docstring):
    """The arm minus its module docstring — what the arm *does*, not what it explains. The
    docstring is *required* to name the write verb this arm cannot perform, so a naive grep
    over the whole file would forbid the very sentence that records the rule."""
    return gate_source.replace(gate_docstring, "", 1)


# --------------------------------------------------------------------------- #
# Posture — read-only, disposables only, no hard-coded subject.                 #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("forbidden", [
    "LARK_WRITE_APP_ID", "LARK_WRITE_APP_SECRET", "from_write_credentials",
    "LARKDOCIO_WRITE_SCRATCH_DOC",
])
def test_the_arm_names_no_write_credential(gate_source, forbidden):
    assert forbidden not in gate_source


@pytest.mark.parametrize("verb", [
    "create_folder", "upload_all", "import_tasks", "create_shortcut", "permission_public",
    "transfer_owner", "batch_update", "apply_plan",
])
def test_the_arm_names_no_drive_write_verb_outside_its_docstring(gate_body, verb):
    assert verb not in gate_body


def test_the_arm_records_WHY_a_disposable_folder_cannot_be_self_provisioned(gate_docstring):
    """The honest limit on AC8. If this sentence is ever deleted the arm silently starts
    looking like it simply did not bother."""
    assert "create_folder" in gate_docstring
    assert "purge" in gate_docstring
    assert "permanent" in gate_docstring.lower()


def test_the_arm_hard_codes_no_document_or_folder_token(gate_body):
    """Every subject is resolved live or from an env var — never a literal token."""
    tree = ast.parse(gate_body)
    literals = [node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    suspects = [text for text in literals
                if len(text) > 20 and " " not in text and text.isalnum()]
    assert not suspects, f"the arm hard-codes what looks like a live token: {suspects}"


def test_the_arm_resolves_its_subjects_through_canary_support_only(gate_body):
    assert "canary_support.canary_folder_override()" in gate_body
    assert "canary_support.blockzoo_doc_url()" in gate_body
    assert "root_folder_token()" in gate_body


# --------------------------------------------------------------------------- #
# The three loud skips.                                                         #
# --------------------------------------------------------------------------- #

def test_the_arm_skips_loudly_without_read_credentials(monkeypatch):
    monkeypatch.setattr(arm.canary_support, "read_creds_available", lambda: False)
    monkeypatch.setattr(arm.canary_support, "missing_reason",
                        lambda: "LARK_READ_APP_ID / LARK_READ_APP_SECRET are unset")
    with pytest.raises(pytest.skip.Exception) as caught:
        next(arm.live_env.__wrapped__())
    assert "LARK_READ_APP_ID" in str(caught.value)


def test_the_arm_skips_loudly_without_the_zoo_document(monkeypatch):
    monkeypatch.setattr(arm.canary_support, "blockzoo_doc_url", lambda: None)
    with pytest.raises(pytest.skip.Exception) as caught:
        arm.zoo.__wrapped__(True)
    assert arm.canary_support.BLOCKZOO_DOC_ENV in str(caught.value)


def test_the_empty_folder_case_is_an_EXPLICIT_skip_not_a_quiet_pass(gate_body):
    """The one that matters most: a folder holding no asset-bearing document must SAY so. A
    fetch-count assertion that vacuously passes on an empty set is the failure shape this
    guards."""
    assert "if referenced == 0:" in gate_body
    assert "pytest.skip(" in gate_body
    assert "LARKDOCIO_CANARY_FOLDER" in gate_body


# --------------------------------------------------------------------------- #
# The layout ruling, driven against fakes — the arm's own assertions, offline.  #
# --------------------------------------------------------------------------- #

def _fake_zoo_result(monkeypatch, *, copies=1):
    refs = (AssetRef("imgTOKEN", IMAGE), AssetRef("wbTOKEN", BOARD))
    monkeypatch.setattr(drive_read, "read_child",
                        lambda *a, **k: drive_read.ChildRead("![](imgTOKEN)\n\n"
                                                             "![Whiteboard](wbTOKEN)",
                                                             7, refs))
    return arm._zoo_result("https://x.larksuite.com/docx/zoo", "zoo", copies=copies)


def _fetcher(tmp_path):
    def fetch(kind, token, directory):
        import os
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{token}.png")
        with open(path, "wb") as handle:
            handle.write(b"\x89PNG")
        return path

    return fetch


def test_the_arms_builder_produces_a_walk_shaped_result(monkeypatch):
    result = _fake_zoo_result(monkeypatch)
    assert result.accounted()
    assert {ref.kind for ref in result.reads[0].assets} == {IMAGE, BOARD}


def test_the_pool_the_arm_asserts_is_FLAT_and_TOKEN_NAMED(monkeypatch, tmp_path):
    result = _fake_zoo_result(monkeypatch)
    markdown, report = fetch_folder_assets(
        result, render_folder(result), str(tmp_path), fetcher=_fetcher(tmp_path))

    pool = tmp_path / ASSET_DIR
    assert sorted(p.name for p in pool.iterdir()) == ["imgTOKEN.png", "wbTOKEN.png"]
    assert [p for p in pool.iterdir() if p.is_dir()] == [], (
        "the pool is FLAT — a per-document subdirectory is the rejected fork")
    assert report.complete
    for name in ("imgTOKEN.png", "wbTOKEN.png"):
        assert f"{ASSET_DIR}/{name}" in markdown


def test_the_collision_leg_really_would_catch_a_double_fetch(monkeypatch, tmp_path):
    result = _fake_zoo_result(monkeypatch, copies=2)
    markdown, report = fetch_folder_assets(
        result, render_folder(result), str(tmp_path), fetcher=_fetcher(tmp_path))

    assert len(result.reads) == 2
    assert report.fetched == ("imgTOKEN", "wbTOKEN")
    assert len(list((tmp_path / ASSET_DIR).iterdir())) == 2
    assert markdown.count(f"{ASSET_DIR}/imgTOKEN.png") == 2


# --------------------------------------------------------------------------- #
# The registry knows about this pair.                                           #
# --------------------------------------------------------------------------- #

def test_the_gate_and_this_companion_are_registered_as_a_pair():
    gate = gr.REGISTRY["test_live_drive_assets_gate.py"]
    assert gate.kind is gr.Kind.HAS_COMPANION
    assert gate.companion == "test_live_drive_assets_gate_offline.py"
    assert gr.REGISTRY[gate.companion].subject == "test_live_drive_assets_gate.py"
