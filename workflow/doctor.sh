#!/usr/bin/env sh
# Doctor probe for winter-service-process-compose.
#
# Emits one NDJSON object per check on stdout:
#   {"name": "...", "status": "pass|warn|fail", "message"?: "...", "remediation"?: "..."}
#
# Check: the process-compose binary is on PATH and at least the version the provider's flag set was probed on.
# The script always exits 0 so the check's own status surfaces in `winter doctor`.
set -u

MIN_VERSION="1.122.0"
INSTALL_HINT="Install process-compose >= ${MIN_VERSION} (https://f1bonacc1.github.io/process-compose/installation/) and put it on PATH."

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g' | tr -d '\r\n'
}

emit() {
  # Usage: emit <status> <message> [<remediation>]
  if [ -n "${3:-}" ]; then
    printf '{"name":"process-compose","status":"%s","message":"%s","remediation":"%s"}\n' \
      "$1" "$(json_escape "$2")" "$(json_escape "$3")"
  else
    printf '{"name":"process-compose","status":"%s","message":"%s"}\n' "$1" "$(json_escape "$2")"
  fi
}

# True when dotted version $1 >= $2.
version_at_least() {
  [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n 1)" = "$2" ]
}

if ! command -v process-compose >/dev/null 2>&1; then
  emit fail "process-compose is not on PATH" "$INSTALL_HINT"
  exit 0
fi

version=$(process-compose version 2>/dev/null | sed -n 's/^Version:[[:space:]]*v\{0,1\}\([0-9][0-9.]*\).*/\1/p' | head -n 1)
if [ -z "$version" ]; then
  emit fail "could not read the process-compose version" "$INSTALL_HINT"
elif version_at_least "$version" "$MIN_VERSION"; then
  emit pass "process-compose ${version}"
else
  emit fail "process-compose ${version} is older than ${MIN_VERSION}" "$INSTALL_HINT"
fi
exit 0
