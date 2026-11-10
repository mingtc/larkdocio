"""The permissions leg — every op's scope requirement, derived from its own code.

LD-244: the verbatim pre-split slice, lines 2370-2460 of the
2,770-line ``capabilities.py``. Nothing in it was rewritten.
"""
import dataclasses

from larkdocio import permissions as _perm
from larkdocio.base.client import BaseReadClient as _BaseReadClient
from larkdocio.base.schema_client import BaseSchemaClient as _BaseSchemaClient
from larkdocio.base.write_client import BaseWriteClient as _BaseWriteClient
from larkdocio.comments.client import CommentsReadClient as _CommentsReadClient
from larkdocio.contacts.client import ContactsSearchClient as _ContactsSearchClient
from larkdocio.sheets.client import SheetsReadClient as _SheetsReadClient
from larkdocio.sheets.export_reader import SheetsExportReader as _SheetsExportReader
from larkdocio.sheets.write_client import SheetsWriteClient as _SheetsWriteClient
from larkdocio.write.client import WriteClient as _DocxWriteClient

from ._models import Surface

# --------------------------------------------------------------------------- #
# The permissions leg — every op's scope requirement, DERIVED from its own code, #
# and every surface's list PROJECTED from its ops (never asserted twice).        #
# --------------------------------------------------------------------------- #

#: ``{surface_id: {parameter name: the class that surface hands it}}``.
#:
#: The endpoint derivation resolves ``self.foo`` off the owning class and ``client.foo`` off a
#: parameter's own annotation. These are the call sites where the annotation is absent (a
#: write op's descriptor legs take a bare ``client``; the embedded bridge takes a bare
#: ``client`` and ``export_reader``), so the surface states which class it passes. That is a
#: STRUCTURAL fact about the surface, not a scope assertion — the scopes still come from the
#: one endpoint table, via whatever those classes' methods actually call.
_IMPL_SEEDS = {
    "docx-comments-read": {"client": _CommentsReadClient},
    # The Base legs take a bare, injectable ``client`` for the same reason every other read
    # surface's composed entry point does (pacing, credentials and transport all injectable).
    # Without these seeds ``read_base`` / ``read_base_markdown`` / the embed bridge derive as
    # EMPTY, which would report the operations a consumer actually calls as needing no
    # permission at all — and a Base needs one to be readable.
    "base-read": {"client": _BaseReadClient},
    "base-comments-read": {"client": _CommentsReadClient},
    "base-embedded-deep-read": {"client": _BaseReadClient},
    # The record-write families are unbound methods on the write client, so each resolves
    # `self.foo` off its own owning class and needs no seed. The seed is here for the same
    # reason the read one is: so a later composed entry point on this surface (which would take
    # a bare, injectable `client`) cannot derive as EMPTY and report a write as needing no
    # permission at all.
    "base-write": {"client": _BaseWriteClient},
    # The schema ops are unbound methods on the schema client, so each already resolves
    # `self.foo` off its own owning class. The `client` seed is here for the same reason
    # base-write's is: a later composed entry point on this surface would take a bare,
    # injectable `client` and, without a seed, derive as EMPTY — reporting a schema write as
    # needing no permission at all, which is the one answer nothing can check.
    #
    # THAT PREDICTION WAS DISCHARGED BY LD-642 — it happened, and the reason above is why it
    # was worth writing down. It arrived through the door the row did not cover: the composed
    # entry point `migrate_field_type` takes THREE injectable clients (`schema_client`,
    # `client`, `read_client`), and the unseeded one was `read_client`, so the migration
    # published `endpoints: []` / `scopes: []` / `api_using: false` for a Base column-type
    # migration while `unresolved_call_sites` named 14 seams nobody reads first. The lesson
    # the fix carries forward: a seed row must name EVERY injectable client parameter the
    # surface's entry points take, not just the one named after the surface — an unnamed
    # parameter is not a smaller answer, it is the wrong headline.
    "base-schema-write": {"client": _BaseSchemaClient, "read_client": _BaseReadClient},
    # resolve_user takes a bare `client` (so pacing, credentials and transport are all
    # injectable). Without this seed its endpoints derive as EMPTY, which would report the one
    # operation a consumer actually calls as needing no permission at all.
    "contacts-read": {"client": _ContactsSearchClient},
    # LD-432 — the access surface's address -> id LEG calls the shipped ``resolve_colleague``,
    # which takes that same bare, injectable ``client``. Without the seed the leg derives as
    # EMPTY and the contacts call a grant-by-email really makes would be reported as needing no
    # permission at all.
    "drive-access-write": {"client": _ContactsSearchClient},
    # The sheets walk's composed entry points take a bare, injectable ``client`` for the same
    # reason the Base ones do. Without this seed ``read_spreadsheet_markdown`` derives as
    # EMPTY — reporting the one call a consumer holding a URL actually makes as needing no
    # permission at all, when a spreadsheet needs one to be readable.
    "sheets-read": {"client": _SheetsReadClient},
    "sheets-embedded-deep-read": {
        "client": _SheetsReadClient, "export_reader": _SheetsExportReader},
    "docx-write": {"client": _DocxWriteClient},
    "sheets-write": {"client": _SheetsWriteClient},
}


def _surface_with_permissions(surface_id: str, surface: Surface, composed) -> Surface:
    """Attach each op's derived permission block, then PROJECT the surface's own scope lists.

    Two things happen here, in this order, and the order is the point: an operation's
    requirement is derived from its own code first, and the surface's ``scopes`` /
    ``optional_scopes`` are then the **union** of those — so the surface can no longer assert
    a scope list that drifts from the operations under it. ``composed`` carries the required
    scopes of any surface this one runs inside.
    """
    seeds = _IMPL_SEEDS.get(surface_id, {})
    creds = surface.credentials

    def block(impl):
        return _perm.permissions_for(
            impl,
            mode=surface.mode,
            credential_app=creds.app,
            credentials_env=creds.env_primary,
            seeds=seeds,
        )

    operations = [dataclasses.replace(op, permissions=block(op.impl))
                  for op in surface.operations]
    legs = [dataclasses.replace(op, permissions=block(op.impl)) for op in surface.legs]
    lifecycle = (
        [dataclasses.replace(op, permissions=block(op.impl)) for op in surface.lifecycle]
        if surface.lifecycle is not None else None
    )
    required, optional = _perm.surface_projection(
        [op.permissions for op in operations]
        + [op.permissions for op in legs]
        + [op.permissions for op in (lifecycle or ())],
        composed,
    )
    return dataclasses.replace(
        surface,
        operations=operations,
        legs=legs,
        lifecycle=lifecycle,
        credentials=dataclasses.replace(
            creds, scopes=list(required), optional_scopes=list(optional)),
    )


def _with_permissions(surfaces: dict) -> dict:
    """The whole-registry permissions pass, in declaration order.

    Declaration order is load-bearing for exactly one reason: a surface that ``composes``
    another needs that other surface's requirement already projected, and the composed
    surface is declared first. A forward reference raises here rather than projecting a
    silently short requirement.
    """
    out, projected = {}, {}
    for surface_id, surface in surfaces.items():
        composed = []
        for other in surface.composes:
            if other not in projected:
                raise LookupError(
                    f"{surface_id} composes {other!r}, which is not declared before it")
            composed.extend(projected[other])
        out[surface_id] = _surface_with_permissions(surface_id, surface, composed)
        projected[surface_id] = list(out[surface_id].credentials.scopes)
    return out


