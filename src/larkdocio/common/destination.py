"""larkdocio.common.destination — THE CALLER-SUPPLIED-DESTINATION RULE, in one place.

**The rule: if you do not say where, nothing is created.** Every verb that makes a **new
top-level object** — a document, a spreadsheet, a Base, a copy of a Base, a folder, an uploaded
file — requires a destination the caller supplies, and refuses **locally, before any call**,
when none is given. This library picks no default place and creates no folder to put things in;
inventing a destination is the same guess one level up.

**Why it is a rule and not a preference — measured, not asserted.** With no destination Lark
files the object in the *application identity's own space*. That space has **no human interface
at all**, not even for an account holding full tenant administration: it cannot be browsed, its
trash cannot be listed, and ``delete`` there is a **trash, not a purge** — the object's metadata
still resolves afterwards. An object put there is reachable only through a token somebody kept,
so a stray is effectively permanent. The measurements, and the accumulation they explain, are
unpublished recordings of the media-purge probe, including an orphan that still resolves.

**One public value is NOT a destination:** :meth:`larkdocio.drive.client.DriveClient.root_folder_token`.
It answers the token of the *application identity's own root* — the very space the paragraph
above is about — so it must **not** be passed as ``folder_token`` to any create. It stays public
and stays in the drive-read matrix because reading it is how you inspect that space; using it as
a destination is how objects end up somewhere no human interface can browse. A destination is a
folder **a person** can open.

**And it is now refused by type, not only by rule.** That accessor returns an
:class:`ApplicationRootToken` — a ``str`` subclass, so every existing string use of it is
unchanged — and :func:`require_destination` refuses that type outright, locally, before any
call. **The limit, stated because it is narrower than the rule above:** what is refused is the
value this library's own accessor handed you. A raw root token *copied in from elsewhere*
arrives as an ordinary string and cannot be told apart from a folder you own. Closing that gap
would mean resolving the root inside the fence — a network call and a wider permission
requirement on every create — so the fence stays local and the gap is disclosed instead.

**This generalises a shape already shipped twice**, and both keep their own wording because both
carry their own measurement:

* :func:`larkdocio.drive.folders_write.check_parent_token` — ``parent_token`` is required, and
  the **empty string** is refused rather than forwarded *because Lark accepts it and files the
  folder in the calling app's own root*. That measurement is the whole reason the empty string
  is refused here too, on every verb;
* :meth:`larkdocio.drive.files_write.DriveFilesWriteClient._refuse_unaddressed` — ``folder_token``
  is a required keyword on every upload leg.

**What this module deliberately does not do.** It does not create the destination, look one up,
remember a previous one, or read an environment variable to find one. A library that picks the
place is the behaviour the rule removes.
"""
from larkdocio.common.errors import MissingDestinationError


class ApplicationRootToken(str):
    """The token of the *application identity's own root* — a ``str``, and never a destination.

    Returned by :meth:`larkdocio.drive.client.DriveClient.root_folder_token`, which stays
    public because reading that space is how you inspect it. **It is a ``str`` subclass**, so it
    concatenates, compares, formats, hashes, keys a dict and JSON-serialises exactly as the
    plain token did — nothing that already worked changes.

    What the type adds is one thing: :func:`require_destination` can refuse it **locally,
    before any call**, with no client, no credentials and no permission this library did not
    already need. The type marks *provenance* — this value came out of that accessor — not
    non-emptiness: when the response carries no token the accessor still answers an empty
    ``ApplicationRootToken``, which is falsy and equal to ``""`` just as it always was, and is
    refused as "no destination" rather than as "the root".

    **The limit.** Every string derived from it — stripped, sliced, or passed back through the
    ``str`` constructor — is a plain ``str`` again, and a raw root token *copied in from
    elsewhere* was never this type at all. So the refusal covers the value the accessor handed
    you and nothing wider.
    """

    __slots__ = ()


#: The rule itself, in one sentence, consumer-voiced. Every refusal carries it verbatim so a
#: caller meets one statement of the rule rather than a family of paraphrases.
DESTINATION_RULE = (
    "the destination is the caller's: this library creates nothing in a place you did not "
    "name, because an object created with no destination lands in the application's own "
    "space, which no human interface can browse — deleting it there only trashes it, and what "
    "you lose track of you cannot recover"
)

#: The one value this library hands out that is NOT a destination, refused by TYPE rather than
#: by prose alone (LD-581 — the free half of P6; the root-resolving variant was priced and left
#: unruled because it would pull a drive-read endpoint into every create). It POINTS AT
#: ``DESTINATION_RULE`` for why that space is fatal instead of paraphrasing the measurement into
#: a second thing to keep true, and it carries the guarantee's LIMIT in its own last clause.
ROOT_IS_NOT_A_DESTINATION = (
    "that token is the application's own root — the value DriveClient.root_folder_token() "
    "answers, and the one place this rule exists to keep objects out of, for the reason the "
    "rule above gives. It is refused by type, so what this library can refuse is the value its "
    "own accessor handed you: a raw root token copied in from elsewhere arrives here as an "
    "ordinary string and cannot be told apart from a folder you own"
)

#: What to supply — the actionable half.
WHAT_TO_SUPPLY = (
    "pass folder_token= the token of a folder you own, created, or were given access to"
)

#: How to get one. Both routes are things a caller can do today, with no further permission —
#: and the one with **no permanent consequence leads**, because the other one has one and this
#: refusal must not steer a caller into it (LD-565).
HOW_TO_GET_A_DESTINATION = (
    "to get one: open a folder in your own Drive and use the token from its link, or create a "
    "folder with create_folder(name, parent_token)"
)

#: What the second route costs, said before the caller takes it. Both facts are quoted from
#: ``larkdocio.drive.folders_write``'s own rows: the delete row of ``R3_NOT_SHIPPED`` (a
#: **measured** route left unshipped — the call answered ``code:0`` and a re-query reported the
#: token gone; it is this library that does not ship the verb, never Lark that cannot) and
#: ``DUPLICATE_NAME_BEHAVIOUR`` (the same name twice makes a second folder).
WHAT_A_FOLDER_COSTS = (
    "what making one costs, before you make one: this library ships no verb that deletes a "
    "folder — the Drive delete route was measured to work and was left unshipped under the "
    "one-verb ruling, so a folder created through larkdocio is permanent as far as this "
    "library is concerned — and creating the same name twice under the same parent makes a "
    "second folder rather than reusing the first, so a retry is not idempotent"
)


def require_destination(folder_token, *, what):
    """Return ``folder_token``, or refuse — **locally, before any call**.

    ``what`` names what was being created ("a document", "a spreadsheet", "a Base", "a copy of
    a Base"), so the refusal says which call it came from without the caller re-deriving it
    from a traceback.

    Every spelling of "no destination" is refused identically: ``None``, the empty string, and
    a whitespace-only string. The empty string is the load-bearing one — **Lark accepts it**
    and files the object in the calling application's own root, so forwarding it would be the
    silent default this rule exists to remove.

    **One real token is refused too:** an :class:`ApplicationRootToken`, the value
    :meth:`larkdocio.drive.client.DriveClient.root_folder_token` answers. A **type check** is
    what keeps that refusal local — no client is constructed, no credential is read, no request
    is sent, and no permission is needed that a create did not already need. Resolving the root
    and comparing tokens would be the alternative, and it would turn this local seam into a
    networked one on every create; the type check does not.

    **Its limit, because it is narrower than the sentence above.** What is refused is the value
    the accessor itself handed you. A raw root token *copied in from elsewhere* is an ordinary
    string here and is accepted, as is any string derived from the typed one. That gap is
    disclosed rather than closed, because closing it costs the locality this function promises
    in its first line.
    """
    if folder_token is None or not str(folder_token).strip():
        raise MissingDestinationError(
            f"{what} needs a destination — {DESTINATION_RULE}. Nothing was sent: "
            f"{WHAT_TO_SUPPLY}. {HOW_TO_GET_A_DESTINATION}. {WHAT_A_FOLDER_COSTS}."
        )
    # The blankness test stays FIRST, so an empty answer from the accessor keeps the message it
    # already had: it IS "no destination", and a root-specific message there would be untrue.
    if isinstance(folder_token, ApplicationRootToken):
        raise MissingDestinationError(
            f"{what} needs a destination — {DESTINATION_RULE}. "
            f"{ROOT_IS_NOT_A_DESTINATION}. Nothing was sent: {WHAT_TO_SUPPLY}. "
            f"{HOW_TO_GET_A_DESTINATION}. {WHAT_A_FOLDER_COSTS}."
        )
    return folder_token
