"""Offline unit tests for the live-write harness scaffolding (LD-064, W0-S5).

NOT marked ``live_write`` — these run in the default ``pytest -q`` with no creds
and no network. They cover the offline-testable pieces of the W0 harness:

* AC2 — the ``live_write`` marker is registered and the default ``addopts``
  **deselects** it (so a plain ``pytest`` / ``verify.sh`` never runs the ring);
* AC3 — the write-creds availability helpers skip **loudly** (a clear message
  naming ``LARK_WRITE_APP_*``) when the write pair is unset — never a silent pass;
* AC5 — a static guard proving the harness writes **only against a doc it creates
  itself**: it never references ``LARKDOCIO_CANARY_DOC`` / ``LARKDOCIO_BLOCKZOO_DOC``
  or any hard-coded external doc URL, and it self-provisions via ``create_document``.

The live round-trip itself (AC4 — the binding W0 gate) is in
``tests/test_live_write_harness.py`` and only runs under ``pytest -m live_write``.
"""
from pathlib import Path

import canary_support


# --------------------------------------------------------------------------- #
# AC2 — the live_write marker is registered and deselected by default          #
# --------------------------------------------------------------------------- #

def test_live_write_marker_registered(pytestconfig):
    markers = pytestconfig.getini("markers")
    assert any(m.startswith("live_write:") for m in markers), (
        "expected a `live_write:` marker registered in "
        f"[tool.pytest.ini_options].markers; got {markers!r}"
    )


def test_default_addopts_deselects_live_write(pytestconfig):
    """The deselection stays — and it is now documented as the FIRST OF TWO fences.

    **The assertion below and its reason are unchanged** (LD-064 AC2: a plain ``pytest`` /
    ``verify.sh`` must never reach the tenant, and the deselection is what makes that true).
    What LD-537 supersedes is only the **sufficiency** conclusion that used to sit around it —
    that being deselected *was* the protection. It is not, because a deselection is a
    **selection** control and one typed ``-o addopts=""`` on an executing run clears it. That
    flag has been typed twice on this repository:

    * **wave 0** — ~3 permanent, unpurgeable drive media tokens minted; the ids were lost
      (LD-505's media guardrail closed that half);
    * **wave 2, 2026-08-20** — a full-suite ``--update-golden`` with the deselection cleared
      created **15 disposable Bases**; 14 self-deleted, one (``BaseGoneExample000000000001``)
      was still live when this was written and read as gone by 2026-08-25. Three self-reports and two complete QA reviews missed it.

    So **LD-537** added a second, independent fence on a different question — *consent*, checked
    at **execution** (``tests/live_write_fence.py``, guarded by
    ``tests/test_consent_fence_live_write.py``): a ``live_write``-marked test does not run
    unless ``LARKDOCIO_LIVE_WRITE_AUTHORIZED_BY`` names the issue that authorized it. Clearing
    ``addopts`` re-selects the ring; it does not arm it. **Both fences stay** — this one is
    defense in depth, not a superseded guard, and deleting it would remove the very control
    that keeps the default suite offline.
    """
    addopts = pytestconfig.getini("addopts")
    joined = " ".join(addopts) if isinstance(addopts, (list, tuple)) else str(addopts)
    assert "not live_write" in joined, (
        f"addopts must deselect live_write by default; got {joined!r}"
    )


# --------------------------------------------------------------------------- #
# AC3 — write-creds availability skips LOUDLY when LARK_WRITE_APP_* is unset    #
# --------------------------------------------------------------------------- #

def _set_write_creds(monkeypatch):
    monkeypatch.setenv("LARK_WRITE_APP_ID", "dummy_write_id")
    monkeypatch.setenv("LARK_WRITE_APP_SECRET", "dummy_write_secret")


def _clear_write_creds(monkeypatch):
    monkeypatch.delenv("LARK_WRITE_APP_ID", raising=False)
    monkeypatch.delenv("LARK_WRITE_APP_SECRET", raising=False)


def test_write_creds_available_true_when_pair_set(monkeypatch):
    _set_write_creds(monkeypatch)
    assert canary_support.write_creds_available() is True
    assert canary_support.live_write_missing_reason() is None


def test_write_creds_unavailable_when_unset(monkeypatch):
    _clear_write_creds(monkeypatch)
    assert canary_support.write_creds_available() is False
    reason = canary_support.live_write_missing_reason()
    assert reason is not None
    # The skip reason must name the write env vars (never a silent pass).
    assert "LARK_WRITE_APP" in reason


def test_write_creds_unavailable_when_half_configured(monkeypatch):
    # A lone id (no secret) is not usable — the write getter never mixes pairs.
    monkeypatch.setenv("LARK_WRITE_APP_ID", "dummy_write_id")
    monkeypatch.delenv("LARK_WRITE_APP_SECRET", raising=False)
    assert canary_support.write_creds_available() is False
    assert canary_support.live_write_missing_reason() is not None


def test_write_creds_never_fall_back_to_read_or_legacy(monkeypatch):
    # Read/legacy creds present but no write pair => still unavailable (write path
    # never borrows read/legacy credentials — the credential doctrine).
    _clear_write_creds(monkeypatch)
    monkeypatch.setenv("LARK_READ_APP_ID", "r_id")
    monkeypatch.setenv("LARK_READ_APP_SECRET", "r_secret")
    monkeypatch.setenv("LARK_APP_ID", "l_id")
    monkeypatch.setenv("LARK_APP_SECRET", "l_secret")
    assert canary_support.write_creds_available() is False


# --------------------------------------------------------------------------- #
# AC5 — the harness writes ONLY against a doc it creates itself                 #
# --------------------------------------------------------------------------- #

HARNESS_SRC = Path(__file__).resolve().parent / "test_live_write_harness.py"


def test_harness_self_provisions_its_own_doc():
    src = HARNESS_SRC.read_text(encoding="utf-8")
    assert "create_document" in src, (
        "the harness must self-provision its target doc via create_document"
    )


def test_harness_never_references_canary_or_zoo_or_external_docs():
    src = HARNESS_SRC.read_text(encoding="utf-8")
    forbidden = [
        "LARKDOCIO_CANARY_DOC",
        "CANARY_DOC_ENV",
        "canary_doc_url",
        "LARKDOCIO_BLOCKZOO_DOC",
        "BLOCKZOO_DOC_ENV",
        "blockzoo_doc_url",
        # no hard-coded external doc URL literal — the harness NEVER writes to a
        # pre-existing doc (never the read canary, never the zoo, never a real doc).
        "larksuite.com/docx/",
        "feishu.cn/docx/",
    ]
    for token in forbidden:
        assert token not in src, (
            f"the write harness must not reference {token!r} — it writes only "
            "against the doc it creates itself (AC5)."
        )
