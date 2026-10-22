# Winter service orchestration via process-compose — hub

## Reference

| Topic                                          | Read when…                                                                                                           |
| ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| [Setup](./setup.md)                            | …installing `process-compose`, writing the manifest, or binding the provider in `[capabilities]`                     |
| [Manifest schema](./manifest.md)               | …declaring a service, or moving an entry between this provider and `winter-service-tmux`                             |
| [Provider behavior](./provider.md)             | …reading status and health mapping, the log source and flags, the runtime layout, or instance lifecycle and recovery |
| [Agent read paths](./read-paths.md)            | …finding a service's log, or diagnosing why a daemon would not start                                                 |
| [Testing changed provider code](./dev-loop.md) | …exercising in-progress changes through `--service-orchestrator`, or checking the doctor probe                       |
| [README.md](../README.md)                      | …installing the extension                                                                                            |
