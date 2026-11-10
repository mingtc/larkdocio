"""larkdocio.sheets.rich_encode — Sheets rich-cell WRITE encoders.

The write-side counterpart to L1's read-side ``render_cell`` / the typed
:mod:`~larkdocio.sheets.cell_model`: pure functions that build the **exact probe-confirmed
wire cells** the write spike proved live, so a caller never hand-assembles a rich
segment object. Four encodings:

* **hyperlink** — :func:`encode_hyperlink` → ``{"type":"url","text","link"}``;
* **styled-runs** — :func:`encode_styled_run` / :func:`encode_styled_runs` → a
  ``segmentStyle`` array (the sheets analogue of the docx writer's run-preservation), each run
  carrying **only the style keys actually set** (matching the spike's write shape,
  where the read-back fills every default);
* **@mention** — :func:`encode_mention` →
  ``{"type":"mention","text":<open_id>,"textType":"openId","notify":false,"grantReadPermission":false}``
  — the **least-surprise / least-privilege defaults** (``notify:false`` +
  ``grantReadPermission:false``), exposed as **opt-in** overrides;
* **multi-select** — :func:`encode_multi_select` →
  ``{"type":"multipleValue","values":[…]}``, the labels normalized to an **ordered
  label set**.

The dropdown **RULE** the multi-select cell pairs with is the same ``dataValidation``
family: :func:`encode_dropdown_rule` builds the probe-confirmed
list-rule payload — ``{"dataValidationType":"list","dataValidation":{"conditionValues":[…],
"options":{"multipleValues":…,"highlightValidData":…}}}``. Its load-bearing caveat is the
**`90204`**: ``highlightValidData:true`` needs a ``colors`` array **1:1** with the
``conditionValues`` — the encoder defaults ``highlightValidData:false`` and, when it is
turned on without a matching-length ``colors`` array, refuses **before the write** with a
typed :class:`DropdownColorsError` (never a live ``90204`` round-trip). The rule declares
the options; the paired multi-select **cell** write (:func:`encode_multi_select`) still owns
the comma-in-label refusal (a rule only lists options — a comma becomes unrepresentable only
once a multi-value cell is written through it).

**The multi-select read/write asymmetry.** The write form is the object above;
the read-back is a **comma-joined string** (``"Red,Green"`` — confirmed
twice). Because the read form is comma-joined, a **comma inside an option label is
unrepresentable** — :func:`encode_multi_select` **refuses** it with a typed
:class:`MultiSelectLabelError` (never a silent corruption). :func:`normalize_multi_select`
normalizes **both** wire forms to the same ordered label-set tuple by **reusing the
read path's own** :class:`~larkdocio.sheets.cell_model.MultiSelect` normalizer (not a fork), so a
differ / round-trip check compares like-for-like.

Pure + offline — no network, no creds. These build the cells the gated apply engine
(:mod:`larkdocio.sheets.write_apply`, via :class:`~larkdocio.sheets.write_apply.RichCellWriteRequest`)
writes through the ``Plan`` → dry-run → apply gate.
"""
from larkdocio.errors import LarkConfigError
from larkdocio.sheets.cell_model import MultiSelect

# The write-side segmentStyle boolean flags, mapped from the encoder's snake_case name
# to the Lark wire (camelCase) name. Only a flag actually set to True is emitted — the
# spike's write shape carries the deltas, and the read-back fills every default
# (03-rich-cells.json).
_STYLE_FLAG_WIRE = {
    "bold": "bold",
    "italic": "italic",
    "strikethrough": "strikeThrough",
    "underline": "underline",
}


class MultiSelectLabelError(LarkConfigError):
    """A multi-select option label is unrepresentable — a **comma** inside it.

    The multi-select read-back is a **comma-joined string**, so a comma inside a
    label cannot round-trip; :func:`encode_multi_select` refuses it here rather than
    silently corrupt the value. Under :class:`~larkdocio.errors.LarkConfigError` (an
    unsupported-input problem), so ``except LarkConfigError`` / ``except LarkDocIOError``
    catch it.
    """


#: **The write/read asymmetry, stated once** (LD-190) — quoted verbatim by ``GUIDE.md`` and
#: by ``SHEETS.md`` (in the source repository, not in the wheel), so the three cannot drift. The
#: colors go OUT positionally and come back under a
#: different field, which larkdocio does not read: an absence a consumer would otherwise
#: discover by writing colors and finding nothing to compare them against.
DROPDOWN_COLORS_NOT_READ_BACK = (
    "A DROPDOWN'S COLORS CANNOT BE READ BACK THROUGH larkdocio. They are written POSITIONALLY "
    "as options.colors[] — entry i colours condition value i, which is the only reason the "
    "1:1-length rule that highlightValidData:true enforces matters — but Lark reports them back "
    "under a DIFFERENT field, options.colorValueMap (a value-to-colour map, not a positional "
    "array), and larkdocio ships no data-validation READ leg at all, so that field appears "
    "nowhere in the library. Consequence, plainly: you can set a dropdown's colors and you "
    "cannot verify them here — check them in the Lark UI, or keep the colors array you wrote as "
    "your own record. The read leg (dataValidation GET/UPDATE/DELETE) is a deliberately deferred "
    "rung of its own, not an oversight; what is fixed here is the silence about it."
)


class DropdownColorsError(LarkConfigError):
    """A dropdown rule turns on ``highlightValidData`` without a 1:1 ``colors`` array.

    The **`90204`** caveat: Lark rejects a list rule whose
    ``highlightValidData`` is ``true`` unless a ``colors`` array **1:1** with the
    ``conditionValues`` accompanies it. :func:`encode_dropdown_rule` refuses the mismatch
    **before the write** (a typed error, never a live ``90204`` round-trip). Under
    :class:`~larkdocio.errors.LarkConfigError` (an unsupported-input problem), so
    ``except LarkConfigError`` / ``except LarkDocIOError`` catch it — the sibling of
    :class:`MultiSelectLabelError`.
    """


def encode_hyperlink(link: str, text: str = None) -> dict:
    """A hyperlink cell — ``{"type":"url","text","link"}``.

    ``text`` defaults to ``link`` (a bare link renders as its own label).
    """
    return {"type": "url", "text": link if text is None else text, "link": link}


def encode_styled_run(
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    strikethrough: bool = False,
    underline: bool = False,
    fore_color: str = None,
    font_size: int = None,
) -> dict:
    """One styled run — ``{"type":"text","text","segmentStyle":{…}}``.

    ``segmentStyle`` carries **only the style keys actually set** (a truthy flag, or a
    non-``None`` ``fore_color`` / ``font_size``), matching the spike's write shape; the
    read-back fills the remaining defaults. Snake_case params map to the wire
    ``strikeThrough`` / ``foreColor`` / ``fontSize`` names.
    """
    flags = {"bold": bold, "italic": italic,
             "strikethrough": strikethrough, "underline": underline}
    style: dict = {
        _STYLE_FLAG_WIRE[name]: True for name, on in flags.items() if on
    }
    if fore_color is not None:
        style["foreColor"] = fore_color
    if font_size is not None:
        style["fontSize"] = font_size
    return {"type": "text", "text": text, "segmentStyle": style}


def encode_styled_runs(runs) -> list:
    """A styled-runs cell — a list of :func:`encode_styled_run` segments.

    ``runs`` is a sequence of mappings, each a kwargs bundle for
    :func:`encode_styled_run` (``{"text": …, "bold": True, …}``), so the cell is
    ``[{"type":"text",…}, …]`` — the ``segmentStyle`` array the spike wrote.
    """
    return [encode_styled_run(**dict(run)) for run in runs]


def encode_mention(open_id: str, *, notify: bool = False,
                   grant_read_permission: bool = False) -> dict:
    """An @user-mention cell — ``{"type":"mention","text":<open_id>,"textType":"openId",
    "notify":false,"grantReadPermission":false}``.

    ``notify`` + ``grant_read_permission`` default to **false** (least surprise / least
    privilege — nobody is pinged, no permission is granted); both are **opt-in**
    overrides.
    """
    return {
        "type": "mention",
        "text": open_id,
        "textType": "openId",
        "notify": bool(notify),
        "grantReadPermission": bool(grant_read_permission),
    }


def mention_open_ids(value) -> tuple:
    """Every distinct ``open_id`` mentioned anywhere inside ``value`` — first-seen order.

    The **decoder half of** :func:`encode_mention`, and deliberately its neighbour: the
    mention wire shape is defined once here, so the plan-time **id validation** reads it
    from the same place the writer builds it and the two cannot drift.

    ``value`` is any proposed-write payload — a values **matrix**, a single cell, a
    ``segmentStyle`` run array, or a structural descriptor — walked recursively, so a
    mention is found wherever it rides (a 1×1 rich cell, a styled-run array, the rows of an
    ``AppendRowsWithValues``). Only a ``{"type": "mention", "textType": "openId"}`` object
    with a non-empty string ``text`` counts; anything else is ignored (an ``open_id`` is the
    only mention form this surface writes).
    """
    found: list = []
    _collect_mention_open_ids(value, found)
    return tuple(found)


def _collect_mention_open_ids(node, found: list) -> None:
    """Recursive worker for :func:`mention_open_ids` (dicts and lists, depth-first)."""
    if isinstance(node, dict):
        if node.get("type") == "mention" and node.get("textType") == "openId":
            open_id = node.get("text")
            if isinstance(open_id, str) and open_id and open_id not in found:
                found.append(open_id)
        for item in node.values():
            _collect_mention_open_ids(item, found)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _collect_mention_open_ids(item, found)


def normalize_multi_select(value) -> tuple:
    """Normalize either multi-select wire form to the **same ordered label-set** tuple.

    Delegates to the shared :meth:`~larkdocio.sheets.cell_model.MultiSelect.from_wire`
    (reuse, not a fork), which unifies the ``{"type":"multipleValue","values":[…]}``
    write object and the comma-joined read string (``"Red,Green"`` / ``"Red, Green"``)
    to the same order-preserving ``options`` tuple — the load-bearing asymmetry, so a
    differ / round-trip check compares like-for-like.
    """
    return MultiSelect.from_wire(value).options


def encode_multi_select(labels) -> dict:
    """A multi-select cell — ``{"type":"multipleValue","values":[…]}``.

    Labels are normalized to an **ordered label set** (each stripped, empties dropped,
    order preserved). A label containing a **comma** is unrepresentable (the read form is
    comma-joined) → a typed :class:`MultiSelectLabelError` (never a silent corruption).
    """
    values = []
    for raw in labels:
        label = str(raw).strip()
        if not label:
            continue
        if "," in label:
            raise MultiSelectLabelError(
                f"multi-select option label {label!r} contains a comma; the multi-select "
                "read-back is a comma-joined string so a comma inside a label is "
                "unrepresentable — refusing rather than silently corrupt the value."
            )
        values.append(label)
    return {"type": "multipleValue", "values": values}


def encode_dropdown_rule(condition_values, *, multiple_values: bool = False,
                         highlight_valid_data: bool = False, colors=None) -> dict:
    """A dropdown (list) **rule** payload — the ``dataValidation`` family.

    Builds ``{"dataValidationType":"list","dataValidation":{"conditionValues":[…],
    "options":{"multipleValues":…,"highlightValidData":…}}}`` — the range-independent rule
    (the target range is the client's job, forced through
    :func:`~larkdocio.sheets.write_client.normalize_write_range`). ``multiple_values`` picks
    a single- vs multi-select rule.

    **The `90204` colors caveat.** ``highlight_valid_data`` defaults **False**; turning it
    **True** requires a ``colors`` array **1:1** with ``condition_values`` (else Lark rejects
    the write ``90204``) — a mismatch (missing, or a different length) is refused **here,
    before the write**, with a typed :class:`DropdownColorsError`. With highlight **off**, a
    stray ``colors`` argument is dropped (it is meaningless without the highlight) so the wire
    shape stays the highlight-off form (the exact ``03b-dropdown.json`` capture).
    """
    values = list(condition_values)
    options = {
        "multipleValues": bool(multiple_values),
        "highlightValidData": bool(highlight_valid_data),
    }
    if highlight_valid_data:
        if colors is None or len(list(colors)) != len(values):
            supplied = "none" if colors is None else str(len(list(colors)))
            raise DropdownColorsError(
                f"highlightValidData:true needs a `colors` array 1:1 with the "
                f"{len(values)} conditionValues (Lark rejects a mismatch with 90204); "
                f"got {supplied} colors — refusing before the write. Supply matching "
                f"colors or leave highlightValidData false."
            )
        options["colors"] = list(colors)
    return {"dataValidationType": "list", "dataValidation": {
        "conditionValues": values, "options": options,
    }}
