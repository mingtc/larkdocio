"""Tests for larkdocio.read.client against a stubbed SDK (no network).

We construct a ``Client`` via ``__new__`` (skipping ``__init__``'s real SDK
builder) and inject a stub ``lark_client`` whose docx/drive/board/wiki shims
mimic the SDK's success/data/file response shapes. This pins:

* multi-page pagination in ``get_docx_content`` (the ``has_more`` / ``page_token``
  loop) and the ``items=None`` guard;
* ``download_image`` filename/extension fallback and the ``resp.file is None``
  guards (image + board);
* the exact error-message strings raised on ``resp.success() == False``.

  **SUPERSEDED IN ITS CONCLUSION BY LD-531 (2026-08-20); THE REASON AND EVERY ASSERTION
  STAY.** What this bullet said before, verbatim: *"these are the substrings
  ``download._report_error`` later re-parses (``not found``, ``not read permission``, error
  codes like ``1061004`` / ``99991672``)."* The reason it existed — the exact bytes of a
  reader raise are a contract something downstream depends on, so pin them — is unchanged,
  and every message assertion below is unchanged with it.

  What moved is *what* depends on them. ``download._report_error`` now routes on the
  exception's CLASS and ``code``, not on substrings of its message, so these strings are no
  longer the routing's input. They are still worth pinning for the two reasons that outlive
  it: they are what an operator reads, and ``code``/``msg`` are echoed INTO them, so a drift
  in the message shape is still a drift in what the reader reports.
"""

import io
from types import SimpleNamespace

import pytest

from larkdocio.read.client import Client


def _resp(success=True, code=0, msg="ok", **data):
    """A docx/wiki-shaped response: ``.success()`` + ``.code`` + ``.msg`` + ``.data``."""
    return SimpleNamespace(
        success=lambda: success,
        code=code,
        msg=msg,
        data=SimpleNamespace(**data),
    )


def _media_resp(success=True, code=0, msg="ok", file_name=None, file=None):
    """A drive-media-shaped response: ``.file_name`` + ``.file`` (a ``.read()`` stream)."""
    return SimpleNamespace(
        success=lambda: success,
        code=code,
        msg=msg,
        file_name=file_name,
        file=file,
    )


def _client_with(
    *,
    docx_doc_get=None,
    children_get=None,
    media_download=None,
    board_download=None,
    wiki_get_node=None,
):
    """Build a ``Client`` with a stub ``lark_client``; unset shims get sane happy defaults."""
    client = Client.__new__(Client)
    client.lark_client = SimpleNamespace(
        docx=SimpleNamespace(
            v1=SimpleNamespace(
                document=SimpleNamespace(
                    get=docx_doc_get
                    or (lambda req: _resp(document=SimpleNamespace(title="t")))
                ),
                document_block_children=SimpleNamespace(
                    get=children_get
                    or (lambda req: _resp(items=[], page_token="", has_more=False))
                ),
            )
        ),
        drive=SimpleNamespace(
            v1=SimpleNamespace(
                media=SimpleNamespace(
                    download=media_download
                    or (lambda req: _media_resp(file=io.BytesIO(b"")))
                ),
            )
        ),
        board=SimpleNamespace(
            v1=SimpleNamespace(
                whiteboard=SimpleNamespace(
                    download_as_image=board_download
                    or (lambda req: SimpleNamespace(
                        success=lambda: True, code=0, msg="ok", file=io.BytesIO(b"")
                    ))
                ),
            )
        ),
        wiki=SimpleNamespace(
            v2=SimpleNamespace(
                space=SimpleNamespace(
                    get_node=wiki_get_node
                    or (lambda req: _resp(node=SimpleNamespace(obj_token="x")))
                ),
            )
        ),
    )
    return client


# --------------------------------------------------------------------------- #
# AC1 — get_docx_content pagination                                           #
# --------------------------------------------------------------------------- #

def test_get_docx_content_paginates_across_pages():
    """Two-page fetch: ``has_more`` true→false, ``page_token`` threaded into the
    next request, and the items of both pages concatenated in order."""
    seen_tokens = []
    pages = [
        _resp(items=["b1", "b2"], page_token="PAGE2", has_more=True),
        _resp(items=["b3"], page_token="", has_more=False),
    ]

    def children_get(req):
        seen_tokens.append(req.page_token)
        return pages[len(seen_tokens) - 1]

    client = _client_with(children_get=children_get)

    docx, blocks = client.get_docx_content("doc123")

    assert blocks == ["b1", "b2", "b3"]
    # First request carries no page_token; the second threads page1's token.
    assert seen_tokens == [None, "PAGE2"]
    assert docx.title == "t"


def test_get_docx_content_handles_none_items():
    """A paginated block response with ``data.items=None`` must not raise; the
    guarded ``or []`` should yield an empty block list."""
    block_resp = _resp(items=None, page_token="", has_more=False)
    client = _client_with(children_get=lambda req: block_resp)

    docx, blocks = client.get_docx_content("doc123")

    assert blocks == []


# --------------------------------------------------------------------------- #
# AC2 — download_image / download_board_image filename + file guards          #
# --------------------------------------------------------------------------- #

def test_download_image_uses_header_filename_extension(tmp_path):
    """A header ``file_name`` with an extension drives the on-disk suffix, while
    the on-disk stem is always the token."""
    resp = _media_resp(file_name="picture.jpg", file=io.BytesIO(b"IMG"))
    client = _client_with(media_download=lambda req: resp)

    out = client.download_image("tok1", str(tmp_path))

    assert out == str(tmp_path / "tok1.jpg")
    assert (tmp_path / "tok1.jpg").read_bytes() == b"IMG"


def test_download_image_defaults_to_png_when_no_filename(tmp_path):
    """No header ``file_name`` → the ``{token}.png`` default → ``.png`` suffix."""
    resp = _media_resp(file_name=None, file=io.BytesIO(b"X"))
    client = _client_with(media_download=lambda req: resp)

    out = client.download_image("tok2", str(tmp_path))

    assert out == str(tmp_path / "tok2.png")


def test_download_image_falls_back_to_png_when_filename_has_no_suffix(tmp_path):
    """A header ``file_name`` with no suffix falls back to ``.png``."""
    resp = _media_resp(file_name="noext", file=io.BytesIO(b"X"))
    client = _client_with(media_download=lambda req: resp)

    out = client.download_image("tok3", str(tmp_path))

    assert out == str(tmp_path / "tok3.png")


def test_download_image_raises_when_file_is_none(tmp_path):
    """A success response with no ``file`` content raises the explicit guard."""
    resp = _media_resp(file_name="a.png", file=None)
    client = _client_with(media_download=lambda req: resp)

    with pytest.raises(Exception, match="response contained no file content"):
        client.download_image("tok4", str(tmp_path))


def test_download_board_image_writes_file(tmp_path):
    """Happy path: board image is written as ``{whiteboard_id}.png``."""
    resp = SimpleNamespace(success=lambda: True, code=0, msg="ok", file=io.BytesIO(b"BRD"))
    client = _client_with(board_download=lambda req: resp)

    out = client.download_board_image("wb2", str(tmp_path))

    assert out == str(tmp_path / "wb2.png")
    assert (tmp_path / "wb2.png").read_bytes() == b"BRD"


def test_download_board_image_raises_when_file_is_none(tmp_path):
    """A success response with no ``file`` content raises the explicit guard."""
    resp = SimpleNamespace(success=lambda: True, code=0, msg="ok", file=None)
    client = _client_with(board_download=lambda req: resp)

    with pytest.raises(Exception, match="response contained no file content"):
        client.download_board_image("wb1", str(tmp_path))


def test_download_board_image_error_surfaces_status_and_log_id(tmp_path):
    """A failed board download surfaces code/msg/HTTP status/log id in the message."""
    resp = SimpleNamespace(
        success=lambda: False,
        code=None,
        msg=None,
        get_log_id=lambda: "LOG-123",
        raw=SimpleNamespace(status_code=403),
    )
    client = _client_with(board_download=lambda req: resp)

    with pytest.raises(Exception) as ei:
        client.download_board_image("wb3", str(tmp_path))

    msg = str(ei.value)
    assert "Failed to download board image wb3" in msg
    assert "HTTP: 403" in msg
    assert "LogID: LOG-123" in msg


# --------------------------------------------------------------------------- #
# AC3 — error-message strings _report_error re-parses by substring            #
# --------------------------------------------------------------------------- #

def test_get_docx_content_document_error_message_pinned():
    resp = _resp(success=False, code="1061004", msg="not found")
    client = _client_with(docx_doc_get=lambda req: resp)

    with pytest.raises(Exception) as ei:
        client.get_docx_content("doc9")

    msg = str(ei.value)
    assert msg == "Failed to get docx document doc9: Code: 1061004, Msg: not found"
    # Lark's code and msg, echoed into the operator-facing text. `_report_error` reads them off
    # the exception now (LD-531) rather than back out of this string, but the string is still
    # what a human sees.
    assert "1061004" in msg
    assert "not found" in msg


def test_get_docx_content_blocks_error_message_pinned():
    """The block-listing (paginated) branch has its own error string."""
    children_resp = _resp(success=False, code="99991672", msg="not read permission")
    client = _client_with(children_get=lambda req: children_resp)

    with pytest.raises(Exception) as ei:
        client.get_docx_content("docB")

    msg = str(ei.value)
    assert msg == "Failed to get docx blocks: Code: 99991672, Msg: not read permission"
    assert "99991672" in msg
    assert "not read permission" in msg
    # ...and the exception carries them as attributes, which is what the routing reads.
    assert str(ei.value.code) == "99991672" and ei.value.msg == "not read permission"


def test_download_image_error_message_pinned(tmp_path):
    resp = _media_resp(success=False, code="1061004", msg="not read permission")
    client = _client_with(media_download=lambda req: resp)

    with pytest.raises(Exception) as ei:
        client.download_image("imgX", str(tmp_path))

    msg = str(ei.value)
    assert msg == "Failed to download image imgX: Code: 1061004, Msg: not read permission"
    assert "1061004" in msg
    assert "not read permission" in msg


def test_get_wiki_node_info_error_message_pinned():
    resp = _resp(success=False, code="1061004", msg="not found")
    client = _client_with(wiki_get_node=lambda req: resp)

    with pytest.raises(Exception) as ei:
        client.get_wiki_node_info("wikitok")

    msg = str(ei.value)
    assert msg == "Failed to get wiki node info wikitok: Code: 1061004, Msg: not found"
    assert "1061004" in msg
    assert "not found" in msg


def test_get_wiki_node_info_returns_node_on_success():
    node = SimpleNamespace(obj_token="obj1", obj_type="docx")
    client = _client_with(wiki_get_node=lambda req: _resp(node=node))

    assert client.get_wiki_node_info("wikitok") is node
