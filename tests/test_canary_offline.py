"""Offline unit tests for the live read-canary scaffolding (LD-003).

These are NOT marked ``live`` — they run in the default ``pytest -q`` with no
creds and no network. They cover the three offline-testable pieces of the
canary:

* the ``live`` marker is registered (so ``pytest`` emits no unknown-marker
  warning and the live tests are deselectable);
* the ``LARKDOCIO_CANARY_DOC`` env plumbing (the ``canary_support`` helpers);
* the canary URL parses under the reader's host allowlist.

The live assertions themselves (real download + determinism) live in
``tests/test_live_canary.py`` and only run under ``pytest -m live``.
"""
import pytest

import canary_support
from larkdocio.utils.url import validate_download_url

# A scratch-doc URL of the .env.example shape on a non-placeholder host (the
# .env.example value itself reads as unset — LD-694). Used here
# ONLY to prove the URL parses offline; the live canary reads it from the env
# (LARKDOCIO_CANARY_DOC), never from this literal.
CANARY_URL = "https://tenant.larksuite.com/docx/DocCanaryExample00000000001"


def test_live_marker_registered(pytestconfig):
    markers = pytestconfig.getini("markers")
    assert any(m.startswith("live:") for m in markers), (
        "expected a `live:` marker registered in "
        f"[tool.pytest.ini_options].markers; got {markers!r}"
    )


def test_canary_doc_url_reads_env(monkeypatch):
    monkeypatch.setenv(canary_support.CANARY_DOC_ENV, CANARY_URL)
    assert canary_support.canary_doc_url() == CANARY_URL


def test_canary_doc_url_none_when_unset(monkeypatch):
    monkeypatch.delenv(canary_support.CANARY_DOC_ENV, raising=False)
    assert canary_support.canary_doc_url() is None


def test_canary_doc_url_none_when_blank(monkeypatch):
    # A blank/whitespace value is treated as unset (so the live test skips).
    monkeypatch.setenv(canary_support.CANARY_DOC_ENV, "   ")
    assert canary_support.canary_doc_url() is None


def _set_read_creds(monkeypatch):
    monkeypatch.setenv("LARK_READ_APP_ID", "dummy_id")
    monkeypatch.setenv("LARK_READ_APP_SECRET", "dummy_secret")


def _clear_read_creds(monkeypatch):
    for name in (
        "LARK_READ_APP_ID",
        "LARK_READ_APP_SECRET",
        "LARK_APP_ID",
        "LARK_APP_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)


def test_live_available_true_with_url_and_creds(monkeypatch):
    monkeypatch.setenv(canary_support.CANARY_DOC_ENV, CANARY_URL)
    _set_read_creds(monkeypatch)
    assert canary_support.live_available() is True
    assert canary_support.missing_reason() is None


def test_live_unavailable_without_url(monkeypatch):
    monkeypatch.delenv(canary_support.CANARY_DOC_ENV, raising=False)
    _set_read_creds(monkeypatch)
    assert canary_support.live_available() is False
    # The skip reason must name the missing env var (never a silent pass).
    assert canary_support.CANARY_DOC_ENV in canary_support.missing_reason()


def test_live_unavailable_without_creds(monkeypatch):
    monkeypatch.setenv(canary_support.CANARY_DOC_ENV, CANARY_URL)
    _clear_read_creds(monkeypatch)
    assert canary_support.live_available() is False
    assert canary_support.missing_reason() is not None


def test_canary_url_validates_offline():
    # Proves the scratch-doc URL parses under the reader's host allowlist,
    # yielding the docx token — no network.
    assert validate_download_url(CANARY_URL) == (
        "larksuite.com",
        "docx",
        "DocCanaryExample00000000001",
    )


# ===========================================================================
# LD-106 — the live SHEETS canary scaffolding (mirrors the docx canary above).
# These are offline: the env plumbing + the sheets-URL parse + the .env.example
# doc-drift guards. The live assertions (two byte-identical L1 renders of the
# scratch sheet) live in tests/test_live_canary.py under `pytest -m live`.
# ===========================================================================

_ENV_EXAMPLE = canary_support.REPO_ROOT / ".env.example"

# A scratch-SHEET URL of the .env.example shape on a non-placeholder host. Used here
# ONLY to prove the URL parses offline; the live sheets canary reads it from the
# env (LARKDOCIO_SCRATCH_SHEET), never from this literal.
SCRATCH_SHEET_URL = "https://tenant.larksuite.com/sheets/SheetScratchExample00000001"


def test_scratch_sheet_url_reads_env(monkeypatch):
    monkeypatch.setenv(canary_support.SCRATCH_SHEET_ENV, SCRATCH_SHEET_URL)
    assert canary_support.scratch_sheet_url() == SCRATCH_SHEET_URL


def test_scratch_sheet_url_none_when_unset(monkeypatch):
    monkeypatch.delenv(canary_support.SCRATCH_SHEET_ENV, raising=False)
    assert canary_support.scratch_sheet_url() is None


def test_scratch_sheet_url_none_when_blank(monkeypatch):
    # A blank/whitespace value is treated as unset (so the sheets canary skips).
    monkeypatch.setenv(canary_support.SCRATCH_SHEET_ENV, "   ")
    assert canary_support.scratch_sheet_url() is None


def test_sheets_live_available_true_with_url_and_creds(monkeypatch):
    monkeypatch.setenv(canary_support.SCRATCH_SHEET_ENV, SCRATCH_SHEET_URL)
    _set_read_creds(monkeypatch)
    assert canary_support.sheets_live_available() is True
    assert canary_support.sheets_missing_reason() is None


def test_sheets_live_unavailable_without_url(monkeypatch):
    monkeypatch.delenv(canary_support.SCRATCH_SHEET_ENV, raising=False)
    _set_read_creds(monkeypatch)
    assert canary_support.sheets_live_available() is False
    # The skip reason must name the missing env var (never a silent pass).
    assert canary_support.SCRATCH_SHEET_ENV in canary_support.sheets_missing_reason()


def test_sheets_live_unavailable_without_creds(monkeypatch):
    monkeypatch.setenv(canary_support.SCRATCH_SHEET_ENV, SCRATCH_SHEET_URL)
    _clear_read_creds(monkeypatch)
    assert canary_support.sheets_live_available() is False
    assert canary_support.sheets_missing_reason() is not None


def test_scratch_sheet_url_parses_offline():
    # Proves the scratch-SHEET URL parses to (base_host, spreadsheet_token). The parse
    # is validate_download_url's own (LD-183 taught it /sheets/); parse_sheet_url is the
    # thin adapter onto it that narrows to the spreadsheet type (LD-210 AC5). No network.
    assert canary_support.parse_sheet_url(SCRATCH_SHEET_URL) == (
        "larksuite.com",
        "SheetScratchExample00000001",
    )


def test_parse_sheet_url_rejects_malformed():
    # A non-sheets / non-Lark URL is a ValueError (parity with validate_download_url).
    import pytest as _pytest

    with _pytest.raises(ValueError):
        canary_support.parse_sheet_url(CANARY_URL)  # a /docx/ URL, not /sheets/
    with _pytest.raises(ValueError):
        canary_support.parse_sheet_url("not-a-url")


def test_env_example_documents_scratch_sheet():
    # LD-106: .env.example documents LARKDOCIO_SCRATCH_SHEET (the canary's target).
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert canary_support.SCRATCH_SHEET_ENV in text, (
        f".env.example must document {canary_support.SCRATCH_SHEET_ENV}"
    )


def test_env_example_scratch_sheet_marked_consumed():
    # LD-106 doc-drift guard: LARKDOCIO_SCRATCH_SHEET is now CONSUMED by the L1 live
    # sheets canary, so the old blanket "not yet consumed by any code or test" claim
    # (which lumped the sheet in with the still-unconsumed Base surface) must be gone.
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "Not yet consumed by any code or test" not in text, (
        "The blanket 'Not yet consumed by any code or test' note in .env.example is "
        "stale — LARKDOCIO_SCRATCH_SHEET is consumed by the L1 live sheets canary "
        "(LD-106). Correct the .env.example commentary."
    )


# --------------------------------------------------------------------------- #
# LD-210 AC5 — the THIRD hand-rolled sheets-URL parser dies.                   #
# --------------------------------------------------------------------------- #
#
# LD-183 recognised ``/sheets/`` in ``validate_download_url`` and collapsed the two hand-rolled
# URL→token expressions in the shipped guide into that one call. Its QA then found a THIRD copy
# surviving here (``parse_sheet_url`` / ``_SHEET_URL_RE``), with three comments asserting
# something now FALSE — that the validator cannot handle a ``/sheets/`` URL — and flagged that it
# was not a one-line swap, because the helper also accepted ``/sheet/`` SINGULAR, which the
# validator rejects.
#
# **THE DECISION (LD-210 AC5): the canary DROPS the singular form and delegates.** The singular
# was never evidenced — LD-183's accepted-shape table, built from real URLs, has ``/sheets/``
# only, and Lark's spreadsheet URLs are plural. Keeping an unevidenced shape alive was the whole
# reason a third parser existed, so the divergence is removed rather than documented. Everything
# the live canary actually uses parses to the identical tuple; that is pinned below, and so is
# the absence of a re-introduced regex.

#: ``(url, expected tuple or None for ValueError)`` — ``parse_sheet_url``'s behavior, captured
#: from the hand-rolled implementation BEFORE the delegation and asserted against it after, so
#: the swap is proven behavior-preserving rather than assumed. The one deliberate change is the
#: singular row.
_PARSE_SHEET_URL_BEHAVIOR = [
    ("https://your-domain.larksuite.com/sheets/SheetScratchExample00000001",
     ("larksuite.com", "SheetScratchExample00000001")),
    ("https://your-domain.larksuite.com/sheets/SheetScratchExample00000001?sheet=3bf016",
     ("larksuite.com", "SheetScratchExample00000001")),
    ("https://x.feishu.cn/sheets/Shtcn1", ("feishu.cn", "Shtcn1")),
    ("https://x.feishu.cn/sheets/Shtcn1/", ("feishu.cn", "Shtcn1")),
    ("https://feishu.cn/sheets/Shtcn2", ("feishu.cn", "Shtcn2")),
    ("https://x.feishu.cn/docx/ABC", None),        # a document URL is not a spreadsheet
    ("not-a-url", None),
    ("https://evil.example.org/sheets/S1", None),  # host policy is the validator's, unchanged
    ("https://x.feishu.cn/sheets/", None),         # tokenless
]


def test_parse_sheet_url_behavior_is_UNCHANGED_by_the_delegation():
    """AC5: the same tuple for every URL shape the live canary actually uses, and the same
    ``ValueError`` for everything it refused."""
    import pytest as _pytest

    for url, expected in _PARSE_SHEET_URL_BEHAVIOR:
        if expected is None:
            with _pytest.raises(ValueError):
                canary_support.parse_sheet_url(url)
        else:
            assert canary_support.parse_sheet_url(url) == expected, url


def test_parse_sheet_url_no_longer_accepts_the_SINGULAR_sheet_path():
    """AC5's one deliberate behavior change, asserted so it is a decision and not a drift: the
    unevidenced ``/sheet/`` form is refused, exactly as the shipped validator refuses it."""
    import pytest as _pytest

    from larkdocio.common import validate_download_url

    with _pytest.raises(ValueError):
        canary_support.parse_sheet_url("https://x.feishu.cn/sheet/Shtcn1")
    with _pytest.raises(ValueError):
        validate_download_url("https://x.feishu.cn/sheet/Shtcn1")


def test_parse_sheet_url_DELEGATES_and_no_hand_rolled_URL_REGEX_SURVIVES():
    """AC5's red proof, the twin of LD-183's *"adding a ``parse_sheets_url`` twin reddens the
    absence assertion"*: re-introducing a hand-rolled Lark-URL regex anywhere in
    ``canary_support`` reddens here, so the third parser cannot grow back."""
    import inspect
    import re as _re

    source = inspect.getsource(canary_support)
    hand_rolled = [
        line.strip() for line in source.splitlines()
        if _re.search(r"(?:feishu\\?\.cn|larksuite\\?\.com|/sheets\??/|sheets\?)", line)
        and ("re.compile" in line or "\\w" in line or "[A-Za-z0-9]" in line)
    ]
    assert not hand_rolled, (
        "a hand-rolled Lark-URL pattern is back in canary_support — the sheets URL parse belongs "
        f"to larkdocio.common.validate_download_url, which recognises /sheets/: {hand_rolled}"
    )
    assert "validate_download_url" in inspect.getsource(canary_support.parse_sheet_url), (
        "parse_sheet_url no longer delegates to the shipped validator"
    )


def test_the_CONFIGURED_scratch_sheet_url_is_one_the_shipped_validator_accepts():
    """AC5's *"assert no live canary URL uses the singular form"*, offline: if a scratch sheet is
    configured in this environment it must parse through the delegation. Skips when unset, so the
    offline suite never depends on a credential-adjacent variable."""
    import pytest as _pytest

    canary_support.load_env()
    configured = canary_support.scratch_sheet_url()
    if not configured:
        _pytest.skip(f"{canary_support.SCRATCH_SHEET_ENV} unset — nothing to check")
    domain, token = canary_support.parse_sheet_url(configured)
    assert domain and token, configured


# ===========================================================================
# LD-694 F13 — a .env.example PLACEHOLDER is unset, not a target.
# `setup.sh` copies .env.example to .env on a fresh clone, and every URL there is
# a placeholder on the `your-domain` host. Read as "set", `pytest -m live` ran
# against the placeholder (once credentials were filled in) instead of skipping
# with the variable's name, as the README promises.
# ===========================================================================

def _env_example_values():
    values = {}
    for line in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.partition("=")
        if sep and name.isupper() and name.startswith("LARKDOCIO_") and value.strip():
            values[name] = value.strip()
    return values


_GETTERS = {
    canary_support.CANARY_DOC_ENV: canary_support.canary_doc_url,
    canary_support.SCRATCH_SHEET_ENV: canary_support.scratch_sheet_url,
    canary_support.SCRATCH_BASE_ENV: canary_support.scratch_base_url,
    canary_support.BLOCKZOO_DOC_ENV: canary_support.blockzoo_doc_url,
}


def test_every_committed_url_value_is_a_placeholder_the_helpers_recognise():
    values = _env_example_values()
    assert set(_GETTERS) <= set(values), sorted(values)
    for name, value in values.items():
        assert canary_support.is_placeholder(value), (name, value)


@pytest.mark.parametrize("name", sorted(_GETTERS))
def test_a_placeholder_from_env_example_reads_as_unset(monkeypatch, name):
    monkeypatch.setenv(name, _env_example_values()[name])
    assert _GETTERS[name]() is None


def test_the_canary_skips_naming_the_variable_when_it_holds_the_placeholder(monkeypatch):
    monkeypatch.setenv(canary_support.CANARY_DOC_ENV,
                       _env_example_values()[canary_support.CANARY_DOC_ENV])
    _set_read_creds(monkeypatch)
    assert canary_support.live_available() is False
    assert canary_support.CANARY_DOC_ENV in canary_support.missing_reason()


def test_a_placeholder_identity_skips_the_arm(monkeypatch):
    monkeypatch.setattr(canary_support, "load_env", lambda: None)
    monkeypatch.setenv("LARKDOCIO_LD694_PROBE_DOC",
                       "https://your-domain.larksuite.com/docx/DocProbeExample0000000000001")
    with pytest.raises(pytest.skip.Exception, match="LARKDOCIO_LD694_PROBE_DOC"):
        canary_support.live_identity("LARKDOCIO_LD694_PROBE_DOC", "this arm")


@pytest.mark.parametrize("value", [
    "https://tenant-1.larksuite.com/docx/DocRealShapeExample00000001",
    "https://tenant-1.feishu.cn/sheets/SheetRealShapeExample000001?sheet=3bf016",
    "DocRealShapeExample00000001",
])
def test_a_real_shaped_value_is_not_a_placeholder(value):
    assert not canary_support.is_placeholder(value)
