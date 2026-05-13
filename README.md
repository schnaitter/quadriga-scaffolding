# QUADRIGA scaffolding

This tool updates a QUADRIGA OER to contain common files (scripts, CSS, JS, ...) to the latest version.

## Installation (for development)

The project is a standard `pyproject.toml`-based package. The recommended way to set up a development environment is via [`just`](https://github.com/casey/just):

```console
$ git clone https://github.com/quadriga-dk/quadriga-scaffolding.git
$ cd quadriga-scaffolding
$ just install
```

If you don't have `just` yet, install it via your package manager (e.g. `brew install just`, `apt install just`, `cargo install just`) — see the [just installation docs](https://github.com/casey/just#installation) for more options.

`just install` will detect whether [`uv`](https://docs.astral.sh/uv/) is available and use it (`uv sync`) if so. Otherwise it falls back to creating a `.venv/` with `python3 -m venv` and installing the package in **editable** mode together with the development tools (`pytest`, `ruff`, `mypy`) via `pip`.

If you'd rather run the steps yourself:

With `uv`:

```console
$ uv sync
```

Or with plain `pip`:

```console
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install -e ".[dev]"
```

### Running the development tools

With [`just`](https://github.com/casey/just):

```console
$ just check   # run all checks (ruff, mypy, pytest)
$ just ruff    # lint
$ just format  # auto-format
$ just mypy    # type-check
$ just test    # tests
```

Or with `uv`:

```console
$ uv run pytest          # tests
$ uv run ruff check .    # lint
$ uv run ruff format .   # auto-format
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
$ just scaffold ../path/to/oer/
```

To update the files to the newest version:

```console
$ just scaffold --update ../path/to/oer/
```

(`just scaffold` uses `uv run scaffold` when `uv` is available, and falls back to the `scaffold` entry point in `.venv/` otherwise.)

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
