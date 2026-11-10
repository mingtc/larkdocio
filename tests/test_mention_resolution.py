"""LD-053 — @mention display-name resolution (download-time, graceful degrade).

Resolution mirrors the image-token substitution: the parser stays **offline-pure**
(no network — it only *collects* the distinct mention open_ids at construction
time, like ``parser.file_tokens``), and the download pipeline does the
``contact.v3.user.batch`` lookup + ``@ou_id → @Name`` substitution. Every test
here is deterministic and fully mocks the contacts surface — no live call.

* AC2 — the handler is offline: ``MentionUser`` unchanged; distinct open_ids
  collected on ``parser.mention_user_ids`` (dedup, non-empty).
* AC3 — ``Client.batch_get_user_names`` chunks ≤50/call, ``user_id_type="open_id"``,
  per-run cache (one dict), name preference ``.name`` → ``.en_name`` → ``.nickname``.
* AC4 — graceful degrade: a permission error logs ONE info line, negative-caches
  the whole run (no per-id retry), and output falls back to ``@ou_id``. A partial
  result rewrites only the resolved ids.
"""
import logging
from types import SimpleNamespace

from harness import build_blocks
from larkdocio.blocks.text import build_inline
from larkdocio.read.parser import Parser
from larkdocio.read.config import Config, OutputConfig
from larkdocio.read.client import Client
from larkdocio.model import MentionUser, MarkdownRenderer


def _text_block_dict(elements):
    return {
        "block_id": "b",
        "parent_id": "root",
        "block_type": 2,
        "text": {"elements": elements},
    }


def _text_obj(elements):
    """Build one SDK text block and return its ``.text`` sub-object."""
    b = build_blocks([_text_block_dict(elements)])[0]
    return b.text


# --------------------------------------------------------------------------- #
# AC2 — offline-pure handler: collect distinct open_ids, node unchanged        #
# --------------------------------------------------------------------------- #

def test_mention_user_node_unchanged_and_id_collected():
    """The handler still yields ``MentionUser(user_id)`` (offline, renders @id),
    AND queues the id on ``parser.mention_user_ids`` (like ``file_tokens``)."""
    parser = Parser(Config())
    obj = _text_obj([{"mention_user": {"user_id": "ou_1"}}])
    nodes = build_inline(parser, obj)
    assert nodes == [MentionUser("ou_1")]
    assert MarkdownRenderer().render_inline(nodes) == "@ou_1"  # node offline-pure
    assert parser.mention_user_ids == ["ou_1"]


def test_mention_ids_are_deduped_in_first_seen_order():
    """Repeated ids collapse to one entry (dedup), preserving first-seen order —
    same doc ⇒ same id set ⇒ deterministic within a run."""
    parser = Parser(Config())
    obj = _text_obj([
        {"mention_user": {"user_id": "ou_b"}},
        {"text_run": {"content": " and "}},
        {"mention_user": {"user_id": "ou_a"}},
        {"text_run": {"content": " and again "}},
        {"mention_user": {"user_id": "ou_b"}},
    ])
    build_inline(parser, obj)
    assert parser.mention_user_ids == ["ou_b", "ou_a"]


def test_empty_mention_id_not_collected():
    """A mention with an empty id is not queued (nothing to resolve)."""
    parser = Parser(Config())
    obj = _text_obj([{"mention_user": {"user_id": ""}}])
    nodes = build_inline(parser, obj)
    assert nodes == [MentionUser("")]
    assert parser.mention_user_ids == []


def test_fresh_parser_starts_with_empty_mention_ids():
    """The collection is per-parser (per-run) state, like ``img_tokens``."""
    assert Parser(Config()).mention_user_ids == []


# --------------------------------------------------------------------------- #
# AC3 — Client.batch_get_user_names: chunking, cache, name preference          #
# --------------------------------------------------------------------------- #

def _user(open_id, name=None, en_name=None, nickname=None):
    return SimpleNamespace(open_id=open_id, name=name, en_name=en_name, nickname=nickname)


def _contact_resp(success=True, code=0, msg="ok", items=None):
    return SimpleNamespace(
        success=lambda: success,
        code=code,
        msg=msg,
        get_log_id=lambda: "LOG-XYZ",
        data=SimpleNamespace(items=items or []),
    )


def _client_with_batch(batch_fn):
    client = Client.__new__(Client)
    client.lark_client = SimpleNamespace(
        contact=SimpleNamespace(
            v3=SimpleNamespace(
                user=SimpleNamespace(batch=batch_fn)
            )
        )
    )
    return client


def test_batch_get_user_names_maps_ids_to_names():
    """Happy path: open_ids resolve to display names (prefer ``.name``)."""
    def batch(req):
        return _contact_resp(items=[
            _user("ou_1", name="Alice"),
            _user("ou_2", name="Bob"),
        ])

    client = _client_with_batch(batch)
    assert client.batch_get_user_names(["ou_1", "ou_2"]) == {"ou_1": "Alice", "ou_2": "Bob"}


def test_batch_get_user_names_name_preference_falls_back():
    """Preference is ``.name`` → ``.en_name`` → ``.nickname``; a user with no
    usable name at all is omitted (nothing to substitute)."""
    def batch(req):
        return _contact_resp(items=[
            _user("ou_name", name="Real Name", en_name="EN", nickname="NICK"),
            _user("ou_en", name=None, en_name="EnOnly", nickname="NICK"),
            _user("ou_nick", name=None, en_name=None, nickname="NickOnly"),
            _user("ou_none", name=None, en_name=None, nickname=None),
        ])

    client = _client_with_batch(batch)
    out = client.batch_get_user_names(["ou_name", "ou_en", "ou_nick", "ou_none"])
    assert out == {"ou_name": "Real Name", "ou_en": "EnOnly", "ou_nick": "NickOnly"}


def test_batch_get_user_names_chunks_at_50():
    """More than 50 ids are split into ≤50-id calls (SDK limit)."""
    seen_chunks = []

    def batch(req):
        ids = req.user_ids
        seen_chunks.append(len(ids))
        return _contact_resp(items=[_user(i, name=f"n-{i}") for i in ids])

    client = _client_with_batch(batch)
    ids = [f"ou_{n}" for n in range(120)]
    out = client.batch_get_user_names(ids)
    assert seen_chunks == [50, 50, 20]
    assert len(out) == 120


def test_batch_get_user_names_sets_open_id_type():
    """The request is built with ``user_id_type="open_id"`` (our ids are ``ou_``)."""
    captured = {}

    def batch(req):
        captured["user_id_type"] = req.user_id_type
        captured["user_ids"] = list(req.user_ids)
        return _contact_resp(items=[_user("ou_1", name="Alice")])

    client = _client_with_batch(batch)
    client.batch_get_user_names(["ou_1"])
    assert captured["user_id_type"] == "open_id"
    assert captured["user_ids"] == ["ou_1"]


def test_batch_get_user_names_empty_input_makes_no_call():
    """No ids ⇒ no API call, empty dict."""
    def batch(req):  # pragma: no cover - must not be called
        raise AssertionError("no contact call expected for empty input")

    client = _client_with_batch(batch)
    assert client.batch_get_user_names([]) == {}


# --------------------------------------------------------------------------- #
# AC4 — graceful degrade: permission error → ONE info line → whole-run @ou_id  #
# --------------------------------------------------------------------------- #

def test_permission_error_degrades_with_one_info_line(caplog):
    """A permission-denied response logs exactly ONE info line (carrying Lark's
    error body for the maintainer to read the scope from) and returns an empty dict —
    the whole run falls back to ``@ou_id``."""
    calls = []

    def batch(req):
        calls.append(1)
        return _contact_resp(
            success=False, code=99991672,
            msg="Permission denied: the app lacks scope contact:user.base:readonly",
        )

    client = _client_with_batch(batch)
    with caplog.at_level(logging.INFO, logger="larkdocio"):
        out = client.batch_get_user_names(["ou_1", "ou_2"])

    assert out == {}
    info_lines = [r for r in caplog.records if r.levelno == logging.INFO]
    assert len(info_lines) == 1, [r.message for r in info_lines]
    # The exact Lark error body is surfaced (AC6 scope capture at QA).
    assert "contact:user.base:readonly" in info_lines[0].message


def test_permission_error_negative_caches_whole_run(caplog):
    """On a permission error the remaining chunks are NOT retried (negative cache
    for the run) — only the first chunk is attempted before falling back."""
    calls = []

    def batch(req):
        calls.append(len(req.user_ids))
        return _contact_resp(success=False, code=99991672, msg="no permission scope contact:user.base:readonly")

    client = _client_with_batch(batch)
    with caplog.at_level(logging.INFO, logger="larkdocio"):
        out = client.batch_get_user_names([f"ou_{n}" for n in range(120)])

    assert out == {}
    # Exactly one attempt (the first chunk), then negative-cache short-circuits.
    assert calls == [50]


def test_partial_result_rewrites_only_resolved_ids(caplog):
    """A permission error after a successful chunk keeps the resolved ids and
    stops (partial result); no exception escapes."""
    responses = [
        _contact_resp(items=[_user(f"ou_{n}", name=f"n-{n}") for n in range(50)]),
        _contact_resp(success=False, code=99991672, msg="no permission scope contact:user.base:readonly"),
    ]

    def batch(req):
        return responses.pop(0)

    client = _client_with_batch(batch)
    with caplog.at_level(logging.INFO, logger="larkdocio"):
        out = client.batch_get_user_names([f"ou_{n}" for n in range(120)])

    # Only the first (resolved) chunk survives; the rest degrade to @ou_id.
    assert len(out) == 50
    assert out["ou_0"] == "n-0"
    assert "ou_60" not in out


def test_batch_generic_exception_degrades_gracefully(caplog):
    """Any exception from the SDK is swallowed (best-effort, warn-and-continue
    precedent) — the download never fails because of mention resolution."""
    def batch(req):
        raise RuntimeError("network boom")

    client = _client_with_batch(batch)
    with caplog.at_level(logging.INFO, logger="larkdocio"):
        out = client.batch_get_user_names(["ou_1"])

    assert out == {}


# --------------------------------------------------------------------------- #
# AC3 / AC4 / AC7 — download-time substitution (`_resolve_mentions`)           #
# --------------------------------------------------------------------------- #

from larkdocio.read import download  # noqa: E402


class _MentionClient:
    """Stub client exposing only ``batch_get_user_names`` (records the ids seen)."""

    def __init__(self, names):
        self._names = names
        self.calls = []

    def batch_get_user_names(self, ids):
        self.calls.append(list(ids))
        return {i: self._names[i] for i in ids if i in self._names}


class _MentionParser:
    def __init__(self, mention_user_ids=()):
        self.mention_user_ids = list(mention_user_ids)


def test_resolve_mentions_substitutes_names_default_on():
    """Default (resolve_mentions True): every ``@ou_id`` is rewritten to ``@Name``."""
    client = _MentionClient({"ou_1": "Alice", "ou_2": "Bob"})
    parser = _MentionParser(["ou_1", "ou_2"])
    md = "Author: @ou_1 and reviewer @ou_2 signed off; @ou_1 again."

    out = download._resolve_mentions(client, Config(), parser, md)

    assert out == "Author: @Alice and reviewer @Bob signed off; @Alice again."


def test_resolve_mentions_disabled_knob_skips_and_makes_no_call():
    """resolve_mentions=False → no contacts call, markdown byte-identical."""
    client = _MentionClient({"ou_1": "Alice"})
    parser = _MentionParser(["ou_1"])
    cfg = Config(OutputConfig(resolve_mentions=False))

    out = download._resolve_mentions(client, cfg, parser, "hi @ou_1")

    assert out == "hi @ou_1"
    assert client.calls == [], "disabled knob must never call the contacts API"


def test_resolve_mentions_no_ids_makes_no_call():
    """A doc with no mentions makes no call and is unchanged."""
    client = _MentionClient({"ou_1": "Alice"})
    parser = _MentionParser([])

    out = download._resolve_mentions(client, Config(), parser, "no mentions here")

    assert out == "no mentions here"
    assert client.calls == []


def test_resolve_mentions_partial_result_rewrites_only_resolved():
    """AC4: a partial result rewrites only the resolved ids; the rest stay @ou_id."""
    client = _MentionClient({"ou_1": "Alice"})  # ou_2 unresolved
    parser = _MentionParser(["ou_1", "ou_2"])
    md = "@ou_1 talked to @ou_2"

    out = download._resolve_mentions(client, Config(), parser, md)

    assert out == "@Alice talked to @ou_2"


def test_resolve_mentions_empty_result_leaves_markdown_byte_identical():
    """Graceful degrade (scope absent → empty dict): output is byte-identical
    to today's raw ``@ou_id`` passthrough."""
    client = _MentionClient({})  # nothing resolved (missing scope)
    parser = _MentionParser(["ou_1", "ou_2"])
    md = "@ou_1 and @ou_2"

    out = download._resolve_mentions(client, Config(), parser, md)

    assert out == "@ou_1 and @ou_2"


def test_resolve_mentions_no_prefix_collision_between_ids():
    """Ids where one is a prefix of another (``ou_1`` vs ``ou_da``) are substituted
    without corruption — the longest ids are rewritten first."""
    client = _MentionClient({"ou_1": "Alice", "ou_da": "Bob"})
    parser = _MentionParser(["ou_1", "ou_da"])
    md = "@ou_1 then @ou_da"

    out = download._resolve_mentions(client, Config(), parser, md)

    assert out == "@Alice then @Bob"


def test_handle_download_substitutes_mention_names_end_to_end(monkeypatch, tmp_path):
    """End-to-end: the written markdown has ``@ou_id`` rewritten to ``@Name`` when
    resolve_mentions is on (default). AC7 pipeline wiring."""
    monkeypatch.setattr(download, "init_env", lambda *a, **k: None)
    monkeypatch.setattr(download, "get_read_credentials", lambda: ("id", "sec"))

    class _Client:
        def get_docx_content(self, doc_token):
            return SimpleNamespace(title="Doc", document_id="D"), []

        def batch_get_user_names(self, ids):
            return {"ou_zed": "Zed"}

    class _Parser:
        def __init__(self, config):
            self.img_tokens = []
            self.board_tokens = []
            self.file_tokens = []
            self.mention_user_ids = ["ou_zed"]

        def parse_docx_content(self, document_id, blocks):
            return "Owner: @ou_zed\n"

    monkeypatch.setattr(download, "Client", lambda *a, **k: _Client())
    monkeypatch.setattr(download, "Parser", lambda config: _Parser(config))

    download.handle_download_command(
        "https://example.larksuite.com/docx/AbCdEfG123", str(tmp_path), "", False, ""
    )

    written = list(tmp_path.glob("*.md"))
    assert len(written) == 1
    assert written[0].read_text(encoding="utf-8") == "Owner: @Zed\n"
