---
name: larkdocio-read-into-markdown
description: Use when the contents of a Lark or Feishu document, spreadsheet, Base table, folder or comment thread are needed as Markdown that can be read, diffed, stored or handed to a model.
---

# Read it into Markdown

Find the row, open the address. There is a shipped reader for each of these; a hand-rolled one
will lose things the shipped one keeps.

> **Version skew, both directions.** Copied from a `larkdocio` checkout, **1.53.2**, on **2026-11-14**. Pointer will not resolve? Your wheel is older — refresh it. Wheel newer than 1.53.2? This pack may be missing something added since — refresh anyway. Either way, run `scripts/update_larkdocio.sh`, then re-copy the pack with a fresh clone's `consumers/install-skills.sh`.

| What is behind the URL | Read this section first |
|---|---|
| A document | `recipe-download-a-docx-to-markdown` |
| A spreadsheet | `recipe-read-a-sheet-to-markdown` |
| A spreadsheet, with styling and number formats | `recipe-read-a-sheet-at-style-fidelity-the-l2-export-leg` |
| A Base table | `recipe-read-a-base-to-markdown` |
| Every document in a folder | `recipe-read-every-document-in-a-folder` |
| The review conversation on a document | `recipe-read-the-comments-on-a-document` |

Open one:

```bash
larkdocio guide --section recipe-download-a-docx-to-markdown
```

## Straight from the command line

```bash
larkdocio download "<url>" -o ./out/
larkdocio folder "<url>" -o ./out/
```

Both read and never write.

## Two decisions worth making before you parse anything

- Markdown text, or the node tree the Markdown is projected from —
  `larkdocio guide --section which-level-does-this-ask-need`
- What that projection does not carry —
  `larkdocio guide --section what-the-projection-drops-three-directions-stated-separately`

## Then

- Editing what you just read → `larkdocio-edit-a-document-as-a-file`
- Nothing came back, or only part of it → `larkdocio-when-lark-refuses`
