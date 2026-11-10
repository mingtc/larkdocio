"""larkdocio.drive.errors — the Drive enumeration's typed refusals (LD-324).

**The one rule this module exists to keep: a refusal that cannot know may not claim to.**

The captures and the guard named below live **in the source repository**, not in the wheel.

Lark answers a folder listing it will not serve with ``HTTP 400 {"code": 1061002,
"msg": "params error."}`` — and the drive spike established that **three distinct causes
collapse onto that single code**: a malformed folder token
(``tests/captures/drive-spike/captures/04-list-files-invalid-folder.json``), a **well-formed token of the
identical 27-character shape** for a folder this caller cannot reach
(``13-wellformed-fake-folder.json``), and a bad parameter value (``14-option-param.json``).
The two token cases are **byte-identical** in the response. A typed ``FolderNotFound`` is
therefore **not expressible** from what Lark returns, and inventing one would be a guess wearing
a type's clothing — so :data:`REFUSAL_SENTENCE` names both possibilities, attributes neither,
and says outright that larkdocio does not guess.

``1061003`` — the drive family's captured **not-found** code, recorded at
``larkdocio.base.media`` — keeps its own type here. Folding it into the 1061002 refusal would
throw away the one drive code that does distinguish something.
"""
from larkdocio.errors import LarkAPIError

#: The generic params refusal the whole drive family answers with.
FOLDER_REFUSED_CODE = 1061002

#: The family's captured not-found code — a DIFFERENT answer, kept a different type.
#: (``larkdocio.base.media`` records it from the media side.)
DRIVE_NOT_FOUND_CODE = 1061003

#: ``(what it was, the capture that established it)`` — the three causes, as data, so a caller
#: (and a reader of the traceback) can see WHY the refusal refuses to diagnose.
REFUSAL_CAUSES = (
    ("a malformed folder token", "04-list-files-invalid-folder.json"),
    ("a well-formed token of the identical 27-character shape, for a folder this caller "
     "cannot reach", "13-wellformed-fake-folder.json"),
    ("a bad parameter value", "14-option-param.json"),
)

#: THE SENTENCE. Both possibilities, neither diagnosed. Pinned verbatim by the enumeration
#: client's own guard (``tests/test_drive_enumeration_client.py``, in the source repository) so a later
#: edit that "tightens" it into a diagnosis reddens.
REFUSAL_SENTENCE = (
    "Lark refused this folder token (1061002): it may not exist, or you may not have access. "
    "Lark answers three distinct causes with this one code, so larkdocio cannot tell them "
    "apart and does not guess which applies."
)


class DriveError(LarkAPIError):
    """Base for every typed Drive-enumeration failure."""


class FolderRefusedError(DriveError):
    """Lark refused a folder token with ``1061002`` — cause unknowable, and not guessed.

    Carries the offending ``token`` and the three :data:`REFUSAL_CAUSES` with their captures,
    so the honesty is inspectable data rather than only prose in a message.
    """

    def __init__(self, message, *, code=None, msg=None, token=None,
                 causes=REFUSAL_CAUSES):
        super().__init__(message, code=code, msg=msg)
        self.token = token
        self.causes = tuple(causes)


class DriveObjectNotFoundError(DriveError):
    """Lark answered ``1061003`` — the family's captured not-found. Distinct on purpose."""

    def __init__(self, message, *, code=None, msg=None, token=None):
        super().__init__(message, code=code, msg=msg)
        self.token = token


class PaginationStalledError(DriveError):
    """The page loop could not make progress, so it stopped instead of spinning.

    Three shapes, all of them a server-side contradiction rather than a caller error: the same
    ``next_page_token`` handed back twice, ``has_more: true`` with no token at all, and an
    empty page that still claims there is more. Each is a **typed** stop — the alternative is a
    loop that never ends, which is the one outcome a walker may not have.
    """


def folder_refused(token, *, code=FOLDER_REFUSED_CODE, msg=None):
    """The honest refusal for ``token`` — one constructor, so every path says the same thing."""
    return FolderRefusedError(
        f"{REFUSAL_SENTENCE} (folder token: {token})",
        code=code, msg=msg, token=token,
    )


def drive_not_found(token, *, code=DRIVE_NOT_FOUND_CODE, msg=None):
    """The ``1061003`` answer, which DOES say something: Lark reports no such drive object."""
    return DriveObjectNotFoundError(
        f"Lark reports no such drive object ({DRIVE_NOT_FOUND_CODE}) for token: {token}",
        code=code, msg=msg, token=token,
    )
