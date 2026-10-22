# Winter service orchestration via process-compose

Implements winter's `service` capability slot over [process-compose](https://github.com/F1bonacci/process-compose): one
headless process-compose daemon per scope — each feature environment, plus the workspace scope — so environments run
side by side without sharing sockets, ports, or process state. It reads the same `[[service]]` manifest the tmux
provider reads, so an entry moves between the two providers unchanged; the one addition is `[service.restart]`.

The manifest schema, with the keys this provider honors, ignores, and refuses, is annotated in
[workflow/config.toml.example](./workflow/config.toml.example).
