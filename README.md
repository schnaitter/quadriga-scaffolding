# QUADRIGA scaffolding

This tool updates a QUADRIGA OER to contain common files (scripts, CSS, JS, ...) to the latest version.

## Installation (for development)

The project is a standard `pyproject.toml`-based package managed with [`uv`](https://docs.astral.sh/uv/).

Clone the repository and create the development environment in one step:

```console
$ git clone https://github.com/quadriga-dk/quadriga-scaffolding.git
$ cd quadriga-scaffolding
$ uv sync
```

`uv sync` will create a `.venv/`, install the package in **editable** mode, and pull in the development tools listed under `[dependency-groups].dev` (currently `pytest`, `ruff`, `mypy`).

If you prefer plain `pip` over `uv`:

```console
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install -e ".[dev]"  # or: pip install -e . && pip install pytest ruff mypy
```

### Running the development tools

```console
$ uv run pytest          # tests
$ uv run ruff check .    # lint
$ uv run mypy            # type-check
```

## Usage

> **⚠️ Work in progress.** The CLI currently only validates that the packaged
> `data/` tree matches the manifest. The `oer_path` argument and `--update`
> flag are accepted but the diff/update behaviour described below is not yet
> implemented.

The package installs a `scaffold` console script. The common files and the manifest ship with the package via `importlib.resources`, so the tool no longer depends on being run from inside the repository clone.

To compare the current state of an OER to the newest version of the common files:

```console
$ uv run scaffold ../path/to/oer/
```

To update the files to the newest version:

```console
$ uv run scaffold --update ../path/to/oer/
```

The script will overwrite existing files with their newest version and possibly delete files that were marked as deleted in the scaffolding manifest.

Equivalent invocations:

```console
$ uv run python -m quadriga_scaffolding ../path/to/oer/
$ scaffold ../path/to/oer/        # if the venv is activated
```

## Structure of the repo

The package lives under `src/quadriga_scaffolding/`:

- `scaffold.py` — core logic (parsing the manifest, resolving packaged resources, checking the data tree).
- `cli.py` — command-line entry point (`scaffold` console script).
- `data/` — the files and folders that are common amongst all OERs and that will be used to create or overwrite files in the target OER. **These ship with the installed package.**
- `data/scaffold.txt` — manifest listing files/directories to be created or overwritten (lines starting with `+ `) and deleted (lines starting with `- `). Every other line is treated as a comment.

Tests live under `tests/`.
