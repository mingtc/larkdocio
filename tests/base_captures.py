"""The committed Base captures, loaded through the pinned SDK's own deserializer.

**One loader, two consumers.** ``tests/test_base_table.py`` built these three captures into
the whole-Base golden; LD-251's shipped-guide recipe needs the *same* Base behind an offline
read client, and a second loader beside this one would be two definitions of "the Scratch
Base" that can drift. So the loader moved here and both callers go through it.

Everything is a **real captured payload** (``tests/captures/base-study/captures/``) round-tripped through
``lark_oapi``'s deserializer, so an API drift reddens at deserialization rather than travelling
on as a plausible-looking ``None`` (PROJECT.md § Quality bar).

``p1-q0-01`` / ``p1-q0-02`` / ``p1-q0-03`` are one live recon of **one** Base, which is what
makes an offline whole-Base read possible at all.
"""
import json
from pathlib import Path

from lark_oapi.api.bitable.v1 import (
    GetAppResponse,
    ListAppTableFieldResponse,
    ListAppTableResponse,
    SearchAppTableRecordResponse,
)
from lark_oapi.core.json import JSON

CAPTURES = Path(__file__).resolve().parent.parent / "tests" / "captures" / "base-study" / "captures"


def capture(name):
    """One committed capture, as its own JSON."""
    return json.loads((CAPTURES / name).read_text(encoding="utf-8"))


def unmarshal(payload, cls):
    """A captured payload through the pinned SDK's deserializer."""
    return JSON.unmarshal(json.dumps(payload), cls)


def scratch_base():
    """``(app, tables, {table_id: (fields, records)})`` for the captured Scratch Base."""
    app = unmarshal(capture("p1-q0-01-app-meta.json")["response"], GetAppResponse).data.app
    tables = unmarshal(
        capture("p1-q0-02-tables.json")["response"], ListAppTableResponse).data.items
    per_table = {}
    for entry in capture("p1-q0-03-per-table.json")["per_table"]:
        per_table[entry["table_id"]] = (
            unmarshal(entry["fields"]["response"], ListAppTableFieldResponse).data.items,
            unmarshal(entry["records_search"]["response"],
                      SearchAppTableRecordResponse).data.items,
        )
    return app, tables, per_table
