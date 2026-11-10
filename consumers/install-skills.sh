#!/usr/bin/env bash
#
# install-skills.sh — copy the larkdocio router skill pack into a consumer repo.
#
# The pack is a handful of ROUTER skills: each fires on a task shape ("edit a
# document as a file", "why was I refused?") and answers with an address — a
# packaged-guide section or a console command — instead of an explanation. It is
# COPIED rather than shipped inside the wheel, because an agent harness discovers
# skills as files in the working repo; a copy inside site-packages is inert.
#
# It enumerates the pack directory. There is deliberately NO list of skill names
# here: a list is one more copy of the truth, and it goes stale the first time
# somebody adds a router and forgets to update it.
#
# Usage:
#   /path/to/larkdocio/consumers/install-skills.sh            # consumer = CWD
#   /path/to/larkdocio/consumers/install-skills.sh /repo/root # explicit root
#
# Idempotent: re-running refreshes the copies in place.
#
set -euo pipefail

log() { printf '%s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACK_SRC="$SCRIPT_DIR/skills"
[ -d "$PACK_SRC" ] || die "cannot find the skill pack next to this script ($PACK_SRC)."

CONSUMER="${1:-$(pwd)}"
CONSUMER="$(cd "$CONSUMER" && pwd)" || die "consumer path does not exist: ${1:-$(pwd)}"

DEST="$CONSUMER/.claude/skills"
mkdir -p "$DEST"

# THE VERSION-SKEW STAMP IS DERIVED, never carried (LD-694). Each router's banner names
# the larkdocio version it was copied from and the date of the copy. Typed into the pack
# once, that stamp was stale from the next release on, and every re-copy reproduced it; so
# the copy step writes it: the version of the checkout this script sits in (its own
# src/larkdocio/__init__.py) and today's date. A checkout with no readable version keeps
# the pack's own stamp and says so.
VERSION_FILE="$SCRIPT_DIR/../src/larkdocio/__init__.py"
PACK_VERSION=""
if [ -f "$VERSION_FILE" ]; then
    PACK_VERSION="$(sed -n 's/^__version__ = "\([0-9][0-9.]*\)"$/\1/p' "$VERSION_FILE" | head -1)"
fi
STAMP_DATE="$(date +%Y-%m-%d)"
[ -n "$PACK_VERSION" ] \
    || log "NOTE: no larkdocio version found at $VERSION_FILE — the copies keep the pack's own version stamp."

stamp() {  # <copied file> — restamp its version-skew banner line in place
    [ -n "$PACK_VERSION" ] || return 0
    local tmp="$1.stamp.$$"
    sed -E "/Version skew/{
s/\*\*[0-9]+\.[0-9]+\.[0-9]+\*\*, on \*\*[0-9]{4}-[0-9]{2}-[0-9]{2}\*\*/**${PACK_VERSION}**, on **${STAMP_DATE}**/
s/newer than [0-9]+\.[0-9]+\.[0-9]+\?/newer than ${PACK_VERSION}?/
}" "$1" > "$tmp" && mv "$tmp" "$1"
}

copied=0
# Enumerate — never enumerate into a hard-coded list.
while IFS= read -r source; do
    relative="${source#"$PACK_SRC"/}"
    mkdir -p "$DEST/$(dirname "$relative")"
    cp "$source" "$DEST/$relative"
    stamp "$DEST/$relative"
    copied=$((copied + 1))
done < <(find "$PACK_SRC" -type f | sort)

[ "$copied" -gt 0 ] || die "the skill pack is empty ($PACK_SRC) — nothing to install."

log "Copied $copied skill-pack file(s) into $DEST"
log "Each file POINTS at a packaged-guide section or a console command; none of them"
log "restates one. Re-run this script after refreshing the vendored wheel."
