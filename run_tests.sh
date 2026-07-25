#!/bin/bash

set -e

# uv run ruff check . --exclude chirpstack_mqtt

uv run ruff check
uv run pytest