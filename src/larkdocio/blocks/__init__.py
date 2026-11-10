from typing import Any, Callable, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from larkdocio.read.parser import Parser
    from larkdocio.model import Node

# A block handler takes the main Parser instance, the block object, and the
# current indent_level, and returns a typed model Node. The renderer serializes
# the node per its type (the inverse of the registry division). This is the final
# post-T2 contract: the LD-024 strangler shim allowed a handler to return EITHER a
# legacy Markdown string OR a Node during the migration; that string arm was
# removed in LD-032, so a handler now returns a Node only.
BlockHandler = Callable[["Parser", Any, int], "Node"]

BLOCK_REGISTRY: Dict[int, BlockHandler] = {}

def register_block(block_type: int):
    """Decorator to register a block handler for a specific block type enum."""
    def decorator(func: BlockHandler) -> BlockHandler:
        BLOCK_REGISTRY[block_type] = func
        return func
    return decorator

# Import modules to execute the decorators and register them
# These must be imported after the decorators are defined
from . import text
from . import headings
from . import lists
from . import table
from . import container
from . import media
from . import iframe
from . import callout
from . import file
from . import diagram
from . import synced
from . import quote
from . import divider
from . import embedded

def get_registry() -> Dict[int, BlockHandler]:
    return BLOCK_REGISTRY
