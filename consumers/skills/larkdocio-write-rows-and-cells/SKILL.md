---
name: larkdocio-write-rows-and-cells
description: Use when the target is tabular — creating or updating rows, records, columns, fields, cells, links, formulas or attachments in a Lark Base table or a Lark spreadsheet.
---

# Write rows and cells

Two different surfaces with two different contracts. Open the handshake for the one you are on
before sending anything, and preview every batch before applying it.

> **Version skew, both directions.** Copied from a `larkdocio` checkout, **1.53.2**, on **2026-11-14**. Pointer will not resolve? Your wheel is older — refresh it. Wheel newer than 1.53.2? This pack may be missing something added since — refresh anyway. Either way, run `scripts/update_larkdocio.sh`, then re-copy the pack with a fresh clone's `consumers/install-skills.sh`.

## Base

| Task | Read |
|---|---|
| The handshake, end to end | `recipe-the-base-write-handshake` |
| What a cell accepts, and what it returns | `what-a-base-cell-takes-and-what-it-hands-back` |
| A new column, or renaming one | `recipe-add-a-column-and-change-one-s-name` |
| Changing a column's type | `recipe-change-a-column-s-type-the-guided-migration-do-not-hand-roll-this` |
| A file on a record | `recipe-attach-a-file-to-a-record-and-prove-the-bytes-survived` |
| Sizing a bulk load first | `recipe-price-a-bulk-import-before-you-send-it` |
| A whole new table or Base | `recipe-create-rename-and-copy-a-base-the-structural-handshake` |

## Spreadsheet

| Task | Read |
|---|---|
| The handshake, end to end | `recipe-the-sheets-write-handshake` |
| A hyperlink or styled text in one cell | `recipe-write-a-hyperlink-and-a-styled-run-into-a-cell` |
| A live formula | `recipe-write-a-live-formula-into-a-sheet` |
| Rows and columns in or out | `recipe-insert-and-delete-rows-and-columns-a-structural-write` |
| Fills, fonts, borders, number formats | `recipe-set-a-cell-s-fill-font-border-and-number-format-a-style-write` |
| Emptying cells | `recipe-clear-cells-there-is-no-clear-operation` |

## Two things to read before the first batch

- `larkdocio guide --section the-two-batch-contracts-docx-refuses-the-whole-batch-sheets-disposes-per-entry`
- `larkdocio guide --section verifying-a-sheet-write-compare-values-not-their-string-forms`

## Then

- Some entries came back refused → `larkdocio-when-lark-refuses`
- You need the table as text first → `larkdocio-read-into-markdown`
