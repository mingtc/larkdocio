#!/usr/bin/env bash
#
# setup-consumer.sh — one-time onboarding for a new larkdocio consumer.
#
# Run it from (or point it at) a consumer repo root. It:
#   1. copies the canonical update_larkdocio.sh into the consumer's scripts/,
#   2. copies the advisory git-hook template into the consumer's scripts/,
#   2b. copies the router skill pack into the consumer's .claude/skills/,
#   3. runs the refresh script (builds + vendors the latest tagged wheel into
#      ./vendor/),
#   4. prints what remains for the human/agent: the requirement line to pin, the
#      .env credential names, and the recommended nag wiring (a git hook).
#
# larkdocio never tracks its consumers — this is self-service onboarding.
#
# Usage:
#   /path/to/larkdocio/consumers/setup-consumer.sh            # consumer = CWD
#   /path/to/larkdocio/consumers/setup-consumer.sh /repo/root # explicit root
#
set -euo pipefail

log() { printf '%s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPDATE_SRC="$SCRIPT_DIR/update_larkdocio.sh"
HOOK_SRC="$SCRIPT_DIR/hooks/post-merge"
SKILLS_INSTALLER="$SCRIPT_DIR/install-skills.sh"
[ -f "$UPDATE_SRC" ] || die "cannot find update_larkdocio.sh next to this script ($UPDATE_SRC)."

CONSUMER="${1:-$(pwd)}"
CONSUMER="$(cd "$CONSUMER" && pwd)" || die "consumer path does not exist: ${1:-$(pwd)}"
[ -d "$CONSUMER/.git" ] || log "Note: $CONSUMER does not look like a git repo root — continuing anyway."

log "Onboarding consumer: $CONSUMER"

# 1. Copy the canonical refresh script into the consumer's scripts/.
mkdir -p "$CONSUMER/scripts"
cp "$UPDATE_SRC" "$CONSUMER/scripts/update_larkdocio.sh"
chmod +x "$CONSUMER/scripts/update_larkdocio.sh"
log "Copied scripts/update_larkdocio.sh into the consumer."

# 1b. Copy the advisory git-hook template so the nag can be wired with no path
#     edits (see the printed one-liner below). It is NOT installed automatically —
#     wiring the hook stays the consumer's explicit choice.
if [ -f "$HOOK_SRC" ]; then
    cp "$HOOK_SRC" "$CONSUMER/scripts/larkdocio-post-merge.hook"
    log "Copied scripts/larkdocio-post-merge.hook (advisory nag template) into the consumer."
else
    log "Note: hook template not found next to this script ($HOOK_SRC) — skipping; wire the nag manually per consumers/README.md."
fi

# 1d. Where the consumer's git ACTUALLY reads hooks from, asked of their own repo rather
#     than assumed. `core.hooksPath` can point git somewhere other than `.git/hooks`, and a
#     hook left in `.git/hooks` is then never run — no warning, no error, exit 0. So the
#     one-liner printed below is computed for THIS repo instead of being a general
#     instruction the reader has to adapt.
#
#     `git rev-parse --git-path hooks` is the primitive because it answers in every state:
#     `.git/hooks` when the setting is unset, the configured directory (relative or
#     absolute) when it is set. `git config --get core.hooksPath` prints nothing and exits 1
#     when absent, so it would need a second branch for the common case.
HOOK_DEST="$(git -C "$CONSUMER" rev-parse --git-path hooks 2>/dev/null || true)"
[ -n "$HOOK_DEST" ] || HOOK_DEST=".git/hooks"

# 1c. Copy the ROUTER SKILL PACK into the consumer's .claude/skills/. Delegated to
#     install-skills.sh, which enumerates the pack directory — no file list lives
#     in either script, so a router added later installs itself.
if [ -x "$SKILLS_INSTALLER" ]; then
    bash "$SKILLS_INSTALLER" "$CONSUMER"
    SKILLS_INSTALLED=yes
else
    log "Note: skill-pack installer not found next to this script ($SKILLS_INSTALLER) — skipping."
    SKILLS_INSTALLED=no
fi

# 2. Run it from the consumer root to vendor the latest tagged wheel.
#    Its stdout is exactly the requirement line to pin.
log "Building + vendoring the latest larkdocio wheel…"
REQ_LINE="$(cd "$CONSUMER" && bash scripts/update_larkdocio.sh)"

# 3. Tell the human/agent what remains (pin + creds + nag wiring).
cat >&2 <<EOF

────────────────────────────────────────────────────────────────────────────
larkdocio is vendored, and the router skill pack was installed: ${SKILLS_INSTALLED}
(into .claude/skills/ in this repo — a few small files that fire on a task shape
 and point at the packaged guide's sections and at the console verbs. They carry
 no copy of the guide, so keep them thin; after every wheel refresh, re-copy them
 with consumers/install-skills.sh from a fresh clone of the public repository.)

Three things remain for you (the third is recommended, not required):

1) Pin this requirement in the consumer's requirements file
   (so a fresh clone reproduces the env from the LOCAL wheel — no git host):

     ${REQ_LINE}

   Then install it into the consumer venv (this first install resolves larkdocio's
   runtime dependencies, so no --no-deps here; a later refresh uses the command
   update_larkdocio.sh prints, which adds --no-deps):

     .venv/bin/pip install --force-reinstall '${REQ_LINE#*file:}'

2) Provide Lark credentials in the consumer's .env (read path):

     LARK_READ_APP_ID=...        # preferred
     LARK_READ_APP_SECRET=...
     # — or the legacy names, still accepted —
     LARK_APP_ID=...
     LARK_APP_SECRET=...

   (LARK_WRITE_APP_ID / LARK_WRITE_APP_SECRET are used by every write surface —
    roundtrip push and the Sheets, Base and Drive writers — and never by the reader.)

3) (Recommended) Wire the ADVISORY update nag — it only TELLS you when a newer
   larkdocio exists; it NEVER auto-updates, never touches ./vendor/, never
   fails your git workflow. From the consumer repo root:

     mkdir -p '${HOOK_DEST}'
     cp scripts/larkdocio-post-merge.hook '${HOOK_DEST}/post-merge'
     chmod +x '${HOOK_DEST}/post-merge'
     git hook run post-merge

   That destination is not a guess — it is what your own git answers for
   'git rev-parse --git-path hooks', which is where it reads hooks from. It is
   NOT always '.git/hooks': core.hooksPath overrides it, and a hook left in
   '.git/hooks' is then never run (no warning, no error, exit 0).

   The last line is the proof, and it is worth running: it resolves the hook the
   way git does, prints the nag's own line when the wiring is right (or nothing
   at all if the check cannot reach the host or no tag exists yet), and fails
   loudly when the file sits somewhere git does not read (needs git 2.36+; on
   older git, merge something and watch for the '[larkdocio]' line). Check once
   — this nag is quiet when you are up to date, so silence alone tells you
   nothing.

   Then a future 'git pull' prints '[larkdocio] UPDATE AVAILABLE …' when there
   is one.

Refresh later — always DELIBERATE, never automatic:
     scripts/update_larkdocio.sh [tag]     # build + vendor (then re-pin)
     scripts/update_larkdocio.sh --check    # report-only: newer tag available?

Full zero-knowledge walkthrough: consumers/README.md
────────────────────────────────────────────────────────────────────────────
EOF

# Echo the requirement line on stdout too, so callers can capture it.
echo "$REQ_LINE"
