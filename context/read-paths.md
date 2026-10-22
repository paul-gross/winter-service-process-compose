# Agent read paths

- **A service's log**: `winter service status <env> --json` carries each service's `log_path`; the file is
  `<scope-root>/.winter/process-compose/logs/<svc>.log`, JSON lines with a timestamp per entry.
- **A daemon that will not start**: read `<scope-root>/.winter/process-compose/daemon.log`. A failed launch surfaces its
  tail on stderr, and an over-long socket path is reported there.
- **Orphans after a crash**: `status` prints a stale-socket diagnostic; `winter service up <env>` or `down <env>` reaps
  the recorded session.
