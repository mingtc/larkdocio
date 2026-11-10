"""Shared test harness for the write-apply suites (LD-088).

The four offline write-apply test files
(``test_whole_paragraph_apply``, ``test_subspan_edits``, ``test_insert_delete_apply``,
``test_table_cell_apply``) plus the two table anchor-resolution files had each
re-authored the **same** fake-HTTP/throttle doubles and node/request/table builders
near-byte-identically — the exact multi-agent-drift pattern that ``tests/builders.py``
already blessed for the *read* parser tests (LD-039). The write tranche re-introduced
it; LD-088 consolidates it here.

Kept in a plain importable module beside ``builders.py``/``harness.py`` —
``conftest.py`` puts this ``tests/`` directory on ``sys.path`` — so a change to a
payload shape or the transport doubles is edited in exactly **one** place.

Scope (the ``builders.py`` doctrine): only the *byte-identical helper definitions*
live here — the fake transport, the node/request builders, the table structural
builders, and the request-introspection helpers. Each test keeps its own inline
DATA fixtures (``_spike_test5_table``, ``_merged_table``, ``_ambiguous_rows_table``,
``_mention_user``, and the create/delete-response payloads) wherever those literals
are the readable per-test spec.

Where signatures diverged across the copies, the **superset** is adopted here so
every prior call site produces a byte-identical object:

* ``_para(bid, text, inlines=None)`` — the ``test_subspan_edits`` superset.
* ``_heading(bid, text, level=1, children=None)`` — the ``test_insert_delete_apply``
  superset (``children or []`` matches ``HeadingNode``'s ``default_factory=list``).
* ``_block_payload(..., parent_id=None, style=None)`` — the
  ``test_insert_delete_apply`` superset (both extras omitted ⇒ the base payload).

The "exactly one place" claim above is **guarded, and it is guarded per name**
(LD-212). LD-088 consolidated the write-apply suites but the *sheets* suites went on
re-authoring the same transport doubles: ``_FakeHTTPResponse`` reached **nine**
module-level definitions under ``tests/`` — one sha256 across all nine — with copy #9
landing twenty-four hours after the refactor audit measured eight. So the claim is now
held by :mod:`tests.test_write_harness_double_ownership`, an AST scan over ``tests/**``
that reads its inventory off this module:

* :data:`OWNED_DOUBLES` — names for which **exactly one** module-level definition may
  exist under ``tests/``, here. A tenth copy anywhere in ``tests/**`` reddens the guard,
  named by file and line.
* :data:`DECLARED_DIVERGENT` — names deliberately left duplicated, each with its reason
  and the **exact** site inventory. ``StubOpener`` and ``_client`` are the two: their
  copies are genuinely different objects, not drift (measured 2026-07-31 —
  ``StubOpener`` is 9 definitions in 8 distinct shapes whose *recorded-field sets*
  differ, one of them recording a bare URL string rather than a dict; ``_client`` was 7
  definitions in 7 distinct shapes across **three** different client classes, no two
  alike, and is 10 as of LD-477). Collapsing either would mean rewriting call-site
  assertions, which is not a
  relocation — so the divergence is recorded rather than asserted away, and the guard
  still reddens on a NEW copy because the declared inventory would no longer match.

**Ruling on nested definitions** (LD-212, AC6): the guard inspects the **module body
only**. A double defined *inside a test function* is genuinely test-local and is not
the failure this guard exists to stop. ``tests/sheets_write_harness.py`` — the
credential-carrying **live-gate** harness — is a different module with a different job
and is deliberately not folded in here.
"""
import json

from larkdocio.common.transport import WriteTransport
from larkdocio.model import (
    HeadingNode,
    PageNode,
    TableCellNode,
    TableNode,
    Text,
    TextNode,
)
from larkdocio.write.client import WriteClient
from larkdocio.write.model import (
    Anchor,
    DeleteRequest,
    EditRequest,
    InsertRequest,
    NewParagraph,
    TableLocator,
)


# --------------------------------------------------------------------------- #
# model node builders                                                          #
# --------------------------------------------------------------------------- #

def _para(bid, text, inlines=None):
    return TextNode(content=inlines if inlines is not None else [Text(text)], block_id=bid)


def _heading(bid, text, level=1, children=None):
    return HeadingNode(level=level, content=[Text(text)], block_id=bid, children=children or [])


def _page(*children):
    return PageNode(title=[Text("Doc")], children=list(children), block_id="root")


# --------------------------------------------------------------------------- #
# request builders                                                             #
# --------------------------------------------------------------------------- #

def _req(quote, replacement="REPLACED", breadcrumb=()):
    return EditRequest(anchor=Anchor(quote=quote, breadcrumb=breadcrumb), replacement=replacement)


def _insert(quote, position, texts, *, breadcrumb=()):
    return InsertRequest(
        reference=Anchor(quote=quote, breadcrumb=breadcrumb),
        position=position,
        content=tuple(NewParagraph(t) for t in texts),
    )


def _delete(quote, *, breadcrumb=()):
    return DeleteRequest(target=Anchor(quote=quote, breadcrumb=breadcrumb))


# --------------------------------------------------------------------------- #
# table structural builders — a cell wraps an INNER text block with its own id  #
# (real docx: cell type 32 → child text block type 2; patch targets the inner)  #
# --------------------------------------------------------------------------- #

def _cell(bid, text):
    return TableCellNode(
        children=[TextNode(content=[Text(text)], block_id=f"{bid}__t")],
        block_id=bid,
    )


def _table(bid, rows, *, header_row=True, merges=None):
    """Build a TableNode. ``rows`` is a list of rows; each row is a list of
    ``(cell_block_id, text)`` pairs. ``col_size`` is the first row's width; every
    flat cell is a :class:`TableCellNode`. ``merges`` (optional) is the flat
    ``(row_span, col_span)`` list parallel to the flattened cells."""
    col_size = len(rows[0])
    cells = []
    for row in rows:
        for (cid, text) in row:
            cells.append(_cell(cid, text))
    return TableNode(
        cells=cells,
        col_size=col_size,
        header_row=header_row,
        merges=list(merges or []),
        block_id=bid,
    )


def _treq(row_key, *, column_header=None, column_index=None, breadcrumb=(), replacement="NEW"):
    loc = TableLocator(
        row_key=row_key,
        column_header=column_header,
        column_index=column_index,
        breadcrumb=breadcrumb,
    )
    return EditRequest(anchor=loc, replacement=replacement)


# --------------------------------------------------------------------------- #
# raw live-block payloads                                                       #
# --------------------------------------------------------------------------- #

def _run(content, **style):
    """One read ``text_run`` element; ``style`` kwargs become its text_element_style."""
    el = {"text_run": {"content": content}}
    if style:
        el["text_run"]["text_element_style"] = style
    return el


def _block_payload(block_id, elements, *, block_type=2, key="text", parent_id=None, style=None):
    """A ``get_block`` HTTP payload: ``{code, data:{block:{... type key:{elements[,style]}}}}``.

    ``parent_id`` / ``style`` are the insert/delete superset — omit both and the
    payload is byte-identical to the whole-paragraph/subspan/table-cell base form.
    """
    container = {"elements": elements}
    if style is not None:
        container["style"] = style
    block = {"block_id": block_id, "block_type": block_type, key: container}
    if parent_id is not None:
        block["parent_id"] = parent_id
    return {"code": 0, "data": {"block": block}}


def _parent_payload(block_id, children_ids, *, block_type=1):
    """A ``get_block`` payload for a container block carrying an ordered ``children`` list.

    The **live parent** read: both block-level write paths locate their child index off this
    ordered list rather than any offline ordinal — delete always did, and since LD-453 insert
    does too — so a suite driving either needs one of these queued after the target read.
    Promoted here at LD-453 (it was byte-identical in three files, and the fix made a fourth
    copy the alternative).
    """
    return {"code": 0, "data": {"block": {
        "block_id": block_id, "block_type": block_type, "children": list(children_ids),
    }}}


def _patch_ok():
    return {"code": 0, "data": {"block": {"block_id": "x"}}}


# --------------------------------------------------------------------------- #
# fake HTTP + clock doubles (no network)                                        #
# --------------------------------------------------------------------------- #

class FakeClock:
    """Deterministic monotonic clock: ``sleep`` advances ``now`` by the slept dt."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, dt):
        self.sleeps.append(dt)
        self.now += dt


class _FakeHTTPResponse:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()

    def read(self):
        return self._b


class StubOpener:
    """Records each urllib request and returns the next queued payload (by count)."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.requests = []

    def __call__(self, req, timeout=30):
        body = json.loads(req.data.decode()) if req.data else None
        self.requests.append({
            "method": req.get_method(),
            "url": req.full_url,
            "body": body,
        })
        return _FakeHTTPResponse(self._payloads[len(self.requests) - 1])


class RoutingOpener:
    """A ``urlopen`` double that answers by **method + path**, never by call count.

    :class:`StubOpener` hands back the *n*-th queued payload for the *n*-th call, which is
    exactly right for a fixed call sequence and desyncs the moment a batch makes a
    different number of calls than the test imagined (a refusal that skips a read, a batch
    whose length is the thing under test). This one routes instead — the docx document
    meta, ``get_block``, ``create_children``, ``batch_delete`` and the element patch each
    have an answer — so a suite driving **whole batches** through the shipped
    ``dry_run`` → ``apply`` gate can vary the batch without re-queueing payloads.

    * ``blocks`` — ``block_id`` → the ``get_block`` payload (``_block_payload``). An id
      that is not there answers Lark's own ``1770002`` not-found body.
    * ``document_revisions`` — the ``revision_id`` values the meta read returns, one per
      read (the last repeats). Two different values is how "the document drifted between
      plan and apply" is injected.
    * ``created`` — the block ids handed back by ``create_children``, consumed in order;
      when it runs out, ids are generated (``created-1``, ``created-2``, …) so a create of
      any width answers.

    Every call is recorded on :attr:`calls` as ``{"method", "path", "body"}``, and
    :attr:`writes` is the subset that mutates — so "zero writes" is a measurement.
    """

    WRITE_METHODS = ("POST", "PATCH", "DELETE", "PUT")

    def __init__(self, *, blocks=None, document_revisions=(), created=()):
        self.blocks = dict(blocks or {})
        self._revisions = list(document_revisions)
        self._created = list(created)
        self.calls = []
        self.meta_reads = 0

    @property
    def writes(self):
        return [c for c in self.calls if c["method"] in self.WRITE_METHODS]

    @property
    def reads(self):
        return [c for c in self.calls if c["method"] == "GET"]

    def of(self, method, needle=""):
        return [c for c in self.calls if c["method"] == method and needle in c["path"]]

    def _next_revision(self):
        self.meta_reads += 1
        if not self._revisions:
            return None
        return self._revisions[min(self.meta_reads - 1, len(self._revisions) - 1)]

    def _new_id(self, n):
        out = []
        for _ in range(n):
            out.append(self._created.pop(0) if self._created
                       else f"created-{len(self.blocks) + len(out) + 1}")
        return out

    def __call__(self, req, timeout=30):
        method, url = req.get_method(), req.full_url
        path = url.split(".com", 1)[-1]
        body = json.loads(req.data.decode()) if req.data else None
        self.calls.append({"method": method, "path": path, "body": body})
        if method == "GET":
            if "/blocks/" not in path:                       # the document meta read
                document_id = path.rsplit("/documents/", 1)[-1].split("?")[0]
                return _FakeHTTPResponse({"code": 0, "data": {"document": {
                    "document_id": document_id,
                    "revision_id": self._next_revision(),
                    "title": "routing doc",
                }}})
            block_id = path.rsplit("/blocks/", 1)[-1].split("?")[0]
            payload = self.blocks.get(block_id)
            if payload is None:
                return _FakeHTTPResponse(
                    {"code": 1770002, "msg": f"block {block_id} not found"}
                )
            return _FakeHTTPResponse(payload)
        if method == "POST" and path.endswith("/children"):
            children = (body or {}).get("children") or []
            ids = self._new_id(len(children))
            return _FakeHTTPResponse({"code": 0, "data": {
                "children": [{"block_id": i} for i in ids],
                "document_revision_id": 99,
            }})
        return _FakeHTTPResponse(_patch_ok())


class LiveTreeOpener:
    """A ``urlopen`` double backed by a **mutable** document tree — the live-document double.

    :class:`RoutingOpener` answers every read out of a dict that its own writes never
    touch, so a call made **mid-batch** sees the tree as it was *before* that batch's
    earlier writes. That blind spot is precisely what let the same-parent multi-insert
    positional drift (LD-453) ship past a green suite: the engine's insert path could hand
    Lark a plan-time ordinal and no offline test could tell, because no offline double had
    a child order to get wrong.

    This one **applies** each write to its own tree — ``create_children`` splices the new
    ids into the parent's ordered child list at the requested ``index`` (``-1`` appends),
    ``descendant`` splices its ``children_id`` roots in the same way and mints a real id for
    every block of the subtree (LD-482), ``batch_delete`` removes the half-open child range —
    so a read issued between two writes returns what the live document would really hold, and
    the **final child order** is a measurable an assertion can name.

    Construct it from the parent→children map plus each block's text::

        LiveTreeOpener(children={"root": ["p1", "p2"]}, texts={"p1": "Alpha", "p2": "Beta"})

    ``root`` is the page node (block type 1); everything else is a paragraph (type 2)
    unless named in ``block_types``. New blocks created through ``create_children`` take
    their id from ``created`` (in order) or an auto id, and their text from the request's
    own payload, so :meth:`order` reads back the authored strings.

    Every call is recorded on :attr:`calls` as ``{"method", "path", "body"}``.
    """

    WRITE_METHODS = ("POST", "PATCH", "DELETE", "PUT")

    def __init__(self, *, children, texts=None, block_types=None, created=()):
        self.children = {parent: list(kids) for parent, kids in children.items()}
        self.texts = dict(texts or {})
        self.block_types = dict(block_types or {})
        self._created = list(created)
        self._auto = 0
        self.calls = []

    # -- introspection ------------------------------------------------------- #

    @property
    def writes(self):
        return [c for c in self.calls if c["method"] in self.WRITE_METHODS]

    @property
    def reads(self):
        return [c for c in self.calls if c["method"] == "GET"]

    def of(self, method, needle=""):
        return [c for c in self.calls if c["method"] == method and needle in c["path"]]

    def order(self, parent="root"):
        """The parent's live child **texts**, in order — the document as it now reads."""
        return [self.texts.get(bid, "") for bid in self.children.get(parent, ())]

    def index_of(self, block_id, parent="root"):
        return self.children.get(parent, []).index(block_id)

    # -- the tree ------------------------------------------------------------ #

    def _parent_of(self, block_id):
        for parent, kids in self.children.items():
            if block_id in kids:
                return parent
        return None

    def _block(self, block_id):
        block_type = self.block_types.get(block_id, 1 if block_id == "root" else 2)
        if block_type == 27:
            # AN IMAGE BLOCK CARRIES NO TEXT CONTAINER AT ALL, and the double has to say so
            # or a delete against one would be proved against a fiction. The real live
            # payload is exactly ``{"image": {"align", "height", "scale", "token",
            # "width"}}`` — no ``elements`` key anywhere, hence no quotable own text, which
            # is what makes ``AnchorById`` the only anchor a delete of one can use.
            # PROVENANCE, corrected by LD-528 (the citation here originally named LD-507's
            # capture, which records the DELETE and the same block/token but not the block's
            # five-key payload): the payload is quoted from **LD-506's** capture
            # ``dev/ld506-in-cell-image/captures/002-in-cell-image-raw-payload.json`` →
            # ``blocks_flat_route[10]``, which at the time of writing lived on an unlanded
            # branch of LD-506 and not on this one. The delete itself is LD-507's capture
            # ``tests/captures/ld507-image-block-delete/captures/001-image-block-delete.json``.
            block = {
                "block_id": block_id,
                "block_type": 27,
                "image": {"align": 2, "height": 1, "scale": 1,
                          "token": f"tok-{block_id}", "width": 1},
            }
        else:
            key = "page" if block_type == 1 else "text"
            block = {
                "block_id": block_id,
                "block_type": block_type,
                key: {"elements": [_run(self.texts.get(block_id, ""))]},
            }
        if block_id in self.children:
            block["children"] = list(self.children[block_id])
        parent = self._parent_of(block_id)
        if parent is not None:
            block["parent_id"] = parent
        return block

    def _new_id(self):
        if self._created:
            return self._created.pop(0)
        self._auto += 1
        return f"created-{self._auto}"

    def _text_of(self, payload):
        container = payload.get("text") or payload.get("heading1") or {}
        return "".join(
            (element.get("text_run") or {}).get("content", "")
            for element in container.get("elements", ())
        )

    def _provision_cells(self, table_id, payload):
        """Lark AUTO-PROVISIONS a table's cell family from its grid property (LD-135) — each
        type-32 cell wrapping one empty type-2 text block — and returns those cell ids on the
        create response. Reproduced here so the shipped create-then-fill route can run
        end to end against this double; ``{}`` for every other block type."""
        if payload.get("block_type") != 31:
            return {}
        prop = (payload.get("table") or {}).get("property") or {}
        cells = int(prop.get("row_size") or 0) * int(prop.get("column_size") or 0)
        cell_ids = []
        for _ in range(cells):
            cell_id = self._new_id()
            inner_id = self._new_id()
            self.block_types[cell_id] = 32
            self.block_types[inner_id] = 2
            self.texts[inner_id] = ""
            self.children[cell_id] = [inner_id]
            cell_ids.append(cell_id)
        self.children[table_id] = cell_ids
        return {"children": cell_ids}

    def _all_block_ids(self):
        ids = list(self.children.get("root", ()))
        seen, out = set(), []
        stack = ["root"]
        while stack:
            block_id = stack.pop(0)
            if block_id in seen:
                continue
            seen.add(block_id)
            out.append(block_id)
            stack.extend(self.children.get(block_id, ()))
        for block_id in list(self.texts) + ids:
            if block_id not in seen:
                seen.add(block_id)
                out.append(block_id)
        return out

    # -- the wire ------------------------------------------------------------ #

    def __call__(self, req, timeout=30):
        method, url = req.get_method(), req.full_url
        path = url.split(".com", 1)[-1]
        bare = path.split("?")[0]                             # the path without its query
        body = json.loads(req.data.decode()) if req.data else None
        self.calls.append({"method": method, "path": path, "body": body})

        if method == "GET":
            if bare.endswith("/blocks"):                      # the flat document block list
                return _FakeHTTPResponse({"code": 0, "data": {
                    "items": [self._block(b) for b in self._all_block_ids()],
                    "has_more": False,
                }})
            if "/blocks/" not in path:                        # the document meta read
                document_id = path.rsplit("/documents/", 1)[-1].split("?")[0]
                return _FakeHTTPResponse({"code": 0, "data": {"document": {
                    "document_id": document_id, "revision_id": 1, "title": "live tree",
                }}})
            block_id = path.rsplit("/blocks/", 1)[-1].split("?")[0]
            if block_id != "root" and self._parent_of(block_id) is None:
                return _FakeHTTPResponse(
                    {"code": 1770002, "msg": f"block {block_id} not found"}
                )
            return _FakeHTTPResponse({"code": 0, "data": {"block": self._block(block_id)}})

        if method == "POST" and bare.endswith("/children"):
            parent = bare.rsplit("/blocks/", 1)[-1].split("/children")[0]
            index = (body or {}).get("index", -1)
            kids = self.children.setdefault(parent, [])
            at = len(kids) if index is None or index < 0 else index
            new_ids, records = [], []
            for payload in (body or {}).get("children") or []:
                block_id = self._new_id()
                self.texts[block_id] = self._text_of(payload)
                self.block_types[block_id] = payload.get("block_type")
                new_ids.append(block_id)
                records.append({"block_id": block_id,
                                **self._provision_cells(block_id, payload)})
            self.children[parent] = kids[:at] + new_ids + kids[at:]
            return _FakeHTTPResponse({"code": 0, "data": {
                "children": records,
                "document_revision_id": 99,
            }})

        if method == "POST" and bare.endswith("/descendant"):
            # LD-482's one-call subtree route, applied to the tree the same way
            # ``create_children`` is: the ``children_id`` roots are spliced into the parent's
            # ordered child list at ``index``, and every descendant becomes a real block with
            # its temp-id children re-pointed at the ids this double minted. Modelled on the
            # measured response shape — ``block_id_relations`` (temp → real) plus the created
            # ``children`` (dev/table-row-boundary/captures/306-c1-descendant-subtree-10x3.json,
            # in the dev repo).
            parent = bare.rsplit("/blocks/", 1)[-1].split("/descendant")[0]
            index = (body or {}).get("index", -1)
            descendants = list((body or {}).get("descendants") or ())
            minted = {d.get("block_id"): self._new_id() for d in descendants}
            for payload in descendants:
                real = minted[payload.get("block_id")]
                self.block_types[real] = payload.get("block_type")
                self.texts[real] = self._text_of(payload)
                kids = [minted.get(k, k) for k in (payload.get("children") or ())]
                if kids:
                    self.children[real] = kids
            roots = [minted.get(t, t) for t in ((body or {}).get("children_id") or ())]
            kids = self.children.setdefault(parent, [])
            at = len(kids) if index is None or index < 0 else index
            self.children[parent] = kids[:at] + roots + kids[at:]
            return _FakeHTTPResponse({"code": 0, "data": {
                "block_id_relations": [
                    {"block_id": real, "temporary_block_id": temp}
                    for temp, real in minted.items()
                ],
                "children": [{"block_id": r} for r in roots],
                "document_revision_id": 99,
            }})

        if method == "DELETE" and bare.endswith("/children/batch_delete"):
            parent = bare.rsplit("/blocks/", 1)[-1].split("/children")[0]
            start, end = (body or {}).get("start_index"), (body or {}).get("end_index")
            kids = self.children.setdefault(parent, [])
            self.children[parent] = kids[:start] + kids[end:]
            return _FakeHTTPResponse({"code": 0, "data": {"document_revision_id": 100}})

        return _FakeHTTPResponse(_patch_ok())


class CountingTransport:
    """A transport spy: counts ``execute`` calls, delegates to the real one.

    Proves each op path actually routes through *a* transport (the throttle
    chokepoint) — no op builds+sends a request behind the transport's back.
    """

    def __init__(self, inner):
        self._inner = inner
        self.executes = 0

    def execute(self, call):
        self.executes += 1
        return self._inner.execute(call)


def _client(opener, clock=None, max_writes_per_sec=3):
    clock = clock or FakeClock()
    transport = WriteTransport(
        max_writes_per_sec=max_writes_per_sec, time_fn=clock.time, sleep_fn=clock.sleep
    )
    return WriteClient(
        "app", "secret", "larksuite.com",
        transport=transport, urlopen=opener, token_fetcher=lambda *a, **k: "t-test",
    )


# --------------------------------------------------------------------------- #
# request-introspection helpers                                                 #
# --------------------------------------------------------------------------- #

def _methods(opener):
    return [r["method"] for r in opener.requests]


def _by_method(opener, method):
    return [r for r in opener.requests if r["method"] == method]


# --------------------------------------------------------------------------- #
# LD-212 — the transport-double ownership inventory (read by the guard)         #
# --------------------------------------------------------------------------- #

#: Names this module OWNS: exactly ONE module-level definition of each may exist
#: anywhere under ``tests/``, and it must be the one here. Import it — do not
#: re-author it. Held by ``tests/test_write_harness_double_ownership.py``.
OWNED_DOUBLES = (
    "CountingTransport",
    "FakeClock",
    "LiveTreeOpener",
    "RoutingOpener",
    "_FakeHTTPResponse",
    "_parent_payload",
)

#: Names deliberately left duplicated, with the reason and the EXACT site inventory
#: (``tests/``-relative paths). Not a licence to keep copying: the guard compares the
#: tree against this list, so a new copy in a new file reddens until it is either
#: pointed at the harness or added here with its own reason.
DECLARED_DIVERGENT = {
    "StubOpener": {
        "reason": (
            "9 definitions in 8 distinct shapes: the recorded-field set genuinely "
            "differs per suite (url only / +method / +body / +auth), one flavour "
            "records a bare URL string rather than a dict, and one carries a "
            "``query_of`` helper. A single superset would change what call sites "
            "assert against, which is a behaviour edit, not a relocation (LD-212)."
        ),
        "sites": (
            "test_sheets_client.py",
            "test_sheets_dimension_properties.py",
            "test_sheets_extent.py",
            "test_sheets_filter_read.py",
            "test_sheets_freeze_panes.py",
            "test_sheets_lifecycle.py",
            "test_sheets_write_client.py",
            "test_write_client.py",
            "write_harness.py",
        ),
    },
    "_client": {
        "reason": (
            "10 definitions in 10 distinct shapes across THREE different client "
            "classes (SheetsReadClient / SheetsWriteClient / WriteClient) with "
            "different keyword surfaces. A single factory over three classes would "
            "be a ``**kwargs`` mush; the shapes are named per suite instead (LD-212). "
            "The eighth (LD-383) stubs the token fetcher AND serves a QUEUE of "
            "payloads in call order, because the walk it drives makes several reads "
            "per test and each must answer differently. The ninth (LD-405) is that "
            "queue-serving shape plus one thing the eighth has no use for: it hands the "
            "recorded url list back on the client, because the front door's "
            "options-pass-through test asserts on the QUERY STRING the walk produced. "
            "The tenth (LD-477) is the narrowest of them all — a READ client with no "
            "rate limiter and no keyword surface at all, because its suite's central "
            "claim is that the visibility answer costs exactly ONE request, and any "
            "extra construction knob is a way for a second call to enter unnoticed."
        ),
        "sites": (
            "test_sheets_client.py",
            "test_sheets_dimension_properties.py",
            "test_sheets_extent.py",
            "test_sheets_filter_read.py",
            "test_sheets_ghost_tabs_skip_loudly.py",
            "test_sheets_hidden_tab_read_route.py",
            "test_sheets_read_spreadsheet_entry.py",
            "test_sheets_write_client.py",
            "test_write_client.py",
            "write_harness.py",
        ),
    },
}
