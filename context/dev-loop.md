# Testing changed provider code

Unit tests never need a running daemon; every external system sits behind a Protocol with a fake in `tests/fakes.py`.
One live-adapter test runs only when `process-compose` is on `PATH`.

```bash
uv run pytest && uv run ruff check . && uv run pyright
```

To exercise in-progress changes against a real environment, point winter at the checkout. The override dispatches to
this provider alone, so it does not collide with other bound providers:

```bash
winter --service-orchestrator=./<env>/winter-service-process-compose service up <env> --wait
```

Run the entrypoint without winter by setting `WINTER_WORKSPACE_DIR` and calling `workflow/service <action> …`.

The doctor probe is `bash workflow/doctor.sh`; it prints one NDJSON object per check and always exits 0.
