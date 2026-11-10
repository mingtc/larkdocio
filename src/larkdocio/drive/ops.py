"""larkdocio.drive.ops — the Drive R1 op registry, with an EXPLICIT ``mutates`` flag (LD-324).

The ``larkdocio.base.ops`` rule, inherited unchanged: **``mutates`` is declared, never derived
from the HTTP verb.** This surface has its own reason to need that rule rather than only to
respect it — ``POST /open-apis/drive/v1/metas/batch_query`` is a **documented query** that
mutates nothing, and a registry that inferred "POST ⇒ write" would classify the leg that reads
a folder's own title as a write. :func:`read_only` then makes that claim mechanically checkable
instead of merely intended.

**LD-409 registered the surface's first MUTATING op** (``create_version``, a ``POST`` that
declares ``mutates: True`` beside a ``POST`` that declares ``False``). The read-only claim was
**transformed rather than deleted** — ``read_only()`` over the whole registry is now ``False``,
and ``read_only(ENUMERATION_OPS)`` carries forward the claim that was, and still is, true of
R1's three enumeration legs.

The other difference from the Base registry is the transport column. Two of these three
endpoints are **not SDK-modelled at all** — ``drive/explorer/v2/root_folder/meta`` is a legacy
family the pinned ``lark-oapi`` does not carry, and ``metas/batch_query`` is reached the same
way for one uniform code path — so each row records *which* transport it rides and the evidence
that it answers. Nothing new was built for them:
:class:`larkdocio.common.transport.CredentialedRawHttpClient` is the LD-126 precedent.
"""
import dataclasses
from dataclasses import dataclass
from typing import Optional, Tuple

from larkdocio.common.citations import dev_repo

#: Path prefix + the transport every leg rides.
RAW_HTTP = "raw-http (common.transport.CredentialedRawHttpClient)"

_CAPTURES = "tests/captures/drive-spike/captures"
_EDITION_CAPTURES = "tests/captures/editions-spike/captures"
_PERMISSION_CAPTURES = "tests/captures/permissions-spike/captures"
_FOLDER_CAPTURES = "tests/captures/ld467-create-folder/captures"

#: **The endpoints this surface reaches, as module-level constants — the ONE source.**
#: Each descriptor's ``endpoint`` reads from the matching constant here, and the client passes
#: the same constant explicitly as its call's ``path`` (behaviour-identical to the descriptor's
#: default). Naming them here rather than only inside the descriptor tuple is what lets the
#: capability layer's permission derivation *reach* them: it walks a call site's own source, and
#: an endpoint reachable only through ``op(name).endpoint`` at runtime is invisible to that walk —
#: so the derivation would report an enumeration call as needing no permission at all. A bare
#: module constant a source walk resolves to a string closes that without a second copy.
LIST_FILES_ENDPOINT = "/open-apis/drive/v1/files"
ROOT_FOLDER_META_ENDPOINT = "/open-apis/drive/explorer/v2/root_folder/meta"
METAS_BATCH_QUERY_ENDPOINT = "/open-apis/drive/v1/metas/batch_query"
#: The **versions** family (LD-409) — one path, two verbs: ``GET`` lists a file's named
#: versions, ``POST`` creates one. Written in the tokenised shape the table already uses for a
#: path with an id in the middle (cf. ``permissions.py``'s
#: ``/open-apis/drive/v1/files/:file_token/comments`` row), because a raw path built with the
#: token inside an f-string leaves only its literal prefix in the source — and the derivation
#: would then answer this family at the bare ``/open-apis/drive/v1/files`` row instead of its
#: own. ``larkdocio.drive.versions.versions_path`` substitutes the token from this one constant.
FILE_VERSIONS_ENDPOINT = "/open-apis/drive/v1/files/:file_token/versions"
#: The **permission MEMBER** family (LD-432) — one path, four verbs: ``GET`` reads a
#: document's members, ``POST`` adds one, ``PUT`` changes one's level and ``DELETE`` removes
#: one (the last two address ``…/members/{open_id}``, which resolves under this same prefix).
#: Tokenised for the same reason the versions family is: a path built with the token inside an
#: f-string leaves only its literal prefix in the source, and the derivation would then answer
#: this family at another row. The member family is **v1** — the ``v2`` spelling is not a route
#: at all (``tests/captures/permissions-spike/captures/703-``: ``404 page not found``, plain text).
PERMISSION_MEMBERS_ENDPOINT = "/open-apis/drive/v1/permissions/:file_token/members"
#: The **PUBLIC settings** family (LD-432) — the document-level switches, of which this surface
#: sets exactly two (``copy_entity`` / ``security_entity``). This half really is **v2**; only
#: the member half is v1, which is why the two are named separately rather than derived from
#: one prefix.
PERMISSION_PUBLIC_ENDPOINT = "/open-apis/drive/v2/permissions/:file_token/public"
#: **The ONE R3 organize verb that opened** (LD-467, maintainer ruling 2026-08-14): create a folder
#: under a parent. A row of its own rather than the bare ``/open-apis/drive/v1/files`` prefix
#: because the permission table answers the **longest** matching prefix, and filing a create
#: under the non-observation recorded for a folder *listing* would attribute one family's
#: silence to another's. The rest of the rung — move, rename, copy, delete, shortcut — is
#: **deliberately unregistered**, because this registry declares what the library calls.
FILES_CREATE_FOLDER_ENDPOINT = "/open-apis/drive/v1/files/create_folder"


@dataclass(frozen=True)
class DriveOpDescriptor:
    """One Drive R1 read op: what it calls, on which verb, and whether it mutates.

    * ``name`` — the op's name, and the name of the client method that implements it;
    * ``endpoint`` — the Lark path, exactly as the client composes it;
    * ``http_method`` — the verb. Recorded so a reader can *see* that the one ``POST``
      declares ``mutates: False``;
    * ``mutates`` — **mandatory, explicit, never inferred**;
    * ``paged`` — whether the op follows a cursor to exhaustion;
    * ``transport`` — which transport the leg rides, and why it is not the SDK;
    * ``sdk_modelled`` — whether the pinned SDK carries a request model for it at all;
    * ``evidence`` — the capture that proved it answers.
    """

    name: str
    endpoint: str
    http_method: str
    mutates: bool
    paged: bool
    transport: str
    sdk_modelled: bool
    evidence: str
    note: Optional[str] = None


#: The ordered registry — the ONE place a Drive R1 op is declared.
OPS: Tuple[DriveOpDescriptor, ...] = (
    DriveOpDescriptor(
        name="list_folder_children",
        endpoint=LIST_FILES_ENDPOINT,
        http_method="GET",
        mutates=False,
        paged=True,
        transport=RAW_HTTP,
        sdk_modelled=True,
        evidence=dev_repo(f"{_CAPTURES}/02-list-files-implicit-root.json · "
                          f"{_CAPTURES}/11-real-tree-walk.json · "
                          f"{_CAPTURES}/12-pagination-continuation.json"),
        note=("THE enumerator. SDK-modelled, but ridden raw so all three legs share one "
              "request/response path, one throttle and one refusal seam."),
    ),
    DriveOpDescriptor(
        name="root_folder_token",
        endpoint=ROOT_FOLDER_META_ENDPOINT,
        http_method="GET",
        mutates=False,
        paged=False,
        transport=RAW_HTTP,
        sdk_modelled=False,
        evidence=dev_repo(f"{_CAPTURES}/01-root-folder-meta.json"),
        note=("A LEGACY, non-SDK family (explorer/v2): the pinned lark-oapi models no request "
              "for it, so the raw-HTTP core is the only way in. Answers the caller's OWN root."),
    ),
    DriveOpDescriptor(
        # THE QUERY POST, and the row that is why `mutates` cannot be derived from the verb.
        name="folder_name",
        endpoint=METAS_BATCH_QUERY_ENDPOINT,
        http_method="POST",
        mutates=False,
        paged=False,
        transport=RAW_HTTP,
        sdk_modelled=True,
        evidence=dev_repo(f"{_CAPTURES}/06-metas-batch-query.json"),
        note=("A documented QUERY that changes nothing — the listing returns a folder's "
              "CHILDREN, never the folder's own title, so a rendered heading needs this. It "
              # LD-606 replaced this row's earlier no-capture conclusion (false since
              # 2026-08-15) while keeping its degradable-design reason in force; the ISSUE ID
              # stays in this comment because the note itself is consumer-reaching.
              "DOES resolve a FOLDER token, on a control pair (superseding this row's earlier "
              "no-capture reading): live folders resolve with their titles "
              "(ld514-04, 4 rows, 2026-08-19; ld467-25's single-token control, 2026-08-15) and "
              "a trashed folder token answers code:0 with metas: [] and failed_list "
              "[{code: 970005}] (ld467-13, 2026-08-15; 36 rows in ld514-04). The leg still "
              "degrades rather than assumes — that is what the measured NEGATIVE looks like, "
              "and it is why a code:0 here is read through failed_list."),
    ),
    DriveOpDescriptor(
        # THE SECOND DECLARED-READ POST, on the SAME documented endpoint as the row above — a
        # DOCUMENT's own metadata, for the tenant SECURITY LEVEL that rides it. Its own row rather
        # than a widening of `folder_name`, because the two send different `doc_type`s, answer
        # different types and degrade for different reasons; sharing a name would make the
        # refusal seam's context lie about which leg refused.
        name="document_security_level",
        endpoint=METAS_BATCH_QUERY_ENDPOINT,
        http_method="POST",
        mutates=False,
        paged=False,
        transport=RAW_HTTP,
        sdk_modelled=True,
        evidence=dev_repo(f"{_CAPTURES}/06-metas-batch-query.json"),
        note=("A documented QUERY that changes nothing, for ONE document token at a time. The "
              "reply's `sec_label_name` is the document's tenant security level — READABLE on "
              "this route (measured: the key comes back on a docx token) and settable by no "
              "route this library ships. The BATCHED form of this endpoint has no caller and "
              "no row: this leg sends exactly one `request_docs` entry."),
    ),
    DriveOpDescriptor(
        name="list_versions",
        endpoint=FILE_VERSIONS_ENDPOINT,
        http_method="GET",
        mutates=False,
        paged=True,
        transport=RAW_HTTP,
        sdk_modelled=True,
        evidence=dev_repo(f"{_EDITION_CAPTURES}/07-leg1-list-versions-read-pair-page-size-10"
                          f".json · "
                          f"{_EDITION_CAPTURES}/08-leg1-list-versions-page-size-1-pagination-"
                          f"probe.json · "
                          f"{_EDITION_CAPTURES}/09-leg1-list-versions-page-2-page-token-"
                          f"honoured.json"),
        note=("A file's NAMED versions — the semantic anchor a numeric revision cannot "
              "carry. Ridden raw for the same reason the enumerator is: one request path, "
              "one throttle, one refusal seam."),
    ),
    DriveOpDescriptor(
        # THE MUTATING POST, and the row that makes `mutates` provably a declaration rather
        # than a verb inference from BOTH sides: this surface now registers a POST that is a
        # read (folder_name) and a POST that is a write, and only the declaration tells them
        # apart. It is also the Drive surface's FIRST mutating op — see `read_only`.
        name="create_version",
        endpoint=FILE_VERSIONS_ENDPOINT,
        http_method="POST",
        mutates=True,
        paged=False,
        transport=RAW_HTTP,
        sdk_modelled=True,
        evidence=dev_repo(f"{_EDITION_CAPTURES}/02-leg0-leg2-create-version-write-pair-drive-"
                          f"v1-files-versions.json · "
                          f"{_EDITION_CAPTURES}/101-r2-head-revision-before-creating-a-version"
                          f".json · "
                          f"{_EDITION_CAPTURES}/103-r2-head-revision-after-creating-a-version-"
                          f"inertness.json"),
        note=("Additive and REVISION-INERT (head revision measured identical either side of "
              "the create), which is what makes the (name, token, revision) pairing exact "
              "absent a concurrent edit. WRITE pair only."),
    ),
    DriveOpDescriptor(
        # THE ONE R3 ORGANIZE VERB (LD-467). A THIRD declared-mutating POST, and the row that
        # says the rung opened by exactly one notch: no move, no rename, no copy, no delete and
        # no shortcut is registered here, because this registry declares what the library
        # CALLS — and a row nobody calls would read as a verb somebody could.
        name="create_folder",
        endpoint=FILES_CREATE_FOLDER_ENDPOINT,
        http_method="POST",
        mutates=True,
        paged=False,
        transport=RAW_HTTP,
        sdk_modelled=True,
        evidence=dev_repo(f"{_FOLDER_CAPTURES}/ld467-01-create-the-disposable-parent-under-the-"
                          f"bots-own-root.json · "
                          f"{_FOLDER_CAPTURES}/ld467-03-duplicate-probe-SECOND-create-same-name-"
                          f"same-parent.json · "
                          f"{_FOLDER_CAPTURES}/ld467-04-list-the-parent-after-two-identical-"
                          f"names.json"),
        note=("Creates ONE folder under a caller-named parent and answers exactly two keys, "
              "token and url. DUPLICATE NAMES MAKE A SECOND FOLDER (measured: the second "
              "create answered code:0 with a distinct token and the parent then listed two "
              "byte-identically named folders) — disclosed, never deduped. WRITE pair only."),
    ),
    # ---- the ACCESS family (LD-432): who may use a document the app created. ----
    DriveOpDescriptor(
        name="list_members",
        endpoint=PERMISSION_MEMBERS_ENDPOINT,
        http_method="GET",
        mutates=False,
        paged=False,
        transport=RAW_HTTP,
        sdk_modelled=True,
        evidence=dev_repo(f"{_PERMISSION_CAPTURES}/702-ld420-leg0-b-list-permission-members-"
                          f"of-a-doc-the-bot-just-created-v1.json · "
                          f"{_PERMISSION_CAPTURES}/708-ld420-leg1-c-independent-member-list-"
                          f"read-back-after-the-full-access-g.json"),
        note=("A READ on a WRITE surface, and the row that shows `mutates` is a declaration "
              "from the other direction again: a GET beside a DELETE, each saying for itself. "
              "The owner is NOT in this list — and what IS in it depends on where the "
              "document was filed: nothing at all with no folder, the folder's own rows "
              "(perm_type='container') when it was filed into one — so the op pairs it "
              "with the metas/batch_query owner leg."),
    ),
    DriveOpDescriptor(
        name="grant_access",
        endpoint=PERMISSION_MEMBERS_ENDPOINT,
        http_method="POST",
        mutates=True,
        paged=False,
        transport=RAW_HTTP,
        sdk_modelled=True,
        evidence=dev_repo(f"{_PERMISSION_CAPTURES}/707-ld420-leg1-b-grant-full-access-to-the-"
                          f"resolved-grantee-the-echo-not-th.json · "
                          f"{_PERMISSION_CAPTURES}/708-ld420-leg1-c-independent-member-list-"
                          f"read-back-after-the-full-access-g.json · "
                          f"{_PERMISSION_CAPTURES}/729-ld420-leg3-b-grant-edit-to-the-resolved-"
                          f"grantee.json"),
        note=("The THIRD declared-mutating POST in this registry, beside a POST that declares "
              "False. Read back independently on the same round, because THIS family produced "
              "the spike's one measured swallow (759- accepted, 760- not stored)."),
    ),
    DriveOpDescriptor(
        name="update_access",
        endpoint=PERMISSION_MEMBERS_ENDPOINT,
        http_method="PUT",
        mutates=True,
        paged=False,
        transport=RAW_HTTP,
        sdk_modelled=True,
        evidence=dev_repo(f"{_PERMISSION_CAPTURES}/731-ld420-ac8-update-raise-the-member-from-"
                          f"edit-to-full-access.json · "
                          f"{_PERMISSION_CAPTURES}/733-ld420-ac8-downgrade-lower-the-member-"
                          f"from-full-access-to-view.json"),
        note=("One route, BOTH directions — raising and lowering a member's level are the same "
              "call with a different `perm`, each measured with its own read-back."),
    ),
    DriveOpDescriptor(
        name="revoke_access",
        endpoint=PERMISSION_MEMBERS_ENDPOINT,
        http_method="DELETE",
        mutates=True,
        paged=False,
        transport=RAW_HTTP,
        sdk_modelled=True,
        evidence=dev_repo(f"{_PERMISSION_CAPTURES}/736-ld420-ac8-revoke-remove-the-member-"
                          f"entirely.json · "
                          f"{_PERMISSION_CAPTURES}/737-ld420-ac8-read-back-after-the-revoke"
                          f".json"),
        note=("The registry's first DELETE. A grant surface that cannot take a grant back is "
              "not shippable; the revoke REMOVES the row rather than tombstoning it."),
    ),
    DriveOpDescriptor(
        name="set_copy_permissions",
        endpoint=PERMISSION_PUBLIC_ENDPOINT,
        http_method="PATCH",
        mutates=True,
        paged=False,
        transport=RAW_HTTP,
        sdk_modelled=True,
        evidence=dev_repo(f"{_PERMISSION_CAPTURES}/709-ld420-ac3-patch-copy-entity-to-anyone-"
                          f"can-view-candidate-lever.json · "
                          f"{_PERMISSION_CAPTURES}/711-ld420-ac3-patch-security-entity-to-"
                          f"anyone-can-view-candidate-lever.json · "
                          f"{_PERMISSION_CAPTURES}/725-ld420-ac3-invented-key-control-patch-"
                          f"zzz-ld420-control.json"),
        note=("ONE KEY PER CALL, each read back — the shape it was measured in. The "
              "invented-key control was REFUSED rather than swallowed on this route, which is "
              "what lets an accepted value be read as a stored value HERE and nowhere else."),
    ),
)

#: The **R1 enumeration** ops — the three this surface shipped first, and the set whose
#: read-only claim was, and remains, true. Named so that claim can be **re-scoped rather than
#: deleted** when a mutating op joins the registry (D-24: preserve the reason, supersede only
#: the conclusion).
ENUMERATION_OPS: Tuple[DriveOpDescriptor, ...] = tuple(
    descriptor for descriptor in OPS
    if descriptor.name in ("list_folder_children", "root_folder_token", "folder_name")
)


def dataclasses_fields():
    """The descriptor's own fields — so a guard can assert ``mutates`` is one of them rather
    than trusting that every row happened to pass it."""
    return dataclasses.fields(DriveOpDescriptor)


def op(name: str) -> DriveOpDescriptor:
    """The descriptor named ``name``."""
    for descriptor in OPS:
        if descriptor.name == name:
            return descriptor
    raise KeyError(name)


def descriptor_for_path(path: str) -> Optional[DriveOpDescriptor]:
    """The descriptor whose endpoint a wire path resolves to, or ``None``."""
    for descriptor in OPS:
        if descriptor.endpoint == path:
            return descriptor
    return None


def http_verbs() -> Tuple[str, ...]:
    """Every verb this surface can put on the wire — sorted, deduplicated, derived."""
    return tuple(sorted({descriptor.http_method for descriptor in OPS}))


def query_posts() -> Tuple[DriveOpDescriptor, ...]:
    """The ``POST`` ops that are declared **reads**.

    **RE-SCOPED, not deleted (D-24).** The reason this set exists is unchanged — a documented
    query POST must be visibly declared a read, or the registry classifies it as a write. What
    moved is only the count: R1 shipped exactly one (``folder_name``), and the document
    security-level leg is a **second** read on the very same endpoint, so the set is now two.

    Their counterpart is registered too: ``create_version`` is a ``POST`` that declares
    ``mutates: True``. POSTs with opposite declarations on one verb — which is the whole
    argument for declaring rather than inferring, visible from both sides.
    """
    return tuple(d for d in OPS if d.http_method == "POST" and d.mutates is False)


def mutating_ops(ops: Optional[Tuple[DriveOpDescriptor, ...]] = None
                 ) -> Tuple[DriveOpDescriptor, ...]:
    """Every registered op that **declares** it mutates.

    Empty until LD-409 (``create_version``); LD-432 added the four access-management ops
    (``grant_access``, ``update_access``, ``revoke_access``, ``set_copy_permissions``). The
    set is derived, so a new write op joins it by declaring itself rather than by anyone
    remembering to.
    """
    return tuple(d for d in (OPS if ops is None else ops) if d.mutates is True)


def read_only(ops: Optional[Tuple[DriveOpDescriptor, ...]] = None) -> bool:
    """``True`` when no op in ``ops`` mutates — the read-only proof, mechanically.

    **TRANSFORMED, not deleted (LD-409, D-24).** This answered for the whole registry while the
    whole registry was R1's enumeration, and the reason it existed is unchanged: a read-only
    claim should be checkable rather than merely intended. What changed is only the
    **conclusion for the default argument** — ``create_version`` mutates, so ``read_only()``
    over the whole registry is now ``False``, and saying otherwise would be the lie the
    function exists to prevent. The claim that *was* true is re-scoped, not dropped:
    ``read_only(ENUMERATION_OPS)`` is ``True`` and stays the enumeration's proof.

    **LD-432 re-applies the same rule rather than restating it.** Four access-management ops
    joined the registry, so the whole-registry answer is ``False`` for five reasons instead of
    one — and the enumeration's claim is untouched, because it was never a claim about the
    ops that came later.
    """
    return all(descriptor.mutates is False
               for descriptor in (OPS if ops is None else ops))
