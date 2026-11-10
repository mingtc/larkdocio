import json
import logging

logger = logging.getLogger("larkdocio")

#: Where a bug report goes — **authored here, once**, and projected into this wheel's own
#: ``METADATA`` as ``Project-URL: Issues``. A guard in the source repository
#: (``tests/test_cli_refusal_uniformity.py``) holds the two byte-identical, so the banner below
#: and the package metadata cannot drift apart.
#:
#: LD-658 AC4: the banner below demanded a bug report while the package declared no project
#: urls at all, so the demand had no destination — a reader was told to report something and
#: given nowhere to report it.
ISSUES_URL = "https://github.com/mingtc/larkdocio/issues"


def check_err(e: Exception):
    logger.error(str(e))
    logger.error(
        f"{'='*20}\n\nReport the following if it is a bug — {ISSUES_URL}\n")
    raise e

def pretty_print(i: dict | list) -> str:
    return json.dumps(i, indent=2)
