"""The credential requirements — the READ/WRITE app split, which is code truth.

LD-244: the verbatim pre-split slice, lines 1240-1266 of the
2,770-line ``capabilities.py``. Nothing in it was rewritten.
"""
from larkdocio.common.auth import LEGACY_ENV, READ_ENV, WRITE_ENV

from ._models import Credentials

# --------------------------------------------------------------------------- #
# Credential requirements — the READ/WRITE app split, which is CODE TRUTH (the  #
# auth env tuples). The SCOPE lists are deliberately NOT passed in here: they    #
# are projected in the permissions pass from each surface's own operations, so   #
# no scope string is asserted twice and no surface can claim one its operations  #
# do not need. Only the human ``note`` is authored per surface.                  #
# --------------------------------------------------------------------------- #

def _read_credentials(note=None) -> Credentials:
    return Credentials(
        app="read",
        env_primary=list(READ_ENV),
        env_fallback=list(LEGACY_ENV),
        note=note,
    )


def _write_credentials(note=None) -> Credentials:
    # The write path NEVER falls back to read/legacy creds (credential doctrine).
    return Credentials(
        app="write",
        env_primary=list(WRITE_ENV),
        env_fallback=[],
        note=note,
    )


