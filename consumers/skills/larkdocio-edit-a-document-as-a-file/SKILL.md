---
name: larkdocio-edit-a-document-as-a-file
description: Use when words already present in a Lark or Feishu document must change — an edit, a correction, a rewrite, a deletion or a reorder of existing content, rather than the addition of something new.
---

# Edit a document as a file

Pull it to disk, edit the file, push it back — the route for changing a lot of a document at
once. Every block your edited file changed comes back as a single run: it keeps the styling the
block started with, and a colour further along the same paragraph is flattened onto that. Bold
and italics refuse the push instead of being flattened, and so does a labelled link — unless its
label is its own URL, which composes as plain text; see
`authoring-from-markdown-the-dialect-and-what-it-cannot-express`. To change a few words inside a
block and leave the rest of it exactly as it stands, use a sub-span edit instead:
`larkdocio guide --section recipe-edit-part-of-a-paragraph-a-sub-span-edit`. Two invocations,
because the edit happens between them — possibly in another process, possibly tomorrow.

> **Version skew, both directions.** Copied from a `larkdocio` checkout, **1.53.1**, on **2026-11-10**. Pointer will not resolve? Your wheel is older — refresh it. Wheel newer than 1.53.1? This pack may be missing something added since — refresh anyway. Either way, run `scripts/update_larkdocio.sh`, then re-copy the pack with a fresh clone's `consumers/install-skills.sh`.

```bash
larkdocio roundtrip pull "<url>" -o ./edit/
# edit ./edit/document.md — leave every marker exactly where it is
larkdocio roundtrip push -o ./edit/            # preview; writes nothing
larkdocio roundtrip push -o ./edit/ --apply    # applies the plan you just previewed
```

The same two steps from Python are `larkdocio.roundtrip.pull()` and `larkdocio.roundtrip.push()`.

## The addresses

| You want | Read |
|---|---|
| The full script the command was promoted from | `recipe-copy-this-the-end-to-end-update-script-from-url-to-applied-edit` |
| To change many blocks at once, by hand | `recipe-update-an-existing-document-change-or-edit-many-blocks-at-once-without-re-authoring-it` |
| To change part of a sentence, keeping its styling | `recipe-edit-part-of-a-paragraph-a-sub-span-edit` |
| To change the text of a code block | `recipe-edit-a-code-block-s-text` |
| To move sections around | `recipe-reorganise-a-document-there-is-no-move-so-a-reorder-is-delete-and-recreate` |
| To object level, no Markdown anywhere | `recipe-change-a-document-at-the-object-level-no-markdown-anywhere` |

## Two rules that cost people a day when skipped

- `larkdocio guide --section the-read-back-law-a-green-apply-is-not-a-receipt`
- `larkdocio guide --section do-not-edit-the-document-while-an-authoring-session-runs-the-concurrency-doctrine`

## Then

- Adding something that is not there yet → `larkdocio-author-into-a-document`
- The push refused → `larkdocio-when-lark-refuses`
