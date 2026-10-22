# Setup

1. Install [process-compose](https://github.com/F1bonacci/process-compose) **1.122.0 or newer** — the version whose flag
   set this provider is built on. `winter doctor` fails with install guidance when the binary is missing or older.
2. Copy [workflow/config.toml.example](../workflow/config.toml.example) to
   `workspace:/.winter/config/winter-service-process-compose/config.toml` and declare the services. Services already
   declared for `winter-service-tmux` work unchanged.
3. Bind the provider in `workspace:/.winter/config.toml`, alone or beside another provider. Each service is owned by
   exactly one bound provider, so a service declared in two manifests needs one of them removed:

   ```toml
   [capabilities]
   service = "winter-service-process-compose"
   ```

4. Run `winter ws init <env>`, `winter provision <env>`, then `winter service up <env> --wait`.

The runtime is stdlib-only: the provider needs `python3` and the `process-compose` binary, nothing else.
