#!/usr/bin/env sh
# on_env_destroy hook for winter-service-process-compose.
#
# Invoked by `winter ws destroy` with cwd at the env root and WINTER_EXT_DIR, WINTER_WORKSPACE_DIR and WINTER_ENV set.
# Best-effort: stops the env's process-compose instance through the provider's own `down`, so the daemon, its
# processes, and any orphans of a dead daemon are cleaned up. Never fails env destroy.
set -u

: "${WINTER_ENV:?WINTER_ENV not set}"
: "${WINTER_WORKSPACE_DIR:?WINTER_WORKSPACE_DIR not set}"

if [ -n "${WINTER_EXT_DIR:-}" ]; then
  _SRC="$WINTER_EXT_DIR/src"
else
  _SELF="$0"
  while [ -L "$_SELF" ]; do
    _SELF="$(readlink "$_SELF")"
  done
  _SRC="$(cd "$(dirname "$_SELF")/.." && pwd)/src"
fi

echo "winter-service-process-compose: stopping the instance for env '${WINTER_ENV}'..." >&2
PYTHONPATH="$_SRC${PYTHONPATH:+:$PYTHONPATH}" python3 -m process_compose_orchestrator.cli down "$WINTER_ENV" >&2 || true
exit 0
