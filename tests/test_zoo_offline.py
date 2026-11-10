"""Offline unit tests for the block-zoo live ring (LD-044).

The zoo ring is the advisory sibling of the live read-canary (LD-003): it
mirrors the same skip-loudly-never-block machinery so future block-zoo
revisions harvest their fixtures the same way. These tests are NOT marked
``zoo`` (nor ``live``) — they run in the default ``pytest -q`` with no creds
and no network. They cover the offline-testable pieces of the ring:

* the ``zoo`` marker is registered (so ``pytest`` emits no unknown-marker
  warning and the zoo tests are deselectable);
* the default ``addopts`` deselects BOTH ``live`` and ``zoo`` (a plain
  ``pytest`` never touches the network);
* the ``LARKDOCIO_BLOCKZOO_DOC`` env plumbing (the ``canary_support`` helpers),
  including the optional ``LARKDOCIO_BLOCKZOO_WIKI`` companion var;
* the skip reason names the missing env var (never a silent pass).

The live assertion itself (a real ``--dump``-style read) lives in
``tests/test_zoo_ring.py`` and only runs under ``pytest -m zoo``. The ring is
**advisory, never binding** — nothing in ``verify.sh``/CI/QA blocks on the zoo
doc being reachable.
"""
import canary_support

_ENV_EXAMPLE = canary_support.REPO_ROOT / ".env.example"

# A syntactically valid disposable zoo-doc URL, used ONLY to prove the env
# plumbing offline; the live ring reads the real URL from the env
# (LARKDOCIO_BLOCKZOO_DOC), never from this literal.
ZOO_URL = "https://tenant.larksuite.com/docx/DocBlockZooExample000000001"


def test_env_example_documents_blockzoo_doc():
    # AC4: .env.example documents LARKDOCIO_BLOCKZOO_DOC beside the canary var.
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert canary_support.BLOCKZOO_DOC_ENV in text, (
        f".env.example must document {canary_support.BLOCKZOO_DOC_ENV}"
    )


def test_env_example_documents_optional_blockzoo_wiki():
    # AC4: the OPTIONAL companion var is documented (commented) too.
    text = _ENV_EXAMPLE.read_text(encoding="utf-8")
    assert canary_support.BLOCKZOO_WIKI_ENV in text, (
        f".env.example must document the optional {canary_support.BLOCKZOO_WIKI_ENV}"
    )




def test_zoo_marker_registered(pytestconfig):
    markers = pytestconfig.getini("markers")
    assert any(m.startswith("zoo:") for m in markers), (
        "expected a `zoo:` marker registered in "
        f"[tool.pytest.ini_options].markers; got {markers!r}"
    )


def test_default_addopts_deselects_live_and_zoo(pytestconfig):
    # A plain `pytest` must run neither the live canary nor the zoo ring — the
    # default -m expression deselects both markers.
    addopts = pytestconfig.getini("addopts")
    joined = " ".join(addopts) if isinstance(addopts, (list, tuple)) else str(addopts)
    assert "not live" in joined, f"addopts must deselect live by default; got {joined!r}"
    assert "not zoo" in joined, f"addopts must deselect zoo by default; got {joined!r}"


def test_blockzoo_doc_url_reads_env(monkeypatch):
    monkeypatch.setenv(canary_support.BLOCKZOO_DOC_ENV, ZOO_URL)
    assert canary_support.blockzoo_doc_url() == ZOO_URL


def test_blockzoo_doc_url_none_when_unset(monkeypatch):
    monkeypatch.delenv(canary_support.BLOCKZOO_DOC_ENV, raising=False)
    assert canary_support.blockzoo_doc_url() is None


def test_blockzoo_doc_url_none_when_blank(monkeypatch):
    # A blank/whitespace value is treated as unset (so the zoo ring skips).
    monkeypatch.setenv(canary_support.BLOCKZOO_DOC_ENV, "   ")
    assert canary_support.blockzoo_doc_url() is None


def test_blockzoo_wiki_url_reads_env(monkeypatch):
    # The optional companion var for the wiki-only types (42/51).
    wiki = "https://tenant.larksuite.com/wiki/SOMEwikiTOKEN"
    monkeypatch.setenv(canary_support.BLOCKZOO_WIKI_ENV, wiki)
    assert canary_support.blockzoo_wiki_url() == wiki


def test_blockzoo_wiki_url_none_when_unset(monkeypatch):
    monkeypatch.delenv(canary_support.BLOCKZOO_WIKI_ENV, raising=False)
    assert canary_support.blockzoo_wiki_url() is None


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


def test_blockzoo_available_true_with_url_and_creds(monkeypatch):
    monkeypatch.setenv(canary_support.BLOCKZOO_DOC_ENV, ZOO_URL)
    _set_read_creds(monkeypatch)
    assert canary_support.blockzoo_available() is True
    assert canary_support.blockzoo_missing_reason() is None


def test_blockzoo_unavailable_without_url(monkeypatch):
    monkeypatch.delenv(canary_support.BLOCKZOO_DOC_ENV, raising=False)
    _set_read_creds(monkeypatch)
    assert canary_support.blockzoo_available() is False
    # The skip reason must name the missing env var (never a silent pass).
    assert canary_support.BLOCKZOO_DOC_ENV in canary_support.blockzoo_missing_reason()


def test_blockzoo_unavailable_without_creds(monkeypatch):
    monkeypatch.setenv(canary_support.BLOCKZOO_DOC_ENV, ZOO_URL)
    _clear_read_creds(monkeypatch)
    assert canary_support.blockzoo_available() is False
    assert canary_support.blockzoo_missing_reason() is not None
