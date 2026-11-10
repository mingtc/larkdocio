"""Tests for utils.sanitize.sanitize_path_string.

Covers space->underscore conversion, OS-reserved character stripping,
empty/whitespace fallback to "untitled", leading/trailing -_ stripping,
100-char truncation, and UTF-8 preservation.
"""
from larkdocio.utils.sanitize import sanitize_path_string


def test_spaces_become_underscores():
    assert sanitize_path_string("my file name") == "my_file_name"


def test_os_reserved_chars_stripped():
    # / \ : * ? " < > | are all removed.
    assert sanitize_path_string('a/b\\c:d*e?f"g<h>i|j') == "abcdefghij"


def test_empty_string_returns_untitled():
    assert sanitize_path_string("") == "untitled"


def test_none_returns_untitled():
    assert sanitize_path_string(None) == "untitled"


def test_whitespace_only_returns_untitled():
    # Spaces -> underscores, then leading/trailing underscore strip empties it.
    assert sanitize_path_string("   ") == "untitled"


def test_reserved_only_returns_untitled():
    assert sanitize_path_string("///:::") == "untitled"


def test_leading_trailing_dash_underscore_stripped():
    assert sanitize_path_string("-_name_-") == "name"


def test_truncates_to_100_chars():
    result = sanitize_path_string("a" * 250)
    assert len(result) == 100
    assert result == "a" * 100


def test_utf8_preserved():
    assert sanitize_path_string("日本語テスト") == "日本語テスト"


def test_utf8_with_spaces_preserved():
    assert sanitize_path_string("会议 记录 草稿") == "会议_记录_草稿"
