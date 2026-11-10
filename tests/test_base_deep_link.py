"""LD-498 — the Base deep-link builders: `base.table_url` / `base.view_url`.

Two pure, offline functions that mint `…/base/<app_token>?table=&view=[&record=]` from the
Base's own URL and ids a caller already holds. The tests below hold the four things that make
them safe to ship: the host is an INPUT (never derived, never hardcoded), the refusal set is a
refusal set (never a default), the claim in the docstring is scoped to what was measured, and
the whole thing reaches no endpoint — so no permission row moves.
"""
import socket

import pytest

import larkdocio.base as base_pkg
from larkdocio import permissions as perm
from larkdocio.base import record_permalink, table_url, view_url
from larkdocio.base.deep_link import BASE_DEEP_LINK_CLICK_MEASUREMENT
from larkdocio.common.url import NotADeepLink, parse_deep_link

#: The maintainer's own tenant host shape — a tenant subdomain the API domain cannot produce, which is
#: the whole reason the host is copied rather than composed.
TENANT = "https://your-domain.larksuite.com"
BASE_URL = f"{TENANT}/base/BaseTOKEN123"


# --------------------------------------------------------------------------- #
# AC1 — two pure builders, host as an INPUT.                                    #
# --------------------------------------------------------------------------- #

def test_ac1_table_url_reads_the_TENANT_HOST_and_the_APP_TOKEN_off_the_bases_own_url():
    assert table_url(BASE_URL, "tblvHhs6KA9QYNCo") == (
        "https://your-domain.larksuite.com/base/BaseTOKEN123?table=tblvHhs6KA9QYNCo")


def test_ac1_view_url_adds_the_view_and_optionally_the_record():
    assert view_url(BASE_URL, "tblvHhs6KA9QYNCo", "vewHtny0oX") == (
        f"{TENANT}/base/BaseTOKEN123?table=tblvHhs6KA9QYNCo&view=vewHtny0oX")
    assert view_url(BASE_URL, "tblA", "vewV", record="rec88HpEvHGLV4") == (
        f"{TENANT}/base/BaseTOKEN123?table=tblA&view=vewV&record=rec88HpEvHGLV4")


def test_ac1_the_host_is_COPIED_not_composed_so_no_API_DOMAIN_can_appear_by_itself():
    """The failure this function is built to avoid: minting `https://larksuite.com/base/…`,
    which is the API domain and not any tenant's host. Whatever host arrives is what leaves."""
    for host in ("https://your-domain.larksuite.com", "https://your-domain.feishu.cn",
                 "https://one.two.three.larksuite.com"):
        minted = table_url(f"{host}/base/TOK", "tbl1")
        assert minted.startswith(f"{host}/base/TOK?"), minted
    # and no host literal is hardcoded anywhere in the module
    import pathlib
    source = pathlib.Path(base_pkg.__file__).with_name("deep_link.py").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.split('"""')[::2] if line)  # strip the docstrings
    for api_domain in ("feishu.cn", "larksuite.com"):
        assert api_domain not in code, (
            f"{api_domain} appears in the module's CODE — the tenant host is an input")


def test_ac1_any_query_or_fragment_already_on_the_base_url_is_DROPPED():
    minted = table_url(f"{BASE_URL}?table=stale&from=space#frag", "tblNEW")
    assert minted == f"{BASE_URL}?table=tblNEW"


@pytest.mark.parametrize("bad_url", [
    "",
    None,
    "your-domain.larksuite.com/base/TOK",          # hostless / schemeless
    "http://your-domain.larksuite.com/base/TOK",   # not https
    "https:///base/TOK",                            # no netloc
    f"{TENANT}/sheets/TOK",                         # a spreadsheet, not a Base
    f"{TENANT}/docx/TOK",                           # a document, not a Base
    f"{TENANT}/base",                               # no token segment
    f"{TENANT}/base/TOK/extra",                     # not a /base/<token> shape
    "BaseTOKEN123",                                 # a bare app_token carries no host
])
def test_ac1_a_url_that_cannot_supply_a_HOST_AND_A_TOKEN_is_a_REFUSAL_never_a_default(bad_url):
    with pytest.raises(ValueError):
        table_url(bad_url, "tbl1")
    with pytest.raises(ValueError):
        view_url(bad_url, "tbl1", "vew1")


@pytest.mark.parametrize("call", [
    lambda: table_url(BASE_URL, ""),
    lambda: table_url(BASE_URL, None),
    lambda: view_url(BASE_URL, "", "vew1"),
    lambda: view_url(BASE_URL, "tbl1", ""),
    lambda: view_url(BASE_URL, "tbl1", None),
    lambda: view_url(BASE_URL, "tbl1", "vew1", record=""),
])
def test_ac1_an_empty_id_is_a_REFUSAL_never_a_link_with_a_blank_parameter(call):
    with pytest.raises(ValueError):
        call()


def test_ac1_the_refusal_NAMES_the_function_and_the_input_it_refused():
    with pytest.raises(ValueError) as refusal:
        table_url(f"{TENANT}/sheets/TOK", "tbl1")
    assert "table_url" in str(refusal.value) and "/sheets/TOK" in str(refusal.value)


def test_ac1_ZERO_API_CALLS_no_client_is_constructed_and_no_transport_is_patched(monkeypatch):
    """The proof is by construction, not by mocking: any socket at all raises, and nothing in
    this test builds a client or replaces a transport."""
    def _no_network(*args, **kwargs):
        raise AssertionError("a Base deep-link builder opened a socket")

    monkeypatch.setattr(socket, "socket", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)
    assert table_url(BASE_URL, "tbl1")
    assert view_url(BASE_URL, "tbl1", "vew1", record="rec1")


# --------------------------------------------------------------------------- #
# AC2 — the claim is scoped to what was measured.                               #
# --------------------------------------------------------------------------- #

#: Words that would turn a one-day, one-tenant click into a promise about the world.
_UNIVERSALITY = (
    "always", "permanent", "guaranteed", "forever", "every client", "any client",
    "every tenant", "all tenants", "will continue", "never changes",
)


@pytest.mark.parametrize("doc", [
    BASE_DEEP_LINK_CLICK_MEASUREMENT, table_url.__doc__, view_url.__doc__])
def test_ac2_the_measurement_carries_its_DATE_its_CLIENT_and_its_ONE_TENANT_scope(doc):
    assert "2026-08-17" in doc
    assert "one tenant" in doc
    assert "Lark web client" in doc


@pytest.mark.parametrize("doc", [
    BASE_DEEP_LINK_CLICK_MEASUREMENT, table_url.__doc__, view_url.__doc__])
def test_ac2_the_NON_FIRST_TABLE_method_note_and_WHY_IT_MATTERS_survive(doc):
    """Without it the reading is not trustworthy: on a first table with one view a correct
    navigation and a default landing are indistinguishable — which is how the earlier click
    was a false negative."""
    assert "non-first" in doc.lower()
    assert "only view" in doc and "false negative" in doc


@pytest.mark.parametrize("doc", [
    BASE_DEEP_LINK_CLICK_MEASUREMENT, table_url.__doc__, view_url.__doc__])
def test_ac2_the_ID_STABILITY_finding_is_stated_WITH_its_span_and_its_one_base_scope(doc):
    assert "ten days" in doc
    assert "one Base" in doc


@pytest.mark.parametrize("doc", [
    BASE_DEEP_LINK_CLICK_MEASUREMENT, table_url.__doc__, view_url.__doc__])
def test_ac2_the_unmeasured_axes_are_ENUMERATED_and_nothing_universal_is_promised(doc):
    assert "UNMEASURED" in doc
    for axis in ("mobile", "desktop", "any other tenant"):
        assert axis in doc, f"the unmeasured axis {axis!r} is not enumerated"
    lowered = doc.lower()
    for word in _UNIVERSALITY:
        assert word not in lowered, f"{word!r} promises more than one day on one tenant"


# --------------------------------------------------------------------------- #
# AC3 — `record=` rides, carrying its recommendation.                           #
# --------------------------------------------------------------------------- #

def test_ac3_the_record_link_is_mintable_and_its_grammar_is_the_measured_one():
    assert view_url(BASE_URL, "tblA", "vewV", record="rec1").endswith(
        "?table=tblA&view=vewV&record=rec1")


@pytest.mark.parametrize("doc", [
    BASE_DEEP_LINK_CLICK_MEASUREMENT, view_url.__doc__])
def test_ac3_the_docstring_names_record_permalink_as_the_DURABLE_FIRST_CHOICE(doc):
    assert "record_permalink" in doc
    assert "minted by Lark" in doc
    assert "byte-identical across a week" in doc


def test_ac3_the_recommendation_points_at_a_REAL_shipped_function():
    assert callable(record_permalink)
    assert record_permalink.__module__ == "larkdocio.base.permalink"


def test_ac3_the_new_names_do_not_collide_with_the_shipped_permalinks_meaning():
    """`record_permalink` is fetched and server-minted; these are composed. A composed builder
    called `record_permalink`-anything would blur exactly the distinction AC3 protects."""
    for name in ("table_url", "view_url"):
        assert "permalink" not in name


# --------------------------------------------------------------------------- #
# AC4 — no API call, therefore no permission row. The guard is ASKED.           #
# --------------------------------------------------------------------------- #

def test_ac4_the_permissions_registrys_OWN_derivation_says_these_reach_NO_endpoint():
    """`endpoints_of` is the derivation the bidirectional coverage guard keys on: an operation
    with a non-empty endpoint set and no row reddens. Both builders derive the empty set, so
    there is nothing to cover — asked, not assumed."""
    assert perm.endpoints_of(table_url) == ()
    assert perm.endpoints_of(view_url) == ()


def test_ac4_the_coverage_guard_is_still_green_with_NO_row_added():
    gaps = perm.coverage_gaps()
    assert not gaps.uncovered and not gaps.orphans, gaps


# --------------------------------------------------------------------------- #
# AC5 — the superseded `parse_deep_link` clause: reason preserved, behaviour    #
#       pinned unchanged.                                                       #
# --------------------------------------------------------------------------- #

def test_ac5_the_now_false_UNVERIFIED_justification_no_longer_ships():
    doc = parse_deep_link.__doc__
    assert "it is unverified" not in doc, (
        "the grammar was click-measured on 2026-08-17; the old reason may not stand")


def test_ac5_the_reason_is_PRESERVED_AS_DATED_HISTORY_and_the_new_one_is_stated():
    doc = parse_deep_link.__doc__
    assert "unverified" in doc and "2026-08-17" in doc, (
        "the superseded reason is kept as dated history, not struck")
    assert "table_url" in doc and "view_url" in doc, (
        "the docstring must point at the builders that now mint the grammar")
    assert "extending this parse" in doc, (
        "the honest current reason — extending the parse is a separate change — is missing")


@pytest.mark.parametrize("url", [
    f"{BASE_URL}?table=tblA",
    f"{BASE_URL}?table=tblA&view=vewV",
    f"{BASE_URL}?table=tblA&view=vewV&record=rec1",
])
def test_ac5_CHARACTERIZATION_the_base_query_form_still_returns_NotADeepLink(url):
    """Behaviour unchanged, pinned: a later parse extension must be a deliberate act that
    re-writes this test, not a side effect of someone widening the grammar table."""
    assert isinstance(parse_deep_link(url), NotADeepLink)


def test_ac5_the_builders_own_output_round_trips_to_NotADeepLink_MEASURED():
    for minted in (table_url(BASE_URL, "tblA"), view_url(BASE_URL, "tblA", "vewV")):
        assert isinstance(parse_deep_link(minted), NotADeepLink), minted


# --------------------------------------------------------------------------- #
# AC6 — exported beside the sibling public Base helpers.                        #
# --------------------------------------------------------------------------- #

def test_ac6_both_builders_are_exported_from_larkdocio_base_and_named_in_dunder_all():
    for name in ("table_url", "view_url"):
        assert hasattr(base_pkg, name), f"{name} is not re-exported from larkdocio.base"
        assert name in base_pkg.__all__, f"{name} is missing from larkdocio.base.__all__"
