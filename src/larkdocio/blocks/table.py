from typing import Any, List, Optional, Tuple, TYPE_CHECKING
from larkdocio.blocks import register_block
from larkdocio.model import Node, TableCellNode, TableNode

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser


def _table_prop(b: Any) -> Any:
    if getattr(b, 'table', None) and getattr(b.table, 'property', None):
        return b.table.property
    return None


def _extract_merges(prop: Any) -> List[Tuple[Optional[int], Optional[int]]]:
    """Pull the table's merge spans off the SDK ``TableProperty``.

    ``TableProperty.merge_info`` is a flat ``List[TableMergeInfo]`` that runs
    parallel to the table's cells in row-major order; each entry carries a
    ``row_span`` / ``col_span``. We flatten it into plain ``(row_span, col_span)``
    tuples so the model node stays free of SDK objects (dumb typed data).

    The RAW getattr values are kept — ``None`` is preserved rather than
    normalized — because the renderer reproduces the legacy handler's TWO
    distinct None rules: merge *detection* read ``getattr(...) or 0`` (a None
    span counts as 0, i.e. not a merge), while span *emission* used
    ``1 if x is None else x`` (a None span emits as a normal 1). Collapsing to a
    single default here would break one path or the other.
    """
    if prop is None:
        return []
    merge_info = getattr(prop, 'merge_info', None) or []
    return [(getattr(mi, 'row_span', None), getattr(mi, 'col_span', None))
            for mi in merge_info]


@register_block(31)  # Table
def handle_table(parser: "Parser", b: Any, indent_level: int) -> Node:
    """Build a :class:`~larkdocio.model.nodes.TableNode` (LD-027 model migration).

    The handler recurses each cell to a typed NODE (R-S3 carriage flip — a table
    recurses its cells at depth 0 via ``Parser._child_nodes``) and pulls the
    structural data (``column_size`` fold width, ``header_row`` promotion flag,
    merge spans) off the SDK block. ALL serialization — pipe/HTML escaping,
    folding, ragged padding, header promotion and the merged-cell HTML path — is
    the renderer's job. Output is byte-identical to the prior string handler.
    """
    if not b or not b.children:
        return TableNode()
    prop = _table_prop(b)
    col_size = 1
    if prop is not None:
        col_size = getattr(prop, 'column_size', 1) or 1

    # header_row defaults to True (Lark promotes the first row by default). Only
    # an explicit False suppresses promotion.
    header_row = getattr(prop, 'header_row', None) if prop is not None else None
    header_row = True if header_row is None else bool(header_row)

    return TableNode(
        cells=parser._child_nodes(b, 0),
        col_size=col_size,
        header_row=header_row,
        merges=_extract_merges(prop),
    )


@register_block(32)  # TableCell
def handle_table_cell(parser: "Parser", b: Any, indent_level: int) -> Node:
    """Build a :class:`~larkdocio.model.nodes.TableCellNode` (LD-027).

    Recurses the cell's child blocks to typed NODES via ``Parser._child_nodes``
    at ``indent_level`` 0 (R-S3 carriage flip — a cell recurses at depth 0); the
    renderer descends each child and concatenates the results verbatim
    (byte-identical to the prior ``"".join(...)`` over already-rendered strings).
    """
    return TableCellNode(children=parser._child_nodes(b, 0))
