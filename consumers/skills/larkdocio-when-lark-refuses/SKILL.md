---
name: larkdocio-when-lark-refuses
description: Use when a call was refused, denied, halted, rejected as stale, or returned nothing at all — including permission and scope errors, empty reads, and batches that wrote less than expected.
---

# When it refuses

A refusal here is typed and deliberate: it names what it would not do, and why. Read the
refusal first, then the section that owns that class of refusal.

> **Version skew, both directions.** Copied from a `larkdocio` checkout, **1.53.2**, on **2026-11-14**. Pointer will not resolve? Your wheel is older — refresh it. Wheel newer than 1.53.2? This pack may be missing something added since — refresh anyway. Either way, run `scripts/update_larkdocio.sh`, then re-copy the pack with a fresh clone's `consumers/install-skills.sh`.

Start with the map of where refusals come from at all:

```bash
larkdocio guide --section where-refusals-happen-and-when-the-three-channels
```

| What you saw | Read |
|---|---|
| A scope or permission error from Lark | `permissions-what-to-ask-for` |
| Some entries applied, others did not | `the-sheets-disposition-vocabulary-what-a-per-entry-outcome-can-be` |
| The whole batch refused, nothing written | `the-two-batch-contracts-docx-refuses-the-whole-batch-sheets-disposes-per-entry` |
| Refused before any write, on the document itself | `the-document-s-security-level-readable-not-settable-and-it-can-gate-an-edit-before-you-get-here` |
| A person cannot open what was just created | `recipe-grant-a-human-access-and-who-can-already-read-a-document-the-app-just-created` |
| Nothing found at a URL that plainly works in a browser | `domain-is-the-lark-api-domain-not-your-tenant-host` |
| Something was created, but nowhere you can find it | `where-a-new-object-goes-you-name-the-destination-or-nothing-is-created` |
| A link you tried to build does not open anything | `the-links-you-cannot-mint-or-fetch-stated-plainly-so-you-do-not-re-run-the-search` |
| A push refused not-in-dialect on bold, italics or a link | `recipe-edit-part-of-a-paragraph-a-sub-span-edit` |
| Refused **stale** — the document or sheet moved under your plan | `do-not-edit-the-document-while-an-authoring-session-runs-the-concurrency-doctrine` |
| A rate limit interrupted a rewrite and the re-push now refuses **stale-anchor** | `recipe-a-rate-limit-interrupted-your-rewrite-and-the-re-push-refuses-stale-anchor-the-idempotent-repair` |

## The scope question, answered from the code rather than from memory

```python
from larkdocio import permissions
permissions.permission_registry()   # every operation, with the scopes it needs
```

Granting a scope is an action in the Lark console. This library only reports what an operation
requires and shows what Lark itself said when it declined.

## Then

Back to `larkdocio-start-here` if the refusal turned out to be the wrong tool for the task.
