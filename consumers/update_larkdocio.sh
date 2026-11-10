#!/usr/bin/env bash
#
# update_larkdocio.sh — refresh the vendored `larkdocio` wheel in THIS consumer
# repo. Canonical template shipped by the larkdocio project; each consumer keeps
# its own copy at scripts/update_larkdocio.sh.
#
# Distribution model (locked): consumers VENDOR a built wheel into ./vendor/ and
# pin a local-file requirement. THIS script BUILDS/REFRESHES that wheel, so it DOES
# clone the larkdocio repository — it needs the git host (see LARKDOCIO_REPO_URL below).
# What needs NO reachable git host is a DOWNSTREAM clone of the CONSUMER: it
# reproduces the env from the already-vendored local wheel (PyPI only, for transitive
# deps). Refresh is pull-based and DELIBERATE: this script touches the network ONLY
# when you run it. Nothing here runs on `git pull`.
#
# Usage (run from the consumer repo root):
#   scripts/update_larkdocio.sh              # build + vendor the LATEST tag
#   scripts/update_larkdocio.sh v1.53.0      # build + vendor a specific tag
#   scripts/update_larkdocio.sh --check      # report-only: is a newer tag available?
#
# TWO PATHS, and you never have to choose. It first tries the `dist` FAST PATH —
# a shallow clone of larkdocio's consumer-only distribution branch, which carries
# the current release's wheel and documents and nothing else, so there is no build
# and no history to fetch. If `dist` is absent (an older repo state) or stale (its
# wheel is not the version you asked for), it FALLS BACK to the original path:
# clone the repository, check out the tag, build the wheel. A log line always says
# which path ran; ./vendor/ is identical either way, so nothing downstream can tell.
# Then it copies the wheel into ./vendor/ (removing older larkdocio wheels) and
# prints the exact requirement line to pin.
#
# The tag remains AUTHORITATIVE for every version: `dist` carries only the current
# release (larkdocio replaces it on each cut, one commit, force-pushed), so asking
# for an older tag builds from that tag. Tags start at v1.53.0, the first public
# release; nothing older is published. Set LARKDOCIO_NO_DIST=1 to skip the fast
# path entirely.
#
# WHAT LANDS IN ./vendor/ (all five refreshed on every run, all sourced from the
# checked-out tag, so they always describe the wheel sitting next to them):
#   • larkdocio-<ver>-py3-none-any.whl  — the wheel you pin
#   • larkdocio-GUIDE.md                — the usage + capability guide
#   • larkdocio-CHANGELOG.md            — the project's changelog
#   • larkdocio-RELEASE_NOTES.md        — what changed THAT AFFECTS YOU, per release
#   • larkdocio-LARK_SETUP.md           — the Lark-application walkthrough: the app,
#                                         its scopes, its reach (read it FIRST if
#                                         nothing works yet)
# A tag that lacks one of these documents skips that drop with a logged note; the
# run still succeeds.
#
# `--check` is REPORT-ONLY: it never writes to ./vendor/ (or anywhere else) and
# never updates. When a newer tag exists it also prints WHAT CHANGED — the release
# notes' section headers for the versions in between — which needs that tag's notes
# file and therefore a throwaway shallow clone, deleted before it returns. Set
# LARKDOCIO_CHECK_NOTES=0 to skip that and keep the check to lightweight
# `git ls-remote` queries — one, plus one for the dist branch when an update is
# available (what the advisory post-merge nag hook does, so a `git pull`
# stays fast). --check's STDOUT stays exactly the one verdict line either way; the
# what-changed report is narration and goes to STDERR.
#
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# The ONE place the larkdocio repository's location lives: the PUBLIC repository,
# larkdocio's release home — its vX.Y.Z tags and its wheel-only `dist` branch are
# what this script reads. HTTPS, so an anonymous reader needs no git credential.
# One line to change if the repository moves host — that is why this seam exists.
# Overridable via the
# environment (default unchanged) so the kit self-test can point tag-selection at
# a local throwaway repo without touching the network.
LARKDOCIO_REPO_URL="${LARKDOCIO_REPO_URL:-https://github.com/mingtc/larkdocio.git}"
# ─────────────────────────────────────────────────────────────────────────────

# Print the what-changed release-notes delta in --check mode (1) or skip it (0).
# Off is for automated nags that run on every `git pull`: it keeps the check to
# lightweight `git ls-remote` queries, with no clone.
LARKDOCIO_CHECK_NOTES="${LARKDOCIO_CHECK_NOTES:-1}"

PKG="larkdocio"
VENDOR_DIR="./vendor"

log()  { printf '%s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || die "python3 not found (set \$PYTHON)."
command -v git      >/dev/null 2>&1 || die "git not found."

# ---- helpers ---------------------------------------------------------------

# Version string embedded in the vendored wheel filename, or empty if none.
# MORE THAN ONE wheel is a REFUSAL, never a guess (LD-543): vendor/ is
# long-lived, so a stale wheel CAN sit beside the current one, and the old
# `ls | head -1` answered by sort order — a healthy checkout could report
# UPDATE AVAILABLE with a DOWNGRADE as its remedy. Which wheel is current is a
# question only a human can answer. (This parenthetical used to CONTRAST the
# this-run-created directories elsewhere in this script — "$WORK/dist, the dist
# clone" — where `head -1` was said to stay correct because a directory this run
# just made cannot hold a stale artifact. THAT REASONING IS SOUND AND IS KEPT,
# but its premise stopped holding: the two names it lists resolved to ONE
# directory, so the dist clone's stale wheel sat in the build's own output and
# `head -1` picked it (LD-591). The directories are separated below AND the
# build side now refuses a second wheel exactly as this function does — so the
# contrast is gone and the two refusals are one voice.)
vendored_version() {
    local whls count base
    whls=$(ls "$VENDOR_DIR"/${PKG}-*.whl 2>/dev/null || true)
    count=$(printf '%s\n' "$whls" | grep -c '.' || true)
    if [ "$count" -eq 0 ]; then
        echo ""
        return
    fi
    if [ "$count" -gt 1 ]; then
        printf '%s\n' "$whls" | sed 's/^/    /' >&2
        die "$count ${PKG} wheels in ${VENDOR_DIR}/ — refusing to guess which is current. Remove the stale one(s), keeping only the wheel the consumer's requirements file pins."
    fi
    base="${whls##*/}"               # larkdocio-1.0.0-py3-none-any.whl
    base="${base#${PKG}-}"           # 1.0.0-py3-none-any.whl
    echo "${base%%-*}"               # 1.0.0
}

# Newest tag on the remote (semver-sorted), without cloning. Empty if none.
# The trailing `|| true` keeps a failed ls-remote (unreachable host, no tags)
# from tripping `set -euo pipefail` in the caller's command substitution — an
# empty result is the intended "no tag" signal, handled by the caller.
# Filter to `^v[0-9]` release tags (grep after the sed) so a stray non-release
# tag (a `refactor-baseline-*` process tag, an experimental tag) can never sort
# to the top and be reported as "latest". `--sort=-v:refname` ordering among the
# v* tags is preserved.
remote_latest_tag() {
    git ls-remote --tags --refs --sort=-v:refname "$LARKDOCIO_REPO_URL" 2>/dev/null \
        | sed -n 's#.*refs/tags/##p' | grep -E '^v[0-9]' | head -1 || true
}

tag_to_version() { echo "${1#v}"; }

# ---- the what-changed delta (--check) --------------------------------------
# "A newer version exists" is only actionable with "and here is what changed", so
# --check reports the release-notes SECTION HEADERS for the versions between what
# you have vendored and the latest tag — plus, per header, the subsection titles
# that actually say something. Headers, never bodies: the point is a delta you can
# scan, and the full text lands in ./vendor/ the moment you update.
#
# Is $1 a STRICTLY newer version than $2? `sort -V` so 1.9.0 < 1.10.0.
ver_gt() {
    [ "$1" != "$2" ] || return 1
    [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -1)" = "$1" ]
}

# "VERSION|<the verbatim header line>" for every `## [X.Y.Z] — date` section of a
# release document. A missing file yields nothing and still succeeds.
notes_headers() {   # <release document>
    [ -f "$1" ] || return 0
    sed -n 's/^\(## \[\([0-9][0-9.]*\)\].*\)$/\2|\1/p' "$1"
}

# The `### Title` subsections of ONE version's section that actually say something.
# A subsection with nothing to report is written `None.`, and printing those would
# bury the ones that matter under four fixed titles per release.
notes_subsections() {   # <release document> <version>
    awk -v ver="$2" '
        BEGIN { marker = "## [" ver "]" }
        substr($0, 1, length(marker)) == marker { inside = 1; next }
        /^## \[/ { if (inside) exit; next }
        inside && /^### / {
            if (title != "" && filled) print title
            title = substr($0, 5); filled = 0; next
        }
        inside {
            line = $0
            gsub(/^[ \t]+|[ \t]+$/, "", line)
            if (line != "" && line != "None." && title != "") filled = 1
        }
        END { if (inside && title != "" && filled) print title }
    ' "$1"
}

# Report what changed between the vendored version and the latest tag.
# STRICTLY REPORT-ONLY, and that is the whole contract of this function: the notes
# for the intervening versions exist nowhere in the consumer's tree yet, so they are
# read out of a THROWAWAY shallow clone that is deleted before this returns. Nothing
# under the consumer repo is written, ./vendor/ is not touched, and EVERY failure
# path (no temp dir, clone refused, a tag carrying no notes, an empty span) prints a
# note and returns success — a report must never break the answer it decorates.
# Output goes to STDERR with the rest of the narration, so --check's STDOUT stays
# exactly the one verdict line an installed nag hook greps.
print_notes_delta() {   # <vendored version> <latest version> <latest tag>
    local from="$1" to="$2" tag="$3"
    local work clone notes changelog span v header

    work="$(mktemp -d)" || {
        log "NOTE: could not create a temp dir — skipping the what-changed report."
        return 0
    }
    clone="$work/notes"
    if ! git clone --quiet --depth 1 --branch "$tag" "$LARKDOCIO_REPO_URL" "$clone" \
            >/dev/null 2>&1; then
        rm -rf "$work"
        log "NOTE: could not read ${tag}'s release notes — skipping the what-changed report."
        return 0
    fi
    notes="$clone/RELEASE_NOTES.md"
    changelog="$clone/CHANGELOG.md"

    if [ ! -f "$notes" ]; then
        rm -rf "$work"
        log "NOTE: $tag carries no RELEASE_NOTES.md, so there is no what-changed report for" \
            "this span — read the changelog for those releases."
        return 0
    fi

    # Every version documented in EITHER document, narrowed to (from, to]. The
    # changelog is in the union on purpose: a version it documents and the notes do
    # not is an un-noted release, and saying so beats leaving a silent gap.
    span="$(
        { notes_headers "$notes"; notes_headers "$changelog"; } \
            | cut -d'|' -f1 | sort -u \
            | while IFS= read -r v; do
                  if ver_gt "$v" "$from" && ! ver_gt "$v" "$to"; then printf '%s\n' "$v"; fi
              done | sort -rV
    )"

    if [ -z "$span" ]; then
        rm -rf "$work"
        log "NOTE: no release-notes sections are documented between ${from} and ${to}."
        return 0
    fi

    log ""
    log "What changed between ${from} and ${to}:"
    while IFS= read -r v; do
        [ -n "$v" ] || continue
        header="$(notes_headers "$notes" | grep "^${v}|" | head -1 | cut -d'|' -f2- || true)"
        if [ -z "$header" ]; then
            log "  NOTE: ${v} has no release-notes section — see" \
                "${PKG}-CHANGELOG.md for that release."
            continue
        fi
        log "  $header"
        notes_subsections "$notes" "$v" | while IFS= read -r sub; do
            [ -n "$sub" ] && log "    - $sub"
        done
    done <<SPAN
$span
SPAN
    log "  (full text: ${VENDOR_DIR}/${PKG}-RELEASE_NOTES.md, refreshed when you update)"
    log ""
    rm -rf "$work"
}

# ---- --check mode ----------------------------------------------------------

if [ "${1:-}" = "--check" ]; then
    log "Checking for a newer ${PKG} release (network)…"
    latest_tag=$(remote_latest_tag)
    [ -n "$latest_tag" ] || die "no tags found at $LARKDOCIO_REPO_URL"
    latest_ver=$(tag_to_version "$latest_tag")
    local_ver=$(vendored_version)

    if [ -z "$local_ver" ]; then
        log "vendored: (none)   latest: ${latest_ver} (${latest_tag})"
        echo "UPDATE AVAILABLE: no ${PKG} wheel vendored yet; latest is ${latest_ver}."
        exit 0
    fi

    log "vendored: ${local_ver}   latest: ${latest_ver} (${latest_tag})"
    if [ "$local_ver" = "$latest_ver" ]; then
        echo "UP TO DATE: vendored ${PKG} ${local_ver} matches the latest tag."
        exit 0
    fi
    # Is the latest strictly newer than what's vendored?
    newest=$(printf '%s\n%s\n' "$local_ver" "$latest_ver" | sort -V | tail -1)
    if [ "$newest" = "$latest_ver" ]; then
        echo "UPDATE AVAILABLE: vendored ${local_ver} < latest ${latest_ver}. Run this script (no --check) to update."
        # WHICH PATH an update would take, so the integrator knows whether it costs a
        # build. One lightweight ls-remote for the branch head — NO clone, and like
        # everything else in --check it writes nothing anywhere. Narration, so stderr:
        # --check's STDOUT stays exactly the one verdict line an installed nag greps.
        if git ls-remote --heads "$LARKDOCIO_REPO_URL" "${LARKDOCIO_DIST_BRANCH:-dist}" 2>/dev/null \
                | grep -q .; then
            log "An update would use the ${LARKDOCIO_DIST_BRANCH:-dist} fast path (shallow clone, no build) if it carries ${latest_ver}."
        else
            log "An update would build from tag ${latest_tag} (no ${LARKDOCIO_DIST_BRANCH:-dist} branch on the remote)."
        fi
        # …and what actually changed, so the answer is actionable. Report-only, and
        # skipped entirely (no clone) when LARKDOCIO_CHECK_NOTES=0.
        if [ "$LARKDOCIO_CHECK_NOTES" != "0" ]; then
            print_notes_delta "$local_ver" "$latest_ver" "$latest_tag"
        fi
    else
        echo "AHEAD: vendored ${local_ver} is newer than the latest tag ${latest_ver} (pinned to an unreleased build?)."
    fi
    exit 0
fi

# ---- build + vendor mode ---------------------------------------------------

TAG="${1:-}"
WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# TWO SCRATCH DIRECTORIES, AND NO INPUT MAY EVER MAKE THEM ONE (LD-591).
# The `dist` fast path clones into one; the build-from-tag path writes its wheel
# into the other. They used to be "$WORK/$DIST_BRANCH" and "$WORK/dist" — the
# SAME directory under the default branch name — so a bailed-out fast path left a
# stale published wheel sitting in the build's output and the alphabetical
# `head -1` below vendored it under the new tag's name. Both names are CONSTANT
# and neither is derived from $DIST_BRANCH, so no value of LARKDOCIO_DIST_BRANCH
# (`dist`, `build`, anything) can collide them again.
DIST_CLONE_DIR="$WORK/dist-clone"
BUILD_OUT_DIR="$WORK/build-output"

# ---- the dist FAST PATH (tried first, falls back silently) ------------------
# larkdocio publishes a consumer-only `dist` branch at every release: one commit
# carrying just the wheel, the four consumer documents and a short README. When
# it is there and current, a shallow clone of it gets us the same artifacts this
# script would otherwise spend a full clone plus a wheel build to produce — no build
# toolchain, no history, no source.
#
# It is a FAST PATH, never a requirement. `dist` is absent on any repo state older
# than its introduction and can lag a tag if a publish failed, so every failure here
# falls through to the build-from-tag path below, which is unchanged and remains the
# authoritative way to reproduce any version. A log line always says which path ran,
# so a vendor-integrator is never guessing — but ./vendor/ ends up identical either
# way, which is why the fallback is invisible in the result.
#
# Set LARKDOCIO_NO_DIST=1 to skip the fast path (what the sandbox's fallback case
# does, and an escape hatch if a publish is ever known-bad).
LARKDOCIO_NO_DIST="${LARKDOCIO_NO_DIST:-0}"
DIST_BRANCH="${LARKDOCIO_DIST_BRANCH:-dist}"

# Version embedded in a wheel FILENAME (larkdocio-1.2.0-py3-none-any.whl → 1.2.0).
wheel_version() {  # <path or filename>
    local base="${1##*/}"
    base="${base#${PKG}-}"
    echo "${base%%-*}"
}

# The ONE ${PKG} wheel in a build output directory. Zero is the build's own failure;
# MORE THAN ONE is a REFUSAL, never a guess (LD-591) — the same posture, and the same
# voice, as vendored_version() takes for the long-lived ${VENDOR_DIR}/. Sort order
# cannot answer "which of these is the one you asked for", and until LD-591 `head -1`
# answered it wrong. Echoes the wheel's path; dies otherwise, having written
# nothing to ${VENDOR_DIR}/.
sole_built_wheel() {  # <build output dir>
    local dir="$1" whls count
    whls=$(ls "$dir"/${PKG}-*.whl 2>/dev/null || true)
    count=$(printf '%s\n' "$whls" | grep -c '.' || true)
    if [ "$count" -eq 0 ]; then
        die "build produced no ${PKG} wheel."
    fi
    if [ "$count" -gt 1 ]; then
        printf '%s\n' "$whls" | sed 's/^/    /' >&2
        die "$count ${PKG} wheels in the build output directory ($dir) — refusing to guess which is current. Nothing was vendored and ${VENDOR_DIR}/ is untouched. This directory is scratch space created by this run, so a second wheel means something else wrote into it: re-run, and report it if it repeats."
    fi
    printf '%s\n' "$whls"
}

# The ONE ${PKG} wheel in <dir>, or nothing. Silent, unlike sole_built_wheel(): the
# fast path asks this of the dist clone and of nothing else may it guess either — two
# wheels there are not a choice to make by sort order (LD-694), so the caller falls back.
only_wheel_in() {  # <dir> -> echoes the wheel path, or returns nonzero
    local whls count
    whls=$(ls "$1"/${PKG}-*.whl 2>/dev/null || true)
    count=$(printf '%s\n' "$whls" | grep -c '.' || true)
    [ "$count" -eq 1 ] || return 1
    printf '%s\n' "$whls"
}

# Vendor the artifacts sitting in <dir>: the wheel (exactly one is pinned) plus any
# of the four consumer documents that are present. Shared by both paths so the
# result cannot differ between them — the build path STAGES its wheel and the tag's
# documents in a directory of its own and calls this only after every check has
# passed, so ./vendor/ is written once, at the end, or not at all (LD-694: it used to
# drop the documents before the build, so a refusal left the old wheel beside the new
# tag's documents while saying ./vendor/ was untouched).
vendor_from_dir() {  # <dir> -> echoes the wheel filename
    local src="$1" whl name doc
    whl=$(only_wheel_in "$src") || return 1
    name="${whl##*/}"
    mkdir -p "$VENDOR_DIR"
    rm -f "$VENDOR_DIR"/${PKG}-*.whl
    cp "$whl" "$VENDOR_DIR/$name"
    for doc in GUIDE CHANGELOG RELEASE_NOTES LARK_SETUP; do
        if [ -f "$src/${PKG}-${doc}.md" ]; then
            cp "$src/${PKG}-${doc}.md" "$VENDOR_DIR/${PKG}-${doc}.md"
        fi
    done
    echo "$name"
}

# Try the fast path. Echoes the vendored wheel filename on success; returns nonzero
# (silently, with a logged reason) on anything at all, so the caller falls back.
try_dist_fast_path() {  # <requested tag or ""> <latest tag or "">
    local want_tag="$1" latest_tag="$2" clone dist_whl dist_ver want_ver
    [ "$LARKDOCIO_NO_DIST" = "1" ] && { log "Skipping the $DIST_BRANCH fast path (LARKDOCIO_NO_DIST=1)."; return 1; }

    clone="$DIST_CLONE_DIR"
    if ! git clone --quiet --depth 1 --branch "$DIST_BRANCH" "$LARKDOCIO_REPO_URL" "$clone" \
            >/dev/null 2>&1; then
        log "No $DIST_BRANCH branch on the remote — using the build-from-tag path."
        return 1
    fi
    dist_whl=$(only_wheel_in "$clone") \
        || { log "The $DIST_BRANCH branch does not carry exactly one ${PKG} wheel — refusing to guess; using the build-from-tag path."; return 1; }
    dist_ver="$(wheel_version "$dist_whl")"

    # It has to be the version being ASKED for. An explicit tag must match exactly;
    # with no tag the request is "the latest", so a dist older than the newest tag is
    # STALE and we build instead.
    # With no tag named AND no tag on the remote there is nothing to compare against; that
    # edge is said out loud rather than passed silently (round 9, Z20).
    want_ver="$(tag_to_version "${want_tag:-$latest_tag}")"
    if [ -z "$want_ver" ]; then
        log "No tag was named and the remote has none, so the $DIST_BRANCH wheel's version (${dist_ver}) is NOT checked against a tag."
    elif [ "$dist_ver" != "$want_ver" ]; then
        log "The $DIST_BRANCH branch carries ${dist_ver}, not ${want_ver} — using the build-from-tag path."
        return 1
    fi

    vendor_from_dir "$clone" || { log "Could not vendor from $DIST_BRANCH — using the build-from-tag path."; return 1; }
    return 0
}

# The fast path needs to know what "latest" is when no tag was named. One
# lightweight ls-remote, the same call --check already uses; empty is handled.
DIST_LATEST_TAG=""
if [ -z "$TAG" ]; then DIST_LATEST_TAG="$(remote_latest_tag)"; fi

if FAST_WHEEL="$(try_dist_fast_path "$TAG" "$DIST_LATEST_TAG")" && [ -n "$FAST_WHEEL" ]; then
    REQ_LINE="${PKG} @ file:${VENDOR_DIR}/${FAST_WHEEL}"
    log ""
    log "Vendored: $VENDOR_DIR/$FAST_WHEEL  (via the $DIST_BRANCH fast path — no build)"
    log "Pin this requirement in the consumer's requirements file:"
    log ""
    echo "$REQ_LINE"
    log ""
    log "Then reinstall into the consumer venv, e.g.:"
    log "    .venv/bin/pip install --force-reinstall --no-deps '$VENDOR_DIR/$FAST_WHEEL'"
    exit 0
fi

CLONE="$WORK/repo"
log "Cloning the ${PKG} repository (network)…"
git clone --quiet "$LARKDOCIO_REPO_URL" "$CLONE" || die "clone failed: $LARKDOCIO_REPO_URL"

if [ -z "$TAG" ]; then
    # `|| true` binds to the whole pipeline (|| is looser than |), so a failed
    # `git tag` can't trip `set -euo pipefail` before the `|| die` below reports it.
    # Filter to `^v[0-9]` release tags (same guard as remote_latest_tag) so a
    # stray non-release tag is never auto-picked as the latest to build+vendor.
    TAG=$(git -C "$CLONE" tag --sort=-v:refname | grep -E '^v[0-9]' | head -1 || true)
    [ -n "$TAG" ] || die "no tags in $LARKDOCIO_REPO_URL — cannot pick a latest."
    log "Latest tag: $TAG"
fi
git -C "$CLONE" checkout --quiet "refs/tags/$TAG" 2>/dev/null \
    || git -C "$CLONE" checkout --quiet "$TAG" \
    || die "tag not found: $TAG"

# ---- refresh the shipped consumer guide (LD-128) ---------------------------
# larkdocio ships an AGENTS-style consumer guide INSIDE THE WHEEL
# (larkdocio/GUIDE.md, read at runtime via larkdocio.guide()). Drop/refresh it
# next to the vendored wheel so a consumer has the canonical usage + capability
# matrix on disk without unzipping the wheel or reaching the network. Sourced
# from the CHECKED-OUT TAG's own tree — deterministic, the same bytes the wheel
# packages (the wheel-RECORD test proves GUIDE.md ships in the wheel; this copy
# is its on-disk sibling), and independent of the build below so a tag
# without GUIDE.md simply skips the drop.
#
# Every drop below lands in $STAGE, never in ./vendor/: the documents and the wheel
# are vendored TOGETHER by vendor_from_dir, after the build and the version check
# have passed, so a refusal leaves ./vendor/ exactly as it was (LD-694).
STAGE="$WORK/stage"
mkdir -p "$STAGE"
GUIDE_SRC="$CLONE/src/larkdocio/GUIDE.md"
GUIDE_DEST="$STAGE/${PKG}-GUIDE.md"
if [ -f "$GUIDE_SRC" ]; then
    cp "$GUIDE_SRC" "$GUIDE_DEST"
    log "Staged the consumer guide (vendored with the wheel): ${GUIDE_DEST##*/}"
else
    log "NOTE: $TAG carries no src/larkdocio/GUIDE.md — skipping the guide drop."
fi

# ---- refresh the two release documents -------------------------------------
# A vendoring consumer's ENTIRE view of larkdocio is the wheel plus what lands
# here, and until these two dropped that view carried no changelog and no release
# notes at all — so "what changed under me since I last re-vendored?" had no
# in-band answer. Both ship inside the wheel as well; these are their on-disk
# siblings, readable without unzipping anything. Same shape as the guide drop
# above: sourced from the CHECKED-OUT TAG's own tree (deterministic, the same bytes
# that tag's wheel packages), staged before the build (vendored after it), and a tag that lacks a
# document just skips its drop with its OWN note rather than failing the run.
CHANGELOG_SRC="$CLONE/CHANGELOG.md"
CHANGELOG_DEST="$STAGE/${PKG}-CHANGELOG.md"
if [ -f "$CHANGELOG_SRC" ]; then
    cp "$CHANGELOG_SRC" "$CHANGELOG_DEST"
    log "Staged the changelog (vendored with the wheel): ${CHANGELOG_DEST##*/}"
else
    log "NOTE: $TAG carries no CHANGELOG.md — skipping the changelog drop."
fi

NOTES_SRC="$CLONE/RELEASE_NOTES.md"
NOTES_DEST="$STAGE/${PKG}-RELEASE_NOTES.md"
if [ -f "$NOTES_SRC" ]; then
    cp "$NOTES_SRC" "$NOTES_DEST"
    log "Staged the release notes (vendored with the wheel): ${NOTES_DEST##*/}"
else
    log "NOTE: $TAG carries no RELEASE_NOTES.md — skipping the release-notes drop."
fi

# ---- refresh the Lark-application walkthrough ------------------------------
# The document a BRAND-NEW consumer needs before any of the others: nothing in the
# library works until a Lark app exists, holds the scopes, and can reach the
# documents, and none of those three is a code change. It ships inside the wheel too
# (larkdocio.lark_setup()); this is its on-disk sibling, readable before anything is
# installed at all — which is the case the in-wheel copy cannot serve. Same shape as
# the drops above: the CHECKED-OUT TAG's own root copy, staged before the build (vendored after it), and a
# tag that lacks the document skips with its OWN note rather than failing the run.
SETUP_SRC="$CLONE/LARK_SETUP.md"
SETUP_DEST="$STAGE/${PKG}-LARK_SETUP.md"
if [ -f "$SETUP_SRC" ]; then
    cp "$SETUP_SRC" "$SETUP_DEST"
    log "Staged the Lark setup walkthrough (vendored with the wheel): ${SETUP_DEST##*/}"
else
    log "NOTE: $TAG carries no LARK_SETUP.md — skipping the Lark-setup drop."
fi

# Isolated build environment (does not touch the consumer's venv).
# All build tooling output goes to STDERR so this script's STDOUT stays exactly
# the requirement line — setup-consumer.sh captures our stdout verbatim as the
# pin, and the setuptools backend is chatty on stdout otherwise.
BUILD_VENV="$WORK/buildvenv"
log "Building the wheel…"
"$PYTHON" -m venv "$BUILD_VENV" >&2
"$BUILD_VENV/bin/pip" install --quiet --upgrade pip build >&2
( cd "$CLONE" && "$BUILD_VENV/bin/python" -m build --wheel --outdir "$BUILD_OUT_DIR" ) >&2

# Capture, then test, then select (LD-543, amended by LD-591): the ORIGINAL
# one-liner `WHEEL=$(ls … | head -1)` had no guard, so under `set -euo pipefail`
# a no-match ls failed the ASSIGNMENT and the die below was unreachable dead
# code — the failure it exists to explain died bare. That half stands.
#
# LD-543's second half said `head -1` itself stayed CORRECT here, because
# "$WORK/dist was created by this run's own build and cannot hold a stale
# artifact (unlike the long-lived vendor/, whose multi-wheel case
# vendored_version() now refuses)". THE REASON IS KEPT — a directory a run
# creates for its own build genuinely cannot hold an artifact from an earlier
# run — and only the CONCLUSION is superseded, because the PREMISE was falsified
# after it was written: the `dist` fast path was added later and cloned into
# $WORK/$DIST_BRANCH, which for the default branch name IS $WORK/dist, so a
# bailed-out fast path left a stale published wheel in the build's own output
# directory. The directory was no longer this run's build alone, `head -1`
# picked 1.41.0 alphabetically, and the run printed it against "(tag v1.42.0)"
# and exited 0 (LD-591, consumer-filed). Both halves of the answer are kept: the
# directories are separated at the top of this mode so the premise holds again,
# AND selection refuses a second wheel rather than trusting the premise.
WHEEL=$(sole_built_wheel "$BUILD_OUT_DIR")
WHEEL_NAME="${WHEEL##*/}"

# The success line below says "Vendored: <file>  (tag $TAG)", which CLAIMS the
# file is that tag's version. It claimed it unchecked, which is how a 1.41.0
# wheel got printed against v1.42.0 under a zero exit. Check it here, BEFORE
# ${VENDOR_DIR}/ is touched, so a refusal leaves the consumer's existing pin
# intact instead of clearing it. An empty want-version (a tag no version can be
# derived from) is handled explicitly: the check is skipped with a note, never
# silently passed and never turned into a false refusal.
WANT_VER="$(tag_to_version "$TAG")"
BUILT_VER="$(wheel_version "$WHEEL_NAME")"
if [ -z "$WANT_VER" ]; then
    log "NOTE: no version could be derived from tag '$TAG' — skipping the built-version check."
elif [ "$BUILT_VER" != "$WANT_VER" ]; then
    die "the build produced ${PKG} ${BUILT_VER}, but this run asked for ${WANT_VER} (tag ${TAG}) — refusing to vendor a wheel that is not the version requested. Nothing was vendored and ${VENDOR_DIR}/ is untouched. The wheel built was: ${WHEEL_NAME}."
fi

# Every check has passed: vendor the wheel and the staged documents together, the
# same way the fast path does (vendor_from_dir removes older wheels so exactly one
# is pinned).
cp "$WHEEL" "$STAGE/$WHEEL_NAME"
vendor_from_dir "$STAGE" >/dev/null || die "could not vendor from the staging directory ($STAGE)."

REQ_LINE="${PKG} @ file:${VENDOR_DIR}/${WHEEL_NAME}"

log ""
log "Vendored: $VENDOR_DIR/$WHEEL_NAME  (tag $TAG)"
log "Pin this requirement in the consumer's requirements file:"
log ""
echo "$REQ_LINE"
log ""
log "Then reinstall into the consumer venv, e.g.:"
log "    .venv/bin/pip install --force-reinstall --no-deps '$VENDOR_DIR/$WHEEL_NAME'"
