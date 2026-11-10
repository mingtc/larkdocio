"""larkdocio.sheets.models — typed parses of the Sheets read responses (LD-101).

Small, frozen dataclasses the :mod:`larkdocio.sheets.client` returns instead of
raw dicts, so downstream L1 stories (used-range trim S2, cell rendering S3, table
assembly + the merge join S4) consume a **typed** surface. They pin the exact
response shapes the opener spike characterized (``tests/captures/sheets-spike/``, in the source repository):

* :class:`SpreadsheetMeta` — the v3 spreadsheet-metadata ``data.spreadsheet``.
* :class:`SheetTab` — one tab from the v3 ``sheets/query`` response: id / title /
  index / grid extent + its :class:`Merge` list.
* :class:`Merge` — one merged region from the tab-query ``merges`` array,
  **0-indexed with the end row/column INCLUSIVE** (spike Q3; ``{0,0,0,2}`` = A1:C1).
  The values read alone can never reconstruct merge geometry — S4 joins this.
* :class:`ValueRange` — one v2 values range: its A1 ``range``, ``revision``,
  ``major_dimension``, and the raw ``values`` matrix (untrimmed, unrendered — trim
  is S2, render is S3).
* :class:`SheetFilter` (+ :class:`FilterColumn` / :class:`FilterCondition`) — one tab's
  filter state from the v3 ``.../filter`` read: its range, the rows the filter **hides**,
  and the per-column conditions. A values read cannot see any of this, which is why a
  filtered tab used to render its hidden rows as if they were visible.
* :class:`FrozenPanes` (+ :func:`parse_frozen_panes` and the ``FROZEN_*`` state slugs) — one
  tab's **frozen row/column counts** (LD-186). Sheet-level view state that ``metainfo`` and
  the v3 tab query both carry and that L1 surfaced **nowhere** before LD-186 — the read leg a
  freeze write needs in order to be verifiable at all.
* the ``REVISION_*`` state slugs + :func:`parse_revision` — the spreadsheet's **revision
  anchor** (LD-332), the one version number a consumer's ledger compares between runs. It is
  **per-spreadsheet**, and it is the same number :attr:`UsedRange.revision` has always
  carried; :class:`SheetTab` now carries it too, so the tab-object read paths answer the
  ledger's question without a values read.
"""
from dataclasses import dataclass, replace

# --------------------------------------------------------------------------- #
# Filter-state vocabulary. Four states, and the difference between the last    #
# three is the whole point: "nobody asked", "asked, there is none", and        #
# "asked, could not find out" are three different facts, and collapsing any    #
# pair of them is how a fidelity limit becomes silent.                        #
# --------------------------------------------------------------------------- #

#: No filter read was attempted for this tab — the reader claims **no knowledge** either
#: way. The default, and the state every tab a plain tab query returns is in.
FILTER_NOT_READ = "not-read"

#: The filter read succeeded and the tab has **no** filter.
FILTER_NONE = "none"

#: The filter read succeeded and the tab **has** a filter (which may hide zero rows).
FILTER_ACTIVE = "active"

#: The filter read was attempted and **failed** (no permission, a call error, a transport
#: failure). Whether rows are hidden is **unknown** — deliberately not reported as "none".
FILTER_UNAVAILABLE = "unavailable"


# --------------------------------------------------------------------------- #
# Frozen-panes vocabulary (LD-186). The SAME four states as the filter's, and    #
# deliberately the same four slugs: a consumer already branches on              #
# `not-read` / `none` / `active` / `unavailable`, and coining a second           #
# vocabulary for the identical distinction would be gratuitous.                 #
#                                                                              #
# The whole reason this exists: the backlog claimed larkdocio ALREADY read      #
# `frozen_*_count`. It did not — `grep -rl "frozen_" src/` was empty — so a     #
# freeze write had nothing to diff against. This is that missing read leg.      #
# --------------------------------------------------------------------------- #

#: No frozen read was attempted for this tab — **no knowledge** either way. The default, and
#: the state every tab a plain tab query returns is in (so nothing about the shipped read path
#: changes until a caller opts in).
FROZEN_NOT_READ = "not-read"

#: The frozen read succeeded and the tab freezes **nothing** (both counts ``0``).
FROZEN_NONE = "none"

#: The frozen read succeeded and the tab **has** a frozen band on at least one axis.
FROZEN_ACTIVE = "active"

#: The frozen read was attempted and the answer is **unknown** — the call failed, the tab was
#: absent from the response, or the payload carried no frozen keys. Deliberately **not**
#: reported as ``none``: "I could not find out" and "nothing is frozen" are different facts,
#: and collapsing them is exactly how a fidelity limit becomes silent (the LD-155 lesson, and
#: the LD-184 one — three outcomes that all answered ``{}`` cost ~5 days of misdiagnosis).
FROZEN_UNAVAILABLE = "unavailable"

#: ``metainfo``'s key names for the two counts (camelCase) — probed live
#: (``tests/captures/sheets-freeze-probe/captures/01-…json``).
FROZEN_KEYS_METAINFO = ("frozenRowCount", "frozenColCount")

#: The v3 tab query's key names for the same two counts, under ``grid_properties``
#: (snake_case) — the same probe.
FROZEN_KEYS_GRID = ("frozen_row_count", "frozen_column_count")


# --------------------------------------------------------------------------- #
# Revision-anchor vocabulary (LD-332). THREE states, not four: there is no      #
# "this spreadsheet has no revision" — an absent number is not a fact about     #
# the spreadsheet, it is a gap in what we know, so it lands in `unavailable`.   #
# --------------------------------------------------------------------------- #

#: No revision read was attempted for this tab — **no knowledge** either way. The default, and
#: the state every tab a plain tab query returns is in (the v3 tab query carries no revision at
#: all — probed, ``tests/captures/sheets-revision-anchor-probe/`` (in the source repository)), so no
#: shipped read path pays for an anchor until a caller asks for one.
REVISION_NOT_READ = "not-read"

#: The revision read succeeded and the anchor is **known** — including when it is ``0``, which
#: on this API is a real value a fresh spreadsheet genuinely reports.
REVISION_KNOWN = "known"

#: The revision read was attempted and the answer is **unknown** — the call failed, the reply
#: carried no ``properties.revision``, or what it carried was not an integer. Deliberately
#: **never** reported as ``0``: ``0`` is a real revision on this API, so synthesizing it would
#: hand a ledger a version number nobody observed.
REVISION_UNAVAILABLE = "unavailable"


def parse_revision(raw):
    """``(revision, reason)`` — the ONE reading of a raw revision value.

    Only a real :class:`int` is knowledge, and ``0`` is knowledge. A digit-string, a ``bool``
    (an ``int`` subclass in Python, but drift rather than a version), a float, ``None`` or an
    absent key all yield ``(None, reason)``, and the ``reason`` quotes what was actually seen —
    so a ledger is told *why* it has no anchor instead of being handed a plausible number.
    """
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None, (
            f"the read carried no usable spreadsheet revision (it carried {raw!r}) — so the "
            f"revision anchor is UNKNOWN, which is not the same as revision 0 and is "
            f"deliberately not reported as such"
        )
    return raw, None


@dataclass(frozen=True)
class FrozenPanes:
    """One tab's frozen row/column counts — how many leading rows/columns stay pinned.

    **Counts, not indexes**, so no index-convention question arises: ``rows=2`` means the
    first two rows are frozen, and ``0`` means nothing on that axis. The write side takes the
    same counts (:class:`~larkdocio.sheets.requests.FreezePanes`), so a read-back compares
    like-for-like with what was asked — which is the entire point of shipping this leg
    alongside the write.

    ``source`` records **which read** produced it (``"metainfo"`` / ``"v3-tab-query"``), because
    the two payload families name the fields differently and a reader of a plan or an apply-log
    should not have to guess which one was consulted.
    """

    rows: int = 0
    cols: int = 0
    source: str | None = None

    @property
    def is_frozen(self) -> bool:
        """True iff either axis freezes anything."""
        return bool(self.rows) or bool(self.cols)

    def describe(self) -> str:
        """The human restatement used in plan notes and apply-log records."""
        if not self.is_frozen:
            return "nothing frozen"
        rows = f"{self.rows} row(s) frozen" if self.rows else "no rows frozen"
        cols = f"{self.cols} column(s) frozen" if self.cols else "no columns frozen"
        return f"{rows}, {cols}"

    def as_dict(self) -> dict:
        return {"frozen_rows": self.rows, "frozen_cols": self.cols, "source": self.source}


def _frozen_count(raw):
    """One frozen count, or ``None`` when the payload does not actually name one.

    A digit string (``"2"``) is accepted as the number it plainly names — Lark itself accepts a
    string count on the WRITE side (probed: ``frozenRowCount: "2"`` → ``code 0``), and the
    failure modes are not symmetric: **under**-reporting a frozen band silently tells a caller
    the tab is unfrozen, while accepting a well-formed number costs nothing. A bool is an
    ``int`` subclass in Python but is drift, never a count (Lark answers a bool
    ``9499 Invalid parameter type in json: FrozenRowCount``), so it is rejected. A negative
    count is not expressible on the wire and is treated as drift too.
    """
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        return raw if raw >= 0 else None
    if isinstance(raw, str):
        text = raw.strip()
        if text.isdigit():
            return int(text)
    return None


def parse_frozen_panes(payload, *, keys=FROZEN_KEYS_METAINFO, source=None) -> tuple:
    """``(FrozenPanes, None)`` — or ``(None, reason)`` when the payload does not carry the
    frozen counts.

    The ONE parser both payload families go through (``metainfo``'s camelCase sheet dict and
    the v3 tab query's snake_cased ``grid_properties``), so the two shapes cannot drift apart
    and a third caller cannot invent a third reading.

    **A half-present payload is ``None``, not half-invented.** One axis known and the other
    absent is not knowledge a write can be diffed against, and reporting the known half as
    fact while quietly zeroing the other is the silent-fidelity failure this whole leg exists
    to prevent. The ``reason`` names the missing key(s), so the disclosure can say *why* the
    frozen state is unknown instead of just that it is.
    """
    row_key, col_key = keys
    data = payload if isinstance(payload, dict) else {}
    rows, cols = _frozen_count(data.get(row_key)), _frozen_count(data.get(col_key))
    missing = [k for k, v in ((row_key, rows), (col_key, cols)) if v is None]
    if missing:
        return None, (
            f"the frozen read carried no usable {' and no usable '.join(missing)} — so "
            f"whether this tab freezes anything is UNKNOWN, which is not the same as nothing "
            f"being frozen and is deliberately not reported as such"
        )
    return FrozenPanes(rows=rows, cols=cols, source=source), None


@dataclass(frozen=True)
class SpreadsheetMeta:
    """The v3 spreadsheet metadata (``data.spreadsheet``)."""

    token: str
    title: str
    owner_id: str | None = None
    url: str | None = None

    @classmethod
    def from_response(cls, resp: dict) -> "SpreadsheetMeta":
        s = (resp.get("data") or {}).get("spreadsheet") or {}
        return cls(
            token=s.get("token"),
            title=s.get("title"),
            owner_id=s.get("owner_id"),
            url=s.get("url"),
        )


@dataclass(frozen=True)
class Merge:
    """A merged region from the tab-query ``merges`` array.

    **0-indexed, END-inclusive** (spike Q3): ``Merge(0, 0, 0, 2)`` is A1:C1;
    ``Merge(2, 4, 0, 0)`` is the vertical merge A3:A5 (covers A4, A5).
    """

    start_row: int
    end_row: int
    start_col: int
    end_col: int

    @classmethod
    def from_dict(cls, d: dict) -> "Merge":
        return cls(
            start_row=d.get("start_row_index"),
            end_row=d.get("end_row_index"),
            start_col=d.get("start_column_index"),
            end_col=d.get("end_column_index"),
        )


@dataclass(frozen=True)
class FilterCondition:
    """One condition inside a filter column.

    ``compare_type`` is optional because the filter **read** does not echo it back even
    when the write that created the filter supplied one (observed against the live API), so
    requiring it would fail on every real filter.
    """

    filter_type: str | None = None
    compare_type: str | None = None
    expected: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, d: dict) -> "FilterCondition":
        expected = d.get("expected")
        return cls(
            filter_type=d.get("filter_type"),
            compare_type=d.get("compare_type"),
            expected=tuple(expected) if isinstance(expected, list) else (),
        )


@dataclass(frozen=True)
class FilterColumn:
    """One filtered column (``col`` is an A1 column letter) and its conditions."""

    col: str | None = None
    conditions: tuple[FilterCondition, ...] = ()

    @classmethod
    def from_dict(cls, d: dict) -> "FilterColumn":
        conditions = d.get("conditions")
        return cls(
            col=d.get("col"),
            conditions=tuple(
                FilterCondition.from_dict(c)
                for c in (conditions if isinstance(conditions, list) else ())
                if isinstance(c, dict)
            ),
        )


@dataclass(frozen=True)
class SheetFilter:
    """One tab's filter state, from ``GET …/sheets/v3/spreadsheets/{token}/sheets/{id}/filter``.

    **``filtered_out_rows`` is SHEET-ABSOLUTE and 1-INDEXED** — the row numbers the
    spreadsheet itself shows a person, counting the first row of the sheet as 1. This was
    established by probing the live API with the filter's own range **offset** away from row
    1, so that a sheet-absolute answer and a range-relative one could not be confused:
    with the filter ranged over ``A3:B8`` and the hidden rows sitting at the sheet's rows 5
    and 7, the API answered ``[5, 7]``.

    That is worth stating explicitly because it is the **opposite** of the convention its
    neighbour in the same response family uses: the tab query's ``merges`` array is
    0-indexed and end-inclusive. Two consequences follow:

    * a consumer indexing a Python values matrix wants :attr:`matrix_row_indexes`, which
      does the one subtraction in one place; and
    * a filter whose range is **narrower** than the used range needs no arithmetic at all,
      because the numbers are already absolute to the sheet.

    The rows are **sorted and de-duplicated** on parse so a disclosure built from them is
    deterministic.
    """

    range: str | None = None
    filtered_out_rows: tuple[int, ...] = ()
    columns: tuple[FilterColumn, ...] = ()

    @classmethod
    def from_response(cls, resp: dict) -> "SheetFilter | None":
        """Parse a filter read, or return ``None`` when the tab has **no filter**.

        A tab with no filter answers **successfully** with the ``sheet_filter_info`` key
        simply absent (observed live), so ``None`` here means "read fine, no filter" — it
        never means "the read failed". A failed read is a different state and is carried on
        the tab as :data:`FILTER_UNAVAILABLE`.

        Belt-and-braces against payload drift: a non-integer row number is dropped rather
        than raised on, because a document read must never fail over its filter metadata.
        """
        info = (resp.get("data") or {}).get("sheet_filter_info")
        if not isinstance(info, dict):
            return None
        infos = info.get("filter_infos")
        return cls(
            range=info.get("range"),
            filtered_out_rows=_row_numbers(info.get("filtered_out_rows")),
            columns=tuple(
                FilterColumn.from_dict(c)
                for c in (infos if isinstance(infos, list) else ())
                if isinstance(c, dict)
            ),
        )

    @property
    def hidden_row_count(self) -> int:
        """How many rows this filter hides (may be ``0`` — a filter can match everything)."""
        return len(self.filtered_out_rows)

    @property
    def matrix_row_indexes(self) -> tuple[int, ...]:
        """The hidden rows as **0-indexed** offsets into a values matrix.

        The one place the 1-indexed→0-indexed subtraction happens, so a consumer wanting to
        drop the hidden rows from a matrix never has to rediscover the convention. A row
        number below 1 is not addressable and is dropped.
        """
        return tuple(r - 1 for r in self.filtered_out_rows if r >= 1)


def _row_numbers(raw) -> tuple[int, ...]:
    """Sorted, de-duplicated row numbers from a filter payload.

    A digit-string (``"5"``) is accepted as the row it plainly names, because the failure
    modes here are not symmetric: **under**-reporting a hidden row is a quiet return of the
    very defect the disclosure exists to fix, while over-accepting a well-formed number
    costs nothing. Anything that is not a whole number — a float, a boolean (an ``int``
    subclass in Python, but drift rather than a row), a non-numeric string, ``None`` — is
    dropped, since a read must never fail over its filter metadata.
    """
    if not isinstance(raw, list):
        return ()
    rows = set()
    for value in raw:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            rows.add(value)
        elif isinstance(value, str):
            text = value.strip()
            if text.lstrip("-").isdigit():
                rows.add(int(text))
    return tuple(sorted(rows))


@dataclass(frozen=True)
class SheetTab:
    """One tab from the v3 ``sheets/query`` response.

    Surfaces the tab's ``sheet_id`` / ``title`` / ``index`` / declared grid extent
    (``row_count`` × ``column_count`` — the used-range upper bound) and its
    :class:`Merge` list (empty when the tab declares none).

    **Filter state is carried, never assumed.** The tab query does not report filters — the
    filter is a separate endpoint — so a tab starts at :data:`FILTER_NOT_READ` and gains
    filter knowledge only through :meth:`with_filter` / :meth:`with_filter_unavailable`.
    A tab in the ``not-read`` state renders exactly as it always has: no disclosure note,
    because the reader has nothing to disclose. :attr:`filtered_out_rows` is the
    programmatic surface (**sheet-absolute, 1-indexed** — see :class:`SheetFilter`).

    **Visibility is carried, and it is free.** :attr:`hidden` is projected from the same
    tab-query element every other field here comes from — the route answers it on every tab
    — so a read-only caller can tell a hidden tab from a visible one without a second call
    and without write credentials. Through 1.35 it was dropped in projection, and the only
    shipped way to ask was the write client's ``query_tabs``. ``None`` means the payload did
    not say, which is never reported as *visible*.

    **The rendered Markdown does not change with it.** :func:`~larkdocio.sheets.table.render_spreadsheet`
    emits the same bytes for a hidden tab as for a visible one; a report that wants the
    distinction reads :attr:`hidden` and says so itself.
    """

    sheet_id: str
    title: str
    index: int
    row_count: int | None
    column_count: int | None
    merges: tuple[Merge, ...] = ()
    filter_state: str = FILTER_NOT_READ
    filter_state_detail: str | None = None
    sheet_filter: SheetFilter | None = None
    filtered_out_rows: tuple[int, ...] = ()
    #: LD-186 — frozen-panes state, carried exactly the way filter state is: never assumed.
    #: A tab query DOES carry the counts, but ``from_dict`` deliberately leaves this at
    #: ``not-read`` so no shipped read path changes shape until a caller opts in.
    frozen_state: str = FROZEN_NOT_READ
    frozen_state_detail: str | None = None
    frozen_panes: FrozenPanes | None = None
    #: LD-332 — the spreadsheet's **revision anchor**, carried the way filter and frozen state
    #: are: never assumed. ``None`` means *not known* (see :attr:`revision_state`) — never
    #: revision ``0``, which is a real value on this API. Same name and same ``int | None`` type
    #: as :attr:`~larkdocio.sheets.extent.UsedRange.revision`, because it is the same number:
    #: one anchor, per **spreadsheet**, whichever read path reached it.
    revision: int | None = None
    revision_state: str = REVISION_NOT_READ
    revision_state_detail: str | None = None
    #: LD-477 — the tab's **visibility**, taken straight off the tab query's own wire.
    #: ``True`` the tab is hidden, ``False`` it is visible, ``None`` the payload did not say
    #: usably — never ``False`` for an absent answer (see :meth:`from_dict`). It is last in
    #: the field order deliberately: every field before it keeps the position it shipped in,
    #: so a caller constructing a tab positionally is unaffected.
    hidden: bool | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "SheetTab":
        """One ``sheets[]`` element of the v3 tab query, projected.

        **``hidden`` is read here and costs nothing**: the tab query answers it on every
        element it returns (measured on the read route, 2026-08-16 — a hidden tab
        ``true``, a visible one an explicit ``false``), so the read that was already being
        made carries the answer and no second call, endpoint or credential is involved.

        A payload that names no usable ``hidden`` yields ``None``, **never** ``False`` —
        the rule :func:`parse_frozen_panes` established and
        :meth:`~larkdocio.sheets.write_client.SheetsWriteClient.query_tabs` applies to this
        same flag: *"nobody said"* and *"the tab is visible"* are different facts, and
        collapsing them is how a fidelity limit goes silent.
        """
        grid = d.get("grid_properties") or {}
        merges = tuple(Merge.from_dict(m) for m in (d.get("merges") or []))
        raw_hidden = d.get("hidden")
        return cls(
            sheet_id=d.get("sheet_id"),
            title=d.get("title"),
            index=d.get("index"),
            row_count=grid.get("row_count"),
            column_count=grid.get("column_count"),
            merges=merges,
            hidden=raw_hidden if isinstance(raw_hidden, bool) else None,
        )

    def with_filter(self, sheet_filter: "SheetFilter | None", *, detail=None) -> "SheetTab":
        """A copy of this tab carrying the outcome of a **successful** filter read.

        ``sheet_filter=None`` records that the tab has no filter (:data:`FILTER_NONE`); a
        :class:`SheetFilter` records that it has one (:data:`FILTER_ACTIVE`), which may
        still hide zero rows. This is the **only** writer of :attr:`filtered_out_rows`, so
        the field and the filter object cannot drift apart.
        """
        if sheet_filter is None:
            return replace(
                self, filter_state=FILTER_NONE, filter_state_detail=detail,
                sheet_filter=None, filtered_out_rows=(),
            )
        return replace(
            self, filter_state=FILTER_ACTIVE, filter_state_detail=detail,
            sheet_filter=sheet_filter,
            filtered_out_rows=sheet_filter.filtered_out_rows,
        )

    def with_filter_unavailable(self, detail: str) -> "SheetTab":
        """A copy of this tab recording that the filter read was attempted and **failed**.

        ``detail`` is the reason, and it is required: the value of this state over silence
        is that it says *why* the reader cannot vouch for the row set. No rows are claimed
        hidden, because none are known — which is precisely not the same as none being
        hidden.
        """
        return replace(
            self, filter_state=FILTER_UNAVAILABLE, filter_state_detail=detail,
            sheet_filter=None, filtered_out_rows=(),
        )

    # -- LD-186: frozen-panes state, the filter pattern replayed ------------ #

    def with_frozen(self, panes: "FrozenPanes", *, detail=None) -> "SheetTab":
        """A copy of this tab carrying the outcome of a **successful** frozen read.

        ``panes`` is required and must be a real :class:`FrozenPanes`: an unsuccessful read is
        :meth:`with_frozen_unavailable`, never a ``FrozenPanes(0, 0)``. A tab that freezes
        nothing lands in :data:`FROZEN_NONE` — a **known** answer — while a tab whose freeze
        state could not be established lands in :data:`FROZEN_UNAVAILABLE`.
        """
        state = FROZEN_ACTIVE if panes.is_frozen else FROZEN_NONE
        return replace(self, frozen_state=state, frozen_state_detail=detail,
                       frozen_panes=panes)

    def with_frozen_unavailable(self, detail: str) -> "SheetTab":
        """A copy recording that the frozen read was attempted and the answer is **unknown**.

        ``detail`` is required — the value of this state over silence is that it says *why*.
        No counts are carried, because none are known, which is precisely not the same as
        nothing being frozen.
        """
        return replace(self, frozen_state=FROZEN_UNAVAILABLE, frozen_state_detail=detail,
                       frozen_panes=None)

    # -- LD-332: the revision anchor, the same pattern a third time ---------- #

    def with_revision(self, revision: int, *, detail=None) -> "SheetTab":
        """A copy of this tab carrying a **known** revision anchor.

        ``revision`` must be a real integer — an unusable one is
        :meth:`with_revision_unavailable`, never a ``0``. ``0`` reaching here is a *known*
        anchor (a fresh spreadsheet reports it), so it lands in :data:`REVISION_KNOWN`.
        """
        parsed, reason = parse_revision(revision)
        if parsed is None:
            return self.with_revision_unavailable(reason)
        return replace(self, revision=parsed, revision_state=REVISION_KNOWN,
                       revision_state_detail=detail)

    def with_revision_unavailable(self, detail: str) -> "SheetTab":
        """A copy recording that the revision read was attempted and the answer is **unknown**.

        ``detail`` is required — the value of this state over silence is that it says *why* a
        ledger has no version to compare against. No number is carried, because none is known,
        which is precisely not the same as revision ``0``.
        """
        return replace(self, revision=None, revision_state=REVISION_UNAVAILABLE,
                       revision_state_detail=detail)


@dataclass(frozen=True)
class ValueRange:
    """One v2 values range: its A1 ``range``, ``revision``, ``major_dimension``,
    and the **raw** ``values`` matrix (untrimmed, unrendered).

    The matrix is returned exactly as the API gave it — the full declared grid
    with trailing ``null``s (no trim — the extent module does that), and rich cells still as their
    structured arrays/objects (no value→Markdown render — the renderer does that).
    """

    range: str
    revision: int | None
    major_dimension: str | None
    values: list

    @classmethod
    def from_dict(cls, d: dict) -> "ValueRange":
        return cls(
            range=d.get("range"),
            revision=d.get("revision"),
            major_dimension=d.get("majorDimension"),
            values=d.get("values") or [],
        )
