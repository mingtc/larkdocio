"""Drive enumeration fixtures — DERIVED FROM THE COMMITTED CAPTURES, never hand-mocked.

PROJECT.md § Quality bar: *"tests must pin real payload shapes (fixtures are deserialized
from actual API JSON, not hand-mocked dicts), so a drift reddens the suite instead of
silently corrupting output."* So every builder here **reads the spike's own capture files**
at call time rather than copying their contents into Python literals — a capture edited or
deleted reddens the tests that stand on it.

Provenance, one line per builder (`tests/captures/drive-spike/captures/`):

* :func:`listing_capture` / :func:`listing_response` ← ``02-list-files-implicit-root.json``
  — the nine-field child shape and the ``has_more`` envelope.
* :func:`real_tree_pages` ← ``11-real-tree-walk.json`` — the maintainer's real tree, 35 children over
  4 levels in 7 listing calls, regrouped by ``parent_token`` into the per-folder listing
  responses that produced it.
* :func:`pagination_pages` ← ``12-pagination-continuation.json`` — the two-page continuation,
  its recorded ``next_page_token`` **shape** (135 chars, non-numeric) and the proven
  zero-overlap property. The token STRING itself was deliberately not captured (it is a live
  cursor over a real tenant tree), so it is synthesised **to the recorded shape** and that is
  said here rather than implied.
* :func:`refusal_response` ← ``04-list-files-invalid-folder.json`` (malformed token),
  ``13-wellformed-fake-folder.json`` (well-formed, nonexistent) and ``14-option-param.json``
  (a bad ``option`` value) — the three distinct causes Lark collapses onto ``1061002``.
* :func:`root_folder_meta_response` ← ``01-root-folder-meta.json``.
* :func:`metas_batch_query_response` ← ``06-metas-batch-query.json``.

The round-2 captures carry **pseudonymised** child tokens (``<tok:xxxxxxxx>``) because their
subject was a real tenant tree; that is exactly right for an offline fixture and is why the
tests here never assert a token's spelling, only its identity and its flow.
"""
import io
import json
import pathlib
import urllib.parse

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CAPTURES = REPO_ROOT / "tests" / "captures" / "drive-spike" / "captures"


def capture(name: str) -> dict:
    """One committed capture, parsed. The single door onto the evidence base."""
    path = CAPTURES / name
    assert path.exists(), f"the fixture's evidence is missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# The listing leg — capture 02.                                                #
# --------------------------------------------------------------------------- #

LISTING_CAPTURE = "02-list-files-implicit-root.json"

#: The nine fields the listing returns per child (spike § I.A, read off capture 02).
CHILD_FIELDS = (
    "token", "name", "type", "parent_token", "url",
    "shortcut_info", "created_time", "modified_time", "owner_id",
)


def listing_capture() -> dict:
    return capture(LISTING_CAPTURE)


def listing_response() -> dict:
    """The captured ``GET /drive/v1/files`` response body, verbatim."""
    return listing_capture()["response"]


def listing_children() -> list:
    return listing_response()["data"]["files"]


def page(children, *, has_more=False, next_page_token=None) -> dict:
    """A listing response envelope in the captured shape, around ``children``."""
    data = {"files": list(children), "has_more": has_more}
    if next_page_token is not None:
        data["next_page_token"] = next_page_token
    return {"code": 0, "msg": "success", "data": data}


# --------------------------------------------------------------------------- #
# The real tree — capture 11, regrouped into the listings that produced it.     #
# --------------------------------------------------------------------------- #

REAL_TREE_CAPTURE = "11-real-tree-walk.json"


def real_tree() -> dict:
    return capture(REAL_TREE_CAPTURE)


def real_tree_root() -> str:
    return real_tree()["_root_folder"]


def real_tree_listings() -> dict:
    """``{folder_token: response}`` — the 7 single-page listings the walk consumed.

    Rebuilt from the capture's own ``nodes`` by grouping on ``parent_token``, so the fixture
    cannot drift from the tree that was actually walked: the folder set is derived from the
    nodes, not typed out.
    """
    tree = real_tree()
    by_parent: dict = {tree["_root_folder"]: []}
    for node in tree["nodes"]:
        if node["type"] == "folder":
            by_parent.setdefault(node["token"], [])
    for node in tree["nodes"]:
        child = {
            "token": node["token"],
            "name": node["name"],
            "type": node["type"],
            "parent_token": node["parent_token"],
            "url": node["url"],
            "shortcut_info": node["shortcut_info"],
            "modified_time": node["modified_time"],
        }
        by_parent.setdefault(node["parent_token"], []).append(child)
    return {token: page(children) for token, children in by_parent.items()}


# --------------------------------------------------------------------------- #
# Pagination — capture 12.                                                     #
# --------------------------------------------------------------------------- #

PAGINATION_CAPTURE = "12-pagination-continuation.json"


def pagination_capture() -> dict:
    return capture(PAGINATION_CAPTURE)


def opaque_page_token() -> str:
    """A ``next_page_token`` **synthesised to capture 12's recorded shape** — its length and
    its non-numeric-ness — because the live cursor string itself was deliberately not
    captured. Nothing in the client may depend on the spelling; that is the point.
    """
    shape = pagination_capture()["next_page_token_shape"]
    assert shape["is_numeric"] is False
    alphabet = "MzA9-_bQ7xTfLpV0KsRnYcHdEuWjG"
    token = "".join(alphabet[i % len(alphabet)] for i in range(shape["len"]))
    assert len(token) == shape["len"] and not token.isdigit()
    return token


def pagination_pages(folder_token="fldrPAGED"):
    """``(page1, page2, expected_tokens)`` for the captured 2 + 2 continuation.

    Zero overlap between the pages and *page 1 + page 2 = the folder's full child set* are
    the capture's own proven properties (``overlap_between_pages: []``), so they are carried
    into the fixture rather than re-invented.
    """
    cap = pagination_capture()
    assert cap["overlap_between_pages"] == []
    first = [_child(tok, folder_token) for tok in cap["page1_tokens"]]
    second = [_child(tok, folder_token) for tok in cap["page2_tokens"]]
    return (
        page(first, has_more=True, next_page_token=opaque_page_token()),
        page(second, has_more=False),
        [c["token"] for c in first + second],
    )


def _child(token, parent_token, child_type="docx"):
    return {
        "token": token,
        "name": f"name of {token}",
        "type": child_type,
        "parent_token": parent_token,
        "url": f"https://example.larksuite.com/docx/{token}",
        "shortcut_info": None,
        "created_time": "1785886310",
        "modified_time": "1785888054",
        "owner_id": "<redacted:person-id>",
    }


child_payload = _child


# --------------------------------------------------------------------------- #
# The refusals — captures 04 / 13 / 14 — and the two raw legs — 01 / 06.        #
# --------------------------------------------------------------------------- #

#: ``name -> (capture file, what that capture's cause was)``. All three answer 1061002.
REFUSAL_CAPTURES = {
    "malformed_token": ("04-list-files-invalid-folder.json", "a malformed folder token"),
    "wellformed_but_nonexistent": (
        "13-wellformed-fake-folder.json",
        "a well-formed token of the identical 27-char shape for a folder that does not exist",
    ),
    "bad_option_value": ("14-option-param.json", "a bad `option` parameter value"),
}


def refusal_response(cause="malformed_token") -> dict:
    """The captured ``1061002`` refusal body for one of the three distinct causes."""
    name, _why = REFUSAL_CAPTURES[cause]
    cap = capture(name)
    if "response" in cap:
        return cap["response"]
    # capture 14 records one result object per probed `option` value.
    probe = cap["obj_type"]
    return {"code": probe["code"], "msg": probe["msg"], "error": {"log_id": "captured"}}


def not_found_response() -> dict:
    """The drive family's *other* code — ``1061003``, the captured not-found
    (``src/larkdocio/base/media.py``). Kept distinct on purpose: conflating it with
    ``1061002`` is the exact defect AC5 forbids."""
    return {"code": 1061003, "msg": "file not found", "error": {"log_id": "captured"}}


# --------------------------------------------------------------------------- #
# The dispatch dry-run — capture 15 — the maintainer-tree shape LD-325 reproduces.       #
# --------------------------------------------------------------------------- #

DISPATCH_DRY_RUN_CAPTURE = "15-dispatch-dry-run.json"


def dispatch_dry_run() -> dict:
    return capture(DISPATCH_DRY_RUN_CAPTURE)


def dispatch_dry_run_children() -> list:
    """The maintainer tree as ``FolderChild`` objects, built from capture 15's own rows.

    The capture records 35 rows — 27 ``docx``, 6 ``folder``, 2 ``file`` — with each row's
    ``name`` and ``type``. That is exactly what a *pure* dispatcher routes on, so the fixture
    carries no more than the capture did: a ``url`` is synthesised only for the ``docx`` rows
    (the listing hands one over for a real document), and nothing else is invented.
    """
    from larkdocio.drive.models import FolderChild

    children = []
    for index, row in enumerate(dispatch_dry_run()["rows"]):
        child_type = row["type"]
        url = (f"https://example.larksuite.com/docx/tok{index}"
               if child_type == "docx" else None)
        children.append(FolderChild(
            token=f"tok{index}", name=row["name"], type=child_type, url=url))
    return children


def observed_child_types() -> set:
    """Every child ``type`` string that appears in a committed listing capture.

    Read off the captures rather than typed out, so the seam's honesty label
    (``bitable`` observed, ``sheet`` SDK-modeled-and-unobserved) rests on the evidence base.
    """
    types: set = set()
    for cap_name in (LISTING_CAPTURE, DISPATCH_DRY_RUN_CAPTURE):
        cap = capture(cap_name)
        rows = (cap.get("response", {}).get("data", {}).get("files")
                or cap.get("rows") or [])
        types.update(row["type"] for row in rows)
    return types


ROOT_META_CAPTURE = "01-root-folder-meta.json"
METAS_CAPTURE = "06-metas-batch-query.json"


def root_folder_meta_response() -> dict:
    return capture(ROOT_META_CAPTURE)["response"]


def metas_batch_query_response() -> dict:
    return capture(METAS_CAPTURE)["response"]


def document_meta_response(token, *, sec_label_name="", drop_key=False,
                           title="a disposable document") -> dict:
    """A ``metas/batch_query`` answer for ONE **document** token, in the captured meta shape.

    Built from the same committed capture as every other builder here — whose own rows carry
    ``sec_label_name`` populated with ``""`` — so the field's presence is a real payload shape
    rather than a hand-mocked dict. ``drop_key=True`` produces the third case: a reply that
    carries no security-level key at all, which is a **disclosure**, not an empty level.
    """
    template = dict(metas_batch_query_response()["data"]["metas"][0])
    template.update({
        "doc_token": token,
        "doc_type": "docx",
        "title": title,
        "sec_label_name": sec_label_name,
        "request_doc_info": {"doc_token": token, "doc_type": "docx"},
    })
    if drop_key:
        template.pop("sec_label_name")
    return {"code": 0, "msg": "Success", "data": {"metas": [template]}}


def folder_meta_response(token, title) -> dict:
    """A ``metas/batch_query`` answer for ONE folder token, in the captured meta shape.

    Whether ``batch_query`` resolves a *folder* token at all is **not established by any
    capture** (AC7) — this fixture is the optimistic branch, and
    :func:`refusal_response` drives the degrade branch.
    """
    template = dict(metas_batch_query_response()["data"]["metas"][0])
    template.update({
        "doc_token": token,
        "doc_type": "folder",
        "title": title,
        "request_doc_info": {"doc_token": token, "doc_type": "folder"},
    })
    return {"code": 0, "msg": "Success", "data": {"metas": [template]}}


# --------------------------------------------------------------------------- #
# The transport seam — a recording ``urlopen``.                                 #
# --------------------------------------------------------------------------- #

class Call:
    """One request the client really sent, decomposed. What the tests assert against."""

    def __init__(self, request):
        self.method = request.get_method()
        parsed = urllib.parse.urlsplit(request.full_url)
        self.path = parsed.path
        self.url = request.full_url
        #: Query params, **not** collapsed: a repeated key stays visible.
        self.params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        self.param_keys = tuple(k for k, _v in
                                urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        self.body = json.loads(request.data.decode()) if request.data else None


class RecordingTransport:
    """An injectable ``urlopen`` that records every request and answers from ``route``.

    ``route(call)`` returns the response body (a dict) for one request. Every call is kept in
    :attr:`calls`, so a test can assert **what went on the wire** — which is the only way to
    prove ``option`` is never sent and that an opaque page token is echoed verbatim.
    """

    def __init__(self, route):
        self._route = route
        self.calls: list = []

    def __call__(self, request, timeout=None):
        call = Call(request)
        self.calls.append(call)
        body = self._route(call)
        return io.BytesIO(json.dumps(body).encode())

    @property
    def paths(self):
        return [call.path for call in self.calls]

    @property
    def methods(self):
        return sorted({call.method for call in self.calls})


def fast_limiter():
    """A limiter that admits immediately — the offline tests are not about wall-clock pacing,
    and the shipped default (one call per 1.2 s) would make the suite sleep for minutes. The
    pace itself is asserted, separately and on purpose, by the throttle-on-path test."""
    from larkdocio.common.transport import RateLimiter

    return RateLimiter(10 ** 6, window=0.000001)


def token_fetcher(app_id, app_secret, domain, urlopen=None):
    """A stand-in for the tenant-token mint — the credential pair is not this test's subject."""
    return "t-testing-token"


def listing_router(listings, *, refusals=None, root_token=None, metas=None):
    """A ``route`` over ``{folder_token: response}``.

    ``refusals`` maps a folder token onto a refusal body; ``root_token`` answers the
    ``root_folder/meta`` leg; ``metas`` answers ``metas/batch_query``. An unknown folder
    token refuses with the captured ``1061002`` — which is exactly what Lark does.
    """
    refusals = refusals or {}

    def route(call):
        if call.path.endswith("/root_folder/meta"):
            if root_token is None:
                return refusal_response()
            return {"code": 0, "msg": "success",
                    "data": {"id": "9000000000000000001", "token": root_token,
                             "user_id": "<redacted:user_id>"}}
        if call.path.endswith("/metas/batch_query"):
            if metas is None:
                return refusal_response()
            return metas(call) if callable(metas) else metas
        folder = call.params.get("folder_token")
        if folder in refusals:
            return refusals[folder]
        if folder not in listings:
            return refusal_response()
        answer = listings[folder]
        return answer(call) if callable(answer) else answer

    return route
