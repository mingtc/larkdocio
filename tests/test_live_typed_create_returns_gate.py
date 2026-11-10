"""LD-583 AC7 — the typed create returns, proved against a REAL reply.

``@pytest.mark.live_write``, deselected by default and **refused to execute** unless the run
names its authorising issue::

    LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY=LD-583 pytest -m live_write \
        tests/test_live_typed_create_returns_gate.py

**Why this arm exists at all, rather than trusting the offline doubles.** A typed return whose
fields were only ever proven against a recorded double is a guess wearing the shape of an
answer — the same objection ``CreatedFolder``'s own docstring raises about assembled URLs. These
four verbs *create objects*; the only honest proof that the type carries what the reply carries
is to make the call and compare the type against **what came back today**.

**THE BUDGET, declared before the spend** (``process/doctrine/live-resources.md``; the same
table is in the issue's Spec/Plan § 4). **Four objects, every one reclaimable, none permanent,
no media token minted:**

===  =================  =================================  ==============================
 #   Kind               Created by                         Torn down by
===  =================  =================================  ==============================
 1   docx document      ``WriteClient.create_document``     ``delete_document``, ``finally``
 2   spreadsheet        ``create_spreadsheet``              ``delete_spreadsheet``, ``finally``
 3   Base               ``BaseSchemaClient.create_app``     ``delete_base``, ``finally``
 4   copy of a Base     ``BaseSchemaClient.copy_app``       ``delete_base``, ``finally``
===  =================  =================================  ==============================

**Disposables only.** Every token this file touches is one it created in this run, in the
human-visible folder named by ``LARKDOCIO_DISPOSABLES_FOLDER``. It names no canary, no standing
scratch document, no zoo target and no real object. Residue is **named, never counted**: the
ledger's own ``orphans()`` output is printed per object at the end.
"""
import pathlib
import tempfile
import time

import pytest
from lark_oapi.api.bitable.v1 import App

import base_write_harness
import canary_support
import docx_ledger
import sheets_write_harness
from larkdocio.base.schema_client import BaseSchemaClient, CopiedBase, CreatedBase
from larkdocio.common.auth import get_write_credentials
from larkdocio.errors import LarkAPIError
from larkdocio.sheets.write_client import CreatedSpreadsheet, SheetsWriteClient
from larkdocio.write.client import CreatedDocument, WriteClient

pytestmark = pytest.mark.live_write
# LD-370: the live rings are CONFORMANCE-tier — the mark is OVERLAID, never replacing
# the statement above (the ring guards read that literal line to prove ring membership).
# See process/doctrine/conformance-tier.md.
pytestmark = [pytestmark, pytest.mark.conformance]

DOMAIN = "larksuite.com"


def _live_or_skip():
    canary_support.load_env()
    reason = canary_support.live_write_missing_reason()
    if reason:
        pytest.skip(reason)
    return canary_support.require_disposables_folder()


def _report(label, value, keys_or_attributes):
    """Name what the real reply answered, so the evidence is the reply and not a summary."""
    print(f"\n[LD-583 live] {label}: {type(value).__name__} "
          f"answering {sorted(keys_or_attributes)}")


def test_the_docx_create_type_matches_the_REAL_reply(capsys):
    """Object 1 of 4. **The docx reply's own key set is what `CreatedDocument` is checked
    against** — including the negative: the live reply carries no ``url`` key, which is the
    fact the type encodes by having no ``url`` attribute."""
    folder = _live_or_skip()
    # `WriteClient` takes the pair positionally — it ships no `from_write_credentials`
    # classmethod, unlike its sheets and Base siblings. The WRITE pair, never the read one.
    writer = WriteClient(*get_write_credentials(), DOMAIN)
    # A run-local ledger, so this arm's residue is its own to name and nobody else's to adopt.
    tmpdir = tempfile.mkdtemp(prefix="ld583-typed-create-")
    ledger = docx_ledger.Ledger(pathlib.Path(tmpdir) / "run_ledger.json")

    title = f"larkdocio-DISPOSABLE-LD583-doc-{int(time.time())}"
    with docx_ledger.disposable(writer, ledger, title=title,
                                folder_token=folder) as disposable:
        created = disposable.created
        _report("create_document", created, created.keys())

        assert isinstance(created, CreatedDocument)
        assert isinstance(created, dict)
        # every attribute is a view onto a key the REAL reply carried
        assert created["document_id"] == created.document_id == disposable.document_id
        assert created["title"] == created.title == title
        assert "revision_id" in created and created.revision_id == created["revision_id"]
        assert created.folder_token == folder
        # THE NEGATIVE, measured today rather than assumed: no url key on the wire…
        assert "url" not in created, (
            f"the docx v1 create reply carried a url today: {sorted(created)} — the type's "
            "no-url claim is measured, so a reply that grew one is a finding, not a pass")
        # …and therefore none on the value, with the reason readable rather than guessable
        assert not hasattr(created, "url")
        with pytest.raises(AttributeError) as raised:
            created.url
        assert created.no_url_reason in str(raised.value)
        # no URL was assembled from a host and a token, anywhere in the answer
        for value in created.values():
            assert "http" not in str(value)

    print(f"\n[LD-583 residue] docx: {ledger.entries()}")


def test_the_spreadsheet_create_type_matches_the_REAL_reply(capsys):
    """Object 2 of 4. Its reply **does** carry a ``url``, and the type carries Lark's own
    bytes — the assertion is identity with the reply, which an assembled link could not pass."""
    folder = _live_or_skip()
    writer = SheetsWriteClient.from_write_credentials(DOMAIN)

    title = sheets_write_harness.disposable_title(f"LD583-sheet-{int(time.time())}")
    created = writer.create_spreadsheet(title, folder_token=folder)
    token = created["spreadsheet_token"]
    assert token, f"create returned no spreadsheet_token: {created!r}"
    try:
        _report("create_spreadsheet", created, created.keys())

        assert isinstance(created, CreatedSpreadsheet)
        assert isinstance(created, dict)
        assert created.spreadsheet_token == created["spreadsheet_token"] == token
        assert created.title == created["title"] == title
        assert created.folder_token == created["folder_token"]
        # the url is REAL and is the reply's own value — never assembled
        assert created["url"], f"the sheets create reply carried no url today: {created!r}"
        assert created.url == created["url"]
        assert token in created.url
        # the disclosure a caller holding this object meets
        assert "orphan by construction" in created.capture_the_token
    finally:
        code = None
        try:
            writer.delete_spreadsheet(token)
            code = 0
        except LarkAPIError as exc:
            code = exc.code
        print(f"\n[LD-583 residue] spreadsheet {token} delete_code={code!r}")
    assert code == 0, f"the disposable spreadsheet was not trashed: code={code!r}"


def test_the_base_create_and_copy_types_match_the_REAL_echoes(capsys):
    """Objects 3 and 4 of 4. These two return the SDK's ``App``, **not** a dict, so what is
    proved live is that every attribute of the real echo survives onto the type — and that the
    copy's own measured fact (an empty ``default_table_id``) is visible on the value the
    ``echo_is_not_state`` disclosure is about."""
    folder = _live_or_skip()
    schema = BaseSchemaClient.from_write_credentials()
    ledger = base_write_harness.Ledger()

    name = base_write_harness.disposable_title(f"LD583-base-{int(time.time())}")
    created = schema.create_app(name, folder, time_zone="Asia/Singapore")
    app_token = created.app_token
    assert app_token, f"create_app returned no app_token: {created!r}"
    ledger.record_create(app_token, name)

    copy_token = None
    try:
        _report("create_app", created, vars(created))
        assert isinstance(created, CreatedBase)
        assert isinstance(created, App)
        for attribute in App._types:
            assert hasattr(created, attribute), attribute
        assert created.folder_token == folder
        assert created.time_zone == "Asia/Singapore"
        assert "not empty" in created.default_table_disclosure.lower()
        # the url is the SDK echo's own; nothing here builds one
        if created.url:
            assert app_token in created.url

        copy_name = base_write_harness.disposable_title(f"LD583-copy-{int(time.time())}")
        copied = schema.copy_app(app_token, copy_name, without_content=True,
                                 folder_token=folder)
        copy_token = copied.app_token
        assert copy_token, f"copy_app returned no app_token: {copied!r}"
        ledger.record_create(copy_token, copy_name)

        _report("copy_app", copied, vars(copied))
        assert isinstance(copied, CopiedBase)
        assert isinstance(copied, App)
        for attribute in App._types:
            assert hasattr(copied, attribute), attribute
        # the measured fact the disclosure exists for, seen on the live echo
        assert not copied.default_table_id, (
            f"the copy echo carried a default_table_id today: {copied.default_table_id!r} — "
            "the async-copy claim is measured, so this is a finding, not a pass")
        assert "asynchronous" in copied.echo_is_not_state.lower()
    finally:
        for token in [t for t in (copy_token, app_token) if t]:
            code, deleted = None, False
            try:
                schema.delete_base(token)
                code, deleted = 0, True
            except LarkAPIError as exc:
                code = exc.code
            ledger.record_delete(token, code, deleted)
            print(f"\n[LD-583 residue] base {token} delete_code={code!r} deleted={deleted}")

    # Residue NAMED, not counted: the oracle's own per-object answer.
    remaining = base_write_harness.orphans(ledger=ledger)
    print(f"\n[LD-583 orphans()] {remaining!r}")
    assert remaining == [], f"the live leg left orphans: {remaining!r}"
