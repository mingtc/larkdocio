#!/usr/bin/env bash
# KIT-CLASS: PROJECT — this project's bootstrap (.venv, pip install -e, pytest, hooks path where the kit is present).
#
# setup.sh — larkdocio's one front door. Two modes, auto-resolved by context:
#
#   DEV mode (default; run with no args from inside the larkdocio clone)
#     Build/reuse the dev environment: create .venv, `pip install -e .[dev]`, wire the
#     kanban git hooks (only where scripts/githooks/ exists — the maintainers' working
#     repository; the public repository does not carry it, and pointing core.hooksPath at
#     a missing directory would silently switch off the developer's own hooks), run
#     `pytest -q` as a sanity gate, print next steps. Idempotent.
#
#   CONSUMER mode (`./setup.sh --for <consumer-repo-path>`, OR auto-detected when this
#     script is invoked from a CWD that is a DIFFERENT git repo root)
#     Do NOT build a dev env. Delegate to consumers/setup-consumer.sh against that
#     consumer (vendors a built wheel into the consumer's ./vendor/, copies the refresh
#     script), then leave the remaining manual steps to that script + the README.
#
#   Ambiguous context (neither a larkdocio clone nor a recognizable git repo) → explain
#     both modes and exit non-zero. This script never guesses.
#
# Bash only — no new dependencies. See `./setup.sh --help`.
#
set -euo pipefail

# The larkdocio clone root = the directory this script lives in.
LARKDOCIO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PYTHON="${PYTHON:-python3}"

log()  { printf '%s\n' "$*" >&2; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
larkdocio setup.sh — one front door, two modes.

USAGE:
  ./setup.sh                       Dev mode: set up THIS larkdocio clone for development.
  ./setup.sh --for <repo-path>     Consumer mode: vendor larkdocio into <repo-path>.
  /path/to/larkdocio/setup.sh      Auto: dev mode inside the clone; consumer mode when run
                                   from a DIFFERENT git repo root (that repo is the consumer).
  ./setup.sh --help                This help.

DEV MODE (default, no args, from inside the clone):
  - creates/reuses .venv and runs `pip install -e ".[dev]"` (larkdocio + pytest + build)
  - wires the kanban git hooks (`git config core.hooksPath scripts/githooks`) ONLY if
    scripts/githooks/ exists; otherwise your git hook configuration is left alone
  - runs `pytest -q` as a sanity gate
  - prints next steps (env var names, a CLI check, and the process files where present)
  Idempotent — safe to re-run.

CONSUMER MODE:
  Delegates to consumers/setup-consumer.sh, which copies scripts/update_larkdocio.sh, the
  advisory git-hook template (copied, not installed) and the router skill pack
  (.claude/skills/), then vendors the latest release's wheel into the consumer's ./vendor/
  (taken from the dist branch, built from the tag when it cannot be). The requirement line
  to pin, the .env credential names and the hook wiring are printed by that step.
  The CANONICAL consumer instructions live in the README — see its
  "Consuming larkdocio" section (this script does not duplicate them).
EOF
}

# ── Argument / mode resolution ──────────────────────────────────────────────
MODE=""
CONSUMER_TARGET=""

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  --for)
    MODE="consumer"
    CONSUMER_TARGET="${2:-}"
    [ -n "$CONSUMER_TARGET" ] || die "--for needs a consumer repo path. See ./setup.sh --help."
    ;;
  "")
    # Auto-detect from the invocation context (CWD's git repo root).
    INVOKER_TOPLEVEL="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null || true)"
    if [ -n "$INVOKER_TOPLEVEL" ]; then
      INVOKER_TOPLEVEL="$(cd "$INVOKER_TOPLEVEL" && pwd -P)"
    fi
    if [ "$INVOKER_TOPLEVEL" = "$LARKDOCIO_ROOT" ]; then
      MODE="dev"
    elif [ -n "$INVOKER_TOPLEVEL" ]; then
      # Invoked from a DIFFERENT git repo root → that repo is the consumer.
      MODE="consumer"
      CONSUMER_TARGET="$INVOKER_TOPLEVEL"
    else
      MODE="ambiguous"
    fi
    ;;
  *)
    die "Unknown argument '$1'. See ./setup.sh --help."
    ;;
esac

# ── Ambiguous: explain both modes, exit non-zero (never guess). ─────────────
if [ "$MODE" = "ambiguous" ]; then
  log "Cannot resolve context: the current directory is not the larkdocio clone and is not a git repo root."
  log ""
  log "  • To set up larkdocio for development, run this from inside the larkdocio clone:"
  log "        cd '$LARKDOCIO_ROOT' && ./setup.sh"
  log "  • To vendor larkdocio into a consumer repo, name it explicitly:"
  log "        ./setup.sh --for /path/to/consumer-repo"
  log ""
  log "  (See ./setup.sh --help and the README's \"Consuming larkdocio\" section.)"
  exit 2
fi

# ── CONSUMER mode ───────────────────────────────────────────────────────────
if [ "$MODE" = "consumer" ]; then
  CONSUMER_SETUP="$LARKDOCIO_ROOT/consumers/setup-consumer.sh"
  [ -f "$CONSUMER_SETUP" ] || die "consumers/setup-consumer.sh not found at $CONSUMER_SETUP."
  CONSUMER_TARGET="$(cd "$CONSUMER_TARGET" 2>/dev/null && pwd -P)" || die "consumer path does not exist: $CONSUMER_TARGET"
  [ "$CONSUMER_TARGET" != "$LARKDOCIO_ROOT" ] || die "the consumer path IS the larkdocio clone — run with no args for dev mode instead."

  log "Consumer mode → onboarding consumer at: $CONSUMER_TARGET"
  log "Delegating to consumers/setup-consumer.sh …"
  log ""
  bash "$CONSUMER_SETUP" "$CONSUMER_TARGET"

  log ""
  log "Consumer onboarding delegated. Canonical instructions: the README's \"Consuming larkdocio\" section."
  exit 0
fi

# ── DEV mode ────────────────────────────────────────────────────────────────
cd "$LARKDOCIO_ROOT"
[ -f "$LARKDOCIO_ROOT/pyproject.toml" ] || die "no pyproject.toml at $LARKDOCIO_ROOT — is this the larkdocio clone?"
command -v "$PYTHON" >/dev/null 2>&1 || die "python3 not found (set \$PYTHON)."

VENV="$LARKDOCIO_ROOT/.venv"
if [ ! -d "$VENV" ]; then
  log "Creating virtual environment at .venv …"
  "$PYTHON" -m venv "$VENV"
else
  log "Reusing existing .venv."
fi

log "Installing larkdocio (editable) + dev tools (pytest, build) …"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -e ".[dev]"

# Wire the kanban commit-message role-prefix guard (idempotent) — ONLY where the hook
# directory exists. The public repository does not carry scripts/githooks/, and setting
# core.hooksPath to a missing directory makes git read hooks from nowhere: every hook the
# developer already had in .git/hooks/ would stop running without a word (LD-694).
if [ -d "$LARKDOCIO_ROOT/scripts/githooks" ] \
    && git -C "$LARKDOCIO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$LARKDOCIO_ROOT" config core.hooksPath scripts/githooks
  log "Wired git hooks: core.hooksPath = scripts/githooks (commit-message role-prefix guard)."
fi

# Standalone convenience: seed a local .env from the example on first setup so a
# standalone clone has a credentials file to fill in. Never overwrites an existing
# .env; .env is gitignored (never committed).
ENV_SEEDED=false
if [ ! -f "$LARKDOCIO_ROOT/.env" ] && [ -f "$LARKDOCIO_ROOT/.env.example" ]; then
  cp "$LARKDOCIO_ROOT/.env.example" "$LARKDOCIO_ROOT/.env"
  ENV_SEEDED=true
  log "Seeded .env from .env.example — edit it with your Lark read credentials before running downloads."
fi

log "Running the sanity gate: pytest -q …"
if "$VENV/bin/python" -m pytest -q; then
  GATE="pytest -q: PASS"
else
  GATE="pytest -q: FAIL — investigate before you start work"
fi

cat >&2 <<EOF

────────────────────────────────────────────────────────────────────────────
larkdocio dev environment ready.  ($GATE)

Activate the venv:      source .venv/bin/activate
Check the CLI:          larkdocio --version    (or: .venv/bin/larkdocio --version)
Credentials:            edit .env (gitignored; seeded from .env.example on first setup).
    LARK_READ_APP_ID=...        # preferred
    LARK_READ_APP_SECRET=...
    # (or legacy LARK_APP_ID / LARK_APP_SECRET)
    # LARK_WRITE_APP_ID / LARK_WRITE_APP_SECRET are used by every write surface (live tests: scratch doc only).
Run the gates:          ./scripts/verify.sh    (pytest, then python -m build)
EOF

# The process kit's pointers, printed only where the kit is present: the public repository
# carries none of these files, and a next step naming a file that is not there is not one.
if [ -d "$LARKDOCIO_ROOT/progress/todo" ] && [ -f "$LARKDOCIO_ROOT/CLAUDE.md" ]; then
  log "The board:              ls progress/todo/ ; ./scripts/check-board.sh"
  log "Operating manual:       CLAUDE.md   ·   project facts: PROJECT.md"
fi
log "────────────────────────────────────────────────────────────────────────────"
