#!/usr/bin/env bash
# The `check` command (OQ-B4): everything CI must run. Add the pipeline file once the CI system is known.
set -euo pipefail
cd "$(dirname "$0")/.."

uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run lint-imports
uv run pytest "$@"
