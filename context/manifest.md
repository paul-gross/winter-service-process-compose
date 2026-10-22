# Manifest schema

The manifest is `workspace:/.winter/config/winter-service-process-compose/config.toml`, a list of `[[service]]` tables
in the `winter-service-tmux` vocabulary. The annotated example is
[workflow/config.toml.example](../workflow/config.toml.example).

| Key                                                                       | Treatment                                                                    |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `name`, `scope`, `cmd` (`command` alias), `cwd`, `env`, `port`            | Honored. `scope` is `project` (default, one per feature env) or `workspace`. |
| `health` with `type` `url` or `cmd`, and `timeout`                        | Honored; becomes a process-compose readiness probe.                          |
| `depends_on`                                                              | Honored for same-scope names.                                                |
| `startup`                                                                 | Honored; maps to a restart policy when `[service.restart]` is absent.        |
| `restart`                                                                 | Native to this provider; `winter-service-tmux` ignores it.                   |
| `target`, `log`                                                           | Accepted and ignored (tmux-only).                                            |
| empty `cmd`, `health.type` of `log` or `uptime`, cross-scope `depends_on` | Refused at validation with a message naming this provider.                   |

## `[service.restart]`

```toml
[service.restart]
policy = "on_failure"   # "no", "on_failure", or "always"
backoff_seconds = 2     # optional
max_restarts = 3        # optional
```

It maps onto process-compose's `availability` block. Without it, `[service.startup]` maps to `on_failure` with
`max_restarts = retries` and `backoff_seconds = retry_delay`.

## Moving an entry between providers

An entry that avoids the refused keys parses under both providers, because each ignores the keys it does not know.
`${VAR}` and `$$` in `cmd` reach the shell verbatim, as they would in a tmux pane; `${VAR}` in a health target is
interpolated when the config is rendered.

## Extension-declared services

On `up`, entries from the file `WINTER_SERVICE_MANIFEST` names are merged into the scope. Entries with no `cmd`
(image-only) are skipped with a note on stderr, and a name that collides with the workspace manifest is refused.
