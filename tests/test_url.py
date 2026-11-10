"""Tests for utils.url.validate_download_url.

Covers subdomain handling, doc_type extraction (docs/docx/wiki), the
allow_host extra host, and the rejection paths (bad host, wrong path
segment, non-https) which must raise ValueError. Each accepted case asserts
the exact (domain, doc_type, token) tuple returned.
"""
import pytest

from larkdocio.utils.url import validate_download_url

# Every case here is a URL grammar or a refusal of one — the accepted host/type/token
# vocabulary and the host, path and scheme lines the parse draws. All of it is
# consumer-observable and none of it is this implementation's choice, so the whole file
# qualifies and the file-level mark is the right unit.
# See process/doctrine/conformance-tier.md (a lens, not a gate).
pytestmark = pytest.mark.conformance


def test_larksuite_docx_no_subdomain():
    assert validate_download_url("https://larksuite.com/docx/ABC123") == (
        "larksuite.com",
        "docx",
        "ABC123",
    )


def test_larksuite_docx_multi_subdomain():
    # 0..N subdomain labels are allowed before the base host.
    assert validate_download_url(
        "https://your-domain.larksuite.com/docx/Tok3n"
    ) == ("larksuite.com", "docx", "Tok3n")


def test_feishu_wiki_single_subdomain():
    assert validate_download_url("https://xxx.feishu.cn/wiki/WikiTok") == (
        "feishu.cn",
        "wiki",
        "WikiTok",
    )


def test_docs_doc_type_extracted():
    # The legacy "docs" type is still parsed out of the URL here; the
    # unsupported-guard lives downstream in the download command.
    assert validate_download_url("https://feishu.cn/docs/DocsTok") == (
        "feishu.cn",
        "docs",
        "DocsTok",
    )


def test_trailing_path_is_ignored():
    # Only the leading id segment is captured; trailing segments/params are
    # not part of the token.
    assert validate_download_url(
        "https://foo.larksuite.com/docx/Id42/extra?query=1"
    ) == ("larksuite.com", "docx", "Id42")


def test_allow_host_extra_host_accepted():
    assert validate_download_url(
        "https://custom.example.com/wiki/Node9", allow_host="example.com"
    ) == ("example.com", "wiki", "Node9")


def test_allow_host_not_supplied_rejects_custom_host():
    with pytest.raises(ValueError):
        validate_download_url("https://custom.example.com/wiki/Node9")


def test_rejects_bad_host():
    with pytest.raises(ValueError):
        validate_download_url("https://evil.invalid/docx/ABC123")


def test_rejects_wrong_path_segment():
    with pytest.raises(ValueError):
        validate_download_url("https://feishu.cn/sheet/ABC123")


def test_rejects_non_https():
    with pytest.raises(ValueError):
        validate_download_url("http://feishu.cn/docx/ABC123")
