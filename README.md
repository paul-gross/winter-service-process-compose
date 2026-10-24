# ❄️ winter-service-process-compose

A [winter](https://github.com/paul-gross/winter) extension that adds
[process-compose](https://github.com/F1bonacci/process-compose) service orchestration to a workspace. Each scope — a
feature environment or the workspace — gets its own headless process-compose daemon, so several environments run the
full application stack side by side.

📚 **Documentation:** <https://paul-gross.github.io/winter-docs/>

## ✨ Features

- **Tmux-compatible manifest** — reads the `[[service]]` entries `winter-service-tmux` reads, so an entry moves between
  providers unchanged. `[service.restart]` adds a native restart policy.
- **One daemon per scope** — no sockets, ports, or state shared between environments.
- **Stdlib-only runtime** — the provider needs only `python3` and the `process-compose` binary.

## 🚀 Setup

Install `process-compose` (1.122.0 or newer), copy [workflow/config.toml.example](./workflow/config.toml.example) to
`.winter/config/winter-service-process-compose/config.toml`, and bind the provider in `[capabilities]`. See the
[context hub](./context/index.md) for the schema and behavior.

## License

Source-available under the Functional Source License 1.1 (FSL-1.1-ALv2). Each release converts to Apache License 2.0 two
years after it ships. See LICENSE.
