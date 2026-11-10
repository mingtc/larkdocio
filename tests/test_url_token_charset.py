"""LD-396 — FULL-TOKEN-OR-REFUSE: a token that is 40 % of a token is not a token.

The regeneration spike's divergence **A4**: ``…/docx/Ab-c_1`` used to return the token
``'Ab'``. The leading-run regex matched as much as it could and never asked whether it had
matched **all** of it, so a user-pasted token carrying a hyphen or an underscore was
**silently truncated** into a value that is structurally plausible — it looks exactly like a
real token — and handed downstream as a lookup.

The maintainer ruling (2026-08-10) is **full-token-or-refuse**, uniformly across the grammar family:
a URL whose **token region** carries a character outside the token alphabet
(``[A-Za-z0-9]``) is refused **loudly** — ``ValueError`` from
:func:`~larkdocio.common.url.validate_download_url` (its established refusal contract) and
:class:`~larkdocio.common.url.NotADeepLink` from
:func:`~larkdocio.common.url.parse_deep_link` (its established refusal answer) — never a
truncated-but-plausible token and never a half-filled anchor.

This is the **product**, not this implementation: a rewrite from the corpus must still
refuse. Hence the module-level conformance mark (process/doctrine/conformance-tier.md).
"""
import pytest

from larkdocio.common.url import (
    NotADeepLink,
    URL_PATH_SHAPES,
    parse_deep_link,
    validate_download_url,
)

pytestmark = pytest.mark.conformance

HOST = "https://your-domain.larksuite.com"

#: The spike's exact reproduction string — the token region as it was pasted.
MANGLED = "Ab-c_1"


# --------------------------------------------------------------------------- #
# AC1 — the spike's EXACT reproduction                                          #
# --------------------------------------------------------------------------- #

def test_ac1_the_spike_reproduction_is_refused_not_truncated():
    with pytest.raises(ValueError) as excinfo:
        validate_download_url(f"{HOST}/docx/{MANGLED}")
    # The failure mode this issue exists to kill: a plausible-looking prefix.
    assert "'Ab'" not in str(excinfo.value)


def test_ac1_the_spike_reproduction_is_not_a_deep_link_either():
    got = parse_deep_link(f"{HOST}/docx/{MANGLED}#share-Example6927bf4fb83ebfc55a3a")
    assert got == NotADeepLink(f"{HOST}/docx/{MANGLED}#share-Example6927bf4fb83ebfc55a3a")


# --------------------------------------------------------------------------- #
# AC2 / AC4 — UNIFORM across the whole grammar family                           #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("shape", sorted(URL_PATH_SHAPES))
@pytest.mark.parametrize("token", ["Ab-c_1", "Ab-c", "Ab_c", "Ab.c", "Ab c", "-Abc", "_Abc"])
def test_ac4_every_path_shape_refuses_a_mangled_token_region(shape, token):
    # doc (docs/docx/wiki), sheet, base and folder all read their token through the SAME
    # accepting pattern, so the fix is uniform by construction rather than by repetition.
    with pytest.raises(ValueError):
        validate_download_url(f"{HOST}/{shape}/{token}")


@pytest.mark.parametrize("url_template", [
    "{host}/docx/{token}#share-Example6927bf4fb83ebfc55a3a",   # doc grammar
    "{host}/sheets/{token}?sheet=7pg9wE",                       # sheet grammar (tab)
    "{host}/sheets/{token}?sheet=7pg9wE&rangeId=7pg9wE_x&rangeVer=1",  # sheet (range)
    "{host}/record/{token}",                                    # record grammar
])
def test_ac4_every_deep_link_grammar_refuses_a_mangled_token_region(url_template):
    url = url_template.format(host=HOST, token=MANGLED)
    assert parse_deep_link(url) == NotADeepLink(url)


def test_ac2_a_refusal_is_never_a_half_filled_anchor():
    # The parse's standing promise: no partially-filled answer, ever.
    got = parse_deep_link(f"{HOST}/sheets/{MANGLED}?sheet=7pg9wE")
    assert isinstance(got, NotADeepLink)
    assert not hasattr(got, "spreadsheet_token")


# --------------------------------------------------------------------------- #
# AC8 — the refusal is DISCOVERABLE, not silent                                 #
# --------------------------------------------------------------------------- #

def test_ac8_the_validator_refusal_names_the_token_region_it_refused():
    with pytest.raises(ValueError) as excinfo:
        validate_download_url(f"{HOST}/docx/{MANGLED}")
    message = str(excinfo.value)
    assert MANGLED in message, "the refusal must quote the token region it refused"
    assert "token" in message.lower()


# --------------------------------------------------------------------------- #
# AC9 — no OTHER parsing behavior changes                                       #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("url,expected", [
    ("https://larksuite.com/docx/ABC123", ("larksuite.com", "docx", "ABC123")),
    (f"{HOST}/docx/Tok3n", ("larksuite.com", "docx", "Tok3n")),
    ("https://xxx.feishu.cn/wiki/WikiTok", ("feishu.cn", "wiki", "WikiTok")),
    ("https://feishu.cn/docs/DocsTok", ("feishu.cn", "docs", "DocsTok")),
    ("https://x.larksuite.com/sheets/ShT0ken", ("larksuite.com", "sheets", "ShT0ken")),
    ("https://x.larksuite.com/base/BsT0ken", ("larksuite.com", "base", "BsT0ken")),
    ("https://x.larksuite.com/drive/folder/FldTok", ("larksuite.com", "drive", "FldTok")),
    # A token ENDS at its segment boundary — trailing segments, a query and a fragment are
    # not part of it and never were. Full-token-or-refuse is about the token region only.
    ("https://foo.larksuite.com/docx/Id42/extra?query=1",
     ("larksuite.com", "docx", "Id42")),
    ("https://foo.larksuite.com/docx/Id42?query=1", ("larksuite.com", "docx", "Id42")),
    ("https://foo.larksuite.com/docx/Id42#share-x", ("larksuite.com", "docx", "Id42")),
])
def test_ac9_alphanumeric_tokens_parse_exactly_as_before(url, expected):
    assert validate_download_url(url) == expected


def test_ac9_the_public_tuple_does_not_move():
    got = validate_download_url("https://larksuite.com/docx/ABC123")
    assert isinstance(got, tuple) and len(got) == 3
