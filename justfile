help:
    @just --list

# Set up the development environment (uses uv if available, otherwise venv + pip)
install:
    #!/usr/bin/env bash
    set -euo pipefail
    if command -v uv >/dev/null 2>&1; then
        echo "Using uv to sync the environment..."
        uv sync
    else
        echo "uv not found, falling back to python3 -m venv + pip..."
        if [ ! -d .venv ]; then
            python3 -m venv .venv
        fi
        ./.venv/bin/pip install --upgrade pip
        ./.venv/bin/pip install -e ".[dev]"
    fi
    echo "✓ Environment ready. Activate with: source .venv/bin/activate"

# Run all checks (ruff, mypy, pytest)
check: ruff mypy test
    @echo "✓ All checks passed!"

# Run a tool via `uv run` if available, otherwise via .venv/bin
_run TOOL *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    if command -v uv >/dev/null 2>&1; then
        uv run {{TOOL}} {{ARGS}}
    else
        ./.venv/bin/{{TOOL}} {{ARGS}}
    fi

# Run ruff linter
ruff:
    @echo "Running ruff..."
    @just _run ruff check src tests

# Run mypy type checker
mypy:
    @echo "Running mypy..."
    @just _run mypy

# Run pytest
test:
    @echo "Running pytest..."
    @just _run pytest

# Run the scaffold CLI (uses uv run if available, otherwise the .venv)
scaffold *ARGS:
    @just _run scaffold {{ARGS}}

# Format code with ruff
format:
    @echo "Formatting code..."
    @just _run ruff format src tests
