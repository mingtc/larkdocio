---
name: larkdocio-author-into-a-document
description: Use when content a Lark or Feishu document does not have yet must be added — a Markdown fragment, headings and lists, a table, an image, an attached file, a link or a diagram.
---

# Author new content into a document

Write the fragment in Markdown, compile it, preview the plan, apply it, then read it back.
The dialect is fixed and narrower than Markdown generally; check it before composing anything
long.

> **Version skew, both directions.** Copied from a `larkdocio` checkout, **1.53.1**, on **2026-11-10**. Pointer will not resolve? Your wheel is older — refresh it. Wheel newer than 1.53.1? This pack may be missing something added since — refresh anyway. Either way, run `scripts/update_larkdocio.sh`, then re-copy the pack with a fresh clone's `consumers/install-skills.sh`.

## Start here, in this order

1. `larkdocio guide --section which-write-recipe-do-you-need-add-change-update-or-delete-content-in-a-document`
2. `larkdocio guide --section authoring-from-markdown-the-dialect-and-what-it-cannot-express`
3. `larkdocio guide --section recipe-author-a-markdown-fragment-into-a-document`

## By what you are adding

| Adding | Read |
|---|---|
| A first draft into an empty document | `recipe-write-into-an-empty-document` |
| More blocks than one call carries | `recipe-author-more-than-one-call-s-worth-of-blocks-the-50-per-call-cap-batched-in-order` |
| A table | `what-authoring-a-table-costs-and-where-the-500-cell-cap-comes-from` |
| An image | `recipe-put-an-image-in-a-document-create-upload-bind` |
| A file card | `recipe-attach-a-file-to-a-document-the-attachment-card` |
| A link to a file inside a sentence | `recipe-link-a-file-from-a-sentence` |
| A diagram | `recipe-author-a-mermaid-diagram-and-change-one` |
| A follow-up anchored to what you just created | `recipe-anchor-a-follow-up-by-a-created-block-id` |
| A row added to a table that already exists | `recipe-add-a-row-to-a-table-that-already-exists` — the gated route appends at the end and keeps every block id; removal, a column append and mid-table insertion are not operations, and of those three only mid-table insertion is a REFUSED request (typed **table-grow-unsupported**) — the other two are shapes the op cannot express at all, which the recipe states |

Rendering a diagram locally, before it goes anywhere near Lark:

```bash
larkdocio mermaid --help
```

## Confirm it landed

`larkdocio guide --section recipe-verify-what-you-authored-compose-equivalence-not-string-equality`
— comparing rendered strings will report differences that are not differences.

## Then

- Changing what is already there → `larkdocio-edit-a-document-as-a-file`
- It refused → `larkdocio-when-lark-refuses`
