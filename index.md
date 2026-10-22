# Winter service orchestration via process-compose

Implements winter's `service` capability slot over [process-compose](https://github.com/F1bonacci/process-compose): one
headless process-compose daemon per scope — each feature environment, plus the workspace scope — so environments run
side by side without sharing sockets, ports, or process state. It reads the same `[[service]]` manifest the tmux
provider reads, so an entry moves between the two providers unchanged; the one addition is `[service.restart]`.

Read [context/index.md](./context/index.md) when setting up, operating, or developing this provider — the hub for the
setup steps, manifest schema, status and log behavior, and dev loop.
