"""The **docx** disposables ledger + zero-orphan close-out (LD-236).

The round-trip-editing spec's gate 3 says "zero orphans at close, with the ledger independently reconciled — the
``tests/sheets_write_harness.py`` pattern". That pattern is **Sheets-only**: its ``Ledger`` /
``close_out`` re-query through ``gateway.query_spreadsheet``. The docx ring had the same
discipline but only inline and once (``test_live_write_comment_op_gate.py`` § close-out: trash
the disposable, then re-fetch and require Lark to say it is gone). This module is that
discipline ported to the docx re-query seam and made reusable, so the four round-trip
arms all close out the same way and the proof is one implementation rather than four.

**The re-query seam is** :meth:`larkdocio.write.client.WriteClient.get_document` — the
whole-document meta read the engine already ships (it is where ``revision_id`` comes from), so
the audit needs no new endpoint and no new scope.

**Three outcomes, not two.** A ledgered id whose re-query *returns* a document still resolves:
an **orphan**, a leak, loud. One whose re-query raises a typed
:class:`~larkdocio.errors.LarkAPIError` is **gone**, and the code Lark answered with is
recorded as the evidence. Anything else — a socket error, a timeout — is **indeterminate**:
it is not a deletion, and calling it clean is exactly how a sweep goes quiet on the run where
the network was the problem. Only "no orphans **and** nothing indeterminate" is clean.

**Why the ledger is on disk.** It is the create-side record. A crash between create and
teardown still leaves the id on a list a human (or a later run) can sweep, which a variable
held in a test process does not.

This module lives in ``tests/`` on purpose: it provisions and destroys **test** documents, and
nothing a consumer runs needs it. It is not a ``test_*`` module and carries no test.
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from larkdocio.errors import LarkAPIError


class HarnessError(RuntimeError):
    """A provisioning failure: loud, and raised BEFORE anything is ledgered."""


class OrphanLeakError(AssertionError):
    """The close-out found a disposable that still resolves, or one it could not confirm."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Ledger:
    """A persisted JSON ledger of every disposable document a run created.

    One entry per create — ``{document_id, title, created_at, deleted, delete_code,
    deleted_at}`` — appended on create and updated on delete. A delete that failed leaves
    ``deleted=False`` with its ``delete_code``: the id is **flagged, never dropped**.
    """

    def __init__(self, path):
        self.path = Path(path)
        self._entries = self._read()

    def _read(self):
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return []

    def _flush(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._entries, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def record_create(self, document_id, title=""):
        self._entries.append({
            "document_id": document_id,
            "title": title,
            "created_at": _now(),
            "deleted": False,
            "delete_code": None,
            "deleted_at": None,
        })
        self._flush()

    def record_delete(self, document_id, code):
        """Mark ``document_id``'s delete outcome.

        ``deleted`` flips True only for ``code 0`` (Lark's own success), and once True it
        stays True — a best-effort second delete answering "already gone" must not un-delete
        the row. Any other code (or an exception string) leaves it False so the id stays on
        the sweep list; the close-out, not this flag, is what proves gone-ness.
        """
        for entry in self._entries:
            if entry["document_id"] == document_id:
                entry["deleted"] = bool(entry["deleted"]) or code in (0, "0")
                entry["delete_code"] = code
                entry["deleted_at"] = _now()
                break
        self._flush()

    def entries(self):
        return list(self._entries)

    def document_ids(self):
        return [entry["document_id"] for entry in self._entries]


@dataclass(frozen=True)
class Disposable:
    """One self-provisioned docx document: its id, its title, and the create response."""

    document_id: str
    title: str
    created: dict


@contextmanager
def disposable(write_client, ledger, *, title=None, folder_token=None):
    """Create a disposable document, yield a :class:`Disposable`, ALWAYS delete it.

    ``folder_token`` is **where** the disposable goes. Omitted, it is read from
    ``LARKDOCIO_DISPOSABLES_FOLDER`` and the caller **SKIPS LOUDLY** when that is unset — never
    a fall-back to the application's own space, which no human interface can browse and whose
    trash cannot be listed. The house half of the caller-supplied-destination rule: a rule the
    library states and its own harness breaks is not a rule.

    The id is ledgered the moment it exists, so a crash between create and yield still
    leaves it on the sweep list. A create that came back without a ``document_id`` raises
    :class:`HarnessError` with **nothing ledgered** — no bogus yield, no orphan delete of an
    id that was never made. The ``finally`` delete is best-effort by design (the Drive delete's
    required scope is not established — see ``WriteClient.delete_document``); its outcome is
    recorded rather than asserted here, because the authority on gone-ness is
    :func:`close_out`'s independent re-query, not the delete's own return code.
    """
    if title is None:
        title = f"larkdocio-LD-236-disposable {int(time.time())}"
    if folder_token is None:
        import canary_support

        folder_token = canary_support.require_disposables_folder()
    created = write_client.create_document(title=title, folder_token=folder_token)
    document_id = (created or {}).get("document_id")
    if not document_id:
        raise HarnessError(
            f"disposable create failed — no document_id in the response; nothing ledgered. "
            f"resp={created!r}"
        )
    ledger.record_create(document_id, title)
    try:
        yield Disposable(document_id=document_id, title=title, created=created)
    finally:
        try:
            resp = write_client.delete_document(document_id)
            code = resp.get("code") if isinstance(resp, dict) else "ok"
        except Exception as exc:            # noqa: BLE001 — teardown must not mask the body
            # The API code, when there is one, is the part worth keeping: it is what says
            # WHY the trash failed (a missing Drive scope reads differently from a 404).
            code = f"error: code={getattr(exc, 'code', None)} {type(exc).__name__}: {exc}"
        ledger.record_delete(document_id, code)


@dataclass
class CloseOutReport:
    """The result of a close-out sweep: what is gone, what leaked, what is unknown."""

    ledger_count: int
    orphans: list = field(default_factory=list)
    clean: list = field(default_factory=list)
    indeterminate: list = field(default_factory=list)

    @property
    def all_clean(self):
        return not self.orphans and not self.indeterminate

    def raise_if_orphans(self):
        if self.orphans:
            ids = ", ".join(o["document_id"] for o in self.orphans)
            raise OrphanLeakError(
                f"close-out found {len(self.orphans)} orphan disposable(s) still resolving "
                f"(a leak): {ids}. Trash them (drive v1 delete) — the ledger is the "
                f"authoritative list."
            )
        if self.indeterminate:
            ids = ", ".join(i["document_id"] for i in self.indeterminate)
            raise OrphanLeakError(
                f"{len(self.indeterminate)} disposable(s) could not be confirmed gone "
                f"(the re-query failed for a reason that is not a deletion): {ids}. Re-run "
                f"the close-out — an unconfirmed id is not a clean one."
            )

    def to_dict(self):
        return {
            "ledger_count": self.ledger_count,
            "orphans": list(self.orphans),
            "clean": list(self.clean),
            "indeterminate": list(self.indeterminate),
            "all_clean": self.all_clean,
        }


def close_out(write_client, ledger):
    """Independently re-query EVERY ledgered document id and report what is really left.

    Every id is re-queried — including the ones the ledger already believes are deleted.
    Trusting the ledger's own flag would make the audit circular: the flag records what the
    delete *answered*, and this pass records what Lark *says now*.
    """
    orphans, clean, indeterminate = [], [], []
    for entry in ledger.entries():
        document_id = entry["document_id"]
        record = {"document_id": document_id, "title": entry.get("title"),
                  "delete_code": entry.get("delete_code")}
        try:
            write_client.get_document(document_id)
        except LarkAPIError as exc:
            record["recheck_code"] = exc.code
            clean.append(record)
        except Exception as exc:            # noqa: BLE001 — not a deletion; say so
            record["recheck_error"] = repr(exc)
            indeterminate.append(record)
        else:
            record["still_resolves"] = True
            orphans.append(record)
    return CloseOutReport(ledger_count=len(ledger.entries()), orphans=orphans,
                          clean=clean, indeterminate=indeterminate)
