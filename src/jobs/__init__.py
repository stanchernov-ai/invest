"""Split pipeline jobs: prepare -> debate -> deliver.

Each module exposes an async run_<phase>(run_id=...) entrypoint. They hand off
state via storage_client checkpoints (runs/{run_id}/{phase}.json) so each can run
as its own Azure Function invocation with an independent 10-minute ceiling."""
