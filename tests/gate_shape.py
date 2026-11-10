"""The always-on half of the round-trip ring's discipline (LD-236).

Each of the four live round-trip arms has a ``*_offline.py`` companion, and every companion
asks the same five questions of its gate's **source text** before asking its own: is it in the
ring, does it skip loudly, does it provision its own disposable, does it tear down in a
``finally``, and does it close out with an independent re-query. Those five are written here
once so the four companions differ only where the arms differ.

A source-text check is a weak proof of behaviour and a strong proof of **discipline**: it
cannot tell you the round trip works (that is what the credential-gated arm is for), but it
reddens on an ordinary ``pytest -q`` the moment somebody deletes the teardown, drops the skip,
or points an arm at a document it did not create.
"""
from pathlib import Path

TESTS = Path(__file__).resolve().parent

#: Every way a gate could name a document it did not create. The ring's rule is absolute: the
#: only document id an arm ever holds is one ``create_document`` just returned.
FORBIDDEN_TARGETS = (
    "LARKDOCIO_CANARY_DOC",
    "canary_doc_url",
    "blockzoo",
    "BLOCKZOO",
    "scratch_sheet_url",
    "/docx/",
    "/wiki/",
)


def gate_source(name):
    path = TESTS / name
    assert path.exists(), f"the ring member {name} must exist (LD-236)"
    return path.read_text(encoding="utf-8")


def assert_in_the_ring(src, name):
    """It carries the ring's marker as a MODULE-LEVEL statement — which is also what puts it
    in ``capabilities()``' docx-write gate coverage (the truth set is read off exactly that)."""
    assert any(line.startswith("pytestmark = pytest.mark.live_write")
               for line in src.splitlines()), (
        f"{name} must carry `pytestmark = pytest.mark.live_write` as a module-level statement "
        f"— that is what deselects it by default AND what joins it to the docx-write ring.")


def assert_skips_loudly(src, name):
    assert "live_write_missing_reason" in src and "pytest.skip(" in src, (
        f"{name} must gate on canary_support.live_write_missing_reason() and pytest.skip(...) "
        f"— absent credentials SKIP, never silently pass.")


def assert_self_provisions(src, name):
    """The document is one the arm creates itself, and there is no other way it gets one."""
    assert "docx_ledger.disposable(" in src, (
        f"{name} must take its document from docx_ledger.disposable(...), which creates it, "
        f"ledgers it and trashes it — a gate that gets its id any other way is not disposable-"
        f"only (the round-trip-editing spec § gate 3).")
    for needle in FORBIDDEN_TARGETS:
        assert needle not in src, (
            f"{name} names {needle!r} — the ring NEVER addresses the read canary, the block "
            f"zoo, a pre-existing scratch doc or any document it did not create.")


def assert_tears_down_in_a_finally(src, name):
    assert "finally:" in src and "rt.empty_document(" in src, (
        f"{name} must restore its document in a `finally` (rt.empty_document) so nothing "
        f"persists even on a mid-round-trip failure.")


def assert_closes_out_by_re_query(src, name):
    assert "docx_ledger.close_out(" in src and "raise_if_orphans()" in src, (
        f"{name} must close out by INDEPENDENTLY re-querying every ledgered id and raising on "
        f"an orphan — a best-effort delete is not a zero-orphan proof.")


def assert_ring_discipline(name):
    """All five, for one gate file. Returns the source so a companion can add its own."""
    src = gate_source(name)
    assert_in_the_ring(src, name)
    assert_skips_loudly(src, name)
    assert_self_provisions(src, name)
    assert_tears_down_in_a_finally(src, name)
    assert_closes_out_by_re_query(src, name)
    return src
