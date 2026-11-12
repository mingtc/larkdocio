---
name: larkdocio-start-here
description: Use when a task involves a Lark or Feishu URL — a document, spreadsheet, Base table or folder — and it is not yet clear which tool, which guide section or which console command answers it. Route from here first.
---

# Start here

This file routes. It carries no answers of its own: every answer already ships inside the
installed wheel, and each row below is the address of one.

> **Version skew, both directions.** Copied from a `larkdocio` checkout, **1.53.1**, on **2026-11-10**. Pointer will not resolve? Your wheel is older — refresh it. Wheel newer than 1.53.1? This pack may be missing something added since — refresh anyway. Either way, run `scripts/update_larkdocio.sh`, then re-copy the pack with a fresh clone's `consumers/install-skills.sh`.

## Which router

| The shape of the task | Open |
|---|---|
| Get something out of Lark and into text | `larkdocio-read-into-markdown` |
| Change words that are already in a document | `larkdocio-edit-a-document-as-a-file` |
| Add content the document does not have yet | `larkdocio-author-into-a-document` |
| Rows, columns and cells (Base or spreadsheet) | `larkdocio-write-rows-and-cells` |
| Something was refused, denied or came back empty | `larkdocio-when-lark-refuses` |

## The two calls that answer "can it do this at all"

```python
import larkdocio
larkdocio.capabilities()      # every surface, machine-readable
larkdocio.guide_sections()    # every section name you may cite
```

The same ground in prose: `larkdocio guide --section capability-matrix`.

## Before any first call in a fresh repository

- `larkdocio guide --section install-vendored-wheel-the-locked-distribution-model`
- `larkdocio guide --section credentials-env-setup-the-read-write-app-split`
- `larkdocio guide --section which-level-does-this-ask-need`

## The rule this pack lives by

Every file here **points**; none of them restates what it points at. Keep it that way when you
edit one — a second copy of the guide drifts away from the wheel silently, and then the routing
sends people somewhere that no longer exists. If a section you want does not exist, that is a
gap to report, not prose to write here.

To read one address without leaving the terminal:

```bash
larkdocio guide --section <slug>
```
