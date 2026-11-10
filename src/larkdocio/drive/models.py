"""larkdocio.drive.models — the typed shapes the Drive enumeration returns (LD-324).

Everything here is a **faithful carrier of what Lark said**, not an interpretation of it:

* :class:`FolderChild` keeps all nine fields the listing returns, including the ready-to-use
  ``url`` (present on 9/9 children in round 1 and 27/27 documents in round 2) and Lark's own
  raw ``type`` string — the ``sheet``/``bitable`` → ``sheets``/``base`` translation is
  LD-325's seam, and pre-translating it here would put the seam in two places.
* :class:`FolderContents` carries one folder's children **and its truncation, if any**, so a
  page budget that fires cannot be lost between the client and its caller.
* :class:`Truncation` is the disclosure object AC4 is about: which cap, where, and what was
  not visited. A silent truncation is the same class of defect as a silent drop — it makes the
  enumeration lie about the folder.
"""
from dataclasses import dataclass, field
from typing import NamedTuple, Optional, Tuple


class AssetRef(NamedTuple):
    """One binary a read child REFERENCED — the token and which fetch path retrieves it.

    A projection of a parse the read already did, never a second reading of the
    Markdown and never an API call: the docx reader queues every image and whiteboard token on
    its parser as it walks the blocks, and this is that queue carried up to the walk so the
    ``folder --assets`` leg can fetch it. ``kind`` is ``"image"`` or ``"board"`` — two
    genuinely different endpoints (drive media download vs. the whiteboard PNG export), which
    is why the kind travels with the token instead of being guessed at fetch time.
    """

    token: str
    kind: str


#: The nine fields the listing returns per child (spike § I.A, capture 02).
CHILD_FIELDS = (
    "token", "name", "type", "parent_token", "url",
    "shortcut_info", "created_time", "modified_time", "owner_id",
)

#: Lark's own word for a child that is a folder — the one type this surface acts on.
FOLDER_TYPE = "folder"


@dataclass(frozen=True)
class FolderChild:
    """One child of a folder, exactly as the listing described it."""

    token: str
    name: Optional[str] = None
    type: Optional[str] = None
    parent_token: Optional[str] = None
    url: Optional[str] = None
    shortcut_info: Optional[dict] = None
    created_time: Optional[str] = None
    modified_time: Optional[str] = None
    owner_id: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: dict) -> "FolderChild":
        return cls(**{name: payload.get(name) for name in CHILD_FIELDS})

    @property
    def is_folder(self) -> bool:
        return self.type == FOLDER_TYPE


@dataclass(frozen=True)
class Truncation:
    """A cap that fired, disclosed: which one, where, and what was not visited."""

    cap: str
    limit: int
    at_folder: str
    at_path: str
    not_visited: Tuple[str, ...] = ()
    detail: str = ""

    def describe(self) -> str:
        """One sentence a consumer can act on."""
        where = self.at_path or self.at_folder
        head = (f"Enumeration stopped at the {self.cap} cap ({self.limit}) "
                f"in {where or 'the folder'}")
        tail = (f"; {len(self.not_visited)} not visited: "
                f"{', '.join(self.not_visited[:5])}"
                f"{'…' if len(self.not_visited) > 5 else ''}")
        return head + (tail if self.not_visited else "; nothing further was not visited") + (
            f". {self.detail}" if self.detail else ".")


@dataclass(frozen=True)
class FolderContents:
    """One folder's children, plus the truncation that fired while collecting them."""

    folder_token: Optional[str]
    children: Tuple[FolderChild, ...] = ()
    pages: int = 0
    has_more: bool = False
    next_page_token: Optional[str] = None
    truncation: Optional[Truncation] = None

    @classmethod
    def from_response(cls, response: dict, *, folder_token=None, pages: int = 1
                      ) -> "FolderContents":
        data = response.get("data") or {}
        return cls(
            folder_token=folder_token,
            children=tuple(FolderChild.from_dict(row) for row in (data.get("files") or [])),
            pages=pages,
            has_more=bool(data.get("has_more")),
            next_page_token=data.get("next_page_token") or None,
        )


@dataclass(frozen=True)
class FolderName:
    """A folder's own title — or the **disclosed** reason there isn't one.

    Never a synthesised title: ``name is None`` with a ``disclosure`` is the honest answer, and
    the folder renders by its token.
    """

    token: str
    name: Optional[str] = None
    disclosure: Optional[str] = None

    @property
    def resolved(self) -> bool:
        return self.name is not None


#: The three outcomes :class:`SecurityLevel` distinguishes — **in the type, never in a
#: comment**, because the difference between *the tenant set no level* and *this call could not
#: answer* is exactly the difference a consumer plans around.
LEVEL_REPORTED = "level-reported"
NO_LEVEL_SET = "no-level-set"
NOT_ANSWERED = "not-answered"
SECURITY_LEVEL_OUTCOMES = (LEVEL_REPORTED, NO_LEVEL_SET, NOT_ANSWERED)

#: WHERE the standing *unmeasured* list for this field is authored — cited from here, never
#: re-authored here, so there is one place to correct when any of it is measured.
SECURITY_LEVEL_UNMEASURED = (
    "What is unmeasured about a security level (unmeasured is not refuted) is authored in ONE "
    "place and cited from here: larkdocio.guide(), section \"The document's SECURITY LEVEL\", "
    "bullet \"What is unmeasured, not refuted\" — a user_access_token on this route is untried, "
    "the admin / console APIs are untried, product-internal endpoints the web client calls are "
    "untried, whether \"Label A\" is a stable id or a localised display string is unknown, whether "
    "the level gates the open API at all is unmeasured, and object types beyond docx are "
    "untried beyond one no-level Base control. Read that bullet rather than this sentence; "
    "this is a pointer to it."
)

#: What this library will and will not do with the field, said once and carried on the result.
SECURITY_LEVEL_NOT_SETTABLE = (
    "A security level is READABLE here and is settable by NO route this library ships: in the "
    "vendored SDK sec_label* appears only on response Meta models, and four probed spellings of "
    "a dedicated route each answered not found. Choosing a level is a human's action in the "
    "Lark client, or an administrator's in the console. larkdocio never sets, requests, widens "
    "or escalates one."
)


@dataclass(frozen=True)
class SecurityLevel:
    """A document's tenant **security level** as Lark reported it — or the **disclosed** reason
    there is no answer. The :class:`FolderName` pattern, applied to a second field.

    **Three outcomes, and they are three different things** (:data:`SECURITY_LEVEL_OUTCOMES`):

    * ``level`` is a non-empty string (``"Label A"``) — a level **was reported**;
    * ``level`` is ``""`` — the field came back **empty, which means NO LEVEL IS SET**. That
      reading is not an interpretation: on the fixture whose level a human had just chosen by
      hand the same call read back ``"Label A"``, while its own **before control** — the identical
      call on the identical token earlier the same day — read ``""``, and a **negative control**
      object with no level ever set also read ``""``. So ``""`` is a value, never an absence;
    * ``level`` is ``None`` with a ``disclosure`` — the key was **not present**, or the call
      could not answer. That is a disclosure, and a ``""`` is never invented to stand in for it.

    ``no_level_set`` and ``reported`` read the first two apart without anyone comparing to
    ``""`` at a call site; :attr:`outcome` names all three.

    The value is carried **exactly as Lark said it** — never normalised, mapped, translated or
    ranked, because whether ``"Label A"`` is a stable id or a localised display string is unknown
    (:data:`SECURITY_LEVEL_UNMEASURED`, reachable from :attr:`unmeasured`).
    """

    token: str
    level: Optional[str] = None
    disclosure: Optional[str] = None

    @property
    def reported(self) -> bool:
        """``True`` when Lark answered the field at all — including with ``""``."""
        return self.level is not None

    @property
    def no_level_set(self) -> bool:
        """``True`` only for the measured *empty means no level* case."""
        return self.level == ""

    @property
    def outcome(self) -> str:
        """Which of :data:`SECURITY_LEVEL_OUTCOMES` this answer is."""
        if self.level is None:
            return NOT_ANSWERED
        return NO_LEVEL_SET if self.level == "" else LEVEL_REPORTED

    @property
    def unmeasured(self) -> str:
        """The standing unmeasured list, by citation — see :data:`SECURITY_LEVEL_UNMEASURED`."""
        return SECURITY_LEVEL_UNMEASURED

    @property
    def not_settable(self) -> str:
        """Why nothing here writes a level — see :data:`SECURITY_LEVEL_NOT_SETTABLE`."""
        return SECURITY_LEVEL_NOT_SETTABLE


@dataclass(frozen=True)
class WalkedChild:
    """A child, with where in the tree the walk found it."""

    child: FolderChild
    depth: int
    path: str


@dataclass(frozen=True)
class CycleDisclosure:
    """A token the walk met twice — disclosed, never silently pruned."""

    token: str
    path: str
    first_seen_path: str
    note: str


@dataclass(frozen=True)
class RefusedFolder:
    """A subfolder the walk could not list. Disclosed; it never fails the whole walk."""

    token: str
    path: str
    note: str


@dataclass(frozen=True)
class FolderWalk:
    """The result of a depth-first walk: what was found, and everything that was not."""

    root_token: str
    children: Tuple[WalkedChild, ...] = ()
    truncations: Tuple[Truncation, ...] = ()
    cycles: Tuple[CycleDisclosure, ...] = ()
    refusals: Tuple[RefusedFolder, ...] = ()
    listing_calls: int = 0
    max_depth_reached: int = 0
    root_name: Optional[FolderName] = field(default=None)

    @property
    def subfolders(self) -> Tuple[WalkedChild, ...]:
        return tuple(walked for walked in self.children if walked.child.is_folder)

    @property
    def complete(self) -> bool:
        """``True`` only when nothing was truncated, refused or met twice — so a caller reading
        one boolean is never told a partial enumeration was the folder."""
        return not (self.truncations or self.cycles or self.refusals)

    def by_type(self) -> dict:
        counts: dict = {}
        for walked in self.children:
            counts[walked.child.type] = counts.get(walked.child.type, 0) + 1
        return counts
