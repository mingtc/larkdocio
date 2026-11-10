"""larkdocio.drive.walk — the depth-first folder walker (LD-324).

Recursion is **the same endpoint with one parameter changed**: a child whose ``type`` is
``folder`` is listed by handing its own token back to
:meth:`~larkdocio.drive.client.DriveClient.list_folder_children_to_exhaustion`. The round-2
probe walked a real 4-level, 35-node tree in **7 listing calls** that way (its capture
``tests/captures/drive-spike/captures/11-real-tree-walk.json`` is in the source repository), and this walker
reproduces that order exactly — a folder's children first, then a depth-first descent into each
folder child in listing order.

**THE VISITED-SET IS MANDATORY, AND ITS HAZARD IS UNPROVEN — deliberately in that order.**
Neither probe tree contained a ``shortcut`` child, so a shortcut cycle has
**never been observed**: the risk is asserted from the SDK's own model
(``ShortcutInfo{target_type, target_token}``), not from a capture. That is precisely why the
guard is built now rather than the day someone hits one — and why a token met twice is
**disclosed** (:class:`~larkdocio.drive.models.CycleDisclosure`) rather than silently pruned.
Resolving a shortcut's target is LD-325's job; refusing to loop is this module's.

**Every cap is explicit, defaulted and finite, and a cap that fires is DISCLOSED.** A silent
truncation is the same class of defect as a silent drop: it makes the enumeration lie about the
folder. So :class:`~larkdocio.drive.models.FolderWalk` carries a truncation record naming which
cap fired, where, and what was not visited — and ``walk.complete`` is ``False`` whenever
anything was truncated, refused or met twice.

A subfolder that **refuses** mid-walk never fails the whole walk; it is disclosed the same way
(a refused root still raises, because there is nothing to enumerate).
"""
from larkdocio.drive.errors import DriveError
from larkdocio.drive.models import (
    CycleDisclosure,
    FolderWalk,
    RefusedFolder,
    Truncation,
    WalkedChild,
)

#: Maximum depth of children below the root. **8** — the round-2 probe's own runaway guard,
#: which a real 4-level tree never came near.
DEFAULT_MAX_DEPTH = 8

#: Total children one walk may collect. 5000 is far above any observed tree (the maintainer's real one
#: held 35) and far below anything that would page for hours.
DEFAULT_MAX_CHILDREN = 5000

#: Total listing calls one walk may spend. 200 against the 7 that covered a 35-node tree.
DEFAULT_MAX_CALLS = 200


def walk_folder(client, folder_token, *, max_depth=DEFAULT_MAX_DEPTH,
                max_children=DEFAULT_MAX_CHILDREN, max_calls=DEFAULT_MAX_CALLS,
                page_size=None, max_pages=None) -> FolderWalk:
    """Walk ``folder_token`` depth-first and return everything found — and everything not.

    **The two arguments, because neither is what a caller first assumes.**

    * ``client`` is **required and positional** — this function constructs none. Build one with
      :meth:`DriveClient.from_read_credentials()
      <larkdocio.drive.client.DriveClient.from_read_credentials>`. (:func:`read_folder
      <larkdocio.drive.read.read_folder>` is the layer above and *will* build one when its
      ``client=`` keyword is omitted; this layer will not, because it is the layer you reach for
      precisely when you want to choose the client.)
    * ``folder_token`` is a **bare token, never a URL.** ``read_folder`` accepts either and
      parses a link for you; this one does not, and a URL handed here is sent to Lark as if it
      were a token. Hand it ``validate_download_url(url)[2]``
      (:func:`larkdocio.common.url.validate_download_url`), which is the shipped parse.

    What comes back is a :class:`~larkdocio.drive.models.FolderWalk`: ``.children`` is one
    :class:`~larkdocio.drive.models.WalkedChild` per node (each ``.child`` being the listing row
    itself, with its ``modified_time`` and ``owner_id``), and ``.complete`` is the one boolean
    to read before trusting any of it.

    Caps, all explicit, all finite, each disclosed when it fires:

    * ``max_depth`` (default **8**) — the probe's runaway guard; a folder child at the limit is
      listed but not descended into;
    * ``max_children`` (default **5000**) — the total the walk may collect;
    * ``max_calls`` (default **200**) — the total listing calls it may spend;
    * ``page_size`` / ``max_pages`` — passed to the client's own exhaustion loop, whose page
      budget is disclosed on the walk result too rather than swallowed at the folder boundary.

    The ``seen`` set is carried exactly as the round-2 probe's ``walk()`` does — mandatory even
    though a **shortcut cycle has never been observed** (§ O5): the hazard is asserted from the
    SDK model, so the guard exists before the first one is met.
    """
    children: list = []
    truncations: list = []
    cycles: list = []
    refusals: list = []
    seen = {folder_token}
    listing_calls = 0
    max_depth_reached = 0
    #: The depth-first frontier: folders discovered and not yet listed, in walk order.
    frontier = [(folder_token, "", 0)]

    def stop(cap, limit, token, path, remaining, detail=""):
        truncations.append(Truncation(
            cap=cap, limit=limit, at_folder=str(token), at_path=path or str(token),
            not_visited=tuple(remaining), detail=detail))

    while frontier:
        token, path, depth = frontier.pop(0)

        if listing_calls >= max_calls:
            stop("max_calls", max_calls, token, path,
                 [p or t for t, p, _d in [(token, path, depth)] + frontier],
                 detail="raise max_calls to walk the rest of the tree.")
            break

        kwargs = {"page_size": page_size}
        if max_pages is not None:
            kwargs["max_pages"] = max_pages
        try:
            contents = client.list_folder_children_to_exhaustion(token, **kwargs)
        except DriveError as exc:
            if depth == 0:
                raise
            refusals.append(RefusedFolder(
                token=token, path=path,
                note=(f"this subfolder could not be listed and the rest of the walk "
                      f"continued: {exc}")))
            continue

        listing_calls += contents.pages
        if contents.truncation is not None:
            truncations.append(contents.truncation)

        discovered = []
        for index, child in enumerate(contents.children):
            if child.token in seen:
                cycles.append(CycleDisclosure(
                    token=child.token,
                    path=f"{path}/{child.name}",
                    first_seen_path=_first_seen(children, child.token, folder_token),
                    note=("this token was already visited in this walk, so the walk did not "
                          "follow it again — a cycle, disclosed rather than pruned in "
                          "silence"),
                ))
                continue
            if len(children) >= max_children:
                remaining = [f"{path}/{c.name}" for c in contents.children[index:]]
                remaining += [p or t for t, p, _d in frontier]
                stop("max_children", max_children, token, path, remaining,
                     detail="raise max_children to collect the rest of the folder.")
                return _result(folder_token, children, truncations, cycles, refusals,
                               listing_calls, max_depth_reached)
            seen.add(child.token)
            child_path = f"{path}/{child.name}"
            children.append(WalkedChild(child=child, depth=depth + 1, path=child_path))
            max_depth_reached = max(max_depth_reached, depth + 1)
            if child.is_folder:
                discovered.append((child.token, child_path, depth + 1))

        if discovered and depth + 1 >= max_depth:
            stop("max_depth", max_depth, token, path, [p for _t, p, _d in discovered],
                 detail="raise max_depth to descend further.")
            continue
        frontier[:0] = discovered

    return _result(folder_token, children, truncations, cycles, refusals,
                   listing_calls, max_depth_reached)


def _first_seen(children, token, root_token):
    for walked in children:
        if walked.child.token == token:
            return walked.path
    return f"the walk's own root ({root_token})"


def _result(root_token, children, truncations, cycles, refusals, listing_calls,
            max_depth_reached) -> FolderWalk:
    return FolderWalk(
        root_token=root_token,
        children=tuple(children),
        truncations=tuple(truncations),
        cycles=tuple(cycles),
        refusals=tuple(refusals),
        listing_calls=listing_calls,
        max_depth_reached=max_depth_reached,
    )
