# Provider behavior

## Runtime layout

One headless process-compose daemon runs per scope. Its files live in `<scope-root>/.winter/process-compose/`, where the
scope root is `<ws>/<env>` for a feature env and `<ws>` for the workspace scope:

| File             | Holds                                                                 |
| ---------------- | --------------------------------------------------------------------- |
| `pc.sock`        | The daemon's unix socket                                              |
| `config.json`    | The generated process-compose config                                  |
| `daemon.log`     | The daemon's own log                                                  |
| `state.json`     | The recorded daemon pid, which is also its session id, and the socket |
| `lock`           | Per-scope advisory lock taken by `up`, `down`, and `restart`          |
| `logs/<svc>.log` | One JSON-lines log per service                                        |

The workspace scope's directory is machine-local state. `winter-ext.toml` declares it under `[excludes]`, so
`winter ws init` adds it to the workspace's `.git/info/exclude` and adopters have nothing to ignore by hand. A feature
env's directory sits inside the env directory, which winter already excludes.

A unix socket path is limited to 108 bytes. When `pc.sock` would exceed 107, the socket moves to
`${XDG_RUNTIME_DIR:-/tmp}/winter-pc-<uid>/<sha256 of the scope root, first 16 hex>.sock` (directory mode 0700). The
fallback is derived from the scope alone, so every action finds it again without reading state.

The generated config never holds resolved environment values: each command is wrapped so its own shell sources
`winter env <scope> --resolve` and then the service `env` table when it launches. `disable_env_expansion` is set, and
every process sets `flush_each_line` and `add_timestamp` so its log file is current and timestamped.

## Lifecycle

A feature-env name whose `<ws>/<env>/` directory does not exist is a scope that does not exist, and no action creates
anything for it: `status` reports nothing running, `logs` finds no files and emits nothing, and `up` exits non-zero
naming the missing directory. `down` and `restart` first look for a daemon still answering on the scope's socket: with
none, `down` notes that there is no running instance and exits 0, and `restart` fails as it does for a stopped scope.
The fallback socket derives from the scope path alone, so a daemon can outlive its env directory (an `rm -rf` while it
ran, an interrupted destroy); `down` and `restart` act on it without taking the lock, which lives under the missing
root, and create nothing there. Only the state directory beneath an existing scope root is created on demand, and the
lock refuses a root that vanishes underneath it with an error naming the directory.

- **`up`, no instance**: launches the daemon with every process disabled, then enables them in one update. The first
  update after a launch restarts every process even with identical config, so enabling at that point avoids a later
  spurious restart.
- **`up`, live instance**: `project update` with the regenerated config. A process whose definition is unchanged keeps
  its pid; a changed one restarts.
- **`up`, stale socket** (daemon killed, socket left behind): reaps the orphaned session, removes the socket and state,
  then starts fresh.
- **`up <env>/<pattern>`**: starts only the matched services plus their transitive same-scope `depends_on`. A wildcard
  in the scope segment is refused. An empty scope is a no-op with exit 0.
- **Readiness**: when a started service declares a health check, `up` polls `process list` until each is ready or
  `WINTER_SERVICE_TIMEOUT` elapses, then exits non-zero naming the services that are not ready. It also fails early when
  a service has exited. It never calls `project is-ready --wait`, which blocks forever on a process that failed for
  good.
- **`down`**: a whole scope uses process-compose `down`, which kills each process group and removes the socket. A
  partial `down` stops only the matched processes. For a stale instance it reaps the recorded session without needing
  the binary. No instance is exit 0.
- **`restart <env>/<pattern>`**: restarts the matched processes on the live daemon. With no live daemon it exits
  non-zero naming the scope. Restart truncates that process's log.
- **Missing binary**: every action except `describe` and `catalog` exits non-zero naming `process-compose` and how to
  install it; `down` needs it only for a live instance.

## Status and health mapping

| Field    | Value                                                                                                               |
| -------- | ------------------------------------------------------------------------------------------------------------------- |
| `state`  | `Running` → `running`; terminal states (`Completed`, `Error`, `Skipped`, `Disabled`, …) → `stopped`; else `unknown` |
| `health` | `healthy` when ready; `unhealthy` when a probe exists and the process is not ready; `unknown` when it has no probe  |
| `handle` | The process pid                                                                                                     |
| `since`  | The process start time, as RFC3339                                                                                  |

A declared service with no live instance reports `stopped`. Live processes that no manifest declares — services merged
from an extension — are listed as well. A stale socket still yields a valid document plus a diagnostic on stderr.

## Logs

`logs` reads the per-service files directly, so it works with no daemon running. Each entry is NDJSON
`{ts, env, svc, msg}` with `ts` in microsecond UTC RFC3339, merged across services by time. One trailing newline is
stripped from each message and bare-newline entries are dropped.

| Flag                 | Behavior                                                                               |
| -------------------- | -------------------------------------------------------------------------------------- |
| `-n N` or `-n all`   | The last N entries per service, or all                                                 |
| `--since`, `--until` | Inclusive filters on `ts`, applied by the provider                                     |
| `-f`                 | Follows the matched files, reopening from the start when one is truncated by a restart |
| `-t`                 | Accepted; `ts` is always emitted                                                       |

## Version

The flag set was probed on process-compose 1.122.0; `winter doctor` requires that version or newer.
